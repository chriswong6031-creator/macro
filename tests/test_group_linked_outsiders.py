"""GR3 — `group_linked_outsiders.v1` contract, resolver, subtypes, and states.

Every fixture here is synthetic and injected through an explicit `data_root` /
`site_root`, so no assertion depends on today's live tape or on a collector run.
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path
from types import ModuleType

import pandas as pd
import pytest

from engine import group_linked_outsiders as glo


# --------------------------------------------------------------------------
# Fixtures — a two-basket world with a registry, filings, and tape
# --------------------------------------------------------------------------

AS_OF = date(2026, 8, 7)

MEMBERSHIP = {
    "version": 1,
    "baskets": {
        "ai_infra": {
            "name": "AI Infrastructure",
            "members": [
                {"ticker": "NVDA", "added": "2024-01-01", "removed": None},
                {"ticker": "AVGO", "added": "2024-01-01", "removed": None},
                {"ticker": "GONE", "added": "2024-01-01", "removed": "2025-01-01"},
            ],
        },
        "solar": {
            "name": "Solar",
            "members": [{"ticker": "ENPH", "added": "2024-01-01", "removed": None}],
        },
    },
}

REGISTRY_ROWS = [
    {"ticker": "NVDA", "cik": 1045810, "title": "NVIDIA CORP"},
    {"ticker": "AVGO", "cik": 1730168, "title": "Broadcom Inc."},
    {"ticker": "ENPH", "cik": 1463101, "title": "Enphase Energy, Inc."},
    {"ticker": "TSM", "cik": 1046179, "title": "Taiwan Semiconductor Manufacturing"},
    {"ticker": "WOLF", "cik": 895419, "title": "Wolfspeed, Inc."},
    {"ticker": "DARK", "cik": 111111, "title": "Darkside Industries"},
    # A dual-class registrant: one title, two tickers -> an admissibility tie.
    {"ticker": "TWNA", "cik": 222222, "title": "Twinning Holdings"},
    {"ticker": "TWNB", "cik": 222222, "title": "Twinning Holdings"},
]


def _write_registry(root: Path) -> None:
    directory = root / "symbol_directory" / "cik_map"
    directory.mkdir(parents=True, exist_ok=True)
    # An older snapshot that must lose to the newer one on filename date.
    pd.DataFrame([{"ticker": "OLD", "cik": 1, "title": "Stale Snapshot Only"}]).to_parquet(
        directory / "2020-01-01.parquet", index=False,
    )
    pd.DataFrame(REGISTRY_ROWS).to_parquet(directory / "2026-08-06.parquet", index=False)


def _write_membership(root: Path) -> None:
    directory = root / "baskets"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "membership.json").write_text(json.dumps(MEMBERSHIP), encoding="utf-8")


def _event(ticker, filing_date, items, accession, counterparty, **extra):
    row = {
        "ticker": ticker,
        "cik": 1,
        "form": "8-K",
        "filing_date": filing_date,
        "items": items,
        "accession": accession,
        "_first_seen": "2026-01-01T00:00:00+00:00",
        "amount_usd": None,
        "counterparty": counterparty,
        "extraction_ok": True,
    }
    row.update(extra)
    return row


DEFAULT_EVENTS = [
    # NVDA -> TSM, two filings, so TSM outranks a single-edge outsider.
    _event("NVDA", "2026-07-01", "1.01", "acc-1", "Taiwan Semiconductor Manufacturing"),
    _event("NVDA", "2026-06-01", "1.01", "acc-2", "Taiwan Semiconductor Manufacturing"),
    # AVGO -> WOLF, one filing, Item 2.03 only -> financing by the item rule.
    _event("AVGO", "2026-05-01", "2.03", "acc-3", "Wolfspeed, Inc."),
    # NVDA -> AVGO: an INSIDER of the same basket, never published as an outsider.
    _event("NVDA", "2026-04-01", "1.01", "acc-4", "Broadcom Inc."),
    # NVDA -> NVDA: a self-reference.
    _event("NVDA", "2026-03-02", "1.01", "acc-5", "NVIDIA CORP"),
    # NVDA -> an ambiguous dual-class registrant.
    _event("NVDA", "2026-03-01", "1.01", "acc-6", "Twinning Holdings"),
    # NVDA -> a name in no registry.
    _event("NVDA", "2026-02-01", "1.01", "acc-7", "Nowhere Systems"),
    # Aged out of the 24-month window by one day.
    _event("NVDA", "2024-08-06", "1.01", "acc-8", "Darkside Industries"),
    # A non-material item never becomes a candidate.
    _event("NVDA", "2026-07-02", "8.01", "acc-9", "Darkside Industries"),
    # A filer that is not a basket member.
    _event("XXXX", "2026-07-03", "1.01", "acc-10", "Darkside Industries"),
]


def _write_events(root: Path, rows=None) -> None:
    directory = root / "edgar"
    directory.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows if rows is not None else DEFAULT_EVENTS).to_parquet(
        directory / "material_8k_events.parquet", index=False,
    )


def _bars(root: Path, ticker: str, *, n: int = 200, last: date = AS_OF,
          jump: float = 0.0, volume_spike: float = 1.0, store: str = "stocks") -> None:
    """Deterministic bars: flat 0.1%/day drift, then an optional final-day jump."""
    directory = root / store
    directory.mkdir(parents=True, exist_ok=True)
    index = pd.bdate_range(end=pd.Timestamp(last), periods=n)
    closes = [100.0]
    for i in range(1, n):
        closes.append(closes[-1] * (1.0 + (0.001 if i % 2 else -0.0005)))
    if jump:
        closes[-1] = closes[-2] * (1.0 + jump)
    volumes = [1_000_000] * n
    volumes[-1] = int(1_000_000 * volume_spike)
    pd.DataFrame({"close": closes, "volume": volumes}, index=index).to_parquet(
        directory / f"{ticker}.parquet",
    )


def _spy(root: Path, *, n: int = 200, last: date = AS_OF) -> None:
    directory = root / "yahoo"
    directory.mkdir(parents=True, exist_ok=True)
    index = pd.bdate_range(end=pd.Timestamp(last), periods=n)
    closes = [500.0 * (1.0 + 0.0001) ** i for i in range(n)]
    pd.DataFrame({"close": closes, "volume": [1] * n}, index=index).to_parquet(
        directory / "SPY.parquet",
    )


@pytest.fixture()
def world(tmp_path: Path) -> Path:
    root = tmp_path / "data"
    root.mkdir()
    _write_membership(root)
    _write_registry(root)
    _write_events(root)
    _spy(root)
    return root


# --------------------------------------------------------------------------
# Contract: golden + mutant
# --------------------------------------------------------------------------


def test_golden_artifact_validates(world: Path, tmp_path: Path):
    result = glo.compute(as_of=AS_OF, data_root=world, site_root=tmp_path / "site", pulse={})
    assert set(result) == {"ai_infra", "solar"}
    for obj in result.values():
        glo.validate_artifact(obj)
    infra = result["ai_infra"]
    assert infra["schema"] == "group_linked_outsiders.v1"
    assert infra["authority"] == "context_only"
    assert infra["edge_window_months"] == 24
    assert infra["as_of"] == "2026-08-07"
    # A basket with no edges still gets an object with the key present.
    assert result["solar"]["outsiders"] == []
    assert result["solar"]["n_outsiders"] == 0


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(lambda o: o.update({"heat_score": 1}), id="unknown_top_level_key"),
        pytest.param(lambda o: o.pop("basis"), id="missing_key"),
        pytest.param(lambda o: o.update({"authority": "signal"}), id="authority_escalated"),
        pytest.param(lambda o: o.update({"schema": "group_linked_outsiders.v2"}), id="wrong_schema"),
        pytest.param(lambda o: o.update({"n_outsiders": 99}), id="count_disagrees_with_list"),
        pytest.param(lambda o: o.update({"edge_window_months": 6}), id="undisclosed_window"),
        pytest.param(lambda o: o.update({"basis": "trust us"}), id="basis_rewritten"),
        pytest.param(lambda o: o["outsiders"][0].update({"rank": 1}), id="unknown_outsider_key"),
        pytest.param(lambda o: o["outsiders"][0].update({"state": "confirmed"}), id="unknown_state"),
        pytest.param(lambda o: o["outsiders"][0].update({"edge_n": 42}), id="edge_n_disagrees"),
        pytest.param(
            lambda o: o["outsiders"][0]["linked_members"][0].update({"relationship": "supplier"}),
            id="role_label_relationship",
        ),
        pytest.param(
            lambda o: o["outsiders"][0]["linked_members"][0].update({"score": 0.9}),
            id="unknown_link_key",
        ),
        pytest.param(lambda o: o.update({"n_confirming": 7}), id="n_confirming_disagrees"),
        pytest.param(lambda o: o.update({"n_with_tape": 7}), id="n_with_tape_disagrees"),
    ],
)
def test_mutant_artifact_is_rejected(world: Path, tmp_path: Path, mutate):
    result = glo.compute(as_of=AS_OF, data_root=world, site_root=tmp_path / "site", pulse={})
    obj = json.loads(json.dumps(result["ai_infra"]))
    assert obj["outsiders"], "fixture must publish at least one outsider to mutate"
    mutate(obj)
    with pytest.raises(glo.ContractError):
        glo.validate_artifact(obj)


def test_no_score_rank_or_heat_key_anywhere(world: Path, tmp_path: Path):
    """G0-2 tripwire: this artifact mints no composite number."""
    result = glo.compute(as_of=AS_OF, data_root=world, site_root=tmp_path / "site", pulse={})
    banned = ("score", "rank", "heat")

    def walk(node, trail="$"):
        if isinstance(node, dict):
            for key, value in node.items():
                assert not any(b in str(key).lower() for b in banned), f"{trail}.{key}"
                walk(value, f"{trail}.{key}")
        elif isinstance(node, list):
            for i, value in enumerate(node):
                walk(value, f"{trail}[{i}]")

    walk(result)


def test_no_role_labels_in_the_relationship_vocabulary():
    for relationship in glo.RELATIONSHIPS:
        for banned in glo.FORBIDDEN_ROLE_LABELS:
            assert banned not in relationship, f"{relationship!r} carries a role label"


# --------------------------------------------------------------------------
# Resolver admissibility matrix
# --------------------------------------------------------------------------


@pytest.fixture()
def registry(world: Path):
    buckets, path = glo.load_registry(world)
    assert path is not None and path.name == "2026-08-06.parquet", "newest snapshot must win"
    return buckets


@pytest.mark.parametrize(
    ("name", "expected_ticker", "expected_reason"),
    [
        ("NVIDIA CORP", "NVDA", None),                       # verbatim
        ("nvidia corp.", "NVDA", None),                      # case + punctuation only
        ("NVIDIA", "NVDA", None),                            # one-sided legal suffix
        ("Wolfspeed, Inc.", "WOLF", None),
        ("Wolfspeed", "WOLF", None),
        ("Twinning Holdings", None, "ambiguous_tie"),        # two tickers, one title
        ("Nowhere Systems", None, "no_registrant_match"),
        ("NVID", None, "no_registrant_match"),               # no substring matching
        ("NVIDIA Corporation of America", None, "no_registrant_match"),
        ("Wolfspeed Ltd.", None, "no_registrant_match"),     # two different designators
        ("", None, "no_registrant_match"),
        (None, None, "no_registrant_match"),
    ],
)
def test_resolver_matrix(registry, name, expected_ticker, expected_reason):
    ticker, _title, reason = glo.resolve_counterparty(name, registry)
    assert ticker == expected_ticker
    assert reason == expected_reason


def test_resolver_rejects_self_reference(registry):
    assert glo.resolve_counterparty("NVIDIA CORP", registry, "NVDA")[2] == "self_reference"
    assert glo.resolve_counterparty("NVIDIA CORP", registry, "AVGO")[0] == "NVDA"


def test_every_rejection_reason_is_in_the_declared_taxonomy(world: Path):
    membership = glo.load_membership(world)
    universe = {t for v in membership.values() for t in v}
    candidates, _ = glo.candidate_edges(glo.load_events(world), universe, AS_OF)
    buckets, _ = glo.load_registry(world)
    edges = glo.resolve_edges(candidates, buckets)
    reasons = {e["reject_reason"] for e in edges if not e["admitted"]}
    assert reasons <= glo.REJECTION_REASONS
    assert reasons == {"ambiguous_tie", "no_registrant_match", "self_reference"}
    # No candidate is ever silently dropped: admitted xor rejected, always.
    for edge in edges:
        assert edge["admitted"] is (edge["reject_reason"] is None)


def test_resolver_imports_the_govrev_helpers_rather_than_forking_them():
    from engine.government_revenue import issuer_graph_expansion as igx
    assert glo.normalize_legal_name is igx.normalize_legal_name
    assert glo.strip_legal_suffix is igx.strip_legal_suffix
    assert glo.name_match_tier is igx.name_match_tier


# --------------------------------------------------------------------------
# Subtype rules
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "items", "expected"),
    [
        ("Supply Agreement with Acme", "1.01", "supply_agreement"),
        ("Master Purchase Agreement", "1.01", "purchase_agreement"),
        ("Procurement Agreement", "1.01", "purchase_agreement"),
        ("Offtake Agreement", "1.01", "supply_agreement"),
        ("Collaboration Agreement", "1.01", "collaboration"),
        ("Joint Development Agreement", "1.01", "collaboration"),
        ("Strategic Alliance", "1.01", "collaboration"),
        ("License Agreement", "1.01", "license"),
        ("Sublicense terms", "1.01", "license"),
        ("Credit Agreement and Indenture", "1.01,2.03", "financing"),
        ("Term Loan facility", "2.03", "financing"),
        ("Agreement and Plan of Merger", "1.01", "merger_related"),
        ("Share Purchase Agreement", "1.01", "merger_related"),   # order is load-bearing
        ("Supply and purchase of wafers", "1.01", "supply_agreement"),
        ("", "2.03", "financing"),                                # item-code fallback
        ("", "1.01,2.03", "disclosed_agreement"),
        ("", "1.01", "disclosed_agreement"),
        ("Something entirely unremarkable", "1.01", "disclosed_agreement"),
    ],
)
def test_relationship_subtype_rules(text, items, expected):
    assert glo.relationship_subtype({"agreement_title": text, "items": items}) == expected


def test_subtype_vocabulary_is_closed(world: Path, tmp_path: Path):
    result = glo.compute(as_of=AS_OF, data_root=world, site_root=tmp_path / "site", pulse={})
    seen = {
        link["relationship"]
        for obj in result.values()
        for outsider in obj["outsiders"]
        for link in outsider["linked_members"]
    }
    assert seen and seen <= set(glo.RELATIONSHIPS)


# --------------------------------------------------------------------------
# Edge admission + window + cap
# --------------------------------------------------------------------------


def test_edge_admission_and_window(world: Path, tmp_path: Path):
    result = glo.compute(as_of=AS_OF, data_root=world, site_root=tmp_path / "site", pulse={})
    infra = result["ai_infra"]
    tickers = {o["ticker"] for o in infra["outsiders"]}
    assert "TSM" in tickers          # two admitted edges
    assert "WOLF" in tickers         # one admitted edge, item 2.03
    assert "AVGO" not in tickers     # a member of this basket is never an outsider
    assert "NVDA" not in tickers     # self-reference
    assert "DARK" not in tickers     # aged out of the 24-month window
    tsm = next(o for o in infra["outsiders"] if o["ticker"] == "TSM")
    assert tsm["edge_n"] == 2 and tsm["last_filed_at"] == "2026-07-01"
    assert {link["member"] for link in tsm["linked_members"]} == {"NVDA"}
    wolf = next(o for o in infra["outsiders"] if o["ticker"] == "WOLF")
    assert wolf["linked_members"][0]["relationship"] == "financing"
    assert wolf["linked_members"][0]["item"] == "2.03"
    # Ordering: more edges first.
    assert infra["outsiders"][0]["ticker"] == "TSM"


def test_window_aging_drops_an_edge_one_day_past_the_boundary(world: Path, tmp_path: Path):
    """The same filing is admitted at the boundary and gone one day later."""
    rows = [_event("NVDA", "2024-08-08", "1.01", "acc-w", "Wolfspeed, Inc.")]
    _write_events(world, rows)
    inside = glo.compute(as_of=date(2026, 8, 7), data_root=world,
                         site_root=tmp_path / "s1", pulse={})
    outside = glo.compute(as_of=date(2026, 8, 9), data_root=world,
                          site_root=tmp_path / "s2", pulse={})
    assert [o["ticker"] for o in inside["ai_infra"]["outsiders"]] == ["WOLF"]
    assert outside["ai_infra"]["outsiders"] == []


def test_a_filing_dated_after_as_of_is_not_admitted(world: Path, tmp_path: Path):
    rows = [_event("NVDA", "2026-09-01", "1.01", "acc-f", "Wolfspeed, Inc.")]
    _write_events(world, rows)
    result = glo.compute(as_of=AS_OF, data_root=world, site_root=tmp_path / "site", pulse={})
    assert result["ai_infra"]["outsiders"] == []


def test_cap_is_disclosed_never_silent(world: Path, tmp_path: Path):
    """13 distinct outsiders -> 12 published plus an explicit warning."""
    extra = [
        {"ticker": f"OUT{i:02d}", "cik": 900000 + i, "title": f"Outsider Number {i:02d} Holdings"}
        for i in range(13)
    ]
    directory = world / "symbol_directory" / "cik_map"
    pd.DataFrame(REGISTRY_ROWS + extra).to_parquet(directory / "2026-08-06.parquet", index=False)
    rows = [
        _event("NVDA", f"2026-0{1 + i % 7}-0{1 + i % 9}", "1.01", f"cap-{i}",
               f"Outsider Number {i:02d} Holdings")
        for i in range(13)
    ]
    _write_events(world, rows)

    result = glo.compute(as_of=AS_OF, data_root=world, site_root=tmp_path / "site", pulse={})
    infra = result["ai_infra"]
    glo.validate_artifact(infra)
    assert infra["n_outsiders"] == glo.MAX_OUTSIDERS_PER_BASKET == 12
    warning = [w for w in infra["coverage_warnings"] if w.startswith("outsider_cap_applied")]
    assert len(warning) == 1
    assert "13 linked outsiders found" in warning[0]
    assert "12 published" in warning[0]


def test_no_cap_warning_when_the_cap_does_not_bind(world: Path, tmp_path: Path):
    result = glo.compute(as_of=AS_OF, data_root=world, site_root=tmp_path / "site", pulse={})
    for obj in result.values():
        assert not [w for w in obj["coverage_warnings"] if w.startswith("outsider_cap_applied")]


def test_reverse_direction_edge_counts(world: Path, tmp_path: Path):
    """An outsider's own 8-K naming a member creates the same edge."""
    rows = [_event("ENPH", "2026-07-01", "1.01", "rev-1", "NVIDIA CORP")]
    _write_events(world, rows)
    result = glo.compute(as_of=AS_OF, data_root=world, site_root=tmp_path / "site", pulse={})
    # ENPH files, naming NVDA: NVDA is an outsider TO ENPH's own basket.
    assert [o["ticker"] for o in result["solar"]["outsiders"]] == ["NVDA"]
    assert result["ai_infra"]["outsiders"] == []


