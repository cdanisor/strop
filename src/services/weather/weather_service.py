"""
Weather Service for Raspberry Pi Irrigation System
This service handles fetching and storing weather data from OpenWeather API.
"""
import requests
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from src.database import Database
from src.services.config_service import ConfigService

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class WeatherService:
    """Service for managing weather data from OpenWeather API."""
    
    def __init__(self):
        """Initialize the weather service."""
        self.config_service = ConfigService()
        self.db = Database()
        self.api_key = self.config_service.get('weather_api.api_key', '')
        self.location = self.config_service.get('weather_api.location', 'Bucharest, Romania')
        self.latitude = self.config_service.get('weather_api.latitude', 44.439663)
        self.longitude = self.config_service.get('weather_api.longitude', 26.096306)
        self.update_interval_minutes = self.config_service.get('weather_api.update_interval_minutes', 360)
        self.base_url = "http://api.openweathermap.org/data/2.5/forecast"
    
    def fetch_5day_forecast(self) -> Optional[Dict[str, Any]]:
        """
        Fetch 5-day forecast data from OpenWeather API.
        
        Returns:
            Dict[str, Any]: Forecast data or None if failed
        """
        try:
            # Prepare the API request parameters
            params = {
                'lat': self.latitude,
                'lon': self.longitude,
                'appid': self.api_key,
                'units': 'metric',  # Use Celsius
                'cnt': 40  # 40 data points = 5 days (3-hour intervals)
            }
            
            # Make the API request
            response = requests.get(self.base_url, params=params, timeout=10)
            response.raise_for_status()  # Raise an exception for bad status codes
            
            data = response.json()
            logger.info("Successfully fetched 5-day forecast data")
            return data
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to fetch weather data from API: {e}")
            return None
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse weather data JSON: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error fetching weather data: {e}")
            return None
    
    def store_weather_data(self, forecast_data: Dict[str, Any]) -> bool:
        """
        Store weather forecast data in the database, avoiding duplicates.
        Updates existing records that were written earlier.
        
        Args:
            forecast_data (Dict[str, Any]): Raw forecast data from API
        
        Returns:
            bool: True if storage was successful, False otherwise
        """
        try:
            # Process the forecast data to extract relevant information
            daily_forecast_data = self._process_forecast_data(forecast_data)
        
            if daily_forecast_data:
                # Store each day's forecast data
                for day_data in daily_forecast_data:
                    # Insert or update weather data in database
                    result = self.db.insert_weather_data(day_data)
                    if not result:
                        logger.error("Failed to store one day of weather data")
                        return False
                # Log the dates that were stored
                date_list = [day['date'] for day in daily_forecast_data]
                logger.info(f"Weather data stored successfully for dates: {', '.join(date_list)}")
                return True
            else:
                logger.warning("No valid weather data to store")
                return False
       
        except Exception as e:
            logger.error(f"Failed to store weather data: {e}")
            return False
    
    def _process_forecast_data(self, forecast_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Process raw forecast data into daily forecast data for storage.
        
        Args:
            forecast_data (Dict[str, Any]): Raw forecast data from API
        
        Returns:
            List[Dict[str, Any]]: Processed daily weather data ready for storage
        """
        try:
            # Process forecast data to group by day and calculate min/max temperatures
            daily_forecast = self._group_forecast_by_day(forecast_data)
            
            logger.info(f"Processed forecast data: {len(daily_forecast)} days")
            for day in daily_forecast:
                logger.info(f"Day data: {day}")
        
            # Return forecast data for the next 5 days (including today)
            if daily_forecast:
                # Return all daily forecast data (up to 5 days)
                return daily_forecast
            else:
                # Fallback to current weather data
                current_weather = forecast_data.get('list', [{}])[0] if forecast_data.get('list') else {}
                result = [{
                    'date': datetime.now().strftime('%Y-%m-%d'),
                    'temperature_minimum': current_weather.get('main', {}).get('temp'),
                    'temperature_maximum': current_weather.get('main', {}).get('temp'),
                    'average_humidity': current_weather.get('main', {}).get('humidity'),
                    'average_pressure': current_weather.get('main', {}).get('pressure'),
                    'description': current_weather.get('weather', [{}])[0].get('description', '')
                }]
                logger.info(f"Fallback weather data: {result}")
                return result
        except Exception as e:
            logger.error(f"Failed to process weather data: {e}")
            return []
    
    def _group_forecast_by_day(self, forecast_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Group 3-hourly forecast data by day and calculate min/max temperatures.
        
        Args:
            forecast_data (Dict[str, Any]): Raw forecast data from API
            
        Returns:
            List[Dict[str, Any]]: Processed daily forecast data
        """
        try:
            daily_data = {}
        
            # Get list of forecast items
            forecast_list = forecast_data.get('list', [])
        
            # Group by date
            for item in forecast_list:
                # Convert timestamp to date
                timestamp = item.get('dt', 0)
                item_date = datetime.fromtimestamp(timestamp)
                date_key = item_date.strftime('%Y-%m-%d')
      
                # Get temperature, humidity and pressure from main section
                main_data = item.get('main', {})
                temp = main_data.get('temp')
                humidity = main_data.get('humidity')
                pressure = main_data.get('pressure')
                temp_min = main_data.get('temp_min')
                temp_max = main_data.get('temp_max')
      
                # Get rain data
                rain_data = item.get('rain', {})
                rain_3h = rain_data.get('3h', 0)  # Rain volume for last 3 hours, mm
                
                # Initialize daily data if not exists
                if date_key not in daily_data:
                    daily_data[date_key] = {
                        'date': date_key,
                        'min_temp': temp_min if temp_min is not None else temp,
                        'max_temp': temp_max if temp_max is not None else temp,
                        'weather': [],
                        'total_humidity': 0,
                        'total_pressure': 0,
                        'count': 0,
                        'total_temp': 0,
                        'total_rain': 0
                    }
                else:
                    # Update min/max temperatures
                    if temp_min is not None:
                        daily_data[date_key]['min_temp'] = min(daily_data[date_key]['min_temp'], temp_min)
                    if temp_max is not None:
                        daily_data[date_key]['max_temp'] = max(daily_data[date_key]['max_temp'], temp_max)
      
                # Add to totals for averaging
                if humidity is not None:
                    daily_data[date_key]['total_humidity'] += humidity
                    daily_data[date_key]['count'] += 1
                if pressure is not None:
                    daily_data[date_key]['total_pressure'] += pressure
                    daily_data[date_key]['count'] += 1
                if temp is not None:
                    daily_data[date_key]['total_temp'] += temp
                    
                # Add rain data
                daily_data[date_key]['total_rain'] += rain_3h
      
                # Add weather description for this time slot
                weather_desc = item.get('weather', [{}])[0].get('description', '')
                daily_data[date_key]['weather'].append({
                    'time': item_date.strftime('%H:%M'),
                    'temp': temp,
                    'description': weather_desc
                })
        
            # Calculate averages and convert to list
            result = []
            for date_key, data in daily_data.items():
                avg_humidity = data['total_humidity'] // data['count'] if data['count'] > 0 else 0
                avg_pressure = data['total_pressure'] // data['count'] if data['count'] > 0 else 0
                avg_temp = data['total_temp'] / data['count'] if data['count'] > 0 else data['min_temp']
        
                result.append({
                    'date': data['date'],
                    'temperature_minimum': data['min_temp'],
                    'temperature_maximum': data['max_temp'],
                    'average_humidity': avg_humidity,
                    'average_pressure': avg_pressure,
                    'description': data['weather'][0]['description'] if data['weather'] else '',
                    'total_rain': data['total_rain']
                })
        
            # Sort by date
            result.sort(key=lambda x: x['date'])
            return result
        except Exception as e:
            logger.error(f"Failed to group forecast by day: {e}")
            return []
    
    def update_weather_data(self) -> bool:
        """
        Fetch and store weather data from OpenWeather API.
        This method is called at startup and every 3 hours as requested.
        
        Returns:
            bool: True if update was successful, False otherwise
        """
        logger.info("Updating weather data from OpenWeather API")
        
        # Fetch the forecast data
        forecast_data = self.fetch_5day_forecast()
        if not forecast_data:
            logger.error("Failed to fetch weather forecast data")
            return False
        
        # Store the data in database
        success = self.store_weather_data(forecast_data)
        if success:
            logger.info("Weather data updated successfully")
        else:
            logger.error("Failed to store weather data")
        
        return success