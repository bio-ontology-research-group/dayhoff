import json
import shlex
from typing import Any, List, Dict, Optional, Protocol, Tuple, Set
import logging
import os
import io
import time
from pathlib import Path
import datetime
import argparse
import textwrap

# --- Rich for coloring ---
from rich.console import Console
from rich.theme import Theme

# --- Core Components ---
from .config import config, DayhoffConfig, ALLOWED_WORKFLOW_LANGUAGES, ALLOWED_EXECUTORS, get_executor_config_key, ALLOWED_LLM_PROVIDERS, ALLOWED_EXECUTION_MODES

# --- File System ---
from .fs.local import LocalFileSystem
from .fs.file_inspector import FileInspector

# --- HPC Bridge ---
from .hpc_bridge.credentials import CredentialManager
from .hpc_bridge.slurm_manager import SlurmManager
from .hpc_bridge.ssh_manager import SSHManager

# --- AI/LLM ---
try:
    from .llm.client import LLMClient, OpenAIClient, AnthropicClient
    from .llm.prompt import PromptManager
    from .workflows.llm_generator import LLMWorkflowGenerator
    LLM_CLIENTS_AVAILABLE = True
except ImportError:
    LLM_CLIENTS_AVAILABLE = False
    # Define placeholder Protocol for type hinting if imports fail
    class LLMClient(Protocol):
        def generate(self, prompt: str, context: Optional[Dict[str, Any]] = None, **kwargs) -> Dict[str, Any]: ...
        def get_usage(self) -> Dict[str, int]: ...
    class OpenAIClient(LLMClient):
         def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None, default_model: Optional[str] = None): ...
    class AnthropicClient(LLMClient):
         def __init__(self, api_key: Optional[str] = None, default_model: Optional[str] = None, base_url: Optional[str] = None): ...
    class PromptManager:
        def generate_prompt(self, template_name: str, context: Dict[str, Any]) -> str: ...
    class LLMWorkflowGenerator:
        def generate_workflow(self, description: str, max_attempts: int = 3) -> Dict[str, Any]: ...
        def list_workflows(self) -> List[Dict[str, Any]]: ...
        def delete_workflow(self, index: int) -> Dict[str, Any]: ...
        def get_workflow_inputs(self, index: int) -> Dict[str, Any]: ...
    logging.getLogger(__name__).warning("LLM client libraries not found or import failed. LLM features will be unavailable.")

# --- Handlers ---
from .handlers import (
    config as config_handlers,
    filesystem as fs_handlers,
    hpc as hpc_handlers,
    slurm as slurm_handlers,
    workflow as workflow_handlers,
    queue as queue_handlers,
    misc as misc_handlers
)

# Configure logging for the service
logger = logging.getLogger(__name__)
if not logging.getLogger().hasHandlers():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# --- Rich Console and Theme Setup ---
# Use a global console for direct output
console = Console(theme=Theme({
    "info": "dim cyan",
    "warning": "yellow",
    "error": "bold red",
    "repr.str": "none", # Avoid Rich adding quotes around output strings
}))


