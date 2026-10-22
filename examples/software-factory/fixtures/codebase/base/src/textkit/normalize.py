"""空白の正規化。"""


def normalize_whitespace(text: str) -> str:
    """連続する空白を一つにまとめ、前後の空白を除く。大文字小文字は変えない。"""
    return " ".join(text.split())
