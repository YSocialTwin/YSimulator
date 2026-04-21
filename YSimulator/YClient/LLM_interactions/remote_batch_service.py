"""
Remote batch-capable LLM service.

This service reuses the VLLMService prompt/batch method surface, but delegates
generation to a remote endpoint instead of an embedded local vLLM engine.
It supports both Ollama-compatible and OpenAI-compatible chat/completions APIs.
"""

import logging
from types import SimpleNamespace
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import ray
import requests
from langchain_ollama import ChatOllama

from YSimulator.YClient.LLM_interactions.vllm_service import VLLMService

logger = logging.getLogger(__name__)

_VLLMServiceBase = VLLMService.__ray_metadata__.modified_class


def _coerce_http_base_url(config: Dict[str, Any]) -> str:
    """Build a normalized base URL from address/port without dropping path segments."""
    address = config["address"]
    if address.startswith("http://") or address.startswith("https://"):
        return address.rstrip("/")
    if ":" in address:
        return f"http://{address}".rstrip("/")
    return f"http://{address}:{config['port']}".rstrip("/")


def _normalize_ollama_base_url(config: Dict[str, Any]) -> str:
    """Return base URL suitable for Ollama's /api endpoints."""
    base_url = _coerce_http_base_url(config)
    parsed = urlparse(base_url)
    path = parsed.path.rstrip("/")
    if path.endswith("/v1"):
        path = path[: -len("/v1")]
    rebuilt = parsed._replace(path=path)
    return rebuilt.geturl().rstrip("/")


def _normalize_openai_base_url(config: Dict[str, Any]) -> str:
    """Return base URL suitable for OpenAI-compatible /v1 endpoints."""
    base_url = _coerce_http_base_url(config)
    parsed = urlparse(base_url)
    path = parsed.path.rstrip("/")
    if not path.endswith("/v1"):
        path = f"{path}/v1" if path else "/v1"
    rebuilt = parsed._replace(path=path)
    return rebuilt.geturl().rstrip("/")


def _extract_text(response: Any) -> str:
    """Extract text content from a LangChain or raw response."""
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


class _OllamaChatModelAdapter:
    """Adapter exposing a vLLM-like generate() surface over ChatOllama."""

    provider = "ollama"

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


class _OpenAICompatibleModelAdapter:
    """Adapter for OpenAI-compatible completion endpoints such as remote vLLM."""

    provider = "openai"

    def __init__(
        self,
        model: str,
        base_url: str,
        api_key: Optional[str] = None,
        timeout: int = 30,
    ):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key and str(self.api_key).upper() != "NULL":
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def generate(self, prompts: List[str], sampling_params: Optional[_RemoteSamplingParams] = None):
        if not prompts:
            return []

        sampling_params = sampling_params or _RemoteSamplingParams(temperature=0.7, max_tokens=256)
        payload = {
            "model": self.model,
            "prompt": prompts if len(prompts) > 1 else prompts[0],
            "temperature": sampling_params.temperature,
            "max_tokens": sampling_params.max_tokens,
        }
        response = requests.post(
            f"{self.base_url}/completions",
            headers=self._headers(),
            json=payload,
            timeout=self.timeout,
        )
        response.raise_for_status()
        data = response.json()
        choices = data.get("choices", [])

        texts = [""] * len(prompts)
        if len(prompts) == 1 and choices:
            texts[0] = (choices[0].get("text") or "").strip()
        else:
            for choice in choices:
                index = choice.get("index", 0)
                if 0 <= index < len(texts):
                    texts[index] = (choice.get("text") or "").strip()

        return [SimpleNamespace(outputs=[SimpleNamespace(text=text)]) for text in texts]


def _probe_openai_batch_support(llm_config: Dict[str, Any], logger: Optional[logging.Logger] = None) -> bool:
    """Probe whether the endpoint supports OpenAI-compatible batched completions."""
    logger = logger or logging.getLogger(__name__)
    try:
        base_url = _normalize_openai_base_url(llm_config)
        payload = {
            "model": llm_config["model"],
            "prompt": ["Reply with exactly OK.", "Reply with exactly OK."],
            "temperature": llm_config.get("temperature", 0.7),
            "max_tokens": llm_config.get("max_tokens", 16),
        }
        headers = {"Content-Type": "application/json"}
        api_key = llm_config.get("llm_api_key")
        if api_key and str(api_key).upper() != "NULL":
            headers["Authorization"] = f"Bearer {api_key}"
        response = requests.post(
            f"{base_url}/completions",
            headers=headers,
            json=payload,
            timeout=llm_config.get("timeout", 15),
        )
        if response.status_code >= 400:
            logger.info(
                f"OpenAI-compatible batch probe failed with status={response.status_code}: {response.text[:200]}"
            )
            return False
        data = response.json()
        choices = data.get("choices", [])
        return len(choices) == 2 and all(bool((choice.get("text") or "").strip()) for choice in choices)
    except Exception as exc:
        logger.info(f"OpenAI-compatible batch probe failed: {exc}")
        return False


