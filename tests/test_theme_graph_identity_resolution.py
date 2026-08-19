"""V4-D2A — the GMI -> Data OS identity resolution bridge.

Contract: ``research/prophet_v4/d2/D2A_FROZEN_CONTRACT_2026-08-18.md``. This suite runs
the §6 hostile-case table VERBATIM against the REAL committed stores
(``data/theme_graph/{nodes,edges}.parquet`` + ``data/reference/{security_master,
vendor_aliases}.parquet``) — a planted-AAPL-only fixture would be insufficient (handoff
§14): the whole point of the bridge is what it says about the real, messy graph.

Mutation tests (§8) isolate the algorithm's mechanics from the real committed table's
redundant CURRENT-CATALOG rows (``store``/``yahoo_fetch``), which are unconditionally
open and would make almost any real, vendor-covered symbol resolve regardless of the
query date — so a genuine two-clock (dated-boundary) assertion needs a fixture table
carrying ONLY the historical vendor space under test.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from engine.theme_graph import identity_resolution as ir
from engine.theme_graph import store
from lib import config as lib_config
from lib.dataos.identity import AliasRow, VendorAliasTable

ROOT = Path(__file__).resolve().parent.parent
NODES_PATH = ROOT / "data" / "theme_graph" / "nodes.parquet"
MASTER_PATH = ROOT / "data" / "reference" / "security_master.parquet"
BAKED_IDRES_PATH = ROOT / "data" / "theme_graph" / "identity_resolution.parquet"

pytestmark = pytest.mark.skipif(
    not (NODES_PATH.exists() and MASTER_PATH.exists()),
    reason="sparse checkout — data/theme_graph and data/reference are not materialized",
)


# ---------------------------------------------------------------------------
# Real committed inputs, loaded once
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def nodes() -> pd.DataFrame:
    return pd.read_parquet(NODES_PATH)


@pytest.fixture(scope="module")
def company_nodes(nodes: pd.DataFrame) -> pd.DataFrame:
    return nodes[nodes["kind"].astype(str) == "company"]


@pytest.fixture(scope="module")
def master_inputs() -> ir.MasterInputs:
    inputs = ir.load_master_inputs()
    assert inputs is not None, "the committed Data OS spine must be readable for this suite"
    return inputs


@pytest.fixture(scope="module")
def etf_symbols(nodes: pd.DataFrame) -> frozenset[str]:
    return ir._etf_symbols(nodes.to_dict("records"))


@pytest.fixture(scope="module")
def baked_idres() -> pd.DataFrame:
    """The COMMITTED, re-baked sidecar (§9 first materialization) — F4's full-population
    tests read this rather than the pure algorithm, so they pin what actually shipped."""
    assert BAKED_IDRES_PATH.exists(), (
        "data/theme_graph/identity_resolution.parquet must be committed for the "
        "full-population F4 tests")
    return pd.read_parquet(BAKED_IDRES_PATH)


def _resolve(node_id: str, master_inputs: ir.MasterInputs, etf_symbols: frozenset[str],
            asof: str = "2026-08-14") -> dict:
    return ir._resolve_node_row(
        node_id=node_id, resolution_asof=asof, inputs=master_inputs,
        etf_symbols=etf_symbols, computed_at="2026-08-18T00:00:00Z",
        engine_version=store.ENGINE_VERSION)


# ---------------------------------------------------------------------------
# §2 — row scope: 2,806 company nodes at pin, every one gets a row
# ---------------------------------------------------------------------------

def test_the_committed_graph_carries_exactly_2806_company_nodes(company_nodes):
    """The contract's own pinned count (§1/§9) — if this drifts, the graph moved under
    the frozen contract and the fixture table below needs re-pinning, not silent trust."""
    assert len(company_nodes) == 2806


def test_every_company_node_gets_a_row(nodes, company_nodes, master_inputs, etf_symbols):
    """F4: derive_rows is called with the FULL node list (etf nodes included), exactly
    as materialize.py's real build does — a company-nodes-only call would starve rule 4
    (ENTITY_TYPE_CONFLICT) of the etf:IBIT node it needs to see, silently making
    co:us:IBIT resolve instead of refuse in THIS derivation, even though the guard
    (fed the real full-list derive_rows call) would never observe that bug."""
    rows = ir.derive_rows(
        nodes.to_dict("records"), resolution_asof="2026-08-14",
        computed_at="2026-08-18T00:00:00Z", engine_version=store.ENGINE_VERSION)
    assert len(rows) == len(company_nodes) == 2806
    assert {r["node_id"] for r in rows} == set(company_nodes["node_id"].astype(str))
    by_id = {r["node_id"]: r for r in rows}
    assert by_id["co:us:IBIT"]["resolution_state"] == "ENTITY_TYPE_CONFLICT", (
        "rule 4 must be LIVE in this derivation — the etf:IBIT node is in the full "
        "list passed to derive_rows")
    for row in rows:
        assert row["resolution_state"] in ir.RESOLUTION_STATES
        assert row["join_method"] in ir.JOIN_METHODS
        assert row["source_receipts"]
        if row["resolution_state"] == "RESOLVED":
            assert row["issuer_id"] and row["security_id"] and row["listing_key"]
            assert row["refusal_reason"] is None
        else:
            assert row["issuer_id"] is None and row["security_id"] is None \
                and row["listing_key"] is None
            assert row["refusal_reason"], row


# ---------------------------------------------------------------------------
# §6 — the binding hostile-case fixture table, verbatim
# ---------------------------------------------------------------------------

class TestSection6HostileCases:
    def test_goog_and_googl_resolve_distinctly(self, master_inputs, etf_symbols):
        goog = _resolve("co:us:GOOG", master_inputs, etf_symbols)
        googl = _resolve("co:us:GOOGL", master_inputs, etf_symbols)
        assert goog["resolution_state"] == googl["resolution_state"] == "RESOLVED"
        assert goog["security_id"] == "SEC:US-XNAS-GOOG"
        assert googl["security_id"] == "SEC:US-XNAS-GOOGL"
        assert goog["security_id"] != googl["security_id"]
        # No cross-share-class issuer axis — the master's own limitation, disclosed
        # rather than manufactured. config/share_class_equiv.yml is NEVER consulted.
        assert goog["issuer_id"] != googl["issuer_id"]

    def test_share_class_equiv_is_never_consulted(self):
        """Structural proof: the resolver's only inputs are the master + alias table +
        receipt — ``config/share_class_equiv.yml`` is never even referenced by this
        module's source, so it structurally cannot influence a resolution."""
        src = Path(ir.__file__).read_text(encoding="utf-8")
        assert "share_class_equiv" not in src

    def test_brk_b_resolves_via_alias(self, master_inputs, etf_symbols):
        row = _resolve("co:us:BRK-B", master_inputs, etf_symbols)
        assert row["resolution_state"] == "RESOLVED"
        assert row["join_method"] == "vendor_alias"
        assert row["security_id"] == "SEC:US-XNYS-BRK.B"

    def test_b_is_deferred(self, master_inputs, etf_symbols):
        row = _resolve("co:us:B", master_inputs, etf_symbols)
        assert row["resolution_state"] == "DEFERRED_IDENTITY_EXCEPTION"
        assert "deferred_no_mint" in row["refusal_reason"]
        assert row["security_id"] is None

    def test_gold_is_deferred(self, master_inputs, etf_symbols):
        row = _resolve("co:us:GOLD", master_inputs, etf_symbols)
        assert row["resolution_state"] == "DEFERRED_IDENTITY_EXCEPTION"
        assert "disclosed_existing_alias" in row["refusal_reason"]
        assert row["security_id"] is None

    def test_mmc_resolves(self, master_inputs, etf_symbols):
        row = _resolve("co:us:MMC", master_inputs, etf_symbols)
        assert row["resolution_state"] == "RESOLVED"
        assert row["security_id"] == "SEC:US-XNYS-MMC"

    def test_sats_and_echo_resolve_to_the_same_security(self, master_inputs, etf_symbols):
        sats = _resolve("co:us:SATS", master_inputs, etf_symbols)
        echo = _resolve("co:us:ECHO", master_inputs, etf_symbols)
        assert sats["resolution_state"] == echo["resolution_state"] == "RESOLVED"
        assert sats["security_id"] == echo["security_id"] == "SEC:US-XNAS-SATS"
        # Two topology nodes, one security — the machine-visible duplicate the bridge
        # exists to expose.
        assert "co:us:SATS" != "co:us:ECHO"

    def test_fi_and_fisv_resolve_to_the_same_security(self, master_inputs, etf_symbols):
        fi = _resolve("co:us:FI", master_inputs, etf_symbols)
        fisv = _resolve("co:us:FISV", master_inputs, etf_symbols)
        assert fi["resolution_state"] == fisv["resolution_state"] == "RESOLVED"
        assert fi["security_id"] == fisv["security_id"] == "SEC:US-XNAS-FISV"

    def test_ibit_is_an_entity_type_conflict(self, master_inputs, etf_symbols):
        row = _resolve("co:us:IBIT", master_inputs, etf_symbols)
        assert row["resolution_state"] == "ENTITY_TYPE_CONFLICT"
        assert row["security_id"] is None
        receipts = json.loads(row["source_receipts"])
        assert receipts["conflicting_etf_node"] == "etf:IBIT"
        assert receipts["master_row_would_otherwise_resolve_to"] == "SEC:US-XNAS-IBIT"

    def test_ctra_resolves_despite_being_delisted(self, master_inputs, etf_symbols):
        """The master models identity, not lifecycle — CTRA (delisted-receipted) still
        RESOLVES; lifecycle is out of D2A scope."""
        row = _resolve("co:us:CTRA", master_inputs, etf_symbols)
        assert row["resolution_state"] == "RESOLVED"
        assert row["security_id"] == "SEC:US-XNYS-CTRA"

    @pytest.mark.parametrize("symbol", [
        "ANGPY", "BLD", "CBOE", "EA", "GATO", "IMPUY", "MAG", "RHHBY",
    ])
    def test_the_eight_not_in_master_names(self, symbol, master_inputs, etf_symbols):
        row = _resolve(f"co:us:{symbol}", master_inputs, etf_symbols)
        assert row["resolution_state"] == "NOT_IN_MASTER", row
        assert row["security_id"] is None
        assert row["refusal_reason"]

    def test_every_cn_hk_ca_node_is_not_in_master(self, baked_idres):
        """F4: FULL-POPULATION over the BAKED parquet, not a 25-per-market sample — the
        master is 100% US today, so every cn/hk/ca row must be NOT_IN_MASTER, with no
        sampled subset left unchecked."""
        for market in ("cn", "hk", "ca"):
            rows = baked_idres[baked_idres["market_scope"] == market]
            assert not rows.empty, (
                f"no {market} company rows in the baked sidecar — fixture stale")
            bad = rows[rows["resolution_state"] != "NOT_IN_MASTER"]
            assert bad.empty, (market, bad[["node_id", "resolution_state"]].to_dict("records"))

    def test_every_intl_node_is_unsupported_market(self, baked_idres):
        """F4: full population, not a sample."""
        rows = baked_idres[baked_idres["market_scope"] == "intl"]
        assert not rows.empty, "no intl company rows in the baked sidecar — fixture stale"
        bad = rows[rows["resolution_state"] != "UNSUPPORTED_MARKET"]
        assert bad.empty, bad[["node_id", "resolution_state"]].to_dict("records")
        assert rows["security_id"].isna().all()

    def test_every_us_node_is_in_the_remaining_states(self, baked_idres):
        """F4: full population — every us-scope row lands in a state OTHER than
        UNSUPPORTED_MARKET (that state exists solely for market_scope=intl, rule 2)."""
        rows = baked_idres[baked_idres["market_scope"] == "us"]
        assert not rows.empty, "no us company rows in the baked sidecar — fixture stale"
        bad = rows[rows["resolution_state"] == "UNSUPPORTED_MARKET"]
        assert bad.empty, bad[["node_id", "resolution_state"]].to_dict("records")
        assert set(rows["resolution_state"]) <= set(ir.RESOLUTION_STATES)


