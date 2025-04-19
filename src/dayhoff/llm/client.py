from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
import logging # Added logging
from ..config import config

logger = logging.getLogger(__name__)

class LLMClient(ABC):
    """Abstract base class for LLM clients"""

    def __init__(self, api_key: Optional[str] = None):
        """Initialize with API key from config if not provided"""
        # Prioritize explicitly passed API key, then config, then None
        self.api_key = api_key if api_key is not None else config.get('LLM', 'api_key')
        # Load other common settings from config with defaults
        self.rate_limit = int(config.get('LLM', 'rate_limit', '60')) # Example: requests per minute
        self.max_tokens_default = int(config.get('LLM', 'max_tokens', '4096')) # Default max tokens for generation
        logger.debug(f"LLMClient initialized. API Key set: {bool(self.api_key)}, Rate Limit: {self.rate_limit}, Default Max Tokens: {self.max_tokens_default}")

    @abstractmethod
    def generate(self, prompt: str, context: Optional[Dict[str, Any]] = None, **kwargs) -> Dict[str, Any]:
        """Generate a response to the given prompt

        Args:
            prompt: The input prompt
            context: Optional context for multi-turn interactions
            **kwargs: Additional provider-specific parameters (e.g., max_tokens, temperature, model)

        Returns:
            Dictionary containing response and metadata (e.g., tokens used)
        """
        pass

    @abstractmethod
    def get_usage(self) -> Dict[str, int]:
        """Get current token usage statistics (if tracked by the client)

        Returns:
            Dictionary with token usage details
        """
        pass

class OpenAIClient(LLMClient):
    """Concrete implementation for OpenAI API (and compatible APIs like OpenRouter)"""

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None, default_model: Optional[str] = None):
        """Initialize OpenAI client.

        Args:
            api_key: API key. If None, uses config.
            base_url: API base URL. If None, uses config or provider default.
            default_model: Default model to use for generation if not specified. If None, uses config.
        """
        super().__init__(api_key=api_key)
        # Prioritize passed args, then config, then defaults/None
        self.base_url = base_url if base_url is not None else config.get('LLM', 'base_url')
        self.default_model = default_model if default_model is not None else config.get('LLM', 'model')

        # Use provider default URL if base_url is still empty
        provider = config.get('LLM', 'provider') # Get provider to find default URL
        if not self.base_url and provider in config.DEFAULT_LLM_BASE_URLS:
             self.base_url = config.DEFAULT_LLM_BASE_URLS[provider]

        logger.debug(f"OpenAIClient initialized. Base URL: {self.base_url}, Default Model: {self.default_model}")
        # TODO: Initialize actual OpenAI library client here using self.api_key, self.base_url

    def generate(self, prompt: str, context: Optional[Dict[str, Any]] = None, **kwargs) -> Dict[str, Any]:
        """Generate using OpenAI API."""
        # Extract common parameters or use defaults
        model = kwargs.get('model', self.default_model)
        max_tokens = kwargs.get('max_tokens', self.max_tokens_default)
        temperature = kwargs.get('temperature', 0.7)

        if not self.api_key:
            raise ValueError("OpenAI API key is not set.")
        if not model:
            raise ValueError("OpenAI model is not set.")

        logger.info(f"Generating response using OpenAI/compatible API. Model: {model}, Max Tokens: {max_tokens}, Temp: {temperature}")
        # TODO: Replace with actual OpenAI API call
        # Example structure:
        # try:
        #     from openai import OpenAI
        #     client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        #     response = client.chat.completions.create(
        #         model=model,
        #         messages=[{"role": "user", "content": prompt}], # Add context handling later
        #         max_tokens=max_tokens,
        #         temperature=temperature,
        #         # Pass other kwargs if needed
        #     )
        #     content = response.choices[0].message.content
        #     tokens_used = response.usage.total_tokens if response.usage else 0
        #     return {'response': content, 'tokens_used': tokens_used, 'model_used': response.model}
        # except ImportError:
        #     logger.error("OpenAI library not installed. Please install it: pip install openai")
        #     raise
        # except Exception as e:
        #     logger.error(f"OpenAI API call failed: {e}", exc_info=True)
        #     raise # Re-raise the exception

        # Mock response for now
        mock_response = f"Mock OpenAI response for model '{model}' to prompt: '{prompt[:50]}...'"
        mock_tokens = len(prompt.split()) + 15 # Rough estimate
        logger.warning("Using mock OpenAI response.")
        return {
            'response': mock_response,
            'tokens_used': mock_tokens,
            'model_used': model
        }

    def get_usage(self) -> Dict[str, int]:
        # TODO: Implement actual usage tracking if needed/possible
        logger.warning("OpenAI usage tracking not implemented, returning mock data.")
        return {
            'total_tokens': 100,
            'prompt_tokens': 50,
            'completion_tokens': 50
        }

