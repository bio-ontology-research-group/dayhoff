import json
import os
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
import datetime
import subprocess # Added for potential external validation
import re # Added for cleaning response

from ..config import config
from ..llm.prompt import PromptManager
from ..llm.client import LLMClient
# Removed unused import: from .base import Workflow

logger = logging.getLogger(__name__)

class WorkflowValidator:
    """Validates generated workflows for syntax and correctness"""

    def __init__(self, language: str):
        self.language = language.lower() # Ensure lowercase for consistency

    def validate(self, workflow_code: str) -> Tuple[bool, Optional[str]]:
        """
        Validate the workflow code for the given language

        Returns:
            Tuple of (is_valid, error_message)
        """
        # Basic validation - this should be expanded with actual validators for each language
        # TODO: Implement calls to external linters/validators via subprocess
        if self.language == 'cwl':
            return self._validate_cwl(workflow_code)
        elif self.language == 'nextflow':
            return self._validate_nextflow(workflow_code)
        elif self.language == 'snakemake':
            return self._validate_snakemake(workflow_code)
        elif self.language == 'wdl':
            return self._validate_wdl(workflow_code)
        else:
            logger.warning(f"Validation requested for unsupported workflow language: {self.language}")
            # Return True for unsupported languages for now to avoid blocking generation
            return True, f"Validation not implemented for language: {self.language}"

    def _validate_cwl(self, workflow_code: str) -> Tuple[bool, Optional[str]]:
        # Basic validation for CWL
        if not workflow_code: return False, "Workflow code is empty"
        if 'cwlVersion' not in workflow_code:
            return False, "Missing cwlVersion field"
        if 'class:' not in workflow_code and '"class":' not in workflow_code:
            return False, "Missing class field (e.g., Workflow, CommandLineTool)"
        # TODO: Use cwltool --validate via subprocess
        # Example (requires cwltool installed and careful path/error handling):
        # try:
        #     # Write code to temp file? Or pipe via stdin?
        #     # result = subprocess.run(['cwltool', '--validate', temp_file_path], capture_output=True, text=True, check=True)
        #     # return True, None
        # except subprocess.CalledProcessError as e:
        #     # return False, f"cwltool validation failed:\n{e.stderr}"
        # except FileNotFoundError:
        #     # return False, "cwltool not found. Cannot perform full validation."
        # except Exception as e:
        #     # return False, f"Error during cwltool validation: {e}"
        return True, None # Basic check passed

    def _validate_nextflow(self, workflow_code: str) -> Tuple[bool, Optional[str]]:
        # Basic validation for Nextflow
        if not workflow_code: return False, "Workflow code is empty"
        # Nextflow is quite flexible, basic checks are hard. Look for common keywords.
        if 'process' not in workflow_code and 'workflow' not in workflow_code:
            # Allow if it only contains config settings? Maybe too lenient.
            logger.warning("Basic Nextflow validation: Missing 'process' or 'workflow' block.")
            # return False, "Missing process or workflow definition"
        # TODO: Use nextflow -validate or config -check via subprocess
        return True, None # Basic check passed (very lenient)

    def _validate_snakemake(self, workflow_code: str) -> Tuple[bool, Optional[str]]:
        # Basic validation for Snakemake
        if not workflow_code: return False, "Workflow code is empty"
        if 'rule ' not in workflow_code and 'workflow.' not in workflow_code: # Check for 'rule ' to avoid matching variables
             logger.warning("Basic Snakemake validation: Missing 'rule' definition.")
            # return False, "Missing rule definition"
        # TODO: Use snakemake --lint via subprocess
        return True, None # Basic check passed (lenient)

    def _validate_wdl(self, workflow_code: str) -> Tuple[bool, Optional[str]]:
        # Basic validation for WDL
        if not workflow_code: return False, "Workflow code is empty"
        if 'workflow ' not in workflow_code: # Check for 'workflow ' to avoid matching variables
            return False, "Missing workflow definition"
        if 'task ' not in workflow_code: # Check for 'task '
            # WDL can have workflows without tasks (e.g., importing), but usually tasks are expected for generation
             logger.warning("Basic WDL validation: Missing 'task' definition.")
            # return False, "Missing task definition"
        # TODO: Use womtool validate or miniwdl check via subprocess
        return True, None # Basic check passed


