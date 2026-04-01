# Enhanced Decision Algorithm Implementation Plan

## Overview
This document outlines the implementation details for enhancing the irrigation decision algorithm to incorporate historical irrigation duration data and weather trends (temperature and humidity) from recent and upcoming days.

## Algorithm Enhancement Details

### 1. Historical Irrigation Duration Analysis

#### Data Retrieval
- Query `valve_logs` table for irrigation history
- Retrieve logs for last 7 days (configurable time window)
- Group logs by valve ID and date
- Calculate average duration per valve for recent periods

#### Analysis Logic
- If valves have been active recently (within last 3 days), soil may be moist
- If valves have been inactive recently (more than 3 days), soil may be dry
- Adjust irrigation recommendation based on recent usage patterns
- Consider duration of previous irrigation sessions to estimate soil moisture

#### Scoring Calculation
- Historical duration score = (Recent usage frequency × 0.5) + (Average duration × 0.5)
- If recent usage > 2 times in 3 days: Score = 70-100 (lower irrigation need)
- If recent usage < 1 time in 3 days: Score = 0-30 (higher irrigation need)
- If recent usage = 1-2 times in 3 days: Score = 30-70 (moderate irrigation need)

### 2. Weather Trends Analysis

#### Data Retrieval
- Query `weather_data` table for historical weather data
- Retrieve data for last 7 days (configurable time window)
- Extract temperature, humidity, and precipitation data

#### Trend Analysis Logic
- Calculate daily averages for temperature and humidity over recent period
- Determine trend direction (increasing, decreasing, stable)
- Analyze precipitation patterns over recent days
- Compare current conditions with historical averages

#### Scoring Calculation
- Temperature trend score:
  - Increasing trend: Lower irrigation score (0-30)
  - Decreasing trend: Higher irrigation score (70-100)
  - Stable trend: Moderate irrigation score (30-70)
- Humidity trend score:
  - Decreasing trend: Higher irrigation score (70-100)
  - Increasing trend: Lower irrigation score (0-30)
  - Stable trend: Moderate irrigation score (30-70)
- Precipitation trend score:
  - Recent precipitation > 5mm: Lower irrigation score (0-30)
  - Recent precipitation < 2mm: Higher irrigation score (70-100)
  - No recent precipitation: Moderate irrigation score (30-70)

### 3. Integration with Existing Algorithm

#### Weighted Scoring System
The enhanced algorithm will use the following weights:
- Precipitation probability: 30%
- Temperature: 15%
- Humidity: 15%
- Weather conditions: 15%
- Historical irrigation duration: 15%
- Weather trends: 10%

#### Decision Thresholds
- Score < 25: Irrigation highly recommended
- Score 25-50: Irrigation recommended with caution
- Score > 50: Irrigation not recommended

### 4. Implementation Components

#### Class Structure
```python
class EnhancedWeatherAnalyzer:
    def __init__(self, db_connection):
        self.db = db_connection
        self.config = self.load_config()
    
    def analyze_historical_irrigation(self, valve_id, days_back=7):
        """Analyze irrigation duration history for a specific valve"""
        # Implementation details here
        pass
    
    def analyze_weather_trends(self, days_back=7):
        """Analyze temperature and humidity trends"""
        # Implementation details here
        pass
    
    def calculate_enhanced_score(self, weather_data, valve_id):
        """Calculate final irrigation score with enhanced factors"""
        # Implementation details here
        pass
    
    def make_decision(self, weather_data, valve_id):
        """Make final irrigation decision"""
        # Implementation details here
        pass
```

#### Data Access Methods
```python
def get_valve_logs_history(self, valve_id, days_back=7):
    """Retrieve irrigation logs for specified valve and time period"""
    # SQL query to get logs from valve_logs table
    pass

def get_weather_history(self, days_back=7):
    """Retrieve weather data for specified time period"""
    # SQL query to get data from weather_data table
    pass
```

### 5. Configuration Options

#### New Configuration Parameters
- `historical_duration_days`: Number of days to consider for irrigation history (default: 7)
- `weather_trend_days`: Number of days to consider for weather trends (default: 7)
- `irrigation_frequency_threshold`: Minimum frequency of irrigation to consider soil moist (default: 2 times/3 days)
- `trend_sensitivity`: Sensitivity for trend analysis (default: 0.5)

### 6. Error Handling and Edge Cases

#### Data Availability
- If historical irrigation data is missing, use default duration values
- If weather data is incomplete, use conservative estimates
- If database connection fails, use cached data or default values

#### Data Quality
- Filter out invalid or corrupted data points
- Apply smoothing techniques to reduce noise in trend analysis
- Handle missing data points gracefully

### 7. Performance Considerations

#### Database Optimization
- Create indexes on `valve_logs.timestamp` and `weather_data.timestamp` for faster queries
- Cache frequently accessed historical data
- Implement pagination for large datasets

#### Processing Efficiency
- Pre-calculate trends during data collection rather than on-the-fly
- Use efficient data structures for trend analysis
- Implement parallel processing where possible

### 8. Testing Strategy

#### Unit Tests
- Test historical irrigation analysis with various data scenarios
- Test weather trend analysis with different trend patterns
- Test scoring calculations with edge cases

#### Integration Tests
- Test full decision-making process with mock data
- Test database integration with real data
- Test error handling scenarios

### 9. Logging and Monitoring

#### Decision Logs
- Log all factors used in decision calculation
- Include historical data points used in analysis
- Track confidence levels for each decision
- Store decision outcomes for performance monitoring

#### Performance Metrics
- Track processing time for each analysis component
- Monitor database query performance
- Log error rates and recovery scenarios