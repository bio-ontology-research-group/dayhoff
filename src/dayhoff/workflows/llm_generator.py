import json
import os
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
import datetime

from ..config import config
from ..llm.prompt import PromptManager
from ..llm.client import LLMClient
from .base import Workflow

logger = logging.getLogger(__name__)

class WorkflowValidator:
    """Validates generated workflows for syntax and correctness"""
    
    def __init__(self, language: str):
        self.language = language
        
    def validate(self, workflow_code: str) -> Tuple[bool, Optional[str]]:
        """
        Validate the workflow code for the given language
        
        Returns:
            Tuple of (is_valid, error_message)
        """
        # Basic validation - this should be expanded with actual validators for each language
        if self.language == 'cwl':
            return self._validate_cwl(workflow_code)
        elif self.language == 'nextflow':
            return self._validate_nextflow(workflow_code)
        elif self.language == 'snakemake':
            return self._validate_snakemake(workflow_code)
        elif self.language == 'wdl':
            return self._validate_wdl(workflow_code)
        else:
            return False, f"Unsupported workflow language: {self.language}"
    
    def _validate_cwl(self, workflow_code: str) -> Tuple[bool, Optional[str]]:
        # Basic validation for CWL
        if 'cwlVersion' not in workflow_code:
            return False, "Missing cwlVersion field"
        if 'class:' not in workflow_code and '"class":' not in workflow_code:
            return False, "Missing class field"
        # More detailed validation would use cwltool --validate
        return True, None
    
    def _validate_nextflow(self, workflow_code: str) -> Tuple[bool, Optional[str]]:
        # Basic validation for Nextflow
        if 'process' not in workflow_code and 'workflow' not in workflow_code:
            return False, "Missing process or workflow definition"
        # More detailed validation would use nextflow -check
        return True, None
    
    def _validate_snakemake(self, workflow_code: str) -> Tuple[bool, Optional[str]]:
        # Basic validation for Snakemake
        if 'rule' not in workflow_code:
            return False, "Missing rule definition"
        # More detailed validation would use snakemake --lint
        return True, None
    
    def _validate_wdl(self, workflow_code: str) -> Tuple[bool, Optional[str]]:
        # Basic validation for WDL
        if 'workflow' not in workflow_code:
            return False, "Missing workflow definition"
        if 'task' not in workflow_code:
            return False, "Missing task definition"
        # More detailed validation would use womtool validate
        return True, None


class LLMWorkflowGenerator:
    """Generates workflows using LLM"""
    
    def __init__(self, llm_client: LLMClient, prompt_manager: PromptManager):
        self.llm_client = llm_client
        self.prompt_manager = prompt_manager
        self.workflows_dir = Path.home() / ".dayhoff" / "workflows"
        self.workflows_dir.mkdir(parents=True, exist_ok=True)
        self.workflows_index_file = self.workflows_dir / "index.json"
        self._load_workflows_index()
    
    def _load_workflows_index(self) -> None:
        """Load the workflows index file or create it if it doesn't exist"""
        if self.workflows_index_file.exists():
            try:
                with open(self.workflows_index_file, 'r') as f:
                    self.workflows_index = json.load(f)
            except json.JSONDecodeError:
                logger.warning("Invalid workflows index file. Creating a new one.")
                self.workflows_index = []
        else:
            self.workflows_index = []
    
    def _save_workflows_index(self) -> None:
        """Save the workflows index file"""
        with open(self.workflows_index_file, 'w') as f:
            json.dump(self.workflows_index, f, indent=2)
    
    def generate_workflow(self, description: str, max_attempts: int = 3) -> Dict[str, Any]:
        """
        Generate a workflow based on the description
        
        Args:
            description: User's description of the workflow
            max_attempts: Maximum number of attempts to generate a valid workflow
            
        Returns:
            Dictionary with workflow details
        """
        language = config.get_workflow_language()
        validator = WorkflowValidator(language)
        
        # First attempt to generate workflow
        prompt = self.prompt_manager.generate_prompt('workflow_generation', {
            'description': description,
            'language': language
        })
        
        response = self.llm_client.generate(prompt)
        try:
            workflow_data = json.loads(response.get('content', '{}'))
            workflow_code = workflow_data.get('workflow_code', '')
            workflow_name = workflow_data.get('workflow_name', 'Untitled Workflow')
            workflow_summary = workflow_data.get('workflow_summary', 'No description provided')
        except (json.JSONDecodeError, AttributeError):
            logger.error("Failed to parse LLM response")
            return {
                'success': False,
                'error': 'Failed to generate workflow: Invalid response from LLM'
            }
        
        # Validate and correct if needed
        is_valid, error_message = validator.validate(workflow_code)
        attempts = 1
        
        while not is_valid and attempts < max_attempts:
            logger.info(f"Workflow validation failed. Attempt {attempts}/{max_attempts} to correct.")
            correction_prompt = self.prompt_manager.generate_prompt('workflow_correction', {
                'language': language,
                'workflow_code': workflow_code,
                'validation_errors': error_message
            })
            
            correction_response = self.llm_client.generate(correction_prompt)
            try:
                correction_data = json.loads(correction_response.get('content', '{}'))
                workflow_code = correction_data.get('corrected_workflow', workflow_code)
            except (json.JSONDecodeError, AttributeError):
                logger.error("Failed to parse LLM correction response")
                break
            
            is_valid, error_message = validator.validate(workflow_code)
            attempts += 1
        
        if not is_valid:
            return {
                'success': False,
                'error': f'Failed to generate valid workflow after {max_attempts} attempts: {error_message}'
            }
        
        # Save the workflow
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{language}_{timestamp}.{self._get_file_extension(language)}"
        file_path = self.workflows_dir / filename
        
        with open(file_path, 'w') as f:
            f.write(workflow_code)
        
        # Update index
        workflow_entry = {
            'name': workflow_name,
            'summary': workflow_summary,
            'language': language,
            'file': str(file_path),
            'created_at': datetime.datetime.now().isoformat(),
            'description': description
        }
        
        self.workflows_index.append(workflow_entry)
        self._save_workflows_index()
        
        return {
            'success': True,
            'workflow': workflow_entry
        }
    
    def list_workflows(self) -> List[Dict[str, Any]]:
        """List all saved workflows"""
        return self.workflows_index
    
    def _get_file_extension(self, language: str) -> str:
        """Get the appropriate file extension for the workflow language"""
        extensions = {
            'cwl': 'cwl',
            'nextflow': 'nf',
            'snakemake': 'smk',
            'wdl': 'wdl'
        }
        return extensions.get(language, 'txt')
