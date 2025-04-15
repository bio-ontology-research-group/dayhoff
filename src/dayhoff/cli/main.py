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

COMMANDS = [] # Will be populated by DayhoffService instance (without leading '/')

def setup_readline(service: DayhoffService):
    """Configures readline for history and autocompletion."""
    if readline is None:
        logger.warning("Readline module not available. Command history and completion disabled.")
        return

    global COMMANDS
    # Get available commands from the service, WITHOUT the leading '/'
    # Store them sorted for consistent completion order
    COMMANDS = sorted(service.get_available_commands())

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
        parts = line.split(' ', 1) # Split into command part and the rest

        # Only complete the command if it starts with '/' and there are no spaces yet
        # 'text' is the part of the word being completed (e.g., 'he' in '/he')
        if line.startswith('/') and ' ' not in parts[0]:
            # Find commands in our list that start with the text being completed
            options = [cmd for cmd in COMMANDS if cmd.startswith(text)]
            if state < len(options):
                # Return the full command name (without '/')
                # Readline will append this to the '/' already typed, replacing 'text'
                return options[state]
            else:
                return None
        # Placeholder for potential argument completion in the future
        # elif ' ' in line:
        #     # Logic to complete arguments based on the command
        #     pass
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
    # Print the commands loaded by this specific service instance and used for completion
    print(f"[DEBUG] Commands available for completion: {COMMANDS}")
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
