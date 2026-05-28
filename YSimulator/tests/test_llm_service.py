"""
Unit tests for LLM Service Layer (Phase 3).

Tests cover:
- LLMManager: Centralized LLM interaction
- BatchHandler: Scatter/gather pattern processing
- RetryHandler: Error handling and retry logic
- ResponseParser: Response validation
- CostTracker: Usage and cost monitoring
"""

import logging
import sys
import unittest
from unittest.mock import MagicMock, Mock, patch

# Mock ray before importing llm_utils components
sys.modules["ray"] = MagicMock()

from YSimulator.YClient.llm_utils.batch_handler import BatchHandler
from YSimulator.YClient.llm_utils.cost_tracker import CostTracker
from YSimulator.YClient.llm_utils.llm_manager import LLMManager
from YSimulator.YClient.llm_utils.response_parser import ResponseParser
from YSimulator.YClient.llm_utils.retry_handler import RetryHandler


class TestLLMManager(unittest.TestCase):
    """Test LLMManager functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_logger = MagicMock(spec=logging.Logger)
        self.mock_llm = MagicMock()
        self.mock_llm.generate_post = MagicMock()
        self.mock_llm.generate_comment = MagicMock()
        self.mock_llm.decide_follow = MagicMock()

    def test_initialization(self):
        """Test LLMManager initialization."""
        manager = LLMManager(self.mock_llm, logger=self.mock_logger)
        self.assertEqual(manager.llm, self.mock_llm)
        self.assertEqual(manager.logger, self.mock_logger)

    def test_is_available(self):
        """Test LLM availability check."""
        manager = LLMManager(self.mock_llm)
        self.assertTrue(manager.is_available())

        manager_none = LLMManager(None)
        self.assertFalse(manager_none.is_available())

    def test_generate_post(self):
        """Test generate_post method."""
        manager = LLMManager(self.mock_llm, logger=self.mock_logger)

        future = manager.generate_post(1, {"name": "Alice"}, "technology")

        self.mock_llm.generate_post.remote.assert_called_once_with(
            1, {"name": "Alice"}, "technology"
        )
        self.assertIsNotNone(future)

    def test_generate_comment(self):
        """Test generate_comment method."""
        manager = LLMManager(self.mock_llm)

        future = manager.generate_comment(
            1, "Great post!", {"name": "Bob"}, "Alice", "Previous context"
        )

        self.mock_llm.generate_comment.remote.assert_called_once()
        self.assertIsNotNone(future)


class TestStressPromptFormatting(unittest.TestCase):
    """Test stress prompt formatting helpers used by LLM services."""

    def test_llm_service_stress_prompt_block(self):
        from YSimulator.YClient.LLM_interactions.llm_service import _stress_prompt_block

        block = _stress_prompt_block(
            {
                "stress_level_label": "moderately stressed",
                "stress_level_scale": 3,
            }
        )

        self.assertIn("moderately stressed", block)
        self.assertIn("3/5", block)

    def test_vllm_service_stress_prompt_block(self):
        from YSimulator.YClient.LLM_interactions.vllm_service import _stress_prompt_block

        block = _stress_prompt_block(
            {
                "stress_level_label": "slightly stressed",
                "stress_level_scale": 2,
            }
        )

        self.assertIn("slightly stressed", block)
        self.assertIn("2/5", block)

    def test_stress_prompt_block_is_empty_without_metadata(self):
        from YSimulator.YClient.LLM_interactions.llm_service import _stress_prompt_block

        self.assertEqual(_stress_prompt_block({}), "")


class TestBatchHandler(unittest.TestCase):
    """Test BatchHandler functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_logger = MagicMock(spec=logging.Logger)

    def test_initialization(self):
        """Test BatchHandler initialization."""
        handler = BatchHandler(logger=self.mock_logger)
        self.assertEqual(handler.logger, self.mock_logger)

    def test_gather_futures_success(self):
        """Test successful future gathering."""
        with patch(
            "YSimulator.YClient.llm_utils.batch_handler.ray.get",
            return_value=["result1", "result2", "result3"],
        ) as mock_ray_get:
            handler = BatchHandler(logger=self.mock_logger)
            futures = [Mock(), Mock(), Mock()]

            results = handler.gather_futures(futures)

            self.assertEqual(len(results), 3)
            self.assertEqual(results, ["result1", "result2", "result3"])
            mock_ray_get.assert_called_once_with(futures)

    def test_gather_futures_empty(self):
        """Test gathering empty list."""
        handler = BatchHandler(logger=self.mock_logger)
        results = handler.gather_futures([])
        self.assertEqual(results, [])

    def test_gather_futures_error(self):
        """Test future gathering with error."""
        with patch(
            "YSimulator.YClient.llm_utils.batch_handler.ray.get",
            side_effect=Exception("Ray error"),
        ):
            handler = BatchHandler(logger=self.mock_logger)
            futures = [Mock(), Mock()]

            results = handler.gather_futures(futures)

            # Should return None for each future on error
            self.assertEqual(results, [None, None])

    def test_gather_with_metadata(self):
        """Test gathering with metadata preservation."""
        with patch(
            "YSimulator.YClient.llm_utils.batch_handler.ray.get",
            return_value=["result1", "result2"],
        ):
            handler = BatchHandler(logger=self.mock_logger)
            futures_with_meta = [
                (Mock(), {"agent_id": "a1", "cluster": 1}),
                (Mock(), {"agent_id": "a2", "cluster": 2}),
            ]

            results = handler.gather_with_metadata(futures_with_meta)

            self.assertEqual(len(results), 2)
            self.assertEqual(results[0], ("result1", {"agent_id": "a1", "cluster": 1}))
            self.assertEqual(results[1], ("result2", {"agent_id": "a2", "cluster": 2}))


