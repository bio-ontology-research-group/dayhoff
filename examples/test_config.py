from dayhoff.config import DayhoffConfig # Import the class

def print_config():
    """
    Loads and prints the current Dayhoff configuration.

    This script demonstrates how to access the Dayhoff configuration
    programmatically using the DayhoffConfig class. It iterates through
    all sections and key-value pairs, printing them to the console.
    It also specifically prints the [DEFAULT] section items.
    """
    print("Initializing Dayhoff configuration...")
    # Instantiate the config manager
    config_manager = DayhoffConfig()

    print("\nCurrent Dayhoff Configuration:")
    print("=" * 40)

    # Access the underlying configparser object from the instance
    config_data = config_manager.config

    # Iterate through sections and print key-value pairs
    for section in config_data.sections():
        print(f"\n[{section}]")
        for key, value in config_data.items(section):
            # Mask sensitive keys like api_key if necessary for printing
            if 'key' in key.lower() or 'password' in key.lower():
                 print(f"{key} = ******")
            else:
                 print(f"{key} = {value}")

    # Specifically print DEFAULT section items (often used for fallbacks)
    if 'DEFAULT' in config_data:
        print("\n\n[DEFAULT] Section Details:")
        print("=" * 40)
        for key, value in config_data.items('DEFAULT'):
             if 'key' in key.lower() or 'password' in key.lower():
                 print(f"{key} = ******")
             else:
                 print(f"{key} = {value}")

    print(f"\nConfiguration loaded from: {config_manager._get_config_path()}")
    print("\nConfig printing test completed.")

if __name__ == "__main__":
    print_config()
