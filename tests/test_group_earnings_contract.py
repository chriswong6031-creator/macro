"""group_earnings_pulse.v1 contract + floor-refusal guards (Group Reads W-GR2).

Everything here runs against a SYNTHETIC data tree written into tmp_path — no network,
no dependence on the committed stores, and every number the assertions pin is one the
fixture put there by hand. The contract validator lives in this file, not in the engine:
a schema that certifies itself certifies nothing.

WHAT IS PINNED
    * the v1 key set, exactly — an unknown key and a missing `n` must both go red
    * a stat may be null ONLY next to its own n (the legal refusal form)
    * every floor refuses with a null instead of a survivor-only number: `thin` has three
      members with perfectly good data and must publish nothing but nulls, because three
      is below every floor in the module
    * the resolution-conditioned-denominator law: n_beat + n_miss + n_inline + n_no_data
      == n_members in every basket, refused or not
    * engine.guidance_gap's >=2-distinct-filers law survives the generalization to basket
      rosters: one filer -> band null, two filers -> a band
    * the drift window arithmetic (5 sessions from the REACTION close, SPY-adjusted)
"""
from __future__ import annotations

import copy
import json

import pandas as pd
import pytest

from engine import group_earnings as ge
from lib import config

# --------------------------------------------------------------------------- #
# synthetic data tree
# --------------------------------------------------------------------------- #
AS_OF = "2026-08-07"
N_SESSIONS = 400
SPY_DAILY = 0.001            # constant benchmark drift — an unadjusted leg reads wrong
QUIET_ADJ = 0.01             # SPY-adjusted member move on a non-report session
EVENT_ADJ = 0.02             # ... and on a session some member of the basket reports into

RICH = [f"R{i}" for i in range(1, 9)]        # 8 members — clears every floor
THIN = ["T1", "T2", "T3"]                    # 3 members — below every floor, WITH data
ONEF = [f"O{i}" for i in range(1, 6)]        # 5 members — exactly one guidance filer
STALE_MEMBER = "O5"          # its only report is two cycles back — outside the season
STALE_REPORT_IDX = -200

#: latest report of RICH member i sits at session index -(20 + 6*i); earlier quarters step
#: back 63 sessions. Chosen so all eight land inside the 75-session season window, at least
#: 5 sessions before as_of (so drift resolves), and never inside another member's +5 window.
def _rich_event_index(i: int, q: int) -> int:
    return -(20 + 6 * i + 63 * q)


def _sessions() -> pd.DatetimeIndex:
    return pd.bdate_range(end=AS_OF, periods=N_SESSIONS)


def _adj_returns(sessions: pd.DatetimeIndex) -> tuple[pd.DataFrame, set[int]]:
    """Per-member SPY-ADJUSTED daily returns, plus the RICH basket's event-day positions."""
    n = len(sessions)
    event_pos = {n + _rich_event_index(i, q) for i in range(8) for q in range(6)}
    members = RICH + THIN + ONEF
    frame = pd.DataFrame(QUIET_ADJ, index=sessions, columns=members, dtype=float)
    for p in event_pos:
        frame.iloc[p] = EVENT_ADJ
    # R7/R8 drift NEGATIVE over the five sessions after their own latest report, so
    # pos_share_5d is 6/8 and not a degenerate 1.0. Those windows contain no event day.
    for i, t in ((6, "R7"), (7, "R8")):
        p = n + _rich_event_index(i, 0)
        frame.iloc[p + 1:p + 6, frame.columns.get_loc(t)] = -QUIET_ADJ
    frame.iloc[0] = 0.0
    return frame, event_pos


