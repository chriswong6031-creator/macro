"""US Prophet C1 evidence-family fusion — the LIVE board ranker (``us_prophet_v3``).

WHAT THIS IS.  One vote per evidence FAMILY, equal weight, no fitting beyond a
within-night normalization.  Per member: the cross-sectional percentile rank
(average ties) of the value oriented by its REGISTERED sign.  Per family: the mean
of its present members' percentiles.  The fusion score: the equal-weight mean of the
present family scores, on a 0-100 scale.

WHERE IT CAME FROM, AND WHY THE MATH IS NOT RE-DERIVED HERE.  This is the C1 rung of
``WS:PROPHET-CONDITIONAL-FUSION`` — raced frozen and non-promotion-bearing in PR-1b
(#5667) as ``scripts/prophet_fusion_race.build_c1``.  The Chairman override of
2026-08-15 made it the canonical US board ranker, which means the construction had to
leave ``scripts/`` for an engine module the nightly may import.  The port is an
EXTRACTION, not a re-implementation: :func:`aggregate` is byte-parity-pinned against
``build_c1`` over the frozen research frame by
``tests/test_us_prophet_fusion.py::TestByteParityWithTheRacedC1``.  Production code
never imports ``research/`` or ``scripts/``; the parity TEST does, which is the only
place the two are allowed to meet.

THE TWO HALVES, KEPT APART ON PURPOSE.

  * :func:`admit_members` — the FLOOR evaluation.  Which registered members are
    allowed to vote on a frame, on two axes: PRESENCE (coverage) and VARIANCE.
  * :func:`aggregate` — the C1 arithmetic, over an already-decided admitted set.

They are separate functions because the frozen race and the live board evaluate the
FLOORS over different frames while running identical ARITHMETIC.  PR-1b's race
computed coverage over its whole 24-date frame — lawful for a frozen counterfactual,
and a look-ahead if a live board did it, because tonight's ranker would be consulting
a member's coverage on nights that have not happened.  #5700 named the prospective
form as unfinished work and PR-3's shadow lane inherited it.  The Chairman override
needed it BEFORE that lane, so it is implemented here: the live board calls
:func:`admit_members` with tonight's pool as the whole frame, and the parity test
calls it with the frozen 24-date frame and reproduces the race exactly.  One code
path, two frames.

THE AS-OF-NIGHT VARIANCE FLOOR (the derivation, so a reader can check it).  The
registered law (``research/prophet_fusion/families.yml`` ``variance_floor_spec``) is:
count, per date, the DISTINCT non-null sign-oriented values among that date's rows; a
date "carries variation" when that count is >= 2; a member is VOTE-INERT on the frame
when the share of frame dates carrying variation falls below 0.50.  On a ONE-DATE
frame — which is what a live board is — that share can only be 1.0 or 0.0, so the
rule collapses without loss to: *a member votes tonight iff tonight's pool holds at
least two distinct non-null oriented values for it*.  Nothing is relaxed and no
threshold is re-chosen; the general rule is evaluated on the frame the board actually
has.  This is the axis that PR-1b measured and could not act on: ``news_burst`` fired
on 19 of 1,493 graded rows, its within-date percentile was a near-constant, F8's
leave-one-family-out delta was exactly 0.000 with CI [0, 0] — and the 0.50 PRESENCE
floor admitted it anyway, because presence cannot see a column that is present and
constant.

NULL IS NOT ZERO, AT EVERY LAYER.  A member with no reading for a row ABSTAINS: its
percentile is null and the family mean is taken over the members that did answer.  A
family with no surviving member is ABSENT and is listed with its reason.  A row with
no family at all is scored ``None`` — never 0.0 — and the board's sort puts it after
every scored row in its stage bucket rather than pretending it earned the bottom
score.  A night with no surviving family at all is a REFUSAL
(:class:`FusionUnavailable`), which the board answers with an explicitly stamped
degradation mode, never by quietly ranking on something else.

WHAT MAY NEVER ENTER (:data:`FORBIDDEN_INPUTS`).  Cross-desk COUNTS of agreeing
evidence (``confluence_k``, ``altdata_conv_gte2``) are the anti-double-count budget
spent as one vote, which is the thing the family construct exists to forbid.  The
champion's own composites (``potential_score``, ``conviction``, ``name_score``,
``score``) are BASELINES: a baseline ingested as evidence cannot be beaten by
anything, it is merely re-fit.  Reaching the feature path with one of these raises.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

__all__ = [
    "FUSION_CONSTRUCTION",
    "FORBIDDEN_INPUTS",
    "REGISTERED_SIGNS",
    "FAMILY_KEYS",
    "STRUCTURAL_FAMILY_NOTES",
    "PRESENCE_FLOOR",
    "VARIANCE_MIN_DISTINCT",
    "FusionRefusal",
    "FusionUnavailable",
    "ForbiddenCompositeRefusal",
    "RegisteredSign",
    "Admission",
    "FusionPlane",
    "extract_members",
    "oriented_value",
    "percentile_rank",
    "admit_members",
    "aggregate",
    "fuse_board",
]


# --------------------------------------------------------------------------- #
# refusals
# --------------------------------------------------------------------------- #

class FusionRefusal(Exception):
    """The fusion plane cannot be built as specified."""


class FusionUnavailable(FusionRefusal):
    """No family survived the floors — there is no lawful fusion order tonight.

    A vote with no voters is not a null result about the evidence, it is a null
    result about the FRAME (§9.9 abstention semantics).  The board answers this by
    publishing a distinctly stamped degradation mode, never by scoring rows 0.
    """


class ForbiddenCompositeRefusal(FusionRefusal):
    """A composite or a cross-desk count reached the feature path."""

    def __init__(self, column: str) -> None:
        self.column = column
        super().__init__(
            f"{column!r} may never be a C1 member: cross-desk counts spend the "
            "anti-double-count budget as a single vote, and a champion composite "
            "ingested as evidence cannot be beaten by anything — it is merely re-fit "
            "(masterplan §5.2 + the C1 fence).")


# --------------------------------------------------------------------------- #
# the sign law — ported verbatim from the raced registry
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class RegisteredSign:
    """One registered member: where it lives, which way is good, how to read it."""

    column: str
    family: str
    sign: int
    kind: str                    # continuous | flag | ordinal | categorical
    source: str
    mapping: Mapping[str, float] | None = None

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"column": self.column, "family": self.family,
                               "sign": int(self.sign), "kind": self.kind,
                               "source": self.source}
        if self.mapping is not None:
            out["mapping"] = {str(k): float(v) for k, v in self.mapping.items()}
        return out


#: Tier ordinal.  CHAMPION-INDEPENDENT: read off the GATE's own documented cascade
#: rank (``engine/signal_gate.py`` ``_CASCADE_RANK`` / :func:`engine.signal_gate.
#: tier_rank`, operator-ratified 2026-07-06), NOT off ``us_board_rank._SIGNAL_BASE``.
#: The two agree on T2 > T1 > T3; citing the gate keeps F1's vote from being the
#: champion's own constant re-entering as evidence.
_TIER_ORDINAL = {"T2": 4.0, "T1": 3.0, "T3": 1.0, "T4": 0.0}

#: GEX verdict vocabulary, read from ``engine/gex_confirm.py`` ``_LABEL``.  NOTE the
#: vocabulary is confirm / neutral / **caution** — there is no "infirm" value.
_GEX_ORDINAL = {"confirm": 1.0, "neutral": 0.0, "caution": -1.0}

#: The eight registered families, in registry order.  A family with no surviving
#: member is ABSENT and says why; it is never silently skipped.
FAMILY_KEYS: tuple[str, ...] = (
    "F1_TECHNICAL_CONFLUENCE",
    "F2_MOMENTUM_EXTENSION",
    "F3_THEME_STRUCTURE",
    "F4_CATALYST_EVENT",
    "F5_FLOW_POSITIONING",
    "F6_MACRO_REGIME",
    "F7_QUALITY_FUNDAMENTAL",
    "F8_ATTENTION_CROWDING",
)

#: Families expected ABSENT with the reason each is absent.  F6 is STRUCTURALLY
#: excluded (row-constant per night, so cross-sectionally degenerate by construction)
#: — a different fact from a family whose members the board does not carry, and the
#: receipt must not blur them.
STRUCTURAL_FAMILY_NOTES: dict[str, str] = {
    "F3_THEME_STRUCTURE": (
        "absent_from_frame: the board row carries no theme / basket / relay evidence "
        "column (sector is IDENTITY, and donor_state/donor_sector are page-level "
        "constants). Not measured here."),
    "F6_MACRO_REGIME": (
        "STRUCTURALLY EXCLUDED, not missing: F6 is row-constant per night (one value "
        "for every name), so it is cross-sectionally DEGENERATE by construction and "
        "cannot rank names. Lawful only as a router/interaction axis."),
    "F7_QUALITY_FUNDAMENTAL": (
        "absent_from_frame: the only F7-adjacent field on the board row is "
        "`archetype`, which routes through the Stock Identity fingerprint interfaces "
        "and never raw. No a-priori ordinal direction is filed for a nominal "
        "category, and reading one off outcomes would be an audition. Not raced."),
}

#: The registered members, ported from ``scripts/prophet_fusion_race.REGISTERED_SIGNS``
#: (PR-1b, #5667).  Every ``source`` is the a-priori PRODUCER direction; not one of
#: them was read off an outcome, which is what keeps C1 an unfitted glass-box vote.
REGISTERED_SIGNS: dict[str, RegisteredSign] = {
    "alpha": RegisteredSign(
        column="alpha", family="F2_MOMENTUM_EXTENSION", sign=+1, kind="continuous",
        source=(
            "registry F2.residual_alpha — the selection axis the retired v2 scorer's "
            "25-point edge leg read (a higher alpha percentile earned more points). "
            "A-PRIORI producer direction. The frozen race measured this axis NEGATIVE "
            "against forward excess on its frame; that measurement is an OUTCOME and "
            "is therefore not a sign source."),
    ),
    "off_high": RegisteredSign(
        column="off_high", family="F2_MOMENTUM_EXTENSION", sign=+1, kind="continuous",
        source=(
            "registry F2.relative_strength member semantics ('RS measures / distance "
            "from high'). off_high is a non-positive percentage distance below the "
            "high, so a value nearer zero is nearer the high and is the stronger "
            "relative-strength reading."),
    ),
    "tier_cascade": RegisteredSign(
        column="tier_cascade", family="F1_TECHNICAL_CONFLUENCE", sign=+1,
        kind="ordinal", mapping=_TIER_ORDINAL,
        source=(
            "engine/signal_gate.py _CASCADE_RANK and tier_rank() — the GATE's own "
            "documented ordering (operator-ratified 2026-07-06: T2 confirmed cross is "
            "best, then T1 held take, then T3 anticipation, then T4). Cited from the "
            "gate deliberately, not from us_board_rank._SIGNAL_BASE, so F1's vote is "
            "not the retired champion's own constant re-entering as evidence."),
    ),
    "sue_fresh": RegisteredSign(
        column="sue_fresh", family="F4_CATALYST_EVENT", sign=+1, kind="flag",
        source=(
            "registry F4.sue_surprise producer semantics — the chip fires on a fresh "
            "POSITIVE standardized earnings surprise (sue_z present AND "
            "sue_fresh_days <= 60); PEAD's a-priori direction is positive. BINDING "
            "WARNING carried from the registry: sue_phase0.json's shallow-panel "
            "'WIRE' verdict was REVERSED by the deep survivorship-clean panel "
            "(IC 0.0006). The sign is the producer's a-priori direction, never a "
            "live GO."),
    ),
    "smartmoney_add": RegisteredSign(
        column="smartmoney_add", family="F5_FLOW_POSITIONING", sign=+1, kind="flag",
        source=(
            "registry F5.smart_money_board_chip — the ledger chip fires on the 13F ADD "
            "direction only; accumulation by the tracked cohort is the a-priori "
            "positive direction. The 13F disclosure lag is why the member carries "
            "max_staleness_sessions: 63."),
    ),
    "insider_cluster": RegisteredSign(
        column="insider_cluster", family="F5_FLOW_POSITIONING", sign=+1, kind="flag",
        source=(
            "registry F5.insider_panel — the chip fires on >= 2 insider BUYERS; "
            "cluster BUYING is the a-priori positive direction. TRAIN/SERVE SKEW "
            "carried forward from the race: the panel collector stopped at 2026q1 "
            "(registry serving_dead: true), so on a live board this member is "
            "all-False and the AS-OF-NIGHT VARIANCE FLOOR is what stands it down — "
            "disclosed in the receipt as vote_inert, never silently pre-excluded."),
    ),
    "gex_confirm_verdict": RegisteredSign(
        column="gex_confirm_verdict", family="F5_FLOW_POSITIONING", sign=+1,
        kind="categorical", mapping=_GEX_ORDINAL,
        source=(
            "engine/gex_confirm.py _LABEL and the confirm_at/caution_at thresholds: "
            "the long confirmer's positive verdict is 'confirm' and its negative "
            "verdict is 'caution' — the vocabulary has NO 'infirm' value, and "
            "'neutral' (including the OPEX suppression override) is the zero. The "
            "module's own charter — 'a confirmer can only LOWER confidence, never "
            "manufacture a buy' — is why this is a confirmer sign and not a "
            "standalone ranker."),
    ),
    "news_burst": RegisteredSign(
        column="news_burst", family="F8_ATTENTION_CROWDING", sign=+1, kind="flag",
        source=(
            "PR-1b filed adjudication: the ledger chip fires on >= 3 recent news items "
            "on an ALREADY-ADMITTED name, and the a-priori direction filed for "
            "attention arriving with a catalyst is positive. NAMED AS THE WEAKEST "
            "SIGN IN THIS SET: F8's charter also carries a CROWDING reading under "
            "which a burst is negative. One column gets one home, so the crowding "
            "read is a registered interaction for a later rung and NOT a rival sign "
            "here."),
    ),
}

#: The C1 fence.  These may never reach the feature path — see the module docstring.
FORBIDDEN_INPUTS: frozenset[str] = frozenset({
    "confluence_k", "conviction", "composite_z", "verdict", "band",
    "potential_score", "name_score", "score", "urgency", "act_level",
    "altdata_conv_gte2", "signal_quality", "validation_status",
})

#: Presence floor: a member reading non-null on fewer than this share of the frame's
#: rows cannot be said to have a live channel, and DROPS.
PRESENCE_FLOOR = 0.50

#: Variance floor: a date "carries variation" for a member when it holds at least
#: this many DISTINCT non-null oriented values.  Rank-of-one is degenerate — a single
#: measured value cannot order a cross-section.
VARIANCE_MIN_DISTINCT = 2

#: Share of frame dates that must carry variation before a member may vote.  On a
#: one-date frame (a live board) this can only be 1.0 or 0.0; see the module
#: docstring for why that is the general rule evaluated, not a relaxed one.
VARIANCE_MIN_DATE_SHARE = 0.50

#: The published construction sentence — the receipt's own account of what it did.
FUSION_CONSTRUCTION = (
    "Per member: within-night cross-sectional percentile rank (average ties) of the "
    "value oriented by its REGISTERED sign. Per family: the mean of its present "
    "members' percentiles. Fusion: the equal-weight mean of the present family "
    "scores, x100. No interactions, no fitting beyond the per-night normalization, no "
    "weight read off any outcome. A member below "
    f"{PRESENCE_FLOOR:.0%} non-null coverage on tonight's pool DROPS (presence "
    f"floor); a member with fewer than {VARIANCE_MIN_DISTINCT} distinct non-null "
    "oriented values tonight is VOTE-INERT (variance floor) and is disclosed rather "
    "than hidden; a family with no surviving member is ABSENT with its reason; a row "
    "missing a family is scored on the mean of ITS present families, and a row with "
    "no family at all scores null — never zero."
)


# --------------------------------------------------------------------------- #
# small helpers
# --------------------------------------------------------------------------- #

def _finite(value: Any) -> float | None:
    """A finite float, or None.  ``bool`` is rejected — ``True`` is not 1.0 here."""
    if value is None or isinstance(value, bool):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if out != out or out in (float("inf"), float("-inf")):
        return None
    return out


def _dig(row: Mapping[str, Any], *paths: Sequence[str], default: Any = None) -> Any:
    """First non-None value at any of ``paths`` inside nested mappings."""
    for path in paths:
        cur: Any = row
        for key in path:
            if not isinstance(cur, Mapping):
                cur = None
                break
            cur = cur.get(key)
        if cur is not None:
            return cur
    return default


def oriented_value(raw: Any, sign: RegisteredSign) -> float | None:
    """``raw`` read through the member's kind and multiplied by its registered sign.

    Mirrors ``prophet_fusion_race._oriented_values`` value-for-value: a mapped
    vocabulary resolves through the mapping (an unmapped token is UNMEASURED, not a
    zero), a flag reads 1.0/0.0 with None staying null, and anything else coerces
    numerically with a non-number reading null.
    """
    if sign.mapping is not None:
        if raw is None:
            return None
        mapped = sign.mapping.get(str(raw).strip())
        if mapped is None:
            return None
        return float(mapped) * float(sign.sign)
    if sign.kind == "flag":
        if raw is None:
            return None
        if isinstance(raw, float) and raw != raw:
            return None
        return float(bool(raw)) * float(sign.sign)
    numeric = _finite(raw)
    if numeric is None:
        # A bare bool reaching a continuous member is a producer defect, not a 1.0.
        return None
    return numeric * float(sign.sign)


def percentile_rank(values: Sequence[float | None]) -> list[float | None]:
    """Percentile rank within the sequence, average ties, nulls stay NULL.

    Byte-equal to pandas ``Series.rank(pct=True, method="average")`` over one group:
    ranks run 1..n over the n NON-NULL entries with ties averaged, and the percentile
    divides by n (the non-null count), not by the row count.  A missing member
    ABSTAINS; it is never handed the mid-pool 0.5, because a neutral vote and no vote
    are different acts.
    """
    present = [(index, value) for index, value in enumerate(values) if value is not None]
    n = len(present)
    out: list[float | None] = [None] * len(values)
    if not n:
        return out
    order = sorted(present, key=lambda pair: pair[1])
    position = 0
    while position < n:
        end = position
        while end + 1 < n and order[end + 1][1] == order[position][1]:
            end += 1
        # ranks are 1-based; the tied block spans [position, end]
        average = (position + end + 2) / 2.0
        for index, _value in order[position:end + 1]:
            out[index] = average / n
        position = end + 1
    return out


def _mean(values: Iterable[float | None]) -> float | None:
    present = [v for v in values if v is not None]
    if not present:
        return None
    return sum(present) / len(present)


# --------------------------------------------------------------------------- #
# member extraction from a LIVE board row
# --------------------------------------------------------------------------- #

def extract_members(row: Mapping[str, Any],
                    verdict: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """The registered members' RAW values off a live board row.

    Every derivation here is the one ``scripts/grade_us_board._row_features`` writes
    into the graded frame the race was run on — same field, same fallback, same
    coercion — so the live plane and the frozen race read the same member from the
    same row.  A derivation that drifted from that function would make the ported
    arithmetic exact and the INPUTS different, which is the subtler half of the same
    mistake; ``tests/test_us_prophet_fusion.py::TestExtractionMirrorsTheGradedFrame``
    pins them together.

    Flags coerce through ``bool`` exactly as the graded frame does, which means a
    producer that is DARK reads all-False rather than all-null.  That is deliberate
    and it is not a hidden zero: the variance floor is the layer that stands a
    constant member down, and it says so in the receipt.
    """
    sig = dict(verdict or {})
    return {
        "alpha": _finite(row.get("alpha")),
        "off_high": _finite(row.get("off_high")),
        "tier_cascade": _dig(row, ("signal", "tier_cascade"),
                             default=sig.get("tier_cascade")),
        "sue_fresh": bool(row.get("sue_z") and (row.get("sue_fresh_days") or 999) <= 60),
        "smartmoney_add": bool(row.get("smartmoney_chip")),
        "insider_cluster": bool((row.get("insider_buyers") or 0) >= 2),
        "gex_confirm_verdict": _dig(row, ("gex_confirm", "verdict"), default=None),
        "news_burst": bool((_dig(row, ("news_burst", "n_recent"), default=0) or 0) >= 3),
    }


# --------------------------------------------------------------------------- #
# the floors
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class Admission:
    """Which members may vote on a frame, and the measured reason for each verdict."""

    admitted: tuple[str, ...]
    dropped: tuple[dict[str, Any], ...]
    frame_dates: int
    frame_rows: int

    def as_dict(self) -> dict[str, Any]:
        return {"admitted": list(self.admitted),
                "dropped": [dict(d) for d in self.dropped],
                "frame_dates": self.frame_dates, "frame_rows": self.frame_rows}


def admit_members(
    frame: Sequence[tuple[Any, Mapping[str, Any]]],
    *,
    signs: Mapping[str, RegisteredSign] | None = None,
    presence_floor: float = PRESENCE_FLOOR,
    apply_variance_floor: bool = True,
) -> Admission:
    """Evaluate the presence and variance floors over ``frame``.

    ``frame`` is ``[(date, {column: raw_value})]`` — one entry per (date, row).  The
    LIVE board hands one night; the parity test hands the frozen 24-date race frame.
    THE FLOORS DECIDE, NOT THE AUTHOR: nothing is pre-excluded for looking weak and
    nothing is kept for looking strong, and every drop is listed with its measurement.

    ``apply_variance_floor=False`` reproduces PR-1b's C1 exactly (presence only) and
    exists for the byte-parity pin; the live board runs with it ON, which is the
    #5700 carry-forward the Chairman override needed before PR-3 could deliver it.
    """
    table = dict(signs or REGISTERED_SIGNS)
    for column in table:
        if column in FORBIDDEN_INPUTS:
            raise ForbiddenCompositeRefusal(column)

    rows = list(frame)
    n_rows = len(rows)
    dates = sorted({str(date) for date, _values in rows})

    admitted: list[str] = []
    dropped: list[dict[str, Any]] = []
    for column, sign in sorted(table.items()):
        oriented = [(str(date), oriented_value(values.get(column), sign))
                    for date, values in rows]
        present = sum(1 for _date, value in oriented if value is not None)
        coverage = (present / n_rows) if n_rows else 0.0
        if coverage < presence_floor:
            dropped.append({"column": column, "family": sign.family,
                            "reason": "below_presence_floor",
                            "coverage": round(coverage, 6),
                            "presence_floor": presence_floor})
            continue
        by_date: dict[str, set[float]] = defaultdict(set)
        rows_per_date: dict[str, int] = defaultdict(int)
        for date, value in oriented:
            rows_per_date[date] += 1
            if value is not None:
                by_date[date].add(value)
        # A date holding fewer than VARIANCE_MIN_DISTINCT ROWS cannot carry variation
        # for ANY member — that is a fact about the pool's size, not about the
        # evidence — so it is excluded from the denominator rather than counted as a
        # date the member failed.  Counting it would make every member on a one-name
        # board vote-inert and refuse the whole plane, turning a legitimately tiny
        # board into a fabricated outage.
        evaluable = [d for d in dates if rows_per_date[d] >= VARIANCE_MIN_DISTINCT]
        varying = sum(1 for date in evaluable
                      if len(by_date.get(date, ())) >= VARIANCE_MIN_DISTINCT)
        share = (varying / len(evaluable)) if evaluable else 1.0
        if apply_variance_floor and evaluable and share < VARIANCE_MIN_DATE_SHARE:
            dropped.append({"column": column, "family": sign.family,
                            "reason": "vote_inert",
                            "coverage": round(coverage, 6),
                            "dates_with_variation": varying,
                            "frame_dates": len(dates),
                            "evaluable_dates": len(evaluable),
                            "variation_share": round(share, 6),
                            "min_variation_share": VARIANCE_MIN_DATE_SHARE,
                            "note": ("present but constant across tonight's pool — "
                                     "a single measured value cannot order a "
                                     "cross-section, so the member is disclosed and "
                                     "stood down rather than voting a flat rank")})
            continue
        admitted.append(column)
    return Admission(admitted=tuple(admitted), dropped=tuple(dropped),
                     frame_dates=len(dates), frame_rows=n_rows)


# --------------------------------------------------------------------------- #
# the C1 arithmetic
# --------------------------------------------------------------------------- #

@dataclass
class FusionPlane:
    """One night's fusion: a score per row plus the receipt that explains it."""

    scores: list[float | None]                       # 0-100, row-aligned; None = no family
    family_scores: list[dict[str, float]]            # row-aligned, present families only
    member_percentiles: list[dict[str, float]]       # row-aligned, admitted members only
    families_present: list[str]
    families_absent: list[dict[str, str]]
    members_voting: list[dict[str, Any]]
    members_dropped: list[dict[str, Any]]
    members_collapsed: list[dict[str, Any]]
    rows_by_n_families: dict[str, int] = field(default_factory=dict)

    def receipt(self) -> dict[str, Any]:
        """The board-level disclosure block — what voted, what abstained, and why."""
        return {
            "construction": FUSION_CONSTRUCTION,
            "families_present": list(self.families_present),
            "families_absent": [dict(f) for f in self.families_absent],
            "members_voting": [dict(m) for m in self.members_voting],
            "members_dropped": [dict(m) for m in self.members_dropped],
            "members_collapsed_as_duplicates": [dict(m) for m in self.members_collapsed],
            "rows_by_n_families_present": dict(self.rows_by_n_families),
            "presence_floor": PRESENCE_FLOOR,
            "variance_floor": {
                "axis": "within_night_distinct_nonnull_oriented_values",
                "min_distinct_values": VARIANCE_MIN_DISTINCT,
                "evaluated": "as_of_night",
            },
            "forbidden_inputs": sorted(FORBIDDEN_INPUTS),
            "duplicate_collapse_law": (
                "agreement inside a family is ONE fact, not N. Two members whose "
                "oriented percentile vectors are identical are the same measurement "
                "under two names; the second is collapsed and listed rather than "
                "averaged in, so the anti-double-count budget cannot be defeated by "
                "registering a column twice."),
        }


