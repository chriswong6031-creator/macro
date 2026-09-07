"""Security State view model — `build_security_state()` against the contract.

The contract suite proves the compiler emits the right payload. This suite
proves the DOSSIER reads that payload: every assertion here names a field the
compiled `security_state.v1` object actually carries, so a projection that
quietly reads a field the contract never emits fails here rather than shipping
an empty panel.

Four things are pinned, all of them regressions this file exists to prevent:

1. Integration — a really compiled object, straight through the projection,
   reaching the view model with its real recipe/block ids, its real compilation
   denominator, its coverage counts, its R1..R9 receipts and its state leg.
2. The State axis renders from `legs.state`, never from the blob's own ladder.
3. `last_good` is read by the keys the contract writes.
4. An `ESTIMATED_WINDOW` observable renders as a window that says it is not an
   announced date.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from scripts.build_ticker_pages import build_security_state  # noqa: E402


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _axis(view: dict, key: str) -> dict:
    for a in view["axes"]:
        if a["key"] == key:
            return a
    raise AssertionError(f"axis {key!r} missing from the view model")


def _k1_bundle(engine, subject, workspace, disposition: str, manifest_sha256: str | None) -> dict:
    from lib.evidence_foundation import compile_recipe

    recipe = engine._build_k1_recipe(subject=subject)
    empty = compile_recipe(recipe, blocks=[], references={})
    found = None
    if disposition == "found" and isinstance(workspace, dict):
        lifecycle = workspace.get("lifecycle") or {}
        reference = engine._build_k1_reference(
            subject=subject,
            generation_id=workspace["generation_id"], event_id=workspace["event_id"],
            manifest_sha256=manifest_sha256,
            source_available_at=lifecycle.get("source_available_at"),
            observed_at=lifecycle.get("observed_at"),
            generated_at=workspace.get("generated_at"),
        )
        block = engine._build_k1_block([reference], subject=subject)
        found = {
            "reference_id": reference["reference_id"],
            "block_id": block["evidence_block_id"],
            "compilation": compile_recipe(
                recipe, blocks=[block], references={reference["reference_id"]: reference},
            ),
        }
    return {
        "subject_cik": subject.issuer_cik,
        "recipe_id": recipe["recipe_id"],
        "empty_compilation": empty,
        "found": found,
    }


def _render_section(view: dict, lang: str = "en") -> str:
    """Render the dossier template far enough to read the section's own text.

    The section is server-rendered, so "does the value reach the page" is a
    question about HTML, not about a dict. Undefined page context is chainable
    so the rest of the dossier simply does not render.
    """
    import jinja2

    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(REPO / "templates")),
        undefined=jinja2.ChainableUndefined,
    )
    html = env.get_template("ticker.html.j2").render(
        security_state=view, ticker="AAPL", name="Apple Inc.",
    )
    assert 'id="security-state"' in html, "the section did not render at all"
    if lang == "en":
        # Drop the Chinese twin of every bilingual pair so an assertion cannot
        # pass on the other language's copy.
        html = re.sub(r'<span class="l-zh">.*?</span>', "", html, flags=re.S)
    else:
        html = re.sub(r'<span class="l-en">.*?</span>', "", html, flags=re.S)
    return html


# ---------------------------------------------------------------------------
# 1 · integration — a really compiled object through the real projection
# ---------------------------------------------------------------------------

# Hand-carried golden inputs. Deliberately a copy rather than an import of the
# contract suite's fixture files: this suite must fail when the CONSUMER drifts
# from the contract, and a shared fixture that moves with the producer would
# hide exactly that.
GOLDEN_NOW = "2026-08-23T12:00:00Z"

GOLDEN_SECURITY_MASTER_ROW = {
    "security_id": "SEC:US-XNAS-AAPL",
    "issuer_id": "ISS:US-XNAS-AAPL",
    "issuer_state": "RESOLVED",
    "issuer_cik": "0000320193",
    "listing_key": "US-XNAS-AAPL",
    "country": "US",
    "mic": "XNAS",
    "inception_code": "AAPL",
    "security_state": None,
    "superseded_by": None,
}

GOLDEN_ISSUER_MASTER_ROWS = [{
    "issuer_id": "ISS:US-XNAS-AAPL",
    "cik": "0000320193",
    "legal_name": "Apple Inc.",
    "n_securities": 1,
    "status": "active",
    "era": "issuer_semantic_correction_v1",
}]

GOLDEN_WORKSPACE = {
    "schema": "event_workspace.v1",
    "event_id": "evt_cik0000320193_2026q3_results",
    "generation_id": "6d56c84a3ac23b8954e59ee7",
    "issuer": {
        "company_id": "cik:0000320193",
        "display_name": "Apple Inc.",
        "listings": [{
            "is_primary": True, "mic": "XNAS", "security_id": "xnas:AAPL",
            "share_class": "common", "ticker": "AAPL", "trading_currency": "USD",
            "valid_from": "1970-01-01", "valid_to": None,
        }],
    },
    "fiscal_period": {"calendar_end": "2026-06-27", "quarter": 3, "year": 2026},
    "lifecycle": {
        "observed_at": "2026-07-30T20:30:28Z",
        "source_available_at": "2026-07-30T20:30:28Z",
        "state": "complete",
    },
    "generated_at": "2026-07-30T20:30:28Z",
    "authority": "context_only",
    "prophet_flags": {"earnings_flagged": False},
    "claim_citations_pending": False,
    "qa_exchanges": [],
    "warnings": [
        "collector_filing_unjoinable", "consensus_unlicensed",
        "questions_count_unstructured", "reaction_not_joined",
        "slides_absent", "wire_record_not_found",
    ],
    "completeness": {"filing": {"filing_key": {
        "accession": "0000320193-26-000018", "cik": "0000320193"}}},
    "facts": [{"k": 1}, {"k": 2}, {"k": 3}],
    "deltas": [{"k": 1}],
    "guidance": [{"k": 1}, {"k": 2}],
    "claims": [], "sources": [], "aliases": {},
}

GOLDEN_BLOB = {
    "ticker": "AAPL", "name": "Apple Inc.", "sector": "Technology",
    "asof": "2026-08-23", "history_days": 500,
    "tech": {"chg_1d": 0.5, "price": 230.1},
    "ladder": {"state": "watch", "dir": "up",
               "entry": {"text": "Watching for a pullback entry.",
                         "text_zh": "等待回调买点。"}},
    "entry_signal": {"score": 1, "state": "watch"},
    "conviction": {"cautions": [
        "Valuation is rich relative to trailing five-year multiples."]},
    "alerts": {"pinned": None, "timeline": [], "n_recent": 2, "n_total": 10},
    "view": {}, "basket_alloc": {}, "alpha": {"alpha": 0.1},
}


def _compile_golden() -> dict:
    """Compile the golden AAPL object with the real compiler."""
    engine = pytest.importorskip("engine.security_state")
    subject = engine.SecurityStateSubject(
        security_id="SEC:US-XNAS-AAPL",
        issuer_id="ISS:US-XNAS-AAPL",
        listing_key="US-XNAS-AAPL",
        ticker_display="AAPL",
        issuer_cik="0000320193",
        owner_evidence=(
            ("decision_date", "2026-09-04"),
            ("alias_reader", "VendorAliasTable.resolve(store)"),
            ("issuer_reader", "IssuerMaster.issuer_of_security"),
            ("cik_reader", "IssuerMaster.cik_of_issuer"),
        ),
    )
    return engine.compile_security_state(
        validator=engine.build_security_state_validator(
            json.loads(engine.SCHEMA_PATH.read_text(encoding="utf-8"))
        ),
        subject=subject,
        k1_bundle=_k1_bundle(
            engine, subject, GOLDEN_WORKSPACE, "found",
            "c3b9495028c07e6bf1eb385f520f0b3c57064b84ea430540ba9a0808cd2d14db",
        ),
        now=GOLDEN_NOW,
        security_master_row=dict(GOLDEN_SECURITY_MASTER_ROW),
        issuer_master_rows=[dict(r) for r in GOLDEN_ISSUER_MASTER_ROWS],
        issuer_security_ids=["SEC:US-XNAS-AAPL"],
        issuer_migration_matches=[],
        security_migration_matches=[],
        workspace=GOLDEN_WORKSPACE,
        workspace_disposition="found",
        blob=GOLDEN_BLOB,
        manifest_sha256="c3b9495028c07e6bf1eb385f520f0b3c57064b84ea430540ba9a0808cd2d14db",
    )


def test_compiled_msft_object_reaches_the_existing_view_model() -> None:
    engine = pytest.importorskip("engine.security_state")
    subject = engine.SecurityStateSubject(
        security_id="SEC:US-XNAS-MSFT",
        issuer_id="ISS:US-XNAS-MSFT",
        listing_key="US-XNAS-MSFT",
        ticker_display="MSFT",
        issuer_cik="0000789019",
        owner_evidence=(
            ("decision_date", "2026-09-04"),
            ("alias_reader", "VendorAliasTable.resolve(store)"),
            ("issuer_reader", "IssuerMaster.issuer_of_security"),
            ("cik_reader", "IssuerMaster.cik_of_issuer"),
        ),
    )
    row = {
        "security_id": subject.security_id, "issuer_id": subject.issuer_id,
        "issuer_state": "RESOLVED", "issuer_cik": subject.issuer_cik,
        "listing_key": subject.listing_key, "country": "US", "mic": "XNAS",
        "inception_code": "MSFT", "security_state": None, "superseded_by": None,
    }
    blob = {**GOLDEN_BLOB, "ticker": "MSFT", "name": "Microsoft Corp."}
    compiled = engine.compile_security_state(
        subject=subject,
        validator=engine.build_security_state_validator(
            json.loads(engine.SCHEMA_PATH.read_text(encoding="utf-8"))
        ),
        now=GOLDEN_NOW, security_master_row=row,
        k1_bundle=_k1_bundle(engine, subject, None, "not_published", None),
        issuer_master_rows=[{
            "issuer_id": subject.issuer_id, "cik": subject.issuer_cik,
            "status": "active",
        }],
        issuer_security_ids=[subject.security_id], issuer_migration_matches=[],
        security_migration_matches=[], workspace=None,
        workspace_disposition="not_published", blob=blob, manifest_sha256=None,
    )
    view = build_security_state({"security_state": compiled})
    assert view is not None
    assert view["ticker_display"] == "MSFT"
    assert view["security_id"] == "SEC:US-XNAS-MSFT"
    assert view["issuer_id"] == "ISS:US-XNAS-MSFT"
    assert view["listing_key"] == "US-XNAS-MSFT"


def test_compiled_golden_object_reaches_the_view_model() -> None:
    """A really compiled object keeps its receipts all the way to the page."""
    compiled = _compile_golden()
    if "state" not in (compiled.get("legs") or {}):
        pytest.skip("compiler does not yet emit legs.state (producer lane in flight)")

    view = build_security_state({"security_state": compiled})
    assert view is not None

    legs = compiled["legs"]
    ev_leg = legs["evidence"]

    # ── evidence: the real recipe, the real blocks, the real denominator ──
    assert view["evidence"]["recipe_id"] == ev_leg["recipe_id"]
    assert view["evidence"]["recipe_id"], "recipe_id must not be blank"
    for ref in ev_leg["evidence_block_refs"]:
        assert ref in view["evidence"]["refs"]

    comp = ev_leg["compilation"]
    assert view["evidence"]["compile_state"] is not None
    assert view["evidence"]["compile_state"]["code"] == str(comp["state"]).upper()
    rendered_counts = {r["v"] for r in view["evidence"]["counts"]}
    for key, value in comp["denominator"].items():
        assert any(r["v"] == value for r in view["evidence"]["counts"]), (
            f"denominator.{key}={value} never reached the view model")
    assert rendered_counts, "denominator rendered empty"

    # ── coverage: available and nonblocking are separate answers ──
    cov = compiled["coverage"]
    vc = view["coverage"]
    assert vc["req_total"] == cov["required_legs_total"]
    assert vc["req_avail"] == cov["required_legs_available"]
    assert vc["req_nonblock"] == cov["required_legs_nonblocking"]
    assert vc["opt_total"] == cov["optional_legs_total"]
    assert vc["opt_avail"] == cov["optional_legs_available"]
    assert vc["opt_nonblock"] == cov["optional_legs_nonblocking"]

    # ── identity: R1..R9 with the fields the contract emits ──
    contract_legs = compiled["identity_proof"]["legs"]
    assert contract_legs, "the golden object carries no identity legs"
    assert len(view["identity"]["legs"]) == len(contract_legs)
    for src, out in zip(contract_legs, view["identity"]["legs"]):
        assert out["check"] == src["check"]
        assert out["desc"] == src["description"]
        assert out["artifact"] == src["artifact"]
        assert out["reader"] == src["reader"]
        assert out["result"] == str(src["result"]).lower()
        assert len(out["reads"]) == len(src["values_read"])
        for pair, row in zip(src["values_read"], out["reads"]):
            assert row["k"] == pair["field"]
    checks = [lg["check"] for lg in view["identity"]["legs"]]
    assert checks[0] == "R1" and "R9" in checks

    # ── state: the contract's own axis ──
    assert _axis(view, "state")["ladder_state"] == legs["state"]["ladder_state"]


# ---------------------------------------------------------------------------
# shared fixture — a compiled object in the amended shapes
# ---------------------------------------------------------------------------

def _contract(**over) -> dict:
    ss = {
        "schema": "security_state.v1",
        "version": "1.0.0",
        "security_id": "SEC:US-XNAS-AAPL",
        "issuer_id": "ISS:US-XNAS-AAPL",
        "listing_key": "US-XNAS-AAPL",
        "ticker_display": "AAPL",
        "generated_at": "2026-08-23T12:00:00Z",
        "content_sha256": "cfecf1282d8c59f8d265529e040f9d04ed7e31caaa3b23d8ab22c88cd74c0138",
        "as_of": {
            "market_at": "2026-08-23",
            "source_frontier_at": "2026-07-30T20:30:28Z",
            "state_compiled_at": "2026-08-23T12:00:00Z",
        },
        "identity_proof": {
            "state": "PROVEN",
            "method": "owner_backed_chain.v1",
            "legs": [{
                "check": "R1",
                "description": "security_master row exists, security_state/superseded_by both null",
                "artifact": "data/reference/security_master.parquet",
                "reader": "scripts/build_stock_library.py::_read_security_state_identity_rows",
                "values_read": [
                    {"field": "row_present", "value": True},
                    {"field": "security_state", "value": None},
                ],
                "result": "pass",
                "code": None,
            }],
            "equalities": [], "refusals": [], "disclosures": [],
        },
        "coverage": {
            "overall_state": "PARTIAL",
            "required_legs_total": 2, "required_legs_available": 2,
            "required_legs_nonblocking": 2,
            "optional_legs_total": 5, "optional_legs_available": 3,
            "optional_legs_nonblocking": 5,
            "missing_legs": [], "stale_legs": [],
            "rights_blocked_legs": [], "conflicted_legs": [],
        },
        "dominant_degradation": "PARTIAL",
        "legs": {
            "state": {
                "deterministic_state_refs": ["ladder.state", "ladder.dir", "tech.chg_1d"],
                "ladder_state": "watch",
                "ladder_direction": "up",
                "values_read": [{"field": "tech.chg_1d", "value": 0.5}],
                "summary": {"en": "Ladder state: watch (up).",
                            "zh": "阶梯状态：watch（上行）。"},
                "coverage_state": "AVAILABLE",
            },
            "change": {
                "event_refs": ["evt_cik0000320193_2026q3_results"],
                "generation_id": "6d56c84a3ac23b8954e59ee7",
                "observed_at": "2026-07-30T20:30:28Z",
                "summary": {"en": "Q3 2026 results workspace is complete.",
                            "zh": "Q3 2026 财报工作区状态为完整。"},
                "correction_state": "none",
                "coverage_state": "AVAILABLE",
                "workspace_warnings": ["reaction_not_joined"],
            },
            "opportunity_context": {
                "prophet": {"ref": None, "state": "UNAVAILABLE",
                            "reason": "no current Prophet US owner output for this security"},
                "entry": {"state": "AVAILABLE", "available": True, "null_reason": None},
                "market_incorporation": {"ref": None, "state": "NOT_COVERED"},
                "dislocation": {"ref": None, "state": "NOT_COVERED"},
                "coverage_state": "AVAILABLE",
            },
            "risk": {
                "risk_refs": ["alerts_n_total:10"],
                "failed_gates": [],
                "strongest_unresolved_fact": {
                    "state": "workspace_warning", "leg": "change",
                    "code": "reaction_not_joined",
                    "en": "Market reaction data has not been joined to this release yet.",
                    "zh": "市场反应数据尚未与此次发布关联。",
                },
                "coverage_state": "AVAILABLE",
            },
            "catalyst": {
                "next_observables": [{
                    "kind": "ESTIMATED_WINDOW",
                    "window_start": "2026-09-19",
                    "window_end": "2026-10-03",
                    "authoritative": False,
                    "basis": "fiscal_period.calendar_end + ~1 fiscal quarter (91 days), "
                             "deterministic calendar arithmetic",
                }],
                "deadlines": [],
                "coverage_state": "PARTIAL",
            },
            "personal_impact": {
                "state": "NO_USER_CONTEXT",
                "user_exposure_overlay_ref": None,
                "coverage_state": "NOT_APPLICABLE",
            },
            "evidence": {
                "evidence_block_refs": ["ebl_5b86ed829a65b95f6f82bc5a856f8f74"],
                "recipe_id": "erp_5687f42d2acac8826110a5952a4d0ba0",
                "compilation": {
                    "schema": "evidence_foundation.recipe_compilation_receipt.v1",
                    "recipe_id": "erp_5687f42d2acac8826110a5952a4d0ba0",
                    "state": "partial",
                    "dominant_degradation": "unknown",
                    "block_ids": ["ebl_5b86ed829a65b95f6f82bc5a856f8f74"],
                    "denominator": {"total": 1, "included": 1, "excluded": 0,
                                    "missing": 0, "stale": 0, "rights_blocked": 0,
                                    "fallback": 0, "identity_unresolved": 0},
                },
                "conflicts": [],
                "coverage_state": "PARTIAL",
            },
        },
        "last_good": None,
    }
    ss.update(over)
    return ss


# ---------------------------------------------------------------------------
# 2 · the State axis renders from the contract, not from the blob
# ---------------------------------------------------------------------------

def test_state_axis_renders_the_contract_not_the_blob_ladder() -> None:
    """The blob's own ladder is loudly wrong; the card must not repeat it."""
    contract = _contract()
    contract["legs"]["state"]["ladder_state"] = "downtrend"
    contract["legs"]["state"]["ladder_direction"] = "down"
    contract["legs"]["state"]["summary"] = {
        "en": "Ladder state: downtrend (down).", "zh": "阶梯状态：downtrend（下行）。"}

    blob = {
        # The blob disagrees on purpose — this is the fallback the section used
        # to render before the contract carried a state leg.
        "ladder": {"state": "uptrend", "dir": "up"},
        "security_state": contract,
    }
    view = build_security_state(blob)
    assert view is not None

    state = _axis(view, "state")
    assert state["ladder_state"] == "downtrend"
    assert state["ladder_direction"] == "down"
    assert {"k": "ladder_state", "v": "downtrend"} in state["fields"]
    assert state["headline"]["en"] == "Below its long-term trend"

    html = _render_section(view)
    # The contract's reading ("Below its long-term trend") is on the page and
    # the blob's ("In an uptrend") is nowhere in the section.
    assert "Below its long-term trend" in html
    assert "In an uptrend" not in html
    assert "pointing down" in html
    assert "pointing up" not in html


