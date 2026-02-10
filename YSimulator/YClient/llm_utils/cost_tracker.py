"""
Cost Tracker for monitoring LLM usage and costs.

This module provides optional cost tracking functionality for LLM calls,
helping monitor token usage and API costs.
"""

import json
import logging
from collections import defaultdict
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Dict, Optional


class CostTracker:
    """
    Tracks LLM usage and costs.

    Monitors:
    - Number of calls per method
    - Estimated token usage
    - Estimated costs (if pricing provided)
    """

    def __init__(
        self,
        token_costs: Optional[Dict[str, float]] = None,
        logger: Optional[logging.Logger] = None,
        log_file_path: Optional[Path] = None,
        enable_file_logging: bool = True,
    ):
        """
        Initialize the CostTracker.

        Args:
            token_costs: Optional dict mapping LLM methods to cost per 1K tokens
            logger: Logger instance for debugging
            log_file_path: Optional path to dedicated LLM usage log file
            enable_file_logging: Whether to enable file logging (default: True)
        """
        self.call_counts = defaultdict(int)
        self.token_counts = defaultdict(int)
        self.token_costs = token_costs or {}
        self.logger = logger or logging.getLogger(__name__)

        # Set up dedicated file logging for LLM usage if enabled
        self.usage_logger = None
        if enable_file_logging and log_file_path:
            self._setup_usage_logger(log_file_path)

    def _setup_usage_logger(self, log_file_path: Path) -> None:
        """
        Set up dedicated file logger for LLM usage statistics.

        Args:
            log_file_path: Path to the LLM usage log file
        """
        # Ensure log directory exists
        log_file_path.parent.mkdir(parents=True, exist_ok=True)

        # Create dedicated logger for LLM usage
        self.usage_logger = logging.getLogger(f"YSimulator.LLMUsage.{id(self)}")
        self.usage_logger.setLevel(logging.INFO)
        self.usage_logger.propagate = False  # Don't propagate to parent

        # Remove any existing handlers
        self.usage_logger.handlers = []

        # Create rotating file handler (10MB per file, keep 5 backups)
        handler = RotatingFileHandler(log_file_path, maxBytes=10 * 1024 * 1024, backupCount=5)

        # Use JSON format for structured logging
        class UsageFormatter(logging.Formatter):
            def format(self, record: logging.LogRecord) -> str:
                return record.getMessage()

        handler.setFormatter(UsageFormatter())
        self.usage_logger.addHandler(handler)

    def record_call(self, method: str, input_tokens: int = 0, output_tokens: int = 0) -> None:
        """
        Record an LLM call.

        Args:
            method: LLM method name (e.g., 'generate_post')
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens
        """
        self.call_counts[method] += 1
        total_tokens = input_tokens + output_tokens
        self.token_counts[method] += total_tokens

        self.logger.debug(
            f"LLM call recorded: {method} "
            f"(in={input_tokens}, out={output_tokens}, total={total_tokens})"
        )

        # Log to dedicated usage file if enabled
        if self.usage_logger:
            log_entry = {
                "timestamp": datetime.utcnow().isoformat(),
                "method": method,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": total_tokens,
                "cumulative_calls": self.call_counts[method],
                "cumulative_tokens": self.token_counts[method],
            }

            # Add cost if configured
            if method in self.token_costs:
                cost_per_1k = self.token_costs[method]
                log_entry["cost"] = (total_tokens / 1000.0) * cost_per_1k
                log_entry["cumulative_cost"] = self.get_estimated_cost(method)

            self.usage_logger.info(json.dumps(log_entry))

    def log_gpu_selection(self, gpu_info: dict, model_name: str = None, backend: str = "vllm") -> None:
        """
        Log GPU selection information to the usage log.

        Args:
            gpu_info: Dictionary with GPU selection details
            model_name: Optional model name being loaded
            backend: Backend being used (default: vllm)
        """
        if self.usage_logger:
            log_entry = {
                "timestamp": datetime.utcnow().isoformat(),
                "event": "gpu_selection",
                "backend": backend,
                "physical_gpu_id": gpu_info.get("physical_gpu_id"),
                "logical_gpu_id": gpu_info.get("logical_gpu_id"),
                "assignment_method": gpu_info.get("assignment_method", "unknown"),
                "cuda_visible_devices": gpu_info.get("cuda_visible_devices"),
            }
            
            if model_name:
                log_entry["model"] = model_name
            
            self.usage_logger.info(json.dumps(log_entry))
            self.logger.info(
                f"GPU selection logged: method={gpu_info.get('assignment_method')}, "
                f"physical_gpu={gpu_info.get('physical_gpu_id')}"
            )

    def get_call_count(self, method: Optional[str] = None) -> int:
        """
        Get total number of calls.

        Args:
            method: Optional method name to filter by

        Returns:
            Number of calls (for method if specified, total otherwise)
        """
        if method:
            return self.call_counts[method]
        return sum(self.call_counts.values())

    def get_token_count(self, method: Optional[str] = None) -> int:
        """
        Get total number of tokens used.

        Args:
            method: Optional method name to filter by

        Returns:
            Number of tokens (for method if specified, total otherwise)
        """
        if method:
            return self.token_counts[method]
        return sum(self.token_counts.values())

    def get_estimated_cost(self, method: Optional[str] = None) -> float:
        """
        Get estimated cost based on token usage.

        Args:
            method: Optional method name to filter by

        Returns:
            Estimated cost in dollars
        """
        if not self.token_costs:
            return 0.0

        if method:
            tokens = self.token_counts[method]
            cost_per_1k = self.token_costs.get(method, 0.0)
            return (tokens / 1000.0) * cost_per_1k

        total_cost = 0.0
        for method, tokens in self.token_counts.items():
            cost_per_1k = self.token_costs.get(method, 0.0)
            total_cost += (tokens / 1000.0) * cost_per_1k

        return total_cost

    def get_summary(self) -> Dict:
        """
        Get a summary of usage and costs.

        Returns:
            Dictionary with usage statistics
        """
        summary = {
            "total_calls": self.get_call_count(),
            "total_tokens": self.get_token_count(),
            "estimated_cost": self.get_estimated_cost(),
            "by_method": {},
        }

        for method in set(self.call_counts.keys()) | set(self.token_counts.keys()):
            summary["by_method"][method] = {
                "calls": self.call_counts[method],
                "tokens": self.token_counts[method],
                "cost": self.get_estimated_cost(method),
            }

        return summary

    def log_summary(self) -> None:
        """Log a summary of usage and costs."""
        summary = self.get_summary()

        self.logger.info("=" * 60)
        self.logger.info("LLM Usage Summary")
        self.logger.info("=" * 60)
        self.logger.info(f"Total Calls: {summary['total_calls']}")
        self.logger.info(f"Total Tokens: {summary['total_tokens']:,}")
        self.logger.info(f"Estimated Cost: ${summary['estimated_cost']:.4f}")
        self.logger.info("-" * 60)

        for method, stats in sorted(summary["by_method"].items()):
            self.logger.info(
                f"{method:30s}: {stats['calls']:4d} calls, "
                f"{stats['tokens']:8,} tokens, ${stats['cost']:.4f}"
            )

        self.logger.info("=" * 60)

    def reset(self) -> None:
        """Reset all counters."""
        self.call_counts.clear()
        self.token_counts.clear()
        self.logger.info("Cost tracker reset")
