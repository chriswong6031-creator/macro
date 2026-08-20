"""research/cn_limit/p0_st_band_replay.py — P0-ST bounded owner-native replay instrument.

Verifies the P0-ST repair (main-board risk-warning band ±5% → ±10% effective 2026-07-06;
see engine.china_microstructure.MAIN_ST_BAND_WIDE_DATE and
research/cn_limit/P0_ST_BAND_REPAIR_RECEIPT_2026-08-19.md) by replaying the OWNER's own
detection function (`engine.china_microstructure._detect_limit_events`) over the affected
universe under two arms — the current (era-dated) width law and the superseded (always-5%)
law it replaced — and diffing the resulting event sets.

Deterministic, offline, read-only w.r.t. every data store: this script only reads
data/china_microstructure/limit_events.parquet, data/china_st/st_snapshot.parquet,
data/china_st/st_history.parquet, and data/china_stocks_raw/*.parquet. It writes exactly one
file, the receipt JSON alongside this script, and never touches any store the nightly
pipeline owns. Running this script twice against unchanged inputs produces a byte-identical
JSON receipt: there is no wall-clock timestamp inside it (the repo HEAD sha is stamped
instead via `git rev-parse HEAD`), and every collection that could iterate in a nondeterministic
order is sorted before being serialised.

Usage
-----
    python3 research/cn_limit/p0_st_band_replay.py
"""
from __future__ import annotations

import hashlib
import inspect
import json
import subprocess
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

import engine.china_microstructure as cm  # noqa: E402
from engine.china_microstructure import (  # noqa: E402
    MAIN_ST_BAND_WIDE_DATE,
    ST_STORE_COVERAGE_DATE,
    _board_from_ticker,
    _detect_limit_events,
    _load_st_set,
    limit_width_for_date,
)

DATA_DIR = REPO_ROOT / "data"
RAW_DIR = DATA_DIR / "china_stocks_raw"
RECEIPT_JSON = Path(__file__).resolve().parent / "P0_ST_BAND_REPAIR_RECEIPT_2026-08-19.json"


# ── git / definition provenance ─────────────────────────────────────────────────

def _git_head_sha() -> str:
    out = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO_ROOT, capture_output=True, text=True, check=True,
    )
    return out.stdout.strip()


def _definition_hash() -> str:
    """sha256 over (limit_width_for_date source + raw bytes of the registry YAML).

    Changes to either the width function's own logic or the citable registry it is held
    to parity with will move this hash — it is the "what law were we replaying under"
    fingerprint for this receipt.
    """
    src = inspect.getsource(limit_width_for_date)
    cfg_bytes = (REPO_ROOT / "config" / "cn_limit_rules.yml").read_bytes()
    h = hashlib.sha256()
    h.update(src.encode("utf-8"))
    h.update(cfg_bytes)
    return h.hexdigest()


# ── census ────────────────────────────────────────────────────────────────────

def _census() -> dict:
    le_path = DATA_DIR / "china_microstructure" / "limit_events.parquet"
    le = pd.read_parquet(le_path)
    stale_5pct = le[le["limit_width"] == 5.0]

    sn = pd.read_parquet(DATA_DIR / "china_st" / "st_snapshot.parquet")
    sh = pd.read_parquet(DATA_DIR / "china_st" / "st_history.parquet")

    return {
        "limit_events_total_rows": int(len(le)),
        "limit_events_stale_5pct_rows": int(len(stale_5pct)),
        "limit_events_min_date": str(pd.Timestamp(le["date"].min()).date()),
        "limit_events_max_date": str(pd.Timestamp(le["date"].max()).date()),
        "st_snapshot_row_count": int(len(sn)),
        "st_snapshot_asof_dates": sorted(str(d) for d in sn["asof"].astype(str).unique()),
        "st_history_dates_covered": sorted(str(d) for d in sh["date"].astype(str).unique()),
    }


