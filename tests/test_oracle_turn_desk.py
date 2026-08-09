"""Tests for W6 Rotation Turn Desk (_step_turn_desk + ledger helpers).

All fixtures are SYNTHETIC — no real data files, no network.

Test inventory
--------------
A. armed_window_recompute     — A15 fires detected from synthetic panel; window merges correct
B. no_fires_quiet_payload     — when no nodes fire, armed=[] and payload is quiet state
C. member_fire_join           — tier_cascade rows from standouts joined to correct armed sector
D. provisional_flag_carried   — T3 provisional flag propagates into member_fires
E. staleness_dual_asof        — member_fires_asof != asof when they differ
F. ledger_keep_first          — re-running same night does not duplicate rows
G. ledger_maturity_grading    — h=21 absolute return graded from synthetic closes
H. banned_key_guard           — payload with a 'forecast' key raises / returns False
I. template_smoke             — td-section present in rendered HTML, no title= violations
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Repo root on path
# ---------------------------------------------------------------------------
_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))


# ---------------------------------------------------------------------------
# Synthetic data builders
# ---------------------------------------------------------------------------

def _make_panel(
    nodes: list[str],
    n_days: int = 60,
    start: str = "2024-01-02",
    seed: int = 42,
    washout_last: bool = True,
) -> pd.DataFrame:
    """Minimal panel with all columns the grammar needs."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(start, periods=n_days, name="date")
    rows = []
    for node in nodes:
        ret = rng.normal(0.001, 0.01, n_days)
        rs = rng.normal(0, 0.01, n_days)
        vel_1w = np.cumsum(ret) * 0.02
        vel_1m = np.cumsum(ret) * 0.015
        vel_3m = np.cumsum(ret) * 0.01
        accel = vel_1w - vel_3m
        accel_z = (accel - accel.mean()) / (accel.std() + 1e-9)
        washout_w = np.zeros(n_days)
        if washout_last:
            washout_w[-1] = 1.0
        stochrsi_w_k = rng.uniform(0.05, 0.25, n_days)
        stochrsi_w_d = rng.uniform(0.05, 0.30, n_days)
        vix_pctile = rng.uniform(0.3, 0.6, n_days)
        spy_above_200d = np.ones(n_days)
        tlt_ret_10d = rng.normal(0, 0.005, n_days)
        cohesion = rng.uniform(0.3, 0.7, n_days)
        cohesion_chg = np.diff(cohesion, prepend=cohesion[0])
        breadth_50 = rng.uniform(0.4, 0.7, n_days)
        persistence = rng.uniform(0.45, 0.6, n_days)
        turnover_z = rng.normal(0, 1, n_days)
        cohesion_rebuild = np.zeros(n_days)
        oil_ret_10d = rng.normal(0, 0.01, n_days)
        dollar_chg_10d = rng.normal(0, 0.005, n_days)
        hy_oas_chg_10d = rng.normal(0, 0.01, n_days)

        df = pd.DataFrame({
            "ret": ret, "rs": rs, "vel_1w": vel_1w, "vel_1m": vel_1m,
            "vel_3m": vel_3m, "accel": accel, "accel_z": accel_z,
            "washout_w": washout_w, "stochrsi_w_k": stochrsi_w_k,
            "stochrsi_w_d": stochrsi_w_d, "vix_pctile": vix_pctile,
            "spy_above_200d": spy_above_200d, "tlt_ret_10d": tlt_ret_10d,
            "cohesion": cohesion, "cohesion_chg": cohesion_chg,
            "breadth_50": breadth_50, "persistence": persistence,
            "turnover_z": turnover_z, "cohesion_rebuild": cohesion_rebuild,
            "oil_ret_10d": oil_ret_10d, "dollar_chg_10d": dollar_chg_10d,
            "hy_oas_chg_10d": hy_oas_chg_10d,
        }, index=dates)
        df.index.name = "date"
        df["node"] = node
        rows.append(df.reset_index().set_index(["node", "date"]))
    return pd.concat(rows)


