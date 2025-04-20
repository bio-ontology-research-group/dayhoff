import json
import logging
import argparse
from typing import List, Optional, TYPE_CHECKING

from rich.panel import Panel

if TYPE_CHECKING:
    from ..service import DayhoffService # Import DayhoffService for type hinting

logger = logging.getLogger(__name__)

# --- Config Handler ---
def handle_config(service: 'DayhoffService', args: List[str]) -> Optional[str]:
    """Handles the /config command with subparsers. Prints output directly."""
    parser = service._create_parser( # Use helper from service instance
        "config",
        service._command_map['config']['help'], # Access help text from service
        add_help=True
    )
    subparsers = parser.add_subparsers(dest="subcommand", title="Subcommands",
                                       description="Valid subcommands for /config",
                                       help="Action to perform on the configuration")
    # subparsers.required = True # Make subcommand mandatory

    # --- Subparser: get ---
    parser_get = subparsers.add_parser("get", help="Get a specific config value.", add_help=True)
    parser_get.add_argument("section", help="Configuration section name (e.g., HPC, LLM)")
    parser_get.add_argument("key", help="Configuration key name")
    parser_get.add_argument("default", nargs='?', default=None, help="Optional default value if key not found")

    # --- Subparser: set ---
    parser_set = subparsers.add_parser("set", help="Set a config value (and save).", add_help=True)
    parser_set.add_argument("section", help="Configuration section name")
    parser_set.add_argument("key", help="Configuration key name")
    parser_set.add_argument("value", help="Value to set")

    # --- Subparser: save ---
    parser_save = subparsers.add_parser("save", help="Manually save the current configuration.", add_help=True)

    # --- Subparser: show ---
    parser_show = subparsers.add_parser("show", help="Show config sections.", add_help=True)
    # Updated help text in _build_command_map reflects 'hpc' option
    parser_show.add_argument("section", nargs='?', default=None, help="Section name (e.g., HPC, LLM, ssh, all) or omit for all.")

    # --- Subparser: slurm_singularity ---
    parser_slurm_singularity = subparsers.add_parser("slurm_singularity", help="Enable/disable default Singularity use for Slurm jobs.", add_help=True)
    parser_slurm_singularity.add_argument("state", choices=['on', 'off'], help="Set default Singularity usage to 'on' or 'off'.")


    # --- Parse arguments ---
    try:
        # Handle case where no subcommand is given
        if not args:
             parser.print_help()
             return None

        parsed_args = parser.parse_args(args)

        # --- Execute subcommand logic ---
        if parsed_args.subcommand == "get":
            # Use config.get which handles defaults and path expansion
            # Handle boolean explicitly if needed for display
            section_upper = parsed_args.section.upper()
            key_lower = parsed_args.key.lower()
            if section_upper == 'HPC' and key_lower == 'slurm_use_singularity':
                 value = service.config.getboolean(section_upper, key_lower, default=parsed_args.default)
            else:
                 value = service.config.get(section_upper, key_lower, parsed_args.default)

            if value is not None:
                if isinstance(value, (dict, list)): # Should not happen with INI, but maybe future formats
                    service.console.print_json(data=value)
                else:
                    service.console.print(str(value)) # Print string representation
            else:
                # config.get returns default (None here) if not found, so indicate that
                service.console.print(f"Key '[{section_upper}].{key_lower}' not found.", style="warning")

        elif parsed_args.subcommand == "set":
            section_upper = parsed_args.section.upper()
            key_lower = parsed_args.key.lower() # Standardize key case for setting
            try:
                # config.set handles validation and saving
                service.config.set(section_upper, key_lower, parsed_args.value)
                # Invalidate cached LLM client if LLM settings changed
                if section_upper == 'LLM':
                     service.llm_client = None
                     logger.info("Invalidated cached LLM client due to config change.")
                # Invalidate cached SSH manager if HPC settings changed
                if section_upper == 'HPC':
                     if service.active_ssh_manager:
                         logger.warning("HPC config changed. Closing active SSH connection.")
                         try: service.active_ssh_manager.disconnect()
                         except Exception: pass
                         service.active_ssh_manager = None
                         service.remote_cwd = None
                         service.console.print("[warning]HPC configuration changed. Active connection closed. Please use /hpc_connect again.[/warning]")
                     else:
                         logger.info("HPC config changed. Any new connection will use the updated settings.")

                service.console.print(f"Config '[{section_upper}].{key_lower}' set to '{parsed_args.value}' and saved.", style="info")
            except ValueError as e: # Catch validation errors from config.set
                service.console.print(f"[error]Validation Error:[/error] {e}")
            except Exception as e:
                logger.error(f"Failed to set config [{section_upper}].{key_lower}", exc_info=True)
                service.console.print(f"[error]Failed to set config:[/error] {e}")

        elif parsed_args.subcommand == "save":
            service.config.save_config()
            config_path = service.config.config_path
            service.console.print(f"Configuration saved successfully to {config_path}.", style="info")

        elif parsed_args.subcommand == "show":
            section_name = parsed_args.section
            if section_name is None or section_name.lower() == 'all':
                config_data = service.config.get_all_config()
                if not config_data:
                    service.console.print("Configuration is empty or could not be read.", style="warning")
                else:
                    # Mask sensitive data in 'all' view
                    display_data = json.loads(json.dumps(config_data)) # Deep copy
                    if 'LLM' in display_data and 'api_key' in display_data['LLM']:
                         display_data['LLM']['api_key'] = "[Set]" if display_data['LLM'].get('api_key') else "[Not Set]"
                    if 'HPC' in display_data and 'password' in display_data['HPC']: # Assuming password might be stored directly (bad practice)
                         display_data['HPC']['password'] = "[Set]" if display_data['HPC'].get('password') else "[Not Set]"
                    service.console.print(Panel(json.dumps(display_data, indent=2), title="Current Configuration (All Sections)", border_style="cyan"))

            elif section_name.lower() == 'ssh':
                config_data = service.config.get_ssh_config()
                if not config_data:
                    service.console.print("SSH (HPC) configuration section not found or empty.", style="warning")
                else:
                     # Mask password if present
                     display_data = config_data.copy()
                     # Password shouldn't be in get_ssh_config result, but check defensively
                     if 'password' in display_data: display_data['password'] = "[Set]" if display_data['password'] else "[Not Set]"
                     if 'key_filename' in display_data and display_data.get('auth_method') != 'key':
                          del display_data['key_filename'] # Don't show irrelevant key path

                     service.console.print(Panel(json.dumps(display_data, indent=2), title="Interpreted SSH Configuration (Subset of HPC)", border_style="cyan"))
            elif section_name.lower() == 'llm':
                 config_data = service.config.get_llm_config() # Gets interpreted LLM config (checks env vars)
                 if not config_data:
                     service.console.print("LLM configuration section not found or empty.", style="warning")
                 else:
                     # Mask API key
                     display_data = config_data.copy()
                     display_data['api_key'] = "[Set]" if display_data.get('api_key') else "[Not Set]"
                     service.console.print(Panel(json.dumps(display_data, indent=2), title="Interpreted LLM Configuration", border_style="cyan"))
            elif section_name.lower() == 'hpc': # Show the full HPC section
                 section_upper = 'HPC'
                 config_data = service.config.get_section(section_upper)
                 if config_data is None:
                     service.console.print(f"Configuration section '[{section_upper}]' not found.", style="warning")
                 else:
                     display_data = config_data.copy()
                     # Mask password if present
                     if 'password' in display_data: display_data['password'] = "[Set]" if display_data['password'] else "[Not Set]"
                     service.console.print(Panel(json.dumps(display_data, indent=2), title=f"Configuration Section [{section_upper}]", border_style="cyan"))

            else:
                # Show specific section
                section_upper = section_name.upper()
                config_data = service.config.get_section(section_upper) # Gets raw section data
                if config_data is None:
                    available_sections = service.config.get_available_sections()
                    service.console.print(f"Configuration section '[{section_upper}]' not found. Available sections: {', '.join(available_sections)}", style="warning")
                else:
                     # Mask sensitive data if showing specific sections like LLM or HPC directly
                     display_data = config_data.copy()
                     if section_upper == 'LLM' and 'api_key' in display_data:
                         display_data['api_key'] = "[Set]" if display_data.get('api_key') else "[Not Set]"
                     if section_upper == 'HPC' and 'password' in display_data:
                         display_data['password'] = "[Set]" if display_data.get('password') else "[Not Set]"
                     # Add other masking if needed

                     service.console.print(Panel(json.dumps(display_data, indent=2), title=f"Configuration Section [{section_upper}]", border_style="cyan"))

        elif parsed_args.subcommand == "slurm_singularity":
            # Handle the new subcommand
            section = 'HPC'
            key = 'slurm_use_singularity'
            value_str = 'True' if parsed_args.state == 'on' else 'False'
            try:
                # Use config.set which handles validation and saving
                service.config.set(section, key, value_str)
                # No need to disconnect SSH for this specific setting change
                logger.info(f"Set {key} to {value_str}")
                service.console.print(f"Default Slurm Singularity usage set to: [bold cyan]{parsed_args.state}[/bold cyan]", style="info")
            except ValueError as e: # Catch validation errors from config.set
                service.console.print(f"[error]Validation Error:[/error] {e}")
            except Exception as e:
                logger.error(f"Failed to set config [{section}].{key}", exc_info=True)
                service.console.print(f"[error]Failed to set config:[/error] {e}")

        else:
             # Should be caught by argparse if required=True
             parser.print_help()

        return None # Output is printed directly

    except argparse.ArgumentError as e:
        raise e # Re-raise for execute_command to handle
    except SystemExit:
         return None # Help was printed
    except Exception as e:
        logger.error(f"Error during /config {args}: {e}", exc_info=True)
        raise RuntimeError(f"Error executing config command: {e}") from e
