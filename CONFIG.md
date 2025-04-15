# Dayhoff Configuration (`dayhoff.cfg`)

This document outlines the configuration settings used by the Dayhoff application. These settings control various aspects of its operation, including logging, data storage, HPC connections, and workflow management.

## Configuration File

*   **Location**: By default, Dayhoff searches for the configuration file at `~/.config/dayhoff/dayhoff.cfg`. The `~` represents the user's home directory.
*   **Environment Variable**: You can override the default location by setting the `DAYHOFF_CONFIG_PATH` environment variable to the desired file path.
*   **Creation**: If the configuration file is not found at startup, Dayhoff will automatically create one with default settings at the default location.
*   **Format**: The file uses the standard INI format.
    *   Sections are defined using square brackets, e.g., `[SectionName]`.
    *   Settings within sections are key-value pairs, e.g., `key = value`.
    *   Comments begin with `#` or `;`. Inline comments using `;` after a value are also supported.

## Configuration Sections and Options

### `[DEFAULT]`

General application-wide settings.

*   **`log_level`**
    *   **Description**: Controls the minimum severity level of messages that Dayhoff will log. Lower levels are more verbose.
    *   **Allowed Values**: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`
    *   **Default**: `INFO`

*   **`data_dir`**
    *   **Description**: Specifies the root directory where Dayhoff stores its operational data, such as temporary files or downloaded resources.
    *   **Default**: `~/dayhoff_data`

### `[HPC]`

Settings for connecting to and interacting with High-Performance Computing (HPC) clusters via SSH.

*   **`default_host`**
    *   **Description**: The hostname or IP address of the target HPC cluster's login node. This is essential for most HPC-related commands.
    *   **Default**: (empty string)

*   **`username`**
    *   **Description**: The username used for logging into the HPC cluster.
    *   **Default**: (empty string)

*   **`auth_method`**
    *   **Description**: The method used for SSH authentication. `key`-based authentication is generally more secure and recommended. If `password` is used, Dayhoff might prompt for it or attempt retrieval from the system keyring (see `credential_system`).
    *   **Allowed Values**: `key`, `password`
    *   **Default**: `key`

*   **`ssh_key_dir`**
    *   **Description**: The directory path where your SSH private key files are stored. Relevant only when `auth_method` is `key`.
    *   **Default**: `~/.ssh`

*   **`ssh_key`**
    *   **Description**: The filename of the specific private SSH key (within `ssh_key_dir`) to use for authentication.
    *   **Default**: `id_rsa`

*   **`known_hosts`**
    *   **Description**: The path to the SSH `known_hosts` file, which is used to verify the authenticity of the remote HPC host and prevent man-in-the-middle attacks.
    *   **Default**: `~/.ssh/known_hosts`

*   **`remote_root`**
    *   **Description**: Specifies a directory on the remote HPC system to change into immediately after a successful SSH connection. Use `.` to remain in the default login directory.
    *   **Default**: `.`

*   **`credential_system`**
    *   **Description**: Defines a base name for the service entry when storing or retrieving passwords using the operating system's credential manager (keyring). The actual service name typically combines this base name with the HPC hostname.
    *   **Default**: `dayhoff_hpc`

### `[WORKFLOWS]`

Settings related to the generation and execution specifics of bioinformatics workflows.

*   **`default_workflow_type`**
    *   **Description**: Sets the default workflow language (e.g., CWL, Nextflow) that Dayhoff will use when generating new workflow definitions (e.g., via the `/wf_gen` command).
    *   **Allowed Values**: `cwl`, `nextflow`, `snakemake`, `wdl`
    *   **Default**: `cwl`

*   **`cwl_default_executor`**
    *   **Description**: Specifies the default tool or execution engine to be used for running workflows written in Common Workflow Language (CWL). This setting informs external scripts or tools that execute the generated CWL.
    *   **Allowed Values**: `cwltool`, `toil`, `cwl-runner`, `arvados-cwl-runner`
    *   **Default**: `cwltool`

*   **`nextflow_default_executor`**
    *   **Description**: Defines the default execution environment or profile for Nextflow workflows. Nextflow often uses internal configuration (`nextflow.config`) or command-line profiles (`-profile`) to manage execution backends (like `local`, `slurm`, `awsbatch`). This setting provides a default hint for execution scripts.
    *   **Allowed Values**: `local`, `slurm`, `sge`, `lsf`, `pbs`, `awsbatch`, `google-lifesciences`
    *   **Default**: `local`

*   **`snakemake_default_executor`**
    *   **Description**: Specifies the default backend for executing Snakemake workflows. This often corresponds to command-line options like `--profile` or specific execution environment flags (e.g., `--kubernetes`, `--google-lifesciences`).
    *   **Allowed Values**: `local`, `slurm`, `drmaa`, `kubernetes`, `google-lifesciences`
    *   **Default**: `local`

*   **`wdl_default_executor`**
    *   **Description**: Sets the default execution engine for workflows written in Workflow Description Language (WDL).
    *   **Allowed Values**: `cromwell`, `miniwdl`, `dxwdl`
    *   **Default**: `cromwell`

## Modifying the Configuration

There are two primary ways to change Dayhoff's configuration:

1.  **Direct File Editing**: You can open the `dayhoff.cfg` file in a text editor and modify the values directly. Save the file for the changes to take effect on the next Dayhoff startup or when the configuration is reloaded.

2.  **Using the REPL `/config` Command**: Within the Dayhoff interactive REPL, you can manage settings dynamically:
    *   `/config show`: Display all current configuration settings.
    *   `/config show <section>`: Display settings for a specific section (e.g., `/config show HPC`).
    *   `/config show ssh`: Display the interpreted SSH settings derived from the `[HPC]` section.
    *   `/config get <section> <key>`: Retrieve the current value of a specific setting (e.g., `/config get DEFAULT log_level`).
    *   `/config set <section> <key> <value>`: Change the value of a setting. This command also automatically saves the entire configuration file (e.g., `/config set WORKFLOWS default_workflow_type nextflow`).
    *   `/config save`: Manually trigger saving the current configuration state to the file.

    Use `/help config` within the REPL for more detailed command usage and examples.
