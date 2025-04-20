import json
import logging
import argparse
import os
import datetime
from typing import List, Optional, TYPE_CHECKING
from pathlib import Path # Added

from rich.panel import Panel
from rich.table import Table
from rich.live import Live
from rich.spinner import Spinner
from rich.markdown import Markdown

from ..config import ALLOWED_WORKFLOW_LANGUAGES # Import allowed languages
from ..workflow_generator import WorkflowGenerator # For wf_gen
from ..workflows.visualizer import WorkflowVisualizer # Import the new visualizer

if TYPE_CHECKING:
    from ..service import DayhoffService # Import DayhoffService for type hinting

logger = logging.getLogger(__name__)

# --- Workflow & Language Handlers ---

def handle_wf_gen(service: 'DayhoffService', args: List[str]) -> Optional[str]:
    """Handles the /wf_gen command using the configured language. Prints output."""
    parser = service._create_parser("wf_gen", service._command_map['wf_gen']['help'], add_help=True)
    parser.add_argument("steps_json", help="Workflow steps definition as JSON string (list or dict)")

    try:
        parsed_args = parser.parse_args(args)

        try:
            steps = json.loads(parsed_args.steps_json)
            if not isinstance(steps, (list, dict)):
                 raise ValueError("Steps JSON must decode to a list or dictionary.")
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON provided for steps: {e}") from e

        language = service.config.get_workflow_language()
        executor = service.config.get_workflow_executor(language) # Get configured executor
        logger.info(f"Generating workflow using configured language: {language} (default executor: {executor})")
        service.console.print(f"Generating {language.upper()} workflow (default executor: {executor or 'N/A'})...", style="info")

        # Assuming WorkflowGenerator exists and has a method like generate_workflow
        generator = WorkflowGenerator()
        # Pass language to the generator method
        # TODO: Update WorkflowGenerator.generate_workflow signature if needed
        # For now, assume it takes steps and language
        # workflow_output = generator.generate_workflow(steps, language=language)
        # Placeholder until generate_workflow exists
        if language == 'cwl':
             workflow_output = generator.generate_cwl(steps) # Assuming this exists
        elif language == 'nextflow':
             workflow_output = generator.generate_nextflow(steps) # Assuming this exists
        else:
             raise NotImplementedError(f"Workflow generation for language '{language}' is not implemented in WorkflowGenerator.")


        if workflow_output is None or not workflow_output.strip():
            service.console.print(f"Workflow generation for language '{language}' returned no output.", style="warning")
            return None

        # Print the generated workflow content
        service.console.print(Panel(workflow_output, title=f"Generated {language.upper()} Workflow", border_style="green", expand=True))
        return None # Output printed

    except argparse.ArgumentError as e: raise e
    except SystemExit: return None # Help printed
    except ValueError as e: # Catch JSON errors or validation errors
         raise e
    except NotImplementedError as e:
         # Catch if generator doesn't support the language
         logger.warning(f"Workflow generation not implemented for language '{language}': {e}")
         raise NotImplementedError(f"Workflow generation for language '{language}' is not implemented.") from e
    except Exception as e:
        logger.error("Error generating workflow", exc_info=True)
        raise RuntimeError(f"Error generating workflow: {e}") from e


def handle_language(service: 'DayhoffService', args: List[str]) -> Optional[str]:
    """Handles the /language command to view or set the workflow language. Prints output."""
    parser = service._create_parser(
        "language",
        service._command_map['language']['help'],
        add_help=True
    )
    parser.add_argument("language", nargs='?', help="The workflow language to set (optional).")

    try:
        parsed_args = parser.parse_args(args)

        if parsed_args.language is None:
            # Show current language and its executor
            current_language = service.config.get_workflow_language()
            current_executor = service.config.get_workflow_executor(current_language) or "N/A"
            service.console.print(f"Current default workflow language: [bold cyan]{current_language}[/bold cyan]")
            service.console.print(f"Default executor for {current_language.upper()}: [bold cyan]{current_executor}[/bold cyan]")
        else:
            # Set the language
            requested_language = parsed_args.language.lower()
            if requested_language in ALLOWED_WORKFLOW_LANGUAGES:
                try:
                    # Use config.set to update and save
                    service.config.set('WORKFLOWS', 'default_workflow_type', requested_language)
                    logger.info(f"Workflow language set to: {requested_language}")
                    # Show the executor that will now be used by default
                    new_executor = service.config.get_workflow_executor(requested_language) or "N/A"
                    service.console.print(f"Workflow language set to: [bold cyan]{requested_language}[/bold cyan]", style="info")
                    service.console.print(f"(Default executor for {requested_language.upper()} is now: [bold cyan]{new_executor}[/bold cyan])", style="info")
                except Exception as e:
                    logger.error(f"Failed to set workflow language to {requested_language}: {e}", exc_info=True)
                    raise RuntimeError(f"Failed to save workflow language setting: {e}") from e
            else:
                # Raise error for invalid language
                allowed_str = ", ".join(ALLOWED_WORKFLOW_LANGUAGES)
                raise argparse.ArgumentError(None, f"Invalid language '{parsed_args.language}'. Allowed languages are: {allowed_str}")

        return None # Output printed

    except argparse.ArgumentError as e:
        raise e # Re-raise for execute_command
    except SystemExit:
         return None # Help was printed

