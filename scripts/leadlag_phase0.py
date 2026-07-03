"""
W5.1 — Lead-Lag Phase-0 (pre-registered, two-stage, HARD STOP)
==============================================================

The LAST gated question of the Cycle Intelligence Masterplan: **does exploitable
cross-asset lead-lag exist, or does the interaction layer STOP at a sync gauge?**

Study design is D5_PREDICTION.md §4.2 verbatim; the binding gate is PREREGISTRATION.md
§5 (LL-A / LL-B). This script embodies the TWO-COMMIT discipline:

  commit 1 (protocol):  --emit-protocol writes the FROZEN pre-registration block into
                        data/cycle_hazard/leadlag_phase0.json BEFORE any result exists.
  commit 2 (results):   --run computes Stage A (screen) + Stage B (OOS refit), appends
                        results under the SAME frozen criteria, freezes the top-20 pairs
                        into data/leadlag/frozen_pairs.json, and evaluates the gate.

The STOP rule is written into the artifact before the run and is evaluated VERBATIM.

Integrity trap (D5 §4 / D5_PREDICTION.md §4.2): a leader's turn is only usable at the
follower's decision time t if the leader's turn was CONFIRMED by t (confirmed_at <= t).
A lead measured on the PIVOT date (`event_date`) is a confirmation-lag artifact — the
future leaking backward. Stage A's event-study and Stage B's `leader_turned_3m` feature
BOTH gate on confirmed_at, never on the pivot. `tests/test_leadlag_phase0.py` proves a
synthetic leader that confirms LATE cannot produce a usable lead.

Universe (66 NON-BLOC instruments; A14 drops the 7 mechanical bloc composites; D5 §4.2
"within {11 US sectors}, within {24 countries}, within {31 CN sectors}"):
  11 US sectors + 24 single-country ETFs + 31 CN Shenwan L1 = 66.
  Excluded blocs: AAXJ, EEM, EFA, ILF, VGK, VPL, VXUS.

Statistical contract
--------------------
Stage A statistic: cross-correlation of monthly Δpos (first difference of the panel's
detrended osc `pos_osc`, which whitens the near-integrated level series) at lags 1..6
months, per ORDERED pair (leader→follower). Null band by block bootstrap on the
follower's Δpos series (circular block shuffle of the leader relative to the follower,
block=STAGE_A_BLOCK_M months, B=STAGE_A_BOOT draws), two-sided p per pair×lag, then
BH-FDR at q=0.10 across ALL pairs×lags (`grading_stats.fdr_bh`). Event-study variant:
for each pair, distribution of (follower confirmed-turn date − nearest PRIOR leader
confirmed-turn date), effective-n = number of FOLLOWER turns (EWZ ~112, XLC ~7; pairs
into low-turn followers are near-untestable and reported as such).

Stage B statistic: for the frozen top-20 pairs, add ONE feature `leader_turned_3m` to
the follower's hazard design and refit the W4.2 walk-forward (fit_cycle_hazard machinery)
on the OOS window (first_test_year=2018, train <=2017 only — the SAME cutoff Stage A
froze on). Pooled OOS 3m Brier of (leader model) vs (same design refit WITHOUT the leader
feature). Gate: rel. Brier improvement >=2% AND positive in >=2/3 walk-forward year-blocks
AND paired month-block bootstrap 90% CI on ΔBrier excludes 0.

Seed=7, draws=800 (repo BOOT_SEED/BOOT_DRAWS) for Stage B; Stage A uses its own frozen
STAGE_A_BOOT=2000 (D5 §4.2 "B=2000").

Runtime: Stage A ~66×66×6 correlations on ~200 months (trivial). Stage B <=20 logistic
refits (minutes). One-off research run — NOT pipeline-batch (masterplan §4 ops note).

Usage
-----
  python scripts/leadlag_phase0.py --emit-protocol   # commit 1 (criteria only)
  python scripts/leadlag_phase0.py --run             # commit 2 (append results)
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.grading_stats import fdr_bh  # noqa: E402

# ── Paths ────────────────────────────────────────────────────────────────────
PANEL_PATH = ROOT / "data" / "hazard" / "panel_price_c4414dcb.parquet"
ARTIFACT_PATH = ROOT / "data" / "cycle_hazard" / "leadlag_phase0.json"
FROZEN_PAIRS_PATH = ROOT / "data" / "leadlag" / "frozen_pairs.json"
YAHOO_DIR = ROOT / "data" / "yahoo"
CN_DIR = ROOT / "data" / "china_sectors"

# ── FROZEN pre-registered parameters (do NOT move after commit 1) ────────────
TRAIN_CUTOFF = "2017-12-31"          # Stage A screens on TRAIN <= this only
OOS_FIRST_TEST_YEAR = 2018           # Stage B walk-forward first test year
LAGS = [1, 2, 3, 4, 5, 6]            # months (D5 §4.2 "lags 1..6 months")
TOP_K = 20                           # frozen top-K pairs (D5 §4.2 K=20)
FDR_Q = 0.10                         # BH-FDR q (LL-A family)
STAGE_A_BOOT = 2000                  # D5 §4.2 "B=2000"
STAGE_A_BLOCK_M = 1                  # dates already monthly → 1-month blocks
STAGE_A_SEED = 7
MIN_TRAIN_MONTHS = 24                # min overlapping TRAIN months to screen a pair
LEADER_TURN_WINDOW_M = 3             # `leader_turned_3m`: confirmed opposite pivot <=3m
STAGE_B_TARGET_H = 3                 # primary endpoint: 3-month Brier
REL_BRIER_BAR = 0.02                 # LL-B: >=2% relative improvement
YEAR_BLOCK_FRAC = 2.0 / 3.0          # LL-B: positive in >=2/3 year blocks
CI_LO_PCT, CI_HI_PCT = 5.0, 95.0     # 90% CI

# Universe — 66 NON-BLOC instruments (A14: blocs dropped) ----------------------
US_SECTOR_IDS = ["XLB", "XLC", "XLE", "XLF", "XLI", "XLK", "XLP", "XLRE", "XLU", "XLV", "XLY"]
BLOC_IDS = {"AAXJ", "EEM", "EFA", "ILF", "VGK", "VPL", "VXUS"}  # A14 mechanical composites
COUNTRY_IDS = [i for i in [
    "AAXJ", "ECH", "EEM", "EFA", "EIDO", "EPOL", "EWA", "EWC", "EWD", "EWG",
    "EWH", "EWI", "EWJ", "EWL", "EWN", "EWP", "EWQ", "EWS", "EWT", "EWU",
    "EWW", "EWY", "EWZ", "EZA", "FXI", "ILF", "INDA", "TUR", "VGK", "VPL", "VXUS",
] if i not in BLOC_IDS]  # → 24 single-country ETFs
CN_SECTOR_IDS = [
    "801010", "801030", "801040", "801050", "801080", "801110", "801120",
    "801130", "801140", "801150", "801160", "801170", "801180", "801200",
    "801210", "801230", "801710", "801720", "801730", "801740", "801750",
    "801760", "801770", "801780", "801790", "801880", "801890", "801950",
    "801960", "801970", "801980",
]
NONBLOC_IDS = US_SECTOR_IDS + COUNTRY_IDS + CN_SECTOR_IDS  # 66

TURN_DEF_VERSION = "price_c4414dcb"


# ═════════════════════════════════════════════════════════════════════════════
# Pre-registration block (commit 1 writes this BEFORE any result)
# ═════════════════════════════════════════════════════════════════════════════

def preregistration_block() -> dict:
    """The FROZEN protocol. Written to the artifact before Stage B runs (two-commit
    discipline). Criteria here are the LL-A / LL-B gate verbatim from PREREGISTRATION.md
    §5 and the STOP rule from D5_PREDICTION.md §4.2. Do not edit after commit 1."""
    return {
        "wave": "W5.1",
        "study": "lead-lag phase-0 (pre-registered, two-stage, hard STOP)",
        "frozen_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "turn_def_version": TURN_DEF_VERSION,
        "universe": {
            "n_instruments": len(NONBLOC_IDS),
            "us_sector": US_SECTOR_IDS,
            "country_single": COUNTRY_IDS,
            "cn_sector": CN_SECTOR_IDS,
            "excluded_blocs": sorted(BLOC_IDS),
            "note": "A14: 7 mechanical bloc composites dropped; D5 §4.2 within-family pairs only.",
        },
        "params": {
            "train_cutoff": TRAIN_CUTOFF,
            "oos_first_test_year": OOS_FIRST_TEST_YEAR,
            "lags_months": LAGS,
            "top_k": TOP_K,
            "fdr_q": FDR_Q,
            "stage_a_boot": STAGE_A_BOOT,
            "stage_a_block_months": STAGE_A_BLOCK_M,
            "stage_a_seed": STAGE_A_SEED,
            "min_train_months": MIN_TRAIN_MONTHS,
            "leader_turn_window_m": LEADER_TURN_WINDOW_M,
            "stage_b_target_horizon": STAGE_B_TARGET_H,
            "rel_brier_bar": REL_BRIER_BAR,
            "year_block_frac": YEAR_BLOCK_FRAC,
            "ci_pct": [CI_LO_PCT, CI_HI_PCT],
        },
        "gate_LL_A": {
            "claim": "some ordered pair's lagged Δphase-position leads",
            "criterion": (
                ">=1 pair×lag survives BH-FDR q=0.10 across ALL pairs×lags on the "
                "<=2017 TRAIN cross-correlation (Δosc, block-bootstrap null band)"
            ),
            "judged_by": "stageA.fdr_survivors",
            "fdr_family": "leadlag_A",
        },
        "gate_LL_B": {
            "claim": "knowing the leader's confirmed turn improves the follower's OOS hazard",
            "criterion": (
                "for the frozen top-K=20 pairs: pooled OOS 3m Brier improvement >= 2% "
                "AND positive in >= 2/3 walk-forward year-blocks AND paired month-block "
                "bootstrap 90% CI on ΔBrier excludes 0"
            ),
            "judged_by": "stageB.{rel_brier_improvement, year_block_signs, ci90}",
            "fdr_family": "leadlag_B",
        },
        "confirmed_at_discipline": (
            "A leader turn is usable at follower decision time t iff confirmed_at <= t. "
            "Leads keyed on pivot dates (event_date) are FORBIDDEN — they leak the future. "
            "Both the Stage-A event study and the Stage-B leader_turned_3m feature gate on "
            "confirmed_at. Verified by tests/test_leadlag_phase0.py::test_late_confirmation_no_lead."
        ),
        "stop_rule": (
            "If Stage A yields no FDR survivors OR Stage B fails the criterion → verdict "
            "NO-GO: do NOT build the interaction layer. Ship instead the measured "
            "synchronization statistic sync = 1 − circ_var(2π·pos/100) per family, "
            "validated as a conditioning state, replacing markets.html's fake convergence "
            "bands with a measured gauge on measurement.html. And stop there."
        ),
        "prior_expectation": (
            "Per masterplan §6.5, every predictive gate in this program has FAILED "
            "(keystone NO-EDGE, CC-1/2/3 FAIL, BC-1 FAIL). Wave prompts must NOT assume "
            "this gate passes. The pre-committed likely outcome is STOP + sync gauge."
        ),
    }


# ═════════════════════════════════════════════════════════════════════════════
# Data loading
# ═════════════════════════════════════════════════════════════════════════════

def load_pos_panel() -> pd.DataFrame:
    """One monthly `pos` series per (id, date) from the hazard panel. pos_osc is
    direction-partitioned (an (id,date) appears in exactly one of up/down rows);
    collapsing with .first() reconstructs the single active-leg oscillator series."""
    df = pd.read_parquet(PANEL_PATH, columns=["id", "date", "pos_osc"])
    df = df[df["id"].isin(NONBLOC_IDS)].copy()
    one = df.groupby(["id", "date"], as_index=False)["pos_osc"].first()
    one = one.rename(columns={"pos_osc": "pos"})
    return one


def wide_dpos(pos_panel: pd.DataFrame, cutoff: str | None = None) -> pd.DataFrame:
    """Wide monthly Δpos frame: rows=month, cols=instrument, values=first-difference of
    pos. Whitens the near-integrated level series (D5 §4.2)."""
    p = pos_panel.copy()
    p["date"] = pd.to_datetime(p["date"]).dt.to_period("M").dt.to_timestamp("M")
    wide = p.pivot_table(index="date", columns="id", values="pos", aggfunc="first")
    if cutoff is not None:
        wide = wide[wide.index <= pd.Timestamp(cutoff)]
    dpos = wide.diff()
    return dpos


# ═════════════════════════════════════════════════════════════════════════════
# Stage A — cross-correlation screen (TRAIN <= 2017 only)
# ═════════════════════════════════════════════════════════════════════════════

def _lagged_corr(lead: np.ndarray, follow: np.ndarray, k: int):
    """corr(lead[t-k], follow[t]) on the overlapping non-NaN window. Returns (r, n)."""
    if k <= 0:
        return np.nan, 0
    a = lead[:-k]
    b = follow[k:]
    m = np.isfinite(a) & np.isfinite(b)
    n = int(m.sum())
    if n < MIN_TRAIN_MONTHS:
        return np.nan, n
    a, b = a[m], b[m]
    if a.std() < 1e-9 or b.std() < 1e-9:
        return np.nan, n
    return float(np.corrcoef(a, b)[0, 1]), n


def _block_perm_null_p(lead: np.ndarray, follow: np.ndarray, k: int, r_obs: float,
                       *, block_m: int, boot: int, seed: int) -> float:
    """Two-sided p-value for the lagged corr via circular block permutation of the
    LEADER series relative to the follower (block=block_m months). Preserves each
    series' autocorrelation while destroying cross-series alignment → an honest null
    band for near-integrated whitened Δpos (D5 §4.2 block-bootstrap null)."""
    a_full = lead[:-k]
    b_full = follow[k:]
    m = np.isfinite(a_full) & np.isfinite(b_full)
    a = a_full[m]
    b = b_full[m]
    n = len(a)
    if n < MIN_TRAIN_MONTHS or not np.isfinite(r_obs):
        return np.nan
    rng = np.random.default_rng(seed)
    nb = max(1, n // block_m)
    ge = 0
    for _ in range(boot):
        shift = int(rng.integers(1, n)) if n > 1 else 0
        a_perm = np.roll(a, shift)
        if a_perm.std() < 1e-9 or b.std() < 1e-9:
            r = 0.0
        else:
            r = float(np.corrcoef(a_perm, b)[0, 1])
        if abs(r) >= abs(r_obs):
            ge += 1
    return (ge + 1) / (boot + 1)


def stage_a_screen(pos_panel: pd.DataFrame) -> dict:
    """Screen all ordered WITHIN-FAMILY pairs × lags 1..6 on TRAIN <= 2017. Returns the
    ranked table + BH-FDR survivors."""
    dpos = wide_dpos(pos_panel, cutoff=TRAIN_CUTOFF)
    families = {"us_sector": US_SECTOR_IDS, "country": COUNTRY_IDS, "cn_sector": CN_SECTOR_IDS}
    present = set(dpos.columns)

    rows = []
    pvals = {}
    for fam, ids in families.items():
        fids = [i for i in ids if i in present]
        arrs = {i: dpos[i].to_numpy(float) for i in fids}
        for lead in fids:
            for follow in fids:
                if lead == follow:
                    continue
                for k in LAGS:
                    r, n = _lagged_corr(arrs[lead], arrs[follow], k)
                    if not np.isfinite(r):
                        continue
                    key = f"{fam}|{lead}->{follow}|lag{k}"
                    p = _block_perm_null_p(
                        arrs[lead], arrs[follow], k, r,
                        block_m=STAGE_A_BLOCK_M, boot=STAGE_A_BOOT, seed=STAGE_A_SEED,
                    )
                    rows.append({
                        "key": key, "family": fam, "leader": lead, "follower": follow,
                        "lag": k, "r": round(r, 4), "n": n, "p": round(float(p), 5),
                    })
                    pvals[key] = float(p)

    survivors_mask = fdr_bh(pvals, q=FDR_Q) if pvals else {}
    survivors = [k for k, ok in survivors_mask.items() if ok]
    for row in rows:
        row["fdr_survivor"] = bool(survivors_mask.get(row["key"], False))

    # Rank by screened strength: FDR survivors first, then by |r| (ties by smaller p).
    rows_sorted = sorted(rows, key=lambda x: (not x["fdr_survivor"], -abs(x["r"]), x["p"]))
    top_k = rows_sorted[:TOP_K]

    return {
        "n_pairs_x_lags": len(rows),
        "n_fdr_survivors": len(survivors),
        "fdr_survivors": sorted(survivors),
        "fdr_q": FDR_Q,
        "top_k": top_k,
        "all_rows": rows_sorted,
    }


# ═════════════════════════════════════════════════════════════════════════════
# Confirmed turns (the integrity trap) — reconstructed from price via detect_turns
# ═════════════════════════════════════════════════════════════════════════════

def load_confirmed_turns() -> dict:
    """Per-instrument confirmed turns (list of dicts with pivot date, kind, confirmed_at)
    reconstructed from the STRUCTURE-MATH price basis via engine.cycle_ontology.detect_turns
    (reusing build_hazard_panel's exact loaders/params). Provisional open legs are dropped.
    confirmed_at is the bar the reversal threshold was first crossed — the ONLY PIT-honest
    'usable at t' timestamp. event_date/pivot is NEVER used as the usable timestamp."""
    from engine.cycle_ontology import detect_turns, TurnParams
    from scripts.build_hazard_panel import (
        _load_yahoo_price, _load_cn_sector_close, ZZ_PCT_US, ZZ_PCT_COUNTRY, ZZ_PCT_CN,
    )

    def _turns(px, sid, pct):
        if px is None or len(px.dropna()) < 30:
            return []
        params = TurnParams(pct=pct, basis="close_price", freq="D", version=2)
        ts = detect_turns(px, series_id=sid, params=params)
        return [t for t in ts if not t.get("provisional", False)]

    out = {}
    for iid in US_SECTOR_IDS:
        out[iid] = _turns(_load_yahoo_price(iid, YAHOO_DIR), iid, ZZ_PCT_US)
    for iid in COUNTRY_IDS:
        out[iid] = _turns(_load_yahoo_price(iid, YAHOO_DIR), iid, ZZ_PCT_COUNTRY)
    for iid in CN_SECTOR_IDS:
        out[iid] = _turns(_load_cn_sector_close(iid, CN_DIR), iid, ZZ_PCT_CN)
    return out


def event_study(pair_rows: list[dict], turns: dict) -> list[dict]:
    """For each candidate pair: distribution of (follower CONFIRMED-turn date − nearest
    PRIOR leader CONFIRMED-turn date). effective-n = # follower turns. A NEGATIVE median
    lead (leader confirms before follower turns) is the only usable direction; a lead
    measured on pivots would be a confirmation-lag artifact (see confirmed_at discipline)."""
    seen = set()
    out = []
    for row in pair_rows:
        pk = (row["leader"], row["follower"])
        if pk in seen:
            continue
        seen.add(pk)
        lead_conf = sorted(pd.Timestamp(t["confirmed_at"]) for t in turns.get(row["leader"], []))
        fol_turns = turns.get(row["follower"], [])
        n_fol = len(fol_turns)
        gaps_m = []
        for ft in fol_turns:
            f_conf = pd.Timestamp(ft["confirmed_at"])
            prior = [lc for lc in lead_conf if lc <= f_conf]
            if not prior:
                continue
            gap_days = (f_conf - prior[-1]).days
            gaps_m.append(gap_days / 30.44)
        out.append({
            "leader": row["leader"], "follower": row["follower"],
            "n_follower_turns": n_fol,
            "median_lead_months": round(float(np.median(gaps_m)), 2) if gaps_m else None,
            "n_matched": len(gaps_m),
            "testable": n_fol >= 8,   # effective-n discipline (D5 §4.2)
        })
    return out


# ═════════════════════════════════════════════════════════════════════════════
# Stage B — OOS hazard refit with the leader feature (frozen pairs only)
# ═════════════════════════════════════════════════════════════════════════════

def _leader_turned_feature(panel: pd.DataFrame, leader: str, turns: dict) -> np.ndarray:
    """leader_turned_3m ∈ {0,1} per follower row: 1 iff the leader printed a CONFIRMED
    turn whose confirmed_at ∈ (t − LEADER_TURN_WINDOW_M months, t]. PIT-honest: uses
    confirmed_at, never the pivot. This is the integrity trap made executable.

    Comparisons use pandas Timestamps directly (the panel `date` is datetime64[us]; a raw
    int64 view would be MICROseconds while Timestamp.value is nanoseconds — a unit trap)."""
    lead_conf = sorted(pd.Timestamp(t["confirmed_at"]) for t in turns.get(leader, []))
    lead_conf = np.array(lead_conf, dtype="datetime64[ns]")
    win = pd.DateOffset(months=LEADER_TURN_WINDOW_M)
    feat = np.zeros(len(panel), dtype=float)
    if len(lead_conf) == 0:
        return feat
    dates = pd.to_datetime(panel["date"]).to_numpy(dtype="datetime64[ns]")
    for i, t_dt in enumerate(dates):
        t_ts = pd.Timestamp(t_dt)
        lo = np.datetime64(t_ts - win)
        # confirmed in (t-window, t]
        cnt = np.count_nonzero((lead_conf <= np.datetime64(t_ts)) & (lead_conf > lo))
        feat[i] = 1.0 if cnt > 0 else 0.0
    return feat


def stage_b_refit(frozen_pairs: list[dict], turns: dict, seed: int = 7) -> dict:
    """For the frozen top-K pairs, refit the follower's hazard walk-forward on OOS
    (first_test_year=2018) WITH and WITHOUT the leader_turned_3m feature; measure pooled
    3m Brier lift. Reuses fit_cycle_hazard's exact design/logistic/calibration."""
    from scripts import fit_cycle_hazard as fch

    full = pd.read_parquet(PANEL_PATH)
    full = full[full["id"].isin(NONBLOC_IDS)].copy()
    full["date"] = pd.to_datetime(full["date"])
    design_base = fch.build_design(full)

    follower_ids = sorted({p["follower"] for p in frozen_pairs})
    # one leader feature column per (leader) — a follower may pair with several leaders;
    # we evaluate each PAIR's follower rows independently (the frozen pair is the unit).
    per_pair = []
    all_dates, all_y, all_p_base, all_p_lead = [], [], [], []

    for pair in frozen_pairs:
        leader, follower = pair["leader"], pair["follower"]
        sub = design_base[design_base["id"] == follower].copy()
        if sub.empty:
            per_pair.append({**_pair_id(pair), "skipped": "no_follower_rows"})
            continue
        sub["leader_turned_3m"] = _leader_turned_feature(sub, leader, turns)

        base = _wf_pooled(fch, sub, extra=None, seed=seed)
        lead = _wf_pooled(fch, sub, extra="leader_turned_3m", seed=seed)
        if base is None or lead is None:
            per_pair.append({**_pair_id(pair), "skipped": "insufficient_oos"})
            continue

        d, y, pb, pl = base["dates"], base["y3"], base["p3"], lead["p3"]
        brier_b = float(np.mean((pb - y) ** 2))
        brier_l = float(np.mean((pl - y) ** 2))
        rel = (brier_b - brier_l) / brier_b if brier_b > 0 else 0.0
        per_pair.append({
            **_pair_id(pair),
            "n_oos": int(len(y)),
            "brier_base": round(brier_b, 6),
            "brier_leader": round(brier_l, 6),
            "rel_improvement": round(rel, 5),
            "leader_feat_active_frac": round(float(sub["leader_turned_3m"].mean()), 4),
        })
        all_dates.append(d); all_y.append(y); all_p_base.append(pb); all_p_lead.append(pl)

    if not all_dates:
        return {"pooled": None, "per_pair": per_pair, "note": "no evaluable pairs"}

    D = np.concatenate(all_dates)
    Y = np.concatenate(all_y)
    PB = np.concatenate(all_p_base)
    PL = np.concatenate(all_p_lead)

    br_base = float(np.mean((PB - Y) ** 2))
    br_lead = float(np.mean((PL - Y) ** 2))
    rel_imp = (br_base - br_lead) / br_base if br_base > 0 else 0.0

    # year-block signs
    yr = pd.to_datetime(D).year
    year_signs = {}
    for y_ in sorted(set(yr)):
        mask = yr == y_
        bb = float(np.mean((PB[mask] - Y[mask]) ** 2))
        bl = float(np.mean((PL[mask] - Y[mask]) ** 2))
        year_signs[int(y_)] = 1 if (bb - bl) > 0 else -1 if (bb - bl) < 0 else 0
    n_pos = sum(1 for v in year_signs.values() if v > 0)
    n_yr = len(year_signs)

    # paired month-block bootstrap 90% CI on ΔBrier = Brier_base − Brier_leader
    b_base_row = (PB - Y) ** 2
    b_lead_row = (PL - Y) ** 2
    point, lo, hi = fch.month_block_brier_gap_ci(
        D, b_base_row, b_lead_row, draws=fch.BOOT_DRAWS, seed=seed,
        lo_pct=CI_LO_PCT, hi_pct=CI_HI_PCT,
    )

    return {
        "pooled": {
            "n_oos": int(len(Y)),
            "brier_base": round(br_base, 6),
            "brier_leader": round(br_lead, 6),
            "rel_brier_improvement": round(float(rel_imp), 5),
            "year_block_signs": year_signs,
            "n_year_blocks": n_yr,
            "n_year_blocks_positive": n_pos,
            "delta_brier_point": round(float(point), 6),
            "ci90": [round(float(lo), 6) if lo is not None else None,
                     round(float(hi), 6) if hi is not None else None],
        },
        "per_pair": per_pair,
    }


def _pair_id(pair: dict) -> dict:
    return {"family": pair.get("family"), "leader": pair["leader"],
            "follower": pair["follower"], "lag": pair.get("lag")}


def _wf_pooled(fch, sub: pd.DataFrame, extra: str | None, seed: int):
    """Run fit_cycle_hazard's walk-forward on a single-follower slice with OPTIONAL one
    extra design column. first_test_year=2018 (train <=2017 only). Returns pooled OOS
    3m predictions (calibrated out-of-fold, same as the W4.2 skill gate)."""
    design = list(fch.DESIGN) + ([extra] if extra else [])
    l2_exempt = fch.L2_MASK_EXEMPT

    sub = sub.sort_values("date").reset_index(drop=True)
    years = sorted(sub["date"].dt.year.unique())
    if not years:
        return None
    last_year = years[-1]

    dates_out, y3_out, p3_out = [], [], []
    n_folds = 0
    for Y in range(OOS_FIRST_TEST_YEAR, last_year + 1):
        cut = pd.Timestamp(year=Y - 1, month=12, day=31) - pd.DateOffset(months=fch.EMBARGO_M)
        train = sub[sub["date"] <= cut]
        test = sub[sub["date"].dt.year == Y]
        if len(train) < 60 or len(test) == 0:
            continue
        mu = train[fch.CONT_FEATURES].mean()
        sd = train[fch.CONT_FEATURES].replace(0, np.nan).std(ddof=0).fillna(1.0).replace(0, 1.0)

        def _mat(df):
            m = df[design].copy()
            for c in fch.CONT_FEATURES:
                m[c] = (df[c] - mu[c]) / sd[c]
            return m[design].to_numpy(dtype=float)

        Xtr, ytr = _mat(train), train["y1"].to_numpy(float)
        Xte = _mat(test)
        l2_mask = np.array([c not in l2_exempt for c in design])
        w, b = fch.fit_logistic_l2(Xtr, ytr, l2_mask)
        p1_tr = fch._sigmoid(Xtr @ w + b)
        p1_te = fch._sigmoid(Xte @ w + b)
        h = STAGE_B_TARGET_H
        p_tr_h = 1.0 - (1.0 - np.clip(p1_tr, 1e-6, 1 - 1e-6)) ** h
        p_te_h = 1.0 - (1.0 - np.clip(p1_te, 1e-6, 1 - 1e-6)) ** h
        from engine.validation import isotonic_calibration, apply_calibration
        iso = isotonic_calibration(p_tr_h, train[f"y{h}"].to_numpy(float))
        cal = apply_calibration(iso, p_te_h) if iso else p_te_h
        dates_out.append(test["date"].to_numpy())
        y3_out.append(test[f"y{h}"].to_numpy(float))
        p3_out.append(np.asarray(cal, float))
        n_folds += 1

    if n_folds == 0 or not y3_out:
        return None
    return {
        "dates": np.concatenate(dates_out),
        "y3": np.concatenate(y3_out),
        "p3": np.concatenate(p3_out),
    }


# ═════════════════════════════════════════════════════════════════════════════
# Gate evaluation (LL-A / LL-B VERBATIM)
# ═════════════════════════════════════════════════════════════════════════════

def evaluate_gate(stage_a: dict, stage_b: dict) -> dict:
    """Evaluate LL-A and LL-B verbatim; derive the GO / NO-GO verdict + STOP action."""
    ll_a_pass = stage_a["n_fdr_survivors"] >= 1

    ll_b_pass = False
    ll_b_detail = {}
    pooled = stage_b.get("pooled") if stage_b else None
    if pooled:
        rel_ok = pooled["rel_brier_improvement"] >= REL_BRIER_BAR
        yr_ok = pooled["n_year_blocks_positive"] >= np.ceil(YEAR_BLOCK_FRAC * pooled["n_year_blocks"])
        lo = pooled["ci90"][0]
        ci_ok = lo is not None and lo > 0.0
        ll_b_pass = bool(rel_ok and yr_ok and ci_ok)
        ll_b_detail = {"rel_ok": bool(rel_ok), "year_blocks_ok": bool(yr_ok), "ci_excludes_0": bool(ci_ok)}

    go = bool(ll_a_pass and ll_b_pass)
    return {
        "LL_A_pass": bool(ll_a_pass),
        "LL_B_pass": bool(ll_b_pass),
        "LL_B_detail": ll_b_detail,
        "verdict": "GO" if go else "NO-GO",
        "stop_action": None if go else "ship_sync_gauge",
    }


# ═════════════════════════════════════════════════════════════════════════════
# Sync gauge (the STOP fallback deliverable data)
# ═════════════════════════════════════════════════════════════════════════════

def compute_sync_gauge(pos_panel: pd.DataFrame) -> dict:
    """Per-family monthly synchronization: sync = 1 − circ_var(2π·pos/100), plus the
    fraction of instruments in each phase quadrant. This is the MEASURED gauge that ships
    on measurement.html when the verdict is STOP, replacing markets.html's fake
    convergence bands. History from the full backfill (all months)."""
    families = {"us_sector": US_SECTOR_IDS, "country": COUNTRY_IDS, "cn_sector": CN_SECTOR_IDS}
    p = pos_panel.copy()
    p["date"] = pd.to_datetime(p["date"]).dt.to_period("M").dt.to_timestamp("M")

    def _phase(pos):
        # 4 quadrants of the cycle wheel by position 0-100
        if pos < 25: return "trough"
        if pos < 50: return "advance"
        if pos < 75: return "peak"
        return "decline"

    out = {}
    for fam, ids in families.items():
        sub = p[p["id"].isin(ids)]
        recs = []
        for dt, g in sub.groupby("date"):
            vals = g["pos"].dropna().to_numpy(float)
            if len(vals) < 3:
                continue
            ang = 2 * np.pi * (vals / 100.0)
            R = np.sqrt(np.mean(np.cos(ang)) ** 2 + np.mean(np.sin(ang)) ** 2)
            circ_var = 1.0 - R
            sync = 1.0 - circ_var  # = R (mean resultant length)
            phases = {"trough": 0, "advance": 0, "peak": 0, "decline": 0}
            for v in vals:
                phases[_phase(v)] += 1
            n = len(vals)
            recs.append({
                "date": dt.strftime("%Y-%m-%d"),
                "sync": round(float(sync), 4),
                "n": int(n),
                "frac": {k: round(v / n, 3) for k, v in phases.items()},
            })
        out[fam] = recs
    return out


# ═════════════════════════════════════════════════════════════════════════════
# Orchestration
# ═════════════════════════════════════════════════════════════════════════════

def emit_protocol():
    """Commit 1: write the FROZEN pre-registration block only (no results)."""
    ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "leadlag_phase0/v1",
        "preregistration": preregistration_block(),
        "stageA": None,
        "stageB": None,
        "gate": None,
        "verdict": None,
        "generated_at": None,
        "note": "PROTOCOL COMMIT — criteria frozen before results (two-commit discipline).",
    }
    ARTIFACT_PATH.write_text(json.dumps(payload, indent=2))
    print(f"wrote FROZEN protocol → {ARTIFACT_PATH}")


