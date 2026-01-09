from nltk.sentiment import SentimentIntensityAnalyzer
from perspective import PerspectiveAPI


def vader_sentiment(text: str) -> dict:
    """
    Calculate sentiment scores using VADER.

    :param text: the text to analyze
    :return: a dictionary with sentiment scores
    """
    sia = SentimentIntensityAnalyzer()
    sentiment = sia.polarity_scores(text)
    return sentiment


def toxicity(text, api_key: str) -> dict:
    """
    Calculate toxicity scores using the Perspective API.

    :param text: the text to analyze
    :param api_key: the Perspective API key
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

        except Exception:
            return {}
    return {}
