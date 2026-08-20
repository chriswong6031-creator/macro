"""The CN board price-limit regime registry (``config/cn_limit_rules.yml``).

WHAT THIS FILE IS FOR. The registry is metadata, not a computer:
``engine/china_microstructure.py::limit_width_for_date`` remains the canonical
implementation and the registry never feeds it. That separation is only safe while the
two AGREE — otherwise the repo grows a second, quietly different, source of truth about
limit widths, and a study citing the registry and an engine scoring the tape would
disagree with nobody noticing. So this suite holds them to parity for seasoned names,
on top of validating the file's own structure.

Three checks:
  (a) the committed YAML satisfies contracts/theme_graph/cn_limit_rules.v1.schema.json;
  (b) the intervals TILE each (board, security_status) series from its own start with no
      gaps and no overlaps — "which regime governed this date" must have exactly one
      answer, and every (board, status) pair is either tiled or declared in `unencoded`;
  (c) PARITY against the engine at each regime's endpoints, midpoint and boundary±1.

The registry and the engine use different board vocabularies (the engine collapses the
two main boards into "main"); the map is declared once, below.

Fixture-free by nature: this reads two committed CONFIG artifacts, no data/ store, and
pins no live count.
"""
from __future__ import annotations

import datetime as dt
import json
from collections import defaultdict
from pathlib import Path

import pandas as pd
import pytest
import yaml

from engine.china_microstructure import limit_width_for_date

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "config" / "cn_limit_rules.yml"
SCHEMA = ROOT / "contracts" / "theme_graph" / "cn_limit_rules.v1.schema.json"

#: Registry board → the engine's board vocabulary. The engine has never distinguished
#: the two main boards because their widths have never differed.
ENGINE_BOARD = {"sse_main": "main", "szse_main": "main",
                "star": "star", "chinext": "chinext", "bse": "bse"}

#: NOTE (P0-ST amendment): this suite used to skip every ST probe dated before the
#: engine's ST_STORE_COVERAGE_DATE, reasoning that "the engine applies ST narrowing only
#: from its own coverage date, so an earlier probe compares the registry's rule against
#: the engine's declared blindness". That reasoning is a DETECTION-level concern —
#: `_detect_limit_events` gates `is_st` to `ST_STORE_COVERAGE_DATE` because it derives
#: `is_st` from a current-only membership snapshot it cannot trust for earlier dates.
#: This suite instead calls `limit_width_for_date` DIRECTLY with an explicit
#: `is_st=(status == "st")` — it is never blind pre-coverage, because the caller is
#: telling it the ST status rather than asking the engine to infer one. The skip was
#: therefore over-broad: once the historical 5% ST row gained a `valid_to` (P0-ST closed
#: it at 2026-07-05), every one of its probe dates fell before the coverage floor and the
#: skip silently zeroed out parity coverage for that entire closed interval. Removed;
#: all probes (including the closed 5% era) now run and pass.
#:
#: An open-ended interval needs a right edge to probe. Fixed constant, deliberately not
#: `today`: a wall-clock probe date makes the suite's coverage drift every night.
OPEN_INTERVAL_PROBE = dt.date(2026, 8, 1)


def _load() -> dict:
    return yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))


DOC = _load()


def _d(s: str) -> dt.date:
    return dt.date.fromisoformat(s)


def _series() -> dict[tuple[str, str], list[dict]]:
    out: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in DOC["rules"]:
        out[(row["board"], row["security_status"])].append(row)
    return {k: sorted(v, key=lambda r: r["valid_from"]) for k, v in out.items()}


SERIES = _series()
UNENCODED = {(u["board"], u["security_status"]) for u in DOC["unencoded"]}


# ---------------------------------------------------------------------------
# (a) Structure
# ---------------------------------------------------------------------------

def test_the_registry_satisfies_its_committed_contract():
    import jsonschema

    jsonschema.validate(DOC, json.loads(SCHEMA.read_text(encoding="utf-8")))


def test_every_board_status_pair_is_either_tiled_or_declared_unencoded():
    """An honest null beats a plausible guess: a fabricated width here would be cited
    later as a fact, so a gap has to be written down rather than merely absent."""
    for board in DOC["boards"]:
        for status in ("ordinary", "st"):
            key = (board, status)
            assert (key in SERIES) != (key in UNENCODED), (
                f"{key} is neither tiled nor declared unencoded (or is both)")


def test_every_board_declares_an_ordinary_series():
    assert {b for (b, s) in SERIES if s == "ordinary"} == set(DOC["boards"])


