#!/usr/bin/env python3
"""PR-1b — the frozen, counterfactual-replay-labelled BASELINE RACE.

WHAT THIS IS.  Masterplan §8.1 rungs **G0, G0', G1, G2, G3, G4 and C1** raced against the
§7 frozen outcomes on ONE frame: the graded-board frame (§8.5 frame 2,
``data/us_board_ledger/retro_grades.parquet``).  No C2+.  No fitting.  No backfill.

WHAT THIS IS NOT.  It carries **no authority**.  §15 narrowed PR-1b to a calibration
exercise and this module stamps that into every artifact it writes: the champion has
never been graded (§6.1, N=0), so G0 here is a REPLAY of today's scorer over historical
board payloads, the frame is ``survivorship_biased: true``, and half the chartered
horizons (H=42/63) have ZERO graded rows.  ``counterfactual_replay: true`` and
``non_promotion_bearing: true`` are top-level keys of the report, not footnotes, and
the vocabulary law is enforced by a test: a rung **leads on the replay frame**; nothing
here beats, wins, or validates anything.

THE THREE THINGS THIS MODULE REFUSES TO DO
------------------------------------------
1. **Silently default a champion input.**  A date whose snapshot payload cannot be built
   REFUSES for every rung that needs it, is listed by name in ``rung_coverage``, and is
   dropped from every pairwise comparison (comparisons are PAIRED on common dates).
   Within a built date a leg's missing input resolves through *the champion's own*
   fail-closed rule (unknown extension earns 0 runway, a cleared tier earns 0 signal) —
   that is the behaviour that shipped, and it is disclosed per-leg per-date rather than
   smoothed away.
2. **Let an outcome pick a sign.**  Every C1 member's direction lives in
   :data:`REGISTERED_SIGNS` with a ``source`` string naming registry semantics, a
   producer doc, or a filed adjudication.  The rung builders are handed a frame with the
   outcome columns REMOVED (:func:`build_race_frame`), so the sign law is structural and
   not a promise.  §6.6's ore signatures are logged-not-claimed and are never a source.
3. **Manufacture a fold.**  §9.2's minimum-usable-fold rule cannot be satisfied by 24
   dates at a 21-session embargo.  The harness calls
   :func:`scripts.prophet_fusion_arena.folds_for_labels` and embeds its refusal VERBATIM.

Run::

    python3 -m scripts.prophet_fusion_race --out research/prophet_fusion/pr1b_baseline_race

The report carries no wall-clock stamp on purpose: two runs of the same CLI over the same
repo produce byte-identical JSON, which is the reproducibility receipt.  The date lives in
the companion doc and in git.
"""
from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
import tempfile
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

import numpy as np
import pandas as pd

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from engine import us_board_rank as ubr                      # noqa: E402
from scripts.prophet_fusion_arena import (                   # noqa: E402
    ForbiddenCompositeRefusal,
    FoldRefusal,
    Registry,
    folds_for_labels,
    load_registry,
)
from scripts.prophet_fusion_labels import (                  # noqa: E402
    FRAME_BOARD_LEDGER,
    FusionRefusal,
    LabelFrame,
    assert_poolable,
    build_labels,
    load_board_ledger_frame,
)

SCHEMA = "prophet_fusion.pr1b_race.v1"

#: The frame this race runs on.  §8.5 frame 2, and ONLY frame 2 — frames are never
#: pooled.  Frame 3 is REFUSED (see :func:`frame3_refusal`) and frame 1 appears only as
#: a coverage exhibit (:func:`frame1_coverage_exhibit`).
FRAME = FRAME_BOARD_LEDGER

SNAPSHOTS_JSONL = "data/us_board_ledger/snapshots.jsonl"
NAME_SCORE_PARQUET = "data/name_score/us_calls.parquet"
CANDIDATES_DIR = "data/us_prophet_rank/candidates"
GRADES_DIR = "data/us_prophet_rank/grades"

#: §8.3's registered primary tuple, spelled out once so the report and the tests read
#: the same words.
PRIMARY_HORIZON = 10
PRIMARY_K = 5
PRIMARY_COMPOSITION = "deployed"
PRIMARY_TUPLE = (
    "P@5 + top-5 mean excess, H=10 sessions, deployed composition "
    "(stage_rank, -score, ticker), classes POOLED (the grades store's "
    "universe_tier/signal_class cohort columns are null by a named sibling-lane debt, "
    "§7 population-enforcement) — ONE tuple per rung, registered before any outcome "
    "cell in this file is read."
)

HORIZONS = (5, 10, 21)
#: Printed as explicit zero-row nulls, never omitted (§8.7: H=42/63 have no graded rows).
HORIZONS_ABSENT = (42, 63)
METRIC_KS = (1, 3, 5, 10)

#: §8.3 large-loser thresholds, per horizon.  A horizon with no registered threshold is
#: reported null — never handed the neighbouring horizon's number (the labels module's
#: own law, ``FRAGILITY_BY_HORIZON``).
LOSER_THRESHOLD_BY_HORIZON: dict[int, float] = {10: -0.03, 21: -0.10}

#: §8.3 large-winner capture: the realized top-decile-excess names of that date.
WINNER_DECILE = 0.90

BOOTSTRAP_B = 2000
BOOTSTRAP_SEED = 20260814
PERMUTATION_B = 1000
PERMUTATION_SEED = 20260815
TIEBREAK_B = 200
TIEBREAK_SEED = 20260816

#: Lane -> published lane-major rank for G0'.  Disclosed rather than inferred: the
#: board renders buy first, then watch, then the leaders shelf, then laggards, and a
#: reader has to be able to check the mapping this race sorted on.
LANE_RANK = {"buy": 0, "watch": 1, "leaders": 2, "laggards": 3}

#: The five legs, in :data:`engine.us_board_rank.SCORE_WEIGHTS` order.
LEGS = ("signal", "entry", "edge", "runway", "quality")

#: Outcome columns.  The rung builders never see these — :func:`build_race_frame`
#: strips them and :func:`assert_no_outcomes` re-checks at every builder entry.  The
#: registry's ``label_only_stores`` block is the prose form of this list.
OUTCOME_COLUMNS = frozenset({
    "ret", "spy_ret", "excess_spy", "excess_sector", "etf_ret", "sector_etf",
    "mae_close_excess_spy", "mae_close_excess_sector",
    "fwd_mfe_5", "fwd_mfe_10", "fwd_mfe_21", "fwd_mfe_42", "fwd_mfe_63",
    "fwd_mdd", "fwd_mfe", "hit", "tail_win", "tail_loss", "fragile",
    "fragility_threshold", "mfe", "mdd", "tail_registered_read",
})

#: §5.2 + the C1 fence.  These may never reach the C1 feature path.  ``confluence_k``
#: and ``altdata_conv_gte2`` are cross-desk COUNTS of agreeing evidence — a count of
#: families agreeing is the anti-double-count budget spent as a single vote, which is
#: precisely what the family construct exists to forbid.  ``potential_score`` /
#: ``conviction.potential.score`` is G2, a BASELINE: a baseline ingested as evidence
#: cannot be beaten by anything, it is merely re-fit.
C1_FORBIDDEN_INPUTS = frozenset({
    "confluence_k", "conviction", "composite_z", "verdict", "band",
    "potential_score", "name_score", "score", "urgency", "act_level",
    "altdata_conv_gte2", "signal_quality", "validation_status",
})


# --------------------------------------------------------------------------- #
# refusals
# --------------------------------------------------------------------------- #

class RaceRefusal(FusionRefusal):
    """The race cannot be run as specified."""


class ReplayValidationRefusal(RaceRefusal):
    """§6.6's replay gate did not reproduce a single published v2 board byte-exact.

    THE GATE IS THE POINT.  G0 is a replay of the CURRENT scorer over historical board
    payloads.  If the replay cannot reproduce a board whose published score we still
    hold, then whatever G0 scores on the graded window is not the champion — it is an
    unvalidated reimplementation wearing the champion's name, and every delta measured
    against it is a delta against nothing.  §6.6 achieved byte-exact on both v2 dates,
    so this is known-achievable and a failure here is a defect, not a data limit.
    """

    def __init__(self, detail: Mapping[str, Any]) -> None:
        self.detail = dict(detail)
        super().__init__(
            "replay validation FAILED: no v2-era board was reproduced byte-exact "
            f"({detail}). §6.6 reproduced both v2 dates exactly; the race refuses to "
            "emit results behind an unvalidated G0 — an unvalidated champion replay "
            "makes every delta a delta against nothing.")


@dataclass(frozen=True)
class DateRefusal:
    """One (rung, date) that could not be raced, with the input that was missing."""

    rung: str
    date: str
    missing: str

    def as_dict(self) -> dict[str, str]:
        return {"rung": self.rung, "date": self.date, "missing": self.missing}


# --------------------------------------------------------------------------- #
# the sign law (§5.1 semantics / producer docs / filed adjudications)
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class RegisteredSign:
    column: str
    family: str
    sign: int
    kind: str                    # continuous | flag | ordinal | categorical
    source: str
    mapping: Mapping[str, float] | None = None

    def as_dict(self) -> dict[str, Any]:
        out = {"column": self.column, "family": self.family, "sign": int(self.sign),
               "kind": self.kind, "source": self.source}
        if self.mapping is not None:
            out["mapping"] = {str(k): float(v) for k, v in self.mapping.items()}
        return out


#: Tier ordinal.  CHAMPION-INDEPENDENT: read off the GATE's own documented cascade rank
#: (``engine/signal_gate.py`` ``_CASCADE_RANK`` / :func:`engine.signal_gate.tier_rank`,
#: operator-ratified 2026-07-06 — "T2 confirmed cross=0 (best), T1 held take=1, T3=3,
#: T4=4"), NOT off ``us_board_rank._SIGNAL_BASE``.  The two agree on T2>T1>T3; citing the
#: gate keeps C1 from voting with the champion's own constant.
_TIER_ORDINAL = {"T2": 4.0, "T1": 3.0, "T3": 1.0, "T4": 0.0}

#: GEX verdict vocabulary, read from ``engine/gex_confirm.py`` ``_LABEL`` and the
#: ``confirm_at`` / ``caution_at`` thresholds.  NOTE the vocabulary is
#: confirm / neutral / **caution** — there is no "infirm" value in the producer.
_GEX_ORDINAL = {"confirm": 1.0, "neutral": 0.0, "caution": -1.0}

REGISTERED_SIGNS: dict[str, RegisteredSign] = {
    "alpha": RegisteredSign(
        column="alpha", family="F2_MOMENTUM_EXTENSION", sign=+1, kind="continuous",
        source=(
            "registry F2.residual_alpha — the selection axis the champion's 25-point "
            "edge leg reads (engine/us_board_rank.py selection_value/edge_value: a "
            "higher alpha percentile earns more points). A-PRIORI producer direction. "
            "§6.6 measured this axis NEGATIVE against forward excess on this very "
            "frame; that measurement is an OUTCOME and is therefore not a sign source "
            "— G1 and G3 exist to price it as ORDERINGS instead."),
    ),
    "off_high": RegisteredSign(
        column="off_high", family="F2_MOMENTUM_EXTENSION", sign=+1, kind="continuous",
        source=(
            "registry F2.relative_strength member semantics ('RS measures / distance "
            "from high'). off_high is a non-positive percentage distance below the "
            "high, so a value nearer zero is nearer the high and is the stronger "
            "relative-strength reading. §6.6's rho -0.19/-0.23 is logged-not-claimed "
            "and is NOT the sign source."),
    ),
    "tier_cascade": RegisteredSign(
        column="tier_cascade", family="F1_TECHNICAL_CONFLUENCE", sign=+1, kind="ordinal",
        mapping=_TIER_ORDINAL,
        source=(
            "engine/signal_gate.py:80-83 _CASCADE_RANK and tier_rank() — the GATE's own "
            "documented ordering (operator-ratified 2026-07-06: T2 confirmed cross is "
            "best, then T1 held take, then T3 anticipation, then T4). Cited from the "
            "gate deliberately, not from us_board_rank._SIGNAL_BASE, so C1's F1 vote is "
            "not the champion's own constant re-entering as evidence."),
    ),
    "sue_fresh": RegisteredSign(
        column="sue_fresh", family="F4_CATALYST_EVENT", sign=+1, kind="flag",
        source=(
            "registry F4.sue_surprise producer semantics — the chip fires on a fresh "
            "POSITIVE standardized earnings surprise (scripts/grade_us_board.py:767 = "
            "sue_z present AND sue_fresh_days <= 60); PEAD's a-priori direction is "
            "positive. BINDING WARNING carried from the registry: sue_phase0.json's "
            "shallow-panel 'WIRE' verdict was REVERSED by the deep survivorship-clean "
            "panel (IC 0.0006). The sign is the producer's a-priori direction, never a "
            "live GO."),
    ),
    "smartmoney_add": RegisteredSign(
        column="smartmoney_add", family="F5_FLOW_POSITIONING", sign=+1, kind="flag",
        source=(
            "registry F5.smart_money_board_chip — the ledger chip fires on the 13F ADD "
            "direction only (scripts/grade_us_board.py:769 reads r['smartmoney_chip']); "
            "accumulation by the tracked cohort is the a-priori positive direction. The "
            "13F disclosure lag is why the member carries max_staleness_sessions: 63."),
    ),
    "insider_cluster": RegisteredSign(
        column="insider_cluster", family="F5_FLOW_POSITIONING", sign=+1, kind="flag",
        source=(
            "registry F5.insider_panel — the chip fires on >= 2 insider BUYERS "
            "(scripts/grade_us_board.py:764); cluster BUYING is the a-priori positive "
            "direction. §8.5 flags this column as a TRAIN/SERVE SKEW (the panel "
            "collector stopped at 2026q1, registry serving_dead: true): it is raced "
            "here because C1 is an unfitted glass-box vote on a frozen historical "
            "frame, and the skew is printed beside every C1 number rather than being "
            "silently pre-excluded."),
    ),
    "gex_confirm_verdict": RegisteredSign(
        column="gex_confirm_verdict", family="F5_FLOW_POSITIONING", sign=+1,
        kind="categorical", mapping=_GEX_ORDINAL,
        source=(
            "engine/gex_confirm.py _LABEL (lines 49-52) and the confirm_at/caution_at "
            "thresholds (lines 45-46, applied line 177): the long confirmer's positive "
            "verdict is 'confirm' and its negative verdict is 'caution' — the "
            "vocabulary has NO 'infirm' value, and 'neutral' (including the OPEX "
            "suppression override) is the zero. The module's own charter — 'a confirmer "
            "can only LOWER confidence, never manufacture a buy' — is why this is a "
            "confirmer sign and not a standalone ranker."),
    ),
    "news_burst": RegisteredSign(
        column="news_burst", family="F8_ATTENTION_CROWDING", sign=+1, kind="flag",
        source=(
            "PR-1b filed adjudication (this file, reviewable): the ledger chip fires on "
            ">= 3 recent news items on an ALREADY-ADMITTED name "
            "(scripts/grade_us_board.py:768), and the a-priori direction filed for "
            "attention arriving with a catalyst is positive. NAMED AS THE WEAKEST SIGN "
            "IN THIS SET: F8's charter also carries a CROWDING reading under which a "
            "burst is negative. §5.1 forbids a second membership for the second "
            "hypothesis, so the crowding read is a §10.7 registered interaction for a "
            "later rung and NOT a rival sign here."),
    ),
}

