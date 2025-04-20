import logging
import argparse
import textwrap
import os
import sys
import subprocess
import time
import io
from typing import List, Optional, TYPE_CHECKING

from rich.panel import Panel
from rich.live import Live
from rich.spinner import Spinner

if TYPE_CHECKING:
    from ..service import DayhoffService # Import DayhoffService for type hinting

logger = logging.getLogger(__name__)

# --- Misc Handlers (Help, Test) ---

def handle_help(service: 'DayhoffService', args: List[str]) -> Optional[str]:
    """Handles the /help command. Returns None as output is printed directly."""
    if not args:
        # General help
        status = service.get_status()
        current_language = service.config.get_workflow_language()
        current_executor = service.config.get_workflow_executor(current_language) or "N/A"
        llm_provider = service.config.get('LLM', 'provider', 'N/A')
        llm_model = service.config.get('LLM', 'model', 'N/A')
        exec_mode = status['exec_mode'] # Get from status
        queue_size = status['queue_size'] # Get queue size

        # Build status line
        if status['mode'] == 'connected':
            status_line = f"Mode: [bold green]Connected[/] ({status['user']}@{status['host']}:{status['cwd']})"
        else:
            status_line = f"Mode: [bold yellow]Local[/] ({status['cwd']})"
        status_line += f" | Exec: [bold]{exec_mode}[/]" # Add exec mode
        status_line += f" | Queue: [bold]{queue_size}[/]" # Add queue size

        # Check LLM config status for workflow generation hint
        llm_configured = False
        try:
            llm_cfg = service.config.get_llm_config()
            if llm_cfg.get('api_key') and llm_cfg.get('model'):
                llm_configured = True
        except Exception: pass

        help_text_lines = [
            f"[bold]Dayhoff REPL[/bold] - Type /<command> [arguments] to execute.",
            status_line,
            f"Workflow: {current_language.upper()} (Executor: {current_executor}) - Use /language, /config",
            f"LLM: {llm_provider.upper()} (Model: {llm_model}) - Use /config",
        ]
        if llm_configured:
             help_text_lines.append("Type text without '/' to generate a workflow.")
        else:
             help_text_lines.append("[dim]LLM not configured - workflow generation disabled.[/dim]")
        help_text_lines.append("Type /help <command> for details.")


        service.console.print(Panel(
            "\n".join(help_text_lines),
            title="Dayhoff Help",
            expand=False
        ))

        service.console.print("\n[bold cyan]Available commands:[/bold cyan]")
        # Group commands logically
        cmd_groups = {
            "General": ["help", "config", "language", "test"],
            "File System (Local/Remote)": ["ls", "cd", "fs_head"], # fs_head is local only
            "File Queue": ["queue"], # New category
            "HPC Connection": ["hpc_connect", "hpc_disconnect"],
            "HPC Execution": ["hpc_run"],
            "Slurm": ["hpc_slurm_run", "hpc_slurm_submit", "hpc_slurm_status"],
            "Credentials": ["hpc_cred_get"],
            "Workflow": ["wf_gen", "workflow"], # Added workflow command group
        }
        displayed_cmds = set()
        for group, cmds in cmd_groups.items():
             service.console.print(f"\n--- {group} ---")
             for cmd in cmds:
                 if cmd in service._command_map:
                     info = service._command_map[cmd]
                     first_line = info['help'].split('\n')[0].strip()
                     service.console.print(f"  /{cmd:<20} - {first_line}")
                     displayed_cmds.add(cmd)

        # Show any remaining commands not in groups
        remaining_cmds = sorted([cmd for cmd in service._command_map if cmd not in displayed_cmds])
        if remaining_cmds:
             service.console.print("\n--- Other ---")
             for cmd in remaining_cmds:
                  info = service._command_map[cmd]
                  first_line = info['help'].split('\n')[0].strip()
                  service.console.print(f"  /{cmd:<20} - {first_line}")

        service.console.print("\nType /help <command_name> for more details.")
        return None # Output printed directly
    else:
        # Specific command help
        cmd_name = args[0].lstrip('/')
        if cmd_name in service._command_map:
            # Use argparse's help printing mechanism for commands that use it heavily
            # Check if the handler uses argparse (heuristic: check for ArgumentParser creation or specific commands)
            # For simplicity, assume all handlers might use it or print their own help
            try:
                # Call the handler with '--help'
                service._command_map[cmd_name]['handler'](service, ['--help']) # Pass service instance
            except SystemExit: # Argparse calls sys.exit on --help
                pass # Expected behavior, help was printed
            except argparse.ArgumentError as e: # Handle cases where --help isn't the first arg or other parse errors
                # If ArgumentError occurs, print the stored help string as fallback
                logger.debug(f"ArgumentError showing help for {cmd_name}, falling back to stored help string: {e}")
                service.console.print(Panel(service._command_map[cmd_name]['help'], title=f"Help for /{cmd_name}", border_style="cyan"))
            except Exception as e:
                 logger.error(f"Unexpected error showing help for {cmd_name}", exc_info=True)
                 # Fallback to stored help string on unexpected errors
                 service.console.print(f"[warning]Could not display dynamic help for {cmd_name}. Showing basic help:[/warning]")
                 service.console.print(Panel(service._command_map[cmd_name]['help'], title=f"Help for /{cmd_name}", border_style="cyan"))

            return None # Output printed directly
        else:
             service.console.print(f"[error]Unknown command:[/error] /{cmd_name}")
             return None

