"""tests/test_metabolism_v12_surface.py — Hermetic tests for Metabolism V12
(Surface Curator + Metered Loop).

COVERAGE:
  CENSUS    marker counting, outline extraction, build/load, page keys,
            saturation (thresholds + entry verdict + overrides)
  DUP       panel_dup_reason: same-page, sitewide, no-collision, short titles
  DELTA     realized_delta_from_diff: adds, removals, lab-file exclusion
  PROPOSE   _validate_surface_fields: fail-closed fields, mode/delta coherence,
            saturation deny, duplicate deny, non-ui front-page deny,
            docket pass-through of surface fields + changed_files
  ADJUD     _surface_screen deny/allow
  AUDIT     realized-delta pre-screen rejects (undeclared addition,
            panel_delta exceeded, saturated growth)
  THROTTLE  daily pace rung (0 loops), propose_cadence_factor eco
  PINS      operator pins: core / weekly (hash-spread day) / paused,
            eco cadence factor on unpinned lobes
  GATE      429-derived pct_5h, cooling exclusion, known_readings

All tests are HERMETIC (tmp_path roots, synthetic fixtures, monkeypatched
usage_snapshot; no network).
"""
from __future__ import annotations

import hashlib
import sys
import textwrap
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from engine.metabolism import surface_map as sm  # noqa: E402
from engine.metabolism import throttle  # noqa: E402
from engine.metabolism import attention  # noqa: E402
from engine.metabolism import budget_gate  # noqa: E402
from engine.metabolism.propose import _validate_surface_fields, build_docket  # noqa: E402
from engine.metabolism.adjudicate import _surface_screen  # noqa: E402
from engine.metabolism.audit import audit_pr  # noqa: E402


# ── Fixture helpers ───────────────────────────────────────────────────────────

_UX_RULES = textwrap.dedent("""\
schema: ux_simplicity_rules.v1
surface_patterns:
  front_page:
    include:
      - "site/*.html"
      - "templates/*.html"
      - "templates/*.j2"
    exclude:
      - "*_lab*"
      - "*admin*"
jargon_blocklist: []
""")

_SURFACE_RULES = textwrap.dedent("""\
schema: metabolism_surface_rules.v1
saturated_markers: 3
saturated_bytes: 100000
max_new_bytes_saturated: 100
outline_max: 10
prompt_pages_max: 5
page_overrides: {}
""")

_CRAMMED_PAGE = (
    "<html><body>"
    "<section><h2>Momentum Overheat Scoreboard</h2><p>x</p></section>"
    "<section><h2>Breadth Divergence Board</h2><p>x</p></section>"
    '<div class="mx-eyebrow">Credit Stress</div>'
    "</body></html>"
)
_SMALL_PAGE = "<html><body><h2>Watchlist</h2><p>tiny</p></body></html>"


def _mk_root(tmp_path: Path) -> Path:
    (tmp_path / "config").mkdir(parents=True, exist_ok=True)
    (tmp_path / "config" / "ux_simplicity_rules.yml").write_text(_UX_RULES)
    (tmp_path / "config" / "metabolism_surface_rules.yml").write_text(_SURFACE_RULES)
    site = tmp_path / "site"
    site.mkdir(exist_ok=True)
    (site / "macro.html").write_text(_CRAMMED_PAGE)
    (site / "markets.html").write_text(_SMALL_PAGE)
    (site / "signal_lab.html").write_text(_CRAMMED_PAGE)  # excluded pattern
    return tmp_path


# ── CENSUS ────────────────────────────────────────────────────────────────────

def test_count_markers_tags_and_classes():
    assert sm.count_markers(_CRAMMED_PAGE) == 5  # 2 section + 2 h2 + 1 eyebrow
    assert sm.count_markers(_SMALL_PAGE) == 1
    assert sm.count_markers("") == 0


def test_extract_outline_headings_and_classed():
    out = sm.extract_outline(_CRAMMED_PAGE)
    assert "Momentum Overheat Scoreboard" in out
    assert "Credit Stress" in out


