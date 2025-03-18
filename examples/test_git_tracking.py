from dayhoff.git_tracking import GitTracker

def main():
    print("Initializing Git tracking system...")
    tracker = GitTracker()
    
    print("Recording test event...")
    branch_name = tracker.record_event(
        event_type="test_event",
        metadata={"description": "This is a test event"}
    )
    
    print(f"Event recorded in branch: {branch_name}")
    print("Git tracking system test complete!")

if __name__ == "__main__":
    main()
