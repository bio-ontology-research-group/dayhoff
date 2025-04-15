import json
import shlex
from typing import Any, List, Dict, Optional
import logging # Added logging
import os # Added os import

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
            # Renamed from test_command to test
            "test": {"handler": self._handle_test, "help": "A simple test command. Usage: /test [--param key=value]"},
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
            "hpc_slurm_status": {"handler": self._handle_hpc_slurm_status, "help": "Get Slurm job status. Usage: /hpc_slurm_status <job_id>"},
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
                 return f"Argument Error: {e}\nUsage: {command_info.get('help', 'No help available.')}"
            except FileNotFoundError as e: # Catch file not found specifically
                 logger.warning(f"File not found during /{command}: {e}")
                 return f"Error: File not found - {e}"
            except Exception as e:
                logger.error(f"Error executing command /{command}: {e}", exc_info=True)
                # Log the exception details?
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
                help_summary = info['help'].split('.')[0]
                help_lines.append(f"  /{cmd:<20} - {help_summary}")
            help_lines.append("\nType /help <command_name> for more details.")
            return "\n".join(help_lines)
        else:
            # Specific command help
            cmd_name = args[0]
            if cmd_name.startswith('/'): # Allow /help /command_name
                cmd_name = cmd_name[1:]
            if cmd_name in self._command_map:
                # Return the full help text for the specific command
                return self._command_map[cmd_name]['help']
            else:
                return f"Unknown command: /{cmd_name}"

    # --- Argument Parsers (Example for one command) ---
    def _create_parser(self, prog: str, description: str) -> argparse.ArgumentParser:
        """Creates an ArgumentParser instance for command parsing."""
        # Prevent argparse from exiting the program on error
        parser = argparse.ArgumentParser(prog=f"/{prog}", description=description, add_help=False)
        # Override error handling to raise exception instead of exiting
        def error(message):
            # Include the command name in the error message for clarity
            raise argparse.ArgumentError(None, f"Invalid arguments for /{prog}: {message}")
        parser.error = error
        return parser

    # --- Test Command Handler ---
    # Renamed from _handle_test_command to _handle_test
    def _handle_test(self, args: List[str]) -> str:
        """Handles the simple /test command."""
        # Updated parser prog name
        parser = self._create_parser("test", "A simple test command.")
        # Example of accepting arbitrary key=value pairs
        parser.add_argument('--param', action='append', help="Parameters in key=value format")
        parsed_args = parser.parse_args(args)

        params = {}
        if parsed_args.param:
            for p in parsed_args.param:
                if '=' in p:
                    key, value = p.split('=', 1)
                    params[key] = value
                else:
                    # Handle case where value is not provided, maybe treat as flag or error
                    params[p] = True # Or raise argparse.ArgumentError

        # Construct the output message based on click test
        # Updated output message to reflect command name
        output = f"Executed /test command with params: {params}"
        logger.info(f"Test command executed with params: {params}")
        return output


    # --- Config Handlers ---
    def _handle_config_get(self, args: List[str]) -> Any:
        parser = self._create_parser("config_get", "Get a config value.")
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
        parser = self._create_parser("config_ssh", "Get SSH configuration.")
        # No arguments expected, parse to catch extra args
        parsed_args = parser.parse_args(args)
        ssh_config = self.config.get_ssh_config()
        if not ssh_config:
            return "SSH configuration not found or empty."
        return json.dumps(ssh_config, indent=2)


    def _handle_config_save(self, args: List[str]) -> str:
        parser = self._create_parser("config_save", "Save current configuration.")
        parsed_args = parser.parse_args(args)
        try:
            self.config.save_config()
            config_path = self.config._get_config_path() # Assuming this method exists
            return f"Configuration saved successfully to {config_path}."
        except Exception as e:
            logger.error("Error saving configuration", exc_info=True)
            return f"Error saving configuration: {e}"

    # --- File System Handlers ---
    def _handle_fs_find_seq(self, args: List[str]) -> str:
        parser = self._create_parser("fs_find_seq", "Find sequence files.")
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
             return f"Error: {e}"
        except Exception as e:
            logger.error(f"Error finding sequence files in {parsed_args.root_path}", exc_info=True)
            return f"Error finding sequence files: {e}"

    def _handle_fs_head(self, args: List[str]) -> str:
        """Handles the /fs_head command."""
        parser = self._create_parser("fs_head", "Show the first N lines of a local file.")
        parser.add_argument("file_path", help="Path to the local file")
        parser.add_argument("num_lines", type=int, nargs='?', default=10, help="Number of lines to show (default: 10)")
        parsed_args = parser.parse_args(args)

        if parsed_args.num_lines <= 0:
            raise argparse.ArgumentError(None, "Number of lines must be positive.")

        try:
            # Use the FileInspector instance
            lines = list(self.file_inspector.head(parsed_args.file_path, parsed_args.num_lines))
            if not lines:
                return f"File is empty or could not be read: {parsed_args.file_path}"
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
        parser = self._create_parser("fs_detect_format", "Detect the format of a local file.")
        parser.add_argument("file_path", help="Path to the local file")
        parsed_args = parser.parse_args(args)

        try:
            # Use the LocalFileSystem instance's method
            file_format = self.local_fs.detect_format(parsed_args.file_path)
            if file_format:
                return f"Detected format for '{parsed_args.file_path}': {file_format}"
            else:
                return f"Could not detect format for '{parsed_args.file_path}'."
        except FileNotFoundError:
             raise FileNotFoundError(f"File not found at '{parsed_args.file_path}'")
        except Exception as e:
            logger.error(f"Error detecting format for file {parsed_args.file_path}", exc_info=True)
            raise e


    # --- Git Tracking Handlers ---
    def _handle_git_record(self, args: List[str]) -> str:
        parser = self._create_parser("git_record", "Record a custom event.")
        parser.add_argument("event_type", help="Type of the event (e.g., 'manual_step')")
        parser.add_argument("metadata_json", help="Metadata as a JSON string (e.g., '{\"key\": \"value\"}')")
        parser.add_argument("files_json", nargs='?', default='{}', help="Optional dictionary of files to track as JSON string (e.g., '{\"input.txt\": \"path/to/input.txt\"}')")
        parsed_args = parser.parse_args(args)

        try:
            metadata = json.loads(parsed_args.metadata_json)
            # Ensure metadata is a dictionary
            if not isinstance(metadata, dict):
                raise ValueError("Metadata JSON must decode to a dictionary.")

            files_dict = json.loads(parsed_args.files_json)
            if not isinstance(files_dict, dict):
                 raise ValueError("Files JSON must decode to a dictionary.")

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
            return f"Invalid JSON provided: {e}"
        except ValueError as e: # Catch our custom validation error
            return f"Invalid input: {e}"
        except Exception as e:
            logger.error("Error recording git event", exc_info=True)
            return f"Error recording event: {e}"

    def _handle_git_log(self, args: List[str]) -> str:
        """Handles the /git_log command."""
        parser = self._create_parser("git_log", "Show git event log.")
        parser.add_argument("limit", type=int, nargs='?', default=10, help="Maximum number of events to show (default: 10)")
        parsed_args = parser.parse_args(args)

        if parsed_args.limit <= 0:
            raise argparse.ArgumentError(None, "Limit must be positive.")

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
            raise ConnectionError("SSH configuration not found. Use /config_set or edit config file.")
        # Assuming SSHManager takes ssh_config dict directly
        # Adjust if it expects specific keys or a different format
        return SSHManager(ssh_config=ssh_config)

    def _get_file_synchronizer(self) -> FileSynchronizer:
        """Helper to get an initialized FileSynchronizer."""
        ssh_config = self.config.get_ssh_config()
        if not ssh_config:
            raise ConnectionError("SSH configuration not found.")
        # Assuming FileSynchronizer takes ssh_config dict directly
        return FileSynchronizer(ssh_config=ssh_config)

    def _get_slurm_manager(self) -> SlurmManager:
        """Helper to get an initialized SlurmManager."""
        ssh_config = self.config.get_ssh_config()
        if not ssh_config:
            raise ConnectionError("SSH configuration not found.")
        # Assuming SlurmManager takes ssh_config dict directly
        return SlurmManager(ssh_config=ssh_config)


    def _handle_hpc_sync_up(self, args: List[str]) -> str:
        parser = self._create_parser("hpc_sync_up", "Upload file(s) to HPC.")
        parser.add_argument("local_path", help="Local file or glob pattern (e.g., 'data/*.fastq')")
        parser.add_argument("remote_dir", help="Remote destination directory")
        parsed_args = parser.parse_args(args)

        try:
            synchronizer = self._get_file_synchronizer()

            # FileSynchronizer.upload_files expects List[str], handle potential glob
            import glob
            local_paths = glob.glob(parsed_args.local_path)
            if not local_paths:
                return f"Warning: No local files found matching '{parsed_args.local_path}'. Nothing uploaded."

            logger.info(f"Uploading {len(local_paths)} files to {parsed_args.remote_dir}...")
            success = synchronizer.upload_files(local_paths, parsed_args.remote_dir)
            if success:
                return f"Successfully uploaded {len(local_paths)} file(s) matching '{parsed_args.local_path}' to {parsed_args.remote_dir}."
            else:
                # FileSynchronizer should ideally raise exceptions on failure
                return "File upload failed. Check logs for details."
        except ConnectionError as e: # Catch specific error from helper
            return f"Error: {e}"
        except Exception as e:
            logger.error("Error during HPC upload", exc_info=True)
            return f"Error during upload: {e}"

    def _handle_hpc_sync_down(self, args: List[str]) -> str:
        parser = self._create_parser("hpc_sync_down", "Download file(s) from HPC.")
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
            if success:
                 # We don't know exactly how many files were downloaded if it was a glob
                 return f"Successfully downloaded '{parsed_args.remote_path}' to {parsed_args.local_dir}."
            else:
                 return "File download failed. Check logs for details."
        except ConnectionError as e:
            return f"Error: {e}"
        except Exception as e:
            logger.error("Error during HPC download", exc_info=True)
            return f"Error during download: {e}"

    def _handle_hpc_ssh_cmd(self, args: List[str]) -> str:
        if not args:
             # Use the parser to raise the standard argument error
             parser = self._create_parser("hpc_ssh_cmd", "Execute a command via SSH.")
             parser.add_argument("command", nargs='+', help="The command string to execute remotely")
             parser.parse_args(args) # This will raise the error

        command_string = " ".join(args) # Rejoin args into the command

        try:
            ssh_manager = self._get_ssh_manager()
            logger.info(f"Executing SSH command: {command_string}")
            output = ssh_manager.execute_command(command_string)
            # Return output, potentially trimming whitespace
            return f"SSH command output:\n---\n{output.strip()}\n---"
        except ConnectionError as e:
            return f"Error: {e}"
        except Exception as e:
            logger.error("Error executing SSH command", exc_info=True)
            return f"Error executing SSH command: {e}"

    def _handle_hpc_slurm_submit(self, args: List[str]) -> str:
        parser = self._create_parser("hpc_slurm_submit", "Submit a Slurm job.")
        parser.add_argument("script_path", help="Path to the local Slurm script file")
        parser.add_argument("options_json", nargs='?', default='{}', help="Optional Slurm options as JSON string (e.g., '{\"--nodes\": 1, \"--time\": \"01:00:00\"}')")
        parsed_args = parser.parse_args(args)

        try:
            slurm_manager = self._get_slurm_manager()

            options = json.loads(parsed_args.options_json)
            if not isinstance(options, dict):
                raise ValueError("Options JSON must decode to a dictionary.")

            # Read the script content from the local path
            script_path = os.path.abspath(parsed_args.script_path)
            if not os.path.isfile(script_path):
                 raise FileNotFoundError(f"Script file not found at '{script_path}'")

            with open(script_path, 'r') as f:
                script_content = f.read()

            logger.info(f"Submitting Slurm job from script: {script_path} with options: {options}")
            job_id = slurm_manager.submit_job(script_content, options)
            return f"Slurm job submitted with ID: {job_id}"
        except ConnectionError as e:
            return f"Error: {e}"
        except FileNotFoundError as e:
            return f"Error: {e}"
        except json.JSONDecodeError as e:
            return f"Invalid JSON provided for options: {e}"
        except ValueError as e: # Catch our options validation error
             return f"Invalid input: {e}"
        except Exception as e:
            logger.error("Error submitting Slurm job", exc_info=True)
            return f"Error submitting Slurm job: {e}"

    def _handle_hpc_slurm_status(self, args: List[str]) -> str:
        parser = self._create_parser("hpc_slurm_status", "Get Slurm job status.")
        parser.add_argument("job_id", help="Slurm job ID")
        parsed_args = parser.parse_args(args)

        try:
            slurm_manager = self._get_slurm_manager()
            logger.info(f"Getting status for Slurm job ID: {parsed_args.job_id}")
            status = slurm_manager.get_job_status(parsed_args.job_id)
            # Format the status dict for pretty printing
            return json.dumps(status, indent=2)
        except ConnectionError as e:
            return f"Error: {e}"
        except Exception as e:
            logger.error(f"Error getting Slurm job status for {parsed_args.job_id}", exc_info=True)
            return f"Error getting Slurm job status: {e}"

    def _handle_hpc_cred_get(self, args: List[str]) -> str:
        parser = self._create_parser("hpc_cred_get", "Get HPC password for user (if stored securely).")
        parser.add_argument("username", help="HPC username")
        parsed_args = parser.parse_args(args)

        try:
            # Assuming CredentialManager can be instantiated directly
            # It likely uses the 'keyring' library backend
            cred_manager = CredentialManager()
            # Construct a service name (adjust as needed based on CredentialManager impl)
            service_name = f"dayhoff_hpc_{parsed_args.username}"
            password = cred_manager.get_password(service_name=service_name, username=parsed_args.username) # Adjust args if needed
            if password:
                 # Security: Do NOT return the password itself to the REPL!
                 logger.info(f"Password found for user '{parsed_args.username}' in keyring.")
                 return f"Password found for user '{parsed_args.username}' in system keyring."
            else:
                 logger.info(f"No stored password found for user '{parsed_args.username}' in keyring.")
                 return f"No stored password found for user '{parsed_args.username}' in system keyring."
        except Exception as e:
            # Catch potential keyring backend errors
            logger.error(f"Error retrieving credentials for {parsed_args.username}", exc_info=True)
            return f"Error retrieving credentials: {e}"

    # --- AI/LLM Handlers ---
    def _handle_ai_suggest(self, args: List[str]) -> str:
        parser = self._create_parser("ai_suggest", "Suggest analysis based on data type and metadata.")
        parser.add_argument("data_type", help="Type of data (e.g., 'fastq', 'vcf', 'bam')")
        parser.add_argument("metadata_json", help="Metadata relevant to the data as JSON string (e.g., '{\"sample_id\": \"s1\", \"condition\": \"treated\"}')")
        parsed_args = parser.parse_args(args)

        try:
            metadata = json.loads(parsed_args.metadata_json)
            if not isinstance(metadata, dict):
                raise ValueError("Metadata JSON must decode to a dictionary.")

            # Assuming AnalysisAdvisor can be instantiated directly
            # It might need configuration (e.g., API keys) passed via self.config
            advisor = AnalysisAdvisor(config=self.config) # Pass config if needed
            logger.info(f"Requesting analysis suggestion for data type '{parsed_args.data_type}'")
            suggestion = advisor.suggest_analysis(parsed_args.data_type, metadata)
            return f"Analysis Suggestion:\n---\n{suggestion}\n---"
        except json.JSONDecodeError as e:
            return f"Invalid JSON provided for metadata: {e}"
        except ValueError as e:
             return f"Invalid input: {e}"
        except Exception as e:
            logger.error("Error getting analysis suggestion", exc_info=True)
            return f"Error getting analysis suggestion: {e}"

    def _handle_llm_budget(self, args: List[str]) -> str:
        parser = self._create_parser("llm_budget", "Show remaining LLM token budget.")
        parsed_args = parser.parse_args(args)
        try:
            # Assuming TokenBudget might read limits from config
            budget = TokenBudget(config=self.config) # Pass config if needed
            remaining = budget.remaining()
            limit = budget.limit # Assuming a 'limit' property exists
            return f"LLM Token Budget: {remaining} remaining / {limit} limit"
        except Exception as e:
            logger.error("Error getting token budget", exc_info=True)
            return f"Error getting token budget: {e}"

    def _handle_llm_context_update(self, args: List[str]) -> str:
        parser = self._create_parser("llm_context_update", "Update LLM context.")
        parser.add_argument("updates_json", help="Updates as JSON string (dictionary)")
        parsed_args = parser.parse_args(args)

        try:
            updates = json.loads(parsed_args.updates_json)
            if not isinstance(updates, dict):
                raise ValueError("Updates JSON must decode to a dictionary.")

            # Assuming ContextManager might be stateful or read from config/disk
            context_manager = ContextManager(config=self.config) # Pass config if needed
            context_manager.update(updates)
            logger.info(f"LLM context updated with keys: {list(updates.keys())}")
            return "LLM context updated."
        except json.JSONDecodeError as e:
            return f"Invalid JSON provided for updates: {e}"
        except ValueError as e:
             return f"Invalid input: {e}"
        except Exception as e:
            logger.error("Error updating LLM context", exc_info=True)
            return f"Error updating LLM context: {e}"

    def _handle_llm_context_get(self, args: List[str]) -> str:
        parser = self._create_parser("llm_context_get", "Get current LLM context.")
        parsed_args = parser.parse_args(args)
        try:
            # Assuming ContextManager might be stateful or read from config/disk
            context_manager = ContextManager(config=self.config) # Pass config if needed
            context = context_manager.get()
            if not context:
                return "LLM context is currently empty."
            return f"Current LLM Context:\n{json.dumps(context, indent=2)}"
        except Exception as e:
            logger.error("Error getting LLM context", exc_info=True)
            return f"Error getting LLM context: {e}"

    # --- Workflow & Environment Handlers ---
    def _handle_wf_gen_cwl(self, args: List[str]) -> str:
        parser = self._create_parser("wf_gen_cwl", "Generate CWL workflow from steps.")
        parser.add_argument("steps_json", help="Workflow steps definition as JSON string (list or dict)")
        # Add optional output file argument?
        # parser.add_argument("-o", "--output", help="Optional path to save the generated CWL file")
        parsed_args = parser.parse_args(args)

        try:
            steps = json.loads(parsed_args.steps_json)
            # Basic validation (expecting a list or dict)
            if not isinstance(steps, (list, dict)):
                 raise ValueError("Steps JSON must decode to a list or dictionary.")

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
                return "CWL generation is not yet implemented."
            return f"Generated CWL Workflow:\n---\n{cwl_output}\n---"
        except json.JSONDecodeError as e:
            return f"Invalid JSON provided for steps: {e}"
        except ValueError as e:
             return f"Invalid input: {e}"
        except Exception as e:
            logger.error("Error generating CWL workflow", exc_info=True)
            return f"Error generating CWL workflow: {e}"

    def _handle_wf_gen_nextflow(self, args: List[str]) -> str:
        parser = self._create_parser("wf_gen_nextflow", "Generate Nextflow workflow from steps.")
        parser.add_argument("steps_json", help="Workflow steps definition as JSON string (list or dict)")
        # parser.add_argument("-o", "--output", help="Optional path to save the generated Nextflow script")
        parsed_args = parser.parse_args(args)

        try:
            steps = json.loads(parsed_args.steps_json)
            if not isinstance(steps, (list, dict)):
                 raise ValueError("Steps JSON must decode to a list or dictionary.")

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
                return "Nextflow generation is not yet implemented."
            return f"Generated Nextflow Workflow:\n---\n{nf_output}\n---"
        except json.JSONDecodeError as e:
            return f"Invalid JSON provided for steps: {e}"
        except ValueError as e:
             return f"Invalid input: {e}"
        except Exception as e:
            logger.error("Error generating Nextflow workflow", exc_info=True)
            return f"Error generating Nextflow workflow: {e}"

    def _handle_env_get(self, args: List[str]) -> str:
        parser = self._create_parser("env_get", "Get environment details (Python version, packages, etc.).")
        parsed_args = parser.parse_args(args)
        try:
            # Assuming EnvironmentTracker can be instantiated directly
            env_tracker = EnvironmentTracker()
            # Accessing protected method - consider making it public if used here
            # Or add a public method that calls the protected ones.
            # Let's assume a public 'get_details' method exists or should be added.
            # details = env_tracker.get_details() # Preferred
            details = env_tracker._get_environment_details() # Using existing protected method
            return f"Environment Details:\n{json.dumps(details, indent=2)}"
        except Exception as e:
            logger.error("Error getting environment details", exc_info=True)
            return f"Error getting environment details: {e}"

