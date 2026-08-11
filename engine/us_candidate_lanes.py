"""US candidate-pool lanes — a LOSSLESS, DISPLAY-TIER partition of the eligible pool.

Operator commission 2026-08-11: *refused / below-cutoff candidates must stay visible
in a lower pool and be able to graduate to the real list when their scoring improves.*

WHAT THIS FIXES.  The US board publishes only its ``buy[]`` lane.  Counted on the
committed 2026-08-07 board (``site/factordata/us_standouts.json`` as of origin/main
``8c2d152``): ``eligible`` is **144** and ``buy`` holds **78** rows, so **66
cascade-eligible names get no published row at all** — ``scripts/build_stock_library.py``
discloses them as a single integer (``wide["eligible"]``) and the concentration stat's
``overflow_count``.  The 66 decompose as **55 sector-cap overflow** (``overflow_count``)
+ **6 earnings-blackout suppressions** (``earnings_blackout_note.tickers``: UAMY, ASTS,
LITE, SVM, CRC, ONON) + **5** across the dual-class dedup and the sector-integrity
backstop.  A name that was displaced by the per-sector soft cap is, from the artifact's
point of view, indistinguishable from a name the gate never saw.  The CN board ships the
fix already:
``engine/china_board_rank.py::_partition`` places EVERY eligible row into one of four
lanes, each row carrying ``lane``, ``lane_reasons`` and ``display_rank`` (real counts on
the 2026-08-10 CN board: eligible 180 = 24 + 93 + 41 + 22).  This module ports that
SHAPE — not CN's A-share specifics — to the US vocabulary.

ZERO AUTHORITY, AND THE FENCE IS A FILE BOUNDARY.  This module is DISPLAY TIER.  It
changes no ``buy[]`` membership, no ``buy[]`` ordering, no admission gate, no score, no
rank and no size.  It reads verdicts and rows that a producer already computed tonight
and re-describes them; it originates nothing (glass-box law, A7).  It lives in its own
file precisely so that fence is greppable and testable: this module imports FROM
``us_board_rank`` / ``prophet_bridge``, and **nothing on the authority path imports it**
— ``tests/test_us_candidate_lanes.py::TestNoAuthorityLeak`` pins that as a static token
sweep, an import-closure walk and a behavioural invariance check on
``prophet_bridge.select_candidates``.  Folding this into ``us_board_rank`` would make
that fence unstateable, which is the whole reason it is not folded in.

Graduation is **not** a new promotion rule.  A name graduates by clearing the EXISTING
gates on a later night; this module only makes the trajectory visible
(``days_in_pool`` / ``score_delta_5d`` / ``lane_transitions``).  Nothing here auto-
promotes anything (``DNR:KILL-CHATTER-PROMOTION``), and the lower tier is display-only
(``DNR:KILL-PRIMED-DIRECTIONAL-GATE``).

--------------------------------------------------------------------------------------
WHY ``prophet.score`` IS NULL OFF THE BUY LANE (read before "fixing" it)
--------------------------------------------------------------------------------------
``us_board_rank.score_rows`` computes its ``edge`` leg from
``alpha_percentiles(pool)`` — a CROSS-SECTIONAL percentile over the pool it is handed.
So there are only two ways to score the 66 off-board names, and both are wrong:

* score them as their own pool → their ``edge`` legs are percentiles of a DIFFERENT
  population than the published ``buy[]`` scores.  Two rulers wearing one name; every
  cross-lane and cross-night comparison the operator asked for silently breaks.
* score them together with ``buy[]`` → every published ``buy[]`` row's ``edge``
  percentile moves, which moves its score, which moves the board ORDER.  Forbidden.

So the off-board rows carry ``prophet: null`` with ``prophet_score_basis: null``, and
the store's existing disclosure ("legs are null off the board",
``data/us_prophet_rank/README.md``) is inherited rather than contradicted.  What they
DO carry is :data:`pool_rank` — their position in the board's OWN pre-cap blend order
(``signal_gate.blend_sorted``), which is defined for all 144 names, is membership-blind,
is already computed tonight, and is therefore the one trajectory key that IS comparable
across the whole pool and across nights.

--------------------------------------------------------------------------------------
DECLINED-COUNT BASIS (rider debt, resolved here by naming the canonical one)
--------------------------------------------------------------------------------------
``prophet_bridge.refusal_receipts`` is called from two sites that see different facts:

* ``scripts/build_site.py`` knows the admission gate but NOT tonight's origination run
  (``build_site`` runs before ``build_prophet``, and ``render.yml`` never runs
  ``build_prophet`` at all), so it reports ``declined`` 25 / ``open_now`` 48.
* ``scripts/build_prophet.py`` passes ``originated_tickers`` and reports 56 / 23.

**build_prophet's originated-aware basis is CANONICAL.**  A row that cleared every gate
and got no plan is a decline, and only build_prophet can see that.  This module is
stamped from the build_site-side lane (``build_stock_library``), so its own tally is the
gate-only basis and says so in the block: ``declined_basis == "build_site_gate_only"``
with a pointer to the canonical figure.  It reports the honest number it can compute and
labels which one it is, rather than printing the smaller one unlabelled.

--------------------------------------------------------------------------------------
WHY THE STORE DOES NOT CARRY ``originated``
--------------------------------------------------------------------------------------
The dated pool store is the EXISTING ``data/us_prophet_rank/candidates`` — see
:func:`store_columns`.  It is stamped by ``build_stock_library`` at the end of its
nightly run, i.e. before ``build_prophet`` has originated anything, and the store's
charter forbids retroactive backfill AND forbids shipping a column that can never be
populated ("never leave schema that lies", README §Named debts).  Origination is
``build_prophet``'s fact and already lives in its own artifact and ledger; a study joins
on ``(stamp_date, ticker)``.  What IS knowable at stamp time — whether a name already
holds an OPEN plan, because open plans persist across nights — is stamped as
``pool_open_plan``.
"""
from __future__ import annotations