# --- LLM Workflow Handlers ---

def handle_workflow(service: 'DayhoffService', args: List[str]) -> Optional[str]:
    """Handles the /workflow command with subparsers. Prints output directly."""
    parser = service._create_parser("workflow", service._command_map['workflow']['help'], add_help=True)
    subparsers = parser.add_subparsers(dest="subcommand", title="Subcommands",
                                       description="Valid subcommands for /workflow",
                                       help="Action to perform with workflows")
    
    # --- Subparser: list ---
    parser_list = subparsers.add_parser("list", help="List all saved workflows.", add_help=True)
    
    # --- Subparser: show ---
    parser_show = subparsers.add_parser("show", help="Show details of a specific workflow.", add_help=True)
    parser_show.add_argument("index", type=int, help="Index of the workflow to show (from list).")
    
    # --- Subparser: generate ---
    parser_generate = subparsers.add_parser("generate", help="Generate a new workflow using LLM.", add_help=True)
    parser_generate.add_argument("description", nargs='+', help="Description of the workflow to generate.")

    # --- Subparser: delete ---
    parser_delete = subparsers.add_parser("delete", help="Delete a specific workflow.", add_help=True)
    parser_delete.add_argument("index", type=int, help="Index of the workflow to delete (from list).")

    # --- Subparser: inputs ---
    parser_inputs = subparsers.add_parser("inputs", help="List required inputs for a specific workflow.", add_help=True)
    parser_inputs.add_argument("index", type=int, help="Index of the workflow to inspect (from list).")

    # --- Subparser: visualize ---
    parser_visualize = subparsers.add_parser("visualize", help="Generate a DOT file visualizing the workflow structure.", add_help=True)
    parser_visualize.add_argument("index", type=int, help="Index of the workflow to visualize (from list).")
    
    try:
        # Handle case where no subcommand is given - default to list
        if not args:
            return _handle_workflow_list(service)
            
        parsed_args = parser.parse_args(args)
        
        # --- Execute subcommand logic ---
        if parsed_args.subcommand == "list":
            return _handle_workflow_list(service)
        elif parsed_args.subcommand == "show":
            return _handle_workflow_show(service, parsed_args.index)
        elif parsed_args.subcommand == "generate":
            description = " ".join(parsed_args.description)
            return _handle_workflow_generation(service, description)
        elif parsed_args.subcommand == "delete":
            return _handle_workflow_delete(service, parsed_args.index)
        elif parsed_args.subcommand == "inputs":
            return _handle_workflow_inputs(service, parsed_args.index)
        elif parsed_args.subcommand == "visualize":
            return _handle_workflow_visualize(service, parsed_args.index)
        else:
            # Should not happen if subcommand is required/checked, but handle defensively
            parser.print_help()
            return None
            
    except argparse.ArgumentError as e:
        raise e # Re-raise for execute_command to handle
    except SystemExit:
        return None # Help was printed
    except Exception as e:
        logger.error(f"Error during /workflow {args}: {e}", exc_info=True)
        raise RuntimeError(f"Error executing workflow command: {e}") from e

