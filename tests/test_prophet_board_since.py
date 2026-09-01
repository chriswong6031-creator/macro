"""RED-before-GREEN tests for engine/prophet_board_since.py.

Covers: the pure resolver core (continuity, left-censoring, idempotence),
the CN watch/legacy exclusion, and the HK/CA/US visible-lane traces pinned
against the templates that actually render candidate cards.
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import pandas as pd  # noqa: E402
import pytest  # noqa: E402

from engine import prophet_board_since as pbs  # noqa: E402


# ─────────────────────────────── resolver core ──────────────────────────────

def test_continuing_candidate_keeps_date_with_preceding_absence_proof():
    obs = [
        ("2026-07-01", ["AAA", "BBB"]),
        ("2026-07-02", ["BBB"]),          # AAA absent here -> resets AAA's streak
        ("2026-07-03", ["AAA", "BBB"]),   # AAA re-added
        ("2026-07-04", ["AAA", "BBB"]),
    ]
    start = pbs.current_continuous_membership_start(obs, "AAA")
    assert start == ("2026-07-03", "absence_proof")


def test_visible_lane_move_preserves_streak():
    # A move between visible lanes at the SAME published date is represented as
    # simple continued presence in the observation set (lane detail is not part
    # of the observation identity), so it must not reset the streak.
    obs = [
        ("2026-07-01", ["AAA"]),
        ("2026-07-02", ["AAA"]),
        ("2026-07-03", ["AAA"]),
    ]
    start = pbs.current_continuous_membership_start(obs, "AAA", starts_at_inception=True)
    assert start == ("2026-07-01", "inception_proof")


def test_published_absence_resets_then_readd_mints_new_date():
    obs = [
        ("2026-07-01", ["AAA"]),
        ("2026-07-05", []),               # published board — AAA explicitly absent
        ("2026-07-06", ["AAA"]),          # re-add
    ]
    start = pbs.current_continuous_membership_start(obs, "AAA")
    assert start == ("2026-07-06", "absence_proof")


def test_missing_whole_board_date_gap_does_not_reset():
    obs = [
        ("2026-07-01", ["AAA"]),
        # 2026-07-02..04 simply never published (weekend/holiday/outage) — not
        # in `obs` at all, so no absence is asserted for those dates.
        ("2026-07-05", ["AAA"]),
    ]
    start = pbs.current_continuous_membership_start(obs, "AAA", starts_at_inception=True)
    assert start == ("2026-07-01", "inception_proof")


def test_with_current_board_no_op_when_as_of_not_after_newest_fossil():
    fossil = [("2026-07-01", ["AAA"]), ("2026-07-02", ["AAA", "BBB"])]
    same_session = pbs.with_current_board(fossil, "2026-07-02", ["AAA"])  # BBB dropped in "current"
    assert same_session == pbs.collapse_published_observations(fossil)
    older = pbs.with_current_board(fossil, "2026-06-30", ["ZZZ"])
    assert older == pbs.collapse_published_observations(fossil)


def test_stale_as_of_never_overwrites_newer_fossil():
    fossil = [("2026-07-01", ["AAA"]), ("2026-07-05", ["AAA", "BBB"])]
    result = pbs.with_current_board(fossil, "2026-07-03", ["CCC"])
    assert dict(result)["2026-07-05"] == frozenset({"AAA", "BBB"})
    assert "2026-07-03" not in dict(result)


def test_with_current_board_appends_strictly_newer_as_of():
    fossil = [("2026-07-01", ["AAA"])]
    result = pbs.with_current_board(fossil, "2026-07-02", ["AAA", "BBB"])
    assert dict(result)["2026-07-02"] == frozenset({"AAA", "BBB"})


def test_left_censoring_present_at_oldest_returns_none_by_default():
    obs = [("2026-07-01", ["AAA"]), ("2026-07-02", ["AAA"])]
    assert pbs.current_continuous_membership_start(obs, "AAA") is None


def test_left_censoring_present_at_oldest_returns_inception_when_asserted():
    obs = [("2026-07-01", ["AAA"]), ("2026-07-02", ["AAA"])]
    start = pbs.current_continuous_membership_start(obs, "AAA", starts_at_inception=True)
    assert start == ("2026-07-01", "inception_proof")


def test_absent_from_last_observation_is_none():
    obs = [("2026-07-01", ["AAA"]), ("2026-07-02", ["BBB"])]
    assert pbs.current_continuous_membership_start(obs, "AAA") is None


def test_malformed_or_empty_history_is_none():
    assert pbs.current_continuous_membership_start([], "AAA") is None
    assert pbs.current_continuous_membership_start(None, "AAA") is None
    assert pbs.current_continuous_membership_start([("not-a-date", ["AAA"])], "AAA") is None


def test_with_current_board_idempotent_across_repeated_calls():
    fossil = [("2026-07-01", ["AAA"])]
    once = pbs.with_current_board(fossil, "2026-07-02", ["AAA"])
    twice = pbs.with_current_board(once, "2026-07-02", ["AAA"])
    assert once == twice


# ──────────────────────────────────── CN ────────────────────────────────────

def _cn_frame(rows):
    return pd.DataFrame(rows, columns=["date", "ticker", "board_definition"])


def test_cn_watch_definitions_never_sustain_tenure():
    watch = {"cn_reversal_watch_v1"}
    df = _cn_frame([
        ("2026-08-01", "AAA", "cn_reversal_watch_v1"),
        ("2026-08-02", "AAA", "cn_reversal_watch_v1"),
    ])
    obs = pbs.observations_from_cn_frame(df, watch)
    assert obs == []


def test_cn_legacy_rows_excluded_from_presence_and_absence():
    df = _cn_frame([
        ("2026-06-30", "AAA", "legacy"),
        ("2026-07-30", "AAA", "cn_prophet_v2"),
        ("2026-07-31", "AAA", "cn_prophet_v2"),
    ])
    obs = pbs.observations_from_cn_frame(df, watch_definitions=set())
    assert [d for d, _ in obs] == ["2026-07-30", "2026-07-31"]
    # present at the (non-legacy) oldest observation -> left-censored, None
    start = pbs.current_continuous_membership_start(obs, "AAA", starts_at_inception=False)
    assert start is None


def test_cn_watch_definitions_module_attr_identity():
    from engine.china_standout_track import WATCH_DEFINITIONS
    # The adapter takes watch_definitions as a parameter and must not carry a
    # copied/duplicated frozenset anywhere in this module's own namespace.
    assert not hasattr(pbs, "CN_WATCH_DEFINITIONS")
    assert isinstance(WATCH_DEFINITIONS, frozenset)


def test_cn_current_visible_ids_matches_template_partition():
    artifact = {
        "buy": [
            {"ticker": "AAA", "stage": "ENTRY"},
            {"ticker": "BBB", "stage": "RAN_LATE"},
            {"ticker": "CCC", "stage": "SOMETHING_ELSE"},
        ],
        "more_actionable": [{"ticker": "DDD"}],
        "late_or_unfillable": [{"ticker": "EEE"}],
    }
    ids = pbs.cn_current_visible_ids(artifact)
    assert ids == {"AAA", "BBB", "DDD"}


def test_cn_current_visible_ids_legacy_fallback_whole_board():
    artifact = {"buy": [{"ticker": "AAA"}, {"ticker": "BBB"}]}
    assert pbs.cn_current_visible_ids(artifact) == {"AAA", "BBB"}


# ─────────────────────────────────── HK/CA ───────────────────────────────────

def _ledger_frame(rows):
    return pd.DataFrame(rows, columns=["date", "ticker", "group"])


def test_hk_ca_visible_groups_excludes_watch():
    df = _ledger_frame([
        ("2026-08-01", "AAA", "entry_open"),
        ("2026-08-01", "BBB", "watch"),
        ("2026-08-02", "AAA", "setting_up"),
        ("2026-08-02", "BBB", "watch"),
    ])
    obs = pbs.observations_from_board_ledger_frame(df)
    assert dict(obs)["2026-08-01"] == frozenset({"AAA"})
    assert dict(obs)["2026-08-02"] == frozenset({"AAA"})


def test_hk_ca_visible_groups_constant_is_entry_open_and_setting_up_only():
    assert pbs.HK_CA_VISIBLE_GROUPS == frozenset({"entry_open", "setting_up"})


def test_hk_template_never_pv_cards_the_watch_lane():
    text = (_ROOT / "templates" / "hk.html.j2").read_text(encoding="utf-8")
    # setups.watch renders through a plain anchor grid, never pv_card — pin the
    # absence of a pv_card(...) call anywhere between the watch-strip guard and
    # its closing block by checking there is no 'pv.pv_card(' on any line whose
    # nearby context mentions 'watch-strip'.
    idx = text.find('class="watch-strip"')
    assert idx != -1
    window = text[idx: idx + 2000]
    assert "pv.pv_card(" not in window


def test_canada_template_never_pv_cards_the_watch_lane():
    text = (_ROOT / "templates" / "canada.html.j2").read_text(encoding="utf-8")
    idx = text.find('class="watch-strip"')
    assert idx != -1
    window = text[idx: idx + 2000]
    assert "pv.pv_card(" not in window


# ──────────────────────────────────── US ─────────────────────────────────────

def test_us_visible_lanes_is_buy_only():
    assert pbs.US_VISIBLE_LANES == ("buy",)


def test_us_donor_never_treated_as_a_ticker_lane(tmp_path):
    jsonl = tmp_path / "snapshots.jsonl"
    jsonl.write_text(
        '{"as_of": "2026-06-30", "buy": [{"ticker": "AAA"}], '
        '"donor": {"donor_sector": "Technology", "state": "cracking"}}\n',
        encoding="utf-8",
    )
    obs = pbs.observations_from_us_snapshots_jsonl(jsonl)
    assert dict(obs)["2026-06-30"] == frozenset({"AAA"})


def test_us_snapshot_memoization_avoids_second_reparse(tmp_path, monkeypatch):
    jsonl = tmp_path / "snapshots.jsonl"
    jsonl.write_text('{"as_of": "2026-06-30", "buy": [{"ticker": "AAA"}]}\n', encoding="utf-8")
    pbs._us_obs_cache.clear()
    calls = {"n": 0}
    real_open = Path.open

    def counting_open(self, *a, **kw):
        if self == jsonl:
            calls["n"] += 1
        return real_open(self, *a, **kw)

    monkeypatch.setattr(Path, "open", counting_open)
    first = pbs.observations_from_us_snapshots_jsonl(jsonl)
    second = pbs.observations_from_us_snapshots_jsonl(jsonl)
    assert first == second
    assert calls["n"] == 1


def test_us_board_cards_template_only_ever_included_with_buy_derived_items():
    dash = (_ROOT / "templates" / "dashboard.html.j2").read_text(encoding="utf-8")
    assert dash.count('include "_us_board_cards.html.j2"') == 1
    build = (_ROOT / "scripts" / "build_site.py").read_text(encoding="utf-8")
    assert build.count('get_template("_us_board_cards.html.j2")') == 1


# ─────────────────────────────────── Intl ────────────────────────────────────

def test_intl_carry_forward_carries_valid_prior_date():
    prior = {"as_of": "2026-08-01", "buy": [{"ticker": "AAA", "added_date": "2026-07-15"}]}
    current = {"as_of": "2026-08-02", "buy": [{"ticker": "AAA"}]}
    out = pbs.stamp_intl_board_since(current, prior_artifact=prior)
    assert out["buy"][0]["added_date"] == "2026-07-15"


def test_intl_absent_in_prior_and_valid_newer_as_of_mints_current():
    prior = {"as_of": "2026-08-01", "buy": [{"ticker": "BBB", "added_date": "2026-07-01"}]}
    current = {"as_of": "2026-08-02", "buy": [{"ticker": "AAA"}]}
    out = pbs.stamp_intl_board_since(current, prior_artifact=prior)
    assert out["buy"][0]["added_date"] == "2026-08-02"


def test_intl_null_as_of_mints_nothing():
    prior = {"as_of": "2026-08-01", "buy": [{"ticker": "BBB"}]}
    current = {"as_of": None, "buy": [{"ticker": "AAA"}]}
    out = pbs.stamp_intl_board_since(current, prior_artifact=prior)
    assert out["buy"][0]["added_date"] is None


def test_intl_same_as_of_is_idempotent_mints_nothing_new():
    prior = {"as_of": "2026-08-01", "buy": [{"ticker": "AAA", "added_date": "2026-07-15"},
                                             {"ticker": "BBB"}]}
    current = {"as_of": "2026-08-01", "buy": [{"ticker": "AAA"}, {"ticker": "BBB"}, {"ticker": "CCC"}]}
    out = pbs.stamp_intl_board_since(current, prior_artifact=prior)
    by_tk = {r["ticker"]: r["added_date"] for r in out["buy"]}
    assert by_tk["AAA"] == "2026-07-15"
    assert by_tk["BBB"] is None  # was present in prior but had no valid recorded since
    assert by_tk["CCC"] is None  # new but not a strictly-newer as_of -> mint nothing


def test_intl_prior_unreadable_yields_all_none_no_exception():
    current = {"as_of": "2026-08-02", "buy": [{"ticker": "AAA"}]}
    out = pbs.stamp_intl_board_since(current, prior_artifact=None)
    assert out["buy"][0]["added_date"] is None


def test_intl_visible_lane_is_buy_only():
    text = (_ROOT / "templates" / "intl.html.j2").read_text(encoding="utf-8")
    assert text.count("pv.pv_card(") == 1
    assert pbs.INTL_VISIBLE_LANES == ("buy",)


def test_intl_stamp_fail_open_never_raises(tmp_path):
    # A prior artifact path that does not exist must fail open, not raise.
    out = pbs.stamp_intl_board_since_fail_open(
        {"as_of": "2026-08-02", "buy": [{"ticker": "AAA"}]},
        repo_root=tmp_path,
    )
    assert out["buy"][0]["added_date"] is None
