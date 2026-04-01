"""
Test file for GPIO Control Service
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.services.gpio_control_service import GPIOControlService

def test_gpio_control_service():
    """Test the GPIO control service functionality."""
    
    # Create a mock configuration
    config = {
        'gpio': {
            'valve1_pin': 23,
            'valve2_pin': 24
        }
    }
    
    try:
        # Initialize the service
        gpio_service = GPIOControlService(config)
        print("GPIO Control Service initialized successfully")
        # Note: is_simulation_mode is now a public attribute
        print(f"Is simulation mode: {gpio_service.is_simulation_mode}")
        
        # Test getting valve status (should be False initially)
        status1 = gpio_service.get_valve_status(1)
        status2 = gpio_service.get_valve_status(2)
        print(f"Valve 1 status: {status1}")
        print(f"Valve 2 status: {status2}")
        
        # Test activating valve 1
        result = gpio_service.activate_valve(1, duration=1)
        print(f"Activate valve 1 result: {result}")
        
        # Check status after activation
        status1 = gpio_service.get_valve_status(1)
        print(f"Valve 1 status after activation: {status1}")
        
        # Test deactivating valve 1
        result = gpio_service.deactivate_valve(1)
        print(f"Deactivate valve 1 result: {result}")
        
        # Check status after deactivation
        status1 = gpio_service.get_valve_status(1)
        print(f"Valve 1 status after deactivation: {status1}")
        
        # Test getting all valve statuses
        all_status = gpio_service.get_all_valve_status()
        print(f"All valve statuses: {all_status}")
        
        # Cleanup
        gpio_service.cleanup()
        print("Test completed successfully")
        
    except Exception as e:
        print(f"Test failed with error: {e}")
        raise

if __name__ == "__main__":
    test_gpio_control_service()