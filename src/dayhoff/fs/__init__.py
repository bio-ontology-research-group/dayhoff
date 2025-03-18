"""File system exploration tools for bioinformatics data.

This package provides functionality for:
- File inspection (head, tail, grep)
- Bioinformatics file format detection
- Streaming access to large files
- Statistics generation for common file types
"""
from .file_inspector import FileInspector
from .format_detector import FileFormatDetector
from .streaming import FileStreamer
from .stats import FileStats

__all__ = ['FileInspector', 'FileFormatDetector', 'FileStreamer', 'FileStats']
