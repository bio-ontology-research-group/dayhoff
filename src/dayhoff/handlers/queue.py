import logging
import argparse
import os
import shlex
from pathlib import Path
from typing import List, Optional, TYPE_CHECKING, Set

from rich.table import Table
from rich.text import Text

# Import from new location - Assuming utils is at the same level as handlers
from ..utils.coloring import colorize_filename

if TYPE_CHECKING:
    from ..service import DayhoffService # Import DayhoffService for type hinting

logger = logging.getLogger(__name__)

# --- File Queue Handlers ---

def handle_queue(service: 'DayhoffService', args: List[str]) -> Optional[str]:
    """Handles the /queue command with subparsers. Prints output directly."""
    parser = service._create_parser("queue", service._command_map['queue']['help'], add_help=True)
    subparsers = parser.add_subparsers(dest="subcommand", title="Subcommands",
                                       description="Valid subcommands for /queue",
                                       help="Action to perform on the file queue")

    # --- Subparser: add ---
    parser_add = subparsers.add_parser("add", help="Add file(s) or directory(s) (recursive) to the queue.", add_help=True)
    parser_add.add_argument("paths", nargs='+', help="One or more paths relative to the current working directory.")

    # --- Subparser: show ---
    parser_show = subparsers.add_parser("show", help="Display the files currently in the queue.", add_help=True)

    # --- Subparser: remove ---
    parser_remove = subparsers.add_parser("remove", help="Remove files from the queue by index.", add_help=True)
    parser_remove.add_argument("indices", nargs='+', type=int, help="One or more index numbers (from /queue show).")

    # --- Subparser: clear ---
    parser_clear = subparsers.add_parser("clear", help="Remove all files from the queue.", add_help=True)


    # --- Parse arguments ---
    try:
        # Handle case where no subcommand is given
        if not args:
             parser.print_help()
             return None

        parsed_args = parser.parse_args(args)

        # --- Execute subcommand logic ---
        if parsed_args.subcommand == "add":
            return _handle_queue_add(service, parsed_args.paths)
        elif parsed_args.subcommand == "show":
            return _handle_queue_show(service)
        elif parsed_args.subcommand == "remove":
             return _handle_queue_remove(service, parsed_args.indices)
        elif parsed_args.subcommand == "clear":
             return _handle_queue_clear(service)
        else:
             # Should not happen if subcommand is required/checked, but handle defensively
             parser.print_help()
             return None

    except argparse.ArgumentError as e:
        raise e # Re-raise for execute_command to handle
    except SystemExit:
         return None # Help was printed
    # Catch specific errors from queue handlers
    except FileNotFoundError as e: raise e
    except NotADirectoryError as e: raise e
    except PermissionError as e: raise e
    except IndexError as e: raise e # From remove handler
    except (ConnectionError, TimeoutError) as e: raise e # From remote operations
    except Exception as e:
        logger.error(f"Error during /queue {args}: {e}", exc_info=True)
        raise RuntimeError(f"Error executing queue command: {e}") from e


def _handle_queue_add(service: 'DayhoffService', paths_to_add: List[str]) -> None:
    """Adds files/directories to the queue. Prints output."""
    status = service.get_status()
    added_count = 0
    skipped_count = 0
    error_count = 0
    processed_dirs: Set[str] = set() # Track dirs to avoid re-processing if listed multiple times

    for relative_path in paths_to_add:
        try:
            abs_path, cwd = service._resolve_path(relative_path) # Use service helper
            path_type = service._get_path_type(abs_path) # Use service helper

            if path_type == 'file':
                if abs_path not in service.file_queue:
                    service.file_queue.append(abs_path)
                    service.console.print(f"Added file: {abs_path}", style="info")
                    added_count += 1
                else:
                    service.console.print(f"Skipped (already in queue): {abs_path}", style="dim")
                    skipped_count += 1
            elif path_type == 'directory':
                if abs_path in processed_dirs:
                     service.console.print(f"Skipped (directory already processed): {abs_path}", style="dim")
                     skipped_count += 1 # Count skipped dirs? Or just files? Let's count as 1 skip.
                     continue

                processed_dirs.add(abs_path)
                service.console.print(f"Scanning directory: {abs_path}...", style="info")
                subdir_files_added = 0
                subdir_files_skipped = 0

                if status['mode'] == 'connected':
                    # Remote recursive listing
                    found_files = service._list_remote_files_recursive(abs_path) # Use service helper
                else:
                    # Local recursive listing
                    found_files = []
                    for root, _, files in os.walk(abs_path):
                        for filename in files:
                            try:
                                 # Ensure correct absolute path construction
                                 file_abs_path = str(Path(root) / filename)
                                 # Redundant check, but safe: Check if it's actually a file
                                 if os.path.isfile(file_abs_path):
                                      found_files.append(file_abs_path)
                                 else: # Should not happen with files from os.walk
                                      logger.warning(f"os.walk listed non-file item? {file_abs_path}")
                            except OSError as walk_err:
                                 logger.warning(f"Error accessing file during local walk: {filename} in {root} - {walk_err}")
                                 # Should we count this as an error? For now, just log.


                # Add files found inside the directory
                for file_path in found_files:
                    if file_path not in service.file_queue:
                        service.file_queue.append(file_path)
                        subdir_files_added += 1
                    else:
                        subdir_files_skipped += 1

                added_count += subdir_files_added
                skipped_count += subdir_files_skipped
                service.console.print(f"  -> Added {subdir_files_added} files from directory {abs_path} ({subdir_files_skipped} skipped).", style="info")

        except FileNotFoundError as e:
             logger.warning(f"Could not add path '{relative_path}': {e}")
             service.console.print(f"[warning]Skipped (not found):[/warning] '{relative_path}' (in {status['cwd']})")
             error_count += 1
        except NotADirectoryError as e: # Should be caught by _get_path_type more specifically
             logger.warning(f"Path is not a file or directory '{relative_path}': {e}")
             service.console.print(f"[warning]Skipped (not a file/directory):[/warning] '{relative_path}'")
             error_count += 1
        except PermissionError as e:
             logger.warning(f"Permission denied for path '{relative_path}': {e}")
             service.console.print(f"[error]Skipped (permission denied):[/error] '{relative_path}'")
             error_count += 1
        except (ConnectionError, TimeoutError, RuntimeError) as e:
             logger.error(f"Error processing path '{relative_path}': {e}")
             service.console.print(f"[error]Error processing '{relative_path}': {e}[/error]")
             error_count += 1
             # Stop processing further paths if connection seems lost? Maybe not, try others.
        except Exception as e:
             logger.error(f"Unexpected error processing path '{relative_path}': {e}", exc_info=True)
             service.console.print(f"[error]Unexpected error processing '{relative_path}': {e}[/error]")
             error_count += 1

    service.console.print(f"\nQueue add summary: Added {added_count}, Skipped {skipped_count}, Errors {error_count}. Total in queue: {len(service.file_queue)}", style="bold")
    return None # Output printed

