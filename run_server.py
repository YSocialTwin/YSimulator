"""
Server entry point for YSimulator.

This module initializes and runs the Ray-based orchestration server that manages
the simulation, coordinates clients, and handles agent registration.
"""

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

import ray

from YServer.server import OrchestratorServer


def setup_logging(config_path: Path, server_name: str) -> logging.Logger:
    """
    Set up rotating JSON logging for the server.

    Args:
        config_path: Path to the configuration directory
        server_name: Name of the server instance

    Returns:
        Configured logger instance
    """
    log_dir = config_path / "logs"
    log_dir.mkdir(exist_ok=True)

    log_file = log_dir / f"{server_name}_server.log"

    # Create logger
    logger = logging.getLogger("YSimulator.Server")
    logger.setLevel(logging.INFO)

    # Create rotating file handler (10MB per file, keep 5 backups)
    handler = RotatingFileHandler(log_file, maxBytes=10 * 1024 * 1024, backupCount=5)  # 10MB

    # Create JSON formatter
    class JsonFormatter(logging.Formatter):
        def format(self, record):
            log_data = {
                "timestamp": datetime.utcnow().isoformat(),
                "level": record.levelname,
                "message": record.getMessage(),
                "module": record.module,
                "function": record.funcName,
                "line": record.lineno,
            }
            if hasattr(record, "execution_time"):
                log_data["execution_time_ms"] = record.execution_time
            if hasattr(record, "extra_data"):
                log_data.update(record.extra_data)
            return json.dumps(log_data)

    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)

    # Also log to console
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(
        logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    )
    logger.addHandler(console_handler)

    return logger


if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description="YSimulator Server - Ray-based social media simulation orchestrator"
    )
    parser.add_argument(
        "--config",
        type=str,
        default="server_config.json",
        help="Path to server configuration file (default: server_config.json)",
    )
    args = parser.parse_args()

    # Determine config file path
    config_file = Path(args.config)
    if not config_file.exists():
        print(f"❌ Error: Configuration file '{config_file}' not found.")
        print("See CONFIG.md for configuration details.")
        sys.exit(1)

    config_path = config_file.parent if config_file.parent != Path(".") else Path.cwd()

    # Load server configuration
    start_time = time.time()
    try:
        with open(config_file, "r") as f:
            config = json.load(f)
    except json.JSONDecodeError as e:
        print(f"❌ Error: Invalid JSON in '{config_file}': {e}")
        sys.exit(1)

    # Extract configuration
    server_name = config.get("server_name", "orchestrator_server")
    namespace = config.get("namespace", "social_sim")
    address = config.get("address", "auto")
    port = config.get("port")
    db_filename = config.get("database_file", "simulation.db")
    min_to_start = config.get("min_to_start", 1)  # Minimum clients before simulation starts

    # Create database in config path
    db_path = config_path / db_filename
    db_name = str(db_path)

    # Set up logging
    logger = setup_logging(config_path, server_name)

    load_time = (time.time() - start_time) * 1000
    logger.info(
        "Server configuration loaded",
        extra={
            "extra_data": {
                "server_name": server_name,
                "config_file": str(config_file),
                "execution_time_ms": load_time,
            }
        },
    )

    # Build ray.init() arguments
    init_kwargs = {"include_dashboard": False, "namespace": namespace}

    # Add address if not 'auto'
    if address and address != "auto":
        init_kwargs["address"] = address

    # Note: Port configuration is handled by Ray's internal mechanisms
    # Use RAY_ADDRESS environment variable or ray start --port for custom ports

    # Start Ray cluster
    init_start = time.time()
    context = ray.init(**init_kwargs)
    ray_address = context.address_info["address"]
    init_time = (time.time() - init_start) * 1000

    logger.info(
        "Ray cluster initialized",
        extra={
            "extra_data": {
                "ray_address": ray_address,
                "namespace": namespace,
                "execution_time_ms": init_time,
            }
        },
    )

    # Save address for clients
    ray_config_file = config_path / "ray_config.temp"
    with open(ray_config_file, "w") as f:
        f.write(ray_address)

    print(f"--- 🚀 Server Running on {ray_address} ---")
    print(f"--- 📝 Server Name: {server_name} ---")
    print(f"--- 📝 Namespace: {namespace} ---")
    print(f"--- 💾 Database: {db_name} ---")
    print(f"--- 📋 Logs: {config_path / 'logs'} ---")
    print(f"--- 💾 Waiting for clients... ---")

    # Start orchestrator actor
    actor_start = time.time()
    server = OrchestratorServer.options(name="Orchestrator").remote(
        db_name=db_name,
        min_to_start=min_to_start,
        config_path=str(config_path),
        server_name=server_name,
    )
    actor_time = (time.time() - actor_start) * 1000

    logger.info(
        "Orchestrator actor started", extra={"extra_data": {"execution_time_ms": actor_time}}
    )

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Server shutting down")
        print("Stopping...")
        if ray_config_file.exists():
            ray_config_file.unlink()
        ray.shutdown()
        logger.info("Server shutdown complete")
