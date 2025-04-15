import os
import configparser
from pathlib import Path
from typing import Dict, Any, Optional, List, Mapping # Added Mapping
import logging

logger = logging.getLogger(__name__)

# Define allowed values for configuration options
ALLOWED_LOG_LEVELS = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
ALLOWED_AUTH_METHODS = ['key', 'password']
ALLOWED_WORKFLOW_LANGUAGES = ['cwl', 'nextflow', 'snakemake', 'wdl']
ALLOWED_LLM_PROVIDERS = ['openai', 'anthropic', 'openrouter'] # Add more as needed

# Mapping from workflow language to allowed executor tools/platforms
ALLOWED_EXECUTORS: Mapping[str, List[str]] = {
    'cwl': ['cwltool', 'toil', 'cwl-runner', 'arvados-cwl-runner'],
    'nextflow': ['local', 'slurm', 'sge', 'lsf', 'pbs', 'awsbatch', 'google-lifesciences'], # Nextflow handles executors via profiles mostly
    'snakemake': ['local', 'slurm', 'drmaa', 'kubernetes', 'google-lifesciences'],
    'wdl': ['cromwell', 'miniwdl', 'dxwdl'],
    # Add more as needed
}

# Default base URLs for LLM providers (used if base_url is empty in config)
DEFAULT_LLM_BASE_URLS = {
    'openai': 'https://api.openai.com/v1',
    'anthropic': 'https://api.anthropic.com/v1', # Check Anthropic docs for exact URL
    'openrouter': 'https://openrouter.ai/api/v1',
}

# Environment variable names for API keys (checked if config value is missing)
LLM_API_KEY_ENV_VARS = {
    'openai': 'OPENAI_API_KEY',
    'anthropic': 'ANTHROPIC_API_KEY',
    'openrouter': 'OPENROUTER_API_KEY',
}


# Helper function to generate the key for the default executor config setting
def get_executor_config_key(language: str) -> str:
    """Generates the config key for a language's default executor."""
    return f"{language}_default_executor"

