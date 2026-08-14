"""Live Entry Radar PR-1 — producer adapters + the write-discipline proof.

Synthetic fixtures only.  These artifacts do not exist in an agent worktree
(``data/`` and ``site/`` are absent from the sparse checkout), so every fixture
is written into ``tmp_path`` in the shape verified from the WRITER code —
never read from a real artifact, and never inferred from an absent one.

The last section is the one that matters most for W1's boundary:
``test_full_assembly_writes_nothing_under_data`` runs the real entrypoint
end to end against a synthetic repo root and proves ``data/`` is untouched.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from engine.entry_radar.nomination_bus import NominationBus
from engine.entry_radar.producers import (
    memberships_from,
    names_from,
    read_ipo_calendar,
    read_setups,
    read_stock_library,
    read_universe_sources,
    read_us_standouts,
    sectors_from,
)
from engine.entry_radar.spool import NominationSpool, tail_outbox_events
from engine.entry_radar.universe import load_config

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 8, 14, 14, 30, tzinfo=timezone.utc)
ASOF = "2026-08-14T02:10:00Z"


def _cfg():
    return load_config(ROOT)


# ---------------------------------------------------------------------------
# boards — us_standouts / setups (dict-with-lanes, per the verified writer)
# ---------------------------------------------------------------------------

def _standouts_doc():
    """The shape ``scripts/build_stock_library.py`` writes: root ``as_of`` + lanes."""
    return {
        "as_of": ASOF,
        "rank_by": "eq",
        "buy": [{"ticker": "NVDA", "name": "NVIDIA", "sector": "Information Technology",
                 "alpha": 2.31, "alpha_entry": 1.8, "state": "go", "label": "Buy",
                 "urgency": "high", "score_rank": 1, "display_rank": 1,
                 "prophet": {"version": "v9", "score": 88, "points": 12}},
                {"ticker": "KRUS", "name": "Kura Sushi", "alpha": 1.02,
                 "state": "go", "label": "Buy", "score_rank": 2}],
        "watch": [{"ticker": "MCK", "name": "McKesson", "alpha": 0.4, "label": "Watch"}],
        "leaders": [], "laggards": [],
    }


def test_us_standouts_adapter_reads_every_lane_distinctly(tmp_path):
    path = tmp_path / "us_standouts.json"
    path.write_text(json.dumps(_standouts_doc()), encoding="utf-8")
    got = read_us_standouts(path, now=NOW, cfg=_cfg())

    assert got.status == "ok"
    assert got.source_asof == datetime(2026, 8, 14, 2, 10, tzinfo=timezone.utc)
    by_ticker = {n.ticker: n for n in got.nominations}
    assert set(by_ticker) == {"NVDA", "KRUS", "MCK"}
    assert by_ticker["NVDA"].reason_code == "board.buy"
    assert by_ticker["MCK"].reason_code == "board.watch", \
        "watch and buy are different facts and must not collapse"
    assert by_ticker["NVDA"].source_rank == 1
    assert by_ticker["NVDA"].source_value == 2.31       # `alpha`, the real row number
    assert all(n.source_family == "market_price" for n in got.nominations)
    assert all(n.observed_at >= n.source_asof for n in got.nominations)


def test_standouts_adapter_does_not_ingest_the_prophet_block(tmp_path):
    """The board's ``prophet`` block is deliberately not read (contract §1)."""
    path = tmp_path / "us_standouts.json"
    path.write_text(json.dumps(_standouts_doc()), encoding="utf-8")
    got = read_us_standouts(path, now=NOW, cfg=_cfg())
    blob = json.dumps([n.to_dict() for n in got.nominations])
    assert "prophet" not in blob
    assert "88" not in blob, "Prophet's score must not ride into a Radar nomination"


