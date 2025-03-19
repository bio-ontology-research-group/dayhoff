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
        
        # Generate workflow CWL
        cwl_gen = CWLGenerator()
        workflow_cwl = cwl_gen.generate(workflow)
        workflow_path = Path(tmpdir) / "workflow.cwl"
        with open(workflow_path, "w") as f:
            f.write(workflow_cwl)
        
        # Create input YAML
        input_yaml = """message: "Hello Remote World"
"""
        input_path = Path(tmpdir) / "inputs.yml"
        with open(input_path, "w") as f:
            f.write(input_yaml)
        
        # Create remote temp directory
        remote_tmp = ssh.execute_command("mktemp -d").strip()
        print(f"Created remote temp directory: {remote_tmp}")
        
        # Upload files to remote
        files_to_upload = [echo_path, workflow_path, input_path]
        if not file_sync.upload_files(
            [str(f) for f in files_to_upload],
            remote_tmp
        ):
            print("✗ File upload failed")
            return False
        print("✓ Files uploaded successfully")
        
        # Execute workflow remotely
        print("Executing workflow remotely...")
        cmd = f"cd {remote_tmp} && cwl-runner workflow.cwl inputs.yml"
        result = ssh.execute_command(cmd)
        
        # Parse and verify output
        print("\nWorkflow output:")
        print(result)
        
        try:
            # The output is a JSON object with the file location
            import json
            output = json.loads(result)
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
        except (json.JSONDecodeError, KeyError) as e:
            print(f"\nRemote workflow test failed - error parsing output: {str(e)}")
            return False
        finally:
            # Clean up remote temp directory
            ssh.execute_command(f"rm -rf {remote_tmp}")
            print("Cleaned up remote temp directory")

if __name__ == "__main__":
    test_remote_workflow()