class DayhoffConfig:
    """Centralized configuration manager for Dayhoff system"""

    DEFAULT_CONFIG = {
        'DEFAULT': {
            'log_level': 'INFO',
            'data_dir': '~/dayhoff_data',
        },
        'HPC': {
            'default_host': '',
            'username': '',
            'auth_method': 'key',
            'ssh_key_dir': '~/.ssh',
            'ssh_key': 'id_rsa',
            'known_hosts': '~/.ssh/known_hosts',
            'remote_root': '.',
            'credential_system': 'dayhoff_hpc',
        },
        'WORKFLOWS': {
            'default_workflow_type': 'cwl',
            'cwl_default_executor': 'cwltool',
            'nextflow_default_executor': 'local',
            'snakemake_default_executor': 'local',
            'wdl_default_executor': 'cromwell',
        },
        'LLM': {
            'provider': 'openrouter',
            'api_key': '', # Recommend using environment variables instead
            'model': 'openrouter/auto',
            'base_url': '', # Will use provider defaults if empty
        }
    }

    def __init__(self, config_path_override: Optional[str] = None):
        # Allow inline comments by specifying the comment prefix and inline_comment_prefixes
        self.config = configparser.ConfigParser(inline_comment_prefixes=('#', ';'), interpolation=None)
        self.config_path = self._get_config_path(config_path_override)

        # Load existing or create default config
        self._load_or_create_config()

    def _get_config_path(self, config_path_override: Optional[str] = None) -> Path:
        """Determines the configuration file path, prioritizing override, then env var, then default."""
        if config_path_override:
            path = Path(config_path_override).expanduser()
            logger.debug(f"Using specified config path: {path}")
            return path
        elif 'DAYHOFF_CONFIG_PATH' in os.environ:
            path = Path(os.environ['DAYHOFF_CONFIG_PATH']).expanduser()
            logger.debug(f"Using config path from DAYHOFF_CONFIG_PATH: {path}")
            return path
        else:
            config_dir = Path.home() / ".config" / "dayhoff"
            config_dir.mkdir(parents=True, exist_ok=True) # Ensure directory exists
            default_path = config_dir / "dayhoff.cfg"
            logger.debug(f"Using default config path: {default_path}")
            return default_path

    def _load_or_create_config(self):
        """Loads the config file or creates it with defaults if it doesn't exist."""
        if self.config_path.exists():
            logger.info(f"Loading configuration from: {self.config_path}")
            self.config.read(self.config_path)
            # Ensure all default sections and keys exist after loading
            self._ensure_defaults()
        else:
            logger.warning(f"Configuration file not found at {self.config_path}. Creating default config.")
            self._create_default_config()
            self.save_config() # Save the newly created default config

    def _ensure_defaults(self):
        """Ensures that all default sections and keys exist in the loaded config."""
        needs_save = False
        for section, defaults in self.DEFAULT_CONFIG.items():
            if not self.config.has_section(section):
                self.config.add_section(section)
                needs_save = True
                logger.info(f"Added missing default section: [{section}]")
            for key, value in defaults.items():
                if not self.config.has_option(section, key):
                    self.config.set(section, key, str(value))
                    needs_save = True
                    logger.info(f"Added missing default key: [{section}] {key} = {value}")
        if needs_save:
            logger.info("Saving configuration file with added default options.")
            self.save_config()

    def _create_default_config(self):
        """Populates the ConfigParser object with default settings."""
        self.config.read_dict(self.DEFAULT_CONFIG)
        logger.info("Initialized with default configuration settings.")
        # Add comments for clarity when creating the file (optional but helpful)
        # This part is tricky with read_dict, might need manual section/key setting if comments are crucial on creation

    def save_config(self):
        """Save the current configuration to file"""
        try:
            # Ensure the parent directory exists before writing
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_path, 'w') as configfile:
                self.config.write(configfile)
            logger.debug(f"Configuration saved to {self.config_path}")
        except IOError as e:
            logger.error(f"Failed to save configuration file {self.config_path}: {e}")

    def get(self, section: str, key: str, default: Any = None) -> Any:
        """Get a configuration value, stripping inline comments."""
        # Ensure section exists before getting to avoid NoSectionError if defaults weren't loaded properly
        if not self.config.has_section(section):
            # Check if it's a default section that should exist
            if section in self.DEFAULT_CONFIG:
                 logger.warning(f"Config section [{section}] was missing, attempting recovery.")
                 self._ensure_defaults() # Try to recover defaults
                 if not self.config.has_section(section): # Still missing?
                      logger.error(f"Config section [{section}] not found even after recovery attempt.")
                      return default
            else:
                 logger.warning(f"Config section [{section}] not found.")
                 return default

        value = self.config.get(section, key, fallback=default)

        # Expand user path for specific known path keys
        if value and isinstance(value, str):
            if (section == 'DEFAULT' and key == 'data_dir') or \
               (section == 'HPC' and key in ['ssh_key_dir', 'known_hosts']):
                expanded_value = str(Path(value).expanduser())
                if expanded_value != value:
                    logger.debug(f"Expanded path for [{section}].{key}: '{value}' -> '{expanded_value}'")
                return expanded_value

        logger.debug(f"Config get [{section}].{key}: returning '{value}'")
        return value

    def set(self, section: str, key: str, value: Any):
        """Set a configuration value and save."""
        if not self.config.has_section(section):
            self.config.add_section(section)
            logger.info(f"Created new config section: [{section}]")

        str_value = str(value)

        # --- Validation ---
        validation_error = None
        if section == 'DEFAULT':
            if key == 'log_level' and str_value not in ALLOWED_LOG_LEVELS:
                validation_error = f"Invalid log_level '{str_value}'. Allowed: {', '.join(ALLOWED_LOG_LEVELS)}"
        elif section == 'HPC':
            if key == 'auth_method' and str_value not in ALLOWED_AUTH_METHODS:
                validation_error = f"Invalid auth_method '{str_value}'. Allowed: {', '.join(ALLOWED_AUTH_METHODS)}"
        elif section == 'WORKFLOWS':
            if key == 'default_workflow_type' and str_value not in ALLOWED_WORKFLOW_LANGUAGES:
                validation_error = f"Invalid default_workflow_type '{str_value}'. Allowed: {', '.join(ALLOWED_WORKFLOW_LANGUAGES)}"
            elif key.endswith('_default_executor'):
                lang = key.replace('_default_executor', '')
                if lang in ALLOWED_EXECUTORS and str_value not in ALLOWED_EXECUTORS[lang]:
                    validation_error = f"Invalid executor '{str_value}' for {lang}. Allowed: {', '.join(ALLOWED_EXECUTORS[lang])}"
        elif section == 'LLM':
             if key == 'provider' and str_value not in ALLOWED_LLM_PROVIDERS:
                 validation_error = f"Invalid provider '{str_value}'. Allowed: {', '.join(ALLOWED_LLM_PROVIDERS)}"
        # Add more validation as needed

        if validation_error:
            logger.error(f"Config set validation failed for [{section}].{key}: {validation_error}")
            raise ValueError(validation_error)
        # --- End Validation ---

        self.config[section][key] = str_value
        logger.info(f"Config set [{section}].{key} = {str_value}")
        self.save_config() # Save after successful set

    def get_ssh_config(self) -> Dict[str, str]:
        """Get SSH-related configuration from the [HPC] section."""
        ssh_settings = {}
        section_name = 'HPC'
        if self.config.has_section(section_name):
            try:
                # Use self.get to handle path expansion and defaults correctly
                ssh_settings['host'] = self.get(section_name, 'default_host', '')
                ssh_settings['username'] = self.get(section_name, 'username', '')
                ssh_settings['auth_method'] = self.get(section_name, 'auth_method', 'key')
                ssh_settings['ssh_key_dir'] = self.get(section_name, 'ssh_key_dir', '~/.ssh') # Expanded by get
                ssh_settings['ssh_key'] = self.get(section_name, 'ssh_key', 'id_rsa') # Just the name
                ssh_settings['known_hosts'] = self.get(section_name, 'known_hosts', '~/.ssh/known_hosts') # Expanded by get
                ssh_settings['remote_root'] = self.get(section_name, 'remote_root', '.')
                ssh_settings['credential_system'] = self.get(section_name, 'credential_system', 'dayhoff_hpc')

                # Construct full path for ssh_key if using key auth
                if ssh_settings['auth_method'] == 'key' and ssh_settings['ssh_key_dir'] and ssh_settings['ssh_key']:
                    full_key_path = Path(ssh_settings['ssh_key_dir']) / ssh_settings['ssh_key']
                    # Store the full path for the SSHManager
                    ssh_settings['key_filename'] = str(full_key_path)
                    logger.debug(f"Constructed full path for ssh_key: {ssh_settings['key_filename']}")
                else:
                    ssh_settings['key_filename'] = None


                logger.debug(f"Retrieved SSH config from [{section_name}]: {ssh_settings}")
                return ssh_settings
            except Exception as e:
                logger.error(f"Error reading section [{section_name}] from config: {e}")
                return {}
        else:
            logger.warning(f"Configuration section [{section_name}] not found.")
            return {}

    def get_section(self, section_name: str) -> Optional[Dict[str, str]]:
        """Get all key-value pairs for a specific section, using self.get for consistency."""
        if not self.config.has_section(section_name):
            logger.warning(f"Configuration section [{section_name}] not found.")
            return None
        try:
            # Iterate through keys in the section and use self.get to retrieve them
            # This ensures defaults and path expansions are handled
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
            # Include DEFAULT section explicitly if it exists
            if 'DEFAULT' in self.config:
                 default_section_data = self.get_section('DEFAULT')
                 if default_section_data is not None:
                     all_config_dict['DEFAULT'] = default_section_data

            for section_name in self.config.sections():
                 # Skip DEFAULT as it might be handled differently by configparser sometimes
                 # and we already added it if it exists.
                 if section_name == 'DEFAULT': continue

                 section_data = self.get_section(section_name)
                 if section_data is not None:
                    all_config_dict[section_name] = section_data

            logger.debug("Retrieved all config sections.")
            return all_config_dict
        except Exception as e:
            logger.error(f"Error reading all config sections: {e}")
            return {}

    def get_available_sections(self) -> List[str]:
        """Returns a list of available section names."""
        # Ensure DEFAULT is included if present
        sections = self.config.sections()
        if 'DEFAULT' in self.config and 'DEFAULT' not in sections:
             sections.insert(0, 'DEFAULT')
        return sections

    def get_workflow_language(self) -> str:
        """Gets the configured default workflow language."""
        language = self.get('WORKFLOWS', 'default_workflow_type', default='cwl')
        if language not in ALLOWED_WORKFLOW_LANGUAGES:
            logger.warning(f"Invalid workflow language '{language}' found in config ([WORKFLOWS].default_workflow_type). Falling back to default 'cwl'. Allowed: {', '.join(ALLOWED_WORKFLOW_LANGUAGES)}")
            language = 'cwl' # Default language
        return language

    def get_workflow_executor(self, language: str) -> Optional[str]:
        """Gets the configured default executor for a given workflow language."""
        if language not in ALLOWED_WORKFLOW_LANGUAGES:
            logger.error(f"Cannot get executor for unsupported language: {language}")
            return None

        config_key = get_executor_config_key(language)
        allowed_execs = ALLOWED_EXECUTORS.get(language, [])

        # Determine a sensible default if not found in config or if invalid
        default_executor = self.DEFAULT_CONFIG['WORKFLOWS'].get(config_key)

        executor = self.get('WORKFLOWS', config_key, default=default_executor)

        # Validate against the allowed list for this language
        if executor not in allowed_execs:
            logger.warning(f"Invalid executor '{executor}' configured for language '{language}' ([WORKFLOWS].{config_key}). Falling back to default '{default_executor}'. Allowed: {', '.join(allowed_execs)}")
            executor = default_executor # Fallback to default

        logger.debug(f"Using executor '{executor}' for language '{language}'")
        return executor

    def get_llm_config(self) -> Dict[str, Optional[str]]:
        """Retrieves LLM configuration, checking environment variables for API key."""
        section_name = 'LLM'
        # Use self.get with defaults from DEFAULT_CONFIG
        provider = self.get(section_name, 'provider', self.DEFAULT_CONFIG[section_name]['provider'])
        config_api_key = self.get(section_name, 'api_key', self.DEFAULT_CONFIG[section_name]['api_key'])
        model = self.get(section_name, 'model', self.DEFAULT_CONFIG[section_name]['model'])
        base_url = self.get(section_name, 'base_url', self.DEFAULT_CONFIG[section_name]['base_url'])

        # Determine final API key: prioritize environment variable, then config
        api_key = None
        env_var_name = LLM_API_KEY_ENV_VARS.get(provider)
        if env_var_name and env_var_name in os.environ:
            api_key = os.environ[env_var_name]
            logger.info(f"Using LLM API key from environment variable {env_var_name}")
        elif config_api_key:
            api_key = config_api_key
            logger.info(f"Using LLM API key from config file [{section_name}].api_key")
        else:
            logger.warning(f"LLM API key not found in config section [{section_name}] key 'api_key' or environment variable {env_var_name}")

        # Determine final base URL: use config value if set, otherwise use provider default
        final_base_url = base_url
        if not final_base_url and provider in DEFAULT_LLM_BASE_URLS:
            final_base_url = DEFAULT_LLM_BASE_URLS[provider]
            logger.debug(f"Using default base URL for {provider}: {final_base_url}")

        return {
            'provider': provider,
            'api_key': api_key, # Will be None if not found anywhere
            'model': model,
            'base_url': final_base_url or None, # Return None if still empty
        }


# Global config instance
config = DayhoffConfig()
