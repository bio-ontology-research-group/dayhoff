import os
from typing import Iterator
import logging # Added logging

# Configure logging for this module
logger = logging.getLogger(__name__)

class BioDataExplorer:
    """File system explorer for bioinformatics data"""

    def __init__(self, root_path: str = '.'): # Added default root_path
        if not os.path.isdir(root_path):
            raise ValueError(f"Root path '{root_path}' is not a valid directory.")
        self.root = root_path
        logger.info(f"BioDataExplorer initialized with root: {self.root}")

    def find_sequence_files(self) -> Iterator[str]:
        """Find biological sequence files in the directory tree"""
        logger.info(f"Searching for sequence files in {self.root}")
        count = 0
        # Define common sequence file extensions
        sequence_extensions = ('.fasta', '.fastq', '.fa', '.fna', '.ffn', '.faa', '.frn', '.fq')
        try:
            for root, _, files in os.walk(self.root):
                for file in files:
                    # Check if the file ends with any of the sequence extensions
                    if file.lower().endswith(sequence_extensions):
                        full_path = os.path.join(root, file)
                        logger.debug(f"Found potential sequence file: {full_path}")
                        yield full_path
                        count += 1
        except Exception as e:
            logger.error(f"Error during file search in {self.root}: {e}", exc_info=True)
            # Re-raise the exception or handle it as appropriate
            raise
        logger.info(f"Found {count} sequence files.")

# TODO: Add more file system utilities like finding alignment files, VCFs, etc.
