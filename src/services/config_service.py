"""
Configuration Service for Raspberry Pi Irrigation System
This service handles loading and managing system configuration.
"""

import json
import os
from pathlib import Path
from typing import Dict, Any

# config.json lives in the project root; resolve it independently of the CWD
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
                "valve1_pin": 23,
                "valve2_pin": 24
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