def _affected_universe() -> list[str]:
    """st_snapshot tickers ∩ raw-store names, filtered to main board.

    Expected result (per the P0-ST commission): exactly ['600079.SS']. If reality
    differs the receipt reports the ACTUAL list rather than forcing the expectation.
    """
    sn = pd.read_parquet(DATA_DIR / "china_st" / "st_snapshot.parquet")
    raw_names = {p.stem for p in RAW_DIR.glob("*.parquet")}
    st_tickers = {str(t) for t in sn["ticker"]}
    inter = st_tickers & raw_names
    return sorted(t for t in inter if _board_from_ticker(t) == "main")


# ── per-session transparency table (independent of the event detector) ────────

def _per_session_table(df: pd.DataFrame, window_start: pd.Timestamp) -> list[dict]:
    """Session-by-session would-touch/seal table at both 5% and 10% widths, and the
    ex-div suspect gate at both widths, for the receipt's transparency section.

    Computed independently of `_detect_limit_events` (which only ever runs under ONE
    width per bar) so the receipt can show, per session, what BOTH candidate widths
    would have done — this is what makes the "zero corrections needed" claim a
    measured fact rather than an assumption.
    """
    full = df.copy()
    full.index = pd.to_datetime(full.index)
    full = full.sort_index()
    prev_close = full["close"].astype(float).shift(1)

    rows: list[dict] = []
    for ts in full.index[full.index >= window_start]:
        pc = prev_close.loc[ts]
        if pd.isna(pc) or pc <= 0:
            continue
        o = float(full.loc[ts, "open"])
        h = float(full.loc[ts, "high"])
        lo = float(full.loc[ts, "low"])
        c = float(full.loc[ts, "close"])

        max_abs_move_pct = round(max(abs(h - pc), abs(pc - lo), abs(c - pc)) / pc * 100, 4)

        lim_up_5, lim_down_5 = round(pc * 1.05, 2), round(pc * 0.95, 2)
        lim_up_10, lim_down_10 = round(pc * 1.10, 2), round(pc * 0.90, 2)

        open_move_pct = abs(o - pc) / pc
        rows.append({
            "date": ts.strftime("%Y-%m-%d"),
            "prev_close": round(pc, 4),
            "open": round(o, 4),
            "high": round(h, 4),
            "low": round(lo, 4),
            "close": round(c, 4),
            "max_abs_move_pct": max_abs_move_pct,
            "at_5pct": {
                "would_touch": bool(h >= lim_up_5 or lo <= lim_down_5),
                "would_seal": bool(c >= lim_up_5 or c <= lim_down_5),
                "exdiv_suspect": bool(open_move_pct > 0.05 * 1.5),
            },
            "at_10pct": {
                "would_touch": bool(h >= lim_up_10 or lo <= lim_down_10),
                "would_seal": bool(c >= lim_up_10 or c <= lim_down_10),
                "exdiv_suspect": bool(open_move_pct > 0.10 * 1.5),
            },
        })
    return rows


# ── two-arm replay ──────────────────────────────────────────────────────────────

def _run_current_arm(ticker: str, df: pd.DataFrame, st_set: frozenset) -> dict:
    events, ipo_excl, exdiv_excl = _detect_limit_events(
        ticker, df, "main", st_set, start_date=MAIN_ST_BAND_WIDE_DATE,
    )
    return {"events": events, "ipo_excluded": ipo_excl, "exdiv_excluded": exdiv_excl}


def _run_superseded_arm(ticker: str, df: pd.DataFrame, st_set: frozenset) -> dict:
    """Monkeypatch engine.china_microstructure.limit_width_for_date with a shim
    labelled "superseded pre-P0-ST behavior": main-board ST always takes 5%,
    regardless of date. Restored in the `finally` block regardless of outcome."""
    original = cm.limit_width_for_date

    def _superseded_shim(board: str, trade_date: pd.Timestamp, is_st: bool = False) -> float:
        if board == "main" and is_st:
            return 0.05  # superseded pre-P0-ST behavior
        return original(board, trade_date, is_st=is_st)

    cm.limit_width_for_date = _superseded_shim
    try:
        events, ipo_excl, exdiv_excl = _detect_limit_events(
            ticker, df, "main", st_set, start_date=MAIN_ST_BAND_WIDE_DATE,
        )
    finally:
        cm.limit_width_for_date = original
    return {"events": events, "ipo_excluded": ipo_excl, "exdiv_excluded": exdiv_excl}


