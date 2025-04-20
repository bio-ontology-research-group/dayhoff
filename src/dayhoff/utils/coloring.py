import os
from rich.text import Text

# --- File Coloring Logic ---
COLOR_MAP = {
    # Sequences (Raw)
    ".fastq": "bright_cyan", ".fq": "bright_cyan",
    # Sequences (Reference/Assembly)
    ".fasta": "cyan", ".fa": "cyan", ".fna": "cyan", ".ffn": "cyan", ".faa": "cyan", ".frn": "cyan",
    # Sequences (Alignment)
    ".sam": "dark_cyan", ".bam": "dark_cyan", ".cram": "dark_cyan",
    # Annotations
    ".gff": "bright_magenta", ".gff3": "bright_magenta", ".gtf": "bright_magenta", ".bed": "bright_magenta",
    # Variant Data
    ".vcf": "bright_red", ".bcf": "bright_red",
    # Phylogenetics
    ".nwk": "bright_green", ".newick": "bright_green", ".nex": "bright_green", ".nexus": "bright_green", ".phy": "bright_green",
    # Tabular Data
    ".csv": "yellow", ".tsv": "yellow", ".txt": "yellow", # Heuristic for .txt
    # Scripts/Workflows
    ".py": "blue", ".sh": "blue", ".cwl": "blue", ".wdl": "blue", ".nf": "blue", ".smk": "blue",
    # Config/Metadata
    ".json": "bright_black", ".yaml": "bright_black", ".yml": "bright_black", ".toml": "bright_black", ".ini": "bright_black", ".xml": "bright_black",
    # Compressed
    ".gz": "grey50", ".bz2": "grey50", ".zip": "grey50", ".tar": "grey50", ".tgz": "grey50", ".xz": "grey50",
}

def colorize_filename(filename: str, is_dir: bool = False) -> Text:
    """Applies semantic coloring to a filename using Rich Text."""
    if is_dir:
        return Text(filename, style="bold blue")
    else:
        _base, ext = os.path.splitext(filename)
        ext_lower = ext.lower()
        style = COLOR_MAP.get(ext_lower)
        # Handle double extensions like .fasta.gz
        if style is None and ext_lower in {".gz", ".bz2", ".xz"}:
            _base2, ext2 = os.path.splitext(_base)
            ext2_lower = ext2.lower()
            style = COLOR_MAP.get(ext2_lower) # Get style for inner extension
            if style is None:
                 style = COLOR_MAP.get(ext_lower, "default") # Fallback to compression style
        elif style is None:
             style = "default" # Default style if no match
        return Text(filename, style=style)

# --- End File Coloring Logic ---
