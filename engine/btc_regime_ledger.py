"""BTC Regime Ledger — P4 falsifiable, auto-demoting regime ledger (CONTEXT-ONLY).

Tracks the live regime stance forward and grades it deterministically once the
90-day horizon matures. A tier whose falsifier trips is MECHANICALLY demoted: its
weight is zeroed in the display scorecard going forward. Nothing in the live
sizing or allocation path reads this file — it is context metadata only.

API:
    stamp(regime, asof=None)        → append one row/day to regime_ledger.jsonl
    score(asof=None)                → grade all matured rows (≥90d old)
    falsifier_status(asof=None)     → per-tier FRAGILE/OK/INELIGIBLE_PENDING + writes
                                       data/vector/regime_falsifiers.json
    render_summary(asof=None)       → dict for dashboard consumption

Ledger file:  data/vector/regime_ledger.jsonl   (append-only, dedupe by date)
Scored file:  data/vector/regime_scored.jsonl   (append-only, dedupe by date)
Falsifiers:   data/vector/regime_falsifiers.json (rewritten on each run)

CONTEXT-ONLY — never imports from sizing / allocation; never re-fits weights.
Pure, NaN-safe, degrade-never-raise.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from lib import config

log = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# paths
# --------------------------------------------------------------------------- #
_LEDGER_PATH = ("data", "vector", "regime_ledger.jsonl")
_SCORED_PATH = ("data", "vector", "regime_scored.jsonl")
_FALSIFIERS_PATH = ("data", "vector", "regime_falsifiers.json")
_SIGNALS_PATH = ("data", "vector", "signals.parquet")

# --------------------------------------------------------------------------- #
# tuning knobs (a-priori; count as 1 trial each in any validation harness)
# --------------------------------------------------------------------------- #
HORIZON_DAYS = 90              # forward-return horizon for grading
MIN_QUARTERS_FALSIFIER = 8     # minimum graded quarters before falsifier fires
FRAGILE_THRESHOLD = 0.45       # sign-agreement below this → FRAGILE

# Tier that is structurally context-only (2024+ history only; cannot be promoted)
_CONTEXT_TIERS = {"T5_etf"}    # keyed by tier+"_"+factor_key

SCHEMA = "btc_regime_ledger.v1"


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _today_str(asof=None) -> str:
    if asof is None:
        return date.today().isoformat()
    if hasattr(asof, "isoformat"):
        return asof.isoformat()
    return str(asof)


def _load_jsonl(path: Path) -> list[dict]:
    try:
        if not path.exists():
            return []
        lines = path.read_text().splitlines()
        return [json.loads(l) for l in lines if l.strip()]
    except Exception as e:  # noqa: BLE001
        log.warning("btc_regime_ledger: jsonl load failed %s: %s", path, e)
        return []


def _dedupe_by_date(rows: list[dict]) -> dict[str, dict]:
    """Last write wins per date — makes stamp idempotent."""
    out: dict[str, dict] = {}
    for r in rows:
        d = r.get("date")
        if d:
            out[d] = r
    return out


def _append_jsonl(path: Path, rows: list[dict]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a") as fh:
            for r in rows:
                fh.write(json.dumps(r, default=str) + "\n")
    except Exception as e:  # noqa: BLE001
        log.warning("btc_regime_ledger: append failed %s: %s", path, e)


def _write_json(path: Path, obj: Any) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(obj, indent=2, default=str))
    except Exception as e:  # noqa: BLE001
        log.warning("btc_regime_ledger: json write failed %s: %s", path, e)


def _f(v) -> float | None:
    """Safe float cast; returns None for NaN/None."""
    try:
        if v is None:
            return None
        f = float(v)
        return None if np.isnan(f) else f
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------------------- #
# BTC close series
# --------------------------------------------------------------------------- #
def _load_close(root: Path) -> pd.Series | None:
    """Load BTC daily closes from signals.parquet, indexed by date."""
    try:
        p = root / _SIGNALS_PATH[0] / _SIGNALS_PATH[1] / _SIGNALS_PATH[2]
        df = pd.read_parquet(p, columns=["close"])
        s = df["close"].dropna()
        s.index = pd.to_datetime(s.index)
        return s
    except Exception as e:  # noqa: BLE001
        log.warning("btc_regime_ledger: close load failed: %s", e)
        return None


def _close_at(closes: pd.Series, dt) -> float | None:
    """Last close on or before dt."""
    try:
        sub = closes[closes.index <= pd.Timestamp(dt)]
        return _f(sub.iloc[-1]) if len(sub) else None
    except Exception:  # noqa: BLE001
        return None


def _forward_return(closes: pd.Series, start_dt, horizon_days: int) -> float | None:
    """Realized (close[start+horizon] / close[start]) - 1, or None if data absent."""
    try:
        c0 = _close_at(closes, start_dt)
        end_dt = pd.Timestamp(start_dt) + pd.Timedelta(days=horizon_days)
        c1 = _close_at(closes, end_dt)
        if c0 is None or c1 is None or c0 == 0:
            return None
        return _f((c1 / c0) - 1.0)
    except Exception:  # noqa: BLE001
        return None


def _forward_max_drawdown(closes: pd.Series, start_dt, horizon_days: int) -> float | None:
    """Max peak-to-trough drawdown over [start, start+horizon], or None."""
    try:
        end_dt = pd.Timestamp(start_dt) + pd.Timedelta(days=horizon_days)
        window = closes[(closes.index > pd.Timestamp(start_dt)) &
                        (closes.index <= end_dt)]
        if len(window) < 2:
            return None
        roll_max = window.expanding().max()
        dd = (window - roll_max) / roll_max
        return _f(dd.min())
    except Exception:  # noqa: BLE001
        return None


# --------------------------------------------------------------------------- #
# stamp — one row per day
# --------------------------------------------------------------------------- #
def stamp(regime: dict, asof=None, *, root=None, _persist: bool = True) -> dict:
    """Append one row to the ledger for today (or `asof`). Idempotent per date.

    Args:
        regime: the dict returned by engine.btc_regime.compute()
        asof:   override the stamp date (for testing / back-fill)
        root:   override the project root (for testing)

    Returns the stamped row dict (useful for testing).
    """
    root = Path(root) if root else config.ROOT
    stamp_date = _today_str(asof)

    # ---- extract fields from regime dict ---------------------------------- #
    flags = regime.get("flags") or {}
    flags_active = flags.get("active", []) if isinstance(flags, dict) else []
    if isinstance(flags_active, list):
        flag_str = ",".join(flags_active) if flags_active else "NONE"
    else:
        flag_str = str(flags_active)

    sa = flags.get("stay_away") or {}
    dd_f = flags.get("double_down") or {}

    tier_subs: dict[str, float | None] = {}
    for t in (regime.get("tiers") or []):
        tc = t.get("tier")
        if tc:
            tier_subs[tc] = _f(t.get("norm"))

    factor_scores: dict[str, int | None] = {}
    for f in (regime.get("factors") or []):
        k = f.get("key")
        if k:
            sc = f.get("score")
            factor_scores[k] = int(sc) if sc is not None else None

    mode_lean = (regime.get("mode_lean") or {})
    lean = mode_lean.get("lean") if isinstance(mode_lean, dict) else None

    row = {
        "schema": SCHEMA,
        "date": stamp_date,
        "stamped_at": _now_iso(),
        "index": _f(regime.get("index")),
        "band": regime.get("band"),
        "band_zh": regime.get("band_zh"),
        "exposure_display": _f(regime.get("exposure_display")),
        "flags_active": flag_str,
        "sa_count": int(sa.get("count", 0)) if isinstance(sa, dict) else 0,
        "dd_count": int(dd_f.get("count", 0)) if isinstance(dd_f, dict) else 0,
        "mode_lean": lean,
        "tier_subs": tier_subs,
        "factor_scores": factor_scores,
    }

    if _persist:
        path = root.joinpath(*_LEDGER_PATH)
        # Load existing, overwrite same-date row, re-append all
        existing = _dedupe_by_date(_load_jsonl(path))
        existing[stamp_date] = row
        # Rewrite entire file to maintain idempotency (file is typically small)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w") as fh:
                for r in sorted(existing.values(), key=lambda x: x["date"]):
                    fh.write(json.dumps(r, default=str) + "\n")
        except Exception as e:  # noqa: BLE001
            log.warning("btc_regime_ledger: stamp write failed: %s", e)

    return row


# --------------------------------------------------------------------------- #
# score — grade matured rows
# --------------------------------------------------------------------------- #
def score(asof=None, *, root=None, horizon: int = HORIZON_DAYS,
          _persist: bool = True) -> dict:
    """Grade all ledger rows where date + horizon ≤ asof (matured).

    Returns a render-ready summary dict.
    """
    root = Path(root) if root else config.ROOT
    today = pd.Timestamp(_today_str(asof))

    ledger_rows = list(_dedupe_by_date(
        _load_jsonl(root.joinpath(*_LEDGER_PATH))
    ).values())

    if not ledger_rows:
        return _empty_score(today)

    closes = _load_close(root)

    # ---- grade each matured row ------------------------------------------ #
    matured_rows = []
    for row in ledger_rows:
        stamp_dt = pd.Timestamp(row["date"])
        if stamp_dt + pd.Timedelta(days=horizon) > today:
            continue   # not yet matured
        if closes is None:
            continue

        fwd_ret = _forward_return(closes, row["date"], horizon)
        fwd_mdd = _forward_max_drawdown(closes, row["date"], horizon)
        if fwd_ret is None:
            continue   # no price data for this window

        matured_rows.append({
            **row,
            "fwd_return": fwd_ret,
            "fwd_max_drawdown": fwd_mdd,
        })

    n = len(matured_rows)
    thin = n < 30

    # ---- (a) index IC over matured rows ----------------------------------- #
    index_ic = _index_ic(matured_rows)

    # ---- (b) STAY-AWAY: avg drawdown when active vs not ------------------- #
    sa_stats = _sa_stats(matured_rows)

    # ---- (c) DOUBLE-DOWN: avg fwd return when active ---------------------- #
    dd_stats = _dd_stats(matured_rows)

    # ---- (d) per-tier sign agreement -------------------------------------- #
    tier_agreement = _tier_agreement(matured_rows)

    summary = {
        "schema": SCHEMA,
        "as_of": today.date().isoformat(),
        "horizon_days": horizon,
        "n_matured": n,
        "n_total_ledger": len(ledger_rows),
        "thin_sample": thin,
        "thin_note": ("n too thin (<30) — treat all statistics as provisional."
                      if thin else ""),
        "index_ic": index_ic,
        "stay_away": sa_stats,
        "double_down": dd_stats,
        "tier_agreement": tier_agreement,
    }

    if _persist and matured_rows:
        # Write scored rows for auditability (append-only, no deduplication
        # needed here — callers who re-run will produce identical rows)
        scored_path = root.joinpath(*_SCORED_PATH)
        scored_dates = {r.get("date") for r in _load_jsonl(scored_path)}
        new_rows = [r for r in matured_rows if r.get("date") not in scored_dates]
        if new_rows:
            _append_jsonl(scored_path, new_rows)

    return summary


def _empty_score(today) -> dict:
    return {
        "schema": SCHEMA,
        "as_of": str(today.date()) if hasattr(today, "date") else str(today),
        "horizon_days": HORIZON_DAYS,
        "n_matured": 0,
        "n_total_ledger": 0,
        "thin_sample": True,
        "thin_note": "No ledger rows found.",
        "index_ic": None,
        "stay_away": {"n_active": 0, "n_inactive": 0,
                      "avg_mdd_active": None, "avg_mdd_inactive": None,
                      "working": None},
        "double_down": {"n_active": 0, "avg_fwd_return_active": None},
        "tier_agreement": {},
    }


def _index_ic(rows: list[dict]) -> float | None:
    """Rank IC between regime index and forward return over matured rows."""
    if len(rows) < 4:
        return None
    idx = [_f(r.get("index")) for r in rows]
    ret = [_f(r.get("fwd_return")) for r in rows]
    pairs = [(i, r) for i, r in zip(idx, ret) if i is not None and r is not None]
    if len(pairs) < 4:
        return None
    try:
        from scipy.stats import spearmanr  # optional; degrade if absent
        idxs, rets = zip(*pairs)
        ic, _ = spearmanr(idxs, rets)
        return _f(ic)
    except Exception:
        # Fallback: manual rank correlation
        n = len(pairs)
        idxs, rets = zip(*pairs)
        rank_i = _rank(list(idxs))
        rank_r = _rank(list(rets))
        d2 = sum((ri - rr) ** 2 for ri, rr in zip(rank_i, rank_r))
        ic = 1 - (6 * d2) / (n * (n ** 2 - 1))
        return _f(ic)


def _rank(vals: list[float]) -> list[float]:
    """Simple rank (1-based) without ties handling."""
    sorted_vals = sorted(enumerate(vals), key=lambda x: x[1])
    ranks = [0.0] * len(vals)
    for rank, (orig_idx, _) in enumerate(sorted_vals, 1):
        ranks[orig_idx] = float(rank)
    return ranks


def _sa_stats(rows: list[dict]) -> dict:
    """STAY-AWAY grading: avg fwd max drawdown when active vs inactive."""
    active = [r for r in rows if "STAY" in str(r.get("flags_active", ""))]
    inactive = [r for r in rows if "STAY" not in str(r.get("flags_active", ""))]

    def avg_mdd(lst):
        vals = [_f(r.get("fwd_max_drawdown")) for r in lst]
        vals = [v for v in vals if v is not None]
        return round(sum(vals) / len(vals), 4) if vals else None

    mdd_a = avg_mdd(active)
    mdd_i = avg_mdd(inactive)
    # Working = drawdown when active is MORE negative than when inactive
    working = None
    if mdd_a is not None and mdd_i is not None:
        working = bool(mdd_a < mdd_i)

    return {
        "n_active": len(active),
        "n_inactive": len(inactive),
        "avg_mdd_active": mdd_a,
        "avg_mdd_inactive": mdd_i,
        "working": working,
        "note": ("STAY-AWAY working: avg drawdown worse when flag active"
                 if working else
                 "STAY-AWAY not working or insufficient data"),
    }


def _dd_stats(rows: list[dict]) -> dict:
    """DOUBLE-DOWN grading: avg fwd return when active."""
    active = [r for r in rows if "DOUBLE" in str(r.get("flags_active", ""))]
    vals = [_f(r.get("fwd_return")) for r in active]
    vals = [v for v in vals if v is not None]
    avg = round(sum(vals) / len(vals), 4) if vals else None
    return {
        "n_active": len(active),
        "avg_fwd_return_active": avg,
        "note": (f"avg +{avg:.1%} fwd return when DOUBLE-DOWN active"
                 if avg is not None and avg > 0
                 else "neutral or negative" if avg is not None
                 else "no DOUBLE-DOWN observations yet"),
    }


def _tier_agreement(rows: list[dict]) -> dict[str, dict]:
    """Per-tier: sign-agreement of tier norm sub-score with forward return."""
    tiers = ["T1", "T2", "T3", "T4", "T5"]
    result = {}
    for tc in tiers:
        pairs = []
        for r in rows:
            tsub = _f((r.get("tier_subs") or {}).get(tc))
            ret = _f(r.get("fwd_return"))
            if tsub is not None and ret is not None:
                pairs.append((tsub, ret))
        n = len(pairs)
        if n == 0:
            result[tc] = {"n": 0, "agreement": None}
            continue
        # sign agreement: both positive or both negative or both zero
        agree = sum(1 for (s, r) in pairs
                    if (s > 0 and r > 0) or (s < 0 and r < 0))
        result[tc] = {
            "n": n,
            "agreement": round(agree / n, 3),
        }
    return result


# --------------------------------------------------------------------------- #
# falsifier_status — per-tier FRAGILE / OK / INELIGIBLE_PENDING
# --------------------------------------------------------------------------- #

# Falsifier definitions (one-liners):
# T1 Liquidity:      sign-agreement < 0.45 over ≥8 graded quarters → FRAGILE
# T2 Rates/Dollar:   sign-agreement < 0.45 over ≥8 graded quarters → FRAGILE
# T3 Curve/Fed:      sign-agreement < 0.45 over ≥8 graded quarters → FRAGILE
# T4 Equity/VIX:     sign-agreement < 0.45 over ≥8 graded quarters → FRAGILE
# T5 apriori legs:   sign-agreement < 0.45 over ≥8 graded quarters → FRAGILE
# T5 etf (context):  STRUCTURALLY INELIGIBLE — needs ≥8 graded quarters first,
#                    then evaluated like T5 but never promoted above context tier.

# A "graded quarter" ≈ 13 matured rows (quarterly non-overlapping windows).
# We approximate: n_matured / 13 ≥ MIN_QUARTERS_FALSIFIER.
_APPROX_ROWS_PER_QUARTER = 13


def falsifier_status(asof=None, *, root=None, horizon: int = HORIZON_DAYS,
                     _persist: bool = True) -> dict:
    """Evaluate per-tier falsifiers. Writes data/vector/regime_falsifiers.json.

    Returns:
        dict with keys:
            "tiers": {T1..T5: {status, agreement, n_quarters, demote_weight_to}}
            "etf_leg": {status, agreement, n_quarters}
            "as_of": date str
            "honesty_note": EN plain-English summary
            "honesty_note_zh": ZH mirror
    """
    root = Path(root) if root else config.ROOT
    today = pd.Timestamp(_today_str(asof))

    ledger_rows = list(_dedupe_by_date(
        _load_jsonl(root.joinpath(*_LEDGER_PATH))
    ).values())

    closes = _load_close(root)

    # Build matured rows (same logic as score())
    matured_rows = []
    for row in ledger_rows:
        stamp_dt = pd.Timestamp(row["date"])
        if stamp_dt + pd.Timedelta(days=horizon) > today:
            continue
        if closes is None:
            continue
        fwd_ret = _forward_return(closes, row["date"], horizon)
        if fwd_ret is None:
            continue
        matured_rows.append({**row, "fwd_return": fwd_ret})

    n_matured = len(matured_rows)
    n_quarters = n_matured / _APPROX_ROWS_PER_QUARTER
    tier_agreement = _tier_agreement(matured_rows)

    tiers_out: dict[str, dict] = {}
    for tc in ["T1", "T2", "T3", "T4", "T5"]:
        ta = tier_agreement.get(tc, {})
        agree = _f(ta.get("agreement"))
        n_rows = ta.get("n", 0)
        tier_quarters = n_rows / _APPROX_ROWS_PER_QUARTER

        if tier_quarters < MIN_QUARTERS_FALSIFIER:
            status = "INELIGIBLE_PENDING"
            demote = None
        elif agree is not None and agree < FRAGILE_THRESHOLD:
            status = "FRAGILE"
            demote = 0.0   # zero-weight this tier in the display scorecard
        else:
            status = "OK"
            demote = None

        tiers_out[tc] = {
            "status": status,
            "agreement": agree,
            "n_quarters": round(tier_quarters, 1),
            "demote_weight_to": demote,
            "falsifies_if": (f"sign-agreement < {FRAGILE_THRESHOLD} "
                             f"over ≥{MIN_QUARTERS_FALSIFIER} graded quarters"),
        }

    # ---- ETF leg (context/flow; structurally INELIGIBLE_PENDING) ---------- #
    # The ETF leg lives inside T5 but is tracked separately because it is
    # structurally ineligible for promotion (2024+ history only). We compute
    # its own sign-agreement vs forward return using the 'etf' factor score.
    etf_pairs = []
    for r in matured_rows:
        escore = _f((r.get("factor_scores") or {}).get("etf"))
        ret = _f(r.get("fwd_return"))
        if escore is not None and ret is not None:
            etf_pairs.append((escore, ret))
    etf_n = len(etf_pairs)
    etf_quarters = etf_n / _APPROX_ROWS_PER_QUARTER
    etf_agree = None
    if etf_n > 0:
        etf_agree = round(
            sum(1 for (s, r) in etf_pairs
                if (s > 0 and r > 0) or (s < 0 and r < 0)) / etf_n, 3
        )

    etf_status = "INELIGIBLE_PENDING"  # always starts here; needs ≥8 quarters
    if etf_quarters >= MIN_QUARTERS_FALSIFIER:
        # Only then evaluate, but it can NEVER be promoted above context tier
        if etf_agree is not None and etf_agree < FRAGILE_THRESHOLD:
            etf_status = "FRAGILE"
        else:
            etf_status = "OK_CONTEXT_ONLY"  # graded but cannot be promoted

    etf_out = {
        "status": etf_status,
        "agreement": etf_agree,
        "n_quarters": round(etf_quarters, 1),
        "demote_weight_to": 0.0 if etf_status == "FRAGILE" else None,
        "note": ("ETF/flow leg is structurally CONTEXT-ONLY (2024+ history). "
                 "It can be graded once ≥8 quarters accrue, but cannot be "
                 "promoted to an apriori tier regardless of performance."),
    }

    honesty_note = _honesty_note(tiers_out, etf_out, n_matured)
    honesty_note_zh = _honesty_note_zh(tiers_out, etf_out, n_matured)

    out = {
        "schema": SCHEMA,
        "as_of": today.date().isoformat(),
        "horizon_days": horizon,
        "n_matured": n_matured,
        "tiers": tiers_out,
        "etf_leg": etf_out,
        "honesty_note": honesty_note,
        "honesty_note_zh": honesty_note_zh,
        "context_only": True,
    }

    if _persist:
        _write_json(root.joinpath(*_FALSIFIERS_PATH), out)

    return out


def _honesty_note(tiers: dict, etf: dict, n_matured: int) -> str:
    fragile = [tc for tc, v in tiers.items() if v["status"] == "FRAGILE"]
    pending = [tc for tc, v in tiers.items() if v["status"] == "INELIGIBLE_PENDING"]
    if n_matured == 0:
        return ("Regime ledger is empty — no matured rows to grade yet. "
                "Falsifier evaluation begins after the first 90-day windows close.")
    parts = [f"{n_matured} matured rows graded."]
    if fragile:
        parts.append(f"FRAGILE tiers (display-zeroed): {', '.join(fragile)}.")
    if pending:
        parts.append(f"Pending ≥{MIN_QUARTERS_FALSIFIER} graded quarters: "
                     f"{', '.join(pending)}.")
    parts.append(f"ETF/flow leg: {etf['status']} "
                 f"({etf.get('n_quarters', 0):.1f} quarters).")
    parts.append("CONTEXT-ONLY — demotion is display metadata, never re-fits engine weights.")
    return " ".join(parts)


def _honesty_note_zh(tiers: dict, etf: dict, n_matured: int) -> str:
    fragile = [tc for tc, v in tiers.items() if v["status"] == "FRAGILE"]
    pending = [tc for tc, v in tiers.items() if v["status"] == "INELIGIBLE_PENDING"]
    if n_matured == 0:
        return ("账本为空 —— 暂无到期行记录，待首批90天窗口到期后开始评分。")
    parts = [f"已评分 {n_matured} 条成熟记录。"]
    if fragile:
        parts.append(f"脆弱层级（展示权重归零）：{', '.join(fragile)}。")
    if pending:
        parts.append(f"待达到≥{MIN_QUARTERS_FALSIFIER}个季度：{', '.join(pending)}。")
    parts.append(f"ETF/资金流层：{etf['status']}（{etf.get('n_quarters', 0):.1f}季度）。")
    parts.append("仅供参考 —— 降级仅为展示元数据，不重新拟合引擎权重。")
    return "".join(parts)


# --------------------------------------------------------------------------- #
# render_summary — combined dashboard payload
# --------------------------------------------------------------------------- #
def render_summary(asof=None, *, root=None, horizon: int = HORIZON_DAYS) -> dict:
    """Return a single render-ready dict combining score + falsifier status.

    Safe to call on every build; degrades gracefully with no ledger data.
    """
    try:
        s = score(asof=asof, root=root, horizon=horizon)
        f = falsifier_status(asof=asof, root=root, horizon=horizon)
        return {
            "schema": SCHEMA,
            "as_of": s.get("as_of"),
            "score": s,
            "falsifiers": f,
            "honesty_note": f.get("honesty_note", ""),
            "honesty_note_zh": f.get("honesty_note_zh", ""),
            "context_only": True,
            "display_note": (
                "Regime ledger grades the live stance forward; demoted tiers "
                "are display-only metadata. Nothing in sizing or allocation reads this."
            ),
        }
    except Exception as e:  # noqa: BLE001
        log.error("btc_regime_ledger render_summary failed: %s", e)
        return {"ok": False, "reason": f"{type(e).__name__}: {e}"}


# --------------------------------------------------------------------------- #
# CLI entry point
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    s = render_summary()
    print(json.dumps(s, indent=2, default=str))
