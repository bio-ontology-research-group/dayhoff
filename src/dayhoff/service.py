import json
import shlex
from typing import Any, List, Dict, Optional
import logging # Added logging
import os # Added os import
import subprocess # Added for running test scripts
import sys # Added for getting python executable
import textwrap # For formatting help text

# --- Core Components ---
from .config import DayhoffConfig
from .git_tracking import GitTracker, Event

# --- File System ---
# This import should now work correctly
from .fs import BioDataExplorer
# Import specific FS components needed for new commands
from .fs.local import LocalFileSystem
from .fs.file_inspector import FileInspector

# --- HPC Bridge ---
# Import necessary components as needed by commands
# from .hpc import HPCManager # Maybe too high-level? Use bridge components directly?
from .hpc_bridge.credentials import CredentialManager
from .hpc_bridge.file_sync import FileSynchronizer
from .hpc_bridge.slurm_manager import SlurmManager
from .hpc_bridge.ssh_manager import SSHManager

# --- AI/LLM ---
from .ai import AnalysisAdvisor
from .llm.budget import TokenBudget
from .llm.context import ContextManager

# --- Workflows & Environment ---
# Corrected import: Import WorkflowGenerator from the workflow_generator module
from .workflow_generator import WorkflowGenerator
from .workflows.environment import EnvironmentTracker
# from .modules import ModuleManager # If needed for a /module command

# --- Helper for argument parsing ---
import argparse

# Configure logging for the service
logger = logging.getLogger(__name__)
# Basic logging configuration (can be more sophisticated)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')


