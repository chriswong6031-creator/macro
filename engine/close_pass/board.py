"""engine.close_pass.board — the provisional board payload, from closes alone.

WHAT THIS COMPUTES, AND WHAT IT REFUSES TO
==========================================
Membership and ordering are different questions with different answers here, and
conflating them is the whole trap this module is shaped around.

MEMBERSHIP is exact. ``engine.signal_gate.gate()`` takes one data argument — a
daily close series — and everything it calls stays inside that: ``analyze()`` is
close-only by construction (``signal_gate`` docstring: it stochs the RSI of
close and never needs high/low) and ``confluence_tiers.cascade()``'s only
positional data argument is the same series (``market`` is a static suffix
label, ``event_latch`` an in-memory cache over the same history). No FINRA, no
open interest, no fundamentals, no SUE, no insider, no 13F, no LLM. So "who
would tonight's gate admit" is answerable at 16:20 ET and the answer is the real
one, not an approximation.

ORDERING is PARTIAL, and the masterplan's premise that it is not was measured
false. Of ``us_board_rank.SCORE_WEIGHTS``' five legs, exactly two are computable
from closes alone:

  signal  30  verdict.tier_cascade / provisional / ticks — all written by
              gate() above.                                        CLOSE-ONLY
  runway  10  row.ext_z / antichase_shadow_blocked — engine.extension reads a
              close matrix and nothing else.                       CLOSE-ONLY
  entry   25  entry.status ← engine.cycles.ladder_state(), which formally takes
              a net-liquidity regime, a macro risk score, THIS NAME'S SECTOR
              BETA and a vol regime; cycle_state() also takes `high`.  OMITTED
  edge    25  row.alpha ← engine.residual_alpha, which is sector-NEUTRALISED by
              construction: it needs a GICS label per name and a full-universe
              cross-section, not one name's history.                OMITTED
  quality 10  row.coiled{star,coiled} ← coiled.cohort_fractions(), a
              sector-cohort percentile. (washout_ctx alone IS close-only; the
              star/coiled verdict that scores 1.0/0.8 is not.)      OMITTED

Those three are OMITTED AND DISCLOSED — never imputed, never back-filled from
last night's artifact, and the weights are NOT renormalised over the surviving
legs. Renormalising would silently redefine what a point means and produce a
number that looks like the nightly's score and is not it; the payload carries
``weight_covered: 40`` and the reader of the payload is told which 60 points are
missing and why. A provisional order over 40 points of evidence, honestly
labelled, is worth more than a fabricated 100.

None of the omitted inputs is a FINRA / OI / fundamental figure — every one of
those is already in ``us_board_rank.ZERO_SCORE_AUTHORITY`` at zero weight. What
the omitted legs actually need is a sector classification and a macro regime
read. That is a weaker claim than "the score legs are 100% price-derived" and a
stronger one than "the board needs alternative data", and it is the true one.

WHY THE FUNCTIONS ARE IMPORTED, NEVER REIMPLEMENTED
Both surviving legs are scored by calling ``us_board_rank``'s own
``signal_value`` / ``runway_value``. A local copy would be a second definition
of the board's scoring language that drifts the first time either is re-tuned —
and ``signal_value``'s docstring documents a deliberately frozen non-monotone
shape that a reimplementation would "fix" and thereby disagree.
"""
from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, time, timedelta, timezone
from typing import Any

from engine import signal_gate, us_board_rank

#: The payload the W-L1b surface consumes. Bump on any breaking shape change.
SCHEMA = "us_board_provisional/v1"
#: Lane marker, in the vocabulary closing-bell.yml's stamp already established
#: ({as_of, provisional: true, lane: …}) rather than a second convention.
LANE = "closepass"