# ---------------------------------------------------------------------------
# §8 — mutation tests
# ---------------------------------------------------------------------------

class TestMutations:
    def test_a_sec_shaped_node_id_fails_validation(self, master_inputs, etf_symbols):
        """Rewriting a real graph id (co:us:GOOGL) into a Data OS master id shape fails
        rule 1 (INVALID_SOURCE_ID) — a bridge row's node_id is ALWAYS the GMI id, never
        a Data OS one, and the algorithm refuses to treat a master-shaped string as a
        graph node id."""
        row = _resolve("SEC:US-XNAS-GOOGL", master_inputs, etf_symbols)
        assert row["resolution_state"] == "INVALID_SOURCE_ID"
        assert row["issuer_id"] is None and row["security_id"] is None
        assert row["join_method"] == "refused"

    def test_a_sec_shaped_node_id_also_breaches_the_graphs_own_id_grammar_guard(
        self, tmp_path,
    ):
        """The SAME mutation, one layer up: if it ever reached nodes.parquet, the
        EXISTING company-id-grammar check in check_theme_graph_contracts.py (unrelated
        to this bridge) catches it structurally too — two independent guards, same
        defect, neither trusting the other."""
        from scripts import check_theme_graph_contracts as guard

        stamp = "2024-01-02T00:00:00Z"
        node_rows = [{
            "node_id": "SEC:US-XNAS-GOOGL", "kind": "company", "name_en": None,
            "name_zh": None, "market_scope": "us", "tier": None, "status": "canonical",
            "merged_into": None, "birth_date": None, "retire_date": None,
            "identity_epoch": 1, "external_ids": "{}", "provenance": "fixture",
            "computed_at": stamp, "engine_version": store.ENGINE_VERSION,
            "source_meta": None,
        }]
        d = tmp_path / "store"
        d.mkdir()
        pd.DataFrame(node_rows).reindex(columns=list(store.NODE_COLUMNS)).to_parquet(
            d / "nodes.parquet", index=False)
        pd.DataFrame([]).reindex(columns=list(store.EDGE_COLUMNS)).to_parquet(
            d / "edges.parquet", index=False)
        pd.DataFrame([]).reindex(columns=list(store.EVIDENCE_COLUMNS)).to_parquet(
            d / "evidence.parquet", index=False)
        breaks_file = tmp_path / "no_breaks.yml"
        breaks_file.write_text("breaks: []\n", encoding="utf-8")

        breaches, _notices = guard.audit(d, breaks_file)
        assert any("outside the permanent-identity grammar" in b for b in breaches), breaches

    def test_a_deleted_resolution_row_fails_the_guard(self, tmp_path):
        """A company node with no CURRENT identity_resolution row, while the sidecar
        exists, is a breach (Sol attack 17) — the guard's own selftest pins this; this
        mirrors it at the pytest layer so the property is visible from this suite too."""
        from scripts import check_theme_graph_contracts as guard

        stamp = "2024-01-02T00:00:00Z"
        node_rows = [{
            "node_id": "co:us:AAA", "kind": "company", "name_en": None, "name_zh": None,
            "market_scope": "us", "tier": None, "status": "canonical",
            "merged_into": None, "birth_date": None, "retire_date": None,
            "identity_epoch": 1, "external_ids": "{}", "provenance": "fixture",
            "computed_at": stamp, "engine_version": store.ENGINE_VERSION,
            "source_meta": None,
        }]
        edge_rows: list[dict] = []
        evidence_rows: list[dict] = []
        d = tmp_path / "store"
        d.mkdir()
        pd.DataFrame(node_rows).reindex(columns=list(store.NODE_COLUMNS)).to_parquet(
            d / "nodes.parquet", index=False)
        pd.DataFrame(edge_rows).reindex(columns=list(store.EDGE_COLUMNS)).to_parquet(
            d / "edges.parquet", index=False)
        pd.DataFrame(evidence_rows).reindex(columns=list(store.EVIDENCE_COLUMNS)).to_parquet(
            d / "evidence.parquet", index=False)
        pd.DataFrame([]).reindex(columns=list(store.IDENTITY_RESOLUTION_COLUMNS)).to_parquet(
            d / "identity_resolution.parquet", index=False)
        breaks_file = tmp_path / "no_breaks.yml"
        breaks_file.write_text("breaks: []\n", encoding="utf-8")

        breaches, notices = guard.audit(d, breaks_file)
        assert any("no current identity_resolution" in b for b in breaches), breaches

    def test_no_ticker_equality_fallback(self, master_inputs, etf_symbols):
        """A symbol structurally cannot become RESOLVED by string equality alone — only
        through the master's inception_code or the alias table. Proven by constructing
        a symbol that equals no master inception_code and no alias vendor_symbol: it
        MUST land NOT_IN_MASTER, never RESOLVED-by-coincidence."""
        bogus = "ZZZNOSUCHTICKERXYZ"
        assert bogus not in master_inputs.master_by_code
        assert not any(master_inputs.alias_table.resolve(v, bogus, on=date(2026, 8, 14))
                       for v in master_inputs.vendors)
        row = _resolve(f"co:us:{bogus}", master_inputs, etf_symbols)
        assert row["resolution_state"] == "NOT_IN_MASTER"
        assert row["security_id"] is None

    def test_mmc_historical_clock_the_post_rename_name_alone_cannot_resolve_pre_boundary(
        self,
    ):
        """The two-clock law (§4), isolated from the real committed table's redundant
        CURRENT-CATALOG rows (store/yahoo_fetch), which are unconditionally open and
        would make MRSH resolve at any date if they were present — that is correct for
        THOSE vendor spaces (§4's own two-clock note: 'what string to use TODAY for a
        bar of ANY date') but would mask the property this test pins: a HISTORICAL
        vendor space's dated pair must not let the post-rename spelling answer on the
        wrong side of the boundary.
        """
        table = VendorAliasTable([
            AliasRow("yahoo", "MMC", "SEC:US-XNYS-MMC", None, date(2026, 1, 14)),
            AliasRow("yahoo", "MRSH", "SEC:US-XNYS-MMC", date(2026, 1, 14), None),
        ])
        inputs = ir.MasterInputs(
            master_by_code={}, master_by_security={
                "SEC:US-XNYS-MMC": {"security_id": "SEC:US-XNYS-MMC",
                                    "issuer_id": "ISS:US-XNYS-MMC",
                                    "listing_key": "US-XNYS-MMC"}},
            alias_table=table, vendors=frozenset({"yahoo"}),
            identity_exceptions={}, generated_at=None,
            symbol_directory_snapshot=None, code_version=None,
        )
        pre = ir._resolve_node_row(
            node_id="co:us:MRSH", resolution_asof="2026-01-01", inputs=inputs,
            etf_symbols=frozenset(), computed_at="x", engine_version="v")
        assert pre["resolution_state"] == "NOT_IN_MASTER", (
            "MRSH, the POST-rename name, must not resolve at a PRE-rename asof through "
            "the historical vendor space alone")

        post = ir._resolve_node_row(
            node_id="co:us:MRSH", resolution_asof="2026-02-01", inputs=inputs,
            etf_symbols=frozenset(), computed_at="x", engine_version="v")
        assert post["resolution_state"] == "RESOLVED"
        assert post["security_id"] == "SEC:US-XNYS-MMC"

        # And the OLD spelling, symmetrically, cannot resolve on the new side.
        old_post = ir._resolve_node_row(
            node_id="co:us:MMC", resolution_asof="2026-02-01", inputs=inputs,
            etf_symbols=frozenset(), computed_at="x", engine_version="v")
        assert old_post["resolution_state"] == "NOT_IN_MASTER"

    def test_mmc_real_resolution_is_asof_invariant_via_exact_match(
        self, master_inputs, etf_symbols,
    ):
        """Contrast with the isolated test above: against the REAL committed master,
        co:us:MMC resolves via rule 5 (master_inception_exact) — the master's
        inception_code is date-independent (mint-once-and-store), so it never even
        reaches the alias table, and the resolution is stable across any asof."""
        for asof in ("2020-01-01", "2026-01-13", "2026-01-14", "2026-08-14"):
            row = _resolve("co:us:MMC", master_inputs, etf_symbols, asof=asof)
            assert row["resolution_state"] == "RESOLVED"
            assert row["join_method"] == "master_inception_exact"
            assert row["security_id"] == "SEC:US-XNYS-MMC"

    def test_ambiguous_when_two_vendors_disagree(self):
        """A constructed conflict: two DIFFERENT vendor spaces resolving the same
        symbol to two different securities on the same date — AMBIGUOUS, never picked
        by precedence/cap/name."""
        table = VendorAliasTable([
            AliasRow("yahoo", "DUP", "SEC:US-XNYS-AAA", None, None),
            AliasRow("membership", "DUP", "SEC:US-XNAS-BBB", None, None),
        ])
        inputs = ir.MasterInputs(
            master_by_code={}, master_by_security={}, alias_table=table,
            vendors=frozenset({"yahoo", "membership"}), identity_exceptions={},
            generated_at=None, symbol_directory_snapshot=None, code_version=None,
        )
        row = ir._resolve_node_row(
            node_id="co:us:DUP", resolution_asof="2026-08-14", inputs=inputs,
            etf_symbols=frozenset(), computed_at="x", engine_version="v")
        assert row["resolution_state"] == "AMBIGUOUS"
        assert row["security_id"] is None
        candidates = json.loads(row["source_receipts"])["candidates"]
        assert set(candidates) == {"SEC:US-XNYS-AAA", "SEC:US-XNAS-BBB"}


