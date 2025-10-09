import json
import uuid
from datetime import datetime
from flask import Flask, request, jsonify, send_file
import mysql.connector
from mysql.connector import Error
import os
from flask import Flask, send_from_directory
from flask_cors import CORS
# --- Flask App Configuration ---
app = Flask(__name__)
CORS(app)

# --- Environment Variables for AWS RDS ---
DB_HOST = os.environ.get("DB_HOST")
DB_USER = os.environ.get("DB_USER")
DB_PASS = os.environ.get("DB_PASS")
# DB_NAME remains 'ecommerce_db'
DB_NAME = os.environ.get("DB_NAME", "ecommerce_db") 


# --- Database Utilities ---

# CHANGE 1: Allow optional db_name to connect to server before DB exists
def get_connection(db_name=DB_NAME):
    """Connect to AWS RDS MySQL. If db_name is None, connects only to the server."""
    try:
        conn = mysql.connector.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASS,
            # Use db_name if provided, otherwise defaults to None, connecting to server root
            database=db_name 
        )
        return conn
    except Error as e:
        # Note: If credentials/host are wrong, this will fail immediately.
        # If 'db_name' is missing, this is where the 1049 error happens.
        print(f"❌ Database connection error: {e}")
        return None


# CHANGE 2: Implement logic to CREATE DATABASE first
def init_db():
    """Initializes DB schema and inserts sample products."""
    conn = None
    cursor = None
    
    # --- Phase 1: Connect to server (no DB specified) and create the database ---
    
    # Connect without specifying a database name (passing None)
    conn = get_connection(db_name=None)
    if not conn:
        print("❌ Could not connect to the MySQL server to create the database.")
        return
    
    try:
        cursor = conn.cursor()
        
        # Create the missing database if it doesn't exist
        print(f"Attempting to create database: {DB_NAME}")
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS {DB_NAME}")
        conn.commit()
        
    except Error as e:
        print(f"❌ Error during database creation: {e}")
        return
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected():
            conn.close()

    # --- Phase 2: Connect to the newly created database and create tables ---
    
    # Now connect *with* the created database name
    conn = get_connection(db_name=DB_NAME)
    if not conn:
        print(f"❌ Could not connect to the database ({DB_NAME}) for table initialization.")
        return

    try:
        cursor = conn.cursor()

        # Create tables
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id VARCHAR(20) PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                price DECIMAL(10,2) NOT NULL,
                flavor VARCHAR(255),
                img TEXT
            );
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                order_id VARCHAR(50) PRIMARY KEY,
                order_date DATETIME NOT NULL,
                total_amount DECIMAL(10,2) NOT NULL,
                status VARCHAR(50) NOT NULL
            );
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS order_items (
                item_id INT AUTO_INCREMENT PRIMARY KEY,
                order_id VARCHAR(50),
                product_id VARCHAR(20),
                product_name VARCHAR(255),
                quantity INT,
                unit_price DECIMAL(10,2),
                FOREIGN KEY (order_id) REFERENCES orders(order_id)
            );
        """)

        # Insert default products
        products_data = [
            ('prod-001', '70% Dark Cacao Bar', 8.00, 'Intense, deep, pure', 'https://images.pexels.com/photos/6167328/pexels-photo-6167328.jpeg'),
            ('prod-002', 'Sea Salt Dark Squares', 12.00, 'Dark chocolate, sea salt flakes', 'https://images.unsplash.com/photo-1504674900247-0877df9cc836'),
            ('prod-003', 'Espresso Milk Bar', 10.00, 'Smooth milk chocolate, espresso', 'https://images.unsplash.com/photo-1504674900247-0877df9cc836'),
            ('prod-004', 'White Raspberry Truffle', 14.00, 'White chocolate, raspberry', 'https://images.unsplash.com/photo-1527515637462-cff94eecc1ac'),
            ('prod-005', 'Champagne Truffle', 17.00, 'Milk chocolate, champagne', 'https://images.pexels.com/photos/4399753/pexels-photo-4399753.jpeg'),
            ('prod-006', 'Salted Caramel Praline', 16.00, 'Milk chocolate, salted caramel', 'https://images.pexels.com/photos/7676087/pexels-photo-7676087.jpeg')
        ]

        for p in products_data:
            cursor.execute("""
                INSERT IGNORE INTO products (id, name, price, flavor, img)
                VALUES (%s, %s, %s, %s, %s);
            """, p)

        conn.commit()
        print("✅ Database initialized successfully.")
    
    except Error as e:
        print(f"❌ Initialization error during table/data creation: {e}")
        
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected():
            conn.close()


# Initialize database on startup
init_db()


# --- 3. Frontend Serving Route ---
@app.route('/')
def serve_index():
    try:
        # Note: You need to ensure 'index.html' is in the backend build context
        return send_from_directory("static", "index.html")
    except FileNotFoundError:
        return "index.html not found", 404

@app.route('/health')
def health():
    return "OK", 200


# --- 4. API Endpoints ---
@app.route('/api/products', methods=['GET'])
def get_products():
    conn = get_connection()
    if not conn:
        return jsonify({"error": "DB connection failed"}), 500
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id, name, price, flavor, img FROM products;")
    products = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify({"products": products})


@app.route('/api/checkout', methods=['POST'])
def checkout():
    data = request.get_json()
    cart_items = data.get('items', [])
    if not cart_items:
        return jsonify({"message": "Cart is empty."}), 400

    conn = get_connection()
    if not conn:
        return jsonify({"message": "DB connection failed."}), 500
    cursor = conn.cursor(dictionary=True)

    product_ids = [item['id'] for item in cart_items]
    placeholders = ','.join(['%s'] * len(product_ids))
    cursor.execute(f"SELECT id, name, price FROM products WHERE id IN ({placeholders})", product_ids)
    db_products = cursor.fetchall()
    lookup = {p['id']: p for p in db_products}

    total = 0.0
    order_items = []
    for item in cart_items:
        pid = item['id']
        qty = item['qty']
        if pid not in lookup:
            return jsonify({"message": f"Product {pid} not found"}), 400
        price = float(lookup[pid]['price'])
        total += price * qty
        order_items.append((pid, lookup[pid]['name'], qty, price))

    order_id = str(uuid.uuid4())
    cursor.execute("INSERT INTO orders (order_id, order_date, total_amount, status) VALUES (%s, %s, %s, %s)",
                   (order_id, datetime.now(), total, "Processing"))

    for pid, name, qty, price in order_items:
        cursor.execute("INSERT INTO order_items (order_id, product_id, product_name, quantity, unit_price) VALUES (%s, %s, %s, %s, %s)",
                       (order_id, pid, name, qty, price))

    conn.commit()
    cursor.close()
    conn.close()

    return jsonify({
        "orderId": order_id,
        "status": "Processing",
        "total": round(total, 2),
        "message": "Order placed successfully!"
    })


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
