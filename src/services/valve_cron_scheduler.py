"""
Valve Cron Scheduler for Raspberry Pi Irrigation System
This service handles scheduling valve activations based on cron expressions using APScheduler.

A zone (valve) can have several schedules; each one is a row of the
valve_cron table and gets its own job. The database is the single source of
truth:
  * reload_valve()/reload_all() sync the in-memory jobs with the DB, removing
    jobs for schedules that are disabled, deleted or cleared;
  * every scheduled run re-reads its schedule from the DB right before
    opening a valve, so a disabled schedule never opens a valve even if a
    stale job were somehow left behind.
"""
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.base import JobLookupError
import logging
import threading
from datetime import datetime
from typing import Any, Dict, Optional

from src.services.cron_utils import build_trigger, find_overlap, next_run_times, CronValidationError
from src.services.watering_adjustment import WateringAdjuster, encode_note

logger = logging.getLogger(__name__)

VALVE_IDS = (1, 2)
DEFAULT_DURATION = 60  # seconds, used when a schedule has no duration stored
JOB_PREFIX = 'schedule_'


def find_schedule_conflict(db, valve_id: int, cron_expression: str, duration: int,
                           exclude_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
    """
    Check a schedule against itself and the zone's other ENABLED schedules.

    Returns None, or {'schedule_id': other id or None (overlaps itself),
    'cron_expression', 'duration', 'weekday': 0-6 (Monday=0), 'time': 'HH:MM'}.
    """
    duration = int(duration or DEFAULT_DURATION)

    def result(other, at):
        return {'schedule_id': other.get('id') if other else None,
                'cron_expression': other.get('cron_expression') if other else cron_expression,
                'duration': (other.get('duration') or DEFAULT_DURATION) if other else duration,
                'weekday': at.weekday(), 'time': at.strftime('%H:%M')}

    at = find_overlap(cron_expression, duration)
    if at:
        return result(None, at)
    for other in db.list_schedules(valve_id):
        if other['id'] == exclude_id or not other['enabled']:
            continue
        try:
            at = find_overlap(cron_expression, duration, other['cron_expression'],
                              other.get('duration') or DEFAULT_DURATION)
        except CronValidationError:
            continue  # an unreadable stored schedule cannot be compared
        if at:
            return result(other, at)
    return None


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
    def _job_id(schedule_id: int) -> str:
        return f"{JOB_PREFIX}{schedule_id}"

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
        """Sync the jobs of all valves with the database."""
        for valve_id in VALVE_IDS:
            self.reload_valve(valve_id)

    # Backwards compatible name
    _load_existing_crons = reload_all

    def _jobs_of_valve(self, valve_id: int):
        return [j for j in self.scheduler.get_jobs()
                if j.id.startswith(JOB_PREFIX) and j.kwargs.get('valve_id') == valve_id]

    def reload_valve(self, valve_id: int) -> bool:
        """
        Sync the jobs of one valve with its schedules in the database.

        Returns True if at least one active job exists for the valve afterwards.
        """
        with self._lock:
            if not self.is_running or self.db is None:
                logger.warning("Scheduler not running, cannot reload valve %s", valve_id)
                return False

            for job in self._jobs_of_valve(valve_id):
                self._remove_job(job.id)

            active = 0
            for schedule in self.db.list_schedules(valve_id):
                sid = schedule['id']
                if not schedule.get('enabled'):
                    self._update_next_run(sid, None)
                    continue
                try:
                    trigger = build_trigger(schedule['cron_expression'])
                except CronValidationError as e:
                    logger.error("Schedule %s (valve %s): invalid cron '%s' not scheduled: %s",
                                 sid, valve_id, schedule['cron_expression'], e)
                    self._update_next_run(sid, None)
                    continue
                job = self.scheduler.add_job(
                    func=self._run_valve_activation,
                    trigger=trigger,
                    id=self._job_id(sid),
                    kwargs={'valve_id': valve_id, 'schedule_id': sid},
                    replace_existing=True,
                )
                next_run = job.next_run_time.isoformat() if job.next_run_time else None
                self._update_next_run(sid, next_run)
                active += 1
                logger.info("Valve %s: schedule %s '%s' (next run %s)",
                            valve_id, sid, schedule['cron_expression'], next_run)
            if not active:
                logger.info("Valve %s: no enabled schedule, no job scheduled", valve_id)
            return active > 0

    def _remove_job(self, job_id: str):
        try:
            self.scheduler.remove_job(job_id)
        except JobLookupError:
            pass

    def has_job(self, valve_id: int) -> bool:
        return bool(self._jobs_of_valve(valve_id))

    # ------------------------------------------------------------------ API helpers
    def add_valve_cron(self, valve_id: int, cron_expression: str, duration: int = DEFAULT_DURATION,
                       enabled: bool = True) -> bool:
        """Validate, save and schedule the zone's first schedule (legacy single-schedule API)."""
        build_trigger(cron_expression)  # raises CronValidationError if invalid
        if not self.db.update_valve_cron(valve_id, cron_expression, enabled):
            return False
        if duration is not None:
            self.db.update_valve_cron_duration(valve_id, duration)
        self.reload_valve(valve_id)
        return True

    def remove_valve_cron(self, valve_id: int) -> bool:
        """Delete all schedules of a valve."""
        success = self.db.update_valve_cron(valve_id, "", False)
        self.reload_valve(valve_id)
        return success

    # ------------------------------------------------------------------ execution
    def _run_valve_activation(self, valve_id: int, schedule_id: Optional[int] = None):
        """Scheduled job: open the valve for the duration stored in the schedule."""
        if not self.is_running or self.main_service is None:
            logger.warning("Scheduler not running, skipping valve %s activation", valve_id)
            return
        try:
            cron = (self.db.get_schedule(schedule_id) if schedule_id is not None
                    else self.db.get_valve_cron(valve_id))
            if not cron or not cron.get('enabled') or not cron.get('cron_expression') \
                    or cron.get('valve_id') != valve_id:
                # Safety net: never open a valve for a disabled or deleted schedule
                logger.warning("Valve %s: schedule %s is disabled or gone, skipping", valve_id, schedule_id)
                if schedule_id is not None:
                    self._remove_job(self._job_id(schedule_id))
                    self._update_next_run(schedule_id, None)
                return
            schedule_id = cron['id']

            base_duration = cron.get('duration') or DEFAULT_DURATION
            now = datetime.now()
            last_run = now.isoformat()

            # Weather-based reduction of the programmed time
            plan = self.adjuster.plan(base_duration, now.date())
            meta = {
                'base_duration': base_duration,
                'adjust_percent': plan['percent'],
                'adjust_note': encode_note(plan),
            }

            if self.main_service.get_valve_status(valve_id):
                logger.warning("Valve %s already open, skipping scheduled activation (schedule %s)",
                               valve_id, schedule_id)
            elif plan['skip']:
                logger.info("Valve %s: scheduled run skipped (%s)", valve_id, plan['reason'])
                self.db.insert_valve_log(valve_id, 'Skipped', 0, now, meta)
                notifier = getattr(self.main_service, 'notifier', None)
                if notifier is not None:
                    notifier.emit('run_skipped', valve_id=valve_id, schedule_id=schedule_id,
                                  base_duration=base_duration,
                                  reason_key=plan.get('reason_key'), reason_args=plan.get('reason_args'),
                                  reason=plan.get('reason'))
            else:
                logger.info("Running schedule %s for valve %s: %ss of %ss (%s%%, %s)",
                            schedule_id, valve_id, plan['duration'], base_duration, plan['percent'],
                            plan['reason'])
                if not self.main_service.activate_valve(valve_id, plan['duration'], meta):
                    logger.error("Failed to activate valve %s", valve_id)

            self._update_cron_run_dates(schedule_id, last_run, self._calculate_next_run_date(schedule_id))
        except Exception as e:
            logger.exception("Error in scheduled activation of valve %s: %s", valve_id, e)

    def _calculate_next_run_date(self, schedule_id: int) -> Optional[str]:
        """Next fire time of the schedule's job, as ISO string."""
        job = self.scheduler.get_job(self._job_id(schedule_id))
        if job is not None and job.next_run_time:
            return job.next_run_time.isoformat()
        cron = self.db.get_schedule(schedule_id)
        if cron and cron.get('enabled') and cron.get('cron_expression'):
            try:
                runs = next_run_times(cron['cron_expression'], 1)
                return runs[0].isoformat() if runs else None
            except CronValidationError:
                return None
        return None

    # ------------------------------------------------------------------ DB helpers
    def _update_cron_run_dates(self, schedule_id: int, last_run: Optional[str], next_run: Optional[str]):
        try:
            conn = self.db.get_connection()
            conn.execute('UPDATE valve_cron SET last_run = ?, next_run = ? WHERE id = ?',
                         (last_run, next_run, schedule_id))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Error updating run dates for schedule {schedule_id}: {e}")

    def _update_next_run(self, schedule_id: int, next_run: Optional[str]):
        try:
            conn = self.db.get_connection()
            conn.execute('UPDATE valve_cron SET next_run = ? WHERE id = ?', (next_run, schedule_id))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Error updating next run for schedule {schedule_id}: {e}")