@pytest.mark.parametrize("key", sorted(SERIES))
def test_each_series_tiles_its_own_timeline_without_gaps_or_overlaps(key):
    board, status = key
    rows = SERIES[key]
    meta = DOC["boards"][board]
    start = meta["limits_from"] if status == "ordinary" else meta["st_from"]
    assert start is not None, f"{key} has rows but the board declares no start for it"
    assert rows[0]["valid_from"] == start, (
        f"{key} starts at {rows[0]['valid_from']}, not the declared {start}")
    for earlier, later in zip(rows, rows[1:]):
        assert earlier["valid_to"] is not None, f"{key}: an inner row is open-ended"
        assert _d(earlier["valid_to"]) + dt.timedelta(days=1) == _d(later["valid_from"]), (
            f"{key}: gap or overlap at {earlier['valid_to']} → {later['valid_from']}")
    assert rows[-1]["valid_to"] is None, f"{key}: the current regime must stay open"


def test_the_st_series_never_starts_before_the_status_could_exist():
    """The ST designation post-dates the main boards' price limits by sixteen months.
    Back-filling the ST series to the board's birth would assert a rule for a status
    that did not yet exist."""
    for board, meta in DOC["boards"].items():
        if meta["st_from"] is None:
            continue
        assert _d(meta["st_from"]) >= _d(meta["limits_from"]), board


def test_ipo_windows_are_kept_out_of_the_seasoned_rules():
    """A consumer that only knows about seasoned names must not be able to read a
    listing window as the daily regime."""
    assert DOC["ipo_windows"], "the IPO-window list must not be vacuous"
    for row in DOC["ipo_windows"]:
        if row["rule"] == "no_limit":
            assert row["sessions"] and row["limit_up"] is None and row["limit_down"] is None
        else:
            # first_day_collar / informational rows record THAT a mechanism applied
            # without inventing its numeric form.
            assert row["limit_up"] is None and row["limit_down"] is None
            assert row["note"]


def test_the_wide_regime_ipo_windows_start_no_earlier_than_their_board():
    for row in DOC["ipo_windows"]:
        board = DOC["boards"][row["board"]]
        assert _d(row["valid_from"]) >= _d(board["limits_from"]), row


def test_every_row_is_citable():
    for row in [*DOC["rules"], *DOC["ipo_windows"]]:
        assert str(row["source"]).startswith("http"), row


# ---------------------------------------------------------------------------
# (c) Parity with the canonical engine — SEASONED names only
# ---------------------------------------------------------------------------

def _probe_dates(row: dict) -> list[dt.date]:
    """Endpoints, midpoint and boundary±1 for one regime interval."""
    lo = _d(row["valid_from"])
    hi = _d(row["valid_to"]) if row["valid_to"] else OPEN_INTERVAL_PROBE
    if hi < lo:  # pragma: no cover — a closed regime after the probe constant
        hi = lo
    out = {lo, hi, lo + (hi - lo) / 2, lo + dt.timedelta(days=1)}
    if row["valid_to"]:
        out.add(hi - dt.timedelta(days=1))
    return sorted(d for d in out if lo <= d <= hi)


def _parity_cases() -> list[tuple[str, str, str, float]]:
    cases = []
    for (board, status), rows in SERIES.items():
        if status == "st" and board not in ("sse_main", "szse_main"):
            # The engine implements ST narrowing on the main board only (CN-SYS-R12);
            # STAR/ChiNext ST rows in the registry record real exchange rules the engine
            # deliberately does not model, so they are not parity material.
            continue
        for row in rows:
            for probe in _probe_dates(row):
                cases.append((board, status, probe.isoformat(), row["limit_up"]))
    return cases


PARITY_CASES = _parity_cases()


def test_the_parity_probe_is_not_vacuous():
    """A parity suite that probes nothing passes for the wrong reason."""
    assert len(PARITY_CASES) >= 30
    assert {b for b, _s, _d, _w in PARITY_CASES} == set(DOC["boards"])
    assert any(s == "st" for _b, s, _d, _w in PARITY_CASES)


@pytest.mark.parametrize("board,status,probe,expected", PARITY_CASES)
def test_the_registry_agrees_with_the_canonical_engine(board, status, probe, expected):
    got = limit_width_for_date(ENGINE_BOARD[board], pd.Timestamp(probe),
                               is_st=(status == "st"))
    assert got == pytest.approx(expected), (
        f"{board}/{status} on {probe}: registry says {expected}, "
        f"engine/china_microstructure says {got}")


def test_the_two_main_boards_are_identical_everywhere():
    """The engine collapses them into one board. That is only sound while the registry
    keeps them identical — if a future rule change splits them, this fails and the
    engine's board vocabulary has to grow before the registry can express it."""
    for status in ("ordinary", "st"):
        sse = [(r["valid_from"], r["valid_to"], r["limit_up"], r["limit_down"])
               for r in SERIES[("sse_main", status)]]
        szse = [(r["valid_from"], r["valid_to"], r["limit_up"], r["limit_down"])
                for r in SERIES[("szse_main", status)]]
        assert sse == szse, status


def test_limits_are_symmetric_up_and_down():
    for row in DOC["rules"]:
        assert row["limit_up"] == row["limit_down"], row
