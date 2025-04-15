import os
import configparser
from pathlib import Path
from typing import Dict, Any, Optional, List, Mapping # Added Mapping
import logging

logger = logging.getLogger(__name__)

# Define allowed workflow languages (renamed from EXECUTORS)
ALLOWED_WORKFLOW_LANGUAGES = ['cwl', 'nextflow', 'snakemake', 'wdl']

# Define allowed executors for each language (can be expanded)
ALLOWED_EXECUTORS: Mapping[str, List[str]] = {
    'cwl': ['cwltool', 'toil', 'cwl-runner', 'arvados-cwl-runner'],
    'nextflow': ['local', 'slurm', 'sge', 'lsf', 'pbs', 'awsbatch', 'google-lifesciences'], # Nextflow handles executors internally, this might represent profiles or config settings
    'snakemake': ['local', 'slurm', 'drmaa', 'kubernetes', 'google-lifesciences'],
    'wdl': ['cromwell', 'miniwdl', 'dxwdl'],
    # Add more as needed
}

# Helper function to generate the key for the default executor config setting
def get_executor_config_key(language: str) -> str:
    """Generates the config key for a language's default executor."""
    return f"{language}_default_executor"

class DayhoffConfig:
    """Centralized configuration manager for Dayhoff system"""

    def __init__(self):
        # Allow inline comments by specifying the comment prefix and inline_comment_prefixes
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
        env_path = os.environ.get("DAYHOFF_CONFIG_PATH")
        if env_path:
            logger.debug(f"Using config path from DAYHOFF_CONFIG_PATH: {env_path}")
            return Path(env_path)
        else:
            config_dir = Path.home() / ".config" / "dayhoff"
            config_dir.mkdir(parents=True, exist_ok=True)
            default_path = config_dir / "dayhoff.cfg"
            logger.debug(f"Using default config path: {default_path}")
            return default_path

    def _create_default_config(self):
        """Create default configuration file"""
        temp_config = configparser.RawConfigParser()

        temp_config['DEFAULT'] = {
            'log_level': 'INFO',
            'data_dir': str(Path.home() / 'dayhoff_data')
        }
        temp_config.set('DEFAULT', '# Default logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)')
        temp_config.set('DEFAULT', '# Default directory for storing Dayhoff-related data')

        temp_config['HPC'] = {
            'default_host': '',
            'username': '',
            'auth_method': 'key',
            'ssh_key_dir': str(Path.home() / '.ssh'),
            'ssh_key': 'id_rsa',
            'known_hosts': str(Path.home() / '.ssh' / 'known_hosts'),
            'remote_root': '.',
            'credential_system': 'dayhoff_hpc'
        }
        temp_config.set('HPC', '# --- HPC Connection Settings ---')
        temp_config.set('HPC', '# Hostname or IP address of the HPC login node')
        temp_config.set('HPC', '# Your username on the HPC')
        temp_config.set('HPC', '# Authentication method: \'key\' (recommended) or \'password\'')
        temp_config.set('HPC', '# Directory containing SSH keys (if auth_method is \'key\')')
        temp_config.set('HPC', '# Name of private key file in ssh_key_dir (e.g., id_rsa, id_ed25519)')
        temp_config.set('HPC', '# Path to your SSH known_hosts file (for host key verification)')
        temp_config.set('HPC', '# Default remote directory to change into after login (e.g., /scratch/user)')
        temp_config.set('HPC', '# Base service name used for storing/retrieving passwords via keyring')

        # --- WORKFLOWS section ---
        temp_config['WORKFLOWS'] = {
            'default_workflow_type': 'cwl', # Default workflow language
            # Add default executors for each language
            get_executor_config_key('cwl'): 'cwltool',
            get_executor_config_key('nextflow'): 'local',
            get_executor_config_key('snakemake'): 'local',
            get_executor_config_key('wdl'): 'cromwell',
        }
        temp_config.set('WORKFLOWS', '# --- Workflow Settings ---')
        temp_config.set('WORKFLOWS', '# Preferred workflow language for generation.')
        temp_config.set('WORKFLOWS', f'# Allowed languages: {", ".join(ALLOWED_WORKFLOW_LANGUAGES)}')
        # Add comments for executor settings
        for lang in ALLOWED_WORKFLOW_LANGUAGES:
            key = get_executor_config_key(lang)
            allowed_execs = ALLOWED_EXECUTORS.get(lang, [])
            temp_config.set('WORKFLOWS', f'# Default executor for {lang.upper()} workflows.')
            temp_config.set('WORKFLOWS', f'# Allowed values for {lang}: {", ".join(allowed_execs)}')
        # --- End WORKFLOWS section ---

        # Add other sections if needed
        # temp_config['LLM'] = { ... }

        try:
            with open(self.config_path, 'w') as configfile:
                temp_config.write(configfile)
            logger.info(f"Default configuration file created at {self.config_path}")
        except IOError as e:
            logger.error(f"Failed to create default configuration file {self.config_path}: {e}")

        # Re-initialize the main config parser
        self.config = configparser.ConfigParser(inline_comment_prefixes=('#', ';'))
        self.config.read(self.config_path)

    def save_config(self):
        """Save the current configuration to file"""
        try:
            with open(self.config_path, 'w') as configfile:
                self.config.write(configfile)
            logger.debug(f"Configuration saved to {self.config_path}")
        except IOError as e:
            logger.error(f"Failed to save configuration file {self.config_path}: {e}")

    def get(self, section: str, key: str, default: Any = None) -> Any:
        """Get a configuration value, stripping inline comments."""
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
                for key in hpc_section:
                    value = self.get(section_name, key)
                    if key == 'default_host':
                        ssh_settings['host'] = value
                    else:
                        ssh_settings[key] = value
                logger.debug(f"Retrieved SSH config from [{section_name}]: {ssh_settings}")
            except Exception as e:
                logger.error(f"Error reading section [{section_name}] from config: {e}")
                return {}
        else:
            logger.warning(f"Configuration section [{section_name}] not found.")
            return {}

        # Expand ~ in paths
        for key in ['ssh_key_dir', 'known_hosts', 'ssh_key']:
            if key in ssh_settings and isinstance(ssh_settings[key], str) and ssh_settings[key].startswith('~'):
                ssh_settings[key] = os.path.expanduser(ssh_settings[key])
                logger.debug(f"Expanded path for {key}: {ssh_settings[key]}")

        # Construct full path for ssh_key
        if 'ssh_key_dir' in ssh_settings and 'ssh_key' in ssh_settings and isinstance(ssh_settings['ssh_key'], str) and not os.path.isabs(ssh_settings['ssh_key']):
             full_key_path = os.path.join(ssh_settings['ssh_key_dir'], ssh_settings['ssh_key'])
             if os.path.exists(full_key_path):
                 ssh_settings['ssh_key'] = full_key_path
                 logger.debug(f"Constructed full path for ssh_key: {ssh_settings['ssh_key']}")
             else:
                 logger.warning(f"Constructed SSH key path does not exist: '{full_key_path}'. Using original value: '{ssh_settings['ssh_key']}'")

        return ssh_settings

    def get_section(self, section_name: str) -> Optional[Dict[str, str]]:
        """Get all key-value pairs for a specific section."""
        if section_name not in self.config:
            logger.warning(f"Configuration section [{section_name}] not found.")
            return None
        try:
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
            if 'DEFAULT' in self.config:
                 default_section_data = {key: self.get('DEFAULT', key) for key in self.config['DEFAULT']}
                 if default_section_data:
                     all_config_dict['DEFAULT'] = default_section_data

            logger.debug("Retrieved all config sections.")
            return all_config_dict
        except Exception as e:
            logger.error(f"Error reading all config sections: {e}")
            return {}

    def get_available_sections(self) -> List[str]:
        """Returns a list of available section names."""
        return self.config.sections()

    def get_workflow_language(self) -> str:
        """Gets the configured default workflow language."""
        language = self.get('WORKFLOWS', 'default_workflow_type', default='cwl')
        # Use renamed constant
        if language not in ALLOWED_WORKFLOW_LANGUAGES:
            logger.warning(f"Invalid workflow language '{language}' found in config ([WORKFLOWS].default_workflow_type). Falling back to default 'cwl'. Allowed: {', '.join(ALLOWED_WORKFLOW_LANGUAGES)}")
            language = 'cwl' # Default language
        return language

    # --- New Method ---
    def get_workflow_executor(self, language: str) -> Optional[str]:
        """Gets the configured default executor for a given workflow language."""
        if language not in ALLOWED_WORKFLOW_LANGUAGES:
            logger.error(f"Cannot get executor for unsupported language: {language}")
            return None

        config_key = get_executor_config_key(language)
        allowed_execs = ALLOWED_EXECUTORS.get(language, [])

        # Determine a sensible default if not found in config
        default_executor = None
        if language == 'cwl': default_executor = 'cwltool'
        elif language == 'nextflow': default_executor = 'local'
        elif language == 'snakemake': default_executor = 'local'
        elif language == 'wdl': default_executor = 'cromwell'
        # Add more defaults as needed

        executor = self.get('WORKFLOWS', config_key, default=default_executor)

        # Validate against the allowed list for this language
        if executor not in allowed_execs:
            logger.warning(f"Invalid executor '{executor}' configured for language '{language}' ([WORKFLOWS].{config_key}). Falling back to default '{default_executor}'. Allowed: {', '.join(allowed_execs)}")
            executor = default_executor # Fallback to default

        logger.debug(f"Using executor '{executor}' for language '{language}'")
        return executor
    # --- End New Method ---


# Global config instance
config = DayhoffConfig()
