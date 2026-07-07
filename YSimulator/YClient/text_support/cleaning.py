import re


def clean_text(author: str, text: str) -> str:
    """
    Clean the text by removing unwanted characters and the author's self mention.

    :param author: the author's username
    :param text: the text to clean
    :return: the cleaned text
    """
    text = (
        text.replace("-", "")
        .replace("@ ", "")
        .replace("  ", " ")
        .replace(". ", ".")
        .replace(" ,", ",")
        .replace("[", "")
        .replace("]", "")
        .replace("@,", "")
        .replace('"', "")
        .replace("'", "")
        .strip("()[]{}'")
        .lstrip()
    )
    text = text.replace(f"@{author}", "")
    return text


def extract_components(text: str, c_type: str = "hashtags") -> list:
    """
    Extract the components from the text.

    :param text: the text to extract the components from
    :param c_type: the component type, either "hashtags" or "mentions"
    :return: the extracted components
    """
    # Define the regex pattern
    if c_type == "hashtags":
        pattern = re.compile(r"#\w+")
    elif c_type == "mentions":
        pattern = re.compile(r"@\w+")
    else:
        return []
    # Find all matches in the input text
    components = pattern.findall(text)
    return components


def strip_invalid_mentions(text: str, is_valid_username_fn) -> str:
    """
    Remove @mentions that do not resolve to a real user.

    Args:
        text: Input text containing mentions
        is_valid_username_fn: Callable that returns True when a username exists

    Returns:
        Text with invalid mentions removed and spacing normalized
    """
    if not text:
        return text

    mention_pattern = re.compile(r"(?<!\w)@(\w+)")

    def _replace(match: re.Match) -> str:
        username = match.group(1)
        try:
            if is_valid_username_fn(username):
                return match.group(0)
        except Exception:
            # If validation fails, keep the mention to avoid destroying content.
            return match.group(0)
        return ""

    cleaned = mention_pattern.sub(_replace, text)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    cleaned = re.sub(r"\s+([,.;:!?])", r"\1", cleaned)
    cleaned = re.sub(r"\s+\)", ")", cleaned)
    cleaned = re.sub(r"\(\s+", "(", cleaned)
    return cleaned.strip()
