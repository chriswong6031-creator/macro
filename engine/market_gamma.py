"""Whole-market dealer-gamma vol regime — the SINGLE SHARED deriver behind both the
dashboard banner (scripts/build_site.py) and the machine-readable contract
(data/regime/latest.json, via engine/run.py), so the two can never drift.

Reads the VALIDATED index dealer-gamma store (SPX, data/cboe/gex — the same that
drives the dealer-gamma board, computed by engine.gex_engine). ABOVE the gamma-flip
strike dealers are net long gamma and hedge AGAINST price (pinning / vol suppressed);
BELOW it they are short gamma and hedge WITH price (amplifying moves) — the air-pocket
precondition. A whole-market vol CONTEXT, not a per-stock signal, and an estimate from
delayed CBOE chains, not ground truth.

Degrade-never-raise: returns None when the store is missing / empty / NaN (callers
simply render or serialize nothing). Unlike the episodic `gex_flip_cross` ALERT, this
verdict is STEADY-STATE: it reports the standing regime every build, with no crossing
required, so a downstream consumer reads "dealers short gamma" from a structured field
instead of parsing an alert string."""
from __future__ import annotations

from datetime import datetime

import pandas as pd

from lib import nyse_calendar, store

# Reconstructed index dealer-gamma history (scripts/build_index_gex_history.py). SPY is
# the S&P index proxy comparable to the SPX-based cboe/gex current-day source used by
# view(); the reconstructed series supplies LEVELS/VOL CONTEXT ONLY (net-GEX percentile
# vs own multi-year history, standing-regime persistence) — DISPLAY-ONLY, no score path.
_HISTORY_ROOT = "SPY"
_HISTORY_GROUP = "index_gex_history"

# WINDOW DISCLOSURE (OIP E3c, 2026-07-29). The reconstruction only runs where the
# ThetaData EOD store lives (the M1 ops host), so a missed run FREEZES this series
# while the percentile below keeps computing happily against the stale distribution.
# Before this, nothing in the artifact said how old the window was: the store sat at
# 2026-07-02 for 18 sessions and the context block read as current. It now carries
# window bounds, a session-count lag and a plain-word EN/ZH pair. The reconstruction
# is a WEEKLY job (ops/launchd/com.macro.indexgexhistory.plist), so ~5 sessions of lag
# is normal — hence the threshold below rather than "anything but today is stale".
# Deliberately CALM language (§0.7): a window statement, never a red alarm.
_STALE_SESSIONS = 7


def _history_context(current_net_gex_bn: "float | None",
                     current_regime: "str | None",
                     now: "datetime | None" = None) -> dict | None:
    """Multi-year vol CONTEXT from the reconstructed SPY history: where the reconstructed
    net-GEX sits in its OWN 2017-> distribution, and how long the standing regime has held.

    SCALE NOTE (why we percentile the reconstructed series against ITSELF, not the
    current-day SPX value against it): the current-day source is the SPX-based cboe/gex
    store, whose net-GEX $ level is on a different scale than the reconstructed SPY-ETF
    series — a raw percentile of the SPX level against SPY history would be a category
    error. So `net_gex_pctile` is the reconstruction's own latest value vs its own history
    (apples-to-apples); `current_regime` (SPX) is only cross-checked against the
    reconstructed regime for AGREEMENT. Returns None (graceful fallback) when the history
    store is absent/empty so snapshot() degrades to the pre-upgrade current-day-only verdict.

    `now` is injectable so the staleness disclosure is deterministic under test."""
    hist = store.read(_HISTORY_GROUP, _HISTORY_ROOT)
    if hist is None or not len(hist) or "net_gex_bn" not in hist.columns:
        return None
    # Session guard as above. This store is reconstructed and mostly clean — as measured
    # on 2026-07-29 it held 2388 rows spanning 2017-01-03 -> 2026-07-02 with exactly ONE
    # non-session row, dated 2019-02-02 (a Saturday). But the percentile below is an
    # own-history distribution and `.iloc[-1]` is the standing reading, so both must be
    # session-true by construction, not by luck of which rows the reconstruction emitted.
    hist = nyse_calendar.session_rows(hist, label="index_gex_history/SPY")
    ng = pd.to_numeric(hist["net_gex_bn"], errors="coerce").dropna()
    hist_start = str(hist.index.min().date())
    hist_end = str(hist.index.max().date())
    ctx: dict = {
        "source": f"{_HISTORY_GROUP}/{_HISTORY_ROOT}",
        "reconstructed": True,
        "n_days": int(len(ng)),
        "hist_start": hist_start,
        "hist_end": hist_end,
    }
    # ── window / staleness disclosure (plain words, calm) ────────────────────
    try:
        sessions_behind = int(nyse_calendar.sessions_behind(hist.index.max().date(), now))
    except Exception:  # noqa: BLE001 — a calendar hiccup must not drop the whole context
        sessions_behind = None
    ctx["sessions_behind"] = sessions_behind
    ctx["stale"] = (sessions_behind is not None and sessions_behind > _STALE_SESSIONS)
    if sessions_behind is None:
        lag_en, lag_zh = "", ""
    elif ctx["stale"]:
        lag_en = f" — {sessions_behind} trading sessions behind the latest close"
        lag_zh = f" — 比最近收盘落后 {sessions_behind} 个交易日"
    else:
        lag_en, lag_zh = " and is current", "，数据为最新"
    ctx["note_en"] = (
        f"The rebuilt multi-year record covers {hist_start} through {hist_end}{lag_en}. "
        "The placement below compares that rebuilt record against itself, not against "
        "today's reading.")
    ctx["note_zh"] = (
        f"重建的多年记录覆盖 {hist_start} 至 {hist_end}{lag_zh}。"
        "下方的定位是该重建记录与自身的比较，不是与今日读数的比较。")
    # Own-history percentile of the RECONSTRUCTED latest net-GEX (not the SPX current-day).
    if len(ng):
        latest = float(ng.iloc[-1])
        ctx["net_gex_latest_bn"] = round(latest, 3)
        ctx["net_gex_pctile"] = round(float((ng <= latest).mean() * 100.0), 1)
    # Standing-regime persistence in the reconstructed series + agreement with current-day.
    if "gamma_regime" in hist.columns:
        reg = hist["gamma_regime"].astype("object")
        recon_regime = None if reg.empty else str(reg.iloc[-1])
        ctx["recon_regime_last"] = recon_regime
        run = 0
        for v in reversed(list(reg.values)):
            if recon_regime is not None and v == recon_regime:
                run += 1
            else:
                break
        ctx["regime_persistence_days"] = int(run)
        if current_regime is not None and recon_regime is not None:
            ctx["regime_agrees_current"] = bool(recon_regime == current_regime)
    return ctx


