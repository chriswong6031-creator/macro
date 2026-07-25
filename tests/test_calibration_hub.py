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


# --------------------------------------------------------------------------- #
# desk family — a desk absent from _DESKS is ungoverned: no null, no verdict, no row
# --------------------------------------------------------------------------- #
def test_every_pooled_desk_is_governed_by_the_gate():
    """The regression this guards: thematic_desk and narrative_brain were first-class in
    engine.desk_scorer.POOL_DESKS — pooled into desk weights — while being invisible on the
    Calibration Hub, so the promotion gate computed no null and emitted no verdict for them.
    A desk the system trusts enough to pool is a desk the gate must judge."""
    from engine.desk_scorer import POOL_DESKS

    governed = {slug for _, slug in ch._DESKS}
    assert set(POOL_DESKS) - governed == set()
    assert "master_brain" in governed          # graded by engine/master_brain_scorer.py
    assert len({slug for _, slug in ch._DESKS}) == len(ch._DESKS)     # no duplicate slugs
    assert all(label and label[0].isupper() for label, _ in ch._DESKS)


def test_thematic_desks_directional_divergence_is_caught():
    """thematic_desk's live shape, and the reason it had to be governed: 57% not-falsified
    (a lenient endpoint) alongside 43% directional accuracy. The lean points the wrong way,
    and no placebo is available to soften it — one-half is the fallback bar for direction
    precisely because dir_accuracy IS directional."""
    root = _new_root()
    _write_track(root, "thematic_desk", {
        "scored_total": 21, "open": 98,
        "overall": _bucket(21, 12, dir_acc=0.429),
        "by_conviction": {"high": _bucket(0, 0), "medium": _bucket(0, 0),
                          "low": _bucket(21, 12, dir_acc=0.429)}})
    s = ch.build(root)
    td = next(d for d in s["desks"] if d["slug"] == "thematic_desk")
    assert td["name"] == "Thematic Desk"
    assert td["health"] == "inverted"
    assert "WRONG WAY" in td["health_note"]
    # the lenient endpoint must not be allowed to rescue it
    assert "57%" in td["health_note"] and "43%" in td["health_note"]
    assert td["health"] != "calibrated"


def test_cold_desk_is_visible_rather_than_absent():
    """master_brain is n=2 — far too cold to mean anything, which is exactly why it belongs
    on the surface saying so, rather than being silently omitted."""
    root = _new_root()
    _write_track(root, "master_brain", {"scored_total": 2, "open": 7,
                                        "overall": _bucket(2, 2, dir_acc=1.0)})
    s = ch.build(root)
    mb = next(d for d in s["desks"] if d["slug"] == "master_brain")
    assert mb["name"] == "Master Brain" and mb["health"] == "cold"
    assert "only 2 scored" in mb["health_note"]
    # a desk that produces nothing at all still gets an honest row
    nb = next(d for d in s["desks"] if d["slug"] == "narrative_brain")
    assert nb["health"] == "cold" and nb["scored"] == 0


# --------------------------------------------------------------------------- #
# Holm family — the correction reported must be the correction applied
# --------------------------------------------------------------------------- #
def test_promotion_eligibility_is_the_holm_family():
    assert ch._promotion_eligible({"overall": _bucket(20, 15)}, _null()) is True
    # below the sample floor the alpha bar is never consulted → not a test
    assert ch._promotion_eligible({"overall": _bucket(2, 2)}, _null()) is False
    # no null covering every graded call → 'unproven' before alpha → not a test
    assert ch._promotion_eligible({"overall": _bucket(20, 15)},
                                  _null(available=False, reason="partial")) is False
    assert ch._promotion_eligible({}, _null()) is False


