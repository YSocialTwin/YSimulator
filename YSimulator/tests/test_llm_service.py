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
from unittest.mock import MagicMock, Mock, patch

import pytest

from YSimulator.YClient.llm_utils import (
    LLMManager,
    BatchHandler,
    RetryHandler,
    ResponseParser,
    CostTracker,
)


@pytest.fixture
def mock_logger():
    """Create a mock logger."""
    return MagicMock(spec=logging.Logger)


@pytest.fixture
def mock_llm():
    """Create a mock LLM actor handle."""
    llm = MagicMock()
    llm.generate_post = MagicMock()
    llm.generate_comment = MagicMock()
    llm.decide_follow = MagicMock()
    return llm


class TestLLMManager:
    """Test LLMManager functionality."""

    def test_initialization(self, mock_llm, mock_logger):
        """Test LLMManager initialization."""
        manager = LLMManager(mock_llm, logger=mock_logger)
        assert manager.llm == mock_llm
        assert manager.logger == mock_logger

    def test_is_available(self, mock_llm):
        """Test LLM availability check."""
        manager = LLMManager(mock_llm)
        assert manager.is_available() is True

        manager_none = LLMManager(None)
        assert manager_none.is_available() is False

    def test_generate_post(self, mock_llm, mock_logger):
        """Test generate_post method."""
        manager = LLMManager(mock_llm, logger=mock_logger)
        
        future = manager.generate_post(1, {"name": "Alice"}, "technology")
        
        mock_llm.generate_post.remote.assert_called_once_with(1, {"name": "Alice"}, "technology")
        assert future is not None

    def test_generate_comment(self, mock_llm):
        """Test generate_comment method."""
        manager = LLMManager(mock_llm)
        
        future = manager.generate_comment(
            1, "Great post!", {"name": "Bob"}, "Alice", "Previous context"
        )
        
        mock_llm.generate_comment.remote.assert_called_once()
        assert future is not None


class TestBatchHandler:
    """Test BatchHandler functionality."""

    def test_initialization(self, mock_logger):
        """Test BatchHandler initialization."""
        handler = BatchHandler(logger=mock_logger)
        assert handler.logger == mock_logger

    @patch('YSimulator.YClient.llm_service.batch_handler.ray.get')
    def test_gather_futures_success(self, mock_ray_get, mock_logger):
        """Test successful future gathering."""
        mock_ray_get.return_value = ["result1", "result2", "result3"]
        
        handler = BatchHandler(logger=mock_logger)
        futures = [Mock(), Mock(), Mock()]
        
        results = handler.gather_futures(futures)
        
        assert len(results) == 3
        assert results == ["result1", "result2", "result3"]
        mock_ray_get.assert_called_once_with(futures)

    def test_gather_futures_empty(self, mock_logger):
        """Test gathering empty list."""
        handler = BatchHandler(logger=mock_logger)
        results = handler.gather_futures([])
        assert results == []

    @patch('YSimulator.YClient.llm_service.batch_handler.ray.get')
    def test_gather_futures_error(self, mock_ray_get, mock_logger):
        """Test future gathering with error."""
        mock_ray_get.side_effect = Exception("Ray error")
        
        handler = BatchHandler(logger=mock_logger)
        futures = [Mock(), Mock()]
        
        results = handler.gather_futures(futures)
        
        # Should return None for each future on error
        assert results == [None, None]

    @patch('YSimulator.YClient.llm_service.batch_handler.ray.get')
    def test_gather_with_metadata(self, mock_ray_get, mock_logger):
        """Test gathering with metadata preservation."""
        mock_ray_get.return_value = ["result1", "result2"]
        
        handler = BatchHandler(logger=mock_logger)
        futures_with_meta = [
            (Mock(), {"agent_id": "a1", "cluster": 1}),
            (Mock(), {"agent_id": "a2", "cluster": 2}),
        ]
        
        results = handler.gather_with_metadata(futures_with_meta)
        
        assert len(results) == 2
        assert results[0] == ("result1", {"agent_id": "a1", "cluster": 1})
        assert results[1] == ("result2", {"agent_id": "a2", "cluster": 2})


