"""
Example usage of the GPIO control services
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.main_service import main_service

def main():
    """Demonstrate usage of the GPIO control services."""
    
    # Initialize the main service
    if not main_service.initialize():
        print("Failed to initialize main service")
        return
    
    print("Main service initialized successfully")
    
    try:
        # Get status of all valves
        all_status = main_service.get_all_valve_status()
        print(f"Initial valve statuses: {all_status}")
        
        # Activate valve 1 for 5 seconds
        print("Activating valve 1 for 5 seconds...")
        result = main_service.activate_valve(1, duration=5)
        print(f"Activation result: {result}")
        
        # Check status after activation
        status = main_service.get_valve_status(1)
        print(f"Valve 1 status after activation: {status}")
        
        # Activate valve 2 for 3 seconds
        print("Activating valve 2 for 3 seconds...")
        result = main_service.activate_valve(2, duration=3)
        print(f"Activation result: {result}")
        
        # Check status after activation
        status = main_service.get_valve_status(2)
        print(f"Valve 2 status after activation: {status}")
        
        # Deactivate valve 1
        print("Deactivating valve 1...")
        result = main_service.deactivate_valve(1)
        print(f"Deactivation result: {result}")
        
        # Final status check
        all_status = main_service.get_all_valve_status()
        print(f"Final valve statuses: {all_status}")
        
    except Exception as e:
        print(f"Error during operation: {e}")
    
    finally:
        # Cleanup
        main_service.cleanup()
        print("Cleanup completed")

if __name__ == "__main__":
    main()