#: Options columns that exist on this frame but carry NO single a-priori member
#: direction in the registry.  §8.2/§9.8: picking their signs from this frame's outcomes
#: is exactly the audition the arena forbids, so they stay OUT of C1 v1 and are listed.
OPTIONS_PRESENT_NO_FILED_DIRECTION = (
    "opt_gamma_regime", "opt_dist_to_flip_pct", "opt_wall_up", "opt_wall_down",
    "opt_iv30", "opt_iv_rank_252", "opt_doi_slope_5d", "opt_voi_flag",
    "opt_ivspread_rel", "opt_skew", "opt_skew_5d_chg", "opt_opex_days",
    "opt_pin_risk", "opt_wall_dist_up_pct", "opt_wall_dist_down_pct",
    "opt_net_signed_prem_5d_z", "opt_flow_breadth_group", "opt_dte_quality",
    "opt_crowding_flag", "opt_vanna_relief", "opt_front7_charm_share", "opt_root_class",
)

#: Families expected ABSENT on this frame, with the reason each is absent.  §5.1 F6 is
#: STRUCTURALLY excluded (row-constant per night), which is a different fact from a
#: family whose columns the frame does not carry, and the report must not blur them.
STRUCTURAL_FAMILY_NOTES = {
    "F3_THEME_STRUCTURE": (
        "absent_from_frame: the frozen board payload the ledger records carries no "
        "theme / basket / relay evidence column (sector is IDENTITY, and "
        "donor_state/donor_sector are page-level constants). Not measured here."),
    "F6_MACRO_REGIME": (
        "STRUCTURALLY EXCLUDED, not missing: §5.1 F6 is row-constant per night "
        "(one value for every name), so it is cross-sectionally DEGENERATE by "
        "construction and cannot rank names. The frame DOES carry its columns "
        "(quad_hard_label, vol_regime, rate_pressure, fused_risk_label, "
        "risk_radar_state, dispersion_state) and their row-constancy is measured and "
        "printed in exhibits.f6_row_constancy. Lawful only as a router/interaction "
        "axis (§10.2)."),
    "F7_QUALITY_FUNDAMENTAL": (
        "absent_from_frame: the only F7-adjacent column present is `archetype`, and "
        "§5.1 F7 routes archetype/personality through #5583's fingerprint interfaces, "
        "never raw. No a-priori ordinal direction is filed for a nominal category, and "
        "reading one off this frame's outcomes would be an audition. Not raced."),
}


# --------------------------------------------------------------------------- #
# small helpers
# --------------------------------------------------------------------------- #

def _opt(value: Any) -> float | None:
    """A finite float, or None.  NaN is a null in JSON, never a number."""
    if value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _round(value: Any, places: int = 6) -> float | None:
    out = _opt(value)
    return None if out is None else round(out, places)


def assert_no_outcomes(frame: pd.DataFrame, where: str) -> None:
    """Structural sign law: a rung builder may not see an outcome column.

    This is a STRUCTURE, not a promise.  A builder that cannot reach ``excess_spy``
    cannot fit to it, cannot pick a sign from it and cannot leak it — no review pass
    has to take anyone's word for it.
    """
    leaked = sorted(set(frame.columns) & OUTCOME_COLUMNS)
    if leaked:
        raise RaceRefusal(
            f"{where} was handed outcome column(s) {leaked} — rung builders never see "
            f"outcomes (§9.5 sign law; the registry's label_only_stores block). A "
            f"builder that can read the label can audition against it.")


def _percentile_within_date(frame: pd.DataFrame, values: pd.Series) -> pd.Series:
    """Cross-sectional percentile rank within each date, average ties.

    Nulls stay NULL — a missing member ABSTAINS (§7 O6 / §9.9); it is never handed the
    mid-pool 0.5, because a neutral vote and no vote are different acts.
    """
    numeric = pd.to_numeric(values, errors="coerce")
    return numeric.groupby(frame["date"]).rank(pct=True, method="average")


# --------------------------------------------------------------------------- #
# the frame
# --------------------------------------------------------------------------- #

@dataclass
class RaceFrame:
    """The raced universe: identical per-date candidate sets, features and outcomes."""

    features: pd.DataFrame            # one row per (date, ticker); NO outcome columns
    outcomes: pd.DataFrame            # (date, ticker, horizon) -> the §7 heads
    labels: LabelFrame
    receipt: dict[str, Any] = field(default_factory=dict)

    @property
    def dates(self) -> list[str]:
        return sorted(self.features["date"].unique().tolist())

    def candidate_sets(self) -> dict[str, list[str]]:
        return {str(date): sorted(slab["ticker"].tolist())
                for date, slab in self.features.groupby("date", sort=True)}


#: Columns lifted from the raw ledger onto the per-(date,ticker) feature frame.  Kept
#: explicit: a wildcard would sweep the outcome columns back in the moment the store
#: gains one.
FEATURE_COLUMNS = (
    "lane", "position", "alpha", "off_high", "tier_cascade", "entry_status",
    "sue_fresh", "news_burst", "smartmoney_add", "insider_cluster",
    "gex_confirm_verdict", "altdata_conv_gte2", "confluence_k",
    "rank_by", "price_basis", "price_source", "sector", "archetype",
    "quad_hard_label", "vol_regime", "rate_pressure", "fused_risk_label",
    "risk_radar_state", "dispersion_state", "regime_vector_degraded",
) + OPTIONS_PRESENT_NO_FILED_DIRECTION


def build_race_frame(*, root: Path | str | None = None,
                     raw: pd.DataFrame | None = None,
                     labels: LabelFrame | None = None) -> RaceFrame:
    """Assemble the raced universe from the graded-board store.

    THE CANDIDATE SET IS THE LABEL FRAME'S (§8.3 "identical candidate sets").  Every
    rung ranks exactly these (date, ticker) pairs; abstention is expressed as a refused
    DATE, never as a dropped NAME — a model that ranks an easier subpopulation has not
    led anything.
    """
    raw_frame = load_board_ledger_frame(root=root) if raw is None else raw.copy()
    label_frame = build_labels(frame=raw_frame, frame_name=FRAME) if labels is None else labels

    outcomes = label_frame.frame.copy()
    keys = (outcomes[["date", "ticker"]].drop_duplicates()
            .sort_values(["date", "ticker"]).reset_index(drop=True))

    work = raw_frame.copy()
    date_col = "as_of" if "as_of" in work.columns else "stamp_date"
    work["date"] = work[date_col].astype(str).str.slice(0, 10)
    work["ticker"] = work["ticker"].astype(str)
    present = [c for c in FEATURE_COLUMNS if c in work.columns]
    absent = [c for c in FEATURE_COLUMNS if c not in work.columns]
    work = (work[["date", "ticker"] + present]
            .drop_duplicates(subset=["date", "ticker"], keep="first"))

    features = keys.merge(work, on=["date", "ticker"], how="left", validate="one_to_one")
    unjoined = int(features[present].isna().all(axis=1).sum()) if present else len(features)

    # The structural half of the sign law: the builders literally cannot see an outcome.
    features = features.drop(columns=[c for c in features.columns
                                      if c in OUTCOME_COLUMNS], errors="ignore")
    assert_no_outcomes(features, "build_race_frame")

    pooling = assert_poolable(label_frame, allow_price_basis_pool=True)

    receipt = {
        "labels_receipt": label_frame.receipt,
        "n_dates": int(features["date"].nunique()),
        "n_candidates": int(len(features)),
        "feature_columns_present": present,
        "feature_columns_absent_from_store": absent,
        "rows_with_no_feature_join": unjoined,
        "price_basis_pooling": pooling,
        "pooling_note": (
            "price_basis is POOLED by explicit flag and the frame is therefore tagged "
            "EXPLORATORY and promotion-barred (§9.4). It is pooled rather than split "
            "because splitting 24 dates across 4 bases leaves no cell with enough dates "
            "to read at all — the honest cost is the tag, not a hidden split."),
    }
    return RaceFrame(features=features, outcomes=outcomes, labels=label_frame,
                     receipt=receipt)


# --------------------------------------------------------------------------- #
# the snapshot adapter (the champion's own inputs, off the frozen payloads)
# --------------------------------------------------------------------------- #

def load_snapshots(path: Path | str | None = None) -> dict[str, dict[str, Any]]:
    """``as_of`` -> the frozen published board payload, as ``grade_us_board`` reads it.

    Row order within a lane IS the published order (``collect_boards``' contract), so
    the adapter records it rather than re-deriving it.
    """
    target = Path(path) if path is not None else (_REPO_ROOT / SNAPSHOTS_JSONL)
    if not target.exists():
        raise RaceRefusal(
            f"board snapshots not found at {target} — G0/G2/G3/G4 replay the champion "
            f"from the FROZEN PUBLISHED PAYLOAD and have no other source; a race that "
            f"reconstructed the inputs from today's stores would be leakage, not a "
            f"replay (§9.1).")
    out: dict[str, dict[str, Any]] = {}
    with target.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            doc = json.loads(line)
            as_of = str(doc.get("as_of") or "")[:10]
            if as_of:
                out[as_of] = doc
    return out