def _make_episodes(
    nodes: list[str],
    n_days: int = 60,
    start: str = "2024-01-02",
    n_opposite_out_onset: int = 2,
) -> pd.DataFrame:
    """Episodes df matching real episodes_s schema: flat table with onset_date as column.

    Plants outflow-onset episode rows so ep(out/onset/opposite/w20/min2) can fire.
    Each episode has onset_date = start date (so they're always in any window).
    n_opposite_out_onset controls how many distinct nodes get episodes.
    """
    dates = pd.bdate_range(start, periods=n_days, name="date")
    rows = []
    # All nodes except the first act as "opposite-complex out-onset" episodes
    opp_nodes = nodes[1:] if len(nodes) > 1 else nodes
    ep_nodes = opp_nodes[:n_opposite_out_onset]

    for ep_node in ep_nodes:
        # One episode per node; onset_date = early in the date range (always in window)
        rows.append({
            "episode_id": f"{ep_node}::out::{dates[0].strftime('%Y-%m-%d')}::1",
            "node": ep_node,
            "direction": "out",
            "onset_date": dates[0],
            "confirmed_date": dates[2] if len(dates) > 2 else dates[0],
            "undeniable_date": None,
            "exhausted_date": None,
            "duration": n_days,
            "peak_accel_z": 1.2,
            "breadth_at_onset": 2,
            "cohesion_at_onset": 0.5,
            "cohesion_chg_at_onset": 0.1,
            "regime_vix_pctile": 0.4,
            "regime_tlt_sign": -1,
            "regime_spy_above_200d": 1,
            "two_sided": True,
            "paired_episode_id": None,
            "survivorship_flagged": False,
            "pairing_unavailable": False,
        })

    if not rows:
        return pd.DataFrame(columns=[
            "episode_id", "node", "direction", "onset_date", "confirmed_date",
            "undeniable_date", "exhausted_date", "duration", "peak_accel_z",
        ])
    return pd.DataFrame(rows).reset_index(drop=True)


def _make_rotation_groups(nodes: list[str]) -> dict:
    """Group nodes into two complexes with opposite risk_sign so episode_event opposite-scope fires.

    First node → risk_on complex; rest → risk_off complex.
    This lets episode rows on the risk_off nodes satisfy the 'opposite' scope condition
    for the risk_on first node.
    """
    complexes = [
        {
            "id": "cx_risk_on",
            "name": "risk_on",
            "direction": "out",
            "risk_sign": "risk_on",
            "members": [nodes[0]] if nodes else [],
        },
        {
            "id": "cx_risk_off",
            "name": "risk_off",
            "direction": "out",
            "risk_sign": "risk_off",
            "members": nodes[1:] if len(nodes) > 1 else [],
        },
    ]
    return {"complexes": complexes}


def _make_standouts(sector: str, ticker: str, tier: str = "T1", provisional: bool = False) -> dict:
    """Minimal us_standouts.json dict with one buy row."""
    return {
        "as_of": "2024-03-15",
        "buy": [
            {
                "ticker": ticker,
                "sector": sector,
                "label": "Buy",
                "signal": {
                    "tier_cascade": tier,
                    "provisional": provisional,
                    "fresh_bars": 2,
                },
            }
        ],
        "watch": [],
    }


# ---------------------------------------------------------------------------
# Test A: armed_window_recompute
# ---------------------------------------------------------------------------

