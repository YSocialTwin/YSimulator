"""
Cost Tracker for monitoring LLM usage and costs.

This module provides optional cost tracking functionality for LLM calls,
helping monitor token usage and API costs.
"""

import logging
from collections import defaultdict
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
    ):
        """
        Initialize the CostTracker.
        
        Args:
            token_costs: Optional dict mapping LLM methods to cost per 1K tokens
            logger: Logger instance for debugging
        """
        self.call_counts = defaultdict(int)
        self.token_counts = defaultdict(int)
        self.token_costs = token_costs or {}
        self.logger = logger or logging.getLogger(__name__)
    
    def record_call(
        self, method: str, input_tokens: int = 0, output_tokens: int = 0
    ) -> None:
        """
        Record an LLM call.
        
        Args:
            method: LLM method name (e.g., 'generate_post')
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens
        """
        self.call_counts[method] += 1
        self.token_counts[method] += input_tokens + output_tokens
        
        self.logger.debug(
            f"LLM call recorded: {method} "
            f"(in={input_tokens}, out={output_tokens}, total={input_tokens + output_tokens})"
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
