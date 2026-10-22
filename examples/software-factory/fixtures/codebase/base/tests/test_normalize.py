from textkit.normalize import normalize_whitespace


def test_collapses_inner_spaces():
    assert normalize_whitespace("a   b\t c") == "a b c"


def test_strips_both_ends():
    assert normalize_whitespace("  a b  ") == "a b"


def test_keeps_case():
    assert normalize_whitespace("Hello  World") == "Hello World"
