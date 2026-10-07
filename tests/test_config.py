import pytest

from idx_evidence_lab.config import Settings, load_settings
from idx_evidence_lab.research_attachments import read_attachment


def test_defaults_match_previous_hardcoded_behavior():
    s = load_settings({})
    assert (s.host, s.port) == ("127.0.0.1", 5500)
    assert s.is_loopback
    assert (s.chat_per_min, s.post_per_min) == (20, 120)


def test_overrides_and_loopback_detection():
    s = load_settings({"IDXEL_HOST": "0.0.0.0", "IDXEL_PORT": "8080", "IDXEL_RL_CHAT_PER_MIN": "0"})
    assert (s.host, s.port, s.chat_per_min) == ("0.0.0.0", 8080, 0)
    assert not s.is_loopback
    assert Settings(host="localhost").is_loopback
    assert Settings(host="::1").is_loopback
    assert not Settings(host="example.com").is_loopback


@pytest.mark.parametrize("env", [
    {"IDXEL_PORT": "abc"}, {"IDXEL_PORT": "0"}, {"IDXEL_PORT": "70000"}, {"IDXEL_RL_POST_PER_MIN": "-1"},
])
def test_invalid_values_fail_fast(env):
    with pytest.raises(ValueError, match="IDXEL_"):
        load_settings(env)


def test_attachment_name_with_control_characters_is_rejected():
    import base64
    data = base64.b64encode(b"hello").decode()
    with pytest.raises(ValueError, match="INVALID_ATTACHMENT"):
        read_attachment({"name": "bad\x00name.txt", "mime": "text/plain", "data": data})
    assert read_attachment({"name": "ok.txt", "mime": "text/plain", "data": data})["status"] == "READABLE"