def _card_region(html: str) -> str:
    """Just the always-visible grid — the dialogs live outside the section."""
    start = html.index('id="security-state"')
    return html[start:html.index("</section>", start)]


def test_the_state_card_never_prints_the_raw_state_name() -> None:
    """The contract's summary is a receipt; the glance tier gets plain words.

    `legs.state.summary` restates the fields it read ("Ladder state: watch
    (up).") — an internal state name, and an English one inside the Chinese
    page. It is quoted verbatim in the drilldown and never on the card.
    """
    view = build_security_state({"security_state": _contract()})
    card = _card_region(_render_section(view))
    assert "Worth monitoring" in card
    assert "Ladder state:" not in card

    zh_card = _card_region(_render_section(view, lang="zh"))
    assert "值得关注" in zh_card
    assert "阶梯状态" not in zh_card

    # …and it is still there, unchanged, where receipts belong.
    assert "Ladder state: watch (up)." in _render_section(view)


def test_state_axis_without_a_state_leg_claims_nothing() -> None:
    """No state leg is 'not available', never a borrowed reading."""
    contract = _contract()
    contract["legs"].pop("state")
    view = build_security_state({"ladder": {"state": "uptrend"},
                                 "security_state": contract})
    state = _axis(view, "state")
    assert state["cov"] == "UNAVAILABLE"
    assert not state.get("ladder_state")
    assert "In an uptrend" not in _render_section(view)