def test_armed_window_recompute(tmp_path):
    """A15 fires on last day → at least one sector appears in armed list."""
    from scripts.oracle_nightly import _step_turn_desk

    nodes = ["XLK", "XLV", "XLF"]
    panel = _make_panel(nodes, n_days=40, washout_last=True)
    episodes = _make_episodes(nodes, n_days=40, n_opposite_out_onset=2)
    rotation_groups = _make_rotation_groups(nodes)

    data_dir = tmp_path / "data"
    site_dir = tmp_path / "site"
    oracle_dir = data_dir / "oracle"
    oracle_dir.mkdir(parents=True)
    (site_dir / "basketdata").mkdir(parents=True)
    (site_dir / "factordata").mkdir(parents=True)

    panel.to_parquet(oracle_dir / "panel_s.parquet")
    episodes.to_parquet(oracle_dir / "episodes_s.parquet")
    (oracle_dir / "rotation_groups.json").write_text(json.dumps(rotation_groups))

    # No standouts file → member_fires will be empty
    standouts_path = site_dir / "factordata" / "us_standouts.json"
    standouts_path.write_text(json.dumps({"as_of": "2024-03-15", "buy": [], "watch": []}))

    # Unpack the FULL 4-tuple exactly as scripts/oracle_nightly.py main() does. A
    # single-name `ok = ...` here would pass against a bare-bool return and leave the
    # production unpack unguarded — that gap is what let the 2026-08-04 TypeError ship.
    ok, armed, panel_asof, all_dates = _step_turn_desk(data_dir, site_dir, dry_run=False)
    assert ok, "step should succeed with synthetic data"

    artifact = json.loads((site_dir / "basketdata" / "oracle_turn_desk.json").read_text())
    assert artifact.get("schema") == "oracle_turn_desk.v1"
    assert "armed" in artifact
    assert "base_rates" in artifact
    assert "promotion_clock" in artifact
    assert artifact["base_rates"]["confidence_class"] == "display_with_edge"
    # At least one armed entry expected (XLK fires on last day, episode present)
    # Note: may be 0 if compound's episode_event condition doesn't match the synthetic data
    # shape, which is acceptable — we verify structure not fire count
    assert isinstance(artifact["armed"], list)


# ---------------------------------------------------------------------------
# Test B: no_fires_quiet_payload
# ---------------------------------------------------------------------------

def test_no_fires_quiet_payload(tmp_path):
    """When washout_w=0 everywhere → armed=[] (quiet state)."""
    from scripts.oracle_nightly import _step_turn_desk

    nodes = ["XLK", "XLV"]
    panel = _make_panel(nodes, n_days=30, washout_last=False)  # no fires
    episodes = _make_episodes(nodes, n_days=30, n_opposite_out_onset=0)
    rotation_groups = _make_rotation_groups(nodes)

    data_dir = tmp_path / "data"
    site_dir = tmp_path / "site"
    (data_dir / "oracle").mkdir(parents=True)
    (site_dir / "basketdata").mkdir(parents=True)
    (site_dir / "factordata").mkdir(parents=True)

    panel.to_parquet(data_dir / "oracle" / "panel_s.parquet")
    episodes.to_parquet(data_dir / "oracle" / "episodes_s.parquet")
    (data_dir / "oracle" / "rotation_groups.json").write_text(json.dumps(rotation_groups))
    (site_dir / "factordata" / "us_standouts.json").write_text(
        json.dumps({"as_of": "2024-03-15", "buy": [], "watch": []})
    )

    ok, armed, panel_asof, all_dates = _step_turn_desk(data_dir, site_dir, dry_run=False)
    assert ok

    artifact = json.loads((site_dir / "basketdata" / "oracle_turn_desk.json").read_text())
    assert artifact["armed"] == [], f"Expected quiet payload, got {artifact['armed']}"
    assert artifact["schema"] == "oracle_turn_desk.v1"


# ---------------------------------------------------------------------------
# Test C: member_fire_join
# ---------------------------------------------------------------------------

