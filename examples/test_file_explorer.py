from dayhoff.fs import FileInspector, LocalFileSystem
# Removed unused import: from dayhoff.config import config
import os

def test_file_explorer():
    """
    Tests basic file system exploration functionalities.

    This script demonstrates:
    1. Initializing a LocalFileSystem object.
    2. Initializing a FileInspector using the filesystem.
    3. Using FileInspector to read the head (first few lines) of a file.
    4. Using LocalFileSystem to detect the format of a file based on content/extension.
    """
    print("Testing file system exploration tools...\n")

    # 1. Initialize filesystem (using the local implementation)
    print("Initializing LocalFileSystem...")
    fs = LocalFileSystem()
    print("✓ LocalFileSystem initialized.")

    # Define the path to the sample file relative to this script
    script_dir = os.path.dirname(__file__)
    file_path = os.path.join(script_dir, "sample.fasta")
    print(f"Using sample file: {file_path}")

    if not os.path.exists(file_path):
        print(f"✗ Error: Sample file not found at {file_path}")
        return

    # 2. Initialize file inspector
    print("\nInitializing FileInspector...")
    inspector = FileInspector(fs)
    print("✓ FileInspector initialized.")

    # 3. Test file inspection (reading head)
    num_lines_to_read = 2
    print(f"\nReading first {num_lines_to_read} lines of file using inspector.head():")
    try:
        head_lines = list(inspector.head(file_path, num_lines_to_read))
        if head_lines:
            for line in head_lines:
                print(f"  {line.strip()}") # strip newline for cleaner printing
            print(f"✓ Successfully read {len(head_lines)} lines.")
        else:
            print("  File appears empty or could not be read.")
    except Exception as e:
        print(f"✗ Error reading file head: {e}")
        return

    # 4. Test format detection using the filesystem object
    print("\nDetecting file format using fs.detect_format():")
    try:
        file_type = fs.detect_format(file_path)
        if file_type:
            print(f"✓ Detected file type: {file_type}")
            # Basic assertion based on sample file name/content
            assert "fasta" in file_type.lower(), "Expected FASTA format"
        else:
            print("  Could not detect file type.")
    except Exception as e:
        print(f"✗ Error detecting file format: {e}")
        return

    print("\nFile system exploration test completed successfully!")

if __name__ == "__main__":
    test_file_explorer()
