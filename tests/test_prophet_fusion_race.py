"""The PR-1b baseline race is enforced by this file, not by its own prose.

WHAT IS PINNED, AND WHY EACH CLAIM EXISTS.

  * DETERMINISM.  A research artifact nobody can reproduce is an anecdote.  Two runs of
    the same CLI over the same inputs must produce BYTE-IDENTICAL JSON — which is also
    why the report carries no wall-clock stamp.

  * IDENTICAL CANDIDATE SETS (§8.3).  "A model that ranks an easier subpopulation has
    not beaten anything."  Every rung must rank the same (date, ticker) set on every
    date it races; abstention is a refused DATE, never a dropped NAME.

  * FAMILY-VOTE LAW (§5.1/§10.6).  Families are the unit of anti-double-count budgeting.
    Registering the same evidence twice inside one family must not move C1 — otherwise
    the budget is defeated by copy-paste.

  * SIGN LAW (§9.5), STRUCTURALLY.  Rung builders are handed a frame with the outcome
    columns REMOVED.  Mutating the outcomes must move the METRICS and leave every rung
    SCORE untouched.  A builder that cannot reach the label cannot audition against it,
    and no reviewer has to take that on trust.

  * COMPOSITE FENCE (§5.2).  `confluence_k` / `conviction` / `composite_z` /
    `potential_score` are blended composites and G2's own baseline; each must RAISE on
    the C1 feature path, by name.

  * FOLD REFUSAL (§9.2).  24 dates cannot satisfy a 60-train/10-test fold at a
    21-session embargo.  The report must carry the refusal VERBATIM — a harness that
    silently shrank the fold would report a validated number.

  * WORDING (§14/§15).  `counterfactual_replay` and `non_promotion_bearing` are keys,
    and the calibration sentence is in the doc verbatim.

  * G3 / G4 ALGEBRA.  The two champion-repair baselines are the rungs a later challenger
    would otherwise be credited for; if their construction drifts, the credit is wrong.

  * THE REPLAY GATE.  §6.6 reproduced both v2 boards byte-exact, so a replay that
    reproduces none is a DEFECT, and the CLI must refuse to emit results behind it.

Run: python3 -m pytest tests/test_prophet_fusion_race.py -q
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine import us_board_rank as ubr                             # noqa: E402
from scripts import prophet_fusion_race as race_mod                 # noqa: E402
from scripts.prophet_fusion_arena import (                          # noqa: E402
    ForbiddenCompositeRefusal, load_registry,
)
from scripts.prophet_fusion_labels import build_labels              # noqa: E402

DOC_PATH = ROOT / "research" / "prophet_fusion" / "PR1B_BASELINE_RACE.md"
REPORT_PATH = ROOT / "research" / "prophet_fusion" / "pr1b_baseline_race" / "report.json"

CALIBRATION_SENTENCE = (
    "This is a counterfactual replay on a survivorship-flagged frame at horizons that "
    "are 50% absent; it is a calibration exercise and is non-promotion-bearing "
    "(§14, §15)."
)


# --------------------------------------------------------------------------- #
# the synthetic fixture — a whole race, off no real store
# --------------------------------------------------------------------------- #

_TIERS = ("T1", "T2", "T3", None)
_STATUSES = ("buy_now", "bounce_wait", "buy_soon", "later", "watch")
_LANES = ("buy", "watch", "leaders", "laggards")


def _synthetic(n_dates: int = 24, n_tickers: int = 30, seed: int = 7):
    """A frozen ledger frame + the matching snapshot payloads.

    Shaped like the real thing where the shape is load-bearing (per-date candidate sets,
    three horizons, the W3 evidence columns, a null-era gap) and deliberately unlike it
    everywhere else, so a test that passes here is testing the CODE and not the store.
    """
    rng = np.random.default_rng(seed)
    dates = [f"2026-06-{d:02d}" for d in range(1, min(n_dates, 28) + 1)][:n_dates]
    tickers = [f"TK{i:03d}" for i in range(n_tickers)]

    rows: list[dict] = []
    snapshots: dict[str, dict] = {}
    for date in dates:
        lanes: dict[str, list[dict]] = {lane: [] for lane in _LANES}
        alphas = rng.normal(0, 1, size=n_tickers).round(4)
        for index, ticker in enumerate(tickers):
            lane = _LANES[index % len(_LANES)]
            alpha = float(alphas[index])
            tier = _TIERS[int(rng.integers(0, len(_TIERS)))]
            status = _STATUSES[int(rng.integers(0, len(_STATUSES)))]
            ext_z = round(float(rng.uniform(-1, 3)), 3)
            snap = {
                "ticker": ticker, "alpha": alpha, "ext_z": ext_z,
                "signal": {"tier_cascade": tier, "ticks": int(rng.integers(0, 4)),
                           "provisional": bool(rng.integers(0, 2))},
                "entry_signal": {"status": status},
                "coiled": {"coiled": bool(rng.integers(0, 2)),
                           "star": False, "washout_ctx": False},
                "dir": "up", "label": "UPTREND", "state": "ADVANCING",
                "conviction": {"potential": {"score": int(rng.integers(0, 100))}},
            }
            lanes[lane].append(snap)
            for horizon in (5, 10, 21):
                excess = round(float(rng.normal(0.0, 0.06)), 5)
                rows.append({
                    "as_of": date, "ticker": ticker, "horizon": horizon,
                    "lane": lane, "position": len(lanes[lane]) - 1,
                    "alpha": alpha, "off_high": round(-abs(float(rng.normal(4, 3))), 2),
                    "tier_cascade": tier, "entry_status": status,
                    "sue_fresh": bool(rng.integers(0, 2)),
                    "news_burst": bool(rng.integers(0, 2)),
                    "smartmoney_add": bool(rng.integers(0, 2)),
                    "insider_cluster": bool(rng.integers(0, 2)),
                    "gex_confirm_verdict": ("confirm", "neutral", "caution")[
                        int(rng.integers(0, 3))],
                    "altdata_conv_gte2": bool(rng.integers(0, 2)),
                    "confluence_k": int(rng.integers(0, 5)),
                    "rank_by": "confluence", "price_basis": "adjusted",
                    "sector": "Industrials",
                    "excess_spy": excess,
                    "mae_close_excess_spy": round(-abs(float(rng.normal(0.03, 0.02))), 5),
                    f"fwd_mfe_{horizon}": round(abs(float(rng.normal(0.05, 0.03))), 5),
                })
        snapshots[date] = {"as_of": date, **lanes}
    snapshots["2026-08-13"] = _validation_board(rng)
    return pd.DataFrame(rows), snapshots


def _validation_board(rng) -> dict:
    """A v2-era board that carries its own `prophet.*` block, for the replay GATE.

    WHAT THIS DOES AND DOES NOT PROVE.  The block is stamped by calling the engine's own
    leg functions, so this fixture exercises the gate's PLUMBING — that it reads the
    published block, compares every leg, and reports byte-exactness — and it cannot
    prove the arithmetic matches what shipped. That proof is the COMMITTED report's job
    and it stands on real published payloads (see `TestCommittedReport`). The failing
    direction is covered honestly here: `TestReplayValidationGate` feeds a board whose
    published score the replay cannot reproduce and asserts the CLI refuses.
    """
    rows = []
    for index in range(20):
        rows.append({
            "ticker": f"VB{index:02d}", "alpha": round(float(rng.normal(0, 1)), 4),
            "ext_z": round(float(rng.uniform(-1, 3)), 3),
            "signal": {"tier_cascade": _TIERS[int(rng.integers(0, len(_TIERS)))],
                       "ticks": int(rng.integers(0, 4)),
                       "provisional": bool(rng.integers(0, 2))},
            "entry_signal": {"status": _STATUSES[int(rng.integers(0, len(_STATUSES)))]},
            "coiled": {"coiled": bool(rng.integers(0, 2)), "star": False,
                       "washout_ctx": False},
            "dir": "up", "label": "UPTREND", "state": "ADVANCING",
        })
    percentiles = ubr.alpha_percentiles(rows)
    for index, row in enumerate(rows):
        verdict, entry = ubr.verdict_for(row), row["entry_signal"]
        values = {"signal": ubr.signal_value(verdict),
                  "entry": ubr.entry_value(entry),
                  "edge": ubr.edge_value(percentiles.get(index)),
                  "runway": ubr.runway_value(row),
                  "quality": ubr.quality_value(row)}
        points = {name: round(ubr.SCORE_WEIGHTS[name] * value, 4)
                  for name, value in values.items()}
        row["stage"] = ubr.stage_for(row, entry, bottom_watch_stage=ubr.STAGE_BASING)
        row["prophet"] = {"version": ubr.BOARD_DEFINITION,
                          "score": round(max(0.0, min(100.0, sum(points.values()))), 1),
                          "components": values, "points": points,
                          "alpha_percentile": percentiles.get(index)}
    return {"as_of": "2026-08-13", "buy": rows, "watch": [], "laggards": []}


@pytest.fixture(scope="module")
def synthetic():
    return _synthetic()


@pytest.fixture(scope="module")
def registry():
    return load_registry()


@pytest.fixture(scope="module")
def frame(synthetic):
    raw, _snapshots = synthetic
    return race_mod.build_race_frame(raw=raw)


@pytest.fixture(scope="module")
def rungs(frame, synthetic, registry):
    _raw, snapshots = synthetic
    built = [
        race_mod.rung_g0(frame, snapshots),
        race_mod.rung_g0_published(frame),
        race_mod.rung_g1(frame),
        race_mod.rung_g2(frame, snapshots),
        race_mod.rung_g3(frame, snapshots),
        race_mod.rung_g4(frame, snapshots),
        race_mod.build_c1(frame, registry).rung,
    ]
    return built


def _run(tmp_path: Path, synthetic, *, name: str = "run") -> dict:
    raw, snapshots = synthetic
    snap_path = tmp_path / f"{name}_snapshots.jsonl"
    snap_path.write_text(
        "\n".join(json.dumps(doc) for doc in snapshots.values()) + "\n",
        encoding="utf-8")
    return race_mod.run_race(raw=raw, snapshots_path=snap_path, git_receipts=False,
                             bootstrap_b=40, permutation_b=10, tiebreak_b=3)


@pytest.fixture(scope="module")
def report(tmp_path_factory, synthetic):
    """ONE race, shared by every test that only INSPECTS the artifact.

    The determinism test deliberately does not use it — it needs two independent runs,
    which is the whole point of that assertion.
    """
    return _run(tmp_path_factory.mktemp("shared"), synthetic, name="shared")


# --------------------------------------------------------------------------- #
# 1. determinism
# --------------------------------------------------------------------------- #

class TestDeterminism:
    def test_two_runs_produce_byte_identical_json(self, tmp_path, synthetic):
        """A research artifact nobody can reproduce is an anecdote."""
        first = race_mod.write_report(_run(tmp_path, synthetic, name="a"),
                                      tmp_path / "one")
        second = race_mod.write_report(_run(tmp_path, synthetic, name="b"),
                                       tmp_path / "two")
        assert first.read_bytes() == second.read_bytes()

    def test_the_report_carries_no_wall_clock_stamp(self, report):
        """The determinism above is only possible because of this; pin it directly."""
        blob = json.dumps(report)
        for banned in ("generated_at", "timestamp", "run_at", "as_of_utc"):
            assert f'"{banned}"' not in blob, (
                f"{banned!r} would make the artifact non-reproducible; the date belongs "
                f"in the doc and in git")


# --------------------------------------------------------------------------- #
# 2. identical candidate sets (§8.3)
# --------------------------------------------------------------------------- #

class TestIdenticalCandidateSets:
    def test_every_rung_ranks_the_same_names_on_every_date_it_races(self, frame, rungs):
        truth = frame.candidate_sets()
        for rung in rungs:
            for date, slab in rung.scores.groupby("date", sort=True):
                got = sorted(slab["ticker"].astype(str).tolist())
                assert got == truth[str(date)], (
                    f"{rung.key} ranks a different candidate set on {date} — §8.3: a "
                    f"model that ranks an easier subpopulation has not led anything")

    def test_a_rung_refuses_a_whole_date_rather_than_dropping_a_name(
        self, frame, synthetic
    ):
        """Delete one date's payload: G0 must lose the DATE, not the NAMES."""
        _raw, snapshots = synthetic
        victim = frame.dates[3]
        thinned = {k: v for k, v in snapshots.items() if k != victim}
        rung = race_mod.rung_g0(frame, thinned)
        assert victim not in rung.dates
        assert any(r.date == victim for r in rung.refusals)
        truth = frame.candidate_sets()
        for date in rung.dates:
            got = sorted(rung.scores[rung.scores["date"] == date]["ticker"].tolist())
            assert got == truth[date]

    def test_the_report_verifies_candidate_set_equality(self, report):
        assert report["exhibits"]["candidate_sets_identical"]["verified"]["ok"] is True

    def test_a_date_with_no_computable_stage_is_dropped_from_the_deployed_cell(
        self, frame, synthetic, registry
    ):
        """NOT degraded to raw order under the deployed label (§8.3).

        G1/G2/C1 borrow stage buckets from the G0 adapter. Starve G0 of one date's
        payload and that date must LEAVE the deployed cell by name — a constant-filled
        stage rank would silently publish a RAW ordering as a DEPLOYED primary, which is
        the one comparison §8.3 says must never be blurred.
        """
        _raw, snapshots = synthetic
        victim = frame.dates[2]
        thinned = {k: v for k, v in snapshots.items() if k != victim}
        g0 = race_mod.rung_g0(frame, thinned)
        stages = g0.scores[["date", "ticker", "stage"]]
        c1 = race_mod.build_c1(frame, registry).rung

        deployed = race_mod.score_rung(c1, frame, horizon=10, composition="deployed",
                                       stages=stages)
        raw = race_mod.score_rung(c1, frame, horizon=10, composition="raw")
        assert victim in deployed["composition_unavailable_dates"]
        assert victim not in {row["date"] for row in deployed["per_date"]}
        assert victim in {row["date"] for row in raw["per_date"]}, (
            "the raw diagnostic still sees the date — only the deployed cell refuses it")


