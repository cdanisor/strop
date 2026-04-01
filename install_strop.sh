#!/bin/bash

# Strop Installation Script for Raspberry Pi 1
# This script sets up the irrigation control system with virtual environment,
# installs dependencies, creates systemd services, and ensures network accessibility.
# Assumes the project is already present in the working directory.

set -e  # Exit on any error

echo "Starting Strop installation for Raspberry Pi 1..."

# Get the user who ran the script
RUNNING_USER=$(whoami)
echo "Running as user: $RUNNING_USER"

# Set project directory (assuming it's already present)
PROJECT_DIR="$PWD"
echo "Using project directory: $PROJECT_DIR"

# Check if project directory exists
if [ ! -d "$PROJECT_DIR" ]; then
    echo "Error: Project directory $PROJECT_DIR does not exist"
    exit 1
fi

# Update package list
echo "Updating package list..."
sudo apt-get update

# Install required packages
echo "Installing required packages..."
sudo apt-get install -y python3 python3-pip python3-venv

# Create virtual environment
echo "Creating virtual environment..."
cd "$PROJECT_DIR"
python3 -m venv venv

# Activate virtual environment and install dependencies
echo "Installing project dependencies..."
bash -c "source venv/bin/activate && pip install --upgrade pip && pip install -r requirements.txt"

# Create systemd service for API application
echo "Creating API service..."
sudo cat > /etc/systemd/system/strop-api.service << EOF
[Unit]
Description=Strop API Service
After=network.target

[Service]
Type=simple
User=$RUNNING_USER
WorkingDirectory=$PROJECT_DIR
ExecStart=$PROJECT_DIR/venv/bin/python3 $PROJECT_DIR/src/api_server.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Create systemd service for UI
echo "Creating UI service..."
sudo cat > /etc/systemd/system/strop-ui.service << EOF
[Unit]
Description=Strop UI Service
After=network.target

[Service]
Type=simple
User=$RUNNING_USER
WorkingDirectory=$PROJECT_DIR
ExecStart=$PROJECT_DIR/venv/bin/python3 $PROJECT_DIR/ui/server.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Reload systemd daemon
echo "Reloading systemd daemon..."
sudo systemctl daemon-reload

# Enable and start services
echo "Enabling and starting services..."
sudo systemctl enable strop-api.service
sudo systemctl enable strop-ui.service
sudo systemctl start strop-api.service
sudo systemctl start strop-ui.service

# Verify services are running
echo "Checking service status..."
sudo systemctl status strop-api.service --no-pager
sudo systemctl status strop-ui.service --no-pager

# Verify network accessibility
echo "Verifying network accessibility..."
echo "API should be accessible at http://$(hostname -I | awk '{print $1}'):5000"
echo "UI should be accessible at http://$(hostname -I | awk '{print $1}'):8000"

echo "Installation completed successfully!"
echo "Services:"
echo "  - API Service: http://$(hostname -I | awk '{print $1}'):5000"
echo "  - UI Service: http://$(hostname -I | awk '{print $1}'):8000"