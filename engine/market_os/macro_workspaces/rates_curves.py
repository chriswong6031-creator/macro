"""Pure composer for the US ``rates_curves`` workspace snapshot (beyond-F01
expansion, Chairman-authorized 2026-09-04).

Reads NINETEEN raw, ALREADY-LOADED level series -- all FRED constant-maturity
Treasury (CMT) / policy-corridor parquet series -- and projects them into a
``mastermind.macro_workspace_snapshot.v1`` body:

* ``curve_frames`` -- a dict ``{series_id: rows_or_None}`` where ``rows`` is a
  plain Python list of ``(date, value)`` pairs (or longer tuples -- extra
  elements are ignored, mirrors ``housing.py``'s unconsumed-field negative
  control) read from ``data/fred/<series_id>.parquet``, ascending. Exactly
  NINETEEN series are consumed (column names per ``config.yml`` / the F01 R1B
  hand-off's ``build.py`` loader spec, ``_RATES_FRED_COLUMNS``); any OTHER key
  in ``curve_frames`` is ignored -- this composer never iterates the dict
  blindly, only ever reads the nineteen series ids it names below. All
  nineteen were VERIFIED present as ``data/fred/<SERIES>.parquet`` at
  authoring time (see the hand-off's "what could not be verified without a
  shell" for what a live parquet read would still need to confirm: the exact
  latest row date and row count of each file).

    Nominal CMT curve (percent, investment/bond-equivalent basis):
        DGS3MO=us3m   DGS6MO=us6m   DGS1=us1y   DGS2=us2y   DGS3=us3y
        DGS5=us5y     DGS7=us7y     DGS10=us10y DGS20=us20y DGS30=us30y
    Real yields, TIPS CMT (percent):
        DFII5=us5y_real   DFII10=us10y_real
    Breakevens (percent):
        T10YIE=breakeven_10y   T5YIFR=breakeven_5y5y
    Term premium (percent):
        THREEFYTP10=term_premium_10y  (Kim-Wright 10y)
    Policy corridor (percent):
        EFFR=effr   OBFR=obfr   SOFR=sofr   IORB=iorb

WHY THIS COMPOSER EXISTS (expansion workspace 13, not one of the twelve):
``research/market_intelligence_productization/
MARKET_ONTOLOGY_MACRO_MONETARY_SUITE_ARCHITECTURE_2026-09-04.md`` (the frozen
architecture doc) defines exactly twelve closed macro workspace identities
(``engine.market_os.macro_workspaces.registry.WORKSPACE_IDS``'s original
twelve). Rates & Curves is a Chairman-authorized EXPANSION appended after that
freeze, reaching toward the reference product's fourteen-workspace taxonomy --
it has no architecture section number, no required-composition list, and no
headline-model subsection AT ALL, because the frozen document was never
written with this workspace in mind (see JUDGMENT CALL 1 / the ``_headline``
note below for the consequence this has for ``headline.state_id``).

SEAM DECISION (binding, never re-litigated inline; JUDGMENT CALL 2): this
composer reads FRED Treasury-curve and policy-corridor parquets ONLY. It takes
NO input at all from the ``rates_command`` owner artifact, even though that
artifact already computes a market-implied path, an FOMC dot-plot comparison,
and a yield-momentum read -- ``monetary_policy.py`` already projects exactly
that artifact (its ``board.rate_path_row`` / ``expectations_pressure`` /
``dots`` fields) onto this suite's Monetary Policy page. The REJECTED
alternative: reading ``rates_command`` here too and re-publishing its
yield-momentum leg under a second workspace identity would duplicate an owner
projection another workspace already carries, not add a genuinely new read.
Rates & Curves stays the pure MARKET-CURVE workspace -- built only from the
raw FRED series -- so the two pages can never drift or double-count the same
owner fact.

HEADLINE (read this before "fixing" it -- the consequence of the "no
architecture section" fact above, JUDGMENT CALL 1): unlike ``housing.py`` /
``national_debt.py`` (whose architecture sections DO define a real two-axis
blueprint the composable-core data merely cannot fill, so THEIR headlines are
``COMPUTATION_REFUSED`` -- a data-insufficiency refusal against an EXISTING
blueprint) and like ``monetary_policy.py`` / ``liquidity_central_banks.py``
(whose architecture sections define NO headline-model subsection at all, so
THEIR headlines are honestly ``NOT_APPLICABLE`` -- a design absence, not a
refusal to fill one), Rates & Curves sits in the ``monetary_policy`` case, one
level further removed: there is no architecture section for this workspace to
even NOT define a headline model in. ``headline.state_id`` therefore stays
``null`` with ``status="ABSENT"`` and a null_reason that is a real, closed
vocabulary member describing a design absence, never a fabricated substitute
quadrant this composer invents on its own authority. A future architecture
revision may ratify a genuine two-axis blueprint for this workspace, at which
point this null lawfully flips into a real headline the moment that blueprint
is adopted -- exactly the same lawful-flip relationship ``monetary_policy.py``
already documents for its own design-absence headline. Until then, the real
curve content -- node levels, thirteen-week changes, slopes, inversion status,
curvature, the real/breakeven decomposition, term premium, and the policy
corridor -- is published in full under ``metrics`` / ``drivers`` /
``implications``, never smuggled into a quadrant that has no definition to be
smuggled into. See the ``headline_unavailable`` implication for the
reader-facing version of this note, phrased without the raw closed-vocabulary
token (the leak guard scans every prose field).

SAME-DATE DISCIPLINE (a new house law this composer introduces; JUDGMENT
CALL 3 -- no sibling composer combines two INDEPENDENTLY-CLOCKED series into
one point-in-time read the way a curve spread does): every spread, curvature,
and decomposition read below (2s10s, 3m10y, 5s30s, the butterfly, the
nominal/real/breakeven decomposition, and each policy-corridor spread) is
computed only from a date common to EVERY leg it combines, located as the
LATEST date shared by all of them -- never by pairing each leg's own
separately-latest print under one reported date. When that shared date lags
any single leg's own newest available print by more than the disclosed
``_SAME_DATE_STALENESS_BOUND_DAYS`` tolerance, this composer refuses the read
(``COMPUTATION_REFUSED``) rather than mixing an older print from one leg with
a newer print from another. This generalizes the leg-floor law
``housing.py``'s ``permits_minus_starts_spread`` / ``national_debt.py``'s
``auction_demand_spread_recent_vs_baseline`` already establish (never publish
a composite from fewer legs than it needs) to the EIGHT two- and three-leg
combinations this single-domain workspace carries (JUDGMENT CALL 4 -- the
``_pair_value`` / ``_triple_value`` helpers below are a disclosed
generalization of that sibling pattern, not a new law in spirit).

INVESTMENT-BASIS-ONLY LAW (JUDGMENT CALL 5, disclosed even though it never
actually fires here, because the trap is well-known elsewhere in this estate
-- see ``config.yml``'s own ``DTB3``-vs-``DGS3MO`` inline comment and
``engine/yield_curve.py``'s ``NODES`` convention this composer stays
consistent with, WITHOUT importing that module): every yield node this
composer reads is a constant-maturity, investment (bond-equivalent) basis
FRED series -- internally consistent with every other node here. The
discount-basis Treasury bill rate (FRED ``DTB3``) is a different, structurally
lower-reading series on a different basis and is never one of this
workspace's nineteen inputs, so it can never be mixed with any node published
below.

FRESHNESS (worst-case-age law, JUDGMENT CALL 6 -- mirrors
``national_debt.py``'s DTS cadence derivation exactly): all eighteen CMT/
corridor series are observation-dated and published the next business day, so
the worst-case age of the newest-possible print over a long weekend / holiday
cluster is roughly 4-5 calendar days -- cadence 5d, grace 4d. ``THREEFYTP10``
(the Kim-Wright term premium) publishes with a few days' extra lag beyond a
plain CMT/corridor series -- cadence 9d, grace 5d (JUDGMENT CALL 7, a
composer-derived constant; no other owner in this estate declares a cadence
for this exact series).

REQUIRED / OPTIONAL SPLIT (JUDGMENT CALL 8): fourteen of the nineteen series
are required (``us3m``, ``us6m``, ``us2y``, ``us5y``, ``us10y``, ``us30y``,
``us5y_real``, ``us10y_real``, ``breakeven_10y``, ``breakeven_5y5y``,
``term_premium_10y``, ``effr``, ``sofr``, ``iorb``); the long-tail CMT nodes
(``us1y``, ``us3y``, ``us7y``, ``us20y``) and ``obfr`` are optional -- VERIFIED
by construction: no derived (spread/butterfly/decomposition/corridor) metric
below reads any of these five, so their absence can never degrade
``availability.state`` (optional never degrades, the ``housing.py`` ZORI
precedent).

DERIVED-READ WINDOWS (JUDGMENT CALL 9): the thirteen-week change lookback
uses a 10-calendar-day slack (``_LOOKBACK_SLACK_DAYS``) even though these are
DAILY business-day series that need far less slack than the weekly/monthly
series ``housing.py`` sized this constant for -- a generous, disclosed value
to absorb a holiday cluster sitting exactly on the 91-day boundary, not a
sign this composer expects large gaps in daily CMT data.

INVERSION RUN-LENGTH MINIMUM HISTORY (JUDGMENT CALL 10): the
consecutive-business-day inversion run-length walk (2s10s, 3m10y) refuses
(``INSUFFICIENT_HISTORY``) below ``_MIN_INVERSION_HISTORY_ROWS`` (20)
shared-date historical rows -- a composer-invented floor distinguishing "a
genuinely short run" from "not enough shared history collected yet to tell,"
independent of whether the CURRENT sign itself is known (the sign needs only
the latest shared-date pair; the run length needs real history behind it).

DECOMPOSITION-RESIDUAL TOLERANCE (JUDGMENT CALL 11, the one contradiction
this composer ships): the 10-year nominal yield, 10-year real (TIPS) yield,
and 10-year breakeven inflation rate are three SEPARATELY-interpolated FRED
constant-maturity curves, not three legs of one single calculation -- so
``nominal - (real + breakeven)`` rarely equals exactly zero even on a shared
date, and a small nonzero residual is NORMAL, not a data error. The
``_DECOMPOSITION_RESIDUAL_TOLERANCE_PCT_PTS`` band (0.15 percentage points,
~15bp) is a disclosed composer judgment call sized to that normal
interpolation-noise reality -- never a percentile/z-score this composer has
no historical residual distribution to calibrate honestly (mirrors
``housing.py``'s ``_HOME_PRICE_RENT_FLAT_BAND_PCT`` / ``national_debt.py``'s
flat-band precedent). A residual beyond the band is a genuine, owner-native
disagreement: the market's own curve data disagreeing with its own identity,
not a threshold this composer invents beyond the disclosed band.

CORRIDOR SPREADS IN BASIS POINTS (JUDGMENT CALL 12): ``EFFR-IORB``,
``SOFR-EFFR``, and ``SOFR-IORB`` are published in basis points, never
percent, following this exact estate's own convention for these exact spreads
(``config.yml``'s ``plumbing.sofr_iorb_stress_bp`` / ``repo_spike_bp``), never
rescaled back to percent and never mixed with a percent-denominated level in
one derived read.

REGISTRY DEPENDENCY (JUDGMENT CALL 13, disclosed for the orchestrator, never
silently patched here): this composer emits ``workspace.id="rates_curves"``,
which ``engine.market_os.macro_workspaces.registry.WORKSPACE_IDS`` already
lists (the 2026-09-04 expansion append) -- and, VERIFIED at authoring time by
re-reading the committed schema, ``contracts/market_os/
macro_workspace_snapshot.v1.schema.json``'s own ``$defs.workspaceId`` enum
ALSO already includes ``"rates_curves"`` (widened in the same 2026-09-04
expansion as the schema's ``axis_id`` pattern-widening), so ``contract.
validate()`` accepts a real snapshot from this composer with no companion
schema PR needed. What ``registry.py`` does NOT yet carry is a dedicated
``REGISTRY["rates_curves"]`` entry (title/subtitle/producer/
required_components) -- it falls through to that module's own
``_NOT_BUILT`` default, so ``registry.built_ids()`` will not route
``build_all()`` to this composer until that entry is added. Adding it is out
of scope for this composer (a write-only, two-file mandate); the recommended
entry is returned as part of this hand-off instead of silently added here.

ONE-MONTH-VECTOR PRECEDENT CHOICE (JUDGMENT CALL 14): ``consumer_payments.py``
documents a "refusal outranks warmup" precedence for its own
``one_month_vector.null_reason`` because ITS headline quadrant is genuinely
COMPUTABLE once its pending series populate (so a real "computable but no
prior print yet" case exists there). Rates & Curves has no quadrant at all,
ever -- there is no computable case to distinguish from a data-refused case --
so this composer follows ``monetary_policy.py``'s SIMPLER fixed pattern
instead (both ``nearest_boundary.null_reason`` and ``one_month_vector.
null_reason`` are unconditionally the same design-absence value as
``headline.null_reason``), a disclosed rejection of the more complex
precedent rather than an oversight.

NO rank/gate/size/trade authority. NO LLM-originated facts. Descriptive
ceiling only. Depends only on the standard library (no pandas import here --
the caller supplies plain rows so this module stays testable without
pandas). The composer NEVER reads a wall clock: ``built_at`` is supplied by
the caller, and every staleness/age/lookback/same-date check is a pure
function of ``built_at`` and the given rows, so an identical set of owner
inputs always yields an identical snapshot body.
"""
from __future__ import annotations

