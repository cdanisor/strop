# Raspberry Pi Irrigation Control System

An automated irrigation system that controls two solenoid valves via GPIO pins on a Raspberry Pi, using weather data to make intelligent watering decisions.

## Features
- Control two relays (GPIO23 and GPIO24) to operate solenoid valves
- Fetch weather data from OpenWeatherMap API (5-day forecast with 3-hour intervals)
- Store weather data and valve operation logs in SQLite database
- Intelligent irrigation scheduling based on 5-day weather forecast
- Web-based UI for monitoring and control
- Manual valve activation
- Configurable cron scheduling
- REST API for remote valve control
- Automatic weather data updates at startup and every 3 hours
- Weather data API endpoints for UI consumption
- 5-day weather forecast cards showing temperature for 3-hour intervals

## Hardware Requirements
- Raspberry Pi 1 (or compatible)
- 2-channel relay module
- 2 solenoid valves
- Jumper wires
- Power supply for solenoid valves

## Software Requirements
- Python 3.x
- Flask web framework
- RPi.GPIO library (for Raspberry Pi GPIO control)
- requests library (for API calls)
- sqlite3 (built-in Python library)
- schedule library (for task scheduling)
