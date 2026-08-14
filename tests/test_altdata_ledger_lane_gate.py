"""HOUSE-U5 lane gate for the alt-data convergence ledger (engine/altdata_ledger.py).

WHY THIS SUITE EXISTS. `scripts.build_alt_data` — the module's only production
caller — runs in FIVE lanes: daily.yml's `engine` job (COLLECT_LANE=nightly, the sole
forward advancer) and closing-bell.yml / earlyclose.yml / render.yml /
engine-render.yml, none of which set COLLECT_LANE. Until #5679's review this module
had no self-gate at all: every one of those express lanes appended a fresh thesis row
to `data/altdata/theses.jsonl` and rewrote `data/altdata/track_record.json`, and the
ONLY reason the committed ledger never double-advanced is that those lanes commit
`git add site/` and then throw the dirty `data/` tree away (closing-bell.yml's
`git checkout -- . && git clean -fdq data/`). That is survival by someone else's
cleanup, not by design — and closing-bell.yml's own header asserts the opposite
premise in prose ("every engine ledger writer self-gates on it"), so the next lane
written against that promise, or any lane that stopped discarding, would have
double-advanced silently.

CONTRACT PINNED HERE (mirrors tests/test_build_leader_radar.py::TestHouseU5Gate and
tests/test_foresight_ledger_lane_gates.py, adapted to a writer that must still RUN
off-lane):

1. OFF-LANE the three `data/altdata/` artifacts are not created — not the theses
   append, not the scored append, not the stored track record.
2. OFF-LANE the module still COMPUTES: build_theses returns its rows and score()
   returns a real track record, because the express lanes render the page from those
   return values. This half is why the gate cannot be the function's first statement
   (the foresight-family contract) — a gate-first refusal here would blank the page.
3. OFF-LANE `site/altdata/track_record.json` IS written, from the COMMITTED ledger.
   That artifact is the render output the express lanes exist to refresh.
4. ON-LANE (COLLECT_LANE=nightly) every write lands — a gate that is always closed
   would silently stop the nightly's accrual, which is the failure mode this test is
   worth more for than for the ungated one it fixes.
5. An off-lane run leaves NO trace for the next nightly: the nightly that follows
   logs exactly what it would have logged had the express lane never run.

Hermetic: every write is redirected to tmp_path (root= param), so no repo data/ or
site/ artifact is touched.
"""
from __future__ import annotations

import json
from datetime import date

import pandas as pd
import pytest

from engine import altdata_ledger

# The convergence rows are unremarkable on purpose — this suite is about WHERE the
# bytes land, never about family routing (tests/test_altdata_reboot_families.py owns
# that). Both names are 2-channel/`altdata_slow`, so check_by lands ~63 business days
# out and `_SCORE_DAY` below is comfortably past it.
_BY_TICKER = {
    "as_of": "2026-01-02",
    "tickers": {
        "WIN": {"convergence_score": 2, "channels": ["congress_buy", "trump"],
                "trump_linked": True},
        "LOSE": {"convergence_score": 2, "channels": ["smart_money_13f", "13f_add"],
                 "trump_linked": False},
    },
}
_BUILD_DAY = date(2026, 1, 2)
_SCORE_DAY = date(2026, 5, 2)

_DATA_ARTIFACTS = ("theses.jsonl", "scored.jsonl", "track_record.json")


@pytest.fixture
def prices(monkeypatch):
    """Synthetic closes: WIN beats SPY, LOSE lags it.

    One patch covers BOTH halves — build_theses reads levels through
    `_desk._level_asof` and score() grades through the shared desk scorer, and both
    bottom out in `engine.ai_desk._close_series`.
    """
    idx = pd.date_range("2026-01-01", "2026-05-01", freq="B")
    n = len(idx)

    def fake_closes(tk, root):
        if tk == "SPY":
            return pd.Series([100 * (1 + 0.05 * i / n) for i in range(n)], index=idx)
        if tk == "WIN":
            return pd.Series([50 * (1 + 0.20 * i / n) for i in range(n)], index=idx)
        if tk == "LOSE":
            return pd.Series([50 * (1 - 0.15 * i / n) for i in range(n)], index=idx)
        return None

    monkeypatch.setattr(altdata_ledger._desk, "_close_series", fake_closes)


def _off_lane(monkeypatch):
    """Simulate closing-bell / earlyclose / render / engine-render.

    tests/conftest.py arms COLLECT_LANE=nightly for every test via an autouse
    fixture, so an off-lane case MUST delete it (and the US_LANE legacy alias that
    ledger_lane also accepts) or it tests the on-lane path while reading as the
    off-lane one.
    """
    monkeypatch.delenv("COLLECT_LANE", raising=False)
    monkeypatch.delenv("US_LANE", raising=False)


def _data_paths(root):
    return {name: root / "data" / "altdata" / name for name in _DATA_ARTIFACTS}


def _site_track(root):
    return root / "site" / "altdata" / "track_record.json"


# --------------------------------------------------------------------------- #
# 1 + 2 + 3 — off-lane: nothing persists under data/, the page still renders
# --------------------------------------------------------------------------- #
def test_build_theses_computes_but_does_not_persist_off_lane(tmp_path, monkeypatch, prices):
    """The express lanes may compute theses; only nightly may LOG them."""
    _off_lane(monkeypatch)
    new = altdata_ledger.build_theses(_BY_TICKER, root=tmp_path, today=_BUILD_DAY)

    # still computed — build_alt_data renders from the return value
    assert {r["ticker"] for r in new} == {"WIN", "LOSE"}
    assert not _data_paths(tmp_path)["theses.jsonl"].exists(), (
        "theses.jsonl was appended off-lane — the gate is missing or bypassed; today "
        "only closing-bell.yml's `git clean -fdq data/` hides this"
    )
    # and no half-created directory left behind either
    assert not (tmp_path / "data" / "altdata").exists()