import datetime as _dt
from hashlib import sha256
from typing import Any, Mapping, Sequence

METHOD_VERSION = "rates_curves.compose.v1"
DEFINITION_VERSION = "1.0.0"
PRODUCER = "engine.market_os.macro_workspaces.rates_curves"
WORKSPACE_ID = "rates_curves"

# --------------------------------------------------------------------------- #
# series identity (FRED series id -> config.yml column name; mirrors build.py's
# _RATES_FRED_COLUMNS verbatim -- see module docstring's series table).
# --------------------------------------------------------------------------- #
SERIES_US3M, COL_US3M = "DGS3MO", "us3m"
SERIES_US6M, COL_US6M = "DGS6MO", "us6m"
SERIES_US1Y, COL_US1Y = "DGS1", "us1y"
SERIES_US2Y, COL_US2Y = "DGS2", "us2y"
SERIES_US3Y, COL_US3Y = "DGS3", "us3y"
SERIES_US5Y, COL_US5Y = "DGS5", "us5y"
SERIES_US7Y, COL_US7Y = "DGS7", "us7y"
SERIES_US10Y, COL_US10Y = "DGS10", "us10y"
SERIES_US20Y, COL_US20Y = "DGS20", "us20y"
SERIES_US30Y, COL_US30Y = "DGS30", "us30y"
SERIES_US5Y_REAL, COL_US5Y_REAL = "DFII5", "us5y_real"
SERIES_US10Y_REAL, COL_US10Y_REAL = "DFII10", "us10y_real"
SERIES_BREAKEVEN_10Y, COL_BREAKEVEN_10Y = "T10YIE", "breakeven_10y"
SERIES_BREAKEVEN_5Y5Y, COL_BREAKEVEN_5Y5Y = "T5YIFR", "breakeven_5y5y"
SERIES_TERM_PREMIUM_10Y, COL_TERM_PREMIUM_10Y = "THREEFYTP10", "term_premium_10y"
SERIES_EFFR, COL_EFFR = "EFFR", "effr"
SERIES_OBFR, COL_OBFR = "OBFR", "obfr"
SERIES_SOFR, COL_SOFR = "SOFR", "sofr"
SERIES_IORB, COL_IORB = "IORB", "iorb"

# (metric_id, series_id, column, human tenor label) -- the nineteen level
# metrics/components, grouped by family (JUDGMENT CALL 8's required/optional
# split is expressed via _OPTIONAL_SERIES below, not by group membership here).
_NOMINAL_NODES = (
    ("us3m_level", SERIES_US3M, COL_US3M, "3-month"),
    ("us6m_level", SERIES_US6M, COL_US6M, "6-month"),
    ("us1y_level", SERIES_US1Y, COL_US1Y, "1-year"),
    ("us2y_level", SERIES_US2Y, COL_US2Y, "2-year"),
    ("us3y_level", SERIES_US3Y, COL_US3Y, "3-year"),
    ("us5y_level", SERIES_US5Y, COL_US5Y, "5-year"),
    ("us7y_level", SERIES_US7Y, COL_US7Y, "7-year"),
    ("us10y_level", SERIES_US10Y, COL_US10Y, "10-year"),
    ("us20y_level", SERIES_US20Y, COL_US20Y, "20-year"),
    ("us30y_level", SERIES_US30Y, COL_US30Y, "30-year"),
)
_REAL_NODES = (
    ("us5y_real_level", SERIES_US5Y_REAL, COL_US5Y_REAL, "5-year"),
    ("us10y_real_level", SERIES_US10Y_REAL, COL_US10Y_REAL, "10-year"),
)
_BREAKEVEN_NODES = (
    ("breakeven_10y_level", SERIES_BREAKEVEN_10Y, COL_BREAKEVEN_10Y, "10-year"),
    ("breakeven_5y5y_level", SERIES_BREAKEVEN_5Y5Y, COL_BREAKEVEN_5Y5Y, "5-year, 5-year forward"),
)
_TERM_PREMIUM_NODE = ("term_premium_10y_level", SERIES_TERM_PREMIUM_10Y, COL_TERM_PREMIUM_10Y, "10-year")
_CORRIDOR_NODES = (
    ("effr_level", SERIES_EFFR, COL_EFFR, "Effective Fed Funds Rate"),
    ("obfr_level", SERIES_OBFR, COL_OBFR, "Overnight Bank Funding Rate"),
    ("sofr_level", SERIES_SOFR, COL_SOFR, "Secured Overnight Financing Rate"),
    ("iorb_level", SERIES_IORB, COL_IORB, "Interest on Reserve Balances"),
)
_ALL_LEVEL_NODES = _NOMINAL_NODES + _REAL_NODES + _BREAKEVEN_NODES + (_TERM_PREMIUM_NODE,) + _CORRIDOR_NODES

# JUDGMENT CALL 8: the long-tail CMT nodes + OBFR are optional; everything
# else is required. Verified by construction: grep every _pair_value /
# _triple_value call below -- none reads DGS1, DGS3, DGS7, DGS20, or OBFR.
_OPTIONAL_SERIES = frozenset({SERIES_US1Y, SERIES_US3Y, SERIES_US7Y, SERIES_US20Y, SERIES_OBFR})

# --------------------------------------------------------------------------- #
# freshness law constants (JUDGMENT CALLS 6-7; see module docstring).
# --------------------------------------------------------------------------- #
_DAILY_CADENCE_DAYS = 5
_DAILY_GRACE_DAYS = 4
_TERM_PREMIUM_CADENCE_DAYS = 9
_TERM_PREMIUM_GRACE_DAYS = 5

# --------------------------------------------------------------------------- #
# derived-read window constants (JUDGMENT CALL 9).
# --------------------------------------------------------------------------- #
_THIRTEEN_WEEK_DAYS = 91
_LOOKBACK_SLACK_DAYS = 10

# Same-date discipline tolerance (JUDGMENT CALL 3).
_SAME_DATE_STALENESS_BOUND_DAYS = 5

# Inversion run-length minimum history (JUDGMENT CALL 10).
_MIN_INVERSION_HISTORY_ROWS = 20

# Decomposition-residual tolerance, percentage points (JUDGMENT CALL 11).
_DECOMPOSITION_RESIDUAL_TOLERANCE_PCT_PTS = 0.15

_FRESH_SEVERITY = {
    "CURRENT": 0,
    "HISTORICAL_AS_KNOWN": 1,
    "LATE_WITHIN_TOLERANCE": 2,
    "SIMULATED": 3,
    "STALE_SOURCE": 4,
    "NOT_YET_RELEASED": 5,
    "RIGHTS_BLOCKED": 6,
    "NOT_COVERED": 7,
    "SOURCE_FAILED": 8,
}

_TRACKED_CHANGE_METRICS = (
    "us2y_level", "us10y_level", "curve_2s10s_level", "term_premium_10y_level",
)
_TRACKED_CORRECTION_METRICS = tuple(mid for mid, *_ in _ALL_LEVEL_NODES) + (
    "us2y_change_13w", "us10y_change_13w", "us30y_change_13w", "term_premium_10y_change_13w",
    "curve_2s10s_level", "curve_3m10y_level", "curve_5s30s_level",
    "curve_2s10s_inversion_run_length_bd", "curve_3m10y_inversion_run_length_bd",
    "curvature_butterfly_2s5s10s", "nominal_real_breakeven_residual_10y",
    "corridor_effr_minus_iorb_bp", "corridor_sofr_minus_effr_bp", "corridor_sofr_minus_iorb_bp",
)


# --------------------------------------------------------------------------- #
# small pure helpers (deliberately self-contained -- no cross-import from any
# sibling composer, mirrors housing.py / national_debt.py so this file can be
# added without touching any other module)
# --------------------------------------------------------------------------- #
def _get(d: Any, *path: str) -> Any:
    cur = d
    for key in path:
        if isinstance(cur, Mapping) and key in cur:
            cur = cur[key]
        else:
            return None
    return cur


def _num(v: Any) -> float | None:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    return float(v)


def _round(v: float | None, n: int = 4) -> float | None:
    return None if v is None else round(float(v), n)


def _bil(en: str | None, zh: str | None) -> dict:
    return {"en": en, "zh": zh}


def _band(v, lo, hi):
    if v is None:
        return None
    return "LOW" if v < lo else ("HIGH" if v > hi else "MEDIUM")


def _worst_freshness(states: list[str]) -> str:
    if not states:
        return "SOURCE_FAILED"
    return max(states, key=lambda s: _FRESH_SEVERITY.get(s, 0))


def _parse_date(s: Any) -> _dt.date | None:
    if isinstance(s, _dt.date):
        return s
    if not isinstance(s, str) or len(s) < 10:
        return None
    try:
        return _dt.date.fromisoformat(s[:10])
    except ValueError:
        return None


def _iso(d: _dt.date | None) -> str | None:
    return d.isoformat() if isinstance(d, _dt.date) else None


def _age_days(built_at: Any, asof: Any) -> int | None:
    """Pure function of two GIVEN date/datetime values -- never a wall-clock
    read. ``built_at`` is always supplied by the caller (the builder), never
    sourced from ``datetime.now()`` inside this module."""
    b, a = _parse_date(built_at), _parse_date(asof)
    if b is None or a is None:
        return None
    return (b - a).days