# --------------------------------------------------------------------------
# States
# --------------------------------------------------------------------------


def test_activity_constants_match_the_masterplan_and_group_pulse():
    """§4.2: |SPY-adj return| z >= 1.5 vs own 63d, OR volume >= 1.5x own 63d median.

    When GR0's group_pulse lands, its constants become the source of truth and
    this asserts the two definitions are the same number, not merely similar.
    """
    assert glo.ACTIVITY_Z == 1.5
    assert glo.ACTIVITY_VOLUME_RATIO == 1.5
    assert glo.ACTIVITY_LOOKBACK_D == 63
    resolved = glo._activity_constants()
    assert resolved == (1.5, 1.5, 63)


def test_activity_constants_use_group_pulse_when_present(monkeypatch):
    """The independently reviewed GR0 module becomes canonical when it lands."""

    group_pulse = ModuleType("engine.group_pulse")
    group_pulse.ACTIVITY_Z = 2.0
    group_pulse.ACTIVITY_VOLUME_RATIO = 3.0
    group_pulse.ACTIVITY_LOOKBACK_D = 42
    monkeypatch.setitem(sys.modules, "engine.group_pulse", group_pulse)
    assert glo._activity_constants() == (2.0, 3.0, 42)


def test_activity_constants_do_not_hide_a_present_modules_broken_dependency(monkeypatch):
    """Only absent GR0 is optional; a defect inside a present GR0 stays loud."""

    def _broken_import(_name: str):
        raise ModuleNotFoundError("No module named 'inner_dependency'", name="inner_dependency")

    monkeypatch.setattr(glo, "import_module", _broken_import)
    with pytest.raises(ModuleNotFoundError, match="inner_dependency"):
        glo._activity_constants()


