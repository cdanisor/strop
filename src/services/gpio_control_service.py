"""
GPIO Control Service for Raspberry Pi Irrigation System
This service handles relay operations for controlling solenoid valves.
"""

import time
import logging
import threading
from typing import Dict, Any, Optional
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import database module
from src.database import Database

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
        
        # Store active timers for valves
        self.active_timers = {}
        
        # Store start times for valves
        self.valve_start_times = {}
        
        # Initialize database
        self.db = Database()
        
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
    
            # Store the start time for this valve
            import datetime
            start_time = datetime.datetime.now()
            self.valve_start_times[valve_id] = start_time
            
            # Log the valve activation to database
            self.db.insert_valve_log(valve_id, 'Opened', None, start_time)
        
            # If duration is specified, schedule deactivation
            if duration is not None and duration > 0:
                # Cancel any existing timer for this valve
                if valve_id in self.active_timers:
                    self.active_timers[valve_id].cancel()
      		
                # Create a new timer to deactivate the valve after duration
                timer = threading.Timer(duration, self.deactivate_valve, [valve_id])
                timer.daemon = True  # Dies when main thread dies
                timer.start()
                self.active_timers[valve_id] = timer
                logger.info(f"Valve {valve_id} will be deactivated after {duration} seconds")
        
            return True
        
        except Exception as e:
            logger.error(f"Failed to activate valve {valve_id}: {e}")
            return False
    
    def deactivate_valve(self, valve_id: int, manual: bool = False) -> bool:
        """
        Deactivate specified valve.
        
        Args:
            valve_id (int): ID of the valve to deactivate (1 or 2)
            manual (bool): Whether the deactivation was manual (via API) or automatic (by timer)
        
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
            # Cancel any active timer for this valve
            if valve_id in self.active_timers:
                self.active_timers[valve_id].cancel()
                del self.active_timers[valve_id]
        
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
    
            # Calculate duration since activation
            duration = None
            if valve_id in self.valve_start_times:
                import datetime
                start_time = self.valve_start_times[valve_id]
                end_time = datetime.datetime.now()
                duration = int((end_time - start_time).total_seconds())
                # Remove the start time after calculating duration
                del self.valve_start_times[valve_id]
        
            # Find the last 'on' operation for this valve and update it with duration
            # Get all logs for this valve
            logs = self.db.get_valve_logs(valve_id=valve_id, limit=100)
    
            # Find the most recent 'Opened' operation that doesn't have a duration yet
            last_on_log = None
            last_on_log_id = None
            for log in logs:
                if log['status'] == 'Opened' and log['duration'] is None:
                    if last_on_log is None or log['timestamp'] > last_on_log['timestamp']:
                        last_on_log = log
                        last_on_log_id = log['id']
    
            # If we found a matching 'Opened' log, update it with the duration and status
            if last_on_log_id is not None:
                # Set appropriate status based on manual flag
                status = 'Manually Stopped' if manual else 'Finished'
                # Update the existing log with duration and status
                success = self.db.update_valve_log_status(last_on_log_id, duration, status)
                if not success:
                    logger.warning(f"Failed to update log entry {last_on_log_id}, inserting new entry instead")
                    self.db.insert_valve_log(valve_id, status, duration)
            else:
                # No matching 'Opened' log found, insert a new log with appropriate status
                status = 'Manually Stopped' if manual else 'Finished'
                self.db.insert_valve_log(valve_id, status, duration)
        
            # Return the status to indicate if it was manual or automatic deactivation
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
        # Cancel all active timers
        for timer in self.active_timers.values():
            timer.cancel()
        self.active_timers.clear()
        
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