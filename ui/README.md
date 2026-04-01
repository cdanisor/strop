# Valve Control UI

A simple web-based user interface for controlling irrigation valves using jQuery and the existing API.

## Features

- Display status of two valves (Active/Inactive)
- Activate valves with optional duration
- Deactivate valves
- Refresh status manually
- Auto-refresh every 10 seconds
- Responsive design for different screen sizes

## Requirements

- Python 3.x
- jQuery (loaded from CDN)
- Running instance of the irrigation API server
- The system will run in simulation mode if GPIO hardware is not available

## Setup

1. Ensure the API server is running:
   ```bash
   python src/api_server.py
   ```

2. Start the UI server:
   ```bash
   python ui/server.py
   ```

3. Open your browser and navigate to:
   ```
   http://localhost:8000
   ```

## Usage

### Valve Controls

- **Activate Valve**: Click the "Activate" button to turn on a valve. Optionally enter a duration in seconds.
- **Deactivate Valve**: Click the "Deactivate" button to turn off a valve.
- **Refresh Status**: Click the "Refresh Status" button to manually update valve statuses.

### API Endpoints Used

- `GET /api/valves/status` - Get status of all valves
- `GET /api/valves/{valve_id}/status` - Get status of a specific valve
- `POST /api/valves/{valve_id}/activate` - Activate a valve
- `POST /api/valves/{valve_id}/deactivate` - Deactivate a valve

## File Structure

```
ui/
├── index.html          # Main HTML page
├── styles.css          # CSS styling
├── script.js           # jQuery JavaScript code
└── server.py           # Simple HTTP server for development
```

## Design Notes

- The UI uses a clean, modern design with responsive layout
- Status indicators change color based on valve state (green for active, red for inactive)
- Error messages are displayed when API calls fail
- Success messages confirm successful operations
- Duration input is optional for activation
- Auto-refresh keeps the UI in sync with the actual valve states