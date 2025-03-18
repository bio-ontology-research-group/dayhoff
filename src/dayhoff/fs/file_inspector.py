from typing import List
import gzip
import bz2
import lzma

class FileInspector:
    """Provides file inspection utilities like head, tail, and grep"""
    
    def __init__(self, file_path: str):
        """Initialize with a file path
        
        Args:
            file_path: Path to the file to inspect
        """
        self.file_path = file_path
        self._open_fn = self._get_open_function()
        
    def _get_open_function(self):
        """Determine the appropriate open function based on file extension"""
        if self.file_path.endswith('.gz'):
            return gzip.open
        elif self.file_path.endswith('.bz2'):
            return bz2.open
        elif self.file_path.endswith('.xz'):
            return lzma.open
        return open
        
    def head(self, lines: int = 10) -> List[str]:
        """Get the first n lines of a file
        
        Args:
            lines: Number of lines to return
            
        Returns:
            List of lines
        """
        # TODO: Add C/C++ extension for better performance on large files
        with self._open_fn(self.file_path, 'rt') as f:
            return [next(f) for _ in range(lines)]
        
    def tail(self, lines: int = 10) -> List[str]:
        """Get the last n lines of a file
        
        Args:
            lines: Number of lines to return
            
        Returns:
            List of lines
        """
        # TODO: Add C/C++ extension for better performance on large files
        with self._open_fn(self.file_path, 'rt') as f:
            return list(f)[-lines:]
        
    def grep(self, pattern: str) -> List[str]:
        """Search for a pattern in a file
        
        Args:
            pattern: Pattern to search for
            
        Returns:
            List of matching lines
        """
        # TODO: Add C/C++ extension for better performance on large files
        import re
        regex = re.compile(pattern)
        with self._open_fn(self.file_path, 'rt') as f:
            return [line for line in f if regex.search(line)]
