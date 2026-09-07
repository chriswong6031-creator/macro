"""Pure-source assertions for packet B-A-F04-3 (F04 identity archaeology).

No `data/`, no `site/`, no network access - must pass in a sparse worktree.
Pins the round-2 META-CEO B ruling recorded in
agentos/decisions/DEC-F04-CANONICAL-ETF-IDENTITY-OWNER-2026-09-06.md and the
memo at
research/market_intelligence_productization/F04_IDENTITY_ARCHAEOLOGY_2026-09-06.md:
no canonical ETF security-identity owner is named (upholding the ratified
2026-09-04 F04 closure map §2.4), `etf_node_id` is scoped to a graph-node
slug only, and the ETF-symbol coverage figure discloses its own bias.
"""

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]

MEMO_PATH = (
    REPO_ROOT
    / "research"
    / "market_intelligence_productization"
    / "F04_IDENTITY_ARCHAEOLOGY_2026-09-06.md"
)
DEC_PATH = (
    REPO_ROOT
    / "agentos"
    / "decisions"
    / "DEC-F04-CANONICAL-ETF-IDENTITY-OWNER-2026-09-06.md"
)


def test_graph_node_slug_minter_module_and_symbol_exist():
    identity_path = REPO_ROOT / "engine" / "theme_graph" / "identity.py"
    assert identity_path.exists(), (
        "the DEC's named graph-node slug minter module is missing: "
        f"{identity_path}"
    )
    from engine.theme_graph.identity import etf_node_id

    assert etf_node_id("tan") == "etf:TAN"


def test_k1_evidence_layer_binds_to_the_graph_node_slug_minter():
    evidence_foundation_path = REPO_ROOT / "lib" / "evidence_foundation.py"
    text = evidence_foundation_path.read_text(encoding="utf-8")
    assert "etf_node_id" in text, (
        "the DEC's decisive evidence (lib/evidence_foundation.py:309-310) no "
        "longer holds - update DEC-F04-CANONICAL-ETF-IDENTITY-OWNER-2026-09-06."
    )


def test_roster_owner_exists_and_is_not_an_id_minter():
    registry_path = REPO_ROOT / "engine" / "etf_registry.py"
    assert registry_path.exists()

    from engine.etf_registry import fund_registry  # noqa: F401

    text = registry_path.read_text(encoding="utf-8")
    assert "etf:" not in text, (
        "engine/etf_registry.py now mints an `etf:` id - the identity/roster "
        "split recorded in DEC-F04-CANONICAL-ETF-IDENTITY-OWNER-2026-09-06 "
        "must be revisited."
    )


def test_stock_identity_owns_no_etf():
    stock_identity_dir = REPO_ROOT / "engine" / "stock_identity"
    assert stock_identity_dir.exists()

    hits = []
    for path in stock_identity_dir.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        if "etf" in path.read_text(encoding="utf-8").lower():
            hits.append(path)

    assert not hits, (
        "engine/stock_identity/ now references ETFs; the refutation in "
        "DEC-F04-CANONICAL-ETF-IDENTITY-OWNER-2026-09-06 must be revisited. "
        f"Offending files: {hits}"
    )


def test_dec_record_is_wellformed_and_names_both_ledger_rows():
    text = DEC_PATH.read_text(encoding="utf-8")
    assert text.startswith("---"), "DEC record must open with YAML frontmatter"
    _, frontmatter_raw, _body = text.split("---", 2)
    frontmatter = yaml.safe_load(frontmatter_raw)

    assert frontmatter["schema"] == "agentos.decision.v1"
    assert frontmatter["key"] == "F04-CANONICAL-ETF-IDENTITY-OWNER-2026-09-06"
    assert DEC_PATH.stem == "DEC-" + frontmatter["key"]

    required_fields = {
        "key",
        "question",
        "answer",
        "rationale",
        "alternatives",
        "evidence",
        "affects",
        "confidence",
        "reversibility",
        "decided_by",
        "decided_at",
    }
    missing = required_fields - frontmatter.keys()
    assert not missing, f"DEC record missing required fields: {missing}"

    assert frontmatter["confidence"] in {"high", "medium", "low"}
    assert frontmatter["reversibility"] in {"easy", "costly", "one_way"}

    alternatives = frontmatter["alternatives"]
    assert alternatives, "alternatives must be non-empty"
    for alt in alternatives:
        assert "option" in alt and "why_not" in alt

    assert "MO-DELTA-005" in text
    assert "MO-DELTA-009" in text


def test_memo_carries_the_binding_sentences():
    text = MEMO_PATH.read_text(encoding="utf-8")
    for needle in (
        "engine/theme_graph/identity.py:234",
        "engine/etf_registry.py",
        "engine/stock_identity/",
        "No new identity store is proposed",
        "row type over the existing baseline",
        "#6896",
        "engine/chronicle/impact.py",
        "MO-DELTA-005",
        "MO-DELTA-009",
        "We did not count it, and we are not guessing.",
        "lib/dataos/identity.py",
        "76 baskets",
        "25 distinct symbols",
        "flow-board/holdings estate",
    ):
        assert needle in text, f"memo missing required sentence/anchor: {needle!r}"


