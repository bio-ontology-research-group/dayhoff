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

inputs:
  message:
    type: string

outputs:
  output:
    type: File
    outputSource: echo_step/output

steps:
  echo_step:
    run: echo.cwl
    in:
      message: message
    out: [output]
"""
        return cwl
