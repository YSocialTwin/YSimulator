"""
Comprehensive test suite for text processing modules.
Target: 80%+ coverage for text_support package.

Tests cover:
- Text cleaning (cleaning.py)
- Text annotations (annotations.py) 
- Text annotator integration (text_annotator.py)
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from YSimulator.YClient.text_support.cleaning import clean_text, extract_components
from YSimulator.YClient.text_support.annotations import vader_sentiment, toxicity
from YSimulator.YClient.text_support.text_annotator import (
    annotate_text,
    prepare_sentiment_data,
    prepare_toxicity_data,
)


class TestTextCleaning:
    """Test suite for text cleaning functionality."""

    def test_clean_text_basic(self):
        """Test basic text cleaning."""
        result = clean_text("john", "Hello world!")
        assert result == "Hello world!"

    def test_clean_text_remove_dashes(self):
        """Test dash removal."""
        result = clean_text("user", "Hello-world-test")
        assert result == "Helloworldtest"

    def test_clean_text_remove_at_symbol(self):
        """Test @ symbol handling."""
        result = clean_text("user", "Hello @ world")
        assert result == "Hello world"  # Double space removed too

    def test_clean_text_remove_double_spaces(self):
        """Test double space normalization."""
        result = clean_text("user", "Hello  world  test")
        assert result == "Hello world test"

    def test_clean_text_remove_dot_spaces(self):
        """Test dot-space normalization."""
        result = clean_text("user", "Hello. world. test.")
        assert result == "Hello.world.test."

    def test_clean_text_remove_comma_spaces(self):
        """Test comma-space normalization."""
        result = clean_text("user", "Hello ,world ,test")
        assert result == "Hello,world,test"

    def test_clean_text_remove_brackets(self):
        """Test bracket removal."""
        result = clean_text("user", "[Hello] world [test]")
        assert result == "Hello world test"

    def test_clean_text_remove_at_comma(self):
        """Test @, pattern removal."""
        result = clean_text("user", "Hello @,world")
        assert result == "Hello world"

    def test_clean_text_remove_quotes(self):
        """Test quote removal."""
        result = clean_text("user", "\"Hello\" 'world'")
        assert result == "Hello world"

    def test_clean_text_strip_parentheses(self):
        """Test stripping of parentheses."""
        result = clean_text("user", "(Hello world)")
        assert result == "Hello world"

    def test_clean_text_remove_self_mention(self):
        """Test author self-mention removal."""
        result = clean_text("john", "Hey @john, how are you?")
        assert "@john" not in result

    def test_clean_text_preserve_other_mentions(self):
        """Test that other mentions are preserved."""
        result = clean_text("john", "Hey @jane, check this out!")
        assert "@jane" in result

    def test_clean_text_empty_string(self):
        """Test cleaning of empty string."""
        result = clean_text("user", "")
        assert result == ""

    def test_clean_text_only_whitespace(self):
        """Test cleaning of whitespace-only string."""
        result = clean_text("user", "   ")
        assert result == ""

    def test_clean_text_complex_combination(self):
        """Test complex cleaning with multiple transformations."""
        text = '[Hello-world] @john "test" @,jane. Check ,this (out)'
        result = clean_text("john", text)
        assert "Hello" in result
        assert "@john" not in result
        assert "-" not in result
        assert "[" not in result
        assert "]" not in result


class TestExtractComponents:
    """Test suite for component extraction."""

    def test_extract_hashtags_single(self):
        """Test single hashtag extraction."""
        result = extract_components("Hello #world", c_type="hashtags")
        assert result == ["#world"]

    def test_extract_hashtags_multiple(self):
        """Test multiple hashtag extraction."""
        result = extract_components("Hello #world #test #python", c_type="hashtags")
        assert result == ["#world", "#test", "#python"]

    def test_extract_hashtags_none(self):
        """Test hashtag extraction with no hashtags."""
        result = extract_components("Hello world", c_type="hashtags")
        assert result == []

    def test_extract_hashtags_with_numbers(self):
        """Test hashtag extraction with numbers."""
        result = extract_components("Check #python3 and #test123", c_type="hashtags")
        assert result == ["#python3", "#test123"]

    def test_extract_hashtags_with_underscores(self):
        """Test hashtag extraction with underscores."""
        result = extract_components("Use #test_case and #foo_bar", c_type="hashtags")
        assert result == ["#test_case", "#foo_bar"]

    def test_extract_mentions_single(self):
        """Test single mention extraction."""
        result = extract_components("Hello @john", c_type="mentions")
        assert result == ["@john"]

    def test_extract_mentions_multiple(self):
        """Test multiple mention extraction."""
        result = extract_components("Hey @john @jane @bob", c_type="mentions")
        assert result == ["@john", "@jane", "@bob"]

    def test_extract_mentions_none(self):
        """Test mention extraction with no mentions."""
        result = extract_components("Hello world", c_type="mentions")
        assert result == []

    def test_extract_mentions_with_numbers(self):
        """Test mention extraction with numbers."""
        result = extract_components("Contact @user123 and @admin99", c_type="mentions")
        assert result == ["@user123", "@admin99"]

    def test_extract_components_invalid_type(self):
        """Test extraction with invalid component type."""
        result = extract_components("Hello world", c_type="invalid")
        assert result == []

    def test_extract_components_empty_string(self):
        """Test extraction from empty string."""
        result = extract_components("", c_type="hashtags")
        assert result == []

    def test_extract_mixed_content(self):
        """Test extraction from mixed content."""
        text = "Check #python @john and #test @jane"
        hashtags = extract_components(text, c_type="hashtags")
        mentions = extract_components(text, c_type="mentions")
        assert hashtags == ["#python", "#test"]
        assert mentions == ["@john", "@jane"]


class TestVaderSentiment:
    """Test suite for VADER sentiment analysis."""

    def test_vader_sentiment_positive(self):
        """Test positive sentiment detection."""
        result = vader_sentiment("I love this! It's amazing and wonderful!")
        assert result is not None
        assert "compound" in result
        assert result["compound"] > 0

    def test_vader_sentiment_negative(self):
        """Test negative sentiment detection."""
        result = vader_sentiment("I hate this! It's terrible and awful!")
        assert result is not None
        assert "compound" in result
        assert result["compound"] < 0

    def test_vader_sentiment_neutral(self):
        """Test neutral sentiment detection."""
        result = vader_sentiment("This is a chair.")
        assert result is not None
        assert "compound" in result
        assert abs(result["compound"]) < 0.5

    def test_vader_sentiment_keys(self):
        """Test that all expected keys are present."""
        result = vader_sentiment("Test text")
        assert "neg" in result
        assert "pos" in result
        assert "neu" in result
        assert "compound" in result

    def test_vader_sentiment_empty_string(self):
        """Test sentiment of empty string."""
        result = vader_sentiment("")
        assert result is not None
        assert "compound" in result

    def test_vader_sentiment_whitespace_only(self):
        """Test sentiment of whitespace-only string."""
        result = vader_sentiment("   ")
        assert result is not None
        assert "compound" in result

    def test_vader_sentiment_mixed_emotions(self):
        """Test sentiment with mixed emotions."""
        result = vader_sentiment("I love the idea but hate the execution")
        assert result is not None
        assert "compound" in result

    def test_vader_sentiment_exclamations(self):
        """Test sentiment with exclamations."""
        result = vader_sentiment("This is great!!!")
        assert result is not None
        assert result["compound"] > 0

    def test_vader_sentiment_all_caps(self):
        """Test sentiment with all caps."""
        result = vader_sentiment("LOVE THIS!")
        assert result is not None
        assert result["compound"] > 0


class TestToxicity:
    """Test suite for toxicity analysis."""

    def test_toxicity_no_api_key(self):
        """Test toxicity with no API key."""
        result = toxicity("Test text", api_key=None)
        assert result == {}

    @patch("YSimulator.YClient.text_support.annotations.PerspectiveAPI")
    def test_toxicity_with_api_key_success(self, mock_perspective):
        """Test successful toxicity analysis."""
        mock_api = MagicMock()
        mock_api.score.return_value = {
            "TOXICITY": 0.1,
            "SEVERE_TOXICITY": 0.05,
            "IDENTITY_ATTACK": 0.02,
            "INSULT": 0.03,
            "PROFANITY": 0.01,
            "THREAT": 0.01,
            "SEXUALLY_EXPLICIT": 0.02,
            "FLIRTATION": 0.15,
        }
        mock_perspective.return_value = mock_api

        result = toxicity("Test text", api_key="test_key")
        assert "TOXICITY" in result
        assert result["TOXICITY"] == 0.1
        assert "SEVERE_TOXICITY" in result
        assert "IDENTITY_ATTACK" in result
        assert "INSULT" in result
        assert "PROFANITY" in result
        assert "THREAT" in result
        assert "SEXUALLY_EXPLICIT" in result
        assert "FLIRTATION" in result

    @patch("YSimulator.YClient.text_support.annotations.PerspectiveAPI")
    def test_toxicity_exception_handling(self, mock_perspective):
        """Test toxicity exception handling."""
        mock_perspective.side_effect = Exception("API error")
        result = toxicity("Test text", api_key="test_key")
        assert result == {}

    @patch("YSimulator.YClient.text_support.annotations.PerspectiveAPI")
    def test_toxicity_empty_text(self, mock_perspective):
        """Test toxicity with empty text."""
        mock_api = MagicMock()
        mock_api.score.return_value = {
            "TOXICITY": 0.0,
            "SEVERE_TOXICITY": 0.0,
            "IDENTITY_ATTACK": 0.0,
            "INSULT": 0.0,
            "PROFANITY": 0.0,
            "THREAT": 0.0,
            "SEXUALLY_EXPLICIT": 0.0,
            "FLIRTATION": 0.0,
        }
        mock_perspective.return_value = mock_api

        result = toxicity("", api_key="test_key")
        assert isinstance(result, dict)


class TestAnnotateText:
    """Test suite for text annotation integration."""

    def test_annotate_text_default(self):
        """Test default annotation."""
        result = annotate_text("Hello #world @user")
        assert "hashtags" in result
        assert "mentions" in result
        assert "sentiment" in result
        assert "toxicity" in result
        assert "emotions" in result

    def test_annotate_text_hashtags(self):
        """Test hashtag extraction in annotation."""
        result = annotate_text("Check #python #test #coding")
        assert result["hashtags"] == ["python", "test", "coding"]

    def test_annotate_text_mentions(self):
        """Test mention extraction in annotation."""
        result = annotate_text("Hey @john @jane @bob")
        assert result["mentions"] == ["john", "jane", "bob"]

    def test_annotate_text_no_hashtags_or_mentions(self):
        """Test annotation with no hashtags or mentions."""
        result = annotate_text("Plain text without any special components")
        assert result["hashtags"] == []
        assert result["mentions"] == []

    def test_annotate_text_sentiment_enabled(self):
        """Test annotation with sentiment enabled."""
        result = annotate_text("I love this!", enable_sentiment=True)
        assert result["sentiment"] is not None
        assert "compound" in result["sentiment"]

    def test_annotate_text_sentiment_disabled(self):
        """Test annotation with sentiment disabled."""
        result = annotate_text("I love this!", enable_sentiment=False)
        assert result["sentiment"] is None

    @patch("YSimulator.YClient.text_support.annotations.PerspectiveAPI")
    def test_annotate_text_toxicity_enabled(self, mock_perspective):
        """Test annotation with toxicity enabled."""
        mock_api = MagicMock()
        mock_api.score.return_value = {
            "TOXICITY": 0.1,
            "SEVERE_TOXICITY": 0.05,
            "IDENTITY_ATTACK": 0.02,
            "INSULT": 0.03,
            "PROFANITY": 0.01,
            "THREAT": 0.01,
            "SEXUALLY_EXPLICIT": 0.02,
            "FLIRTATION": 0.15,
        }
        mock_perspective.return_value = mock_api

        result = annotate_text("Test text", enable_toxicity=True, perspective_api_key="test_key")
        assert result["toxicity"] is not None
        assert "TOXICITY" in result["toxicity"]

    def test_annotate_text_toxicity_disabled(self):
        """Test annotation with toxicity disabled."""
        result = annotate_text("Test text", enable_toxicity=False)
        assert result["toxicity"] is None

    def test_annotate_text_toxicity_no_api_key(self):
        """Test annotation with toxicity enabled but no API key."""
        result = annotate_text("Test text", enable_toxicity=True, perspective_api_key=None)
        assert result["toxicity"] is None

    def test_annotate_text_emotions_enabled(self):
        """Test annotation with emotions enabled."""
        with patch("ray.get") as mock_ray_get:
            mock_llm = MagicMock()
            mock_ray_get.return_value = ["joy", "excitement"]

            result = annotate_text("I'm so happy!", enable_emotions=True, llm_handle=mock_llm)
            assert result["emotions"] == ["joy", "excitement"]

    def test_annotate_text_emotions_disabled(self):
        """Test annotation with emotions disabled."""
        result = annotate_text("I'm so happy!", enable_emotions=False)
        assert result["emotions"] is None

    def test_annotate_text_emotions_no_llm_handle(self):
        """Test annotation with emotions enabled but no LLM handle."""
        result = annotate_text("I'm so happy!", enable_emotions=True, llm_handle=None)
        assert result["emotions"] is None

    def test_annotate_text_emotions_exception(self):
        """Test annotation with emotions when LLM fails."""
        with patch("ray.get") as mock_ray_get:
            mock_llm = MagicMock()
            mock_ray_get.side_effect = Exception("LLM error")

            result = annotate_text("Test text", enable_emotions=True, llm_handle=mock_llm)
            assert result["emotions"] == []

    def test_annotate_text_emotions_empty_result(self):
        """Test annotation when LLM returns empty emotions."""
        with patch("ray.get") as mock_ray_get:
            mock_llm = MagicMock()
            mock_ray_get.return_value = None

            result = annotate_text("Test text", enable_emotions=True, llm_handle=mock_llm)
            assert result["emotions"] == []

    def test_annotate_text_complex(self):
        """Test complex annotation with multiple features."""
        text = "I love #python! @john check this out!"
        result = annotate_text(text, enable_sentiment=True)

        assert result["hashtags"] == ["python"]
        assert result["mentions"] == ["john"]
        assert result["sentiment"] is not None
        assert result["sentiment"]["compound"] > 0


class TestPrepareSentimentData:
    """Test suite for sentiment data preparation."""

    def test_prepare_sentiment_data_single_topic(self):
        """Test sentiment data preparation for single topic."""
        sentiment_scores = {"neg": 0.1, "pos": 0.7, "neu": 0.2, "compound": 0.8}
        result = prepare_sentiment_data(
            post_id="post1",
            user_id="user1",
            topic_ids=["topic1"],
            round_id="round1",
            sentiment_scores=sentiment_scores,
            is_post=True,
        )

        assert len(result) == 1
        assert result[0]["post_id"] == "post1"
        assert result[0]["user_id"] == "user1"
        assert result[0]["topic_id"] == "topic1"
        assert result[0]["round"] == "round1"
        assert result[0]["neg"] == 0.1
        assert result[0]["pos"] == 0.7
        assert result[0]["neu"] == 0.2
        assert result[0]["compound"] == 0.8
        assert result[0]["is_post"] == 1
        assert result[0]["is_comment"] == 0
        assert result[0]["is_reaction"] == 0

    def test_prepare_sentiment_data_multiple_topics(self):
        """Test sentiment data preparation for multiple topics."""
        sentiment_scores = {"neg": 0.1, "pos": 0.7, "neu": 0.2, "compound": 0.8}
        result = prepare_sentiment_data(
            post_id="post1",
            user_id="user1",
            topic_ids=["topic1", "topic2", "topic3"],
            round_id="round1",
            sentiment_scores=sentiment_scores,
            is_post=True,
        )

        assert len(result) == 3
        assert all(entry["post_id"] == "post1" for entry in result)
        assert [entry["topic_id"] for entry in result] == ["topic1", "topic2", "topic3"]

    def test_prepare_sentiment_data_comment(self):
        """Test sentiment data preparation for comment."""
        sentiment_scores = {"neg": 0.1, "pos": 0.7, "neu": 0.2, "compound": 0.8}
        result = prepare_sentiment_data(
            post_id="comment1",
            user_id="user1",
            topic_ids=["topic1"],
            round_id="round1",
            sentiment_scores=sentiment_scores,
            sentiment_parent=0.5,
            is_comment=True,
        )

        assert result[0]["is_comment"] == 1
        assert result[0]["is_post"] == 0
        assert result[0]["is_reaction"] == 0
        assert result[0]["sentiment_parent"] == 0.5

    def test_prepare_sentiment_data_reaction(self):
        """Test sentiment data preparation for reaction."""
        sentiment_scores = {"neg": 0.1, "pos": 0.7, "neu": 0.2, "compound": 0.8}
        result = prepare_sentiment_data(
            post_id="reaction1",
            user_id="user1",
            topic_ids=["topic1"],
            round_id="round1",
            sentiment_scores=sentiment_scores,
            is_reaction=True,
        )

        assert result[0]["is_reaction"] == 1
        assert result[0]["is_post"] == 0
        assert result[0]["is_comment"] == 0

    def test_prepare_sentiment_data_missing_scores(self):
        """Test sentiment data preparation with missing scores."""
        sentiment_scores = {"compound": 0.8}
        result = prepare_sentiment_data(
            post_id="post1",
            user_id="user1",
            topic_ids=["topic1"],
            round_id="round1",
            sentiment_scores=sentiment_scores,
            is_post=True,
        )

        assert result[0]["neg"] is None
        assert result[0]["pos"] is None
        assert result[0]["neu"] is None
        assert result[0]["compound"] == 0.8


class TestPrepareToxicityData:
    """Test suite for toxicity data preparation."""

    def test_prepare_toxicity_data_all_scores(self):
        """Test toxicity data preparation with all scores."""
        toxicity_scores = {
            "TOXICITY": 0.1,
            "SEVERE_TOXICITY": 0.05,
            "IDENTITY_ATTACK": 0.02,
            "INSULT": 0.03,
            "PROFANITY": 0.01,
            "THREAT": 0.01,
            "SEXUALLY_EXPLICIT": 0.02,
            "FLIRTATION": 0.15,
        }
        result = prepare_toxicity_data("post1", toxicity_scores)

        assert result["post_id"] == "post1"
        assert result["toxicity"] == 0.1
        assert result["severe_toxicity"] == 0.05
        assert result["identity_attack"] == 0.02
        assert result["insult"] == 0.03
        assert result["profanity"] == 0.01
        assert result["threat"] == 0.01
        assert result["sexually_explicit"] == 0.02
        assert result["flirtation"] == 0.15

    def test_prepare_toxicity_data_missing_scores(self):
        """Test toxicity data preparation with missing scores."""
        toxicity_scores = {"TOXICITY": 0.1}
        result = prepare_toxicity_data("post1", toxicity_scores)

        assert result["post_id"] == "post1"
        assert result["toxicity"] == 0.1
        assert result["severe_toxicity"] == 0.0
        assert result["identity_attack"] == 0.0
        assert result["insult"] == 0.0
        assert result["profanity"] == 0.0
        assert result["threat"] == 0.0
        assert result["sexually_explicit"] == 0.0
        assert result["flirtation"] == 0.0

    def test_prepare_toxicity_data_empty_scores(self):
        """Test toxicity data preparation with empty scores."""
        toxicity_scores = {}
        result = prepare_toxicity_data("post1", toxicity_scores)

        assert result["post_id"] == "post1"
        assert all(result[key] == 0.0 for key in result if key != "post_id")

    def test_prepare_toxicity_data_zero_scores(self):
        """Test toxicity data preparation with zero scores."""
        toxicity_scores = {
            "TOXICITY": 0.0,
            "SEVERE_TOXICITY": 0.0,
            "IDENTITY_ATTACK": 0.0,
            "INSULT": 0.0,
            "PROFANITY": 0.0,
            "THREAT": 0.0,
            "SEXUALLY_EXPLICIT": 0.0,
            "FLIRTATION": 0.0,
        }
        result = prepare_toxicity_data("post1", toxicity_scores)

        assert all(result[key] == 0.0 for key in result if key != "post_id")
