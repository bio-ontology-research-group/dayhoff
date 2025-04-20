import os
import logging
import argparse
import shlex
from typing import List, Optional, TYPE_CHECKING
from pathlib import Path

from rich.panel import Panel
from rich.text import Text
from rich.columns import Columns

# Import from new location - Assuming utils is at the same level as handlers
from ..utils.coloring import colorize_filename

if TYPE_CHECKING:
    from ..service import DayhoffService # Import DayhoffService for type hinting

logger = logging.getLogger(__name__)

# --- File System Handlers ---
def handle_fs_head(service: 'DayhoffService', args: List[str]) -> Optional[str]:
    """Handles the /fs_head command. Prints output directly."""
    parser = service._create_parser("fs_head", service._command_map['fs_head']['help'], add_help=True)
    parser.add_argument("file_path", help="Path to the local file")
    parser.add_argument("num_lines", type=int, nargs='?', default=10, help="Number of lines to show (default: 10)")

    try:
        parsed_args = parser.parse_args(args)

        if parsed_args.num_lines <= 0:
            # Use parser.error for consistency, requires ArgumentParser subclass override
            # For now, raise ArgumentError manually
            raise argparse.ArgumentError(parser._get_action("num_lines"), "Number of lines must be positive.")

        # Resolve the file path relative to the *local* CWD
        target_path = Path(service.local_cwd) / parsed_args.file_path
        abs_path = target_path.resolve() # Get absolute path

        # Check existence using resolved absolute path
        if not abs_path.is_file():
             raise FileNotFoundError(f"File not found at '{abs_path}'")

        # Use the absolute path with the file inspector
        lines = list(service.file_inspector.head(str(abs_path), parsed_args.num_lines))

        if not lines:
            service.console.print(f"File is empty: {abs_path}", style="info")
            return None

        dirname = str(abs_path.parent)
        basename = abs_path.name
        colored_basename = colorize_filename(basename, is_dir=False)
        header_text = Text.assemble(f"First {len(lines)} lines of '", dirname + os.path.sep, colored_basename, "':")

        # Use capture console only if we need the string value later, otherwise print directly
        service.console.print(Panel("\n".join(lines), title=header_text, border_style="cyan", expand=False))
        return None # Output printed directly

    except argparse.ArgumentError as e:
        raise e # Re-raise for execute_command
    except FileNotFoundError as e:
         raise e # Re-raise
    except SystemExit:
         return None # Help was printed
    except Exception as e:
        logger.error(f"Error reading head of file {args[0] if args else ''}", exc_info=True)
        raise RuntimeError(f"Error reading file head: {e}") from e

