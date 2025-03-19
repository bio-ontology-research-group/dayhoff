import os
import tempfile
import subprocess
from pathlib import Path
from dayhoff.workflows import Workflow, WorkflowStep, CWLGenerator, NextflowGenerator

def test_workflow():
    print("Testing workflow generation and execution...\n")
    
    # Create a temporary directory for the test
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a simple workflow
        workflow = Workflow("test_workflow")
        
        # Create a simple echo tool CWL
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
        
        # Write the echo tool CWL
        echo_path = Path(tmpdir) / "echo.cwl"
        with open(echo_path, "w") as f:
            f.write(echo_cwl)
        
        # Add a simple echo step
        step = WorkflowStep(
            name="echo_step",
            tool=str(echo_path),
            inputs={"message": "string"},
            outputs={"output": "File"},
            container="alpine:latest",
            requirements=[]
        )
        workflow.add_step(step)
        
        # Generate CWL
        cwl_gen = CWLGenerator()
        workflow_cwl = cwl_gen.generate(workflow)
        
        # Write the workflow CWL
        workflow_path = Path(tmpdir) / "workflow.cwl"
        with open(workflow_path, "w") as f:
            f.write(workflow_cwl)
        
        # Create input YAML
        input_yaml = """message: "Hello World"
"""
        input_path = Path(tmpdir) / "inputs.yml"
        with open(input_path, "w") as f:
            f.write(input_yaml)
        
        # Run the workflow using cwl-runner
        print("Executing workflow with cwl-runner...")
        result = subprocess.run(
            ["cwl-runner", str(workflow_path), str(input_path)],
            cwd=tmpdir,
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            print("Workflow execution failed!")
            print("STDOUT:", result.stdout)
            print("STDERR:", result.stderr)
            return False
        
        # Verify output
        print("Workflow output:")
        print(result.stdout)
        
        # The output is a JSON object with the file location
        import json
        try:
            output = json.loads(result.stdout)
            output_file = output['output']['path']
            
            # Read the actual output file
            with open(output_file, 'r') as f:
                content = f.read().strip()
                print(f"Actual output content: {content}")
                
                if content == "Hello World":
                    print("\nWorkflow test completed successfully!")
                    return True
                else:
                    print("\nWorkflow test failed - unexpected output content")
                    return False
        except (json.JSONDecodeError, KeyError) as e:
            print(f"\nWorkflow test failed - error parsing output: {str(e)}")
            return False

if __name__ == "__main__":
    test_workflow()
