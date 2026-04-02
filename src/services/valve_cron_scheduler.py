"""
Valve Cron Scheduler for Raspberry Pi Irrigation System
This service handles scheduling valve activations based on cron expressions using APScheduler.
"""
from apscheduler.schedulers.background import BackgroundScheduler
import logging
from datetime import datetime
from typing import Dict, Any
import time

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ValveCronScheduler:
    """Scheduler for running valve cron schedules using APScheduler."""
    
    def __init__(self):
        """Initialize the valve cron scheduler."""
        self.scheduler = BackgroundScheduler()
        self.is_running = False
        self.valve_cron_jobs = {}  # Store job IDs for each valve
        self.db = None  # Database instance will be set later
        self.main_service = None  # Main service instance will be set later
        self._setup_scheduler()
    
    def _setup_scheduler(self):
        """Setup the scheduler with basic configuration."""
        # Configure the scheduler with a more robust configuration
        self.scheduler.configure(
            job_defaults={
                'coalesce': True,  # Run missed jobs once
                'max_instances': 1,     # Only one instance of each job at a time
                'misfire_grace_time': 30  # Allow 30 seconds grace for missed jobs
            }
        )
    
    def start(self, db, main_service):
        """Start the scheduler with database and main service instances."""
        if not self.is_running:
            # Double-check that scheduler is not already started
            try:
                # Check if scheduler is already running
                if hasattr(self.scheduler, 'running') and self.scheduler.running:
                    logger.info("Scheduler already running")
                    return
            except Exception:
                # If we can't check, proceed with starting
                pass
    	
            self.db = db
            self.main_service = main_service
            self.is_running = True
            self._load_existing_crons()
            # Additional safeguard - make sure we're not in a shutdown state
            try:
                self.scheduler.start()
                logger.info("Valve cron scheduler started with APScheduler")
            except Exception as e:
                # If we get an error during start, make sure we don't leave the state inconsistent
                self.is_running = False
                logger.error(f"Failed to start scheduler: {e}")
                raise
        else:
            logger.info("Valve cron scheduler already running")
    
    def stop(self):
        """Stop the scheduler."""
        if self.is_running:
            try:
                # Remove all jobs first
                self.scheduler.remove_all_jobs()
                # Shutdown the scheduler with wait=True to ensure all jobs are completed
                self.scheduler.shutdown(wait=True)
                self.is_running = False
                logger.info("Valve cron scheduler stopped")
            except Exception as e:
                logger.error(f"Error stopping scheduler: {e}")
                # Even if there's an error, we should still set is_running to False
                self.is_running = False
                # Additional safeguard - if we get a shutdown error, make sure we don't leave
                # the scheduler in a bad state
                try:
                    # Try to force shutdown if needed
                    self.scheduler.shutdown(wait=False)
                except:
                    # If we can't shutdown cleanly, that's okay - we've already set is_running to False
                    pass
    
    def _load_existing_crons(self):
        """Load existing cron schedules from database."""
        try:
            if self.db is None:
                logger.warning("Database not initialized, cannot load existing crons")
                return
    
            # Get all enabled valve cron schedules
            crons = self.db.get_all_valve_crons()
            logger.info(f"Loading {len(crons)} existing valve cron schedules")
       
            if not crons:
                logger.info("No cron schedules found in database")
            else:
                for cron in crons:
                    if cron['enabled'] and cron['cron_expression']:
                        self._add_cron_job(cron)
                    else:
                        logger.info(f"Skipping disabled cron for valve {cron['valve_id']}")
       
        except Exception as e:
            logger.error(f"Error loading existing crons: {e}")
            import traceback
            traceback.print_exc()
    
    def _add_cron_job(self, cron_data: Dict[str, Any]):
        """Add a cron job for a valve."""
        try:
            # Check if scheduler is still running before adding new jobs
            if not self.is_running:
                logger.warning("Scheduler not running, cannot add new cron job")
                return
    	
            valve_id = cron_data['valve_id']
            cron_expression = cron_data['cron_expression']
            duration = cron_data['duration'] if cron_data['duration'] is not None else 60  # Default 60 seconds if not set
            job_id = f"valve_{valve_id}_cron"
        
            # Remove existing job if it exists - handle the case where job doesn't exist
            if job_id in self.valve_cron_jobs:
                try:
                    self.scheduler.remove_job(job_id)
                    logger.info(f"Removed existing job for valve {valve_id} before adding new one")
                except Exception as e:
                    logger.warning(f"Could not remove existing job {job_id}: {e}")
                    # Continue anyway, as we're about to add a new one anyway
     
            # Add new job with cron expression
            # APScheduler expects cron parameters directly
            cron_params = self._parse_cron_expression(cron_expression)
            # Double-check that scheduler is still running before adding job
            if not self.is_running:
                logger.warning("Scheduler not running, skipping job addition for valve {valve_id}")
                return
     			
            # Additional safeguard - try to catch any shutdown state issues
            try:
                self.scheduler.add_job(
                    func=self._run_valve_activation,
                    trigger="cron",
                    id=job_id,
                    kwargs={
                        'valve_id': valve_id,
                        'duration': duration
                    },
                    **cron_params
                )
            except Exception as e:
                # If we get an error during job addition, check if it's related to shutdown
                error_str = str(e)
                if "shutdown" in error_str.lower() or "cannot schedule new futures" in error_str:
                    logger.warning(f"Job addition skipped due to scheduler shutdown: {e}")
                    return
                else:
                    raise  # Re-raise if it's not a shutdown-related error
        
            self.valve_cron_jobs[job_id] = {
                'valve_id': valve_id,
                'cron_expression': cron_expression,
                'duration': duration
            }
        
            logger.info(f"Added cron job for valve {valve_id}: {cron_expression} with duration {duration}s")
        
        except Exception as e:
            logger.error(f"Error adding cron job for valve {cron_data['valve_id']}: {e}")
            # Even if there's an error, we should still update the database with the last run date
            # This ensures that the system can continue working properly
            try:
                # Set last_run to current time to prevent infinite errors
                current_time = datetime.now().isoformat()
                self._update_cron_run_dates(valve_id, current_time, None)
            except Exception as e2:
                logger.error(f"Error updating run dates after cron job error: {e2}")
    
    def _parse_cron_expression(self, cron_expression: str) -> dict:
        """
        Parse a cron expression and return parameters for APScheduler.
        
        Supports standard cron expressions (minute, hour, day, month, day_of_week).
        """
        try:
            # Split the cron expression into its components
            parts = cron_expression.strip().split()
       
            # Standard cron format: minute hour day month day_of_week
            # If we have 5 parts, it's standard cron
            if len(parts) == 5:
                minute, hour, day, month, day_of_week = parts
    
                # Return parameters for APScheduler
                return {
                    'minute': minute,
                    'hour': hour,
                    'day': day,
                    'month': month,
                    'day_of_week': day_of_week
                }
            else:
                # If it's not standard cron, we can't parse it properly
                # Return empty dict so APScheduler can handle it
                logger.warning(f"Non-standard cron expression: {cron_expression}")
                return {}
        except Exception as e:
            logger.error(f"Error parsing cron expression '{cron_expression}': {e}")
            return {}
    
    def _run_valve_activation(self, valve_id: int, duration: int):
        """Run the valve activation for a specific valve with duration."""
        # Additional safeguard - check if scheduler is in a shutdown state
        try:
            # Check if scheduler is still running before proceeding
            if not self.is_running:
                logger.warning(f"Scheduler not running, skipping valve activation for valve {valve_id}")
                return
    
            logger.info(f"Running scheduled activation for valve {valve_id} for {duration} seconds")
    
            # Get current time for run tracking
            current_time = datetime.now()
            last_run = current_time.isoformat()
    
            # Update last run date in database before execution
            self._update_cron_run_dates(valve_id, last_run, None)
    
            if self.main_service is None:
                logger.error("Main service not initialized, cannot activate valve")
                return
    
            # Activate the valve with specified duration
            success = self.main_service.activate_valve(valve_id, duration)
    
            if success:
                logger.info(f"Successfully activated valve {valve_id} for {duration} seconds")
                # Calculate next run date based on cron expression
                next_run = self._calculate_next_run_date(valve_id, last_run)
                self._update_cron_run_dates(valve_id, last_run, next_run)
            else:
                logger.error(f"Failed to activate valve {valve_id} for {duration} seconds")
                # Even if activation failed, calculate next run date
                next_run = self._calculate_next_run_date(valve_id, last_run)
                self._update_cron_run_dates(valve_id, last_run, next_run)
    
        except Exception as e:
            # This is a critical fix - we need to catch the specific RuntimeError about shutdown
            # The error might be coming from the APScheduler itself, not our code
            error_str = str(e)
            if "cannot schedule new futures after shutdown" in error_str or "shutdown" in error_str.lower():
                logger.warning(f"Job execution skipped due to scheduler shutdown: {e}")
                return
            else:
                logger.error(f"Error in valve activation: {e}")
                # Even if there's an error, update the last run date to prevent infinite loops
                try:
                    last_run = datetime.now().isoformat()
                    self._update_cron_run_dates(valve_id, last_run, None)
                except Exception as e2:
                    logger.error(f"Error updating run dates after activation error: {e2}")
                    # If we can't even update the database, we should still try to avoid infinite loops
                    # by checking if the scheduler is still running
                    if not self.is_running:
                        logger.warning("Scheduler is not running, skipping further processing")
                        return
    
    def add_valve_cron(self, valve_id: int, cron_expression: str, duration: int = 60, enabled: bool = True):
        """Add a new cron schedule for a valve."""
        try:
            # Check if scheduler is still running before adding new jobs
            if not self.is_running:
                logger.warning("Scheduler not running, cannot add new cron schedule")
                return False

            # First, save to database
            success = self.db.update_valve_cron(valve_id, cron_expression, enabled)
            if not success:
                logger.error(f"Failed to save cron schedule for valve {valve_id} in database")
                return False

            # Update the duration in database if provided
            if duration is not None:
                self.db.update_valve_cron_duration(valve_id, duration)

            # If we're updating an existing cron, disable the current job first
            job_id = f"valve_{valve_id}_cron"
            if job_id in self.valve_cron_jobs:
                # Remove existing job
                try:
                    self.scheduler.remove_job(job_id)
                    logger.info(f"Removed existing cron job for valve {valve_id} before adding new one")
                    # Remove from tracking
                    del self.valve_cron_jobs[job_id]
                except Exception as e:
                    logger.warning(f"Could not remove existing job {job_id}: {e}")
                    # Continue anyway, as we're about to add a new one anyway

            # Add to scheduler if enabled and valid
            if enabled and cron_expression:
                cron_data = {
                    'valve_id': valve_id,
                    'cron_expression': cron_expression,
                    'duration': duration,
                    'enabled': enabled
                }
                self._add_cron_job(cron_data)
                logger.info(f"Added new cron schedule for valve {valve_id}: {cron_expression} with duration {duration}s")
                return True
            else:
                logger.info(f"Skipped adding cron schedule for valve {valve_id} (disabled or invalid)")
                return True  # Not an error, just not added

        except Exception as e:
            logger.error(f"Error adding valve cron schedule: {e}")
            return False
    
    def remove_valve_cron(self, valve_id: int):
        """Remove a cron schedule for a valve."""
        try:
            # Remove from scheduler
            job_id = f"valve_{valve_id}_cron"
            if job_id in self.valve_cron_jobs:
                try:
                    self.scheduler.remove_job(job_id)
                    del self.valve_cron_jobs[job_id]
                    logger.info(f"Removed cron job for valve {valve_id} from scheduler")
                except Exception as e:
                    logger.warning(f"Could not remove job {job_id}: {e}")
                    # Continue anyway, as we're removing it anyway
   
            # Remove from database (set enabled to False)
            success = self.db.update_valve_cron(valve_id, "", False)
            if success:
                logger.info(f"Disabled cron schedule for valve {valve_id} in database")
            else:
                logger.warning(f"Failed to disable cron schedule for valve {valve_id} in database")
   
            return True
        except Exception as e:
            logger.error(f"Error removing valve cron schedule: {e}")
            return False
    
    def _calculate_next_run_date(self, valve_id: int, last_run: str) -> str:
        """Calculate the next run date based on the cron expression for a valve."""
        try:
            # Get the cron expression for this valve
            cron_data = self.db.get_valve_cron(valve_id)
            if not cron_data or not cron_data['cron_expression']:
                logger.warning(f"No cron expression found for valve {valve_id}")
                return None
     
            cron_expression = cron_data['cron_expression']
     
            # Import required modules for cron parsing
            from apscheduler.triggers.cron import CronTrigger
            from datetime import datetime
     
            # Create a CronTrigger from the cron expression
            trigger = CronTrigger.from_crontab(cron_expression)
     
            # Get the last run time (convert from ISO format)
            last_run_time = datetime.fromisoformat(last_run.replace('Z', '+00:00'))
     
            # Calculate the next run time after the last run
            # The correct signature is get_next_fire_time(previous_fire_time, now)
            next_run_time = trigger.get_next_fire_time(last_run_time, last_run_time)
     
            if next_run_time:
                return next_run_time.isoformat()
            else:
                logger.warning(f"Could not calculate next run time for valve {valve_id}")
                return None
        except Exception as e:
            logger.error(f"Error calculating next run date for valve {valve_id}: {e}")
            return None

    def _update_cron_run_dates(self, valve_id: int, last_run: str, next_run: str):
        """Update last run and next run dates in database."""
        try:
            # Update the database with last run and next run dates
            conn = self.db.get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE valve_cron
                SET last_run = ?, next_run = ?
                WHERE valve_id = ?
            ''', (last_run, next_run, valve_id))
            conn.commit()
            conn.close()
            logger.info(f"Updated run dates for valve {valve_id}: last_run={last_run}, next_run={next_run}")
        except Exception as e:
            logger.error(f"Error updating run dates for valve {valve_id}: {e}")