# ---------------------------------------------------------------------------
# 3 · last_good is read by the keys the contract writes
# ---------------------------------------------------------------------------

def test_last_good_renders_from_the_contract_keys() -> None:
    view = build_security_state({"security_state": _contract(last_good={
        "generated_at": "2026-08-22T12:00:00Z",
        "content_sha256": "aa11bb22cc33dd44ee55ff66aa77bb88cc99dd00ee11ff22aa33bb44cc55dd66",
        "dominant_degradation": "STALE",
        "reason": "current cycle could not reach the owner",
    })})
    lg = view["last_good"]
    assert lg["ok"] is True
    assert lg["at"] == "2026-08-22 12:00Z"
    assert lg["sha"].startswith("aa11bb22")
    assert lg["deg"]["code"] == "STALE"
    assert lg["reason"]["en"] == "current cycle could not reach the owner"

    html = _render_section(view)
    assert "Last complete read" in html
    assert "2026-08-22 12:00Z" in html
    assert "aa11bb22" in html


def test_last_good_is_never_cited_for_a_read_that_failed() -> None:
    """A recorded fallback whose own compile failed is not a fallback."""
    view = build_security_state({"security_state": _contract(
        dominant_degradation="COMPILER_FAILURE",
        last_good={
            "generated_at": "2026-08-22T12:00:00Z",
            "content_sha256": "deadbeef" * 8,
            "dominant_degradation": "COMPILER_FAILURE",
            "reason": "compiler_failure",
        },
    )})
    assert view["last_good"]["ok"] is False
    html = _render_section(view)
    assert "This read could not be built" in html
    assert "Last complete read" not in html
    assert "2026-08-22 12:00Z" not in html


