"""engine.marketing.ad_arena — the split test: arms, assignment, and the ledger.

Ad Central spine, module 4 of 5 (`research/AD_CENTRAL_MASTERPLAN.md` §3).

An **arena** is one pre-registered split test: a frozen primary metric, a unit, a
set of arms (one per creative), a holdout, guardrails, and a stop rule.

Assignment is ``hash(arena_id, unit_key) → arm``.  Stateless and reproducible: no
session store, no cookie jar, no server — which is what makes it workable on a
static site behind a CDN.  The same visitor lands in the same arm on every visit,
forever, because nothing about the assignment depends on when it is computed.

**Assignment weights are frozen at arena creation.**  This is load-bearing, not
conservatism.  If the allocator could vary assignment probability mid-flight, a
returning visitor would flip arms and every one of their later events would be
attributed to a variant they only just met.  So the two knobs are kept apart:

    free planes (owned, organic)   fixed assignment weights; impressions cost
                                   nothing, so equal split learns fastest
    paid plane                     the allocator varies *spend*, never assignment;
                                   the platform decides who sees what, and the
                                   unit is an impression, not a sticky visitor

**Denominators are assignment-time** (masterplan §0 G-B).  `tally()` counts
`assigned` from the assignment ledger and `converted` only from units that appear
in it.  An outcome from a never-assigned unit is dropped and reported as an
anomaly — it is a bug upstream, and silently crediting it to an arm would inflate
that arm's numerator against a denominator that never saw the unit.

Forward-only ledgers; nightly is the sole advancer (G-I).
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from . import ad_stats
from .ledgers import append_jsonl, read_jsonl

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

HOLDOUT = "__holdout__"

DEFAULT_LEDGER_DIR = Path("data") / "marketing" / "ad_central"
ASSIGNMENTS_FILE = "assignments.jsonl"
OUTCOMES_FILE = "outcomes.jsonl"
ARENAS_FILE = "arenas.jsonl"
CREATIVES_FILE = "creatives.jsonl"

SCHEMA = "marketing.ad_arena/v1"

UNITS: tuple[str, ...] = ("visitor", "session", "impression", "account")
STATUSES: tuple[str, ...] = ("planned", "running", "halted", "concluded")

# FNV-1a 32-bit — see `_unit_hash` for why this and not SHA-256.
_FNV_OFFSET = 0x811C9DC5
_FNV_PRIME = 0x01000193
_U32 = 0xFFFFFFFF
_HASH_SPACE = 1 << 32


# ─────────────────────────────────────────────────────────────────────────────
# Arena
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Arena:
    arena_id: str
    hypothesis: str
    plane: str                              # owned | organic | paid
    unit: str                               # visitor | session | impression | account
    primary_metric: str                     # FROZEN at creation (G-E)
    arm_creative_ids: list[str] = field(default_factory=list)
    control_creative_id: str | None = None
    assignment_weights: dict[str, float] = field(default_factory=dict)
    holdout: float = 0.0                    # 0.0–1.0 fraction shown nothing
    n_floor: int = ad_stats.DEFAULT_N_FLOOR
    guardrails: dict[str, float] = field(default_factory=dict)
    secondary_metrics: list[str] = field(default_factory=list)
    status: str = "planned"
    start_at: str | None = None
    stop_at: str | None = None
    mode: str = "shadow"                    # shadow | live
    envelope_usd: float = 0.0

    def as_dict(self) -> dict:
        return {
            "schema": SCHEMA,
            "arena_id": self.arena_id,
            "hypothesis": self.hypothesis,
            "plane": self.plane,
            "unit": self.unit,
            "primary_metric": self.primary_metric,
            "arm_creative_ids": list(self.arm_creative_ids),
            "control_creative_id": self.control_creative_id,
            "assignment_weights": dict(self.assignment_weights),
            "holdout": self.holdout,
            "n_floor": self.n_floor,
            "guardrails": dict(self.guardrails),
            "secondary_metrics": list(self.secondary_metrics),
            "status": self.status,
            "start_at": self.start_at,
            "stop_at": self.stop_at,
            "mode": self.mode,
            "envelope_usd": self.envelope_usd,
        }


def create(
    *,
    arena_id: str,
    hypothesis: str,
    plane: str,
    unit: str,
    primary_metric: str,
    creative_ids: list[str],
    control_creative_id: str | None = None,
    holdout: float = 0.0,
    n_floor: int = ad_stats.DEFAULT_N_FLOOR,
    guardrails: dict[str, float] | None = None,
    secondary_metrics: list[str] | None = None,
    envelope_usd: float = 0.0,
    mode: str = "shadow",
    approvals: set[str] | None = None,
) -> Arena:
    """Create an arena with equal frozen assignment weights.

    The first creative is the control unless one is named.  Weights are equal and
    frozen here on purpose — see the module docstring.

    `mode="live"` requires `approvals` covering every arm (operator ruling
    2026-07-27, `ad_review`).  Shadow arenas are pre-registrations and need none —
    writing down a test you intend to run is not running it.  There is no bypass
    flag: a live arena without a human's approval raises.
    """
    ids = [str(c) for c in creative_ids if str(c)]
    if str(mode) == "live":
        from . import ad_review  # noqa: PLC0415 — avoids an import cycle
        ad_review.assert_approved(ids, approvals)
    control = control_creative_id if control_creative_id in ids else (ids[0] if ids else None)
    weight = round(1.0 / len(ids), 8) if ids else 0.0
    return Arena(
        arena_id=str(arena_id),
        hypothesis=str(hypothesis),
        plane=str(plane),
        unit=str(unit),
        primary_metric=str(primary_metric),
        arm_creative_ids=ids,
        control_creative_id=control,
        assignment_weights={cid: weight for cid in ids},
        holdout=max(0.0, min(1.0, float(holdout))),
        n_floor=int(n_floor),
        guardrails=dict(guardrails or {}),
        secondary_metrics=list(secondary_metrics or []),
        status="planned",
        mode=str(mode),
        envelope_usd=float(envelope_usd),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Assignment
# ─────────────────────────────────────────────────────────────────────────────

def _utf16_units(text: str) -> tuple[int, ...]:
    """The exact sequence JS `String.prototype.charCodeAt` walks.

    Python iterates *code points*; JS iterates *UTF-16 code units*, so an
    astral character (emoji, rare CJK) is one step in Python and two in JS.
    Encoding to UTF-16-LE and reading 16-bit words makes the two agree — the
    whole assignment contract depends on it.
    """
    raw = text.encode("utf-16-le")
    return struct.unpack(f"<{len(raw) // 2}H", raw)


def _unit_hash(arena_id: str, unit_key: str, salt: str = "") -> float:
    """Stable uniform draw in [0, 1) from (arena, unit).

    **Deliberately not SHA-256.**  This hash has to be computed identically in
    the browser (`templates/adtest.js`) so a visitor sees their variant in the
    first paint.  Web Crypto's digest is Promise-only, so a SHA-based assignment
    would render the control, resolve, then swap — a flash of the wrong variant
    on every load, which biases the very metric the test measures.

    So: FNV-1a 32-bit, run forward and then backward, exactly the construction
    already used by the fingerprint in `templates/theme.js`.  Synchronous on
    both sides, and every operation is 32-bit so JS's `Math.imul` / `^` / `>>> 0`
    and Python's mask arithmetic produce bit-identical results.

    Salted per purpose so the holdout draw and the arm draw are independent —
    without the salt, a unit near the bottom of the hash space would be both
    held out *and* systematically assigned to the first arm.

    Parity is enforced by `tests/test_marketing_ad_plane_o.py`, which executes
    the real `adtest.js` under node and compares. Changing either side alone
    silently corrupts every running test, so change both or neither.
    """
    units = _utf16_units(f"{arena_id}\x1f{unit_key}\x1f{salt}")
    a = _FNV_OFFSET
    for u in units:
        a = ((a ^ u) * _FNV_PRIME) & _U32
    b = (_FNV_OFFSET ^ a) & _U32
    for u in reversed(units):
        b = ((b ^ u) * _FNV_PRIME) & _U32
    return b / _HASH_SPACE


def assign(arena: Arena, unit_key: str) -> str | None:
    """Return the creative id this unit sees, `HOLDOUT`, or None if the arena is empty.

    Deterministic and stateless: same (arena, unit) ⇒ same arm, always.  Reads the
    arena's *frozen* weights — never a live allocation — so a budget shift can
    never move a visitor between arms mid-test.
    """
    ids = list(arena.arm_creative_ids)
    if not ids:
        return None

    if arena.holdout > 0.0 and _unit_hash(arena.arena_id, unit_key, "holdout") < arena.holdout:
        return HOLDOUT

    weights = [max(0.0, float(arena.assignment_weights.get(cid, 0.0))) for cid in ids]
    total = sum(weights)
    if total <= 0.0:
        weights = [1.0] * len(ids)
        total = float(len(ids))

    draw = _unit_hash(arena.arena_id, unit_key, "arm") * total
    cumulative = 0.0
    for cid, w in zip(ids, weights):
        cumulative += w
        if draw < cumulative:
            return cid
    return ids[-1]


# ─────────────────────────────────────────────────────────────────────────────
# Ledgers (forward-only; nightly is the sole advancer — G-I)
# ─────────────────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _dir(root: Path | str | None = None) -> Path:
    return (Path(root) if root is not None else Path(".")) / DEFAULT_LEDGER_DIR


def record_assignment(
    arena_id: str, unit_key: str, creative_id: str,
    *, root: Path | str | None = None, at: str | None = None,
) -> bool:
    """Append one assignment.  This row IS the denominator (G-B)."""
    return append_jsonl(_dir(root) / ASSIGNMENTS_FILE, {
        "arena_id": str(arena_id),
        "unit_key": str(unit_key),
        "creative_id": str(creative_id),
        "at": at or _now(),
    })


def record_outcome(
    arena_id: str, unit_key: str, metric: str,
    *, value: float = 1.0, root: Path | str | None = None, at: str | None = None,
) -> bool:
    """Append one outcome.  Carries no creative id — the assignment ledger owns that.

    Letting an outcome name its own arm is how attribution drifts: a client that
    reports the variant it *thinks* it saw can disagree with the one it was
    assigned, and the disagreement always resolves in favour of whichever arm the
    buggy client over-reports.  `tally()` joins on `unit_key` instead.
    """
    return append_jsonl(_dir(root) / OUTCOMES_FILE, {
        "arena_id": str(arena_id),
        "unit_key": str(unit_key),
        "metric": str(metric),
        "value": float(value),
        "at": at or _now(),
    })


def arm(arena: Arena, approvals: set[str] | None, *, note: str = "") -> Arena:
    """The ONLY sanctioned way an arena starts showing ads to real visitors.

    Setting `status`/`mode` by hand is what let an un-reviewed hero test go live;
    this is the transition with the gate attached. Raises unless a person has
    approved every arm.
    """
    from . import ad_review  # noqa: PLC0415
    ad_review.assert_approved(arena.arm_creative_ids, approvals)
    arena.status = "running"
    arena.mode = "live"
    if note:
        arena.hypothesis = arena.hypothesis or note
    return arena


def pause(arena: Arena) -> Arena:
    """Stop showing ads without concluding the test. Always allowed — the brake
    never needs permission."""
    arena.status = "planned"
    arena.mode = "shadow"
    return arena


def save_arena(arena: Arena, *, root: Path | str | None = None) -> bool:
    return append_jsonl(_dir(root) / ARENAS_FILE, arena.as_dict())


def save_creatives(creatives: list[Any], *, root: Path | str | None = None) -> int:
    """Persist the copy behind each arm.

    Without this the console can only print `adc-d50a1a888439`, which tells a
    reader nothing about which *ad* is winning. Ids are stable, so re-saving the
    same creative is harmless — `load_creatives` keeps the latest row.
    """
    written = 0
    for c in creatives:
        row = c.as_dict() if hasattr(c, "as_dict") else dict(c)
        if row.get("creative_id") and append_jsonl(_dir(root) / CREATIVES_FILE, row):
            written += 1
    return written


def load_creatives(*, root: Path | str | None = None) -> dict[str, dict]:
    """Latest row per creative_id, keyed by id."""
    out: dict[str, dict] = {}
    for row in read_jsonl(_dir(root) / CREATIVES_FILE):
        cid = row.get("creative_id")
        if cid:
            out[str(cid)] = row
    return out


def load_arenas(*, root: Path | str | None = None) -> list[Arena]:
    """Latest row per arena_id wins (the ledger is append-only, so state is the tail)."""
    latest: dict[str, dict] = {}
    for row in read_jsonl(_dir(root) / ARENAS_FILE):
        aid = row.get("arena_id")
        if aid:
            latest[str(aid)] = row
    out: list[Arena] = []
    for row in latest.values():
        try:
            out.append(Arena(
                arena_id=row["arena_id"],
                hypothesis=row.get("hypothesis", ""),
                plane=row.get("plane", "owned"),
                unit=row.get("unit", "visitor"),
                primary_metric=row.get("primary_metric", ""),
                arm_creative_ids=list(row.get("arm_creative_ids") or []),
                control_creative_id=row.get("control_creative_id"),
                assignment_weights=dict(row.get("assignment_weights") or {}),
                holdout=float(row.get("holdout") or 0.0),
                n_floor=int(row.get("n_floor") or ad_stats.DEFAULT_N_FLOOR),
                guardrails=dict(row.get("guardrails") or {}),
                secondary_metrics=list(row.get("secondary_metrics") or []),
                status=row.get("status", "planned"),
                start_at=row.get("start_at"),
                stop_at=row.get("stop_at"),
                mode=row.get("mode", "shadow"),
                envelope_usd=float(row.get("envelope_usd") or 0.0),
            ))
        except Exception:  # noqa: BLE001 — a malformed row must not blank the panel
            continue
    return sorted(out, key=lambda a: a.arena_id)


# ─────────────────────────────────────────────────────────────────────────────
# Tally — where G-B is enforced
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Tally:
    arms: list[ad_stats.Arm] = field(default_factory=list)
    holdout_assigned: int = 0
    holdout_converted: int = 0
    anomalies: dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "arms": [a.as_dict() for a in self.arms],
            "holdout_assigned": self.holdout_assigned,
            "holdout_converted": self.holdout_converted,
            "anomalies": dict(self.anomalies),
        }


def tally(
    arena: Arena,
    assignments: Iterable[dict[str, Any]],
    outcomes: Iterable[dict[str, Any]],
    *,
    metric: str | None = None,
    spend_by_creative: dict[str, float] | None = None,
    labels: dict[str, str] | None = None,
) -> Tally:
    """Fold the ledgers into `ad_stats.Arm` rows.

    The denominator is the count of distinct units **assigned** to each arm.  A
    unit that converted without an assignment row is dropped into
    ``anomalies["outcome_without_assignment"]`` rather than credited: it has a
    numerator and no denominator, and quietly adding one to the arm it claims
    would be an outcome-conditioned denominator wearing a different hat.

    A unit is counted once no matter how many outcome rows it emits — repeat
    conversions are a different question than conversion rate, and mixing them
    turns one enthusiastic visitor into a winning variant.
    """
    want_metric = metric or arena.primary_metric

    assigned_by_unit: dict[str, str] = {}
    duplicates = 0
    for row in assignments:
        if str(row.get("arena_id")) != arena.arena_id:
            continue
        unit = str(row.get("unit_key") or "")
        cid = str(row.get("creative_id") or "")
        if not unit or not cid:
            continue
        prior = assigned_by_unit.get(unit)
        if prior is not None:
            # First assignment wins; a later contradicting row is a bug worth surfacing.
            if prior != cid:
                duplicates += 1
            continue
        assigned_by_unit[unit] = cid

    converted_units: set[str] = set()
    orphans = 0
    wrong_metric = 0
    for row in outcomes:
        if str(row.get("arena_id")) != arena.arena_id:
            continue
        if str(row.get("metric")) != want_metric:
            wrong_metric += 1
            continue
        unit = str(row.get("unit_key") or "")
        if not unit:
            continue
        if unit not in assigned_by_unit:
            orphans += 1
            continue
        converted_units.add(unit)

    counts: dict[str, list[int]] = {cid: [0, 0] for cid in arena.arm_creative_ids}
    counts[HOLDOUT] = [0, 0]
    for unit, cid in assigned_by_unit.items():
        bucket = counts.setdefault(cid, [0, 0])
        bucket[0] += 1
        if unit in converted_units:
            bucket[1] += 1

    spend = spend_by_creative or {}
    arms = [
        ad_stats.Arm(
            arm_id=cid,
            creative_id=cid,
            assigned=counts.get(cid, [0, 0])[0],
            converted=counts.get(cid, [0, 0])[1],
            spend_usd=float(spend.get(cid, 0.0)),
            is_control=(cid == arena.control_creative_id),
            label=str((labels or {}).get(cid, "")),
        )
        for cid in arena.arm_creative_ids
    ]

    anomalies = {
        "outcome_without_assignment": orphans,
        "conflicting_assignment": duplicates,
        "outcome_other_metric": wrong_metric,
    }
    return Tally(
        arms=arms,
        holdout_assigned=counts[HOLDOUT][0],
        holdout_converted=counts[HOLDOUT][1],
        anomalies={k: v for k, v in anomalies.items() if v},
    )


def tally_from_ledgers(
    arena: Arena, *, root: Path | str | None = None,
    spend_by_creative: dict[str, float] | None = None,
    labels: dict[str, str] | None = None,
) -> Tally:
    """`tally()` over the on-disk ledgers.  Labels default to the stored headlines."""
    d = _dir(root)
    if labels is None:
        labels = {
            cid: str(row.get("headline") or "")
            for cid, row in load_creatives(root=root).items()
        }
    return tally(
        arena,
        read_jsonl(d / ASSIGNMENTS_FILE),
        read_jsonl(d / OUTCOMES_FILE),
        spend_by_creative=spend_by_creative,
        labels=labels,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Guardrails
# ─────────────────────────────────────────────────────────────────────────────

def check_guardrails(arena: Arena, observed: dict[str, float]) -> list[dict[str, Any]]:
    """Return guardrail breaches.

    A guardrail is a *ceiling* on harm (refund rate, unsubscribe rate, support
    load).  Breaching one HALTS the arena.

    This is not a violation of the frozen-primary-metric law (G-E), and the
    distinction matters: G-E stops a secondary metric from declaring a *winner* —
    from being mined until something looks significant.  A guardrail can only ever
    stop the test, never win it, so it cannot manufacture a finding.  Stopping for
    harm on a non-primary metric is the whole point of having one.
    """
    breaches: list[dict[str, Any]] = []
    for name, ceiling in (arena.guardrails or {}).items():
        if name not in observed:
            continue
        value = float(observed[name])
        if value > float(ceiling):
            breaches.append({
                "guardrail": name,
                "ceiling": float(ceiling),
                "observed": value,
                "action": "halt",
            })
    return breaches


# ─────────────────────────────────────────────────────────────────────────────
# Readout
# ─────────────────────────────────────────────────────────────────────────────

def readout(
    arena: Arena,
    tallied: Tally,
    *,
    credible_level: float = ad_stats.DEFAULT_CREDIBLE_LEVEL,
    decisive: float = ad_stats.DEFAULT_DECISIVE,
    practical_pp: float = ad_stats.DEFAULT_PRACTICAL_PP,
    prior_alpha: float = ad_stats.DEFAULT_PRIOR_ALPHA,
    prior_beta: float = ad_stats.DEFAULT_PRIOR_BETA,
) -> dict[str, Any]:
    """Full arena readout: verdict, per-arm numbers, holdout, anomalies."""
    r = ad_stats.analyze(
        tallied.arms,
        primary_metric=arena.primary_metric,
        n_floor=arena.n_floor,
        prior_alpha=prior_alpha,
        prior_beta=prior_beta,
        credible_level=credible_level,
        decisive=decisive,
        practical_pp=practical_pp,
    )
    out = r.as_dict()
    out["arena_id"] = arena.arena_id
    out["plane"] = arena.plane
    out["unit"] = arena.unit
    out["status"] = arena.status
    out["mode"] = arena.mode
    out["hypothesis"] = arena.hypothesis
    out["holdout"] = {
        "fraction": arena.holdout,
        "assigned": tallied.holdout_assigned,
        "converted": tallied.holdout_converted,
    }
    out["anomalies"] = dict(tallied.anomalies)
    return out
