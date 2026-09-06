"""Tests for engine/special_situations_premium.py (packet B-F09-4).

No network, no `data/` reads — every fixture is self-contained under
tests/fixtures/special_situations/premium_*.json.
"""
from __future__ import annotations

import inspect
import json
import re
from pathlib import Path

import pandas as pd
import pytest

from engine import special_situations_premium as prem

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "special_situations"


def _load(name: str) -> dict:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


def _closes_series(closes: dict) -> pd.Series:
    idx = pd.to_datetime(list(closes.keys()))
    s = pd.Series(list(closes.values()), index=idx).sort_index()
    return s


def _run_fixture(name: str) -> dict:
    fx = _load(name)
    closes = _closes_series(fx["closes"])
    return prem.premium_for_event(
        fx["event"], closes=closes, lifecycle_row=fx["lifecycle_row"],
        ledger=fx["ledger"], asof="2026-09-06 00:00 UTC")


def test_premium_is_anchored_to_the_announcement_not_the_filing_being_read():
    row = _run_fixture("premium_computed_deal.json")
    assert row["status"] == "computed"
    # first_date is 2026-06-02; the trading day strictly before it in the fixture is
    # 2026-06-01 ... but 2026-06-01 is not itself in the series -> nearest is 2026-05-30
    # via a 1-row lag from the searchsorted position. Assert the anchor is NOT the
    # filing-being-read's own 30-rows-back value (2026-05-20, which is what a
    # filing-anchored proxy on date_filed=2026-09-04 would return).
    assert row["unaffected_price_date"] != "2026-05-20"
    assert row["announcement_filing_date"] == "2026-06-02"
    filing_anchored_price = 21.50  # the 30-rows-back-from-date_filed value in this fixture
    assert row["unaffected_price"] != filing_anchored_price


def test_computed_premium_names_and_dates_every_input():
    row = _run_fixture("premium_computed_deal.json")
    for key in ("offer_price", "offer_accession", "offer_filing_date", "offer_form_type",
                "announcement_filing_date", "unaffected_price", "unaffected_price_date",
                "amendment_vintage", "currency", "source_url"):
        assert row.get(key) not in (None, ""), f"missing/blank {key}"


def test_absent_offer_terms_refuses_in_plain_words():
    row = _run_fixture("premium_terms_absent.json")
    assert row["status"] == "refused"
    assert row["refusal"] == "offer_terms_absent"
    assert "premium_pct" not in row
    assert row["null_en"]
    assert row["null_zh"]


def test_issuer_join_is_cik_only():
    params = inspect.signature(prem.resolve_issuer).parameters
    assert "company" not in params
    assert set(params) == {"cik", "ledger"}
    # the join body never reads event["company"]/["name"] — it only compares the ledger's
    # CIK values against the supplied cik.
    join_body = "\n".join(inspect.getsource(prem.resolve_issuer).splitlines()[1:])
    assert '"company"' not in join_body and "'company'" not in join_body
    assert '.get("company"' not in join_body
    with pytest.raises(prem.PremiumRefusal) as exc:
        prem.resolve_issuer("not-a-cik", ledger={"SMTI": 714256})
    assert exc.value.reason == "issuer_join_unresolved"


def test_ambiguous_cik_refuses_rather_than_picking_a_share_class():
    row = _run_fixture("premium_join_ambiguous.json")
    assert row["status"] == "refused"
    assert row["refusal"] == "issuer_join_ambiguous"


def test_announcement_before_price_coverage_refuses():
    row = _run_fixture("premium_no_unaffected.json")
    assert row["status"] == "refused"
    assert row["refusal"] == "unaffected_price_unavailable"


def test_module_is_display_only():
    assert prem.SCORED is False
    src = inspect.getsource(prem)
    assert not re.search(r"^\s*(from|import)\s+.*\b(conditions|regime|run)\b", src, re.M)
    banned = re.compile(r"\b(rank|score|expected_return|annualized|signal|target|position|size|edge)\b")
    for name in ("premium_computed_deal", "premium_terms_absent",
                 "premium_join_ambiguous", "premium_no_unaffected"):
        row = _run_fixture(f"{name}.json")
        assert not any(banned.search(str(k)) for k in row.keys())