def test_setups_adapter(tmp_path):
    path = tmp_path / "setups.json"
    path.write_text(json.dumps({
        "as_of": ASOF,
        "buy": [{"ticker": "REGN", "alpha": 1.4, "label": "Buy", "setup": "pullback"}],
        "laggards": [{"ticker": "YELP", "alpha": -0.9, "label": "Laggard"}],
    }), encoding="utf-8")
    got = read_setups(path, now=NOW, cfg=_cfg())
    codes = {n.ticker: n.reason_code for n in got.nominations}
    assert codes == {"REGN": "board.buy", "YELP": "board.laggard"}
    assert all(n.source_id == "factordata:setups" for n in got.nominations)
    assert {n.source_prefix for n in got.nominations} == {"factordata"}


def test_boards_share_a_correlated_prefix(tmp_path):
    """One upstream, one disclosed family — not two independent confirmations."""
    (tmp_path / "us_standouts.json").write_text(json.dumps(_standouts_doc()), encoding="utf-8")
    (tmp_path / "setups.json").write_text(json.dumps(
        {"as_of": ASOF, "buy": [{"ticker": "NVDA", "alpha": 2.0, "label": "Buy"}]}),
        encoding="utf-8")
    bus = NominationBus()
    bus.ingest_read(read_us_standouts(tmp_path / "us_standouts.json", now=NOW, cfg=_cfg()),
                    now=NOW)
    bus.ingest_read(read_setups(tmp_path / "setups.json", now=NOW, cfg=_cfg()), now=NOW)
    groups = bus.correlated_groups(now=NOW)
    assert sorted(groups["factordata"]) == ["factordata:setups", "factordata:us_standouts"]
    # NVDA legitimately carries BOTH nominations — correlated, never deduped away.
    assert len(bus.for_ticker("NVDA", now=NOW)) == 2


# ---------------------------------------------------------------------------
# stock library — feature provider
# ---------------------------------------------------------------------------

def test_stock_library_reads_features_from_the_tech_block():
    """``rec["tech"]`` is where ``stock_technicals.snapshot()`` lands."""
    got = read_stock_library({
        "NVDA": {"ticker": "NVDA", "name": "NVIDIA Corp", "asof": ASOF,
                 "history_days": 6800,
                 "tech": {"dollar_vol_20d": 4.2e10, "rel_volume": 3.1,
                          "atr_pct": 4.4, "ret_1m": -12.5},
                 "profile": {"mktcap_bn": 3100.0},
                 "entry_signal": {"state": "GO", "score": 91}},
    }, now=NOW, cfg=_cfg())

    assert got.status in ("ok", "stale")
    assert got.read.nominations == (), "the master record emits no nominations by design"
    feat = got.features["NVDA"]
    assert feat["dollar_vol_20d"] == 4.2e10
    assert feat["rel_volume"] == 3.1
    assert feat["realized_range_pct"] == 4.4
    assert feat["momentum_20d_abs_pct"] == 12.5, "absolute — both directions are attention"
    assert feat["mktcap_bn"] == 3100.0
    assert got.names["NVDA"] == "NVIDIA Corp"
    assert got.history_age["NVDA"] == 6800


def test_stock_library_never_promotes_another_organs_verdict():
    got = read_stock_library({
        "NVDA": {"ticker": "NVDA", "asof": ASOF, "tech": {"rel_volume": 1.0},
                 "entry_signal": {"score": 91}, "conviction": {"potential": 77},
                 "washout_turn": {"state": "TURNING"}},
    }, now=NOW, cfg=_cfg())
    assert got.read.nominations == ()
    for banned in ("entry_signal", "conviction", "washout_turn", "potential"):
        assert banned not in json.dumps(got.features)


def test_stock_library_absent_dir_is_unavailable(tmp_path):
    got = read_stock_library(stockdata_dir=tmp_path / "nope", now=NOW, cfg=_cfg())
    assert got.status == "unavailable"
    assert got.features == {}


# ---------------------------------------------------------------------------
# IPO calendar
# ---------------------------------------------------------------------------

