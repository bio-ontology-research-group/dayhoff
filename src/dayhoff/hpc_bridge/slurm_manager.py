import logging
import re
import shlex # Added import
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional, List, Tuple

# Assuming SSHManager is correctly imported and provides execute_command
# from .ssh_manager import SSHManager # Assuming this path is correct

logger = logging.getLogger(__name__)

# Define a standard, parsable format for squeue output
# Example: JobID, Partition, Name, User, StateCompact, TimeUsed, Nodes, ReasonList, SubmitTime
SQUEUE_FORMAT = "%i|%P|%j|%u|%t|%M|%D|%R|%S"
SQUEUE_FIELDS = ["job_id", "partition", "name", "user", "state_compact", "time_used", "nodes", "reason", "submit_time_str"]

class SlurmManager:
    """Manages Slurm job submission and monitoring via SSH"""

    def __init__(self, ssh_manager):
        """Initialize with an SSH connection manager

        Args:
            ssh_manager: SSHManager instance for remote command execution
        """
        self.ssh_manager = ssh_manager # Renamed attribute from self.ssh
        # Attempt to get username from ssh_manager if available, needed for user-specific queries
        self.username = getattr(ssh_manager, 'username', None)
        if not self.username and hasattr(ssh_manager, 'ssh_config') and 'user' in ssh_manager.ssh_config:
             self.username = ssh_manager.ssh_config['user']


    def submit_job(self, script_content: str, job_options: Optional[Dict[str, Any]] = None) -> str:
        """Submit a job script to the Slurm scheduler using sbatch.

        Args:
            script_content: The content of the Slurm job script.
            job_options: Optional dictionary of Slurm options (e.g., {"--nodes": 1, "--time": "1:00:00"}).
                         These are added as command-line arguments to sbatch.

        Returns:
            str: The Job ID assigned by Slurm.

        Raises:
            ValueError: If the script content is empty.
            RuntimeError: If the sbatch command fails or doesn't return a job ID.
        """
        if not script_content:
            raise ValueError("Job script content cannot be empty.")

        # Construct the sbatch command
        sbatch_cmd = "sbatch"
        if job_options:
            for key, value in job_options.items():
                # Handle flags (like --exclusive) vs options with values
                if value is True: # Flag
                    sbatch_cmd += f" {key}"
                elif value is not None and value is not False: # Option with value
                    # Ensure keys starting with '--' are handled correctly if needed,
                    # but sbatch usually takes options like --nodes=1 or --time=...
                    # Using shlex.quote on the value provides safety.
                    sbatch_cmd += f" {key}={shlex.quote(str(value))}"

        # Use echo with heredoc marker or pipe to pass the script content securely
        # Using process substitution with echo is generally safer and avoids temp files
        # Ensure the script content doesn't contain EOF marker itself
        heredoc_marker = "DAYHOFF_SBATCH_EOF"
        # Ensure script_content ends with a newline before the marker
        script_content_nl = script_content if script_content.endswith('\n') else script_content + '\n'
        full_command = f"cat <<'{heredoc_marker}' | {sbatch_cmd}\n{script_content_nl}{heredoc_marker}"

        logger.info(f"Executing Slurm submission command on {self.ssh_manager.host}") # Use self.ssh_manager
        try:
            # Execute the command. Ensure execute_command handles potential errors.
            output = self.ssh_manager.execute_command(full_command) # Use self.ssh_manager
            logger.debug(f"sbatch output: {output}")

            # Parse the output to find the job ID
            # Typical output: "Submitted batch job 12345"
            match = re.search(r"Submitted batch job (\d+)", output)
            if match:
                job_id = match.group(1)
                logger.info(f"Successfully submitted job with ID: {job_id}")
                return job_id
            else:
                # Handle cases where sbatch might print warnings/errors but still submit,
                # or fail entirely.
                logger.error(f"Failed to parse job ID from sbatch output: {output}")
                # Include sbatch command in error for easier debugging
                raise RuntimeError(f"Failed to parse job ID from sbatch output. Command: '{sbatch_cmd}', Output: {output}")

        except Exception as e:
            logger.error(f"Error submitting Slurm job: {e}", exc_info=True)
            # Re-raise the exception to be handled by the caller
            raise RuntimeError(f"Error submitting Slurm job via SSH: {e}") from e


    def _parse_squeue_output(self, squeue_output: str) -> List[Dict[str, Any]]:
        """Parses the output of the squeue command with the defined format."""
        jobs = []
        lines = squeue_output.strip().split('\n')
        # Handle empty output or output with only potential Slurm informational messages
        if not lines:
             logger.debug("squeue output is empty.")
             return []

        # Slurm might prepend informational lines, find the first line that looks like data
        data_start_index = 0
        num_fields = len(SQUEUE_FIELDS)
        for i, line in enumerate(lines):
            parts = line.strip().split('|')
            # Check if it has the expected number of fields and the first field looks like a job ID (numeric)
            if len(parts) == num_fields and parts[0].isdigit():
                data_start_index = i
                logger.debug(f"Detected squeue data starting at line {i}: {line.strip()}")
                break
        else:
            # If no data lines found matching the format
            logger.warning(f"No data lines found in squeue output matching the expected format ({num_fields} fields, starting with digit). Output: {squeue_output}")
            return []


        logger.debug(f"Parsing squeue data lines starting from index {data_start_index}")

        for line in lines[data_start_index:]:
            parts = line.strip().split('|')
            if len(parts) == num_fields:
                job_data = dict(zip(SQUEUE_FIELDS, parts))
                # Attempt to parse submit time for potential waiting time calculation
                try:
                    # Slurm time format can vary, try common ones
                    # Example: 2023-10-27T10:30:00
                    # Use fromisoformat which is quite flexible
                    submit_dt_naive = datetime.fromisoformat(job_data['submit_time_str'])
                    # Store both naive and potentially timezone-aware versions if needed later
                    # For now, store naive for direct comparison with naive now_utc
                    job_data['submit_time'] = submit_dt_naive

                except ValueError:
                    logger.warning(f"Could not parse submit time '{job_data['submit_time_str']}' for job {job_data.get('job_id')} using fromisoformat.")
                    job_data['submit_time'] = None # Indicate parsing failure
                except TypeError: # Handle if submit_time_str is None or not string-like
                     logger.warning(f"Invalid type for submit time string '{job_data.get('submit_time_str')}' for job {job_data.get('job_id')}.")
                     job_data['submit_time'] = None

                jobs.append(job_data)
            else:
                # Log lines that don't match the expected field count after the detected start
                logger.warning(f"Skipping malformed squeue line: {line.strip()} (expected {num_fields} fields, got {len(parts)})")

        logger.debug(f"Parsed {len(jobs)} jobs from squeue output.")
        return jobs

    def _calculate_waiting_summary(self, jobs: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calculates waiting time summary for pending jobs."""
        # Filter for pending jobs ('PD') that have a successfully parsed submit_time
        pending_jobs = [j for j in jobs if j.get('state_compact') == 'PD' and isinstance(j.get('submit_time'), datetime)]
        summary = {"pending_count": len(pending_jobs), "waiting_times_seconds": []}

        if not pending_jobs:
            # Check total jobs to provide better context
            total_pending = sum(1 for j in jobs if j.get('state_compact') == 'PD')
            if total_pending > 0:
                 summary["message"] = f"{total_pending} pending jobs found, but none had parsable submission times for summary."
            else:
                 summary["message"] = "No pending jobs found."
            return summary

        # Use current UTC time for comparison, make it naive to compare with naive submit_time
        # Getting precise remote time is tricky; using local naive UTC is a practical approximation
        now_utc_naive = datetime.now(timezone.utc).replace(tzinfo=None) # Use naive UTC

        for job in pending_jobs:
            # Compare naive datetime objects
            wait_duration = now_utc_naive - job['submit_time']
            summary["waiting_times_seconds"].append(wait_duration.total_seconds())

        if summary["waiting_times_seconds"]:
            times = summary["waiting_times_seconds"]
            # Filter out potential negative times if clock skew is extreme (unlikely but possible)
            positive_times = [t for t in times if t >= 0]
            if not positive_times:
                 summary["message"] = "Pending jobs found, but waiting times could not be calculated (possible clock skew?)."
                 # Keep pending_count, remove times list
                 if "waiting_times_seconds" in summary: del summary["waiting_times_seconds"]
                 return summary

            summary["min_wait_seconds"] = min(positive_times)
            summary["max_wait_seconds"] = max(positive_times)
            summary["avg_wait_seconds"] = sum(positive_times) / len(positive_times)
            # Add human-readable versions using timedelta formatting
            summary["min_wait_human"] = str(timedelta(seconds=int(summary["min_wait_seconds"]))) # Use int for cleaner timedelta str
            summary["max_wait_human"] = str(timedelta(seconds=int(summary["max_wait_seconds"])))
            summary["avg_wait_human"] = str(timedelta(seconds=int(summary["avg_wait_seconds"])))
        else:
             # This case should be covered by the initial check, but handle defensively
             summary["message"] = "No pending jobs found with valid submission times."


        # Remove raw seconds list from final summary for cleaner output
        if "waiting_times_seconds" in summary:
            del summary["waiting_times_seconds"]

        return summary


    def get_queue_info(self, job_id: Optional[str] = None, query_user: bool = False, query_all: bool = False, waiting_summary: bool = False) -> Dict[str, Any]:
        """Get Slurm queue information based on scope.

        Args:
            job_id: Specific Job ID to query.
            query_user: If True, query jobs for the current user.
            query_all: If True, query all jobs in the queue.
            waiting_summary: If True, calculate and include a summary of waiting times for pending jobs.

        Returns:
            dict: Dictionary containing:
                  'jobs': A list of dictionaries, each representing a job's details.
                  'waiting_summary': (Optional) A dictionary with waiting time stats if requested.

        Raises:
            ValueError: If invalid combination of arguments is provided or user cannot be determined.
            RuntimeError: If the squeue command fails.
        """
        if sum([bool(job_id), query_user, query_all]) > 1:
            raise ValueError("Only one of job_id, query_user, or query_all can be specified.")
        if query_user and not self.username:
             raise ValueError("Cannot query by user: username not available from SSH configuration.")

        # Construct the squeue command
        # Request no header from squeue, parsing assumes our specific format
        squeue_cmd = f"squeue --format='{SQUEUE_FORMAT}' --noheader"

        if job_id:
            # Validate job_id format roughly (digits)
            if not re.fullmatch(r"\d+", job_id):
                 raise ValueError(f"Invalid job_id format: '{job_id}'. Must be numeric.")
            squeue_cmd += f" --jobs={shlex.quote(job_id)}"
        elif query_user:
            squeue_cmd += f" --user={shlex.quote(self.username)}"
        elif query_all:
            # No additional filter needed for all jobs
            pass
        else:
            # Default behavior if nothing is specified: query user's jobs
            if not self.username:
                 # If default is user, but no user, raise error instead of querying all
                 raise ValueError("Defaulting to user query, but username not available from SSH config. Use --all explicitly if intended.")
            logger.info("No specific scope provided, defaulting to user's jobs.")
            squeue_cmd += f" --user={shlex.quote(self.username)}"


        logger.info(f"Executing Slurm query command on {self.ssh_manager.host}: {squeue_cmd}") # Use self.ssh_manager
        try:
            # Add a reasonable timeout for squeue
            output = self.ssh_manager.execute_command(squeue_cmd, timeout=30) # Use self.ssh_manager
            logger.debug(f"Raw squeue output:\n{output}")

            parsed_jobs = self._parse_squeue_output(output)

            result = {"jobs": parsed_jobs}

            if waiting_summary:
                logger.info("Calculating waiting time summary...")
                summary = self._calculate_waiting_summary(parsed_jobs)
                result["waiting_summary"] = summary
                logger.debug(f"Waiting summary: {summary}")

            return result

        except Exception as e:
            logger.error(f"Error getting Slurm queue info: {e}", exc_info=True)
            # Check if it's a timeout error specifically
            if isinstance(e, TimeoutError):
                 raise RuntimeError(f"Timeout getting Slurm queue info via SSH: {e}") from e
            raise RuntimeError(f"Error getting Slurm queue info via SSH: {e}") from e

    def get_job_status(self, job_id: str) -> Dict[str, str]:
        """Get the status of a *single* submitted job.

        Kept for backward compatibility or simple single-job checks.
        Prefer get_queue_info for more complex queries.

        Args:
            job_id: ID of the job to check

        Returns:
            dict: Dictionary containing job status information. Returns specific status if job not found or query failed.
        """
        try:
            result = self.get_queue_info(job_id=job_id)
            if result["jobs"]:
                # Return the first (and should be only) job's details
                # Simplify the output compared to get_queue_info's list
                return result["jobs"][0]
            else:
                # Job not found or command failed implicitly (e.g., squeue returns non-zero exit but no output)
                # Check if squeue command itself might have failed if output was empty
                logger.warning(f"Job ID {job_id} not found via squeue or squeue returned no data.")
                # Provide a more specific status than just empty dict
                return {"job_id": job_id, "state_compact": "NOT_FOUND", "reason": "Job not found in squeue output"}
        except ValueError as e: # Catch invalid job_id format from get_queue_info
             logger.error(f"Invalid job ID format for status check: {job_id} - {e}")
             return {"job_id": job_id, "state_compact": "INVALID_ID", "reason": str(e)}
        except Exception as e:
             # Log the error but return a status indicating failure
             logger.error(f"Failed to get status for job {job_id}: {e}", exc_info=True)
             return {"job_id": job_id, "state_compact": "QUERY_FAILED", "reason": str(e)}

