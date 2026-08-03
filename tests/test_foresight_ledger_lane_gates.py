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

2026-08-02 sweep — the same contract now pins six more forward-ledger writers that
shipped ungated: the US + China sector-central graders, vol_shock_scorecard,
froth_fragility, event_risk, and regime_snap_veto. One exception is deliberate: the
China grader gates on asia_advance_enabled() (CN_LANE=asia), because its sole
advancing lane is asia-close.yml band 2, which sets no COLLECT_LANE — a nightly gate
there would be permanently closed. froth_fragility._parab_history is gated on the
PERSIST half only (legitimate off-lane read intent), so it is tested separately.

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
    # 2026-08-02 sweep. Every arg tuple below is REACHING: ungated, execution gets to
    # config.data_dir(), so deleting a gate fails its case rather than passing vacuously.
    ("engine.sector_central_grader", "append_central_log",
     ({"as_of": "2026-08-02", "sectors": [], "baskets": [{"id": "b-x", "kind": "basket"}]},)),
    ("engine.china_sector_central_grader", "append_central_log",
     ({"as_of": "2026-08-02", "sectors": [], "baskets": [{"id": "b-x", "kind": "basket"}]},)),
    ("engine.vol_shock_scorecard", "append_log",
     ({"score": 50, "asof": "2026-08-02", "band": "elevated"},)),
    ("engine.vol_shock_scorecard", "resolve", ({"2026-08-02": 100.0},)),
    ("engine.vol_shock_scorecard", "resolve_from_store", ()),
    ("engine.froth_fragility", "append_log", ({"asof": "2026-08-02", "headline": "x"},)),
    ("engine.froth_fragility", "resolve", ({"2026-08-02": 100.0},)),
    ("engine.froth_fragility", "resolve_from_store", ()),
    ("engine.event_risk", "append_log",
     ({"show": True, "days_to": 0, "asof": "2026-08-02", "type": "CPI"},)),
    ("engine.event_risk", "resolve", ({"2026-08-02": 100.0},)),
    ("engine.regime_snap_veto", "_append_log", ({}, {})),
]

_IDS = [f"{m.rsplit('.', 1)[1]}.{f}" for m, f, _ in APPENDERS]

# The probe must NOT be an Exception: most of the pinned writers are fail-soft
# (`except Exception` bodies), so an AssertionError raised inside them is SWALLOWED
# and the off-lane test passes vacuously on ungated code. A BaseException travels
# through those wrappers and makes the breach visible. Strictly stronger for the
# original 12 entries too — gated first, they never reach the probe.
class _LaneBreach(BaseException):
    pass


def _off_lane(monkeypatch):
    monkeypatch.delenv("COLLECT_LANE", raising=False)
    monkeypatch.delenv("US_LANE", raising=False)
    monkeypatch.delenv("CN_LANE", raising=False)


def _probe(monkeypatch, label: str):
    """Patch config.data_dir() to a tripwire — any filesystem intent surfaces."""
    import lib.config as cfg

    def _boom(*a, **k):  # noqa: ANN002, ANN003
        raise _LaneBreach(
            f"{label} reached config.data_dir() off-lane — "
            f"the ledger-advance gate must be the first statement"
        )

    monkeypatch.setattr(cfg, "data_dir", _boom)


@pytest.mark.parametrize("mod_name,fn_name,args", APPENDERS, ids=_IDS)
def test_appender_short_circuits_off_lane(monkeypatch, mod_name, fn_name, args):
    """Off-lane, the gate must fire before ANY filesystem intent."""
    _off_lane(monkeypatch)
    _probe(monkeypatch, f"{mod_name}.{fn_name}")
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


# --------------------------------------------------------------------------- #
# Cross-lane asymmetry — the US-nightly and asia-close families never cross-arm.
# --------------------------------------------------------------------------- #
_CN_GRADER = "engine.china_sector_central_grader"
_CENTRAL_DATA = {"as_of": "2026-08-02", "sectors": [],
                 "baskets": [{"id": "b-x", "kind": "basket"}]}
_NIGHTLY_APPENDERS = [e for e in APPENDERS if e[0] != _CN_GRADER]
_NIGHTLY_IDS = [f"{m.rsplit('.', 1)[1]}.{f}" for m, f, _ in _NIGHTLY_APPENDERS]


def test_china_grader_refuses_on_us_nightly_lane(monkeypatch):
    """COLLECT_LANE=nightly must NOT open the asia gate."""
    _off_lane(monkeypatch)
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    _probe(monkeypatch, f"{_CN_GRADER}.append_central_log")
    from engine import china_sector_central_grader as ccg

    assert ccg.append_central_log(_CENTRAL_DATA) == 0


@pytest.mark.parametrize("mod_name,fn_name,args", _NIGHTLY_APPENDERS, ids=_NIGHTLY_IDS)
def test_nightly_appender_refuses_on_asia_lane(monkeypatch, mod_name, fn_name, args):
    """CN_LANE=asia must NOT open any nightly gate."""
    _off_lane(monkeypatch)
    monkeypatch.setenv("CN_LANE", "asia")
    _probe(monkeypatch, f"{mod_name}.{fn_name}")
    mod = importlib.import_module(mod_name)
    getattr(mod, fn_name)(*args)


