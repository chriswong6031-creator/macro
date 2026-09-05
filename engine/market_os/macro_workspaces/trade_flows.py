"""Pure composer for the US ``trade_flows`` workspace snapshot (beyond-F01
expansion, Chairman-authorized 2026-09-04 -- the SECOND workspace past the
frozen twelve-workspace Market Ontology architecture set, reaching toward the
reference product's fourteen-workspace taxonomy alongside ``rates_curves``).

Reads FIVE raw, ALREADY-LOADED level series -- all FRED parquet series -- and
projects them into a ``mastermind.macro_workspace_snapshot.v1`` body:

* ``fred_frames`` -- a dict ``{series_id: rows_or_None}`` where ``rows`` is a
  plain Python list of ``(date, value)`` pairs (or longer tuples -- extra
  elements are ignored, mirrors ``housing.py``'s / ``rates_curves.py``'s
  unconsumed-field negative control) read from ``data/fred/<series_id>.parquet``,
  ascending. Exactly FIVE series are consumed (column names per the
  orchestrator's same-commit ``config.yml`` append, ``build.py``'s
  ``_TRADE_FRED_COLUMNS``); any OTHER key in ``fred_frames`` is ignored -- this
  composer never iterates the dict blindly, only ever reads the five series ids
  it names below:

    BOPGSTB -> trade_balance_goods_services  Trade Balance: Goods and Services,
        BoP Basis ($ MILLIONS, SA, monthly, period-start dated; negative =
        deficit; released by Census/BEA's joint FT-900 report)
    BOPTEXP -> exports_goods_services  Exports of Goods and Services, BoP Basis
        ($M SA monthly, period-start dated, FT-900)
    BOPTIMP -> imports_goods_services  Imports of Goods and Services, BoP Basis
        ($M SA monthly, period-start dated, FT-900)
    IR -> import_price_index  Import Price Index, All Commodities (index, NSA,
        monthly, period-start dated, BLS)
    IQ -> export_price_index  Export Price Index, All Commodities (index, NSA,
        monthly, period-start dated, BLS)

DISK TRUTH TODAY (2026-09-04, verified via a live glob during authoring, no
shell): NONE of the five parquets exist -- ``data/fred/BOPGSTB.parquet``,
``BOPTEXP.parquet``, ``BOPTIMP.parquet``, ``IR.parquet``, ``IQ.parquet`` are
all absent, and ``data/china_trade_detail/`` (a different owner's lane, see
below) does not exist either. This is the EXTREME case of
``consumer_payments.py``'s self-heal pattern: where Consumer & Payments ships
with two of nine series already collected, Trade Flows ships with ZERO of five
collected -- every frame is ``None`` on the real first build. The
orchestrator's ``config.yml`` ``fred.series.trade_flows:`` group (this exact
five-id/column map) lands in the SAME commit as this composer; the nightly
KEYLESS collector materializes the five parquets within a day. Every derived
read below is a pure function of whatever rows are handed in -- there is no
hardcoded "still early" branch anywhere in this module, so the snapshot
self-heals the instant real rows appear, exactly like every other typed-absent
leg in this estate.

REGISTRY / SCHEMA DEPENDENCY (disclosed, verified during authoring, mirrors
``rates_curves.py``'s own JUDGMENT CALL 13): ``engine.market_os.macro_workspaces
.registry.WORKSPACE_IDS`` already lists ``"trade_flows"`` (the 2026-09-04
expansion append, immediately after ``"rates_curves"``), and
``contracts/market_os/macro_workspace_snapshot.v1.schema.json``'s own
``$defs.workspaceId`` enum ALSO already includes ``"trade_flows"`` -- checked
directly against the committed schema file at authoring time, not assumed --
so ``contract.validate()`` accepts a real snapshot from this composer with no
companion schema PR needed. ``engine.market_os.macro_workspaces.build.py`` is
ALREADY wired end-to-end for this workspace: it imports ``trade_flows``,
routes ``workspace_id == "trade_flows"`` to ``trade_flows.compose(
trade_fred_frames, built_at=..., prior_snapshot=..., code_version=...)``, and
its own ``_TRADE_FRED_COLUMNS`` dict already matches the five ids/columns
above verbatim -- this composer's ``compose()`` signature was cross-checked
against that live call site, not merely against the hand-off spec. What
``registry.py`` does NOT yet carry is a dedicated ``REGISTRY["trade_flows"]``
entry (title/subtitle/producer/required_components) -- it falls through to
that module's own ``_NOT_BUILT`` default, so ``registry.built_ids()`` will not
route ``build_all()`` to this composer until that entry is added. Adding it is
out of scope for this composer (a write-only, two-file mandate); the
recommended entry is returned as part of this hand-off instead of silently
added here.

REQUIRED-ONLY, NO OPTIONAL SPLIT (JUDGMENT CALL 1 -- a deliberate departure
from ``consumer_payments.py``'s 2-required/7-optional split and
``rates_curves.py``'s 14-required/5-optional split): all FIVE series are
REQUIRED. With zero series collected today, an honest first build reads
``availability.state = SOURCE_FAILED`` and ``coverage_ratio = 0.0`` across the
board -- this is the intended, designed signal for a workspace whose entire
composable core is still pending collection, not a failure state to soften
with an optional-legs escape hatch the way Consumer's seven pending legs (out
of nine) were kept optional because two OTHER legs were already live.

SA / NSA NEVER-MIX LAW (JUDGMENT CALL 2): ``BOPGSTB``/``BOPTEXP``/``BOPTIMP``
are seasonally adjusted (SA) dollar flows, in USD MILLIONS; ``IR``/``IQ`` are
NOT seasonally adjusted (NSA) price indexes. ``terms_of_trade_proxy`` (IQ/IR)
combines the two NSA series only -- clean, but disclosed explicitly since it
is the one non-obvious same-basis pairing on this page. Every OTHER derived
read (``export_import_coverage_ratio``, ``trade_balance_share_of_flows_pct``,
``trade_balance_identity_residual``) combines only the three SA dollar-flow
series. Verified by construction: grep every ``_pair_value``/``_triple_value``
call below -- none ever crosses the SA/NSA boundary.

$M UNIT DISCIPLINE (JUDGMENT CALL 3): every dollar-flow metric is published in
USD MILLIONS (``usd_millions_sa``), FRED's own native scale for
BOPGSTB/BOPTEXP/BOPTIMP, and is NEVER rescaled to $bn (unlike, e.g.,
``consumer_payments.py``'s G.19 series, which are natively $bn) -- a scale
this composer never mixes with any $bn read from another workspace.

TRADE-BALANCE YOY IS A LEVEL CHANGE, NEVER A PERCENT (JUDGMENT CALL 4):
``trade_balance_yoy_change`` is the level DIFFERENCE (current minus year-ago),
in $M, never a percent-change. BOPGSTB crosses zero (a trade balance can flip
from deficit to surplus, and frequently sits near zero relative to its own
swings), so a percent YoY is mathematically unstable near a zero or
sign-flipping denominator. Every OTHER level series here (exports, imports,
both price indexes) never crosses zero in practice, so those legitimately use
a genuine percent YoY instead.

3-MONTH AVERAGE IS WINDOW-BASED, NEVER "THE LAST THREE ROWS BLINDLY"
(JUDGMENT CALL 5): ``trade_balance_avg_3m`` requires at least THREE
observations inside a disclosed ``[latest_date - 65 days, latest_date]``
window before publishing an average (65d = ~61d for three consecutive
30-31-day months + 4d slack for month-length variance), refusing
``INSUFFICIENT_HISTORY`` otherwise. A window-based floor keeps a collection
gap from silently reaching back across a large outage to stitch three
non-consecutive prints together under one "3-month average" label.

SAME-DATE DISCIPLINE, GENERALIZED TO MONTHLY CADENCE (JUDGMENT CALL 6,
``rates_curves.py`` precedent): ``export_import_coverage_ratio``,
``terms_of_trade_proxy``, ``trade_balance_share_of_flows_pct``, and
``trade_balance_identity_residual`` are each computed only from the LATEST
date common to every leg they combine, refusing (``COMPUTATION_REFUSED``)
when that shared date lags any leg's own newest print by more than the
disclosed ``_SAME_DATE_STALENESS_BOUND_DAYS`` (20 -- reused from
``housing.py``/``consumer_payments.py``'s own monthly lookback-slack constant,
since these are MONTHLY, not daily, series; ``rates_curves.py``'s 5-day daily
bound would be far too tight here and would spuriously refuse a perfectly
healthy monthly same-month pairing).

ESTATE PROPAGATION LAW (JUDGMENT CALL 7, housing/consumer_payments/
rates_curves precedent): an absent leg in any paired/triple read propagates
``SOURCE_FAILED`` -- the read failed because a source failed.
``COMPUTATION_REFUSED`` is reserved for legs that are ALL present but share no
sufficiently fresh common date (the same-date-discipline law above).

THE ONE CONTRADICTION THIS COMPOSER SHIPS (JUDGMENT CALL 8):
``trade_balance_identity_residual`` (``BOPGSTB`` minus (``BOPTEXP`` minus
``BOPTIMP``)) is a genuine, defensible internal-consistency check, NOT the
dollar-flows-vs-price-indexes divergence the hand-off's own domain brief
raised and this composer REJECTS as a contradiction: nominal imports rising
while import prices fall sharply is a real economic INSIGHT (a real-volume
surge), never a data disagreement, and forcing it into ``contradiction`` would
mislabel a genuine signal as a data-quality problem -- so this composer emits
NO detector for that pattern (it is surfaced, when both legs are present, as
a plain descriptive implication instead, never as ``contradiction.present``).
The identity residual is different in kind from ``rates_curves.py``'s own
nominal/real/breakeven residual (three SEPARATELY-interpolated curves, where
a nonzero residual is NORMAL): ``BOPGSTB`` is DEFINED as ``BOPTEXP`` minus
``BOPTIMP`` by the very same BEA/Census FT-900 release, so a real disagreement
here -- beyond the disclosed ``_IDENTITY_RESIDUAL_TOLERANCE_USD_M`` ($100M)
band that absorbs ordinary rounding -- signals an actual per-series
revision-vintage mismatch between FRED's three independently-refreshed
series, a genuine owner-native data-integrity read.

NOT_COVERED REMAINDER, FOUR NAMED LANES, NEVER ESTIMATED (JUDGMENT CALL 9):
* Bilateral / country-level trade detail: a China-side GACC (Customs) partner-
  country breakdown collector is real and nightly-wired in this estate
  (``collectors/china_trade_detail.py`` -> ``data/china_trade_detail/``), but
  its own docstring frames it as "CONTEXT / DISPLAY TIER ONLY. Nothing here is
  scored, ranked, sized or promoted" for its owning surface (the CN board) --
  reusing its partner-country breakdown under a DIFFERENT workspace's
  projection is a cross-workspace scope/rights decision this composer has no
  standing to make on its own authority. Typed ``NOT_COVERED``, not silently
  read.
* Petroleum-specific trade flows: EIA weekly crude oil import/export series
  (``config.yml``'s ``eia:`` group, ``WCEIMUS2``/``WCREXUS2``, surfaced as a
  SUPPLY read on the energy/oil page's Commodity Vector) exist in-tree but
  belong to the energy-plumbing owner's lane, not this one. Typed
  ``NOT_COVERED``.
* Customs / tariff receipts: no collector for this release exists anywhere in
  this estate. Typed ``NOT_COVERED``.
* Services-only or goods-only trade detail: ``BOPGSTB``/``BOPTEXP``/
  ``BOPTIMP`` are the COMBINED goods-AND-services read; no finer goods-only or
  services-only breakdown is collected. Typed ``NOT_COVERED``.
None of the four is ever estimated from a different series, and none is
``RIGHTS_BLOCKED`` (unlike ``consumer_payments.py``'s card-network panels) --
each is a genuine scope gap (no collector wired for THIS workspace's
projection), never a rights barrier.

HEADLINE: UNCONDITIONALLY NOT_APPLICABLE (JUDGMENT CALL 10, ``rates_curves.py``
/ ``monetary_policy.py`` precedent, NOT ``consumer_payments.py``'s/
``housing.py``'s data-refusal precedent): Trade Flows is a Chairman-authorized
expansion workspace with no architecture-document section defining a headline
blueprint at all -- there is no named axis pair here to attempt, computable or
not, so ``axes.items`` stays ``[]`` (schema-legal) and the null is a DESIGN
ABSENCE, never a per-build ``COMPUTATION_REFUSED``. This holds regardless of
data completeness: even a fully self-healed, all-``CURRENT`` build still
carries the same ``NOT_APPLICABLE`` null.

ONE-MONTH-VECTOR / NEAREST-BOUNDARY: THE SIMPLER FIXED PATTERN (JUDGMENT
CALL 11, a disclosed departure from ``consumer_payments.py``'s "refusal
outranks warmup" precedent): both ``nearest_boundary.null_reason`` and
``one_month_vector.null_reason`` unconditionally carry the SAME
``NOT_APPLICABLE`` value as ``headline.null_reason`` itself, exactly
mirroring ``rates_curves.py``'s own JUDGMENT CALL 14. Consumer's more complex
precedent exists ONLY for a workspace whose headline quadrant IS genuinely
computable once its pending legs populate (so a real "computable-but-no-
prior-print" case exists to distinguish from a data-refused case); Trade
Flows, like Rates & Curves, never has a computable quadrant at all, so there
is no such case for the more complex precedent to apply to here.

DRIVERS BUCKET REUSE (JUDGMENT CALL 12, disclosed, mirrors every sibling):
the contract's ``drivers`` block is closed to exactly ``{rate_side,
balance_sheet}``. ``balance_sheet`` carries the dollar-flow legs (trade
balance, exports, imports, the coverage ratio, the balance-share-of-flows
read, the identity residual) -- a loose thematic fit (these ARE about a
"balance"), not a literal monetary balance sheet. ``rate_side`` carries the
two price-index legs and the terms-of-trade proxy -- pure bucket-naming
convenience, never a claim these are policy rates. Disclosed in the
``driver_bucket_naming_note`` implication, never left implicit.

PIT / REVISION LAW (JUDGMENT CALL 13): no ALFRED point-in-time vintage capture
exists for any of the five series today. Every level and derived read below
is therefore the LATEST-REVISED value as currently stored, never an "as it
was known then" reconstruction (housing/consumer_payments/rates_curves
precedent) -- FT-900 dollar flows and BLS price indexes are both revised for
months after first release.

UNVERIFIED INDEX BASE YEAR (JUDGMENT CALL 14, mirrors
``consumer_payments.py``'s DSPIC96 judgment call 15): ``IR``/``IQ``'s index
base year (BLS conventionally bases these near 2000=100, but this composer
cannot execute code to inspect the parquet's own embedded metadata in this
authoring environment -- no shell) is disclosed generically ("index, NSA,
base year per BLS/FRED series metadata") in each metric's own transformation
text, never asserted as a specific unverified base year.

FRESHNESS (worst-case-age law, hand-traced against "a maximally-fresh print
must read CURRENT throughout the publication cycle" -- the same law every
sibling composer derives its cadence constants from):
* BOPGSTB/BOPTEXP/BOPTIMP: the Census/BEA FT-900 report is released
  approximately 35-40 days after the reference MONTH END. FRED dates the
  series period-START, so the worst case (a 31-day reference month, released
  at the 40-day-after-month-end edge of the window) puts the lag-at-release at
  31 + 40 = 71 days from the period-start date; add one further ~31-day
  release cycle (the newest-possible age right before the NEXT month's print
  supersedes it) -> cadence 71 + 31 = 102 days. Grace 17 days (the Census-
  family shutdown-precedent grace this estate already uses for
  HOUST/PERMIT/RSAFS).
* IR/IQ: BLS releases these import/export price indexes around the second
  week of the following month, worst case landing as late as day ~18 of M+1;
  from a period-start date that is a lag of 31 (reference month length) + 18
  = 49 days at release; add one further ~31-day cycle -> cadence
  49 + 31 = 80 days. Grace 15 days (the construction-class grace this estate
  already uses for Case-Shiller / UMCSENT-style monthly releases).
Both hand-checks satisfy the maximally-fresh-print law: a print sitting at
exactly its cadence's age (the newest-possible print, one instant before the
next release supersedes it) reads ``CURRENT``, never falsely ``STALE_SOURCE``.

NO rank/gate/size/trade authority. NO LLM-originated facts. Descriptive
ceiling only. Depends only on the standard library (no pandas import here --
the caller supplies plain rows). The composer NEVER reads a wall clock:
``built_at`` is supplied by the caller, and every staleness/age/lookback/
same-date check is a pure function of ``built_at`` and the given rows, so an
identical set of owner inputs always yields an identical snapshot body.
"""
from __future__ import annotations

