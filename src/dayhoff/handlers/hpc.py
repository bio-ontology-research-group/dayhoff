import logging
import argparse
import shlex
from typing import List, Optional, TYPE_CHECKING

from ..hpc_bridge.credentials import CredentialManager

if TYPE_CHECKING:
    from ..service import DayhoffService # Import DayhoffService for type hinting

logger = logging.getLogger(__name__)

# --- HPC Connection Handlers ---
def handle_hpc_connect(service: 'DayhoffService', args: List[str]) -> Optional[str]:
    """Establishes and stores a persistent SSH connection. Prints output."""
    parser = service._create_parser("hpc_connect", service._command_map['hpc_connect']['help'], add_help=True)
    try:
        parsed_args = parser.parse_args(args) # Handles --help

        if service.active_ssh_manager and service.active_ssh_manager.is_connected:
            try:
                test_cmd = "echo 'Dayhoff connection active'"
                logger.debug(f"Testing existing SSH connection with: {test_cmd}")
                service.active_ssh_manager.execute_command(test_cmd, timeout=5)
                host = service.active_ssh_manager.host
                logger.info(f"Persistent SSH connection to {host} is already active.")
                if service.remote_cwd is None: # Check if CWD is None
                    try:
                        # Use pwd -P to get physical directory, avoid symlink issues if possible
                        service.remote_cwd = service.active_ssh_manager.execute_command("pwd -P", timeout=10).strip()
                        logger.info(f"Refreshed remote CWD: {service.remote_cwd}")
                    except Exception as pwd_err:
                        logger.warning(f"Could not refresh remote CWD on existing connection: {pwd_err}")
                        # Attempt simpler 'pwd' as fallback
                        try:
                            service.remote_cwd = service.active_ssh_manager.execute_command("pwd", timeout=10).strip()
                            logger.info(f"Refreshed remote CWD (fallback): {service.remote_cwd}")
                        except Exception as pwd_err_fallback:
                            logger.warning(f"Could not refresh remote CWD using fallback 'pwd': {pwd_err_fallback}")
                            service.remote_cwd = "~" # Default CWD
                service.console.print(f"Already connected to HPC host: {host} (cwd: {service.remote_cwd}). Use /hpc_disconnect first to reconnect.", style="info")
                return None # Already connected
            except (ConnectionError, TimeoutError, RuntimeError) as e:
                logger.warning(f"Existing SSH connection seems stale ({type(e).__name__}: {e}), attempting to reconnect.")
                try: service.active_ssh_manager.disconnect()
                except Exception as close_err: logger.debug(f"Error closing stale SSH connection: {close_err}")
                service.active_ssh_manager = None
                service.remote_cwd = None
            except Exception as e:
                 logger.error(f"Unexpected error testing existing SSH connection: {e}", exc_info=True)
                 try: service.active_ssh_manager.disconnect()
                 except Exception: pass
                 service.active_ssh_manager = None
                 service.remote_cwd = None
                 service.console.print(f"[warning]Error testing existing connection ({e}). Cleared connection state. Please try connecting again.[/warning]")
                 return None


        service.console.print("Attempting to establish persistent SSH connection...", style="info")
        ssh_manager = None
        try:
            # Get manager instance, but don't connect immediately within _get_ssh_manager
            ssh_manager = service._get_ssh_manager(connect_now=False)
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

            service.active_ssh_manager = ssh_manager
            service.remote_cwd = initial_cwd # Set remote CWD
            exec_mode = service.config.get_execution_mode() # Get current exec mode
            service.console.print(f"Successfully connected to HPC host: {hostname} (user: {ssh_manager.username}, cwd: {service.remote_cwd}, exec_mode: {exec_mode}).", style="bold green")
            return None

        except (ConnectionError, TimeoutError, RuntimeError, ValueError) as e:
            logger.error(f"Failed to establish persistent SSH connection: {type(e).__name__}: {e}", exc_info=False)
            if ssh_manager: ssh_manager.disconnect() # Ensure cleanup
            service.active_ssh_manager = None
            service.remote_cwd = None
            # Raise the error for execute_command to catch and display
            raise ConnectionError(f"Failed to establish SSH connection: {e}") from e
        except Exception as e:
            logger.error(f"Unexpected error during persistent SSH connection: {e}", exc_info=True)
            if ssh_manager: ssh_manager.disconnect()
            service.active_ssh_manager = None
            service.remote_cwd = None
            raise ConnectionError(f"Unexpected error establishing SSH connection: {e}") from e

    except argparse.ArgumentError as e:
         raise e # Let execute_command handle parser errors
    except SystemExit:
         return None # Help was printed


