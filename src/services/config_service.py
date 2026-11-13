"""
Configuration Service for Raspberry Pi Irrigation System
This service handles loading and managing system configuration.
"""

import json
import os
import re
from pathlib import Path
from typing import Optional, Dict, Any

# config.json lives in the project root; resolve it independently of the CWD
MAX_ZONES = 16
MAX_ZONE_ID = 99
# BCM numbers of the header GPIOs usable as outputs
VALID_PINS = range(2, 28)
DEFAULT_ZONES = {1: 23, 2: 24}


class ZoneConfigError(ValueError):
    """config.json describes the zones in a way that cannot be used safely."""


def _as_int(value, what):
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise ZoneConfigError(f"{what} must be a whole number, got {value!r}")
    try:
        return int(value)
    except ValueError:
        raise ZoneConfigError(f"{what} must be a whole number, got {value!r}")


def parse_zones(config: Dict[str, Any]) -> Dict[int, int]:
    """
    Zones from config.json as {zone id: BCM pin}, sorted by id.

    New format (any number of zones, edited by hand):
        "gpio": {"zones": [{"id": 1, "pin": 23}, {"id": 2, "pin": 24}, {"id": 3, "pin": 25}]}
    Old format (still read): "gpio": {"valve1_pin": 23, "valve2_pin": 24, ...}
    Without either, the two default zones (GPIO 23 and 24) are used.

    Raises ZoneConfigError for duplicate ids or pins, ids outside 1..99,
    pins outside 2..27 or more than MAX_ZONES zones, so a typo can never
    drive the wrong relay.
    """
    gpio = (config or {}).get('gpio') or {}
    if not isinstance(gpio, dict):
        raise ZoneConfigError("'gpio' must be an object")
    zones: Dict[int, int] = {}
    if 'zones' in gpio:
        items = gpio['zones']
        if not isinstance(items, list) or not items:
            raise ZoneConfigError("'gpio.zones' must be a non-empty list")
        for item in items:
            if not isinstance(item, dict) or 'id' not in item or 'pin' not in item:
                raise ZoneConfigError(f"each zone needs an 'id' and a 'pin', got {item!r}")
            zone_id = _as_int(item['id'], 'zone id')
            if zone_id in zones:
                raise ZoneConfigError(f"zone {zone_id} is defined twice")
            zones[zone_id] = _as_int(item['pin'], f'pin of zone {zone_id}')
    else:
        for key, value in gpio.items():
            m = re.fullmatch(r'valve(\d+)_pin', key)
            if m:
                zones[int(m.group(1))] = _as_int(value, key)
        if not zones:
            zones = dict(DEFAULT_ZONES)

    if len(zones) > MAX_ZONES:
        raise ZoneConfigError(f"at most {MAX_ZONES} zones are supported, got {len(zones)}")
    pins_seen = {}
    for zone_id, pin in zones.items():
        if not 1 <= zone_id <= MAX_ZONE_ID:
            raise ZoneConfigError(f"zone id {zone_id} must be between 1 and {MAX_ZONE_ID}")
        if pin not in VALID_PINS:
            raise ZoneConfigError(f"GPIO {pin} of zone {zone_id} is not a usable BCM pin (2-27)")
        if pin in pins_seen:
            raise ZoneConfigError(f"GPIO {pin} is used by zones {pins_seen[pin]} and {zone_id}")
        pins_seen[pin] = zone_id
    return dict(sorted(zones.items()))


DEFAULT_CONFIG_PATH = os.environ.get("STROP_CONFIG_PATH") or os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "config.json")

class ConfigService:
    """Service for managing system configuration."""
    
    def __init__(self, config_path: str = DEFAULT_CONFIG_PATH):
        """
        Initialize the configuration service.
        
        Args:
            config_path (str): Path to the configuration file
        """
        self.config_path = config_path
        self.config = self._load_config()
    
    def _load_config(self) -> Dict[str, Any]:
        """
        Load configuration from file.
        
        Returns:
            Dict[str, Any]: Configuration dictionary
        """
        # Check if config file exists
        if not os.path.exists(self.config_path):
            # Create default config file
            self._create_default_config()
            return self._load_config()
        
        try:
            with open(self.config_path, 'r') as f:
                config = json.load(f)
            return config
        except Exception as e:
            raise Exception(f"Failed to load configuration: {e}")
    
    def _create_default_config(self) -> None:
        """
        Create a default configuration file.
        """
        default_config = {
            "weather_api": {
                "api_key": "your_openweathermap_api_key_here",
                "location": "Bucharest, Romania",
                "latitude": 44.492831362490136,
                "longitude": 26.0459309519,
                "update_interval_minutes": 360
            },
            "gpio": {
                "zones": [{"id": zone_id, "pin": pin} for zone_id, pin in DEFAULT_ZONES.items()]
            },
            "system": {
                "default_duration_seconds": 30,
                "debug_mode": False
            }
        }
        
        with open(self.config_path, 'w') as f:
            json.dump(default_config, f, indent=4)
        
        print(f"Created default configuration file: {self.config_path}")
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        Get a configuration value by key.
        
        Args:
            key (str): Configuration key (e.g., 'weather_api.api_key')
            default (Any): Default value if key not found
            
        Returns:
            Any: Configuration value or default
        """
        keys = key.split('.')
        value = self.config
        
        try:
            for k in keys:
                value = value[k]
            return value
        except (KeyError, TypeError):
            return default
    
    def get_all(self) -> Dict[str, Any]:
        """
        Get all configuration values.
        
        Returns:
            Dict[str, Any]: Complete configuration dictionary
        """
        return self.config.copy()
    
    def update(self, key: str, value: Any) -> None:
        """
        Update a configuration value.
        
        Args:
            key (str): Configuration key to update
            value (Any): New value
        """
        keys = key.split('.')
        config = self.config
        
        # Navigate to the parent of the key
        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]
        
        # Set the value
        config[keys[-1]] = value
        
        # Save to file
        self._save_config()
    
    MAX_ZONE_NAME = 32

    def zones(self) -> Dict[int, int]:
        """Configured zones as {zone id: BCM pin} (see parse_zones)."""
        return parse_zones(self.config)

    def zone_ids(self) -> list:
        return list(self.zones())

    def has_zone(self, valve_id: int) -> bool:
        try:
            return valve_id in self.zones()
        except ZoneConfigError:
            return False

    def zone_names(self) -> Dict[str, str]:
        """Custom zone names, keyed by zone id as string ('1', '2', ...)."""
        names = self.config.get('zone_names') or {}
        return {str(k): str(v) for k, v in names.items() if v}

    def zone_name(self, valve_id: int) -> Optional[str]:
        return self.zone_names().get(str(valve_id))

    def set_zone_name(self, valve_id: int, name: Optional[str]) -> Optional[str]:
        """Set (or clear, with an empty name) a zone's name; returns the stored name."""
        name = ' '.join(str(name or '').split())[:self.MAX_ZONE_NAME]
        names = self.zone_names()
        if name:
            names[str(valve_id)] = name
        else:
            names.pop(str(valve_id), None)
        self.update('zone_names', names)
        return name or None

    def _save_config(self) -> None:
        """
        Save current configuration to file.
        """
        try:
            # Write atomically and keep it private: it holds the password hash
            tmp_path = self.config_path + '.tmp'
            with open(tmp_path, 'w') as f:
                json.dump(self.config, f, indent=4)
            try:
                os.chmod(tmp_path, 0o600)
            except OSError:
                pass
            os.replace(tmp_path, self.config_path)
        except Exception as e:
            raise Exception(f"Failed to save configuration: {e}")