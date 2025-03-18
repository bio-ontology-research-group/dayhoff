from typing import Iterator
import gzip
import bz2
import lzma

class FileStreamer:
    """Provides streaming access to large files"""
    
    def __init__(self, file_path: str):
        """Initialize with a file path
        
        Args:
            file_path: Path to the file to stream
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
        
    def stream(self) -> Iterator[str]:
        """Stream lines from a file
        
        Yields:
            Lines from the file
        """
        # TODO: Add C/C++ extension for better performance
        with self._open_fn(self.file_path, 'rt') as f:
            for line in f:
                yield line
