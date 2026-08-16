"""Live Entry Radar PR-1 (W1) — probe universe + enlistment bus acceptance suite.

Every test runs on SYNTHETIC fixtures.  Nothing here reads ``data/`` or
``site/``: agent worktrees are sparse checkouts where those trees are absent,
and a suite that needed them would pass vacuously on the render host and fail
everywhere else (DSC:SESSION-WORKTREES-ARE-SPARSE).

The headline is ``test_ACCEPTANCE_lobe_nominated_small_cap_enters_probe_set`` —
the contract §15 PR-1 row, verbatim: *"A lobe-nominated small cap outside the
hot universe appears in the Probe Set at the next eligible refresh with source
evidence intact; every nomination event spools durably from day one."*
"""
from __future__ import annotations

import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from engine.entry_radar.contracts import (
    AUTHORITY_BLOCK,
    NOMINATION_FIELDS,
    PROBE_RECORD_FIELDS,
    SOURCE_FAMILIES,
    Nomination,
    NominationError,
    ProducerRead,
    assert_no_score_fields,
    nomination_dataclass_fields,
)
from engine.entry_radar.nomination_bus import NominationBus
from engine.entry_radar.spool import NominationSpool, tap_hot_tape_events
from engine.entry_radar.universe import (
    SupabaseWatchlistAdapter,
    UniverseSourceRead,
    assemble_probe_set,
    build_layer_a,
    classify_eligibility,
    load_config,
)

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 8, 14, 14, 30, tzinfo=timezone.utc)
YESTERDAY = NOW - timedelta(days=1)


# ---------------------------------------------------------------------------
# fixtures — all synthetic
# ---------------------------------------------------------------------------

def _cfg():
    return load_config(ROOT)


def _layer_a(names: dict[str, str], *, source_key: str = "sp500"):
    """A Layer-A read over a synthetic constituents source."""
    src = UniverseSourceRead(
        key=source_key, status="ok", tickers=tuple(names),
        meta={sym: {"name": label} for sym, label in names.items()},
        detail="synthetic")
    return build_layer_a([src], names=names, curated=frozenset())


def _nomination(ticker="ZZTOP", *, source_id="basketdata:linked_outsiders",
                family="special_situation", reason_code="filing.linked_counterparty",
                observed_at=NOW, source_asof=YESTERDAY, **kw) -> Nomination:
    base = dict(
        ticker=ticker, source_id=source_id, source_family=family,
        reason_code=reason_code,
        reason_text=f"{ticker} named as a counterparty in a material 8-K",
        observed_at=observed_at, source_asof=source_asof,
        source_rank=3, source_value=1.0, source_horizon="event",
        ttl_until=observed_at + timedelta(hours=36),
        evidence_ref="linked_outsiders.json#semis/ZZTOP?accession=0001", data_quality="ok")
    base.update(kw)
    return Nomination(**base)


def _spool(tmp_path: Path) -> NominationSpool:
    return NominationSpool(local_dir=tmp_path / "spool", prefix="live_flow/entry_radar_nominations")


# ---------------------------------------------------------------------------
# THE ACCEPTANCE TEST — contract §15, PR-1 row
# ---------------------------------------------------------------------------

def test_ACCEPTANCE_lobe_nominated_small_cap_enters_probe_set(tmp_path):
    """A lobe-nominated small cap outside the hot universe reaches the Probe Set.

    The name fails EVERY Layer-C threshold and is in NO Layer-B index, so
    Layer D is the only door it can come through — which is exactly gate P-6
    ("every lobe nomination can force a ticker into the Probe Set; IPO/small
    caps not rejected for index non-membership").
    """
    small_cap = "ZZTOP"
    cfg = _cfg()

    # Layer A knows the name (it is a real operating company), Layer B does not
    # carry it in any index, and its attention features are far below every knob.
    layer_a = _layer_a({"AAPL": "Apple Inc.", small_cap: "ZZ Top Industries Inc."})
    memberships = {"sp500": ["AAPL"]}                     # small cap NOT a member
    liquidity = {"AAPL": {"dollar_vol_20d": 9.9e9},
                 small_cap: {"dollar_vol_20d": 250_000.0}}  # far below the $50M floor
    hot_features = {small_cap: {"dollar_vol_rank": 4200, "rel_volume": 0.6,
                                "rvol_tod": 0.4, "realized_range_pct": 1.1,
                                "gap_abs_pct": 0.2, "momentum_20d_abs_pct": 1.5}}

    bus = NominationBus(spool=_spool(tmp_path))
    nom = _nomination(small_cap)
    read = ProducerRead(source_id=nom.source_id, status="ok", nominations=(nom,),
                        source_asof=YESTERDAY, observed_at=NOW)
    assert bus.ingest_read(read, now=NOW) == 1

    probe_set = assemble_probe_set(layer_a=layer_a, bus=bus, cfg=cfg,
                                   memberships=memberships, liquidity=liquidity,
                                   hot_features=hot_features, history_age={small_cap: 310},
                                   market_session="2026-08-14", now=NOW)

    record = probe_set.by_ticker()[small_cap]

    # --- it came through Layer D, and D is the ONLY hot/core door it had -----
    assert "D" in record.admission_layers
    assert "B" not in record.admission_layers, "small cap must not qualify for core"
    assert "C" not in record.admission_layers, "small cap must fail every hot threshold"

    # --- source evidence intact --------------------------------------------
    assert len(record.nominations) == 1
    kept = record.nominations[0]
    assert kept.source_family == "special_situation"
    assert kept.source_id == "basketdata:linked_outsiders"
    assert kept.observed_at == NOW
    assert kept.source_asof == YESTERDAY
    assert kept.evidence_ref == "linked_outsiders.json#semis/ZZTOP?accession=0001"
    assert kept.reason_code == "filing.linked_counterparty"
    assert kept.reason_text  # the operator-readable why survives

    reason = next(r for r in record.admission_reasons if r.layer == "D")
    assert reason.source_id == "basketdata:linked_outsiders"
    assert reason.detail["source_family"] == "special_situation"

    # --- freshness + eligibility intact -------------------------------------
    assert record.eligibility == "operating_equity"
    assert record.freshness["newest_source_asof"] == "2026-08-13T14:30:00Z"
    assert record.freshness["computed_at"] == "2026-08-14T14:30:00Z"
    assert record.history_age_sessions == 310

    # --- and NO score of any kind -------------------------------------------
    serialised = record.to_dict()
    assert set(serialised) == set(PROBE_RECORD_FIELDS)
    assert_no_score_fields(serialised)
    for banned in ("score", "rank", "points", "bullish", "candidate", "conviction"):
        assert not any(banned in k.lower() for k in serialised), \
            f"probe record grew a {banned!r} field — admission is not bullishness"

    # --- the published artifact stamps display-tier authority ---------------
    doc = probe_set.to_dict()
    assert doc["authority"] == AUTHORITY_BLOCK
    assert all(v is False for v in doc["authority"].values())