import json
import logging
from collections import Counter
from copy import deepcopy
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

log = logging.getLogger(__name__)

#: Stamped on the block and on every store row, exactly the way ``board_definition``
#: and ``selection_era`` are: a reader must be able to tell WHICH partition rule
#: produced a row without trusting whatever the constants say at read time.
POOL_DEFINITION = "us_candidate_pool_v1"

# --------------------------------------------------------------------------- #
# lane taxonomy — CN's four-lane SHAPE, US vocabulary
# --------------------------------------------------------------------------- #

#: Everything clear: on the buy lane, cleared every admission gate, and flagged by the
#: board's own ``featured`` rule (cap 12, sector cap 4).
LANE_FEATURED = "featured"
#: Actionable, but not on the top shelf — short of a featured requirement, or displaced
#: by a cap (the per-sector soft cap, the buy slice, the dual-class dedup).  This is the
#: lane the 55 sector-cap overflow names land in, and CN's ``sector_cap`` reason lands
#: in the same place.
LANE_MORE_ACTIONABLE = "more_actionable"
#: The signal is there; the entry is not available to us tonight — it ran too far, or we
#: are standing aside.  CN's ``extended`` / ``non_entry_stage`` / unfillable cohort.
LANE_LATE_OR_UNFILLABLE = "late_or_unfillable"
#: Still developing, or not placeable: the entry has not arrived, conviction is low, the
#: cascade graded it below the actionable set, tone is refused, or we could not read
#: enough about it to place it.  CN's ``forming``.  Also the FAIL-CLOSED lane — an
#: eligible name this module cannot account for lands here with a stated reason rather
#: than vanishing.
LANE_FORMING = "forming"

LANE_ORDER = (LANE_FEATURED, LANE_MORE_ACTIONABLE, LANE_LATE_OR_UNFILLABLE, LANE_FORMING)

#: Refusal codes (``prophet_bridge.REFUSAL_ORDER`` vocabulary — ONE vocabulary through
#: the whole flow, never a second one coined here) that mean "the entry is gone or we
#: are standing aside", as opposed to "it has not arrived yet".
LATE_OR_UNFILLABLE_CODES = frozenset({"ran_too_far", "stood_down"})

#: Codes that are NOT refusals.  ``prophet_bridge.refusal_receipts`` states this law in
#: its own arithmetic ("AN OPEN PLAN IS NOT A REFUSAL"): both of these rows cleared every
#: gate.  They are carried in ``lane_reasons`` but never move a row down a lane.
NON_REFUSING_CODES = frozenset({"already_open", "plan_not_built"})

#: The positive reason list a featured row carries, mirroring CN's featured lane so the
#: two boards read the same way.
FEATURED_REASONS = (
    "cleared_admission",
    "board_featured",
)

#: Reasons a CASCADE-ELIGIBLE name never reached ``buy[]``, derived at the exact point in
#: ``scripts/build_stock_library.py`` where the name drops out.  Every one of these is a
#: DISPLAY cap or a data-integrity drop — none of them is an admission gate, which is why
#: their rows are honestly describable as "actionable, displaced" rather than "refused".
OFF_BOARD_REASONS = {
    # the per-sector soft cap (_WIDE_PER_SECTOR) — 55 names on the 2026-08-07 board
    "sector_cap_overflow": LANE_MORE_ACTIONABLE,
    # engine.setups.norm_company kept the higher-ranked share class (GOOG/GOOGL)
    "dual_class_duplicate": LANE_MORE_ACTIONABLE,
    # beyond the buy-lane display slice
    "buy_slice_cap": LANE_MORE_ACTIONABLE,
    # W1.5 earnings-blackout hygiene gate removed it from `buyable` for tonight.  LATE,
    # not FORMING: the setup is intact and the name is blocked *by a dated event*, which
    # is the same "signal there, entry not available to us tonight" shape as `extended`.
    # Filing it under `forming` would say the setup had not developed, which is false —
    # and the SAME artifact names these tickers in `earnings_blackout_note`, so the two
    # blocks would have contradicted each other (6 names on the 2026-08-07 board:
    # UAMY, ASTS, LITE, SVM, CRC, ONON).
    "event_blackout": LANE_LATE_OR_UNFILLABLE,
    # the sector-integrity backstop dropped the row (corrupt GICS label)
    "sector_label_unreadable": LANE_FORMING,
    # FAIL-CLOSED: eligible, and this module could not account for it.  The row still
    # ships — a pool that silently loses a name is the defect this module exists to fix.
    # A non-zero count of these raises a line-start ``::warning`` from the builder: an
    # uninstrumented drop site is a REAL defect and must be loud, not quietly absorbed
    # into a bucket that looks like a lane.
    "off_board_reason_unknown": LANE_FORMING,
}

