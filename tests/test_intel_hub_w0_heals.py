"""Intelligence Hub — Wave 0 measurement-integrity heals + the policy-vote A7 heal.

Program: research/INTEL_HUB_LOBE_AUDIT_AND_UPGRADE_MASTERPLAN_BY_FABLE.md §4 / Appendix A.
One section per defect, each named with its register key:

  ITEM 1 (D13) — the policy desk's LLM-originated lean voted in BOTH scored aggregations
                 (net_confirm/agreement/conf_bonus → composite; lag_up → gap_mult →
                 opportunity). Operator ruling 2026-08-08 Option A: remove the vote, keep
                 the facet. DNR:KILL-LLM-ORIGINATION / constitution A7.
  ITEM 2 (D22) — snapshot rows carried no rank / cohort / hero-rejection provenance, so
                 "did Command win?" and "how often does the hero gate bar a #1 name?" were
                 unanswerable from 38 accrued nights.
  ITEM 3 (D2)  — the governor read data/radar/radar_ic.json, which engine-render never
                 commits, and degraded silently to identity trust on a stale/absent input.
  ITEM 4 (D21) — asof-or-BEFORE price reads were unbounded: a stalled series graded against
                 an arbitrarily old close on both legs of _fwd_rel.
  ITEM 5 (D20) — the ledger skipped 2026-08-04/07/08 with zero alarms while the page read
                 fresh, and 20d coverage sat at 6.2% printed nowhere.
  ITEM 6 (D3)  — special_situations.json could go days stale and the catalyst panel looked
                 identical.
  ITEM 7 (D4)  — the Quiver `twitter` dataset, dead since the 2023 X API shutdown, was still
                 listed as an active data lane.

Every ::warning added by this wave is asserted through capsys with a line-START check —
never caplog. GitHub only parses a workflow command when `::` is the first thing on the
line, and every builder here logs with a level-prefixing format, so an annotation routed
through a logger is silently dropped (tests/test_gh_annotation_line_start.py).
"""
from __future__ import annotations

import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402
import pytest  # noqa: E402

from engine import ai_desk as _desk  # noqa: E402
from engine import altdata as A  # noqa: E402
from engine import desk_scorer as DS  # noqa: E402
from engine import hub_track_record as H  # noqa: E402
from engine import intel_hub as IH  # noqa: E402
from engine import intelligence as I  # noqa: E402
from engine import signal_governor as G  # noqa: E402
from engine import trajectory as _trajectory  # noqa: E402
from scripts import build_intel_hub as BIH  # noqa: E402

_TODAY = date(2026, 6, 20)


def _annotations(capsys) -> list[str]:
    """Every captured stdout line that GitHub would actually parse as a workflow command.

    The line-START check is the whole point: a `::warning` emitted through a logger arrives
    as "WARNING ::warning …" and GitHub drops it, so a test that merely searched for the
    substring would pass on a dead annotation."""
    return [ln for ln in capsys.readouterr().out.splitlines() if ln.startswith("::")]


# =========================================================================== #
# ITEM 1 (D13) — policy casts no vote in any score
# =========================================================================== #
@pytest.fixture
def _no_velocity(monkeypatch):
    # Keep every W0 synthetic name away from the live roster, price store, and
    # entry-gate snapshot.  These tests exercise dossier/hero bookkeeping; the
    # universe gate has its own dedicated suite.  Reading current repo artifacts
    # here made the answer depend on whether a fixture ticker (notably DDD) had
    # accrued a real gate verdict since the test was written.
    monkeypatch.setattr(
        IH,
        "_scope_universe",
        lambda tickers, _root: (dict(tickers), {"mode": "synthetic"}, lambda _t: True),
    )
    monkeypatch.setattr(IH, "_load_gate_index", lambda: {})
    monkeypatch.setattr(_trajectory, "_yahoo_closes", lambda _ticker, _root: None)
    monkeypatch.setattr(IH, "load_velocity", lambda tickers, today, persist=True: {})


def _bundle_for_policy_test():
    """A four-desk bullish name with a REAL brain block (so brain.priority is non-zero and
    `base` takes the priority short-circuit, exactly as production does)."""
    news = {"ACME": {"n_recent": 3, "sentiment_lean": "pos", "sentiment_score": 0.5,
                     "sentiment_strength": 0.5, "baskets": [], "sectors": ["XLK"]}}
    alt = [{"ticker": "ACME", "signal_score": 78, "action": "BUY", "channels": ["insider"]}]
    radar = [{"ticker": "ACME", "state": "POSITIVE_DIVERGENCE", "edge_score": 72,
              "lifecycle": "forming"}]
    standout = [{"ticker": "ACME", "label": "UPTREND", "conviction": 0.7}]
    return I.build(news, alt, None, radar, standout, today=_TODAY)


def _policy(lean: str | None):
    if lean is None:
        return None
    return {"theses": [{"subject": "ACME", "lean": lean, "conviction": "high",
                        "actor": "admin", "thesis": "chips"}]}


def _hub_for(lean: str | None):
    return IH.build(_bundle_for_policy_test(), _policy(lean), {}, today=_TODAY)


