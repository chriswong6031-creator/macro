#!/usr/bin/env python3
"""regime_calibration_v2.py — CN LIMIT-MOVE ALPHA, Wave 2 / lane W2-A.

THE ONE QUESTION
    Wave 1's onset model B1 (lane L3) MISSED its pre-registered holdout Brier-skill bar
    against the 连板 ladder B0 — main -0.17%, chinext -11.69% — for a MEASURED reason, not a
    mysterious one.  Its discrimination is fine (AUC 0.775 vs the ladder's 0.592).  Its
    CALIBRATION is not: a frozen isotonic map inherits the base rate of the slice it was
    fitted on, and L3's calibration slice ran 1.30x (main) / 2.06x (chinext) hotter than the
    holdout.  ChiNext's B1 over-predicts by 2.58x as a direct consequence.

    Wave 1's lane L2 then measured the era-neutral regime dial that could fix exactly that:
    i5_realized_continuation_ma5 — the 5-session mean of "of the names whose prior usable bar
    was a limit-up, what share closed limit-up today".  Holdout top-vs-bottom quintile
    26.73% vs 12.61% = 2.121x, Spearman rho 1.0, era-neutral in 12 of 16 years.  L2 also
    measured that the RAW BREADTH COUNTS (涨停家数) INVERT within-year and must never be used
    as a same-year dial; only the continuation-rate family survives.

    This file merges the two and answers, on ONE holdout pass: does regime conditioning close
    B1's calibration gap, and which object should a desk actually read?

TIER
    Display / audit.  MEASUREMENT ONLY.  Nothing here promotes, ranks for size, gates, admits,
    or reaches a live surface.  No LLM is involved at any point.  Under the ORE LAW the null
    is printed, never buried, and the ORE LEDGER states what was NOT tested.

FOUR MODELS PLUS TWO BENCHMARKS, ONE EVALUATION PASS
    B0  LADDER-ONLY BENCHMARK  — L3's, unchanged: fit-window base rate per 连板 bucket N.
    R0  REGIME-LADDER BENCHMARK — fit-window base rate per (连板 N x i5 stratum) cell.  THE
        NEW, HARDER BAR.  If R0 alone beats both B0 and B1, the ladder+dial IS the model and
        the parametric machinery is again buying nothing (L3's B2-beats-B1 precedent).
    R1  B1 + REGIME COVARIATE — L3's exact logistic plus i5 (winsorised + standardised on the
        FIT CORE only) and a missing-indicator; pooled isotonic, exactly as B1.
    R2  REGIME-CONDITIONED CALIBRATION — THE CAUSAL FIX.  B1's raw logistic scores, unchanged,
        isotonic-calibrated SEPARATELY per i5 stratum.  Every calibration slice is carved from
        the FIT window's inner calibration slice; the holdout is never touched.
    R3  R1 + R2 — regime in the features AND in the calibration.

PRE-REGISTERED, WRITTEN BEFORE THE FIRST HOLDOUT PASS (see PREREGISTRATION below and the
receipt's own section; nothing was refit, retuned, re-split or re-bucketed after any holdout
number was seen).

BINDING CONVENTIONS — INHERITED VERBATIM, NOT RE-DECIDED
    Everything about the panel, the exclusions, the PRIMARY limit-up definition, the tolerant
    cushion, the no-pooling rule, the ChiNext 2020-08-24 era split, the fit/calibration/holdout
    boundaries, the THIN gates, Wilson intervals, and the metric definitions comes from
    onset_calibration_v1.py by IMPORT, not by re-implementation.  The regime series comes from
    board_ecology_series_v1.parquet as committed.  This file adds exactly three things: the
    regime join, the regime strata, and the four models above.

DEPENDENCIES (sibling Wave-1 artifacts; this lane does not vendor copies of them)
    research/cn_prophet_audit/onset_calibration_v1.py
        (branch claude/cn-limit-w1-onset)
    research/cn_prophet_audit/board_ecology_series_v1.parquet
        (branch claude/cn-limit-w1-regime-salvage)
    Both are required at those exact paths.  A missing file is a loud, named error — never a
    silent fallback, because a fallback would quietly change what "regime" means.

Run from repo root:  TZ=UTC python3 research/cn_prophet_audit/regime_calibration_v2.py
Outputs (frozen, committed):
    research/cn_prophet_audit/REGIME_CALIBRATION_V2_2026-08-09.json
    research/cn_prophet_audit/REGIME_CALIBRATION_V2_2026-08-09.md   (hand-written from JSON)
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import time
from pathlib import Path

os.environ["TZ"] = "UTC"
try:
    time.tzset()
except AttributeError:  # pragma: no cover - non-POSIX
    pass

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

OUT_DIR = REPO / "research" / "cn_prophet_audit"
OUT_JSON = OUT_DIR / "REGIME_CALIBRATION_V2_2026-08-09.json"
ONSET_PY = OUT_DIR / "onset_calibration_v1.py"
ECOLOGY_PARQUET = OUT_DIR / "board_ecology_series_v1.parquet"

_MISSING = (
    "MISSING WAVE-1 DEPENDENCY: {path}\n"
    "This lane MERGES two Wave-1 artifacts and deliberately does not vendor copies of them.\n"
    "Fetch them from their authoring branches:\n"
    "  git fetch origin claude/cn-limit-w1-onset claude/cn-limit-w1-regime-salvage\n"
    "  git show origin/claude/cn-limit-w1-onset:research/cn_prophet_audit/onset_calibration_v1.py"
    " > research/cn_prophet_audit/onset_calibration_v1.py\n"
    "  git show origin/claude/cn-limit-w1-regime-salvage:"
    "research/cn_prophet_audit/board_ecology_series_v1.parquet"
    " > research/cn_prophet_audit/board_ecology_series_v1.parquet\n"
    "(or simply run this after both Wave-1 PRs have merged to main)."
)

for _p in (ONSET_PY, ECOLOGY_PARQUET):
    if not _p.exists():
        raise SystemExit(_MISSING.format(path=_p))

_spec = importlib.util.spec_from_file_location("onset_calibration_v1", ONSET_PY)
onset = importlib.util.module_from_spec(_spec)
sys.modules["onset_calibration_v1"] = onset
_spec.loader.exec_module(onset)  # safe: onset_calibration_v1 guards its main() on __main__


# ── frozen parameters (this file's, pre-registered before the first run) ──────

REGIME_COL = "i5_realized_continuation_ma5"
REGIME_RAW_COL = "i5_realized_continuation"
N_STRATA = 3                    # terciles; collapses to halves under the pre-registered ladder
UNKNOWN_STRATUM = 9             # sentinel id for "the board printed no continuation rate"
TOP_FRACTION = 0.10             # "the top bins" = the top decile of P-hat by row
MIN_STRATUM_CALIB_POS = onset.MIN_CALIB_POS   # 50 — reuse L3's floor, do not invent a new one
MODEL_VERSION = "regime_cal_v2"

STRATUM_LABELS_3 = {0: "T1_cold", 1: "T2_mid", 2: "T3_hot", UNKNOWN_STRATUM: "UNKNOWN_no_print"}
STRATUM_LABELS_2 = {0: "H1_cold", 1: "H2_hot", UNKNOWN_STRATUM: "UNKNOWN_no_print"}

R1_EXTRA_COLS = ["i5_ma5_z", "i5_is_null"]
R1_COLS = list(onset.DESIGN_COLS) + R1_EXTRA_COLS

# STAR era re-split — PRE-REGISTERED AND AUTHORISED (L3 ORE row #3).  L3 printed STAR as a
# THIN-SKIP under v0's GLOBAL 70/30 date split, which hands a board that listed in 2019-07 a
# 33/67 split (565 fit dates vs 1,135 holdout).  L3 refused to re-split AFTER watching the gate
# fail — correctly.  The re-split is authorised here BEFORE any Wave-2 number is computed, and
# it is the identical mechanism ChiNext already gets: the board's own era, re-split 70/30
# inside it.  L3's global-split STAR gate is printed alongside so the change is auditable.
BOARD_SPLIT_RULE_V2 = {
    "main": "global",
    "chinext": "chinext_wide_era",
    "star": "star_listing_era",
}

# L3's PUBLISHED holdout numbers.  This file re-derives B0/B1 from L3's own code on the same
# store, so these are the gate that nothing drifted between the two runs.  A mismatch is
# printed loudly rather than absorbed.
L3_PARITY_TARGETS = {
    "main": {
        "holdout_rows": 1283376,
        "holdout_base_rate_pct": 1.204,
        "b1_brier_skill_vs_b0_pct": -0.17,
        "b1_auc": 0.775,
        "b0_auc": 0.592,
        "b1_top20_realized_pct": 12.317,
    },
    "chinext": {
        "holdout_rows": 135753,
        "holdout_base_rate_pct": 0.357,
        "b1_brier_skill_vs_b0_pct": -11.69,
        "b1_auc": 0.726,
        "b0_auc": 0.540,
        "b1_mean_p_over_realized": 2.58,
    },
}
PARITY_TOL = {"pct": 0.02, "auc": 0.0015, "rate": 0.001, "ratio": 0.02}


# ── STAGE 0 — the regime series, its join, and the lookahead audit ────────────

def head_sha() -> str:
    """The checkout's HEAD — the store vintage stamp.  Run-stamp field, like generated_utc."""
    try:
        import subprocess
        r = subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"],
                           capture_output=True, text=True, timeout=30, check=False)
        return r.stdout.strip() or "UNKNOWN"
    except Exception:  # noqa: BLE001
        return "UNKNOWN"


def _daykey(s: pd.Series) -> np.ndarray:
    """Calendar-day integer key.  Immune to the ns/ms unit mismatch between the two stores."""
    return s.to_numpy(dtype="datetime64[D]").astype(np.int64)


