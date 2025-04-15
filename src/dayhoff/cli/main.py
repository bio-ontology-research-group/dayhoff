import shlex
from ..service import DayhoffService

# Instantiate the service once
service = DayhoffService()

def run_repl():
    """Runs the Dayhoff Read-Eval-Print Loop (REPL)."""
    print("Welcome to the Dayhoff REPL. Type /help for commands, /quit or /exit to exit.")
    while True:
        try:
            raw_input = input("dayhoff> ")
            stripped_input = raw_input.strip()

            if not stripped_input:
                continue

            if stripped_input.lower() in ["/quit", "/exit"]:
                print("Exiting Dayhoff REPL.")
                break

            if not stripped_input.startswith('/'):
                print("Error: Commands must start with '/' (e.g., /help, /execute ...)")
                continue

            # Use shlex to handle quoted arguments properly
            parts = shlex.split(stripped_input)
            command = parts[0][1:]  # Remove leading '/'
            args = parts[1:]

            # --- Argument Parsing Adaptation ---
            # The original code expected key=value pairs.
            # The REPL now passes a list of strings (args).
            # We will pass this list directly. The `execute_command`
            # method in DayhoffService will need to be able to handle
            # this list of arguments appropriately for each command.
            # For simplicity here, we are not converting them back to a dict.
            # If specific commands *require* key=value, the parsing logic
            # here or within execute_command would need refinement.

            # Example: If input is "/run_analysis file.txt --threshold 0.5"
            # command = "run_analysis"
            # args = ["file.txt", "--threshold", "0.5"]

            result = service.execute_command(command, args)
            if result is not None:
                print(result)

        except EOFError:
            # Handle Ctrl+D as an exit signal
            print("\nExiting Dayhoff REPL.")
            break
        except KeyboardInterrupt:
            # Handle Ctrl+C gracefully
            print("\nOperation cancelled by user. Type /quit or /exit to exit.")
        except Exception as e:
            print(f"An error occurred: {e}")
            # Optionally add more detailed error logging or handling here

if __name__ == "__main__":
    run_repl()
