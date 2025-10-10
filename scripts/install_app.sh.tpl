#!/bin/bash
sudo yum update -y

sudo yum install docker git -y
sudo systemctl start docker
sudo systemctl enable docker
sudo usermod -aG docker ec2-user

# Install Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/download/v2.27.0/docker-compose-linux-x86_64" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose
docker-compose version


# --- Clone and Setup ---
cd /home/ec2-user
mkdir -p app
cd app


echo "Cloning repository..."
git clone https://github.com/muthuraj-rajarathinam/demorepo.git
cd demorepo

cat > .env <<EOF
DB_HOST=
DB_USER=admin
DB_PASS=SuperSecret123
EOF

echo "Deployment complete at $(date)" > /home/ec2-user/deploy.log