# ---------------------------------------------------------------------------
# F1 (post-adversarial-review) — cross-market equality. A rule 5/6 hit whose master
# row belongs to a DIFFERENT country than the node's own market_scope must refuse,
# never resolve and never AMBIGUOUS: the master row is definitively another market's
# security, not a coincidental symbol collision. Isolated synthetic fixture per the
# commission — not an invented graph node in the real store, which is 100% US today
# and so cannot exhibit this collision live.
# ---------------------------------------------------------------------------

class TestF1CrossMarketEquality:
    def test_a_ca_scope_node_whose_symbol_equals_a_us_inception_code_refuses(self):
        inputs = ir.MasterInputs(
            master_by_code={"TSLA": {"security_id": "SEC:US-XNAS-TSLA",
                                     "issuer_id": "ISS:US-XNAS-TSLA",
                                     "listing_key": "US-XNAS-TSLA"}},
            master_by_security={"SEC:US-XNAS-TSLA": {"security_id": "SEC:US-XNAS-TSLA",
                                                      "issuer_id": "ISS:US-XNAS-TSLA",
                                                      "listing_key": "US-XNAS-TSLA"}},
            alias_table=VendorAliasTable(), vendors=frozenset(),
            identity_exceptions={}, generated_at=None,
            symbol_directory_snapshot=None, code_version=None,
        )
        row = ir._resolve_node_row(
            node_id="co:ca:TSLA", resolution_asof="2026-08-14", inputs=inputs,
            etf_symbols=frozenset(), computed_at="x", engine_version="v")
        assert row["resolution_state"] == "NOT_IN_MASTER", row
        assert row["security_id"] is None and row["issuer_id"] is None \
            and row["listing_key"] is None
        assert row["join_method"] == "refused"
        assert "cross-market" in row["refusal_reason"] or "CA" in row["refusal_reason"]
        receipts = json.loads(row["source_receipts"])
        assert receipts.get("cross_market_collision") is True
        assert receipts.get("would_resolve_to") == "SEC:US-XNAS-TSLA"

    def test_a_matching_market_still_resolves(self):
        """Control: the SAME master row, queried by a us-scope node, resolves normally
        — the refusal is about the market disagreement, not about the fixture."""
        inputs = ir.MasterInputs(
            master_by_code={"TSLA": {"security_id": "SEC:US-XNAS-TSLA",
                                     "issuer_id": "ISS:US-XNAS-TSLA",
                                     "listing_key": "US-XNAS-TSLA"}},
            master_by_security={}, alias_table=VendorAliasTable(), vendors=frozenset(),
            identity_exceptions={}, generated_at=None,
            symbol_directory_snapshot=None, code_version=None,
        )
        row = ir._resolve_node_row(
            node_id="co:us:TSLA", resolution_asof="2026-08-14", inputs=inputs,
            etf_symbols=frozenset(), computed_at="x", engine_version="v")
        assert row["resolution_state"] == "RESOLVED"
        assert row["security_id"] == "SEC:US-XNAS-TSLA"

    def test_a_cross_market_vendor_alias_hit_also_refuses(self):
        """The same collision reached via rule 6 (vendor_alias) rather than rule 5."""
        table = VendorAliasTable([AliasRow("yahoo", "SHOP", "SEC:US-XNYS-SHOP",
                                           None, None)])
        inputs = ir.MasterInputs(
            master_by_code={}, master_by_security={
                "SEC:US-XNYS-SHOP": {"security_id": "SEC:US-XNYS-SHOP",
                                     "issuer_id": "ISS:US-XNYS-SHOP",
                                     "listing_key": "US-XNYS-SHOP"}},
            alias_table=table, vendors=frozenset({"yahoo"}), identity_exceptions={},
            generated_at=None, symbol_directory_snapshot=None, code_version=None,
        )
        row = ir._resolve_node_row(
            node_id="co:hk:SHOP", resolution_asof="2026-08-14", inputs=inputs,
            etf_symbols=frozenset(), computed_at="x", engine_version="v")
        assert row["resolution_state"] == "NOT_IN_MASTER", row
        assert row["security_id"] is None
        receipts = json.loads(row["source_receipts"])
        assert receipts.get("cross_market_collision") is True


