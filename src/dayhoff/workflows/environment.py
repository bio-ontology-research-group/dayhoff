import platform
import subprocess
from typing import Dict, List

class EnvironmentTracker:
    """Tracks and records execution environment details"""
    
    def __init__(self):
        self.details = self._get_environment_details()
        
    def _get_environment_details(self) -> Dict[str, str]:
        """Get details about the current environment"""
        return {
            'os': platform.system(),
            'python_version': platform.python_version(),
            'cpu': platform.processor(),
            'memory': self._get_memory(),
            'packages': self._get_installed_packages()
        }
        
    def _get_memory(self) -> str:
        """Get system memory information"""
        try:
            result = subprocess.run(['free', '-h'], capture_output=True, text=True)
            return result.stdout
        except:
            return "Unknown"
            
    def _get_installed_packages(self) -> List[str]:
        """Get list of installed Python packages"""
        try:
            result = subprocess.run(['pip', 'list'], capture_output=True, text=True)
            return result.stdout.splitlines()
        except:
            return []
            
    def get_environment_report(self) -> str:
        """Generate a report of the current environment"""
        report = "Environment Details:\n"
        for key, value in self.details.items():
            report += f"{key}:\n{value}\n"
        return report