@pytest.mark.parametrize(
    ("jump", "volume_spike", "sign", "expected"),
    [
        (0.25, 1.0, "up", "confirming"),          # big up move, basket up
        (-0.25, 1.0, "up", "active_divergent"),   # big down move, basket up
        (-0.25, 1.0, "down", "confirming"),
        (0.25, 1.0, "down", "active_divergent"),
        (0.0, 1.0, "up", "quiet"),                # readable, not active
        # No return-leg jump: only the volume leg can make these active at all.
        (0.0, 4.0, "up", "confirming"),           # drift is mildly positive
        (0.0, 4.0, "down", "active_divergent"),
        (0.25, 1.0, "mixed", "active_divergent"), # a mixed basket has no direction
        (0.0, 1.0, "mixed", "quiet"),
    ],
)
def test_state_machine(world: Path, tmp_path: Path, jump, volume_spike, sign, expected):
    _write_events(world, [_event("NVDA", "2026-07-01", "1.01", "st-1", "Wolfspeed, Inc.")])
    _bars(world, "WOLF", jump=jump, volume_spike=volume_spike)
    result = glo.compute(
        as_of=AS_OF, data_root=world, site_root=tmp_path / "site",
        pulse={"ai_infra": {"direction": {"sign": sign}}},
    )
    outsider = result["ai_infra"]["outsiders"][0]
    assert outsider["state"] == expected
    assert outsider["move_spy_adj"] is not None
    assert result["ai_infra"]["n_with_tape"] == 1
    assert result["ai_infra"]["n_confirming"] == (1 if expected == "confirming" else 0)


