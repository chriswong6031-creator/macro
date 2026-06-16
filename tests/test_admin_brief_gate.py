"""AI-brief regenerate-every-N-days interval gate (engine/master_brain + engine/ai_desk)."""
import json
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import ai_desk, master_brain


def _iso(days_ago):
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()


# ---- age helper --------------------------------------------------------------
def test_brief_age_days_parsing():
    assert master_brain._brief_age_days(None) is None
    assert master_brain._brief_age_days({}) is None
    assert master_brain._brief_age_days({"generated_at": "garbage"}) is None
    age = master_brain._brief_age_days({"generated_at": _iso(3)})
    assert 2.9 < age < 3.1
    # ai_desk shares the same semantics
    assert ai_desk._brief_age_days({"generated_at": _iso(0)}) < 0.01


def _seed(root, rel, payload):
    p = Path(root) / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload))
    return p


# ---- master_brain skip when fresh -------------------------------------------
def test_master_brain_skips_when_within_interval(monkeypatch):
    root = Path(tempfile.mkdtemp(prefix="mb_"))
    _seed(root, "data/regime/master_brief.json",
          {"generated_at": _iso(1), "lens": "macro", "sentinel": "PREV"})
    monkeypatch.setattr(master_brain, "_cfg",
                        lambda: {"enabled": True, "interval_days": 7, "lenses": ["macro"]})
    # synthesize must NOT be reached when we skip
    def _boom(*a, **k):
        raise AssertionError("synthesize must not run when the gate skips")
    monkeypatch.setattr(master_brain, "synthesize", _boom)

    out = master_brain.run(persist=False, root=root, force=False, lens="macro")
    assert out and out.get("sentinel") == "PREV"


def test_master_brain_force_bypasses_gate(monkeypatch):
    root = Path(tempfile.mkdtemp(prefix="mbf_"))
    _seed(root, "data/regime/master_brief.json", {"generated_at": _iso(0), "sentinel": "PREV"})
    monkeypatch.setattr(master_brain, "_cfg",
                        lambda: {"enabled": True, "interval_days": 7, "lenses": ["macro"]})
    master_brain.LENSES["macro"]["state_fn"]  # touch to ensure key exists
    monkeypatch.setitem(master_brain.LENSES["macro"], "state_fn", lambda r: {"macro": {"date": "x"}})
    monkeypatch.setattr(master_brain, "synthesize", lambda *a, **k: {"sentinel": "NEW"})
    monkeypatch.setattr(master_brain, "_translate_brief", lambda *a, **k: None)

    out = master_brain.run(persist=False, root=root, force=True, lens="macro")
    assert out and out.get("sentinel") == "NEW"   # forced → regenerated, not the prev


def test_master_brain_interval_one_does_not_skip(monkeypatch):
    root = Path(tempfile.mkdtemp(prefix="mb1_"))
    _seed(root, "data/regime/master_brief.json", {"generated_at": _iso(0), "sentinel": "PREV"})
    monkeypatch.setattr(master_brain, "_cfg",
                        lambda: {"enabled": True, "interval_days": 1, "lenses": ["macro"]})
    monkeypatch.setitem(master_brain.LENSES["macro"], "state_fn", lambda r: {"macro": {"date": "x"}})
    monkeypatch.setattr(master_brain, "synthesize", lambda *a, **k: {"sentinel": "NEW"})
    monkeypatch.setattr(master_brain, "_translate_brief", lambda *a, **k: None)

    out = master_brain.run(persist=False, root=root, force=False, lens="macro")
    assert out and out.get("sentinel") == "NEW"   # interval 1 → never skips


# ---- ai_desk skip when fresh -------------------------------------------------
def test_ai_desk_skips_when_within_interval(monkeypatch):
    root = Path(tempfile.mkdtemp(prefix="ad_"))
    _seed(root, "data/regime/ai_desk.json", {"generated_at": _iso(2), "sentinel": "PREV"})
    base = ai_desk._cfg()
    base.update({"enabled": True, "interval_days": 7})
    monkeypatch.setattr(ai_desk, "_cfg", lambda: base)
    def _boom(*a, **k):
        raise AssertionError("gather_desk_state must not run when the gate skips")
    monkeypatch.setattr(ai_desk, "gather_desk_state", _boom)

    out = ai_desk.run(persist=False, root=root, force=False)
    assert out and out.get("sentinel") == "PREV"


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
