# System Configuration

The system uses a JSON configuration file to store settings that should not be changed from the UI. This includes API keys, hardware pin configurations, and system-level settings.

## Configuration File Structure

### Configuration File Location
- Primary configuration: `config.json`
- Example configuration: `config.example.json`

### Configuration Schema

```json
{
  "weather_api": {
    "api_key": "your_openweathermap_api_key_here",
    "location": "Bucharest, Romania",
    "latitude": 44.492831362490136,
    "longitude": 26.0459309519,
    "update_interval_minutes": 360
  },
  "gpio": {
    "zones": [
      {"id": 1, "pin": 23},
      {"id": 2, "pin": 24}
    ]
  },
  "system": {
    "default_duration_seconds": 30,
    "debug_mode": false
  }
}
```

## Configuration Sections

### Weather API Configuration
- `api_key`: OpenWeatherMap API key for weather data
- `location`: Location for weather data (default: Bucharest, Romania)
- `update_interval_minutes`: How often to fetch weather data in minutes

### GPIO Configuration (zones)
`gpio.zones` lists the irrigation zones, each with its `id` and the relay's
GPIO `pin` (BCM numbering, 2-27). Add or remove zones only by editing
`config.json`, then restart the API (`sudo systemctl restart strop-api`); the
UI and Home Assistant pick the new list up on their own.

```json
"gpio": {
  "zones": [
    {"id": 1, "pin": 23},
    {"id": 2, "pin": 24},
    {"id": 3, "pin": 25}
  ]
}
```

- Up to 16 zones, ids 1-99. Ids and pins must be unique; otherwise the API
  refuses to start (see `journalctl -u strop-api`) instead of driving the
  wrong relay.
- Removing a zone keeps its history and schedules in the database (they are
  simply not run); adding the same id back restores them. Home Assistant
  deletes the entities of removed zones.
- Zone names are set from the UI (stored under `zone_names`).
- Older configs with `valve1_pin`, `valve2_pin`, ... keep working.

### System Configuration
- `default_duration_seconds`: Default manual activation duration in seconds
- `debug_mode`: Enable/disable debug logging

## File Structure

The system follows a modular file structure:

```
src/
├── api/
│   ├── api_server.py
│   └── api_service.py
├── core/
│   └── main_service.py
├── services/
│   ├── gpio_control_service.py
│   └── config_service.py
├── repositories/
├── models/
├── schemas/
└── README.md
````

Each service is implemented as a separate module to promote code reusability and maintainability.

## Session Management

For authenticated sessions, the system will store session information in the database with the following structure:

### Sessions Table
| Column Name | Data Type | Description |
|-------------|-----------|-------------|
| id | INTEGER | Primary key |
| session_id | TEXT | Unique session identifier |
| user_id | INTEGER | Reference to authenticated user |
| created_at | DATETIME | Session creation timestamp |
| expires_at | DATETIME | Session expiration timestamp |
| ip_address | TEXT | IP address of the client |
| user_agent | TEXT | User agent string |

### Session Flow

1. **Authentication**: Users provide credentials (username/password) to authenticate
2. **Session Creation**: Upon successful authentication, a unique session ID is generated
3. **Session Storage**: Session data is stored in the database with expiration time
4. **Session Validation**: Each request includes session ID in headers/cookies for validation
5. **Session Expiration**: Sessions automatically expire after a configured time period (e.g., 24 hours)
6. **Session Cleanup**: Expired sessions are periodically cleaned up from the database

### Session Security Considerations

- Session IDs should be cryptographically secure random strings
- Sessions should be invalidated upon logout
- IP address binding can be used for additional security (optional)
- User agent binding can be used for additional security (optional)
- Sessions should automatically expire after a reasonable time period

### Session Validation Process

When a request is received:
1. Extract session ID from request headers or cookies
2. Query database for session with matching ID
3. Check if session is still valid (not expired)
4. If valid, allow access to requested resource
5. If invalid or expired, return authentication required error

## Example Configuration File

```json
{
  "weather_api": {
    "api_key": "your_openweathermap_api_key_here",
    "location": "Bucharest, Romania",
    "update_interval_minutes": 360
  },
  "gpio": {
    "zones": [
      {"id": 1, "pin": 23},
      {"id": 2, "pin": 24}
    ]
  },
  "system": {
    "default_duration_seconds": 30,
    "debug_mode": false
  }
}
## Weather-based watering adjustment

Scheduled runs are shortened (never lengthened) or skipped based on
temperature, humidity and rain (past two days, the run day and the next two
days). The method is an adaptation of the Zimmerman method used by
OpenSprinkler; see `src/services/watering_adjustment.py` for the formula.
Manual runs are never adjusted.

All keys are optional; the defaults are shown:

```json
"watering_adjustment": {
    "enabled": true,
    "base_temp": 22.0,
    "base_humidity": 55.0,
    "temp_pct_per_c": 3.6,
    "humidity_pct_per_pct": 1.0,
    "rain_pct_per_mm": 7.87,
    "rain_weights": {"-2": 0.5, "-1": 1.0, "0": 1.0, "1": 0.5, "2": 0.25},
    "freeze_temp": 2.0,
    "cold_temp": 8.0,
    "min_percent": 20.0,
    "min_run_seconds": 60
}
```

- `base_temp` / `base_humidity`: the day for which the programmed time is right
  (100 %). Raise `base_temp` if the lawn gets too little water in spring.
- `rain_pct_per_mm`: 7.87 % per mm means about 12.7 mm (half an inch) of
  effective rain cancels a run.
- Runs are skipped when the run day's minimum is at or below `freeze_temp`,
  when the mean temperature is below `cold_temp`, or when less than
  `min_percent` / `min_run_seconds` would remain.
