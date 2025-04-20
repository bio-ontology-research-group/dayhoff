import logging
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional
import re
import json # Added import

# Attempt to import graphviz
try:
    import graphviz
    GRAPHVIZ_AVAILABLE = True
except ImportError:
    graphviz = None # type: ignore
    GRAPHVIZ_AVAILABLE = False

# Attempt to import ruamel.yaml for CWL parsing
try:
    from ruamel.yaml import YAML
    RUAMEL_AVAILABLE = True
except ImportError:
    YAML = None # type: ignore
    RUAMEL_AVAILABLE = False

logger = logging.getLogger(__name__)

class WorkflowVisualizer:
    """Generates graph visualizations (DOT format) for workflows."""

    def __init__(self):
        if not GRAPHVIZ_AVAILABLE:
            raise ImportError("The 'graphviz' library is required for visualization. Please install it (`pip install graphviz`) and ensure Graphviz is installed system-wide.")

    def generate_dot(self, workflow_code: str, language: str, output_path: Path) -> Dict[str, Any]:
        """
        Generates a DOT file representing the workflow structure.

        Args:
            workflow_code: The string content of the workflow file.
            language: The workflow language (e.g., 'cwl', 'nextflow').
            output_path: The Path object where the DOT file should be saved.

        Returns:
            Dictionary with 'success': bool and 'path': str or 'error': str.
        """
        language = language.lower()
        dot = None
        error_msg = None

        try:
            if language == 'cwl':
                dot = self._generate_cwl_dot(workflow_code)
            # Add elif blocks for other languages here if needed
            # elif language == 'nextflow':
            #     dot = self._generate_nextflow_dot(workflow_code)
            else:
                error_msg = f"Visualization for language '{language}' is not yet implemented."
                logger.warning(error_msg)
                return {'success': False, 'error': error_msg}

            if dot:
                dot.render(outfile=str(output_path), view=False, cleanup=True) # Saves the .gv file
                logger.info(f"Successfully generated DOT file: {output_path}")
                return {'success': True, 'path': str(output_path)}
            else:
                # This case might occur if parsing succeeded but graph generation failed internally
                error_msg = f"Graph generation failed for language '{language}' for unknown reasons."
                logger.error(error_msg)
                return {'success': False, 'error': error_msg}

        except ImportError as e: # Catch missing ruamel.yaml specifically
             logger.error(f"Failed to generate CWL graph: {e}", exc_info=True)
             return {'success': False, 'error': f"Failed to generate CWL graph: {e}"}
        except Exception as e:
            logger.error(f"Error generating DOT file for {language}: {e}", exc_info=True)
            return {'success': False, 'error': f"Error generating DOT graph: {e}"}

    def _generate_cwl_dot(self, code: str) -> Optional[graphviz.Digraph]:
        """Generates a graphviz.Digraph object for a CWL workflow."""
        if not RUAMEL_AVAILABLE:
            raise ImportError("Cannot parse CWL for visualization: ruamel.yaml not installed.")

        yaml = YAML(typ='safe')
        try:
            data = yaml.load(code)
        except Exception as e:
            raise ValueError(f"Failed to parse CWL YAML for visualization: {e}") from e

        if not isinstance(data, dict) or data.get('class') != 'Workflow':
            raise ValueError("Content is not a valid CWL Workflow object.")

        wf_id = data.get('id', 'workflow')
        wf_label = data.get('label', wf_id)
        dot = graphviz.Digraph(name=wf_id, comment=wf_label, graph_attr={'label': wf_label, 'labelloc': 't', 'fontsize': '14'})
        dot.attr(rankdir='LR') # Left-to-right layout

        # --- Workflow Inputs ---
        with dot.subgraph(name='cluster_inputs', graph_attr={'label': 'Workflow Inputs', 'style': 'filled', 'color': 'lightgrey'}) as inputs_subgraph:
            inputs_subgraph.attr(rank='source') # Try to place inputs on the left
            cwl_inputs = data.get('inputs', {})
            if isinstance(cwl_inputs, dict):
                for name, details in cwl_inputs.items():
                    label = f"{name}\n({self._format_type(details.get('type', 'any'))})"
                    inputs_subgraph.node(f"input_{name}", label=label, shape='box', style='filled', fillcolor='lightblue')

        # --- Workflow Outputs ---
        with dot.subgraph(name='cluster_outputs', graph_attr={'label': 'Workflow Outputs', 'style': 'filled', 'color': 'lightgrey'}) as outputs_subgraph:
            outputs_subgraph.attr(rank='sink') # Try to place outputs on the right
            cwl_outputs = data.get('outputs', {})
            if isinstance(cwl_outputs, dict):
                for name, details in cwl_outputs.items():
                    label = f"{name}\n({self._format_type(details.get('type', 'any'))})"
                    outputs_subgraph.node(f"output_{name}", label=label, shape='box', style='filled', fillcolor='lightgreen')

        # --- Workflow Steps ---
        cwl_steps = data.get('steps', {})
        if isinstance(cwl_steps, dict):
            for step_id, step_details in cwl_steps.items():
                step_label = step_details.get('label', step_id)
                # Create a cluster subgraph for each step
                with dot.subgraph(name=f'cluster_{step_id}') as step_subgraph:
                    step_subgraph.attr(label=step_label, style='filled', color='beige')
                    step_subgraph.node(step_id, label=step_label, shape='ellipse') # Central node for the step itself

                    # Step Inputs
                    step_inputs = step_details.get('in', {})
                    if isinstance(step_inputs, dict):
                        for in_name, source in step_inputs.items():
                            # Source can be string (workflow input or other step output) or dict (default value)
                            if isinstance(source, str):
                                source_parts = source.split('/')
                                if len(source_parts) == 1: # Workflow input
                                    source_node = f"input_{source_parts[0]}"
                                    dot.edge(source_node, step_id, label=in_name)
                                elif len(source_parts) == 2: # Output of another step
                                    source_step_id = source_parts[0]
                                    source_step_output_name = source_parts[1]
                                    # Edge from source step node to current step node
                                    dot.edge(source_step_id, step_id, label=f"{source_step_output_name} -> {in_name}")
                            elif isinstance(source, dict) and 'default' in source:
                                # Represent default value? Maybe skip edge for simplicity
                                pass
                            elif isinstance(source, list): # Multiple sources
                                 for src_item in source:
                                     if isinstance(src_item, str):
                                         src_parts = src_item.split('/')
                                         if len(src_parts) == 1:
                                             dot.edge(f"input_{src_parts[0]}", step_id, label=in_name)
                                         elif len(src_parts) == 2:
                                             dot.edge(src_parts[0], step_id, label=f"{src_parts[1]} -> {in_name}")


                    # Step Outputs (Implicitly connected via edges from source steps)
                    # We don't explicitly draw step output nodes unless they connect to workflow outputs

        # --- Connect Steps to Workflow Outputs ---
        if isinstance(cwl_outputs, dict):
            for out_name, details in cwl_outputs.items():
                source = details.get('outputSource')
                if isinstance(source, str):
                    source_parts = source.split('/')
                    if len(source_parts) == 2:
                        source_step_id = source_parts[0]
                        source_step_output_name = source_parts[1]
                        target_node = f"output_{out_name}"
                        dot.edge(source_step_id, target_node, label=source_step_output_name)

        return dot

    def _format_type(self, cwl_type: Any) -> str:
        """Helper to format CWL type definitions for display."""
        if isinstance(cwl_type, str):
            return cwl_type
        elif isinstance(cwl_type, list):
            # Handle optional types (['null', 'typename']) and arrays
            if 'null' in cwl_type:
                non_null = [t for t in cwl_type if t != 'null']
                if len(non_null) == 1:
                    return f"{self._format_type(non_null[0])}?"
            return "|".join(self._format_type(t) for t in cwl_type)
        elif isinstance(cwl_type, dict):
            if cwl_type.get('type') == 'array':
                return f"Array<{self._format_type(cwl_type.get('items', 'any'))}>"
            elif cwl_type.get('type') == 'record':
                return f"Record<{cwl_type.get('name', '')}>"
            # Add other complex types if needed
            return json.dumps(cwl_type) # Fallback
        return str(cwl_type)

    # Placeholder for other language parsers
    # def _generate_nextflow_dot(self, code: str) -> Optional[graphviz.Digraph]:
    #     logger.warning("Nextflow visualization is not yet implemented.")
    #     return None
