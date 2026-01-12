"""
Client entry point for YSimulator.

This module initializes and runs a simulation client that connects to the
Ray orchestration server and executes agent behaviors.
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
from YSimulator.YClient.client import SimulationClient
from YSimulator.YClient.LLM_interactions.llm_service import LLMService
from YSimulator.YClient.LLM_interactions.vllm_service import VLLMService
from YSimulator.YClient.news_feeds.news_service import NewsFeedService


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
    config_path: Path, client_name: str, logging_config: dict = None
) -> logging.Logger:
    """
    Set up rotating JSON logging for the client with gzip compression.

    Args:
        config_path: Path to the configuration directory
        client_name: Name of the client instance
        logging_config: Optional logging configuration dict with keys:
            - enable_execution_log: bool (default True)
            - enable_console_log: bool (default True)

    Returns:
        Configured logger instance
    """
    # Default logging configuration
    if logging_config is None:
        logging_config = {}

    enable_execution_log = logging_config.get("enable_execution_log", True)
    enable_console_log = logging_config.get("enable_console_log", True)

    log_dir = config_path / "logs"
    log_dir.mkdir(exist_ok=True)

    # Create logger
    logger = logging.getLogger(f"YSimulator.Client.{client_name}")
    logger.setLevel(logging.INFO)

    # Add file handler if enabled
    if enable_execution_log:
        log_file = log_dir / f"{client_name}_execution.log"

        # Create rotating file handler (10MB per file, keep 5 backups)
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
        description="YSimulator Client - Simulation client for social media agents"
    )
    parser.add_argument(
        "--config",
        type=str,
        default=".",
        help="Path to configuration directory containing simulation_config.json (default: current directory)",
    )
    args = parser.parse_args()

    # Validate config directory and check for required files
    config_dir = validate_config_directory(
        args.config,
        required_files=[
            "simulation_config.json",
            "agent_population.json",
            "prompts.json",
        ],
    )

    # Load simulation config first to get client name
    sim_config_file = config_dir / "simulation_config.json"
    try:
        with open(sim_config_file, "r") as f:
            sim_config = json.load(f)
    except json.JSONDecodeError as e:
        print(f"❌ Error: Invalid JSON in '{sim_config_file}': {e}")
        sys.exit(1)

    # Extract client name from config (not argparse)
    client_name = sim_config.get("client_name", "client_1")

    # Helper function to find client-specific or generic config file
    def find_config_file(base_name: str) -> Path:
        """Find client-specific config file or fall back to generic."""
        client_specific = config_dir / f"{client_name}_{base_name}"
        generic = config_dir / base_name

        if client_specific.exists():
            print(f"Using client-specific config: {client_specific.name}")
            return client_specific
        else:
            return generic

    # Use client-specific file names with fallback to conventional names
    agent_config_file = find_config_file("agent_population.json")
    prompts_config_file = find_config_file("prompts.json")

    # Load configuration files
    start_time = time.time()
    config_files = {
        str(agent_config_file): "agent population",
        str(prompts_config_file): "LLM prompts",
    }

    configs = {}
    for filename, description in config_files.items():
        try:
            with open(filename, "r") as f:
                configs[filename] = json.load(f)
        except json.JSONDecodeError as e:
            print(f"❌ Error: Invalid JSON in '{filename}': {e}")
            sys.exit(1)

    agent_config = configs[str(agent_config_file)]
    prompts_config = configs[str(prompts_config_file)]

    # Set up logging in config directory
    logging_config = sim_config.get("logging", {})
    logger = setup_logging(config_dir, client_name, logging_config)

    load_time = (time.time() - start_time) * 1000
    logger.info(
        "Client configuration loaded",
        extra={
            "extra_data": {
                "client_name": client_name,
                "config_dir": str(config_dir),
                "execution_time_ms": load_time,
            }
        },
    )

    # Get server address from temp file or config
    server_address = sim_config["server"].get("address")
    if not server_address:
        # Fallback to temp file in config directory
        ray_config_file = config_dir / "ray_config.temp"
        if not ray_config_file.exists():
            print(f"❌ Error: '{ray_config_file}' not found and no server address in config.")
            print("Start run_server.py first.")
            sys.exit(1)
        with open(ray_config_file, "r") as f:
            server_address = f.read().strip()

    logger.info(
        "Connecting to Ray cluster", extra={"extra_data": {"server_address": server_address}}
    )

    print(f"--- Connecting to Cluster at {server_address} ---")

    # Initialize with namespace from config
    namespace = sim_config.get("namespace", "social_sim")
    connect_start = time.time()
    ray.init(address=server_address, namespace=namespace, ignore_reinit_error=True)
    connect_time = (time.time() - connect_start) * 1000

    logger.info(
        "Connected to Ray cluster",
        extra={"extra_data": {"namespace": namespace, "execution_time_ms": connect_time}},
    )

    print(f"--- Launching Client {client_name} ---")
    print(f"--- Namespace: {namespace} ---")
    print(f"--- LLM Model: {sim_config['llm']['model']} ---")
    print(f"--- 📋 Logs: {config_dir / 'logs'} ---")

    # Calculate total number of agents
    num_predefined = len(agent_config.get("agents", []))
    num_generated = agent_config.get("generation_config", {}).get("num_additional_agents", 0)
    total_agents = num_predefined + num_generated
    print(
        f"--- Number of Agents: {total_agents} ({num_predefined} predefined + {num_generated} generated) ---"
    )

    logger.info(
        "Creating LLM service and client actors",
        extra={"extra_data": {"num_agents": total_agents, "llm_model": sim_config["llm"]["model"]}},
    )

    # Create LLM service with configuration
    # Support both Ollama (default) and vLLM backends
    llm_start = time.time()
    llm_config = sim_config["llm"]
    llm_v_config = sim_config.get("llm_v")  # Get vision LLM config if available
    
    # Determine which LLM backend to use
    # Default to "ollama" for backward compatibility and macOS support
    llm_backend = llm_config.get("backend", "ollama").lower()
    
    # Get number of LLM actors (default: 1 for backward compatibility)
    num_llm_actors = llm_config.get("num_actors", 1)
    
    # Get reuse_actors flag (default: False for backward compatibility)
    reuse_actors = llm_config.get("reuse_actors", False)
    
    # Get actor name prefix (default: ysim_llm)
    actor_name_prefix = llm_config.get("actor_name_prefix", "ysim_llm")
    
    if llm_backend == "vllm":
        logger.info(f"Using vLLM backend with {num_llm_actors} actor(s) for LLM inference")
        reuse_msg = " (reusing existing if available)" if reuse_actors else ""
        print(f"--- Using vLLM backend ({num_llm_actors} actor(s) for parallel processing{reuse_msg}) ---")
        try:
            from YSimulator.YClient.llm_utils import create_llm_actors
            
            # Create LLM service with configured number of actors
            # Allocates GPU resources for each vLLM actor
            llm_service = create_llm_actors(
                llm_config=llm_config,
                prompts_config=prompts_config,
                num_actors=num_llm_actors,
                strategy="hash",  # Hash-based load balancing for agent affinity
                backend="vllm",
                enable_monitoring=False,
                llm_v_config=llm_v_config,
                logger=logger,
                reuse_actors=reuse_actors,
                actor_name_prefix=actor_name_prefix,
            )
        except ImportError as e:
            logger.error(f"Failed to import vLLM: {e}")
            print(f"❌ Error: vLLM not available: {e}")
            print("💡 Tip: vLLM requires Linux. On macOS, use 'ollama' backend instead.")
            sys.exit(1)
        except Exception as e:
            logger.error(f"Failed to initialize vLLM service: {e}")
            logger.error(f"Model: {llm_config.get('model', 'unknown')}")
            print(f"❌ Error: vLLM initialization failed: {e}")
            print("💡 Check the logs above for detailed error information.")
            print("💡 Common issues:")
            print("   - Insufficient GPU memory (try reducing gpu_memory_utilization or num_actors)")
            print("   - Model not found (check model path)")
            print("   - GPU compatibility issues (check CUDA version)")
            print("   - Insufficient GPU resources (ensure Ray has enough GPUs for num_actors)")
            sys.exit(1)
    else:
        # Default to Ollama backend
        if num_llm_actors > 1:
            logger.info(f"Using Ollama backend with {num_llm_actors} actors for parallel inference")
            reuse_msg = " (reusing existing if available)" if reuse_actors else ""
            print(f"--- Using Ollama backend ({num_llm_actors} actors for parallel processing{reuse_msg}) ---")
            try:
                from YSimulator.YClient.llm_utils import create_llm_actors
                
                llm_service = create_llm_actors(
                    llm_config=llm_config,
                    prompts_config=prompts_config,
                    num_actors=num_llm_actors,
                    strategy="hash",
                    backend="ollama",
                    enable_monitoring=False,
                    llm_v_config=llm_v_config,
                    logger=logger,
                    reuse_actors=reuse_actors,
                    actor_name_prefix=actor_name_prefix,
                )
            except Exception as e:
                logger.error(f"Failed to initialize Ollama service: {e}")
                print(f"❌ Error: Ollama initialization failed: {e}")
                sys.exit(1)
        else:
            logger.info("Using Ollama backend for LLM inference")
            print("--- Using Ollama backend ---")
            
            # Support actor reuse even for single actor
            if reuse_actors:
                from YSimulator.YClient.llm_utils import create_llm_actors
                llm_service = create_llm_actors(
                    llm_config=llm_config,
                    prompts_config=prompts_config,
                    num_actors=1,
                    backend="ollama",
                    llm_v_config=llm_v_config,
                    logger=logger,
                    reuse_actors=reuse_actors,
                    actor_name_prefix=actor_name_prefix,
                )
            else:
                llm_service = LLMService.remote(llm_config, prompts_config, llm_v_config)
    
    llm_time = (time.time() - llm_start) * 1000

    # Create News Feed service with configuration (optional)
    # Always create the service - page agents will register their feeds dynamically
    news_start = time.time()
    news_feeds_config = sim_config.get("news_feeds", {"feeds": []})
    news_service = NewsFeedService.remote(news_feeds_config, llm_service)
    feed_count = len(news_feeds_config.get("feeds", []))
    if feed_count > 0:
        logger.info(
            "News feed service enabled with static feeds",
            extra={"extra_data": {"feeds": feed_count}},
        )
    else:
        logger.info("News feed service enabled for page agents (no static feeds)")
    news_time = (time.time() - news_start) * 1000

    # Create client with all configurations
    client_start = time.time()
    client = SimulationClient.remote(
        client_name, llm_service, agent_config, sim_config, str(config_dir), logger, news_service
    )
    client_time = (time.time() - client_start) * 1000

    logger.info(
        "Client actors created",
        extra={
            "extra_data": {
                "llm_creation_time_ms": llm_time,
                "news_creation_time_ms": news_time,
                "client_creation_time_ms": client_time,
            }
        },
    )

    try:
        logger.info("Starting simulation")
        ray.get(client.run.remote())
    except KeyboardInterrupt:
        logger.info("Client stopping by user request")
        print("Client stopping...")
    except Exception as e:
        logger.error(f"Client error: {e}", extra={"extra_data": {"error": str(e)}})
        raise
    finally:
        logger.info("Client shutdown complete")
