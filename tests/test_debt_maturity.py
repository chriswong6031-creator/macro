"""Tests for engine/debt_maturity.py (packet B-F09-3)."""
from __future__ import annotations

import ast
import json
import re
from datetime import date
from pathlib import Path

import pytest

from engine.debt_maturity import BUCKETS, extract_maturity_ladder

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "debt_maturity"
AAPL_CIK = "0000320193"


def _load(name: str) -> dict:
    return json.loads((FIXTURE_DIR / name).read_text())


def test_six_buckets_map_from_exact_tags():
    assert [b[0] for b in BUCKETS] == ["y1", "y2", "y3", "y4", "y5", "after5"]
    tags = [b[1] for b in BUCKETS]
    assert tags == [
        "LongTermDebtMaturitiesRepaymentsOfPrincipalInNextTwelveMonths",
        "LongTermDebtMaturitiesRepaymentsOfPrincipalInYearTwo",
        "LongTermDebtMaturitiesRepaymentsOfPrincipalInYearThree",
        "LongTermDebtMaturitiesRepaymentsOfPrincipalInYearFour",
        "LongTermDebtMaturitiesRepaymentsOfPrincipalInYearFive",
        "LongTermDebtMaturitiesRepaymentsOfPrincipalAfterYearFive",
    ]


def test_latest_annual_period_wins():
    facts = _load("aapl_trimmed.json")
    result = extract_maturity_ladder(facts, cik=AAPL_CIK, as_of=date(2025, 1, 1))
    assert result["period"]["form"] == "10-K"
    assert result["period"]["fp"] == "FY"
    assert result["period"]["end"] == "2024-09-28"


def test_buckets_never_mix_filings():
    facts = _load("aapl_trimmed.json")
    result = extract_maturity_ladder(facts, cik=AAPL_CIK, as_of=date(2025, 1, 1))
    y4 = next(b for b in result["buckets"] if b["key"] == "y4")
    assert y4["reported"] is False
    assert y4["drop_reason"] == "period_mismatch"
    # excluded from the total
    assert result["total_reported_usd"] == 11128000000 + 10912000000 + 0


def test_unit_not_usd_is_not_reported_not_zero():
    facts = _load("aapl_trimmed.json")
    result = extract_maturity_ladder(facts, cik=AAPL_CIK, as_of=date(2025, 1, 1))
    y3 = next(b for b in result["buckets"] if b["key"] == "y3")
    assert y3["usd"] is None
    assert y3["reported"] is False
    assert y3["drop_reason"] == "unit_not_usd"
    assert y3["display"] is None


def test_missing_bucket_is_null_not_zero():
    facts = _load("aapl_trimmed.json")
    result = extract_maturity_ladder(facts, cik=AAPL_CIK, as_of=date(2025, 1, 1))
    after5 = next(b for b in result["buckets"] if b["key"] == "after5")
    assert after5["usd"] is None
    assert after5["reported"] is False
    assert result["buckets_reported"] < result["buckets_total"]


def test_reported_zero_survives_as_zero():
    facts = _load("aapl_trimmed.json")
    result = extract_maturity_ladder(facts, cik=AAPL_CIK, as_of=date(2025, 1, 1))
    y5 = next(b for b in result["buckets"] if b["key"] == "y5")
    assert y5["reported"] is True
    assert y5["usd"] == 0
    assert y5["display"] == "$0"


def test_no_companyfacts_is_no_filings():
    result = extract_maturity_ladder(None, cik=AAPL_CIK)
    assert result["status"] == "no_filings"
    assert result["buckets"] == []


def test_facts_without_maturity_tags_is_no_maturity_facts():
    result = extract_maturity_ladder({"facts": {"us-gaap": {}}}, cik=AAPL_CIK)
    assert result["status"] == "no_maturity_facts"
    # META-CEO ruling round 2 (B2): "a filer that reports no maturity facts
    # renders each bucket 'not reported'" -- the null state is printed per
    # bucket, never hidden behind a single blanket sentence with no buckets.
    assert len(result["buckets"]) == len(BUCKETS)
    assert all(b["reported"] is False for b in result["buckets"])
    assert all(b["display"] is None and b["usd"] is None for b in result["buckets"])
    assert [b["key"] for b in result["buckets"]] == [b[0] for b in BUCKETS]


