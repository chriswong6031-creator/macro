"""engine.neuralweb.edge_outcomes — Neural Web edge-outcome ledger (quant wave-2b).

PURPOSE
-------
The Neural Web has typed edges (confluence graph ``confirms``/``leads``/
``contradicts``/``headwind``/``tailwind``; causal-scout candidate edges) but no
ledger anywhere grades **"edge fired → did the target actually move, and with
what lag"**.  The spine grades *signal-fires*; nothing grades *edges*.  This
module is that ledger.

It exists for two reasons, and the second one is a house ruling:

1. **Product read** — which claimed linkages actually propagate.  An edge that
   says "altdata confirms radar" is a claim; this ledger is the record of what
   happened after the claim fired.
2. **CHF-R15 evidence base.**  Verbatim from
   ``research/CAUSAL_HYPOTHESIS_FACTORY_MASTERPLAN_BY_FABLE.md``:

       **CHF-R15 (evidence clocks).** Registry-seed entries (RF-9: no bespoke
       timers): first-edge-batch review clock (~35d after W3 lands), Phase-2
       dedicated-family come-back (2026-10-15, conditional on >=8 matured
       exit-(a)/(b) candidates), and the Phase-3 structure-learner come-back
       (2027-01-15). Grace 7d.

   The Phase-3 structure-learner come-back has no evidence to come back to
   unless edge behaviour is on the record by then.  This ledger accrues it.

RELATION TO CHF-R14 — READ THIS BEFORE EXTENDING
------------------------------------------------
CHF-R14 says, verbatim:

    **CHF-R14 (kills and deferrals registered now).**
    - Full-graph learners (NOTEARS/DAG-GNN/LoRAM/CMIN-style) in v1: KILLED for
      v1; small-universe NOTEARS-with-priors is a Phase-3 candidate behind the
      §7 clock, admissible only after the scout + null library have operated
      for a quarter.
    - Causal-DAG -> portfolio construction: FORBIDDEN (Codex concurs;
      Article 1/2).
    - Weekly full-DAG re-estimation: REJECTED (churn); drift monitors are
      nightly, structure re-estimation is quarterly at most.
    - LLM numeric confidence anywhere in CHF: FORBIDDEN (RF-16 extension).
    - **New fire/outcome ledger: FORBIDDEN (RUL-ORTH-4).**
    - These rows are appended to ``research/DO_NOT_REBUILD.md`` in this PR.

That last bullet is about the **fire substrate**.  RUL-ORTH-4 is quoted in the
same masterplan as "spine remains the sole fire substrate" (§ architecture
limits: "no recomputation of R-ORTH statistics (RUL-ORTH-9), spine remains the
sole fire substrate (RUL-ORTH-4)"), and its table row reads: "reuse with
env-override resolution + honest data-absent degradation (CHF-R6); **no new
fire ledger** (RUL-ORTH-4)".  The kill forbids standing up a *parallel
substrate that decides what fired and computes its own outcomes*.

This module does not do that, by construction:

  * It **never originates a fire.**  A fire is read off ``spine_index.parquet``
    (the sole fire substrate) or off the existing confluence tape.  No new
    fire detection, no new price pipeline, no recomputation of any outcome.
  * It **never grades an outcome.**  Every outcome number it prints is an
    ``outcome_excess`` / ``fwd_mfe_*`` value the spine already graded.  This
    module is a *join* over two existing substrates plus the edge inventory.
  * Its unit of record is the **edge**, which the spine has never carried, and
    which is the object CHF-R15's Phase-3 clock will be asked to judge.

If a future change makes this module compute an outcome, or decide that
something fired on evidence outside the spine/tape, it has become the thing
RUL-ORTH-4 forbids.  Do not make that change.

AUTHORITY
---------
Display-tier, deterministic, zero fitted weights.  Every emitted row stamps the
authority block: not_a_signal, may_rank=False, may_gate=False, may_size=False,
may_escalate=False, display_only=True.  This ledger EVIDENCES; it never scores.
No LLM anywhere in this path (A7 / Article 1).

WHY ``feeds`` EDGES ARE SKIPPED
-------------------------------
``confluence_graph.json`` is dominated by ``feeds`` edges (1,667 of 1,690 in
the 2026-08-05 store — 98.6%, matching the charter census).  A
``feeds`` edge is *static wiring* read out of ``config/synapse.yml``:
producer -> artifact -> consumer.  It asserts that data flows along a pipe, not
that a market subject moves when another one does.  Grading it would produce a
number with no claim behind it — the pipe is either connected or it is not, and
that is a plumbing test, not an outcome test.  Only the five MEASURED edge
types below carry a directional market claim, so only they are inventoried.

PRE-REGISTERED CONSTRUCTION (fixed before the first run; change = amendment)
---------------------------------------------------------------------------
**Fire definition (PRIMARY) — ``spine_asof``:** edge (src -> dst) fires on
session ``t`` iff the resolved SRC subject has >= 1 spine row with
``as_of == t``.  A fire is an *emission*, so src rows need not be graded.  The
fire's direction is the majority sign of ``direction`` over those rows; an
exact tie yields direction 0 and the fire is recorded but excluded from
agreement (``src_direction_ambiguous``).

**Fire definition (VARIANT, disclosed) — ``tape_transition``:** edge fires on
``t`` iff the confluence tape (``confluence_tape.jsonl``) has a row for the src
subject at ``as_of == t`` whose sequence state is ``new`` (first ever
appearance) or ``strengthening`` (``n_independent_confirming`` strictly above
the subject's previous tape session).  Implemented and selectable via
``fire_def=``, but NOT the default, for a structural reason worth stating
plainly: the tape is keyed by **ticker** (``subject`` values are AVGO, BA, CB,
... — 170 distinct symbols over 544 rows in the 2026-08-05 store), while every
edge in the measured inventory is keyed by ``engine:``/``sector:``/``macro:``.
The two subject spaces are disjoint, so the variant runs clean and grades zero
fires against today's inventory.  That is a coverage fact, not a defect: the
variant becomes live the moment ticker-level edges enter the inventory.
Bridging tape subjects to engine ids would be an amendment to this
pre-registration, not a refactor.

**Outcome grading:** for a fire at ``t``, candidate outcome rows are spine rows
matching the DST subject with ``outcome_graded == True``, a non-null
``outcome_excess``, and ``as_of`` within ``LINK_WINDOW_SESSIONS`` sessions of
``t`` on the spine's own session grid.  Per horizon H in ``OUTCOME_HORIZONS``
the dst outcome is the **median** ``outcome_excess`` of the candidates at that
horizon.  Nothing is recomputed and no price store is opened.

**Agreement semantics per edge type** (``claimed_sign``):

    confirms     -> +src_direction   (dst is claimed to move WITH the src)
    leads        -> +src_direction   (same claim, displaced in time)
    contradicts  -> -src_direction   (dst is claimed to move AGAINST the src)
    headwind     -> -1               (dst is claimed to underperform)
    tailwind     -> +1               (dst is claimed to outperform)

An edge "agrees" at horizon H when ``sign(dst_outcome_H) == claimed_sign``.

**Realized lag (report-only, MIN_N-floored):** the smallest horizon H in
``LAG_HORIZONS`` at which ``|dst_outcome_H| >= LAG_SIGMA_K * sigma_H``, where
``sigma_H`` is the standard deviation of the dst subject's OWN ``outcome_excess``
at horizon H over its graded rows strictly before ``t``.  Below
``MIN_N_LAG`` trailing observations the lag is null with a printed reason.

    DEVIATION, DISCLOSED: the charter phrasing is "first *session* in
    (t, t+21] where |dst cumulative excess| crosses 1 sigma".  A session-
    resolution cumulative-excess path for a dst subject is NOT derivable from
    the graded artifacts — the spine stores forward outcomes per signal row,
    not a daily path per subject — and building one would mean opening a new
    price pipeline, which this module is forbidden to do (see RUL-ORTH-4
    above).  The lag is therefore reported on the horizon grid
    {5, 21, 63} sessions, which is a subset of the intended window, and every
    row carries ``lag_basis="horizon_grid"`` so the coarser resolution is never
    mistaken for session resolution.

THE UNSIGNED-OUTCOME TRAP (fail-closed guard — do not remove)
-------------------------------------------------------------
``engine/neuralweb/query.py`` builds the ``track_record`` ledger's rows with

    # outcome_excess: use fwd_mfe for this horizon as proxy if present
    row["outcome_excess"] = _safe_float(r.get(mfe_col))

i.e. for that ledger ``outcome_excess`` IS ``fwd_mfe_H`` — a **max favorable
excursion**, which is unsigned by construction.  Measured on the 2026-07-07
spine: 276,279 graded ``track_record`` rows, ``outcome_excess == fwd_mfe_H``
for 100.0% of them, minimum 0.0000, fraction negative 0.000.  Any directional
agreement computed against it would read ~100% agreement at every horizon and
mean nothing.  ``direction`` is also structurally pinned to 1 on that ledger.

The same assignment appears at THREE sites in query.py covering FOUR ledgers —
``track_record`` (573), ``board_hk``/``board_ca`` (657), ``board_cn`` (742) —
and the board ones are live in the spine with the identical signature
(``board_hk`` 509 rows, ``board_ca`` 330 rows, both min 0.0000, both zero
negatives).  A dst whose outcomes come from any of them is UNGRADEABLE, reason
``dst_outcome_unsigned_mfe_proxy``.  Two checks:

  1. structural — ``ledger in UNSIGNED_OUTCOME_LEDGERS``, and
  2. empirical — a dst cohort with >= ``UNSIGNED_PROBE_MIN_N`` graded outcomes
     and not one negative value.

Be exact about what check 2 is worth: it is a **backstop, not a second lock**.
It fails OPEN on a single negative value — one signed row anywhere in the
cohort and an otherwise-unsigned ledger grades normally, reporting a near-100%
agreement that means nothing.  Only check 1 is fail-closed, which is why the
structural list is pinned against query.py by a source-scan test
(``QUERY_MFE_ASSIGNMENT_SITES``) rather than trusted to stay current on its
own.  Do not describe the pair as "doubled" or "fail-closed" as a whole: the
empirical probe catches an accident, never an adversary.

FILES
-----
Inventory in   : ``data/neuralweb/confluence_graph.json`` (measured edges only)
                 ``data/neuralweb/causal_edges.jsonl``   (scout candidates)
Substrate in   : ``data/neuralweb/spine_index.parquet``  (fires + outcomes)
                 ``data/neuralweb/confluence_tape.jsonl`` (variant fire def)
Ledger out     : ``data/neuralweb/edge_outcomes.jsonl``       (prospective)
                 ``data/neuralweb/edge_outcomes_retro.jsonl`` (retro replay)

The prospective ledger is nightly-only from day one and the two files never
mix: ``scripts/build_edge_outcomes.py --retro`` writes only the retro file, and
``--nightly`` refuses to run outside the nightly lane.

WIRING — DELIBERATELY ABSENT
----------------------------
This PR does NOT touch ``config/dag.yml``, ``.github/workflows/``, or
``config/synapse.yml``.  Four open lanes collide on those files; the wiring
rides a follow-up PR.  Until then the runner is invoked by hand.

FAIL-OPEN CONTRACT
------------------
Every source is read fail-open.  Absent spine -> zero rows plus a gap note.
Absent graph -> zero edges plus a gap note.  Nothing here raises on a corrupt
or missing artifact.
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants — pre-registered; a change here is an amendment, not a refactor
# ---------------------------------------------------------------------------

SCHEMA = "neuralweb.edge_outcomes.v1"
ARTIFACT_ID = "edge-outcomes"
PRODUCED_BY = "engine/neuralweb/edge_outcomes.py"

#: Edge types that carry a directional market claim.  ``feeds`` is excluded on
#: purpose — see the module docstring.
MEASURED_EDGE_TYPES: frozenset[str] = frozenset({
    "confirms", "leads", "contradicts", "headwind", "tailwind",
})

#: Static wiring edges, inventoried nowhere.  Named so the skip is auditable.
WIRING_EDGE_TYPES: frozenset[str] = frozenset({"feeds", "stable"})

#: House floor before ANY per-edge rate is printed.
MIN_N: int = 10

#: Trailing graded observations required before a lag sigma is computed.
MIN_N_LAG: int = 10

#: Sessions after the fire in which a dst outcome row is accepted.
LINK_WINDOW_SESSIONS: int = 5

#: Horizons graded per fire.  21 is the primary verdict horizon (charter §4).
OUTCOME_HORIZONS: tuple[int, ...] = (5, 21, 63)
PRIMARY_HORIZON: int = 21

#: How far back a nightly run re-sweeps.
#:
#: A fire on session t cannot be graded on session t: its outcome rows live in
#: [t, t+LINK_WINDOW] and its longest horizon settles 63 sessions later.  A
#: nightly lane that only ever looked at the newest session would therefore
#: record every fire as an ungraded stub and never revisit it — measured on a
#: 60-night simulation: 0 graded rows, against 39 for a retro over the same
#: store.  The prospective lane sweeps this lookback every night so a fire is
#: re-examined until its outcomes have settled, and the settled row SUPERSEDES
#: the earlier stub (see append_rows).
NIGHTLY_LOOKBACK_SESSIONS: int = max(OUTCOME_HORIZONS) + LINK_WINDOW_SESSIONS

#: Horizon grid the realized-lag estimator walks (subset of (t, t+21] plus 63).
LAG_HORIZONS: tuple[int, ...] = (5, 21, 63)
LAG_SIGMA_K: float = 1.0

#: Ledgers whose ``outcome_excess`` is an unsigned MFE proxy.
#:
#: ``engine/neuralweb/query.py`` assigns ``outcome_excess = <fwd_mfe column>`` at
#: THREE sites, covering FOUR ledger labels:
#:
#:   query.py:573  adapt_track_record  -> ledger "track_record"
#:   query.py:657  adapt_board         -> ledger "board_hk" / "board_ca"
#:   query.py:742  adapt_china_board   -> ledger "board_cn"
#:
#: All four are unsigned by construction.  ``tests/test_edge_outcomes.py``
#: re-scans query.py's source and fails if a fourth assignment site appears, so
#: this list cannot silently fall behind its upstream.  That test is the only
#: coupling: this module never imports from or edits query.py.
UNSIGNED_OUTCOME_LEDGERS: frozenset[str] = frozenset({
    "track_record", "board_hk", "board_ca", "board_cn",
})

#: Number of ``outcome_excess = <fwd_mfe>`` assignment sites in query.py, pinned
#: so a new one trips the source-scan test instead of shipping an unsigned dst
#: as a ~100%-agreement edge.
QUERY_MFE_ASSIGNMENT_SITES: int = 3

#: Cohort size at which the empirical unsigned probe is allowed to fire.
UNSIGNED_PROBE_MIN_N: int = 8

#: Fire definitions.
FIRE_DEF_SPINE = "spine_asof"
FIRE_DEF_TAPE = "tape_transition"
VALID_FIRE_DEFS: frozenset[str] = frozenset({FIRE_DEF_SPINE, FIRE_DEF_TAPE})

#: Row-level authority stamp.  Present on EVERY emitted row.
AUTHORITY_BLOCK: dict[str, bool] = {
    "not_a_signal": True,
    "may_rank": False,
    "may_gate": False,
    "may_size": False,
    "may_escalate": False,
}

#: Ungradeable reason codes.  Every ungraded edge names exactly one.
REASON_SPINE_ABSENT = "spine_absent"
REASON_SRC_UNRESOLVED = "src_unresolved"
REASON_DST_UNRESOLVED = "dst_unresolved"
REASON_SRC_NO_ROWS = "src_no_spine_rows"
REASON_DST_NO_GRADED = "dst_no_graded_rows"
REASON_DST_UNSIGNED = "dst_outcome_unsigned_mfe_proxy"
REASON_NO_OVERLAP = "no_overlapping_outcome_window"
REASON_SRC_DIR_AMBIGUOUS = "src_direction_ambiguous"
REASON_CHF_PANEL_SUBJECT = "chf_panel_subject_graded_elsewhere"
REASON_SPINE_UNUSABLE = "spine_missing_required_columns"

REASON_CODES: tuple[str, ...] = (
    REASON_SPINE_ABSENT,
    REASON_SPINE_UNUSABLE,
    REASON_SRC_UNRESOLVED,
    REASON_DST_UNRESOLVED,
    REASON_CHF_PANEL_SUBJECT,
    REASON_SRC_NO_ROWS,
    REASON_DST_NO_GRADED,
    REASON_DST_UNSIGNED,
    REASON_NO_OVERLAP,
    REASON_SRC_DIR_AMBIGUOUS,
)

REASON_NOTES: dict[str, str] = {
    REASON_SPINE_ABSENT:
        "spine_index.parquet unavailable — the sole fire substrate is not readable",
    REASON_SPINE_UNUSABLE:
        "spine_index.parquet is readable but lacks a column this ledger requires; "
        "degraded rather than raised",
    REASON_SRC_UNRESOLVED:
        "edge src string does not resolve to a spine subject under the "
        "pre-registered resolver rules",
    REASON_DST_UNRESOLVED:
        "edge dst string does not resolve to a spine subject under the "
        "pre-registered resolver rules",
    REASON_SRC_NO_ROWS:
        "no fire for this src inside the requested window — either the subject has "
        "no spine rows at all, or none within the run's since/until bounds. On a "
        "bounded nightly sweep this usually means 'did not fire recently', NOT "
        "'never fired'",
    REASON_DST_NO_GRADED:
        "dst resolves to a spine subject with no graded outcome rows",
    REASON_DST_UNSIGNED:
        "dst outcomes come from an unsigned max-favorable-excursion proxy; "
        "direction agreement is undefined against it",
    REASON_NO_OVERLAP:
        "src fired but the dst has no graded outcome row inside the link window "
        "of any fire",
    REASON_SRC_DIR_AMBIGUOUS:
        "src direction is an exact tie at this fire; agreement is undefined",
    REASON_CHF_PANEL_SUBJECT:
        "endpoint is a causal-scout cause-feature or target-panel id "
        "(e.g. fed_net_liquidity -> regime_worsening_5d), not a spine subject. "
        "The CHF battery grades these edges itself in causal_edges.jsonl; "
        "re-grading them here would duplicate an existing measurement, so this "
        "ledger records the edge and defers",
}

#: Sector-node id -> spine symbol is the identity uppercase mapping, but the
#: macro lobe ids and the board lane ids are not.  Both alias tables are
#: explicit: an unlisted subject resolves to nothing rather than to a guess.
_MACRO_FAMILY_ALIASES: dict[str, str] = {
    "rates_transmission": "transmission",
}

_LANE_ALIASES: dict[str, tuple[str, str]] = {
    "us_board.buy_lane": ("us_board", "us_board:buy"),
    "us_board.watch_lane": ("us_board", "us_board:watch"),
    "us_board.laggard_lane": ("us_board", "us_board:laggards"),
}


# ---------------------------------------------------------------------------
# Data-root ladder
# ---------------------------------------------------------------------------

_PRIMARY_CHECKOUT_NW = Path(
    "/Users/chriswong/Documents/Cluade/Macro Dashboard/data/neuralweb"
)


def resolve_data_root(
    explicit: Path | str | None = None,
    *,
    repo_root: Path | None = None,
    env: dict[str, str] | None = None,
) -> tuple[Path | None, str]:
    """Resolve the ``data/neuralweb`` directory; return (path, provenance).

    Ladder (first hit wins), mirroring ``scripts/pick_forward_dist_phase0.py``:

        --data-root arg -> $MACRO_PRIMARY_DATA_NW -> <repo>/data/neuralweb
        -> the primary checkout's data/neuralweb (read-only)

    ``data/neuralweb`` is TRACKED in this repo (72 files, including
    ``spine_index.parquet`` and ``confluence_graph.json``), so the
    ``<repo>/data/neuralweb`` rung normally wins and a worktree reads the
    committed store.  The env and primary-checkout rungs exist for a checkout
    where those artifacts are absent or deliberately overridden.  Returns
    ``(None, ...)`` when no rung exists; callers degrade rather than raise.
    """
    environ = os.environ if env is None else env
    rungs: list[tuple[Path, str]] = []
    if explicit:
        rungs.append((Path(explicit), "--data-root"))
    env_dir = environ.get("MACRO_PRIMARY_DATA_NW")
    if env_dir:
        rungs.append((Path(env_dir), "$MACRO_PRIMARY_DATA_NW"))
    if repo_root is not None:
        rungs.append((Path(repo_root) / "data" / "neuralweb", "<repo>/data/neuralweb"))
    rungs.append((_PRIMARY_CHECKOUT_NW, "primary checkout"))

    for path, provenance in rungs:
        try:
            if path.is_dir():
                return path, provenance
        except OSError:  # pragma: no cover - defensive
            continue
    return None, "unresolved"


# ---------------------------------------------------------------------------
# Small deterministic helpers
# ---------------------------------------------------------------------------

def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sign(x: float | None) -> int | None:
    """Strict sign; exact 0.0 returns 0, None returns None."""
    if x is None:
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    if v != v:  # NaN
        return None
    if v > 0:
        return 1
    if v < 0:
        return -1
    return 0


def _median(values: Sequence[float]) -> float | None:
    vals = sorted(float(v) for v in values if v is not None and float(v) == float(v))
    n = len(vals)
    if n == 0:
        return None
    mid = n // 2
    if n % 2 == 1:
        return vals[mid]
    return (vals[mid - 1] + vals[mid]) / 2.0


def _stdev(values: Sequence[float]) -> float | None:
    vals = [float(v) for v in values if v is not None and float(v) == float(v)]
    n = len(vals)
    if n < 2:
        return None
    mean = sum(vals) / n
    var = sum((v - mean) ** 2 for v in vals) / (n - 1)
    return math.sqrt(var)


def wilson_interval(k: int, n: int, z: float = 1.96) -> tuple[float, float] | None:
    """Wilson score interval for k successes in n trials.

    Returns ``None`` when ``n <= 0``.  Deterministic, closed form, no fitting.

    The house has a one-sided sibling, ``engine/qledger.py::wilson_ci_low``
    (the promotion-gate lower bound).  This ledger needs the two-sided interval
    because it reports an agreement rate that can be wrong in either direction:
    a ``confirms`` edge whose target reliably moves the OTHER way is as much a
    finding as one that never moves at all, and a lower bound alone would hide
    it.  Same estimator, same z, both bounds kept.
    """
    if n <= 0:
        return None
    p = k / n
    denom = 1.0 + (z * z) / n
    centre = (p + (z * z) / (2 * n)) / denom
    half = (z * math.sqrt((p * (1 - p) + (z * z) / (4 * n)) / n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def _canonical_hash(payload: dict) -> str:
    """SHA1 over the row's content, excluding volatile/derived keys.

    ``produced_at`` and ``row_id`` are excluded so a re-run of the same content
    hashes identically — that is what makes the append idempotent.
    """
    body = {k: v for k, v in payload.items() if k not in ("produced_at", "row_id")}
    blob = json.dumps(body, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()  # noqa: S324 - not security


def make_edge_id(edge_type: str, src: str, dst: str) -> str:
    """Deterministic, human-readable-prefixed edge id."""
    raw = f"{edge_type}|{src}|{dst}"
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]  # noqa: S324
    return f"{edge_type}:{digest}"


# ---------------------------------------------------------------------------
# Subject resolution
# ---------------------------------------------------------------------------

class Subject:
    """A resolved spine subject: a filter over spine rows.

    ``kind`` is one of ``engine``, ``family``, ``symbol``.  ``label`` is the
    original edge string, kept so the ledger can always be read back to the
    graph.
    """

    __slots__ = ("kind", "engine", "family", "symbol", "label")

    def __init__(
        self,
        kind: str,
        label: str,
        *,
        engine: str | None = None,
        family: str | None = None,
        symbol: str | None = None,
    ) -> None:
        self.kind = kind
        self.label = label
        self.engine = engine
        self.family = family
        self.symbol = symbol

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "label": self.label,
            "engine": self.engine,
            "family": self.family,
            "symbol": self.symbol,
        }

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"Subject({self.kind}, {self.label!r})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Subject):
            return NotImplemented
        return self.as_dict() == other.as_dict()


def resolve_subject(raw: str) -> Subject | None:
    """Resolve an edge endpoint string to a spine subject, or ``None``.

    PRE-REGISTERED RULES (an endpoint matching none of them is unresolved; the
    resolver never guesses):

      ``engine:<name>``      -> engine == name
      ``sector:<id>``        -> symbol == ID.upper()  (GICS sector ETF ticker)
      ``macro:<lobe>``       -> engine == macro_context, family == alias(lobe)
      ``<board>.<lane>``     -> explicit lane alias table only
      anything else          -> None

    Deliberately unresolved, with the reason recorded rather than papered over:

      * ``complex:<id>`` oracle complexes have no spine key.
      * ``options.<condition>`` names a *condition* inside the options engine,
        not the engine.  Mapping it to the whole ``options_entry`` engine would
        silently grade a different object, so it stays unresolved.
      * artifact paths (``data/...json:field``, ``site/...json``) are files,
        not market subjects.
    """
    if not raw or not isinstance(raw, str):
        return None
    s = raw.strip()
    if not s:
        return None

    # Artifact paths are never subjects.
    if "/" in s or ".json" in s:
        return None

    if s.startswith("engine:"):
        name = s.split(":", 1)[1].strip()
        return Subject("engine", s, engine=name) if name else None

    if s.startswith("sector:"):
        sym = s.split(":", 1)[1].strip().upper()
        return Subject("symbol", s, symbol=sym) if sym else None

    if s.startswith("macro:"):
        lobe = s.split(":", 1)[1].strip()
        if not lobe:
            return None
        family = _MACRO_FAMILY_ALIASES.get(lobe, lobe)
        return Subject("family", s, engine="macro_context", family=family)

    if s.startswith("complex:"):
        return None

    if s in _LANE_ALIASES:
        engine, family = _LANE_ALIASES[s]
        return Subject("family", s, engine=engine, family=family)

    return None


# ---------------------------------------------------------------------------
# Edge inventory
# ---------------------------------------------------------------------------

def load_edge_inventory(nw_dir: Path | None, gaps: list[str]) -> list[dict]:
    """Read measured edges from the confluence graph + causal-scout candidates.

    Returns a list of inventory dicts::

        {"edge_id", "edge_type", "src", "dst", "source", "n", "lift", "note"}

    ``feeds``/``stable`` wiring edges are counted into ``gaps`` and dropped.
    Fail-open: an absent or corrupt source contributes zero edges and a note.
    """
    edges: list[dict] = []
    if nw_dir is None:
        gaps.append("edge inventory: data/neuralweb unresolved — zero edges")
        return edges

    # --- confluence graph -------------------------------------------------
    graph_path = nw_dir / "confluence_graph.json"
    n_wiring = 0
    if not graph_path.exists():
        gaps.append(
            "edge inventory: confluence_graph.json absent — "
            "no confluence edges (tracked artifact — check the data root, "
            "or run the nightly graph build)"
        )
    else:
        try:
            graph = json.loads(graph_path.read_text(encoding="utf-8"))
            for e in (graph.get("edges") or []):
                etype = str(e.get("edge_type") or "")
                if etype in WIRING_EDGE_TYPES:
                    n_wiring += 1
                    continue
                if etype not in MEASURED_EDGE_TYPES:
                    continue
                src = str(e.get("src") or "")
                dst = str(e.get("dst") or "")
                if not src or not dst:
                    continue
                edges.append({
                    "edge_id": make_edge_id(etype, src, dst),
                    "edge_type": etype,
                    "src": src,
                    "dst": dst,
                    "source": "confluence_graph",
                    "n": e.get("n"),
                    "lift": e.get("lift"),
                    "note": str(e.get("note") or "")[:400],
                })
            if n_wiring:
                gaps.append(
                    f"edge inventory: skipped {n_wiring} static wiring edges "
                    f"({'/'.join(sorted(WIRING_EDGE_TYPES))}) — "
                    "config/synapse.yml plumbing carries no directional market claim"
                )
        except Exception as exc:  # noqa: BLE001 - fail-open contract
            log.warning("edge_outcomes: confluence_graph unreadable — %s", exc)
            gaps.append(f"edge inventory: confluence_graph.json unreadable — {exc}")

    # --- causal-scout candidate edges -------------------------------------
    cand_path = nw_dir / "causal_edges.jsonl"
    if not cand_path.exists():
        gaps.append(
            "edge inventory: causal_edges.jsonl absent — "
            "no causal-scout candidate edges (build_causal_edges.py has not run here)"
        )
    else:
        n_cand = 0
        try:
            for line in cand_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                src = str(row.get("cause_feature_id") or row.get("cause_family") or "")
                dst = str(row.get("target_id") or row.get("target_family") or "")
                if not src or not dst:
                    continue
                eid = str(row.get("edge_id") or make_edge_id("leads", src, dst))
                edges.append({
                    "edge_id": eid,
                    "edge_type": "leads",
                    "src": src,
                    "dst": dst,
                    "source": "causal_edges",
                    "n": row.get("n"),
                    "lift": None,
                    "note": f"causal-scout candidate; status={row.get('status')}",
                })
                n_cand += 1
            if n_cand == 0:
                gaps.append("edge inventory: causal_edges.jsonl present but empty")
        except Exception as exc:  # noqa: BLE001 - fail-open contract
            log.warning("edge_outcomes: causal_edges unreadable — %s", exc)
            gaps.append(f"edge inventory: causal_edges.jsonl unreadable — {exc}")

    # Deterministic order, deduped on edge_id (keep-first).
    seen: set[str] = set()
    out: list[dict] = []
    for e in sorted(edges, key=lambda r: (r["edge_type"], r["src"], r["dst"])):
        if e["edge_id"] in seen:
            continue
        seen.add(e["edge_id"])
        out.append(e)
    return out


# ---------------------------------------------------------------------------
# Spine access
# ---------------------------------------------------------------------------

class SpineView:
    """A read-only view over ``spine_index.parquet``.

    Holds the session grid and per-subject slices.  Never writes, never
    recomputes an outcome — it only selects rows the spine already graded.
    """

    def __init__(self, df: Any) -> None:
        self._df = df
        self.sessions: list[str] = sorted(
            {str(v) for v in df["as_of"].dropna().unique().tolist()}
        )
        self._session_ix: dict[str, int] = {d: i for i, d in enumerate(self.sessions)}

    # -- selection ------------------------------------------------------
    def rows_for(self, subject: Subject) -> Any:
        """Slice the spine for a subject; an absent column degrades to empty."""
        df = self._df
        try:
            if subject.kind == "engine":
                return df[df["engine"] == subject.engine]
            if subject.kind == "family":
                mask = df["family"] == subject.family
                if subject.engine:
                    mask = mask & (df["engine"] == subject.engine)
                return df[mask]
            if subject.kind == "symbol":
                return df[df["symbol"] == subject.symbol]
        except (KeyError, TypeError, AttributeError) as exc:  # noqa: BLE001
            log.warning("edge_outcomes: subject slice failed for %r — %s", subject, exc)
        return df.iloc[0:0]

    def session_index(self, date: str) -> int | None:
        return self._session_ix.get(date)

    def window_dates(self, date: str, n_sessions: int) -> list[str]:
        """Sessions in ``[date, date + n_sessions]`` on the spine's own grid."""
        i = self._session_ix.get(date)
        if i is None:
            return []
        return self.sessions[i: i + n_sessions + 1]


