import logging
import re
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
        self.ssh = ssh_manager
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
                    sbatch_cmd += f" {key}={shlex.quote(str(value))}" # Use shlex.quote for safety

        # Use echo with heredoc marker or pipe to pass the script content securely
        # Using process substitution with echo is generally safer and avoids temp files
        # Ensure the script content doesn't contain EOF marker itself
        heredoc_marker = "DAYHOFF_SBATCH_EOF"
        full_command = f"cat <<'{heredoc_marker}' | {sbatch_cmd}\n{script_content}\n{heredoc_marker}"

        logger.info(f"Executing Slurm submission command on {self.ssh.host}")
        try:
            # Execute the command. Ensure execute_command handles potential errors.
            output = self.ssh.execute_command(full_command)
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
                raise RuntimeError(f"Failed to parse job ID from sbatch output. Output: {output}")

        except Exception as e:
            logger.error(f"Error submitting Slurm job: {e}", exc_info=True)
            # Re-raise the exception to be handled by the caller
            raise RuntimeError(f"Error submitting Slurm job via SSH: {e}") from e


    def _parse_squeue_output(self, squeue_output: str) -> List[Dict[str, Any]]:
        """Parses the output of the squeue command with the defined format."""
        jobs = []
        lines = squeue_output.strip().split('\n')
        if not lines or len(lines) < 2: # Check for header + data
             logger.debug("squeue output is empty or contains only header.")
             return []

        header = lines[0].strip() # Slurm might add extra info before header sometimes
        # Find the actual header line based on expected fields (more robust)
        header_index = -1
        for i, line in enumerate(lines):
            if all(field.upper() in line for field in ["JOBID", "USER", "ST", "TIME"]): # Check for key fields
                header = line.strip()
                header_index = i
                break

        if header_index == -1:
             logger.warning(f"Could not find expected squeue header in output: {lines[0]}")
             # Attempt basic parsing assuming first line is header if desperate
             # return [] # Or raise error? Let's try basic parsing
             header_index = 0
             header = lines[0].strip()


        logger.debug(f"Using squeue header: {header}")
        logger.debug(f"Parsing squeue data lines starting from index {header_index + 1}")

        # Simple split based on the delimiter '|'
        num_fields = len(SQUEUE_FIELDS)
        for line in lines[header_index + 1:]:
            parts = line.strip().split('|')
            if len(parts) == num_fields:
                job_data = dict(zip(SQUEUE_FIELDS, parts))
                # Attempt to parse submit time for potential waiting time calculation
                try:
                    # Slurm time format can vary, try common ones
                    # Example: 2023-10-27T10:30:00
                    job_data['submit_time'] = datetime.fromisoformat(job_data['submit_time_str'])
                    # Make it timezone-aware (assume HPC uses UTC or local time - needs verification)
                    # If the time is naive, assume it's the system's local time.
                    # For simplicity, let's assume UTC if naive. A better approach might involve
                    # getting the HPC timezone, but that's complex.
                    if job_data['submit_time'].tzinfo is None:
                         # This is a guess - might need config or remote 'date +%Z' check
                         # job_data['submit_time'] = job_data['submit_time'].replace(tzinfo=timezone.utc)
                         pass # Keep it naive for now, comparison below will use naive UTC now

                except ValueError:
                    logger.warning(f"Could not parse submit time '{job_data['submit_time_str']}' for job {job_data.get('job_id')}")
                    job_data['submit_time'] = None
                jobs.append(job_data)
            else:
                logger.warning(f"Skipping malformed squeue line: {line.strip()} (expected {num_fields} fields, got {len(parts)})")

        logger.debug(f"Parsed {len(jobs)} jobs from squeue output.")
        return jobs

    def _calculate_waiting_summary(self, jobs: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calculates waiting time summary for pending jobs."""
        pending_jobs = [j for j in jobs if j.get('state_compact') == 'PD' and j.get('submit_time')]
        summary = {"pending_count": len(pending_jobs), "waiting_times_seconds": []}

        if not pending_jobs:
            summary["message"] = "No pending jobs found with submission times."
            return summary

        # Use current UTC time for comparison
        # Getting precise remote time is tricky; using local UTC is an approximation
        now_utc = datetime.now(timezone.utc).replace(tzinfo=None) # Use naive UTC

        for job in pending_jobs:
            # Compare naive datetime objects
            wait_duration = now_utc - job['submit_time']
            summary["waiting_times_seconds"].append(wait_duration.total_seconds())

        if summary["waiting_times_seconds"]:
            times = summary["waiting_times_seconds"]
            summary["min_wait_seconds"] = min(times)
            summary["max_wait_seconds"] = max(times)
            summary["avg_wait_seconds"] = sum(times) / len(times)
            # Add human-readable versions
            summary["min_wait_human"] = str(timedelta(seconds=summary["min_wait_seconds"]))
            summary["max_wait_human"] = str(timedelta(seconds=summary["max_wait_seconds"]))
            summary["avg_wait_human"] = str(timedelta(seconds=summary["avg_wait_seconds"]))
        else:
             summary["message"] = "No pending jobs found with parsable submission times."


        # Remove raw seconds list from final summary for cleaner output
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
        squeue_cmd = f"squeue --format='{SQUEUE_FORMAT}' --noheader" # Request no header from squeue

        if job_id:
            squeue_cmd += f" --jobs={shlex.quote(job_id)}"
        elif query_user:
            squeue_cmd += f" --user={shlex.quote(self.username)}"
        elif query_all:
            # No additional filter needed for all jobs
            pass
        else:
            # Default behavior if nothing is specified: query user's jobs
            if not self.username:
                 raise ValueError("Defaulting to user query, but username not available.")
            logger.info("No specific scope provided, defaulting to user's jobs.")
            squeue_cmd += f" --user={shlex.quote(self.username)}"


        logger.info(f"Executing Slurm query command on {self.ssh.host}: {squeue_cmd}")
        try:
            output = self.ssh.execute_command(squeue_cmd)
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
            raise RuntimeError(f"Error getting Slurm queue info via SSH: {e}") from e

    def get_job_status(self, job_id: str) -> Dict[str, str]:
        """Get the status of a *single* submitted job.

        Kept for backward compatibility or simple single-job checks.
        Prefer get_queue_info for more complex queries.

        Args:
            job_id: ID of the job to check

        Returns:
            dict: Dictionary containing job status information. Returns empty dict if job not found.
        """
        try:
            result = self.get_queue_info(job_id=job_id)
            if result["jobs"]:
                # Return the first (and should be only) job's details
                # Simplify the output compared to get_queue_info's list
                return result["jobs"][0]
            else:
                # Job not found or command failed implicitly
                logger.warning(f"Job ID {job_id} not found via squeue.")
                return {"job_id": job_id, "status": "NOT_FOUND"}
        except Exception as e:
             # Log the error but return a status indicating failure
             logger.error(f"Failed to get status for job {job_id}: {e}", exc_info=True)
             return {"job_id": job_id, "status": "QUERY_FAILED", "error": str(e)}

