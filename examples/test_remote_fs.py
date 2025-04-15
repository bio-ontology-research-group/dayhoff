from dayhoff.hpc_bridge import SSHManager
# Removed unused import: from dayhoff.fs import FileFormatDetector
from dayhoff.config import DayhoffConfig # To get SSH config
import os
import logging

# Configure logging for the test script
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Common bioinformatics file extensions (can be expanded)
BIOINFO_EXTENSIONS = {
    '.fasta': 'FASTA sequence',
    '.fa': 'FASTA sequence',
    '.fastq': 'FASTQ sequence',
    '.fq': 'FASTQ sequence',
    '.vcf': 'Variant Call Format',
    '.bam': 'Binary Alignment Map',
    '.sam': 'Sequence Alignment Map',
    '.gff': 'General Feature Format',
    '.gtf': 'Gene Transfer Format',
    '.bed': 'Browser Extensible Data'
}

def explore_remote_fs() -> bool:
    """
    Tests remote file system interaction via SSH.

    Requires SSH configuration to be set up correctly in the Dayhoff config.
    1. Initializes DayhoffConfig to get SSH parameters.
    2. Initializes SSHManager with the configuration.
    3. Connects to the remote host via SSH.
    4. Executes `ls -l` and `ls` commands remotely in the configured directory.
    5. Parses the `ls` output to identify potential bioinformatics files
       based on their extensions using the BIOINFO_EXTENSIONS map.
    6. Disconnects the SSH session.

    Returns:
        bool: True if all steps complete successfully, False otherwise.
    """
    logger.info("--- Testing Remote File System Exploration via SSH ---")
    ssh = None # Initialize ssh variable

    # 1. Initialize Config and SSH Manager
    try:
        logger.info("Loading Dayhoff configuration...")
        config = DayhoffConfig()
        # --- Add Debugging ---
        config_path = config._get_config_path() # Get the path being used
        logger.info(f"DayhoffConfig using configuration file: {config_path}")
        # --- End Debugging ---

        ssh_config = config.get_ssh_config()
        # --- Add Debugging ---
        logger.info(f"Value returned by config.get_ssh_config(): {ssh_config}")
        # --- End Debugging ---

        if not ssh_config or not ssh_config.get('host'):
            logger.error("✗ SSH configuration missing or incomplete in Dayhoff config.")
            print("Error: SSH host not configured. Please set up [HPC] section in your Dayhoff config.")
            return False
        logger.info(f"Found SSH config for host: {ssh_config.get('host')}")

        logger.info("Initializing SSHManager...")
        # Assuming SSHManager takes the config dictionary
        ssh = SSHManager(ssh_config=ssh_config)
        logger.info("✓ SSHManager initialized.")
    except Exception as e:
        logger.error(f"✗ Error during initialization: {e}", exc_info=True)
        print(f"Error during initialization: {e}")
        return False

    # 2. Establish SSH connection
    logger.info(f"Attempting SSH connection to {ssh.host} as {ssh.username}...")
    try:
        if not ssh.connect():
            logger.error("✗ SSH connection failed. Check credentials, keys, and host availability.")
            print("Error: SSH connection failed. Check logs and configuration.")
            return False
        logger.info("✓ SSH connection established successfully.")
        print("\n✓ SSH connection established.") # Also print to stdout for REPL visibility
    except Exception as e:
        logger.error(f"✗ Exception during SSH connection: {e}", exc_info=True)
        print(f"Error during SSH connection: {e}")
        return False

    # 3. Execute remote commands
    remote_dir = ssh_config.get('remote_root', '.') # Use remote_root from config or default to home dir '.'
    logger.info(f"\nExecuting 'ls -l {remote_dir}' on remote host...")
    try:
        ls_l_output = ssh.execute_command(f"ls -l {remote_dir}")
        logger.info(f"✓ 'ls -l' executed. Output:\n---\n{ls_l_output.strip()}\n---")
        print(f"\nListing remote directory ('{remote_dir}'):")
        print(ls_l_output.strip())
    except Exception as e:
        logger.error(f"✗ Error executing 'ls -l': {e}", exc_info=True)
        print(f"Error executing remote command 'ls -l': {e}")
        ssh.disconnect()
        return False

    logger.info(f"\nExecuting 'ls {remote_dir}' to get file names...")
    try:
        # Execute 'ls' without -l to get just filenames
        ls_output = ssh.execute_command(f"ls {remote_dir}")
        files = ls_output.splitlines() # Split output into lines (filenames)
        logger.info(f"✓ 'ls' executed. Found {len(files)} entries.")
    except Exception as e:
        logger.error(f"✗ Error executing 'ls': {e}", exc_info=True)
        print(f"Error executing remote command 'ls': {e}")
        ssh.disconnect()
        return False

    # 4. Identify bioinformatics files by extension
    print(f"\nIdentifying potential bioinformatics files in '{remote_dir}' by extension:")
    logger.info("Identifying files by known bioinformatics extensions...")
    found_bioinfo_files = 0
    if not files:
        print("  No files found in the directory.")
    else:
        for file in files:
            if not file: continue # Skip empty lines if any
            # Get the file extension
            _, ext = os.path.splitext(file)
            ext_lower = ext.lower()
            # Check against known extensions
            if ext_lower in BIOINFO_EXTENSIONS:
                file_type = BIOINFO_EXTENSIONS[ext_lower]
                print(f"  - {file}: Found ({file_type})")
                logger.info(f"  Identified: {file} as {file_type}")
                found_bioinfo_files += 1
            else:
                # Optionally log unknown files at a lower level (e.g., DEBUG)
                # logger.debug(f"  Unknown format (extension: {ext}) for file: {file}")
                pass # Don't print every unknown file to keep output clean

    logger.info(f"Found {found_bioinfo_files} potential bioinformatics files based on extension.")
    if found_bioinfo_files == 0 and files:
         print("  No files with recognized bioinformatics extensions found.")

    # 5. Disconnect
    logger.info("\nDisconnecting SSH session...")
    ssh.disconnect()
    logger.info("✓ SSH session disconnected.")
    print("\n✓ SSH session disconnected.")

    print("\n--- Remote file system exploration test completed successfully! ---")
    return True

if __name__ == "__main__":
    if not explore_remote_fs():
        print("\nTest encountered errors.")
        exit(1) # Exit with non-zero code on failure
    else:
        print("\nTest finished.")
        exit(0) # Exit with zero code on success
