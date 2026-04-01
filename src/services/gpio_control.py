"""
GPIO Control Service for Raspberry Pi Irrigation System
This service handles relay operations for controlling solenoid valves.
"""

import time
import logging
from typing import Dict, Any, Optional
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class GPIOControlService:
    """Service for controlling GPIO pins and relays for irrigation valves."""
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the GPIO control service.
        
        Args:
            config (Dict[str, Any]): Configuration dictionary containing GPIO settings
        """
        self.config = config
        self.valve1_pin = config.get('gpio', {}).get('valve1_pin', 23)
        self.valve2_pin = config.get('gpio', {}).get('valve2_pin', 24)
        self.is_initialized = False
        self.is_simulation_mode = False
        
        # Store valve states
        self.valve_states = {
            1: False,  # Valve 1 is off by default
            2: False   # Valve 2 is off by default
        }
        
        # Setup GPIO or simulation mode
        self._setup_gpio()
    
    def _setup_gpio(self) -> None:
        """
        Setup GPIO pins for output or use simulation mode.
        """
        try:
            # Try to import RPi.GPIO to check if we're on a Raspberry Pi
            import RPi.GPIO as GPIO
            
            # Use BCM pin numbering
            GPIO.setmode(GPIO.BCM)
            
            # Setup pins as outputs
            GPIO.setup(self.valve1_pin, GPIO.OUT)
            GPIO.setup(self.valve2_pin, GPIO.OUT)
            
            # Set initial state to LOW (relays off)
            GPIO.output(self.valve1_pin, GPIO.LOW)
            GPIO.output(self.valve2_pin, GPIO.LOW)
            
            self.is_initialized = True
            logger.info("GPIO pins initialized successfully")
            
        except ImportError:
            # We're not on a Raspberry Pi, use simulation mode
            self.is_simulation_mode = True
            self.is_initialized = True
            logger.info("Running in simulation mode (no GPIO hardware)")
    
    def activate_valve(self, valve_id: int, duration: Optional[int] = None) -> bool:
        """
        Activate specified valve for given duration.
        
        Args:
            valve_id (int): ID of the valve to activate (1 or 2)
            duration (int, optional): Duration in seconds to keep valve open.
                                     If None, valve stays open indefinitely.
        
        Returns:
            bool: True if activation was successful, False otherwise
        """
        if not self.is_initialized:
            logger.error("GPIO not initialized")
            return False
            
        if valve_id not in [1, 2]:
            logger.error(f"Invalid valve ID: {valve_id}")
            return False
            
        try:
            if self.is_simulation_mode:
                logger.info(f"SIMULATION: Activating valve {valve_id}")
            else:
                # Use actual GPIO
                import RPi.GPIO as GPIO
                if valve_id == 1:
                    GPIO.output(self.valve1_pin, GPIO.HIGH)
                else:
                    GPIO.output(self.valve2_pin, GPIO.HIGH)
                
            self.valve_states[valve_id] = True
            logger.info(f"Valve {valve_id} activated")
            
            # If duration is specified, deactivate after that time
            if duration is not None:
                time.sleep(duration)
                self.deactivate_valve(valve_id)
                
            return True
            
        except Exception as e:
            logger.error(f"Failed to activate valve {valve_id}: {e}")
            return False
    
    def deactivate_valve(self, valve_id: int) -> bool:
        """
        Deactivate specified valve.
        
        Args:
            valve_id (int): ID of the valve to deactivate (1 or 2)
            
        Returns:
            bool: True if deactivation was successful, False otherwise
        """
        if not self.is_initialized:
            logger.error("GPIO not initialized")
            return False
            
        if valve_id not in [1, 2]:
            logger.error(f"Invalid valve ID: {valve_id}")
            return False
            
        try:
            if self.is_simulation_mode:
                logger.info(f"SIMULATION: Deactivating valve {valve_id}")
            else:
                # Use actual GPIO
                import RPi.GPIO as GPIO
                if valve_id == 1:
                    GPIO.output(self.valve1_pin, GPIO.LOW)
                else:
                    GPIO.output(self.valve2_pin, GPIO.LOW)
                
            self.valve_states[valve_id] = False
            logger.info(f"Valve {valve_id} deactivated")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to deactivate valve {valve_id}: {e}")
            return False
    
    def get_valve_status(self, valve_id: int) -> bool:
        """
        Get current status of specified valve.
        
        Args:
            valve_id (int): ID of the valve to check (1 or 2)
            
        Returns:
            bool: True if valve is active, False if inactive
        """
        if valve_id not in [1, 2]:
            logger.error(f"Invalid valve ID: {valve_id}")
            return False
            
        return self.valve_states[valve_id]
    
    def get_all_valve_status(self) -> Dict[int, bool]:
        """
        Get status of all valves.
        
        Returns:
            Dict[int, bool]: Dictionary mapping valve IDs to their status
        """
        return self.valve_states.copy()
    
    def cleanup(self) -> None:
        """
        Cleanup GPIO resources.
        """
        if self.is_initialized and not self.is_simulation_mode:
            try:
                # Use actual GPIO cleanup
                import RPi.GPIO as GPIO
                # Turn off all valves
                GPIO.output(self.valve1_pin, GPIO.LOW)
                GPIO.output(self.valve2_pin, GPIO.LOW)
                
                # Cleanup GPIO
                GPIO.cleanup()
                self.is_initialized = False
                logger.info("GPIO cleanup completed")
                
            except Exception as e:
                logger.error(f"Error during GPIO cleanup: {e}")
        elif self.is_initialized and self.is_simulation_mode:
            logger.info("Simulation mode - no cleanup needed")
    
    def __del__(self):
        """
        Destructor to ensure cleanup when object is destroyed.
        """
        self.cleanup()