def _handle_workflow_list(service: 'DayhoffService') -> None:
    """Lists all saved workflows. Prints output."""
    try:
        workflow_generator = service._get_workflow_generator()
        workflows = workflow_generator.list_workflows()
        
        if not workflows:
            service.console.print("No workflows have been generated yet.", style="info")
            return None
            
        table = Table(title=f"Generated Workflows ({len(workflows)} total)", show_header=True, header_style="bold magenta")
        table.add_column("#", style="dim", width=4, justify="right")
        table.add_column("Name", style="bold")
        table.add_column("Language", width=10)
        table.add_column("Created", width=20)
        table.add_column("Summary")
        
        for i, workflow in enumerate(workflows):
            # Format the date for display
            created_at = workflow.get('created_at', '')
            try:
                dt = datetime.datetime.fromisoformat(created_at)
                created_display = dt.strftime("%Y-%m-%d %H:%M")
            except (ValueError, TypeError):
                created_display = created_at
                
            table.add_row(
                str(i + 1),  # 1-based index
                workflow.get('name', 'Untitled'),
                workflow.get('language', 'unknown').upper(),
                created_display,
                workflow.get('summary', 'No summary available')
            )
            
        service.console.print(table)
        service.console.print("\nUse '/workflow show <#>' to view details of a specific workflow.", style="dim")
        service.console.print("Use '/workflow delete <#>' to remove a workflow.", style="dim")
        service.console.print("Use '/workflow inputs <#>' to list required inputs.", style="dim")
        service.console.print("Use '/workflow visualize <#>' to generate a DOT graph file.", style="dim") # Added help text
        return None
        
    except Exception as e:
        logger.error(f"Error listing workflows: {e}", exc_info=True)
        raise RuntimeError(f"Error listing workflows: {e}") from e

def _handle_workflow_show(service: 'DayhoffService', index: int) -> None:
    """Shows details of a specific workflow. Prints output."""
    try:
        workflow_generator = service._get_workflow_generator()
        # Use get_workflow_details which handles index validation
        details_result = workflow_generator.get_workflow_details(index)
        if not details_result['success']:
             error_msg = details_result.get('error', 'Unknown error')
             if "index" in error_msg.lower() and "out of range" in error_msg.lower():
                 raise IndexError(error_msg)
             else:
                 service.console.print(f"[error]Failed to get workflow details:[/error] {error_msg}")
                 return None

        workflow = details_result['workflow']
        
        # Format created date
        created_at = workflow.get('created_at', '')
        try:
            dt = datetime.datetime.fromisoformat(created_at)
            created_display = dt.strftime("%Y-%m-%d %H:%M:%S")
        except (ValueError, TypeError):
            created_display = created_at
        
        # Display workflow details
        details = [
            f"[bold]Name:[/bold] {workflow.get('name', 'Untitled')}",
            f"[bold]Language:[/bold] {workflow.get('language', 'unknown').upper()}",
            f"[bold]Created:[/bold] {created_display}",
            f"[bold]File:[/bold] {workflow.get('file', 'Unknown')}",
            "",
            f"[bold]Summary:[/bold] {workflow.get('summary', 'No summary available')}",
            "",
            f"[bold]Original Description:[/bold] {workflow.get('description', 'No description available')}"
        ]
        
        service.console.print(Panel("\n".join(details), title=f"Workflow #{index} Details", border_style="cyan"))
        
        # Try to read and display the workflow file
        file_path = workflow.get('file')
        if file_path and os.path.exists(file_path):
            try:
                with open(file_path, 'r') as f:
                    workflow_code = f.read()
                
                language = workflow.get('language', 'unknown')
                # Use Rich Markdown for syntax highlighting if language is known
                # Note: Requires 'pygments' library
                try:
                    md = Markdown(f"```{language}\n{workflow_code}\n```", code_theme="default")
                    service.console.print(Panel(md, title=f"{language.upper()} Workflow Code", border_style="green"))
                except Exception: # Fallback if markdown fails
                     logger.warning("Failed to render workflow code as markdown, showing plain text.")
                     service.console.print(Panel(workflow_code, title=f"{language.upper()} Workflow Code (Plain Text)", border_style="green"))

            except Exception as e:
                service.console.print(f"[error]Error reading workflow file:[/error] {e}")
        else:
            service.console.print("[warning]Workflow file not found or path not specified.[/warning]")
            
        return None
        
    except IndexError as e:
        raise e  # Re-raise for execute_command to handle
    except Exception as e:
        logger.error(f"Error showing workflow: {e}", exc_info=True)
        raise RuntimeError(f"Error showing workflow: {e}") from e

