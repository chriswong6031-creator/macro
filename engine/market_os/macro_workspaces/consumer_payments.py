"""Pure composer for the US ``consumer_payments`` workspace snapshot (F01 / R1B).

Reads NINE raw, ALREADY-LOADED level series -- all FRED parquet series -- and
projects them into a ``mastermind.macro_workspace_snapshot.v1`` body:

* ``fred_frames`` -- a dict ``{series_id: rows_or_None}`` where ``rows`` is a
  plain Python list of ``(date, value)`` pairs (or longer tuples -- extra
  elements are ignored, mirrors ``housing.py``'s unconsumed-field negative
  control) read from ``data/fred/<series_id>.parquet``. Exactly NINE series
  are consumed (column names per the orchestrator's same-commit config.yml
  append, listed alongside each series id below); any OTHER key in
  ``fred_frames`` is ignored -- this composer never iterates the dict
  blindly, only ever reads the nine series ids it names.

TODAY'S DISK TRUTH (2026-09-04, per the F01 R1B hand-off): only two of the
nine series are populated --

* ``RSAFS`` (retail sales, column ``retail_sales``) -- monthly $M SA,
  period-start dated, latest row 2026-07-01, 415 rows, VERIFIED present.
* ``UMCSENT`` (Michigan consumer sentiment, column ``umich_sentiment``) --
  monthly index, period-start dated, latest row 2026-07-01, 675 rows,
  VERIFIED present.

The remaining SEVEN are being appended to ``config.yml``'s ``fred.series`` in
the SAME commit that ships this composer; the nightly collector populates
their parquets LATER -- today those parquet files are ABSENT, so the builder
passes ``None`` for each. This composer treats a ``None`` frame as the
honest typed absence (housing precedent: absent value -> SOURCE_FAILED
freshness at the availability layer; metric value null with null_reason
SOURCE_FAILED) and SELF-HEALS the instant real rows are supplied -- every
derived read, the credit-stress axis, and the three-leg contradiction below
are pure functions of whatever rows are handed in, never a hardcoded "still
early" branch:

* ``TOTALSL`` (total consumer credit, column ``consumer_credit_total``),
  ``REVOLSL`` (revolving, column ``consumer_credit_revolving``), ``NONREVSL``
  (nonrevolving, column ``consumer_credit_nonrevolving``) -- G.19 consumer
  credit, monthly $bn SA, period-start dated.
* ``PSAVERT`` (personal saving rate, column ``personal_saving_rate``) --
  monthly percent, BEA, period-start dated.
* ``DSPIC96`` (real disposable personal income, column
  ``real_disposable_income``) -- monthly, chained dollars (base year per
  FRED series metadata -- NOT verified in this authoring environment, see
  judgment call 15), SAAR, BEA, period-start dated.
* ``DRCCLACBS`` (credit-card delinquency rate, column
  ``cc_delinquency_rate``), ``DRSFRMACBS`` (single-family-residential
  mortgage delinquency rate, column ``mortgage_delinquency_rate``) --
  quarterly percent, period-START dated on FRED.

SCOPE (architecture section 10.11, "Consumer & Payments" required
composition): real income/disposable income/spending/saving; goods/services
and discretionary/essential spending "where the source permits" (this
estate's composable core has none of that split -- RSAFS is a single
aggregate, disclosed, never estimated); revolving and nonrevolving credit;
delinquency context "only from accepted sources" (DRCCLACBS/DRSFRMACBS,
both public FRED series, are accepted); payments proxies "only where lawful
and methodologically stable" (card/transaction panels are a standing
exclusion -- see the RIGHTS_BLOCKED note below); revisions and
seasonal-adjustment changes (see the no-PIT-vintage disclosure).

RIGHTS / SCOPE LAWS (binding, doc-cited, never re-litigated inline):
* Card-network / processor transaction-volume panels (Yipit, Earnest
  Research, Consumer Edge, Bloomberg Second Measure, and equivalents) are
  typed ``RIGHTS_BLOCKED`` (``payments_panel_card_network`` metric), citing
  ``docs/QUAL_DATA_COMPLIANCE.md`` section 2.3 verbatim: "These panels
  aggregate individual payment transactions. The data originates from bank
  partnerships or card-network agreements; the downstream compliance burden
  includes verifying that each data vendor's underlying consent framework is
  intact, that individual transaction records are appropriately anonymized
  at the cell level, and that the aggregate product does not permit
  re-identification." This composer reads that section as a RIGHTS-adjacent
  posture, not a pure scope/backlog gap -- see judgment call 3 for the full
  disclosed reasoning and the rejected NOT_COVERED alternative.
* NY Fed Quarterly Report on Household Debt and Credit (QHDC) panels are
  typed ``NOT_COVERED`` (``household_debt_panel_nyfed_qhdc`` metric): no
  collector for that release exists anywhere in this estate today. This
  composer does not build new collectors; a future revision may add one.

CENSUS BINDING / VERIFICATION LIMIT: none of the nine series above were
inspected via a live parquet read in this authoring environment (no shell).
RSAFS/UMCSENT presence and row counts, and the seven pending series' current
absence, are per the F01 R1B hand-off's own disclosed source census, taken
as given.

PIT / REVISION LAW: no ALFRED point-in-time vintage capture exists for any
series on this page today (same law as ``housing.py``'s
``no_alfred_pit_vintage_capture`` disclosure). Every level and derived read
below is the LATEST-REVISED value as currently stored, never an "as it was
known then" reconstruction -- BEA income/saving and Census retail-sales
figures in particular are revised for months after first release.

SA / NSA + UNIT-SCALE LAWS: every series here is seasonally adjusted (SA) by
the publishing agency's own convention EXCEPT the two quarterly delinquency
rates, which FRED publishes NSA (not seasonally adjusted; delinquency has no
standard SA convention). No derived read in this composer ever mixes an SA
series with the NSA delinquency reads. Separately -- the task's own
disclosed trap -- RSAFS is denominated in USD MILLIONS while the G.19 credit
series (TOTALSL/REVOLSL/NONREVSL) and DSPIC96 are USD BILLIONS; every
metric's ``unit`` field states the scale explicitly
(``usd_millions_sa`` vs ``usd_billions_sa`` / ``usd_billions_chained_saar``)
and no metric or derived read ever divides/subtracts across the two scales
(see judgment call 14).

HEADLINE (read this before "fixing" it -- mirrors ``housing.py``'s own
note): architecture section 10.11 DOES define a real two-axis blueprint --
unlike ``monetary_policy``/``liquidity_central_banks`` (no headline-model
subsection at all, honestly ``NOT_APPLICABLE``) --

    x-axis: real household cash-flow/spending momentum, weak -> strong
    y-axis: consumer credit stress, low -> high

Unlike Housing (whose blueprint the composable core can NEVER fill, so its
headline is PERMANENTLY refused), this blueprint IS genuinely computable
once its owner inputs exist -- so this composer implements REAL axis
computation (weighted composites over standardized components, a coverage
floor, hysteresis, quadrant classification -- the ``liquidity_regime.py``
pattern), not a permanent stub. TODAY, though, every y-axis (credit-stress)
leg is one of the seven pending series, so the REAL first build refuses the
headline as ``COMPUTATION_REFUSED`` (never ``NOT_APPLICABLE`` -- this is a
data gap, not a design absence) with ``axes.items`` still populated (each
axis object's ``components`` array is always emitted, showing exactly which
legs are present/absent) -- the refusal path is first-class, not an
afterthought: every test in the paired suite that composes with the
"pending" fixture set (mirroring the real first build) asserts this exact
refused shape.

x-axis (``cash_flow_momentum``): retail_sales_yoy + real_disposable_income_yoy,
BOTH required present (leg-floor law, judgment call 6) -- never averaged from
a single leg.
y-axis (``credit_stress``): consumer_credit_revolving_yoy (0.30),
personal_saving_rate_level inverted (0.25), cc_delinquency_rate_level (0.25),
mortgage_delinquency_rate_level (0.20); needs >= 2 of 4 legs AND >= 50%
coverage (``liquidity_regime.py``'s own coverage-floor law, judgment call 7).

CONTRADICTION: a three-leg "confidence vs. credit-financed spending"
divergence -- consumer sentiment rising, revolving-credit growth
accelerating, AND the saving rate falling, all beyond disclosed flat bands,
simultaneously -- is a genuine, owner-native pattern (architecture 10.11's
own alert vocabulary names "spending/income divergence"): it means reported
strength may be credit-financed rather than income-financed, a fragility
signal the sentiment/spending legs alone would miss. Scoped to exactly the
three metrics the architecture names (judgment call 12); never propagated
into the credit-stress axis's own value/component status (judgment call 16).

DRIVERS BUCKET REUSE (disclosed, mirrors ``housing.py`` /
``liquidity_central_banks.py``): the contract's ``drivers`` block is closed
to exactly ``{rate_side, balance_sheet}``. Neither literally fits Consumer.
``rate_side`` carries the cash-flow-momentum legs (retail sales YoY, real
disposable income YoY); ``balance_sheet`` carries the credit-stress legs
(revolving-credit YoY, saving rate, the two delinquency reads) -- disclosed
in each driver's own note and in the ``driver_bucket_naming_note``
implication.

NO rank/gate/size/trade authority. NO LLM-originated facts. Descriptive
ceiling only. Depends only on the standard library (no pandas import here --
the caller supplies plain rows). The composer NEVER reads a wall clock:
``built_at`` is supplied by the caller, and every staleness/age/lookback
check is a pure function of ``built_at`` and the given rows, so an identical
set of owner inputs always yields an identical snapshot body.

DISCLOSED JUDGMENT CALLS (numbered, never left implicit):

1.  UMCSENT freshness cadence is set to 61 days / 15-day grace, NOT the
    naive "lag ~30d + ~31d cycle -> ~65d" a shallow reading suggests.
    Hand-trace: UMich's FINAL reading for reference month M lands within
    month M itself (~day 25-31, lag ~30d from the period-start date); the
    NEXT month's final (which makes month M's print no longer the newest
    possible) lands ~28-31 days later -- the true worst-case agency cycle is
    therefore lag(30) + interval(31) = 61 days, not 65. Verified against the
    concrete 2026-09-04 calendar fact this hand-off itself raises: a July
    print (2026-07-01) sitting on disk at age 65 days on 2026-09-04 is
    AFTER the August final (~Aug 28-31) should already exist upstream --
    under the correct 61/15 pair this reads ``LATE_WITHIN_TOLERANCE``
    (62-76 days), honestly signalling the print is behind the agency's own
    schedule (collector lag or a delayed release -- this composer cannot
    tell which, and does not guess), rather than a naive 65-day cadence
    that would falsely read it ``CURRENT``. See
    ``test_umcsent_july_print_reads_late_not_current`` for the pinned proof.
2.  RSAFS reuses ``housing.py``'s own Census-construction cadence (80d /
    17d grace) verbatim, per the hand-off's explicit "match construction
    precedent" instruction -- RSAFS is period-start dated and released
    ~17th-19th of M+1, the same release-calendar shape as HOUST/PERMIT.
3.  Card-network/processor payments panels are typed ``RIGHTS_BLOCKED``,
    not ``NOT_COVERED``. The alternative NOT_COVERED reading (QUAL_DATA_
    COMPLIANCE.md section 2 is titled "Exclusions as Deliberate Policy" --
    Mastermind's OWN choice, not an externally imposed contract term like
    housing's NAR ruling R-3) was considered and rejected: section 2.3's own
    text frames the barrier as a RIGHTS/consent/anonymization problem
    inherent to the underlying data ("verifying that each data vendor's
    underlying consent framework is intact... does not permit
    re-identification"), not an engineering backlog item a collector could
    ever close -- unlike a genuine NOT_COVERED gap (e.g. this composer's own
    NY Fed QHDC leg, judgment call 4), no amount of collector-building work
    would ever change this leg's status. RIGHTS_BLOCKED best matches that
    permanence.
4.  NY Fed QHDC household-debt panels are typed ``NOT_COVERED`` (no
    collector exists anywhere in this estate) -- a pure scope gap, not a
    rights question; a future collector could close it.
5.  Architecture 10.11's real x/y blueprint is implemented as genuinely
    computable (unlike Housing's permanently-refused stub) -- it
    self-heals once the pending G.19/BEA/delinquency series populate; the
    REAL first build (today's mostly-absent shape) is a first-class tested
    path, not an afterthought.
6.  X-axis leg floor: retail_sales_yoy AND real_disposable_income_yoy are
    BOTH required (``coverage_floor=1.0``) -- a spending read without an
    income read (or vice versa) is never averaged from a single leg and
    published as "cash-flow momentum".
7.  Y-axis reuses ``liquidity_regime.py``'s own min_components=2-of-4 /
    coverage_floor=0.5 pattern (not a stricter all-4 floor), because its
    four legs span genuinely different cadences (G.19 monthly, BEA monthly,
    delinquency quarterly) that will rarely all refresh in the same build.
8.  Saving-rate and delinquency standardization use fixed, disclosed
    floor/ceiling/neutral anchors (not a live percentile engine) --
    explicitly composer-invented transformations, the same posture as
    ``liquidity_regime.py``'s own quality-label-to-support-score mapping.
9.  ``personal_saving_rate_level`` is the first axis component in this
    estate's composers to carry ``sign = -1``: a raw INCREASE in the saving
    rate maps to a standardized DECREASE in the credit-stress axis. Every
    other sibling composer's axis components use ``sign = +1`` only, so this
    is disclosed explicitly rather than left as a silent first.
10. MoM/YoY lookback slack reuses ``housing.py``'s own disclosed monthly
    slack constant (20 days) verbatim rather than inventing a second,
    possibly-inconsistent value.
11. ``personal_saving_rate_change_3m`` mirrors ``housing.py``'s
    ``mortgage_30y_rate_change_13w`` derived-read pattern (a trailing
    level-difference, refused rather than defaulted to zero when history is
    insufficient), adapted to a ~91-day BEA-cadence lookback.
12. The three-leg contradiction is scoped to exactly the mechanism
    architecture 10.11 names (sentiment, revolving credit, saving rate) --
    it deliberately excludes real_disposable_income even though that series
    is also read by this composer, to avoid inventing a fourth leg the
    architecture never named.
13. Drivers-bucket reuse (see module docstring above) is disclosed in both
    each driver's own note and a dedicated implication.
14. RSAFS ($M) is never divided, subtracted, or averaged against a $bn
    series (G.19 / DSPIC96) in any derived read; every metric's ``unit``
    field states its scale explicitly.
15. DSPIC96's chained-dollar base year could not be verified without a
    shell read of the parquet/FRED series metadata; the unit is disclosed
    generically ("chained dollars, base year per FRED series metadata") in
    the metric's transformation text rather than asserting an unverified
    base year.
16. A fired contradiction marks DISAGREEMENT on exactly the three
    implicated METRIC entries (consumer_sentiment_yoy,
    consumer_credit_revolving_yoy, personal_saving_rate_change_3m); it is
    never propagated into the credit_stress axis's own value_status or its
    revolving-credit component's coverage_state, since the contradiction's
    three legs only partially overlap with the axis's four components and
    forcibly flipping the whole axis status would overstate its scope.
"""
from __future__ import annotations