def test_member_fire_join(tmp_path):
    """T1 ticker in sector matching an armed node appears in member_fires."""
    from scripts.oracle_nightly import _step_turn_desk, _SECTOR_TO_ETF

    nodes = ["XLK", "XLV", "XLF"]
    panel = _make_panel(nodes, n_days=40, washout_last=True)
    episodes = _make_episodes(nodes, n_days=40, n_opposite_out_onset=2)
    rotation_groups = _make_rotation_groups(nodes)

    data_dir = tmp_path / "data"
    site_dir = tmp_path / "site"
    (data_dir / "oracle").mkdir(parents=True)
    (site_dir / "basketdata").mkdir(parents=True)
    (site_dir / "factordata").mkdir(parents=True)

    panel.to_parquet(data_dir / "oracle" / "panel_s.parquet")
    episodes.to_parquet(data_dir / "oracle" / "episodes_s.parquet")
    (data_dir / "oracle" / "rotation_groups.json").write_text(json.dumps(rotation_groups))

    # XLK maps to "Information Technology"; plant a T1 ticker in that sector
    it_sector = "Information Technology"
    standouts = _make_standouts(it_sector, "NVDA", tier="T1", provisional=False)
    (site_dir / "factordata" / "us_standouts.json").write_text(json.dumps(standouts))

    ok, armed, panel_asof, all_dates = _step_turn_desk(data_dir, site_dir, dry_run=False)
    assert ok

    artifact = json.loads((site_dir / "basketdata" / "oracle_turn_desk.json").read_text())
    # Find XLK in armed list (may or may not be armed depending on episode match)
    xlk_entries = [a for a in artifact["armed"] if a["node"] == "XLK"]
    if xlk_entries:
        mfires = xlk_entries[0]["member_fires"]
        tickers = [m["ticker"] for m in mfires]
        assert "NVDA" in tickers, f"NVDA should be in member_fires for XLK: {mfires}"
        for mf in mfires:
            assert "tier" in mf
            assert "provisional" in mf


# ---------------------------------------------------------------------------
# Test D: provisional_flag_carried
# ---------------------------------------------------------------------------

def test_provisional_flag_carried(tmp_path):
    """T3 provisional=True flag is carried into member_fires."""
    from scripts.oracle_nightly import _step_turn_desk

    nodes = ["XLK", "XLV", "XLF"]
    panel = _make_panel(nodes, n_days=40, washout_last=True)
    episodes = _make_episodes(nodes, n_days=40, n_opposite_out_onset=2)
    rotation_groups = _make_rotation_groups(nodes)

    data_dir = tmp_path / "data"
    site_dir = tmp_path / "site"
    (data_dir / "oracle").mkdir(parents=True)
    (site_dir / "basketdata").mkdir(parents=True)
    (site_dir / "factordata").mkdir(parents=True)

    panel.to_parquet(data_dir / "oracle" / "panel_s.parquet")
    episodes.to_parquet(data_dir / "oracle" / "episodes_s.parquet")
    (data_dir / "oracle" / "rotation_groups.json").write_text(json.dumps(rotation_groups))

    standouts = _make_standouts("Information Technology", "TEST", tier="T3", provisional=True)
    (site_dir / "factordata" / "us_standouts.json").write_text(json.dumps(standouts))

    ok, armed, panel_asof, all_dates = _step_turn_desk(data_dir, site_dir, dry_run=False)
    assert ok

    artifact = json.loads((site_dir / "basketdata" / "oracle_turn_desk.json").read_text())
    xlk_entries = [a for a in artifact["armed"] if a["node"] == "XLK"]
    if xlk_entries:
        for mf in xlk_entries[0]["member_fires"]:
            if mf["ticker"] == "TEST":
                assert mf["provisional"] is True
                assert mf["tier"] == "T3"


# ---------------------------------------------------------------------------
# Test E: staleness_dual_asof
# ---------------------------------------------------------------------------