def test_outsider_with_no_tape_stays_listed_as_unavailable(world: Path, tmp_path: Path):
    _write_events(world, [_event("NVDA", "2026-07-01", "1.01", "nt-1", "Wolfspeed, Inc.")])
    result = glo.compute(
        as_of=AS_OF, data_root=world, site_root=tmp_path / "site",
        pulse={"ai_infra": {"direction": {"sign": "up"}}},
    )
    infra = result["ai_infra"]
    assert [o["ticker"] for o in infra["outsiders"]] == ["WOLF"]
    assert infra["outsiders"][0]["state"] == "unavailable"
    assert infra["outsiders"][0]["move_spy_adj"] is None
    assert infra["outsiders"][0]["active"] is None
    assert infra["n_with_tape"] == 0
    assert [w for w in infra["coverage_warnings"] if w.startswith("tape_unavailable")]


def test_stale_tape_reads_unavailable_not_quiet(world: Path, tmp_path: Path):
    """A halted or delisted name must not publish an old session's move as today's."""
    _write_events(world, [_event("NVDA", "2026-07-01", "1.01", "sl-1", "Wolfspeed, Inc.")])
    _bars(world, "WOLF", last=date(2026, 6, 1))
    result = glo.compute(
        as_of=AS_OF, data_root=world, site_root=tmp_path / "site",
        pulse={"ai_infra": {"direction": {"sign": "up"}}},
    )
    outsider = result["ai_infra"]["outsiders"][0]
    assert outsider["state"] == "unavailable"
    assert outsider["move_spy_adj"] is None


