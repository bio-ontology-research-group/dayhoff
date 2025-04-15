import os
import logging
from typing import Optional, Dict
import paramiko
from pathlib import Path
import socket # Moved import to the top

# Removed incorrect import: from ..config import config

logger = logging.getLogger(__name__)

class SSHManager:
    """Manages SSH connections to remote HPC systems"""

    def __init__(self, ssh_config: Dict[str, str]):
        """Initialize SSH connection parameters from a configuration dictionary.

        Args:
            ssh_config: A dictionary containing SSH configuration details like
                        'host', 'username', 'auth_method', 'ssh_key', 'password',
                        'known_hosts', 'port', 'ssh_key_dir'.

        Raises:
            ValueError: If essential configuration keys ('host') are missing.
        """
        self.ssh_config = ssh_config
        self.connection: Optional[paramiko.SSHClient] = None

        # Extract essential parameters
        self.host: Optional[str] = ssh_config.get('host')
        if not self.host:
            logger.error("SSH configuration dictionary is missing the 'host' key.")
            raise ValueError("SSH configuration must include a 'host'.")

        # Use provided username or fallback to current system user
        self.username: str = ssh_config.get('username') or os.getlogin()
        self.port: int = int(ssh_config.get('port', 22)) # Default SSH port is 22

        # Authentication details
        raw_auth_method: str = ssh_config.get('auth_method', 'key')
        # Clean the auth_method string: remove comments and strip whitespace
        self.auth_method: str = raw_auth_method.split('#')[0].strip().lower()

        # --- SSH Key Handling ---
        raw_key_file: Optional[str] = ssh_config.get('ssh_key')
        raw_key_dir: Optional[str] = ssh_config.get('ssh_key_dir')
        self.key_file: Optional[str] = None # Initialize

        key_file_name: Optional[str] = None
        if raw_key_file:
            key_file_name = raw_key_file.split('#')[0].strip()

        key_dir: Optional[str] = None
        if raw_key_dir:
            key_dir = raw_key_dir.split('#')[0].strip()

        if self.auth_method == 'key':
            if key_file_name:
                # Expand user ~ in key_file_name first, in case it's an absolute path
                expanded_key_file_name = os.path.expanduser(key_file_name)

                if key_dir:
                    # Construct full path if directory is provided
                    expanded_key_dir = os.path.expanduser(key_dir)
                    # Check if expanded_key_file_name is already absolute
                    if os.path.isabs(expanded_key_file_name):
                        self.key_file = expanded_key_file_name # Use the absolute path directly
                        logger.debug(f"Using absolute SSH key path from 'ssh_key': {self.key_file}")
                    else:
                        # Join directory and relative filename
                        self.key_file = os.path.join(expanded_key_dir, expanded_key_file_name)
                        logger.debug(f"Constructed SSH key path using 'ssh_key_dir' and 'ssh_key': {self.key_file}")
                else:
                    # Assume expanded_key_file_name is a full path or relative to CWD
                    self.key_file = expanded_key_file_name
                    logger.debug(f"Using SSH key path directly from 'ssh_key' (no ssh_key_dir provided): {self.key_file}")

                # Final check for key file existence
                if not os.path.exists(self.key_file):
                     logger.warning(f"SSH key file specified does not exist: {self.key_file}")
                     # Set key_file back to None if it doesn't exist to prevent connection attempt
                     self.key_file = None
                else:
                     logger.debug(f"Verified SSH key file exists: {self.key_file}")

            else:
                logger.warning("SSH auth method is 'key', but 'ssh_key' is missing or empty in config.")
        # --- End SSH Key Handling ---


        self.password: Optional[str] = ssh_config.get('password') # Password should ideally be handled securely

        # Host key checking
        self.known_hosts_file: Optional[str] = ssh_config.get('known_hosts') # Path should be resolved

        # Clean known_hosts_file path if it exists
        if self.known_hosts_file:
             raw_known_hosts = self.known_hosts_file
             self.known_hosts_file = os.path.expanduser(raw_known_hosts.split('#')[0].strip())
             logger.debug(f"Using known_hosts file: {self.known_hosts_file}")


        logger.debug(f"SSHManager initialized for host={self.host}, user={self.username}, port={self.port}, auth={self.auth_method}, key_file={self.key_file}")
        if self.auth_method == 'key' and not self.key_file:
             # This warning might be redundant now due to earlier checks, but keep for clarity
             logger.warning("SSH auth method is 'key', but effective key file path could not be determined or file does not exist.")
        elif self.auth_method == 'password' and not self.password:
             logger.warning("SSH auth method is 'password', but 'password' is missing in config.")


    def connect(self) -> bool:
        """Establish SSH connection using configured authentication method.

        Returns:
            bool: True if connection was successful and is active, False otherwise.
        """
        if self.connection and self.is_connected:
            logger.debug("SSH connection already established.")
            return True

        try:
            self.connection = paramiko.SSHClient()

            # Load known hosts if specified and exists
            if self.known_hosts_file:
                if os.path.exists(self.known_hosts_file):
                    self.connection.load_system_host_keys(filename=self.known_hosts_file)
                    logger.debug(f"Loaded known host keys from {self.known_hosts_file}")
                else:
                    logger.warning(f"Specified known_hosts file not found: {self.known_hosts_file}. Falling back to system keys.")
                    self.connection.load_system_host_keys() # Fallback
            else:
                 # Fallback to default system keys if specific file not specified
                 self.connection.load_system_host_keys()
                 logger.debug("Loaded default system host keys (no specific known_hosts file configured).")


            # Policy for adding new host keys (consider RejectPolicy for higher security)
            self.connection.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            # self.connection.set_missing_host_key_policy(paramiko.RejectPolicy()) # Stricter

            logger.info(f"Attempting SSH connection to {self.host}:{self.port} as {self.username} using {self.auth_method} auth...")

            connect_args = {
                'hostname': self.host,
                'port': self.port,
                'username': self.username,
                'timeout': 10 # Add a connection timeout
            }

            if self.auth_method == 'key':
                if not self.key_file:
                    # This error should ideally be caught during init, but double-check
                    logger.error("SSH key file path was not determined or file does not exist.")
                    self.connection = None # Ensure connection is None
                    return False
                # Check existence again just before use (redundant but safe)
                if not os.path.exists(self.key_file):
                    logger.error(f"SSH key file not found: {self.key_file}") # Log the full path being checked
                    self.connection = None # Ensure connection is None
                    return False
                try:
                    # Attempt to load key (supports various formats)
                    # Consider adding passphrase support if keys are encrypted
                    # Use self.key_file which should now be the full path
                    # Try common key types
                    loaded_key = None
                    key_types = [paramiko.Ed25519Key, paramiko.RSAKey, paramiko.ECDSAKey, paramiko.DSSKey]
                    for key_type in key_types:
                        try:
                            # TODO: Add passphrase handling if needed
                            # password = self.password if self.password else None # Example passphrase source
                            loaded_key = key_type.from_private_key_file(self.key_file) #, password=password)
                            logger.debug(f"Loaded {key_type.__name__} key from {self.key_file}")
                            break # Stop trying once a key is loaded
                        except paramiko.ssh_exception.PasswordRequiredException:
                            logger.error(f"SSH key file {self.key_file} is encrypted and requires a passphrase (not implemented).")
                            self.connection = None
                            return False
                        except paramiko.ssh_exception.SSHException:
                            # This key type didn't work, try the next one
                            continue
                        except Exception as key_load_err:
                             logger.error(f"Unexpected error loading key {self.key_file} as {key_type.__name__}: {key_load_err}")
                             # Continue trying other key types? Or fail here? Let's continue for now.

                    if not loaded_key:
                         logger.error(f"Failed to load private key ({self.key_file}) using supported types.")
                         self.connection = None
                         return False

                    connect_args['pkey'] = loaded_key

                except Exception as key_err: # Catch any unexpected error during key loading phase
                     logger.error(f"Unexpected error processing private key file {self.key_file}: {key_err}", exc_info=True)
                     self.connection = None
                     return False


            elif self.auth_method == 'password':
                if not self.password:
                    logger.error("Password authentication selected, but no password provided in config.")
                    # Consider prompting user if running interactively, but not suitable for service
                    self.connection = None # Ensure connection is None
                    return False
                connect_args['password'] = self.password
                connect_args['look_for_keys'] = False # Don't waste time looking for keys
                connect_args['allow_agent'] = False # Don't use SSH agent if using password

            else:
                # Log the *cleaned* auth method here
                logger.error(f"Unsupported authentication method: '{self.auth_method}'")
                self.connection = None # Ensure connection is None
                return False

            # *** The actual connection attempt ***
            self.connection.connect(**connect_args)

            # *** Explicitly check if connection is active AFTER connect() call ***
            if self.is_connected:
                logger.info("SSH connection established successfully and transport is active.")
                return True
            else:
                # This case might occur if connect() returns without error but transport isn't active
                logger.error("SSH connection attempt finished, but connection is not active.")
                self.disconnect() # Clean up potentially partially formed connection
                return False

        except paramiko.ssh_exception.AuthenticationException as auth_err:
             logger.error(f"SSH authentication failed: {auth_err}")
             self.disconnect() # Clean up
             return False
        except paramiko.ssh_exception.SSHException as ssh_err:
             # More specific SSH errors (e.g., NoValidConnectionsError, BadHostKeyException)
             logger.error(f"SSH connection error: {type(ssh_err).__name__}: {ssh_err}")
             self.disconnect() # Clean up
             return False
        except socket.timeout:
             logger.error(f"SSH connection timed out to {self.host}:{self.port}")
             self.disconnect() # Clean up
             return False
        except socket.error as sock_err:
             logger.error(f"Socket error during SSH connection: {sock_err}")
             self.disconnect() # Clean up
             return False
        except Exception as e:
            # Catch-all for other unexpected errors during connection setup
            logger.error(f"Unexpected error during SSH connection: {type(e).__name__}: {e}", exc_info=True)
            self.disconnect() # Clean up
            return False

    def execute_command(self, command: str, timeout: Optional[int] = 60) -> str:
        """Execute a command on the remote system.

        Args:
            command: Command string to execute.
            timeout: Optional timeout in seconds for command execution.

        Returns:
            str: Combined standard output and standard error from the command.

        Raises:
            RuntimeError: If no connection is established or active.
            TimeoutError: If the command execution times out.
            ConnectionError: If the SSH connection drops during execution.
        """
        if not self.connection or not self.is_connected:
            logger.error("Attempted to execute command without an active SSH connection.")
            # Raise RuntimeError here as the connection should have been verified before calling this
            raise RuntimeError("SSH connection not established or active.")

        logger.debug(f"Executing remote command: {command}")
        try:
            # Use invoke_shell() or request_pty=True for interactive-like sessions if needed
            stdin, stdout, stderr = self.connection.exec_command(command, timeout=timeout)

            # Read output/error streams
            # Consider reading in chunks for very large outputs
            output = stdout.read().decode(errors='ignore').strip()
            error = stderr.read().decode(errors='ignore').strip()

            exit_status = stdout.channel.recv_exit_status() # Get exit status
            logger.debug(f"Command finished with exit status: {exit_status}")

            # Combine output and error for simplicity, log error separately
            combined_output = output
            if error:
                logger.warning(f"Command stderr: {error}")
                # Append error to output for visibility, could be handled differently
                if combined_output:
                     combined_output += f"\nSTDERR: {error}"
                else:
                     combined_output = f"STDERR: {error}"

            # Optionally raise an exception if exit status is non-zero
            # if exit_status != 0:
            #    raise RuntimeError(f"Remote command failed with exit status {exit_status}: {command}\nOutput:\n{combined_output}")

            return combined_output

        except paramiko.ssh_exception.SSHException as e:
             logger.error(f"SSH error during command execution: {e}", exc_info=True)
             # This often indicates the connection dropped.
             self.disconnect() # Close potentially broken connection
             # Raise ConnectionError to signal the connection is gone
             raise ConnectionError(f"SSH connection error during command execution: {e}") from e
        except socket.timeout: # Catch timeout from exec_command
             logger.error(f"Remote command timed out after {timeout} seconds: {command}")
             raise TimeoutError(f"Remote command timed out: {command}")
        except Exception as e:
             logger.error(f"Error executing remote command '{command}': {e}", exc_info=True)
             # Raise a generic RuntimeError for other execution issues
             raise RuntimeError(f"Error executing remote command: {e}") from e


    def disconnect(self):
        """Close the SSH connection."""
        if self.connection:
            logger.info(f"Closing SSH connection to {self.host}.")
            try:
                self.connection.close()
            except Exception as e:
                 logger.error(f"Error closing SSH connection: {e}", exc_info=True)
            finally:
                 self.connection = None
        else:
             logger.debug("No active SSH connection to disconnect.")

    @property
    def is_connected(self) -> bool:
        """Check if the SSH connection transport is active."""
        if not self.connection:
            # logger.debug("is_connected check: No connection object.")
            return False
        try:
            transport = self.connection.get_transport()
            if transport is not None and transport.is_active():
                 # logger.debug("is_connected check: Transport active.")
                 return True
            else:
                 # logger.debug(f"is_connected check: Transport inactive (transport={transport}).")
                 return False
        except Exception as e:
            # logger.debug(f"is_connected check: Exception during check: {e}")
            return False # Assume not connected if checking fails

    # Context manager support
    def __enter__(self):
        """Enter context manager, establish connection."""
        if not self.connect():
             # Use a more specific error message if possible
             raise ConnectionError(f"Failed to establish SSH connection to {self.host} in context manager.")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit context manager, close connection."""
        self.disconnect()
