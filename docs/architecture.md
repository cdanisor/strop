# System Architecture

This document describes the architecture of the Raspberry Pi Irrigation Control System.

## Overview

The system is composed of several key components that work together to provide automated irrigation control:

1. Main Service - Coordinates all system components
2. GPIO Control Service - Handles relay operations for controlling solenoid valves
3. Configuration Service - Manages system configuration
4. API Service - Exposes valve control functionality through a REST API
5. Database Service - Stores weather data and valve operation logs

## Component Details

### Main Service
The main service is the central coordinator that initializes and manages all other services.

### GPIO Control Service
The GPIO control service handles relay operations for controlling solenoid valves via GPIO pins.

### Configuration Service
The configuration service handles loading and managing system configuration.

### API Service
The API service exposes valve control functionality through a REST API.

### Database Service
The database service stores weather data and valve operation logs in SQLite.

## File Structure

The system follows a modular file structure:

```
src/
├── api_server.py
├── main_service.py
├── api/
│   ├── api_service.py
├── core/
├── services/
│   ├── gpio_control_service.py
│   └── config_service.py
├── repositories/
├── models/
├── schemas/
└── README.md
```

Each service is implemented as a separate module to promote code reusability and maintainability.

## Component Interactions

The system components interact as follows:

1. The Main Service initializes all other services and coordinates their operation
2. The GPIO Control Service handles direct hardware interaction via Raspberry Pi GPIO pins
3. The Configuration Service loads system settings from configuration files
4. The API Service provides REST endpoints for external applications to control valves
5. The Database Service manages data persistence for weather information and valve logs

## Design Principles

- Separation of concerns: Each component has a specific responsibility
- Modularity: Services are organized into logical directories
- Reusability: Components can be used independently
- Maintainability: Clear directory structure and naming conventions