def _cadence_freshness(built_at: Any, asof: _dt.date | None, cadence_days: int,
                        grace_days: int, value_present: bool) -> str:
    """Shared release-cadence law (JUDGMENT CALLS 6-7). ``value_present=False``
    (series wholly absent) always reads SOURCE_FAILED; an ``asof`` in the
    future relative to ``built_at`` (a clock inversion) also reads
    SOURCE_FAILED rather than a nonsensical CURRENT."""
    if not value_present or asof is None:
        return "SOURCE_FAILED"
    age = _age_days(built_at, asof)
    if age is None or age < 0:
        return "SOURCE_FAILED"
    if age <= cadence_days:
        return "CURRENT"
    if age <= cadence_days + grace_days:
        return "LATE_WITHIN_TOLERANCE"
    return "STALE_SOURCE"


# --------------------------------------------------------------------------- #
# raw-row handling (mirrors housing.py / national_debt.py exactly)
# --------------------------------------------------------------------------- #
def _clean_rows(rows: Any) -> list[tuple[_dt.date, float]]:
    """Defensively normalize a caller-supplied row list: accept ``(date, value)``
    pairs or longer tuples (extra elements ignored -- an unconsumed-field
    negative control for the digest tests), drop unparseable dates / non-numeric
    values, de-duplicate a repeated date keeping the LAST-listed occurrence
    (mirrors ``lib.store.upsert``'s own "new wins" convention), and sort
    ascending by date. Never raises on malformed input -- a bad row is dropped,
    never fabricated into a fake reading."""
    if not rows:
        return []
    out: dict[_dt.date, float] = {}
    for row in rows:
        if row is None:
            continue
        try:
            d_raw, v_raw = row[0], row[1]
        except (IndexError, TypeError, KeyError):
            continue
        d = _parse_date(d_raw)
        v = _num(v_raw)
        if d is None or v is None:
            continue
        out[d] = v
    return sorted(out.items())


def _latest(rows: list[tuple[_dt.date, float]]) -> tuple[_dt.date, float] | None:
    return rows[-1] if rows else None


def _value_before_or_at(rows: list[tuple[_dt.date, float]], target: _dt.date,
                         slack_days: int) -> tuple[_dt.date, float] | None:
    """The most recent row with date <= ``target``, accepted ONLY if it lands
    within ``slack_days`` of ``target`` -- never an arbitrarily-old fallback
    masquerading as a fresh 13w comparison point. Returns ``None`` (refuse)
    when no row reaches back far enough or the nearest one is too stale."""
    best: tuple[_dt.date, float] | None = None
    for d, v in rows:
        if d <= target:
            best = (d, v)
        else:
            break
    if best is None:
        return None
    if (target - best[0]).days > slack_days:
        return None
    return best


# --------------------------------------------------------------------------- #
# same-date discipline (JUDGMENT CALLS 3-4): a genuine new law this composer
# introduces -- combining two or three INDEPENDENTLY-clocked series into one
# point-in-time read.
# --------------------------------------------------------------------------- #
def _shared_reading(rows_list: list[list[tuple[_dt.date, float]]],
                     bound_days: int) -> tuple[_dt.date, tuple[float, ...]] | None:
    """Locate the LATEST date common to every given (non-empty) row list, then
    refuse (``None``) unless that shared date sits within ``bound_days`` of
    EVERY list's own separately-latest print. Returns
    ``(shared_date, (value_for_list_0, value_for_list_1, ...))`` on success --
    never a per-leg "each at its own latest date" reading under one reported
    date. Callers are responsible for the leg-floor check (all lists non-empty)
    before calling this; see ``_pair_value`` / ``_triple_value``."""
    maps = [dict(r) for r in rows_list]
    common = set(maps[0])
    for m in maps[1:]:
        common &= set(m)
    if not common:
        return None
    shared_date = max(common)
    for rows in rows_list:
        newest = rows[-1][0]
        if (newest - shared_date).days > bound_days:
            return None
    return shared_date, tuple(m[shared_date] for m in maps)


def _pair_value(a_rows: list[tuple[_dt.date, float]], b_rows: list[tuple[_dt.date, float]],
                 a_fresh: str, b_fresh: str,
                 bound_days: int = _SAME_DATE_STALENESS_BOUND_DAYS
                 ) -> tuple[_dt.date | None, float | None, float | None, str, str | None]:
    """Two-leg same-date-disciplined pair read. Returns
    ``(shared_date, a_value, b_value, freshness, null_reason)``; on a null the
    first three are ``None`` and ``null_reason`` explains why. Estate
    propagation law (housing/consumer_payments precedent): ANY absent leg
    propagates ``SOURCE_FAILED`` -- the read failed because a source failed;
    ``COMPUTATION_REFUSED`` is reserved for legs that are all PRESENT but share
    no sufficiently fresh common date (the same-date-discipline law in the
    module docstring)."""
    if a_rows and b_rows:
        fresh = _worst_freshness([a_fresh, b_fresh])
        shared = _shared_reading([a_rows, b_rows], bound_days)
        if shared is None:
            return None, None, None, fresh, "COMPUTATION_REFUSED"
        d, (va, vb) = shared
        return d, va, vb, fresh, None
    return None, None, None, "SOURCE_FAILED", "SOURCE_FAILED"


def _triple_value(a_rows, b_rows, c_rows, a_fresh: str, b_fresh: str, c_fresh: str,
                   bound_days: int = _SAME_DATE_STALENESS_BOUND_DAYS
                   ) -> tuple[_dt.date | None, tuple[float | None, float | None, float | None],
                              str, str | None]:
    """Three-leg same-date-disciplined read (the butterfly and the nominal/
    real/breakeven decomposition). Returns
    ``(shared_date, (a_value, b_value, c_value), freshness, null_reason)``.
    Same estate propagation law as ``_pair_value``: any absent leg ->
    ``SOURCE_FAILED``; ``COMPUTATION_REFUSED`` only for all-present legs with
    no shared, sufficiently fresh date."""
    present = (bool(a_rows), bool(b_rows), bool(c_rows))
    if all(present):
        fresh = _worst_freshness([a_fresh, b_fresh, c_fresh])
        shared = _shared_reading([a_rows, b_rows, c_rows], bound_days)
        if shared is None:
            return None, (None, None, None), fresh, "COMPUTATION_REFUSED"
        d, vals = shared
        return d, vals, fresh, None
    return None, (None, None, None), "SOURCE_FAILED", "SOURCE_FAILED"


def _shared_series(short_rows: list[tuple[_dt.date, float]],
                    long_rows: list[tuple[_dt.date, float]]
                    ) -> list[tuple[_dt.date, float, float]]:
    """ALL dates common to both series (ascending), each carrying
    ``(date, short_value, long_value)`` -- the FULL merged history the
    inversion run-length walk needs, distinct from ``_shared_reading``'s
    single-point-plus-staleness-bound check used for a fresh spread/
    decomposition read. No staleness bound applies here: the walk uses
    whatever contiguous shared history the two given series actually carry."""
    if not short_rows or not long_rows:
        return []
    long_map = dict(long_rows)
    return [(d, v, long_map[d]) for d, v in short_rows if d in long_map]


def _inversion_run_length(shared: list[tuple[_dt.date, float, float]],
                           min_rows: int = _MIN_INVERSION_HISTORY_ROWS
                           ) -> tuple[int | None, str | None]:
    """Walk the shared (short, long) history BACKWARD from its latest shared
    date, counting consecutive rows sharing the latest row's own inversion
    sign (inverted when ``long < short``). Refused (``INSUFFICIENT_HISTORY``)
    below ``min_rows`` shared-date rows -- JUDGMENT CALL 10."""
    if len(shared) < min_rows:
        return None, "INSUFFICIENT_HISTORY"
    signs = [1 if (long_v - short_v) < 0 else 0 for _, short_v, long_v in shared]
    latest_sign = signs[-1]
    run = 0
    for s in reversed(signs):
        if s != latest_sign:
            break
        run += 1
    return run, None


# --------------------------------------------------------------------------- #
# metric / component builders (mirror housing.py / national_debt.py)
# --------------------------------------------------------------------------- #
def _metric(metric_id, value, value_type, unit, basis, direction, owner_ref,
            owner_field, reference_period, freshness, *, source_refs=None,
            transformation=None, status="PRESENT", null_reason=None,
            calculation_as_of=None) -> dict:
    return {
        "metric_id": metric_id,
        "reference_id": f"mastermind.market_reference/v1#{metric_id}",
        "definition_id": owner_field,
        "definition_version": DEFINITION_VERSION,
        "owner_ref": owner_ref,
        "value": value,
        "value_type": value_type,
        "unit": unit,
        "basis": basis,
        "direction_semantics": direction,
        "reference_period": reference_period,
        "observed_at": reference_period,
        "released_at": None,
        "available_at": None,
        "collected_at": None,
        "revised_at": None,
        "calculation_as_of": calculation_as_of if calculation_as_of is not None else reference_period,
        "market_session": None,
        "source_refs": source_refs or [owner_ref],
        "source_digest": None,
        "transformation": transformation,
        "model_version": METHOD_VERSION,
        "uncertainty": {"kind": None, "value": None},
        "coverage": None,
        "freshness": freshness,
        "rights_state": "OPEN",
        "status": status if value is not None else "ABSENT",
        "null_reason": null_reason if value is not None else (null_reason or "SOURCE_FAILED"),
        "authority_ceiling": "DESCRIPTIVE",
    }


def _metric_value(snapshot: Mapping | None, metric_id: str) -> Any:
    for m in (_get(snapshot, "metrics", "items") or []):
        if m.get("metric_id") == metric_id:
            return m.get("value")
    return None


def _component(component_id: str, label_en: str, label_zh: str,
                rows: list[tuple[_dt.date, float]], freshness: str, required: bool) -> dict:
    present = bool(rows)
    latest = _latest(rows)
    status = "PRESENT" if present and freshness == "CURRENT" else ("PARTIAL" if present else "ABSENT")
    if present:
        null_reason = None
    elif freshness == "SOURCE_FAILED":
        null_reason = "SOURCE_FAILED"
    else:
        null_reason = "UNKNOWN"
    return {
        "component_id": component_id,
        "label": _bil(label_en, label_zh),
        "required": required,
        "freshness": freshness,
        "status": status,
        "source_asof": _iso(latest[0]) if latest else None,
        "null_reason": null_reason,
    }


