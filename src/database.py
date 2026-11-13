"""
Database Module for Raspberry Pi Irrigation System
This module handles database operations for storing valve logs and other system data.
"""
import os
import sqlite3
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Project root (one level above src/) so the DB location does not depend on the CWD
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DB_PATH = os.environ.get("STROP_DB_PATH", os.path.join(PROJECT_ROOT, "irrigation_system.db"))

# A valve can never be open longer than this (see GPIOControlService); used to
# bound durations of records left "Opened" by a crash.
MAX_VALVE_DURATION_SECONDS = 3600

class Database:
    """Database class for managing irrigation system data."""
    
    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        """
        Initialize database connection and create tables if they don't exist.
        
        Args:
            db_path (str): Path to the SQLite database file
        """
        self.db_path = db_path
        self.init_database()
    
    def get_connection(self):
        """
        Create and return a SQLite database connection with row_factory for named access.
        
        Returns:
            sqlite3.Connection: Database connection object
        """
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row  # Enable named column access
        return conn
    
    def init_database(self):
        """
        Create all required tables if they don't exist.
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # Create valve_logs table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS valve_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    valve_id INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    timestamp DATETIME NOT NULL,
                    duration INTEGER,
                    start_time DATETIME
                )
            ''')
            
            # Check if start_time column exists, if not add it (for backward compatibility)
            try:
                cursor.execute('SELECT start_time FROM valve_logs LIMIT 1')
            except sqlite3.OperationalError:
                # Column doesn't exist, add it
                cursor.execute('ALTER TABLE valve_logs ADD COLUMN start_time DATETIME')
            
            # Create weather_data table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS weather_data (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME NOT NULL,
                    date DATE NOT NULL,
                    temperature_minimum REAL,
                    temperature_maximum REAL,
                    average_humidity INTEGER,
                    average_pressure INTEGER,
                    description TEXT,
                    total_rain REAL DEFAULT 0
                )
            ''')
            
            # Check if total_rain column exists, if not add it (for backward compatibility)
            try:
                cursor.execute('SELECT total_rain FROM weather_data LIMIT 1')
            except sqlite3.OperationalError:
                # Column doesn't exist, add it
                cursor.execute('ALTER TABLE weather_data ADD COLUMN total_rain REAL DEFAULT 0')

            # One-off data fix: an averaging bug stored humidity and pressure at half
            # their real value. Real air pressure is never below 800 hPa, so such rows
            # are the affected ones; once doubled they no longer match (idempotent).
            cursor.execute('''
                UPDATE weather_data
                SET average_humidity = average_humidity * 2,
                    average_pressure = average_pressure * 2
                WHERE average_pressure > 0 AND average_pressure < 800
            ''')
            if cursor.rowcount:
                logger.info(f"Corrected halved humidity/pressure in {cursor.rowcount} weather rows")
            
            # Raw 3-hour forecast slots, keyed by their timestamp. Keeping every slot
            # (the last forecast received before it passed) lets daily totals cover
            # the whole day instead of only the slots still ahead at the last update.
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS weather_slots (
                    dt INTEGER PRIMARY KEY,
                    data TEXT NOT NULL,
                    updated_at DATETIME NOT NULL
                )
            ''')

            # Weather-based adjustment details for valve runs (backward compatible)
            for column, ddl in (('base_duration', 'INTEGER'), ('adjust_percent', 'INTEGER'),
                                ('adjust_note', 'TEXT')):
                try:
                    cursor.execute(f'SELECT {column} FROM valve_logs LIMIT 1')
                except sqlite3.OperationalError:
                    cursor.execute(f'ALTER TABLE valve_logs ADD COLUMN {column} {ddl}')

            # Create valve_cron table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS valve_cron (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    valve_id INTEGER NOT NULL,
                    cron_expression TEXT NOT NULL,
                    enabled BOOLEAN DEFAULT 1,
                    last_run DATETIME,
                    next_run DATETIME,
                    duration INTEGER
                )
            ''')
            
            # Several schedules per valve (one row each). Schema version 2 drops
            # the empty rows the single-schedule version used for "cleared".
            version = cursor.execute('PRAGMA user_version').fetchone()[0]
            if version < 2:
                cursor.execute("DELETE FROM valve_cron WHERE cron_expression IS NULL OR TRIM(cron_expression) = ''")
                cursor.execute('''
                    DELETE FROM valve_cron WHERE id NOT IN (
                        SELECT MIN(id) FROM valve_cron GROUP BY valve_id, cron_expression, duration)
                ''')
                cursor.execute('PRAGMA user_version = 2')

            # Create system_config table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS system_config (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    api_key TEXT,
                    location TEXT,
                    default_duration INTEGER DEFAULT 30,
                    weather_update_interval INTEGER DEFAULT 10
                )
            ''')
            
            # Create sessions table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT UNIQUE NOT NULL,
                    user_id INTEGER,
                    created_at DATETIME NOT NULL,
                    expires_at DATETIME NOT NULL,
                    ip_address TEXT,
                    user_agent TEXT
                )
            ''')
            
            conn.commit()
            conn.close()
            logger.info("Database initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            raise
    
    def insert_valve_log(self, valve_id: int, status: str, duration: Optional[int] = None,
                         start_time: Optional[datetime] = None,
                         meta: Optional[Dict[str, Any]] = None) -> Optional[int]:
        """
        Insert a new valve operation log entry.
        
        Args:
            valve_id (int): ID of the valve (1 or 2)
            status (str): Operation status ('on', 'off', 'Opened', 'Finished', 'Manually Stopped', 'Terminated')
            duration (int, optional): Duration of operation in seconds
            start_time (datetime, optional): Start time of the operation
    
        Returns:
            int: ID of the new log row (truthy), or None if insertion failed
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
    
            cursor.execute('''
                INSERT INTO valve_logs (valve_id, status, timestamp, duration, start_time,
                                        base_duration, adjust_percent, adjust_note)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (valve_id, status, datetime.now(), duration, start_time,
                  (meta or {}).get('base_duration'), (meta or {}).get('adjust_percent'),
                  (meta or {}).get('adjust_note')))
            log_id = cursor.lastrowid
    
            conn.commit()
            conn.close()
            logger.info(f"Valve log inserted: id={log_id}, valve_id={valve_id}, status={status}, duration={duration}")
            return log_id
    
        except Exception as e:
            logger.error(f"Failed to insert valve log: {e}")
            return None
    
    def update_valve_log_status(self, log_id: int, duration: int, status: str) -> bool:
        """
        Update an existing valve operation log entry with duration and status.
        
        Args:
            log_id (int): ID of the log entry to update
            duration (int): Duration of operation in seconds
            status (str): Status of the operation ('Opened', 'Finished', 'Manually Stopped', 'Terminated')
        
        Returns:
            bool: True if update was successful, False otherwise
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
    
            cursor.execute('''
                UPDATE valve_logs
                SET duration = ?, status = ?
                WHERE id = ?
            ''', (duration, status, log_id))
    
            conn.commit()
            conn.close()
            logger.info(f"Valve log updated: id={log_id}, duration={duration}, status={status}")
            return True
    
        except Exception as e:
            logger.error(f"Failed to update valve log with status: {e}")
            return False
    
    def get_valve_logs(self, valve_id: Optional[int] = None, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Retrieve valve operation logs.
        
        Args:
            valve_id (int, optional): Filter by specific valve ID
            limit (int): Maximum number of records to return
            
        Returns:
            List[Dict[str, Any]]: List of valve log records
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            if valve_id is not None:
                cursor.execute('''
                    SELECT * FROM valve_logs 
                    WHERE valve_id = ? 
                    ORDER BY timestamp DESC 
                    LIMIT ?
                ''', (valve_id, limit))
            else:
                cursor.execute('''
                    SELECT * FROM valve_logs 
                    ORDER BY timestamp DESC 
                    LIMIT ?
                ''', (limit,))
            
            rows = cursor.fetchall()
            conn.close()
            
            # Convert rows to list of dictionaries
            logs = []
            for row in rows:
                logs.append({
                    'id': row['id'],
                    'valve_id': row['valve_id'],
                    'status': row['status'],
                    'timestamp': row['timestamp'],
                    'duration': row['duration'],
                    'start_time': row['start_time'] if 'start_time' in row.keys() else None,
                    'base_duration': row['base_duration'] if 'base_duration' in row.keys() else None,
                    'adjust_percent': row['adjust_percent'] if 'adjust_percent' in row.keys() else None,
                    'adjust_note': row['adjust_note'] if 'adjust_note' in row.keys() else None,
                })
            
            return logs
            
        except Exception as e:
            logger.error(f"Failed to retrieve valve logs: {e}")
            return []
    
    def insert_weather_data(self, weather_data: Dict[str, Any]) -> bool:
        """
        Insert weather data into database.
        
        Args:
            weather_data (Dict[str, Any]): Dictionary with weather metrics
            {
                'date': date,
                'temperature_minimum': float,
                'temperature_maximum': float,
                'average_humidity': int,
                'average_pressure': int,
                'description': str,
                'total_rain': float
            }
        
        Returns:
            bool: True if insertion was successful, False otherwise
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
    
            # Check if we already have data for this date to avoid duplicates
            cursor.execute('''
                SELECT id FROM weather_data WHERE date = ?
            ''', (weather_data.get('date'),))
    
            existing_record = cursor.fetchone()
            if existing_record:
                # Update existing record instead of inserting new one
                cursor.execute('''
                    UPDATE weather_data
                        SET timestamp = ?, temperature_minimum = ?, temperature_maximum = ?,
                                average_humidity = ?, average_pressure = ?, description = ?, total_rain = ?
                        WHERE date = ?
                ''', (
                    datetime.now(),
                    weather_data.get('temperature_minimum'),
                    weather_data.get('temperature_maximum'),
                    weather_data.get('average_humidity'),
                    weather_data.get('average_pressure'),
                    weather_data.get('description'),
                    weather_data.get('total_rain', 0),
                    weather_data.get('date')
                ))
                logger.info(f"Updated existing weather data for date {weather_data.get('date')}")
            else:
                # Insert new record
                cursor.execute('''
                    INSERT INTO weather_data (timestamp, date, temperature_minimum, temperature_maximum, average_humidity, average_pressure, description, total_rain)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    datetime.now(),
                    weather_data.get('date'),
                    weather_data.get('temperature_minimum'),
                    weather_data.get('temperature_maximum'),
                    weather_data.get('average_humidity'),
                    weather_data.get('average_pressure'),
                    weather_data.get('description'),
                    weather_data.get('total_rain', 0)
                ))
                logger.info("Weather data inserted successfully")
    
            conn.commit()
            conn.close()
            return True
    
        except Exception as e:
            logger.error(f"Failed to insert weather data: {e}")
            return False
    
    def upsert_weather_slots(self, items: List[Dict[str, Any]]) -> None:
        """Store raw 3-hour forecast items (newer data replaces older for the same slot)."""
        import json
        now = datetime.now()
        conn = self.get_connection()
        try:
            conn.executemany(
                'INSERT OR REPLACE INTO weather_slots (dt, data, updated_at) VALUES (?, ?, ?)',
                [(int(item['dt']), json.dumps(item), now) for item in items if item.get('dt')])
            # Keep 60 days of slots
            cutoff = int(now.timestamp()) - 60 * 86400
            conn.execute('DELETE FROM weather_slots WHERE dt < ?', (cutoff,))
            conn.commit()
        finally:
            conn.close()

    def get_weather_slots(self, start_ts: int, end_ts: int) -> List[Dict[str, Any]]:
        """Raw forecast items with start_ts <= dt < end_ts, ordered by time."""
        import json
        conn = self.get_connection()
        try:
            rows = conn.execute('SELECT data FROM weather_slots WHERE dt >= ? AND dt < ? ORDER BY dt',
                                (start_ts, end_ts)).fetchall()
        finally:
            conn.close()
        return [json.loads(r['data']) for r in rows]

    def get_latest_weather_data(self) -> Optional[Dict[str, Any]]:
        """
        Retrieve the most recent weather data entry.
        
        Returns:
            Dict[str, Any]: Most recent weather data or None if no data exists
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
        
            cursor.execute('''
                SELECT * FROM weather_data
                ORDER BY timestamp DESC
                LIMIT 1
            ''')
        
            row = cursor.fetchone()
            conn.close()
        
            if row:
                return {
                    'id': row['id'],
                    'timestamp': row['timestamp'],
                    'date': row['date'],
                    'temperature_minimum': row['temperature_minimum'],
                    'temperature_maximum': row['temperature_maximum'],
                    'average_humidity': row['average_humidity'],
                    'average_pressure': row['average_pressure'],
                    'description': row['description'],
                    'total_rain': row['total_rain']
                }
        
            return None
        
        except Exception as e:
            logger.error(f"Failed to retrieve latest weather data: {e}")
            return None
   
    def get_all_daily_weather_data(self) -> List[Dict[str, Any]]:
        """
        Retrieve all daily weather data entries, limited to no more than 6 days in the past.
        
        Returns:
            List[Dict[str, Any]]: List of daily weather data entries (limited to 6 days)
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
        
            # Get all weather data but limit to 6 days in the past
            from datetime import datetime, timedelta
            today = datetime.now().date()
            six_days_ago = today - timedelta(days=6)
            
            cursor.execute('''
                SELECT * FROM weather_data
                WHERE date >= ?
                ORDER BY date ASC
            ''', (six_days_ago.isoformat(),))
        
            rows = cursor.fetchall()
            conn.close()
        
            # Convert rows to list of dictionaries
            daily_data = []
            for row in rows:
                daily_data.append({
                    'id': row['id'],
                    'timestamp': row['timestamp'],
                    'date': row['date'],
                    'temperature_minimum': row['temperature_minimum'],
                    'temperature_maximum': row['temperature_maximum'],
                    'average_humidity': row['average_humidity'],
                    'average_pressure': row['average_pressure'],
                    'description': row['description'],
                    'total_rain': row['total_rain']
                })
        
            return daily_data
        
        except Exception as e:
            logger.error(f"Failed to retrieve daily weather data: {e}")
            return []
    
    def get_weather_forecast_data(self) -> List[Dict[str, Any]]:
        """
        Retrieve the daily forecast from today onwards.

        Returns:
            List[Dict[str, Any]]: Daily weather rows with date >= today, ordered by date
        """
        today = datetime.now().date().isoformat()
        return [row for row in self.get_all_daily_weather_data() if row['date'] >= today]

    def get_weather_data_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Retrieve weather data history.
        
        Args:
            limit (int): Maximum number of records to return
      	  
        Returns:
            List[Dict[str, Any]]: List of weather data records
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
      	  
            cursor.execute('''
                SELECT * FROM weather_data
                ORDER BY timestamp DESC
                LIMIT ?
            ''', (limit,))
      	  
            rows = cursor.fetchall()
            conn.close()
      	  
            # Convert rows to list of dictionaries
            weather_data = []
            for row in rows:
                weather_data.append({
                    'id': row['id'],
                    'timestamp': row['timestamp'],
                    'date': row['date'],
                    'temperature_minimum': row['temperature_minimum'],
                    'temperature_maximum': row['temperature_maximum'],
                    'average_humidity': row['average_humidity'],
                    'average_pressure': row['average_pressure'],
                    'description': row['description'],
                    'total_rain': row['total_rain']
                })
      	  
            return weather_data
      	  
        except Exception as e:
            logger.error(f"Failed to retrieve weather data history: {e}")
            return []
    
    # ------------------------------------------------------------------ schedules
    @staticmethod
    def _schedule_row(row) -> Dict[str, Any]:
        return {
            'id': row['id'],
            'valve_id': row['valve_id'],
            'cron_expression': row['cron_expression'] or '',
            'enabled': bool(row['enabled']),
            'last_run': row['last_run'],
            'next_run': row['next_run'],
            'duration': row['duration'],
        }

    def list_schedules(self, valve_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """Schedules (non-empty), optionally of one valve, oldest first."""
        conn = self.get_connection()
        try:
            sql = "SELECT * FROM valve_cron WHERE TRIM(COALESCE(cron_expression, '')) != ''"
            args: tuple = ()
            if valve_id is not None:
                sql += ' AND valve_id = ?'
                args = (valve_id,)
            rows = conn.execute(sql + ' ORDER BY valve_id, id', args).fetchall()
            return [self._schedule_row(r) for r in rows]
        finally:
            conn.close()

    def get_schedule(self, schedule_id: int) -> Optional[Dict[str, Any]]:
        conn = self.get_connection()
        try:
            row = conn.execute('SELECT * FROM valve_cron WHERE id = ?', (schedule_id,)).fetchone()
            return self._schedule_row(row) if row else None
        finally:
            conn.close()

    def create_schedule(self, valve_id: int, cron_expression: str, duration: int, enabled: bool = True) -> int:
        conn = self.get_connection()
        try:
            cur = conn.execute(
                'INSERT INTO valve_cron (valve_id, cron_expression, enabled, duration) VALUES (?, ?, ?, ?)',
                (valve_id, cron_expression, bool(enabled), duration))
            conn.commit()
            logger.info("Schedule %s created: valve_id=%s, cron=%s, duration=%s, enabled=%s",
                        cur.lastrowid, valve_id, cron_expression, duration, enabled)
            return cur.lastrowid
        finally:
            conn.close()

    def update_schedule(self, schedule_id: int, cron_expression: Optional[str] = None,
                        duration: Optional[int] = None, enabled: Optional[bool] = None) -> bool:
        """Change some fields of a schedule; last_run is kept."""
        fields, args = [], []
        for column, value in (('cron_expression', cron_expression), ('duration', duration),
                              ('enabled', None if enabled is None else bool(enabled))):
            if value is not None:
                fields.append(f'{column} = ?')
                args.append(value)
        if not fields:
            return self.get_schedule(schedule_id) is not None
        conn = self.get_connection()
        try:
            cur = conn.execute(f"UPDATE valve_cron SET {', '.join(fields)} WHERE id = ?", (*args, schedule_id))
            conn.commit()
            logger.info("Schedule %s updated: %s", schedule_id, dict(zip(fields, args)))
            return cur.rowcount > 0
        finally:
            conn.close()

    def delete_schedule(self, schedule_id: int) -> bool:
        conn = self.get_connection()
        try:
            cur = conn.execute('DELETE FROM valve_cron WHERE id = ?', (schedule_id,))
            conn.commit()
            logger.info("Schedule %s deleted", schedule_id)
            return cur.rowcount > 0
        finally:
            conn.close()

    # ------------------------------------------------------------------ single-schedule API (legacy)
    # These act on the zone's first schedule; kept for older clients.
    def _first_schedule_id(self, valve_id: int) -> Optional[int]:
        conn = self.get_connection()
        try:
            row = conn.execute('SELECT id FROM valve_cron WHERE valve_id = ? ORDER BY id LIMIT 1',
                               (valve_id,)).fetchone()
            return row['id'] if row else None
        finally:
            conn.close()

    def update_valve_cron(self, valve_id: int, cron_expression: str, enabled: bool = True) -> bool:
        """Set the zone's first schedule; an empty expression deletes all its schedules."""
        try:
            if not (cron_expression or '').strip():
                conn = self.get_connection()
                try:
                    conn.execute('DELETE FROM valve_cron WHERE valve_id = ?', (valve_id,))
                    conn.commit()
                finally:
                    conn.close()
                logger.info("All schedules of valve %s deleted", valve_id)
                return True
            sid = self._first_schedule_id(valve_id)
            if sid is None:
                self.create_schedule(valve_id, cron_expression, None, enabled)
            else:
                self.update_schedule(sid, cron_expression=cron_expression, enabled=enabled)
            return True
        except Exception as e:
            logger.error(f"Failed to update valve cron: {e}")
            return False

    def get_valve_cron(self, valve_id: int) -> Optional[Dict[str, Any]]:
        """The zone's first schedule (or None)."""
        try:
            sid = self._first_schedule_id(valve_id)
            return self.get_schedule(sid) if sid is not None else None
        except Exception as e:
            logger.error(f"Failed to retrieve valve cron: {e}")
            return None

    def update_valve_cron_duration(self, valve_id: int, duration: int) -> bool:
        """Set the duration of the zone's first schedule."""
        try:
            sid = self._first_schedule_id(valve_id)
            if sid is None:
                self.create_schedule(valve_id, '', duration, False)
            else:
                self.update_schedule(sid, duration=duration)
            return True
        except Exception as e:
            logger.error(f"Failed to update valve cron duration: {e}")
            return False

    def get_all_valve_crons(self) -> List[Dict[str, Any]]:
        """All schedules of all valves."""
        try:
            return self.list_schedules()
        except Exception as e:
            logger.error(f"Failed to retrieve all valve crons: {e}")
            return []

    def update_system_config(self, config: Dict[str, Any]) -> bool:
        """
        Update system configuration settings.
        
        Args:
            config (Dict[str, Any]): Configuration settings to update
            {
                'api_key': str,
                'location': str,
                'default_duration': int,
                'weather_update_interval': int
            }
    
        Returns:
            bool: True if update was successful, False otherwise
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
    
            # Insert or update system config (assuming only one config record)
            cursor.execute('''
                INSERT OR REPLACE INTO system_config (id, api_key, location, default_duration, weather_update_interval)
                VALUES (1, ?, ?, ?, ?)
            ''', (
                config.get('api_key'),
                config.get('location'),
                config.get('default_duration'),
                config.get('weather_update_interval')
            ))
    
            conn.commit()
            conn.close()
            logger.info("System configuration updated successfully")
            return True
    
        except Exception as e:
            logger.error(f"Failed to update system configuration: {e}")
            return False
    
    def get_system_config(self) -> Optional[Dict[str, Any]]:
        """
        Retrieve current system configuration.
        
        Returns:
            Dict[str, Any]: System configuration settings or None if not found
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
       
            cursor.execute('''
                SELECT * FROM system_config WHERE id = 1
            ''')
       
            row = cursor.fetchone()
            conn.close()
       
            if row:
                return {
                    'id': row['id'],
                    'api_key': row['api_key'],
                    'location': row['location'],
                    'default_duration': row['default_duration'],
                    'weather_update_interval': row['weather_update_interval']
                }
       
            return None
       
        except Exception as e:
            logger.error(f"Failed to retrieve system configuration: {e}")
            return None
    
    def test_database_connection(self) -> bool:
        """
        Test if database connection is working properly.
        
        Returns:
            bool: True if connection is working, False otherwise
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute('SELECT 1')
            conn.close()
            logger.info("Database connection test successful")
            return True
        except Exception as e:
            logger.error(f"Database connection test failed: {e}")
            return False
    
    def create_session(self, session_id: str, user_id: int, ip_address: str, user_agent: str) -> bool:
        """
        Create a new user session.
        
        Args:
            session_id (str): Unique session identifier
            user_id (int): Reference to authenticated user
            ip_address (str): IP address of the client
            user_agent (str): User agent string
                
        Returns:
            bool: True if session creation was successful, False otherwise
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # Calculate expiration time (24 hours from now)
            expires_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            # For simplicity, we'll just store the current time as created_at and not implement expiration logic here
            # In a real system, you'd want to implement proper session expiration logic
            
            cursor.execute('''
                INSERT INTO sessions (session_id, user_id, created_at, expires_at, ip_address, user_agent)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (session_id, user_id, datetime.now(), expires_at, ip_address, user_agent))
            
            conn.commit()
            conn.close()
            logger.info(f"Session created: session_id={session_id}, user_id={user_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to create session: {e}")
            return False
    
    def validate_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Validate if a session is active and not expired.
        
        Args:
            session_id (str): Session identifier to validate
                
        Returns:
            Dict[str, Any]: Session data if valid, None if invalid or expired
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT * FROM sessions WHERE session_id = ?
            ''', (session_id,))
            
            row = cursor.fetchone()
            conn.close()
            
            if row:
                # In a real system, you'd check if the session has expired
                # For now, we'll just return the session data if it exists
                return {
                    'id': row['id'],
                    'session_id': row['session_id'],
                    'user_id': row['user_id'],
                    'created_at': row['created_at'],
                    'expires_at': row['expires_at'],
                    'ip_address': row['ip_address'],
                    'user_agent': row['user_agent']
                }
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to validate session: {e}")
            return None
    
    def delete_session(self, session_id: str) -> bool:
        """
        Remove a session from the database.
        
        Args:
            session_id (str): Session identifier to delete
     
        Returns:
            bool: True if deletion was successful, False otherwise
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
     
            cursor.execute('''
                DELETE FROM sessions WHERE session_id = ?
            ''', (session_id,))
     
            conn.commit()
            conn.close()
            logger.info(f"Session deleted: session_id={session_id}")
            return True
     
        except Exception as e:
            logger.error(f"Failed to delete session: {e}")
            return False
    
    def check_and_terminate_opened_records(self) -> int:
        """
        Check for records with status "Opened" and update them to "Terminated"
        with calculated duration.
        
        Returns:
            int: Number of records updated
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # Find all records with status "Opened"
            cursor.execute('''
                SELECT id, valve_id, status, timestamp, start_time
                FROM valve_logs
                WHERE status = 'Opened'
                ORDER BY timestamp ASC
            ''')
            
            opened_records = cursor.fetchall()
            updated_count = 0
            
            # Process each opened record
            for record in opened_records:
                log_id = record['id']
                valve_id = record['valve_id']
                start_time_str = record['start_time']
                
                if start_time_str:
                    # Calculate duration from start_time to now
                    import datetime
                    start_time = datetime.datetime.fromisoformat(start_time_str.replace('Z', '+00:00'))
                    end_time = datetime.datetime.now()
                    # The real end time is unknown (crash / power loss); the valve can
                    # never have been open longer than the safety limit.
                    duration = int((end_time - start_time).total_seconds())
                    duration = max(0, min(duration, MAX_VALVE_DURATION_SECONDS))
                    
                    # Update the record with "Terminated" status and duration
                    cursor.execute('''
                        UPDATE valve_logs
                        SET status = 'Terminated', duration = ?
                        WHERE id = ?
                    ''', (duration, log_id))
                    
                    updated_count += 1
                    logger.info(f"Updated record {log_id} for valve {valve_id}: duration = {duration} seconds")
                else:
                    # If no start_time, we can't calculate duration, so just update status
                    cursor.execute('''
                        UPDATE valve_logs
                        SET status = 'Terminated'
                        WHERE id = ?
                    ''', (log_id,))
                    
                    updated_count += 1
                    logger.info(f"Updated record {log_id} for valve {valve_id} to 'Terminated' (no duration)")
            
            conn.commit()
            conn.close()
            logger.info(f"Successfully updated {updated_count} 'Opened' records to 'Terminated'")
            return updated_count
            
        except Exception as e:
            logger.error(f"Failed to check and terminate opened records: {e}")
            return 0