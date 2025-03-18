"""LLM integration layer for Dayhoff system.

This package provides functionality for:
- Abstract LLM client interface
- Prompt management and templating
- Response parsing and handling
- Context management for multi-turn interactions
- Token usage tracking and budget management
"""
from .client import LLMClient, OpenAIClient, AnthropicClient
from .prompt import PromptManager
from .response import ResponseParser
from .context import ContextManager
from .budget import TokenBudget

__all__ = [
    'LLMClient', 'OpenAIClient', 'AnthropicClient',
    'PromptManager', 'ResponseParser',
    'ContextManager', 'TokenBudget'
]
