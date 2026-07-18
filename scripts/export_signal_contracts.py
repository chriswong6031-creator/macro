"""Export cross-repo signal contracts as DATA (audit #7 #9 #45) → site/factordata/contracts/.

The dashboard is the ORACLE. It exports two artifacts the Terminal and bot consume as a
conformance check — so a stale fork FAILS and a correct engine PASSES (the inversion of
the old golden_gate, which self-checked a known-wrong reference):

  1. golden_signals.json — for NVDA + one A-share + one HK name: an inputs-hash and the
     expected BUY/SELL/tier sequence over a FIXED historical window, computed from the
     dashboard's CORRECTED confluence math (engine.canon.confluence_signals: session-
     grouped 3D resample, adjust=False EMA, SMA-seeded RMA). The Terminal reproduces the
     sequence from the same close series; any mismatch means its math drifted (#7).

  2. artifact_manifest.json — {artifact, expected_max_age in TRADING-CALENDAR days} for the
     handoff files the Terminal and bot read (stock JSONs, us/china standouts, regime
     timelines). The consumer fails-CLOSED on genuine staleness (per-artifact cadence)
     without halting on benign weekend/holiday lag (#9).

The window is FIXED (start/end pinned) so the exported sequence is deterministic and the
contract is reproducible across repos and reruns. Never raises on a missing symbol —
it is skipped with a logged warning.

Usage:  PYTHONPATH=. python scripts/export_signal_contracts.py
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from engine import canon

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "site" / "factordata" / "contracts"

# Fixed historical window: pinned so the exported sequence is deterministic & reproducible.
WINDOW_START = "2015-01-01"
WINDOW_END = "2024-12-31"

# The three golden symbols (one per region) + where their close series lives.
GOLDEN_SYMBOLS = [
    {"symbol": "NVDA", "region": "US", "path": "data/stocks/NVDA.parquet"},
    {"symbol": "600519.SS", "region": "CN", "path": "data/china_stocks/600519.SS.parquet",
     "label": "Kweichow Moutai (A-share)"},
    {"symbol": "0700.HK", "region": "HK", "path": "data/hk_stocks/0700.HK.parquet",
     "label": "Tencent (HK)"},
]


# ── golden signal vectors ─────────────────────────────────────────────────────
def _close_window(path: str) -> pd.Series | None:
    p = ROOT / path
    if not p.exists():
        log.warning("golden symbol source missing: %s", p)
        return None
    df = pd.read_parquet(p)
    if "close" not in df.columns:
        log.warning("no close column in %s", p)
        return None
    s = pd.to_numeric(df["close"], errors="coerce").dropna()
    s.index = pd.to_datetime(s.index)
    s = s[(s.index >= WINDOW_START) & (s.index <= WINDOW_END)]
    return s if len(s) else None


def _inputs_hash(close: pd.Series) -> str:
    """Hash the exact close series the sequence was computed from (dates + rounded values),
    so the Terminal can PROVE it fed the same inputs before trusting the expected sequence."""
    payload = json.dumps(
        {"dates": [d.strftime("%Y-%m-%d") for d in close.index],
         "close": [round(float(v), 6) for v in close.to_numpy()]},
        sort_keys=True)
    return "sha256:" + hashlib.sha256(payload.encode()).hexdigest()


def _signal_sequence(sig: pd.DataFrame) -> list[dict]:
    """Corrected confluence frame → the BUY/SELL/REBUY/CUT event sequence (the contract).

    Priority mirrors the Terminal's contracts._extract_signals: CB→BUY, revBuy→REBUY,
    CS→SELL, revSell→CUT. `tier` is the owner's confidence read on the event bar (regime
    gates agreeing) so the contract also pins the tier, not just the direction."""
    out = []
    for ts, row in sig.iterrows():
        kind = None
        if row.get("CB"):
            kind = "BUY"
        elif row.get("revBuy"):
            kind = "REBUY"
        elif row.get("CS"):
            kind = "SELL"
        elif row.get("revSell"):
            kind = "CUT"
        if not kind:
            continue
        gates = [bool(row.get("w_bull")), bool(row.get("above200")),
                 bool(row.get("mo_bull")), bool(row.get("w2_bull"))]
        out.append({
            "ts": ts.strftime("%Y-%m-%d"),
            "type": kind,
            "tier": _tier(kind, sum(gates)),
            "regime": {"weeklyBull": gates[0], "above200": gates[1], "monthlyBull": gates[2]},
        })
    return out


def _tier(kind: str, n_gates: int) -> str:
    """Coarse tier from how many regime gates agree (T1 strongest .. T4 weakest).
    BUY/REBUY only; SELL/CUT carry no tier (exit)."""
    if kind in ("SELL", "CUT"):
        return "EXIT"
    return {4: "T1", 3: "T2", 2: "T3"}.get(n_gates, "T4")


def build_golden_signals() -> dict:
    syms = []
    for spec in GOLDEN_SYMBOLS:
        close = _close_window(spec["path"])
        if close is None:
            continue
        sig = canon.confluence_signals(close)
        if sig.empty:
            log.warning("insufficient history for %s in window", spec["symbol"])
            continue
        seq = _signal_sequence(sig)
        syms.append({
            "symbol": spec["symbol"],
            "region": spec["region"],
            "label": spec.get("label", spec["symbol"]),
            "window": {"start": WINDOW_START, "end": WINDOW_END,
                       "n_daily_bars": int(len(close)),
                       "first_bar": close.index[0].strftime("%Y-%m-%d"),
                       "last_bar": close.index[-1].strftime("%Y-%m-%d")},
            "inputs_hash": _inputs_hash(close),
            "n_signals": len(seq),
            "expected_sequence": seq,
        })
        log.info("  %s: %d signals over %d bars", spec["symbol"], len(seq), len(close))
    return {
        "schema": "signal_golden_vectors/v1",
        "as_of": date.today().isoformat(),
        "oracle": "engine.canon.confluence_signals",
        "math": canon.CONFLUENCE_PARAMS,
        "note": ("The dashboard is the ORACLE. A Terminal engine that reproduces this "
                 "BUY/SELL/tier sequence from the same close window (verify inputs_hash "
                 "first) is conformant; any mismatch means its confluence math drifted "
                 "(audit #7). The corrected math relocated ~80% of NVDA signal dates vs "
                 "the legacy calendar-3B resample the Terminal shipped."),
        "symbols": syms,
    }


# ── artifact manifest ─────────────────────────────────────────────────────────
# expected_max_age is in TRADING-CALENDAR days: an artifact older than this (excluding
# weekends/holidays) is genuinely stale and the consumer must abstain. A weekend-only
# lag is NOT stale (the cadence is trading-day-aware on the consumer side).
#
# R4 contract governance (NW Rails PR-7):
#   schema_version  — semver string; bump minor when fields are added (backwards-compatible),
#                     bump major when fields are removed or renamed (breaking change).
#   schema_fields   — sorted list of ACTUAL top-level JSON keys in the artifact.
#                     For list-valued artifacts where kind implies items (e.g. board),
#                     schema_item_fields lists the item-level keys (buy[] / reduce[] items).
#                     scripts/check_contract_drift.py compares these against the live artifact
#                     and exits nonzero on divergence — use --warn-only during the ratchet
#                     period, then flip to hard-fail after one clean week (see that script).
#   Per-wildcard artifacts (per_stock_intel, per_stock_signal): schema is derived from a
#   representative sample; all files in the same kind share the schema.
#
# Consumer-registry vocabulary:
#   bot:*       — the autonomous trading bot (bot.mastermind-x.com :8001, Brain BOT VPS
#                 mirror). Reads artifacts at intraday cadence. A stale or schema-drifted
#                 artifact causes the bot to abstain (fail-closed per audit #9). Known
#                 consumers: bot:conviction, bot:lenses, bot:strategist, bot:macro_risk,
#                 bot:china_book, bot:canada_book, bot:hk_book.
#   terminal:*  — the Mastermind Terminal (app.mastermind-x.com, Next.js SaaS). Reads
#                 artifacts for display and chart markers. Known consumers:
#                 terminal:pull_macro_intel (stock intel bridge), terminal:chart_markers
#                 (BUY/SELL/tier markers overlay), terminal:screener (US board candidates),
#                 terminal:regime_banner (macro regime display strip).
ARTIFACT_MANIFEST = [
    {"artifact": "site/stockdata/<SYM>.json",
     "kind": "per_stock_intel",
     "schema_version": "1.0.0",
     "schema_fields": [
         "accounting_quality", "alerts", "alpha", "altdata", "analyst", "anticipation",
         "asof", "basket_alloc", "baskets_membership", "composite", "conviction", "cycle",
         "dt_contra", "early", "earnings", "entry_signal", "factors", "financials",
         "fund_flows", "gex", "gex_confirm", "has_intraday", "history_days", "iv_spread",
         "iv_spread_confirm", "ladder", "macro_sensitivity", "mtf", "name", "positioning",
         "profile", "revisions", "risk_sizing", "season_next", "season_next_zh",
         "season_this", "season_this_zh", "sector", "smart_money", "tech", "ticker",
         "valuation", "view", "vol_squeeze",
     ],
     "expected_max_age_td": 2,
     "as_of_field": "asof",
     "consumers": ["terminal:pull_macro_intel", "bot:conviction"],
     "note": "per-stock decision/conviction/gex intel; the Terminal intel bridge reads this"},
    {"artifact": "site/signals/<SYM>.json",
     "kind": "per_stock_signal",
     "schema_version": "1.1.0",
     "schema_fields": [
         "above200", "asof", "early_markers", "early_now", "markers", "pit",
         "risk_flags", "state", "tf", "ticker", "trail_breach", "trail_stop",
         "weekly_bull",
     ],
     "expected_max_age_td": 2,
     "as_of_field": "asof",
     "consumers": ["terminal:chart_markers"],
     "note": "confluence signal state + markers (BUY/SELL/cut) per stock"},
    {"artifact": "site/factordata/us_standouts.json",
     "kind": "board",
     "schema_version": "1.2.0",
     "schema_fields": [
         "as_of", "buy", "concentration", "delta", "dispersion_regime", "donor",
         "earnings_blackout_note", "eligible", "gate_go", "laggards", "lane_counts",
         "pending_expired_count", "rank_by", "staleness", "universe", "watch",
     ],
     "schema_item_fields": [
         "above_trend", "adv_dollar_20d_median", "adv_dollar_21d", "align_tier", "alpha",
         "alpha_entry", "antichase_shadow_blocked", "composite", "conviction",
         "days_to_build_100k", "days_to_build_1m", "days_to_exit_at_10pct_adv", "dd_pct",
         "dir", "entry_signal", "eq_dir", "f1d_shadow_bonus", "f1d_shadow_c6",
         "f1d_shadow_rank", "factor_z", "hold", "label", "label_zh", "lane",
         "liquidity_tier", "name", "off_high", "price", "risk_sizing", "sector",
         "sector_n", "sector_pulse", "sector_rank", "setup", "signal", "spark_svg",
         "state", "stop_guidance", "sue_fresh_days", "ticker", "urgency",
         "washout_active", "weekly_phase",
     ],
     "expected_max_age_td": 2,
     "as_of_field": "as_of",
     "consumers": ["bot:lenses", "bot:strategist", "terminal:screener"],
     "note": "US Buy Board — sizes the autonomous book's US candidate universe"},
    {"artifact": "site/factordata/china_standouts.json",
     "kind": "board",
     "schema_version": "1.1.0",
     "schema_fields": [
         "as_of", "board_track", "buy", "cap_composition", "coverage",
         "dispersion_regime", "eligible", "laggards", "quality_screen", "qvix_regime",
         "ran", "rank_by", "ripening", "ripening_falling", "sleeve_chip", "universe",
     ],
     "schema_item_fields": [
         "ab_tier", "align_tier", "alpha", "alpha_entry", "coiled", "conviction",
         "data_through", "dir", "entry_signal", "eq_dir", "extension", "hold", "label",
         "label_zh", "name", "narrative", "off_high", "price", "risk_sizing", "sector",
         "sector_n", "sector_rank", "sector_turn", "setup", "signal", "spark_svg",
         "stage", "stage_detail", "stage_sublabel", "stage_sublabel_zh", "state",
         "ticker", "urgency", "washout_2w", "why_ranked",
     ],
     "expected_max_age_td": 3,
     "as_of_field": "as_of",
     "consumers": ["bot:china_book"],
     "note": "Prophet China board; CN calendar has more holidays → wider cadence"},
    {"artifact": "site/factordata/canada_standouts.json",
     "kind": "board",
     "schema_version": "1.0.0",
     "schema_fields": [
         "as_of", "branch", "buy", "confluence", "dispersion_regime", "eligible",
         "laggards", "rank_basis", "universe",
     ],
     "schema_item_fields": [
         "align_tier", "alpha", "alpha_entry", "board_pos", "conviction", "dir",
         "earnings", "entry_signal", "eq_dir", "factor_beta", "group", "hold",
         "insider", "label", "label_zh", "lead_en", "lead_zh", "name", "off_high",
         "oil_tailwind", "price", "risk_sizing", "sector", "sector_n", "sector_rank",
         "setup", "signal", "spark_svg", "state", "ticker", "urgency",
     ],
     "expected_max_age_td": 2,
     "as_of_field": "as_of",
     "consumers": ["bot:canada_book"],
     "note": "Prophet Canada board"},
    {"artifact": "site/regime_timeline.json",
     "kind": "regime",
     "schema_version": "1.0.0",
     "schema_fields": [
         "conf", "cyc", "dates", "flag_order", "flags", "g", "i", "liq", "quad",
         "rec", "shock", "trans",
     ],
     "expected_max_age_td": 2,
     "as_of_field": None,
     "consumers": ["bot:macro_risk", "terminal:regime_banner"],
     "note": "US regime/quad timeline; as_of = last entry of the `dates` array"},
    {"artifact": "site/china_regime_timeline.json",
     "kind": "regime",
     "schema_version": "1.0.0",
     "schema_fields": [
         "conf", "cyc", "dates", "flag_order", "flags", "g", "i", "liq", "quad",
         "rec", "shock", "trans",
     ],
     "expected_max_age_td": 3,
     "as_of_field": None,
     "consumers": ["bot:china_book"],
     "note": "China regime timeline"},
    {"artifact": "site/hk_regime_timeline.json",
     "kind": "regime",
     "schema_version": "1.0.0",
     "schema_fields": [
         "conf", "cyc", "dates", "flag_order", "flags", "g", "i", "liq", "quad",
         "rec", "shock", "trans",
     ],
     "expected_max_age_td": 3,
     "as_of_field": None,
     "consumers": ["bot:hk_book"],
     "note": "HK regime timeline"},
]


def build_manifest() -> dict:
    return {
        "schema": "artifact_manifest/v1",
        "as_of": date.today().isoformat(),
        "cadence_basis": "trading_calendar",
        "note": ("Per-artifact expected freshness in TRADING-calendar days. A consumer "
                 "compares the artifact's as_of against `today` counting only trading days; "
                 "older than expected_max_age_td ⇒ abstain + flag (fail-closed on genuine "
                 "staleness, audit #9). Benign weekend/holiday lag is NOT stale because the "
                 "cadence excludes non-trading days."),
        "artifacts": ARTIFACT_MANIFEST,
    }


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    OUT.mkdir(parents=True, exist_ok=True)

    golden = build_golden_signals()
    (OUT / "golden_signals.json").write_text(json.dumps(golden, indent=1))
    manifest = build_manifest()
    (OUT / "artifact_manifest.json").write_text(json.dumps(manifest, indent=1))

    n_syms = len(golden["symbols"])
    n_sig = sum(s["n_signals"] for s in golden["symbols"])
    print(f"\nwrote {OUT}/golden_signals.json  ({n_syms} symbols, {n_sig} total signals)")
    print(f"wrote {OUT}/artifact_manifest.json ({len(manifest['artifacts'])} artifacts)")
    for s in golden["symbols"]:
        print(f"  {s['symbol']:10s} {s['region']:3s} {s['n_signals']:3d} signals "
              f"[{s['window']['first_bar']} → {s['window']['last_bar']}]")


if __name__ == "__main__":
    main()
