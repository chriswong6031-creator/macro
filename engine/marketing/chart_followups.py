"""engine.marketing.chart_followups — origination ledger + follow-up candidates.

TrendSpider hardening PR-C §5. **SPEC AND DATA ONLY.** This module writes two
JSONL artifacts and nothing else: no publisher change, no scheduler change, no
cadence change. Posting cadence belongs to another session's lane (masterplan
§5 backlog), and wiring a posting rail here would take that decision away from
the session that owns it.

WHY THE MECHANIC EXISTS. 48.7% of the corpus quotes its own prior post, and the
reach sweet spot is the **+2-4 day reawakening**: the level you drew on Monday
gets reached on Wednesday and you say so in three words. That is a
follow-up-first account, not an origination-first one, and it is the single
largest structural difference between their feed and ours.

THE DENOMINATOR IS THE WHOLE DESIGN (masterplan §1.3). Their follow-up pool is
survivorship-selected: they follow up the calls that moved. Build the pool that
way and the track record it implies is manufactured — the losers are simply
never mentioned again, so the denominator quietly deletes itself.

So the ledger row is written at **ORIGINATION**, for EVERY chart post that drew
a level, before anyone knows whether the level will be reached. The candidate
scan then reads that complete ledger and grades it. ``thesis_hurt`` rows are
FIRST-CLASS, not an afterthought: the corpus measures "ouch" follow-ups at 107k
median views against 76k for victory laps, so honesty is also the reach-optimal
play, and a scanner that only emitted wins would be leaving reach on the table
as well as lying.

Both writes are nightly-only by convention — the caller passes ``write=True``
exactly where it already passes ``write_shape_ledger=True`` — because nightly is
the sole advancer of forward ledgers (CLAUDE.md ledger law).
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Union

log = logging.getLogger(__name__)

PathLike = Union[str, Path]

#: Origination ledger — one row per chart post that drew a level. The honest
#: denominator; never filtered, never pruned by outcome.
LEDGER_REL = "data/marketing/chart_level_ledger.jsonl"

#: Tonight's follow-up candidates. Rewritten each run (it is a QUEUE, not a
#: ledger — a candidate that is no longer live must not linger).
CANDIDATES_REL = "data/marketing/followup_candidates.jsonl"

#: The +2-4 day reawakening window (§1.2). Younger than 2 days and the parent
#: is still in the timeline; older than 4 and the corpus measures the reach
#: falling away.
MIN_AGE_DAYS, MAX_AGE_DAYS = 2, 4

#: How close a session has to come to the drawn level to count as REACHING it.
_LEVEL_TOUCH_TOL = 0.005

#: The three triggers. Kept as data so a consumer can assert the vocabulary.
TRIGGERS: tuple[str, ...] = ("level_reached", "streak_extended", "thesis_hurt")


def _iso(value: object) -> date | None:
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except Exception:  # noqa: BLE001
        return None


def _age_days(origin: object, today: object) -> int | None:
    d0, d1 = _iso(origin), _iso(today)
    if d0 is None or d1 is None:
        return None
    return (d1 - d0).days


def origination_row(
    *,
    asset_id: str,
    ticker: str,
    drawn_level: float,
    origin_date: str,
    timeframe: str = "DAILY",
    claim_kind: str = "",
    fact_id: str = "",
    side: str = "",
    last_price: float | None = None,
    streak_len: int | None = None,
) -> dict[str, Any]:
    """One origination row. ``side`` is which way the level was being held.

    ``side`` is "support" when the post was made with price ABOVE the level and
    "resistance" when below; it is what makes ``thesis_hurt`` decidable later,
    and deriving it at origination rather than at scan time means a later price
    move cannot silently re-label which story the post was telling.
    """
    row: dict[str, Any] = {
        "asset_id": str(asset_id),
        "ticker": str(ticker).upper(),
        "drawn_level": round(float(drawn_level), 4),
        "origin_date": str(origin_date)[:10],
        "timeframe": str(timeframe or "DAILY").upper(),
        "claim_kind": str(claim_kind or ""),
        "fact_id": str(fact_id or ""),
        "side": str(side or ""),
    }
    if last_price is not None:
        row["origin_price"] = round(float(last_price), 4)
        if not row["side"]:
            row["side"] = "support" if float(last_price) >= float(drawn_level) else "resistance"
    if streak_len is not None:
        row["streak_len"] = int(streak_len)
    return row


def record_originations(root: PathLike, rows: list[dict]) -> int:
    """Append origination rows. Returns how many landed. Never raises.

    Idempotent by ``asset_id``: re-running a night must not double the
    denominator, which would silently halve every rate computed from it.
    """
    from engine.marketing.ledgers import append_jsonl, read_jsonl

    path = Path(str(root)) / LEDGER_REL
    try:
        seen = {str(r.get("asset_id")) for r in read_jsonl(path)}
    except Exception:  # noqa: BLE001
        seen = set()
    n = 0
    for row in rows or []:
        aid = str(row.get("asset_id") or "")
        if not aid or aid in seen:
            continue
        if append_jsonl(path, row):
            seen.add(aid)
            n += 1
    return n


def scan_candidates(
    root: PathLike,
    *,
    today: str,
    price_loader: Callable[[str], tuple[list[str], list[float], list[float], list[float]] | None] | None = None,
) -> list[dict]:
    """Follow-up candidates from the origination ledger. Never raises.

    *price_loader* returns ``(dates, highs, lows, closes)`` for a ticker; the
    default reads the same split-adjusted daily parquet the chart plotted, so a
    level "reached" here is reached on the series the reader saw.

    A parent yields AT MOST ONE candidate, and the triggers are checked in the
    order that matters: ``thesis_hurt`` first. A post whose level broke and
    whose level was also touched on the way through is an ouch, not a victory
    lap, and checking the happy trigger first would have relabelled it.
    """
    from engine.marketing.ledgers import read_jsonl

    rows = read_jsonl(Path(str(root)) / LEDGER_REL)
    if not rows:
        return []
    loader = price_loader or _default_price_loader(root)

    out: list[dict] = []
    for row in rows:
        age = _age_days(row.get("origin_date"), today)
        if age is None or not (MIN_AGE_DAYS <= age <= MAX_AGE_DAYS):
            continue
        tkr = str(row.get("ticker") or "").upper()
        try:
            level = float(row.get("drawn_level"))
        except (TypeError, ValueError):
            continue
        if not tkr or level <= 0:
            continue
        series = None
        try:
            series = loader(tkr)
        except Exception:  # noqa: BLE001
            series = None
        if not series or not series[0]:
            continue
        dates, highs, lows, closes = series
        since = [i for i, d in enumerate(dates)
                 if str(d)[:10] > str(row.get("origin_date"))[:10]]
        if not since:
            continue
        last_price = float(closes[-1])
        side = str(row.get("side") or "")

        trigger = ""
        # 1. THESIS HURT — the level the post was built on gave way. First,
        #    deliberately (see the docstring).
        for i in since:
            if side == "support" and closes[i] < level * (1 - _LEVEL_TOUCH_TOL):
                trigger = "thesis_hurt"
                break
            if side == "resistance" and closes[i] > level * (1 + _LEVEL_TOUCH_TOL):
                trigger = "thesis_hurt"
                break
        # 2. STREAK EXTENDED — a streak post whose streak grew.
        if not trigger and row.get("streak_len"):
            grew = _streak_grew(row, dates, closes, since)
            if grew:
                trigger = "streak_extended"
        # 3. LEVEL REACHED — price came back and touched the drawn line.
        if not trigger:
            for i in since:
                if lows[i] <= level * (1 + _LEVEL_TOUCH_TOL) <= highs[i] or \
                        lows[i] <= level <= highs[i]:
                    trigger = "level_reached"
                    break
        if not trigger:
            continue
        out.append({
            "parent_asset_id": str(row.get("asset_id") or ""),
            "ticker": tkr,
            "trigger": trigger,
            "age_days": age,
            "drawn_level": round(level, 4),
            "last_price": round(last_price, 4),
            # Carried so a future posting lane does not have to re-derive the
            # parent's story from its copy.
            "claim_kind": str(row.get("claim_kind") or ""),
            "timeframe": str(row.get("timeframe") or "DAILY"),
            "origin_date": str(row.get("origin_date") or "")[:10],
            "as_of": str(today)[:10],
        })
    out.sort(key=lambda r: (r["ticker"], r["parent_asset_id"]))
    return out


def _streak_grew(row: dict, dates: list[str], closes: list[float],
                 since: list[int]) -> bool:
    """Did the parent's streak keep going? Direction from the origination row."""
    try:
        origin_price = float(row.get("origin_price") or 0.0)
    except (TypeError, ValueError):
        return False
    if origin_price <= 0 or not since:
        return False
    # A down-streak extends when price keeps making lower closes; an up-streak
    # when it keeps making higher ones. The origination row does not store the
    # direction separately, so it is read off the side the level was held from.
    last = float(closes[-1])
    if str(row.get("side")) == "resistance":
        return last < origin_price
    return last > origin_price


