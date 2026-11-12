"""
Valve Cron Scheduler for Raspberry Pi Irrigation System
This service handles scheduling valve activations based on cron expressions using APScheduler.

The database is the single source of truth:
  * reload_valve()/reload_all() sync the in-memory jobs with the DB, removing
    jobs for schedules that are disabled or cleared;
  * every scheduled run re-reads the schedule from the DB right before opening
    a valve, so a disabled schedule never opens a valve even if a stale job
    were somehow left behind.
"""
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.base import JobLookupError
import logging
import threading
from datetime import datetime
from typing import Optional

from src.services.cron_utils import build_trigger, next_run_times, CronValidationError
from src.services.watering_adjustment import WateringAdjuster

logger = logging.getLogger(__name__)

VALVE_IDS = (1, 2)
DEFAULT_DURATION = 60  # seconds, used when a schedule has no duration stored


class ValveCronScheduler:
    """Scheduler for running valve cron schedules using APScheduler."""

    def __init__(self):
        self.scheduler = BackgroundScheduler(job_defaults={
            'coalesce': True,          # Run missed jobs once
            'max_instances': 1,        # Only one instance of each job at a time
            'misfire_grace_time': 60,  # Allow 60 seconds grace for missed jobs
        })
        self.is_running = False
        self.db = None
        self.main_service = None
        self._lock = threading.RLock()

    def _adjustment_config(self):
        config_service = getattr(self.main_service, 'config_service', None)
        if config_service is None:
            return {}
        return config_service.get('watering_adjustment', {}) or {}

    @staticmethod
    def _job_id(valve_id: int) -> str:
        return f"valve_{valve_id}_cron"

    # ------------------------------------------------------------------ lifecycle
    def start(self, db, main_service):
        """Start the scheduler with database and main service instances."""
        with self._lock:
            if self.is_running:
                logger.info("Valve cron scheduler already running")
                return
            self.db = db
            self.main_service = main_service
            self.adjuster = WateringAdjuster(db, self._adjustment_config())
            self.scheduler.start()
            self.is_running = True
            self.reload_all()
            logger.info("Valve cron scheduler started")

    def stop(self):
        """Stop the scheduler."""
        with self._lock:
            if not self.is_running:
                return
            self.is_running = False
            try:
                self.scheduler.remove_all_jobs()
                self.scheduler.shutdown(wait=False)
            except Exception as e:
                logger.error(f"Error stopping valve scheduler: {e}")
            logger.info("Valve cron scheduler stopped")

    # ------------------------------------------------------------------ syncing
    def reload_all(self):
        """Sync jobs for all valves with the database."""
        for valve_id in VALVE_IDS:
            self.reload_valve(valve_id)

    # Backwards compatible name
    _load_existing_crons = reload_all

    def reload_valve(self, valve_id: int) -> bool:
        """
        Sync the job of one valve with its schedule in the database.

        Returns True if an active job exists for the valve afterwards.
        """
        with self._lock:
            if not self.is_running or self.db is None:
                logger.warning("Scheduler not running, cannot reload valve %s", valve_id)
                return False

            self._remove_job(valve_id)

            cron = self.db.get_valve_cron(valve_id)
            if not cron or not cron.get('enabled') or not cron.get('cron_expression'):
                logger.info("Valve %s: schedule disabled or empty, no job scheduled", valve_id)
                self._update_next_run(valve_id, None)
                return False

            try:
                trigger = build_trigger(cron['cron_expression'])
            except CronValidationError as e:
                logger.error("Valve %s: invalid cron '%s' not scheduled: %s",
                             valve_id, cron['cron_expression'], e)
                self._update_next_run(valve_id, None)
                return False

            job = self.scheduler.add_job(
                func=self._run_valve_activation,
                trigger=trigger,
                id=self._job_id(valve_id),
                kwargs={'valve_id': valve_id},
                replace_existing=True,
            )
            next_run = job.next_run_time.isoformat() if job.next_run_time else None
            self._update_next_run(valve_id, next_run)
            logger.info("Valve %s: scheduled '%s' (next run %s)",
                        valve_id, cron['cron_expression'], next_run)
            return True

    def _remove_job(self, valve_id: int):
        try:
            self.scheduler.remove_job(self._job_id(valve_id))
            logger.info("Valve %s: removed existing job", valve_id)
        except JobLookupError:
            pass

    def has_job(self, valve_id: int) -> bool:
        return self.scheduler.get_job(self._job_id(valve_id)) is not None

    # ------------------------------------------------------------------ API helpers
    def add_valve_cron(self, valve_id: int, cron_expression: str, duration: int = DEFAULT_DURATION,
                       enabled: bool = True) -> bool:
        """Validate, save and schedule a cron for a valve."""
        build_trigger(cron_expression)  # raises CronValidationError if invalid
        if not self.db.update_valve_cron(valve_id, cron_expression, enabled):
            return False
        if duration is not None:
            self.db.update_valve_cron_duration(valve_id, duration)
        self.reload_valve(valve_id)
        return True

    def remove_valve_cron(self, valve_id: int) -> bool:
        """Clear and disable the cron schedule of a valve."""
        success = self.db.update_valve_cron(valve_id, "", False)
        self.reload_valve(valve_id)
        return success

    # ------------------------------------------------------------------ execution
    def _run_valve_activation(self, valve_id: int):
        """Scheduled job: open the valve for the duration stored in the database."""
        if not self.is_running or self.main_service is None:
            logger.warning("Scheduler not running, skipping valve %s activation", valve_id)
            return
        try:
            cron = self.db.get_valve_cron(valve_id)
            if not cron or not cron.get('enabled') or not cron.get('cron_expression'):
                # Safety net: never open a valve for a disabled schedule
                logger.warning("Valve %s: schedule is disabled in DB, skipping and removing job", valve_id)
                self._remove_job(valve_id)
                self._update_next_run(valve_id, None)
                return

            base_duration = cron.get('duration') or DEFAULT_DURATION
            now = datetime.now()
            last_run = now.isoformat()

            # Weather-based reduction of the programmed time
            plan = self.adjuster.plan(base_duration, now.date())
            meta = {
                'base_duration': base_duration,
                'adjust_percent': plan['percent'],
                'adjust_note': plan['reason'],
            }

            if self.main_service.get_valve_status(valve_id):
                logger.warning("Valve %s already open, skipping scheduled activation", valve_id)
            elif plan['skip']:
                logger.info("Valve %s: scheduled run skipped (%s)", valve_id, plan['reason'])
                self.db.insert_valve_log(valve_id, 'Skipped', 0, now, meta)
            else:
                logger.info("Running scheduled activation for valve %s: %ss of %ss (%s%%, %s)",
                            valve_id, plan['duration'], base_duration, plan['percent'], plan['reason'])
                if not self.main_service.activate_valve(valve_id, plan['duration'], meta):
                    logger.error("Failed to activate valve %s", valve_id)

            self._update_cron_run_dates(valve_id, last_run, self._calculate_next_run_date(valve_id))
        except Exception as e:
            logger.exception("Error in scheduled activation of valve %s: %s", valve_id, e)

    def _calculate_next_run_date(self, valve_id: int) -> Optional[str]:
        """Next fire time of the valve's job, as ISO string."""
        job = self.scheduler.get_job(self._job_id(valve_id))
        if job is not None and job.next_run_time:
            return job.next_run_time.isoformat()
        cron = self.db.get_valve_cron(valve_id)
        if cron and cron.get('enabled') and cron.get('cron_expression'):
            try:
                runs = next_run_times(cron['cron_expression'], 1)
                return runs[0].isoformat() if runs else None
            except CronValidationError:
                return None
        return None

    # ------------------------------------------------------------------ DB helpers
    def _update_cron_run_dates(self, valve_id: int, last_run: Optional[str], next_run: Optional[str]):
        try:
            conn = self.db.get_connection()
            conn.execute('UPDATE valve_cron SET last_run = ?, next_run = ? WHERE valve_id = ?',
                         (last_run, next_run, valve_id))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Error updating run dates for valve {valve_id}: {e}")

    def _update_next_run(self, valve_id: int, next_run: Optional[str]):
        try:
            conn = self.db.get_connection()
            conn.execute('UPDATE valve_cron SET next_run = ? WHERE valve_id = ?', (next_run, valve_id))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Error updating next run for valve {valve_id}: {e}")
