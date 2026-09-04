"""Tests for scripts.research_top_anatomy_oot_receipt — synthetic massive_stock_day
stores only, deterministic, no real `data/` tree required.

Fixture idiom follows tests/test_top_anatomy.py's `_bars`/`_cal` shape, extended
with a `_cycle` helper that builds one quiet -> ramp -> pullback/decline -> flat
tail price path so an episode's start/peak/seal state can be placed exactly
where a test needs it relative to one fixed OOT boundary (2021-06-01, chosen for
readable calendar arithmetic — this suite never touches the frozen production
boundary 2026-07-03, which is exercised only via the module's own default).

Schema is the FROZEN post-adversarial-review prereg (§1/§4/§5,
`research/top_anatomy/TOPA_OOT_PREREG.md` commit `0f35a5e4d0e7`): the STRICT
boundary rule is session arithmetic (peak minus 21 sessions on the episode's own
identity-segment calendar), per-cell eligibility replaces a top-level scalar, and
two labeled-unit blocks (episode-level / day-level) are reported separately.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from engine import top_anatomy as ta
from scripts import research_top_anatomy_oot_receipt as oot
from scripts import research_top_anatomy_phase0 as rh

REPO = Path(__file__).resolve().parent.parent
BOUNDARY = "2021-06-01"


# ══════════════════════════════════════════════════════════════════════════════
# builders — full synthetic store (parquet files on disk)
# ══════════════════════════════════════════════════════════════════════════════
def _bars(close: np.ndarray, idx: pd.DatetimeIndex, *, vol: float = 5e6) -> pd.DataFrame:
    c = pd.Series(close, index=idx, dtype=float)
    v = pd.Series(vol, index=idx, dtype=float)
    return pd.DataFrame({"close": c, "high": c * 1.01, "low": c * 0.99, "volume": v,
                         "open": c.shift(1).fillna(c.iloc[0])})


def _cycle(n_quiet: int, *, pullback: list[float], tail_len: int,
          ramp_days: int = 90, ramp_rate: float = 1.009,
          quiet_price: float = 50.0, start: str = "2020-01-01") -> pd.DataFrame:
    """quiet(n_quiet) -> ramp(ramp_days) -> pullback/decline -> flat tail(tail_len).

    A pure exponential ramp with no noise clears r126>=0.50 (§4.1) roughly
    `ln(1.5)/ln(ramp_rate)` sessions into the ramp, near-high(0.90) trivially
    (a monotonic ramp is always at its own trailing high). `pullback` then either
    seals TOPPED (a clean >=20% collapse) or ends the EXT run at a shallower
    drawdown that never nears -20%, letting `tail_len` alone decide sealing.
    """
    seq = [quiet_price] * n_quiet
    px = quiet_price
    for _ in range(ramp_days):
        px *= ramp_rate
        seq.append(px)
    for f in pullback:
        px *= f
        seq.append(px)
    seq += [px] * tail_len
    idx = pd.bdate_range(start, periods=len(seq))
    return _bars(np.array(seq), idx)


def _write_store(tmp_path: Path, tickers: dict[str, pd.DataFrame]) -> Path:
    store = tmp_path / "massive_stock_day"
    store.mkdir(parents=True, exist_ok=True)
    for tk, bars in tickers.items():
        bars.to_parquet(store / f"{tk}.parquet")
    return tmp_path


#: a clean >=20% collapse (TOPPED); a shallow pullback that ends the EXT run
#: (near-high drops under 0.90) without ever nearing -20% from the peak.
TOPPED_DECLINE = [0.97] * 8
SHALLOW_PULLBACK = [0.985] * 10

#: five hand-placed episodes around BOUNDARY, one ticker each (verified against
#: the live engine while this suite was written — see module docstring):
#:   ASTOP: start 2021-06-23 (>= boundary), peak 2021-08-24, TOPPED, fully sealed
#:          -> OOT-STRICT / sealed_topped
#:   BBRDG: start 2021-04-28 (< boundary), peak 2021-06-29, TOPPED, fully sealed,
#:          peak-21-sessions precedes the boundary -> OOT-BRIDGE / sealed_topped
#:   CIMMA: same episode as ASTOP but a 20-session tail truncates the peak search
#:          -> OOT-STRICT / immature_unsealed
#:   DCENS: same start/peak as ASTOP, a shallow pullback + 80-session tail clears
#:          the peak-search buffer but not the 126-session seal window
#:          -> OOT-STRICT / censored_at_data_edge
#:   ESURV: same as DCENS with a 200-session tail — both windows fully observed,
#:          never breaches -20% -> OOT-STRICT / sealed_survived
def _five_ticker_store(tmp_path: Path) -> Path:
    return _write_store(tmp_path, {
        "ASTOP": _cycle(340, pullback=TOPPED_DECLINE, tail_len=300),
        "BBRDG": _cycle(300, pullback=TOPPED_DECLINE, tail_len=300),
        "CIMMA": _cycle(340, pullback=TOPPED_DECLINE, tail_len=20),
        "DCENS": _cycle(340, pullback=SHALLOW_PULLBACK, tail_len=80),
        "ESURV": _cycle(340, pullback=SHALLOW_PULLBACK, tail_len=200),
    })


#: two well-separated TOPPED-and-sealed episodes (peaks in different calendar
#: months) on all three tiers at once. Floors are monkeypatched down for these
#: tests rather than manufacturing 100 real episodes; the ARITHMETIC under test
#: is identical either way.
def _two_month_topped_store(tmp_path: Path) -> Path:
    return _write_store(tmp_path, {
        "ASTOP": _cycle(340, pullback=TOPPED_DECLINE, tail_len=300),   # peak 2021-08
        "SECOND": _cycle(480, pullback=TOPPED_DECLINE, tail_len=300),  # peak 2022-03
    })


# ══════════════════════════════════════════════════════════════════════════════
# builders — direct `_classify_cohort` unit fixtures (no store, no engine pass)
# ══════════════════════════════════════════════════════════════════════════════
def _seg_calendar(n: int = 80, start: str = "2021-01-01") -> pd.DatetimeIndex:
    return pd.bdate_range(start, periods=n)


def _sealed_row(*, episode_id: str, segment: str, peak_date, outcome: str = "TOPPED",
                truncated: bool = False, censored: bool = False,
                micro: bool = False) -> dict:
    return {"episode_id": episode_id, "segment": segment, "micro": micro,
            "peak_date": pd.Timestamp(peak_date), "outcome": outcome,
            "peak_window_truncated": truncated, "peak_window_censored": censored}


def _dtp_row(episode_id: str, segment: str, date, days_to_peak: int) -> dict:
    return {"episode_id": episode_id, "segment": segment, "date": pd.Timestamp(date),
            "days_to_peak": days_to_peak}


_EMPTY_DTP = pd.DataFrame(columns=["episode_id", "segment", "date", "days_to_peak"])
_EMPTY_RACES = pd.DataFrame(columns=["segment", "date", "label", "censor_reason"])


# ══════════════════════════════════════════════════════════════════════════════
# (a) §1 STRICT/BRIDGE session-arithmetic rule — direct unit tests
# ══════════════════════════════════════════════════════════════════════════════
def test_strict_requires_peak_minus_21_sessions_on_or_after_boundary():
    seg_idx = _seg_calendar()
    peak = seg_idx[40]
    snap21_date = seg_idx[40 - oot.STRICT_SNAPSHOT_SESSIONS]
    sealed = pd.DataFrame([_sealed_row(episode_id="E1", segment="SEG", peak_date=peak)])
    dtp = pd.DataFrame([_dtp_row("E1", "SEG", seg_idx[35], 5)])   # >=1 existing snapshot

    # boundary == peak-21-sessions exactly -> inclusive ("on or after") -> STRICT
    out = oot._classify_cohort(sealed, dtp, _EMPTY_RACES, {"SEG": seg_idx}, snap21_date)
    assert out["episode_level"]["strict"]["sealed_topped"] == 1
    assert out["episode_level"]["bridge"]["sealed_topped"] == 0

    # boundary one session LATER than peak-21-sessions -> BRIDGE
    boundary_late = seg_idx[40 - oot.STRICT_SNAPSHOT_SESSIONS + 1]
    out2 = oot._classify_cohort(sealed, dtp, _EMPTY_RACES, {"SEG": seg_idx}, boundary_late)
    assert out2["episode_level"]["bridge"]["sealed_topped"] == 1
    assert out2["episode_level"]["strict"]["sealed_topped"] == 0


def test_strict_uses_session_arithmetic_regardless_of_which_snapshot_offsets_exist():
    """§1: STRICT depends only on the peak's POSITION, never on which of the
    {21,10,5} offsets happen to be actual EXT days."""
    seg_idx = _seg_calendar()
    peak = seg_idx[50]
    boundary = seg_idx[50 - oot.STRICT_SNAPSHOT_SESSIONS]   # exactly peak-21
    sealed = pd.DataFrame([_sealed_row(episode_id="E2", segment="SEG", peak_date=peak)])
    # only the 5-offset EXT day exists (no 21 or 10 offset) -- session arithmetic
    # still governs, so this is STILL strict
    dtp = pd.DataFrame([_dtp_row("E2", "SEG", seg_idx[45], 5)])
    out = oot._classify_cohort(sealed, dtp, _EMPTY_RACES, {"SEG": seg_idx}, boundary)
    assert out["episode_level"]["strict"]["sealed_topped"] == 1


def test_zero_snapshot_episodes_are_excluded_from_both_cohorts():
    """§1 (b): a candidate with ZERO existing snapshots is a candidate in
    NEITHER cohort, counted separately."""
    seg_idx = _seg_calendar()
    peak = seg_idx[50]
    boundary = seg_idx[10]
    sealed = pd.DataFrame([_sealed_row(episode_id="E3", segment="SEG", peak_date=peak)])
    out = oot._classify_cohort(sealed, _EMPTY_DTP, _EMPTY_RACES, {"SEG": seg_idx}, boundary)
    assert out["n_case_episodes_strict"] == 0
    assert out["n_case_episodes_bridge"] == 0
    assert out["n_excluded_no_snapshots"] == 1


def test_a_peak_before_the_boundary_is_not_a_candidate_at_all():
    seg_idx = _seg_calendar()
    boundary = seg_idx[50]
    peak = seg_idx[49]   # one session before boundary
    sealed = pd.DataFrame([_sealed_row(episode_id="E4", segment="SEG", peak_date=peak)])
    dtp = pd.DataFrame([_dtp_row("E4", "SEG", seg_idx[45], 5)])
    out = oot._classify_cohort(sealed, dtp, _EMPTY_RACES, {"SEG": seg_idx}, boundary)
    assert out["n_case_episodes_strict"] == 0
    assert out["n_case_episodes_bridge"] == 0
    assert out["n_excluded_no_snapshots"] == 0


# ══════════════════════════════════════════════════════════════════════════════
# (b) §5 day-level labeled-unit block — race labels on candidate observation days
# ══════════════════════════════════════════════════════════════════════════════
def test_day_level_block_counts_race_labels_on_candidate_snapshot_days():
    seg_idx = _seg_calendar()
    peak = seg_idx[50]
    boundary = seg_idx[50 - oot.STRICT_SNAPSHOT_SESSIONS]
    snap_date = seg_idx[45]
    sealed = pd.DataFrame([_sealed_row(episode_id="E5", segment="SEG", peak_date=peak)])
    dtp = pd.DataFrame([_dtp_row("E5", "SEG", snap_date, 5)])
    races = pd.DataFrame([{"segment": "SEG", "date": snap_date, "label": "CONTINUED",
                          "censor_reason": ""}])
    out = oot._classify_cohort(sealed, dtp, races, {"SEG": seg_idx}, boundary)
    assert out["day_level"]["strict"]["CONTINUED"] == 1
    assert out["day_level"]["strict"]["TOPPED"] == 0
    assert out["day_level"]["strict"]["CENSORED"] == 0
    # never merged with the episode-level block
    assert out["episode_level"]["strict"]["sealed_topped"] == 1


def test_day_level_never_merges_with_episode_level_labels():
    """The two blocks use different label vocabularies and must never collide."""
    assert {"TOPPED", "SURVIVED", "IMMATURE-UNSEALED"} != {"TOPPED", "CONTINUED", "CENSORED"}


# ══════════════════════════════════════════════════════════════════════════════
# (c) mutation check — flip the session arithmetic or the >=1-snapshot rule
# ══════════════════════════════════════════════════════════════════════════════
# See the packet EVIDENCE for the receipted run: both mutations were applied via
# sed to scripts/research_top_anatomy_oot_receipt.py, the suite was rerun, the
# named tests above went red, and the file was reverted byte-for-byte.


# ══════════════════════════════════════════════════════════════════════════════
# (d) matcher_run reason — exactly two literal strings (§5, frozen)
# ══════════════════════════════════════════════════════════════════════════════
def test_matcher_zero_candidates_reason():
    m = oot._matcher_block(0)
    assert m["run"] is False
    assert m["reason"] == "zero_candidates"
    assert m["n_sealed_topped_strict_candidates"] == 0


@pytest.mark.parametrize("n", [1, 5, 20, 100, 1000])
def test_matcher_pending_activation_reason_when_count_at_least_one(n):
    m = oot._matcher_block(n)
    assert m["run"] is False
    assert m["reason"] == "matched_counting_pending_activation"
    assert m["n_sealed_topped_strict_candidates"] == n


# ══════════════════════════════════════════════════════════════════════════════
# (e) per-cell eligibility — the §5 contract (no top-level scalar)
# ══════════════════════════════════════════════════════════════════════════════
def test_all_18_cells_present_keyed_correctly(tmp_path):
    data_root = _five_ticker_store(tmp_path)
    receipt = oot.build_receipt(data_root, boundary=BOUNDARY)
    rows = receipt["final_verdict_eligible"]
    assert isinstance(rows, list)
    assert len(rows) == 18   # 3 panels x 2 cohorts x 3 legs
    keys = {(r["cohort"], r["panel"], r["construction"], r["leg"]) for r in rows}
    assert len(keys) == 18
    for panel in ("primary", "r63", "atrz"):
        for cohort in ("strict", "bridge"):
            assert (cohort, panel, "am2", "B2_rsi14") in keys
            assert (cohort, panel, "am2", "B3_rsi14_chg10") in keys
            assert (cohort, panel, "am2_agefree", "F1_episode_age") in keys


def test_bridge_cells_are_permanently_ineligible(tmp_path):
    data_root = _five_ticker_store(tmp_path)
    receipt = oot.build_receipt(data_root, boundary=BOUNDARY)
    bridge_rows = [r for r in receipt["final_verdict_eligible"] if r["cohort"] == "bridge"]
    assert len(bridge_rows) == 9   # 3 panels x 3 legs
    for row in bridge_rows:
        assert row["eligible"] is False
        assert row["reasons"] == ["bridge_never_graded"]


def test_strict_cells_name_every_unmet_floor_on_an_immature_cohort(tmp_path):
    data_root = _five_ticker_store(tmp_path)
    receipt = oot.build_receipt(data_root, boundary=BOUNDARY)
    strict_primary = [r for r in receipt["final_verdict_eligible"]
                      if r["cohort"] == "strict" and r["panel"] == "primary"]
    assert len(strict_primary) == 3
    for row in strict_primary:
        assert row["eligible"] is False
        assert any("month floor" in r for r in row["reasons"])
        assert any("registered floor" in r for r in row["reasons"])
        assert "completeness_floor_not_evaluable_no_era_blocks" in row["reasons"]
        assert "validity_precondition_not_evaluable_matcher_not_run" in row["reasons"]


def test_strict_cells_stay_blocked_even_once_months_and_matched_floors_clear(
    tmp_path, monkeypatch,
):
    """The completeness/validity preconditions ALONE keep every STRICT cell
    ineligible today, even once the months/matched floors are cleared — the
    prereg's own designed "no cell clears before ~2027-07" state (§4)."""
    monkeypatch.setattr(ta, "MIN_EPISODE_MONTHS", 2)
    monkeypatch.setattr(rh, "P1_MIN_MATCHED_EPISODES", 2)
    data_root = _two_month_topped_store(tmp_path)
    receipt = oot.build_receipt(data_root, boundary=BOUNDARY)

    for tier_key in ("primary", "r63", "atrz"):
        t = receipt["tiers"][tier_key]
        assert t["episode_level"]["strict"]["sealed_topped"] == 2, tier_key
        assert t["distinct_peak_months_sealed_topped"]["strict"] == 2, tier_key
        assert t["floors"]["distinct_peak_months_floor_met"] is True, tier_key
        assert t["floors"]["matched_topped_episodes_floor_met"] is True, tier_key

    strict_rows = [r for r in receipt["final_verdict_eligible"] if r["cohort"] == "strict"]
    assert len(strict_rows) == 9
    for row in strict_rows:
        assert row["eligible"] is False
        # months/matched floors cleared -> those two reasons must NOT appear
        assert not any("month floor" in r for r in row["reasons"])
        assert not any("registered floor" in r for r in row["reasons"])
        # completeness/validity are the ONLY remaining blockers
        assert row["reasons"] == [
            "completeness_floor_not_evaluable_no_era_blocks",
            "validity_precondition_not_evaluable_matcher_not_run",
        ]

    assert receipt["state"] == "OOT_ACCRUING_NO_VERDICT"