#: Reason for a buy-lane row whose pending confirmation window lapsed.  The row still
#: ships inside ``buy[]`` (``_expire_pending_buys`` re-tags it ``lane="watch"`` and keeps
#: it there for the template's Watch sub-heading), so the pool must see it as blocked
#: rather than inherit whatever the pre-expiry pass thought of it.
PENDING_EXPIRED = "pending_expired"

#: Reason for a buy-lane row that cleared every admission gate and carries no other
#: explanation for sitting off the top shelf.
CLEARED_ADMISSION = "cleared_admission"

# --------------------------------------------------------------------------- #
# the FOURTH reason vocabulary — the board's own featured shortfalls
# --------------------------------------------------------------------------- #
#
# `pool_lane_reasons` / `pool_headline_reason` ship to a PUBLIC parquet, so every value
# they can take must be declared somewhere a rename has to go past.  Three of the four
# sources were already declared (:data:`OFF_BOARD_REASONS`, this module's own literals,
# and ``prophet_bridge.REFUSAL_ORDER``).  The fourth was not, and it is the biggest:
# ``us_board_rank.featured_shortfalls`` + the featured pass in ``score_rows`` supply the
# reasons for every cleared-but-not-featured row — 41 of 144 headline reasons on the
# 2026-08-07 board, through codes like ``alpha_below_floor`` and ``featured_cap`` that
# appeared in no declared set at all.  An upstream rename must RED, not silently split a
# cohort across two spellings of the same fact.

#: Fixed literals emitted by ``us_board_rank.featured_shortfalls`` and by the featured
#: pass inside ``score_rows``.  Pinned against those functions' own source by
#: ``TestReasonVocabulary`` so a rename cannot land quietly.
FEATURED_SHORTFALL_CODES = frozenset({
    "ticks_unknown", "ticks_stale", "provisional", "antichase_blocked", "extended",
    "alpha_unknown", "alpha_below_floor", "earnings_blackout",
    # stamped by score_rows' featured pass, not by featured_shortfalls
    "featured_cap", "sector_cap", "not_evaluated",
})

#: The three PARAMETRIZED families — ``featured_shortfalls`` interpolates a status, a
#: stage or a tier into the code.  Declared as prefixes AND bounded by their producing
#: enum (see ``TestReasonVocabulary``), so a new stage word is caught rather than waved
#: through by a permissive prefix match.
FEATURED_SHORTFALL_PREFIXES = ("entry_status_", "stage_", "tier_")


def declared_reasons() -> frozenset[str]:
    """Every fixed reason literal this module can emit, across all four vocabularies."""
    from engine.prophet_bridge import REFUSAL_ORDER  # noqa: PLC0415

    return frozenset({
        *OFF_BOARD_REASONS,
        *FEATURED_SHORTFALL_CODES,
        *REFUSAL_ORDER,
        *FEATURED_REASONS,
        CLEARED_ADMISSION,
        PENDING_EXPIRED,
    })


def is_declared_reason(code: Any) -> bool:
    """True when ``code`` is a declared literal or a member of a declared family."""
    text = _text(code)
    if not text:
        return False
    if text in declared_reasons():
        return True
    return any(text.startswith(prefix) for prefix in FEATURED_SHORTFALL_PREFIXES)

#: ``score_delta_5d`` is measured over the ticker's five most recent PRIOR STAMPS in the
#: store, not over five calendar sessions: the store stamps once per nightly, so a missed
#: night shifts the reference.  Named in the block so a reader never has to guess.
SCORE_DELTA_BASIS = "5_prior_stamps"

#: The store columns this module contributes.  Every one is ``pool_``-prefixed so it can
#: never be confused with the store's existing ``lane`` column, which is the ARTIFACT
#: display lane (buy / watch / leaders / laggards / not_on_board) and means something
#: else entirely.
STORE_COLUMNS = (
    "pool_definition",
    "pool_lane",
    "pool_lane_reasons",
    "pool_headline_reason",
    "pool_rank",
    "pool_display_rank",
    "pool_in_buy_lane",
    "pool_admission_class",
    "pool_open_plan",
)

#: Columns :func:`load_pool_history` projects out of the candidates store.  Kept minimal
#: on purpose: the store is ~240 columns wide and this read happens on the render path.
HISTORY_COLUMNS = (
    "stamp_date", "ticker", "pool_lane", "prophet_score", "pool_rank",
)


# --------------------------------------------------------------------------- #
# small helpers (local, so this module stays importable without pandas)
# --------------------------------------------------------------------------- #

