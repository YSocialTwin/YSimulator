"""
Common utilities for YSimulator.

This module provides shared utility functions used across the simulation system.
"""

import sys
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


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
        logger.error(f"❌ Error: Configuration directory '{config_dir}' not found.")
        logger.info("See CONFIG.md for configuration details.")
        sys.exit(1)

    # Check if it's a directory
    if not config_dir.is_dir():
        logger.error(f"❌ Error: '{config_dir}' is not a directory.")
        logger.info("Please provide a directory path containing configuration files.")
        sys.exit(1)

    # Check for required files if specified
    if required_files:
        for filename in required_files:
            config_file = config_dir / filename
            if not config_file.exists():
                logger.error(f"❌ Error: Required file '{config_file}' not found.")
                logger.error(f"Please ensure {filename} exists in the configuration directory.")
                logger.info("See CONFIG.md for configuration details.")
                sys.exit(1)

    return config_dir
