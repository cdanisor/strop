"""
Cron Scheduler for Raspberry Pi Irrigation System
This service handles scheduling weather updates every 3 hours.
"""
import time
import threading
import logging
from datetime import datetime, timedelta
from src.services.weather.weather_service import WeatherService

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class CronScheduler:
    """Scheduler for running periodic tasks."""
    
    def __init__(self):
        """Initialize the cron scheduler."""
        self.weather_service = WeatherService()
        self.is_running = False
        self.thread = None
    
    def start(self):
        """Start the scheduler in a background thread."""
        if not self.is_running:
            self.is_running = True
            self.thread = threading.Thread(target=self._run_scheduler, daemon=True)
            self.thread.start()
            logger.info("Weather update scheduler started")
    
    def stop(self):
        """Stop the scheduler."""
        self.is_running = False
        if self.thread:
            # Set a timeout for joining to prevent hanging
            self.thread.join(timeout=5)
        logger.info("Weather update scheduler stopped")
    
    def _run_scheduler(self):
        """Run the scheduler loop."""
        while self.is_running:
            try:
                # Update weather data
                logger.info("Running scheduled weather update")
                self.weather_service.update_weather_data()
      
                # Wait for 3 hours (10800 seconds) with periodic checks
                # Break the sleep into smaller chunks to allow for quicker shutdown
                remaining_time = 10800
                while remaining_time > 0 and self.is_running:
                    sleep_time = min(10, remaining_time)  # Sleep in 10-second chunks
                    time.sleep(sleep_time)
                    remaining_time -= sleep_time
      
            except Exception as e:
                logger.error(f"Error in scheduler loop: {e}")
                # Wait 1 minute before retrying
                time.sleep(60)