"""Lane 6 — the Neural Web shadow lobe: per-symbol expiring context states.

This module turns the committed calendar-clock artifacts (Lane 1/2/4) into
compact ``neuralweb.biopharma_seasonality_state.v1`` states and the forward
outcome rows that will eventually grade them.  It is pure logic: no CLI, no
file writes, no network.  ``scripts/build_seasonality_shadow_state.py`` owns
every byte that touches the disk.

Four properties are structural rather than commented-on:

* **The state cannot act.**  Every state is assembled through
  :func:`engine.seasonality.contracts.build_neuralweb_state`, whose authority
  ceiling is all-false — a state may explain and may flag attention, and may
  never rank, gate, size, originate, rewrite geometry, or boost confidence.
  Nothing here returns a score or an ordering, and the emitted map is keyed by
  symbols the *index* already covers, so it can never introduce a name.
* **The state expires.**  ``expires_at`` is ``available_at + 48h``; a consumer
  that reads a stale file is expected to drop the block rather than carry a
  dead calendar read forward.
* **Absent data fails open with a structured gap.**  A missing, unreadable, or
  shape-shifted entity artifact produces a ``{"symbol", "reason_code",
  "detail"}`` row, never an exception, and never a fabricated state.
* **The window convention is checked, not assumed.**  Two independent
  implementations of this spec have already disagreed by one day about what
  ``start_doy`` names, and the disagreement is invisible in the output — it
  just publishes a slightly wrong |t|.  The artifact states its own convention
  in ``calendar.window_convention``; a symbol whose artifact no longer states
  the convention this module implements is a structured gap, not a guess.

The forward-ledger helpers at the bottom are pure too: they take rows in and
return rows out.  Appending them is the NIGHTLY's job alone (house law: the
nightly is the sole advancer of forward ledgers).
"""
from __future__ import annotations

import hashlib
import json
import math
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from . import contracts
from .event_clock import EXPECTED_PROJECTION_CONTRACT
from .panel import N_SLOTS, date_for_slot, slot_for_date

# --- identity ---------------------------------------------------------------

BIOPHARMA_SECTOR = "Health Care"
STATE_FILE_SCHEMA = "neuralweb.biopharma_seasonality_state.file.v1"
STATE_ARTIFACT_ID = "data-neuralweb-biopharma-seasonality-state"
LEDGER_SCHEMA = "seasonality.nw_forward_ledger.v1"
MODEL_VERSION = "seasonality-calendar-v1"

ENTITY_SCHEMA = "biopharma_seasonality.entity.v1"
FORECAST_TARGET = "default_window_return_gt_0"
BASELINE_BASIS = "same_length_all_starts_mean"

# --- thresholds -------------------------------------------------------------

TTL_HOURS = 48
PRE_WINDOW_DAYS = 21
THIN_LIVE_N = 12
THIN_YEARS = 10
ABSTAIN_YEARS = 6
STALE_ARTIFACT_DAYS = 7
UNGRADABLE_AFTER_DAYS = 30
WILSON_Z_90 = 1.645

# The formula this module implements, as the producer states it in
# ``calendar.window_convention``.  Checked, not trusted: an artifact that stops
# saying this is a structured gap rather than an off-by-one nobody can see.
_WINDOW_CONVENTION_MARK = "cum[end_doy - 1] - cum[start_doy - 1]"

# --- v2: the multi-clock state ----------------------------------------------
#
# v1 carried the contradiction and overlap questions as a loose ``hooks`` blob
# bolted onto the payload AFTER the contract validated it — so the two facts
# the lobe most needed to be honest about were the two the contract never
# checked, and their only vocabulary was a free-text ``status`` string. Both
# are first-class validated fields in v2 (:func:`measure_contradiction`,
# :func:`measure_overlap`), each of which must name a reason code when it
# cannot measure.

#: The schema this module EMITS.  v1 remains a supported input everywhere it is
#: read (``contracts.validate_seasonality_state`` dispatches on the payload's
#: own schema), so a stale committed artifact keeps working through the change.
EMITTED_STATE_SCHEMA = contracts.NEURALWEB_STATE_V2_SCHEMA

#: NO calibrated model exists.  This is a hard constant rather than a parameter
#: because a calibrated seasonality estimate is a promotion decision — it needs
#: pre-registered gates and a gauntlet, not a keyword argument.  The contract
#: refuses a partially-provenanced estimate outright, so the day this stops
#: being ``None`` the payload must carry a calibration version, a model
#: version, and a data cutoff or it will not validate.
CALIBRATED_ESTIMATE: dict[str, Any] | None = None

#: Where the covariance spine publishes its measurement.  Read, never rebuilt:
#: the spine is the repo's ONE redundancy measurement and a second one computed
#: here would be a second answer to the same question.
SPINE_ARTIFACT_PATH = "data/neuralweb/covariance_spine.json"
SPINE_SCHEMA = "neuralweb.covariance_spine.v1"

