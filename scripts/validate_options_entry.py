"""scripts/validate_options_entry.py — pre-registered options-entry-quality gate.

Options Alpha program W1.3 (research/OPTIONS_ALPHA_MASTERPLAN.md §4, rulings A6/A9/A10).

THE KEYSTONE MACHINE, NOT A RESULT. This gate answers — once enough fires accrue — the one
question the desk cares about:

    "Does options context reduce stop-outs / dead money and improve clean liftoffs on entries
     the price thesis already likes?"

It reads the options-state-stamped US board ledger (``data/us_board_ledger/retro_grades.parquet``,
stamped by scripts/stamp_options_state.py) and runs the four pre-registered bucket tests from
§4 of the masterplan, speaking ONLY in ledger primitives (ruling A10):

  * ``post_cushion_breach``            — 21d stop-out proxy (True/False/None)
  * ``terminal_state_clean8_21``       — 21d clean-liftoff label (CLEAN_LIFTOFF vs the rest)
  * ``fwd_mfe_21`` / ``fwd_mfe_5``     — max favourable excursion
  * ``fwd_ret_5``                       — fast 5d return (S-VOI fast read)

There is NO stop5 / clean15@5d / absolute-MAE primitive; the wall study (S-WALL) computes
absolute-price wall touches directly from ``data/massive_stock_day/`` raw closes vs the stamped
``opt_wall_down`` level (close-path — UNDERSTATES intraday touches; documented in the evidence).

Each test is a conditioned-vs-unconditioned delta with a bootstrap CI. HARD RULE (doctrine
§2.3): NO verdict — no effect-size claim — until n ≥ ``MIN_PER_BUCKET`` fires in EACH condition
bucket. Until then the gate emits ``scored:false`` / ``status:"building_history"`` with the
LIVE per-bucket n counts. With ~13 board dates × 18 days of options history, every bucket is far
under threshold today; the machine ships so no future fire goes unstamped or ungraded.

Output: ``data/options_entry/gate.json`` (schema ``options_entry.gate.v1``, mirroring the
``gex.gate.v1`` style of ``data/gex/gate.json``).

Only recomputes counts / verdicts — a verdict flip requires the pre-registered thresholds,
never a code edit. Idempotent, resilient.
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

    # per-test verdicts (only bucket-delta tests carry a verdict; S-WALL is counts-only for now)
    verdicts = {}
    for tid in ("S-DOI", "S-IVR", "S-VOI"):
        t = tests[tid]
        verdicts[tid] = _verdict_for_test(t) if "breach" in t else "building_history"

    any_ready = any(tests[t].get("ready") for t in ("S-DOI", "S-IVR", "S-VOI"))
    any_signal = any(v == "signal" for v in verdicts.values())

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

    return {
        "schema": "options_entry.gate.v1",
        "generated_at": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "scored": False,                       # ALWAYS false in W1.3 — machine, not a lever
        "status": "signal" if any_signal else ("scorable" if any_ready else "building_history"),
        "weight": 0.0,
        "horizons": [5, 10, 21],
        "min_per_bucket": MIN_PER_BUCKET,
        "n_ledger_rows": int(len(df)),
        "n_stamped_rows": int(df[STAMP_COLS].notna().any(axis=1).sum())
                          if all(c in df.columns for c in STAMP_COLS) else 0,
        "tests": tests,
        "verdicts": verdicts,
        "evidence": evidence,
        "note": ("Pre-registered entry-quality gate (S-IVR/S-DOI/S-WALL/S-VOI). Display/ledger-seed "
                 "only until a bucket clears n≥30 AND a primitive delta's bootstrap CI excludes 0 "
                 "(doctrine §2.3). Ledger primitives only (ruling A10). Never scored in W1.3."),
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
