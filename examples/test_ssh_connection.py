from dayhoff.hpc_bridge import SSHManager

def test_ssh_connection():
    print("Testing SSH connection...\n")
    
    ssh_manager = SSHManager()
    
    if not ssh_manager.connect():
        print("✗ SSH connection failed")
        return False
    
    print("✓ SSH connection established")
    
    # Execute test commands
    commands = [
        "echo 'Hello world'",
        "hostname",
        "uname -a"
    ]
    
    for cmd in commands:
        print(f"\nExecuting: {cmd}")
        output = ssh_manager.execute_command(cmd)
        print(f"Output:\n{output}")
    
    ssh_manager.disconnect()
    print("\nSSH connection test completed successfully!")
    return True

if __name__ == "__main__":
    test_ssh_connection()
