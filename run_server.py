"""
Server entry point for YSimulator.

This module initializes and runs the Ray-based orchestration server that manages
the simulation, coordinates clients, and handles agent registration.
"""

import argparse
import gzip
import hashlib
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
from YSimulator.utils.init_db import database_exists, initialize_database
from YSimulator.YServer.server import OrchestratorServer


def _configure_model_cache_env():
    root = Path(os.environ.get("YSOCIAL_MODEL_CACHE_DIR", "~/.cache/ysocial_models")).expanduser()
    hf_home = root / "huggingface"
    transformers_cache = hf_home / "transformers"
    hub_cache = hf_home / "hub"
    torch_home = root / "torch"

    for path in (root, hf_home, transformers_cache, hub_cache, torch_home):
        path.mkdir(parents=True, exist_ok=True)

    os.environ.setdefault("YSOCIAL_MODEL_CACHE_DIR", str(root))
    os.environ.setdefault("HF_HOME", str(hf_home))
    os.environ.setdefault("TRANSFORMERS_CACHE", str(transformers_cache))
    os.environ.setdefault("HUGGINGFACE_HUB_CACHE", str(hub_cache))
    os.environ.setdefault("TORCH_HOME", str(torch_home))


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


def build_isolated_namespace(base_namespace: str, config_dir: Path) -> str:
    """Build a stable per-experiment namespace for servers sharing one Ray cluster."""
    digest = hashlib.sha256(str(config_dir.resolve()).encode()).hexdigest()[:10]
    return f"{base_namespace}_{digest}"


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


def _get_short_ray_temp_dir(config_dir: Path, ray_config: dict) -> Path:
    """
    Return a Ray temp dir path short enough for AF_UNIX socket limits.

    Ray appends a long session/sockets suffix under _temp_dir. On HPC systems the
    experiment directory path can exceed the 107-byte Unix socket pathname limit,
    so we create a short alias path pointing to the real storage directory.
    """
    configured = ray_config.get("temp_dir")
    if configured:
        target_dir = Path(configured)
        if not target_dir.is_absolute():
            target_dir = config_dir / target_dir
    else:
        target_dir = config_dir / "ray"

    target_dir.mkdir(parents=True, exist_ok=True)

    # Conservative allowance for Ray's generated suffix:
    # /session_<timestamp>_<pid>/sockets/plasma_store
    max_base_len = 35
    if len(str(target_dir)) <= max_base_len:
        return target_dir

    short_roots = [
        Path(os.environ.get("YSIM_RAY_ALIAS_ROOT", "")).expanduser()
        if os.environ.get("YSIM_RAY_ALIAS_ROOT")
        else None,
        Path("/dev/shm"),
        Path("/var/tmp"),
        Path("/tmp"),
    ]

    short_roots = [root for root in short_roots if root and root.exists() and os.access(root, os.W_OK)]
    target_hash = hashlib.sha1(str(target_dir).encode("utf-8")).hexdigest()[:12]

    for root in short_roots:
        alias_path = root / f"ysr_{target_hash}"
        try:
            if alias_path.exists() or alias_path.is_symlink():
                if alias_path.is_symlink() and alias_path.resolve() == target_dir.resolve():
                    return alias_path
                if alias_path.is_dir() and alias_path.resolve() == target_dir.resolve():
                    return alias_path
                continue

            os.symlink(str(target_dir), str(alias_path), target_is_directory=True)
            return alias_path
        except Exception:
            continue

    return target_dir


