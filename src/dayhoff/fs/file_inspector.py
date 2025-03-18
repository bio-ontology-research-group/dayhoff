from typing import List
from .base import BaseFileSystem
from ..config import config

class FileInspector:
    """Provides file inspection utilities like head, tail, and grep"""
    
    def __init__(self, filesystem: BaseFileSystem):
        """Initialize with a filesystem implementation
        
        Args:
            filesystem: BaseFileSystem implementation (local or remote)
        """
        self.fs = filesystem
        
    def head(self, file_path: str, lines: int = 10) -> List[str]:
        """Get the first n lines of a file"""
        return self.fs.head(file_path, lines)
        
    def tail(self, file_path: str, lines: int = 10) -> List[str]:
        """Get the last n lines of a file"""
        return self.fs.tail(file_path, lines)
        
    def grep(self, file_path: str, pattern: str) -> List[str]:
        """Search for a pattern in a file"""
        return self.fs.grep(file_path, pattern)
