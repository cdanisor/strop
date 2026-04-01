"""
Cron Scheduler for Raspberry Pi Irrigation System
This service handles scheduling weather updates every 3 hours using APScheduler.
"""
from apscheduler.schedulers.background import BackgroundScheduler
import logging
from datetime import datetime
from src.services.weather.weather_service import WeatherService

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class CronScheduler:
    """Scheduler for running periodic tasks using APScheduler."""
    
    def __init__(self):
        """Initialize the cron scheduler."""
        self.weather_service = WeatherService()
        self.scheduler = BackgroundScheduler()
        self.is_running = False
    
    def start(self):
        """Start the scheduler."""
        if not self.is_running:
            # Add the job to run every 3 hours (10800 seconds)
            self.scheduler.add_job(
                func=self._run_weather_update,
                trigger="interval",
                seconds=10800,  # 3 hours in seconds
                id="weather_update_job"
            )
            
            self.scheduler.start()
            self.is_running = True
            logger.info("Weather update scheduler started with APScheduler")
    
    def stop(self):
        """Stop the scheduler."""
        if self.is_running:
            try:
                self.scheduler.shutdown(wait=True)
                self.is_running = False
                logger.info("Weather update scheduler stopped")
            except Exception as e:
                logger.error(f"Error stopping scheduler: {e}")
    
    def _run_weather_update(self):
        """Run the weather update task."""
        try:
            logger.info("Running scheduled weather update")
            self.weather_service.update_weather_data()
        except Exception as e:
            logger.error(f"Error in weather update: {e}")