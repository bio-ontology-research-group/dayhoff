from typing import Dict, Any
from .base import Workflow

class CWLGenerator:
    """Generates CWL (Common Workflow Language) workflows"""
    
    def generate(self, workflow: Workflow) -> str:
        """Generate CWL representation of a workflow
        
        Args:
            workflow: The workflow to convert
            
        Returns:
            str: CWL workflow definition
        """
        cwl = f"""#!/usr/bin/env cwl-runner
cwlVersion: v1.0
class: Workflow

inputs: []
outputs: []
steps:
"""
        for step in workflow.steps:
            cwl += f"""  {step.name}:
    run: {step.tool}.cwl
    in:
"""
            for input_name, input_type in step.inputs.items():
                cwl += f"      {input_name}: {input_type}\n"
            cwl += "    out: ["
            cwl += ", ".join(step.outputs.keys())
            cwl += "]\n\n"
        return cwl
