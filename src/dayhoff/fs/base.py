from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Iterator, Optional
from ..config import config

class BaseFileSystem(ABC):
    """Abstract base class for filesystem operations"""
    
    def __init__(self):
        self.root = Path(config.get('FILESYSTEM', 'local_root'))
        if config.get('FILESYSTEM', 'mode') == 'remote':
            self.root = Path(config.get('FILESYSTEM', 'remote_root'))
    
    @abstractmethod
    def head(self, file_path: str, lines: int = 10) -> List[str]:
        """Get the first n lines of a file"""
        pass
        
    @abstractmethod
    def tail(self, file_path: str, lines: int = 10) -> List[str]:
        """Get the last n lines of a file"""
        pass
        
    @abstractmethod
    def grep(self, file_path: str, pattern: str) -> List[str]:
        """Search for a pattern in a file"""
        pass
        
    @abstractmethod
    def stream(self, file_path: str) -> Iterator[str]:
        """Stream lines from a file"""
        pass
        
    @abstractmethod
    def get_stats(self, file_path: str) -> dict:
        """Get file statistics"""
        pass
        
    @abstractmethod
    def detect_format(self, file_path: str) -> Optional[str]:
        """Detect bioinformatics file format"""
        pass