class TestRetryHandler(unittest.TestCase):
    """Test RetryHandler functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_logger = MagicMock(spec=logging.Logger)

    def test_initialization(self):
        """Test RetryHandler initialization."""
        handler = RetryHandler(
            max_retries=3,
            initial_delay=1.0,
            backoff_factor=2.0,
            logger=self.mock_logger,
        )
        self.assertEqual(handler.max_retries, 3)
        self.assertEqual(handler.initial_delay, 1.0)
        self.assertEqual(handler.backoff_factor, 2.0)

    def test_retry_with_backoff_success(self):
        """Test successful retry."""
        handler = RetryHandler(max_retries=3, logger=self.mock_logger)

        mock_func = Mock(return_value="success")
        result = handler.retry_with_backoff(mock_func, error_message="test")

        self.assertEqual(result, "success")
        mock_func.assert_called_once()

    def test_retry_with_backoff_eventual_success(self):
        """Test retry that succeeds after failures."""
        handler = RetryHandler(max_retries=3, initial_delay=0.01, logger=self.mock_logger)

        # Fail twice, then succeed
        mock_func = Mock(side_effect=[Exception("Error 1"), Exception("Error 2"), "success"])

        result = handler.retry_with_backoff(mock_func, error_message="test")

        self.assertEqual(result, "success")
        self.assertEqual(mock_func.call_count, 3)

    def test_is_retryable_error(self):
        """Test retryable error detection."""
        handler = RetryHandler(logger=self.mock_logger)

        # Test retryable errors
        self.assertTrue(handler.is_retryable_error(ConnectionError()))
        self.assertTrue(handler.is_retryable_error(TimeoutError()))

        # Test non-retryable errors
        self.assertFalse(handler.is_retryable_error(ValueError()))
        self.assertFalse(handler.is_retryable_error(KeyError()))


class TestResponseParser(unittest.TestCase):
    """Test ResponseParser functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_logger = MagicMock(spec=logging.Logger)

    def test_initialization(self):
        """Test ResponseParser initialization."""
        parser = ResponseParser(logger=self.mock_logger)
        self.assertEqual(parser.logger, self.mock_logger)

    def test_parse_text_response_valid(self):
        """Test parsing valid text response."""
        parser = ResponseParser(logger=self.mock_logger)

        result = parser.parse_text_response("Hello world")
        self.assertEqual(result, "Hello world")

    def test_parse_text_response_none(self):
        """Test parsing None response."""
        parser = ResponseParser(logger=self.mock_logger)

        result = parser.parse_text_response(None, default="default text")
        self.assertEqual(result, "default text")

    def test_parse_text_response_empty(self):
        """Test parsing empty text."""
        parser = ResponseParser(logger=self.mock_logger)

        result = parser.parse_text_response("   ", default="default")
        self.assertEqual(result, "default")

    def test_parse_text_response_truncate(self):
        """Test text truncation."""
        parser = ResponseParser(logger=self.mock_logger)

        long_text = "a" * 100
        result = parser.parse_text_response(long_text, max_length=50)
        self.assertEqual(len(result), 50)

    def test_parse_boolean_response_bool(self):
        """Test parsing boolean response."""
        parser = ResponseParser(logger=self.mock_logger)

        self.assertTrue(parser.parse_boolean_response(True))
        self.assertFalse(parser.parse_boolean_response(False))

    def test_parse_boolean_response_string(self):
        """Test parsing string to boolean."""
        parser = ResponseParser(logger=self.mock_logger)

        self.assertTrue(parser.parse_boolean_response("true"))
        self.assertTrue(parser.parse_boolean_response("yes"))
        self.assertFalse(parser.parse_boolean_response("false"))
        self.assertFalse(parser.parse_boolean_response("no"))

    def test_parse_list_response_valid(self):
        """Test parsing valid list."""
        parser = ResponseParser(logger=self.mock_logger)

        result = parser.parse_list_response([1, 2, 3])
        self.assertEqual(result, [1, 2, 3])

    def test_parse_list_response_invalid(self):
        """Test parsing invalid list."""
        parser = ResponseParser(logger=self.mock_logger)

        result = parser.parse_list_response("not a list", default=[])
        self.assertEqual(result, [])

    def test_parse_dict_response_valid(self):
        """Test parsing valid dict."""
        parser = ResponseParser(logger=self.mock_logger)

        result = parser.parse_dict_response({"key": "value"})
        self.assertEqual(result, {"key": "value"})

    def test_parse_emotion_response_valid(self):
        """Test parsing valid emotion."""
        parser = ResponseParser(logger=self.mock_logger)

        self.assertEqual(parser.parse_emotion_response("joy"), "joy")
        self.assertEqual(parser.parse_emotion_response("anger"), "anger")
        self.assertEqual(parser.parse_emotion_response("neutral"), "neutral")

    def test_parse_emotion_response_invalid(self):
        """Test parsing invalid emotion."""
        parser = ResponseParser(logger=self.mock_logger)

        result = parser.parse_emotion_response("invalid_emotion")
        self.assertIsNone(result)

    def test_sanitize_text(self):
        """Test text sanitization."""
        parser = ResponseParser(logger=self.mock_logger)

        dirty_text = "  Hello   <b>world</b>  "
        clean_text = parser.sanitize_text(dirty_text, remove_html=True)
        self.assertEqual(clean_text, "Hello world")