def _write_tree(root, monkeypatch) -> dict:
    data = root / "data"
    sessions = _sessions()
    adj, event_pos = _adj_returns(sessions)

    # closes: member return = adjusted return + the benchmark's, so a leg that forgets to
    # subtract SPY lands 0.1%/session away from every asserted value
    (data / "baskets" / "ohlcv").mkdir(parents=True, exist_ok=True)
    for t in adj.columns:
        close = 100.0 * (1.0 + adj[t] + SPY_DAILY).cumprod()
        pd.DataFrame({"close": close.to_numpy()},
                     index=pd.DatetimeIndex(sessions, name="Date")).to_parquet(
            data / "baskets" / "ohlcv" / f"{t}.parquet")

    (data / "yahoo").mkdir(parents=True, exist_ok=True)
    spy = 100.0 * (1.0 + pd.Series(SPY_DAILY, index=sessions)).cumprod()
    pd.DataFrame({"close": spy.to_numpy()},
                 index=pd.DatetimeIndex(sessions, name="Date")).to_parquet(
        data / "yahoo" / "SPY.parquet")

    # registry
    def _members(tickers):
        return [{"ticker": t, "added": "2020-01-02", "removed": None} for t in tickers]
    (data / "baskets").mkdir(parents=True, exist_ok=True)
    (data / "baskets" / "membership.json").write_text(json.dumps({
        "version": AS_OF,
        "baskets": {
            "rich": {"name": "Rich", "members": _members(RICH)},
            "thin": {"name": "Thin", "members": _members(THIN)},
            "onefiler": {"name": "One Filer", "members": _members(ONEF)},
        }}))

    # 8-K Item-2.02 spine — one after-hours filing per (member, quarter)
    rows = []
    for i, t in enumerate(RICH):
        for q in range(6):
            d = sessions[_rich_event_index(i, q) - 1]        # prints the NEXT session
            rows.append({"ticker": t, "cik": 1, "filing_date": d.date().isoformat(),
                         "acceptance_datetime": f"{d.date().isoformat()}T20:15:00.000Z",
                         "items": "2.02,9.01"})
    # THIN + ONEF report once, in-season — EXCEPT O5, whose only report is ~200 sessions
    # back. It is the season window's own test subject: a member last seen two cycles ago
    # has not reported THIS season and must land in n_no_data.
    for tick_set in (THIN, ONEF):
        for t in tick_set:
            d = sessions[STALE_REPORT_IDX - 1] if t == STALE_MEMBER else sessions[-21]
            rows.append({"ticker": t, "cik": 2, "filing_date": d.date().isoformat(),
                         "acceptance_datetime": f"{d.date().isoformat()}T20:15:00.000Z",
                         "items": "2.02"})
    (data / "edgar").mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(data / "edgar" / "earnings_8k_dates.parquet", index=False)

    # Nasdaq calendar + surprises. RICH: R1-R4 beat, R5 miss, R6 exactly inline, R7/R8 have
    # no surprise history at all -> n_no_data=2 (they are counted, never dropped).
    surprise = {"R1": 5.0, "R2": 4.0, "R3": 3.0, "R4": 2.0, "R5": -3.0, "R6": 0.0}
    surprise.update({t: 1.5 for t in THIN})                  # 3 classified: below the floor
    surprise.update({t: 1.5 for t in ONEF})
    erows, idx = [], []
    for i, t in enumerate(RICH):
        reported = _sessions()[_rich_event_index(i, 0) - 1].date().isoformat()
        sj = ([] if t not in surprise else
              [{"qtr": "Q", "reported": reported, "eps": 1.0, "consensus": 1.0,
                "surprise_pct": surprise[t]}])
        idx.append(t)
        erows.append({"next_date": "2026-08-12" if i < 2 else "2026-12-01",
                      "next_time": ["time-after-hours", "time-pre-market"][i % 2],
                      "eps_forecast": 1.0, "surprises_json": json.dumps(sj),
                      "surprises_as_of": AS_OF, "as_of": AS_OF})
    for t in THIN + ONEF:
        reported = _sessions()[
            STALE_REPORT_IDX - 1 if t == STALE_MEMBER else -21].date().isoformat()
        idx.append(t)
        erows.append({"next_date": "2026-12-01", "next_time": "time-not-supplied",
                      "eps_forecast": 1.0,
                      "surprises_json": json.dumps(
                          [{"qtr": "Q", "reported": reported, "eps": 1.0, "consensus": 1.0,
                            "surprise_pct": surprise[t]}]),
                      "surprises_as_of": AS_OF, "as_of": AS_OF})
    (data / "earnings").mkdir(parents=True, exist_ok=True)
    pd.DataFrame(erows, index=pd.Index(idx, name="ticker")).to_parquet(
        data / "earnings" / "earnings.parquet")

    # guidance language hits: RICH gets TWO distinct raisers (clears the law), ONEF gets
    # ONE (must refuse), THIN gets none
    ghits = [{"ticker": "R1", "direction": "raise", "phrase": "raising guidance",
              "file_date": "2026-07-20"},
             {"ticker": "R2", "direction": "raise", "phrase": "raising guidance",
              "file_date": "2026-07-21"},
             {"ticker": "O1", "direction": "raise", "phrase": "raising guidance",
              "file_date": "2026-07-22"}]
    pd.DataFrame(ghits).to_parquet(data / "edgar" / "guidance_hits.parquet", index=False)

    # analyst revisions: 6 RICH members covered (4 up, 2 down) -> net_up_share 4/6; the
    # 2 uncovered members sit below MIN_ANALYSTS and must not enter n_covered
    rev_idx = RICH + THIN
    rev = pd.DataFrame({
        "breadth": [0.4, 0.3, 0.2, 0.1, -0.2, -0.3, 0.9, 0.9] + [0.5, 0.5, 0.5],
        "n_analysts": [9, 9, 9, 9, 9, 9, 1, 1] + [9, 9, 9],
    }, index=pd.Index(rev_idx))
    (data / "revisions").mkdir(parents=True, exist_ok=True)
    rev.to_parquet(data / "revisions" / "latest.parquet")

    monkeypatch.setattr(config, "data_dir", lambda: data)
    return {"sessions": sessions, "adj": adj, "event_pos": event_pos}