import datetime as _dt
from hashlib import sha256
from typing import Any, Mapping

METHOD_VERSION = "trade_flows.compose.v1"
DEFINITION_VERSION = "1.0.0"
PRODUCER = "engine.market_os.macro_workspaces.trade_flows"
WORKSPACE_ID = "trade_flows"

# The five composable-core FRED series. Column names per the orchestrator's
# same-commit config.yml append / build.py's _TRADE_FRED_COLUMNS (verbatim).
SERIES_TRADE_BALANCE = "BOPGSTB"      # column: trade_balance_goods_services (monthly, $M SA)
SERIES_EXPORTS = "BOPTEXP"            # column: exports_goods_services (monthly, $M SA)
SERIES_IMPORTS = "BOPTIMP"            # column: imports_goods_services (monthly, $M SA)
SERIES_IMPORT_PRICE = "IR"            # column: import_price_index (monthly, index NSA)
SERIES_EXPORT_PRICE = "IQ"            # column: export_price_index (monthly, index NSA)

_ALL_SERIES = (SERIES_TRADE_BALANCE, SERIES_EXPORTS, SERIES_IMPORTS,
               SERIES_IMPORT_PRICE, SERIES_EXPORT_PRICE)

# SA dollar-flow series vs NSA price-index series (judgment call 2). Verified
# by construction: grep every _pair_value / _triple_value call below -- the
# only cross-series read that touches _PRICE_SERIES (terms_of_trade_proxy)
# touches BOTH of its members and none of _DOLLAR_SERIES; every other
# cross-series read touches only _DOLLAR_SERIES members.
_DOLLAR_SERIES = frozenset({SERIES_TRADE_BALANCE, SERIES_EXPORTS, SERIES_IMPORTS})
_PRICE_SERIES = frozenset({SERIES_IMPORT_PRICE, SERIES_EXPORT_PRICE})

# Cadence / grace-window laws (disclosed constants -- see module docstring's
# FRESHNESS hand-trace).
_TRADE_DOLLAR_CADENCE_DAYS = 102
_TRADE_DOLLAR_GRACE_DAYS = 17
_TRADE_PRICE_CADENCE_DAYS = 80
_TRADE_PRICE_GRACE_DAYS = 15

# Derived-read lookback windows (disclosed constants, never silently
# invented). The monthly slack reuses housing.py's / consumer_payments.py's
# own disclosed constant verbatim (judgment call 6).
_YOY_DAYS = 365
_MONTHLY_LOOKBACK_SLACK_DAYS = 20
_THREE_MONTH_AVG_WINDOW_DAYS = 65
_THREE_MONTH_AVG_MIN_COUNT = 3

# Same-date discipline tolerance, generalized to monthly cadence (judgment
# call 6 -- NOT rates_curves.py's 5-day daily bound).
_SAME_DATE_STALENESS_BOUND_DAYS = 20