# ---------------------------------------------------------------------------
# F2 (BLOCKER, post-adversarial-review) — two-clock law on the HISTORICAL asof path.
# Asserted through the PUBLIC reader API (resolve_graph_node_identity), per the
# commission. ECHO and MMC are real graph nodes and exercise the mechanism against the
# REAL committed master + alias table. MRSH is never itself a graph topology id — the
# permanent node id law keeps the id on the FIRST-known symbol (co:us:MMC), never a
# later vendor-rename spelling — so the MRSH probe uses an isolated fixture graph +
# master, pinned to the same MMC/MRSH 2026-01-14 boundary, to prove the two-clock law
# end-to-end through the reader rather than the pure algorithm alone.
# ---------------------------------------------------------------------------

class TestF2TwoClockLawPublicReader:
    @pytest.mark.parametrize("node_id,asof,expected_state,expected_security", [
        ("co:us:ECHO", "2015-01-01", "NOT_IN_MASTER", None),
        ("co:us:ECHO", "2026-06-23", "NOT_IN_MASTER", None),
        ("co:us:ECHO", "2026-07-01", "RESOLVED", "SEC:US-XNAS-SATS"),
        ("co:us:MMC", "2015-01-01", "RESOLVED", "SEC:US-XNYS-MMC"),
    ])
    def test_echo_and_mmc_probes_against_the_real_committed_graph(
        self, node_id, asof, expected_state, expected_security,
    ):
        row = ir.resolve_graph_node_identity(node_id, asof=asof)
        assert row["resolution_state"] == expected_state, (node_id, asof, row)
        if expected_security:
            assert row["security_id"] == expected_security
        else:
            assert row["security_id"] is None

    def test_echo_pre_boundary_discloses_current_catalog_rows_were_excluded(self):
        """ECHO has fully-open (store/yahoo_fetch) rows in the REAL committed table in
        addition to its dated ledger/membership/yahoo rows — this is the live proof
        that a pre-boundary historical query does NOT fall back to them."""
        row = ir.resolve_graph_node_identity("co:us:ECHO", asof="2015-01-01")
        assert row["resolution_state"] == "NOT_IN_MASTER"
        assert "current-catalog" in row["refusal_reason"]
        receipts = json.loads(row["source_receipts"])
        assert receipts.get("current_catalog_rows_excluded_as_historical_evidence") is True

    def test_mrsh_probes_via_an_isolated_fixture_graph_and_master(self, tmp_path,
                                                                   monkeypatch):
        node_id = "co:us:MRSH"
        stamp = "2024-01-02T00:00:00Z"
        node_rows = [{
            "node_id": node_id, "kind": "company", "name_en": None, "name_zh": None,
            "market_scope": "us", "tier": None, "status": "canonical",
            "merged_into": None, "birth_date": None, "retire_date": None,
            "identity_epoch": 1, "external_ids": "{}", "provenance": "fixture",
            "computed_at": stamp, "engine_version": store.ENGINE_VERSION,
            "source_meta": None,
        }]
        graph_dir = tmp_path / "theme_graph"
        graph_dir.mkdir(parents=True)
        pd.DataFrame(node_rows).reindex(columns=list(store.NODE_COLUMNS)).to_parquet(
            graph_dir / "nodes.parquet", index=False)
        pd.DataFrame([]).reindex(columns=list(store.EDGE_COLUMNS)).to_parquet(
            graph_dir / "edges.parquet", index=False)
        pd.DataFrame([]).reindex(columns=list(store.EVIDENCE_COLUMNS)).to_parquet(
            graph_dir / "evidence.parquet", index=False)

        ref_dir = tmp_path / "reference"
        ref_dir.mkdir(parents=True)
        pd.DataFrame([{"security_id": "SEC:US-XNYS-MMC", "issuer_id": "ISS:US-XNYS-MMC",
                       "listing_key": "US-XNYS-MMC", "inception_code": "MMC"}]).to_parquet(
            ref_dir / "security_master.parquet", index=False)
        pd.DataFrame([
            {"vendor": "yahoo", "vendor_symbol": "MMC", "security_id": "SEC:US-XNYS-MMC",
             "valid_from": None, "valid_to": date(2026, 1, 14)},
            {"vendor": "yahoo", "vendor_symbol": "MRSH", "security_id": "SEC:US-XNYS-MMC",
             "valid_from": date(2026, 1, 14), "valid_to": None},
        ]).to_parquet(ref_dir / "vendor_aliases.parquet", index=False)
        (ref_dir / "_receipt.json").write_text(json.dumps({
            "generated_at": None, "symbol_directory_snapshot": None, "code_version": None,
            "identity_exceptions": [],
        }), encoding="utf-8")

        monkeypatch.setattr(lib_config, "data_dir", lambda: tmp_path)

        pre = ir.resolve_graph_node_identity(node_id, asof="2015-01-01")
        assert pre["resolution_state"] == "NOT_IN_MASTER", pre

        post = ir.resolve_graph_node_identity(node_id, asof="2026-02-01")
        assert post["resolution_state"] == "RESOLVED", post
        assert post["security_id"] == "SEC:US-XNYS-MMC"
        assert post["join_method"] == "vendor_alias"


