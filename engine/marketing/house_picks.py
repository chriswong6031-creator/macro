"""engine.marketing.house_picks — our own desks as a fact supply for W1 (E2).

OPERATOR RULING 2026-07-29: *"our site's pick engines are post sources too"*.
The Content Studio was sourcing tickers from Prophet plans, fired confluence
combos and the heatmap — and ignoring four pages of screens the site already
publishes every night. This module is the read-only join that puts them back in
the supply.

WHAT IT READS (all built by other lanes; nothing here writes)::

    site/factordata/impulse.json            scripts/build_impulse.py
    site/factordata/tech_screener.json      scripts/build_tech_lab_data.py
    site/allocationdata/special_situations.json
                                            scripts/build_special_situations.py

The congress desk (`congress_trades.html`) is deliberately ABSENT: its picks are
their own lane in `engine.marketing.congress_feed`, with the reporting-lag
honesty that page's own blog post demands. Sourcing it twice would put one
disclosure on the timeline as both a filing post and a "house pick".

WHAT A PICK IS, AND IS NOT. Every pick names the desk that produced it in PLAIN
WORDS — "our momentum screen", "our special-situations desk", "our tech lab" —
because a reader who cannot tell where a name came from cannot weigh it, and
"our tech lab" is a claim we can stand behind in a way "IMPULSE_SCORE 100" is
not. Each pick also carries the SOURCE ARTIFACT'S OWN disclosure verbatim in
plain words:

  * `special_situations.json` ships ``is_context_only: true`` and the sentence
    "Context only — an event-tracking display of public filings, not a signal,
    recommendation, or sizing input." A pick that dropped that on the way to a
    timeline would be laundering an event tracker into a call.
  * `tech_lab.json` ships ``universe_caveat: "survivor mega-caps; descriptive
    not §5.9 verdict"`` — a screen over survivors, described as one.
  * The impulse board is a state read, not an entry.

These picks are ADDITIONAL FACT SUPPLY for the EXISTING `watchlist` / `chart`
kinds. They introduce no kind, no writer change and no gate of their own: they
ride W1's cooldowns, reuse budget, shape mixer and approval gate exactly as a
Prophet-sourced watchlist item does.

Public API::

    lane_cfg(cfg)                     -> dict
    load_impulse(root)                -> dict | None
    load_tech_screener(root)          -> dict | None
    load_special_situations(root)     -> dict | None
    impulse_picks(data, *, limit)     -> list[dict]
    tech_lab_picks(data, *, limit)    -> list[dict]
    special_situation_picks(data, *, today, limit) -> list[dict]
    pick_facts(pick)                  -> dict          (FactPacket)
    house_picks(root, *, today, cfg, cooled, exclude) -> list[dict]
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from engine.marketing.congress_feed import (
    display_entity_name,
    display_price,
    fold_numbers,
    parse_iso_date,
    sentence_case,
)

__all__ = [
    "DEFAULTS",
    "DESK_WORDS",
    "lane_cfg",
    "load_impulse",
    "load_tech_screener",
    "load_special_situations",
    "impulse_picks",
    "tech_lab_picks",
    "special_situation_picks",
    "pick_facts",
    "house_picks",
]

_IMPULSE_REL = Path("site") / "factordata" / "impulse.json"
_TECH_SCREENER_REL = Path("site") / "factordata" / "tech_screener.json"
_SPECIAL_REL = Path("site") / "allocationdata" / "special_situations.json"

#: engine id → the words a reader gets. The engine id NEVER reaches copy: the
#: design doctrine bans internal state names, study names and raw slugs from
#: user-facing surfaces, and "EARLY_IGNITION" is all three.
DESK_WORDS: dict[str, str] = {
    "impulse": "our momentum screen",
    "special_situations": "our special-situations desk",
    "tech_lab": "our tech lab",
}

#: Each desk's honest posture, carried into every packet it produces. Sourced
#: from the artifacts' own disclosure fields, restated in plain words.
DESK_DISCLOSURE: dict[str, str] = {
    "impulse": "That is a read on where the move is in its life, not an entry.",
    "special_situations": (
        "This is event tracking off public filings — context, not a "
        "recommendation."),
    "tech_lab": (
        "The screen runs over long-surviving large caps, so it describes that "
        "group and not the whole market."),
}

#: Impulse states worth a post, in preference order. EXTENDED_RUN and FADING are
#: deliberately excluded from the default: "this already ran" is a fine internal
#: state and a bad post, and the doctrine's "so what do I do" test has no honest
#: answer for it beyond "nothing".
_IMPULSE_STATES: tuple[str, ...] = ("EARLY_IGNITION", "IGNITING", "COILING")

#: Plain words for each impulse state.
_IMPULSE_WORDS: dict[str, str] = {
    "EARLY_IGNITION": "just started moving",
    "IGNITING": "has been moving for a few sessions now",
    "COILING": "has gone quiet and tight",
}

#: Special-situation categories that are a legible story to a general reader.
_SPECIAL_CATEGORIES: tuple[str, ...] = (
    "Acquisitions", "Divestitures", "Capital Returns", "Spinoffs",
    "Restructuring", "Delistings",
)

#: Deal-stage slugs → plain words. An unmapped stage is DROPPED from the copy
#: rather than printed raw: "(ASH), vote-scheduled" is a slug wearing a comma.
_STAGE_WORDS: dict[str, str] = {
    "announced": "just announced",
    "vote-scheduled": "with a shareholder vote on the calendar",
    "completed": "now completed",
    "pending": "still pending",
    "notice": "at the notice stage",
    "rumoured": "still only reported, not confirmed",
    "rumored": "still only reported, not confirmed",
}

DEFAULTS: dict[str, Any] = {
    "enabled": True,
    #: Per-desk caps. Small on purpose — this is supply for existing kinds, and
    #: a screen that contributes twenty names is a screen that owns the plan.
    "max_impulse": 3,
    "max_tech_lab": 2,
    "max_special": 2,
    #: A special situation older than this is not news any more.
    "special_max_age_days": 3,
    #: Impulse picks below this score are the tail of the board.
    "min_impulse_score": 80,
    #: Only US common stock: the marketing lane's charts and cashtags assume it.
    "us_only": True,
}


def lane_cfg(cfg: dict | None) -> dict[str, Any]:
    """Resolved `house_picks` block — defaults filled, types coerced."""
    block = ((cfg or {}).get("house_picks") or {}) if isinstance(cfg, dict) else {}
    out = dict(DEFAULTS)
    if isinstance(block, dict):
        for key in DEFAULTS:
            if block.get(key) is not None:
                out[key] = block[key]
    out["enabled"] = bool(out["enabled"])
    out["us_only"] = bool(out["us_only"])
    for key in ("max_impulse", "max_tech_lab", "max_special",
                "special_max_age_days", "min_impulse_score"):
        try:
            out[key] = max(int(out[key]), 0)
        except (TypeError, ValueError):
            out[key] = DEFAULTS[key]
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Sources (read-only, fail-soft)
# ─────────────────────────────────────────────────────────────────────────────

def _load_json(root: Path | str | None, rel: Path) -> dict | None:
    try:
        path = (Path(root) if root is not None else Path(".")) / rel
        if not path.exists():
            return None
        text = path.read_text(encoding="utf-8")
        if not text.strip():
            return None
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except Exception:  # noqa: BLE001
        return None


def load_impulse(root: Path | str | None = None) -> dict | None:
    """`site/factordata/impulse.json`, or None (fail-soft)."""
    return _load_json(root, _IMPULSE_REL)


def load_tech_screener(root: Path | str | None = None) -> dict | None:
    """`site/factordata/tech_screener.json`, or None (fail-soft)."""
    return _load_json(root, _TECH_SCREENER_REL)


def load_special_situations(root: Path | str | None = None) -> dict | None:
    """`site/allocationdata/special_situations.json`, or None (fail-soft)."""
    return _load_json(root, _SPECIAL_REL)


# ─────────────────────────────────────────────────────────────────────────────
# Per-desk pick extraction
# ─────────────────────────────────────────────────────────────────────────────

def _pick(engine: str, ticker: str, **extra: Any) -> dict:
    """One pick, with its desk named in plain words and its posture attached."""
    return {
        "ticker": str(ticker).upper(),
        "engine": engine,
        "engine_words": DESK_WORDS.get(engine, "one of our screens"),
        "disclosure": DESK_DISCLOSURE.get(engine, ""),
        "source": "house_picks",
        **extra,
    }


def impulse_picks(data: dict | None, *, limit: int = 3, min_score: int = 80) -> list[dict]:
    """Fresh momentum-screen names, best first.

    Reads the state buckets `impulse.json` publishes (buy / igniting / coiling)
    rather than re-deriving anything — the builder owns the arithmetic, this is
    a join.
    """
    if not isinstance(data, dict) or str(data.get("status") or "") != "ok":
        return []
    rows: list[dict] = []
    for bucket in ("buy", "igniting", "coiling"):
        for row in (data.get(bucket) or []):
            if not isinstance(row, dict):
                continue
            state = str(row.get("state") or "")
            ticker = str(row.get("ticker") or "").strip().upper()
            try:
                score = int(row.get("impulse_score") or 0)
            except (TypeError, ValueError):
                score = 0
            if not ticker or state not in _IMPULSE_STATES or score < min_score:
                continue
            rows.append(_pick(
                "impulse", ticker,
                name=str(row.get("name") or ticker),
                sector=str(row.get("sector") or ""),
                price=row.get("price"),
                state=state,
                state_words=_IMPULSE_WORDS.get(state, "is on the board"),
                just_starting=bool(row.get("just_starting")),
                days_igniting=row.get("days_igniting"),
                _rank=(-score, ticker),
            ))
    rows.sort(key=lambda r: r["_rank"])
    seen: set[str] = set()
    out: list[dict] = []
    for row in rows:
        if row["ticker"] in seen:
            continue
        seen.add(row["ticker"])
        row.pop("_rank", None)
        out.append(row)
    return out[:limit]


def tech_lab_picks(data: dict | None, *, limit: int = 2) -> list[dict]:
    """Names whose tech-lab signal set is currently firing, best first.

    Ranked by the screener's own `active_buy` count with its composite `score`
    as the tiebreak. Neither number reaches copy — the packet says "most of the
    signals we track are pointing the same way", which is what the count means.
    """
    if not isinstance(data, dict):
        return []
    stocks = data.get("stocks")
    if not isinstance(stocks, dict):
        return []
    rows: list[dict] = []
    for ticker, row in stocks.items():
        if not isinstance(row, dict):
            continue
        try:
            active_buy = int(row.get("active_buy") or 0)
            active_total = int(row.get("active_total") or 0)
            score = float(row.get("score") or 0.0)
        except (TypeError, ValueError):
            continue
        if active_total <= 0 or active_buy <= 0:
            continue
        share = active_buy / active_total
        # A majority of the tracked signals, or it is not a read.
        if share < 0.6:
            continue
        rows.append(_pick(
            "tech_lab", str(ticker),
            name=str(row.get("name") or ticker),
            price=row.get("price"),
            band=str(row.get("band") or ""),
            active_buy=active_buy,
            active_total=active_total,
            _rank=(-share, -score, str(ticker)),
        ))
    rows.sort(key=lambda r: r["_rank"])
    for row in rows:
        row.pop("_rank", None)
    return rows[:limit]


def special_situation_picks(
    data: dict | None,
    *,
    today: str,
    limit: int = 2,
    max_age_days: int = 3,
    us_only: bool = True,
) -> list[dict]:
    """Freshly-dated corporate events with a legible category, newest first."""
    if not isinstance(data, dict):
        return []
    by_ticker = data.get("by_ticker")
    if not isinstance(by_ticker, dict):
        return []
    today_d = parse_iso_date(today)
    if today_d is None:
        return []
    rows: list[dict] = []
    for row in by_ticker.values():
        if not isinstance(row, dict):
            continue
        ticker = str(row.get("ticker") or "").strip().upper()
        # A ticker carrying an exchange suffix ("2551.HK") is not a US cashtag.
        if not ticker or "." in ticker:
            continue
        if us_only and str(row.get("country") or "").upper() != "US":
            continue
        category = str(row.get("category") or "").strip()
        if category not in _SPECIAL_CATEGORIES:
            continue
        event_d = parse_iso_date(row.get("date"))
        if event_d is None or not (0 <= (today_d - event_d).days <= max_age_days):
            continue
        rows.append(_pick(
            "special_situations", ticker,
            name=str(row.get("company") or ticker),
            category=category,
            stage=str(row.get("stage") or ""),
            event_date=event_d.isoformat(),
            confidence=str(row.get("confidence") or ""),
            _rank=(-event_d.toordinal(), ticker),
        ))
    rows.sort(key=lambda r: r["_rank"])
    seen: set[str] = set()
    out: list[dict] = []
    for row in rows:
        if row["ticker"] in seen:
            continue
        seen.add(row["ticker"])
        row.pop("_rank", None)
        out.append(row)
    return out[:limit]


# ─────────────────────────────────────────────────────────────────────────────
# Fact packet
# ─────────────────────────────────────────────────────────────────────────────

def pick_facts(pick: dict) -> dict:
    """FactPacket for one house pick: ``{facts, numbers_whitelist}``.

    The lead fact ALWAYS names the desk ("our momentum screen has …"), and the
    desk's own disclosure always ships with it. There is no code path that
    produces a house-pick packet without attribution, because an unattributed
    screen output is indistinguishable from a call.
    """
    ticker = str(pick.get("ticker") or "")
    desk = str(pick.get("engine_words") or "one of our screens")
    engine = str(pick.get("engine") or "")
    name = display_entity_name(pick.get("name") or ticker)
    price_s = display_price(pick.get("price"))

    if engine == "impulse":
        lead = (f"{desk} has {ticker} in the group that "
                f"{pick.get('state_words', 'is on the board')}.")
    elif engine == "tech_lab":
        lead = (f"{desk} has most of the signals it tracks on {ticker} "
                f"pointing the same way right now.")
    elif engine == "special_situations":
        stage_words = _STAGE_WORDS.get(str(pick.get("stage") or "").strip().lower(), "")
        stage_clause = f", {stage_words}" if stage_words else ""
        lead = (f"{desk} is tracking a "
                f"{str(pick.get('category') or 'corporate event').lower()} story at "
                f"{name} ({ticker}){stage_clause}.")
    else:
        lead = f"{desk} surfaced {ticker}."

    facts: list[dict] = [
        {"id": "house_pick_lead", "text": sentence_case(lead), "salience": 10}]

    if price_s:
        facts.append({
            "id": "house_pick_price",
            "text": f"{ticker} last traded around ${price_s}.",
            "salience": 6,
        })

    disclosure = str(pick.get("disclosure") or "").strip()
    if disclosure:
        facts.append({
            "id": "house_pick_disclosure",
            "text": disclosure,
            "salience": 4,
        })

    return fold_numbers(facts)


# ─────────────────────────────────────────────────────────────────────────────
# Pipeline
# ─────────────────────────────────────────────────────────────────────────────

def house_picks(
    root: Path | str | None = None,
    *,
    today: str | None = None,
    cfg: dict | None = None,
    cooled: frozenset[str] | set[str] | None = None,
    exclude: frozenset[str] | set[str] | None = None,
) -> list[dict]:
    """Every desk's fresh picks, deduped, cooled names removed, facts attached.

    `exclude` is the set of tickers the plan has already claimed tonight
    (Prophet, confluence, movers): a house pick is EXTRA supply, so it never
    displaces a name a producer already put on the board.

    Interleaved round-robin across desks rather than concatenated, so a single
    prolific screen cannot take every slot when the caller truncates.
    """
    lane = lane_cfg(cfg)
    if not lane["enabled"]:
        return []
    if today is None:
        today = date.today().isoformat()
    blocked = {str(t).upper() for t in (cooled or ())} | {
        str(t).upper() for t in (exclude or ())}

    by_desk = [
        impulse_picks(load_impulse(root),
                      limit=lane["max_impulse"], min_score=lane["min_impulse_score"]),
        special_situation_picks(load_special_situations(root), today=today,
                                limit=lane["max_special"],
                                max_age_days=lane["special_max_age_days"],
                                us_only=lane["us_only"]),
        tech_lab_picks(load_tech_screener(root), limit=lane["max_tech_lab"]),
    ]

    out: list[dict] = []
    seen: set[str] = set()
    for column in range(max((len(d) for d in by_desk), default=0)):
        for desk in by_desk:
            if column >= len(desk):
                continue
            pick = desk[column]
            ticker = pick["ticker"]
            if ticker in blocked or ticker in seen:
                continue
            seen.add(ticker)
            pick["facts"] = pick_facts(pick)
            out.append(pick)
    return out