def test_build_and_load_census(tmp_path):
    root = _mk_root(tmp_path)
    built = sm.build_surface_map(root=root, write=True)
    assert built["counts"]["pages"] == 2  # lab page excluded
    loaded = sm.load_surface_map(root)
    assert loaded["pages"]["macro.html"]["markers"] == 5
    assert loaded["pages"]["macro.html"]["saturated"] is True  # >= 3 markers
    assert loaded["pages"]["markets.html"]["saturated"] is False


def test_page_key_for_path():
    assert sm.page_key_for_path("templates/us_stocks.html.j2") == "us_stocks.html"
    assert sm.page_key_for_path("site/macro.html") == "macro.html"


def test_saturation_override(tmp_path):
    root = _mk_root(tmp_path)
    rules = (root / "config" / "metabolism_surface_rules.yml")
    rules.write_text(_SURFACE_RULES.replace(
        "page_overrides: {}", "page_overrides:\n  markets.html: { saturated: true }"))
    sm.build_surface_map(root=root, write=True)
    assert sm.is_saturated("markets.html", root=root) is True


# ── DUP ───────────────────────────────────────────────────────────────────────

def test_panel_dup_same_page_and_sitewide(tmp_path):
    root = _mk_root(tmp_path)
    smap = sm.build_surface_map(root=root, write=True)
    same = sm.panel_dup_reason("Add momentum overheat scoreboard chip", "macro.html", smap)
    assert same and "macro.html" in same
    other = sm.panel_dup_reason("Momentum overheat scoreboard", "markets.html", smap)
    assert other and "another page" in other and "macro.html" in other
    assert sm.panel_dup_reason("Liquidity stress ribbon", "macro.html", smap) is None
    assert sm.panel_dup_reason("Up", "macro.html", smap) is None  # too short


# ── DELTA ─────────────────────────────────────────────────────────────────────

_DIFF_ADD = textwrap.dedent("""\
diff --git a/site/macro.html b/site/macro.html
--- a/site/macro.html
+++ b/site/macro.html
@@ -1,2 +1,5 @@
 <div>
+<section class="nb">
+<h2>Volatility Regime Scoreboard</h2>
+<p>42 41 40</p>
 </div>
""")

_DIFF_REMOVE = textwrap.dedent("""\
diff --git a/site/macro.html b/site/macro.html
--- a/site/macro.html
+++ b/site/macro.html
@@ -1,5 +1,2 @@
 <div>
-<section class="nb">
-<h2>Volatility Regime Scoreboard</h2>
-<p>42 41 40</p>
 </div>
""")

_DIFF_LAB = _DIFF_ADD.replace("site/macro.html", "site/signal_lab.html")


def test_realized_delta_add_remove_and_exclusion(tmp_path):
    root = _mk_root(tmp_path)
    add = sm.realized_delta_from_diff(_DIFF_ADD, root)
    assert add["marker_delta"] == 2 and add["net_bytes"] > 0
    assert "macro.html" in add["files"]
    rem = sm.realized_delta_from_diff(_DIFF_REMOVE, root)
    assert rem["marker_delta"] == -2 and rem["net_bytes"] < 0
    lab = sm.realized_delta_from_diff(_DIFF_LAB, root)
    assert lab["front_paths"] == [] and lab["marker_delta"] == 0


# ── PROPOSE validation ────────────────────────────────────────────────────────

def _census() -> dict[str, Any]:
    return {"pages": {
        "macro.html": {"bytes": 9000, "markers": 5, "saturated": True,
                       "outline": ["Momentum Overheat Scoreboard", "Credit Stress"]},
        "markets.html": {"bytes": 100, "markers": 1, "saturated": False,
                         "outline": ["Watchlist"]},
    }}