# --------------------------------------------------------------------------- #
# 3. family-vote law
# --------------------------------------------------------------------------- #

class TestFamilyVoteLaw:
    def test_registering_a_duplicate_column_into_a_family_does_not_change_c1(
        self, frame, registry
    ):
        """Families are the anti-double-count unit; a copy-pasted column is not a
        second vote. The duplicate is a byte-identical copy of `alpha`, so F2's mean of
        [pct(alpha), pct(alpha_copy), pct(off_high)] must equal the original mean —
        which it does only because the vote is taken per FAMILY, never per column."""
        base = race_mod.build_c1(frame, registry)

        work = frame.features.copy()
        work["alpha_copy"] = work["alpha"]
        doubled = race_mod.RaceFrame(features=work, outcomes=frame.outcomes,
                                     labels=frame.labels, receipt=frame.receipt)
        signs = dict(race_mod.REGISTERED_SIGNS)
        original = signs["alpha"]
        signs["alpha_copy"] = race_mod.RegisteredSign(
            column="alpha_copy", family=original.family, sign=original.sign,
            kind=original.kind, source="TEST duplicate of alpha")
        duplicated = race_mod.build_c1(doubled, registry, signs=signs)

        merged = base.rung.scores.merge(duplicated.rung.scores,
                                        on=["date", "ticker"], suffixes=("_a", "_b"))
        assert len(merged) == len(base.rung.scores)
        assert np.allclose(merged["score_a"], merged["score_b"], equal_nan=True)

    def test_a_family_with_no_surviving_member_is_absent_with_a_reason(
        self, frame, registry
    ):
        build = race_mod.build_c1(frame, registry)
        absent = {row["family"]: row["reason"] for row in
                  build.membership["families_absent"]}
        assert absent, "no family absent on a frame that carries three of eight"
        for family, reason in absent.items():
            assert reason.strip(), f"{family} is absent with no stated reason"
        assert "STRUCTURALLY EXCLUDED" in absent["F6_MACRO_REGIME"], (
            "F6 is row-constant per night — that is a STRUCTURAL exclusion and must "
            "never be reported as a missing family")

    def test_a_member_below_the_coverage_floor_drops_and_is_listed(
        self, frame, registry
    ):
        work = frame.features.copy()
        work["sue_fresh"] = work["sue_fresh"].astype("object")
        work.loc[work.index[: int(len(work) * 0.8)], "sue_fresh"] = None
        thinned = race_mod.RaceFrame(features=work, outcomes=frame.outcomes,
                                     labels=frame.labels, receipt=frame.receipt)
        build = race_mod.build_c1(thinned, registry)
        dropped = {row["column"]: row for row in build.membership["members_dropped"]}
        assert "sue_fresh" in dropped
        assert dropped["sue_fresh"]["reason"] == "below_coverage_floor"


