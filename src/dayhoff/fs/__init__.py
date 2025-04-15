"""File system exploration tools for bioinformatics data.

This package provides functionality for:
- File inspection (head, tail, grep)
- Bioinformatics file format detection
- Streaming access to large files
- Statistics generation for common file types
- Exploring file systems for specific bioinformatics data
"""
from .base import BaseFileSystem
from .local import LocalFileSystem
# from .file_inspector import FileInspector # Assuming these exist or will be added
# from .streaming import FileStreamer
# from .stats import FileStats
# from .format_detector import FileFormatDetector
from .explorer import BioDataExplorer # Import the moved class

__all__ = [
    'BaseFileSystem',
    'LocalFileSystem',
    # 'FileInspector',
    # 'FileStreamer',
    # 'FileStats',
    # 'FileFormatDetector',
    'BioDataExplorer' # Add to __all__
]
