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

## Core Features

### HPC Bridge

The HPC Bridge component provides secure remote access to HPC systems with features for:

- SSH connection management
- Slurm job submission and monitoring
- File synchronization between local and remote systems
- Secure credential storage

Example usage:
```python
from dayhoff.hpc_bridge import SSHManager, SlurmManager

# Connect to HPC
ssh = SSHManager("hpc.example.com", "username")
ssh.connect(password="secure_password")

# Submit job
slurm = SlurmManager(ssh)
job_id = slurm.submit_job("echo hello", {"time": "00:01:00"})
```

### Git Event Tracking
Dayhoff includes a built-in git-based event tracking system that automatically records all significant actions in the system. This ensures full reproducibility of all analyses and workflows.

Example usage:
```python
from dayhoff.git_tracking import GitTracker

tracker = GitTracker()
tracker.record_event(
    event_type="analysis_started",
    metadata={"analysis_type": "variant_calling"}
)
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
