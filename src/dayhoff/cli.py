import click

@click.group()
def main():
    """Dayhoff CLI interface for bioinformatics tasks"""
    pass

@main.command()
@click.argument('path')
def explore(path):
    """Explore bioinformatics data in the filesystem"""
    # TODO: Implement filesystem exploration
    pass

@main.command()
@click.option('--workflow-type', type=click.Choice(['cwl', 'nextflow']))
def generate_workflow(workflow_type):
    """Generate bioinformatics workflows"""
    # TODO: Implement workflow generation
    pass

# TODO: Add more CLI commands
