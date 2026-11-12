"""
API Server for Raspberry Pi Irrigation System
This script starts the Flask API server for valve control.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.main_service import main_service
from src.api.api_service import api_service
from src.services.watchdog import Watchdog, sd_notify


def main():
    """Start the API server."""
    # Initialize the main service
    if not main_service.initialize():
        print("Failed to initialize main service")
        sys.exit(1)

    print("Main service initialized successfully")
    print("Starting API server...")

    watchdog = Watchdog(main_service, health_url=f'http://127.0.0.1:{api_service.port}/api/health')
    watchdog.start()
    # Tell systemd (Type=notify) that start-up is complete
    sd_notify('READY=1\nSTATUS=Serving API')

    try:
        api_service.run()
    except KeyboardInterrupt:
        print("API server stopped by user")
    except Exception as e:
        print(f"Error starting API server: {e}")
        raise
    finally:
        sd_notify('STOPPING=1')
        watchdog.stop()
        main_service.cleanup()


if __name__ == "__main__":
    main()
