"""Tests for the V1 excess-legality gate at the `engine.qledger._aggregate` emitter.

WHY THIS FILE EXISTS
--------------------
`grades.jsonl.excess` is RAW subject-minus-control return and is NOT signed by the
claim's direction — the stored `hit` field is what carries direction. A correct
BEARISH call therefore contributes a NEGATIVE excess, so a pooled signed
`excess_mean` over a family that holds calls in both directions measures the drift
of the subject universe, not the skill of the calls. That is invariant V1
(SIGNED_EXCESS_POOLED_ACROSS_DIRECTIONS) in `engine/qledger_validity.py`.

Before this gate the illegal figure was LIVE and reaching a human: `_aggregate`
feeds both `compute_track_record()` -> site/qledger/track_record.json and
`scripts/grade_qledger.compute_promotion_readiness()` -> track_record.json
['promotion_readiness'] / ['_duel_context'], and from there
`engine/experiments_registry._refresh_qledger_promotion()` -> the admin
Experiments tab, rendered literally as "hit=…% · excess=…%". Measured on the
2026-08-12 live corpus: radar@5d published excess_mean=-0.003096 and
whitehouse@5d published -0.002604, both mixed-direction.

WHAT IS PINNED HERE
-------------------
  * a mixed-direction family publishes NO signed excess_mean, at either grouping;
  * it publishes the legal replacements instead (mean_abs_excess + the
    per-direction split), with `excess_basis` naming the reading;
  * a single-direction family is byte-for-byte UNCHANGED — the pooled mean there
    is legitimate and must survive;
  * the gate is DELEGATED to `engine.qledger_validity.may_pool_signed_excess`, not
    re-derived — proven by mutating that symbol and watching the emitter follow;
  * an unprofiled group fails CLOSED;
  * the two downstream surfaces carry the basis through and degrade to an HONEST
    label, never an ambiguous dash.

FIXTURES ONLY. Nothing here asserts over the content of data/qledger/claims.jsonl
or grades.jsonl: those are append-only stores that grow every night, and a
historical assertion over them becomes false the moment a valid new row lands.
Every corpus in this file is hand-built in the test.
"""
from __future__ import annotations

import json

import pytest

from engine import qledger as q
from engine import experiments_registry as er
from engine.qledger_validity import FamilyProfile, may_pool_signed_excess


# --------------------------------------------------------------------------- #
# fixtures — synthetic corpora, never the live store
# --------------------------------------------------------------------------- #

def _claim(cid: str, family: str, direction, *, desk: str | None = None,
           asof: str = "2026-01-05", horizon_d: int = 5,
           is_placebo: bool = False) -> dict:
    return {
        "claim_id": cid,
        "claim_family": family,
        "desk": desk or family,
        "direction": direction,
        "horizon_d": horizon_d,
        "asof": asof,
        "is_placebo": is_placebo,
    }


def _grade(cid: str, excess: float | None, hit: bool | None,
           horizon_d: int = 5) -> dict:
    return {"claim_id": cid, "horizon_d": horizon_d, "excess": excess, "hit": hit}


@pytest.fixture
def mixed_corpus():
    """A family holding BOTH directions — the V1 hazard.

    Two bullish calls (one right, one wrong) and two bearish calls (one right,
    one wrong). The signed pool is (0.04 - 0.02 - 0.06 + 0.03)/4 = -0.0025 — a
    number that looks like underperformance and is really just the drift of the
    subject universe. The magnitude reading is (0.04+0.02+0.06+0.03)/4 = 0.0375.
    """
    claims = [
        _claim("m1", "mixedfam", 1, asof="2026-01-05"),
        _claim("m2", "mixedfam", 1, asof="2026-01-06"),
        _claim("m3", "mixedfam", -1, asof="2026-01-07"),
        _claim("m4", "mixedfam", -1, asof="2026-01-08"),
    ]
    grades = [
        _grade("m1", 0.04, True),     # bullish, right  -> +excess
        _grade("m2", -0.02, False),   # bullish, wrong  -> -excess
        _grade("m3", -0.06, True),    # bearish, RIGHT  -> -excess  <-- the trap
        _grade("m4", 0.03, False),    # bearish, wrong  -> +excess
    ]
    return claims, grades