# ---------------------------------------------------------------------------
# §5 — reader API
# ---------------------------------------------------------------------------

class TestReaderAPI:
    def test_read_identity_resolution_matches_the_store_reader(self):
        assert (ir.read_identity_resolution(latest=True).equals(
            store.read_identity_resolution(latest=True)))

    def test_resolve_graph_node_identity_raises_for_an_unknown_node(self):
        with pytest.raises(ir.UnknownGraphNodeError):
            ir.resolve_graph_node_identity("co:us:THIS_NODE_DOES_NOT_EXIST_ZZZ")

    def test_resolve_graph_node_identity_raises_for_a_non_company_node(self, nodes):
        non_company = nodes[nodes["kind"].astype(str) != "company"]
        assert not non_company.empty
        other_id = str(non_company.iloc[0]["node_id"])
        with pytest.raises(ir.UnknownGraphNodeError):
            ir.resolve_graph_node_identity(other_id)

    def test_resolve_graph_node_identity_with_explicit_asof_is_pure(self):
        """A pure re-run — no store write, and calling it twice with the same asof
        returns the same typed row (idempotent, no second store)."""
        first = ir.resolve_graph_node_identity("co:us:MMC", asof="2026-08-14")
        second = ir.resolve_graph_node_identity("co:us:MMC", asof=date(2026, 8, 14))
        assert first["resolution_state"] == second["resolution_state"] == "RESOLVED"
        assert first["security_id"] == second["security_id"] == "SEC:US-XNYS-MMC"

    def test_resolve_graph_node_identity_never_returns_an_untyped_resolution(self):
        """A known node, even one the persisted sidecar has not yet resolved (queried
        with asof=None before any build has written the sidecar for it in this
        process), must still come back as a typed row — never None/untyped."""
        row = ir.resolve_graph_node_identity("co:us:ANGPY")
        assert row is not None
        assert row["resolution_state"] in ir.RESOLUTION_STATES
        assert row["node_id"] == "co:us:ANGPY"