import datetime as _dt
from hashlib import sha256
from typing import Any, Mapping

METHOD_VERSION = "consumer_payments.compose.v1"
DEFINITION_VERSION = "1.0.0"
AXIS_DEFINITION_VERSION = "1.0.0"
PRODUCER = "engine.market_os.macro_workspaces.consumer_payments"
WORKSPACE_ID = "consumer_payments"

# The nine composable-core FRED series. Column names per the orchestrator's
# same-commit config.yml append (task hand-off, verbatim).
SERIES_RETAIL_SALES = "RSAFS"                 # column: retail_sales (monthly, $M SA)
SERIES_SENTIMENT = "UMCSENT"                  # column: umich_sentiment (monthly, index)
SERIES_CREDIT_TOTAL = "TOTALSL"               # column: consumer_credit_total (monthly, $bn SA)
SERIES_CREDIT_REVOLVING = "REVOLSL"           # column: consumer_credit_revolving (monthly, $bn SA)
SERIES_CREDIT_NONREVOLVING = "NONREVSL"       # column: consumer_credit_nonrevolving (monthly, $bn SA)
SERIES_SAVING_RATE = "PSAVERT"                # column: personal_saving_rate (monthly, %)
SERIES_REAL_DISPOSABLE_INCOME = "DSPIC96"     # column: real_disposable_income (monthly, chained $bn SAAR)
SERIES_CC_DELINQUENCY = "DRCCLACBS"           # column: cc_delinquency_rate (quarterly, %)
SERIES_MORTGAGE_DELINQUENCY = "DRSFRMACBS"    # column: mortgage_delinquency_rate (quarterly, %)

# Cadence / grace-window laws (disclosed constants -- see module docstring's
# judgment calls 1-2 and the task hand-off's own hand-traced release
# calendars for BEA/G.19/quarterly delinquency).
_RETAIL_SALES_CADENCE_DAYS = 80
_RETAIL_SALES_GRACE_DAYS = 17
_SENTIMENT_CADENCE_DAYS = 61
_SENTIMENT_GRACE_DAYS = 15
_G19_CADENCE_DAYS = 100
_G19_GRACE_DAYS = 15
_BEA_CADENCE_DAYS = 92
_BEA_GRACE_DAYS = 15
_DELINQUENCY_CADENCE_DAYS = 255
_DELINQUENCY_GRACE_DAYS = 30

# Derived-read lookback windows (disclosed constants, never silently
# invented). The monthly slack reuses housing.py's own constant verbatim
# (judgment call 10).
_MOM_LOOKBACK_DAYS = 30
_YOY_DAYS = 365
_THREE_MONTH_LOOKBACK_DAYS = 91
_MONTHLY_LOOKBACK_SLACK_DAYS = 20

# Contradiction flat bands (disclosed constants; a leg reading smaller than
# its band in magnitude is itself flat/noisy and can never be read as
# "disagreeing" with anything -- mirrors housing.py's
# _HOME_PRICE_RENT_FLAT_BAND_PCT pattern).
_SENTIMENT_YOY_FLAT_BAND_PCT = 1.0
_REVOLVING_YOY_FLAT_BAND_PCT = 1.0
_SAVING_RATE_CHANGE_FLAT_BAND_PCT_PTS = 0.2

# Headline axis standardization constants (all disclosed, composer-invented
# -- see judgment call 8; no live percentile engine exists in this
# composer).
BOUNDARY = 50.0
HYSTERESIS_BAND = 5.0
_RETAIL_YOY_SCALE = 8.0          # +-8% YoY retail-sales growth -> full x half-swing
_INCOME_YOY_SCALE = 6.0          # +-6% YoY real-income growth -> full x half-swing
_REVOLVING_YOY_SCALE = 10.0      # +-10% YoY revolving-credit growth -> full y half-swing
_SAVING_RATE_NEUTRAL_PCT = 6.0   # disclosed neutral anchor (roughly the long-run average)
_SAVING_RATE_SCALE_PCT = 6.0     # +-6pp around the neutral anchor -> full y half-swing
_CC_DELINQ_FLOOR_PCT = 1.0       # disclosed floor (near-trough historical reading) -> stress 0
_CC_DELINQ_CEIL_PCT = 6.0        # disclosed ceiling (near-GFC-peak historical reading) -> stress 100
_MORTGAGE_DELINQ_FLOOR_PCT = 1.0
_MORTGAGE_DELINQ_CEIL_PCT = 8.0

# X-axis (cash_flow_momentum) weights -- both legs required (leg-floor law,
# judgment call 6).
_X_WEIGHT_RETAIL_YOY = 0.5
_X_WEIGHT_INCOME_YOY = 0.5
_X_MIN_COMPONENTS = 2
_X_COVERAGE_FLOOR = 1.0

# Y-axis (credit_stress) weights -- liquidity_regime.py's own coverage-floor
# law reused (judgment call 7).
_Y_WEIGHT_REVOLVING_YOY = 0.30
_Y_WEIGHT_SAVING_RATE = 0.25
_Y_WEIGHT_CC_DELINQ = 0.25
_Y_WEIGHT_MORTGAGE_DELINQ = 0.20
_Y_MIN_COMPONENTS = 2
_Y_COVERAGE_FLOOR = 0.5

_QUADRANTS = {
    "A": {"en": "Strong cash-flow momentum / Low credit stress", "zh": "现金流动能强 / 信贷压力低"},
    "B": {"en": "Strong cash-flow momentum / High credit stress", "zh": "现金流动能强 / 信贷压力高"},
    "C": {"en": "Weak cash-flow momentum / Low credit stress", "zh": "现金流动能弱 / 信贷压力低"},
    "D": {"en": "Weak cash-flow momentum / High credit stress", "zh": "现金流动能弱 / 信贷压力高"},
}

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
    "retail_sales_level", "retail_sales_yoy", "consumer_sentiment_level",
    "consumer_sentiment_yoy", "cash_flow_momentum", "credit_stress",
)
_TRACKED_CORRECTION_METRICS = (
    "retail_sales_level", "retail_sales_mom", "retail_sales_yoy",
    "consumer_sentiment_level", "consumer_sentiment_yoy",
    "consumer_credit_total_level", "consumer_credit_total_yoy",
    "consumer_credit_revolving_level", "consumer_credit_revolving_yoy",
    "consumer_credit_nonrevolving_level", "consumer_credit_nonrevolving_yoy",
    "personal_saving_rate_level", "personal_saving_rate_change_3m",
    "real_disposable_income_level", "real_disposable_income_yoy",
    "cc_delinquency_rate_level", "mortgage_delinquency_rate_level",
    "cash_flow_momentum", "credit_stress",
)

