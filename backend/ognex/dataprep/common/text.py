import re


def normalize_text(text: str) -> str:
    text = re.sub(r"\.{2,}", "", text)
    text = re.sub(r"\n{2,}", "\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()