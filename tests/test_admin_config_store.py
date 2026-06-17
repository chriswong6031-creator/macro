"""admin.config_store — surgical, comment-preserving config.yml edits."""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from admin import config_store as cs

SAMPLE = """\
# header comment
top:
  enabled: true            # comment A
  interval_days: 2         # comment B
  lenses: [a, b, c]
  sub:
    enabled: false  # nested flag
other:
  enabled: true
  deep:
    veto:
      enabled: true   # deeply nested
"""


def _temp(monkeypatch, content=SAMPLE):
    """Point config_store at a throwaway file (auto-restored by monkeypatch)."""
    d = tempfile.mkdtemp(prefix="cfgtest_")
    p = Path(d) / "config.yml"
    p.write_text(content)
    monkeypatch.setattr(cs, "CONFIG", p)
    return p


def test_locate_line_nested_and_reused_keys(monkeypatch):
    p = _temp(monkeypatch)
    lines = p.read_text().split("\n")
    assert cs.locate_line("top.enabled", lines) == 2
    assert cs.locate_line("top.sub.enabled", lines) == 6
    assert cs.locate_line("other.enabled", lines) == 8
    # deeply nested, walks through two intermediate parents
    assert cs.locate_line("other.deep.veto.enabled", lines) == 11
    assert cs.locate_line("top.missing", lines) is None


def test_set_bool_flips_only_value_and_preserves_comment(monkeypatch):
    p = _temp(monkeypatch)
    r = cs.set_bool("top.sub.enabled", True)
    assert r["ok"] and r["old"] == "false" and r["new"] == "true"
    out = p.read_text().split("\n")
    assert out[6] == "    enabled: true  # nested flag"   # indent + comment intact
    # every OTHER line is byte-identical
    src = SAMPLE.split("\n")
    for i, (a, b) in enumerate(zip(src, out)):
        if i != 6:
            assert a == b, f"line {i} changed unexpectedly"


def test_set_bool_rejects_non_boolean_line(monkeypatch):
    _temp(monkeypatch)
    r = cs.set_bool("top.lenses", True)      # a list, not a bool
    assert not r["ok"] and "not a boolean" in r["error"]


def test_set_int_clamps_to_range_and_keeps_comment(monkeypatch):
    p = _temp(monkeypatch)
    r = cs.set_int("top.interval_days", 99, 1, 7)
    assert r["ok"] and r["new"] == "7"       # clamped
    assert p.read_text().split("\n")[3] == "  interval_days: 7         # comment B"
    r2 = cs.set_int("top.interval_days", 0, 1, 7)
    assert r2["new"] == "1"                   # clamped low


def test_roundtrip_read_value(monkeypatch):
    _temp(monkeypatch)
    assert cs.get_value("top.sub.enabled") is False
    cs.set_bool("top.sub.enabled", True)
    assert cs.get_value("top.sub.enabled") is True


LIST_SAMPLE = """\
top:
  items:
    - name: x
      enabled: false
  count: 3
"""


def test_set_bool_fails_closed_on_non_scalar_path(monkeypatch):
    """A dotted path that traverses a list (so get_value is None) must NOT be edited,
    even though locate_line could match the embedded `enabled:` line."""
    p = _temp(monkeypatch, LIST_SAMPLE)
    before = p.read_text()
    r = cs.set_bool("top.items.enabled", True)
    assert not r["ok"] and "scalar" in r["error"]
    assert p.read_text() == before          # file untouched


def test_set_int_rejects_bool_and_missing(monkeypatch):
    _temp(monkeypatch, LIST_SAMPLE)
    assert cs.set_int("top.count", 5, 1, 7)["ok"]            # real int → ok
    assert not cs.set_int("top.items.enabled", 5, 1, 7)["ok"]  # non-int path → fail closed


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