def _default_price_loader(root: PathLike):
    """``(dates, highs, lows, closes)`` from the split-adjusted daily store."""
    def _load(ticker: str):
        from engine.marketing.chart_render import load_ohlcv
        bars = load_ohlcv(ticker, str(root), n=30)
        if not bars or not bars[0]:
            return None
        d, _o, h, l, c, _v = bars
        return d, h, l, c
    return _load


def write_candidates(root: PathLike, rows: list[dict]) -> str | None:
    """Rewrite ``followup_candidates.jsonl``. Returns the path, or None.

    A REWRITE, not an append: this file is tonight's queue. An append would
    leave last week's already-answered candidates in it, and a consumer reading
    the file as "what is live now" would re-post them.
    """
    import json

    path = Path(str(root)) / CANDIDATES_REL
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        body = "".join(
            json.dumps(r, ensure_ascii=False, separators=(",", ":")) + "\n"
            for r in rows)
        path.write_text(body, encoding="utf-8")
        return str(path)
    except Exception as exc:  # noqa: BLE001
        log.warning("chart_followups.write_candidates failed: %s", exc)
        return None


def run_nightly(root: PathLike, *, today: str, originations: list[dict]) -> dict:
    """Record tonight's originations, then scan and write the candidate queue.

    Returns a census for the plan artifact. Never raises — a follow-up artifact
    is a nice-to-have and must never be able to take the nightly down.
    """
    try:
        n_new = record_originations(root, originations)
    except Exception:  # noqa: BLE001
        n_new = 0
    try:
        rows = scan_candidates(root, today=today)
        path = write_candidates(root, rows)
    except Exception:  # noqa: BLE001
        rows, path = [], None
    by_trigger: dict[str, int] = {}
    for r in rows:
        by_trigger[r["trigger"]] = by_trigger.get(r["trigger"], 0) + 1
    return {
        "originations_recorded": n_new,
        "candidates": len(rows),
        "by_trigger": by_trigger,
        "path": path,
    }
