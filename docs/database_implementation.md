# Database Implementation

## Database Module Structure

The database module will be implemented in `src/database.py` with the following structure:

### Class: Database

#### Constructor
- Initialize database connection
- Create required tables if they don't exist
- Set default configuration values

#### Methods

##### get_connection()
- Create and return a SQLite database connection
- Uses row_factory for named column access

##### init_database()
- Create all required tables:
  1. valve_logs - Stores valve operation logs
  2. weather_data - Stores weather data history
  3. valve_cron - Stores cron schedules for each valve
  4. system_config - Stores system configuration settings

##### insert_valve_log(valve_id, status, duration)
- Insert a new valve operation log entry
- Parameters:
  - valve_id: Integer (1 or 2)
  - status: String ('on', 'off', 'Opened', 'Finished', 'Manually Stopped', 'Terminated')
  - duration: Integer (optional, in seconds)

##### get_valve_logs(valve_id, limit)
- Retrieve valve operation logs
- Optional valve_id filter
- Limit results to specified number

##### insert_weather_data(weather_data)
- Insert weather data into database
- Parameters: Dictionary with weather metrics

##### get_latest_weather_data()
- Retrieve the most recent weather data entry

##### get_weather_data_history(limit)
- Retrieve weather data history

##### update_valve_cron(valve_id, cron_expression, enabled)
- Update cron schedule for a specific valve

##### get_valve_cron(valve_id)
- Retrieve cron schedule for a specific valve

##### get_all_valve_crons()
- Retrieve all valve cron schedules

##### update_system_config(config)
- Update system configuration settings

##### get_system_config()
- Retrieve current system configuration

##### create_session(session_id, user_id, ip_address, user_agent)
- Create a new user session
- Parameters:
  - session_id: String (unique session identifier)
  - user_id: Integer (authenticated user ID)
  - ip_address: String (client IP address)
  - user_agent: String (user agent string)

##### validate_session(session_id)
- Validate if a session is active and not expired
- Returns session data if valid, None if invalid or expired

##### delete_session(session_id)
- Remove a session from the database
- Parameters:
  - session_id: String (session identifier to delete)

## Database Schema Details

### valve_logs Table
| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key |
| valve_id | INTEGER | Valve identifier (1 or 2) |
| status | TEXT | Operation status ('on', 'off', 'Opened', 'Finished', 'Manually Stopped', 'Terminated') |
| timestamp | DATETIME | When operation occurred |
| duration | INTEGER | Duration in seconds (optional) |
| start_time | DATETIME | When operation started (for opened operations) |

### weather_data Table
| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key |
| timestamp | DATETIME | When data was collected |
| temperature | REAL | Temperature in Celsius |
| humidity | INTEGER | Humidity percentage |
| pressure | INTEGER | Atmospheric pressure in hPa |
| description | TEXT | Weather condition description |
| forecast_5day | TEXT | JSON string of 5-day forecast |

### valve_cron Table
| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key |
| valve_id | INTEGER | Valve identifier |
| cron_expression | TEXT | Cron schedule expression |
| enabled | BOOLEAN | Whether schedule is active |
| last_run | DATETIME | When schedule last executed |
| next_run | DATETIME | When schedule will next execute |

### system_config Table
| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key |
| api_key | TEXT | OpenWeatherMap API key |
| location | TEXT | Location for weather data |
| default_duration | INTEGER | Default manual activation duration |
| weather_update_interval | INTEGER | Weather update frequency in minutes |