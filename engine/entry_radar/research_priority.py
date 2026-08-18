"""engine/entry_radar/research_priority.py — RP1 Research Priority (W6).

Deterministic, decomposable, ACCRUING attention-ordering over currently
developing Radar episodes.  Not a probability, not W7, not Prophet.

Policy (frozen before this module existed as ranking code):
``research/live_entry_radar/W6_RP1_POLICY.md``.

This module is PURE.  No clock, no network, no ``data/`` path, no LLM, no
ledger write.  Given identical frozen inputs it returns identical JSON-safe
dicts.  Input-order of episodes does not change ``priority_value`` / ``ordinal``.
Ticker identity is an address, never a measure.

Cross-section calibration is on unique current name snapshots (ticker).
Each rankable expert observation still receives its own row; the snapshot's
canonical ``priority_value`` is projected onto every such row.

Live Priority is ephemeral: the durable episode ledger keeps
``research_priority`` null.  This module only produces payload objects.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

POLICY_VERSION = "RP1"
SCHEMA = "mastermind.research_priority.v1"
STATUS = "ACCRUING"
MEANING = "deterministic Research Priority index under policy RP1"
DOES_NOT_CLAIM: tuple[str, ...] = (
    "probability",
    "confidence",
    "conviction",
    "expected return",
    "expected upside",
    "win rate",
    "percentile of future performance",
    "edge",
)

MIN_DIMENSIONS = 2
PULLBACK_RATIO = 0.98
SMA_LEN = 50
RET_WINDOWS: tuple[int, ...] = (20, 60, 120)
PROXIMITY_WINDOW = 120
BENCH_TICKER = "SPY"

DEVELOPING_STATES: frozenset[str] = frozenset({"ARMED", "TURNING", "CANDIDATE"})
CYCLE_REFUSALS: frozenset[str] = frozenset({
    "killed", "out_of_window", "stale_pack", "proof_failed", "failed",
})
NULL_AVAILABILITY: frozenset[str] = frozenset({"unavailable", "stale"})

#: Whitelist.  Anything else on an input mapping (hotness, lobes, MFE, W5
#: outcomes, ticker-specific weights, C4 depth, …) is ignored.
MEASURE_KEYS: frozenset[str] = frozenset({
    "ret_20", "ret_60", "ret_120", "proximity_120",
    "structure_intact", "pulled_back",
    "rs_60_vs_bench", "oscillator_reset_intact",
    "rebound_atr", "hist", "k_minus_d",
})

DIMENSIONS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("structural_quality", ("ret_20", "ret_60", "ret_120", "proximity_120")),
    ("reset_quality", ("structure_intact", "pulled_back")),
    ("resilience_quality", ("rs_60_vs_bench", "oscillator_reset_intact")),
    ("recovery_quality", ("rebound_atr", "hist", "k_minus_d")),
)

BANNED_PRESENTATION: tuple[str, ...] = (
    "probability", "validated", "win chance", "expected return",
    "conviction", "edge confirmed",
)


class PriorityError(ValueError):
    """A malformed RP1 input.  Never raised because a measure is missing."""


@dataclass(frozen=True, slots=True)
class EpisodeInput:
    """One expert observation presented for ranking.

    Identity fields are addresses.  ``measures`` is the only ranking surface,
    and only ``MEASURE_KEYS`` are read from it.
    """

    ticker: str
    detector_id: str
    variant: str | None
    state: str
    first_armed_at: str | None
    candidate_at: str | None
    last_observed_at: str | None
    known_at: str | None
    availability: str
    history_freshness: str
    name_state: str
    name_reasons: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    pack_hash: str | None = None
    substrate_fingerprint: str | None = None
    measures: Mapping[str, Any] = field(default_factory=dict)
    extra: Mapping[str, Any] = field(default_factory=dict)

    @property
    def expert_key(self) -> tuple[str, str, str]:
        return (self.ticker, self.detector_id, self.variant or "")


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def _tail_mean(values: Sequence[float], n: int) -> float | None:
    if n <= 0 or len(values) < n:
        return None
    window = values[-n:]
    return sum(window) / float(n)


def _ret(values: Sequence[float], n: int) -> float | None:
    if n <= 0 or len(values) < n + 1:
        return None
    prior = values[-1 - n]
    last = values[-1]
    if prior == 0:
        return None
    return last / prior - 1.0


def _max_tail(values: Sequence[float], n: int) -> float | None:
    if n <= 0 or len(values) < n:
        return None
    return max(values[-n:])


def measures_from_history(
    closes: Sequence[float],
    highs: Sequence[float] | None = None,
    *,
    atr: float | None = None,
    sampled_close: float | None = None,
    running_sampled_low: float | None = None,
    k: float | None = None,
    d: float | None = None,
    hist: float | None = None,
    bench_closes: Sequence[float] | None = None,
) -> dict[str, float | None]:
    """Point-in-time RP1 measures.  Missing history → None, never 0."""
    del highs  # proximity uses closes; highs reserved so callers can pass OHLC
    clean = [v for v in (_finite(x) for x in closes) if v is not None]
    out: dict[str, float | None] = {key: None for key in MEASURE_KEYS}
    if not clean:
        return out
    last = clean[-1]
    for window in RET_WINDOWS:
        out[f"ret_{window}"] = _ret(clean, window)
    peak = _max_tail(clean, PROXIMITY_WINDOW)
    out["proximity_120"] = None if peak is None or peak == 0 else last / peak
    sma = _tail_mean(clean, SMA_LEN)
    out["structure_intact"] = None if sma is None else (1.0 if last >= sma else 0.0)
    high20 = _max_tail(clean, 20)
    out["pulled_back"] = None if high20 is None else (
        1.0 if last < PULLBACK_RATIO * high20 else 0.0)
    bench = [v for v in (_finite(x) for x in (bench_closes or ())) if v is not None]
    stock_60 = out["ret_60"]
    bench_60 = _ret(bench, 60)
    out["rs_60_vs_bench"] = None if stock_60 is None or bench_60 is None else (
        stock_60 - bench_60)
    k_val = _finite(k)
    intact = out["structure_intact"]
    out["oscillator_reset_intact"] = None if k_val is None or intact is None else (
        1.0 if (k_val < 20.0 and intact >= 1.0) else 0.0)
    close_px = _finite(sampled_close)
    low_px = _finite(running_sampled_low)
    atr_val = _finite(atr)
    if close_px is not None and low_px is not None and atr_val is not None and atr_val > 0:
        out["rebound_atr"] = (close_px - low_px) / atr_val
    out["hist"] = _finite(hist)
    d_val = _finite(d)
    out["k_minus_d"] = None if k_val is None or d_val is None else k_val - d_val
    return out


def _whitelisted(measures: Mapping[str, Any]) -> dict[str, float | None]:
    return {key: _finite(measures.get(key)) for key in MEASURE_KEYS}


def _dimension_available(measures: Mapping[str, float | None], keys: Sequence[str]
                         ) -> bool:
    """A dimension is available iff at least one of its submeasures is finite.

    Coverage only.  Ranking never averages the raw submeasure units.
    """
    return any(measures.get(k) is not None for k in keys)


def _mean_available(values: Sequence[float | None]) -> float | None:
    vals = [v for v in values if v is not None]
    if not vals:
        return None
    return sum(vals) / float(len(vals))


def _percentiles(values: Sequence[float | None]) -> list[float | None]:
    """Higher-is-better percentile in 0–100.  None stays None.

    Ties share the mid-rank percentile so input order cannot move the number.
    """
    indexed = [(i, v) for i, v in enumerate(values) if v is not None]
    out: list[float | None] = [None] * len(values)
    n = len(indexed)
    if n == 0:
        return out
    if n == 1:
        out[indexed[0][0]] = 100.0
        return out
    ordered = sorted(indexed, key=lambda item: item[1])
    i = 0
    while i < n:
        j = i
        while j + 1 < n and ordered[j + 1][1] == ordered[i][1]:
            j += 1
        mid = (i + j) / 2.0
        pct = 100.0 * mid / float(n - 1)
        for k in range(i, j + 1):
            out[ordered[k][0]] = pct
        i = j + 1
    return out


def _competition_ordinals(values: Sequence[float | None]) -> list[int | None]:
    """1 = highest finite value.  Ties share the minimum ordinal."""
    indexed = [(i, v) for i, v in enumerate(values) if v is not None]
    out: list[int | None] = [None] * len(values)
    if not indexed:
        return out
    ordered = sorted(indexed, key=lambda item: item[1], reverse=True)
    rank = 1
    i = 0
    n = len(ordered)
    while i < n:
        j = i
        while j + 1 < n and ordered[j + 1][1] == ordered[i][1]:
            j += 1
        for k in range(i, j + 1):
            out[ordered[k][0]] = rank
        rank += (j - i + 1)
        i = j + 1
    return out


def _unrank_reason(ep: EpisodeInput, *, cycle_state: str) -> str | None:
    if cycle_state in CYCLE_REFUSALS:
        return "cycle_refused"
    if ep.name_state != "evaluated":
        return ep.name_reasons[0] if ep.name_reasons else "name_unavailable"
    banned = {"basis_mismatch", "pack_integrity", "no_quote", "stale_quote",
              "no_substrate", "stale_observation"}
    for reason in ep.name_reasons:
        if reason in banned or reason.startswith("reading_stale") \
                or reason.startswith("reading_unavailable"):
            return reason
    if ep.availability in NULL_AVAILABILITY:
        return "stale_observation" if ep.availability == "stale" else "unavailable_observation"
    if ep.history_freshness in NULL_AVAILABILITY:
        return "stale_observation" if ep.history_freshness == "stale" else "unavailable_history"
    state = str(ep.state or "")
    if state not in DEVELOPING_STATES:
        return "not_developing"
    return None


def _empty_component(key: str, *, unavailable: Sequence[str],
                     reason: str | None = None) -> dict[str, Any]:
    return {
        "key": key,
        "index": None,
        "value": None,
        "inputs": {},
        "cs": {},
        "unavailable": list(unavailable),
        "reason": reason,
    }


def _priority_shell(ep: EpisodeInput, *, reason: str, computed_at: str | None,
                    population_n: int | None = None) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "policy_version": POLICY_VERSION,
        "status": STATUS,
        "meaning": MEANING,
        "does_not_claim": list(DOES_NOT_CLAIM),
        "priority_value": None,
        "priority_index": None,
        "ordinal": None,
        "population_n": population_n,
        "computed_at": computed_at,
        "known_at": ep.known_at,
        "components": [_empty_component(name, unavailable=list(keys),
                                        reason=reason)
                       for name, keys in DIMENSIONS],
        "evidence_refs": list(ep.evidence_refs),
        "pack_hash": ep.pack_hash,
        "substrate_fingerprint": ep.substrate_fingerprint,
        "abstention": reason,
        "ticker": ep.ticker,
        "detector_id": ep.detector_id,
        "variant": ep.variant,
        "state": ep.state,
        "first_armed_at": ep.first_armed_at,
        "candidate_at": ep.candidate_at,
        "last_observed_at": ep.last_observed_at,
    }


def _name_snapshots(
    rankable: Sequence[tuple[int, EpisodeInput, Mapping[str, float | None]]],
) -> dict[str, Mapping[str, float | None]]:
    """One current name snapshot per ticker.

    Deterministic: the first expert in stable ``(detector_id, variant)`` order
    supplies the snapshot measures.  Live wiring already shares name-level
    measures across experts of the same ticker; this is the calibration unit,
    not a collapse of expert identity.
    """
    ordered = sorted(
        rankable,
        key=lambda row: (row[1].ticker, row[1].detector_id, row[1].variant or ""),
    )
    snapshots: dict[str, Mapping[str, float | None]] = {}
    for _i, ep, measures in ordered:
        snapshots.setdefault(ep.ticker, measures)
    return snapshots


def _submeasure_cs(
    snapshots: Mapping[str, Mapping[str, float | None]],
) -> dict[str, dict[str, float | None]]:
    """Percentile each whitelist submeasure across unique name snapshots."""
    tickers = sorted(snapshots)
    cs: dict[str, dict[str, float | None]] = {ticker: {} for ticker in tickers}
    for key in MEASURE_KEYS:
        raws = [snapshots[ticker].get(key) for ticker in tickers]
        for ticker, pct in zip(tickers, _percentiles(raws)):
            cs[ticker][key] = pct
    return cs


def assign(
    episodes: Sequence[EpisodeInput],
    *,
    computed_at: str | None,
    cycle_state: str = "live",
) -> dict[str, Any]:
    """Rank ``episodes`` under RP1.  Order of ``episodes`` is irrelevant.

    Calibration population = unique current name snapshots.  Each rankable
    expert observation remains its own row and receives the snapshot's
    canonical ``priority_value``.
    """
    items = list(episodes)
    if cycle_state in CYCLE_REFUSALS:
        board = [_priority_shell(ep, reason="cycle_refused",
                                 computed_at=computed_at, population_n=0)
                 for ep in items]
        return _board(board, computed_at=computed_at, cycle_state=cycle_state)

    prelim: list[tuple[EpisodeInput, dict[str, float | None], str | None]] = []
    for ep in items:
        reason = _unrank_reason(ep, cycle_state=cycle_state)
        measures = _whitelisted(ep.measures)
        if reason is None:
            available_dims = sum(
                1 for _, keys in DIMENSIONS
                if _dimension_available(measures, keys))
            if available_dims < MIN_DIMENSIONS:
                reason = "insufficient_coverage"
        prelim.append((ep, measures, reason))

    rankable = [(i, ep, measures) for i, (ep, measures, reason) in enumerate(prelim)
                if reason is None]
    snapshots = _name_snapshots(rankable)
    tickers = sorted(snapshots)
    population_n = len(tickers)
    cs_by_ticker = _submeasure_cs(snapshots) if tickers else {}

    dim_by_ticker: dict[str, dict[str, float | None]] = {
        ticker: {} for ticker in tickers}
    canonical: dict[str, float | None] = {}
    for ticker in tickers:
        for name, keys in DIMENSIONS:
            dim_by_ticker[ticker][name] = _mean_available(
                [cs_by_ticker[ticker].get(k) for k in keys])
        canonical[ticker] = _mean_available(
            [dim_by_ticker[ticker][name] for name, _ in DIMENSIONS])
    ordinal_by_ticker = dict(zip(
        tickers, _competition_ordinals([canonical[t] for t in tickers])))

    board: list[dict[str, Any]] = []
    for _i, (ep, measures, reason) in enumerate(prelim):
        if reason is not None:
            row = _priority_shell(ep, reason=reason, computed_at=computed_at,
                                  population_n=population_n)
            for component in row["components"]:
                keys = dict(DIMENSIONS)[component["key"]]
                component["inputs"] = {k: measures.get(k) for k in keys
                                       if measures.get(k) is not None}
                component["unavailable"] = [k for k in keys
                                            if measures.get(k) is None]
            board.append(row)
            continue
        ticker_cs = cs_by_ticker[ep.ticker]
        ticker_dims = dim_by_ticker[ep.ticker]
        priority_value = canonical[ep.ticker]
        components = []
        unavailable_all = []
        for name, keys in DIMENSIONS:
            present = {k: measures.get(k) for k in keys if measures.get(k) is not None}
            missing = [k for k in keys if measures.get(k) is None]
            unavailable_all.extend(missing)
            dim_value = ticker_dims[name]
            components.append({
                "key": name,
                "index": None if dim_value is None else round(dim_value),
                "value": dim_value,
                "inputs": present,
                "cs": {k: ticker_cs.get(k) for k in keys
                       if ticker_cs.get(k) is not None},
                "unavailable": missing,
                "reason": None if present else "dimension_unavailable",
            })
        board.append({
            "schema": SCHEMA,
            "policy_version": POLICY_VERSION,
            "status": STATUS,
            "meaning": MEANING,
            "does_not_claim": list(DOES_NOT_CLAIM),
            "priority_value": priority_value,
            "priority_index": (None if priority_value is None
                               else int(round(priority_value))),
            "ordinal": ordinal_by_ticker[ep.ticker],
            "population_n": population_n,
            "computed_at": computed_at,
            "known_at": ep.known_at,
            "components": components,
            "evidence_refs": list(ep.evidence_refs),
            "pack_hash": ep.pack_hash,
            "substrate_fingerprint": ep.substrate_fingerprint,
            "abstention": None,
            "unavailable": unavailable_all,
            "ticker": ep.ticker,
            "detector_id": ep.detector_id,
            "variant": ep.variant,
            "state": ep.state,
            "first_armed_at": ep.first_armed_at,
            "candidate_at": ep.candidate_at,
            "last_observed_at": ep.last_observed_at,
        })
    return _board(board, computed_at=computed_at, cycle_state=cycle_state)


def _board(rows: Sequence[Mapping[str, Any]], *, computed_at: str | None,
           cycle_state: str) -> dict[str, Any]:
    ranked = [r for r in rows if r.get("abstention") is None]
    ranked_sorted = sorted(
        ranked,
        key=lambda r: (int(r["ordinal"] or 10**9),
                       str(r.get("detector_id") or ""),
                       str(r.get("variant") or ""),
                       str(r.get("ticker") or "")),
    )
    unranked = [r for r in rows if r.get("abstention") is not None]
    unranked_sorted = sorted(
        unranked,
        key=lambda r: (str(r.get("abstention") or ""),
                       str(r.get("detector_id") or ""),
                       str(r.get("variant") or ""),
                       str(r.get("ticker") or "")),
    )
    population_n = 0
    for row in ranked:
        n = row.get("population_n")
        if isinstance(n, int):
            population_n = n
            break
    return {
        "schema": SCHEMA,
        "policy_version": POLICY_VERSION,
        "status": STATUS,
        "meaning": MEANING,
        "does_not_claim": list(DOES_NOT_CLAIM),
        "computed_at": computed_at,
        "cycle_state": cycle_state,
        "population_n": population_n,
        "episodes": list(ranked_sorted) + list(unranked_sorted),
    }


def presentation_violations(node: Any) -> list[str]:
    """Keys/labels that would imply probability, validation, or edge."""
    found: list[str] = []

    def walk(obj: Any, path: str) -> None:
        if isinstance(obj, Mapping):
            for key, value in obj.items():
                low = str(key).lower()
                for token in BANNED_PRESENTATION:
                    if token.replace(" ", "_") == low or token == low:
                        found.append(f"{path}.{key}")
                if isinstance(value, str):
                    blob = value.lower()
                    for token in BANNED_PRESENTATION:
                        if token in blob and key not in ("does_not_claim", "meaning"):
                            found.append(f"{path}.{key}={value!r}")
                walk(value, f"{path}.{key}")
        elif isinstance(obj, (list, tuple)):
            for i, item in enumerate(obj):
                walk(item, f"{path}[{i}]")

    walk(node, "$")
    return found


def iso(ts: datetime | None) -> str | None:
    if ts is None:
        return None
    if ts.tzinfo is None:
        raise PriorityError("computed_at must be timezone-aware")
    return ts.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


__all__ = [
    "BENCH_TICKER",
    "BANNED_PRESENTATION",
    "DEVELOPING_STATES",
    "DIMENSIONS",
    "DOES_NOT_CLAIM",
    "EpisodeInput",
    "MEASURE_KEYS",
    "MEANING",
    "MIN_DIMENSIONS",
    "POLICY_VERSION",
    "PriorityError",
    "SCHEMA",
    "STATUS",
    "assign",
    "iso",
    "measures_from_history",
    "presentation_violations",
]
