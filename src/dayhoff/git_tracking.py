import git
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Any

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
        self.repo = git.Repo(repo_path)
        if self.repo.bare:
            raise ValueError("Repository is bare - cannot track events")
    
    def record_event(self, event_type: str, metadata: Dict[str, Any]) -> str:
        """Record a new event in the git history"""
        event = Event(
            timestamp=datetime.now(),
            event_type=event_type,
            metadata=metadata,
            user=self._get_current_user()
        )
        
        # Create a new branch for the event
        # Create branch name without invalid characters
        branch_name = f"event/{event.timestamp.strftime('%Y-%m-%dT%H-%M-%S')}"
        self.repo.git.checkout('HEAD', b=branch_name)
        
        # TODO: Store event in a structured format
        with open("dayhoff_events.log", "a") as f:
            f.write(f"{event}\n")
            
        self.repo.index.add(["dayhoff_events.log"])
        self.repo.index.commit(f"Dayhoff event: {event_type}")
        
        # Return to main branch
        self.repo.git.checkout('main')
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
