import os
import tempfile
import subprocess
from pathlib import Path
from dayhoff.workflows import Workflow, WorkflowStep, CWLGenerator
from dayhoff.hpc_bridge import SSHManager, FileSynchronizer

def test_remote_workflow():
    print("Testing remote workflow execution...\n")
    
    # Create a temporary directory for local files
    with tempfile.TemporaryDirectory() as tmpdir:
        # Initialize SSH connection
        ssh = SSHManager()
        if not ssh.connect():
            print("✗ SSH connection failed")
            return False
        print("✓ SSH connection established")
        
        # Initialize file synchronizer
        file_sync = FileSynchronizer(ssh)
        
        # Create workflow files locally
        workflow = Workflow("remote_test_workflow")
        
        # Create echo tool CWL
        echo_cwl = """#!/usr/bin/env cwl-runner
cwlVersion: v1.0
class: CommandLineTool
baseCommand: echo
inputs:
  message:
    type: string
    inputBinding:
      position: 1
outputs:
  output:
    type: stdout
"""
        
        # Write files locally
        echo_path = Path(tmpdir) / "echo.cwl"
        with open(echo_path, "w") as f:
            f.write(echo_cwl)
        
        # Add workflow step
        step = WorkflowStep(
            name="echo_step",
            tool="echo.cwl",
            inputs={"message": "string"},
            outputs={"output": "File"},
            container="alpine:latest",
            requirements=[]
        )
        workflow.add_step(step)
        
        # Create remote temp directory first
        remote_tmp = ssh.execute_command("mktemp -d").strip()
        print(f"Created remote temp directory: {remote_tmp}")

        # Generate workflow CWL with explicit paths
        cwl_gen = CWLGenerator()
        workflow_cwl = cwl_gen.generate(workflow)
        workflow_path = Path(tmpdir) / "workflow.cwl"
        
        # Add explicit import of echo.cwl
        workflow_cwl = f"""cwlVersion: v1.0
class: Workflow
inputs:
  message: string
outputs:
  output:
    type: File
    outputSource: echo_step/output
steps:
  echo_step:
    run: {remote_tmp}/echo.cwl
    in:
      message: message
    out: [output]
"""
        
        with open(workflow_path, "w") as f:
            f.write(workflow_cwl)
        
        # Create input YAML
        input_yaml = """message: "Hello Remote World"
"""
        input_path = Path(tmpdir) / "inputs.yml"
        with open(input_path, "w") as f:
            f.write(input_yaml)
        
        
        # Upload files to remote with detailed debugging
        files_to_upload = [echo_path, workflow_path, input_path]
        try:
            print("\nAttempting to upload files...")
            for f in files_to_upload:
                print(f"Uploading {f.name}...")
                # Use scp directly for more reliable transfer
                scp_cmd = f"scp {f} {ssh.username}@{ssh.host}:{remote_tmp}/{f.name}"
                result = subprocess.run(scp_cmd, shell=True, capture_output=True, text=True)
                
                if result.returncode != 0:
                    print(f"✗ Failed to upload {f.name}")
                    print("SCP error output:")
                    print(result.stderr)
                    return False
                print(f"✓ {f.name} uploaded successfully")
            
            # Verify files were uploaded
            print("\nVerifying uploaded files...")
            for f in files_to_upload:
                remote_path = f"{remote_tmp}/{f.name}"
                # Check file exists and has content
                check_cmd = f"test -s {remote_path} && echo exists || echo missing"
                result = ssh.execute_command(check_cmd).strip()
                if result != "exists":
                    print(f"✗ File verification failed for {f.name}")
                    # Show remote directory contents for debugging
                    print("Remote directory contents:")
                    print(ssh.execute_command(f"ls -l {remote_tmp}"))
                    return False
            
            print("✓ Files uploaded and verified successfully")
            
            # Verify remote directory contents
            print("\nRemote directory contents:")
            ls_output = ssh.execute_command(f"ls -l {remote_tmp}")
            print(ls_output)
            
            # Verify file sizes match
            print("\nVerifying file sizes:")
            for f in files_to_upload:
                local_size = os.path.getsize(f)
                remote_size = int(ssh.execute_command(f"stat -c%s {remote_tmp}/{f.name}").strip())
                print(f"{f.name}: local={local_size} bytes, remote={remote_size} bytes")
                if local_size != remote_size:
                    print(f"✗ Size mismatch for {f.name}")
                    return False
            
            print("✓ All file sizes match")
            
        except Exception as e:
            print(f"✗ Error during file upload and verification: {str(e)}")
            return False
        
        # Execute workflow remotely with full paths
        print("Executing workflow remotely...")
        remote_workflow = f"{remote_tmp}/workflow.cwl"
        remote_inputs = f"{remote_tmp}/inputs.yml"
        cmd = f"cwl-runner {remote_workflow} {remote_inputs}"
        result = ssh.execute_command(cmd)
        
        # Parse and verify output
        print("\nWorkflow output:")
        print(result)
        
        try:
            # Extract just the JSON portion from the output
            import json
            import re
            
            # Find the JSON object in the output
            json_match = re.search(r'\{.*\}', result, re.DOTALL)
            if not json_match:
                print("✗ Failed to find JSON output in workflow results")
                return False
                
            output = json.loads(json_match.group())
            output_file = output['output']['path']
            
            # Read the actual output file
            output_content = ssh.execute_command(f"cat {output_file}").strip()
            print(f"Actual output content: {output_content}")
            
            if output_content == "Hello Remote World":
                print("\nRemote workflow test completed successfully!")
                return True
            else:
                print("\nRemote workflow test failed - unexpected output content")
                return False
        except (json.JSONDecodeError, KeyError, AttributeError) as e:
            print(f"\nRemote workflow test failed - error parsing output: {str(e)}")
            return False
        finally:
            # Clean up remote temp directory
            ssh.execute_command(f"rm -rf {remote_tmp}")
            print("Cleaned up remote temp directory")

if __name__ == "__main__":
    test_remote_workflow()
