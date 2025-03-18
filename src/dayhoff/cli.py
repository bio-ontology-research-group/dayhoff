import click
import readline
from typing import List, Optional

class DayhoffCLI:
    """Interactive CLI interface for Dayhoff"""
    
    def __init__(self):
        self.commands = {
            '/help': self.show_help,
            '/explore': self.explore,
            '/workflow': self.generate_workflow,
            '/exit': self.exit_cli
        }
        self.setup_autocomplete()
        
    def setup_autocomplete(self):
        """Set up command autocompletion"""
        def completer(text: str, state: int) -> Optional[str]:
            options = [cmd for cmd in self.commands if cmd.startswith(text)]
            if state < len(options):
                return options[state]
            return None
            
        readline.parse_and_bind("tab: complete")
        readline.set_completer(completer)
        
    def show_help(self, args: List[str]) -> None:
        """Show help information"""
        click.echo("Available commands:")
        for cmd in self.commands:
            click.echo(f"  {cmd}")
            
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

@click.command()
def main():
    """Interactive Dayhoff CLI interface"""
    cli = DayhoffCLI()
    click.echo("Welcome to Dayhoff CLI! Type /help for available commands.")
    
    while True:
        try:
            input_str = click.prompt("dayhoff>", prompt_suffix=" ")
            cli.process_command(input_str)
        except (KeyboardInterrupt, SystemExit):
            click.echo("\nGoodbye!")
            break
        except Exception as e:
            click.echo(f"Error: {str(e)}")