@pytest.fixture
def single_direction_corpus():
    """A family holding one direction only — pooling signed excess is LEGAL here.

    Mirrors the live `altdata` family (directions == {1}). Pooled signed mean is
    (0.04 - 0.02 + 0.01)/3 = 0.01.
    """
    claims = [
        _claim("s1", "longonly", 1, asof="2026-02-02"),
        _claim("s2", "longonly", 1, asof="2026-02-03"),
        _claim("s3", "longonly", 1, asof="2026-02-04"),
    ]
    grades = [
        _grade("s1", 0.04, True),
        _grade("s2", -0.02, False),
        _grade("s3", 0.01, True),
    ]
    return claims, grades


@pytest.fixture
def salience_corpus():
    """direction == 0 everywhere: no sign convention exists, so the mean excess is
    a legitimate drift statistic and stays pooled. `hit` is undefined and null."""
    claims = [
        _claim("z1", "saliencefam", 0, asof="2026-03-01"),
        _claim("z2", "saliencefam", 0, asof="2026-03-02"),
    ]
    grades = [_grade("z1", 0.02, None), _grade("z2", -0.04, None)]
    return claims, grades


# --------------------------------------------------------------------------- #
# 1. the illegal figure is no longer published
# --------------------------------------------------------------------------- #

class TestMixedDirectionFamilyRefusesSignedPool:

    def test_excess_mean_is_withheld(self, mixed_corpus):
        claims, grades = mixed_corpus
        row = q._aggregate(claims, grades, "family", 5)["mixedfam"]
        assert row["excess_mean"] is None
        assert row["excess_basis"] == q.EXCESS_BASIS_MAGNITUDE

    def test_the_specific_illegal_value_appears_nowhere_in_the_payload(self, mixed_corpus):
        """The pooled signed mean is -0.0025. Serialise the whole emitted row and
        assert that number is not reachable under ANY key — a gate that merely
        renames the field would still leak it."""
        claims, grades = mixed_corpus
        row = q._aggregate(claims, grades, "family", 5)["mixedfam"]
        illegal = round(sum(g["excess"] for g in grades) / len(grades), 6)
        assert illegal == -0.0025                      # the value the old code shipped

        def _walk(node):
            if isinstance(node, dict):
                for v in node.values():
                    yield from _walk(v)
            elif isinstance(node, list):
                for v in node:
                    yield from _walk(v)
            else:
                yield node

        assert illegal not in [v for v in _walk(row) if isinstance(v, float)]

    def test_legal_replacements_are_published_instead(self, mixed_corpus):
        claims, grades = mixed_corpus
        row = q._aggregate(claims, grades, "family", 5)["mixedfam"]
        # magnitude form — mirrors engine.qledger._placebo_magnitude
        assert row["mean_abs_excess"] == 0.0375
        # per-direction split — the other legal reading
        assert row["excess_mean_by_direction"] == {
            "-1": round((-0.06 + 0.03) / 2, 6),
            "1": round((0.04 - 0.02) / 2, 6),
        }
        assert row["excess_directions"] == [-1, 1]

    def test_hit_rate_survives_untouched(self, mixed_corpus):
        """hit is direction-aware by construction, so it is NOT what V1 gates."""
        claims, grades = mixed_corpus
        row = q._aggregate(claims, grades, "family", 5)["mixedfam"]
        assert row["hit_rate"] == 0.5

    def test_desk_grouping_is_gated_too(self, mixed_corpus):
        """`_aggregate(by='desk')` groups on a DIFFERENT key than
        profile_families' default. A gate that only covered the family grouping
        would leave by_desk publishing the same illegal number."""
        claims, grades = mixed_corpus
        row = q._aggregate(claims, grades, "desk", 5)["mixedfam"]
        assert row["excess_mean"] is None
        assert row["excess_basis"] == q.EXCESS_BASIS_MAGNITUDE

    def test_desk_can_be_mixed_while_each_family_is_not(self):
        """One desk, two single-direction families. Each family may pool; the desk
        may NOT. Pins that the profile is built per GROUP KEY, not per family."""
        claims = [
            _claim("d1", "bulls", 1, desk="twoway", asof="2026-04-01"),
            _claim("d2", "bulls", 1, desk="twoway", asof="2026-04-02"),
            _claim("d3", "bears", -1, desk="twoway", asof="2026-04-03"),
            _claim("d4", "bears", -1, desk="twoway", asof="2026-04-04"),
        ]
        grades = [_grade("d1", 0.05, True), _grade("d2", -0.01, False),
                  _grade("d3", -0.05, True), _grade("d4", 0.02, False)]
        by_family = q._aggregate(claims, grades, "family", 5)
        by_desk = q._aggregate(claims, grades, "desk", 5)
        assert by_family["bulls"]["excess_mean"] == round((0.05 - 0.01) / 2, 6)
        assert by_family["bears"]["excess_mean"] == round((-0.05 + 0.02) / 2, 6)
        assert by_desk["twoway"]["excess_mean"] is None

    def test_string_directions_are_coerced_like_the_contract_does(self):
        """Stores hold both 1 and '1'. A gate that only understood ints would read
        this family as direction-homogeneous and publish the illegal pool."""
        claims = [_claim("t1", "strfam", "1", asof="2026-05-01"),
                  _claim("t2", "strfam", "-1", asof="2026-05-02")]
        grades = [_grade("t1", 0.03, True), _grade("t2", -0.03, True)]
        row = q._aggregate(claims, grades, "family", 5)["strfam"]
        assert row["excess_mean"] is None
        assert row["excess_mean_by_direction"] == {"-1": -0.03, "1": 0.03}