# --------------------------------------------------------------------------- #
# 4. the sign law, structurally
# --------------------------------------------------------------------------- #

class TestSignLaw:
    def test_builders_are_handed_a_frame_with_no_outcome_columns(self, frame):
        leaked = sorted(set(frame.features.columns) & race_mod.OUTCOME_COLUMNS)
        assert not leaked, (
            f"the rung builders can see {leaked} — a builder that can read the label "
            f"can audition against it")

    def test_the_guard_refuses_an_outcome_bearing_frame(self, frame):
        poisoned = frame.features.copy()
        poisoned["excess_spy"] = 0.0
        with pytest.raises(race_mod.RaceRefusal, match="outcome column"):
            race_mod.assert_no_outcomes(poisoned, "test")

    def test_mutating_outcomes_moves_metrics_but_never_a_rung_score(
        self, frame, synthetic, registry
    ):
        _raw, snapshots = synthetic
        original = race_mod.rung_g0(frame, snapshots)
        c1_original = race_mod.build_c1(frame, registry).rung

        flipped = frame.outcomes.copy()
        flipped["excess_spy"] = -flipped["excess_spy"]
        mutated = race_mod.RaceFrame(features=frame.features, outcomes=flipped,
                                     labels=frame.labels, receipt=frame.receipt)
        after = race_mod.rung_g0(mutated, snapshots)
        c1_after = race_mod.build_c1(mutated, registry).rung

        assert original.scores.equals(after.scores), "G0 moved when the OUTCOME moved"
        assert c1_original.scores.equals(c1_after.scores), "C1 moved when the OUTCOME moved"

        stages = original.scores[["date", "ticker", "stage"]]
        before_metrics = race_mod.score_rung(original, frame, horizon=10,
                                             composition="deployed", stages=stages)
        after_metrics = race_mod.score_rung(after, mutated, horizon=10,
                                            composition="deployed", stages=stages)
        assert (before_metrics["aggregate"]["top_5_mean_excess"]
                != after_metrics["aggregate"]["top_5_mean_excess"]), (
            "the metric did NOT move when the outcome was negated — this test would "
            "then be vacuous about the scores")