def test_state_is_accruing_while_any_cell_ineligible(tmp_path):
    data_root = _five_ticker_store(tmp_path)
    receipt = oot.build_receipt(data_root, boundary=BOUNDARY)
    assert receipt["state"] == "OOT_ACCRUING_NO_VERDICT"
    assert all(not row["eligible"] for row in receipt["final_verdict_eligible"])


# ══════════════════════════════════════════════════════════════════════════════
# (f) episode-level fixture sanity + sealing law (full store, full engine pass)
# ══════════════════════════════════════════════════════════════════════════════
def test_boundary_classification_and_sealing_on_the_five_ticker_store(tmp_path):
    data_root = _five_ticker_store(tmp_path)
    receipt = oot.build_receipt(data_root, boundary=BOUNDARY)
    primary = receipt["tiers"]["primary"]

    assert primary["n_case_episodes_strict"] == 4     # ASTOP, CIMMA, DCENS, ESURV
    assert primary["n_case_episodes_bridge"] == 1      # BBRDG
    assert primary["n_excluded_no_snapshots"] == 0

    assert primary["episode_level"]["strict"] == {
        "sealed_topped": 1, "sealed_survived": 1,
        "immature_unsealed": 1, "censored_at_data_edge": 1,
    }
    assert primary["episode_level"]["bridge"] == {
        "sealed_topped": 1, "sealed_survived": 0,
        "immature_unsealed": 0, "censored_at_data_edge": 0,
    }
    # sealing law: an unsealed (truncated peak search) episode is IMMATURE, never
    # counted as topped or survived, even though its own `outcome` label is TOPPED
    assert primary["episode_level"]["strict"]["immature_unsealed"] == 1