def test_last_good_absent_renders_no_banner() -> None:
    view = build_security_state({"security_state": _contract()})
    assert view["last_good"]["ok"] is False
    assert "Last complete read" not in _render_section(view)


# ---------------------------------------------------------------------------
# 4 · an estimated window never reads as an announced date
# ---------------------------------------------------------------------------

def test_estimated_window_renders_as_a_window_that_says_it_is_estimated() -> None:
    view = build_security_state({"security_state": _contract()})
    obs = _axis(view, "catalyst")["observables"]
    assert len(obs) == 1
    row = obs[0]
    assert row["est"] is True
    assert row["when"] == "2026-09-19 – 2026-10-03"
    assert row["basis"].startswith("fiscal_period.calendar_end")

    html = _render_section(view)
    assert "2026-09-19 – 2026-10-03" in html
    assert "Estimated window — not an announced date" in html
    # Neither end of the window may appear as a lone dated claim.
    assert not re.search(r"(?<!\d)2026-09-19(?!\s*–)", html)

    zh = _render_section(view, lang="zh")
    assert "预计窗口 — 并非官方公布日期" in zh


def test_an_authoritative_observable_carries_no_estimate_qualifier() -> None:
    contract = _contract()
    contract["legs"]["catalyst"]["next_observables"] = [{
        "kind": "CONFIRMED_EARNINGS",
        "date": "2026-10-29",
        "authoritative": True,
        "basis": "issuer announcement",
    }]
    view = build_security_state({"security_state": contract})
    row = _axis(view, "catalyst")["observables"][0]
    assert row["est"] is False
    assert row["when"] == "2026-10-29"
    html = _render_section(view)
    assert "Confirmed results date" in html
    assert "not an announced date" not in html


