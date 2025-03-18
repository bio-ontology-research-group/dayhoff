from dayhoff.git_tracking import GitTracker
from pathlib import Path
import shutil

def main():
    # Create a temporary test directory
    test_path = Path("/tmp/dayhoff_test_git_tracking")
    if test_path.exists():
        shutil.rmtree(test_path)
    
    print("Initializing Git tracking system...")
    tracker = GitTracker(str(test_path))
    
    print("\nRecording first event with configuration...")
    branch1 = tracker.record_event(
        event_type="test_started",
        metadata={"test": "git_tracking", "version": "1.0"},
        files={
            "test_config.yaml": "test: git_tracking\nversion: 1.0",
            "test_script.py": "print('Hello from test script')"
        }
    )
    
    print("\nRecording second event with results...")
    branch2 = tracker.record_event(
        event_type="test_completed",
        metadata={"status": "success", "assertions_passed": 5},
        files={
            "results.log": "Test results:\n- Assertion 1: PASS\n- Assertion 2: PASS",
            "summary.json": '{"total_tests": 5, "passed": 5, "failed": 0}'
        }
    )
    
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