def _acme(hub):
    return next(d for d in hub["command"] if d["ticker"] == "ACME")


def test_policy_lean_never_moves_a_score(_no_velocity):
    """GOLDEN FIXTURE — identical inputs, three policy states: bullish / bearish / absent.
    opportunity_score, composite_conviction and stage must be byte-identical across all
    three. Before the heal, flipping the LLM's policy lean from overweight to underweight
    moved BOTH scores: it changed net_confirm (→ conf_bonus and agreement → composite) and
    lag_up (→ gap_mult → opportunity)."""
    bull, bear, absent = _acme(_hub_for("overweight")), _acme(_hub_for("underweight")), _acme(_hub_for(None))
    for field in ("opportunity_score", "composite_conviction", "stage", "lean",
                  "n_confirm", "n_dissent", "agreement", "leading_gap", "lag_up",
                  "lag_present", "edge_remaining"):
        assert bull[field] == bear[field] == absent[field], (
            f"{field} moved with the policy lean: bullish={bull[field]!r} "
            f"bearish={bear[field]!r} absent={absent[field]!r}")


def test_policy_facet_and_flags_still_flip(_no_velocity):
    """The heal removes the VOTE, not the desk. The facet, the display direction and the
    alignment flags must all still respond to the policy lean — a silent facet would be a
    different bug (and would hide a real policy conflict from the reader)."""
    bull, bear, absent = _acme(_hub_for("overweight")), _acme(_hub_for("underweight")), _acme(_hub_for(None))

    assert bull["policy"]["dir"] == 1 and bear["policy"]["dir"] == -1
    assert absent["policy"] is None
    assert bull["directions"]["policy"] == 1 and bear["directions"]["policy"] == -1
    assert "policy_aligned" in bull["flags"] and "policy_conflict" not in bull["flags"]
    assert "policy_conflict" in bear["flags"] and "policy_aligned" not in bear["flags"]
    assert not {"policy_aligned", "policy_conflict"} & set(absent["flags"])
    assert bull["facets"]["policy"] is not None            # the dossier facet survives


def test_policy_desk_still_reports_live_and_regime(_no_velocity):
    """desks.policy.live and the macro_context regime string are explicitly out of scope for
    the vote removal — the page must keep showing that the desk exists and what it says."""
    pol = dict(_policy("overweight"), regime_context="low real yields")
    hub = IH.build(_bundle_for_policy_test(), pol, {}, today=_TODAY)
    assert hub["desks"]["policy"]["live"] is True
    assert hub["macro_context"]["policy_regime"] == "low real yields"
    assert hub["counts"]["policy_conflict"] == 0           # conflict counting still wired


def test_policy_is_absent_from_the_voting_desks():
    """The structural guard: a future edit that re-adds policy to the scored aggregation has
    to go through this constant, and this assertion fails when it does."""
    assert "policy" not in IH._VOTING_DESKS
    assert set(IH._VOTING_DESKS) == {"news", "alt", "radar", "standout"}


def test_known_residual_policy_still_widens_base_when_brain_priority_is_zero(_no_velocity):
    """PINNED NON-REPAIR (report to W1, deliberately NOT fixed here).

    `base = brain.priority or (0.5*(len(present)/5) + 0.5*agreement) * strength`. The W0 brief
    ruled `base` out of scope on the premise that brain.priority always short-circuits — but
    priority is `confidence * strength` and strength is 0.0 for a name with no radar
    edge_score, no alt signal_score and no standout conviction (a NEWS-ONLY name). Such a
    name falls into the fallback, where `len(present)` still counts the policy facet, so
    composite_conviction still moves with policy PRESENCE (not with its direction — the
    agreement half is healed).

    This test asserts the residual so it cannot regress silently and so the W1 fix has a
    handle: when `present` stops counting policy, THIS TEST GOES RED. That is intended —
    flip the assertion then."""
    news_only = I.build({"ACME": {"n_recent": 3, "sentiment_lean": "pos", "sentiment_score": 0.5,
                                  "sentiment_strength": 0.5, "baskets": [], "sectors": ["XLK"]}},
                        None, None, None, None, today=_TODAY)
    assert news_only["tickers"]["ACME"]["brain"]["priority"] == 0.0   # the fallback branch
    with_pol = _acme(IH.build(news_only, _policy("overweight"), {}, today=_TODAY))
    no_pol = _acme(IH.build(news_only, None, {}, today=_TODAY))
    # direction-independence IS healed even here
    flipped = _acme(IH.build(news_only, _policy("underweight"), {}, today=_TODAY))
    assert with_pol["composite_conviction"] == flipped["composite_conviction"]
    # …but mere PRESENCE still widens len(present) → base. Residual, reported, not fixed in W0.
    assert with_pol["composite_conviction"] != no_pol["composite_conviction"]
    assert with_pol["n_facets"] == no_pol["n_facets"] + 1


