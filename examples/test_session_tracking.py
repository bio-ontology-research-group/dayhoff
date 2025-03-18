from dayhoff.git_tracking import GitTracker
from pathlib import Path
import shutil

def main():
    # Create a temporary session directory
    session_path = Path("/tmp/dayhoff_test_session")
    if session_path.exists():
        shutil.rmtree(session_path)
    
    print("Initializing new session...")
    tracker = GitTracker(str(session_path))
    
    print("\nRecording first event with generated files...")
    tracker.record_event(
        event_type="analysis_started",
        metadata={"analysis": "variant_calling", "sample": "NA12878"},
        files={
            "config.yaml": "sample: NA12878\nanalysis: variant_calling",
            "pipeline.cwl": "cwlVersion: v1.0\nclass: Workflow"
        }
    )
    
    print("\nRecording second event with results...")
    tracker.record_event(
        event_type="analysis_completed",
        metadata={"status": "success", "variants_found": 1234},
        files={
            "results.vcf": "##fileformat=VCFv4.2\n#CHROM\tPOS\tID\tREF\tALT",
            "metrics.json": '{"precision": 0.99, "recall": 0.98}'
        }
    )
    
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
