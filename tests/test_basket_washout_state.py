"""tests/test_basket_washout_state.py — frozen contract + PIT sanity for the nightly
`site/factordata/basket_washout_state.json` artifact (ratified blocked-entry override,
construction A1b; `research/BLOCKED_ENTRY_RATIFICATION_PACKET_2026-08-10.md` §4).

Covers:
  (1) frozen v1 contract shape — exact key sets, types, threshold menu, id/qualifies keys
  (2) PIT sanity — `qualifies` flips EXACTLY at the threshold, boundary inclusive, and is
      always re-derivable from the PUBLISHED (rounded) number; the NAME map is
      LEAVE-ONE-OUT (the graded per-event quantity) while the BASKET map is the plain
      group median, so a deep name cannot vote itself into its own washout evidence
  (3) omitted-name behaviour — a name in neither mapping is absent, never defaulted
  (4) degrade — empty/broken membership store still emits the sector arm; a group thinner
      than MIN_PEERS states nothing and its names fall back to sector
  (5) construction — 252d/min-60 drawdown formula, primary-basket selection (smallest
      basket, ties by id), members with no print on `as_of` drop out of the median
  (6) banned vocabulary — no "validated" and no falsifier/refutation language in the
      module's own copy or in any string it emits

All hermetic: synthetic frames + tmp_path, no repo data and no network.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from scripts import build_basket_washout_state as B  # noqa: E402

THR_KEYS = {"20", "25", "30"}


# --------------------------------------------------------------------- helpers --
def _dd(*values: float, start: str = "2026-08-03") -> pd.Series:
    """A ready-made drawdown series: the LAST value is what `as_of` reads."""
    idx = pd.bdate_range(start, periods=len(values))
    return pd.Series([float(v) for v in values], index=idx, dtype="float64")


def _flat_group(prefix: str, n: int, level: float, as_of: pd.Timestamp) -> dict[str, pd.Series]:
    return {f"{prefix}{i}": pd.Series([level], index=[as_of], dtype="float64") for i in range(n)}


def _defs(**kw: list[str]) -> dict[str, dict]:
    return {bid: {"name": bid.title(), "name_zh": f"ZH-{bid}", "members": sorted(members)}
            for bid, members in kw.items()}


# ------------------------------------------------------------ (1) contract shape --
def test_contract_shape_is_frozen_v1():
    as_of = pd.Timestamp("2026-08-07")
    dd = _flat_group("U", 6, -0.31, as_of) | _flat_group("F", 6, -0.05, as_of)
    defs = _defs(uranium_miners=[f"U{i}" for i in range(6)])
    sectors = {f"F{i}": "Financials" for i in range(6)}
    out = B.build_state(defs, sectors, dd, as_of=as_of)

    assert set(out) == {"schema", "as_of", "thresholds", "baskets", "names"}
    assert out["schema"] == "basket_washout_state.v1"
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", out["as_of"])
    assert out["thresholds"] == [20, 25, 30]

    b = out["baskets"]["uranium_miners"]
    assert set(b) == {"name", "name_zh", "peer_median_dd_252", "n_members", "qualifies"}
    assert isinstance(b["name"], str) and isinstance(b["name_zh"], str)
    assert isinstance(b["peer_median_dd_252"], float)
    assert isinstance(b["n_members"], int) and b["n_members"] == 6
    assert set(b["qualifies"]) == THR_KEYS
    assert all(isinstance(v, bool) for v in b["qualifies"].values())

    n = out["names"]["U0"]
    assert set(n) == {"basis", "group_id", "peer_dd", "qualifies"}
    assert n["basis"] == "basket" and n["group_id"] == "uranium_miners"
    assert set(n["qualifies"]) == THR_KEYS
    assert out["names"]["F0"]["basis"] == "sector"
    assert out["names"]["F0"]["group_id"] == "Financials"


def test_payload_is_json_serialisable_and_round_trips(tmp_path):
    as_of = pd.Timestamp("2026-08-07")
    dd = _flat_group("U", 6, -0.31, as_of)
    out = B.build_state(_defs(uranium_miners=[f"U{i}" for i in range(6)]), {}, dd, as_of=as_of)
    p = tmp_path / "basket_washout_state.json"
    B.write_state(out, p)
    assert json.loads(p.read_text()) == out
    assert not list(tmp_path.glob("*.tmp")), "atomic write must not leave a temp file behind"


# --------------------------------------------------------------- (2) PIT sanity --
@pytest.mark.parametrize(
    "level, expect",
    [
        (-0.1999, {"20": False, "25": False, "30": False}),
        (-0.20, {"20": True, "25": False, "30": False}),       # boundary is INCLUSIVE
        (-0.2000001, {"20": True, "25": False, "30": False}),
        (-0.2499994, {"20": True, "25": False, "30": False}),   # publishes -0.249999
        (-0.2499999, {"20": True, "25": True, "30": False}),    # publishes -0.25 -> flips WITH it
        (-0.25, {"20": True, "25": True, "30": False}),
        (-0.2999, {"20": True, "25": True, "30": False}),
        (-0.30, {"20": True, "25": True, "30": True}),
        (-0.55, {"20": True, "25": True, "30": True}),
        (0.0, {"20": False, "25": False, "30": False}),
    ],
)
def test_qualifies_flips_exactly_at_the_threshold(level, expect):
    as_of = pd.Timestamp("2026-08-07")
    dd = _flat_group("U", 6, level, as_of)
    out = B.build_state(_defs(theme=[f"U{i}" for i in range(6)]), {}, dd, as_of=as_of)
    assert out["baskets"]["theme"]["qualifies"] == expect
    assert out["names"]["U0"]["qualifies"] == expect


def test_qualifies_is_rederivable_from_the_published_number():
    """A consumer recomputing the flag from the printed value must always agree with us —
    the flag is computed from the ROUNDED number, not from an unpublished full-precision one."""
    as_of = pd.Timestamp("2026-08-07")
    rng = np.random.default_rng(20260810)
    dd, defs_members = {}, []
    for g in range(12):
        lvl = float(rng.uniform(-0.6, 0.0))
        dd |= _flat_group(f"G{g}_", 6, lvl, as_of)
        defs_members.append((f"basket{g}", [f"G{g}_{i}" for i in range(6)]))
    out = B.build_state(_defs(**dict(defs_members)), {}, dd, as_of=as_of)
    for entry in list(out["baskets"].values()):
        v = entry["peer_median_dd_252"]
        assert entry["qualifies"] == {str(t): v <= -t / 100.0 for t in (20, 25, 30)}
    for entry in list(out["names"].values()):
        v = entry["peer_dd"]
        assert entry["qualifies"] == {str(t): v <= -t / 100.0 for t in (20, 25, 30)}


def test_name_peer_dd_is_leave_one_out_and_the_basket_map_is_not():
    """The two maps answer different questions: the basket prints its own plain median,
    the NAME prints its peers with itself removed (the graded per-event quantity)."""
    as_of = pd.Timestamp("2026-08-07")
    vals = {"A": -0.90, "B": -0.50, "C": -0.30, "D": -0.10, "E": 0.0}
    dd = {t: pd.Series([v], index=[as_of], dtype="float64") for t, v in vals.items()}
    out = B.build_state(_defs(theme=list(vals)), {}, dd, as_of=as_of)

    assert out["baskets"]["theme"]["peer_median_dd_252"] == pytest.approx(-0.30)
    assert out["names"]["A"]["peer_dd"] == pytest.approx(-0.20)   # median(-.5,-.3,-.1, 0)
    assert out["names"]["E"]["peer_dd"] == pytest.approx(-0.40)   # median(-.9,-.5,-.3,-.1)
    assert out["names"]["C"]["peer_dd"] == pytest.approx(-0.30)   # median(-.9,-.5,-.1, 0)
    assert len({e["peer_dd"] for e in out["names"].values()}) > 1, \
        "names inside one basket must NOT all print the same number"


def test_a_deep_name_cannot_vote_itself_into_its_own_washout_evidence():
    """The whole point of the leave-one-out read: the fired name is usually among the
    deepest in its basket, and must not be able to drag the median over the line for
    itself.  Group median clears 25%; the name that caused it does not."""
    as_of = pd.Timestamp("2026-08-07")
    vals = {"DEEP": -0.90, "B": -0.30, "C": -0.26, "D": -0.20, "E": -0.18}
    dd = {t: pd.Series([v], index=[as_of], dtype="float64") for t, v in vals.items()}
    out = B.build_state(_defs(theme=list(vals)), {}, dd, as_of=as_of)

    assert out["baskets"]["theme"]["qualifies"]["25"] is True     # group median -0.26
    assert out["names"]["DEEP"]["peer_dd"] == pytest.approx(-0.23)
    assert out["names"]["DEEP"]["qualifies"]["25"] is False       # its OWN peers do not
    assert out["names"]["E"]["qualifies"]["25"] is True           # a shallow member's do


def test_leave_one_out_helper_is_a_true_exclusion():
    vals = {"A": -0.9, "B": -0.5, "C": -0.3, "D": -0.1, "E": 0.0}
    assert B.leave_one_out_median(vals, "A") == pytest.approx(-0.20)
    assert B.leave_one_out_median(vals, "NOT_A_MEMBER") == pytest.approx(-0.30)
    assert B.leave_one_out_median({"A": -0.3}, "A") is None


def test_min_peers_floor_applies_to_the_full_group_so_five_leaves_four():
    """Mirrors r3_axes.py: the >=5 floor is checked BEFORE the name is removed."""
    as_of = pd.Timestamp("2026-08-07")
    dd = _flat_group("U", B.MIN_PEERS, -0.33, as_of)
    out = B.build_state(_defs(theme=[f"U{i}" for i in range(B.MIN_PEERS)]), {}, dd, as_of=as_of)
    assert out["baskets"]["theme"]["n_members"] == B.MIN_PEERS
    assert len(out["names"]) == B.MIN_PEERS
    assert out["names"]["U0"]["peer_dd"] == pytest.approx(-0.33)


# ---------------------------------------------------------- (3) omitted names --
def test_name_in_neither_mapping_is_omitted_never_defaulted():
    as_of = pd.Timestamp("2026-08-07")
    dd = _flat_group("U", 6, -0.4, as_of) | {"ORPHAN": pd.Series([-0.9], index=[as_of])}
    out = B.build_state(_defs(theme=[f"U{i}" for i in range(6)]), {}, dd, as_of=as_of)
    assert "ORPHAN" not in out["names"]
    assert "U0" in out["names"]


def test_sector_only_name_with_no_price_of_its_own_still_reads_its_peers():
    """peer_dd never depends on the name's OWN price — a mapped name with no series still
    reads its group (and a name mapped nowhere is still omitted)."""
    as_of = pd.Timestamp("2026-08-07")
    dd = _flat_group("S", 6, -0.33, as_of)
    sectors = {f"S{i}": "Energy" for i in range(6)} | {"NOPRICE": "Energy"}
    out = B.build_state({}, sectors, dd, as_of=as_of)
    assert out["names"]["NOPRICE"]["group_id"] == "Energy"
    assert out["names"]["NOPRICE"]["peer_dd"] == pytest.approx(-0.33)


# ---------------------------------------------------------------- (4) degrade --
def test_empty_membership_store_still_emits_the_sector_arm():
    as_of = pd.Timestamp("2026-08-07")
    dd = _flat_group("S", 7, -0.28, as_of)
    out = B.build_state({}, {f"S{i}": "Materials" for i in range(7)}, dd, as_of=as_of)
    assert out["baskets"] == {}
    assert len(out["names"]) == 7
    assert out["names"]["S0"] == {
        "basis": "sector", "group_id": "Materials", "peer_dd": -0.28,
        "qualifies": {"20": True, "25": True, "30": False},
    }


def test_missing_membership_file_degrades_without_raising(tmp_path, capsys):
    assert B.load_basket_defs(tmp_path) == {}
    line = capsys.readouterr().out.strip().splitlines()[0]
    assert line.startswith("::warning"), "GitHub annotations must START the line"


def test_group_thinner_than_min_peers_states_nothing_and_falls_back():
    as_of = pd.Timestamp("2026-08-07")
    thin = B.MIN_PEERS - 1
    dd = _flat_group("U", thin, -0.55, as_of) | _flat_group("E", 6, -0.10, as_of)
    sectors = {f"U{i}": "Energy" for i in range(thin)} | {f"E{i}": "Energy" for i in range(6)}
    out = B.build_state(_defs(tiny=[f"U{i}" for i in range(thin)] + ["GHOST", "GHOST2"]),
                        sectors, dd, as_of=as_of)
    assert "tiny" not in out["baskets"], "a group under the peer floor must be omitted"
    assert out["names"]["U0"]["basis"] == "sector"
    assert out["names"]["U0"]["group_id"] == "Energy"


def test_no_data_at_all_emits_an_empty_but_well_formed_payload():
    out = B.build_state({}, {}, {})
    assert out["schema"] == "basket_washout_state.v1"
    assert out["as_of"] is None and out["baskets"] == {} and out["names"] == {}
    assert out["thresholds"] == [20, 25, 30]


def test_main_leaves_the_previous_artifact_in_place_when_nothing_computes(tmp_path, capsys):
    out = tmp_path / "site" / "factordata" / "basket_washout_state.json"
    out.parent.mkdir(parents=True)
    out.write_text('{"schema":"basket_washout_state.v1","keep":"me"}')
    rc = B.main(["--data-root", str(tmp_path / "empty-data"), "--out", str(out)])
    assert rc == 0
    assert json.loads(out.read_text())["keep"] == "me"
    assert "::warning" in capsys.readouterr().out


# ------------------------------------------------------------ (5) construction --
def test_drawdown_is_close_over_trailing_252_max():
    n = 300
    close = pd.Series(np.linspace(100.0, 200.0, n),
                      index=pd.bdate_range("2025-01-01", periods=n))
    close.iloc[-1] = 150.0                       # a 25% haircut off the running high (200)
    dd = B.drawdown_series(close)
    assert dd.iloc[-1] == pytest.approx(150.0 / close.iloc[-2] - 1.0)
    assert dd.iloc[:B.MIN_PERIODS - 1].isna().all(), "no high before min_periods"
    assert dd.max() <= 1e-12, "drawdown is never positive"


def test_drawdown_window_is_252_sessions_not_all_history():
    idx = pd.bdate_range("2024-01-01", periods=600)
    close = pd.Series(50.0, index=idx)
    close.iloc[0] = 1000.0                       # an ancient high, far outside the window
    dd = B.drawdown_series(close)
    assert dd.iloc[-1] == pytest.approx(0.0), "a high older than 252 sessions must roll off"


def test_primary_basket_is_the_smallest_claiming_group_ties_by_id():
    defs = _defs(
        zzz_small=["X", "A", "B", "C", "D"],                       # 5 members
        aaa_small=["X", "E", "F", "G", "H"],                       # 5 members — tie, wins by id
        big=["X"] + [f"N{i}" for i in range(20)],
        thin=["X", "Y"],                                           # under the floor: never claims
    )
    assert B.primary_basket(defs, "X") == "aaa_small"
    assert B.primary_basket(defs, "Y") is None
    assert B.primary_basket(defs, "N0") == "big"
    assert B.primary_basket(defs, "NOPE") is None


def test_members_with_no_print_on_as_of_drop_out_of_the_median():
    as_of = pd.Timestamp("2026-08-07")
    stale = pd.Timestamp("2026-06-01")
    dd = _flat_group("A", 5, -0.10, as_of)
    dd |= {f"H{i}": pd.Series([-0.90], index=[stale], dtype="float64") for i in range(4)}
    med, n = B.group_median(dd, sorted(dd), as_of)
    assert n == 5 and med == pytest.approx(-0.10)


def test_group_median_is_a_true_median_of_the_printing_members():
    as_of = pd.Timestamp("2026-08-07")
    dd = {t: pd.Series([v], index=[as_of], dtype="float64")
          for t, v in zip("ABCDE", (-0.9, -0.5, -0.3, -0.1, 0.0))}
    med, n = B.group_median(dd, list("ABCDE"), as_of)
    assert n == 5 and med == pytest.approx(-0.3)


def test_n_members_counts_only_the_members_that_priced():
    as_of = pd.Timestamp("2026-08-07")
    dd = _flat_group("U", 6, -0.4, as_of)
    out = B.build_state(_defs(theme=[f"U{i}" for i in range(6)] + ["DELISTED"]), {}, dd,
                        as_of=as_of)
    assert out["baskets"]["theme"]["n_members"] == 6


def test_removed_members_are_dropped_from_the_roster(tmp_path):
    (tmp_path / "baskets").mkdir()
    (tmp_path / "baskets" / "membership.json").write_text(json.dumps({"baskets": {
        "silver_miners": {"name": "Silver Miners", "name_zh": "白银矿业", "members": [
            {"ticker": "HL"}, {"ticker": "AG"},
            {"ticker": "GONE", "removed": "2026-01-02"},
        ]},
    }}))
    defs = B.load_basket_defs(tmp_path)
    assert defs["silver_miners"]["members"] == ["AG", "HL"]
    assert defs["silver_miners"]["name_zh"] == "白银矿业"


# ---------------------------------------------------------- (6) banned copy --
_BANNED = re.compile(
    r"\bvalidated\b|\bfalsif\w*|\brefut\w*|\bthesis (?:refuted|broken)\b|证伪", re.I)


# ------------------------------------------------- (7) history intervals (v1) --
def _hist(defs, sectors, dd, as_of):
    state = B.build_state(defs, sectors, dd, as_of=as_of)
    return state, B.build_history(dd, defs, sectors, state)


def _ramp(values, start="2026-07-01"):
    idx = pd.bdate_range(start, periods=len(values))
    return pd.Series([float(v) for v in values], index=idx, dtype="float64")


def _open_at(h: dict, ticker: str, notch: str) -> bool:
    e = h["names"].get(ticker)
    if not e or not e["intervals"][notch]:
        return False
    return e["intervals"][notch][-1][1] is None


def test_history_contract_shape():
    as_of = pd.Timestamp("2026-08-07")
    defs = _defs(theme=[f"U{i}" for i in range(6)])
    dd = _flat_group("U", 6, -0.27, as_of)
    state = B.build_state(defs, {}, dd, as_of=as_of)
    h = B.build_history(dd, defs, {}, state)

    assert set(h) == {"schema", "as_of", "notches", "notes", "names"}
    assert h["schema"] == "basket_washout_history.v1"
    assert h["notches"] == [20, 25, 30]
    assert h["as_of"] == "2026-08-07"
    assert set(h["names"]["U0"]) == {"basis", "group_id", "intervals"}
    # -0.27 clears 20 and 25 but not 30 — and all three keys are always present
    assert set(h["names"]["U0"]["intervals"]) == THR_KEYS
    assert h["names"]["U0"]["intervals"]["20"] == [["2026-08-07", None]]
    assert h["names"]["U0"]["intervals"]["25"] == [["2026-08-07", None]]
    assert h["names"]["U0"]["intervals"]["30"] == []
    # the honesty note is part of the contract, not decoration
    for phrase in ("retro-applied", "TODAY's basket rosters", "INCLUSIVE", "per notch"):
        assert phrase.lower() in h["notes"].lower()
    assert not _BANNED.search(json.dumps(h, ensure_ascii=False))


def test_intervals_open_and_close_exactly_at_the_notch_crossings():
    """Five sessions: below, below, ABOVE, below, below -> two runs, the first one closed
    at the last qualifying date (inclusive), the second open because it reaches as_of."""
    levels = [-0.27, -0.27, -0.10, -0.27, -0.27]
    dd = {f"U{i}": _ramp(levels) for i in range(6)}
    as_of = dd["U0"].index[-1]
    _, h = _hist(_defs(theme=[f"U{i}" for i in range(6)]), {}, dd, as_of)
    idx = [str(d.date()) for d in dd["U0"].index]
    assert h["names"]["U0"]["intervals"]["25"] == [[idx[0], idx[1]], [idx[3], None]]
    assert h["names"]["U0"]["intervals"]["20"] == [[idx[0], idx[1]], [idx[3], None]]
    assert h["names"]["U0"]["intervals"]["30"] == []


def test_each_notch_is_drawn_independently_and_nests():
    """A looser notch can only ever cover MORE dates than a tighter one — the three keys
    are three readings of one series, so their qualifying date sets must nest 30 ⊆ 25 ⊆ 20."""
    levels = [-0.10, -0.22, -0.27, -0.33, -0.27, -0.22]
    dd = {f"U{i}": _ramp(levels) for i in range(6)}
    as_of = dd["U0"].index[-1]
    _, h = _hist(_defs(theme=[f"U{i}" for i in range(6)]), {}, dd, as_of)
    idx = [str(d.date()) for d in dd["U0"].index]
    iv = h["names"]["U0"]["intervals"]
    assert iv["20"] == [[idx[1], None]]            # still under -20% on as_of -> open
    assert iv["25"] == [[idx[2], idx[4]]]          # closed: back above -25% before as_of
    assert iv["30"] == [[idx[3], idx[3]]]          # a single session at -0.33

    def dates(spans):
        out = set()
        for a, b in spans:
            hi = as_of if b is None else pd.Timestamp(b)
            out |= {str(d.date()) for d in pd.bdate_range(a, hi)}
        return out

    assert dates(iv["30"]) <= dates(iv["25"]) <= dates(iv["20"])


def test_history_is_leave_one_out_and_agrees_with_the_state_artifact_on_as_of():
    """The LOO fidelity gate: on `as_of`, having an OPEN interval at a notch must mean
    exactly the same thing as the state artifact's qualifies[notch] — every name, every
    notch, both directions."""
    rng = np.random.default_rng(20260810)
    dd, members = {}, []
    for g in range(6):
        for i in range(7):
            t = f"G{g}_{i}"
            dd[t] = _ramp(rng.uniform(-0.45, -0.05, size=9))
            members.append((g, t))
    defs = _defs(**{f"b{g}": [t for gg, t in members if gg == g] for g in range(6)})
    as_of = dd["G0_0"].index[-1]
    state, h = _hist(defs, {}, dd, as_of)

    for notch in sorted(THR_KEYS):
        assert any(v["qualifies"][notch] for v in state["names"].values()), f"notch {notch}"
        assert any(not v["qualifies"][notch] for v in state["names"].values())
        for t, e in state["names"].items():
            assert _open_at(h, t, notch) == e["qualifies"][notch], \
                f"{t} @ {notch}: interval and state disagree on as_of"


def test_history_uses_the_states_group_assignment():
    as_of = pd.Timestamp("2026-08-07")
    dd = _flat_group("U", 6, -0.40, as_of) | _flat_group("S", 6, -0.33, as_of)
    defs = _defs(theme=[f"U{i}" for i in range(6)])
    sectors = {f"S{i}": "Energy" for i in range(6)}
    state, h = _hist(defs, sectors, dd, as_of)
    for t, e in h["names"].items():
        assert (e["basis"], e["group_id"]) == (state["names"][t]["basis"],
                                               state["names"][t]["group_id"])
    assert h["names"]["S0"]["basis"] == "sector"


def test_names_that_never_qualify_are_omitted_not_emitted_empty():
    as_of = pd.Timestamp("2026-08-07")
    dd = _flat_group("U", 6, -0.05, as_of)
    _, h = _hist(_defs(theme=[f"U{i}" for i in range(6)]), {}, dd, as_of)
    assert h["names"] == {}


def test_a_session_the_name_did_not_print_breaks_its_run():
    """No print = no reading for that name that session, so the run splits rather than
    being bridged."""
    idx = pd.bdate_range("2026-07-01", periods=5)
    dd = {f"U{i}": pd.Series([-0.30] * 5, index=idx, dtype="float64") for i in range(6)}
    dd["U0"] = dd["U0"].drop(idx[2])
    _, h = _hist(_defs(theme=[f"U{i}" for i in range(6)]), {}, dd, idx[-1])
    assert h["names"]["U0"]["intervals"]["25"] == [
        [str(idx[0].date()), str(idx[1].date())], [str(idx[3].date()), None]]
    assert h["names"]["U1"]["intervals"]["25"] == [[str(idx[0].date()), None]]


def test_a_row_under_the_peer_floor_states_nothing():
    idx = pd.bdate_range("2026-07-01", periods=3)
    dd = {f"U{i}": pd.Series([-0.40] * 3, index=idx, dtype="float64") for i in range(6)}
    for i in range(3, 6):                       # only 3 members print on the middle session
        dd[f"U{i}"] = dd[f"U{i}"].drop(idx[1])
    _, h = _hist(_defs(theme=[f"U{i}" for i in range(6)]), {}, dd, idx[-1])
    assert h["names"]["U0"]["intervals"]["25"] == [
        [str(idx[0].date()), str(idx[0].date())], [str(idx[2].date()), None]]


@pytest.mark.parametrize("k", [5, 6, 7, 8, 11, 12])
def test_loo_matrix_matches_the_scalar_helper(k):
    """The vectorised rank trick must be identical to the one-name-at-a-time median."""
    rng = np.random.default_rng(1000 + k)
    V = rng.normal(-0.3, 0.2, size=(40, k))
    V[rng.random((40, k)) < 0.2] = np.nan
    M = B.loo_median_matrix(V)
    for t in range(V.shape[0]):
        row = {f"c{j}": float(V[t, j]) for j in range(k) if np.isfinite(V[t, j])}
        for j in range(k):
            if not np.isfinite(V[t, j]) or len(row) < B.MIN_PEERS:
                assert not np.isfinite(M[t, j])
                continue
            assert M[t, j] == pytest.approx(B.leave_one_out_median(row, f"c{j}"))


def test_history_degrades_to_an_empty_payload_without_a_state():
    empty = B.build_state({}, {}, {})
    h = B.build_history({}, {}, {}, empty)
    assert h["schema"] == "basket_washout_history.v1" and h["names"] == {}
    assert h["notches"] == [20, 25, 30]


def test_main_replaces_previous_history_when_a_healthy_recompute_is_empty(
        tmp_path, monkeypatch):
    """No qualifying intervals is a valid current result, not permission to keep stale rows."""
    as_of = pd.Timestamp("2026-08-07")
    tickers = [f"U{i}" for i in range(6)]
    defs = _defs(theme=tickers)
    dd = _flat_group("U", 6, -0.05, as_of)
    monkeypatch.setattr(B, "load_basket_defs", lambda _root: defs)
    monkeypatch.setattr(B, "load_sector_map", lambda _root: {})
    monkeypatch.setattr(B, "panel_paths", lambda _root: {t: tmp_path / t for t in tickers})
    monkeypatch.setattr(B, "compute_drawdowns", lambda _paths, _need: dd)

    out = tmp_path / "basket_washout_state.json"
    hist_out = tmp_path / "basket_washout_history.json"
    hist_out.write_text(json.dumps({
        "schema": "basket_washout_history.v1",
        "as_of": "2026-08-06",
        "names": {"STALE": {"intervals": {"20": [["2026-01-01", None]]}}},
    }))

    assert B.main(["--data-root", str(tmp_path), "--out", str(out),
                   "--history-out", str(hist_out)]) == 0
    current = json.loads(hist_out.read_text())
    assert current["as_of"] == "2026-08-07"
    assert current["names"] == {}


def test_module_and_payload_carry_no_banned_vocabulary():
    src = (_REPO_ROOT / "scripts" / "build_basket_washout_state.py").read_text()
    assert not _BANNED.search(src), "banned vocabulary in the builder's own copy"
    as_of = pd.Timestamp("2026-08-07")
    dd = _flat_group("U", 6, -0.4, as_of)
    out = B.build_state(_defs(theme=[f"U{i}" for i in range(6)]), {}, dd, as_of=as_of)
    assert not _BANNED.search(json.dumps(out, ensure_ascii=False))