# ---------------------------------------------------------------------------
# receipts that used to render blank
# ---------------------------------------------------------------------------

def test_evidence_ids_and_denominator_reach_the_page() -> None:
    view = build_security_state({"security_state": _contract()})
    html = _render_section(view)
    assert "erp_5687f42d2acac8826110a5952a4d0ba0" in html
    assert "ebl_5b86ed829a65b95f6f82bc5a856f8f74" in html
    assert "Partly compiled" in html
    assert "Records asked for" in html
    assert "Records not tied to this listing" in html


def test_coverage_counts_separate_available_from_nonblocking() -> None:
    view = build_security_state({"security_state": _contract()})
    html = _render_section(view)
    assert "Required reads, current" in html
    assert "Optional reads, not in the way" in html
    assert "3 / 5" in html   # optional available
    assert "5 / 5" in html   # optional nonblocking


def test_not_applicable_leg_is_not_displayed_as_available() -> None:
    view = build_security_state({"security_state": _contract()})
    personal = _axis(view, "personal_impact")
    assert personal["cov"] == "NOT_APPLICABLE"
    assert personal["ok"] is False
    assert personal["tone"] == "off"


def test_identity_receipts_render_their_actual_fields() -> None:
    view = build_security_state({"security_state": _contract()})
    html = _render_section(view)
    assert "R1" in html
    assert "security_master row exists" in html
    assert "data/reference/security_master.parquet" in html
    assert "_read_security_state_identity_rows" in html
    assert "row_present" in html
    assert "true" in html
    assert "security_state</dt>" in html and "null" in html


def test_provenance_copy_is_two_register_and_bilingual() -> None:
    view = build_security_state({"security_state": _contract()})
    html = _render_section(view)
    # The absolutist claims are gone.
    assert "Nothing in this panel is calculated here" not in html
    assert "It does not calculate anything" not in html
    # Both registers are named, and the marker is on the page.
    assert "worked out here" in html
    assert "counted here" in html
    assert "quoted" in html
    zh = _render_section(view, lang="zh")
    assert "本页推算" in zh
    assert "本页统计" in zh


def test_absent_block_still_costs_only_the_section() -> None:
    assert build_security_state(None) is None
    assert build_security_state({}) is None
    assert build_security_state({"security_state": {}}) is None


# ---------------------------------------------------------------------------
# B-F06-1 · second issuer end to end — the golden MSFT compiled object renders
# with plain words, no raw enum codes, and both languages present
# ---------------------------------------------------------------------------

def test_view_model_renders_the_msft_state_with_plain_words() -> None:
    import jinja2

    fixture = REPO / "tests" / "fixtures" / "security_state" / "golden_msft_expected_output.json"
    state = json.loads(fixture.read_text(encoding="utf-8"))
    view = build_security_state({"security_state": state})
    assert view is not None
    assert view["ticker_display"] == "MSFT"

    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(REPO / "templates")),
        undefined=jinja2.ChainableUndefined,
    )
    html = env.get_template("ticker.html.j2").render(
        security_state=view, ticker="MSFT", name="Microsoft Corp.",
    )
    assert 'id="security-state"' in html

    for code in (
        "COMPILER_FAILURE", "IDENTITY_UNRESOLVED", "BLOCKED_IDENTITY_BRIDGE",
        "NOT_COVERED", "UNAVAILABLE",
    ):
        assert code not in html, f"raw enum code {code!r} leaked into MSFT panel markup"

    # macro#6920 round-3 MINOR #1: the allowlist above excludes every code
    # the MSFT panel actually renders — the golden fixture's own
    # `identity_proof.disclosures` carry these four (the
    # `owner_read_completed=True` shared `DISCLOSURES` tuple). Those codes
    # ARE expected to appear, but only inside their own `ss-id` receipt chip
    # — never as the bare sentence itself (the actual MAJOR #2 failure mode).
    for code in (
        "CIK_LEG_OWNER_BACKED_CURRENT_ONLY", "OWNER_COMPOSED_SUBJECT_CURRENT_ONLY",
        "ISSUERMASTER_CURRENT_IDENTITY_ONLY", "ALIAS_EPOCH_VALID_FROM",
    ):
        assert f'<span class="c ss-id">{code}</span>' in html, (
            f"{code}: expected inside its ss-id receipt chip, not found"
        )
        assert f'<span class="l-en">{code}</span>' not in html, (
            f"{code}: raw code leaked as the bare EN sentence"
        )
        assert f'<span class="l-zh">{code}</span>' not in html, (
            f"{code}: raw code leaked as the bare ZH sentence"
        )

    import re
    section_match = re.search(r'id="security-state".*?(?=<section )', html, re.DOTALL)
    assert section_match is not None, "could not isolate the #security-state panel markup"
    section_html = section_match.group(0)
    assert '<span class="l-en">' in section_html
    assert '<span class="l-zh">' in section_html