def test_ACCEPTANCE_nomination_for_a_name_layer_a_never_heard_of(tmp_path):
    """P-6's hardest case: the nominated name is in NO universe source at all.

    It is still admitted (never rejected for non-membership) and lands
    ``unclassified`` by the fail-closed rule rather than being waved through as
    an operating company.
    """
    bus = NominationBus(spool=_spool(tmp_path))
    bus.ingest_read(ProducerRead(source_id="ipo:calendar", status="ok",
                                 nominations=(_nomination("NEWCO", source_id="ipo:calendar",
                                                          reason_code="ipo.recent_listing"),),
                                 source_asof=YESTERDAY, observed_at=NOW), now=NOW)
    probe_set = assemble_probe_set(layer_a=_layer_a({"AAPL": "Apple Inc."}), bus=bus,
                                   cfg=_cfg(), market_session="2026-08-14", now=NOW)
    record = probe_set.by_ticker()["NEWCO"]
    assert record.admission_layers == ("D",)
    assert record.eligibility == "unclassified"
    assert record.data_quality == "degraded"
    assert any(n["code"] == "unclassified_present" for n in probe_set.to_dict()["notes"])


# ---------------------------------------------------------------------------
# spool-before-consume (contract §5)
# ---------------------------------------------------------------------------

def test_nomination_is_spooled_durably_with_admission(tmp_path):
    """The same event that admits the name is on disk in the spool."""
    spool = _spool(tmp_path)
    bus = NominationBus(spool=spool)
    nom = _nomination("ZZTOP")
    bus.ingest_read(ProducerRead(source_id=nom.source_id, status="ok", nominations=(nom,),
                                 source_asof=YESTERDAY, observed_at=NOW), now=NOW)

    assert bus.spool_keys, "an ingested nomination must produce a spool object"
    key = bus.spool_keys[0]
    assert key.startswith("live_flow/entry_radar_nominations/2026-08-14/")
    payload = json.loads((tmp_path / "spool" / key).read_text(encoding="utf-8"))
    assert payload["n_nominations"] == 1
    spooled = payload["nominations"][0]
    assert spooled["ticker"] == "ZZTOP"
    assert spooled["observed_at"] == "2026-08-14T14:30:00Z"
    assert spooled["source_asof"] == "2026-08-13T14:30:00Z"
    assert set(spooled) == set(NOMINATION_FIELDS), "the spooled row is the frozen v1 shape"
    assert payload["authority"] == AUTHORITY_BLOCK


def test_unspooled_nomination_is_refused_admission(tmp_path):
    """Spool-before-consume is mechanical: a failed spool blocks admission.

    An ephemeral producer's nomination that was never spooled is
    unreconstructible forever, so admitting on it would put an ungradeable
    episode into the forward ledger.
    """
    class _DeadSpool(NominationSpool):
        def _put(self, key, payload):  # noqa: ANN001, ARG002
            return False

    bus = NominationBus(spool=_DeadSpool(local_dir=None))
    nom = _nomination("ZZTOP")
    admitted = bus.ingest_read(ProducerRead(source_id=nom.source_id, status="ok",
                                            nominations=(nom,), source_asof=YESTERDAY,
                                            observed_at=NOW), now=NOW)
    assert admitted == 0
    assert bus.active(now=NOW) == []
    assert [n.ticker for n in bus.refused_unspooled] == ["ZZTOP"]

    probe_set = assemble_probe_set(layer_a=_layer_a({}), bus=bus, cfg=_cfg(),
                                   market_session="2026-08-14", now=NOW)
    assert "ZZTOP" not in probe_set.by_ticker()


# ---------------------------------------------------------------------------
# no flattening (contract §16 A1.2)
# ---------------------------------------------------------------------------

def test_two_families_for_one_ticker_stay_two_records(tmp_path):
    """One ticker, two producers, two families → two records, two provenances."""
    bus = NominationBus(spool=_spool(tmp_path))
    a = _nomination("ZZTOP", source_id="factordata:us_standouts",
                    family="market_price", reason_code="board.buy")
    b = _nomination("ZZTOP", source_id="ipo:calendar",
                    family="special_situation", reason_code="ipo.recent_listing")
    bus.ingest_read(ProducerRead(source_id=a.source_id, status="ok", nominations=(a,),
                                 observed_at=NOW), now=NOW)
    bus.ingest_read(ProducerRead(source_id=b.source_id, status="ok", nominations=(b,),
                                 observed_at=NOW), now=NOW)

    kept = bus.for_ticker("ZZTOP", now=NOW)
    assert len(kept) == 2
    assert {n.source_family for n in kept} == {"market_price", "special_situation"}
    assert {n.source_id for n in kept} == {"factordata:us_standouts", "ipo:calendar"}
    assert {n.reason_code for n in kept} == {"board.buy", "ipo.recent_listing"}

    probe_set = assemble_probe_set(layer_a=_layer_a({"ZZTOP": "ZZ Top Industries Inc."}),
                                   bus=bus, cfg=_cfg(), market_session="2026-08-14",
                                   now=NOW)
    record = probe_set.by_ticker()["ZZTOP"]
    assert len(record.nominations) == 2, "nominations must never collapse to a count"
    rows = record.to_dict()["nominations"]
    assert len({r["source_id"] for r in rows}) == 2
    # ... and no "n_lobes"/"lobe_count" summary replaced them.
    assert not any("count" in k.lower() for k in record.to_dict())


def test_correlated_producers_are_disclosed_by_source_prefix(tmp_path):
    """Two cuts of one upstream artifact disclose as one correlated family."""
    bus = NominationBus(spool=_spool(tmp_path))
    for source_id, code in (("factordata:us_standouts", "board.buy"),
                            ("factordata:setups", "board.setup")):
        nom = _nomination("ZZTOP", source_id=source_id, family="market_price",
                          reason_code=code)
        bus.ingest_read(ProducerRead(source_id=source_id, status="ok", nominations=(nom,),
                                     observed_at=NOW), now=NOW)
    groups = bus.correlated_groups(now=NOW)
    assert groups["factordata"] == ["factordata:setups", "factordata:us_standouts"]
    assert len(groups["factordata"]) > 1, "a >1 group is the double-counting warning"


# ---------------------------------------------------------------------------
# missing is not negative (contract §5)
# ---------------------------------------------------------------------------

def test_absent_producer_reads_unavailable_with_age_not_empty(tmp_path):
    """An absent artifact is ``unavailable`` with a reason — never an empty list."""
    from engine.entry_radar.producers import read_flow_pulse, read_group_pulse

    missing = tmp_path / "does_not_exist.json"
    flow = read_flow_pulse(missing, now=NOW, cfg=_cfg())
    assert flow.read.status == "unavailable"
    assert flow.read.nominations == ()
    assert "absent" in flow.read.detail
    pulse = read_group_pulse(missing, now=NOW, cfg=_cfg())
    assert pulse.status == "unavailable"

    # A ProducerRead cannot even be constructed claiming unavailability WITH data.
    with pytest.raises(NominationError):
        ProducerRead(source_id="x:y", status="unavailable",
                     nominations=(_nomination(),), observed_at=NOW)


