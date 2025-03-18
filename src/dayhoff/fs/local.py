import subprocess
from pathlib import Path
from typing import List, Iterator, Optional
from .base import BaseFileSystem

class LocalFileSystem(BaseFileSystem):
    """Local filesystem implementation using system commands"""
    
    def _run_command(self, command: str) -> List[str]:
        """Run a shell command and return output lines"""
        result = subprocess.run(command, shell=True, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"Command failed: {command}\n{result.stderr}")
        return result.stdout.splitlines()
        
    def head(self, file_path: str, lines: int = 10) -> List[str]:
        """Get the first n lines of a file using head command"""
        full_path = self.root / file_path
        return self._run_command(f"head -n {lines} {full_path}")
        
    def tail(self, file_path: str, lines: int = 10) -> List[str]:
        """Get the last n lines of a file using tail command"""
        full_path = self.root / file_path
        return self._run_command(f"tail -n {lines} {full_path}")
        
    def grep(self, file_path: str, pattern: str) -> List[str]:
        """Search for a pattern in a file using grep command"""
        full_path = self.root / file_path
        return self._run_command(f"grep '{pattern}' {full_path}")
        
    def stream(self, file_path: str) -> Iterator[str]:
        """Stream lines from a file using cat command"""
        full_path = self.root / file_path
        process = subprocess.Popen(
            f"cat {full_path}",
            shell=True,
            stdout=subprocess.PIPE,
            text=True
        )
        for line in process.stdout:
            yield line.strip()
                
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
