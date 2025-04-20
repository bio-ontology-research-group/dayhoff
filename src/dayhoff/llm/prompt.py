from typing import Dict, Any
from jinja2 import Template

class PromptManager:
    """Manages prompt templates and generation"""

    def __init__(self):
        # Define templates using Jinja2 for variable substitution
        # Ensure templates clearly specify the expected JSON output format
        self.templates = {
            'command': Template("""
            Given the following input, generate an appropriate command:
            Input: {{input}}

            Respond ONLY in JSON format with the following structure:
            {
                "command": "the command to execute",
                "reasoning": "why this command is appropriate"
            }
            """),
            'followup': Template("""
            Previous context:
            {{context}}

            New input: {{input}}

            Generate an appropriate response. Respond ONLY in JSON format with the following structure:
            {
                "command": "the command to execute",
                "reasoning": "why this command is appropriate",
                "context_updates": "any context updates"
            }
            """),
            'workflow_generation': Template("""
            You are an expert bioinformatics workflow developer. Generate a bioinformatics workflow script in {{language}} format based on the following description.

            Description: {{description}}

            The workflow script should:
            1. Be syntactically correct and runnable for the {{language}} language.
            2. Follow best practices for {{language}} development (e.g., modularity, clear inputs/outputs).
            3. Include comments explaining key steps or complex logic.
            4. Use container images (e.g., Docker or Singularity) for software dependencies where appropriate, specifying reasonable image names (e.g., from biocontainers).
            5. Define necessary inputs and outputs clearly.
            6. Include basic error handling or reporting if feasible within the language structure.

            Also provide a brief, descriptive name and a one or two-sentence summary for this workflow.

            Respond ONLY with a valid JSON object containing the following keys:
            {
                "workflow_name": "A short, descriptive name for the workflow (e.g., 'RNASeq_Alignment_Quantification')",
                "workflow_summary": "A brief summary of what the workflow does (1-2 sentences)",
                "workflow_code": "The complete, runnable workflow script code as a single string in {{language}} format"
            }

            Ensure the "workflow_code" value is a single string containing the entire script, properly escaped for JSON if necessary. Do not include any text outside the JSON structure.
            """),
            'workflow_correction': Template("""
            You are an expert bioinformatics workflow developer. The following {{language}} workflow script has validation errors.

            Original workflow script:
            ```{{language}}
            {{workflow_code}}
            ```

            Validation errors reported:
            {{validation_errors}}

            Please correct the workflow script to fix ONLY the reported errors. Maintain the original functionality and structure as much as possible. Ensure the corrected script is syntactically valid {{language}}.

            Respond ONLY with a valid JSON object containing the following keys:
            {
                "corrected_workflow": "The complete, corrected workflow script code as a single string in {{language}} format",
                "explanation": "Brief explanation of the specific changes made to fix the reported errors"
            }

            Ensure the "corrected_workflow" value is a single string containing the entire corrected script, properly escaped for JSON if necessary. Do not include any text outside the JSON structure.
            """)
        }
        # Add more templates as needed (e.g., for specific analysis suggestions, code explanation)

    def generate_prompt(self, template_name: str, context: Dict[str, Any]) -> str:
        """Generate a prompt from a template using the provided context"""
        template = self.templates.get(template_name)
        if not template:
            raise ValueError(f"Unknown prompt template: {template_name}")
        try:
            return template.render(**context)
        except Exception as e:
            # Catch potential Jinja rendering errors (e.g., missing context variables)
            raise ValueError(f"Error rendering prompt template '{template_name}': {e}") from e

