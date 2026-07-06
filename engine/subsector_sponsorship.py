"""engine.subsector_sponsorship — shared SRSS join/classification logic.

Phase 2 (Subsector Rotation Sponsorship Sensor). This module factors out the
nearest-prior-date join + sponsorship-state classification that Phase 0
(``research/entry_stack/sponsorship_phase0.py``) built and validated as a
RESEARCH-ONLY harness, so the PRODUCTION shadow-tier pipeline
(``engine.spine.adapt_subsector_sponsorship`` + the confluence graph edges)
can reuse the exact same join/classification rules instead of re-deriving a
subtly different convention. Phase 0 now imports from here too — this is the
ONE place the rules live.

Inputs this module operates on (read-only, never mutated):
  - data/subsector_rotation/snapshots.jsonl — PIT-frozen daily subsector
    rotation snapshots (engine/subsector_track_record.py is the producer).
    Fields on disk: date, key, name, theme, score (== emerging_score),
    rs_mom, accel, quadrant, stage, lean, members (frozen ticker list as of
    that date).

Leak-prevention rule (unchanged from Phase 0, research doc §8.5): a stock
event on date D may only join to a rotation snapshot row with date <= D, for
a subsector whose FROZEN member list (as recorded on that snapshot date)
contains the event's ticker. Never join to a rotation row dated after D. If
no such snapshot exists for that ticker as of D, the event is a no-match.

Sponsorship states: TAILWIND, EARLY_REPAIR, CONFIRMED_LEADERSHIP, HEADWIND,
ROLLOVER, NEUTRAL. See ``classify_sponsorship`` for the exact rules
(including the documented ROLLOVER-before-HEADWIND ordering deviation from
the research doc, preserved verbatim from Phase 0 for continuity).
"""
from __future__ import annotations

import bisect
import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

__all__ = [
    "STATES",
    "SNAPSHOTS_REL",
    "load_snapshots",
    "RotationIndex",
    "confidence_tier",
    "is_stale",
    "classify_sponsorship",
    "STALE_TRADING_DAYS",
    "SPONSORSHIP_PARQUET_REL",
    "load_display_rows",
    "plain_language",
    "EPISTEMIC_CAVEAT_EN",
    "EPISTEMIC_CAVEAT_ZH",
]

SNAPSHOTS_REL = ("data", "subsector_rotation", "snapshots.jsonl")

STALE_TRADING_DAYS = 5

STATES = (
    "TAILWIND", "EARLY_REPAIR", "CONFIRMED_LEADERSHIP",
    "HEADWIND", "ROLLOVER", "NEUTRAL",
)


# --------------------------------------------------------------------------- #
# loader
# --------------------------------------------------------------------------- #
def load_snapshots(root: Path) -> list[dict]:
    p = Path(root, *SNAPSHOTS_REL)
    if not p.exists():
        return []
    out = []
    for line in p.read_text().splitlines():
        if not line.strip():
            continue
        try:
            out.append(json.loads(line))
        except Exception:  # noqa: BLE001
            continue
    return out


# --------------------------------------------------------------------------- #
# symbol -> nearest-prior-date rotation row index (leak-safe by construction)
# --------------------------------------------------------------------------- #
class RotationIndex:
    """ticker -> sorted list of (date, row) where ticker was a FROZEN member
    of that snapshot's subsector. Lookup is bisect-based: nearest date <= D,
    never a date > D."""

    def __init__(self, snapshots: list[dict]):
        by_ticker: dict[str, list[tuple[pd.Timestamp, dict]]] = {}
        ambiguous = 0
        # group first so that if >1 key claims the same ticker on the same
        # date we can pick deterministically (highest score) rather than
        # silently taking whichever dict iteration order handed us first.
        same_date_candidates: dict[tuple[str, pd.Timestamp], list[dict]] = {}
        for row in snapshots:
            d = row.get("date")
            if not d:
                continue
            try:
                ts = pd.Timestamp(d)
            except Exception:  # noqa: BLE001
                continue
            for t in row.get("members") or []:
                same_date_candidates.setdefault((t, ts), []).append(row)

        for (t, ts), rows in same_date_candidates.items():
            if len(rows) > 1:
                ambiguous += 1
                score_key = lambda r: (r.get("score") if r.get("score") is not None else -1e9)
                row = max(rows, key=score_key)
            else:
                row = rows[0]
            by_ticker.setdefault(t, []).append((ts, row))

        for t in by_ticker:
            by_ticker[t].sort(key=lambda x: x[0])

        self._by_ticker = by_ticker
        self._dates_by_ticker = {t: [x[0] for x in v] for t, v in by_ticker.items()}
        self.ambiguous_ticker_dates = ambiguous
        self.distinct_keys = len({r.get("key") for r in snapshots if r.get("key")})

    def lookup(self, ticker: str, event_date: pd.Timestamp) -> dict | None:
        dates = self._dates_by_ticker.get(ticker)
        if not dates:
            return None
        idx = bisect.bisect_right(dates, event_date) - 1
        if idx < 0:
            return None  # every snapshot for this ticker is AFTER event_date — no leak allowed
        return self._by_ticker[ticker][idx][1]