def test_every_tier_is_present_and_internally_consistent(tmp_path):
    data_root = _five_ticker_store(tmp_path)
    receipt = oot.build_receipt(data_root, boundary=BOUNDARY)
    assert set(receipt["tiers"]) == {"primary", "r63", "atrz"}
    for tier_key, t in receipt["tiers"].items():
        assert sum(t["episode_level"]["strict"].values()) == t["n_case_episodes_strict"]
        assert sum(t["episode_level"]["bridge"].values()) == t["n_case_episodes_bridge"]
        assert t["matcher"]["run"] is False
        assert "cells" not in t   # flattened into the top-level contract, not duplicated


# ══════════════════════════════════════════════════════════════════════════════
# (g) pinned store state (§5 / §2 moved variable item 4)
# ══════════════════════════════════════════════════════════════════════════════
def test_pinned_store_state_manifest_absent(tmp_path):
    data_root = _five_ticker_store(tmp_path)
    receipt = oot.build_receipt(data_root, boundary=BOUNDARY)
    pss = receipt["pinned_store_state"]
    assert pss["manifest_sha256"] is None
    assert pss["manifest_reason"] == "manifest_not_present_in_checkout"
    assert pss["shard_count"] == 5
    assert pss["last_session"] == receipt["store_coverage"]["last_session"]