def _handle_workflow_generation(service: 'DayhoffService', description: str) -> None:
    """Generates a workflow using LLM based on description. Prints output."""
    if not service.LLM_CLIENTS_AVAILABLE: # Check flag on service instance
        service.console.print("[error]LLM client libraries not installed or found. Cannot generate workflow.[/error]")
        service.console.print("Please ensure necessary packages like 'openai' or 'anthropic' are installed.")
        return None
        
    try:
        # Check if LLM is configured
        llm_config = service.config.get_llm_config()
        if not llm_config.get('api_key'):
            service.console.print("[error]LLM API Key is not configured. Cannot generate workflow.[/error]")
            service.console.print("Use '/config set LLM api_key <your_key>' to configure.")
            return None
            
        if not llm_config.get('model'):
            service.console.print("[error]LLM Model is not configured. Cannot generate workflow.[/error]")
            service.console.print("Use '/config set LLM model <model_name>' to configure.")
            return None
            
        # Get current workflow language
        language = service.config.get_workflow_language()
        service.console.print(f"Generating {language.upper()} workflow based on your description...", style="info")
        
        # Show spinner during generation
        with Live(Spinner("dots", text="Generating workflow with LLM..."), console=service.console, transient=True, refresh_per_second=10) as live:
            workflow_generator = service._get_workflow_generator()
            result = workflow_generator.generate_workflow(description)
            
        if not result.get('success', False):
            error_msg = result.get('error', 'Unknown error')
            service.console.print(f"[error]Failed to generate workflow:[/error] {error_msg}")
            return None
            
        workflow = result.get('workflow', {})
        
        # Display success message and workflow details
        service.console.print(f"[bold green]✅ Workflow generated successfully![/bold green]")
        
        details = [
            f"[bold]Name:[/bold] {workflow.get('name', 'Untitled')}",
            f"[bold]Language:[/bold] {workflow.get('language', 'unknown').upper()}",
            f"[bold]Saved to:[/bold] {workflow.get('file', 'Unknown')}",
            "",
            f"[bold]Summary:[/bold] {workflow.get('summary', 'No summary available')}"
        ]
        
        service.console.print(Panel("\n".join(details), title="Generated Workflow", border_style="green"))
        
        # Try to read and display the workflow file
        file_path = workflow.get('file')
        if file_path and os.path.exists(file_path):
            try:
                with open(file_path, 'r') as f:
                    workflow_code = f.read()
                
                # Use Rich Markdown for syntax highlighting
                try:
                    md = Markdown(f"```{language}\n{workflow_code}\n```", code_theme="default")
                    service.console.print(Panel(md, title=f"{language.upper()} Workflow Code", border_style="cyan"))
                except Exception:
                     logger.warning("Failed to render workflow code as markdown, showing plain text.")
                     service.console.print(Panel(workflow_code, title=f"{language.upper()} Workflow Code (Plain Text)", border_style="cyan"))

            except Exception as e:
                service.console.print(f"[error]Error reading generated workflow file:[/error] {e}")
        
        service.console.print("\nUse '/workflow list' to see all generated workflows.", style="dim")
        return None
        
    except Exception as e:
        logger.error(f"Error generating workflow: {e}", exc_info=True)
        # Raise runtime error so the REPL can catch and display it
        raise RuntimeError(f"Error generating workflow: {e}") from e

def _handle_workflow_delete(service: 'DayhoffService', index: int) -> None:
    """Deletes a specific workflow. Prints output."""
    try:
        workflow_generator = service._get_workflow_generator()
        result = workflow_generator.delete_workflow(index) # Call backend method

        if result.get('success', False):
            workflow_name = result.get('name', 'Unknown')
            service.console.print(f"[bold green]✅ Workflow #{index} ('{workflow_name}') deleted successfully.[/bold green]")
            if 'warning' in result: # Show warning if file deletion failed but index was updated
                 service.console.print(f"[warning]Warning:[/warning] {result['warning']}")
        else:
            error_msg = result.get('error', 'Unknown error')
            # Raise specific errors if possible (IndexError, FileNotFoundError)
            if "index" in error_msg.lower() and "out of range" in error_msg.lower():
                 raise IndexError(error_msg)
            elif "file not found" in error_msg.lower():
                 raise FileNotFoundError(error_msg)
            else:
                 service.console.print(f"[error]Failed to delete workflow #{index}:[/error] {error_msg}")

        return None

    except IndexError as e:
        raise e # Re-raise for execute_command to handle
    except FileNotFoundError as e:
         raise e # Re-raise
    except Exception as e:
        logger.error(f"Error deleting workflow #{index}: {e}", exc_info=True)
        raise RuntimeError(f"Error deleting workflow: {e}") from e