# Trade-balance identity-residual tolerance, USD MILLIONS (judgment call 8).
_IDENTITY_RESIDUAL_TOLERANCE_USD_M = 100.0

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
    "trade_balance_level", "exports_level", "imports_level",
    "export_import_coverage_ratio",
)
_TRACKED_CORRECTION_METRICS = (
    "trade_balance_level", "trade_balance_avg_3m", "trade_balance_yoy_change",
    "exports_level", "exports_yoy", "imports_level", "imports_yoy",
    "export_import_coverage_ratio", "import_price_index_level",
    "import_price_index_yoy", "export_price_index_level",
    "export_price_index_yoy", "terms_of_trade_proxy",
    "trade_balance_share_of_flows_pct", "trade_balance_identity_residual",
)

_UNVERIFIED_INDEX_BASE_NOTE = (
    " (index, NSA, base year per BLS/FRED series metadata -- NOT verified in "
    "this authoring environment; see judgment call 14)"
)


# --------------------------------------------------------------------------- #
# small pure helpers (deliberately self-contained -- no cross-import from any
# sibling composer, mirrors rates_curves.py / housing.py's own shape)
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
    """Shared release-cadence law (see module docstring's FRESHNESS
    hand-trace). ``value_present=False`` (series wholly absent) always reads
    ``SOURCE_FAILED``; an ``asof`` in the future relative to ``built_at`` (a
    clock inversion) also reads ``SOURCE_FAILED`` rather than a nonsensical
    ``CURRENT``."""
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
# raw-row handling (mirrors rates_curves.py / housing.py exactly)
# --------------------------------------------------------------------------- #
def _clean_rows(rows: Any) -> list[tuple[_dt.date, float]]:
    """Defensively normalize a caller-supplied row list: accept ``(date, value)``
    pairs or longer tuples (extra elements ignored -- an unconsumed-field
    negative control for the digest tests), drop unparseable dates /
    non-numeric values, de-duplicate a repeated date keeping the LAST-listed
    occurrence, and sort ascending by date. Never raises on malformed input --
    a bad row is dropped, never fabricated into a fake reading."""
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
    masquerading as a fresh YoY comparison point."""
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
# same-date discipline (judgment call 6, rates_curves.py precedent
# generalized to monthly cadence): combining two or three INDEPENDENTLY-
# clocked series into one point-in-time read.
# --------------------------------------------------------------------------- #
def _shared_reading(rows_list: list[list[tuple[_dt.date, float]]],
                     bound_days: int) -> tuple[_dt.date, tuple[float, ...]] | None:
    """Locate the LATEST date common to every given (non-empty) row list, then
    refuse (``None``) unless that shared date sits within ``bound_days`` of
    EVERY list's own separately-latest print."""
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


def _pair_value(a_rows, b_rows, a_fresh: str, b_fresh: str,
                 bound_days: int = _SAME_DATE_STALENESS_BOUND_DAYS
                 ) -> tuple[_dt.date | None, float | None, float | None, str, str | None]:
    """Two-leg same-date-disciplined pair read. Returns
    ``(shared_date, a_value, b_value, freshness, null_reason)``. Estate
    propagation law (judgment call 7): ANY absent leg propagates
    ``SOURCE_FAILED``; ``COMPUTATION_REFUSED`` is reserved for legs that are
    all PRESENT but share no sufficiently fresh common date."""
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
    """Three-leg same-date-disciplined read (trade-balance / exports / imports).
    Same estate propagation law as ``_pair_value``."""
    present = (bool(a_rows), bool(b_rows), bool(c_rows))
    if all(present):
        fresh = _worst_freshness([a_fresh, b_fresh, c_fresh])
        shared = _shared_reading([a_rows, b_rows, c_rows], bound_days)
        if shared is None:
            return None, (None, None, None), fresh, "COMPUTATION_REFUSED"
        d, vals = shared
        return d, vals, fresh, None
    return None, (None, None, None), "SOURCE_FAILED", "SOURCE_FAILED"


# --------------------------------------------------------------------------- #
# derived-read primitives
# --------------------------------------------------------------------------- #
def _pct_change(cur: float | None, prior: float | None) -> float | None:
    if cur is None or prior is None or prior == 0:
        return None
    return _round((cur / prior - 1.0) * 100.0, 4)


def _level_diff(a: float | None, b: float | None) -> float | None:
    if a is None or b is None:
        return None
    return _round(a - b, 4)


def _yoy_pct(rows: list[tuple[_dt.date, float]]) -> float | None:
    latest = _latest(rows)
    if latest is None:
        return None
    prior = _value_before_or_at(rows, latest[0] - _dt.timedelta(days=_YOY_DAYS),
                                 _MONTHLY_LOOKBACK_SLACK_DAYS)
    if prior is None:
        return None
    return _pct_change(latest[1], prior[1])


def _yoy_level_change(rows: list[tuple[_dt.date, float]]) -> float | None:
    """Judgment call 4: a level DIFFERENCE, never a percent -- BOPGSTB crosses
    zero, so a percent YoY would be unstable near a zero/sign-flipping
    denominator."""
    latest = _latest(rows)
    if latest is None:
        return None
    prior = _value_before_or_at(rows, latest[0] - _dt.timedelta(days=_YOY_DAYS),
                                 _MONTHLY_LOOKBACK_SLACK_DAYS)
    if prior is None:
        return None
    return _level_diff(latest[1], prior[1])


def _trailing_avg(rows: list[tuple[_dt.date, float]], min_count: int,
                   window_days: int) -> float | None:
    """Judgment call 5: a WINDOW-based trailing average (never "the last N
    rows blindly"). Requires at least ``min_count`` observations inside
    ``[latest_date - window_days, latest_date]``; refuses otherwise."""
    if not rows:
        return None
    latest_date = rows[-1][0]
    window_start = latest_date - _dt.timedelta(days=window_days)
    vals = [v for d, v in rows if window_start <= d <= latest_date]
    if len(vals) < min_count:
        return None
    return _round(sum(vals) / len(vals), 4)


