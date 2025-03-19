from typing import List, Dict, Any
from dataclasses import dataclass

@dataclass
class WorkflowStep:
    """Represents a single step in a workflow"""
    name: str
    tool: str
    inputs: Dict[str, Any]
    outputs: Dict[str, str]
    container: str
    requirements: List[str]

class Workflow:
    """Abstract representation of a workflow"""
    
    def __init__(self, name: str):
        """Initialize a new workflow"""
        self.name = name
        self.steps: List[WorkflowStep] = []
        self.dependencies: Dict[str, List[str]] = {}
        
    def add_step(self, step: WorkflowStep, depends_on: List[str] = []):
        """Add a step to the workflow
        
        Args:
            step: The workflow step to add
            depends_on: List of step names this step depends on
        """
        self.steps.append(step)
        self.dependencies[step.name] = depends_on
        
    def validate(self) -> bool:
        """Validate the workflow structure
        
        Returns:
            bool: True if workflow is valid
        """
        # TODO: Implement workflow validation
        return True