def test_short_history_cannot_be_called_active(world: Path, tmp_path: Path):
    _write_events(world, [_event("NVDA", "2026-07-01", "1.01", "sh-1", "Wolfspeed, Inc.")])
    _bars(world, "WOLF", n=10, jump=0.5)
    result = glo.compute(
        as_of=AS_OF, data_root=world, site_root=tmp_path / "site",
        pulse={"ai_infra": {"direction": {"sign": "up"}}},
    )
    outsider = result["ai_infra"]["outsiders"][0]
    assert outsider["active"] is None
    assert outsider["state"] == "unavailable"


def test_missing_pulse_degrades_without_crashing(world: Path, tmp_path: Path):
    _write_events(world, [_event("NVDA", "2026-07-01", "1.01", "mp-1", "Wolfspeed, Inc.")])
    _bars(world, "WOLF", jump=0.25)
    site = tmp_path / "site"          # no basketdata/pulse.json exists here
    result = glo.compute(as_of=AS_OF, data_root=world, site_root=site)
    infra = result["ai_infra"]
    glo.validate_artifact(infra)
    assert [o["state"] for o in infra["outsiders"]] == ["unavailable"]
    assert infra["n_confirming"] == 0
    assert [w for w in infra["coverage_warnings"] if w.startswith("basket_direction_unavailable")]
    # The tape figures that ARE readable are still printed — they are facts.
    assert infra["outsiders"][0]["move_spy_adj"] is not None
    assert infra["n_with_tape"] == 1


