"""TOP ANATOMY OOT — deterministic maturity-receipt + roster-census emitter.

Implements the masterplan §5.4 contract
(`research/top_anatomy/TOPA_OOT_COMPLETION_MASTERPLAN_2026-08-28.md`) and the exact
receipt schema **FROZEN post-adversarial-review**
(`research/top_anatomy/TOPA_OOT_PREREG.md` §1/§4/§5, commit
`0f35a5e4d0e7`), against the §1 OOT boundary (2026-07-03).

THIS IS A COUNTING READ ONLY. It never computes a feature delta, a matched-delta
effect estimate, a bootstrap, or a grade. It reads the frozen §4.1-4.4 machinery
from `engine/top_anatomy.py` — extension definitions, episodes, sealing, race
labels, eligibility, identity segmentation — exactly as
`scripts/research_top_anatomy_phase0.py` calls them (including its own
`repair_bars` split-repair helper, reused rather than reimplemented).

BOUNDARY RULE (§1, tightened at freeze — session arithmetic, not EXT-day pattern).
A non-micro episode with §4.4 peak date on-or-after the boundary is OOT-STRICT iff
(a) its peak, minus **21 trading sessions on its own identity-segment calendar**,
is itself on-or-after the boundary — so all three registered `{21,10,5}` snapshot
offsets fall inside the OOT window regardless of which of them the episode
actually has EXT days for — and (b) it has **>=1 EXISTING snapshot day** (an EXT
day at one of the `{21,10,5}` offsets). Episodes peaking inside the first 21 OOT
sessions are OOT-BRIDGE by construction; episodes with ZERO existing snapshots are
candidates in NEITHER cohort (`n_excluded_no_snapshots`) — this closes the
snapshot-existence selection door named in §1.

TWO LABELED-UNIT BLOCKS, NEVER MERGED (§5, phase-1 §2 discipline). `episode_level`
counts distinct sealed/unsealed CASE EPISODES with labels
`{TOPPED, SURVIVED, IMMATURE-UNSEALED}` — TOPPED needs the −20% print with a final
peak search, SURVIVED needs the full [peak, peak+126] window observed
(`_seal_state`, a declared operationalization of §4's sealing law read literally
off `episode_peaks`'s `peak_window_truncated`/`peak_window_censored` flags — to be
mirrored into prereg §8 by the commissioning session). `day_level` counts RACE
LABELS on candidate observation (existing-snapshot) days with labels
`{TOPPED, CONTINUED, CENSORED}` — a direct reuse of `engine.top_anatomy.race_labels`.

PER-CELL ELIGIBILITY (§5: "no top-level eligibility scalar"). `final_verdict_eligible`
is a flat list of rows keyed `(cohort, panel, construction, leg)` — 3 panels x
2 cohorts x 3 legs (AM2: B2_rsi14, B3_rsi14_chg10; AM2-AGEFREE: F1_episode_age) =
18 rows. Every OOT-BRIDGE row is permanently `eligible: false` /
`reasons: ["bridge_never_graded"]` (§1/§3/§6: BRIDGE is never graded). A STRICT row
also cannot clear today: the frozen §4 per-era >=80% completeness floor needs
era-block construction this receipt deliberately does not build (commissioning
instruction, 2026-09-01 reconciliation wave — only the §5 monthly completeness
CENSUS ships here, as an input for a later wave's era blocks), and the AM-v2
validity precondition needs matched pairs this receipt never produces. Both are
reported `evaluable: false`, which alone keeps every STRICT row ineligible too —
exactly the prereg's own stated "no cell clears before ~2027-07" design (§4).

MATCHER SCOPE (§5, deliberately narrowed further at reconciliation). The frozen
AM-v2 matcher is never invoked — `matcher_run` is always `false`. Reason is
exactly the literal string `zero_candidates` when the panel's strict sealed-topped
count is 0, else exactly `matched_counting_pending_activation` (never a different
skip reason) with the literal candidate count also printed. The prereg's own text
says the matcher "runs whenever candidate case episodes >= 1"; implementing the
full AM-v2 matched-set assembly (age terciles, hard anchor caliper,
restrict-then-draw control pool) is out of scope for this counting receipt by
explicit commissioning-session instruction — the prereg-side operationalization
of this deliberate interim gap is recorded by that session, not here.

DARK-SEGMENT CENSUS (declared operationalization, to be mirrored into prereg §8).
"Dark since last session" = an identity segment whose last bar is on-or-after the
boundary (it traded inside the OOT window) but strictly before the store's last
observed session (it stopped trading before today) — a self-designed reading of
the masterplan's "who is missing" requirement, not a pre-existing named census.

DETERMINISM. No wall-clock read enters any decision. The only timestamp in the
output lives under `provenance.generated_at_utc`; identical inputs (same
--data-root content, same --boundary) yield byte-identical JSON apart from that
one field (and the default --out filename, which embeds the run date and is a
path, not a value inside the JSON).

Run:
  python -m scripts.research_top_anatomy_oot_receipt --data-root <repo>/data
  python -m scripts.research_top_anatomy_oot_receipt --data-root <repo>/data \\
      --out /tmp/receipt.json --md /tmp/receipt.md --verbose
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))

from engine import top_anatomy as ta  # noqa: E402
from scripts import research_top_anatomy_phase0 as rh  # noqa: E402

FAMILY = "top_anatomy_oot"
DEFAULT_BOUNDARY = "2026-07-03"          # masterplan §5.1 / prereg §1
OOT_SEED = 20260901                      # prereg §2 "moved variables" — declared, unused by a counting read
#: §1 (frozen): STRICT requires peak minus this many SESSIONS (on the episode's
#: own identity-segment calendar) to be on-or-after the boundary.
STRICT_SNAPSHOT_SESSIONS = 21
#: §5 registered cells: (construction, leg) pairs. 3 panels x 2 cohorts x this
#: tuple = the 18 `final_verdict_eligible` rows.
CELL_LEGS: tuple[tuple[str, str], ...] = (
    ("am2", "B2_rsi14"),
    ("am2", "B3_rsi14_chg10"),
    ("am2_agefree", "F1_episode_age"),
)
#: §4.1 tiers this receipt covers: primary (phase-0 §4.1) + the two W2 sensitivity
#: arms, exactly the engine's own `extended_mask(variant=...)` values.
TIERS: tuple[tuple[str, str], ...] = (
    ("primary", "primary"), ("r63", "r63"), ("atrz", "atrz"))
#: Panel legs pulled out of `repair_bars` output and widened per identity segment.
PANEL_COLS = ("close", "open", "high", "low", "volume", "raw_close", "raw_dvol",
              "split_day")

_T0 = time.time()


def say(msg: str, *, verbose: bool) -> None:
    if verbose:
        print(f"[{time.time() - _T0:7.1f}s] {msg}", flush=True)


# ══════════════════════════════════════════════════════════════════════════════
# store read (mirrors scripts.research_top_anatomy_phase0.build_panel_w's own
# loading shape; reuses its `repair_bars` split-repair rather than reimplementing
# it — no engine change, no reimplemented formula)
# ══════════════════════════════════════════════════════════════════════════════
def _load_segments(data_root: Path, *, verbose: bool = False) -> tuple[dict, pd.DatetimeIndex, int]:
    """Read+repair every `massive_stock_day` ticker, then split into identity segments.

    Returns ``(segments, calendar, n_tickers_scanned)``. The pre-filter is a strict
    SUPERSET of §3 eligibility (whole-series max close/best 21d dollar volume/bar
    count) — the same superset `build_panel_w` uses — so no per-day floor is
    silently applied here; §3 itself still runs inside `eligibility_mask` /
    `extended_mask` below.
    """
    store_dir = data_root / "massive_stock_day"
    if not store_dir.is_dir():
        raise FileNotFoundError(f"no massive_stock_day store at {store_dir}")
    files = sorted(store_dir.glob("*.parquet"))
    say(f"scanning {len(files)} ticker files in {store_dir}", verbose=verbose)
    keep: dict[str, pd.DataFrame] = {}
    for f in files:
        try:
            df = pd.read_parquet(f)
        except Exception:  # noqa: BLE001 — one torn vendor file must not kill the read
            continue
        if not {"close", "volume"} <= set(df.columns):
            continue
        df = df[~df.index.duplicated(keep="last")].sort_index()
        px = pd.to_numeric(df["close"], errors="coerce").dropna()
        if len(px) <= ta.MIN_PRIOR_SESSIONS:
            continue
        vol = pd.to_numeric(df["volume"], errors="coerce").reindex(px.index)
        dv21 = (px * vol).rolling(21, min_periods=21).median()
        if float(px.max()) < ta.MIN_CLOSE:
            continue
        if not (len(dv21) and dv21.max() >= ta.MIN_MEDIAN_DVOL21):
            continue
        frame = rh.repair_bars(df)
        if len(frame) > ta.MIN_PRIOR_SESSIONS:
            keep[f.stem] = frame
    say(f"{len(keep)} tickers pass the superset pre-filter", verbose=verbose)
    if not keep:
        return {}, pd.DatetimeIndex([]), len(files)
    calendar = pd.DatetimeIndex(sorted({d for b in keep.values() for d in b.index}))
    segments = ta.split_identity_segments(
        keep, calendar, residual_up_ratio_break=ta.RESIDUAL_UP_RATIO_BREAK)
    say(f"{len(keep)} tickers -> {len(segments)} identity segments", verbose=verbose)
    return segments, calendar, len(files)


def _wide(segments: dict[str, pd.DataFrame], col: str) -> pd.DataFrame:
    """One panel leg, segments as columns — the same reshape `research_top_anatomy_phase0._wide` uses."""
    have = {k: v[col] for k, v in segments.items() if col in v.columns}
    return pd.DataFrame(have).sort_index() if have else pd.DataFrame()


def _build_panel(data_root: Path, *, verbose: bool = False) -> tuple[dict, dict, pd.DatetimeIndex, int]:
    """Returns ``(panel, segments, calendar, n_tickers_scanned)``."""
    segments, calendar, n_tickers_scanned = _load_segments(data_root, verbose=verbose)
    panel = {c: _wide(segments, c) for c in PANEL_COLS}
    if not panel["close"].empty:
        panel["close"] = panel["close"].reindex(calendar)
        for c in PANEL_COLS:
            if not panel[c].empty:
                panel[c] = panel[c].reindex(index=calendar, columns=panel["close"].columns)
                if c == "split_day":
                    panel[c] = panel[c].fillna(False).astype(bool)
    return panel, segments, calendar, n_tickers_scanned


# ══════════════════════════════════════════════════════════════════════════════
# §1/§4 classification — STRICT vs BRIDGE, sealing state
# ══════════════════════════════════════════════════════════════════════════════
_EMPTY_SEAL_COUNTS = {"sealed_topped": 0, "sealed_survived": 0,
                      "immature_unsealed": 0, "censored_at_data_edge": 0}


def _seal_state(row) -> str:
    """§4 sealing law, read literally off `episode_peaks`'s own flags.

    TOPPED is sealed the moment the print fires PROVIDED the peak search itself
    is final (`peak_window_truncated` false) — a still-open peak-search window
    means a later, higher close could still move the peak and void today's print.
    SURVIVED is sealed only once the full [peak, peak+126] window was actually
    observed (`peak_window_censored` false); a SURVIVED label whose seal window
    ran off the data edge is CENSORED-AT-DATA-EDGE, not evidence of survival.
    """
    if bool(row["peak_window_truncated"]):
        return "immature_unsealed"
    if row["outcome"] == "TOPPED":
        return "sealed_topped"
    if bool(row.get("peak_window_censored", False)):
        return "censored_at_data_edge"
    return "sealed_survived"


_EMPTY_DAY_COUNTS = {"TOPPED": 0, "CONTINUED": 0, "CENSORED": 0}


def _date_n_sessions_before(seg_index: pd.DatetimeIndex | None, peak_date: pd.Timestamp,
                            n: int) -> pd.Timestamp | None:
    """The date exactly ``n`` trading SESSIONS before ``peak_date`` on one identity
    segment's own bar calendar — pure session arithmetic, independent of which of
    those sessions happen to be EXT days. Returns ``None`` when the segment index is
    unavailable, ``peak_date`` is not one of its bars, or fewer than ``n`` prior
    bars exist (never observed in practice given the 260-session eligibility floor;
    handled conservatively rather than assumed away).
    """
    if seg_index is None or len(seg_index) == 0:
        return None
    try:
        pos = seg_index.get_loc(peak_date)
    except KeyError:
        return None
    if not isinstance(pos, (int, np.integer)):
        return None   # a duplicated index — never true on a compacted segment
    target = int(pos) - n
    if target < 0:
        return None
    return seg_index[target]


def _classify_cohort(sealed: pd.DataFrame, dtp: pd.DataFrame, races: pd.DataFrame,
                     seg_bar_index: dict[str, pd.DatetimeIndex],
                     boundary: pd.Timestamp) -> dict:
    """§1 STRICT/BRIDGE split (session-arithmetic rule, frozen) + §4 sealing bucket
    + §5's two labeled-unit blocks + the §5 monthly completeness census, over
    non-micro candidate episodes (peak date on-or-after ``boundary``).

    OOT-STRICT iff (a) peak minus `STRICT_SNAPSHOT_SESSIONS` sessions on the
    episode's OWN identity-segment calendar is itself on-or-after ``boundary``
    (regardless of which `{21,10,5}` EXT days actually exist) and (b) the episode
    has >=1 EXISTING snapshot day. Episodes failing (a) are OOT-BRIDGE. Episodes
    failing (b) are candidates in NEITHER cohort — counted as
    `n_excluded_no_snapshots`, never silently folded into BRIDGE.
    """
    empty = {
        "episode_level": {"strict": dict(_EMPTY_SEAL_COUNTS), "bridge": dict(_EMPTY_SEAL_COUNTS)},
        "day_level": {"strict": dict(_EMPTY_DAY_COUNTS), "bridge": dict(_EMPTY_DAY_COUNTS)},
        "n_case_episodes_strict": 0, "n_case_episodes_bridge": 0,
        "n_excluded_no_snapshots": 0,
        "distinct_peak_months_sealed_topped": {"strict": 0, "bridge": 0},
        "monthly_completeness": {"strict": {}, "bridge": {}},
    }
    if sealed.empty:
        return empty
    cases = sealed[~sealed["micro"]].copy()
    cases["peak_date"] = pd.to_datetime(cases["peak_date"])
    candidates = cases[cases["peak_date"] >= boundary]
    if candidates.empty:
        return empty

    snap = dtp[dtp["days_to_peak"].isin(ta.CASE_OFFSETS)].copy()
    if not snap.empty:
        snap["date"] = pd.to_datetime(snap["date"])
        snap_by_ep = snap.groupby("episode_id")["date"].apply(list)
    else:
        snap_by_ep = pd.Series(dtype=object)

    races_lbl = None
    if races is not None and not races.empty:
        r = races.copy()
        r["date"] = pd.to_datetime(r["date"])
        races_lbl = r.set_index(["segment", "date"])["label"]

    episode_level = {"strict": dict(_EMPTY_SEAL_COUNTS), "bridge": dict(_EMPTY_SEAL_COUNTS)}
    day_level = {"strict": dict(_EMPTY_DAY_COUNTS), "bridge": dict(_EMPTY_DAY_COUNTS)}
    topped_months: dict[str, set] = {"strict": set(), "bridge": set()}
    monthly: dict[str, dict] = {"strict": {}, "bridge": {}}
    n_excluded = 0

    for _, row in candidates.iterrows():
        snap_dates = snap_by_ep.get(row["episode_id"], [])
        if not snap_dates:                      # §1 (b): zero-snapshot episodes are
            n_excluded += 1                      # candidates in neither cohort
            continue
        seg_idx = seg_bar_index.get(row["segment"])
        snap21 = _date_n_sessions_before(seg_idx, pd.Timestamp(row["peak_date"]),
                                         STRICT_SNAPSHOT_SESSIONS)
        cohort = "strict" if (snap21 is not None and snap21 >= boundary) else "bridge"

        state = _seal_state(row)
        episode_level[cohort][state] += 1
        pk = pd.Timestamp(row["peak_date"])
        month_key = f"{pk.year:04d}-{pk.month:02d}"
        if state == "sealed_topped":
            topped_months[cohort].add(month_key)
        m = monthly[cohort].setdefault(month_key, {
            "episode_sealed": 0, "episode_unsealed": 0,
            "day_topped": 0, "day_continued": 0, "day_censored": 0})
        if state in ("sealed_topped", "sealed_survived"):
            m["episode_sealed"] += 1
        else:
            m["episode_unsealed"] += 1

        for d in snap_dates:
            lbl = None
            if races_lbl is not None:
                key = (row["segment"], pd.Timestamp(d))
                if key in races_lbl.index:
                    v = races_lbl.loc[key]
                    lbl = v.iloc[0] if isinstance(v, pd.Series) else v
            if lbl in day_level[cohort]:
                day_level[cohort][lbl] += 1
            if lbl == "TOPPED":
                m["day_topped"] += 1
            elif lbl == "CONTINUED":
                m["day_continued"] += 1
            elif lbl == "CENSORED":
                m["day_censored"] += 1

    return {
        "episode_level": episode_level,
        "day_level": day_level,
        "n_case_episodes_strict": sum(episode_level["strict"].values()),
        "n_case_episodes_bridge": sum(episode_level["bridge"].values()),
        "n_excluded_no_snapshots": n_excluded,
        "distinct_peak_months_sealed_topped": {
            "strict": len(topped_months["strict"]), "bridge": len(topped_months["bridge"])},
        "monthly_completeness": monthly,
    }


# ══════════════════════════════════════════════════════════════════════════════
# matcher-skip + per-cell eligibility (counting only — never a matched-delta estimate)
# ══════════════════════════════════════════════════════════════════════════════
def _matcher_block(n_sealed_topped_strict: int) -> dict:
    """§5 (frozen): exactly two literal reasons, `matcher_run` always false.

    See module docstring "MATCHER SCOPE" — the prereg itself says the matcher runs
    whenever candidate case episodes >= 1; actually running the frozen AM-v2
    matched-set assembly is out of scope for this receipt by explicit
    commissioning-session instruction, so the reason states which of the two
    prereg-named cases applies and the literal count is always printed alongside.
    """
    reason = "zero_candidates" if n_sealed_topped_strict == 0 \
        else "matched_counting_pending_activation"
    return {"run": False, "seed": OOT_SEED,
            "n_sealed_topped_strict_candidates": n_sealed_topped_strict,
            "reason": reason}


def _floor_block(distinct_months: int, n_sealed_topped_strict: int) -> dict:
    """Per-panel STRICT floor CONVENIENCE summary (months + literal count) —
    kept beside the per-cell rows below per commissioning instruction ("keep
    per-tier floor blocks as convenience, but the cell rows are the contract").
    Never authoritative for eligibility on its own; see `_cell_rows`.
    """
    met_months = distinct_months >= ta.MIN_EPISODE_MONTHS
    met_literal_count = n_sealed_topped_strict >= rh.P1_MIN_MATCHED_EPISODES
    return {
        "min_distinct_peak_months": ta.MIN_EPISODE_MONTHS,
        "distinct_peak_months_sealed_topped_strict": distinct_months,
        "distinct_peak_months_floor_met": met_months,
        "min_matched_topped_episodes": rh.P1_MIN_MATCHED_EPISODES,
        "literal_sealed_topped_strict_count": n_sealed_topped_strict,
        "literal_count_is_not_a_matched_count": True,
        "matched_topped_episodes_floor_met": met_literal_count,
        "match_starved_rate_line": rh.P1_MATCH_STARVED_RATE,
    }


def _cell_rows(panel: str, cohort: str, distinct_months: int,
              n_sealed_topped: int) -> list[dict]:
    """§5 (frozen): `final_verdict_eligible` PER CELL, keyed
    `(cohort, panel, construction, leg)` — see module docstring "PER-CELL
    ELIGIBILITY". OOT-BRIDGE is permanently ineligible (`bridge_never_graded`).
    A STRICT cell is also always ineligible today: the completeness/validity
    preconditions are always `not evaluable` in this receipt (see module
    docstring), which alone blocks every cell regardless of the months/matched
    floors — the deliberate, disclosed "no cell clears before ~2027-07" state.
    """
    rows = []
    for construction, leg in CELL_LEGS:
        floor_inputs = {
            "distinct_peak_months_sealed_topped": distinct_months,
            "min_distinct_peak_months": ta.MIN_EPISODE_MONTHS,
            "literal_sealed_topped_count": n_sealed_topped,
            "min_matched_topped_episodes": rh.P1_MIN_MATCHED_EPISODES,
            "literal_count_is_not_a_matched_count": True,
            "completeness_evaluable": False,
            "validity_precondition_evaluable": False,
        }
        if cohort == "bridge":
            reasons = ["bridge_never_graded"]
        else:
            reasons = []
            if distinct_months < ta.MIN_EPISODE_MONTHS:
                reasons.append(
                    f"distinct sealed-topped OOT-STRICT episode-peak months "
                    f"({distinct_months}) is below the {ta.MIN_EPISODE_MONTHS}-month "
                    "floor")
            if n_sealed_topped < rh.P1_MIN_MATCHED_EPISODES:
                reasons.append(
                    f"literal sealed-topped OOT-STRICT candidate count "
                    f"({n_sealed_topped}) is below the {rh.P1_MIN_MATCHED_EPISODES}-"
                    "episode registered floor (matcher_run is false; literal "
                    "pre-matching count only, never an actual matched count)")
            reasons.append("completeness_floor_not_evaluable_no_era_blocks")
            reasons.append("validity_precondition_not_evaluable_matcher_not_run")
        rows.append({
            "cohort": cohort, "panel": panel, "construction": construction,
            "leg": leg, "eligible": False, "floor_inputs": floor_inputs,
            "reasons": reasons,
        })
    return rows


# ══════════════════════════════════════════════════════════════════════════════
# per-tier receipt block
# ══════════════════════════════════════════════════════════════════════════════
def _tier_receipt(tier_key: str, variant: str, close: pd.DataFrame, dvol: pd.DataFrame,
                  high: pd.DataFrame | None, low: pd.DataFrame | None,
                  raw_close: pd.DataFrame | None, raw_dvol: pd.DataFrame | None,
                  split_day: pd.DataFrame | None,
                  seg_bar_index: dict[str, pd.DatetimeIndex],
                  boundary: pd.Timestamp) -> dict:
    ext = ta.extended_mask(close, dvol, variant=variant, high_df=high, low_df=low,
                           raw_close_df=raw_close, raw_dollar_vol_df=raw_dvol,
                           split_day_df=split_day)
    episodes = ta.extract_episodes(ext, close)
    sealed, dtp = ta.episode_peaks(close, episodes, ext)
    races = ta.race_labels(close, ext)

    cohort = _classify_cohort(sealed, dtp, races, seg_bar_index, boundary)
    strict_ep = cohort["episode_level"]["strict"]
    bridge_ep = cohort["episode_level"]["bridge"]
    strict_months = cohort["distinct_peak_months_sealed_topped"]["strict"]
    bridge_months = cohort["distinct_peak_months_sealed_topped"]["bridge"]

    matcher = _matcher_block(strict_ep["sealed_topped"])
    floors = _floor_block(strict_months, strict_ep["sealed_topped"])
    cells = (_cell_rows(tier_key, "strict", strict_months, strict_ep["sealed_topped"])
            + _cell_rows(tier_key, "bridge", bridge_months, bridge_ep["sealed_topped"]))

    n_races_censored_data_edge_in_window = 0
    if not races.empty:
        r = races.copy()
        r["date"] = pd.to_datetime(r["date"])
        n_races_censored_data_edge_in_window = int(
            ((r["censor_reason"] == "data_end") & (r["date"] >= boundary)).sum())

    return {
        "variant": variant,
        "n_ext_days": int(ext.to_numpy().sum()) if not ext.empty else 0,
        "n_episodes_total": int(len(episodes)),
        "n_case_episodes_strict": cohort["n_case_episodes_strict"],
        "n_case_episodes_bridge": cohort["n_case_episodes_bridge"],
        "n_excluded_no_snapshots": cohort["n_excluded_no_snapshots"],
        "episode_level": {   # unit: distinct sealed/unsealed case episodes
            "labels": ["TOPPED", "SURVIVED", "IMMATURE-UNSEALED"],
            "strict": strict_ep, "bridge": bridge_ep,
        },
        "day_level": {   # unit: race labels on candidate observation (snapshot) days
            "labels": ["TOPPED", "CONTINUED", "CENSORED"],
            "strict": cohort["day_level"]["strict"], "bridge": cohort["day_level"]["bridge"],
        },
        "distinct_peak_months_sealed_topped": cohort["distinct_peak_months_sealed_topped"],
        "monthly_completeness": cohort["monthly_completeness"],
        "matcher": matcher,
        "match_starvation": {
            "evaluable": False,
            "reason": "matcher_run is false; match rate cannot be computed",
        },
        "outcome_horizon_maturity": {
            "any_strict_sealed": bool(strict_ep["sealed_topped"] or strict_ep["sealed_survived"]),
            "n_strict_immature_unsealed": strict_ep["immature_unsealed"],
            "n_strict_censored_at_data_edge": strict_ep["censored_at_data_edge"],
        },
        "construction_diagnostic_readiness": {
            "am_v2_validity_evaluable": False,
            "reason": ("matched-episode counting was skipped; AM-v2 validity "
                      "diagnostics require matched pairs"),
        },
        "n_races_censored_data_edge_in_window": n_races_censored_data_edge_in_window,
        "floors": floors,
        "cells": cells,
    }


# ══════════════════════════════════════════════════════════════════════════════
# pinned store state (§5, moved variable §2 item 4)
# ══════════════════════════════════════════════════════════════════════════════
def _pinned_store_state(data_root: Path, calendar: pd.DatetimeIndex,
                        n_tickers_scanned: int) -> dict:
    """sha256 of `_manifest.json` content + last session date + shard count.

    When the manifest is absent (a local checkout `fetch_r2` skipped, or a
    synthetic test store), emits `manifest_sha256: null` with the literal reason
    `manifest_not_present_in_checkout` — never a fabricated hash.
    """
    manifest_path = data_root / "massive_stock_day" / "_manifest.json"
    if manifest_path.is_file():
        manifest_sha256 = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
        manifest_reason = None
    else:
        manifest_sha256 = None
        manifest_reason = "manifest_not_present_in_checkout"
    return {
        "manifest_sha256": manifest_sha256,
        "manifest_reason": manifest_reason,
        "last_session": (str(calendar.max().date()) if len(calendar) else None),
        "shard_count": n_tickers_scanned,
    }


# ══════════════════════════════════════════════════════════════════════════════
# delisting / identity-break census (masterplan §5.4 "who is missing")
# ══════════════════════════════════════════════════════════════════════════════
def _delisting_identity_break_census(segments: dict[str, pd.DataFrame],
                                     calendar: pd.DatetimeIndex,
                                     boundary: pd.Timestamp) -> dict:
    if len(calendar) == 0 or not segments:
        return {"n_identity_segments_total": len(segments), "last_session_read": None,
                "n_dark_since_last_session": 0, "dark_examples": [],
                "n_identity_breaks_starting_in_window": 0, "identity_break_examples": []}
    last_session = calendar.max()
    dark, breaks = [], []
    for seg, bars in segments.items():
        idx = bars.index
        if len(idx) == 0:
            continue
        seg_last, seg_first = idx.max(), idx.min()
        # traded during/through the OOT window, then stopped before today's session
        if seg_last >= boundary and seg_last < last_session:
            dark.append({"segment": seg, "ticker": ta.segment_ticker(seg),
                        "last_session": str(pd.Timestamp(seg_last).date())})
        # a fresh identity (reused-ticker or residual-up-jump break) starting
        # inside the OOT window itself
        if "#" in seg and seg_first >= boundary:
            breaks.append({"segment": seg, "ticker": ta.segment_ticker(seg),
                          "first_session": str(pd.Timestamp(seg_first).date())})
    dark.sort(key=lambda r: (r["ticker"], r["segment"]))
    breaks.sort(key=lambda r: (r["ticker"], r["segment"]))
    return {
        "n_identity_segments_total": len(segments),
        "last_session_read": str(pd.Timestamp(last_session).date()),
        "n_dark_since_last_session": len(dark),
        "dark_examples": dark[:50],
        "n_identity_breaks_starting_in_window": len(breaks),
        "identity_break_examples": breaks[:50],
    }


# ══════════════════════════════════════════════════════════════════════════════
# top-level receipt
# ══════════════════════════════════════════════════════════════════════════════
def build_receipt(data_root: Path, *, boundary: str = DEFAULT_BOUNDARY,
                  seed: int = OOT_SEED, verbose: bool = False) -> dict:
    boundary_ts = pd.Timestamp(boundary)
    panel, segments, calendar, n_tickers_scanned = _build_panel(
        data_root, verbose=verbose)
    close = panel["close"]
    volume = panel["volume"]
    high = panel["high"] if not panel["high"].empty else None
    low = panel["low"] if not panel["low"].empty else None
    raw_close = panel["raw_close"] if not panel["raw_close"].empty else None
    raw_dvol = panel["raw_dvol"] if not panel["raw_dvol"].empty else None
    split_day = panel["split_day"] if not panel["split_day"].empty else None
    dvol = (close * volume) if not volume.empty else pd.DataFrame(
        np.nan, index=close.index, columns=close.columns)
    #: per-segment OWN bar calendar (no NaN gaps) — the session-arithmetic ruler
    #: `_classify_cohort` walks for the §1 peak-minus-21-sessions STRICT rule.
    seg_bar_index = {col: close[col].dropna().index for col in close.columns}

    elig = ta.eligibility_mask(close, dvol, raw_close_df=raw_close,
                               raw_dollar_vol_df=raw_dvol, split_day_df=split_day)
    if len(calendar) and not elig.empty and elig.shape[1] > 0:
        n_eligible_last = int(elig.iloc[-1].fillna(False).astype(bool).sum())
    else:
        n_eligible_last = 0

    say("computing per-tier candidate/sealing counts", verbose=verbose)
    tiers = {}
    for tier_key, variant in TIERS:
        tiers[tier_key] = _tier_receipt(
            tier_key, variant, close, dvol, high, low, raw_close, raw_dvol,
            split_day, seg_bar_index, boundary_ts)

    census = _delisting_identity_break_census(segments, calendar, boundary_ts)
    pinned_store_state = _pinned_store_state(data_root, calendar, n_tickers_scanned)

    # §5: "no top-level eligibility scalar" — final_verdict_eligible IS this flat
    # list of per-cell rows (3 panels x 2 cohorts x 3 legs = 18 rows).
    cell_rows: list[dict] = []
    for tier_key, _variant in TIERS:
        cell_rows.extend(tiers[tier_key].pop("cells"))
    all_eligible = bool(cell_rows) and all(row["eligible"] for row in cell_rows)
    state = ("OOT_ACCRUING_NO_VERDICT" if not all_eligible
            else "OOT_MATURITY_FLOORS_CLEARED_AWAITING_R2_ADJUDICATION")

    return {
        "schema_version": 2,
        "family": FAMILY,
        "artifact": "oot_maturity_receipt",
        "boundary": str(boundary_ts.date()),
        "oot_start": str(boundary_ts.date()),
        "oot_end_observed": (str(calendar.max().date()) if len(calendar) else None),
        "seed": seed,
        "pinned_store_state": pinned_store_state,
        "store_coverage": {
            "first_session": (str(calendar.min().date()) if len(calendar) else None),
            "last_session": (str(calendar.max().date()) if len(calendar) else None),
            "n_tickers_scanned": n_tickers_scanned,
            "n_identity_segments": len(segments),
            "n_eligible_names_last_session": n_eligible_last,
        },
        "delisting_identity_break_census": census,
        "tiers": tiers,
        "final_verdict_eligible": cell_rows,
        "state": state,
        "provenance": {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "script": "scripts/research_top_anatomy_oot_receipt.py",
            "data_root": str(data_root),
        },
    }


# ══════════════════════════════════════════════════════════════════════════════
# markdown companion (display only — the JSON is the artifact of record)
# ══════════════════════════════════════════════════════════════════════════════
def render_markdown(receipt: dict) -> str:
    n_eligible_cells = sum(1 for row in receipt["final_verdict_eligible"] if row["eligible"])
    lines = [
        f"# TOP ANATOMY OOT maturity receipt — {receipt['state']}",
        "",
        f"- boundary: `{receipt['boundary']}`  ·  oot_end_observed: "
        f"`{receipt['oot_end_observed']}`",
        f"- eligible cells: **{n_eligible_cells} / {len(receipt['final_verdict_eligible'])}**",
        f"- pinned store state: {receipt['pinned_store_state']}",
        f"- store coverage: {receipt['store_coverage']}",
        "",
        "## Per-tier counts (episode-level {TOPPED,SURVIVED,IMMATURE-UNSEALED} / "
        "day-level {TOPPED,CONTINUED,CENSORED})",
        "",
    ]
    for tier_key, t in receipt["tiers"].items():
        lines += [
            f"### {tier_key} ({t['variant']})",
            f"- candidates: strict={t['n_case_episodes_strict']} "
            f"bridge={t['n_case_episodes_bridge']} "
            f"excluded_no_snapshots={t['n_excluded_no_snapshots']}",
            f"- episode-level strict: {t['episode_level']['strict']}",
            f"- episode-level bridge: {t['episode_level']['bridge']}",
            f"- day-level strict: {t['day_level']['strict']}",
            f"- day-level bridge: {t['day_level']['bridge']}",
            f"- distinct sealed-topped peak months: "
            f"{t['distinct_peak_months_sealed_topped']}",
            f"- matcher: run={t['matcher']['run']} — {t['matcher']['reason']}",
            "",
        ]
    lines += [
        "## Per-cell eligibility (cohort x panel x construction x leg)",
        "",
    ]
    for row in receipt["final_verdict_eligible"]:
        lines.append(f"- {row['cohort']}/{row['panel']}/{row['construction']}/"
                     f"{row['leg']}: eligible={row['eligible']} "
                     f"reasons={row['reasons']}")
    lines += [
        "",
        "## Delisting / identity-break census",
        f"{receipt['delisting_identity_break_census']}",
        "",
        f"_generated {receipt['provenance']['generated_at_utc']}_",
    ]
    return "\n".join(lines) + "\n"


# ══════════════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════════════
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--data-root", type=Path, default=_REPO / "data",
                    help="root directory containing massive_stock_day/ (default: repo data/)")
    ap.add_argument("--out", type=Path, default=None,
                    help="output JSON path (default: data/research/"
                         "top_anatomy_oot_receipt_<UTC date>.json)")
    ap.add_argument("--boundary", default=DEFAULT_BOUNDARY,
                    help=f"OOT boundary date, inclusive (default: {DEFAULT_BOUNDARY})")
    ap.add_argument("--md", type=Path, default=None,
                    help="optional companion markdown path")
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args(argv)

    out_path = a.out
    if out_path is None:
        utc_date = datetime.now(timezone.utc).strftime("%Y%m%d")
        out_path = _REPO / "data" / "research" / f"top_anatomy_oot_receipt_{utc_date}.json"

    receipt = build_receipt(a.data_root, boundary=a.boundary, verbose=a.verbose)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(receipt, indent=2, sort_keys=True, default=str))
    say(f"wrote {out_path}", verbose=a.verbose)
    n_eligible = sum(1 for row in receipt["final_verdict_eligible"] if row["eligible"])
    print(f"eligible_cells={n_eligible}/{len(receipt['final_verdict_eligible'])} "
         f"state={receipt['state']}")

    if a.md is not None:
        a.md.parent.mkdir(parents=True, exist_ok=True)
        a.md.write_text(render_markdown(receipt))
        say(f"wrote {a.md}", verbose=a.verbose)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