@pytest.fixture()
def pulse(tmp_path, monkeypatch):
    _write_tree(tmp_path, monkeypatch)
    out = ge.compute_group_earnings(write_ledger=False)
    assert out is not None, "synthetic sweep returned nothing"
    return out


# --------------------------------------------------------------------------- #
# the contract — owned by the test, applied to real engine output
# --------------------------------------------------------------------------- #
NUM = (int, float)
#: value -> the key that must accompany it. A stat may be null; its n may not be absent.
CONTRACT: dict = {
    "schema": (str,), "authority": (str,), "generated_at": (str,),
    "basket_id": (str,), "as_of": (str,),
    "season": {"n_members": (int,), "n_reported": (int,), "n_upcoming_14d": (int,),
               "next": (list,)},
    "results": {"n_beat": (int, type(None)), "n_miss": (int, type(None)),
                "n_inline": (int, type(None)), "n_no_data": (int,),
                "beat_basis": (str,)},
    "guidance": {"band": (str, type(None)), "n_filers": (int,), "basis": (str,)},
    "revisions": {"net_up_share": (*NUM, type(None)), "n_covered": (int,)},
    "drift": {"pos_share_5d": (*NUM, type(None)), "n": (int,)},
    "sympathy": {"ratio": (*NUM, type(None)), "n_events": (int,), "n_reporters": (int,),
                 "window_q": (int,), "basis": (str,),
                 "directional": {"beat_day_median": (*NUM, type(None)),
                                 "miss_day_median": (*NUM, type(None)),
                                 "n_beat_days": (int,), "n_miss_days": (int,)}},
}
NEXT_KEYS = {"ticker", "date", "session"}


def validate_pulse(obj, spec=CONTRACT, path="") -> list[str]:
    """Return the list of contract violations. Empty list == conformant."""
    bad: list[str] = []
    if not isinstance(obj, dict):
        return [f"{path or '<root>'}: not an object"]
    for k in obj:
        if k not in spec:
            bad.append(f"{path}{k}: UNKNOWN key")
    for k, want in spec.items():
        if k not in obj:
            bad.append(f"{path}{k}: MISSING key")
            continue
        v = obj[k]
        if isinstance(want, dict):
            bad += validate_pulse(v, want, f"{path}{k}.")
        elif not isinstance(v, want) or isinstance(v, bool):
            bad.append(f"{path}{k}: type {type(v).__name__} not in "
                       f"{[t.__name__ for t in want]}")
    if spec is CONTRACT:
        for e in obj.get("season", {}).get("next", []) or []:
            if set(e) != NEXT_KEYS:
                bad.append(f"{path}season.next: key set {sorted(e)} != {sorted(NEXT_KEYS)}")
    return bad


