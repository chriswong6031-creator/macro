"""W8-R6 — US standout stocktable render tests.

Verifies the W8-R6 stocktable port into templates/dashboard.html.j2 (mode='stocks'):
  - JSON data block emits well-formed JSON with all configured column keys present or None
  - Serialization does NOT mutate system order (rows are in producer order, no re-sort)
  - All required structural IDs are present in rendered HTML
  - View toggle buttons present (bilingual)
  - nb-grid-section wrapper present (grid/table switching)
  - stocktable.js script tag present
  - Jinja parse of the data block snippet with synthetic context
  - ENTRY_STATUS_EN/ZH maps cover every status value in the live artifact (vocabulary-drift CI)
  - SECZH map covers every sector in the live artifact (vocabulary-drift CI)
"""
import json
import re
from pathlib import Path

import pytest
from jinja2 import DictLoader, Environment

ROOT = Path(__file__).resolve().parent.parent
SRC = (ROOT / "templates" / "dashboard.html.j2").read_text()

# ── synthetic us_standouts rows ──────────────────────────────────────────────

def _make_row(ticker, lane="bottoming", **kw):
    """Return a minimal synthetic standout row dict."""
    row = {
        "ticker": ticker,
        "name": f"{ticker} Corp",
        "sector": "Technology",
        "lane": lane,
        "price": 100.0,
        "alpha": 0.25,
        "off_high": -8.5,
        "factor_z": 0.5,
        "sue_z": None,
        "insider_buyers": None,
        "signal": {"tier_cascade": "T1", "weight": 1.0},
        "entry_signal": {"status": "buy_now"},
        "conviction": {"score": 72, "score_edge": 65},
        "dir": "up",
    }
    row.update(kw)
    return row


def _make_standouts(rows):
    return {
        "as_of": "2026-07-10",
        "buy": rows,
        "eligible": len(rows),
        "rank_by": "confluence",
    }


# ── Jinja render helper ───────────────────────────────────────────────────────

def _render_us_data_block(us_standouts):
    """Extract and render the W8-R6 JSON data block from dashboard.html.j2."""
    # Locate the stocktable data block for us market
    start = SRC.index('<script type="application/json" id="us-stocktable-data">')
    end = SRC.index("</script>", start) + len("</script>")
    snippet = SRC[start:end]

    macros = (
        '{%- macro t(en, zh="") -%}{{ en }}{%- endmacro -%}\n'
        '{%- macro td(x) -%}{{ x }}{%- endmacro -%}\n'
    )
    full = macros + "{% set _su = us_standouts %}\n" + snippet

    env = Environment(loader=DictLoader({"t": full}), autoescape=False)
    tmpl = env.get_template("t")
    return tmpl.render(us_standouts=us_standouts)


# ── column keys that must be present in every row ────────────────────────────

REQUIRED_KEYS = [
    "ticker", "name", "sector", "lane", "stage",
    "price", "conviction_score", "alpha", "off_high",
    "factor_z", "sue_z", "insider_buyers",
    "sig_tier", "entry_status", "dir",
]