def test_pulse_present_but_basket_absent_degrades_per_basket(world: Path, tmp_path: Path):
    _write_events(world, [_event("NVDA", "2026-07-01", "1.01", "pb-1", "Wolfspeed, Inc.")])
    _bars(world, "WOLF", jump=0.25)
    result = glo.compute(
        as_of=AS_OF, data_root=world, site_root=tmp_path / "site",
        pulse={"some_other_basket": {"direction": {"sign": "up"}}},
    )
    assert result["ai_infra"]["outsiders"][0]["state"] == "unavailable"


def test_pulse_json_is_read_from_the_site_root(world: Path, tmp_path: Path):
    _write_events(world, [_event("NVDA", "2026-07-01", "1.01", "pj-1", "Wolfspeed, Inc.")])
    _bars(world, "WOLF", jump=0.25)
    site = tmp_path / "site"
    (site / "basketdata").mkdir(parents=True)
    (site / "basketdata" / "pulse.json").write_text(
        json.dumps({"ai_infra": {"direction": {"sign": "up"}}}), encoding="utf-8",
    )
    result = glo.compute(as_of=AS_OF, data_root=world, site_root=site)
    assert result["ai_infra"]["outsiders"][0]["state"] == "confirming"


# --------------------------------------------------------------------------
# as_of — one session for the whole GR plane (audit 2026-08-10, F-7 tail)
# --------------------------------------------------------------------------


def _pulse_at(site: Path, session: str) -> None:
    (site / "basketdata").mkdir(parents=True, exist_ok=True)
    (site / "basketdata" / "pulse.json").write_text(
        json.dumps({"ai_infra": {"as_of": session, "direction": {"sign": "up"}}}),
        encoding="utf-8",
    )


def test_as_of_follows_the_pulse_data_session_not_the_run_clock(world: Path, tmp_path: Path):
    """This plane stamped the WALL-CLOCK run date while pulse / episodes / earnings_pulse
    stamp the last DATA SESSION, so the four GR artifacts disagreed about what "today" was
    (audit observed 08-10 here against 08-07 there).  With no caller-supplied `as_of` the
    stamp now comes from the sibling artifact this plane is joined to."""
    _write_events(world, [_event("NVDA", "2026-07-01", "1.01", "ao-1", "Wolfspeed, Inc.")])
    site = tmp_path / "site"
    _pulse_at(site, "2026-08-07")
    result = glo.compute(data_root=world, site_root=site)
    assert {obj["as_of"] for obj in result.values()} == {"2026-08-07"}


def test_an_explicit_as_of_still_outranks_the_pulse_session(world: Path, tmp_path: Path):
    """Backfills and the smoke run pass their own session; the pulse stamp is the DEFAULT,
    never an override."""
    site = tmp_path / "site"
    _pulse_at(site, "2026-08-07")
    result = glo.compute(as_of=date(2026, 8, 5), data_root=world, site_root=site)
    assert {obj["as_of"] for obj in result.values()} == {"2026-08-05"}