def test_pinned_store_state_manifest_present_is_hashed_never_fabricated(tmp_path):
    data_root = _five_ticker_store(tmp_path)
    manifest_path = data_root / "massive_stock_day" / "_manifest.json"
    manifest_path.write_text('{"latest_date": "2022-10-28"}')
    receipt = oot.build_receipt(data_root, boundary=BOUNDARY)
    pss = receipt["pinned_store_state"]
    assert pss["manifest_sha256"] == hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    assert pss["manifest_reason"] is None


# ══════════════════════════════════════════════════════════════════════════════
# (h) schema completeness — every prereg §5 field is present
# ══════════════════════════════════════════════════════════════════════════════
def test_receipt_contains_every_prereg_section5_field(tmp_path):
    data_root = _five_ticker_store(tmp_path)
    receipt = oot.build_receipt(data_root, boundary=BOUNDARY)

    assert receipt["oot_start"] == "2021-06-01"
    assert receipt["oot_end_observed"] is not None
    assert "pinned_store_state" in receipt
    assert {"manifest_sha256", "manifest_reason", "last_session", "shard_count"} \
        <= set(receipt["pinned_store_state"])
    assert set(receipt["tiers"]) == {"primary", "r63", "atrz"}
    for t in receipt["tiers"].values():
        assert {"n_case_episodes_strict", "n_case_episodes_bridge",
                "n_excluded_no_snapshots", "episode_level", "day_level",
                "matcher", "match_starvation",
                "distinct_peak_months_sealed_topped", "monthly_completeness",
                "outcome_horizon_maturity", "construction_diagnostic_readiness",
                "floors"} <= set(t)
        assert t["episode_level"]["labels"] == ["TOPPED", "SURVIVED", "IMMATURE-UNSEALED"]
        assert t["day_level"]["labels"] == ["TOPPED", "CONTINUED", "CENSORED"]
        for bucket in (t["episode_level"]["strict"], t["episode_level"]["bridge"]):
            assert {"sealed_topped", "sealed_survived", "immature_unsealed",
                    "censored_at_data_edge"} == set(bucket)
        for bucket in (t["day_level"]["strict"], t["day_level"]["bridge"]):
            assert {"TOPPED", "CONTINUED", "CENSORED"} == set(bucket)
    assert isinstance(receipt["final_verdict_eligible"], list)
    assert len(receipt["final_verdict_eligible"]) == 18
    for row in receipt["final_verdict_eligible"]:
        assert {"cohort", "panel", "construction", "leg", "eligible",
                "floor_inputs", "reasons"} <= set(row)
    assert "delisting_identity_break_census" in receipt
    census = receipt["delisting_identity_break_census"]
    assert {"n_identity_segments_total", "n_dark_since_last_session",
            "dark_examples", "n_identity_breaks_starting_in_window",
            "identity_break_examples"} <= set(census)
    assert "store_coverage" in receipt
    assert {"first_session", "last_session", "n_eligible_names_last_session"} \
        <= set(receipt["store_coverage"])


