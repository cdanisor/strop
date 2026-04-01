# Cron Scheduling Logic

## Overview
The system will use cron scheduling to determine when to run irrigation decisions based on weather forecasts. The scheduling will be configurable through the web UI.

## Implementation Approach

### 1. Cron Expression Parsing
- Support standard cron expressions (5-field format: minute hour day month weekday)
- Parse expressions to determine next execution time
- Handle edge cases and invalid expressions

### 2. Decision Engine Integration
- Trigger weather data collection at scheduled intervals
- Analyze 5-day forecast data to make irrigation decisions
- Update valve cron schedules with next run times

### 3. Scheduling Components

#### Scheduler Class
- Manages all cron schedules
- Executes scheduled tasks
- Updates next run times
- Handles task queuing

#### Decision Maker Class
- Analyzes weather data for irrigation needs
- Makes decisions based on forecast
- Considers multiple weather factors:
  - Precipitation probability
  - Temperature trends
  - Humidity levels
  - Weather conditions

### 4. Scheduling Logic

#### Weather Update Schedule
- Default: Every 6 hours (configurable)
- Fetches current weather using `/data/2.5/weather` endpoint
- Fetches 5-day forecast using `/data/2.5/forecast` endpoint
- Stores data in database

#### Irrigation Decision Schedule
- Default: Daily (configurable)
- Analyzes forecast data
- Determines if irrigation is needed
- Sets valves to activate if needed

### 5. Decision Algorithm

#### Factors Considered
1. **Precipitation Probability**
   - If rain is forecasted in next 24-48 hours, skip irrigation
   - Consider intensity of precipitation

2. **Temperature Analysis**
   - High temperatures increase evaporation
   - May require more frequent irrigation

3. **Humidity Levels**
   - Low humidity increases water loss
   - May require more irrigation

4. **Weather Conditions**
   - Clear skies increase evaporation
   - Cloudy conditions reduce evaporation

#### Decision Process
1. Retrieve latest weather data
2. Analyze 5-day forecast for precipitation
3. Calculate irrigation needs based on factors
4. Update valve schedules accordingly
5. Log decision for audit trail

### 6. Implementation Details

#### Cron Expression Format
Support standard cron format:
```
* * * * * (minute hour day month weekday)
```

#### Example Schedules
- `0 6 * * *` - Run daily at 6:00 AM
- `0 0,12 * * *` - Run twice daily at midnight and noon
- `0 */6 * * *` - Run every 6 hours

#### Execution Flow
1. Scheduler checks all active cron jobs
2. If time matches, trigger weather data collection
3. Run decision algorithm
4. Update valve schedules
5. Log execution results

### 7. Error Handling
- Invalid cron expressions
- Failed weather API calls
- Database access errors
- Hardware control failures
- Time synchronization issues

### 8. Configuration
- Configurable schedule intervals
- Per-valve scheduling
- Enable/disable individual schedules
- Manual override capability