def _events_key(ev: dict) -> tuple:
    return tuple(ev[k] for k in sorted(ev.keys()))


def _diff_events(current: list[dict], superseded: list[dict]) -> dict:
    cur_keys = sorted(_events_key(e) for e in current)
    sup_keys = sorted(_events_key(e) for e in superseded)
    return {
        "current_only_count": len([k for k in cur_keys if k not in sup_keys]),
        "superseded_only_count": len([k for k in sup_keys if k not in cur_keys]),
        "identical": cur_keys == sup_keys,
    }


# ── main ─────────────────────────────────────────────────────────────────────

def main() -> dict:
    st_set = _load_st_set(DATA_DIR)
    affected = _affected_universe()
    census = _census()
    def_hash = _definition_hash()
    head_sha = _git_head_sha()

    per_name: dict[str, dict] = {}
    for ticker in affected:
        raw_ticker = ticker  # raw store already uses .SS/.SZ
        fp = RAW_DIR / f"{raw_ticker}.parquet"
        df = pd.read_parquet(fp) if fp.exists() else pd.DataFrame()
        if df.empty:
            per_name[ticker] = {"error": f"raw store file missing or empty: {fp}"}
            continue

        current_arm = _run_current_arm(ticker, df, st_set)
        superseded_arm = _run_superseded_arm(ticker, df, st_set)
        session_table = _per_session_table(df, MAIN_ST_BAND_WIDE_DATE)
        diff = _diff_events(current_arm["events"], superseded_arm["events"])

        per_name[ticker] = {
            "board": _board_from_ticker(ticker),
            "session_count": len(session_table),
            "arm_current": current_arm,
            "arm_superseded": superseded_arm,
            "diff": diff,
            "sessions": session_table,
        }

    all_diffs_empty = all(
        v.get("diff", {}).get("identical", False)
        for v in per_name.values()
        if "diff" in v
    )

    receipt = {
        "schema": "cn_limit.p0_st_band_replay.v1",
        "repo_head_sha": head_sha,
        "definition_hash_sha256": def_hash,
        "constants": {
            "MAIN_ST_BAND_WIDE_DATE": str(MAIN_ST_BAND_WIDE_DATE.date()),
            "ST_STORE_COVERAGE_DATE": str(ST_STORE_COVERAGE_DATE.date()),
        },
        "census": census,
        "affected_main_board_universe": affected,
        "expected_affected_main_board_universe": ["600079.SS"],
        "affected_universe_matches_expectation": affected == ["600079.SS"],
        "per_name": per_name,
        "zero_corrections_required": bool(all_diffs_empty),
    }
    return receipt


if __name__ == "__main__":
    result = main()
    payload = json.dumps(result, sort_keys=True, indent=2, default=str)
    RECEIPT_JSON.write_text(payload + "\n")

    print(f"repo_head_sha: {result['repo_head_sha']}")
    print(f"definition_hash_sha256: {result['definition_hash_sha256']}")
    print(f"limit_events_total_rows: {result['census']['limit_events_total_rows']}")
    print(f"limit_events_stale_5pct_rows: {result['census']['limit_events_stale_5pct_rows']}")
    print(f"affected_main_board_universe: {result['affected_main_board_universe']}")
    print(f"affected_universe_matches_expectation: {result['affected_universe_matches_expectation']}")
    for ticker, v in result["per_name"].items():
        if "diff" in v:
            print(f"  {ticker}: sessions={v['session_count']} diff={v['diff']}")
    print(f"zero_corrections_required: {result['zero_corrections_required']}")
    print(f"wrote {RECEIPT_JSON}")
