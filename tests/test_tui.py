from agj.models import InstanceInfo, ProcessInfo, SessionInfo
from agj.tui import TuiState, _state_value


def test_state_value():
    assert _state_value("permission") == "permission"
    assert _state_value("running") == "running"
    assert _state_value(None) == "unknown"


def test_tui_state_defaults():
    state = TuiState(instances=[])
    assert state.permission_only is False
    assert state.hide_unmapped is False
    assert state.output_lines == []
    assert state.output_loading is False
