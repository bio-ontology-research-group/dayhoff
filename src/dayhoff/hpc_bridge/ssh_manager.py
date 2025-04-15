import os
import logging
from typing import Optional, Dict
import paramiko
from pathlib import Path
# Removed incorrect import: from ..config import config

logger = logging.getLogger(__name__)

class SSHManager:
    """Manages SSH connections to remote HPC systems"""

    def __init__(self, ssh_config: Dict[str, str]):
        """Initialize SSH connection parameters from a configuration dictionary.

        Args:
            ssh_config: A dictionary containing SSH configuration details like
                        'host', 'username', 'auth_method', 'ssh_key', 'password',
                        'known_hosts', 'port'.

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
        self.auth_method: str = ssh_config.get('auth_method', 'key').lower()
        self.key_file: Optional[str] = ssh_config.get('ssh_key') # Path should be resolved by config loader
        self.password: Optional[str] = ssh_config.get('password') # Password should ideally be handled securely

        # Host key checking
        self.known_hosts_file: Optional[str] = ssh_config.get('known_hosts') # Path should be resolved

        logger.debug(f"SSHManager initialized for host={self.host}, user={self.username}, port={self.port}, auth={self.auth_method}")
        if self.auth_method == 'key' and not self.key_file:
             logger.warning("SSH auth method is 'key', but 'ssh_key' path is missing in config.")
        elif self.auth_method == 'password' and not self.password:
             logger.warning("SSH auth method is 'password', but 'password' is missing in config.")


    def connect(self) -> bool:
        """Establish SSH connection using configured authentication method.

        Returns:
            bool: True if connection was successful, False otherwise.
        """
        if self.connection and self.is_connected:
            logger.debug("SSH connection already established.")
            return True

        try:
            self.connection = paramiko.SSHClient()

            # Load known hosts if specified
            if self.known_hosts_file and os.path.exists(self.known_hosts_file):
                 self.connection.load_system_host_keys(filename=self.known_hosts_file)
                 logger.debug(f"Loaded known host keys from {self.known_hosts_file}")
            else:
                 # Fallback to default system keys if specific file not found/specified
                 self.connection.load_system_host_keys()
                 logger.debug("Loaded default system host keys.")

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
                if not self.key_file or not os.path.exists(self.key_file):
                    logger.error(f"SSH key file not found or not specified: {self.key_file}")
                    return False
                try:
                    # Attempt to load key (supports various formats)
                    # Consider adding passphrase support if keys are encrypted
                    private_key = paramiko.Ed25519Key.from_private_key_file(self.key_file)
                    logger.debug(f"Loaded Ed25519 key from {self.key_file}")
                except paramiko.ssh_exception.SSHException:
                    try:
                        private_key = paramiko.RSAKey.from_private_key_file(self.key_file)
                        logger.debug(f"Loaded RSA key from {self.key_file}")
                    except paramiko.ssh_exception.SSHException:
                         try:
                             private_key = paramiko.ECDSAKey.from_private_key_file(self.key_file)
                             logger.debug(f"Loaded ECDSA key from {self.key_file}")
                         except paramiko.ssh_exception.SSHException as key_err:
                              logger.error(f"Failed to load private key ({self.key_file}): {key_err}")
                              return False

                connect_args['pkey'] = private_key

            elif self.auth_method == 'password':
                if not self.password:
                    logger.error("Password authentication selected, but no password provided in config.")
                    # Consider prompting user if running interactively, but not suitable for service
                    return False
                connect_args['password'] = self.password
                connect_args['look_for_keys'] = False # Don't waste time looking for keys
                connect_args['allow_agent'] = False # Don't use SSH agent if using password

            else:
                logger.error(f"Unsupported authentication method: {self.auth_method}")
                return False

            self.connection.connect(**connect_args)
            logger.info("SSH connection established successfully.")
            return True

        except paramiko.ssh_exception.AuthenticationException as auth_err:
             logger.error(f"SSH authentication failed: {auth_err}")
             self.connection = None # Ensure connection is None on failure
             return False
        except Exception as e:
            logger.error(f"SSH connection failed: {type(e).__name__}: {e}", exc_info=True)
            self.connection = None # Ensure connection is None on failure
            return False

    def execute_command(self, command: str, timeout: Optional[int] = 60) -> str:
        """Execute a command on the remote system.

        Args:
            command: Command string to execute.
            timeout: Optional timeout in seconds for command execution.

        Returns:
            str: Combined standard output and standard error from the command.

        Raises:
            RuntimeError: If no connection is established.
            TimeoutError: If the command execution times out.
        """
        if not self.connection or not self.is_connected:
            logger.error("Attempted to execute command without an active SSH connection.")
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
             # Attempt to reconnect or handle disconnection? For now, raise.
             self.disconnect() # Close potentially broken connection
             raise RuntimeError(f"SSH error during command execution: {e}")
        except socket.timeout: # Catch timeout from exec_command
             logger.error(f"Remote command timed out after {timeout} seconds: {command}")
             raise TimeoutError(f"Remote command timed out: {command}")
        except Exception as e:
             logger.error(f"Error executing remote command '{command}': {e}", exc_info=True)
             raise RuntimeError(f"Error executing remote command: {e}")


    def disconnect(self):
        """Close the SSH connection."""
        if self.connection:
            logger.info("Closing SSH connection.")
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
        """Check if the SSH connection is active."""
        if not self.connection:
            return False
        try:
            # Check if transport is active
            return self.connection.get_transport() is not None and self.connection.get_transport().is_active()
        except Exception:
            return False # Assume not connected if checking fails

    # Context manager support
    def __enter__(self):
        """Enter context manager, establish connection."""
        if not self.connect():
             raise RuntimeError("Failed to establish SSH connection.")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit context manager, close connection."""
        self.disconnect()

# Need to import socket for timeout exception handling
import socket
