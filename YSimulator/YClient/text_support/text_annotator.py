"""
Text annotation utilities for posts and comments.

This module provides functions to extract and annotate text content with:
- Hashtags
- User mentions
- Sentiment analysis
- Toxicity scores
- Emotions
"""

from typing import Dict, List, Optional

from YSimulator.YClient.text_support.annotations import toxicity, vader_sentiment
from YSimulator.YClient.text_support.cleaning import extract_components


def annotate_text(
    text: str,
    enable_sentiment: bool = True,
    enable_toxicity: bool = False,
    perspective_api_key: Optional[str] = None,
    enable_emotions: bool = False,
    llm_handle=None,
) -> Dict:
    """
    Annotate text with hashtags, mentions, sentiment, toxicity, and emotions.

    Uses existing methods from cleaning.py and annotations.py:
    - extract_components() for hashtags and mentions
    - vader_sentiment() for sentiment analysis
    - toxicity() for toxicity scores
    - LLM for emotion extraction (GoEmotions taxonomy)

    Args:
        text: The text to annotate
        enable_sentiment: Whether to compute sentiment (default: True)
        enable_toxicity: Whether to compute toxicity (default: False)
        perspective_api_key: API key for Perspective API toxicity analysis
        enable_emotions: Whether to extract emotions using LLM (default: False)
        llm_handle: Ray actor handle for LLM service (required if enable_emotions=True)

    Returns:
        dict: Annotations containing:
            - hashtags: List of hashtag strings (without #)
            - mentions: List of mentioned usernames (without @)
            - sentiment: Dict with neg, pos, neu, compound scores (if enabled)
            - toxicity: Dict with toxicity scores (if enabled)
            - emotions: List of emotion names from GoEmotions taxonomy (if enabled)
    """
    annotations = {}

    # Extract hashtags using existing method from cleaning.py
    # Returns list like ['#hashtag1', '#hashtag2']
    hashtags_raw = extract_components(text, c_type="hashtags")
    # Remove # prefix for storage
    annotations["hashtags"] = [h[1:] for h in hashtags_raw]

    # Extract mentions using existing method from cleaning.py
    # Returns list like ['@username1', '@username2']
    mentions_raw = extract_components(text, c_type="mentions")
    # Remove @ prefix for storage
    annotations["mentions"] = [m[1:] for m in mentions_raw]

    # Compute sentiment if enabled using existing method from annotations.py
    if enable_sentiment:
        annotations["sentiment"] = vader_sentiment(text)
    else:
        annotations["sentiment"] = None

    # Compute toxicity if enabled using existing method from annotations.py
    if enable_toxicity and perspective_api_key:
        annotations["toxicity"] = toxicity(text, perspective_api_key)
    else:
        annotations["toxicity"] = None

    # Extract emotions if enabled using LLM
    if enable_emotions and llm_handle:
        try:
            import ray

            emotions = ray.get(llm_handle.extract_emotions.remote(text))
            annotations["emotions"] = emotions if emotions else []
        except Exception:
            # If emotion extraction fails, return empty list
            annotations["emotions"] = []
    else:
        annotations["emotions"] = None

    return annotations


def prepare_sentiment_data(
    post_id: str,
    user_id: str,
    topic_ids: List[str],
    round_id: str,
    sentiment_scores: Dict[str, float],
    sentiment_parent: Optional[str] = None,
    is_post: bool = False,
    is_comment: bool = False,
    is_reaction: bool = False,
) -> List[Dict]:
    """
    Prepare sentiment data for database insertion.

    Creates one entry per topic associated with the post/comment.

    Args:
        post_id: UUID of the post/comment
        user_id: UUID of the user
        topic_ids: List of topic UUIDs
        round_id: UUID of the current round
        sentiment_scores: Dict with 'neg', 'pos', 'neu', 'compound' keys
        sentiment_parent: Compound sentiment of parent post (for comments)
        is_post: Flag indicating this is a post
        is_comment: Flag indicating this is a comment
        is_reaction: Flag indicating this is a reaction

    Returns:
        List of dicts ready for database insertion
    """
    sentiment_entries = []

    for topic_id in topic_ids:
        entry = {
            "post_id": post_id,
            "user_id": user_id,
            "topic_id": topic_id,
            "round": round_id,
            "neg": sentiment_scores.get("neg"),
            "pos": sentiment_scores.get("pos"),
            "neu": sentiment_scores.get("neu"),
            "compound": sentiment_scores.get("compound"),
            "sentiment_parent": sentiment_parent,
            "is_post": 1 if is_post else 0,
            "is_comment": 1 if is_comment else 0,
            "is_reaction": 1 if is_reaction else 0,
        }
        sentiment_entries.append(entry)

    return sentiment_entries


def prepare_toxicity_data(post_id: str, toxicity_scores: Dict[str, float]) -> Dict:
    """
    Prepare toxicity data for database insertion.

    Args:
        post_id: UUID of the post/comment
        toxicity_scores: Dict with toxicity metrics from Perspective API

    Returns:
        Dict ready for database insertion
    """
    return {
        "post_id": post_id,
        "toxicity": toxicity_scores.get("TOXICITY", 0.0),
        "severe_toxicity": toxicity_scores.get("SEVERE_TOXICITY", 0.0),
        "identity_attack": toxicity_scores.get("IDENTITY_ATTACK", 0.0),
        "insult": toxicity_scores.get("INSULT", 0.0),
        "profanity": toxicity_scores.get("PROFANITY", 0.0),
        "threat": toxicity_scores.get("THREAT", 0.0),
        "sexually_explicit": toxicity_scores.get("SEXUALLY_EXPLICIT", 0.0),
        "flirtation": toxicity_scores.get("FLIRTATION", 0.0),
    }
