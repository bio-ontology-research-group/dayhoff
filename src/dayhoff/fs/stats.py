from typing import Dict, Any
from collections import defaultdict

class FileStats:
    """Generates statistics for bioinformatics files"""
    
    def __init__(self, file_path: str):
        """Initialize with a file path
        
        Args:
            file_path: Path to the file to analyze
        """
        self.file_path = file_path
        
    def get_stats(self) -> Dict[str, Any]:
        """Get basic statistics about the file
        
        Returns:
            Dictionary of statistics
        """
        # TODO: Add C/C++ extension for better performance
        stats = {
            'line_count': 0,
            'sequence_count': 0,
            'base_count': 0,
            'quality_scores': defaultdict(int)
        }
        
        with open(self.file_path, 'r') as f:
            for line in f:
                stats['line_count'] += 1
                if line.startswith('>'):
                    stats['sequence_count'] += 1
                elif not line.startswith('@') and not line.startswith('+'):
                    stats['base_count'] += len(line.strip())
                    
        return stats
