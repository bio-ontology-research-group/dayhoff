import json
import shlex
from typing import Any, List, Dict, Optional, Protocol, Tuple, Set # Added Protocol, Tuple, Set
import logging # Added logging
import os # Added os import
import subprocess # Added for running test scripts
import sys # Added for getting python executable
import textwrap # For formatting help text
import shlex # For shell quoting
import io # For capturing rich output
import time # For LLM test timeout
from pathlib import Path # For local path operations

# --- Rich for coloring ---
from rich.console import Console
from rich.text import Text
from rich.columns import Columns
from rich.theme import Theme
from rich.panel import Panel
from rich.live import Live
from rich.spinner import Spinner
from rich.table import Table # Added for queue show

# --- Core Components ---
# Import the GLOBAL config instance and renamed ALLOWED_WORKFLOW_LANGUAGES
from .config import config, DayhoffConfig, ALLOWED_WORKFLOW_LANGUAGES, ALLOWED_EXECUTORS, get_executor_config_key, ALLOWED_LLM_PROVIDERS, ALLOWED_EXECUTION_MODES # Updated import
# Removed GitTracker import as /git_* commands are removed

# --- File System ---
# Removed BioDataExplorer import as /fs_find_seq is removed
from .fs.local import LocalFileSystem
from .fs.file_inspector import FileInspector

# --- HPC Bridge ---
from .hpc_bridge.credentials import CredentialManager
# Removed FileSynchronizer import as /hpc_sync_* commands are removed
from .hpc_bridge.slurm_manager import SlurmManager
from .hpc_bridge.ssh_manager import SSHManager

# --- AI/LLM ---
# Placeholder imports for LLM clients - replace with actual imports when available
try:
    # Attempt to import real clients if they exist and are installed
    from .llm.client import LLMClient, OpenAIClient, AnthropicClient
    LLM_CLIENTS_AVAILABLE = True
except ImportError:
    LLM_CLIENTS_AVAILABLE = False
    # Define placeholder Protocol for type hinting if imports fail
    class LLMClient(Protocol):
        # Update protocol to match expected generate signature better
        def generate(self, prompt: str, context: Optional[Dict[str, Any]] = None, **kwargs) -> Dict[str, Any]:
            ...
        def get_usage(self) -> Dict[str, int]:
            ...
    # Define placeholder classes inheriting from the protocol
    class OpenAIClient(LLMClient):
         def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None, default_model: Optional[str] = None): ...
    class AnthropicClient(LLMClient):
         def __init__(self, api_key: Optional[str] = None, default_model: Optional[str] = None, base_url: Optional[str] = None): ...
    # Log warning only once during initialization
    logging.getLogger(__name__).warning("LLM client libraries not found or import failed. LLM features will be unavailable.")


# --- Workflows & Environment ---
from .workflow_generator import WorkflowGenerator
# Removed EnvironmentTracker import as /env_get is removed
# from .modules import ModuleManager # If needed for a /module command

# --- Helper for argument parsing ---
import argparse

# Configure logging for the service
logger = logging.getLogger(__name__)
if not logging.getLogger().hasHandlers():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# --- Rich Console and Theme Setup ---
string_io = io.StringIO()
capture_console = Console(file=string_io, force_terminal=True, color_system="truecolor", width=120)
# Use a global console for direct output
console = Console(theme=Theme({
    "info": "dim cyan",
    "warning": "yellow",
    "error": "bold red",
    "repr.str": "none", # Avoid Rich adding quotes around output strings
}))


# --- File Coloring Logic ---
COLOR_MAP = {
    # Sequences (Raw)
    ".fastq": "bright_cyan", ".fq": "bright_cyan",
    # Sequences (Reference/Assembly)
    ".fasta": "cyan", ".fa": "cyan", ".fna": "cyan", ".ffn": "cyan", ".faa": "cyan", ".frn": "cyan",
    # Sequences (Alignment)
    ".sam": "dark_cyan", ".bam": "dark_cyan", ".cram": "dark_cyan",
    # Annotations
    ".gff": "bright_magenta", ".gff3": "bright_magenta", ".gtf": "bright_magenta", ".bed": "bright_magenta",
    # Variant Data
    ".vcf": "bright_red", ".bcf": "bright_red",
    # Phylogenetics
    ".nwk": "bright_green", ".newick": "bright_green", ".nex": "bright_green", ".nexus": "bright_green", ".phy": "bright_green",
    # Tabular Data
    ".csv": "yellow", ".tsv": "yellow", ".txt": "yellow", # Heuristic for .txt
    # Scripts/Workflows
    ".py": "blue", ".sh": "blue", ".cwl": "blue", ".wdl": "blue", ".nf": "blue", ".smk": "blue",
    # Config/Metadata
    ".json": "bright_black", ".yaml": "bright_black", ".yml": "bright_black", ".toml": "bright_black", ".ini": "bright_black", ".xml": "bright_black",
    # Compressed
    ".gz": "grey50", ".bz2": "grey50", ".zip": "grey50", ".tar": "grey50", ".tgz": "grey50", ".xz": "grey50",
}

def colorize_filename(filename: str, is_dir: bool = False) -> Text:
    """Applies semantic coloring to a filename using Rich Text."""
    if is_dir:
        return Text(filename, style="bold blue")
    else:
        _base, ext = os.path.splitext(filename)
        ext_lower = ext.lower()
        style = COLOR_MAP.get(ext_lower)
        # Handle double extensions like .fasta.gz
        if style is None and ext_lower in {".gz", ".bz2", ".xz"}:
            _base2, ext2 = os.path.splitext(_base)
            ext2_lower = ext2.lower()
            style = COLOR_MAP.get(ext2_lower) # Get style for inner extension
            if style is None:
                 style = COLOR_MAP.get(ext_lower, "default") # Fallback to compression style
        elif style is None:
             style = "default" # Default style if no match
        return Text(filename, style=style)