def aggregate(rows: Sequence[Mapping[str, Any]],
              admitted: Sequence[str],
              *,
              signs: Mapping[str, RegisteredSign] | None = None,
              family_keys: Sequence[str] = FAMILY_KEYS) -> FusionPlane:
    """C1 over ONE night's pool, given an already-decided admitted member set.

    This is the extracted arithmetic and nothing else — the floors were decided by
    :func:`admit_members` on whatever frame was lawful for the caller.  Byte-parity
    with ``prophet_fusion_race.build_c1`` is pinned on this function.
    """
    table = dict(signs or REGISTERED_SIGNS)
    for column in table:
        if column in FORBIDDEN_INPUTS:
            raise ForbiddenCompositeRefusal(column)

    pool = list(rows)
    n = len(pool)
    keep = [c for c in sorted(admitted) if c in table]

    percentiles: dict[str, list[float | None]] = {}
    for column in keep:
        sign = table[column]
        oriented = [oriented_value(values.get(column), sign) for values in pool]
        percentiles[column] = percentile_rank(oriented)

    family_members: dict[str, list[str]] = defaultdict(list)
    for column in keep:
        family_members[table[column].family].append(column)

    # --- within-family duplicate collapse ---------------------------------------
    # Two members whose ORIENTED percentile vectors are identical are the same
    # measurement wearing two names; averaging both would double-weight it inside the
    # family.  Collapsed members are LISTED, never silently dropped — which columns
    # turned out to be the same reading is itself a redundancy finding.
    collapsed: list[dict[str, Any]] = []
    for family, cols in list(family_members.items()):
        seen: dict[tuple, str] = {}
        kept: list[str] = []
        for column in sorted(cols):
            key = tuple(round(v, 9) if v is not None else -999.0
                        for v in percentiles[column])
            if key in seen:
                collapsed.append({"column": column, "family": family,
                                  "duplicate_of": seen[key],
                                  "reason": "identical oriented percentile vector"})
                continue
            seen[key] = column
            kept.append(column)
        family_members[family] = kept

    families_present: list[str] = []
    families_absent: list[dict[str, str]] = []
    family_scores: list[dict[str, float]] = [{} for _ in range(n)]
    for family in family_keys:
        cols = family_members.get(family) or []
        if not cols:
            reason = STRUCTURAL_FAMILY_NOTES.get(family)
            if reason is None:
                # Name the members that were dropped INTO this absence when we know
                # them; a bare "absent" hides whether a channel died or never existed.
                own = sorted(c for c, s in table.items() if s.family == family)
                reason = (
                    f"no surviving member — every registered member "
                    f"({', '.join(own)}) either is absent from the board row or was "
                    f"stood down by a floor" if own else
                    "no registered member of this family is carried by the board row")
            families_absent.append({"family": family, "reason": reason})
            continue
        families_present.append(family)
        for index in range(n):
            value = _mean(percentiles[column][index] for column in cols)
            if value is not None:
                family_scores[index][family] = value

    if not families_present:
        raise FusionUnavailable(
            "the fusion plane has ZERO surviving families on tonight's pool — every "
            "registered member either is absent from the board row or was stood down "
            "by the presence or variance floor. A vote with no voters is not a null "
            "result about the evidence, it is a null result about the frame.")

    scores: list[float | None] = []
    by_count: dict[str, int] = defaultdict(int)
    for index in range(n):
        present = family_scores[index]
        by_count[str(len(present))] += 1
        mean = _mean(present.values())
        scores.append(None if mean is None else mean * 100.0)

    voting = [dict(table[c].as_dict()) for c in keep
              if c not in {d["column"] for d in collapsed}]
    member_pct: list[dict[str, float]] = []
    for index in range(n):
        member_pct.append({column: percentiles[column][index]
                           for family_cols in family_members.values()
                           for column in family_cols
                           if percentiles[column][index] is not None})

    return FusionPlane(
        scores=scores,
        family_scores=family_scores,
        member_percentiles=member_pct,
        families_present=families_present,
        families_absent=families_absent,
        members_voting=voting,
        members_dropped=[],
        members_collapsed=collapsed,
        rows_by_n_families={k: by_count[k] for k in sorted(by_count, key=int)},
    )


# --------------------------------------------------------------------------- #
# the live entry point
# --------------------------------------------------------------------------- #

def fuse_board(rows: Sequence[Mapping[str, Any]],
               *,
               verdicts: Sequence[Mapping[str, Any] | None] | None = None,
               ) -> FusionPlane:
    """Tonight's fusion plane over a live buy pool, floors evaluated AS OF TONIGHT.

    ``verdicts`` is row-aligned and optional — the caller (``score_rows``) has
    already resolved each row's verdict through its own precedence rules, so it hands
    them in rather than making this module re-derive them and risk a second answer.

    Raises :class:`FusionUnavailable` when no family survives — the caller answers
    that with an explicitly stamped degradation mode, never by ranking on something
    else under the canonical stamp.
    """
    pool = list(rows)
    seq = list(verdicts or ())
    members = [extract_members(row, seq[i] if i < len(seq) else None)
               for i, row in enumerate(pool)]

    admission = admit_members([("live", values) for values in members])
    plane = aggregate(members, admission.admitted)
    plane.members_dropped = [dict(d) for d in admission.dropped]
    return plane
