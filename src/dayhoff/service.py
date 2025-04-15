import json
import shlex
from typing import Any, List, Dict, Optional

# --- Core Components ---
from .config import DayhoffConfig
from .git_tracking import GitTracker, Event

# --- File System ---
from .fs import BioDataExplorer
# Assuming BaseFileSystem and implementations might be needed later
# from .fs.local import LocalFileSystem
# from .fs.stats import FileStats
# from .fs.streaming import FileStreamer

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
from .workflows import WorkflowGenerator
from .workflows.environment import EnvironmentTracker
# from .modules import ModuleManager # If needed for a /module command

# --- Helper for argument parsing ---
import argparse

class DayhoffService:
    """Shared backend service for both CLI and notebook interfaces"""

    def __init__(self):
        # Instantiate core/persistent services
        self.tracker = GitTracker()
        self.config = DayhoffConfig()
        # Lazily instantiate others as needed within command handlers
        # or instantiate here if frequently used and lightweight.
        self._command_map = self._build_command_map()


    def _build_command_map(self) -> Dict[str, Dict[str, Any]]:
        """Builds a map of commands, their handlers, and help text."""
        # Structure: command_name: {'handler': self._handle_command_xyz, 'help': 'Help text...'}
        return {
            "help": {"handler": self._handle_help, "help": "Show help for commands. Usage: /help [command_name]"},
            # --- Config ---
            "config_get": {"handler": self._handle_config_get, "help": "Get a config value. Usage: /config_get <section> <key> [default_value]"},
            "config_ssh": {"handler": self._handle_config_ssh, "help": "Get SSH configuration. Usage: /config_ssh"},
            "config_save": {"handler": self._handle_config_save, "help": "Save current configuration. Usage: /config_save"},
            # --- File System ---
            "fs_find_seq": {"handler": self._handle_fs_find_seq, "help": "Find sequence files (iterator). Usage: /fs_find_seq"},
            # "fs_stats": {"handler": self._handle_fs_stats, "help": "Get file statistics. Usage: /fs_stats <filepath>"}, # Needs FileStats class
            # "fs_cmd": {"handler": self._handle_fs_cmd, "help": "Run a local shell command. Usage: /fs_cmd <command_string>"}, # Needs LocalFileSystem class
            # --- Git Tracking ---
            "git_record": {"handler": self._handle_git_record, "help": "Record a custom event. Usage: /git_record <event_type> <metadata_json> [files_json]"},
            # "git_log": {"handler": self._handle_git_log, "help": "Show git event log (placeholder). Usage: /git_log"}, # Needs implementation in GitTracker
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

    def execute_command(self, command: str, args: List[str]) -> Any:
        """Execute a command and track it in git"""

        if command in self._command_map:
            command_info = self._command_map[command]
            handler = command_info["handler"]
            try:
                # Record the event before execution
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
                return result
            except argparse.ArgumentError as e:
                 return f"Argument Error for /{command}: {e}\nUsage: {command_info.get('help', 'No help available.')}"
            except Exception as e:
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
                return f"Error executing command /{command}: {type(e).__name__}: {e}"
        else:
            return f"Unknown command: /{command}. Type /help for available commands."

    # --- Help Handler ---
    def _handle_help(self, args: List[str]) -> str:
        if not args:
            # General help
            help_lines = ["Available commands:"]
            for cmd, info in sorted(self._command_map.items()):
                help_lines.append(f"  /{cmd:<20} - {info['help'].split('.')[0]}") # Show only first sentence
            help_lines.append("\nType /help <command_name> for more details.")
            return "\n".join(help_lines)
        else:
            # Specific command help
            cmd_name = args[0]
            if cmd_name.startswith('/'): # Allow /help /command_name
                cmd_name = cmd_name[1:]
            if cmd_name in self._command_map:
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
            raise argparse.ArgumentError(None, message)
        parser.error = error
        return parser

    # --- Config Handlers ---
    def _handle_config_get(self, args: List[str]) -> Any:
        parser = self._create_parser("config_get", "Get a config value.")
        parser.add_argument("section", help="Configuration section name")
        parser.add_argument("key", help="Configuration key name")
        parser.add_argument("default", nargs='?', default=None, help="Optional default value")
        parsed_args = parser.parse_args(args)

        return self.config.get(parsed_args.section, parsed_args.key, parsed_args.default)

    def _handle_config_ssh(self, args: List[str]) -> Dict[str, str]:
        if args:
            raise argparse.ArgumentError(None, "Command takes no arguments.")
        return self.config.get_ssh_config()

    def _handle_config_save(self, args: List[str]) -> str:
        if args:
            raise argparse.ArgumentError(None, "Command takes no arguments.")
        try:
            self.config.save_config()
            return "Configuration saved successfully."
        except Exception as e:
            return f"Error saving configuration: {e}"

    # --- File System Handlers ---
    def _handle_fs_find_seq(self, args: List[str]) -> str:
        # Note: Iterators are tricky in a simple REPL.
        # We'll collect and return the list for now.
        if args:
            raise argparse.ArgumentError(None, "Command takes no arguments.")
        try:
            # Assuming BioDataExplorer can be instantiated without args here
            explorer = BioDataExplorer()
            files = list(explorer.find_sequence_files())
            if not files:
                return "No sequence files found."
            return "Found sequence files:\n" + "\n".join(files)
        except Exception as e:
            return f"Error finding sequence files: {e}"

    # --- Git Tracking Handlers ---
    def _handle_git_record(self, args: List[str]) -> str:
        parser = self._create_parser("git_record", "Record a custom event.")
        parser.add_argument("event_type", help="Type of the event (e.g., 'manual_step')")
        parser.add_argument("metadata_json", help="Metadata as a JSON string (e.g., '{\"key\": \"value\"}')")
        parser.add_argument("files_json", nargs='?', default='{}', help="Optional dictionary of files to track as JSON string (e.g., '{\"input.txt\": \"path/to/input.txt\"}')")
        parsed_args = parser.parse_args(args)

        try:
            metadata = json.loads(parsed_args.metadata_json)
            files_dict = json.loads(parsed_args.files_json) if parsed_args.files_json else None

            self.tracker.record_event(
                event_type=parsed_args.event_type,
                metadata=metadata,
                files=files_dict
            )
            return f"Event '{parsed_args.event_type}' recorded."
        except json.JSONDecodeError as e:
            return f"Invalid JSON provided: {e}"
        except Exception as e:
            return f"Error recording event: {e}"

    # --- HPC Bridge Handlers ---
    def _handle_hpc_sync_up(self, args: List[str]) -> str:
        parser = self._create_parser("hpc_sync_up", "Upload file(s) to HPC.")
        parser.add_argument("local_path", help="Local file or glob pattern (e.g., 'data/*.fastq')")
        parser.add_argument("remote_dir", help="Remote destination directory")
        parsed_args = parser.parse_args(args)

        try:
            # Need SSH config to instantiate FileSynchronizer
            ssh_config = self.config.get_ssh_config()
            if not ssh_config:
                return "Error: SSH configuration not found. Use /config_set or edit config file."

            # Assuming FileSynchronizer takes ssh_config or similar
            # This might need adjustment based on FileSynchronizer's __init__
            synchronizer = FileSynchronizer(ssh_config=ssh_config) # Placeholder

            # FileSynchronizer.upload_files expects List[str], handle potential glob
            import glob
            local_paths = glob.glob(parsed_args.local_path)
            if not local_paths:
                return f"Error: No local files found matching '{parsed_args.local_path}'"

            success = synchronizer.upload_files(local_paths, parsed_args.remote_dir)
            return "File upload successful." if success else "File upload failed."
        except Exception as e:
            return f"Error during upload: {e}"

    def _handle_hpc_sync_down(self, args: List[str]) -> str:
        parser = self._create_parser("hpc_sync_down", "Download file(s) from HPC.")
        parser.add_argument("remote_path", help="Remote file or glob pattern")
        parser.add_argument("local_dir", help="Local destination directory")
        parsed_args = parser.parse_args(args)

        try:
            ssh_config = self.config.get_ssh_config()
            if not ssh_config: return "Error: SSH configuration not found."
            synchronizer = FileSynchronizer(ssh_config=ssh_config) # Placeholder

            # download_files expects List[str], but remote globbing might need SSH execution first
            # For simplicity, assume single file or user handles globbing on remote manually for now
            # Or adjust FileSynchronizer to handle remote globs
            remote_paths = [parsed_args.remote_path] # Simplification

            success = synchronizer.download_files(remote_paths, parsed_args.local_dir)
            return "File download successful." if success else "File download failed."
        except Exception as e:
            return f"Error during download: {e}"

    def _handle_hpc_ssh_cmd(self, args: List[str]) -> str:
        if not args:
             raise argparse.ArgumentError(None, "Missing command string.")
        command_string = " ".join(args) # Rejoin args into the command

        try:
            ssh_config = self.config.get_ssh_config()
            if not ssh_config: return "Error: SSH configuration not found."
            ssh_manager = SSHManager(ssh_config=ssh_config) # Placeholder
            output = ssh_manager.execute_command(command_string)
            return f"SSH command output:\n{output}"
        except Exception as e:
            return f"Error executing SSH command: {e}"

    def _handle_hpc_slurm_submit(self, args: List[str]) -> str:
        parser = self._create_parser("hpc_slurm_submit", "Submit a Slurm job.")
        parser.add_argument("script_path", help="Path to the Slurm script file")
        parser.add_argument("options_json", nargs='?', default='{}', help="Optional Slurm options as JSON string (e.g., '{\"--nodes\": 1, \"--time\": \"01:00:00\"}')")
        parsed_args = parser.parse_args(args)

        try:
            ssh_config = self.config.get_ssh_config()
            if not ssh_config: return "Error: SSH configuration not found."
            slurm_manager = SlurmManager(ssh_config=ssh_config) # Placeholder

            options = json.loads(parsed_args.options_json)

            # Read the script content - assuming local path for now
            with open(parsed_args.script_path, 'r') as f:
                script_content = f.read()

            job_id = slurm_manager.submit_job(script_content, options)
            return f"Slurm job submitted with ID: {job_id}"
        except FileNotFoundError:
            return f"Error: Script file not found at '{parsed_args.script_path}'"
        except json.JSONDecodeError as e:
            return f"Invalid JSON provided for options: {e}"
        except Exception as e:
            return f"Error submitting Slurm job: {e}"

    def _handle_hpc_slurm_status(self, args: List[str]) -> str:
        parser = self._create_parser("hpc_slurm_status", "Get Slurm job status.")
        parser.add_argument("job_id", help="Slurm job ID")
        parsed_args = parser.parse_args(args)

        try:
            ssh_config = self.config.get_ssh_config()
            if not ssh_config: return "Error: SSH configuration not found."
            slurm_manager = SlurmManager(ssh_config=ssh_config) # Placeholder
            status = slurm_manager.get_job_status(parsed_args.job_id)
            # Format the status dict for printing
            return json.dumps(status, indent=2)
        except Exception as e:
            return f"Error getting Slurm job status: {e}"

    def _handle_hpc_cred_get(self, args: List[str]) -> str:
        parser = self._create_parser("hpc_cred_get", "Get HPC password for user.")
        parser.add_argument("username", help="HPC username")
        parsed_args = parser.parse_args(args)

        try:
            # Assuming CredentialManager can be instantiated directly
            cred_manager = CredentialManager()
            password = cred_manager.get_password(parsed_args.username)
            return f"Password found for user '{parsed_args.username}'." if password else f"No stored password found for user '{parsed_args.username}'."
        except Exception as e:
            return f"Error retrieving credentials: {e}"

    # --- AI/LLM Handlers ---
    def _handle_ai_suggest(self, args: List[str]) -> str:
        parser = self._create_parser("ai_suggest", "Suggest analysis.")
        parser.add_argument("data_type", help="Type of data (e.g., 'fastq', 'vcf')")
        parser.add_argument("metadata_json", help="Metadata as JSON string")
        parsed_args = parser.parse_args(args)

        try:
            metadata = json.loads(parsed_args.metadata_json)
            # Assuming AnalysisAdvisor can be instantiated directly
            advisor = AnalysisAdvisor()
            suggestion = advisor.suggest_analysis(parsed_args.data_type, metadata)
            return f"Analysis Suggestion:\n{suggestion}"
        except json.JSONDecodeError as e:
            return f"Invalid JSON provided for metadata: {e}"
        except Exception as e:
            return f"Error getting analysis suggestion: {e}"

    def _handle_llm_budget(self, args: List[str]) -> str:
        if args:
            raise argparse.ArgumentError(None, "Command takes no arguments.")
        try:
            # Assuming TokenBudget can be instantiated directly
            budget = TokenBudget()
            remaining = budget.remaining()
            return f"Remaining LLM token budget: {remaining}"
        except Exception as e:
            return f"Error getting token budget: {e}"

    def _handle_llm_context_update(self, args: List[str]) -> str:
        parser = self._create_parser("llm_context_update", "Update LLM context.")
        parser.add_argument("updates_json", help="Updates as JSON string")
        parsed_args = parser.parse_args(args)

        try:
            updates = json.loads(parsed_args.updates_json)
            # Assuming ContextManager can be instantiated directly
            context_manager = ContextManager()
            context_manager.update(updates)
            return "LLM context updated."
        except json.JSONDecodeError as e:
            return f"Invalid JSON provided for updates: {e}"
        except Exception as e:
            return f"Error updating LLM context: {e}"

    def _handle_llm_context_get(self, args: List[str]) -> str:
        if args:
            raise argparse.ArgumentError(None, "Command takes no arguments.")
        try:
            # Assuming ContextManager can be instantiated directly
            context_manager = ContextManager()
            context = context_manager.get()
            return f"Current LLM Context:\n{json.dumps(context, indent=2)}"
        except Exception as e:
            return f"Error getting LLM context: {e}"

    # --- Workflow & Environment Handlers ---
    def _handle_wf_gen_cwl(self, args: List[str]) -> str:
        parser = self._create_parser("wf_gen_cwl", "Generate CWL workflow.")
        parser.add_argument("steps_json", help="Workflow steps as JSON string")
        parsed_args = parser.parse_args(args)

        try:
            steps = json.loads(parsed_args.steps_json)
            # Assuming WorkflowGenerator can be instantiated directly
            generator = WorkflowGenerator()
            cwl_output = generator.generate_cwl(steps)
            # Decide how to output: print to console or save to file? Print for now.
            return f"Generated CWL Workflow:\n{cwl_output}"
        except json.JSONDecodeError as e:
            return f"Invalid JSON provided for steps: {e}"
        except Exception as e:
            return f"Error generating CWL workflow: {e}"

    def _handle_wf_gen_nextflow(self, args: List[str]) -> str:
        parser = self._create_parser("wf_gen_nextflow", "Generate Nextflow workflow.")
        parser.add_argument("steps_json", help="Workflow steps as JSON string")
        parsed_args = parser.parse_args(args)

        try:
            steps = json.loads(parsed_args.steps_json)
            generator = WorkflowGenerator()
            nf_output = generator.generate_nextflow(steps)
            return f"Generated Nextflow Workflow:\n{nf_output}"
        except json.JSONDecodeError as e:
            return f"Invalid JSON provided for steps: {e}"
        except Exception as e:
            return f"Error generating Nextflow workflow: {e}"

    def _handle_env_get(self, args: List[str]) -> str:
        if args:
            raise argparse.ArgumentError(None, "Command takes no arguments.")
        try:
            # Assuming EnvironmentTracker can be instantiated directly
            env_tracker = EnvironmentTracker()
            # Accessing protected method - consider making it public if used here
            details = env_tracker._get_environment_details()
            return f"Environment Details:\n{json.dumps(details, indent=2)}"
        except Exception as e:
            return f"Error getting environment details: {e}"

