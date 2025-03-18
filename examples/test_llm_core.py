from dayhoff.llm import OpenAIClient, PromptManager, ResponseParser, ContextManager
from typing import Dict, Any, Optional

class MockOpenAIClient:
    """Mock OpenAI client for testing"""
    
    def generate(self, prompt: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        # Mock responses for specific prompts
        if "generate an appropriate command" in prompt:
            return {
                'response': '{"command": "explore /data", "reasoning": "User wants to explore data"}',
                'tokens_used': 10
            }
        elif "Previous context" in prompt:
            return {
                'response': '{"command": "explore /data/results", "reasoning": "Following up on previous exploration", "context_updates": {"last_location": "/data/results"}}',
                'tokens_used': 15
            }
        return {
            'response': '{"error": "Unknown prompt"}',
            'tokens_used': 5
        }
    
    def get_usage(self) -> Dict[str, int]:
        return {
            'total_tokens': 25,
            'prompt_tokens': 15,
            'completion_tokens': 10
        }

def test_llm_core():
    print("Testing LLM core functionality...\n")
    
    # Initialize components
    client = MockOpenAIClient()
    prompt_manager = PromptManager()
    response_parser = ResponseParser()
    context_manager = ContextManager()
    
    # First interaction
    print("First prompt:")
    prompt = prompt_manager.generate_prompt('command', {'input': 'I want to explore my data'})
    print(f"Generated prompt: {prompt}")
    
    response = client.generate(prompt)
    print(f"Raw response: {response['response']}")
    
    parsed = response_parser.parse_response(response['response'])
    print(f"Parsed response: {parsed}")
    
    # Update context
    if 'context_updates' in parsed:
        context_manager.update(parsed['context_updates'])
    
    # Follow-up interaction
    print("\nFollow-up prompt:")
    followup_prompt = prompt_manager.generate_prompt('followup', {
        'context': context_manager.get(),
        'input': 'Now show me the results'
    })
    print(f"Generated followup prompt: {followup_prompt}")
    
    followup_response = client.generate(followup_prompt)
    print(f"Raw followup response: {followup_response['response']}")
    
    parsed_followup = response_parser.parse_response(followup_response['response'])
    print(f"Parsed followup response: {parsed_followup}")
    
    # Show usage
    print("\nToken usage:")
    print(client.get_usage())
    
    print("\nLLM core test completed successfully!")

if __name__ == "__main__":
    test_llm_core()
