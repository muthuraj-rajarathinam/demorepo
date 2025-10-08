#!/bin/bash
# ---------------------------------------
# EC2 User Data Script for 3-Tier App (Docker Compose version)
# ---------------------------------------

# --- Pre-requisites Setup ---
echo "Starting system update and installing dependencies..."
yum update -y
amazon-linux-extras install docker -y
yum install -y git docker-compose-plugin

# Start Docker
systemctl start docker
systemctl enable docker
usermod -a -G docker ec2-user

# --- Clone and Setup ---
cd /home/ec2-user
mkdir -p app
cd app

echo "Cloning repository..."
git clone https://github.com/muthuraj-rajarathinam/3tierapp_aws.git
cd 3tierapp_aws

# --- Environment variables (from Terraform) ---
export DB_HOST=${db_endpoint}
export DB_USER=${db_user}
export DB_PASS=${db_pass}

# Save environment vars for compose
cat > .env <<EOF
DB_HOST=${db_endpoint}
DB_USER=${db_user}
DB_PASS=${db_pass}
EOF

# --- Run using Docker Compose ---
echo "Starting Docker Compose services..."
docker compose up -d --build

echo "Deployment complete at $(date)" > /home/ec2-user/deploy.log