def test_a_cold_desk_does_not_inflate_the_correction_on_a_tested_one():
    """Holm controls the chance of a false PROMOTION. A cold desk cannot be promoted, so it
    makes no test and must not cost an eligible desk power — otherwise merely adding a desk
    to _DESKS tightens the bar on desks whose evidence did not change.

    Built end-to-end so master_brain really does carry a p-value: prices, a ledger, and a
    scored file, differing from ai_desk only in sample size."""
    import pandas as pd

    root = _new_root()
    d = root / "data" / "yahoo"
    d.mkdir(parents=True, exist_ok=True)
    idx = pd.bdate_range("2020-01-01", periods=500)
    pd.DataFrame({"close": [100 * (1.001 ** i) for i in range(500)]},
                 index=idx).to_parquet(d / "UP.parquet")
    pd.DataFrame({"close": [100.0] * 500}, index=idx).to_parquet(d / "FLAT.parquet")

    def _desk(slug, n):
        p = root / "data" / slug
        p.mkdir(parents=True, exist_ok=True)
        (p / "theses.jsonl").write_text("".join(json.dumps(
            {"id": f"{slug}{i}", "state_asof": "2021-01-04", "check_by": "2021-02-01",
             "falsifier": {"check": {"kind": "rel_return", "subject_ticker": "UP",
                                     "vs": "FLAT", "op": "<", "threshold": -0.05}}}) + "\n"
            for i in range(n)))
        (p / "scored.jsonl").write_text("".join(json.dumps(
            {"id": f"{slug}{i}", "outcome": "hit", "directionally_correct": True}) + "\n"
            for i in range(n)))
        _write_track(root, slug, {"scored_total": n, "open": 0,
                                  "overall": _bucket(n, n, dir_acc=1.0)})

    _desk("ai_desk", 20)                 # eligible: clears _MIN_SAMPLE
    _desk("master_brain", 2)             # cold: below it
    s = ch.build(root)
    ai = next(x for x in s["desks"] if x["slug"] == "ai_desk")
    mb = next(x for x in s["desks"] if x["slug"] == "master_brain")

    assert mb["health"] == "cold" and mb["p_hit"] is not None   # a real p-value exists...
    assert mb["p_hit_holm"] is None                             # ...but it is not in the family
    assert s["promotion_gate"]["holm_family_hit"] == 1
    # the tested desk is corrected as a family of one — unchanged by the cold desk's presence
    assert ai["p_hit_holm"] == ai["p_hit"]


def test_gate_reports_the_correction_actually_applied_not_the_desk_count():
    """The note said 'correcting for the 6 desks tested' while Holm's family was 1 — claiming
    more multiplicity correction than was applied overstates rigor, which is the one direction
    this gate exists to police."""
    root = _new_root()
    s = ch.build(root)                                    # nothing present → no desk eligible
    gate = s["promotion_gate"]
    assert gate["desks_tracked"] == len(ch._DESKS)
    assert gate["holm_family_hit"] == 0 and gate["holm_family_dir"] == 0
    assert str(len(ch._DESKS)) in gate["alpha_correction"] and "eligible" in gate["alpha_correction"]

    # and the per-desk note quotes the family size, not len(_DESKS)
    track = {"scored_total": 20, "open": 0, "overall": _bucket(20, 17, dir_acc=0.7),
             "by_conviction": {"high": _bucket(10, 9), "low": _bucket(10, 8)}}
    _, note = ch._desk_health(track, _null(p_hit=0.3), p_hit_adj=0.30, family_n=3)
    assert "3 desks eligible for the test" in note
    assert f"{len(ch._DESKS)} desks tested" not in note


def test_holm_stays_monotone_across_the_larger_family():
    """Sanity on the corrected p-values themselves once every tracked desk is in play: the
    untested desks drop out, and the tested ones step down monotonically under the cap."""
    from engine import desk_placebo as dp

    pvals = {slug: None for _, slug in ch._DESKS}
    pvals.update({"ai_desk": 0.001, "stock_desk": 0.01, "thematic_desk": 0.02,
                  "master_brain": 0.04, "altdata": 0.5, "radar": 0.9})
    adj = dp.holm_adjust(pvals)
    assert adj.keys() == pvals.keys()                            # every desk still keyed
    tested = [adj[s] for s, p in sorted(pvals.items(), key=lambda kv: (kv[1] is None, kv[1]))
              if p is not None]
    assert tested == sorted(tested)                              # monotone step-down
    assert all(0.0 <= v <= 1.0 for v in tested)                  # capped
    assert adj["ai_desk"] == 0.006                               # 6 in the family x 0.001
    assert adj["radar"] == 1.0                                   # capped, not 0.9 x 1
    assert adj["policy_intent"] is None                          # never tested → no adjusted p


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
