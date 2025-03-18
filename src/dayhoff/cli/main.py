import click
from ..service import DayhoffService

service = DayhoffService()

@click.group()
def cli():
    """Dayhoff CLI interface"""
    pass

@cli.command()
@click.argument('command')
@click.option('--param', multiple=True)
def execute(command: str, param: tuple):
    """Execute a command through the CLI"""
    params = dict(p.split('=') for p in param)
    result = service.execute_command(command, params)
    click.echo(result)
