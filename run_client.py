"""
Client entry point for YSimulator.

This module initializes and runs a simulation client that connects to the
Ray orchestration server and executes agent behaviors.
"""

import argparse
import json
import logging
import sys
import time
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

import ray

from YSimulator.common_utils import validate_config_directory
from YSimulator.YClient.LLM_interactions.llm_service import LLMService
from YSimulator.YClient.news_feeds.news_service import NewsFeedService
from YSimulator.YClient.client import SimulationClient


def setup_logging(config_path: Path, client_name: str) -> logging.Logger:
    """
    Set up rotating JSON logging for the client.

    Args:
        config_path: Path to the configuration directory
        client_name: Name of the client instance

    Returns:
        Configured logger instance
    """
    log_dir = config_path / "logs"
    log_dir.mkdir(exist_ok=True)

    log_file = log_dir / f"{client_name}_client.log"

    # Create logger
    logger = logging.getLogger(f"YSimulator.Client.{client_name}")
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
    logger = setup_logging(config_dir, client_name)

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
    llm_start = time.time()
    llm_v_config = sim_config.get("llm_v")  # Get vision LLM config if available
    llm_service = LLMService.remote(sim_config["llm"], prompts_config, llm_v_config)
    llm_time = (time.time() - llm_start) * 1000
    
    # Create News Feed service with configuration (optional)
    # Always create the service - page agents will register their feeds dynamically
    news_start = time.time()
    news_feeds_config = sim_config.get("news_feeds", {"feeds": []})
    news_service = NewsFeedService.remote(news_feeds_config, llm_service)
    feed_count = len(news_feeds_config.get("feeds", []))
    if feed_count > 0:
        logger.info("News feed service enabled with static feeds", extra={"extra_data": {"feeds": feed_count}})
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
                "client_creation_time_ms": client_time
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
