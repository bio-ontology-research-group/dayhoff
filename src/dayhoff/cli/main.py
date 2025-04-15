import click
import shlex
import logging
import sys
import os

# Import readline for command history and completion (if available)
try:
    import readline
except ImportError:
    # readline is not available on Windows by default
    readline = None # type: ignore

from ..service import DayhoffService

# Configure logging for the CLI
logger = logging.getLogger(__name__)
# Example basic config, could be more sophisticated (e.g., file logging)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# --- Readline Setup for Autocompletion ---

COMMANDS = [] # Will be populated by DayhoffService instance

def setup_readline(service: DayhoffService):
    """Configures readline for history and autocompletion."""
    if readline is None:
        logger.warning("Readline module not available. Command history and completion disabled.")
        return

    global COMMANDS
    # Get available commands from the service, prepend '/'
    COMMANDS = ['/' + cmd for cmd in service.get_available_commands()]

    # --- History ---
    histfile = os.path.join(os.path.expanduser("~"), ".dayhoff_history")
    try:
        readline.read_history_file(histfile)
        # default history len is -1 (infinite), which may grow unruly
        readline.set_history_length(1000)
    except FileNotFoundError:
        pass # No history file yet is fine
    except Exception as e:
        logger.warning(f"Could not read history file {histfile}: {e}")

    import atexit
    atexit.register(readline.write_history_file, histfile)

    # --- Autocompletion ---
    def completer(text, state):
        """Readline completer function."""
        line = readline.get_line_buffer()
        # Only complete at the beginning of the line or after a space if needed later
        # For now, only complete the command itself (starting with '/')
        if line.startswith('/'):
            prefix = line.split(' ')[0] # Get the command part
            options = [cmd for cmd in COMMANDS if cmd.startswith(prefix)]
            if state < len(options):
                return options[state]
            else:
                return None
        return None # No completion otherwise

    readline.set_completer(completer)
    # Use tab for completion
    if 'libedit' in readline.__doc__: # Handle macOS libedit differences
        readline.parse_and_bind("bind ^I rl_complete")
    else:
        readline.parse_and_bind("tab: complete")

# --- Click CLI Definition ---

@click.group()
def cli():
    """Dayhoff Bioinformatics Assistant CLI."""
    pass

@cli.command()
def repl():
    """Start the Dayhoff interactive REPL."""
    service = DayhoffService()
    setup_readline(service) # Setup history and completion
    print("Welcome to the Dayhoff REPL. Type '/help' for commands, '/exit' or Ctrl+D to quit.")

    # --- Diagnostic Print ---
    # Print the commands loaded by this specific service instance
    loaded_commands = service.get_available_commands()
    print(f"[DEBUG] Loaded commands: {sorted(loaded_commands)}")
    # --- End Diagnostic Print ---


    while True:
        try:
            # Use input() which now benefits from readline enhancements
            line = input("dayhoff> ")
            line = line.strip()

            if not line:
                continue
            if line.lower() in ['/exit', '/quit']:
                break

            if not line.startswith('/'):
                print("Error: Commands must start with '/' (e.g., /help).")
                continue

            # Parse command and arguments
            parts = shlex.split(line)
            command = parts[0][1:] # Remove leading '/'
            args = parts[1:]

            # Execute command via service
            result = service.execute_command(command, args)
            if result: # Print result only if it's not empty/None
                print(result)

        except KeyboardInterrupt:
            print("\nInterrupted. Type /exit or Ctrl+D to quit.")
        except EOFError:
            print("\nExiting.")
            break
        except Exception as e:
            # Catch unexpected errors in the REPL loop itself
            logger.error(f"Unexpected error in REPL: {e}", exc_info=True)
            print(f"An unexpected error occurred: {e}")


@cli.command()
@click.argument('command')
@click.argument('args', nargs=-1)
def execute(command, args):
    """Execute a single Dayhoff command non-interactively."""
    service = DayhoffService()
    # Reconstruct args list if needed (Click might handle spaces okay)
    # For simplicity, assume args are passed correctly by Click
    result = service.execute_command(command, list(args))
    if result:
        print(result)

# Example of how other subcommands could be added
# @cli.command()
# @click.option('--path', default='.', help='Path to analyze.')
# def analyze(path):
#     """Perform automated analysis (placeholder)."""
#     click.echo(f"Analyzing path: {path}")
#     # service = DayhoffService()
#     # result = service.execute_command("analyze", [path]) ...

if __name__ == '__main__':
    # This allows running the CLI directly using `python -m dayhoff.cli.main`
    cli()
