import os
import configparser
from pathlib import Path
from typing import Dict, Any

class DayhoffConfig:
    """Centralized configuration manager for Dayhoff system"""
    
    def __init__(self):
        self.config = configparser.ConfigParser()
        self.config_path = self._get_config_path()
        
        # Create default config if it doesn't exist
        if not self.config_path.exists():
            self._create_default_config()
            
        self.config.read(self.config_path)
    
    def _get_config_path(self) -> Path:
        """Get the path to the config file"""
        config_dir = Path.home() / ".config" / "dayhoff"
        config_dir.mkdir(parents=True, exist_ok=True)
        return config_dir / "dayhoff.cfg"
    
    def _create_default_config(self):
        """Create default configuration file"""
        self.config['DEFAULT'] = {
            'log_level': 'INFO',
            'data_dir': str(Path.home() / 'dayhoff_data')
        }
        
        self.config['HPC'] = {
            'default_host': 'hpc.example.com',
            'ssh_key_dir': str(Path.home() / '.ssh'),
            'known_hosts': str(Path.home() / '.ssh' / 'known_hosts')
        }
        
        self.save_config()
    
    def save_config(self):
        """Save the current configuration to file"""
        with open(self.config_path, 'w') as configfile:
            self.config.write(configfile)
    
    def get(self, section: str, key: str, default: Any = None) -> Any:
        """Get a configuration value"""
        try:
            return self.config.get(section, key)
        except (configparser.NoSectionError, configparser.NoOptionError):
            return default
    
    def set(self, section: str, key: str, value: Any):
        """Set a configuration value"""
        if section not in self.config:
            self.config[section] = {}
        self.config[section][key] = str(value)
        self.save_config()
    
    def get_ssh_config(self) -> Dict[str, str]:
        """Get SSH-related configuration"""
        return {
            'ssh_key_dir': self.get('HPC', 'ssh_key_dir'),
            'known_hosts': self.get('HPC', 'known_hosts')
        }

# Global config instance
config = DayhoffConfig()