def _text(value: Any) -> str | None:
    """Trimmed text, or None.

    NaN-AWARE, and that is load-bearing rather than defensive.  ``load_pool_history``
    reads the candidates store through ``load_candidates(columns=...)``, whose documented
    fallback for a part that predates a requested column is a full read reindexed onto
    the requested columns — which materialises the absent column as **float NaN**, not
    None.  A plain ``str(value).strip()`` turns that into the string ``"nan"``, which is
    truthy: measured against the real committed store before this guard, every one of
    4,474 tickers came back with four nights of "history" on a store that has never
    carried a pool lane at all.  A missing column must read as no history.
    """
    if value is None:
        return None
    if isinstance(value, float) and value != value:      # float/np.float64 NaN
        return None
    text = str(value).strip()
    # Belt for the non-float pandas nulls (pd.NA / NaT), which stringify rather than
    # comparing unequal to themselves.  No lane name, reason code, ticker or sector this
    # helper ever sees is one of these words.
    if not text or text.lower() in {"nan", "none", "nat", "<na>"}:
        return None
    return text


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number and number not in (float("inf"), float("-inf")) else None


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def join_reasons(reasons: Iterable[str]) -> str | None:
    """``|``-joined reason codes, ORDER PRESERVED (headline first).

    Deliberately NOT ``us_context_vector._ids``, which sorts: the first code is the
    headline reason and sorting would silently re-headline every row.
    """
    parts = [str(r).strip() for r in (reasons or ()) if str(r).strip()]
    return "|".join(parts) or None


# --------------------------------------------------------------------------- #
# refusal codes — read through prophet_bridge, never re-derived
# --------------------------------------------------------------------------- #

def _refusal_codes_for(row: Mapping[str, Any]) -> list[str]:
    """Every admission gate this buy-lane row fails, in ``REFUSAL_ORDER`` order.

    Read through ``prophet_bridge.refusal_codes`` so the pool, the "why not" shelf and
    the intake gate can never disagree about why a name is not being acted on.  Fail-soft:
    an unreadable bridge costs the reason detail, never the row.
    """
    try:
        from engine.prophet_bridge import refusal_codes  # noqa: PLC0415

        return list(refusal_codes(row))
    except Exception as exc:  # noqa: BLE001 — display tier is never fatal
        log.warning("us_candidate_lanes: refusal codes unavailable (%s)", exc)
        return []


def _admission_class_for(row: Mapping[str, Any]) -> str | None:
    try:
        from engine.prophet_bridge import admission_class, entry_status  # noqa: PLC0415

        return admission_class(entry_status(row))
    except Exception as exc:  # noqa: BLE001
        log.warning("us_candidate_lanes: admission class unavailable (%s)", exc)
        return None


def load_open_plan_tickers(site_dir: Any) -> list[str]:
    """Tickers holding an OPEN plan, read from the published prophet index.

    This is LAST NIGHT'S index when called from the nightly builder, and that is safe for
    the same reason ``build_site`` states at its own call site: open plans persist across
    nights, so "already has a plan running" does not go stale the way a refusal REASON
    would.  Fail-soft to ``[]`` — an unreadable index costs the ``already_open`` reason
    and nothing else.
    """
    try:
        path = Path(site_dir) / "prophet" / "index.json"
        if not path.exists():
            return []
        doc = json.loads(path.read_text())
        return [str(p.get("asset")).strip().upper()
                for p in (doc.get("plans") or [])
                if isinstance(p, Mapping) and p.get("asset") and not p.get("closed")]
    except Exception as exc:  # noqa: BLE001
        log.warning("us_candidate_lanes: prophet index unreadable (%s)", exc)
        return []


# --------------------------------------------------------------------------- #
# the partition
# --------------------------------------------------------------------------- #

def _featured_shortfalls_of(row: Mapping[str, Any]) -> list[str]:
    """Why the board did not feature this row, read off its OWN published field.

    ``us_board_rank.score_rows`` pops its internal ``_featured_shortfalls`` and re-stamps
    the surviving reason list as ``featured_blocked_by`` on every non-featured row (and
    pops it back off the featured ones).  Reading that published field means the pool's
    "why not on the top shelf" answer is literally the board's own, with no second
    derivation to drift — measured on the 2026-08-07 board: 19 ``featured_cap``,
    18 ``alpha_below_floor``, 12 featured (field absent), and a long tail.
    """
    values = row.get("featured_blocked_by")
    if isinstance(values, str):
        return [values]
    if isinstance(values, Sequence):
        return [str(v).strip() for v in values if str(v).strip()]
    return []