# --------------------------------------------------------------------------- #
# confidence tier
# --------------------------------------------------------------------------- #
def confidence_tier(n_members: int | None) -> str:
    if n_members is None:
        return "none"
    if n_members < 3:
        return "none"
    if n_members <= 5:
        return "low"
    if n_members <= 11:
        return "medium"
    return "high"


def is_stale(rotation_date: pd.Timestamp | None, event_date: pd.Timestamp) -> bool:
    if rotation_date is None:
        return False
    try:
        bd = int(np.busday_count(rotation_date.date(), event_date.date()))
    except Exception:  # noqa: BLE001
        bd = (event_date - rotation_date).days
    return bd > STALE_TRADING_DAYS


# --------------------------------------------------------------------------- #
# sponsorship state classification — implements the research-doc rules
# literally, with the rs_ratio substitution the brief specifies (this
# ledger has no rs_ratio field, only score/rs_mom/accel):
#   EARLY_REPAIR substitute:          rs_mom > 0 and score < 0   (for rs_ratio < 0)
#   CONFIRMED_LEADERSHIP substitute:  score > 0                  (for rs_ratio > 0)
#   ROLLOVER substitute:              score > 0                  (for rs_ratio > 0)
# --------------------------------------------------------------------------- #
def classify_sponsorship(quadrant, rs_mom, accel, score, n_members, stale: bool) -> str:
    if stale or n_members is None or n_members < 3 or quadrant is None or rs_mom is None:
        return "NEUTRAL"

    accel_ok = True if accel is None else accel >= 0
    accel_neg = accel is not None and accel < 0

    if (quadrant in ("improving", "leading") and rs_mom > 0 and accel_ok
            and score is not None and score >= 1.0 and n_members >= 3):
        return "TAILWIND"

    if (quadrant == "improving" and rs_mom > 0 and accel_ok
            and score is not None and score < 0):
        return "EARLY_REPAIR"

    if (quadrant == "leading" and rs_mom > 0
            and score is not None and score > 0):
        return "CONFIRMED_LEADERSHIP"

    # DEVIATION (documented, preserved from Phase 0): the research doc lists
    # HEADWIND ("quadrant==weakening and rs_mom<0") ahead of ROLLOVER
    # ("quadrant==weakening and rs_mom<0 and score>0 substitute"), but
    # ROLLOVER's condition is a strict SUBSET of that HEADWIND clause — if
    # checked in the doc's literal order, ROLLOVER can never fire (dead
    # code), which defeats the purpose of having the state. ROLLOVER is
    # checked first here as the more specific case (a subsector still
    # showing a positive score while its momentum has already turned
    # negative — i.e. rolling over FROM leadership, distinct from generic
    # weakness). The generic weakening/lagging/accel-negative HEADWIND
    # clause is the fallback once ROLLOVER's tighter condition doesn't hold.
    if (quadrant == "weakening" and rs_mom < 0
            and score is not None and score > 0):
        return "ROLLOVER"

    if (quadrant == "lagging"
            or (quadrant == "weakening" and rs_mom < 0)
            or (accel_neg and rs_mom < 0)):
        return "HEADWIND"

    return "NEUTRAL"


# --------------------------------------------------------------------------- #
# UI-only display join (SRSS Phase 4) — reads the ALREADY-WRITTEN shadow
# parquet (engine.spine.write_subsector_sponsorship's output) plus the same
# snapshots.jsonl ledger, and enriches for display. This is a light read+join,
# never a recompute of the join/classification rules above — those already ran
# on the render-off-path nightly build. Kept in this module (not the builder
# scripts) so both site.-rendering call sites (subsector_rotation.html rails
# and the stock-page sponsorship chip) share ONE join, per this module's own
# "one place the rules live" convention.
# --------------------------------------------------------------------------- #
SPONSORSHIP_PARQUET_REL = ("data", "spine", "subsector_sponsorship.parquet")

# Plain-language per-state labels (EN, ZH) — never the word "validated".
_STATE_TEXT: dict[str, tuple[str, str]] = {
    "TAILWIND":             ("Group tailwind", "板块顺风"),
    "EARLY_REPAIR":         ("Group repair", "板块修复"),
    "CONFIRMED_LEADERSHIP": ("Confirmed group leadership", "确认板块领先"),
    "HEADWIND":             ("Group headwind", "板块逆风"),
    "ROLLOVER":             ("Group rolling over", "板块转向下行"),
    "NEUTRAL":              ("Group neutral", "板块中性"),
}
_STATE_VERB: dict[str, tuple[str, str]] = {
    "TAILWIND":             ("improving", "改善中"),
    "EARLY_REPAIR":         ("improving", "修复中"),
    "CONFIRMED_LEADERSHIP": ("leading", "领先"),
    "HEADWIND":             ("fighting headwinds", "逆风中"),
    "ROLLOVER":             ("rolling over", "转向下行"),
    "NEUTRAL":              ("flat", "持平"),
}

