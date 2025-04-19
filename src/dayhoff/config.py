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
ALLOWED_EXECUTION_MODES = ['direct', 'slurm'] # New: Allowed modes for execution

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
            'execution_mode': 'direct', # New: 'direct' or 'slurm'
            'slurm_use_singularity': 'True', # New: Default to using singularity with slurm jobs
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
        # Initialize with defaults from DEFAULT_CONFIG['DEFAULT']
        self.config = configparser.ConfigParser(
            defaults=self.DEFAULT_CONFIG['DEFAULT'],
            inline_comment_prefixes=('#', ';'),
            interpolation=None,
            converters={'boolean': self._parse_boolean} # Add boolean converter
        )
        self.config_path = self._get_config_path(config_path_override)

        # Load existing or create default config
        self._load_or_create_config()

    def _parse_boolean(self, value: str) -> bool:
        """Custom boolean converter for configparser."""
        return value.lower() in ('true', 'yes', '1', 'on')

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
            # Read the file, which will overlay existing values over the defaults
            # already set during ConfigParser initialization.
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
        # Handle the special 'DEFAULT' section first by checking its keys
        default_section_key = 'DEFAULT'
        if default_section_key in self.DEFAULT_CONFIG:
            for key, value in self.DEFAULT_CONFIG[default_section_key].items():
                # Check if the key exists in the actual defaults of the parser
                if key not in self.config.defaults():
                    self.config.defaults()[key] = str(value)
                    needs_save = True
                    logger.info(f"Added missing default option: [DEFAULT] {key} = {value}")

        # Handle regular sections
        for section, defaults in self.DEFAULT_CONFIG.items():
            if section == default_section_key:
                continue # Skip the special DEFAULT section here

            if not self.config.has_section(section):
                # This is where the error occurred before. Now it only runs for non-DEFAULT sections.
                self.config.add_section(section)
                needs_save = True
                logger.info(f"Added missing default section: [{section}]")
                # Add all default keys for the new section
                for key, value in defaults.items():
                    self.config.set(section, key, str(value))
                    logger.info(f"Added default key for new section: [{section}] {key} = {value}")
            else:
                # Section exists, check if all default keys are present
                for key, value in defaults.items():
                    if not self.config.has_option(section, key):
                        self.config.set(section, key, str(value))
                        needs_save = True
                        logger.info(f"Added missing default key: [{section}] {key} = {value}")

        if needs_save:
            logger.info("Saving configuration file with added default options.")
            self.save_config()

    def _create_default_config(self):
        """Populates the ConfigParser object with default settings for non-DEFAULT sections."""
        # Defaults for the 'DEFAULT' section are already handled during initialization.
        # We only need to add the other sections and their default key-value pairs.
        for section, defaults in self.DEFAULT_CONFIG.items():
            if section == 'DEFAULT':
                continue # Skip DEFAULT section
            if not self.config.has_section(section):
                 self.config.add_section(section)
            for key, value in defaults.items():
                 # Set the default values for the non-DEFAULT sections
                 self.config.set(section, key, str(value))

        logger.info("Initialized non-DEFAULT sections with default configuration settings.")
        # Comments are not easily added when using read_dict or setting programmatically.
        # The structure itself should be clear.

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
        """Get a configuration value, utilizing configparser's fallback mechanism."""
        # configparser automatically falls back to the DEFAULT section if an option
        # is not found in the specified section.
        # The 'fallback' argument to config.get handles cases where the option
        # is not in the specified section OR the DEFAULT section.

        # We still need to handle the case where the section itself might not exist,
        # although _ensure_defaults should prevent this for default sections.
        if not self.config.has_section(section) and section != 'DEFAULT':
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

        # Use configparser's get method which handles DEFAULT fallback automatically.
        # Provide the explicit default value for cases where it's not found anywhere.
        value = self.config.get(section, key, fallback=default)

        # Expand user path for specific known path keys
        if value and isinstance(value, str):
            # Check if the key is one we need to expand, considering the section
            # or if it's a default value being retrieved (section might be 'DEFAULT' conceptually)
            original_section = section # Keep track of the requested section
            actual_section, actual_key = self._find_key_location(key) # Find where the key actually lives (could be DEFAULT)

            if actual_section: # Check if the key was found at all
                if (actual_section == 'DEFAULT' and actual_key == 'data_dir') or \
                   (actual_section == 'HPC' and actual_key in ['ssh_key_dir', 'known_hosts']):
                    expanded_value = str(Path(value).expanduser())
                    if expanded_value != value:
                        logger.debug(f"Expanded path for [{original_section}].{key} (found in [{actual_section}]): '{value}' -> '{expanded_value}'")
                    return expanded_value

        logger.debug(f"Config get [{section}].{key}: returning '{value}'")
        return value

    def getboolean(self, section: str, key: str, default: bool = False) -> bool:
        """Get a boolean configuration value."""
        # Use the custom boolean converter
        return self.config.getboolean(section, key, fallback=default)


    def _find_key_location(self, key_to_find: str) -> tuple[Optional[str], Optional[str]]:
        """Helper to find if a key exists in any section, starting from DEFAULT."""
        # Check DEFAULT first
        if key_to_find in self.config.defaults():
            return 'DEFAULT', key_to_find
        # Check other sections
        for section_name in self.config.sections():
            if self.config.has_option(section_name, key_to_find):
                return section_name, key_to_find
        return None, None


    def set(self, section: str, key: str, value: Any):
        """Set a configuration value and save."""
        # Do not allow setting values in the 'DEFAULT' section directly via this method
        # as it's meant for fallback defaults. Users should set specific section values.
        if section == 'DEFAULT':
             logger.error("Setting values directly in the 'DEFAULT' section is not supported via set(). Set values in specific sections.")
             raise ValueError("Cannot set values directly in the 'DEFAULT' section.")

        if not self.config.has_section(section):
            self.config.add_section(section)
            logger.info(f"Created new config section: [{section}]")

        str_value = str(value)

        # --- Validation ---
        validation_error = None
        # Note: Validation for 'DEFAULT' section keys is less critical here as we prevent setting them directly.
        # However, if loaded from a file, they might be invalid. Validation during 'get' might be needed if strictness is required.
        if section == 'HPC':
            if key == 'auth_method' and str_value not in ALLOWED_AUTH_METHODS:
                validation_error = f"Invalid auth_method '{str_value}'. Allowed: {', '.join(ALLOWED_AUTH_METHODS)}"
            if key == 'execution_mode' and str_value not in ALLOWED_EXECUTION_MODES: # New validation
                validation_error = f"Invalid execution_mode '{str_value}'. Allowed: {', '.join(ALLOWED_EXECUTION_MODES)}"
            if key == 'slurm_use_singularity': # New validation (check if boolean-like)
                 try:
                     self._parse_boolean(str_value)
                 except ValueError:
                     validation_error = f"Invalid boolean value for slurm_use_singularity: '{str_value}'. Use true/false, yes/no, 1/0."

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
                # execution_mode and slurm_use_singularity are retrieved via specific getters

                # Construct full path for ssh_key if using key auth
                if ssh_settings['auth_method'] == 'key' and ssh_settings['ssh_key_dir'] and ssh_settings['ssh_key']:
                    # ssh_key_dir should already be expanded by self.get
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
            # Attempt to return defaults if section is missing but defined in DEFAULT_CONFIG
            if section_name in self.DEFAULT_CONFIG:
                 logger.info(f"Returning default values for missing section [{section_name}]")
                 # Manually construct defaults, applying path expansion where needed
                 defaults = self.DEFAULT_CONFIG[section_name]
                 ssh_settings['host'] = defaults.get('default_host', '')
                 ssh_settings['username'] = defaults.get('username', '')
                 ssh_settings['auth_method'] = defaults.get('auth_method', 'key')
                 ssh_settings['ssh_key_dir'] = str(Path(defaults.get('ssh_key_dir', '~/.ssh')).expanduser())
                 ssh_settings['ssh_key'] = defaults.get('ssh_key', 'id_rsa')
                 ssh_settings['known_hosts'] = str(Path(defaults.get('known_hosts', '~/.ssh/known_hosts')).expanduser())
                 ssh_settings['remote_root'] = defaults.get('remote_root', '.')
                 ssh_settings['credential_system'] = defaults.get('credential_system', 'dayhoff_hpc')
                 if ssh_settings['auth_method'] == 'key' and ssh_settings['ssh_key_dir'] and ssh_settings['ssh_key']:
                     full_key_path = Path(ssh_settings['ssh_key_dir']) / ssh_settings['ssh_key']
                     ssh_settings['key_filename'] = str(full_key_path)
                 else:
                     ssh_settings['key_filename'] = None
                 return ssh_settings
            else:
                 return {} # Section not defined in defaults either

    def get_section(self, section_name: str) -> Optional[Dict[str, str]]:
        """Get all key-value pairs for a specific section, using self.get for consistency."""
        if section_name == 'DEFAULT':
            # Return the effective defaults
            logger.debug(f"Retrieving effective defaults for [DEFAULT] section.")
            # Use a temporary parser to get interpolated defaults if needed, or just return raw defaults
            # For simplicity, return the raw defaults stored in the parser
            # Convert values to string for consistency with other sections
            return {k: str(v) for k, v in self.config.defaults().items()}


        if not self.config.has_section(section_name):
            logger.warning(f"Configuration section [{section_name}] not found.")
            # Check if it's a default section and return its defaults if so
            if section_name in self.DEFAULT_CONFIG:
                 logger.info(f"Returning default values for missing section [{section_name}]")
                 # Apply path expansion to default values before returning
                 section_defaults = {}
                 for key, value in self.DEFAULT_CONFIG[section_name].items():
                     # Reuse the path expansion logic from get() if possible, or replicate it
                     str_value = str(value)
                     if (section_name == 'HPC' and key in ['ssh_key_dir', 'known_hosts']):
                         section_defaults[key] = str(Path(str_value).expanduser())
                     # Handle boolean conversion for display if needed, but get_section usually returns strings
                     # elif (section_name == 'HPC' and key == 'slurm_use_singularity'):
                     #     section_defaults[key] = str(self._parse_boolean(str_value)) # Return 'True' or 'False' string
                     else:
                         section_defaults[key] = str_value
                 return section_defaults
            else:
                 return None # Section not defined in defaults either

        try:
            # Iterate through keys in the section and use self.get to retrieve them
            # This ensures defaults and path expansions are handled correctly via fallback
            section_dict = {}
            # Need to get options defined *only* in this section + options falling back to DEFAULT
            # configparser section proxy includes defaults, so this is simpler:
            section_proxy = self.config[section_name]
            for key in section_proxy:
                 # Use self.get to ensure consistent value retrieval (like path expansion)
                 # For boolean values, use getboolean to show True/False consistently
                 if section_name == 'HPC' and key == 'slurm_use_singularity':
                     section_dict[key] = str(self.getboolean(section_name, key)) # Get boolean then convert back to string
                 else:
                     section_dict[key] = self.get(section_name, key) # Get potentially expanded string value

            # Ensure keys defined ONLY in DEFAULT are not included unless explicitly requested via get_section('DEFAULT')
            # The above loop correctly handles fallback, so section_dict contains the effective values for the section.

            logger.debug(f"Retrieved config section [{section_name}]: {section_dict}")
            return section_dict
        except Exception as e:
            logger.error(f"Error reading section [{section_name}] from config: {e}")
            return None

    def get_all_config(self) -> Dict[str, Dict[str, str]]:
        """Get all configuration sections and their key-value pairs."""
        all_config_dict = {}
        try:
            # Get the effective DEFAULTs first
            default_section_data = self.get_section('DEFAULT')
            if default_section_data is not None:
                all_config_dict['DEFAULT'] = default_section_data

            # Get all other sections
            for section_name in self.config.sections():
                 # Skip DEFAULT as we handled it above
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
        """Returns a list of available section names, including DEFAULT."""
        # configparser.sections() does not include DEFAULT
        sections = self.config.sections()
        # Explicitly add 'DEFAULT' as it's conceptually a section for defaults
        if 'DEFAULT' not in sections:
             sections.insert(0, 'DEFAULT')
        return sections

    def get_workflow_language(self) -> str:
        """Gets the configured default workflow language."""
        # Use self.get which handles fallback to DEFAULT section automatically
        language = self.get('WORKFLOWS', 'default_workflow_type', default='cwl')
        if language not in ALLOWED_WORKFLOW_LANGUAGES:
            # Find the default value from DEFAULT_CONFIG to fallback correctly
            default_lang = self.DEFAULT_CONFIG.get('WORKFLOWS', {}).get('default_workflow_type', 'cwl')
            logger.warning(f"Invalid workflow language '{language}' found in config ([WORKFLOWS].default_workflow_type). Falling back to default '{default_lang}'. Allowed: {', '.join(ALLOWED_WORKFLOW_LANGUAGES)}")
            language = default_lang
        return language

    def get_workflow_executor(self, language: str) -> Optional[str]:
        """Gets the configured default executor for a given workflow language."""
        if language not in ALLOWED_WORKFLOW_LANGUAGES:
            logger.error(f"Cannot get executor for unsupported language: {language}")
            return None

        config_key = get_executor_config_key(language)
        allowed_execs = ALLOWED_EXECUTORS.get(language, [])

        # Determine the ultimate default value from DEFAULT_CONFIG
        default_executor = self.DEFAULT_CONFIG.get('WORKFLOWS', {}).get(config_key)

        # Use self.get to retrieve the value, falling back to the default if necessary
        executor = self.get('WORKFLOWS', config_key, default=default_executor)

        # Validate against the allowed list for this language
        if executor not in allowed_execs:
            logger.warning(f"Invalid executor '{executor}' configured for language '{language}' ([WORKFLOWS].{config_key}). Falling back to default '{default_executor}'. Allowed: {', '.join(allowed_execs)}")
            executor = default_executor # Fallback to default from DEFAULT_CONFIG

        # Final check if default_executor itself was invalid (shouldn't happen with current setup)
        if executor not in allowed_execs:
             logger.error(f"Default executor '{executor}' for language '{language}' is invalid. Allowed: {', '.join(allowed_execs)}. Please check DEFAULT_CONFIG.")
             return None # Or raise an error

        logger.debug(f"Using executor '{executor}' for language '{language}'")
        return executor

    def get_llm_config(self) -> Dict[str, Optional[str]]:
        """Retrieves LLM configuration, checking environment variables for API key."""
        section_name = 'LLM'
        # Use self.get with defaults derived from DEFAULT_CONFIG
        default_provider = self.DEFAULT_CONFIG[section_name]['provider']
        default_api_key = self.DEFAULT_CONFIG[section_name]['api_key']
        default_model = self.DEFAULT_CONFIG[section_name]['model']
        default_base_url = self.DEFAULT_CONFIG[section_name]['base_url']

        provider = self.get(section_name, 'provider', default_provider)
        config_api_key = self.get(section_name, 'api_key', default_api_key)
        model = self.get(section_name, 'model', default_model)
        base_url = self.get(section_name, 'base_url', default_base_url)

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
            # Only warn if the provider actually requires a key (most do)
            if provider in LLM_API_KEY_ENV_VARS: # Check if we expect a key for this provider
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

    # --- New Getters for Execution Settings ---

    def get_execution_mode(self) -> str:
        """Gets the configured execution mode ('direct' or 'slurm')."""
        section = 'HPC'
        key = 'execution_mode'
        default_mode = self.DEFAULT_CONFIG.get(section, {}).get(key, 'direct')
        mode = self.get(section, key, default=default_mode)
        if mode not in ALLOWED_EXECUTION_MODES:
            logger.warning(f"Invalid execution mode '{mode}' found in config ([{section}].{key}). Falling back to default '{default_mode}'. Allowed: {', '.join(ALLOWED_EXECUTION_MODES)}")
            mode = default_mode
        return mode

    def get_slurm_use_singularity(self) -> bool:
        """Gets the configured preference for using Singularity with Slurm jobs."""
        section = 'HPC'
        key = 'slurm_use_singularity'
        # Get the default value string from DEFAULT_CONFIG and parse it
        default_value_str = self.DEFAULT_CONFIG.get(section, {}).get(key, 'True')
        default_value = self._parse_boolean(default_value_str)
        # Use getboolean which handles fallback and uses the converter
        return self.getboolean(section, key, default=default_value)


# Global config instance
# Initialize DayhoffConfig only once
# Ensure logger is configured before initializing config if config uses logging during init
# Basic logging config for bootstrap phase if needed:
# logging.basicConfig(level=logging.INFO)
config = DayhoffConfig()