def test_dfoot_c_chip_scoping_is_structural_not_a_grep_count() -> None:
    """The `.dfoot .c{margin-left:6px;...}` CSS rule (round-3 MAJOR #1 fix)
    applies to every `.c`-classed descendant of every `.dfoot` element on the
    page. A prior PR body argued this could not regress any other `.dfoot`
    usage by grepping `class="dfoot"` line counts in the `.j2` source and
    eyeballing which lines also mentioned `class="c"` — a text coincidence
    on the SOURCE template, not a structural check of what actually renders
    (round-3 review MINOR-3). A `.dfoot` spanning several lines, or a `.c`
    element nested inside conditional Jinja branches, would not show up in a
    single-line grep at all.

    This test instead parses the ACTUALLY RENDERED HTML with a real HTML
    parser (BeautifulSoup) and asks, for every `.dfoot` element, whether it
    has a `.c`-classed descendant — the exact question the CSS selector
    answers in a browser — for two renders that between them exercise every
    `.dfoot` line in the template, including both new `.c`-chip lines
    (identity refusals and identity disclosures).
    """
    import jinja2
    from bs4 import BeautifulSoup

    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(REPO / "templates")),
        undefined=jinja2.ChainableUndefined,
    )
    tmpl = env.get_template("ticker.html.j2")

    # golden MSFT: identity.disclosures present (dfoot line ~1933), identity
    # PROVEN so identity.refusals is empty (dfoot line ~1932 does not render
    # at all — proving the `{% if %}` guard, not merely the CSS selector).
    fixture = REPO / "tests" / "fixtures" / "security_state" / "golden_msft_expected_output.json"
    msft_state = json.loads(fixture.read_text(encoding="utf-8"))
    msft_view = build_security_state({"security_state": msft_state})
    assert msft_view is not None

    # A BLOCKED shell with both refusals and disclosures present renders the
    # remaining `.c`-chip dfoot line (~1932) too.
    blocked_contract = _contract(identity_proof={
        "state": "BLOCKED_IDENTITY_BRIDGE", "method": "owner_backed_chain.v1",
        "legs": [], "equalities": [],
        "refusals": ["COMPILER_FAILURE"],
        "disclosures": ["CIK_LEG_OWNER_BACKED_CURRENT_ONLY: some technical description"],
    })
    blocked_view = build_security_state({"security_state": blocked_contract})
    assert blocked_view is not None

    for label, view, expect_refusals_dfoot in (
        ("msft (disclosures only, no refusals)", msft_view, False),
        ("blocked shell (refusals + disclosures)", blocked_view, True),
    ):
        html = tmpl.render(security_state=view, ticker="MSFT", name="Microsoft Corp.")
        soup = BeautifulSoup(html, "html.parser")
        dfoots = soup.find_all(class_="dfoot")
        assert len(dfoots) >= 8, f"{label}: expected at least 8 static+dynamic .dfoot blocks, found {len(dfoots)}"

        carrying_ids = {id(d) for d in dfoots if d.find(class_="c") is not None}
        carrying = [d for d in dfoots if id(d) in carrying_ids]

        found_refusals_dfoot = any("Held back" in d.get_text() or "暂不呈现" in d.get_text() for d in carrying)
        found_disclosures_dfoot = any(
            d.find(class_="ss-id") is not None
            and "Held back" not in d.get_text() and "暂不呈现" not in d.get_text()
            for d in carrying
        )
        assert found_refusals_dfoot == expect_refusals_dfoot, (
            f"{label}: refusals .dfoot .c-chip presence = {found_refusals_dfoot}, expected {expect_refusals_dfoot}"
        )
        assert found_disclosures_dfoot, f"{label}: disclosures .dfoot .c-chip not found"
        # Structural scoping proof: every OTHER rendered .dfoot element (not
        # the refusals/disclosures lines just identified) carries NO
        # element with class "c" at all — so `.dfoot .c` cannot style them.
        expected_carrying_count = (1 if expect_refusals_dfoot else 0) + 1  # + disclosures
        assert len(carrying) == expected_carrying_count, (
            f"{label}: {len(carrying)} .dfoot blocks carry a .c descendant, "
            f"expected exactly {expected_carrying_count}: "
            f"{[d.get_text(' ', strip=True)[:60] for d in carrying]!r}"
        )
        for d in dfoots:
            if id(d) not in carrying_ids:
                assert d.find(class_="c") is None, (
                    f"{label}: an unaccounted .dfoot block unexpectedly carries a .c descendant: "
                    f"{d.get_text(' ', strip=True)[:80]!r}"
                )