# --------------------------------------------------------------------------- #
# the composer
# --------------------------------------------------------------------------- #
def compose(curve_frames: Mapping[str, Any] | None, *, built_at: str,
            prior_snapshot: Mapping[str, Any] | None = None,
            code_version: str | None = None) -> dict:
    """Project ``curve_frames`` (dict of raw FRED CMT/corridor level rows, see
    module docstring) into an UNSEALED snapshot body. The builder seals it via
    ``contract.finalize``."""
    cf = curve_frames if isinstance(curve_frames, Mapping) else {}

    rows: dict[str, list[tuple[_dt.date, float]]] = {
        sid: _clean_rows(cf.get(sid)) for _mid, sid, _col, _label in _ALL_LEVEL_NODES
    }
    fresh: dict[str, str] = {}
    for _mid, sid, _col, _label in _ALL_LEVEL_NODES:
        cadence, grace = ((_TERM_PREMIUM_CADENCE_DAYS, _TERM_PREMIUM_GRACE_DAYS)
                           if sid == SERIES_TERM_PREMIUM_10Y
                           else (_DAILY_CADENCE_DAYS, _DAILY_GRACE_DAYS))
        latest = _latest(rows[sid])
        fresh[sid] = _cadence_freshness(built_at, latest[0] if latest else None,
                                         cadence, grace, bool(latest))

    ctx = {"built_at": built_at, "rows": rows, "fresh": fresh}

    derived = _derive(ctx)
    contradictions = _detect_contradiction(derived["residual_10y"],
                                            derived["residual_10y_shared_date"])
    fired_kinds = {c["kind"] for c in contradictions}

    metrics = _metrics(ctx, derived, fired_kinds)
    metrics_by_id = {m["metric_id"]: m["value"] for m in metrics}

    required_avail, optional_avail = _required_availability(rows, fresh)
    all_avail = required_avail + optional_avail
    worst = _worst_freshness([c["freshness"] for c in required_avail])
    n_present = sum(1 for c in required_avail if c["status"] in ("PRESENT", "PARTIAL"))
    coverage_ratio = round(n_present / len(required_avail), 4) if required_avail else 0.0
    degraded = [c["component_id"] for c in required_avail if c["freshness"] != "CURRENT"]
    reasons: list[str] = []
    if worst != "CURRENT":
        reasons.append(f"worst_required_source_freshness={worst}")
    for c in contradictions:
        reasons.append(f"contradiction={c['kind']}")

    primary_contradiction = contradictions[0] if contradictions else {
        "kind": None, "en": None, "zh": None, "components": [],
    }

    dates: list[_dt.date] = []
    for sid_rows in rows.values():
        latest = _latest(sid_rows)
        if latest:
            dates.append(latest[0])
    effective_date = _iso(max(dates)) if dates else None

    headline = _headline(effective_date, prior_snapshot)
    changes = _changes(metrics_by_id, prior_snapshot)

    snapshot = {
        "schema": {"contract": "mastermind.macro_workspace_snapshot.v1", "version": "1.0.0"},
        "workspace": {
            "id": WORKSPACE_ID,
            "title": _bil("Rates & Curves", "利率与曲线"),
            "subtitle": _bil("The Treasury curve, node by node",
                              "国债收益率曲线，逐节点"),
        },
        "region": {"code": "US", "supported": True, "display_name": "United States"},
        "generation": {
            "generation_id": "PENDING",
            "built_at": built_at,
            "rendered_at": None,
            "producer": PRODUCER,
            "code_version": code_version,
            "calculation_as_of": effective_date,
            "content_sha256": "0" * 64,
        },
        "authority": {
            "class": "context_only", "display_only": True, "can_rank": False,
            "can_gate": False, "can_size": False, "can_originate_signal": False,
            "can_execute": False, "axis_authority_ceiling": "DESCRIPTIVE",
        },
        "availability": {
            "state": worst,
            "required": all_avail,
            "degraded": degraded,
            "coverage_ratio": coverage_ratio,
            "worst_freshness": worst,
            "contradiction": {
                "present": bool(contradictions),
                "kind": primary_contradiction["kind"],
                "en": primary_contradiction["en"],
                "zh": primary_contradiction["zh"],
                "components": primary_contradiction["components"],
            },
            "reasons": reasons,
        },
        "headline": headline,
        "axes": {"items": []},
        "metrics": {"items": metrics},
        "series": {
            "items": [],
            "status": "ABSENT",
            "null_reason": "INSUFFICIENT_HISTORY",
        },
        "drivers": _drivers(metrics_by_id),
        "changes": changes,
        "implications": {"items": _implications(metrics_by_id, contradictions,
                                                  worst, coverage_ratio)},
        "scenario_contract": _scenario_contract(),
        "alert_contract": _alert_contract(),
        "sources": {"items": _sources(rows, fresh)},
        "corrections": _corrections(metrics_by_id, effective_date, prior_snapshot),
        "learning": {
            "instrumentation": "first_party",
            "event_names": [
                "macro_workspace_opened", "macro_state_changed_seen",
                "macro_driver_expanded", "macro_source_opened",
                "macro_degraded_state_seen", "macro_unknown_or_refusal_seen",
            ],
            "privacy_note": "Event definitions reuse the existing first-party analytics owner; no second analytics store, no user identity copied into the artifact.",
        },
    }
    return snapshot


# --------------------------------------------------------------------------- #
# derived reads (compute-then-detect order, mirrors housing.py / national_debt.py)
# --------------------------------------------------------------------------- #
def _derive(ctx: dict) -> dict:
    rows, fresh, built_at = ctx["rows"], ctx["fresh"], ctx["built_at"]

    def r(sid):
        return rows[sid]

    def f(sid):
        return fresh[sid]

    d: dict[str, Any] = {}

    # -- 13-week changes (2y / 10y / 30y / term premium) ---------------------
    for mid, sid in (("us2y_change_13w", SERIES_US2Y), ("us10y_change_13w", SERIES_US10Y),
                      ("us30y_change_13w", SERIES_US30Y),
                      ("term_premium_10y_change_13w", SERIES_TERM_PREMIUM_10Y)):
        latest = _latest(r(sid))
        if latest is None:
            d[mid] = None
            continue
        prior = _value_before_or_at(r(sid), latest[0] - _dt.timedelta(days=_THIRTEEN_WEEK_DAYS),
                                     _LOOKBACK_SLACK_DAYS)
        d[mid] = _round(latest[1] - prior[1], 4) if prior is not None else None

    # -- slopes (same-date disciplined pairs) ---------------------------------
    d["date_2s10s"], d["v_2y_for_2s10s"], d["v_10y_for_2s10s"], d["fresh_2s10s"], d["null_2s10s"] = \
        _pair_value(r(SERIES_US2Y), r(SERIES_US10Y), f(SERIES_US2Y), f(SERIES_US10Y))
    d["curve_2s10s_level"] = (_round(d["v_10y_for_2s10s"] - d["v_2y_for_2s10s"], 4)
                               if d["null_2s10s"] is None else None)

    d["date_3m10y"], d["v_3m_for_3m10y"], d["v_10y_for_3m10y"], d["fresh_3m10y"], d["null_3m10y"] = \
        _pair_value(r(SERIES_US3M), r(SERIES_US10Y), f(SERIES_US3M), f(SERIES_US10Y))
    d["curve_3m10y_level"] = (_round(d["v_10y_for_3m10y"] - d["v_3m_for_3m10y"], 4)
                               if d["null_3m10y"] is None else None)

    d["date_5s30s"], d["v_5y_for_5s30s"], d["v_30y_for_5s30s"], d["fresh_5s30s"], d["null_5s30s"] = \
        _pair_value(r(SERIES_US5Y), r(SERIES_US30Y), f(SERIES_US5Y), f(SERIES_US30Y))
    d["curve_5s30s_level"] = (_round(d["v_30y_for_5s30s"] - d["v_5y_for_5s30s"], 4)
                               if d["null_5s30s"] is None else None)

    # -- inversion run-lengths (full shared-history walk, independent floor) -
    shared_2s10s = _shared_series(r(SERIES_US2Y), r(SERIES_US10Y))
    d["run_2s10s"], d["run_2s10s_null"] = (
        (None, d["null_2s10s"]) if d["null_2s10s"] is not None
        else _inversion_run_length(shared_2s10s))
    shared_3m10y = _shared_series(r(SERIES_US3M), r(SERIES_US10Y))
    d["run_3m10y"], d["run_3m10y_null"] = (
        (None, d["null_3m10y"]) if d["null_3m10y"] is not None
        else _inversion_run_length(shared_3m10y))

    # -- curvature butterfly (2*5y - 2y - 10y, three-leg same-date) -----------
    d["date_butterfly"], (d["v_2y_bf"], d["v_5y_bf"], d["v_10y_bf"]), d["fresh_butterfly"], d["null_butterfly"] = \
        _triple_value(r(SERIES_US2Y), r(SERIES_US5Y), r(SERIES_US10Y),
                       f(SERIES_US2Y), f(SERIES_US5Y), f(SERIES_US10Y))
    d["curvature_butterfly_2s5s10s"] = (
        _round(2.0 * d["v_5y_bf"] - d["v_2y_bf"] - d["v_10y_bf"], 4)
        if d["null_butterfly"] is None else None)

    # -- nominal/real/breakeven decomposition (three-leg same-date) -----------
    (d["date_decomp"], (d["v_nominal_10y"], d["v_real_10y"], d["v_breakeven_10y"]),
     d["fresh_decomp"], d["null_decomp"]) = _triple_value(
        r(SERIES_US10Y), r(SERIES_US10Y_REAL), r(SERIES_BREAKEVEN_10Y),
        f(SERIES_US10Y), f(SERIES_US10Y_REAL), f(SERIES_BREAKEVEN_10Y))
    d["residual_10y"] = (
        _round(d["v_nominal_10y"] - (d["v_real_10y"] + d["v_breakeven_10y"]), 4)
        if d["null_decomp"] is None else None)
    d["residual_10y_shared_date"] = d["date_decomp"]

    # -- policy corridor spreads (basis points, same-date pairs) --------------
    d["date_effr_iorb"], d["v_effr_a"], d["v_iorb_a"], d["fresh_effr_iorb"], d["null_effr_iorb"] = \
        _pair_value(r(SERIES_EFFR), r(SERIES_IORB), f(SERIES_EFFR), f(SERIES_IORB))
    d["corridor_effr_minus_iorb_bp"] = (
        _round((d["v_effr_a"] - d["v_iorb_a"]) * 100.0, 2) if d["null_effr_iorb"] is None else None)

    d["date_sofr_effr"], d["v_sofr_b"], d["v_effr_b"], d["fresh_sofr_effr"], d["null_sofr_effr"] = \
        _pair_value(r(SERIES_SOFR), r(SERIES_EFFR), f(SERIES_SOFR), f(SERIES_EFFR))
    d["corridor_sofr_minus_effr_bp"] = (
        _round((d["v_sofr_b"] - d["v_effr_b"]) * 100.0, 2) if d["null_sofr_effr"] is None else None)

    d["date_sofr_iorb"], d["v_sofr_c"], d["v_iorb_c"], d["fresh_sofr_iorb"], d["null_sofr_iorb"] = \
        _pair_value(r(SERIES_SOFR), r(SERIES_IORB), f(SERIES_SOFR), f(SERIES_IORB))
    d["corridor_sofr_minus_iorb_bp"] = (
        _round((d["v_sofr_c"] - d["v_iorb_c"]) * 100.0, 2) if d["null_sofr_iorb"] is None else None)

    return d