# ---------------------------------------------------------------------------
# Determinism / referential integrity over the real committed inputs
# ---------------------------------------------------------------------------

def test_derive_rows_is_deterministic(company_nodes, master_inputs):
    a = ir.derive_rows(company_nodes.to_dict("records"), resolution_asof="2026-08-14",
                       computed_at="c1", engine_version="v1")
    b = ir.derive_rows(company_nodes.to_dict("records"), resolution_asof="2026-08-14",
                       computed_at="c1", engine_version="v1")
    assert a == b


def test_every_resolved_security_id_exists_in_the_master(company_nodes, master_inputs,
                                                          etf_symbols):
    rows = ir.derive_rows(company_nodes.to_dict("records"), resolution_asof="2026-08-14",
                          computed_at="c1", engine_version="v1")
    master = pd.read_parquet(MASTER_PATH)
    known = set(master["security_id"])
    for row in rows:
        if row["resolution_state"] == "RESOLVED":
            assert row["security_id"] in known, row


# ---------------------------------------------------------------------------
# F3b (post-adversarial-review) — the reproducibility gate the review found missing:
# the COMMITTED artifact's current view must be frame-equal to a FRESH derive_rows()
# over the committed graph + master inputs, column order/dtype normalized.
# ---------------------------------------------------------------------------