def run():
    """Commit 2: compute Stage A + Stage B under the frozen criteria; append results."""
    t0 = datetime.now()
    if not ARTIFACT_PATH.exists():
        raise SystemExit("protocol block missing — run --emit-protocol first (two-commit discipline)")
    artifact = json.loads(ARTIFACT_PATH.read_text())
    prereg = artifact["preregistration"]

    print("Loading pos panel …")
    pos_panel = load_pos_panel()
    print(f"  {pos_panel['id'].nunique()} instruments, {len(pos_panel)} monthly stamps")

    print("Stage A — cross-correlation screen (TRAIN <= 2017) …")
    stage_a = stage_a_screen(pos_panel)
    print(f"  {stage_a['n_pairs_x_lags']} pairs×lags screened; "
          f"{stage_a['n_fdr_survivors']} survive BH-FDR q={FDR_Q}")

    print("Reconstructing confirmed turns (confirmed_at discipline) …")
    turns = load_confirmed_turns()
    stage_a["event_study"] = event_study(stage_a["top_k"], turns)

    # freeze the top-K pairs BEFORE Stage B
    frozen = [{"family": r["family"], "leader": r["leader"], "follower": r["follower"],
               "lag": r["lag"], "r": r["r"], "p": r["p"], "fdr_survivor": r["fdr_survivor"]}
              for r in stage_a["top_k"]]
    FROZEN_PAIRS_PATH.parent.mkdir(parents=True, exist_ok=True)
    FROZEN_PAIRS_PATH.write_text(json.dumps({
        "frozen_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "train_cutoff": TRAIN_CUTOFF, "top_k": TOP_K,
        "n_fdr_survivors": stage_a["n_fdr_survivors"], "pairs": frozen,
    }, indent=2))
    print(f"  froze top-{len(frozen)} pairs → {FROZEN_PAIRS_PATH}")

    print("Stage B — OOS hazard refit with leader feature (frozen pairs) …")
    stage_b = stage_b_refit(frozen, turns, seed=STAGE_A_SEED)
    if stage_b.get("pooled"):
        pl = stage_b["pooled"]
        print(f"  pooled rel Brier improvement = {pl['rel_brier_improvement']:+.3%}; "
              f"year-blocks +{pl['n_year_blocks_positive']}/{pl['n_year_blocks']}; "
              f"ΔBrier CI90 = {pl['ci90']}")

    gate = evaluate_gate(stage_a, stage_b)
    print(f"  VERDICT: {gate['verdict']}  (LL-A={gate['LL_A_pass']}, LL-B={gate['LL_B_pass']})")

    sync = None
    if gate["verdict"] == "NO-GO":
        print("STOP → computing sync gauge fallback …")
        sync = compute_sync_gauge(pos_panel)

    artifact.update({
        "stageA": {k: v for k, v in stage_a.items() if k != "all_rows"},
        "stageA_all_rows_n": len(stage_a["all_rows"]),
        "stageB": stage_b,
        "gate": gate,
        "verdict": gate["verdict"],
        "sync_gauge": sync,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "runtime_seconds": round((datetime.now() - t0).total_seconds(), 1),
        "note": "RESULTS COMMIT — criteria in `preregistration` were NOT moved.",
    })
    ARTIFACT_PATH.write_text(json.dumps(artifact, indent=2, default=str))
    print(f"wrote results → {ARTIFACT_PATH}  ({artifact['runtime_seconds']}s)")

    # sync gauge also to its own compact site-data file if STOP
    if sync is not None:
        sync_path = ROOT / "data" / "leadlag" / "sync_gauge.json"
        sync_path.write_text(json.dumps({
            "generated_at": artifact["generated_at"],
            "families": sync,
            "definition": "sync = 1 − circ_var(2π·pos/100); mean resultant length of phase angles",
        }, indent=2))
        print(f"wrote sync gauge → {sync_path}")


def main():
    ap = argparse.ArgumentParser(description="W5.1 lead-lag phase-0 (two-commit)")
    ap.add_argument("--emit-protocol", action="store_true", help="commit 1: freeze criteria")
    ap.add_argument("--run", action="store_true", help="commit 2: compute + append results")
    args = ap.parse_args()
    if args.emit_protocol:
        emit_protocol()
    elif args.run:
        run()
    else:
        ap.error("one of --emit-protocol / --run required")


if __name__ == "__main__":
    main()