def test_ipo_calendar_admits_recent_and_upcoming_listings():
    rows = [
        {"deal_id": "d1", "ticker": "NEWCO", "company": "NewCo Inc", "status": "priced",
         "priced_date": "2026-07-01", "offer_price": 18.0, "is_spac": False,
         "as_of": ASOF},
        {"deal_id": "d2", "ticker": "SOONCO", "status": "upcoming",
         "expected_date": "2026-08-20", "range_mid": 21.0, "is_spac": True,
         "as_of": ASOF},
        {"deal_id": "d3", "ticker": "OLDCO", "status": "priced",
         "priced_date": "2024-01-05", "as_of": ASOF},          # outside the window
        {"deal_id": "d4", "ticker": "GONECO", "status": "withdrawn",
         "withdraw_date": "2026-06-01", "as_of": ASOF},        # not tradable-now
    ]
    got = read_ipo_calendar(rows=rows, now=NOW, cfg=_cfg())
    by_ticker = {n.ticker: n for n in got.read.nominations}
    assert set(by_ticker) == {"NEWCO", "SOONCO"}
    assert by_ticker["NEWCO"].reason_code == "ipo.recent_listing"
    assert by_ticker["SOONCO"].reason_code == "ipo.upcoming_listing"
    assert "SPAC" in by_ticker["SOONCO"].reason_text
    assert all(n.source_family == "special_situation" for n in got.read.nominations)

    # The young cohort gets a real history age, not a warm-up exclusion.
    assert 0 < got.history_age["NEWCO"] < 60
    assert "session(s) of history" in by_ticker["NEWCO"].reason_text


def test_ipo_calendar_absent_parquet_is_unavailable(tmp_path):
    got = read_ipo_calendar(tmp_path / "calendar.parquet", now=NOW, cfg=_cfg())
    assert got.status == "unavailable"
    assert got.read.nominations == ()


def test_ipo_calendar_empty_frame_is_an_outage_not_an_empty_pipeline():
    got = read_ipo_calendar(rows=[], now=NOW, cfg=_cfg())
    assert got.status == "unavailable"
    assert "outage" in got.read.detail


# ---------------------------------------------------------------------------
# constituents / universe sources
# ---------------------------------------------------------------------------

def _fake_loader(frames):
    def load(path):
        key = Path(path).parent.name
        if key not in frames:
            raise FileNotFoundError(path)
        return frames[key]
    return load


def test_universe_sources_read_symbol_indexed_constituents(tmp_path):
    """Index ``symbol``, columns ``name``/``sector`` (collectors/breadth.py:503)."""
    frames = {
        "breadth": {"AAPL": {"name": "Apple Inc.", "sector": "Information Technology"},
                    "TQQQ": {"name": "ProShares UltraPro QQQ", "sector": "n/a"}},
        "midcap_breadth": {"KRUS": {"name": "Kura Sushi USA Inc",
                                    "sector": "Consumer Discretionary"}},
    }
    sources = read_universe_sources(tmp_path, loader=_fake_loader(frames))
    by_key = {s.key: s for s in sources}
    assert by_key["sp500"].status == "ok"
    assert set(by_key["sp500"].tickers) == {"AAPL", "TQQQ"}
    assert by_key["sp400"].status == "ok"
    assert by_key["sp600"].status == "unavailable", "an absent sibling is an OUTAGE"
    assert by_key["russell2000"].status == "unavailable"
    assert by_key["deep_history"].status == "unavailable"

    memberships = memberships_from(sources)
    assert set(memberships) == {"sp500", "sp400"}, \
        "a failed source is ABSENT, never present-and-empty"
    assert names_from(sources)["AAPL"] == "Apple Inc."
    assert sectors_from(sources)["KRUS"] == "Consumer Discretionary"


