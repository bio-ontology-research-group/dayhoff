import os
import configparser
from pathlib import Path
from typing import Dict, Any, Optional, List # Added List
import logging # Added logging

logger = logging.getLogger(__name__)

# Define allowed workflow executors
ALLOWED_WORKFLOW_EXECUTORS = ['cwl', 'nextflow', 'snakemake', 'wdl']

class DayhoffConfig:
    """Centralized configuration manager for Dayhoff system"""

    def __init__(self):
        # Allow inline comments by specifying the comment prefix and inline_comment_prefixes
        # Note: configparser by default uses '#' and ';' as comment prefixes for *whole lines*.
        # Setting inline_comment_prefixes handles comments *after* values.
        self.config = configparser.ConfigParser(inline_comment_prefixes=('#', ';'))
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
        # Using RawConfigParser temporarily to write comments easily
        # Note: This doesn't affect reading, as the main self.config handles inline comments
        temp_config = configparser.RawConfigParser()

        temp_config['DEFAULT'] = {
            'log_level': 'INFO',
            'data_dir': str(Path.home() / 'dayhoff_data')
        }
        # Add comments for clarity in the default file
        temp_config.set('DEFAULT', '# Default logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)')
        temp_config.set('DEFAULT', '# Default directory for storing Dayhoff-related data')


        temp_config['HPC'] = {
            'default_host': '',     # Hostname or IP address of the HPC login node
            'username': '',         # Your username on the HPC
            'auth_method': 'key',   # Authentication method: 'key' or 'password'
            'ssh_key_dir': str(Path.home() / '.ssh'), # Directory containing SSH keys
            'ssh_key': 'id_rsa',    # Name of private key file in ssh_key_dir
            'known_hosts': str(Path.home() / '.ssh' / 'known_hosts'), # Path to known_hosts file
            'remote_root': '.',     # Default remote directory after login
            'credential_system': 'dayhoff_hpc' # Base service name for keyring storage
        }
        # Add comments for HPC section
        temp_config.set('HPC', '# --- HPC Connection Settings ---')
        temp_config.set('HPC', '# Hostname or IP address of the HPC login node')
        temp_config.set('HPC', '# Your username on the HPC')
        temp_config.set('HPC', '# Authentication method: \'key\' (recommended) or \'password\'')
        temp_config.set('HPC', '# Directory containing SSH keys (if auth_method is \'key\')')
        temp_config.set('HPC', '# Name of private key file in ssh_key_dir (e.g., id_rsa, id_ed25519)')
        temp_config.set('HPC', '# Path to your SSH known_hosts file (for host key verification)')
        temp_config.set('HPC', '# Default remote directory to change into after login (e.g., /scratch/user)')
        temp_config.set('HPC', '# Base service name used for storing/retrieving passwords via keyring')

        # Add WORKFLOWS section (plural)
        temp_config['WORKFLOWS'] = {
            'default_workflow_type': 'cwl' # Default workflow language/executor
        }
        # Add comments for WORKFLOWS section
        temp_config.set('WORKFLOWS', '# --- Workflow Settings ---')
        temp_config.set('WORKFLOWS', '# Preferred workflow language for generation.') # Updated comment
        temp_config.set('WORKFLOWS', f'# Allowed values: {", ".join(ALLOWED_WORKFLOW_EXECUTORS)}')


        # Add other sections if needed
        # temp_config['LLM'] = { ... }

        # Write the config with comments
        try:
            with open(self.config_path, 'w') as configfile:
                temp_config.write(configfile)
            logger.info(f"Default configuration file created at {self.config_path}")
        except IOError as e:
            logger.error(f"Failed to create default configuration file {self.config_path}: {e}")

        # Now, re-initialize the main config parser to read the file correctly
        self.config = configparser.ConfigParser(inline_comment_prefixes=('#', ';'))
        self.config.read(self.config_path)


    def save_config(self):
        """Save the current configuration to file"""
        # Note: Saving with configparser might strip comments depending on version/settings.
        # If preserving comments on save is critical, more complex handling is needed.
        try:
            with open(self.config_path, 'w') as configfile:
                self.config.write(configfile)
            logger.debug(f"Configuration saved to {self.config_path}")
        except IOError as e:
            logger.error(f"Failed to save configuration file {self.config_path}: {e}")

    def get(self, section: str, key: str, default: Any = None) -> Any:
        """Get a configuration value, stripping inline comments."""
        # Use fallback mechanism for keys potentially in DEFAULT
        # configparser with inline_comment_prefixes handles this automatically now.
        value = self.config.get(section, key, fallback=default)

        # # Manual stripping (no longer needed if inline_comment_prefixes works)
        # if isinstance(value, str):
        #     # Split at the first comment character and take the part before it
        #     comment_chars = ('#', ';') # Add others if needed
        #     for char in comment_chars:
        #         if char in value:
        #             value = value.split(char, 1)[0]
        #     value = value.strip() # Remove leading/trailing whitespace

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
        # Consider if saving immediately after every set is desired,
        # or if an explicit save command is better. Saving now.
        self.save_config()

    def get_ssh_config(self) -> Dict[str, str]:
        """Get SSH-related configuration from the [HPC] section."""
        ssh_settings = {}
        section_name = 'HPC'
        if section_name in self.config:
            try:
                hpc_section = self.config[section_name]
                # Iterate through keys available in the section
                for key in hpc_section:
                    # Use the 'get' method to ensure comments are stripped
                    value = self.get(section_name, key)
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
            if key in ssh_settings and isinstance(ssh_settings[key], str) and ssh_settings[key].startswith('~'):
                ssh_settings[key] = os.path.expanduser(ssh_settings[key])
                logger.debug(f"Expanded path for {key}: {ssh_settings[key]}")

        # Construct full path for ssh_key if ssh_key_dir is present
        if 'ssh_key_dir' in ssh_settings and 'ssh_key' in ssh_settings and isinstance(ssh_settings['ssh_key'], str) and not os.path.isabs(ssh_settings['ssh_key']):
             full_key_path = os.path.join(ssh_settings['ssh_key_dir'], ssh_settings['ssh_key'])
             # Only update if the constructed path exists, otherwise keep original value
             # This allows specifying an absolute path directly in ssh_key
             if os.path.exists(full_key_path):
                 ssh_settings['ssh_key'] = full_key_path
                 logger.debug(f"Constructed full path for ssh_key: {ssh_settings['ssh_key']}")
             else:
                 # Log clearly if the constructed path doesn't exist
                 logger.warning(f"Constructed SSH key path does not exist: '{full_key_path}'. Using original value: '{ssh_settings['ssh_key']}'")


        return ssh_settings

    def get_section(self, section_name: str) -> Optional[Dict[str, str]]:
        """Get all key-value pairs for a specific section."""
        if section_name not in self.config:
            logger.warning(f"Configuration section [{section_name}] not found.")
            return None
        try:
            # Use self.get() to ensure comments are stripped and defaults are handled (if applicable)
            section_dict = {key: self.get(section_name, key) for key in self.config[section_name]}
            logger.debug(f"Retrieved config section [{section_name}]: {section_dict}")
            return section_dict
        except Exception as e:
            logger.error(f"Error reading section [{section_name}] from config: {e}")
            return None

    def get_all_config(self) -> Dict[str, Dict[str, str]]:
        """Get all configuration sections and their key-value pairs."""
        all_config_dict = {}
        try:
            for section_name in self.config.sections():
                section_data = self.get_section(section_name)
                if section_data is not None:
                    all_config_dict[section_name] = section_data
            # Include DEFAULT section if needed (configparser treats it specially)
            if 'DEFAULT' in self.config:
                 default_section_data = {key: self.get('DEFAULT', key) for key in self.config['DEFAULT']}
                 if default_section_data:
                     # Decide where to put DEFAULT, maybe under its own key?
                     all_config_dict['DEFAULT'] = default_section_data

            logger.debug("Retrieved all config sections.")
            return all_config_dict
        except Exception as e:
            logger.error(f"Error reading all config sections: {e}")
            return {} # Return empty dict on error

    def get_available_sections(self) -> List[str]:
        """Returns a list of available section names."""
        return self.config.sections()

    # --- Updated Method ---
    def get_workflow_language(self) -> str:
        """Gets the configured workflow language."""
        # Read from section WORKFLOWS and key default_workflow_type
        language = self.get('WORKFLOWS', 'default_workflow_type', default='cwl')
        # Validate against allowed list, fallback to default if invalid value stored
        if language not in ALLOWED_WORKFLOW_EXECUTORS:
            logger.warning(f"Invalid workflow language '{language}' found in config ([WORKFLOWS].default_workflow_type). Falling back to default 'cwl'.")
            language = 'cwl'
        return language
    # --- End Updated Method ---


# Global config instance (consider if this is truly needed or if instances should be passed)
config = DayhoffConfig() # Instantiate the global config object
