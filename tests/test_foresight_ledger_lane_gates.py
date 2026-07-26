"""Express-lane ledger gates for the foresight estate — HOUSE-U5 class.

2026-07-25: build_foresight joined the express re-render lanes (render.yml /
engine-render.yml scope=all). Those lanes re-render pages from COMMITTED data,
commit ``git add site/`` ONLY, and never set COLLECT_LANE — so every foresight
ledger appender must gate on engine.ledger_lane.nightly_advance_enabled().
These appenders were the gap the #2598 gating sweep missed (policy_calendar
carried the only gate); ungated, an express bake re-read its own same-run rows
and shipped a page asserting accrual the committed ledgers did not contain.

Contract pinned here (mirrors tests/test_build_leader_radar.py's HOUSE-U5 gate):

1. OFF-LANE (no COLLECT_LANE/US_LANE): every appender returns BEFORE touching
   the filesystem — config.data_dir is patched to raise, so any fs intent fails
   the test. Junk args are deliberate: the gate must be the FIRST statement.
2. ON-LANE (COLLECT_LANE=nightly): the gate opens and rows land — guards
   against a future "gate accidentally always closed" regression that would
   silently stop the nightly's forward accrual.
3. The RENDER_NO_DRIP sentinel and the analyst ledger-replay loader behave as
   the express lanes assume.

Hermetic: all writes go to tmp_path; no repo data/ or site/ artifact is touched
(pytest-writes-live-artifacts trap).
"""
from __future__ import annotations

import importlib
import json

import pytest

# (module, function, junk args) — gate-first appenders: off-lane these must
# return without evaluating args or touching config.data_dir().
# bottleneck._append_ledger is absent by design: it sits behind the caller's
# write_ledger flag (threaded by the same 2026-07-25 change), and engine.run's
# engine-artifact writes are the engine-render lane's separate, pre-existing
# discard contract.
APPENDERS = [
    ("engine.foresight_cascade", "_append_ledger", ({},)),
    ("engine.theme_emergence", "_append_ledger", ({},)),
    ("engine.subsector_scan", "_append_ledger", ({}, [])),
    ("engine.power_scarcity", "_append_ledger", ({},)),
    ("engine.foresight_enb", "_append_log", ({},)),
    ("engine.foresight_health", "_append_health_log", ({},)),
    ("engine.foresight_analyst", "_append_ledger", ({}, {})),
    ("engine.thesis_monitor", "_append_det_record", ({},)),
    ("engine.bottleneck", "_shadow_log_cutoffs", ("theme", "2026-07-25", 1.0, 99)),
    ("engine.foresight_divergence", "_append_divergence_ledger", ([{"theme": "t"}],)),
    ("engine.foresight_shadow", "compute_shadow_stages", (None, None, None, None)),
    ("engine.foresight_shadow", "compute_heat_shadow", (None, None)),
]

_IDS = [f"{m.rsplit('.', 1)[1]}.{f}" for m, f, _ in APPENDERS]


def _off_lane(monkeypatch):
    monkeypatch.delenv("COLLECT_LANE", raising=False)
    monkeypatch.delenv("US_LANE", raising=False)


@pytest.mark.parametrize("mod_name,fn_name,args", APPENDERS, ids=_IDS)
def test_appender_short_circuits_off_lane(monkeypatch, mod_name, fn_name, args):
    """Off-lane, the gate must fire before ANY filesystem intent."""
    _off_lane(monkeypatch)
    import lib.config as cfg

    def _boom(*a, **k):  # noqa: ANN002, ANN003
        raise AssertionError(
            f"{mod_name}.{fn_name} reached config.data_dir() with COLLECT_LANE unset — "
            f"the nightly-advance gate must be the first statement"
        )

    monkeypatch.setattr(cfg, "data_dir", _boom)
    mod = importlib.import_module(mod_name)
    getattr(mod, fn_name)(*args)  # must return silently (None or 0), no raise


def test_gate_opens_on_nightly_lane(monkeypatch, tmp_path):
    """On-lane the same choke points append — the nightly's accrual must survive."""
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    import lib.config as cfg
    monkeypatch.setattr(cfg, "data_dir", lambda: tmp_path)

    from engine import foresight_health, thesis_monitor

    thesis_monitor._append_det_record({"theme": "t", "asof": "2026-07-25", "status": "OPEN"})
    det = tmp_path / "foresight" / "deterministic_theses.jsonl"
    assert det.exists()
    assert json.loads(det.read_text().splitlines()[0])["theme"] == "t"

    foresight_health._append_health_log({"overall": "OK"})
    assert (tmp_path / "foresight" / "health_log.jsonl").exists()


def test_nightly_advance_enabled_matrix(monkeypatch):
    from engine import ledger_lane

    _off_lane(monkeypatch)
    assert not ledger_lane.nightly_advance_enabled()
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    assert ledger_lane.nightly_advance_enabled()
    monkeypatch.setenv("COLLECT_LANE", "render")
    assert not ledger_lane.nightly_advance_enabled()
    monkeypatch.delenv("COLLECT_LANE")
    monkeypatch.setenv("US_LANE", "nightly")  # legacy alias
    assert ledger_lane.nightly_advance_enabled()


def test_no_drip_sentinel(monkeypatch):
    import scripts.build_foresight as bf

    monkeypatch.delenv("RENDER_NO_DRIP", raising=False)
    assert not bf._no_drip()
    monkeypatch.setenv("RENDER_NO_DRIP", "1")
    assert bf._no_drip()
    monkeypatch.setenv("RENDER_NO_DRIP", "0")
    assert not bf._no_drip()


def test_load_committed_theses_latest_asof_wins(monkeypatch, tmp_path):
    """The express replay renders the newest committed row per theme, marked from_ledger."""
    import lib.config as cfg
    monkeypatch.setattr(cfg, "data_dir", lambda: tmp_path)
    d = tmp_path / "foresight"
    d.mkdir(parents=True)
    rows = [
        {"theme": "power", "asof": "2026-07-20", "confidence": "medium", "kill_criteria": ["a"]},
        {"theme": "power", "asof": "2026-07-24", "confidence": "high", "kill_criteria": ["b"]},
        {"theme": "glp1", "asof": "2026-07-22", "confidence": "low", "kill_criteria": []},
    ]
    (d / "analyst_theses.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n"
    )

    from engine.foresight_analyst import load_committed_theses

    out = load_committed_theses()
    assert out is not None and out["from_ledger"] is True
    assert out["n_theses"] == 2
    by_theme = {t["theme"]: t for t in out["theses"]}
    assert by_theme["power"]["confidence"] == "high"
    assert by_theme["power"]["kill_criteria"] == ["b"]
    assert out["asof"] == "2026-07-24"
    assert "No new read was taken" in out["regime_read"]


def test_load_committed_theses_absent_ledger(monkeypatch, tmp_path):
    import lib.config as cfg
    monkeypatch.setattr(cfg, "data_dir", lambda: tmp_path)

    from engine.foresight_analyst import load_committed_theses

    assert load_committed_theses() is None
