"""
API Service for Raspberry Pi Irrigation System
This service exposes valve control functionality through a REST API.
"""

from flask import Flask, jsonify, request
from flask_cors import CORS
import logging
from typing import Dict, Any, Optional
import json

from src.services.cron_utils import next_run_times, validate_cron, CronValidationError

MAX_DURATION_SECONDS = 3600
DEFAULT_MANUAL_DURATION = 60

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
# Per-request access logs flood the journal (and wear the SD card)
logging.getLogger('werkzeug').setLevel(logging.WARNING)

# Endpoints reachable without a token
PUBLIC_ENDPOINTS = {'/api/health', '/api/auth/login', '/api/auth/status'}

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
        # Bearer tokens (no cookies), so credentials are not needed for CORS
        CORS(self.app, allow_headers=['Content-Type', 'Authorization'])
        self._auth = None
        self._setup_auth()
        self._setup_routes()

    @property
    def auth(self):
        """AuthService sharing the main service's configuration (created lazily)."""
        if self._auth is None:
            from src.main_service import main_service
            from src.services.auth_service import AuthService
            self._auth = AuthService(main_service.config_service)
        return self._auth

    def _setup_auth(self):
        """Require a valid bearer token on every API endpoint except PUBLIC_ENDPOINTS."""

        @self.app.before_request
        def require_token():
            if request.method == 'OPTIONS' or not request.path.startswith('/api/'):
                return None
            if request.path in PUBLIC_ENDPOINTS:
                return None
            header = request.headers.get('Authorization', '')
            token = header[7:].strip() if header.lower().startswith('bearer ') else None
            if not self.auth.verify_token(token):
                return jsonify({'success': False, 'code': 'auth_required', 'message': 'Authentication required',
                                'auth_required': True}), 401
            return None

        @self.app.route('/api/auth/status', methods=['GET'])
        def auth_status():
            """Whether a password is configured (no secrets revealed)."""
            return jsonify({'configured': self.auth.is_configured()}), 200

        @self.app.route('/api/auth/login', methods=['POST'])
        def auth_login():
            """Exchange the password for a bearer token."""
            auth = self.auth
            key = auth.client_key(request.remote_addr, request.headers.get('X-Forwarded-For'))
            wait = auth.retry_after(key)
            if wait:
                resp = jsonify({'success': False, 'code': 'rate_limited', 'retry_minutes': max(1, wait // 60),
                                'message': f'Too many failed attempts. Try again in {max(1, wait // 60)} min.'})
                resp.headers['Retry-After'] = str(wait)
                return resp, 429
            if not auth.is_configured():
                return jsonify({'success': False, 'code': 'not_configured',
                                'message': 'No password set on the controller. Run scripts/set_password.py on the Pi.'}), 503
            payload = request.get_json(silent=True) or {}
            if not auth.check_password(str(payload.get('password') or '')):
                auth.record_failure(key)
                return jsonify({'success': False, 'code': 'wrong_password', 'message': 'Wrong password'}), 401
            auth.record_success(key)
            return jsonify({'success': True, 'token': auth.issue_token(),
                            'expires_in': auth.token_max_age}), 200

        # ------------------------------------------------------------ integrations
        @self.app.route('/api/auth/integration-tokens', methods=['GET'])
        def list_integration_tokens():
            return jsonify({'tokens': self.auth.list_integration_tokens()}), 200

        @self.app.route('/api/auth/integration-tokens', methods=['POST'])
        def create_integration_token():
            """Create a long-lived token for an integration (shown only once)."""
            payload = request.get_json(silent=True) or {}
            try:
                token = self.auth.create_integration_token(str(payload.get('name') or ''))
            except ValueError as e:
                return jsonify({'success': False, 'code': 'invalid_name', 'message': str(e)}), 400
            return jsonify({'success': True, 'token': token}), 200

        @self.app.route('/api/auth/integration-tokens/<name>', methods=['DELETE'])
        def revoke_integration_token(name):
            if not self.auth.revoke_integration_token(name):
                return jsonify({'success': False, 'message': 'Unknown token'}), 404
            return jsonify({'success': True}), 200

        @self.app.route('/api/integrations/webhooks', methods=['GET'])
        def list_webhooks():
            from src.main_service import main_service
            hooks = [{'name': h.get('name')} for h in main_service.notifier.webhooks()]
            return jsonify({'webhooks': hooks}), 200

        @self.app.route('/api/integrations/webhooks', methods=['POST'])
        def set_webhook():
            """Register (or replace) the webhook an integration wants events on."""
            from src.main_service import main_service
            payload = request.get_json(silent=True) or {}
            name = str(payload.get('name') or '').strip()[:64]
            url = str(payload.get('url') or '').strip()
            if not name or not url:
                return jsonify({'success': False, 'message': 'name and url are required'}), 400
            try:
                main_service.notifier.set_webhook(name, url)
            except ValueError as e:
                return jsonify({'success': False, 'message': str(e)}), 400
            return jsonify({'success': True}), 200

        @self.app.route('/api/integrations/webhooks/<name>', methods=['DELETE'])
        def remove_webhook(name):
            from src.main_service import main_service
            if not main_service.notifier.remove_webhook(name):
                return jsonify({'success': False, 'message': 'Unknown webhook'}), 404
            return jsonify({'success': True}), 200

        @self.app.route('/api/auth/check', methods=['GET'])
        def auth_check():
            """Protected no-op used by the UI to validate a stored token."""
            return jsonify({'success': True}), 200
    
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
                        'code': 'already_active',
                        'message': f'Valve {valve_id} is already active'
                    }), 400
                
                # Get duration from request (optional, body may be missing)
                payload = request.get_json(silent=True) or {}
                duration = payload.get('duration')
                if duration is not None:
                    try:
                        duration = int(duration)
                    except (TypeError, ValueError):
                        return jsonify({'success': False, 'message': 'Duration must be a valid integer'}), 400
                    if duration <= 0:
                        return jsonify({'success': False, 'code': 'invalid_duration',
                                        'message': 'Duration must be at least 1 second'}), 400
                    # Limit duration to 1 hour (3600 seconds)
                    duration = min(duration, MAX_DURATION_SECONDS)
                else:
                    # Default to 1 minute (60 seconds) if no duration specified
                    duration = DEFAULT_MANUAL_DURATION

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
                
                # Daily forecast from today onwards
                forecast = db.get_weather_forecast_data()
                if forecast:
                    return jsonify({'forecast': forecast}), 200
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
    
                # Limit to no more than 6 days in the past
                from datetime import datetime, timedelta
                today = datetime.now().date()
                limited_weather = []
                
                for data in daily_weather:
                    # Parse the date from the data (assuming it's in YYYY-MM-DD format)
                    data_date = datetime.strptime(data['date'], '%Y-%m-%d').date()
                    # Calculate the difference in days from today
                    days_diff = (today - data_date).days
                    # Only include data from the last 6 days (including today)
                    if days_diff <= 6:
                        limited_weather.append(data)
    
                if limited_weather:
                    return jsonify({
                        'daily': limited_weather
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
                cron_data = request.get_json(silent=True)
                if not cron_data:
                    return jsonify({'success': False, 'message': 'No cron data provided'}), 400

                cron_expression = (cron_data.get('cron_expression') or '').strip()
                enabled = cron_data.get('enabled', True)
                duration = cron_data.get('duration')

                if not isinstance(enabled, bool):
                    return jsonify({'success': False, 'message': 'enabled must be true or false'}), 400

                if not cron_expression:
                    return jsonify({'success': False, 'message': 'Cron expression is required'}), 400

                # Reject invalid expressions before they reach the database/scheduler
                try:
                    validate_cron(cron_expression)
                except CronValidationError as e:
                    return jsonify({'success': False, 'code': 'invalid_cron', 'message': str(e)}), 400

                if duration is not None:
                    try:
                        duration = int(duration)
                    except (TypeError, ValueError):
                        return jsonify({'success': False, 'message': 'Duration must be a valid integer'}), 400
                    if duration <= 0 or duration > MAX_DURATION_SECONDS:
                        return jsonify({'success': False,
                                        'message': f'Duration must be between 1 and {MAX_DURATION_SECONDS} seconds'}), 400

                if not db.update_valve_cron(valve_id, cron_expression, enabled):
                    return jsonify({
                        'success': False,
                        'message': f'Failed to set cron schedule for valve {valve_id}'
                    }), 500
                if duration is not None:
                    db.update_valve_cron_duration(valve_id, duration)

                # Sync the running scheduler (adds, replaces or removes the job)
                from src.main_service import main_service
                if main_service.valve_scheduler:
                    main_service.valve_scheduler.reload_valve(valve_id)
                logger.info(f"Cron set for valve {valve_id}: '{cron_expression}' enabled={enabled}")

                state = "enabled" if enabled else "saved (disabled)"
                return jsonify({
                    'success': True,
                    'message': f'Cron schedule {state} for valve {valve_id}'
                }), 200

            except Exception as e:
                logger.error(f"Error setting valve {valve_id} cron: {e}")
                return jsonify({
                    'success': False,
                    'message': f'Error setting valve cron: {str(e)}'
                }), 500
    
        # Route for clearing (deleting) a valve cron schedule
        @self.app.route('/api/valves/<int:valve_id>/cron', methods=['DELETE'])
        def delete_valve_cron(valve_id):
            """Clear and disable the cron schedule of a valve."""
            try:
                from src.database import Database
                db = Database()

                if valve_id not in [1, 2]:
                    return jsonify({'error': 'Invalid valve ID. Must be 1 or 2'}), 400

                if not db.update_valve_cron(valve_id, '', False):
                    return jsonify({'success': False,
                                    'message': f'Failed to clear schedule for valve {valve_id}'}), 500

                from src.main_service import main_service
                if main_service.valve_scheduler:
                    main_service.valve_scheduler.reload_valve(valve_id)

                return jsonify({'success': True,
                                'message': f'Schedule cleared for valve {valve_id}'}), 200
            except Exception as e:
                logger.error(f"Error clearing valve {valve_id} cron: {e}")
                return jsonify({'success': False, 'message': f'Error clearing valve cron: {str(e)}'}), 500

        # Route for getting valve usage statistics
        @self.app.route('/api/valves/usage', methods=['GET'])
        def get_valve_usage():
            """Get valve usage statistics for the last 8 days including today."""
            try:
                # Import database here to avoid circular imports
                from src.database import Database
                db = Database()
             
                # Get valve logs for the last 8 days (including today)
                from datetime import datetime, timedelta
                end_date = datetime.now()
                start_date = end_date - timedelta(days=8)
             
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
                        # Same trigger construction as the scheduler, so the
                        # displayed days match the real executions
                        try:
                            runs = [r.isoformat() for r in next_run_times(cron['cron_expression'], 5)]
                        except CronValidationError as e:
                            logger.error(f"Invalid cron for valve {cron['valve_id']}: {e}")
                            runs = []
                        next_runs.append({
                            'valve_id': cron['valve_id'],
                            'next_runs': runs
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
    
        # Route for the whole dashboard in one request (cheap for the Pi:
        # the UI polls only /api/valves/status and calls this on changes)
        @self.app.route('/api/valves/<int:valve_id>/name', methods=['PUT', 'POST'])
        def set_valve_name(valve_id):
            """Rename a zone; an empty name restores the default ("Zona N")."""
            from src.main_service import main_service
            if valve_id not in [1, 2]:
                return jsonify({'error': 'Invalid valve ID. Must be 1 or 2'}), 400
            payload = request.get_json(silent=True) or {}
            if not isinstance(payload.get('name', ''), str):
                return jsonify({'error': 'name must be a string'}), 400
            try:
                name = main_service.config_service.set_zone_name(valve_id, payload.get('name'))
            except Exception as e:
                logger.error(f"Error renaming valve {valve_id}: {e}")
                return jsonify({'success': False, 'message': 'Could not save the name'}), 500
            logger.info(f"Valve {valve_id} renamed to {name!r}")
            return jsonify({'success': True, 'valve_id': valve_id, 'name': name}), 200

        @self.app.route('/api/dashboard', methods=['GET'])
        def get_dashboard():
            """Valves (state, schedule, next runs, history), usage and weather."""
            try:
                from src.database import Database
                from src.main_service import main_service
                from datetime import datetime, timedelta
                from src.services.watering_adjustment import (WateringAdjuster, decode_note,
                                                              settings as adjustment_settings)
                db = Database()
                now = datetime.now()
                today = now.date()
                adjuster = WateringAdjuster(db, main_service.config_service.get('watering_adjustment', {}) or {})
                weather_by_date = {w['date']: w for w in db.get_all_daily_weather_data()}

                valves = []
                for valve_id in (1, 2):
                    details = main_service.get_valve_details(valve_id)
                    cron = db.get_valve_cron(valve_id) or {}
                    next_runs = []
                    planned = []
                    base_duration = cron.get('duration') or 60
                    if cron.get('enabled') and cron.get('cron_expression'):
                        try:
                            runs = next_run_times(cron['cron_expression'], 5)
                        except CronValidationError as e:
                            logger.error(f"Invalid cron for valve {valve_id}: {e}")
                            runs = []
                        next_runs = [r.isoformat() for r in runs]
                        # Expected weather adjustment of each upcoming run
                        for r in runs:
                            plan = adjuster.plan(base_duration, r.date(), weather_by_date)
                            if r.date().isoformat() not in weather_by_date:
                                # Beyond the forecast: shown as "pending" (at most the
                                # programmed time), computed for real at run time
                                plan.update(reason='Forecast not available yet, adjusted at run time',
                                            reason_key='pending', reason_args={}, pending=True,
                                            percent=100, skip=False, duration=base_duration)
                            planned.append({
                                'at': r.isoformat(),
                                'base_duration': base_duration,
                                'duration': plan['duration'],
                                'percent': plan['percent'],
                                'skip': plan['skip'],
                                'reason': plan['reason'],
                                'reason_key': plan['reason_key'],
                                'reason_args': plan['reason_args'],
                                'has_forecast': r.date().isoformat() in weather_by_date,
                            })
                    history = [
                        {'status': log['status'], 'start_time': log['start_time'] or log['timestamp'],
                         'duration': log['duration'], 'base_duration': log.get('base_duration'),
                         'adjust_percent': log.get('adjust_percent'),
                         'adjust_note': decode_note(log.get('adjust_note'))['text'],
                         'adjust_reason': decode_note(log.get('adjust_note'))}
                        for log in db.get_valve_logs(valve_id=valve_id, limit=5)
                    ]
                    valves.append({
                        'id': valve_id,
                        'name': main_service.config_service.zone_name(valve_id),
                        **details,
                        'schedule': {
                            'cron_expression': cron.get('cron_expression') or '',
                            'enabled': bool(cron.get('enabled')),
                            'duration': cron.get('duration'),
                            'last_run': cron.get('last_run'),
                            'next_runs': next_runs,
                            'planned': planned,
                        },
                        'history': history,
                    })

                # Watering seconds per valve per day for the last 7 days
                usage = {1: {}, 2: {}}
                start_day = today - timedelta(days=6)
                for log in db.get_valve_logs(limit=500):
                    if not log['duration']:
                        continue
                    started = log['start_time'] or log['timestamp']
                    try:
                        day = datetime.fromisoformat(str(started)).date()
                    except ValueError:
                        continue
                    if start_day <= day <= today and log['valve_id'] in usage:
                        key = day.isoformat()
                        usage[log['valve_id']][key] = usage[log['valve_id']].get(key, 0) + log['duration']

                weather = [w for w in db.get_all_daily_weather_data()
                           if (datetime.strptime(w['date'], '%Y-%m-%d').date() - today).days <= 5]
                weather_updated = max((w['timestamp'] for w in weather if w['timestamp']), default=None)

                # Breakdown for the next scheduled run day (or today)
                upcoming = sorted(p['at'] for v in valves for p in v['schedule']['planned'])
                focus_day = datetime.fromisoformat(upcoming[0]).date() if upcoming else today
                adjustment = adjuster.for_date(focus_day, weather_by_date)
                adjustment['settings'] = {
                    k: v for k, v in adjustment_settings(adjuster.config).items() if k != 'rain_weights'
                }

                return jsonify({
                    'server_time': now.isoformat(),
                    'valves': valves,
                    'adjustment': adjustment,
                    'usage': usage,
                    'weather': weather,
                    'weather_updated': weather_updated,
                }), 200
            except Exception as e:
                logger.error(f"Error building dashboard: {e}")
                return jsonify({'success': False, 'message': f'Error building dashboard: {str(e)}'}), 500

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