def test_empty_constituents_file_is_an_outage_not_an_empty_index(tmp_path):
    sources = read_universe_sources(tmp_path, loader=_fake_loader({"breadth": {}}))
    sp500 = next(s for s in sources if s.key == "sp500")
    assert sp500.status == "unavailable"
    assert "outage" in sp500.detail


# ---------------------------------------------------------------------------
# hot_tape outbox tailer (the prospective fallback)
# ---------------------------------------------------------------------------

def test_outbox_tailer_is_degraded_and_absent_dir_is_unavailable(tmp_path):
    assert tail_outbox_events(tmp_path / "nope", now=NOW).status == "unavailable"

    outbox = tmp_path / "outbox"
    outbox.mkdir()
    (outbox / "post1.json").write_text(json.dumps(
        {"ts": "2026-08-14T13:00:00Z", "tickers": ["ZZTOP", "NVDA"]}), encoding="utf-8")
    got = tail_outbox_events(outbox, now=NOW)
    assert got.status == "ok"
    assert {n.ticker for n in got.nominations} == {"ZZTOP", "NVDA"}
    assert all(n.data_quality == "degraded" for n in got.nominations), \
        "the outbox carries what was PUBLISHED, not what was DETECTED"
    assert all(n.source_family == "news_catalyst" for n in got.nominations)


# ---------------------------------------------------------------------------
# WRITE DISCIPLINE — the PR-1 boundary
# ---------------------------------------------------------------------------

def _synthetic_repo(root: Path) -> None:
    """A repo-shaped tree with real artifacts AND a data/ tree we must not touch."""
    (root / "data" / "ipo").mkdir(parents=True)
    (root / "data" / "breadth").mkdir(parents=True)
    (root / "data" / "entry_radar").mkdir(parents=True)   # the tempting durable home
    (root / "site" / "live").mkdir(parents=True)
    (root / "site" / "factordata").mkdir(parents=True)
    (root / "site" / "basketdata").mkdir(parents=True)
    (root / "site" / "stockdata").mkdir(parents=True)

    (root / "site" / "factordata" / "us_standouts.json").write_text(
        json.dumps(_standouts_doc()), encoding="utf-8")
    (root / "site" / "stockdata" / "NVDA.json").write_text(json.dumps(
        {"ticker": "NVDA", "name": "NVIDIA Corp", "asof": ASOF, "history_days": 6800,
         "tech": {"dollar_vol_20d": 4.2e10, "rel_volume": 3.4, "atr_pct": 5.0}}),
        encoding="utf-8")
    (root / "site" / "live" / "flow_pulse.json").write_text(json.dumps(
        {"schema": "flow_pulse.v1", "as_of": "2026-08-14T14:25:00Z", "stale": False,
         "tickers": [{"ticker": "KRUS", "rvol_tod": 6.2, "higher_lows": True}]}),
        encoding="utf-8")
    (root / "site" / "basketdata" / "pulse.json").write_text(json.dumps(
        {"semis": {"basket_id": "semis", "as_of": ASOF,
                   "direction": {"leader": {"ticker": "NVDA", "kind": "activity"}}}}),
        encoding="utf-8")


def _data_tree(root: Path) -> list[str]:
    return sorted(str(p.relative_to(root)) for p in (root / "data").rglob("*")
                  if p.is_file())


