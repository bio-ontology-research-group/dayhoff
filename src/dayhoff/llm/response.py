import json
from typing import Dict, Any

class ResponseParser:
    """Parses and validates LLM responses"""
    
    def parse_response(self, response: str) -> Dict[str, Any]:
        """Parse a JSON response from the LLM"""
        try:
            data = json.loads(response)
            return {
                'command': data.get('command'),
                'reasoning': data.get('reasoning'),
                'context_updates': data.get('context_updates', {})
            }
        except json.JSONDecodeError:
            return {
                'error': 'Invalid JSON response',
                'raw_response': response
            }