def _handle_queue_show(service: 'DayhoffService') -> None:
    """Displays the current file queue. Prints output."""
    if not service.file_queue:
        service.console.print("File queue is empty.", style="info")
        return None

    table = Table(title=f"File Queue ({len(service.file_queue)} items)", show_header=True, header_style="bold magenta")
    table.add_column("Index", style="dim", width=6, justify="right")
    table.add_column("Absolute Path")

    # Use colorize_filename for the path display
    for i, file_path in enumerate(service.file_queue):
         # Simple coloring based on file extension from the absolute path
         # We don't know if it's local or remote here, assume file
         colored_name = colorize_filename(os.path.basename(file_path))
         # Display the full path but color the basename
         dir_name = os.path.dirname(file_path)
         display_path = Text.assemble(dir_name + os.path.sep, colored_name)
         table.add_row(str(i + 1), display_path) # 1-based index for user

    service.console.print(table)
    return None # Output printed

def _handle_queue_remove(service: 'DayhoffService', indices_to_remove: List[int]) -> None:
    """Removes files from the queue by 1-based index. Prints output."""
    if not service.file_queue:
        service.console.print("File queue is already empty.", style="warning")
        return None

    current_queue_size = len(service.file_queue)
    # Convert 1-based input indices to 0-based list indices
    # Validate indices immediately
    valid_zero_based_indices: Set[int] = set()
    invalid_inputs: List[str] = []

    for index_arg in indices_to_remove:
        if 1 <= index_arg <= current_queue_size:
            valid_zero_based_indices.add(index_arg - 1)
        else:
            invalid_inputs.append(str(index_arg))

    if invalid_inputs:
        service.console.print(f"[error]Invalid index numbers provided:[/error] {', '.join(invalid_inputs)}. Use indices from 1 to {current_queue_size}.", style="error")
        # Optionally, proceed with valid indices or stop? Let's proceed.
        # raise ValueError(f"Invalid index numbers provided: {', '.join(invalid_inputs)}. Use indices from 1 to {current_queue_size}.")


    if not valid_zero_based_indices:
         if not invalid_inputs: # No valid indices and no invalid inputs probably means no indices given? Argparse handles.
              service.console.print("No valid indices provided to remove.", style="warning")
         return None # Nothing to remove

    # Remove items by index, working from highest index downwards to avoid shifting issues
    removed_count = 0
    removed_items_display = []
    sorted_indices = sorted(list(valid_zero_based_indices), reverse=True)

    for index in sorted_indices:
        try:
            removed_item = service.file_queue.pop(index)
            removed_items_display.append(os.path.basename(removed_item)) # Show basename for brevity
            removed_count += 1
            logger.debug(f"Removed item at index {index+1}: {removed_item}")
        except IndexError:
             # Should not happen due to validation, but handle defensively
             logger.error(f"Internal error: IndexError removing previously validated index {index}")
             service.console.print(f"[error]Internal error removing index {index+1}. Queue may be inconsistent.[/error]", style="error")

    if removed_count > 0:
         service.console.print(f"Removed {removed_count} item(s): {', '.join(removed_items_display)}.", style="info")
         service.console.print(f"Queue now contains {len(service.file_queue)} item(s).", style="info")
    elif invalid_inputs: # Only invalid inputs were given
         service.console.print("No items removed due to invalid indices.", style="warning")
    # else: # No valid or invalid indices provided scenario (should be handled earlier)

    return None # Output printed


def _handle_queue_clear(service: 'DayhoffService') -> None:
    """Clears the entire file queue. Prints output."""
    queue_size_before = len(service.file_queue)
    if queue_size_before == 0:
         service.console.print("File queue is already empty.", style="info")
    else:
         service.file_queue.clear()
         logger.info(f"Cleared {queue_size_before} items from the file queue.")
         service.console.print(f"Cleared {queue_size_before} items from the file queue.", style="info")
    return None # Output printed