def view(gex: "pd.DataFrame | None") -> dict | None:
    """Pure deriver over the cboe/gex frame -> structured dealer-gamma verdict.
    Uses the flip side (spot vs flip), the engine's authoritative regime, NOT the
    coarse net-$ sign the ETF-flows board flags — they answer different questions."""
    if gex is None or not len(gex):
        return None
    # SESSION GUARD (#3721 class, OIP E8 2026-07-29). data/cboe/gex.parquet accrues rows
    # on non-session days — 13 of 39 as of this writing — and those rows RECOMPUTE
    # spot_vs_flip_pct / flip_strike / net_gex_bn off a stale carried-forward spot rather
    # than skipping the day. Unfiltered, `.iloc[-1]` hands the dashboard banner AND
    # latest['market_gamma'] a fabricated Saturday reading every weekend and Monday
    # morning. build_market_structure._read_gex_spx already filters its twin store
    # (gex_SPX.parquet) for exactly this reason; this reader was missed.
    # Fail-open: session_rows returns the frame unchanged if filtering would empty it.
    gex = nyse_calendar.session_rows(gex, label="cboe/gex")
    g = gex.iloc[-1]
    svf = g.get("spot_vs_flip_pct")
    if svf is None or pd.isna(svf):
        return None
    flip = int(round(float(g.get("flip_strike") or 0)))
    return {
        "regime": "short" if float(svf) < 0 else "long",  # spot<flip -> dealers amplify
        "spot_vs_flip_pct": round(float(svf), 1),
        "net_gex_bn": round(float(g.get("net_gex_bn") or 0), 0),
        "flip": flip,            # FE banner key (market_gamma.flip in dashboard.html.j2)
        "gamma_flip": flip,      # contract alias (engine.gex_engine naming)
        "flip_strike": flip,     # contract alias (cboe/gex store column naming)
        "spot": int(round(float(g.get("spot") or 0))),
        "asof": str(gex.index.max().date()),
    }


def snapshot(now: "datetime | None" = None) -> dict | None:
    """Read the cboe/gex store and derive the verdict — the entry point for the
    machine-readable contract (engine/run.py writes this into latest['market_gamma']).
    None when the store is absent/empty so the leaf degrades to a null contract field.

    P1.1b upgrade: the CBOE/polygon current-day path stays the source of today's regime,
    flip and net-GEX (view() is unchanged); we ADD a `context` block derived from the
    reconstructed multi-year SPY history — net-GEX percentile vs own history + standing-
    regime persistence. DISPLAY-ONLY vol context, never a score input. When the history
    store is absent, `context` is None and the verdict is byte-identical to pre-upgrade.

    OIP E3c: when the history store IS present, `context` additionally carries the
    window bounds, how many trading sessions behind the latest close it sits, and a
    plain-word EN/ZH disclosure. `now` is injectable for deterministic tests."""
    verdict = view(store.read("cboe", "gex"))
    if verdict is None:
        return None
    verdict["context"] = _history_context(verdict.get("net_gex_bn"),
                                          verdict.get("regime"), now)
    return verdict