# --------------------------------------------------------------------------- #
# contradiction detection (JUDGMENT CALL 11)
# --------------------------------------------------------------------------- #
def _detect_contradiction(residual: float | None, shared_date: _dt.date | None) -> list[dict]:
    """The nominal-10y vs (real-10y + breakeven-10y) decomposition residual,
    beyond the disclosed tolerance, on a genuine shared date -- the market's
    own curve data disagreeing with its own identity. Silent whenever the
    residual is absent or inside the disclosed band -- never forced."""
    if residual is None:
        return []
    if abs(residual) <= _DECOMPOSITION_RESIDUAL_TOLERANCE_PCT_PTS:
        return []
    direction_en = "above" if residual > 0 else "below"
    direction_zh = "高于" if residual > 0 else "低于"
    date_en = f" on {shared_date.isoformat()}" if shared_date is not None else ""
    date_zh = f"（{shared_date.isoformat()}）" if shared_date is not None else ""
    return [{
        "kind": "nominal_real_breakeven_decomposition_disagreement",
        "en": (f"The 10-year nominal Treasury yield reads {residual:+.2f} percentage "
               f"points {direction_en} the sum of the 10-year real (TIPS) yield and the "
               f"10-year breakeven inflation rate{date_en} -- beyond this page's "
               "disclosed interpolation-noise tolerance, so the curve's own nominal, "
               "real, and breakeven legs are disagreeing with their own identity by "
               "more than normal cross-curve noise would explain."),
        "zh": (f"10年期名义国债收益率与10年期实际（TIPS）收益率加10年期盈亏平衡通胀率之和"
               f"相比{date_zh}，读数相差{residual:+.2f}个百分点，方向为{direction_zh}——"
               "超出本页披露的插值噪声容差,说明曲线自身的名义、实际与盈亏平衡分项之间的"
               "分歧已超出正常跨曲线噪声所能解释的范围。"),
        "components": ["nominal_real_breakeven_residual_10y"],
    }]


# --------------------------------------------------------------------------- #
# availability
# --------------------------------------------------------------------------- #
def _required_availability(rows: dict, fresh: dict) -> tuple[list[dict], list[dict]]:
    specs = []
    for mid, sid, col, label in _ALL_LEVEL_NODES:
        specs.append((col, f"{label} node ({col})", f"{label}节点（{col}）",
                      rows[sid], fresh[sid], sid not in _OPTIONAL_SERIES))
    built = [_component(cid, en, zh, r, fr, req) for cid, en, zh, r, fr, req in specs]
    required_rows = [c for c in built if c["required"]]
    optional_rows = [c for c in built if not c["required"]]
    return required_rows, optional_rows


# --------------------------------------------------------------------------- #
# metrics
# --------------------------------------------------------------------------- #
def _metrics(ctx: dict, d: dict, fired_kinds: set[str]) -> list[dict]:
    rows, fresh = ctx["rows"], ctx["fresh"]
    items: list[dict] = []

    # -- levels (nineteen, one per series) ------------------------------------
    for mid, sid, col, label in _NOMINAL_NODES:
        latest = _latest(rows[sid])
        items.append(_metric(
            mid, latest[1] if latest else None, "percent", "percent",
            "constant_maturity_investment_basis", "higher_more_restrictive",
            f"data/fred/{sid}.parquet", f"fred.{sid}.{col}",
            _iso(latest[0]) if latest else None, fresh[sid],
            source_refs=[f"FRED:{sid}"],
            transformation=(f"{label} Treasury constant-maturity yield (investment/"
                             "bond-equivalent basis), republished by FRED."),
        ))
    for mid, sid, col, label in _REAL_NODES:
        latest = _latest(rows[sid])
        items.append(_metric(
            mid, latest[1] if latest else None, "percent", "percent",
            "tips_constant_maturity_investment_basis", "higher_more_restrictive_real_financing_cost",
            f"data/fred/{sid}.parquet", f"fred.{sid}.{col}",
            _iso(latest[0]) if latest else None, fresh[sid],
            source_refs=[f"FRED:{sid}"],
            transformation=(f"{label} Treasury Inflation-Protected Securities (TIPS) "
                             "constant-maturity real yield, republished by FRED."),
        ))
    for mid, sid, col, label in _BREAKEVEN_NODES:
        latest = _latest(rows[sid])
        items.append(_metric(
            mid, latest[1] if latest else None, "percent", "percent",
            "market_derived_breakeven_inflation", "higher_more_inflation_priced",
            f"data/fred/{sid}.parquet", f"fred.{sid}.{col}",
            _iso(latest[0]) if latest else None, fresh[sid],
            source_refs=[f"FRED:{sid}"],
            transformation=(f"{label} Treasury breakeven inflation rate (nominal minus "
                             "TIPS yield at that tenor), republished by FRED -- a market "
                             "price, not a survey or a Fed forecast."),
        ))
    tp_mid, tp_sid, tp_col, tp_label = _TERM_PREMIUM_NODE
    tp_latest = _latest(rows[tp_sid])
    items.append(_metric(
        tp_mid, tp_latest[1] if tp_latest else None, "percent", "percent",
        "kim_wright_term_premium_model", "higher_more_term_compensation_demanded",
        f"data/fred/{tp_sid}.parquet", f"fred.{tp_sid}.{tp_col}",
        _iso(tp_latest[0]) if tp_latest else None, fresh[tp_sid],
        source_refs=[f"FRED:{tp_sid}"],
        transformation=(f"{tp_label} Kim-Wright term premium (model-based decomposition "
                         "of the nominal yield into an expectations component and a "
                         "term-premium component), republished by FRED."),
    ))
    for mid, sid, col, label in _CORRIDOR_NODES:
        latest = _latest(rows[sid])
        items.append(_metric(
            mid, latest[1] if latest else None, "percent", "percent",
            "realized_reference_rate", "higher_tighter_policy_stance",
            f"data/fred/{sid}.parquet", f"fred.{sid}.{col}",
            _iso(latest[0]) if latest else None, fresh[sid],
            source_refs=[f"FRED:{sid}"],
            transformation=f"{label}, republished by FRED.",
        ))

    # -- 13-week changes -------------------------------------------------------
    for mid, sid in (("us2y_change_13w", SERIES_US2Y), ("us10y_change_13w", SERIES_US10Y),
                      ("us30y_change_13w", SERIES_US30Y)):
        latest = _latest(rows[sid])
        items.append(_metric(
            mid, d[mid], "number", "pct_pts", "trailing_13w_level_change",
            "positive_is_yields_rising_over_13w", f"data/fred/{sid}.parquet",
            f"fred.{sid}",
            _iso(latest[0]) if latest else None, fresh[sid], source_refs=[f"FRED:{sid}"],
            transformation=(
                "Current level minus the level roughly 13 weeks (91 days) prior, in "
                f"percentage points; refused when no observation lands within "
                f"{_LOOKBACK_SLACK_DAYS} days of that lookback target."
            ),
            null_reason="INSUFFICIENT_HISTORY" if latest else None,
        ))
    tp_latest_for_chg = _latest(rows[SERIES_TERM_PREMIUM_10Y])
    items.append(_metric(
        "term_premium_10y_change_13w", d["term_premium_10y_change_13w"], "number", "pct_pts",
        "trailing_13w_level_change", "positive_is_term_compensation_rising_over_13w",
        f"data/fred/{SERIES_TERM_PREMIUM_10Y}.parquet", f"fred.{SERIES_TERM_PREMIUM_10Y}",
        _iso(tp_latest_for_chg[0]) if tp_latest_for_chg else None, fresh[SERIES_TERM_PREMIUM_10Y],
        source_refs=[f"FRED:{SERIES_TERM_PREMIUM_10Y}"],
        transformation=(
            "Current 10-year Kim-Wright term premium minus the level roughly 13 weeks "
            f"(91 days) prior; refused when no observation lands within "
            f"{_LOOKBACK_SLACK_DAYS} days of that lookback target."
        ),
        null_reason="INSUFFICIENT_HISTORY" if tp_latest_for_chg else None,
    ))

    # -- slopes (same-date disciplined) -----------------------------------------
    _slope_defs = (
        ("curve_2s10s_level", "curve_2s10s", d["curve_2s10s_level"], d["date_2s10s"],
         d["fresh_2s10s"], d["null_2s10s"], SERIES_US10Y, SERIES_US2Y, "10-year minus 2-year"),
        ("curve_3m10y_level", "curve_3m10y", d["curve_3m10y_level"], d["date_3m10y"],
         d["fresh_3m10y"], d["null_3m10y"], SERIES_US10Y, SERIES_US3M, "10-year minus 3-month"),
        ("curve_5s30s_level", "curve_5s30s", d["curve_5s30s_level"], d["date_5s30s"],
         d["fresh_5s30s"], d["null_5s30s"], SERIES_US30Y, SERIES_US5Y, "30-year minus 5-year"),
    )
    for mid, slug, val, shared_date, fr, null_reason, long_sid, short_sid, label in _slope_defs:
        items.append(_metric(
            mid, val, "number", "pct_pts", "same_date_disciplined_spread",
            "higher_steeper_curve", f"data/fred/{long_sid}.parquet + data/fred/{short_sid}.parquet",
            f"fred.{long_sid} - fred.{short_sid}", _iso(shared_date), fr,
            source_refs=[f"FRED:{long_sid}", f"FRED:{short_sid}"],
            transformation=(
                f"{label}, at the latest date common to both legs (same-date "
                f"discipline); refused when no such date exists within "
                f"{_SAME_DATE_STALENESS_BOUND_DAYS} days of either leg's own newest "
                "print, rather than mixing an older print from one leg with a newer "
                "print from the other."
            ),
            null_reason=null_reason,
        ))

    # -- inversion run-lengths ---------------------------------------------------
    _run_defs = (
        ("curve_2s10s_inversion_run_length_bd", d["run_2s10s"], d["run_2s10s_null"],
         d["date_2s10s"], d["fresh_2s10s"], "2s10s", SERIES_US2Y, SERIES_US10Y),
        ("curve_3m10y_inversion_run_length_bd", d["run_3m10y"], d["run_3m10y_null"],
         d["date_3m10y"], d["fresh_3m10y"], "3m10y", SERIES_US3M, SERIES_US10Y),
    )
    for mid, val, null_reason, shared_date, fr, slug, short_sid, long_sid in _run_defs:
        items.append(_metric(
            mid, val, "count", "business_days", "consecutive_shared_date_rows",
            "longer_run_more_entrenched_regime", f"data/fred/{long_sid}.parquet + data/fred/{short_sid}.parquet",
            f"fred.{long_sid} - fred.{short_sid}", _iso(shared_date), fr,
            source_refs=[f"FRED:{long_sid}", f"FRED:{short_sid}"],
            transformation=(
                f"Count of consecutive shared-date rows (walking backward from the "
                f"latest one) holding the SAME sign as the {slug} spread's current "
                f"reading (inverted when the long leg reads below the short leg); "
                f"refused as insufficient below {_MIN_INVERSION_HISTORY_ROWS} "
                "shared-date historical rows, independent of whether the current "
                "sign itself is known."
            ),
            null_reason=null_reason,
        ))

    # -- curvature butterfly -------------------------------------------------
    items.append(_metric(
        "curvature_butterfly_2s5s10s", d["curvature_butterfly_2s5s10s"], "number", "pct_pts",
        "same_date_disciplined_butterfly", "higher_more_humped_curve",
        f"data/fred/{SERIES_US5Y}.parquet + data/fred/{SERIES_US2Y}.parquet + data/fred/{SERIES_US10Y}.parquet",
        f"2*fred.{SERIES_US5Y} - fred.{SERIES_US2Y} - fred.{SERIES_US10Y}",
        _iso(d["date_butterfly"]), d["fresh_butterfly"],
        source_refs=[f"FRED:{SERIES_US5Y}", f"FRED:{SERIES_US2Y}", f"FRED:{SERIES_US10Y}"],
        transformation=(
            "2*(5-year yield) minus 2-year yield minus 10-year yield, at the latest "
            "date common to all three legs (same-date discipline); refused unless "
            "all three legs share a sufficiently fresh date."
        ),
        null_reason=d["null_butterfly"],
    ))

    # -- nominal/real/breakeven decomposition residual ------------------------
    residual_disagree = ("nominal_real_breakeven_decomposition_disagreement" in fired_kinds
                          and d["residual_10y"] is not None)
    items.append(_metric(
        "nominal_real_breakeven_residual_10y", d["residual_10y"], "number", "pct_pts",
        "same_date_disciplined_decomposition_residual", "magnitude_indicates_cross_curve_interpolation_noise",
        f"data/fred/{SERIES_US10Y}.parquet + data/fred/{SERIES_US10Y_REAL}.parquet + data/fred/{SERIES_BREAKEVEN_10Y}.parquet",
        f"fred.{SERIES_US10Y} - (fred.{SERIES_US10Y_REAL} + fred.{SERIES_BREAKEVEN_10Y})",
        _iso(d["date_decomp"]), d["fresh_decomp"],
        source_refs=[f"FRED:{SERIES_US10Y}", f"FRED:{SERIES_US10Y_REAL}", f"FRED:{SERIES_BREAKEVEN_10Y}"],
        transformation=(
            "10-year nominal yield minus the sum of the 10-year real (TIPS) yield and "
            "the 10-year breakeven inflation rate, at the latest date common to all "
            f"three legs; a disclosed {_DECOMPOSITION_RESIDUAL_TOLERANCE_PCT_PTS:g}-"
            "percentage-point tolerance band absorbs the normal noise of comparing "
            "three separately-interpolated FRED curves -- a residual beyond the band "
            "is flagged as a genuine disagreement, never silently averaged away."
        ),
        status="DISAGREEMENT" if residual_disagree else "PRESENT",
        null_reason="DISAGREEMENT" if residual_disagree else d["null_decomp"],
    ))

    # -- policy corridor spreads (basis points) -------------------------------
    _corridor_defs = (
        ("corridor_effr_minus_iorb_bp", d["corridor_effr_minus_iorb_bp"], d["date_effr_iorb"],
         d["fresh_effr_iorb"], d["null_effr_iorb"], SERIES_EFFR, SERIES_IORB, "EFFR minus IORB"),
        ("corridor_sofr_minus_effr_bp", d["corridor_sofr_minus_effr_bp"], d["date_sofr_effr"],
         d["fresh_sofr_effr"], d["null_sofr_effr"], SERIES_SOFR, SERIES_EFFR, "SOFR minus EFFR"),
        ("corridor_sofr_minus_iorb_bp", d["corridor_sofr_minus_iorb_bp"], d["date_sofr_iorb"],
         d["fresh_sofr_iorb"], d["null_sofr_iorb"], SERIES_SOFR, SERIES_IORB, "SOFR minus IORB"),
    )
    for mid, val, shared_date, fr, null_reason, a_sid, b_sid, label in _corridor_defs:
        items.append(_metric(
            mid, val, "basis_points", "bp", "same_date_disciplined_spread",
            "higher_leg_a_trading_rich_to_leg_b", f"data/fred/{a_sid}.parquet + data/fred/{b_sid}.parquet",
            f"fred.{a_sid} - fred.{b_sid}", _iso(shared_date), fr,
            source_refs=[f"FRED:{a_sid}", f"FRED:{b_sid}"],
            transformation=(
                f"{label}, converted to basis points at the latest date common to "
                "both legs (same-date discipline); never published in percent, never "
                "mixed with a percent-denominated level."
            ),
            null_reason=null_reason,
        ))

    return items


