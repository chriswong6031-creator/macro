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

# Contradiction + overlap hooks. Both are OPEN questions, and both are carried
# on every state so the Neural Web can see that they are open rather than infer
# from their absence that they were answered. The event clock (Lane 3) does not
# exist yet, so a calendar tailwind cannot yet be checked against an event
# hazard; the covariance-spine crosswalk that would discount duplicate momentum
# information lands with Lane 4.
HOOKS: dict[str, dict[str, str]] = {
    "calendar_tailwind_vs_event_hazard": {"status": "event_clock_not_built"},
    "momentum_overlap": {
        "status": "not_yet_measured",
        "note": "covariance-spine crosswalk lands with Lane 4",
    },
}


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
) -> dict[str, Any]:
    """Build ONE contract-checked context state. Raises StateInputError / ContractError."""
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

    state = contracts.build_neuralweb_state(
        artifact_id=STATE_ARTIFACT_ID,
        entity={
            "type": "issuer" if group == "equity" else "etf",
            "id": f"ticker:{symbol}",
            "ticker": symbol,
        },
        asof=asof,
        available_at=available_at,
        expires_at=expires_at,
        clock={
            "type": "calendar",
            "phase": window_phase(today, start_doy, end_doy),
            "pattern_id": f"cal:{symbol}:{start_doy}-{end_doy}",
            "start_doy": start_doy,
            "end_doy": end_doy,
            "occurrence_end_date": end_date.isoformat(),
            "days_to_window_end": (end_date - today).days,
            "window_source": default_window.get("source"),
        },
        forecast={
            "target": FORECAST_TARGET,
            "horizon_td": horizon_td,
            "p": p,
            "p_baseline": p_baseline,
            "edge": edge,
            "ci90": [ci_low, ci_high],
            "quantiles": {
                "q05": round(_quantile(returns, 0.05), 6),
                "q50": round(_quantile(returns, 0.50), 6),
                "q95": round(_quantile(returns, 0.95), 6),
            },
            "baseline_basis": BASELINE_BASIS,
        },
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
    # Re-checked with the hooks attached so the augmented payload is proven,
    # not merely assumed to still pass.
    return contracts.validate_neuralweb_state({**state, "hooks": dict(HOOKS)})


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
) -> tuple[dict[str, dict], list[dict]]:
    """Build every biopharma state. Returns ``(states, gaps)`` and never raises.

    One bad artifact is one structured gap, not a dead lobe: the covered set is
    ~28 names and the entity tree is R2-published, so a partially-synced
    checkout is the NORMAL case off the nightly runner, and it has to degrade
    into a visible, countable hole.
    """
    entities_dir = Path(entities_dir)
    index_as_of = index.get("as_of")
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
    """
    rows: list[dict] = []
    seen = set(existing_keys)
    for symbol in sorted(states):
        state = states[symbol]
        if (state.get("uncertainty") or {}).get("abstain"):
            continue
        clock = state.get("clock") or {}
        forecast = state.get("forecast") or {}
        provenance = state.get("provenance") or {}
        end_date = date.fromisoformat(str(clock["occurrence_end_date"]))
        key = occurrence_key(symbol, end_date.year, clock["start_doy"], clock["end_doy"])
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
                "start_doy": clock["start_doy"],
                "end_doy": clock["end_doy"],
                "occurrence_end_date": end_date.isoformat(),
                "p": forecast.get("p"),
                "p_baseline": forecast.get("p_baseline"),
                "n_years": (state.get("evidence") or {}).get("n_independent"),
                "pattern_spec_hash": provenance.get("pattern_spec_hash"),
                "model_version": provenance.get("model_version"),
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