def test_score_skips_data_writes_but_renders_site_off_lane(tmp_path, monkeypatch, prices):
    """Off-lane score() refreshes the RENDER copy and nothing under data/."""
    # Seed a committed ledger the way the nightly would have.
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    altdata_ledger.build_theses(_BY_TICKER, root=tmp_path, today=_BUILD_DAY)
    assert _data_paths(tmp_path)["theses.jsonl"].exists()

    _off_lane(monkeypatch)
    track = altdata_ledger.score(root=tmp_path, today=_SCORE_DAY)

    # (2) the express lane still gets a real track record to render
    assert track is not None and track["scored_total"] == 2
    assert track["schema"] == altdata_ledger.SCHEMA
    # (1) …written to neither of the two data/ artifacts
    assert not _data_paths(tmp_path)["scored.jsonl"].exists(), (
        "scored.jsonl was appended off-lane — outcome rows are forward-ledger rows"
    )
    assert not _data_paths(tmp_path)["track_record.json"].exists(), (
        "data/altdata/track_record.json was rewritten off-lane"
    )
    # (3) …while the render output the express lanes exist for IS refreshed
    assert json.loads(_site_track(tmp_path).read_text())["scored_total"] == 2


def test_rebuild_off_lane_touches_no_data_artifact(tmp_path, monkeypatch, prices):
    """The composite entry point build_alt_data actually calls is gated end to end."""
    _off_lane(monkeypatch)
    track = altdata_ledger.rebuild(_BY_TICKER, root=tmp_path, today=_BUILD_DAY)

    assert track is not None                       # page still renders
    assert not (tmp_path / "data").exists(), (
        "rebuild() wrote under data/ off-lane — every write in this module is "
        "COLLECT_LANE=nightly gated (HOUSE-U5)"
    )
    assert _site_track(tmp_path).exists()


# --------------------------------------------------------------------------- #
# 4 — on-lane: the gate must not be always-closed
# --------------------------------------------------------------------------- #
def test_nightly_lane_writes_every_artifact(tmp_path, monkeypatch, prices):
    """COLLECT_LANE=nightly advances all three data/ artifacts (accrual survives)."""
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    new = altdata_ledger.build_theses(_BY_TICKER, root=tmp_path, today=_BUILD_DAY)
    assert {r["ticker"] for r in new} == {"WIN", "LOSE"}

    logged = [json.loads(line) for line
              in _data_paths(tmp_path)["theses.jsonl"].read_text().splitlines()]
    assert {r["ticker"] for r in logged} == {"WIN", "LOSE"}

    track = altdata_ledger.score(root=tmp_path, today=_SCORE_DAY)
    assert track["scored_total"] == 2
    for name, path in _data_paths(tmp_path).items():
        assert path.exists(), f"nightly lane did not write data/altdata/{name}"
    assert _site_track(tmp_path).exists()

    # the grade itself is unchanged by the gate — hit/miss still resolve as before
    scored = [json.loads(line) for line
              in _data_paths(tmp_path)["scored.jsonl"].read_text().splitlines()]
    outcome = {r["id"].split("-")[-2]: r["outcome"] for r in scored}
    assert outcome == {"WIN": "hit", "LOSE": "miss"}


def test_us_lane_legacy_alias_also_opens_the_gate(tmp_path, monkeypatch, prices):
    """ledger_lane accepts US_LANE=nightly; the gate here must inherit that."""
    monkeypatch.delenv("COLLECT_LANE", raising=False)
    monkeypatch.setenv("US_LANE", "nightly")
    altdata_ledger.build_theses(_BY_TICKER, root=tmp_path, today=_BUILD_DAY)
    assert _data_paths(tmp_path)["theses.jsonl"].exists()


def test_asia_lane_does_not_open_the_us_nightly_gate(tmp_path, monkeypatch, prices):
    """CN_LANE=asia is a DIFFERENT lane — it must not advance a US forward ledger."""
    _off_lane(monkeypatch)
    monkeypatch.setenv("CN_LANE", "asia")
    altdata_ledger.build_theses(_BY_TICKER, root=tmp_path, today=_BUILD_DAY)
    assert not _data_paths(tmp_path)["theses.jsonl"].exists()


# --------------------------------------------------------------------------- #
# 5 — the whole point: an express lane leaves the next nightly's work untouched
# --------------------------------------------------------------------------- #
def test_express_lane_run_does_not_consume_the_nightly_thesis(tmp_path, monkeypatch, prices):
    """A render bake before the nightly must not steal (or duplicate) the row.

    Ungated, the express lane's append lands first and `_active_subjects` then dedupes
    the NIGHTLY away — so on a lane that ever stopped discarding `data/`, the row that
    survives to the commit is whichever bake ran first, and running both would append
    the same id twice. Gated, the nightly logs exactly what it would have logged.
    """
    _off_lane(monkeypatch)
    altdata_ledger.rebuild(_BY_TICKER, root=tmp_path, today=_BUILD_DAY)

    monkeypatch.setenv("COLLECT_LANE", "nightly")
    nightly = altdata_ledger.build_theses(_BY_TICKER, root=tmp_path, today=_BUILD_DAY)

    assert {r["ticker"] for r in nightly} == {"WIN", "LOSE"}, (
        "the off-lane bake pre-empted the nightly's own append"
    )
    lines = _data_paths(tmp_path)["theses.jsonl"].read_text().splitlines()
    assert len(lines) == 2                                   # exactly one row per name
    assert len({json.loads(line)["id"] for line in lines}) == 2