def test_compiler_failure_gate_renders_a_plain_bilingual_sentence() -> None:
    """A ``COMPILER_FAILURE`` failed-gate must render a real, DISTINCT EN/ZH
    sentence — never the raw enum code duplicated into both language slots
    (Chairman plain-language law, 2026-09-06, macro#6920 round-2 ruling).

    Before the fix, ``COMPILER_FAILURE`` had no ``_SS_GATES`` house-copy
    entry, so both ``en`` and ``zh`` fell back to ``_ss_prettify(code)`` —
    the SAME English words in the field the page treats as Chinese. The raw
    machine code may still appear, but only inside the receipt's own
    ``ss-id`` chip, never as the sentence itself.
    """
    contract = _contract(dominant_degradation="COMPILER_FAILURE")
    contract["legs"]["risk"]["failed_gates"] = [
        {"code": "COMPILER_FAILURE",
         "reason": "security_state compiler failed after owner identity was composed"},
    ]
    view = build_security_state({"security_state": contract})
    assert view is not None

    gate = next(g for a in view["axes"] for g in a["gates"] if g["code"] == "COMPILER_FAILURE")
    assert gate["en"] != gate["zh"], (
        f"ZH slot must be real Chinese, not the English fallback duplicated: {gate!r}"
    )
    assert gate["en"] not in ("COMPILER_FAILURE", "Compiler failure"), (
        "must be a house plain sentence, not the raw code or its bare prettification"
    )
    # A real Chinese sentence contains CJK characters — a prettified English
    # fallback never does.
    assert re.search(r"[一-鿿]", gate["zh"]), f"zh is not Chinese: {gate['zh']!r}"

    import jinja2
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(REPO / "templates")),
        undefined=jinja2.ChainableUndefined,
    )
    html = env.get_template("ticker.html.j2").render(
        security_state=view, ticker="AAPL", name="Apple Inc.",
    )
    # The plain sentence must appear as visible prose …
    assert gate["en"] in html
    assert gate["zh"] in html
    # … and wherever the raw code still appears, it must be inside the
    # receipt's machine-id chip, never as a bare bilingual prose span.
    assert '<span class="l-en">COMPILER_FAILURE</span>' not in html
    assert '<span class="l-zh">COMPILER_FAILURE</span>' not in html


def test_identity_refusal_renders_a_plain_bilingual_sentence_not_the_raw_code() -> None:
    """``identity_proof.refusals`` is the M1/M2 failure-shell path

    (``engine.security_state.compile_security_state_failure``) — a DIFFERENT
    rendering path from ``legs.risk.failed_gates`` covered by
    ``test_compiler_failure_gate_renders_a_plain_bilingual_sentence`` above.
    Before this fix the "Held back" line rendered the raw refusal code
    (``COMPILER_FAILURE`` / ``IDENTITY_UNRESOLVED``) as bare, language-
    identical text inside a plain ``<div class="dfoot">`` — no ``ss-id``
    chip, no ``data-`` attribute — byte-identical in the EN and ZH views
    (macro#6920 round-2 MAJOR #2: the PR body's claim that the raw code
    "only appears inside the receipt's own ss-id machine-id chip" was false
    for this path).
    """
    for code in ("COMPILER_FAILURE", "IDENTITY_UNRESOLVED"):
        contract = _contract(identity_proof={
            "state": "BLOCKED_IDENTITY_BRIDGE", "method": "owner_backed_chain.v1",
            "legs": [], "equalities": [], "refusals": [code], "disclosures": [],
        })
        view = build_security_state({"security_state": contract})
        assert view is not None

        refusal = next(r for r in view["identity"]["refusals"] if r["code"] == code)
        assert refusal["en"] != refusal["zh"], (
            f"{code}: ZH slot must be real Chinese, not the English fallback duplicated: {refusal!r}"
        )
        assert refusal["en"] not in (code, _prettify_words(code)), (
            f"{code}: must be a house plain sentence, not the raw code or its bare prettification"
        )
        assert re.search(r"[一-鿿]", refusal["zh"]), f"{code}: zh is not Chinese: {refusal['zh']!r}"

        import jinja2
        env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(str(REPO / "templates")),
            undefined=jinja2.ChainableUndefined,
        )
        html = env.get_template("ticker.html.j2").render(
            security_state=view, ticker="MSFT", name="Microsoft Corp.",
        )  # both languages present, un-filtered
        # The plain sentence must appear as visible prose in BOTH languages.
        assert refusal["en"] in html, f"{code}: EN plain sentence missing from render"
        assert refusal["zh"] in html, f"{code}: ZH plain sentence missing from render"

        # The raw machine code, wherever it appears, must be inside the
        # receipt's own ss-id chip — never as bare, bilingual-identical text
        # sitting directly in the "Held back" line (what the PR body's round-2
        # claim asserted but did not test).
        m = re.search(r'Held back</span>.*?:(.*?)</div>', html, re.S)
        assert m is not None, f"{code}: 'Held back' line not found in render"
        held_back_html = m.group(1)
        assert f'<span class="c ss-id">{code}</span>' in held_back_html, (
            f"{code}: raw code must be inside the ss-id chip: {held_back_html!r}"
        )
        stripped = re.sub(r'<span class="c ss-id">.*?</span>', "", held_back_html)
        assert code not in stripped, (
            f"{code}: raw code leaked outside the ss-id chip: {stripped!r}"
        )
        # And explicitly: the raw code must never sit as its own bare
        # bilingual-label span (the exact failure the round-2 PR body missed).
        assert f'<span class="l-en">{code}</span>' not in html
        assert f'<span class="l-zh">{code}</span>' not in html


