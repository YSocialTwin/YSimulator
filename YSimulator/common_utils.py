"""
Common utilities for YSimulator.

This module provides shared utility functions used across the simulation system.
"""

import sys
from pathlib import Path


def validate_config_directory(config_path_str: str, required_files: list = None) -> Path:
    """
    Validate that a configuration directory exists and contains required files.

    Args:
        config_path_str: Path to the configuration directory as string
        required_files: List of required file names (optional)

    Returns:
        Path: Validated Path object for the configuration directory

    Raises:
        SystemExit: If validation fails
    """
    config_dir = Path(config_path_str)

    # Check if directory exists
    if not config_dir.exists():
        print(f"❌ Error: Configuration directory '{config_dir}' not found.")
        print("See CONFIG.md for configuration details.")
        sys.exit(1)

    # Check if it's a directory
    if not config_dir.is_dir():
        print(f"❌ Error: '{config_dir}' is not a directory.")
        print("Please provide a directory path containing configuration files.")
        sys.exit(1)

    # Check for required files if specified
    if required_files:
        for filename in required_files:
            config_file = config_dir / filename
            if not config_file.exists():
                print(f"❌ Error: Required file '{config_file}' not found.")
                print(f"Please ensure {filename} exists in the configuration directory.")
                print("See CONFIG.md for configuration details.")
                sys.exit(1)

    return config_dir