# --------------------------------------------------------------------------- #
# 5. composite fence (§5.2)
# --------------------------------------------------------------------------- #

class TestCompositeFence:
    @pytest.mark.parametrize("column", ["confluence_k", "conviction", "composite_z",
                                        "potential_score", "altdata_conv_gte2"])
    def test_a_composite_on_the_c1_feature_path_raises_by_name(
        self, frame, registry, column
    ):
        work = frame.features.copy()
        if column not in work.columns:
            work[column] = 1.0
        poisoned = race_mod.RaceFrame(features=work, outcomes=frame.outcomes,
                                      labels=frame.labels, receipt=frame.receipt)
        signs = dict(race_mod.REGISTERED_SIGNS)
        signs[column] = race_mod.RegisteredSign(
            column=column, family="F2_MOMENTUM_EXTENSION", sign=+1, kind="continuous",
            source="TEST — must never be admitted")
        with pytest.raises(ForbiddenCompositeRefusal) as excinfo:
            race_mod.build_c1(poisoned, registry, signs=signs)
        assert column in str(excinfo.value)

    def test_the_registered_signs_table_carries_no_forbidden_input(self):
        overlap = set(race_mod.REGISTERED_SIGNS) & race_mod.C1_FORBIDDEN_INPUTS
        assert not overlap, f"{overlap} is both a registered sign and a forbidden input"

    def test_every_registered_sign_names_a_source(self):
        for column, sign in race_mod.REGISTERED_SIGNS.items():
            assert len(sign.source.strip()) > 40, (
                f"{column} carries no substantive `source:` — a sign with no cited "
                f"origin is a sign read off the outcomes")
            assert sign.sign in (-1, 1)