def test_stale_read_is_usable_but_aged(tmp_path):
    """``stale`` carries real, aged facts; ``unavailable`` carries none."""
    from engine.entry_radar.producers import read_flow_pulse

    path = tmp_path / "flow_pulse.json"
    path.write_text(json.dumps({
        "schema": "flow_pulse.v1", "as_of": "2026-08-14T14:00:00Z", "stale": True,
        "tickers": [{"ticker": "ZZTOP", "rvol_tod": 9.0, "higher_lows": True}],
    }), encoding="utf-8")
    got = read_flow_pulse(path, now=NOW, cfg=_cfg())
    assert got.read.status == "stale", "the producer's own stale flag is honoured"
    assert got.read.usable is True
    assert len(got.read.nominations) == 1
    assert got.read.nominations[0].data_quality == "degraded"


def test_unavailable_producer_retains_prior_members(tmp_path):
    """THE RETENTION RULE — and its counterpart.

    A producer that went ``unavailable`` keeps its prior members (retained,
    marked stale).  A producer that read ``ok`` and simply did not mention a
    name is a REAL negative observation, so that name's reason lapses.
    """
    cfg = _cfg()
    layer_a = _layer_a({"HELD": "Held Corp", "DROPPED": "Dropped Corp"})

    # Pass 1: both names nominated by their own producers, both producers OK.
    bus1 = NominationBus(spool=_spool(tmp_path / "p1"))
    for sym, source_id in (("HELD", "flow_pulse:fastpath"),
                           ("DROPPED", "factordata:us_standouts")):
        nom = _nomination(sym, source_id=source_id, family="market_price",
                          reason_code="flow_pulse.rvol_tod")
        bus1.ingest_read(ProducerRead(source_id=source_id, status="ok", nominations=(nom,),
                                      source_asof=YESTERDAY, observed_at=NOW), now=NOW)
    first = assemble_probe_set(layer_a=layer_a, bus=bus1, cfg=cfg,
                               market_session="2026-08-14", now=NOW)
    assert {"HELD", "DROPPED"} <= set(first.by_ticker())

    # Pass 2 (next session): flow_pulse is UNAVAILABLE (outage);
    # us_standouts read fine and simply no longer lists DROPPED.
    later = NOW + timedelta(days=1)
    bus2 = NominationBus(spool=_spool(tmp_path / "p2"))
    bus2.ingest_reads([
        ProducerRead(source_id="flow_pulse:fastpath", status="unavailable",
                     observed_at=later, detail="artifact absent"),
        ProducerRead(source_id="factordata:us_standouts", status="ok", nominations=(),
                     source_asof=later, observed_at=later),
    ], now=later)
    second = assemble_probe_set(layer_a=layer_a, bus=bus2, cfg=cfg,
                                previous=first, market_session="2026-08-15", now=later)

    held = second.by_ticker()["HELD"]
    retained = [r for r in held.admission_reasons if r.retained_stale]
    assert retained, "an outage must not evict the names that producer had admitted"
    assert retained[0].source_status == "unavailable"
    assert retained[0].source_id == "flow_pulse:fastpath"
    assert held.freshness["retained_stale"] is True
    assert held.data_quality == "degraded"

    assert "DROPPED" not in second.by_ticker(), \
        "a producer that read OK and said nothing is a real negative observation — " \
        "its only door closed, so the name leaves the set"


def test_retention_lapses_after_the_budget(tmp_path):
    """Retention is bounded — an outage cannot pin a name forever."""
    cfg = _cfg()
    layer_a = _layer_a({"HELD": "Held Corp"})
    bus1 = NominationBus(spool=_spool(tmp_path / "a"))
    nom = _nomination("HELD", source_id="flow_pulse:fastpath", family="market_price",
                      reason_code="flow_pulse.rvol_tod")
    bus1.ingest_read(ProducerRead(source_id="flow_pulse:fastpath", status="ok",
                                  nominations=(nom,), observed_at=NOW), now=NOW)
    first = assemble_probe_set(layer_a=layer_a, bus=bus1, cfg=cfg,
                               market_session="2026-08-14", now=NOW)

    much_later = NOW + timedelta(days=30)   # far past 3 retention sessions
    bus2 = NominationBus(spool=_spool(tmp_path / "b"))
    bus2.ingest_read(ProducerRead(source_id="flow_pulse:fastpath", status="unavailable",
                                  observed_at=much_later), now=much_later)
    second = assemble_probe_set(layer_a=layer_a, bus=bus2, cfg=cfg, previous=first,
                                market_session="2026-09-14", now=much_later)
    assert "HELD" not in second.by_ticker(), \
        "retention is bounded — an outage cannot pin a name in the set forever"


def test_supabase_watchlist_absent_client_is_unavailable_not_empty():
    """No credentials ⇒ ``unavailable``.  An empty watchlist is a claim; an
    outage is not."""
    got = SupabaseWatchlistAdapter(None).read(now=NOW)
    assert got.status == "unavailable"
    assert got.nominations == ()
    assert "not readable" in got.detail


def test_supabase_watchlist_with_fake_client_emits_operator_nominations():
    class _Resp:
        def __init__(self, data):
            self.data = data

    class _Table:
        def __init__(self, rows):
            self._rows = rows

        def select(self, *_a, **_k):
            return self

        def execute(self):
            return _Resp(self._rows)

    class _Client:
        def table(self, name):
            rows = {
                "watchlists": [],
                "watchlist_symbols": [{"symbol": "ZZTOP", "updated_at": "2026-08-13T00:00:00Z"}],
                "portfolio_positions": [{"symbol": "AAPL", "quantity": 100,
                                         "updated_at": "2026-08-13T00:00:00Z"}],
            }[name]
            return _Table(rows)

    got = SupabaseWatchlistAdapter(_Client()).read(now=NOW)
    assert got.status == "ok"
    by_ticker = {n.ticker: n for n in got.nominations}
    assert by_ticker["ZZTOP"].reason_code == "operator.watchlist_member"
    assert by_ticker["AAPL"].reason_code == "operator.portfolio_position"
    assert all(n.source_family == "operator" for n in got.nominations)


# ---------------------------------------------------------------------------
# Layer A wrapper classifier
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("ticker,name,expected", [
    ("TQQQ", "ProShares UltraPro QQQ", "wrapper_excluded"),
    ("SQQQ", "ProShares UltraPro Short QQQ", "wrapper_excluded"),
    ("SOXL", "Direxion Daily Semiconductor Bull 3X Shares", "wrapper_excluded"),
    ("SPY", "SPDR S&P 500 ETF Trust", "wrapper_excluded"),
    ("XYZW", "Acme Holdings Warrants", "wrapper_excluded"),
    ("ACMEU", "Acme Acquisition Corp Units", "wrapper_excluded"),
    ("AAPL", "Apple Inc.", "operating_equity"),
    ("KRUS", "Kura Sushi USA Inc", "operating_equity"),
    ("BABA", "Alibaba Group Holding Ltd ADR", "adr"),
])
def test_wrapper_classifier(ticker, name, expected):
    assert classify_eligibility(ticker, name=name).state == expected


def test_unknown_instrument_fails_closed_to_unclassified():
    """No name, no metadata ⇒ ``unclassified``.  Never a silent operating equity."""
    verdict = classify_eligibility("QQQQZ")
    assert verdict.state == "unclassified"
    assert verdict.confidence == "low"
    assert "fail-closed" in verdict.reason