class TestRetryHandler:
    """Test RetryHandler functionality."""

    def test_initialization(self, mock_logger):
        """Test RetryHandler initialization."""
        handler = RetryHandler(
            max_retries=3,
            initial_delay=1.0,
            backoff_factor=2.0,
            logger=mock_logger,
        )
        assert handler.max_retries == 3
        assert handler.initial_delay == 1.0
        assert handler.backoff_factor == 2.0

    def test_retry_with_backoff_success(self, mock_logger):
        """Test successful retry."""
        handler = RetryHandler(max_retries=3, logger=mock_logger)
        
        mock_func = Mock(return_value="success")
        result = handler.retry_with_backoff(mock_func, error_message="test")
        
        assert result == "success"
        mock_func.assert_called_once()

    def test_retry_with_backoff_eventual_success(self, mock_logger):
        """Test retry that succeeds after failures."""
        handler = RetryHandler(max_retries=3, initial_delay=0.01, logger=mock_logger)
        
        # Fail twice, then succeed
        mock_func = Mock(side_effect=[Exception("Error 1"), Exception("Error 2"), "success"])
        
        result = handler.retry_with_backoff(mock_func, error_message="test")
        
        assert result == "success"
        assert mock_func.call_count == 3

    def test_is_retryable_error(self, mock_logger):
        """Test retryable error detection."""
        handler = RetryHandler(logger=mock_logger)
        
        # Test retryable errors
        assert handler.is_retryable_error(ConnectionError()) is True
        assert handler.is_retryable_error(TimeoutError()) is True
        
        # Test non-retryable errors
        assert handler.is_retryable_error(ValueError()) is False
        assert handler.is_retryable_error(KeyError()) is False


class TestResponseParser:
    """Test ResponseParser functionality."""

    def test_initialization(self, mock_logger):
        """Test ResponseParser initialization."""
        parser = ResponseParser(logger=mock_logger)
        assert parser.logger == mock_logger

    def test_parse_text_response_valid(self, mock_logger):
        """Test parsing valid text response."""
        parser = ResponseParser(logger=mock_logger)
        
        result = parser.parse_text_response("Hello world")
        assert result == "Hello world"

    def test_parse_text_response_none(self, mock_logger):
        """Test parsing None response."""
        parser = ResponseParser(logger=mock_logger)
        
        result = parser.parse_text_response(None, default="default text")
        assert result == "default text"

    def test_parse_text_response_empty(self, mock_logger):
        """Test parsing empty text."""
        parser = ResponseParser(logger=mock_logger)
        
        result = parser.parse_text_response("   ", default="default")
        assert result == "default"

    def test_parse_text_response_truncate(self, mock_logger):
        """Test text truncation."""
        parser = ResponseParser(logger=mock_logger)
        
        long_text = "a" * 100
        result = parser.parse_text_response(long_text, max_length=50)
        assert len(result) == 50

    def test_parse_boolean_response_bool(self, mock_logger):
        """Test parsing boolean response."""
        parser = ResponseParser(logger=mock_logger)
        
        assert parser.parse_boolean_response(True) is True
        assert parser.parse_boolean_response(False) is False

    def test_parse_boolean_response_string(self, mock_logger):
        """Test parsing string to boolean."""
        parser = ResponseParser(logger=mock_logger)
        
        assert parser.parse_boolean_response("true") is True
        assert parser.parse_boolean_response("yes") is True
        assert parser.parse_boolean_response("false") is False
        assert parser.parse_boolean_response("no") is False

    def test_parse_list_response_valid(self, mock_logger):
        """Test parsing valid list."""
        parser = ResponseParser(logger=mock_logger)
        
        result = parser.parse_list_response([1, 2, 3])
        assert result == [1, 2, 3]

    def test_parse_list_response_invalid(self, mock_logger):
        """Test parsing invalid list."""
        parser = ResponseParser(logger=mock_logger)
        
        result = parser.parse_list_response("not a list", default=[])
        assert result == []

    def test_parse_dict_response_valid(self, mock_logger):
        """Test parsing valid dict."""
        parser = ResponseParser(logger=mock_logger)
        
        result = parser.parse_dict_response({"key": "value"})
        assert result == {"key": "value"}

    def test_parse_emotion_response_valid(self, mock_logger):
        """Test parsing valid emotion."""
        parser = ResponseParser(logger=mock_logger)
        
        assert parser.parse_emotion_response("joy") == "joy"
        assert parser.parse_emotion_response("anger") == "anger"
        assert parser.parse_emotion_response("neutral") == "neutral"

    def test_parse_emotion_response_invalid(self, mock_logger):
        """Test parsing invalid emotion."""
        parser = ResponseParser(logger=mock_logger)
        
        result = parser.parse_emotion_response("invalid_emotion")
        assert result is None

    def test_sanitize_text(self, mock_logger):
        """Test text sanitization."""
        parser = ResponseParser(logger=mock_logger)
        
        dirty_text = "  Hello   <b>world</b>  "
        clean_text = parser.sanitize_text(dirty_text, remove_html=True)
        assert clean_text == "Hello world"


