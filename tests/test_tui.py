from agj.models import InstanceInfo, ProcessInfo, SessionInfo
from agj.tui import TuiState, _permission_value


def test_permission_value():
    assert _permission_value(True) == "yes"
    assert _permission_value(False) == "no"
    assert _permission_value(None) == "unknown"


def test_tui_state_defaults():
    state = TuiState(instances=[])
    assert state.permission_only is False
    assert state.hide_unmapped is False
    assert state.output_lines == []
    assert state.output_loading is False
