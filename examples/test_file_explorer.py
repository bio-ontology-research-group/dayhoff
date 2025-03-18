from dayhoff.fs import FileInspector, FileFormatDetector

def test_file_explorer():
    print("Testing file system exploration tools...\n")
    
    # Test file inspection
    file_path = "sample.fasta"
    inspector = FileInspector(file_path)
    
    print("First 2 lines of file:")
    for line in inspector.head(2):
        print(line.strip())
    
    # Test format detection
    detector = FileFormatDetector()
    file_type = detector.detect(file_path)
    print(f"\nDetected file type: {file_type}")
    
    print("\nFile system exploration test completed successfully!")

if __name__ == "__main__":
    test_file_explorer()
