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
            # Match should be based on the part *after* the '/'
            cmd_text = parts[0][1:] # Text after '/'
            options = [cmd for cmd in COMMANDS if cmd.startswith(cmd_text)]
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
    # logger.debug(f"Commands available for completion: {COMMANDS}") # Use logger instead of print
    # --- End Diagnostic Print ---


    while True:
        try:
            # Get current status for the prompt
            status = service.get_status()
            if status['mode'] == 'connected':
                # Shorten host if possible (e.g., remove domain)
                short_host = status['host'].split('.')[0] if status['host'] else 'hpc'
                prompt = f"dayhoff[{status['user']}@{short_host}:{status['cwd']}]> "
            else:
                # Show ~ for home directory if applicable
                home_dir = os.path.expanduser("~")
                display_cwd = status['cwd']
                if display_cwd.startswith(home_dir):
                    display_cwd = "~" + display_cwd[len(home_dir):]
                prompt = f"dayhoff[local:{display_cwd}]> "

            # Use input() which now benefits from readline enhancements
            line = input(prompt)
            line = line.strip()

            if not line:
                continue
            if line.lower() in ['/exit', '/quit']:
                break

            if not line.startswith('/'):
                # Allow simple shell commands if not connected? Maybe not for now.
                # print("Error: Commands must start with '/' (e.g., /help).")
                # Treat non-slash commands as potential /hpc_run if connected, or error otherwise?
                # For now, stick to requiring '/'
                if status['mode'] == 'connected':
                     print("Error: Commands must start with '/'. Did you mean '/hpc_run ...'?")
                else:
                     print("Error: Commands must start with '/' (e.g., /help, /ls, /cd).")
                continue

            # Parse command and arguments
            try:
                parts = shlex.split(line)
            except ValueError as e:
                print(f"Error parsing command: {e}") # Handle unbalanced quotes etc.
                continue

            command = parts[0][1:] # Remove leading '/'
            args = parts[1:]

            # Execute command via service
            result = service.execute_command(command, args)
            # execute_command now handles printing its own output via console.print
            # if result: # Print result only if it's not empty/None and not handled by handler
            #     print(result)

        except KeyboardInterrupt:
            print("\nInterrupted. Type /exit or Ctrl+D to quit.") # Add newline for clarity
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
    # execute_command handles printing via console, so don't print result here
    # if result:
    #     print(result)

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