def handle_ls(service: 'DayhoffService', args: List[str]) -> Optional[str]:
    """Handles the /ls command locally or remotely. Prints output."""
    parser = service._create_parser("ls", service._command_map['ls']['help'], add_help=True)
    # Allow unknown args for now, just ignore them
    parsed_args, unknown_args = parser.parse_known_args(args)
    if unknown_args:
         logger.warning(f"Ignoring unsupported arguments/options for /ls: {unknown_args}")

    try:
        status = service.get_status()
        items = []

        if status['mode'] == 'connected':
            # --- Remote LS ---
            if not service.active_ssh_manager or service.remote_cwd is None:
                raise ConnectionError("Internal state error: Connected mode but no SSH manager or remote CWD.")

            # Use find command to get type and name, handle potential errors
            # %Y = item type (f=file, d=dir, l=link), %P = name relative to starting point (.)
            # Use -print0 for safe handling of names
            find_cmd = f"find . -mindepth 1 -maxdepth 1 -printf '%Y\\0%P\\0'"
            full_command = f"cd {shlex.quote(service.remote_cwd)} && {find_cmd}"

            try:
                logger.info(f"Fetching remote file list for /ls with command: {full_command}")
                output = service.active_ssh_manager.execute_command(full_command, timeout=30)

                if output:
                    # Split by null character, pairs of type and name
                    parts = output.strip('\0').split('\0')
                    if len(parts) % 2 != 0:
                         logger.warning(f"Unexpected output format from remote find (odd number of parts): {output}")
                         # Attempt to process anyway or raise error? Raise for now.
                         raise RuntimeError(f"Unexpected output format from remote find: {output}")

                    for i in range(0, len(parts), 2):
                         type_char = parts[i]
                         name = parts[i+1]
                         is_dir = (type_char == 'd')
                         # Could handle 'l' for links differently if needed
                         items.append(colorize_filename(name, is_dir=is_dir))

            except (ConnectionError, TimeoutError, RuntimeError) as e:
                # Let outer handler deal with connection/timeout issues
                # RuntimeError will be raised if `find` fails (e.g., permissions)
                raise e
            except Exception as e:
                logger.error(f"Unexpected error during remote /ls execution: {e}", exc_info=True)
                raise RuntimeError(f"Unexpected error listing remote directory: {e}") from e

        else:
            # --- Local LS ---
            logger.info(f"Fetching local file list for /ls in directory: {service.local_cwd}")
            try:
                for entry in sorted(os.listdir(service.local_cwd), key=str.lower):
                    try:
                        full_path = os.path.join(service.local_cwd, entry)
                        is_dir = os.path.isdir(full_path)
                        # Could add check for os.islink if needed
                        items.append(colorize_filename(entry, is_dir=is_dir))
                    except OSError as item_err: # Handle errors accessing specific items (e.g., permissions)
                         logger.warning(f"Could not stat item '{entry}' in {service.local_cwd}: {item_err}")
                         items.append(Text(f"{entry} (error)", style="error"))
            except FileNotFoundError:
                 # The CWD itself doesn't exist (e.g., deleted after start)
                 raise FileNotFoundError(f"Local directory not found: {service.local_cwd}")
            except PermissionError:
                 raise PermissionError(f"Permission denied listing local directory: {service.local_cwd}")
            except Exception as e:
                 logger.error(f"Unexpected error during local /ls execution: {e}", exc_info=True)
                 raise RuntimeError(f"Unexpected error listing local directory: {e}") from e

        # --- Display Results (Common for Local/Remote) ---
        current_dir_display = status['cwd']
        if not items:
            service.console.print(f"(Directory '{current_dir_display}' is empty)", style="info")
            return None

        # Sort by name (case-insensitive) - already sorted for local, sort remote here
        if status['mode'] == 'connected':
             items.sort(key=lambda text: text.plain.lower())

        # Display using Rich Columns
        columns = Columns(items, expand=True, equal=True, column_first=True)
        service.console.print(f"Contents of '{current_dir_display}':")
        service.console.print(columns)
        return None # Output printed

    except argparse.ArgumentError as e:
         raise e
    except SystemExit:
         return None # Help was printed