def load_spine(nw_dir: Path | None, gaps: list[str]) -> tuple[SpineView | None, str | None]:
    """Load the spine fail-open.  Returns ``(spine, reason_code)``.

    ``reason_code`` is the ungradeable code to stamp when the spine could not
    be used, so a structurally-wrong spine is distinguishable from a missing
    one instead of both reading as "absent".
    """
    if nw_dir is None:
        gaps.append("spine: data/neuralweb unresolved — no fire substrate")
        return None, REASON_SPINE_ABSENT
    path = nw_dir / "spine_index.parquet"
    if not path.exists():
        gaps.append(
            "spine: spine_index.parquet absent — no fire substrate "
            "(ledger degrades to zero rows)"
        )
        return None, REASON_SPINE_ABSENT
    try:
        import pandas as pd  # local import: keeps module importable without pandas
        df = pd.read_parquet(path)
    except Exception as exc:  # noqa: BLE001 - fail-open contract
        log.warning("edge_outcomes: spine unreadable — %s", exc)
        gaps.append(f"spine: spine_index.parquet unreadable — {exc}")
        return None, REASON_SPINE_ABSENT
    missing = missing_spine_columns(df)
    if missing:
        gaps.append(
            f"spine: readable but missing required column(s) {sorted(missing)} — "
            "cannot grade edges against it"
        )
        return None, REASON_SPINE_UNUSABLE
    try:
        return SpineView(df), None
    except Exception as exc:  # noqa: BLE001 - fail-open contract
        log.warning("edge_outcomes: spine view failed — %s", exc)
        gaps.append(f"spine: could not build session grid — {exc}")
        return None, REASON_SPINE_UNUSABLE


