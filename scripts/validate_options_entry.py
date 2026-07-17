"""scripts/validate_options_entry.py — pre-registered options-entry-quality gate.

Options Alpha program W1.3 / W-C (research/OPTIONS_ALPHA_MASTERPLAN.md §4, rulings A6/A9/A10;
W-C 2026-07-05 adds five new pre-registered bucket tests).
Extended by W-OVC (2026-07-17): S-VANNA-RELIEF and S-FRONT-CHARM gate cells registered.
See OPTIONS_OPEX_VANNA_CHARM_ADJUDICATION.md §4/§5 for the ruling and gate specifications.

THE KEYSTONE MACHINE, NOT A RESULT. This gate answers — once enough fires accrue — the one
question the desk cares about:

    "Does options context reduce stop-outs / dead money and improve clean liftoffs on entries
     the price thesis already likes?"

It reads the options-state-stamped US board ledger (``data/us_board_ledger/retro_grades.parquet``,
stamped by scripts/stamp_options_state.py) and runs pre-registered bucket tests from §4 of the
masterplan, speaking ONLY in ledger primitives (ruling A10):

  * ``post_cushion_breach``            — 21d stop-out proxy (True/False/None)
  * ``terminal_state_clean8_21``       — 21d clean-liftoff label (CLEAN_LIFTOFF vs the rest)
  * ``fwd_mfe_21`` / ``fwd_mfe_5``     — max favourable excursion
  * ``fwd_ret_5``                       — fast 5d return (S-VOI fast read)

There is NO stop5 / clean15@5d / absolute-MAE primitive; the wall study (S-WALL) computes
absolute-price wall touches directly from ``data/massive_stock_day/`` raw closes vs the stamped
``opt_wall_down`` level (close-path — UNDERSTATES intraday touches; documented in the evidence).

W-C ADDITIONS (pre-registered 2026-07-05):
  * S-IVSPREAD-F: fire-conditioned call−put IV spread (opt_ivspread_rel > 0 vs <= 0)
  * S-SKEW_DECEL: skew top-tercile AND falling (opt_skew_5d_chg < 0 vs rest)
  * S-TOP_RISK: de-escalation flag (skew rising OR ivspread_rel < 0 → flag bad entries)
    CAUTION-ONLY: beneficial direction = flagged fires show WORSE outcomes (correctly de-escalates)
  * S-PIN_RISK: OPEX proximity + long-gamma + near-wall flag (opt_pin_risk True vs False)
  * S-VOI2: stricter vol>OI burst (see engine/options_stamp.py notes; FUTURE stamp col)

W-OVC ADDITIONS (pre-registered 2026-07-17 — adjudication OPTIONS_OPEX_VANNA_CHARM_ADJUDICATION.md):
  * S-VANNA-RELIEF: vanna-relief vol compression flag (opt_vanna_relief True vs False)
    PRIMARY: post_cushion_breach delta (beneficial = LOWER breach in flagged bucket)
    SECONDARY: terminal_state_clean8_21, fwd_mfe_21 (reported honestly; no pre-judged direction)
    Holdability / de-escalation / stop-width state only (RO-3 caution-only). NOT an entry originator.
  * S-FRONT-CHARM: front-expiry charm concentration flag (opt_front7_charm_share top tercile vs rest)
    PRIMARY: post_cushion_breach delta (beneficial = HIGHER breach → flag correctly identifies vol-
    exposed entries; caution-only per RO-3 — may only LOWER conviction, never short)
    SECONDARY: terminal_state_clean8_21, fwd_mfe_21 (reported honestly)

Each test is a conditioned-vs-unconditioned delta with a bootstrap CI. HARD RULE (doctrine
§2.3): NO verdict — no effect-size claim — until n ≥ ``MIN_PER_BUCKET`` fires in EACH condition
bucket. Both W-OVC buckets are ``building_history`` on initial dispatch (stamp ships first).

Output: ``data/options_entry/gate.json`` (schema ``options_entry.gate.v3``, extends v2).

Only recomputes counts / verdicts — a verdict flip requires the pre-registered thresholds,
never a code edit. Idempotent, resilient.

FDR FAMILY (BH α=0.10): 28 tests total (22 prior + 6 W-OVC: S-VANNA-RELIEF×3, S-FRONT-CHARM×3).
See OPTIONS_ALPHA_MASTERPLAN.md §4 amended-family BH-FDR statement (2026-07-06).
No verdict claims significance without clearing BH-FDR at α=0.10 over this full family.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
from pathlib import Path

import numpy as np
import pandas as pd

from engine.options_stamp import STAMP_COLS
from lib import config

GATE_DIR = config.data_dir() / "options_entry"
GATE_PATH = GATE_DIR / "gate.json"
LEDGER_PATH = config.data_dir() / "us_board_ledger" / "retro_grades.parquet"
STOCK_DAY_DIR = config.data_dir() / "massive_stock_day"

# pre-registered thresholds (doctrine §2.3 — bans sub-30 verdicts)
MIN_PER_BUCKET = 30
BOOTSTRAP_N = 2000
CLEAN = "CLEAN_LIFTOFF"          # terminal_state_clean8_21 value that means a clean liftoff
FIXED_STOP = 0.95               # S-WALL comparator: fixed −5% stop

_RNG = np.random.default_rng(20260703)


# ── bootstrap helpers ────────────────────────────────────────────────────────
def _bootstrap_mean_ci(vals: np.ndarray, n_boot: int = BOOTSTRAP_N) -> tuple[float, float, float]:
    """(point mean, 2.5%, 97.5%) bootstrap CI of the mean. NaN triple on empty."""
    vals = vals[~np.isnan(vals)]
    n = len(vals)
    if n == 0:
        return (float("nan"), float("nan"), float("nan"))
    idx = _RNG.integers(0, n, size=(n_boot, n))
    means = vals[idx].mean(axis=1)
    return (float(vals.mean()), float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5)))


def _bootstrap_delta_ci(a: np.ndarray, b: np.ndarray,
                        n_boot: int = BOOTSTRAP_N) -> dict:
    """Bootstrap CI for mean(a) − mean(b) (conditioned − unconditioned).

    Returns delta, ci_lo, ci_hi, and ``excludes_zero`` (the pre-registered pass signal).
    Both arrays are NaN-dropped; empty either side → all-NaN, excludes_zero False."""
    a = a[~np.isnan(a)]
    b = b[~np.isnan(b)]
    na, nb = len(a), len(b)
    if na == 0 or nb == 0:
        return {"n_cond": na, "n_base": nb, "delta": None,
                "ci_lo": None, "ci_hi": None, "excludes_zero": False}
    ia = _RNG.integers(0, na, size=(n_boot, na))
    ib = _RNG.integers(0, nb, size=(n_boot, nb))
    deltas = a[ia].mean(axis=1) - b[ib].mean(axis=1)
    lo, hi = float(np.percentile(deltas, 2.5)), float(np.percentile(deltas, 97.5))
    return {
        "n_cond": na, "n_base": nb,
        "delta": round(float(a.mean() - b.mean()), 5),
        "ci_lo": round(lo, 5), "ci_hi": round(hi, 5),
        "excludes_zero": bool(lo > 0 or hi < 0),
    }


def _breach_rate_arr(sub: pd.DataFrame) -> np.ndarray:
    """post_cushion_breach as a 0/1 array over applicable (non-None) rows.
    Lower is better (fewer post-cushion stop-outs)."""
    v = sub["post_cushion_breach"] if "post_cushion_breach" in sub.columns else pd.Series(dtype=object)
    v = v.dropna()
    return v.astype(bool).astype(float).to_numpy()


def _clean_rate_arr(sub: pd.DataFrame) -> np.ndarray:
    """terminal_state_clean8_21 == CLEAN_LIFTOFF as a 0/1 array over matured (non-None) rows.
    Higher is better."""
    col = "terminal_state_clean8_21"
    if col not in sub.columns:
        return np.array([], dtype=float)
    v = sub[col].dropna()
    return (v == CLEAN).astype(float).to_numpy()


def _num_arr(sub: pd.DataFrame, col: str) -> np.ndarray:
    if col not in sub.columns:
        return np.array([], dtype=float)
    return pd.to_numeric(sub[col], errors="coerce").dropna().to_numpy()


# ── one bucket test (conditioned vs unconditioned) ───────────────────────────
def _bucket_test(df: pd.DataFrame, mask: pd.Series, label: str) -> dict:
    """Compute the conditioned (mask=True) vs unconditioned (mask=False) deltas on the
    three ledger-primitive outcomes. Each ledger row populates only its own horizon's fwd_*
    col, so the fwd_mfe_21 delta naturally draws only from the 21d rows that carry it."""
    cond = df[mask]
    base = df[~mask]
    n_cond = int(mask.sum())
    n_base = int((~mask).sum())

    out = {
        "bucket": label,
        "n_cond": n_cond, "n_base": n_base,
        "ready": bool(n_cond >= MIN_PER_BUCKET and n_base >= MIN_PER_BUCKET),
        "breach": _bootstrap_delta_ci(_breach_rate_arr(cond), _breach_rate_arr(base)),
        "clean": _bootstrap_delta_ci(_clean_rate_arr(cond), _clean_rate_arr(base)),
        "mfe21": _bootstrap_delta_ci(_num_arr(cond, "fwd_mfe_21"), _num_arr(base, "fwd_mfe_21")),
    }
    return out


def _verdict_for_test(t: dict) -> str:
    """A test PASSES only when it is ready (both buckets ≥ MIN) AND at least one of the three
    primitive deltas has a bootstrap CI excluding 0 in the beneficial direction.

    Beneficial: breach delta < 0 (fewer stop-outs), clean delta > 0 (more liftoffs),
    mfe21 delta > 0 (more upside). We require the CI to exclude 0 AND the point estimate to
    have the beneficial sign."""
    if not t["ready"]:
        return "building_history"
    passes = []
    b, c, m = t["breach"], t["clean"], t["mfe21"]
    if b["excludes_zero"] and b["delta"] is not None and b["delta"] < 0:
        passes.append("breach_reduced")
    if c["excludes_zero"] and c["delta"] is not None and c["delta"] > 0:
        passes.append("clean_improved")
    if m["excludes_zero"] and m["delta"] is not None and m["delta"] > 0:
        passes.append("mfe21_improved")
    return "signal" if passes else "no_effect"


# ── S-VOI fast read (5d primitives) ──────────────────────────────────────────
def _voi_fast_test(df: pd.DataFrame) -> dict:
    """S-VOI fastest read: fwd_ret_5 / fwd_mfe_5 deltas conditioned on opt_voi_flag=True."""
    if "opt_voi_flag" not in df.columns:
        return {"bucket": "S-VOI-fast", "n_cond": 0, "n_base": 0, "ready": False,
                "fwd_ret_5": _bootstrap_delta_ci(np.array([]), np.array([])),
                "fwd_mfe_5": _bootstrap_delta_ci(np.array([]), np.array([]))}
    flag = df["opt_voi_flag"].astype("boolean")
    cond = df[flag == True]   # noqa: E712 — pandas boolean mask
    base = df[flag == False]  # noqa: E712
    return {
        "bucket": "S-VOI-fast",
        "n_cond": len(cond), "n_base": len(base),
        "ready": bool(len(cond) >= MIN_PER_BUCKET and len(base) >= MIN_PER_BUCKET),
        "fwd_ret_5": _bootstrap_delta_ci(_num_arr(cond, "fwd_ret_5"), _num_arr(base, "fwd_ret_5")),
        "fwd_mfe_5": _bootstrap_delta_ci(_num_arr(cond, "fwd_mfe_5"), _num_arr(base, "fwd_mfe_5")),
    }


# ── S-WALL (raw-close wall-touch study; A10) ─────────────────────────────────
def _read_stock_day(ticker: str) -> pd.Series | None:
    """Raw daily closes for a ticker from data/massive_stock_day/<TICKER>.parquet (R2-backed;
    may be absent locally). Returns a close Series indexed by date, or None."""
    p = STOCK_DAY_DIR / f"{ticker}.parquet"
    if not p.exists():
        return None
    try:
        df = pd.read_parquet(p, columns=["close"])
    except Exception:  # noqa: BLE001
        return None
    if df.empty or "close" not in df.columns:
        return None
    return df["close"]


def _wall_touch_study(df: pd.DataFrame, horizon: int = 21) -> dict:
    """S-WALL: for fires with a stamped opt_wall_down, walk the raw closes over the forward
    window and record whether the close touched the wall (close ≤ wall) vs whether it touched
    the fixed −5% stop first. This is a CLOSE-PATH study — it UNDERSTATES intraday touches (a
    bar can pierce the wall intraday and close back above it). Documented in the evidence.

    Returns per-fire counts only (no verdict); the full stop-out comparison is W2.3."""
    n_eligible = 0
    n_priced = 0
    wall_touches = 0
    fixed_stop_touches = 0
    wall_before_fixed = 0

    if "opt_wall_down" not in df.columns:
        return {"n_eligible": 0, "n_priced": 0, "wall_touches": 0,
                "fixed_stop_touches": 0, "wall_before_fixed": 0, "price_store_available": False,
                "limitation": "opt_wall_down not stamped yet"}

    # one fire per (as_of, ticker) — wall level is identical across lanes/horizons
    fires = df[df["opt_wall_down"].notna()][["as_of", "ticker", "opt_wall_down"]].drop_duplicates(
        subset=["as_of", "ticker"])
    n_eligible = len(fires)
    price_store_available = False

    for _, r in fires.iterrows():
        closes = _read_stock_day(str(r["ticker"]))
        if closes is None:
            continue
        price_store_available = True
        try:
            as_of = pd.Timestamp(r["as_of"])
        except (ValueError, TypeError):
            continue
        # next-bar fill: first close strictly after as_of
        fwd = closes[closes.index > as_of].head(horizon)
        if fwd.empty:
            continue
        entry = float(fwd.iloc[0])
        if not (entry > 0):
            continue
        n_priced += 1
        wall = float(r["opt_wall_down"])
        fixed = entry * FIXED_STOP
        # first-passage over the forward path
        wall_bar = next((i for i, c in enumerate(fwd.to_numpy()) if float(c) <= wall), None)
        fixed_bar = next((i for i, c in enumerate(fwd.to_numpy()) if float(c) <= fixed), None)
        if wall_bar is not None:
            wall_touches += 1
        if fixed_bar is not None:
            fixed_stop_touches += 1
        if wall_bar is not None and (fixed_bar is None or wall_bar <= fixed_bar):
            wall_before_fixed += 1

    return {
        "n_eligible": n_eligible,
        "n_priced": n_priced,
        "wall_touches": wall_touches,
        "fixed_stop_touches": fixed_stop_touches,
        "wall_before_fixed": wall_before_fixed,
        "price_store_available": price_store_available,
        "limitation": ("close-path study understates intraday touches; a bar may pierce the wall "
                       "intraday and close back above it. Full stop-out comparison is W2.3."),
    }


# ── W-C: new pre-registered bucket tests ─────────────────────────────────────

def _verdict_for_top_risk(t: dict) -> str:
    """Verdict for S-TOP_RISK (caution-only de-escalation flag).

    Pre-registered primitives (§4): {breach, clean}.
    Beneficial direction (conjunction, per §4 registration):
      breach delta > 0 (MORE stop-outs in flagged bucket) AND
      clean delta < 0 (FEWER clean liftoffs in flagged bucket).
    Both conditions must hold for a 'signal' verdict — OR would deviate from the
    written pre-registration.  This signal MAY ONLY LOWER confidence, never short (RO-3)."""
    if not t["ready"]:
        return "building_history"
    b, c = t["breach"], t["clean"]
    breach_ok = b["excludes_zero"] and b["delta"] is not None and b["delta"] > 0
    clean_ok = c["excludes_zero"] and c["delta"] is not None and c["delta"] < 0
    return "signal" if (breach_ok and clean_ok) else "no_effect"


def _verdict_for_pin_risk(t: dict) -> str:
    """Verdict for S-PIN_RISK (caution-only pin-risk flag).

    Pre-registered primitives (§4): {clean, mfe21} — breach is NOT a registered
    S-PIN_RISK primitive.  Beneficial direction:
      clean delta < 0 (FEWER clean liftoffs — pin mechanics suppress liftoff) AND/OR
      mfe21 delta < 0 (LOWER mfe21 — pin mechanics suppress follow-through).
    §4 registers 'LOWER clean rate + LOWER mfe21' as the signal pattern; we require
    both conditions for a 'signal' verdict to match the conjunction wording in the
    pre-registration.  This signal MAY ONLY LOWER confidence, never short (RO-3)."""
    if not t["ready"]:
        return "building_history"
    c = t.get("clean")
    m = t.get("mfe21")
    if c is None or m is None:
        return "building_history"
    clean_ok = c["excludes_zero"] and c["delta"] is not None and c["delta"] < 0
    mfe21_ok = m["excludes_zero"] and m["delta"] is not None and m["delta"] < 0
    return "signal" if (clean_ok and mfe21_ok) else "no_effect"


def _ivspread_f_test(df: pd.DataFrame) -> dict:
    """S-IVSPREAD-F: fire-conditioned call-put IV spread.

    Condition: opt_ivspread_rel > 0 (calls richening vs puts = constructive positioning)
    vs opt_ivspread_rel <= 0. A10 primitives: breach, clean, mfe21.
    Pre-registered in §4 W-C (2026-07-05). Era: single live-accrual 2026→."""
    col = "opt_ivspread_rel"
    if col not in df.columns or df[col].notna().sum() == 0:
        return {"bucket": "S-IVSPREAD-F", "n_cond": 0, "n_base": 0, "ready": False,
                "note": f"{col} not yet stamped — W-C harness extension pending full backfill"}
    iv = pd.to_numeric(df[col], errors="coerce")
    sub = df[iv.notna()].copy()
    submask = pd.to_numeric(sub[col], errors="coerce") > 0
    return _bucket_test(sub, submask, "S-IVSPREAD-F: ivspread_rel > 0 (calls richening)")


def _skew_decel_test(df: pd.DataFrame) -> dict:
    """S-SKEW_DECEL: skew high-but-falling at fire.

    Condition: opt_skew in top cross-sectional tercile (by as_of date, over stamped fires)
    AND opt_skew_5d_chg < 0.  vs rest.  A10 primitives: breach, clean, mfe21.
    Pre-registered in §4 W-C (2026-07-05). Era: single live-accrual 2026→."""
    skew_col = "opt_skew"
    chg_col = "opt_skew_5d_chg"
    if skew_col not in df.columns or df[skew_col].notna().sum() == 0:
        return {"bucket": "S-SKEW_DECEL", "n_cond": 0, "n_base": 0, "ready": False,
                "note": f"{skew_col} not yet stamped — W-C harness extension pending"}
    if chg_col not in df.columns or df[chg_col].notna().sum() == 0:
        return {"bucket": "S-SKEW_DECEL", "n_cond": 0, "n_base": 0, "ready": False,
                "note": f"{chg_col} not yet stamped — needs ≥5 prior days of skew snapshots"}
    # need both columns present
    both = df[df[skew_col].notna() & df[chg_col].notna()].copy()
    if both.empty:
        return {"bucket": "S-SKEW_DECEL", "n_cond": 0, "n_base": 0, "ready": False,
                "note": "no fires with both opt_skew and opt_skew_5d_chg stamped yet"}
    # compute top-tercile cutoff cross-sectionally per as_of date
    tercile_hi = (
        both.groupby("as_of")[skew_col]
        .transform(lambda x: x.quantile(2 / 3))
    )
    in_top_tercile = pd.to_numeric(both[skew_col], errors="coerce") >= tercile_hi
    falling = pd.to_numeric(both[chg_col], errors="coerce") < 0
    submask = in_top_tercile & falling
    return _bucket_test(
        both, submask.fillna(False),
        "S-SKEW_DECEL: skew top-tercile AND skew_5d_chg < 0 (high skew fading)"
    )


def _top_risk_test(df: pd.DataFrame) -> dict:
    """S-TOP_RISK: de-escalation family flag.

    Condition: opt_skew_5d_chg > 0 (puts richening) OR opt_ivspread_rel < 0 (puts rich).
    CAUTION-ONLY per RO-3: a PASS means flagged fires have WORSE outcomes (correctly
    identifies bad entries; used to LOWER confidence, never to short).
    A10 primitives: breach (primary), clean (secondary).
    Pre-registered in §4 W-C (2026-07-05). Era: single live-accrual 2026→."""
    skew_chg_col = "opt_skew_5d_chg"
    iv_col = "opt_ivspread_rel"
    skew_ok = skew_chg_col in df.columns and df[skew_chg_col].notna().any()
    iv_ok = iv_col in df.columns and df[iv_col].notna().any()
    if not skew_ok and not iv_ok:
        return {"bucket": "S-TOP_RISK", "n_cond": 0, "n_base": 0, "ready": False,
                "note": "neither opt_skew_5d_chg nor opt_ivspread_rel stamped yet"}
    # use rows with at least one of the two cols stamped
    sub = df[
        (df[skew_chg_col].notna() if skew_ok else False) |
        (df[iv_col].notna() if iv_ok else False)
    ].copy() if (skew_ok or iv_ok) else df.copy()
    if sub.empty:
        return {"bucket": "S-TOP_RISK", "n_cond": 0, "n_base": 0, "ready": False,
                "note": "no rows with relevant stamp cols"}
    skew_rising = (
        pd.to_numeric(sub[skew_chg_col], errors="coerce") > 0
        if skew_chg_col in sub.columns else pd.Series(False, index=sub.index)
    )
    puts_rich = (
        pd.to_numeric(sub[iv_col], errors="coerce") < 0
        if iv_col in sub.columns else pd.Series(False, index=sub.index)
    )
    submask = (skew_rising | puts_rich).fillna(False)
    result = _bucket_test(
        sub, submask,
        "S-TOP_RISK: skew_5d_chg>0 OR ivspread_rel<0 (puts richening/dominant — caution-only)"
    )
    result["caution_only"] = True
    result["note"] = (
        "CAUTION-ONLY (RO-3): beneficial direction = flagged fires show WORSE outcomes "
        "(correctly identifies bad entries). NEVER initiates a negative position."
    )
    return result


def _pin_risk_test(df: pd.DataFrame) -> dict:
    """S-PIN_RISK: OPEX proximity + long-gamma + near-wall flag.

    Condition: opt_pin_risk == True vs False.  CAUTION-ONLY: beneficial = flagged fires
    have lower clean liftoff + lower mfe21 (pinning suppresses follow-through).
    A10 primitives: clean (primary), mfe21 (secondary).
    Pre-registered in §4 W-C (2026-07-05). Era: single live-accrual 2026→."""
    col = "opt_pin_risk"
    if col not in df.columns or df[col].notna().sum() == 0:
        return {"bucket": "S-PIN_RISK", "n_cond": 0, "n_base": 0, "ready": False,
                "note": f"{col} not yet stamped — W-C harness extension pending"}
    pin = df[col].astype("boolean")
    sub = df[pin.notna()].copy()
    submask = sub[col].astype("boolean") == True  # noqa: E712
    result = _bucket_test(
        sub, submask.fillna(False),
        "S-PIN_RISK: opex_days<=5 AND gamma=long AND min_wall_dist<=2% (pin-risk window)"
    )
    result["caution_only"] = True
    result["note"] = (
        "CAUTION-ONLY: beneficial direction = flagged fires show lower clean liftoff / mfe21 "
        "(pinning suppresses follow-through). de-escalation only, never a short."
    )
    return result


def _voi2_test(df: pd.DataFrame) -> dict:
    """S-VOI2: stricter vol>OI burst (pre-registered, harness col not yet stamped).

    S-VOI2 requires a future stamp column opt_voi2_flag (z-threshold + contract-count
    floor; see §4 registration). Until that column is stamped, this is building_history.
    This function is a placeholder that will activate once the stamp col exists.
    Pre-registered in §4 W-C (2026-07-05). Documented as a NEW registration distinct from
    the degenerate S-VOI (n_base=4 is architecturally degenerate; S-VOI registration stands)."""
    col = "opt_voi2_flag"
    if col not in df.columns or df[col].notna().sum() == 0:
        return {
            "bucket": "S-VOI2",
            "n_cond": 0, "n_base": 0, "ready": False,
            "note": (
                f"{col} not yet stamped — awaits W-C harness extension that adds the stricter "
                "z-threshold + contract-count-floor to the stamp (future PR). "
                "S-VOI original registration stands; this is a distinct, stricter bucket "
                "registered after S-VOI was documented as degenerate (n_cond=42/n_base=4)."
            ),
        }
    flag = df[col].astype("boolean")
    sub = df[flag.notna()].copy()
    submask = sub[col].astype("boolean") == True  # noqa: E712
    result: dict = {
        "bucket": "S-VOI2",
        "n_cond": int(submask.sum()), "n_base": int((~submask).sum()),
        "ready": bool(int(submask.sum()) >= MIN_PER_BUCKET and int((~submask).sum()) >= MIN_PER_BUCKET),
        "fwd_ret_5": _bootstrap_delta_ci(_num_arr(sub[submask], "fwd_ret_5"),
                                          _num_arr(sub[~submask], "fwd_ret_5")),
        "fwd_mfe_5": _bootstrap_delta_ci(_num_arr(sub[submask], "fwd_mfe_5"),
                                           _num_arr(sub[~submask], "fwd_mfe_5")),
        "breach": _bootstrap_delta_ci(_breach_rate_arr(sub[submask]), _breach_rate_arr(sub[~submask])),
        "clean": _bootstrap_delta_ci(_clean_rate_arr(sub[submask]), _clean_rate_arr(sub[~submask])),
        "mfe21": _bootstrap_delta_ci(_num_arr(sub[submask], "fwd_mfe_21"),
                                      _num_arr(sub[~submask], "fwd_mfe_21")),
    }
    return result


# ── W-OVC: new pre-registered bucket tests (2026-07-17) ─────────────────────

def _vanna_relief_test(df: pd.DataFrame) -> dict:
    """S-VANNA-RELIEF: vanna-relief vol compression flag.

    Condition: opt_vanna_relief == True (IV fell 5d AND vanna_hedge_5d in top cross-
    sectional tercile per as_of) vs False.
    A10 primitives:
      PRIMARY:   post_cushion_breach delta (beneficial = LOWER breach in flagged bucket;
                 vanna relief = hedging flow compresses vol = fewer stop-outs)
      SECONDARY: terminal_state_clean8_21, fwd_mfe_21 (reported honestly; compression may
                 trim both tails — no pre-judged direction per masterplan §4 registration)
    Scored=false, building_history until n≥30/bucket.
    CAUTION-ONLY per RO-3: holdability / de-escalation / stop-width context only.
    NOT an entry originator; never initiates a new position.

    Pre-registered gate (OPTIONS_ALPHA_MASTERPLAN.md §4 W-OVC, 2026-07-17).
    Era: single live-accrual (2026→); stamp ships in W-OVC first (same pattern as S-PIN_RISK).
    """
    col = "opt_vanna_relief"
    if col not in df.columns or df[col].notna().sum() == 0:
        return {"bucket": "S-VANNA-RELIEF", "n_cond": 0, "n_base": 0, "ready": False,
                "note": (f"{col} not yet stamped — W-OVC harness extension (stamp ships "
                         "in this PR; history accrues from live fires)")}
    flag = df[col].astype("boolean")
    sub = df[flag.notna()].copy()
    submask = sub[col].astype("boolean") == True  # noqa: E712
    result = _bucket_test(
        sub, submask.fillna(False),
        "S-VANNA-RELIEF: opt_vanna_relief=True (IV fell 5d AND vanna_hedge top-tercile)"
    )
    result["caution_only"] = True
    result["note"] = (
        "CAUTION-ONLY (RO-3): holdability / de-escalation / stop-width state. "
        "PRIMARY = breach delta (beneficial = LOWER breach). "
        "SECONDARY = clean + mfe21 (reported honestly; no pre-judged direction). "
        "Never originates a new entry. "
        "Sign note (audit #29): flag uses signed net vanna under long-call/short-put "
        "dealer convention; mechanism narrative inherits that assumption."
    )
    return result


def _front_charm_test(df: pd.DataFrame) -> dict:
    """S-FRONT-CHARM: front-expiry charm concentration flag (caution-only).

    Condition: opt_front7_charm_share in top cross-sectional tercile per as_of vs rest.
    A10 primitives:
      PRIMARY:   post_cushion_breach delta (beneficial = HIGHER breach in flagged bucket →
                 flag correctly identifies vol-exposed entries; CAUTION-ONLY per RO-3)
      SECONDARY: terminal_state_clean8_21, fwd_mfe_21 (reported honestly)
    Scored=false, building_history until n≥30/bucket.
    CAUTION-ONLY per RO-3: elevated front-charm = wider stops / worse holdability.
    May only LOWER conviction; never initiates a negative position.

    Root-class caveat (RUL-OVC-3): opt_root_class is reported per-class once n allows.
    ETF-slice sign is era-unstable (robustness §3.2) — do not interpret without root_class.

    Pre-registered gate (OPTIONS_ALPHA_MASTERPLAN.md §4 W-OVC, 2026-07-17).
    Era: single live-accrual (2026→); stamp ships in W-OVC first.
    """
    col = "opt_front7_charm_share"
    if col not in df.columns or df[col].notna().sum() == 0:
        return {"bucket": "S-FRONT-CHARM", "n_cond": 0, "n_base": 0, "ready": False,
                "note": (f"{col} not yet stamped — W-OVC harness extension (stamp ships "
                         "in this PR; history accrues from live fires)")}
    charm_val = pd.to_numeric(df[col], errors="coerce")
    sub = df[charm_val.notna()].copy()
    if sub.empty:
        return {"bucket": "S-FRONT-CHARM", "n_cond": 0, "n_base": 0, "ready": False,
                "note": "no fires with opt_front7_charm_share stamped yet"}
    # Top tercile per as_of date (cross-sectional, matching stamp construction)
    tercile_hi = (
        sub.groupby("as_of")[col]
        .transform(lambda x: x.quantile(2.0 / 3.0))
    )
    submask = pd.to_numeric(sub[col], errors="coerce") >= tercile_hi
    result = _bucket_test(
        sub, submask.fillna(False),
        "S-FRONT-CHARM: opt_front7_charm_share top-tercile (near-term charm concentration)"
    )
    result["caution_only"] = True
    result["note"] = (
        "CAUTION-ONLY (RO-3): elevated front-charm = higher near-term vol risk = wider stops. "
        "PRIMARY = breach delta (beneficial = HIGHER breach — flag correctly identifies "
        "vol-exposed entries). SECONDARY = clean + mfe21 (reported honestly). "
        "Never initiates a negative position. "
        "Root-class caveat: ETF-slice sign is era-unstable (robustness §3.2 of adjudication); "
        "per-class breakdowns reported once n≥30 per class."
    )
    return result


def _verdict_for_vanna_relief(t: dict) -> str:
    """Verdict for S-VANNA-RELIEF.

    Pre-registered primitives: {breach, clean, mfe21}.
    Primary beneficial direction: breach delta < 0 (LOWER stop-outs in flagged bucket).
    Secondary: clean + mfe21 reported honestly (no pre-judged direction for secondaries).
    A 'signal' verdict requires the PRIMARY breach delta to exclude 0 in the beneficial
    direction (breach < 0). Secondary deltas are evidence only (reported, not gating)."""
    if not t.get("ready"):
        return "building_history"
    b = t.get("breach")
    if b is None:
        return "building_history"
    breach_ok = b.get("excludes_zero") and b.get("delta") is not None and b["delta"] < 0
    return "signal" if breach_ok else "no_effect"


def _verdict_for_front_charm(t: dict) -> str:
    """Verdict for S-FRONT-CHARM (caution-only).

    Pre-registered primitives: {breach, clean, mfe21}.
    PRIMARY beneficial direction: breach delta > 0 (HIGHER stop-outs in flagged bucket —
    flag correctly identifies vol-exposed entries). CAUTION-ONLY per RO-3.
    A 'signal' verdict requires the PRIMARY breach delta to exclude 0 with delta > 0."""
    if not t.get("ready"):
        return "building_history"
    b = t.get("breach")
    if b is None:
        return "building_history"
    breach_ok = b.get("excludes_zero") and b.get("delta") is not None and b["delta"] > 0
    return "signal" if breach_ok else "no_effect"


def _compute_wc_coverage(df: pd.DataFrame) -> dict:
    """Compute coverage percentages for W-C and W-OVC stamp columns.  Returns dict of
    col -> (n_non_null, pct_float) for each column present."""
    tracked_cols = [
        # W-C columns
        "opt_ivspread_rel", "opt_skew", "opt_skew_5d_chg",
        "opt_opex_days", "opt_pin_risk",
        "opt_wall_dist_up_pct", "opt_wall_dist_down_pct",
        # W-OVC columns
        "opt_vanna_relief", "opt_front7_charm_share", "opt_root_class",
    ]
    n_total = max(len(df), 1)
    out = {}
    for col in tracked_cols:
        if col in df.columns:
            n_col = int(df[col].notna().sum())
            out[col] = (n_col, round(n_col / n_total * 100.0, 1))
        else:
            out[col] = (0, 0.0)
    return out


# ── gate assembly ────────────────────────────────────────────────────────────
def build_gate(df: pd.DataFrame) -> dict:
    """Run all four pre-registered bucket tests and assemble the gate.json payload.

    df is the stamped ledger. All tests speak only ledger primitives (A10). No verdict
    survives unless a test is ready (both buckets ≥ MIN_PER_BUCKET) — doctrine §2.3."""
    tests: dict[str, dict] = {}

    # S-DOI: informed-accumulation bucket — positive vs non-positive 5d call-OI slope
    if "opt_doi_slope_5d" in df.columns and df["opt_doi_slope_5d"].notna().any():
        doi = pd.to_numeric(df["opt_doi_slope_5d"], errors="coerce")
        # only rows with a stamped slope participate; NaN slope → excluded from both buckets
        sub = df[doi.notna()].copy()
        submask = pd.to_numeric(sub["opt_doi_slope_5d"], errors="coerce") > 0
        tests["S-DOI"] = _bucket_test(sub, submask, "S-DOI: doi_slope_5d > 0 (call-OI accumulating)")
    else:
        tests["S-DOI"] = {"bucket": "S-DOI", "n_cond": 0, "n_base": 0, "ready": False,
                          "note": "no stamped opt_doi_slope_5d yet (needs ≥5 prior chain days per name)"}

    # S-IVR: cheap-convexity bucket — LOW iv-rank vs HIGH. opt_iv_rank_252 is ALWAYS NULL
    # until the post-W1.1 backfill PR (A9), so this bucket is unpopulated by construction now.
    if "opt_iv_rank_252" in df.columns and df["opt_iv_rank_252"].notna().any():
        ivr = pd.to_numeric(df["opt_iv_rank_252"], errors="coerce")
        sub = df[ivr.notna()].copy()
        submask = pd.to_numeric(sub["opt_iv_rank_252"], errors="coerce") <= 0.30  # bottom-third rank
        tests["S-IVR"] = _bucket_test(sub, submask, "S-IVR: iv_rank_252 ≤ 0.30 (cheap convexity)")
    else:
        tests["S-IVR"] = {"bucket": "S-IVR", "n_cond": 0, "n_base": 0, "ready": False,
                          "note": "opt_iv_rank_252 is null until the post-W1.1 IV-backfill PR (ruling A9)"}

    # S-VOI: fresh-positioning bucket — voi_flag True vs False. Fast read on 5d + full on 21d clean.
    if "opt_voi_flag" in df.columns and df["opt_voi_flag"].notna().any():
        flag = df["opt_voi_flag"].astype("boolean")
        sub = df[flag.notna()].copy()
        submask = sub["opt_voi_flag"].astype("boolean") == True  # noqa: E712
        tests["S-VOI"] = _bucket_test(sub, submask.fillna(False),
                                      "S-VOI: voi_flag True (vol>prior-OI fresh positioning)")
        tests["S-VOI-fast"] = _voi_fast_test(df)
    else:
        tests["S-VOI"] = {"bucket": "S-VOI", "n_cond": 0, "n_base": 0, "ready": False,
                          "note": "no stamped opt_voi_flag yet"}
        tests["S-VOI-fast"] = {"bucket": "S-VOI-fast", "n_cond": 0, "n_base": 0, "ready": False}

    # S-WALL: raw-close wall-touch study (counts only; A10)
    tests["S-WALL"] = _wall_touch_study(df)

    # ── W-C additions: fire-conditioned buckets on new stamp cols ─────────────
    # S-IVSPREAD-F: positive ivspread_rel at fire (call richening vs puts = bullish tilt)
    tests["S-IVSPREAD-F"] = _ivspread_f_test(df)

    # S-SKEW_DECEL: skew in top cross-sectional tercile AND falling (de-escalation signal)
    tests["S-SKEW_DECEL"] = _skew_decel_test(df)

    # S-TOP_RISK: de-escalation family flag (caution-only: beneficial = flagged fires worse)
    tests["S-TOP_RISK"] = _top_risk_test(df)

    # S-PIN_RISK: OPEX proximity + long-gamma + near-wall flag
    tests["S-PIN_RISK"] = _pin_risk_test(df)

    # S-VOI2: stricter vol>OI burst — future stamp col, building_history until col exists
    tests["S-VOI2"] = _voi2_test(df)

    # ── W-OVC additions: vanna-relief and front-charm gate cells ─────────────
    # S-VANNA-RELIEF: holdability state (IV fell + top vanna_hedge tercile)
    tests["S-VANNA-RELIEF"] = _vanna_relief_test(df)

    # S-FRONT-CHARM: front-expiry charm concentration caution flag
    tests["S-FRONT-CHARM"] = _front_charm_test(df)

    # per-test verdicts (only bucket-delta tests carry a verdict; S-WALL is counts-only)
    _standard_tests = ("S-DOI", "S-IVR", "S-VOI", "S-IVSPREAD-F", "S-SKEW_DECEL", "S-VOI2")
    verdicts = {}
    for tid in _standard_tests:
        t = tests[tid]
        verdicts[tid] = _verdict_for_test(t) if "breach" in t else "building_history"
    # Caution tests use per-bucket verdict functions (different registered primitives):
    #   S-TOP_RISK: {breach, clean} — _verdict_for_top_risk
    #   S-PIN_RISK: {clean, mfe21} — _verdict_for_pin_risk (breach is NOT registered)
    #   S-VANNA-RELIEF: {breach primary, clean+mfe21 secondary} — _verdict_for_vanna_relief
    #   S-FRONT-CHARM: {breach primary (higher=beneficial), clean+mfe21 secondary} — caution-only
    verdicts["S-TOP_RISK"] = (
        _verdict_for_top_risk(tests["S-TOP_RISK"])
        if "breach" in tests["S-TOP_RISK"] else "building_history"
    )
    verdicts["S-PIN_RISK"] = (
        _verdict_for_pin_risk(tests["S-PIN_RISK"])
        if "clean" in tests["S-PIN_RISK"] else "building_history"
    )
    verdicts["S-VANNA-RELIEF"] = (
        _verdict_for_vanna_relief(tests["S-VANNA-RELIEF"])
        if "breach" in tests["S-VANNA-RELIEF"] else "building_history"
    )
    verdicts["S-FRONT-CHARM"] = (
        _verdict_for_front_charm(tests["S-FRONT-CHARM"])
        if "breach" in tests["S-FRONT-CHARM"] else "building_history"
    )

    _caution_tests = ("S-TOP_RISK", "S-PIN_RISK", "S-VANNA-RELIEF", "S-FRONT-CHARM")
    any_ready = any(
        tests[t].get("ready") for t in (*_standard_tests, *_caution_tests, "S-IVR", "S-VOI")
    )
    any_signal = any(v == "signal" for v in verdicts.values())

    # W-C + W-OVC coverage percentages (honest reporting)
    wc_col_coverage = _compute_wc_coverage(df)

    # evidence lines — LIVE per-bucket n counts (doctrine §2.3: n before any verdict)
    evidence: list[str] = []
    for tid in ("S-IVR", "S-DOI", "S-VOI"):
        t = tests[tid]
        if t.get("ready"):
            evidence.append(f"{tid}: n_cond={t['n_cond']} n_base={t['n_base']} → verdict={verdicts[tid]}")
        else:
            note = t.get("note", "")
            evidence.append(
                f"{tid}: building history (n_cond={t.get('n_cond', 0)}, n_base={t.get('n_base', 0)}; "
                f"need {MIN_PER_BUCKET}/bucket){(' — ' + note) if note else ''}")
    vf = tests["S-VOI-fast"]
    evidence.append(
        f"S-VOI-fast (5d): building history (n_cond={vf.get('n_cond', 0)}, "
        f"n_base={vf.get('n_base', 0)}; need {MIN_PER_BUCKET}/bucket)")
    w = tests["S-WALL"]
    evidence.append(
        f"S-WALL: {w['n_priced']}/{w['n_eligible']} eligible fires priced "
        f"(price_store_available={w['price_store_available']}); wall_touches={w['wall_touches']}, "
        f"fixed−5%_touches={w['fixed_stop_touches']}, wall_before_fixed={w['wall_before_fixed']}. "
        f"LIMITATION: {w['limitation']}")
    # W-C bucket evidence lines
    for tid in ("S-IVSPREAD-F", "S-SKEW_DECEL", "S-TOP_RISK", "S-PIN_RISK", "S-VOI2"):
        t = tests[tid]
        vdict = verdicts.get(tid, "building_history")
        if t.get("ready"):
            evidence.append(
                f"{tid}: n_cond={t['n_cond']} n_base={t['n_base']} → verdict={vdict}")
        else:
            note = t.get("note", "")
            evidence.append(
                f"{tid}: building history (n_cond={t.get('n_cond', 0)}, "
                f"n_base={t.get('n_base', 0)}; need {MIN_PER_BUCKET}/bucket)"
                f"{(' — ' + note) if note else ''}")
    # W-OVC bucket evidence lines
    for tid in ("S-VANNA-RELIEF", "S-FRONT-CHARM"):
        t = tests[tid]
        vdict = verdicts.get(tid, "building_history")
        if t.get("ready"):
            evidence.append(
                f"{tid}: n_cond={t['n_cond']} n_base={t['n_base']} → verdict={vdict}")
        else:
            note = t.get("note", "")
            evidence.append(
                f"{tid}: building history (n_cond={t.get('n_cond', 0)}, "
                f"n_base={t.get('n_base', 0)}; need {MIN_PER_BUCKET}/bucket)"
                f"{(' — ' + note) if note else ''}")
    # coverage lines (W-C + W-OVC)
    for col, (n_col, pct) in wc_col_coverage.items():
        evidence.append(f"stamp coverage [{col}]: {n_col}/{len(df)} rows ({pct:.1f}%)")

    return {
        "schema": "options_entry.gate.v3",
        "generated_at": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "scored": False,                       # ALWAYS false until a gate passes — machine, not a lever
        "status": "signal" if any_signal else ("scorable" if any_ready else "building_history"),
        "weight": 0.0,
        "horizons": [5, 10, 21],
        "min_per_bucket": MIN_PER_BUCKET,
        "n_ledger_rows": int(len(df)),
        "n_stamped_rows": int(df[STAMP_COLS].notna().any(axis=1).sum())
                          if all(c in df.columns for c in STAMP_COLS) else 0,
        "fdr_family": {
            "alpha": 0.10,
            "method": "Benjamini-Hochberg",
            "family_size": 28,
            "description": (
                "All fire-conditioned bucket tests × A10 primitives × live-accrual era (2026→). "
                "28 tests total (S-IVR×3, S-DOI×3, S-VOI×3, S-IVSPREAD-F×3, S-SKEW_DECEL×3, "
                "S-TOP_RISK×2, S-PIN_RISK×2, S-VOI2×3, S-VANNA-RELIEF×3, S-FRONT-CHARM×3). "
                "BH-FDR threshold for k-th ranked p-value: p_k <= (k/28) * 0.10. "
                "No verdict claims significance without clearing BH-FDR at alpha=0.10 over "
                "this full family. See OPTIONS_ALPHA_MASTERPLAN.md §4 amended BH-FDR statement "
                "(2026-07-06 OVC amendment: 22→28 tests). Prior W-C registered p-values "
                "unaffected (all building_history, no claimed p-values to re-check)."
            ),
        },
        "per_family_status": {
            "S-IVR": verdicts.get("S-IVR", "building_history"),
            "S-DOI": verdicts.get("S-DOI", "building_history"),
            "S-VOI": verdicts.get("S-VOI", "building_history"),
            "S-IVSPREAD-F": verdicts.get("S-IVSPREAD-F", "building_history"),
            "S-SKEW_DECEL": verdicts.get("S-SKEW_DECEL", "building_history"),
            "S-TOP_RISK": verdicts.get("S-TOP_RISK", "building_history"),
            "S-PIN_RISK": verdicts.get("S-PIN_RISK", "building_history"),
            "S-VOI2": verdicts.get("S-VOI2", "building_history"),
            "S-VANNA-RELIEF": verdicts.get("S-VANNA-RELIEF", "building_history"),
            "S-FRONT-CHARM": verdicts.get("S-FRONT-CHARM", "building_history"),
        },
        "tests": tests,
        "verdicts": verdicts,
        "evidence": evidence,
        "note": (
            "Pre-registered entry-quality gate (S-IVR/S-DOI/S-WALL/S-VOI + W-C: "
            "S-IVSPREAD-F/S-SKEW_DECEL/S-TOP_RISK/S-PIN_RISK/S-VOI2 + W-OVC: "
            "S-VANNA-RELIEF/S-FRONT-CHARM). Display/ledger-seed only until a bucket "
            "clears n≥30 AND a primitive delta's bootstrap CI excludes 0 (doctrine §2.3). "
            "Ledger primitives only (ruling A10). FDR family=28 tests, BH α=0.10. "
            "Never scored until a gate passes. "
            "S-TOP_RISK/S-PIN_RISK/S-FRONT-CHARM are caution-only: beneficial direction = "
            "flagged fires worse/higher-vol (correctly de-escalates). "
            "S-VANNA-RELIEF is caution-only: holdability context only, not an entry originator. "
            "Never initiates a negative position (RO-3)."
        ),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--ledger", default=str(LEDGER_PATH))
    args = ap.parse_args()

    ledger = Path(args.ledger)
    GATE_DIR.mkdir(parents=True, exist_ok=True)

    if not ledger.exists():
        gate = {
            "schema": "options_entry.gate.v1",
            "generated_at": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "scored": False, "status": "building_history", "weight": 0.0,
            "min_per_bucket": MIN_PER_BUCKET, "n_ledger_rows": 0,
            "evidence": ["ledger absent — no fires stamped yet"],
            "note": "board ledger not found; gate awaits first stamped rows",
        }
    else:
        df = pd.read_parquet(ledger)
        gate = build_gate(df)

    GATE_PATH.write_text(json.dumps(gate, indent=1, default=str))
    if not args.quiet:
        print(f"[options_entry] wrote {GATE_PATH.relative_to(config.data_dir().parent)} "
              f"(scored={gate['scored']}, status={gate['status']})")
        for line in gate.get("evidence", []):
            print(f"  · {line}")


if __name__ == "__main__":
    main()