# --------------------------------------------------------------------------- #
# contract: golden + mutants
# --------------------------------------------------------------------------- #
def test_every_basket_is_contract_conformant(pulse):
    assert set(pulse) == {"rich", "thin", "onefiler"}
    for bid, obj in pulse.items():
        assert validate_pulse(obj) == [], f"{bid}: {validate_pulse(obj)}"
        assert obj["schema"] == "group_earnings_pulse.v1"
        assert obj["authority"] == "context_only"
        assert obj["basket_id"] == bid
        assert obj["as_of"] == AS_OF


def test_pulse_is_json_serialisable_without_a_default_hook(pulse):
    """The nightly writes this straight to site/basketdata/ — a Timestamp or numpy scalar
    that only survives because json.dumps was handed default=str is a contract leak."""
    json.dumps(pulse)


@pytest.mark.parametrize("mutate,why", [
    (lambda o: o.update({"confidence": 0.9}), "unknown top-level key"),
    (lambda o: o["sympathy"].update({"score": 1.0}), "unknown nested key"),
    (lambda o: o["sympathy"]["directional"].update({"pval": 0.01}), "unknown leaf key"),
    (lambda o: o["revisions"].pop("n_covered"), "missing n"),
    (lambda o: o["drift"].pop("n"), "missing n"),
    (lambda o: o["sympathy"].pop("n_events"), "missing n"),
    (lambda o: o["results"].pop("n_no_data"), "missing n"),
    (lambda o: o.pop("authority"), "missing authority"),
    (lambda o: o["season"]["next"].append({"ticker": "X"}), "malformed next entry"),
])
def test_contract_validator_rejects_mutants(pulse, mutate, why):
    obj = copy.deepcopy(pulse["rich"])
    assert validate_pulse(obj) == [], "the golden must be clean before it is mutated"
    if why == "malformed next entry" and not obj["season"]["next"]:
        obj["season"]["next"] = []
    mutate(obj)
    assert validate_pulse(obj) != [], f"validator missed: {why}"


def test_a_null_stat_is_legal_only_beside_its_own_n(pulse):
    """The refusal FORM: nulling a stat is conformant, dropping its n is not."""
    obj = copy.deepcopy(pulse["rich"])
    obj["revisions"]["net_up_share"] = None
    obj["drift"]["pos_share_5d"] = None
    obj["sympathy"]["ratio"] = None
    assert validate_pulse(obj) == []
    obj["revisions"].pop("n_covered")
    assert validate_pulse(obj) != []


# --------------------------------------------------------------------------- #
# floors — three members with GOOD data must still publish nulls
# --------------------------------------------------------------------------- #
#: `thin` has three members, each carrying a real surprise, a real analyst reading and a
#: real post-report price path. Three is below MIN_REPORTED / MIN_COVERED / MIN_DRIFT_N and
#: below the sympathy cohort minimum, so every one of those legs must publish null — a
#: 3-of-3 beat share here would be exactly the survivor-only number the floors suppress.
@pytest.mark.parametrize("leg,stat,n_key", [
    ("results", "n_beat", "n_no_data"),
    ("revisions", "net_up_share", "n_covered"),
    ("drift", "pos_share_5d", "n"),
    ("sympathy", "ratio", "n_events"),
])
def test_below_floor_legs_null_the_stat_and_still_print_the_n(pulse, leg, stat, n_key):
    thin = pulse["thin"]
    assert thin[leg][stat] is None, f"thin.{leg}.{stat} published below its floor"
    assert isinstance(thin[leg][n_key], int), f"thin.{leg}.{n_key} vanished with the stat"


def test_thin_members_really_do_carry_data(pulse):
    """Guards the guard: if the fixture stopped giving `thin` usable inputs the floor test
    above would pass for the wrong reason (no data, rather than data below the floor)."""
    assert pulse["thin"]["season"]["n_reported"] == 3
    assert pulse["thin"]["results"]["n_no_data"] == 3
    assert pulse["thin"]["revisions"]["n_covered"] == 3
    assert ge.MIN_REPORTED > 3 and ge.MIN_COVERED > 3 and ge.MIN_DRIFT_N > 3