def test_no_sentence_names_an_etf_identity_owner():
    """META-CEO B ruling r2, BLOCKER-1 (upheld): the memo and the DEC may not
    name engine/theme_graph/identity.py::etf_node_id (or anything else) as
    THE canonical ETF identity owner - MARKET_ONTOLOGY_F04_EXACT_CAPABILITY_
    CLOSURE_MAP_2026-09-04.md §2.4 already refuses a graph node slug as
    identity, and that ruling is ratified and stands."""
    memo_text = MEMO_PATH.read_text(encoding="utf-8")
    dec_text = DEC_PATH.read_text(encoding="utf-8")
    forbidden = (
        "CANONICAL ETF IDENTITY (ID) OWNER",
        "Canonical ETF identity owner =",
        "is the canonical ETF identity owner",
        "is the canonical ETF identity\n  owner",
        "Yes, an owner exists and is named",
    )
    for needle in forbidden:
        assert needle not in memo_text, (
            f"memo still names an ETF identity owner: {needle!r}"
        )
        assert needle not in dec_text, (
            f"DEC still names an ETF identity owner: {needle!r}"
        )


def test_closure_map_2_4_is_cited_and_upheld():
    """The rewritten answer must cite the ratified closure-map ruling by
    file:line, not merely by section number, and must state the NO-owner
    conclusion the ruling requires."""
    memo_text = MEMO_PATH.read_text(encoding="utf-8")
    dec_text = DEC_PATH.read_text(encoding="utf-8")
    for text, name in ((memo_text, "memo"), (dec_text, "DEC")):
        assert "graph node slug is not sufficient" in text, (
            f"{name} does not cite the closure map's :135 ruling"
        )
        assert ":135" in text, f"{name} missing closure map :135 citation"
        assert ":151" in text, f"{name} missing closure map :151 citation"
        assert "NO canonical ETF security-identity owner exists" in text or (
            "NO canonical ETF security-identity owner exists" in dec_text
        )
    assert "NO canonical ETF security-identity owner exists" in dec_text
    assert "NO canonical ETF security-identity owner exists" in memo_text


def test_open_row_wording_present_for_the_join_contract():
    """The join contract etf:<SYMBOL> <-> data/etf_holdings/<FUND>/ must be
    recorded as an explicit OPEN row naming the owning program, per the
    ruling's required answer text."""
    memo_text = MEMO_PATH.read_text(encoding="utf-8")
    dec_text = DEC_PATH.read_text(encoding="utf-8")
    for text, name in ((memo_text, "memo"), (dec_text, "DEC")):
        assert "OPEN row" in text, f"{name} missing explicit OPEN row wording"
        assert "F04 identity" in text, f"{name} missing the owning-program name"


def test_etf_node_id_statements_are_scoped_to_graph_side():
    """MAJOR-1: no statement about etf_node_id may claim it covers anything
    beyond graph-side ids - the 'and nothing else' framing the review flagged
    must be replaced with an explicit graph-side scope statement."""
    memo_text = MEMO_PATH.read_text(encoding="utf-8")
    assert 'implied "and nothing else."' not in memo_text
    assert "flow-board/holdings estate" in memo_text
    assert "graph-side" in memo_text


def test_symbol_count_discloses_its_own_bias():
    """MAJOR (25-distinct-symbols figure): the count must disclose its
    counting method and the family it is blind to, not present a
    literal-value grep as a resolution of all 76 declared etf_proxy sites."""
    memo_text = MEMO_PATH.read_text(encoding="utf-8")
    dec_text = DEC_PATH.read_text(encoding="utf-8")
    for text, name in ((memo_text, "memo"), (dec_text, "DEC")):
        assert "29 of" in text or "29 of those 76" in text, (
            f"{name} does not disclose the 29-of-76 matched-site count"
        )
        assert "seed_us_sector_baskets.py" in text, (
            f"{name} does not name the blind-spot family"
        )
        assert "variable" in text, f"{name} does not name why the family is missed"


def test_store_side_null_carries_no_sparse_worktree_excuse():
    """MAJOR-2 (the null's stated cause): the store-side overlap null must
    either state its true cause with evidence, or be printed without a
    claimed cause - it may not blame the sparse worktree, since
    `python3 scripts/worktree_sparse.py full` was an available, untaken
    remedy."""
    memo_text = MEMO_PATH.read_text(encoding="utf-8")
    dec_text = DEC_PATH.read_text(encoding="utf-8")
    for text, name in ((memo_text, "memo"), (dec_text, "DEC")):
        assert "absent in this sparse worktree" not in text, (
            f"{name} still blames the sparse worktree for the store-side null"
        )
        assert "absent in the sparse worktree" not in text, (
            f"{name} still blames the sparse worktree for the store-side null"
        )
        assert "NOT MEASURED" in text, f"{name} must still print the null"


def test_dataos_identity_owns_no_etf():
    """BLOCKER-2: the Data OS half of the composite closure-map route must be
    verified absent, not merely asserted."""
    dataos_identity = REPO_ROOT / "lib" / "dataos" / "identity.py"
    assert dataos_identity.exists(), (
        "the DEC's reconciled Data OS identity module is missing: "
        f"{dataos_identity}"
    )
    text = dataos_identity.read_text(encoding="utf-8").lower()
    assert "etf" not in text, (
        "lib/dataos/identity.py now references ETFs; the refutation of the "
        "Data OS half of the composite owner route in "
        "DEC-F04-CANONICAL-ETF-IDENTITY-OWNER-2026-09-06 must be revisited."
    )