# --------------------------------------------------------------------------- #
# 6. fold refusal (§9.2)
# --------------------------------------------------------------------------- #

class TestFoldRefusal:
    def test_report_carries_a_verbatim_fold_refusal(self, report):
        block = report["fold_refusal"]
        assert block["messages_verbatim"], (
            "24 dates cannot satisfy §9.2's 60-train/10-test rule at a 21-session "
            "embargo; an empty refusal list means the harness silently shrank a fold")
        assert block["n_usable_folds"] == 0
        assert any("minimum-usable-fold" in m for m in block["messages_verbatim"])

    def test_no_fold_was_manufactured(self, report):
        assert "NO FOLD WAS MANUFACTURED" in report["fold_refusal"]["note"]


# --------------------------------------------------------------------------- #
# 7. wording fence (§14 / §15)
# --------------------------------------------------------------------------- #

class TestWordingFence:
    def test_report_is_stamped_replay_and_non_promotion_bearing(self, report):
        assert report["counterfactual_replay"] is True
        assert report["non_promotion_bearing"] is True
        assert report["survivorship_biased"] is True
        assert report["horizons_available"] == [5, 10, 21]
        assert report["calibration_sentence"] == CALIBRATION_SENTENCE

    def test_the_power_block_is_written_before_any_outcome_cell(self, report):
        """§8.7: the registered comparison count is published BEFORE outcomes are read.
        In a file, "before" is a byte offset — so assert one."""
        blob = json.dumps(report, indent=2)
        assert blob.index('"power"') < blob.index('"results"')
        assert blob.index('"registered_comparisons"') < blob.index('"headline"')

    def test_registered_comparison_count_is_seven(self, report):
        assert report["power"]["registered_comparisons"] == 7
        assert len(report["power"]["registered_comparison_set"]) == 7

    @pytest.mark.skipif(not DOC_PATH.exists(), reason="doc not committed yet")
    def test_the_doc_carries_the_calibration_sentence_verbatim(self):
        assert CALIBRATION_SENTENCE in DOC_PATH.read_text(encoding="utf-8")

    @pytest.mark.skipif(not DOC_PATH.exists(), reason="doc not committed yet")
    def test_the_doc_uses_no_promotion_vocabulary(self):
        """`leads on the replay frame`, never `beats` / `wins` / `validates`."""
        text = DOC_PATH.read_text(encoding="utf-8").lower()
        for banned in (" beats ", " wins ", " outperforms ", " validated ",
                       " proves ", " winner "):
            assert banned not in text, (
                f"promotion vocabulary {banned!r} in a non-promotion-bearing artifact")

    @pytest.mark.skipif(not DOC_PATH.exists(), reason="doc not committed yet")
    def test_the_doc_leaves_the_adjudication_section_empty(self):
        text = DOC_PATH.read_text(encoding="utf-8")
        assert "## Adjudication (main loop)" in text, (
            "the commissioning session writes the six answers there; the section must "
            "exist and must be left for it")


