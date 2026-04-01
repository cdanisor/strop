"""
Main Service for Raspberry Pi Irrigation System
This service coordinates all system components.
"""

import atexit
import signal
import sys
import time
import logging
from typing import Dict, Any
from src.services.gpio_control_service import GPIOControlService
from src.services.config_service import ConfigService
from src.database import Database
from src.services.weather.weather_service import WeatherService
from src.services.weather.cron_scheduler import CronScheduler
from src.services.valve_cron_scheduler import ValveCronScheduler

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MainService:
    """Main service that coordinates all system components."""
    
    def __init__(self):
        """Initialize the main service."""
        self.config_service = ConfigService()
        self.gpio_service = None
        self.is_running = False
        self.db = Database()
        self.weather_service = None
        self.scheduler = None
        self.valve_scheduler = None
        
        # Register cleanup handler
        atexit.register(self.cleanup)
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def initialize(self) -> bool:
        """
        Initialize the main service and all components.
        
        Returns:
            bool: True if initialization was successful, False otherwise
        """
        try:
            # Check for and terminate any "Opened" records from previous sessions
            opened_count = self.db.check_and_terminate_opened_records()
            if opened_count > 0:
                print(f"Terminated {opened_count} previously opened records")
               
            # Initialize GPIO service
            self.gpio_service = GPIOControlService(self.config_service.get_all())
            
            # Initialize weather service
            self.weather_service = WeatherService()
            
            # Fetch weather data at startup
            self.weather_service.update_weather_data()
            
            # Start the weather update scheduler
            self.scheduler = CronScheduler()
            self.scheduler.start()
    
            # Start the valve cron scheduler
            self.valve_scheduler = ValveCronScheduler()
            self.valve_scheduler.start(self.db, self)
            logger.info("Valve cron scheduler started")
    
            self.is_running = True
            return True
    
        except Exception as e:
            print(f"Failed to initialize main service: {e}")
            return False
    
    def activate_valve(self, valve_id: int, duration: int = None) -> bool:
        """
        Activate specified valve.
        
        Args:
            valve_id (int): ID of the valve to activate (1 or 2)
            duration (int, optional): Duration in seconds to keep valve open
   		
        Returns:
            bool: True if activation was successful, False otherwise
        """
        if not self.is_running or not self.gpio_service:
            print("Main service not initialized")
            return False
   		
        return self.gpio_service.activate_valve(valve_id, duration)
    
    def deactivate_valve(self, valve_id: int, manual: bool = False) -> bool:
        """
        Deactivate specified valve.
        
        Args:
            valve_id (int): ID of the valve to deactivate (1 or 2)
            manual (bool): Whether the deactivation was manual (via API) or automatic (by timer)
    
        Returns:
            bool: True if deactivation was successful, False otherwise
        """
        if not self.is_running or not self.gpio_service:
            print("Main service not initialized")
            return False
    
        result = self.gpio_service.deactivate_valve(valve_id, manual)
        return result
    
    def get_valve_status(self, valve_id: int) -> bool:
        """
        Get status of specified valve.
        
        Args:
            valve_id (int): ID of the valve to check (1 or 2)
   		
        Returns:
            bool: True if valve is active, False if inactive
        """
        if not self.is_running or not self.gpio_service:
            print("Main service not initialized")
            return False
   		
        return self.gpio_service.get_valve_status(valve_id)
    
    def get_all_valve_status(self) -> Dict[int, bool]:
        """
        Get status of all valves.
        
        Returns:
            Dict[int, bool]: Dictionary mapping valve IDs to their status
        """
        if not self.is_running or not self.gpio_service:
            print("Main service not initialized")
            return {}
   		
        return self.gpio_service.get_all_valve_status()
    
    def cleanup(self) -> None:
        """
        Cleanup all resources.
        """
        if self.is_running:
            try:
                # Stop the valve scheduler first
                if self.valve_scheduler:
                    self.valve_scheduler.stop()
      
                # Stop the weather scheduler
                if self.scheduler:
                    self.scheduler.stop()
      
                # Cleanup GPIO service
                if self.gpio_service:
                    self.gpio_service.cleanup()
      
                self.is_running = False
                print("System cleanup completed")
            except Exception as e:
                print(f"Error during cleanup: {e}")
                # Even if there's an error, we should still set is_running to False
                self.is_running = False
    
    def _signal_handler(self, signum, frame):
        """
        Handle shutdown signals.
        """
        print(f"Received signal {signum}, shutting down...")
        self.cleanup()
        # Give some time for cleanup before exiting
        time.sleep(1)
        sys.exit(0)

# Global instance
main_service = MainService()