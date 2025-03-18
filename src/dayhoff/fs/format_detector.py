from typing import Optional

class FileFormatDetector:
    """Detects bioinformatics file formats"""
    
    def detect(self, file_path: str) -> Optional[str]:
        """Detect the format of a bioinformatics file
        
        Args:
            file_path: Path to the file to detect
            
        Returns:
            str: Detected file format (e.g., 'fasta', 'fastq', 'vcf')
        """
        # TODO: Add C/C++ extension for better performance
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