def test_a_pulse_without_a_session_stamp_discloses_the_clock_fallback(
        world: Path, tmp_path: Path, capsys):
    """No pulse, no session — the run date is still usable, but it is never SILENT, because
    a silent fallback is exactly how the two planes drifted apart in the first place."""
    result = glo.compute(data_root=world, site_root=tmp_path / "site", pulse={})
    lines = [ln for ln in capsys.readouterr().out.splitlines()
             if "linked-outsiders-as-of" in ln]
    assert lines, "the fallback to the run clock shipped silently"
    # GitHub only parses an annotation that STARTS the line.
    assert lines[0].startswith("::warning title="), lines[0]
    stamps = {obj["as_of"] for obj in result.values()}
    assert len(stamps) == 1
    date.fromisoformat(stamps.pop())   # well formed; the clock value itself is not pinned


def test_run_takes_its_window_and_its_stamp_from_the_same_session(
        world: Path, tmp_path: Path, monkeypatch):
    """The edge WINDOW and the artifact STAMP are resolved once, together — a filing that
    lands after the last data session is in-window against the clock and out-of-window
    against the tape, and the tape is what the outsider move is read on."""
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    site = tmp_path / "site"
    _pulse_at(site, "2026-08-07")
    _write_events(world, [_event("NVDA", "2026-08-09", "1.01", "rw-1", "Wolfspeed, Inc.")])
    glo.run(data_root=world, site_root=site)
    written = json.loads(
        (site / "basketdata" / "linked_outsiders.json").read_text(encoding="utf-8"))
    assert written["ai_infra"]["as_of"] == "2026-08-07"
    assert written["ai_infra"]["n_outsiders"] == 0, \
        "a filing past the data session was admitted — the window did not move with the stamp"


# --------------------------------------------------------------------------
# Missing / broken inputs never crash the nightly
# --------------------------------------------------------------------------


@pytest.mark.parametrize("victim", [
    "edgar/material_8k_events.parquet",
    "symbol_directory/cik_map/2026-08-06.parquet",
])
def test_missing_input_degrades_with_a_warning(world: Path, tmp_path: Path, victim):
    (world / victim).unlink()
    result = glo.compute(as_of=AS_OF, data_root=world, site_root=tmp_path / "site", pulse={})
    for obj in result.values():
        glo.validate_artifact(obj)
        assert obj["outsiders"] == []
        assert obj["coverage_warnings"]


def test_zero_counterparty_source_is_disclosed(world: Path, tmp_path: Path):
    rows = [_event("NVDA", "2026-07-01", "1.01", "z-1", None)]
    _write_events(world, rows)
    result = glo.compute(as_of=AS_OF, data_root=world, site_root=tmp_path / "site", pulse={})
    warning = [w for w in result["ai_infra"]["coverage_warnings"]
               if w.startswith("source_counterparty_absent")]
    assert len(warning) == 1 and "0 of 1" in warning[0]


def test_candidates_that_all_reject_are_disclosed_never_a_silent_zero(world: Path, tmp_path: Path):
    """Edges exist, none resolves -> the artifact says so and names the census."""
    (world / "symbol_directory" / "cik_map" / "2026-08-06.parquet").unlink()
    result = glo.compute(as_of=AS_OF, data_root=world, site_root=tmp_path / "site", pulse={})
    infra = result["ai_infra"]
    assert infra["outsiders"] == []
    warning = [w for w in infra["coverage_warnings"] if w.startswith("no_edge_admitted")]
    assert len(warning) == 1
    assert "candidate counterparty names" in warning[0]
    assert "no_registrant_match=" in warning[0]


def test_missing_membership_yields_an_empty_mapping(tmp_path: Path):
    assert glo.load_membership(tmp_path) == {}


def test_empty_events_table_is_not_an_error(world: Path, tmp_path: Path):
    _write_events(world, [])
    result = glo.compute(as_of=AS_OF, data_root=world, site_root=tmp_path / "site", pulse={})
    assert all(obj["outsiders"] == [] for obj in result.values())


# --------------------------------------------------------------------------
# Site artifact
# --------------------------------------------------------------------------


def test_write_site_artifact_round_trips(world: Path, tmp_path: Path):
    site = tmp_path / "site"
    result = glo.compute(as_of=AS_OF, data_root=world, site_root=site, pulse={})
    path = glo.write_site_artifact(result, site)
    assert path == site / "basketdata" / "linked_outsiders.json"
    reloaded = json.loads(path.read_text(encoding="utf-8"))
    assert set(reloaded) == set(result)
    for obj in reloaded.values():
        glo.validate_artifact(obj)


# --------------------------------------------------------------------------
# Edge ledger — nightly-gated, append-only, immutable
# --------------------------------------------------------------------------