class TestUSStocktableDataBlock:
    """Serialization correctness tests."""

    def test_jinja_renders_valid_json(self):
        """Data block produces parseable JSON."""
        rows = [_make_row("AAPL"), _make_row("MSFT", lane="continuation")]
        rendered = _render_us_data_block(_make_standouts(rows))
        # Extract JSON from rendered script tag
        m = re.search(r'<script[^>]*>(.*?)</script>', rendered, re.DOTALL)
        assert m, "No script tag found"
        payload = json.loads(m.group(1).strip())
        assert "rows" in payload
        assert len(payload["rows"]) == 2

    def test_all_required_keys_present_on_every_row(self):
        """Every configured column key is present (as field or None) on every row."""
        rows = [
            _make_row("AAPL"),
            _make_row("MSFT", lane="continuation", sue_z=1.2, insider_buyers=3),
            _make_row("GOOGL", lane="watch", price=None),
        ]
        rendered = _render_us_data_block(_make_standouts(rows))
        m = re.search(r'<script[^>]*>(.*?)</script>', rendered, re.DOTALL)
        payload = json.loads(m.group(1).strip())
        for i, row in enumerate(payload["rows"]):
            for key in REQUIRED_KEYS:
                assert key in row, f"Row {i} (ticker={row.get('ticker')}) missing key '{key}'"

    def test_system_order_not_mutated(self):
        """Producer order is preserved in the JSON rows array."""
        tickers = ["AES", "NVDA", "MSFT", "AAPL", "GOOGL"]
        rows = [_make_row(t) for t in tickers]
        rendered = _render_us_data_block(_make_standouts(rows))
        m = re.search(r'<script[^>]*>(.*?)</script>', rendered, re.DOTALL)
        payload = json.loads(m.group(1).strip())
        serialized_order = [r["ticker"] for r in payload["rows"]]
        assert serialized_order == tickers, (
            f"System order mutated: expected {tickers}, got {serialized_order}"
        )

    def test_lane_to_stage_mapping(self):
        """stage field maps lane values to CSS-class-compatible stage names."""
        lane_to_expected_stage = {
            "bottoming": "ENTRY",
            "continuation": "ENTRY",
            "trend": "ENTRY",
            "recovery": "RIPENING",
            "watch": "RAN_LATE",
        }
        rows = [_make_row(f"T{i}", lane=lane) for i, lane in enumerate(lane_to_expected_stage.keys())]
        rendered = _render_us_data_block(_make_standouts(rows))
        m = re.search(r'<script[^>]*>(.*?)</script>', rendered, re.DOTALL)
        payload = json.loads(m.group(1).strip())
        for row, (lane, expected) in zip(payload["rows"], lane_to_expected_stage.items()):
            assert row["stage"] == expected, (
                f"lane='{lane}' → expected stage='{expected}', got '{row['stage']}'"
            )

    def test_nullable_fields_serialize_as_null(self):
        """Fields absent from a row serialize as JSON null, not missing."""
        row = _make_row("XYZ")
        row["sue_z"] = None
        row["insider_buyers"] = None
        row["factor_z"] = None
        rendered = _render_us_data_block(_make_standouts([row]))
        m = re.search(r'<script[^>]*>(.*?)</script>', rendered, re.DOTALL)
        payload = json.loads(m.group(1).strip())
        r = payload["rows"][0]
        assert r["sue_z"] is None
        assert r["insider_buyers"] is None
        assert r["factor_z"] is None

    def test_empty_buy_list_handled(self):
        """Empty buy list renders valid empty rows array."""
        su = _make_standouts([])
        rendered = _render_us_data_block(su)
        m = re.search(r'<script[^>]*>(.*?)</script>', rendered, re.DOTALL)
        payload = json.loads(m.group(1).strip())
        assert payload["rows"] == []