def load_regime_series() -> tuple[pd.DataFrame, dict]:
    ser = pd.read_parquet(ECOLOGY_PARQUET)
    ser["date"] = pd.to_datetime(ser["date"])
    keep = ["date", "board", REGIME_COL, REGIME_RAW_COL, "i5_pairs_n", "i5_k"]
    ser = ser[keep].sort_values(["board", "date"]).reset_index(drop=True)
    meta = {
        "source": "research/cn_prophet_audit/board_ecology_series_v1.parquet",
        "provenance": ("Wave-1 lane L2, branch claude/cn-limit-w1-regime-salvage.  Taken as "
                       "committed; NOT recomputed here — recomputing it would silently fork "
                       "the definition this lane is supposed to be testing."),
        "rows": len(ser),
        "boards": sorted(ser["board"].unique().tolist()),
        "regime_variable": REGIME_COL,
        "why_this_variable": (
            "L2 measured it as the ONLY era-neutral dial in the family: holdout top-vs-bottom "
            "quintile 2.121x, Spearman rho 1.0, monotone in both fit and holdout, era-neutral "
            "in 12 of 16 years.  L2 also measured that the raw breadth counts INVERT "
            "within-year (i1 era-neutral ratio 0.724, 12/16 years the WRONG way), so no "
            "absolute 涨停家数 count is admitted here as a conditioner."),
        "coverage_by_board": [],
    }
    for b, g in ser.groupby("board", sort=True):
        nn = int(g[REGIME_COL].notna().sum())
        meta["coverage_by_board"].append({
            "board": str(b),
            "sessions": len(g),
            "first_session": g["date"].min().strftime("%Y-%m-%d"),
            "last_session": g["date"].max().strftime("%Y-%m-%d"),
            "regime_non_null": nn,
            "regime_non_null_pct": round(100.0 * nn / max(1, len(g)), 2),
        })
    return ser, meta


def join_regime(panel: pd.DataFrame, ser: pd.DataFrame) -> pd.DataFrame:
    """LEFT-join the board's own daily regime print onto the FEATURE bar T.  Never onto T+1.

    The alignment is the whole safety question of this lane, so it is joined on an explicit
    day key and then AUDITED (audit_lookahead below), not asserted in a comment.
    """
    left = pd.DataFrame({
        "_dk": _daykey(panel["date"]),
        "_bd": panel["board"].astype(str).to_numpy(),
    })
    right = pd.DataFrame({
        "_dk": _daykey(ser["date"]),
        "_bd": ser["board"].astype(str).to_numpy(),
        "i5_ma5": ser[REGIME_COL].to_numpy(dtype=np.float64),
        "i5_raw": ser[REGIME_RAW_COL].to_numpy(dtype=np.float64),
        "i5_pairs_n": ser["i5_pairs_n"].to_numpy(dtype=np.float64),
    })
    merged = left.merge(right, on=["_dk", "_bd"], how="left", validate="many_to_one")
    panel = panel.copy()
    panel["i5_ma5"] = merged["i5_ma5"].to_numpy()
    panel["i5_raw"] = merged["i5_raw"].to_numpy()
    panel["i5_pairs_n"] = merged["i5_pairs_n"].to_numpy()
    return panel


def audit_lookahead(panel: pd.DataFrame, ser: pd.DataFrame) -> dict:
    """MANDATORY LOOKAHEAD CHECK — four independent gates, all printed.

    i5(T) is computable at T's close BY CONSTRUCTION (it counts pairs whose TARGET bar is T),
    and its 5-session mean is a backward rolling window.  "By construction" is an argument, not
    evidence, so each leg is measured:

      G1  JOIN ALIGNMENT — the value landing on a row equals the series value at that row's
          OWN feature date T, for every sampled (board, T).
      G2  POWER — the check is not vacuous: i5(T) and i5(T+1) actually differ on a material
          share of sessions, so a T+1 join would have been detectable by G1.
      G3  BACKWARD WINDOW — ma5(T) equals the mean of the series' own i5 over the <=5 sessions
          ENDING at T, recomputed from the parquet's raw column.  A forward or centred window
          would fail here.
      G4  INDEPENDENT RECOMPUTE — i5(T) recomputed from THIS lane's panel (L2's exact
          definition: of the live limit-up bars with a usable next bar, the share whose next
          bar is also a limit-up, indexed on the TARGET date) matches the committed parquet.
          This gates both the join and the definition at once.
    """
    out = {"definition_note": (
        "i5_realized_continuation at date d = k/n over pairs whose NEXT USABLE BAR IS d and "
        "whose prior bar was a limit-up close.  Every input bar is at or before d, so the "
        "value is on the tape at d's close.  _ma5 is pandas .rolling(5, min_periods=3).mean() "
        "on the board's own session index — backward-looking and inclusive of d.")}

    sb = {str(b): g.sort_values("date").reset_index(drop=True)
          for b, g in ser.groupby("board", sort=True)}

    # one (board, day) -> joined value lookup, taken from the panel AS JOINED
    lk = pd.DataFrame({"bd": panel["board"].astype(str).to_numpy(),
                       "dk": _daykey(panel["date"]),
                       "v": panel["i5_ma5"].to_numpy(dtype=np.float64)}).drop_duplicates(
        subset=["bd", "dk"])
    joined = {(str(b), int(k)): float(v) for b, k, v in
              zip(lk["bd"].to_numpy(), lk["dk"].to_numpy(),
                  lk["v"].to_numpy(dtype=np.float64))}

    # G1 + G2 — deterministic sample: the last 60 sessions of each board's own series.
    g1_rows, g1_ok, g2_diff, g2_n = [], True, 0, 0
    g2_by_board = {}
    for b in sorted(sb):
        s = sb[b]
        vals = s[REGIME_COL].to_numpy(dtype=np.float64)
        dks = _daykey(s["date"])
        bd_n = bd_diff = 0
        for i in range(max(1, len(s) - 60), len(s) - 1):
            v_t, v_t1 = vals[i], vals[i + 1]
            g2_n += 1
            bd_n += 1
            if np.isfinite(v_t) and np.isfinite(v_t1) and abs(v_t - v_t1) > 1e-12:
                g2_diff += 1
                bd_diff += 1
            gv = joined.get((b, int(dks[i])))
            if gv is None:
                continue
            same = ((not np.isfinite(gv) and not np.isfinite(v_t))
                    or (np.isfinite(gv) and np.isfinite(v_t) and abs(gv - v_t) < 1e-12))
            if not same:
                g1_ok = False
            if len(g1_rows) < 6 and i >= len(s) - 3:
                g1_rows.append({
                    "board": b, "feature_date_T": s["date"].iloc[i].strftime("%Y-%m-%d"),
                    "series_i5_ma5_at_T": None if not np.isfinite(v_t) else round(float(v_t), 6),
                    "series_i5_ma5_at_T_plus_1": (None if not np.isfinite(v_t1)
                                                  else round(float(v_t1), 6)),
                    "value_joined_onto_panel_rows": (None if not np.isfinite(gv)
                                                     else round(float(gv), 6)),
                    "joined_equals_T": bool(same),
                })
        g2_by_board[b] = {
            "sessions_compared": bd_n,
            "sessions_where_T_and_T1_differ": bd_diff,
            "share_pct": round(100.0 * bd_diff / max(1, bd_n), 2),
            "verdict": ("HAS POWER" if bd_diff > 0.5 * max(1, bd_n) else
                        "WEAK — this board's dial repeats its own value too often for G1 to "
                        "reliably catch a one-session shift ON THIS BOARD"),
        }
    out["G1_join_alignment"] = {
        "gate": "the joined value equals the series value at the row's OWN feature date T",
        "sampled_board_sessions": g2_n,
        "all_match": bool(g1_ok),
        "worked_example_rows": g1_rows,
    }
    out["G2_check_has_power"] = {
        "gate": "i5(T) != i5(T+1) on a material share of sessions, so a T+1 join would show up",
        "sessions_compared": g2_n,
        "sessions_where_T_and_T1_differ": g2_diff,
        "share_pct": round(100.0 * g2_diff / max(1, g2_n), 2),
        "by_board": g2_by_board,
        "READ_PER_BOARD": (
            "The POOLED share understates G1's power on the board that matters and overstates "
            "it on the sparse ones.  main's dial moves nearly every session, so G1 is a strong "
            "test there; chinext and star print long runs of the SAME value (frequently 0.0) "
            "because their boards go days with no continuation pairs at all, so a one-session "
            "shift would often be invisible ON THOSE BOARDS.  G3 and G4 do not share that "
            "weakness — G3 pins the window's direction arithmetically and G4 re-derives the "
            "series from an independent panel — so the alignment is gated three ways, not one."),
        "verdict": ("HAS POWER" if g2_diff > 0.5 * max(1, g2_n) else
                    "POOLED SHARE BELOW 50% — read by_board; the sparse boards dilute it"),
    }

    # G3 — backward rolling window, recomputed from the parquet's own raw column.
    g3_bad, g3_checked, g3_rows = 0, 0, []
    for b in sorted(sb):
        s = sb[b]
        raw = s[REGIME_RAW_COL].to_numpy(dtype=np.float64)
        ma = s[REGIME_COL].to_numpy(dtype=np.float64)
        for i in range(max(0, len(s) - 200), len(s)):
            w = raw[max(0, i - 4):i + 1]
            w = w[np.isfinite(w)]
            exp = float(w.mean()) if w.size >= 3 else np.nan
            got = ma[i]
            g3_checked += 1
            ok = (not np.isfinite(exp) and not np.isfinite(got)) or (
                np.isfinite(exp) and np.isfinite(got) and abs(exp - got) < 1e-9)
            if not ok:
                g3_bad += 1
            if len(g3_rows) < 3 and np.isfinite(got):
                g3_rows.append({"board": b, "date": s.loc[i, "date"].strftime("%Y-%m-%d"),
                                "recomputed_backward_ma5": round(exp, 6),
                                "parquet_ma5": round(float(got), 6)})
    out["G3_backward_window"] = {
        "gate": "ma5(T) == mean of the series' own i5 over the <=5 sessions ENDING at T",
        "sessions_checked": g3_checked,
        "mismatches": g3_bad,
        "all_match": bool(g3_bad == 0),
        "worked_example_rows": g3_rows,
    }

    # G4 — independent recompute of i5 from this lane's own panel.
    pr = panel[panel["live"] & panel["limit_up"] & panel["y_ok"]
               & panel["next_bar_date"].notna()]
    rec = pr.groupby(["board", "next_bar_date"], observed=True)["y_limit_up"].agg(
        k="sum", n="size").reset_index()
    rec["_bd"] = rec["board"].astype(str)
    rec["_dk"] = _daykey(rec["next_bar_date"])
    rec["i5_recomputed"] = np.where(rec["n"] > 0, rec["k"] / rec["n"], np.nan)
    right = pd.DataFrame({"_bd": ser["board"].astype(str).to_numpy(),
                          "_dk": _daykey(ser["date"]),
                          "i5_parquet": ser[REGIME_RAW_COL].to_numpy(dtype=np.float64),
                          "n_parquet": ser["i5_pairs_n"].to_numpy(dtype=np.float64)})
    cmp = rec.merge(right, on=["_bd", "_dk"], how="inner")
    d = np.abs(cmp["i5_recomputed"].to_numpy(dtype=np.float64)
               - cmp["i5_parquet"].to_numpy(dtype=np.float64))
    dn = np.abs(cmp["n"].to_numpy(dtype=np.float64)
                - cmp["n_parquet"].to_numpy(dtype=np.float64))
    fin = np.isfinite(d)
    out["G4_independent_recompute"] = {
        "gate": ("i5(T) recomputed from THIS lane's panel using L2's exact definition matches "
                 "the committed parquet, on the (board, date) keys both carry"),
        "keys_compared": int(len(cmp)),
        "dates_with_a_finite_rate_on_both_sides": int(fin.sum()),
        "max_abs_rate_diff": (round(float(np.nanmax(d[fin])), 9) if bool(fin.any()) else None),
        "max_abs_pair_count_diff": (round(float(np.nanmax(dn)), 6) if len(dn) else None),
        "exact_matches": int((d[fin] < 1e-12).sum()) if bool(fin.any()) else 0,
        "all_match": bool(len(cmp) > 0 and bool(fin.any())
                          and float(np.nanmax(d[fin])) < 1e-9
                          and float(np.nanmax(dn)) < 1e-9),
        "why_it_matters": ("this gates the DEFINITION as well as the join — a drift between "
                           "L2's panel and L3's panel would show up here as a numeric gap, not "
                           "as a silent difference of meaning"),
    }
    out["verdict"] = ("PASS — no lookahead" if all(
        out[k].get("all_match") for k in
        ("G1_join_alignment", "G3_backward_window", "G4_independent_recompute"))
        else "SEE GATES — at least one leg did not match")
    return out


