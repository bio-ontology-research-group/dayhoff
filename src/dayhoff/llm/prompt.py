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
            """)
        }
        
    def generate_prompt(self, template_name: str, context: Dict[str, Any]) -> str:
        """Generate a prompt from a template"""
        template = self.templates.get(template_name)
        if not template:
            raise ValueError(f"Unknown template: {template_name}")
        return template.render(**context)