# --------------------------------------------------------------------------- #
# 2. the legal cases must survive — a gate that refuses everything is useless
# --------------------------------------------------------------------------- #

class TestLegalFamiliesAreUnchanged:

    def test_single_direction_family_keeps_its_signed_mean(self, single_direction_corpus):
        claims, grades = single_direction_corpus
        row = q._aggregate(claims, grades, "family", 5)["longonly"]
        assert row["excess_mean"] == 0.01
        assert row["excess_basis"] == q.EXCESS_BASIS_POOLED

    def test_single_direction_value_matches_the_pre_gate_arithmetic(
            self, single_direction_corpus):
        """Bit-identical to `round(excess_sum / n_obs, 6)` including the historical
        `float(excess or 0.0)` convention — the gate must not silently change the
        denominator for families it permits."""
        claims, grades = single_direction_corpus
        grades = grades + [_grade("s3", None, None)]      # a null-excess row
        claims = claims + [_claim("s4", "longonly", 1, asof="2026-02-05")]
        grades = grades + [_grade("s4", None, None)]
        row = q._aggregate(claims, grades, "family", 5)["longonly"]
        n_obs = len(grades)
        pre_gate = round(sum(float(g["excess"] or 0.0) for g in grades) / n_obs, 6)
        assert row["n_obs"] == n_obs
        assert row["excess_mean"] == pre_gate

    def test_single_direction_family_omits_the_split_keys(self, single_direction_corpus):
        """The split is the REPLACEMENT for a refused pool; its presence is itself
        the marker that the pooled figure was withheld."""
        claims, grades = single_direction_corpus
        row = q._aggregate(claims, grades, "family", 5)["longonly"]
        assert "excess_mean_by_direction" not in row
        assert "excess_directions" not in row

    def test_salience_only_family_still_pools(self, salience_corpus):
        """directions == {0}: no sign convention to violate (V1's own carve-out)."""
        claims, grades = salience_corpus
        row = q._aggregate(claims, grades, "family", 5)["saliencefam"]
        assert row["excess_mean"] == round((0.02 - 0.04) / 2, 6)
        assert row["excess_basis"] == q.EXCESS_BASIS_POOLED
        assert row["hit_rate"] is None          # hit is undefined for direction==0

    def test_magnitude_leg_skips_null_excess_like_placebo_magnitude(self):
        """`mean_abs_excess` must use the SAME convention as
        `_placebo_magnitude` (null excess skipped, not counted as a zero move) or
        the two sides of the placebo duel are not comparable."""
        claims = [_claim("n1", "nullfam", 1, asof="2026-06-01"),
                  _claim("n2", "nullfam", 1, asof="2026-06-02")]
        grades = [_grade("n1", 0.04, True), _grade("n2", None, None)]
        row = q._aggregate(claims, grades, "family", 5)["nullfam"]
        assert row["mean_abs_excess"] == 0.04          # not 0.02
        assert row["n_obs"] == 2

    def test_no_grades_at_this_horizon_yields_no_row(self, mixed_corpus):
        claims, grades = mixed_corpus
        assert q._aggregate(claims, grades, "family", 63) == {}


