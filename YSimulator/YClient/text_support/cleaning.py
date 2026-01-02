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
