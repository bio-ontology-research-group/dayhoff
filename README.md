# Dayhoff Bioinformatics Assistant

Dayhoff is a dual-interface (CLI/Jupyter) bioinformatics assistant system designed for:

- Reproducible research with Git-centric event tracking
- HPC/Slurm integration with remote SSH capabilities
- Intelligent file system exploration for bioinformatics data
- AI-powered analysis suggestions
- Retrieval-Augmented Generation (RAG) for biological entities
- Workflow generation (CWL and Nextflow) with Singularity support
- HPC module system awareness

## Installation

```bash
pip install -e .
```

## Usage

### CLI Interface
```bash
dayhoff explore /path/to/data
dayhoff generate-workflow --workflow-type cwl
```

### Jupyter Notebook
```python
from dayhoff.notebook import DayhoffKernel
kernel = DayhoffKernel()
```

## Documentation

See the [docs](docs/) directory for detailed documentation.

## Contributing

Contributions are welcome! Please see our contribution guidelines.