# ---------------------------------------------------------------------------
# Unsigned-outcome detection (fail-closed; see module docstring)
# ---------------------------------------------------------------------------

#: Spine columns this module cannot work without.
REQUIRED_SPINE_COLUMNS: tuple[str, ...] = (
    "engine", "family", "symbol", "ledger", "as_of", "direction",
    "horizon", "outcome_excess", "outcome_graded",
)


def missing_spine_columns(df: Any) -> list[str]:
    """Which required columns this spine lacks.  Empty list = usable."""
    try:
        cols = set(df.columns)
    except Exception:  # noqa: BLE001 - defensive
        return list(REQUIRED_SPINE_COLUMNS)
    return [c for c in REQUIRED_SPINE_COLUMNS if c not in cols]


def _graded_rows(rows: Any) -> Any:
    """Graded rows with a usable outcome_excess.

    Guarded: a spine that reads but lacks a required column degrades to an
    empty slice, which surfaces as a reason code upstream.  The fail-open
    contract covers a spine that is *unreadable*; a spine that is readable but
    structurally wrong used to raise straight out of build_rows, which is the
    one shape the contract promised not to have.
    """
    try:
        return rows[(rows["outcome_graded"] == True) & (rows["outcome_excess"].notna())]  # noqa: E712
    except (KeyError, TypeError, AttributeError) as exc:  # noqa: BLE001
        log.warning("edge_outcomes: graded-row selection failed — %s", exc)
        try:
            return rows.iloc[0:0]
        except Exception:  # noqa: BLE001 - defensive
            return []