# --------------------------------------------------------------------------- #
# 8. G3 inversion
# --------------------------------------------------------------------------- #

class TestG3Inversion:
    def test_g3_edge_ordering_is_the_reverse_of_g0_when_alpha_has_no_ties(self):
        """Build one date with strictly distinct alphas: G3's edge percentile must be
        G0's, reversed. Anything else means the flip touched more than the sign."""
        tickers = [f"AA{i:02d}" for i in range(12)]
        rows = [{"ticker": t, "alpha": float(i)} for i, t in enumerate(tickers)]
        forward = race_mod.replay_champion(rows, date="2026-06-01")

        def flipped(row):
            value = ubr._finite_float(row.get("alpha"))
            return None if value is None else -value

        reverse = race_mod.replay_champion(rows, date="2026-06-01", alpha_of=flipped)

        forward_order = sorted(tickers,
                               key=lambda t: -forward.by_ticker[t]["values"]["edge"])
        reverse_order = sorted(tickers,
                               key=lambda t: -reverse.by_ticker[t]["values"]["edge"])
        # edge_value floors the bottom quartile at 0, so compare the percentile itself,
        # which is the quantity the sign flip acts on.
        forward_pct = [forward.by_ticker[t]["alpha_percentile"] for t in tickers]
        reverse_pct = [reverse.by_ticker[t]["alpha_percentile"] for t in tickers]
        assert forward_pct == list(reversed(reverse_pct))
        assert forward_order[0] == reverse_order[-1]

    def test_g3_changes_only_the_edge_leg(self, frame, synthetic):
        _raw, snapshots = synthetic
        g0 = race_mod.rung_g0(frame, snapshots)
        g3 = race_mod.rung_g3(frame, snapshots)
        merged = g0.scores.merge(g3.scores, on=["date", "ticker"],
                                 suffixes=("_g0", "_g3"))
        assert (merged["stage_g0"] == merged["stage_g3"]).all(), (
            "G3 moved a stage — the flip is scoped to the edge leg's input")
        assert not np.allclose(merged["score_g0"], merged["score_g3"])
        assert (merged["score_g0"] - merged["score_g3"]).abs().max() <= 25.0 + 1e-9, (
            "a change larger than the 25-point edge weight means the flip escaped its leg")


