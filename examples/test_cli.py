from dayhoff.cli.main import cli
from click.testing import CliRunner

def test_cli():
    """Test the CLI interface"""
    runner = CliRunner()
    
    # Test basic command execution
    result = runner.invoke(cli, ['execute', 'test_command', '--param', 'key=value'])
    assert result.exit_code == 0
    assert "Executed test_command" in result.output
    
    # TODO: Add git event verification
    print("CLI test completed successfully!")

if __name__ == "__main__":
    test_cli()