# ── STAGE 1 — splits (L3's, plus the pre-registered STAR era re-split) ────────

def make_splits_v2(panel: pd.DataFrame) -> tuple[dict, pd.Timestamp, dict]:
    """L3's splits verbatim for main and chinext; a STAR listing-era re-split added.

    L3's own make_splits is CALLED, not copied, and its main/chinext entries are asserted
    identical to what this function returns.  That is the gate that the STAR change did not
    perturb the two boards whose numbers must compose with L3's receipt.
    """
    splits, global_split = onset.make_splits(panel)
    l3_star = splits.get("star")

    usable = panel[panel["live"] & panel["y_ok"]]
    star = usable[usable["board"] == "star"]
    star_note = None
    if len(star):
        bdates = np.sort(star["date"].unique())
        era_start = pd.Timestamp(bdates[0])
        si = int(len(bdates) * onset.FIT_FRACTION)
        sd = pd.Timestamp(bdates[si])
        fit_dates = bdates[bdates < sd]
        ci = int(len(fit_dates) * (1.0 - onset.CALIB_FRACTION))
        calib_start = pd.Timestamp(fit_dates[ci]) if len(fit_dates) else sd
        splits["star"] = {
            "split_rule": "star_listing_era",
            "era_start": era_start.strftime("%Y-%m-%d"),
            "fit_core": [era_start.strftime("%Y-%m-%d"),
                         (calib_start - pd.Timedelta(days=1)).strftime("%Y-%m-%d")],
            "fit_calib": [calib_start.strftime("%Y-%m-%d"),
                          (sd - pd.Timedelta(days=1)).strftime("%Y-%m-%d")],
            "holdout": [sd.strftime("%Y-%m-%d"), pd.Timestamp(bdates[-1]).strftime("%Y-%m-%d")],
            "split_date": sd.strftime("%Y-%m-%d"),
            "calib_start": calib_start.strftime("%Y-%m-%d"),
            "n_fit_dates": int(si),
            "n_holdout_dates": int(len(bdates) - si),
            "why": ("PRE-REGISTERED WAVE-2 CHANGE (L3 ORE row #3, authorised before any number "
                    "here was computed).  STAR listed 2019-07-29, so v0's GLOBAL 70/30 date "
                    "split gives it a 33/67 fit/holdout split and starves the fit side.  This "
                    "is the identical mechanism ChiNext already gets — the board's own era, "
                    "re-split 70/30 inside it.  L3's global-split gate is carried alongside."),
        }
        star_note = {
            "l3_global_split": l3_star,
            "v2_era_split": splits["star"],
            "discipline": ("L3 refused to re-split AFTER watching its THIN gate fail — the "
                           "correct call.  The re-split is admitted here only because it was "
                           "written down before Wave 2's first run, and it is applied to STAR "
                           "alone: main and chinext keep L3's boundaries byte-for-byte."),
        }
    return splits, global_split, {"star_resplit": star_note}


# ── STAGE 2 — regime strata (edges from the FIT window only) ──────────────────

def stratum_edges(ser_board: pd.DataFrame, fit_dates: np.ndarray, n_cuts: int) -> list[float]:
    """Quantile edges of the regime dial over the board's own FIT-WINDOW SESSIONS.

    Quantiled on DATES, not on rows — L2's convention.  A row-weighted quantile would let a
    board's cross-sectional size decide where "hot" starts, which is not what the dial means.
    Edges are computed on the fit window ONLY and applied unchanged to the holdout, so a
    holdout row's stratum label carries the same meaning as a fit row's.
    """
    dk = set(_daykey(pd.Series(fit_dates)).tolist())
    m = np.isin(_daykey(ser_board["date"]), sorted(dk))
    v = ser_board.loc[m, REGIME_COL].to_numpy(dtype=np.float64)
    v = v[np.isfinite(v)]
    if v.size < 30:
        return []
    qs = np.linspace(0.0, 1.0, n_cuts + 1)[1:-1]
    return [float(x) for x in np.unique(np.quantile(v, qs))]


def assign_stratum(vals: np.ndarray, edges: list[float]) -> np.ndarray:
    out = np.full(vals.shape, UNKNOWN_STRATUM, dtype=np.int16)
    fin = np.isfinite(vals)
    if edges:
        out[fin] = np.searchsorted(np.asarray(edges, dtype=np.float64),
                                   vals[fin], side="right").astype(np.int16)
    else:
        out[fin] = 0
    return out