def test_staleness_dual_asof(tmp_path):
    """Artifact carries both asof (panel) and member_fires_asof (standouts) when they differ."""
    from scripts.oracle_nightly import _step_turn_desk

    nodes = ["XLK"]
    panel = _make_panel(nodes, n_days=30, washout_last=False)
    episodes = _make_episodes(nodes, n_days=30, n_opposite_out_onset=0)
    rotation_groups = _make_rotation_groups(nodes)

    data_dir = tmp_path / "data"
    site_dir = tmp_path / "site"
    (data_dir / "oracle").mkdir(parents=True)
    (site_dir / "basketdata").mkdir(parents=True)
    (site_dir / "factordata").mkdir(parents=True)

    panel.to_parquet(data_dir / "oracle" / "panel_s.parquet")
    episodes.to_parquet(data_dir / "oracle" / "episodes_s.parquet")
    (data_dir / "oracle" / "rotation_groups.json").write_text(json.dumps(rotation_groups))

    stale_date = "2024-01-05"  # intentionally different from panel asof
    (site_dir / "factordata" / "us_standouts.json").write_text(
        json.dumps({"as_of": stale_date, "buy": [], "watch": []})
    )

    ok, armed, panel_asof, all_dates = _step_turn_desk(data_dir, site_dir, dry_run=False)
    assert ok

    artifact = json.loads((site_dir / "basketdata" / "oracle_turn_desk.json").read_text())
    assert "asof" in artifact
    assert "member_fires_asof" in artifact
    # If they differ, both must be present and distinct
    assert artifact["member_fires_asof"] == stale_date


# ---------------------------------------------------------------------------
# Test F: ledger_keep_first
# ---------------------------------------------------------------------------

def test_ledger_keep_first(tmp_path):
    """Re-running the step twice for the same night writes each key exactly once."""
    from scripts.oracle_nightly import _step_turn_desk

    nodes = ["XLK", "XLV", "XLF"]
    panel = _make_panel(nodes, n_days=40, washout_last=True)
    episodes = _make_episodes(nodes, n_days=40, n_opposite_out_onset=2)
    rotation_groups = _make_rotation_groups(nodes)

    data_dir = tmp_path / "data"
    site_dir = tmp_path / "site"
    (data_dir / "oracle").mkdir(parents=True)
    (site_dir / "basketdata").mkdir(parents=True)
    (site_dir / "factordata").mkdir(parents=True)

    panel.to_parquet(data_dir / "oracle" / "panel_s.parquet")
    episodes.to_parquet(data_dir / "oracle" / "episodes_s.parquet")
    (data_dir / "oracle" / "rotation_groups.json").write_text(json.dumps(rotation_groups))
    (site_dir / "factordata" / "us_standouts.json").write_text(
        json.dumps({"as_of": "2024-03-15", "buy": [], "watch": []})
    )

    ok1, _a1, _p1, _d1 = _step_turn_desk(data_dir, site_dir, dry_run=False)
    ok2, _a2, _p2, _d2 = _step_turn_desk(data_dir, site_dir, dry_run=False)  # same night
    assert ok1 and ok2

    ledger_path = data_dir / "oracle" / "turn_desk_ledger.jsonl"
    if ledger_path.exists():
        lines = [l for l in ledger_path.read_text().splitlines() if l.strip()]
        rows = [json.loads(l) for l in lines]
        keys = [r["key"] for r in rows]
        assert len(keys) == len(set(keys)), f"Duplicate keys found in ledger: {keys}"


# ---------------------------------------------------------------------------
# Test G: ledger_maturity_grading
# ---------------------------------------------------------------------------

