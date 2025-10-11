# backend/app.py
import os
import json
import uuid
from datetime import datetime
from contextlib import contextmanager
from flask import Flask, request, jsonify, send_from_directory
from mysql.connector import pooling, Error as MySQLError

# --- Flask App Configuration ---
app = Flask(__name__, static_folder="static", static_url_path="/")
# Environment-driven configuration (set these in your EC2 launch config / container runtime)
DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_USER = os.environ.get("DB_USER", "root")
DB_PASS = os.environ.get("DB_PASS", "")
DB_NAME = os.environ.get("DB_NAME", "elegance_chocolat")
DB_PORT = int(os.environ.get("DB_PORT", 3306))
POOL_NAME = os.environ.get("DB_POOL_NAME", "mypool")
POOL_SIZE = int(os.environ.get("DB_POOL_SIZE", 5))

# Web server port (container listens here)
PORT = int(os.environ.get("PORT", 8080))

# Create a MySQL connection pool at startup
db_pool = None

def init_db_pool():
    global db_pool
    if db_pool is None:
        db_pool = pooling.MySQLConnectionPool(
            pool_name=POOL_NAME,
            pool_size=POOL_SIZE,
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASS,
            database=DB_NAME,
            charset='utf8mb4'
        )

@contextmanager
def get_db():
    """Context manager to get a connection from the pool."""
    conn = None
    try:
        conn = db_pool.get_connection()
        cursor = conn.cursor(dictionary=True)
        yield conn, cursor
    finally:
        if conn:
            conn.commit()
            cursor.close()
            conn.close()

