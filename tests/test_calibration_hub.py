"""Calibration Hub (engine/calibration_hub.py) — the unified observability surface.

Verifies the per-desk health classification (cold / weak / inverted / calibrated), the
conviction-monotonicity read, the Trial Ledger roll-up, and that build/render degrade
gracefully on missing inputs.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import calibration_hub as ch  # noqa: E402
from engine.trial_ledger import TrialLedger  # noqa: E402


def _new_root():
    return Path(tempfile.mkdtemp())


def _write_track(root, slug, track):
    d = root / "data" / slug
    d.mkdir(parents=True, exist_ok=True)
    (d / "track_record.json").write_text(json.dumps(track))


def _bucket(n, hits, dir_acc=None):
    return {"n": n, "hits": hits, "misses": n - hits,
            "hit_rate": round(hits / n, 3) if n else None,
            "dir_accuracy": dir_acc}


def _null(**kw):
    """A placebo baseline as engine.desk_placebo would return it."""
    base = {"available": True, "reason": "", "mix_source": "scored", "n": 20, "n_decided": 20,
            "coverage": 1.0, "unreconstructable": 0, "null_hit_rate": 0.50, "null_dir_rate": 0.50,
            "p_hit": 0.001, "p_dir": None, "independent_blocks": 20,
            "by_kind": {"rel_return": {"n": 20, "null_hit_rate": 0.50, "null_dir_rate": 0.50}}}
    base.update(kw)
    return base


def test_cold_desk_when_sample_small():
    root = _new_root()
    _write_track(root, "ai_desk", {"scored_total": 3, "open": 5, "overall": _bucket(3, 2)})
    s = ch.build(root)
    ai = next(d for d in s["desks"] if d["slug"] == "ai_desk")
    assert ai["health"] == "cold" and ai["scored"] == 3


def test_weak_desk_below_coinflip():
    root = _new_root()
    _write_track(root, "ai_desk", {"scored_total": 20, "open": 0,
                                   "overall": _bucket(20, 7),  # 35% hit
                                   "by_conviction": {"high": _bucket(8, 3), "low": _bucket(8, 3)}})
    s = ch.build(root)
    ai = next(d for d in s["desks"] if d["slug"] == "ai_desk")
    assert ai["health"] == "weak"


def test_inverted_conviction_flagged():
    root = _new_root()
    _write_track(root, "ai_desk", {"scored_total": 20, "open": 0,
                                   "overall": _bucket(20, 12),
                                   # high hits LESS than low → conviction means nothing
                                   "by_conviction": {"high": _bucket(10, 4), "low": _bucket(10, 8)}})
    s = ch.build(root)
    ai = next(d for d in s["desks"] if d["slug"] == "ai_desk")
    assert ai["health"] == "inverted"
    assert ai["conviction_monotone"] is False


def test_calibrated_requires_clearing_the_measured_null():
    """A desk clears its OWN empirical null by the pre-registered margin, at the corrected
    alpha, over enough non-overlapping windows — then, and only then, it is promoted."""
    track = {"scored_total": 20, "open": 0, "overall": _bucket(20, 17, dir_acc=0.7),
             "by_conviction": {"high": _bucket(10, 9), "low": _bucket(10, 8)},
             "by_regime": {"Goldilocks": _bucket(12, 8)}}
    health, note = ch._desk_health(track, _null(), p_hit_adj=0.004, p_dir_adj=0.03)
    assert health == "calibrated"
    assert "clears its own null by +35pp" in note
    assert "conviction ordering holds" in note


def test_not_falsified_rate_is_judged_against_its_own_null_not_one_half():
    """The regression this gate exists for: AI Desk's live reading — 85% not-falsified over
    13 calls — is ~83% by chance on those very falsifiers, so it is NOT an edge. The old
    0.5 'coin-flip' bar promoted exactly this to 'calibrated'."""
    track = {"scored_total": 13, "open": 32, "overall": _bucket(13, 11, dir_acc=0.846),
             "by_conviction": {"high": _bucket(0, 0), "medium": _bucket(0, 0),
                               "low": _bucket(13, 11, dir_acc=0.846)}}
    null = _null(n=13, n_decided=13, null_hit_rate=0.83, null_dir_rate=0.50,
                 independent_blocks=1, p_hit=0.674, p_dir=0.011,
                 by_kind={"rel_return": {"n": 11, "null_hit_rate": 0.87, "null_dir_rate": 0.50},
                          "level": {"n": 2, "null_hit_rate": 0.60, "null_dir_rate": 0.50}})
    health, note = ch._desk_health(track, null, p_hit_adj=0.674, p_dir_adj=0.011)
    assert health == "unproven"
    assert "83%" in note and "no separation" in note
    # the honest reading points at the metric that actually separates
    assert "Direction" in note and "not a result" in note


def test_no_surface_calls_one_half_the_coin_flip_null():
    """0.5 survives only as a demotion floor. The phrase that named it the null is the exact
    mislabel this gate exists to remove — keep it out of the module (ratchet guard)."""
    src = (Path(__file__).resolve().parent.parent / "engine" / "calibration_hub.py").read_text()
    assert "below coin-flip" not in src


def test_board_track_is_not_promoted_on_a_bare_half():
    """The board tracks carried the same unearned promotion: any hit-rate over one-half read
    'calibrated'. That endpoint's null IS near one-half (beat SPY over 21 days), but a point
    estimate over it is still not a track record until the pre-registered floor is met."""
    root = _new_root()

    def row(n, hr):
        (root / "site" / "factordata").mkdir(parents=True, exist_ok=True)
        (root / "site" / "factordata" / "us_board_track.json").write_text(json.dumps(
            {"board_dates_total": 10, "graded_rows_total": n,
             "per_horizon": {"h21": {"buy_lane": {"vs_spy": {"n": n, "hit_rate": hr}}}}}))
        return ch._standout_track_row("US", "site/factordata/us_board_track.json", "US", root)

    assert row(12, 0.58)["health"] == "unproven"          # over half, under the floor
    assert "floor of 25" in row(12, 0.58)["health_note"]
    assert row(12, 0.40)["health"] == "weak"              # under half still demotes
    assert row(40, 0.58)["health"] == "calibrated"        # past the floor
    assert row(4, 0.90)["health"] == "cold"


def test_overlapping_windows_block_promotion():
    """45 theses logged across three weeks and graded over the following month are not 45
    independent looks at the tape. Raw count clears every other bar; independence does not."""
    track = {"scored_total": 20, "open": 0, "overall": _bucket(20, 17, dir_acc=0.7),
             "by_conviction": {"high": _bucket(10, 9), "low": _bucket(10, 8)}}
    health, note = ch._desk_health(track, _null(independent_blocks=2), p_hit_adj=0.004)
    assert health == "unproven"
    assert "overlap in time" in note and "2 independent windows" in note


def test_directionally_wrong_desk_is_inverted_not_calibrated():
    """Stock Desk's live shape: a lenient not-falsified rate alongside leans that point the
    wrong way. Direction is a genuinely directional metric, so it is demoted against its
    measured null (falling back to one-half only when unmeasured)."""
    track = {"scored_total": 45, "open": 96, "overall": _bucket(45, 29, dir_acc=0.333),
             "by_conviction": {"medium": _bucket(3, 3), "low": _bucket(42, 26)}}
    health, note = ch._desk_health(track, _null(n=16, n_decided=45, coverage=0.356,
                                                available=False, reason="partial coverage",
                                                null_hit_rate=0.84, null_dir_rate=0.539,
                                                p_hit=None, independent_blocks=2), None)
    assert health == "inverted"
    assert "WRONG WAY" in note
    # a 3-call medium tier is not evidence that conviction orders anything
    assert "conviction ordering untested" in note


def test_single_tier_desk_never_claims_conviction_ordering_holds():
    """Every desk to date logs one conviction tier, so the monotonicity check cannot fail —
    it returned None and the note asserted 'conviction ordering holds' anyway. An untested
    property is reported as untested."""
    read = ch._conviction_read({"high": _bucket(0, 0), "medium": _bucket(0, 0),
                                "low": _bucket(13, 11)})
    assert read["verdict"] is None
    assert read["note"] == "conviction ordering untested — all 13 calls are single-tier (low 13)"
    assert "holds" not in read["note"]


def test_tiny_conviction_tier_is_not_evidence():
    """Stock Desk's live split — 3 medium calls at 100% next to 42 low calls — is not a
    demonstration that conviction orders anything."""
    read = ch._conviction_read({"high": _bucket(0, 0), "medium": _bucket(3, 3),
                                "low": _bucket(42, 26)})
    assert read["verdict"] is None
    assert "only 1 of 3 tiers has 5+ calls" in read["note"]
    assert read["tiers"] == {"high": 0, "medium": 3, "low": 42}


def test_conviction_ordering_reported_only_once_tested():
    read = ch._conviction_read({"high": _bucket(10, 8), "medium": _bucket(0, 0),
                                "low": _bucket(10, 5)})
    assert read["verdict"] is True
    assert "conviction ordering holds" in read["note"] and "n=10" in read["note"]


def test_health_note_never_asserts_an_untested_property():
    """Guards the exact defect: an untested conviction ordering must not read as a held one
    anywhere in the emitted row."""
    root = _new_root()
    _write_track(root, "ai_desk", {"scored_total": 13, "open": 0,
                                   "overall": _bucket(13, 11, dir_acc=0.846),
                                   "by_conviction": {"low": _bucket(13, 11)}})
    s = ch.build(root)
    ai = next(d for d in s["desks"] if d["slug"] == "ai_desk")
    assert ai["conviction_monotone"] is None
    assert "conviction ordering untested" in ai["health_note"]
    assert "conviction ordering holds" not in ai["health_note"]


def test_every_pooled_desk_is_governed():
    """A desk that grades theses but is missing from _DESKS accrues a track record no one
    adjudicates. thematic_desk was exactly that — live n=21, hit-rate 0.571 against
    directional accuracy 0.429, and no health verdict emitted anywhere."""
    from engine.desk_scorer import POOL_DESKS

    governed = {slug for _, slug in ch._DESKS}
    missing = sorted(set(POOL_DESKS) - governed)
    assert not missing, f"pooled desks invisible to the promotion gate: {missing}"


def test_directionally_wrong_desk_is_caught_without_a_placebo():
    """thematic_desk's live shape: its falsifier kind (theme_rel_return) is not sweepable
    yet, so no null is measured — but dir_accuracy IS a directional metric, so the one-half
    fallback still catches leans that point the wrong way. A missing null must never
    upgrade a desk."""
    track = {"scored_total": 21, "open": 0,
             "overall": _bucket(21, 12, dir_acc=0.429),
             "by_conviction": {"low": _bucket(21, 12)}}
    null = _null(available=False, reason="no sweepable kind", n=0, n_decided=21,
                 coverage=None, null_hit_rate=None, null_dir_rate=None,
                 p_hit=None, independent_blocks=0, by_kind={})
    health, note = ch._desk_health(track, null, None)
    assert health == "inverted"
    assert "a coin flip" in note          # the fallback is named honestly, not as a measurement
    assert "no placebo baseline" in note


def test_promotion_gate_bars_are_published_with_the_verdicts():
    """Nulls and bars get printed, not implied — a reader can audit the gate from the JSON."""
    root = _new_root()
    gate = ch.build(root)["promotion_gate"]
    assert gate["min_sample"] == ch._MIN_SAMPLE
    assert gate["min_independent_blocks"] == ch._MIN_INDEPENDENT_BLOCKS
    assert gate["alpha"] == ch._PROMOTE_ALPHA and "Holm" in gate["alpha_correction"]
    assert "NOT-FALSIFIED" in gate["note"]


def test_loops_live_vs_cold_count():
    root = _new_root()
    _write_track(root, "ai_desk", {"scored_total": 20, "overall": _bucket(20, 13),
                                   "by_conviction": {"high": _bucket(10, 8), "low": _bucket(10, 5)}})
    _write_track(root, "radar", {"scored_total": 2, "overall": _bucket(2, 1)})  # cold
    s = ch.build(root)
    assert s["loops"]["live"] == 1            # ai_desk
    assert s["loops"]["cold"] == len(s["desks"]) - 1   # radar + the 4 absent desks


def test_trial_ledger_rollup():
    root = _new_root()
    led = TrialLedger(root / "data" / "trial_ledger.jsonl", family="vector")
    led.log_grid([{"v": i} for i in range(4)])
    led.log_declared_budget(65)
    led.log_declared_budget(8, family="tactical")
    s = ch.build(root)
    tl = {f["family"]: f for f in s["trial_ledger"]["families"]}
    assert tl["vector"]["effective_n"] == 65 and tl["vector"]["itemized"] == 4
    assert tl["tactical"]["effective_n"] == 8
    assert s["trial_ledger"]["total_families"] == 2


def test_run_persists_json_and_html():
    root = _new_root()
    _write_track(root, "ai_desk", {"scored_total": 20, "overall": _bucket(20, 13),
                                   "by_conviction": {"high": _bucket(10, 8), "low": _bucket(10, 5)}})
    s = ch.run(root=root, persist=True)
    assert (root / "data" / "calibration" / "summary.json").exists()
    html = (root / "site" / "calibration.html").read_text()
    assert "Calibration Hub" in html and "AI Desk" in html
    assert ch.render_markdown(s).startswith("# Calibration Hub")


def test_build_degrades_with_no_inputs():
    root = _new_root()
    s = ch.build(root)                          # nothing present
    assert s["loops"]["live"] == 0
    assert all(d["health"] == "cold" for d in s["desks"])
    assert s["trial_ledger"]["families"] == []