def test_leveraged_etf_is_excluded_with_classification_not_silently(tmp_path):
    """A wrapper is held out WITH its classification, and the artifact says so."""
    layer_a = _layer_a({"TQQQ": "ProShares UltraPro QQQ", "AAPL": "Apple Inc."})
    assert layer_a.eligibility["TQQQ"].state == "wrapper_excluded"
    assert "TQQQ" not in layer_a.probeable()
    assert "AAPL" in layer_a.probeable()

    bus = NominationBus(spool=_spool(tmp_path))
    nom = _nomination("TQQQ", source_id="flow_pulse:fastpath", family="market_price",
                      reason_code="flow_pulse.rvol_tod")
    bus.ingest_read(ProducerRead(source_id=nom.source_id, status="ok", nominations=(nom,),
                                 observed_at=NOW), now=NOW)
    probe_set = assemble_probe_set(layer_a=layer_a, bus=bus, cfg=_cfg(),
                                   memberships={"sp500": ["AAPL", "TQQQ"]},
                                   market_session="2026-08-14", now=NOW)

    assert "AAPL" in probe_set.by_ticker(), "the operating equity is admitted"
    assert "TQQQ" not in probe_set.by_ticker(), "a leveraged wrapper is not probed"
    note = next(n for n in probe_set.to_dict()["notes"] if n["code"] == "wrapper_excluded")
    assert "TQQQ" in note["tickers"], "the exclusion is CLASSIFIED, never silent"
    assert probe_set.eligibility_counts["wrapper_excluded"] == 1


def test_unclassified_is_probed_and_flagged_never_dropped(tmp_path):
    """``unclassified`` stays in the set — dropping it would lose real companies."""
    src = UniverseSourceRead(key="sp500", status="ok", tickers=("NONAME",), meta={},
                             detail="synthetic")
    layer_a = build_layer_a([src], curated=frozenset())
    probe_set = assemble_probe_set(layer_a=layer_a, bus=NominationBus(), cfg=_cfg(),
                                   memberships={"sp500": ["NONAME"]},
                                   market_session="2026-08-14", now=NOW)
    record = probe_set.by_ticker()["NONAME"]
    assert record.eligibility == "unclassified"
    assert record.data_quality == "degraded"
    assert record.freshness["eligibility_confidence"] == "low"


# ---------------------------------------------------------------------------
# membership-expansion laundering guard (contract §6)
# ---------------------------------------------------------------------------

def test_membership_expansion_cannot_carry_a_single_name_family():
    """A basket-level reason code with a single-name family is REFUSED."""
    with pytest.raises(NominationError, match="never launder"):
        _nomination("ZZTOP", source_id="basketdata:pulse", family="market_price",
                    reason_code="membership_expansion.basket_leader")


def test_membership_expansion_family_requires_its_reason_prefix():
    """And the mirror: the family without the prefix is refused too."""
    with pytest.raises(NominationError, match="reason prefix"):
        _nomination("ZZTOP", source_id="basketdata:pulse", family="membership_expansion",
                    reason_code="board.buy")


def test_basket_level_nomination_is_well_formed():
    nom = _nomination("ZZTOP", source_id="basketdata:pulse",
                      family="membership_expansion",
                      reason_code="membership_expansion.basket_leader")
    assert nom.source_family == "membership_expansion"
    assert nom.reason_code.startswith("membership_expansion.")
    assert "membership_expansion" in SOURCE_FAMILIES


def test_pulse_emits_basket_level_and_linked_outsiders_emits_single_name(tmp_path):
    """The two basket artifacts sit on opposite sides of the laundering line."""
    from engine.entry_radar.producers import read_group_pulse, read_linked_outsiders

    pulse_path = tmp_path / "pulse.json"
    pulse_path.write_text(json.dumps({
        "semis": {"schema": "group_pulse.v1", "basket_id": "semis",
                  "as_of": "2026-08-13T20:00:00Z",
                  "direction": {"leader": {"ticker": "NVDA", "kind": "activity"},
                                "strongest": {"ticker": "AMD", "ret": 0.041},
                                "weakest": {"ticker": "INTC", "ret": -0.03}}},
    }), encoding="utf-8")
    pulse = read_group_pulse(pulse_path, now=NOW, cfg=_cfg())
    assert pulse.status in ("ok", "stale")
    assert len(pulse.nominations) == 3
    for nom in pulse.nominations:
        assert nom.source_family == "membership_expansion"
        assert nom.reason_code.startswith("membership_expansion.")
    assert {n.reason_code for n in pulse.nominations} == {
        "membership_expansion.basket_leader",
        "membership_expansion.basket_strongest",
        "membership_expansion.basket_weakest"}, "the three slots stay DISTINCT facts"

    lo_path = tmp_path / "linked_outsiders.json"
    lo_path.write_text(json.dumps({
        "semis": {"schema": "group_linked_outsiders.v1", "basket_id": "semis",
                  "as_of": "2026-08-13T20:00:00Z",
                  "outsiders": [{"ticker": "ZZTOP", "name": "ZZ Top Industries",
                                 "edge_n": 2, "last_filed_at": "2026-08-12T00:00:00Z",
                                 "linked_members": [{"member": "NVDA",
                                                     "relationship": "supply agreement",
                                                     "accession": "0001", "form": "8-K"}]}]},
    }), encoding="utf-8")
    outsiders = read_linked_outsiders(lo_path, now=NOW, cfg=_cfg())
    assert len(outsiders.nominations) == 1
    row = outsiders.nominations[0]
    assert row.source_family == "special_situation", \
        "an 8-K naming a counterparty is a fact ABOUT that company"
    assert not row.reason_code.startswith("membership_expansion.")
    assert "NVDA" in row.reason_text and "accession=0001" in (row.evidence_ref or "")


# ---------------------------------------------------------------------------
# TTL, dedup, PIT, budget
# ---------------------------------------------------------------------------

def test_ttl_expiry_removes_from_active_but_never_deletes(tmp_path):
    bus = NominationBus(spool=_spool(tmp_path))
    nom = _nomination("ZZTOP", ttl_until=NOW + timedelta(hours=1))
    bus.ingest_read(ProducerRead(source_id=nom.source_id, status="ok", nominations=(nom,),
                                 observed_at=NOW), now=NOW)
    assert len(bus.active(now=NOW)) == 1

    later = NOW + timedelta(hours=2)
    assert bus.active(now=later) == []
    assert [n.ticker for n in bus.expired(now=later)] == ["ZZTOP"], \
        "expiry removes from ACTIVE; it never deletes the record (no silent deletion)"

    probe_set = assemble_probe_set(layer_a=_layer_a({}), bus=bus, cfg=_cfg(),
                                   market_session="2026-08-14", now=later)
    assert "ZZTOP" not in probe_set.by_ticker()


