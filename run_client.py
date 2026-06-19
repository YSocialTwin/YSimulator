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
import traceback
import uuid
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

import ray

from YSimulator.common_utils import validate_config_directory
from YSimulator.YClient.client import SimulationClient
from YSimulator.YClient.news_feeds.news_service import NewsFeedService


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
            - enable_prompt_log: bool (default False)

    Returns:
        Configured logger instance
    """
    # Default logging configuration
    if logging_config is None:
        logging_config = {}

    enable_execution_log = logging_config.get("enable_execution_log", True)
    enable_console_log = logging_config.get("enable_console_log", True)
    enable_prompt_log = logging_config.get("enable_prompt_log", False)

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
        
        # Create custom console formatter that truncates long messages
        class TruncatingConsoleFormatter(logging.Formatter):
            """Console formatter that truncates long messages for readability."""
            
            def format(self, record):
                # Get the full formatted message first
                formatted = super().format(record)
                
                # Find where the message starts (after timestamp - name - level - )
                # Format is: "timestamp - name - level - message"
                parts = formatted.split(" - ", 3)  # Split on first 3 occurrences
                
                if len(parts) == 4 and len(parts[3]) > 200:
                    # Truncate just the message part
                    parts[3] = parts[3][:200] + "..."
                    return " - ".join(parts)
                
                return formatted
        
        console_handler.setFormatter(
            TruncatingConsoleFormatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        )
        logger.addHandler(console_handler)

    # Set up prompt logging if enabled
    if enable_prompt_log:
        prompt_logger = logging.getLogger(f"YSimulator.Client.{client_name}.prompts")
        prompt_logger.setLevel(logging.DEBUG)
        prompt_logger.propagate = False  # Don't propagate to parent logger
        
        prompt_log_file = log_dir / f"{client_name}_prompts.log"
        
        # Create rotating file handler for prompts (50MB per file, keep 3 backups)
        prompt_handler = RotatingFileHandler(
            prompt_log_file, maxBytes=50 * 1024 * 1024, backupCount=3
        )
        
        # Add compression for rotated files
        prompt_handler.rotator = compress_rotated_log
        prompt_handler.namer = lambda name: name + ".gz"
        
        # Create JSON formatter for prompts
        class PromptJsonFormatter(logging.Formatter):
            def format(self, record):
                log_data = {
                    "timestamp": datetime.utcnow().isoformat(),
                    "level": record.levelname,
                    "message": record.getMessage(),
                }
                if hasattr(record, "extra_data"):
                    log_data.update(record.extra_data)
                return json.dumps(log_data, indent=2)
        
        prompt_handler.setFormatter(PromptJsonFormatter())
        prompt_logger.addHandler(prompt_handler)
        
        logger.info(f"Prompt logging enabled - writing to {prompt_log_file}")

    return logger


def resolve_client_namespace(config_dir: Path, sim_config: dict) -> str:
    """Return the Ray namespace clients should use for this experiment."""
    namespace_config_file = config_dir / "ray_namespace.temp"
    if namespace_config_file.exists():
        return namespace_config_file.read_text().strip()
    return sim_config.get("namespace", "social_sim")


def _llm_models_configured(sim_config: dict) -> bool:
    llm_cfg = sim_config.get("llm") or {}
    llm_v_cfg = sim_config.get("llm_v") or {}
    return bool(llm_cfg.get("model") or llm_v_cfg.get("model"))


if __name__ == "__main__":
    _configure_model_cache_env()
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description="YSimulator Client - Simulation client for social media agents"
    )
    parser.add_argument(
        "--config",
        type=str,
        default=".",
        help="Path to configuration directory or simulation_config.json file (default: current directory)",
    )
    parser.add_argument(
        "--agents",
        "--population",
        type=str,
        default=None,
        dest="agents",
        help="Path to agent_population.json file (optional, overrides config directory)",
    )
    parser.add_argument(
        "--prompts",
        type=str,
        default=None,
        help="Path to prompts.json file (optional, overrides config directory)",
    )
    args = parser.parse_args()

    # Determine configuration directory and files
    config_path = Path(args.config)

    if config_path.is_file():
        # If --config points to a file, use its parent directory as config_dir
        config_dir = config_path.parent
        sim_config_file = config_path
    else:
        # If --config points to a directory, validate it
        # Only require simulation_config.json if we're relying on directory structure
        config_dir = validate_config_directory(
            args.config,
            required_files=(
                ["simulation_config.json"] if not (args.agents and args.prompts) else None
            ),
        )
        sim_config_file = config_dir / "simulation_config.json"

    # Determine agent population and prompts files
    if args.agents:
        agent_population_file = Path(args.agents)
        if not agent_population_file.exists():
            print(f"❌ Error: Agent population file '{agent_population_file}' not found.")
            sys.exit(1)
    else:
        agent_population_file = config_dir / "agent_population.json"
        if not agent_population_file.exists():
            print(f"❌ Error: Required file '{agent_population_file}' not found.")
            sys.exit(1)

    if args.prompts:
        prompts_file = Path(args.prompts)
        if not prompts_file.exists():
            print(f"❌ Error: Prompts file '{prompts_file}' not found.")
            sys.exit(1)
    else:
        prompts_file = config_dir / "prompts.json"
        if not prompts_file.exists():
            print(f"❌ Error: Required file '{prompts_file}' not found.")
            sys.exit(1)

    # Load simulation config first to get client name
    try:
        with open(sim_config_file, "r") as f:
            sim_config = json.load(f)
    except json.JSONDecodeError as e:
        print(f"❌ Error: Invalid JSON in '{sim_config_file}': {e}")
        sys.exit(1)

    # Extract client name from config (not argparse)
    client_name = sim_config.get("client_name", "client_1")
    runtime_client_id = f"{config_dir.name}:{client_name}"

    # Helper function to find client-specific or generic config file
    def find_config_file(base_name: str, override_file: Path = None) -> Path:
        """Find client-specific config file or fall back to generic."""
        if override_file:
            return override_file

        client_specific = config_dir / f"{client_name}_{base_name}"
        generic = config_dir / base_name

        if client_specific.exists():
            print(f"Using client-specific config: {client_specific.name}")
            return client_specific
        else:
            return generic

    # Use client-specific file names with fallback to conventional names
    agent_config_file = find_config_file("agent_population.json", agent_population_file)
    prompts_config_file = find_config_file("prompts.json", prompts_file)

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
                print(f"✓ Loaded {description} from: {filename}")
        except json.JSONDecodeError as e:
            print(f"❌ Error: Invalid JSON in '{filename}': {e}")
            sys.exit(1)

    agent_config = configs[str(agent_config_file)]
    prompts_config = configs[str(prompts_config_file)]

    # Set up logging in config directory
    logging_config = sim_config.get("logging", {})
    logger = setup_logging(config_dir, client_name, logging_config)
    
    # Add log directory path to logging_config for Ray actors
    logging_config["log_dir"] = str(config_dir / "logs")

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

    # Get server address - check ray_config.temp first (takes priority), then config
    ray_config_file = config_dir / "ray_config.temp"

    if ray_config_file.exists():
        # Priority: Use ray_config.temp if it exists
        with open(ray_config_file, "r") as f:
            ray_address = f.read().strip()
        print(f"--- Using server address from ray_config.temp: {ray_address} ---")
    else:
        # Fallback: Use server address from config
        server_config = sim_config.get("server", {})
        server_address = server_config.get("address")
        server_port = server_config.get("port")

        if not server_address:
            print("❌ Error: No server address specified in configuration.")
            print(
                "Please set 'server.address' in simulation_config.json to the Ray cluster address."
            )
            print(
                "The server address is displayed when you start run_server.py (look for '🚀 Server Running on...')."
            )
            print('Example: "server": {"address": "127.0.0.1", "port": 10001}')
            print('Or: "server": {"address": "ray://127.0.0.1:10001", "port": null}')
            print(
                f"Alternatively, start the server in the same config directory to create {ray_config_file}"
            )
            sys.exit(1)

        # Construct full Ray address
        # If address already contains "ray://" and port, use it as-is
        # Otherwise, construct from address and port fields
        if server_address.startswith("ray://"):
            ray_address = server_address
        elif server_port:
            # Construct ray:// URL from separate address and port
            ray_address = f"ray://{server_address}:{server_port}"
        else:
            # Check if port is embedded in address (legacy format - not recommended)
            if ":" in server_address:
                print(
                    "⚠️  Warning: Port appears to be in the address field. "
                    "Please use separate 'address' and 'port' fields."
                )
                ray_address = f"ray://{server_address}"
            else:
                print("❌ Error: No server port specified in configuration.")
                print("Please set 'server.port' or include port in 'server.address'.")
                print('Example: "server": {"address": "127.0.0.1", "port": 10001}')
                sys.exit(1)

    logger.info("Connecting to Ray cluster", extra={"extra_data": {"server_address": ray_address}})

    print(f"--- Connecting to Cluster at {ray_address} ---")

    # Initialize with namespace from config, unless server provided an override for this experiment.
    namespace = resolve_client_namespace(config_dir, sim_config)
    connect_start = time.time()
    ray.init(address=ray_address, namespace=namespace, ignore_reinit_error=True)
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
    # Attach client identity for shared actor lease tracking.
    llm_config["client_name"] = client_name
    llm_config["_lease_client_id"] = f"{client_name}:{os.getpid()}:{uuid.uuid4().hex}"
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

    llm_service = None

    if not _llm_models_configured(sim_config):
        logger.info("No LLM models configured; running client without LLM actors")
        print("--- No LLM model configured; skipping LLM actor startup ---")
    elif llm_backend == "vllm":
        logger.info(f"Using vLLM backend with {num_llm_actors} actor(s) for LLM inference")
        reuse_msg = " (reusing existing if available)" if reuse_actors else ""
        print(
            f"--- Using vLLM backend ({num_llm_actors} actor(s) for parallel processing{reuse_msg}) ---"
        )
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
            resolved_num_llm_actors = llm_config.get("_resolved_num_actors", num_llm_actors)
            resolved_actor_name_prefix = llm_config.get(
                "_resolved_actor_name_prefix", actor_name_prefix
            )
            resolved_actor_namespace = llm_config.get("_resolved_actor_namespace")
            if llm_config.get("_reused_existing_pool"):
                logger.info(
                    f"Attached to existing local vLLM pool: model={llm_config.get('model')}, "
                    f"actors={resolved_num_llm_actors}, prefix={resolved_actor_name_prefix}, "
                    f"namespace={resolved_actor_namespace or namespace}"
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
            print(
                "   - Insufficient GPU memory (try reducing gpu_memory_utilization or num_actors)"
            )
            print("   - Model not found (check model path)")
            print("   - GPU compatibility issues (check CUDA version)")
            print("   - Insufficient GPU resources (ensure Ray has enough GPUs for num_actors)")
            sys.exit(1)
    else:
        # Default to Ollama backend
        if num_llm_actors > 1:
            logger.info(f"Using Ollama backend with {num_llm_actors} actors for parallel inference")
            reuse_msg = " (reusing existing if available)" if reuse_actors else ""
            print(
                f"--- Using Ollama backend ({num_llm_actors} actors for parallel processing{reuse_msg}) ---"
            )
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
                logging_config=logging_config,
            )

    resolved_num_llm_actors = llm_config.get("_resolved_num_actors", num_llm_actors)
    resolved_actor_name_prefix = llm_config.get("_resolved_actor_name_prefix", actor_name_prefix)
    resolved_actor_namespace = llm_config.get("_resolved_actor_namespace")
    resolved_service_backend = llm_config.get("_resolved_service_backend", llm_backend)
    resolved_pool_backend = llm_config.get("_resolved_pool_backend", llm_backend)

    if llm_service is not None and resolved_service_backend != llm_backend:
        logger.info(
            f"Upgraded non-vLLM backend to batch-capable service backend: {resolved_service_backend}"
        )

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
        runtime_client_id,
        llm_service,
        agent_config,
        sim_config,
        str(config_dir),
        logger,
        news_service,
        str(agent_config_file),
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
        # Capture full exception details including traceback
        error_type = type(e).__name__
        error_msg = str(e)
        full_traceback = traceback.format_exc()
        
        # Log complete error message (console handler will truncate if needed)
        logger.error(
            f"Client error: {error_type}: {error_msg}",
            extra={
                "extra_data": {
                    "error_type": error_type,
                    "error_message": error_msg,
                    "traceback": full_traceback,
                }
            },
        )
        raise
    finally:
        try:
            if resolved_pool_backend:
                from YSimulator.YClient.llm_utils import release_llm_pool_lease

                release_llm_pool_lease(
                    backend=resolved_pool_backend,
                    actor_name_prefix=resolved_actor_name_prefix,
                    num_actors=resolved_num_llm_actors,
                    client_id=llm_config.get("_lease_client_id", client_name),
                    actor_namespace=resolved_actor_namespace,
                    logger=logger,
                )
        except Exception as cleanup_error:
            logger.warning(f"Failed to release LLM pool lease cleanly: {cleanup_error}")
        logger.info("Client shutdown complete")
