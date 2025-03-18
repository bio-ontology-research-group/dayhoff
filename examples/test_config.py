from dayhoff.config import config

def print_config():
    print("Current Dayhoff Configuration:")
    print("=" * 40)
    
    for section in config.config.sections():
        print(f"\n[{section}]")
        for key, value in config.config.items(section):
            print(f"{key} = {value}")
    
    print("\nDefault Configuration:")
    print("=" * 40)
    for key, value in config.config.items('DEFAULT'):
        print(f"{key} = {value}")

if __name__ == "__main__":
    print_config()