# --------------------------------------------------------------------------- #
# metric / component builders (mirror rates_curves.py / consumer_payments.py)
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
        "rights_state": "RIGHTS_BLOCKED" if freshness == "RIGHTS_BLOCKED" else "OPEN",
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
def compose(fred_frames: Mapping[str, Any] | None, *, built_at: str,
            prior_snapshot: Mapping[str, Any] | None = None,
            code_version: str | None = None) -> dict:
    """Project ``fred_frames`` (dict of raw FRED level rows, see module
    docstring) into an UNSEALED snapshot body. The builder seals it via
    ``contract.finalize``."""
    ff = fred_frames if isinstance(fred_frames, Mapping) else {}

    rows: dict[str, list[tuple[_dt.date, float]]] = {
        sid: _clean_rows(ff.get(sid)) for sid in _ALL_SERIES
    }
    fresh: dict[str, str] = {}
    for sid in _ALL_SERIES:
        cadence, grace = ((_TRADE_DOLLAR_CADENCE_DAYS, _TRADE_DOLLAR_GRACE_DAYS)
                           if sid in _DOLLAR_SERIES
                           else (_TRADE_PRICE_CADENCE_DAYS, _TRADE_PRICE_GRACE_DAYS))
        latest = _latest(rows[sid])
        fresh[sid] = _cadence_freshness(built_at, latest[0] if latest else None,
                                         cadence, grace, bool(latest))

    derived = _derive(rows, fresh)
    contradictions = _detect_contradiction(derived["trade_balance_identity_residual"],
                                            derived["triple_shared_date"])
    fired_kinds = {c["kind"] for c in contradictions}

    metrics = _metrics(rows, fresh, derived, fired_kinds)
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
    for sid in _ALL_SERIES:
        latest = _latest(rows[sid])
        if latest:
            dates.append(latest[0])
    effective_date = _iso(max(dates)) if dates else None

    headline = _headline(effective_date, prior_snapshot)
    changes = _changes(metrics_by_id, prior_snapshot)

    snapshot = {
        "schema": {"contract": "mastermind.macro_workspace_snapshot.v1", "version": "1.0.0"},
        "workspace": {
            "id": WORKSPACE_ID,
            "title": _bil("Trade Flows", "贸易流动"),
            "subtitle": _bil("Goods & services dollar flows x import/export price indexes",
                              "货物与服务美元贸易流量 × 进出口价格指数"),
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
# derived reads (compute-then-detect order, mirrors rates_curves.py)
# --------------------------------------------------------------------------- #
def _derive(rows: dict, fresh: dict) -> dict:
    tb, ex, im = rows[SERIES_TRADE_BALANCE], rows[SERIES_EXPORTS], rows[SERIES_IMPORTS]
    ir, iq = rows[SERIES_IMPORT_PRICE], rows[SERIES_EXPORT_PRICE]
    tb_f, ex_f, im_f = fresh[SERIES_TRADE_BALANCE], fresh[SERIES_EXPORTS], fresh[SERIES_IMPORTS]
    ir_f, iq_f = fresh[SERIES_IMPORT_PRICE], fresh[SERIES_EXPORT_PRICE]

    d: dict[str, Any] = {}
    d["trade_balance_avg_3m"] = _trailing_avg(tb, _THREE_MONTH_AVG_MIN_COUNT,
                                               _THREE_MONTH_AVG_WINDOW_DAYS)
    d["trade_balance_yoy_change"] = _yoy_level_change(tb)
    d["exports_yoy"] = _yoy_pct(ex)
    d["imports_yoy"] = _yoy_pct(im)
    d["import_price_index_yoy"] = _yoy_pct(ir)
    d["export_price_index_yoy"] = _yoy_pct(iq)

    # -- export/import coverage ratio (pair, both SA dollar-flow legs) -------
    (d["date_coverage"], d["v_exports_cov"], d["v_imports_cov"],
     d["fresh_coverage"], d["null_coverage"]) = _pair_value(ex, im, ex_f, im_f)
    if d["null_coverage"] is None and d["v_imports_cov"]:
        d["export_import_coverage_ratio"] = _round(d["v_exports_cov"] / d["v_imports_cov"], 4)
    else:
        d["export_import_coverage_ratio"] = None
        if d["null_coverage"] is None:
            # both legs present, shared date found, but imports reads exactly
            # zero -- a present-but-unusable division, COMPUTATION_REFUSED
            # (never a fabricated infinite/undefined ratio).
            d["null_coverage"] = "COMPUTATION_REFUSED"

    # -- terms-of-trade proxy (pair, both NSA price-index legs) --------------
    (d["date_tot"], d["v_iq_tot"], d["v_ir_tot"],
     d["fresh_tot"], d["null_tot"]) = _pair_value(iq, ir, iq_f, ir_f)
    if d["null_tot"] is None and d["v_ir_tot"]:
        d["terms_of_trade_proxy"] = _round(d["v_iq_tot"] / d["v_ir_tot"], 4)
    else:
        d["terms_of_trade_proxy"] = None
        if d["null_tot"] is None:
            d["null_tot"] = "COMPUTATION_REFUSED"

    # -- triple leg: trade balance / exports / imports -----------------------
    # feeds BOTH trade_balance_share_of_flows_pct and the one contradiction
    # this composer ships (trade_balance_identity_residual, judgment call 8).
    (d["date_triple"], (d["v_tb3"], d["v_ex3"], d["v_im3"]),
     d["fresh_triple"], d["null_triple"]) = _triple_value(tb, ex, im, tb_f, ex_f, im_f)
    d["triple_shared_date"] = d["date_triple"]
    if d["null_triple"] is None:
        denom = d["v_ex3"] + d["v_im3"]
        if denom:
            d["trade_balance_share_of_flows_pct"] = _round((d["v_tb3"] / denom) * 100.0, 4)
            d["null_share"] = None
        else:
            d["trade_balance_share_of_flows_pct"] = None
            d["null_share"] = "COMPUTATION_REFUSED"
        d["trade_balance_identity_residual"] = _round(
            d["v_tb3"] - (d["v_ex3"] - d["v_im3"]), 4)
        d["null_identity"] = None
    else:
        d["trade_balance_share_of_flows_pct"] = None
        d["null_share"] = d["null_triple"]
        d["trade_balance_identity_residual"] = None
        d["null_identity"] = d["null_triple"]

    return d


# --------------------------------------------------------------------------- #
# contradiction detection (judgment call 8 -- the ONE detector this composer
# ships; the dollar-flows-vs-price-index divergence is deliberately NOT a
# detector here, see module docstring)
# --------------------------------------------------------------------------- #
def _detect_contradiction(residual: float | None, shared_date: _dt.date | None) -> list[dict]:
    """``BOPGSTB`` minus (``BOPTEXP`` minus ``BOPTIMP``), beyond the disclosed
    tolerance, on a genuine shared date -- a real per-series revision-vintage
    mismatch across three FRED series that are DEFINED to satisfy this
    identity from the same underlying BEA/Census release. Silent whenever the
    residual is absent or inside the disclosed band -- never forced."""
    if residual is None:
        return []
    if abs(residual) <= _IDENTITY_RESIDUAL_TOLERANCE_USD_M:
        return []
    direction_en = "above" if residual > 0 else "below"
    direction_zh = "高于" if residual > 0 else "低于"
    date_en = f" on {shared_date.isoformat()}" if shared_date is not None else ""
    date_zh = f"（{shared_date.isoformat()}）" if shared_date is not None else ""
    return [{
        "kind": "trade_balance_identity_disagreement",
        "en": (f"The published trade balance reads {residual:+.1f} USD million "
               f"{direction_en} what exports minus imports computes to{date_en} -- "
               "beyond this page's disclosed rounding tolerance, so FRED's three "
               "separately-refreshed trade series (balance, exports, imports) are "
               "disagreeing with an identity the same underlying BEA/Census release "
               "defines them to satisfy exactly, most likely a per-series "
               "revision-vintage mismatch rather than a modeling artifact."),
        "zh": (f"已发布的贸易差额读数与出口减进口的计算结果相差{residual:+.1f}百万美元"
               f"，方向为{direction_zh}{date_zh}——超出本页披露的四舍五入容差，说明FRED"
               "三条各自独立刷新的贸易序列（差额、出口、进口）之间的分歧，已超出同一份"
               "BEA/海关联合发布本应精确满足的恒等式所允许的范围，这很可能是各序列"
               "修订版本不一致所致，而非建模误差。"),
        "components": ["trade_balance_identity_residual"],
    }]


# --------------------------------------------------------------------------- #
# availability (judgment call 1: ALL FIVE required, no optional split)
# --------------------------------------------------------------------------- #
def _required_availability(rows: dict, fresh: dict) -> tuple[list[dict], list[dict]]:
    specs = [
        ("trade_balance", "Trade balance (goods & services)", "贸易差额（货物与服务）",
         rows[SERIES_TRADE_BALANCE], fresh[SERIES_TRADE_BALANCE]),
        ("exports", "Exports (goods & services)", "出口（货物与服务）",
         rows[SERIES_EXPORTS], fresh[SERIES_EXPORTS]),
        ("imports", "Imports (goods & services)", "进口（货物与服务）",
         rows[SERIES_IMPORTS], fresh[SERIES_IMPORTS]),
        ("import_price_index", "Import price index", "进口价格指数",
         rows[SERIES_IMPORT_PRICE], fresh[SERIES_IMPORT_PRICE]),
        ("export_price_index", "Export price index", "出口价格指数",
         rows[SERIES_EXPORT_PRICE], fresh[SERIES_EXPORT_PRICE]),
    ]
    required = [_component(cid, en, zh, r, fr, True) for cid, en, zh, r, fr in specs]
    return required, []  # no optional legs -- judgment call 1


# --------------------------------------------------------------------------- #
# metrics
# --------------------------------------------------------------------------- #
def _metrics(rows: dict, fresh: dict, d: dict, fired_kinds: set[str]) -> list[dict]:
    items: list[dict] = []
    tb, ex, im = rows[SERIES_TRADE_BALANCE], rows[SERIES_EXPORTS], rows[SERIES_IMPORTS]
    ir, iq = rows[SERIES_IMPORT_PRICE], rows[SERIES_EXPORT_PRICE]
    tb_f, ex_f, im_f = fresh[SERIES_TRADE_BALANCE], fresh[SERIES_EXPORTS], fresh[SERIES_IMPORTS]
    ir_f, iq_f = fresh[SERIES_IMPORT_PRICE], fresh[SERIES_EXPORT_PRICE]

    # -- trade balance: level + 3m avg + YoY change (level diff, judgment 4) --
    tb_latest = _latest(tb)
    tb_level = tb_latest[1] if tb_latest else None
    tb_date = _iso(tb_latest[0]) if tb_latest else None
    items.append(_metric(
        "trade_balance_level", tb_level, "number", "usd_millions_sa", "level",
        "higher_more_surplus", f"data/fred/{SERIES_TRADE_BALANCE}.parquet",
        f"fred.{SERIES_TRADE_BALANCE}.trade_balance_goods_services", tb_date, tb_f,
        source_refs=["FRED:BOPGSTB"],
        transformation=(
            "Census/BEA FT-900 Trade Balance: Goods and Services, BoP basis, "
            "seasonally adjusted, republished by FRED, in USD MILLIONS (never "
            "rescaled to $bn -- judgment call 3). Negative = deficit. No ALFRED "
            "point-in-time vintage exists for this series; this composer "
            "publishes the current stored (latest-revised) read."
        ),
    ))
    items.append(_metric(
        "trade_balance_avg_3m", d["trade_balance_avg_3m"], "number", "usd_millions_sa",
        "trailing_3m_average", "higher_more_surplus", f"data/fred/{SERIES_TRADE_BALANCE}.parquet",
        "fred.BOPGSTB.trade_balance_goods_services", tb_date, tb_f, source_refs=["FRED:BOPGSTB"],
        transformation=(
            f"Mean of every observation inside a {_THREE_MONTH_AVG_WINDOW_DAYS}-day "
            f"trailing window from the latest print, refused as insufficient history "
            f"below {_THREE_MONTH_AVG_MIN_COUNT} observations in that window -- "
            "never a blind average of 'the last three rows' across a collection gap "
            "(judgment call 5)."
        ),
        null_reason="INSUFFICIENT_HISTORY" if tb_latest else None,
    ))
    items.append(_metric(
        "trade_balance_yoy_change", d["trade_balance_yoy_change"], "number", "usd_millions_sa",
        "yoy_level_change", "positive_is_balance_improving",
        f"data/fred/{SERIES_TRADE_BALANCE}.parquet", "fred.BOPGSTB.trade_balance_goods_services",
        tb_date, tb_f, source_refs=["FRED:BOPGSTB"],
        transformation=(
            "Current level minus the level roughly 12 months prior, in USD MILLIONS "
            "-- a LEVEL difference, never a percent (judgment call 4): the trade "
            "balance crosses zero, so a percent YoY would be unstable near a zero "
            "or sign-flipping denominator."
        ),
        null_reason="INSUFFICIENT_HISTORY" if tb_latest else None,
    ))

    # -- exports: level + YoY --------------------------------------------------
    ex_latest = _latest(ex)
    ex_level = ex_latest[1] if ex_latest else None
    ex_date = _iso(ex_latest[0]) if ex_latest else None
    items.append(_metric(
        "exports_level", ex_level, "number", "usd_millions_sa", "level",
        "higher_more_exports", f"data/fred/{SERIES_EXPORTS}.parquet",
        "fred.BOPTEXP.exports_goods_services", ex_date, ex_f, source_refs=["FRED:BOPTEXP"],
        transformation=(
            "Census/BEA FT-900 Exports of Goods and Services, BoP basis, "
            "seasonally adjusted, republished by FRED, in USD MILLIONS. No ALFRED "
            "point-in-time vintage exists for this series."
        ),
    ))
    items.append(_metric(
        "exports_yoy", d["exports_yoy"], "percent", "percent", "yoy_pct_change",
        "higher_faster_export_growth", f"data/fred/{SERIES_EXPORTS}.parquet",
        "fred.BOPTEXP.exports_goods_services", ex_date, ex_f, source_refs=["FRED:BOPTEXP"],
        transformation="12-month percent change of the same SA series.",
        null_reason="INSUFFICIENT_HISTORY" if ex_latest else None,
    ))

    # -- imports: level + YoY --------------------------------------------------
    im_latest = _latest(im)
    im_level = im_latest[1] if im_latest else None
    im_date = _iso(im_latest[0]) if im_latest else None
    items.append(_metric(
        "imports_level", im_level, "number", "usd_millions_sa", "level",
        "higher_more_imports", f"data/fred/{SERIES_IMPORTS}.parquet",
        "fred.BOPTIMP.imports_goods_services", im_date, im_f, source_refs=["FRED:BOPTIMP"],
        transformation=(
            "Census/BEA FT-900 Imports of Goods and Services, BoP basis, "
            "seasonally adjusted, republished by FRED, in USD MILLIONS. No ALFRED "
            "point-in-time vintage exists for this series."
        ),
    ))
    items.append(_metric(
        "imports_yoy", d["imports_yoy"], "percent", "percent", "yoy_pct_change",
        "higher_faster_import_growth", f"data/fred/{SERIES_IMPORTS}.parquet",
        "fred.BOPTIMP.imports_goods_services", im_date, im_f, source_refs=["FRED:BOPTIMP"],
        transformation="12-month percent change of the same SA series.",
        null_reason="INSUFFICIENT_HISTORY" if im_latest else None,
    ))

    # -- export/import coverage ratio (same-date pair) -------------------------
    items.append(_metric(
        "export_import_coverage_ratio", d["export_import_coverage_ratio"], "ratio", None,
        "same_date_disciplined_ratio", "higher_more_export_coverage_of_imports",
        f"fred.{SERIES_EXPORTS} / fred.{SERIES_IMPORTS}",
        f"fred.{SERIES_EXPORTS} / fred.{SERIES_IMPORTS}", _iso(d["date_coverage"]),
        d["fresh_coverage"], source_refs=["FRED:BOPTEXP", "FRED:BOPTIMP"],
        transformation=(
            "Exports divided by imports (both goods-and-services, SA, USD "
            "millions), at the latest date common to both legs (same-date "
            f"discipline); refused when no such date exists within "
            f"{_SAME_DATE_STALENESS_BOUND_DAYS} days of either leg's own newest "
            "print, rather than mixing an older print from one leg with a newer "
            "print from the other."
        ),
        null_reason=d["null_coverage"],
    ))

    # -- import price index: level + YoY ---------------------------------------
    ir_latest = _latest(ir)
    ir_level = ir_latest[1] if ir_latest else None
    ir_date = _iso(ir_latest[0]) if ir_latest else None
    items.append(_metric(
        "import_price_index_level", ir_level, "index", "index_nsa", "level",
        "higher_more_expensive_imports", f"data/fred/{SERIES_IMPORT_PRICE}.parquet",
        "fred.IR.import_price_index", ir_date, ir_f, source_refs=["FRED:IR"],
        transformation=(
            "BLS Import Price Index, All Commodities, NOT seasonally adjusted, "
            "republished by FRED" + _UNVERIFIED_INDEX_BASE_NOTE +
            ". No ALFRED point-in-time vintage exists for this series."
        ),
    ))
    items.append(_metric(
        "import_price_index_yoy", d["import_price_index_yoy"], "percent", "percent",
        "yoy_pct_change", "higher_faster_import_price_inflation",
        f"data/fred/{SERIES_IMPORT_PRICE}.parquet", "fred.IR.import_price_index",
        ir_date, ir_f, source_refs=["FRED:IR"],
        transformation="12-month percent change of the same NSA index.",
        null_reason="INSUFFICIENT_HISTORY" if ir_latest else None,
    ))

    # -- export price index: level + YoY ---------------------------------------
    iq_latest = _latest(iq)
    iq_level = iq_latest[1] if iq_latest else None
    iq_date = _iso(iq_latest[0]) if iq_latest else None
    items.append(_metric(
        "export_price_index_level", iq_level, "index", "index_nsa", "level",
        "higher_more_expensive_exports", f"data/fred/{SERIES_EXPORT_PRICE}.parquet",
        "fred.IQ.export_price_index", iq_date, iq_f, source_refs=["FRED:IQ"],
        transformation=(
            "BLS Export Price Index, All Commodities, NOT seasonally adjusted, "
            "republished by FRED" + _UNVERIFIED_INDEX_BASE_NOTE +
            ". No ALFRED point-in-time vintage exists for this series."
        ),
    ))
    items.append(_metric(
        "export_price_index_yoy", d["export_price_index_yoy"], "percent", "percent",
        "yoy_pct_change", "higher_faster_export_price_inflation",
        f"data/fred/{SERIES_EXPORT_PRICE}.parquet", "fred.IQ.export_price_index",
        iq_date, iq_f, source_refs=["FRED:IQ"],
        transformation="12-month percent change of the same NSA index.",
        null_reason="INSUFFICIENT_HISTORY" if iq_latest else None,
    ))

    # -- terms-of-trade proxy (same-date pair, both NSA) -----------------------
    items.append(_metric(
        "terms_of_trade_proxy", d["terms_of_trade_proxy"], "ratio", None,
        "same_date_disciplined_ratio", "higher_more_favorable_terms_of_trade",
        f"fred.{SERIES_EXPORT_PRICE} / fred.{SERIES_IMPORT_PRICE}",
        f"fred.{SERIES_EXPORT_PRICE} / fred.{SERIES_IMPORT_PRICE}", _iso(d["date_tot"]),
        d["fresh_tot"], source_refs=["FRED:IQ", "FRED:IR"],
        transformation=(
            "Export price index divided by import price index (both NOT "
            "seasonally adjusted -- a clean NSA-vs-NSA pairing, judgment call 2), "
            "at the latest date common to both legs; refused when no such date "
            f"exists within {_SAME_DATE_STALENESS_BOUND_DAYS} days of either leg's "
            "own newest print. Never combined with any SA dollar-flow series in "
            "the same derived read."
        ),
        null_reason=d["null_tot"],
    ))

    # -- trade balance as a share of total flows (triple-leg) ------------------
    items.append(_metric(
        "trade_balance_share_of_flows_pct", d["trade_balance_share_of_flows_pct"],
        "percent", "percent", "same_date_disciplined_share",
        "higher_more_surplus_relative_to_flow_volume",
        f"fred.{SERIES_TRADE_BALANCE} / (fred.{SERIES_EXPORTS} + fred.{SERIES_IMPORTS})",
        f"fred.{SERIES_TRADE_BALANCE} / (fred.{SERIES_EXPORTS} + fred.{SERIES_IMPORTS})",
        _iso(d["triple_shared_date"]), d["fresh_triple"],
        source_refs=["FRED:BOPGSTB", "FRED:BOPTEXP", "FRED:BOPTIMP"],
        transformation=(
            "Trade balance divided by (exports plus imports), expressed as a "
            "percent, at the latest date common to all three legs (same-date "
            "discipline, three-leg -- judgment call 6); refused when no such "
            "date exists within the disclosed staleness bound, or when the "
            "exports-plus-imports denominator reads exactly zero."
        ),
        null_reason=d["null_share"],
    ))

    # -- trade-balance identity residual (triple-leg, the one contradiction) --
    identity_disagree = ("trade_balance_identity_disagreement" in fired_kinds
                          and d["trade_balance_identity_residual"] is not None)
    items.append(_metric(
        "trade_balance_identity_residual", d["trade_balance_identity_residual"],
        "number", "usd_millions_sa", "same_date_disciplined_identity_residual",
        "magnitude_indicates_cross_series_revision_vintage_mismatch",
        f"fred.{SERIES_TRADE_BALANCE} - (fred.{SERIES_EXPORTS} - fred.{SERIES_IMPORTS})",
        f"fred.{SERIES_TRADE_BALANCE} - (fred.{SERIES_EXPORTS} - fred.{SERIES_IMPORTS})",
        _iso(d["triple_shared_date"]), d["fresh_triple"],
        source_refs=["FRED:BOPGSTB", "FRED:BOPTEXP", "FRED:BOPTIMP"],
        transformation=(
            "Published trade balance minus (exports minus imports), at the "
            "latest date common to all three legs; a disclosed "
            f"{_IDENTITY_RESIDUAL_TOLERANCE_USD_M:g}-USD-million tolerance band "
            "absorbs ordinary rounding across FRED's three independently-"
            "refreshed series -- a residual beyond the band is flagged as a "
            "genuine disagreement (this composer's one contradiction, judgment "
            "call 8), never silently averaged away."
        ),
        status="DISAGREEMENT" if identity_disagree else "PRESENT",
        null_reason="DISAGREEMENT" if identity_disagree else d["null_identity"],
    ))

    # -- typed remainder: four NOT_COVERED lanes, never estimated -------------
    items.append(_metric(
        "bilateral_country_trade_detail", None, "number", None, "n/a", "n/a",
        "NONE -- a China-side GACC partner-country collector exists in this "
        "estate but is another owner's context/display-tier-only lane",
        "NONE", None, "NOT_COVERED",
        transformation=(
            "A bilateral/country-level breakdown of US trade flows is not "
            "shown. A China-side partner-country trade detail collector "
            "(collectors/china_trade_detail.py -> data/china_trade_detail/) is "
            "real and nightly-wired in this estate, but it is scoped as "
            "'CONTEXT / DISPLAY TIER ONLY' for its own owning surface, and "
            "reusing its breakdown here would require a cross-workspace scope/ "
            "rights decision this composer has no standing to make on its own "
            "authority. Typed as not covered rather than silently read."
        ),
        null_reason="NOT_COVERED",
    ))
    items.append(_metric(
        "petroleum_specific_trade_flows", None, "number", None, "n/a", "n/a",
        "NONE -- EIA weekly crude import/export series exist in this estate "
        "but belong to the energy-plumbing owner's lane",
        "NONE", None, "NOT_COVERED",
        transformation=(
            "Petroleum-specific import/export flows are not shown. EIA weekly "
            "crude oil import/export series (WCEIMUS2 / WCREXUS2) exist "
            "in-tree, surfaced as a supply read on the energy/oil page's "
            "Commodity Vector -- a different owner's lane, not this "
            "workspace's. This composer does not build new collectors or "
            "cross-project another workspace's supply read; typed as not "
            "covered."
        ),
        null_reason="NOT_COVERED",
    ))
    items.append(_metric(
        "customs_tariff_receipts", None, "number", None, "n/a", "n/a",
        "NONE -- no collector for customs/tariff receipts exists anywhere in "
        "this estate",
        "NONE", None, "NOT_COVERED",
        transformation=(
            "Customs duty / tariff receipts context is not shown: no "
            "collector for that release exists in this estate today. This "
            "workspace does not estimate that context from a different series."
        ),
        null_reason="NOT_COVERED",
    ))
    items.append(_metric(
        "trade_services_detail", None, "number", None, "n/a", "n/a",
        "NONE -- only the combined goods-and-services read is collected; no "
        "goods-only or services-only breakdown exists",
        "NONE", None, "NOT_COVERED",
        transformation=(
            "A goods-only or services-only breakdown of the trade balance, "
            "exports, or imports is not shown: BOPGSTB/BOPTEXP/BOPTIMP are the "
            "COMBINED goods-AND-services read, and no finer breakdown is "
            "collected in this estate. This composer never estimates a "
            "goods-only or services-only split from the combined figure."
        ),
        null_reason="NOT_COVERED",
    ))

    return items


# --------------------------------------------------------------------------- #
# headline (unconditionally NOT_APPLICABLE -- judgment calls 10-11, see module
# docstring: a design absence, not a per-build refusal)
# --------------------------------------------------------------------------- #
def _headline(effective_date, prior_snapshot) -> dict:
    prior_method = _get(prior_snapshot, "headline", "method_version")
    prior_eff = _get(prior_snapshot, "headline", "effective_date")
    return {
        "state_id": None,
        "state_label": {"en": None, "zh": None},
        "subtitle": _bil("Trade balance, exports/imports, and the terms of trade",
                          "贸易差额、出口与进口及贸易条件"),
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
                "Trade Flows is a Chairman-authorized expansion added after the "
                "frozen Market Ontology architecture document's own twelve-workspace "
                "freeze, so no section of that document defines a headline model for "
                "it at all -- not even a note that none exists, the way "
                "monetary_policy/liquidity_central_banks each carry their own such "
                "note. There is accordingly no named axis pair here to attempt, and "
                "no dual-axis quadrant is asserted. A future architecture revision "
                "may ratify a genuine two-axis blueprint for this workspace, at which "
                "point this null becomes a real state the moment that blueprint is "
                "adopted. Until then, the real trade content -- balance, exports, "
                "imports, price indexes, the terms-of-trade proxy, and the "
                "balance-identity read -- lives in metrics, drivers, and "
                "implications instead. See the headline_unavailable implication for "
                "the reader-facing version."
            ),
        },
        "status": "ABSENT",
        "null_reason": "NOT_APPLICABLE",
    }


