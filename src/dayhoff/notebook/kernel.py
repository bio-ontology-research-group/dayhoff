from ipykernel.kernelbase import Kernel
from ..service import DayhoffService

class DayhoffKernel(Kernel):
    """Jupyter kernel implementation for Dayhoff"""
    
    implementation = 'Dayhoff'
    implementation_version = '0.1'
    language = 'python'
    language_version = '3.10'
    language_info = {
        'name': 'dayhoff',
        'mimetype': 'text/plain',
        'file_extension': '.dh',
    }
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.service = DayhoffService()
        
    def do_execute(self, code, silent, store_history=True, user_expressions=None, allow_stdin=False):
        """Execute code in the kernel"""
        if not silent:
            # Parse and execute the command
            result = self.service.execute_command("notebook_command", {"code": code})
            
            # Send the result back to the frontend
            stream_content = {
                'name': 'stdout',
                'text': str(result)
            }
            self.send_response(self.iopub_socket, 'stream', stream_content)
            
        return {
            'status': 'ok',
            'execution_count': self.execution_count,
            'payload': [],
            'user_expressions': {}
        }