def strata_for_board(panel: pd.DataFrame, ser: pd.DataFrame, board: str,
                     splits: dict) -> dict:
    """Pre-registered collapse ladder, decided on FIT-SIDE COUNTS ONLY.

    1. terciles + an UNKNOWN stratum for sessions where the board printed no continuation rate
    2. if ANY tercile carries fewer than MIN_STRATUM_CALIB_POS positives in the fit CALIBRATION
       slice, collapse to HALVES and print it
    3. a stratum still under the floor after that falls back to the POOLED isotonic map and is
       printed as a fallback, never fitted at a lower standard

    The UNKNOWN stratum is NOT a missing-data hole to be patched.  A board prints no
    continuation rate on a session precisely when no name was carrying a board into it — the
    absence IS the cold state.  It is therefore carried as its own stratum with its own map,
    and its share of every slice is printed.
    """
    s = splits[board]
    era_start = pd.Timestamp(s["era_start"])
    sd = pd.Timestamp(s["split_date"])
    cs = pd.Timestamp(s["calib_start"])
    sb = ser[ser["board"].astype(str) == board].sort_values("date").reset_index(drop=True)

    m = ((panel["board"] == board) & (panel["date"] >= era_start)
         & panel["live"] & panel["y_ok"] & panel["complete_case"])
    sub = panel[m]
    fit_dates = np.sort(sub.loc[sub["date"] < sd, "date"].unique())
    calib_mask = (sub["date"] >= cs) & (sub["date"] < sd)

    # DIAL SHAPE — measured before any cut, because a quantile cut on a variable with a large
    # point mass silently produces empty strata whose LABELS then lie.
    dk = set(_daykey(pd.Series(fit_dates)).tolist())
    fitm = np.isin(_daykey(sb["date"]), sorted(dk))
    fv = sb.loc[fitm, REGIME_COL].to_numpy(dtype=np.float64)
    n_fit = int(fv.size)
    n_null = int((~np.isfinite(fv)).sum())
    n_zero = int(np.sum(np.isfinite(fv) & (fv <= 0.0)))
    info = {"board": board, "regime_variable": REGIME_COL,
            "edge_source": ("quantiles of the dial over the board's OWN fit-window sessions "
                            "(dates, not rows); applied unchanged to the holdout"),
            "fit_sessions_used_for_edges": int(len(fit_dates)),
            "dial_shape_on_fit_sessions": {
                "sessions": n_fit,
                "no_print_null_sessions": n_null,
                "no_print_null_pct": round(100.0 * n_null / max(1, n_fit), 2),
                "sessions_at_exactly_zero": n_zero,
                "sessions_at_exactly_zero_pct": round(100.0 * n_zero / max(1, n_fit), 2),
                "point_mass_warning": (
                    "A quantile cut cannot separate a point mass.  When more than 1/n_cuts of "
                    "the fit sessions sit at exactly 0.0, the lowest edge LANDS ON ZERO and the "
                    "bottom stratum comes out EMPTY — every zero session sorts to the stratum "
                    "above it.  The surviving stratum then carries a 'hot' label it has not "
                    "earned, and the real contrast collapses to printed-a-rate vs no-pairs.  "
                    "Read occupancy_pct below before reading any stratum label."),
            }}

    scheme, n_cuts = "terciles", N_STRATA
    edges = stratum_edges(sb, fit_dates, n_cuts)
    strat = assign_stratum(sub["i5_ma5"].to_numpy(dtype=np.float64), edges)
    y = sub["y_limit_up"].to_numpy(dtype=np.float64)
    cm = calib_mask.to_numpy()

    def calib_pos(st_arr: np.ndarray) -> dict[int, int]:
        return {int(k): int(y[cm & (st_arr == k)].sum()) for k in sorted(set(st_arr.tolist()))}

    pos3 = calib_pos(strat)
    info["terciles"] = {"edges": edges,
                        "fit_calib_positives_by_stratum": {
                            STRATUM_LABELS_3.get(k, str(k)): v for k, v in pos3.items()}}
    thin = [k for k in (0, 1, 2) if pos3.get(k, 0) < MIN_STRATUM_CALIB_POS]
    if thin:
        scheme, n_cuts = "halves", 2
        edges = stratum_edges(sb, fit_dates, n_cuts)
        strat = assign_stratum(sub["i5_ma5"].to_numpy(dtype=np.float64), edges)
        info["collapsed_to_halves"] = {
            "trigger": [STRATUM_LABELS_3.get(k, str(k)) for k in thin],
            "floor": MIN_STRATUM_CALIB_POS,
            "note": ("PRE-REGISTERED collapse.  Decided on FIT-CALIBRATION positive counts "
                     "only; the holdout was not consulted."),
        }
    labels = STRATUM_LABELS_3 if scheme == "terciles" else STRATUM_LABELS_2
    info["scheme"] = scheme
    info["edges_applied"] = edges
    info["labels"] = {str(k): v for k, v in labels.items()}
    info["fit_calib_positives_by_stratum_applied"] = {
        labels.get(k, str(k)): v for k, v in calib_pos(strat).items()}

    occ, tot = {}, max(1, int(np.sum(strat != UNKNOWN_STRATUM)))
    for k in sorted(labels):
        if k == UNKNOWN_STRATUM:
            continue
        occ[labels[k]] = round(100.0 * float(np.sum(strat == k)) / tot, 3)
    biggest = max(occ.values()) if occ else 100.0
    info["occupancy_pct_of_non_unknown_rows"] = occ
    info["dial_is_degenerate"] = bool(biggest >= 99.0)
    info["degeneracy_reading"] = (
        ("DEGENERATE — one stratum holds >=99% of this board's rows with a regime print, so "
         "the dial is not ordering anything here.  The only contrast this board actually "
         "supplies is PRINTED-A-RATE vs NO-PAIRS, and the surviving stratum's 'hot'/'mid' "
         "label is a naming artifact of a quantile cut landing on a point mass, NOT a "
         "statement that the board is hot.  Every regime result on this board must be read as "
         "a coverage null." ) if biggest >= 99.0 else
        "The dial separates this board's rows into occupied strata; labels are meaningful.")

    col = pd.Series(UNKNOWN_STRATUM, index=panel.index, dtype=np.int16)
    col.loc[sub.index] = strat
    return {"info": info, "stratum": col, "labels": labels, "edges": edges,
            "scheme": scheme, "index": sub.index}


def stratum_share_table(sl: dict, scol: str, labels: dict) -> tuple[list[dict], dict]:
    """Base rate per stratum in EACH slice, plus a machine-stated direction verdict.

    This is the diagnosis table for R2.  A per-stratum calibration map can only correct a
    level error if the dial orders the outcome the SAME WAY in the calibration slice as it
    does in the holdout.  If the ordering differs between those two slices, the maps carry the
    calibration window's ordering into a holdout that does not share it, and conditioning makes
    the level error LARGER.  The verdict is computed rather than argued.
    """
    rows, direction = [], {}
    for name in ("fit_core", "fit_calib", "holdout"):
        g = sl[name]
        n = max(1, len(g))
        seq = []
        for st in sorted(set(g[scol].tolist())):
            m = g[scol] == st
            k = int(g.loc[m, "y_limit_up"].sum())
            nn = int(m.sum())
            ci = onset.wilson(k, nn)
            rate = (k / nn) if nn else None
            rows.append({
                "slice": name, "stratum": labels.get(int(st), str(int(st))),
                "rows": nn, "share_pct": round(100.0 * nn / n, 3),
                "positives": k,
                "base_rate_pct": round(100.0 * rate, 4) if rate is not None else None,
                "wilson95_pct": ([round(100.0 * ci[0], 4), round(100.0 * ci[1], 4)]
                                 if ci else None),
            })
            if int(st) != UNKNOWN_STRATUM and rate is not None:
                seq.append((int(st), rate))
        seq.sort()
        vals = [v for _, v in seq]
        if len(vals) < 2:
            direction[name] = {"ordered_strata": len(vals), "verdict": "DEGENERATE — one "
                               "non-UNKNOWN stratum only; the dial cannot order this slice"}
        else:
            up = all(vals[i] < vals[i + 1] for i in range(len(vals) - 1))
            dn = all(vals[i] > vals[i + 1] for i in range(len(vals) - 1))
            direction[name] = {
                "ordered_strata": len(vals),
                "base_rates_cold_to_hot_pct": [round(100.0 * v, 4) for v in vals],
                "top_over_bottom_x": (round(vals[-1] / vals[0], 3) if vals[0] > 0 else None),
                "verdict": ("MONOTONE POSITIVE (hotter tape -> higher onset rate)" if up else
                            "MONOTONE INVERTED (hotter tape -> LOWER onset rate)" if dn else
                            "NON-MONOTONE"),
            }
    return rows, direction


# ── STAGE 3 — models ──────────────────────────────────────────────────────────

def fit_r0(fit_all: pd.DataFrame, scol: str, labels: dict) -> dict:
    """REGIME-LADDER: fit-window base rate per (连板 N x regime stratum) cell.

    Fitted on the WHOLE fit window, exactly as B0 is, so the new benchmark gets at least as
    much data as any model it is compared against.  A cell thinner than L3's THIN_CELL_N falls
    back to that N's marginal rate — which IS B0 — so R0 degrades toward the old benchmark
    rather than toward noise.  No shrinkage, no smoothing: this is a lookup table and it is
    supposed to be readable as one.
    """
    base = float(fit_all["y_limit_up"].mean())
    nmarg = fit_all.groupby("N_bucket", observed=True)["y_limit_up"].mean().to_dict()
    g = fit_all.groupby(["N_bucket", scol], observed=True)["y_limit_up"].agg(["size", "sum"])
    cells = {}
    for (nb, st), row in g.iterrows():
        n, k = int(row["size"]), int(row["sum"])
        thin = n < onset.THIN_CELL_N
        p = float(nmarg.get(nb, base)) if thin else k / n
        ci = onset.wilson(k, n)
        cells[f"{int(nb)}|{int(st)}"] = {
            "N_label": f"{onset.N_CAP}+" if int(nb) == onset.N_CAP else str(int(nb)),
            "stratum": labels.get(int(st), str(int(st))),
            "n": n, "k": k, "p": p,
            "rate_pct": round(100.0 * k / n, 4) if n else None,
            "wilson95_pct": ([round(100.0 * ci[0], 4), round(100.0 * ci[1], 4)] if ci else None),
            "thin": bool(thin),
            "used": round(100.0 * p, 4),
        }
    return {"cells": cells, "n_marginal": {int(k): float(v) for k, v in nmarg.items()},
            "fallback_p": base, "n_cells": len(cells),
            "n_cells_thin": int(sum(1 for v in cells.values() if v["thin"])),
            "fit_rows": len(fit_all), "fit_positives": int(fit_all["y_limit_up"].sum())}


def apply_r0(df: pd.DataFrame, model: dict, scol: str) -> np.ndarray:
    """Vectorised lookup.  An (N, stratum) pair unseen in the fit window falls back to that N's
    marginal rate — i.e. to B0 — and, failing that, to the fit-window base rate."""
    nb = df["N_bucket"].to_numpy()
    st = df[scol].to_numpy()
    nm, fb = model["n_marginal"], model["fallback_p"]
    out = np.full(len(df), fb, dtype=np.float64)
    for k, v in nm.items():
        out[nb == int(k)] = float(v)
    keys = pd.Series(nb.astype(str)).str.cat(pd.Series(st.astype(str)), sep="|")
    lut = pd.Series({k: v["p"] for k, v in model["cells"].items()}, dtype="float64")
    hit = keys.map(lut).to_numpy(dtype=np.float64)
    m = np.isfinite(hit)
    out[m] = hit[m]
    return out


def add_regime_covariates(panel: pd.DataFrame, board: str, splits: dict,
                          index: pd.Index) -> dict:
    """i5_ma5_z (winsorised + standardised on the FIT CORE only) + a missing indicator.

    WHY A MISSING INDICATOR AND NOT COMPLETE-CASE: dropping rows without a regime print would
    change the holdout ROW SET, and every number in this receipt is designed to compose with
    L3's on the identical rows.  A dropped-row model would be measuring a different holdout and
    calling it a comparison.  The indicator keeps the row set byte-identical to B1's while
    letting the logistic price the no-print state explicitly rather than pretending it is
    average.  Nulls take z = 0 (the fit-core mean) BY CONSTRUCTION, never an imputed guess.
    """
    s = splits[board]
    cs = pd.Timestamp(s["calib_start"])
    era_start = pd.Timestamp(s["era_start"])
    core = panel.loc[index]
    core = core[(core["date"] >= era_start) & (core["date"] < cs)]
    v = core["i5_ma5"].to_numpy(dtype=np.float64)
    v = v[np.isfinite(v)]
    if v.size < 100:
        lo, hi, mu, sd = 0.0, 1.0, 0.0, 1.0
    else:
        lo, hi = float(np.quantile(v, onset.WINSOR_Q[0])), float(np.quantile(v, onset.WINSOR_Q[1]))
        w = np.clip(v, lo, hi)
        mu, sd = float(w.mean()), float(w.std(ddof=0))
        if not (sd > 0):
            sd = 1.0
    return {"winsor_lo": lo, "winsor_hi": hi, "mean": mu, "std": sd,
            "fit_core_non_null": int(v.size),
            "note": ("winsorisation quantiles and standardisation moments come from the FIT "
                     "CORE only — the same leakage guard L3 applies to its six features")}


