"""Falsifier tripwire compiler & evaluator — D3-W3.3.

This module:

1. Loads data/cycle_ontology/falsifiers.json (the compiled DSL registry).
2. Evaluates each tripwire's DSL expression against collected series data,
   returning per-tripwire {state, fired_on, latched, current_leg, details}.
3. Persists latch state across builds (FIRED is sticky until version bump).
4. Emits new-fire alerts through the existing alerts.py pipeline.

States:
  ARMED        — DSL has live feeds; expression has NOT fired
  FIRED        — expression fired (and latched); shows current_leg for recovery info
  EXPIRED      — wall-clock > tripwire.expires
  DATA_MISSING — one or more series is stale (>5 trading days old)
  MANUAL       — no compilable legs (coverage=none); shows TTL countdown

Ruling A17 (FIRED + current-leg):
  A FIRED latch persists (un-fire = version bump to v(N+1)).
  BUT the result always carries `current_leg` = live re-evaluation, so a
  recovered thesis shows "fired {date}; condition no longer met" rather than
  silence.

Staleness measured in TRADING DAYS via pd.bdate_range (not calendar days) to
avoid the R2 holiday-week false-alarm trap documented in the memory notes.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import date, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from lib import config, store

log = logging.getLogger("falsifier_tripwires")

# ── paths ─────────────────────────────────────────────────────────────────────
_DATA = Path("data/cycle_ontology")
_FALSIFIERS_JSON = _DATA / "falsifiers.json"
_STATE_JSON = _DATA / "tripwire_state.json"

# staleness threshold in TRADING DAYS (pd.bdate_range — holiday-week aware)
_STALE_TRADING_DAYS = 5


# ── result dataclass ──────────────────────────────────────────────────────────
@dataclass
class TripwireResult:
    id: str
    cycle: str
    version: int
    state: str                  # ARMED | FIRED | EXPIRED | DATA_MISSING | MANUAL
    fired_on: str | None        # ISO date string when expression first fired
    latched: bool               # True = FIRED is sticky (version-locked)
    current_leg: bool | None    # live re-evaluation of the expression (None if data missing)
    claim: str
    direction: str
    coverage: str               # full | partial | none
    expires: str | None
    legs: list[dict] = field(default_factory=list)   # per-leg detail for UI
    manual: dict | None = None  # {ttl_days, last_reviewed, note} for none/partial residuals
    overdue_days: int | None = None   # days past TTL for MANUAL entries
    # nwqs-c scope extension: 'cycle' (default, existing behaviour) or 'ticker'.
    # JSON entries MAY carry scope/tickers; schema-tolerant loading preserves
    # existing 24 entries untouched (they simply get the default 'cycle' scope).
    scope: str = "cycle"        # 'cycle' | 'ticker'
    tickers: list[str] = field(default_factory=list)  # non-empty for scope='ticker'


def _result_dict(r: TripwireResult) -> dict:
    """JSON-safe dict for serialisation."""
    d = asdict(r)
    return d


# ── series resolution ─────────────────────────────────────────────────────────
def _trading_days_stale(s: pd.Series, asof: pd.Timestamp) -> int:
    """Number of trading days between the series' last date and asof.
    Uses pd.bdate_range so a long holiday weekend doesn't false-alarm.
    Negative = last date is AFTER asof (impossible in causal data, returns 0)."""
    last = pd.Timestamp(s.index.max().date())
    asof_d = pd.Timestamp(asof.date())
    if last >= asof_d:
        return 0
    # bdate_range includes both endpoints; subtract 1 for the gap count
    return max(0, len(pd.bdate_range(last, asof_d)) - 1)


def _dilution_series(ticker: str, asof: pd.Timestamp) -> pd.Series | None:
    """Materialise a daily rolling-90d count series from dilution_events.parquet.

    This is the DSL bridge for future 'edgar_dilution:<TICKER>' series refs.
    Returns a DatetimeIndex pd.Series[float] of dilution_events_trailing_90d
    (rolling count of all S-3/S-3ASR/424B* filings in the trailing 90 calendar
    days, evaluated at each date in the parquet), or None when the parquet is
    absent (RENDER_NO_DRIP — degrade gracefully).

    The series uses the full date range from the earliest filing to asof so DSL
    ops like 'gt' / 'lt' can reference a threshold (e.g. 'value: 2' means at
    least 3 events in 90 days → a dilution pressure signal).
    """
    try:
        from lib import config as _config
        path = _config.data_dir() / "edgar" / "dilution_events.parquet"
        if not path.exists():
            return None
        df = pd.read_parquet(path)
        if df.empty or "ticker" not in df.columns or "filing_date" not in df.columns:
            return None
        df["filing_date"] = pd.to_datetime(df["filing_date"], errors="coerce")
        tk_rows = df[df["ticker"] == ticker.upper()].dropna(subset=["filing_date"])
        if tk_rows.empty:
            return None
        # Build a daily indicator series (1 on filing day, 0 otherwise),
        # then compute the trailing 90-day rolling sum to get a count series.
        start = tk_rows["filing_date"].min()
        end = min(asof, pd.Timestamp.now().normalize())
        if start > end:
            return None
        idx = pd.date_range(start=start, end=end, freq="D")
        indicator = pd.Series(0.0, index=idx)
        for d in tk_rows["filing_date"].dropna():
            ts = pd.Timestamp(d).normalize()
            if ts in indicator.index:
                indicator[ts] += 1.0
        rolling_90 = indicator.rolling(90, min_periods=1).sum()
        # Causal: truncate to asof
        rolling_90 = rolling_90[rolling_90.index <= asof]
        return rolling_90 if not rolling_90.empty else None
    except Exception as exc:  # noqa: BLE001
        log.debug("edgar_dilution series materialisation failed for %s: %s", ticker, exc)
        return None


def _load_series_ref(ref: str, asof: pd.Timestamp) -> tuple[pd.Series | None, int]:
    """Resolve a series ref → (series_up_to_asof, stale_trading_days).
    Returns (None, -1) if the tape is completely missing.

    nwqs-c: recognises 'edgar_dilution:<TICKER>' refs and materialises the
    derived daily rolling-90d count series from dilution_events.parquet.
    """
    if ":" not in ref:
        return None, -1
    grp, tick = ref.split(":", 1)

    # nwqs-c: edgar_dilution:<TICKER> — derived series, not in the standard store.
    if grp == "edgar_dilution":
        s = _dilution_series(tick, asof)
        if s is None or s.empty:
            return None, -1
        stale = _trading_days_stale(s, asof)
        return s, stale

    # handle ratio transform embedded in the ref (ratio:yahoo:GC=F)
    if grp == "ratio":
        # ratio:<group>:<ticker>
        parts = tick.split(":", 1)
        if len(parts) != 2:
            return None, -1
        grp, tick = parts[0], parts[1]

    df = store.read(grp, tick)
    if df is None or df.empty:
        return None, -1

    if grp == "yahoo":
        col = "close_price" if "close_price" in df.columns else "close"
    elif "close" in df.columns:
        col = "close"
    else:
        col = df.columns[0]

    s = df[col].astype(float).replace([np.inf, -np.inf], np.nan).dropna()
    s.index = pd.to_datetime(s.index)
    s = s.sort_index()
    # causal: only data up to asof
    s = s[s.index <= asof]
    if s.empty:
        return None, -1

    stale = _trading_days_stale(s, asof)
    return s, stale


# ── DSL transforms ────────────────────────────────────────────────────────────
def _apply_transform(s: pd.Series, transform: str | None, asof: pd.Timestamp,
                     ratio_ref: str | None = None) -> pd.Series | None:
    """Apply a DSL transform to series s.  Returns None on failure."""
    if transform is None:
        return s
    t = transform.strip()

    if t == "yoy_pct":
        # 12-period % change (works for both daily and monthly freq)
        # use 252 bars for daily (approx), 12 for monthly
        freq = "M" if len(s) < 600 else "D"
        lag = 12 if freq == "M" else 252
        if len(s) < lag + 1:
            return None
        shifted = s.shift(lag)
        yoy = (s - shifted) / shifted.abs() * 100
        return yoy.replace([np.inf, -np.inf], np.nan).dropna()

    if t == "weekly_close":
        # resample to weekly Friday closes
        return s.resample("W-FRI").last().dropna()

    if t.startswith("ratio:"):
        # ratio: s / other_series (aligned by date index)
        other_ref = t[6:]
        other_s, other_stale = _load_series_ref(other_ref, asof)
        if other_s is None or other_stale > _STALE_TRADING_DAYS:
            return None
        # align and divide (sort=False: DatetimeIndex concat sort future-deprecated)
        combined = pd.concat([s.rename("a"), other_s.rename("b")], axis=1, sort=False).dropna()
        if combined.empty:
            return None
        ratio = combined["a"] / combined["b"]
        return ratio.replace([np.inf, -np.inf], np.nan).dropna()

    return s   # unknown transform: passthrough


# ── per-leg evaluator ─────────────────────────────────────────────────────────
def _eval_leg(leg: dict, asof: pd.Timestamp) -> tuple[bool | None, dict]:
    """Evaluate one atomic leg.  Returns (result, detail_dict).
    result = True/False/None (None = data missing or stale)."""
    series_ref = leg.get("series")
    if not series_ref:
        return None, {"error": "no series ref in leg"}

    s, stale = _load_series_ref(series_ref, asof)
    if s is None:
        return None, {"series": series_ref, "stale_trading_days": -1,
                      "error": "tape missing"}
    if stale > _STALE_TRADING_DAYS:
        return None, {"series": series_ref, "stale_trading_days": stale,
                      "error": f"tape stale {stale} trading days"}

    # apply transform
    transform = leg.get("transform")
    # pull ratio ref from the leg's transform field if it starts with "ratio:"
    s_t = _apply_transform(s, transform, asof)
    if s_t is None or s_t.empty:
        return None, {"series": series_ref, "transform": transform,
                      "error": "transform failed or empty"}

    # seasonal guard
    months_guard = leg.get("months")
    if months_guard:
        cur_month = asof.month
        if cur_month not in months_guard:
            # outside the seasonal window — leg is vacuously True (armed, not watchful)
            return True, {"series": series_ref, "note": f"outside seasonal months {months_guard}",
                          "seasonal_skip": True}

    op = leg.get("op", "")
    value = leg.get("value")
    if value is None:
        return None, {"series": series_ref, "error": "no value in leg"}

    sustain = max(1, int(leg.get("sustain_bars", 1)))

    # compute the boolean mask for the op
    def _mask(sv: pd.Series, op_name: str, v: float) -> pd.Series:
        if op_name == "gt":
            return sv > v
        elif op_name == "lt":
            return sv < v
        elif op_name == "ge":
            return sv >= v
        elif op_name == "le":
            return sv <= v
        elif op_name == "cross_above":
            return (sv > v) & (sv.shift(1) <= v)
        elif op_name == "cross_below":
            return (sv < v) & (sv.shift(1) >= v)
        return pd.Series(False, index=sv.index)

    mask = _mask(s_t, op, float(value))

    # sustain check: last `sustain` bars must ALL be True
    if sustain > 1:
        if len(mask) < sustain:
            held = False
        else:
            held = bool(mask.iloc[-sustain:].all())
    else:
        held = bool(mask.iloc[-1]) if len(mask) else False

    last_val = float(s_t.iloc[-1]) if len(s_t) else None
    return held, {
        "series": series_ref,
        "transform": transform,
        "op": op,
        "threshold": value,
        "value_now": last_val,
        "sustain_bars": sustain,
        "stale_trading_days": stale,
        "result": held,
    }


# ── DSL combinator evaluator ──────────────────────────────────────────────────
def _eval_expr(expr: Any, asof: pd.Timestamp) -> tuple[bool | None, list[dict]]:
    """Recursively evaluate a DSL expression.
    Returns (result, [leg_details]).
    result = True/False/None (None = data missing somewhere)."""
    if expr is None:
        return None, []

    # atomic leg: has "series" and "op"
    if isinstance(expr, dict) and "series" in expr and "op" in expr:
        r, detail = _eval_leg(expr, asof)
        return r, [detail]

    if isinstance(expr, dict):
        if "all" in expr:
            results, details = [], []
            for sub in expr["all"]:
                r, d = _eval_expr(sub, asof)
                results.append(r)
                details.extend(d)
            # all: True only if every sub is True; None if any is None; False otherwise
            if any(r is None for r in results):
                overall = None
            else:
                overall = all(r is True for r in results)
            return overall, details

        if "any" in expr:
            results, details = [], []
            for sub in expr["any"]:
                r, d = _eval_expr(sub, asof)
                results.append(r)
                details.extend(d)
            # any: True if any sub is True; None if any is None and none True; False otherwise
            if any(r is True for r in results):
                overall = True
            elif any(r is None for r in results):
                overall = None
            else:
                overall = False
            return overall, details

        if "not" in expr:
            r, d = _eval_expr(expr["not"], asof)
            if r is None:
                return None, d
            return (not r), d

    return None, [{"error": "unrecognised DSL node", "expr": str(expr)[:120]}]


# ── latch state persistence ───────────────────────────────────────────────────
def _load_state() -> dict:
    """Load tripwire_state.json.  Returns {} if absent or malformed."""
    p = config.ROOT / _STATE_JSON
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:
        log.warning("tripwire_state.json unreadable: %s", exc)
        return {}


def _save_state(state: dict) -> None:
    """Atomically write tripwire_state.json."""
    p = config.ROOT / _STATE_JSON
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(p)


# ── main evaluate function ────────────────────────────────────────────────────
def evaluate_all(asof: pd.Timestamp | None = None) -> list[TripwireResult]:
    """Evaluate every tripwire in falsifiers.json against collected data.

    Pure read of data/ parquets (causal: data ≤ asof only).  Does NOT persist
    latch state — call persist() to write latches and get newly-fired list."""
    if asof is None:
        asof = pd.Timestamp.now().normalize()

    root = config.ROOT
    f_path = root / _FALSIFIERS_JSON
    if not f_path.exists():
        log.warning("falsifiers.json not found at %s", f_path)
        return []

    entries = json.loads(f_path.read_text(encoding="utf-8"))
    results: list[TripwireResult] = []

    for entry in entries:
        eid = entry["id"]
        cycle = entry["cycle"]
        version = entry.get("version", 1)
        coverage = entry.get("coverage", "none")
        dsl = entry.get("dsl")
        expires = entry.get("expires")
        claim = entry.get("claim", "")
        direction = entry.get("direction", "refutes")
        manual = entry.get("manual")
        # nwqs-c scope extension: schema-tolerant — existing entries carry no
        # scope/tickers keys and receive the defaults ('cycle', []).
        scope = entry.get("scope", "cycle")
        tickers = list(entry.get("tickers") or [])

        # EXPIRED check
        if expires:
            try:
                exp_date = date.fromisoformat(expires)
                if asof.date() > exp_date:
                    results.append(TripwireResult(
                        id=eid, cycle=cycle, version=version,
                        state="EXPIRED", fired_on=None, latched=False,
                        current_leg=None, claim=claim, direction=direction,
                        coverage=coverage, expires=expires, legs=[],
                        manual=manual, scope=scope, tickers=tickers,
                    ))
                    continue
            except ValueError:
                pass

        # MANUAL / NONE coverage
        if coverage == "none" or dsl is None:
            overdue = None
            if manual and manual.get("ttl_days") and manual.get("last_reviewed"):
                try:
                    reviewed = date.fromisoformat(manual["last_reviewed"])
                    age = (asof.date() - reviewed).days
                    overdue = max(0, age - manual["ttl_days"])
                except ValueError:
                    pass
            results.append(TripwireResult(
                id=eid, cycle=cycle, version=version,
                state="MANUAL", fired_on=None, latched=False,
                current_leg=None, claim=claim, direction=direction,
                coverage=coverage, expires=expires, legs=[],
                manual=manual, overdue_days=overdue, scope=scope, tickers=tickers,
            ))
            continue

        # evaluate DSL
        current_leg, leg_details = _eval_expr(dsl, asof)

        # DATA_MISSING: any leg returned None
        has_missing = any(d.get("stale_trading_days", 0) == -1
                          or "error" in d
                          for d in leg_details)
        if current_leg is None and has_missing:
            results.append(TripwireResult(
                id=eid, cycle=cycle, version=version,
                state="DATA_MISSING", fired_on=None, latched=False,
                current_leg=None, claim=claim, direction=direction,
                coverage=coverage, expires=expires, legs=leg_details,
                manual=manual, scope=scope, tickers=tickers,
            ))
            continue

        # ARMED or potential FIRED — will be latched by persist()
        state_val = "FIRED" if current_leg else "ARMED"
        results.append(TripwireResult(
            id=eid, cycle=cycle, version=version,
            state=state_val,
            fired_on=(str(asof.date()) if current_leg else None),
            latched=False,  # set by persist()
            current_leg=current_leg,
            claim=claim, direction=direction,
            coverage=coverage, expires=expires, legs=leg_details,
            manual=manual, scope=scope, tickers=tickers,
        ))

    return results


def persist(results: list[TripwireResult]) -> list[TripwireResult]:
    """Apply latch semantics and write state.

    FIRED is STICKY: once a tripwire fires, it stays FIRED until the version
    bumps (a human re-authors the entry with version N+1).  But `current_leg`
    always reflects the live re-evaluation (ruling A17 — "condition no longer
    met" must be visible even on a latched FIRED).

    Returns: list of NEWLY-fired tripwires (those not previously latched).
    """
    state = _load_state()
    newly_fired: list[TripwireResult] = []

    for r in results:
        key = r.id
        prev = state.get(key, {})
        prev_version = prev.get("version", 0)
        prev_fired_on = prev.get("fired_on")
        prev_latched = prev.get("latched", False)

        # version bump un-latches (human re-authored the entry)
        if prev_latched and prev_version != r.version:
            prev_latched = False
            prev_fired_on = None

        if prev_latched and prev_fired_on:
            # already latched: stay FIRED, keep original fire date, update current_leg
            r.state = "FIRED"
            r.fired_on = prev_fired_on
            r.latched = True
        elif r.state == "FIRED":
            # newly fired this build
            r.latched = True
            newly_fired.append(r)
        # else: ARMED/MANUAL/EXPIRED/DATA_MISSING — no latch changes

        # persist current state
        state[key] = {
            "version": r.version,
            "state": r.state,
            "fired_on": r.fired_on,
            "latched": r.latched,
            "current_leg": r.current_leg,
            "as_of": str(pd.Timestamp.now().date()),
        }

    _save_state(state)
    return newly_fired


# ── alert wiring ──────────────────────────────────────────────────────────────
def cycle_falsifier_fired(hist: "pd.DataFrame", f: "pd.DataFrame",
                          newly_fired: list[TripwireResult]) -> list:
    """Alert rule for new FIRED tripwires.  Returns a list[Alert].

    The `hist` and `f` parameters follow the alerts.py rule signature
    (they are unused here — the tripwire state is the data source, not
    the regime frame) so this function integrates cleanly into the
    evaluate() / multi-rule loop without special-casing."""
    try:
        from engine.alerts import Alert
    except ImportError:
        log.warning("alerts.Alert not importable — skipping alert dispatch")
        return []

    alerts = []
    for r in newly_fired:
        # direction → severity mapping: refutes = warn, confirms = info
        severity = "warn" if r.direction == "refutes" else "info"
        # Display register (operator 2026-07-27, #3821): the schema value stays
        # "refutes"/"confirms", but user-shown text never says falsified/refuted/证伪.
        dirn = "cuts against the read" if r.direction == "refutes" else "supports the read"
        dirn_zh = "与原判断相反" if r.direction == "refutes" else "支持原判断"
        msg_en = (
            f"Cycle read-change condition HIT — {r.cycle}: {r.claim}. "
            f"Direction: {dirn}. "
            f"Coverage: {r.coverage}."
        )
        msg_zh = (
            f"周期改判条件触发 — {r.cycle}：{r.claim}。"
            f"方向：{dirn_zh}。"
        )
        alerts.append(Alert(
            rule=f"cycle_falsifier_fired:{r.id}",
            severity=severity,
            message=msg_en,
            message_zh=msg_zh,
        ))
    return alerts


def register_alert_rule() -> None:
    """Register cycle_falsifier_fired as a multi-rule in alerts.py.

    Called once from build_cycle.py after evaluate_all + persist().
    We use the 'multi' pattern (returns list[Alert]) rather than
    the single-Alert pattern, so it slips into the existing multi loop
    at alerts.py:480 without touching the rules list ordering.

    Since alerts.evaluate() has no side-channel for tripwire results,
    we wire the alert dispatch DIRECTLY from build_cycle.py (which has
    the newly_fired list) rather than via the evaluate() hook.
    This is consistent with how build-time signals bypass the live-data
    frame (f: pd.DataFrame) pattern — the build IS the trigger.
    """
    pass   # no-op: dispatch happens directly in build_cycle._emit_tripwire_alerts()


def dispatch_alerts(newly_fired: list[TripwireResult],
                    asof: pd.Timestamp | None = None) -> None:
    """Emit alerts for newly-fired tripwires through the existing pipeline.

    Follows the experiments_registry.py:182 notify pattern:
    log_and_dedup → dispatch if non-empty.  Non-fatal: a notify failure
    must not abort the build."""
    if not newly_fired:
        return
    if asof is None:
        asof = pd.Timestamp.now().normalize()

    try:
        from engine.alerts import Alert, log_and_dedup
    except ImportError:
        log.warning("alerts module not importable — skipping alert dispatch")
        return

    alerts = []
    for r in newly_fired:
        severity = "warn" if r.direction == "refutes" else "info"
        dirn = "cuts against the read" if r.direction == "refutes" else "supports the read"
        dirn_zh = "与原判断相反" if r.direction == "refutes" else "支持原判断"
        msg_en = (
            f"Cycle read-change condition HIT — {r.cycle}: "
            f"'{r.claim}' (coverage: {r.coverage}, direction: {dirn})."
        )
        msg_zh = (
            f"周期改判条件触发 — {r.cycle}：'{r.claim}'（{dirn_zh}）。"
        )
        alerts.append(Alert(
            rule=f"cycle_falsifier_fired:{r.id}",
            severity=severity,
            message=msg_en,
            message_zh=msg_zh,
        ))

    try:
        fresh = log_and_dedup(alerts, asof)
        if fresh:
            log.warning("tripwire: %d newly-fired alert(s) logged", len(fresh))
            # attempt telegram/discord notify (non-fatal)
            _notify_if_available(fresh)
    except Exception as exc:
        log.error("tripwire alert dispatch failed (non-fatal): %s", exc)


def _notify_if_available(alerts: list) -> None:
    """Best-effort: forward alerts through scripts/notify.py patterns."""
    try:
        import os, requests
        tg_token = os.environ.get("TELEGRAM_BOT_TOKEN")
        tg_chat = os.environ.get("TELEGRAM_CHAT_ID")
        dc_url = os.environ.get("DISCORD_WEBHOOK_URL")

        if not (tg_token and tg_chat) and not dc_url:
            return

        lines = ["🚨 <b>Cycle falsifier alerts</b>"]
        for a in alerts:
            lines.append(f"• <b>{a.rule}</b>: {a.message}")
        msg = "\n".join(lines)

        if tg_token and tg_chat:
            try:
                requests.post(
                    f"https://api.telegram.org/bot{tg_token}/sendMessage",
                    json={"chat_id": tg_chat, "text": msg, "parse_mode": "HTML"},
                    timeout=10,
                )
            except Exception as exc:
                log.debug("telegram notify failed: %s", exc)

        if dc_url:
            # Discord uses plain text
            plain = msg.replace("<b>", "**").replace("</b>", "**")
            try:
                requests.post(dc_url, json={"content": plain}, timeout=10)
            except Exception as exc:
                log.debug("discord notify failed: %s", exc)

    except Exception as exc:
        log.debug("notify not available: %s", exc)


# ── overdue-digest helper ──────────────────────────────────────────────────────
def overdue_manual_digest(results: list[TripwireResult]) -> list[dict]:
    """Return list of overdue MANUAL entries (TTL elapsed) for weekly digest alerts."""
    return [
        {"id": r.id, "cycle": r.cycle, "claim": r.claim,
         "overdue_days": r.overdue_days, "manual": r.manual}
        for r in results
        if r.state == "MANUAL" and r.overdue_days and r.overdue_days > 0
    ]


# ── build integration helper ──────────────────────────────────────────────────
def evaluate_and_persist(asof: pd.Timestamp | None = None,
                         dispatch: bool = True) -> tuple[list[TripwireResult], list[TripwireResult]]:
    """One-call convenience: evaluate_all → persist → optionally dispatch alerts.

    Returns (all_results, newly_fired).  Called from scripts/build_cycle.py."""
    results = evaluate_all(asof=asof)
    newly = persist(results)
    if dispatch and newly:
        dispatch_alerts(newly, asof=asof)
    overdue = overdue_manual_digest(results)
    if overdue:
        log.warning("falsifier review overdue: %d manual tripwire(s) need review: %s",
                    len(overdue), [o["id"] for o in overdue])
    return results, newly


# ── results → JSON-safe summary ───────────────────────────────────────────────
def results_summary(results: list[TripwireResult]) -> dict:
    """Group results by state for the cycle_engine.js payload and UI strip.

    nwqs-c: scope=='ticker' entries are EXCLUDED from cycle grouping so that the
    build_cycle.py UI strip is unaffected (it indexes by cycle key only).
    """
    by_cycle: dict[str, list[dict]] = {}
    for r in results:
        # scope='ticker' entries are not cycle-level; skip them here.
        if r.scope == "ticker":
            continue
        rec = {
            "id": r.id,
            "version": r.version,
            "state": r.state,
            "fired_on": r.fired_on,
            "latched": r.latched,
            "current_leg": r.current_leg,
            "claim": r.claim,
            "direction": r.direction,
            "coverage": r.coverage,
            "expires": r.expires,
            "overdue_days": r.overdue_days,
            "manual": r.manual,
            # legs detail is large; include only the essential sub-fields
            "legs": [
                {k: v for k, v in d.items()
                 if k in ("series", "op", "threshold", "value_now",
                           "sustain_bars", "stale_trading_days", "result",
                           "error", "note", "seasonal_skip")}
                for d in r.legs
            ],
        }
        by_cycle.setdefault(r.cycle, []).append(rec)
    return by_cycle


def results_by_ticker(results: list[TripwireResult]) -> dict[str, list[dict]]:
    """Group ticker-scoped results by ticker symbol.

    Companion to results_summary(): handles only scope=='ticker' entries.
    Returns dict[ticker → list[result_dicts]] for per-stock consumers.
    An entry with scope='ticker' and tickers=['AAPL', 'MSFT'] appears under
    BOTH keys.  Never raises.
    """
    by_ticker: dict[str, list[dict]] = {}
    for r in results:
        if r.scope != "ticker":
            continue
        rec = {
            "id": r.id,
            "version": r.version,
            "state": r.state,
            "fired_on": r.fired_on,
            "latched": r.latched,
            "current_leg": r.current_leg,
            "claim": r.claim,
            "direction": r.direction,
            "coverage": r.coverage,
            "expires": r.expires,
            "cycle": r.cycle,
            "legs": [
                {k: v for k, v in d.items()
                 if k in ("series", "op", "threshold", "value_now",
                           "sustain_bars", "stale_trading_days", "result",
                           "error", "note", "seasonal_skip")}
                for d in r.legs
            ],
        }
        for ticker in r.tickers:
            by_ticker.setdefault(ticker, []).append(rec)
    return by_ticker


# ── standalone CLI ────────────────────────────────────────────────────────────
def main() -> int:
    import sys
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    asof_str = sys.argv[1] if len(sys.argv) > 1 else None
    asof = pd.Timestamp(asof_str) if asof_str else None

    results, newly = evaluate_and_persist(asof=asof, dispatch=False)

    counts = {}
    for r in results:
        counts[r.state] = counts.get(r.state, 0) + 1

    print("\nFalsifier tripwire evaluation")
    print(f"  as_of : {asof or pd.Timestamp.now().date()}")
    print(f"  total : {len(results)}")
    for st, n in sorted(counts.items()):
        print(f"  {st:<15s}: {n}")

    if newly:
        print(f"\n  NEWLY FIRED ({len(newly)}):")
        for r in newly:
            print(f"    {r.id}: {r.claim}")

    fired = [r for r in results if r.state == "FIRED"]
    if fired:
        print(f"\n  CURRENTLY FIRED ({len(fired)}):")
        for r in fired:
            mark = " (current_leg=True)" if r.current_leg else " (condition no longer met)"
            print(f"    {r.id}{mark}")

    overdue = overdue_manual_digest(results)
    if overdue:
        print(f"\n  OVERDUE MANUAL REVIEW ({len(overdue)}):")
        for o in overdue:
            print(f"    {o['id']}: {o['overdue_days']}d overdue")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