def test_the_committed_bake_is_reproducible_from_the_committed_inputs(nodes):
    # The store is deliberately append-only, keyed on (node_id, computed_at): one row
    # per node PER MATERIALIZED GENERATION (engine/theme_graph/store.py). Comparing the
    # raw artifact would mix an older generation's rows in with the newest once a
    # second bake has landed, so collapse to the store's own "current view" first —
    # the same reader every production consumer uses.
    current_view = store.read_identity_resolution(latest=True)
    assert not current_view.empty

    # Even the per-node "current view" can carry one stale row: a node whose latest
    # committed row predates the newest bake (e.g. it was not part of that run, or the
    # graph grew a node after the run). That is a legitimate state for the store — it is
    # NOT a legitimate state for THIS check, whose whole point is "does the newest
    # generation reproduce from today's committed master". So scope the reproducibility
    # comparison to the newest generation's own cohort (max computed_at), not the whole
    # current view. An older generation legitimately may not reproduce from today's
    # inputs — that is expected, not a defect.
    newest_computed_at = current_view["computed_at"].max()
    baked = current_view[current_view["computed_at"] == newest_computed_at].reset_index(drop=True)
    assert not baked.empty
    resolution_asof = str(baked["resolution_asof"].iloc[0])
    engine_version = str(baked["engine_version"].iloc[0])
    assert (baked["resolution_asof"].astype(str) == resolution_asof).all(), (
        "the newest generation's own cohort must be a single generation for this "
        "comparison to be valid")
    assert (baked["engine_version"].astype(str) == engine_version).all()

    fresh_rows = ir.derive_rows(
        nodes.to_dict("records"), resolution_asof=resolution_asof,
        computed_at="reproducibility-check", engine_version=engine_version)
    fresh = pd.DataFrame(fresh_rows).reindex(columns=list(store.IDENTITY_RESOLUTION_COLUMNS))
    # Scope fresh the same way: a node the graph grew AFTER this generation was baked
    # was never resolved at this resolution_asof by the committed run, so it cannot be
    # part of a check for whether that run reproduces.
    fresh = fresh[fresh["node_id"].astype(str).isin(baked["node_id"].astype(str))]

    baked_sorted = baked.sort_values("node_id", kind="stable").reset_index(drop=True)
    fresh_sorted = fresh.sort_values("node_id", kind="stable").reset_index(drop=True)
    assert list(baked_sorted["node_id"].astype(str)) == list(fresh_sorted["node_id"])

    # computed_at is EXCLUDED — a wall-clock stamp, by design fresh on every call. Every
    # other column, including resolution_asof/engine_version (read from the artifact
    # itself, not hard-coded), must match exactly.
    compare_cols = [c for c in store.IDENTITY_RESOLUTION_COLUMNS if c != "computed_at"]
    for col in compare_cols:
        b_col = baked_sorted[col].astype(object).where(baked_sorted[col].notna(), None)
        f_col = fresh_sorted[col].astype(object).where(fresh_sorted[col].notna(), None)
        mismatches = [
            (nid, bv, fv) for nid, bv, fv in
            zip(baked_sorted["node_id"].astype(str), b_col, f_col) if bv != fv]
        assert not mismatches, (col, mismatches[:5])