if __name__ == "__main__":
    _configure_model_cache_env()
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
    configured_namespace = config.get("namespace", "social_sim")
    namespace = configured_namespace
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
        db_config["sqlite"]["filename"] = "database_server.db"
    elif db_config.get("type") in ["postgresql", "mysql"]:
        # For PostgreSQL/MySQL, append server_name to database name
        db_type = db_config["type"]
        type_config = db_config.get(db_type, {})
        base_db_name = type_config.get("database", "ysimulator")
        unique_db_name = f"{base_db_name}_{server_name}"
        db_config[db_type]["database"] = unique_db_name

    redis_config = config.get("redis")  # Redis configuration (optional)
    simulation_config = config.get("simulation", {})  # Simulation configuration (optional)
    ray_config = config.get("ray", {})  # Ray configuration (optional)

    # Add posts configuration to simulation_config for consistency
    posts_config = config.get("posts", {})
    if posts_config:
        simulation_config["posts"] = posts_config

    # Set up logging in config directory
    logging_config = config.get("logging", {})
    logger = setup_logging(config_dir, server_name, logging_config)

    if "recommendations" in config:
        logger.warning(
            "Ignoring server_config recommendations.default_limit; "
            "configure recommendation limits in client simulation_config.json under recommendations.default_limit"
        )

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

    # Handle address and port configuration.
    # If no explicit address is provided, prefer reusing an already-running local Ray cluster.
    start_new_cluster = (not address) or (address == "auto")
    explicit_ray_url = None
    reused_existing_cluster = False

    if not start_new_cluster:
        if address.startswith("ray://"):
            explicit_ray_url = address
        elif port:
            explicit_ray_url = f"ray://{address}:{port}"
        else:
            if ":" in address:
                explicit_ray_url = f"ray://{address}"
                print(
                    "⚠️  Warning: Port appears to be in the address field. "
                    "Consider using separate 'address' and 'port' fields."
                )
            else:
                explicit_ray_url = address

        print(f"--- Attempting to connect to existing Ray cluster at {explicit_ray_url} ---")
    else:
        print("--- Looking for an existing local Ray cluster to reuse ---")
        if port:
            print(f"⚠️  Warning: Port {port} specified but will be ignored.")
            print("    If no existing cluster is found, Ray will still pick a random local port.")

    init_kwargs = {"include_dashboard": False, "namespace": namespace}
    if explicit_ray_url:
        init_kwargs["address"] = explicit_ray_url

    init_start = time.time()
    context = None

    if start_new_cluster:
        try:
            context = ray.init(address="auto", **init_kwargs)
            reused_existing_cluster = True
            print("--- Reusing existing local Ray cluster ---")
        except Exception:
            print("--- No reusable local Ray cluster found; starting a new one ---")
            context = ray.init(**init_kwargs)
    else:
        context = ray.init(**init_kwargs)

    # If the target namespace already contains an Orchestrator actor, isolate this experiment
    # into a stable config-dir-derived namespace while staying on the same Ray cluster.
    connected_to_existing_cluster = reused_existing_cluster or (explicit_ray_url is not None)

    if connected_to_existing_cluster:
        try:
            ray.get_actor("Orchestrator", namespace=namespace)
            isolated_namespace = build_isolated_namespace(configured_namespace, config_dir)
            if isolated_namespace != namespace:
                logger.info(
                    f"Namespace collision detected for '{namespace}'. "
                    f"Switching this experiment to isolated namespace '{isolated_namespace}'."
                )
                ray.shutdown()
                namespace = isolated_namespace
                reconnect_kwargs = {"include_dashboard": False, "namespace": namespace}
                if explicit_ray_url:
                    reconnect_kwargs["address"] = explicit_ray_url
                else:
                    reconnect_kwargs["address"] = "auto"
                context = ray.init(**reconnect_kwargs)
        except ValueError:
            pass

    ray_address = context.address_info["address"]
    init_time = (time.time() - init_start) * 1000

    logger.info(
        "Ray cluster initialized",
        extra={
            "extra_data": {
                "ray_address": ray_address,
                "namespace": namespace,
                "configured_namespace": configured_namespace,
                "reused_existing_cluster": reused_existing_cluster,
                "execution_time_ms": init_time,
            }
        },
    )

    # Save connection details for clients in config directory
    ray_config_file = config_dir / "ray_config.temp"
    with open(ray_config_file, "w") as f:
        f.write(ray_address)
    namespace_config_file = config_dir / "ray_namespace.temp"
    with open(namespace_config_file, "w") as f:
        f.write(namespace)

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
        if namespace_config_file.exists():
            namespace_config_file.unlink()
        ray.shutdown()
        logger.info("Server shutdown complete")