def snapshot_rows(doc: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Every lane's rows, lane-major, with the published lane + position stamped on."""
    rows: list[dict[str, Any]] = []
    for lane in ("buy", "watch", "leaders", "laggards"):
        for position, row in enumerate(doc.get(lane) or []):
            item = dict(row)
            item["_lane"] = lane
            item["_position"] = position
            rows.append(item)
    return rows


@dataclass
class ChampionReplay:
    """One date's replayed champion legs, over one pool."""

    date: str
    pool_size: int
    by_ticker: dict[str, dict[str, Any]]
    leg_input_present: dict[str, int]
    leg_nonzero: dict[str, int]


def replay_champion(rows: Sequence[Mapping[str, Any]], *, date: str,
                    alpha_of: Callable[[Mapping[str, Any]], Any] | None = None,
                    ) -> ChampionReplay:
    """Replay ``us_prophet_v2`` over one pool by calling the ENGINE'S OWN leg functions.

    NOT a reimplementation.  :func:`engine.us_board_rank.signal_value`,
    ``entry_value``, ``alpha_percentiles``, ``edge_value``, ``runway_value``,
    ``quality_value``, ``verdict_for`` and ``stage_for`` are imported and called on the
    frozen payload rows, so a future re-tune of any constant moves this replay in
    lockstep instead of silently forking from it.  ``score_rows`` itself is deliberately
    NOT called: it also does the featured/veto/sector-cap pass, which needs blackout and
    reversal-cohort inputs the snapshot does not carry and which the race does not use.

    ``alpha_of`` is the selection-axis reader.  G0/G4 use the champion's own
    (``row['alpha']``); G3 passes the SIGN-FLIPPED reader into this same machinery, so
    G3's percentile is computed by the identical code path (§8.1 G3: "with the edge leg
    SIGN-FLIPPED", not "with a different percentile scheme").
    """
    pool = list(rows)
    percentiles = ubr.alpha_percentiles(pool, value_of=alpha_of)
    by_ticker: dict[str, dict[str, Any]] = {}
    leg_input_present = {leg: 0 for leg in LEGS}
    leg_nonzero = {leg: 0 for leg in LEGS}

    for index, row in enumerate(pool):
        ticker = str(row.get("ticker") or "")
        verdict = ubr.verdict_for(row)
        entry = row.get("entry_signal") or {}
        values = {
            "signal": ubr.signal_value(verdict),
            "entry": ubr.entry_value(entry),
            "edge": ubr.edge_value(percentiles.get(index)),
            "runway": ubr.runway_value(row),
            "quality": ubr.quality_value(row),
        }
        points = {name: round(ubr.SCORE_WEIGHTS[name] * value, 4)
                  for name, value in values.items()}
        score = max(0.0, min(100.0, sum(points.values())))
        stage = ubr.stage_for(row, entry, bottom_watch_stage=ubr.STAGE_BASING)

        # Per-leg INPUT presence, separate from per-leg nonzero.  The champion's
        # fail-closed rules make "unknown" and "measured zero" look identical in the
        # points; this pair of counters keeps them distinguishable in the receipt.
        leg_input_present["signal"] += int(verdict.get("tier_cascade") is not None)
        leg_input_present["entry"] += int(bool(str(entry.get("status") or "").strip()))
        leg_input_present["edge"] += int(percentiles.get(index) is not None)
        leg_input_present["runway"] += int(
            row.get("antichase_shadow_blocked") is True
            or ubr._finite_float(row.get("ext_z")) is not None)
        leg_input_present["quality"] += int(bool(row.get("coiled")))
        for leg in LEGS:
            leg_nonzero[leg] += int(points[leg] > 0)

        by_ticker[ticker] = {
            "ticker": ticker, "values": values, "points": points,
            "score": round(score, 1), "stage": stage,
            "alpha_percentile": percentiles.get(index),
            "lane": row.get("_lane"), "position": row.get("_position"),
        }

    return ChampionReplay(date=date, pool_size=len(pool), by_ticker=by_ticker,
                          leg_input_present=leg_input_present, leg_nonzero=leg_nonzero)


def validate_replay(snapshots: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """§6.6's gate: reproduce a PUBLISHED board's own ``prophet.*`` block byte-exact.

    The truth is embedded in the snapshot itself — the v2-era payloads carry
    ``prophet.score``, the five ``prophet.points`` and ``prophet.alpha_percentile`` for
    the buy lane that was actually scored.  The replay is run over THAT pool (buy-lane
    rows carrying a ``prophet`` block), because the percentile is pool-relative and a
    different pool is a different, legitimate number (§6.7.2).
    """
    per_date: list[dict[str, Any]] = []
    for date in sorted(snapshots):
        doc = snapshots[date]
        pool = [dict(row) for row in (doc.get("buy") or []) if row.get("prophet")]
        if not pool:
            continue
        versions = sorted({str((r.get("prophet") or {}).get("version") or "")
                           for r in pool})
        replay = replay_champion(pool, date=date)
        max_dscore = 0.0
        leg_max = {leg: 0.0 for leg in LEGS}
        pct_mismatch = 0
        stage_mismatch = 0
        for row in pool:
            ticker = str(row.get("ticker") or "")
            mine = replay.by_ticker[ticker]
            truth = row["prophet"]
            max_dscore = max(max_dscore, abs(mine["score"] - float(truth["score"])))
            for leg in LEGS:
                leg_max[leg] = max(leg_max[leg],
                                   abs(mine["points"][leg] - float(truth["points"][leg])))
            got, want = mine["alpha_percentile"], truth.get("alpha_percentile")
            if (got is None) != (want is None) or (
                    got is not None and abs(float(got) - float(want)) > 1e-9):
                pct_mismatch += 1
            if row.get("stage") is not None and mine["stage"] != row.get("stage"):
                stage_mismatch += 1

        per_date.append({
            "date": date,
            "board_definition": versions[0] if len(versions) == 1 else versions,
            "n_rows_compared": len(pool),
            "max_abs_delta_score": round(max_dscore, 6),
            "byte_exact": bool(max_dscore == 0.0 and pct_mismatch == 0
                               and stage_mismatch == 0),
            "max_abs_delta_points": {leg: round(v, 6) for leg, v in leg_max.items()},
            "alpha_percentile_mismatches": pct_mismatch,
            "stage_mismatches": stage_mismatch,
            "leg_input_present": dict(replay.leg_input_present),
            "leg_nonzero": dict(replay.leg_nonzero),
        })

    v2_exact = [d["date"] for d in per_date
                if d["byte_exact"] and d["board_definition"] == ubr.BOARD_DEFINITION]
    return {
        "gate": ("at least one FULL us_prophet_v2 board reproduced byte-exact, else the "
                 "race refuses to emit results"),
        "engine_functions_called": [
            "engine.us_board_rank.verdict_for", "signal_value", "entry_value",
            "alpha_percentiles", "edge_value", "runway_value", "quality_value",
            "stage_for"],
        "current_definition": ubr.BOARD_DEFINITION,
        "weights": dict(ubr.SCORE_WEIGHTS),
        "n_dates_compared": len(per_date),
        "v2_dates_byte_exact": v2_exact,
        "passes": bool(v2_exact),
        "per_date": per_date,
        "expected_v1_divergence_note": (
            "A v1-era board (us_prophet_v1) is EXPECTED to diverge: §6.6 records up to "
            "16.3 points, all of it in the ENTRY leg, from the v1->v2 entry "
            "re-valuation. Two eras are not one score scale. A v1 mismatch is a "
            "receipt, not a defect; a v2 mismatch is a defect."),
        "known_limit": (
            "The replay resolves the gate verdict through us_board_rank.verdict_for, "
            "which falls back to the row's embedded `signal` blob because the snapshot "
            "carries no separate signal_gate map. That module's own docstring records "
            "the two copies legitimately disagreeing (8 of 69 buy rows on 2026-08-12), "
            "so a residual per-row mismatch on some date would be attributable there "
            "first."),
    }


# --------------------------------------------------------------------------- #
# rungs
# --------------------------------------------------------------------------- #

@dataclass
class Rung:
    """One ranker: a score per (date, ticker), plus what it refused and why."""

    key: str
    title: str
    construction: str
    scores: pd.DataFrame                    # date, ticker, score, [stage]
    refusals: list[DateRefusal] = field(default_factory=list)
    notes: dict[str, Any] = field(default_factory=dict)

    @property
    def dates(self) -> list[str]:
        if self.scores.empty:
            return []
        return sorted(self.scores["date"].unique().tolist())


def _empty_scores() -> pd.DataFrame:
    return pd.DataFrame({"date": pd.Series(dtype="object"),
                         "ticker": pd.Series(dtype="object"),
                         "score": pd.Series(dtype="float64"),
                         "stage": pd.Series(dtype="object")})


def _replay_rung(race: RaceFrame, snapshots: Mapping[str, Mapping[str, Any]], *,
                 key: str, title: str, construction: str,
                 alpha_of: Callable[[Mapping[str, Any]], Any] | None = None,
                 recompose: Callable[[Mapping[str, float]], float] | None = None,
                 ) -> Rung:
    """G0 / G3 / G4: the champion's own legs over the RACED pool.

    THE POOL IS THE RACED CANDIDATE SET, not the buy lane.  §8.3 forbids a rung from
    ranking a different population than its rivals, so the pool-relative edge percentile
    is recomputed over every raced name for that date.  That is the same arithmetic on a
    different pool, and the difference is real (§6.7.2 measured the zero-boundary moving
    on pool composition alone) — which is why :func:`validate_replay` runs on the
    PUBLISHED pool and this does not pretend to reproduce published scores.
    """
    assert_no_outcomes(race.features, f"rung {key}")
    rows: list[dict[str, Any]] = []
    refusals: list[DateRefusal] = []
    per_date_legs: dict[str, dict[str, Any]] = {}

    for date, slab in race.features.groupby("date", sort=True):
        doc = snapshots.get(str(date))
        if doc is None:
            refusals.append(DateRefusal(key, str(date),
                                        "no frozen board payload in snapshots.jsonl"))
            continue
        by_ticker = {str(r.get("ticker") or ""): r for r in snapshot_rows(doc)}
        wanted = slab["ticker"].astype(str).tolist()
        missing = [t for t in wanted if t not in by_ticker]
        if missing:
            refusals.append(DateRefusal(
                key, str(date),
                f"{len(missing)} raced name(s) absent from the frozen payload: "
                f"{', '.join(sorted(missing)[:6])}"))
            continue
        pool = [dict(by_ticker[t]) for t in wanted]
        replay = replay_champion(pool, date=str(date), alpha_of=alpha_of)
        per_date_legs[str(date)] = {
            "pool_size": replay.pool_size,
            "leg_input_present": dict(replay.leg_input_present),
            "leg_nonzero": dict(replay.leg_nonzero),
        }
        for ticker in wanted:
            entry = replay.by_ticker[ticker]
            score = (float(entry["score"]) if recompose is None
                     else float(recompose(entry["points"])))
            rows.append({"date": str(date), "ticker": ticker,
                         "score": score, "stage": entry["stage"]})

    scores = pd.DataFrame(rows) if rows else _empty_scores()
    return Rung(key=key, title=title, construction=construction, scores=scores,
                refusals=refusals, notes={"per_date_legs": per_date_legs})


def rung_g0(race: RaceFrame, snapshots: Mapping[str, Mapping[str, Any]]) -> Rung:
    return _replay_rung(
        race, snapshots, key="G0", title="Replayed champion (us_prophet_v2)",
        construction=(
            "engine.us_board_rank's own leg functions over the frozen published payload: "
            "signal 30 / entry 25 / edge 25 / runway 10 / quality 10, score clipped to "
            "[0,100] and rounded to 1dp exactly as score_rows does; stage from "
            "stage_for(..., bottom_watch_stage=STAGE_BASING). Sort (stage_rank, -score, "
            "ticker). This is a COUNTERFACTUAL: the graded window is entirely "
            "pre-prophet (rank_by = bottoming-alignment / confluence), so no row here "
            "ever carried a published prophet score."),
    )


def rung_g3(race: RaceFrame, snapshots: Mapping[str, Mapping[str, Any]]) -> Rung:
    def flipped(row: Mapping[str, Any]) -> Any:
        value = ubr.selection_value(row)
        numeric = ubr._finite_float(value)
        return None if numeric is None else -numeric

    return _replay_rung(
        race, snapshots, key="G3", title="Champion with the edge leg SIGN-FLIPPED",
        alpha_of=flipped,
        construction=(
            "Identical to G0 except that -alpha is fed into the SAME "
            "alpha_percentiles/edge_value machinery (the percentile of -alpha inside "
            "the same date pool). Same legs, same weights, same stages, same sort. "
            "§8.1: a champion-REPAIR baseline, so that a later challenger cannot be "
            "credited for fixing a one-leg sign."),
    )


def rung_g4(race: RaceFrame, snapshots: Mapping[str, Mapping[str, Any]]) -> Rung:
    weight_kept = sum(ubr.SCORE_WEIGHTS[leg] for leg in LEGS if leg != "edge")
    scale = 100.0 / weight_kept

    def recompose(points: Mapping[str, float]) -> float:
        kept = sum(float(points[leg]) for leg in LEGS if leg != "edge")
        return max(0.0, min(100.0, kept * scale))

    return _replay_rung(
        race, snapshots, key="G4", title="Champion with the edge leg REMOVED (pro-rata)",
        recompose=recompose,
        construction=(
            f"(30*signal + 25*entry + 10*runway + 10*quality) * (100/{weight_kept:g}) — "
            f"the deletion variant of G3's question, with the 25 edge points "
            f"redistributed pro-rata so the scale stays comparable. Same legs, same "
            f"stages, same sort."),
    )


def rung_g0_published(race: RaceFrame) -> Rung:
    """G0' — the order users actually saw, lane-major then published position."""
    assert_no_outcomes(race.features, "rung G0'")
    work = race.features[["date", "ticker", "lane", "position"]].copy()
    work["lane_rank"] = work["lane"].astype("string").str.lower().map(LANE_RANK)
    refusals: list[DateRefusal] = []
    keep: list[str] = []
    for date, slab in work.groupby("date", sort=True):
        bad = slab["lane_rank"].isna() | pd.to_numeric(slab["position"],
                                                       errors="coerce").isna()
        if bool(bad.any()):
            refusals.append(DateRefusal(
                "G0'", str(date),
                f"{int(bad.sum())} row(s) carry no published lane/position"))
            continue
        keep.append(str(date))
    work = work[work["date"].isin(keep)].copy()
    # Higher is better, so the published order falls straight out of (-score, ticker).
    work["score"] = -(work["lane_rank"].astype(float) * 10000.0
                      + pd.to_numeric(work["position"], errors="coerce").astype(float))
    work["stage"] = "published"
    return Rung(
        key="G0'", title="The PUBLISHED historical order (what users saw)",
        construction=(
            f"lane-major then published position, read off the ledger's own `lane` / "
            f"`position` columns (grade_us_board.collect_boards: 'position = 0-based "
            f"order within lane as published — this IS the ranking under test'). Lane "
            f"mapping DISCLOSED: {LANE_RANK}. This rung is DEPLOYED BY CONSTRUCTION — "
            f"it is not a score substituted into a composition, it is the composition. "
            f"§8.1 makes it mandatory because the replayed G0 diverges from what "
            f"shipped by up to 16.3 points on v1-era boards."),
        scores=work[["date", "ticker", "score", "stage"]].reset_index(drop=True),
        refusals=refusals,
        notes={"lane_rank": dict(LANE_RANK)})


def rung_g1(race: RaceFrame) -> Rung:
    """G1 — pure residual alpha, the champion's only continuous ranker, alone."""
    assert_no_outcomes(race.features, "rung G1")
    work = race.features[["date", "ticker", "alpha"]].copy()
    work["score"] = pd.to_numeric(work["alpha"], errors="coerce")
    refusals: list[DateRefusal] = []
    keep: list[str] = []
    for date, slab in work.groupby("date", sort=True):
        if not bool(slab["score"].notna().any()):
            refusals.append(DateRefusal("G1", str(date), "alpha absent on every row"))
            continue
        keep.append(str(date))
    work = work[work["date"].isin(keep)].copy()
    return Rung(
        key="G1", title="Residual alpha, descending",
        construction=(
            "alpha descending, ticker tiebreak. §6.6's single most reportable shadow "
            "fact is that this axis has NEGATIVE within-day rank correlation with "
            "forward excess on this population at every horizon; G1 prices it as an "
            "ORDERING rather than restating the correlation."),
        scores=work[["date", "ticker", "score"]].reset_index(drop=True),
        refusals=refusals)


def rung_g2(race: RaceFrame, snapshots: Mapping[str, Mapping[str, Any]]) -> Rung:
    """G2 — ``name_score`` potential, the rival in-house composite, as an ORDERING."""
    assert_no_outcomes(race.features, "rung G2")
    rows: list[dict[str, Any]] = []
    refusals: list[DateRefusal] = []
    for date, slab in race.features.groupby("date", sort=True):
        doc = snapshots.get(str(date))
        if doc is None:
            refusals.append(DateRefusal("G2", str(date),
                                        "no frozen board payload in snapshots.jsonl"))
            continue
        by_ticker = {str(r.get("ticker") or ""): r for r in snapshot_rows(doc)}
        wanted = slab["ticker"].astype(str).tolist()
        values: dict[str, float | None] = {}
        for ticker in wanted:
            row = by_ticker.get(ticker) or {}
            potential = ((row.get("conviction") or {}).get("potential") or {})
            values[ticker] = _opt(potential.get("score"))
        measured = [v for v in values.values() if v is not None]
        if not measured:
            refusals.append(DateRefusal(
                "G2", str(date),
                "conviction.potential.score absent on every row (pre-potential board "
                "schema)"))
            continue
        for ticker in wanted:
            rows.append({"date": str(date), "ticker": ticker,
                         "score": values[ticker]})
    scores = pd.DataFrame(rows) if rows else _empty_scores()
    return Rung(
        key="G2", title="name_score potential (the rival in-house composite)",
        construction=(
            "conviction.potential.score off the frozen payload — the PUBLISHED "
            "name_score, raced as an ordering only. §5.2 forbids it as a FEATURE: a "
            "baseline ingested as evidence cannot be led by anything, it is merely "
            "re-fit."),
        scores=scores, refusals=refusals)


# --------------------------------------------------------------------------- #
# C1 — the evidence-family vote (glass-box)
# --------------------------------------------------------------------------- #

@dataclass
class C1Build:
    rung: Rung
    membership: dict[str, Any]
    family_scores: pd.DataFrame          # date, ticker, <family> columns
    member_percentiles: pd.DataFrame     # date, ticker, <column> oriented percentiles


def _oriented_values(frame: pd.DataFrame, sign: RegisteredSign) -> pd.Series:
    """The member's value, oriented by its REGISTERED sign — never by an outcome."""
    raw = frame[sign.column]
    if sign.mapping is not None:
        numeric = raw.astype("string").str.strip().map(
            {str(k): float(v) for k, v in sign.mapping.items()})
        numeric = pd.to_numeric(numeric, errors="coerce")
    elif sign.kind == "flag":
        # A pandas object column of {True, False, None}: True/False are MEASURED, None
        # is unmeasured.  `astype(float)` on the object column would turn None into NaN
        # (right) and leave the booleans (right), which is exactly what is wanted.
        numeric = pd.to_numeric(raw.map(
            lambda v: np.nan if v is None or (isinstance(v, float) and np.isnan(v))
            else float(bool(v))), errors="coerce")
    else:
        numeric = pd.to_numeric(raw, errors="coerce")
    return numeric * float(sign.sign)


def build_c1(race: RaceFrame, registry: Registry, *,
             coverage_floor: float = 0.50,
             signs: Mapping[str, RegisteredSign] | None = None) -> C1Build:
    """C1 — one vote per FAMILY, equal weight, no fitting beyond normalization.

    Per member: within-date cross-sectional percentile rank (average ties) of the
    SIGN-ORIENTED value.  Per family: the mean of its present members' percentiles.
    C1: the equal-weight mean of the present family scores.

    THE FLOORS DECIDE, NOT THE AUTHOR.  A member below ``coverage_floor`` non-null on
    the frame DROPS and is listed; a family with no surviving member is ABSENT and is
    listed with its reason.  Nothing is pre-excluded for looking weak, and nothing is
    kept for looking strong — the only inputs to those decisions are coverage and the
    registry.
    """
    assert_no_outcomes(race.features, "rung C1")
    table = dict(signs or REGISTERED_SIGNS)

    # --- the fence.  A composite reaching the feature path is a refusal, by name. ---
    for column in table:
        if column in C1_FORBIDDEN_INPUTS or column in registry.forbidden:
            raise ForbiddenCompositeRefusal(
                column, registry.forbidden.get(column, ("its typed legs",)))

    features = race.features
    n_rows = int(len(features))
    members: list[dict[str, Any]] = []
    dropped: list[dict[str, Any]] = []
    percentiles = features[["date", "ticker"]].copy()
    family_members: dict[str, list[str]] = defaultdict(list)

    for column, sign in sorted(table.items()):
        if column not in features.columns:
            dropped.append({"column": column, "family": sign.family,
                            "reason": "absent_from_frame", "coverage": 0.0})
            continue
        oriented = _oriented_values(features, sign)
        coverage = float(oriented.notna().mean()) if n_rows else 0.0
        if coverage < coverage_floor:
            dropped.append({"column": column, "family": sign.family,
                            "reason": "below_coverage_floor",
                            "coverage": round(coverage, 6),
                            "coverage_floor": coverage_floor})
            continue
        percentiles[column] = _percentile_within_date(features, oriented)
        family_members[sign.family].append(column)
        members.append({"column": column, "family": sign.family, "sign": int(sign.sign),
                        "kind": sign.kind, "coverage": round(coverage, 6),
                        "source": sign.source})

    # --- within-family duplicate collapse -----------------------------------------
    # §5.1: "agreement inside this family is one fact, not four."  Two members whose
    # ORIENTED percentile vectors are identical are the same measurement wearing two
    # names, and averaging both would double-weight it inside the family — the
    # anti-double-count budget defeated by copy-paste.  Collapsed members are LISTED,
    # never silently dropped: which columns turned out to be the same reading is itself
    # a §5.3 redundancy finding.
    collapsed: list[dict[str, Any]] = []
    for family, cols in list(family_members.items()):
        seen: dict[tuple, str] = {}
        kept: list[str] = []
        for column in sorted(cols):
            key = tuple(np.round(percentiles[column].fillna(-999.0).to_numpy(), 9))
            if key in seen:
                collapsed.append({"column": column, "family": family,
                                  "duplicate_of": seen[key],
                                  "reason": "identical oriented percentile vector"})
                continue
            seen[key] = column
            kept.append(column)
        family_members[family] = kept

    fam_frame = features[["date", "ticker"]].copy()
    families_present: list[str] = []
    families_absent: list[dict[str, str]] = []
    for family in sorted(registry.families):
        cols = family_members.get(family) or []
        if not cols:
            reason = STRUCTURAL_FAMILY_NOTES.get(family)
            if reason is None:
                fam_dropped = [d["column"] for d in dropped if d["family"] == family]
                reason = (f"no surviving member — every candidate dropped: "
                          f"{', '.join(sorted(fam_dropped))}" if fam_dropped
                          else "no registered member of this family is carried by the "
                               "graded-board frame")
            families_absent.append({"family": family, "reason": reason})
            continue
        fam_frame[family] = percentiles[cols].mean(axis=1, skipna=True)
        families_present.append(family)

    if not families_present:
        raise RaceRefusal(
            "C1 has ZERO surviving families on this frame — every registered member "
            "either is absent or sits below its coverage floor. A vote with no voters "
            "is not a null result about the evidence, it is a null result about the "
            "frame (§9.9 abstention semantics).")

    score = fam_frame[families_present].mean(axis=1, skipna=True)
    n_families = fam_frame[families_present].notna().sum(axis=1)
    scores = features[["date", "ticker"]].copy()
    scores["score"] = score

    rows_by_family_count = {str(k): int(v) for k, v in
                            n_families.value_counts().sort_index().items()}

    rung = Rung(
        key="C1", title="Evidence-family vote (equal weight, glass-box)",
        construction=(
            "Per member: within-date cross-sectional percentile rank (average ties) of "
            "the value oriented by its REGISTERED sign. Per family: the mean of its "
            "present members' percentiles. C1: the equal-weight mean of the present "
            "family scores. No interactions, no fitting beyond the per-date "
            "normalization, no weights read off any outcome. A member below "
            f"{coverage_floor:.0%} non-null coverage on the frame DROPS; a family with "
            "no surviving member is ABSENT; a row missing a family entirely is scored "
            "on the mean of ITS present families and the distribution of "
            "families-per-row is printed."),
        scores=scores.reset_index(drop=True),
        refusals=[],
        notes={"rows_by_n_families": rows_by_family_count,
               "rows_with_zero_families": int((n_families == 0).sum())})

    membership = {
        "coverage_floor": coverage_floor,
        "members_raced": [m for m in members
                          if m["column"] not in {c["column"] for c in collapsed}],
        "members_dropped": dropped,
        "members_collapsed_as_duplicates": collapsed,
        "duplicate_collapse_law": (
            "§5.1: agreement inside a family is ONE fact, not N. Two members whose "
            "oriented percentile vectors are identical are the same measurement under "
            "two names; the second is collapsed and listed rather than averaged in, so "
            "the anti-double-count budget cannot be defeated by registering a column "
            "twice."),
        "families_present": families_present,
        "families_absent": families_absent,
        "rows_by_n_families_present": rows_by_family_count,
        "rows_with_zero_families": int((n_families == 0).sum()),
        "options_present_no_filed_direction": list(OPTIONS_PRESENT_NO_FILED_DIRECTION),
        "options_note": (
            "Present on the frame, LEFT OUT of C1 v1: no single a-priori member "
            "direction is filed for them in the registry, and choosing signs from this "
            "frame's outcomes is the audition §8.2/§9.8 forbids. §6.6's opt_iv30 "
            "signature is logged-not-claimed and is not a filed direction."),
        "forbidden_inputs": sorted(C1_FORBIDDEN_INPUTS),
    }
    return C1Build(rung=rung, membership=membership,
                   family_scores=fam_frame, member_percentiles=percentiles)


# --------------------------------------------------------------------------- #
# composition (§8.3 — the order the product would actually publish)
# --------------------------------------------------------------------------- #

def compose(rung: Rung, *, composition: str,
            stages: pd.DataFrame | None = None) -> pd.DataFrame:
    """Attach the ordering key.  ``deployed`` = (stage_rank, -score, ticker).

    §8.3 measures every primary on the DEPLOYED composition because §6.7.1 measured a
    majority of cross-bucket raw-score comparisons contradicting the published order —
    a raw-score P@5 measures something no user ever sees.  The raw order rides beside
    it, labelled, as the diagnostic §8.3 explicitly demotes.
    """
    frame = rung.scores.copy()
    if frame.empty:
        frame["stage_rank"] = pd.Series(dtype="float64")
        return frame
    if composition == "raw":
        frame["stage_rank"] = 0
        return frame
    if composition != PRIMARY_COMPOSITION:
        raise RaceRefusal(f"unknown composition {composition!r}")
    if "stage" in frame.columns and frame["stage"].notna().all():
        source = frame["stage"]
    elif stages is not None:
        merged = frame.merge(stages, on=["date", "ticker"], how="left",
                             suffixes=("", "_g0"))
        source = merged["stage_g0"] if "stage_g0" in merged else merged["stage"]
        source.index = frame.index
    else:
        frame["stage_rank"] = np.nan
        return frame
    ranks = source.astype("string").map(
        lambda s: ubr.stage_rank(str(s)) if isinstance(s, str) else np.nan)
    # 'published' is G0''s own marker: the rung IS the deployed order, so every row
    # shares one bucket and the sort collapses to the published sequence.
    ranks = ranks.where(source.astype("string") != "published", 0)
    frame["stage_rank"] = pd.to_numeric(ranks, errors="coerce")
    return frame


def order_within_date(slab: pd.DataFrame, *,
                      tiebreak: pd.Series | None = None) -> pd.DataFrame:
    """(stage_rank asc, score desc, ticker asc); a NULL score never outranks a measured one."""
    work = slab.copy()
    work["_score"] = pd.to_numeric(work["score"], errors="coerce")
    work["_stage"] = pd.to_numeric(work["stage_rank"], errors="coerce").fillna(
        len(ubr.STAGE_ORDER))
    work["_tie"] = (work["ticker"].astype(str) if tiebreak is None
                    else tiebreak.reindex(work.index))
    work = work.sort_values(["_stage", "_score", "_tie"],
                            ascending=[True, False, True],
                            na_position="last", kind="mergesort")
    return work


# --------------------------------------------------------------------------- #
# metrics (§8.3)
# --------------------------------------------------------------------------- #

def _outcome_slice(race: RaceFrame, horizon: int) -> pd.DataFrame:
    slab = race.outcomes[race.outcomes["horizon"] == int(horizon)]
    return slab[["date", "ticker", "excess_spy", "mfe", "mdd"]].copy()


def per_date_metrics(ordered: pd.DataFrame, outcome: pd.DataFrame, *,
                     horizon: int, ks: Sequence[int] = METRIC_KS) -> dict[str, Any]:
    """Every §8.3 metric for ONE date.  Nulls are printed, never filled."""
    joined = ordered.merge(outcome, on=["date", "ticker"], how="left")
    excess = pd.to_numeric(joined["excess_spy"], errors="coerce")
    row: dict[str, Any] = {"n_candidates": int(len(joined)),
                           "n_measured": int(excess.notna().sum())}
    loser_threshold = LOSER_THRESHOLD_BY_HORIZON.get(int(horizon))

    for k in ks:
        head = excess.head(int(k)).dropna()
        row[f"p_at_{k}"] = float((head > 0).mean()) if len(head) else None
        row[f"top_{k}_mean_excess"] = float(head.mean()) if len(head) else None
        row[f"top_{k}_median_excess"] = float(head.median()) if len(head) else None
        row[f"top_{k}_n_measured"] = int(len(head))

    top10 = excess.head(10).dropna()
    row["large_loser_rate_top10"] = (
        float((top10 < loser_threshold).mean())
        if (loser_threshold is not None and len(top10)) else None)
    row["loser_threshold"] = loser_threshold
    row["expected_shortfall_top10"] = (
        float(top10[top10 <= top10.quantile(0.10)].mean()) if len(top10) >= 3 else None)

    measured = excess.dropna()
    if len(measured) >= 10:
        cutoff = float(measured.quantile(WINNER_DECILE))
        winners = set(joined.loc[excess >= cutoff, "ticker"].astype(str))
        top10_names = set(joined.head(10)["ticker"].astype(str))
        row["large_winner_capture_top10"] = (
            float(len(winners & top10_names) / len(winners)) if winners else None)
        row["n_large_winners"] = len(winners)
    else:
        row["large_winner_capture_top10"] = None
        row["n_large_winners"] = None

    mfe = pd.to_numeric(joined["mfe"], errors="coerce").head(10)
    mdd = pd.to_numeric(joined["mdd"], errors="coerce").head(10)
    row["top10_mfe_median"] = float(mfe.median()) if mfe.notna().any() else None
    row["top10_mfe_coverage"] = float(mfe.notna().mean()) if len(mfe) else None
    row["top10_mdd_median"] = float(mdd.median()) if mdd.notna().any() else None
    row["top10_mdd_coverage"] = float(mdd.notna().mean()) if len(mdd) else None

    score = pd.to_numeric(joined["score"], errors="coerce")
    both = pd.DataFrame({"s": score, "e": excess}).dropna()
    row["spearman"] = (float(both["s"].corr(both["e"], method="spearman"))
                       if len(both) >= 5 and both["s"].nunique() > 1 else None)
    row["spearman_n"] = int(len(both))

    distinct = int(score.nunique(dropna=True))
    row["n_distinct_scores"] = distinct
    row["tie_ratio"] = (float(distinct / len(joined)) if len(joined) else None)
    row["top5_boundary_ties"] = _boundary_ties(joined, k=5)
    return row


def _boundary_ties(joined: pd.DataFrame, *, k: int = 5) -> int:
    """Rows sharing the k-th row's (stage_rank, score) — i.e. decided by the tiebreak."""
    if len(joined) <= k:
        return 0
    score = pd.to_numeric(joined["score"], errors="coerce")
    stage = pd.to_numeric(joined.get("stage_rank"), errors="coerce")
    boundary_score, boundary_stage = score.iloc[k - 1], (
        stage.iloc[k - 1] if stage is not None and len(stage) else np.nan)
    if pd.isna(boundary_score):
        return 0
    same = score == boundary_score
    if stage is not None and len(stage) and not pd.isna(boundary_stage):
        same &= stage == boundary_stage
    return int(same.sum()) if int(same.sum()) > 1 else 0


def score_rung(rung: Rung, race: RaceFrame, *, horizon: int, composition: str,
               stages: pd.DataFrame | None = None,
               tiebreak_seed: int | None = None) -> dict[str, Any]:
    """Per-date then equal-weight-over-dates, the arena's convention."""
    composed = compose(rung, composition=composition, stages=stages)
    if composed.empty or composed["stage_rank"].isna().all():
        return {"rung": rung.key, "horizon": int(horizon), "composition": composition,
                "n_dates": 0, "per_date": [], "aggregate": {},
                "unavailable": ("no stage bucketing is computable for this rung on this "
                                "frame — the deployed composition needs the G0 adapter's "
                                "stages and the date carries no frozen payload")}
    outcome = _outcome_slice(race, horizon)
    rng = np.random.default_rng(tiebreak_seed) if tiebreak_seed is not None else None
    per_date: list[dict[str, Any]] = []
    for date, slab in composed.groupby("date", sort=True):
        tiebreak = None
        if rng is not None:
            tiebreak = pd.Series(rng.random(len(slab)), index=slab.index)
        ordered = order_within_date(slab, tiebreak=tiebreak)
        row = per_date_metrics(ordered, outcome, horizon=horizon)
        row["date"] = str(date)
        per_date.append(row)

    table = pd.DataFrame(per_date)
    aggregate: dict[str, Any] = {}
    for column in table.columns:
        if column in ("date", "loser_threshold") or column.endswith("_n_measured"):
            continue
        series = pd.to_numeric(table[column], errors="coerce").dropna()
        aggregate[column] = _round(series.mean()) if len(series) else None
        aggregate[f"{column}__n_dates"] = int(len(series))
    return {
        "rung": rung.key, "horizon": int(horizon), "composition": composition,
        "composition_note": (
            "DEPLOYED: the rung's score substituted into the champion's own "
            "(stage_rank, -score, ticker) sort (§8.3 primary surface)."
            if composition == PRIMARY_COMPOSITION else
            "RAW score order — the pure-score diagnostic §8.3 explicitly DEMOTES. Not "
            "comparable to any published primary."),
        "n_dates": int(len(table)), "per_date": per_date, "aggregate": aggregate,
    }


# --------------------------------------------------------------------------- #
# uncertainty
# --------------------------------------------------------------------------- #

def restrict_aggregate(scored: Mapping[str, Any],
                       dates: Iterable[str]) -> dict[str, Any]:
    """Re-average a rung's per-date table over a FIXED date set.

    Why this exists: the rungs do not all race the same nights (G0/G2/G3/G4 need a
    frozen payload, G0'/G1/C1 do not), so a headline table built from each rung's own
    dates compares seven different windows. This is the apples-to-apples read — every
    rung on the intersection — and it rides BESIDE the own-dates table rather than
    replacing it, because "which nights could this rung even see" is itself a result.
    """
    keep = set(str(d) for d in dates)
    rows = [row for row in (scored.get("per_date") or []) if str(row["date"]) in keep]
    table = pd.DataFrame(rows)
    aggregate: dict[str, Any] = {}
    if table.empty:
        return {"n_dates": 0, "aggregate": aggregate}
    for column in table.columns:
        if column in ("date", "loser_threshold") or column.endswith("_n_measured"):
            continue
        series = pd.to_numeric(table[column], errors="coerce").dropna()
        aggregate[column] = _round(series.mean()) if len(series) else None
        aggregate[f"{column}__n_dates"] = int(len(series))
    return {"n_dates": int(len(table)), "aggregate": aggregate}


def _measured_dates(scored: Mapping[str, Any], metric: str) -> set[str]:
    return {str(row["date"]) for row in (scored.get("per_date") or [])
            if _opt(row.get(metric)) is not None}


def _per_date_series(scored: Mapping[str, Any], metric: str) -> dict[str, float]:
    out: dict[str, float] = {}
    for row in scored.get("per_date") or []:
        value = _opt(row.get(metric))
        if value is not None:
            out[str(row["date"])] = value
    return out


def block_bootstrap_delta(challenger: Mapping[str, Any], anchor: Mapping[str, Any], *,
                          metric: str, b: int = BOOTSTRAP_B,
                          seed: int = BOOTSTRAP_SEED) -> dict[str, Any]:
    """Date-blocked paired bootstrap of a metric DELTA (`DNR:LAW-TIME-CLUSTERED-CI`).

    Dates are the block: overlapping forward windows make rows within a night anything
    but independent, so the resample draws NIGHTS with replacement and never tickers.
    """
    left, right = _per_date_series(challenger, metric), _per_date_series(anchor, metric)
    common = sorted(set(left) & set(right))
    if len(common) < 2:
        return {"metric": metric, "n_common_dates": len(common), "point": None,
                "ci95": [None, None], "b": b, "seed": seed,
                "note": "fewer than 2 common date-blocks — no CI is computable"}
    diffs = np.array([left[d] - right[d] for d in common], dtype="float64")
    rng = np.random.default_rng(seed)
    draws = rng.integers(0, len(diffs), size=(int(b), len(diffs)))
    means = diffs[draws].mean(axis=1)
    return {
        "metric": metric, "n_common_dates": len(common),
        "point": _round(diffs.mean()),
        "ci95": [_round(np.percentile(means, 2.5)), _round(np.percentile(means, 97.5))],
        "se_date_blocked": _round(diffs.std(ddof=1) / math.sqrt(len(diffs))),
        "b": int(b), "seed": int(seed),
        "excludes_zero": bool(np.percentile(means, 2.5) > 0
                              or np.percentile(means, 97.5) < 0),
    }


def permutation_floor(rung: Rung, race: RaceFrame, *, horizon: int, composition: str,
                      stages: pd.DataFrame | None = None,
                      b: int = PERMUTATION_B,
                      seed: int = PERMUTATION_SEED) -> dict[str, Any]:
    """Within-date ticker-shuffle null for top-5 mean excess. EXPLORATORY.

    NOT §9.5's name-permutation null (that binds C3+ and shuffles NAMES against a fitted
    model to prove it did not memorize them). This shuffles the ORDERING inside each
    night and asks only "is this order better than an arbitrary order of the same
    names?" — a floor, labelled as such, claimable for nothing.
    """
    composed = compose(rung, composition=composition, stages=stages)
    if composed.empty or composed["stage_rank"].isna().all():
        return {"rung": rung.key, "unavailable": "no composed ordering"}
    outcome = _outcome_slice(race, horizon)
    observed = score_rung(rung, race, horizon=horizon, composition=composition,
                          stages=stages)
    point = _opt(observed["aggregate"].get(f"top_{PRIMARY_K}_mean_excess"))
    if point is None:
        return {"rung": rung.key, "unavailable": "observed statistic is null"}

    rng = np.random.default_rng(seed)
    slabs = [(str(date), slab) for date, slab in composed.groupby("date", sort=True)]
    draws: list[float] = []
    for _ in range(int(b)):
        values: list[float] = []
        for date, slab in slabs:
            shuffled = slab.copy()
            shuffled["score"] = rng.permutation(
                pd.to_numeric(slab["score"], errors="coerce").to_numpy())
            ordered = order_within_date(shuffled)
            joined = ordered.merge(outcome, on=["date", "ticker"], how="left")
            head = pd.to_numeric(joined["excess_spy"],
                                 errors="coerce").head(PRIMARY_K).dropna()
            if len(head):
                values.append(float(head.mean()))
        if values:
            draws.append(float(np.mean(values)))
    if not draws:
        return {"rung": rung.key, "unavailable": "no permutation draw produced a value"}
    arr = np.array(draws, dtype="float64")
    return {
        "rung": rung.key, "label": "ordering-vs-random floor, EXPLORATORY",
        "statistic": f"top-{PRIMARY_K} mean excess, H={horizon}, {composition}",
        "observed": _round(point), "null_mean": _round(arr.mean()),
        "null_sd": _round(arr.std(ddof=1)),
        "p_value_one_sided": _round((1.0 + float((arr >= point).sum())) / (len(arr) + 1.0)),
        "b": int(b), "seed": int(seed),
        "not_the_9_5_null": ("§9.5's name-permutation null binds C3+ and is a different "
                             "test; this one is a floor and is claimable for nothing."),
    }


def tie_sensitivity(rung: Rung, race: RaceFrame, *, horizon: int, composition: str,
                    stages: pd.DataFrame | None = None, b: int = TIEBREAK_B,
                    seed: int = TIEBREAK_SEED) -> dict[str, Any]:
    """Re-run the primary with RANDOM tie-breaks: how much of P@5 is the alphabet?"""
    values: list[float] = []
    for offset in range(int(b)):
        scored = score_rung(rung, race, horizon=horizon, composition=composition,
                            stages=stages, tiebreak_seed=seed + offset)
        point = _opt(scored["aggregate"].get(f"p_at_{PRIMARY_K}"))
        if point is not None:
            values.append(point)
    if not values:
        return {"rung": rung.key, "unavailable": "no tie-break draw produced a value"}
    arr = np.array(values, dtype="float64")
    baseline = score_rung(rung, race, horizon=horizon, composition=composition,
                          stages=stages)
    return {
        "rung": rung.key, "metric": f"P@{PRIMARY_K}", "horizon": int(horizon),
        "composition": composition, "b": int(b), "seed": int(seed),
        "alphabetic_tiebreak": _round(baseline["aggregate"].get(f"p_at_{PRIMARY_K}")),
        "random_tiebreak_min": _round(arr.min()),
        "random_tiebreak_max": _round(arr.max()),
        "random_tiebreak_mean": _round(arr.mean()),
        "spread": _round(arr.max() - arr.min()),
    }


def benjamini_hochberg(pvalues: Sequence[float], *, alpha: float = 0.05
                       ) -> list[dict[str, Any]]:
    """Hand-rolled BH-FDR (no statsmodels dependency), documented in place.

    Sort ascending, compare p_(i) against i/m * alpha, take the largest i that passes
    and reject everything at or below it. Adjusted p = min over j>=i of (m/j)*p_(j),
    enforced monotone.
    """
    m = len(pvalues)
    order = sorted(range(m), key=lambda i: pvalues[i])
    adjusted = [1.0] * m
    running = 1.0
    for rank in range(m, 0, -1):
        index = order[rank - 1]
        running = min(running, (m / rank) * float(pvalues[index]))
        adjusted[index] = min(1.0, running)
    threshold = 0.0
    for rank in range(m, 0, -1):
        if float(pvalues[order[rank - 1]]) <= (rank / m) * alpha:
            threshold = (rank / m) * alpha
            break
    return [{"p": _round(pvalues[i]), "p_adj": _round(adjusted[i]),
             "reject": bool(float(pvalues[i]) <= threshold)} for i in range(m)]


def _paired_p_value(challenger: Mapping[str, Any], anchor: Mapping[str, Any],
                    metric: str) -> tuple[float | None, int]:
    left, right = _per_date_series(challenger, metric), _per_date_series(anchor, metric)
    common = sorted(set(left) & set(right))
    if len(common) < 3:
        return None, len(common)
    diffs = np.array([left[d] - right[d] for d in common], dtype="float64")
    se = diffs.std(ddof=1) / math.sqrt(len(diffs))
    if not math.isfinite(se) or se == 0.0:
        return None, len(common)
    t = float(diffs.mean() / se)
    # Two-sided normal approximation, disclosed: with 17-24 date-blocks the t and the
    # normal differ in the third decimal and the FDR verdict does not turn on it.
    p = math.erfc(abs(t) / math.sqrt(2.0))
    return p, len(common)


# --------------------------------------------------------------------------- #
# C1 family analysis
# --------------------------------------------------------------------------- #

def _spearman_by_date(frame: pd.DataFrame, left: str, right: str) -> list[float]:
    out: list[float] = []
    for _date, slab in frame.groupby("date", sort=True):
        both = slab[[left, right]].apply(pd.to_numeric, errors="coerce").dropna()
        if len(both) >= 5 and both[left].nunique() > 1 and both[right].nunique() > 1:
            value = both[left].corr(both[right], method="spearman")
            if pd.notna(value):
                out.append(float(value))
    return out


def _partial_spearman_by_date(frame: pd.DataFrame, left: str, right: str,
                              controls: Sequence[str]) -> list[float]:
    """Rank-residual partial correlation, within date.

    Rank every series inside the night, regress the ranks of ``left`` and ``right`` on
    the ranks of the controls (OLS with an intercept), and correlate the residuals.
    """
    out: list[float] = []
    keep = [left, right, *controls]
    for _date, slab in frame.groupby("date", sort=True):
        block = slab[keep].apply(pd.to_numeric, errors="coerce").dropna()
        if len(block) < max(8, len(controls) + 4):
            continue
        ranks = block.rank(method="average")
        if ranks[left].nunique() <= 1 or ranks[right].nunique() <= 1:
            continue
        design = np.column_stack([np.ones(len(ranks))]
                                 + [ranks[c].to_numpy() for c in controls])
        try:
            residual_left = ranks[left].to_numpy() - design @ np.linalg.lstsq(
                design, ranks[left].to_numpy(), rcond=None)[0]
            residual_right = ranks[right].to_numpy() - design @ np.linalg.lstsq(
                design, ranks[right].to_numpy(), rcond=None)[0]
        except np.linalg.LinAlgError:
            continue
        if np.std(residual_left) == 0 or np.std(residual_right) == 0:
            continue
        out.append(float(np.corrcoef(residual_left, residual_right)[0, 1]))
    return out


def _date_blocked_ci(values: Sequence[float], *, b: int = BOOTSTRAP_B,
                     seed: int = BOOTSTRAP_SEED) -> dict[str, Any]:
    arr = np.array([v for v in values if math.isfinite(v)], dtype="float64")
    if len(arr) < 2:
        return {"mean": _round(arr.mean()) if len(arr) else None,
                "n_dates": int(len(arr)), "ci95": [None, None]}
    rng = np.random.default_rng(seed)
    draws = rng.integers(0, len(arr), size=(int(b), len(arr)))
    means = arr[draws].mean(axis=1)
    return {"mean": _round(arr.mean()), "median": _round(np.median(arr)),
            "n_dates": int(len(arr)),
            "ci95": [_round(np.percentile(means, 2.5)),
                     _round(np.percentile(means, 97.5))],
            "share_positive": _round(float((arr > 0).mean()))}


def c1_family_analysis(build: C1Build, race: RaceFrame, g0: Rung, *,
                       horizon: int = PRIMARY_HORIZON,
                       stages: pd.DataFrame | None = None) -> dict[str, Any]:
    """(a) LOFO, (b) single-family, (c) incremental-over-champion, (d) own-family, (e) rho.

    This is the "one family, several independent families, or correlated siblings?"
    question, asked five ways so no single construction carries it.
    """
    families = list(build.membership["families_present"])
    fam = build.family_scores
    outcome = _outcome_slice(race, horizon)
    joined = fam.merge(outcome, on=["date", "ticker"], how="left")

    baseline = score_rung(build.rung, race, horizon=horizon,
                          composition=PRIMARY_COMPOSITION, stages=stages)
    base_p5 = _opt(baseline["aggregate"].get(f"p_at_{PRIMARY_K}"))
    base_top5 = _opt(baseline["aggregate"].get(f"top_{PRIMARY_K}_mean_excess"))

    def _rung_from(columns: Sequence[str], key: str) -> Rung:
        scores = fam[["date", "ticker"]].copy()
        scores["score"] = fam[list(columns)].mean(axis=1, skipna=True)
        return Rung(key=key, title=key, construction="derived from C1 family scores",
                    scores=scores)

    lofo: list[dict[str, Any]] = []
    single: list[dict[str, Any]] = []
    for family in families:
        rest = [f for f in families if f != family]
        if rest:
            scored = score_rung(_rung_from(rest, f"C1-minus-{family}"), race,
                                horizon=horizon, composition=PRIMARY_COMPOSITION,
                                stages=stages)
            lofo.append({
                "family": family,
                "p_at_5_without": _round(scored["aggregate"].get(f"p_at_{PRIMARY_K}")),
                "delta_p_at_5": _round(
                    (base_p5 or 0.0) - (_opt(scored["aggregate"].get(f"p_at_{PRIMARY_K}")) or 0.0))
                if base_p5 is not None else None,
                "top5_mean_excess_without": _round(
                    scored["aggregate"].get(f"top_{PRIMARY_K}_mean_excess")),
                "delta_top5_mean_excess": _round(
                    (base_top5 or 0.0)
                    - (_opt(scored["aggregate"].get(f"top_{PRIMARY_K}_mean_excess")) or 0.0))
                if base_top5 is not None else None,
                "bootstrap_delta_p_at_5": block_bootstrap_delta(
                    baseline, scored, metric=f"p_at_{PRIMARY_K}"),
            })
        alone = score_rung(_rung_from([family], f"C1-only-{family}"), race,
                           horizon=horizon, composition=PRIMARY_COMPOSITION,
                           stages=stages)
        single.append({
            "family": family, "n_dates": alone["n_dates"],
            "p_at_5": _round(alone["aggregate"].get(f"p_at_{PRIMARY_K}")),
            "top5_mean_excess": _round(
                alone["aggregate"].get(f"top_{PRIMARY_K}_mean_excess")),
            "top5_median_excess": _round(
                alone["aggregate"].get(f"top_{PRIMARY_K}_median_excess")),
            "large_loser_rate_top10": _round(
                alone["aggregate"].get("large_loser_rate_top10")),
            "spearman": _round(alone["aggregate"].get("spearman")),
        })

    # (c) incremental over the champion replay: partial Spearman conditioning on G0.
    g0_scores = g0.scores[["date", "ticker", "score"]].rename(
        columns={"score": "g0_score"})
    conditioned = joined.merge(g0_scores, on=["date", "ticker"], how="inner")
    incremental: list[dict[str, Any]] = []
    for family in families:
        raw = _spearman_by_date(joined, family, "excess_spy")
        partial = _partial_spearman_by_date(conditioned, family, "excess_spy",
                                            ["g0_score"])
        incremental.append({
            "family": family,
            "spearman_vs_outcome": _date_blocked_ci(raw),
            "partial_spearman_given_g0": _date_blocked_ci(partial),
            "method": ("rank-residual partial correlation within date: rank every "
                       "series inside the night, regress the family rank and the "
                       "outcome rank on the G0-replay rank, correlate the residuals; "
                       "date-blocked bootstrap CI over nights"),
        })

    # (d) own-family conditioning: each member against the OTHER members of its family.
    own: list[dict[str, Any]] = []
    by_family: dict[str, list[str]] = defaultdict(list)
    for member in build.membership["members_raced"]:
        by_family[member["family"]].append(member["column"])
    member_frame = build.member_percentiles.merge(outcome, on=["date", "ticker"],
                                                  how="left")
    for family, columns in sorted(by_family.items()):
        if len(columns) < 2:
            continue
        for column in columns:
            others = [c for c in columns if c != column]
            own.append({
                "family": family, "member": column, "conditioned_on": others,
                "spearman_vs_outcome": _date_blocked_ci(
                    _spearman_by_date(member_frame, column, "excess_spy")),
                "partial_spearman_given_siblings": _date_blocked_ci(
                    _partial_spearman_by_date(member_frame, column, "excess_spy",
                                              others)),
            })

    # (e) family x family per-date Spearman.
    matrix: dict[str, dict[str, Any]] = {}
    for left in families:
        matrix[left] = {}
        for right in families:
            if left == right:
                matrix[left][right] = 1.0
                continue
            values = _spearman_by_date(fam, left, right)
            matrix[left][right] = _round(float(np.mean(values))) if values else None

    return {
        "horizon": int(horizon), "composition": PRIMARY_COMPOSITION,
        "baseline_c1": {"p_at_5": _round(base_p5),
                        "top5_mean_excess": _round(base_top5),
                        "n_dates": baseline["n_dates"]},
        "leave_one_family_out": lofo,
        "single_family_only": single,
        "incremental_over_champion": incremental,
        "own_family_conditioning": own,
        "family_correlation_matrix": matrix,
        "reading": ("A family whose LOFO delta is ~0 and whose single-family read is "
                    "~the pooled read is a SIBLING, not an independent voter; a family "
                    "whose partial-Spearman-given-G0 keeps the sign of its raw Spearman "
                    "is carrying something the champion replay does not. Every cell "
                    "here is exploratory and promotion-barred (§8.3)."),
    }


# --------------------------------------------------------------------------- #
# exhibits + receipts
# --------------------------------------------------------------------------- #

def frame3_refusal() -> dict[str, Any]:
    """§8.5 frame 3 is REFUSED for this race, and the refusal is a printed result."""
    return {
        "frame": "deep price/technical history (data/massive_stock_day, "
                 "data/baskets/ohlcv, EDGAR, polygon_gex)",
        "status": "REFUSED for PR-1b",
        "reasons": [
            "No champion existed before 2026-06: G0, G0', G3 and G4 are all replays or "
            "reads of a board that did not exist, so four of the seven rungs are "
            "UNDEFINED on that frame. A race missing its own baselines is not a race.",
            "survivorship_biased: true is PRE-ASSIGNED to this frame in §8.5 and §9.6 "
            "bars any promotion claim resting on it; PR-1b is non-promotion-bearing "
            "anyway, but the frame cannot even carry the calibration read that frame 2 "
            "carries, because there is nothing to calibrate against.",
            "G2's input does not reach back: data/name_score/us_calls.parquet starts "
            "2026-06-29, so the name_score ordering is undefined for every earlier date.",
            "§8.3 identical-candidate-sets would be violated by construction: the deep "
            "frame's population is the whole investable universe, not an admitted "
            "board, and DNR:KILL-PROPHET-POP-MERGE keeps those populations apart.",
        ],
        "what_it_is_good_for": (
            "Multi-year PIT reconstruction of price/technical experts and a few event "
            "experts (§8.5), for rungs that do not need a champion baseline. That is "
            "PR-2+ work, and it must be reconstructed from filing/event dates, never "
            "from mutable latest.json files."),
        "frames_never_pooled": True,
    }


def frame1_coverage_exhibit(root: Path | str | None = None) -> dict[str, Any]:
    """§8.5 frame 1 as a COVERAGE EXHIBIT only — it races nothing here."""
    base = Path(root) if root is not None else _REPO_ROOT
    cand_dir = base / CANDIDATES_DIR
    stamps: list[dict[str, Any]] = []
    if cand_dir.is_dir():
        for path in sorted(cand_dir.glob("*.parquet")):
            frame = pd.read_parquet(path, columns=["stamp_date", "tier"])
            frame["d"] = frame["stamp_date"].astype(str).str.slice(0, 10)
            for date, slab in frame.groupby("d", sort=True):
                counts = slab["tier"].astype("string").fillna("<null>").value_counts()
                stamps.append({"stamp_date": str(date), "file": path.name,
                               "n_rows": int(len(slab)),
                               "tiers": {str(k): int(v) for k, v in counts.items()}})
    grades_dir = base / GRADES_DIR
    return {
        "role": ("COVERAGE EXHIBIT ONLY. Frame 1 races nothing in PR-1b — it has four "
                 "to five stamped days, which is a census substrate and not a race "
                 "frame. Frames are never pooled."),
        "stamps": stamps,
        "n_stamps": len(stamps),
        "grades_store": {
            "path": GRADES_DIR,
            "exists": grades_dir.is_dir(),
            "n_files": (len(list(grades_dir.glob('*'))) if grades_dir.is_dir() else 0),
            "matured_rows": 0,
            "note": ("§8.7 FACT, printed rather than inferred: the candidates store's "
                     "own grades/ sibling has ZERO matured rows (the directory is not "
                     "materialized at all). Frame 1 therefore has no outcomes to race "
                     "against, at any horizon, today."),
        },
        "accrual_gap": {
            "window": "2026-08-08 .. 2026-08-13",
            "status": ("PRINTED AS A GAP. No stamp exists for these dates in the "
                       "candidates store and nothing here backfills one — a backfilled "
                       "context vector is a snapshot join wearing a historical date "
                       "(§9.1). The gap is the measurement."),
        },
        "universe_widening_break": (
            "§7 era hygiene: 08-05/06 carry scan rows only, 08-07 carries 1,717 curated "
            "rows. Coverage is reported PER STAMP DATE and never pooled across this "
            "break."),
    }


def f6_row_constancy_exhibit(race: RaceFrame) -> dict[str, Any]:
    """Measure §5.1 F6's row-constancy instead of asserting it."""
    columns = [c for c in ("quad_hard_label", "vol_regime", "rate_pressure",
                           "fused_risk_label", "risk_radar_state", "dispersion_state",
                           "regime_vector_degraded")
               if c in race.features.columns]
    out: dict[str, Any] = {}
    for column in columns:
        per_date = race.features.groupby("date")[column].nunique(dropna=True)
        out[column] = {
            "dates_measured": int((per_date > 0).sum()),
            "dates_row_constant": int((per_date <= 1).sum()),
            "max_distinct_values_within_a_date": int(per_date.max()) if len(per_date) else 0,
        }
    return {
        "columns": out,
        "reading": ("A column with one distinct value per night cannot ORDER names "
                    "inside that night. This is the measured form of §5.1 F6 and the "
                    "reason F6 is STRUCTURALLY EXCLUDED from C1 rather than reported "
                    "missing."),
    }


def store_delta_exhibit(race: RaceFrame,
                        snapshots: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """§6.7.5 — the two memories of the board are not byte-identical. Disclose it."""
    per_date: list[dict[str, Any]] = []
    for date, slab in race.features.groupby("date", sort=True):
        doc = snapshots.get(str(date))
        if doc is None:
            per_date.append({"date": str(date), "snapshot": False,
                             "n_raced": int(len(slab)),
                             "note": "no frozen payload for this date"})
            continue
        snap = {str(r.get("ticker") or "") for r in snapshot_rows(doc)}
        raced = set(slab["ticker"].astype(str))
        per_date.append({
            "date": str(date), "snapshot": True,
            "n_raced": len(raced), "n_snapshot": len(snap),
            "raced_not_in_snapshot": sorted(raced - snap),
            "snapshot_not_raced": sorted(snap - raced),
        })
    return {
        "law": ("§6.7.5: the candidates store's lanes and the snapshot's lanes are not "
                "byte-identical, so the arena JOINS ON THE SNAPSHOT (what shipped) and "
                "discloses the delta. Rows the ledger dropped are usually the label "
                "builder's (date,ticker,horizon) dedupe of a name sitting in two lanes."),
        "per_date": per_date,
        "total_raced_not_in_snapshot": sum(len(d.get("raced_not_in_snapshot") or [])
                                           for d in per_date),
        "total_snapshot_not_raced": sum(len(d.get("snapshot_not_raced") or [])
                                        for d in per_date),
    }


def name_score_cross_check(race: RaceFrame, g2: Rung, *,
                           root: Path | str | None = None,
                           n_dates: int = 3) -> dict[str, Any]:
    """G2 receipt: does the PUBLISHED potential match the name_score store?"""
    base = Path(root) if root is not None else _REPO_ROOT
    path = base / NAME_SCORE_PARQUET
    if not path.exists() or g2.scores.empty:
        return {"status": "unavailable",
                "reason": f"{NAME_SCORE_PARQUET} not materialized"
                          if not path.exists() else "G2 raced no date"}
    store = pd.read_parquet(path, columns=["date", "ticker", "score"])
    store["date"] = store["date"].astype(str).str.slice(0, 10)
    store["ticker"] = store["ticker"].astype(str)
    dates = g2.dates[:int(n_dates)]
    per_date: list[dict[str, Any]] = []
    for date in dates:
        left = g2.scores[g2.scores["date"] == date][["ticker", "score"]]
        right = store[store["date"] == date][["ticker", "score"]]
        merged = left.merge(right, on="ticker", how="inner", suffixes=("_board", "_store"))
        both = merged.dropna()
        exact = int((both["score_board"].astype(float)
                     == both["score_store"].astype(float)).sum())
        per_date.append({
            "date": date, "n_board": int(len(left)), "n_store": int(len(right)),
            "n_joined": int(len(both)),
            "n_exact_match": exact,
            "match_rate": _round(exact / len(both)) if len(both) else None,
            "max_abs_delta": _round((both["score_board"].astype(float)
                                     - both["score_store"].astype(float)).abs().max())
            if len(both) else None,
        })
    return {"store": NAME_SCORE_PARQUET,
            "store_date_range": [str(store["date"].min()), str(store["date"].max())],
            "per_date": per_date,
            "note": ("The board's conviction.potential.score and the name_score store's "
                     "own `score` are two writes of ONE producer; a mismatch is a "
                     "provenance fact about the STORES, not about the rung. G2 races "
                     "the PUBLISHED board value — what the product actually showed — "
                     "so a low match rate does not move G2's numbers; it says the two "
                     "memories of name_score disagree and that a future rung reading "
                     "the STORE would be racing a different quantity than this one."),
            "lag_probe": ("Tested and rejected: the same-date join is the BEST match on "
                          "every date tried (2026-06-30 / 07-01 / 07-31), so the "
                          "disagreement is not a one-session staleness offset.")}


def name_score_pit_receipt(*, root: Path | str | None = None,
                           n_commits: int = 2) -> dict[str, Any]:
    """Is the name_score store PIT-APPENDED, or rewritten? Ask git, not the store.

    A store that is rewritten in place carries today's knowledge on yesterday's rows —
    the exact leak §9.1 forbids. The falsifiable check is whether a historical commit's
    copy of the parquet already contains dates AFTER that commit.
    """
    base = Path(root) if root is not None else _REPO_ROOT
    try:
        log = subprocess.run(
            ["git", "log", f"-{int(n_commits) + 4}", "--format=%H %cI", "--",
             NAME_SCORE_PARQUET],
            cwd=str(base), capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError) as exc:
        return {"status": "unavailable", "reason": f"git unavailable: {exc}"}
    if log.returncode != 0 or not log.stdout.strip():
        return {"status": "unavailable",
                "reason": "no git history for the store in this checkout"}

    checked: list[dict[str, Any]] = []
    for line in log.stdout.strip().splitlines():
        if len(checked) >= int(n_commits):
            break
        sha, _, stamp = line.partition(" ")
        # UTC, not the committer's local wall clock.  The nightly commits at ~23:00
        # PDT carry the NEXT UTC session date in their rows (and in their own subject
        # line, "engine: regime update 2026-08-14"), so a local-date comparison flags a
        # correct append-only store as a PIT violation.  Measured on this very receipt.
        commit_date = pd.Timestamp(stamp.strip()).tz_convert("UTC").strftime("%Y-%m-%d")
        with tempfile.NamedTemporaryFile(suffix=".parquet", delete=True) as handle:
            show = subprocess.run(["git", "show", f"{sha}:{NAME_SCORE_PARQUET}"],
                                  cwd=str(base), capture_output=True, timeout=120)
            if show.returncode != 0 or not show.stdout:
                continue
            handle.write(show.stdout)
            handle.flush()
            try:
                frame = pd.read_parquet(handle.name, columns=["date"])
            except Exception as exc:                          # noqa: BLE001
                checked.append({"commit": sha[:12], "commit_date": commit_date,
                                "status": f"unreadable: {exc}"})
                continue
        dates = frame["date"].astype(str).str.slice(0, 10)
        max_date = str(dates.max())
        checked.append({
            "commit": sha[:12], "commit_date": commit_date,
            "n_rows": int(len(frame)), "max_date_in_file": max_date,
            "pit_ok": bool(max_date <= commit_date),
            "verdict": ("APPEND-ONLY as of this commit: the file's newest date does not "
                        "postdate the commit that wrote it"
                        if max_date <= commit_date else
                        "FUTURE DATE PRESENT: the file carries a date after its own "
                        "commit — investigate before any historical join"),
        })
    return {
        "method": ("git show <sha>:data/name_score/us_calls.parquet into a temp file, "
                   "then assert max(date) <= the commit's own date, with the commit "
                   "date normalized to UTC — the nightly commits at ~23:00 PDT carry "
                   "the NEXT UTC session date in their rows and in their own subject "
                   "line, so a local-clock comparison reports a false PIT violation "
                   "(measured on this receipt before the fix)"),
        "commits_checked": checked,
        "all_pit_ok": bool(checked) and all(c.get("pit_ok") for c in checked),
    }


def mdd_basis(root: Path | str | None = None) -> dict[str, Any]:
    """PR-1a review advisory A1: NAME the column `mdd` actually resolved to."""
    base = Path(root) if root is not None else _REPO_ROOT
    path = base / "data" / "us_board_ledger" / "retro_grades.parquet"
    present: list[str] = []
    if path.exists():
        import pyarrow.parquet as pq
        names = set(pq.ParquetFile(path).schema_arrow.names)
        present = [c for c in ("fwd_mdd", "fwd_mdd_5", "fwd_mdd_10", "fwd_mdd_21",
                               "mae_close_excess_spy") if c in names]
    resolved = present[0] if present else None
    return {
        "resolved_column": resolved,
        "candidates_in_preference_order": ["fwd_mdd", "fwd_mdd_{h}",
                                           "mae_close_excess_spy"],
        "present_in_store": present,
        "warning": (
            "NOT A TRUE INTRABAR MAXIMUM DRAWDOWN. On this frame `mdd` resolves to "
            f"{resolved!r}, a CLOSE-BASED maximum adverse excursion measured on closes "
            "against SPY. It understates a real MDD by exactly the intraday range it "
            "cannot see, and it is an EXCESS series, not a price drawdown. Every "
            "`top10_mdd_median` in this report is that quantity and nothing else."
            if resolved == "mae_close_excess_spy" else
            "The store carries a true fwd_mdd column; the close-based fallback was not "
            "used."),
    }


# --------------------------------------------------------------------------- #
# power (§8.7) — written BEFORE any outcome cell in the file
# --------------------------------------------------------------------------- #

def power_block(race: RaceFrame, rungs: Sequence[Rung], *,
                observed_se: Mapping[str, Any] | None = None) -> dict[str, Any]:
    labels = race.labels
    by_horizon = (labels.frame.groupby("horizon")["excess_spy"]
                  .agg(["size", "count"]).to_dict("index"))
    horizon_rows = {str(int(h)): {"rows": int(v["size"]),
                                  "rows_with_measured_excess": int(v["count"])}
                    for h, v in by_horizon.items()}
    for horizon in HORIZONS_ABSENT:
        horizon_rows[str(horizon)] = {
            "rows": 0, "rows_with_measured_excess": 0,
            "note": "ZERO graded rows — the chartered basing headline (H=63) stays dark "
                    "until its own ruler has data (§8.6.4)"}

    n_dates = {rung.key: len(rung.dates) for rung in rungs}
    primary_dates = min((v for v in n_dates.values() if v), default=0)
    top_k_episodes = {}
    for horizon in HORIZONS:
        slab = labels.frame[labels.frame["horizon"] == horizon]
        dates_with_rows = int(slab["date"].nunique())
        top_k_episodes[str(horizon)] = {
            "dates_with_graded_rows": dates_with_rows,
            "top_5_episodes_upper_bound": dates_with_rows * PRIMARY_K,
            "note": ("upper bound: 5 per graded date, before de-duplicating a name that "
                     "re-enters the top-5 on consecutive nights — episode-level "
                     "honest-N (distinct name x admission episode) is SMALLER"),
        }

    return {
        "written_before_outcomes": True,
        "registered_comparisons": 7,
        "registered_comparison_set": [r.key for r in rungs],
        "primary_tuple": PRIMARY_TUPLE,
        "primary_horizon": PRIMARY_HORIZON,
        "primary_k": PRIMARY_K,
        "primary_composition": PRIMARY_COMPOSITION,
        "fdr_axis": "model x metric x horizon on the SECONDARY table; primaries exempt "
                    "by the §8.3 prereg (one tuple per rung)",
        "slices": "EXPLORATORY BY CONSTRUCTION and structurally barred from any §8.6 "
                  "promotion claim",
        "n_date_blocks_per_rung": n_dates,
        "n_date_blocks_common_minimum": primary_dates,
        "rows_by_horizon": horizon_rows,
        "top_k_episodes_by_horizon": top_k_episodes,
        "date_blocked_se_observed": observed_se or {},
        "registered_expectation": (
            "§8.7 registered SE(ΔP@5) ≈ 0.03–0.04 on ~24 date-blocks, i.e. roughly a "
            "+10pp P@5 improvement is the smallest detectable difference and nothing "
            "smaller is readable"),
        "distance_to_power": [
            "need >= 60 graded prophet-era dates (minimum-usable-fold, §9.2) — have 24 "
            "graded board dates, and ZERO of them carry a published prophet score "
            "(§6.1: the live score has never been graded, N=0)",
            f"need >= 50 top-K episodes at the headline horizon (§8.6.4) — H=10 has "
            f"{top_k_episodes['10']['dates_with_graded_rows']} graded dates, an upper "
            f"bound of {top_k_episodes['10']['top_5_episodes_upper_bound']} top-5 slots "
            f"before episode de-duplication",
            "need a SECOND graded selection era for §8.6.3's era-strata condition — "
            "there is one, so that half of the gate is UNSATISFIABLE today and the gate "
            "cannot pass before then; that is the intended reading, not a defect",
            "need H=42/63 rows for any basing-class claim — there are none",
        ],
        "minimum_detectable_delta_p_at_5": None,   # filled from the observed SEs
    }


# --------------------------------------------------------------------------- #
# the run
# --------------------------------------------------------------------------- #

def _safe_out_dir(out: Path | str | None) -> Path:
    target = (Path(out) if out is not None
              else Path(tempfile.gettempdir()) / "prophet_fusion_race")
    if not target.is_absolute():
        target = _REPO_ROOT / target
    resolved = target.resolve()
    for tracked in ("data", "site"):
        store = (_REPO_ROOT / tracked).resolve()
        if resolved == store or store in resolved.parents:
            raise RaceRefusal(
                f"--out {resolved} is inside {tracked}/ — research tooling never writes "
                f"a tracked store (house law).")
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def run_race(*, root: Path | str | None = None,
             registry_path: Path | str | None = None,
             snapshots_path: Path | str | None = None,
             raw: pd.DataFrame | None = None,
             git_receipts: bool = True,
             bootstrap_b: int = BOOTSTRAP_B,
             permutation_b: int = PERMUTATION_B,
             tiebreak_b: int = TIEBREAK_B) -> dict[str, Any]:
    """Race the seven rungs and return the report document."""
    registry = load_registry(registry_path)
    race = build_race_frame(root=root, raw=raw)
    snapshots = load_snapshots(snapshots_path)

    replay_validation = validate_replay(snapshots)
    if not replay_validation["passes"]:
        raise ReplayValidationRefusal({
            "n_dates_compared": replay_validation["n_dates_compared"],
            "v2_dates_byte_exact": replay_validation["v2_dates_byte_exact"],
        })

    g0 = rung_g0(race, snapshots)
    rungs = [
        g0,
        rung_g0_published(race),
        rung_g1(race),
        rung_g2(race, snapshots),
        rung_g3(race, snapshots),
        rung_g4(race, snapshots),
    ]
    c1 = build_c1(race, registry)
    rungs.append(c1.rung)
    by_key = {rung.key: rung for rung in rungs}
    stages = g0.scores[["date", "ticker", "stage"]].copy()

    # --- §8.7 FIRST: the power block is written before any outcome cell -----------
    report: dict[str, Any] = {
        "schema": SCHEMA,
        "counterfactual_replay": True,
        "non_promotion_bearing": True,
        "horizons_available": list(HORIZONS),
        "survivorship_biased": True,
        "calibration_sentence": (
            "This is a counterfactual replay on a survivorship-flagged frame at "
            "horizons that are 50% absent; it is a calibration exercise and is "
            "non-promotion-bearing (§14, §15)."),
        "frame": {
            "name": FRAME,
            "source": "data/us_board_ledger/retro_grades.parquet",
            "champion_inputs": SNAPSHOTS_JSONL,
            "frames_never_pooled": True,
            **race.receipt,
        },
    }
    report["power"] = power_block(race, rungs)
    n_usable_folds = 0
    try:
        plan = folds_for_labels(race.labels)
        fold_messages = [str(r.get("message")) for r in plan.refusals]
        fold_receipt = plan.receipt
        n_usable_folds = len(plan.folds)
    except FoldRefusal as refusal:
        fold_messages = [str(refusal)]
        fold_receipt = {}
    report["fold_refusal"] = {
        "law": "§9.2 minimum-usable-fold: >= 60 train dates and >= 10 test dates AFTER "
               "purge + embargo, else the harness REFUSES the fold and says so — it "
               "never silently shrinks one.",
        "n_usable_folds": n_usable_folds,
        "messages_verbatim": fold_messages,
        "receipt": fold_receipt,
        "note": "NO FOLD WAS MANUFACTURED. Every number in this report is an in-sample "
                "descriptive read of a frozen frame, which is exactly what a "
                "non-promotion-bearing calibration exercise is allowed to be.",
    }
    report["replay_validation"] = replay_validation
    report["registered_signs"] = {c: s.as_dict() for c, s in sorted(REGISTERED_SIGNS.items())}
    report["family_membership"] = c1.membership
    report["rung_coverage"] = {
        rung.key: {
            "title": rung.title,
            "construction": rung.construction,
            "dates_raced": len(rung.dates),
            "dates_raced_list": rung.dates,
            "dates_refused": len(rung.refusals),
            "refusals": [r.as_dict() for r in rung.refusals],
            "notes": {k: v for k, v in rung.notes.items() if k != "per_date_legs"},
        } for rung in rungs
    }
    report["rung_coverage"]["_law"] = (
        "A rung missing its input for a DATE refuses that whole date and is listed "
        "here; it never drops a NAME (§8.3 identical candidate sets). Pairwise "
        "comparisons are PAIRED on common dates and print their n."
    )
    report["replay_leg_availability"] = {
        rung.key: rung.notes.get("per_date_legs", {})
        for rung in rungs if rung.notes.get("per_date_legs")
    }

    # --- results ------------------------------------------------------------------
    results: dict[str, Any] = {"mdd_basis": mdd_basis(root)}
    for composition in (PRIMARY_COMPOSITION, "raw"):
        block: dict[str, Any] = {}
        for horizon in HORIZONS:
            block[str(horizon)] = {
                rung.key: score_rung(rung, race, horizon=horizon,
                                     composition=composition, stages=stages)
                for rung in rungs
            }
        for horizon in HORIZONS_ABSENT:
            block[str(horizon)] = {
                "_null": f"ZERO graded rows at H={horizon} on this frame. Printed as an "
                         f"explicit null, never omitted and never proxied by a "
                         f"neighbouring horizon."
            }
        results[composition] = block
    results["headline"] = {
        "horizon": PRIMARY_HORIZON, "composition": PRIMARY_COMPOSITION,
        "classes": "POOLED",
        "population_note": (
            "§7 population enforcement: the grades store's universe_tier / signal_class "
            "cohort columns are NULL by a named sibling-lane debt, so class-conditional "
            "claims are IMPOSSIBLE on this frame and none is made. The frame is the "
            "admitted board population, unsplit."),
        "h21_thin": ("H=21 carries 442 rows across the whole frame — flagged THIN. Its "
                     "top-5 episode count is far under the §8.6.4 floor of 50."),
        "table": {
            rung.key: results[PRIMARY_COMPOSITION][str(PRIMARY_HORIZON)][rung.key]["aggregate"]
            for rung in rungs
        },
    }
    primary_cells = {rung.key: results[PRIMARY_COMPOSITION][str(PRIMARY_HORIZON)][rung.key]
                     for rung in rungs}
    common = set.intersection(*[_measured_dates(cell, f"p_at_{PRIMARY_K}")
                                for cell in primary_cells.values()]) \
        if primary_cells else set()
    results["headline_common_dates"] = {
        "why": ("The rungs do NOT all race the same nights: G0/G2/G3/G4 need a frozen "
                "board payload and the first 7 graded dates have none. The table above "
                "gives each rung its own window; this one puts every rung on the "
                "INTERSECTION, which is the only apples-to-apples read of the headline."),
        "n_common_dates": len(common),
        "common_dates": sorted(common),
        "table": {key: restrict_aggregate(cell, common)["aggregate"]
                  for key, cell in primary_cells.items()},
    }
    report["results"] = results

    # --- uncertainty --------------------------------------------------------------
    anchors = ("G0", "G0'")
    deltas: dict[str, Any] = {}
    observed_se: dict[str, Any] = {}
    for rung in rungs:
        if rung.key in anchors:
            continue
        entry: dict[str, Any] = {}
        for anchor in anchors:
            challenger_scored = results[PRIMARY_COMPOSITION][str(PRIMARY_HORIZON)][rung.key]
            anchor_scored = results[PRIMARY_COMPOSITION][str(PRIMARY_HORIZON)][anchor]
            entry[anchor] = {
                "delta_p_at_5": block_bootstrap_delta(
                    challenger_scored, anchor_scored, metric=f"p_at_{PRIMARY_K}",
                    b=bootstrap_b),
                "delta_top5_mean_excess": block_bootstrap_delta(
                    challenger_scored, anchor_scored,
                    metric=f"top_{PRIMARY_K}_mean_excess", b=bootstrap_b),
            }
            se = entry[anchor]["delta_p_at_5"].get("se_date_blocked")
            if se is not None:
                observed_se[f"{rung.key}_vs_{anchor}"] = se
        deltas[rung.key] = entry
    report["uncertainty"] = {
        "method": (f"paired date-blocked bootstrap, B={bootstrap_b}, seed="
                   f"{BOOTSTRAP_SEED}: dates are resampled with replacement and the "
                   f"statistic is the mean per-date difference "
                   f"(`DNR:LAW-TIME-CLUSTERED-CI` — block by date, never ticker alone)"),
        "anchors": list(anchors),
        "deltas_vs_anchors": deltas,
    }
    report["power"]["date_blocked_se_observed"] = observed_se
    if observed_se:
        worst = max(float(v) for v in observed_se.values())
        report["power"]["minimum_detectable_delta_p_at_5"] = _round(1.96 * worst)
        report["power"]["minimum_detectable_note"] = (
            "1.96 x the LARGEST observed date-blocked SE across the six challenger-vs-"
            "anchor pairs: the smallest ΔP@5 whose 95% CI could exclude zero on this "
            "frame. Compare against §8.7's registered ~+10pp expectation.")

    # --- floors, ties, FDR ---------------------------------------------------------
    report["permutation_floor"] = {
        "label": "ordering-vs-random floor, EXPLORATORY",
        "by_rung": {rung.key: permutation_floor(
            rung, race, horizon=PRIMARY_HORIZON, composition=PRIMARY_COMPOSITION,
            stages=stages, b=permutation_b) for rung in rungs},
    }
    tie_targets = []
    for rung in rungs:
        scored = results[PRIMARY_COMPOSITION][str(PRIMARY_HORIZON)][rung.key]
        tied_dates = sum(1 for row in (scored.get("per_date") or [])
                         if int(row.get("top5_boundary_ties") or 0) > 1)
        if rung.key == "C1" or tied_dates >= 3:
            tie_targets.append((rung, tied_dates))
    report["tie_sensitivity"] = {
        "trigger": ("C1 always, plus any rung with top-5-boundary ties on >= 3 dates — "
                    "the alphabetic-tie-artifact question asked out loud"),
        "b": tiebreak_b, "seed": TIEBREAK_SEED,
        "by_rung": {rung.key: {**tie_sensitivity(
            rung, race, horizon=PRIMARY_HORIZON, composition=PRIMARY_COMPOSITION,
            stages=stages, b=tiebreak_b), "n_dates_with_boundary_ties": tied}
            for rung, tied in tie_targets},
    }

    secondary: list[dict[str, Any]] = []
    for composition in (PRIMARY_COMPOSITION, "raw"):
        for horizon in HORIZONS:
            for rung in rungs:
                if rung.key == "G0":
                    continue
                for metric in (f"p_at_{PRIMARY_K}", f"top_{PRIMARY_K}_mean_excess",
                               "p_at_1", "p_at_3", "p_at_10", "spearman",
                               "large_loser_rate_top10"):
                    if composition == PRIMARY_COMPOSITION and horizon == PRIMARY_HORIZON \
                            and metric in (f"p_at_{PRIMARY_K}",
                                           f"top_{PRIMARY_K}_mean_excess"):
                        continue                      # primary, exempt by §8.3 prereg
                    p, n = _paired_p_value(
                        results[composition][str(horizon)][rung.key],
                        results[composition][str(horizon)]["G0"], metric)
                    if p is None:
                        continue
                    secondary.append({"rung": rung.key, "metric": metric,
                                      "horizon": int(horizon),
                                      "composition": composition,
                                      "n_common_dates": n, "p": p})
    bh = benjamini_hochberg([row["p"] for row in secondary]) if secondary else []
    for row, verdict in zip(secondary, bh):
        row.update(verdict)
    report["secondary_fdr"] = {
        "axis": "model x metric x horizon (x composition), vs the G0 anchor",
        "method": ("hand-rolled Benjamini-Hochberg at alpha=0.05 (no statsmodels "
                   "dependency); per-cell p from a paired date-blocked mean difference "
                   "with a two-sided normal approximation, disclosed"),
        "primaries_exempt": "§8.3 registers ONE primary tuple per rung; the two primary "
                            "cells are excluded from this table by prereg, not by result",
        "n_tests": len(secondary),
        "n_rejected": sum(1 for row in secondary if row.get("reject")),
        "table": secondary,
    }

    report["c1_analysis"] = c1_family_analysis(c1, race, g0, stages=stages)
    report["store_deltas"] = store_delta_exhibit(race, snapshots)
    report["exhibits"] = {
        "frame1_candidates_coverage": frame1_coverage_exhibit(root),
        "frame3_refusal": frame3_refusal(),
        "f6_row_constancy": f6_row_constancy_exhibit(race),
        "g2_name_score_cross_check": name_score_cross_check(race, by_key["G2"], root=root),
        "g2_name_score_pit_receipt": (name_score_pit_receipt(root=root) if git_receipts
                                      else {"status": "skipped",
                                            "reason": "git receipts disabled"}),
        "candidate_sets_identical": {
            "law": "§8.3: every rung ranks the same (date, ticker) set on every date it "
                   "races. Verified per date below as set equality against the label "
                   "frame's own candidate set.",
            "verified": _verify_candidate_sets(race, rungs),
        },
    }
    report["generated_by"] = {
        "module": "scripts/prophet_fusion_race.py",
        "cli": "python3 -m scripts.prophet_fusion_race --out "
               "research/prophet_fusion/pr1b_baseline_race",
        "schema": SCHEMA,
        "seeds": {"bootstrap": BOOTSTRAP_SEED, "permutation": PERMUTATION_SEED,
                  "tiebreak": TIEBREAK_SEED},
        "b": {"bootstrap": bootstrap_b, "permutation": permutation_b,
              "tiebreak": tiebreak_b},
        "engine_definition": ubr.BOARD_DEFINITION,
        "selection_era": ubr.SELECTION_ERA,
        "no_wall_clock_stamp": (
            "Deliberate: two runs of the same CLI over the same repo produce "
            "byte-identical JSON, which is the reproducibility receipt. The date lives "
            "in the companion doc and in git."),
        "authority": {"can_rank": False, "can_size": False, "can_gate": False,
                      "can_originate_signal": False, "can_escalate": False},
    }
    return report


def _verify_candidate_sets(race: RaceFrame, rungs: Sequence[Rung]) -> dict[str, Any]:
    truth = race.candidate_sets()
    mismatches: list[dict[str, Any]] = []
    for rung in rungs:
        for date, slab in rung.scores.groupby("date", sort=True):
            got = sorted(slab["ticker"].astype(str).tolist())
            want = truth.get(str(date))
            if want is None or got != want:
                mismatches.append({"rung": rung.key, "date": str(date),
                                   "n_got": len(got),
                                   "n_want": len(want) if want else 0})
    return {"n_mismatches": len(mismatches), "mismatches": mismatches[:20],
            "ok": not mismatches}


def write_report(report: Mapping[str, Any], out_dir: Path) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "report.json"
    path.write_text(json.dumps(report, indent=2, sort_keys=False,
                               ensure_ascii=False, allow_nan=False) + "\n",
                    encoding="utf-8")
    return path


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="PR-1b baseline race — counterfactual replay, non-promotion-bearing")
    parser.add_argument("--out", default=None,
                        help="output directory (never inside data/ or site/)")
    parser.add_argument("--root", default=None, help="repo root override (tests)")
    parser.add_argument("--registry", default=None, help="families.yml override")
    parser.add_argument("--snapshots", default=None, help="snapshots.jsonl override")
    parser.add_argument("--bootstrap-b", type=int, default=BOOTSTRAP_B)
    parser.add_argument("--permutation-b", type=int, default=PERMUTATION_B)
    parser.add_argument("--tiebreak-b", type=int, default=TIEBREAK_B)
    parser.add_argument("--no-git-receipts", action="store_true",
                        help="skip the name_score PIT-append git receipt")
    args = parser.parse_args(argv)

    out_dir = _safe_out_dir(args.out)
    report = run_race(root=args.root, registry_path=args.registry,
                      snapshots_path=args.snapshots,
                      git_receipts=not args.no_git_receipts,
                      bootstrap_b=args.bootstrap_b,
                      permutation_b=args.permutation_b,
                      tiebreak_b=args.tiebreak_b)
    path = write_report(report, out_dir)

    head = report["results"]["headline"]["table"]
    print(f"prophet-fusion race — {SCHEMA} (NON-PROMOTION-BEARING, counterfactual replay)")
    print(f"  frame       : {report['frame']['name']} "
          f"({report['frame']['n_dates']} dates, {report['frame']['n_candidates']} rows)")
    print(f"  replay gate : byte-exact on {report['replay_validation']['v2_dates_byte_exact']}")
    print(f"  headline    : H={PRIMARY_HORIZON}, {PRIMARY_COMPOSITION}, classes pooled")
    for key, aggregate in head.items():
        print(f"    {key:4} P@5={aggregate.get('p_at_5')} "
              f"top5mean={aggregate.get('top_5_mean_excess')} "
              f"(n_dates={aggregate.get('p_at_5__n_dates')})")
    print(f"  report      : {path}")
    return 0


if __name__ == "__main__":                                    # pragma: no cover
    raise SystemExit(main())
