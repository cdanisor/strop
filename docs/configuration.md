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
    "valve1_pin": 23,
    "valve2_pin": 24
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

### GPIO Configuration
- `valve1_pin`: GPIO pin number for valve 1 (default: 23)
- `valve2_pin`: GPIO pin number for valve 2 (default: 24)

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
    "valve1_pin": 23,
    "valve2_pin": 24
  },
  "system": {
    "default_duration_seconds": 30,
    "debug_mode": false
  }
}