"""Pure composer for the US ``national_debt_liabilities`` workspace snapshot (F01 / R6).

Reads FOUR raw, ALREADY-LOADED owner inputs -- three Daily-Treasury-Statement (DTS)
flow/level series, a Treasury-auction results table, two BIS quarterly panels, and
one small owner-artifact passthrough -- and projects them into a
``mastermind.macro_workspace_snapshot.v1`` body:

* ``treasury_frames`` -- a dict ``{"tga": rows, "net_issuance": rows,
  "withheld_taxes": rows}`` where ``rows`` is a plain Python list of
  ``(date, value)`` pairs (or longer tuples -- extra elements are ignored, see
  the digest tests' unconsumed-field negative control) or ``None``, ascending.
  ``tga`` -> ``data/treasury/tga.parquet`` column ``tga_mn`` (TGA daily closing
  balance); ``net_issuance`` -> ``data/treasury/net_issuance.parquet`` column
  ``net_issuance_mn`` (Issues minus Redemptions, a daily flow); ``withheld_taxes``
  -> ``data/treasury/withheld_taxes.parquet`` column ``withheld_tax_mn`` (withheld
  income & employment-tax deposits, a daily flow). ALL THREE are DTS business-day
  cadence, published the next business day, and ALL THREE are stored in $
  MILLIONS -- the ``_mn`` column-suffix IS the unit contract (build.py's own
  ``_TREASURY_COLUMNS`` mapping names these same three files/columns).
* ``auction_rows`` -- a plain list of dicts (or ``None``), each carrying exactly
  ``auction_date`` (iso str), ``security_type`` (str), ``tenor_years``
  (float|None), ``bid_to_cover`` (float|None), ``high_yield`` (float|None),
  sorted ascending by ``auction_date`` -- ``data/treasury_auctions/auctions.parquet``
  (build.py's ``_load_auction_rows``), the demand side of the Treasury market from
  the keyless TreasuryDirect ``TA_WS/securities/auctioned`` feed.
* ``bis_frames`` -- a dict ``{"dsr": rows, "gap": rows}`` of the SAME ``(date,
  value)`` row shape, quarterly, PERIOD-END dated -- ``data/bis/us_dsr.parquet``
  column ``dsr`` (US household debt-service ratio) and ``data/bis/us_gap.parquet``
  column ``gap`` (US credit-to-GDP gap), per config.yml's ``credit_gap_dsr.panels``
  ``us_dsr``/``us_gap`` mapping. BIS data carries ATTRIBUTION-ONLY rights: every
  metric/implication touching it names "Bank for International Settlements (BIS)"
  explicitly and never rebrands the read as this estate's own.
* ``bonds_latest`` -- ``dict | None``, the raw parsed ``data/bonds/latest.json``
  owner artifact (``scripts/build_bonds.py``): exactly six keys -- ``date``,
  ``health_score`` (0-100), ``health_label`` (closed owner vocabulary
  ``{"healthy", "mixed", "stressed"}``, ``HEALTH_COLOR``/``label_zh`` in
  ``scripts/build_bonds.py``), ``cycle_phase`` (closed owner vocabulary
  ``{"recession", "early", "mid", "late"}``, ``PHASE`` in the same script),
  ``verdict_en``, ``verdict_zh``. This composer projects a SMALL read of that
  state (health_score/health_label/cycle_phase only, judgment call 10 below) --
  it never republishes the owner's own editorial ``verdict_en``/``verdict_zh``
  sentence as if it were this composer's own voice (mirrors
  ``capital_structure.py``'s never-republish-the-record-set law).

LOAD-BEARING GAP (census 2026-09-04, binding, never silently patched): NO debt
STOCK series exists anywhere in this estate -- no Debt-to-the-Penny, no Monthly
Treasury Statement (MTS) receipts/outlays, no TIC foreign-holdings, no
MSPD/weighted-average-maturity ladder. Total-debt-outstanding, debt-to-GDP,
debt-held-by-public, intragovernmental holdings, the deficit/primary balance,
net interest burden, the maturity ladder, foreign holdings, and contingent
liabilities are ALL typed ``NOT_COVERED`` below, one metric per architecture
10.12 "Required composition" leg this estate cannot fill, each with its own
gap-specific transformation note. This composer NEVER integrates
``net_issuance`` into a fabricated stock level -- a flow's running sum is not a
level without a real anchor (an initial stock this estate does not have), and
publishing one would be exactly the "debt-stock/flow confusion" architecture
10.12 names as a failure state, not an honest workaround.

HEADLINE (read this before "fixing" it -- mirrors ``housing.py``'s /
``capital_structure.py``'s own headline-refusal notes): architecture 10.12 DOES
define a real two-axis blueprint (x: refinancing/issuance pressure, low ->
high; y: fiscal capacity/interest-burden resilience, weak -> strong) -- unlike
``monetary_policy``/``liquidity_central_banks``, which have NO headline-model
subsection at all and are therefore honestly ``NOT_APPLICABLE`` by design.
National Debt is the ``housing``/``capital_structure`` case: a blueprint
exists, but the owner substrate this composer actually has cannot honestly
fill it in. The x-axis bundles TWO distinct pressures -- issuance pressure
(computable: ``net_issuance_sum_4w``/``13w``, the pace-delta read) and
REFINANCING pressure specifically (needs a maturity/rollover wall -- the
absent MSPD/WAM ladder, see the load-bearing gap above); the y-axis needs a
genuine fiscal-capacity/interest-burden composite (debt stock, net interest
expense, revenue -- all absent). Publishing the issuance-pressure half alone
AS "refinancing/issuance pressure," or improvising a DIFFERENT unnamed axis
pair (e.g. "issuance pressure x demand absorption") the architecture never
specified, would both be exactly the fabricated-methodology-dressed-as-real
move ``capital_structure.py``'s own docstring forbids. So: ``headline.state_id``
stays ``null`` with ``status="ABSENT"`` and ``null_reason="COMPUTATION_REFUSED"``
(a data refusal, NOT a design "not-applicable"), and ``axes.items`` stays
``[]`` (schema-legal). The real, honestly-computable content -- issuance
pressure, auction demand absorption, the BIS DSR/credit-gap levels, the
bond-desk coverage passthrough, and a genuine cross-source contradiction check
-- is published as real metrics/drivers/implications instead of being smuggled
into a fabricated quadrant the contract has no dedicated "partial axis" slot
for anyway.

CONTRADICTION: a genuine, three-legged, all-owner-native-value check (never a
composer-invented magnitude beyond the disclosed flat bands, judgment calls 8-9
below): when net issuance is genuinely ACCELERATING (the trailing-4-week daily
pace running materially above the trailing-13-week pace), recent auction
demand is genuinely WEAKENING (the recent bid-to-cover average sits materially
below the trailing-year baseline), and the bond desk's OWN health read still
says "healthy" (its calmest closed-vocabulary state), this composer emits a
typed ``issuance_demand_stress_vs_bond_desk_calm`` DISAGREEMENT -- a
supply/demand stress signal the desk has not itself flagged. It stays silent
whenever any of the three legs is absent or inside its disclosed flat band --
never forced.

DRIVERS BUCKET REUSE (disclosed, mirrors ``housing.py``/``liquidity_central_banks.py``):
the contract's ``drivers`` block is closed to exactly ``{rate_side,
balance_sheet}``. ``balance_sheet`` carries TGA/issuance/auction-spread/revenue
flow legs -- TGA's placement is a closer-than-usual natural fit (TGA IS
literally Treasury's own account balance), but the pairing is still disclosed
bucket reuse per house law since net issuance / the auction spread / withheld-
tax YoY are not literally "a balance sheet." ``rate_side`` carries the
yield/credit-cycle-adjacent legs (latest auction high-yield, the BIS DSR/gap
levels) -- NOT policy rates -- because this workspace has no dedicated
"auction"/"credit" bucket to use; disclosed in each driver's own ``note`` and
in the ``driver_bucket_naming_note`` implication.

DISCLOSED JUDGMENT CALLS (numbered, never silently assumed):
 1. Headline stays ``COMPUTATION_REFUSED`` (data-insufficiency), never
    ``NOT_APPLICABLE`` (design-absence) and never a fabricated substitute axis
    pair the architecture never named -- see the HEADLINE note above.
 2. Every dollar metric below is published in RAW $ MILLIONS (unit
    ``usd_mn``), never rescaled to billions -- mirrors
    ``liquidity_central_banks.py``'s WALCL refuse-not-rescale law. Prose may
    convert to $bn purely for readability, always labeled inline, never
    changing the metric's own declared unit.
 3. TGA "impulse" (4w/13w) is a self-referential calendar-day LEVEL CHANGE
    (28d/91d, disclosed lookback slack) -- a DIFFERENT read, for a DIFFERENT
    purpose, from ``engine/treasury_watch.py``'s own extremum-anchored
    EPISODE-DETECTION windowing (``min_episode_bn``/``lookback_extremum_bd``).
    This composer never imports or re-runs ``treasury_watch.py``; it composes
    from the same raw ``tga.parquet`` independently.
 4. Withheld-taxes windowing deliberately DIVERGES from the ALREADY-established
    ``engine/conditions.py`` convention for this exact series (a 63-ROW ~3-month
    rolling sum with a 252-ROW ~1-year shift for YoY, ``config.yml``
    ``labor.withheld_sum_window_d``/``withheld_yoy_window_d``) in favor of a
    tighter CALENDAR-DAY 4-week sum / 365-day YoY window, per this workspace's
    own "4w YoY" revenue-nowcast brief -- a faster pulse for a different
    purpose, never claimed to reproduce ``engine/conditions.py``'s own number
    (see the ``withheld_taxes_window_divergence_disclosure`` implication).
 5. Minimum-row coverage floors for the DTS trailing sums (``_MIN_ROWS_4W=10``,
    ``_MIN_ROWS_13W=30``) are composer judgment calls sized off DTS's
    business-day cadence (~5/7 of calendar days) -- a genuinely-EMPTY or
    too-sparse window is refused (``INSUFFICIENT_HISTORY``) rather than
    silently summing to a misleadingly-small total.
 6. The auction "recent" window (8) mirrors the OWNER's own
    ``config.yml treasury_auctions.trailing: 8`` same-tenor z-score baseline
    window, reused here as a deliberately CROSS-TENOR blend (all security
    types pooled) -- a disclosed scope-boundary departure from the owner's own
    same-tenor scoping, not an oversight; this composer builds no tenor-bucketed
    read. Its minimum-coverage floor (5) mirrors the owner's own
    ``config.yml treasury_auctions.min_trailing: 5``.
 7. The auction "baseline" window (trailing 365 calendar days, ending at the
    latest bid-to-cover auction's OWN date, never ``built_at``) and its
    minimum-coverage floor (10) are both composer-invented, offered as the
    longer-horizon "vs trailing-year baseline" comparison this workspace's own
    brief calls for -- distinct from the owner's own trailing-8 same-tenor
    z-score baseline.
 8. The issuance-acceleration flat band (``_ISSUANCE_PACE_FLAT_BAND_MN_PER_DAY
    = 1000.0``, i.e. $1bn/day) and the auction-demand flat band
    (``_AUCTION_DEMAND_FLAT_BAND = 0.10`` bid-to-cover points) are disclosed
    composer-invented thresholds (mirrors ``liquidity_central_banks.py``'s
    ``_FED_FLAT_BAND_PCT`` / ``housing.py``'s
    ``_HOME_PRICE_RENT_FLAT_BAND_PCT`` precedent) -- never a percentile/z-score
    this composer has no historical distribution to calibrate honestly.
 9. The contradiction's "calm bond desk" leg is scoped EXACTLY to the owner's
    own closed ``health_label`` vocabulary member ``"healthy"``
    (``scripts/build_bonds.py``'s ``HEALTH_COLOR = {healthy, mixed,
    stressed}``) -- ``"mixed"`` is deliberately excluded from "calm," a
    disclosed composer judgment call, not an owner-published threshold.
10. ``bonds_latest`` is projected as a SMALL read (health_score/health_label/
    cycle_phase only); the owner's own editorial ``verdict_en``/``verdict_zh``
    sentence is never republished by this composer's own prose.
11. Fiscal-year tagging: this composer publishes ONLY rolling calendar-day
    windows (4w/13w/365d), never a US-FY(Oct-Sep)-tagged aggregate -- avoiding
    architecture 10.12's own named "fiscal-year/calendar-year mismatch" failure
    state at the cost of a less budget-native cadence (see the
    ``fiscal_year_windowing_disclosure`` implication).
12. Drivers-bucket reuse (rate_side/balance_sheet) -- see the DRIVERS BUCKET
    REUSE note above.

NO rank/gate/size/trade authority. NO LLM-originated facts. Descriptive
ceiling only. Depends only on the standard library (no pandas import here --
the caller supplies plain rows/dicts so this module stays testable without
pandas). The composer NEVER reads a wall clock: ``built_at`` is supplied by
the caller, and every staleness/age/lookback check is a pure function of
``built_at`` and the given rows, so an identical set of owner inputs always
yields an identical snapshot body.
"""
from __future__ import annotations

