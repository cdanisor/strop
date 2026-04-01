"""
API Server for Raspberry Pi Irrigation System
This script starts the Flask API server for valve control.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.main_service import main_service
from src.api.api_service import api_service

def main():
    """Start the API server."""
    # Initialize the main service
    if not main_service.initialize():
        print("Failed to initialize main service")
        return
    
    print("Main service initialized successfully")
    print("Starting API server...")
    
    try:
        # Start the API service
        api_service.run()
    except KeyboardInterrupt:
        print("API server stopped by user")
        main_service.cleanup()
    except Exception as e:
        print(f"Error starting API server: {e}")
        main_service.cleanup()
        raise

if __name__ == "__main__":
    main()