def handle_cd(service: 'DayhoffService', args: List[str]) -> Optional[str]:
    """Handles the /cd command locally or remotely. Prints output."""
    parser = service._create_parser("cd", service._command_map['cd']['help'], add_help=True)
    parser.add_argument("directory", help="The target directory")

    try:
        parsed_args = parser.parse_args(args)
        target_dir_arg = parsed_args.directory
        status = service.get_status()

        if status['mode'] == 'connected':
            # --- Remote CD ---
            if not service.active_ssh_manager or service.remote_cwd is None:
                raise ConnectionError("Internal state error: Connected mode but no SSH manager or remote CWD.")

            current_dir = service.remote_cwd
            # Command to attempt cd and then print the new working directory's absolute path using pwd -P
            # Check directory existence and type first for better error message
            check_dir_cmd = f"cd {shlex.quote(current_dir)} && test -d {shlex.quote(target_dir_arg)}"
            test_command = f"cd {shlex.quote(current_dir)} && cd {shlex.quote(target_dir_arg)} && pwd -P"
            logger.info(f"Attempting remote directory change to: {target_dir_arg}")

            try:
                # 1. Verify it's a directory first (execute_command will raise RuntimeError if test -d fails)
                service.active_ssh_manager.execute_command(check_dir_cmd, timeout=15)

                # 2. If directory check passes, get the new absolute path (execute_command raises RuntimeError if cd or pwd fails)
                new_dir_output = service.active_ssh_manager.execute_command(test_command, timeout=15)
                new_dir = new_dir_output.strip()

                # Basic validation: should be a non-empty string starting with '/'
                if not new_dir or not new_dir.startswith("/"):
                    logger.error(f"Failed to get pwd for remote directory '{target_dir_arg}'. 'pwd -P' command returned unexpected output: {new_dir_output}")
                    raise RuntimeError(f"Failed to change remote directory to '{target_dir_arg}'. Could not verify new path.")

                service.remote_cwd = new_dir
                logger.info(f"Successfully changed remote working directory to: {service.remote_cwd}")
                service.console.print(f"Remote working directory changed to: {service.remote_cwd}", style="info")
                return None # Output printed

            except (ConnectionError, TimeoutError) as e:
                 raise e # Let outer handler deal with these
            except RuntimeError as e:
                 # Catch runtime errors from execute_command (e.g., cd failed, test -d failed, pwd failed)
                 logger.error(f"Failed to change remote directory to '{target_dir_arg}': {e}", exc_info=False)
                 # Provide a clearer error message based on common failure points
                 if "test -d" in str(e) or "No such file or directory" in str(e) or "Not a directory" in str(e):
                      raise NotADirectoryError(f"Remote path is not a directory or does not exist: '{target_dir_arg}' (relative to {current_dir})") from e
                 elif "Permission denied" in str(e):
                      raise PermissionError(f"Permission denied accessing remote directory: '{target_dir_arg}' (relative to {current_dir})") from e
                 else:
                      raise RuntimeError(f"Failed to change remote directory to '{target_dir_arg}'. Error: {e}") from e
            except Exception as e:
                logger.error(f"Unexpected error changing remote directory to '{target_dir_arg}': {e}", exc_info=True)
                raise RuntimeError(f"Unexpected error changing remote directory: {e}") from e

        else:
            # --- Local CD ---
            logger.info(f"Attempting to change local directory from '{service.local_cwd}' to '{target_dir_arg}'")
            try:
                # Construct the target path relative to the current local CWD
                target_path = Path(service.local_cwd) / target_dir_arg
                # Use resolve(strict=True) which checks existence and resolves symlinks/..
                # This raises FileNotFoundError if it doesn't exist
                abs_path = target_path.resolve(strict=True)

                # Check if the resolved path is actually a directory
                if not abs_path.is_dir():
                     raise NotADirectoryError(f"Local path is not a directory: '{abs_path}'")

                # Update local CWD (no need for os.access check as resolve/is_dir handle permissions implicitly)
                service.local_cwd = str(abs_path)
                logger.info(f"Successfully changed local working directory to: {service.local_cwd}")
                service.console.print(f"Local working directory changed to: {service.local_cwd}", style="info")
                return None # Output printed

            except FileNotFoundError as e:
                 # Raised by resolve(strict=True) if path doesn't exist
                 raise FileNotFoundError(f"Local directory not found: '{target_path}'") from e
            except NotADirectoryError as e:
                 raise e # Re-raise
            except PermissionError as e: # Although less likely with resolve, catch defensively
                 raise PermissionError(f"Permission denied accessing local directory: '{target_path}'") from e
            except Exception as e:
                logger.error(f"Unexpected error changing local directory to '{target_dir_arg}': {e}", exc_info=True)
                raise RuntimeError(f"Unexpected error changing local directory: {e}") from e

    except argparse.ArgumentError as e:
         raise e
    except SystemExit:
         return None # Help was printed
