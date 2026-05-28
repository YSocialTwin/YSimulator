"""
Test text annotation functionality for posts and comments.

This test verifies that:
1. Hashtags are extracted correctly
2. User mentions are extracted correctly
3. Sentiment analysis works
4. Database methods for annotations work correctly
"""

from YSimulator.YClient.text_support.cleaning import extract_components
from YSimulator.YClient.text_support.text_annotator import annotate_text


def test_extract_hashtags():
    """Test hashtag extraction from text."""
    text = "This is a #test post with #multiple #hashtags"
    hashtags = extract_components(text, c_type="hashtags")

    assert len(hashtags) == 3
    assert "#test" in hashtags
    assert "#multiple" in hashtags
    assert "#hashtags" in hashtags


def test_extract_mentions():
    """Test user mention extraction from text."""
    text = "Hello @user1 and @user2, how are you?"
    mentions = extract_components(text, c_type="mentions")

    assert len(mentions) == 2
    assert "@user1" in mentions
    assert "@user2" in mentions


def test_annotate_text_basic():
    """Test basic text annotation with hashtags and mentions."""
    text = "Great post about #AI by @researcher! #machinelearning"

    annotations = annotate_text(
        text, enable_sentiment=True, enable_toxicity=False, perspective_api_key=None
    )

    # Check hashtags (without # prefix)
    assert "hashtags" in annotations
    assert len(annotations["hashtags"]) == 2
    assert "AI" in annotations["hashtags"]
    assert "machinelearning" in annotations["hashtags"]

    # Check mentions (without @ prefix)
    assert "mentions" in annotations
    assert len(annotations["mentions"]) == 1
    assert "researcher" in annotations["mentions"]

    # Check sentiment (should be computed)
    assert "sentiment" in annotations
    assert annotations["sentiment"] is not None
    assert "compound" in annotations["sentiment"]
    assert "pos" in annotations["sentiment"]
    assert "neg" in annotations["sentiment"]
    assert "neu" in annotations["sentiment"]


def test_sentiment_scores():
    """Test sentiment analysis on different types of text."""
    # Positive text
    positive_text = "I love this amazing product! It's wonderful and fantastic!"
    pos_annotations = annotate_text(positive_text, enable_sentiment=True)
    assert pos_annotations["sentiment"]["compound"] > 0.5

    # Negative text
    negative_text = "This is terrible and awful. I hate it so much!"
    neg_annotations = annotate_text(negative_text, enable_sentiment=True)
    assert neg_annotations["sentiment"]["compound"] < -0.5

    # Neutral text
    neutral_text = "The sky is blue. Water is wet."
    neu_annotations = annotate_text(neutral_text, enable_sentiment=True)
    assert abs(neu_annotations["sentiment"]["compound"]) < 0.3


def test_annotate_text_no_sentiment():
    """Test annotation with sentiment disabled."""
    text = "Test post #hashtag @user"

    annotations = annotate_text(
        text, enable_sentiment=False, enable_toxicity=False, perspective_api_key=None
    )

    assert annotations["sentiment"] is None
    assert annotations["toxicity"] is None
    assert len(annotations["hashtags"]) == 1
    assert len(annotations["mentions"]) == 1


def test_annotate_text_empty():
    """Test annotation of empty or simple text."""
    text = "Simple post without any special content"

    annotations = annotate_text(
        text, enable_sentiment=True, enable_toxicity=False, perspective_api_key=None
    )

    assert len(annotations["hashtags"]) == 0
    assert len(annotations["mentions"]) == 0
    assert annotations["sentiment"] is not None


def test_annotate_text_toxicity_empty_api_key_uses_detoxify(monkeypatch):
    monkeypatch.setattr(
        "YSimulator.YClient.text_support.annotations._get_detoxify_model",
        lambda: type(
            "FakeDetoxify",
            (),
            {
                "predict": lambda self, text: {
                    "toxicity": 0.05,
                    "severe_toxicity": 0.01,
                    "identity_attack": 0.01,
                    "insult": 0.02,
                    "obscene": 0.01,
                    "threat": 0.01,
                    "sexual_explicit": 0.01,
                }
            },
        )(),
    )

    annotations = annotate_text(
        "Test text",
        enable_sentiment=False,
        enable_toxicity=True,
        perspective_api_key="",
    )

    assert annotations["toxicity"] is not None
    assert "TOXICITY" in annotations["toxicity"]


def test_multiple_hashtags_and_mentions():
    """Test text with many hashtags and mentions."""
    text = "#first #second #third post mentioning @user1 @user2 @user3 and more #tags"

    annotations = annotate_text(text, enable_sentiment=True)

    assert len(annotations["hashtags"]) == 4
    assert "first" in annotations["hashtags"]
    assert "second" in annotations["hashtags"]
    assert "third" in annotations["hashtags"]
    assert "tags" in annotations["hashtags"]

    assert len(annotations["mentions"]) == 3
    assert "user1" in annotations["mentions"]
    assert "user2" in annotations["mentions"]
    assert "user3" in annotations["mentions"]


if __name__ == "__main__":
    # Run basic tests manually
    print("Testing hashtag extraction...")
    test_extract_hashtags()
    print("✓ Hashtag extraction works")

    print("\nTesting mention extraction...")
    test_extract_mentions()
    print("✓ Mention extraction works")

    print("\nTesting basic annotation...")
    test_annotate_text_basic()
    print("✓ Basic annotation works")

    print("\nTesting sentiment scores...")
    test_sentiment_scores()
    print("✓ Sentiment analysis works")

    print("\nAll tests passed!")