# --------------------------------------------------------------------------- #
# 9. G4 algebra
# --------------------------------------------------------------------------- #

class TestG4Algebra:
    def test_g4_equals_the_pro_rata_rescale_of_the_non_edge_legs(self, frame,
                                                                 synthetic):
        _raw, snapshots = synthetic
        g4 = race_mod.rung_g4(frame, snapshots)
        scale = 100.0 / (100.0 - ubr.SCORE_WEIGHTS["edge"])

        for date, slab in frame.features.groupby("date", sort=True):
            doc = snapshots[str(date)]
            by_ticker = {str(r["ticker"]): r for r in race_mod.snapshot_rows(doc)}
            pool = [dict(by_ticker[t]) for t in slab["ticker"].astype(str)]
            replay = race_mod.replay_champion(pool, date=str(date))
            for ticker, entry in replay.by_ticker.items():
                expected = max(0.0, min(100.0, scale * sum(
                    entry["points"][leg] for leg in race_mod.LEGS if leg != "edge")))
                got = float(g4.scores[(g4.scores["date"] == str(date))
                                      & (g4.scores["ticker"] == ticker)]["score"].iloc[0])
                assert got == pytest.approx(expected, abs=1e-9)
            break                     # one date is the algebra; 24 is a slow tautology

    def test_g4_equals_score_minus_edge_points_rescaled(self, frame, synthetic):
        """The commission's other spelling of the same identity: (score - edge)*100/75."""
        _raw, snapshots = synthetic
        date = frame.dates[0]
        slab = frame.features[frame.features["date"] == date]
        by_ticker = {str(r["ticker"]): r for r in race_mod.snapshot_rows(snapshots[date])}
        pool = [dict(by_ticker[t]) for t in slab["ticker"].astype(str)]
        replay = race_mod.replay_champion(pool, date=date)
        g4 = race_mod.rung_g4(frame, snapshots)
        for ticker, entry in replay.by_ticker.items():
            raw_score = sum(entry["points"].values())
            expected = max(0.0, min(100.0,
                                    (raw_score - entry["points"]["edge"]) * (100.0 / 75.0)))
            got = float(g4.scores[(g4.scores["date"] == date)
                                  & (g4.scores["ticker"] == ticker)]["score"].iloc[0])
            assert got == pytest.approx(expected, abs=1e-9)