# --------------------------------------------------------------------------- #
# headline (always NOT_APPLICABLE -- see module docstring: a design absence
# one level removed even from monetary_policy.py's own design-absence case,
# since no architecture section for this workspace exists at all)
# --------------------------------------------------------------------------- #
def _headline(effective_date, prior_snapshot) -> dict:
    prior_method = _get(prior_snapshot, "headline", "method_version")
    prior_eff = _get(prior_snapshot, "headline", "effective_date")
    return {
        "state_id": None,
        "state_label": {"en": None, "zh": None},
        "subtitle": _bil("Curve levels, slopes, inversion, and the policy corridor",
                          "曲线水平、利差、倒挂状态与政策走廊"),
        "method_version": METHOD_VERSION,
        "effective_date": effective_date,
        "quadrant": {"x": None, "y": None, "x_status": "ABSENT", "y_status": "ABSENT"},
        "prior_state": {"state_id": None, "effective_date": prior_eff, "method_version": prior_method},
        "transition_distance": None,
        "nearest_boundary": {"axis": None, "distance": None, "null_reason": "NOT_APPLICABLE"},
        "one_month_vector": {"dx": None, "dy": None, "status": "ABSENT", "null_reason": "NOT_APPLICABLE"},
        "hysteresis": {
            "band": 0.0, "applied": False, "held_prior": False,
            "note": (
                "Rates & Curves is a Chairman-authorized expansion added after the "
                "frozen Market Ontology architecture document's own twelve-workspace "
                "freeze, so no section of that document defines a headline model for "
                "it at all -- not even a note that none exists, the way "
                "monetary_policy/liquidity_central_banks each carry their own such "
                "note. There is accordingly no named axis pair here to attempt, and "
                "no dual-axis quadrant is asserted. A future architecture revision "
                "may ratify a genuine two-axis blueprint for this workspace, at which "
                "point this null becomes a real state the moment that blueprint is "
                "adopted. Until then, the real curve content -- node levels, "
                "thirteen-week changes, slopes, inversion status, curvature, the "
                "real/breakeven decomposition, term premium, and the policy corridor "
                "-- lives in metrics, drivers, and implications instead. See the "
                "headline_unavailable implication for the reader-facing version."
            ),
        },
        "status": "ABSENT",
        "null_reason": "NOT_APPLICABLE",
    }


# --------------------------------------------------------------------------- #
# drivers (bucket reuse, disclosed -- rate_side is a literal fit for the curve
# levels/slopes; balance_sheet carries corridor/curvature/decomposition reads
# that are NOT a balance sheet, disclosed per the driver_bucket_naming_note)
# --------------------------------------------------------------------------- #
def _drivers(metrics_by_id: dict) -> dict:
    def _mk(driver_id, label_en, label_zh, owner_field, value, unit, note):
        sign = 0
        mag = None
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            sign = 1 if value > 0 else (-1 if value < 0 else 0)
            mag = abs(value)
        return {
            "driver_id": driver_id, "label": _bil(label_en, label_zh),
            "owner_field": owner_field, "value": value, "unit": unit,
            "impact_sign": sign, "impact_magnitude": mag, "note": note,
            "coverage_state": "PRESENT" if value is not None else "ABSENT",
        }

    rate_side = [
        _mk("us10y_level", "10-year Treasury yield", "10年期国债收益率",
            f"fred.{SERIES_US10Y}", metrics_by_id.get("us10y_level"), "percent",
            "the curve's most-watched single node; literal fit for drivers.rate_side"),
        _mk("us10y_real_level", "10-year real (TIPS) yield", "10年期实际（TIPS）收益率",
            f"fred.{SERIES_US10Y_REAL}", metrics_by_id.get("us10y_real_level"), "percent",
            "higher = more restrictive real financing cost; literal fit"),
        _mk("curve_2s10s_level", "2s10s slope", "2年-10年期利差",
            f"fred.{SERIES_US10Y} - fred.{SERIES_US2Y}", metrics_by_id.get("curve_2s10s_level"), "pct_pts",
            "positive = normal (upward-sloping); negative = inverted; literal fit"),
        _mk("curve_3m10y_level", "3m10y slope", "3个月-10年期利差",
            f"fred.{SERIES_US10Y} - fred.{SERIES_US3M}", metrics_by_id.get("curve_3m10y_level"), "pct_pts",
            "the NY Fed recession-model spread convention; literal fit"),
        _mk("term_premium_10y_level", "10-year term premium", "10年期期限溢价",
            f"fred.{SERIES_TERM_PREMIUM_10Y}", metrics_by_id.get("term_premium_10y_level"), "percent",
            "Kim-Wright model-based decomposition of the 10-year nominal yield; literal fit"),
    ]
    balance_sheet = [
        _mk("corridor_sofr_minus_iorb_bp", "SOFR minus IORB", "SOFR减IORB",
            f"fred.{SERIES_SOFR} - fred.{SERIES_IORB}", metrics_by_id.get("corridor_sofr_minus_iorb_bp"), "bp",
            "bucket reuse: published under drivers.balance_sheet because the contract's "
            "driver bucket pair is fixed as rate_side/balance_sheet and this workspace "
            "has no dedicated corridor/plumbing bucket -- see the "
            "driver_bucket_naming_note implication"),
        _mk("corridor_effr_minus_iorb_bp", "EFFR minus IORB", "EFFR减IORB",
            f"fred.{SERIES_EFFR} - fred.{SERIES_IORB}", metrics_by_id.get("corridor_effr_minus_iorb_bp"), "bp",
            "bucket reuse: see corridor_sofr_minus_iorb_bp's note"),
        _mk("curvature_butterfly_2s5s10s", "2s5s10s butterfly", "2-5-10年期蝶式利差",
            f"2*fred.{SERIES_US5Y} - fred.{SERIES_US2Y} - fred.{SERIES_US10Y}",
            metrics_by_id.get("curvature_butterfly_2s5s10s"), "pct_pts",
            "bucket reuse: see corridor_sofr_minus_iorb_bp's note"),
        _mk("nominal_real_breakeven_residual_10y", "Nominal/real/breakeven residual (10y)",
            "名义/实际/盈亏平衡残差（10年期）",
            f"fred.{SERIES_US10Y} - (fred.{SERIES_US10Y_REAL} + fred.{SERIES_BREAKEVEN_10Y})",
            metrics_by_id.get("nominal_real_breakeven_residual_10y"), "pct_pts",
            "bucket reuse: see corridor_sofr_minus_iorb_bp's note"),
    ]
    return {"rate_side": rate_side, "balance_sheet": balance_sheet}