def fit_stratified_isotonic(model: dict, fit_calib: pd.DataFrame, scol: str,
                            pooled: onset.Isotonic, labels: dict) -> tuple[dict, dict]:
    """One isotonic map per regime stratum, fitted on that stratum's share of the FIT
    CALIBRATION slice.  The holdout is never touched by any of them.

    This is the causal fix in one function: B1's frozen map inherits the base rate of the
    slice it saw, so a holdout that runs at a different temperature is quoted in the wrong
    regime's currency.  Fitting a map per stratum means a cold holdout row is priced by the
    cold calibration rows and a hot one by the hot rows.
    """
    raw = onset.apply_b1(fit_calib, model, raw=True)
    y = fit_calib["y_limit_up"].to_numpy(dtype=np.float64)
    st = fit_calib[scol].to_numpy()
    maps, rec = {}, []
    for k in sorted(set(st.tolist())):
        m = st == k
        n, kk = int(m.sum()), int(y[m].sum())
        if kk < MIN_STRATUM_CALIB_POS:
            maps[int(k)] = pooled
            rec.append({"stratum": labels.get(int(k), str(int(k))), "calib_rows": n,
                        "calib_positives": kk, "map": "POOLED FALLBACK",
                        "why": (f"fewer than {MIN_STRATUM_CALIB_POS} positives in this "
                                "stratum's calibration slice — an isotonic fitted there would "
                                "be a step function of noise, so the pooled map is used and "
                                "the fallback is printed")})
            continue
        iso = onset.Isotonic(raw[m], y[m])
        maps[int(k)] = iso
        rec.append({"stratum": labels.get(int(k), str(int(k))), "calib_rows": n,
                    "calib_positives": kk, "map": "own isotonic",
                    "isotonic_knots": int(iso.knots),
                    "calib_base_rate_pct": round(100.0 * kk / max(1, n), 4)})
    return maps, {"per_stratum": rec,
                  "floor_positives": MIN_STRATUM_CALIB_POS,
                  "n_own_maps": int(sum(1 for r in rec if r["map"] == "own isotonic")),
                  "n_pooled_fallback": int(sum(1 for r in rec if r["map"] != "own isotonic"))}


def apply_stratified(df: pd.DataFrame, model: dict, maps: dict, scol: str,
                     pooled: onset.Isotonic) -> np.ndarray:
    raw = onset.apply_b1(df, model, raw=True)
    st = df[scol].to_numpy()
    out = np.empty(len(raw), dtype=np.float64)
    seen = np.zeros(len(raw), dtype=bool)
    for k, iso in maps.items():
        m = st == k
        if not bool(m.any()):
            continue
        out[m] = iso.predict(raw[m])
        seen |= m
    if bool((~seen).any()):
        out[~seen] = pooled.predict(raw[~seen])
    return out


# ── STAGE 4 — metrics ─────────────────────────────────────────────────────────

def head_metrics(y: np.ndarray, p: np.ndarray, benches: dict) -> dict:
    bs, ll = onset.brier(y, p), onset.logloss(y, p)
    a = onset.auc(y, p)
    rec = {
        "brier_x1000": round(1000.0 * bs, 6),
        "log_loss": round(ll, 6),
        "auc": round(a, 5) if a is not None else None,
        "mean_p_hat_pct": round(100.0 * float(p.mean()), 4),
        "realized_base_pct": round(100.0 * float(y.mean()), 4),
        "mean_p_over_realized": (round(float(p.mean()) / float(y.mean()), 4)
                                 if float(y.mean()) > 0 else None),
        "murphy": onset.murphy(y, p),
    }
    for nm, pb in benches.items():
        b_bs, b_ll = onset.brier(y, pb), onset.logloss(y, pb)
        rec[f"brier_skill_vs_{nm}_pct"] = (round(100.0 * (1.0 - bs / b_bs), 4)
                                           if b_bs > 0 else None)
        rec[f"log_loss_skill_vs_{nm}_pct"] = (round(100.0 * (1.0 - ll / b_ll), 4)
                                              if b_ll > 0 else None)
    return rec


def head_of_book(y: np.ndarray, p: np.ndarray, frac: float = TOP_FRACTION) -> dict:
    """The named ChiNext defect lives here: L3's B1 over-predicts by 2.58x and its top bin
    predicts 8.586% against a realized 1.535%.  This measures exactly that region, plus the
    isotonic head-tie L3 §12 flagged (six main-board names all priced at the map's last block).
    """
    n = len(y)
    k = max(1, int(round(n * frac)))
    idx = np.argsort(-p, kind="stable")[:k]
    mp, rr = float(p[idx].mean()), float(y[idx].mean())
    pmax = float(p.max())
    top = np.unique(p[idx])
    return {
        "top_fraction": frac,
        "rows": int(k),
        "mean_p_hat_pct": round(100.0 * mp, 4),
        "realized_pct": round(100.0 * rr, 4),
        "over_prediction_ratio_p_over_realized": (round(mp / rr, 4) if rr > 0 else None),
        "distinct_p_values_in_top_decile": int(top.size),
        "max_p_hat_pct": round(100.0 * pmax, 4),
        "rows_tied_at_max": int(np.sum(p >= pmax - 1e-15)),
        "realized_at_max_tie_pct": round(100.0 * float(y[p >= pmax - 1e-15].mean()), 4),
        "distinct_p_values_overall": int(np.unique(p).size),
    }


def ladder_x_regime(hold: pd.DataFrame, scol: str, labels: dict) -> list[dict]:
    """HOLDOUT realized rate in every (连板 N x regime stratum) cell — descriptive only.

    Nothing is fitted, selected or tuned from this table; it is the pre-registered ladder
    crossed with the pre-registered strata on the pre-registered holdout, printed because it
    is the direct evidence for where the dial does and does not carry information.  The row
    share column is load-bearing: a dial that works only on the ladder rungs is invisible to
    any model whose rows are ~99% N=0.
    """
    rows = []
    tot = max(1, len(hold))
    for nb, g in hold.groupby("N_bucket", observed=True):
        seq = []
        for stv in sorted(set(g[scol].tolist())):
            m = g[scol] == stv
            n, k = int(m.sum()), int(g.loc[m, "y_limit_up"].sum())
            ci = onset.wilson(k, n)
            rows.append({
                "N_label": f"{onset.N_CAP}+" if int(nb) == onset.N_CAP else str(int(nb)),
                "stratum": labels.get(int(stv), str(int(stv))),
                "rows": n, "row_share_of_holdout_pct": round(100.0 * n / tot, 4),
                "positives": k,
                "realized_pct": round(100.0 * k / n, 4) if n else None,
                "wilson95_pct": ([round(100.0 * ci[0], 4), round(100.0 * ci[1], 4)]
                                 if ci else None),
                "thin": bool(n < onset.THIN_CELL_N),
            })
            if int(stv) != UNKNOWN_STRATUM and n >= onset.THIN_CELL_N:
                seq.append((int(stv), k / n if n else 0.0))
        seq.sort()
        v = [x for _, x in seq]
        if len(v) >= 2:
            up = all(v[i] < v[i + 1] for i in range(len(v) - 1))
            rows[-1]["_rung_summary"] = {
                "N_label": rows[-1]["N_label"],
                "cold_to_hot_pct": [round(100.0 * x, 4) for x in v],
                "top_over_bottom_x": round(v[-1] / v[0], 3) if v[0] > 0 else None,
                "monotone_positive": bool(up),
            }
    return rows


def per_year_skill(hold: pd.DataFrame, preds: dict, names: list[str], bench: str) -> list[dict]:
    rows = []
    for yr, g in hold.groupby("year", observed=True):
        m = g.index.to_numpy()
        yv = g["y_limit_up"].to_numpy(dtype=np.float64)
        bs_b = onset.brier(yv, preds[bench][m])
        rec = {"year": int(yr), "n": len(g), "positives": int(yv.sum()),
               "base_pct": round(100.0 * float(yv.mean()), 4),
               f"{bench.lower()}_brier_x1000": round(1000.0 * bs_b, 6)}
        for k in names:
            bs = onset.brier(yv, preds[k][m])
            rec[f"{k.lower()}_skill_pct"] = (round(100.0 * (1.0 - bs / bs_b), 4)
                                             if bs_b > 0 else None)
        rows.append(rec)
    rows.sort(key=lambda r: r["year"])
    return rows