def is_unsigned_outcome(graded: Any) -> tuple[bool, str | None]:
    """Is this cohort's ``outcome_excess`` an unsigned MFE proxy?

    Returns ``(unsigned, basis)``.  Two independent checks:

      * structural — the cohort's ``ledger`` is in ``UNSIGNED_OUTCOME_LEDGERS``
        (``query.py`` assigns ``outcome_excess = fwd_mfe_H`` for it);
      * empirical — >= ``UNSIGNED_PROBE_MIN_N`` graded outcomes and not one
        negative value, which catches a ledger that acquires the defect later.

    Fail-closed: either check firing marks the cohort unsigned.
    """
    if graded is None or len(graded) == 0:
        return False, None
    try:
        ledgers = {str(v) for v in graded["ledger"].dropna().unique().tolist()}
    except Exception:  # noqa: BLE001 - defensive
        ledgers = set()
    hit = ledgers & set(UNSIGNED_OUTCOME_LEDGERS)
    if hit:
        return True, f"structural:ledger={'/'.join(sorted(hit))}"
    n = len(graded)
    if n >= UNSIGNED_PROBE_MIN_N:
        try:
            n_neg = int((graded["outcome_excess"] < 0).sum())
        except Exception:  # noqa: BLE001 - defensive
            n_neg = -1
        if n_neg == 0:
            return True, f"empirical:zero_negative_of_{n}"
    return False, None


# ---------------------------------------------------------------------------
# Fire detection
# ---------------------------------------------------------------------------

def _fires_from_spine(
    spine: SpineView,
    subject: Subject,
    *,
    since: str | None = None,
    until: str | None = None,
) -> list[dict]:
    """PRIMARY fire definition — one fire per session the src subject emitted."""
    rows = spine.rows_for(subject)
    if len(rows) == 0:
        return []
    if since is not None:
        rows = rows[rows["as_of"] >= since]
    if until is not None:
        rows = rows[rows["as_of"] <= until]
    if len(rows) == 0:
        return []

    fires: list[dict] = []
    for as_of, grp in rows.groupby("as_of", sort=True):
        dirs = [int(d) for d in grp["direction"].dropna().tolist()]
        n_pos = sum(1 for d in dirs if d > 0)
        n_neg = sum(1 for d in dirs if d < 0)
        if n_pos > n_neg:
            direction = 1
        elif n_neg > n_pos:
            direction = -1
        else:
            direction = 0
        symbols = sorted({str(s) for s in grp["symbol"].dropna().unique().tolist()})
        fires.append({
            "fire_date": str(as_of),
            # Session-grid position, carried so the aggregator can count
            # non-overlapping outcome windows without re-opening the spine.
            "fire_session_ix": spine.session_index(str(as_of)),
            "src_direction": direction,
            "src_n_rows": int(len(grp)),
            "src_n_symbols": len(symbols),
            "src_symbols": symbols[:25],
            "src_direction_degenerate": len(set(dirs)) <= 1 and len(dirs) > 0,
        })
    return fires


def _load_tape(nw_dir: Path | None, gaps: list[str]) -> list[dict] | None:
    if nw_dir is None:
        return None
    path = nw_dir / "confluence_tape.jsonl"
    if not path.exists():
        gaps.append(
            "fire variant: confluence_tape.jsonl absent — the tape_transition "
            "fire definition is unavailable in this checkout; primary "
            "spine_asof definition used"
        )
        return None
    rows: list[dict] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    except Exception as exc:  # noqa: BLE001 - fail-open contract
        gaps.append(f"fire variant: confluence_tape.jsonl unreadable — {exc}")
        return None
    return rows


def _fires_from_tape(
    spine: "SpineView",
    tape: list[dict],
    subject: Subject,
    *,
    since: str | None = None,
    until: str | None = None,
) -> list[dict]:
    """VARIANT fire definition — tape transitions to ``new``/``strengthening``.

    ``new`` = the subject's first ever tape session.  ``strengthening`` =
    ``n_independent_confirming`` strictly above the subject's previous session.
    Both are re-derived here from the tape's own columns rather than importing
    the sequence organ, so the variant carries no dependency on a nightly
    artifact that may not exist.
    """
    label = subject.label
    key = label.split(":", 1)[1] if ":" in label else label
    mine = [
        r for r in tape
        if str(r.get("subject") or "") in (label, key)
    ]
    if not mine:
        return []
    mine.sort(key=lambda r: str(r.get("as_of") or ""))

    fires: list[dict] = []
    prev_strength: float | None = None
    for i, r in enumerate(mine):
        as_of = str(r.get("as_of") or "")
        if not as_of:
            continue
        strength = r.get("n_independent_confirming")
        try:
            strength_f = float(strength) if strength is not None else None
        except (TypeError, ValueError):
            strength_f = None

        if i == 0:
            state = "new"
        elif (
            strength_f is not None
            and prev_strength is not None
            and strength_f > prev_strength
        ):
            state = "strengthening"
        else:
            state = "other"
        prev_strength = strength_f if strength_f is not None else prev_strength

        if state not in ("new", "strengthening"):
            continue
        if since is not None and as_of < since:
            continue
        if until is not None and as_of > until:
            continue
        try:
            direction = int(r.get("direction") or 0)
        except (TypeError, ValueError):
            direction = 0
        fires.append({
            "fire_date": as_of,
            # Same session-grid position the spine path carries.  Without it
            # the independence counter and the matched base rate silently see
            # an empty span for every tape fire.
            "fire_session_ix": spine.session_index(as_of),
            "src_direction": 1 if direction > 0 else (-1 if direction < 0 else 0),
            "src_n_rows": 1,
            "src_n_symbols": 1,
            "src_symbols": [key],
            "src_direction_degenerate": False,
            "tape_state": state,
        })
    return fires


# ---------------------------------------------------------------------------
# Agreement semantics
# ---------------------------------------------------------------------------