#: The legs a close-only pass computes. Order is the payload's display order.
CLOSE_DERIVED_LEGS = ("signal", "runway")
#: The legs it refuses to compute, each with the input that makes it impossible.
#: Published verbatim in the payload — a disclosure the consumer can render is
#: the difference between an omission and a silent hole.
OMITTED_LEGS: dict[str, str] = {
    "entry": "ladder_state needs a net-liquidity regime, a macro risk score, "
             "this name's sector beta and a vol regime",
    "edge": "residual alpha is sector-neutralised — it needs a sector label and "
            "a full-universe cross-section",
    "quality": "the coiled/star verdict is a sector-cohort percentile",
}
#: Points of us_board_rank.SCORE_WEIGHTS this pass can actually stand behind.
WEIGHT_COVERED = sum(us_board_rank.SCORE_WEIGHTS[k] for k in CLOSE_DERIVED_LEGS)


#: Every key a card row may carry, and NOTHING else (W-L1d).
#:
#: THE PAYLOAD SHIPS FACTS, THE CLIENT SHIPS WORDS. `verb`, the edge/priority
#: figure and its label, every tip, chip and bilingual sentence are DERIVED
#: client-side from `signal`/`runway` through the client's own lexicon. Two
#: reasons, both load-bearing: a rendered word makes the payload
#: language-specific (this artifact is polled by EN and ZH readers alike, and
#: shipping both copies doubles a poll that every dashboard reader pays every
#: 120s), and it would stand up a second owner of a vocabulary that already has
#: one. A word in here is a bug even when the word is right.
CARD_FIELDS = (
    "tk", "sym", "mkt", "href", "date",
    "name", "name_zh", "sec", "sec_zh",
    "price_txt", "spark", "signal", "runway",
)
#: The subset a card cannot be RENDERED without. A row that cannot fill all of
#: them leaves the board projection entirely rather than shipping half-filled
#: under a `card_complete: true` flag — see `build_board`'s ruling.
CARD_REQUIRED = ("tk", "sym", "mkt", "href", "name", "price_txt",
                 "signal", "runway")

#: The nightly's OWN ticker-page URL, read out of `templates/dashboard.html.j2`'s
#: pv_card call site (`'href': 'stock.html#' ~ n.ticker`) rather than invented. A
#: second URL convention would send the evening board's cards somewhere the
#: morning board's cards do not go, and the reader would find the difference
#: before we did.
TICKER_PAGE = "stock.html"
#: The card's market suffix, as that same call site passes it (`'mkt': 'us'`).
MARKET = "us"


#: When the nightly board of record is expected to be live, as a UTC wall time.
#: daily.yml fires 22:30 UTC and runs for hours; the board of record has been
#: landing by ~05:00-06:00 UTC. This is the BACKSTOP on how long "ahead of the
#: record" stays true, not the primary guard — that is the ticker match below.
#: Deliberately not optimistic: an expiry set later than the nightly's landing
#: would let a stamp claim the cards are ahead of a record that has arrived.
NIGHTLY_EXPECTED_BY_UTC = time(6, 0)


def valid_until(built_at: datetime) -> datetime:
    """The first NIGHTLY_EXPECTED_BY_UTC strictly after ``built_at``."""
    stamp = built_at.astimezone(timezone.utc)
    edge = stamp.replace(hour=NIGHTLY_EXPECTED_BY_UTC.hour,
                         minute=NIGHTLY_EXPECTED_BY_UTC.minute,
                         second=0, microsecond=0)
    return edge if edge > stamp else edge + timedelta(days=1)