# --------------------------------------------------------------------------- #
# 3. the gate is DELEGATED, not re-derived
# --------------------------------------------------------------------------- #

class TestGateIsDelegatedToTheContract:

    def test_emitter_follows_the_contract_when_the_contract_is_mutated(
            self, single_direction_corpus, monkeypatch):
        """Mutating `may_pool_signed_excess` must change what _aggregate emits.
        If it does not, the emitter holds a SECOND copy of the invariant and the
        two are free to drift."""
        claims, grades = single_direction_corpus
        assert q._aggregate(claims, grades, "family", 5)["longonly"]["excess_mean"] == 0.01
        monkeypatch.setattr(q, "may_pool_signed_excess", lambda prof: False)
        row = q._aggregate(claims, grades, "family", 5)["longonly"]
        assert row["excess_mean"] is None
        assert row["excess_basis"] == q.EXCESS_BASIS_MAGNITUDE

    def test_contract_still_agrees_with_the_live_reading(self, mixed_corpus):
        """The emitter's verdict for the fixture family equals the contract's own,
        computed independently here."""
        claims, _ = mixed_corpus
        prof = FamilyProfile(family="mixedfam")
        for c in claims:
            prof.n_claims += 1
            prof.directions.add(int(c["direction"]))
        assert may_pool_signed_excess(prof) is False

    def test_unprofiled_group_fails_closed(self, single_direction_corpus, monkeypatch):
        """If the group cannot be profiled at all, refuse the signed pool rather
        than publish an uninterpretable number."""
        claims, grades = single_direction_corpus
        monkeypatch.setattr(q, "_group_profiles", lambda claims, by: {})
        row = q._aggregate(claims, grades, "family", 5)["longonly"]
        assert row["excess_mean"] is None
        assert row["excess_basis"] == q.EXCESS_BASIS_MAGNITUDE
        assert row["excess_directions"] == []

    def test_placebo_claims_do_not_decide_a_real_family_profile(self):
        """The placebo tape is a control arm. A synthetic bearish placebo row must
        not flip a real long-only family into 'mixed' and suppress a legal mean."""
        claims = [
            _claim("p1", "longonly", 1, asof="2026-07-01"),
            _claim("p2", "longonly", 1, asof="2026-07-02"),
            _claim("px", "longonly", -1, asof="2026-07-03", is_placebo=True),
        ]
        grades = [_grade("p1", 0.04, True), _grade("p2", -0.02, False),
                  _grade("px", -0.09, True)]
        row = q._aggregate(claims, grades, "family", 5)["longonly"]
        assert row["excess_basis"] == q.EXCESS_BASIS_POOLED
        assert row["n_obs"] == 2                       # placebo grade excluded
        assert row["excess_mean"] == round((0.04 - 0.02) / 2, 6)


# --------------------------------------------------------------------------- #
# 4. downstream: the payload and the two human-reachable surfaces
# --------------------------------------------------------------------------- #

def _track_record(fam: str, row: dict, *, placebo_abs: float | None = 0.0663) -> dict:
    """Minimal track_record.json shaped payload carrying one family at 5d."""
    return {
        "generated_at": "2026-08-12T00:00:00+00:00",
        "grade_horizons": [5, 21, 63],
        "by_desk": {},
        "by_family": {fam: {"5": row}},
        "placebo_magnitude": {"5": {"covered_ticker": {"mean_abs_excess": placebo_abs}}},
        "promotion_readiness": {
            fam: {"5": {
                "n_dates": row["n_dates"], "needed": 25,
                "wilson_ci_low": row["wilson_ci_low"],
                "hit_rate": row["hit_rate"],
                "excess_mean": row["excess_mean"],
                "mean_abs_excess": row["mean_abs_excess"],
                "excess_basis": row["excess_basis"],
                "excess_mean_by_direction": row.get("excess_mean_by_direction"),
                "ready": False, "approaching": False,
                "projected_ready_date": None, "reason": "fixture",
            }},
            "_duel_context": {fam: {
                "challenger_excess_mean_5d": row["excess_mean"],
                "challenger_abs_excess_5d": row["mean_abs_excess"],
                "challenger_excess_basis_5d": row["excess_basis"],
                "placebo_covered_abs_excess_5d": placebo_abs,
                "n_dates_5d": row["n_dates"],
                "wilson_ci_low_5d": row["wilson_ci_low"],
            }},
        },
    }