def ensure_database_and_tables():
    """
    Attempts to create the database (if missing) and required tables.
    For RDS you typically create DB ahead of time, but this helps local dev.
    """
    # Attempt to create DB if not exists (needs user privileges)
    try:
        # Create a temporary connection to server (no database)
        import mysql.connector
        tmp = mysql.connector.connect(host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASS)
        tmp_cursor = tmp.cursor()
        tmp_cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{DB_NAME}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;")
        tmp_cursor.close()
        tmp.close()
    except Exception as e:
        # If using managed RDS with limited user, DB might already exist or creation not permitted.
        print("Warning: could not create database automatically (may be fine on RDS):", e)

    # Initialize pool (now that DB exists)
    init_db_pool()

    # Create tables and seed products
    with get_db() as (conn, cursor):
        # products table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id VARCHAR(64) PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                price DECIMAL(10,2) NOT NULL,
                flavor VARCHAR(255),
                img TEXT
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """)
        # orders table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                order_id VARCHAR(64) PRIMARY KEY,
                order_date DATETIME NOT NULL,
                total_amount DECIMAL(10,2) NOT NULL,
                status VARCHAR(64) NOT NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """)
        # order_items table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS order_items (
                item_id INT AUTO_INCREMENT PRIMARY KEY,
                order_id VARCHAR(64) NOT NULL,
                product_id VARCHAR(64) NOT NULL,
                product_name VARCHAR(255) NOT NULL,
                quantity INT NOT NULL,
                unit_price DECIMAL(10,2) NOT NULL,
                FOREIGN KEY (order_id) REFERENCES orders(order_id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """)

        # Seed product data using INSERT ... ON DUPLICATE KEY UPDATE (works with primary key)
        products_data = [
            ('prod-001', '70% Dark Cacao Bar', 8.00, 'Intense, deep, pure', 'https://images.pexels.com/photos/6167328/pexels-photo-6167328.jpeg'),
            ('prod-002', 'Sea Salt Dark Squares', 12.00, 'Dark chocolate, sea salt flakes', 'https://images.unsplash.com/photo-1504674900247-0877df9cc836'),
            ('prod-003', 'Espresso Milk Bar', 10.00, 'Smooth milk chocolate, espresso', 'https://images.unsplash.com/photo-1504674900247-0877df9cc836'),
            ('prod-004', 'White Raspberry Truffle', 14.00, 'White chocolate, raspberry', 'https://images.unsplash.com/photo-1527515637462-cff94eecc1ac'),
            ('prod-005', 'Champagne Truffle', 17.00, 'Milk chocolate, champagne', 'https://images.pexels.com/photos/4399753/pexels-photo-4399753.jpeg'),
            ('prod-006', 'Salted Caramel Praline', 16.00, 'Milk chocolate, salted caramel', 'https://images.pexels.com/photos/7676087/pexels-photo-7676087.jpeg')
        ]
        for p_id, name, price, flavor, img in products_data:
            cursor.execute("""
                INSERT INTO products (id, name, price, flavor, img)
                VALUES (%s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE name=VALUES(name), price=VALUES(price), flavor=VALUES(flavor), img=VALUES(img);
            """, (p_id, name, price, flavor, img))

@app.route('/health', methods=['GET'])
def health_check():
    return "Server is healthy!", 200

# Serve index (static folder)
@app.route('/')
def serve_index():
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/api/products', methods=['GET'])
def get_products():
    with get_db() as (conn, cursor):
        cursor.execute("SELECT id, name, price, flavor, img FROM products;")
        products = cursor.fetchall()

    categories = [
        {"id": 1, "name": "Dark Chocolate", "img": "https://images.pexels.com/photos/65882/chocolate-dark-coffee-confiserie-65882.jpeg", "flavors": ["70% Cacao", "Espresso", "Sea Salt", "Orange Zest"]},
        {"id": 2, "name": "Milk Chocolate", "img": "https://images.unsplash.com/photo-1504674900247-0877df9cc836", "flavors": ["Classic", "Hazelnut", "Caramel", "Almond"]},
        {"id": 3, "name": "Truffles & Pralines", "img": "https://images.pexels.com/photos/19121798/pexels-photo-19121798.jpeg", "flavors": ["Champagne", "Salted Caramel", "Tiramisu", "Rum"]}
    ]
    return jsonify({"categories": categories, "products": products})

@app.route('/api/checkout', methods=['POST'])
def checkout():
    data = request.get_json() or {}
    cart_items = data.get('items', [])
    if not cart_items:
        return jsonify({"message": "Cart is empty."}), 400

    product_ids = list({item['id'] for item in cart_items})
    if not product_ids:
        return jsonify({"message": "No valid items."}), 400

    placeholders = ','.join(['%s'] * len(product_ids))
    try:
        with get_db() as (conn, cursor):
            cursor.execute(f"SELECT id, name, price FROM products WHERE id IN ({placeholders})", tuple(product_ids))
            product_details = cursor.fetchall()
            product_lookup = {p['id']: p for p in product_details}

            total_amount = 0.0
            order_items_to_save = []

            for item in cart_items:
                product_id = item.get('id')
                quantity = int(item.get('qty', 0))
                if product_id not in product_lookup or quantity <= 0:
                    return jsonify({"message": "Invalid item or quantity found in cart."}), 400
                p = product_lookup[product_id]
                unit_price = float(p['price'])
                total_amount += unit_price * quantity
                order_items_to_save.append((product_id, p['name'], quantity, unit_price))

            order_id = str(uuid.uuid4())
            order_date = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            status = "Processing"

            cursor.execute("INSERT INTO orders (order_id, order_date, total_amount, status) VALUES (%s, %s, %s, %s)",
                           (order_id, order_date, total_amount, status))

            for product_id, product_name, quantity, unit_price in order_items_to_save:
                cursor.execute("INSERT INTO order_items (order_id, product_id, product_name, quantity, unit_price) VALUES (%s, %s, %s, %s, %s)",
                               (order_id, product_id, product_name, quantity, unit_price))

            return jsonify({"orderId": order_id, "status": status, "total": round(total_amount, 2), "message": "Order placed successfully!"}), 200

    except MySQLError as e:
        print("Database error during checkout:", e)
        return jsonify({"message": "Server encountered a database error. Please try again."}), 500

if __name__ == '__main__':
    # Initialize DB + pool and create tables
    ensure_database_and_tables()
    # For development only: Flask built-in server (production: use gunicorn)
    app.run(host='0.0.0.0', port=PORT, debug=False)