# =========================================================================== #
# ITEM 2 (D22) — snapshot-row provenance: rank / cohorts / hero_reason
# =========================================================================== #
def _multi_name_bundle():
    names = ["AAA", "BBB", "CCC", "DDD"]
    news = {t: {"n_recent": 2, "sentiment_lean": "pos", "sentiment_score": 0.4,
                "sentiment_strength": 0.4, "baskets": [], "sectors": ["XLK"]} for t in names}
    alt = [{"ticker": t, "signal_score": 60 + 8 * i, "action": "BUY", "channels": ["insider"]}
           for i, t in enumerate(names)]
    radar = [{"ticker": t, "state": "POSITIVE_DIVERGENCE", "edge_score": 40 + 12 * i,
              "lifecycle": "forming"} for i, t in enumerate(names)]
    standout = [{"ticker": t, "label": "UPTREND", "conviction": 0.4 + 0.1 * i}
                for i, t in enumerate(names)]
    return I.build(news, alt, None, radar, standout, today=_TODAY)


def test_track_rows_carry_rank_and_cohorts(_no_velocity):
    hub = IH.build(_multi_name_bundle(), None, {}, today=_TODAY, top=2)
    rows = hub["track_rows"]
    assert [r["rank"] for r in rows] == list(range(1, len(rows) + 1))   # 1-based, dense
    # rank must follow the RANKED order the page renders, not dict insertion order: the
    # command list is dossiers[:top], so ranks 1..top are exactly the command tickers in order
    assert [r["t"] for r in rows[:2]] == [d["ticker"] for d in hub["command"]]
    opps = [r["opp"] for r in sorted(rows, key=lambda r: r["rank"])]
    assert opps == sorted(opps, reverse=True), f"rank disagrees with opportunity order: {opps}"
    by_t = {r["t"]: r for r in rows}
    # top=2 ⇒ exactly the first two names are in command_30; every row has a list
    assert all(isinstance(r["cohorts"], list) for r in rows)
    assert "command_30" in by_t[rows[0]["t"]]["cohorts"]
    assert "command_top5" in by_t[rows[0]["t"]]["cohorts"]
    assert "command_30" not in by_t[rows[-1]["t"]]["cohorts"], (
        "a name outside the top=2 command slice must NOT be stamped command_30")


def test_cohorts_are_stamped_after_section_selection(_no_velocity):
    """The cohort must record what the page SHOWED. emerging_panel is the post-hero-gate
    list, so a bullish-stage name the gate barred must not carry the cohort."""
    hub = IH.build(_multi_name_bundle(), None, {}, today=_TODAY, top=30)
    shown = {d["ticker"] for d in hub["emerging"]}
    for r in hub["track_rows"]:
        assert ("emerging_panel" in r["cohorts"]) == (r["t"] in shown), (
            f"{r['t']}: emerging_panel cohort disagrees with the rendered panel")


def test_hero_reason_names_the_gate_rejection(_no_velocity):
    """No entry_gate verdict at all ⇒ no_gate_verdict for a bullish-stage name, and nothing
    for any other stage (absence of a verdict is not a rejection of a name that never
    qualified)."""
    hub = IH.build(_multi_name_bundle(), None, {}, today=_TODAY)
    by_t = {d["ticker"]: d for d in hub["command"]}
    for r in hub["track_rows"]:
        d = by_t.get(r["t"])
        if d is None:
            continue
        if d["stage"] in ("emerging", "early"):
            # these fixtures carry no gate index ⇒ every bullish-stage name is barred, and
            # the reason is the ABSENT verdict, never a silent None
            assert r["hero_reason"] == "no_gate_verdict", (
                f"{r['t']} stage={d['stage']} hero_reason={r['hero_reason']!r}")
        else:
            assert r["hero_reason"] is None


@pytest.mark.parametrize(("stage", "traj", "gate", "expected"), [
    # the PRICE VETO outranks the gate verdict — a rolling-over name is barred for that reason
    # even when its gate says eligible
    ("emerging", {"rolling_over": True}, {"eligible": True}, "rolling_over"),
    ("early", {"rolling_over": True}, None, "rolling_over"),
    # absence of a verdict is its own reason, never silence
    ("emerging", None, None, "no_gate_verdict"),
    ("early", {"rolling_over": False}, {}, "no_gate_verdict"),
    # an explicit flat_sell outranks a plain not-eligible
    ("emerging", None, {"eligible": True, "flat_sell": True}, "flat_sell"),
    ("emerging", None, {"eligible": False, "flat_sell": True}, "flat_sell"),
    ("emerging", None, {"eligible": False}, "not_eligible"),
    # cleared the gate ⇒ no reason
    ("emerging", None, {"eligible": True}, None),
    ("early", {"rolling_over": False}, {"eligible": True}, None),
    # stages that were never hero-eligible are not "rejections"
    ("consensus", None, None, None),
    ("exhausted", {"rolling_over": True}, None, None),
    ("discovery", None, {"eligible": False}, None),
])
def test_hero_reason_mirrors_hero_ok_rejection_order(stage, traj, gate, expected):
    """Calls the SHIPPED _hero_reason — not a copy of it. A mirrored re-implementation here
    would be vacuous: it would pass no matter what build() actually stamps."""
    got = IH._hero_reason({"stage": stage, "trajectory": traj, "entry_gate": gate})
    assert got == expected, f"stage={stage} traj={traj} gate={gate} → {got!r}"