# --------------------------------------------------------------------------- #
# drivers (bucket reuse, disclosed -- judgment call 12)
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
        _mk("import_price_index_level", "Import price index", "进口价格指数",
            "fred.IR.import_price_index", metrics_by_id.get("import_price_index_level"), "index",
            "bucket reuse: published under drivers.rate_side because the contract's "
            "driver bucket pair is fixed as rate_side/balance_sheet and Trade Flows "
            "has no dedicated price-index bucket -- see the "
            "driver_bucket_naming_note implication"),
        _mk("export_price_index_level", "Export price index", "出口价格指数",
            "fred.IQ.export_price_index", metrics_by_id.get("export_price_index_level"), "index",
            "bucket reuse: see import_price_index_level's note"),
        _mk("terms_of_trade_proxy", "Terms-of-trade proxy", "贸易条件指标",
            f"fred.{SERIES_EXPORT_PRICE} / fred.{SERIES_IMPORT_PRICE}",
            metrics_by_id.get("terms_of_trade_proxy"), "ratio",
            "bucket reuse: see import_price_index_level's note"),
    ]
    balance_sheet = [
        _mk("trade_balance_level", "Trade balance", "贸易差额",
            "fred.BOPGSTB.trade_balance_goods_services", metrics_by_id.get("trade_balance_level"),
            "usd_millions_sa", "bucket reuse: published under drivers.balance_sheet because "
            "these legs concern a trade 'balance', a loose thematic fit, not a literal "
            "balance sheet -- see the driver_bucket_naming_note implication"),
        _mk("exports_level", "Exports", "出口",
            "fred.BOPTEXP.exports_goods_services", metrics_by_id.get("exports_level"),
            "usd_millions_sa", "bucket reuse: see trade_balance_level's note"),
        _mk("imports_level", "Imports", "进口",
            "fred.BOPTIMP.imports_goods_services", metrics_by_id.get("imports_level"),
            "usd_millions_sa", "bucket reuse: see trade_balance_level's note"),
        _mk("export_import_coverage_ratio", "Export/import coverage ratio", "出口对进口覆盖率",
            f"fred.{SERIES_EXPORTS} / fred.{SERIES_IMPORTS}",
            metrics_by_id.get("export_import_coverage_ratio"), "ratio",
            "bucket reuse: see trade_balance_level's note"),
        _mk("trade_balance_share_of_flows_pct", "Balance as share of flows", "差额占流量比重",
            f"fred.{SERIES_TRADE_BALANCE} / (fred.{SERIES_EXPORTS} + fred.{SERIES_IMPORTS})",
            metrics_by_id.get("trade_balance_share_of_flows_pct"), "percent",
            "bucket reuse: see trade_balance_level's note"),
        _mk("trade_balance_identity_residual", "Trade-balance identity residual", "贸易差额恒等式残差",
            f"fred.{SERIES_TRADE_BALANCE} - (fred.{SERIES_EXPORTS} - fred.{SERIES_IMPORTS})",
            metrics_by_id.get("trade_balance_identity_residual"), "usd_millions_sa",
            "bucket reuse: see trade_balance_level's note"),
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
        "revision_risk": "HIGH",
        "method_stability": "HIGH",
        "evidence_breadth": "MEDIUM",
        "contradiction_state": "PRESENT" if contradictions else "ABSENT",
    }
    items: list[dict] = [{
        "implication_id": "headline_unavailable",
        "text": _bil(
            "This page publishes no dual-axis state and no headline quadrant: the "
            "frozen Market Ontology architecture document defines twelve macro "
            "workspaces, each with its own headline blueprint (or an explicit note "
            "that none exists), and Trade Flows is not one of the twelve -- it is a "
            "Chairman-authorized expansion added afterward, so no blueprint section "
            "for it exists to fill in or fall short of. This is a design absence, "
            "not a data gap: unlike a workspace whose blueprint exists but cannot be "
            "computed from today's inputs, there is simply no named axis pair here "
            "to attempt. A future architecture revision may ratify a two-axis "
            "blueprint for this workspace, at which point this null becomes a real "
            "state the moment that blueprint is adopted. Until then, the real trade "
            "content -- balance, exports, imports, price indexes, and the terms of "
            "trade -- is published in full as metrics, drivers, and implications "
            "instead of being forced into a quadrant that has no definition to "
            "force it into.",
            "本页不发布双轴状态,也不发布头条象限:已冻结的市场本体架构文档定义了十二个"
            "宏观工作区,每个都有各自的头条蓝图（或明确说明不存在蓝图）,而贸易流动并非"
            "这十二个之一——它是后续经授权新增的扩展工作区,因此根本不存在可填补或未能"
            "填补的蓝图章节。这是设计层面的缺失,而非数据缺口:与蓝图存在但当前输入无法"
            "计算的工作区不同,这里根本没有可尝试的既定轴对。未来的架构修订版可能会为"
            "本工作区批准一个双轴蓝图,届时这一空值将在该蓝图被采纳的那一刻转为真实状态。"
            "在此之前,真实的贸易内容——差额、出口、进口、物价指数与贸易条件——均以指标、"
            "驱动因素与含义的形式完整发布,而非被强行纳入一个没有定义可供强行纳入的象限。"),
        "evidence_class": "DESCRIPTIVE", "confidence": conf, "horizon": "current",
        "channels": ["trade"], "contradictions": [c["kind"] for c in contradictions],
        "trace_ref": "engine.market_os.macro_workspaces.trade_flows#headline",
    }]

    tb = metrics_by_id.get("trade_balance_level")
    tb_avg = metrics_by_id.get("trade_balance_avg_3m")
    tb_yoy = metrics_by_id.get("trade_balance_yoy_change")
    if tb is not None or tb_avg is not None or tb_yoy is not None:
        tb_en = f"reads {tb:+,.0f} USD million" if tb is not None else "is unavailable"
        avg_en = f", trailing 3-month average {tb_avg:+,.0f}" if tb_avg is not None else ""
        yoy_en = f", {tb_yoy:+,.0f} versus 12 months prior" if tb_yoy is not None else ""
        tb_zh = f"读数为{tb:+,.0f}百万美元" if tb is not None else "不可得"
        avg_zh = f"，近3个月均值为{tb_avg:+,.0f}" if tb_avg is not None else ""
        yoy_zh = f"，较12个月前变化{tb_yoy:+,.0f}" if tb_yoy is not None else ""
        items.append({
            "implication_id": "trade_balance_read",
            "text": _bil(f"The goods-and-services trade balance {tb_en}{avg_en}{yoy_en}.",
                         f"货物与服务贸易差额{tb_zh}{avg_zh}{yoy_zh}。"),
            "evidence_class": "DESCRIPTIVE", "confidence": conf, "horizon": "current",
            "channels": ["trade"], "contradictions": [], "trace_ref": None,
        })

    ex = metrics_by_id.get("exports_level")
    ex_yoy = metrics_by_id.get("exports_yoy")
    im = metrics_by_id.get("imports_level")
    im_yoy = metrics_by_id.get("imports_yoy")
    cov = metrics_by_id.get("export_import_coverage_ratio")
    if ex is not None or im is not None:
        ex_en = f"exports {ex:,.0f}" + (f" ({ex_yoy:+.1f}% YoY)" if ex_yoy is not None else "") if ex is not None else "exports unavailable"
        im_en = f"imports {im:,.0f}" + (f" ({im_yoy:+.1f}% YoY)" if im_yoy is not None else "") if im is not None else "imports unavailable"
        cov_en = f", export/import coverage {cov:.3f}" if cov is not None else ""
        ex_zh = (f"出口{ex:,.0f}" + (f"（同比{ex_yoy:+.1f}%）" if ex_yoy is not None else "")) if ex is not None else "出口不可得"
        im_zh = (f"进口{im:,.0f}" + (f"（同比{im_yoy:+.1f}%）" if im_yoy is not None else "")) if im is not None else "进口不可得"
        cov_zh = f"，出口对进口覆盖率为{cov:.3f}" if cov is not None else ""
        items.append({
            "implication_id": "flows_read",
            "text": _bil(f"{ex_en[0].upper()}{ex_en[1:]}; {im_en}{cov_en} (USD millions, SA).",
                         f"{ex_zh}；{im_zh}{cov_zh}（单位：百万美元，季节调整）。"),
            "evidence_class": "DESCRIPTIVE", "confidence": conf, "horizon": "current",
            "channels": ["trade"], "contradictions": [], "trace_ref": None,
        })

    ir = metrics_by_id.get("import_price_index_level")
    ir_yoy = metrics_by_id.get("import_price_index_yoy")
    iq = metrics_by_id.get("export_price_index_level")
    iq_yoy = metrics_by_id.get("export_price_index_yoy")
    tot = metrics_by_id.get("terms_of_trade_proxy")
    if ir is not None or iq is not None:
        ir_en = f"import prices {ir:g}" + (f" ({ir_yoy:+.1f}% YoY)" if ir_yoy is not None else "") if ir is not None else "import prices unavailable"
        iq_en = f"export prices {iq:g}" + (f" ({iq_yoy:+.1f}% YoY)" if iq_yoy is not None else "") if iq is not None else "export prices unavailable"
        tot_en = f"; terms-of-trade proxy {tot:.4f}" if tot is not None else ""
        ir_zh = (f"进口价格{ir:g}" + (f"（同比{ir_yoy:+.1f}%）" if ir_yoy is not None else "")) if ir is not None else "进口价格不可得"
        iq_zh = (f"出口价格{iq:g}" + (f"（同比{iq_yoy:+.1f}%）" if iq_yoy is not None else "")) if iq is not None else "出口价格不可得"
        tot_zh = f"；贸易条件指标为{tot:.4f}" if tot is not None else ""
        items.append({
            "implication_id": "price_index_read",
            "text": _bil(f"{ir_en[0].upper()}{ir_en[1:]}; {iq_en}{tot_en}.",
                         f"{ir_zh}；{iq_zh}{tot_zh}。"),
            "evidence_class": "DESCRIPTIVE", "confidence": conf, "horizon": "current",
            "channels": ["trade", "inflation"], "contradictions": [], "trace_ref": None,
        })

    share = metrics_by_id.get("trade_balance_share_of_flows_pct")
    if share is not None:
        items.append({
            "implication_id": "balance_share_of_flows_read",
            "text": _bil(
                f"The trade balance is {share:+.2f}% of total goods-and-services "
                "flows (exports plus imports) -- a scale-normalized read of the "
                "deficit or surplus relative to overall trade volume.",
                f"贸易差额占货物与服务贸易总流量（出口加进口）的{share:+.2f}%——"
                "这是相对于整体贸易规模,对逆差或顺差进行的规模标准化读数。"),
            "evidence_class": "DESCRIPTIVE", "confidence": conf, "horizon": "current",
            "channels": ["trade"], "contradictions": [], "trace_ref": None,
        })

    residual = metrics_by_id.get("trade_balance_identity_residual")
    if residual is not None and "trade_balance_identity_disagreement" not in {
        c["kind"] for c in contradictions
    }:
        items.append({
            "implication_id": "identity_residual_read",
            "text": _bil(
                f"The trade-balance identity (balance = exports minus imports) "
                f"holds within this page's disclosed rounding tolerance; the "
                f"residual reads {residual:+.1f} USD million.",
                f"贸易差额恒等式（差额=出口减进口）在本页披露的四舍五入容差内成立；"
                f"残差读数为{residual:+.1f}百万美元。"),
            "evidence_class": "DESCRIPTIVE", "confidence": conf, "horizon": "current",
            "channels": ["trade"], "contradictions": [], "trace_ref": None,
        })

    for c in contradictions:
        items.append({
            "implication_id": f"contradiction_{c['kind']}",
            "text": _bil(c["en"], c["zh"]),
            "evidence_class": "DESCRIPTIVE", "confidence": conf, "horizon": "current",
            "channels": ["trade"], "contradictions": [c["kind"]], "trace_ref": None,
        })

    items.append({
        "implication_id": "sa_nsa_never_mix_disclosure",
        "text": _bil(
            "The trade balance, exports, and imports are seasonally adjusted "
            "(SA) dollar flows; the import and export price indexes are NOT "
            "seasonally adjusted (NSA). The terms-of-trade proxy divides the two "
            "NSA price indexes by each other -- a clean pairing -- and every "
            "other derived read on this page combines only the SA dollar-flow "
            "series. Neither group is ever mixed with the other in one derived "
            "value.",
            "贸易差额、出口与进口为经季节调整（SA）的美元流量；进口与出口价格指数则"
            "未经季节调整（NSA）。贸易条件指标是两个NSA价格指数相除——属于同类型配对；"
            "本页其余所有派生读数均只组合SA美元流量序列。两类序列从不在同一派生读数中"
            "混用。"),
        "evidence_class": "DESCRIPTIVE", "confidence": conf, "horizon": "current",
        "channels": ["trade"], "contradictions": [], "trace_ref": None,
    })

    items.append({
        "implication_id": "same_date_discipline_disclosure",
        "text": _bil(
            "Every ratio and combined read on this page (the export/import "
            "coverage ratio, the terms-of-trade proxy, the balance-as-share-of-"
            "flows read, and the trade-balance identity residual) is computed "
            "only from a date common to every leg it combines, never by pairing "
            "each leg's own separately-latest print. When the latest shared date "
            "lags any single leg's own newest available print by more than a "
            "disclosed tolerance, this composer refuses that read rather than "
            "mixing an older print from one leg with a newer print from another "
            "under one reported date.",
            "本页所有比率与组合读数（出口对进口覆盖率、贸易条件指标、差额占流量比重"
            "读数,以及贸易差额恒等式残差）均只依据其所涉及的每一分项都共有的同一日期"
            "计算,绝不将各分项各自的最新日期拼凑在一起。当某组合中各分项的共同最新"
            "日期,相较其中任一分项自身的最新可得读数滞后超出披露容差时,本组合器会"
            "拒绝给出该读数,而不会在同一报告日期下混用一个分项的旧读数与另一分项的"
            "新读数。"),
        "evidence_class": "DESCRIPTIVE", "confidence": conf, "horizon": "current",
        "channels": ["trade"], "contradictions": [], "trace_ref": None,
    })

    items.append({
        "implication_id": "no_alfred_pit_vintage_capture",
        "text": _bil(
            "No point-in-time vintage capture exists for any series on this "
            "page today. Every level and derived read above is the current "
            "stored (latest-revised) value, not what was knowable in real "
            "time; both the FT-900 dollar-flow figures and the BLS price "
            "indexes are revised for months after first release.",
            "本页所有序列目前均无时点（PIT）版本捕获。以上所有水平值与派生读数均为"
            "当前存储的（最新修订后的）数值，而非当时实际可知的数值；FT-900美元流量"
            "数据与BLS物价指数在首次发布后均会持续修订数月。"),
        "evidence_class": "DESCRIPTIVE", "confidence": conf, "horizon": "current",
        "channels": ["trade"], "contradictions": [], "trace_ref": None,
    })

    items.append({
        "implication_id": "bilateral_country_not_covered_disclosure",
        "text": _bil(
            "Bilateral or country-level trade detail is not shown: a China-side "
            "GACC partner-country breakdown collector exists in this estate, but "
            "it is scoped as context/display-tier-only for its own owning "
            "surface, and reusing it here is a cross-workspace scope decision "
            "this composer does not make on its own authority.",
            "本页未展示双边或国别贸易细节：本估值体系已接入一个针对中国海关总署"
            "国别贸易明细的采集器，但该采集器的定位仅面向其自身归属界面的"
            "背景/展示层级，若要在本工作区复用，需要跨工作区的范围决策，"
            "本组合器无权自行做出该决策。"),
        "evidence_class": "DESCRIPTIVE", "confidence": conf, "horizon": "current",
        "channels": ["trade"], "contradictions": [], "trace_ref": None,
    })

    items.append({
        "implication_id": "petroleum_not_covered_disclosure",
        "text": _bil(
            "Petroleum-specific trade flows are not shown: EIA weekly crude "
            "oil import/export series exist in this estate but belong to the "
            "energy-plumbing owner's own supply read, not this workspace.",
            "本页未展示原油等石油相关贸易流量：本估值体系已接入EIA每周原油进出口"
            "序列，但该数据归属能源基础设施所有者自身的供给读数，而非本工作区。"),
        "evidence_class": "DESCRIPTIVE", "confidence": conf, "horizon": "current",
        "channels": ["trade"], "contradictions": [], "trace_ref": None,
    })

    items.append({
        "implication_id": "customs_tariff_not_covered_disclosure",
        "text": _bil(
            "Customs duty or tariff receipts context is not shown: no "
            "collector for that release exists in this estate yet. This "
            "workspace does not estimate that context from a different series.",
            "本页未展示关税或海关税收相关背景：本估值体系目前尚未为该发布接入"
            "任何采集器。本工作区不会用其他序列估算该背景数据。"),
        "evidence_class": "DESCRIPTIVE", "confidence": conf, "horizon": "current",
        "channels": ["trade"], "contradictions": [], "trace_ref": None,
    })

    items.append({
        "implication_id": "services_detail_not_covered_disclosure",
        "text": _bil(
            "A goods-only or services-only breakdown of the trade balance, "
            "exports, or imports is not shown: only the combined goods-and-"
            "services read is collected, and this composer never estimates a "
            "finer split from the combined figure.",
            "本页未展示货物或服务单独口径的贸易差额、出口或进口细分：本估值体系"
            "仅采集货物与服务合并口径的读数，本组合器也从不基于合并数据估算更细"
            "的拆分。"),
        "evidence_class": "DESCRIPTIVE", "confidence": conf, "horizon": "current",
        "channels": ["trade"], "contradictions": [], "trace_ref": None,
    })

    items.append({
        "implication_id": "driver_bucket_naming_note",
        "text": _bil(
            "The drivers.balance_sheet bucket in this snapshot carries the "
            "dollar-flow legs (trade balance, exports, imports, the coverage "
            "ratio, the balance-share-of-flows read, and the identity "
            "residual) -- a loose thematic fit (these concern a trade "
            "'balance'), not a literal balance sheet; drivers.rate_side "
            "carries the two price-index legs and the terms-of-trade proxy, "
            "not policy rates. The contract's driver bucket pair is fixed as "
            "rate_side/balance_sheet and this workspace has no dedicated "
            "flows/price bucket, so the naming is cosmetic bucket reuse, "
            "disclosed here rather than left implicit.",
            "本快照中drivers.balance_sheet分组承载的是美元流量分项（贸易差额、"
            "出口、进口、覆盖率、差额占流量比重读数与恒等式残差）——这只是与"
            "“差额”主题的松散呼应，而非字面意义上的资产负债表；drivers.rate_side"
            "分组承载的是两个物价指数分项与贸易条件指标，而非政策利率。合约的"
            "驱动因素分组固定为rate_side/balance_sheet，本工作区没有独立的流量/"
            "价格分组可用，因此命名属于用途借用，在此明确披露而非隐含处理。"),
        "evidence_class": "DESCRIPTIVE", "confidence": conf, "horizon": "current",
        "channels": ["trade"], "contradictions": [], "trace_ref": None,
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
            {"assumption_id": "exports_growth_pct", "label": _bil("Exports growth", "出口增长"),
             "unit": "pct", "step": 0.5, "min": -30.0, "max": 30.0,
             "owner_field": "fred.BOPTEXP.exports_goods_services"},
            {"assumption_id": "imports_growth_pct", "label": _bil("Imports growth", "进口增长"),
             "unit": "pct", "step": 0.5, "min": -30.0, "max": 30.0,
             "owner_field": "fred.BOPTIMP.imports_goods_services"},
            {"assumption_id": "import_price_growth_pct", "label": _bil("Import price growth", "进口价格增长"),
             "unit": "pct", "step": 0.5, "min": -30.0, "max": 30.0,
             "owner_field": "fred.IR.import_price_index"},
            {"assumption_id": "export_price_growth_pct", "label": _bil("Export price growth", "出口价格增长"),
             "unit": "pct", "step": 0.5, "min": -30.0, "max": 30.0,
             "owner_field": "fred.IQ.export_price_index"},
            {"assumption_id": "trade_balance_usd_bn", "label": _bil("Trade balance", "贸易差额"),
             "unit": "usd_bn", "step": 5.0, "min": -200.0, "max": 50.0, "owner_field": None},
        ],
        "status": "PARTIAL",
        "note": (
            "Assumption vocabulary is declared and closed; this composer ships no "
            "scenario execution endpoint (non-goal). trade_balance_usd_bn has no "
            "owner_field because it is a DERIVED read (not a single owner series) "
            "-- a future owner-native pure scenario function produces "
            "mastermind.macro_workspace_scenario_result.v1 with no canonical write."
        ),
    }


