import json
import shlex
from typing import Any, List, Dict, Optional
import logging # Added logging
import os # Added os import
import subprocess # Added for running test scripts
import sys # Added for getting python executable
import textwrap # For formatting help text
import shlex # For shell quoting
import io # For capturing rich output

# --- Rich for coloring ---
from rich.console import Console
from rich.text import Text
from rich.columns import Columns
from rich.theme import Theme

# --- Core Components ---
# Import the GLOBAL config instance and renamed ALLOWED_WORKFLOW_LANGUAGES
from .config import config, ALLOWED_WORKFLOW_LANGUAGES, ALLOWED_EXECUTORS, get_executor_config_key # Updated import
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
# Removed AI/LLM imports as related commands are removed

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
        if style is None and ext_lower in {".gz", ".bz2", ".xz"}:
            _base2, ext2 = os.path.splitext(_base)
            ext2_lower = ext2.lower()
            style = COLOR_MAP.get(ext2_lower)
            if style is None:
                 style = COLOR_MAP.get(ext_lower, "default")
        elif style is None:
             style = "default"
        return Text(filename, style=style)

# --- End File Coloring Logic ---


class DayhoffService:
    """Shared backend service for both CLI and notebook interfaces"""

    def __init__(self):
        self.config = config
        self.local_fs = LocalFileSystem()
        self.file_inspector = FileInspector(self.local_fs)
        self.active_ssh_manager: Optional[SSHManager] = None
        self.remote_cwd: Optional[str] = None
        logger.info("DayhoffService initialized.")
        self._command_map = self._build_command_map()


    def _build_command_map(self) -> Dict[str, Dict[str, Any]]:
        """Builds a map of commands, their handlers, and help text."""
        # Generate executor help dynamically
        executor_help_lines = []
        for lang, execs in sorted(ALLOWED_EXECUTORS.items()):
            key = get_executor_config_key(lang)
            executor_help_lines.append(f"      {key} <executor> : Set default executor for {lang.upper()}. Allowed: {', '.join(execs)}")

        executor_help_text = "\n".join(executor_help_lines)

        return {
            "help": {"handler": self._handle_help, "help": "Show help for commands. Usage: /help [command_name]"},
            "test": {"handler": self._handle_test, "help": "Run or show information about internal tests. Usage: /test [test_name]"},
            "config": {
                "handler": self._handle_config,
                "help": textwrap.dedent(f"""\
                    Manage Dayhoff configuration.
                    Usage: /config <subcommand> [options]
                    Subcommands:
                      get <section> <key> [default] : Get a specific config value.
                      set <section> <key> <value>   : Set a config value (and save). Type '/config set' for examples.
                      save                          : Manually save the current configuration.
                      show [section|ssh]            : Show a specific section, 'ssh' (HPC config), or all config.
                    Workflow Settings (Section: WORKFLOWS):
                      default_workflow_type <lang>  : Set preferred language. Use '/language <lang>' command.
                    {executor_help_text}
                    Allowed languages: {", ".join(ALLOWED_WORKFLOW_LANGUAGES)}""")
            },
            "fs_head": {"handler": self._handle_fs_head, "help": "Show the first N lines of a local file. Usage: /fs_head <file_path> [num_lines=10]"},
            "hpc_connect": {"handler": self._handle_hpc_connect, "help": "Establish a persistent SSH connection to the HPC. Usage: /hpc_connect"},
            "hpc_disconnect": {"handler": self._handle_hpc_disconnect, "help": "Close the persistent SSH connection to the HPC. Usage: /hpc_disconnect"},
            "hpc_run": {"handler": self._handle_hpc_run, "help": "Execute a command on the HPC using the active connection. Usage: /hpc_run <command_string>"},
            "hpc_slurm_run": {"handler": self._handle_hpc_slurm_run, "help": "Execute a command within a Slurm allocation (srun). Usage: /hpc_slurm_run <command_string>"},
            "ls": {"handler": self._handle_ls, "help": "List files in the current remote directory with colors. Usage: /ls [ls_options_ignored]"},
            "cd": {"handler": self._handle_cd, "help": "Change the current remote directory. Usage: /cd <remote_directory>"},
            "hpc_slurm_submit": {"handler": self._handle_hpc_slurm_submit, "help": "Submit a Slurm job script. Usage: /hpc_slurm_submit <script_path> [options_json]"},
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
        }

    def get_available_commands(self) -> List[str]:
        """Returns a list of available command names (without the leading '/')."""
        return list(self._command_map.keys())

    def execute_command(self, command: str, args: List[str]) -> Any:
        """Execute a command"""
        logger.info(f"Executing command: /{command} with args: {args}")
        if command in self._command_map:
            command_info = self._command_map[command]
            handler = command_info["handler"]
            try:
                result = handler(args)
                logger.info(f"Command /{command} executed successfully.")
                return result if result is not None else ""
            except argparse.ArgumentError as e:
                 logger.warning(f"Argument error for /{command}: {e}")
                 if "usage:" in str(e).lower():
                     return f"Argument Error: {e}"
                 else:
                     usage = command_info.get('help', 'No help available.')
                     if not usage.strip().lower().startswith("usage:"):
                         usage = f"Usage: /{command} ..."
                     return f"Argument Error: {e}\n{usage}"
            except FileNotFoundError as e:
                 logger.warning(f"File not found during /{command}: {e}")
                 return f"Error: File not found - {e}"
            except ConnectionError as e:
                 logger.error(f"Connection error during /{command}: {e}", exc_info=False)
                 return f"Connection Error: {e}"
            except TimeoutError as e:
                 logger.error(f"Timeout error during /{command}: {e}", exc_info=False)
                 return f"Timeout Error: {e}"
            except Exception as e:
                logger.error(f"Error executing command /{command}: {e}", exc_info=True)
                return f"Error: {type(e).__name__}: {e}"
        else:
            logger.warning(f"Unknown command attempted: /{command}")
            return f"Unknown command: /{command}. Type /help for available commands."

    # --- Help Handler ---
    def _handle_help(self, args: List[str]) -> str:
        if not args:
            # General help
            current_language = self.config.get_workflow_language()
            # Get executor for the current language
            current_executor = self.config.get_workflow_executor(current_language) or "N/A"
            help_lines = [
                f"Dayhoff REPL - Type /<command> [arguments] to execute.",
                f"Current Workflow Language: {current_language} (set with /language)",
                f"Default Executor for {current_language.upper()}: {current_executor} (set with /config set WORKFLOWS ...)", # Added executor display
                "\nAvailable commands:"
            ]
            for cmd, info in sorted(self._command_map.items()):
                first_line = info['help'].split('\n')[0].strip()
                help_lines.append(f"  /{cmd:<20} - {first_line}")
            help_lines.append("\nType /help <command_name> for more details.")
            return "\n".join(help_lines)
        else:
            # Specific command help
            cmd_name = args[0]
            if cmd_name.startswith('/'):
                cmd_name = cmd_name[1:]
            if cmd_name in self._command_map:
                if cmd_name == 'test':
                    return self._handle_test([])
                elif cmd_name == 'config':
                    capture_stream = io.StringIO()
                    try:
                        original_stdout = sys.stdout
                        sys.stdout = capture_stream
                        self._handle_config(['--help'])
                    except SystemExit: pass
                    finally: sys.stdout = original_stdout
                    return capture_stream.getvalue()
                elif cmd_name == 'language':
                     capture_stream = io.StringIO()
                     try:
                         original_stdout = sys.stdout
                         sys.stdout = capture_stream
                         self._handle_language(['--help'])
                     except SystemExit: pass
                     finally: sys.stdout = original_stdout
                     return capture_stream.getvalue()
                else:
                    return self._command_map[cmd_name]['help']
            else:
                return f"Unknown command: /{cmd_name}"

    # --- Argument Parsers ---
    def _create_parser(self, prog: str, description: str, add_help: bool = False) -> argparse.ArgumentParser:
        """Creates an ArgumentParser instance for command parsing."""
        parser = argparse.ArgumentParser(
            prog=f"/{prog}",
            description=description,
            add_help=add_help,
            formatter_class=argparse.RawDescriptionHelpFormatter
        )
        def error(message):
            usage = parser.format_usage()
            if "usage:" not in message.lower():
                full_message = f"Invalid arguments for /{prog}: {message}\n{usage}"
            else:
                full_message = f"Invalid arguments for /{prog}: {message}"
            raise argparse.ArgumentError(None, full_message)
        parser.error = error
        return parser

    # --- Test Command Handler ---
    def _handle_test(self, args: List[str]) -> str:
        """Handles the /test command, running tests from the examples directory."""
        examples_dir = "examples"
        available_tests = {
            "cli": "Test non-interactive CLI execution (`dayhoff execute ...`).",
            "config": "Test loading and printing the current configuration.",
            "file_explorer": "Test local file head.",
            "hpc_bridge": "Test mock SSH/Slurm interactions.",
            "remote_fs": "Test SSH connection and remote `ls` execution.",
            # Updated help text for workflow tests
            "remote_workflow": "Test remote workflow execution via SSH (using configured language/executor).",
            "ssh_connection": "Test basic SSH connection and simple command execution.",
            "workflow": "Test local workflow generation (using configured language) and execution (using configured executor).",
        }

        if not args or (args and args[0] == 'help'):
            help_lines = [
                self._command_map['test']['help'],
                "\nAvailable tests:",
            ]
            for name, desc in sorted(available_tests.items()):
                script_path = os.path.join(examples_dir, f"test_{name}.py")
                exists_marker = "[exists]" if os.path.isfile(script_path) else "[missing]"
                help_lines.append(f"  {name:<20} - {desc} {exists_marker}")
            return "\n".join(help_lines)

        parser = self._create_parser("test", self._command_map['test']['help'])
        parser.add_argument("test_name", nargs='?', help="The name of the test to run.")
        try:
            parsed_args = parser.parse_args(args)
        except argparse.ArgumentError as e:
             return self._handle_test([])

        test_name = parsed_args.test_name
        if not test_name:
             return self._handle_test([])

        if test_name in available_tests:
            script_name = f"test_{test_name}.py"
            script_path = os.path.join(examples_dir, script_name)
            logger.info(f"Attempting to execute test script: {script_path}")

            if not os.path.isfile(script_path):
                raise FileNotFoundError(f"Test script '{script_path}' not found.")

            try:
                process = subprocess.run(
                    [sys.executable, script_path],
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=120
                )
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
                 return f"Error: Test script '{script_path}' timed out after 120 seconds."
            except Exception as e:
                logger.error(f"Failed to execute test script '{script_path}': {e}", exc_info=True)
                raise e
        else:
            valid_names = ", ".join(sorted(available_tests.keys()))
            parser.error(f"Unknown test_name '{test_name}'. Available tests are: {valid_names}")


    # --- Consolidated Config Handler ---
    def _handle_config(self, args: List[str]) -> Any:
        """Handles the /config command with subparsers."""
        # Help text is now dynamically generated in _build_command_map
        parser = self._create_parser(
            "config",
            self._command_map['config']['help'],
            add_help=True
        )
        subparsers = parser.add_subparsers(dest="subcommand", title="Subcommands",
                                           description="Valid subcommands for /config",
                                           help="Action to perform on the configuration")
        subparsers.required = True

        # --- Subparser: get ---
        parser_get = subparsers.add_parser("get", help="Get a specific config value.", add_help=False)
        parser_get.add_argument("section", help="Configuration section name")
        parser_get.add_argument("key", help="Configuration key name")
        parser_get.add_argument("default", nargs='?', default=None, help="Optional default value if key not found")
        def get_error(message): parser_get.error(message) # Simplified error override
        parser_get.error = get_error

        # --- Subparser: set ---
        # Generate dynamic examples for 'set' help
        set_examples = [
            "Examples:",
            "  /config set HPC username myuser",
            "  /config set DEFAULT log_level DEBUG",
            f"  /config set WORKFLOWS default_workflow_type nextflow",
        ]
        for lang, execs in sorted(ALLOWED_EXECUTORS.items()):
             key = get_executor_config_key(lang)
             example_exec = execs[1] if len(execs) > 1 else execs[0] # Pick a non-default example if possible
             set_examples.append(f"  /config set WORKFLOWS {key} {example_exec}")

        parser_set = subparsers.add_parser("set", help="Set a config value (and save).",
                                           description="Set a config value (and save).",
                                           epilog="\n".join(set_examples),
                                           formatter_class=argparse.RawDescriptionHelpFormatter,
                                           add_help=False)
        parser_set.add_argument("section", help="Configuration section name")
        parser_set.add_argument("key", help="Configuration key name")
        parser_set.add_argument("value", help="Value to set")
        def set_error(message):
            usage = parser_set.format_usage()
            epilog = parser_set.epilog or ""
            full_message = f"Invalid arguments for /config set: {message}\n{usage}\n{epilog}"
            raise argparse.ArgumentError(None, full_message)
        parser_set.error = set_error

        # --- Subparser: save ---
        parser_save = subparsers.add_parser("save", help="Manually save the current configuration.", add_help=False)
        def save_error(message): parser_save.error(message)
        parser_save.error = save_error

        # --- Subparser: show ---
        parser_show = subparsers.add_parser("show", help="Show a specific section, 'ssh' (HPC config), or all config.", add_help=False)
        parser_show.add_argument("section", nargs='?', default=None, help="Section name to show (e.g., HPC, WORKFLOWS, ssh) or omit for all.")
        def show_error(message): parser_show.error(message)
        parser_show.error = show_error

        # --- Handle 'set' help ---
        if len(args) == 1 and args[0] == 'set':
            capture_stream = io.StringIO()
            try:
                original_stdout = sys.stdout
                sys.stdout = capture_stream
                parser_set.print_help()
            except SystemExit: pass
            finally: sys.stdout = original_stdout
            return capture_stream.getvalue()

        # --- Parse arguments ---
        try:
            parsed_args = parser.parse_args(args)
        except argparse.ArgumentError as e:
            raise e
        except SystemExit:
             return "" # Help was printed

        # --- Execute subcommand logic ---
        try:
            if parsed_args.subcommand == "get":
                value = self.config.get(parsed_args.section, parsed_args.key, parsed_args.default)
                if isinstance(value, (dict, list)):
                    return json.dumps(value, indent=2)
                return str(value)

            elif parsed_args.subcommand == "set":
                section = parsed_args.section
                key = parsed_args.key
                value = parsed_args.value

                # Validate language setting
                if section == 'WORKFLOWS' and key == 'default_workflow_type':
                    if value not in ALLOWED_WORKFLOW_LANGUAGES:
                        allowed_str = ", ".join(ALLOWED_WORKFLOW_LANGUAGES)
                        parser_set.error(f"Invalid value '{value}' for WORKFLOWS.default_workflow_type. Allowed languages: {allowed_str}")
                # Validate executor settings
                elif section == 'WORKFLOWS' and key.endswith('_default_executor'):
                    lang = key.split('_default_executor')[0]
                    if lang in ALLOWED_EXECUTORS:
                        allowed_execs = ALLOWED_EXECUTORS[lang]
                        if value not in allowed_execs:
                             parser_set.error(f"Invalid executor '{value}' for key WORKFLOWS.{key}. Allowed for {lang.upper()}: {', '.join(allowed_execs)}")
                    else:
                        # This case shouldn't happen if key format is correct, but handle defensively
                        logger.warning(f"Attempting to set executor for unknown language inferred from key '{key}'. Skipping validation.")

                # Set the value
                self.config.set(section, key, value)
                return f"Config [{section}].{key} set to '{value}' and saved."

            elif parsed_args.subcommand == "save":
                self.config.save_config()
                config_path = self.config.config_path
                return f"Configuration saved successfully to {config_path}."

            elif parsed_args.subcommand == "show":
                section_name = parsed_args.section
                if section_name is None:
                    config_data = self.config.get_all_config()
                    if not config_data: return "Configuration is empty or could not be read."
                    return f"Current Configuration:\n{json.dumps(config_data, indent=2)}"
                elif section_name.lower() == 'ssh':
                    config_data = self.config.get_ssh_config()
                    if not config_data: return "SSH (HPC) configuration section not found or empty."
                    return f"SSH Configuration (Section: HPC):\n{json.dumps(config_data, indent=2)}"
                else:
                    config_data = self.config.get_section(section_name)
                    if config_data is None:
                        available_sections = self.config.get_available_sections()
                        return f"Configuration section '[{section_name}]' not found. Available sections: {', '.join(available_sections)}"
                    return f"Configuration Section [{section_name}]:\n{json.dumps(config_data, indent=2)}"

        except Exception as e:
            logger.error(f"Error during /config {parsed_args.subcommand}: {e}", exc_info=True)
            raise RuntimeError(f"Error executing config command: {e}") from e

    # --- File System Handlers ---
    def _handle_fs_head(self, args: List[str]) -> str:
        """Handles the /fs_head command."""
        parser = self._create_parser("fs_head", self._command_map['fs_head']['help'])
        parser.add_argument("file_path", help="Path to the local file")
        parser.add_argument("num_lines", type=int, nargs='?', default=10, help="Number of lines to show (default: 10)")
        parsed_args = parser.parse_args(args)

        if parsed_args.num_lines <= 0:
            parser.error("Number of lines must be positive.")

        try:
            lines = list(self.file_inspector.head(parsed_args.file_path, parsed_args.num_lines))
            abs_path = os.path.abspath(parsed_args.file_path)
            if not lines:
                if not self.local_fs.exists(parsed_args.file_path):
                     raise FileNotFoundError(f"File not found at '{abs_path}'")
                return f"File is empty: {abs_path}"

            dirname = os.path.dirname(abs_path)
            basename = os.path.basename(abs_path)
            colored_basename = colorize_filename(basename, is_dir=False)
            header_text = Text.assemble(f"First {len(lines)} lines of '", dirname + os.path.sep, colored_basename, "':\n---")

            global string_io, capture_console
            string_io.seek(0)
            string_io.truncate(0)
            capture_console.print(header_text)
            for line in lines:
                 capture_console.print(line, highlight=False)
            capture_console.print("---")
            return string_io.getvalue().strip()

        except FileNotFoundError:
             abs_path = os.path.abspath(parsed_args.file_path)
             raise FileNotFoundError(f"File not found at '{abs_path}'")
        except Exception as e:
            logger.error(f"Error reading head of file {parsed_args.file_path}", exc_info=True)
            raise e

    # --- HPC Bridge Handlers ---
    def _get_ssh_manager(self, connect_now: bool = False) -> SSHManager:
        """Helper to get an initialized SSHManager."""
        ssh_config = self.config.get_ssh_config()
        if not ssh_config or not ssh_config.get('host'):
            raise ConnectionError("HPC host configuration missing. Use '/config set HPC host <hostname>' and potentially other HPC settings.")
        try:
            ssh_manager = SSHManager(ssh_config=ssh_config)
            if connect_now:
                logger.debug("Attempting immediate connection in _get_ssh_manager...")
                if not ssh_manager.connect():
                    raise ConnectionError(f"Failed to establish temporary SSH connection to {ssh_manager.host}.")
                logger.debug("Immediate connection successful.")
            return ssh_manager
        except ValueError as e:
             raise ConnectionError(f"Failed to initialize SSH connection due to config error: {e}") from e
        except ConnectionError as e:
             raise e
        except Exception as e:
             raise ConnectionError(f"Failed to initialize SSH connection: {e}") from e

    def _get_slurm_manager(self) -> SlurmManager:
        """Helper to get an initialized SlurmManager with an active connection."""
        logger.debug("Creating temporary SSH connection for Slurm manager.")
        ssh_manager = self._get_ssh_manager(connect_now=True)
        try:
            return SlurmManager(ssh_manager=ssh_manager)
        except Exception as e:
             if ssh_manager: ssh_manager.disconnect()
             raise ConnectionError(f"Failed to initialize Slurm manager: {e}") from e

    # --- HPC Connection Handlers ---
    def _handle_hpc_connect(self, args: List[str]) -> str:
        """Establishes and stores a persistent SSH connection."""
        parser = self._create_parser("hpc_connect", self._command_map['hpc_connect']['help'])
        parsed_args = parser.parse_args(args)

        if self.active_ssh_manager and self.active_ssh_manager.is_connected:
            try:
                test_cmd = "echo 'Dayhoff connection active'"
                logger.debug(f"Testing existing SSH connection with: {test_cmd}")
                self.active_ssh_manager.execute_command(test_cmd, timeout=5)
                host = self.active_ssh_manager.host
                logger.info(f"Persistent SSH connection to {host} is already active.")
                if not self.remote_cwd:
                    try:
                        self.remote_cwd = self.active_ssh_manager.execute_command("pwd", timeout=10).strip()
                        logger.info(f"Refreshed remote CWD: {self.remote_cwd}")
                    except Exception as pwd_err:
                        logger.warning(f"Could not refresh remote CWD on existing connection: {pwd_err}")
                        self.remote_cwd = "~"
                return f"Already connected to HPC host: {host} (cwd: {self.remote_cwd}). Use /hpc_disconnect first if you want to reconnect."
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

        logger.info("Attempting to establish persistent SSH connection...")
        ssh_manager = None
        try:
            ssh_manager = self._get_ssh_manager(connect_now=False)
            if not ssh_manager.connect():
                self.active_ssh_manager = None
                self.remote_cwd = None
                raise ConnectionError(f"Failed to establish initial SSH connection to {ssh_manager.host}. Check logs and config.")

            test_cmd = "hostname"
            logger.info(f"SSH connection established, verifying with command: {test_cmd}")
            hostname = ssh_manager.execute_command(test_cmd, timeout=15).strip()
            if not hostname:
                 logger.warning("SSH connection verified but 'hostname' command returned empty.")

            logger.info(f"SSH connection verified. Remote hostname: {hostname}")

            try:
                initial_cwd = ssh_manager.execute_command("pwd", timeout=10).strip()
                if not initial_cwd:
                    logger.warning("Could not determine initial remote working directory, defaulting to '~'.")
                    initial_cwd = "~"
            except (ConnectionError, TimeoutError, RuntimeError) as pwd_err:
                 logger.warning(f"Could not determine initial remote working directory ({pwd_err}), defaulting to '~'.")
                 initial_cwd = "~"

            self.active_ssh_manager = ssh_manager
            self.remote_cwd = initial_cwd
            return f"Successfully connected to HPC host: {hostname} (user: {ssh_manager.username}, cwd: {self.remote_cwd})."

        except (ConnectionError, TimeoutError, RuntimeError, ValueError) as e:
            logger.error(f"Failed to establish persistent SSH connection: {type(e).__name__}: {e}", exc_info=False)
            if ssh_manager: ssh_manager.disconnect()
            self.active_ssh_manager = None
            self.remote_cwd = None
            raise ConnectionError(f"Failed to establish SSH connection: {e}") from e
        except Exception as e:
            logger.error(f"Unexpected error during persistent SSH connection: {e}", exc_info=True)
            if ssh_manager: ssh_manager.disconnect()
            self.active_ssh_manager = None
            self.remote_cwd = None
            raise ConnectionError(f"Unexpected error establishing SSH connection: {e}") from e

    def _handle_hpc_disconnect(self, args: List[str]) -> str:
        """Closes the persistent SSH connection."""
        parser = self._create_parser("hpc_disconnect", self._command_map['hpc_disconnect']['help'])
        parsed_args = parser.parse_args(args)

        if not self.active_ssh_manager:
            return "No active HPC connection to disconnect."

        logger.info("Disconnecting persistent SSH connection...")
        try:
            host = getattr(self.active_ssh_manager, 'host', 'unknown')
            self.active_ssh_manager.disconnect()
            self.active_ssh_manager = None
            self.remote_cwd = None
            return f"Successfully disconnected from HPC host: {host}."
        except Exception as e:
            logger.error(f"Error during SSH disconnection: {e}", exc_info=True)
            self.active_ssh_manager = None
            self.remote_cwd = None
            raise RuntimeError(f"Error closing SSH connection: {e}") from e

    def _handle_hpc_run(self, args: List[str]) -> str:
        """Executes a command using the active persistent SSH connection, respecting remote_cwd."""
        parser = self._create_parser("hpc_run", self._command_map['hpc_run']['help'])
        if not args:
             parser.error("the following arguments are required: command_string")

        if not self.active_ssh_manager or not self.active_ssh_manager.is_connected:
            raise ConnectionError("Not connected to HPC. Use /hpc_connect first.")
        if not self.remote_cwd:
             raise ConnectionError("Remote working directory unknown. Please use /hpc_connect again.")

        command_string = " ".join(shlex.quote(arg) for arg in args)
        full_command = f"cd {shlex.quote(self.remote_cwd)} && {command_string}"

        try:
            logger.info(f"Executing command via active SSH connection: {full_command}")
            output = self.active_ssh_manager.execute_command(full_command)
            return output
        except ConnectionError as e:
            logger.error(f"Connection error during /hpc_run: {e}", exc_info=False)
            try: self.active_ssh_manager.disconnect()
            except Exception: pass
            self.active_ssh_manager = None
            self.remote_cwd = None
            raise ConnectionError(f"Connection error during command execution: {e}. Connection closed.") from e
        except (TimeoutError, RuntimeError) as e:
             logger.error(f"Error during /hpc_run: {type(e).__name__}: {e}", exc_info=False)
             if "No such file or directory" in str(e):
                 logger.warning(f"Remote CWD '{self.remote_cwd}' might be invalid. Resetting to '~'.")
                 self.remote_cwd = "~"
                 raise RuntimeError(f"Remote directory '{self.remote_cwd}' likely invalid. Resetting to '~'. Please verify and use /cd if needed. Original error: {e}") from e
             raise e
        except Exception as e:
            logger.error(f"Unexpected error executing command via active SSH connection: {e}", exc_info=True)
            raise RuntimeError(f"Unexpected error executing remote command: {e}") from e

    def _handle_hpc_slurm_run(self, args: List[str]) -> str:
        """Executes a command within a Slurm allocation (srun) using the active SSH connection."""
        parser = self._create_parser("hpc_slurm_run", self._command_map['hpc_slurm_run']['help'])
        if not args:
             parser.error("the following arguments are required: command_string")

        if not self.active_ssh_manager or not self.active_ssh_manager.is_connected:
            raise ConnectionError("Not connected to HPC. Use /hpc_connect first.")
        if not self.remote_cwd:
             raise ConnectionError("Remote working directory unknown. Please use /hpc_connect again.")

        user_command_string = " ".join(shlex.quote(arg) for arg in args)
        srun_command = f"srun --pty {user_command_string}"
        full_command = f"cd {shlex.quote(self.remote_cwd)} && {srun_command}"

        try:
            logger.info(f"Executing command via srun using active SSH connection: {full_command}")
            output = self.active_ssh_manager.execute_command(full_command, timeout=300)
            return output
        except ConnectionError as e:
            logger.error(f"Connection error during /hpc_slurm_run: {e}", exc_info=False)
            try: self.active_ssh_manager.disconnect()
            except Exception: pass
            self.active_ssh_manager = None
            self.remote_cwd = None
            raise ConnectionError(f"Connection error during srun execution: {e}. Connection closed.") from e
        except TimeoutError as e:
             logger.error(f"Timeout error during /hpc_slurm_run (timeout=300s): {e}", exc_info=False)
             raise TimeoutError(f"Command execution via srun timed out after 300 seconds: {e}") from e
        except RuntimeError as e:
             logger.error(f"Runtime error during /hpc_slurm_run: {e}", exc_info=False)
             if "srun: error:" in str(e):
                 raise RuntimeError(f"Slurm execution failed: {e}") from e
             elif "No such file or directory" in str(e):
                 logger.warning(f"Remote CWD '{self.remote_cwd}' might be invalid. Resetting to '~'.")
                 self.remote_cwd = "~"
                 raise RuntimeError(f"Remote directory '{self.remote_cwd}' likely invalid. Resetting to '~'. Please verify and use /cd if needed. Original error: {e}") from e
             raise e
        except Exception as e:
            logger.error(f"Unexpected error executing command via srun: {e}", exc_info=True)
            raise RuntimeError(f"Unexpected error executing remote srun command: {e}") from e

    def _handle_ls(self, args: List[str]) -> str:
        """Handles the /ls command by fetching file list/types and coloring locally."""
        parser = self._create_parser("ls", self._command_map['ls']['help'])
        parsed_args, unknown_args = parser.parse_known_args(args)
        if unknown_args:
             logger.warning(f"Ignoring unsupported arguments/options for /ls: {unknown_args}")

        if not self.active_ssh_manager or not self.active_ssh_manager.is_connected:
            raise ConnectionError("Not connected to HPC. Use /hpc_connect first.")
        if not self.remote_cwd:
             raise ConnectionError("Remote working directory unknown. Please use /hpc_connect again.")

        find_cmd = f"find . -mindepth 1 -maxdepth 1 -printf '%Y %P\\n'"
        full_command = f"cd {shlex.quote(self.remote_cwd)} && {find_cmd}"

        try:
            logger.info(f"Fetching file list for /ls with command: {full_command}")
            output = self.active_ssh_manager.execute_command(full_command, timeout=30)

            items = []
            if output:
                lines = output.strip().split('\n')
                for line in lines:
                    if not line: continue
                    try:
                        type_char, name = line.split(' ', 1)
                        is_dir = (type_char == 'd')
                        items.append(colorize_filename(name, is_dir=is_dir))
                    except ValueError:
                        logger.warning(f"Could not parse line from find output: '{line}'")
                        items.append(Text(line.strip(), style="red"))

            if not items:
                return f"(Directory {self.remote_cwd} is empty)"

            items.sort(key=lambda text: text.plain)
            columns = Columns(items, expand=True, equal=True)

            global string_io, capture_console
            string_io.seek(0)
            string_io.truncate(0)
            capture_console.print(columns)
            return string_io.getvalue().strip()

        except (ConnectionError, TimeoutError, RuntimeError) as e:
            logger.error(f"Error during /ls execution: {type(e).__name__}: {e}", exc_info=False)
            raise e
        except Exception as e:
            logger.error(f"Unexpected error during /ls execution: {e}", exc_info=True)
            raise RuntimeError(f"Unexpected error listing remote directory: {e}") from e

    def _handle_cd(self, args: List[str]) -> str:
        """Handles the /cd command by verifying the directory and updating remote_cwd."""
        parser = self._create_parser("cd", self._command_map['cd']['help'])
        parser.add_argument("directory", help="The target remote directory")
        parsed_args = parser.parse_args(args)

        if not self.active_ssh_manager or not self.active_ssh_manager.is_connected:
            raise ConnectionError("Not connected to HPC. Use /hpc_connect first.")
        if not self.remote_cwd:
             raise ConnectionError("Remote working directory unknown. Please use /hpc_connect again.")

        target_dir = parsed_args.directory
        current_dir = self.remote_cwd
        test_command = f"cd {shlex.quote(current_dir)} && cd {shlex.quote(target_dir)} && pwd"
        logger.info(f"Verifying remote directory change with command: {test_command}")

        try:
            new_dir_output = self.active_ssh_manager.execute_command(test_command, timeout=30)
            new_dir = new_dir_output.strip()

            if not new_dir or not new_dir.startswith("/"):
                logger.error(f"Failed to change directory to '{target_dir}'. 'pwd' command returned unexpected output: {new_dir_output}")
                raise RuntimeError(f"Failed to change directory to '{target_dir}'. Could not verify new path.")

            self.remote_cwd = new_dir
            logger.info(f"Successfully changed remote working directory to: {self.remote_cwd}")
            return f"Remote working directory changed to: {self.remote_cwd}"

        except (ConnectionError, TimeoutError, RuntimeError) as e:
            logger.error(f"Failed to change remote directory to '{target_dir}': {type(e).__name__}: {e}", exc_info=False)
            raise RuntimeError(f"Failed to change remote directory to '{target_dir}': {e}") from e
        except Exception as e:
            logger.error(f"Unexpected error changing remote directory to '{target_dir}': {e}", exc_info=True)
            raise RuntimeError(f"Unexpected error changing remote directory: {e}") from e

    def _handle_hpc_slurm_submit(self, args: List[str]) -> str:
        parser = self._create_parser("hpc_slurm_submit", self._command_map['hpc_slurm_submit']['help'])
        parser.add_argument("script_path", help="Path to the local Slurm script file")
        parser.add_argument("options_json", nargs='?', default='{}', help="Optional Slurm options as JSON string (e.g., '{\"--nodes\": 1, \"--time\": \"01:00:00\"}')")
        parsed_args = parser.parse_args(args)

        slurm_manager = None
        ssh_manager = None
        try:
            slurm_manager = self._get_slurm_manager()
            ssh_manager = slurm_manager.ssh_manager

            options = json.loads(parsed_args.options_json)
            if not isinstance(options, dict):
                parser.error("Options JSON must decode to a dictionary.")

            script_path = os.path.abspath(parsed_args.script_path)
            if not os.path.isfile(script_path):
                 raise FileNotFoundError(f"Script file not found at '{script_path}'")

            with open(script_path, 'r') as f:
                script_content = f.read()

            logger.info(f"Submitting Slurm job from script: {script_path} with options: {options}")
            job_id = slurm_manager.submit_job(script_content, options)
            return f"Slurm job submitted with ID: {job_id}"
        except (ConnectionError, FileNotFoundError, ValueError, RuntimeError) as e:
            raise e
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON provided for options: {e}") from e
        except Exception as e:
            logger.error("Error submitting Slurm job", exc_info=True)
            raise RuntimeError(f"Error submitting Slurm job: {e}") from e
        finally:
            if ssh_manager:
                 try:
                     ssh_manager.disconnect()
                     logger.debug("Closed temporary SSH connection for Slurm submit.")
                 except Exception as close_err:
                     logger.warning(f"Error closing temporary SSH connection after Slurm submit: {close_err}")

    def _handle_hpc_slurm_status(self, args: List[str]) -> str:
        """Handles the /hpc_slurm_status command with multiple query options."""
        parser = self._create_parser("hpc_slurm_status", self._command_map['hpc_slurm_status']['help'])
        scope_group = parser.add_mutually_exclusive_group()
        scope_group.add_argument("--job-id", help="Show status for a specific job ID.")
        scope_group.add_argument("--user", action='store_true', help="Show status for the current user's jobs (default if no scope specified).")
        scope_group.add_argument("--all", action='store_true', help="Show status for all jobs in the queue.")
        parser.add_argument("--waiting-summary", action='store_true', help="Include a summary of waiting times for pending jobs.")
        parsed_args = parser.parse_args(args)

        job_id = parsed_args.job_id
        query_user = parsed_args.user
        query_all = parsed_args.all
        if not job_id and not query_user and not query_all:
            query_user = True
            logger.info("No scope specified for /hpc_slurm_status, defaulting to --user.")

        slurm_manager = None
        ssh_manager = None
        try:
            slurm_manager = self._get_slurm_manager()
            ssh_manager = slurm_manager.ssh_manager
            logger.info(f"Getting Slurm status info (job_id={job_id}, user={query_user}, all={query_all}, summary={parsed_args.waiting_summary})")

            status_info = slurm_manager.get_queue_info(
                job_id=job_id,
                query_user=query_user,
                query_all=query_all,
                waiting_summary=parsed_args.waiting_summary
            )

            output_lines = []
            jobs = status_info.get("jobs", [])
            summary = status_info.get("waiting_summary")

            if not jobs and not summary:
                output_lines.append("No Slurm jobs found matching the criteria.")
            elif not jobs and summary:
                 output_lines.append("No Slurm jobs found matching the criteria.")
            else:
                field_map = {
                    "job_id": "JobID", "partition": "Partition", "name": "Name",
                    "user": "User", "state_compact": "State", "time_used": "Time",
                    "nodes": "Nodes", "reason": "Reason", "submit_time_str": "SubmitTime"
                }
                if jobs: available_fields = [f for f in field_map if f in jobs[0]]
                else: available_fields = list(field_map.keys())

                display_fields = [f for f in field_map if f in available_fields]
                display_headers = [field_map[f] for f in display_fields]

                col_widths = {h: len(h) for h in display_headers}
                for job in jobs:
                    for field in display_fields:
                        col_widths[field_map[field]] = max(col_widths[field_map[field]], len(str(job.get(field, ''))))

                header_line = "  ".join(f"{h:<{col_widths[h]}}" for h in display_headers)
                output_lines.append(header_line)
                output_lines.append("-" * len(header_line))

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
            raise e
        except Exception as e:
            logger.error(f"Error getting Slurm job status", exc_info=True)
            raise RuntimeError(f"Error getting Slurm job status: {e}") from e
        finally:
             if ssh_manager:
                 try:
                     ssh_manager.disconnect()
                     logger.debug("Closed temporary SSH connection for Slurm status.")
                 except Exception as close_err:
                     logger.warning(f"Error closing temporary SSH connection after Slurm status: {close_err}")

    def _handle_hpc_cred_get(self, args: List[str]) -> str:
        parser = self._create_parser("hpc_cred_get", self._command_map['hpc_cred_get']['help'])
        parser.add_argument("username", help="HPC username")
        parsed_args = parser.parse_args(args)

        try:
            cred_manager = CredentialManager()
            password = cred_manager.get_password(username=parsed_args.username)
            system_name = getattr(cred_manager, 'system_name', 'dayhoff_hpc')

            if password:
                 logger.info(f"Password found for user '{parsed_args.username}' (system: {system_name}) in keyring.")
                 return f"Password found for user '{parsed_args.username}' (system: {system_name}) in system keyring."
            else:
                 logger.info(f"No stored password found for user '{parsed_args.username}' (system: {system_name}) in keyring.")
                 return f"No stored password found for user '{parsed_args.username}' (system: {system_name}) in system keyring."
        except Exception as e:
            logger.error(f"Error retrieving credentials for {parsed_args.username}", exc_info=True)
            raise RuntimeError(f"Error retrieving credentials: {e}") from e

    # --- Workflow & Environment Handlers ---

    def _handle_wf_gen(self, args: List[str]) -> str:
        """Handles the /wf_gen command using the configured language."""
        parser = self._create_parser("wf_gen", self._command_map['wf_gen']['help'])
        parser.add_argument("steps_json", help="Workflow steps definition as JSON string (list or dict)")
        parsed_args = parser.parse_args(args)

        try:
            steps = json.loads(parsed_args.steps_json)
            if not isinstance(steps, (list, dict)):
                 parser.error("Steps JSON must decode to a list or dictionary.")

            language = self.config.get_workflow_language()
            # Note: Executor is not used during generation, but logged for context
            executor = self.config.get_workflow_executor(language)
            logger.info(f"Generating workflow using configured language: {language} (default executor: {executor})")

            generator = WorkflowGenerator()
            workflow_output = generator.generate_workflow(steps, language)

            if workflow_output is None:
                return f"Workflow generation for language '{language}' is not yet implemented or returned no output."

            return f"Generated {language.upper()} Workflow:\n---\n{workflow_output}\n---"

        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON provided for steps: {e}") from e
        except ValueError as e:
             raise e
        except Exception as e:
            logger.error("Error generating workflow", exc_info=True)
            raise RuntimeError(f"Error generating workflow: {e}") from e

    def _handle_language(self, args: List[str]) -> str:
        """Handles the /language command to view or set the workflow language."""
        # Help text updated via _build_command_map
        parser = self._create_parser(
            "language",
            self._command_map['language']['help'],
            add_help=True
        )
        parser.add_argument("language", nargs='?', help="The workflow language to set (optional).")

        try:
            parsed_args = parser.parse_args(args)
        except argparse.ArgumentError as e:
            raise e
        except SystemExit:
             return "" # Help was printed

        if parsed_args.language is None:
            current_language = self.config.get_workflow_language()
            # Also show the configured executor for this language
            current_executor = self.config.get_workflow_executor(current_language) or "N/A"
            return f"Current default workflow language: {current_language}\nDefault executor for {current_language.upper()}: {current_executor}"
        else:
            requested_language = parsed_args.language.lower()
            # Use renamed constant
            if requested_language in ALLOWED_WORKFLOW_LANGUAGES:
                try:
                    self.config.set('WORKFLOWS', 'default_workflow_type', requested_language)
                    logger.info(f"Workflow language set to: {requested_language}")
                    # Also show the executor that will now be used by default
                    new_executor = self.config.get_workflow_executor(requested_language) or "N/A"
                    return f"Workflow language set to: {requested_language}\n(Default executor for {requested_language.upper()} is now: {new_executor})"
                except Exception as e:
                    logger.error(f"Failed to set workflow language to {requested_language}: {e}", exc_info=True)
                    raise RuntimeError(f"Failed to save workflow language setting: {e}") from e
            else:
                allowed_str = ", ".join(ALLOWED_WORKFLOW_LANGUAGES)
                parser.error(f"Invalid language '{parsed_args.language}'. Allowed languages are: {allowed_str}")

