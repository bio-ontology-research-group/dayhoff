from dayhoff.git_tracking import GitTracker
from pathlib import Path
import shutil

def generate_test_events(tracker, k: int):
    """Generate k test events with incrementing metadata"""
    for i in range(1, k + 1):
        print(f"\nRecording test event {i}/{k}...")
        tracker.record_event(
            event_type=f"test_step_{i}",
            metadata={
                "test": "git_tracking",
                "step": i,
                "status": "running" if i < k else "completed"
            },
            files={
                f"test_step_{i}.yaml": f"step: {i}\nstatus: running",
                f"test_log_{i}.txt": f"Test step {i} of {k} completed"
            }
        )

def main():
    # Create a temporary test directory
    test_path = Path("/tmp/dayhoff_test_git_tracking")
    if test_path.exists():
        shutil.rmtree(test_path)
    
    print("Initializing Git tracking system...")
    tracker = GitTracker(str(test_path))
    
    # Generate k events (default to 5 if not specified)
    k = 5
    generate_test_events(tracker, k)
    
    print("\nTest session details:")
    print(f"Location: {test_path}")
    print("Branches created:")
    for branch in tracker.repo.branches:
        print(f" - {branch.name}")
    
    print("\nEvent history:")
    for event in tracker.get_event_history():
        print(f"{event.timestamp} - {event.event_type}")

    print("\nGit tracking system test complete!")

if __name__ == "__main__":
    main()
