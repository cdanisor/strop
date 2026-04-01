# Strop Installation Guide

This guide explains how to install and set up the Strop irrigation control system on a Raspberry Pi 1.

## Prerequisites

- Raspberry Pi 1 (or compatible device)
- SD card with Raspbian OS installed
- Internet connection
- SSH access or direct terminal access
- Project files already present in the current directory

## Installation Script

The installation script `install_strop.sh` is provided for Linux-based systems (including Raspberry Pi).

## How to Use

1. Connect to your Raspberry Pi via SSH or terminal
2. Ensure the project files are in the current directory
3. Run the installation script (no root privileges required):
   ```bash
   ./install_strop.sh
   ```

## What the Installation Does

1. Sets up a virtual environment
2. Installs all project dependencies
3. Creates systemd user services for:
   - API service (port 5000)
   - UI service (port 8000)
4. Enables and starts the services
5. Verifies network accessibility

## Services

After installation, two user services will be running:

- **API Service**: http://localhost:5000
- **UI Service**: http://localhost:8000

## Accessing the System

Once installed, you can access the system from the same device:

1. Open a web browser
2. Navigate to the UI service URL: http://localhost:8000
3. Use the API endpoints for programmatic control

## Troubleshooting

If services fail to start:

1. Check service status:
   ```bash
   systemctl --user status strop-api.service
   systemctl --user status strop-ui.service
   ```

2. View logs:
   ```bash
   journalctl --user -u strop-api.service
   journalctl --user -u strop-ui.service
   ```

3. Ensure all dependencies are installed:
   ```bash
   source venv/bin/activate && pip install -r requirements.txt