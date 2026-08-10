"""tests/test_basket_washout_state.py — frozen contract + PIT sanity for the nightly
`site/factordata/basket_washout_state.json` artifact (ratified blocked-entry override,
construction A1b; `research/BLOCKED_ENTRY_RATIFICATION_PACKET_2026-08-10.md` §4).

Covers:
  (1) frozen v1 contract shape — exact key sets, types, threshold menu, id/qualifies keys
  (2) PIT sanity — `qualifies` flips EXACTLY at the threshold, boundary inclusive, and is
      always re-derivable from the PUBLISHED (rounded) number
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


def test_name_reads_the_same_number_as_its_group():
    as_of = pd.Timestamp("2026-08-07")
    dd = _flat_group("U", 5, -0.4, as_of) | _flat_group("S", 6, -0.1, as_of)
    out = B.build_state(_defs(theme=[f"U{i}" for i in range(5)]),
                        {f"S{i}": "Utilities" for i in range(6)}, dd, as_of=as_of)
    for t, e in out["names"].items():
        if e["basis"] == "basket":
            assert e["peer_dd"] == out["baskets"][e["group_id"]]["peer_median_dd_252"]


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


def test_module_and_payload_carry_no_banned_vocabulary():
    src = (_REPO_ROOT / "scripts" / "build_basket_washout_state.py").read_text()
    assert not _BANNED.search(src), "banned vocabulary in the builder's own copy"
    as_of = pd.Timestamp("2026-08-07")
    dd = _flat_group("U", 6, -0.4, as_of)
    out = B.build_state(_defs(theme=[f"U{i}" for i in range(6)]), {}, dd, as_of=as_of)
    assert not _BANNED.search(json.dumps(out, ensure_ascii=False))