# --------------------------------------------------------------------------- #
# On-lane coverage for the 2026-08-02 sweep — a gate that is always closed is the
# other half of the defect, and silently stops the nightly's forward accrual.
# --------------------------------------------------------------------------- #
def test_sector_central_grader_appends_on_nightly_lane(monkeypatch, tmp_path):
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    import lib.config as cfg
    monkeypatch.setattr(cfg, "data_dir", lambda: tmp_path)
    from engine import sector_central_grader as scg

    rec = {"id": "b-x", "kind": "basket", "name": "X",
           "conviction": {"score": 70, "label_en": "Accumulate", "dir": "up",
                          "confluence": {"agree": 2}},
           "forward": {"trend_pass": True, "ret_12m": 0.1},
           "components": {"gate_factor": 0.6}}
    assert scg.append_central_log({**_CENTRAL_DATA, "baskets": [rec]}) == 1
    assert (tmp_path / "sector_central" / "calls.parquet").exists()


def test_china_sector_central_grader_appends_on_asia_lane(monkeypatch, tmp_path):
    monkeypatch.setenv("CN_LANE", "asia")
    import lib.config as cfg
    monkeypatch.setattr(cfg, "data_dir", lambda: tmp_path)
    from engine import china_sector_central_grader as ccg

    rec = {"id": "b-x", "kind": "basket", "basket_id": "x", "name": "X",
           "conviction": {"score": 70, "label_en": "Accumulate", "dir": "up",
                          "confluence": {"agree": 2}},
           "forward": {"cond_rate": 0.6, "lift": 0.1},
           "components": {"gate_factor": 0.6}}
    assert ccg.append_central_log({**_CENTRAL_DATA, "baskets": [rec]}) == 1
    assert (tmp_path / "china_sector_central" / "calls.parquet").exists()


def test_forward_log_appenders_open_on_nightly_lane(monkeypatch, tmp_path):
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    import lib.config as cfg
    monkeypatch.setattr(cfg, "data_dir", lambda: tmp_path)
    from engine import event_risk, froth_fragility, vol_shock_scorecard

    assert vol_shock_scorecard.append_log(
        {"score": 50, "asof": "2026-08-02", "band": "elevated"}, {},
        path=tmp_path / "vol_shock.jsonl") is True
    assert froth_fragility.append_log(
        {"asof": "2026-08-02", "headline": 72.0}, {},
        path=tmp_path / "froth.jsonl") is True
    assert event_risk.append_log(
        {"show": True, "days_to": 0, "asof": "2026-08-02", "type": "CPI"},
        path=tmp_path / "event.jsonl") is True


def test_regime_snap_veto_log_is_once_per_utc_date(monkeypatch, tmp_path):
    """Keep-FIRST per UTC date: build_site runs on every render lane, and before this
    gate one firing day accrued a row per render."""
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    import lib.config as cfg
    monkeypatch.setattr(cfg, "data_dir", lambda: tmp_path)
    from engine import regime_snap_veto as veto

    bundle = {"snap": {"status": "firing"}, "recent_headlines": []}
    veto._append_log({"generated_at": "2026-08-02T01:05:00+00:00",
                      "lean": "durable", "confidence": "high"}, bundle)
    veto._append_log({"generated_at": "2026-08-02T19:30:00+00:00",
                      "lean": "fragile", "confidence": "low"}, bundle)

    lines = [x for x in (tmp_path / "regime_snap" / "veto_log.jsonl")
             .read_text().splitlines() if x.strip()]
    assert len(lines) == 1
    row = json.loads(lines[0])
    assert row["date"] == "2026-08-02"
    assert row["lean"] == "durable"          # keep-FIRST, not last-writer-wins


def test_parab_history_persists_only_on_nightly_lane(monkeypatch, tmp_path):
    """_parab_history has legitimate off-lane READ intent — the returned series must be
    identical in both lanes so an off-lane snapshot renders the same — so only its
    PERSIST half is gated, and it cannot join the gate-first APPENDERS enumeration."""
    import pandas as pd

    from engine import froth_fragility as ff

    p = tmp_path / "parab_history.parquet"
    monkeypatch.setattr(ff, "_parab_path", lambda: p)
    monkeypatch.setattr(ff, "_backcompute_parab_history",
                        lambda *a, **k: pd.Series(dtype=float))

    _off_lane(monkeypatch)
    off = ff._parab_history(pd.DataFrame(), None, "2026-08-02", 42.0)
    assert float(off.loc[pd.Timestamp("2026-08-02")]) == 42.0
    assert not p.exists()

    monkeypatch.setenv("COLLECT_LANE", "nightly")
    on = ff._parab_history(pd.DataFrame(), None, "2026-08-02", 42.0)
    assert float(on.loc[pd.Timestamp("2026-08-02")]) == 42.0
    assert p.exists()


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