def test_dedup_identity_is_source_ticker_asof_only(tmp_path):
    """Re-reading one producer at one vintage is idempotent; anything else is new."""
    bus = NominationBus(spool=_spool(tmp_path))
    nom = _nomination("ZZTOP")
    for _ in range(3):
        bus.ingest_read(ProducerRead(source_id=nom.source_id, status="ok",
                                     nominations=(nom,), observed_at=NOW), now=NOW)
    assert len(bus.active(now=NOW)) == 1
    assert bus.duplicates_dropped == 2

    # A NEW artifact vintage for the same producer+ticker is a NEW nomination.
    fresher = _nomination("ZZTOP", source_asof=NOW - timedelta(hours=1))
    bus.ingest_read(ProducerRead(source_id=fresher.source_id, status="ok",
                                 nominations=(fresher,), observed_at=NOW), now=NOW)
    assert len(bus.active(now=NOW)) == 2
    assert nom.identity != fresher.identity


def test_pit_nomination_may_not_predate_its_source_artifact():
    """§5 postdate test, made structural: it cannot even be constructed."""
    with pytest.raises(NominationError, match="predates"):
        _nomination("ZZTOP", observed_at=YESTERDAY, source_asof=NOW)

    ok = _nomination("ZZTOP", observed_at=NOW, source_asof=NOW)
    assert ok.observed_at == ok.source_asof, "equal timestamps are legal"


def test_budget_exceeded_emits_a_note_and_truncates_nothing(tmp_path, capsys):
    """1,700 names deserve probing ⇒ 1,700 are probed and the budget escalates."""
    names = {f"T{i:04d}": f"Synthetic Corp {i}" for i in range(1700)}
    layer_a = _layer_a(names)
    # Admitted through Layer B (index membership) — Layer A admits nobody.
    probe_set = assemble_probe_set(layer_a=layer_a, bus=NominationBus(), cfg=_cfg(),
                                   memberships={"sp500": sorted(names)},
                                   market_session="2026-08-14", now=NOW)

    assert len(probe_set) == 1700, "nothing may be truncated"
    assert probe_set.budget["state"] == "exceeded"
    assert probe_set.budget["truncated"] is False
    assert probe_set.budget["n_probed"] == 1700
    note = next(n for n in probe_set.to_dict()["notes"] if n["code"] == "budget_exceeded")
    assert "NOTHING truncated" in note["text"]

    out = capsys.readouterr().out
    line = next(ln for ln in out.splitlines() if "entry-radar-budget" in ln)
    assert line.startswith("::warning"), \
        "GitHub annotations must START the line (bare print, never a logger)"


# ---------------------------------------------------------------------------
# frozen contract shape
# ---------------------------------------------------------------------------

def test_nomination_v1_field_list_is_frozen():
    """The dataclass and the declared §6.1 field list can never drift apart."""
    assert nomination_dataclass_fields() == NOMINATION_FIELDS
    assert NOMINATION_FIELDS == (
        "ticker", "source_id", "source_family", "reason_code", "reason_text",
        "observed_at", "source_asof", "source_rank", "source_value",
        "source_horizon", "ttl_until", "evidence_ref", "data_quality")
    assert set(_nomination().to_dict()) == set(NOMINATION_FIELDS)
    with pytest.raises(NominationError, match="frozen"):
        Nomination.from_dict({**_nomination().to_dict(), "detector_score": 91})


def test_source_families_are_the_frozen_eleven():
    assert SOURCE_FAMILIES == frozenset({
        "market_price", "theme_sector", "fund_etf_flow", "smart_money", "options",
        "off_exchange", "news_catalyst", "fundamental", "special_situation",
        "operator", "membership_expansion"})


def test_probe_record_carries_no_score_field():
    """The no-scores law, enforced on the frozen field list itself."""
    assert PROBE_RECORD_FIELDS == (
        "ticker", "admission_layers", "admission_reasons", "eligibility",
        "history_age_sessions", "first_admitted_at", "last_refreshed_at",
        "freshness", "data_quality", "nominations")
    for banned in ("score", "rank", "points", "bullish", "candidate", "weight", "grade"):
        assert not any(banned in f for f in PROBE_RECORD_FIELDS)
    with pytest.raises(NominationError, match="score/rank"):
        assert_no_score_fields({"ticker": "ZZTOP", "detector_score": 91})


def test_hot_tape_tap_emits_nominations_without_touching_the_marketing_lane():
    """The tap is a pure function over in-memory events (hot_tape has no artifact)."""
    events = [{"ticker": "ZZTOP", "kind": "gap_up", "change_pct": 8.4},
              {"sym": "AAPL", "event": "volume_surge"}]
    noms = tap_hot_tape_events(events, source_asof=YESTERDAY, now=NOW)
    assert {n.ticker for n in noms} == {"ZZTOP", "AAPL"}
    assert all(n.source_family == "news_catalyst" for n in noms)
    assert all(n.reason_code.startswith("hot_tape.") for n in noms)
    assert noms[0].source_value == 8.4
    assert all(n.data_quality == "ok" for n in noms)

    # No artifact vintage ⇒ honest degradation, not an invented asof.
    degraded = tap_hot_tape_events(events, now=NOW)
    assert all(n.data_quality == "degraded" for n in degraded)


# ---------------------------------------------------------------------------
# Prophet / protected-path boundary (contract §1, §16)
# ---------------------------------------------------------------------------

PROTECTED_PATHS = (
    "engine/entry_signal.py",
    "engine/signal_gate.py",
    "engine/confluence_tiers.py",
    "engine/signal_quality.py",
    "engine/washout_turn.py",
    "engine/mtf_upturn.py",
    "engine/prophet_",
    "engine/stock_identity/",
)

PROTECTED_IMPORTS = (
    "engine.entry_signal", "engine.signal_gate", "engine.confluence_tiers",
    "engine.signal_quality", "engine.washout_turn", "engine.mtf_upturn",
    "engine.stock_identity", "engine.prophet_", "engine.setups",
    "engine.stock_personality", "scripts.build_stock_library", "build_stock_library",
)

RADAR_SOURCES = sorted(
    [*(ROOT / "engine" / "entry_radar").rglob("*.py"),
     *(ROOT / "scripts").glob("entry_radar_*.py")])


def test_radar_sources_exist():
    """Guards must never go vacuous through an empty file list."""
    assert len(RADAR_SOURCES) >= 10, RADAR_SOURCES


@pytest.mark.parametrize("path", RADAR_SOURCES, ids=lambda p: p.name)
def test_no_radar_module_imports_a_protected_module(path):
    """Non-interference, statically: Radar reads ARTIFACTS, never gate code.

    This guard is git-independent, so it holds even where the diff guard below
    cannot resolve a base ref.
    """
    text = path.read_text(encoding="utf-8")
    code = "\n".join(ln for ln in text.splitlines()
                     if ln.strip().startswith(("import ", "from ")))
    for banned in PROTECTED_IMPORTS:
        assert banned not in code, f"{path.name} imports protected module {banned!r}"


