"""Pure-source assertions for packet B-A-F04-3 (F04 identity archaeology).

No `data/`, no `site/`, no network access - must pass in a sparse worktree.
Pins the canonical ETF identity owner named in
agentos/decisions/DEC-F04-CANONICAL-ETF-IDENTITY-OWNER-2026-09-06.md and the
memo at
research/market_intelligence_productization/F04_IDENTITY_ARCHAEOLOGY_2026-09-06.md.
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


def test_named_owner_module_and_symbol_exist():
    identity_path = REPO_ROOT / "engine" / "theme_graph" / "identity.py"
    assert identity_path.exists(), (
        "the DEC's named canonical ETF identity owner module is missing: "
        f"{identity_path}"
    )
    from engine.theme_graph.identity import etf_node_id

    assert etf_node_id("tan") == "etf:TAN"


def test_k1_evidence_layer_binds_to_the_named_owner():
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
    ):
        assert needle in text, f"memo missing required sentence/anchor: {needle!r}"
