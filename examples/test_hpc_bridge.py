from unittest.mock import MagicMock
from dayhoff.hpc_bridge import SSHManager, SlurmManager

def test_hpc_bridge():
    print("Testing HPC Bridge functionality...\n")
    
    # Mock SSH connection
    print("1. Establishing mock SSH connection...")
    ssh_manager = SSHManager("hpc.example.com", "testuser")
    ssh_manager.connect = MagicMock(return_value=True)
    ssh_manager.execute_command = MagicMock(return_value="hello")
    
    if ssh_manager.connect():
        print("  ✓ SSH connection established")
    else:
        print("  ✗ Failed to establish SSH connection")
        return
    
    # Test command execution
    print("\n2. Testing command execution...")
    output = ssh_manager.execute_command("echo hello")
    print(f"  Command output: {output}")
    
    # Test Slurm job submission
    print("\n3. Testing Slurm job submission...")
    slurm_manager = SlurmManager(ssh_manager)
    job_id = slurm_manager.submit_job("echo hello", {})
    print(f"  Submitted job with ID: {job_id}")
    
    # Test job status
    print("\n4. Checking job status...")
    status = slurm_manager.get_job_status(job_id)
    print(f"  Job status: {status['status']}")
    
    print("\nHPC Bridge test completed successfully!")

if __name__ == "__main__":
    test_hpc_bridge()
