from typing import Dict, List

class ContainerManager:
    """Manages container specifications and builds"""
    
    def __init__(self):
        self.containers: Dict[str, str] = {}
        
    def add_container(self, name: str, definition: str) -> None:
        """Add a container definition
        
        Args:
            name: Name of the container
            definition: Singularity definition file content
        """
        self.containers[name] = definition
        
    def build_container(self, name: str) -> bool:
        """Build a container from its definition
        
        Args:
            name: Name of the container to build
            
        Returns:
            bool: True if build was successful
        """
        # TODO: Implement container building
        return True
        
    def get_container(self, name: str) -> str:
        """Get a container's definition
        
        Args:
            name: Name of the container
            
        Returns:
            str: The container's definition file content
        """
        return self.containers.get(name, "")