import datetime as _dt
from hashlib import sha256
from typing import Any, Mapping, Sequence

METHOD_VERSION = "national_debt_liabilities.compose.v1"
DEFINITION_VERSION = "1.0.0"
PRODUCER = "engine.market_os.macro_workspaces.national_debt"
WORKSPACE_ID = "national_debt_liabilities"

# treasury_frames / bis_frames dict keys (build.py's _TREASURY_COLUMNS / _BIS_US_COLUMNS).
TGA_KEY = "tga"
NET_ISSUANCE_KEY = "net_issuance"
WITHHELD_KEY = "withheld_taxes"
BIS_DSR_KEY = "dsr"
BIS_GAP_KEY = "gap"

# Owner artifact paths (verified present in-tree at authoring time; see the
# hand-off's "what could not be verified without a shell").
_TGA_PATH = "data/treasury/tga.parquet"
_NET_ISSUANCE_PATH = "data/treasury/net_issuance.parquet"
_WITHHELD_PATH = "data/treasury/withheld_taxes.parquet"
_AUCTIONS_PATH = "data/treasury_auctions/auctions.parquet"
_BIS_DSR_PATH = "data/bis/us_dsr.parquet"
_BIS_GAP_PATH = "data/bis/us_gap.parquet"
_BONDS_PATH = "data/bonds/latest.json"

# --------------------------------------------------------------------------- #
# freshness law constants (MANDATORY, corrected 2026-09-04 -- see module
# docstring's cadence derivations; each hand-checked against 2026-09-04 disk
# truth so a maximally-fresh read carries CURRENT, never a false STALE_SOURCE).
# --------------------------------------------------------------------------- #
# DTS daily series (tga/net_issuance/withheld_taxes): published next business
# day -> worst-case newest print age over a long weekend is ~4-5 calendar days
# -> cadence 5d, grace 4d covers holiday-shifted release days.
_DTS_CADENCE_DAYS = 5
_DTS_GRACE_DAYS = 4
# Treasury auctions: event-driven weekly rhythm -> newest auction row worst-
# case ~10d in a normal week -> cadence 10d, grace 7d. Freshness is measured
# on the latest AUCTION_DATE itself (disclosed, per judgment call 6/7).
_AUCTION_CADENCE_DAYS = 10
_AUCTION_GRACE_DAYS = 7
# BIS dsr/gap: quarterly, period-END dated, published ~5-6 months after
# quarter end -> worst-case lag ~165d + one 92d cycle -> cadence 260d, grace
# 30d (hand-check: the 2025-12-31 print at age 247d on 2026-09-04 MUST read
# CURRENT -- it is the newest possible print; 247 <= 260).
_BIS_CADENCE_DAYS = 260
_BIS_GRACE_DAYS = 30
# bonds_latest: a daily owner artifact with its own `date` field -> cadence
# 3d, grace 3d (weekend coverage).
_BONDS_CADENCE_DAYS = 3
_BONDS_GRACE_DAYS = 3

# --------------------------------------------------------------------------- #
# derived-read window constants (disclosed, never silently invented).
# --------------------------------------------------------------------------- #
_FOUR_WEEK_DAYS = 28
_THIRTEEN_WEEK_DAYS = 91
_YOY_DAYS = 365
# TGA level-change lookback tolerance: DTS is near-daily (business-day)
# cadence, so a single shared slack covers both the 4w and 13w lookups
# (mirrors housing.py's weekly-series slack, judgment call 3).
_LEVEL_LOOKBACK_SLACK_DAYS = 10
# Minimum ACTUAL rows required inside a trailing window before this composer
# trusts the sum -- DTS deposit days are business-day cadence (~5/7 of
# calendar days); floors sized conservatively below that expectation
# (judgment call 5).
_MIN_ROWS_4W = 10
_MIN_ROWS_13W = 30

# Auction recent/baseline windows (judgment calls 6-7).
_AUCTION_RECENT_WINDOW = 8          # mirrors config.yml treasury_auctions.trailing
_AUCTION_MIN_RECENT = 5             # mirrors config.yml treasury_auctions.min_trailing
_AUCTION_BASELINE_WINDOW_DAYS = 365
_AUCTION_MIN_BASELINE = 10

# Contradiction flat bands (judgment call 8) + the "calm" owner vocabulary
# member (judgment call 9; scripts/build_bonds.py HEALTH_COLOR = {healthy,
# mixed, stressed}).
_ISSUANCE_PACE_FLAT_BAND_MN_PER_DAY = 1000.0
_AUCTION_DEMAND_FLAT_BAND = 0.10
_CALM_BOND_DESK_LABELS = frozenset({"healthy"})

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
    "tga_level", "net_issuance_sum_13w", "auction_bid_to_cover_recent_avg",
    "household_debt_service_ratio_level", "bond_desk_health_score_level",
)
_TRACKED_CORRECTION_METRICS = (
    "tga_level", "tga_impulse_4w", "tga_impulse_13w",
    "net_issuance_sum_4w", "net_issuance_sum_13w",
    "net_issuance_pace_delta_4w_vs_13w_avg_daily",
    "withheld_taxes_level", "withheld_taxes_sum_4w", "withheld_taxes_yoy_4w",
    "auction_bid_to_cover_recent_avg", "auction_bid_to_cover_baseline_avg",
    "auction_demand_spread_recent_vs_baseline",
    "household_debt_service_ratio_level", "credit_gap_level",
    "bond_desk_health_score_level", "bond_desk_health_label", "bond_desk_cycle_phase",
)

# NOT_COVERED remainder: architecture 10.12's "Required composition" legs this
# estate cannot fill (the load-bearing gap, see module docstring). Each tuple
# is (metric_id, value_type, unit, gap-specific transformation note).
_NOT_COVERED_REMAINDER = (
    ("debt_outstanding_total", "number", "usd_mn",
     "Total public debt outstanding needs a Debt-to-the-Penny (or MSPD) "
     "collector; no such collector or store exists anywhere in this estate "
     "(census 2026-09-04). This composer never integrates net_issuance into a "
     "fabricated stock -- a flow's running sum is not a level without a real "
     "anchor this estate does not have (architecture 10.12's own named "
     "debt-stock/flow-confusion failure state)."),
    ("debt_held_by_public", "number", "usd_mn",
     "Debt held by the public (the total-debt-outstanding split) needs the "
     "same Debt-to-the-Penny/MSPD collector this estate does not have; not "
     "estimated from net_issuance."),
    ("debt_intragovernmental_holdings", "number", "usd_mn",
     "Intragovernmental holdings (the other total-debt-outstanding split) "
     "needs the same absent Debt-to-the-Penny/MSPD collector."),
    ("fiscal_deficit_primary_balance", "number", "usd_mn",
     "The deficit/primary balance and receipts/outlays split needs a Monthly "
     "Treasury Statement (MTS) collector this estate does not have. "
     "net_issuance is a FINANCING flow (how a deficit gets funded), not the "
     "deficit itself, and this composer never conflates the two."),
    ("net_interest_burden", "number", "usd_mn",
     "Net interest burden / effective financing cost needs an MTS or "
     "budget-function interest-expense series this estate does not collect; "
     "not estimated from the TGA or auction high_yield legs."),
    ("debt_weighted_average_maturity", "number", "years",
     "A maturity/issuance schedule (weighted-average maturity, the "
     "refinancing wall) needs an MSPD-equivalent WAM ladder collector this "
     "estate does not have; auction_rows carries only per-auction "
     "tenor_years, not the outstanding-stock maturity distribution."),
    ("auction_tail_bp", "basis_points", "bp",
     "The auction 'tail' (high yield minus the when-issued yield) needs a "
     "when-issued-yield column this composer's fixed five-column "
     "auction_rows contract (auction_date, security_type, tenor_years, "
     "bid_to_cover, high_yield) does not carry."),
    ("auction_indirect_bidder_share", "ratio", "ratio_0_1",
     "Indirect/direct bidder share needs bidder-class columns this "
     "composer's fixed five-column auction_rows contract does not carry."),
    ("foreign_holdings_tic", "number", "usd_mn",
     "Foreign holdings and demand context need a Treasury International "
     "Capital (TIC) collector; no such collector or store exists anywhere in "
     "this estate (census 2026-09-04)."),
    ("contingent_liabilities", "number", "usd_mn",
     "Contingent liabilities (shown separately from recorded debt per "
     "architecture 10.12) have no collector or store in this estate; never "
     "estimated from recorded-debt series."),
    ("debt_to_gdp_ratio", "percent", "percent_of_gdp",
     "Debt-to-GDP needs BOTH the absent debt-stock numerator (see "
     "debt_outstanding_total) and a GDP denominator this composer's scoped "
     "owner inputs do not carry; not estimated from either leg alone."),
)


