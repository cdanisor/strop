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
            self.db = db
            self.main_service = main_service
            self._load_existing_crons()
            self.scheduler.start()
            self.is_running = True
            logger.info("Valve cron scheduler started with APScheduler")
    
    def stop(self):
        """Stop the scheduler."""
        if self.is_running:
            try:
                # Remove all jobs
                self.scheduler.remove_all_jobs()
                self.scheduler.shutdown(wait=True)
                self.is_running = False
                logger.info("Valve cron scheduler stopped")
            except Exception as e:
                logger.error(f"Error stopping scheduler: {e}")
    
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
            valve_id = cron_data['valve_id']
            cron_expression = cron_data['cron_expression']
            duration = cron_data['duration'] if cron_data['duration'] is not None else 60  # Default 60 seconds if not set
            job_id = f"valve_{valve_id}_cron"
            
            # Remove existing job if it exists
            if job_id in self.valve_cron_jobs:
                self.scheduler.remove_job(job_id)
                logger.info(f"Removed existing job for valve {valve_id} before adding new one")
            
            # Add new job with cron expression
            # APScheduler expects cron parameters directly
            # We need to parse the cron expression and pass it as parameters
            cron_params = self._parse_cron_expression(cron_expression)
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
            
            self.valve_cron_jobs[job_id] = {
                'valve_id': valve_id,
                'cron_expression': cron_expression,
                'duration': duration
            }
            
            logger.info(f"Added cron job for valve {valve_id}: {cron_expression} with duration {duration}s")
            
        except Exception as e:
            logger.error(f"Error adding cron job for valve {cron_data['valve_id']}: {e}")
    
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
                # If it's not standard cron, return the expression as-is for APScheduler to handle
                logger.warning(f"Non-standard cron expression: {cron_expression}")
                return {}
        except Exception as e:
            logger.error(f"Error parsing cron expression '{cron_expression}': {e}")
            return {}
    
    def _run_valve_activation(self, valve_id: int, duration: int):
        """Run the valve activation for a specific valve with duration."""
        try:
            logger.info(f"Running scheduled activation for valve {valve_id} for {duration} seconds")
            
            if self.main_service is None:
                logger.error("Main service not initialized, cannot activate valve")
                return
        
            # Activate the valve with specified duration
            success = self.main_service.activate_valve(valve_id, duration)
        
            if success:
                logger.info(f"Successfully activated valve {valve_id} for {duration} seconds")
            else:
                logger.error(f"Failed to activate valve {valve_id} for {duration} seconds")
        
        except Exception as e:
            logger.error(f"Error in valve activation: {e}")
    
    def add_valve_cron(self, valve_id: int, cron_expression: str, duration: int = 60, enabled: bool = True):
        """Add a new cron schedule for a valve."""
        try:
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
                self.scheduler.remove_job(job_id)
                logger.info(f"Removed existing cron job for valve {valve_id} before adding new one")
                # Remove from tracking
                del self.valve_cron_jobs[job_id]
         	
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
                self.scheduler.remove_job(job_id)
                del self.valve_cron_jobs[job_id]
                logger.info(f"Removed cron job for valve {valve_id} from scheduler")
            
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