def test_rights_gated_concepts_are_absent():
    src = inspect.getsource(prem)
    assert not re.search(r"break_fee|financing|antitrust|hsr", src, re.I)
    for name in ("premium_computed_deal", "premium_terms_absent",
                 "premium_join_ambiguous", "premium_no_unaffected"):
        row = _run_fixture(f"{name}.json")
        blob = json.dumps(row)
        assert not re.search(r"break_fee|financing|antitrust|hsr", blob, re.I)


def test_refusal_enum_is_closed():
    for name in ("premium_terms_absent", "premium_join_ambiguous", "premium_no_unaffected"):
        row = _run_fixture(f"{name}.json")
        assert row["refusal"] in prem.REFUSALS
    with pytest.raises(ValueError):
        prem.PremiumRefusal("not_a_real_reason")


def test_snapshot_contract_is_extended_not_forked(monkeypatch):
    from engine import special_situations as ss

    monkeypatch.setattr(ss, "build_situations", lambda: pd.DataFrame())
    snap = ss.snapshot()
    assert snap["scored"] is False
    assert snap["is_context_only"] is True
    assert "disclaimer" in snap
    assert "counts" in snap and "coverage" in snap and "situations" in snap
    assert "premium" in snap


def test_receipt_round_trips_the_template_contract(tmp_path, monkeypatch):
    fx = _load("premium_computed_deal.json")
    expected = prem.premium_for_event(
        fx["event"], closes=_closes_series(fx["closes"]), lifecycle_row=fx["lifecycle_row"],
        ledger=fx["ledger"], asof="2026-09-06 00:00 UTC")
    monkeypatch.setattr(prem, "featured_premium", lambda: expected)
    target = tmp_path / "premium_featured.json"
    out = prem.write_receipt(target)
    assert out == target
    from scripts.build_capital_structure_page import _featured_premium
    root = tmp_path
    (root / "data" / "special_situations").mkdir(parents=True, exist_ok=True)
    (root / "data" / "special_situations" / "premium_featured.json").write_text(
        target.read_text(encoding="utf-8"), encoding="utf-8")
    payload = _featured_premium(root)
    assert payload["schema"] == "special_situations.premium.v1"
    assert payload["ticker"] == expected["ticker"]


def test_desk_shell_renders_the_premium_block_in_both_languages(tmp_path):
    from jinja2 import Environment, FileSystemLoader, StrictUndefined
    repo_root = Path(__file__).parent.parent
    env = Environment(loader=FileSystemLoader(str(repo_root / "templates")),
                       autoescape=True, undefined=StrictUndefined)
    fx = _load("premium_computed_deal.json")
    premium = prem.premium_for_event(
        fx["event"], closes=_closes_series(fx["closes"]), lifecycle_row=fx["lifecycle_row"],
        ledger=fx["ledger"], asof="2026-09-06 00:00 UTC")
    html = env.get_template("capital_structure.html.j2").render(
        active_section="research", active_page="capital_structure", premium=premium)
    assert 'id="cs-premium"' in html
    assert premium["unaffected_price_date"] in html
    assert premium["announcement_filing_date"] in html
    assert f"{premium['premium_pct']:+.1f}%" in html
    assert "<style" not in html
    css = (repo_root / "templates" / "capital_structure.css").read_text(encoding="utf-8")
    block = html.split('id="cs-premium"')[1]
    for cls in re.findall(r'class="([^"]+)"', block):
        for token in cls.split():
            if token.startswith("cs-"):
                assert f".{token}" in css, f"class {token} not defined in capital_structure.css"


def test_desk_shell_renders_without_a_receipt():
    from jinja2 import Environment, FileSystemLoader, StrictUndefined
    repo_root = Path(__file__).parent.parent
    env = Environment(loader=FileSystemLoader(str(repo_root / "templates")),
                       autoescape=True, undefined=StrictUndefined)
    html = env.get_template("capital_structure.html.j2").render(
        active_section="research", active_page="capital_structure")
    assert "No deal is ready to show right now." in html


def test_builder_tolerates_a_missing_or_corrupt_receipt(tmp_path):
    from scripts.build_capital_structure_page import _featured_premium
    assert _featured_premium(tmp_path) is None
    d = tmp_path / "data" / "special_situations"
    d.mkdir(parents=True)
    (d / "premium_featured.json").write_text("not json", encoding="utf-8")
    assert _featured_premium(tmp_path) is None
    (d / "premium_featured.json").write_text(json.dumps({"schema": "wrong"}), encoding="utf-8")
    assert _featured_premium(tmp_path) is None