def _ui(**kw) -> dict[str, Any]:
    base = {
        "title": "Liquidity stress ribbon on markets", "kind": "ui",
        "target_page": "markets.html", "ui_mode": "add", "panel_delta": 1,
        "user_question": "Is funding stress rising right now?",
        "displacement": "none: page below saturation",
    }
    base.update(kw)
    return base


def test_surface_fields_fail_closed():
    assert _validate_surface_fields(_ui(target_page=""), _census())
    assert _validate_surface_fields(_ui(ui_mode="expand"), _census())
    assert _validate_surface_fields(_ui(panel_delta="two"), _census())
    assert _validate_surface_fields(_ui(user_question="  "), _census())
    assert _validate_surface_fields(_ui(displacement=""), _census())  # delta>0
    assert _validate_surface_fields(_ui(), _census()) is None


def test_surface_mode_delta_coherence():
    assert "panel_delta >= 1" in _validate_surface_fields(_ui(panel_delta=0), _census())
    err = _validate_surface_fields(
        _ui(ui_mode="improve", panel_delta=1), _census())
    assert err and "declare ui_mode=add" in err
    ok = _validate_surface_fields(
        _ui(ui_mode="consolidate", panel_delta=-1, displacement="merge 2 boards"),
        _census())
    assert ok is None


def test_surface_saturation_and_dup_denies():
    err = _validate_surface_fields(
        _ui(target_page="macro.html", displacement="drop weakest chip"), _census())
    assert err and "SATURATED" in err
    err = _validate_surface_fields(
        _ui(title="Momentum overheat scoreboard v2", target_page="markets.html"),
        _census())
    assert err and "another page" in err
    err = _validate_surface_fields(_ui(target_page="nope.html"), _census())
    assert err and "census" in err


def test_non_ui_front_page_denied():
    prop = {"title": "add helper", "kind": "doc",
            "changed_files": ["site/macro.html"]}
    err = _validate_surface_fields(prop, _census())
    assert err and "kind=ui" in err
    assert _validate_surface_fields(
        {"title": "add helper", "kind": "doc",
         "changed_files": ["docs/README.md"]}, _census()) is None


def test_docket_passes_surface_fields_through(tmp_path):
    raw = [_ui(tier="T1", targets_sensor="s1",
               fitness_contract={"sensor": "s1", "expected_sign": "+",
                                 "band": "b", "check_by": "2027-01-01",
                                 "placebo_to_beat": "p"},
               changed_files=["site/markets.html"], rationale="r")]
    docket = build_docket("cyc-1", raw, root=tmp_path, max_docket_size=5)
    assert len(docket["proposals"]) == 1, docket["rejected"]
    p = docket["proposals"][0]
    for k in ("target_page", "ui_mode", "panel_delta", "user_question",
              "displacement", "changed_files"):
        assert k in p, f"{k} dropped by pass-through"


# ── ADJUDICATE screen ─────────────────────────────────────────────────────────

def test_surface_screen_denies_and_allows(tmp_path):
    root = _mk_root(tmp_path)
    sm.build_surface_map(root=root, write=True)
    bad = _ui(target_page="macro.html", displacement="drop weakest chip")
    verdict = _surface_screen(bad, root)
    assert verdict["allow"] is False and "R-V12" in verdict["reason"]
    good = _ui()
    assert _surface_screen(good, root)["allow"] is True
    assert _surface_screen({"title": "t", "kind": "test"}, root)["allow"] is True


# ── AUDIT realized-delta teeth ────────────────────────────────────────────────

def test_audit_rejects_undeclared_surface_addition(tmp_path):
    root = _mk_root(tmp_path)
    sm.build_surface_map(root=root, write=True)
    proposal = {"proposal_id": "p1", "title": "doc tweak", "kind": "doc",
                "target_files": ["site/macro.html"], "fitness_contract": {}}
    rec = audit_pr(1, proposal, _DIFF_ADD, "deadbeef", root)
    assert rec["verdict"] == "reject"
    assert any("undeclared_surface_addition" in f for f in rec["findings"])