# The two diff guards below are RADAR-LANE boundary contracts, and they must
# SELF-SCOPE to diffs that actually touch Radar code. They run inside the shared
# always-on signal-contract job, where CI checks out the PR *merge ref* — so an
# unscoped ``git diff base...HEAD`` names EVERY pr's own files. Unscoped, these
# asserts red ci-pack-4 for every non-Radar PR in the fleet (measured 2026-08-14:
# a research-only PR's files printed as "strays"; main's own baseline passes only
# because its diff is empty). A per-lane scope guard wired into an always-on job
# is a fleet control plane — it may only bind the lane it governs.
# Triggers are the RUNTIME surfaces only. Deliberately NOT ``tests/test_entry_
# radar_``: the guards contain runtime scope, which a tests-only diff cannot
# stray from — and a fleet heal of these very guards must not re-trigger them.
_RADAR_CODE_PREFIXES = ("engine/entry_radar/", "scripts/entry_radar_", "scripts/reconcile_entry_radar.py",
                        "config/entry_radar.yml")


def _branch_diff_vs_base() -> list[str] | None:
    """Changed paths vs origin/main (merge-base three-dot), or None if no base."""
    base = None
    for candidate in ("origin/main", "main"):
        probe = subprocess.run(["git", "rev-parse", "--verify", candidate],
                               cwd=ROOT, capture_output=True, text=True, check=False)
        if probe.returncode == 0:
            base = candidate
            break
    if base is None:
        return None
    got = subprocess.run(["git", "diff", "--name-only", f"{base}...HEAD"],
                         cwd=ROOT, capture_output=True, text=True, check=False)
    if got.returncode != 0 and "no merge base" in (got.stderr or ""):
        # A depth-limited CI checkout can hold the ref while lacking the history
        # that joins it to HEAD (`fatal: origin/main...HEAD: no merge base`) —
        # the same environmental impossibility as the missing-ref case, with the
        # same answer: the git-independent import guard still carries
        # non-interference. Receipt: run 31838336391 pack-4, hosted runner.
        return None
    assert got.returncode == 0, got.stderr
    return [ln.strip() for ln in got.stdout.splitlines() if ln.strip()]


def test_branch_diff_touches_no_protected_path():
    """``git diff --name-only <base>...HEAD`` must not name a protected path."""
    changed = _branch_diff_vs_base()
    if changed is None:
        pytest.skip("no origin/main or main ref in this checkout — the import guard "
                    "above still covers non-interference")
    if not any(p.startswith(_RADAR_CODE_PREFIXES) for p in changed):
        pytest.skip("diff touches no Radar code — the boundary guard binds Radar "
                    "lanes only; the import guard above still covers non-interference")
    offenders = [p for p in changed if any(p.startswith(x) for x in PROTECTED_PATHS)]
    assert not offenders, f"Radar PR touched protected Prophet paths: {offenders}"


def test_radar_owns_only_its_declared_paths():
    """§16 ("Radar owns — NEW PATHS ONLY"), as a property of the TREE.

    This guard used to read ``git diff --name-only <base>...HEAD`` and fail on any
    changed path outside a Radar allowlist.  That form polices the scope of ONE pull
    request — #5625, which has merged — so on main it asks every OTHER pull request
    to be a Radar pull request, and fails all of them.  Receipt: run 31825207851, a
    qledger ship branch, red with "PR-1 touched paths outside the Radar-owned set:
    ['engine/demand_ledger.py', 'engine/qledger.py', ...]" — files that have nothing
    to do with the Radar and that no Radar rule forbids.

    It was also unfixable as a diff check.  A repo-wide CI heal is REQUIRED to pin
    scripts/entry_radar_universe.py (tests/test_check_script_import_pinning.py) while
    also carrying unrelated heals; under the allowlist those two mandates contradict,
    so no arming condition on "touched a Radar path" can be satisfied by both.

    NON-INTERFERENCE IS NOT WEAKENED BY THIS, because it was never this test's job.
    The contract's boundary is carried by the two guards directly above, both intact:
    ``test_no_radar_module_imports_a_protected_module`` (git-independent, parametrized
    over every Radar source, and the one §16 calls mechanical) and
    ``test_branch_diff_touches_no_protected_path`` (a diff guard that names PROTECTED
    paths only, so it reds a PR that touches Prophet gate code and nothing else).

    What remains enforceable — and is enforced here — is §16's own sentence: the
    Radar's footprint LIVES at the declared paths.  A Radar module dropped into
    engine/ root, or a radar script outside scripts/entry_radar_*.py, is sprawl this
    catches in any checkout, with no base ref and no PR context.
    """
    owned_exact = {"config/entry_radar.yml", "templates/entry_radar.html.j2",
                   "site/entry_radar.html"}
    owned_prefixes = ("engine/entry_radar/", "scripts/entry_radar_",
                      # the contract (§7.3) names the reconciler VERBATIM as the
                      # sole durable writer — an owned path by the frozen text:
                      "scripts/reconcile_entry_radar.py",
                      "tests/test_entry_radar_", "tests/fixtures/entry_radar/",
                      "data/entry_radar/",
                      "research/LIVE_ENTRY_RADAR_", "research/live_entry_radar/",
                      "mockups/refs/entry_radar/", "agentos/")
    listed = subprocess.run(["git", "ls-files"], cwd=ROOT,
                            capture_output=True, text=True, check=False)
    assert listed.returncode == 0, listed.stderr
    tracked = [ln.strip() for ln in listed.stdout.splitlines() if ln.strip()]
    radar_named = [p for p in tracked
                   if "entry_radar" in p or "LIVE_ENTRY_RADAR" in p]
    # Vacuity guard, same reason as test_radar_sources_exist: an empty census would
    # make this pass for the wrong reason forever.
    assert len(radar_named) >= 10, radar_named
    strays = [p for p in radar_named
              if p not in owned_exact and not p.startswith(owned_prefixes)]
    assert not strays, (
        "Radar files exist outside the §16 owned path set (new paths only): "
        f"{strays}")


# ---------------------------------------------------------------------------
# B1 REGRESSION — one producer, one vintage, several distinct facts
# ---------------------------------------------------------------------------

def _board_nom(ticker: str, code: str, *, source_id="factordata:us_standouts",
               lane: str = "") -> Nomination:
    return Nomination(
        ticker=ticker, source_id=source_id, source_family="market_price",
        reason_code=code, reason_text=f"{ticker} on {code}",
        observed_at=NOW, source_asof=YESTERDAY,
        evidence_ref=f"us_standouts.json#{lane or code}/{ticker}")


def test_one_board_listing_a_ticker_in_two_lanes_keeps_both(tmp_path):
    """B1: same source_id, same ticker, same vintage — DIFFERENT lanes.

    The dedup identity must not collapse ``board.buy`` and ``board.leader`` for
    NVDA into one record.  It did: 2 ingested, 1 kept, duplicates_dropped 0.
    """
    bus = NominationBus(spool=_spool(tmp_path))
    buy = _board_nom("NVDA", "board.buy", lane="buy")
    leader = _board_nom("NVDA", "board.leader", lane="leaders")
    assert buy.identity != leader.identity, "distinct facts need distinct identities"

    admitted = bus.ingest_read(ProducerRead(
        source_id="factordata:us_standouts", status="ok", nominations=(buy, leader),
        source_asof=YESTERDAY, observed_at=NOW), now=NOW)

    assert admitted == 2
    kept = bus.for_ticker("NVDA", now=NOW)
    assert len(kept) == 2
    assert {n.reason_code for n in kept} == {"board.buy", "board.leader"}
    assert bus.duplicates_dropped == 0