def _text(value: Any) -> str | None:
    """A display string, or None. Empty and whitespace are NOT display values.

    `_spark_svg` returns ``""`` for a series too short to draw and the universe
    carries the odd blank name, so without this an empty string would sail
    through the required-field check and render as a hole on the card.
    """
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def card_row(row: Mapping[str, Any],
             display: Mapping[str, Any] | None) -> dict | None:
    """One admitted row + its display facts → a card row, or None if unfillable.

    Returns None rather than a partial dict: a row that cannot fill
    `CARD_REQUIRED` is dropped from the projection by `board_state`, which is
    what keeps `card_complete: true` an honest claim about every row that ships
    (W-L1d gate 3). Every `CARD_FIELDS` key is always PRESENT so the shape does
    not vary row to row; the optional ones may be null.

    `edge` IS NEVER EMITTED, and no 100-scale number appears here at all. The
    board's edge leg is sector-neutralised and this pass cannot compute it
    (OMITTED_LEGS); `points` is a figure on the real 100-point weights of which
    this pass covers 40, so publishing it beside a card would read as the
    nightly's score and would not be it. The client gets the two legs that ARE
    computed, on their own [0,1] scale, and derives its own words from them.
    """
    d = display or {}
    ticker = row["ticker"]
    price = d.get("price")
    legs = row.get("legs") or {}
    card = {
        "tk": ticker,
        # The nightly's US call site passes no `sym` and the card macro falls
        # back to `tk`; they are the same string for a US name. Stated rather
        # than left to the fallback so the live-quote overlay's `data-sym` is
        # populated from data on both boards.
        "sym": ticker,
        "mkt": MARKET,
        "href": f"{TICKER_PAGE}#{ticker}",
        "date": _text(row.get("signal_asof")),
        "name": _text(d.get("name")),
        "name_zh": _text(d.get("name_zh")),
        "sec": _text(d.get("sec")),
        "sec_zh": _text(d.get("sec_zh")),
        "price_txt": None if price is None else f"${float(price):.2f}",
        "spark": _text(d.get("spark")),
        "signal": legs.get("signal"),
        "runway": legs.get("runway"),
    }
    if any(card[k] is None for k in CARD_REQUIRED):
        return None
    return card


def board_state(payload: Mapping[str, Any], *, rel: str = "ahead") -> dict:
    """The small view the W-L1b surface consumes, as ``prophet_live.json``'s
    optional top-level ``board_state`` key.

    ONE ARTIFACT, ONE POLL. The surface rides the artifact the live strip
    already fetches rather than opening a second hydration path, so this is a
    projection of the full board rather than a second copy of it. The full
    payload stays where it is — it is what the confirmation delta grades and
    what the sentinel measures.

    ``board.tickers`` IS THE SAFETY PROPERTY, not a convenience. The client
    compares it against the ordered ``data-ticker`` values of the cards actually
    in the grid and paints nothing on a mismatch, which turns spec gate §0-2
    ("rel == 'ahead' only when the rendered cards came from the evening board")
    from an intention into a property of the code: a page still showing last
    night's cards CANNOT render tonight's stamp, whatever this producer claims.
    So the order here must be the board's own display order and nothing else —
    sorting or filtering it to look tidier would silently disarm the guard.

    ``rel`` is only ever 'ahead' from this lane. 'behind' would need a producer
    that runs on the evenings this one did NOT publish, and it is mandatory to
    carry ``confirmed_label`` with it — asserted rather than commented, because
    an undated stale board is the exact ambiguity that misleads. 'confirmed'
    (state 2) is never published here at all: it is the nightly render's own
    server-side receipt and the client refuses to paint it from the live plane.
    """
    if rel not in ("ahead", "behind"):
        raise ValueError(f"rel must be 'ahead' or 'behind', not {rel!r}")
    built = datetime.fromisoformat(payload["built_at"].replace("Z", "+00:00"))
    complete = bool((payload.get("consumer_contract") or {}).get("card_complete"))
    # PARALLEL BY CONSTRUCTION, never by convention. `tickers` and `cards` are
    # taken from ONE filtered list in ONE pass, so there is no second traversal
    # that could drift and no order to keep in sync by hand. When the board is
    # not card-complete the projection degrades to exactly what it published
    # before W-L1d — the full ticker list and no `cards` key at all, which is
    # the shape the client already refuses to render cards from.
    rendered = ([row for row in payload["names"] if row.get("card")] if complete
                else list(payload["names"]))
    board = {
        "as_of": payload["as_of"],
        "lane": payload["lane"],
        "card_complete": complete,
        "tickers": [row["ticker"] for row in rendered],
    }
    if complete:
        board["cards"] = [row["card"] for row in rendered]
    return {
        "rel": rel,
        "note": rel,
        "generated_at": payload["built_at"],
        "valid_until": valid_until(built).isoformat().replace("+00:00", "Z"),
        "board": board,
    }


