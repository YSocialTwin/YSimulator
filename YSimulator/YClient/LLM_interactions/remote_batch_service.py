"""
Remote batch-capable LLM service.

This service reuses the VLLMService prompt/batch method surface, but delegates
generation to a remote chat endpoint instead of an embedded local vLLM engine.
It is selected only after a small startup probe succeeds.
"""

import logging
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import ray
from langchain_ollama import ChatOllama

from YSimulator.YClient.LLM_interactions.vllm_service import VLLMService

logger = logging.getLogger(__name__)

_VLLMServiceBase = VLLMService.__ray_metadata__.modified_class


def _normalize_base_url(config: Dict[str, Any]) -> str:
    """Build the base URL following the same rules as the existing non-vLLM path."""
    address = config["address"]
    if address.startswith("http://") or address.startswith("https://"):
        address = address.replace("http://", "").replace("https://", "")
    if ":" in address:
        return f"http://{address}".replace("/v1", "")
    return f"http://{address}:{config['port']}".replace("/v1", "")


def _extract_text(response: Any) -> str:
    """Extract text content from a LangChain chat response."""
    if response is None:
        return ""

    content = getattr(response, "content", response)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                parts.append(item.get("text", ""))
            else:
                parts.append(str(item))
        return "".join(parts)
    return str(content)


class _RemoteSamplingParams:
    """Small compatibility shim for vLLM-style sampling params."""

    def __init__(self, temperature: float, max_tokens: int):
        self.temperature = temperature
        self.max_tokens = max_tokens


class _RemoteChatModelAdapter:
    """Adapter exposing a vLLM-like generate() surface over a chat model."""

    def __init__(self, chat_model: ChatOllama):
        self.chat_model = chat_model

    def generate(self, prompts: List[str], sampling_params: Optional[_RemoteSamplingParams] = None):
        if not prompts:
            return []

        if len(prompts) == 1:
            raw_results = [self.chat_model.invoke(prompts[0])]
        else:
            raw_results = self.chat_model.batch(prompts)

        outputs = []
        for result in raw_results:
            text = _extract_text(result).strip()
            outputs.append(SimpleNamespace(outputs=[SimpleNamespace(text=text)]))
        return outputs


def probe_remote_batch_support(llm_config: Dict[str, Any], logger: Optional[logging.Logger] = None) -> bool:
    """
    Probe whether the configured remote endpoint can execute a short batch request.

    This is intentionally conservative: if the probe errors or the response shape is
    unexpected, callers should fall back to the standard LLMService path.
    """
    logger = logger or logging.getLogger(__name__)

    try:
        base_url = _normalize_base_url(llm_config)
        probe_kwargs = {
            "model": llm_config["model"],
            "temperature": llm_config.get("temperature", 0.7),
            "base_url": base_url,
        }
        if "timeout" in llm_config:
            probe_kwargs["timeout"] = llm_config["timeout"]

        probe_model = ChatOllama(**probe_kwargs)
        probe_inputs = [
            "Reply with exactly OK.",
            "Reply with exactly OK.",
        ]
        result = probe_model.batch(probe_inputs)
        if not isinstance(result, list) or len(result) != len(probe_inputs):
            return False
        return all(bool(_extract_text(item).strip()) for item in result)
    except Exception as exc:
        logger.info(f"Remote batch probe failed, falling back to standard LLMService: {exc}")
        return False


@ray.remote
class RemoteBatchLLMService(_VLLMServiceBase):
    """
    Remote batch-capable LLM service.

    The method surface intentionally matches VLLMService, but generation is delegated
    to a remote chat endpoint. This preserves the batch request/response behavior used
    by BatchProcessor without requiring a local embedded vLLM engine.
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
        llm_config = llm_config or {
            "address": "localhost",
            "port": 11434,
            "model": "llama3.2",
            "temperature": 0.7,
            "max_tokens": 256,
        }
        prompts_config = prompts_config or {}
        logging_config = logging_config or {}

        self.server = server
        self.client_id = client_id
        self.prompts_config = prompts_config
        self.model_name = llm_config.get("model", "llama3.2")
        self.pool_prefix = llm_config.get("_resolved_actor_name_prefix")
        self.pool_namespace = llm_config.get("_resolved_actor_namespace")
        self.prompt_logger = None

        base_url = _normalize_base_url(llm_config)
        llm_kwargs = {
            "model": llm_config["model"],
            "temperature": llm_config.get("temperature", 0.7),
            "base_url": base_url,
        }
        if "timeout" in llm_config:
            llm_kwargs["timeout"] = llm_config["timeout"]

        text_model = ChatOllama(**llm_kwargs)
        self.llm = _RemoteChatModelAdapter(text_model)
        self.sampling_params = _RemoteSamplingParams(
            temperature=llm_config.get("temperature", 0.7),
            max_tokens=llm_config.get("max_tokens", 256),
        )

        self.llm_v = None
        self.sampling_params_v = None
        self.vision_gpu_id = None
        self.gpu_selection_info = {
            "backend": "remote_batch",
            "base_url": base_url,
            "model": self.model_name,
        }
        self.vision_init_status = "vision llm not configured"

        if llm_v_config:
            base_url_v = _normalize_base_url(llm_v_config)
            llm_v_kwargs = {
                "model": llm_v_config["model"],
                "temperature": llm_v_config.get("temperature", 0.5),
                "base_url": base_url_v,
            }
            if "timeout" in llm_v_config:
                llm_v_kwargs["timeout"] = llm_v_config["timeout"]
            self.llm_v = _RemoteChatModelAdapter(ChatOllama(**llm_v_kwargs))
            self.sampling_params_v = _RemoteSamplingParams(
                temperature=llm_v_config.get("temperature", 0.5),
                max_tokens=llm_v_config.get("max_tokens", 300),
            )
            self.vision_init_status = None

        # Reuse the existing actor log setup from VLLMService.
        self._setup_logger(logging_config)

    def get_capabilities(self) -> Dict[str, Any]:
        """Expose capability flags for capability-driven dispatch and diagnostics."""
        return {
            "provider": "remote_batch",
            "supports_native_batching": True,
            "supports_batch_posts": True,
            "supports_batch_reactions": True,
            "supports_batch_comments": True,
            "supports_batch_read_reactions": True,
            "supports_batch_opinion_eval": True,
            "supports_batch_search_actions": True,
            "supports_batch_emotions": True,
            "supports_batch_topics": True,
            "supports_batch_images": self.llm_v is not None,
        }

    def get_service_metadata(self) -> Dict[str, Any]:
        """Expose enough metadata for diagnostics and future pool discovery."""
        return {
            "backend": "remote_batch",
            "model": self.model_name,
            "pool_prefix": self.pool_prefix,
            "pool_namespace": self.pool_namespace,
        }

    def shutdown(self) -> Dict[str, Any]:
        """
        Remote services do not own a local engine or worker tree.

        Keep the same method surface as VLLMService so shared cleanup logic can call
        shutdown safely without special-casing this actor type.
        """
        self.llm = None
        self.llm_v = None
        self.sampling_params = None
        self.sampling_params_v = None
        return {
            "actor_pid": None,
            "child_pids": [],
            "terminated_children": 0,
            "errors": [],
        }
