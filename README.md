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

# Copy example config file to your home directory
cp examples/dayhoff.cfg.example ~/.config/dayhoff/dayhoff.cfg
```

## Configuration

Dayhoff uses a centralized configuration system stored in `~/.config/dayhoff/dayhoff.cfg`. The configuration file is divided into sections:

- `[DEFAULT]`: General system settings
- `[HPC]`: HPC connection settings
- `[LOGGING]`: Logging configuration
- `[WORKFLOWS]`: Workflow defaults

You can modify the configuration file directly or use the Python API:

```python
from dayhoff.config import config

# Get a config value
log_level = config.get('LOGGING', 'level')

# Set a config value
config.set('HPC', 'default_host', 'new.hpc.example.com')
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

## Workflow Generation

Dayhoff supports generating workflows in both CWL and Nextflow formats. The workflow system includes:

- Abstract workflow representation
- CWL generator
- Nextflow generator
- Singularity container integration
- Environment tracking for reproducibility

Example usage:

```python
from dayhoff.workflows import Workflow, WorkflowStep, CWLGenerator, NextflowGenerator

# Create workflow
workflow = Workflow("my_workflow")

# Add steps
step1 = WorkflowStep(
    name="qc",
    tool="fastqc",
    inputs={"input_file": "File"},
    outputs={"output_html": "File"},
    container="quay.io/biocontainers/fastqc:0.11.9--0",
    requirements=[]
)

step2 = WorkflowStep(
    name="report",
    tool="multiqc",
    inputs={"input_dir": "Directory"},
    outputs={"report_html": "File"},
    container="quay.io/biocontainers/multiqc:1.11--pyhdfd78af_0",
    requirements=[]
)

workflow.add_step(step1)
workflow.add_step(step2, depends_on=["qc"])

# Generate CWL
cwl_gen = CWLGenerator()
cwl = cwl_gen.generate(workflow)
print(cwl)

# Generate Nextflow
nf_gen = NextflowGenerator()
nf = nf_gen.generate(workflow)
print(nf)
```

### Container Integration

Dayhoff integrates with Singularity containers for reproducible execution:

```python
from dayhoff.workflows import ContainerManager

# Add container definition
container_mgr = ContainerManager()
container_mgr.add_container("fastqc", """
Bootstrap: docker
From: quay.io/biocontainers/fastqc:0.11.9--0
""")

# Build container
container_mgr.build_container("fastqc")
```

## LLM Integration

The LLM integration layer provides a unified interface for interacting with language models. Key features:

- Support for multiple providers (OpenAI, Anthropic, etc.)
- Prompt templating and management
- Response parsing and validation
- Context management for multi-turn interactions
- Token usage tracking and budget management

Example usage:

```python
from dayhoff.llm import OpenAIClient, PromptManager, ResponseParser

# Initialize components
client = OpenAIClient()
prompt_manager = PromptManager()
response_parser = ResponseParser()

# Generate a prompt
prompt = prompt_manager.generate_prompt('command', {'input': 'Analyze this data'})

# Get response from LLM
response = client.generate(prompt)

# Parse and use the response
parsed = response_parser.parse_response(response['response'])
print(parsed['command'])
```

Configuration:

Add to your `~/.config/dayhoff/dayhoff.cfg`:

```ini
[LLM]
api_key = your_api_key
model = gpt-4
max_tokens = 4096
rate_limit = 60
```

## Usage

### CLI Interface
```bash
# Install CLI
pip install -e .

# Run a command
dayhoff execute test_command --param key=value
```

### Jupyter Notebook
1. Install the kernel:
```bash
python -m dayhoff.notebook.kernel install --user
```

2. Start Jupyter Notebook:
```bash
jupyter notebook
```

3. Select "Dayhoff" as the kernel when creating a new notebook

4. Run commands directly in notebook cells

## Documentation

See the [docs](docs/) directory for detailed documentation.

## Contributing

Contributions are welcome! Please see our contribution guidelines.