def handle_hpc_disconnect(service: 'DayhoffService', args: List[str]) -> Optional[str]:
    """Closes the persistent SSH connection. Prints output."""
    parser = service._create_parser("hpc_disconnect", service._command_map['hpc_disconnect']['help'], add_help=True)
    try:
        parsed_args = parser.parse_args(args) # Handles --help

        if not service.active_ssh_manager:
            service.console.print("No active HPC connection to disconnect.", style="warning")
            return None

        logger.info("Disconnecting persistent SSH connection...")
        try:
            host = getattr(service.active_ssh_manager, 'host', 'unknown')
            service.active_ssh_manager.disconnect()
            service.active_ssh_manager = None
            service.remote_cwd = None # Clear remote CWD
            service.console.print(f"Successfully disconnected from HPC host: {host}. Operating in local mode.", style="info")
            return None
        except Exception as e:
            logger.error(f"Error during SSH disconnection: {e}", exc_info=True)
            # Force clear state even if disconnect fails
            service.active_ssh_manager = None
            service.remote_cwd = None # Clear remote CWD
            raise RuntimeError(f"Error closing SSH connection: {e}") from e

    except argparse.ArgumentError as e:
         raise e
    except SystemExit:
         return None # Help was printed


def handle_hpc_run(service: 'DayhoffService', args: List[str]) -> Optional[str]:
    """Executes a command using the active persistent SSH connection, respecting execution_mode. Prints output."""
    parser = service._create_parser("hpc_run", service._command_map['hpc_run']['help'], add_help=True)
    # Use REMAINDER to capture the full command string
    parser.add_argument("command_string", nargs=argparse.REMAINDER, help="The command and arguments to execute remotely.")

    try:
        parsed_args = parser.parse_args(args)

        if not parsed_args.command_string:
             raise argparse.ArgumentError(None, "Missing command to execute.")

        if not service.active_ssh_manager or not service.active_ssh_manager.is_connected:
            raise ConnectionError("Not connected to HPC. Use /hpc_connect first.")
        if service.remote_cwd is None: # Check for None specifically
             raise ConnectionError("Remote working directory unknown. Please use /hpc_connect again.")

        # Get execution mode from config
        exec_mode = service.config.get_execution_mode()
        user_command = " ".join(shlex.quote(arg) for arg in parsed_args.command_string)
        command_to_run = ""
        exec_via = "" # For logging

        # Ensure we are in the correct directory before execution
        cd_cmd = f"cd {shlex.quote(service.remote_cwd)}"

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
            output = service.active_ssh_manager.execute_command(command_to_run, timeout=timeout)
            # Print the raw output
            if output:
                 service.console.print(output)
            else:
                 service.console.print(f"(Command via {exec_via} produced no output)", style="dim")
            return None # Output printed directly

        except ConnectionError as e:
            logger.error(f"Connection error during /hpc_run (via {exec_via}): {e}", exc_info=False)
            try: service.active_ssh_manager.disconnect()
            except Exception: pass
            service.active_ssh_manager = None
            service.remote_cwd = None
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

def handle_hpc_cred_get(service: 'DayhoffService', args: List[str]) -> Optional[str]:
    """Gets HPC password status from keyring. Prints output."""
    parser = service._create_parser("hpc_cred_get", service._command_map['hpc_cred_get']['help'], add_help=True)
    parser.add_argument("username", help="HPC username")

    try:
        parsed_args = parser.parse_args(args)

        # Use CredentialManager directly (doesn't need active SSH)
        # Get system name from config if possible
        system_name_base = service.config.get('HPC', 'credential_system', 'dayhoff_hpc')
        # CredentialManager might combine this with hostname internally, adjust if needed
        cred_manager = CredentialManager(system_name=system_name_base) # Pass base name

        password_found = cred_manager.get_password(username=parsed_args.username) is not None
        # Use the actual system name used by the manager if available
        actual_system_name = getattr(cred_manager, 'system_name', system_name_base)

        if password_found:
             logger.info(f"Password found for user '{parsed_args.username}' (system: {actual_system_name}) in keyring.")
             service.console.print(f"Password found for user '{parsed_args.username}' (system: {actual_system_name}) in system keyring.", style="info")
        else:
             logger.info(f"No stored password found for user '{parsed_args.username}' (system: {actual_system_name}) in keyring.")
             service.console.print(f"No stored password found for user '{parsed_args.username}' (system: {actual_system_name}) in system keyring.", style="info")
        return None # Output printed

    except argparse.ArgumentError as e: raise e
    except SystemExit: return None # Help printed
    except Exception as e:
        logger.error(f"Error retrieving credentials for {args[0] if args else ''}", exc_info=True)
        raise RuntimeError(f"Error retrieving credentials: {e}") from e
