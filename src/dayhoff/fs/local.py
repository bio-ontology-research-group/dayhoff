import gzip
import bz2
import lzma
from pathlib import Path
from typing import List, Iterator, Optional
from .base import BaseFileSystem

class LocalFileSystem(BaseFileSystem):
    """Local filesystem implementation"""
    
    def _get_open_function(self, file_path: str):
        """Determine the appropriate open function based on file extension"""
        if file_path.endswith('.gz'):
            return gzip.open
        elif file_path.endswith('.bz2'):
            return bz2.open
        elif file_path.endswith('.xz'):
            return lzma.open
        return open
        
    def head(self, file_path: str, lines: int = 10) -> List[str]:
        """Get the first n lines of a file"""
        full_path = self.root / file_path
        with self._get_open_function(str(full_path))(full_path, 'rt') as f:
            return [next(f) for _ in range(lines)]
        
    def tail(self, file_path: str, lines: int = 10) -> List[str]:
        """Get the last n lines of a file"""
        full_path = self.root / file_path
        with self._get_open_function(str(full_path))(full_path, 'rt') as f:
            return list(f)[-lines:]
        
    def grep(self, file_path: str, pattern: str) -> List[str]:
        """Search for a pattern in a file"""
        import re
        regex = re.compile(pattern)
        full_path = self.root / file_path
        with self._get_open_function(str(full_path))(full_path, 'rt') as f:
            return [line for line in f if regex.search(line)]
        
    def stream(self, file_path: str) -> Iterator[str]:
        """Stream lines from a file"""
        full_path = self.root / file_path
        with self._get_open_function(str(full_path))(full_path, 'rt') as f:
            for line in f:
                yield line
                
    def get_stats(self, file_path: str) -> dict:
        """Get file statistics"""
        full_path = self.root / file_path
        stats = {
            'size': full_path.stat().st_size,
            'modified': full_path.stat().st_mtime,
            'created': full_path.stat().st_ctime
        }
        return stats
        
    def detect_format(self, file_path: str) -> Optional[str]:
        """Detect bioinformatics file format"""
        full_path = self.root / file_path
        with open(full_path, 'r') as f:
            first_line = f.readline()
            
        if first_line.startswith('>'):
            return 'fasta'
        elif first_line.startswith('@'):
            return 'fastq'
        elif first_line.startswith('##fileformat=VCF'):
            return 'vcf'
        elif first_line.startswith('##gff-version'):
            return 'gff'
        return None
