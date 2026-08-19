"""Tests for scripts/check_stock_dossier_integrity.py — the post-render
machine-sentinel estate guard.

Covers the shape verified against the real committed tree while building this
guard: it must flag exactly the pages grep finds carrying "$nan" (69 of 2066
on the tree this PR was built against), it must not flag a clean page, it
must not flag the word "nan" appearing legitimately in prose (nan bread), and
it must catch a NaN token leaking into a page's JSON-LD payload (the shape
Python's json module emits for a literal NaN float).
"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from scripts.check_stock_dossier_integrity import (  # noqa: E402
    check_machine_sentinel,
    main,
    prepare_checkable_text,
    scan,
)


def _write_page(site_root: Path, name: str, html: str) -> Path:
    stocks_dir = site_root / "stocks"
    stocks_dir.mkdir(parents=True, exist_ok=True)
    page = stocks_dir / name
    page.write_text(html, encoding="utf-8")
    return page


def test_dollar_nan_m_is_flagged(tmp_path):
    _write_page(
        tmp_path, "BAD.html",
        '<html><body><div class="peers">'
        '<a class="pcard"><b>XYZ</b><span>Widget Co</span>'
        '<small class="num">$nanM</small></a>'
        '</div></body></html>',
    )
    scanned, violations = scan(tmp_path)
    assert scanned == 1
    assert len(violations) == 1
    assert violations[0]["page"] == "BAD.html"
    assert violations[0]["check"] == "machine_sentinel"
    assert "$nanM" in violations[0]["snippet"]


def test_clean_page_is_not_flagged(tmp_path):
    _write_page(
        tmp_path, "CLEAN.html",
        '<html><body><div class="peers">'
        '<a class="pcard"><b>XYZ</b><span>Widget Co</span>'
        '<small class="num">$12B</small></a>'
        '</div><p>Revenue grew 12% year over year.</p>'
        '</body></html>',
    )
    scanned, violations = scan(tmp_path)
    assert scanned == 1
    assert violations == []


def test_prose_word_nan_is_not_flagged(tmp_path):
    """'nan' (lowercase, bare) is the English word for a flatbread and shows
    up in ordinary prose ('nan bread') — it must never be flagged, unlike the
    '$'-prefixed sentinels or the exact mixed-case NaN token."""
    _write_page(
        tmp_path, "PROSE.html",
        '<html><body><p>The company signed a distribution deal for nan bread '
        "across grocery chains, and its founder's grandmother, Nan, still "
        "reviews every recipe.</p></body></html>",
    )
    scanned, violations = scan(tmp_path)
    assert scanned == 1
    assert violations == []


def test_json_ld_nan_is_flagged(tmp_path):
    """Python's json.dumps emits a bare, non-standard NaN token for a NaN
    float — exactly the shape that would leak into identity metadata."""
    _write_page(
        tmp_path, "LD.html",
        '<html><head>'
        '<script type="application/ld+json">'
        '{"@type": "Corporation", "name": "Widget Co", "marketCap": NaN}'
        '</script>'
        '</head><body><p>All clean here.</p></body></html>',
    )
    scanned, violations = scan(tmp_path)
    assert scanned == 1
    assert len(violations) == 1
    assert violations[0]["pattern"] == "NaN"
    assert "NaN" in violations[0]["snippet"]


def test_non_ld_json_script_is_stripped(tmp_path):
    """A NaN-shaped token inside an ordinary (non-JSON-LD) <script> block must
    not be flagged — that block is application logic, not a rendered value,
    and stripping it is what keeps this guard from false-positiving on JS
    source that happens to mention NaN (e.g. `if (Number.isNaN(x))`)."""
    _write_page(
        tmp_path, "SCRIPT.html",
        '<html><body>'
        '<script>if (Number.isNaN(x)) { console.log("NaN spotted"); }</script>'
        '<p>All clean here.</p>'
        '</body></html>',
    )
    scanned, violations = scan(tmp_path)
    assert scanned == 1
    assert violations == []


def test_style_block_is_stripped(tmp_path):
    """A <style> block is never a rendered value; a coincidental keyword
    collision there (e.g. a font literally named "Infinity") must not fire."""
    _write_page(
        tmp_path, "STYLE.html",
        '<html><head><style>.foo { font-family: "Infinity"; }</style></head>'
        '<body><p>All clean here.</p></body></html>',
    )
    scanned, violations = scan(tmp_path)
    assert scanned == 1
    assert violations == []


def test_infinity_and_inf_are_flagged(tmp_path):
    _write_page(
        tmp_path, "INF.html",
        '<html><body><p>Growth rate: Infinity</p>'
        '<p>Ratio: inf</p></body></html>',
    )
    scanned, violations = scan(tmp_path)
    assert scanned == 1
    patterns = sorted(v["pattern"] for v in violations)
    assert patterns == ["Infinity", "inf"]


def test_prepare_checkable_text_keeps_ld_json_drops_other_scripts():
    html = (
        '<style>.x{color:red}</style>'
        '<script>var x = 1;</script>'
        '<script type="application/ld+json">{"a": 1}</script>'
        '<p>hello</p>'
    )
    text = prepare_checkable_text(html)
    assert "color:red" not in text
    assert "var x = 1" not in text
    assert '{"a": 1}' in text
    assert "hello" in text


def test_check_machine_sentinel_reports_page_name():
    page = Path("site/stocks/FAKE.html")
    violations = check_machine_sentinel(page, "some $nanM text", {})
    assert violations
    assert violations[0]["page"] == "FAKE.html"


def test_main_exits_nonzero_on_violation(tmp_path, capsys):
    _write_page(tmp_path, "BAD.html", '<html><body>$nanM</body></html>')
    code = main([str(tmp_path)])
    out = capsys.readouterr().out
    assert code == 1
    assert "FAIL" in out
    assert "::error title=stock-dossier-integrity::" in out


def test_main_exits_zero_on_clean_tree(tmp_path, capsys):
    _write_page(tmp_path, "OK.html", '<html><body>$12B</body></html>')
    code = main([str(tmp_path)])
    out = capsys.readouterr().out
    assert code == 0
    assert "OK" in out


# --- identity class ----------------------------------------------------------
# The dossier estate is public and crawlable. A shared identity mistake is a
# distribution-scale misinformation problem, not a one-page visual defect, so the
# release gate must audit WHO each page says it is — against the stock hub the same
# run produced, and against the page's own structured data.

from scripts.check_stock_dossier_integrity import (  # noqa: E402
    check_identity,
    load_canonical_universe,
)

_HUB = '''<!doctype html><html><body><script>
const ROWS = [["RWT", "Redwood Trust Inc", "Real Estate", 4.77],
              ["RMD", "ResMed", "Health Care", 33.1],
              ["AAPL", "Apple Inc.", "Tech", 3200.0]];
</script></body></html>'''


def _page_html(ticker, issuer, sector, *, provenance=None, conflict=None,
               jsonld_name=None, jsonld_ticker=None, title=None):
    head = [f'<title>{title or (ticker + " — " + issuer)}</title>',
            f'<meta name="mm:ticker" content="{ticker}">',
            f'<meta name="mm:issuer" content="{issuer}">',
            f'<meta name="mm:sector" content="{sector}">']
    if conflict:
        head.append(f'<meta name="mm:sector-conflict" content="{conflict}">')
    if provenance:
        head.append(f'<meta name="mm:desc-provenance" content="{provenance}">')
    ld = ""
    if jsonld_name or jsonld_ticker:
        ld = ('<script type="application/ld+json">{"@type":"Corporation",'
              f'"name":"{jsonld_name or issuer}",'
              f'"tickerSymbol":"{jsonld_ticker or ticker}"}}</script>')
    return f"<!doctype html><html><head>{''.join(head)}{ld}</head><body></body></html>"


def _universe(tmp_path):
    hub = tmp_path / "index.html"
    hub.write_text(_HUB, encoding="utf-8")
    return {"universe": load_canonical_universe(hub)}


def test_load_canonical_universe_reads_the_rendered_hub(tmp_path):
    uni = _universe(tmp_path)["universe"]
    assert uni["RWT"] == {"name": "Redwood Trust Inc", "sector": "Real Estate"}
    assert uni["RMD"]["name"] == "ResMed"
    assert uni["AAPL"]["sector"] == "Tech"


def test_identity_clean_page_has_no_violations(tmp_path):
    ctx = _universe(tmp_path)
    page = tmp_path / "RWT.html"
    html = _page_html("RWT", "Redwood Trust Inc", "Real Estate",
                      provenance="wikipedia:Redwood Trust:exact:v2:2026-08-19",
                      jsonld_name="Redwood Trust Inc")
    assert check_identity(page, html, ctx) == []


def test_identity_flags_issuer_name_transport_residue(tmp_path):
    """The RMD defect: 'ResMed|' reached <title>, meta, OG and JSON-LD."""
    ctx = _universe(tmp_path)
    page = tmp_path / "RMD.html"
    html = _page_html("RMD", "ResMed|", "Health Care", jsonld_name="ResMed|")
    pats = {v["pattern"] for v in check_identity(page, html, ctx)}
    assert "issuer-name-residue" in pats
    assert "jsonld-name-residue" in pats


def test_identity_flags_lost_sector(tmp_path):
    """The RWT defect: the hub knows Real Estate, the dossier prints nothing."""
    ctx = _universe(tmp_path)
    page = tmp_path / "RWT.html"
    html = _page_html("RWT", "Redwood Trust Inc", "")
    pats = {v["pattern"] for v in check_identity(page, html, ctx)}
    assert "sector-lost" in pats
    # the em-dash sentinel is "lost", not a sector
    html_dash = _page_html("RWT", "Redwood Trust Inc", "—")
    assert "sector-lost" in {v["pattern"] for v in check_identity(page, html_dash, ctx)}


def test_identity_accepts_vendor_sector_aliases(tmp_path):
    ctx = _universe(tmp_path)
    page = tmp_path / "AAPL.html"
    for alias in ("Tech", "Technology", "Information Technology"):
        html = _page_html("AAPL", "Apple Inc.", alias)
        assert check_identity(page, html, ctx) == [], f"{alias} must equal Tech"


def test_identity_flags_contradicted_sector_but_allows_recorded_conflict(tmp_path):
    ctx = _universe(tmp_path)
    page = tmp_path / "RWT.html"
    bad = _page_html("RWT", "Redwood Trust Inc", "Energy")
    assert "sector-mismatch" in {v["pattern"] for v in check_identity(page, bad, ctx)}
    # an explicitly RECORDED conflict is disclosure, not a silent contradiction
    declared = _page_html("RWT", "Redwood Trust Inc", "Energy",
                          conflict="Real Estate vs Energy")
    assert "sector-mismatch" not in {v["pattern"] for v in check_identity(page, declared, ctx)}


def test_identity_flags_wrong_ticker_and_wrong_issuer(tmp_path):
    ctx = _universe(tmp_path)
    page = tmp_path / "RWT.html"
    wrong_tkr = _page_html("RWTX", "Redwood Trust Inc", "Real Estate",
                           title="RWT — Redwood Trust Inc")
    assert "ticker-mismatch" in {v["pattern"] for v in check_identity(page, wrong_tkr, ctx)}
    wrong_name = _page_html("RWT", "Redwood Restaurant Group", "Real Estate")
    assert "issuer-name-mismatch" in {v["pattern"] for v in check_identity(page, wrong_name, ctx)}


def test_identity_flags_jsonld_disagreeing_with_the_page(tmp_path):
    ctx = _universe(tmp_path)
    page = tmp_path / "RWT.html"
    html = _page_html("RWT", "Redwood Trust Inc", "Real Estate",
                      jsonld_ticker="ARI", jsonld_name="Apollo Commercial")
    pats = {v["pattern"] for v in check_identity(page, html, ctx)}
    assert "jsonld-ticker-mismatch" in pats
    assert "jsonld-name-mismatch" in pats


def test_identity_requires_provenance_for_a_published_description(tmp_path):
    ctx = _universe(tmp_path)
    page = tmp_path / "RWT.html"
    bad = _page_html("RWT", "Redwood Trust Inc", "Real Estate", provenance="incomplete")
    assert "description-provenance-missing" in {v["pattern"] for v in check_identity(page, bad, ctx)}
    # no description published at all -> nothing to audit, no violation
    none_published = _page_html("RWT", "Redwood Trust Inc", "Real Estate")
    assert check_identity(page, none_published, ctx) == []


def test_identity_ignores_corporate_form_differences(tmp_path):
    """"ResMed" and "ResMed Inc." are the same issuer; only real disagreement counts."""
    ctx = _universe(tmp_path)
    page = tmp_path / "RMD.html"
    html = _page_html("RMD", "ResMed Inc.", "Health Care", jsonld_name="ResMed Inc.")
    assert check_identity(page, html, ctx) == []


def test_identity_does_not_fail_a_page_that_asserts_nothing(tmp_path):
    """An un-migrated page is incomplete, not wrong — the guard must not fail it."""
    ctx = _universe(tmp_path)
    page = tmp_path / "RWT.html"
    html = "<!doctype html><html><head><title>RWT — Redwood Trust Inc</title></head><body></body></html>"
    assert check_identity(page, html, ctx) == []