def test_hero_reason_agrees_with_the_hero_panel_on_real_dossiers(_no_velocity):
    """Cross-check against the gate itself: a reason is present exactly when the name is
    bullish-stage AND absent from the rendered Emerging panel."""
    hub = IH.build(_multi_name_bundle(), None, {}, today=_TODAY)
    shown = {d["ticker"] for d in hub["emerging"]}
    by_t = {d["ticker"]: d for d in hub["command"]}
    for r in hub["track_rows"]:
        d = by_t.get(r["t"])
        if d is None:
            continue
        barred = d["stage"] in ("emerging", "early") and r["t"] not in shown
        assert (r["hero_reason"] is not None) == barred, (
            f"{r['t']} stage={d['stage']} shown={r['t'] in shown} reason={r['hero_reason']!r}")


def test_snapshot_persists_provenance_fields(tmp_path):
    rows = [{"t": "AAA", "opp": 60, "edge": 0.6, "stage": "emerging", "lean": 1,
             "rank": 1, "cohorts": ["command_top5", "command_30"], "hero_reason": None},
            {"t": "BBB", "opp": 20, "edge": 0.2, "stage": "early", "lean": 1,
             "rank": 2, "cohorts": [], "hero_reason": "rolling_over"}]
    H.snapshot(rows, date(2026, 1, 2), root=tmp_path)
    written = {json.loads(l)["t"]: json.loads(l)
               for l in H._path(tmp_path).read_text().splitlines()}
    assert written["AAA"]["rank"] == 1
    assert written["AAA"]["cohorts"] == ["command_top5", "command_30"]
    assert "hero_reason" not in written["AAA"]        # None ⇒ omitted, not stored as null
    assert written["BBB"]["hero_reason"] == "rolling_over"
    assert "cohorts" not in written["BBB"]            # empty list ⇒ omitted (bytes are not free)


def test_compute_still_grades_legacy_rows_without_provenance(tmp_path, monkeypatch):
    """BACKWARD COMPATIBILITY GATE — the 38 accrued nights carry none of the three new
    fields. Every one of them must still mature and grade exactly as before."""
    legacy = [{"date": "2026-01-02", "t": f"T{i:02d}", "opp": 10 + i * 5,
               "edge": round((10 + i * 5) / 100, 2),
               "stage": "emerging" if i >= 9 else "exhausted", "lean": 1} for i in range(14)]
    monkeypatch.setattr(H, "_covers", lambda *a, **k: True)
    monkeypatch.setattr(H, "_fwd_rel", lambda t, root, start, h: (int(t[1:]) - 6) * 0.01)
    out = H.compute(date(2026, 6, 21), root=tmp_path, rows=legacy)
    assert out["horizons"]["21"]["n_matured"] == 14
    assert out["horizons"]["21"]["opportunity_ic_pooled"] > 0.5


def test_track_rows_are_still_stripped_from_the_published_hub(monkeypatch, tmp_path):
    """The heavy rows must never reach site/intel_hub/hub.json. Adding three fields per row
    made them heavier, so this behavior is now load-bearing rather than incidental."""
    stub = {"command": [], "emerging": [], "exhausted": [], "catalysts": [], "discovery": [],
            "as_of": "2026-06-20", "desks": {},
            "track_rows": [{"t": "AAA", "opp": 1, "rank": 1, "cohorts": ["command_30"],
                            "hero_reason": None}]}
    monkeypatch.setattr(BIH.intel_hub, "load_and_build", lambda top=30: dict(stub))
    monkeypatch.setattr(BIH.hub_track_record, "snapshot", lambda *a, **k: 1)
    monkeypatch.setattr(BIH.hub_track_record, "compute", lambda *a, **k: {"schema": "x"})
    monkeypatch.setattr(BIH.signal_governor, "compute", lambda **k: {})
    monkeypatch.setattr(BIH.desk_grader, "seed_notes", lambda *a, **k: None)
    monkeypatch.setattr(BIH.desk_grader, "compute", lambda *a, **k: {})
    monkeypatch.setattr(BIH, "build_china_packet", lambda *a, **k: None)
    monkeypatch.setattr(BIH.config, "ROOT", tmp_path)
    hub = BIH.build(write=False)
    assert "track_rows" not in hub
    assert hub["track_record"] == {"schema": "x"}


# =========================================================================== #
# ITEM 3 (D2) — governor reads the freshest radar_ic copy, fails LOUD
# =========================================================================== #
def _radar_ic(as_of: str | None, by_horizon: dict) -> dict:
    out = {"schema": "radar_ic.v2", "by_horizon": by_horizon}
    if as_of:
        out["as_of"] = as_of
    return out


def _demotable(n_days=25):
    return {"21": {"n_matured": 1977,
                   "ic_daily_hac": {"mean_ic": -0.267, "t_hac": -8.29, "n": n_days}}}


def _healthy(n_days=25):
    return {"21": {"n_matured": 1977,
                   "ic_daily_hac": {"mean_ic": 0.12, "t_hac": 6.0, "n": n_days}}}


def _write(root, parts, obj):
    p = root.joinpath(*parts)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj))