def _classify_buy_row(
    row: Mapping[str, Any],
    *,
    open_tickers: frozenset[str],
    shortfalls: Sequence[str] | None = None,
) -> tuple[str, list[str]]:
    """``(lane, reasons)`` for a row that IS on ``buy[]``.

    ``shortfalls`` overrides the row's own ``featured_blocked_by`` (tests only).
    """
    codes = _refusal_codes_for(row)
    ticker = str(row.get("ticker") or "").strip().upper()

    refusing = [c for c in codes if c not in NON_REFUSING_CODES]
    informational: list[str] = [c for c in codes if c in NON_REFUSING_CODES]

    # A row whose pending confirmation expired is BLOCKED, whatever the gate codes say.
    # `_expire_pending_buys` demotes it to lane="watch" INSIDE buy[] and none of the
    # admission gates read that flag, so without this the pool would keep calling an
    # expired row featured — which is exactly what it did before the partition was moved
    # below that pass (BIDU and UEC on the 2026-08-07 board).
    if row.get("pending_expired") is True:
        return LANE_LATE_OR_UNFILLABLE, [PENDING_EXPIRED, *refusing, *informational]
    if not refusing and ticker and ticker in open_tickers \
            and "already_open" not in informational:
        informational.append("already_open")

    if refusing:
        if any(code in LATE_OR_UNFILLABLE_CODES for code in refusing):
            lane = LANE_LATE_OR_UNFILLABLE
        else:
            lane = LANE_FORMING
        return lane, [*refusing, *informational]

    # Cleared every admission gate.
    if row.get("featured") is True:
        return LANE_FEATURED, [*FEATURED_REASONS, *informational]
    blocked = list(shortfalls) if shortfalls is not None else _featured_shortfalls_of(row)
    return LANE_MORE_ACTIONABLE, [*(blocked or [CLEARED_ADMISSION]), *informational]


def _pool_row(
    ticker: str,
    *,
    lane: str,
    reasons: Sequence[str],
    pool_rank: int | None,
    in_buy_lane: bool,
    board_row: Mapping[str, Any] | None,
    meta_row: Mapping[str, Any] | None,
    selection_era: str | None,
) -> dict[str, Any]:
    """One published pool row.  Pure — never aliases or mutates the source row."""
    source = _mapping(board_row) or _mapping(meta_row)
    prophet = _mapping(_mapping(board_row).get("prophet"))
    signal = _mapping(source.get("signal"))
    reason_list = [str(r) for r in reasons] or ["off_board_reason_unknown"]

    row: dict[str, Any] = {
        "ticker": ticker,
        "name": _text(source.get("name")) or ticker,
        "sector": _text(source.get("sector")),
        "lane": lane,
        "lane_reasons": reason_list,
        "headline_reason": reason_list[0],
        "pool_rank": pool_rank,
        "in_buy_lane": bool(in_buy_lane),
        "admission_class": _admission_class_for(source) if in_buy_lane else None,
        "align_tier": _text(source.get("align_tier")),
        "tier_cascade": _text(signal.get("tier_cascade")),
        "stage": _text(source.get("stage")),
        "selection_era": selection_era,
        # The full prophet block is deliberately NOT duplicated per row (its
        # ``zero_score_authority`` list would repeat once per buy row); the score, its
        # legs and the alpha percentile are what a graduation reader needs.
        "prophet": ({
            "score": _finite(prophet.get("score")),
            "components": deepcopy(dict(_mapping(prophet.get("components")))),
            "points": deepcopy(dict(_mapping(prophet.get("points")))),
            "alpha_percentile": _finite(prophet.get("alpha_percentile")),
        } if prophet else None),
        # See the module docstring: a score computed on any pool other than the published
        # buy lane is a second ruler, so off-board rows carry no score and say so.
        "prophet_score_basis": "buy_lane_pool" if prophet else None,
    }
    return row