# --- End File Coloring Logic ---


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
        self.file_queue: List[str] = [] # Initialize the file queue
        logger.info(f"DayhoffService initialized. Local CWD: {self.local_cwd}")
        self._command_map = self._build_command_map()


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


        return {
            "help": {"handler": self._handle_help, "help": "Show help for commands. Usage: /help [command_name]"},
            "test": {
                "handler": self._handle_test,
                "help": textwrap.dedent("""\
                    Run or show information about internal tests.
                    Usage: /test <subcommand> [options]
                    Subcommands:
                      llm        : Test connection to the configured Large Language Model.
                      script <name> : Run a specific test script from the 'examples' directory.
                      list       : List available test scripts in the 'examples' directory.""")
            },
            "config": {
                "handler": self._handle_config,
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
            "fs_head": {"handler": self._handle_fs_head, "help": "Show the first N lines of a local file. Usage: /fs_head <file_path> [num_lines=10]"},
            "hpc_connect": {"handler": self._handle_hpc_connect, "help": "Establish a persistent SSH connection to the HPC. Usage: /hpc_connect"},
            "hpc_disconnect": {"handler": self._handle_hpc_disconnect, "help": "Close the persistent SSH connection to the HPC. Usage: /hpc_disconnect"},
            "hpc_run": {
                "handler": self._handle_hpc_run,
                "help": textwrap.dedent("""\
                    Execute a command on the HPC using the active connection.
                    Behavior depends on HPC.execution_mode config:
                      'direct': Runs the command directly via SSH.
                      'slurm': Wraps the command in 'srun --pty' for execution via Slurm.
                    Usage: /hpc_run <command_string>""")
            },
            "hpc_slurm_run": {"handler": self._handle_hpc_slurm_run, "help": "Execute a command explicitly within a Slurm allocation (srun). Usage: /hpc_slurm_run <command_string>"},
            "ls": {"handler": self._handle_ls, "help": "List files in the current directory (local or remote) with colors. Usage: /ls [ls_options_ignored]"}, # Updated help
            "cd": {"handler": self._handle_cd, "help": "Change the current directory (local or remote). Usage: /cd <directory>"}, # Updated help
            "hpc_slurm_submit": {
                "handler": self._handle_hpc_slurm_submit,
                "help": textwrap.dedent("""\
                    Submit a Slurm job script.
                    Usage: /hpc_slurm_submit <script_path> [options_json]
                      script_path : Path to the local Slurm script file.
                      options_json: Optional Slurm options as JSON string (e.g., '{"--nodes": 1, "--time": "01:00:00"}').
                                    Can include runner flags like '--singularity' or '--docker'.
                                    If HPC.slurm_use_singularity is true and no container flag is given, '--singularity' will be added by default.""")
            },
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
            "wf_gen": {"handler": self._handle_wf_gen, "help": "Generate workflow using the configured language. Usage: /wf_gen <steps_json>"},
            "language": {
                "handler": self._handle_language,
                "help": textwrap.dedent(f"""\
                    View or set the preferred workflow *language* for generation.
                    Usage:
                      /language             : Show the current language setting.
                      /language <language>  : Set the language (e.g., /language cwl).
                    Allowed languages: {", ".join(ALLOWED_WORKFLOW_LANGUAGES)}
                    Note: To set the default *executor* for a language, use '/config set WORKFLOWS <lang>_default_executor <executor_name>'.""") # Updated help
            },
            "queue": { # New command group
                "handler": self._handle_queue,
                 "help": textwrap.dedent("""\
                    Manage the file queue for processing.
                    Usage: /queue <subcommand> [arguments]
                    Subcommands:
                      add <path...> : Add file(s) or directory(s) (recursive) to the queue. Paths are relative to CWD.
                      show          : Display the files currently in the queue.
                      remove <idx...> : Remove files from the queue by their index number (from /queue show).
                      clear         : Remove all files from the queue.""")
            },
        }

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
        """Execute a command"""
        logger.info(f"Executing command: /{command} with args: {args}")
        if command in self._command_map:
            command_info = self._command_map[command]
            handler = command_info["handler"]
            try:
                # Use console.print for outputting results directly
                result = handler(args)
                # Handlers should ideally print their own output or return structured data
                # If a handler returns a string, print it. Avoid double printing.
                if isinstance(result, str) and result:
                     console.print(result, overflow="ignore", crop=False, highlight=False) # Print simple string results
                elif result is not None:
                     # For non-string results, maybe use rich.pretty.pretty_repr or just log
                     logger.debug(f"Command /{command} returned non-string result: {type(result)}")
                logger.info(f"Command /{command} executed successfully.")
                return result # Return the result for potential programmatic use
            except argparse.ArgumentError as e:
                 logger.warning(f"Argument error for /{command}: {e}")
                 # ArgumentError message often includes usage, print it directly
                 console.print(f"[error]Argument Error:[/error] {e}")
                 return None # Indicate error
            except FileNotFoundError as e:
                 logger.warning(f"File/Directory not found during /{command}: {e}")
                 console.print(f"[error]Error:[/error] File or directory not found - {e}")
                 return None
            except NotADirectoryError as e:
                 logger.warning(f"Path is not a directory during /{command}: {e}")
                 console.print(f"[error]Error:[/error] Path is not a directory - {e}")
                 return None
            except PermissionError as e:
                 logger.warning(f"Permission denied during /{command}: {e}")
                 console.print(f"[error]Error:[/error] Permission denied - {e}")
                 return None
            except ConnectionError as e:
                 logger.error(f"Connection error during /{command}: {e}", exc_info=False)
                 console.print(f"[error]Connection Error:[/error] {e}")
                 return None
            except TimeoutError as e:
                 logger.error(f"Timeout error during /{command}: {e}", exc_info=False)
                 console.print(f"[error]Timeout Error:[/error] {e}")
                 return None
            except ValueError as e: # Catch validation errors (e.g., from config.set)
                 logger.warning(f"Validation error during /{command}: {e}")
                 console.print(f"[error]Validation Error:[/error] {e}")
                 return None
            except IndexError as e: # Catch index errors specifically (e.g., for /queue remove)
                 logger.warning(f"Index error during /{command}: {e}")
                 console.print(f"[error]Index Error:[/error] {e}")
                 return None
            except NotImplementedError as e:
                 logger.warning(f"Feature not implemented for /{command}: {e}")
                 console.print(f"[warning]Not Implemented:[/warning] {e}")
                 return None
            except Exception as e:
                logger.error(f"Error executing command /{command}: {e}", exc_info=True)
                console.print(f"[error]Unexpected Error:[/error] {type(e).__name__}: {e}")
                return None
        else:
            logger.warning(f"Unknown command attempted: /{command}")
            console.print(f"[error]Unknown command:[/error] /{command}. Type /help for available commands.")
            return None

    # --- Help Handler ---
    def _handle_help(self, args: List[str]) -> Optional[str]:
        """Handles the /help command. Returns None as output is printed directly."""
        if not args:
            # General help
            status = self.get_status()
            current_language = self.config.get_workflow_language()
            current_executor = self.config.get_workflow_executor(current_language) or "N/A"
            llm_provider = self.config.get('LLM', 'provider', 'N/A')
            llm_model = self.config.get('LLM', 'model', 'N/A')
            exec_mode = status['exec_mode'] # Get from status
            queue_size = status['queue_size'] # Get queue size

            # Build status line
            if status['mode'] == 'connected':
                status_line = f"Mode: [bold green]Connected[/] ({status['user']}@{status['host']}:{status['cwd']})"
            else:
                status_line = f"Mode: [bold yellow]Local[/] ({status['cwd']})"
            status_line += f" | Exec: [bold]{exec_mode}[/]" # Add exec mode
            status_line += f" | Queue: [bold]{queue_size}[/]" # Add queue size

            console.print(Panel(
                f"[bold]Dayhoff REPL[/bold] - Type /<command> [arguments] to execute.\n"
                f"{status_line}\n"
                f"Workflow: {current_language.upper()} (Executor: {current_executor}) - Use /language, /config\n"
                f"LLM: {llm_provider.upper()} (Model: {llm_model}) - Use /config\n"
                f"Type /help <command> for details.",
                title="Dayhoff Help",
                expand=False
            ))

            console.print("\n[bold cyan]Available commands:[/bold cyan]")
            # Group commands logically
            cmd_groups = {
                "General": ["help", "config", "language", "test"],
                "File System (Local/Remote)": ["ls", "cd", "fs_head"], # fs_head is local only
                "File Queue": ["queue"], # New category
                "HPC Connection": ["hpc_connect", "hpc_disconnect"],
                "HPC Execution": ["hpc_run"],
                "Slurm": ["hpc_slurm_run", "hpc_slurm_submit", "hpc_slurm_status"],
                "Credentials": ["hpc_cred_get"],
                "Workflow": ["wf_gen"],
            }
            displayed_cmds = set()
            for group, cmds in cmd_groups.items():
                 console.print(f"\n--- {group} ---")
                 for cmd in cmds:
                     if cmd in self._command_map:
                         info = self._command_map[cmd]
                         first_line = info['help'].split('\n')[0].strip()
                         console.print(f"  /{cmd:<20} - {first_line}")
                         displayed_cmds.add(cmd)

            # Show any remaining commands not in groups
            remaining_cmds = sorted([cmd for cmd in self._command_map if cmd not in displayed_cmds])
            if remaining_cmds:
                 console.print("\n--- Other ---")
                 for cmd in remaining_cmds:
                      info = self._command_map[cmd]
                      first_line = info['help'].split('\n')[0].strip()
                      console.print(f"  /{cmd:<20} - {first_line}")

            console.print("\nType /help <command_name> for more details.")
            return None # Output printed directly
        else:
            # Specific command help
            cmd_name = args[0].lstrip('/')
            if cmd_name in self._command_map:
                # Use argparse's help printing mechanism for commands that use it heavily
                # Check if the handler uses argparse (heuristic: check for ArgumentParser creation or specific commands)
                # For simplicity, assume all handlers might use it or print their own help
                try:
                    # Call the handler with '--help'
                    self._command_map[cmd_name]['handler'](['--help'])
                except SystemExit: # Argparse calls sys.exit on --help
                    pass # Expected behavior, help was printed
                except argparse.ArgumentError as e: # Handle cases where --help isn't the first arg or other parse errors
                    # If ArgumentError occurs, print the stored help string as fallback
                    logger.debug(f"ArgumentError showing help for {cmd_name}, falling back to stored help string: {e}")
                    console.print(Panel(self._command_map[cmd_name]['help'], title=f"Help for /{cmd_name}", border_style="cyan"))
                except Exception as e:
                     logger.error(f"Unexpected error showing help for {cmd_name}", exc_info=True)
                     # Fallback to stored help string on unexpected errors
                     console.print(f"[warning]Could not display dynamic help for {cmd_name}. Showing basic help:[/warning]")
                     console.print(Panel(self._command_map[cmd_name]['help'], title=f"Help for /{cmd_name}", border_style="cyan"))

                return None # Output printed directly
            else:
                 console.print(f"[error]Unknown command:[/error] /{cmd_name}")
                 return None

    # --- Argument Parsers ---
    def _create_parser(self, prog: str, description: str, add_help: bool = False) -> argparse.ArgumentParser:
        """Creates an ArgumentParser instance for command parsing."""
        # Custom error handler to raise ArgumentError instead of exiting
        class RaiseArgumentParser(argparse.ArgumentParser):
            def error(self, message):
                # Get usage string
                usage = self.format_usage()
                full_message = f"{message}\n{usage}"
                # Raise specific error type that execute_command can catch
                raise argparse.ArgumentError(None, full_message)

            def exit(self, status=0, message=None):
                 # Prevent sys.exit on --help
                 if message:
                     # Print help message manually to the console
                     # Use StringIO to capture help message if needed elsewhere
                     help_io = io.StringIO()
                     self._print_message(message, help_io)
                     console.print(help_io.getvalue().strip()) # Strip trailing newline from help
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

    # --- Test Command Handler ---
    def _handle_test(self, args: List[str]) -> Optional[str]:
        """Handles the /test command with subparsers."""
        parser = self._create_parser("test", self._command_map['test']['help'], add_help=True)
        subparsers = parser.add_subparsers(dest="subcommand", title="Subcommands",
                                           description="Valid subcommands for /test",
                                           help="Test to perform")
        # subparsers.required = True # Make subcommand mandatory

        # --- Subparser: llm ---
        parser_llm = subparsers.add_parser("llm", help="Test connection to the configured LLM.", add_help=True)
        # Add options specific to LLM test if needed, e.g., --model

        # --- Subparser: script ---
        parser_script = subparsers.add_parser("script", help="Run a specific test script from 'examples'.", add_help=True)
        parser_script.add_argument("test_name", help="Name of the test script (e.g., 'cli', 'hpc_bridge').")

        # --- Subparser: list ---
        parser_list = subparsers.add_parser("list", help="List available test scripts in 'examples'.", add_help=True)


        # --- Parse arguments ---
        try:
            # Handle case where no subcommand is given
            if not args:
                 parser.print_help()
                 return None

            parsed_args = parser.parse_args(args)

            # --- Execute subcommand logic ---
            if parsed_args.subcommand == "llm":
                self._test_llm_connection() # This method prints its own output
                return None
            elif parsed_args.subcommand == "script":
                return self._run_test_script(parsed_args.test_name) # This method returns string output, execute_command will print it
            elif parsed_args.subcommand == "list":
                return self._list_test_scripts() # This method returns string output, execute_command will print it
            else:
                 # Should be caught by argparse if required=True, but handle defensively
                 parser.print_help()
                 return None

        except argparse.ArgumentError as e:
            raise e # Re-raise for execute_command to handle
        except SystemExit:
             return None # Help was printed
        except Exception as e:
             logger.error(f"Error during /test {args}: {e}", exc_info=True)
             raise RuntimeError(f"Error executing test command: {e}") from e


    def _list_test_scripts(self) -> str:
        """Lists available test scripts in the examples directory."""
        examples_dir = "examples"
        available_tests = {}
        help_lines = ["Available test scripts in 'examples/' directory:"]
        try:
            if os.path.isdir(examples_dir):
                for filename in sorted(os.listdir(examples_dir)):
                    if filename.startswith("test_") and filename.endswith(".py"):
                        test_name = filename[len("test_"):-len(".py")]
                        # Could try to parse a docstring for description, but keep simple for now
                        help_lines.append(f"  - {test_name}")
                if len(help_lines) == 1: # Only header added
                     help_lines.append("  (No test scripts found)")
            else:
                 help_lines.append(f"  (Directory '{examples_dir}' not found)")
        except Exception as e:
             logger.error(f"Error listing test scripts in '{examples_dir}': {e}")
             help_lines.append(f"  (Error listing scripts: {e})")

        help_lines.append("\nUse '/test script <name>' to run a specific test.")
        return "\n".join(help_lines)


    def _run_test_script(self, test_name: str) -> str:
        """Runs a specific test script from the examples directory."""
        examples_dir = "examples"
        script_name = f"test_{test_name}.py"
        script_path = os.path.join(examples_dir, script_name)
        logger.info(f"Attempting to execute test script: {script_path}")

        if not os.path.isfile(script_path):
            # Provide list of available scripts in error message
            available_scripts_msg = self._list_test_scripts()
            raise FileNotFoundError(f"Test script '{script_path}' not found.\n{available_scripts_msg}")

        try:
            process = subprocess.run(
                [sys.executable, script_path],
                capture_output=True,
                text=True,
                check=False, # Don't raise exception on non-zero exit code
                timeout=120 # 2-minute timeout
            )
            output_lines = [
                f"--- Running Test Script: {test_name} ({script_path}) ---",
                f"Exit Code: {process.returncode}",
                "\n--- STDOUT ---",
                process.stdout.strip() if process.stdout else "(empty)",
                "\n--- STDERR ---",
                process.stderr.strip() if process.stderr else "(empty)",
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
             raise TimeoutError(f"Test script '{script_path}' timed out after 120 seconds.")
        except Exception as e:
            logger.error(f"Failed to execute test script '{script_path}': {e}", exc_info=True)
            raise RuntimeError(f"Failed to execute test script '{script_path}': {e}") from e


    def _test_llm_connection(self) -> None:
        """Performs a simple test of the configured LLM connection. Prints output directly."""
        if not LLM_CLIENTS_AVAILABLE:
             console.print("[error]LLM client libraries not installed or found. Cannot run LLM test.[/error]")
             console.print("Please ensure necessary packages like 'openai' or 'anthropic' are installed.")
             return

        console.print("🧪 Testing LLM connection...")
        llm_config = self.config.get_llm_config()

        config_details = [
            f"Provider : {llm_config.get('provider') or '[Not Set]'}",
            f"Model    : {llm_config.get('model') or '[Not Set]'}",
            f"Base URL : {llm_config.get('base_url') or '[Provider Default]'}",
            f"API Key  : {'[Set]' if llm_config.get('api_key') else '[Not Set]'}" # Don't print the key
        ]
        console.print(Panel("\n".join(config_details), title="LLM Configuration", border_style="dim"))

        if not llm_config.get('api_key'):
             console.print("[error]LLM API Key is not configured (checked config file and environment variables). Cannot perform test.[/error]")
             return
        if not llm_config.get('model'):
             console.print("[error]LLM Model is not configured. Cannot perform test.[/error]")
             return

        try:
            client = self._get_llm_client() # Gets or initializes the client
            test_prompt = "Briefly explain the concept of bioinformatics in one sentence."
            console.print(f"  Sending test prompt to model '{llm_config.get('model')}'...")

            response_data = None
            error_message = None
            start_time = time.time()

            # Use Rich Live display for spinner
            with Live(Spinner("dots", text="Waiting for LLM response..."), console=console, transient=True, refresh_per_second=10) as live:
                try:
                    # Pass parameters expected by the client's generate method
                    # Use a short max_tokens for the test
                    response_data = client.generate(
                        prompt=test_prompt,
                        max_tokens=50,
                        temperature=0.1,
                        model=llm_config.get('model') # Explicitly pass model if needed by generate
                    )
                except Exception as e:
                    error_message = str(e)
                    logger.error(f"LLM API call failed: {e}", exc_info=True)

            duration = time.time() - start_time
            console.print(f"  Request completed in {duration:.2f} seconds.")

            if error_message:
                 console.print(f"[error]LLM API call failed:[/error] {error_message}")
                 return # Stop test on API error

            # Check the structure of the response_data dictionary
            if response_data and isinstance(response_data, dict):
                 response_text = response_data.get('response')
                 tokens_used = response_data.get('tokens_used')
                 model_used = response_data.get('model_used', llm_config.get('model')) # Fallback to configured model

                 if response_text and isinstance(response_text, str) and response_text.strip():
                     console.print(Panel(response_text.strip(), title=f"LLM Response (from {model_used})", border_style="green", expand=False))
                     if tokens_used is not None:
                         console.print(f"  Tokens used: {tokens_used}", style="dim")
                     console.print("[bold green]✅ LLM Test Successful[/bold green]")
                 else:
                     console.print("[warning]LLM Test Warning:[/warning] Received empty or unexpected response content.")
                     logger.warning(f"LLM test received empty response content: {response_data}")
            else:
                 console.print("[warning]LLM Test Warning:[/warning] Received unexpected response format.")
                 logger.warning(f"LLM test received unexpected response format: {response_data}")

        except ImportError as e:
             # This case should be caught earlier by LLM_CLIENTS_AVAILABLE, but handle defensively
             console.print(f"[error]Missing LLM client library dependency:[/error] {e}.")
             console.print("Please ensure necessary packages are installed.")
        except Exception as e:
            # Catch errors during client initialization or other unexpected issues
            logger.error(f"LLM connection test failed during setup or execution: {e}", exc_info=True)
            console.print(f"[error]LLM Test Failed:[/error] {e}")


    def _get_llm_client(self) -> LLMClient:
        """Initializes and returns the LLMClient instance based on config."""
        if not LLM_CLIENTS_AVAILABLE:
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


    # --- Consolidated Config Handler ---
    def _handle_config(self, args: List[str]) -> Optional[str]:
        """Handles the /config command with subparsers. Prints output directly."""
        parser = self._create_parser(
            "config",
            self._command_map['config']['help'],
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
                     value = self.config.getboolean(section_upper, key_lower, default=parsed_args.default)
                else:
                     value = self.config.get(section_upper, key_lower, parsed_args.default)

                if value is not None:
                    if isinstance(value, (dict, list)): # Should not happen with INI, but maybe future formats
                        console.print_json(data=value)
                    else:
                        console.print(str(value)) # Print string representation
                else:
                    # config.get returns default (None here) if not found, so indicate that
                    console.print(f"Key '[{section_upper}].{key_lower}' not found.", style="warning")

            elif parsed_args.subcommand == "set":
                section_upper = parsed_args.section.upper()
                key_lower = parsed_args.key.lower() # Standardize key case for setting
                try:
                    # config.set handles validation and saving
                    self.config.set(section_upper, key_lower, parsed_args.value)
                    # Invalidate cached LLM client if LLM settings changed
                    if section_upper == 'LLM':
                         self.llm_client = None
                         logger.info("Invalidated cached LLM client due to config change.")
                    # Invalidate cached SSH manager if HPC settings changed
                    if section_upper == 'HPC':
                         if self.active_ssh_manager:
                             logger.warning("HPC config changed. Closing active SSH connection.")
                             try: self.active_ssh_manager.disconnect()
                             except Exception: pass
                             self.active_ssh_manager = None
                             self.remote_cwd = None
                             console.print("[warning]HPC configuration changed. Active connection closed. Please use /hpc_connect again.[/warning]")
                         else:
                             logger.info("HPC config changed. Any new connection will use the updated settings.")

                    console.print(f"Config '[{section_upper}].{key_lower}' set to '{parsed_args.value}' and saved.", style="info")
                except ValueError as e: # Catch validation errors from config.set
                    console.print(f"[error]Validation Error:[/error] {e}")
                except Exception as e:
                    logger.error(f"Failed to set config [{section_upper}].{key_lower}", exc_info=True)
                    console.print(f"[error]Failed to set config:[/error] {e}")

            elif parsed_args.subcommand == "save":
                self.config.save_config()
                config_path = self.config.config_path
                console.print(f"Configuration saved successfully to {config_path}.", style="info")

            elif parsed_args.subcommand == "show":
                section_name = parsed_args.section
                if section_name is None or section_name.lower() == 'all':
                    config_data = self.config.get_all_config()
                    if not config_data:
                        console.print("Configuration is empty or could not be read.", style="warning")
                    else:
                        # Mask sensitive data in 'all' view
                        display_data = json.loads(json.dumps(config_data)) # Deep copy
                        if 'LLM' in display_data and 'api_key' in display_data['LLM']:
                             display_data['LLM']['api_key'] = "[Set]" if display_data['LLM'].get('api_key') else "[Not Set]"
                        if 'HPC' in display_data and 'password' in display_data['HPC']: # Assuming password might be stored directly (bad practice)
                             display_data['HPC']['password'] = "[Set]" if display_data['HPC'].get('password') else "[Not Set]"
                        console.print(Panel(json.dumps(display_data, indent=2), title="Current Configuration (All Sections)", border_style="cyan"))

                elif section_name.lower() == 'ssh':
                    config_data = self.config.get_ssh_config()
                    if not config_data:
                        console.print("SSH (HPC) configuration section not found or empty.", style="warning")
                    else:
                         # Mask password if present
                         display_data = config_data.copy()
                         # Password shouldn't be in get_ssh_config result, but check defensively
                         if 'password' in display_data: display_data['password'] = "[Set]" if display_data['password'] else "[Not Set]"
                         if 'key_filename' in display_data and display_data.get('auth_method') != 'key':
                              del display_data['key_filename'] # Don't show irrelevant key path

                         console.print(Panel(json.dumps(display_data, indent=2), title="Interpreted SSH Configuration (Subset of HPC)", border_style="cyan"))
                elif section_name.lower() == 'llm':
                     config_data = self.config.get_llm_config() # Gets interpreted LLM config (checks env vars)
                     if not config_data:
                         console.print("LLM configuration section not found or empty.", style="warning")
                     else:
                         # Mask API key
                         display_data = config_data.copy()
                         display_data['api_key'] = "[Set]" if display_data.get('api_key') else "[Not Set]"
                         console.print(Panel(json.dumps(display_data, indent=2), title="Interpreted LLM Configuration", border_style="cyan"))
                elif section_name.lower() == 'hpc': # Show the full HPC section
                     section_upper = 'HPC'
                     config_data = self.config.get_section(section_upper)
                     if config_data is None:
                         console.print(f"Configuration section '[{section_upper}]' not found.", style="warning")
                     else:
                         display_data = config_data.copy()
                         # Mask password if present
                         if 'password' in display_data: display_data['password'] = "[Set]" if display_data['password'] else "[Not Set]"
                         console.print(Panel(json.dumps(display_data, indent=2), title=f"Configuration Section [{section_upper}]", border_style="cyan"))

                else:
                    # Show specific section
                    section_upper = section_name.upper()
                    config_data = self.config.get_section(section_upper) # Gets raw section data
                    if config_data is None:
                        available_sections = self.config.get_available_sections()
                        console.print(f"Configuration section '[{section_upper}]' not found. Available sections: {', '.join(available_sections)}", style="warning")
                    else:
                         # Mask sensitive data if showing specific sections like LLM or HPC directly
                         display_data = config_data.copy()
                         if section_upper == 'LLM' and 'api_key' in display_data:
                             display_data['api_key'] = "[Set]" if display_data.get('api_key') else "[Not Set]"
                         if section_upper == 'HPC' and 'password' in display_data:
                             display_data['password'] = "[Set]" if display_data.get('password') else "[Not Set]"
                         # Add other masking if needed

                         console.print(Panel(json.dumps(display_data, indent=2), title=f"Configuration Section [{section_upper}]", border_style="cyan"))

            elif parsed_args.subcommand == "slurm_singularity":
                # Handle the new subcommand
                section = 'HPC'
                key = 'slurm_use_singularity'
                value_str = 'True' if parsed_args.state == 'on' else 'False'
                try:
                    # Use config.set which handles validation and saving
                    self.config.set(section, key, value_str)
                    # No need to disconnect SSH for this specific setting change
                    logger.info(f"Set {key} to {value_str}")
                    console.print(f"Default Slurm Singularity usage set to: [bold cyan]{parsed_args.state}[/bold cyan]", style="info")
                except ValueError as e: # Catch validation errors from config.set
                    console.print(f"[error]Validation Error:[/error] {e}")
                except Exception as e:
                    logger.error(f"Failed to set config [{section}].{key}", exc_info=True)
                    console.print(f"[error]Failed to set config:[/error] {e}")

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


    # --- File System Handlers ---
    def _handle_fs_head(self, args: List[str]) -> Optional[str]:
        """Handles the /fs_head command. Prints output directly."""
        parser = self._create_parser("fs_head", self._command_map['fs_head']['help'], add_help=True)
        parser.add_argument("file_path", help="Path to the local file")
        parser.add_argument("num_lines", type=int, nargs='?', default=10, help="Number of lines to show (default: 10)")

        try:
            parsed_args = parser.parse_args(args)

            if parsed_args.num_lines <= 0:
                # Use parser.error for consistency, requires ArgumentParser subclass override
                # For now, raise ArgumentError manually
                raise argparse.ArgumentError(parser._get_action("num_lines"), "Number of lines must be positive.")

            # Resolve the file path relative to the *local* CWD
            target_path = Path(self.local_cwd) / parsed_args.file_path
            abs_path = target_path.resolve() # Get absolute path

            # Check existence using resolved absolute path
            if not abs_path.is_file():
                 raise FileNotFoundError(f"File not found at '{abs_path}'")

            # Use the absolute path with the file inspector
            lines = list(self.file_inspector.head(str(abs_path), parsed_args.num_lines))

            if not lines:
                console.print(f"File is empty: {abs_path}", style="info")
                return None

            dirname = str(abs_path.parent)
            basename = abs_path.name
            colored_basename = colorize_filename(basename, is_dir=False)
            header_text = Text.assemble(f"First {len(lines)} lines of '", dirname + os.path.sep, colored_basename, "':")

            # Use capture console only if we need the string value later, otherwise print directly
            console.print(Panel("\n".join(lines), title=header_text, border_style="cyan", expand=False))
            return None # Output printed directly

        except argparse.ArgumentError as e:
            raise e # Re-raise for execute_command
        except FileNotFoundError as e:
             raise e # Re-raise
        except SystemExit:
             return None # Help was printed
        except Exception as e:
            logger.error(f"Error reading head of file {args[0] if args else ''}", exc_info=True)
            raise RuntimeError(f"Error reading file head: {e}") from e


    # --- HPC Bridge Helpers ---

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
        # Use -print0 and split('\0') for safer handling of filenames with whitespace/newlines
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

    # --- HPC Bridge Handlers --- Updated structure
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


    # --- HPC Connection Handlers ---
    def _handle_hpc_connect(self, args: List[str]) -> Optional[str]:
        """Establishes and stores a persistent SSH connection. Prints output."""
        parser = self._create_parser("hpc_connect", self._command_map['hpc_connect']['help'], add_help=True)
        try:
            parsed_args = parser.parse_args(args) # Handles --help

            if self.active_ssh_manager and self.active_ssh_manager.is_connected:
                try:
                    test_cmd = "echo 'Dayhoff connection active'"
                    logger.debug(f"Testing existing SSH connection with: {test_cmd}")
                    self.active_ssh_manager.execute_command(test_cmd, timeout=5)
                    host = self.active_ssh_manager.host
                    logger.info(f"Persistent SSH connection to {host} is already active.")
                    if self.remote_cwd is None: # Check if CWD is None
                        try:
                            # Use pwd -P to get physical directory, avoid symlink issues if possible
                            self.remote_cwd = self.active_ssh_manager.execute_command("pwd -P", timeout=10).strip()
                            logger.info(f"Refreshed remote CWD: {self.remote_cwd}")
                        except Exception as pwd_err:
                            logger.warning(f"Could not refresh remote CWD on existing connection: {pwd_err}")
                            # Attempt simpler 'pwd' as fallback
                            try:
                                self.remote_cwd = self.active_ssh_manager.execute_command("pwd", timeout=10).strip()
                                logger.info(f"Refreshed remote CWD (fallback): {self.remote_cwd}")
                            except Exception as pwd_err_fallback:
                                logger.warning(f"Could not refresh remote CWD using fallback 'pwd': {pwd_err_fallback}")
                                self.remote_cwd = "~" # Default CWD
                    console.print(f"Already connected to HPC host: {host} (cwd: {self.remote_cwd}). Use /hpc_disconnect first to reconnect.", style="info")
                    return None # Already connected
                except (ConnectionError, TimeoutError, RuntimeError) as e:
                    logger.warning(f"Existing SSH connection seems stale ({type(e).__name__}: {e}), attempting to reconnect.")
                    try: self.active_ssh_manager.disconnect()
                    except Exception as close_err: logger.debug(f"Error closing stale SSH connection: {close_err}")
                    self.active_ssh_manager = None
                    self.remote_cwd = None
                except Exception as e:
                     logger.error(f"Unexpected error testing existing SSH connection: {e}", exc_info=True)
                     try: self.active_ssh_manager.disconnect()
                     except Exception: pass
                     self.active_ssh_manager = None
                     self.remote_cwd = None
                     console.print(f"[warning]Error testing existing connection ({e}). Cleared connection state. Please try connecting again.[/warning]")
                     return None


            console.print("Attempting to establish persistent SSH connection...", style="info")
            ssh_manager = None
            try:
                # Get manager instance, but don't connect immediately within _get_ssh_manager
                ssh_manager = self._get_ssh_manager(connect_now=False)
                # Now call connect, which might prompt for password if needed
                if not ssh_manager.connect():
                    # connect() should raise error on failure, but double-check
                    raise ConnectionError(f"Failed to establish initial SSH connection to {ssh_manager.host}. Check logs and config.")

                test_cmd = "hostname"
                logger.info(f"SSH connection established, verifying with command: {test_cmd}")
                hostname = ssh_manager.execute_command(test_cmd, timeout=15).strip()
                if not hostname:
                     logger.warning("SSH connection verified but 'hostname' command returned empty.")
                     hostname = ssh_manager.host # Use configured host as fallback

                logger.info(f"SSH connection verified. Remote hostname: {hostname}")

                try:
                    # Use pwd -P to get physical directory, avoid symlink issues if possible
                    initial_cwd = ssh_manager.execute_command("pwd -P", timeout=10).strip()
                    if not initial_cwd:
                        logger.warning("Could not determine initial remote working directory using 'pwd -P', trying 'pwd'.")
                        initial_cwd = ssh_manager.execute_command("pwd", timeout=10).strip()
                        if not initial_cwd:
                             logger.warning("Could not determine initial remote working directory using 'pwd' either, defaulting to '~'.")
                             initial_cwd = "~"
                except (ConnectionError, TimeoutError, RuntimeError) as pwd_err:
                     logger.warning(f"Could not determine initial remote working directory ({pwd_err}), defaulting to '~'.")
                     initial_cwd = "~"

                self.active_ssh_manager = ssh_manager
                self.remote_cwd = initial_cwd # Set remote CWD
                exec_mode = self.config.get_execution_mode() # Get current exec mode
                console.print(f"Successfully connected to HPC host: {hostname} (user: {ssh_manager.username}, cwd: {self.remote_cwd}, exec_mode: {exec_mode}).", style="bold green")
                return None

            except (ConnectionError, TimeoutError, RuntimeError, ValueError) as e:
                logger.error(f"Failed to establish persistent SSH connection: {type(e).__name__}: {e}", exc_info=False)
                if ssh_manager: ssh_manager.disconnect() # Ensure cleanup
                self.active_ssh_manager = None
                self.remote_cwd = None
                # Raise the error for execute_command to catch and display
                raise ConnectionError(f"Failed to establish SSH connection: {e}") from e
            except Exception as e:
                logger.error(f"Unexpected error during persistent SSH connection: {e}", exc_info=True)
                if ssh_manager: ssh_manager.disconnect()
                self.active_ssh_manager = None
                self.remote_cwd = None
                raise ConnectionError(f"Unexpected error establishing SSH connection: {e}") from e

        except argparse.ArgumentError as e:
             raise e # Let execute_command handle parser errors
        except SystemExit:
             return None # Help was printed


    def _handle_hpc_disconnect(self, args: List[str]) -> Optional[str]:
        """Closes the persistent SSH connection. Prints output."""
        parser = self._create_parser("hpc_disconnect", self._command_map['hpc_disconnect']['help'], add_help=True)
        try:
            parsed_args = parser.parse_args(args) # Handles --help

            if not self.active_ssh_manager:
                console.print("No active HPC connection to disconnect.", style="warning")
                return None

            logger.info("Disconnecting persistent SSH connection...")
            try:
                host = getattr(self.active_ssh_manager, 'host', 'unknown')
                self.active_ssh_manager.disconnect()
                self.active_ssh_manager = None
                self.remote_cwd = None # Clear remote CWD
                console.print(f"Successfully disconnected from HPC host: {host}. Operating in local mode.", style="info")
                return None
            except Exception as e:
                logger.error(f"Error during SSH disconnection: {e}", exc_info=True)
                # Force clear state even if disconnect fails
                self.active_ssh_manager = None
                self.remote_cwd = None # Clear remote CWD
                raise RuntimeError(f"Error closing SSH connection: {e}") from e

        except argparse.ArgumentError as e:
             raise e
        except SystemExit:
             return None # Help was printed


    def _handle_hpc_run(self, args: List[str]) -> Optional[str]:
        """Executes a command using the active persistent SSH connection, respecting execution_mode. Prints output."""
        parser = self._create_parser("hpc_run", self._command_map['hpc_run']['help'], add_help=True)
        # Use REMAINDER to capture the full command string
        parser.add_argument("command_string", nargs=argparse.REMAINDER, help="The command and arguments to execute remotely.")

        try:
            parsed_args = parser.parse_args(args)

            if not parsed_args.command_string:
                 raise argparse.ArgumentError(None, "Missing command to execute.")

            if not self.active_ssh_manager or not self.active_ssh_manager.is_connected:
                raise ConnectionError("Not connected to HPC. Use /hpc_connect first.")
            if self.remote_cwd is None: # Check for None specifically
                 raise ConnectionError("Remote working directory unknown. Please use /hpc_connect again.")

            # Get execution mode from config
            exec_mode = self.config.get_execution_mode()
            user_command = " ".join(shlex.quote(arg) for arg in parsed_args.command_string)
            command_to_run = ""
            exec_via = "" # For logging

            # Ensure we are in the correct directory before execution
            cd_cmd = f"cd {shlex.quote(self.remote_cwd)}"

            if exec_mode == 'slurm':
                # Wrap in srun
                srun_command = f"srun --pty {user_command}"
                command_to_run = f"{cd_cmd} && {srun_command}"
                exec_via = "srun"
                logger.info(f"Executing command via {exec_via} due to execution_mode='slurm': {command_to_run}")
                # Use a longer timeout for potential Slurm allocation delays
                timeout = 600 # 10 min timeout
            else: # Default to 'direct'
                command_to_run = f"{cd_cmd} && {user_command}"
                exec_via = "direct SSH"
                logger.info(f"Executing command via {exec_via} due to execution_mode='direct': {command_to_run}")
                timeout = 300 # 5 min timeout

            try:
                # Execute command - relies on execute_command raising RuntimeError on failure
                output = self.active_ssh_manager.execute_command(command_to_run, timeout=timeout)
                # Print the raw output
                if output:
                     console.print(output)
                else:
                     console.print(f"(Command via {exec_via} produced no output)", style="dim")
                return None # Output printed directly

            except ConnectionError as e:
                logger.error(f"Connection error during /hpc_run (via {exec_via}): {e}", exc_info=False)
                try: self.active_ssh_manager.disconnect()
                except Exception: pass
                self.active_ssh_manager = None
                self.remote_cwd = None
                raise ConnectionError(f"Connection error during command execution (via {exec_via}): {e}. Connection closed.") from e
            except TimeoutError as e:
                 logger.error(f"Timeout error during /hpc_run (via {exec_via}, timeout={timeout}s): {e}", exc_info=False)
                 raise TimeoutError(f"Remote command execution (via {exec_via}) timed out after {timeout} seconds: {e}") from e
            except RuntimeError as e:
                 logger.error(f"Runtime error during /hpc_run (via {exec_via}): {e}", exc_info=False)
                 # Check for common errors based on the raised RuntimeError message
                 if exec_mode == 'slurm' and "srun: error:" in str(e):
                     raise RuntimeError(f"Slurm execution failed: {e}") from e
                 # Let execute_command handle the display of the runtime error message
                 raise e
            except Exception as e:
                logger.error(f"Unexpected error executing command via {exec_via}: {e}", exc_info=True)
                raise RuntimeError(f"Unexpected error executing remote command (via {exec_via}): {e}") from e

        except argparse.ArgumentError as e:
             raise e
        except SystemExit:
             return None # Help was printed


    def _handle_hpc_slurm_run(self, args: List[str]) -> Optional[str]:
        """Executes a command explicitly within a Slurm allocation (srun). Prints output."""
        # This command ignores the execution_mode setting.
        parser = self._create_parser("hpc_slurm_run", self._command_map['hpc_slurm_run']['help'], add_help=True)
        parser.add_argument("command_string", nargs=argparse.REMAINDER, help="The command and arguments to execute via srun.")

        try:
            parsed_args = parser.parse_args(args)

            if not parsed_args.command_string:
                 raise argparse.ArgumentError(None, "Missing command to execute via srun.")

            if not self.active_ssh_manager or not self.active_ssh_manager.is_connected:
                raise ConnectionError("Not connected to HPC. Use /hpc_connect first.")
            if self.remote_cwd is None:
                 raise ConnectionError("Remote working directory unknown. Please use /hpc_connect again.")

            user_command = " ".join(shlex.quote(arg) for arg in parsed_args.command_string)
            # Use --pty for interactive-like behavior if possible
            srun_command = f"srun --pty {user_command}"
            full_command = f"cd {shlex.quote(self.remote_cwd)} && {srun_command}"
            timeout = 600 # 10 min timeout

            try:
                logger.info(f"Executing command explicitly via srun using active SSH connection: {full_command}")
                # Relies on execute_command raising RuntimeError on failure
                output = self.active_ssh_manager.execute_command(full_command, timeout=timeout)
                if output:
                     console.print(output)
                else:
                     console.print("(Explicit srun command produced no output)", style="dim")
                return None # Output printed

            except ConnectionError as e:
                logger.error(f"Connection error during explicit /hpc_slurm_run: {e}", exc_info=False)
                try: self.active_ssh_manager.disconnect()
                except Exception: pass
                self.active_ssh_manager = None
                self.remote_cwd = None
                raise ConnectionError(f"Connection error during explicit srun execution: {e}. Connection closed.") from e
            except TimeoutError as e:
                 logger.error(f"Timeout error during explicit /hpc_slurm_run (timeout={timeout}s): {e}", exc_info=False)
                 raise TimeoutError(f"Explicit command execution via srun timed out after {timeout} seconds: {e}") from e
            except RuntimeError as e:
                 logger.error(f"Runtime error during explicit /hpc_slurm_run: {e}", exc_info=False)
                 if "srun: error:" in str(e):
                     # Specific Slurm error
                     raise RuntimeError(f"Explicit Slurm execution failed: {e}") from e
                 raise e # Re-raise other runtime errors
            except Exception as e:
                logger.error(f"Unexpected error executing explicit command via srun: {e}", exc_info=True)
                raise RuntimeError(f"Unexpected error executing explicit remote srun command: {e}") from e

        except argparse.ArgumentError as e:
             raise e
        except SystemExit:
             return None # Help was printed


    def _handle_ls(self, args: List[str]) -> Optional[str]:
        """Handles the /ls command locally or remotely. Prints output."""
        parser = self._create_parser("ls", self._command_map['ls']['help'], add_help=True)
        # Allow unknown args for now, just ignore them
        parsed_args, unknown_args = parser.parse_known_args(args)
        if unknown_args:
             logger.warning(f"Ignoring unsupported arguments/options for /ls: {unknown_args}")

        try:
            status = self.get_status()
            items = []

            if status['mode'] == 'connected':
                # --- Remote LS ---
                if not self.active_ssh_manager or self.remote_cwd is None:
                    raise ConnectionError("Internal state error: Connected mode but no SSH manager or remote CWD.")

                # Use find command to get type and name, handle potential errors
                # %Y = item type (f=file, d=dir, l=link), %P = name relative to starting point (.)
                # Use -print0 for safe handling of names
                find_cmd = f"find . -mindepth 1 -maxdepth 1 -printf '%Y\\0%P\\0'"
                full_command = f"cd {shlex.quote(self.remote_cwd)} && {find_cmd}"

                try:
                    logger.info(f"Fetching remote file list for /ls with command: {full_command}")
                    output = self.active_ssh_manager.execute_command(full_command, timeout=30)

                    if output:
                        # Split by null character, pairs of type and name
                        parts = output.strip('\0').split('\0')
                        if len(parts) % 2 != 0:
                             logger.warning(f"Unexpected output format from remote find (odd number of parts): {output}")
                             # Attempt to process anyway or raise error? Raise for now.
                             raise RuntimeError(f"Unexpected output format from remote find: {output}")

                        for i in range(0, len(parts), 2):
                             type_char = parts[i]
                             name = parts[i+1]
                             is_dir = (type_char == 'd')
                             # Could handle 'l' for links differently if needed
                             items.append(colorize_filename(name, is_dir=is_dir))

                except (ConnectionError, TimeoutError, RuntimeError) as e:
                    # Let outer handler deal with connection/timeout issues
                    # RuntimeError will be raised if `find` fails (e.g., permissions)
                    raise e
                except Exception as e:
                    logger.error(f"Unexpected error during remote /ls execution: {e}", exc_info=True)
                    raise RuntimeError(f"Unexpected error listing remote directory: {e}") from e

            else:
                # --- Local LS ---
                logger.info(f"Fetching local file list for /ls in directory: {self.local_cwd}")
                try:
                    for entry in sorted(os.listdir(self.local_cwd), key=str.lower):
                        try:
                            full_path = os.path.join(self.local_cwd, entry)
                            is_dir = os.path.isdir(full_path)
                            # Could add check for os.islink if needed
                            items.append(colorize_filename(entry, is_dir=is_dir))
                        except OSError as item_err: # Handle errors accessing specific items (e.g., permissions)
                             logger.warning(f"Could not stat item '{entry}' in {self.local_cwd}: {item_err}")
                             items.append(Text(f"{entry} (error)", style="error"))
                except FileNotFoundError:
                     # The CWD itself doesn't exist (e.g., deleted after start)
                     raise FileNotFoundError(f"Local directory not found: {self.local_cwd}")
                except PermissionError:
                     raise PermissionError(f"Permission denied listing local directory: {self.local_cwd}")
                except Exception as e:
                     logger.error(f"Unexpected error during local /ls execution: {e}", exc_info=True)
                     raise RuntimeError(f"Unexpected error listing local directory: {e}") from e

            # --- Display Results (Common for Local/Remote) ---
            current_dir_display = status['cwd']
            if not items:
                console.print(f"(Directory '{current_dir_display}' is empty)", style="info")
                return None

            # Sort by name (case-insensitive) - already sorted for local, sort remote here
            if status['mode'] == 'connected':
                 items.sort(key=lambda text: text.plain.lower())

            # Display using Rich Columns
            columns = Columns(items, expand=True, equal=True, column_first=True)
            console.print(f"Contents of '{current_dir_display}':")
            console.print(columns)
            return None # Output printed

        except argparse.ArgumentError as e:
             raise e
        except SystemExit:
             return None # Help was printed


    def _handle_cd(self, args: List[str]) -> Optional[str]:
        """Handles the /cd command locally or remotely. Prints output."""
        parser = self._create_parser("cd", self._command_map['cd']['help'], add_help=True)
        parser.add_argument("directory", help="The target directory")

        try:
            parsed_args = parser.parse_args(args)
            target_dir_arg = parsed_args.directory
            status = self.get_status()

            if status['mode'] == 'connected':
                # --- Remote CD ---
                if not self.active_ssh_manager or self.remote_cwd is None:
                    raise ConnectionError("Internal state error: Connected mode but no SSH manager or remote CWD.")

                current_dir = self.remote_cwd
                # Command to attempt cd and then print the new working directory's absolute path using pwd -P
                # Check directory existence and type first for better error message
                check_dir_cmd = f"cd {shlex.quote(current_dir)} && test -d {shlex.quote(target_dir_arg)}"
                test_command = f"cd {shlex.quote(current_dir)} && cd {shlex.quote(target_dir_arg)} && pwd -P"
                logger.info(f"Attempting remote directory change to: {target_dir_arg}")

                try:
                    # 1. Verify it's a directory first (execute_command will raise RuntimeError if test -d fails)
                    self.active_ssh_manager.execute_command(check_dir_cmd, timeout=15)

                    # 2. If directory check passes, get the new absolute path (execute_command raises RuntimeError if cd or pwd fails)
                    new_dir_output = self.active_ssh_manager.execute_command(test_command, timeout=15)
                    new_dir = new_dir_output.strip()

                    # Basic validation: should be a non-empty string starting with '/'
                    if not new_dir or not new_dir.startswith("/"):
                        logger.error(f"Failed to get pwd for remote directory '{target_dir_arg}'. 'pwd -P' command returned unexpected output: {new_dir_output}")
                        raise RuntimeError(f"Failed to change remote directory to '{target_dir_arg}'. Could not verify new path.")

                    self.remote_cwd = new_dir
                    logger.info(f"Successfully changed remote working directory to: {self.remote_cwd}")
                    console.print(f"Remote working directory changed to: {self.remote_cwd}", style="info")
                    return None # Output printed

                except (ConnectionError, TimeoutError) as e:
                     raise e # Let outer handler deal with these
                except RuntimeError as e:
                     # Catch runtime errors from execute_command (e.g., cd failed, test -d failed, pwd failed)
                     logger.error(f"Failed to change remote directory to '{target_dir_arg}': {e}", exc_info=False)
                     # Provide a clearer error message based on common failure points
                     if "test -d" in str(e) or "No such file or directory" in str(e) or "Not a directory" in str(e):
                          raise NotADirectoryError(f"Remote path is not a directory or does not exist: '{target_dir_arg}' (relative to {current_dir})") from e
                     elif "Permission denied" in str(e):
                          raise PermissionError(f"Permission denied accessing remote directory: '{target_dir_arg}' (relative to {current_dir})") from e
                     else:
                          raise RuntimeError(f"Failed to change remote directory to '{target_dir_arg}'. Error: {e}") from e
                except Exception as e:
                    logger.error(f"Unexpected error changing remote directory to '{target_dir_arg}': {e}", exc_info=True)
                    raise RuntimeError(f"Unexpected error changing remote directory: {e}") from e

            else:
                # --- Local CD ---
                logger.info(f"Attempting to change local directory from '{self.local_cwd}' to '{target_dir_arg}'")
                try:
                    # Construct the target path relative to the current local CWD
                    target_path = Path(self.local_cwd) / target_dir_arg
                    # Use resolve(strict=True) which checks existence and resolves symlinks/..
                    # This raises FileNotFoundError if it doesn't exist
                    abs_path = target_path.resolve(strict=True)

                    # Check if the resolved path is actually a directory
                    if not abs_path.is_dir():
                         raise NotADirectoryError(f"Local path is not a directory: '{abs_path}'")

                    # Update local CWD (no need for os.access check as resolve/is_dir handle permissions implicitly)
                    self.local_cwd = str(abs_path)
                    logger.info(f"Successfully changed local working directory to: {self.local_cwd}")
                    console.print(f"Local working directory changed to: {self.local_cwd}", style="info")
                    return None # Output printed

                except FileNotFoundError as e:
                     # Raised by resolve(strict=True) if path doesn't exist
                     raise FileNotFoundError(f"Local directory not found: '{target_path}'") from e
                except NotADirectoryError as e:
                     raise e # Re-raise
                except PermissionError as e: # Although less likely with resolve, catch defensively
                     raise PermissionError(f"Permission denied accessing local directory: '{target_path}'") from e
                except Exception as e:
                    logger.error(f"Unexpected error changing local directory to '{target_dir_arg}': {e}", exc_info=True)
                    raise RuntimeError(f"Unexpected error changing local directory: {e}") from e

        except argparse.ArgumentError as e:
             raise e
        except SystemExit:
             return None # Help was printed


    def _handle_hpc_slurm_submit(self, args: List[str]) -> Optional[str]:
        """Submits a Slurm job script, potentially adding --singularity. Prints output."""
        parser = self._create_parser("hpc_slurm_submit", self._command_map['hpc_slurm_submit']['help'], add_help=True)
        parser.add_argument("script_path", help="Path to the local Slurm script file")
        parser.add_argument("options_json", nargs='?', default='{}', help="Optional Slurm options as JSON string (e.g., '{\"--nodes\": 1, \"--time\": \"01:00:00\"}')")

        slurm_manager = None
        try:
            parsed_args = parser.parse_args(args)

            # Parse user-provided options
            try:
                user_options = json.loads(parsed_args.options_json)
                if not isinstance(user_options, dict):
                    raise ValueError("Options JSON must decode to a dictionary.")
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON provided for options: {e}") from e

            # Resolve script path relative to local CWD
            script_path_obj = (Path(self.local_cwd) / parsed_args.script_path).resolve()
            script_path = str(script_path_obj)

            if not os.path.isfile(script_path):
                 raise FileNotFoundError(f"Script file not found at '{script_path}'")

            with open(script_path, 'r') as f:
                script_content = f.read()

            # --- Handle Singularity Option ---
            job_options = user_options.copy() # Start with user options
            use_singularity_config = self.config.get_slurm_use_singularity()
            singularity_flag = "--singularity" # Assuming cwltool-like flag
            docker_flag = "--docker" # Assuming cwltool-like flag

            # Check if user explicitly set a container flag
            user_set_singularity = singularity_flag in job_options
            user_set_docker = docker_flag in job_options

            if use_singularity_config and not user_set_singularity and not user_set_docker:
                # Config says use singularity, and user didn't specify singularity or docker
                # Check if user explicitly disabled singularity (e.g., "--singularity false")
                singularity_value = job_options.get(singularity_flag)
                if not (isinstance(singularity_value, bool) and not singularity_value): # Add if not explicitly set to false
                    logger.info(f"Adding '{singularity_flag}' to job options based on config (slurm_use_singularity=True)")
                    job_options[singularity_flag] = True # Add the flag
            elif not use_singularity_config and not user_set_singularity and not user_set_docker:
                 logger.info(f"Not adding '{singularity_flag}' to job options based on config (slurm_use_singularity=False)")
            elif user_set_singularity:
                 logger.info(f"User explicitly provided '{singularity_flag}' in options_json: {job_options[singularity_flag]}")
            elif user_set_docker:
                 logger.info(f"User explicitly provided '{docker_flag}' in options_json, not adding '{singularity_flag}'.")
            # --- End Handle Singularity Option ---


            slurm_manager = self._get_slurm_manager() # Gets manager with active (or temp) SSH

            logger.info(f"Submitting Slurm job from script: {script_path} with effective options: {job_options}")
            console.print(f"Submitting Slurm job from '{os.path.basename(script_path)}'...", style="info")

            job_id = slurm_manager.submit_job(script_content, job_options)
            console.print(f"Slurm job submitted with ID: {job_id}", style="bold green")
            return None # Output printed

        except argparse.ArgumentError as e: raise e
        except SystemExit: return None # Help printed
        except FileNotFoundError as e: raise e
        except ValueError as e: # Catches JSON errors and dict validation
            raise e
        except (ConnectionError, RuntimeError) as e:
            # Catch errors from _get_slurm_manager or submit_job
            raise e # Re-raise for execute_command
        except Exception as e:
            logger.error("Error submitting Slurm job", exc_info=True)
            raise RuntimeError(f"Error submitting Slurm job: {e}") from e
        finally:
            # Close the SSH connection ONLY if it was temporary for this command
            self._close_slurm_manager_ssh(slurm_manager)


    def _handle_hpc_slurm_status(self, args: List[str]) -> Optional[str]:
        """Gets Slurm job status. Prints output."""
        parser = self._create_parser("hpc_slurm_status", self._command_map['hpc_slurm_status']['help'], add_help=True)
        scope_group = parser.add_mutually_exclusive_group()
        scope_group.add_argument("--job-id", help="Show status for a specific job ID.")
        scope_group.add_argument("--user", action='store_true', help="Show status for the current user's jobs (default if no scope specified).")
        scope_group.add_argument("--all", action='store_true', help="Show status for all jobs in the queue.")
        parser.add_argument("--waiting-summary", action='store_true', help="Include a summary of waiting times for pending jobs.")

        slurm_manager = None
        try:
            parsed_args = parser.parse_args(args)

            job_id = parsed_args.job_id
            query_user = parsed_args.user
            query_all = parsed_args.all
            # Default to user if no scope is specified
            if not job_id and not query_user and not query_all:
                query_user = True
                logger.info("No scope specified for /hpc_slurm_status, defaulting to --user.")

            slurm_manager = self._get_slurm_manager()
            logger.info(f"Getting Slurm status info (job_id={job_id}, user={query_user}, all={query_all}, summary={parsed_args.waiting_summary})")
            console.print("Fetching Slurm queue information...", style="info")

            # Assume get_queue_info returns structured data (e.g., dict with 'jobs' list and 'waiting_summary' dict)
            status_info = slurm_manager.get_queue_info(
                job_id=job_id,
                query_user=query_user,
                query_all=query_all,
                waiting_summary=parsed_args.waiting_summary
            )

            # --- Format and Print Output ---
            jobs = status_info.get("jobs", [])
            summary = status_info.get("waiting_summary")

            if not jobs and not summary:
                console.print("No Slurm jobs found matching the criteria.", style="info")
            elif not jobs and summary and not summary.get('pending_count', 0):
                 console.print("No running/pending Slurm jobs found matching the criteria.", style="info")
                 # Still print summary if it has info (e.g., message)
            else:
                # Use Rich Table for better formatting
                # from rich.table import Table # Already imported at top
                table = Table(title="Slurm Job Status", show_header=True, header_style="bold magenta")

                # Define columns based on available fields in the first job (if any)
                # Adjust field names and headers as needed based on SlurmManager output
                field_map = {
                    "job_id": "JobID", "partition": "Partition", "name": "Name",
                    "user": "User", "state_compact": "State", "time_used": "Time",
                    "nodes": "Nodes", "reason": "Reason", "submit_time_str": "SubmitTime"
                }
                if jobs:
                    # Determine available fields dynamically from the first job
                    available_fields = [f for f in field_map if f in jobs[0]]
                else:
                    # If no jobs, still create table structure if summary exists
                    # Use a default set or all possible fields
                    available_fields = ["job_id", "partition", "name", "user", "state_compact", "time_used", "nodes", "reason", "submit_time_str"]


                display_fields = [f for f in field_map if f in available_fields] # Fields to display
                for field_key in display_fields:
                     table.add_column(field_map[field_key])

                # Add rows
                for job in jobs:
                    row_values = [str(job.get(field, '')) for field in display_fields]
                    table.add_row(*row_values)

                if table.row_count > 0:
                     console.print(table)
                elif not summary: # No jobs and no summary
                     console.print("No Slurm jobs found matching the criteria.", style="info")


            # Print waiting summary if requested and available
            if summary:
                summary_lines = ["[bold]Waiting Time Summary (Pending Jobs)[/bold]"]
                count = summary.get('pending_count', 0)
                summary_lines.append(f"  Count: {count}")
                if count > 0:
                    if "avg_wait_human" in summary: summary_lines.append(f"  Average Wait: {summary.get('avg_wait_human', 'N/A')}")
                    if "min_wait_human" in summary: summary_lines.append(f"  Min Wait:     {summary.get('min_wait_human', 'N/A')}")
                    if "max_wait_human" in summary: summary_lines.append(f"  Max Wait:     {summary.get('max_wait_human', 'N/A')}")
                elif "message" in summary:
                     summary_lines.append(f"  Info: {summary['message']}")

                if len(summary_lines) > 1: # Only print if there's more than the header
                     console.print(Panel("\n".join(summary_lines), expand=False))
                elif not jobs: # No jobs and only header in summary
                     console.print("No pending jobs found for summary.", style="info")


            return None # Output printed

        except argparse.ArgumentError as e: raise e
        except SystemExit: return None # Help printed
        except (ConnectionError, ValueError, RuntimeError) as e:
            raise e # Re-raise for execute_command
        except Exception as e:
            logger.error(f"Error getting Slurm job status", exc_info=True)
            raise RuntimeError(f"Error getting Slurm job status: {e}") from e
        finally:
            self._close_slurm_manager_ssh(slurm_manager)


    def _handle_hpc_cred_get(self, args: List[str]) -> Optional[str]:
        """Gets HPC password status from keyring. Prints output."""
        parser = self._create_parser("hpc_cred_get", self._command_map['hpc_cred_get']['help'], add_help=True)
        parser.add_argument("username", help="HPC username")

        try:
            parsed_args = parser.parse_args(args)

            # Use CredentialManager directly (doesn't need active SSH)
            # Get system name from config if possible
            system_name_base = self.config.get('HPC', 'credential_system', 'dayhoff_hpc')
            # CredentialManager might combine this with hostname internally, adjust if needed
            cred_manager = CredentialManager(system_name=system_name_base) # Pass base name

            password_found = cred_manager.get_password(username=parsed_args.username) is not None
            # Use the actual system name used by the manager if available
            actual_system_name = getattr(cred_manager, 'system_name', system_name_base)

            if password_found:
                 logger.info(f"Password found for user '{parsed_args.username}' (system: {actual_system_name}) in keyring.")
                 console.print(f"Password found for user '{parsed_args.username}' (system: {actual_system_name}) in system keyring.", style="info")
            else:
                 logger.info(f"No stored password found for user '{parsed_args.username}' (system: {actual_system_name}) in keyring.")
                 console.print(f"No stored password found for user '{parsed_args.username}' (system: {actual_system_name}) in system keyring.", style="info")
            return None # Output printed

        except argparse.ArgumentError as e: raise e
        except SystemExit: return None # Help printed
        except Exception as e:
            logger.error(f"Error retrieving credentials for {args[0] if args else ''}", exc_info=True)
            raise RuntimeError(f"Error retrieving credentials: {e}") from e


    # --- Workflow & Environment Handlers ---

    def _handle_wf_gen(self, args: List[str]) -> Optional[str]:
        """Handles the /wf_gen command using the configured language. Prints output."""
        parser = self._create_parser("wf_gen", self._command_map['wf_gen']['help'], add_help=True)
        parser.add_argument("steps_json", help="Workflow steps definition as JSON string (list or dict)")

        try:
            parsed_args = parser.parse_args(args)

            try:
                steps = json.loads(parsed_args.steps_json)
                if not isinstance(steps, (list, dict)):
                     raise ValueError("Steps JSON must decode to a list or dictionary.")
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON provided for steps: {e}") from e

            language = self.config.get_workflow_language()
            executor = self.config.get_workflow_executor(language) # Get configured executor
            logger.info(f"Generating workflow using configured language: {language} (default executor: {executor})")
            console.print(f"Generating {language.upper()} workflow (default executor: {executor or 'N/A'})...", style="info")

            # Assuming WorkflowGenerator exists and has a method like generate_workflow
            generator = WorkflowGenerator()
            # Pass language to the generator method
            # TODO: Update WorkflowGenerator.generate_workflow signature if needed
            # For now, assume it takes steps and language
            # workflow_output = generator.generate_workflow(steps, language=language)
            # Placeholder until generate_workflow exists
            if language == 'cwl':
                 workflow_output = generator.generate_cwl(steps) # Assuming this exists
            elif language == 'nextflow':
                 workflow_output = generator.generate_nextflow(steps) # Assuming this exists
            else:
                 raise NotImplementedError(f"Workflow generation for language '{language}' is not implemented in WorkflowGenerator.")


            if workflow_output is None or not workflow_output.strip():
                console.print(f"Workflow generation for language '{language}' returned no output.", style="warning")
                return None

            # Print the generated workflow content
            console.print(Panel(workflow_output, title=f"Generated {language.upper()} Workflow", border_style="green", expand=True))
            return None # Output printed

        except argparse.ArgumentError as e: raise e
        except SystemExit: return None # Help printed
        except ValueError as e: # Catch JSON errors or validation errors
             raise e
        except NotImplementedError as e:
             # Catch if generator doesn't support the language
             logger.warning(f"Workflow generation not implemented for language '{language}': {e}")
             raise NotImplementedError(f"Workflow generation for language '{language}' is not implemented.") from e
        except Exception as e:
            logger.error("Error generating workflow", exc_info=True)
            raise RuntimeError(f"Error generating workflow: {e}") from e


    def _handle_language(self, args: List[str]) -> Optional[str]:
        """Handles the /language command to view or set the workflow language. Prints output."""
        parser = self._create_parser(
            "language",
            self._command_map['language']['help'],
            add_help=True
        )
        parser.add_argument("language", nargs='?', help="The workflow language to set (optional).")

        try:
            parsed_args = parser.parse_args(args)

            if parsed_args.language is None:
                # Show current language and its executor
                current_language = self.config.get_workflow_language()
                current_executor = self.config.get_workflow_executor(current_language) or "N/A"
                console.print(f"Current default workflow language: [bold cyan]{current_language}[/bold cyan]")
                console.print(f"Default executor for {current_language.upper()}: [bold cyan]{current_executor}[/bold cyan]")
            else:
                # Set the language
                requested_language = parsed_args.language.lower()
                if requested_language in ALLOWED_WORKFLOW_LANGUAGES:
                    try:
                        # Use config.set to update and save
                        self.config.set('WORKFLOWS', 'default_workflow_type', requested_language)
                        logger.info(f"Workflow language set to: {requested_language}")
                        # Show the executor that will now be used by default
                        new_executor = self.config.get_workflow_executor(requested_language) or "N/A"
                        console.print(f"Workflow language set to: [bold cyan]{requested_language}[/bold cyan]", style="info")
                        console.print(f"(Default executor for {requested_language.upper()} is now: [bold cyan]{new_executor}[/bold cyan])", style="info")
                    except Exception as e:
                        logger.error(f"Failed to set workflow language to {requested_language}: {e}", exc_info=True)
                        raise RuntimeError(f"Failed to save workflow language setting: {e}") from e
                else:
                    # Raise error for invalid language
                    allowed_str = ", ".join(ALLOWED_WORKFLOW_LANGUAGES)
                    raise argparse.ArgumentError(None, f"Invalid language '{parsed_args.language}'. Allowed languages are: {allowed_str}")

            return None # Output printed

        except argparse.ArgumentError as e:
            raise e # Re-raise for execute_command
        except SystemExit:
             return None # Help was printed


    # --- File Queue Handlers ---

    def _handle_queue(self, args: List[str]) -> Optional[str]:
        """Handles the /queue command with subparsers. Prints output directly."""
        parser = self._create_parser("queue", self._command_map['queue']['help'], add_help=True)
        subparsers = parser.add_subparsers(dest="subcommand", title="Subcommands",
                                           description="Valid subcommands for /queue",
                                           help="Action to perform on the file queue")

        # --- Subparser: add ---
        parser_add = subparsers.add_parser("add", help="Add file(s) or directory(s) (recursive) to the queue.", add_help=True)
        parser_add.add_argument("paths", nargs='+', help="One or more paths relative to the current working directory.")

        # --- Subparser: show ---
        parser_show = subparsers.add_parser("show", help="Display the files currently in the queue.", add_help=True)

        # --- Subparser: remove ---
        parser_remove = subparsers.add_parser("remove", help="Remove files from the queue by index.", add_help=True)
        parser_remove.add_argument("indices", nargs='+', type=int, help="One or more index numbers (from /queue show).")

        # --- Subparser: clear ---
        parser_clear = subparsers.add_parser("clear", help="Remove all files from the queue.", add_help=True)

        # --- Parse arguments ---
        try:
            # Handle case where no subcommand is given
            if not args:
                 parser.print_help()
                 return None

            parsed_args = parser.parse_args(args)

            # --- Execute subcommand logic ---
            if parsed_args.subcommand == "add":
                return self._handle_queue_add(parsed_args.paths)
            elif parsed_args.subcommand == "show":
                return self._handle_queue_show()
            elif parsed_args.subcommand == "remove":
                 return self._handle_queue_remove(parsed_args.indices)
            elif parsed_args.subcommand == "clear":
                 return self._handle_queue_clear()
            else:
                 # Should not happen if subcommand is required/checked, but handle defensively
                 parser.print_help()
                 return None

        except argparse.ArgumentError as e:
            raise e # Re-raise for execute_command to handle
        except SystemExit:
             return None # Help was printed
        # Catch specific errors from queue handlers
        except FileNotFoundError as e: raise e
        except NotADirectoryError as e: raise e
        except PermissionError as e: raise e
        except IndexError as e: raise e # From remove handler
        except (ConnectionError, TimeoutError) as e: raise e # From remote operations
        except Exception as e:
            logger.error(f"Error during /queue {args}: {e}", exc_info=True)
            raise RuntimeError(f"Error executing queue command: {e}") from e


    def _handle_queue_add(self, paths_to_add: List[str]) -> None:
        """Adds files/directories to the queue. Prints output."""
        status = self.get_status()
        added_count = 0
        skipped_count = 0
        error_count = 0
        processed_dirs: Set[str] = set() # Track dirs to avoid re-processing if listed multiple times

        for relative_path in paths_to_add:
            try:
                abs_path, cwd = self._resolve_path(relative_path)
                path_type = self._get_path_type(abs_path)

                if path_type == 'file':
                    if abs_path not in self.file_queue:
                        self.file_queue.append(abs_path)
                        console.print(f"Added file: {abs_path}", style="info")
                        added_count += 1
                    else:
                        console.print(f"Skipped (already in queue): {abs_path}", style="dim")
                        skipped_count += 1
                elif path_type == 'directory':
                    if abs_path in processed_dirs:
                         console.print(f"Skipped (directory already processed): {abs_path}", style="dim")
                         skipped_count += 1 # Count skipped dirs? Or just files? Let's count as 1 skip.
                         continue

                    processed_dirs.add(abs_path)
                    console.print(f"Scanning directory: {abs_path}...", style="info")
                    subdir_files_added = 0
                    subdir_files_skipped = 0

                    if status['mode'] == 'connected':
                        # Remote recursive listing
                        found_files = self._list_remote_files_recursive(abs_path)
                    else:
                        # Local recursive listing
                        found_files = []
                        for root, _, files in os.walk(abs_path):
                            for filename in files:
                                try:
                                     # Ensure correct absolute path construction
                                     file_abs_path = str(Path(root) / filename)
                                     # Redundant check, but safe: Check if it's actually a file
                                     if os.path.isfile(file_abs_path):
                                          found_files.append(file_abs_path)
                                     else: # Should not happen with files from os.walk
                                          logger.warning(f"os.walk listed non-file item? {file_abs_path}")
                                except OSError as walk_err:
                                     logger.warning(f"Error accessing file during local walk: {filename} in {root} - {walk_err}")
                                     # Should we count this as an error? For now, just log.


                    # Add files found inside the directory
                    for file_path in found_files:
                        if file_path not in self.file_queue:
                            self.file_queue.append(file_path)
                            subdir_files_added += 1
                        else:
                            subdir_files_skipped += 1

                    added_count += subdir_files_added
                    skipped_count += subdir_files_skipped
                    console.print(f"  -> Added {subdir_files_added} files from directory {abs_path} ({subdir_files_skipped} skipped).", style="info")

            except FileNotFoundError as e:
                 logger.warning(f"Could not add path '{relative_path}': {e}")
                 console.print(f"[warning]Skipped (not found):[/warning] '{relative_path}' (in {status['cwd']})")
                 error_count += 1
            except NotADirectoryError as e: # Should be caught by _get_path_type more specifically
                 logger.warning(f"Path is not a file or directory '{relative_path}': {e}")
                 console.print(f"[warning]Skipped (not a file/directory):[/warning] '{relative_path}'")
                 error_count += 1
            except PermissionError as e:
                 logger.warning(f"Permission denied for path '{relative_path}': {e}")
                 console.print(f"[error]Skipped (permission denied):[/error] '{relative_path}'")
                 error_count += 1
            except (ConnectionError, TimeoutError, RuntimeError) as e:
                 logger.error(f"Error processing path '{relative_path}': {e}")
                 console.print(f"[error]Error processing '{relative_path}': {e}[/error]")
                 error_count += 1
                 # Stop processing further paths if connection seems lost? Maybe not, try others.
            except Exception as e:
                 logger.error(f"Unexpected error processing path '{relative_path}': {e}", exc_info=True)
                 console.print(f"[error]Unexpected error processing '{relative_path}': {e}[/error]")
                 error_count += 1

        console.print(f"\nQueue add summary: Added {added_count}, Skipped {skipped_count}, Errors {error_count}. Total in queue: {len(self.file_queue)}", style="bold")
        return None # Output printed

    def _handle_queue_show(self) -> None:
        """Displays the current file queue. Prints output."""
        if not self.file_queue:
            console.print("File queue is empty.", style="info")
            return None

        table = Table(title=f"File Queue ({len(self.file_queue)} items)", show_header=True, header_style="bold magenta")
        table.add_column("Index", style="dim", width=6, justify="right")
        table.add_column("Absolute Path")

        # Use colorize_filename for the path display
        for i, file_path in enumerate(self.file_queue):
             # Simple coloring based on file extension from the absolute path
             # We don't know if it's local or remote here, assume file
             colored_name = colorize_filename(os.path.basename(file_path))
             # Display the full path but color the basename
             dir_name = os.path.dirname(file_path)
             display_path = Text.assemble(dir_name + os.path.sep, colored_name)
             table.add_row(str(i + 1), display_path) # 1-based index for user

        console.print(table)
        return None # Output printed

    def _handle_queue_remove(self, indices_to_remove: List[int]) -> None:
        """Removes files from the queue by 1-based index. Prints output."""
        if not self.file_queue:
            console.print("File queue is already empty.", style="warning")
            return None

        current_queue_size = len(self.file_queue)
        # Convert 1-based input indices to 0-based list indices
        # Validate indices immediately
        valid_zero_based_indices: Set[int] = set()
        invalid_inputs: List[str] = []

        for index_arg in indices_to_remove:
            if 1 <= index_arg <= current_queue_size:
                valid_zero_based_indices.add(index_arg - 1)
            else:
                invalid_inputs.append(str(index_arg))

        if invalid_inputs:
            console.print(f"[error]Invalid index numbers provided:[/error] {', '.join(invalid_inputs)}. Use indices from 1 to {current_queue_size}.", style="error")
            # Optionally, proceed with valid indices or stop? Let's proceed.
            # raise ValueError(f"Invalid index numbers provided: {', '.join(invalid_inputs)}. Use indices from 1 to {current_queue_size}.")


        if not valid_zero_based_indices:
             if not invalid_inputs: # No valid indices and no invalid inputs probably means no indices given? Argparse handles.
                  console.print("No valid indices provided to remove.", style="warning")
             return None # Nothing to remove

        # Remove items by index, working from highest index downwards to avoid shifting issues
        removed_count = 0
        removed_items_display = []
        sorted_indices = sorted(list(valid_zero_based_indices), reverse=True)

        for index in sorted_indices:
            try:
                removed_item = self.file_queue.pop(index)
                removed_items_display.append(os.path.basename(removed_item)) # Show basename for brevity
                removed_count += 1
                logger.debug(f"Removed item at index {index+1}: {removed_item}")
            except IndexError:
                 # Should not happen due to validation, but handle defensively
                 logger.error(f"Internal error: IndexError removing previously validated index {index}")
                 console.print(f"[error]Internal error removing index {index+1}. Queue may be inconsistent.[/error]", style="error")

        if removed_count > 0:
             console.print(f"Removed {removed_count} item(s): {', '.join(removed_items_display)}.", style="info")
             console.print(f"Queue now contains {len(self.file_queue)} item(s).", style="info")
        elif invalid_inputs: # Only invalid inputs were given
             console.print("No items removed due to invalid indices.", style="warning")
        # else: # No valid or invalid indices provided scenario (should be handled earlier)

        return None # Output printed


    def _handle_queue_clear(self) -> None:
        """Clears the entire file queue. Prints output."""
        queue_size_before = len(self.file_queue)
        if queue_size_before == 0:
             console.print("File queue is already empty.", style="info")
        else:
             self.file_queue.clear()
             logger.info(f"Cleared {queue_size_before} items from the file queue.")
             console.print(f"Cleared {queue_size_before} items from the file queue.", style="info")
        return None # Output printed

