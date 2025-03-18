from dayhoff.hpc_bridge import SSHManager
from dayhoff.fs import FileFormatDetector
import os

# Common bioinformatics file extensions
BIOINFO_EXTENSIONS = {
    '.fasta': 'FASTA sequence',
    '.fa': 'FASTA sequence',
    '.fastq': 'FASTQ sequence',
    '.fq': 'FASTQ sequence',
    '.vcf': 'Variant Call Format',
    '.bam': 'Binary Alignment Map',
    '.sam': 'Sequence Alignment Map',
    '.gff': 'General Feature Format',
    '.gtf': 'Gene Transfer Format',
    '.bed': 'Browser Extensible Data'
}

def explore_remote_fs():
    print("Testing remote file system exploration...\n")
    
    # Initialize SSH connection
    ssh = SSHManager()
    if not ssh.connect():
        print("✗ SSH connection failed")
        return False
    
    print("✓ SSH connection established")
    
    # Run ls command
    print("\nListing remote directory:")
    ls_output = ssh.execute_command("ls -l")
    print(ls_output)
    
    # Identify bioinformatics files
    print("\nIdentifying bioinformatics files:")
    files = ssh.execute_command("ls").splitlines()
    detector = FileFormatDetector(ssh)
    
    for file in files:
        _, ext = os.path.splitext(file)
        if ext.lower() in BIOINFO_EXTENSIONS:
            print(f"{file}: {BIOINFO_EXTENSIONS[ext.lower()]}")
        else:
            # Try to detect format based on content
            file_type = detector.detect(file)
            if file_type:
                print(f"{file}: Detected as {file_type}")
            else:
                print(f"{file}: Unknown format")
    
    ssh.disconnect()
    print("\nRemote file system exploration completed successfully!")
    return True

if __name__ == "__main__":
    explore_remote_fs()