# --------------------------------------------------------------------------- #
# implications
# --------------------------------------------------------------------------- #
def _implications(metrics_by_id: dict, contradictions: list[dict],
                   worst_freshness: str, coverage_ratio: float) -> list[dict]:
    conf = {
        "data_coverage": _band(coverage_ratio, 0.5, 0.99),
        "source_health": "HIGH" if worst_freshness == "CURRENT" else "LOW",
        "revision_risk": "LOW",
        "method_stability": "HIGH",
        "evidence_breadth": "HIGH",
        "contradiction_state": "PRESENT" if contradictions else "ABSENT",
    }
    items: list[dict] = [{
        "implication_id": "headline_unavailable",
        "text": _bil(
            "This page publishes no dual-axis state and no headline quadrant: the "
            "frozen Market Ontology architecture document defines twelve macro "
            "workspaces, each with its own headline blueprint (or an explicit note "
            "that none exists), and Rates & Curves is not one of the twelve -- it is "
            "a Chairman-authorized expansion added afterward, so no blueprint section "
            "for it exists to fill in or fall short of. This is a design absence, not "
            "a data gap: unlike a workspace whose blueprint exists but cannot be "
            "computed from today's inputs, there is simply no named axis pair here to "
            "attempt. A future architecture revision may ratify a two-axis blueprint "
            "for this workspace, at which point this null becomes a real state the "
            "moment that blueprint is adopted. Until then, the real curve content -- "
            "node levels, slopes, inversion status, the real/breakeven decomposition, "
            "term premium, and the policy corridor -- is published in full as "
            "metrics, drivers, and implications instead of being forced into a "
            "quadrant that has no definition to force it into.",
            "本页不发布双轴状态,也不发布头条象限:已冻结的市场本体架构文档定义了十二个"
            "宏观工作区,每个都有各自的头条蓝图（或明确说明不存在蓝图）,而利率与曲线并非"
            "这十二个之一——它是后续经授权新增的扩展工作区,因此根本不存在可填补或未能"
            "填补的蓝图章节。这是设计层面的缺失,而非数据缺口:与蓝图存在但当前输入无法"
            "计算的工作区不同,这里根本没有可尝试的既定轴对。未来的架构修订版可能会为"
            "本工作区批准一个双轴蓝图,届时这一空值将在该蓝图被采纳的那一刻转为真实状态。"
            "在此之前,真实的曲线内容——节点水平、利差、倒挂状态、名义/实际/盈亏平衡分解、"
            "期限溢价与政策走廊——均以指标、驱动因素与含义的形式完整发布,而非被强行纳入"
            "一个没有定义可供强行纳入的象限。"),
        "evidence_class": "DESCRIPTIVE", "confidence": conf, "horizon": "current",
        "channels": ["rates", "curve"],
        "contradictions": [c["kind"] for c in contradictions],
        "trace_ref": "engine.market_os.macro_workspaces.rates_curves#headline",
    }]

    items.append({
        "implication_id": "seam_decision_disclosure",
        "text": _bil(
            "This workspace reads FRED Treasury-curve and policy-corridor parquets "
            "only. It deliberately takes no input at all from the rates_command "
            "owner artifact, even though that artifact already computes a "
            "market-implied path, an FOMC dot-plot comparison, and a yield-momentum "
            "read: those are Monetary Policy's own projection of that owner "
            "artifact, already published on this suite's Monetary Policy page. "
            "Reading rates_command here too and re-publishing its yield-momentum "
            "leg under a different workspace identity would duplicate an owner "
            "projection another workspace already carries, not add a genuinely new "
            "read. Rates & Curves stays a pure market-curve workspace instead, built "
            "only from the raw FRED series.",
            "本工作区仅读取FRED国债收益率曲线与政策走廊的parquet数据,刻意不读取"
            "rates_command所有者产物的任何输入——尽管该产物已经计算出市场隐含路径、"
            "FOMC点阵图对比与收益率动能读数:这些已经是货币政策工作区对该所有者产物的"
            "自有投影,并已在本套件的货币政策页面发布。若本工作区也读取rates_command"
            "并在另一个工作区身份下重复发布其收益率动能分项,只是重复了另一个工作区"
            "已经承载的所有者投影,而非新增真正的读数。因此利率与曲线工作区保持为纯"
            "市场曲线工作区,仅基于原始FRED序列构建。"),
        "evidence_class": "DESCRIPTIVE", "confidence": conf, "horizon": "current",
        "channels": ["rates"], "contradictions": [], "trace_ref": None,
    })

    c2 = metrics_by_id.get("curve_2s10s_level")
    c3m10 = metrics_by_id.get("curve_3m10y_level")
    c5s30 = metrics_by_id.get("curve_5s30s_level")
    if c2 is not None or c3m10 is not None or c5s30 is not None:
        c2_en = f"2s10s reads {c2:+.2f} percentage points" if c2 is not None else "2s10s is unavailable"
        c3_en = f"3m10y reads {c3m10:+.2f} percentage points" if c3m10 is not None else "3m10y is unavailable"
        c5_en = f"5s30s reads {c5s30:+.2f} percentage points" if c5s30 is not None else "5s30s is unavailable"
        c2_zh = f"2年-10年期利差为{c2:+.2f}个百分点" if c2 is not None else "2年-10年期利差不可得"
        c3_zh = f"3个月-10年期利差为{c3m10:+.2f}个百分点" if c3m10 is not None else "3个月-10年期利差不可得"
        c5_zh = f"5年-30年期利差为{c5s30:+.2f}个百分点" if c5s30 is not None else "5年-30年期利差不可得"
        items.append({
            "implication_id": "curve_shape_read",
            "text": _bil(f"Curve shape: {c2_en}; {c3_en}; {c5_en}.",
                         f"曲线形态：{c2_zh}；{c3_zh}；{c5_zh}。"),
            "evidence_class": "DESCRIPTIVE", "confidence": conf, "horizon": "current",
            "channels": ["rates", "curve"], "contradictions": [], "trace_ref": None,
        })

    run2 = metrics_by_id.get("curve_2s10s_inversion_run_length_bd")
    run3 = metrics_by_id.get("curve_3m10y_inversion_run_length_bd")
    if run2 is not None or run3 is not None or c2 is not None or c3m10 is not None:
        state2_en = "inverted" if (c2 is not None and c2 < 0) else "normal (not inverted)"
        state3_en = "inverted" if (c3m10 is not None and c3m10 < 0) else "normal (not inverted)"
        state2_zh = "倒挂" if (c2 is not None and c2 < 0) else "正常（未倒挂）"
        state3_zh = "倒挂" if (c3m10 is not None and c3m10 < 0) else "正常（未倒挂）"
        run2_en = f", holding that sign for {run2} consecutive shared trading dates" if run2 is not None else ""
        run3_en = f", holding that sign for {run3} consecutive shared trading dates" if run3 is not None else ""
        run2_zh = f"，该方向已持续{run2}个共同交易日" if run2 is not None else ""
        run3_zh = f"，该方向已持续{run3}个共同交易日" if run3 is not None else ""
        items.append({
            "implication_id": "inversion_status_read",
            "text": _bil(
                f"2s10s is currently {state2_en}{run2_en}. 3m10y is currently "
                f"{state3_en}{run3_en}.",
                f"2年-10年期利差目前为{state2_zh}{run2_zh}。"
                f"3个月-10年期利差目前为{state3_zh}{run3_zh}。"),
            "evidence_class": "DESCRIPTIVE", "confidence": conf, "horizon": "current",
            "channels": ["rates", "curve", "recession_signal"], "contradictions": [],
            "trace_ref": None,
        })

    residual = metrics_by_id.get("nominal_real_breakeven_residual_10y")
    items.append({
        "implication_id": "real_breakeven_decomposition_read",
        "text": _bil(
            "The 10-year nominal yield, 10-year real (TIPS) yield, and 10-year "
            "breakeven inflation rate are three separately-interpolated FRED "
            "constant-maturity curves, not three legs of one single calculation -- "
            "so the nominal yield rarely equals the real yield plus the breakeven "
            "exactly, even on the same date. This page publishes the residual "
            "(nominal minus the sum of the other two) as its own read, with a "
            f"{_DECOMPOSITION_RESIDUAL_TOLERANCE_PCT_PTS:g}-percentage-point disclosed "
            "tolerance band sized to that normal interpolation noise" +
            (f"; the current residual reads {residual:+.3f} percentage points."
             if residual is not None else "; the current residual is unavailable."),
            "10年期名义收益率、10年期实际（TIPS）收益率与10年期盈亏平衡通胀率是FRED"
            "三条各自独立插值得出的曲线,而非同一次计算的三个分项——因此即使在同一日期,"
            "名义收益率也很少恰好等于实际收益率加盈亏平衡通胀率之和。本页将残差"
            "（名义减去另外两者之和）作为独立读数发布,并设定"
            f"{_DECOMPOSITION_RESIDUAL_TOLERANCE_PCT_PTS:g}个百分点的披露容差,"
            "以吸收这种正常的跨曲线插值噪声" +
            (f"；当前残差读数为{residual:+.3f}个百分点。" if residual is not None else "；当前残差不可得。")),
        "evidence_class": "DESCRIPTIVE", "confidence": conf, "horizon": "current",
        "channels": ["rates", "inflation"], "contradictions": [c["kind"] for c in contradictions],
        "trace_ref": None,
    })

    tp_level = metrics_by_id.get("term_premium_10y_level")
    tp_chg = metrics_by_id.get("term_premium_10y_change_13w")
    if tp_level is not None or tp_chg is not None:
        tp_en = f"reads {tp_level:.2f}%" if tp_level is not None else "is unavailable"
        chg_en = f", {tp_chg:+.2f} percentage points over the trailing 13 weeks" if tp_chg is not None else ""
        tp_zh = f"读数为{tp_level:.2f}%" if tp_level is not None else "不可得"
        chg_zh = f"，较13周前变化{tp_chg:+.2f}个百分点" if tp_chg is not None else ""
        items.append({
            "implication_id": "term_premium_read",
            "text": _bil(f"The 10-year Kim-Wright term premium {tp_en}{chg_en}.",
                         f"10年期Kim-Wright期限溢价{tp_zh}{chg_zh}。"),
            "evidence_class": "DESCRIPTIVE", "confidence": conf, "horizon": "current",
            "channels": ["rates"], "contradictions": [], "trace_ref": None,
        })

    ei = metrics_by_id.get("corridor_effr_minus_iorb_bp")
    se = metrics_by_id.get("corridor_sofr_minus_effr_bp")
    si = metrics_by_id.get("corridor_sofr_minus_iorb_bp")
    if ei is not None or se is not None or si is not None:
        ei_en = f"EFFR-IORB {ei:+.1f}bp" if ei is not None else "EFFR-IORB unavailable"
        se_en = f"SOFR-EFFR {se:+.1f}bp" if se is not None else "SOFR-EFFR unavailable"
        si_en = f"SOFR-IORB {si:+.1f}bp" if si is not None else "SOFR-IORB unavailable"
        ei_zh = f"EFFR减IORB为{ei:+.1f}个基点" if ei is not None else "EFFR减IORB不可得"
        se_zh = f"SOFR减EFFR为{se:+.1f}个基点" if se is not None else "SOFR减EFFR不可得"
        si_zh = f"SOFR减IORB为{si:+.1f}个基点" if si is not None else "SOFR减IORB不可得"
        items.append({
            "implication_id": "corridor_read",
            "text": _bil(f"Policy corridor spreads: {ei_en}; {se_en}; {si_en}.",
                         f"政策走廊利差：{ei_zh}；{se_zh}；{si_zh}。"),
            "evidence_class": "DESCRIPTIVE", "confidence": conf, "horizon": "current",
            "channels": ["rates", "funding"], "contradictions": [], "trace_ref": None,
        })

    for c in contradictions:
        items.append({
            "implication_id": f"contradiction_{c['kind']}",
            "text": _bil(c["en"], c["zh"]),
            "evidence_class": "DESCRIPTIVE", "confidence": conf, "horizon": "current",
            "channels": ["rates", "inflation"], "contradictions": [c["kind"]],
            "trace_ref": None,
        })

    items.append({
        "implication_id": "same_date_discipline_disclosure",
        "text": _bil(
            "Every spread, curvature, and decomposition read on this page (2s10s, "
            "3m10y, 5s30s, the butterfly, the nominal/real/breakeven decomposition, "
            "and each policy-corridor spread) is computed only from a date common to "
            "every leg it combines, never by pairing each leg's own separately-latest "
            "print. When the latest shared date across a combination's legs lags any "
            "single leg's own newest available print by more than a disclosed "
            "tolerance, this composer refuses that read rather than mixing an older "
            "print from one leg with a newer print from another under one reported "
            "date.",
            "本页所有利差、曲率与分解读数（2年-10年期、3个月-10年期、5年-30年期利差、"
            "蝶式利差,以及名义/实际/盈亏平衡分解、各政策走廊利差）均只依据其所涉及的"
            "每一分项都共有的同一日期计算,绝不将各分项各自的最新日期拼凑在一起。"
            "当某组合中各分项的共同最新日期,相较其中任一分项自身的最新可得读数滞后"
            "超出披露容差时,本组合器会拒绝给出该读数,而不会在同一报告日期下混用"
            "一个分项的旧读数与另一分项的新读数。"),
        "evidence_class": "DESCRIPTIVE", "confidence": conf, "horizon": "current",
        "channels": ["rates"], "contradictions": [], "trace_ref": None,
    })

    items.append({
        "implication_id": "investment_basis_only_disclosure",
        "text": _bil(
            "Every yield node on this page is a constant-maturity, investment "
            "(bond-equivalent) basis FRED series -- the same basis convention this "
            "estate's own yield-curve engine uses for internal consistency. The "
            "discount-basis Treasury bill rate (FRED DTB3) is a different, "
            "structurally lower-reading series on a different basis and is never one "
            "of this workspace's inputs, so it can never be mixed with any node "
            "published here.",
            "本页每一个收益率节点都是FRED发布的固定期限、投资（债券等价）基础国债"
            "收益率序列——与本估值体系自有收益率曲线引擎所用的基础保持内部一致。"
            "贴现基础的国库券利率（FRED DTB3）是另一条结构性读数更低、基础不同的"
            "序列,从未作为本工作区的输入,因此也绝不会与本页发布的任何节点混用。"),
        "evidence_class": "DESCRIPTIVE", "confidence": conf, "horizon": "current",
        "channels": ["rates"], "contradictions": [], "trace_ref": None,
    })

    items.append({
        "implication_id": "driver_bucket_naming_note",
        "text": _bil(
            "The drivers.balance_sheet bucket in this snapshot carries corridor "
            "spreads, the curvature butterfly, and the decomposition residual -- not "
            "a balance sheet. The contract's driver bucket pair is fixed as "
            "rate_side/balance_sheet and this workspace has no dedicated corridor/"
            "plumbing bucket to use, so the naming is cosmetic bucket reuse, "
            "disclosed here rather than left implicit.",
            "本快照中drivers.balance_sheet分组承载的是政策走廊利差、蝶式利差与分解"
            "残差,而非资产负债表。合约的驱动因素分组固定为rate_side/balance_sheet,"
            "本工作区没有独立的走廊/资金面分组可用,因此命名属于用途借用,在此明确"
            "披露而非隐含处理。"),
        "evidence_class": "DESCRIPTIVE", "confidence": conf, "horizon": "current",
        "channels": ["rates"], "contradictions": [], "trace_ref": None,
    })

    return items


