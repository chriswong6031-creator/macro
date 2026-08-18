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
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from engine import canon  # noqa: E402

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
#   schema_fields   — sorted list of ALWAYS-PRESENT (required) top-level JSON keys.
#                     For list-valued artifacts where kind implies items (e.g. board),
#                     schema_item_fields lists the item-level keys (buy[] / reduce[] items).
#                     scripts/check_contract_drift.py compares these against the live artifact
#                     and exits nonzero on divergence — use --warn-only during the ratchet
#                     period, then flip to hard-fail after one clean week (see that script).
#   optional_fields — sorted list of CONDITIONAL top-level keys the builder emits only when
#                     a data condition holds (present some nights, absent others by design).
#                     Documented for consumers but EXCLUDED from drift (present-or-absent is
#                     fine); a conditional field belongs here, NOT in schema_fields, or it
#                     flaps the drift lane red↔green with the data. A key in NEITHER list is
#                     undocumented and still trips `added` drift. An ITEM-level key that is
#                     emitted on only one of an artifact's arrays (us_standouts `anchor`,
#                     ran[] rows only) may also be registered here as the contract's
#                     may-be-absent notice to consumers — check_contract_drift reads
#                     top-level keys only, so this exempts nothing it would otherwise catch.
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
    # 1.1.0 -> 1.2.0 (2026-08-07): the anchor-era programme stamps `anchor_era` on
    # every per-stock signal file. REQUIRED, not conditional — measured present on
    # 240/240 committed site/signals/*.json.
    # 1.2.0 -> 1.3.0 (2026-08-11): `early_signal_dates` — the ADDITIVE knowability stamp
    # for the dots (§6.7 family) — registered as OPTIONAL. The producer
    # (engine.signal_quality.analyze) emits it ALL-OR-NOTHING: `stamped = all(x is not
    # None for x in early_signal_dates)`, and the key is omitted whenever any dot's bucket
    # did not resolve a last session, because a partially-resolved list would silently
    # re-index every pair. A conditional key belongs in optional_fields per this file's own
    # law above — registering it as REQUIRED would have flipped the drift lane red on the
    # next manifest regeneration against all 241 committed site/signals/*.json (none of
    # which carry the field yet) and then flapped with the data forever after. Minor bump:
    # the change is additive and backwards-compatible.
    {"artifact": "site/signals/<SYM>.json",
     "kind": "per_stock_signal",
     "schema_version": "1.3.0",
     "schema_fields": [
         "above200", "anchor_era", "asof", "early_markers", "early_now",
         "markers", "pit", "risk_flags", "state", "tf", "ticker",
         "trail_breach", "trail_stop", "weekly_bull",
     ],
     "optional_fields": [
         "early_signal_dates",
     ],
     "expected_max_age_td": 2,
     "as_of_field": "asof",
     "consumers": ["terminal:chart_markers"],
     "note": "confluence signal state + markers (BUY/SELL/cut) per stock"},
    # 1.3.0 -> 1.4.0 (2026-08-02, us_prophet_v1): the board gained a priority
    # ranking. New top-level keys board_definition / ranking / ran /
    # themes_in_favour; new per-row keys stage, featured, new, score_rank,
    # display_rank, prophet, theme, signal_asof, days_since_signal. Additive —
    # nothing was removed or renamed, and buy-lane MEMBERSHIP is unchanged.
    # 1.4.0 -> 1.5.0 (2026-08-02, review pass): two per-row disclosure keys, both
    # additive. `anchor` ("marker"|"approx") on every ran[] row says how that row's
    # cross age was anchored — the ran lane now DROPS a row whose cross cannot be
    # anchored at all rather than rendering an age derived from the tick count, so
    # a present row's `sessions_since` is trustworthy and `anchor` says how much.
    # `days_since_signal_basis` ("sessions"|"calendar") discloses the units of
    # days_since_signal, which the shared stocktable.js NEW-dot filter reads as
    # sessions; the US board now answers in sessions whenever the verdict carries a
    # marker-anchored fresh_bars count and labels the calendar fallback.
    # `ranking.component_coverage` also lands here (inside the existing `ranking`
    # object, so it adds no top-level or item-level key).
    # 1.6.0 -> 1.7.0 (2026-08-04, prophet-us W4): two DISPLAY-TIER per-row keys, both
    # additive and both conditional. `post_earnings_move` ({date, day0, day0_move_pct,
    # basis, ...}) is attached only when the name reported inside the trailing 5
    # sessions. It is deliberately NOT called `earnings_reaction` — that token is the
    # hot-tape lane's TRIGGER name (engine/marketing/hot_tape.py) for a related but
    # different thing, and one token across two artifact vocabularies makes every future
    # grep ambiguous. `earnings_soon` has shipped since MLC-W5 but was never registered; W4
    # documents it and widens it — besides the existing CHIP shape (days_to + chip_en/
    # chip_zh, unchanged) it now also carries a DISCLOSURE shape on a row whose store
    # stamp has aged past 10 sessions: days_to_report=null, reports_within_7=null,
    # stale=true, no days_to and no chip text. Nothing scores, ranks, or gates on either
    # key; the earnings-blackout veto (engine/earnings_blackout.assess) is unchanged,
    # including its fail-open behaviour on a stale row. Both are registered in
    # optional_fields (the may-be-absent register) rather than promoted; graduation to a
    # required item field waits on a committed render that proves the builder emits them.
    # 1.7.0 -> 1.8.0 (2026-08-07): `universe_sources` registered as OPTIONAL (see the
    # note in optional_fields below for why it is not required).
    # 1.8.0 -> 1.9.0 (2026-08-11): `candidate_pool` is the lossless,
    # display-only US candidate-lane disclosure.  The board builder deliberately
    # wraps it in a fail-open try/except, so absence means the additive disclosure
    # failed; it cannot be promoted to a required field.
    # 1.9.0 -> 1.10.0 (2026-08-14): `emit` is the board/signal-gate lineage stamp.
    # The builder assigns it unconditionally immediately before the sole board
    # write, so it is a required top-level field rather than an optional one.
    {"artifact": "site/factordata/us_standouts.json",
     "kind": "board",
     "schema_version": "1.10.0",
     "schema_fields": [
         # 1.6.0 GRADUATION (2026-08-03): board_definition / ran / ranking /
         # themes_in_favour moved up from optional_fields after the first committed
         # us_prophet_v1 render (engine-render on main, as_of 2026-07-31,
         # rank_by=us_prophet_v1) proved the builder emits all four unconditionally
         # — the same order china_standouts reached 2.0.0 in.
         "as_of", "board_definition", "buy", "concentration", "delta",
         "dispersion_regime", "donor", "earnings_blackout_note", "eligible", "emit",
         "gate_go", "laggards", "lane_counts", "leaders", "pending_expired_count",
         "ran", "rank_by", "ranking", "staleness", "themes_in_favour", "universe",
         "watch",
     ],
     "optional_fields": [
         # `anchor` is a ran[] ITEM key, registered here as well as in
         # schema_item_fields because it is the contract's may-be-absent register
         # and `anchor` is emitted only on ran rows (buy rows carry no cross
         # anchor). check_contract_drift compares TOP-LEVEL keys only, so listing
         # an item key here exempts nothing that would otherwise be caught — it
         # documents conditionality for consumers.
         # `earnings_soon` / `post_earnings_move` are likewise ITEM keys (W4): both are
         # attached per row only when the earnings store can answer for that name, so a
         # consumer must treat both as may-be-absent and must not infer "no report
         # scheduled" from their absence.
         # `universe_sources` (2026-08-07) is the universe-source disclosure. OPTIONAL,
         # not required: build_stock_library emits it inside a try/except whose handler
         # is explicit that the key is dropped on failure ("disclosure is additive, never
         # fatal" -> "block absent from artifact"). Registering it in schema_fields would
         # flap this lane red<->green with that failure, which is exactly what
         # optional_fields exists to prevent. Consumers must not read its absence as a
         # complete universe — absence means the disclosure itself failed.
         # (List order is alphabetical — test_contract_drift asserts it sorted.)
         "anchor", "candidate_pool", "earnings_soon", "post_earnings_move",
         "universe_sources",
     ],
     "schema_item_fields": [
         "above_trend", "adv_dollar_20d_median", "adv_dollar_21d", "align_tier", "alpha",
         "alpha_entry", "anchor", "antichase_shadow_blocked", "composite", "conviction",
         "cross_date", "days_since_signal", "days_since_signal_basis",
         "days_to_build_100k", "days_to_build_1m",
         "days_to_exit_at_10pct_adv", "dd_pct", "dir", "display_rank",
         "earnings_soon", "entry_signal",
         "eq_dir", "f1d_shadow_bonus", "f1d_shadow_c6", "f1d_shadow_rank", "factor_z",
         "featured", "featured_blocked_by", "hold", "label", "label_zh", "lane",
         "liquidity_tier", "name", "new", "off_high", "pct_since",
         "post_earnings_move", "price", "prophet",
         "risk_sizing", "score_rank", "sector", "sector_n", "sector_pulse",
         "sector_rank", "sessions_since", "setup", "signal", "signal_asof",
         "spark_svg", "stage", "state", "stop_guidance", "sue_fresh_days", "theme",
         "theme_confirmed", "theme_note", "theme_note_zh", "ticker", "ticks",
         "urgency", "washout_active", "weekly_phase",
     ],
     "expected_max_age_td": 2,
     "as_of_field": "as_of",
     "consumers": ["bot:lenses", "bot:strategist", "terminal:screener"],
     "note": "US Buy Board — sizes the autonomous book's US candidate universe"},
    # 2.1.0 -> 2.2.0 (2026-08-07): `staleness` (the price-age disclosure) is REQUIRED,
    # not conditional. build_china_library computes it "with the other conservative
    # defaults so the key always exists on the artifact" and is fail-soft INSIDE, so a
    # failure empties the disclosure rather than dropping the key — and the zero-collapse
    # fallback carries `"staleness": compute_board_staleness()` for the same reason
    # ("a zero-name collapse is exactly when the reader most needs to know").
    {"artifact": "site/factordata/china_standouts.json",
     "kind": "board",
     "schema_version": "2.2.0",
     "schema_fields": [
         "actionable", "as_of", "board_definition", "buy", "cap_composition",
         "coverage", "eligible", "execution_coverage", "forming", "laggards",
         "lane_counts", "late_or_unfillable", "more_actionable", "quality_screen",
         "ran", "rank_by", "ranking", "ripening", "ripening_falling",
         "schema_version", "sleeve_chip", "staleness", "track_ledger", "universe",
     ],
     "optional_fields": [
         # data_outage — W0.7 board-width guard stamp, present only on a collapsed
         # board (>40% day-over-day buy-count drop); conditional-by-design.
         # reversal_watch — the measurement-only washout shelf; present on normal
         # builds but absent from the explicit zero-universe outage shell.
         # reversal_ledger — fail-soft companion ledger; absent when its isolated
         # emitter cannot produce a document.
         # watch — compatibility union of the explicit v2 secondary lanes
         # (more_actionable + late_or_unfillable + forming).  New consumers must use
         # the explicit lanes; the alias keeps older bots/microstructure collectors
         # lossless during migration.
         # (List order is alphabetical — test_contract_drift asserts optional_fields sorted.)
         "board_track", "data_outage", "definition_change", "dispersion_regime",
         "qvix_regime", "reversal_ledger", "reversal_watch", "watch",
     ],
     "schema_item_fields": [
         "ab_tier", "adv_yi", "align_tier", "alpha", "alpha_entry",
         # V4: board_rank is the live display/admission ORDER (interest, then v3
         # score); score_rank below stays the v3 SCORE order. intel* carry the
         # board-independent interest receipt and its basis.
         "board_definition", "board_rank", "cap_bucket", "coiled", "conviction",
         "data_through",
         "days_since_signal", "dir", "display_rank", "entry_signal", "eq_dir",
         "extension", "hold", "intel", "intel_interest_basis",
         "intel_interest_score", "label", "label_zh", "lane", "lane_reasons",
         "macd_d2", "macd_d3", "macd_hist_d", "mcap", "microstructure",
         "muted_entry", "name", "narrative", "off_high", "price", "prophet",
         "quality", "rev_percentile", "rev_z",
         "reversal_member", "reversal_sector_n", "reversal_sector_rank",
         "risk_sizing", "score_rank", "sector", "sector_n", "sector_rank",
         "sector_turn", "setup", "signal", "spark_svg", "stage", "stage_detail",
         "stage_sublabel", "stage_sublabel_zh", "state", "ticker", "urgency",
         "washout_2w", "why_ranked",
     ],
     "expected_max_age_td": 3,
     "as_of_field": "as_of",
     "consumers": ["bot:china_book"],
     "note": "Prophet China board; CN calendar has more holidays → wider cadence"},
    {"artifact": "site/factordata/canada_standouts.json",
     "kind": "board",
     "schema_version": "1.2.0",
     "schema_fields": [
         "as_of", "branch", "buy", "confluence", "eligible",
         "laggards", "rank_basis", "universe",
     ],
     "optional_fields": [
         # dispersion_regime — build_canada_library.py:1136 `if disp_regime:` (only when
         # the selection-regime dispersion dial computes). sector_concentration —
         # build_canada_library.py:700 `if _sc:` (only when >60% of the board clusters in
         # one sector). Both are conditional-by-design: present on concentrated/regime-on
         # nights, absent otherwise. Kept OUT of schema_fields so the drift lane does not
         # flap red↔green with the tape (were wrongly required in 1.1.0 / #3289 — that lane
         # went red on the first diversified-board nightly after).
         "dispersion_regime", "sector_concentration",
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
     "note": ("Prophet Canada board. dispersion_regime + sector_concentration are "
              "conditional (optional_fields) — bot:canada_book must treat both as "
              "may-be-absent, unchanged from prior behaviour (they were always emitted "
              "conditionally; 1.2.0 only corrects the contract classification)")},
    {"artifact": "site/data/portfolio_ctx.json",
     "kind": "context",
     # 1.1.0 (PSI-W2, 2026-08-07): MINOR — one top-level field ADDED (`market`), every
     # 1.0.0 field kept with its exact shape and meaning. `market` is unconditional (it is
     # {} when no tape-context source resolves, exactly like `regime`/`sectors`), so it
     # belongs in schema_fields as REQUIRED — not in optional_fields, which is for keys the
     # builder emits only when a data condition holds.
     "schema_version": "1.1.0",
     "schema_fields": [
         "asof", "built", "coverage", "gate_go", "market", "regime", "schema",
         "sectors", "tickers", "v",
     ],
     # W1: nightly-wired (daily.yml engine job, serial step after build_sector_central).
     # 2 trading days = one nightly + a weekend/holiday cushion (same bar as the other
     # daily-baked context artifacts).
     "expected_max_age_td": 2,
     "as_of_field": "asof",
     "consumers": ["terminal:portfolio"],
     "note": ("Portfolio-Aware Intelligence per-ticker context (charter: "
              "research/PORTFOLIO_BRIEF_MASTERPLAN_BY_FABLE.md §2). Re-expresses "
              "existing nightly reads keyed by ticker; the terminal Portfolio page "
              "composes each user's brief on demand off the render path. W1 = "
              "full-universe nightly bake (daily.yml, after build_sector_central). "
              "PSI-W2 (schema portfolio_ctx.v2, charter "
              "research/PORTFOLIO_SUPERINTELLIGENCE_MASTERPLAN_BY_FABLE.md §5.1/§9) is "
              "ADDITIVE: per-ticker tech/msens/fq/pers/dossier state blocks, the new "
              "top-level `market` tape-context block, and coverage counts per block. "
              "Consumers feature-detect on `schema`; every v1 key is unchanged.")},
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
    # 1.0.0 (2026-08-02, hk_prophet_v1): first registration of the HK Stock Desk
    # board. The artifact has shipped for months but was never in this manifest, so
    # it had no drift guard at all — registering it now is the guard, and the
    # priority-ranking keys land in optional_fields for the usual transition window
    # (the contract lands one render BEFORE the artifact carrying them; a required
    # field the artifact has not been rebuilt with yet reads as `removed` drift).
    # They GRADUATE to schema_fields on a minor bump once the first hk_prophet_v1
    # render is committed — the same order us_standouts reached 1.5.0 in.
    # 1.0.0 -> 1.1.0 (2026-08-07): `ripening` registered as optional (see below).
    {"artifact": "site/factordata/hk_standouts.json",
     "kind": "board",
     "schema_version": "1.1.0",
     "schema_fields": [
         "as_of", "board_track", "buy", "calm", "cohort", "context_chips",
         "eligible", "health", "laggards", "leadership", "liquidity_regime",
         "overlay", "risk_state", "southbound_summary", "universe",
         "washout_watch", "watch",
     ],
     "optional_fields": [
         # dispersion_regime — build_hk_library.py `if disp_regime:` (only when the
         # selection-regime dial computes); conditional-by-design, as on the Canada
         # board. The rest are the hk_prophet_v1 additions described above:
         #   board_definition / rank_by / ranking  the priority score + its receipt
         #   lane_counts                            per-lane + per-stage counts
         #   leaders / ran / vetoed                 the three display-tier lanes
         #   universe_excluded / universe_source_rows  the disclosed universe gap
         #   ripening (2026-08-07)                  the HK ripening shelf
         # `ripening` is emitted unconditionally — a plain key in build_hk_library's
         # payload literal, beside leaders/ran/vetoed — so it is registered HERE rather
         # than in schema_fields for the same reason those three are: this entry is still
         # at the pre-graduation stage described above, and the whole hk_prophet_v1 group
         # graduates together on one minor bump once the first render is committed.
         # Splitting it out early would claim a guarantee the rest of its own wave does
         # not yet carry.
         # (List order is alphabetical — test_contract_drift asserts it sorted.)
         "board_definition", "dispersion_regime", "lane_counts", "leaders",
         "ran", "rank_by", "ranking", "ripening", "universe_excluded",
         "universe_source_rows", "vetoed",
     ],
     "schema_item_fields": [
         "ah_value", "align_tier", "alpha", "alpha_entry", "anchor", "beta",
         "blocked_reason_en", "blocked_reason_zh", "conviction",
         "days_since_signal", "days_since_signal_basis", "dir", "display_only",
         "display_rank", "dist_200dma", "edge_basis", "edge_z", "entry_signal",
         "entry_window", "extended", "featured", "featured_blocked_by", "group",
         # knife_risk — the H4 deepest-3M-quintile CLASS, stamped on every row of
         #   every cohort (knife_demoted is the narrower "this buy was pushed to the
         #   watch strip"). scripts/build_hk_pick_lab reads this, not lane membership.
         # laggard_z — the resolved laggards SORT KEY, stamped on laggards[] rows so
         #   the strip prints the number it was ordered by.
         "in_leadership_cohort", "knife_demoted", "knife_risk", "knife_z",
         "label", "label_zh", "laggard_z",
         "lane", "lead", "leadership", "momentum_z", "name", "name_zh", "off_high",
         "pct_since", "placement_flag", "price", "prophet", "rank_key",
         "reason_raw", "risk_sizing", "role", "rsi", "score_rank", "sector",
         "sector_n", "sector_rank", "sector_zh", "sessions_since", "sfc_short",
         "signal", "signal_asof", "signal_date", "southbound", "spark_svg",
         "stage", "stance", "stance_zh", "ticker", "ticks", "tilt", "washout_2w",
         "watch_reason",
     ],
     "expected_max_age_td": 3,
     "as_of_field": "as_of",
     "consumers": ["bot:hk_book"],
     "note": "HK Stock Desk board; leaders/ran/vetoed are display-tier context "
             "lanes carrying no entry claim"},
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
    # 1.0.0 (2026-08-13, prophet §J.9(c) PR-0(c)): first registration of the Prophet
    # plan book. Like hk_standouts above, the artifact has shipped for months with NO
    # drift guard at all — registering it now IS the guard. The ruling
    # (research/PROPHET_RULING_J9C_J10_LIFECYCLE_CELLS.md §8) directs the additive
    # lifecycle keys through "the optional-fields path with a schema version bump and
    # manifest regen"; there was no prior entry to bump, so this is a 1.0.0 first
    # registration and the three `lifecycle_*` keys land in optional_fields for the
    # usual transition window — the contract lands one render BEFORE the artifact
    # carrying them, and a required field the artifact has not been rebuilt with yet
    # reads as `removed` drift (the #5395 J-15 lesson exactly). They GRADUATE to
    # schema_fields on a minor bump once the first nightly bake carrying them is
    # committed. `origination_disclosure` is conditional BY DESIGN and stays optional
    # permanently: build_prophet.py sets it after the index literal precisely so the
    # key is absent, not present-and-null, on a night nothing was reconstructed.
    #
    # as_of_field is `source_asof`, NOT `asof`: build_prophet.py documents `asof` as a
    # compatibility run clock that a successful rerun can refresh while its INPUT
    # freezes, so a freshness read against it can score green on stale data.
    {"artifact": "site/prophet/index.json",
     "kind": "plan_book",
     "schema_version": "1.1.0",
     "schema_fields": [
         "active_count", "active_count_by_age", "asof", "authority_tier", "cadence",
         "gate_go", "intake", "ledger_corrections", "ledger_quarantine", "note",
         "open_count", "plan_count", "plan_integrity", "plans", "plans_sort_key",
         "record", "recorded_at", "schema", "selection_era", "source_asof",
         "source_basis", "source_board_asof", "source_delayed", "source_mixed_vintage",
         "source_unknown",
     ],
     "optional_fields": [
         # G-D Board read (engine/prophet_board_read.py). CONDITIONAL, not required:
         # build_prophet stamps both inside a try/except (scripts/build_prophet.py
         # :2671-2678), so a night whose library/standouts read degrades ships the
         # index WITHOUT them. Registering them under schema_fields would turn that
         # degraded night into a drift red in the opposite direction — the
         # red-flips-with-the-data shape optional_fields exists to prevent.
         "board_read_coverage", "board_read_lineage",
         "lifecycle_counts", "lifecycle_grand_total", "lifecycle_live_total",
         "origination_disclosure",
     ],
     "expected_max_age_td": 2,
     "as_of_field": "source_asof",
     "consumers": ["terminal:oracle-tab"],
     "note": "Prophet plan book — every active plan with its management state inline. "
             "authority_tier=display; the lifecycle_* keys are a derived display-tier "
             "projection over phase/closed and carry no engine judgment"},
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