def claimed_sign(edge_type: str, src_direction: int | None) -> int | None:
    """The direction the EDGE claims the dst will move.  See module docstring."""
    if edge_type == "headwind":
        return -1
    if edge_type == "tailwind":
        return 1
    if src_direction is None or src_direction == 0:
        return None
    if edge_type in ("confirms", "leads"):
        return 1 if src_direction > 0 else -1
    if edge_type == "contradicts":
        return -1 if src_direction > 0 else 1
    return None


# ---------------------------------------------------------------------------
# Lag estimator
# ---------------------------------------------------------------------------

def matched_base_up_rate(
    spine: "SpineView",
    dst_graded: Any,
    span_ixs: Sequence[int],
    horizon: int = PRIMARY_HORIZON,
) -> tuple[float | None, int]:
    """The dst's up-rate under the SAME estimator, window and span as the numerator.

    The numerator this control is compared against is: pooled median of the
    dst's ``outcome_excess`` at ``horizon`` over rows whose ``as_of`` falls in
    ``[t, t+LINK_WINDOW_SESSIONS]``, evaluated at fire dates.  So the base must
    be the pooled median over ``[s, s+LINK_WINDOW_SESSIONS]`` evaluated at
    EVERY grid session ``s`` inside the fires' own span — same estimator, same
    window width, same stretch of calendar.

    An earlier cut of this function got all three wrong: it took a per-session
    median (no link window) over the dst's ENTIRE history (no span match).  On
    the first retro that reported ``altdata -> radar`` at base 0.200 and lift
    +0.078; the matched base is 0.241 and the true lift is +0.037 — about half.
    On a constructed fixture the unmatched window turns a true 0.000 lift into
    -0.667.  A base rate that does not match its numerator is not a control, it
    is a second uncontrolled statistic.

    Returns ``(up_rate, n_sessions, evaluated_ixs)`` where ``n_sessions``
    counts only grid sessions that yielded a median at all, and
    ``evaluated_ixs`` are those sessions — kept so callers can report how much
    the control overlaps the fires it is controlling for.
    """
    if dst_graded is None or len(dst_graded) == 0 or not span_ixs:
        return None, 0, set()
    try:
        at_h = dst_graded[dst_graded["horizon"] == float(horizon)]
    except Exception:  # noqa: BLE001 - defensive
        return None, 0, set()
    if len(at_h) == 0:
        return None, 0, set()

    lo, hi = min(span_ixs), max(span_ixs)
    n_up = 0
    n_sessions = 0
    evaluated: set[int] = set()
    for ix in range(lo, hi + 1):
        if ix < 0 or ix >= len(spine.sessions):
            continue
        window = spine.sessions[ix: ix + LINK_WINDOW_SESSIONS + 1]
        if not window:
            continue
        try:
            vals = [
                float(v) for v in
                at_h[at_h["as_of"].isin(window)]["outcome_excess"].dropna().tolist()
            ]
        except Exception:  # noqa: BLE001 - defensive
            continue
        med = _median(vals)
        if med is None:
            continue
        n_sessions += 1
        evaluated.add(ix)
        if med > 0:
            n_up += 1
    if n_sessions == 0:
        return None, 0, set()
    return n_up / n_sessions, n_sessions, evaluated


def make_base_provider(spine: "SpineView"):
    """Build the aggregation-time base-rate provider.

    The base depends on the fires' span, and that span GROWS as the ledger
    accrues, so a value stamped at write time goes stale the moment another
    fire lands.  Aggregation therefore recomputes it from the spine rather than
    reading it off the first row it happens to see.
    """
    cache: dict[str, Any] = {}

    def provider(dst_subject: dict | None, span_ixs: Sequence[int]):
        if not dst_subject or not span_ixs:
            return None, 0, set()
        key = json.dumps(dst_subject, sort_keys=True, default=str)
        if key not in cache:
            subj = Subject(
                str(dst_subject.get("kind") or ""),
                str(dst_subject.get("label") or ""),
                engine=dst_subject.get("engine"),
                family=dst_subject.get("family"),
                symbol=dst_subject.get("symbol"),
            )
            cache[key] = _graded_rows(spine.rows_for(subj))
        return matched_base_up_rate(spine, cache[key], span_ixs)

    return provider


def estimate_lag(
    dst_graded: Any,
    fire_date: str,
    outcomes: dict[int, dict],
) -> tuple[int | None, str | None]:
    """Smallest horizon at which the dst move clears 1 sigma of its own history.

    ``sigma_H`` is the standard deviation of the dst subject's own graded
    ``outcome_excess`` at horizon H over rows whose ``as_of`` is strictly before
    ``fire_date``.

    Be precise about what that does and does not buy.  The rows are selected by
    a pre-fire ``as_of``, but each carries a FORWARD outcome that resolves
    *after* its own as_of — so for a row dated a few sessions before the fire,
    the outcome window overlaps the fire.  This is trailing-by-selection, not
    strictly point-in-time, and it is not a clean "no peeking" guarantee.  The
    estimate is report-only and feeds no rate, no rank and no gate, which is
    what makes the looseness tolerable; a promotion-tier use would need a
    graded_at-based cutoff instead.

    Below ``MIN_N_LAG`` trailing observations the lag is null and the reason is
    printed.  See also the disclosed resolution deviation in the module
    docstring.
    """
    if dst_graded is None or len(dst_graded) == 0:
        return None, "no_dst_history"
    trailing = dst_graded[dst_graded["as_of"] < fire_date]
    if len(trailing) == 0:
        return None, "no_trailing_history_before_fire"

    checked_any = False
    for h in LAG_HORIZONS:
        obs = outcomes.get(h) or {}
        val = obs.get("dst_outcome")
        if val is None:
            continue
        at_h = trailing[trailing["horizon"] == float(h)]
        vals = [float(v) for v in at_h["outcome_excess"].dropna().tolist()]
        if len(vals) < MIN_N_LAG:
            continue
        checked_any = True
        sigma = _stdev(vals)
        if sigma is None or sigma <= 0:
            continue
        if abs(float(val)) >= LAG_SIGMA_K * sigma:
            return int(h), None
    if not checked_any:
        return None, "trailing_dispersion_below_floor"
    return None, "no_horizon_crossed_1sigma"


# ---------------------------------------------------------------------------
# Row construction
# ---------------------------------------------------------------------------

def _blank_outcomes() -> dict[str, dict]:
    return {
        str(h): {"dst_outcome": None, "n_dst_rows": 0, "agree": None}
        for h in OUTCOME_HORIZONS
    }


def _make_row(
    edge: dict,
    fire: dict,
    *,
    fire_def: str,
    src_subject: Subject | None,
    dst_subject: Subject | None,
    outcomes: dict[str, dict],
    graded: bool,
    ungradeable_reason: str | None,
    realized_lag: int | None,
    lag_reason: str | None,
    claimed: int | None,
    base_rate: float | None = None,
    base_rate_n: int = 0,
    latest_session_ix: int | None = None,
) -> dict:
    row: dict[str, Any] = {
        "schema": SCHEMA,
        "edge_id": edge["edge_id"],
        "edge_type": edge["edge_type"],
        "src": edge["src"],
        "dst": edge["dst"],
        "edge_source": edge.get("source"),
        "src_subject": src_subject.as_dict() if src_subject else None,
        "dst_subject": dst_subject.as_dict() if dst_subject else None,
        "fire_date": fire["fire_date"],
        "fire_def": fire_def,
        "src_direction": fire.get("src_direction"),
        "src_n_rows": fire.get("src_n_rows"),
        "src_n_symbols": fire.get("src_n_symbols"),
        "src_symbols": fire.get("src_symbols"),
        "src_direction_degenerate": fire.get("src_direction_degenerate"),
        "fire_session_ix": fire.get("fire_session_ix"),
        # Can this verdict still change?  window_settled is the gate the
        # scoreboard uses; primary_window_settled is disclosed alongside it
        # because the H=21 verdict stops moving 42 sessions earlier than the
        # H=63 column does.
        "window_settled": is_window_settled(
            fire.get("fire_session_ix"), latest_session_ix),
        "primary_window_settled": is_window_settled(
            fire.get("fire_session_ix"), latest_session_ix,
            PRIMARY_SETTLE_OFFSET_SESSIONS),
        "settle_offset_sessions": SETTLE_OFFSET_SESSIONS,
        "latest_session_ix_at_build": latest_session_ix,
        "claimed_sign": claimed,
        # Unconditional base rate for the dst — the control the agreement rate
        # must be read against.  See dst_up_rate().
        "dst_up_rate_primary": base_rate,
        "dst_up_rate_n_sessions": base_rate_n,
        "primary_horizon": PRIMARY_HORIZON,
        "outcomes": outcomes,
        "graded": graded,
        "ungradeable_reason": ungradeable_reason,
        "realized_lag_sessions": realized_lag,
        "lag_basis": "horizon_grid",
        "lag_resolution_sessions": list(LAG_HORIZONS),
        "lag_reason": lag_reason,
        "row_kind": "fire",
        # Authority — stamped on EVERY row, graded or not.
        "authority": dict(AUTHORITY_BLOCK),
        "display_only": True,
        "tier": "display",
        "produced_by": PRODUCED_BY,
    }
    # Explicit ledger key.  A fire row is keyed by its date; the per-edge stub
    # and summary rows carry no fire date, so they get their own stable keys —
    # without this, every dateless row for an edge would collide on
    # (edge_id, None) and later runs would silently drop their tallies.
    fd = fire.get("fire_date")
    row["ledger_key"] = f"{edge['edge_id']}|{fd}" if fd else f"{edge['edge_id']}|stub"
    row["row_id"] = _canonical_hash(row)
    row["produced_at"] = _utc_now()
    return row


