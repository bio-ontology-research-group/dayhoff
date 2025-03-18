from dayhoff.git_tracking import GitTracker
from pathlib import Path
import shutil

def generate_events(tracker, k: int):
    """Generate k events with different metadata and files"""
    for i in range(1, k + 1):
        print(f"\nRecording event {i}/{k}...")
        tracker.record_event(
            event_type=f"analysis_step_{i}",
            metadata={
                "step": i,
                "status": "running" if i < k else "completed",
                "progress": f"{i}/{k}"
            },
            files={
                f"step_{i}_config.yaml": f"step: {i}\nstatus: running",
                f"step_{i}_log.txt": f"Processing step {i} of {k}"
            }
        )

def main():
    # Create a temporary session directory
    session_path = Path("/tmp/dayhoff_test_session")
    if session_path.exists():
        shutil.rmtree(session_path)
    
    print("Initializing new session...")
    tracker = GitTracker(str(session_path))
    
    # Generate k events (default to 5 if not specified)
    k = 5
    generate_events(tracker, k)
    
    print("\nSession details:")
    print(f"Location: {session_path}")
    print("Branches:")
    for branch in tracker.repo.branches:
        print(f" - {branch.name}")
    
    print("\nEvent history:")
    for event in tracker.get_event_history():
        print(f"{event.timestamp} - {event.event_type}")

if __name__ == "__main__":
    main()
