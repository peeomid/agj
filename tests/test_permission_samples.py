import pytest

from agj.permissions import detect_permission_prompt


@pytest.mark.parametrize(
    "output",
    [
        "Would you like to run the following command?\n› 1. Yes, proceed (y)\n2. No",
        "Would you like to run the following command?\n> 1. Yes, proceed\n3. No, and tell Codex what to do differently",
        "Would you like to run the following command?\n  1. Yes, proceed\n  2. Yes, and don't ask again\n  3. No, and tell Codex what to do differently",
        "Would you like to proceed?\n(no menu shown)",
        "Do you want to continue?\n(no menu shown)",
    ],
)
def test_codex_permission_true(output):
    assert detect_permission_prompt(output, "codex") is True


@pytest.mark.parametrize(
    "output",
    [
        "Would you like to run the following command?\n(no menu shown)",
        'output = "Would you like to run the following command?"',
        "Yes, proceed\n(no question shown)",
    ],
)
def test_codex_permission_false(output):
    assert detect_permission_prompt(output, "codex") is False


@pytest.mark.parametrize(
    "output",
    [
        "Do you want to proceed?\n❯ 1. Yes\n2. No\nEsc to cancel",
        "Do you want to make this edit to README.md?\n  1. Yes\n  2. No",
        "Do you want to proceed?\n> 1. Yes\n3. No, and tell Claude what to do differently",
        "Do you want to proceed?\n(no menu shown)",
        "Would you like to create the file?\n(no menu shown)",
        "Would you like me to add a License section to the README?\n  1. Yes\n  2. No",
    ],
)
def test_claude_permission_true(output):
    assert detect_permission_prompt(output, "claude") is True


@pytest.mark.parametrize(
    "output",
    [
        'note = "Do you want to proceed?"',
        "1. Yes\n(no question shown)",
    ],
)
def test_claude_permission_false(output):
    assert detect_permission_prompt(output, "claude") is False
