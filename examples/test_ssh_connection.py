from dayhoff.hpc_bridge import SSHManager
from dayhoff.config import config # Import the global config object

def test_ssh_connection():
    print("Testing SSH connection...\n")

    # Get SSH configuration from the Dayhoff config
    ssh_config = config.get_ssh_config()
    if not ssh_config or not ssh_config.get('host'):
        print("✗ SSH configuration missing or incomplete (host not set). Please configure [HPC] section in dayhoff.cfg.")
        return False

    # Pass the configuration to SSHManager
    ssh_manager = SSHManager(ssh_config=ssh_config)

    if not ssh_manager.connect():
        print("✗ SSH connection failed")
        # Optionally print more details from ssh_manager if available
        return False

    print("✓ SSH connection established")

    # Execute test commands
    commands = [
        "echo 'Hello world'",
        "hostname",
        "uname -a"
    ]

    success = True
    for cmd in commands:
        print(f"\nExecuting: {cmd}")
        try:
            output = ssh_manager.execute_command(cmd)
            print(f"Output:\n{output}")
        except Exception as e:
            print(f"✗ Error executing command '{cmd}': {e}")
            success = False
            # Decide if we should stop on first error or continue
            # break # Uncomment to stop on first error

    ssh_manager.disconnect()

    if success:
        print("\nSSH connection test completed successfully!")
    else:
        print("\nSSH connection test completed with errors.")

    return success

if __name__ == "__main__":
    test_ssh_connection()