# --------------------------------------------------------------------------- #
# small pure helpers (deliberately self-contained -- no cross-import from any
# sibling composer, mirrors housing.py / liquidity_central_banks.py so this
# file can be added without touching any other module)
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
    """Shared release-cadence law (see module docstring's per-source
    derivations). ``value_present=False`` always reads SOURCE_FAILED; an
    ``asof`` in the future relative to ``built_at`` (a clock inversion) also
    reads SOURCE_FAILED rather than a nonsensical CURRENT."""
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


def _pct_change(cur: float | None, prior: float | None) -> float | None:
    if cur is None or prior is None or prior == 0:
        return None
    return _round((cur / prior - 1.0) * 100.0, 4)


# --------------------------------------------------------------------------- #
# raw-row handling (this composer, like housing.py, is handed plain level/flow
# rows instead of a pre-aggregated owner JSON for treasury_frames/bis_frames)
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
    masquerading as a fresh 4w/13w comparison point."""
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


def _level_change(rows: list[tuple[_dt.date, float]],
                   latest: tuple[_dt.date, float] | None,
                   window_days: int, slack_days: int) -> float | None:
    if latest is None:
        return None
    prior = _value_before_or_at(rows, latest[0] - _dt.timedelta(days=window_days), slack_days)
    if prior is None:
        return None
    return _round(latest[1] - prior[1], 4)


def _window_rows(rows: list[tuple[_dt.date, float]], end_date: _dt.date,
                  window_days: int) -> list[tuple[_dt.date, float]]:
    """Rows with ``end_date - window_days < d <= end_date`` -- a half-open
    trailing calendar window of ``window_days`` days ending at (and
    including) ``end_date``."""
    start = end_date - _dt.timedelta(days=window_days)
    return [(d, v) for d, v in rows if start < d <= end_date]


def _trailing_sum(rows: list[tuple[_dt.date, float]], end_date: _dt.date | None,
                   window_days: int, min_rows: int) -> tuple[float | None, int]:
    """Sum of a FLOW series over a trailing calendar window, refused (never a
    fabricated 0) when fewer than ``min_rows`` actual observations land inside
    it -- "never ffill a flow" (engine/conditions.py's own comment for this
    exact series)."""
    if end_date is None:
        return None, 0
    sub = _window_rows(rows, end_date, window_days)
    if len(sub) < min_rows:
        return None, len(sub)
    return _round(sum(v for _, v in sub), 4), len(sub)


# --------------------------------------------------------------------------- #
# auction-row handling
# --------------------------------------------------------------------------- #
def _clean_auction_rows(rows: Any) -> list[dict]:
    """Defensively normalize caller-supplied auction dict rows: keep only rows
    with a parseable ``auction_date``; coerce ``tenor_years``/``bid_to_cover``/
    ``high_yield`` to float-or-None, keep ``security_type`` as a string or
    None. Extra dict keys are ignored (an unconsumed-field negative control).
    Never raises on malformed input; sorted ascending by date (stable, so
    same-day rows keep the caller's own order)."""
    if not rows:
        return []
    out: list[dict] = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        d = _parse_date(row.get("auction_date"))
        if d is None:
            continue
        sec = row.get("security_type")
        out.append({
            "auction_date": d,
            "security_type": sec if isinstance(sec, str) else None,
            "tenor_years": _num(row.get("tenor_years")),
            "bid_to_cover": _num(row.get("bid_to_cover")),
            "high_yield": _num(row.get("high_yield")),
        })
    out.sort(key=lambda r: r["auction_date"])
    return out


def _recent_auction_stats(with_btc: list[dict], window: int,
                           min_n: int) -> tuple[float | None, int]:
    """Mean bid_to_cover over the most recent up-to-``window`` auctions that
    HAVE a non-null bid_to_cover (chronologically last) -- refused (None)
    when fewer than ``min_n`` such auctions exist at all; published over
    however many ARE available otherwise (never padded to ``window`` with a
    fabricated value; judgment call 6)."""
    n = len(with_btc)
    if n < min_n:
        return None, n
    subset = with_btc[-window:]
    vals = [a["bid_to_cover"] for a in subset]
    return _round(sum(vals) / len(vals), 6), len(subset)


def _baseline_auction_stats(with_btc: list[dict], end_date: _dt.date | None,
                             window_days: int, min_n: int) -> tuple[float | None, int]:
    """Mean bid_to_cover over auctions (with non-null bid_to_cover) landing in
    the trailing ``window_days`` ending at ``end_date`` -- refused when fewer
    than ``min_n`` qualify (judgment call 7)."""
    if end_date is None:
        return None, 0
    start = end_date - _dt.timedelta(days=window_days)
    subset = [a for a in with_btc if start < a["auction_date"] <= end_date]
    if len(subset) < min_n:
        return None, len(subset)
    vals = [a["bid_to_cover"] for a in subset]
    return _round(sum(vals) / len(vals), 6), len(subset)


def _issuance_pace_delta(sum4w: float | None, sum13w: float | None) -> float | None:
    """Trailing-4-week average DAILY pace minus trailing-13-week average daily
    pace, in $mn/day -- a self-referential acceleration read that needs no
    external historical baseline (a difference, never a ratio, so it is never
    undefined or sign-flipped by a near-zero or negative denominator)."""
    if sum4w is None or sum13w is None:
        return None
    avg4 = sum4w / _FOUR_WEEK_DAYS
    avg13 = sum13w / _THIRTEEN_WEEK_DAYS
    return _round(avg4 - avg13, 4)


# --------------------------------------------------------------------------- #
# metric / component builders
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


def _component(component_id: str, label_en: str, label_zh: str, *, present: bool,
               freshness: str, source_asof: str | None, required: bool) -> dict:
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
        "source_asof": source_asof,
        "null_reason": null_reason,
    }


