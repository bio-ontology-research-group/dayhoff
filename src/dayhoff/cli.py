import click
import readline
import subprocess
from typing import List, Optional
from pathlib import Path

class DayhoffCLI:
    """Interactive CLI interface for Dayhoff"""
    
    def __init__(self):
        self.commands = {
            '/help': self.show_help,
            '/explore': self.explore,
            '/workflow': self.generate_workflow,
            '/test': self.run_tests,
            '/exit': self.exit_cli,
            '/quit': self.exit_cli  # Add /quit as alias
        }
        self.setup_autocomplete()
        self.test_commands = {
            'cli': 'python examples/test_cli.py',
            'config': 'python examples/test_config.py',
            'fs': 'python examples/test_file_explorer.py',
            'hpc': 'python examples/test_hpc_bridge.py',
            'ssh': 'python examples/test_ssh_connection.py',
            'remote-fs': 'python examples/test_remote_fs.py',
            'all': 'python -m pytest examples/'
        }
        
    def setup_autocomplete(self):
        """Set up command autocompletion and history"""
        # Initialize readline if available
        try:
            import readline
            import rlcompleter
            
            # Set up tab completion
            readline.parse_and_bind("tab: complete")
            
            # Set up command completion
            def completer(text: str, state: int) -> Optional[str]:
                # Get matching commands
                options = [cmd for cmd in self.commands if cmd.startswith(text)]
                
                # Also autocomplete test names for /test command
                if text.startswith('/test '):
                    test_part = text[6:]
                    options = [f'/test {test}' for test in self.test_commands 
                             if test.startswith(test_part)]
                
                if state < len(options):
                    return options[state]
                return None
                
            readline.set_completer(completer)
            
            # Set up history
            readline.set_history_length(100)
            try:
                readline.read_history_file(".dayhoff_history")
            except FileNotFoundError:
                pass
                
            # Save history on exit
            import atexit
            atexit.register(readline.write_history_file, ".dayhoff_history")
            
        except ImportError:
            # Readline not available, skip advanced features
            pass
        
    def show_help(self, args: List[str]) -> None:
        """Show help information"""
        click.echo("Available commands:")
        for cmd in self.commands:
            click.echo(f"  {cmd}")
        
        click.echo("\nAvailable tests:")
        for test in self.test_commands:
            click.echo(f"  /test {test}")
            
    def explore(self, args: List[str]) -> None:
        """Explore bioinformatics data"""
        if not args:
            click.echo("Usage: /explore <path>")
            return
        path = args[0]
        # TODO: Implement filesystem exploration
        click.echo(f"Exploring {path}...")
        
    def generate_workflow(self, args: List[str]) -> None:
        """Generate bioinformatics workflow"""
        if not args:
            click.echo("Usage: /workflow <type>")
            return
        workflow_type = args[0]
        # TODO: Implement workflow generation
        click.echo(f"Generating {workflow_type} workflow...")
        
    def exit_cli(self, args: List[str]) -> None:
        """Exit the CLI"""
        click.echo("Exiting Dayhoff CLI...")
        raise SystemExit
        
    def process_command(self, input_str: str) -> None:
        """Process a command from user input"""
        parts = input_str.strip().split()
        if not parts:
            return
            
        command = parts[0]
        args = parts[1:]
        
        if command in self.commands:
            self.commands[command](args)
        else:
            click.echo(f"Unknown command: {command}. Type /help for available commands.")

    def run_tests(self, args: List[str]) -> None:
        """Run test suite"""
        if not args:
            click.echo("Usage: /test <test_name>")
            click.echo("Available tests:")
            for test in self.test_commands:
                click.echo(f"  {test}")
            return
        
        test_name = args[0]
        if test_name not in self.test_commands:
            click.echo(f"Unknown test: {test_name}")
            return
            
        command = self.test_commands[test_name]
        click.echo(f"Running test: {test_name}...")
        result = subprocess.run(command, shell=True)
        if result.returncode == 0:
            click.echo(f"Test {test_name} completed successfully!")
        else:
            click.echo(f"Test {test_name} failed with code {result.returncode}")

@click.command()
@click.option('--help', is_flag=True, help="Show help message and exit")
@click.option('--test', type=str, help="Run a specific test suite")
def main(help: bool, test: Optional[str]):
    """Interactive Dayhoff CLI interface"""
    if help:
        click.echo("Dayhoff CLI - Bioinformatics Assistant")
        click.echo("\nUsage:")
        click.echo("  python src/dayhoff/cli.py [--help] [--test <test_name>]")
        click.echo("\nInteractive commands:")
        click.echo("  /help       Show available commands")
        click.echo("  /explore    Explore bioinformatics data")
        click.echo("  /workflow   Generate bioinformatics workflows")
        click.echo("  /test       Run test suite")
        click.echo("  /exit       Exit the CLI")
        click.echo("\nAvailable tests:")
        for test_name in ['cli', 'config', 'fs', 'hpc', 'ssh', 'remote-fs', 'all']:
            click.echo(f"  {test_name}")
        return
        
    if test:
        cli = DayhoffCLI()
        cli.run_tests([test])
        return
        
    cli = DayhoffCLI()
    click.echo("Welcome to Dayhoff CLI! Type /help for available commands.")
    
    while True:
        try:
            # Set up readline for better input handling
            try:
                input_str = input("dayhoff> ")
            except EOFError:  # Handle Ctrl+D
                click.echo("\nGoodbye!")
                break
            except KeyboardInterrupt:
                # First Ctrl+C - show message
                click.echo("\nPress Ctrl+C again to exit or type /exit to quit.")
                try:
                    input_str = input("dayhoff> ")
                except KeyboardInterrupt:
                    # Second Ctrl+C - exit
                    click.echo("\nGoodbye!")
                    break
                continue
            
            # Process the command
            if input_str.strip():
                cli.process_command(input_str)
                
        except SystemExit:
            click.echo("\nGoodbye!")
            break
        except Exception as e:
            click.echo(f"Error: {str(e)}")

if __name__ == "__main__":
    main()
