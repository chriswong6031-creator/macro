"""Adjusted-basis re-run of the W5.1 per-leg veto isolation — both columns, one mask.

Charter: #4698's price-adjustment audit fenced `veto_leg_isolation.py` out of its sweep,
leaving this instrument's numbers the only uncleared ones in the W5.1 evidence set — and
the tightest boundary of the set (-0.26 / -0.57 / -0.52pp), so the one most able to move.

THE DEFECT #4698 FOUND. An excess return is `name - benchmark`, and that subtraction is
only meaningful when both legs sit on the same adjustment basis. The three breadth close
caches are re-based only at a full rebuild (last ~2026-05-12) and accrue RAW rows after
it; `data/baskets/ohlcv`, `data/yahoo` and `data/stocks` are back-adjusted, and SPY is
available adjusted only. A cache-priced name measured against SPY therefore books its OWN
distribution as a loss. The exposure is a bounded tail, not all history: #4698 swept 1,227
names and found 72.1% bit-identical across their whole overlap, with first divergence
clustering at p05 2026-05-13 / median 2026-06-01.

WHY THIS FILE EXISTS RATHER THAN AN EDIT. The frozen original
(`veto_leg_isolation_results.json`) is the artifact the packet's numbers were reported
from. It is NOT overwritten — the as-shipped column is a frozen historical record, and
§Reproducibility below explains why it could not be re-derived even if we wanted to.

THE TWO TRAPS #4698 HIT, BOTH FENCED HERE
=========================================

(1) COVERAGE MASQUERADING AS BASIS. #4698's first adjusted run grew its admitted
    population 31%, because `baskets/ohlcv` carries the large-cap sleeve ~2 years deeper
    than the breadth cache. That is a different STUDY, not a re-priced one. This file
    pins all three axes and proves each with a count:

      * UNIVERSE  — the adjusted panel is restricted to the as-shipped name list; no name
        enters or leaves.
      * CALENDAR  — reindexed onto the as-shipped session index; no session enters or
        leaves.
      * OBSERVED-CELL MASK — the INTERSECTION of the two panels' observed cells is
        computed once and applied to BOTH, so the two runs see literally the same
        name-days. Intersecting (rather than masking adjusted down to the cache) matters
        because an adjusted source can also be missing a date the cache carries; masking
        one way would leave that asymmetry in place.

    Because the mask is applied before any leg is computed, each name's FIRST observed
    date is identical across runs, so the 2B/3B resample phase — which anchors on that
    date — is identical too (memory: resample-bin-phase-is-anchored-on-the-first-index-date).

(2) THE AS-SHIPPED COLUMN IS NOT REPRODUCIBLE. #4698's receipt: PNC's 2026-06-22 close
    read 234.71 on 07-01 and 232.85 today — the caches mutate under re-basing. Every
    as-shipped number here is a FROZEN HISTORICAL ARTIFACT pinned to its read date, not
    something a later run can re-derive. The adjusted column, drawn from back-adjusted
    per-name stores, is the reproducible one.

THREE RUNS, BECAUSE "DOES IT MOVE" HAS TWO CHANNELS
===================================================
Re-pricing does not only change forward returns — it changes the price series the
oscillator legs are computed from, so cohort MEMBERSHIP moves too. Reporting one blended
delta would hide which channel carried it:

  A  cache-today  legs from cache prices,    returns from cache prices
  C  hybrid       legs from CACHE prices,    returns from ADJUSTED prices
  B  adjusted     legs from ADJUSTED prices, returns from ADJUSTED prices

A→C isolates the OUTCOME channel (the bias #4698 measured, cohorts held fixed).
C→B isolates the COHORT channel (legs re-derived on the corrected basis).
A→B is the headline both-columns comparison.

**A IS NOT THE FROZEN COLUMN, AND IS NOT CALLED ONE.** It is a re-read of the caches
TODAY on the intersected sub-universe. It differs from the committed
`veto_leg_isolation_results.json` by three things at once — store drift (the caches
re-base between reads), the universe reduction the adjusted ladder forces (266 of 1,493
names have no adjusted source at all), and the re-phasing of the names whose first
observation moved. This file does NOT decompose that gap; `section_6` prints it and says
so. The verdict rests on A-vs-B, which shares one read, one universe, one calendar, one
mask and one phase — the only comparison in which price BASIS is the sole difference.

Ladder: `price_ladder.close_panel` (vendored byte-identical from #4698 — receipt in
`section_0`). Not re-invented here.

Re-run: python3 research/prophet_us_audit/veto_leg_isolation_adjusted_rerun.py
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = str(Path(__file__).resolve().parents[2])
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "veto_leg_isolation_adjusted_rerun.json")
FROZEN = os.path.join(HERE, "veto_leg_isolation_results.json")
os.chdir(REPO)
sys.path.insert(0, REPO)
sys.path.insert(0, HERE)


def _load(name: str):
    """Import a sibling research module by path (they live outside any package).

    The module is registered in ``sys.modules`` BEFORE it executes: ``@dataclass`` resolves
    its own annotations through ``sys.modules[cls.__module__]``, so a path-loaded module
    carrying a dataclass (``price_ladder.Resolved``) raises on an unregistered name.
    """
    if name in sys.modules:
        return sys.modules[name]
    cwd = os.getcwd()
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, f"{name}.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    try:
        spec.loader.exec_module(mod)
    except Exception:
        sys.modules.pop(name, None)
        raise
    finally:
        os.chdir(cwd)
    return mod


VLI = _load("veto_leg_isolation")
PL = _load("price_ladder")

#: the #4698 commit the vendored ladder was taken from, for the receipt
LADDER_SOURCE_REF = "origin/claude/price-adjustment-audit-20260806"
LADDER_SOURCE_PR = 4698
#: when the as-shipped cache read was taken. The caches mutate under re-basing, so this
#: is the pin that makes the frozen column interpretable at all.
AS_SHIPPED_READ_DATE = "2026-08-05"
LEGS = ("SOLE:stoch_ob", "SOLE:stoch_bear", "SOLE:macd_bear")
KEYCELLS = ("CONTROL:admitted",) + LEGS + ("UNION:board_without_macd_bear",)


def _sha(p: str) -> str:
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def ladder_receipt() -> dict:
    """Prove the vendored copy is byte-identical to #4698's, not a re-implementation."""
    mine = _sha(os.path.join(HERE, "price_ladder.py"))
    rec = {
        "vendored_from": f"PR #{LADDER_SOURCE_PR} ({LADDER_SOURCE_REF})",
        "why_vendored": "price_ladder.py is not on main yet; importing across branches is "
                        "not reproducible, so the file is carried here byte-identically "
                        "and the receipt below proves it was not re-invented",
        "local_sha256": mine,
        "on_merge": "if both PRs land, the two copies are byte-identical, so git resolves "
                    "the add/add as one file; the note stays until #4698 is on main",
    }
    try:
        theirs = subprocess.run(
            ["git", "show", f"{LADDER_SOURCE_REF}:research/prophet_us_audit/price_ladder.py"],
            capture_output=True, check=True).stdout
        rec["source_sha256"] = hashlib.sha256(theirs).hexdigest()
        rec["identical"] = bool(rec["source_sha256"] == mine)
    except (subprocess.CalledProcessError, OSError) as e:
        rec["source_sha256"] = None
        rec["identical"] = None
        rec["note"] = f"source ref unavailable in this checkout ({e}) — local sha only"
    return rec


