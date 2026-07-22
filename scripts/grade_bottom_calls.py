"""Bottom Ledger — nightly-only advancer for the policy-free bottom-calling instrument.

OPERATOR OBJECTIVE (charter 2026-07-22): "pinpoint bottom picks — that's the main objective
of Prophet." This advancer is Phase 1 of the Bottom Ledger (design:
research/signal_engine/BOTTOM_LEDGER_DESIGN.md, ratified on research PR #3182). It is a
LEARNING instrument only — no exits, no stops, no user-facing surface changes, no Episode
Record (that is Phase 2). Grading semantics are the frozen ones in engine/bottom_ruler.py,
which replicate research/signal_engine/bottom_ruler_study.py exactly.

Three stages, run nightly (`--nightly`, the cron/DAG entry point):

  ACCRUE  append one row per bottom-class flag, idempotent by (flag_date, ticker, source):
            (a) us_board_ledger buy-lane rows            -> source="board_buy"
            (b) us_board_ledger watch-lane rows carrying a `washout` payload
                (added by feat/washout-watch-wait-lane; tolerated absent today)
                                                          -> source="washout_watch"
            (c) Prophet plans (site/prophet/plans/*.json) -> source="prophet_plan"
          Store: data/bottom_ledger/rows.parquet (atomic write, append-only, deterministic
          order). Committed by nightly's `git add data/` like every sibling forward ledger
          (data/us_board_ledger, data/risk_radar, ...) — that persistence is how cohorts
          accrue night to night; only intraday lanes discard data/ writes (CLAUDE.md), and the
          initial build PR carries no data/ rows. This advancer writes ONLY this store, the
          site/ emit, and (under --baseline) the calibration file — NO mutation of any other
          store on any path (MM_DATA_GUARD lesson).

  MATURE  rows with flag_date + 60 trading days <= as_of and no grade yet are graded ONCE via
          engine.bottom_ruler.grade_call using price history (data/stocks/<T>.parquet with
          high/low preferred; else data/yahoo/<T>.parquet close, close_only basis). Grades are
          FROZEN — a graded row is never regraded (one-grader law SA-R14).

  EMIT    display artifact site/factordata/us_bottom_ledger.json (schema bottom_ledger/v1):
          counts + cohort tables by source x lane/rung tags + baseline_ref + display-tier
          reliability wording. Nulls printed while nothing is matured. First live maturities
          land ~2026-09-25 (H=60 from the first 2026-06-30 snapshots); the committed panel
          baseline (calibration/bottom_ruler_baseline.json) carries the learning until then.

NIGHTLY-ONLY LAW (house law: nightly is the SOLE advancer of forward ledgers). The forward
advance — appending NEW flag rows and freezing NEW grades into the store — happens ONLY under
`--nightly`, mirroring scripts/grade_us_board.py where the snapshot append lives inside
`if args.nightly:`. Without `--nightly` the script reads the existing store and re-emits the
display artifact only (idempotent), discarding no forward state — matching CLAUDE.md "intraday
lanes discard data/ writes". `--force-local --out-dir DIR` runs the full ACCRUE/MATURE/EMIT
into a scratch DIR (never the real store) for safe non-nightly testing.

Baseline (`--baseline`): reproduce the panel replay per-rung table from bottom_ruler_study.py
(full history + since-2018) and write calibration/bottom_ruler_baseline.json — the committed
yardstick live cohorts are compared against as they mature. Deterministic output.

DISPLAY-TIER throughout; the word "validated" stays out of user-facing text; nulls printed.
This advancer confers NO ranking/sizing/gate authority.

Run (nightly / DAG):   python -m scripts.grade_bottom_calls --nightly
Run (regen baseline):  python -m scripts.grade_bottom_calls --baseline
Run (safe local test): python -m scripts.grade_bottom_calls --force-local --out-dir /tmp/bl
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import bottom_ruler as BR  # noqa: E402

# --------------------------------------------------------------------------- #
# paths
# --------------------------------------------------------------------------- #
SNAPSHOTS_JSONL = ROOT / "data" / "us_board_ledger" / "snapshots.jsonl"
PROPHET_PLANS_DIR = ROOT / "site" / "prophet" / "plans"
STOCKS_DIR = ROOT / "data" / "stocks"
YAHOO_DIR = ROOT / "data" / "yahoo"

LEDGER_DIR = ROOT / "data" / "bottom_ledger"
ROWS_PARQUET = LEDGER_DIR / "rows.parquet"
EMIT_JSON = ROOT / "site" / "factordata" / "us_bottom_ledger.json"
BASELINE_JSON = ROOT / "calibration" / "bottom_ruler_baseline.json"

SCHEMA = "bottom_ledger/v1"
LEDGER_BORN = "2026-06-30"           # first snapshot as_of
FIRST_MATURITY_EST = "2026-09-25"    # H=60 from 2026-06-30 (approx, business days)

# accrual identity — a flag is unique on (flag_date, ticker, source).
DEDUP_KEYS = ["flag_date", "ticker", "source"]

# grade fields written at maturity (one-grader law: frozen once, never regraded).
GRADE_FIELDS = ["prox", "t_off", "undercut", "undercut_class", "mfe60", "mae60", "fwd60", "basis"]

# stable column order for the parquet store (deterministic row/column layout).
STORE_COLS = [
    "flag_date", "ticker", "source", "lane", "rung", "tier",
    "conviction", "act", "washout_tier", "weeks_at_floor", "late_pct",
    "graded", "grade_asof",
] + GRADE_FIELDS


# --------------------------------------------------------------------------- #
# atomic writers (house law: tmp-file + os.replace, never open('w') truncation)
# --------------------------------------------------------------------------- #
def _atomic_write_json(path: Path, doc: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(doc, ensure_ascii=False, indent=1, default=str)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        os.write(fd, payload.encode("utf-8"))
    finally:
        os.close(fd)
    os.replace(tmp, path)


def _atomic_write_parquet(path: Path, df: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".parquet.tmp")
    os.close(fd)
    try:
        df.to_parquet(tmp, index=False)
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            try:
                os.unlink(tmp)
            except OSError:
                pass
        raise


# --------------------------------------------------------------------------- #
# price readers — data/stocks (OHLC, preferred) then data/yahoo (close_only)
# --------------------------------------------------------------------------- #
def _read_prices(ticker: str) -> tuple[pd.Series, pd.Series | None, pd.Series | None] | None:
    """Return (close, high, low) for a ticker. high/low are None on the close_only path.

    Prefer data/stocks/<T>.parquet (dividend-unadjusted OHLC). Fall back to
    data/yahoo/<T>.parquet (close column; no high/low → close_only grade). Read-only: never
    writes (MM_DATA_GUARD — reader APIs must never persist).
    """
    sp = STOCKS_DIR / f"{ticker}.parquet"
    if sp.exists():
        try:
            df = pd.read_parquet(sp)
            if {"close", "high", "low"} <= set(df.columns):
                df.index = pd.to_datetime(df.index)
                df = df.sort_index()
                return df["close"], df["high"], df["low"]
        except Exception:
            pass
    yp = YAHOO_DIR / f"{ticker}.parquet"
    if yp.exists():
        try:
            df = pd.read_parquet(yp)
            col = "close" if "close" in df.columns else df.columns[0]
            s = df[col]
            s.index = pd.to_datetime(s.index)
            s = s.sort_index()
            return s, None, None
        except Exception:
            pass
    return None


# --------------------------------------------------------------------------- #
# ACCRUE — collect bottom-class flags from the three sources
# --------------------------------------------------------------------------- #
def _read_snapshots() -> list[dict]:
    if not SNAPSHOTS_JSONL.exists():
        return []
    rows = []
    for line in SNAPSHOTS_JSONL.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def _flag_row(**kw: Any) -> dict:
    """Build a store row with every column present (missing → None), grade fields null."""
    row = {c: None for c in STORE_COLS}
    row["graded"] = False
    row.update(kw)
    return row


def collect_flags() -> list[dict]:
    """Accrue bottom-class flags from board snapshots + washout WAIT payloads + Prophet plans.

    Tolerates snapshot-shape drift: buy/watch rows may lack `lane` (old snapshots → "unknown"),
    watch rows may lack a `washout` payload (in-flight PR feat/washout-watch-wait-lane not yet
    landed → those rows are simply not washout flags today). Deterministic: rows are emitted in
    a stable (flag_date, source, ticker) order by the caller's sort.
    """
    flags: list[dict] = []

    # (a)+(b) board snapshots: buy-lane -> board_buy; watch-lane w/ washout payload -> washout_watch
    for snap in _read_snapshots():
        as_of = snap.get("as_of")
        if not as_of:
            continue
        for r in snap.get("buy", []) or []:
            tkr = r.get("ticker")
            if not tkr:
                continue
            # lane taxonomy (P2.4): carry lane if present; old snapshots lack it -> "unknown".
            lane = r.get("lane") or "unknown"
            conv = r.get("conviction")
            conv_score = conv.get("score") if isinstance(conv, dict) else None
            sig = r.get("signal")
            tier = None
            if isinstance(sig, dict):
                tier = sig.get("tier_cascade") or sig.get("tier")
            flags.append(_flag_row(
                flag_date=as_of, ticker=tkr, source="board_buy",
                lane=lane, tier=tier, conviction=conv_score,
            ))
        for r in snap.get("watch", []) or []:
            tkr = r.get("ticker")
            if not tkr:
                continue
            wash = r.get("washout")
            if not isinstance(wash, dict):
                continue      # not a washout WAIT flag (payload not present yet)
            flags.append(_flag_row(
                flag_date=as_of, ticker=tkr, source="washout_watch",
                lane=r.get("lane") or "washout",
                washout_tier=wash.get("tier"),
                weeks_at_floor=wash.get("weeks_at_floor"),
                late_pct=wash.get("late_pct"),
            ))

    # (c) Prophet plans -> prophet_plan; flag_date = signal_date.
    if PROPHET_PLANS_DIR.exists():
        for p in sorted(glob.glob(str(PROPHET_PLANS_DIR / "*.json"))):
            try:
                d = json.loads(Path(p).read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            sd = d.get("signal_date")
            tkr = d.get("asset") or d.get("ticker")
            if not sd or not tkr:
                continue
            flags.append(_flag_row(
                flag_date=sd, ticker=tkr, source="prophet_plan",
                lane=(d.get("direction") or "").lower() or None,
                conviction=d.get("_conviction_score"),
                act=d.get("_act_level"),
            ))
    return flags


# --------------------------------------------------------------------------- #
# store I/O + idempotent merge
# --------------------------------------------------------------------------- #
def _empty_store() -> pd.DataFrame:
    return pd.DataFrame({c: pd.Series(dtype="object") for c in STORE_COLS})


def _load_store(rows_path: Path) -> pd.DataFrame:
    if rows_path.exists():
        try:
            df = pd.read_parquet(rows_path)
            for c in STORE_COLS:
                if c not in df.columns:
                    df[c] = None
            return df[STORE_COLS]
        except Exception:
            return _empty_store()
    return _empty_store()


def _sort_store(df: pd.DataFrame) -> pd.DataFrame:
    """Deterministic append-only order: (flag_date, source, ticker)."""
    if df.empty:
        return df
    return (df.sort_values(["flag_date", "source", "ticker"], kind="stable")
              .reset_index(drop=True))


def merge_flags(store: pd.DataFrame, flags: list[dict]) -> pd.DataFrame:
    """Idempotent accrual: append only flags whose (flag_date,ticker,source) is not already in
    the store. Existing rows (including their frozen grades) are left untouched."""
    if not flags:
        return _sort_store(store)
    have = set()
    if not store.empty:
        have = set(map(tuple, store[DEDUP_KEYS].astype(object).values.tolist()))
    fresh = []
    seen_new: set = set()
    for f in flags:
        key = tuple(f[k] for k in DEDUP_KEYS)
        if key in have or key in seen_new:
            continue
        seen_new.add(key)
        fresh.append(f)
    if not fresh:
        return _sort_store(store)
    fresh_df = pd.DataFrame(fresh)[STORE_COLS]
    merged = pd.concat([store, fresh_df], ignore_index=True) if not store.empty else fresh_df
    return _sort_store(merged)


# --------------------------------------------------------------------------- #
# MATURE — grade rows whose window has closed, ONCE, frozen
# --------------------------------------------------------------------------- #
def mature_rows(store: pd.DataFrame, as_of: pd.Timestamp) -> tuple[pd.DataFrame, int]:
    """Grade every ungraded row whose flag_date + H trading days has closed on/before `as_of`.

    A row is graded ONCE and then frozen (graded=True); already-graded rows are skipped. The
    maturity gate is enforced by grade_call itself (it returns None when fewer than H bars
    follow the signal in the price series). Returns (store, n_newly_graded)."""
    if store.empty:
        return store, 0
    price_cache: dict[str, Any] = {}
    n_graded = 0
    for idx in store.index:
        if bool(store.at[idx, "graded"]):
            continue
        tkr = store.at[idx, "ticker"]
        fdate = store.at[idx, "flag_date"]
        if tkr not in price_cache:
            price_cache[tkr] = _read_prices(tkr)
        px = price_cache[tkr]
        if px is None:
            continue
        close, high, low = px
        # Cheap pre-check: only attempt grading once as_of is well past flag+H calendar days.
        # grade_call is the authority on maturity (H *trading* bars must follow); this just
        # avoids grading rows that plainly cannot be mature yet.
        try:
            fts = pd.Timestamp(fdate)
        except (ValueError, TypeError):
            continue
        if as_of < fts + pd.Timedelta(days=BR.H):     # < H calendar days → cannot be H trading days
            continue
        grade = BR.grade_call(close, high, low, fdate)
        if grade is None:
            continue
        for k in GRADE_FIELDS:
            store.at[idx, k] = grade[k]
        store.at[idx, "graded"] = True
        store.at[idx, "grade_asof"] = str(as_of.date())
        n_graded += 1
    return store, n_graded


# --------------------------------------------------------------------------- #
# EMIT — display artifact
# --------------------------------------------------------------------------- #
_RELIABILITY = {
    "tier": "display",
    "en": ("Display-tier learning instrument. Measures how close bottom-class flags land to the "
           "eventual low and whether the called floor holds — policy-free (no exits/stops). It "
           "confers no ranking, sizing, or trading authority. Live cohorts are compared against "
           "the committed panel baseline as they mature; first maturities land ~2026-09-25."),
    "zh": ("展示层学习工具。衡量“抄底类”信号距最终低点的接近度以及所判定的底部是否守住 — 不含任何策略"
           "（无止损/离场）。不赋予任何排名、仓位或交易权限。随着样本成熟，实时队列将与已提交的面板基线"
           "比较；首批成熟约在 2026-09-25。"),
    "one_grader_law": "grades are computed once at maturity and never recomputed (SA-R14)",
}


def _grades_from_store(store: pd.DataFrame) -> list[dict]:
    """Matured rows as grade dicts carrying source/lane/rung tags for cohorting."""
    if store.empty:
        return []
    matured = store[store["graded"] == True]  # noqa: E712
    out = []
    for _, r in matured.iterrows():
        d = {k: (None if pd.isna(r[k]) else r[k]) for k in GRADE_FIELDS}
        d["source"] = r["source"]
        d["lane"] = r["lane"] if not pd.isna(r["lane"]) else "unknown"
        d["rung"] = r["rung"] if not pd.isna(r["rung"]) else None
        out.append(d)
    return out


def build_emit(store: pd.DataFrame, as_of: pd.Timestamp) -> dict:
    """Assemble the site/factordata/us_bottom_ledger.json display doc (schema bottom_ledger/v1).

    Nulls printed while nothing is matured: cohorts is an empty list, the median/rate summaries
    are null, and reliability language states the display-tier + first-maturity estimate."""
    n_total = int(len(store))
    n_matured = int((store["graded"] == True).sum()) if not store.empty else 0  # noqa: E712
    n_accruing = n_total - n_matured

    # per-source accrual counts (deterministic).
    by_source: dict[str, int] = {}
    if not store.empty:
        for src, cnt in store["source"].value_counts().sort_index().items():
            by_source[str(src)] = int(cnt)

    grades = _grades_from_store(store)
    cohorts = BR.cohort_table(grades, by=["source", "lane"]) if grades else []

    # headline summary (null until matured).
    summary: dict[str, Any] = {"pin5": None, "held_pct": None, "prox_med": None}
    if grades:
        summary["pin5"] = round(sum(1 for g in grades if BR.pinpoint(g)) / len(grades), 4)
        held = sum(1 for g in grades if BR._is_held(g)) / len(grades)
        summary["held_pct"] = round(held, 4)
        proxes = [g["prox"] for g in grades if g.get("prox") is not None]
        summary["prox_med"] = round(float(np.median(proxes)), 4) if proxes else None

    return {
        "schema": SCHEMA,
        "as_of": str(as_of.date()),
        "ledger_born": LEDGER_BORN,
        "maturity_state": "accruing" if n_matured == 0 else "maturing",
        "n_accruing": n_accruing,
        "n_matured": n_matured,
        "first_maturity_est": FIRST_MATURITY_EST if n_matured == 0 else None,
        "accrual_by_source": by_source,
        "summary": summary,
        "cohorts": cohorts,
        "baseline_ref": "calibration/bottom_ruler_baseline.json",
        "reliability": _RELIABILITY,
    }


# --------------------------------------------------------------------------- #
# BASELINE — panel replay per-rung table (reproduces bottom_ruler_study.py)
# --------------------------------------------------------------------------- #
# frozen study constants for event generation (bottom_ruler_study.py lines 45-49).
_H, _PRE, _DEDUP = 60, 10, 20
_FLOOR_D, _FLOOR_WKS, _FLOOR_WIN = 10.0, 3, 6
_RUNGS = ("W0_thrust", "W1_stoch2d", "W2_macd2d", "W3_1w", "W4_2w", "CASCADE_P")


def _study_events_for(df: pd.DataFrame) -> list[dict]:
    """Reproduce bottom_ruler_study.py::events_for exactly (all six rungs).

    Kept in-file (rather than importing the research script, which is not committed here) so the
    committed baseline is reproducible from this repo alone. The grade arithmetic below is the
    same as engine.bottom_ruler.grade_call — cross-checked field-for-field."""
    from engine.confluence_tiers import (  # local import: heavy module
        CONF_W, OB, OS, RSI_LEN, BUY_RSI_MAX,
        _tf_bars, _stoch_rsi_kd, _rsi_macd, _xup, _since, _to_daily, rsi,
    )
    c = df["close"].dropna()
    if len(c) < 340:
        return []
    di = c.index
    hi = df["high"].reindex(di)
    lo = df["low"].reindex(di)
    vol = df["volume"].reindex(di) if "volume" in df else None

    wk = c.resample("W-FRI").last().dropna()
    kw, dw = _stoch_rsi_kd(wk)
    floored = (dw <= _FLOOR_D).rolling(_FLOOR_WIN, min_periods=_FLOOR_WKS).sum() >= _FLOOR_WKS
    state_d = floored.shift(1).reindex(di, method="ffill").fillna(False).astype(bool)

    ret1 = c.pct_change()
    atrp = (hi - lo).rolling(20).mean() / c.shift(1)
    rngpos = ((c - lo) / (hi - lo).replace(0, np.nan)).fillna(1.0)
    thrust = (ret1 >= np.maximum(0.05, 1.5 * atrp)) & (rngpos >= 0.6)
    if vol is not None and vol.notna().sum() > 100:
        thrust &= (vol >= 1.5 * vol.rolling(20).mean())

    sm, smk = _tf_bars(c, 2)
    k2, d2 = _stoch_rsi_kd(sm)
    st2 = _xup(k2, d2) & (d2.rolling(CONF_W).min() < OS)
    m2, s2 = _rsi_macd(sm)
    mb2_d = _to_daily(_xup(m2, s2).fillna(False), smk, di, "event")

    ss3, sk3 = _tf_bars(c, 3)
    k3, d3 = _stoch_rsi_kd(ss3)
    recent3_d = _to_daily((_since(_xup(k3, d3)) <= CONF_W).fillna(False), sk3, di).fillna(False)
    fromos3_d = _to_daily((d3.rolling(CONF_W).min() < OS).fillna(False), sk3, di).fillna(False)
    r14_d = _to_daily(rsi(ss3, RSI_LEN), sk3, di)
    m3_d, s3_d = _to_daily(_rsi_macd(ss3)[0], sk3, di), _to_daily(_rsi_macd(ss3)[1], sk3, di)
    k3_d, d3_d = _to_daily(k3, sk3, di), _to_daily(d3, sk3, di)
    wm, ws = _rsi_macd(wk)
    wbull_d = (wm >= ws).shift(1).reindex(di, method="ffill").fillna(False).astype(bool)
    confirm3 = (wbull_d | fromos3_d)
    rsi_ok = (r14_d < BUY_RSI_MAX).fillna(False)
    not_topped = ~((k3_d >= OB) | (d3_d >= OB) | (k3_d < d3_d) | (m3_d < s3_d))
    cascade_p = (mb2_d & recent3_d & confirm3 & rsi_ok & not_topped).fillna(False)

    wx = _xup(kw, dw)
    wk2 = c.resample("2W-FRI").last().dropna()
    k2w, d2w = _stoch_rsi_kd(wk2)

    ev = {
        "W0_thrust": (thrust.fillna(False) & state_d),
        "W1_stoch2d": (_to_daily(st2.fillna(False), smk, di, "event") & state_d),
        "W2_macd2d": (mb2_d & state_d),
        "W3_1w": (wx.reindex(di).fillna(False).astype(bool) & state_d),
        "W4_2w": (_xup(k2w, d2w).reindex(di).fillna(False).astype(bool) & state_d),
        "CASCADE_P": cascade_p,
    }

    low20 = lo.rolling(20, min_periods=5).min()
    cn = c.to_numpy()
    hn = hi.fillna(c).to_numpy()
    ln = lo.fillna(c).to_numpy()
    n = len(cn)
    out: list[dict] = []
    for rung in _RUNGS:
        mask = ev[rung].to_numpy()
        last = -10**9
        for i in np.where(mask)[0]:
            if i - last <= _DEDUP:
                continue
            if i + _H >= n or i - _PRE < 0:
                continue
            F = float(low20.iloc[i])
            if not np.isfinite(F) or F <= 0:
                continue
            last = i
            f = i + 1
            fill = cn[f]
            w_lo = ln[i - _PRE: i + _H + 1]
            trough = float(np.nanmin(w_lo))
            t_off = int(np.nanargmin(w_lo)) - _PRE
            fwd_lo = ln[f: i + _H + 1]
            undercut = max(0.0, 1.0 - float(np.nanmin(fwd_lo)) / F)
            mfe = float(np.nanmax(hn[f + 1: i + _H + 1]) / fill - 1.0)
            mae = float(np.nanmin(ln[f + 1: i + _H + 1]) / fill - 1.0)
            out.append({
                "rung": rung, "date": str(di[i].date()),
                "prox": float(cn[i] / trough - 1.0),
                "t_off": t_off, "undercut": undercut,
                "mfe60": mfe, "mae60": mae,
                "fwd60": float(cn[i + _H] / fill - 1.0),
            })
    return out


def _rung_table(R: pd.DataFrame) -> list[dict]:
    """Per-rung aggregate matching bottom_ruler_study.py::table (deterministic RUNGS order)."""
    rows = []
    for rung in _RUNGS:
        d = R[R.rung == rung]
        if not len(d):
            continue
        rows.append({
            "rung": rung,
            "n": int(len(d)),
            "names": int(d.ticker.nunique()),
            "prox_med_pct": round(100 * float(d.prox.median()), 1),
            "pin5_pct": round(100 * float((d.prox <= 0.05).mean()), 1),
            "t_off_med": int(d.t_off.median()),
            "held_pct": round(100 * float((d.undercut <= 0.005).mean()), 1),
            "probe3_pct": round(100 * float((d.undercut <= 0.03).mean()), 1),
            "broke10_pct": round(100 * float((d.undercut > 0.10).mean()), 1),
            "mfe60_med_pct": round(100 * float(d.mfe60.median()), 1),
            "mae60_med_pct": round(100 * float(d.mae60.median()), 1),
            "fwd60_med_pct": round(100 * float(d.fwd60.median()), 1),
        })
    return rows


def build_baseline() -> dict:
    """Reproduce the panel replay (full history + since-2018) as the committed baseline doc.

    Deterministic: files are sorted, RUNGS order is fixed, all floats are rounded to 1dp. This
    is the yardstick live cohorts are compared against as they mature."""
    rows: list[dict] = []
    files = sorted(glob.glob(str(STOCKS_DIR / "*.parquet")))
    for p in files:
        try:
            df = pd.read_parquet(p)
        except Exception:
            continue
        if not {"close", "high", "low"} <= set(df.columns):
            continue
        for r in _study_events_for(df):
            r["ticker"] = Path(p).stem
            rows.append(r)
    R = pd.DataFrame(rows)
    if not len(R):
        return {"schema": "bottom_ruler_baseline/v1", "error": "no events"}
    R["date"] = pd.to_datetime(R["date"])
    return {
        "schema": "bottom_ruler_baseline/v1",
        "generated_from": "scripts/grade_bottom_calls.py --baseline",
        "regen_command": "python -m scripts.grade_bottom_calls --baseline",
        "replicates": "research/signal_engine/bottom_ruler_study.py (design PR #3182)",
        "panel": {
            "n_files": len(files),
            "n_events": int(len(R)),
            "date_min": str(R.date.min().date()),
            "date_max": str(R.date.max().date()),
        },
        "grading": {
            "H": _H, "PRE": _PRE, "floor_win": 20,
            "undercut_classes": {"held": "<=0.5%", "probe": "<=3%", "deep": "<=10%", "broke": ">10%"},
            "prox": "signal close vs eventual trough low in [t-10,t+60]; pin5 = within 5%",
            "note": "matured events only; frozen grades; MFE/MAE/fwd60 vs next-close fill",
        },
        "reliability_tier": "display",
        "full_history": _rung_table(R),
        "since_2018": _rung_table(R[R.date >= "2018-01-01"]),
    }


def _print_baseline_table(doc: dict) -> None:
    for label, key in [("FULL HISTORY", "full_history"), ("SINCE 2018", "since_2018")]:
        print(f"\n== {label} (matured events only) ==")
        hdr = (f"{'rung':10} {'n':>6} {'names':>5} {'prox%':>6} {'pin5%':>6} {'t_off':>6} "
               f"{'held%':>6} {'probe%':>6} {'brk%':>6} {'MFE%':>6} {'MAE%':>6} {'fwd%':>6}")
        print(hdr)
        for r in doc.get(key, []):
            print(f"{r['rung']:10} {r['n']:>6} {r['names']:>5} {r['prox_med_pct']:>6.1f} "
                  f"{r['pin5_pct']:>6.1f} {r['t_off_med']:>6d} {r['held_pct']:>6.1f} "
                  f"{r['probe3_pct']:>6.1f} {r['broke10_pct']:>6.1f} {r['mfe60_med_pct']:>6.1f} "
                  f"{r['mae60_med_pct']:>6.1f} {r['fwd60_med_pct']:>6.1f}")


# --------------------------------------------------------------------------- #
# pipeline
# --------------------------------------------------------------------------- #
def run_pipeline(rows_path: Path, emit_path: Path, *, accrue: bool, as_of: pd.Timestamp,
                 quiet: bool = False) -> dict:
    """ACCRUE (if nightly/forced) → MATURE → EMIT. Returns the emitted doc.

    `accrue` gates the forward advance (new flag rows + new frozen grades). When False the
    store is read and the display artifact is re-emitted only — no forward state is written."""
    store = _load_store(rows_path)
    n_before = len(store)

    if accrue:
        flags = collect_flags()
        store = merge_flags(store, flags)
        n_new = len(store) - n_before
        store, n_graded = mature_rows(store, as_of)
        _atomic_write_parquet(rows_path, store)
        if not quiet:
            print(f"[accrue] +{n_new} new flags (store {n_before}->{len(store)}); "
                  f"[mature] +{n_graded} newly graded rows -> {rows_path.name}")
    else:
        store = _sort_store(store)
        if not quiet:
            print(f"[read-only] store {len(store)} rows (no forward advance)")

    doc = build_emit(store, as_of)
    _atomic_write_json(emit_path, doc)
    if not quiet:
        print(f"[emit] n_accruing={doc['n_accruing']} n_matured={doc['n_matured']} "
              f"cohorts={len(doc['cohorts'])} -> {emit_path.name}")
    return doc


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--nightly", action="store_true",
                    help="forward-advance the ledger: accrue new flags + freeze new grades "
                         "(the SOLE advancer; cron/DAG entry point)")
    ap.add_argument("--baseline", action="store_true",
                    help="regenerate calibration/bottom_ruler_baseline.json from the panel and exit")
    ap.add_argument("--force-local", action="store_true",
                    help="run the full accrue/mature/emit into --out-dir (safe non-nightly test; "
                         "never writes the real store)")
    ap.add_argument("--out-dir", default=None,
                    help="scratch dir for --force-local (default: a temp dir)")
    ap.add_argument("--as-of", default=None, help="override as_of date (YYYY-MM-DD); default today")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    as_of = pd.Timestamp(args.as_of) if args.as_of else pd.Timestamp.utcnow().normalize()

    if args.baseline:
        doc = build_baseline()
        _atomic_write_json(BASELINE_JSON, doc)
        if not args.quiet:
            print(f"[baseline] panel {doc.get('panel', {})} -> {BASELINE_JSON.relative_to(ROOT)}")
            _print_baseline_table(doc)
        return

    if args.force_local:
        out_dir = Path(args.out_dir) if args.out_dir else Path(tempfile.mkdtemp(prefix="bottom_ledger_"))
        out_dir.mkdir(parents=True, exist_ok=True)
        rows_path = out_dir / "rows.parquet"
        emit_path = out_dir / "us_bottom_ledger.json"
        if not args.quiet:
            print(f"[force-local] scratch dir = {out_dir} (real store untouched)")
        run_pipeline(rows_path, emit_path, accrue=True, as_of=as_of, quiet=args.quiet)
        return

    # default / --nightly: emit always; forward-advance ONLY under --nightly.
    run_pipeline(ROWS_PARQUET, EMIT_JSON, accrue=bool(args.nightly), as_of=as_of, quiet=args.quiet)


if __name__ == "__main__":
    main()