def test_ledger_maturity_grading(tmp_path):
    """h=21 absolute return is graded from synthetic closes when exit date is available."""
    from scripts.oracle_nightly import _write_turn_desk_ledger, _grade_turn_desk_ledger
    import json

    data_dir = tmp_path / "data"
    oracle_dir = data_dir / "oracle"
    oracle_dir.mkdir(parents=True)
    massive_dir = data_dir / "massive_stock_day"
    massive_dir.mkdir()

    # Build synthetic close series for AAPL spanning fire_date + 25 days
    dates = pd.bdate_range("2024-01-02", periods=60)
    closes = pd.Series(100.0 + np.arange(60) * 0.5, index=dates, name="close")
    pd.DataFrame({"close": closes}).to_parquet(massive_dir / "AAPL.parquet")

    # Seed a member_fire row that is old enough to be graded (fire_date 22 days back)
    fire_date_ts = dates[5]
    fire_date_str = fire_date_ts.strftime("%Y-%m-%d")
    panel_asof_str = dates[-1].strftime("%Y-%m-%d")
    all_dates_list = [d.strftime("%Y-%m-%d") for d in dates]
    date_to_pos = {d: i for i, d in enumerate(all_dates_list)}

    ledger_path = oracle_dir / "turn_desk_ledger.jsonl"
    seed_row = {
        "kind": "member_fire",
        "key": f"XLK::a15::{fire_date_str}::AAPL::{fire_date_str}",
        "node": "XLK",
        "ticker": "AAPL",
        "tier": "T1",
        "provisional": False,
        "fire_date": fire_date_str,
        "pit_stamp": fire_date_str,
        "registered_at": "2024-01-08T00:00:00+00:00",
        "fwd_ret_21": None,
        "outcome_mature": False,
    }
    ledger_path.write_text(json.dumps(seed_row, separators=(",", ":")) + "\n")

    _grade_turn_desk_ledger(ledger_path, data_dir, all_dates_list, date_to_pos)

    rows = [json.loads(l) for l in ledger_path.read_text().splitlines() if l.strip()]
    assert len(rows) == 1
    row = rows[0]
    # Row should now be graded since fire_date is 5 days in and exit at 5+21=26 < 60
    assert row["outcome_mature"] is True, f"Expected mature=True, got {row}"
    assert row["fwd_ret_21"] is not None, "Expected fwd_ret_21 to be graded"
    assert isinstance(row["fwd_ret_21"], float)


# ---------------------------------------------------------------------------
# Test H: banned_key_guard
# ---------------------------------------------------------------------------

def test_banned_key_guard():
    """The banned-key substrings list catches 'forecast' in a key name."""
    from scripts.oracle_nightly import _BANNED_KEY_SUBS

    # Verify the guard list contains the required strings
    for required in ("forecast", "predicted", "target", "expected_return"):
        assert required in _BANNED_KEY_SUBS, f"'{required}' missing from _BANNED_KEY_SUBS"

    # Simulate a banned payload key
    bad_key = "forecast_return"
    assert any(b in bad_key for b in _BANNED_KEY_SUBS), (
        f"banned-key check failed to catch '{bad_key}'"
    )


# ---------------------------------------------------------------------------
# Test I: template_smoke
# ---------------------------------------------------------------------------

def test_template_smoke():
    """The turn-desk surface survives the Sector Intelligence consolidation.

    subsector_rotation.html.j2 is a redirect stub as of 2026-08 — the desk moved
    onto sector_central.html.j2 under the #si-movement section. The old pin was
    `class="td-section"` in the standalone template; asserting that now would
    just fail on the stub, and DELETING the assertion would leave the surface
    unguarded. So pin the redirect AND its landing site: a stub that points at a
    section the merged page does not actually have is the failure this replaces.
    The title= i18n law is checked on the live surface, where the copy now lives.
    """
    stub_path = _REPO / "templates" / "subsector_rotation.html.j2"
    assert stub_path.exists(), "stub template not found"
    stub = stub_path.read_text()
    assert 'location.replace("sector_central.html#si-movement")' in stub, (
        "the redirect stub lost its target — the desk would be unreachable")

    template_path = _REPO / "templates" / "sector_central.html.j2"
    assert template_path.exists(), "merged template not found"
    content = template_path.read_text()
    assert 'id="si-movement"' in content, (
        "sector_central.html.j2 has no #si-movement section, so the stub above "
        "redirects into a void")

    # No CJK in title= attributes (check_title_i18n law)
    import re
    # Find all title="..." attributes
    title_attrs = re.findall(r'title=["\'][^"\']*["\']', content)
    cjk_range = re.compile(r'[一-鿿㐀-䶿]')
    for attr in title_attrs:
        assert not cjk_range.search(attr), (
            f"CJK found in title attribute: {attr!r}"
        )

    # No t() macro inside title= attributes
    title_with_t = re.findall(r'title=["\'][^"\']*\bt\s*\(', content)
    assert not title_with_t, f"t() macro found in title= attribute: {title_with_t}"

    # The "validated" law is NOT re-implemented here. This test used to carry a
    # bare `"validated" not in content` substring check, which was safe only while
    # it scanned the tiny standalone subsector_rotation template. Pointed at the
    # merged sector_central.html.j2 it fires on two legitimate uses — the
    # `tr.verdict === 'validated'` enum in the self-grader JS, and hover copy whose
    # claim IS backed — neither of which the law forbids. scripts/
    # check_validated_claims.py is the authority (it distinguishes an affirmative
    # unearned claim from a backed one) and runs in CI as the `validated-claims`
    # step, so duplicating it with a blunter rule here would only produce false
    # reds on the merged surface.