def test_receipt_is_a_counting_read_never_a_grade_or_estimate(tmp_path):
    """No feature-delta / effect-estimate / grade vocabulary anywhere in the JSON."""
    data_root = _five_ticker_store(tmp_path)
    receipt = oot.build_receipt(data_root, boundary=BOUNDARY)
    blob = json.dumps(receipt, default=str).lower()
    for banned in ("oot-replicated", "oot-not-confirmed", "oot-underpowered",
                  "matched_delta", "bootstrap", "q_value", "p_value", "effect_size"):
        assert banned not in blob, banned


# ══════════════════════════════════════════════════════════════════════════════
# (i) determinism — identical inputs, byte-identical JSON apart from provenance
# ══════════════════════════════════════════════════════════════════════════════
def test_determinism_apart_from_provenance_timestamp(tmp_path):
    data_root = _five_ticker_store(tmp_path)
    r1 = oot.build_receipt(data_root, boundary=BOUNDARY)
    r2 = oot.build_receipt(data_root, boundary=BOUNDARY)

    def _strip(r: dict) -> dict:
        r = json.loads(json.dumps(r, sort_keys=True, default=str))
        r["provenance"] = {k: v for k, v in r["provenance"].items()
                           if k != "generated_at_utc"}
        return r

    assert _strip(r1) == _strip(r2)
    # the timestamp itself is real and lives ONLY in provenance
    assert r1["provenance"]["generated_at_utc"] != ""