def test_audit_rejects_exceeded_panel_delta(tmp_path):
    root = _mk_root(tmp_path)
    sm.build_surface_map(root=root, write=True)
    proposal = {"proposal_id": "p2", "title": "small chip", "kind": "ui",
                "panel_delta": 1, "target_files": ["site/macro.html"],
                "fitness_contract": {}}
    rec = audit_pr(2, proposal, _DIFF_ADD + _DIFF_ADD.replace("Volatility", "Breadth"),
                   "deadbeef", root)
    assert rec["verdict"] == "reject"
    assert any("panel_delta_exceeded" in f or "saturated_page_growth" in f
               for f in rec["findings"])


def test_audit_rejects_saturated_growth_even_declared(tmp_path):
    root = _mk_root(tmp_path)
    sm.build_surface_map(root=root, write=True)  # macro.html saturated
    proposal = {"proposal_id": "p3", "title": "board", "kind": "ui",
                "panel_delta": 2, "target_files": ["site/macro.html"],
                "fitness_contract": {}}
    rec = audit_pr(3, proposal, _DIFF_ADD, "deadbeef", root)
    assert rec["verdict"] == "reject"
    assert any("saturated_page_growth" in f for f in rec["findings"])


def test_audit_allows_saturated_removal_prescreen(tmp_path):
    root = _mk_root(tmp_path)
    sm.build_surface_map(root=root, write=True)
    proposal = {"proposal_id": "p4", "title": "consolidate", "kind": "ui",
                "panel_delta": -2, "target_files": ["site/macro.html"],
                "fitness_contract": {}}
    with patch("engine.metabolism.audit._call_llm_auditor",
               return_value=("approve", 0.9, [], "clean removal", None)):
        rec = audit_pr(4, proposal, _DIFF_REMOVE, "deadbeef", root)
    assert rec["deterministic_ok"] is True
    assert rec["verdict"] == "approve"


# ── THROTTLE ──────────────────────────────────────────────────────────────────

def test_daily_pace_rung(monkeypatch):
    monkeypatch.setenv("METAB_PACE", "daily")
    assert throttle.pace_loops_per_window() == 0
    assert throttle.pace() == "daily"
    monkeypatch.delenv("METAB_PACE")
    assert throttle.pace_loops_per_window() == 1  # fail-open unchanged


def test_eco_cadence_factor(monkeypatch):
    monkeypatch.setenv("METAB_INTENSITY", "low")
    assert throttle.propose_cadence_factor() == 2
    monkeypatch.setenv("METAB_INTENSITY", "high")
    assert throttle.propose_cadence_factor() == 1
    monkeypatch.delenv("METAB_INTENSITY")
    assert throttle.propose_cadence_factor() == 1


# ── PINS ──────────────────────────────────────────────────────────────────────

_ATTN_TPL = """\
schema: metabolism_attention.v1
max_focus_lobes: 8
operator_pins:
  core: [core-lobe]
  weekly: [{weekly_lobe}]
  paused: [paused-lobe]
"""


def _lobe_due(today: bool) -> str:
    """Find a lobe id whose weekly due day is (or is not) today (deterministic)."""
    now = datetime.now(timezone.utc).weekday()
    for i in range(500):
        name = f"wk-lobe-{i}"
        if (attention.weekly_due_day(name) == now) is today:
            return name
    raise AssertionError("no lobe name found")


def test_operator_pins(tmp_path):
    due = _lobe_due(True)
    not_due = _lobe_due(False)
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "metabolism_attention.yml").write_text(
        _ATTN_TPL.format(weekly_lobe=f"{due}, {not_due}"))
    assert attention.propose_skip("core-lobe", root=tmp_path) == (False, "")
    skip, reason = attention.propose_skip("paused-lobe", root=tmp_path)
    assert skip is True and reason == "operator_pin:paused"
    assert attention.propose_skip(due, root=tmp_path) == (False, "")
    skip, reason = attention.propose_skip(not_due, root=tmp_path)
    assert skip is True and reason.startswith("operator_pin:weekly")