# --------------------------------------------------------------------------- #
# scenario / alert contracts (declared vocabulary only -- non-goal: execution)
# --------------------------------------------------------------------------- #
def _scenario_contract() -> dict:
    return {
        "execution_available": False,
        "result_schema": "mastermind.macro_workspace_scenario_result.v1",
        "assumptions": [
            {"assumption_id": "us10y_bp", "label": _bil("10-year yield", "10年期收益率"),
             "unit": "bp", "step": 5.0, "min": -300.0, "max": 300.0,
             "owner_field": f"fred.{SERIES_US10Y}"},
            {"assumption_id": "us2y_bp", "label": _bil("2-year yield", "2年期收益率"),
             "unit": "bp", "step": 5.0, "min": -300.0, "max": 300.0,
             "owner_field": f"fred.{SERIES_US2Y}"},
            {"assumption_id": "curve_2s10s_bp", "label": _bil("2s10s slope", "2年-10年期利差"),
             "unit": "bp", "step": 5.0, "min": -300.0, "max": 300.0, "owner_field": None},
            {"assumption_id": "term_premium_10y_bp", "label": _bil("10-year term premium", "10年期期限溢价"),
             "unit": "bp", "step": 5.0, "min": -200.0, "max": 200.0,
             "owner_field": f"fred.{SERIES_TERM_PREMIUM_10Y}"},
            {"assumption_id": "sofr_iorb_spread_bp", "label": _bil("SOFR-IORB spread", "SOFR减IORB利差"),
             "unit": "bp", "step": 1.0, "min": -50.0, "max": 100.0, "owner_field": None},
        ],
        "status": "PARTIAL",
        "note": (
            "Assumption vocabulary is declared and closed; this composer ships no "
            "scenario execution endpoint (non-goal). curve_2s10s_bp / "
            "sofr_iorb_spread_bp have no owner_field because they are DERIVED reads "
            "(a spread, not a single owner series) -- a future owner-native pure "
            "scenario function produces mastermind.macro_workspace_scenario_result.v1 "
            "with no canonical write."
        ),
    }


def _alert_contract() -> dict:
    return {
        "service_available": False,
        "eligible_conditions": [
            {"condition_id": "curve_inversion_change", "kind": "state_transition",
             "label": _bil("Curve inversion change", "曲线倒挂状态变化"), "params": ["spread_id"]},
            {"condition_id": "curve_level_shock", "kind": "component_shock",
             "label": _bil("Curve level shock", "曲线水平冲击"), "params": ["metric_id", "delta"]},
            {"condition_id": "term_premium_shock", "kind": "component_shock",
             "label": _bil("Term premium shock", "期限溢价冲击"), "params": ["term_premium_10y_level"]},
            {"condition_id": "corridor_spread_shock", "kind": "component_shock",
             "label": _bil("Corridor spread shock", "政策走廊利差冲击"), "params": ["metric_id", "bp"]},
            {"condition_id": "decomposition_disagreement_change", "kind": "contradiction_change",
             "label": _bil("Decomposition disagreement change", "分解分歧变化"), "params": ["kind"]},
            {"condition_id": "source_stale_or_failed", "kind": "source_stale_or_failed",
             "label": _bil("Source stale or failed", "数据源过期或失败"), "params": ["source_id"]},
        ],
        "status": "ABSENT",
        "note": (
            "Eligible condition types are declared; this composer writes no alert "
            "(non-goal). Alerts extend the existing Terminal alert lifecycle later; "
            "a page shows the Alerts tab only once the service can create/list/"
            "evaluate/delete these real conditions."
        ),
    }


# --------------------------------------------------------------------------- #
# sources
# --------------------------------------------------------------------------- #
def _sources(rows: dict, fresh: dict) -> list[dict]:
    def _src(source_id, en, zh, sid, ref_period, fresh_state):
        return {
            "source_id": source_id, "label": _bil(en, zh),
            "owner_ref": f"collectors.fred[{sid}]", "provider": "FRED (Federal Reserve Bank of St. Louis)",
            "reference_period": ref_period, "released_at": None, "first_known_at": None,
            "collected_at": None, "revised_at": None, "correction_state": "unknown",
            "transform": None, "rights_state": "OPEN", "definition_id": None,
            "definition_version": None, "artifact_ref": f"data/fred/{sid}.parquet",
            "freshness": fresh_state,
        }

    out: list[dict] = []
    for _mid, sid, _col, label in _ALL_LEVEL_NODES:
        latest = _latest(rows[sid])
        out.append(_src(sid.lower(), f"{label} ({sid}, via FRED)", f"{label}（{sid}，经FRED）",
                         sid, _iso(latest[0]) if latest else None, fresh[sid]))
    return out


# --------------------------------------------------------------------------- #
# changes / corrections
# --------------------------------------------------------------------------- #
def _changes(current_metrics_by_id: dict, prior_snapshot: Mapping | None) -> dict:
    if prior_snapshot is None:
        return {"comparability": "NO_PRIOR", "prior_generation_id": None,
                "prior_effective_date": None, "prior_method_version": None,
                "deltas": [], "status": "ABSENT", "null_reason": "WARMUP"}
    prior_method = _get(prior_snapshot, "headline", "method_version")
    prior_gen = _get(prior_snapshot, "generation", "generation_id")
    prior_eff = _get(prior_snapshot, "headline", "effective_date")
    if prior_method != METHOD_VERSION:
        return {"comparability": "METHOD_CHANGED", "prior_generation_id": prior_gen,
                "prior_effective_date": prior_eff, "prior_method_version": prior_method,
                "deltas": [], "status": "ABSENT", "null_reason": "COMPUTATION_REFUSED"}
    deltas = []
    for mid in _TRACKED_CHANGE_METRICS:
        cur = current_metrics_by_id.get(mid)
        prev = _metric_value(prior_snapshot, mid)
        delta = None
        if isinstance(cur, (int, float)) and not isinstance(cur, bool) and \
           isinstance(prev, (int, float)) and not isinstance(prev, bool):
            delta = _round(cur - prev, 4)
        deltas.append({"metric_id": mid, "prior_value": prev, "current_value": cur,
                       "delta": delta, "note": "same method version; numeric comparison permitted"})
    return {"comparability": "COMPARABLE", "prior_generation_id": prior_gen,
            "prior_effective_date": prior_eff, "prior_method_version": prior_method,
            "deltas": deltas, "status": "PRESENT", "null_reason": None}


def _corrections(current_metrics_by_id: dict, effective_date, prior_snapshot: Mapping | None) -> dict:
    """Scoped supersession detection over the tracked metric subset (mirrors
    housing.py/national_debt.py's own ``_corrections`` for the full caveat
    about this being a scoped subset, not a persisted vintage ledger)."""
    prior_gen = _get(prior_snapshot, "generation", "generation_id")
    if prior_snapshot is None:
        return {
            "predecessor_generation_id": None, "changed_fingerprints": [],
            "correction_state": "none",
            "note": "First-known snapshot for this owner input; predecessor recorded when a prior accepted print exists.",
        }
    prior_eff = _get(prior_snapshot, "headline", "effective_date")
    if prior_eff != effective_date:
        return {
            "predecessor_generation_id": prior_gen, "changed_fingerprints": [],
            "correction_state": "none",
            "note": "Reference period differs from the predecessor print (a new observation, not a revision of the same period); no correction asserted.",
        }
    changed: list[str] = []
    for mid in _TRACKED_CORRECTION_METRICS:
        cur = current_metrics_by_id.get(mid)
        prev = _metric_value(prior_snapshot, mid)
        if cur != prev:
            digest16 = sha256(f"{mid}:{cur!r}".encode("utf-8")).hexdigest()[:16]
            changed.append(f"{mid}:{mid}:{digest16}")
    if changed:
        return {
            "predecessor_generation_id": prior_gen, "changed_fingerprints": sorted(changed),
            "correction_state": "superseded",
            "note": "Same reference period as the predecessor print, but one or more owner-native metrics changed value: this print supersedes the prior one as a revision.",
        }
    return {
        "predecessor_generation_id": prior_gen, "changed_fingerprints": [],
        "correction_state": "none",
        "note": "Same reference period as the predecessor print; no tracked metric changed value (no-change republication).",
    }
