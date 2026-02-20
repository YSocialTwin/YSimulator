import logging

from detoxify import Detoxify
from nltk.sentiment import SentimentIntensityAnalyzer
from perspective import PerspectiveAPI

logger = logging.getLogger(__name__)

_detoxify_model = None


def _get_detoxify_model() -> Detoxify:
    """Return a cached Detoxify model instance, creating it on first use."""
    global _detoxify_model
    if _detoxify_model is None:
        logger.info("Initializing Detoxify model (first use)")
        _detoxify_model = Detoxify("original")
        logger.info("Detoxify model initialized successfully")
    return _detoxify_model


def vader_sentiment(text: str) -> dict:
    """
    Calculate sentiment scores using VADER.

    :param text: the text to analyze
    :return: a dictionary with sentiment scores
    """
    sia = SentimentIntensityAnalyzer()
    sentiment = sia.polarity_scores(text)
    return sentiment


def detoxify_toxicity(text: str) -> dict:
    """
    Calculate toxicity scores using the detoxify library locally.

    Returns results in the same format as the Perspective API, mapping
    detoxify categories to their Perspective API equivalents.

    :param text: the text to analyze
    :return: a dictionary with toxicity scores in Perspective API format
    """
    try:
        scores = _get_detoxify_model().predict(text)
        return {
            "TOXICITY": scores.get("toxicity", 0.0),
            "SEVERE_TOXICITY": scores.get("severe_toxicity", 0.0),
            "IDENTITY_ATTACK": scores.get("identity_attack", 0.0),
            "INSULT": scores.get("insult", 0.0),
            "PROFANITY": scores.get("obscene", 0.0),
            "THREAT": scores.get("threat", 0.0),
            "SEXUALLY_EXPLICIT": scores.get("sexual_explicit", 0.0),
            "FLIRTATION": 0.0,
        }
    except Exception as e:
        logger.warning("detoxify_toxicity failed: %s", e)
        return {}


def toxicity(text, api_key: str) -> dict:
    """
    Calculate toxicity scores using the Perspective API or detoxify locally.

    When an API key is provided, the Perspective API is used. When no API key
    is provided, the detoxify library is used as a local drop-in replacement.

    :param text: the text to analyze
    :param api_key: the Perspective API key (optional; uses detoxify if None)
    :return: a dictionary with toxicity scores
    """

    if api_key is not None:
        try:
            p = PerspectiveAPI(api_key)
            toxicity_score = p.score(
                text,
                tests=[
                    "TOXICITY",
                    "SEVERE_TOXICITY",
                    "IDENTITY_ATTACK",
                    "INSULT",
                    "PROFANITY",
                    "THREAT",
                    "SEXUALLY_EXPLICIT",
                    "FLIRTATION",
                ],
            )

            return {
                "TOXICITY": toxicity_score["TOXICITY"],
                "SEVERE_TOXICITY": toxicity_score["SEVERE_TOXICITY"],
                "IDENTITY_ATTACK": toxicity_score["IDENTITY_ATTACK"],
                "INSULT": toxicity_score["INSULT"],
                "PROFANITY": toxicity_score["PROFANITY"],
                "THREAT": toxicity_score["THREAT"],
                "SEXUALLY_EXPLICIT": toxicity_score["SEXUALLY_EXPLICIT"],
                "FLIRTATION": toxicity_score["FLIRTATION"],
            }

        except Exception as e:
            logger.warning("Perspective API toxicity scoring failed: %s", e)
            return {}

    logger.debug("No Perspective API key provided; using detoxify for local toxicity scoring")
    return detoxify_toxicity(text)