def _probe_ollama_batch_support(llm_config: Dict[str, Any], logger: Optional[logging.Logger] = None) -> bool:
    """Probe whether the endpoint supports Ollama-compatible batch requests."""
    logger = logger or logging.getLogger(__name__)
    try:
        base_url = _normalize_ollama_base_url(llm_config)
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
        logger.info(f"Ollama-compatible batch probe failed: {exc}")
        return False


def resolve_remote_batch_provider(
    llm_config: Dict[str, Any], logger: Optional[logging.Logger] = None
) -> Optional[str]:
    """Resolve which remote API family supports batching for this endpoint."""
    logger = logger or logging.getLogger(__name__)
    api_format = str(llm_config.get("api_format", "auto")).strip().lower()
    backend = str(llm_config.get("backend", "")).strip().lower()

    if api_format not in {"auto", "ollama", "openai"}:
        logger.warning(f"Unknown llm.api_format={api_format}; defaulting to auto")
        api_format = "auto"

    if api_format != "auto":
        probe_order = [api_format]
    elif backend == "ollama":
        # Avoid probing OpenAI-compatible /v1/completions first on Ollama
        # endpoints, which produces a misleading 400 during normal startup.
        probe_order = ["ollama", "openai"]
    else:
        probe_order = ["openai", "ollama"]
    for provider in probe_order:
        if provider == "openai" and _probe_openai_batch_support(llm_config, logger=logger):
            return "openai"
        if provider == "ollama" and _probe_ollama_batch_support(llm_config, logger=logger):
            return "ollama"
    return None


def probe_remote_batch_support(llm_config: Dict[str, Any], logger: Optional[logging.Logger] = None) -> bool:
    """Return True if any supported remote API family accepts batched generation."""
    return resolve_remote_batch_provider(llm_config, logger=logger) is not None


@ray.remote
class RemoteBatchLLMService(_VLLMServiceBase):
    """
    Remote batch-capable LLM service.

    The method surface intentionally matches VLLMService, but generation is delegated
    to a remote endpoint. This preserves the batch request/response behavior used
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
        self.remote_api = llm_config.get("_resolved_remote_api") or resolve_remote_batch_provider(
            llm_config, logger=logger
        )
        if not self.remote_api:
            raise RuntimeError("RemoteBatchLLMService requires a batch-capable remote endpoint")

        self.llm = self._build_model_adapter(llm_config)
        self.sampling_params = _RemoteSamplingParams(
            temperature=llm_config.get("temperature", 0.7),
            max_tokens=llm_config.get("max_tokens", 256),
        )

        self.llm_v = None
        self.sampling_params_v = None
        self.vision_gpu_id = None
        self.gpu_selection_info = {
            "backend": "remote_batch",
            "remote_api": self.remote_api,
            "base_url": self._display_base_url(llm_config),
            "model": self.model_name,
        }
        self.vision_init_status = "vision llm not configured"

        if llm_v_config:
            llm_v_config = dict(llm_v_config)
            llm_v_config.setdefault("api_format", llm_config.get("api_format", self.remote_api))
            llm_v_config.setdefault("llm_api_key", llm_config.get("llm_api_key"))
            llm_v_config.setdefault("timeout", llm_config.get("timeout"))
            llm_v_config["_resolved_remote_api"] = llm_v_config.get("api_format")
            self.llm_v = self._build_model_adapter(llm_v_config)
            self.sampling_params_v = _RemoteSamplingParams(
                temperature=llm_v_config.get("temperature", 0.5),
                max_tokens=llm_v_config.get("max_tokens", 300),
            )
            self.vision_init_status = None

        self._setup_logger(logging_config)

    def _display_base_url(self, config: Dict[str, Any]) -> str:
        if self.remote_api == "openai":
            return _normalize_openai_base_url(config)
        return _normalize_ollama_base_url(config)

    def _build_model_adapter(self, config: Dict[str, Any]):
        remote_api = config.get("_resolved_remote_api") or config.get("api_format") or self.remote_api
        remote_api = remote_api.lower()
        if remote_api == "openai":
            return _OpenAICompatibleModelAdapter(
                model=config["model"],
                base_url=_normalize_openai_base_url(config),
                api_key=config.get("llm_api_key"),
                timeout=config.get("timeout", 30),
            )

        llm_kwargs = {
            "model": config["model"],
            "temperature": config.get("temperature", 0.7),
            "base_url": _normalize_ollama_base_url(config),
        }
        if "timeout" in config:
            llm_kwargs["timeout"] = config["timeout"]
        return _OllamaChatModelAdapter(ChatOllama(**llm_kwargs))

    def get_capabilities(self) -> Dict[str, Any]:
        """Expose capability flags for capability-driven dispatch and diagnostics."""
        return {
            "provider": "remote_batch",
            "remote_api": self.remote_api,
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
            "remote_api": self.remote_api,
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
