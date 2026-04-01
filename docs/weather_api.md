# Weather API Integration

## API Provider
- OpenWeatherMap API (free tier available)

## API Endpoints

### Current Weather
- Endpoint: `https://api.openweathermap.org/data/2.5/weather`
- Parameters:
  - `q`: Location (Bucharest, Romania)
  - `appid`: API key
  - `units`: metric (for Celsius)

### 5-Day Forecast
- Endpoint: `https://api.openweathermap.org/data/2.5/forecast`
- Parameters:
  - `lat`: Latitude (required)
  - `lon`: Longitude (required)
  - `appid`: API key (required)
  - `units`: metric (for Celsius)
  - `mode`: json (default)
  - `cnt`: 40 (to get 5 days of 3-hour forecasts)
  - `lang`: en (for English descriptions)

## API Call Examples

### Using City Name (Current Weather)
```
https://api.openweathermap.org/data/2.5/weather?q=Bucharest, Romania&appid=YOUR_API_KEY&units=metric
```

### Using Geographic Coordinates (5-Day Forecast)
```
https://api.openweathermap.org/data/2.5/forecast?lat=44.492831362490136&lon=26.0459309519&appid=YOUR_API_KEY&units=metric&cnt=40
```

## Data Structure

### Current Weather Response
```json
{
  "main": {
    "temp": 22.5,
    "humidity": 65,
    "pressure": 1013
  },
  "weather": [
    {
      "description": "clear sky"
    }
  ]
}
```

### 5-Day Forecast Response
```json
{
  "cod": "200",
  "message": 0,
  "cnt": 40,
  "list": [
    {
      "dt": 1661871600,
      "main": {
        "temp": 296.76,
        "feels_like": 296.98,
        "temp_min": 296.76,
        "temp_max": 297.87,
        "pressure": 1015,
        "sea_level": 1015,
        "grnd_level": 933,
        "humidity": 69,
        "temp_kf": -1.11
      },
      "weather": [
        {
          "id": 500,
          "main": "Rain",
          "description": "light rain",
          "icon": "10d"
        }
      ],
      "clouds": {
        "all": 100
      },
      "wind": {
        "speed": 0.62,
        "deg": 349,
        "gust": 1.18
      },
      "visibility": 10000,
      "pop": 0.32,
      "rain": {
        "3h": 0.26
      },
      "sys": {
        "pod": "d"
      },
      "dt_txt": "2022-08-30 15:00:00"
    }
  ],
  "city": {
    "id": 3163858,
    "name": "Zocca",
    "coord": {
      "lat": 44.34,
      "lon": 10.99
    },
    "country": "IT",
    "population": 4593,
    "timezone": 7200,
    "sunrise": 1661834187,
    "sunset": 1661882248
  }
}
```

## API Response Fields

### Main Response Fields
- `cod`: Internal parameter
- `message`: Internal parameter
- `cnt`: Number of timestamps returned in the API response
- `list`: Array of forecast data points
- `city`: City information including coordinates, name, country, etc.

### List Item Fields (Forecast Data Points)
- `dt`: Time of data forecasted, unix, UTC
- `main`: Temperature and pressure data
  - `temp`: Temperature. Unit Default: Kelvin, Metric: Celsius, Imperial: Fahrenheit
  - `feels_like`: This temperature parameter accounts for the human perception of weather
  - `temp_min`: Minimum temperature at the moment of calculation
  - `temp_max`: Maximum temperature at the moment of calculation
  - `pressure`: Atmospheric pressure on the sea level by default, hPa
  - `sea_level`: Atmospheric pressure on the sea level, hPa
  - `grnd_level`: Atmospheric pressure on the ground level, hPa
  - `humidity`: Humidity, %
  - `temp_kf`: Internal parameter
- `weather`: Weather condition data
  - `id`: Weather condition id
  - `main`: Group of weather parameters (Rain, Snow, Clouds etc.)
  - `description`: Weather condition within the group
  - `icon`: Weather icon id
- `clouds`: Cloudiness data
  - `all`: Cloudiness, %
- `wind`: Wind data
  - `speed`: Wind speed. Unit Default: meter/sec, Metric: meter/sec, Imperial: miles/hour
  - `deg`: Wind direction, degrees (meteorological)
  - `gust`: Wind gust. Unit Default: meter/sec, Metric: meter/sec, Imperial: miles/hour
- `visibility`: Average visibility, metres. The maximum value of the visibility is 10km
- `pop`: Probability of precipitation (0-1)
- `rain`: Rain volume for last 3 hours, mm
- `snow`: Snow volume for last 3 hours, mm
- `sys`: Part of the day information
  - `pod`: Part of the day (n - night, d - day)
- `dt_txt`: Time of data forecasted, ISO, UTC

## Data Processing

### Weather Data Collection
- Fetch current weather data using city name or coordinates
- Fetch 5-day forecast data using geographic coordinates
- Store in database with timestamp
- Process forecast data to extract daily information

### Data Analysis for Irrigation Decisions
1. **Precipitation Probability**: Check if rain is forecasted in the next 5 days using `pop` field in forecast data
2. **Temperature**: High temperatures may increase irrigation needs
3. **Humidity**: Low humidity may increase evaporation
4. **Weather Conditions**: Clear skies may increase need for irrigation
5. **Wind Speed**: Strong winds may increase evaporation rates

## Implementation Details

### API Call Frequency
- Configurable interval (default: every 6 hours)
- Cache results to avoid excessive API calls
- Implement retry logic for failed requests

### Error Handling
- API rate limiting
- Network connectivity issues
- Invalid API key
- Invalid location data
- JSON parsing errors

### Data Storage
- Store raw API responses
- Store processed weather metrics
- Maintain historical weather data for trend analysis

### Rate Limiting
- Free OpenWeatherMap API has 60 calls/minute limit
- Implement proper throttling
- Cache data to minimize API calls

### Geographic Coordinates Implementation
- The system uses latitude and longitude coordinates from configuration for 5-day forecast API calls
- Current weather API can use either city name or coordinates
- Coordinates are more precise for accurate weather data