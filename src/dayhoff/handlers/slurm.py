import json
import logging
import argparse
import os
import shlex
from pathlib import Path
from typing import List, Optional, TYPE_CHECKING

from rich.panel import Panel
from rich.table import Table

if TYPE_CHECKING:
    from ..service import DayhoffService # Import DayhoffService for type hinting

logger = logging.getLogger(__name__)

# --- Slurm Handlers ---
def handle_hpc_slurm_run(service: 'DayhoffService', args: List[str]) -> Optional[str]:
    """Executes a command explicitly within a Slurm allocation (srun). Prints output."""
    # This command ignores the execution_mode setting.
    parser = service._create_parser("hpc_slurm_run", service._command_map['hpc_slurm_run']['help'], add_help=True)
    parser.add_argument("command_string", nargs=argparse.REMAINDER, help="The command and arguments to execute via srun.")

    try:
        parsed_args = parser.parse_args(args)

        if not parsed_args.command_string:
             raise argparse.ArgumentError(None, "Missing command to execute via srun.")

        if not service.active_ssh_manager or not service.active_ssh_manager.is_connected:
            raise ConnectionError("Not connected to HPC. Use /hpc_connect first.")
        if service.remote_cwd is None:
             raise ConnectionError("Remote working directory unknown. Please use /hpc_connect again.")

        user_command = " ".join(shlex.quote(arg) for arg in parsed_args.command_string)
        # Use --pty for interactive-like behavior if possible
        srun_command = f"srun --pty {user_command}"
        full_command = f"cd {shlex.quote(service.remote_cwd)} && {srun_command}"
        timeout = 600 # 10 min timeout

        try:
            logger.info(f"Executing command explicitly via srun using active SSH connection: {full_command}")
            # Relies on execute_command raising RuntimeError on failure
            output = service.active_ssh_manager.execute_command(full_command, timeout=timeout)
            if output:
                 service.console.print(output)
            else:
                 service.console.print("(Explicit srun command produced no output)", style="dim")
            return None # Output printed

        except ConnectionError as e:
            logger.error(f"Connection error during explicit /hpc_slurm_run: {e}", exc_info=False)
            try: service.active_ssh_manager.disconnect()
            except Exception: pass
            service.active_ssh_manager = None
            service.remote_cwd = None
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

def handle_hpc_slurm_submit(service: 'DayhoffService', args: List[str]) -> Optional[str]:
    """Submits a Slurm job script, potentially adding --singularity. Prints output."""
    parser = service._create_parser("hpc_slurm_submit", service._command_map['hpc_slurm_submit']['help'], add_help=True)
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
        script_path_obj = (Path(service.local_cwd) / parsed_args.script_path).resolve()
        script_path = str(script_path_obj)

        if not os.path.isfile(script_path):
             raise FileNotFoundError(f"Script file not found at '{script_path}'")

        with open(script_path, 'r') as f:
            script_content = f.read()

        # --- Handle Singularity Option ---
        job_options = user_options.copy() # Start with user options
        use_singularity_config = service.config.get_slurm_use_singularity()
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


        slurm_manager = service._get_slurm_manager() # Gets manager with active (or temp) SSH

        logger.info(f"Submitting Slurm job from script: {script_path} with effective options: {job_options}")
        service.console.print(f"Submitting Slurm job from '{os.path.basename(script_path)}'...", style="info")

        job_id = slurm_manager.submit_job(script_content, job_options)
        service.console.print(f"Slurm job submitted with ID: {job_id}", style="bold green")
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
        service._close_slurm_manager_ssh(slurm_manager)


def handle_hpc_slurm_status(service: 'DayhoffService', args: List[str]) -> Optional[str]:
    """Gets Slurm job status. Prints output."""
    parser = service._create_parser("hpc_slurm_status", service._command_map['hpc_slurm_status']['help'], add_help=True)
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

        slurm_manager = service._get_slurm_manager()
        logger.info(f"Getting Slurm status info (job_id={job_id}, user={query_user}, all={query_all}, summary={parsed_args.waiting_summary})")
        service.console.print("Fetching Slurm queue information...", style="info")

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
            service.console.print("No Slurm jobs found matching the criteria.", style="info")
        elif not jobs and summary and not summary.get('pending_count', 0):
             service.console.print("No running/pending Slurm jobs found matching the criteria.", style="info")
             # Still print summary if it has info (e.g., message)
        else:
            # Use Rich Table for better formatting
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
                 service.console.print(table)
            elif not summary: # No jobs and no summary
                 service.console.print("No Slurm jobs found matching the criteria.", style="info")


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
                 service.console.print(Panel("\n".join(summary_lines), expand=False))
            elif not jobs: # No jobs and only header in summary
                 service.console.print("No pending jobs found for summary.", style="info")


        return None # Output printed

    except argparse.ArgumentError as e: raise e
    except SystemExit: return None # Help printed
    except (ConnectionError, ValueError, RuntimeError) as e:
        raise e # Re-raise for execute_command
    except Exception as e:
        logger.error(f"Error getting Slurm job status", exc_info=True)
        raise RuntimeError(f"Error getting Slurm job status: {e}") from e
    finally:
        service._close_slurm_manager_ssh(slurm_manager)
