# User Interface Design

## Overview
The web-based UI will be built using HTML, CSS, and jQuery with Bootstrap for responsive design. It will provide real-time monitoring, manual control, and configuration capabilities for the irrigation system.

## UI Structure

### Main Pages
1. Dashboard - Overview of system status
2. Valve Control - Manual valve activation and scheduling
3. Weather Data - View current and historical weather data
4. System Configuration - Configure system settings

## Dashboard Page

### Components
- System Status Panel
  - Current valve statuses (on/off)
  - Last weather update time
  - Next scheduled irrigation time
- Recent Valve Logs
  - Table showing last 10 valve operations
- Weather Summary
  - Current temperature, humidity, conditions
  - Next 5-day forecast summary

### Layout
- Responsive grid using Bootstrap
- Real-time status indicators (LED-style)
- Quick access buttons for manual control

## Valve Control Page

### Components
- Valve Status Cards
  - Visual indicator for each valve (on/off)
  - Last operation time
  - Next scheduled operation
- Manual Control Section
  - Buttons to activate valves manually
  - Duration selector (5 min default, configurable)
  - Immediate activation button
- Cron Schedule Editor
  - Form to edit cron expressions
  - Enable/disable toggle
  - Save button
  - Preview of next run time

### Features
- Real-time valve status updates
- Manual activation with duration control
- Configurable cron scheduling
- Visual feedback for all operations

## Weather Data Page

### Components
- Current Weather Display
  - Temperature, humidity, pressure
  - Weather conditions description
- 5-Day Forecast Table
  - Date, temperature, precipitation chance
- Weather History Chart
  - Line chart showing temperature/humidity trends
- Data Refresh Controls

## System Configuration Page

### Components
- API Key Management
  - Input field for OpenWeatherMap API key
  - Test connection button
- Location Settings
  - Location input field
- Default Settings
  - Default manual activation duration
  - Weather update interval
- Save Configuration Button

## Technical Implementation

### Frontend Technologies
- HTML5 for structure
- CSS3 with Bootstrap 5 for styling
- jQuery for DOM manipulation and AJAX calls
- Chart.js for data visualization (optional)
- Bootstrap CDN for responsive design

### UI Components
1. Status Cards - Visual indicators for valve states
2. Control Buttons - For manual valve activation
3. Data Tables - For logs and weather history
4. Forms - For configuration and cron editing
5. Modals - For confirmation dialogs and detailed views

### Responsive Design
- Mobile-first approach
- Bootstrap grid system for responsive layouts
- Touch-friendly controls for mobile devices
- Adaptive data tables

### AJAX Integration
- All UI interactions will be via AJAX calls to Flask endpoints
- Real-time updates using polling or WebSockets (if supported)
- Loading indicators during data operations
- Error handling and user feedback

## Key Features

### Real-time Monitoring
- Live valve status updates
- Automatic refresh of weather data
- Recent logs display

### Manual Control
- One-click valve activation
- Configurable duration
- Immediate activation option

### Scheduling Management
- Edit cron expressions
- Enable/disable schedules
- Preview next execution times

### Data Visualization
- Weather trend charts
- Valve operation history
- System performance metrics

### Configuration
- API key management
- Location settings
- System-wide defaults

## Security Considerations
- Input validation for all user inputs
- CSRF protection for forms
- Secure handling of API keys
- Authentication (if required)