"""
Server entry point for YSimulator.

This module initializes and runs the Ray-based orchestration server that manages
the simulation, coordinates clients, and handles agent registration.
"""

import argparse
import gzip
import json
import logging
import os
import shutil
import sys
import time
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

import ray

from YSimulator.common_utils import validate_config_directory
from YSimulator.YServer.server import OrchestratorServer
from YSimulator.utils.init_db import initialize_database, database_exists


def compress_rotated_log(source, dest):
    """
    Compress a rotated log file using gzip.

    Args:
        source: Path to the source log file
        dest: Path to the destination compressed file
    """
    with open(source, "rb") as f_in:
        with gzip.open(dest, "wb") as f_out:
            shutil.copyfileobj(f_in, f_out)
    os.remove(source)


def setup_logging(
    config_path: Path, server_name: str, logging_config: dict = None
) -> logging.Logger:
    """
    Set up rotating JSON logging for the server with gzip compression.

    Args:
        config_path: Path to the configuration directory
        server_name: Name of the server instance
        logging_config: Optional logging configuration dict with keys:
            - enable_server_log: bool (default True)
            - enable_console_log: bool (default True)

    Returns:
        Configured logger instance
    """
    # Default logging configuration
    if logging_config is None:
        logging_config = {}

    enable_server_log = logging_config.get("enable_server_log", True)
    enable_console_log = logging_config.get("enable_console_log", True)

    log_dir = config_path / "logs"
    log_dir.mkdir(exist_ok=True)

    # Create logger
    logger = logging.getLogger("YSimulator.Server")
    logger.setLevel(logging.INFO)

    # Create rotating file handler if enabled
    if enable_server_log:
        log_file = log_dir / f"{server_name}_server.log"
        handler = RotatingFileHandler(log_file, maxBytes=10 * 1024 * 1024, backupCount=5)  # 10MB

        # Add compression for rotated files
        handler.rotator = compress_rotated_log
        handler.namer = lambda name: name + ".gz"

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

    # Add console handler if enabled
    if enable_console_log:
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
        default=".",
        help="Path to configuration directory containing server_config.json (default: current directory)",
    )
    args = parser.parse_args()

    # Validate config directory and check for required file
    config_dir = validate_config_directory(args.config, required_files=["server_config.json"])

    # Use conventional file name
    config_file = config_dir / "server_config.json"

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
    min_to_start = config.get("min_to_start", 1)  # Minimum clients before simulation starts
    timeout_seconds = config.get("timeout_seconds", 60)  # Stale client timeout (default: 60s)

    # Database configuration - make database unique per server instance
    db_config = config.get("database", {})
    # Support legacy database_file parameter for backward compatibility
    if "database_file" in config:
        db_config = {"type": "sqlite", "sqlite": {"filename": config["database_file"]}}
    elif not db_config:
        db_config = {"type": "sqlite", "sqlite": {"filename": "simulation.db"}}

    # Make database name unique per server instance
    # This ensures each server instance has its own database
    if db_config.get("type") == "sqlite":
        sqlite_config = db_config.get("sqlite", {})
        base_filename = sqlite_config.get("filename", "simulation.db")
        # Add server_name to filename to make it unique
        name_parts = base_filename.rsplit(".", 1)
        if len(name_parts) == 2:
            unique_filename = f"{name_parts[0]}_{server_name}.{name_parts[1]}"
        else:
            unique_filename = f"{base_filename}_{server_name}"
        db_config["sqlite"]["filename"] = unique_filename
    elif db_config.get("type") in ["postgresql", "mysql"]:
        # For PostgreSQL/MySQL, append server_name to database name
        db_type = db_config["type"]
        type_config = db_config.get(db_type, {})
        base_db_name = type_config.get("database", "ysimulator")
        unique_db_name = f"{base_db_name}_{server_name}"
        db_config[db_type]["database"] = unique_db_name

    redis_config = config.get("redis")  # Redis configuration (optional)
    simulation_config = config.get("simulation", {})  # Simulation configuration (optional)

    # Add posts configuration to simulation_config for consistency
    posts_config = config.get("posts", {})
    if posts_config:
        simulation_config["posts"] = posts_config

    # Set up logging in config directory
    logging_config = config.get("logging", {})
    logger = setup_logging(config_dir, server_name, logging_config)

    load_time = (time.time() - start_time) * 1000

    # Get database name for logging
    if db_config.get("type") == "sqlite":
        db_name = db_config["sqlite"]["filename"]
    elif db_config.get("type") == "postgresql":
        db_name = db_config["postgresql"]["database"]
    elif db_config.get("type") == "mysql":
        db_name = db_config["mysql"]["database"]
    else:
        db_name = "unknown"

    logger.info(
        "Server configuration loaded",
        extra={
            "extra_data": {
                "server_name": server_name,
                "config_file": str(config_file),
                "db_type": db_config.get("type", "sqlite"),
                "db_name": db_name,
                "execution_time_ms": load_time,
            }
        },
    )

    # Check if database exists, if not initialize it
    db_init_start = time.time()
    if not database_exists(db_config, config_dir):
        logger.info(
            f"Database does not exist. Initializing new database: {db_name}",
            extra={"extra_data": {"db_type": db_config.get("type", "sqlite")}},
        )
        print(f"--- 🔧 Initializing new database: {db_name} ---")

        if not initialize_database(db_config, config_dir, logger):
            logger.error("Failed to initialize database. Exiting.")
            sys.exit(1)

        db_init_time = (time.time() - db_init_start) * 1000
        logger.info(
            "Database initialized successfully",
            extra={"extra_data": {"db_name": db_name, "execution_time_ms": db_init_time}},
        )
        print(f"--- ✅ Database initialized: {db_name} ---")
    else:
        logger.info(
            f"Using existing database: {db_name}",
            extra={"extra_data": {"db_type": db_config.get("type", "sqlite")}},
        )
        print(f"--- 💾 Using existing database: {db_name} ---")

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

    # Save address for clients in config directory
    ray_config_file = config_dir / "ray_config.temp"
    with open(ray_config_file, "w") as f:
        f.write(ray_address)

    print(f"--- 🚀 Server Running on {ray_address} ---")
    print(f"--- 📝 Server Name: {server_name} ---")
    print(f"--- 📝 Namespace: {namespace} ---")
    print(f"--- 💾 Database Type: {db_config.get('type', 'sqlite').upper()} ---")
    print(f"--- 📋 Logs: {config_dir / 'logs'} ---")
    print("--- 💾 Waiting for clients... ---")

    # Start orchestrator actor
    actor_start = time.time()
    server = OrchestratorServer.options(name="Orchestrator").remote(
        db_config=db_config,
        config_path=str(config_dir),
        min_to_start=min_to_start,
        server_name=server_name,
        redis_config=redis_config,
        timeout_seconds=timeout_seconds,
        simulation_config=simulation_config,
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
