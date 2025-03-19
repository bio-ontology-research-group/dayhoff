from typing import Dict, Any
from .base import Workflow

class NextflowGenerator:
    """Generates Nextflow workflows"""
    
    def generate(self, workflow: Workflow) -> str:
        """Generate Nextflow representation of a workflow
        
        Args:
            workflow: The workflow to convert
            
        Returns:
            str: Nextflow workflow definition
        """
        nf = """#!/usr/bin/env nextflow

params {
    // TODO: Add workflow parameters
}

process {
    // TODO: Add process configurations
}

"""
        for step in workflow.steps:
            nf += f"""process {step.name} {{
    container '{step.container}'
    
    input:
"""
            for input_name, input_type in step.inputs.items():
                nf += f"    val {input_name}, {input_type}\n"
            nf += "    \n    output:\n"
            for output_name, output_type in step.outputs.items():
                nf += f"    file {output_name} into {output_name}_channel\n"
            nf += "    \n    script:\n"
            nf += f"    '''\n    {step.tool} \\\n"
            for input_name in step.inputs.keys():
                nf += f"        --{input_name} ${{{input_name}}} \\\n"
            nf += "    '''\n}\n\n"
        return nf
