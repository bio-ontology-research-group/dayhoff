from typing import Dict, Any
from jinja2 import Template

class PromptManager:
    """Manages prompt templates and generation"""
    
    def __init__(self):
        self.templates = {
            'command': Template("""
            Given the following input, generate an appropriate command:
            Input: {{input}}
            
            Respond in JSON format with:
            {
                "command": "the command to execute",
                "reasoning": "why this command is appropriate"
            }
            """),
            'followup': Template("""
            Previous context:
            {{context}}
            
            New input: {{input}}
            
            Generate an appropriate response in JSON format:
            {
                "command": "the command to execute",
                "reasoning": "why this command is appropriate",
                "context_updates": "any context updates"
            }
            """),
            'workflow_generation': Template("""
            Generate a bioinformatics workflow in {{language}} format based on the following description:
            
            Description: {{description}}
            
            The workflow should:
            1. Be syntactically correct and follow best practices for {{language}}
            2. Include appropriate error handling
            3. Use container images where appropriate
            4. Include comments explaining key steps
            
            Also provide a brief name and summary for this workflow.
            
            Respond in JSON format with:
            {
                "workflow_name": "A short descriptive name for the workflow",
                "workflow_summary": "A brief summary of what the workflow does (1-2 sentences)",
                "workflow_code": "The complete workflow code in {{language}} format"
            }
            """),
            'workflow_correction': Template("""
            The following {{language}} workflow has validation errors:
            
            Original workflow:
            ```
            {{workflow_code}}
            ```
            
            Validation errors:
            {{validation_errors}}
            
            Please correct the workflow to fix these errors. Maintain the same functionality but ensure the workflow is syntactically correct.
            
            Respond in JSON format with:
            {
                "corrected_workflow": "The corrected workflow code in {{language}} format",
                "explanation": "Brief explanation of the changes made to fix the errors"
            }
            """)
        }
        
    def generate_prompt(self, template_name: str, context: Dict[str, Any]) -> str:
        """Generate a prompt from a template"""
        template = self.templates.get(template_name)
        if not template:
            raise ValueError(f"Unknown template: {template_name}")
        return template.render(**context)