def test_one_basket_file_naming_a_ticker_in_several_slots_keeps_all(tmp_path):
    """B1, second shape: AAPL as leader+strongest of one basket AND leader of another."""
    bus = NominationBus(spool=_spool(tmp_path))

    def pulse(basket: str, slot: str) -> Nomination:
        return Nomination(
            ticker="AAPL", source_id="basketdata:pulse",
            source_family="membership_expansion",
            reason_code=f"membership_expansion.basket_{slot}",
            reason_text=f"AAPL {slot} of {basket}", observed_at=NOW,
            source_asof=YESTERDAY,
            evidence_ref=f"pulse.json#{basket}/direction/{slot}")

    noms = (pulse("megacap", "leader"), pulse("megacap", "strongest"),
            pulse("hardware", "leader"), pulse("hardware", "weakest"))
    admitted = bus.ingest_read(ProducerRead(
        source_id="basketdata:pulse", status="ok", nominations=noms,
        source_asof=YESTERDAY, observed_at=NOW), now=NOW)

    assert admitted == 4
    assert len(bus.for_ticker("AAPL", now=NOW)) == 4, \
        "four distinct basket facts must not collapse to one"
    assert bus.duplicates_dropped == 0
    refs = {n.evidence_ref for n in bus.for_ticker("AAPL", now=NOW)}
    assert len(refs) == 4, "each keeps its own evidence pointer"


def test_spool_and_published_probe_set_never_disagree(tmp_path):
    """The invariant B1 broke: what the spool holds is what the artifact shows."""
    bus = NominationBus(spool=_spool(tmp_path))
    noms = (_board_nom("NVDA", "board.buy", lane="buy"),
            _board_nom("NVDA", "board.leader", lane="leaders"),
            _board_nom("KRUS", "board.buy", lane="buy"))
    bus.ingest_read(ProducerRead(source_id="factordata:us_standouts", status="ok",
                                 nominations=noms, source_asof=YESTERDAY,
                                 observed_at=NOW), now=NOW)

    spooled = json.loads((tmp_path / "spool" / bus.spool_keys[0]).read_text(encoding="utf-8"))
    probe_set = assemble_probe_set(
        layer_a=_layer_a({"NVDA": "NVIDIA Corp", "KRUS": "Kura Sushi USA Inc"}),
        bus=bus, cfg=_cfg(), market_session="2026-08-14", now=NOW)
    published = [n for rec in probe_set.records for n in rec.nominations]

    assert spooled["n_nominations"] == len(published) == 3
    assert ({(n["ticker"], n["reason_code"]) for n in spooled["nominations"]}
            == {(n.ticker, n.reason_code) for n in published})


def test_genuine_reread_is_still_idempotent_and_counted(tmp_path):
    """Widening identity must not stop the bus deduping a true re-read."""
    bus = NominationBus(spool=_spool(tmp_path))
    nom = _board_nom("NVDA", "board.buy", lane="buy")
    for _ in range(3):
        bus.ingest_read(ProducerRead(source_id=nom.source_id, status="ok",
                                     nominations=(nom,), observed_at=NOW), now=NOW)
    assert len(bus.for_ticker("NVDA", now=NOW)) == 1
    assert bus.duplicates_dropped == 2


def test_same_pass_duplicates_are_counted_not_silently_overwritten(tmp_path):
    """A within-pass repeat is a REFUSAL, and refusals are counted."""
    bus = NominationBus(spool=_spool(tmp_path))
    nom = _board_nom("NVDA", "board.buy", lane="buy")
    admitted = bus.ingest_read(ProducerRead(
        source_id=nom.source_id, status="ok", nominations=(nom, nom),
        observed_at=NOW), now=NOW)
    assert admitted == 1
    assert bus.duplicates_dropped == 1


# ---------------------------------------------------------------------------
# B2 REGRESSION — Layer A is a lens, membership is B ∪ C ∪ D
# ---------------------------------------------------------------------------

def test_layer_a_admits_nobody_on_its_own(tmp_path):
    """B2: 800 eligible names with no B/C/D reason ⇒ an EMPTY probe set."""
    names = {f"T{i:04d}": f"Synthetic Corp {i}" for i in range(800)}
    probe_set = assemble_probe_set(layer_a=_layer_a(names), bus=NominationBus(),
                                   cfg=_cfg(), market_session="2026-08-14", now=NOW)
    assert len(probe_set) == 0, "eligibility is not admission"
    assert probe_set.universe["eligible"] == 800
    assert probe_set.layer_counts["A"] == 0


def test_probe_set_narrows_to_the_union_of_the_real_doors(tmp_path):
    """A large eligible universe narrows to B ∪ C ∪ D, inside the budget."""
    names = {f"T{i:04d}": f"Synthetic Corp {i}" for i in range(2966)}
    layer_a = _layer_a(names)

    memberships = {"sp500": [f"T{i:04d}" for i in range(500)]}          # Layer B
    liquidity = {f"T{i:04d}": {"dollar_vol_20d": 9e9} for i in range(500)}
    hot = {f"T{i:04d}": {"rel_volume": 5.0} for i in range(500, 620)}   # Layer C
    bus = NominationBus(spool=_spool(tmp_path))
    lobe = _nomination("T2900", source_id="ipo:calendar",
                       reason_code="ipo.recent_listing")               # Layer D
    bus.ingest_read(ProducerRead(source_id="ipo:calendar", status="ok",
                                 nominations=(lobe,), source_asof=YESTERDAY,
                                 observed_at=NOW), now=NOW)

    probe_set = assemble_probe_set(layer_a=layer_a, bus=bus, cfg=_cfg(),
                                   memberships=memberships, liquidity=liquidity,
                                   hot_features=hot, market_session="2026-08-14", now=NOW)

    assert len(probe_set) == 621, "500 core + 120 hot + 1 lobe"
    assert probe_set.universe["eligible"] == 2966
    assert probe_set.budget["state"] == "within", \
        "the budget must be answerable, not exceeded on every pass by construction"
    assert probe_set.layer_counts["B"] == 500
    assert probe_set.layer_counts["C"] == 120
    assert probe_set.layer_counts["D"] == 1
    assert probe_set.layer_counts["A"] == 621, "A counts probed names it vouches for"
    assert not any(n["code"] == "budget_exceeded" for n in probe_set.to_dict()["notes"])


def test_budget_warning_does_not_fire_on_a_normal_pass(tmp_path, capsys):
    """The escalation must be an event, not the weather."""
    names = {f"T{i:04d}": f"Synthetic Corp {i}" for i in range(2966)}
    capsys.readouterr()
    assemble_probe_set(layer_a=_layer_a(names), bus=NominationBus(), cfg=_cfg(),
                       memberships={"sp500": [f"T{i:04d}" for i in range(900)]},
                       market_session="2026-08-14", now=NOW)
    assert "entry-radar-budget" not in capsys.readouterr().out


# ---------------------------------------------------------------------------
# B3 REGRESSION — a universe-source outage must not empty the probe set
# ---------------------------------------------------------------------------

