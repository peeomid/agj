from agj.permissions import parse_pattern_text


def test_parse_pattern_text():
    text = r"""
    [codex]
    Would you like to run the following command\?

    [claude]
    Do you want to proceed\?
    """
    patterns = parse_pattern_text(text)
    assert any(r.pattern.startswith("Would you like") for r in patterns.codex)
    assert any(r.pattern.startswith("Do you want") for r in patterns.claude)