def test_identity_is_cik_only():
    facts = _load("aapl_trimmed.json")
    # the fixture carries its own "cik": 320193 (the real SEC companyfacts
    # shape always does) -- a caller-supplied CIK that does NOT canonicalize
    # to the same value must fail closed, never silently trust whichever
    # value happened to be passed in.
    result = extract_maturity_ladder(facts, cik="0000999999", as_of=date(2025, 1, 1))
    assert result["cik"] == "0000999999"
    assert result["status"] == "identity_mismatch"
    assert result["buckets"] == []
    # the matching CIK (any zero-padding) resolves normally.
    result_ok = extract_maturity_ladder(facts, cik=AAPL_CIK, as_of=date(2025, 1, 1))
    assert result_ok["status"] == "reported"
    with pytest.raises(ValueError):
        extract_maturity_ladder(facts, cik="AAPL")  # a ticker/name is not a CIK
    with pytest.raises(ValueError):
        extract_maturity_ladder(facts, cik="")


def test_unit_thousands_and_millions_scaled_to_dollars():
    tag = "LongTermDebtMaturitiesRepaymentsOfPrincipalInNextTwelveMonths"
    facts = {
        "cik": 999999,
        "facts": {"us-gaap": {tag: {"units": {"USDthousands": [
            {"end": "2024-12-31", "val": 1234, "accn": "0000999999-25-000001",
             "fy": 2024, "fp": "FY", "form": "10-K", "filed": "2025-02-01"},
        ]}}}},
    }
    result = extract_maturity_ladder(facts, cik="0000999999", as_of=date(2025, 3, 1))
    y1 = next(b for b in result["buckets"] if b["key"] == "y1")
    assert y1["reported"] is True
    assert y1["usd"] == 1234 * 1000

    tag2 = "LongTermDebtMaturitiesRepaymentsOfPrincipalInYearTwo"
    facts_m = {
        "cik": 999999,
        "facts": {"us-gaap": {tag2: {"units": {"USDmillions": [
            {"end": "2024-12-31", "val": 5, "accn": "0000999999-25-000001",
             "fy": 2024, "fp": "FY", "form": "10-K", "filed": "2025-02-01"},
        ]}}}},
    }
    result_m = extract_maturity_ladder(facts_m, cik="0000999999", as_of=date(2025, 3, 1))
    y2 = next(b for b in result_m["buckets"] if b["key"] == "y2")
    assert y2["reported"] is True
    assert y2["usd"] == 5 * 1_000_000


def test_as_of_is_never_defaulted_from_the_clock():
    # no as_of supplied at all -- purity means this must not consult a clock;
    # the field is simply omitted (None) rather than silently stamped "today".
    result = extract_maturity_ladder(None, cik=AAPL_CIK)
    assert result["as_of"] is None
    facts = _load("aapl_trimmed.json")
    result2 = extract_maturity_ladder(facts, cik=AAPL_CIK)
    assert result2["as_of"] is None
    assert result2["period"]["stale"] is False  # no as_of -> never asserts staleness


def test_module_is_pure():
    src = Path("engine/debt_maturity.py").read_text()
    tree = ast.parse(src)
    banned_calls = {"open", "urlopen"}
    banned_attrs = {"now", "today", "read_csv", "read_parquet"}
    banned_modules = {"requests", "urllib", "pandas"}

    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [n.name for n in node.names]
            mod = getattr(node, "module", None)
            for m in list(names) + ([mod] if mod else []):
                assert m not in banned_modules, f"forbidden import: {m}"
        if isinstance(node, ast.Call):
            fn = node.func
            if isinstance(fn, ast.Name) and fn.id in banned_calls:
                pytest.fail(f"forbidden call at module scope: {fn.id}")
            if isinstance(fn, ast.Attribute) and fn.attr in banned_attrs:
                pytest.fail(f"forbidden call: {fn.attr}")
    assert "Path(" not in src.replace("# noqa", "")


