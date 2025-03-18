from dayhoff.fs import FileInspector, LocalFileSystem
from dayhoff.config import config

def test_file_explorer():
    print("Testing file system exploration tools...\n")
    
    # Initialize filesystem
    fs = LocalFileSystem()
    
    # Test file inspection
    file_path = "sample.fasta"
    inspector = FileInspector(fs)
    
    print("First 2 lines of file:")
    for line in inspector.head(file_path, 2):
        print(line.strip())
    
    # Test format detection
    file_type = fs.detect_format(file_path)
    print(f"\nDetected file type: {file_type}")
    
    print("\nFile system exploration test completed successfully!")

if __name__ == "__main__":
    test_file_explorer()