class TestEmittedPayload:

    def test_row_is_json_serialisable(self, mixed_corpus):
        claims, grades = mixed_corpus
        payload = q._aggregate(claims, grades, "family", 5)
        assert json.loads(json.dumps(payload)) == payload


class TestAdminExperimentsSurface:
    """`_refresh_qledger_promotion` is the last hop before admin/experiments.py."""

    def _render(self, monkeypatch, tr, fam):
        monkeypatch.setattr(
            er, "_read_json",
            lambda rel: tr if rel == "site/qledger/track_record.json" else None)
        return er._refresh_qledger_promotion({"claim_family": fam, "next_step": "seed"})

    def test_mixed_family_never_renders_a_signed_excess(self, mixed_corpus, monkeypatch):
        claims, grades = mixed_corpus
        row = q._aggregate(claims, grades, "family", 5)["mixedfam"]
        out = self._render(monkeypatch, _track_record("mixedfam", row), "mixedfam")
        assert "-0.25%" not in out["state"]            # the old illegal figure
        assert "excess=-" not in out["state"]

    def test_mixed_family_degrades_to_an_honest_label_not_a_dash(
            self, mixed_corpus, monkeypatch):
        """A bare 'n/a' reads as 'not measured yet' and is exactly the ambiguous
        dash engine/neuralweb/mastermind_context refuses to print."""
        claims, grades = mixed_corpus
        row = q._aggregate(claims, grades, "family", 5)["mixedfam"]
        out = self._render(monkeypatch, _track_record("mixedfam", row), "mixedfam")
        assert "excess=n/a" not in out["state"]
        assert "|3.75%|" in out["state"]               # the magnitude that IS legal
        assert "mixed-direction family" in out["state"]

    def test_mixed_family_duel_is_magnitude_vs_magnitude(self, mixed_corpus, monkeypatch):
        """The placebo side of the duel has always been a |excess|; the challenger
        side must match it, not be a signed mean."""
        claims, grades = mixed_corpus
        row = q._aggregate(claims, grades, "family", 5)["mixedfam"]
        out = self._render(monkeypatch, _track_record("mixedfam", row), "mixedfam")
        duel = out["next_step"].splitlines()[0]
        assert "challenger |excess|=3.75%" in duel
        assert "placebo |excess|=6.63%" in duel
        assert "excess_mean" not in duel

    def test_single_direction_family_renders_exactly_as_before(
            self, single_direction_corpus, monkeypatch):
        claims, grades = single_direction_corpus
        row = q._aggregate(claims, grades, "family", 5)["longonly"]
        out = self._render(monkeypatch, _track_record("longonly", row), "longonly")
        assert "excess=1.00%" in out["state"]
        assert "challenger excess_mean=1.00%" in out["next_step"].splitlines()[0]

    def test_absent_excess_entirely_says_not_measured_not_na(self, monkeypatch):
        """Neither leg available: still a plain-word label, never a bare dash."""
        row = {"n_obs": 0, "n_dates": 0, "hit_rate": None, "excess_mean": None,
               "mean_abs_excess": None, "excess_basis": q.EXCESS_BASIS_MAGNITUDE,
               "wilson_ci_low": None, "state": q.STATE_UNGRADED}
        out = self._render(monkeypatch, _track_record("blank", row, placebo_abs=None),
                           "blank")
        assert "not measured yet" in out["state"]
        # scoped to the EXCESS leg: `CI-low=n/a` is a different (and unambiguous)
        # field, out of scope for V1 and deliberately left alone.
        excess_leg = out["state"].split("excess=", 1)[1]
        assert "n/a" not in excess_leg
