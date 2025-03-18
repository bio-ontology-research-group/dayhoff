from typing import Optional
from dayhoff.hpc_bridge import SSHManager

class FileFormatDetector:
    """Detects bioinformatics file formats"""
    
    def __init__(self, ssh_manager: Optional[SSHManager] = None):
        """Initialize with optional SSH manager for remote detection"""
        self.ssh = ssh_manager
        
    def detect(self, file_path: str) -> Optional[str]:
        """Detect the format of a bioinformatics file
        
        Args:
            file_path: Path to the file to detect
            
        Returns:
            str: Detected file format (e.g., 'fasta', 'fastq', 'vcf')
        """
        try:
            if self.ssh:
                # Remote file detection
                first_line = self.ssh.execute_command(f"head -n 1 {file_path}")
            else:
                # Local file detection
                with open(file_path, 'r') as f:
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
        except Exception:
            return None