class DayhoffService:
    """Shared backend service for both CLI and notebook interfaces"""

    def __init__(self, dayhoff_config: Optional[DayhoffConfig] = None):
        self.config = dayhoff_config if dayhoff_config else config # Use global or passed config
        self.local_fs = LocalFileSystem()
        self.file_inspector = FileInspector(self.local_fs)
        self.active_ssh_manager: Optional[SSHManager] = None
        self.remote_cwd: Optional[str] = None
        self.local_cwd: str = os.getcwd() # Track local CWD
        self.llm_client: Optional[LLMClient] = None # Initialize LLM client as None
        self.prompt_manager: Optional[PromptManager] = None # Initialize prompt manager as None
        self.workflow_generator: Optional[LLMWorkflowGenerator] = None # Initialize workflow generator as None
        self.file_queue: List[str] = [] # Initialize the file queue
        self.console = console # Make console accessible to handlers
        self.LLM_CLIENTS_AVAILABLE = LLM_CLIENTS_AVAILABLE # Store flag for handlers
        logger.info(f"DayhoffService initialized. Local CWD: {self.local_cwd}")
        self._command_map = self._build_command_map() # Build command map after initialization


    def _build_command_map(self) -> Dict[str, Dict[str, Any]]:
        """Builds a map of commands, their handlers, and help text."""
        # Generate executor help dynamically
        executor_help_lines = []
        for lang, execs in sorted(ALLOWED_EXECUTORS.items()):
            key = get_executor_config_key(lang)
            executor_help_lines.append(f"      {key} <executor> : Set default executor for {lang.upper()}. Allowed: {', '.join(execs)}")

        executor_help_text = "\n".join(executor_help_lines)

        # Generate LLM provider help dynamically
        llm_provider_help = f"Allowed providers: {', '.join(ALLOWED_LLM_PROVIDERS)}"
        # Generate Execution mode help dynamically
        execution_mode_help = f"Allowed modes: {', '.join(ALLOWED_EXECUTION_MODES)}"


        # Map command names to handler functions from imported modules
        command_map = {
            "help": {"handler": misc_handlers.handle_help, "help": "Show help for commands. Usage: /help [command_name]"},
            "test": {
                "handler": misc_handlers.handle_test,
                "help": textwrap.dedent("""\
                    Run or show information about internal tests.
                    Usage: /test <subcommand> [options]
                    Subcommands:
                      llm        : Test connection to the configured Large Language Model.
                      script <name> : Run a specific test script from the 'examples' directory.
                      list       : List available test scripts in the 'examples' directory.""")
            },
            "config": {
                "handler": config_handlers.handle_config,
                "help": textwrap.dedent(f"""\
                    Manage Dayhoff configuration.
                    Usage: /config <subcommand> [options]
                    Subcommands:
                      get <section> <key> [default] : Get a specific config value.
                      set <section> <key> <value>   : Set a config value (and save). Type '/config set' for examples.
                      save                          : Manually save the current configuration.
                      show [section|ssh|llm|hpc|all]: Show a specific section, 'ssh' (HPC subset), 'llm', 'hpc', or all config.
                      slurm_singularity <on|off>    : Enable/disable default Singularity use for Slurm jobs.
                    HPC Settings (Section: HPC):
                      execution_mode <mode>         : Set execution mode ('direct' or 'slurm'). {execution_mode_help}
                      slurm_use_singularity <bool>  : Default to using Singularity for Slurm jobs (true/false). Use '/config slurm_singularity'.
                    Workflow Settings (Section: WORKFLOWS):
                      default_workflow_type <lang>  : Set preferred language. Use '/language <lang>' command.
                    {executor_help_text}
                    Allowed languages: {", ".join(ALLOWED_WORKFLOW_LANGUAGES)}
                    LLM Settings (Section: LLM):
                      provider <provider>           : Set the LLM provider. {llm_provider_help}
                      api_key <key>                 : Set the API key (use env vars for safety).
                      model <model_id>              : Set the specific model identifier.
                      base_url <url>                : Set a custom API base URL (optional).""")
            },
            "fs_head": {"handler": fs_handlers.handle_fs_head, "help": "Show the first N lines of a local file. Usage: /fs_head <file_path> [num_lines=10]"},
            "hpc_connect": {"handler": hpc_handlers.handle_hpc_connect, "help": "Establish a persistent SSH connection to the HPC. Usage: /hpc_connect"},
            "hpc_disconnect": {"handler": hpc_handlers.handle_hpc_disconnect, "help": "Close the persistent SSH connection to the HPC. Usage: /hpc_disconnect"},
            "hpc_run": {
                "handler": hpc_handlers.handle_hpc_run,
                "help": textwrap.dedent("""\
                    Execute a command on the HPC using the active connection.
                    Behavior depends on HPC.execution_mode config:
                      'direct': Runs the command directly via SSH.
                      'slurm': Wraps the command in 'srun --pty' for execution via Slurm.
                    Usage: /hpc_run <command_string>""")
            },
            "hpc_slurm_run": {"handler": slurm_handlers.handle_hpc_slurm_run, "help": "Execute a command explicitly within a Slurm allocation (srun). Usage: /hpc_slurm_run <command_string>"},
            "ls": {"handler": fs_handlers.handle_ls, "help": "List files in the current directory (local or remote) with colors. Usage: /ls [ls_options_ignored]"},
            "cd": {"handler": fs_handlers.handle_cd, "help": "Change the current directory (local or remote). Usage: /cd <directory>"},
            "hpc_slurm_submit": {
                "handler": slurm_handlers.handle_hpc_slurm_submit,
                "help": textwrap.dedent("""\
                    Submit a Slurm job script.
                    Usage: /hpc_slurm_submit <script_path> [options_json]
                      script_path : Path to the local Slurm script file.
                      options_json: Optional Slurm options as JSON string (e.g., '{"--nodes": 1, "--time": "01:00:00"}').
                                    Can include runner flags like '--singularity' or '--docker'.
                                    If HPC.slurm_use_singularity is true and no container flag is given, '--singularity' will be added by default.""")
            },
            "hpc_slurm_status": {
                "handler": slurm_handlers.handle_hpc_slurm_status,
                "help": textwrap.dedent("""\
                    Get Slurm job status. Defaults to user's jobs.
                    Usage: /hpc_slurm_status [--job-id <id> | --user | --all] [--waiting-summary]
                      --job-id <id> : Show status for a specific job ID.
                      --user        : Show status for the current user's jobs (default).
                      --all         : Show status for all jobs in the queue.
                      --waiting-summary: Include a summary of waiting times for pending jobs.""")
            },
            "hpc_cred_get": {"handler": hpc_handlers.handle_hpc_cred_get, "help": "Get HPC password for user (if stored). Usage: /hpc_cred_get <username>"},
            "wf_gen": {"handler": workflow_handlers.handle_wf_gen, "help": "Generate workflow using the configured language. Usage: /wf_gen <steps_json>"},
            "language": {
                "handler": workflow_handlers.handle_language,
                "help": textwrap.dedent(f"""\
                    View or set the preferred workflow *language* for generation.
                    Usage:
                      /language             : Show the current language setting.
                      /language <language>  : Set the language (e.g., /language cwl).
                    Allowed languages: {", ".join(ALLOWED_WORKFLOW_LANGUAGES)}
                    Note: To set the default *executor* for a language, use '/config set WORKFLOWS <lang>_default_executor <executor_name>'.""")
            },
            "queue": {
                "handler": queue_handlers.handle_queue,
                 "help": textwrap.dedent("""\
                    Manage the file queue for processing.
                    Usage: /queue <subcommand> [arguments]
                    Subcommands:
                      add <path...> : Add file(s) or directory(s) (recursive) to the queue. Paths are relative to CWD.
                      show          : Display the files currently in the queue.
                      remove <idx...> : Remove files from the queue by their index number (from /queue show).
                      clear         : Remove all files from the queue.""")
            },
            "workflow": {
                "handler": workflow_handlers.handle_workflow,
                "help": textwrap.dedent("""\
                    Manage LLM-generated workflows.
                    Usage: /workflow [subcommand] [arguments]
                    Subcommands:
                      list          : List all saved workflows.
                      show <index>  : Show details of a specific workflow.
                      generate <description> : Generate a new workflow using LLM.
                      delete <index> : Delete a specific workflow.
                      inputs <index> : List the required inputs for a specific workflow.
                    
                    Note: You can also generate workflows by typing a description without a leading '/'.""")
            },
        }
        return command_map

    def get_available_commands(self) -> List[str]:
        """Returns a list of available command names (without the leading '/')."""
        return list(self._command_map.keys())

    def get_status(self) -> Dict[str, Any]:
        """Returns the current connection status and context."""
        exec_mode = self.config.get_execution_mode()
        queue_size = len(self.file_queue) # Get queue size
        if self.active_ssh_manager and self.active_ssh_manager.is_connected:
            return {
                "mode": "connected",
                "host": self.active_ssh_manager.host,
                "user": self.active_ssh_manager.username,
                "cwd": self.remote_cwd or "~", # Provide default if None
                "exec_mode": exec_mode, # Add execution mode status
                "queue_size": queue_size, # Add queue size
            }
        else:
            return {
                "mode": "local",
                "host": None,
                "user": None,
                "cwd": self.local_cwd,
                "exec_mode": exec_mode, # Add execution mode status
                "queue_size": queue_size, # Add queue size
            }

    def execute_command(self, command: str, args: List[str]) -> Any:
        """
        Execute a registered command.
        The 'command' argument should be the command name *without* the leading '/'.
        Natural language input is handled directly by the REPL calling handle_natural_language_input.
        """
        logger.info(f"Executing command: {command} with args: {args}")

        # Check if the command name exists in our map
        if command in self._command_map:
            command_info = self._command_map[command]
            handler = command_info["handler"]
            try:
                # Call the handler, passing the service instance (self) and args
                result = handler(self, args)
                # Handlers should ideally print their own output or return structured data
                # If a handler returns a string, print it. Avoid double printing.
                if isinstance(result, str) and result:
                     self.console.print(result, overflow="ignore", crop=False, highlight=False) # Print simple string results
                elif result is not None:
                     # For non-string results, maybe use rich.pretty.pretty_repr or just log
                     logger.debug(f"Command /{command} returned non-string result: {type(result)}")
                logger.info(f"Command /{command} executed successfully.")
                return result # Return the result for potential programmatic use
            except argparse.ArgumentError as e:
                 logger.warning(f"Argument error for /{command}: {e}")
                 # ArgumentError message often includes usage, print it directly
                 self.console.print(f"[error]Argument Error:[/error] {e}")
                 return None # Indicate error
            except FileNotFoundError as e:
                 logger.warning(f"File/Directory not found during /{command}: {e}")
                 self.console.print(f"[error]Error:[/error] File or directory not found - {e}")
                 return None
            except NotADirectoryError as e:
                 logger.warning(f"Path is not a directory during /{command}: {e}")
                 self.console.print(f"[error]Error:[/error] Path is not a directory - {e}")
                 return None
            except PermissionError as e:
                 logger.warning(f"Permission denied during /{command}: {e}")
                 self.console.print(f"[error]Error:[/error] Permission denied - {e}")
                 return None
            except ConnectionError as e:
                 logger.error(f"Connection error during /{command}: {e}", exc_info=False)
                 self.console.print(f"[error]Connection Error:[/error] {e}")
                 return None
            except TimeoutError as e:
                 logger.error(f"Timeout error during /{command}: {e}", exc_info=False)
                 self.console.print(f"[error]Timeout Error:[/error] {e}")
                 return None
            except ValueError as e: # Catch validation errors (e.g., from config.set)
                 logger.warning(f"Validation error during /{command}: {e}")
                 self.console.print(f"[error]Validation Error:[/error] {e}")
                 return None
            except IndexError as e: # Catch index errors specifically (e.g., for /queue remove, /workflow delete/show/inputs)
                 logger.warning(f"Index error during /{command}: {e}")
                 self.console.print(f"[error]Index Error:[/error] {e}")
                 return None
            except NotImplementedError as e:
                 logger.warning(f"Feature not implemented for /{command}: {e}")
                 self.console.print(f"[warning]Not Implemented:[/warning] {e}")
                 return None
            except Exception as e:
                logger.error(f"Error executing command /{command}: {e}", exc_info=True)
                self.console.print(f"[error]Unexpected Error:[/error] {type(e).__name__}: {e}")
                return None
        else:
            # If command is NOT in the map, it's an unknown command.
            # Workflow generation is now handled explicitly in the REPL.
            logger.warning(f"Unknown command '/{command}' received.")
            self.console.print(f"[error]Unknown command:[/error] /{command}. Type /help for available commands.")
            return None

    # --- Helper Methods (kept within Service class as they use self) ---

    def _create_parser(self, prog: str, description: str, add_help: bool = False) -> argparse.ArgumentParser:
        """Creates an ArgumentParser instance for command parsing."""
        # Custom error handler to raise ArgumentError instead of exiting
        class RaiseArgumentParser(argparse.ArgumentParser):
            def error(self_parser, message): # Use self_parser to avoid conflict with service self
                # Get usage string
                usage = self_parser.format_usage()
                full_message = f"{message}\n{usage}"
                # Raise specific error type that execute_command can catch
                raise argparse.ArgumentError(None, full_message)

            def exit(self_parser, status=0, message=None): # Use self_parser
                 # Prevent sys.exit on --help
                 if message:
                     # Print help message manually to the console
                     # Use StringIO to capture help message if needed elsewhere
                     # help_io = io.StringIO()
                     # _print_message is protected, use print_message if available or print directly
                     # self_parser._print_message(message, help_io) # This might fail
                     self.console.print(message.strip()) # Print directly to service console
                     # help_io.getvalue().strip()) # Strip trailing newline from help
                 # Raise a specific exception or just return to signal help was printed
                 raise SystemExit() # Caught by help handler

        parser = RaiseArgumentParser(
            prog=f"/{prog}",
            description=description,
            add_help=add_help, # Let ArgumentParser handle --help generation
            formatter_class=argparse.RawDescriptionHelpFormatter, # Preserve formatting
            allow_abbrev=False # Disable abbreviation matching
        )
        return parser

    def _get_ssh_manager(self, connect_now: bool = False) -> SSHManager:
        """Helper to get an initialized SSHManager."""
        ssh_config_dict = self.config.get_ssh_config() # Renamed variable for clarity
        if not ssh_config_dict or not ssh_config_dict.get('host'):
            raise ConnectionError("HPC host configuration missing. Use '/config set HPC host <hostname>' and potentially other HPC settings.")
        try:
            # Pass the dictionary directly to SSHManager constructor
            # SSHManager's __init__ should handle extracting values and potentially using CredentialManager
            ssh_manager = SSHManager(ssh_config=ssh_config_dict)

            if connect_now:
                logger.debug("Attempting immediate connection in _get_ssh_manager...")
                # SSHManager's connect method should handle password prompting or keyring lookup if needed
                if not ssh_manager.connect(): # connect should raise on failure
                    raise ConnectionError(f"Failed to establish temporary SSH connection to {ssh_manager.host}.")
                logger.debug("Immediate connection successful.")
            return ssh_manager
        except KeyError as e:
             # This might happen if SSHManager expects a key not provided by get_ssh_config
             raise ConnectionError(f"Missing required SSH configuration key expected by SSHManager: {e}. Check [HPC] section and SSHManager implementation.") from e
        except ValueError as e:
             # Catch validation errors from within SSHManager.__init__
             raise ConnectionError(f"Failed to initialize SSH connection due to config error: {e}") from e
        except ConnectionError as e:
             raise e # Re-raise specific connection errors
        except Exception as e:
             logger.error(f"Unexpected error initializing SSH connection", exc_info=True)
             raise ConnectionError(f"Failed to initialize SSH connection: {e}") from e

    def _get_slurm_manager(self) -> SlurmManager:
        """Helper to get an initialized SlurmManager with an active connection."""
        logger.debug("Getting or creating SSH connection for Slurm manager.")
        # Use the active connection if available and connected, otherwise create temporary one
        if self.active_ssh_manager and self.active_ssh_manager.is_connected:
             ssh_for_slurm = self.active_ssh_manager
             is_temp_ssh = False
             logger.debug("Using active persistent SSH connection for Slurm.")
        else:
             ssh_for_slurm = self._get_ssh_manager(connect_now=True) # Create temporary connection
             is_temp_ssh = True
             logger.debug("Created temporary SSH connection for Slurm.")

        try:
            # Pass the SSHManager instance to SlurmManager
            slurm_manager = SlurmManager(ssh_manager=ssh_for_slurm)
            # Store the temporary connection info if needed for later disconnect
            slurm_manager._is_temp_ssh = is_temp_ssh # Add flag to know if we need to close it
            return slurm_manager
        except Exception as e:
             if is_temp_ssh and ssh_for_slurm:
                 try: ssh_for_slurm.disconnect()
                 except Exception: pass
             logger.error(f"Failed to initialize Slurm manager", exc_info=True)
             raise ConnectionError(f"Failed to initialize Slurm manager: {e}") from e

    def _close_slurm_manager_ssh(self, slurm_manager: Optional[SlurmManager]):
         """Closes the SSH connection associated with a SlurmManager if it was temporary."""
         if slurm_manager and getattr(slurm_manager, '_is_temp_ssh', False) and slurm_manager.ssh_manager:
             try:
                 slurm_manager.ssh_manager.disconnect()
                 logger.debug("Closed temporary SSH connection used by Slurm manager.")
             except Exception as close_err:
                 logger.warning(f"Error closing temporary SSH connection after Slurm operation: {close_err}")

    def _resolve_path(self, relative_path: str) -> Tuple[str, str]:
        """
        Resolves a relative path to an absolute path, returning both the
        absolute path and the CWD used for resolution. Handles local vs remote.
        """
        status = self.get_status()
        if status['mode'] == 'connected':
            # Remote Path Resolution
            if not self.active_ssh_manager or self.remote_cwd is None:
                raise ConnectionError("Cannot resolve remote path: Not connected or CWD unknown.")

            # Use `realpath` command on remote host for canonical path
            # Need to change to the CWD first
            command = f"cd {shlex.quote(self.remote_cwd)} && realpath -e --canonicalize-missing {shlex.quote(relative_path)}"
            try:
                abs_path = self.active_ssh_manager.execute_command(command, timeout=15).strip()
                # Check if realpath succeeded (it might return empty or error message on failure)
                if not abs_path.startswith('/'):
                    # `realpath -e` returns non-zero status if path doesn't exist
                    # execute_command should raise RuntimeError in that case.
                    # If we get here, it means SSH command succeeded but output is weird.
                    # Let's try a simpler check using `test -e` before returning failure.
                     test_cmd = f"cd {shlex.quote(self.remote_cwd)} && test -e {shlex.quote(relative_path)}"
                     try:
                         self.active_ssh_manager.execute_command(test_cmd, timeout=10)
                         # If test -e succeeds, maybe realpath isn't available? Fallback.
                         # Construct path manually (less robust for .. etc.)
                         # We need a more reliable way if realpath fails/is not present.
                         # Let's assume execute_command raises error if path doesn't exist based on realpath -e exit code.
                         # If we are here without an error, realpath output might be unexpected.
                         logger.warning(f"Remote 'realpath' command returned unexpected output: '{abs_path}' for path '{relative_path}'. Falling back to simpler check.")
                         raise FileNotFoundError(f"Could not resolve remote path: '{relative_path}' relative to '{self.remote_cwd}'. 'realpath' failed.")

                     except (RuntimeError, TimeoutError): # test -e failed or timed out
                          raise FileNotFoundError(f"Remote path not found: '{relative_path}' relative to '{self.remote_cwd}'.")

                return abs_path, self.remote_cwd
            except RuntimeError as e:
                # Capture command failure which likely means path doesn't exist
                raise FileNotFoundError(f"Remote path not found or error resolving '{relative_path}' relative to '{self.remote_cwd}': {e}") from e
            except (ConnectionError, TimeoutError) as e:
                 raise ConnectionError(f"Connection error resolving remote path '{relative_path}': {e}") from e

        else:
            # Local Path Resolution
            target_path = Path(self.local_cwd) / relative_path
            try:
                # Use resolve(strict=True) to ensure the path exists
                abs_path_obj = target_path.resolve(strict=True)
                return str(abs_path_obj), self.local_cwd
            except FileNotFoundError as e:
                raise FileNotFoundError(f"Local path not found: '{target_path}'") from e
            except Exception as e: # Catch potential permission errors etc. during resolve
                 raise RuntimeError(f"Error resolving local path '{target_path}': {e}") from e

    def _get_path_type(self, abs_path: str) -> str:
        """
        Determines if an absolute path is a file or directory. Handles local vs remote.
        Returns 'file', 'directory', or raises error.
        """
        status = self.get_status()
        if status['mode'] == 'connected':
            if not self.active_ssh_manager:
                raise ConnectionError("Cannot check remote path type: Not connected.")
            try:
                # Use test -d and test -f
                # Try checking for directory first
                self.active_ssh_manager.execute_command(f"test -d {shlex.quote(abs_path)}", timeout=10)
                return 'directory'
            except RuntimeError:
                # If test -d fails, try test -f
                try:
                    self.active_ssh_manager.execute_command(f"test -f {shlex.quote(abs_path)}", timeout=10)
                    return 'file'
                except RuntimeError as e:
                    # If test -f also fails, the path likely doesn't exist, isn't a file/dir, or lacks permissions
                    raise FileNotFoundError(f"Error checking type or path not found for remote '{abs_path}': {e}") from e
                except (ConnectionError, TimeoutError) as e:
                    raise ConnectionError(f"Connection error checking type of remote path '{abs_path}': {e}") from e
            except (ConnectionError, TimeoutError) as e:
                raise ConnectionError(f"Connection error checking type of remote path '{abs_path}': {e}") from e
        else:
            # Local check
            path_obj = Path(abs_path)
            if not path_obj.exists(): # Should have been caught by resolve
                 raise FileNotFoundError(f"Local path does not exist: {abs_path}")
            if path_obj.is_dir():
                return 'directory'
            elif path_obj.is_file():
                return 'file'
            else:
                 raise FileNotFoundError(f"Local path exists but is not a file or directory: {abs_path}")


    def _list_remote_files_recursive(self, abs_dir_path: str) -> List[str]:
        """
        Recursively lists all *files* within a remote directory using SSH.
        Returns a list of absolute file paths.
        """
        if not self.active_ssh_manager:
            raise ConnectionError("Cannot list remote files: Not connected.")

        # Use find to list only files (-type f) and print their paths (%p) relative to the start dir
        # Use -print0 for safer handling of filenames with whitespace/newlines
        command = f"find {shlex.quote(abs_dir_path)} -type f -print0"
        try:
            output = self.active_ssh_manager.execute_command(command, timeout=120) # Longer timeout for deep dirs
             # Split by null character, filter out empty strings resulting from trailing null
            file_paths = [p for p in output.split('\0') if p]
            # Ensure paths are absolute (find should already provide them based on the absolute input path)
            # Basic check:
            valid_paths = [p for p in file_paths if p.startswith(abs_dir_path)]
            if len(valid_paths) != len(file_paths):
                 logger.warning(f"Some paths from 'find' did not start with the base directory '{abs_dir_path}'. Output: {output}")
                 # Decide whether to return only valid_paths or raise error
                 # For now, return only the seemingly valid ones
            return valid_paths
        except RuntimeError as e:
             # Command failed, possibly directory not found or permission error
             raise RuntimeError(f"Error listing files in remote directory '{abs_dir_path}': {e}") from e
        except (ConnectionError, TimeoutError) as e:
             raise ConnectionError(f"Connection error listing files in remote directory '{abs_dir_path}': {e}") from e

    def _get_llm_client(self) -> LLMClient:
        """Initializes and returns the LLMClient instance based on config."""
        if not self.LLM_CLIENTS_AVAILABLE:
             raise ImportError("LLM client libraries not available.")

        # Check if client is already initialized and config hasn't changed significantly
        # (Simple check: just re-initialize if None for now)
        # TODO: Add more robust check if config has changed (e.g., compare key config values)
        if self.llm_client is None:
            llm_config = self.config.get_llm_config()
            provider = llm_config.get('provider')
            api_key = llm_config.get('api_key')
            base_url = llm_config.get('base_url')
            model = llm_config.get('model')

            if not provider:
                raise ValueError("LLM provider not configured. Set [LLM] provider.")
            if not api_key:
                # Check if the provider is one that typically requires a key
                if provider in config.LLM_API_KEY_ENV_VARS:
                     env_var = config.LLM_API_KEY_ENV_VARS[provider]
                     raise ValueError(f"API key for provider '{provider}' not found in config [LLM].api_key or environment variable {env_var}.")
                else:
                     logger.warning(f"API key for provider '{provider}' not found, but it might not be required.")
            if not model:
                raise ValueError("LLM model not configured. Set [LLM] model.")

            logger.info(f"Initializing LLM client for provider: {provider}, model: {model}")

            try:
                # Instantiate the correct client based on provider
                if provider == 'openai' or provider == 'openrouter':
                    # Pass relevant parameters from llm_config
                    self.llm_client = OpenAIClient(
                        api_key=api_key,
                        base_url=base_url,
                        default_model=model
                    )
                elif provider == 'anthropic':
                     # Pass relevant parameters from llm_config
                     # Note: AnthropicClient now also accepts base_url if needed
                     self.llm_client = AnthropicClient(
                         api_key=api_key,
                         default_model=model,
                         base_url=base_url # Pass base_url if provided/needed
                     )
                else:
                    # This case should be prevented by config validation, but handle defensively
                    raise ValueError(f"Unsupported LLM provider: {provider}")
                logger.info(f"LLM client for {provider} initialized successfully.")
            except TypeError as e:
                 # Catch potential mismatches between arguments passed and client __init__ signature
                 logger.error(f"Failed to initialize LLM client for {provider} due to TypeError: {e}", exc_info=True)
                 raise RuntimeError(f"Failed to initialize LLM client for {provider}: {e}. Check client constructor arguments.") from e
            except Exception as e:
                 logger.error(f"Failed to initialize LLM client for {provider}: {e}", exc_info=True)
                 # Ensure client remains None on failure
                 self.llm_client = None
                 raise RuntimeError(f"Failed to initialize LLM client for {provider}: {e}") from e

        return self.llm_client

    def _get_prompt_manager(self) -> PromptManager:
        """Get or initialize the prompt manager"""
        if self.prompt_manager is None:
            self.prompt_manager = PromptManager()
        return self.prompt_manager
        
    def _get_workflow_generator(self) -> LLMWorkflowGenerator:
        """Get or initialize the workflow generator"""
        if self.workflow_generator is None:
            llm_client = self._get_llm_client()
            prompt_manager = self._get_prompt_manager()
            self.workflow_generator = LLMWorkflowGenerator(llm_client, prompt_manager)
        return self.workflow_generator

    # --- Natural Language Handling ---
    # This method is called directly by the REPL for non-command input
    def handle_natural_language_input(self, text: str) -> None:
        """Handles non-command input, currently routes to workflow generation."""
        logger.info(f"Handling natural language input: {text}")
        # Currently, the only non-command action is workflow generation
        # Use the existing workflow generation handler function from the workflow handler module
        try:
            # Pass self (the service instance) to the handler
            workflow_handlers._handle_workflow_generation(self, text)
        except Exception as e:
            # Catch errors during workflow generation attempt
            logger.error(f"Error attempting workflow generation for input '{text}': {e}", exc_info=True)
            self.console.print(f"[error]Workflow generation failed:[/error] {e}")

