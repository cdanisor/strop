"""
Cron Scheduler for Raspberry Pi Irrigation System
This service handles scheduling weather updates every 3 hours using APScheduler.
It also reports (once) when the weather data has not been refreshed for a long
time, because the watering adjustment then works on old forecasts.
"""
from apscheduler.schedulers.background import BackgroundScheduler
import logging
import time
from src.services.weather.weather_service import WeatherService

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

UPDATE_INTERVAL_SECONDS = 10800   # 3 hours
STALE_AFTER_SECONDS = 12 * 3600   # notify when no successful update for 12 hours


class CronScheduler:
    """Scheduler for running periodic tasks using APScheduler."""

    def __init__(self, notifier=None):
        """Initialize the cron scheduler."""
        self.weather_service = WeatherService()
        self.scheduler = BackgroundScheduler()
        self.is_running = False
        self.notifier = notifier
        self.last_success = time.time()   # grace period starts at start-up
        self.stale_notified = False

    def start(self):
        """Start the scheduler."""
        if not self.is_running:
            self.scheduler.add_job(
                func=self._run_weather_update,
                trigger="interval",
                seconds=UPDATE_INTERVAL_SECONDS,
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

    def run_now(self) -> bool:
        """Run one weather update immediately (used at start-up)."""
        return self._run_weather_update()

    def _run_weather_update(self) -> bool:
        """Run the weather update task and track data freshness."""
        try:
            logger.info("Running scheduled weather update")
            ok = bool(self.weather_service.update_weather_data())
        except Exception as e:
            logger.error(f"Error in weather update: {e}")
            ok = False
        self._track(ok)
        return ok

    def _track(self, ok: bool) -> None:
        if ok:
            self.last_success = time.time()
            self.stale_notified = False
            return
        age = time.time() - self.last_success
        if age >= STALE_AFTER_SECONDS and not self.stale_notified:
            hours = int(age // 3600)
            logger.error("Weather data not updated for %d hours", hours)
            if self.notifier is not None:
                self.notifier.emit('weather_stale', hours=hours)
            self.stale_notified = True