# --------------------------------------------------------------------------- #
# the composer
# --------------------------------------------------------------------------- #
def compose(treasury_frames: Mapping[str, Any] | None,
            auction_rows: Sequence[Any] | None,
            bis_frames: Mapping[str, Any] | None,
            bonds_latest: Mapping[str, Any] | None, *, built_at: str,
            prior_snapshot: Mapping[str, Any] | None = None,
            code_version: str | None = None) -> dict:
    """Project ``treasury_frames`` + ``auction_rows`` + ``bis_frames`` +
    ``bonds_latest`` (see module docstring) into an UNSEALED snapshot body.
    The builder seals it via ``contract.finalize``."""
    tf = treasury_frames if isinstance(treasury_frames, Mapping) else {}
    bf = bis_frames if isinstance(bis_frames, Mapping) else {}
    bl = bonds_latest if isinstance(bonds_latest, Mapping) else None

    tga = _clean_rows(tf.get(TGA_KEY))
    net_issuance = _clean_rows(tf.get(NET_ISSUANCE_KEY))
    withheld = _clean_rows(tf.get(WITHHELD_KEY))
    dsr = _clean_rows(bf.get(BIS_DSR_KEY))
    gap = _clean_rows(bf.get(BIS_GAP_KEY))
    auctions = _clean_auction_rows(auction_rows)
    with_btc = [a for a in auctions if a["bid_to_cover"] is not None]

    tga_latest = _latest(tga)
    ni_latest = _latest(net_issuance)
    wt_latest = _latest(withheld)
    dsr_latest = _latest(dsr)
    gap_latest = _latest(gap)
    auc_latest = auctions[-1] if auctions else None
    auc_btc_latest = with_btc[-1] if with_btc else None
    bonds_date = _parse_date(bl.get("date")) if bl else None

    tga_fresh = _cadence_freshness(built_at, tga_latest[0] if tga_latest else None,
                                    _DTS_CADENCE_DAYS, _DTS_GRACE_DAYS, bool(tga_latest))
    ni_fresh = _cadence_freshness(built_at, ni_latest[0] if ni_latest else None,
                                   _DTS_CADENCE_DAYS, _DTS_GRACE_DAYS, bool(ni_latest))
    wt_fresh = _cadence_freshness(built_at, wt_latest[0] if wt_latest else None,
                                   _DTS_CADENCE_DAYS, _DTS_GRACE_DAYS, bool(wt_latest))
    auc_fresh = _cadence_freshness(built_at, auc_btc_latest["auction_date"] if auc_btc_latest else None,
                                    _AUCTION_CADENCE_DAYS, _AUCTION_GRACE_DAYS, bool(auc_btc_latest))
    auc_latest_fresh = _cadence_freshness(built_at, auc_latest["auction_date"] if auc_latest else None,
                                           _AUCTION_CADENCE_DAYS, _AUCTION_GRACE_DAYS, bool(auc_latest))
    dsr_fresh = _cadence_freshness(built_at, dsr_latest[0] if dsr_latest else None,
                                    _BIS_CADENCE_DAYS, _BIS_GRACE_DAYS, bool(dsr_latest))
    gap_fresh = _cadence_freshness(built_at, gap_latest[0] if gap_latest else None,
                                    _BIS_CADENCE_DAYS, _BIS_GRACE_DAYS, bool(gap_latest))
    bonds_fresh = _cadence_freshness(built_at, bonds_date, _BONDS_CADENCE_DAYS,
                                      _BONDS_GRACE_DAYS, bonds_date is not None)

    # -- derived reads needed BEFORE building the metric list (contradiction
    # detection needs the finished values; mirrors housing.py/liquidity_
    # central_banks.py's compute-then-detect order) -----------------------
    ni_sum4, ni_sum4_n = _trailing_sum(net_issuance, ni_latest[0] if ni_latest else None,
                                        _FOUR_WEEK_DAYS, _MIN_ROWS_4W)
    ni_sum13, ni_sum13_n = _trailing_sum(net_issuance, ni_latest[0] if ni_latest else None,
                                          _THIRTEEN_WEEK_DAYS, _MIN_ROWS_13W)
    pace_delta = _issuance_pace_delta(ni_sum4, ni_sum13)

    wt_sum4, wt_sum4_n = _trailing_sum(withheld, wt_latest[0] if wt_latest else None,
                                        _FOUR_WEEK_DAYS, _MIN_ROWS_4W)
    wt_prior_end = (wt_latest[0] - _dt.timedelta(days=_YOY_DAYS)) if wt_latest else None
    wt_sum4_prior, wt_sum4_prior_n = _trailing_sum(withheld, wt_prior_end, _FOUR_WEEK_DAYS, _MIN_ROWS_4W)
    wt_yoy = _pct_change(wt_sum4, wt_sum4_prior)
    if wt_latest is None:
        wt_yoy_null = None  # let _metric default to SOURCE_FAILED
    elif wt_sum4 is None or wt_sum4_prior is None:
        wt_yoy_null = "INSUFFICIENT_HISTORY"
    elif wt_sum4_prior == 0:
        wt_yoy_null = "COMPUTATION_REFUSED"
    else:
        wt_yoy_null = None

    recent_avg, recent_n = _recent_auction_stats(with_btc, _AUCTION_RECENT_WINDOW, _AUCTION_MIN_RECENT)
    baseline_avg, baseline_n = _baseline_auction_stats(
        with_btc, auc_btc_latest["auction_date"] if auc_btc_latest else None,
        _AUCTION_BASELINE_WINDOW_DAYS, _AUCTION_MIN_BASELINE)
    demand_spread = (_round(recent_avg - baseline_avg, 6)
                      if (recent_avg is not None and baseline_avg is not None) else None)

    health_label = bl.get("health_label") if bl else None
    contradictions = _detect_contradiction(pace_delta, demand_spread, health_label)
    fired_kinds = {c["kind"] for c in contradictions}

    ctx = {
        "built_at": built_at,
        "tga": tga, "net_issuance": net_issuance, "withheld": withheld,
        "dsr": dsr, "gap": gap, "auctions": auctions, "with_btc": with_btc,
        "tga_latest": tga_latest, "ni_latest": ni_latest, "wt_latest": wt_latest,
        "dsr_latest": dsr_latest, "gap_latest": gap_latest,
        "auc_latest": auc_latest, "auc_btc_latest": auc_btc_latest,
        "bonds": bl, "bonds_date": bonds_date,
        "tga_fresh": tga_fresh, "ni_fresh": ni_fresh, "wt_fresh": wt_fresh,
        "auc_fresh": auc_fresh, "auc_latest_fresh": auc_latest_fresh,
        "dsr_fresh": dsr_fresh, "gap_fresh": gap_fresh, "bonds_fresh": bonds_fresh,
        "ni_sum4": ni_sum4, "ni_sum4_n": ni_sum4_n,
        "ni_sum13": ni_sum13, "ni_sum13_n": ni_sum13_n,
        "pace_delta": pace_delta,
        "wt_sum4": wt_sum4, "wt_sum4_n": wt_sum4_n, "wt_yoy": wt_yoy, "wt_yoy_null": wt_yoy_null,
        "recent_avg": recent_avg, "recent_n": recent_n,
        "baseline_avg": baseline_avg, "baseline_n": baseline_n,
        "demand_spread": demand_spread,
    }

    metrics = _metrics(ctx, fired_kinds)
    metrics_by_id = {m["metric_id"]: m["value"] for m in metrics}

    required_avail, optional_avail = _required_availability(ctx)
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
    for latest in (tga_latest, ni_latest, wt_latest):
        if latest:
            dates.append(latest[0])
    if auc_btc_latest:
        dates.append(auc_btc_latest["auction_date"])
    effective_date = _iso(max(dates)) if dates else None

    headline = _headline(effective_date, prior_snapshot)
    changes = _changes(metrics_by_id, prior_snapshot)

    snapshot = {
        "schema": {"contract": "mastermind.macro_workspace_snapshot.v1", "version": "1.0.0"},
        "workspace": {
            "id": WORKSPACE_ID,
            "title": _bil("National Debt & Liabilities", "国债与负债"),
            "subtitle": _bil(
                "Refinancing/issuance pressure x fiscal capacity/interest-burden resilience",
                "再融资/发行压力 × 财政能力/利息负担韧性"),
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
        "implications": {"items": _implications(ctx, metrics_by_id, contradictions, worst, coverage_ratio)},
        "scenario_contract": _scenario_contract(),
        "alert_contract": _alert_contract(),
        "sources": {"items": _sources(ctx)},
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
# contradiction detection
# --------------------------------------------------------------------------- #
def _detect_contradiction(pace_delta: float | None, demand_spread: float | None,
                           health_label: Any) -> list[dict]:
    """Heavy/accelerating issuance + weakening auction demand + a bond desk
    still reading "healthy" (see module docstring + judgment calls 8-9). All
    three legs are genuine owner-native-derived values; the only composer-
    invented numbers are the two disclosed flat bands. Silent whenever any leg
    is absent or inside its flat band -- never forced."""
    if pace_delta is None or demand_spread is None or health_label is None:
        return []
    if pace_delta <= _ISSUANCE_PACE_FLAT_BAND_MN_PER_DAY:
        return []
    if demand_spread > -_AUCTION_DEMAND_FLAT_BAND:
        return []
    if health_label not in _CALM_BOND_DESK_LABELS:
        return []
    return [{
        "kind": "issuance_demand_stress_vs_bond_desk_calm",
        "en": (f"Net Treasury issuance is accelerating ({pace_delta:+.0f} $mn/day faster over "
               f"the trailing 4 weeks than the trailing 13-week pace) while recent auction "
               f"demand is weakening ({demand_spread:+.3f} bid-to-cover vs the trailing-year "
               "baseline), yet the bond desk's own health read still says 'healthy' -- a "
               "supply/demand stress signal the desk has not itself flagged."),
        "zh": (f"美国国债净发行正在加速（近4周日均节奏比近13周日均节奏快{pace_delta:+.0f}百万美元/日），"
               f"而近期拍卖需求正在走弱（投标倍数较近一年基准变化{demand_spread:+.3f}），"
               "但债券台面自身的健康读数仍为“健康”——这是台面自身尚未标记的供需压力信号。"),
        "components": [
            "net_issuance_pace_delta_4w_vs_13w_avg_daily",
            "auction_demand_spread_recent_vs_baseline",
            "bond_desk_health_label",
        ],
    }]


# --------------------------------------------------------------------------- #
# availability
# --------------------------------------------------------------------------- #
def _required_availability(ctx: dict) -> tuple[list[dict], list[dict]]:
    tga_latest, ni_latest, wt_latest = ctx["tga_latest"], ctx["ni_latest"], ctx["wt_latest"]
    auc_btc_latest = ctx["auc_btc_latest"]
    dsr_latest, gap_latest = ctx["dsr_latest"], ctx["gap_latest"]
    specs = [
        ("tga", "Treasury General Account (TGA) balance", "财政部一般账户（TGA）余额",
         bool(tga_latest), ctx["tga_fresh"], _iso(tga_latest[0]) if tga_latest else None, True),
        ("net_issuance", "Net Treasury issuance", "美国国债净发行",
         bool(ni_latest), ctx["ni_fresh"], _iso(ni_latest[0]) if ni_latest else None, True),
        ("withheld_taxes", "Withheld income & employment-tax deposits", "预扣所得税与雇佣税存款",
         bool(wt_latest), ctx["wt_fresh"], _iso(wt_latest[0]) if wt_latest else None, True),
        ("auction_demand", "Treasury auction bid-to-cover demand", "美国国债拍卖投标倍数需求",
         bool(auc_btc_latest), ctx["auc_fresh"],
         _iso(auc_btc_latest["auction_date"]) if auc_btc_latest else None, True),
        ("bis_household_dsr", "BIS household debt-service ratio", "BIS家庭偿债比率",
         bool(dsr_latest), ctx["dsr_fresh"], _iso(dsr_latest[0]) if dsr_latest else None, False),
        ("bis_credit_gap", "BIS credit-to-GDP gap", "BIS信贷/GDP缺口",
         bool(gap_latest), ctx["gap_fresh"], _iso(gap_latest[0]) if gap_latest else None, False),
        ("bond_desk_state", "Bond-desk health/cycle-phase state", "债券台面健康/周期阶段状态",
         ctx["bonds_date"] is not None, ctx["bonds_fresh"], _iso(ctx["bonds_date"]), False),
    ]
    rows = [_component(cid, en, zh, present=p, freshness=fr, source_asof=asof, required=req)
            for cid, en, zh, p, fr, asof, req in specs]
    required_rows = [r for r in rows if r["required"]]
    optional_rows = [r for r in rows if not r["required"]]
    return required_rows, optional_rows


# --------------------------------------------------------------------------- #
# metrics
# --------------------------------------------------------------------------- #
def _metrics(ctx: dict, fired_kinds: set[str]) -> list[dict]:
    items: list[dict] = []

    # -- TGA: level + 4w/13w impulse (drain/build direction) ----------------- #
    tga_latest = ctx["tga_latest"]
    tga_level = tga_latest[1] if tga_latest else None
    tga_date = _iso(tga_latest[0]) if tga_latest else None
    items.append(_metric(
        "tga_level", tga_level, "number", "usd_mn", "level",
        "higher_more_cash_parked_at_the_fed_mechanically_tighter_bank_reserves",
        _TGA_PATH, "treasury_dts.tga.tga_mn", tga_date, ctx["tga_fresh"],
        source_refs=["TREASURY_DTS:operating_cash_balance"],
        transformation=(
            "US Treasury General Account (TGA) daily closing balance, Daily Treasury "
            "Statement 'Deposits and Withdrawals of Operating Cash' (Table II via "
            "FiscalData), stored and published in $ millions (never rescaled to "
            "billions -- judgment call 2). A rising TGA level mechanically DRAINS "
            "bank reserves as Treasury pulls cash into its own account; a falling "
            "level mechanically INJECTS reserves as Treasury spends the balance down."
        ),
    ))
    tga_imp4 = _level_change(ctx["tga"], tga_latest, _FOUR_WEEK_DAYS, _LEVEL_LOOKBACK_SLACK_DAYS)
    items.append(_metric(
        "tga_impulse_4w", tga_imp4, "number", "usd_mn", "trailing_4w_level_change",
        "positive_is_tga_building_reserve_draining_negative_is_draining_reserve_injecting",
        _TGA_PATH, "treasury_dts.tga.tga_mn", tga_date, ctx["tga_fresh"],
        source_refs=["TREASURY_DTS:operating_cash_balance"],
        transformation=(
            "Current TGA level minus the level roughly 4 weeks (28 days) prior, in $ "
            f"millions. Refused when no observation lands within "
            f"{_LEVEL_LOOKBACK_SLACK_DAYS} days of that lookback target -- a "
            "self-referential calendar-window read, distinct from engine/"
            "treasury_watch.py's own extremum-anchored episode detector (judgment "
            "call 3, never imported or re-run by this composer)."
        ),
        null_reason="INSUFFICIENT_HISTORY" if tga_latest else None,
    ))
    tga_imp13 = _level_change(ctx["tga"], tga_latest, _THIRTEEN_WEEK_DAYS, _LEVEL_LOOKBACK_SLACK_DAYS)
    items.append(_metric(
        "tga_impulse_13w", tga_imp13, "number", "usd_mn", "trailing_13w_level_change",
        "positive_is_tga_building_reserve_draining_negative_is_draining_reserve_injecting",
        _TGA_PATH, "treasury_dts.tga.tga_mn", tga_date, ctx["tga_fresh"],
        source_refs=["TREASURY_DTS:operating_cash_balance"],
        transformation=(
            "Current TGA level minus the level roughly 13 weeks (91 days) prior, in "
            f"$ millions. Refused when no observation lands within "
            f"{_LEVEL_LOOKBACK_SLACK_DAYS} days of that lookback target."
        ),
        null_reason="INSUFFICIENT_HISTORY" if tga_latest else None,
    ))

    # -- net issuance: 4w/13w sums + a self-referential pace-acceleration read #
    ni_latest = ctx["ni_latest"]
    ni_date = _iso(ni_latest[0]) if ni_latest else None
    items.append(_metric(
        "net_issuance_sum_4w", ctx["ni_sum4"], "number", "usd_mn", "trailing_4w_sum",
        "higher_more_supply_pressure", _NET_ISSUANCE_PATH,
        "treasury_dts.net_issuance.net_issuance_mn", ni_date, ctx["ni_fresh"],
        source_refs=["TREASURY_DTS:net_issuance"],
        transformation=(
            "Sum of Treasury net issuance (gross issues minus redemptions, a daily "
            "flow) over the trailing 4 calendar weeks (28 days), in $ millions. "
            f"Refused (never a fabricated 0) when fewer than {_MIN_ROWS_4W} actual "
            "observations land inside the window -- 'never ffill a flow.'"
        ),
        null_reason="INSUFFICIENT_HISTORY" if ni_latest else None,
    ))
    items.append(_metric(
        "net_issuance_sum_13w", ctx["ni_sum13"], "number", "usd_mn", "trailing_13w_sum",
        "higher_more_supply_pressure", _NET_ISSUANCE_PATH,
        "treasury_dts.net_issuance.net_issuance_mn", ni_date, ctx["ni_fresh"],
        source_refs=["TREASURY_DTS:net_issuance"],
        transformation=(
            "Sum of Treasury net issuance over the trailing 13 calendar weeks (91 "
            f"days), in $ millions. Refused when fewer than {_MIN_ROWS_13W} actual "
            "observations land inside the window."
        ),
        null_reason="INSUFFICIENT_HISTORY" if ni_latest else None,
    ))
    pace_disagree = ("issuance_demand_stress_vs_bond_desk_calm" in fired_kinds
                      and ctx["pace_delta"] is not None)
    items.append(_metric(
        "net_issuance_pace_delta_4w_vs_13w_avg_daily", ctx["pace_delta"], "number",
        "usd_mn_per_day", "trailing_4w_avg_daily_minus_trailing_13w_avg_daily",
        "positive_is_accelerating_issuance_pace", _NET_ISSUANCE_PATH,
        "treasury_dts.net_issuance.net_issuance_mn", ni_date, ctx["ni_fresh"],
        source_refs=["TREASURY_DTS:net_issuance"],
        transformation=(
            "Trailing-4-week average daily net-issuance pace minus the trailing-"
            "13-week average daily pace, in $mn/day -- a self-referential "
            "acceleration read needing no external historical baseline (a "
            "difference, never a ratio, so it is never undefined by a near-zero "
            "or negative denominator)."
        ),
        status="DISAGREEMENT" if pace_disagree else "PRESENT",
        null_reason=("DISAGREEMENT" if pace_disagree else
                      ("INSUFFICIENT_HISTORY" if ni_latest and ctx["pace_delta"] is None else None)),
    ))

    # -- withheld taxes: level + 4w sum + 4w-sum YoY (revenue nowcast) -------- #
    wt_latest = ctx["wt_latest"]
    wt_level = wt_latest[1] if wt_latest else None
    wt_date = _iso(wt_latest[0]) if wt_latest else None
    items.append(_metric(
        "withheld_taxes_level", wt_level, "number", "usd_mn", "level",
        "higher_more_daily_withheld_receipts", _WITHHELD_PATH,
        "treasury_dts.withheld_taxes.withheld_tax_mn", wt_date, ctx["wt_fresh"],
        source_refs=["TREASURY_DTS:withheld_taxes"],
        transformation=(
            "Latest single-day withheld income & employment-tax deposit, Daily "
            "Treasury Statement, in $ millions -- a noisy daily print; the trailing "
            "sum/YoY legs below are the meaningful revenue-nowcast reads."
        ),
    ))
    items.append(_metric(
        "withheld_taxes_sum_4w", ctx["wt_sum4"], "number", "usd_mn", "trailing_4w_sum",
        "higher_more_trailing_revenue", _WITHHELD_PATH,
        "treasury_dts.withheld_taxes.withheld_tax_mn", wt_date, ctx["wt_fresh"],
        source_refs=["TREASURY_DTS:withheld_taxes"],
        transformation=(
            "Sum of withheld income & employment-tax deposits over the trailing 4 "
            f"calendar weeks (28 days), in $ millions. Refused when fewer than "
            f"{_MIN_ROWS_4W} actual deposit days land inside the window -- 'never "
            "ffill a flow' (mirrors engine/conditions.py's own comment for this "
            "exact series, though this composer deliberately uses a tighter "
            "calendar-day window than that module's 63-row convention; see "
            "judgment call 4 / the withheld_taxes_window_divergence_disclosure "
            "implication)."
        ),
        null_reason="INSUFFICIENT_HISTORY" if wt_latest else None,
    ))
    items.append(_metric(
        "withheld_taxes_yoy_4w", ctx["wt_yoy"], "percent", "percent",
        "yoy_pct_change_of_trailing_4w_sum",
        "higher_stronger_income_and_employment_growth", _WITHHELD_PATH,
        "treasury_dts.withheld_taxes.withheld_tax_mn", wt_date, ctx["wt_fresh"],
        source_refs=["TREASURY_DTS:withheld_taxes"],
        transformation=(
            "Percent change of the trailing-4-week withheld-tax sum versus the "
            "same 4-week window ~365 days prior -- a real-economy wage/employment "
            f"revenue nowcast. Refused when either window has fewer than "
            f"{_MIN_ROWS_4W} actual deposit days, or when the year-ago window sums "
            "to exactly zero (undefined percent change)."
        ),
        null_reason=ctx["wt_yoy_null"],
    ))

    # -- auction demand: recent vs trailing-year baseline, + latest passthrough #
    demand_disagree = ("issuance_demand_stress_vs_bond_desk_calm" in fired_kinds
                        and ctx["demand_spread"] is not None)
    with_btc = ctx["with_btc"]
    recent_null = "INSUFFICIENT_HISTORY" if with_btc else None
    items.append(_metric(
        "auction_bid_to_cover_recent_avg", ctx["recent_avg"], "ratio", "bid_to_cover_ratio",
        f"trailing_up_to_{_AUCTION_RECENT_WINDOW}_auctions_with_btc",
        "higher_stronger_auction_demand", _AUCTIONS_PATH,
        "treasury_auctions.bid_to_cover", _iso(ctx["auc_btc_latest"]["auction_date"]) if ctx["auc_btc_latest"] else None,
        ctx["auc_fresh"], source_refs=["TREASURY_AUCTIONS:bid_to_cover"],
        transformation=(
            f"Mean bid-to-cover over the most recent up to {_AUCTION_RECENT_WINDOW} "
            f"auctions with a reported bid_to_cover, pooled ACROSS all security "
            f"types (cross-tenor, not the owner's own same-tenor windowing; "
            f"judgment call 6). Refused when fewer than {_AUCTION_MIN_RECENT} such "
            "auctions exist at all; published over however many are available "
            "otherwise (disclosed via auction_recent_window_count, never padded)."
        ),
        null_reason=recent_null,
    ))
    baseline_null = "INSUFFICIENT_HISTORY" if with_btc else None
    items.append(_metric(
        "auction_bid_to_cover_baseline_avg", ctx["baseline_avg"], "ratio", "bid_to_cover_ratio",
        f"trailing_{_AUCTION_BASELINE_WINDOW_DAYS}d_auctions_with_btc",
        "higher_stronger_auction_demand", _AUCTIONS_PATH,
        "treasury_auctions.bid_to_cover", _iso(ctx["auc_btc_latest"]["auction_date"]) if ctx["auc_btc_latest"] else None,
        ctx["auc_fresh"], source_refs=["TREASURY_AUCTIONS:bid_to_cover"],
        transformation=(
            f"Mean bid-to-cover over auctions with a reported bid_to_cover landing "
            f"in the trailing {_AUCTION_BASELINE_WINDOW_DAYS} calendar days ending "
            "at the latest such auction's own date (never built_at), cross-tenor "
            f"(judgment call 7). Refused when fewer than {_AUCTION_MIN_BASELINE} "
            "such auctions qualify."
        ),
        null_reason=baseline_null,
    ))
    items.append(_metric(
        "auction_demand_spread_recent_vs_baseline", ctx["demand_spread"], "number",
        "bid_to_cover_ratio_pts", "recent_avg_minus_baseline_avg",
        "positive_is_strengthening_demand_vs_baseline", _AUCTIONS_PATH,
        "treasury_auctions.bid_to_cover", _iso(ctx["auc_btc_latest"]["auction_date"]) if ctx["auc_btc_latest"] else None,
        ctx["auc_fresh"], source_refs=["TREASURY_AUCTIONS:bid_to_cover"],
        transformation=(
            "auction_bid_to_cover_recent_avg minus auction_bid_to_cover_baseline_avg "
            "-- a leg-floor read: refused (never a fabricated one-sided value) unless "
            "BOTH legs compute."
        ),
        status="DISAGREEMENT" if demand_disagree else "PRESENT",
        null_reason=("DISAGREEMENT" if demand_disagree else baseline_null),
    ))
    items.append(_metric(
        "auction_recent_window_count", ctx["recent_n"], "count", "auctions",
        "count_of_auctions_actually_used", "n/a", _AUCTIONS_PATH,
        "treasury_auctions.bid_to_cover", None, ctx["auc_fresh"],
        source_refs=["TREASURY_AUCTIONS:bid_to_cover"],
        transformation=(
            "How many auctions actually fed auction_bid_to_cover_recent_avg (may be "
            f"fewer than the {_AUCTION_RECENT_WINDOW}-auction target window; a "
            "coverage disclosure, always published, never itself refused)."
        ),
    ))
    items.append(_metric(
        "auction_baseline_window_count", ctx["baseline_n"], "count", "auctions",
        "count_of_auctions_actually_used", "n/a", _AUCTIONS_PATH,
        "treasury_auctions.bid_to_cover", None, ctx["auc_fresh"],
        source_refs=["TREASURY_AUCTIONS:bid_to_cover"],
        transformation=(
            "How many auctions actually fed auction_bid_to_cover_baseline_avg (a "
            "coverage disclosure, always published, never itself refused)."
        ),
    ))

    auc_latest = ctx["auc_latest"]
    auc_latest_date = _iso(auc_latest["auction_date"]) if auc_latest else None
    items.append(_metric(
        "auction_latest_bid_to_cover", auc_latest["bid_to_cover"] if auc_latest else None,
        "ratio", "bid_to_cover_ratio", "single_auction_level",
        "higher_stronger_demand_at_that_auction", _AUCTIONS_PATH,
        "treasury_auctions.bid_to_cover", auc_latest_date, ctx["auc_latest_fresh"],
        source_refs=["TREASURY_AUCTIONS:bid_to_cover"],
        transformation="Pass-through of the single most recent auction's own bid_to_cover.",
    ))
    items.append(_metric(
        "auction_latest_high_yield", auc_latest["high_yield"] if auc_latest else None,
        "percent", "percent", "single_auction_level",
        "higher_more_expensive_financing_at_that_auction", _AUCTIONS_PATH,
        "treasury_auctions.high_yield", auc_latest_date, ctx["auc_latest_fresh"],
        source_refs=["TREASURY_AUCTIONS:high_yield"],
        transformation="Pass-through of the single most recent auction's own high (stop-out) yield.",
    ))
    items.append(_metric(
        "auction_latest_security_type", auc_latest["security_type"] if auc_latest else None,
        "categorical", None, "single_auction_level", "n/a", _AUCTIONS_PATH,
        "treasury_auctions.security_type", auc_latest_date, ctx["auc_latest_fresh"],
        source_refs=["TREASURY_AUCTIONS:security_type"],
        transformation="Pass-through of the single most recent auction's own owner-native security_type string.",
    ))
    items.append(_metric(
        "auction_latest_tenor_years", auc_latest["tenor_years"] if auc_latest else None,
        "number", "years", "single_auction_level", "n/a", _AUCTIONS_PATH,
        "treasury_auctions.tenor_years", auc_latest_date, ctx["auc_latest_fresh"],
        source_refs=["TREASURY_AUCTIONS:tenor_years"],
        transformation="Pass-through of the single most recent auction's own tenor in years.",
    ))

    # -- BIS: household DSR + credit-to-GDP gap (attribution-only) ----------- #
    dsr_latest = ctx["dsr_latest"]
    dsr_date = _iso(dsr_latest[0]) if dsr_latest else None
    items.append(_metric(
        "household_debt_service_ratio_level", dsr_latest[1] if dsr_latest else None,
        "percent", "percent_of_disposable_income", "level_quarterly_period_end",
        "higher_more_household_debt_service_burden", _BIS_DSR_PATH,
        "bis.us_dsr.dsr", dsr_date, ctx["dsr_fresh"],
        source_refs=["BIS:us_dsr"],
        transformation=(
            "US household debt-service ratio, Bank for International Settlements "
            "(BIS) quarterly panel, period-END dated (attribution-only rights -- "
            "never rebranded as this estate's own read; judgment call/module "
            "docstring rights note)."
        ),
    ))
    gap_latest = ctx["gap_latest"]
    gap_date = _iso(gap_latest[0]) if gap_latest else None
    items.append(_metric(
        "credit_gap_level", gap_latest[1] if gap_latest else None,
        "number", "pct_pts_of_gdp_trend_gap", "level_quarterly_period_end",
        "higher_more_credit_expansion_relative_to_trend", _BIS_GAP_PATH,
        "bis.us_gap.gap", gap_date, ctx["gap_fresh"],
        source_refs=["BIS:us_gap"],
        transformation=(
            "US total credit-to-GDP gap (credit-to-GDP ratio minus its long-run "
            "trend, in percentage points), Bank for International Settlements "
            "(BIS) quarterly panel, period-END dated (attribution-only rights)."
        ),
    ))

    # -- bond desk: a small coverage-read projection (never the full record) - #
    bl = ctx["bonds"]
    bonds_date_iso = _iso(ctx["bonds_date"])
    health_score = _num(bl.get("health_score")) if bl else None
    items.append(_metric(
        "bond_desk_health_score_level", health_score, "score_0_100", "score_0_100",
        "level", "higher_more_healthy", _BONDS_PATH, "bonds_desk.health_score",
        bonds_date_iso, ctx["bonds_fresh"], source_refs=["BONDS_DESK:latest"],
        transformation=(
            "Owner bond-desk composite health score (0-100), pass-through. A small "
            "coverage read of the owner's own state -- this composer never "
            "republishes the owner's own verdict_en/verdict_zh narrative sentence "
            "(judgment call 10)."
        ),
    ))
    health_label = bl.get("health_label") if bl else None
    label_disagree = ("issuance_demand_stress_vs_bond_desk_calm" in fired_kinds
                       and health_label is not None)
    items.append(_metric(
        "bond_desk_health_label", health_label, "categorical", None, "level", "n/a",
        _BONDS_PATH, "bonds_desk.health_label", bonds_date_iso, ctx["bonds_fresh"],
        source_refs=["BONDS_DESK:latest"],
        transformation=(
            "Owner-native closed vocabulary member: {healthy, mixed, stressed} "
            "(scripts/build_bonds.py). Pass-through, never re-derived."
        ),
        status="DISAGREEMENT" if label_disagree else "PRESENT",
        null_reason="DISAGREEMENT" if label_disagree else None,
    ))
    cycle_phase = bl.get("cycle_phase") if bl else None
    items.append(_metric(
        "bond_desk_cycle_phase", cycle_phase, "categorical", None, "level", "n/a",
        _BONDS_PATH, "bonds_desk.cycle_phase", bonds_date_iso, ctx["bonds_fresh"],
        source_refs=["BONDS_DESK:latest"],
        transformation=(
            "Owner-native closed vocabulary member: {recession, early, mid, late} "
            "(scripts/build_bonds.py). Pass-through, never re-derived."
        ),
    ))

    # -- typed-ABSENT remainder: the load-bearing debt-stock gap -------------- #
    for mid, vtype, unit, note in _NOT_COVERED_REMAINDER:
        items.append(_metric(
            mid, None, vtype, unit, "n/a", "n/a",
            "NONE -- no collector for this leg exists in this estate (census 2026-09-04)",
            "NONE", None, "NOT_COVERED",
            transformation=note, null_reason="NOT_COVERED",
        ))

    return items


# --------------------------------------------------------------------------- #
# headline (always refused -- see module docstring: COMPUTATION_REFUSED, not
# NOT_APPLICABLE -- architecture 10.12 DOES define a two-axis blueprint)
# --------------------------------------------------------------------------- #
def _headline(effective_date, prior_snapshot) -> dict:
    prior_method = _get(prior_snapshot, "headline", "method_version")
    prior_eff = _get(prior_snapshot, "headline", "effective_date")
    return {
        "state_id": None,
        "state_label": {"en": None, "zh": None},
        "subtitle": _bil(
            "Refinancing/issuance pressure x fiscal capacity/interest-burden resilience",
            "再融资/发行压力 × 财政能力/利息负担韧性"),
        "method_version": METHOD_VERSION,
        "effective_date": effective_date,
        "quadrant": {"x": None, "y": None, "x_status": "ABSENT", "y_status": "ABSENT"},
        "prior_state": {"state_id": None, "effective_date": prior_eff, "method_version": prior_method},
        "transition_distance": None,
        "nearest_boundary": {"axis": None, "distance": None, "null_reason": "COMPUTATION_REFUSED"},
        "one_month_vector": {"dx": None, "dy": None, "status": "ABSENT", "null_reason": "COMPUTATION_REFUSED"},
        "hysteresis": {
            "band": 0.0, "applied": False, "held_prior": False,
            "note": (
                "architecture section 10.12 defines a real two-axis blueprint "
                "(refinancing/issuance pressure low-to-high; fiscal capacity/"
                "interest-burden resilience weak-to-strong), but the owner substrate "
                "this composer has cannot fill it in: the x-axis bundles issuance "
                "pressure (computable from net issuance) with REFINANCING pressure "
                "specifically (needs the absent maturity/WAM ladder), and the y-axis "
                "needs a genuine fiscal-capacity/interest-burden composite (debt "
                "stock, net interest expense, revenue -- all absent per the "
                "load-bearing gap). Publishing the issuance-pressure half alone as "
                "the full axis, or inventing a different unnamed axis pair the "
                "architecture never specified, would both fabricate a methodology "
                "the data does not honestly support. The real, computable content "
                "(issuance pressure, auction demand absorption, BIS DSR/credit-gap "
                "levels, the bond-desk coverage passthrough, and a genuine "
                "cross-source contradiction check) is published as real metrics/"
                "drivers/implications instead. See the headline_unavailable "
                "implication for the reader-facing version of this note."
            ),
        },
        "status": "ABSENT",
        "null_reason": "COMPUTATION_REFUSED",
    }


# --------------------------------------------------------------------------- #
# drivers (bucket reuse, disclosed -- see module docstring)
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
        _mk("auction_latest_high_yield", "Latest auction high yield", "最近拍卖最高收益率",
            "treasury_auctions.high_yield", metrics_by_id.get("auction_latest_high_yield"), "percent",
            "bucket reuse: published under drivers.rate_side because the contract's driver "
            "bucket pair is fixed as rate_side/balance_sheet -- see the driver_bucket_naming_note "
            "implication"),
        _mk("household_debt_service_ratio_level", "Household debt-service ratio (BIS)", "家庭偿债比率（BIS）",
            "bis.us_dsr.dsr", metrics_by_id.get("household_debt_service_ratio_level"), "percent",
            "bucket reuse: see auction_latest_high_yield's note; BIS attribution-only"),
        _mk("credit_gap_level", "Credit-to-GDP gap (BIS)", "信贷/GDP缺口（BIS）",
            "bis.us_gap.gap", metrics_by_id.get("credit_gap_level"), "pct_pts_of_gdp_trend_gap",
            "bucket reuse: see auction_latest_high_yield's note; BIS attribution-only"),
    ]
    balance_sheet = [
        _mk("tga_impulse_13w", "TGA impulse (13w)", "TGA脉冲（13周）",
            "treasury_dts.tga.tga_mn", metrics_by_id.get("tga_impulse_13w"), "usd_mn",
            "positive = TGA building (reserve drain); negative = TGA draining (reserve "
            "injection) -- TGA's own placement here is a near-literal fit (it IS "
            "Treasury's own account balance)"),
        _mk("net_issuance_sum_13w", "Net issuance (13w sum)", "净发行（13周合计）",
            "treasury_dts.net_issuance.net_issuance_mn", metrics_by_id.get("net_issuance_sum_13w"), "usd_mn",
            "positive = net issuer over the trailing 13 weeks; bucket reuse, see "
            "driver_bucket_naming_note"),
        _mk("net_issuance_pace_delta_4w_vs_13w_avg_daily", "Issuance pace delta (4w vs 13w)",
            "发行节奏差（4周对13周）", "treasury_dts.net_issuance.net_issuance_mn",
            metrics_by_id.get("net_issuance_pace_delta_4w_vs_13w_avg_daily"), "usd_mn_per_day",
            "positive = issuance pace accelerating; bucket reuse, see driver_bucket_naming_note"),
        _mk("auction_demand_spread_recent_vs_baseline", "Auction demand spread", "拍卖需求利差",
            "treasury_auctions.bid_to_cover", metrics_by_id.get("auction_demand_spread_recent_vs_baseline"),
            "bid_to_cover_ratio_pts",
            "positive = recent demand stronger than the trailing-year baseline; bucket "
            "reuse, see driver_bucket_naming_note"),
        _mk("withheld_taxes_yoy_4w", "Withheld-tax revenue YoY (4w)", "预扣税收入同比（4周）",
            "treasury_dts.withheld_taxes.withheld_tax_mn", metrics_by_id.get("withheld_taxes_yoy_4w"), "percent",
            "positive = real-economy wage/employment revenue strengthening YoY; bucket "
            "reuse, see driver_bucket_naming_note"),
    ]
    return {"rate_side": rate_side, "balance_sheet": balance_sheet}


# --------------------------------------------------------------------------- #
# implications
# --------------------------------------------------------------------------- #
def _implications(ctx: dict, metrics_by_id: dict, contradictions: list[dict],
                   worst_freshness: str, coverage_ratio: float) -> list[dict]:
    conf = {
        "data_coverage": _band(coverage_ratio, 0.5, 0.99),
        "source_health": "HIGH" if worst_freshness == "CURRENT" else "LOW",
        "revision_risk": "MEDIUM",
        "method_stability": "HIGH",
        "evidence_breadth": "LOW",
        "contradiction_state": "PRESENT" if contradictions else "ABSENT",
    }
    items: list[dict] = [{
        "implication_id": "headline_unavailable",
        "text": _bil(
            "No dual-axis National Debt state (refinancing/issuance pressure x fiscal "
            "capacity/interest-burden resilience) is asserted: computing refinancing "
            "pressure needs a maturity/rollover wall this estate has no collector "
            "for, and computing fiscal capacity/interest-burden resilience needs debt "
            "stock, net interest expense, and revenue data this estate does not "
            "carry. The real, honest reads this page DOES have -- issuance pressure, "
            "auction demand absorption, BIS debt-service/credit-gap levels, and the "
            "bond-desk coverage state -- are published as metrics instead of being "
            "forced into a fabricated quadrant.",
            "本页未给出双轴国债状态（再融资/发行压力 × 财政能力/利息负担韧性）：计算再融资压力"
            "需要本估值体系尚未接入的到期/展期墙数据，计算财政能力/利息负担韧性则需要本估值体系"
            "不掌握的债务存量、净利息支出与财政收入数据。本页真正拥有的诚实读数——发行压力、"
            "拍卖需求吸纳度、BIS偿债比率/信贷缺口水平，以及债券台面覆盖状态——以指标形式发布，"
            "而非被强行纳入一个虚构的象限。"),
        "evidence_class": "DESCRIPTIVE", "confidence": conf, "horizon": "current",
        "channels": ["fiscal", "rates", "liquidity"],
        "contradictions": [c["kind"] for c in contradictions],
        "trace_ref": "engine.market_os.macro_workspaces.national_debt#headline",
    }]

    tga_imp13 = metrics_by_id.get("tga_impulse_13w")
    if tga_imp13 is not None:
        direction_en = "building (a net reserve drain)" if tga_imp13 > 0 else "draining (a net reserve injection)"
        direction_zh = "上升（净抽走准备金）" if tga_imp13 > 0 else "下降（净注入准备金）"
        items.append({
            "implication_id": "tga_impulse_read",
            "text": _bil(
                f"The TGA is {direction_en} over the trailing 13 weeks ({tga_imp13:+.0f} $mn).",
                f"过去13周TGA余额{direction_zh}（变化{tga_imp13:+.0f}百万美元）。"),
            "evidence_class": "DESCRIPTIVE", "confidence": conf, "horizon": "current",
            "channels": ["liquidity", "fiscal"], "contradictions": [],
            "trace_ref": _TGA_PATH,
        })

    pace_delta = metrics_by_id.get("net_issuance_pace_delta_4w_vs_13w_avg_daily")
    ni13 = metrics_by_id.get("net_issuance_sum_13w")
    if pace_delta is not None or ni13 is not None:
        ni13_en = f"net issuance over the trailing 13 weeks reads {ni13:+,.0f} $mn" if ni13 is not None else "the trailing-13w net-issuance sum is unavailable"
        ni13_zh = f"近13周净发行合计为{ni13:+,.0f}百万美元" if ni13 is not None else "近13周净发行合计不可得"
        pace_en = (f", with the trailing-4-week daily pace running {pace_delta:+.0f} $mn/day "
                   "against the trailing-13-week pace" if pace_delta is not None else "")
        pace_zh = f"，近4周日均节奏较近13周日均节奏变化{pace_delta:+.0f}百万美元/日" if pace_delta is not None else ""
        items.append({
            "implication_id": "issuance_pressure_read",
            "text": _bil(f"{ni13_en}{pace_en}.", f"{ni13_zh}{pace_zh}。"),
            "evidence_class": "DESCRIPTIVE", "confidence": conf, "horizon": "current",
            "channels": ["fiscal", "rates"], "contradictions": [],
            "trace_ref": _NET_ISSUANCE_PATH,
        })

    wt_yoy = metrics_by_id.get("withheld_taxes_yoy_4w")
    if wt_yoy is not None:
        items.append({
            "implication_id": "revenue_nowcast_read",
            "text": _bil(
                f"Withheld income & employment-tax receipts (a real-economy wage/"
                f"employment nowcast) read {wt_yoy:+.1f}% year-over-year on a trailing "
                "4-week sum.",
                f"预扣所得税与雇佣税收入（实体经济工资/就业的高频读数）近4周合计同比"
                f"读数为{wt_yoy:+.1f}%。"),
            "evidence_class": "DESCRIPTIVE", "confidence": conf, "horizon": "current",
            "channels": ["fiscal", "labor"], "contradictions": [],
            "trace_ref": _WITHHELD_PATH,
        })

    demand_spread = metrics_by_id.get("auction_demand_spread_recent_vs_baseline")
    recent_avg = metrics_by_id.get("auction_bid_to_cover_recent_avg")
    if demand_spread is not None or recent_avg is not None:
        recent_en = f"the recent bid-to-cover average reads {recent_avg:.2f}" if recent_avg is not None else "the recent bid-to-cover average is unavailable"
        recent_zh = f"近期投标倍数均值为{recent_avg:.2f}" if recent_avg is not None else "近期投标倍数均值不可得"
        spread_en = f", {demand_spread:+.3f} versus the trailing-year baseline" if demand_spread is not None else ""
        spread_zh = f"，较近一年基准变化{demand_spread:+.3f}" if demand_spread is not None else ""
        items.append({
            "implication_id": "auction_demand_read",
            "text": _bil(f"{recent_en}{spread_en}.", f"{recent_zh}{spread_zh}。"),
            "evidence_class": "DESCRIPTIVE", "confidence": conf, "horizon": "current",
            "channels": ["fiscal", "rates"], "contradictions": [],
            "trace_ref": _AUCTIONS_PATH,
        })

    dsr = metrics_by_id.get("household_debt_service_ratio_level")
    gap = metrics_by_id.get("credit_gap_level")
    if dsr is not None or gap is not None:
        dsr_en = f"the household debt-service ratio reads {dsr:.1f}%" if dsr is not None else "the household debt-service ratio is unavailable"
        dsr_zh = f"家庭偿债比率读数为{dsr:.1f}%" if dsr is not None else "家庭偿债比率不可得"
        gap_en = f" and the credit-to-GDP gap reads {gap:+.1f} percentage points" if gap is not None else ""
        gap_zh = f"，信贷/GDP缺口读数为{gap:+.1f}个百分点" if gap is not None else ""
        items.append({
            "implication_id": "bis_dsr_gap_read",
            "text": _bil(
                f"Per the Bank for International Settlements (BIS) quarterly panel, "
                f"{dsr_en}{gap_en}.",
                f"根据国际清算银行（BIS）季度面板数据，{dsr_zh}{gap_zh}。"),
            "evidence_class": "DESCRIPTIVE", "confidence": conf, "horizon": "current",
            "channels": ["fiscal", "credit"], "contradictions": [],
            "trace_ref": _BIS_DSR_PATH,
        })

    health_label = metrics_by_id.get("bond_desk_health_label")
    cycle_phase = metrics_by_id.get("bond_desk_cycle_phase")
    health_score = metrics_by_id.get("bond_desk_health_score_level")
    if health_label is not None or cycle_phase is not None:
        items.append({
            "implication_id": "bond_desk_passthrough_read",
            "text": _bil(
                f"Bond-desk coverage state: health {health_label or 'unavailable'}"
                f"{f' ({health_score:.0f}/100)' if health_score is not None else ''}, "
                f"cycle phase {cycle_phase or 'unavailable'} -- a coverage read, not a "
                "forecast this composer originates.",
                f"债券台面覆盖状态：健康度{health_label or '不可得'}"
                f"{f'（{health_score:.0f}/100）' if health_score is not None else ''}，"
                f"周期阶段{cycle_phase or '不可得'}——此为覆盖读数，并非本组合器自行给出的预测。"),
            "evidence_class": "DESCRIPTIVE", "confidence": conf, "horizon": "current",
            "channels": ["fiscal", "credit"], "contradictions": [],
            "trace_ref": _BONDS_PATH,
        })

    for c in contradictions:
        items.append({
            "implication_id": f"contradiction_{c['kind']}",
            "text": _bil(c["en"], c["zh"]),
            "evidence_class": "DESCRIPTIVE", "confidence": conf, "horizon": "current",
            "channels": ["fiscal", "rates"], "contradictions": [c["kind"]],
            "trace_ref": _AUCTIONS_PATH,
        })

    items.append({
        "implication_id": "debt_stock_gap_disclosure",
        "text": _bil(
            "No debt STOCK series exists anywhere in this estate as of the 2026-09-04 "
            "source census: no Debt-to-the-Penny, no Monthly Treasury Statement, no "
            "TIC foreign-holdings feed, no MSPD/weighted-average-maturity ladder. "
            "Total debt outstanding, debt-to-GDP, debt held by public, "
            "intragovernmental holdings, the deficit/primary balance, net interest "
            "burden, the maturity ladder, foreign holdings, and contingent "
            "liabilities are all typed not-covered below rather than estimated from "
            "the net-issuance flow -- a flow's running sum is not a level without a "
            "real anchor this estate does not have.",
            "截至2026-09-04的数据源普查，本估值体系尚无任何债务存量序列：无逐日债务余额"
            "（Debt-to-the-Penny）、无月度财政报表（MTS）、无TIC外国持有数据、无MSPD/加权平均"
            "到期期限梯度。未偿债务总额、债务/GDP比率、公众持有债务、政府内部持有、赤字/基本"
            "财政平衡、净利息负担、到期期限梯度、外国持有与或有负债均在下方标记为未覆盖，"
            "而非用净发行流量估算——流量的累计值在没有真实锚点的情况下并不等于存量水平，"
            "本估值体系并不掌握该锚点。"),
        "evidence_class": "DESCRIPTIVE", "confidence": conf, "horizon": "current",
        "channels": ["fiscal"], "contradictions": [], "trace_ref": None,
    })

    items.append({
        "implication_id": "fiscal_year_windowing_disclosure",
        "text": _bil(
            "This page publishes only rolling calendar-day windows (trailing 4 "
            "weeks / 13 weeks / 365 days), never a US fiscal-year (October-"
            "September)-tagged aggregate -- avoiding a fiscal-year/calendar-year "
            "mismatch (a named architecture failure state) at the cost of a less "
            "budget-native cadence.",
            "本页仅发布滚动日历窗口（近4周/近13周/近365天），从不发布以美国财政年度"
            "（10月至次年9月）标注的汇总数据——以牺牲预算口径的贴近度为代价，"
            "避免了财政年度与日历年度错配（架构文档明确列出的失败模式）。"),
        "evidence_class": "DESCRIPTIVE", "confidence": conf, "horizon": "current",
        "channels": ["fiscal"], "contradictions": [], "trace_ref": None,
    })

    items.append({
        "implication_id": "withheld_taxes_window_divergence_disclosure",
        "text": _bil(
            "This page's withheld-tax revenue-nowcast leg deliberately uses a "
            "tighter calendar-day window (a trailing 4-week sum, YoY against the "
            "same window ~365 days prior) than the engine's own already-established "
            "convention for this exact series elsewhere in this repository (a "
            "trailing 63-row ~3-month sum with a 252-row ~1-year shift) -- a faster "
            "pulse for this page's own purpose, never claimed to reproduce that "
            "other reading.",
            "本页的预扣税收入高频读数刻意采用了比本仓库其他位置已有引擎对同一序列既有惯例"
            "（约63行~3个月滚动合计、约252行~1年位移）更短的日历窗口（近4周合计，"
            "与约365天前的同一窗口比较同比）——这是为本页自身用途设计的更快节奏读数，"
            "绝不声称复现另一处的读数。"),
        "evidence_class": "DESCRIPTIVE", "confidence": conf, "horizon": "current",
        "channels": ["fiscal"], "contradictions": [], "trace_ref": None,
    })

    items.append({
        "implication_id": "bis_attribution_note",
        "text": _bil(
            "The household debt-service ratio and credit-to-GDP gap are Bank for "
            "International Settlements (BIS) data, carried under attribution-only "
            "rights: cited by name in every read, never rebranded as this estate's "
            "own index.",
            "家庭偿债比率与信贷/GDP缺口数据来自国际清算银行（BIS），依据仅限署名的权利"
            "条款使用：每次呈现均明确署名，绝不改标为本估值体系自有指数。"),
        "evidence_class": "DESCRIPTIVE", "confidence": conf, "horizon": "current",
        "channels": ["fiscal", "credit"], "contradictions": [], "trace_ref": _BIS_DSR_PATH,
    })

    items.append({
        "implication_id": "driver_bucket_naming_note",
        "text": _bil(
            "The drivers.rate_side bucket in this snapshot carries yield/credit-"
            "cycle legs (the latest auction high yield, the BIS debt-service ratio "
            "and credit gap), not policy rates. The contract's driver bucket pair is "
            "fixed as rate_side/balance_sheet and this workspace has no dedicated "
            "auction/credit bucket to use, so the naming is cosmetic bucket reuse, "
            "disclosed here rather than left implicit.",
            "本快照中drivers.rate_side分组承载的是收益率/信贷周期分项（最近拍卖最高收益率、"
            "BIS家庭偿债比率与信贷缺口），而非政策利率。合约的驱动因素分组固定为rate_side/"
            "balance_sheet，本工作区没有独立的拍卖/信贷分组可用，因此命名属于用途借用，"
            "在此明确披露而非隐含处理。"),
        "evidence_class": "DESCRIPTIVE", "confidence": conf, "horizon": "current",
        "channels": ["fiscal"], "contradictions": [], "trace_ref": None,
    })

    return items


# --------------------------------------------------------------------------- #
# scenario / alert contracts (declared vocabulary only -- R6 non-goal: execution)
# --------------------------------------------------------------------------- #
def _scenario_contract() -> dict:
    return {
        "execution_available": False,
        "result_schema": "mastermind.macro_workspace_scenario_result.v1",
        "assumptions": [
            {"assumption_id": "net_issuance_pace_bn_per_day", "label": _bil("Net issuance pace", "净发行节奏"),
             "unit": "usd_bn_per_day", "step": 0.5, "min": -20.0, "max": 20.0,
             "owner_field": "treasury_dts.net_issuance.net_issuance_mn"},
            {"assumption_id": "auction_bid_to_cover", "label": _bil("Auction bid-to-cover", "拍卖投标倍数"),
             "unit": "ratio", "step": 0.05, "min": 1.0, "max": 4.0,
             "owner_field": "treasury_auctions.bid_to_cover"},
            {"assumption_id": "household_dsr_pct", "label": _bil("Household debt-service ratio", "家庭偿债比率"),
             "unit": "pct", "step": 0.1, "min": 0.0, "max": 30.0,
             "owner_field": "bis.us_dsr.dsr"},
            {"assumption_id": "debt_to_gdp_pct", "label": _bil("Debt-to-GDP", "债务/GDP比率"),
             "unit": "pct", "step": 1.0, "min": 0.0, "max": 200.0, "owner_field": None},
            {"assumption_id": "net_interest_burden_pct_of_revenue", "label": _bil("Net interest burden", "净利息负担"),
             "unit": "pct", "step": 1.0, "min": 0.0, "max": 50.0, "owner_field": None},
        ],
        "status": "PARTIAL",
        "note": (
            "Assumption vocabulary is declared and closed; this composer ships no "
            "scenario execution endpoint (non-goal). debt_to_gdp_pct / "
            "net_interest_burden_pct_of_revenue have no owner_field because the "
            "load-bearing debt-stock gap means this estate has no such series to "
            "anchor them to; a future owner-native pure scenario function produces "
            "mastermind.macro_workspace_scenario_result.v1 with no canonical write."
        ),
    }


def _alert_contract() -> dict:
    return {
        "service_available": False,
        "eligible_conditions": [
            {"condition_id": "tga_impulse_shock", "kind": "component_shock",
             "label": _bil("TGA impulse shock", "TGA脉冲冲击"), "params": ["tga_impulse_13w"]},
            {"condition_id": "issuance_pace_shock", "kind": "component_shock",
             "label": _bil("Issuance pace shock", "发行节奏冲击"),
             "params": ["net_issuance_pace_delta_4w_vs_13w_avg_daily"]},
            {"condition_id": "auction_demand_shock", "kind": "component_shock",
             "label": _bil("Auction demand shock", "拍卖需求冲击"), "params": ["auction_bid_to_cover_recent_avg"]},
            {"condition_id": "issuance_demand_stress_change", "kind": "contradiction_change",
             "label": _bil("Issuance/demand stress change", "发行/需求压力变化"), "params": ["kind"]},
            {"condition_id": "bis_quarterly_release_approaching", "kind": "release_approaching",
             "label": _bil("BIS quarterly release approaching", "BIS季度数据发布临近"), "params": ["source_id", "days"]},
            {"condition_id": "debt_limit_event", "kind": "state_transition",
             "label": _bil("Debt-limit event", "债务上限事件"), "params": ["state"]},
            {"condition_id": "source_stale_or_failed", "kind": "source_stale_or_failed",
             "label": _bil("Source stale or failed", "数据源过期或失败"), "params": ["source_id"]},
        ],
        "status": "ABSENT",
        "note": (
            "Eligible condition types are declared; this composer writes no alert "
            "(non-goal). debt_limit_event is declared vocabulary only -- this "
            "composer has no debt-limit data source and never evaluates the "
            "condition. Alerts extend the existing Terminal alert lifecycle later; "
            "a page shows the Alerts tab only once the service can create/list/"
            "evaluate/delete these real conditions."
        ),
    }


# --------------------------------------------------------------------------- #
# sources
# --------------------------------------------------------------------------- #
def _sources(ctx: dict) -> list[dict]:
    def _src(source_id, en, zh, owner_ref, provider, ref_period, artifact_ref, fresh,
             rights="OPEN"):
        return {
            "source_id": source_id, "label": _bil(en, zh), "owner_ref": owner_ref,
            "provider": provider, "reference_period": ref_period, "released_at": None,
            "first_known_at": None, "collected_at": None, "revised_at": None,
            "correction_state": "unknown", "transform": None, "rights_state": rights,
            "definition_id": None, "definition_version": None, "artifact_ref": artifact_ref,
            "freshness": fresh,
        }

    tga_asof = _iso(ctx["tga_latest"][0]) if ctx["tga_latest"] else None
    ni_asof = _iso(ctx["ni_latest"][0]) if ctx["ni_latest"] else None
    wt_asof = _iso(ctx["wt_latest"][0]) if ctx["wt_latest"] else None
    auc_asof = _iso(ctx["auc_btc_latest"]["auction_date"]) if ctx["auc_btc_latest"] else None
    dsr_asof = _iso(ctx["dsr_latest"][0]) if ctx["dsr_latest"] else None
    gap_asof = _iso(ctx["gap_latest"][0]) if ctx["gap_latest"] else None
    bonds_asof = _iso(ctx["bonds_date"])

    return [
        _src("tga", "Treasury General Account daily balance (Daily Treasury Statement)",
             "财政部一般账户每日余额（每日财政报表）", "collectors.treasury[tga]",
             "US Treasury FiscalData", tga_asof, _TGA_PATH, ctx["tga_fresh"]),
        _src("net_issuance", "Net Treasury issuance (Daily Treasury Statement)",
             "美国国债净发行（每日财政报表）", "collectors.treasury[net_issuance]",
             "US Treasury FiscalData", ni_asof, _NET_ISSUANCE_PATH, ctx["ni_fresh"]),
        _src("withheld_taxes", "Withheld income & employment-tax deposits (Daily Treasury Statement)",
             "预扣所得税与雇佣税存款（每日财政报表）", "collectors.treasury[withheld_taxes]",
             "US Treasury FiscalData", wt_asof, _WITHHELD_PATH, ctx["wt_fresh"]),
        _src("treasury_auctions", "Treasury auction results (bid-to-cover, high yield)",
             "美国国债拍卖结果（投标倍数、最高收益率）", "collectors.treasury_auctions",
             "TreasuryDirect TA_WS", auc_asof, _AUCTIONS_PATH, ctx["auc_fresh"]),
        _src("bis_household_dsr", "US household debt-service ratio (BIS)",
             "美国家庭偿债比率（BIS）", "collectors.bis[us_dsr]",
             "Bank for International Settlements", dsr_asof, _BIS_DSR_PATH, ctx["dsr_fresh"]),
        _src("bis_credit_gap", "US credit-to-GDP gap (BIS)",
             "美国信贷/GDP缺口（BIS）", "collectors.bis[us_gap]",
             "Bank for International Settlements", gap_asof, _BIS_GAP_PATH, ctx["gap_fresh"]),
        _src("bond_desk_latest", "Bond-desk health/cycle-phase state",
             "债券台面健康/周期阶段状态", "scripts.build_bonds",
             "Mastermind Bond Desk", bonds_asof, _BONDS_PATH, ctx["bonds_fresh"]),
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
    the housing/liquidity_central_banks pattern; see liquidity_regime.py's own
    ``_corrections`` for the full caveat about this being a scoped subset, not
    a persisted vintage ledger)."""
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
