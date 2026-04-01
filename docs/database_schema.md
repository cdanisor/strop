# Database Schema

## Database: irrigation_system.db

### Table: valve_logs
Stores logs of valve operations (when valves were turned on/off)

| Column Name | Data Type | Description |
|-------------|-----------|-------------|
| id | INTEGER | Primary key, auto-increment |
| valve_id | INTEGER | ID of the valve (1 or 2) |
| status | TEXT | Operation status ('on', 'off', 'Opened', 'Finished', 'Manually Stopped', 'Terminated') |
| start_time | DATETIME | When the operation started (for opened operations) |
| timestamp | DATETIME | When the operation occurred |
| duration | INTEGER | Duration of operation in seconds (optional) |

### Table: weather_data
Stores collected weather data

| Column Name | Data Type | Description |
|-------------|-----------|-------------|
| id | INTEGER | Primary key, auto-increment |
| timestamp | DATETIME | When the weather data was collected |
| date | DATE | Date for which the forecast is provided |
| temperature_minimum | REAL | Minimum temperature for the day in Celsius |
| temperature_maximum | REAL | Maximum temperature for the day in Celsius |
| average_humidity | INTEGER | Average humidity percentage for the day |
| average_pressure | INTEGER | Average atmospheric pressure for the day |
| description | TEXT | Weather description for the day |

### Table: valve_cron
Stores cron schedules for each valve

| Column Name | Data Type | Description |
|-------------|-----------|-------------|
| id | INTEGER | Primary key, auto-increment |
| valve_id | INTEGER | ID of the valve (1 or 2) |
| cron_expression | TEXT | Cron expression for scheduling |
| enabled | BOOLEAN | Whether the schedule is active |
| last_run | DATETIME | When the schedule last executed |
| next_run | DATETIME | When the schedule will next execute |

### Table: system_config
Stores system configuration settings

| Column Name | Data Type | Description |
|-------------|-----------|-------------|
| id | INTEGER | Primary key, auto-increment |
| api_key | TEXT | OpenWeatherMap API key |
| location | TEXT | Location for weather data |
| default_duration | INTEGER | Default manual activation duration in seconds |
| weather_update_interval | INTEGER | How often to fetch weather data in minutes |

### Table: sessions
Stores authenticated user sessions

| Column Name | Data Type | Description |
|-------------|-----------|-------------|
| id | INTEGER | Primary key, auto-increment |
| session_id | TEXT | Unique session identifier |
| user_id | INTEGER | Reference to authenticated user |
| created_at | DATETIME | Session creation timestamp |
| expires_at | DATETIME | Session expiration timestamp |
| ip_address | TEXT | IP address of the client |
| user_agent | TEXT | User agent string |