class AnthropicClient(LLMClient):
    """Concrete implementation for Anthropic API"""

    def __init__(self, api_key: Optional[str] = None, default_model: Optional[str] = None, base_url: Optional[str] = None):
        """Initialize Anthropic client.

        Args:
            api_key: API key. If None, uses config.
            default_model: Default model to use for generation if not specified. If None, uses config.
            base_url: API base URL (optional for Anthropic, usually default works).
        """
        super().__init__(api_key=api_key)
        self.default_model = default_model if default_model is not None else config.get('LLM', 'model')
        # Anthropic base URL is less commonly changed, but allow override
        self.base_url = base_url if base_url is not None else config.get('LLM', 'base_url')
        if not self.base_url:
             self.base_url = config.DEFAULT_LLM_BASE_URLS.get('anthropic') # Get default if needed

        logger.debug(f"AnthropicClient initialized. Default Model: {self.default_model}, Base URL: {self.base_url}")
        # TODO: Initialize actual Anthropic library client here

    def generate(self, prompt: str, context: Optional[Dict[str, Any]] = None, **kwargs) -> Dict[str, Any]:
        """Generate using Anthropic API."""
        model = kwargs.get('model', self.default_model)
        max_tokens = kwargs.get('max_tokens', self.max_tokens_default)
        temperature = kwargs.get('temperature', 0.7)

        if not self.api_key:
            raise ValueError("Anthropic API key is not set.")
        if not model:
            raise ValueError("Anthropic model is not set.")

        logger.info(f"Generating response using Anthropic API. Model: {model}, Max Tokens: {max_tokens}, Temp: {temperature}")
        # TODO: Replace with actual Anthropic API call
        # Example structure:
        # try:
        #     import anthropic
        #     client = anthropic.Anthropic(api_key=self.api_key, base_url=self.base_url) # Adjust base_url if needed
        #     response = client.messages.create(
        #         model=model,
        #         messages=[{"role": "user", "content": prompt}], # Add context handling
        #         max_tokens=max_tokens,
        #         temperature=temperature,
        #         # Pass other kwargs if needed
        #     )
        #     content = response.content[0].text if response.content else ""
        #     # Anthropic usage might be structured differently
        #     tokens_used = response.usage.input_tokens + response.usage.output_tokens if response.usage else 0
        #     return {'response': content, 'tokens_used': tokens_used, 'model_used': model} # Anthropic response might not include model name
        # except ImportError:
        #     logger.error("Anthropic library not installed. Please install it: pip install anthropic")
        #     raise
        # except Exception as e:
        #     logger.error(f"Anthropic API call failed: {e}", exc_info=True)
        #     raise

        # Mock response for now
        mock_response = f"Mock Anthropic response for model '{model}' to prompt: '{prompt[:50]}...'"
        mock_tokens = len(prompt.split()) + 18 # Rough estimate
        logger.warning("Using mock Anthropic response.")
        return {
            'response': mock_response,
            'tokens_used': mock_tokens,
            'model_used': model
        }

    def get_usage(self) -> Dict[str, int]:
        # TODO: Implement actual usage tracking if needed/possible
        logger.warning("Anthropic usage tracking not implemented, returning mock data.")
        return {
            'total_tokens': 100,
            'prompt_tokens': 50,
            'completion_tokens': 50
        }

# --- Factory Function (Optional) ---
# Could be useful if initialization logic becomes complex

# def get_llm_client(provider: str, api_key: str, model: str, base_url: Optional[str] = None) -> LLMClient:
#     """Factory function to create LLM client instances."""
#     if provider == 'openai' or provider == 'openrouter':
#         return OpenAIClient(api_key=api_key, base_url=base_url, default_model=model)
#     elif provider == 'anthropic':
#         return AnthropicClient(api_key=api_key, default_model=model, base_url=base_url)
#     else:
#         raise ValueError(f"Unsupported LLM provider: {provider}")
