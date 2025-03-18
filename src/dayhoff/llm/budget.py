from typing import Dict

class TokenBudget:
    """Manages token usage and budget"""
    
    def __init__(self, max_tokens: int = 100000):
        self.max_tokens = max_tokens
        self.used_tokens = 0
        
    def add_usage(self, tokens: int) -> None:
        """Add to the token usage count"""
        self.used_tokens += tokens
        
    def remaining(self) -> int:
        """Get remaining tokens in budget"""
        return max(0, self.max_tokens - self.used_tokens)
        
    def get_usage(self) -> Dict[str, int]:
        """Get current usage statistics"""
        return {
            'max_tokens': self.max_tokens,
            'used_tokens': self.used_tokens,
            'remaining_tokens': self.remaining()
        }
