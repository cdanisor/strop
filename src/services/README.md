# Services Directory

This directory contains all the service modules for the Raspberry Pi Irrigation Control System.

## Services

### GPIO Control Service (`gpio_control.py`)
This service handles all GPIO operations for controlling the relay module that operates the solenoid valves.

**Key Features:**
- Initialize GPIO pins for relay control
- Activate/deactivate valves with optional duration
- Get status of individual valves or all valves
- Graceful cleanup of GPIO resources
- Error handling for GPIO operations
- **Simulation mode support** - Works on Windows without actual GPIO hardware

**Functions:**
- `activate_valve(valve_id, duration=None)` - Activate specified valve
- `deactivate_valve(valve_id)` - Deactivate specified valve
- `get_valve_status(valve_id)` - Get status of specified valve
- `get_all_valve_status()` - Get status of all valves
- `cleanup()` - Cleanup GPIO resources

### Configuration Service (`config_service.py`)
This service handles loading and managing system configuration.

**Key Features:**
- Load configuration from JSON file
- Create default configuration if file doesn't exist
- Get configuration values by key
- Update configuration values
- Save configuration to file

**Functions:**
- `get(key, default=None)` - Get configuration value by key
- `get_all()` - Get all configuration values
- `update(key, value)` - Update configuration value

### Main Service (`main_service.py`)
This is the main coordinator service that integrates all other services.

**Key Features:**
- Initialize and coordinate all system components
- Provide unified interface for valve operations
- Handle system cleanup and shutdown
- Graceful handling of system signals

**Functions:**
- `initialize()` - Initialize all services
- `activate_valve(valve_id, duration)` - Activate specified valve
- `deactivate_valve(valve_id)` - Deactivate specified valve
- `get_valve_status(valve_id)` - Get status of specified valve
- `get_all_valve_status()` - Get status of all valves
- `cleanup()` - Cleanup all resources

## Simulation Mode

The GPIO Control Service supports simulation mode, which allows testing and development on Windows systems without actual Raspberry Pi hardware. When running on a system without RPi.GPIO library installed, the service automatically switches to simulation mode and logs actions instead of sending signals to GPIO pins.