def close_legs(verdict: Mapping[str, Any] | None,
               ext: Mapping[str, Any] | None) -> dict[str, float]:
    """The close-derived legs, scored by the board's OWN leg functions.

    ``ext`` is one ``engine.extension.extension_signals`` row; its ``ext_z`` and
    the antichase flag derived from it are the whole of ``runway``'s input.
    """
    ext = ext or {}
    row = {
        "ext_z": ext.get("ext_z"),
        # Derived here rather than read: the builder stamps this field far
        # downstream, and a close-pass row has not been through that pass. Same
        # threshold, named from the same constant, so the two cannot drift.
        "antichase_shadow_blocked": (
            None if ext.get("ext_z") is None
            else bool(float(ext["ext_z"]) > us_board_rank.EXT_Z_FULL)
        ),
    }
    return {
        "signal": round(us_board_rank.signal_value(verdict), 6),
        "runway": round(us_board_rank.runway_value(row), 6),
    }


def _points(legs: Mapping[str, float]) -> float:
    """Legs in [0,1] → points, on the board's real weights (never renormalised)."""
    return round(sum(us_board_rank.SCORE_WEIGHTS[k] * float(v)
                     for k, v in legs.items()), 4)


def build_board(
    verdicts: Mapping[str, Mapping[str, Any]],
    ext_by: Mapping[str, Mapping[str, Any]],
    *,
    session: str,
    built_at: datetime,
    adjustment_by: Mapping[str, str] | None = None,
    price_through: Mapping[str, str] | None = None,
    display_by: Mapping[str, Mapping[str, Any]] | None = None,
    universe_n: int | None = None,
    skipped: Mapping[str, int] | None = None,
) -> dict:
    """Verdicts + extension rows → the provisional board payload.

    Pure: no I/O, no clock read, no ``data/`` path. Every caller (the lane, the
    tests, a replay) gets the same payload for the same inputs, which is what
    makes the confirmation delta a measurement rather than an opinion.

    ``display_by`` carries the per-name DISPLAY FACTS a card needs and this
    module deliberately cannot fetch: name, sector, last price, sparkline. It is
    an argument rather than a lookup because everything here stays pure — the
    lane that already opens the price store gathers them in the same pass
    (``scripts.close_pass_publish.collect``) and hands them in. Omit it entirely
    and the payload is honestly NOT card-complete, which is what every caller
    that only wants membership and legs (the reconciler, a replay) still gets.

    ``adjustment_by`` names each name's PRICE BASIS (W-L0 gate 3 — name the
    adjustment at every seam). It is per-name and not a single lane-wide string
    on purpose: ``build_stock_library.universe()`` genuinely returns a mixed
    population — the deep ``stocks`` group is split-and-dividend adjusted while
    the four breadth close caches are raw vendor prints — so one lane-level
    label would be false for whichever family it did not describe. A name with
    no declared basis is dropped rather than assumed; an unnamed basis is
    exactly the defect gate 3 exists to stop.
    """
    adjustment_by = adjustment_by or {}
    price_through = price_through or {}
    counts = dict(skipped or {})

    rows: list[dict] = []
    for ticker in sorted(verdicts):
        verdict = verdicts[ticker] or {}
        basis = adjustment_by.get(ticker)
        if not basis:
            counts["no_price_basis"] = counts.get("no_price_basis", 0) + 1
            continue
        legs = close_legs(verdict, ext_by.get(ticker))
        rows.append({
            "ticker": ticker,
            "admitted": bool(signal_gate.is_buyable(verdict)),
            "eligible": bool(verdict.get("eligible")),
            "tier_cascade": verdict.get("tier_cascade"),
            "tier_sub": verdict.get("tier_sub"),
            "ticks": verdict.get("ticks"),
            "provisional_verdict": bool(verdict.get("provisional")),
            "signal_asof": verdict.get("asof"),
            "legs": legs,
            "points": _points(legs),
            "price_basis": basis,
            "price_through": price_through.get(ticker),
        })

    # Ordering is a DISPLAY order over the covered weight, never a re-admission:
    # `admitted` is decided by the gate alone and no sort below can change it
    # (us_board_rank: "the buy lane's membership is decided by the confluence
    # admission gate alone and is unchanged by this ranking").
    admitted = [r for r in rows if r["admitted"]]
    admitted.sort(key=lambda r: (-r["points"], r["ticker"]))
    for i, row in enumerate(admitted, start=1):
        row["provisional_rank"] = i
        if display_by is not None:
            # Cards are built for ADMITTED rows only. An evaluated-but-not-
            # admitted row is a diagnostic record, never a rendered card, so
            # building one would be work whose only consumer is the file size.
            card = card_row(row, display_by.get(row["ticker"]))
            if card is not None:
                row["card"] = card

    # `card_complete` IS A CLAIM ABOUT EVERY ROW THAT SHIPS, so it is computed
    # from the cards actually built and never asserted from the fact that
    # display inputs arrived. A row that could not fill a required field is
    # dropped from the projection (board_state) and counted here rather than
    # shipped half-filled under a true flag — the alternative the W-L1d ruling
    # allows, darkening the WHOLE board over one blank name, would throw away
    # ~130 good cards to disclose one bad one. Membership of record is
    # untouched: the row keeps its place in `names` and `evaluated`, so the
    # reconciler still grades it. Only the client's grid is short.
    cards_n = sum(1 for r in admitted if r.get("card"))
    card_complete = display_by is not None and cards_n > 0

    bases = sorted({r["price_basis"] for r in rows})
    return {
        "schema": SCHEMA,
        "as_of": session,
        "built_at": built_at.isoformat().replace("+00:00", "Z"),
        "lane": LANE,
        "provisional": True,
        "authority_tier": "display",
        "scoring": {
            "board_definition": us_board_rank.BOARD_DEFINITION,
            "weights": dict(us_board_rank.SCORE_WEIGHTS),
            "legs_included": list(CLOSE_DERIVED_LEGS),
            "legs_omitted": dict(OMITTED_LEGS),
            "weight_covered": WEIGHT_COVERED,
            "weight_total": sum(us_board_rank.SCORE_WEIGHTS.values()),
            # Stated so no consumer has to infer it from the two numbers above.
            "renormalised": False,
            "zero_score_authority": list(us_board_rank.ZERO_SCORE_AUTHORITY),
        },
        "price_basis": {
            # Plural because the population is genuinely mixed — see build_board.
            "bases": bases,
            "mixed": len(bases) > 1,
            "per_name_field": "price_basis",
        },
        # The seam W-L1b's spec §7 leaves open. `rel == 'ahead'` is only legal
        # once a consumer RENDERS these rows as the cards; a payload that cannot
        # populate a card must not license a stamp claiming the cards are
        # tonight's. Flag it in the data rather than in a comment nobody reads.
        "consumer_contract": {
            "card_complete": card_complete,
            "card_fields": list(CARD_FIELDS),
            "card_required": list(CARD_REQUIRED),
            "cards_n": cards_n,
            # Disclosed, not silent: the count of admitted names the client will
            # NOT show because a required display fact was missing.
            "cards_dropped_n": len(admitted) - cards_n,
            "row_fields": sorted(rows[0]) if rows else [],
        },
        "names": admitted,
        "evaluated": rows,
        "meta": {
            "universe_n": universe_n if universe_n is not None else len(verdicts),
            "evaluated_n": len(rows),
            "admitted_n": len(admitted),
            "skipped": counts,
        },
    }
