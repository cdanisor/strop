"""
GPIO Control Service for Raspberry Pi Irrigation System
This service handles relay operations for controlling solenoid valves.

Safety rules:
  * a valve is never left open without a timer: missing/zero/negative
    durations fall back to MAX_DURATION_SECONDS and longer ones are capped;
  * activate/deactivate are serialized with a lock (API threads, the
    scheduler thread and timer threads all call in here);
  * activating an already open valve is refused instead of silently
    restarting its timer and leaving an orphan "Opened" log.
"""

import datetime
import logging
import threading
from typing import Dict, Any, Optional

from src.database import Database

logger = logging.getLogger(__name__)

MAX_DURATION_SECONDS = 3600  # 1 hour hard limit for any valve opening
VALVE_IDS = (1, 2)


class GPIOControlService:
    """Service for controlling GPIO pins and relays for irrigation valves."""

    def __init__(self, config: Dict[str, Any], db: Optional[Database] = None):
        self.config = config
        self.valve1_pin = config.get('gpio', {}).get('valve1_pin', 23)
        self.valve2_pin = config.get('gpio', {}).get('valve2_pin', 24)
        self.is_initialized = False
        self.is_simulation_mode = False
        self._gpio = None

        self.valve_states = {valve_id: False for valve_id in VALVE_IDS}
        self.active_timers: Dict[int, threading.Timer] = {}
        self.valve_start_times: Dict[int, datetime.datetime] = {}
        self.open_log_ids: Dict[int, Optional[int]] = {}
        self._lock = threading.RLock()

        self.db = db if db is not None else Database()
        self._setup_gpio()

    def _pin(self, valve_id: int) -> int:
        return self.valve1_pin if valve_id == 1 else self.valve2_pin

    def _setup_gpio(self) -> None:
        """Setup GPIO pins for output or use simulation mode."""
        try:
            import RPi.GPIO as GPIO
            GPIO.setwarnings(False)
            GPIO.setmode(GPIO.BCM)
            for pin in (self.valve1_pin, self.valve2_pin):
                GPIO.setup(pin, GPIO.OUT)
                GPIO.output(pin, GPIO.LOW)
            self._gpio = GPIO
            self.is_initialized = True
            logger.info("GPIO pins initialized successfully")
        except ImportError:
            self.is_simulation_mode = True
            self.is_initialized = True
            logger.info("Running in simulation mode (no GPIO hardware)")

    def _write(self, valve_id: int, on: bool) -> None:
        if self.is_simulation_mode:
            logger.info(f"SIMULATION: {'Activating' if on else 'Deactivating'} valve {valve_id}")
        else:
            self._gpio.output(self._pin(valve_id), self._gpio.HIGH if on else self._gpio.LOW)

    @staticmethod
    def normalize_duration(duration: Optional[int]) -> int:
        """Clamp a requested duration to 1..MAX_DURATION_SECONDS (None/<=0 -> max)."""
        try:
            duration = int(duration) if duration is not None else 0
        except (TypeError, ValueError):
            duration = 0
        if duration <= 0 or duration > MAX_DURATION_SECONDS:
            return MAX_DURATION_SECONDS
        return duration

    def activate_valve(self, valve_id: int, duration: Optional[int] = None,
                       meta: Optional[Dict[str, Any]] = None) -> bool:
        """
        Open a valve; it is always closed again automatically after `duration`
        seconds (capped at MAX_DURATION_SECONDS).
        """
        if not self.is_initialized:
            logger.error("GPIO not initialized")
            return False
        if valve_id not in VALVE_IDS:
            logger.error(f"Invalid valve ID: {valve_id}")
            return False

        duration = self.normalize_duration(duration)
        with self._lock:
            if self.valve_states[valve_id]:
                logger.warning(f"Valve {valve_id} is already open, activation refused")
                return False
            try:
                self._write(valve_id, True)
            except Exception as e:
                logger.error(f"Failed to activate valve {valve_id}: {e}")
                return False

            self.valve_states[valve_id] = True
            start_time = datetime.datetime.now()
            self.valve_start_times[valve_id] = start_time
            self.open_log_ids[valve_id] = self.db.insert_valve_log(valve_id, 'Opened', None, start_time, meta)

            timer = threading.Timer(duration, self._on_timer, [valve_id])
            timer.daemon = True
            self.active_timers[valve_id] = timer
            timer.start()
            logger.info(f"Valve {valve_id} activated for {duration} seconds")
            return True

    def _on_timer(self, valve_id: int) -> None:
        """Timer callback; ignores timers that were cancelled/replaced meanwhile."""
        with self._lock:
            if self.active_timers.get(valve_id) is not threading.current_thread():
                return
            self.deactivate_valve(valve_id, manual=False)

    def deactivate_valve(self, valve_id: int, manual: bool = False, status: Optional[str] = None) -> bool:
        """Close a valve and finish its log entry."""
        if not self.is_initialized:
            logger.error("GPIO not initialized")
            return False
        if valve_id not in VALVE_IDS:
            logger.error(f"Invalid valve ID: {valve_id}")
            return False

        with self._lock:
            timer = self.active_timers.pop(valve_id, None)
            if timer is not None and timer is not threading.current_thread():
                timer.cancel()
            try:
                self._write(valve_id, False)
            except Exception as e:
                logger.error(f"Failed to deactivate valve {valve_id}: {e}")
                return False

            was_open = self.valve_states[valve_id]
            self.valve_states[valve_id] = False
            logger.info(f"Valve {valve_id} deactivated")

            if not was_open:
                return True

            if status is None:
                status = 'Manually Stopped' if manual else 'Finished'
            duration = None
            start_time = self.valve_start_times.pop(valve_id, None)
            if start_time is not None:
                duration = int((datetime.datetime.now() - start_time).total_seconds())

            log_id = self.open_log_ids.pop(valve_id, None)
            if not log_id or not self.db.update_valve_log_status(log_id, duration, status):
                self.db.insert_valve_log(valve_id, status, duration, start_time)
            return True

    def get_valve_status(self, valve_id: int) -> bool:
        if valve_id not in VALVE_IDS:
            logger.error(f"Invalid valve ID: {valve_id}")
            return False
        return self.valve_states[valve_id]

    def get_all_valve_status(self) -> Dict[int, bool]:
        return self.valve_states.copy()

    def get_valve_details(self, valve_id: int) -> Dict[str, Any]:
        """Open state plus start time, planned duration and remaining seconds."""
        with self._lock:
            is_open = self.valve_states.get(valve_id, False)
            details = {'open': is_open, 'started_at': None, 'duration': None, 'remaining': None}
            if is_open:
                start = self.valve_start_times.get(valve_id)
                timer = self.active_timers.get(valve_id)
                if start is not None:
                    details['started_at'] = start.isoformat()
                if timer is not None:
                    details['duration'] = int(timer.interval)
                    if start is not None:
                        elapsed = (datetime.datetime.now() - start).total_seconds()
                        details['remaining'] = max(0, int(round(timer.interval - elapsed)))
            return details

    def cleanup(self) -> None:
        """Close all valves (finishing their logs) and release GPIO."""
        if not self.is_initialized:
            return
        with self._lock:
            for valve_id in VALVE_IDS:
                if self.valve_states.get(valve_id):
                    try:
                        self.deactivate_valve(valve_id, status='Terminated')
                    except Exception as e:
                        logger.error(f"Error closing valve {valve_id} during cleanup: {e}")
            for timer in self.active_timers.values():
                timer.cancel()
            self.active_timers.clear()

            if not self.is_simulation_mode:
                try:
                    for pin in (self.valve1_pin, self.valve2_pin):
                        self._gpio.output(pin, self._gpio.LOW)
                    self._gpio.cleanup()
                    logger.info("GPIO cleanup completed")
                except Exception as e:
                    logger.error(f"Error during GPIO cleanup: {e}")
            self.is_initialized = False

    def __del__(self):
        try:
            self.cleanup()
        except Exception:
            pass