def test_refused_results_names_its_floor_in_the_basis(pulse):
    assert "floor n_reported>=4" in pulse["thin"]["results"]["beat_basis"]
    assert "not met" in pulse["thin"]["results"]["beat_basis"]


def test_refused_sympathy_names_its_floors_in_the_basis(pulse):
    assert "n_events>=12" in pulse["thin"]["sympathy"]["basis"]
    assert "n_reporters>=4" in pulse["thin"]["sympathy"]["basis"]


# --------------------------------------------------------------------------- #
# resolution-conditioned denominator
# --------------------------------------------------------------------------- #
def test_results_counts_always_sum_to_n_members(pulse):
    for bid, obj in pulse.items():
        r, n = obj["results"], obj["season"]["n_members"]
        if r["n_beat"] is None:
            assert r["n_no_data"] == n, f"{bid}: refused results lost members"
            continue
        assert r["n_beat"] + r["n_miss"] + r["n_inline"] + r["n_no_data"] == n, bid


def test_members_without_a_surprise_land_in_no_data_not_out_of_the_denominator(pulse):
    """R7/R8 have 8-K report dates but no consensus, so they are reported-but-unclassified.
    A denominator that quietly shrank to the six classified members would read 4/6 beats
    where the honest read is 4 of 8 members, 2 of which have no data."""
    r = pulse["rich"]["results"]
    assert (r["n_beat"], r["n_miss"], r["n_inline"], r["n_no_data"]) == (4, 1, 1, 2)
    assert pulse["rich"]["season"]["n_members"] == 8


# --------------------------------------------------------------------------- #
# guidance: engine.guidance_gap's >=2-distinct-filers law, generalized
# --------------------------------------------------------------------------- #
def test_one_filer_refuses_the_band(pulse):
    g = pulse["onefiler"]["guidance"]
    assert g["n_filers"] == 1
    assert g["band"] is None, "a single filer produced a directional band"


def test_two_filers_clear_the_law_and_get_a_band(pulse):
    g = pulse["rich"]["guidance"]
    assert g["n_filers"] == 2
    assert g["band"] == "RAISING"


def test_no_filers_reads_null_not_neutral(pulse):
    g = pulse["thin"]["guidance"]
    assert (g["n_filers"], g["band"]) == (0, None)


def test_the_filer_floor_is_imported_from_guidance_gap_not_re_declared():
    """The law must live in ONE place. If guidance_gap raised MIN_FILERS this module would
    follow it; a local copy here would silently keep the old bar."""
    from engine import guidance_gap as gg
    assert gg.MIN_FILERS == 2
    assert not hasattr(ge, "MIN_FILERS"), "group_earnings re-declared the filer floor"
    assert "guidance_gap generalized" in ge.GUIDANCE_BASIS


def test_guidance_band_vocabulary_is_guidance_gaps(pulse):
    for obj in pulse.values():
        assert obj["guidance"]["band"] in {
            "RAISING", "NEUTRAL", "CUTTING", "BROAD-RAISE", None}


# --------------------------------------------------------------------------- #
# season + drift arithmetic
# --------------------------------------------------------------------------- #
def test_season_counts_the_current_cycle_only(pulse):
    s = pulse["rich"]["season"]
    assert s["n_members"] == 8
    assert s["n_reported"] == 8, "one report per member should fall in the 75-session cycle"


def test_a_member_last_seen_two_cycles_ago_has_not_reported_this_season(pulse):
    """O5's only report sits 200 sessions back — well outside the 75-session cycle. It is a
    live member (so it counts in n_members) that has NOT reported (so it is n_no_data). An
    unbounded season window would count it and turn 4-of-5 into 5-of-5."""
    s, r = pulse["onefiler"]["season"], pulse["onefiler"]["results"]
    assert s["n_members"] == 5
    assert s["n_reported"] == 4, "a two-cycle-old report was counted as this season"
    assert (r["n_beat"], r["n_miss"], r["n_inline"], r["n_no_data"]) == (4, 0, 0, 1)
    assert ge.SEASON_LOOKBACK_SESSIONS == 75


