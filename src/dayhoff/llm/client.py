from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
import logging # Added logging
from ..config import config

# Attempt to import LLM libraries
try:
    import openai
    OPENAI_AVAILABLE = True
except ImportError:
    openai = None # type: ignore
    OPENAI_AVAILABLE = False

try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    anthropic = None # type: ignore
    ANTHROPIC_AVAILABLE = False


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
        self.total_tokens_used = 0 # Simple counter for usage
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

    def get_usage(self) -> Dict[str, int]:
        """Get current token usage statistics (if tracked by the client)

        Returns:
            Dictionary with token usage details
        """
        # Basic implementation using the counter
        return {
            'total_tokens': self.total_tokens_used,
            # Prompt/completion breakdown requires more detailed tracking per call
            'prompt_tokens': -1, # Indicate not tracked precisely here
            'completion_tokens': -1 # Indicate not tracked precisely here
        }

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
        if not OPENAI_AVAILABLE:
            raise ImportError("OpenAI library not installed. Please install it: pip install openai")

        # Prioritize passed args, then config, then defaults/None
        self.base_url = base_url if base_url is not None else config.get('LLM', 'base_url')
        self.default_model = default_model if default_model is not None else config.get('LLM', 'model')

        # Use provider default URL if base_url is still empty
        provider = config.get('LLM', 'provider') # Get provider to find default URL
        if not self.base_url and provider in config.DEFAULT_LLM_BASE_URLS:
             self.base_url = config.DEFAULT_LLM_BASE_URLS[provider]

        logger.debug(f"OpenAIClient initialized. Base URL: {self.base_url}, Default Model: {self.default_model}")

        # Initialize actual OpenAI library client here
        try:
            self.client = openai.OpenAI(api_key=self.api_key, base_url=self.base_url)
        except Exception as e:
            logger.error(f"Failed to initialize OpenAI client: {e}", exc_info=True)
            raise RuntimeError(f"Failed to initialize OpenAI client: {e}") from e

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

        # Actual OpenAI API call
        try:
            # Basic message structure, context handling can be added later
            messages = [{"role": "user", "content": prompt}]
            # TODO: Implement context merging if needed

            response = self.client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                # Pass other kwargs if needed (e.g., top_p, frequency_penalty)
                # Be careful about which kwargs are valid for the API
            )

            content = response.choices[0].message.content if response.choices else ""
            tokens_used = response.usage.total_tokens if response.usage else 0
            model_used = response.model # Get model name actually used from response

            # Update usage counter
            self.total_tokens_used += tokens_used

            logger.debug(f"OpenAI API call successful. Tokens used: {tokens_used}, Model: {model_used}")
            return {'response': content, 'tokens_used': tokens_used, 'model_used': model_used}

        except openai.APIConnectionError as e:
            logger.error(f"OpenAI API connection error: {e}", exc_info=True)
            raise ConnectionError(f"Failed to connect to OpenAI API: {e}") from e
        except openai.RateLimitError as e:
            logger.error(f"OpenAI API rate limit exceeded: {e}", exc_info=True)
            raise ConnectionError(f"OpenAI API rate limit exceeded: {e}") from e # Treat as connection error for retry?
        except openai.APIStatusError as e:
            logger.error(f"OpenAI API status error: {e.status_code} - {e.response}", exc_info=True)
            raise RuntimeError(f"OpenAI API returned an error: {e.status_code} - {e.message}") from e
        except Exception as e:
            logger.error(f"OpenAI API call failed unexpectedly: {e}", exc_info=True)
            raise RuntimeError(f"OpenAI API call failed: {e}") from e


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
        if not ANTHROPIC_AVAILABLE:
            raise ImportError("Anthropic library not installed. Please install it: pip install anthropic")

        self.default_model = default_model if default_model is not None else config.get('LLM', 'model')
        # Anthropic base URL is less commonly changed, but allow override
        self.base_url = base_url if base_url is not None else config.get('LLM', 'base_url')
        if not self.base_url:
             self.base_url = config.DEFAULT_LLM_BASE_URLS.get('anthropic') # Get default if needed

        logger.debug(f"AnthropicClient initialized. Default Model: {self.default_model}, Base URL: {self.base_url}")

        # Initialize actual Anthropic library client here
        try:
            # Pass base_url only if it's explicitly set, otherwise use default
            client_args = {"api_key": self.api_key}
            if self.base_url:
                client_args["base_url"] = self.base_url
            self.client = anthropic.Anthropic(**client_args) # type: ignore
        except Exception as e:
            logger.error(f"Failed to initialize Anthropic client: {e}", exc_info=True)
            raise RuntimeError(f"Failed to initialize Anthropic client: {e}") from e

    def generate(self, prompt: str, context: Optional[Dict[str, Any]] = None, **kwargs) -> Dict[str, Any]:
        """Generate using Anthropic API."""
        model = kwargs.get('model', self.default_model)
        # Anthropic uses 'max_tokens_to_sample' or 'max_tokens' depending on API version/method
        # Using 'max_tokens' for the newer Messages API
        max_tokens = kwargs.get('max_tokens', self.max_tokens_default)
        temperature = kwargs.get('temperature', 0.7)

        if not self.api_key:
            raise ValueError("Anthropic API key is not set.")
        if not model:
            raise ValueError("Anthropic model is not set.")

        logger.info(f"Generating response using Anthropic API. Model: {model}, Max Tokens: {max_tokens}, Temp: {temperature}")

        # Actual Anthropic API call (using Messages API)
        try:
            # Basic message structure
            messages = [{"role": "user", "content": prompt}]
            # TODO: Implement context merging if needed (Anthropic expects alternating user/assistant roles)

            response = self.client.messages.create(
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                # Pass other kwargs if needed (e.g., top_p, top_k)
            )

            content = response.content[0].text if response.content and isinstance(response.content, list) and response.content[0].type == 'text' else ""
            # Anthropic usage might be structured differently
            tokens_used = response.usage.input_tokens + response.usage.output_tokens if response.usage else 0
            model_used = model # Anthropic response doesn't typically include model name, use requested model

            # Update usage counter
            self.total_tokens_used += tokens_used

            logger.debug(f"Anthropic API call successful. Tokens used: {tokens_used}, Model: {model_used}")
            return {'response': content, 'tokens_used': tokens_used, 'model_used': model_used}

        except anthropic.APIConnectionError as e:
            logger.error(f"Anthropic API connection error: {e}", exc_info=True)
            raise ConnectionError(f"Failed to connect to Anthropic API: {e}") from e
        except anthropic.RateLimitError as e:
            logger.error(f"Anthropic API rate limit exceeded: {e}", exc_info=True)
            raise ConnectionError(f"Anthropic API rate limit exceeded: {e}") from e
        except anthropic.APIStatusError as e:
            logger.error(f"Anthropic API status error: {e.status_code} - {e.response}", exc_info=True)
            raise RuntimeError(f"Anthropic API returned an error: {e.status_code} - {e.message}") from e
        except Exception as e:
            logger.error(f"Anthropic API call failed unexpectedly: {e}", exc_info=True)
            raise RuntimeError(f"Anthropic API call failed: {e}") from e

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