class TestCostTracker(unittest.TestCase):
    """Test CostTracker functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_logger = MagicMock(spec=logging.Logger)

    def test_initialization(self):
        """Test CostTracker initialization."""
        tracker = CostTracker(logger=self.mock_logger)
        self.assertEqual(tracker.logger, self.mock_logger)
        self.assertEqual(len(tracker.call_counts), 0)

    def test_record_call(self):
        """Test recording a call."""
        tracker = CostTracker(logger=self.mock_logger)

        tracker.record_call("generate_post", input_tokens=10, output_tokens=20)

        self.assertEqual(tracker.get_call_count("generate_post"), 1)
        self.assertEqual(tracker.get_token_count("generate_post"), 30)

    def test_get_call_count(self):
        """Test getting call counts."""
        tracker = CostTracker(logger=self.mock_logger)

        tracker.record_call("generate_post", input_tokens=10, output_tokens=20)
        tracker.record_call("generate_post", input_tokens=15, output_tokens=25)
        tracker.record_call("generate_comment", input_tokens=5, output_tokens=10)

        self.assertEqual(tracker.get_call_count("generate_post"), 2)
        self.assertEqual(tracker.get_call_count("generate_comment"), 1)
        self.assertEqual(tracker.get_call_count(), 3)  # Total

    def test_get_estimated_cost(self):
        """Test cost estimation."""
        token_costs = {
            "generate_post": 0.002,  # $0.002 per 1K tokens
            "generate_comment": 0.001,
        }
        tracker = CostTracker(token_costs=token_costs, logger=self.mock_logger)

        tracker.record_call("generate_post", input_tokens=1000, output_tokens=500)

        # 1500 tokens * $0.002 / 1000 = $0.003
        cost = tracker.get_estimated_cost("generate_post")
        self.assertLess(abs(cost - 0.003), 0.0001)

    def test_get_summary(self):
        """Test getting usage summary."""
        tracker = CostTracker(logger=self.mock_logger)

        tracker.record_call("generate_post", input_tokens=100, output_tokens=200)
        tracker.record_call("generate_comment", input_tokens=50, output_tokens=100)

        summary = tracker.get_summary()

        self.assertEqual(summary["total_calls"], 2)
        self.assertEqual(summary["total_tokens"], 450)
        self.assertIn("by_method", summary)
        self.assertIn("generate_post", summary["by_method"])
        self.assertIn("generate_comment", summary["by_method"])

    def test_reset(self):
        """Test resetting tracker."""
        tracker = CostTracker(logger=self.mock_logger)

        tracker.record_call("generate_post", input_tokens=100, output_tokens=200)
        self.assertEqual(tracker.get_call_count(), 1)

        tracker.reset()
        self.assertEqual(tracker.get_call_count(), 0)
        self.assertEqual(tracker.get_token_count(), 0)


if __name__ == "__main__":
    unittest.main()