def test_weekly_due_day_deterministic_spread():
    days = {attention.weekly_due_day(f"lobe-{i}") for i in range(40)}
    assert days == set(range(7))  # hash spread covers the week
    assert attention.weekly_due_day("x") == attention.weekly_due_day("x")


def test_eco_factor_applies_to_unpinned(tmp_path, monkeypatch):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "metabolism_attention.yml").write_text(
        "schema: metabolism_attention.v1\npropose_cadence:\n  STANDARD: 2\n")
    alloc = {"cycle_id": "cyc-9", "allocations": {"free-lobe": {"band": "STANDARD"}}}

    def _hash_skip(cadence: int) -> bool:
        digest = hashlib.sha256(b"cyc-9:free-lobe").digest()
        return int.from_bytes(digest[:8], "big") % cadence != 0

    monkeypatch.setenv("METAB_INTENSITY", "low")
    skip, _ = attention.propose_skip("free-lobe", root=tmp_path,
                                     allocation=alloc, cycle_id="cyc-9")
    assert skip == _hash_skip(4)  # 2 × eco factor 2
    monkeypatch.delenv("METAB_INTENSITY")
    skip, _ = attention.propose_skip("free-lobe", root=tmp_path,
                                     allocation=alloc, cycle_id="cyc-9")
    assert skip == _hash_skip(2)


# ── GATE (429-derived readings) ──────────────────────────────────────────────

def _snapshot_rows() -> list[dict[str, Any]]:
    return [
        {"key_id": "k_cooling", "present": True, "enabled": True,
         "cooling": True, "cool_kind": "window", "reset_hint": "2026-07-21T08:00:00Z",
         "ratelimit_headers": {}, "window_5h_est_tokens": 0, "weekly_est_tokens": 0},
        {"key_id": "k_fresh", "present": True, "enabled": True,
         "cooling": False, "cool_kind": None, "reset_hint": None,
         "ratelimit_headers": {}, "window_5h_est_tokens": 0, "weekly_est_tokens": 0},
    ]


def test_429_derived_reading_and_cooling_exclusion(tmp_path):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "metabolism_budget.yml").write_text(
        "gate_policy:\n  fivehour_done_pct: 80\n")
    with patch("engine.neuralweb.key_pool.usage_snapshot",
               return_value=_snapshot_rows()):
        kb = budget_gate.key_budget("k_cooling", tmp_path)
        assert kb["pct_5h"] == 100.0 and kb["src_5h"] == "429_window"
        assert kb["cooling"] is True and kb["reset_5h"]
        v = budget_gate.gate_verdict("5h_max", tmp_path)
        assert "k_cooling" not in v["eligible_keys"]
        assert "k_fresh" in v["eligible_keys"]
        assert v["known_readings"] == 1
        assert v["all_done"] is False


def test_all_cooling_disarms_5h_max(tmp_path):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "metabolism_budget.yml").write_text(
        "gate_policy:\n  fivehour_done_pct: 80\n")
    rows = [dict(r, cooling=True, cool_kind="window") for r in _snapshot_rows()]
    with patch("engine.neuralweb.key_pool.usage_snapshot", return_value=rows):
        v = budget_gate.gate_verdict("5h_max", tmp_path)
        assert v["eligible_keys"] == []
        assert v["all_done"] is True  # 429s ARE readings — burn mode disarms
        assert v["known_readings"] == 2


def test_unknowns_still_never_disarm(tmp_path):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "metabolism_budget.yml").write_text("gate_policy: {}\n")
    with patch("engine.neuralweb.key_pool.usage_snapshot",
               return_value=[_snapshot_rows()[1]]):
        v = budget_gate.gate_verdict("5h_max", tmp_path)
        assert v["all_done"] is False
        assert v["reason"] == "unknown_usage"
        assert v["known_readings"] == 0


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