def handle_test(service: 'DayhoffService', args: List[str]) -> Optional[str]:
    """Handles the /test command with subparsers."""
    parser = service._create_parser("test", service._command_map['test']['help'], add_help=True)
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
            _test_llm_connection(service) # This method prints its own output
            return None
        elif parsed_args.subcommand == "script":
            return _run_test_script(service, parsed_args.test_name) # This method returns string output, execute_command will print it
        elif parsed_args.subcommand == "list":
            return _list_test_scripts(service) # This method returns string output, execute_command will print it
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


def _list_test_scripts(service: 'DayhoffService') -> str:
    """Lists available test scripts in the examples directory."""
    # Assuming 'examples' is relative to the project root or CWD where dayhoff is run
    # This might need adjustment depending on installation structure
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
             help_lines.append(f"  (Directory '{examples_dir}' not found relative to CWD: {os.getcwd()})")
    except Exception as e:
         logger.error(f"Error listing test scripts in '{examples_dir}': {e}")
         help_lines.append(f"  (Error listing scripts: {e})")

    help_lines.append("\nUse '/test script <name>' to run a specific test.")
    return "\n".join(help_lines)


def _run_test_script(service: 'DayhoffService', test_name: str) -> str:
    """Runs a specific test script from the examples directory."""
    examples_dir = "examples"
    script_name = f"test_{test_name}.py"
    script_path = os.path.join(examples_dir, script_name)
    logger.info(f"Attempting to execute test script: {script_path}")

    if not os.path.isfile(script_path):
        # Provide list of available scripts in error message
        available_scripts_msg = _list_test_scripts(service)
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


def _test_llm_connection(service: 'DayhoffService') -> None:
    """Performs a simple test of the configured LLM connection. Prints output directly."""
    if not service.LLM_CLIENTS_AVAILABLE:
         service.console.print("[error]LLM client libraries not installed or found. Cannot run LLM test.[/error]")
         service.console.print("Please ensure necessary packages like 'openai' or 'anthropic' are installed.")
         return

    service.console.print("🧪 Testing LLM connection...")
    llm_config = service.config.get_llm_config()

    config_details = [
        f"Provider : {llm_config.get('provider') or '[Not Set]'}",
        f"Model    : {llm_config.get('model') or '[Not Set]'}",
        f"Base URL : {llm_config.get('base_url') or '[Provider Default]'}",
        f"API Key  : {'[Set]' if llm_config.get('api_key') else '[Not Set]'}" # Don't print the key
    ]
    service.console.print(Panel("\n".join(config_details), title="LLM Configuration", border_style="dim"))

    if not llm_config.get('api_key'):
         service.console.print("[error]LLM API Key is not configured (checked config file and environment variables). Cannot perform test.[/error]")
         return
    if not llm_config.get('model'):
         service.console.print("[error]LLM Model is not configured. Cannot perform test.[/error]")
         return

    try:
        client = service._get_llm_client() # Gets or initializes the client
        test_prompt = "Briefly explain the concept of bioinformatics in one sentence."
        service.console.print(f"  Sending test prompt to model '{llm_config.get('model')}'...")

        response_data = None
        error_message = None
        start_time = time.time()

        # Use Rich Live display for spinner
        with Live(Spinner("dots", text="Waiting for LLM response..."), console=service.console, transient=True, refresh_per_second=10) as live:
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
        service.console.print(f"  Request completed in {duration:.2f} seconds.")

        if error_message:
             service.console.print(f"[error]LLM API call failed:[/error] {error_message}")
             return # Stop test on API error

        # Check the structure of the response_data dictionary
        if response_data and isinstance(response_data, dict):
             response_text = response_data.get('response')
             tokens_used = response_data.get('tokens_used')
             model_used = response_data.get('model_used', llm_config.get('model')) # Fallback to configured model

             if response_text and isinstance(response_text, str) and response_text.strip():
                 service.console.print(Panel(response_text.strip(), title=f"LLM Response (from {model_used})", border_style="green", expand=False))
                 if tokens_used is not None:
                     service.console.print(f"  Tokens used: {tokens_used}", style="dim")
                 service.console.print("[bold green]✅ LLM Test Successful[/bold green]")
             else:
                 service.console.print("[warning]LLM Test Warning:[/warning] Received empty or unexpected response content.")
                 logger.warning(f"LLM test received empty response content: {response_data}")
        else:
             service.console.print("[warning]LLM Test Warning:[/warning] Received unexpected response format.")
             logger.warning(f"LLM test received unexpected response format: {response_data}")

    except ImportError as e:
         # This case should be caught earlier by LLM_CLIENTS_AVAILABLE, but handle defensively
         service.console.print(f"[error]Missing LLM client library dependency:[/error] {e}.")
         service.console.print("Please ensure necessary packages are installed.")
    except Exception as e:
        # Catch errors during client initialization or other unexpected issues
        logger.error(f"LLM connection test failed during setup or execution: {e}", exc_info=True)
        service.console.print(f"[error]LLM Test Failed:[/error] {e}")