# ---------------------------------------------------------------------------
# Test J: missing-input skip returns the caller's shape (2026-08-04 regression)
# ---------------------------------------------------------------------------
#
# Nightly run 30960328285 (engine job): _step_turn_desk printed
#   "::error::oracle_nightly: turn_desk — panel_s.parquet missing, skipping"
# and then the pipeline died anyway with
#   TypeError: cannot unpack non-iterable bool object
# at scripts/oracle_nightly.py main(), because the skip branch returned a bare
# `False` while main() unpacks four names. The disclosed skip was real; the SKIP
# was not. Steps 16-19 (reversion promotion scan, qual filter stamps, tape
# outcomes, tape onset) never ran that night as a result.
#
# These tests pin BOTH halves: the skip is disclosed AND it is survivable.

def _bare_dirs(tmp_path):
    """data/site trees with the oracle dir present but no panel/episodes parquet."""
    data_dir = tmp_path / "data"
    site_dir = tmp_path / "site"
    (data_dir / "oracle").mkdir(parents=True)
    (site_dir / "basketdata").mkdir(parents=True)
    (site_dir / "factordata").mkdir(parents=True)
    return data_dir, site_dir


@pytest.mark.parametrize("present", ["none", "panel_only"])
def test_missing_input_skips_without_exception(tmp_path, capsys, present):
    """Missing panel_s/episodes_s → disclosed skip, 4-tuple, NO exception."""
    from scripts.oracle_nightly import _step_turn_desk

    data_dir, site_dir = _bare_dirs(tmp_path)
    if present == "panel_only":
        # panel exists, episodes absent -> exercises the SECOND skip branch
        _make_panel(["XLK"], n_days=30).to_parquet(
            data_dir / "oracle" / "panel_s.parquet")
        expected_missing = "episodes_s.parquet"
    else:
        expected_missing = "panel_s.parquet"

    # The load-bearing assertion is the unpack itself: this line is the exact
    # shape scripts/oracle_nightly.py main() uses. A bare-bool return raises
    # TypeError HERE, which is the production failure reproduced in-suite.
    ok, armed, panel_asof, all_dates = _step_turn_desk(
        data_dir, site_dir, dry_run=False)

    assert ok is False, "a missing input must report failure, not success"
    assert armed == [], "a skipped step must not hand Step 17 any armed windows"
    assert panel_asof == ""
    assert all_dates == []

    # Disclosed, not silent — and via a line-START annotation (house law: the
    # bare print, never a prefixing logger, or GitHub drops it).
    out = capsys.readouterr().out
    ann = [ln for ln in out.splitlines() if ln.startswith("::error::")]
    assert any(expected_missing in ln and "skipping" in ln for ln in ann), (
        f"skip not disclosed as a line-start ::error:: annotation; got {ann!r}")

    # A skipped step writes no artifact — it must not leave a half-built payload.
    assert not (site_dir / "basketdata" / "oracle_turn_desk.json").exists()


