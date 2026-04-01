# API Usage Documentation

## Weather Data Endpoints

### Get Weather History
```
GET /api/weather/history
```

Returns the history of weather data stored in the database.

**Response:**
```json
{
  "weather": [
    {
      "id": 1,
      "timestamp": "2026-03-31 15:30:00",
      "temperature": 18.5,
      "humidity": 75,
      "pressure": 1013,
      "description": "clear sky",
      "forecast_5day": "{...}",  // Full 5-day forecast JSON
      "current_weather": "{...}" // Current weather JSON
    }
  ]
}
```

### Get Weather Forecast
```
GET /api/weather/forecast
```

Returns the latest 5-day weather forecast data that was stored in the database. The forecast data contains 3-hour intervals for 5 days.

**Response:**
```json
{
  "forecast": {
    "city": {
      "name": "Bucharest",
      "country": "RO"
    },
    "list": [
      {
        "dt": 1609459200,
        "main": {
          "temp": 15.0,
          "humidity": 75,
          "pressure": 1013
        },
        "weather": [
          {
            "description": "clear sky"
          }
        ]
      }
    ]
  }
}
```

The `list` array contains weather data points for every 3 hours over the next 5 days. Each data point includes temperature, humidity, and weather description.

## Valve Control Endpoints

### Activate Valve
```
POST /api/valves/{valve_id}/activate
```

Activates a specific valve for a specified duration.

**Request Body:**
```json
{
  "duration": 60
}
```

**Response:**
```json
{
  "success": true,
  "message": "Valve 1 activated for 60 seconds"
}
```

### Deactivate Valve
```
POST /api/valves/{valve_id}/deactivate
```

Deactivates a specific valve.

**Response:**
```json
{
  "success": true,
  "message": "Valve 1 deactivated successfully"
}
```

### Get Valve Status
```
GET /api/valves/{valve_id}/status
```

Returns the status of a specific valve (true for active, false for inactive).

**Response:**
```json
{
  "valve_id": 1,
  "status": true
}
```

### Get All Valve Status
```
GET /api/valves/status
```

Returns the status of all valves.

**Response:**
```json
{
  "valves": {
    "1": true,
    "2": false
  }
}
```

### Get Valve History
```
GET /api/valves/{valve_id}/history
```

Returns the operation history for a specific valve (last 20 operations).

**Response:**
```json
{
  "valve_id": 1,
  "history": [
    {
      "id": 1,
      "valve_id": 1,
      "status": "Opened",
      "timestamp": "2026-03-31 15:30:00",
      "duration": 60,
      "start_time": "2026-03-31 15:30:00"
    }
  ]
}
```

### Get All Valve History
```
GET /api/valves/history
```

Returns the operation history for all valves (last 100 operations).

**Response:**
```json
{
  "valves": [
    {
      "id": 1,
      "valve_id": 1,
      "status": "Opened",
      "timestamp": "2026-03-31 15:30:00",
      "duration": 60,
      "start_time": "2026-03-31 15:30:00"
    }
  ]
}
```

## Health Check
```
GET /api/health
```

Returns the health status of the system. This endpoint is used for monitoring and system health checks.

**Response:**
```json
{
  "status": "healthy",
  "service": "irrigation-control-api"
}