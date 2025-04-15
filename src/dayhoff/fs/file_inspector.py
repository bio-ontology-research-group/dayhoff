from typing import List
from .base import BaseFileSystem
# Removed incorrect import: from ..config import config
import os

class FileInspector:
    """Provides file inspection utilities using system commands"""

    def __init__(self, filesystem: BaseFileSystem):
        """Initialize with a filesystem implementation

        Args:
            filesystem: BaseFileSystem implementation (local or remote)
        """
        self.fs = filesystem

    def head(self, file_path: str, lines: int = 10) -> List[str]:
        """Get the first n lines of a file"""
        # Use os.path.abspath to ensure consistent path format if needed,
        # but the underlying fs implementation should handle path resolution.
        # Consider if abspath is always appropriate, especially for remote fs.
        # For now, keeping it as it was.
        return self.fs.head(os.path.abspath(file_path), lines)

    def tail(self, file_path: str, lines: int = 10) -> List[str]:
        """Get the last n lines of a file"""
        return self.fs.tail(os.path.abspath(file_path), lines)

    def grep(self, file_path: str, pattern: str) -> List[str]:
        """Search for a pattern in a file"""
        return self.fs.grep(os.path.abspath(file_path), pattern)