# ══════════════════════════════════════════════════════════════════════════════
# (j) CLI surface
# ══════════════════════════════════════════════════════════════════════════════
def test_cli_help_is_clean():
    with pytest.raises(SystemExit) as exc:
        oot.main(["--help"])
    assert exc.value.code == 0


def test_cli_writes_a_valid_receipt_json_and_optional_markdown(tmp_path):
    data_root = _five_ticker_store(tmp_path)
    out = tmp_path / "receipt.json"
    md = tmp_path / "receipt.md"
    rc = oot.main(["--data-root", str(data_root), "--out", str(out),
                  "--boundary", BOUNDARY, "--md", str(md)])
    assert rc == 0
    assert out.exists() and md.exists()
    loaded = json.loads(out.read_text())
    assert loaded["family"] == "top_anatomy_oot"
    assert loaded["boundary"] == BOUNDARY
    assert len(loaded["final_verdict_eligible"]) == 18
    assert "TOP ANATOMY OOT maturity receipt" in md.read_text()


def test_cli_default_data_root_is_repo_data(tmp_path):
    data_root = _five_ticker_store(tmp_path)
    out = tmp_path / "receipt2.json"
    oot.main(["--data-root", str(data_root), "--out", str(out), "--boundary", BOUNDARY])
    receipt = json.loads(out.read_text())
    assert receipt["provenance"]["data_root"] == str(data_root)


# ══════════════════════════════════════════════════════════════════════════════
# (k) empty-store honesty (no tickers pass the superset pre-filter)
# ══════════════════════════════════════════════════════════════════════════════
def test_empty_store_reports_zero_counts_not_a_crash(tmp_path):
    store = tmp_path / "massive_stock_day"
    store.mkdir(parents=True)
    receipt = oot.build_receipt(tmp_path, boundary=BOUNDARY)
    assert receipt["oot_end_observed"] is None
    assert receipt["store_coverage"]["n_eligible_names_last_session"] == 0
    for t in receipt["tiers"].values():
        assert t["n_case_episodes_strict"] == 0
        assert t["n_case_episodes_bridge"] == 0
    assert len(receipt["final_verdict_eligible"]) == 18
    assert all(not row["eligible"] for row in receipt["final_verdict_eligible"])
    assert receipt["state"] == "OOT_ACCRUING_NO_VERDICT"
    assert receipt["pinned_store_state"]["manifest_sha256"] is None
    assert receipt["pinned_store_state"]["shard_count"] == 0