def build_candidate_pool(
    *,
    as_of: str | None,
    board_definition: str,
    selection_era: str | None,
    eligible_order: Sequence[str],
    buy_rows: Sequence[Mapping[str, Any]],
    off_board_reasons: Mapping[str, Sequence[str]] | None = None,
    meta_rows: Mapping[str, Mapping[str, Any]] | None = None,
    shortfalls_by_ticker: Mapping[str, Sequence[str]] | None = None,
    open_tickers: Iterable[str] = (),
    display_caps: Mapping[str, Mapping[str, Any]] | None = None,
    history: Mapping[str, Mapping[str, Any]] | None = None,
    history_meta: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """The lossless four-lane partition of tonight's cascade-eligible pool.

    ``eligible_order`` is the board's OWN pre-cap blend order
    (``signal_gate.blend_sorted`` over ``_cascade_elig``) — it defines both the pool
    membership and ``pool_rank``, so this function cannot invent or lose a name.

    PURE.  Nothing in ``buy_rows`` or ``meta_rows`` is mutated or aliased into the
    result; the caller's board rows come back byte-identical.  That is the property
    ``tests/test_us_candidate_lanes.py::TestBuyLaneUntouched`` mutation-checks.

    LOSSLESS INVARIANT (test-pinned, exactly as CN's is):
    ``sum(lane_counts.values()) == len(rows) == eligible``.
    """
    off_board_reasons = {str(k).strip().upper(): list(v or ())
                         for k, v in (off_board_reasons or {}).items()}
    meta_rows = {str(k).strip().upper(): v for k, v in (meta_rows or {}).items()}
    shortfalls_by_ticker = {str(k).strip().upper(): list(v or ())
                            for k, v in (shortfalls_by_ticker or {}).items()}
    open_set = frozenset(str(t).strip().upper() for t in (open_tickers or ()) if str(t).strip())
    history = {str(k).strip().upper(): v for k, v in (history or {}).items()}

    buy_by_ticker: dict[str, Mapping[str, Any]] = {}
    buy_order: list[str] = []
    for row in buy_rows or ():
        if not isinstance(row, Mapping):
            continue
        ticker = str(row.get("ticker") or "").strip().upper()
        if not ticker or ticker in buy_by_ticker:
            continue
        buy_by_ticker[ticker] = row
        buy_order.append(ticker)

    # Pool membership is the eligible set, in blend order, plus — fail-closed — any
    # buy-lane name the eligible order somehow does not carry.  A published row that the
    # pool cannot see is exactly the hole this module closes, so it is never dropped.
    ordered: list[str] = []
    seen: set[str] = set()
    for ticker in eligible_order or ():
        key = str(ticker or "").strip().upper()
        if key and key not in seen:
            seen.add(key)
            ordered.append(key)
    orphan_buys = [t for t in buy_order if t not in seen]
    for ticker in orphan_buys:
        seen.add(ticker)
        ordered.append(ticker)

    rank_by_ticker = {ticker: index for index, ticker in enumerate(ordered, start=1)}

    rows: list[dict[str, Any]] = []
    for ticker in ordered:
        board_row = buy_by_ticker.get(ticker)
        if board_row is not None:
            lane, reasons = _classify_buy_row(
                board_row,
                open_tickers=open_set,
                shortfalls=shortfalls_by_ticker.get(ticker),
            )
            in_buy_lane = True
        else:
            reasons = off_board_reasons.get(ticker) or ["off_board_reason_unknown"]
            lane = OFF_BOARD_REASONS.get(str(reasons[0]), LANE_FORMING)
            in_buy_lane = False
        rows.append(_pool_row(
            ticker,
            lane=lane,
            reasons=reasons,
            pool_rank=rank_by_ticker.get(ticker),
            in_buy_lane=in_buy_lane,
            board_row=board_row,
            meta_row=meta_rows.get(ticker),
            selection_era=selection_era,
        ))

    # display_rank within each lane, by the pool's own order (pool_rank asc, ticker) —
    # the same shape CN's _partition stamps.
    for lane in LANE_ORDER:
        members = sorted(
            (r for r in rows if r["lane"] == lane),
            key=lambda r: (r["pool_rank"] if r["pool_rank"] is not None else 10 ** 9,
                           r["ticker"]),
        )
        for display_rank, row in enumerate(members, start=1):
            row["display_rank"] = display_rank

    # Graduation annotations — display-only, attached ONLY where history exists.  A
    # missing history is disclosed by `history.available`, never faked as "night 1".
    for row in rows:
        record = _mapping(history.get(row["ticker"]))
        if record:
            row["graduation"] = dict(record)

    counts = Counter(row["lane"] for row in rows)
    lane_counts = {lane: int(counts.get(lane, 0)) for lane in LANE_ORDER}
    in_buy = sum(1 for row in rows if row["in_buy_lane"])

    # THE FAIL-CLOSED BUCKET MUST BE LOUD.  `off_board_reason_unknown` is not a lane, it
    # is an UNINSTRUMENTED DROP SITE — a real defect that reads like data.  Surfaced on
    # the block so the builder can raise a line-start ::warning, and named per ticker so
    # the next drop site is found by reading the annotation rather than by re-deriving
    # the whole funnel.  (The earnings-blackout gate hid here for exactly one review.)
    unknown = sorted(r["ticker"] for r in rows
                     if r["headline_reason"] == "off_board_reason_unknown")
    # Same treatment for a reason word no declared vocabulary knows: the column ships to
    # a public parquet, so an upstream rename must be visible, not silently absorbed.
    undeclared = sorted({str(code) for r in rows for code in r["lane_reasons"]
                         if not is_declared_reason(code)})

    # TWO NUMBERS THAT CAN HONESTLY DISAGREE, NAMED RATHER THAN RECONCILED.
    # The board's `featured` flag is a DISPLAY shelf inside buy[]; this module's
    # `featured` lane additionally requires the row to clear the PLAN INTAKE gate, which
    # is a different question and is allowed a different answer.  Measured on the
    # 2026-08-07 board: 12 board-featured rows, of which AEIS is `conviction_low`
    # (band == 'low', status 'bounce_wait') — the intake would not plan it, so the pool
    # places it in `forming` and lists it here.  Silently printing 11 next to the board's
    # 12 is the failure mode this block exists to prevent.
    board_featured = sorted(
        str(row.get("ticker") or "").strip().upper()
        for row in (buy_rows or ())
        if isinstance(row, Mapping) and row.get("featured") is True
    )
    pool_featured = {row["ticker"] for row in rows if row["lane"] == LANE_FEATURED}
    lane_by_ticker = {row["ticker"]: row["lane"] for row in rows}
    divergence = [{"ticker": t, "pool_lane": lane_by_ticker.get(t)}
                  for t in board_featured if t not in pool_featured]

    block: dict[str, Any] = {
        "pool_definition": POOL_DEFINITION,
        "as_of": as_of,
        "board_definition": board_definition,
        "selection_era": selection_era,
        # The lossless invariant, stated in the artifact so a reader can check it
        # without recomputing: eligible == row count == sum(lane_counts).
        "eligible": len(rows),
        "lane_order": list(LANE_ORDER),
        "lane_counts": lane_counts,
        "in_buy_lane": in_buy,
        "off_buy_lane": len(rows) - in_buy,
        # See the divergence note above: the board's shelf flag and this module's
        # featured LANE answer different questions and are reported separately.
        "board_featured_count": len(board_featured),
        "featured_divergence": divergence,
        # Fail-closed disclosure — both of these should be empty on a healthy board.
        "unknown_reason_count": len(unknown),
        "unknown_reason_tickers": unknown,
        "undeclared_reasons": undeclared,
        # Every DISPLAY cap that displaced a name, with what it displaced.  The pool
        # block itself is never truncated — that is the point — so these describe the
        # OTHER lanes' caps, not this one's.
        "display_caps": {k: dict(v) for k, v in (display_caps or {}).items()},
        # See the module docstring: build_prophet's originated-aware receipts are the
        # canonical decline count; this lane can only see the gate.
        "declined_basis": "build_site_gate_only",
        "declined_basis_note": (
            "Counts here are the admission-gate basis this lane can compute. The "
            "canonical declined count is build_prophet's originated-aware "
            "refusal_receipts (site/prophet/index.json intake.receipts), which also "
            "sees which cleared rows became plans tonight."
        ),
        "history": {
            "available": bool((history_meta or {}).get("available")),
            "nights": int((history_meta or {}).get("nights") or 0),
            "months": list((history_meta or {}).get("months") or ()),
            "score_delta_basis": SCORE_DELTA_BASIS,
        },
        "rows": rows,
    }
    if orphan_buys:
        # Fail-closed disclosure: a published buy row the eligible order did not carry is
        # a real inconsistency upstream, and the block says so rather than hiding it.
        block["orphan_buy_rows"] = list(orphan_buys)
    return block


# --------------------------------------------------------------------------- #
# store projection
# --------------------------------------------------------------------------- #

def store_columns(
    block: Mapping[str, Any] | None,
    *,
    open_tickers: Iterable[str] = (),
) -> dict[str, dict[str, Any]]:
    """``{ticker: {column: value}}`` for the candidates store's ``pool_*`` columns.

    THE STORE IS ``data/us_prophet_rank/candidates`` — extended, not forked.  It already
    stamps exactly this grain (one row per analyzed US universe name per night, keyed
    ``(stamp_date, ticker, board_definition)``, carrying ``prophet_score``,
    ``selection_era`` and the display ``lane``), its README charters schema-union append
    with forward-only self-healing for a new column, and the nightly already commits it.
    A parallel store would have duplicated the key, the lane gate, the keep-first fence
    and the monthly-parts layout for nine columns.

    Names outside tonight's eligible pool get NO entry here, so their ``pool_*`` columns
    stay null — "not measured for this name tonight", the store's own disclosure idiom,
    never "false".
    """
    open_set = frozenset(str(t).strip().upper() for t in (open_tickers or ()) if str(t).strip())
    out: dict[str, dict[str, Any]] = {}
    for row in (_mapping(block).get("rows") or ()):
        if not isinstance(row, Mapping):
            continue
        ticker = str(row.get("ticker") or "").strip().upper()
        if not ticker:
            continue
        out[ticker] = {
            "pool_definition": _text(_mapping(block).get("pool_definition")),
            "pool_lane": _text(row.get("lane")),
            "pool_lane_reasons": join_reasons(row.get("lane_reasons") or ()),
            "pool_headline_reason": _text(row.get("headline_reason")),
            "pool_rank": _finite(row.get("pool_rank")),
            "pool_display_rank": _finite(row.get("display_rank")),
            "pool_in_buy_lane": bool(row.get("in_buy_lane")),
            "pool_admission_class": _text(row.get("admission_class")),
            "pool_open_plan": ticker in open_set,
        }
    return out


# --------------------------------------------------------------------------- #
# graduation — READ-ONLY derivation from the dated store
# --------------------------------------------------------------------------- #

def _months_window(as_of: str | None, back: int = 1) -> list[str]:
    """``["YYYY-MM", ...]`` covering ``as_of`` and ``back`` earlier months."""
    text = _text(as_of) or ""
    try:
        year, month = int(text[0:4]), int(text[5:7])
    except (ValueError, IndexError):
        return []
    months: list[str] = []
    for _ in range(max(0, back) + 1):
        months.append(f"{year:04d}-{month:02d}")
        month -= 1
        if month == 0:
            month, year = 12, year - 1
    return list(reversed(months))


def load_pool_history(
    as_of: str | None,
    *,
    root: Any = None,
    months_back: int = 1,
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    """Prior nights' pool rows, per ticker, oldest first.

    READ-ONLY.  Reads the candidates store through its OWN loader
    (``us_context_vector.load_candidates``, projected to :data:`HISTORY_COLUMNS`) — never
    by globbing parts, per the store's contract.  Rows stamped ON or AFTER ``as_of`` are
    excluded, so tonight's own row (on a re-run) can never become its own history.

    Returns ``(history, meta)``.  Fail-soft: any failure returns ``({}, {"available":
    False, ...})`` and the block discloses that rather than printing a fake "night 1".
    """
    meta: dict[str, Any] = {"available": False, "nights": 0, "months": []}
    months = _months_window(as_of, months_back)
    if not months:
        return {}, meta
    try:
        from engine import us_context_vector as ucv  # noqa: PLC0415

        frame = ucv.load_candidates(root, months=months, columns=list(HISTORY_COLUMNS))
    except Exception as exc:  # noqa: BLE001 — telemetry read is never fatal
        log.warning("us_candidate_lanes: pool history unavailable (%s)", exc)
        return {}, meta
    if frame is None or getattr(frame, "empty", True):
        # An empty store is a SUCCESSFUL read of a store with no prior nights.
        meta.update({"available": True, "nights": 0, "months": months})
        return {}, meta

    cutoff = _text(as_of) or ""
    history: dict[str, list[dict[str, Any]]] = {}
    nights: set[str] = set()
    try:
        records = frame.to_dict("records")
    except Exception as exc:  # noqa: BLE001
        log.warning("us_candidate_lanes: pool history unreadable (%s)", exc)
        return {}, meta
    for record in records:
        lane = _text(record.get("pool_lane"))
        if not lane:
            continue                      # a night stamped before this column existed
        stamp = _text(record.get("stamp_date"))
        ticker = str(record.get("ticker") or "").strip().upper()
        if not stamp or not ticker or (cutoff and stamp >= cutoff):
            continue
        nights.add(stamp)
        history.setdefault(ticker, []).append({
            "stamp_date": stamp,
            "pool_lane": lane,
            "prophet_score": _finite(record.get("prophet_score")),
            "pool_rank": _finite(record.get("pool_rank")),
        })
    for rows in history.values():
        rows.sort(key=lambda r: r["stamp_date"])
    meta.update({"available": True, "nights": len(nights), "months": months,
                 "months_back": max(0, int(months_back)),
                 "oldest_stamp": min(nights) if nights else None})
    return history, meta


def graduation_fields(
    history: Mapping[str, Sequence[Mapping[str, Any]]] | None,
    *,
    tonight_lane_by_ticker: Mapping[str, str],
    tonight_score_by_ticker: Mapping[str, Any] | None = None,
    window_meta: Mapping[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    """Per-ticker graduation annotations derived from the dated store.

    DISPLAY ANNOTATIONS, ZERO AUTHORITY.  Nothing here scores, ranks, gates or sizes; the
    fields exist so a reader can see a name's trajectory through the lower pool.

    * ``days_in_pool`` — distinct prior stamps carrying a pool lane for this ticker, plus
      tonight.  A name in the pool for the first time reads 1.
    * ``score_delta_5d`` — tonight's ``prophet.score`` minus its score five PRIOR STAMPS
      back (:data:`SCORE_DELTA_BASIS`).  Null unless both ends exist, which for now means
      buy-lane rows only: off-board rows carry no score, by construction (module
      docstring).
    * ``lane_transitions`` — how many times the pool lane CHANGED across the ticker's
      history including tonight.  0 means it has never moved lane.
    * ``prev_lane`` — the pool lane at the most recent prior stamp; null on night one.
    * ``first_seen`` — the earliest prior stamp in the loaded window.
    * ``window_truncated`` — TRUE when the ticker's history reaches the OLDEST stamp the
      loaded window contains, i.e. ``days_in_pool`` and ``first_seen`` are FLOOR values
      bounded by how far back we read, not by when the name entered the pool.  Without
      this a name that has been in the pool for four months reads "62 nights" with the
      same confidence as one that genuinely arrived 62 nights ago.  ``window_oldest``
      and ``window_months_back`` name the bound.
    """
    tonight_score_by_ticker = tonight_score_by_ticker or {}
    window_oldest = _text((window_meta or {}).get("oldest_stamp"))
    months_back = (window_meta or {}).get("months_back")
    out: dict[str, dict[str, Any]] = {}
    for ticker, lane_now in (tonight_lane_by_ticker or {}).items():
        key = str(ticker or "").strip().upper()
        if not key:
            continue
        prior = list((history or {}).get(key) or ())
        lanes = [str(r.get("pool_lane")) for r in prior] + [str(lane_now)]
        transitions = sum(1 for a, b in zip(lanes, lanes[1:]) if a != b)
        score_now = _finite(tonight_score_by_ticker.get(key))
        delta = None
        if score_now is not None and len(prior) >= 5:
            reference = _finite(prior[-5].get("prophet_score"))
            if reference is not None:
                delta = round(score_now - reference, 2)
        first_seen = _text(prior[0].get("stamp_date")) if prior else None
        out[key] = {
            "days_in_pool": len(prior) + 1,
            "score_delta_5d": delta,
            "lane_transitions": transitions,
            "prev_lane": (_text(prior[-1].get("pool_lane")) if prior else None),
            "first_seen": first_seen,
            # A name whose earliest row IS the window's earliest row may well have been
            # in the pool before the window opened: the counts are floors, and say so.
            "window_truncated": bool(
                first_seen and window_oldest and first_seen <= window_oldest),
            "window_oldest": window_oldest,
            "window_months_back": months_back,
        }
    return out