def test_glance_tier_has_no_machine_text():
    tmpl_path = Path("templates/_debt_maturity.html.j2")
    src = tmpl_path.read_text()
    banned = ["us-gaap", "LongTermDebtMaturities", "accn", "XBRL", "frame"]
    # split at the <details> boundary; everything before/around it minus the
    # details block itself must be free of raw machine vocabulary.
    m = re.search(r"<details.*?</details>", src, re.DOTALL)
    assert m, "expected a <details> disclosure block"
    outside = src[: m.start()] + src[m.end():]
    for term in banned:
        assert term not in outside, f"banned term {term!r} leaked outside <details>"
    inside = m.group(0)
    # the banned vocabulary should actually be reachable inside the details
    assert "accn" in inside


def test_en_zh_parity():
    src = Path("templates/_debt_maturity.html.j2").read_text()
    calls = re.findall(r"\bt\(([^()]*(?:\([^()]*\)[^()]*)*)\)", src)
    assert calls, "expected t() calls in the partial"
    for args in calls:
        # split on the top-level comma (args may themselves contain '~' concatenation
        # but never nested parens at this point since the regex already balanced those)
        depth = 0
        top_commas = 0
        for ch in args:
            if ch in "([":
                depth += 1
            elif ch in ")]":
                depth -= 1
            elif ch == "," and depth == 0:
                top_commas += 1
        assert top_commas >= 1, f"t() call missing a zh arg: {args!r}"


def test_no_translated_title_attribute():
    src = Path("templates/_debt_maturity.html.j2").read_text()
    assert "title=" not in src


def test_resolve_cik_handles_float64_parquet_column(monkeypatch, tmp_path):
    import types
    import sys as _sys
    import scripts.build_debt_maturity as bdm

    monkeypatch.setattr(bdm, "_cik_ledger_path", lambda: tmp_path / "absent.json")

    class _FakeRow(dict):
        def get(self, key, default=None):
            return dict.get(self, key, default)

    class _FakeFrame:
        columns = ["ticker", "cik"]
        empty = False

        def __getitem__(self, _expr):
            return self

        def astype(self, _t):
            return self

        @property
        def str(self):
            return self

        def upper(self):
            return self

        def __eq__(self, _other):
            return self

        @property
        def iloc(self):
            return [_FakeRow(cik=320193.0)]

    fake_pd = types.SimpleNamespace(read_parquet=lambda _p: _FakeFrame())
    monkeypatch.setitem(_sys.modules, "pandas", fake_pd)
    monkeypatch.setattr(bdm, "_issuer_master_path", lambda: Path(__file__))

    cik = bdm.resolve_cik("AAPL")
    assert cik == "0000320193"


def test_stock_page_wiring():
    ticker_tmpl = Path("templates/ticker.html.j2").read_text()
    assert '{% include "_debt_maturity.html.j2" %}' in ticker_tmpl
    assert 'id="debt-maturity"' in Path("templates/_debt_maturity.html.j2").read_text()
    assert '#debt-maturity' in ticker_tmpl
    build_pages_src = Path("scripts/build_ticker_pages.py").read_text()
    assert '"debt_maturity"' in build_pages_src


def test_sections_gate_ignores_null_panel():
    import scripts.build_ticker_pages as btp

    # use a non-empty base blob (any truthy blob already contributes its own
    # +1 in sections_available) so the debt_maturity-specific delta is isolated
    agg = {"intel_map": {}, "news_map": {}}
    base_blob = {"_marker": True}
    base = btp.sections_available(base_blob, {}, agg, "TEST")

    for status in ("no_filings", "no_maturity_facts", "not_applicable", "identity_mismatch", "not_loaded"):
        blob = dict(base_blob, debt_maturity={"status": status})
        with_null = btp.sections_available(blob, {}, agg, "TEST")
        assert with_null == base, f"status={status} unexpectedly added to the gate"

    reported_blob = dict(base_blob, debt_maturity={"status": "reported"})
    with_reported = btp.sections_available(reported_blob, {}, agg, "TEST")
    assert with_reported == base + 1