class TestUSStocktableStructure:
    """Template structural checks (not a full render — checks raw template source)."""

    def test_standouts_div_has_us_standouts_id(self):
        """`.notable` div carrying the standout board has id='us-standouts'."""
        assert 'id="us-standouts"' in SRC

    def test_view_toggle_buttons_present(self):
        """Grid and table toggle buttons are present with bilingual labels."""
        assert 'id="us-st-btn-grid"' in SRC
        assert 'id="us-st-btn-table"' in SRC
        assert 'USStockTable._setView' in SRC

    def test_count_chips_div_present(self):
        """Count chips div uses the id stocktable.js looks up."""
        assert 'id="st-count-chips"' in SRC

    def test_stocktable_wrap_mount_present(self):
        """Table mount point div is present."""
        assert 'id="us-stocktable-wrap"' in SRC

    def test_nb_grid_section_wrapper_present(self):
        """Grid section has .nb-grid-section class for CSS toggle."""
        assert 'class="nb-grid-section"' in SRC

    def test_stocktable_js_include_present(self):
        """stocktable.js is included."""
        assert '<script src="stocktable.js">' in SRC

    def test_us_stocktable_init_present(self):
        """StockTable.init call for US market is present."""
        assert "us-stocktable-data" in SRC
        assert "us-stocktable-wrap" in SRC
        assert "market: 'us'" in SRC

    def test_link_pattern_uses_stock_html(self):
        """US market uses stock.html#{ticker} link pattern."""
        assert "stock.html#{ticker}" in SRC

    def test_localStorage_key_is_us(self):
        """localStorage key uses 'us' namespace."""
        assert "mdx_stocktable_us" in SRC

    def test_bilingual_toggle_labels(self):
        """Toggle labels have both l-en and l-zh spans."""
        # Both Grid/卡片 and Table/表格 labels present
        assert "l-en\">Grid<" in SRC or "l-en\">Grid<" in SRC.replace("\n", "")
        assert "l-zh\">卡片<" in SRC
        assert "l-zh\">表格<" in SRC

    def test_no_title_attribute_with_translated_text(self):
        """check_title_i18n guard: no translated text in title= attributes around stocktable code.

        The CI check forbids Chinese/Japanese/Korean characters inside title="" attributes.
        Scan the data block region for title= with CJK chars.
        """
        # Find region around us-stocktable injection
        start = SRC.find('id="us-standouts"')
        end = SRC.find('</script>', SRC.find('id="us-stocktable-data"')) + 10
        if start < 0 or end < 10:
            pytest.skip("Could not locate us-standouts block")
        region = SRC[start:end]
        # Look for title="..." containing CJK characters
        title_matches = re.findall(r'title="([^"]*)"', region)
        for m in title_matches:
            cjk = re.search(r'[一-鿿぀-ヿ㐀-䶿]', m)
            assert not cjk, f"CJK text in title= attribute: {m!r}"


class TestUSStocktableRealData:
    """Tests against committed us_standouts.json artifact."""

    ARTIFACT = ROOT / "site" / "factordata" / "us_standouts.json"

    @pytest.fixture
    def standouts(self):
        if not self.ARTIFACT.exists():
            pytest.skip("us_standouts.json not found")
        with open(self.ARTIFACT) as f:
            return json.load(f)

    def test_real_data_serializes_without_error(self, standouts):
        """Serialization of real artifact rows completes without exception."""
        rendered = _render_us_data_block(standouts)
        m = re.search(r'<script[^>]*>(.*?)</script>', rendered, re.DOTALL)
        assert m, "No script block found"
        payload = json.loads(m.group(1).strip())
        assert isinstance(payload["rows"], list)
        assert len(payload["rows"]) == len(standouts.get("buy", []))

    def test_real_data_all_keys_present(self, standouts):
        """All configured column keys present on every real row."""
        rendered = _render_us_data_block(standouts)
        m = re.search(r'<script[^>]*>(.*?)</script>', rendered, re.DOTALL)
        payload = json.loads(m.group(1).strip())
        for i, row in enumerate(payload["rows"]):
            for key in REQUIRED_KEYS:
                assert key in row, (
                    f"Real row {i} (ticker={row.get('ticker')}) missing key '{key}'"
                )

    def test_real_data_order_preserved(self, standouts):
        """Serialized order matches producer order in the artifact."""
        orig_tickers = [r["ticker"] for r in standouts.get("buy", [])]
        rendered = _render_us_data_block(standouts)
        m = re.search(r'<script[^>]*>(.*?)</script>', rendered, re.DOTALL)
        payload = json.loads(m.group(1).strip())
        serial_tickers = [r["ticker"] for r in payload["rows"]]
        assert serial_tickers == orig_tickers


# ── helpers to extract maps from template source ─────────────────────────────