#: The name seasonality would fire under in ``spine_index.parquet``.  It does
#: not appear there yet — the lobe is shadow and has never fired — which is
#: exactly why the overlap slot has to be able to say "unmeasured" out loud.
SPINE_LOBE_NAME = "seasonality"

#: The producer of an authorized event-timing probability.  Imported from the
#: reader that DECLARES the expectation rather than restated here, so the name
#: in the contradiction detail cannot drift away from the name the reader
#: actually refuses to interpret without.
EVENT_TIMING_OWNER_CONTRACT = EXPECTED_PROJECTION_CONTRACT
EVENT_TIMING_OWNER = "biocatalyst"


class StateInputError(ValueError):
    """An entity artifact cannot support a state. Carries a reason code."""

    def __init__(self, reason_code: str, detail: str) -> None:
        super().__init__(detail)
        self.reason_code = reason_code
        self.detail = detail


# --- small numerics (pure stdlib on purpose — see contracts.py) --------------


def _up_share(returns: Sequence[float]) -> float:
    """Share of years that finished the window UP.

    ``> 0.0``, strictly, mirroring ``scanner.window_statistics``: a year that
    ended the window exactly flat is not an up year, and the two modules must
    not disagree about that or the published ``p`` and the page's ``up_share``
    would be two different numbers under one name.
    """
    if not returns:
        return 0.0
    return sum(1 for value in returns if value > 0.0) / len(returns)


def _window_deltas(years_cum: Sequence[Sequence[int]], start_doy: int, end_doy: int) -> list[int]:
    """Per-year QUANTIZED window delta, ``cum[end-1] - cum[start-1]``.

    Left in the artifact's integer 1e-5 units. ``cum_scale`` is positive, so
    the sign — and therefore the up-share — is identical either way, and the
    baseline sweep below runs 305 starts x 25 years without touching a float.
    """
    return [int(row[end_doy - 1]) - int(row[start_doy - 1]) for row in years_cum]


def _baseline_up_share(years_cum: Sequence[Sequence[int]], horizon: int) -> float:
    """The MECHANICAL same-length base rate: mean up-share over every valid start.

    "Is 88% of years up impressive?" is unanswerable against 50%: a window of
    this length on a drifting instrument is up more often than a coin.  The
    honest comparison is the same instrument, the same window LENGTH, every
    admissible position in the year — which is exactly the family's own no-wrap
    restriction ``start + horizon <= 365``.
    """
    if horizon <= 0 or horizon >= N_SLOTS or not years_cum:
        return 0.0
    shares: list[float] = []
    for start_doy in range(1, N_SLOTS - horizon + 1):
        deltas = _window_deltas(years_cum, start_doy, start_doy + horizon)
        shares.append(sum(1 for value in deltas if value > 0) / len(deltas))
    return sum(shares) / len(shares)


def _wilson_ci90(p: float, n: int) -> tuple[float, float]:
    """Wilson score interval at 90%. Always contains ``p`` by construction.

    Wald would not: at ``p = 1.0`` (a window every year of the panel finished
    up) the Wald half-width is exactly zero, so the interval would be the point
    [1.0, 1.0] and would advertise certainty from 19 observations.
    """
    if n <= 0:
        return 0.0, 1.0
    z = WILSON_Z_90
    z2 = z * z
    denominator = 1.0 + z2 / n
    center = (p + z2 / (2 * n)) / denominator
    half = (z / denominator) * math.sqrt(p * (1.0 - p) / n + z2 / (4 * n * n))
    return center - half, center + half


def _quantile(values: Sequence[float], q: float) -> float:
    """Empirical quantile with linear interpolation (numpy's default method)."""
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    position = q * (len(ordered) - 1)
    low = math.floor(position)
    high = math.ceil(position)
    if low == high:
        return float(ordered[low])
    return float(ordered[low] + (position - low) * (ordered[high] - ordered[low]))


def _canonical_hash(payload: Mapping[str, Any]) -> str:
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(blob).hexdigest()


