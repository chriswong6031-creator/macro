"""Point-in-time US Context Vector store (PROPHET US roadmap §2 keystone).

This module records the *entire* analyzed US universe once per night — including
names that never passed the raw signal gate — with one flattened context block
per name.  It is a feature-and-admission log only: it joins no forward returns,
computes no score, and changes no production rank or lane.  Its whole purpose is
that every future study can join evidence *point-in-time* instead of
reconstructing the night from mutable files (the 2026-08 audit's hand-joins).

Zero authority at birth.  Nothing reads this store for scoring; the roadmap's
bounded-authority ladder (§3) is the only path by which any column here may ever
influence a decision, and each rung needs its own preregistration.

Storage idiom is copied from the CN sibling ``engine/china_prophet_shadow.py``
(store ``data/china_prophet_rank/candidates.parquet``, accruing since
2026-07-30) so the two markets stay one schema family (roadmap §7):

* the write is gated to the US nightly lane — ``COLLECT_LANE=nightly`` via
  :func:`engine.ledger_lane.nightly_advance_enabled`, the canonical forward-ledger
  advance gate.  Intraday and render lanes discard ``data/`` writes, so the gate
  is the FIRST statement: a non-nightly lane pays none of the assembly cost;
* keep-first on ``(stamp_date, ticker, board_definition)`` so a rerun can never
  rewrite the decision users could have seen (PIT discipline);
* parquet appends use a schema union, so adding a column later neither discards
  old columns nor rewrites old rows (a new column is simply null for prior
  nights — it self-heals forward, never backwards);
* NO retroactive backfill: only same-night values are ever stamped.

Fail-soft by contract: research telemetry must never break the nightly build, so
every failure path logs and returns 0.

Column provenance
-----------------
Every column is READ from a producer that already computed it tonight.  This
module originates no signal, no score and no leg (glass-box law, A7).  Coverage
is deliberately uneven and disclosed rather than imputed:

* ``eligible``/``tier_cascade``/``ticks``/``near_miss_reason`` etc. — the
  ``signal_gate.gate()`` verdict, present for the FULL universe (the spine);
* ``prophet_*`` legs + ``alpha_percentile`` — ``us_board_rank.score_rows()``,
  which the US builder runs on the BUY LANE ONLY, so these are null for every
  name off the board.  They are read off, never recomputed;
* ``ext_z`` — full universe (``extension.extension_signals`` over the whole
  library panel); ``in_blackout`` — only names that reached the earnings gate.

A null here means "not measured for this name tonight", never "false"
(#4485 null-not-false).
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
import json
import logging
import math
from typing import Any

import pandas as pd

from engine import ledger_lane
from lib import config

log = logging.getLogger(__name__)

STORE_DIR = "us_prophet_rank"
STORE_FILE = "candidates.parquet"

#: Keep-first key.  ``board_definition`` participates so a definition change
#: starts a fresh series for the same night instead of silently shadowing it.
DEDUPE_KEY = ("stamp_date", "ticker", "board_definition")

#: The itemized priority-score legs as ``engine.us_board_rank.score_rows``
#: already computes them.  Read off, never recomputed here.
SCORE_COMPONENTS = ("signal", "entry", "edge", "runway", "quality")

#: GICS pseudo-baskets mirror the SPDR sector ETFs 1:1 and are excluded from
#: theme membership exactly as ``us_board_rank.THEME_ID_EXCLUDE_PREFIX`` does.
THEME_ID_EXCLUDE_PREFIX = "us_sector_"

#: Trailing window for the S-A turnover percentile stand-in.
TURNOVER_WINDOW_20D = 20


# --------------------------------------------------------------------------- #
# coercion helpers (idiom copied from engine/china_prophet_shadow.py)
# --------------------------------------------------------------------------- #

def _store_path(root: Any = None):
    base = config.data_dir() if root is None else (root / "data")
    return base / STORE_DIR / STORE_FILE


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _date(value: Any) -> str | None:
    text = _text(value)
    return text[:10] if text else None


def _bool(value: Any) -> bool | None:
    """Strict tri-state: only a real bool is a bool.

    ``None`` means "not measured tonight", never "false" (#4485).
    """
    return value if isinstance(value, bool) else None


def _ids(value: Any) -> str | None:
    """Join an id collection into a stable, sorted, pipe-delimited string."""
    if isinstance(value, str):
        return value or None
    if isinstance(value, Iterable) and not isinstance(value, (bytes, Mapping)):
        parts = sorted({str(item).strip() for item in value if str(item).strip()})
        return "|".join(parts) or None
    return None


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


# --------------------------------------------------------------------------- #
# theme block — curated baskets, relay, foresight stage
# --------------------------------------------------------------------------- #

def basket_membership(asof: str, root: Any = None) -> dict[str, list[str]]:
    """PIT curated-basket membership: ``basket_id -> [ticker, ...]``.

    Honors ``added``/``removed`` against ``asof`` and drops the ``us_sector_``
    GICS pseudo-baskets.  Reads ``data/baskets/membership.json``.
    """
    base = config.data_dir() if root is None else (root / "data")
    path = base / "baskets" / "membership.json"
    if not path.exists():
        return {}
    try:
        doc = json.loads(path.read_text())
    except Exception as exc:  # noqa: BLE001 — absent/malformed theme data ships no chips
        log.warning("us_context_vector: membership.json unreadable (%s)", exc)
        return {}
    day = _date(asof) or ""
    out: dict[str, list[str]] = {}
    for basket_id, basket in (_mapping(doc.get("baskets"))).items():
        if str(basket_id).startswith(THEME_ID_EXCLUDE_PREFIX):
            continue
        members: list[str] = []
        for member in (_mapping(basket).get("members") or ()):
            member = _mapping(member)
            ticker = _text(member.get("ticker"))
            if not ticker:
                continue
            added, removed = _text(member.get("added")), _text(member.get("removed"))
            if added and day and day < added:
                continue
            if removed and day and day >= removed:
                continue
            members.append(ticker)
        if members:
            out[str(basket_id)] = members
    return out


def basket_to_foresight(root: Any = None) -> dict[str, str]:
    """``basket_id -> foresight theme id`` from ``config/theme_crosswalk.yml``.

    The crosswalk is the curated join table between the 47 curated baskets and
    the 18 Foresight Desk themes.  NO fuzzy matching: a basket the crosswalk
    does not list simply has no foresight stage (null), per roadmap §2.
    """
    base = config.ROOT if root is None else root
    path = base / "config" / "theme_crosswalk.yml"
    if not path.exists():
        return {}
    try:
        import yaml
        doc = yaml.safe_load(path.read_text()) or {}
    except Exception as exc:  # noqa: BLE001
        log.warning("us_context_vector: theme_crosswalk unreadable (%s)", exc)
        return {}
    out: dict[str, str] = {}
    for theme in (doc.get("themes") or ()):
        theme = _mapping(theme)
        foresight_id = _text(theme.get("foresight_id")) or _text(theme.get("id"))
        if not foresight_id:
            continue
        for basket_id in (theme.get("basket_ids") or ()):
            basket = _text(basket_id)
            if basket:
                # normalized here, so build_records stays a plain dict lookup
                out[basket] = _norm_theme(foresight_id)
    return out


def _norm_theme(value: Any) -> str:
    """Normalize a theme id to the Foresight Desk's key form.

    Delegates to ``prophet_doors._norm_theme`` — the function that BUILT the
    stage map's keys — so the two can never drift apart.  Falls back to the
    same lowercase-alphanumeric reduction if that private helper ever moves.
    """
    try:
        from engine import prophet_doors
        return prophet_doors._norm_theme(value)
    except Exception:  # noqa: BLE001
        return "".join(ch for ch in str(value or "").lower() if ch.isalnum())


def foresight_stage_map(root: Any = None) -> dict[str, str]:
    """``normalized foresight theme id -> STAGE`` from the Thematic Foresight Desk.

    Isolated in its own try/except: a broken desk artifact must null exactly one
    column, never cost the whole night's store.
    """
    try:
        from engine import prophet_doors
        stages, _disclosure = prophet_doors.load_foresight_stages(root)
        return dict(stages or {})
    except Exception as exc:  # noqa: BLE001
        log.warning("us_context_vector: foresight stages unavailable (%s)", exc)
        return {}


def theme_state(root: Any = None) -> dict[str, dict[str, Any]]:
    """``basket_id -> nightly basket-engine state`` from ``data/baskets/latest.json``.

    ``rank`` is the roadmap's ``heat_rank`` — the basket engine's own nightly
    rotation rank (1 = strongest of 47).  Read, never recomputed.
    """
    base = config.data_dir() if root is None else (root / "data")
    path = base / "baskets" / "latest.json"
    if not path.exists():
        return {}
    try:
        doc = json.loads(path.read_text())
    except Exception as exc:  # noqa: BLE001
        log.warning("us_context_vector: baskets/latest.json unreadable (%s)", exc)
        return {}
    out: dict[str, dict[str, Any]] = {}
    for theme in (doc.get("themes") or ()):
        theme = _mapping(theme)
        basket_id = _text(theme.get("id"))
        if basket_id:
            out[basket_id] = dict(theme)
    return out


def theme_pulse_by_ticker(
    membership: Mapping[str, list[str]],
    states: Mapping[str, Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Per ticker, the state of its BEST-RANKED curated basket (1 = strongest).

    A name in several baskets is described by its strongest one, so
    ``theme_heat_rank`` answers "how hot is the hottest theme this name is in".
    """
    best: dict[str, dict[str, Any]] = {}
    for basket_id, members in membership.items():
        state = _mapping(states.get(basket_id))
        rank = _finite(state.get("rank"))
        if rank is None:
            continue
        for ticker in members:
            prior = best.get(ticker)
            if prior is None or rank < prior["rank"]:
                best[ticker] = {
                    "rank": rank,
                    "id": basket_id,
                    "name": _text(state.get("name")),
                    "label": _text(state.get("label")),
                    "reco": _text(state.get("reco")),
                    "score": _finite(state.get("score")),
                    "bull_days": _finite(state.get("bull_days")),
                    "clean_entry": _bool(state.get("clean_entry")),
                }
    return best


def relay_features(
    closes: pd.DataFrame | None,
    membership: Mapping[str, list[str]],
    *,
    high_lookback: int,
    recent_sessions: int,
    position_window: int,
    min_members: int,
) -> dict[str, dict[str, Any]]:
    """Per-ticker relay position and 3-session relay count, over curated baskets.

    Construction follows the LIVE production definition in
    ``engine.prophet_doors._RecordedFeatures._relay`` (not the research
    stand-in, which broadcasts one basket-day value to all co-breakouts):

    * a "fresh high" is ``close > max(prior ``high_lookback`` closes)`` —
      ``rolling(...).max().shift(1)``, so the bar is never inside its own
      comparison window;
    * ``relay_count_3d`` counts OTHER members of the same basket that printed a
      fresh high in the trailing ``recent_sessions`` sessions;
    * ``relay_position`` is the fraction of the basket's covered members that
      broke out EARLIER in the trailing ``position_window`` sessions.

    A ticker in several baskets takes its MAXIMUM relay_count_3d basket, so the
    value answers "how much of my theme has already gone" at its most advanced.
    """
    out: dict[str, dict[str, Any]] = {}
    if closes is None or closes.empty or not membership:
        return out
    need = high_lookback + position_window + 1
    frame = closes.sort_index()
    tail = frame.iloc[-need:] if len(frame) >= need else frame
    if len(tail) < high_lookback + 2:
        return out
    prior_max = tail.rolling(high_lookback).max().shift(1)
    breakouts = (tail > prior_max) & tail.notna() & prior_max.notna()
    window = breakouts.iloc[-position_window:]

    for basket_id, members in membership.items():
        covered = [t for t in members if t in window.columns]
        # Require a fully-observed tail: a column with holes cannot be compared
        # against one without them (production uses the same notna() rule).
        covered = [t for t in covered if bool(tail[t].notna().all())]
        if len(covered) < min_members:
            continue
        sub = window[covered]
        recent_any = sub.tail(recent_sessions).any(axis=0)
        earlier_any = sub.iloc[:-1].any(axis=0)
        for ticker in covered:
            others = [t for t in covered if t != ticker]
            count_3d = int(recent_any[others].sum()) if others else 0
            earlier = int(earlier_any[others].sum()) if others else 0
            position = round(earlier / len(covered), 4)
            prior = out.get(ticker)
            if prior is None or count_3d > prior["relay_count_3d"]:
                out[ticker] = {
                    "relay_count_3d": count_3d,
                    "relay_position": position,
                    "relay_members_covered": len(covered),
                    "relay_basket_id": basket_id,
                }
    return out


# --------------------------------------------------------------------------- #
# flow block — S-A turnover percentile stand-in
# --------------------------------------------------------------------------- #

def turnover_percentiles(
    volumes: pd.DataFrame | None,
    asof: str,
    *,
    window: int = TURNOVER_WINDOW_20D,
) -> dict[str, dict[str, Any]]:
    """Own-history turnover percentile, ported from the S-A stand-in.

    Port of ``research/prophet_us_audit/superintelligence_standins.py`` (S-A):
    for each ticker, rank the ``asof`` share volume inside that ticker's own
    trailing ``window`` non-null observations via ``Series.rank(pct=True)``.
    TIME-SERIES orientation (own history), never cross-sectional.

    NOTE the deliberate divergence from ``prophet_doors._turnover``, which uses
    ``(w <= last).mean()`` over an adaptive ``min(60, available)`` window.  The
    two formulas differ on ties; they are separate fields with separate names.

    ``turnover_pctile_60d`` is NOT computed here — the volume caches carry only
    ~51 non-null sessions (backfilled 2026-05-19), so the 60d spec is
    DATA-BLOCKED until the cache deepens (~mid-Aug 2026).  It is stamped null
    and self-heals forward through the schema-union append.
    """
    out: dict[str, dict[str, Any]] = {}
    if volumes is None or volumes.empty:
        return out
    try:
        cutoff = pd.Timestamp(_date(asof))
    except Exception:  # noqa: BLE001
        return out
    frame = volumes.sort_index()
    for ticker in frame.columns:
        series = frame[ticker].dropna()
        series = series.loc[series.index <= cutoff]
        if len(series) < window + 1:
            continue
        win = series.iloc[-window:]
        out[str(ticker)] = {
            "turnover_pctile_20d": round(float(win.rank(pct=True).iloc[-1]), 4),
            "turnover_window_20d": int(len(win)),
        }
    return out


# --------------------------------------------------------------------------- #
# event block — 8-K recency
# --------------------------------------------------------------------------- #

def event_features(
    tickers: Iterable[str],
    closes: pd.DataFrame | None,
    today: Any,
) -> dict[str, dict[str, Any]]:
    """Per-ticker earnings-proximity and post-earnings-reaction fields.

    Calls the canonical pair ``earnings_blackout.assess`` +
    ``earnings_catalyst.board_row_fields`` — the same functions the builder runs
    for board rows — over the FULL universe, so an ineligible name carries the
    same event context as a featured one.  Measured 12.9 s / 1,540 names.

    Null-not-false (#4485): ``reports_within_7`` stays ``None`` when
    ``days_to_report`` is unknown, because ``False`` there would assert
    "does not report within 7 days" about a row nothing can vouch for.
    """
    out: dict[str, dict[str, Any]] = {}
    try:
        from engine import earnings_blackout, earnings_catalyst
    except Exception as exc:  # noqa: BLE001
        log.warning("us_context_vector: earnings modules unavailable (%s)", exc)
        return out
    for ticker in tickers:
        try:
            assessment = earnings_blackout.assess(ticker)
            if not assessment:
                continue
            series = None
            if closes is not None and ticker in closes.columns:
                series = closes[ticker].dropna()
            payload = earnings_catalyst.board_row_fields(
                assessment, today, closes=series)
            soon = _mapping(payload.get("earnings_soon"))
            move = _mapping(payload.get("post_earnings_move"))
            out[str(ticker)] = {
                "days_to_report": soon.get("days_to_report"),
                "reports_within_7": soon.get("reports_within_7"),
                "stale": soon.get("stale"),
                "post_earnings_move_pct": move.get("day0_move_pct"),
                "post_earnings_sessions_since": move.get("sessions_since"),
                "in_blackout": assessment.get("in_blackout"),
            }
        except Exception:  # noqa: BLE001 — one bad ticker must not empty the block
            continue
    return out


def eightk_recency(asof: str, root: Any = None) -> dict[str, int]:
    """``ticker -> calendar days since its most recent 8-K filing`` (>= 0).

    Reduction over ``data/edgar/material_8k_events.parquet`` (the canonical
    per-filing store).  PIT: filings dated after ``asof`` are excluded.
    """
    base = config.data_dir() if root is None else (root / "data")
    path = base / "edgar" / "material_8k_events.parquet"
    if not path.exists():
        return {}
    try:
        frame = pd.read_parquet(path, columns=["ticker", "filing_date"])
    except Exception as exc:  # noqa: BLE001
        log.warning("us_context_vector: material_8k_events unreadable (%s)", exc)
        return {}
    try:
        cutoff = pd.Timestamp(_date(asof))
        filed = pd.to_datetime(frame["filing_date"], errors="coerce")
        frame = frame.assign(_filed=filed)
        frame = frame[frame["_filed"].notna() & (frame["_filed"] <= cutoff)]
        if frame.empty:
            return {}
        latest = frame.groupby("ticker")["_filed"].max()
        days = (cutoff - latest).dt.days
        return {str(t): int(v) for t, v in days.items() if pd.notna(v) and v >= 0}
    except Exception as exc:  # noqa: BLE001
        log.warning("us_context_vector: 8-K recency skipped (%s)", exc)
        return {}


# --------------------------------------------------------------------------- #
# regime block — one value for every row of the night
# --------------------------------------------------------------------------- #

def regime_block(gate_go: Any = None, root: Any = None) -> dict[str, Any]:
    """Market-wide regime context; every name of the night carries these values.

    ``market_quad`` is sourced from ``data/regime/latest.json['quad']`` — no
    field literally named ``market_quad`` exists in this repo (roadmap §2 named
    the concept, the census named the field).
    """
    base = config.data_dir() if root is None else (root / "data")
    block: dict[str, Any] = {
        "regime_dispersion_state": None,
        "regime_gate_go": _bool(gate_go),
        "regime_market_quad": None,
        "regime_quad_name": None,
        "regime_vol_regime": None,
    }
    try:
        macro = base / "macro_snapshots" / "latest.json"
        if macro.exists():
            labels = _mapping(_mapping(json.loads(macro.read_text())).get("labels"))
            dispersion = _mapping(labels.get("dispersion"))
            block["regime_dispersion_state"] = _text(dispersion.get("dispersion_state"))
    except Exception as exc:  # noqa: BLE001
        log.debug("us_context_vector: dispersion_state skipped (%s)", exc)
    try:
        regime = base / "regime" / "latest.json"
        if regime.exists():
            doc = _mapping(json.loads(regime.read_text()))
            block["regime_market_quad"] = _text(doc.get("quad"))
            block["regime_quad_name"] = _text(doc.get("quad_name"))
            block["regime_vol_regime"] = _text(_mapping(doc.get("vol_regime")).get("regime"))
    except Exception as exc:  # noqa: BLE001
        log.debug("us_context_vector: regime block skipped (%s)", exc)
    return block


# --------------------------------------------------------------------------- #
# record assembly (pure — every input injected, so it is hermetically testable)
# --------------------------------------------------------------------------- #

def build_records(
    verdicts: Mapping[str, Mapping[str, Any]],
    *,
    stamp_date: str,
    board_definition: str,
    is_buyable,
    universe_meta: Mapping[str, Mapping[str, Any]] | None = None,
    board_rows: Mapping[str, Mapping[str, Any]] | None = None,
    lane_by_ticker: Mapping[str, str] | None = None,
    profile_rows: Mapping[str, Mapping[str, Any]] | None = None,
    ext_map: Mapping[str, Mapping[str, Any]] | None = None,
    blackout_map: Mapping[str, Mapping[str, Any]] | None = None,
    event_rows: Mapping[str, Mapping[str, Any]] | None = None,
    theme_ids: Mapping[str, list[str]] | None = None,
    theme_pulse: Mapping[str, Mapping[str, Any]] | None = None,
    relay: Mapping[str, Mapping[str, Any]] | None = None,
    foresight_by_basket: Mapping[str, str] | None = None,
    foresight_stages: Mapping[str, str] | None = None,
    turnover: Mapping[str, Mapping[str, Any]] | None = None,
    eightk_days: Mapping[str, int] | None = None,
    regime: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """One flattened context row per universe name.  Pure; no I/O.

    ``verdicts`` is the spine — its keys ARE the universe, so a name with no
    board row, no theme and no event still gets a row (that is the point of a
    full-universe store).
    """
    universe_meta = universe_meta or {}
    board_rows = board_rows or {}
    lane_by_ticker = lane_by_ticker or {}
    profile_rows = profile_rows or {}
    ext_map = ext_map or {}
    blackout_map = blackout_map or {}
    event_rows = event_rows or {}
    theme_ids = theme_ids or {}
    theme_pulse = theme_pulse or {}
    relay = relay or {}
    foresight_by_basket = foresight_by_basket or {}
    foresight_stages = foresight_stages or {}
    turnover = turnover or {}
    eightk_days = eightk_days or {}
    regime = regime or {}

    records: list[dict[str, Any]] = []
    for ticker in sorted(verdicts):
        verdict = _mapping(verdicts.get(ticker))
        meta = _mapping(universe_meta.get(ticker))
        board = _mapping(board_rows.get(ticker))
        profile = _mapping(profile_rows.get(ticker))
        prophet = _mapping(board.get("prophet"))
        components = _mapping(prophet.get("components"))
        points = _mapping(prophet.get("points"))
        pulse = _mapping(theme_pulse.get(ticker))
        relay_row = _mapping(relay.get(ticker))
        event = _mapping(event_rows.get(ticker))
        flow = _mapping(turnover.get(ticker))

        memberships = [b for b in (theme_ids.get(ticker) or ())
                       if not str(b).startswith(THEME_ID_EXCLUDE_PREFIX)]
        # foresight stage joins basket -> foresight theme via the curated
        # crosswalk ONLY; an unmapped basket contributes no stage (no fuzzy join).
        stage = None
        for basket_id in sorted(memberships):
            foresight_id = foresight_by_basket.get(basket_id)
            if foresight_id and foresight_id in foresight_stages:
                stage = foresight_stages[foresight_id]
                break

        record: dict[str, Any] = {
            # ── identity / board ───────────────────────────────────────────
            "stamp_date": stamp_date,
            "ticker": ticker,
            "name": _text(meta.get("name")),
            "sector": _text(meta.get("sector")),
            "board_definition": board_definition,
            "lane": _text(lane_by_ticker.get(ticker)) or "not_on_board",
            "eligible": bool(verdict.get("eligible")),
            "buyable": bool(is_buyable(dict(verdict))) if verdict else False,
            "tier_cascade": _text(verdict.get("tier_cascade")),
            "tier_sub": _text(verdict.get("tier_sub")),
            "ticks": _finite(verdict.get("ticks")),
            "bars_to_cross": _finite(verdict.get("bars_to_cross")),
            "fresh_bars": _finite(verdict.get("fresh_bars")),
            "gate_weight": _finite(verdict.get("weight")),
            "gate_state": _text(verdict.get("state")),
            "gate_reason": _text(verdict.get("reason")),
            "gate_provisional": bool(verdict.get("provisional")),
            "htf_s1": _bool(verdict.get("htf_s1")),
            "htf_s2": _bool(verdict.get("htf_s2")),
            # key is ABSENT (not None) on the verdict when no near-miss applies
            "near_miss_reason": _text(verdict.get("near_miss_reason")),
            "signal_asof": _date(verdict.get("asof")),
            "stage": _text(board.get("stage") or profile.get("stage")),
            "alpha": _finite(profile.get("alpha")),
            "alpha_percentile": _finite(prophet.get("alpha_percentile")),
            "prophet_score": _finite(prophet.get("score")),
            "score_rank": _finite(board.get("score_rank")),
            "display_rank": _finite(board.get("display_rank")),
            "featured": _bool(board.get("featured")),
            # ── theme ─────────────────────────────────────────────────────
            "theme_membership_count": len(memberships),
            "theme_membership_ids": _ids(memberships),
            "theme_primary_id": _text(pulse.get("id")),
            "theme_primary_name": _text(pulse.get("name")),
            # the basket engine's own nightly rotation rank (1 = strongest of 47)
            "theme_heat_rank": _finite(pulse.get("rank")),
            "theme_label": _text(pulse.get("label")),
            "theme_reco": _text(pulse.get("reco")),
            "theme_score": _finite(pulse.get("score")),
            "theme_bull_days": _finite(pulse.get("bull_days")),
            "theme_clean_entry": _bool(pulse.get("clean_entry")),
            "relay_count_3d": _finite(relay_row.get("relay_count_3d")),
            "relay_position": _finite(relay_row.get("relay_position")),
            "relay_members_covered": _finite(relay_row.get("relay_members_covered")),
            "relay_basket_id": _text(relay_row.get("relay_basket_id")),
            "foresight_stage": _text(stage),
            # ── event ─────────────────────────────────────────────────────
            "days_to_report": _finite(event.get("days_to_report")),
            "reports_within_7": _bool(event.get("reports_within_7")),
            "post_earnings_move_pct": _finite(event.get("post_earnings_move_pct")),
            "post_earnings_sessions_since": _finite(
                event.get("post_earnings_sessions_since")),
            "earnings_stale": _bool(event.get("stale")),
            # the full-universe event pass wins; the builder's own board-row
            # blackout map is the fallback for names it already assessed.
            "in_blackout": _bool(
                event.get("in_blackout") if event.get("in_blackout") is not None
                else _mapping(blackout_map.get(ticker)).get("in_blackout")),
            "eightk_recent_days": _finite(eightk_days.get(ticker)),
            # ── flow ──────────────────────────────────────────────────────
            "turnover_pctile_20d": _finite(flow.get("turnover_pctile_20d")),
            "turnover_window_20d": _finite(flow.get("turnover_window_20d")),
            # 60d spec is DATA-BLOCKED (caches carry ~51 sessions); self-heals.
            "turnover_pctile_60d": None,
            # ── risk ──────────────────────────────────────────────────────
            "ext_z": _finite(_mapping(ext_map.get(ticker)).get("ext_z")),
            "antichase_shadow_blocked": _bool(profile.get("antichase_shadow_blocked")),
        }
        record.update(regime)
        for component in SCORE_COMPONENTS:
            record[f"prophet_{component}"] = _finite(components.get(component))
            record[f"prophet_{component}_points"] = _finite(points.get(component))
        records.append(record)
    return records


# --------------------------------------------------------------------------- #
# quality block — Neural Web Context Snapshot reuse (canonical source)
# --------------------------------------------------------------------------- #

#: The 11 PIT dimensions ``context_api.context_snapshot`` computes.  Recorded
#: per row as ``context_dims`` so a night that ever assembles fewer of them is
#: visible IN THE STORE, not merely in a note (roadmap §2: never silently thin).
CONTEXT_DIMENSIONS = (
    "personality", "archetype", "regime", "sector", "factor", "attention",
    "insider", "short_int", "options", "spine", "forensics",
)


def context_dimension_frame(
    tickers: list[str],
    asof: str,
    root: Any = None,
) -> pd.DataFrame:
    """Flattened Context Snapshot frame, one row per ticker.

    Calls :func:`engine.neuralweb.context_api.context_frame` rather than
    re-deriving any dimension (canonical-source law).  Columns arrive already
    flattened as ``<dimension>__<field>`` and keep those names verbatim, so the
    store's provenance is legible.

    MEASURED COST (this machine, 2026-08-04): 0.302 s/ticker, linear — about
    7.7 min over a 1,540-name universe.  The dominant term is ``_insider_dim``,
    which re-reads every file in ``data/sec_insider/panel/`` per ticker.  The
    public API exposes NO dimension-subset parameter, so all 11 dimensions are
    always assembled; ``context_dims`` records that fact per row.
    """
    if not tickers:
        return pd.DataFrame()
    try:
        from engine.neuralweb import context_api
    except Exception as exc:  # noqa: BLE001 — minimal-deps lanes lack the import chain
        log.warning("us_context_vector: context_api unavailable (%s)", exc)
        return pd.DataFrame()
    try:
        frame = context_api.context_frame(list(tickers), date=_date(asof), root=root)
    except Exception as exc:  # noqa: BLE001 — context is additive; never fatal
        log.warning("us_context_vector: context_frame failed (%s)", exc)
        return pd.DataFrame()
    if frame is None or frame.empty:
        return pd.DataFrame()
    # ``date`` duplicates our own stamp_date; drop it rather than ship two.
    return frame.drop(columns=[c for c in ("date",) if c in frame.columns])


# --------------------------------------------------------------------------- #
# dtype stability + append
# --------------------------------------------------------------------------- #

_OBJECT_COLUMNS = (
    "stamp_date", "ticker", "name", "sector", "board_definition", "lane",
    "tier_cascade", "tier_sub", "gate_state", "gate_reason", "near_miss_reason",
    "signal_asof", "stage", "theme_membership_ids", "theme_primary_id",
    "theme_primary_name", "theme_label", "theme_reco", "relay_basket_id",
    "foresight_stage", "regime_dispersion_state", "regime_market_quad",
    "regime_quad_name", "regime_vol_regime", "context_dims",
)

_BOOL_COLUMNS = (
    "eligible", "buyable", "gate_provisional", "htf_s1", "htf_s2", "featured",
    "reports_within_7", "earnings_stale", "in_blackout",
    "antichase_shadow_blocked", "regime_gate_go", "theme_clean_entry",
)


def _coerce_nullable_objects(frame: pd.DataFrame) -> pd.DataFrame:
    """Avoid pandas/pyarrow dtype conflicts when an older column was all-null."""
    for column in (*_OBJECT_COLUMNS, *_BOOL_COLUMNS):
        if column in frame.columns:
            values = frame[column].astype(object)
            frame[column] = values.where(pd.notna(values), None)
    return frame


def append_candidates(
    verdicts: Mapping[str, Mapping[str, Any]],
    asof: str | None = None,
    *,
    board_definition: str,
    is_buyable,
    universe_meta: Mapping[str, Mapping[str, Any]] | None = None,
    board_rows: Mapping[str, Mapping[str, Any]] | None = None,
    lane_by_ticker: Mapping[str, str] | None = None,
    profile_rows: Mapping[str, Mapping[str, Any]] | None = None,
    ext_map: Mapping[str, Mapping[str, Any]] | None = None,
    blackout_map: Mapping[str, Mapping[str, Any]] | None = None,
    event_rows: Mapping[str, Mapping[str, Any]] | None = None,
    theme_pulse: Mapping[str, Mapping[str, Any]] | None = None,
    foresight_stages: Mapping[str, str] | None = None,
    closes: pd.DataFrame | None = None,
    gate_go: Any = None,
    root: Any = None,
    with_context_dims: bool = True,
) -> int:
    """Append one settled full-universe US context snapshot.  Returns row count.

    ``verdicts`` must be the COMPLETE ``sig_verdict`` map (every analyzed name,
    not just board rows) — the store's whole value is that ineligible names are
    present too.

    NIGHTLY IS THE SOLE ADVANCER.  The lane gate is the first statement: an
    intraday or render lane returns 0 without loading a single file, so the
    ~8-minute assembly is never paid off the nightly path and the store can
    never advance from a lane whose ``data/`` writes are discarded anyway.

    Best-effort telemetry: returns 0 on any refusal or failure and never raises,
    so a broken context input cannot break the nightly stock library.
    """
    if not ledger_lane.nightly_advance_enabled():
        log.info("us_context_vector append gated — not the US nightly lane")
        return 0

    stamp_date = _date(asof)
    if not stamp_date or not verdicts:
        return 0

    try:
        tickers = sorted(verdicts)
        membership = basket_membership(stamp_date, root=root)
        theme_ids: dict[str, list[str]] = {}
        for basket_id, members in membership.items():
            for ticker in members:
                theme_ids.setdefault(ticker, []).append(basket_id)

        from engine import prophet_doors

        relay = relay_features(
            closes, membership,
            high_lookback=prophet_doors.RELAY_HIGH_LOOKBACK,
            recent_sessions=prophet_doors.RELAY_RECENT_SESSIONS,
            position_window=prophet_doors.RELAY_POSITION_WINDOW,
            min_members=prophet_doors.RELAY_MIN_MEMBERS,
        )
        try:
            volumes = prophet_doors.load_volumes(root)
        except Exception as exc:  # noqa: BLE001
            log.warning("us_context_vector: volume caches unreadable (%s)", exc)
            volumes = None

        if event_rows is None:
            event_rows = event_features(
                tickers, closes, pd.Timestamp(stamp_date).date())
        if theme_pulse is None:
            theme_pulse = theme_pulse_by_ticker(membership, theme_state(root=root))
        if foresight_stages is None:
            foresight_stages = foresight_stage_map(root)

        records = build_records(
            verdicts,
            stamp_date=stamp_date,
            board_definition=board_definition,
            is_buyable=is_buyable,
            universe_meta=universe_meta,
            board_rows=board_rows,
            lane_by_ticker=lane_by_ticker,
            profile_rows=profile_rows,
            ext_map=ext_map,
            blackout_map=blackout_map,
            event_rows=event_rows,
            theme_ids=theme_ids,
            theme_pulse=theme_pulse,
            relay=relay,
            foresight_by_basket=basket_to_foresight(root=root),
            foresight_stages=foresight_stages,
            turnover=turnover_percentiles(volumes, stamp_date),
            eightk_days=eightk_recency(stamp_date, root=root),
            regime=regime_block(gate_go, root=root),
        )
        if not records:
            return 0

        new = pd.DataFrame(records)
        if with_context_dims:
            dims = context_dimension_frame(tickers, stamp_date, root=root)
            if not dims.empty:
                new = new.merge(dims, on="ticker", how="left")
                new["context_dims"] = "|".join(CONTEXT_DIMENSIONS)
            else:
                new["context_dims"] = None
        else:
            new["context_dims"] = None
        new = _coerce_nullable_objects(new)

        path = _store_path(root)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            prior = pd.read_parquet(path)
            # Schema union: a column added tonight is null for prior nights, and
            # a column retired tonight is preserved for the nights that had it.
            columns = list(dict.fromkeys([*prior.columns, *new.columns]))
            combined = pd.concat(
                [prior.reindex(columns=columns), new.reindex(columns=columns)],
                ignore_index=True,
            )
        else:
            combined = new

        # Keep-first: a rerun must never rewrite a night already stamped.
        combined = combined.drop_duplicates(subset=list(DEDUPE_KEY), keep="first")
        combined = _coerce_nullable_objects(combined)
        combined.to_parquet(path, index=False)
        return int(len(combined))
    except Exception as exc:  # noqa: BLE001 — research telemetry never breaks a build
        log.warning("us_context_vector append failed: %s", exc)
        return 0