def test_governor_prefers_the_published_copy_when_it_is_fresher(tmp_path, capsys):
    """engine-render commits site/ but not data/, so the published copy is routinely days
    fresher. The governor must act on THAT one — the old code read only data/ and could
    de-escalate a signal on a reading the page had already superseded."""
    today = date(2026, 8, 8)
    _write(tmp_path, G._RADAR_IC, _radar_ic("2026-08-04", _demotable()))       # stale, demotes
    _write(tmp_path, G._RADAR_IC_SITE, _radar_ic("2026-08-08", _healthy()))    # fresh, healthy
    out = G.compute(root=tmp_path, today=today, persist=False)
    assert out["signals"]["radar"]["trust"] == 1.0, "the fresh healthy copy must win"
    assert out["inputs"]["radar"]["source"].startswith("site/")
    assert out["inputs"]["radar"]["age_days"] == 0
    assert _annotations(capsys) == [], "a fresh input must be silent"


def test_governor_uses_data_copy_when_it_is_the_fresher_one(tmp_path):
    today = date(2026, 8, 8)
    _write(tmp_path, G._RADAR_IC, _radar_ic("2026-08-08", _demotable()))
    _write(tmp_path, G._RADAR_IC_SITE, _radar_ic("2026-08-01", _healthy()))
    out = G.compute(root=tmp_path, today=today, persist=False)
    assert out["signals"]["radar"]["demoted"] is True
    assert out["inputs"]["radar"]["source"].startswith("data/")


def test_governor_warns_when_the_chosen_radar_input_is_stale(tmp_path, capsys):
    today = date(2026, 8, 8)
    _write(tmp_path, G._RADAR_IC, _radar_ic("2026-08-01", _healthy()))         # 7d old
    out = G.compute(root=tmp_path, today=today, persist=False)
    lines = _annotations(capsys)
    assert len(lines) == 1 and lines[0].startswith("::warning title=signal-governor-stale::")
    assert "7d" in lines[0]
    assert out["inputs"]["radar"]["stale"] is True and out["stale_inputs"] == ["radar"]


def test_governor_warns_when_no_radar_copy_is_readable(tmp_path, capsys):
    """The defect this closes: an absent input produced trust 1.0 with no signal at all,
    which is indistinguishable from 'measured healthy'."""
    out = G.compute(root=tmp_path, today=date(2026, 8, 8), persist=False)
    lines = _annotations(capsys)
    assert len(lines) == 1 and lines[0].startswith("::warning title=signal-governor-stale::")
    assert "unreadable" in lines[0] and "BLIND" in lines[0]
    assert out["inputs"]["radar"]["source"] is None


def test_a_stale_input_never_disarms_or_boosts(tmp_path, capsys):
    """Fail-loud must not become fail-open OR fail-closed: the de-escalation-only semantics
    are untouched. A stale demotable reading still demotes (identity is not forced), and a
    stale healthy reading still yields exactly 1.0 (never above)."""
    _write(tmp_path, G._RADAR_IC, _radar_ic("2026-07-01", _demotable()))
    out = G.compute(root=tmp_path, today=date(2026, 8, 8), persist=False)
    assert out["signals"]["radar"]["demoted"] is True
    assert 0 < out["trust"]["radar"] < 1.0
    assert all(v <= 1.0 for v in out["trust"].values())
    assert _annotations(capsys)                                   # and it said so


def test_undated_radar_copy_is_still_read(tmp_path, capsys):
    """Rows/artifacts with no as_of predate the v2 schema. Age is unverifiable, so they are
    never PREFERRED, but refusing to read them would blind the governor for no reason."""
    _write(tmp_path, G._RADAR_IC, _radar_ic(None, _demotable()))
    out = G.compute(root=tmp_path, today=date(2026, 8, 8), persist=False)
    assert out["signals"]["radar"]["demoted"] is True
    assert out["inputs"]["radar"]["as_of"] is None
    assert out["inputs"]["radar"]["stale"] is False               # unknown ≠ stale
    assert _annotations(capsys) == []


def test_dated_copy_beats_an_undated_one(tmp_path):
    _write(tmp_path, G._RADAR_IC, _radar_ic(None, _demotable()))
    _write(tmp_path, G._RADAR_IC_SITE, _radar_ic("2026-08-08", _healthy()))
    out = G.compute(root=tmp_path, today=date(2026, 8, 8), persist=False)
    assert out["inputs"]["radar"]["source"].startswith("site/")
    assert out["signals"]["radar"]["trust"] == 1.0


# =========================================================================== #
# ITEM 4 (D21) — bounded asof-or-BEFORE price reads
# =========================================================================== #
def _parquet(root: Path, ticker: str, points: list[tuple[str, float]]) -> None:
    d = root / "data" / "yahoo"
    d.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"close": [p[1] for p in points], "volume": [1] * len(points)},
                 index=pd.to_datetime([p[0] for p in points])).to_parquet(d / f"{ticker}.parquet")


