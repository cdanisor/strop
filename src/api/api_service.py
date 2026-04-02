"""
API Service for Raspberry Pi Irrigation System
This service exposes valve control functionality through a REST API.
"""

from flask import Flask, jsonify, request
from flask_cors import CORS
import logging
from typing import Dict, Any, Optional
import json

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class APIService:
    """Service for exposing valve control through REST API."""
    
    def __init__(self, host='0.0.0.0', port=5000):
        """
        Initialize the API service.
        
        Args:
            host (str): Host address to bind the API to
            port (int): Port number to bind the API to
        """
        self.host = host
        self.port = port
        self.app = Flask(__name__)
        # Enable CORS for all routes - simple and clean configuration
        CORS(self.app, supports_credentials=True)
        self._setup_routes()
    
    def _setup_routes(self):
        """Setup API routes."""
        # Route for activating a valve
        @self.app.route('/api/valves/<int:valve_id>/activate', methods=['POST'])
        def activate_valve(valve_id):
            """Activate a specific valve."""
            try:
                # Import main service here to avoid circular imports
                from src.main_service import main_service
                
                # Validate valve ID
                if valve_id not in [1, 2]:
                    return jsonify({'error': 'Invalid valve ID. Must be 1 or 2'}), 400
                
                # Check if valve is already active
                current_status = main_service.get_valve_status(valve_id)
                if current_status:
                    return jsonify({
                        'success': False,
                        'message': f'Valve {valve_id} is already active'
                    }), 400
                
                # Get duration from request (optional)
                duration = request.json.get('duration')
                if duration is not None:
                    try:
                        duration = int(duration)
                        if duration < 0:
                            return jsonify({'error': 'Duration must be non-negative'}), 400
                        # Limit duration to 1 hour (3600 seconds)
                        if duration > 3600:
                            duration = 3600
                    except ValueError:
                        return jsonify({'error': 'Duration must be a valid integer'}), 400
                else:
                    # Default to 1 minute (60 seconds) if no duration specified
                    duration = 60
                
                # Activate valve
                result = main_service.activate_valve(valve_id, duration)
                
                if result:
                    return jsonify({
                        'success': True,
                        'message': f'Valve {valve_id} activated for {duration} seconds'
                    }), 200
                else:
                    return jsonify({
                        'success': False,
                        'message': f'Failed to activate valve {valve_id}'
                    }), 500
                    
            except Exception as e:
                logger.error(f"Error activating valve {valve_id}: {e}")
                return jsonify({
                    'success': False,
                    'message': f'Error activating valve: {str(e)}'
                }), 500
        
        # Route for deactivating a valve
        @self.app.route('/api/valves/<int:valve_id>/deactivate', methods=['POST'])
        def deactivate_valve(valve_id):
            """Deactivate a specific valve."""
            try:
                # Import main service here to avoid circular imports
                from src.main_service import main_service
                
                # Validate valve ID
                if valve_id not in [1, 2]:
                    return jsonify({'error': 'Invalid valve ID. Must be 1 or 2'}), 400
                
                # Check if valve is already inactive
                current_status = main_service.get_valve_status(valve_id)
                if not current_status:
                    return jsonify({
                        'success': False,
                        'message': f'Valve {valve_id} is already inactive'
                    }), 400
                
                # Deactivate valve - this will be a manual deactivation
                result = main_service.deactivate_valve(valve_id, manual=True)
                
                if result:
                    return jsonify({
                        'success': True,
                        'message': f'Valve {valve_id} deactivated successfully'
                    }), 200
                else:
                    return jsonify({
                        'success': False,
                        'message': f'Failed to deactivate valve {valve_id}'
                    }), 500
                    
            except Exception as e:
                logger.error(f"Error deactivating valve {valve_id}: {e}")
                return jsonify({
                    'success': False,
                    'message': f'Error deactivating valve: {str(e)}'
                }), 500
        
        # Route for getting status of a specific valve
        @self.app.route('/api/valves/<int:valve_id>/status', methods=['GET'])
        def get_valve_status(valve_id):
            """Get status of a specific valve."""
            try:
                # Import main service here to avoid circular imports
                from src.main_service import main_service
                
                # Validate valve ID
                if valve_id not in [1, 2]:
                    return jsonify({'error': 'Invalid valve ID. Must be 1 or 2'}), 400
                
                # Get valve status
                status = main_service.get_valve_status(valve_id)
                
                return jsonify({
                    'valve_id': valve_id,
                    'status': status
                }), 200
                
            except Exception as e:
                logger.error(f"Error getting status for valve {valve_id}: {e}")
                return jsonify({
                    'success': False,
                    'message': f'Error getting valve status: {str(e)}'
                }), 500
        
        # Route for getting status of all valves
        @self.app.route('/api/valves/status', methods=['GET'])
        def get_all_valve_status():
            """Get status of all valves."""
            try:
                # Import main service here to avoid circular imports
                from src.main_service import main_service
                
                # Get all valve statuses
                all_status = main_service.get_all_valve_status()
                
                return jsonify({
                    'valves': all_status
                }), 200
                
            except Exception as e:
                logger.error(f"Error getting all valve statuses: {e}")
                return jsonify({
                    'success': False,
                    'message': f'Error getting valve statuses: {str(e)}'
                }), 500
        
        # Route for health check
        @self.app.route('/api/health', methods=['GET'])
        def health_check():
            """Health check endpoint."""
            return jsonify({
                'status': 'healthy',
                'service': 'irrigation-control-api'
            }), 200
        
        # Route for getting operation history for a specific valve
        @self.app.route('/api/valves/<int:valve_id>/history', methods=['GET'])
        def get_valve_history(valve_id):
            """Get operation history for a specific valve."""
            try:
                # Import database here to avoid circular imports
                from src.database import Database
                db = Database()
                
                # Validate valve ID
                if valve_id not in [1, 2]:
                    return jsonify({'error': 'Invalid valve ID. Must be 1 or 2'}), 400
                
                # Get valve logs for this valve
                logs = db.get_valve_logs(valve_id=valve_id, limit=20)
                
                return jsonify({
                    'valve_id': valve_id,
                    'history': logs
                }), 200
                
            except Exception as e:
                logger.error(f"Error getting valve {valve_id} history: {e}")
                return jsonify({
                    'success': False,
                    'message': f'Error getting valve history: {str(e)}'
                }), 500
        
        # Route for getting operation history for all valves
        @self.app.route('/api/valves/history', methods=['GET'])
        def get_all_valve_history():
            """Get operation history for all valves."""
            try:
                # Import database here to avoid circular imports
                from src.database import Database
                db = Database()
                
                # Get all valve logs
                logs = db.get_valve_logs(limit=100)
                
                return jsonify({
                    'valves': logs
                }), 200
                
            except Exception as e:
                logger.error(f"Error getting all valve history: {e}")
                return jsonify({
                    'success': False,
                    'message': f'Error getting all valve history: {str(e)}'
                }), 500
        
        # Route for getting weather data history
        @self.app.route('/api/weather/history', methods=['GET'])
        def get_weather_history():
            """Get weather data history for UI."""
            try:
                # Import database here to avoid circular imports
                from src.database import Database
                db = Database()
                
                # Get weather data history (default 100 records)
                weather_data = db.get_weather_data_history(limit=100)
                
                # Return the data
                return jsonify({
                    'weather': weather_data
                }), 200
                
            except Exception as e:
                logger.error(f"Error getting weather history: {e}")
                return jsonify({
                    'success': False,
                    'message': f'Error getting weather history: {str(e)}'
                }), 500
        
        # Route for getting weather forecast data
        @self.app.route('/api/weather/forecast', methods=['GET'])
        def get_weather_forecast():
            """Get current weather forecast data for UI."""
            try:
                # Import database here to avoid circular imports
                from src.database import Database
                db = Database()
                
                # Get the latest weather data
                latest_weather = db.get_latest_weather_data()
                
                if latest_weather and 'forecast_5day' in latest_weather:
                    # Parse the forecast JSON data
                    try:
                        forecast_data = json.loads(latest_weather['forecast_5day'])
                        return jsonify({
                            'forecast': forecast_data
                        }), 200
                    except json.JSONDecodeError:
                        # If we can't parse the JSON, return error
                        return jsonify({
                            'success': False,
                            'message': 'Failed to parse forecast data'
                        }), 500
                else:
                    return jsonify({
                        'success': False,
                        'message': 'No forecast data available'
                    }), 404
                    
            except Exception as e:
                logger.error(f"Error getting weather forecast: {e}")
                return jsonify({
                    'success': False,
                    'message': f'Error getting weather forecast: {str(e)}'
                }), 500
        
        # Route for getting all daily weather forecast data
        @self.app.route('/api/weather/daily', methods=['GET'])
        def get_weather_daily():
            """Get all daily weather forecast data for UI."""
            try:
                # Import database here to avoid circular imports
                from src.database import Database
                db = Database()
    
                # Get all daily weather data
                daily_weather = db.get_all_daily_weather_data()
    
                if daily_weather:
                    return jsonify({
                        'daily': daily_weather
                    }), 200
                else:
                    return jsonify({
                        'success': False,
                        'message': 'No daily weather data available'
                    }), 404
             
            except Exception as e:
                logger.error(f"Error getting daily weather data: {e}")
                return jsonify({
                    'success': False,
                    'message': f'Error getting daily weather data: {str(e)}'
                }), 500
        
        # Route for getting valve cron schedules
        @self.app.route('/api/valves/<int:valve_id>/cron', methods=['GET'])
        def get_valve_cron(valve_id):
            """Get cron schedule for a specific valve."""
            try:
                # Import database here to avoid circular imports
                from src.database import Database
                db = Database()
    
                # Validate valve ID
                if valve_id not in [1, 2]:
                    return jsonify({'error': 'Invalid valve ID. Must be 1 or 2'}), 400
    
                # Get valve cron
                cron = db.get_valve_cron(valve_id)
    
                if cron:
                    return jsonify({
                        'valve_id': valve_id,
                        'cron': cron
                    }), 200
                else:
                    return jsonify({
                        'valve_id': valve_id,
                        'cron': None
                    }), 200
    
            except Exception as e:
                logger.error(f"Error getting valve {valve_id} cron: {e}")
                return jsonify({
                    'success': False,
                    'message': f'Error getting valve cron: {str(e)}'
                }), 500
        
        # Route for setting valve cron schedule
        @self.app.route('/api/valves/<int:valve_id>/cron', methods=['POST'])
        def set_valve_cron(valve_id):
            """Set cron schedule for a specific valve."""
            try:
                # Import database here to avoid circular imports
                from src.database import Database
                db = Database()
    
                # Validate valve ID
                if valve_id not in [1, 2]:
                    return jsonify({'error': 'Invalid valve ID. Must be 1 or 2'}), 400
    
                # Get cron data from request
                cron_data = request.json
                if not cron_data:
                    return jsonify({'error': 'No cron data provided'}), 400
    
                cron_expression = cron_data.get('cron_expression')
                enabled = cron_data.get('enabled', True)
                duration = cron_data.get('duration')
    
                if not cron_expression:
                    return jsonify({'error': 'Cron expression is required'}), 400
    
                # Update valve cron
                success = db.update_valve_cron(valve_id, cron_expression, enabled)
    
                if success:
                    # If duration is provided, update it in the database
                    if duration is not None:
                        db.update_valve_cron_duration(valve_id, duration)
                    # Calculate and set the next run date
                    from apscheduler.triggers.cron import CronTrigger
                    from datetime import datetime
                    try:
                        # Parse the cron expression to get the next run date
                        trigger = CronTrigger.from_crontab(cron_expression)
                        # Use the current time properly
                        current_time = datetime.now()
                        # Try to get next run time - the method signature is different
                        # The correct signature is get_next_fire_time(previous_fire_time, now)
                        # For the first run, we can pass None as previous_fire_time
                        next_run = trigger.get_next_fire_time(None, current_time)
                        # Update the next_run date in the database
                        conn = db.get_connection()
                        cursor = conn.cursor()
                        cursor.execute('''
                            UPDATE valve_cron
                            SET next_run = ?
                            WHERE valve_id = ?
                        ''', (next_run.isoformat(), valve_id))
                        conn.commit()
                        conn.close()
                        logger.info(f"Set next run date for valve {valve_id}: {next_run}")
                    except Exception as e:
                        logger.error(f"Error calculating next run date for valve {valve_id}: {e}")
                        # Even if there's an error, we still return success to avoid breaking the API
                        # The scheduler will handle invalid cron expressions properly
                    # Update the scheduler to respect the new cron
                    try:
                        # Import the main service to access the scheduler
                        from src.main_service import main_service
                        # Restart the scheduler to load the new cron
                        if main_service.valve_scheduler:
                            main_service.valve_scheduler._load_existing_crons()
                        logger.info(f"New cron set for valve {valve_id}, scheduler reinitialized")
                    except Exception as e:
                        logger.error(f"Error updating scheduler with new cron for valve {valve_id}: {e}")
                    return jsonify({
                        'success': True,
                        'message': f'Cron schedule set for valve {valve_id}'
                    }), 200
                else:
                    return jsonify({
                        'success': False,
                        'message': f'Failed to set cron schedule for valve {valve_id}'
                    }), 500
    
            except Exception as e:
                logger.error(f"Error setting valve {valve_id} cron: {e}")
                return jsonify({
                    'success': False,
                    'message': f'Error setting valve cron: {str(e)}'
                }), 500
    
        # Route for getting valve usage statistics
        @self.app.route('/api/valves/usage', methods=['GET'])
        def get_valve_usage():
            """Get valve usage statistics for the last 7 days including today."""
            try:
                # Import database here to avoid circular imports
                from src.database import Database
                db = Database()
             
                # Get valve logs for the last 7 days (including today)
                from datetime import datetime, timedelta
                end_date = datetime.now()
                start_date = end_date - timedelta(days=7)
             
                # Get all valve logs for the last 7 days
                logs = db.get_valve_logs(limit=1000)  # Get a reasonable number of logs
             
                # Calculate total duration per valve per day
                usage_stats = {}
                for log in logs:
                    # Filter logs to last 7 days
                    log_date = datetime.fromisoformat(log['timestamp'].replace('Z', '+00:00')).date()
                    if start_date.date() <= log_date <= end_date.date():
                        valve_id = log['valve_id']
                        duration = log['duration'] or 0
             
                        if valve_id not in usage_stats:
                            usage_stats[valve_id] = {}
             
                        # Convert date to string for JSON serialization
                        date_str = log_date.isoformat()
                        if date_str not in usage_stats[valve_id]:
                            usage_stats[valve_id][date_str] = 0
             
                        usage_stats[valve_id][date_str] += duration
             
                # Convert seconds to minutes
                for valve_id in usage_stats:
                    for date in usage_stats[valve_id]:
                        usage_stats[valve_id][date] = round(usage_stats[valve_id][date] / 60)
             
                return jsonify({
                    'valves': usage_stats
                }), 200
             
            except Exception as e:
                logger.error(f"Error getting valve usage statistics: {e}")
                return jsonify({
                    'success': False,
                    'message': f'Error getting valve usage statistics: {str(e)}'
                }), 500
        
        # Route for getting next run times for all valves
        @self.app.route('/api/valves/next_run', methods=['GET'])
        def get_valves_next_run():
            """Get next run times for all valves."""
            try:
                # Import database here to avoid circular imports
                from src.database import Database
                db = Database()
    
                # Get all valve crons
                all_crons = db.get_all_valve_crons()
    
                # Prepare response with next run times
                next_runs = []
                for cron in all_crons:
                    if cron['enabled'] and cron['cron_expression']:
                        # Calculate the next 5 runs for this valve
                        valve_next_runs = []
                        cron_expression = cron['cron_expression']
                        
                        # Import required modules for cron parsing
                        from apscheduler.triggers.cron import CronTrigger
                        from datetime import datetime
                        
                        # Create a CronTrigger from the cron expression
                        trigger = CronTrigger.from_crontab(cron_expression)
                        
                        # Get the current time
                        current_time = datetime.now()
                        
                        # Calculate the next 5 run times
                        for i in range(5):
                            try:
                                # Get next run time after current time
                                next_run = trigger.get_next_fire_time(None, current_time)
                                if next_run:
                                    valve_next_runs.append(next_run.isoformat())
                                    # Set current_time to the next run time for the next iteration
                                    # Add 1 minute to current_time to avoid same time issues
                                    from datetime import timedelta
                                    current_time = next_run + timedelta(minutes=1)
                                else:
                                    break
                            except Exception as e:
                                logger.error(f"Error calculating next run for valve {cron['valve_id']}: {e}")
                                break
                        
                        next_runs.append({
                            'valve_id': cron['valve_id'],
                            'next_runs': valve_next_runs
                        })
    
                return jsonify({
                    'next_runs': next_runs
                }), 200
    
            except Exception as e:
                logger.error(f"Error getting valves next run times: {e}")
                return jsonify({
                    'success': False,
                    'message': f'Error getting valves next run times: {str(e)}'
                }), 500
    
    def run(self):
        """Start the API server."""
        try:
            logger.info(f"Starting API server on {self.host}:{self.port}")
            # Run Flask with threaded=True to allow proper signal handling
            # Also set use_reloader=False to prevent issues with reloader during shutdown
            self.app.run(host=self.host, port=self.port, debug=False, threaded=True, use_reloader=False)
        except Exception as e:
            logger.error(f"Failed to start API server: {e}")
            raise

# Global instance
api_service = APIService()