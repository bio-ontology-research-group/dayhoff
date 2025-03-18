import os
from typing import Optional, Dict
import paramiko  # TODO: Add to requirements
from pathlib import Path
from ..config import config

class SSHManager:
    """Manages SSH connections to remote HPC systems"""
    
    def __init__(self, host: Optional[str] = None, username: Optional[str] = None):
        """Initialize SSH connection parameters
        
        Args:
            host: Hostname or IP address of the remote system (uses config default if None)
            username: Username for authentication (uses system username if None)
        """
        self.host = host or config.get('HPC', 'default_host')
        self.username = username or os.getlogin()
        self.connection: Optional[paramiko.SSHClient] = None
        self.ssh_config = config.get_ssh_config()
        
    def connect(self) -> bool:
        """Establish SSH connection using configured authentication method
        
        Returns:
            bool: True if connection was successful, False otherwise
        """
        auth_method = config.get('HPC', 'auth_method', 'key')
        
        try:
            self.connection = paramiko.SSHClient()
            self.connection.load_system_host_keys()
            self.connection.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            if auth_method == 'key':
                key_file = Path(config.get('HPC', 'ssh_key_dir')) / config.get('HPC', 'ssh_key')
                private_key = paramiko.RSAKey.from_private_key_file(str(key_file))
                self.connection.connect(
                    hostname=self.host,
                    username=self.username,
                    pkey=private_key
                )
            else:  # password auth
                password = config.get('HPC', 'password')
                self.connection.connect(
                    hostname=self.host,
                    username=self.username,
                    password=password
                )
            return True
        except Exception as e:
            print(f"SSH connection failed: {str(e)}")
            return False
        
    def execute_command(self, command: str) -> str:
        """Execute a command on the remote system
        
        Args:
            command: Command to execute
            
        Returns:
            str: Command output
            
        Raises:
            RuntimeError: If no connection is established
        """
        if not self.connection:
            raise RuntimeError("SSH connection not established")
            
        stdin, stdout, stderr = self.connection.exec_command(command)
        output = stdout.read().decode().strip()
        error = stderr.read().decode().strip()
        
        if error:
            output += f"\nError: {error}"
            
        return output
        
    def disconnect(self):
        """Close the SSH connection"""
        if self.connection:
            self.connection.close()