# The one honest epistemic caveat this whole feature is allowed to say. Never
# "validated" — see research/entry_stack/W2_SPONSORSHIP_PREREG.md §1/§8: the
# rotation ledger is a few trading days old and this is accruing shadow
# evidence, not a promoted signal.
EPISTEMIC_CAVEAT_EN = ("Accruing shadow evidence, not yet validated — the rotation ledger "
                       "is only days old; supporting context only, never a standalone signal.")
EPISTEMIC_CAVEAT_ZH = ("影子证据积累中，尚未验证 — 轮动台账仅有数天历史；仅作辅助背景，"
                       "绝非独立信号。")


def plain_language(name: str, name_zh: str | None, state: str,
                    rs_mom: float | None) -> tuple[str, str]:
    """One-line EN/ZH sentence, e.g. 'Group repair: V-SaaS improving, +2.17 RS
    momentum' (source-doc §7.2 style). Never uses the word 'validated'."""
    en_label, zh_label = _STATE_TEXT.get(state, _STATE_TEXT["NEUTRAL"])
    verb_en, verb_zh = _STATE_VERB.get(state, _STATE_VERB["NEUTRAL"])
    mom_en = f", {rs_mom:+.2f} RS momentum" if rs_mom is not None else ""
    mom_zh = f"，相对强度动量 {rs_mom:+.2f}" if rs_mom is not None else ""
    disp_name_zh = name_zh or name
    en = f"{en_label}: {name} {verb_en}{mom_en}"
    zh = f"{zh_label}：{disp_name_zh} {verb_zh}{mom_zh}"
    return en, zh


def load_display_rows(root=None, zh_lookup: "dict[str, dict] | None" = None) -> list[dict]:
    """Read ``data/spine/subsector_sponsorship.parquet`` (already written by
    ``engine.spine.write_subsector_sponsorship`` off the render path), keep
    the most-recent row per ticker, and enrich with subsector name/theme/
    rs_mom/accel from ``snapshots.jsonl`` (a dict lookup, not a recompute).

    ``zh_lookup``: optional ``{rotation_key: {"name_zh":..., "theme_zh":...}}``
    map (callers that already loaded ``site/marketdata/subsector_rotation.json``
    — which carries zh names — can pass it through so the display rows come
    back fully bilingual; without it, ``name_zh``/``theme_zh`` fall back to the
    English name, same convention as ``_tmName`` in subsector_rotation.js).

    Fail-open: returns [] on any missing/corrupt input. Every row is
    display_only (this parquet holds nothing else).
    """
    from lib import config
    r = Path(root) if root else config.ROOT
    p = Path(r, *SPONSORSHIP_PARQUET_REL)
    if not p.exists():
        return []
    try:
        df = pd.read_parquet(p)
    except Exception:  # noqa: BLE001
        return []
    if df.empty:
        return []

    snaps = load_snapshots(r)
    latest_by_key: dict[str, dict] = {}
    by_key_date: dict[tuple, dict] = {}
    for row in snaps:
        k = row.get("key")
        if not k:
            continue
        latest_by_key[k] = row  # append-ordered on disk -> last wins
        d = row.get("date")
        if d:
            by_key_date[(k, d)] = row

    zh_lookup = zh_lookup or {}
    seen_ticker: dict[str, dict] = {}
    for rec in df.to_dict("records"):
        try:
            meta = json.loads(rec.get("meta") or "{}")
        except Exception:  # noqa: BLE001
            meta = {}
        if not meta.get("display_only"):
            continue
        state = meta.get("sponsorship_state")
        if state not in STATES:
            continue
        ticker = rec.get("symbol")
        as_of = rec.get("as_of")
        if not ticker or not as_of:
            continue
        key = meta.get("rotation_key")
        rotation_asof = meta.get("rotation_asof")
        exact = by_key_date.get((key, rotation_asof))
        snap = exact or latest_by_key.get(key) or {}
        name = snap.get("name") or key or ""
        theme = snap.get("theme")
        zh = zh_lookup.get(key) or {}

        row_out = {
            "ticker": str(ticker),
            "as_of": str(as_of),
            "rotation_key": key,
            "name": name,
            "name_zh": zh.get("name_zh") or name,
            "theme": theme,
            "theme_zh": zh.get("theme_zh") or theme,
            "sponsorship_state": state,
            "confidence_tier": meta.get("confidence_tier"),
            "sponsorship_score": meta.get("sponsorship_score"),
            "n_members": meta.get("n_members"),
            "rotation_asof": rotation_asof,
            # rs_mom/accel are only trustworthy when we hit the EXACT
            # (key, rotation_asof) snapshot row; a latest-key fallback would
            # silently mix in a later day's momentum, so leave them None then.
            "rs_mom": exact.get("rs_mom") if exact else None,
            "accel": exact.get("accel") if exact else None,
            "source_lane": meta.get("source_lane"),
            "stale": bool(meta.get("stale")),
            "display_only": True,
        }
        prev = seen_ticker.get(ticker)
        if prev is None or (row_out["as_of"] or "") >= (prev["as_of"] or ""):
            seen_ticker[ticker] = row_out

    out = list(seen_ticker.values())
    out.sort(key=lambda r_: (r_["as_of"], r_["ticker"]), reverse=True)
    return out