def _handle_workflow_inputs(service: 'DayhoffService', index: int) -> None:
    """Lists required inputs for a specific workflow. Prints output."""
    try:
        workflow_generator = service._get_workflow_generator()
        result = workflow_generator.get_workflow_inputs(index) # Call backend method

        if result.get('success', False):
            inputs = result.get('inputs', [])
            workflow_name = result.get('name', 'Unknown')
            language = result.get('language', 'unknown')

            if not inputs:
                service.console.print(f"Workflow #{index} ('{workflow_name}') in {language.upper()} appears to have no defined inputs (or parsing failed).", style="info")
                return None

            table = Table(title=f"Required Inputs for Workflow #{index} ('{workflow_name}') - {language.upper()}", show_header=True, header_style="bold magenta")
            table.add_column("Input Name", style="bold cyan")
            table.add_column("Type", style="yellow")
            table.add_column("Description / Notes", style="dim")

            for wf_input in inputs:
                table.add_row(
                    wf_input.get('name', 'N/A'),
                    wf_input.get('type', 'unknown'),
                    wf_input.get('description', '')
                )
            service.console.print(table)

        else:
            error_msg = result.get('error', 'Unknown error')
            # Raise specific errors if possible
            if "index" in error_msg.lower() and "out of range" in error_msg.lower():
                 raise IndexError(error_msg)
            elif "file not found" in error_msg.lower():
                 raise FileNotFoundError(error_msg)
            elif "parsing failed" in error_msg.lower() or "not implemented" in error_msg.lower():
                 service.console.print(f"[warning]Could not parse inputs for workflow #{index}:[/warning] {error_msg}")
            else:
                 service.console.print(f"[error]Failed to get inputs for workflow #{index}:[/error] {error_msg}")

        return None

    except IndexError as e:
        raise e # Re-raise for execute_command
    except FileNotFoundError as e:
         raise e # Re-raise
    except Exception as e:
        logger.error(f"Error getting inputs for workflow #{index}: {e}", exc_info=True)
        raise RuntimeError(f"Error getting workflow inputs: {e}") from e

def _handle_workflow_visualize(service: 'DayhoffService', index: int) -> None:
    """Generates a DOT file visualizing a specific workflow. Prints output."""
    try:
        workflow_generator = service._get_workflow_generator()
        details_result = workflow_generator.get_workflow_details(index)

        if not details_result['success']:
            error_msg = details_result.get('error', 'Unknown error')
            if "index" in error_msg.lower() and "out of range" in error_msg.lower():
                 raise IndexError(error_msg)
            else:
                 service.console.print(f"[error]Failed to get workflow details:[/error] {error_msg}")
                 return None

        workflow = details_result['workflow']
        file_path_str = workflow.get('file')
        language = workflow.get('language', 'unknown')
        workflow_name = workflow.get('name', 'Untitled')

        if not file_path_str:
            raise FileNotFoundError(f"No file path found for workflow index #{index}.")

        file_path = Path(file_path_str)
        if not file_path.exists():
            raise FileNotFoundError(f"Workflow file not found at {file_path_str}")

        try:
            with open(file_path, 'r') as f:
                workflow_code = f.read()
        except Exception as e:
            service.console.print(f"[error]Failed to read workflow file {file_path}: {e}[/error]")
            return None

        service.console.print(f"Generating visualization for workflow #{index} ('{workflow_name}') - {language.upper()}...", style="info")

        try:
            visualizer = WorkflowVisualizer()
        except ImportError as e:
             service.console.print(f"[error]Visualization failed: {e}[/error]")
             service.console.print("Please ensure 'graphviz' Python library and system tools are installed.")
             return None

        # Define output path (e.g., same directory, with .gv extension)
        dot_output_path = file_path.with_suffix('.gv')

        viz_result = visualizer.generate_dot(workflow_code, language, dot_output_path)

        if viz_result.get('success'):
            saved_path = viz_result.get('path')
            service.console.print(f"[bold green]✅ Workflow visualization DOT file generated successfully:[/bold green]")
            service.console.print(f"   {saved_path}")
            service.console.print(f"You can render this using Graphviz, e.g.: [cyan]dot -Tsvg {saved_path} -o {dot_output_path.with_suffix('.svg')}[/cyan]")
        else:
            error_msg = viz_result.get('error', 'Unknown visualization error')
            service.console.print(f"[error]Failed to generate visualization:[/error] {error_msg}")

        return None

    except IndexError as e:
        raise e # Re-raise for execute_command
    except FileNotFoundError as e:
         raise e # Re-raise
    except Exception as e:
        logger.error(f"Error visualizing workflow #{index}: {e}", exc_info=True)
        raise RuntimeError(f"Error visualizing workflow: {e}") from e