# ============================================================================
# META-CEO ruling round 2 (2026-09-06), packet B-F09-3 — B1/B2/B3/B4 repair.
# ============================================================================

def test_cache_miss_is_not_loaded(monkeypatch, tmp_path):
    """B2: a CIK that resolved but was never fetched is 'not_loaded', never a
    fabricated 'no_filings' negative."""
    import scripts.build_debt_maturity as bdm

    monkeypatch.setattr(bdm, "_cache_dir", lambda: tmp_path / "cache")
    monkeypatch.setattr(bdm, "resolve_cik", lambda ticker: "0000320193")
    cik, facts, state = bdm.load_debt_maturity_facts("AAPL")
    assert cik == "0000320193"
    assert facts is None
    assert state == "not_loaded"


def test_unresolved_ticker_is_unresolved(monkeypatch):
    import scripts.build_debt_maturity as bdm

    monkeypatch.setattr(bdm, "resolve_cik", lambda ticker: None)
    cik, facts, state = bdm.load_debt_maturity_facts("ZZZZZNOPE")
    assert cik is None
    assert facts is None
    assert state == "unresolved"


def test_refresh_wired_mode_confirmed_absent_writes_confirmed_no_filings(tmp_path, monkeypatch):
    """B2: the wired call mode (an already-fetched full companyfacts document
    supplied by the caller) records a positive 'confirmed_no_filings' cache
    entry when the caller explicitly passes None -- this is what lets
    load_debt_maturity_facts hand the engine a real 'no_filings' status
    instead of a blanket not_loaded."""
    import scripts.build_debt_maturity as bdm

    monkeypatch.setattr(bdm, "_cache_dir", lambda: tmp_path / "cache")
    ok = bdm.refresh_cache_for_cik("0000999999", full_companyfacts=None)
    assert ok is True
    cached = bdm.load_cached_facts("0000999999")
    assert cached is not None
    assert cached.get("confirmed_no_filings") is True
    assert cached.get("fetched_at")


def test_refresh_wired_mode_slims_tags_from_full_companyfacts(tmp_path, monkeypatch):
    """B2/efficiency: the wired mode never makes its own network call -- it
    slims the six bounded tags out of a full companyfacts document the
    caller already fetched (collectors/edgar_facts.py's own per-issuer
    companyfacts fetch)."""
    import scripts.build_debt_maturity as bdm

    monkeypatch.setattr(bdm, "_cache_dir", lambda: tmp_path / "cache")
    facts = _load("aapl_trimmed.json")
    ok = bdm.refresh_cache_for_cik("0000320193", full_companyfacts=facts)
    assert ok is True
    cached = bdm.load_cached_facts("0000320193")
    assert cached is not None
    assert not cached.get("confirmed_no_filings")
    assert cached["cik"] == 320193
    # only the six bounded tags may appear -- never the full companyfacts blob.
    assert set(cached["facts"]["us-gaap"]) <= {t[1] for t in BUCKETS}
    tag = "LongTermDebtMaturitiesRepaymentsOfPrincipalInNextTwelveMonths"
    assert tag in cached["facts"]["us-gaap"]


def test_loaded_state_after_wired_refresh_reaches_reported(tmp_path, monkeypatch):
    import scripts.build_debt_maturity as bdm

    monkeypatch.setattr(bdm, "_cache_dir", lambda: tmp_path / "cache")
    monkeypatch.setattr(bdm, "resolve_cik", lambda ticker: AAPL_CIK)
    facts = _load("aapl_trimmed.json")
    assert bdm.refresh_cache_for_cik(AAPL_CIK, full_companyfacts=facts) is True
    cik, cached_facts, state = bdm.load_debt_maturity_facts("AAPL")
    assert state == "loaded"
    result = extract_maturity_ladder(cached_facts, cik=cik, as_of=date(2025, 1, 1))
    assert result["status"] == "reported"