def utc_iso(moment: datetime) -> str:
    """Second-resolution UTC ISO-8601 with a ``Z`` suffix (contracts parse it)."""
    return (
        moment.astimezone(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _gap(symbol: str, reason_code: str, detail: str) -> dict[str, str]:
    return {"symbol": symbol, "reason_code": reason_code, "detail": detail}


# --- the clock --------------------------------------------------------------


def occurrence_end(today: date, end_doy: int) -> date:
    """The date the NEXT completion of this window falls on.

    A calendar window is a recurring appointment, so a state built in December
    for a window that closed in November is describing next year's occurrence,
    not a past one.  ``today_doy <= end_doy`` keeps this year; anything later
    rolls forward.
    """
    today_doy = slot_for_date(today) + 1
    year = today.year if today_doy <= end_doy else today.year + 1
    return date_for_slot(end_doy - 1, year)


def window_phase(today: date, start_doy: int, end_doy: int) -> str:
    """Where the wall clock is relative to the window, in plain words."""
    today_doy = slot_for_date(today) + 1
    if start_doy <= today_doy <= end_doy:
        return "in_window"
    if 0 < start_doy - today_doy <= PRE_WINDOW_DAYS:
        return "pre_window"
    return "out_of_window"


# --- contradiction: measured, or explicitly unavailable ----------------------


def measure_contradiction(
    *,
    calendar_phase: str,
    event_timing_probability: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Check a calendar tailwind against an event-timing hazard, or say why not.

    A contradiction between "this window is historically up" and "an adverse
    binary lands inside it" is a REAL and useful reading — and it requires two
    legs.  The second leg is an authorized, BioCatalyst-owned event-timing
    probability, and no such artifact exists in this repo: ``event_clock`` is a
    reader whose producer contract
    (:data:`EVENT_TIMING_OWNER_CONTRACT`) has not landed, and that reader
    refuses an unratified dialect *wholesale* rather than partially
    interpreting it.

    So this function has exactly two honest outcomes and no third:

    * both legs present and authorized — measure and report;
    * the event leg absent or unratified — ``present: False`` with a
      ``reason_code`` and a ``detail`` that NAMES the missing owner artifact.

    What it must never do is return ``present: False`` with no reason, because
    that is indistinguishable from "checked, and the two clocks agree".  The
    program has already shipped one hook whose silence read as a finding.
    """
    between = ["calendar_clock", "event_clock"]
    if event_timing_probability is None:
        return {
            "present": False,
            "between": between,
            "reason_code": "event_timing_probability_absent",
            "detail": (
                "no authorized event-timing probability exists: the "
                f"{EVENT_TIMING_OWNER_CONTRACT!r} producer (owner: "
                f"{EVENT_TIMING_OWNER}) has not landed, so a {calendar_phase!r} "
                "calendar read cannot be checked against an event hazard. This is "
                "an unmeasured question, NOT a measured absence of contradiction."
            ),
        }
    return {
        "present": False,
        "between": between,
        "reason_code": "event_timing_contract_not_ratified",
        "detail": (
            "an event-timing payload was supplied but "
            f"{EVENT_TIMING_OWNER_CONTRACT!r} is a consumer-side EXPECTATION, not "
            "a ratified producer contract — engine/seasonality/event_clock.py "
            "refuses an unratified dialect wholesale, and a partial read of an "
            "unknown dialect is indistinguishable from a confident misread. "
            "Reconciliation lands with the BioCatalyst W1B producer PR."
        ),
    }


# --- overlap: measured through the covariance spine, or unavailable ----------


def load_spine(root: Path) -> Mapping[str, Any] | None:
    """Read the committed covariance-spine artifact. ``None`` when unusable.

    Never raises and never rebuilds: rebuilding the spine here would be a
    SECOND redundancy measurement in a repo that already has one, and two
    measurements of the same quantity eventually disagree in public.
    """
    path = Path(root) / SPINE_ARTIFACT_PATH
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(payload, Mapping) or payload.get("schema") != SPINE_SCHEMA:
        return None
    return payload


def _overlap_unavailable(reason_code: str, detail: str, measured_against: list[str]) -> dict[str, Any]:
    return {
        "measured": False,
        "measured_against": measured_against,
        "redundancy": None,  # NOT 0.0 — an unmeasured overlap is not independence
        "reason_code": reason_code,
        "detail": detail,
        "measured_by": SPINE_ARTIFACT_PATH,
    }


def measure_overlap(spine: Mapping[str, Any] | None, symbol: str) -> dict[str, Any]:
    """Redundancy of the seasonality lobe against the other measured lobes.

    Delegated entirely to ``engine/neuralweb/covariance_spine.py`` — this reads
    that artifact's ``lobes`` block and reports what it says.  The spine's unit
    is an ENGINE's weekly firing pattern, so the measurement is per-lobe and the
    same for every symbol this lobe covers; ``symbol`` is carried so the
    unavailable reason is attributable per row rather than only per run.

    The seasonality lobe is shadow and has never fired, so it is absent from
    ``spine_index.parquet`` and the honest answer today is an explicit
    unavailable state.  That is a fact this function MEASURES on every run, not
    a constant it returns: the day the lobe starts firing and clears the spine's
    30-active-week floor, the same code path begins reporting a number.
    """
    if spine is None:
        return _overlap_unavailable(
            "spine_artifact_unavailable",
            f"{SPINE_ARTIFACT_PATH} absent, unreadable, or not {SPINE_SCHEMA} — "
            f"redundancy for {symbol} is unmeasured",
            [],
        )
    lobes = (spine.get("blocks") or {}).get("lobes")
    if not isinstance(lobes, Mapping):
        return _overlap_unavailable(
            "spine_lobes_block_absent",
            f"{SPINE_ARTIFACT_PATH} carries no lobes block — redundancy for "
            f"{symbol} is unmeasured",
            [],
        )

    coverage = lobes.get("coverage") or {}
    measurable = [str(name) for name in (coverage.get("measurable") or [])]
    unmeasurable = coverage.get("unmeasurable") or {}

    if SPINE_LOBE_NAME in unmeasurable:
        return _overlap_unavailable(
            "lobe_below_spine_measurement_floor",
            f"the {SPINE_LOBE_NAME!r} lobe has "
            f"{unmeasurable[SPINE_LOBE_NAME]} active week(s) in the spine, below "
            "its measurement floor — redundancy is unmeasured, not zero",
            measurable,
        )
    if SPINE_LOBE_NAME not in measurable:
        return _overlap_unavailable(
            "lobe_absent_from_spine",
            f"the {SPINE_LOBE_NAME!r} lobe does not appear in the spine's firing "
            "index at all (it is shadow and has never fired), so its redundancy "
            f"against {len(measurable)} measured lobe(s) is unmeasured",
            measurable,
        )

    # The lobe is in the spine's index — now find what the spine actually
    # PUBLISHED about it.
    #
    # The pair dialect is the producer's own and is read by its own key names:
    # ``covariance_spine`` writes ``{"a": <engine>, "b": <engine>, "corr": c}``
    # (engine/neuralweb/covariance_spine.py, ``highest_overlap_pairs``).  A
    # reader that guesses a different key shape finds no pair on every entry and
    # then has to invent a redundancy for a lobe it never correlated — which is
    # the same fabrication ``_overlap_unavailable`` exists to prevent, one level
    # down.  So the shape is asserted here rather than sniffed.
    peers: list[str] = []
    strongest: float | None = None
    for pair in lobes.get("highest_overlap_pairs") or ():
        if not isinstance(pair, Mapping) or "a" not in pair or "b" not in pair:
            continue
        names = [str(pair["a"]), str(pair["b"])]
        if SPINE_LOBE_NAME not in names:
            continue
        value = pair.get("corr")
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            continue
        peers.extend(name for name in names if name != SPINE_LOBE_NAME)
        magnitude = abs(float(value))
        strongest = magnitude if strongest is None else max(strongest, magnitude)

    if strongest is None:
        # ``highest_overlap_pairs`` is the spine's GLOBAL top-5 by |corr|
        # (covariance_spine.py: ``all_pairs[:5]``), not this lobe's pair set,
        # and the artifact publishes no correlation matrix.  So a lobe that is
        # in the index but out of that top-5 has no published correlation at
        # all — which is unmeasured, NOT measured-and-independent.  Reporting
        # 0.0 here would publish a positive claim of total independence against
        # peers this lobe was never correlated with.
        return _overlap_unavailable(
            "lobe_in_index_but_no_pair_published",
            f"the {SPINE_LOBE_NAME!r} lobe clears the spine's measurement floor, "
            f"but {SPINE_ARTIFACT_PATH} publishes only its global top-5 "
            "highest-overlap pairs and none of them names this lobe — its "
            f"redundancy against {len(measurable)} measured lobe(s) is therefore "
            "unpublished, not zero",
            measurable,
        )

    return {
        "measured": True,
        # Exactly the peers the reported number was computed OVER — never the
        # whole measurable roster, because naming a lobe this figure was not
        # correlated against reads as a measurement that never happened.
        "measured_against": sorted(set(peers)),
        # Highest |corr| against any peer the spine published a pair for. The
        # spine treats a below-floor pair as 0.0, which biases this DOWN —
        # toward claiming more independence than was shown — so it is reported
        # as the spine's own figure rather than re-derived here.
        "redundancy": round(strongest, 6),
        "reason_code": "measured",
        "detail": (
            f"strongest |correlation| between the {SPINE_LOBE_NAME!r} lobe and the "
            f"spine-published peer(s) {', '.join(sorted(set(peers)))}"
        ),
        "measured_by": SPINE_ARTIFACT_PATH,
    }


# --- one symbol -------------------------------------------------------------


def _require(condition: bool, reason_code: str, detail: str) -> None:
    if not condition:
        raise StateInputError(reason_code, detail)


def _panel_row(entity: Mapping[str, Any], start_doy: int, end_doy: int) -> dict[str, Any] | None:
    """The registered-panel row for this exact window, if the producer priced one."""
    family = entity.get("family")
    if not isinstance(family, Mapping):
        return None
    for row in family.get("registered_panel") or ():
        if not isinstance(row, Mapping):
            continue
        if row.get("start_doy") == start_doy and row.get("end_doy") == end_doy:
            return dict(row)
    return None


def _flags(
    *,
    default_window: Mapping[str, Any],
    n_years: int,
    live_n: int,
    stale: bool,
) -> list[str]:
    """Mechanical, DE-ESCALATING only: every flag here can weaken a read, none strengthens one."""
    flags: list[str] = []
    if not default_window.get("raw_clears"):
        flags.append("raw_null_not_cleared")
    # `neutral_clears` is a tri-state: true, false, or ABSENT (the benchmark leg
    # could not be formed at all). Absent is unknown, and a flag that fires on
    # unknown would read as a measured failure.
    if default_window.get("neutral_clears") is False:
        flags.append("neutral_null_not_cleared")
    stability = default_window.get("stability")
    if isinstance(stability, Mapping) and stability.get("survives") is False:
        flags.append("stability_fragile")
    if live_n < THIN_LIVE_N:
        flags.append("forward_sample_thin")
    if n_years < THIN_YEARS:
        flags.append("thin_years")
    if stale:
        flags.append("artifact_stale")
    return flags


def build_state(
    *,
    symbol: str,
    group: str | None,
    entity: Mapping[str, Any],
    entity_bytes: bytes,
    index_as_of: str | None,
    live_n: int,
    now: datetime,
    spine: Mapping[str, Any] | None = None,
    event_timing_probability: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build ONE contract-checked v2 context state.

    Raises StateInputError / ContractError.

    The numbers are IDENTICAL to the v1 this replaced — same window deltas,
    same up share, same all-starts baseline, same Wilson interval.  What
    changed is only that they are now named for what they are: the up share
    lives in ``historical_up_share`` instead of ``forecast``, and the slot a
    fitted estimate would occupy (``calibrated_estimate``) is separate, typed,
    and null.
    """
    _require(
        entity.get("schema") == ENTITY_SCHEMA,
        "schema_mismatch",
        f"entity schema is {entity.get('schema')!r}, expected {ENTITY_SCHEMA!r}",
    )

    calendar = entity.get("calendar")
    _require(isinstance(calendar, Mapping), "schema_mismatch", "entity.calendar missing")
    convention = str(calendar.get("window_convention") or "")
    _require(
        _WINDOW_CONVENTION_MARK in convention,
        "schema_mismatch",
        "calendar.window_convention no longer states "
        f"{_WINDOW_CONVENTION_MARK!r} — refusing to guess the window formula",
    )
    cum_scale = calendar.get("cum_scale")
    _require(
        isinstance(cum_scale, (int, float)) and float(cum_scale) > 0.0,
        "schema_mismatch",
        f"calendar.cum_scale is {cum_scale!r}",
    )
    cum_scale = float(cum_scale)

    default_window = entity.get("default_window")
    _require(
        isinstance(default_window, Mapping),
        "schema_mismatch",
        "default_window absent — the producer published no priced window for this symbol",
    )
    start_doy = default_window.get("start_doy")
    end_doy = default_window.get("end_doy")
    _require(
        isinstance(start_doy, int)
        and isinstance(end_doy, int)
        and 1 <= start_doy < end_doy <= N_SLOTS,
        "schema_mismatch",
        f"default_window ({start_doy!r}, {end_doy!r}) is not a 1-based no-wrap window",
    )

    years = entity.get("years")
    _require(isinstance(years, list) and years, "schema_mismatch", "entity.years is empty")
    years_cum: list[list[int]] = []
    for row in years:
        cum = row.get("cum") if isinstance(row, Mapping) else None
        _require(
            isinstance(cum, list) and len(cum) == N_SLOTS,
            "schema_mismatch",
            f"a years[] row carries {0 if cum is None else len(cum)} cum slots, expected {N_SLOTS}",
        )
        years_cum.append(cum)
    n_years = len(years_cum)

    asof = str(entity.get("asof") or "")
    _require(bool(asof), "schema_mismatch", "entity.asof absent")

    # --- the numbers ---
    deltas = _window_deltas(years_cum, start_doy, end_doy)
    returns = [value * cum_scale for value in deltas]
    p = round(_up_share(returns), 6)
    p_baseline = round(_baseline_up_share(years_cum, end_doy - start_doy), 6)
    # The contract re-derives `edge` from the EMITTED p and p_baseline at 1e-9,
    # so it is computed from the rounded pair, not from the raw one. Rounding to
    # 10 places keeps the serialised number readable while staying two orders of
    # magnitude inside the tolerance.
    edge = round(p - p_baseline, 10)
    ci_low, ci_high = _wilson_ci90(p, n_years)
    # Wilson contains p̂ analytically; the clamp is float hygiene at the p=0 and
    # p=1 endpoints (where the algebra cancels to exactly 0.0 / 1.0 and the
    # arithmetic may land a whisker outside), never a widening of the interval.
    ci_low = max(0.0, min(round(ci_low, 6), p))
    ci_high = min(1.0, max(round(ci_high, 6), p))

    asof_date = date.fromisoformat(asof[:10])
    today = now.astimezone(timezone.utc).date()
    end_date = occurrence_end(today, end_doy)
    # horizon_td is the FORECAST horizon and is measured from the data's own
    # as-of; days_to_window_end is the wall-clock countdown a reader wants.
    # They differ whenever the store is behind, and conflating them would let a
    # stale store shorten a horizon it knows nothing about.
    horizon_td = max(1, (end_date - asof_date).days)

    stale = False
    if index_as_of:
        try:
            stale = (date.fromisoformat(str(index_as_of)[:10]) - asof_date).days > STALE_ARTIFACT_DAYS
        except ValueError:
            stale = False

    panel_row = _panel_row(entity, start_doy, end_doy) or {}
    flags = _flags(
        default_window=default_window, n_years=n_years, live_n=live_n, stale=stale
    )
    abstain = bool(stale or n_years < ABSTAIN_YEARS)

    available_at = utc_iso(now)
    expires_at = utc_iso(now + timedelta(hours=TTL_HOURS))

    phase = window_phase(today, start_doy, end_doy)
    state = contracts.build_neuralweb_state_v2(
        artifact_id=STATE_ARTIFACT_ID,
        entity={
            "type": "issuer" if group == "equity" else "etf",
            "id": f"ticker:{symbol}",
            "ticker": symbol,
        },
        asof=asof,
        available_at=available_at,
        expires_at=expires_at,
        # A LIST because a name can sit on several clocks at once. Exactly one
        # is emitted today, and that is the point of the list: the event and
        # regime clocks are ABSENT rather than present-and-empty, so a consumer
        # cannot mistake an unbuilt clock for a clock that found nothing.
        clocks=[
            {
                "type": "calendar",
                "phase": phase,
                "pattern_id": f"cal:{symbol}:{start_doy}-{end_doy}",
                "window": {
                    "start_doy": start_doy,
                    "end_doy": end_doy,
                    "occurrence_end_date": end_date.isoformat(),
                    "days_to_window_end": (end_date - today).days,
                    "window_source": default_window.get("source"),
                },
                "evidence": {
                    "n_years": n_years,
                    "horizon_td": horizon_td,
                },
            }
        ],
        # The v1 ``forecast`` object, renamed to the thing it has always
        # measured. Same p, same baseline, same edge, same interval.
        historical_up_share={
            "target": FORECAST_TARGET,
            "horizon_td": horizon_td,
            "p": p,
            "p_baseline": p_baseline,
            "edge": edge,
            "ci90": [ci_low, ci_high],
            # The two intervals this object ships are DIFFERENT objects and each
            # says so: the Wilson ci90 bounds the realized share itself (a
            # parameter CI), while the quantiles describe where one future
            # window's return might land. They plot identically, so neither is
            # left to be inferred from its position in the payload.
            "ci90_kind": "parameter_ci",
            "n_years": n_years,
            "quantiles": {
                "q05": round(_quantile(returns, 0.05), 6),
                "q50": round(_quantile(returns, 0.50), 6),
                "q95": round(_quantile(returns, 0.95), 6),
            },
            "quantiles_kind": "outcome_quantiles",
            "basis": BASELINE_BASIS,
        },
        # Null, and structurally hard to fill loosely later — see the constant.
        calibrated_estimate=CALIBRATED_ESTIMATE,
        contradiction=measure_contradiction(
            calendar_phase=phase,
            event_timing_probability=event_timing_probability,
        ),
        overlap=measure_overlap(spine, symbol),
        evidence={
            # The independence unit is one complete year, exactly as Lane 1
            # defines it — never one session. One symbol is one issuer, and a
            # calendar window recurs once a year, so the year count IS the
            # date-cluster count here.
            "n_independent": n_years,
            "n_issuers": 1,
            "n_date_clusters": n_years,
            "live_n": live_n,
            "q_by": panel_row.get("q_by"),
            "p_max_t": panel_row.get("p_adj_maxt_family"),
            "spa_p": None,
        },
        uncertainty={"abstain": abstain, "flags": flags},
        provenance={
            "model_version": MODEL_VERSION,
            "pattern_spec_hash": _canonical_hash(
                {
                    "symbol": symbol,
                    "start_doy": start_doy,
                    "end_doy": end_doy,
                    "source": default_window.get("source"),
                    "n_years": n_years,
                }
            ),
            "data_snapshot": "sha256:" + hashlib.sha256(entity_bytes).hexdigest(),
        },
        tier="shadow",
    )
    # ``build_neuralweb_state_v2`` validates before returning, and nothing is
    # attached afterwards: in v1 the two open questions rode along as a loose
    # ``hooks`` blob bolted on after validation, which meant the contract never
    # saw them. They are first-class validated fields now (``contradiction``,
    # ``overlap``), so there is no post-validation mutation left to re-check.
    return state


# --- the sweep --------------------------------------------------------------


def covered_symbols(index: Mapping[str, Any]) -> list[dict[str, Any]]:
    """The biopharma rows of the covered-symbol catalog.

    MEASURED from the index's own sector labels, never a hand-kept roster: the
    sector ETFs (XBI, IBB, XLV) are in-sector and belong here, and a name that
    leaves the covered universe leaves this set on the same night.
    """
    rows: list[dict[str, Any]] = []
    for entry in index.get("entities") or ():
        if not isinstance(entry, Mapping):
            continue
        if entry.get("sector") != BIOPHARMA_SECTOR:
            continue
        symbol = str(entry.get("symbol") or "").strip()
        if symbol:
            rows.append({"symbol": symbol, "group": entry.get("group")})
    return sorted(rows, key=lambda row: row["symbol"])


def build_states(
    index: Mapping[str, Any],
    entities_dir: Path,
    ledger_live_n: Mapping[str, int],
    now: datetime,
    root: Path | None = None,
) -> tuple[dict[str, dict], list[dict]]:
    """Build every biopharma state. Returns ``(states, gaps)`` and never raises.

    One bad artifact is one structured gap, not a dead lobe: the covered set is
    ~28 names and the entity tree is R2-published, so a partially-synced
    checkout is the NORMAL case off the nightly runner, and it has to degrade
    into a visible, countable hole.

    ``root`` locates the covariance-spine artifact, which is read ONCE per run
    and shared: the spine's unit is a lobe, so re-reading it per symbol would
    be ~28 identical file reads producing ~28 identical answers.  When ``root``
    is omitted the spine is simply unavailable and every state says so — the
    overlap slot degrades into its explicit unavailable form rather than into
    silence.
    """
    entities_dir = Path(entities_dir)
    index_as_of = index.get("as_of")
    spine = load_spine(Path(root)) if root is not None else None
    states: dict[str, dict] = {}
    gaps: list[dict] = []

    for row in covered_symbols(index):
        symbol = row["symbol"]
        path = entities_dir / f"{symbol}.json"
        try:
            raw = path.read_bytes()
        except FileNotFoundError:
            gaps.append(_gap(symbol, "entity_artifact_absent", f"{path.name} not in the entity tree"))
            continue
        except OSError as exc:
            gaps.append(_gap(symbol, "entity_artifact_unreadable", f"{type(exc).__name__}: {exc}"))
            continue

        try:
            entity = json.loads(raw)
        except ValueError as exc:
            gaps.append(_gap(symbol, "entity_artifact_unreadable", f"invalid JSON: {exc}"))
            continue
        if not isinstance(entity, Mapping):
            gaps.append(_gap(symbol, "schema_mismatch", "entity artifact is not an object"))
            continue

        try:
            states[symbol] = build_state(
                symbol=symbol,
                group=row.get("group"),
                entity=entity,
                entity_bytes=raw,
                index_as_of=index_as_of,
                live_n=int(ledger_live_n.get(symbol, 0)),
                now=now,
                spine=spine,
            )
        except StateInputError as exc:
            gaps.append(_gap(symbol, exc.reason_code, exc.detail))
        except contracts.ContractError as exc:
            gaps.append(_gap(symbol, "contract_rejected", str(exc)))
        except Exception as exc:  # noqa: BLE001 — one symbol never takes the lobe down
            gaps.append(_gap(symbol, "state_build_failed", f"{type(exc).__name__}: {exc}"))
    return states, gaps


# --- forward outcome ledger (pure helpers; the SCRIPT owns the file) ---------


def occurrence_key(symbol: str, end_year: int, start_doy: int, end_doy: int) -> str:
    """One row per (symbol, window, occurrence) — the ledger's identity."""
    return f"{symbol}:{end_year}:{start_doy}-{end_doy}"


def register_rows(
    states: Mapping[str, Mapping[str, Any]],
    existing_keys: set[str],
    asof: date,
) -> list[dict]:
    """A forward-outcome row for every forecast this run would SHOW.

    Registration is deliberately NOT phase-gated. The docket's law is "write
    forward outcomes for every shown forecast", and a ledger that only recorded
    windows already open would grade the pattern exactly when it was most
    flattering and stay silent the other eleven months.

    An ABSTAINING state is not a shown forecast — it is the lobe declining to
    speak — so it is not registered.

    The ROW schema is unchanged across the v1 -> v2 state migration and stays
    ``seasonality.nw_forward_ledger.v1``: the ledger's 28 existing rows must
    remain comparable with everything appended after it, and ``p`` means the
    same thing on both sides of the rename (it is read through
    ``contracts.seasonality_state_projection``, which resolves v1's
    ``forecast.p`` and v2's ``historical_up_share.p`` to one number).
    """
    rows: list[dict] = []
    seen = set(existing_keys)
    for symbol in sorted(states):
        state = states[symbol]
        projection = contracts.seasonality_state_projection(state)
        if projection["abstain"]:
            continue
        ledger = projection["ledger"]
        # No defensive parse here on purpose. ``contracts._validate_clocks``
        # requires a calendar clock whose window carries a parseable
        # ``occurrence_end_date``, so every state that reaches this function has
        # one — and a try/except that can never fire is a guard no test can
        # distinguish from its absence. The contract is the guard.
        end_date = date.fromisoformat(str(ledger["occurrence_end_date"]))
        key = occurrence_key(symbol, end_date.year, ledger["start_doy"], ledger["end_doy"])
        if key in seen:
            continue
        seen.add(key)
        rows.append(
            {
                "row_type": "register",
                "schema": LEDGER_SCHEMA,
                "key": key,
                "symbol": symbol,
                "registered_asof": asof.isoformat(),
                "start_doy": ledger["start_doy"],
                "end_doy": ledger["end_doy"],
                "occurrence_end_date": end_date.isoformat(),
                "p": ledger["p"],
                "p_baseline": ledger["p_baseline"],
                "n_years": ledger["n_years"],
                "pattern_spec_hash": ledger["pattern_spec_hash"],
                "model_version": ledger["model_version"],
                "tier": "shadow",
            }
        )
    return rows


def _last_close_on_or_before(
    sessions: Sequence[tuple[date, float]], target: date
) -> float | None:
    """Last adjusted close at or before ``target``. ``sessions`` ascends by date."""
    found: float | None = None
    for session_date, close in sessions:
        if session_date > target:
            break
        found = float(close)
    return found


def grade_rows(
    pending_registers: Sequence[Mapping[str, Any]],
    price_frames: Mapping[str, Sequence[tuple[date, float]]],
    asof: date,
) -> list[dict]:
    """Grade matured registrations against the adjusted-close store.

    ``price_frames`` maps a symbol to its chronologically ASCENDING
    ``[(session_date, adjusted_close)]`` pairs — the same ``close`` column
    ``engine.seasonality.panel.load_adjusted_closes`` reads for the panel, so
    the realized number and the panel number are the same measurement.

    EQUIVALENCE (why this reproduces the panel rather than approximating it):
    ``cum[s]`` is the running sum of the folded daily log returns through slot
    ``s``, and slot index is ``doy - 1``.  So
    ``cum[end_doy - 1] - cum[start_doy - 1]`` sums every session's log return
    from the day after ``start_doy`` through ``end_doy`` — which telescopes to
    ``ln(P_end / P_start)`` where each ``P`` is the close of the LAST session on
    or before that calendar date.  Non-trading days carry a zero log return
    (``coverage.missing_session_policy``) so a weekend endpoint contributes
    nothing and the on-or-before close is exactly right; Feb-29's return is
    folded into the Feb-28 slot (``coverage.leap_policy``), which the shared
    ``slot_for_date`` / ``date_for_slot`` pair mirrors, so a leap year does not
    shift either endpoint.

    A register that has matured but whose prices have not arrived stays
    PENDING — it is graded on a later night.  Only after 30 days with no
    session on or after the window's end is it closed out as
    ``ungradable_missing_prices``, which is the honest reading for a symbol
    that left the store.  Nothing here ever invents a price.
    """
    rows: list[dict] = []
    for register in pending_registers:
        symbol = str(register.get("symbol") or "")
        try:
            end_date = date.fromisoformat(str(register["occurrence_end_date"]))
            start_doy = int(register["start_doy"])
        except (KeyError, TypeError, ValueError):
            continue
        if end_date >= asof:
            continue  # the window has not closed yet — nothing to grade

        sessions = price_frames.get(symbol) or ()
        matured = bool(sessions) and sessions[-1][0] >= end_date
        # start_doy < end_doy always (the family never wraps the year), so both
        # endpoints sit in the occurrence's own calendar year.
        start_date = date_for_slot(start_doy - 1, end_date.year)
        entry = _last_close_on_or_before(sessions, start_date) if matured else None
        exit_ = _last_close_on_or_before(sessions, end_date) if matured else None

        if entry is None or exit_ is None or entry <= 0.0 or exit_ <= 0.0:
            if (asof - end_date).days > UNGRADABLE_AFTER_DAYS:
                rows.append(
                    {
                        "row_type": "grade",
                        "schema": LEDGER_SCHEMA,
                        "key": register.get("key"),
                        "symbol": symbol,
                        "graded_asof": asof.isoformat(),
                        "realized_log_return": None,
                        "outcome_up": None,
                        "p": register.get("p"),
                        "p_baseline": register.get("p_baseline"),
                        "brier": None,
                        "grade_status": "ungradable_missing_prices",
                    }
                )
            continue

        realized = math.log(exit_ / entry)
        outcome_up = realized > 0.0
        p = register.get("p")
        brier = (
            round((float(p) - (1.0 if outcome_up else 0.0)) ** 2, 6)
            if isinstance(p, (int, float)) and not isinstance(p, bool)
            else None
        )
        rows.append(
            {
                "row_type": "grade",
                "schema": LEDGER_SCHEMA,
                "key": register.get("key"),
                "symbol": symbol,
                "graded_asof": asof.isoformat(),
                "realized_log_return": round(realized, 6),
                "outcome_up": outcome_up,
                "p": p,
                "p_baseline": register.get("p_baseline"),
                "brier": brier,
                "grade_status": "graded",
            }
        )
    return rows


def live_n_by_symbol(ledger_rows: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    """Per-symbol count of GRADED outcomes — the forward sample, not the backtest.

    ``ungradable_missing_prices`` rows are closed but carry no outcome, so they
    are not evidence and are not counted.
    """
    counts: dict[str, int] = {}
    for row in ledger_rows:
        if row.get("row_type") != "grade" or row.get("grade_status") != "graded":
            continue
        symbol = str(row.get("symbol") or str(row.get("key") or "").split(":")[0])
        if symbol:
            counts[symbol] = counts.get(symbol, 0) + 1
    return counts