def _alert_contract() -> dict:
    return {
        "service_available": False,
        "eligible_conditions": [
            {"condition_id": "trade_balance_shock", "kind": "component_shock",
             "label": _bil("Trade balance shock", "贸易差额冲击"), "params": ["trade_balance_level"]},
            {"condition_id": "coverage_ratio_shift", "kind": "component_shock",
             "label": _bil("Export/import coverage shift", "出口对进口覆盖率变化"),
             "params": ["export_import_coverage_ratio"]},
            {"condition_id": "terms_of_trade_shift", "kind": "component_shock",
             "label": _bil("Terms-of-trade shift", "贸易条件变化"), "params": ["terms_of_trade_proxy"]},
            {"condition_id": "identity_disagreement_change", "kind": "contradiction_change",
             "label": _bil("Trade-balance identity disagreement change", "贸易差额恒等式分歧变化"),
             "params": ["kind"]},
            {"condition_id": "source_stale_or_failed", "kind": "source_stale_or_failed",
             "label": _bil("Source stale or failed", "数据源过期或失败"), "params": ["source_id"]},
            {"condition_id": "source_revision", "kind": "source_revision",
             "label": _bil("Material source revision", "数据源重大修订"), "params": ["source_id"]},
        ],
        "status": "ABSENT",
        "note": (
            "Eligible condition types are declared; this composer writes no alert "
            "(non-goal). Alerts extend the existing Terminal alert lifecycle "
            "later; a page shows the Alerts tab only once the service can "
            "create/list/evaluate/delete these real conditions."
        ),
    }


