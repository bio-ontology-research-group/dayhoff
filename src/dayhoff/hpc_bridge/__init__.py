"""HPC Bridge component for remote HPC access and management.

This package provides functionality for:
- SSH connection management
- Slurm job submission and monitoring
- File synchronization between local and remote systems
- Secure credential management
"""
from .ssh_manager import SSHManager
from .slurm_manager import SlurmManager
from .file_sync import FileSynchronizer
from .credentials import CredentialManager

__all__ = ['SSHManager', 'SlurmManager', 'FileSynchronizer', 'CredentialManager']