def parity_check(board: str, hold_rows: int, base_pct: float, b1: dict, b0: dict,
                 topk: list[dict]) -> dict | None:
    tgt = L3_PARITY_TARGETS.get(board)
    if tgt is None:
        return None
    got = {
        "holdout_rows": hold_rows,
        "holdout_base_rate_pct": round(base_pct, 3),
        "b1_brier_skill_vs_b0_pct": (round(b1["brier_skill_vs_B0_pct"], 2)
                                     if b1.get("brier_skill_vs_B0_pct") is not None else None),
        "b1_auc": round(b1["auc"], 3) if b1.get("auc") is not None else None,
        "b0_auc": round(b0["auc"], 3) if b0.get("auc") is not None else None,
        "b1_mean_p_over_realized": (round(b1["mean_p_over_realized"], 2)
                                    if b1.get("mean_p_over_realized") is not None else None),
    }
    t20 = [r for r in topk if r["ranker"] == "B1" and r["K"] == 20]
    if t20:
        got["b1_top20_realized_pct"] = round(t20[0]["realized_rate_pct"], 3)
    checks = {}
    for k, want in tgt.items():
        have = got.get(k)
        if have is None:
            checks[k] = {"l3_published": want, "recomputed": None, "match": False}
            continue
        tol = (PARITY_TOL["auc"] if k.endswith("auc") else
               PARITY_TOL["rate"] if "base_rate" in k else
               PARITY_TOL["ratio"] if "over_realized" in k else
               0 if k == "holdout_rows" else PARITY_TOL["pct"])
        ok = (have == want) if k == "holdout_rows" else bool(abs(have - want) <= tol)
        checks[k] = {"l3_published": want, "recomputed": have, "tolerance": tol, "match": ok}
    return {"checks": checks, "all_match": bool(all(c["match"] for c in checks.values())),
            "purpose": ("this lane re-derives B0/B1 by CALLING L3's own code on the same store; "
                        "these are L3's published numbers vs this run's.  A mismatch would mean "
                        "the two receipts do not compose and every skill number below would be "
                        "comparing different objects.")}


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> int:  # noqa: C901 - one linear instrument, deliberately readable top-to-bottom
    t0 = time.time()
    stamped = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    print(f"[regime_cal_v2] sklearn={'yes' if onset.SKLEARN else 'NO — fallback'}", flush=True)

    print("[0] regime series ...", flush=True)
    ser, ser_meta = load_regime_series()

    print("[A] building panel (L3's builder, imported) ...", flush=True)
    panel, panel_meta = onset.build_panel()
    print(f"    {len(panel):,} rows / {panel['ticker'].nunique()} names "
          f"/ {time.time() - t0:.1f}s", flush=True)

    panel = join_regime(panel, ser)
    print("[0b] lookahead audit ...", flush=True)
    look = audit_lookahead(panel, ser)
    print(f"    {look['verdict']}", flush=True)

    print("[B] splits ...", flush=True)
    splits, _global_split, split_notes = make_splits_v2(panel)

    print("[C/D] fitting + evaluating per board ...", flush=True)
    by_board = {}
    max_date = pd.Timestamp(panel["date"].max())

    for board in sorted(panel["board"].unique()):
        if board not in splits or board not in BOARD_SPLIT_RULE_V2:
            continue
        # The three regime columns are rewritten per board and only ever read through
        # slice_board, which filters to that board — no cross-board leakage is possible, and
        # this avoids copying a 4.9M-row panel once per board.
        st = strata_for_board(panel, ser, board, splits)
        panel["regime_stratum"] = st["stratum"].to_numpy()
        cov = add_regime_covariates(panel, board, splits, st["index"])
        v = panel["i5_ma5"].to_numpy(dtype=np.float64)
        z = (np.clip(v, cov["winsor_lo"], cov["winsor_hi"]) - cov["mean"]) / cov["std"]
        panel["i5_ma5_z"] = np.where(np.isfinite(z), z, 0.0)
        panel["i5_is_null"] = (~np.isfinite(v)).astype(np.float64)

        sl = onset.slice_board(panel, board, splits)
        gate = {
            "fit_core_rows": len(sl["fit_core"]),
            "fit_core_positives": int(sl["fit_core"]["y_limit_up"].sum()),
            "fit_calib_rows": len(sl["fit_calib"]),
            "fit_calib_positives": int(sl["fit_calib"]["y_limit_up"].sum()),
            "holdout_rows": len(sl["holdout"]),
            "holdout_positives": int(sl["holdout"]["y_limit_up"].sum()),
            "floors": {"fit_core_positives": onset.MIN_FIT_CORE_POS,
                       "fit_calib_positives": onset.MIN_CALIB_POS,
                       "holdout_positives": onset.MIN_HOLDOUT_POS},
        }
        gate["passes"] = bool(
            gate["fit_core_positives"] >= onset.MIN_FIT_CORE_POS
            and gate["fit_calib_positives"] >= onset.MIN_CALIB_POS
            and gate["holdout_positives"] >= onset.MIN_HOLDOUT_POS)

        srb = {}
        for nm in ("fit_core", "fit_calib", "holdout"):
            g = sl[nm]
            srb[nm] = {"rows": len(g), "positives": int(g["y_limit_up"].sum()),
                       "base_rate_pct": (round(100.0 * float(g["y_limit_up"].mean()), 4)
                                         if len(g) else None)}
        if srb["holdout"]["base_rate_pct"]:
            srb["calib_over_holdout_x"] = round(
                srb["fit_calib"]["base_rate_pct"] / srb["holdout"]["base_rate_pct"], 3)
            srb["fit_core_over_holdout_x"] = round(
                srb["fit_core"]["base_rate_pct"] / srb["holdout"]["base_rate_pct"], 3)
        srb["reading"] = ("THE DEFECT THIS LANE EXISTS TO FIX.  calib_over_holdout_x is the "
                          "level error a frozen pooled calibration map carries before a single "
                          "feature is considered.")

        entry = {"split": splits[board], "split_rule_v2": BOARD_SPLIT_RULE_V2[board],
                 "thin_gate": gate, "slice_base_rates": srb, "regime_strata": st["info"]}
        if not gate["passes"]:
            entry["status"] = "THIN-SKIP — not modelled"
            entry["reason"] = ("Pre-registered events-per-variable floor not met.  Printed as a "
                               "measured null, never silently downgraded to a smaller model.")
            by_board[board] = entry
            print(f"    {board}: THIN-SKIP (fit-core positives "
                  f"{gate['fit_core_positives']} < {onset.MIN_FIT_CORE_POS})", flush=True)
            continue

        labels = st["labels"]
        shares, direction = stratum_share_table(sl, "regime_stratum", labels)
        entry["regime_strata"]["slice_shares"] = shares
        entry["regime_strata"]["direction_by_slice"] = direction
        entry["regime_strata"]["r2_precondition"] = {
            "gate": ("R2 can only correct a level error if the dial orders the outcome the SAME "
                     "way in the FIT CALIBRATION slice as in the HOLDOUT"),
            "fit_calib_verdict": direction["fit_calib"]["verdict"],
            "holdout_verdict": direction["holdout"]["verdict"],
            "precondition_met": bool(
                direction["fit_calib"].get("verdict") == direction["holdout"].get("verdict")
                and "MONOTONE" in str(direction["fit_calib"].get("verdict"))),
        }

        b0 = onset.fit_b0(sl["fit_all"])
        b1 = onset.fit_b1(sl, onset.DESIGN_COLS, "B1 (L3) six features + N dummies")
        # B2 and P2 are L3's OWN published models, re-derived here UNCHANGED and REPORTED ONLY.
        # They are not this lane's work and nothing here was built on top of them.  They are
        # included because L3 measured B2 at +0.32% and P2 at +0.71% Brier skill on this exact
        # holdout, so a Wave-2 receipt that omitted them would present R0's win as the
        # program's best when it is not.  Reporting them is a completeness act, not a search:
        # no Wave-2 model was refitted, retuned or reselected in response to them.
        b2 = onset.fit_b2(sl)
        p2 = onset.fit_b1(sl, ["f3_runup_5"] + onset.N_DUMMIES, "P2 (L3) f3 + N dummies")
        r0 = fit_r0(sl["fit_all"], "regime_stratum", labels)
        r1 = onset.fit_b1(sl, R1_COLS, "R1 = B1 + i5 covariate + missing indicator")
        maps2, rec2 = fit_stratified_isotonic(b1, sl["fit_calib"], "regime_stratum",
                                              b1["_iso"], labels)
        maps3, rec3 = fit_stratified_isotonic(r1, sl["fit_calib"], "regime_stratum",
                                              r1["_iso"], labels)

        hold = sl["holdout"].reset_index(drop=True)
        yv = hold["y_limit_up"].to_numpy(dtype=np.float64)
        preds = {
            "B0": onset.apply_b0(hold, b0),
            "B1": onset.apply_b1(hold, b1),
            "B2": onset.apply_b2(hold, b2),
            "P2": onset.apply_b1(hold, p2),
            "R0": apply_r0(hold, r0, "regime_stratum"),
            "R1": onset.apply_b1(hold, r1),
            "R2": apply_stratified(hold, b1, maps2, "regime_stratum", b1["_iso"]),
            "R3": apply_stratified(hold, r1, maps3, "regime_stratum", r1["_iso"]),
        }
        names = ["B0", "B1", "B2", "P2", "R0", "R1", "R2", "R3"]
        wave2 = ["R0", "R1", "R2", "R3"]
        benches = {"B0": preds["B0"], "R0": preds["R0"]}

        entry["status"] = "modelled"
        entry["models"] = {
            "B0": {k: v for k, v in b0.items() if not k.startswith("_")},
            "B1": {k: v for k, v in b1.items() if not k.startswith("_")},
            "B2_reported_only_L3": {k: v for k, v in b2.items() if not k.startswith("_")},
            "P2_reported_only_L3": {k: v for k, v in p2.items() if not k.startswith("_")},
            "R0": {k: v for k, v in r0.items() if not k.startswith("_")},
            "R1": {k: v for k, v in r1.items() if not k.startswith("_")},
            "R1_covariate_scaling": cov,
            "R2_calibration": rec2,
            "R3_calibration": rec3,
        }
        topk = onset.top_k_table(hold, preds, names)
        entry["holdout"] = {
            "rows": len(hold), "positives": int(yv.sum()),
            "base_rate_pct": round(100.0 * float(yv.mean()), 4),
            "dates": int(hold["date"].nunique()),
            "headline": {k: head_metrics(yv, preds[k], benches) for k in names},
            "head_of_book": {k: head_of_book(yv, preds[k]) for k in names},
            "reliability": {k: onset.reliability(yv, preds[k]) for k in names},
            "per_year_skill_vs_B0": per_year_skill(hold, preds, names, "B0"),
            "per_year_skill_vs_R0": per_year_skill(hold, preds, names, "R0"),
            "top_k": topk,
            "ladder_x_regime": ladder_x_regime(hold, "regime_stratum", labels),
            "by_stratum": [],
        }
        for stv in sorted(set(hold["regime_stratum"].tolist())):
            m = (hold["regime_stratum"] == stv).to_numpy()
            if int(m.sum()) < onset.THIN_CELL_N:
                continue
            row = {"stratum": labels.get(int(stv), str(int(stv))), "rows": int(m.sum()),
                   "positives": int(yv[m].sum()),
                   "base_rate_pct": round(100.0 * float(yv[m].mean()), 4)}
            for k in names:
                row[f"{k}_mean_p_pct"] = round(100.0 * float(preds[k][m].mean()), 4)
                row[f"{k}_p_over_realized"] = (
                    round(float(preds[k][m].mean()) / float(yv[m].mean()), 3)
                    if float(yv[m].mean()) > 0 else None)
            entry["holdout"]["by_stratum"].append(row)

        entry["l3_parity_gate"] = parity_check(
            board, len(hold), 100.0 * float(yv.mean()),
            entry["holdout"]["headline"]["B1"], entry["holdout"]["headline"]["B0"], topk)

        hl = entry["holdout"]["headline"]

        def _best(pool: list[str], key: str, table: dict = hl) -> str:
            # `table` is bound at definition time on purpose: closing over the loop's `entry`
            # would be the classic late-binding trap even though it is called in-iteration.
            return max(pool, key=lambda name: (table[name][key] or -1e9))

        best_b0 = _best(names, "brier_skill_vs_B0_pct")
        best_r0 = _best(names, "brier_skill_vs_R0_pct")
        w2_b0 = _best(wave2, "brier_skill_vs_B0_pct")
        w2_r0 = _best(wave2, "brier_skill_vs_R0_pct")
        entry["verdict"] = {
            "best_overall_by_brier_skill_vs_B0": best_b0,
            "best_overall_by_brier_skill_vs_R0": best_r0,
            "best_WAVE2_model_vs_B0": w2_b0,
            "best_WAVE2_model_vs_R0": w2_r0,
            "any_model_clears_the_preregistered_bar_vs_B0": bool(
                (hl[best_b0]["brier_skill_vs_B0_pct"] or -1) > 0),
            "a_WAVE2_model_clears_the_bar_vs_B0": bool(
                (hl[w2_b0]["brier_skill_vs_B0_pct"] or -1) > 0),
            "any_model_clears_the_harder_bar_vs_R0": bool(
                (hl[best_r0]["brier_skill_vs_R0_pct"] or -1) > 0),
            "regime_conditioned_calibration_helped": bool(
                (hl["R2"]["brier_skill_vs_B0_pct"] or -1e9)
                > (hl["B1"]["brier_skill_vs_B0_pct"] or -1e9)),
            "over_prediction_B1_to_R2": {
                "whole_holdout": [hl["B1"]["mean_p_over_realized"],
                                  hl["R2"]["mean_p_over_realized"]],
                "head_of_book": [
                    entry["holdout"]["head_of_book"]["B1"][
                        "over_prediction_ratio_p_over_realized"],
                    entry["holdout"]["head_of_book"]["R2"][
                        "over_prediction_ratio_p_over_realized"]],
                "R0_for_comparison": [hl["R0"]["mean_p_over_realized"],
                                      entry["holdout"]["head_of_book"]["R0"][
                                          "over_prediction_ratio_p_over_realized"]],
            },
            "isotonic_head_tie_unlock": {
                "distinct_p_in_top_decile_B1_R2_R3": [
                    entry["holdout"]["head_of_book"][k]["distinct_p_values_in_top_decile"]
                    for k in ("B1", "R2", "R3")],
                "rows_tied_at_max_B1_R2": [
                    entry["holdout"]["head_of_book"][k]["rows_tied_at_max"]
                    for k in ("B1", "R2")],
                "max_p_hat_pct_B1_R2": [
                    entry["holdout"]["head_of_book"][k]["max_p_hat_pct"] for k in ("B1", "R2")],
            },
            "regime_is_a_LEVEL_instrument_not_a_RANKER": {
                "why": ("i5 is a board-level daily value, so it is CONSTANT across every name "
                        "on a given date and cannot re-order a daily book by construction.  "
                        "The measurement below is the proof: R0's within-date top-K selection "
                        "is identical to B0's at every K, while its cross-date AUC is higher."),
                "top_k_realized_B0_vs_R0": [
                    {"K": r["K"], "B0": r["realized_rate_pct"]}
                    for r in topk if r["ranker"] == "B0"],
                "top_k_realized_R0": [
                    {"K": r["K"], "R0": r["realized_rate_pct"]}
                    for r in topk if r["ranker"] == "R0"],
                "auc_B0_vs_R0": [hl["B0"]["auc"], hl["R0"]["auc"]],
            },
        }

        # today's regime state — display only, so a reader can see which cell is live
        sb = ser[ser["board"].astype(str) == board].sort_values("date").reset_index(drop=True)
        nn = sb[sb[REGIME_COL].notna()]
        live_val = float(nn[REGIME_COL].iloc[-1]) if len(nn) else None
        live_st = (int(assign_stratum(np.array([live_val], dtype=np.float64), st["edges"])[0])
                   if live_val is not None else UNKNOWN_STRATUM)
        entry["live_regime_state"] = {
            "as_of_session": (sb["date"].iloc[-1].strftime("%Y-%m-%d") if len(sb) else None),
            "last_non_null_session": (nn["date"].iloc[-1].strftime("%Y-%m-%d")
                                      if len(nn) else None),
            "i5_ma5": round(live_val, 6) if live_val is not None else None,
            "stratum": labels.get(live_st, str(live_st)),
            "r0_row_today": {
                c["N_label"]: round(100.0 * c["p"], 4)
                for key, c in sorted(r0["cells"].items())
                if key.endswith(f"|{live_st}")
            },
            "note": ("DISPLAY ONLY.  The R0 row a desk would read today under the regime the "
                     "tape is currently printing.  Nothing is promoted, sized or gated."),
        }

        by_board[board] = entry
        print(f"    {board}: holdout {len(hold):,} rows, base "
              f"{entry['holdout']['base_rate_pct']:.3f}% | skill vs B0 "
              f"R0 {hl['R0']['brier_skill_vs_B0_pct']:+.3f}% "
              f"R2 {hl['R2']['brier_skill_vs_B0_pct']:+.3f}% "
              f"R3 {hl['R3']['brier_skill_vs_B0_pct']:+.3f}% "
              f"(B1 {hl['B1']['brier_skill_vs_B0_pct']:+.3f}%, "
              f"P2 {hl['P2']['brier_skill_vs_B0_pct']:+.3f}%) | best={best_b0} "
              f"| R2 precondition met="
              f"{entry['regime_strata']['r2_precondition']['precondition_met']}", flush=True)

    payload = {
        "instrument": "research/cn_prophet_audit/regime_calibration_v2.py",
        "program": "CN LIMIT-MOVE ALPHA — Wave 2 / lane W2-A (regime-conditional calibration)",
        "merges": [
            "research/cn_prophet_audit/onset_calibration_v1.py (Wave 1 / L3, PR #5055)",
            "research/cn_prophet_audit/board_ecology_regime_v1.py (Wave 1 / L2, PR #5078)",
        ],
        "tier": ("display/audit — MEASUREMENT ONLY.  Nothing here promotes, ranks for size, "
                 "gates, admits, or reaches a live surface.  No LLM is involved."),
        "generated_utc": stamped,
        "runtime_sec": None,
        "solver": ("scikit-learn (LogisticRegression C=inf lbfgs; IsotonicRegression)"
                   if onset.SKLEARN else "numpy IRLS + PAVA fallback (sklearn unavailable)"),
        "preregistration": {
            "written_before_the_first_holdout_pass": [
                "the regime variable is i5_realized_continuation_ma5 and nothing else — L2 "
                "measured it as the only era-neutral dial in the family, and measured that the "
                "raw breadth counts INVERT within-year, so no absolute 涨停家数 count is admitted",
                "the split is L3's, frozen and unchanged, for main and chinext",
                "STAR gets its own listing-era 70/30 re-split (L3 ORE row #3, authorised); if it "
                "still misses the THIN gate it is printed THIN-SKIP again",
                "the regime dial is joined on the FEATURE bar T, per the board's OWN series; a "
                "four-gate lookahead audit is run and printed before any model is fitted",
                "strata are terciles of the dial over the board's own FIT-WINDOW SESSIONS, plus "
                "an UNKNOWN stratum for sessions with no continuation print; if any tercile "
                "carries fewer than 50 positives in the fit CALIBRATION slice, collapse to "
                "halves and print it; a stratum still under the floor falls back to the pooled "
                "map and is printed",
                "R0 is fitted on the WHOLE fit window, exactly as B0 is, so the new benchmark is "
                "never handicapped against the models it judges",
                "R2 reuses B1's logistic UNCHANGED — only the calibration step differs, so any "
                "difference is attributable to calibration and to nothing else",
                "rows with no regime print are kept via a missing indicator, NOT dropped, so the "
                "holdout row set stays byte-identical to L3's and the receipts compose",
                "metrics are L3's, imported: Brier x1000, Brier skill, exact Murphy "
                "decomposition, log-loss skill, AUC, 10-bin reliability with Wilson intervals, "
                "per-year skill, top-K realized/capture/mean P-hat",
                "ONE evaluation pass on the holdout; no refit, no retune, no re-bucketing, no "
                "second look",
            ],
            "models": {
                "B0": "L3's ladder-only benchmark — fit-window base rate per 连板 bucket N",
                "R0": "REGIME LADDER — fit-window base rate per (连板 N x i5 stratum) cell",
                "R1": "B1's logistic + i5 covariate + missing indicator, pooled isotonic",
                "R2": "B1's logistic UNCHANGED, isotonic fitted separately per i5 stratum",
                "R3": "R1's logistic + per-stratum isotonic",
                "B2, P2": ("L3's own models, re-derived UNCHANGED and REPORTED ONLY.  L3 "
                           "measured them at +0.32% and +0.71% Brier skill on this exact "
                           "holdout, so a Wave-2 receipt that omitted them would present its "
                           "own best number as the program's best when it is not.  No Wave-2 "
                           "model was refitted, retuned or reselected in response to them, and "
                           "nothing here was built on top of them."),
            },
            "the_named_defect": (
                "L3 measured chinext's calibration slice running 2.06x hotter than its holdout "
                "and B1 over-predicting the holdout by 2.58x.  head_of_book.* and "
                "holdout.by_stratum are the before/after on exactly that number."),
        },
        "definitions": {
            "target": "y = a limit-up CLOSE (PRIMARY definition) on the name's NEXT USABLE bar",
            "regime_variable": (
                "i5_realized_continuation_ma5 — 5-session backward mean of 'of the names whose "
                "prior usable bar was a limit-up, the share closing limit-up today', on the "
                "board's OWN series.  Observable at the session's own close."),
            "regime_stratum": ("tercile (or half, under the collapse ladder) of that dial over "
                               "the board's own fit-window sessions, plus UNKNOWN for sessions "
                               "with no continuation print"),
            "brier_skill_vs_B0": "1 - Brier(model)/Brier(B0).  L3's pre-registered bar.",
            "brier_skill_vs_R0": "1 - Brier(model)/Brier(R0).  The harder Wave-2 bar.",
            "head_of_book": f"the top {int(100 * TOP_FRACTION)}% of holdout rows by P-hat",
            "everything_else": ("imported verbatim from onset_calibration_v1.py — PRIMARY "
                                "limit-up definition and its 0.2% cushion, board widths from "
                                "engine.china_microstructure, ST/IPO/ex-div/zero-volume "
                                "exclusions, the 10-calendar-day pair rule, 连板 N bucketing, "
                                "complete-case handling, Wilson intervals, THIN floors"),
        },
        "coverage_receipt": {
            "price_basis": ("data/china_stocks_raw — nominal/unadjusted.  The adjusted twin "
                            "would fabricate limit misses."),
            "store_vintage": {
                "names_in_store": panel_meta.get("files_found"),
                "tickers_kept": panel_meta.get("tickers_kept"),
                "checkout_head_sha": head_sha(),
                "last_bar_in_panel": max_date.strftime("%Y-%m-%d"),
                "WARNING": (
                    "THIS RUN PREDATES THE UNIVERSE EXPANSION.  A sibling lane is growing "
                    "data/china_stocks_raw from ~1,842 names toward ~5,400.  Every probability, "
                    "every stratum edge and every regime print here is calibrated ON and FOR "
                    "the pre-expansion curated slice.  A post-expansion re-run is NOT a "
                    "refinement of these numbers — it is a different universe, and the two "
                    "receipts must be compared as such.  It is in the ORE LEDGER."),
            },
            "regime_series": ser_meta,
            "panel": panel_meta,
            "lookahead_audit": look,
            "determinism": ("TZ=UTC pinned at import; ticker-sorted file walk; no sampling "
                            "anywhere; ties broken by ticker ascending.  Two consecutive runs "
                            "produce byte-identical JSON modulo generated_utc/runtime_sec."),
        },
        "splits": splits,
        "split_notes": split_notes,
        "by_board": by_board,
        "what_this_does_NOT_establish": [
            "NO significance claim.  Limit-ups cluster hard in time and in the cross-section, so "
            "every Wilson interval printed here is UNDERSTATED.  The evidence offered is skill "
            "and calibration on a frozen holdout plus per-year stability — never a p-value.",
            "It does NOT establish that i5 is causal.  It establishes that conditioning the "
            "CALIBRATION on i5 changes the holdout's calibration in a measured direction.  A "
            "dial that merely co-moves with the base rate would do the same.",
            "It does NOT rescue anything the ORE LAW would call a promotion.  This is display "
            "tier; no key is escalated, ranked for size, or gated on.",
            "Calibration remains IN-UNIVERSE.  The probabilities are calibrated for the curated "
            "~1,842-name store, not for the A-share market, and the 打板 game is denser in the "
            "names the store omits.  L2 measured the consequence for market-level dials "
            "directly: a median 2.748x undercount against the vendor pool.",
            "The regime dial inherits that curation MORE than a per-name feature does.  i5 is a "
            "RATE, so it is less exposed than a count — but it is still a rate measured inside "
            "the slice we hold.",
            "It says nothing about FILLABILITY.  P is for a limit-up CLOSE; a name that gaps "
            "straight to the limit at the open is unfillable and still scores as a hit.",
            "It says nothing about the CONTINUATION side as a model.  N is an input and i5 is a "
            "market aggregate; P(next board | already N boards) as a modelled object is lane "
            "L1's, and merging it is in the ORE LEDGER.",
            "H=1 only.  Nothing here speaks to a board within the next 3 or 5 sessions.",
            "Survivorship is unfixed with the stores we hold, and stated rather than patched.",
        ],
        "ore_ledger": [
            {"ore": "the other L2 instruments as conditioners — 炸板率 (i4) and 高标 height (i3)",
             "status": "UNTESTED HERE — only i5 was admitted",
             "why_it_could_matter": ("L2 measured 炸板率 as a real INVERSE dial pooled "
                                     "(holdout 0.724x, rho -0.6) that did NOT survive its "
                                     "era-neutral control (median 0.974, 9/16 years) — which "
                                     "makes it a confluence candidate, not a null.  Under house "
                                     "epistemics a factor that fails as a STANDALONE signal is "
                                     "retained as a confluence input.  i3 is blind in our "
                                     "universe (below the market on 21 of 36 clean dates, mean "
                                     "gap 1.81 boards) and needs the vendor pool first."),
             "next": "two-dial strata (i5 x i4) on the same frozen split, pre-registered"},
            {"ore": "continuous-in-i5 calibration instead of terciles",
             "status": "UNTESTED",
             "why_it_could_matter": ("terciles are a step function over a continuous dial, so "
                                     "every within-stratum gradient is thrown away and every "
                                     "edge is a discontinuity a desk would have to explain.  A "
                                     "2-D isotonic in (raw score, i5) or a varying-coefficient "
                                     "map would keep the gradient."),
             "next": "2-D isotonic / beta calibration with i5 as the second argument; compare "
                     "against R2 on the identical frozen split"},
            {"ore": "regime-conditional FEATURE coefficients (interactions, not just level)",
             "status": "UNTESTED — R1 admits i5 only as a MAIN EFFECT",
             "why_it_could_matter": ("the practitioner claim is not that a hot tape lifts every "
                                     "name equally — it is that run-up and gap MEAN something "
                                     "different in a hot tape.  R1 cannot express that; only an "
                                     "i5 x feature cross can."),
             "next": "explicit i5 x f3 and i5 x f4 crosses, pre-registered, same frozen split"},
            {"ore": "horizons H > 1 (a board within the next 3 / 5 sessions)",
             "status": "UNTESTED — inherited from L3's ledger, unchanged",
             "why_it_could_matter": ("H=1 is the hardest possible framing and may be why the "
                                     "absolute probabilities stay small; a regime dial should "
                                     "help MORE at a longer horizon, since it is a slower "
                                     "variable than any per-name feature"),
             "next": "same features, H in {2,3,5}; overlapping windows worsen the dependence, so "
                     "state it before measuring"},
            {"ore": "the L1 continuation-side regime merge",
             "status": "OUT OF SCOPE — lane L1 owns P(board | already N boards)",
             "why_it_could_matter": ("i5 IS the realized continuation rate, so conditioning a "
                                     "continuation model on it is far more direct than "
                                     "conditioning an ONSET model on it.  The largest expected "
                                     "effect in the program is probably there, not here."),
             "next": "L1's empirics x i5 strata as a sibling model, never pooled with this one"},
            {"ore": "post-expansion re-run on the ~5,400-name universe",
             "status": "BLOCKED on the sibling universe lane, not on method",
             "why_it_could_matter": ("the omitted names are where the 打板 game is densest, and "
                                     "a market-level dial inherits the curation directly — the "
                                     "i5 level measured here is a curated-slice level"),
             "next": "re-run this file unchanged once the store lands; compare receipts as two "
                     "universes, never as before/after of one"},
            {"ore": "per-stratum FEATURE selection / per-stratum logistic",
             "status": "UNTESTED — R2 deliberately holds the logistic fixed",
             "why_it_could_matter": ("holding the logistic fixed is what makes R2's effect "
                                     "attributable to calibration alone; relaxing it would buy "
                                     "flexibility and lose the attribution"),
             "next": "only after R2's calibration effect is established, and with the "
                     "attribution loss stated up front"},
            {"ore": "an ECE-optimal or Platt/beta calibration in place of isotonic",
             "status": "UNTESTED — inherited from L3's ledger",
             "why_it_could_matter": ("isotonic is a step function whose top block is a tie, "
                                     "which is exactly L3's head-of-book defect; a smooth map "
                                     "would order the head of the book"),
             "next": "beta calibration per stratum; report ECE and head-of-book ties for both"},
            {"ore": "the STAR era re-split as a general policy",
             "status": "APPLIED HERE TO STAR ONLY, by pre-registration",
             "why_it_could_matter": ("if a listing-era re-split is right for STAR it may be "
                                     "right for any board whose era post-dates the global "
                                     "split; but a split rule chosen per board is a degree of "
                                     "freedom and must be pre-registered, never fitted"),
             "next": "state the rule once, in the program masterplan, before Wave 3"},
        ],
    }
    payload["runtime_sec"] = round(time.time() - t0, 1)
    OUT_JSON.write_text(json.dumps(onset.jsonable(payload), indent=2, ensure_ascii=False) + "\n")
    print(f"[done] {payload['runtime_sec']:.1f}s -> {OUT_JSON.name}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