def test_universe_source_outage_retains_prior_members(tmp_path):
    """B3: an index read failing evicted every name it had admitted (800 → 0)."""
    names = {f"T{i:04d}": f"Synthetic Corp {i}" for i in range(800)}
    members = sorted(names)

    healthy = _layer_a(names)
    first = assemble_probe_set(layer_a=healthy, bus=NominationBus(), cfg=_cfg(),
                               memberships={"sp500": members},
                               market_session="2026-08-14", now=NOW)
    assert len(first) == 800

    later = NOW + timedelta(days=1)
    dead = UniverseSourceRead(key="sp500", status="unavailable", detail="read failed")
    second = assemble_probe_set(layer_a=build_layer_a([dead], curated=frozenset()),
                                bus=NominationBus(), cfg=_cfg(), memberships={},
                                previous=first, market_session="2026-08-15", now=later)

    assert len(second) == 800, "a reader crash is not a market event"
    note = next(n for n in second.to_dict()["notes"] if n["code"] == "producers_unavailable")
    assert note["retained_names"] == 800
    assert "breadth:constituents:sp500" in note["sources"]

    sample = second.by_ticker()["T0000"]
    retained = [r for r in sample.admission_reasons if r.retained_stale]
    assert retained and retained[0].source_status == "unavailable"
    assert retained[0].source_id == "breadth:constituents:sp500"
    assert sample.data_quality == "degraded"


def test_universe_source_id_matches_the_layer_b_reason_id():
    """The mismatch that silently disabled retention, pinned directly."""
    from engine.entry_radar.universe import layer_b_admissions, universe_source_id

    reasons = layer_b_admissions(_cfg(), memberships={"sp500": ["AAPL"]}, now=NOW)
    assert reasons["AAPL"][0].source_id == universe_source_id("sp500")
    assert universe_source_id("deep_history") == "universe:deep_history"


# ---------------------------------------------------------------------------
# improvements
# ---------------------------------------------------------------------------

def test_dollar_vol_rank_is_derived_at_assembly(tmp_path):
    """The knob had no feeder upstream; the rank is computed from dollar_vol_20d."""
    from engine.entry_radar.universe import _with_dollar_vol_rank

    ranked = _with_dollar_vol_rank({"BIG": {"dollar_vol_20d": 9e9},
                                    "MID": {"dollar_vol_20d": 5e8},
                                    "SML": {"dollar_vol_20d": 1e6}})
    assert [ranked[s]["dollar_vol_rank"] for s in ("BIG", "MID", "SML")] == [1, 2, 3]

    features = {f"T{i:04d}": {"dollar_vol_20d": float(10_000 - i)} for i in range(400)}
    probe_set = assemble_probe_set(layer_a=_layer_a({s: f"Corp {s}" for s in features}),
                                   bus=NominationBus(), cfg=_cfg(),
                                   hot_features=features, market_session="2026-08-14",
                                   now=NOW)
    assert len(probe_set) == 300, "top-300 by the dollar_vol_rank_max knob"
    reason = probe_set.by_ticker()["T0000"].admission_reasons[0]
    assert reason.reason_code == "hot.dollar_vol_rank"
    assert reason.detail["value"] == 1


def test_future_vintage_is_clamped_but_never_silently(tmp_path):
    """A clamp is recorded, and a clamped read is never graded ``ok``."""
    from engine.entry_radar.producers import read_flow_pulse
    from engine.entry_radar.producers.base import clamp_asof

    assert clamp_asof(NOW + timedelta(hours=5), NOW) == (NOW, True)
    assert clamp_asof(YESTERDAY, NOW) == (YESTERDAY, False)

    path = tmp_path / "flow_pulse.json"
    path.write_text(json.dumps({
        "schema": "flow_pulse.v1", "as_of": "2026-08-20T00:00:00Z", "stale": False,
        "tickers": [{"ticker": "ZZTOP", "rvol_tod": 9.0}]}), encoding="utf-8")
    got = read_flow_pulse(path, now=NOW, cfg=_cfg())
    assert got.read.status == "stale", "a future vintage is not a fresh one"
    assert got.read.nominations[0].data_quality == "degraded"
    assert got.read.nominations[0].source_asof <= NOW
    assert "clamped" in got.read.detail


def test_spool_keys_do_not_collide_within_one_second(tmp_path):
    """Two lanes spooling in the same second must not overwrite each other."""
    from engine.entry_radar.spool import spool_key

    a = spool_key("2026-08-14", "143000", pass_id="nightly")
    b = spool_key("2026-08-14", "143000", pass_id="hot_tape")
    assert a != b and a.endswith("-nightly.json") and b.endswith("-hot_tape.json")

    spool = _spool(tmp_path)
    nom = _nomination("ZZTOP")
    assert spool.append([nom], now=NOW, pass_id="nightly")
    assert spool.append([_nomination("KRUS")], now=NOW, pass_id="hot_tape")
    assert len(sorted((tmp_path / "spool").rglob("*.json"))) == 2, "no silent overwrite"


def test_missing_market_session_warns_rather_than_mis_stamping(capsys):
    assemble_probe_set(layer_a=_layer_a({}), bus=NominationBus(), cfg=_cfg(), now=NOW)
    out = capsys.readouterr().out
    line = next(ln for ln in out.splitlines() if "market_session" in ln)
    assert line.startswith("::warning")


def test_every_config_key_binds_something():
    """A config key that binds nothing is a lie — pin the ones we ship."""
    import yaml
    from engine.entry_radar.producers import stale_after
    from engine.entry_radar.producers.constituents import sources_from_config

    raw = yaml.safe_load((ROOT / "config" / "entry_radar.yml").read_text())["entry_radar"]
    cfg = _cfg()

    # producers.stale_after_minutes ids must be REAL source ids.
    from engine.entry_radar.producers import (
        FLOW_PULSE_SOURCE_ID, IPO_SOURCE_ID, LINKED_OUTSIDERS_SOURCE_ID,
        PULSE_SOURCE_ID, SETUPS_SOURCE_ID, STANDOUTS_SOURCE_ID,
        STOCK_LIBRARY_SOURCE_ID)
    from engine.entry_radar.spool import HOT_TAPE_SOURCE_ID
    from engine.entry_radar.universe import SupabaseWatchlistAdapter, universe_source_id
    real = {FLOW_PULSE_SOURCE_ID, IPO_SOURCE_ID, LINKED_OUTSIDERS_SOURCE_ID,
            PULSE_SOURCE_ID, SETUPS_SOURCE_ID, STANDOUTS_SOURCE_ID,
            STOCK_LIBRARY_SOURCE_ID, HOT_TAPE_SOURCE_ID, "hot_tape:outbox",
            SupabaseWatchlistAdapter.SOURCE_ID, "breadth:constituents"}
    declared = set(raw["producers"]["stale_after_minutes"])
    assert declared <= real, f"config names non-existent producers: {declared - real}"

    # the prefix key really does cover the per-index ids
    assert stale_after(cfg, universe_source_id("sp500")) == 10080

    # layer_a.sources is consumed
    assert [k for k, _, _ in sources_from_config(cfg)] == [
        s["key"] for s in raw["layer_a"]["sources"]]

    # the keys we deleted stay deleted
    assert "min_history_sessions" not in raw["layer_a"]
    assert "default_ttl_minutes" not in raw["spool"]