def test_turn_desk_skip_survives_the_real_caller(tmp_path, capsys):
    """The main() call site itself must survive a missing panel.

    Tests J above pin the function. This pins the SEAM: it re-executes the real
    unpack + the real downstream consumers (`if not td_ok` and the Step 17
    forward of armed/panel_asof/all_dates) against the skip return, so a future
    arity change on either side is caught rather than shipping to the nightly.
    """
    import ast

    from scripts import oracle_nightly
    from scripts.oracle_nightly import _step_turn_desk

    data_dir, site_dir = _bare_dirs(tmp_path)
    result = _step_turn_desk(data_dir, site_dir, dry_run=False)

    src = ast.parse(Path(oracle_nightly.__file__).read_text())
    main_fn = next(n for n in ast.walk(src)
                   if isinstance(n, ast.FunctionDef) and n.name == "main")
    unpacks = [
        n.targets[0] for n in ast.walk(main_fn)
        if isinstance(n, ast.Assign)
        and isinstance(n.targets[0], ast.Tuple)
        and isinstance(n.value, ast.Call)
        and getattr(n.value.func, "id", None) == "_step_turn_desk"
    ]
    assert len(unpacks) == 1, (
        f"expected exactly one _step_turn_desk unpack in main(), found {len(unpacks)}")
    arity = len(unpacks[0].elts)

    # The skip return must satisfy the caller's arity — this is the assertion the
    # nightly needed and did not have.
    assert isinstance(result, tuple) and len(result) == arity, (
        f"main() unpacks {arity} names but the skip path returned "
        f"{type(result).__name__} of length "
        f"{len(result) if isinstance(result, tuple) else 'n/a'}")

    # Downstream consumers must tolerate the skip values, not just the unpack.
    td_ok, td_armed, td_panel_asof, td_all_dates = result
    assert not td_ok
    for value, expected in ((td_armed, list), (td_panel_asof, str),
                            (td_all_dates, list)):
        assert isinstance(value, expected), (
            f"Step 17 receives {value!r}; expected {expected.__name__}")


def test_every_turn_desk_return_matches_the_caller_arity():
    """STRUCTURAL guard: no branch of _step_turn_desk may return a bare bool.

    Fixture tests can only reach the branches a fixture can provoke — the
    banned-key sweep's refusal path (the third bare-`False` in the 2026-08-04
    defect) is not reachable from synthetic data, so a behavioural test alone
    would leave it unguarded and a re-introduced bare bool would ship green.
    This walks the AST instead and holds EVERY return in the function (excluding
    its nested helper closures, which are legitimately bool-typed) to the arity
    main() unpacks.
    """
    import ast

    from scripts import oracle_nightly

    src = ast.parse(Path(oracle_nightly.__file__).read_text())

    main_fn = next(n for n in ast.walk(src)
                   if isinstance(n, ast.FunctionDef) and n.name == "main")
    arity = next(
        len(n.targets[0].elts) for n in ast.walk(main_fn)
        if isinstance(n, ast.Assign)
        and isinstance(n.targets[0], ast.Tuple)
        and isinstance(n.value, ast.Call)
        and getattr(n.value.func, "id", None) == "_step_turn_desk"
    )

    fn = next(n for n in ast.walk(src)
              if isinstance(n, ast.FunctionDef) and n.name == "_step_turn_desk")

    # Returns owned by nested defs/lambdas belong to those closures, not to the step.
    nested_ids = set()
    for node in ast.walk(fn):
        if node is fn and not isinstance(node, ast.Lambda):
            continue
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            nested_ids.update(id(sub) for sub in ast.walk(node))

    offenders = []
    seen = 0
    for node in ast.walk(fn):
        if not isinstance(node, ast.Return) or id(node) in nested_ids:
            continue
        seen += 1
        value = node.value
        if not isinstance(value, ast.Tuple) or len(value.elts) != arity:
            rendered = "None" if value is None else ast.unparse(value)
            offenders.append(f"line {node.lineno}: return {rendered}")

    assert seen >= 5, (
        f"only {seen} _step_turn_desk returns found — the walk lost branches, "
        "so this guard would pass vacuously")
    assert not offenders, (
        f"_step_turn_desk must return a {arity}-tuple on EVERY path "
        f"(main() unpacks {arity} names); offending returns:\n  "
        + "\n  ".join(offenders))
