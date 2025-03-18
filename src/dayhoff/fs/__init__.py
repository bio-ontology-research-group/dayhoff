"""File system exploration tools for bioinformatics data.

This package provides functionality for:
- File inspection (head, tail, grep)
- Bioinformatics file format detection
- Streaming access to large files
- Statistics generation for common file types
"""
from .base import BaseFileSystem
from .local import LocalFileSystem
from .file_inspector import FileInspector
from .streaming import FileStreamer
from .stats import FileStats
from .format_detector import FileFormatDetector

__all__ = [
    'BaseFileSystem',
    'LocalFileSystem',
    'FileInspector',
    'FileStreamer',
    'FileStats',
    'FileFormatDetector'
]