def build_rows(
    nw_dir: Path | None,
    *,
    fire_def: str = FIRE_DEF_SPINE,
    since: str | None = None,
    until: str | None = None,
    gaps: list[str] | None = None,
) -> tuple[list[dict], list[str], dict]:
    """Build ledger rows for every measured edge.  Returns (rows, gaps, meta).

    One row per (edge, fire).  An edge that cannot be graded at all still emits
    a single row carrying its reason code — the coverage disclosure IS a
    deliverable, so an ungradeable edge is recorded, never dropped.
    """
    gaps = [] if gaps is None else gaps
    if fire_def not in VALID_FIRE_DEFS:
        raise ValueError(f"unknown fire_def {fire_def!r}; expected one of {sorted(VALID_FIRE_DEFS)}")

    inventory = load_edge_inventory(nw_dir, gaps)
    spine, spine_reason = load_spine(nw_dir, gaps)
    tape = _load_tape(nw_dir, gaps) if fire_def == FIRE_DEF_TAPE else None

    meta: dict[str, Any] = {
        "n_edges_inventoried": len(inventory),
        "fire_def": fire_def,
        "spine_available": spine is not None,
        "spine_reason": spine_reason,
        "reason_counts": {},
    }

    # The newest session the spine knows about — the reference point for
    # deciding whether a fire's outcome window can still change.
    latest_ix = (len(spine.sessions) - 1) if spine is not None else None

    rows: list[dict] = []
    reason_counts: dict[str, int] = {}

    def _bump(code: str) -> None:
        reason_counts[code] = reason_counts.get(code, 0) + 1

    for edge in inventory:
        etype = edge["edge_type"]
        src_subject = resolve_subject(edge["src"])
        dst_subject = resolve_subject(edge["dst"])
        stub_fire = {
            "fire_date": None,
            "src_direction": None,
            "src_n_rows": 0,
            "src_n_symbols": 0,
            "src_symbols": [],
            "src_direction_degenerate": None,
        }

        def _ungradeable(reason: str, fire: dict | None = None, _edge=edge) -> None:
            _bump(reason)
            r = _make_row(
                edge, fire or stub_fire,
                fire_def=fire_def,
                src_subject=src_subject,
                dst_subject=dst_subject,
                outcomes=_blank_outcomes(),
                graded=False,
                ungradeable_reason=reason,
                realized_lag=None,
                lag_reason=None,
                claimed=None,
                latest_session_ix=latest_ix,
            )
            # SF-7: key stub rows by their REASON, not just "stub".  A single
            # degraded night (spine unreadable) would otherwise write a
            # spine_absent stub whose key permanently blocks the real reason
            # from ever being recorded for that edge.
            r["ledger_key"] = f"{_edge['edge_id']}|stub|{reason}"
            r["row_kind"] = "edge_stub"
            r["row_id"] = _canonical_hash(r)
            rows.append(r)

        if spine is None:
            _ungradeable(spine_reason or REASON_SPINE_ABSENT)
            continue
        # A causal-scout candidate names CHF panel ids, not spine subjects.
        # Say so precisely instead of filing it under generic "unresolved".
        chf_candidate = edge.get("source") == "causal_edges"
        if src_subject is None:
            _ungradeable(REASON_CHF_PANEL_SUBJECT if chf_candidate else REASON_SRC_UNRESOLVED)
            continue
        if dst_subject is None:
            _ungradeable(REASON_CHF_PANEL_SUBJECT if chf_candidate else REASON_DST_UNRESOLVED)
            continue

        # -- dst gradeability, decided once per edge ----------------------
        dst_rows = spine.rows_for(dst_subject)
        dst_graded = _graded_rows(dst_rows)
        if len(dst_graded) == 0:
            _ungradeable(REASON_DST_NO_GRADED)
            continue
        unsigned, basis = is_unsigned_outcome(dst_graded)
        if unsigned:
            _bump(REASON_DST_UNSIGNED)
            r = _make_row(
                edge, stub_fire,
                fire_def=fire_def,
                src_subject=src_subject,
                dst_subject=dst_subject,
                outcomes=_blank_outcomes(),
                graded=False,
                ungradeable_reason=REASON_DST_UNSIGNED,
                realized_lag=None,
                lag_reason=None,
                claimed=None,
                latest_session_ix=latest_ix,
            )
            r["unsigned_basis"] = basis
            r["ledger_key"] = f"{edge['edge_id']}|stub|{REASON_DST_UNSIGNED}"
            r["row_kind"] = "edge_stub"
            r["row_id"] = _canonical_hash(r)
            rows.append(r)
            continue

        # -- fires --------------------------------------------------------
        if fire_def == FIRE_DEF_TAPE:
            fires = _fires_from_tape(spine, tape or [], src_subject, since=since, until=until)
        else:
            fires = _fires_from_spine(spine, src_subject, since=since, until=until)
        if not fires:
            _ungradeable(REASON_SRC_NO_ROWS)
            continue

        # -- control, over THIS edge's own fire span ------------------------
        # Computed after the fires so the span matches, and with the same
        # pooled-median estimator the numerator uses.  Aggregation recomputes
        # this whenever a spine is available — the stamped value is only the
        # fallback for a spine-less read, and is span-limited by construction.
        span_ixs = [f["fire_session_ix"] for f in fires if f.get("fire_session_ix") is not None]
        base_rate, base_rate_n, _ = matched_base_up_rate(spine, dst_graded, span_ixs)

        # BOUNDING (retro is "bounded" by charter): a fire whose link window
        # contains no graded dst row at any horizon carries no information
        # beyond its own existence — and on a long-history src like
        # track_record (12,979 sessions back to 1962) against a dst graded over
        # a handful of recent sessions, those fires outnumber the informative
        # ones ~1000:1.  They are COUNTED, not dropped: the per-edge summary row
        # below carries the exact tally under REASON_NO_OVERLAP, so coverage
        # arithmetic is unchanged while the ledger stays readable.
        n_no_overlap = 0
        edge_rows: list[dict] = []
        for fire in fires:
            t = fire["fire_date"]
            window = spine.window_dates(t, LINK_WINDOW_SESSIONS)
            if not window:
                # fire date is not on the spine session grid (tape variant)
                window = [t]
            cand = dst_graded[dst_graded["as_of"].isin(window)]
            outcomes = _blank_outcomes()
            claimed = claimed_sign(etype, fire.get("src_direction"))
            any_outcome = False
            for h in OUTCOME_HORIZONS:
                at_h = cand[cand["horizon"] == float(h)]
                vals = [float(v) for v in at_h["outcome_excess"].dropna().tolist()]
                med = _median(vals)
                agree: bool | None = None
                if med is not None and claimed is not None:
                    s = _sign(med)
                    agree = (s == claimed) if s not in (None, 0) else None
                obs = {
                    "dst_outcome": med,
                    "n_dst_rows": len(vals),
                    "agree": agree,
                }
                if h == PRIMARY_HORIZON:
                    # Which dst SESSIONS this verdict actually rests on.  Row
                    # count is not evidence count: six fires can all read the
                    # same single dst session through overlapping windows, and
                    # then n_graded=6 is really n=1.
                    try:
                        obs["dst_sessions"] = sorted(
                            {str(v) for v in at_h["as_of"].dropna().unique().tolist()}
                        )
                    except Exception:  # noqa: BLE001 - defensive
                        obs["dst_sessions"] = []
                outcomes[str(h)] = obs
                if med is not None:
                    any_outcome = True

            if not any_outcome:
                # Counted in the per-edge summary row, not emitted individually.
                n_no_overlap += 1
                _bump(REASON_NO_OVERLAP)
                continue
            if claimed is None:
                reason: str | None = REASON_SRC_DIR_AMBIGUOUS
                graded_flag = False
                lag, lag_reason = None, None
            else:
                reason = None
                graded_flag = True
                lag, lag_reason = estimate_lag(
                    dst_graded, t,
                    {h: outcomes[str(h)] for h in OUTCOME_HORIZONS},
                )
            if reason:
                _bump(reason)
            edge_rows.append(_make_row(
                edge, fire,
                fire_def=fire_def,
                src_subject=src_subject,
                dst_subject=dst_subject,
                outcomes=outcomes,
                graded=graded_flag,
                ungradeable_reason=reason,
                realized_lag=lag,
                lag_reason=lag_reason,
                claimed=claimed,
                base_rate=base_rate,
                base_rate_n=base_rate_n,
                latest_session_ix=latest_ix,
            ))

        # Per-edge summary row for the bounded-away fires.  Emitted whenever
        # any fire missed, so the tally is always on the record.
        if n_no_overlap:
            summary = _make_row(
                edge, dict(stub_fire),
                fire_def=fire_def,
                src_subject=src_subject,
                dst_subject=dst_subject,
                outcomes=_blank_outcomes(),
                graded=False,
                ungradeable_reason=REASON_NO_OVERLAP,
                realized_lag=None,
                lag_reason=None,
                claimed=None,
                base_rate=base_rate,
                base_rate_n=base_rate_n,
                latest_session_ix=latest_ix,
            )
            fire_dates = sorted(f["fire_date"] for f in fires if f.get("fire_date"))
            span = f"{fire_dates[0]}..{fire_dates[-1]}" if fire_dates else "none"
            summary["row_kind"] = "edge_summary"
            summary["n_fires_no_overlap"] = n_no_overlap
            summary["n_fires_total"] = len(fires)
            summary["fire_span"] = span
            # STABLE identity per edge — deliberately NOT span-keyed.
            #
            # Span-keying inflated the prospective fire count 17x (1,518 vs a
            # true 90): the nightly lookback re-mints a summary every night,
            # each night's sweep covers a slightly different span, so every one
            # minted a fresh key and the aggregator summed all of them.  With a
            # stable key the ledger keeps one summary per edge and
            # resolve_ledger takes the newest — latest wins, nothing sums.
            summary["ledger_key"] = f"{edge['edge_id']}|summary"
            summary["row_id"] = _canonical_hash(summary)
            edge_rows.append(summary)

        rows.extend(edge_rows)

    meta["reason_counts"] = dict(sorted(reason_counts.items()))
    meta["n_rows"] = len(rows)
    meta["n_graded_rows"] = sum(1 for r in rows if r.get("graded"))
    return rows, gaps, meta


# ---------------------------------------------------------------------------
# Single-writer append (idempotent)
# ---------------------------------------------------------------------------

def read_ledger(path: Path) -> list[dict]:
    """Read a ledger file fail-open.  Missing file -> []."""
    if not path.exists():
        return []
    out: list[dict] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    except OSError as exc:  # pragma: no cover - defensive
        log.warning("edge_outcomes: ledger unreadable — %s", exc)
    return out