def test_identity_disclosure_renders_a_plain_bilingual_sentence_not_the_raw_code() -> None:
    """``identity_proof.disclosures`` is stored engine-side as "CODE:
    technical description" (see ``engine.security_state.DISCLOSURES`` and the
    M1 failure shell's own local list). Before this fix
    ``templates/ticker.html.j2`` rendered each raw string verbatim —
    machine-code prefix and all — identically in the EN and ZH views (macro
    #6920 round-3 MAJOR #2). The code must render only inside the receipt's
    ``ss-id`` chip, and the sentence must be real, distinct EN/ZH prose.
    """
    for code in (
        "PINNED_IDENTITY_NOT_OWNER_READ_THIS_CYCLE",
        "IDENTITY_BRIDGE_UNRESOLVED_THIS_CYCLE",
        "CIK_LEG_OWNER_BACKED_CURRENT_ONLY",
    ):
        contract = _contract(identity_proof={
            "state": "BLOCKED_IDENTITY_BRIDGE", "method": "owner_backed_chain.v1",
            "legs": [], "equalities": [], "refusals": [],
            "disclosures": [f"{code}: some technical description that must never reach the page"],
        })
        view = build_security_state({"security_state": contract})
        assert view is not None

        disclosure = next(d for d in view["identity"]["disclosures"] if d["code"] == code)
        assert disclosure["en"] != disclosure["zh"], (
            f"{code}: ZH slot must be real Chinese, not the English fallback duplicated: {disclosure!r}"
        )
        assert re.search(r"[一-鿿]", disclosure["zh"]), f"{code}: zh is not Chinese: {disclosure['zh']!r}"
        assert "some technical description" not in disclosure["en"], (
            f"{code}: the raw engine description must be replaced by house copy, not passed through"
        )

        import jinja2
        env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(str(REPO / "templates")),
            undefined=jinja2.ChainableUndefined,
        )
        html = env.get_template("ticker.html.j2").render(
            security_state=view, ticker="MSFT", name="Microsoft Corp.",
        )
        assert disclosure["en"] in html, f"{code}: EN plain sentence missing from render"
        assert disclosure["zh"] in html, f"{code}: ZH plain sentence missing from render"
        assert "some technical description" not in html, (
            f"{code}: raw engine disclosure text leaked into rendered markup"
        )

        # The raw machine code, wherever it appears, must be inside the
        # receipt's own ss-id chip — never as bare text sitting directly in
        # the disclosures line, and never duplicated into the ZH view.
        m = re.search(
            r'<div class="dfoot">((?:(?!</div>).)*?' + re.escape(code) + r'(?:(?!</div>).)*?)</div>',
            html, re.S,
        )
        assert m is not None, f"{code}: disclosure line containing the code not found in render"
        line_html = m.group(1)
        assert f'<span class="c ss-id">{code}</span>' in line_html, (
            f"{code}: raw code must be inside the ss-id chip: {line_html!r}"
        )
        stripped = re.sub(r'<span class="c ss-id">.*?</span>', "", line_html)
        assert code not in stripped, f"{code}: raw code leaked outside the ss-id chip: {stripped!r}"


def test_every_compile_path_refusal_code_has_house_copy_with_no_prettify_fallback() -> None:
    """`engine/security_state.py` emits eight distinct refusal codes on its
    compile path (`identity_proof.refusals`, both `compile_security_state`'s
    R1..R8 gates and `compile_security_state_failure`'s M1/M2 shells). Every
    one of them must have a `_SS_GATES` house-copy entry carrying a REAL,
    distinct EN/ZH sentence. The code set is extracted from the engine
    source by regex, not hand-copied, so this test cannot go stale silently
    if a new refusal code is added there without a matching entry here
    (macro#6920 round-3 review MAJOR-1).

    Before this fix, only two of the eight codes (`COMPILER_FAILURE`,
    `IDENTITY_UNRESOLVED`) had a `_SS_GATES` entry; the other six
    (`SECURITY_SUPERSEDED`, `ISSUER_GROUP_AMBIGUOUS`,
    `LISTING_KEY_INCOHERENT`, `IDENTITY_CORRECTED`,
    `SUBJECT_NATIVE_PARITY_FAILED`, `IDENTITY_BRIDGE_DISAGREEMENT`) fell
    through to `_ss_prettify(code)` for BOTH slots — the same English words
    duplicated into the field the page treats as Chinese.
    """
    from scripts.build_ticker_pages import _SS_GATES, _ss_prettify

    engine_src = (REPO / "engine" / "security_state.py").read_text()
    codes = set(re.findall(r'refusals\.append\("([A-Z][A-Z0-9_]*)"\)', engine_src))
    codes |= set(re.findall(r'"refusals":\s*\["([A-Z][A-Z0-9_]*)"\]', engine_src))
    assert codes == {
        "SECURITY_SUPERSEDED", "IDENTITY_UNRESOLVED", "ISSUER_GROUP_AMBIGUOUS",
        "LISTING_KEY_INCOHERENT", "IDENTITY_CORRECTED", "SUBJECT_NATIVE_PARITY_FAILED",
        "IDENTITY_BRIDGE_DISAGREEMENT", "COMPILER_FAILURE",
    }, (
        f"engine/security_state.py's emitted refusal-code set changed: {sorted(codes)} — "
        "this test's extraction regex and its house-copy coverage below must be updated together"
    )

    for code in sorted(codes):
        assert code in _SS_GATES, f"{code}: no _SS_GATES house-copy entry — falls through to _ss_prettify"
        entry = _SS_GATES[code]
        assert entry.get("en") and entry.get("zh"), f"{code}: house-copy entry has an empty slot: {entry!r}"
        assert entry["en"] != entry["zh"], (
            f"{code}: ZH slot is not real Chinese (duplicates the EN fallback): {entry!r}"
        )
        assert re.search(r"[一-鿿]", entry["zh"]), f"{code}: zh is not Chinese: {entry['zh']!r}"
        pretty = _ss_prettify(code)
        assert entry["en"] != pretty, (
            f"{code}: house copy is just the bare prettification of the code, not a real sentence"
        )

        # Exercise the real production mapping site
        # (`(_SS_GATES.get(code) or {}).get("en") or _ss_prettify(code)`) end
        # to end for every code, not just the dict — a present, non-empty
        # `_SS_GATES` entry makes the `_ss_prettify` branch unreachable for
        # this code, and this proves it by observing the actual output.
        contract = _contract(identity_proof={
            "state": "BLOCKED_IDENTITY_BRIDGE", "method": "owner_backed_chain.v1",
            "legs": [], "equalities": [], "refusals": [code], "disclosures": [],
        })
        view = build_security_state({"security_state": contract})
        assert view is not None
        refusal = next(r for r in view["identity"]["refusals"] if r["code"] == code)
        assert refusal["en"] == entry["en"] and refusal["zh"] == entry["zh"], (
            f"{code}: rendered refusal does not match its _SS_GATES house copy: {refusal!r}"
        )
        assert refusal["en"] != pretty, f"{code}: rendered refusal fell back to the bare prettification"


def _prettify_words(code: str) -> str:
    words = re.sub(r"[^0-9A-Za-z]+", " ", code).strip().lower()
    return (words[:1].upper() + words[1:]) if words else ""

