FROM python:3.9-slim

WORKDIR /app

# Install dependencies
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app code

COPY . .
#COPY frontend/index.html /app/index.html

COPY frontend /app/static
# Environment variables will be injected from Terraform (via user data)
EXPOSE 8080

# Use Gunicorn for production
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "app:app"]