def test_confirmed_no_filings_state_reaches_engine_no_filings(tmp_path, monkeypatch):
    import scripts.build_debt_maturity as bdm

    monkeypatch.setattr(bdm, "_cache_dir", lambda: tmp_path / "cache")
    monkeypatch.setattr(bdm, "resolve_cik", lambda ticker: "0000999999")
    assert bdm.refresh_cache_for_cik("0000999999", full_companyfacts=None) is True
    cik, cached_facts, state = bdm.load_debt_maturity_facts("NOFILE")
    assert state == "confirmed_no_filings"
    assert cached_facts is None
    # this is exactly how scripts/build_stock_library.py's call site derives
    # the engine's own "no_filings" status: pass None through, never invent
    # the status string a second time.
    result = extract_maturity_ladder(None, cik=cik, as_of=date(2025, 1, 1))
    assert result["status"] == "no_filings"


def test_refresh_standalone_mode_total_network_failure_never_overwrites_cache(tmp_path, monkeypatch):
    """Standalone mode (no full_companyfacts kwarg): a total per-CIK network
    failure across every tag must leave any existing cache untouched and
    return False -- never confirm a false negative from a network blip."""
    import scripts.build_debt_maturity as bdm

    cache_dir = tmp_path / "cache"
    monkeypatch.setattr(bdm, "_cache_dir", lambda: cache_dir)

    class _DeadSession:
        def get(self, *a, **k):
            raise ConnectionError("network down")

    # seed an existing real cache entry first
    cache_dir.mkdir(parents=True)
    (cache_dir / "CIK0000999999.json").write_text('{"cik": 999999, "facts": {"us-gaap": {}}}')
    before = bdm.load_cached_facts("0000999999")

    ok = bdm.refresh_cache_for_cik("0000999999", session=_DeadSession())
    assert ok is False
    after = bdm.load_cached_facts("0000999999")
    assert after == before  # untouched


def test_refresh_standalone_mode_all_404_writes_confirmed_no_filings(tmp_path, monkeypatch):
    """Standalone mode: every tag request completing (even as a clean 404)
    is a genuine round trip and must write a confirmed cache entry, distinct
    from the total-failure case above."""
    import scripts.build_debt_maturity as bdm

    monkeypatch.setattr(bdm, "_cache_dir", lambda: tmp_path / "cache")

    class _Resp:
        status_code = 404

    class _AllNotFoundSession:
        def get(self, *a, **k):
            return _Resp()

    ok = bdm.refresh_cache_for_cik("0000999999", session=_AllNotFoundSession())
    assert ok is True
    cached = bdm.load_cached_facts("0000999999")
    assert cached.get("confirmed_no_filings") is True


def test_nightly_wiring_call_site_and_registration():
    """B1: refresh_cache_for_cik is called for every issuer
    collectors/edgar_facts.py already companyfacts-fetches (the same universe
    the stock library builds), and the nightly registration line (a real
    cron schedule) exists for it -- never a network call on the render path
    (build_stock_library.py / build_ticker_pages.py never import the
    collector)."""
    edgar_facts_src = Path("collectors/edgar_facts.py").read_text()
    assert "from scripts.build_debt_maturity import refresh_cache_for_cik" in edgar_facts_src
    # a real call, not merely the import line
    assert edgar_facts_src.count("refresh_cache_for_cik(") >= 2

    workflow_src = Path(".github/workflows/debt-maturity-drip.yml").read_text()
    assert re.search(r"cron:\s*[\"']", workflow_src), "expected a real cron schedule line"
    assert "backfill_edgar_flow" in workflow_src

    for render_path in ("scripts/build_stock_library.py", "scripts/build_ticker_pages.py"):
        src = Path(render_path).read_text()
        assert "collectors.edgar_facts" not in src
        assert "refresh_cache_for_cik" not in src, (
            f"{render_path} must read the cache, never refresh it on the render path"
        )