def test_full_assembly_writes_nothing_under_data(tmp_path, monkeypatch):
    """The PR-1 write boundary, proven behaviourally rather than by grep.

    Runs the real entrypoint against a synthetic repo root and asserts the
    ``data/`` tree is byte-for-byte untouched: the live-dir artifact and the
    spool are the only sinks (contract §7.3).
    """
    import scripts.entry_radar_universe as entry

    _synthetic_repo(tmp_path)
    before = _data_tree(tmp_path)
    assert before == [], "fixture sanity: data/ starts empty"

    live = tmp_path / "site" / "live"
    spool = tmp_path / "spool"
    monkeypatch.delenv("MACRO_LIVE_DIR", raising=False)
    monkeypatch.delenv("ENTRY_RADAR_NO_PUBLISH", raising=False)

    rc = entry.main(["--root", str(tmp_path), "--live-dir", str(live),
                     "--spool-dir", str(spool)])
    assert rc == 0

    assert _data_tree(tmp_path) == [], \
        "PR-1 production code must write NO data/ path — PR-5's reconciler owns durable"

    artifact = json.loads((live / "entry_radar_probe_set.json").read_text(encoding="utf-8"))
    assert artifact["schema"] == "mastermind.entry_probe_set.v1"
    assert artifact["authority"] == {"can_rank": False, "can_size": False,
                                     "can_gate": False, "can_originate_signal": False,
                                     "can_escalate": False}
    assert artifact["n_probed"] >= 1
    assert artifact["lane"]["durable_writes"] == []
    tickers = {p["ticker"] for p in artifact["probes"]}
    assert {"NVDA", "KRUS"} <= tickers

    # Every nomination that admitted a name is durably spooled.
    spooled = sorted(spool.rglob("*.json"))
    assert spooled, "the pass must leave a spool object"
    payload = json.loads(spooled[0].read_text(encoding="utf-8"))
    assert payload["n_nominations"] >= 1
    assert payload["nominations"][0]["observed_at"]


def test_dry_run_writes_nothing_at_all(tmp_path, monkeypatch):
    import scripts.entry_radar_universe as entry

    _synthetic_repo(tmp_path)
    live = tmp_path / "site" / "live"
    monkeypatch.delenv("MACRO_LIVE_DIR", raising=False)
    rc = entry.main(["--root", str(tmp_path), "--live-dir", str(live),
                     "--spool-dir", str(tmp_path / "spool"), "--dry-run"])
    assert rc == 0
    assert not (live / "entry_radar_probe_set.json").exists()
    assert not (tmp_path / "spool").exists()
    assert _data_tree(tmp_path) == []


def test_no_publish_env_refuses_the_spool(tmp_path, monkeypatch, capsys):
    """The rehearsal switch: a fabricated spool row is indistinguishable forever."""
    monkeypatch.setenv("ENTRY_RADAR_NO_PUBLISH", "1")
    from engine.entry_radar.contracts import Nomination

    nom = Nomination(ticker="ZZTOP", source_id="ipo:calendar",
                     source_family="special_situation", reason_code="ipo.recent_listing",
                     reason_text="listed", observed_at=NOW, source_asof=NOW)
    spool = NominationSpool(local_dir=tmp_path / "spool")
    assert spool.append([nom], now=NOW) is None
    assert not (tmp_path / "spool").exists()
    line = next(ln for ln in capsys.readouterr().out.splitlines() if "entry-radar" in ln)
    assert line.startswith("::warning"), "annotations must start the line"


def test_no_production_module_uses_a_parquet_or_csv_writer():
    """A static backstop for the behavioural test above."""
    sources = [*(ROOT / "engine" / "entry_radar").rglob("*.py"),
               *(ROOT / "scripts").glob("entry_radar_*.py")]
    assert len(sources) >= 10
    for path in sources:
        text = path.read_text(encoding="utf-8")
        for banned in ("to_parquet", "to_csv", "to_feather"):
            assert banned not in text, f"{path.name} calls {banned} — W1 writes no durable store"


@pytest.mark.parametrize("source_id,expected_max_minutes", [
    ("flow_pulse:fastpath", 90),      # 30-min lane → 3 missed passes
    ("hot_tape:detect_events", 30),   # 5-min lane
    ("stockdata:master", 2160),       # nightly
    ("breadth:constituents", 10080),  # membership moves quarterly
])
def test_staleness_budgets_track_artifact_cadence(source_id, expected_max_minutes):
    """Staleness is per-artifact cadence, never one global number."""
    from engine.entry_radar.producers import stale_after
    assert stale_after(_cfg(), source_id) == expected_max_minutes