def test_level_asof_refuses_a_stalled_series(tmp_path):
    """Series stops 2026-02-20; we ask for a level as of 2026-06-01. The unbounded read
    returned the February close as if it were current — the exact behavior that let a
    delisted / dropped / recycled name keep grading."""
    _parquet(tmp_path, "DEAD", [("2026-02-18", 50.0), ("2026-02-20", 48.0)])
    stale_close = _desk._level_asof("DEAD", tmp_path, "2026-06-01", max_stale_days=None)
    assert stale_close == 48.0, "unbounded read still returns the stale bar (old behavior)"
    assert _desk._level_asof("DEAD", tmp_path, "2026-06-01") is None, "bounded read: not covered"
    assert _desk._level_asof("DEAD", tmp_path, "2026-02-23") == 48.0, "3d old ⇒ still covered"


def test_close_at_refuses_a_stalled_series(tmp_path):
    _parquet(tmp_path, "DEAD", [("2026-02-18", 50.0), ("2026-02-20", 48.0)])
    assert DS.close_at("DEAD", tmp_path, "2026-06-01", max_stale_days=None) == 48.0
    assert DS.close_at("DEAD", tmp_path, "2026-06-01") is None
    assert DS.close_at("DEAD", tmp_path, "2026-02-27") == 48.0        # 7d — the bound is inclusive


def test_a_holiday_weekend_gap_is_still_covered(tmp_path):
    """The bound must not manufacture nulls out of normal market closures: the longest US
    exchange gap is a 3-day holiday weekend."""
    _parquet(tmp_path, "SPY", [("2026-01-16", 100.0)])               # Friday
    assert _desk._level_asof("SPY", tmp_path, "2026-01-19") == 100.0  # holiday Monday
    assert DS.close_at("SPY", tmp_path, "2026-01-19") == 100.0


def test_fwd_rel_refuses_a_hole_around_the_entry_date(tmp_path):
    """The start leg is the one `covers` cannot protect: a name whose series has a HOLE
    around the snapshot date but resumes later passes coverage, then prices its entry off a
    bar from weeks earlier while its exit is current — a fabricated return that entered the
    IC at full weight."""
    # SPY is complete; GAPPY is missing all of February
    spy = [(d.strftime("%Y-%m-%d"), 100.0 + i)
           for i, d in enumerate(pd.bdate_range("2026-01-02", "2026-04-01"))]
    _parquet(tmp_path, "SPY", spy)
    gappy = [("2026-01-05", 10.0)] + [(d.strftime("%Y-%m-%d"), 20.0)
                                      for d in pd.bdate_range("2026-03-02", "2026-04-01")]
    _parquet(tmp_path, "GAPPY", gappy)
    # snapshot on 2026-02-10: the last GAPPY bar before it is 2026-01-05 — 36 days stale
    assert H._fwd_rel("GAPPY", tmp_path, "2026-02-10", 21) is None
    # a name with no hole grades normally, so the bound is not simply refusing everything
    assert H._fwd_rel("SPY", tmp_path, "2026-02-10", 21) == pytest.approx(0.0, abs=1e-9)


def test_max_stale_default_is_seven_calendar_days():
    assert _desk.MAX_ASOF_STALE_DAYS == 7
    assert H.MAX_STALE_D == 7


# =========================================================================== #
# ITEM 5 (D20) — accrual gap + coverage monitor
# =========================================================================== #
def _bdays(start: str, end: str) -> list[str]:
    return [d.strftime("%Y-%m-%d") for d in pd.bdate_range(start, end)]


def test_accrual_gap_is_detected_and_annotated(tmp_path, capsys, monkeypatch):
    """The live failure: 2026-08-04, -07 and -08 were never written while the page kept
    reading fresh. A skipped date is a permanent point-in-time hole, so the only defence is
    noticing the same night."""
    today = date(2026, 8, 20)
    days = _bdays("2026-08-03", today.isoformat())
    skipped = {days[1], days[4]}
    for d in days:
        if d in skipped:
            continue
        H.snapshot([{"t": "AAA", "opp": 50, "edge": 0.5, "stage": "early", "lean": 1}],
                   d, root=tmp_path)
    monkeypatch.setattr(H, "_covers", lambda *a, **k: False)
    out = H.compute(today, root=tmp_path)

    gaps = out["accrual_gaps"]
    assert gaps["approximate"] is True and gaps["window_days"] == H.ACCRUAL_WINDOW_D
    assert skipped <= set(gaps["missing_dates"]), gaps["missing_dates"]
    assert gaps["n_missing"] == len(skipped)
    assert gaps["first_snapshot"] == days[0]        # nothing before the ledger's own start
    lines = _annotations(capsys)
    assert any(ln.startswith("::warning title=hub-accrual-gap::") for ln in lines), lines
    assert all(d in " ".join(lines) for d in skipped)


def test_no_accrual_warning_when_every_expected_date_is_present(tmp_path, capsys, monkeypatch):
    today = date(2026, 8, 20)
    for d in _bdays("2026-08-10", today.isoformat()):
        H.snapshot([{"t": "AAA", "opp": 50, "edge": 0.5, "stage": "early", "lean": 1}],
                   d, root=tmp_path)
    monkeypatch.setattr(H, "_covers", lambda *a, **k: False)
    out = H.compute(today, root=tmp_path)
    assert out["accrual_gaps"]["n_missing"] == 0
    assert not [ln for ln in _annotations(capsys)
                if ln.startswith("::warning title=hub-accrual-gap::")]


