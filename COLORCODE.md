# Dayhoff File Type Color Codes

This document outlines the color scheme used in Dayhoff command outputs (like `/ls`, `/fs_find_seq`) to highlight files relevant to bioinformatics analyses. Colors are applied using the `rich` library syntax.

## Color Philosophy

-   **Semantic Grouping:** Files representing similar types of biological data or stages in an analysis share the same or related colors.
-   **Readability:** Colors are chosen to be distinct and generally readable on common terminal backgrounds.
-   **Context:** Colors help quickly identify key data files within directory listings.

## Color Mappings

| File Category             | Extensions                                       | `rich` Style      | Rationale                                    |
| :------------------------ | :----------------------------------------------- | :---------------- | :------------------------------------------- |
| **Sequence (Raw Reads)**  | `.fastq`, `.fq`                                  | `bright_cyan`     | Raw input data, distinct color.              |
| **Sequence (Reference)**  | `.fasta`, `.fa`, `.fna`, `.ffn`, `.faa`, `.frn` | `cyan`            | Reference or assembled sequences.            |
| **Sequence (Alignment)**  | `.sam`, `.bam`, `.cram`                          | `dark_cyan`       | Processed alignment data.                    |
| **Annotation**            | `.gff`, `.gff3`, `.gtf`, `.bed`                  | `bright_magenta`  | Genomic features and annotations.            |
| **Variant Data**          | `.vcf`, `.bcf`                                   | `bright_red`      | Variant calls, highlighting differences.     |
| **Phylogenetics**         | `.nwk`, `.newick`, `.nex`, `.nexus`, `.phy`      | `bright_green`    | Tree structures.                             |
| **Tabular Data**          | `.csv`, `.tsv`, `.txt` (if tabular?)¹            | `yellow`          | Generic tables, metadata, results.           |
| **Scripts/Workflows**     | `.py`, `.sh`, `.cwl`, `.wdl`, `.nf`, `.smk`      | `blue`            | Code and workflow definitions.               |
| **Configuration/Metadata**| `.json`, `.yaml`, `.yml`, `.toml`, `.ini`, `.xml`| `bright_black`    | Configuration files.                         |
| **Compressed Archives**   | `.gz`, `.bz2`, `.zip`, `.tar`, `.tgz`, `.xz`     | `grey50`          | Indicates compression/archive (applied last).|
| **Directories**           | (Type, not extension)                            | `bold blue`       | Standard convention for directories.         |
| **Other/Default**         | (All other files)                                | `default`         | Standard terminal text color.                |

**Notes:**

1.  Coloring `.txt` as tabular is a heuristic; it might apply to non-tabular text files too.
2.  For compressed files (e.g., `.fasta.gz`), the primary type color (`cyan` for `.fasta`) should ideally be applied, with the compression color potentially modifying it or being less prominent. The current implementation primarily colors based on the *final* extension. More sophisticated logic could parse multiple extensions.
3.  The `rich` library handles the actual rendering based on terminal capabilities.