def _ledger_key(row: dict) -> str:
    """The row's dedup key.  Falls back for rows written before the key existed."""
    key = row.get("ledger_key")
    if key:
        return str(key)
    return f"{row.get('edge_id')}|{row.get('fire_date') or 'stub'}"


#: Monotonic observation states.  A row may only ever move UP this ladder.
STATE_STUB = 0             # no outcome data at all (bounded away, unresolved, absent)
STATE_PARTIAL = 1          # some horizon has an outcome, no primary-horizon verdict
STATE_GRADED_PARTIAL = 2   # primary verdict, but the link window is still filling
STATE_GRADED_SETTLED = 3   # primary verdict on a fully closed link window

#: Back-compat alias.  Prefer the explicit rungs.
STATE_GRADED = STATE_GRADED_PARTIAL

#: Sessions after a fire before its link window can no longer gain a row that
#: changes any graded horizon: the window itself (LINK_WINDOW_SESSIONS) plus the
#: longest horizon those rows are graded at.
SETTLE_OFFSET_SESSIONS: int = LINK_WINDOW_SESSIONS + max(OUTCOME_HORIZONS)

#: The same offset for the PRIMARY horizon only — when the H=21 verdict (the one
#: the agreement rate is computed on) stops moving.  Disclosed, not used as the
#: gate; SETTLE_OFFSET_SESSIONS is the gate.
PRIMARY_SETTLE_OFFSET_SESSIONS: int = LINK_WINDOW_SESSIONS + PRIMARY_HORIZON


def is_window_settled(fire_session_ix: int | None, latest_session_ix: int | None,
                      offset: int = SETTLE_OFFSET_SESSIONS) -> bool:
    """Can this fire's outcome window still change?

    A fire at t draws its outcomes from dst rows in ``[t, t+LINK_WINDOW]``, and
    each of those rows is itself graded forward.  So the verdict is only final
    once ``t + LINK_WINDOW + max(horizon)`` is in the past.
    """
    if fire_session_ix is None or latest_session_ix is None:
        return False
    return (int(fire_session_ix) + offset) <= int(latest_session_ix)


def observation_state(row: dict) -> int:
    """Where this row sits on the accruing -> settled ladder.

    THE PARTIAL-WINDOW TRAP (do not collapse these two rungs):

    A fire's H=21 verdict becomes computable as soon as the dst row at session
    t settles — 21 sessions later.  But the link window ``[t, t+5]`` keeps
    ACQUIRING rows until t+26, and each new row moves the pooled median.  So an
    early verdict is a median over one dst row where the final verdict is a
    median over six.  Measured on a 90-night simulation: 69 fires graded
    prospectively, and 34 of them (49%) carried the OPPOSITE verdict from the
    retro over the identical settled store — agreement 0.507 against 1.000.

    A two-rung ladder (stub -> graded) froze that early wrong answer forever,
    because the dedup skips any row whose state is not strictly higher.  The
    fix is a rung for "graded, but the window is still filling", so the fuller
    re-grade can still supersede it.
    """
    if row.get("graded"):
        return STATE_GRADED_SETTLED if row.get("window_settled") else STATE_GRADED_PARTIAL
    outcomes = row.get("outcomes") or {}
    for obs in outcomes.values():
        if isinstance(obs, dict) and obs.get("dst_outcome") is not None:
            return STATE_PARTIAL
    return STATE_STUB


def resolve_ledger(rows: Sequence[dict]) -> list[dict]:
    """Collapse an append-only ledger to one row per key: the settled one.

    The file keeps the whole history (a stub AND the graded row that later
    superseded it) so the accrual is auditable.  Every reader — aggregation,
    coverage — must resolve through this, or a superseded stub would be counted
    a second time alongside the row that replaced it.

    Ties on state are broken by ``produced_at``, latest wins.
    """
    best: dict[str, dict] = {}
    for r in rows:
        key = _ledger_key(r)
        cur = best.get(key)
        if cur is None:
            best[key] = r
            continue
        new_rank, cur_rank = observation_state(r), observation_state(cur)
        if new_rank > cur_rank:
            best[key] = r
        elif new_rank == cur_rank and (
            str(r.get("produced_at") or "") >= str(cur.get("produced_at") or "")
        ):
            # NOTE the >=.  produced_at has second resolution, so several runs
            # inside the same second carry identical timestamps; a strict > then
            # keeps the FIRST row and "latest wins" silently becomes "first
            # wins".  This is invisible in production (nightly runs are a day
            # apart) and immediate in a simulation loop — it made a 25-night
            # fire tally read 9 instead of 27.  Rows arrive in file order, so on
            # a tie the later-encountered row is the later write.
            best[key] = r
    return list(best.values())


def append_rows(path: Path, rows: Iterable[dict]) -> dict:
    """Append to the PROSPECTIVE ledger with monotonic supersede semantics.

    Three outcomes per candidate row:

      * identical content already on file (``row_id``)      -> skip;
      * key on file at an EQUAL OR HIGHER observation state -> skip;
      * key on file at a LOWER state (stub -> partial -> graded) -> append,
        superseding the earlier row.

    The upgrade direction is one-way.  A settled grading may replace a stub; a
    stub may never replace a grading, so a night whose spine read degrades
    cannot un-grade history.  The superseded row stays in the file — the
    accrual is auditable — and ``resolve_ledger`` is what readers use to see
    only the settled view.

    Without this, the prospective lane could never record a graded fire at all:
    a fire is written before its outcomes exist, and pure keep-first dedup then
    blocks the only run that could ever grade it.
    """
    existing = read_ledger(path)
    seen_hash = {r.get("row_id") for r in existing if r.get("row_id")}
    best_state: dict[str, int] = {}
    for r in existing:
        if r.get("edge_id") is None:
            continue
        key = _ledger_key(r)
        st = observation_state(r)
        if st > best_state.get(key, -1):
            best_state[key] = st

    to_write: list[dict] = []
    n_dupe_hash = 0
    n_dupe_key = 0
    n_superseded = 0
    for r in rows:
        rid = r.get("row_id")
        key = _ledger_key(r)
        if rid in seen_hash:
            n_dupe_hash += 1
            continue
        state = observation_state(r)
        prior = best_state.get(key)
        # A summary row is a running TALLY, not an observation on the state
        # ladder: its content legitimately changes every night while its state
        # stays STUB.  Gate it on content instead, and let resolve_ledger take
        # the newest.  Without this the tally could never be corrected; with
        # span-keying instead, every night's tally was counted again.
        is_tally = r.get("row_kind") == "edge_summary"
        if prior is not None and not is_tally and state <= prior:
            n_dupe_key += 1
            continue
        if prior is not None:
            n_superseded += 1
        seen_hash.add(rid)
        best_state[key] = state
        to_write.append(r)

    if to_write:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            for r in to_write:
                fh.write(json.dumps(r, sort_keys=True, default=str) + "\n")

    return {
        "n_appended": len(to_write),
        "n_superseded": n_superseded,
        "n_skipped_content_hash": n_dupe_hash,
        "n_skipped_key": n_dupe_key,
        "n_existing": len(existing),
    }