def test_no_inline_style_in_partial():
    """B3: the inline <style> block is a design-system bypass — it must live
    in templates/theme.css (governed CSS), not the partial."""
    src = Path("templates/_debt_maturity.html.j2").read_text()
    assert "<style" not in src


def test_theme_css_owns_debt_maturity_rules():
    src = Path("templates/theme.css").read_text()
    assert "debt maturity ladder" in src
    assert ".dmw{" in src or ".dmw {" in src
    assert '[data-theme="light"] .dmr' in src


# ---------------------------------------------------------------------------
# Real Jinja renders of the partial (M4 — the prior suite only regex-scanned
# the template source; these actually render it for every status).
# ---------------------------------------------------------------------------

def _render_partial(debt_maturity: dict) -> str:
    from jinja2 import Environment, FileSystemLoader

    from engine import i18n

    env = Environment(loader=FileSystemLoader("templates"), autoescape=True)
    env.globals["t"] = i18n.t
    tmpl = env.get_template("_debt_maturity.html.j2")
    return tmpl.render(debt_maturity=debt_maturity)


def test_render_reported_status():
    facts = _load("aapl_trimmed.json")
    result = extract_maturity_ladder(facts, cik=AAPL_CIK, as_of=date(2025, 1, 1))
    html = _render_partial(result)
    assert 'id="debt-maturity"' in html
    assert "Debt coming due" in html
    assert result["total_display"] in html
    assert "not reported" in html  # the unit_not_usd/period_mismatch buckets


def test_render_no_filings_status():
    html = _render_partial({"schema": "debt_maturity.v1", "status": "no_filings", "cik": "0000999999",
                            "buckets": [], "total_reported_usd": None, "total_display": None,
                            "near_share_pct": None, "buckets_reported": 0, "buckets_total": 6, "as_of": None})
    assert "No SEC filings available for this listing." in html
    assert "没有可用" not in html  # sanity: not accidentally emitting a different ZH string
    assert "该证券暂无可用的 SEC 文件" in html
    assert "Debt schedule not loaded yet." not in html


def test_render_not_loaded_status_is_distinct_from_no_filings():
    html = _render_partial({"schema": "debt_maturity.v1", "status": "not_loaded", "cik": "0000320193",
                            "buckets": [], "total_reported_usd": None, "total_display": None,
                            "near_share_pct": None, "buckets_reported": 0, "buckets_total": 6, "as_of": None})
    assert "Debt schedule not loaded yet." in html
    assert "到期债务尚未加载" in html
    assert "No SEC filings available" not in html


def test_render_no_maturity_facts_shows_every_bucket_not_reported():
    result = extract_maturity_ladder({"cik": 999999, "facts": {"us-gaap": {}}}, cik="0000999999", as_of=date(2025, 1, 1))
    assert result["status"] == "no_maturity_facts"
    html = _render_partial(result)
    # every one of the six bucket labels appears, each marked not reported —
    # never a single blanket sentence hiding the per-bucket null.
    assert html.count("not reported") == len(BUCKETS)
    for _key, _tag, en, _zh in BUCKETS:
        assert en in html


def test_render_identity_mismatch_is_not_an_empty_panel():
    """B4: identity_mismatch must never render an empty panel between the
    header and the research-only footer."""
    result = extract_maturity_ladder(_load("aapl_trimmed.json"), cik="0000999999", as_of=date(2025, 1, 1))
    assert result["status"] == "identity_mismatch"
    html = _render_partial(result)
    assert "We could not confirm which company filed for this listing, so the debt schedule is not shown." in html
    assert "我们无法确认是哪家公司为该证券提交了文件" in html
    # the research-only footer still renders (it is outside the status branch)
    assert "Research context only" in html
    # the panel is not literally empty between the header close and footer open
    hd_end = html.index("</div>", html.index("mod-hd"))
    ft_start = html.index('class="mod-ft"')
    body = html[hd_end:ft_start].strip()
    assert body, "identity_mismatch rendered an empty panel body"
