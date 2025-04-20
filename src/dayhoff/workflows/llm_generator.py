import json
import os
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
import datetime
import subprocess # Added for potential external validation
import re # Added for cleaning response

# Attempt to import ruamel.yaml for CWL parsing
try:
    from ruamel.yaml import YAML
    # Import the specific error for duplicate keys
    from ruamel.yaml.constructor import DuplicateKeyError
    RUAMEL_AVAILABLE = True
except ImportError:
    YAML = None # type: ignore
    DuplicateKeyError = None # type: ignore
    RUAMEL_AVAILABLE = False


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
            # Consider returning False if strict validation is required for all supported types
            return True, f"Validation not implemented for language: {self.language}"

    def _validate_cwl(self, workflow_code: str) -> Tuple[bool, Optional[str]]:
        """Validate CWL code for basic structure and YAML syntax."""
        if not workflow_code: return False, "Workflow code is empty"
        if 'cwlVersion' not in workflow_code:
            return False, "Missing cwlVersion field"
        if 'class:' not in workflow_code and '"class":' not in workflow_code:
            # Allow 'class' key with quotes for JSON-like YAML
            return False, "Missing class field (e.g., Workflow, CommandLineTool)"

        # Attempt YAML parsing to catch syntax errors like duplicate keys
        if RUAMEL_AVAILABLE:
            yaml = YAML(typ='safe') # Use safe loader (disallows duplicate keys by default)
            try:
                # Load the code to check for YAML syntax errors
                yaml.load(workflow_code)
                logger.debug("CWL code passed basic YAML syntax validation.")
            except DuplicateKeyError as dke:
                 # Provide a more specific error message for duplicate keys
                 error_msg = f"Invalid CWL YAML: Found duplicate key '{dke.problem_mark.name}' near line {dke.problem_mark.line + 1}, column {dke.problem_mark.column + 1}. Original value: {dke.context}"
                 logger.warning(f"CWL validation failed due to duplicate key: {dke}")
                 return False, error_msg
            except Exception as e:
                 # Catch other YAML parsing errors
                 error_msg = f"Invalid CWL YAML syntax: {e}"
                 logger.warning(f"CWL validation failed due to YAML parsing error: {e}")
                 return False, error_msg
        else:
             logger.warning("ruamel.yaml not installed. Skipping YAML syntax validation for CWL.")


        # TODO: Use cwltool --validate via subprocess for deeper validation
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

        # If YAML validation passed (or was skipped) and no external tool check failed
        return True, None # Basic structure and YAML syntax (if checked) are okay

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
        # Regex to find ```json ... ``` or ```<lang> ... ``` or ``` ... ```
        # Make language optional and handle potential variations
        match = re.search(r"```(?:[\w-]+)?\s*(.*?)\s*```", response_text, re.DOTALL | re.IGNORECASE)
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
        # Initialize with defaults that might be overwritten by LLM response
        workflow_name = f"Workflow_{language}_{datetime.datetime.now().strftime('%Y%m%d%H%M')}"
        workflow_summary = "No summary available"
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
                    if not isinstance(parsed_llm_json, dict):
                         raise json.JSONDecodeError("Response is not a JSON object", cleaned_response_text, 0)
                except json.JSONDecodeError as json_err:
                    json_parse_error = True # Mark that JSON parsing failed
                    last_error = f"LLM response was not valid JSON object after cleaning: {json_err}\nCleaned text:\n{cleaned_response_text}"
                    logger.warning(last_error)
                    # Do NOT reset workflow_code here if it was valid before
                    continue # Try again

                # --- JSON Parsing Succeeded ---
                # Extract data based on the prompt used
                # Always try to get name and summary, even on correction attempts, in case LLM provides them
                workflow_name = parsed_llm_json.get('workflow_name', workflow_name) # Keep previous if not provided
                workflow_summary = parsed_llm_json.get('workflow_summary', workflow_summary) # Keep previous if not provided

                # Expect 'workflow_code' on first attempt or after JSON error,
                # 'corrected_workflow' on subsequent validation error corrections.
                # Use .get() with a default of the *current* workflow_code
                # to handle cases where the LLM might not return the expected key.
                if attempt == 1 or json_parse_error:
                    workflow_code = parsed_llm_json.get('workflow_code', workflow_code)
                else: # Correction attempt for validation error
                    workflow_code = parsed_llm_json.get('corrected_workflow', workflow_code) # Use corrected or fallback to previous
                    explanation = parsed_llm_json.get('explanation', '(No explanation provided)')
                    logger.info(f"LLM correction explanation: {explanation}")


                if not workflow_code:
                    # This can happen if the LLM response (after JSON parsing) didn't contain
                    # the expected key ('workflow_code' or 'corrected_workflow') AND
                    # the previous workflow_code was also empty.
                    last_error = "LLM response JSON did not contain workflow code ('workflow_code' or 'corrected_workflow') and no previous code was available."
                    logger.warning(last_error)
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
                        'file': str(file_path.resolve()), # Store absolute path as string
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
        # Include the last piece of invalid code in the error message if available
        final_error_msg = f'Failed to generate valid workflow after {max_attempts} attempts. Last validation error: {last_error}'
        if workflow_code:
            final_error_msg += f"\nLast attempted code:\n---\n{workflow_code}\n---"

        return {
            'success': False,
            'error': final_error_msg
        }

    def list_workflows(self) -> List[Dict[str, Any]]:
        """List all saved workflows"""
        # Reload index in case it was modified externally? Or assume it's managed solely here.
        # self._load_workflows_index() # Optional reload
        return self.workflows_index

    def delete_workflow(self, index: int) -> Dict[str, Any]:
        """
        Delete a workflow by its 1-based index.

        Args:
            index: 1-based index of the workflow to delete.

        Returns:
            Dictionary with 'success': bool and 'name': str or 'error': str.
        """
        idx = index - 1 # Convert to 0-based index
        if idx < 0 or idx >= len(self.workflows_index):
            return {'success': False, 'error': f"Workflow index {index} is out of range. Valid range: 1-{len(self.workflows_index)}"}

        workflow_entry = self.workflows_index[idx]
        file_path_str = workflow_entry.get('file')
        workflow_name = workflow_entry.get('name', 'Unknown')

        # 1. Remove from index
        try:
            del self.workflows_index[idx]
            self._save_workflows_index()
            logger.info(f"Removed workflow #{index} ('{workflow_name}') from index.")
        except Exception as e:
            logger.error(f"Failed to remove workflow #{index} from index or save index: {e}", exc_info=True)
            # Attempt to restore index entry? Risky. For now, report error.
            # If saving failed, the entry might still be gone in memory. Reload?
            self._load_workflows_index() # Reload to be safe
            return {'success': False, 'error': f"Failed to update workflow index file: {e}"}

        # 2. Delete the file (best effort)
        if file_path_str:
            file_path = Path(file_path_str)
            if file_path.exists():
                try:
                    file_path.unlink()
                    logger.info(f"Deleted workflow file: {file_path}")
                except Exception as e:
                    logger.warning(f"Removed workflow #{index} from index, but failed to delete file {file_path}: {e}")
                    # Return success=True because index was updated, but maybe add a warning?
                    return {'success': True, 'name': workflow_name, 'warning': f"Failed to delete file {file_path}: {e}"}
            else:
                logger.warning(f"Workflow file path for index #{index} not found: {file_path_str}")
        else:
            logger.warning(f"No file path found for workflow index #{index}. Cannot delete file.")

        return {'success': True, 'name': workflow_name}

    def get_workflow_details(self, index: int) -> Dict[str, Any]:
        """
        Get the details (metadata) for a workflow by its 1-based index.

        Args:
            index: 1-based index of the workflow.

        Returns:
            Dictionary with 'success': bool and 'workflow': dict or 'error': str.
        """
        idx = index - 1 # Convert to 0-based index
        if idx < 0 or idx >= len(self.workflows_index):
            return {'success': False, 'error': f"Workflow index {index} is out of range. Valid range: 1-{len(self.workflows_index)}"}

        workflow_entry = self.workflows_index[idx]
        return {'success': True, 'workflow': workflow_entry}


    def get_workflow_inputs(self, index: int) -> Dict[str, Any]:
        """
        Get the defined inputs for a workflow by its 1-based index.

        Args:
            index: 1-based index of the workflow.

        Returns:
            Dictionary with 'success': bool, 'inputs': list, 'name': str, 'language': str or 'error': str.
        """
        details_result = self.get_workflow_details(index)
        if not details_result['success']:
            return details_result # Return the error from get_workflow_details

        workflow_entry = details_result['workflow']
        file_path_str = workflow_entry.get('file')
        workflow_name = workflow_entry.get('name', 'Unknown')
        language = workflow_entry.get('language', 'unknown').lower()

        if not file_path_str:
            return {'success': False, 'error': f"No file path found for workflow index #{index}."}

        file_path = Path(file_path_str)
        if not file_path.exists():
            return {'success': False, 'error': f"Workflow file not found at {file_path_str}"}

        try:
            with open(file_path, 'r') as f:
                workflow_code = f.read()
        except Exception as e:
            return {'success': False, 'error': f"Failed to read workflow file {file_path}: {e}"}

        # --- Parse Inputs Based on Language ---
        inputs = []
        parse_error = None
        try:
            if language == 'cwl':
                inputs = self._parse_cwl_inputs(workflow_code)
            elif language == 'nextflow':
                inputs = self._parse_nextflow_inputs(workflow_code)
            elif language == 'wdl':
                inputs = self._parse_wdl_inputs(workflow_code)
            elif language == 'snakemake':
                inputs = self._parse_snakemake_inputs(workflow_code)
            else:
                parse_error = f"Input parsing not implemented for language: {language}"
                logger.warning(parse_error)

        except Exception as e:
            parse_error = f"Parsing failed for {language} workflow: {e}"
            logger.error(f"Error parsing inputs for workflow {file_path}: {e}", exc_info=True)

        if parse_error:
             # Return success=False if parsing failed critically, or maybe success=True with empty inputs and a warning?
             # Let's return failure for now.
             return {'success': False, 'error': parse_error, 'name': workflow_name, 'language': language}

        return {'success': True, 'inputs': inputs, 'name': workflow_name, 'language': language}


    # --- Input Parsing Helper Methods ---

    def _parse_cwl_inputs(self, code: str) -> List[Dict[str, str]]:
        """Basic parsing of CWL inputs using ruamel.yaml if available."""
        inputs = []
        if not RUAMEL_AVAILABLE:
            logger.warning("Cannot parse CWL inputs: ruamel.yaml not installed.")
            raise NotImplementedError("Cannot parse CWL inputs: ruamel.yaml not installed.")

        yaml = YAML(typ='safe') # Use safe loader
        try:
            data = yaml.load(code)
            if isinstance(data, dict) and 'inputs' in data:
                cwl_inputs = data['inputs']
                if isinstance(cwl_inputs, dict):
                    for name, details in cwl_inputs.items():
                        input_info = {'name': name}
                        if isinstance(details, dict):
                            input_info['type'] = self._format_cwl_type(details.get('type', 'unknown'))
                            input_info['description'] = details.get('doc', details.get('label', ''))
                        elif isinstance(details, str): # Simple type definition
                            input_info['type'] = details
                            input_info['description'] = ''
                        else:
                             input_info['type'] = 'unknown'
                             input_info['description'] = ''
                        inputs.append(input_info)
                elif isinstance(cwl_inputs, list): # Array notation (less common for top level)
                     logger.warning("Parsing CWL inputs array notation is not fully supported.")
                     # Handle basic array case if needed
                     for item in cwl_inputs:
                         if isinstance(item, dict):
                             name = list(item.keys())[0] # Assume first key is name
                             details = item[name]
                             input_info = {'name': name}
                             if isinstance(details, dict):
                                 input_info['type'] = self._format_cwl_type(details.get('type', 'unknown'))
                                 input_info['description'] = details.get('doc', details.get('label', ''))
                             elif isinstance(details, str):
                                 input_info['type'] = details
                                 input_info['description'] = ''
                             else:
                                 input_info['type'] = 'unknown'
                                 input_info['description'] = ''
                             inputs.append(input_info)

        except DuplicateKeyError as dke:
             # This shouldn't happen if validation worked, but handle defensively
             raise ValueError(f"Duplicate key '{dke.problem_mark.name}' found during input parsing - validation may have failed.") from dke
        except Exception as e:
            raise ValueError(f"Failed to parse CWL YAML for inputs: {e}") from e
        return inputs

    def _format_cwl_type(self, cwl_type: Any) -> str:
        """Helper to format potentially complex CWL types into a string."""
        if isinstance(cwl_type, str):
            return cwl_type
        elif isinstance(cwl_type, list):
            # Handle optional types (null + type) and arrays of types
            types = [self._format_cwl_type(t) for t in cwl_type]
            if "null" in types:
                types.remove("null")
                suffix = "?" # Indicate optional
            else:
                suffix = ""
            if len(types) == 1:
                return types[0] + suffix
            else:
                # Multiple non-null types (union) - less common for inputs directly
                return "|".join(types) + suffix
        elif isinstance(cwl_type, dict):
            # Handle records, enums, arrays
            type_name = cwl_type.get('type')
            if type_name == 'array':
                items = self._format_cwl_type(cwl_type.get('items', 'unknown'))
                return f"Array<{items}>"
            elif type_name == 'record':
                return f"Record<{cwl_type.get('name', 'anonymous')}>"
            elif type_name == 'enum':
                return f"Enum<{cwl_type.get('name', 'anonymous')}>"
            else:
                # Could be other complex types or just a map
                return str(cwl_type) # Fallback
        else:
            return str(cwl_type) # Fallback for unknown types


    def _parse_nextflow_inputs(self, code: str) -> List[Dict[str, str]]:
        """Basic parsing of Nextflow params using regex."""
        inputs = []
        # Regex to find `params.<name> = <value>` assignments, capturing name and optionally default value
        # Handles single/double quotes, triple quotes, simple groovy expressions (basic)
        # Ignores comments starting with //
        pattern = re.compile(
            r"^\s*params\.(\w+)\s*=\s*" # Match 'params.name ='
            r"(.+?)"                    # Capture the value (non-greedy)
            r"(?:\s*//.*)?$"            # Optional comment, until end of line
            , re.MULTILINE
        )
        for match in pattern.finditer(code):
            name = match.group(1)
            # Basic cleaning of default value - remove quotes, strip whitespace
            default_val = match.group(2).strip()
            if (default_val.startswith("'") and default_val.endswith("'")) or \
               (default_val.startswith('"') and default_val.endswith('"')):
                default_val = default_val[1:-1]
            elif (default_val.startswith("'''") and default_val.endswith("'''")) or \
                 (default_val.startswith('"""') and default_val.endswith('"""')):
                 default_val = default_val[3:-3]
            # Represent groovy expressions or complex types simply
            if default_val.startswith('[') or default_val.startswith('{') or '(' in default_val:
                 desc = f"Default: (expression/complex type)"
            else:
                 desc = f"Default: {default_val}"

            inputs.append({
                'name': name,
                'type': 'param', # Cannot easily determine type from regex
                'description': desc
            })
        if not inputs:
             logger.warning("Basic Nextflow parser found no 'params.<name> = ...' declarations.")
        return inputs

    def _parse_wdl_inputs(self, code: str) -> List[Dict[str, str]]:
        """Basic parsing of WDL workflow inputs using regex."""
        inputs = []
        # Find the 'workflow {...}' block first
        # Make workflow name optional in regex to handle anonymous workflows? No, spec requires name.
        workflow_match = re.search(r"workflow\s+(\w+)\s*\{", code, re.DOTALL)
        if not workflow_match:
            logger.warning("Basic WDL parser could not find 'workflow <name> {' block.")
            # Could potentially look for task inputs, but let's stick to workflow inputs
            return inputs

        workflow_content_start = workflow_match.end()
        # Very naive approach to find the end of the workflow block
        # This doesn't handle nested braces correctly.
        # A better approach would use a parser or more sophisticated brace matching.
        workflow_content_end = code.find('}', workflow_content_start)
        if workflow_content_end == -1:
            workflow_content_end = len(code) # Fallback if closing brace not found

        workflow_content = code[workflow_content_start:workflow_content_end]

        # Find the 'input {...}' block within the workflow content
        input_match = re.search(r"input\s*\{", workflow_content)
        if not input_match:
            logger.warning("Basic WDL parser could not find 'input {...}' block within workflow.")
            # WDL allows inputs directly in workflow scope in WDL >= 1.0
            # Let's try parsing declarations directly in workflow scope as fallback
            input_content = workflow_content
            input_content_start = 0
        else:
            input_content_start = input_match.end()
            # Naive brace matching for end of input block
            input_content_end = workflow_content.find('}', input_content_start)
            if input_content_end == -1:
                input_content_end = len(workflow_content) # Fallback
            input_content = workflow_content[input_content_start:input_content_end]


        # Pattern: `Type name = default` or `Type name` within the input scope
        # Handles optional types (Type?), Array[Type], Map[Type, Type], Pair[Type, Type]
        # Ignores comments starting with #
        pattern = re.compile(
            r"^\s*"                                  # Start of line, optional whitespace
            r"((?:Array|Map|Pair)\[.+?\]\??|\w+\??)" # Type (simple, generic, optional)
            r"\s+"                                   # Separator
            r"(\w+)"                                 # Variable name
            r"(?:\s*=\s*(.+?))?"                     # Optional default value (non-greedy)
            r"(?:\s*#.*)?$"                          # Optional comment, until end of line
            , re.MULTILINE
        )

        for match in pattern.finditer(input_content):
             wdl_type = match.group(1)
             name = match.group(2)
             default_val = match.group(3)
             inputs.append({
                 'name': name,
                 'type': wdl_type,
                 'description': f"Default: {default_val.strip()}" if default_val else "(No default)"
             })

        if not inputs:
             logger.warning("Basic WDL parser found no input declarations like 'Type name' within workflow input block or scope.")
        return inputs


    def _parse_snakemake_inputs(self, code: str) -> List[Dict[str, str]]:
        """Basic parsing of Snakemake config access using regex."""
        inputs = []
        # Look for `config["<name>"]` or `config['<name>']` or `config.get('<name>')` etc.
        # Also look for `workflow.config[...]`
        # This is heuristic and might miss complex access patterns or find false positives in comments/strings.
        patterns = [
            re.compile(r"""config\[\s*['"]([^'"]+)['"]\s*\]"""),
            re.compile(r"""config\.get\(\s*['"]([^'"]+)['"]"""),
            re.compile(r"""workflow\.config\[\s*['"]([^'"]+)['"]\s*\]"""),
            re.compile(r"""workflow\.config\.get\(\s*['"]([^'"]+)['"]"""),
            # Potentially add config.<key> if needed, but more prone to false positives
            # re.compile(r"""config\.(\w+)""")
        ]

        found_keys = set()
        for pattern in patterns:
            for match in pattern.finditer(code):
                key = match.group(1)
                if key not in found_keys:
                    inputs.append({
                        'name': key,
                        'type': 'config',
                        'description': 'Accessed via config dictionary'
                    })
                    found_keys.add(key)

        if not inputs:
             logger.warning("Basic Snakemake parser found no config['key'] or config.get('key') access patterns.")
        return inputs


    def _get_file_extension(self, language: str) -> str:
        """Get the appropriate file extension for the workflow language"""
        extensions = {
            'cwl': 'cwl',
            'nextflow': 'nf',
            'snakemake': 'smk',
            'wdl': 'wdl'
        }
        return extensions.get(language.lower(), 'txt') # Use lower case language
