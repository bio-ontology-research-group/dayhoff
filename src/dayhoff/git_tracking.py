import git
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Any, Optional

@dataclass
class Event:
    """Represents a tracked event in the system"""
    timestamp: datetime
    event_type: str
    metadata: Dict[str, Any]
    user: str

class GitTracker:
    """Git-based event tracking system for reproducibility"""
    
    def __init__(self, repo_path: str = "."):
        """Initialize the tracker with a git repository path"""
        # Create directory if it doesn't exist
        os.makedirs(repo_path, exist_ok=True)
        
        # Initialize or open git repository
        if not os.path.exists(os.path.join(repo_path, ".git")):
            self.repo = git.Repo.init(repo_path)
            # Create initial commit
            with open(os.path.join(repo_path, "README.md"), "w") as f:
                f.write("# Dayhoff Session\n\nThis repository tracks a Dayhoff session.\n")
            self.repo.index.add(["README.md"])
            self.repo.index.commit("Initial commit")
        else:
            self.repo = git.Repo(repo_path)
    
    def record_event(self, event_type: str, metadata: Dict[str, Any], files: Optional[Dict[str, str]] = None) -> str:
        """Record a new event in the git history
        
        Args:
            event_type: Type of event being recorded
            metadata: Dictionary of metadata about the event
            files: Optional dictionary of filename to content for files to include in this event
        """
        event = Event(
            timestamp=datetime.now(),
            event_type=event_type,
            metadata=metadata,
            user=self._get_current_user()
        )
        
        # Create a new branch for the event
        branch_name = f"event/{event.timestamp.strftime('%Y-%m-%dT%H-%M-%S')}"
        self.repo.git.checkout('HEAD', b=branch_name)
        
        # Store event in a structured format
        event_file = os.path.join(self.session_path, "dayhoff_events.log")
        with open(event_file, "a") as f:
            f.write(f"{event}\n")
            
        # Add any provided files to the repository
        if files:
            for filename, content in files.items():
                file_path = os.path.join(self.session_path, filename)
                with open(file_path, "w") as f:
                    f.write(content)
                self.repo.index.add([filename])
            
        self.repo.index.add(["dayhoff_events.log"])
        self.repo.index.commit(f"Dayhoff event: {event_type}")
        
        # Return to default branch
        default_branch = self.repo.active_branch.name
        self.repo.git.checkout(default_branch)
        return branch_name
    
    def _get_current_user(self) -> str:
        """Get the current user from git config"""
        try:
            return self.repo.config_reader().get_value("user", "name", "unknown")
        except:
            return "unknown"

    def get_event_history(self) -> list[Event]:
        """Retrieve the history of tracked events"""
        # TODO: Implement event history retrieval
        return []