def test_upcoming_window_is_14_calendar_days_with_a_mapped_session(pulse):
    nxt = pulse["rich"]["season"]["next"]
    assert pulse["rich"]["season"]["n_upcoming_14d"] == 2
    assert [e["ticker"] for e in nxt] == ["R1", "R2"]
    assert [e["session"] for e in nxt] == ["amc", "bmo"]
    assert all(e["date"] == "2026-08-12" for e in nxt)


def test_the_next_preview_is_capped_but_the_count_is_not(tmp_path, monkeypatch):
    """`next` is a preview list, `n_upcoming_14d` is the answer. With all eight members
    reporting inside the window the count must read 8 while the list stops at MAX_NEXT —
    a surface that counted len(next) would under-report a busy week."""
    _write_tree(tmp_path, monkeypatch)
    p = config.data_dir() / "earnings" / "earnings.parquet"
    df = pd.read_parquet(p)
    # dates run OPPOSITE to ticker order, so a preview that kept roster order rather than
    # sorting by date would hand the surface the six FURTHEST-away reports
    for i, t in enumerate(RICH):
        df.loc[t, "next_date"] = (pd.Timestamp(AS_OF) + pd.Timedelta(days=len(RICH) - i)
                                  ).date().isoformat()
        df.loc[t, "next_time"] = "time-after-hours"
    df.to_parquet(p)
    s = ge.compute_group_earnings(write_ledger=False)["rich"]["season"]
    assert s["n_upcoming_14d"] == 8
    assert len(s["next"]) == ge.MAX_NEXT == 6
    assert [e["ticker"] for e in s["next"]] == RICH[::-1][:6], "the preview is not soonest-first"


def test_unmapped_next_time_reads_unknown_never_a_guess(pulse):
    """`time-not-supplied` must surface as "unknown" — the onefiler members carry it, and
    their next_date is outside the window, so the count is 0 with no fabricated session."""
    assert pulse["onefiler"]["season"]["n_upcoming_14d"] == 0
    assert ge._SESSION_MAP.get("time-not-supplied") is None


def test_drift_is_the_five_sessions_after_the_reaction_close(pulse):
    """Six of the eight RICH members compound +1%/session (SPY-adjusted) over their five
    post-report sessions; R7 and R8 compound -1%. The fixture never touches the reaction
    day itself, so a drift leg measuring THROUGH the gap instead of AFTER it would not
    produce 6/8."""
    d = pulse["rich"]["drift"]
    assert d["n"] == 8
    assert d["pos_share_5d"] == pytest.approx(0.75)


def test_drift_horizon_is_five_sessions_not_the_first_one(tmp_path, monkeypatch):
    """A pop-then-fade path: +5% on the session after the print, then -2% for four more.
    One session out every member is up; five sessions out every member is down. A drift leg
    reading any horizon shorter than DRIFT_SESSIONS would publish 1.0 instead of 0.0."""
    _write_tree(tmp_path, monkeypatch)
    sessions = _sessions()
    n = len(sessions)
    for i, t in enumerate(RICH):
        adj = pd.Series(QUIET_ADJ, index=sessions)
        p = n + _rich_event_index(i, 0)
        adj.iloc[p + 1] = 0.05
        adj.iloc[p + 2:p + 6] = -0.02
        adj.iloc[0] = 0.0
        close = 100.0 * (1.0 + adj + SPY_DAILY).cumprod()
        pd.DataFrame({"close": close.to_numpy()},
                     index=pd.DatetimeIndex(sessions, name="Date")).to_parquet(
            config.data_dir() / "baskets" / "ohlcv" / f"{t}.parquet")
    out = ge.compute_group_earnings(write_ledger=False)
    assert out["rich"]["drift"]["n"] == 8
    assert out["rich"]["drift"]["pos_share_5d"] == pytest.approx(0.0)
    assert ge.DRIFT_SESSIONS == 5


def test_drift_subtracts_the_benchmark(tmp_path, monkeypatch):
    """With the member's raw path set to exactly SPY's, the adjusted drift is zero — so no
    member counts as positive and the share is 0.0, not 1.0."""
    _write_tree(tmp_path, monkeypatch)
    sessions = _sessions()
    flat = 100.0 * (1.0 + pd.Series(SPY_DAILY, index=sessions)).cumprod()
    for t in RICH:
        pd.DataFrame({"close": flat.to_numpy()},
                     index=pd.DatetimeIndex(sessions, name="Date")).to_parquet(
            config.data_dir() / "baskets" / "ohlcv" / f"{t}.parquet")
    out = ge.compute_group_earnings(write_ledger=False)
    assert out["rich"]["drift"]["n"] == 8
    assert out["rich"]["drift"]["pos_share_5d"] == pytest.approx(0.0)