class LLMWorkflowGenerator:
    """Generates workflows using LLM"""

    def __init__(self, llm_client: LLMClient, prompt_manager: PromptManager):
        self.llm_client = llm_client
        self.prompt_manager = prompt_manager
        # Use config for base directory, default to ~/.dayhoff/workflows
        base_dir = Path(config.get("GENERAL", "data_dir", str(Path.home() / ".dayhoff"))).expanduser().resolve()
        self.workflows_dir = base_dir / "workflows"
        self.workflows_dir.mkdir(parents=True, exist_ok=True)
        self.workflows_index_file = self.workflows_dir / "index.json"
        self._load_workflows_index()

    def _load_workflows_index(self) -> None:
        """Load the workflows index file or create it if it doesn't exist"""
        if self.workflows_index_file.exists():
            try:
                with open(self.workflows_index_file, 'r') as f:
                    self.workflows_index = json.load(f)
                    # Basic validation: ensure it's a list
                    if not isinstance(self.workflows_index, list):
                         logger.warning(f"Workflows index file ({self.workflows_index_file}) is not a list. Resetting.")
                         self.workflows_index = []
            except json.JSONDecodeError:
                logger.warning(f"Invalid JSON in workflows index file ({self.workflows_index_file}). Creating a new one.")
                self.workflows_index = []
            except Exception as e:
                 logger.error(f"Error loading workflows index file ({self.workflows_index_file}): {e}. Resetting.", exc_info=True)
                 self.workflows_index = []
        else:
            self.workflows_index = []
            logger.info(f"Workflows index file not found at {self.workflows_index_file}. Will create a new one.")

    def _save_workflows_index(self) -> None:
        """Save the workflows index file"""
        try:
            with open(self.workflows_index_file, 'w') as f:
                json.dump(self.workflows_index, f, indent=2)
            logger.debug(f"Saved workflows index to {self.workflows_index_file}")
        except Exception as e:
            logger.error(f"Failed to save workflows index file ({self.workflows_index_file}): {e}", exc_info=True)

    def _clean_llm_response(self, response_text: str) -> str:
        """Strips markdown code fences and whitespace from LLM response."""
        # Regex to find ```json ... ``` or ``` ... ```
        match = re.search(r"```(?:json)?\s*(.*?)\s*```", response_text, re.DOTALL | re.IGNORECASE)
        if match:
            cleaned_text = match.group(1).strip()
            logger.debug("Stripped markdown fences from LLM response.")
            return cleaned_text
        else:
            # If no fences found, just strip leading/trailing whitespace
            cleaned_text = response_text.strip()
            logger.debug("No markdown fences found, just stripped whitespace.")
            return cleaned_text

    def generate_workflow(self, description: str, max_attempts: int = 3) -> Dict[str, Any]:
        """
        Generate a workflow based on the description, validate, and save it.

        Args:
            description: User's description of the workflow
            max_attempts: Maximum number of attempts to generate a valid workflow

        Returns:
            Dictionary containing generation result ('success': bool, 'workflow': dict or 'error': str)
        """
        language = config.get_workflow_language()
        validator = WorkflowValidator(language)
        workflow_code = ""
        workflow_name = "Untitled Workflow"
        workflow_summary = "No summary provided"
        last_error = "Failed to get initial response from LLM"
        last_raw_response = "" # Store the raw response from the last failed attempt

        for attempt in range(1, max_attempts + 1):
            logger.info(f"Workflow generation attempt {attempt}/{max_attempts} for language: {language}")
            json_parse_error = False # Flag to track if JSON parsing failed this attempt
            try:
                if attempt == 1:
                    # First attempt: generate from description
                    prompt = self.prompt_manager.generate_prompt('workflow_generation', {
                        'description': description,
                        'language': language
                    })
                else:
                    # Subsequent attempts: try to correct previous code
                    # Use the raw response if JSON parsing failed, otherwise use the extracted code
                    code_to_correct = last_raw_response if not workflow_code and last_raw_response else workflow_code
                    if not code_to_correct:
                         logger.error("Correction attempt requested but no previous workflow code or raw response available.")
                         # Use a generic correction prompt if we have nothing else
                         prompt = self.prompt_manager.generate_prompt('workflow_generation', {
                             'description': f"Correct the previous attempt to generate a {language} workflow for: {description}. The previous attempt failed with error: {last_error}",
                             'language': language
                         })
                         logger.warning("Falling back to generation prompt for correction attempt due to missing previous code.")
                    else:
                         prompt = self.prompt_manager.generate_prompt('workflow_correction', {
                             'language': language,
                             'workflow_code': code_to_correct, # Use raw response or previous code
                             'validation_errors': last_error # Provide the error message
                         })

                # Call the LLM Client
                response_data = self.llm_client.generate(prompt)
                llm_response_text = response_data.get('response') # Get the actual response string
                last_raw_response = llm_response_text # Store raw response for potential correction

                if not llm_response_text:
                    last_error = "LLM returned an empty response."
                    logger.warning(last_error)
                    continue # Try again

                # Clean the response (remove markdown fences)
                cleaned_response_text = self._clean_llm_response(llm_response_text)

                if not cleaned_response_text:
                     last_error = "LLM response was empty after cleaning."
                     logger.warning(last_error)
                     continue # Try again

                # Parse the JSON response from the LLM
                try:
                    parsed_llm_json = json.loads(cleaned_response_text)
                except json.JSONDecodeError as json_err:
                    json_parse_error = True # Mark that JSON parsing failed
                    last_error = f"LLM response was not valid JSON after cleaning: {json_err}\nCleaned text:\n{cleaned_response_text}"
                    logger.warning(last_error)
                    # Do NOT reset workflow_code here if it was valid before
                    continue # Try again

                # --- JSON Parsing Succeeded ---
                # Extract data based on the prompt used
                if attempt == 1 or json_parse_error: # If first attempt or correcting a JSON error, expect full structure
                    workflow_code = parsed_llm_json.get('workflow_code', '')
                    workflow_name = parsed_llm_json.get('workflow_name', f"Workflow_{language}_{datetime.datetime.now().strftime('%Y%m%d%H%M')}")
                    workflow_summary = parsed_llm_json.get('workflow_summary', 'No summary available')
                else: # Correction attempt for validation error
                    workflow_code = parsed_llm_json.get('corrected_workflow', workflow_code) # Use corrected or fallback to previous
                    explanation = parsed_llm_json.get('explanation', '(No explanation provided)')
                    logger.info(f"LLM correction explanation: {explanation}")
                    # Keep previous name and summary during correction

                if not workflow_code:
                    last_error = "LLM response JSON did not contain workflow code ('workflow_code' or 'corrected_workflow')."
                    logger.warning(last_error)
                    # workflow_code remains as it was (potentially empty)
                    continue # Try again

                # Validate the generated/corrected code
                is_valid, error_message = validator.validate(workflow_code)

                if is_valid:
                    logger.info(f"Workflow validation successful on attempt {attempt}.")
                    # --- Save the valid workflow ---
                    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                    # Sanitize workflow_name for filename
                    safe_name_part = "".join(c if c.isalnum() or c in ('_', '-') else '_' for c in workflow_name.replace(' ', '_'))[:50]
                    filename = f"{safe_name_part}_{language}_{timestamp}.{self._get_file_extension(language)}"
                    file_path = self.workflows_dir / filename

                    try:
                        with open(file_path, 'w') as f:
                            f.write(workflow_code)
                        logger.info(f"Successfully saved workflow to {file_path}")
                    except Exception as save_err:
                         logger.error(f"Failed to save workflow file to {file_path}: {save_err}", exc_info=True)
                         return {'success': False, 'error': f"Generated valid workflow but failed to save file: {save_err}"}

                    # --- Update index ---
                    workflow_entry = {
                        'name': workflow_name,
                        'summary': workflow_summary,
                        'language': language,
                        'file': str(file_path), # Store absolute path as string
                        'created_at': datetime.datetime.now().isoformat(),
                        'description': description # Store original user description
                    }

                    self.workflows_index.append(workflow_entry)
                    self._save_workflows_index()

                    return {
                        'success': True,
                        'workflow': workflow_entry
                    }
                else:
                    # Validation failed, store error for next attempt or final failure message
                    last_error = error_message or "Validation failed with unspecified error."
                    logger.warning(f"Workflow validation failed on attempt {attempt}: {last_error}")
                    # Loop continues to the next attempt, workflow_code holds the invalid code

            except (ConnectionError, ValueError, RuntimeError, Exception) as e:
                # Catch errors during LLM call or prompt generation
                logger.error(f"Error during workflow generation attempt {attempt}: {e}", exc_info=True)
                last_error = f"API call or processing error: {e}"
                # Depending on the error, we might want to stop retrying (e.g., auth error)
                # For now, continue to next attempt unless it's the last one
                if attempt == max_attempts:
                     return {'success': False, 'error': f"Failed to generate workflow due to error: {e}"}


        # If loop finishes without returning success
        logger.error(f"Failed to generate valid workflow after {max_attempts} attempts. Last error: {last_error}")
        return {
            'success': False,
            'error': f'Failed to generate valid workflow after {max_attempts} attempts. Last validation error: {last_error}'
        }

    def list_workflows(self) -> List[Dict[str, Any]]:
        """List all saved workflows"""
        # Reload index in case it was modified externally? Or assume it's managed solely here.
        # self._load_workflows_index() # Optional reload
        return self.workflows_index

    def _get_file_extension(self, language: str) -> str:
        """Get the appropriate file extension for the workflow language"""
        extensions = {
            'cwl': 'cwl',
            'nextflow': 'nf',
            'snakemake': 'smk',
            'wdl': 'wdl'
        }
        return extensions.get(language.lower(), 'txt') # Use lower case language
