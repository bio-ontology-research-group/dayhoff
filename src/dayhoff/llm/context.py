from typing import Dict, Any

class ContextManager:
    """Manages context for multi-turn interactions"""
    
    def __init__(self):
        self.context = {}
        
    def update(self, updates: Dict[str, Any]) -> None:
        """Update the context with new information"""
        self.context.update(updates)
        
    def get(self) -> Dict[str, Any]:
        """Get the current context"""
        return self.context.copy()