# --------------------------------------------------------------------------- #
# point-in-time roster
# --------------------------------------------------------------------------- #
AS_OF_TS = pd.Timestamp(AS_OF)


@pytest.mark.parametrize("added,removed,live,why", [
    ("2020-01-02", None, True, "added long ago, never removed"),
    (AS_OF, None, True, "added ON the run date is live (the [added, removed) mask)"),
    ("2026-08-08", None, False, "added tomorrow is not live today"),
    ("2020-01-02", "2026-08-08", True, "removed tomorrow is still live today"),
    ("2020-01-02", AS_OF, False, "removed ON the run date is out"),
    ("2020-01-02", "2024-01-02", False, "removed two years ago is out"),
])
def test_live_membership_is_point_in_time(added, removed, live, why):
    """The roster is the one engine.baskets._ew_level uses: a member counts on [added,
    removed). A departed name that stayed in the count would put its earnings into a basket
    that no longer holds it."""
    basket = {"members": [{"ticker": "X", "added": added, "removed": removed}]}
    assert (ge._live_members(basket, AS_OF_TS) == ["X"]) is live, why


def test_a_removed_member_leaves_the_denominator_entirely(tmp_path, monkeypatch):
    """Not n_no_data — GONE. n_no_data is for a live member we cannot resolve; a removed
    member is not part of the basket at all."""
    _write_tree(tmp_path, monkeypatch)
    path = config.data_dir() / "baskets" / "membership.json"
    reg = json.loads(path.read_text())
    reg["baskets"]["rich"]["members"][-1]["removed"] = "2026-01-05"
    path.write_text(json.dumps(reg))
    out = ge.compute_group_earnings(write_ledger=False)
    r = out["rich"]
    assert r["season"]["n_members"] == 7, "a removed member stayed in the roster"
    assert r["results"]["n_beat"] + r["results"]["n_miss"] + r["results"]["n_inline"] \
        + r["results"]["n_no_data"] == 7


def test_a_member_added_after_the_run_date_is_not_counted_yet(tmp_path, monkeypatch):
    _write_tree(tmp_path, monkeypatch)
    path = config.data_dir() / "baskets" / "membership.json"
    reg = json.loads(path.read_text())
    reg["baskets"]["rich"]["members"][-1]["added"] = "2027-01-04"
    path.write_text(json.dumps(reg))
    out = ge.compute_group_earnings(write_ledger=False)
    assert out["rich"]["season"]["n_members"] == 7


# --------------------------------------------------------------------------- #
# revisions
# --------------------------------------------------------------------------- #
def test_net_up_share_counts_only_members_clearing_the_coverage_gate(pulse):
    """R7/R8 carry breadth 0.9 but only one analyst each. Admitting them would push the
    share from 4/6 to 6/8; the imported MIN_ANALYSTS gate must keep them out."""
    r = pulse["rich"]["revisions"]
    assert r["n_covered"] == 6
    assert r["net_up_share"] == pytest.approx(round(4 / 6, 3))


def test_coverage_gate_is_imported_from_theme_revisions():
    from engine.theme_revisions import MIN_ANALYSTS
    assert MIN_ANALYSTS == 3
    assert not hasattr(ge, "MIN_ANALYSTS"), "group_earnings re-declared the coverage gate"


# --------------------------------------------------------------------------- #
# degradation — a missing store nulls its leg and never raises into the nightly
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("victim,leg,stat", [
    ("edgar/guidance_hits.parquet", "guidance", "band"),
    ("revisions/latest.parquet", "revisions", "net_up_share"),
])
def test_a_missing_store_nulls_its_leg_and_leaves_the_rest_intact(
        tmp_path, monkeypatch, victim, leg, stat):
    _write_tree(tmp_path, monkeypatch)
    (config.data_dir() / victim).unlink()
    out = ge.compute_group_earnings(write_ledger=False)
    assert out is not None, "a missing side store took the whole sweep down"
    assert out["rich"][leg][stat] is None
    assert validate_pulse(out["rich"]) == []
    assert out["rich"]["sympathy"]["ratio"] is not None, "an unrelated leg was collateral"