# --------------------------------------------------------------------------- #
# 10. the replay-validation gate
# --------------------------------------------------------------------------- #

class TestReplayValidationGate:
    def _mismatching(self):
        """A payload that claims a published score the replay cannot reproduce."""
        rows = []
        for index in range(8):
            rows.append({
                "ticker": f"ZZ{index:02d}", "alpha": float(index), "ext_z": 0.5,
                "signal": {"tier_cascade": "T2", "ticks": 1, "provisional": False},
                "entry_signal": {"status": "buy_now"},
                "coiled": {"coiled": True},
                "dir": "up", "label": "UPTREND", "state": "ADVANCING",
                "prophet": {
                    "version": ubr.BOARD_DEFINITION,
                    "score": 12.3,                       # deliberately wrong
                    "points": {leg: 1.0 for leg in race_mod.LEGS},
                    "alpha_percentile": 0.5,
                },
            })
        return {"2026-08-13": {"as_of": "2026-08-13", "buy": rows}}

    def test_the_cli_refuses_to_emit_results_behind_a_failed_replay(
        self, tmp_path, synthetic
    ):
        raw, _snapshots = synthetic
        snap_path = tmp_path / "bad.jsonl"
        snap_path.write_text(
            "\n".join(json.dumps(doc) for doc in self._mismatching().values()) + "\n",
            encoding="utf-8")
        with pytest.raises(race_mod.ReplayValidationRefusal):
            race_mod.run_race(raw=raw, snapshots_path=snap_path, git_receipts=False,
                              bootstrap_b=10, permutation_b=2, tiebreak_b=2)
        assert not (tmp_path / "report.json").exists()

    def test_validate_replay_marks_the_mismatch_rather_than_hiding_it(self):
        result = race_mod.validate_replay(self._mismatching())
        assert result["passes"] is False
        assert result["per_date"][0]["byte_exact"] is False
        assert result["per_date"][0]["max_abs_delta_score"] > 0


# --------------------------------------------------------------------------- #
# the committed artifact (skipped until it exists)
# --------------------------------------------------------------------------- #

class TestCommittedReport:
    @pytest.mark.skipif(not REPORT_PATH.exists(), reason="report not committed yet")
    def test_committed_report_has_the_exact_top_level_keys(self):
        report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
        for key in ("schema", "counterfactual_replay", "non_promotion_bearing",
                    "horizons_available", "survivorship_biased", "frame", "power",
                    "fold_refusal", "replay_validation", "rung_coverage",
                    "registered_signs", "family_membership", "results", "c1_analysis",
                    "permutation_floor", "tie_sensitivity", "secondary_fdr",
                    "store_deltas", "exhibits", "generated_by"):
            assert key in report, f"committed report is missing {key!r}"
        assert report["schema"] == race_mod.SCHEMA

    @pytest.mark.skipif(not REPORT_PATH.exists(), reason="report not committed yet")
    def test_committed_report_passed_the_replay_gate_on_a_v2_board(self):
        report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
        assert report["replay_validation"]["passes"] is True
        assert report["replay_validation"]["v2_dates_byte_exact"], (
            "the committed race must be standing on at least one byte-exact v2 replay")

    @pytest.mark.skipif(not REPORT_PATH.exists(), reason="report not committed yet")
    def test_committed_report_carries_no_authority(self):
        report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
        assert report["generated_by"]["authority"] == {
            "can_rank": False, "can_size": False, "can_gate": False,
            "can_originate_signal": False, "can_escalate": False}

    @pytest.mark.skipif(not REPORT_PATH.exists(), reason="report not committed yet")
    def test_committed_report_names_the_mdd_basis(self):
        """PR-1a review advisory A1: say WHICH column `mdd` resolved to."""
        report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
        basis = report["results"]["mdd_basis"]
        assert basis["resolved_column"]
        assert "NOT A TRUE INTRABAR" in basis["warning"] or basis[
            "resolved_column"] == "fwd_mdd"