def _extract_js_object(src: str, var_name: str) -> dict:
    """Extract a JS object literal assigned to `var_name` from the template source.

    Looks for ``var <var_name> = { ... };`` and parses the value as JSON (the
    maps use double-quoted string keys/values so valid JSON).
    Returns an empty dict if not found (test will fail on the check below).
    """
    pattern = r'var\s+' + re.escape(var_name) + r'\s*=\s*(\{[^}]+\})'
    m = re.search(pattern, src, re.DOTALL)
    if not m:
        return {}
    # Normalise: strip trailing commas before } to be valid JSON
    raw = re.sub(r',\s*\}', '}', m.group(1))
    return json.loads(raw)


class TestUSStocktableVocabularyCompleteness:
    """Vocabulary-drift CI: maps in template must cover every key in the live artifact.

    When the entry_signal producer adds a new status value or the sector taxonomy
    changes, these tests fail CI before the table silently shows raw tokens.
    """

    ARTIFACT = ROOT / "site" / "factordata" / "us_standouts.json"

    @pytest.fixture
    def standouts(self):
        if not self.ARTIFACT.exists():
            pytest.skip("us_standouts.json not found")
        with open(self.ARTIFACT) as f:
            return json.load(f)

    def _all_rows(self, standouts) -> list:
        rows = []
        for lane in ("buy", "watch", "laggards"):
            rows.extend(standouts.get(lane, []))
        return rows

    def test_entry_status_en_covers_artifact_vocabulary(self, standouts):
        """ENTRY_STATUS_EN must have a key for every status value in us_standouts.json.

        A missing key causes the column to show the raw token (e.g. 'buy_soon')
        instead of a human-readable label.
        """
        map_en = _extract_js_object(SRC, "ENTRY_STATUS_EN")
        assert map_en, "Could not extract ENTRY_STATUS_EN from template"

        artifact_statuses = set()
        for row in self._all_rows(standouts):
            status = (row.get("entry_signal") or {}).get("status")
            if status:
                artifact_statuses.add(status)

        missing = artifact_statuses - set(map_en.keys())
        assert not missing, (
            f"ENTRY_STATUS_EN is missing keys present in us_standouts.json: {sorted(missing)}. "
            "Add them to both ENTRY_STATUS_EN and ENTRY_STATUS_ZH in templates/dashboard.html.j2."
        )

    def test_entry_status_zh_covers_artifact_vocabulary(self, standouts):
        """ENTRY_STATUS_ZH must have a key for every status value in us_standouts.json."""
        map_zh = _extract_js_object(SRC, "ENTRY_STATUS_ZH")
        assert map_zh, "Could not extract ENTRY_STATUS_ZH from template"

        artifact_statuses = set()
        for row in self._all_rows(standouts):
            status = (row.get("entry_signal") or {}).get("status")
            if status:
                artifact_statuses.add(status)

        missing = artifact_statuses - set(map_zh.keys())
        assert not missing, (
            f"ENTRY_STATUS_ZH is missing keys present in us_standouts.json: {sorted(missing)}. "
            "Add Chinese labels in templates/dashboard.html.j2."
        )

    def test_seczh_covers_artifact_sectors(self, standouts):
        """SECZH must have a key for every sector value in us_standouts.json.

        A missing key causes ZH mode to show the English sector name literally.
        The map uses GICS-style names (Information Technology, Financials, …).
        """
        map_seczh = _extract_js_object(SRC, "SECZH")
        assert map_seczh, "Could not extract SECZH from template"

        artifact_sectors = set()
        for row in self._all_rows(standouts):
            sec = row.get("sector")
            # Ignore spurious data-quality values: real GICS sector names start with
            # an uppercase letter (a 'history' file-stem leak shipped once; the
            # producer now drops such rows — build_stock_library
            # _drop_spurious_sector_rows — do not add junk keys to the SECZH map).
            if sec and sec[0].isupper():
                artifact_sectors.add(sec)

        missing = artifact_sectors - set(map_seczh.keys())
        assert not missing, (
            f"SECZH is missing keys present in us_standouts.json: {sorted(missing)}. "
            "Add Chinese sector labels in templates/dashboard.html.j2. "
            "Note: map uses GICS-style names (e.g. 'Information Technology'), not Yahoo-style."
        )