class DayhoffService:
    """Shared backend service for both CLI and notebook interfaces"""

    def __init__(self):
        # Instantiate core/persistent services
        self.tracker = GitTracker()
        self.config = DayhoffConfig()
        # Instantiate components needed by handlers
        self.local_fs = LocalFileSystem()
        self.file_inspector = FileInspector(self.local_fs) # FileInspector needs a filesystem
        logger.info("DayhoffService initialized.")
        # Lazily instantiate others as needed within command handlers
        # or instantiate here if frequently used and lightweight.
        self._command_map = self._build_command_map()


    def _build_command_map(self) -> Dict[str, Dict[str, Any]]:
        """Builds a map of commands, their handlers, and help text."""
        # Structure: command_name: {'handler': self._handle_command_xyz, 'help': 'Help text...'}
        return {
            "help": {"handler": self._handle_help, "help": "Show help for commands. Usage: /help [command_name]"},
            # --- Test Command ---
            # Updated help text for /test
            "test": {"handler": self._handle_test, "help": "Run or show information about internal tests. Usage: /test [test_name]"},
            # --- Config ---
            "config_get": {"handler": self._handle_config_get, "help": "Get a config value. Usage: /config_get <section> <key> [default_value]"},
            "config_ssh": {"handler": self._handle_config_ssh, "help": "Get SSH configuration. Usage: /config_ssh"},
            "config_save": {"handler": self._handle_config_save, "help": "Save current configuration. Usage: /config_save"},
            # --- File System ---
            "fs_find_seq": {"handler": self._handle_fs_find_seq, "help": "Find sequence files in a directory. Usage: /fs_find_seq [root_path]"},
            "fs_head": {"handler": self._handle_fs_head, "help": "Show the first N lines of a local file. Usage: /fs_head <file_path> [num_lines=10]"},
            "fs_detect_format": {"handler": self._handle_fs_detect_format, "help": "Detect the format of a local file. Usage: /fs_detect_format <file_path>"},
            # "fs_stats": {"handler": self._handle_fs_stats, "help": "Get file statistics. Usage: /fs_stats <filepath>"}, # Needs FileStats class
            # "fs_cmd": {"handler": self._handle_fs_cmd, "help": "Run a local shell command. Usage: /fs_cmd <command_string>"}, # Needs LocalFileSystem class
            # --- Git Tracking ---
            "git_record": {"handler": self._handle_git_record, "help": "Record a custom event. Usage: /git_record <event_type> <metadata_json> [files_json]"},
            "git_log": {"handler": self._handle_git_log, "help": "Show git event log. Usage: /git_log [limit=10]"},
            # --- HPC Bridge ---
            "hpc_sync_up": {"handler": self._handle_hpc_sync_up, "help": "Upload file(s) to HPC. Usage: /hpc_sync_up <local_path_or_glob> <remote_dir>"},
            "hpc_sync_down": {"handler": self._handle_hpc_sync_down, "help": "Download file(s) from HPC. Usage: /hpc_sync_down <remote_path_or_glob> <local_dir>"},
            "hpc_ssh_cmd": {"handler": self._handle_hpc_ssh_cmd, "help": "Execute a command via SSH. Usage: /hpc_ssh_cmd <command_string>"},
            "hpc_slurm_submit": {"handler": self._handle_hpc_slurm_submit, "help": "Submit a Slurm job. Usage: /hpc_slurm_submit <script_path> [options_json]"},
            # Updated help text for hpc_slurm_status
            "hpc_slurm_status": {
                "handler": self._handle_hpc_slurm_status,
                "help": textwrap.dedent("""\
                    Get Slurm job status. Defaults to user's jobs.
                    Usage: /hpc_slurm_status [--job-id <id> | --user | --all] [--waiting-summary]
                      --job-id <id> : Show status for a specific job ID.
                      --user        : Show status for the current user's jobs (default).
                      --all         : Show status for all jobs in the queue.
                      --waiting-summary: Include a summary of waiting times for pending jobs.""")
            },
            "hpc_cred_get": {"handler": self._handle_hpc_cred_get, "help": "Get HPC password for user (if stored). Usage: /hpc_cred_get <username>"},
            # --- AI/LLM ---
            "ai_suggest": {"handler": self._handle_ai_suggest, "help": "Suggest analysis based on data type and metadata. Usage: /ai_suggest <data_type> <metadata_json>"},
            "llm_budget": {"handler": self._handle_llm_budget, "help": "Show remaining LLM token budget. Usage: /llm_budget"},
            "llm_context_update": {"handler": self._handle_llm_context_update, "help": "Update LLM context. Usage: /llm_context_update <updates_json>"},
            "llm_context_get": {"handler": self._handle_llm_context_get, "help": "Get current LLM context. Usage: /llm_context_get"},
            # --- Workflows & Environment ---
            "wf_gen_cwl": {"handler": self._handle_wf_gen_cwl, "help": "Generate CWL workflow. Usage: /wf_gen_cwl <steps_json>"},
            "wf_gen_nextflow": {"handler": self._handle_wf_gen_nextflow, "help": "Generate Nextflow workflow. Usage: /wf_gen_nextflow <steps_json>"},
            "env_get": {"handler": self._handle_env_get, "help": "Get environment details. Usage: /env_get"},
        }

    # --- Added Method ---
    def get_available_commands(self) -> List[str]:
        """Returns a list of available command names (without the leading '/')."""
        return list(self._command_map.keys())
    # --- End Added Method ---

    def execute_command(self, command: str, args: List[str]) -> Any:
        """Execute a command and track it in git"""
        logger.info(f"Executing command: /{command} with args: {args}")
        if command in self._command_map:
            command_info = self._command_map[command]
            handler = command_info["handler"]
            try:
                # Record the event before execution
                # Consider adding more context like current working directory?
                # Skip recording for /test command itself?
                if command != 'test':
                    self.tracker.record_event(
                        event_type="command_executed",
                        metadata={
                            "command": command,
                            "args": args # Log raw args
                        }
                        # Files might be implicitly tracked by handlers if needed
                    )
                # Execute the command handler
                result = handler(args)
                logger.info(f"Command /{command} executed successfully.")
                # Avoid printing None results explicitly in the REPL
                return result if result is not None else ""
            except argparse.ArgumentError as e:
                 logger.warning(f"Argument error for /{command}: {e}")
                 # Provide specific usage help on argument error
                 # Check if the error message already contains usage info from the parser
                 if "usage:" in str(e).lower():
                     return f"Argument Error: {e}"
                 else:
                     # Use the detailed help text from the command map
                     usage = command_info.get('help', 'No help available.')
                     # Ensure usage starts with "Usage:" for consistency
                     if not usage.strip().lower().startswith("usage:"):
                         usage = f"Usage: /{command} ..." # Generic fallback
                     return f"Argument Error: {e}\n{usage}"
            except FileNotFoundError as e: # Catch file not found specifically
                 logger.warning(f"File not found during /{command}: {e}")
                 return f"Error: File not found - {e}"
            except ConnectionError as e: # Catch connection errors from HPC modules
                 logger.error(f"Connection error during /{command}: {e}", exc_info=True)
                 return f"Connection Error: {e}"
            except Exception as e:
                logger.error(f"Error executing command /{command}: {e}", exc_info=True)
                # Log the exception details?
                # Skip recording failure for /test command itself?
                if command != 'test':
                    self.tracker.record_event(
                        event_type="command_failed",
                        metadata={
                            "command": command,
                            "args": args,
                            "error": str(e),
                            "error_type": type(e).__name__
                        }
                    )
                # Return a user-friendly error message
                return f"Error: {type(e).__name__}: {e}"
        else:
            logger.warning(f"Unknown command attempted: /{command}")
            return f"Unknown command: /{command}. Type /help for available commands."

    # --- Help Handler ---
    def _handle_help(self, args: List[str]) -> str:
        if not args:
            # General help
            help_lines = ["Available commands:"]
            # Sort commands alphabetically for better readability
            for cmd, info in sorted(self._command_map.items()):
                # Provide a slightly more descriptive summary if possible
                # Use the first line of the help text if available
                first_line = info['help'].split('\n')[0].strip()
                help_lines.append(f"  /{cmd:<20} - {first_line}")
            help_lines.append("\nType /help <command_name> for more details.")
            return "\n".join(help_lines)
        else:
            # Specific command help
            cmd_name = args[0]
            if cmd_name.startswith('/'): # Allow /help /command_name
                cmd_name = cmd_name[1:]
            if cmd_name in self._command_map:
                # Return the full help text for the specific command
                # If the command is 'test', call its handler without args to get detailed help
                if cmd_name == 'test':
                    return self._handle_test([]) # Call test handler with no args for help
                else:
                    # Ensure the help text includes the usage format
                    help_text = self._command_map[cmd_name]['help']
                    # if not help_text.strip().lower().startswith("usage:"):
                    #     # Add a generic usage line if missing (might not be perfect)
                    #     help_text = f"Usage: /{cmd_name} ...\n\n{help_text}"
                    return help_text
            else:
                return f"Unknown command: /{cmd_name}"

    # --- Argument Parsers (Example for one command) ---
    def _create_parser(self, prog: str, description: str) -> argparse.ArgumentParser:
        """Creates an ArgumentParser instance for command parsing."""
        # Prevent argparse from exiting the program on error
        # Use the description from the command map if available
        parser = argparse.ArgumentParser(
            prog=f"/{prog}",
            description=description,
            add_help=False, # We handle help via /help command
            formatter_class=argparse.RawDescriptionHelpFormatter # Preserve formatting
        )
        # Override error handling to raise exception instead of exiting
        def error(message):
            # Include the command name in the error message for clarity
            # Add usage string to the error message
            usage = parser.format_usage()
            full_message = f"Invalid arguments for /{prog}: {message}\n{usage}"
            raise argparse.ArgumentError(None, full_message)
        parser.error = error
        return parser

    # --- Test Command Handler ---
    def _handle_test(self, args: List[str]) -> str:
        """Handles the /test command, running tests from the examples directory."""

        # Assume 'examples' is relative to the CWD where the REPL is started
        examples_dir = "examples"

        available_tests = {
            "cli": "Test non-interactive CLI execution (`dayhoff execute ...`).",
            "config": "Test loading and printing the current configuration.",
            "file_explorer": "Test local file head and format detection.",
            "git_tracking": "Test GitTracker event recording and history retrieval.",
            "hpc_bridge": "Test mock SSH/Slurm interactions.",
            "llm_core": "Test mock LLM prompt/response/context flow.",
            "remote_fs": "Test SSH connection and remote `ls` execution.",
            "remote_workflow": "Test remote CWL workflow execution via SSH.",
            "session_tracking": "Test GitTracker with simulated session events.",
            "ssh_connection": "Test basic SSH connection and simple command execution.",
            "workflow": "Test local CWL generation and execution.",
            # Add more keys as needed, matching filenames or logical test groups
        }

        # If no arguments are provided, or if 'help' is passed, show available tests
        if not args or (args and args[0] == 'help'):
            help_lines = [
                self._command_map['test']['help'], # Use help text from map
                "\nAvailable tests:",
            ]
            for name, desc in sorted(available_tests.items()):
                script_path = os.path.join(examples_dir, f"test_{name}.py")
                exists_marker = "[exists]" if os.path.isfile(script_path) else "[missing]"
                help_lines.append(f"  {name:<20} - {desc} {exists_marker}")
            return "\n".join(help_lines)

        # Use argparse to parse the optional test_name
        parser = self._create_parser("test", self._command_map['test']['help'])
        parser.add_argument("test_name", nargs='?', help="The name of the test to run.")
        # Add a dummy argument to allow parsing 'help' without error
        # parser.add_argument("dummy", nargs='*', help=argparse.SUPPRESS)

        try:
            parsed_args = parser.parse_args(args)
        except argparse.ArgumentError as e:
             # If parsing fails, show the help text
             return self._handle_test([]) # Show help

        test_name = parsed_args.test_name
        if not test_name: # Should not happen if parsing succeeds, but check anyway
             return self._handle_test([]) # Show help


        if test_name in available_tests:
            script_name = f"test_{test_name}.py"
            script_path = os.path.join(examples_dir, script_name)
            logger.info(f"Attempting to execute test script: {script_path}")

            if not os.path.isfile(script_path):
                logger.error(f"Test script not found: {script_path}")
                # Raise FileNotFoundError to be caught by main handler
                raise FileNotFoundError(f"Test script '{script_path}' not found.")

            try:
                # Execute the script using the same Python interpreter that's running Dayhoff
                process = subprocess.run(
                    [sys.executable, script_path],
                    capture_output=True,
                    text=True,
                    check=False, # Don't raise exception on non-zero exit, handle manually
                    timeout=120 # Add a timeout (e.g., 2 minutes)
                )

                # Format the output
                output_lines = [
                    f"--- Running Test: {test_name} ({script_path}) ---",
                    f"Exit Code: {process.returncode}",
                    "\n--- STDOUT ---",
                    process.stdout.strip(),
                    "\n--- STDERR ---",
                    process.stderr.strip(),
                    "\n--------------"
                ]
                result_message = "\n".join(output_lines)
                if process.returncode == 0:
                    logger.info(f"Test script '{script_path}' executed successfully.")
                else:
                    logger.warning(f"Test script '{script_path}' finished with exit code {process.returncode}.")

                return result_message

            except subprocess.TimeoutExpired:
                 logger.error(f"Test script '{script_path}' timed out.")
                 # Return error message directly
                 return f"Error: Test script '{script_path}' timed out after 120 seconds."
            except Exception as e:
                logger.error(f"Failed to execute test script '{script_path}': {e}", exc_info=True)
                # Raise the exception to be caught by the main execute_command handler
                raise e
        else:
            # Raise error similar to how parser.error would, including usage
            valid_names = ", ".join(sorted(available_tests.keys()))
            # Use the parser's error mechanism to raise ArgumentError
            parser.error(f"Unknown test_name '{test_name}'. Available tests are: {valid_names}")


    # --- Config Handlers ---
    def _handle_config_get(self, args: List[str]) -> Any:
        parser = self._create_parser("config_get", self._command_map['config_get']['help'])
        parser.add_argument("section", help="Configuration section name")
        parser.add_argument("key", help="Configuration key name")
        parser.add_argument("default", nargs='?', default=None, help="Optional default value if key not found")
        parsed_args = parser.parse_args(args)

        value = self.config.get(parsed_args.section, parsed_args.key, parsed_args.default)
        # Nicer output for dicts/lists
        if isinstance(value, (dict, list)):
            return json.dumps(value, indent=2)
        return value

    def _handle_config_ssh(self, args: List[str]) -> Dict[str, str]:
        parser = self._create_parser("config_ssh", self._command_map['config_ssh']['help'])
        # No arguments expected, parse to catch extra args
        parsed_args = parser.parse_args(args)
        ssh_config = self.config.get_ssh_config()
        if not ssh_config:
            return "SSH configuration not found or empty."
        # Return JSON string for consistent output
        return json.dumps(ssh_config, indent=2)


    def _handle_config_save(self, args: List[str]) -> str:
        parser = self._create_parser("config_save", self._command_map['config_save']['help'])
        parsed_args = parser.parse_args(args)
        try:
            self.config.save_config()
            config_path = self.config._get_config_path() # Assuming this method exists
            return f"Configuration saved successfully to {config_path}."
        except Exception as e:
            logger.error("Error saving configuration", exc_info=True)
            # Raise exception to be caught by main handler
            raise RuntimeError(f"Error saving configuration: {e}") from e

    # --- File System Handlers ---
    def _handle_fs_find_seq(self, args: List[str]) -> str:
        parser = self._create_parser("fs_find_seq", self._command_map['fs_find_seq']['help'])
        parser.add_argument("root_path", nargs='?', default='.', help="Optional root directory to search (default: current directory)")
        parsed_args = parser.parse_args(args)

        # Note: Iterators are tricky in a simple REPL.
        # We'll collect and return the list for now.
        try:
            # Instantiate BioDataExplorer with the specified or default path
            explorer = BioDataExplorer(root_path=parsed_args.root_path)
            files = list(explorer.find_sequence_files()) # Collect results from iterator
            if not files:
                return f"No sequence files found in '{os.path.abspath(parsed_args.root_path)}'."
            # Return absolute paths for clarity
            abs_files = [os.path.abspath(f) for f in files]
            return f"Found sequence files in '{os.path.abspath(parsed_args.root_path)}':\n" + "\n".join(abs_files)
        except ValueError as e: # Catch specific error from BioDataExplorer init
             # Let main handler report this error
             raise e
        except Exception as e:
            logger.error(f"Error finding sequence files in {parsed_args.root_path}", exc_info=True)
            raise RuntimeError(f"Error finding sequence files: {e}") from e

    def _handle_fs_head(self, args: List[str]) -> str:
        """Handles the /fs_head command."""
        parser = self._create_parser("fs_head", self._command_map['fs_head']['help'])
        parser.add_argument("file_path", help="Path to the local file")
        parser.add_argument("num_lines", type=int, nargs='?', default=10, help="Number of lines to show (default: 10)")
        parsed_args = parser.parse_args(args)

        if parsed_args.num_lines <= 0:
            # Use parser's error mechanism
            parser.error("Number of lines must be positive.")

        try:
            # Use the FileInspector instance
            lines = list(self.file_inspector.head(parsed_args.file_path, parsed_args.num_lines))
            if not lines:
                # Check if file exists before saying it's empty
                if not self.local_fs.exists(parsed_args.file_path):
                     raise FileNotFoundError(f"File not found at '{parsed_args.file_path}'")
                return f"File is empty: {parsed_args.file_path}"
            return f"First {len(lines)} lines of '{parsed_args.file_path}':\n---\n" + "\n".join(lines) + "\n---"
        except FileNotFoundError:
             # Re-raise specifically for execute_command to catch
             raise FileNotFoundError(f"File not found at '{parsed_args.file_path}'")
        except Exception as e:
            logger.error(f"Error reading head of file {parsed_args.file_path}", exc_info=True)
            # Let the main execute_command handler catch and report generic errors
            raise e

    def _handle_fs_detect_format(self, args: List[str]) -> str:
        """Handles the /fs_detect_format command."""
        parser = self._create_parser("fs_detect_format", self._command_map['fs_detect_format']['help'])
        parser.add_argument("file_path", help="Path to the local file")
        parsed_args = parser.parse_args(args)

        try:
            # Use the LocalFileSystem instance's method
            file_format = self.local_fs.detect_format(parsed_args.file_path)
            if file_format:
                return f"Detected format for '{parsed_args.file_path}': {file_format}"
            else:
                 # Check if file exists before saying format unknown
                 if not self.local_fs.exists(parsed_args.file_path):
                     raise FileNotFoundError(f"File not found at '{parsed_args.file_path}'")
                 return f"Could not detect format for '{parsed_args.file_path}'."
        except FileNotFoundError:
             raise FileNotFoundError(f"File not found at '{parsed_args.file_path}'")
        except Exception as e:
            logger.error(f"Error detecting format for file {parsed_args.file_path}", exc_info=True)
            raise e


    # --- Git Tracking Handlers ---
    def _handle_git_record(self, args: List[str]) -> str:
        parser = self._create_parser("git_record", self._command_map['git_record']['help'])
        parser.add_argument("event_type", help="Type of the event (e.g., 'manual_step')")
        parser.add_argument("metadata_json", help="Metadata as a JSON string (e.g., '{\"key\": \"value\"}')")
        parser.add_argument("files_json", nargs='?', default='{}', help="Optional dictionary of files to track as JSON string (e.g., '{\"input.txt\": \"path/to/input.txt\"}')")
        parsed_args = parser.parse_args(args)

        try:
            metadata = json.loads(parsed_args.metadata_json)
            # Ensure metadata is a dictionary
            if not isinstance(metadata, dict):
                # Use parser error for consistency
                parser.error("Metadata JSON must decode to a dictionary.")

            files_dict = json.loads(parsed_args.files_json)
            if not isinstance(files_dict, dict):
                 parser.error("Files JSON must decode to a dictionary.")

            # Optional: Validate file paths in files_dict exist?
            # for logical_name, path in files_dict.items():
            #     if not os.path.exists(path):
            #         logger.warning(f"File path for '{logical_name}' does not exist: {path}")
            #         # Decide whether to raise an error or just warn

            event_id = self.tracker.record_event(
                event_type=parsed_args.event_type,
                metadata=metadata,
                files=files_dict if files_dict else None # Pass None if empty
            )
            return f"Event '{parsed_args.event_type}' recorded with ID: {event_id}."
        except json.JSONDecodeError as e:
            # Raise a more specific error via parser if possible, otherwise generic
            raise ValueError(f"Invalid JSON provided: {e}") from e
        except ValueError as e: # Catch our custom validation error
            raise e # Let main handler catch it
        except Exception as e:
            logger.error("Error recording git event", exc_info=True)
            raise RuntimeError(f"Error recording event: {e}") from e

    def _handle_git_log(self, args: List[str]) -> str:
        """Handles the /git_log command."""
        parser = self._create_parser("git_log", self._command_map['git_log']['help'])
        parser.add_argument("limit", type=int, nargs='?', default=10, help="Maximum number of events to show (default: 10)")
        parsed_args = parser.parse_args(args)

        if parsed_args.limit <= 0:
            parser.error("Limit must be positive.")

        try:
            history = self.tracker.get_event_history()
            if not history:
                return "No events recorded yet."

            # Apply limit (show most recent first)
            limited_history = history[-parsed_args.limit:]

            log_lines = ["Git Event History (most recent first):"]
            for event in reversed(limited_history): # Reverse to show newest first
                ts = event.timestamp.strftime('%Y-%m-%d %H:%M:%S')
                meta_summary = json.dumps(event.metadata, sort_keys=True)
                # Truncate long metadata for display?
                if len(meta_summary) > 80:
                    meta_summary = meta_summary[:77] + "..."
                log_lines.append(f"- {ts} [{event.event_type}] {meta_summary}")
                if event.files:
                    files_summary = ", ".join(f"{k}: {v}" for k, v in event.files.items())
                    if len(files_summary) > 80:
                         files_summary = files_summary[:77] + "..."
                    log_lines.append(f"    Files: {files_summary}")

            return "\n".join(log_lines)
        except Exception as e:
            logger.error("Error retrieving git log", exc_info=True)
            raise e


    # --- HPC Bridge Handlers ---
    def _get_ssh_manager(self) -> SSHManager:
        """Helper to get an initialized SSHManager."""
        ssh_config = self.config.get_ssh_config()
        if not ssh_config:
            # Raise ConnectionError for the main handler
            raise ConnectionError("SSH configuration not found. Use /config_set or edit config file.")
        try:
            # Pass the config dictionary directly
            return SSHManager(ssh_config=ssh_config)
        except Exception as e:
             logger.error(f"Failed to initialize SSHManager: {e}", exc_info=True)
             raise ConnectionError(f"Failed to initialize SSH connection: {e}") from e


    def _get_file_synchronizer(self) -> FileSynchronizer:
        """Helper to get an initialized FileSynchronizer."""
        # FileSynchronizer likely needs an SSHManager instance or config
        ssh_manager = self._get_ssh_manager() # Reuse SSH manager logic
        # Assuming FileSynchronizer takes the manager instance
        try:
            return FileSynchronizer(ssh_manager=ssh_manager)
            # Or if it takes config:
            # ssh_config = self.config.get_ssh_config()
            # if not ssh_config:
            #     raise ConnectionError("SSH configuration not found.")
            # return FileSynchronizer(ssh_config=ssh_config)
        except Exception as e:
             logger.error(f"Failed to initialize FileSynchronizer: {e}", exc_info=True)
             # Raise a connection error as it likely stems from SSH setup
             raise ConnectionError(f"Failed to initialize file synchronizer: {e}") from e


    def _get_slurm_manager(self) -> SlurmManager:
        """Helper to get an initialized SlurmManager."""
        ssh_manager = self._get_ssh_manager() # Reuse SSH manager logic
        try:
            # Pass the initialized SSHManager instance
            return SlurmManager(ssh_manager=ssh_manager)
        except Exception as e:
             logger.error(f"Failed to initialize SlurmManager: {e}", exc_info=True)
             raise ConnectionError(f"Failed to initialize Slurm manager: {e}") from e


    def _handle_hpc_sync_up(self, args: List[str]) -> str:
        parser = self._create_parser("hpc_sync_up", self._command_map['hpc_sync_up']['help'])
        parser.add_argument("local_path", help="Local file or glob pattern (e.g., 'data/*.fastq')")
        parser.add_argument("remote_dir", help="Remote destination directory")
        parsed_args = parser.parse_args(args)

        try:
            synchronizer = self._get_file_synchronizer()

            # FileSynchronizer.upload_files expects List[str], handle potential glob
            import glob
            local_paths = glob.glob(parsed_args.local_path)
            if not local_paths:
                # Use os.path.exists for single files for better error message
                if not glob.has_magic(parsed_args.local_path) and not os.path.exists(parsed_args.local_path):
                     raise FileNotFoundError(f"Local path not found: '{parsed_args.local_path}'")
                return f"Warning: No local files found matching '{parsed_args.local_path}'. Nothing uploaded."

            logger.info(f"Uploading {len(local_paths)} files to {parsed_args.remote_dir}...")
            # Assuming upload_files returns bool or raises error
            success = synchronizer.upload_files(local_paths, parsed_args.remote_dir)
            if success: # Or if no exception was raised
                return f"Successfully uploaded {len(local_paths)} file(s) matching '{parsed_args.local_path}' to {parsed_args.remote_dir}."
            else:
                # If upload_files returns False without raising error
                raise RuntimeError("File upload failed. Check logs for details.")
        except (ConnectionError, FileNotFoundError, RuntimeError) as e:
            # Let main handler report these specific errors
            raise e
        except Exception as e:
            logger.error("Error during HPC upload", exc_info=True)
            # Raise a generic runtime error
            raise RuntimeError(f"Error during upload: {e}") from e

    def _handle_hpc_sync_down(self, args: List[str]) -> str:
        parser = self._create_parser("hpc_sync_down", self._command_map['hpc_sync_down']['help'])
        parser.add_argument("remote_path", help="Remote file or glob pattern (requires remote shell expansion)")
        parser.add_argument("local_dir", help="Local destination directory")
        parsed_args = parser.parse_args(args)

        try:
            synchronizer = self._get_file_synchronizer()

            # download_files expects List[str]. Handling remote globs requires executing
            # 'ls <remote_glob>' via SSH first, which adds complexity.
            # Current assumption: User provides specific paths or a pattern understood
            # by the underlying sync tool (e.g., rsync).
            # For simplicity, we pass the pattern directly. Adjust if FileSynchronizer needs explicit list.
            remote_paths = [parsed_args.remote_path] # Pass the pattern/path as a single item list
            logger.info(f"Attempting download of '{parsed_args.remote_path}' to {parsed_args.local_dir}...")

            # Ensure local directory exists
            os.makedirs(parsed_args.local_dir, exist_ok=True)

            success = synchronizer.download_files(remote_paths, parsed_args.local_dir)
            if success: # Or if no exception raised
                 # We don't know exactly how many files were downloaded if it was a glob
                 return f"Successfully downloaded files matching '{parsed_args.remote_path}' to {parsed_args.local_dir}."
            else:
                 raise RuntimeError("File download failed. Check logs for details.")
        except (ConnectionError, RuntimeError) as e:
             raise e
        except Exception as e:
            logger.error("Error during HPC download", exc_info=True)
            raise RuntimeError(f"Error during download: {e}") from e

    def _handle_hpc_ssh_cmd(self, args: List[str]) -> str:
        parser = self._create_parser("hpc_ssh_cmd", self._command_map['hpc_ssh_cmd']['help'])
        parser.add_argument("command", nargs='+', help="The command string to execute remotely")
        parsed_args = parser.parse_args(args) # Will raise error if no command provided

        command_string = " ".join(parsed_args.command) # Rejoin args into the command

        try:
            ssh_manager = self._get_ssh_manager()
            logger.info(f"Executing SSH command: {command_string}")
            output = ssh_manager.execute_command(command_string)
            # Return output, potentially trimming whitespace
            return f"SSH command output:\n---\n{output.strip()}\n---"
        except ConnectionError as e:
            raise e
        except Exception as e:
            logger.error("Error executing SSH command", exc_info=True)
            raise RuntimeError(f"Error executing SSH command: {e}") from e

    def _handle_hpc_slurm_submit(self, args: List[str]) -> str:
        parser = self._create_parser("hpc_slurm_submit", self._command_map['hpc_slurm_submit']['help'])
        parser.add_argument("script_path", help="Path to the local Slurm script file")
        parser.add_argument("options_json", nargs='?', default='{}', help="Optional Slurm options as JSON string (e.g., '{\"--nodes\": 1, \"--time\": \"01:00:00\"}')")
        parsed_args = parser.parse_args(args)

        try:
            slurm_manager = self._get_slurm_manager()

            options = json.loads(parsed_args.options_json)
            if not isinstance(options, dict):
                parser.error("Options JSON must decode to a dictionary.")

            # Read the script content from the local path
            script_path = os.path.abspath(parsed_args.script_path)
            if not os.path.isfile(script_path):
                 raise FileNotFoundError(f"Script file not found at '{script_path}'")

            with open(script_path, 'r') as f:
                script_content = f.read()

            logger.info(f"Submitting Slurm job from script: {script_path} with options: {options}")
            # Assuming submit_job raises errors on failure
            job_id = slurm_manager.submit_job(script_content, options)
            return f"Slurm job submitted with ID: {job_id}"
        except (ConnectionError, FileNotFoundError, ValueError, RuntimeError) as e:
            # Let main handler report these
            raise e
        except json.JSONDecodeError as e:
            # Raise ValueError for consistency
            raise ValueError(f"Invalid JSON provided for options: {e}") from e
        except Exception as e:
            logger.error("Error submitting Slurm job", exc_info=True)
            raise RuntimeError(f"Error submitting Slurm job: {e}") from e

    def _handle_hpc_slurm_status(self, args: List[str]) -> str:
        """Handles the /hpc_slurm_status command with multiple query options."""
        parser = self._create_parser("hpc_slurm_status", self._command_map['hpc_slurm_status']['help'])
        # Group for mutually exclusive scope arguments
        scope_group = parser.add_mutually_exclusive_group()
        scope_group.add_argument("--job-id", help="Show status for a specific job ID.")
        scope_group.add_argument("--user", action='store_true', help="Show status for the current user's jobs (default if no scope specified).")
        scope_group.add_argument("--all", action='store_true', help="Show status for all jobs in the queue.")

        parser.add_argument("--waiting-summary", action='store_true', help="Include a summary of waiting times for pending jobs.")

        parsed_args = parser.parse_args(args)

        # Determine scope
        job_id = parsed_args.job_id
        query_user = parsed_args.user
        query_all = parsed_args.all

        # Default to user if no scope argument is given
        if not job_id and not query_user and not query_all:
            query_user = True
            logger.info("No scope specified for /hpc_slurm_status, defaulting to --user.")


        try:
            slurm_manager = self._get_slurm_manager()
            logger.info(f"Getting Slurm status info (job_id={job_id}, user={query_user}, all={query_all}, summary={parsed_args.waiting_summary})")

            # Call the updated SlurmManager method
            status_info = slurm_manager.get_queue_info(
                job_id=job_id,
                query_user=query_user,
                query_all=query_all,
                waiting_summary=parsed_args.waiting_summary
            )

            # Format the output
            output_lines = []
            jobs = status_info.get("jobs", [])
            summary = status_info.get("waiting_summary")

            if not jobs:
                output_lines.append("No Slurm jobs found matching the criteria.")
            else:
                # Simple table-like format (adjust columns as needed)
                # Use headers from the SQUEUE_FIELDS in SlurmManager for consistency
                headers = ["JobID", "Partition", "Name", "User", "State", "Time", "Nodes", "Reason", "SubmitTime"]
                # Map internal keys to display headers
                field_map = {
                    "job_id": "JobID", "partition": "Partition", "name": "Name",
                    "user": "User", "state_compact": "State", "time_used": "Time",
                    "nodes": "Nodes", "reason": "Reason", "submit_time_str": "SubmitTime"
                }
                display_fields = list(field_map.keys())
                display_headers = [field_map[f] for f in display_fields]

                # Calculate column widths (optional, for better alignment)
                col_widths = {h: len(h) for h in display_headers}
                for job in jobs:
                    for field in display_fields:
                        col_widths[field_map[field]] = max(col_widths[field_map[field]], len(str(job.get(field, ''))))

                # Create header line
                header_line = "  ".join(f"{h:<{col_widths[h]}}" for h in display_headers)
                output_lines.append(header_line)
                output_lines.append("-" * len(header_line))

                # Create data lines
                for job in jobs:
                    line_parts = []
                    for field in display_fields:
                        value = str(job.get(field, ''))
                        line_parts.append(f"{value:<{col_widths[field_map[field]]}}")
                    output_lines.append("  ".join(line_parts))

            if summary:
                output_lines.append("\n--- Waiting Time Summary (Pending Jobs) ---")
                output_lines.append(f"  Count: {summary.get('pending_count', 0)}")
                if summary.get('pending_count', 0) > 0 and "avg_wait_human" in summary:
                    output_lines.append(f"  Average Wait: {summary.get('avg_wait_human', 'N/A')}")
                    output_lines.append(f"  Min Wait:     {summary.get('min_wait_human', 'N/A')}")
                    output_lines.append(f"  Max Wait:     {summary.get('max_wait_human', 'N/A')}")
                elif "message" in summary:
                     output_lines.append(f"  Info: {summary['message']}")


            return "\n".join(output_lines)

        except (ConnectionError, ValueError, RuntimeError) as e:
            # Let main handler report these known error types
            raise e
        except Exception as e:
            logger.error(f"Error getting Slurm job status", exc_info=True)
            raise RuntimeError(f"Error getting Slurm job status: {e}") from e


    def _handle_hpc_cred_get(self, args: List[str]) -> str:
        parser = self._create_parser("hpc_cred_get", self._command_map['hpc_cred_get']['help'])
        parser.add_argument("username", help="HPC username")
        parsed_args = parser.parse_args(args)

        try:
            # Assuming CredentialManager can be instantiated directly
            # It likely uses the 'keyring' library backend
            cred_manager = CredentialManager()
            # Construct a service name (adjust as needed based on CredentialManager impl)
            # Let's try to get host from config to make service name more specific
            host = self.config.get("ssh", "host", default="default_hpc") # Example
            service_name = f"dayhoff_hpc_{host}_{parsed_args.username}"

            password = cred_manager.get_password(service_name=service_name, username=parsed_args.username) # Adjust args if needed
            if password:
                 # Security: Do NOT return the password itself to the REPL!
                 logger.info(f"Password found for user '{parsed_args.username}' on host '{host}' in keyring.")
                 return f"Password found for user '{parsed_args.username}' (service: {service_name}) in system keyring."
            else:
                 logger.info(f"No stored password found for user '{parsed_args.username}' (service: {service_name}) in keyring.")
                 return f"No stored password found for user '{parsed_args.username}' (service: {service_name}) in system keyring."
        except Exception as e:
            # Catch potential keyring backend errors
            logger.error(f"Error retrieving credentials for {parsed_args.username}", exc_info=True)
            # Raise a runtime error
            raise RuntimeError(f"Error retrieving credentials: {e}") from e

    # --- AI/LLM Handlers ---
    def _handle_ai_suggest(self, args: List[str]) -> str:
        parser = self._create_parser("ai_suggest", self._command_map['ai_suggest']['help'])
        parser.add_argument("data_type", help="Type of data (e.g., 'fastq', 'vcf', 'bam')")
        parser.add_argument("metadata_json", help="Metadata relevant to the data as JSON string (e.g., '{\"sample_id\": \"s1\", \"condition\": \"treated\"}')")
        parsed_args = parser.parse_args(args)

        try:
            metadata = json.loads(parsed_args.metadata_json)
            if not isinstance(metadata, dict):
                parser.error("Metadata JSON must decode to a dictionary.")

            # Assuming AnalysisAdvisor can be instantiated directly
            # It might need configuration (e.g., API keys) passed via self.config
            advisor = AnalysisAdvisor(config=self.config) # Pass config if needed
            logger.info(f"Requesting analysis suggestion for data type '{parsed_args.data_type}'")
            suggestion = advisor.suggest_analysis(parsed_args.data_type, metadata)
            # Check if suggestion is implemented
            if suggestion is None:
                 return "Analysis suggestion feature is not fully implemented yet."
            return f"Analysis Suggestion:\n---\n{suggestion}\n---"
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON provided for metadata: {e}") from e
        except ValueError as e: # Catch our validation error
             raise e
        except Exception as e:
            logger.error("Error getting analysis suggestion", exc_info=True)
            raise RuntimeError(f"Error getting analysis suggestion: {e}") from e

    def _handle_llm_budget(self, args: List[str]) -> str:
        parser = self._create_parser("llm_budget", self._command_map['llm_budget']['help'])
        parsed_args = parser.parse_args(args)
        try:
            # Assuming TokenBudget might read limits from config
            budget = TokenBudget(config=self.config) # Pass config if needed
            remaining = budget.remaining()
            limit = budget.limit # Assuming a 'limit' property exists
            # Check if budget is implemented
            if remaining is None or limit is None:
                 return "LLM budget tracking is not fully implemented or configured."
            return f"LLM Token Budget: {remaining} remaining / {limit} limit"
        except Exception as e:
            logger.error("Error getting token budget", exc_info=True)
            raise RuntimeError(f"Error getting token budget: {e}") from e

    def _handle_llm_context_update(self, args: List[str]) -> str:
        parser = self._create_parser("llm_context_update", self._command_map['llm_context_update']['help'])
        parser.add_argument("updates_json", help="Updates as JSON string (dictionary)")
        parsed_args = parser.parse_args(args)

        try:
            updates = json.loads(parsed_args.updates_json)
            if not isinstance(updates, dict):
                parser.error("Updates JSON must decode to a dictionary.")

            # Assuming ContextManager might be stateful or read from config/disk
            context_manager = ContextManager(config=self.config) # Pass config if needed
            context_manager.update(updates) # Assume this raises errors if needed
            logger.info(f"LLM context updated with keys: {list(updates.keys())}")
            return "LLM context updated."
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON provided for updates: {e}") from e
        except ValueError as e: # Catch validation errors
             raise e
        except Exception as e:
            logger.error("Error updating LLM context", exc_info=True)
            raise RuntimeError(f"Error updating LLM context: {e}") from e

    def _handle_llm_context_get(self, args: List[str]) -> str:
        parser = self._create_parser("llm_context_get", self._command_map['llm_context_get']['help'])
        parsed_args = parser.parse_args(args)
        try:
            # Assuming ContextManager might be stateful or read from config/disk
            context_manager = ContextManager(config=self.config) # Pass config if needed
            context = context_manager.get()
            if not context: # Handles None or empty dict
                return "LLM context is currently empty."
            return f"Current LLM Context:\n{json.dumps(context, indent=2)}"
        except Exception as e:
            logger.error("Error getting LLM context", exc_info=True)
            raise RuntimeError(f"Error getting LLM context: {e}") from e

    # --- Workflow & Environment Handlers ---
    def _handle_wf_gen_cwl(self, args: List[str]) -> str:
        parser = self._create_parser("wf_gen_cwl", self._command_map['wf_gen_cwl']['help'])
        parser.add_argument("steps_json", help="Workflow steps definition as JSON string (list or dict)")
        # Add optional output file argument?
        # parser.add_argument("-o", "--output", help="Optional path to save the generated CWL file")
        parsed_args = parser.parse_args(args)

        try:
            steps = json.loads(parsed_args.steps_json)
            # Basic validation (expecting a list or dict)
            if not isinstance(steps, (list, dict)):
                 parser.error("Steps JSON must decode to a list or dictionary.")

            # Assuming WorkflowGenerator can be instantiated directly
            generator = WorkflowGenerator()
            logger.info("Generating CWL workflow...")
            cwl_output = generator.generate_cwl(steps) # Assuming this returns the CWL content as string

            # if parsed_args.output:
            #     output_path = os.path.abspath(parsed_args.output)
            #     with open(output_path, 'w') as f:
            #         f.write(cwl_output)
            #     logger.info(f"CWL workflow saved to {output_path}")
            #     return f"Generated CWL workflow saved to: {output_path}"
            # else:
            # Decide how to output: print to console or save to file? Print for now.
            # Check if the generator actually returned something (it might be a placeholder)
            if cwl_output is None:
                # Use a more informative message or potentially raise NotImplementedError
                return "CWL generation is not yet implemented or returned no output."
            return f"Generated CWL Workflow:\n---\n{cwl_output}\n---"
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON provided for steps: {e}") from e
        except ValueError as e: # Catch validation errors
             raise e
        except Exception as e:
            logger.error("Error generating CWL workflow", exc_info=True)
            raise RuntimeError(f"Error generating CWL workflow: {e}") from e

    def _handle_wf_gen_nextflow(self, args: List[str]) -> str:
        parser = self._create_parser("wf_gen_nextflow", self._command_map['wf_gen_nextflow']['help'])
        parser.add_argument("steps_json", help="Workflow steps definition as JSON string (list or dict)")
        # parser.add_argument("-o", "--output", help="Optional path to save the generated Nextflow script")
        parsed_args = parser.parse_args(args)

        try:
            steps = json.loads(parsed_args.steps_json)
            if not isinstance(steps, (list, dict)):
                 parser.error("Steps JSON must decode to a list or dictionary.")

            generator = WorkflowGenerator()
            logger.info("Generating Nextflow workflow...")
            nf_output = generator.generate_nextflow(steps) # Assuming returns script content

            # if parsed_args.output:
            #     output_path = os.path.abspath(parsed_args.output)
            #     with open(output_path, 'w') as f:
            #         f.write(nf_output)
            #     logger.info(f"Nextflow script saved to {output_path}")
            #     return f"Generated Nextflow script saved to: {output_path}"
            # else:
            # Check if the generator actually returned something (it might be a placeholder)
            if nf_output is None:
                return "Nextflow generation is not yet implemented or returned no output."
            return f"Generated Nextflow Workflow:\n---\n{nf_output}\n---"
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON provided for steps: {e}") from e
        except ValueError as e: # Catch validation errors
             raise e
        except Exception as e:
            logger.error("Error generating Nextflow workflow", exc_info=True)
            raise RuntimeError(f"Error generating Nextflow workflow: {e}") from e

    def _handle_env_get(self, args: List[str]) -> str:
        parser = self._create_parser("env_get", self._command_map['env_get']['help'])
        parsed_args = parser.parse_args(args)
        try:
            # Assuming EnvironmentTracker can be instantiated directly
            env_tracker = EnvironmentTracker()
            # Accessing protected method - consider making it public if used here
            # Or add a public method that calls the protected ones.
            # Let's assume a public 'get_details' method exists or should be added.
            # details = env_tracker.get_details() # Preferred
            # For now, use existing protected method if get_details doesn't exist
            if hasattr(env_tracker, 'get_details'):
                 details = env_tracker.get_details()
            elif hasattr(env_tracker, '_get_environment_details'):
                 details = env_tracker._get_environment_details()
            else:
                 return "Environment tracking details method not found."

            return f"Environment Details:\n{json.dumps(details, indent=2)}"
        except Exception as e:
            logger.error("Error getting environment details", exc_info=True)
            raise RuntimeError(f"Error getting environment details: {e}") from e

