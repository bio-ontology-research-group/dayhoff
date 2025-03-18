import os
from typing import Iterator

class BioDataExplorer:
    """File system explorer for bioinformatics data"""
    
    def __init__(self, root_path):
        self.root = root_path
    
    def find_sequence_files(self) -> Iterator[str]:
        """Find biological sequence files in the directory tree"""
        # TODO: Implement efficient file search
        for root, _, files in os.walk(self.root):
            for file in files:
                if file.endswith(('.fasta', '.fastq', '.fa')):
                    yield os.path.join(root, file)

# TODO: Add more file system utilities
