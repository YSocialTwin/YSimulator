"""
Batch Handler for processing LLM calls in scatter/gather pattern.

This module provides generic batch processing functionality for LLM calls,
implementing the scatter/gather pattern for optimal performance.
"""

import logging
import traceback
from typing import Any, List, Optional, Tuple

import ray


class BatchHandler:
    """
    Handles batch processing of LLM futures using scatter/gather pattern.

    The scatter/gather pattern:
    - Scatter: Fire off all LLM calls immediately without waiting
    - Gather: Wait once for all LLM results simultaneously (ray.get on list)

    This preserves parallelism for best performance.
    """

    def __init__(self, logger: Optional[logging.Logger] = None):
        """
        Initialize the BatchHandler.

        Args:
            logger: Logger instance for debugging
        """
        self.logger = logger or logging.getLogger(__name__)

    def gather_futures(self, futures: List[Any]) -> List[Any]:
        """
        Gather multiple LLM futures in parallel.

        Uses ray.get() to wait for all futures simultaneously,
        maintaining the scatter/gather pattern for performance.

        Args:
            futures: List of Ray ObjectRef futures

        Returns:
            List of results in the same order as futures
        """
        if not futures:
            return []

        self.logger.debug(f"Gathering {len(futures)} LLM futures in parallel")

        try:
            results = ray.get(futures)
            self.logger.debug(f"Successfully gathered {len(results)} results")
            return results
        except ray.exceptions.RayTaskError as e:
            # Ray task execution error - log full details
            self.logger.error(f"Ray task error gathering futures: {type(e).__name__}: {str(e)}")
            self.logger.error(f"Full traceback:\n{traceback.format_exc()}")
            
            # Try to get individual results to identify which future failed
            results = []
            for i, future in enumerate(futures):
                try:
                    result = ray.get(future)
                    results.append(result)
                except Exception as individual_error:
                    self.logger.error(f"Future {i} failed: {type(individual_error).__name__}: {str(individual_error)}")
                    results.append(None)
            return results
        except ray.exceptions.RayActorError as e:
            # Actor crashed or unavailable
            self.logger.error(f"Ray actor error gathering futures: {type(e).__name__}: {str(e)}")
            self.logger.error(f"Full traceback:\n{traceback.format_exc()}")
            return [None] * len(futures)
        except ray.exceptions.GetTimeoutError as e:
            # Timeout (shouldn't happen in this method but handle it)
            self.logger.error(f"Timeout gathering futures: {type(e).__name__}: {str(e)}")
            return [None] * len(futures)
        except Exception as e:
            # Generic error - log everything we can
            self.logger.error(f"Unexpected error gathering futures: {type(e).__name__}: {str(e)}")
            self.logger.error(f"Full traceback:\n{traceback.format_exc()}")
            self.logger.error(f"Number of futures: {len(futures)}")
            
            # Try to get individual results to identify which future failed
            results = []
            for i, future in enumerate(futures):
                try:
                    result = ray.get(future)
                    results.append(result)
                except Exception as individual_error:
                    self.logger.error(f"Future {i} failed: {type(individual_error).__name__}: {str(individual_error)}")
                    results.append(None)
            return results

    def gather_with_metadata(
        self, futures_with_metadata: List[Tuple[Any, dict]]
    ) -> List[Tuple[Any, dict]]:
        """
        Gather futures while preserving associated metadata.

        This is useful when you need to track additional information
        about each LLM call (e.g., agent_id, cluster_id, etc.).

        Args:
            futures_with_metadata: List of tuples (future, metadata_dict)

        Returns:
            List of tuples (result, metadata_dict) in the same order
        """
        if not futures_with_metadata:
            return []

        # Separate futures and metadata
        futures = [item[0] for item in futures_with_metadata]
        metadata_list = [item[1] for item in futures_with_metadata]

        self.logger.debug(f"Gathering {len(futures)} LLM futures with metadata")

        # Gather all futures
        results = self.gather_futures(futures)

        # Combine results with metadata
        return list(zip(results, metadata_list))

    def batch_process(
        self,
        items: List[Tuple],
        process_fn: callable,
        batch_size: Optional[int] = None,
    ) -> List[Any]:
        """
        Process items in batches with a custom processing function.

        This is useful for rate limiting or memory management when
        dealing with large numbers of LLM calls.

        Args:
            items: List of items to process
            process_fn: Function that takes a batch and returns results
            batch_size: Optional batch size (None = process all at once)

        Returns:
            List of results from all batches combined
        """
        if not items:
            return []

        if batch_size is None or batch_size >= len(items):
            # Process everything in one batch
            return process_fn(items)

        # Process in batches
        results = []
        for i in range(0, len(items), batch_size):
            batch = items[i : i + batch_size]
            self.logger.debug(f"Processing batch {i // batch_size + 1}: {len(batch)} items")
            batch_results = process_fn(batch)
            results.extend(batch_results)

        return results

    def gather_with_timeout(self, futures: List[Any], timeout: Optional[float] = None) -> List[Any]:
        """
        Gather futures with an optional timeout.

        Args:
            futures: List of Ray ObjectRef futures
            timeout: Optional timeout in seconds (None = no timeout)

        Returns:
            List of results, with None for any that timed out
        """
        if not futures:
            return []

        self.logger.debug(
            f"Gathering {len(futures)} futures with timeout={timeout}s"
            if timeout
            else f"Gathering {len(futures)} futures (no timeout)"
        )

        try:
            if timeout:
                results = ray.get(futures, timeout=timeout)
            else:
                results = ray.get(futures)
            return results
        except ray.exceptions.GetTimeoutError as e:
            self.logger.warning(f"Timeout gathering futures after {timeout}s: {str(e)}")
            # Try to get what we can
            ready_futures, _ = ray.wait(futures, num_returns=len(futures), timeout=0)
            results = []
            for i, future in enumerate(futures):
                if future in ready_futures:
                    try:
                        results.append(ray.get(future, timeout=0))
                    except Exception as individual_error:
                        self.logger.error(f"Future {i} failed even though ready: {type(individual_error).__name__}: {str(individual_error)}")
                        results.append(None)
                else:
                    self.logger.debug(f"Future {i} not ready after timeout")
                    results.append(None)
            return results
        except ray.exceptions.RayTaskError as e:
            self.logger.error(f"Ray task error gathering futures with timeout: {type(e).__name__}: {str(e)}")
            self.logger.error(f"Full traceback:\n{traceback.format_exc()}")
            
            # Try to get individual results
            results = []
            for i, future in enumerate(futures):
                try:
                    result = ray.get(future)
                    results.append(result)
                except Exception as individual_error:
                    self.logger.error(f"Future {i} failed: {type(individual_error).__name__}: {str(individual_error)}")
                    results.append(None)
            return results
        except ray.exceptions.RayActorError as e:
            self.logger.error(f"Ray actor error gathering futures with timeout: {type(e).__name__}: {str(e)}")
            self.logger.error(f"Full traceback:\n{traceback.format_exc()}")
            return [None] * len(futures)
        except Exception as e:
            self.logger.error(f"Unexpected error gathering futures with timeout: {type(e).__name__}: {str(e)}")
            self.logger.error(f"Full traceback:\n{traceback.format_exc()}")
            return [None] * len(futures)