def test_coverage_pct_is_reported_and_the_floor_breach_annotated(tmp_path, capsys, monkeypatch):
    """The scorecard graded 6.2% of its eligible universe with that number printed nowhere;
    a 6% slice and a 90% slice produced identical-looking payloads."""
    rows = [{"t": f"T{i:02d}", "opp": 10 + i * 4, "edge": 0.5, "stage": "early", "lean": 1}
            for i in range(20)]
    H.snapshot(rows, date(2026, 1, 2), root=tmp_path)
    graded = {f"T{i:02d}" for i in range(5)}                    # only 5 of 20 are price-covered
    monkeypatch.setattr(H, "_covers", lambda t, *a, **k: t in graded or t == "SPY")
    monkeypatch.setattr(H, "_fwd_rel", lambda t, root, start, h: 0.01 * int(t[1:]))
    out = H.compute(date(2026, 6, 21), root=tmp_path)

    cov = out["coverage_pct"]["21"]
    assert cov["n_eligible"] == 20 and cov["n_matured"] == 5
    assert cov["coverage_pct"] == 25.0 and cov["below_floor"] is True
    assert out["horizons"]["21"]["coverage"] == cov            # mirrored per horizon
    lines = _annotations(capsys)
    assert any(ln.startswith("::warning title=hub-coverage-floor::") for ln in lines), lines
    assert "25.0%" in " ".join(lines) and "5/20" in " ".join(lines)


def test_coverage_above_the_floor_is_quiet(tmp_path, capsys, monkeypatch):
    rows = [{"t": f"T{i:02d}", "opp": 10 + i * 4, "edge": 0.5, "stage": "early", "lean": 1}
            for i in range(20)]
    H.snapshot(rows, date(2026, 1, 2), root=tmp_path)
    monkeypatch.setattr(H, "_covers", lambda *a, **k: True)
    monkeypatch.setattr(H, "_fwd_rel", lambda t, root, start, h: 0.01 * int(t[1:]))
    out = H.compute(date(2026, 6, 21), root=tmp_path)
    assert out["coverage_pct"]["21"]["coverage_pct"] == 100.0
    assert out["coverage_pct"]["21"]["below_floor"] is False
    assert not [ln for ln in _annotations(capsys)
                if ln.startswith("::warning title=hub-coverage-floor::")]


def test_monitors_gate_nothing(tmp_path, monkeypatch):
    """Display-tier only. A floor breach must not change proven/lead_time/IC — an
    accrual gate that wrote fewer rows would punch the very hole it was watching for."""
    rows = [{"t": f"T{i:02d}", "opp": 10 + i * 4, "edge": 0.5, "stage": "early", "lean": 1}
            for i in range(20)]
    H.snapshot(rows, date(2026, 1, 2), root=tmp_path)
    graded = {f"T{i:02d}" for i in range(12)}
    monkeypatch.setattr(H, "_covers", lambda t, *a, **k: t in graded or t == "SPY")
    monkeypatch.setattr(H, "_fwd_rel", lambda t, root, start, h: 0.01 * int(t[1:]))
    out = H.compute(date(2026, 6, 21), root=tmp_path)
    assert out["coverage_pct"]["21"]["below_floor"] is False
    assert out["horizons"]["21"]["n_matured"] == 12
    assert out["horizons"]["21"]["opportunity_ic_pooled"] is not None
    assert out["proven"] == {h: False for h in ("5", "10", "21", "63")}


def test_compute_error_payload_still_carries_the_monitor_keys(monkeypatch):
    """W5 renders these keys. The degrade-safe branch must not hand it a KeyError."""
    monkeypatch.setattr(H, "_load", lambda root: (_ for _ in ()).throw(RuntimeError("boom")))
    out = H.compute(date(2026, 6, 21), root=Path("/nonexistent"))
    assert out["accrual_gaps"] == {} and out["coverage_pct"] == {}


def test_coverage_floor_constant_is_named():
    assert H.COVERAGE_FLOOR_PCT == 50.0
    assert H.ACCRUAL_WINDOW_D == 30


# =========================================================================== #
# ITEM 6 (D3) — special-situations freshness sentinel
# =========================================================================== #
def _special_sits(tmp_path: Path, generated_at: str | None) -> Path:
    p = tmp_path / "site" / "allocationdata" / "special_situations.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    body: dict = {"schema": "special_situations.v1", "n": 5790, "by_ticker": {}}
    if generated_at is not None:
        body["generated_at"] = generated_at
    p.write_text(json.dumps(body))
    return p


_NOW = datetime(2026, 8, 8, 12, 0, tzinfo=timezone.utc)


def test_special_sits_stale_warns_and_stamps_the_desk(tmp_path, capsys):
    p = _special_sits(tmp_path, "2026-08-05 07:21 UTC")            # ~77h old
    hub: dict = {"desks": {"special": {"live": True}}}
    out = BIH.stamp_special_freshness(hub, now=_NOW, path=p)
    lines = _annotations(capsys)
    assert len(lines) == 1 and lines[0].startswith("::warning title=special-sits-stale::")
    assert hub["desks"]["special"]["stale"] is True
    assert hub["desks"]["special"]["age_days"] == pytest.approx(3.2, abs=0.05)
    assert hub["desks"]["special"]["live"] is True                 # existing keys preserved
    assert out["stale"] is True