_UNVERIFIED_BASE_YEAR_NOTE = (
    " (chained dollars, base year per FRED series metadata -- NOT verified in "
    "this authoring environment; see judgment call 15)"
)


# --------------------------------------------------------------------------- #
# small pure helpers (deliberately self-contained -- no cross-import from any
# sibling composer, mirrors housing.py / liquidity_regime.py's own shape)
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


def _clamp(v: float, lo: float, hi: float) -> float:
    return lo if v < lo else hi if v > hi else v


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


# --------------------------------------------------------------------------- #
# raw-row handling (plain level rows, mirrors housing.py's row cleaning)
# --------------------------------------------------------------------------- #
def _clean_rows(rows: Any) -> list[tuple[_dt.date, float]]:
    """Defensively normalize a caller-supplied row list: accept ``(date, value)``
    pairs or longer tuples (extra elements ignored -- an unconsumed-field
    negative control for the digest tests), drop unparseable dates /
    non-numeric values, de-duplicate a repeated date keeping the
    LAST-listed occurrence, and sort ascending by date. Never raises on
    malformed input -- a bad row is dropped, never fabricated into a fake
    reading."""
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
    masquerading as a fresh MoM/YoY/3m comparison point."""
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


def _cadence_freshness(built_at: Any, asof: _dt.date | None, cadence_days: int,
                        grace_days: int, value_present: bool) -> str:
    """Weekly/monthly/quarterly release-cadence law (see module docstring's
    per-series constants). ``value_present=False`` (series wholly absent)
    always reads SOURCE_FAILED; an ``asof`` in the future relative to
    ``built_at`` (a clock inversion) also reads SOURCE_FAILED rather than a
    nonsensical CURRENT."""
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


def _level_diff(a: float | None, b: float | None) -> float | None:
    if a is None or b is None:
        return None
    return _round(a - b, 4)


def _mom_value(rows: list[tuple[_dt.date, float]]) -> float | None:
    latest = _latest(rows)
    if latest is None:
        return None
    prior = _value_before_or_at(rows, latest[0] - _dt.timedelta(days=_MOM_LOOKBACK_DAYS),
                                 _MONTHLY_LOOKBACK_SLACK_DAYS)
    if prior is None:
        return None
    return _pct_change(latest[1], prior[1])


def _yoy_value(rows: list[tuple[_dt.date, float]]) -> float | None:
    latest = _latest(rows)
    if latest is None:
        return None
    prior = _value_before_or_at(rows, latest[0] - _dt.timedelta(days=_YOY_DAYS),
                                 _MONTHLY_LOOKBACK_SLACK_DAYS)
    if prior is None:
        return None
    return _pct_change(latest[1], prior[1])


def _change_3m_value(rows: list[tuple[_dt.date, float]]) -> float | None:
    latest = _latest(rows)
    if latest is None:
        return None
    prior = _value_before_or_at(rows, latest[0] - _dt.timedelta(days=_THREE_MONTH_LOOKBACK_DAYS),
                                 _MONTHLY_LOOKBACK_SLACK_DAYS)
    if prior is None:
        return None
    return _level_diff(latest[1], prior[1])


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


def _component_availability(component_id: str, label_en: str, label_zh: str,
                             rows: list[tuple[_dt.date, float]], freshness: str,
                             required: bool) -> dict:
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
# headline axis helpers (liquidity_regime.py's pattern, self-contained --
# never cross-imported)
# --------------------------------------------------------------------------- #
def _yoy_scale_to_100(v: float | None, scale: float) -> float | None:
    """Linear standardization: v=0 -> 50 (neutral), v=+-scale -> 0/100,
    clamped beyond. Used for legs where a raw INCREASE already means a raw
    increase in the axis's high-end reading (sign=+1)."""
    if v is None:
        return None
    return _clamp(50.0 + (_clamp(v, -scale, scale) / scale) * 50.0, 0.0, 100.0)


def _inverted_scale_to_100(v: float | None, neutral: float, scale: float) -> float | None:
    """Linear standardization around a NEUTRAL anchor, INVERTED: v=neutral
    -> 50, v=neutral+scale -> 0 (low axis reading), v=neutral-scale -> 100
    (high axis reading), clamped beyond. Used for personal_saving_rate_level
    (judgment call 9): a raw INCREASE in saving rate maps to a standardized
    DECREASE in credit-stress."""
    if v is None:
        return None
    return _clamp(50.0 - (_clamp((v - neutral) / scale, -1.0, 1.0)) * 50.0, 0.0, 100.0)


def _floor_ceil_to_100(v: float | None, floor: float, ceil: float) -> float | None:
    """Linear floor/ceiling standardization: v<=floor -> 0, v>=ceil -> 100,
    linear between, clamped. Used for the two delinquency-rate legs."""
    if v is None or ceil == floor:
        return None
    return _clamp((v - floor) / (ceil - floor) * 100.0, 0.0, 100.0)


def _axis_component(component_id, label_en, label_zh, owner_field, owner_ref, raw,
                     standardized, sign, weight, freshness) -> dict:
    present = standardized is not None
    if not present:
        coverage_state = "ABSENT"
        if freshness == "SOURCE_FAILED":
            null_reason = "SOURCE_FAILED"
        elif freshness == "NOT_YET_RELEASED":
            null_reason = "NOT_YET_RELEASED"
        else:
            null_reason = "UNKNOWN"
    elif freshness in ("STALE_SOURCE", "LATE_WITHIN_TOLERANCE"):
        coverage_state, null_reason = "PARTIAL", None
    else:
        coverage_state, null_reason = "PRESENT", None
    contribution = None if standardized is None else _round((standardized - BOUNDARY) * weight, 2)
    return {
        "component_id": component_id,
        "label": _bil(label_en, label_zh),
        "owner_field": owner_field,
        "owner_ref": owner_ref,
        "raw_value": raw,
        "standardized_value": _round(standardized, 2),
        "contribution": contribution,
        "sign": sign,
        "weight": weight,
        "coverage_state": coverage_state,
        "freshness": freshness,
        "null_reason": null_reason,
    }


def _axis_value(components: list[dict], min_components: int, coverage_floor: float):
    present = [c for c in components if c["standardized_value"] is not None]
    total = len(components)
    available = len(present)
    coverage = (available / total) if total else 0.0
    if available < min_components or coverage < coverage_floor:
        return None, "ABSENT", "COMPUTATION_REFUSED", available
    wsum = sum(c["weight"] for c in present)
    if wsum <= 0:
        return None, "ABSENT", "COMPUTATION_REFUSED", available
    value = sum(c["standardized_value"] * c["weight"] for c in present) / wsum
    status = "PRESENT" if available == total else "PARTIAL"
    return _round(_clamp(value, 0.0, 100.0), 2), status, None, available


def _axis(axis_id, label_en, label_zh, direction, value, value_status, null_reason,
          components, components_available, *, low_en, low_zh, high_en, high_zh,
          weights_law, transformation, frequency_alignment, min_components,
          coverage_floor) -> dict:
    fresh = _worst_freshness([c["freshness"] for c in components]) if components else "SOURCE_FAILED"
    return {
        "axis_id": axis_id,
        "label": _bil(label_en, label_zh),
        "direction_semantics": direction,
        "value": value,
        "value_status": value_status,
        "null_reason": null_reason,
        "components": components,
        "weights_law": weights_law,
        "transformation": transformation,
        "min_components": min_components,
        "coverage_floor": coverage_floor,
        "components_available": components_available,
        "frequency_alignment": frequency_alignment,
        "thresholds": {
            "boundary": BOUNDARY,
            "hysteresis_band": HYSTERESIS_BAND,
            "low_label": _bil(low_en, low_zh),
            "high_label": _bil(high_en, high_zh),
        },
        "definition_version": AXIS_DEFINITION_VERSION,
        "data_version": None,
        "revision_behavior": ("recomputed each owner cadence from prior-only owner reads; a "
                               "method-version change breaks comparability and is reported as "
                               "such, never as a numeric delta"),
        "authority_ceiling": "DESCRIPTIVE",
        "freshness": fresh,
    }