def write_rows(path: Path, rows: Sequence[dict]) -> dict:
    """Replace the RETRO ledger wholesale, atomically.

    The retro file is a replay artifact, not an accruing record: every run
    recomputes it from the same substrate, so the correct semantics are
    "this run's output IS the file", not "merge into what was there".

    Appending instead created a real double-count.  Summary rows are keyed by
    the fire span they cover, so a store that advanced by one session produced
    a new span, a new key, and a SECOND summary row for the same edge — both
    counted.  A full rewrite kills that structurally.

    Written to a temp file and renamed, so an interrupted run leaves the
    previous replay intact rather than a truncated one.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    n_before = len(read_ledger(path)) if path.exists() else 0
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, sort_keys=True, default=str) + "\n")
    tmp.replace(path)
    return {
        "n_written": len(rows),
        "n_appended": len(rows),
        "n_superseded": 0,
        "n_skipped_content_hash": 0,
        "n_skipped_key": 0,
        "n_existing": n_before,
        "mode": "full_rewrite",
    }


# ---------------------------------------------------------------------------
# Aggregation — per-edge scoreboard
# ---------------------------------------------------------------------------

def aggregate(rows: Sequence[dict], *, min_n: int = MIN_N, base_provider=None) -> dict:
    """Per-edge scoreboard with a hard MIN_N floor on every printed rate.

    Below the floor an edge reports ``state="accruing"``, its ``n_graded``, and
    ``agreement_rate=None`` — the count is shown, the rate is not, and
    ``rate_suppressed_reason`` names why.  Nulls are printed, never hidden.

    ``base_provider`` (from :func:`make_base_provider`) recomputes each edge's
    matched base rate from the spine at aggregation time.  Pass it whenever a
    spine is available — without it the scoreboard falls back to the value
    stamped on the rows, which is correct only for the span that existed when
    they were written, and says so via ``base_basis``.

    Rows are resolved through :func:`resolve_ledger` first, so a stub that was
    later superseded by its settled grading is not counted twice.
    """
    rows = resolve_ledger(rows)
    by_edge: dict[str, dict] = {}
    for r in rows:
        eid = r.get("edge_id")
        if not eid:
            continue
        slot = by_edge.setdefault(eid, {
            "edge_id": eid,
            "edge_type": r.get("edge_type"),
            "src": r.get("src"),
            "dst": r.get("dst"),
            "edge_source": r.get("edge_source"),
            "n_fires": 0,
            "n_graded": 0,
            "n_graded_unsettled": 0,
            "n_primary_settled": 0,
            "n_agree": 0,
            "lags": [],
            "graded_session_ix": [],
            "verdict_session_ix": [],
            "claimed_signs": [],
            "dst_sessions": set(),
            "base_rate": None,
            "base_rate_n": 0,
            "dst_subject": r.get("dst_subject"),
            "reason_counts": {},
        })
        if slot["dst_subject"] is None and r.get("dst_subject") is not None:
            slot["dst_subject"] = r["dst_subject"]
        # Stamped fallback only — overwritten below whenever a base_provider is
        # supplied.  Taking the max keeps a single stale row from pinning the
        # value, but the stamped path is span-limited by nature; see base_basis.
        if r.get("dst_up_rate_primary") is not None:
            n_seen = int(r.get("dst_up_rate_n_sessions") or 0)
            if n_seen >= slot["base_rate_n"]:
                slot["base_rate"] = r["dst_up_rate_primary"]
                slot["base_rate_n"] = n_seen
        if r.get("fire_date") is not None:
            slot["n_fires"] += 1
        # Fires bounded away as no-overlap live only in the per-edge summary
        # row's tally; add them back so n_fires is the true emission count.
        slot["n_fires"] += int(r.get("n_fires_no_overlap") or 0)
        reason = r.get("ungradeable_reason")
        if reason:
            slot["reason_counts"][reason] = slot["reason_counts"].get(reason, 0) + 1
        if not r.get("graded"):
            continue
        prim = (r.get("outcomes") or {}).get(str(PRIMARY_HORIZON)) or {}
        agree = prim.get("agree")
        if agree is None:
            continue

        # Every primary-horizon verdict, settled or not, defines the calendar
        # the CONTROL is drawn from — the base rate is descriptive, so scoping
        # it to settled verdicts only would leave an edge with no control at
        # all rather than a control that is merely provisional.
        six_any = r.get("fire_session_ix")
        if six_any is not None:
            slot["verdict_session_ix"].append(int(six_any))
        # The claimed sign is what orients the control (an edge claiming DOWN
        # is scored against 1-up_rate), so it belongs to the descriptive layer
        # too — otherwise an all-unsettled edge gets a control it cannot point.
        if r.get("claimed_sign") is not None:
            slot["claimed_signs"].append(int(r["claimed_sign"]))

        # SETTLED verdicts are final and are the only ones a RATE may be built
        # from.  A verdict whose link window is still filling can still flip —
        # measured at 49% disagreement against the settled retro — so it counts
        # as accruing, is disclosed, and never reaches agreement_rate.
        if not r.get("window_settled"):
            slot["n_graded_unsettled"] += 1
            if r.get("primary_window_settled"):
                slot["n_primary_settled"] += 1
            for s in (prim.get("dst_sessions") or []):
                slot["dst_sessions"].add(str(s))
            continue

        slot["n_graded"] += 1
        slot["n_primary_settled"] += 1
        if agree:
            slot["n_agree"] += 1
        six = r.get("fire_session_ix")
        if six is not None:
            slot["graded_session_ix"].append(int(six))
        # claimed_sign is collected above, for settled and unsettled alike.
        for s in (prim.get("dst_sessions") or []):
            slot["dst_sessions"].add(str(s))
        lag = r.get("realized_lag_sessions")
        if lag is not None:
            slot["lags"].append(int(lag))

    out: list[dict] = []
    for slot in by_edge.values():
        n = slot["n_graded"]
        k = slot["n_agree"]
        above = n >= min_n
        rate = (k / n) if above and n > 0 else None
        ci = wilson_interval(k, n) if above and n > 0 else None
        blocks = count_independent_blocks(slot["graded_session_ix"])

        # Base rate, recomputed from the spine over this edge's OWN fire span
        # under the numerator's estimator.  Never latched to a stamped value
        # when a provider is available: the span grows as the ledger accrues.
        base_basis = "row_stamped_span_limited"
        base_overlap = None
        up = slot["base_rate"]
        base_n = slot["base_rate_n"]
        if base_provider is not None:
            span = slot["verdict_session_ix"] or slot["graded_session_ix"]
            up_r, n_r, evaluated = base_provider(slot["dst_subject"], span)
            if up_r is not None:
                up, base_n, base_basis = up_r, n_r, "matched_estimator_recomputed"
                # NIT: control points and fire sessions come from the same
                # stretch of calendar by construction, so they overlap heavily.
                # Print the intersection instead of letting a reader assume
                # the control is drawn from independent sessions.
                base_overlap = len(evaluated & {int(i) for i in span})

        # Fire-weighted null, NOT the modal sign.  An edge whose fires carry
        # mixed claimed signs is not testing one hypothesis n times; the null a
        # mixed set should be beaten against is the mix itself:
        #     (n_up * up + n_down * (1 - up)) / n
        # Collapsing that to the majority sign biases the comparison toward
        # whichever direction happened to fire more often.  Three live edges
        # already carry mixed signs and will clear MIN_N by accrual.
        signs = slot["claimed_signs"]
        n_pos = sum(1 for s in signs if s > 0)
        n_neg = sum(1 for s in signs if s < 0)
        n_signed = n_pos + n_neg
        if up is None or n_signed == 0:
            base_matched = None
        else:
            base_matched = (n_pos * up + n_neg * (1.0 - up)) / n_signed
        lift = None if (base_matched is None or rate is None) else rate - base_matched

        out.append({
            # The control.  agreement_rate ALONE is not interpretable — read it
            # against the dst's unconditional rate of moving the claimed way.
            "dst_base_rate_matched": base_matched,
            "dst_base_rate_n_sessions": base_n,
            "dst_base_rate_basis": base_basis,
            # How many of the control's evaluation points ARE fire sessions.
            # High overlap is honest by construction — the control is
            # deliberately drawn from the same calendar stretch — but it must
            # be visible, not inferred.
            "dst_base_rate_sessions_overlapping_fires": base_overlap,
            # Settledness split: only settled verdicts reach agreement_rate.
            "n_graded_unsettled": slot["n_graded_unsettled"],
            "n_primary_horizon_settled": slot["n_primary_settled"],
            "settle_offset_sessions": SETTLE_OFFSET_SESSIONS,
            "n_fires_claiming_up": n_pos,
            "n_fires_claiming_down": n_neg,
            "agreement_lift_vs_base": lift,
            # Independence disclosure — read this BEFORE the CI.  Fires only
            # days apart share almost all of a 21-session forward window, so a
            # nominal n of 18 can carry as little as one independent
            # observation.  wilson_interval assumes independent trials, so the
            # printed CI is a NOMINAL floor on width, not a calibrated one.
            # Numerator thinness: how many DISTINCT dst sessions the verdicts
            # rest on.  n_graded counts fires; this counts evidence.
            "n_distinct_dst_sessions": len(slot["dst_sessions"]),
            "thin_numerator_warning": bool(
                slot["n_graded"] > 0 and len(slot["dst_sessions"]) <= 2
            ),
            "n_independent_blocks": blocks,
            "ci_basis": "nominal_wilson_assumes_independent_fires",
            "overlap_warning": bool(above and blocks < min_n),
            "edge_id": slot["edge_id"],
            "edge_type": slot["edge_type"],
            "src": slot["src"],
            "dst": slot["dst"],
            "edge_source": slot["edge_source"],
            "n_fires": slot["n_fires"],
            "n_graded": n,
            "n_agree": k,
            "state": "measured" if above else "accruing",
            "agreement_rate": rate,
            "agreement_ci95": list(ci) if ci else None,
            "rate_suppressed_reason": None if above else f"n_graded<{min_n}",
            "median_lag_sessions": _median(slot["lags"]) if above else None,
            "lag_suppressed_reason": None if above else f"n_graded<{min_n}",
            "n_lag_observations": len(slot["lags"]),
            "reason_counts": dict(sorted(slot["reason_counts"].items())),
            "primary_horizon": PRIMARY_HORIZON,
            "authority": dict(AUTHORITY_BLOCK),
            "display_only": True,
        })

    # Settled verdicts first, then edges carrying the most unsettled evidence —
    # otherwise a store whose fires are all young sorts by nothing at all.
    out.sort(key=lambda r: (-r["n_graded"], -r["n_graded_unsettled"], str(r["edge_id"])))
    n_measured = sum(1 for r in out if r["state"] == "measured")
    return {
        "schema": "neuralweb.edge_outcomes_scoreboard.v1",
        "artifact_id": ARTIFACT_ID,
        "min_n": min_n,
        "primary_horizon": PRIMARY_HORIZON,
        "n_edges": len(out),
        "n_edges_measured": n_measured,
        "n_edges_accruing": len(out) - n_measured,
        "edges": out,
        "authority": dict(AUTHORITY_BLOCK),
        "display_only": True,
        "tier": "display",
        "produced_by": PRODUCED_BY,
    }


def count_independent_blocks(
    session_ixs: Sequence[int], *, stride: int = PRIMARY_HORIZON
) -> int:
    """How many of these fires have non-overlapping forward outcome windows.

    Greedy walk over the sorted session indices, taking a fire only when it
    sits at least ``stride`` sessions after the last one taken.  Two fires
    three days apart share ~85% of a 21-session forward window; counting them
    as two independent trials is how a thin denominator comes to outrank a real
    signal.  This is the honest denominator, printed next to the nominal one.
    """
    ixs = sorted({int(i) for i in session_ixs})
    if not ixs:
        return 0
    blocks = 1
    last = ixs[0]
    for i in ixs[1:]:
        if i - last >= stride:
            blocks += 1
            last = i
    return blocks


def coverage_table(rows: Sequence[dict]) -> dict:
    """Gradeable-fraction + reason-code counts.  The coverage IS a deliverable.

    Resolved through :func:`resolve_ledger` so a superseded stub does not keep
    contributing its reason code after the fire it described has been graded.
    """
    rows = resolve_ledger(rows)
    edges: dict[str, dict] = {}
    for r in rows:
        eid = r.get("edge_id")
        if not eid:
            continue
        slot = edges.setdefault(eid, {"graded": False, "reasons": set()})
        if r.get("graded"):
            slot["graded"] = True
        if r.get("ungradeable_reason"):
            slot["reasons"].add(r["ungradeable_reason"])

    n_edges = len(edges)
    n_gradeable = sum(1 for v in edges.values() if v["graded"])
    reason_edges: dict[str, int] = {}
    for v in edges.values():
        if v["graded"]:
            continue
        for code in v["reasons"]:
            reason_edges[code] = reason_edges.get(code, 0) + 1

    return {
        "n_edges": n_edges,
        "n_edges_gradeable": n_gradeable,
        "gradeable_fraction": (n_gradeable / n_edges) if n_edges else None,
        "ungradeable_by_reason": dict(sorted(reason_edges.items())),
        "reason_notes": {k: REASON_NOTES[k] for k in sorted(reason_edges)},
        "n_rows": len(rows),
        "n_rows_graded": sum(1 for r in rows if r.get("graded")),
    }
