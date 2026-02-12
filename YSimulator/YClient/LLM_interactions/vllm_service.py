"""
vLLM-based LLM Service for YSimulator with batch inference support.

This module provides a Ray actor that uses vLLM for efficient batch inference,
achieving significant performance improvements over sequential Ollama processing.
The interface is designed to be compatible with the existing LLMService pattern.
"""

import logging
import os
from typing import Any, Dict, List, Optional, Tuple

import ray

# Initialize logger
logger = logging.getLogger(__name__)


@ray.remote
class VLLMService:
    """
    vLLM-based LLM service with batch inference support.

    This service uses vLLM's efficient batch inference capabilities to process
    multiple prompts in parallel, reducing the LLM bottleneck identified in
    the performance analysis.

    The service maintains the same interface as LLMService for compatibility
    with existing YClient patterns.
    """

    def __init__(
        self,
        llm_config: Optional[Dict[str, Any]] = None,
        prompts_config: Optional[Dict[str, Any]] = None,
        llm_v_config: Optional[Dict[str, Any]] = None,
        logging_config: Optional[Dict[str, Any]] = None,
        server=None,
        client_id: Optional[str] = None,
    ):
        """
        Initialize vLLM service with configuration.

        Args:
            llm_config: LLM configuration with keys:
                - model: Model name/path (e.g., "meta-llama/Llama-3.2-3B")
                - temperature: Sampling temperature (default: 0.7)
                - max_tokens: Maximum tokens to generate (default: 256)
                - max_model_len: Maximum sequence length (default: 40000)
                - tensor_parallel_size: Number of GPUs for tensor parallelism (default: 1)
                - gpu_memory_utilization: GPU memory utilization (default: 0.9)
                - enable_flashattention: Enable FlashAttention 2 (default: False)
            prompts_config: Prompt templates configuration (same as LLMService)
            llm_v_config: Vision LLM configuration with keys:
                - model: Vision model name/path (e.g., "openbmb/MiniCPM-V-2_6")
                - temperature: Sampling temperature (default: 0.5)
                - max_tokens: Maximum tokens to generate (default: 300)
                - max_model_len: Maximum sequence length (default: 40000)
            logging_config: Optional logging configuration dict
            server: Optional server reference for fetching articles
            client_id: Optional client ID for server requests
        """
        # ============================================================================
        # CRITICAL: GPU selection MUST happen FIRST, before ANY other operations
        # ============================================================================
        # This MUST be the absolute first thing in __init__ because:
        # 1. vLLM spawns subprocesses that need to inherit CUDA_VISIBLE_DEVICES
        # 2. Setting it after CUDA initialization is too late
        # 3. The environment must be set before ANY imports that might touch CUDA
        
        # Get list of candidate GPUs for retry logic
        candidate_gpus = VLLMService._get_candidate_gpus_static(llm_config)

        # Store server and client_id early for use in _initialize
        self.server = server
        self.client_id = client_id
        
        import sys


        print(
            f"####################\n{candidate_gpus}\n########################",
            file=sys.stdout,
            flush=True
        )
        
        # Try each GPU in order until one works
        last_error = None
        gpu_attempts = []
        
        for attempt_num, (gpu_id, free_gb, total_gb) in enumerate(candidate_gpus, 1):
            try:
                # Set GPU environment for this attempt
                VLLMService._set_gpu_env_for_attempt_static(gpu_id, attempt_num, len(candidate_gpus), free_gb)
                
                # Try to initialize with this GPU
                self._initialize(llm_config, prompts_config, llm_v_config, logging_config)
                
                # Success! Log and return
                print(
                    f"[GPU Attempt {attempt_num}/{len(candidate_gpus)}] ✅ Success! "
                    f"vLLM initialized on GPU {gpu_id}",
                    file=sys.stdout,
                    flush=True
                )
                return
                
            except Exception as e:
                last_error = e
                gpu_attempts.append((gpu_id, free_gb, str(e)))
                
                # Log this failed attempt
                error_summary = str(e).split('\n')[0] if '\n' in str(e) else str(e)
                error_summary = error_summary[:100]  # Limit length
                print(
                    f"[GPU Attempt {attempt_num}/{len(candidate_gpus)}] ❌ Failed on GPU {gpu_id} "
                    f"({free_gb:.2f} GB free): {error_summary}",
                    file=sys.stdout,
                    flush=True
                )
                
                # If this isn't the last GPU, continue to next
                if attempt_num < len(candidate_gpus):
                    continue
        
        # All GPUs exhausted - build comprehensive error message
        error_msg = f"\n{'='*70}\n"
        error_msg += "❌ VLLMService Initialization Failed - All GPUs Exhausted\n"
        error_msg += f"{'='*70}\n"
        error_msg += f"Attempted {len(gpu_attempts)} GPU(s):\n"
        for gpu_id, free_gb, error in gpu_attempts:
            error_summary = error.split('\n')[0] if '\n' in error else error
            error_summary = error_summary[:80]
            error_msg += f"  - GPU {gpu_id} ({free_gb:.2f} GB free): {error_summary}\n"
        error_msg += f"\nLast error: {type(last_error).__name__}: {str(last_error)[:200]}\n"
        error_msg += f"{'='*70}\n"
        
        print(error_msg, file=sys.stderr, flush=True)
        
        # Re-raise the last error
        raise RuntimeError(
            f"Failed to initialize vLLM on any of {len(gpu_attempts)} available GPU(s). "
            f"Last error: {type(last_error).__name__}: {str(last_error)}"
        ) from last_error
    
 
    @staticmethod
    def _get_candidate_gpus_static(llm_config: Optional[Dict[str, Any]] = None) -> List[Tuple[int, float, float]]:
        """
        Dynamically discovers all physical GPUs and returns them sorted by free memory.
        """
        import os
        # Save the original mask Ray gave us to restore it later if needed
        original_mask = os.environ.get("CUDA_VISIBLE_DEVICES", "")

        try:
            import pynvml
            # 1. Temporarily clear the mask so we can see all hardware on the host
            os.environ["CUDA_VISIBLE_DEVICES"] = "" 
            
            pynvml.nvmlInit()
            device_count = pynvml.nvmlDeviceGetCount()
            candidates = []

            for i in range(device_count):
                handle = pynvml.nvmlDeviceGetHandleByIndex(i)
                info = pynvml.nvmlDeviceGetMemoryInfo(handle)
                free_gb = info.free / (1024**3)
                total_gb = info.total / (1024**3)
                
                # Minimum threshold: skip cards that can't even hold the model weights
                # A 3B model (FP16/AWQ) usually needs at least 3-4GB free
                if free_gb > 2.0:
                    candidates.append((i, free_gb, total_gb))

            pynvml.nvmlShutdown()

            # 2. Sort by free memory (Highest first) 
            # This pushes the busy GPU 0 to the bottom of the list automatically
            candidates.sort(key=lambda x: x[1], reverse=True)
            
            # Restore the original mask (for safety) before returning the list
            os.environ["CUDA_VISIBLE_DEVICES"] = original_mask
            
            return candidates if candidates else [(0, 0.0, 0.0)]
                
        except Exception as e:
            # Always restore the mask on error
            os.environ["CUDA_VISIBLE_DEVICES"] = original_mask
            print(f"[GPU Selection] Discovery failed: {e}. Falling back to default.")
            return [(0, 0.0, 0.0)]

    @staticmethod
    def _set_gpu_env_for_attempt_static(
        gpu_id: Optional[int],
        attempt_num: int,
        total_attempts: int,
        free_gb: float
    ):
        """Set CUDA_VISIBLE_DEVICES and order for a specific GPU attempt."""
        import os
        import sys
        
        if gpu_id is None:
            return

        # 1. PCI_BUS_ID ensures index 4 is physically card 4 from nvidia-smi
        os.environ["CUDA_DEVICE_ORDER"] = "PCI_BUS_ID"
        
        # 2. Set the mask for this process
        gpu_str = str(gpu_id)
        os.environ["CUDA_VISIBLE_DEVICES"] = gpu_str
        
        # 3. FORCE the environment variable into the actual C-level environment
        # This is critical for vLLM V1 because it uses the 'spawn' start method
        # for subprocesses, which often ignores standard os.environ updates.
        os.putenv("CUDA_VISIBLE_DEVICES", gpu_str)
        
        print(
            f"[GPU Attempt {attempt_num}/{total_attempts}] 🚀 Selected Physical GPU {gpu_id} "
            f"({free_gb:.2f} GB free). Remapping to logical cuda:0",
            file=sys.stdout,
            flush=True
        )
    
    def _initialize(
        self,
        llm_config: Optional[Dict[str, Any]] = None,
        prompts_config: Optional[Dict[str, Any]] = None,
        llm_v_config: Optional[Dict[str, Any]] = None,
        logging_config: Optional[Dict[str, Any]] = None,
    ):
        """Internal initialization method with specific fixes for Ray worker isolation."""
        import os
        import torch
        from vllm import LLM, SamplingParams

        # Load defaults
        if llm_config is None:
            llm_config = {}

        model_name = llm_config.get("model", "meta-llama/Llama-3.2-3B")
        tensor_parallel_size = llm_config.get("tensor_parallel_size", 1)
        gpu_memory_utilization = llm_config.get("gpu_memory_utilization", 0.9)
        max_model_len = llm_config.get("max_model_len", 4096)
        
        # Verify CUDA is seeing the masked device
        if not torch.cuda.is_available():
            raise RuntimeError("Torch reports CUDA is not available after masking.")

        # ============================================================================
        # CRITICAL: vLLM Parameter Tuning for Shared Machines
        # ============================================================================
        vllm_params = {
            "model": model_name,
            "tensor_parallel_size": tensor_parallel_size,
            "gpu_memory_utilization": gpu_memory_utilization,
            "max_model_len": max_model_len,
            "trust_remote_code": True,
            "enforce_eager": True, # Skips CUDA Graph capture to save VRAM and avoid crashes
            "disable_custom_all_reduce": True,
        }

        # FIX: The "Ray Worker Trap"
        # If we are only using 1 GPU, use 'mp' (multiprocessing) instead of 'ray' backend.
        # 'mp' is much more likely to inherit the CUDA_VISIBLE_DEVICES we set above.
        if tensor_parallel_size == 1:
            vllm_params["distributed_executor_backend"] = "mp"
            logger.info("[vLLM] Using 'mp' backend to ensure CUDA_VISIBLE_DEVICES inheritance.")
        else:
            vllm_params["distributed_executor_backend"] = "ray"

        # Initialize the engine
        self.llm = LLM(**vllm_params)

        # Sampling Setup
        self.sampling_params = SamplingParams(
            temperature=llm_config.get("temperature", 0.7),
            max_tokens=llm_config.get("max_tokens", 256),
            top_p=0.95,
        )

        # Initialize vision LLM if config provided
        self.llm_v = None
        self.sampling_params_v = None
        if llm_v_config:
            try:
                logger.info("[vLLM] Initializing vision LLM (llm_v)...")
                v_model_name = llm_v_config.get("model", "meta-llama/Llama-3.2-11B-Vision")
                v_tensor_parallel_size = llm_v_config.get("tensor_parallel_size", 1)
                v_gpu_memory_utilization = llm_v_config.get("gpu_memory_utilization", 0.9)
                v_max_model_len = llm_v_config.get("max_model_len", 4096)
                
                vllm_v_params = {
                    "model": v_model_name,
                    "tensor_parallel_size": v_tensor_parallel_size,
                    "gpu_memory_utilization": v_gpu_memory_utilization,
                    "max_model_len": v_max_model_len,
                    "trust_remote_code": True,
                    "enforce_eager": True,
                    "disable_custom_all_reduce": True,
                }
                
                if v_tensor_parallel_size == 1:
                    vllm_v_params["distributed_executor_backend"] = "mp"
                else:
                    vllm_v_params["distributed_executor_backend"] = "ray"
                
                self.llm_v = LLM(**vllm_v_params)
                
                self.sampling_params_v = SamplingParams(
                    temperature=llm_v_config.get("temperature", 0.5),
                    max_tokens=llm_v_config.get("max_tokens", 256),
                    top_p=0.95,
                )
                logger.info(f"[vLLM] Vision LLM initialized successfully with model: {v_model_name}")
            except Exception as e:
                logger.error(f"[vLLM] Failed to initialize vision LLM: {e}")
                self.llm_v = None
                self.sampling_params_v = None

        # Store prompts and metadata
        self.prompts_config = prompts_config or {}
        self.gpu_selection_info = {
            "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
            "backend": vllm_params.get("distributed_executor_backend")
        }
        
        # Configure logger to write to file if logging_config provided
        self._setup_logger(logging_config)

    def _setup_logger(self, logging_config: Optional[Dict[str, Any]] = None):
        """
        Configure the module-level logger to write to {client_id}_actor.log file.
        
        Args:
            logging_config: Dictionary with:
                - log_dir: Directory for log files (default: "./logs")
                - client_id: Client identifier for log filename (default: "vllm")
                - enable_actor_log: Whether to enable file logging (default: True)
        """
        global logger
        
        if logging_config is None:
            logging_config = {}
        
        # Check if file logging is enabled
        enable_actor_log = logging_config.get("enable_actor_log", True)
        if not enable_actor_log:
            return
        
        # Get configuration
        from pathlib import Path
        log_dir = Path(logging_config.get("log_dir", "./logs"))
        client_id = logging_config.get("client_id", "vllm")
        
        # Create log directory
        log_dir.mkdir(parents=True, exist_ok=True)
        
        # Configure logger
        logger.setLevel(logging.INFO)
        
        # Remove existing handlers to avoid duplicates
        logger.handlers = []
        
        # Create file handler with rotation
        from logging.handlers import RotatingFileHandler
        log_file = log_dir / f"{client_id}_actor.log"
        handler = RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5
        )
        
        # Create JSON formatter matching client.py pattern
        import json
        from datetime import datetime
        
        class JsonFormatter(logging.Formatter):
            def format(self, record: logging.LogRecord) -> str:
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
        
        logger.info(f"[vLLM] Logger configured to write to {log_file}")
    
    def get_gpu_selection_info(self) -> dict:
        """
        Get GPU selection information for logging and diagnostics.

        Returns:
            Dictionary containing GPU selection details:
            - physical_gpu_id: The physical GPU ID selected (if any)
            - logical_gpu_id: The logical GPU ID within the process (usually 0)
            - assignment_method: How the GPU was selected (ray_assigned, dynamic_selection, or default)
            - cuda_visible_devices: Value of CUDA_VISIBLE_DEVICES environment variable
        """
        return self.gpu_selection_info.copy()

    def _log_prompt(
        self, method_name: str, system_msg: str, user_msg: str, agent_attrs: dict = None
    ):
        """
        Log the prompt details for debugging.

        Args:
            method_name: Name of the method generating the prompt
            system_msg: System message content
            user_msg: User message content
            agent_attrs: Optional agent attributes used in prompt generation
        """
        if self.prompt_logger is not None:
            log_data = {
                "method": method_name,
                "system_message": system_msg,
                "user_message": user_msg,
            }
            if agent_attrs:
                log_data["agent_attrs"] = {
                    k: v
                    for k, v in agent_attrs.items()
                    if k
                    in [
                        "name",
                        "topic",
                        "topic_opinion",
                        "topic_opinion_value",
                        "post_topics",
                        "post_opinions",
                        "cluster_id",
                    ]
                }
            self.prompt_logger.debug(f"LLM Prompt - {method_name}", extra={"extra_data": log_data})

    def _build_persona(self, cluster_id: int, agent_attrs: dict = None) -> str:
        """
        Build a persona string for an agent using either attributes or fallback.

        Args:
            cluster_id: Cluster/persona ID for fallback
            agent_attrs: Dict with agent attributes (name, age, gender, nationality,
                        profession, political_leaning, oe, co, ex, ag, ne, toxicity)

        Returns:
            str: Formatted persona string
        """
        # If agent attributes are provided, use the persona template
        if agent_attrs and self.prompts_config.get("persona_template"):
            template = self.prompts_config["persona_template"]
            try:
                # Build persona from template with agent attributes
                persona = template.format(
                    name=agent_attrs.get("name", "Anonymous"),
                    age=agent_attrs.get("age", "unknown"),
                    gender=agent_attrs.get("gender", "person"),
                    nationality=agent_attrs.get("nationality", "citizen"),
                    profession=agent_attrs.get("profession", "individual"),
                    political_leaning=agent_attrs.get("political_leaning", "neutral"),
                    oe=agent_attrs.get("oe", "average in openness"),
                    co=agent_attrs.get("co", "average in conscientiousness"),
                    ex=agent_attrs.get("ex", "average in extraversion"),
                    ag=agent_attrs.get("ag", "average in agreeableness"),
                    ne=agent_attrs.get("ne", "average in neuroticism"),
                )
                return persona
            except KeyError:
                # If template formatting fails, fall back to cluster-based persona
                pass

        # Fallback to cluster-based persona
        return self.prompts_config["personas"].get(str(cluster_id), "You are a social media user.")

    def _format_prompt(self, system_msg: str, user_msg: str) -> str:
        """
        Format system and user messages into a single prompt.

        Args:
            system_msg: System message (context/instructions)
            user_msg: User message (task/query)

        Returns:
            str: Formatted prompt for the model
        """
        return f"System: {system_msg}\n\nUser: {user_msg}\n\nAssistant:"

    def generate_post(self, cluster_id: int, day: int, slot: int, agent_attrs: dict = None) -> str:
        """Generate content based on Persona."""
        try:
            # Build persona using attributes or fallback
            persona = self._build_persona(cluster_id, agent_attrs)

            # Get toxicity level (default to "no" if not provided)
            toxicity = agent_attrs.get("toxicity", "no") if agent_attrs else "no"

            # Get topic if available
            topic = agent_attrs.get("topic") if agent_attrs else None

            # DEBUG: Log if topic is unexpectedly missing
            # Note: null topic is EXPECTED when agent has no interests (per INTERESTS.md)
            if not topic and agent_attrs and "topic" in agent_attrs:
                agent_name = agent_attrs.get("name", "Unknown")
                logger.warning(
                    f"Topic is explicitly None for agent {agent_name} in generate_post. "
                    f"This may indicate the agent has no interests defined or interests are malformed."
                )

            # Get opinion on the topic if available
            topic_opinion = agent_attrs.get("topic_opinion") if agent_attrs else None

            # Get prompt templates from configuration
            system_template = self.prompts_config["generate_post"]["system_template"]
            user_template = self.prompts_config["generate_post"]["user_template"]

            # Format templates
            system_msg = (
                system_template.format(persona=persona, toxicity=toxicity)
                if system_template
                else ""
            )

            # Build topic instruction with opinion if available
            if topic and topic_opinion:
                topic_instruction = f" You MUST write about the topic: {topic}. Your stance is: {topic_opinion}. Express this viewpoint clearly."
            elif topic:
                topic_instruction = f" You MUST write about the topic: {topic}."
            else:
                topic_instruction = ""

            # Format user message with all placeholders
            user_msg = user_template.format(
                persona=persona,
                toxicity=toxicity,
                day=day,
                slot=slot,
                topic_instruction=topic_instruction,
            )

            # Log the prompt for debugging
            self._log_prompt("generate_post", system_msg, user_msg, agent_attrs)

            # Create formatted prompt
            prompt = self._format_prompt(system_msg, user_msg)

            # Generate using vLLM
            logger.debug(
                f"[vLLM] Generating post for cluster_id={cluster_id}, day={day}, slot={slot}"
            )
            outputs = self.llm.generate([prompt], self.sampling_params)
            result = outputs[0].outputs[0].text.strip()
            logger.debug(f"[vLLM] Generated post successfully (length={len(result)})")
            return result
        except KeyError as e:
            logger.error(f"[vLLM] Missing configuration key in generate_post: {e}")
            logger.error(f"[vLLM] cluster_id={cluster_id}, day={day}, slot={slot}")
            raise
        except Exception as e:
            logger.error(f"[vLLM] Failed to generate post: {e}")
            logger.error(f"[vLLM] cluster_id={cluster_id}, day={day}, slot={slot}")
            raise RuntimeError(f"vLLM post generation failed: {e}") from e

    def generate_post_batch(self, requests: List[Dict[str, Any]]) -> List[str]:
        """
        Generate multiple posts in a single batch for improved performance.

        Args:
            requests: List of request dicts, each with keys:
                - cluster_id: Agent cluster ID
                - day: Day number
                - slot: Slot number
                - agent_attrs: Agent attributes dict (optional)
                - article: Article dict for news posts (optional) with keys:
                    - id: Article ID
                    - title: Article title
                    - summary: Article summary/description

        Returns:
            List of generated post strings in the same order as requests
        """
        try:
            logger.debug(f"[vLLM] Starting batch post generation for {len(requests)} requests")
            prompts = []
            for idx, req in enumerate(requests):
                try:
                    cluster_id = req.get("cluster_id")
                    if cluster_id is None:
                        logger.error(f"[vLLM] Missing cluster_id in request {idx}: {req}")
                        raise ValueError(f"Missing cluster_id in request {idx}")
                    day = req.get("day")
                    if day is None:
                        logger.error(f"[vLLM] Missing day in request {idx}: {req}")
                        raise ValueError(f"Missing day in request {idx}")
                    slot = req.get("slot")
                    if slot is None:
                        logger.error(f"[vLLM] Missing slot in request {idx}: {req}")
                        raise ValueError(f"Missing slot in request {idx}")
                    agent_attrs = req.get("agent_attrs")
                    article = req.get("article")  # Article content for news posts
                    
                    # FALLBACK: If article is None but we have a topic that looks like article_id, try to fetch
                    if not article and agent_attrs and self.server and self.client_id:
                        topic = agent_attrs.get("topic")
                        if topic:
                            try:
                                import uuid
                                uuid.UUID(topic)  # Validate it's a UUID (article_id)
                                logger.info(f"[vLLM Batch {idx}] Article is None but topic looks like UUID - attempting fallback fetch for {topic}")
                                article_data = ray.get(self.server.get_article.remote(topic, client_id=self.client_id))
                                if article_data:
                                    article = {
                                        "id": topic,
                                        "title": article_data.get("title", ""),
                                        "summary": article_data.get("summary", article_data.get("description", ""))
                                    }
                                    logger.info(f"[vLLM Batch {idx}] ✅ Fallback fetch successful: '{article['title'][:50]}...'")
                                else:
                                    logger.warning(f"[vLLM Batch {idx}] ❌ Fallback fetch returned None for article_id {topic}")
                            except ValueError:
                                # Not a UUID - regular topic
                                logger.debug(f"[vLLM Batch {idx}] Topic '{topic}' is not UUID - skipping fallback fetch")
                            except Exception as e:
                                logger.warning(f"[vLLM Batch {idx}] ❌ Fallback fetch failed: {type(e).__name__}: {e}")
                    
                    # DETAILED DIAGNOSTIC LOGGING - Improved for robustness
                    logger.info(f"[vLLM Batch {idx}] article type: {type(article).__name__}")
                    logger.info(f"[vLLM Batch {idx}] article is None: {article is None}")
                    logger.info(f"[vLLM Batch {idx}] article is dict: {isinstance(article, dict)}")
                    
                    if article and isinstance(article, dict):
                        logger.info(f"[vLLM Batch {idx}] article keys: {list(article.keys())}")
                        article_title_value = article.get('title')
                        logger.info(f"[vLLM Batch {idx}] article title: '{article_title_value}'")
                        logger.info(f"[vLLM Batch {idx}] title bool: {bool(article_title_value)}")
                        logger.info(f"[vLLM Batch {idx}] has_summary: {bool(article.get('summary'))}")
                    else:
                        logger.info(f"[vLLM Batch {idx}] No article content or not dict - generating regular post")

                    # Check if this is a news post (page sharing article)
                    if article and article.get("title"):
                        # Use news commentary generation for article posts
                        article_title = article.get("title", "News Article")
                        article_text = article.get("summary", "")
                        
                        logger.info(f"[vLLM Batch {idx}] ✅ USING NEWS COMMENTARY PATH for: '{article_title[:50]}...'")
                        
                        if len(article_text) > 500:
                            article_text = article_text[:500] + "..."
                        
                        # Get news commentary prompt templates
                        news_commentary_config = self.prompts_config.get("generate_news_commentary", {})
                        system_template = news_commentary_config.get(
                            "system_template",
                            "You are a social media content creator for {website_name}. Create engaging posts about news articles."
                        )
                        user_template = news_commentary_config.get(
                            "user_template",
                            'Article: "{article_title}"\n\nSummary: {article_text}\n\nWrite a brief engaging social media post about this article (max 280 characters).'
                        )
                        
                        # Safely format templates - only replace placeholders that exist
                        try:
                            system_msg = system_template.format(website_name="this website")
                        except KeyError:
                            # Template doesn't have {website_name} placeholder
                            system_msg = system_template
                        
                        user_msg = user_template.format(
                            website_name="this website",
                            article_title=article_title,
                            article_text=article_text
                        )
                        
                        logger.info(f"[vLLM Batch {idx}] News commentary prompt: user_msg='{user_msg[:100]}...'")
                        prompt = self._format_prompt(system_msg, user_msg)
                        prompts.append(prompt)
                    else:
                        # Regular post generation
                        logger.info(f"[vLLM Batch {idx}] ❌ USING REGULAR POST PATH (no article or no title)")
                        
                        # Build persona
                        persona = self._build_persona(cluster_id, agent_attrs)
                        toxicity = agent_attrs.get("toxicity", "no") if agent_attrs else "no"
                        topic = agent_attrs.get("topic") if agent_attrs else None
                        topic_opinion = agent_attrs.get("topic_opinion") if agent_attrs else None
                        
                        logger.debug(f"[vLLM Batch {idx}] Regular post - persona: {persona[:50]}..., topic: {topic}")

                        # Get prompt templates
                        system_template = self.prompts_config["generate_post"]["system_template"]
                        user_template = self.prompts_config["generate_post"]["user_template"]

                        # Format templates
                        system_msg = (
                            system_template.format(persona=persona, toxicity=toxicity)
                            if system_template
                            else ""
                        )

                        # Build topic instruction
                        if topic and topic_opinion:
                            topic_instruction = f" You MUST write about the topic: {topic}. Your stance is: {topic_opinion}. Express this viewpoint clearly."
                        elif topic:
                            topic_instruction = f" You MUST write about the topic: {topic}."
                        else:
                            topic_instruction = ""

                        user_msg = user_template.format(
                            persona=persona,
                            toxicity=toxicity,
                            day=day,
                            slot=slot,
                            topic_instruction=topic_instruction,
                        )

                        # Create formatted prompt
                        prompt = self._format_prompt(system_msg, user_msg)
                        prompts.append(prompt)
                except Exception as e:
                    logger.error(f"[vLLM] Failed to build prompt for batch request {idx}: {e}")
                    logger.error(f"[vLLM] Request: {req}")
                    raise

            # Batch generate using vLLM
            logger.debug(f"[vLLM] Executing batch inference for {len(prompts)} prompts")
            outputs = self.llm.generate(prompts, self.sampling_params)
            results = [output.outputs[0].text.strip() for output in outputs]
            logger.debug(f"[vLLM] Batch generation completed successfully ({len(results)} results)")
            return results
        except Exception as e:
            logger.error(f"[vLLM] Batch post generation failed: {e}")
            logger.error(f"[vLLM] Number of requests: {len(requests)}")
            raise RuntimeError(f"vLLM batch post generation failed: {e}") from e

    def decide_reaction(self, cluster_id: int, post_content: str) -> str:
        """Decide: LIKE, COMMENT, or IGNORE."""
        try:
            # Build persona from cluster_id
            persona = self._build_persona(cluster_id, None)

            # Get prompt templates from configuration
            system_template = self.prompts_config["decide_reaction"]["system_template"]
            user_template = self.prompts_config["decide_reaction"]["user_template"]

            # Format templates
            system_msg = (
                system_template.format(cluster_id=cluster_id, persona=persona)
                if system_template
                else ""
            )
            user_msg = user_template.format(
                cluster_id=cluster_id, persona=persona, post_content=post_content
            )

            # Create formatted prompt
            prompt = self._format_prompt(system_msg, user_msg)

            # Generate using vLLM
            logger.debug(f"[vLLM] Deciding reaction for cluster_id={cluster_id}")
            outputs = self.llm.generate([prompt], self.sampling_params)
            result = outputs[0].outputs[0].text.strip().upper()

            if "LIKE" in result:
                return "LIKE"
            if "COMMENT" in result:
                return "COMMENT"
            return "IGNORE"
        except KeyError as e:
            logger.error(f"[vLLM] Missing configuration key in decide_reaction: {e}")
            logger.error(f"[vLLM] cluster_id={cluster_id}")
            raise
        except Exception as e:
            logger.error(f"[vLLM] Failed to decide reaction: {e}")
            logger.error(
                f"[vLLM] cluster_id={cluster_id}, post_content_len={len(post_content) if post_content else 0}"
            )
            # Return default fallback to maintain YClient pattern
            logger.warning(f"[vLLM] Returning fallback reaction: IGNORE")
            return "IGNORE"

    def decide_reaction_batch(self, requests: List[Dict[str, Any]]) -> List[str]:
        """
        Decide reactions for multiple posts in a single batch for improved performance.

        Args:
            requests: List of request dicts, each with keys:
                - cluster_id: Agent cluster ID
                - post_content: Content of the post to react to

        Returns:
            List of reaction strings (LIKE, COMMENT, IGNORE) in the same order as requests
        """
        try:
            logger.debug(f"[vLLM] Starting batch reaction decision for {len(requests)} requests")
            prompts = []
            for idx, req in enumerate(requests):
                try:
                    cluster_id = req.get("cluster_id")
                    if cluster_id is None:
                        logger.error(f"[vLLM] Missing cluster_id in request {idx}: {req}")
                        raise ValueError(f"Missing cluster_id in request {idx}")
                    post_content = req.get("post_content", "")

                    # Build persona (no agent_attrs in basic batch)
                    persona = self._build_persona(cluster_id, None)

                    # Get prompt templates
                    system_template = self.prompts_config["decide_reaction"]["system_template"]
                    user_template = self.prompts_config["decide_reaction"]["user_template"]

                    # Format templates
                    system_msg = (
                        system_template.format(cluster_id=cluster_id, persona=persona)
                        if system_template
                        else ""
                    )
                    user_msg = user_template.format(
                        cluster_id=cluster_id, persona=persona, post_content=post_content
                    )

                    # Create formatted prompt
                    prompt = self._format_prompt(system_msg, user_msg)
                    prompts.append(prompt)
                except Exception as e:
                    logger.error(
                        f"[vLLM] Failed to build prompt for batch reaction request {idx}: {e}"
                    )
                    logger.error(f"[vLLM] Request: {req}")
                    raise

            # Batch generate using vLLM
            logger.debug(f"[vLLM] Executing batch inference for {len(prompts)} reaction prompts")
            outputs = self.llm.generate(prompts, self.sampling_params)
            results = []
            for output in outputs:
                result = output.outputs[0].text.strip().upper()
                if "LIKE" in result:
                    results.append("LIKE")
                elif "COMMENT" in result:
                    results.append("COMMENT")
                else:
                    results.append("IGNORE")
            logger.debug(
                f"[vLLM] Batch reaction decision completed successfully ({len(results)} results)"
            )
            return results
        except Exception as e:
            logger.error(f"[vLLM] Batch reaction decision failed: {e}")
            logger.error(f"[vLLM] Number of requests: {len(requests)}")
            raise RuntimeError(f"vLLM batch reaction decision failed: {e}") from e

    def generate_read_reaction_batch(self, requests: List[Dict[str, Any]]) -> List[str]:
        """
        Decide read reactions for multiple posts in a single batch with agent attributes support.

        Similar to decide_reaction_batch but supports agent_attrs including opinions.

        Args:
            requests: List of request dicts, each with keys:
                - cluster_id: Agent cluster ID
                - post_content: Content of the post to react to
                - agent_attrs: Optional dict with agent attributes (opinions, etc.)

        Returns:
            List of reaction strings (LIKE, COMMENT, IGNORE, etc.) in the same order as requests
        """
        try:
            logger.debug(
                f"[vLLM] Starting batch read reaction decision for {len(requests)} requests"
            )
            prompts = []
            for idx, req in enumerate(requests):
                try:
                    cluster_id = req.get("cluster_id")
                    if cluster_id is None:
                        logger.error(f"[vLLM] Missing cluster_id in request {idx}: {req}")
                        raise ValueError(f"Missing cluster_id in request {idx}")
                    post_content = req.get("post_content", "")
                    agent_attrs = req.get("agent_attrs")

                    # Build persona using attributes or fallback
                    persona = self._build_persona(cluster_id, agent_attrs)

                    # Build opinion instruction if available
                    opinion_instruction = ""
                    if agent_attrs and "post_topics" in agent_attrs and agent_attrs["post_topics"]:
                        topics = agent_attrs["post_topics"]
                        opinions = agent_attrs.get("post_opinions", {})

                        if topics and opinions:
                            opinion_parts = []
                            for topic in topics:
                                if topic in opinions:
                                    opinion_parts.append(f"{topic}: {opinions[topic]}")

                            if opinion_parts:
                                opinion_str = ", ".join(opinion_parts)
                                opinion_instruction = f" Your opinions on the discussed topics: {opinion_str}. React accordingly."

                    # Get prompt templates (use decide_reaction templates as base)
                    system_template = self.prompts_config["decide_reaction"]["system_template"]
                    user_template = self.prompts_config["decide_reaction"]["user_template"]

                    # Format templates with persona and opinion instruction
                    system_msg = (
                        system_template.format(cluster_id=cluster_id, persona=persona)
                        if system_template
                        else ""
                    )
                    user_msg = (
                        user_template.format(
                            cluster_id=cluster_id, persona=persona, post_content=post_content
                        )
                        + opinion_instruction
                    )

                    # Create formatted prompt
                    prompt = self._format_prompt(system_msg, user_msg)
                    prompts.append(prompt)
                except Exception as e:
                    logger.error(
                        f"[vLLM] Failed to build prompt for batch read reaction request {idx}: {e}"
                    )
                    logger.error(f"[vLLM] Request: {req}")
                    raise

            # Batch generate using vLLM
            logger.debug(
                f"[vLLM] Executing batch inference for {len(prompts)} read reaction prompts"
            )
            outputs = self.llm.generate(prompts, self.sampling_params)
            results = []
            for output in outputs:
                result = output.outputs[0].text.strip().upper()
                # Parse reaction type from result
                if "LIKE" in result:
                    results.append("LIKE")
                elif "LOVE" in result:
                    results.append("LOVE")
                elif "LAUGH" in result:
                    results.append("LAUGH")
                elif "ANGRY" in result:
                    results.append("ANGRY")
                elif "SAD" in result:
                    results.append("SAD")
                elif "COMMENT" in result:
                    results.append("COMMENT")
                elif "SHARE" in result:
                    results.append("SHARE")
                else:
                    results.append("IGNORE")
            logger.debug(
                f"[vLLM] Batch read reaction decision completed successfully ({len(results)} results)"
            )
            return results
        except Exception as e:
            logger.error(f"[vLLM] Batch read reaction decision failed: {e}")
            logger.error(f"[vLLM] Number of requests: {len(requests)}")
            raise RuntimeError(f"vLLM batch read reaction decision failed: {e}") from e

    def generate_comment(
        self,
        cluster_id: int,
        post_content: str,
        agent_attrs: dict = None,
        author_name: str = "Someone",
        thread_context: list = None,
    ) -> str:
        """
        Generate a comment on a post to continue the discussion.

        Args:
            cluster_id: Cluster/persona ID of the agent
            post_content: Content of the post to comment on
            agent_attrs: Dict with agent attributes for dynamic persona building
            author_name: Username of the post author
            thread_context: List of dicts with thread context (preceding posts/comments)

        Returns:
            str: Generated comment text
        """
        # Build persona using attributes or fallback
        persona = self._build_persona(cluster_id, agent_attrs)

        # Get toxicity level (default to "no" if not provided)
        toxicity = agent_attrs.get("toxicity", "no") if agent_attrs else "no"

        # Get opinions on the post's topics if available
        opinion_instruction = ""
        if agent_attrs and "post_topics" in agent_attrs and agent_attrs["post_topics"]:
            topics = agent_attrs["post_topics"]
            opinions = agent_attrs.get("post_opinions", {})

            if topics and opinions:
                opinion_parts = []
                for topic in topics:
                    if topic in opinions:
                        opinion_parts.append(f"{topic}: {opinions[topic]}")

                if opinion_parts:
                    opinion_str = ", ".join(opinion_parts)
                    opinion_instruction = f" Your opinions on the discussed topics: {opinion_str}. Express your viewpoint accordingly."

        # Get prompt templates from configuration
        system_template = self.prompts_config["generate_comment"]["system_template"]
        user_template = self.prompts_config["generate_comment"]["user_template"]

        # Format thread context if provided
        thread_context_str = ""
        thread_context_instruction = ""
        if thread_context and len(thread_context) > 0:
            thread_context_lines = []
            for ctx in thread_context:
                username = ctx.get("username", "Someone")
                tweet = ctx.get("tweet", "")
                thread_context_lines.append(f"{username}: {tweet}")
            thread_context_str = "\n".join(thread_context_lines)
            thread_context_instruction = (
                f"Previous discussion in this thread (for context only):\n{thread_context_str}\n\n"
                f"Now respond specifically to {author_name}'s post above. "
            )

        # Format templates
        system_msg = (
            system_template.format(persona=persona, toxicity=toxicity) if system_template else ""
        )
        user_msg = user_template.format(
            persona=persona,
            toxicity=toxicity,
            author_name=author_name,
            post_content=post_content,
            thread_context_instruction=thread_context_instruction,
        )

        # Add opinion instruction if available
        if opinion_instruction:
            user_msg += opinion_instruction

        # Log the prompt for debugging
        self._log_prompt("generate_comment", system_msg, user_msg, agent_attrs)

        # Create formatted prompt
        prompt = self._format_prompt(system_msg, user_msg)

        try:
            # Generate using vLLM
            logger.debug(
                f"[vLLM] Generating comment for cluster_id={cluster_id}, author={author_name}"
            )
            outputs = self.llm.generate([prompt], self.sampling_params)
            comment = outputs[0].outputs[0].text.strip()

            # Ensure comment doesn't exceed length
            if len(comment) > 280:
                comment = comment[:277] + "..."

            logger.debug(f"[vLLM] Generated comment successfully (length={len(comment)})")
            return comment
        except Exception as e:
            # Fallback if LLM fails
            logger.error(f"[vLLM] Failed to generate comment: {e}")
            logger.error(
                f"[vLLM] cluster_id={cluster_id}, author={author_name}, post_content_len={len(post_content) if post_content else 0}"
            )
            logger.warning("[vLLM] Returning fallback comment")
            return "Interesting perspective!"

    def generate_comment_batch(self, requests: List[Dict[str, Any]]) -> List[str]:
        """
        Generate multiple comments in a single batch for improved performance.

        Args:
            requests: List of request dicts, each with keys:
                - cluster_id: Agent cluster ID
                - post_content: Content of the post to comment on
                - agent_attrs: Agent attributes dict (optional)
                - author_name: Username of the post author (optional, default: "Someone")
                - thread_context: List of thread context (optional)

        Returns:
            List of generated comment strings in the same order as requests
        """
        try:
            logger.debug(f"[vLLM] Starting batch comment generation for {len(requests)} requests")
            prompts = []
            for idx, req in enumerate(requests):
                try:
                    cluster_id = req.get("cluster_id")
                    if cluster_id is None:
                        logger.error(f"[vLLM] Missing cluster_id in request {idx}: {req}")
                        raise ValueError(f"Missing cluster_id in request {idx}")
                    post_content = req.get("post_content", "")
                    agent_attrs = req.get("agent_attrs")
                    author_name = req.get("author_name", "Someone")
                    thread_context = req.get("thread_context")

                    # Build persona
                    persona = self._build_persona(cluster_id, agent_attrs)
                    toxicity = agent_attrs.get("toxicity", "no") if agent_attrs else "no"

                    # Get opinions on the post's topics if available
                    opinion_instruction = ""
                    if agent_attrs and "post_topics" in agent_attrs and agent_attrs["post_topics"]:
                        topics = agent_attrs["post_topics"]
                        opinions = agent_attrs.get("post_opinions", {})

                        if topics and opinions:
                            opinion_parts = []
                            for topic in topics:
                                if topic in opinions:
                                    opinion_parts.append(f"{topic}: {opinions[topic]}")

                            if opinion_parts:
                                opinion_str = ", ".join(opinion_parts)
                                opinion_instruction = f" Your opinions on the discussed topics: {opinion_str}. Express your viewpoint accordingly."

                    # Get prompt templates
                    system_template = self.prompts_config["generate_comment"]["system_template"]
                    user_template = self.prompts_config["generate_comment"]["user_template"]

                    # Format thread context if provided
                    thread_context_str = ""
                    thread_context_instruction = ""
                    if thread_context and len(thread_context) > 0:
                        thread_context_lines = []
                        for ctx in thread_context:
                            username = ctx.get("username", "Someone")
                            tweet = ctx.get("tweet", "")
                            thread_context_lines.append(f"{username}: {tweet}")
                        thread_context_str = "\n".join(thread_context_lines)
                        thread_context_instruction = (
                            f"Previous discussion in this thread (for context only):\n{thread_context_str}\n\n"
                            f"Now respond specifically to {author_name}'s post above. "
                        )

                    # Format templates
                    system_msg = (
                        system_template.format(persona=persona, toxicity=toxicity)
                        if system_template
                        else ""
                    )
                    user_msg = user_template.format(
                        persona=persona,
                        toxicity=toxicity,
                        author_name=author_name,
                        post_content=post_content,
                        thread_context_instruction=thread_context_instruction,
                    )

                    # Add opinion instruction if available
                    if opinion_instruction:
                        user_msg += opinion_instruction

                    # Create formatted prompt
                    prompt = self._format_prompt(system_msg, user_msg)
                    prompts.append(prompt)
                except Exception as e:
                    logger.error(
                        f"[vLLM] Failed to build prompt for batch comment request {idx}: {e}"
                    )
                    logger.error(f"[vLLM] Request: {req}")
                    raise

            # Batch generate using vLLM
            logger.debug(f"[vLLM] Executing batch inference for {len(prompts)} comment prompts")
            outputs = self.llm.generate(prompts, self.sampling_params)
            results = []
            for output in outputs:
                comment = output.outputs[0].text.strip()
                # Ensure comment doesn't exceed length
                if len(comment) > 280:
                    comment = comment[:277] + "..."
                results.append(comment)
            logger.debug(
                f"[vLLM] Batch comment generation completed successfully ({len(results)} results)"
            )
            return results
        except Exception as e:
            logger.error(f"[vLLM] Batch comment generation failed: {e}")
            logger.error(f"[vLLM] Number of requests: {len(requests)}")
            raise RuntimeError(f"vLLM batch comment generation failed: {e}") from e

    # Add placeholder methods for compatibility with LLMService interface
    # These methods maintain the same signature but may need full implementation
    # based on usage patterns in the codebase

    def generate_news_commentary(self, article: dict, website_name: str = None) -> str:
        """Generate engaging social media commentary for a news article."""
        try:
            article_title = article.get("title", "News Article")
            article_text = article.get("summary", article.get("description", ""))

            if len(article_text) > 500:
                article_text = article_text[:500] + "..."

            if not website_name:
                website_name = "this website"

            # Get prompt templates with fallback defaults
            news_commentary_config = self.prompts_config.get("generate_news_commentary", {})
            system_template = news_commentary_config.get(
                "system_template",
                "You are a social media content creator for {website_name}. Create engaging posts about news articles."
            )
            user_template = news_commentary_config.get(
                "user_template",
                'Article: "{article_title}"\n\nSummary: {article_text}\n\nWrite a brief engaging social media post about this article (max 280 characters).'
            )

            # Safe template formatting - handle missing placeholders
            try:
                system_msg = system_template.format(website_name=website_name)
            except KeyError:
                # Template doesn't have {website_name} placeholder, use as-is
                logger.debug("[vLLM] system_template doesn't have {website_name} placeholder")
                system_msg = system_template
            
            try:
                user_msg = user_template.format(
                    website_name=website_name,
                    article_title=article_title,
                    article_text=article_text
                )
            except KeyError:
                # Template doesn't have expected placeholders, use as-is or try minimal formatting
                logger.debug("[vLLM] user_template doesn't have expected placeholders")
                user_msg = user_template

            prompt = self._format_prompt(system_msg, user_msg)

            logger.debug(f"[vLLM] Generating news commentary for article: {article_title[:50]}...")
            outputs = self.llm.generate([prompt], self.sampling_params)
            commentary = outputs[0].outputs[0].text.strip()

            if len(commentary) > 280:
                commentary = commentary[:277] + "..."

            logger.debug(
                f"[vLLM] Generated news commentary successfully (length={len(commentary)})"
            )
            return commentary
        except KeyError as e:
            logger.error(f"[vLLM] Missing configuration key in generate_news_commentary: {e}")
            title = article_title if len(article_title) <= 97 else article_title[:97] + "..."
            return f"Check out this article: {title}"
        except Exception as e:
            logger.error(f"[vLLM] Failed to generate news commentary: {e}")
            logger.error(f"[vLLM] Article title: {article.get('title', 'Unknown')[:50]}")
            logger.warning("[vLLM] Returning fallback commentary")
            title = article_title if len(article_title) <= 97 else article_title[:97] + "..."
            return f"Check out this article: {title}"

    def generate_share_commentary(
        self,
        cluster_id: int,
        post_content: str,
        agent_attrs: dict = None,
        author_name: str = "Someone",
    ) -> str:
        """Generate commentary for sharing/resharing a post."""
        persona = self._build_persona(cluster_id, agent_attrs)
        toxicity = agent_attrs.get("toxicity", "no") if agent_attrs else "no"

        opinion_instruction = ""
        if agent_attrs and "post_topics" in agent_attrs and agent_attrs["post_topics"]:
            topics = agent_attrs["post_topics"]
            opinions = agent_attrs.get("post_opinions", {})

            if topics and opinions:
                opinion_parts = []
                for topic in topics:
                    if topic in opinions:
                        opinion_parts.append(f"{topic}: {opinions[topic]}")

                if opinion_parts:
                    opinion_str = ", ".join(opinion_parts)
                    opinion_instruction = f" Your opinions on the discussed topics: {opinion_str}. Reflect your viewpoint in your commentary."

        if "generate_share_commentary" not in self.prompts_config:
            logger.warning("generate_share_commentary prompt not found in config, using fallback")
            return "Sharing this!"

        system_template = self.prompts_config["generate_share_commentary"]["system_template"]
        user_template = self.prompts_config["generate_share_commentary"]["user_template"]

        system_msg = (
            system_template.format(persona=persona, toxicity=toxicity) if system_template else ""
        )
        user_msg = user_template.format(
            persona=persona, toxicity=toxicity, author_name=author_name, post_content=post_content
        )

        if opinion_instruction:
            user_msg += opinion_instruction

        prompt = self._format_prompt(system_msg, user_msg)

        try:
            outputs = self.llm.generate([prompt], self.sampling_params)
            commentary = outputs[0].outputs[0].text.strip()

            if len(commentary) > 200:
                commentary = commentary[:197] + "..."

            return commentary
        except Exception:
            return "Sharing this!"

    def generate_read_reaction(
        self, cluster_id: int, post_content: str, agent_attrs: dict = None
    ) -> str:
        """Decide how to react to a post discovered via read/recommendation."""
        persona = self._build_persona(cluster_id, agent_attrs)

        opinion_instruction = ""
        if agent_attrs and "post_topics" in agent_attrs and agent_attrs["post_topics"]:
            topics = agent_attrs["post_topics"]
            opinions = agent_attrs.get("post_opinions", {})

            if topics and opinions:
                opinion_parts = []
                for topic in topics:
                    if topic in opinions:
                        opinion_parts.append(f"{topic}: {opinions[topic]}")

                if opinion_parts:
                    opinion_str = ", ".join(opinion_parts)
                    opinion_instruction = (
                        f" Your opinions on the discussed topics: {opinion_str}. React accordingly."
                    )

        system_template = self.prompts_config["generate_read_reaction"]["system_template"]
        user_template = self.prompts_config["generate_read_reaction"]["user_template"]

        system_msg = system_template.format(persona=persona)
        user_msg = user_template.format(post_content=post_content)

        if opinion_instruction:
            user_msg += opinion_instruction

        prompt = self._format_prompt(system_msg, user_msg)

        try:
            outputs = self.llm.generate([prompt], self.sampling_params)
            result = outputs[0].outputs[0].text.strip().upper()

            if "LOVE" in result:
                return "LOVE"
            if "LIKE" in result:
                return "LIKE"
            if "LAUGH" in result:
                return "LAUGH"
            if "ANGRY" in result or "DISLIKE" in result:
                return "ANGRY"
            if "SAD" in result:
                return "SAD"
            if "IGNORE" in result:
                return "IGNORE"

            return "LIKE"  # Default fallback
        except Exception:
            return "LIKE"

    def generate_follow_decision(self, cluster_id: int, candidate_users: list) -> str:
        """Decide whether to follow one of the suggested users."""
        if not candidate_users:
            return None

        follow_config = self.prompts_config.get("generate_follow_decision", {})
        follow_probability = follow_config.get("follow_probability", 0.7)

        import random

        if random.random() < follow_probability:
            return random.choice(candidate_users)
        else:
            return None

    def decide_search_action(
        self, cluster_id: int, post_content: str, agent_attrs: dict = None
    ) -> str:
        """Decide which action to perform on a searched post."""
        persona = self._build_persona(cluster_id, agent_attrs)

        opinion_instruction = ""
        if agent_attrs and "post_topics" in agent_attrs and agent_attrs["post_topics"]:
            topics = agent_attrs["post_topics"]
            opinions = agent_attrs.get("post_opinions", {})

            if topics and opinions:
                opinion_parts = []
                for topic in topics:
                    if topic in opinions:
                        opinion_parts.append(f"{topic}: {opinions[topic]}")

                if opinion_parts:
                    opinion_str = ", ".join(opinion_parts)
                    opinion_instruction = f" Your opinions on the discussed topics: {opinion_str}. Consider your viewpoint when deciding how to engage."

        search_action_config = self.prompts_config.get("decide_search_action", {})
        system_template = search_action_config.get("system_template")
        user_template = search_action_config.get("user_template")

        if system_template is None or user_template is None:
            logger.warning(
                "decide_search_action prompts not configured in llm_prompts.json, using default fallback"
            )
            return "LIKE"

        system_msg = system_template.format(persona=persona)
        user_msg = user_template.format(post_content=post_content)

        if opinion_instruction:
            user_msg += opinion_instruction

        prompt = self._format_prompt(system_msg, user_msg)

        try:
            outputs = self.llm.generate([prompt], self.sampling_params)
            result = outputs[0].outputs[0].text.strip().upper()

            if "COMMENT" in result:
                return "COMMENT"
            if "SHARE" in result:
                return "SHARE"
            if "LOVE" in result:
                return "LOVE"
            if "LIKE" in result:
                return "LIKE"
            if "LAUGH" in result:
                return "LAUGH"
            if "ANGRY" in result:
                return "ANGRY"
            if "SAD" in result:
                return "SAD"
            if "IGNORE" in result:
                return "IGNORE"

            return "LIKE"
        except Exception:
            return "LIKE"

    def generate_secondary_follow_decision(
        self, cluster_id: int, post_content: str, is_currently_following: bool
    ) -> str:
        """Decide whether to follow or unfollow a post author based on interaction."""
        follow_config = self.prompts_config.get("generate_secondary_follow_decision", {})
        follow_prob = follow_config.get("follow_probability_when_not_following", 0.3)
        unfollow_prob = follow_config.get("unfollow_probability_when_following", 0.1)

        import random

        if not is_currently_following:
            if random.random() < follow_prob:
                return "follow"
        else:
            if random.random() < unfollow_prob:
                return "unfollow"

        return "no_change"

    def extract_topics_from_article(self, article_title: str, article_summary: str) -> list:
        """Extract up to 2 topics from an article using LLM."""
        article_text = (
            f"Title: {article_title}\n\nSummary: {article_summary}"
            if article_summary
            else f"Title: {article_title}"
        )

        system_template = self.prompts_config["extract_article_topics"]["system_template"]
        user_template = self.prompts_config["extract_article_topics"]["user_template"]

        prompt = self._format_prompt(system_template, user_template)
        prompt = prompt.replace("{article_text}", article_text)

        try:
            outputs = self.llm.generate([prompt], self.sampling_params)
            response = outputs[0].outputs[0].text.strip()

            topics = [t.strip() for t in response.split(",") if t.strip()]

            single_word_topics = []
            for topic in topics:
                words = topic.split()
                if words:
                    single_word = words[0].lower()
                    single_word = "".join(
                        char for char in single_word if char.isalnum() or char == "-" or char == "_"
                    )
                    if single_word:
                        single_word_topics.append(single_word)

            return single_word_topics[:2]
        except Exception:
            return []

    def extract_topics_from_article_batch(self, articles: List[Dict[str, str]]) -> List[list]:
        """
        Extract topics from multiple articles in a single batch for improved performance.

        Args:
            articles: List of dicts with keys 'title' and 'summary'

        Returns:
            List of topic lists (up to 2 topics per article) in same order as inputs
        """
        try:
            logger.debug(
                f"[vLLM] Starting batch article topic extraction for {len(articles)} articles"
            )

            system_template = self.prompts_config["extract_article_topics"]["system_template"]
            user_template = self.prompts_config["extract_article_topics"]["user_template"]

            # Build prompts for all articles
            prompts = []
            for article in articles:
                article_text = (
                    f"Title: {article['title']}\n\nSummary: {article['summary']}"
                    if article.get("summary")
                    else f"Title: {article['title']}"
                )
                prompt = self._format_prompt(system_template, user_template)
                prompt = prompt.replace("{article_text}", article_text)
                prompts.append(prompt)

            # Batch generate using vLLM
            logger.debug(
                f"[vLLM] Executing batch inference for {len(prompts)} article topic extractions"
            )
            outputs = self.llm.generate(prompts, self.sampling_params)

            # Parse results
            results = []
            for output in outputs:
                response = output.outputs[0].text.strip()
                topics = [t.strip() for t in response.split(",") if t.strip()]

                single_word_topics = []
                for topic in topics:
                    words = topic.split()
                    if words:
                        single_word = words[0].lower()
                        single_word = "".join(
                            char
                            for char in single_word
                            if char.isalnum() or char == "-" or char == "_"
                        )
                        if single_word:
                            single_word_topics.append(single_word)

                results.append(single_word_topics[:2])

            logger.debug(
                f"[vLLM] Batch article topic extraction completed successfully ({len(results)} results)"
            )
            return results
        except Exception as e:
            logger.error(f"[vLLM] Batch article topic extraction failed: {e}")
            logger.error(f"[vLLM] Number of articles: {len(articles)}")
            # Return empty lists for all articles on error
            return [[] for _ in articles]

    def extract_emotions(self, text: str) -> list:
        """Extract emotions from text using LLM based on GoEmotions taxonomy."""
        system_template = self.prompts_config.get("extract_emotions", {}).get(
            "system_template",
            "You are an emotion classification assistant. Identify which emotions from the GoEmotions taxonomy the given text elicits.",
        )
        user_template = self.prompts_config.get("extract_emotions", {}).get(
            "user_template",
            'Identify emotions from this text. Choose ONLY from: {emotion_list}\n\nText: "{text}"\n\nReturn emotions as comma-separated list:',
        )

        emotion_list = "admiration, amusement, anger, annoyance, approval, caring, confusion, curiosity, desire, disappointment, disapproval, disgust, embarrassment, excitement, fear, gratitude, grief, joy, love, nervousness, optimism, pride, realization, relief, remorse, sadness, surprise, trust"

        prompt = self._format_prompt(system_template, user_template)
        prompt = prompt.replace("{text}", text).replace("{emotion_list}", emotion_list)

        try:
            outputs = self.llm.generate([prompt], self.sampling_params)
            response = outputs[0].outputs[0].text.strip()

            emotions = [e.strip().lower() for e in response.split(",") if e.strip()]
            valid_emotions = emotion_list.split(", ")
            emotions = [e for e in emotions if e in valid_emotions]
            return emotions
        except Exception:
            return []

    def extract_emotions_batch(self, texts: List[str]) -> List[list]:
        """
        Extract emotions from multiple texts in a single batch for improved performance.

        Args:
            texts: List of text strings to extract emotions from

        Returns:
            List of emotion lists (one per input text) in the same order as inputs
        """
        try:
            logger.debug(f"[vLLM] Starting batch emotion extraction for {len(texts)} texts")

            system_template = self.prompts_config.get("extract_emotions", {}).get(
                "system_template",
                "You are an emotion classification assistant. Identify which emotions from the GoEmotions taxonomy the given text elicits.",
            )
            user_template = self.prompts_config.get("extract_emotions", {}).get(
                "user_template",
                'Identify emotions from this text. Choose ONLY from: {emotion_list}\n\nText: "{text}"\n\nReturn emotions as comma-separated list:',
            )

            emotion_list = "admiration, amusement, anger, annoyance, approval, caring, confusion, curiosity, desire, disappointment, disapproval, disgust, embarrassment, excitement, fear, gratitude, grief, joy, love, nervousness, optimism, pride, realization, relief, remorse, sadness, surprise, trust"

            # Build prompts for all texts
            prompts = []
            for text in texts:
                prompt = self._format_prompt(system_template, user_template)
                prompt = prompt.replace("{text}", text).replace("{emotion_list}", emotion_list)
                prompts.append(prompt)

            # Batch generate using vLLM
            logger.debug(
                f"[vLLM] Executing batch inference for {len(prompts)} emotion extraction prompts"
            )
            outputs = self.llm.generate(prompts, self.sampling_params)

            # Parse results
            results = []
            valid_emotions = emotion_list.split(", ")
            for output in outputs:
                response = output.outputs[0].text.strip()
                emotions = [e.strip().lower() for e in response.split(",") if e.strip()]
                emotions = [e for e in emotions if e in valid_emotions]
                results.append(emotions)

            logger.debug(
                f"[vLLM] Batch emotion extraction completed successfully ({len(results)} results)"
            )
            return results
        except Exception as e:
            logger.error(f"[vLLM] Batch emotion extraction failed: {e}")
            logger.error(f"[vLLM] Number of texts: {len(texts)}")
            # Return empty lists for all texts on error
            return [[] for _ in texts]

    def describe_image(self, image_url: str) -> Optional[str]:
        """
        Generate a description of an image using the vision LLM.

        This method uses the llm_v (vision) model loaded in vLLM to analyze and
        describe an image from a given URL.

        Args:
            image_url: URL of the image to describe

        Returns:
            Optional[str]: Description of the image, or None if vision LLM not available or error occurs
        """
        # Check if vision LLM is available
        if not self.llm_v:
            logger.warning("[vLLM] Vision LLM (llm_v) not configured, cannot describe image")
            return None

        try:
            # Get prompts from configuration with defaults
            describe_image_config = self.prompts_config.get(
                "describe_image",
                {
                    "system_template": "You are an image description assistant. Describe images accurately and concisely in English.",
                    "user_template": "Describe the following image. Write in english. <img {url}>",
                },
            )
            system_template = describe_image_config.get(
                "system_template",
                "You are an image description assistant. Describe images accurately and concisely in English.",
            )
            user_template = describe_image_config.get(
                "user_template", "Describe the following image. Write in english. <img {url}>"
            )

            # Format templates
            system_msg = system_template
            user_msg = user_template.format(url=image_url)

            # For vision models, we need to format the prompt with image information
            # vLLM vision models expect a specific format
            prompt = f"{system_msg}\n\n{user_msg}"

            logger.info(f"[vLLM] Calling vLLM vision model to describe image: {image_url[:80]}...")

            # Generate description using vision model
            outputs = self.llm_v.generate([prompt], self.sampling_params_v)

            if outputs and len(outputs) > 0:
                description = outputs[0].outputs[0].text.strip()
                logger.info(
                    f"[vLLM] vLLM vision model returned description ({len(description)} chars)"
                )
                return description
            else:
                logger.warning("[vLLM] vLLM vision model returned empty description")
                return None
        except Exception as e:
            # If description fails, return None
            logger.error(f"[vLLM] vLLM vision model failed to describe image: {e}")
            logger.error(f"[vLLM] Image URL: {image_url[:100] if image_url else 'None'}")
            import traceback

            traceback.print_exc()
            return None

    def infer_article_opinion(
        self, article_content: str, topic_name: str, opinion_groups: dict
    ) -> float:
        """Infer opinion on a topic from article content using discrete opinion categories."""
        try:
            config = self.prompts_config.get("infer_article_opinion", {})
            system_template = config.get(
                "system_template",
                "You are an opinion classification assistant. Analyze articles and determine their stance on topics.",
            )
            user_template = config.get(
                "user_template",
                "Analyze this article and determine its stance on the topic '{topic}'.\n\n"
                + "Article excerpt:\n{article_text}\n\n"
                + "What is the article's stance? Choose ONLY ONE from these options:\n{opinion_options}\n\n"
                + "Your choice (ONE WORD ONLY):",
            )

            opinion_options = "\n".join([f"- {label}" for label in opinion_groups.keys()])
            article_excerpt = (
                article_content[:1000] if len(article_content) > 1000 else article_content
            )

            prompt = self._format_prompt(system_template, user_template)
            prompt = (
                prompt.replace("{topic}", topic_name)
                .replace("{article_text}", article_excerpt)
                .replace("{opinion_options}", opinion_options)
            )

            outputs = self.llm.generate([prompt], self.sampling_params)
            response = outputs[0].outputs[0].text.strip()

            response_lower = response.lower()
            selected_group = None
            for label in opinion_groups.keys():
                if label.lower() in response_lower:
                    selected_group = label
                    break

            if selected_group and selected_group in opinion_groups:
                range_values = opinion_groups[selected_group]
                opinion_value = (range_values[0] + range_values[1]) / 2.0
                return opinion_value
            else:
                import random

                return random.random()

        except Exception:
            import random

            return random.random()

    def generate_image_commentary(
        self,
        image_description: str,
        topics: List[str] = None,
        agent_attrs: dict = None,
        cluster_id: int = 0,
    ) -> str:
        """Generate commentary for sharing an image on social media."""
        persona = self._build_persona(cluster_id, agent_attrs)

        toxicity = ""
        if agent_attrs and "toxicity" in agent_attrs:
            toxicity_level = agent_attrs.get("toxicity", "").lower()
            if toxicity_level in ["low", "medium", "high"]:
                toxicity = toxicity_level

        topics_instruction = ""
        if topics:
            topics_str = ", ".join(topics)
            topics_instruction = f"Related topics: {topics_str}. "

        config = self.prompts_config.get("generate_image_commentary", {})
        system_template = config.get(
            "system_template", "{persona} You are sharing an image on social media."
        )
        user_template = config.get(
            "user_template",
            'You are sharing an image described as: "{image_description}"\n\n{topics_instruction}Write a brief, engaging post to share this image (max 280 characters).',
        )

        system_msg = system_template.format(persona=persona, toxicity=toxicity)
        user_msg = user_template.format(
            image_description=image_description, topics_instruction=topics_instruction
        )

        prompt = self._format_prompt(system_msg, user_msg)

        try:
            outputs = self.llm.generate([prompt], self.sampling_params)
            commentary = outputs[0].outputs[0].text.strip()
            return commentary if commentary else "IMAGE"
        except Exception as e:
            logger.error(f"Failed to generate image commentary: {e}")
            return "IMAGE"

    def evaluate_opinion(
        self,
        agent_opinion: str,
        author_opinion: str,
        post_text: str,
        topic: str,
        peers_opinions: list = None,
    ) -> str:
        """Evaluate how an agent's opinion should change after reading a post."""
        prompt_text = (
            f"Read the following text on the topic '{topic.upper()}': '{post_text}'.\n"
            f"The author has opinion '{author_opinion}' on the topic.\n"
            f"Your initial opinion is '{agent_opinion}'"
        )

        if peers_opinions and len(peers_opinions) > 0:
            prompt_text += "\n\nThe following are the opinions of your friends:\n"
            for op, count in peers_opinions:
                prompt_text += f"Opinion: '{op}' ({count})\n"

        prompt_text += (
            "\nWhat do you think about the expressed opinion? "
            "Answer with a single word among the options: AGREE|DISAGREE|NEUTRAL."
        )

        system_template = self.prompts_config.get("evaluate_opinion", {}).get(
            "system_template",
            "You are evaluating opinions on various topics. Consider the content and opinions presented.",
        )

        prompt = self._format_prompt(system_template, prompt_text)

        try:
            outputs = self.llm.generate([prompt], self.sampling_params)
            response = outputs[0].outputs[0].text.strip().upper()

            if "AGREE" in response:
                return "AGREE"
            elif "DISAGREE" in response:
                return "DISAGREE"
            elif "NEUTRAL" in response:
                return "NEUTRAL"

            return "NEUTRAL"
        except Exception as e:
            logger.error(f"Failed to evaluate opinion: {e}")
            return "NEUTRAL"

    def evaluate_opinion_batch(self, requests: List[Dict[str, Any]]) -> List[str]:
        """
        Evaluate multiple opinion changes in a single batch for improved performance.

        Args:
            requests: List of dicts with keys:
                - agent_opinion: Agent's current opinion label
                - author_opinion: Author's opinion label
                - post_text: Content of the post
                - topic: Topic name
                - peers_opinions: Optional list of (opinion_label, count) tuples

        Returns:
            List of evaluation results ("AGREE"|"DISAGREE"|"NEUTRAL") in same order as inputs
        """
        try:
            logger.debug(f"[vLLM] Starting batch opinion evaluation for {len(requests)} requests")

            system_template = self.prompts_config.get("evaluate_opinion", {}).get(
                "system_template",
                "You are evaluating opinions on various topics. Consider the content and opinions presented.",
            )

            # Build prompts for all evaluations
            prompts = []
            for idx, req in enumerate(requests):
                try:
                    topic = req.get("topic")
                    post_text = req.get("post_text")
                    author_opinion = req.get("author_opinion")
                    agent_opinion = req.get("agent_opinion")

                    if (
                        topic is None
                        or post_text is None
                        or author_opinion is None
                        or agent_opinion is None
                    ):
                        logger.error(
                            f"[vLLM] Missing required fields in opinion evaluation "
                            f"request {idx}: {req}"
                        )
                        raise ValueError(
                            f"Missing required fields in opinion evaluation request {idx}"
                        )

                    prompt_text = (
                        f"Read the following text on the topic '{topic.upper()}': '{post_text}'.\n"
                        f"The author has opinion '{author_opinion}' on the topic.\n"
                        f"Your initial opinion is '{agent_opinion}'"
                    )

                    peers_opinions = req.get("peers_opinions")
                    if peers_opinions and len(peers_opinions) > 0:
                        prompt_text += "\n\nThe following are the opinions of your friends:\n"
                        for op, count in peers_opinions:
                            prompt_text += f"Opinion: '{op}' ({count})\n"

                    prompt_text += (
                        "\nWhat do you think about the expressed opinion? "
                        "Answer with a single word among the options: AGREE|DISAGREE|NEUTRAL."
                    )

                    prompt = self._format_prompt(system_template, prompt_text)
                    prompts.append(prompt)
                except Exception as e:
                    logger.error(
                        f"[vLLM] Failed to build prompt for opinion evaluation request {idx}: {e}"
                    )
                    logger.error(f"[vLLM] Request: {req}")
                    raise

            # Batch generate using vLLM
            logger.debug(f"[vLLM] Executing batch inference for {len(prompts)} opinion evaluations")
            outputs = self.llm.generate(prompts, self.sampling_params)

            # Parse results
            results = []
            for output in outputs:
                response = output.outputs[0].text.strip().upper()
                if "AGREE" in response:
                    results.append("AGREE")
                elif "DISAGREE" in response:
                    results.append("DISAGREE")
                elif "NEUTRAL" in response:
                    results.append("NEUTRAL")
                else:
                    results.append("NEUTRAL")

            logger.debug(
                f"[vLLM] Batch opinion evaluation completed successfully ({len(results)} results)"
            )
            return results
        except Exception as e:
            logger.error(f"[vLLM] Batch opinion evaluation failed: {e}")
            logger.error(f"[vLLM] Number of requests: {len(requests)}")
            # Return NEUTRAL for all evaluations on error
            return ["NEUTRAL" for _ in requests]

    def generate_search_action_batch(self, requests: List[Dict[str, Any]]) -> List[str]:
        """
        Generate batch search action decisions for multiple agents in a single call.

        This method processes multiple search action decisions in parallel,
        significantly reducing latency compared to individual calls.

        Args:
            requests: List of dicts with keys:
                - cluster_id: Agent's cluster ID for persona
                - post_content: Content of the post agent found via search
                - agent_attrs: Optional dict with agent attributes for dynamic persona

        Returns:
            List of action decisions ("COMMENT"|"SHARE"|"LIKE"|"LOVE"|"LAUGH"|"ANGRY"|"SAD"|"IGNORE")
            in same order as input requests
        """
        try:
            logger.debug(
                f"[vLLM] Starting batch search action decision for {len(requests)} requests"
            )

            system_template = self.prompts_config.get("generate_search_action", {}).get(
                "system_template",
                "You are deciding how to engage with a post found via search.",
            )

            # Build prompts for all search decisions
            prompts = []
            for i, req in enumerate(requests):
                try:
                    cluster_id = req.get("cluster_id")
                    if cluster_id is None:
                        logger.error(f"[vLLM] Missing cluster_id in request {i}: {req}")
                        raise ValueError(f"Missing cluster_id in request {i}")
                    post_content = req.get("post_content", "")
                    agent_attrs = req.get("agent_attrs", {})

                    # Build persona (same as individual search action)
                    persona = self._build_persona(cluster_id, agent_attrs)

                    # Get user template
                    user_template = self.prompts_config.get("generate_search_action", {}).get(
                        "user_template",
                        "Post content: {post_content}\n\nHow should you engage? Reply with COMMENT, SHARE, LIKE, LOVE, LAUGH, ANGRY, SAD, or IGNORE.",
                    )

                    # Format the user message
                    prompt_text = user_template.format(
                        persona=persona,
                        post_content=post_content,
                    )

                    prompt = self._format_prompt(system_template, prompt_text)
                    prompts.append(prompt)

                except Exception as e:
                    logger.error(
                        f"[vLLM] Failed to build prompt for batch search action request {i}: {e}"
                    )
                    logger.error(f"[vLLM] Request: {req}")
                    # Add empty prompt as placeholder
                    prompts.append(self._format_prompt(system_template, "IGNORE"))

            # Batch generate using vLLM
            logger.debug(
                f"[vLLM] Executing batch inference for {len(prompts)} search action prompts"
            )
            outputs = self.llm.generate(prompts, self.sampling_params)

            # Parse results
            results = []
            valid_actions = {"COMMENT", "SHARE", "LIKE", "LOVE", "LAUGH", "ANGRY", "SAD", "IGNORE"}
            for output in outputs:
                response = output.outputs[0].text.strip().upper()
                # Extract first valid action from response
                action = "IGNORE"  # default
                for valid_action in valid_actions:
                    if valid_action in response:
                        action = valid_action
                        break
                results.append(action)

            logger.debug(
                f"[vLLM] Batch search action decision completed successfully ({len(results)} results)"
            )
            return results

        except Exception as e:
            logger.error(f"[vLLM] Batch search action decision failed: {e}")
            logger.error(f"[vLLM] Number of requests: {len(requests)}")
            raise RuntimeError(f"vLLM batch search action decision failed: {e}") from e