# ------------------------------------------------------------ the basis control --
def pin_and_intersect(px_cache_raw: pd.DataFrame, adj_raw: pd.DataFrame,
                      *, min_hist: int) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Pin universe + calendar, intersect the observed-cell masks, return the proof.

    This is the whole defence against #4698's +31% confound, and it is a PURE function of
    two frames so a test can drive it with a synthetic store where the adjusted source is
    deliberately deeper than the cache.

    The intersection is symmetric on purpose. Masking adjusted DOWN to the cache would
    still leave the reverse asymmetry — a date the cache carries and the adjusted source
    does not — which would show up as a basis effect while being a coverage hole.
    """
    names = list(px_cache_raw.columns)
    idx = px_cache_raw.index
    adj = adj_raw.reindex(index=idx, columns=names)

    m_cache = px_cache_raw.notna().to_numpy()
    m_adj = adj.notna().to_numpy()
    m_both = m_cache & m_adj
    mboth_df = pd.DataFrame(m_both, index=idx, columns=names)

    px_cache = px_cache_raw.where(mboth_df)
    px_adj = adj.where(mboth_df)

    keep = [t for t in names if int(px_cache[t].notna().sum()) >= min_hist]
    dropped = [t for t in names if t not in set(keep)]
    px_cache, px_adj = px_cache[keep], px_adj[keep]

    mc, ma = px_cache.notna().to_numpy(), px_adj.notna().to_numpy()
    first_cache = px_cache_raw[keep].apply(lambda s: s.first_valid_index())
    first_both = px_cache.apply(lambda s: s.first_valid_index())
    phase_shifted = [t for t in keep if first_cache[t] != first_both[t]]

    proof = {
        "names_in": len(names), "names_kept": len(keep), "names_dropped": len(dropped),
        "dropped_tickers": sorted(dropped),
        "sessions": int(px_cache.shape[0]),
        "cache_observed_cells": int(m_cache.sum()),
        "adjusted_observed_cells_on_pinned_axes": int(m_adj.sum()),
        "intersection_cells": int(m_both.sum()),
        "cells_dropped_from_cache": int(m_cache.sum() - m_both.sum()),
        "cells_dropped_from_adjusted": int(m_adj.sum() - m_both.sum()),
        "final_cache_cells": int(mc.sum()),
        "final_adjusted_cells": int(ma.sum()),
        "masks_identical": bool(np.array_equal(mc, ma)),
        "mask_mismatches": int((mc != ma).sum()),
        "identical_index": bool(px_cache.index.equals(px_adj.index)),
        "identical_columns": bool(list(px_cache.columns) == list(px_adj.columns)),
        "phase_shifted_names": len(phase_shifted),
        "phase_shifted_examples": sorted(phase_shifted)[:20],
    }
    return px_cache, px_adj, proof


def build_two_panels() -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """The as-shipped panel and its adjusted twin, on ONE universe, calendar and mask.

    Returns ``(px_cache, px_adj, control)`` where the two frames have identical shape,
    identical columns, identical index, and — proven in ``control`` — identical
    observed-cell masks.
    """
    px_cache_raw, _deep, prov_cache = VLI.load_universe()
    names = list(px_cache_raw.columns)
    idx = px_cache_raw.index
    start = str(pd.Timestamp(idx[0]).date())

    adj_raw, prov_adj = PL.close_panel(
        names, asof=VLI.REPRO_ASOF, start=start, allow_unadjusted=False)

    # UNIVERSE + CALENDAR pinned and the observed-cell masks intersected. A name absent
    # from every adjusted source becomes an all-NaN column, which the intersection then
    # removes from BOTH runs — never from one.
    px_cache, px_adj, proof = pin_and_intersect(
        px_cache_raw, adj_raw, min_hist=VLI.MIN_HIST)

    control = {
        "why": "#4698's first adjusted run grew its admitted population 31% because "
               "baskets/ohlcv carries the large-cap sleeve ~2 years deeper than the "
               "breadth cache — a COVERAGE change wearing a basis effect's clothes. All "
               "three axes are pinned here and each is proven with a count.",
        "universe": {
            "frozen_run_names": len(names),
            "adjusted_panel_names_before_pinning": int(prov_adj.get("panel_names", 0)),
            "names_after_intersection": proof["names_kept"],
            "names_dropped_no_adjusted_source_or_thin": proof["names_dropped"],
            "dropped_tickers": proof["dropped_tickers"][:40],
            "identical_name_list_across_runs": bool(proof["identical_columns"]),
            "cost_note": "the adjusted ladder has no source for these names, so BOTH "
                         "columns lose them. Every A-vs-B number below is therefore on a "
                         "sub-universe of the frozen run's, and section_6 prints the gap.",
        },
        "calendar": {
            "frozen_run_sessions": int(len(idx)),
            "adjusted_sessions_before_pinning": int(prov_adj.get("panel_sessions", 0)),
            "sessions_used_by_both_runs": proof["sessions"],
            "frame": [start, VLI.REPRO_ASOF],
            "identical_index_across_runs": bool(proof["identical_index"]),
        },
        "observed_cell_mask": {k: proof[k] for k in (
            "cache_observed_cells", "adjusted_observed_cells_on_pinned_axes",
            "intersection_cells", "cells_dropped_from_cache", "cells_dropped_from_adjusted",
            "final_cache_cells", "final_adjusted_cells", "masks_identical",
            "mask_mismatches")},
        "resample_phase": {
            "why": "_tf_bars anchors 2B/3B buckets on each series' FIRST index date, so a "
                   "shifted first observation silently re-phases every oscillator leg",
            "names_whose_first_observation_moved_vs_the_frozen_run":
                proof["phase_shifted_names"],
            "examples": proof["phase_shifted_examples"],
            "note": "these names are re-phased IDENTICALLY in both runs, so the A-vs-B "
                    "comparison is unaffected; the count is disclosed because it is one "
                    "of the three reasons the cache-today column differs from the frozen "
                    "original (section_6)",
        },
        "ladder_provenance": {
            k: prov_adj.get(k) for k in
            ("ladder", "adjusted_sources", "unadjusted_sources", "n_requested",
             "resolved_from", "names_on_unadjusted_basis", "panel_range")},
        "unresolved_on_adjusted_ladder": len(prov_adj.get("unresolved_tickers", [])),
        "unresolved_examples": sorted(prov_adj.get("unresolved_tickers", []))[:40],
        "allow_unadjusted": False,
        "allow_unadjusted_note": "the adjusted panel refuses the cache rung outright — a "
                                 "name that fell through would put the very basis mix "
                                 "this run exists to remove back into the B column",
        "as_shipped_cache_read_date": AS_SHIPPED_READ_DATE,
        "reproducibility": "the as-shipped column is a FROZEN HISTORICAL ARTIFACT. The "
                           "breadth caches are re-based at each full rebuild, so a later "
                           "read returns different numbers for the same past session "
                           "(#4698's receipt: PNC 2026-06-22 read 234.71 on 07-01 and "
                           "232.85 today). Only the adjusted column is re-derivable.",
        "cache_names_source": prov_cache,
    }
    return px_cache, px_adj, control


# ------------------------------------------------------------------ comparison --
def _cells(iso: dict, window: str, h: int) -> dict:
    return (iso["by_window"][window].get(f"H{h}", {}) or {}).get("cells", {}) or {}


def both_columns(runs: dict, window: str = "full_frame") -> dict:
    """The side-by-side the adjudication reads: per leg, per horizon, A vs B (+ C)."""
    out: dict = {"window": window, "metric": "per-name-first median excess vs SPY (pp), "
                                             "and that cohort minus CONTROL:admitted"}
    per_h: dict = {}
    for h in VLI.HORIZONS:
        rows: dict = {}
        for name in KEYCELLS:
            row: dict = {}
            for tag, iso in runs.items():
                c = _cells(iso, window, h).get(name, {})
                row[tag] = {
                    "n": c.get("n"),
                    "pnf_pp": c.get("per_name_first_median_pp"),
                    "vs_control_pp": c.get("vs_control_per_name_pp"),
                    "median_dm_pp": c.get("median_excess_dm_pp"),
                    "loser_pct": c.get("loser_rate_pct"),
                }
            a, b = row.get("A_cache_today", {}), row.get("B_adjusted", {})
            c_ = row.get("C_cache_cohorts_adjusted_returns", {})
            row["delta_B_minus_A"] = {
                "vs_control_pp": VLI._r((b.get("vs_control_pp") or 0) - (a.get("vs_control_pp") or 0))
                if (b.get("vs_control_pp") is not None and a.get("vs_control_pp") is not None) else None,
                "pnf_pp": VLI._r((b.get("pnf_pp") or 0) - (a.get("pnf_pp") or 0))
                if (b.get("pnf_pp") is not None and a.get("pnf_pp") is not None) else None,
                "n_pct": VLI._r(100.0 * ((b.get("n") or 0) - (a.get("n") or 0)) / max(a.get("n") or 1, 1), 1),
            }
            row["channel_split"] = {
                "outcome_A_to_C_vs_control_pp": VLI._r(
                    (c_.get("vs_control_pp") or 0) - (a.get("vs_control_pp") or 0))
                if (c_.get("vs_control_pp") is not None and a.get("vs_control_pp") is not None) else None,
                "cohort_C_to_B_vs_control_pp": VLI._r(
                    (b.get("vs_control_pp") or 0) - (c_.get("vs_control_pp") or 0))
                if (b.get("vs_control_pp") is not None and c_.get("vs_control_pp") is not None) else None,
            }
            rows[name] = row
        per_h[f"H{h}"] = rows
    out["by_horizon"] = per_h
    return out


def verdict(bc: dict, frozen: dict, runs: dict) -> dict:
    """Holds / weakens / flips — decided from the printed numbers, not narrated."""
    NOISE = 0.28          # #4547's own max_edge_over_control_pp, its demonstrated floor
    per_leg: dict = {}
    for leg in LEGS:
        adj = [bc["by_horizon"][f"H{h}"][leg]["B_adjusted"]["vs_control_pp"]
               for h in VLI.HORIZONS]
        ship = [bc["by_horizon"][f"H{h}"][leg]["A_cache_today"]["vs_control_pp"]
                for h in VLI.HORIZONS]
        adj = [v for v in adj if v is not None]
        ship = [v for v in ship if v is not None]
        if not adj or not ship:
            per_leg[leg] = {"verdict": "UNRUNNABLE"}
            continue
        sign_stable = bool(len({v > 0 for v in adj}) == 1)
        same_sign_as_shipped = bool(all((a > 0) == (s > 0) for a, s in zip(adj, ship)))
        worst_shrink = max(abs(s) - abs(a) for a, s in zip(adj, ship))
        above_noise = bool(max(abs(v) for v in adj) > NOISE)
        if not same_sign_as_shipped:
            v = "FLIPS"
        elif not above_noise:
            v = "COLLAPSES INTO THE NOISE FLOOR"
        elif worst_shrink > 0.10:
            v = "HOLDS BUT WEAKENS"
        else:
            v = "HOLDS"
        per_leg[leg] = {
            "verdict": v,
            "adjusted_vs_control_pp": adj,
            "as_shipped_vs_control_pp": ship,
            "sign_stable_across_horizons": sign_stable,
            "sign_matches_as_shipped": same_sign_as_shipped,
            "largest_shrink_pp": VLI._r(worst_shrink),
            "max_abs_adjusted_pp": VLI._r(max(abs(v) for v in adj)),
            "noise_floor_pp": NOISE,
        }
    fr = frozen.get("readout", {}).get("per_leg_vs_control", {})
    return {
        "noise_floor_basis": "#4547's readout reports max_edge_over_control_pp = 0.28 as "
                             "the largest gap it measured and called a clean null; a "
                             "separation at or under that is at that instrument's "
                             "demonstrated floor",
        "per_leg": per_leg,
        "headline_leg": "SOLE:macd_bear",
        "headline": per_leg.get("SOLE:macd_bear", {}).get("verdict"),
        "frozen_original_for_reference": {
            f"H{h}": {leg: fr.get(f"H{h}", {}).get(leg, {}).get("vs_control_per_name_pp")
                      for leg in LEGS} for h in VLI.HORIZONS},
    }


def main() -> None:
    px_cache, px_adj, control = build_two_panels()
    m = control["observed_cell_mask"]
    print(f"basis control: masks_identical={m['masks_identical']} "
          f"cells={m['intersection_cells']} names={px_cache.shape[1]} "
          f"sessions={px_cache.shape[0]}", flush=True)
    if not m["masks_identical"]:
        raise SystemExit("mask control FAILED — the two runs would not see the same cells")

    sector_of = VLI._sector_map()
    panels_cache, diag_cache = VLI.build_panels(px_cache)
    print(f"A gate: {diag_cache['equality_gate']['status']}", flush=True)
    panels_adj, diag_adj = VLI.build_panels(px_adj)
    print(f"B gate: {diag_adj['equality_gate']['status']}", flush=True)

    runs = {
        # A: legs and returns both from the cache basis — the as-shipped construction,
        #    re-masked so it is cell-for-cell comparable with B.
        "A_cache_today": VLI.section_isolation(px_cache, panels_cache, sector_of),
        # C: cohorts held at A's, returns re-priced — isolates the OUTCOME channel.
        "C_cache_cohorts_adjusted_returns": VLI.section_isolation(px_adj, panels_cache, sector_of),
        # B: legs and returns both adjusted — the corrected construction.
        "B_adjusted": VLI.section_isolation(px_adj, panels_adj, sector_of),
    }
    frozen = json.load(open(FROZEN))

    coh_c, coh_a = VLI._cohorts(panels_cache), VLI._cohorts(panels_adj)
    res = {
        "instrument": "W5.1 per-leg veto isolation — ADJUSTED-BASIS RE-RUN (both columns)",
        "charter": "research/prophet_us_audit/MACD_BEAR_RATIFICATION_PACKET.md §8",
        "scope": "MEASUREMENT ONLY — no gate/board/engine/config change follows; W5 stays "
                 "sequenced behind G0.2 and operator ratification",
        "supersedes_nothing": "veto_leg_isolation_results.json is NOT overwritten — it is "
                              "the frozen artifact the packet's original numbers came from",
        "repro_asof": VLI.REPRO_ASOF,
        "as_shipped_read_date": AS_SHIPPED_READ_DATE,
        "horizons": list(VLI.HORIZONS),
        "loser_def_pp": VLI.LOSER_PP,
        "section_0_ladder_receipt": ladder_receipt(),
        "section_1_basis_control": control,
        "section_2_leg_diagnostics": {
            "A_cache_today": {k: diag_cache[k] for k in
                             ("in_range_name_days", "fire_counts_name_days", "dead_legs",
                              "equality_gate", "universe_names", "sessions")},
            "B_adjusted": {k: diag_adj[k] for k in
                           ("in_range_name_days", "fire_counts_name_days", "dead_legs",
                            "equality_gate", "universe_names", "sessions")},
            "cohort_cell_counts": {
                k: {"A_cache_today": int(coh_c[k].sum()), "B_adjusted": int(coh_a[k].sum()),
                    "pct_change": VLI._r(100.0 * (int(coh_a[k].sum()) - int(coh_c[k].sum()))
                                         / max(int(coh_c[k].sum()), 1), 1)}
                for k in KEYCELLS},
            "cohort_channel_note": "a cohort count that moves is the LEGS moving on the "
                                   "corrected basis, not the bias — run C separates it",
        },
        "section_3_both_columns_full_frame": both_columns(runs, "full_frame"),
        "section_4_both_columns_recent_window": both_columns(runs, "battery_window"),
        "section_5_forfeiture_adjusted": {
            "as_shipped": frozen["section_3_forfeiture_pricing"]["volume"],
            "adjusted": {
                "admitted_name_days_now": int(coh_a["CONTROL:admitted"].sum()),
                "added_name_days": int(coh_a["SOLE:macd_bear"].sum()),
                "widening_pct": VLI._r(100.0 * int(coh_a["SOLE:macd_bear"].sum())
                                       / max(int(coh_a["CONTROL:admitted"].sum()), 1), 1),
            },
            "union_board_delta_vs_control": {
                f"H{h}": {
                    tag: {
                        "union_pnf_pp": _cells(iso, "full_frame", h)
                        .get("UNION:board_without_macd_bear", {})
                        .get("per_name_first_median_pp"),
                        "control_pnf_pp": _cells(iso, "full_frame", h)
                        .get("CONTROL:admitted", {}).get("per_name_first_median_pp"),
                        "union_loser_pct": _cells(iso, "full_frame", h)
                        .get("UNION:board_without_macd_bear", {}).get("loser_rate_pct"),
                        "control_loser_pct": _cells(iso, "full_frame", h)
                        .get("CONTROL:admitted", {}).get("loser_rate_pct"),
                    } for tag, iso in runs.items()} for h in VLI.HORIZONS},
        },
        "section_6_frozen_vs_cache_today": {
            "question": "how far does the re-masked cache column sit from the committed "
                        "frozen JSON the packet's numbers were reported from?",
            "not_decomposable_here": "this gap conflates THREE causes and this file does "
                                     "not separate them: (1) STORE DRIFT — the breadth "
                                     "caches re-base between reads, so a past session's "
                                     "close is not stable (#4698: PNC 2026-06-22 read "
                                     "234.71 on 07-01, 232.85 today); (2) UNIVERSE — the "
                                     "adjusted ladder has no source for 266 of 1,493 "
                                     "names, and they are dropped from BOTH columns; "
                                     "(3) PHASE — the names whose first observation moved "
                                     "under the intersection mask. Do not read this gap "
                                     "as a basis effect; the basis effect is A-vs-B.",
            "frozen": {f"H{h}": {leg: frozen["readout"]["per_leg_vs_control"]
                                 .get(f"H{h}", {}).get(leg, {}).get("vs_control_per_name_pp")
                                 for leg in LEGS} for h in VLI.HORIZONS},
            "cache_today": {f"H{h}": {
                leg: _cells(runs["A_cache_today"], "full_frame", h)
                .get(leg, {}).get("vs_control_per_name_pp") for leg in LEGS}
                for h in VLI.HORIZONS},
            "frozen_universe_names": frozen["section_0_provenance"]["universe"][
                "universe_after_min_history"],
            "cache_today_universe_names": int(px_cache.shape[1]),
            "frozen_read_date": AS_SHIPPED_READ_DATE,
        },
        "readout": verdict(both_columns(runs, "full_frame"), frozen, runs),
    }
    with open(OUT, "w") as fh:
        json.dump(res, fh, indent=1, sort_keys=False, default=str)
    print(f"wrote {OUT}", flush=True)
    print(json.dumps(res["readout"], indent=1, default=str), flush=True)


if __name__ == "__main__":
    main()