def _edges(world: Path):
    membership = glo.load_membership(world)
    universe = {t for v in membership.values() for t in v}
    candidates, _ = glo.candidate_edges(glo.load_events(world), universe, AS_OF)
    buckets, _ = glo.load_registry(world)
    return glo.resolve_edges(candidates, buckets)


def test_ledger_is_gated_off_the_nightly_lane(world: Path, monkeypatch):
    monkeypatch.delenv("COLLECT_LANE", raising=False)
    monkeypatch.delenv("US_LANE", raising=False)
    assert glo.advance_edge_ledger(_edges(world), world) == 0
    assert not glo.ledger_path(world).exists()


def test_ledger_records_admissions_and_rejections(world: Path, monkeypatch):
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    edges = _edges(world)
    appended = glo.advance_edge_ledger(edges, world, advanced_at="2026-08-07T00:00:00+00:00")
    assert appended == len(edges) > 0
    frame = pd.read_parquet(glo.ledger_path(world))
    assert list(frame.columns) == list(glo.LEDGER_COLUMNS)
    assert frame["admitted"].sum() > 0
    rejected = frame[~frame["admitted"].astype(bool)]
    assert len(rejected) > 0
    assert rejected["reject_reason"].notna().all()
    assert set(rejected["reject_reason"]) <= glo.REJECTION_REASONS
    assert rejected["outsider_ticker"].isna().all()
    admitted = frame[frame["admitted"].astype(bool)]
    assert admitted["reject_reason"].isna().all()
    assert admitted["outsider_ticker"].notna().all()


def test_double_advance_is_byte_identical_and_adds_no_duplicate(world: Path, monkeypatch):
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    edges = _edges(world)
    glo.advance_edge_ledger(edges, world, advanced_at="2026-08-07T00:00:00+00:00")
    path = glo.ledger_path(world)
    first_bytes = path.read_bytes()
    first = pd.read_parquet(path)

    # A later run with a LATER clock over identical inputs must append nothing.
    assert glo.advance_edge_ledger(edges, world, advanced_at="2026-08-08T00:00:00+00:00") == 0
    assert path.read_bytes() == first_bytes
    second = pd.read_parquet(path)
    pd.testing.assert_frame_equal(first, second)
    assert not second.duplicated(subset=list(glo.LEDGER_KEY)).any()
    assert (second["advanced_at"] == "2026-08-07T00:00:00+00:00").all()


def test_later_run_appends_only_the_new_accession(world: Path, monkeypatch):
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    edges = _edges(world)
    glo.advance_edge_ledger(edges, world, advanced_at="2026-08-07T00:00:00+00:00")
    prior = pd.read_parquet(glo.ledger_path(world))

    _write_events(world, DEFAULT_EVENTS + [
        _event("AVGO", "2026-07-30", "1.01", "acc-new", "Taiwan Semiconductor Manufacturing"),
    ])
    appended = glo.advance_edge_ledger(_edges(world), world,
                                       advanced_at="2026-08-08T00:00:00+00:00")
    assert appended == 1
    after = pd.read_parquet(glo.ledger_path(world))
    assert len(after) == len(prior) + 1
    # Prior rows are untouched, in their original order, with their original clock.
    pd.testing.assert_frame_equal(after.iloc[: len(prior)].reset_index(drop=True), prior)
    assert after.iloc[-1]["accession"] == "acc-new"
    assert after.iloc[-1]["advanced_at"] == "2026-08-08T00:00:00+00:00"


def test_ledger_refuses_to_advance_over_an_unreadable_store(world: Path, monkeypatch, capsys):
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    path = glo.ledger_path(world)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"not a parquet file")
    assert glo.advance_edge_ledger(_edges(world), world) == 0
    assert path.read_bytes() == b"not a parquet file"
    line = capsys.readouterr().out.strip().splitlines()[0]
    # GitHub only parses an annotation that STARTS the line.
    assert line.startswith("::warning title=")


def test_run_writes_the_artifact_and_advances_once(world: Path, tmp_path: Path, monkeypatch):
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    site = tmp_path / "site"
    summary = glo.run(as_of=AS_OF, data_root=world, site_root=site)
    assert summary["baskets"] == 2
    assert summary["baskets_with_outsiders"] == 1
    assert summary["edges_appended"] > 0
    assert (site / "basketdata" / "linked_outsiders.json").exists()
    assert glo.ledger_path(world).exists()


# --------------------------------------------------------------------------
# Determinism
# --------------------------------------------------------------------------


def test_compute_is_deterministic(world: Path, tmp_path: Path):
    stamp = "2026-08-07T00:00:00+00:00"
    a = glo.compute(as_of=AS_OF, data_root=world, site_root=tmp_path / "a",
                    pulse={}, generated_at=stamp)
    b = glo.compute(as_of=AS_OF, data_root=world, site_root=tmp_path / "b",
                    pulse={}, generated_at=stamp)
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