def test_missing_earnings_store_still_publishes_a_conformant_object(tmp_path, monkeypatch):
    _write_tree(tmp_path, monkeypatch)
    (config.data_dir() / "earnings" / "earnings.parquet").unlink()
    out = ge.compute_group_earnings(write_ledger=False)
    assert out is not None
    rich = out["rich"]
    assert validate_pulse(rich) == []
    assert rich["results"]["n_beat"] is None          # no consensus anywhere -> refused
    assert rich["results"]["n_no_data"] == 8
    assert rich["season"]["n_upcoming_14d"] == 0
    assert rich["sympathy"]["ratio"] is not None      # the 8-K spine still carries events


def test_no_registry_returns_none_rather_than_a_fabricated_sweep(tmp_path, monkeypatch):
    _write_tree(tmp_path, monkeypatch)
    (config.data_dir() / "baskets" / "membership.json").unlink()
    assert ge.compute_group_earnings(write_ledger=False) is None


# --------------------------------------------------------------------------- #
# nightly wiring: the sweep advances the ledger, and a broken ledger never stops it
# --------------------------------------------------------------------------- #
def test_the_nightly_sweep_advances_the_sympathy_ledger(tmp_path, monkeypatch):
    _write_tree(tmp_path, monkeypatch)
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    out = ge.compute_group_earnings()
    assert out is not None
    df = pd.read_parquet(ge.sympathy_ledger_path())
    assert not df.duplicated(subset=ge.LEDGER_KEY).any()
    # `rich` logs its 48 events; `onefiler` logs the one event day where a lone reporter
    # left a big enough cohort. `thin` has too few members to form a cohort at all.
    assert dict(df["basket_id"].value_counts()) == {"rich": 48, "onefiler": 1}
    # the ledger accrues FACTS, not display-eligible stats: onefiler's sympathy block is
    # refused for display and its event day is recorded anyway
    assert out["onefiler"]["sympathy"]["ratio"] is None


def test_a_failing_ledger_append_never_takes_the_sweep_down(tmp_path, monkeypatch):
    _write_tree(tmp_path, monkeypatch)
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    monkeypatch.setattr(ge, "append_sympathy_ledger",
                        lambda rows: (_ for _ in ()).throw(RuntimeError("boom")))
    out = ge.compute_group_earnings()
    assert out is not None, "a ledger failure propagated into the nightly build"
    assert validate_pulse(out["rich"]) == []


def test_write_earnings_pulse_emits_the_named_artifact(tmp_path, monkeypatch):
    _write_tree(tmp_path, monkeypatch)
    out_dir = tmp_path / "site" / "basketdata"
    assert ge.write_earnings_pulse(out_dir) is not None
    written = json.loads((out_dir / "earnings_pulse.json").read_text())
    assert set(written) == {"rich", "thin", "onefiler"}
    for obj in written.values():
        assert validate_pulse(obj) == []


def test_end_to_end_sympathy_ratio_is_the_fixtures_arithmetic(pulse):
    """Quiet sessions move each member +1% SPY-adjusted, member report days +2%. A leg that
    skipped the benchmark subtraction would read 2.1/1.1 = 1.91, not 2.0."""
    s = pulse["rich"]["sympathy"]
    assert s["ratio"] == pytest.approx(EVENT_ADJ / QUIET_ADJ)      # 2.0
    assert s["n_events"] == 48 and s["n_reporters"] == 8


def test_end_to_end_directional_split_refuses_on_its_own_floor(pulse):
    """Only the latest quarter carries a surprise in the fixture, so four beat days and one
    miss day — both below MIN_DIRECTIONAL_DAYS. The medians null; the counts do not."""
    d = pulse["rich"]["sympathy"]["directional"]
    assert (d["n_beat_days"], d["n_miss_days"]) == (4, 1)
    assert d["beat_day_median"] is None and d["miss_day_median"] is None