# --------------------------------------------------------------------------- #
# sources
# --------------------------------------------------------------------------- #
def _sources(rows: dict, fresh: dict) -> list[dict]:
    def _src(source_id, en, zh, owner_ref, provider, ref_period, artifact_ref, fresh_state,
              rights="OPEN"):
        return {
            "source_id": source_id, "label": _bil(en, zh), "owner_ref": owner_ref,
            "provider": provider, "reference_period": ref_period, "released_at": None,
            "first_known_at": None, "collected_at": None, "revised_at": None,
            "correction_state": "unknown", "transform": None, "rights_state": rights,
            "definition_id": None, "definition_version": None, "artifact_ref": artifact_ref,
            "freshness": fresh_state,
        }

    tb_asof = _iso(_latest(rows[SERIES_TRADE_BALANCE])[0]) if rows[SERIES_TRADE_BALANCE] else None
    ex_asof = _iso(_latest(rows[SERIES_EXPORTS])[0]) if rows[SERIES_EXPORTS] else None
    im_asof = _iso(_latest(rows[SERIES_IMPORTS])[0]) if rows[SERIES_IMPORTS] else None
    ir_asof = _iso(_latest(rows[SERIES_IMPORT_PRICE])[0]) if rows[SERIES_IMPORT_PRICE] else None
    iq_asof = _iso(_latest(rows[SERIES_EXPORT_PRICE])[0]) if rows[SERIES_EXPORT_PRICE] else None

    return [
        _src("bopgstb", "Trade balance, goods & services (Census/BEA FT-900, via FRED)",
             "贸易差额，货物与服务（人口普查局/BEA FT-900报告，经FRED）",
             "collectors.fred[BOPGSTB]", "US Census Bureau / BEA / FRED", tb_asof,
             f"data/fred/{SERIES_TRADE_BALANCE}.parquet", fresh[SERIES_TRADE_BALANCE]),
        _src("boptexp", "Exports, goods & services (Census/BEA FT-900, via FRED)",
             "出口，货物与服务（人口普查局/BEA FT-900报告，经FRED）",
             "collectors.fred[BOPTEXP]", "US Census Bureau / BEA / FRED", ex_asof,
             f"data/fred/{SERIES_EXPORTS}.parquet", fresh[SERIES_EXPORTS]),
        _src("boptimp", "Imports, goods & services (Census/BEA FT-900, via FRED)",
             "进口，货物与服务（人口普查局/BEA FT-900报告，经FRED）",
             "collectors.fred[BOPTIMP]", "US Census Bureau / BEA / FRED", im_asof,
             f"data/fred/{SERIES_IMPORTS}.parquet", fresh[SERIES_IMPORTS]),
        _src("ir", "Import price index, all commodities (BLS, via FRED)",
             "进口价格指数，所有商品（BLS，经FRED）", "collectors.fred[IR]",
             "US Bureau of Labor Statistics / FRED", ir_asof,
             f"data/fred/{SERIES_IMPORT_PRICE}.parquet", fresh[SERIES_IMPORT_PRICE]),
        _src("iq", "Export price index, all commodities (BLS, via FRED)",
             "出口价格指数，所有商品（BLS，经FRED）", "collectors.fred[IQ]",
             "US Bureau of Labor Statistics / FRED", iq_asof,
             f"data/fred/{SERIES_EXPORT_PRICE}.parquet", fresh[SERIES_EXPORT_PRICE]),
        _src("bilateral_country_trade_detail", "Bilateral/country-level trade detail",
             "双边/国别贸易细节", "NONE -- another owner's context/display-tier-only lane",
             "China Customs (GACC), via collectors/china_trade_detail.py", None, None, "NOT_COVERED"),
        _src("petroleum_specific_trade_flows", "Petroleum-specific trade flows",
             "石油相关贸易流量", "NONE -- another owner's energy-plumbing lane",
             "US Energy Information Administration", None, None, "NOT_COVERED"),
        _src("customs_tariff_receipts", "Customs duty / tariff receipts",
             "关税/海关税收", "NONE -- no collector wired in this estate",
             None, None, None, "NOT_COVERED"),
        _src("trade_services_detail", "Goods-only / services-only trade detail",
             "货物或服务单独口径贸易细节", "NONE -- only the combined read is collected",
             None, None, None, "NOT_COVERED"),
    ]


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
    rates_curves.py's/consumer_payments.py's own ``_corrections`` for the full
    caveat about this being a scoped subset, not a persisted vintage ledger)."""
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
