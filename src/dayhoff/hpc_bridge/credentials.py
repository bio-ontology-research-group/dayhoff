import keyring  # TODO: Add to requirements
from typing import Optional
from ..config import config

class CredentialManager:
    """Manages secure storage and retrieval of HPC credentials"""
    
    def __init__(self, system_name: Optional[str] = None):
        system_name = system_name or config.get('HPC', 'credential_system', 'dayhoff_hpc')
        """Initialize credential manager for a specific system
        
        Args:
            system_name: Name to use for credential storage
        """
        self.system_name = system_name
        
    def store_credentials(self, username: str, password: str):
        """Store credentials securely
        
        Args:
            username: HPC username
            password: HPC password
        """
        keyring.set_password(self.system_name, username, password)
        
    def get_password(self, username: str) -> Optional[str]:
        """Retrieve stored password
        
        Args:
            username: HPC username
            
        Returns:
            str: Stored password if found, None otherwise
        """
        return keyring.get_password(self.system_name, username)
