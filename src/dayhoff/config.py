import os
import configparser
from pathlib import Path
from typing import Dict, Any, Optional # Added Optional
import logging # Added logging

logger = logging.getLogger(__name__)

class DayhoffConfig:
    """Centralized configuration manager for Dayhoff system"""

    def __init__(self):
        self.config = configparser.ConfigParser()
        self.config_path = self._get_config_path()

        # Create default config if it doesn't exist
        if not self.config_path.exists():
            logger.info(f"Configuration file not found at {self.config_path}, creating default.")
            self._create_default_config()
        else:
            logger.info(f"Loading configuration from {self.config_path}")

        self.config.read(self.config_path)

    def _get_config_path(self) -> Path:
        """Get the path to the config file"""
        # Use environment variable if set, otherwise default location
        env_path = os.environ.get("DAYHOFF_CONFIG_PATH")
        if env_path:
            logger.debug(f"Using config path from DAYHOFF_CONFIG_PATH: {env_path}")
            return Path(env_path)
        else:
            config_dir = Path.home() / ".config" / "dayhoff"
            config_dir.mkdir(parents=True, exist_ok=True)
            default_path = config_dir / "dayhoff.cfg" # Changed extension to .cfg for consistency
            logger.debug(f"Using default config path: {default_path}")
            return default_path

    def _create_default_config(self):
        """Create default configuration file"""
        self.config['DEFAULT'] = {
            'log_level': 'INFO',
            'data_dir': str(Path.home() / 'dayhoff_data')
        }

        self.config['HPC'] = {
            'default_host': '', # Default to empty, user must fill in
            'username': '',     # Default to empty
            'auth_method': 'key', # Default to key-based auth
            'ssh_key_dir': str(Path.home() / '.ssh'),
            'ssh_key': 'id_rsa', # Default private key name
            'known_hosts': str(Path.home() / '.ssh' / 'known_hosts'),
            'remote_root': '.', # Default remote directory
            'credential_system': 'dayhoff_hpc' # Default service name for keyring
        }

        # Add other sections if needed
        # self.config['LLM'] = { ... }

        self.save_config()
        logger.info(f"Default configuration file created at {self.config_path}")

    def save_config(self):
        """Save the current configuration to file"""
        try:
            with open(self.config_path, 'w') as configfile:
                self.config.write(configfile)
            logger.debug(f"Configuration saved to {self.config_path}")
        except IOError as e:
            logger.error(f"Failed to save configuration file {self.config_path}: {e}")

    def get(self, section: str, key: str, default: Any = None) -> Any:
        """Get a configuration value"""
        # Use fallback mechanism for keys potentially in DEFAULT
        value = self.config.get(section, key, fallback=default)
        logger.debug(f"Config get [{section}].{key}: returning '{value}'")
        return value

    def set(self, section: str, key: str, value: Any):
        """Set a configuration value"""
        if section not in self.config:
            self.config[section] = {}
            logger.info(f"Created new config section: [{section}]")
        str_value = str(value)
        self.config[section][key] = str_value
        logger.info(f"Config set [{section}].{key} = {str_value}")
        self.save_config()

    def get_ssh_config(self) -> Dict[str, str]:
        """Get SSH-related configuration from the [HPC] section."""
        ssh_settings = {}
        section_name = 'HPC'
        if section_name in self.config:
            try:
                hpc_section = self.config[section_name]
                for key, value in hpc_section.items():
                    # Rename default_host to host for SSHManager compatibility
                    if key == 'default_host':
                        ssh_settings['host'] = value
                    else:
                        ssh_settings[key] = value
                logger.debug(f"Retrieved SSH config from [{section_name}]: {ssh_settings}")
            except Exception as e:
                logger.error(f"Error reading section [{section_name}] from config: {e}")
                # Return empty dict on error reading the section items
                return {}
        else:
            logger.warning(f"Configuration section [{section_name}] not found.")
            # Return empty dict if section doesn't exist
            return {}

        # Expand ~ in paths for convenience
        for key in ['ssh_key_dir', 'known_hosts', 'ssh_key']:
            if key in ssh_settings and ssh_settings[key].startswith('~'):
                ssh_settings[key] = os.path.expanduser(ssh_settings[key])
                logger.debug(f"Expanded path for {key}: {ssh_settings[key]}")

        # Construct full path for ssh_key if ssh_key_dir is present
        if 'ssh_key_dir' in ssh_settings and 'ssh_key' in ssh_settings and not os.path.isabs(ssh_settings['ssh_key']):
             full_key_path = os.path.join(ssh_settings['ssh_key_dir'], ssh_settings['ssh_key'])
             # Only update if the constructed path exists, otherwise keep original value
             # This allows specifying an absolute path directly in ssh_key
             if os.path.exists(full_key_path):
                 ssh_settings['ssh_key'] = full_key_path
                 logger.debug(f"Constructed full path for ssh_key: {ssh_settings['ssh_key']}")
             else:
                 logger.warning(f"Constructed SSH key path does not exist: {full_key_path}. Using original value: {ssh_settings['ssh_key']}")


        return ssh_settings

# Global config instance (consider if this is truly needed or if instances should be passed)
config = DayhoffConfig()
# Commenting out global instance for now - better to instantiate where needed
# to ensure latest config is loaded if file changes during runtime.