def test_special_sits_fresh_is_quiet(tmp_path, capsys):
    p = _special_sits(tmp_path, "2026-08-08 07:21 UTC")            # ~5h old
    hub: dict = {"desks": {"special": {"live": True}}}
    BIH.stamp_special_freshness(hub, now=_NOW, path=p)
    assert _annotations(capsys) == []
    assert hub["desks"]["special"]["stale"] is False
    assert hub["desks"]["special"]["age_hours"] == pytest.approx(4.65, abs=0.05)


def test_special_sits_36h_bar(tmp_path, capsys):
    """Just inside the bar is silent; just outside fires. The bar is 36h because the file is
    written by the nightly — one skipped run crosses it."""
    hub: dict = {"desks": {}}
    BIH.stamp_special_freshness(hub, now=_NOW,
                               path=_special_sits(tmp_path, "2026-08-07 01:00 UTC"))  # 35h
    assert _annotations(capsys) == [] and hub["desks"]["special"]["stale"] is False
    hub2: dict = {"desks": {}}
    BIH.stamp_special_freshness(hub2, now=_NOW,
                                path=_special_sits(tmp_path, "2026-08-06 23:00 UTC"))  # 37h
    assert len(_annotations(capsys)) == 1 and hub2["desks"]["special"]["stale"] is True
    assert BIH._SPECIAL_STALE_HOURS == 36


def test_special_sits_undated_file_warns(tmp_path, capsys):
    """Present but undated ⇒ freshness unverifiable, which is the same silence the sentinel
    exists to end. Reporting a comforting None would be the defect wearing a new hat."""
    hub: dict = {"desks": {}}
    BIH.stamp_special_freshness(hub, now=_NOW, path=_special_sits(tmp_path, None))
    lines = _annotations(capsys)
    assert len(lines) == 1 and lines[0].startswith("::warning title=special-sits-stale::")
    assert hub["desks"]["special"]["stale"] is None


def test_special_sits_absent_file_is_not_annotated(tmp_path, capsys):
    """An absent artifact is already carried by desks.special.live == False (the catalyst
    index is empty) — a valid, documented degrade state, not a silent one."""
    hub: dict = {"desks": {"special": {"live": False}}}
    assert BIH.stamp_special_freshness(hub, now=_NOW, path=tmp_path / "nope.json") is None
    assert _annotations(capsys) == []
    assert hub["desks"]["special"]["stale"] is None


def test_special_sits_parses_every_stamp_shape_we_write():
    assert BIH._parse_stamp("2026-08-08 07:21 UTC") == datetime(2026, 8, 8, 7, 21, tzinfo=timezone.utc)
    assert BIH._parse_stamp("2026-08-08T07:21:00+00:00") == datetime(2026, 8, 8, 7, 21, tzinfo=timezone.utc)
    assert BIH._parse_stamp("2026-08-08") == datetime(2026, 8, 8, tzinfo=timezone.utc)
    assert BIH._parse_stamp("not a date") is None and BIH._parse_stamp(None) is None


def test_special_sits_future_stamp_is_never_negative_age(tmp_path, capsys):
    hub: dict = {"desks": {}}
    BIH.stamp_special_freshness(hub, now=_NOW,
                                path=_special_sits(tmp_path, "2026-08-09 07:21 UTC"))
    assert hub["desks"]["special"]["age_hours"] == 0.0
    assert hub["desks"]["special"]["stale"] is False
    assert _annotations(capsys) == []


def test_special_sits_sentinel_is_wired_into_the_build():
    """A helper nobody calls is a helper that ships dead."""
    import inspect
    src = inspect.getsource(BIH.build)
    assert "stamp_special_freshness(hub" in src


# =========================================================================== #
# ITEM 7 (D4) — the dead Quiver twitter dataset is delisted
# =========================================================================== #
def test_dead_twitter_dataset_is_delisted():
    """Quiver /beta/live/twitter has returned nothing since the 2023 X API shutdown (1 row,
    last date 2023-08-11; collector tombstoned at collectors/quiver.py:229). While it was
    listed it rendered as a live data lane and counted as a channel that can never fire."""
    assert "twitter" not in A.DATASETS
    assert not [k for k in A.DATASETS if "twitter" in k.lower()]


def test_surviving_datasets_are_intact():
    """A delist must remove exactly one key — not quietly reshape the registry."""
    assert len(A.DATASETS) == 22
    for key in ("congress", "insiders", "wallstreetbets", "spacs", "sec13f", "news"):
        assert key in A.DATASETS
    assert all(len(v) == 4 for v in A.DATASETS.values())


def test_twitter_is_not_a_convergence_channel():
    from engine import altdata_models as M
    assert "twitter" not in M.CHANNEL_WEIGHTS
    recs = M.channel_records({"twitter": [{"ticker": "AAA"}]})
    assert not any("twitter" in (r.get("channels") or []) for r in recs.values())