def _classify(x: float, y: float) -> str:
    strong = x >= BOUNDARY
    stressed = y >= BOUNDARY
    if strong and not stressed:
        return "A"
    if strong and stressed:
        return "B"
    if not strong and not stressed:
        return "C"
    return "D"


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

    retail = _clean_rows(ff.get(SERIES_RETAIL_SALES))
    sentiment = _clean_rows(ff.get(SERIES_SENTIMENT))
    credit_total = _clean_rows(ff.get(SERIES_CREDIT_TOTAL))
    credit_revolving = _clean_rows(ff.get(SERIES_CREDIT_REVOLVING))
    credit_nonrevolving = _clean_rows(ff.get(SERIES_CREDIT_NONREVOLVING))
    saving_rate = _clean_rows(ff.get(SERIES_SAVING_RATE))
    real_income = _clean_rows(ff.get(SERIES_REAL_DISPOSABLE_INCOME))
    cc_delinq = _clean_rows(ff.get(SERIES_CC_DELINQUENCY))
    mtg_delinq = _clean_rows(ff.get(SERIES_MORTGAGE_DELINQUENCY))

    r_fresh = _cadence_freshness(built_at, _latest(retail)[0] if retail else None,
                                  _RETAIL_SALES_CADENCE_DAYS, _RETAIL_SALES_GRACE_DAYS, bool(retail))
    s_fresh = _cadence_freshness(built_at, _latest(sentiment)[0] if sentiment else None,
                                  _SENTIMENT_CADENCE_DAYS, _SENTIMENT_GRACE_DAYS, bool(sentiment))
    ct_fresh = _cadence_freshness(built_at, _latest(credit_total)[0] if credit_total else None,
                                   _G19_CADENCE_DAYS, _G19_GRACE_DAYS, bool(credit_total))
    cr_fresh = _cadence_freshness(built_at, _latest(credit_revolving)[0] if credit_revolving else None,
                                   _G19_CADENCE_DAYS, _G19_GRACE_DAYS, bool(credit_revolving))
    cn_fresh = _cadence_freshness(built_at, _latest(credit_nonrevolving)[0] if credit_nonrevolving else None,
                                   _G19_CADENCE_DAYS, _G19_GRACE_DAYS, bool(credit_nonrevolving))
    sr_fresh = _cadence_freshness(built_at, _latest(saving_rate)[0] if saving_rate else None,
                                   _BEA_CADENCE_DAYS, _BEA_GRACE_DAYS, bool(saving_rate))
    ri_fresh = _cadence_freshness(built_at, _latest(real_income)[0] if real_income else None,
                                   _BEA_CADENCE_DAYS, _BEA_GRACE_DAYS, bool(real_income))
    ccd_fresh = _cadence_freshness(built_at, _latest(cc_delinq)[0] if cc_delinq else None,
                                    _DELINQUENCY_CADENCE_DAYS, _DELINQUENCY_GRACE_DAYS, bool(cc_delinq))
    mdq_fresh = _cadence_freshness(built_at, _latest(mtg_delinq)[0] if mtg_delinq else None,
                                    _DELINQUENCY_CADENCE_DAYS, _DELINQUENCY_GRACE_DAYS, bool(mtg_delinq))

    # -- derive the raw values the contradiction detector needs BEFORE
    # building the metric list (mirrors housing.py's compute-then-detect order) --
    sentiment_yoy_val = _yoy_value(sentiment)
    revolving_yoy_val = _yoy_value(credit_revolving)
    saving_rate_change_3m_val = _change_3m_value(saving_rate)
    contradictions = _detect_contradiction(sentiment_yoy_val, revolving_yoy_val, saving_rate_change_3m_val)
    fired_kinds = {c["kind"] for c in contradictions}

    metrics = _metrics(
        retail, sentiment, credit_total, credit_revolving, credit_nonrevolving,
        saving_rate, real_income, cc_delinq, mtg_delinq,
        r_fresh, s_fresh, ct_fresh, cr_fresh, cn_fresh, sr_fresh, ri_fresh, ccd_fresh, mdq_fresh,
        sentiment_yoy_val, revolving_yoy_val, saving_rate_change_3m_val, fired_kinds,
    )
    # NOTE: cash_flow_momentum / credit_stress metric entries are appended
    # below once the axis values are known; metrics_by_id is rebuilt after.

    required_avail, optional_avail = _required_availability(
        retail, sentiment, credit_total, credit_revolving, credit_nonrevolving,
        saving_rate, real_income, cc_delinq, mtg_delinq,
        r_fresh, s_fresh, ct_fresh, cr_fresh, cn_fresh, sr_fresh, ri_fresh, ccd_fresh, mdq_fresh,
    )
    all_avail = required_avail + optional_avail
    worst = _worst_freshness([c["freshness"] for c in required_avail])
    n_present = sum(1 for c in required_avail if c["status"] in ("PRESENT", "PARTIAL"))
    coverage_ratio = round(n_present / len(required_avail), 4) if required_avail else 0.0
    degraded = [c["component_id"] for c in required_avail if c["freshness"] != "CURRENT"]

    dates: list[_dt.date] = []
    for rows in (retail, sentiment):
        latest = _latest(rows)
        if latest:
            dates.append(latest[0])
    effective_date = _iso(max(dates)) if dates else None

    # ---- headline: real two-axis computation (see module docstring) ------ #
    retail_yoy_val = _yoy_value(retail)
    income_yoy_val = _yoy_value(real_income)
    saving_rate_level = _latest(saving_rate)[1] if saving_rate else None
    cc_delinq_level = _latest(cc_delinq)[1] if cc_delinq else None
    mtg_delinq_level = _latest(mtg_delinq)[1] if mtg_delinq else None

    x1 = _axis_component(
        "retail_sales_yoy_leg", "Retail sales YoY", "零售销售同比",
        "fred.RSAFS.retail_sales", f"data/fred/{SERIES_RETAIL_SALES}.parquet",
        retail_yoy_val, _yoy_scale_to_100(retail_yoy_val, _RETAIL_YOY_SCALE), 1,
        _X_WEIGHT_RETAIL_YOY, r_fresh,
    )
    x2 = _axis_component(
        "real_disposable_income_yoy_leg", "Real disposable income YoY", "实际可支配收入同比",
        "fred.DSPIC96.real_disposable_income", f"data/fred/{SERIES_REAL_DISPOSABLE_INCOME}.parquet",
        income_yoy_val, _yoy_scale_to_100(income_yoy_val, _INCOME_YOY_SCALE), 1,
        _X_WEIGHT_INCOME_YOY, ri_fresh,
    )
    x_components = [x1, x2]
    x_value, x_status, x_null, x_avail = _axis_value(x_components, _X_MIN_COMPONENTS, _X_COVERAGE_FLOOR)

    y1 = _axis_component(
        "revolving_credit_yoy_leg", "Revolving credit YoY", "循环信贷同比",
        "fred.REVOLSL.consumer_credit_revolving", f"data/fred/{SERIES_CREDIT_REVOLVING}.parquet",
        revolving_yoy_val, _yoy_scale_to_100(revolving_yoy_val, _REVOLVING_YOY_SCALE), 1,
        _Y_WEIGHT_REVOLVING_YOY, cr_fresh,
    )
    y2 = _axis_component(
        "saving_rate_level_leg", "Personal saving rate", "个人储蓄率",
        "fred.PSAVERT.personal_saving_rate", f"data/fred/{SERIES_SAVING_RATE}.parquet",
        saving_rate_level,
        _inverted_scale_to_100(saving_rate_level, _SAVING_RATE_NEUTRAL_PCT, _SAVING_RATE_SCALE_PCT),
        -1, _Y_WEIGHT_SAVING_RATE, sr_fresh,
    )
    y3 = _axis_component(
        "cc_delinquency_level_leg", "Credit-card delinquency rate", "信用卡拖欠率",
        "fred.DRCCLACBS.cc_delinquency_rate", f"data/fred/{SERIES_CC_DELINQUENCY}.parquet",
        cc_delinq_level, _floor_ceil_to_100(cc_delinq_level, _CC_DELINQ_FLOOR_PCT, _CC_DELINQ_CEIL_PCT),
        1, _Y_WEIGHT_CC_DELINQ, ccd_fresh,
    )
    y4 = _axis_component(
        "mortgage_delinquency_level_leg", "Mortgage delinquency rate", "住房抵押贷款拖欠率",
        "fred.DRSFRMACBS.mortgage_delinquency_rate", f"data/fred/{SERIES_MORTGAGE_DELINQUENCY}.parquet",
        mtg_delinq_level,
        _floor_ceil_to_100(mtg_delinq_level, _MORTGAGE_DELINQ_FLOOR_PCT, _MORTGAGE_DELINQ_CEIL_PCT),
        1, _Y_WEIGHT_MORTGAGE_DELINQ, mdq_fresh,
    )
    y_components = [y1, y2, y3, y4]
    y_value, y_status, y_null, y_avail = _axis_value(y_components, _Y_MIN_COMPONENTS, _Y_COVERAGE_FLOOR)

    x_fresh = _worst_freshness([c["freshness"] for c in x_components])
    y_fresh = _worst_freshness([c["freshness"] for c in y_components])
    metrics.append(_metric(
        "cash_flow_momentum", x_value, "score_0_100", "score", "composite_prior_only",
        "higher_stronger_momentum", "engine.market_os.macro_workspaces.consumer_payments",
        "axes.cash_flow_momentum", effective_date, x_fresh if x_value is not None else "SOURCE_FAILED",
        transformation="weighted-mean composite over retail_sales_yoy + real_disposable_income_yoy; see axes[cash_flow_momentum]",
        null_reason=x_null,
    ))
    metrics.append(_metric(
        "credit_stress", y_value, "score_0_100", "score", "composite_prior_only",
        "higher_more_stress", "engine.market_os.macro_workspaces.consumer_payments",
        "axes.credit_stress", effective_date, y_fresh if y_value is not None else "SOURCE_FAILED",
        transformation="weighted-mean composite over revolving-credit YoY, saving rate (inverted), cc delinquency, mortgage delinquency; see axes[credit_stress]",
        null_reason=y_null,
    ))
    metrics_by_id = {m["metric_id"]: m["value"] for m in metrics}

    headline = _headline(x_value, x_status, x_null, y_value, y_status, y_null,
                          effective_date, prior_snapshot)
    changes = _changes(metrics_by_id, prior_snapshot)

    reasons: list[str] = []
    if worst != "CURRENT":
        reasons.append(f"worst_required_source_freshness={worst}")
    for c in contradictions:
        reasons.append(f"contradiction={c['kind']}")

    primary_contradiction = contradictions[0] if contradictions else {
        "kind": None, "en": None, "zh": None, "components": [],
    }

    snapshot = {
        "schema": {"contract": "mastermind.macro_workspace_snapshot.v1", "version": "1.0.0"},
        "workspace": {
            "id": WORKSPACE_ID,
            "title": _bil("Consumer & Payments", "消费与支付"),
            "subtitle": _bil("Cash-flow/spending momentum x consumer credit stress",
                              "现金流/支出动能 × 消费信贷压力"),
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
        "axes": {"items": [
            _axis("cash_flow_momentum", "Cash-flow / spending momentum", "现金流/支出动能",
                  "higher_stronger", x_value, x_status, x_null, x_components, x_avail,
                  low_en="Weak momentum", low_zh="动能疲弱", high_en="Strong momentum", high_zh="动能强劲",
                  weights_law="weighted mean of standardized components, BOTH legs required present (coverage_floor=1.0, judgment call 6); retail sales YoY 0.50, real disposable income YoY 0.50",
                  transformation="YoY percent changes mapped 50+clamp(v/scale,-1,1)*50; prior-only owner reads, no in-composer estimation",
                  frequency_alignment="both legs monthly, period-start dated; RSAFS ~M+1 mid-month release, DSPIC96 ~M+1 month-end BEA release",
                  min_components=_X_MIN_COMPONENTS, coverage_floor=_X_COVERAGE_FLOOR),
            _axis("credit_stress", "Consumer credit stress", "消费信贷压力",
                  "higher_more_stress", y_value, y_status, y_null, y_components, y_avail,
                  low_en="Low stress", low_zh="压力低", high_en="High stress", high_zh="压力高",
                  weights_law="weighted mean of standardized components, weights renormalized over present components (min 2 of 4, coverage_floor=0.5, judgment call 7); revolving-credit YoY 0.30, saving rate (inverted) 0.25, cc delinquency 0.25, mortgage delinquency 0.20",
                  transformation="revolving-credit YoY mapped 50+clamp(v/scale,-1,1)*50 (sign=+1); saving rate mapped 50-clamp((v-neutral)/scale,-1,1)*50 (sign=-1, judgment call 9); delinquency rates mapped linearly floor->ceil (disclosed anchors, judgment call 8)",
                  frequency_alignment="mixed: G.19 revolving credit monthly (~5th business day of M+2), saving rate monthly (BEA, ~M+1 month-end), delinquency quarterly (~70d after quarter end)",
                  min_components=_Y_MIN_COMPONENTS, coverage_floor=_Y_COVERAGE_FLOOR),
        ]},
        "metrics": {"items": metrics},
        "series": {
            "items": [],
            "status": "ABSENT",
            "null_reason": "INSUFFICIENT_HISTORY",
        },
        "drivers": _drivers(metrics_by_id),
        "changes": changes,
        "implications": {"items": _implications(
            metrics_by_id, contradictions, worst, coverage_ratio,
            x_value, y_value, headline)},
        "scenario_contract": _scenario_contract(),
        "alert_contract": _alert_contract(),
        "sources": {"items": _sources(retail, sentiment, credit_total, credit_revolving,
                                       credit_nonrevolving, saving_rate, real_income,
                                       cc_delinq, mtg_delinq, r_fresh, s_fresh, ct_fresh,
                                       cr_fresh, cn_fresh, sr_fresh, ri_fresh, ccd_fresh, mdq_fresh)},
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
def _detect_contradiction(sentiment_yoy: float | None, revolving_yoy: float | None,
                           saving_rate_change_3m: float | None) -> list[dict]:
    """Three-leg "confidence vs. credit-financed spending" divergence (see
    module docstring + judgment call 12): sentiment rising, revolving-credit
    growth accelerating, AND the saving rate falling, all beyond disclosed
    flat bands, simultaneously. Every leg is owner-native; the only
    composer-invented numbers are the three disclosed flat-band constants
    that keep a merely-noisy reading from manufacturing a contradiction."""
    if sentiment_yoy is None or revolving_yoy is None or saving_rate_change_3m is None:
        return []
    sentiment_rising = sentiment_yoy > _SENTIMENT_YOY_FLAT_BAND_PCT
    revolving_accelerating = revolving_yoy > _REVOLVING_YOY_FLAT_BAND_PCT
    saving_falling = saving_rate_change_3m < -_SAVING_RATE_CHANGE_FLAT_BAND_PCT_PTS
    if not (sentiment_rising and revolving_accelerating and saving_falling):
        return []
    return [{
        "kind": "spending_on_credit_vs_confidence_divergence",
        "en": (f"Consumer sentiment is rising year-over-year ({sentiment_yoy:g}%) at the same time "
               f"revolving-credit growth is accelerating ({revolving_yoy:g}% YoY) and the saving "
               f"rate is falling ({saving_rate_change_3m:+g} percentage points over the trailing "
               "~3 months) -- reported consumer strength may be increasingly credit-financed rather "
               "than income-financed, a fragility signal the sentiment and spending reads alone "
               "would miss."),
        "zh": (f"消费者信心同比上升（{sentiment_yoy:g}%），与此同时循环信贷增速加快"
               f"（同比{revolving_yoy:g}%），储蓄率下降（近3个月变化{saving_rate_change_3m:+g}个百分点）——"
               "所报告的消费者强劲程度可能越来越依赖信贷融资而非收入增长，这是仅凭信心与支出读数"
               "无法察觉的脆弱性信号。"),
        "components": ["consumer_sentiment_yoy", "consumer_credit_revolving_yoy",
                        "personal_saving_rate_change_3m"],
    }]


# --------------------------------------------------------------------------- #
# availability
# --------------------------------------------------------------------------- #
def _required_availability(retail, sentiment, credit_total, credit_revolving,
                            credit_nonrevolving, saving_rate, real_income,
                            cc_delinq, mtg_delinq, r_fresh, s_fresh, ct_fresh,
                            cr_fresh, cn_fresh, sr_fresh, ri_fresh, ccd_fresh,
                            mdq_fresh) -> tuple[list[dict], list[dict]]:
    specs = [
        ("retail_sales", "Retail sales", "零售销售", retail, r_fresh, True),
        ("consumer_sentiment", "Consumer sentiment (Michigan)", "消费者信心（密歇根大学）",
         sentiment, s_fresh, True),
        ("consumer_credit_total", "Consumer credit (total)", "消费信贷（总额）",
         credit_total, ct_fresh, False),
        ("consumer_credit_revolving", "Consumer credit (revolving)", "消费信贷（循环）",
         credit_revolving, cr_fresh, False),
        ("consumer_credit_nonrevolving", "Consumer credit (nonrevolving)", "消费信贷（非循环）",
         credit_nonrevolving, cn_fresh, False),
        ("personal_saving_rate", "Personal saving rate", "个人储蓄率",
         saving_rate, sr_fresh, False),
        ("real_disposable_income", "Real disposable income", "实际可支配收入",
         real_income, ri_fresh, False),
        ("cc_delinquency", "Credit-card delinquency rate", "信用卡拖欠率",
         cc_delinq, ccd_fresh, False),
        ("mortgage_delinquency", "Mortgage delinquency rate", "住房抵押贷款拖欠率",
         mtg_delinq, mdq_fresh, False),
    ]
    rows = [_component_availability(cid, en, zh, r, fr, req) for cid, en, zh, r, fr, req in specs]
    required_rows = [r for r in rows if r["required"]]
    optional_rows = [r for r in rows if not r["required"]]
    return required_rows, optional_rows


# --------------------------------------------------------------------------- #
# metrics
# --------------------------------------------------------------------------- #
def _metrics(retail, sentiment, credit_total, credit_revolving, credit_nonrevolving,
             saving_rate, real_income, cc_delinq, mtg_delinq,
             r_fresh, s_fresh, ct_fresh, cr_fresh, cn_fresh, sr_fresh, ri_fresh,
             ccd_fresh, mdq_fresh, sentiment_yoy_val, revolving_yoy_val,
             saving_rate_change_3m_val, fired_kinds: set[str]) -> list[dict]:
    items: list[dict] = []
    contradiction_fired = "spending_on_credit_vs_confidence_divergence" in fired_kinds

    # -- retail sales: level + MoM + YoY -------------------------------------- #
    r_latest = _latest(retail)
    r_level = r_latest[1] if r_latest else None
    r_date = _iso(r_latest[0]) if r_latest else None
    items.append(_metric(
        "retail_sales_level", r_level, "number", "usd_millions_sa", "level",
        "higher_more_spending", f"data/fred/{SERIES_RETAIL_SALES}.parquet",
        "fred.RSAFS.retail_sales", r_date, r_fresh, source_refs=["FRED:RSAFS"],
        transformation=(
            "Census Bureau Advance Retail Sales, total, seasonally adjusted, "
            "republished by FRED, in USD MILLIONS (never mixed with the "
            "USD-BILLIONS G.19/DSPIC96 series in one derived read -- judgment "
            "call 14). No ALFRED point-in-time vintage exists for this series; "
            "this composer publishes the current stored (latest-revised) read."
        ),
    ))
    r_mom_val = _mom_value(retail)
    items.append(_metric(
        "retail_sales_mom", r_mom_val, "percent", "percent", "mom_pct_change",
        "higher_more_spending", f"data/fred/{SERIES_RETAIL_SALES}.parquet",
        "fred.RSAFS.retail_sales", r_date, r_fresh, source_refs=["FRED:RSAFS"],
        transformation=(
            f"Month-over-month percent change of the same SA series; refused when no "
            f"observation lands within {_MONTHLY_LOOKBACK_SLACK_DAYS} days of the "
            f"~{_MOM_LOOKBACK_DAYS}-day lookback target."
        ),
        null_reason="INSUFFICIENT_HISTORY" if r_latest else None,
    ))
    r_yoy_val = _yoy_value(retail)
    items.append(_metric(
        "retail_sales_yoy", r_yoy_val, "percent", "percent", "yoy_pct_change",
        "higher_more_spending", f"data/fred/{SERIES_RETAIL_SALES}.parquet",
        "fred.RSAFS.retail_sales", r_date, r_fresh, source_refs=["FRED:RSAFS"],
        transformation="12-month percent change of the same SA series.",
        null_reason="INSUFFICIENT_HISTORY" if r_latest else None,
    ))

    # -- consumer sentiment: level + YoY --------------------------------------- #
    s_latest = _latest(sentiment)
    s_level = s_latest[1] if s_latest else None
    s_date = _iso(s_latest[0]) if s_latest else None
    items.append(_metric(
        "consumer_sentiment_level", s_level, "index", "index_1966q1_100", "level",
        "higher_more_confident", f"data/fred/{SERIES_SENTIMENT}.parquet",
        "fred.UMCSENT.umich_sentiment", s_date, s_fresh, source_refs=["FRED:UMCSENT"],
        transformation=(
            "University of Michigan Surveys of Consumers, Index of Consumer "
            "Sentiment, republished by FRED. No ALFRED point-in-time vintage "
            "exists for this series; the current stored (latest-revised) read is "
            "published. Freshness cadence for this series is 61 days / 15-day "
            "grace, hand-corrected from a naive 65-day figure -- see judgment call 1."
        ),
    ))
    s_yoy_disagree = contradiction_fired and sentiment_yoy_val is not None
    items.append(_metric(
        "consumer_sentiment_yoy", sentiment_yoy_val, "percent", "percent", "yoy_pct_change",
        "higher_more_confident", f"data/fred/{SERIES_SENTIMENT}.parquet",
        "fred.UMCSENT.umich_sentiment", s_date, s_fresh, source_refs=["FRED:UMCSENT"],
        transformation="12-month percent change of the same index.",
        status="DISAGREEMENT" if s_yoy_disagree else "PRESENT",
        null_reason="DISAGREEMENT" if s_yoy_disagree else ("INSUFFICIENT_HISTORY" if s_latest else None),
    ))

    # -- consumer credit: total / revolving / nonrevolving, level + YoY ------- #
    def _credit_leg(metric_prefix, rows, fresh, series_id, column, label_en_frag):
        latest = _latest(rows)
        level = latest[1] if latest else None
        date = _iso(latest[0]) if latest else None
        items.append(_metric(
            f"{metric_prefix}_level", level, "number", "usd_billions_sa", "level",
            "higher_more_credit_outstanding", f"data/fred/{series_id}.parquet",
            f"fred.{series_id}.{column}", date, fresh, source_refs=[f"FRED:{series_id}"],
            transformation=(
                f"Federal Reserve G.19 Consumer Credit, {label_en_frag}, seasonally "
                "adjusted, republished by FRED, in USD BILLIONS (never mixed with the "
                "USD-MILLIONS RSAFS series in one derived read -- judgment call 14). "
                "No ALFRED point-in-time vintage exists for this series."
            ),
        ))
        yoy_val = _yoy_value(rows)
        disagree = (contradiction_fired and metric_prefix == "consumer_credit_revolving"
                    and yoy_val is not None)
        items.append(_metric(
            f"{metric_prefix}_yoy", yoy_val, "percent", "percent", "yoy_pct_change",
            "higher_faster_credit_growth", f"data/fred/{series_id}.parquet",
            f"fred.{series_id}.{column}", date, fresh, source_refs=[f"FRED:{series_id}"],
            transformation="12-month percent change of the same SA series.",
            status="DISAGREEMENT" if disagree else "PRESENT",
            null_reason="DISAGREEMENT" if disagree else ("INSUFFICIENT_HISTORY" if latest else None),
        ))
        return yoy_val

    _credit_leg("consumer_credit_total", credit_total, ct_fresh, SERIES_CREDIT_TOTAL,
                "consumer_credit_total", "total")
    _credit_leg("consumer_credit_revolving", credit_revolving, cr_fresh, SERIES_CREDIT_REVOLVING,
                "consumer_credit_revolving", "revolving")
    _credit_leg("consumer_credit_nonrevolving", credit_nonrevolving, cn_fresh, SERIES_CREDIT_NONREVOLVING,
                "consumer_credit_nonrevolving", "nonrevolving")

    # -- personal saving rate: level + 3-month change -------------------------- #
    sr_latest = _latest(saving_rate)
    sr_level = sr_latest[1] if sr_latest else None
    sr_date = _iso(sr_latest[0]) if sr_latest else None
    items.append(_metric(
        "personal_saving_rate_level", sr_level, "percent", "percent", "level",
        "higher_more_precautionary_saving", f"data/fred/{SERIES_SAVING_RATE}.parquet",
        "fred.PSAVERT.personal_saving_rate", sr_date, sr_fresh, source_refs=["FRED:PSAVERT"],
        transformation=(
            "BEA Personal Saving Rate (personal saving as a percentage of "
            "disposable personal income), republished by FRED. No ALFRED "
            "point-in-time vintage exists for this series."
        ),
    ))
    sr3_val = saving_rate_change_3m_val
    sr3_disagree = contradiction_fired and sr3_val is not None
    items.append(_metric(
        "personal_saving_rate_change_3m", sr3_val, "number", "pct_pts",
        "trailing_3m_level_change", "higher_more_precautionary_saving",
        f"data/fred/{SERIES_SAVING_RATE}.parquet", "fred.PSAVERT.personal_saving_rate",
        sr_date, sr_fresh, source_refs=["FRED:PSAVERT"],
        transformation=(
            f"Current level minus the level roughly {_THREE_MONTH_LOOKBACK_DAYS} days prior, "
            f"in percentage points (mirrors housing.py's mortgage_30y_rate_change_13w "
            "pattern -- judgment call 11); refused when no observation lands within "
            f"{_MONTHLY_LOOKBACK_SLACK_DAYS} days of that lookback target."
        ),
        status="DISAGREEMENT" if sr3_disagree else "PRESENT",
        null_reason="DISAGREEMENT" if sr3_disagree else ("INSUFFICIENT_HISTORY" if sr_latest else None),
    ))

    # -- real disposable income: level + YoY ------------------------------------ #
    ri_latest = _latest(real_income)
    ri_level = ri_latest[1] if ri_latest else None
    ri_date = _iso(ri_latest[0]) if ri_latest else None
    items.append(_metric(
        "real_disposable_income_level", ri_level, "number", "usd_billions_chained_saar",
        "level", "higher_more_income", f"data/fred/{SERIES_REAL_DISPOSABLE_INCOME}.parquet",
        "fred.DSPIC96.real_disposable_income", ri_date, ri_fresh, source_refs=["FRED:DSPIC96"],
        transformation=(
            "BEA Real Disposable Personal Income, seasonally adjusted annual "
            "rate, republished by FRED" + _UNVERIFIED_BASE_YEAR_NOTE
            + ". No ALFRED point-in-time vintage exists for this series."
        ),
    ))
    ri_yoy_val = _yoy_value(real_income)
    items.append(_metric(
        "real_disposable_income_yoy", ri_yoy_val, "percent", "percent", "yoy_pct_change",
        "higher_more_income_growth", f"data/fred/{SERIES_REAL_DISPOSABLE_INCOME}.parquet",
        "fred.DSPIC96.real_disposable_income", ri_date, ri_fresh, source_refs=["FRED:DSPIC96"],
        transformation="12-month percent change of the same SAAR series.",
        null_reason="INSUFFICIENT_HISTORY" if ri_latest else None,
    ))

    # -- delinquency: cc + mortgage, quarterly, level only --------------------- #
    ccd_latest = _latest(cc_delinq)
    ccd_level = ccd_latest[1] if ccd_latest else None
    ccd_date = _iso(ccd_latest[0]) if ccd_latest else None
    items.append(_metric(
        "cc_delinquency_rate_level", ccd_level, "percent", "percent", "level",
        "higher_more_delinquency_stress", f"data/fred/{SERIES_CC_DELINQUENCY}.parquet",
        "fred.DRCCLACBS.cc_delinquency_rate", ccd_date, ccd_fresh, source_refs=["FRED:DRCCLACBS"],
        transformation=(
            "Federal Reserve delinquency rate on credit card loans, all "
            "commercial banks, NOT seasonally adjusted (delinquency has no "
            "standard SA convention), republished by FRED, quarterly, "
            "period-START dated. No ALFRED point-in-time vintage exists for "
            "this series; delinquency data can be revised after first release."
        ),
    ))
    mdq_latest = _latest(mtg_delinq)
    mdq_level = mdq_latest[1] if mdq_latest else None
    mdq_date = _iso(mdq_latest[0]) if mdq_latest else None
    items.append(_metric(
        "mortgage_delinquency_rate_level", mdq_level, "percent", "percent", "level",
        "higher_more_delinquency_stress", f"data/fred/{SERIES_MORTGAGE_DELINQUENCY}.parquet",
        "fred.DRSFRMACBS.mortgage_delinquency_rate", mdq_date, mdq_fresh,
        source_refs=["FRED:DRSFRMACBS"],
        transformation=(
            "Federal Reserve delinquency rate on single-family residential "
            "mortgages, all commercial banks, NOT seasonally adjusted, "
            "republished by FRED, quarterly, period-START dated. No ALFRED "
            "point-in-time vintage exists for this series."
        ),
    ))

    # -- typed remainder: rights-blocked / not-covered ------------------------- #
    items.append(_metric(
        "payments_panel_card_network", None, "number", None, "n/a", "n/a",
        "NONE -- card-network/processor panels are a standing rights-adjacent "
        "exclusion (docs/QUAL_DATA_COMPLIANCE.md section 2.3)", "NONE", None,
        "RIGHTS_BLOCKED",
        transformation=(
            "Consumer card/transaction data panels (Yipit, Earnest Research, "
            "Consumer Edge, Bloomberg Second Measure, and equivalents) are "
            "excluded per docs/QUAL_DATA_COMPLIANCE.md section 2.3: \"These "
            "panels aggregate individual payment transactions. The data "
            "originates from bank partnerships or card-network agreements; the "
            "downstream compliance burden includes verifying that each data "
            "vendor's underlying consent framework is intact, that individual "
            "transaction records are appropriately anonymized at the cell "
            "level, and that the aggregate product does not permit "
            "re-identification.\" This composer reads that as a rights-adjacent "
            "permanent barrier, not an engineering backlog item -- see judgment "
            "call 3 for the full disclosed reasoning."
        ),
        null_reason="RIGHTS_BLOCKED",
    ))
    items.append(_metric(
        "household_debt_panel_nyfed_qhdc", None, "number", None, "n/a", "n/a",
        "NONE -- no collector for the NY Fed Quarterly Report on Household Debt "
        "and Credit exists in this estate", "NONE", None, "NOT_COVERED",
        transformation=(
            "The NY Fed Quarterly Report on Household Debt and Credit (QHDC) "
            "would supply richer household-debt composition context, but no "
            "collector for that release exists in this estate today. This "
            "composer does not build new collectors; typed as not covered "
            "rather than estimated from a different series (judgment call 4)."
        ),
        null_reason="NOT_COVERED",
    ))

    return items


# --------------------------------------------------------------------------- #
# headline (real two-axis computation -- see module docstring)
# --------------------------------------------------------------------------- #
def _headline(x_value, x_status, x_null, y_value, y_status, y_null, effective_date,
              prior_snapshot) -> dict:
    computable = x_value is not None and y_value is not None
    prior_id = _get(prior_snapshot, "headline", "state_id")
    prior_method = _get(prior_snapshot, "headline", "method_version")
    prior_x = _get(prior_snapshot, "headline", "quadrant", "x")
    prior_y = _get(prior_snapshot, "headline", "quadrant", "y")
    comparable_prior = prior_id in ("A", "B", "C", "D") and prior_method == METHOD_VERSION

    state_id = None
    held_prior = False
    applied = False
    crossed_axes: list[str] = []
    if computable:
        raw = _classify(x_value, y_value)
        state_id = raw
        if comparable_prior:
            applied = True
            if raw != prior_id:
                prior_x_num = prior_x if isinstance(prior_x, (int, float)) else None
                prior_y_num = prior_y if isinstance(prior_y, (int, float)) else None
                if prior_x_num is not None and prior_y_num is not None:
                    if (x_value >= BOUNDARY) != (prior_x_num >= BOUNDARY):
                        crossed_axes.append("cash_flow_momentum")
                    if (y_value >= BOUNDARY) != (prior_y_num >= BOUNDARY):
                        crossed_axes.append("credit_stress")
                    within_band = {
                        "cash_flow_momentum": abs(x_value - BOUNDARY) <= HYSTERESIS_BAND,
                        "credit_stress": abs(y_value - BOUNDARY) <= HYSTERESIS_BAND,
                    }
                    if all(within_band[a] for a in crossed_axes):
                        state_id = prior_id
                        held_prior = True

    if state_id is not None:
        label = _QUADRANTS[state_id]
        state_label = {"en": label["en"], "zh": label["zh"]}
        status = "PRESENT"
        null_reason = None
    else:
        state_label = {"en": None, "zh": None}
        status = "ABSENT"
        null_reason = x_null or y_null or "COMPUTATION_REFUSED"

    if computable:
        dx = abs(x_value - BOUNDARY)
        dy = abs(y_value - BOUNDARY)
        near_axis = "cash_flow_momentum" if dx <= dy else "credit_stress"
        near_dist = round(min(dx, dy), 2)
        nb_null = None
    else:
        near_axis, near_dist, nb_null = None, None, "COMPUTATION_REFUSED"

    if computable and comparable_prior and isinstance(prior_x, (int, float)) and isinstance(prior_y, (int, float)):
        vec = {"dx": round(x_value - prior_x, 2), "dy": round(y_value - prior_y, 2),
               "status": "PRESENT", "null_reason": None}
        transition_distance = round(((x_value - prior_x) ** 2 + (y_value - prior_y) ** 2) ** 0.5, 2)
    else:
        # Refusal outranks warmup: when the quadrant itself cannot be filled,
        # no amount of publication history would produce a vector, so the
        # state's own refusal propagates. WARMUP is reserved for a computable
        # state that merely lacks a prior print (R1A convention).
        if not computable:
            vec_null = "COMPUTATION_REFUSED"
        elif prior_snapshot is None:
            vec_null = "WARMUP"
        elif prior_method != METHOD_VERSION:
            vec_null = "COMPUTATION_REFUSED"
        else:
            vec_null = "INSUFFICIENT_HISTORY"
        vec = {"dx": None, "dy": None, "status": "ABSENT", "null_reason": vec_null}
        transition_distance = None

    if not computable:
        note = (
            "architecture section 10.11 defines a real two-axis blueprint (real "
            "household cash-flow/spending momentum x consumer credit stress), but "
            "this build cannot fill it in: the cash-flow-momentum axis needs BOTH "
            "retail_sales_yoy and real_disposable_income_yoy present, and the "
            "credit-stress axis needs at least 2 of its 4 legs (revolving-credit "
            "YoY, saving rate, cc delinquency, mortgage delinquency) covering at "
            "least half the axis's weight -- most of those legs are pending "
            "collector population as of this build. This is a genuine data gap "
            "(a refusal to fill an existing blueprint), not a design absence "
            "(a blueprint that does not exist): it self-heals the instant the "
            "pending series populate. See the headline_unavailable implication "
            "for the reader-facing version."
        )
    elif not applied:
        note = "no comparable prior print; raw threshold classification, hysteresis not applied"
    elif not held_prior and raw == prior_id:
        note = "raw classification already matches the prior print; no boundary crossing, hysteresis not engaged"
    elif held_prior:
        crossed_txt = " and ".join(crossed_axes) if crossed_axes else "no axis"
        note = (f"prior quadrant held: {crossed_txt} crossed the 50 boundary since the prior "
                f"print but stayed within the {HYSTERESIS_BAND}-pt hysteresis band of ITS OWN "
                f"boundary")
    else:
        crossed_txt = " and ".join(crossed_axes) if crossed_axes else "the classification"
        note = (f"prior quadrant not held: {crossed_txt} crossed the 50 boundary and moved beyond "
                f"the {HYSTERESIS_BAND}-pt hysteresis band, so the transition to the raw quadrant "
                f"is accepted")

    return {
        "state_id": state_id,
        "state_label": state_label,
        "subtitle": _bil("Cash-flow/spending momentum x consumer credit stress",
                          "现金流/支出动能 × 消费信贷压力"),
        "method_version": METHOD_VERSION,
        "effective_date": effective_date,
        "quadrant": {"x": x_value, "y": y_value, "x_status": x_status, "y_status": y_status},
        "prior_state": {
            "state_id": prior_id if prior_id in ("A", "B", "C", "D") else None,
            "effective_date": _get(prior_snapshot, "headline", "effective_date"),
            "method_version": prior_method,
        },
        "transition_distance": transition_distance,
        "nearest_boundary": {"axis": near_axis, "distance": near_dist, "null_reason": nb_null},
        "one_month_vector": vec,
        "hysteresis": {"band": HYSTERESIS_BAND, "applied": applied, "held_prior": held_prior, "note": note},
        "status": status,
        "null_reason": null_reason,
    }


# --------------------------------------------------------------------------- #
# drivers (bucket reuse, disclosed -- see module docstring)
# --------------------------------------------------------------------------- #
def _drivers(metrics_by_id: dict) -> dict:
    def _mk(driver_id, label_en, label_zh, owner_field, value, unit, note):
        sign = 0
        mag = None
        if isinstance(value, (int, float)):
            sign = 1 if value > 0 else (-1 if value < 0 else 0)
            mag = abs(value)
        return {
            "driver_id": driver_id, "label": _bil(label_en, label_zh),
            "owner_field": owner_field, "value": value, "unit": unit,
            "impact_sign": sign, "impact_magnitude": mag, "note": note,
            "coverage_state": "PRESENT" if value is not None else "ABSENT",
        }

    rate_side = [
        _mk("retail_sales_yoy", "Retail sales YoY", "零售销售同比",
            "fred.RSAFS.retail_sales", metrics_by_id.get("retail_sales_yoy"), "percent",
            "bucket reuse: published under drivers.rate_side because the contract's driver "
            "bucket pair is fixed as rate_side/balance_sheet and Consumer has no dedicated "
            "spending bucket -- see the driver_bucket_naming_note implication"),
        _mk("real_disposable_income_yoy", "Real disposable income YoY", "实际可支配收入同比",
            "fred.DSPIC96.real_disposable_income", metrics_by_id.get("real_disposable_income_yoy"),
            "percent", "bucket reuse: see retail_sales_yoy's note"),
    ]
    balance_sheet = [
        _mk("consumer_credit_revolving_yoy", "Revolving credit YoY", "循环信贷同比",
            "fred.REVOLSL.consumer_credit_revolving", metrics_by_id.get("consumer_credit_revolving_yoy"),
            "percent", "bucket reuse: published under drivers.balance_sheet because Consumer has "
            "no dedicated credit bucket -- see the driver_bucket_naming_note implication"),
        _mk("personal_saving_rate_level", "Personal saving rate", "个人储蓄率",
            "fred.PSAVERT.personal_saving_rate", metrics_by_id.get("personal_saving_rate_level"),
            "percent", "bucket reuse: see consumer_credit_revolving_yoy's note; higher saving "
            "rate lowers credit stress (inverted leg, judgment call 9)"),
        _mk("cc_delinquency_rate_level", "Credit-card delinquency rate", "信用卡拖欠率",
            "fred.DRCCLACBS.cc_delinquency_rate", metrics_by_id.get("cc_delinquency_rate_level"),
            "percent", "bucket reuse: see consumer_credit_revolving_yoy's note"),
        _mk("mortgage_delinquency_rate_level", "Mortgage delinquency rate", "住房抵押贷款拖欠率",
            "fred.DRSFRMACBS.mortgage_delinquency_rate", metrics_by_id.get("mortgage_delinquency_rate_level"),
            "percent", "bucket reuse: see consumer_credit_revolving_yoy's note"),
    ]
    return {"rate_side": rate_side, "balance_sheet": balance_sheet}


# --------------------------------------------------------------------------- #
# implications
# --------------------------------------------------------------------------- #
def _implications(metrics_by_id: dict, contradictions: list[dict], worst_freshness: str,
                   coverage_ratio: float, x_value, y_value, headline: dict) -> list[dict]:
    conf = {
        "data_coverage": _band(coverage_ratio, 0.5, 0.99),
        "source_health": "HIGH" if worst_freshness == "CURRENT" else "LOW",
        "revision_risk": "HIGH",
        "method_stability": "HIGH",
        "evidence_breadth": "LOW" if (x_value is None or y_value is None) else "MEDIUM",
        "contradiction_state": "PRESENT" if contradictions else "ABSENT",
    }
    items: list[dict] = []

    if headline["state_id"] is not None:
        label = _QUADRANTS[headline["state_id"]]
        items.append({
            "implication_id": "headline_computed",
            "text": _bil(
                f"Consumer & Payments reads {headline['state_id']} - {label['en']} "
                f"(cash-flow momentum x={x_value}, credit stress y={y_value}, boundary 50).",
                f"消费与支付读数为 {headline['state_id']} - {label['zh']}"
                f"（现金流动能 x={x_value}，信贷压力 y={y_value}，分界 50）。"),
            "evidence_class": "DESCRIPTIVE", "confidence": conf, "horizon": "current",
            "channels": ["consumer", "spending", "credit"],
            "contradictions": [c["kind"] for c in contradictions],
            "trace_ref": "engine.market_os.macro_workspaces.consumer_payments#headline",
        })
    else:
        items.append({
            "implication_id": "headline_unavailable",
            "text": _bil(
                "No dual-axis Consumer & Payments state (cash-flow/spending momentum x "
                "consumer credit stress) is asserted this cycle: the cash-flow-momentum "
                "axis needs both retail sales and real disposable income growth reads, "
                "and the credit-stress axis needs at least half of its four legs "
                "(revolving credit, saving rate, cc delinquency, mortgage delinquency) "
                "-- most credit-stress legs are pending collector population as of this "
                "build. This is a data gap, not a design absence; the state is expected "
                "to become computable once the pending series populate.",
                "本周期未给出消费与支付双轴状态（现金流/支出动能 × 消费信贷压力）："
                "现金流动能轴需要零售销售与实际可支配收入增速读数同时具备，信贷压力轴"
                "需要其四个分项（循环信贷、储蓄率、信用卡拖欠率、住房抵押贷款拖欠率）中"
                "至少一半具备——截至本次构建，大多数信贷压力分项仍待采集器填充数据。"
                "这是数据缺口，而非设计上的不适用；一旦待填充序列具备数据，该状态预计"
                "即可计算。"),
            "evidence_class": "DESCRIPTIVE", "confidence": conf, "horizon": "current",
            "channels": ["consumer", "spending", "credit"],
            "contradictions": [c["kind"] for c in contradictions],
            "trace_ref": "engine.market_os.macro_workspaces.consumer_payments#headline",
        })

    r_yoy = metrics_by_id.get("retail_sales_yoy")
    r_mom = metrics_by_id.get("retail_sales_mom")
    if r_yoy is not None or r_mom is not None:
        yoy_txt_en = f"{r_yoy:+.1f}% YoY" if r_yoy is not None else "YoY unavailable"
        mom_txt_en = f"{r_mom:+.1f}% MoM" if r_mom is not None else "MoM unavailable"
        yoy_txt_zh = f"同比{r_yoy:+.1f}%" if r_yoy is not None else "同比不可得"
        mom_txt_zh = f"环比{r_mom:+.1f}%" if r_mom is not None else "环比不可得"
        items.append({
            "implication_id": "retail_sales_read",
            "text": _bil(
                f"Retail sales read {yoy_txt_en} ({mom_txt_en}).",
                f"零售销售读数为{yoy_txt_zh}（{mom_txt_zh}）。"),
            "evidence_class": "DESCRIPTIVE", "confidence": conf, "horizon": "current",
            "channels": ["spending"], "contradictions": [],
            "trace_ref": f"data/fred/{SERIES_RETAIL_SALES}.parquet",
        })

    s_level = metrics_by_id.get("consumer_sentiment_level")
    s_yoy = metrics_by_id.get("consumer_sentiment_yoy")
    if s_level is not None:
        s_yoy_txt_en = f", {s_yoy:+.1f}% YoY" if s_yoy is not None else ""
        s_yoy_txt_zh = f"，同比{s_yoy:+.1f}%" if s_yoy is not None else ""
        items.append({
            "implication_id": "sentiment_read",
            "text": _bil(
                f"University of Michigan consumer sentiment reads {s_level:g}{s_yoy_txt_en}.",
                f"密歇根大学消费者信心指数读数为{s_level:g}{s_yoy_txt_zh}。"),
            "evidence_class": "DESCRIPTIVE", "confidence": conf, "horizon": "current",
            "channels": ["confidence"], "contradictions": [],
            "trace_ref": f"data/fred/{SERIES_SENTIMENT}.parquet",
        })

    for c in contradictions:
        items.append({
            "implication_id": f"contradiction_{c['kind']}",
            "text": _bil(c["en"], c["zh"]),
            "evidence_class": "DESCRIPTIVE", "confidence": conf, "horizon": "current",
            "channels": ["consumer", "credit", "confidence"], "contradictions": [c["kind"]],
            "trace_ref": f"data/fred/{SERIES_CREDIT_REVOLVING}.parquet",
        })

    items.append({
        "implication_id": "no_alfred_pit_vintage_capture",
        "text": _bil(
            "No point-in-time vintage capture exists for any series on this page "
            "today. Every level and derived read above is the current stored "
            "(latest-revised) value, not what was knowable in real time; BEA "
            "income/saving and Census retail-sales figures in particular are "
            "revised for months after first release.",
            "本页所有序列目前均无时点（PIT）版本捕获。以上所有水平值与派生读数均为当前"
            "存储的（最新修订后的）数值，而非当时实际可知的数值；BEA的收入/储蓄数据"
            "与人口普查局的零售销售数据在首次发布后会持续修订数月。"),
        "evidence_class": "DESCRIPTIVE", "confidence": conf, "horizon": "current",
        "channels": ["consumer"], "contradictions": [], "trace_ref": None,
    })

    items.append({
        "implication_id": "payments_rights_blocked_disclosure",
        "text": _bil(
            "Card-network and processor transaction-volume panels are not shown: "
            "docs/QUAL_DATA_COMPLIANCE.md section 2.3 excludes this category as a "
            "rights-adjacent standing policy (consent-framework verification and "
            "re-identification risk), never as a scope backlog item this "
            "composer could close by building a new collector.",
            "本页未展示银行卡网络/收单机构交易量面板数据：docs/QUAL_DATA_COMPLIANCE.md "
            "第2.3节将此类数据列为权利相关的既定排除政策（涉及同意框架核实与"
            "重新识别风险），而非可通过新建采集器解决的范围性待办事项。"),
        "evidence_class": "DESCRIPTIVE", "confidence": conf, "horizon": "current",
        "channels": ["consumer", "payments"], "contradictions": [], "trace_ref": None,
    })

    items.append({
        "implication_id": "household_debt_not_covered_disclosure",
        "text": _bil(
            "NY Fed Quarterly Report on Household Debt and Credit (QHDC) context "
            "is not shown: no collector for that release exists in this estate "
            "yet. This workspace does not estimate that context from a different "
            "series.",
            "纽约联储家庭债务与信贷季度报告（QHDC）相关背景未展示：本估值体系"
            "目前尚未为该发布接入任何采集器。本工作区不会用其他序列估算该背景数据。"),
        "evidence_class": "DESCRIPTIVE", "confidence": conf, "horizon": "current",
        "channels": ["consumer", "credit"], "contradictions": [], "trace_ref": None,
    })

    items.append({
        "implication_id": "driver_bucket_naming_note",
        "text": _bil(
            "The drivers.rate_side bucket in this snapshot carries cash-flow/"
            "spending legs (retail sales YoY, real disposable income YoY), not "
            "policy rates; drivers.balance_sheet carries credit-stress legs "
            "(revolving-credit YoY, saving rate, cc/mortgage delinquency), not a "
            "balance sheet. The contract's driver bucket pair is fixed as "
            "rate_side/balance_sheet and this workspace has no dedicated "
            "spending/credit buckets, so the naming is cosmetic bucket reuse, "
            "disclosed here rather than left implicit.",
            "本快照中drivers.rate_side分组承载的是现金流/支出分项（零售销售同比、"
            "实际可支配收入同比），而非政策利率；drivers.balance_sheet分组承载的是"
            "信贷压力分项（循环信贷同比、储蓄率、信用卡/住房抵押贷款拖欠率），而非"
            "资产负债表。合约的驱动因素分组固定为rate_side/balance_sheet，本工作区"
            "没有独立的支出/信贷分组可用，因此命名属于用途借用，在此明确披露而非"
            "隐含处理。"),
        "evidence_class": "DESCRIPTIVE", "confidence": conf, "horizon": "current",
        "channels": ["consumer"], "contradictions": [], "trace_ref": None,
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
            {"assumption_id": "real_income_growth_pct", "label": _bil("Real income growth", "实际收入增长"),
             "unit": "pct", "step": 0.5, "min": -20.0, "max": 20.0,
             "owner_field": "fred.DSPIC96.real_disposable_income"},
            {"assumption_id": "saving_rate_pct", "label": _bil("Saving rate", "储蓄率"),
             "unit": "pct", "step": 0.5, "min": 0.0, "max": 25.0,
             "owner_field": "fred.PSAVERT.personal_saving_rate"},
            {"assumption_id": "revolving_credit_growth_pct", "label": _bil("Revolving credit growth", "循环信贷增长"),
             "unit": "pct", "step": 1.0, "min": -20.0, "max": 30.0,
             "owner_field": "fred.REVOLSL.consumer_credit_revolving"},
            {"assumption_id": "cc_delinquency_rate_pct", "label": _bil("Credit-card delinquency rate", "信用卡拖欠率"),
             "unit": "pct", "step": 0.25, "min": 0.0, "max": 15.0,
             "owner_field": "fred.DRCCLACBS.cc_delinquency_rate"},
            {"assumption_id": "retail_sales_growth_pct", "label": _bil("Retail sales growth", "零售销售增长"),
             "unit": "pct", "step": 0.5, "min": -30.0, "max": 30.0,
             "owner_field": "fred.RSAFS.retail_sales"},
        ],
        "status": "PARTIAL",
        "note": (
            "Assumption vocabulary is declared and closed; this composer ships no "
            "scenario execution endpoint (non-goal). A future owner-native pure "
            "scenario function produces mastermind.macro_workspace_scenario_"
            "result.v1 with no canonical write."
        ),
    }


def _alert_contract() -> dict:
    return {
        "service_available": False,
        "eligible_conditions": [
            {"condition_id": "savings_deterioration", "kind": "state_transition",
             "label": _bil("Savings deterioration", "储蓄恶化"), "params": ["direction"]},
            {"condition_id": "revolving_credit_acceleration", "kind": "component_shock",
             "label": _bil("Revolving-credit acceleration", "循环信贷加速"), "params": ["revolving_credit_yoy"]},
            {"condition_id": "spending_income_divergence", "kind": "contradiction_change",
             "label": _bil("Spending/income divergence", "支出/收入背离"), "params": ["kind"]},
            {"condition_id": "credit_stress_break", "kind": "boundary_approach",
             "label": _bil("Credit-stress boundary approach", "信贷压力临界值临近"), "params": ["axis", "distance"]},
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
def _sources(retail, sentiment, credit_total, credit_revolving, credit_nonrevolving,
             saving_rate, real_income, cc_delinq, mtg_delinq, r_fresh, s_fresh,
             ct_fresh, cr_fresh, cn_fresh, sr_fresh, ri_fresh, ccd_fresh, mdq_fresh) -> list[dict]:
    def _src(source_id, en, zh, owner_ref, provider, ref_period, artifact_ref, fresh, rights="OPEN"):
        return {
            "source_id": source_id, "label": _bil(en, zh), "owner_ref": owner_ref,
            "provider": provider, "reference_period": ref_period, "released_at": None,
            "first_known_at": None, "collected_at": None, "revised_at": None,
            "correction_state": "unknown", "transform": None, "rights_state": rights,
            "definition_id": None, "definition_version": None, "artifact_ref": artifact_ref,
            "freshness": fresh,
        }

    r_asof = _iso(_latest(retail)[0]) if retail else None
    s_asof = _iso(_latest(sentiment)[0]) if sentiment else None
    ct_asof = _iso(_latest(credit_total)[0]) if credit_total else None
    cr_asof = _iso(_latest(credit_revolving)[0]) if credit_revolving else None
    cn_asof = _iso(_latest(credit_nonrevolving)[0]) if credit_nonrevolving else None
    sr_asof = _iso(_latest(saving_rate)[0]) if saving_rate else None
    ri_asof = _iso(_latest(real_income)[0]) if real_income else None
    ccd_asof = _iso(_latest(cc_delinq)[0]) if cc_delinq else None
    mdq_asof = _iso(_latest(mtg_delinq)[0]) if mtg_delinq else None

    return [
        _src("retail_sales", "Retail sales (Census Advance Monthly Retail Trade, via FRED)",
             "零售销售（人口普查局零售贸易先行月度统计，经FRED）", "collectors.fred[RSAFS]",
             "US Census Bureau / FRED", r_asof, f"data/fred/{SERIES_RETAIL_SALES}.parquet", r_fresh),
        _src("consumer_sentiment", "Consumer sentiment (University of Michigan, via FRED)",
             "消费者信心（密歇根大学，经FRED）", "collectors.fred[UMCSENT]",
             "University of Michigan / FRED", s_asof, f"data/fred/{SERIES_SENTIMENT}.parquet", s_fresh),
        _src("consumer_credit_total", "Consumer credit, total (Federal Reserve G.19, via FRED)",
             "消费信贷总额（美联储G.19报告，经FRED）", "collectors.fred[TOTALSL]",
             "Federal Reserve / FRED", ct_asof, f"data/fred/{SERIES_CREDIT_TOTAL}.parquet", ct_fresh),
        _src("consumer_credit_revolving", "Consumer credit, revolving (Federal Reserve G.19, via FRED)",
             "消费信贷循环部分（美联储G.19报告，经FRED）", "collectors.fred[REVOLSL]",
             "Federal Reserve / FRED", cr_asof, f"data/fred/{SERIES_CREDIT_REVOLVING}.parquet", cr_fresh),
        _src("consumer_credit_nonrevolving", "Consumer credit, nonrevolving (Federal Reserve G.19, via FRED)",
             "消费信贷非循环部分（美联储G.19报告，经FRED）", "collectors.fred[NONREVSL]",
             "Federal Reserve / FRED", cn_asof, f"data/fred/{SERIES_CREDIT_NONREVOLVING}.parquet", cn_fresh),
        _src("personal_saving_rate", "Personal saving rate (BEA, via FRED)",
             "个人储蓄率（BEA，经FRED）", "collectors.fred[PSAVERT]",
             "US Bureau of Economic Analysis / FRED", sr_asof, f"data/fred/{SERIES_SAVING_RATE}.parquet", sr_fresh),
        _src("real_disposable_income", "Real disposable personal income (BEA, via FRED)",
             "实际可支配个人收入（BEA，经FRED）", "collectors.fred[DSPIC96]",
             "US Bureau of Economic Analysis / FRED", ri_asof,
             f"data/fred/{SERIES_REAL_DISPOSABLE_INCOME}.parquet", ri_fresh),
        _src("cc_delinquency", "Credit-card delinquency rate (Federal Reserve, via FRED)",
             "信用卡拖欠率（美联储，经FRED）", "collectors.fred[DRCCLACBS]",
             "Federal Reserve / FRED", ccd_asof, f"data/fred/{SERIES_CC_DELINQUENCY}.parquet", ccd_fresh),
        _src("mortgage_delinquency", "Mortgage delinquency rate (Federal Reserve, via FRED)",
             "住房抵押贷款拖欠率（美联储，经FRED）", "collectors.fred[DRSFRMACBS]",
             "Federal Reserve / FRED", mdq_asof, f"data/fred/{SERIES_MORTGAGE_DELINQUENCY}.parquet", mdq_fresh),
        _src("payments_panel_card_network", "Card-network/processor transaction panels",
             "银行卡网络/收单机构交易面板数据", "NONE -- rights-blocked (docs/QUAL_DATA_COMPLIANCE.md section 2.3)",
             None, None, None, "RIGHTS_BLOCKED", rights="RIGHTS_BLOCKED"),
        _src("household_debt_nyfed_qhdc", "NY Fed Quarterly Report on Household Debt and Credit",
             "纽约联储家庭债务与信贷季度报告", "NONE -- no collector wired in this estate",
             "Federal Reserve Bank of New York", None, None, "NOT_COVERED"),
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
    the housing/liquidity_central_banks pattern; see liquidity_regime.py's
    own _corrections for the full caveat about this being a scoped subset,
    not a persisted vintage ledger)."""
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
