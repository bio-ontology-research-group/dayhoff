from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from ..config import config

class LLMClient(ABC):
    """Abstract base class for LLM clients"""
    
    def __init__(self, api_key: Optional[str] = None):
        """Initialize with API key from config if not provided"""
        self.api_key = api_key or config.get('LLM', 'api_key')
        self.rate_limit = int(config.get('LLM', 'rate_limit', '60'))
        self.max_tokens = int(config.get('LLM', 'max_tokens', '4096'))
        
    @abstractmethod
    def generate(self, prompt: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Generate a response to the given prompt
        
        Args:
            prompt: The input prompt
            context: Optional context for multi-turn interactions
            
        Returns:
            Dictionary containing response and metadata
        """
        pass
    
    @abstractmethod
    def get_usage(self) -> Dict[str, int]:
        """Get current token usage statistics
        
        Returns:
            Dictionary with token usage details
        """
        pass

class OpenAIClient(LLMClient):
    """Concrete implementation for OpenAI API"""
    
    def generate(self, prompt: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        # TODO: Implement OpenAI API integration
        return {
            'response': "Mock OpenAI response",
            'tokens_used': 10
        }
    
    def get_usage(self) -> Dict[str, int]:
        return {
            'total_tokens': 100,
            'prompt_tokens': 50,
            'completion_tokens': 50
        }

class AnthropicClient(LLMClient):
    """Concrete implementation for Anthropic API"""
    
    def generate(self, prompt: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        # TODO: Implement Anthropic API integration
        return {
            'response': "Mock Anthropic response",
            'tokens_used': 10
        }
    
    def get_usage(self) -> Dict[str, int]:
        return {
            'total_tokens': 100,
            'prompt_tokens': 50,
            'completion_tokens': 50
        }