class TestCostTracker:
    """Test CostTracker functionality."""

    def test_initialization(self, mock_logger):
        """Test CostTracker initialization."""
        tracker = CostTracker(logger=mock_logger)
        assert tracker.logger == mock_logger
        assert len(tracker.call_counts) == 0

    def test_record_call(self, mock_logger):
        """Test recording a call."""
        tracker = CostTracker(logger=mock_logger)
        
        tracker.record_call("generate_post", input_tokens=10, output_tokens=20)
        
        assert tracker.get_call_count("generate_post") == 1
        assert tracker.get_token_count("generate_post") == 30

    def test_get_call_count(self, mock_logger):
        """Test getting call counts."""
        tracker = CostTracker(logger=mock_logger)
        
        tracker.record_call("generate_post", input_tokens=10, output_tokens=20)
        tracker.record_call("generate_post", input_tokens=15, output_tokens=25)
        tracker.record_call("generate_comment", input_tokens=5, output_tokens=10)
        
        assert tracker.get_call_count("generate_post") == 2
        assert tracker.get_call_count("generate_comment") == 1
        assert tracker.get_call_count() == 3  # Total

    def test_get_estimated_cost(self, mock_logger):
        """Test cost estimation."""
        token_costs = {
            "generate_post": 0.002,  # $0.002 per 1K tokens
            "generate_comment": 0.001,
        }
        tracker = CostTracker(token_costs=token_costs, logger=mock_logger)
        
        tracker.record_call("generate_post", input_tokens=1000, output_tokens=500)
        
        # 1500 tokens * $0.002 / 1000 = $0.003
        cost = tracker.get_estimated_cost("generate_post")
        assert abs(cost - 0.003) < 0.0001

    def test_get_summary(self, mock_logger):
        """Test getting usage summary."""
        tracker = CostTracker(logger=mock_logger)
        
        tracker.record_call("generate_post", input_tokens=100, output_tokens=200)
        tracker.record_call("generate_comment", input_tokens=50, output_tokens=100)
        
        summary = tracker.get_summary()
        
        assert summary["total_calls"] == 2
        assert summary["total_tokens"] == 450
        assert "by_method" in summary
        assert "generate_post" in summary["by_method"]
        assert "generate_comment" in summary["by_method"]

    def test_reset(self, mock_logger):
        """Test resetting tracker."""
        tracker = CostTracker(logger=mock_logger)
        
        tracker.record_call("generate_post", input_tokens=100, output_tokens=200)
        assert tracker.get_call_count() == 1
        
        tracker.reset()
        assert tracker.get_call_count() == 0
        assert tracker.get_token_count() == 0
