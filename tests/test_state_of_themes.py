"""tests/test_state_of_themes.py — TIL W4 State of Themes builder acceptance tests.

Tests:
1. Live render: builder renders a non-empty matrix from the real artifacts.
2. Tolerant empty-state: each missing artifact → honest empty-state, no crash.
3. Banned-word scan: 'validated' absent from rendered HTML.
4. No translated title= attrs: each title= value is single-language (no CJK in title=).
5. Filter-chip counts match the data computed from theme_asymmetry + theme_thesis.
6. Falsifier-fired count matches theme_thesis.json n_falsifier_fired.
7. Inline JS parses cleanly (node --check).
8. check_template_site_sync passes for state_of_themes.html.j2 (it is a .j2 page,
   not a plain-copy asset, so the sync check should not flag it as requiring a
   paired site copy).
9. check_validated_claims passes on the rendered page.
10. TIL page-wiring: options crowding check section renders with plain-word state.
11. TIL page-wiring: clinical section renders only for covered themes, negative yoy honest.
12. TIL page-wiring: trade_flows all-null → page-level accrual note, no per-theme rows.
13. TIL page-wiring: trade_flows populated → per-theme row with confirmation plain word.
14. TIL page-wiring: all 3 basketdata artifacts missing → page renders, no crash, no new sections.
15. TIL page-wiring: no title= attrs with CJK in new sections.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))

NWD = REPO_ROOT / "site" / "neuralwebdata"
RENDERED = REPO_ROOT / "site" / "state_of_themes.html"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_CJK = re.compile(r"[一-鿿㐀-䶿　-〿＀-￯]")


def _load_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _render(root: Path) -> str:
    """Import and call render(); return HTML string."""
    import scripts.build_state_of_themes as sot
    return sot.render(root)


# ---------------------------------------------------------------------------
# 1. Live render — non-empty matrix from real artifacts
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not (NWD / "theme_state.json").exists(), reason="live artifacts absent")
def test_live_render_non_empty_matrix():
    """Builder renders with real data and produces a non-empty matrix."""
    html = _render(REPO_ROOT)
    assert "theme-row" in html, "expected at least one theme-row in rendered matrix"
    # Header must show the theme count chip (real render, not just a shell)
    assert "themes" in html and "stage-pill" in html
    # Ensure a stage chip appears
    assert "stage-pill" in html


@pytest.mark.skipif(not (NWD / "theme_state.json").exists(), reason="live artifacts absent")
def test_live_render_theme_count():
    """Matrix row count matches n_themes in theme_state.json."""
    state = _load_json(NWD / "theme_state.json")
    assert state is not None
    n_themes = state.get("n_themes", 0)
    html = _render(REPO_ROOT)
    count = html.count('class="theme-row"')
    assert count == n_themes, f"expected {n_themes} theme rows, got {count}"


# ---------------------------------------------------------------------------
# 2. Tolerant empty-state on missing artifacts
# ---------------------------------------------------------------------------

def test_missing_theme_state_graceful():
    """Builder produces valid HTML (no crash, empty-state) when theme_state.json is absent."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        # Minimal structure — copy template dir + navlinks
        (root / "templates").mkdir()
        src_tpl = REPO_ROOT / "templates" / "state_of_themes.html.j2"
        (root / "templates" / "state_of_themes.html.j2").write_bytes(src_tpl.read_bytes())
        nav = REPO_ROOT / "templates" / "_navlinks.html.j2"
        if nav.exists():
            (root / "templates" / "_navlinks.html.j2").write_bytes(nav.read_bytes())
        # No site/neuralwebdata dir → all artifacts missing
        (root / "site").mkdir()
        import scripts.build_state_of_themes as sot
        html = sot.render(root)
        assert "<!DOCTYPE html>" in html
        # With all artifacts missing, the honest empty-state MUST render and there
        # must be NO data theme-rows (discriminating: fails if a shell leaks rows).
        # data-theme-id= appears ONLY on a rendered data row (line 281), never in
        # CSS/JS — a discriminating check that no shell rows leak.
        assert "data-theme-id=" not in html, "empty-state must not render data rows"
        assert ("No theme data available" in html or "暂无主题数据" in html), \
            "empty-state div must render when no artifacts are present"


def _make_root_with_only(artifact_name: str, content: dict) -> Path:
    """Create a temp root with only one artifact present."""
    tmp_dir = tempfile.mkdtemp()
    root = Path(tmp_dir)
    (root / "templates").mkdir()
    tpl = REPO_ROOT / "templates" / "state_of_themes.html.j2"
    (root / "templates" / "state_of_themes.html.j2").write_bytes(tpl.read_bytes())
    nav = REPO_ROOT / "templates" / "_navlinks.html.j2"
    if nav.exists():
        (root / "templates" / "_navlinks.html.j2").write_bytes(nav.read_bytes())
    nwd = root / "site" / "neuralwebdata"
    nwd.mkdir(parents=True)
    (nwd / artifact_name).write_text(json.dumps(content), encoding="utf-8")
    return root


@pytest.mark.skipif(not (NWD / "theme_state.json").exists(), reason="live artifacts absent")
def test_missing_thesis_graceful():
    """Builder does not crash when theme_thesis.json is missing."""
    import scripts.build_state_of_themes as sot
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "templates").mkdir()
        tpl = REPO_ROOT / "templates" / "state_of_themes.html.j2"
        (root / "templates" / "state_of_themes.html.j2").write_bytes(tpl.read_bytes())
        nav = REPO_ROOT / "templates" / "_navlinks.html.j2"
        if nav.exists():
            (root / "templates" / "_navlinks.html.j2").write_bytes(nav.read_bytes())
        nwd = root / "site" / "neuralwebdata"
        nwd.mkdir(parents=True)
        # Copy only theme_state + theme_asymmetry
        for f in ["theme_state.json", "theme_asymmetry.json"]:
            src = NWD / f
            if src.exists():
                (nwd / f).write_bytes(src.read_bytes())
        html = sot.render(root)
        assert "<!DOCTYPE html>" in html


@pytest.mark.skipif(not (NWD / "theme_state.json").exists(), reason="live artifacts absent")
def test_missing_asymmetry_graceful():
    """Builder does not crash when theme_asymmetry.json is missing."""
    import scripts.build_state_of_themes as sot
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "templates").mkdir()
        tpl = REPO_ROOT / "templates" / "state_of_themes.html.j2"
        (root / "templates" / "state_of_themes.html.j2").write_bytes(tpl.read_bytes())
        nav = REPO_ROOT / "templates" / "_navlinks.html.j2"
        if nav.exists():
            (root / "templates" / "_navlinks.html.j2").write_bytes(nav.read_bytes())
        nwd = root / "site" / "neuralwebdata"
        nwd.mkdir(parents=True)
        for f in ["theme_state.json", "theme_thesis.json"]:
            src = NWD / f
            if src.exists():
                (nwd / f).write_bytes(src.read_bytes())
        html = sot.render(root)
        assert "<!DOCTYPE html>" in html


# ---------------------------------------------------------------------------
# 3. Banned-word scan
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not RENDERED.exists(), reason="rendered file absent — run builder first")
def test_no_validated_in_rendered():
    """The word 'validated' must not appear in user-facing HTML."""
    content = RENDERED.read_text(encoding="utf-8")
    # check_validated_claims.py pattern: whole-word match, case-insensitive
    hits = re.findall(r"\bvalidated\b", content, re.IGNORECASE)
    assert not hits, f"'validated' found {len(hits)} time(s) in rendered page"


@pytest.mark.skipif(not (NWD / "theme_state.json").exists(), reason="live artifacts absent")
def test_no_validated_in_live_render():
    """Live render must not contain 'validated'."""
    html = _render(REPO_ROOT)
    hits = re.findall(r"\bvalidated\b", html, re.IGNORECASE)
    assert not hits, f"'validated' found {len(hits)} time(s)"


# ---------------------------------------------------------------------------
# 4. No translated title= attrs
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not (NWD / "theme_state.json").exists(), reason="live artifacts absent")
def test_no_cjk_in_title_attrs():
    """No title= attribute should contain CJK characters (i18n guard)."""
    html = _render(REPO_ROOT)
    title_re = re.compile(r'title="([^"]*?)"', re.DOTALL)
    violations = [m.group(1)[:80] for m in title_re.finditer(html) if _CJK.search(m.group(1))]
    assert not violations, f"CJK found in title= attrs: {violations}"


# ---------------------------------------------------------------------------
# 5. Filter-chip counts match data
# ---------------------------------------------------------------------------

@pytest.mark.skipif(
    not (NWD / "theme_asymmetry.json").exists() or not (NWD / "theme_thesis.json").exists(),
    reason="live artifacts absent",
)
def test_filter_chip_counts_match_data():
    """Filter-chip counts in template context match what the data says."""
    import scripts.build_state_of_themes as sot
    ctx = sot.compose(REPO_ROOT)

    # Recompute manually from raw data
    asym = _load_json(NWD / "theme_asymmetry.json")
    th_data = _load_json(NWD / "theme_thesis.json")
    assert asym and th_data

    thesis_by_id = {t["theme_id"]: t for t in th_data.get("theses", []) if "theme_id" in t}

    crowded = 0
    bottleneck_tight = 0
    thesis_review = 0
    secular_at_cyclical = 0

    for theme in asym.get("themes", []):
        legs = theme.get("legs", {})
        tid = theme.get("theme_id", "")
        th = thesis_by_id.get(tid, {})
        any_fired = (th.get("falsifier_summary", {}) or {}).get("any_fired", False)
        flags = sot._compute_filter_flags(legs, any_fired)

        if "crowded" in flags:
            crowded += 1
        if "bottleneck_tight" in flags:
            bottleneck_tight += 1
        if "thesis_review" in flags:
            thesis_review += 1
        if "secular_at_cyclical" in flags:
            secular_at_cyclical += 1

    assert ctx["chip_crowded"] == crowded, f"crowded: expected {crowded}, got {ctx['chip_crowded']}"
    assert ctx["chip_bottleneck_tight"] == bottleneck_tight
    assert ctx["chip_thesis_review"] == thesis_review
    assert ctx["chip_secular_at_cyclical"] == secular_at_cyclical


# ---------------------------------------------------------------------------
# 6. Falsifier-fired count matches theme_thesis.json
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not (NWD / "theme_thesis.json").exists(), reason="live artifacts absent")
def test_falsifier_fired_count_matches_thesis():
    """n_falsifier_fired in context must match theme_thesis.json top-level count."""
    import scripts.build_state_of_themes as sot
    ctx = sot.compose(REPO_ROOT)
    th_data = _load_json(NWD / "theme_thesis.json")
    expected = th_data.get("n_falsifier_fired", 0)
    assert ctx["n_falsifier_fired"] == expected, (
        f"n_falsifier_fired mismatch: expected {expected}, got {ctx['n_falsifier_fired']}"
    )


# ---------------------------------------------------------------------------
# 7. Inline JS parses cleanly (node --check)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not shutil.which("node"), reason="node not on PATH")
@pytest.mark.skipif(not (NWD / "theme_state.json").exists(), reason="live artifacts absent")
def test_inline_js_parses():
    """All inline <script> blocks in the rendered page must parse as valid JS."""
    html = _render(REPO_ROOT)
    script_re = re.compile(r"<script(?:\s[^>]*)?>(.+?)</script>", re.DOTALL | re.IGNORECASE)
    errors = []
    for i, m in enumerate(script_re.finditer(html)):
        block = m.group(1).strip()
        # Skip src= scripts (empty body) and JSON-only blocks
        if not block or block.startswith("{") or "src=" in m.group(0):
            continue
        with tempfile.NamedTemporaryFile(suffix=".js", mode="w", encoding="utf-8", delete=False) as tf:
            tf.write(block)
            tf_path = tf.name
        result = subprocess.run(
            ["node", "--check", tf_path],
            capture_output=True, text=True,
        )
        Path(tf_path).unlink(missing_ok=True)
        if result.returncode != 0:
            errors.append(f"block {i}: {result.stderr[:200]}")
    assert not errors, f"inline JS parse errors:\n" + "\n".join(errors)


# ---------------------------------------------------------------------------
# 8. check_template_site_sync — .j2 page should not require plain-copy pairing
# ---------------------------------------------------------------------------

def test_template_site_sync_check():
    """check_template_site_sync should not flag state_of_themes.html.j2 as requiring
    a plain-copy site/ peer (it is a Jinja2-rendered page, not a plain-copy asset)."""
    from scripts.check_template_site_sync import check
    errors = check(REPO_ROOT, fix=False)
    # Filter to only errors related to state_of_themes
    sot_errors = [e for e in errors if "state_of_themes" in e]
    assert not sot_errors, f"check_template_site_sync flagged state_of_themes: {sot_errors}"


# ---------------------------------------------------------------------------
# 9. check_validated_claims on rendered page
# ---------------------------------------------------------------------------

def test_check_validated_claims():
    """check_validated_claims.py must pass (exit 0) — scans templates/ including our new template."""
    result = subprocess.run(
        [sys.executable, "-m", "scripts.check_validated_claims"],
        capture_output=True, text=True, cwd=str(REPO_ROOT),
    )
    assert result.returncode == 0, (
        f"check_validated_claims failed:\n{result.stdout}\n{result.stderr}"
    )


# ---------------------------------------------------------------------------
# Helpers for TIL page-wiring tests (10–15)
# Synthetic roots: minimal theme_state + the three basketdata artifacts.
# ---------------------------------------------------------------------------

def _make_sot_root(
    tmp_path: Path,
    *,
    include_options_witness: bool = True,
    include_clinical: bool = True,
    include_trade_flows: bool = True,
    trade_flows_populated: bool = False,
) -> Path:
    """Build a minimal synthetic repo root for build_state_of_themes.render().

    Sets up:
      - templates/state_of_themes.html.j2 (real template, copied)
      - templates/_navlinks.html.j2       (real template, copied if exists)
      - site/neuralwebdata/theme_state.json   (2 themes: ai_infrastructure + diagnostics_lifesci)
      - site/neuralwebdata/theme_asymmetry.json
      - site/basketdata/options_witness.json  (if include_options_witness)
      - site/basketdata/clinical_pipeline.json (if include_clinical)
      - site/basketdata/trade_flows.json      (if include_trade_flows; accruing or populated)
    """
    # Templates
    (tmp_path / "templates").mkdir(exist_ok=True)
    tpl_src = REPO_ROOT / "templates" / "state_of_themes.html.j2"
    (tmp_path / "templates" / "state_of_themes.html.j2").write_bytes(tpl_src.read_bytes())
    nav = REPO_ROOT / "templates" / "_navlinks.html.j2"
    if nav.exists():
        (tmp_path / "templates" / "_navlinks.html.j2").write_bytes(nav.read_bytes())

    # neuralwebdata
    nwd = tmp_path / "site" / "neuralwebdata"
    nwd.mkdir(parents=True, exist_ok=True)

    # Minimal theme_state.json — 2 themes
    (nwd / "theme_state.json").write_text(json.dumps({
        "as_of": "2026-07-17",
        "n_themes": 2,
        "stale_legs": [],
        "themes": [
            {
                "theme_id": "ai_infrastructure",
                "name_en": "AI Infrastructure",
                "name_zh": "AI基础设施",
                "foresight": {"stage": "WATCH"},
            },
            {
                "theme_id": "diagnostics_lifesci",
                "name_en": "Diagnostics / Life Sciences",
                "name_zh": "诊断/生命科学",
                "foresight": {"stage": "WATCH"},
            },
        ],
    }), encoding="utf-8")

    # theme_asymmetry.json — real leg ids for polarity tests
    # ai_infrastructure: bottleneck_tightness=high (→fav), crowding_hazard=high (→caut),
    #   entry_cleanliness=low (→caut), stale_consensus_gap=low (→neut),
    #   orthogonality=high (→fav); memory_storage: entry_cleanliness=high (→fav)
    (nwd / "theme_asymmetry.json").write_text(json.dumps({
        "as_of": "2026-07-17",
        "themes": [
            {
                "theme_id": "ai_infrastructure",
                "name_en": "AI Infrastructure",
                "legs": {
                    "bottleneck_tightness": {"band": "high", "value": 0.85, "note_en": "chipmakers report supply constraints"},
                    "stale_consensus_gap": {"band": "low", "value": 0.1},
                    "cyclical_dislocation": {"band": "med", "value": 0.5},
                    "entry_cleanliness": {"band": "low", "value": 0.2},
                    "crowding_hazard": {"band": "high", "value": 0.9},
                    "falsifier_clarity": {"band": "high", "value": 0.8},
                    "orthogonality": {"band": "high", "value": 0.75},
                },
            },
            {
                "theme_id": "diagnostics_lifesci",
                "name_en": "Diagnostics / Life Sciences",
                "legs": {},
            },
        ],
    }), encoding="utf-8")

    # basketdata
    bkd = tmp_path / "site" / "basketdata"
    bkd.mkdir(parents=True, exist_ok=True)

    if include_options_witness:
        (bkd / "options_witness.json").write_text(json.dumps({
            "as_of": "2026-07-17",
            "coverage_stats": {"themes_covered": 1, "themes_suppressed": 1},
            "themes": {
                "ai_infrastructure": {
                    "name_en": "AI Infrastructure",
                    "name_zh": "AI基础设施",
                    "leg_a_call_oi_hhi": {
                        "band": "elevated", "value": 0.72, "value_z252": 2.1, "stale": False,
                        "coverage_count": 8, "coverage_total": 10,
                    },
                    "leg_b_pcr": {
                        "band": "complacency", "value": 0.65, "value_z252": -1.8, "stale": False,
                        "pcr_collapse_into_strength": False,
                        "coverage_count": 8, "coverage_total": 10,
                    },
                    "leg_c_iv_premium": {
                        "band": "normal", "value": 0.08, "value_z252": 0.3, "stale": False,
                        "coverage_count": 8, "coverage_total": 10,
                    },
                },
                "diagnostics_lifesci": {
                    "name_en": "Diagnostics / Life Sciences",
                    "name_zh": "诊断/生命科学",
                    "leg_a_call_oi_hhi": {
                        "band": None, "value": None, "value_z252": None, "stale": None,
                    },
                    "leg_b_pcr": {
                        "band": None, "value": None, "value_z252": None, "stale": None,
                        "pcr_collapse_into_strength": False,
                    },
                    "leg_c_iv_premium": {
                        "band": None, "value": None, "value_z252": None, "stale": None,
                    },
                },
            },
        }), encoding="utf-8")

    if include_clinical:
        (bkd / "clinical_pipeline.json").write_text(json.dumps({
            "as_of": "2026-07-17",
            "coverage_stats": {"themes_with_data": 1},
            "themes": {
                "diagnostics_lifesci": {
                    "theme_registration_yoy_pct": -5.2,
                    "theme_registration_velocity_read": "decelerating",
                    "theme_registration_magnitude_band": "small",
                    "n_phase3_trailing12m": 3,
                    "n_studies_total": 42,
                    "coverage_note": "",
                    "coverage_note_zh": "",
                },
                # ai_infrastructure has NO clinical data (n_studies_total=0)
            },
        }), encoding="utf-8")

    if include_trade_flows:
        if trade_flows_populated:
            (bkd / "trade_flows.json").write_text(json.dumps({
                "as_of": "2026-07-17",
                "coverage_stats": {"themes_with_data": 1},
                "themes": {
                    "ai_infrastructure": {
                        "yoy_pct": 12.3,
                        "accel_3m_vs_12m": 2.1,
                        "confirmation": "confirms",
                        "magnitude_band": "moderate",
                        "n_codes_with_data": 4,
                        "coverage_note": "",
                        "coverage_note_zh": "",
                    },
                },
            }), encoding="utf-8")
        else:
            # All-null / accruing
            (bkd / "trade_flows.json").write_text(json.dumps({
                "as_of": "2026-07-17",
                "coverage_stats": {"themes_with_data": 0, "parquet_absent": True},
                "themes": {},
            }), encoding="utf-8")

    return tmp_path


# ---------------------------------------------------------------------------
# 10. Options crowding check section renders with plain-word state
# ---------------------------------------------------------------------------

def test_options_crowding_section_renders_plain_state(tmp_path):
    """Crowding section renders with plain-word state rows for covered themes.

    ai_infrastructure has: leg_a=elevated, leg_b=complacency, leg_c=normal.
    Expected: 'crowding sign' (el level) and 'crowding signs building' stance.
    diagnostics_lifesci has all-null legs → renders 'not enough option coverage'.
    """
    root = _make_sot_root(tmp_path)
    import scripts.build_state_of_themes as sot
    html = sot.render(root)

    # AI theme should show crowding section with elevated leg-A plain word
    assert "crowding sign" in html.lower() or "don&#39;t chase" in html.lower() or "don't chase" in html, (
        "expected crowding-sign plain word for elevated leg-A"
    )
    # The stance for worst=3 (elevated) should be present
    assert "Crowding signs building" in html or "choosy" in html, (
        "expected crowding-stance text for worst-severity=3"
    )
    # Diagnostics (suppressed) → "Not enough option coverage"
    assert "Not enough option coverage" in html, (
        "expected suppressed-theme coverage message"
    )
    # The section header must appear (bilingual; template renders both spans)
    assert "期权拥挤度检查" in html, "expected Chinese label for options crowding section"


def test_options_crowding_section_context_keys(tmp_path):
    """compose() populates ow_section correctly for ai_infrastructure."""
    root = _make_sot_root(tmp_path)
    import scripts.build_state_of_themes as sot
    ctx = sot.compose(root)
    themes = {t["theme_id"]: t for t in ctx["themes"]}
    ai_ow = themes["ai_infrastructure"]["ow_section"]
    assert ai_ow.get("available") is True
    assert ai_ow.get("covered") is True
    # Leg-A band 'elevated' → plain word must contain 'crowding'
    assert "crowding" in ai_ow["leg_a"]["word_en"].lower()
    # Leg-B band 'complacency' → hazard word
    assert "crowding" in ai_ow["leg_b"]["word_en"].lower()
    # Leg-C band 'normal' → no crowding
    assert "normal" in ai_ow["leg_c"]["word_en"].lower() or "no crowding" in ai_ow["leg_c"]["word_en"].lower()


# ---------------------------------------------------------------------------
# 11. Clinical section renders only for covered themes; negative yoy honest
# ---------------------------------------------------------------------------

def test_clinical_section_only_for_covered_themes(tmp_path):
    """Clinical section renders for diagnostics_lifesci (has data) but NOT ai_infrastructure (no data)."""
    root = _make_sot_root(tmp_path)
    import scripts.build_state_of_themes as sot
    ctx = sot.compose(root)
    themes = {t["theme_id"]: t for t in ctx["themes"]}

    # diagnostics has clinical data → cp_section available
    diag_cp = themes["diagnostics_lifesci"]["cp_section"]
    assert diag_cp.get("available") is True, "diagnostics_lifesci should have cp_section"
    # Negative yoy must be honestly rendered (not hidden or sign-flipped)
    assert "-5" in diag_cp["line1_en"] or "−5" in diag_cp["line1_en"], (
        f"negative yoy must appear honestly; got: {diag_cp['line1_en']}"
    )
    assert "decelerating" in diag_cp["line1_en"].lower() or "slowing" in diag_cp["line1_en"].lower(), (
        "velocity_read=decelerating must translate to plain word"
    )
    # ai_infrastructure has no clinical data → cp_section empty
    ai_cp = themes["ai_infrastructure"]["cp_section"]
    assert not ai_cp, "ai_infrastructure should NOT have cp_section (n_studies_total=0)"


def test_clinical_section_renders_in_html(tmp_path):
    """Rendered HTML contains the clinical-pipeline drawer section with ZH label."""
    root = _make_sot_root(tmp_path)
    import scripts.build_state_of_themes as sot
    html = sot.render(root)
    # Chinese section header must appear
    assert "临床管线" in html, "expected Chinese label '临床管线'"
    # Negative yoy number should appear (honest, unfiltered)
    assert "-5" in html or "−5" in html, "negative yoy percent must be in rendered HTML"


# ---------------------------------------------------------------------------
# 12. Trade-flows all-null → page-level accrual note; no per-theme rows
# ---------------------------------------------------------------------------

def test_trade_flows_allnull_page_note_present(tmp_path):
    """All-null trade_flows → page-level accrual note rendered; no per-theme tf rows."""
    root = _make_sot_root(tmp_path, trade_flows_populated=False)
    import scripts.build_state_of_themes as sot
    ctx = sot.compose(root)

    # Page-level note must be set
    assert ctx.get("trade_flows_page_note_en"), (
        "trade_flows_page_note_en must be set when themes_with_data==0"
    )
    assert "accruing" in ctx["trade_flows_page_note_en"].lower() or (
        "import-flow" in ctx["trade_flows_page_note_en"].lower()
    ), "page note must mention accruing or import-flow context"

    # Per-theme tf_section must be empty (no data)
    for th in ctx["themes"]:
        assert not th["tf_section"], (
            f"theme {th['theme_id']}: tf_section must be empty when all-null trade_flows"
        )


def test_trade_flows_allnull_page_note_in_html(tmp_path):
    """Rendered HTML contains the page-level accrual note (EN text)."""
    root = _make_sot_root(tmp_path, trade_flows_populated=False)
    import scripts.build_state_of_themes as sot
    html = sot.render(root)
    # The page note is wrapped in .ctx-page-note and rendered in the template
    assert "import-flow" in html.lower() or "accruing" in html.lower() or "customs" in html.lower(), (
        "page-level accrual note must appear in rendered HTML when trade_flows all-null"
    )
    # Per-theme import row labels must NOT appear
    assert "进口流量：" not in html, "per-theme import rows must not render when all-null"


# ---------------------------------------------------------------------------
# 13. Trade-flows populated → per-theme row with confirmation plain word
# ---------------------------------------------------------------------------

def test_trade_flows_populated_per_theme_row(tmp_path):
    """Populated trade_flows → per-theme tf_section with confirmation plain word."""
    root = _make_sot_root(tmp_path, trade_flows_populated=True)
    import scripts.build_state_of_themes as sot
    ctx = sot.compose(root)

    # ai_infrastructure has data → tf_section must be available
    themes = {t["theme_id"]: t for t in ctx["themes"]}
    ai_tf = themes["ai_infrastructure"]["tf_section"]
    assert ai_tf.get("available") is True, "ai_infrastructure tf_section should be available"
    # confirmation='confirms' → plain word from _TF_CONFIRMATION_EN
    assert "confirms" in ai_tf["line_en"].lower() or "confirm" in ai_tf["line_en"].lower(), (
        f"confirmation plain word missing; got: {ai_tf['line_en']}"
    )
    # Percentage must appear in line
    assert "12" in ai_tf["line_en"], f"yoy_pct missing; got: {ai_tf['line_en']}"

    # diagnostics_lifesci has no trade_flows data → tf_section empty
    diag_tf = themes["diagnostics_lifesci"]["tf_section"]
    assert not diag_tf, "diagnostics_lifesci tf_section must be empty (no import data)"

    # Page-level note must NOT be set (data exists → no accruing note)
    assert not ctx.get("trade_flows_page_note_en"), (
        "trade_flows_page_note_en must be empty when themes_with_data > 0"
    )


def test_trade_flows_populated_in_html(tmp_path):
    """Rendered HTML contains per-theme import row with confirmation plain word."""
    root = _make_sot_root(tmp_path, trade_flows_populated=True)
    import scripts.build_state_of_themes as sot
    html = sot.render(root)
    # Per-theme import row ZH label
    assert "进口流量" in html, "per-theme import row ZH label must appear when populated"
    # Plain confirmation word for 'confirms'
    assert "confirm" in html.lower(), "confirmation plain word must appear in rendered HTML"


# ---------------------------------------------------------------------------
# 14. All 3 basketdata artifacts missing → page renders, no crash, no new sections
# ---------------------------------------------------------------------------

def test_all_basketdata_missing_no_crash(tmp_path):
    """All 3 basketdata artifacts absent → render() succeeds, no new sections."""
    root = _make_sot_root(
        tmp_path,
        include_options_witness=False,
        include_clinical=False,
        include_trade_flows=False,
    )
    import scripts.build_state_of_themes as sot
    html = sot.render(root)

    assert "<!DOCTYPE html>" in html, "render must succeed even with all basketdata absent"
    # Options crowding check section must NOT render
    assert "期权拥挤度检查" not in html, (
        "crowding section must not appear when options_witness absent"
    )
    # Clinical section must NOT render
    assert "临床管线" not in html, (
        "clinical section must not appear when clinical_pipeline absent"
    )
    # Import-flow note must NOT render (no trade_flows.json at all)
    assert "进口流量" not in html, (
        "import-flow text must not appear when trade_flows absent"
    )


def test_all_basketdata_missing_compose_returns_empty_sections(tmp_path):
    """All 3 basketdata artifacts absent → compose() returns empty ow/cp/tf sections."""
    root = _make_sot_root(
        tmp_path,
        include_options_witness=False,
        include_clinical=False,
        include_trade_flows=False,
    )
    import scripts.build_state_of_themes as sot
    ctx = sot.compose(root)

    for th in ctx["themes"]:
        assert not th["ow_section"], f"{th['theme_id']}: ow_section must be empty"
        assert not th["cp_section"], f"{th['theme_id']}: cp_section must be empty"
        assert not th["tf_section"], f"{th['theme_id']}: tf_section must be empty"

    assert not ctx.get("trade_flows_page_note_en"), "page note must be empty when artifact absent"


# ---------------------------------------------------------------------------
# 15. No title= attributes with CJK text introduced by new sections
# ---------------------------------------------------------------------------

def test_no_cjk_in_title_attrs_new_sections_options_witness(tmp_path):
    """Options crowding section introduces no CJK in title= attributes."""
    root = _make_sot_root(tmp_path)
    import scripts.build_state_of_themes as sot
    html = sot.render(root)
    title_re = re.compile(r'title="([^"]*?)"', re.DOTALL)
    violations = [m.group(1)[:120] for m in title_re.finditer(html) if _CJK.search(m.group(1))]
    assert not violations, f"CJK found in title= attrs (new sections): {violations}"


def test_no_cjk_in_title_attrs_new_sections_all_populated(tmp_path):
    """All 3 basketdata artifacts populated → still no CJK in title= attributes."""
    root = _make_sot_root(tmp_path, trade_flows_populated=True)
    import scripts.build_state_of_themes as sot
    html = sot.render(root)
    title_re = re.compile(r'title="([^"]*?)"', re.DOTALL)
    violations = [m.group(1)[:120] for m in title_re.finditer(html) if _CJK.search(m.group(1))]
    assert not violations, f"CJK found in title= attrs (all populated): {violations}"


# ---------------------------------------------------------------------------
# 16. Per-leg valence polarity tests (Fix 1 / Fix 2)
# ---------------------------------------------------------------------------

def test_asym_leg_valence_polarity_compose(tmp_path):
    """compose() produces correct polarity words + valence_class for each leg.

    Fixture: ai_infrastructure has:
      bottleneck_tightness=high  → word contains 'supports the thesis', class=fav
      crowding_hazard=high       → word contains 'crowded — caution', class=caut
      entry_cleanliness=low      → word contains 'messy entry', class=caut
      stale_consensus_gap=low    → class=neut (market already caught up)
      orthogonality=high         → word contains 'moves on its own', class=fav
    diagnostics_lifesci has no legs → all null, class=null.
    """
    root = _make_sot_root(tmp_path)
    import scripts.build_state_of_themes as sot
    ctx = sot.compose(root)
    themes = {t["theme_id"]: t for t in ctx["themes"]}

    ai_legs = {lg["id"]: lg for lg in themes["ai_infrastructure"]["asym_legs_section"]}

    # bottleneck_tightness high → fav
    btl = ai_legs["bottleneck_tightness"]
    assert "supports the thesis" in btl["word_en"], (
        f"bottleneck_tightness high should say 'supports the thesis'; got: {btl['word_en']}"
    )
    assert btl["valence_class"] == "fav", (
        f"bottleneck_tightness high → fav; got: {btl['valence_class']}"
    )

    # crowding_hazard high → caut
    crw = ai_legs["crowding_hazard"]
    assert "crowded" in crw["word_en"].lower(), (
        f"crowding_hazard high should mention 'crowded'; got: {crw['word_en']}"
    )
    assert crw["valence_class"] == "caut", (
        f"crowding_hazard high → caut; got: {crw['valence_class']}"
    )

    # entry_cleanliness low → caut
    cln = ai_legs["entry_cleanliness"]
    assert "messy" in cln["word_en"].lower(), (
        f"entry_cleanliness low should say 'messy entry'; got: {cln['word_en']}"
    )
    assert cln["valence_class"] == "caut", (
        f"entry_cleanliness low → caut; got: {cln['valence_class']}"
    )

    # stale_consensus_gap low → neut
    gap = ai_legs["stale_consensus_gap"]
    assert gap["valence_class"] == "neut", (
        f"stale_consensus_gap low → neut; got: {gap['valence_class']}"
    )

    # orthogonality high → fav
    ort = ai_legs["orthogonality"]
    assert "own story" in ort["word_en"].lower() or "own" in ort["word_en"].lower(), (
        f"orthogonality high should mention own story; got: {ort['word_en']}"
    )
    assert ort["valence_class"] == "fav", (
        f"orthogonality high → fav; got: {ort['valence_class']}"
    )

    # diagnostics_lifesci has no legs → all null
    diag_legs = {lg["id"]: lg for lg in themes["diagnostics_lifesci"]["asym_legs_section"]}
    for lg in diag_legs.values():
        assert lg["valence_class"] == "null", (
            f"missing leg {lg['id']} should have null class; got: {lg['valence_class']}"
        )
        assert lg["word_en"] == "no data yet", (
            f"missing leg {lg['id']} should say 'no data yet'; got: {lg['word_en']}"
        )


def test_asym_leg_valence_in_rendered_html(tmp_path):
    """Rendered HTML: polarity-correct words + valence dot classes present in page.

    Asserts:
      - 'supports the thesis' (bottleneck_tightness high, fav) in HTML
      - 'crowded — caution' (crowding_hazard high, caut) in HTML
      - 'messy entry' (entry_cleanliness low, caut) in HTML
      - class='dot caut' (for the matrix dot) appears
      - class='dot fav' appears
      - legend contains 'favorable' and the Chinese 有利
    """
    root = _make_sot_root(tmp_path)
    import scripts.build_state_of_themes as sot
    html = sot.render(root)

    assert "supports the thesis" in html, (
        "bottleneck_tightness high → 'supports the thesis' must appear in HTML"
    )
    assert "crowded" in html.lower(), (
        "crowding_hazard high → 'crowded' must appear in HTML"
    )
    assert "messy entry" in html.lower(), (
        "entry_cleanliness low → 'messy entry' must appear in HTML"
    )
    # Valence dot classes in rendered HTML
    assert 'class="dot caut"' in html or "dot caut" in html, (
        "valence class 'caut' must appear in rendered HTML (matrix or drawer dots)"
    )
    assert 'class="dot fav"' in html or "dot fav" in html, (
        "valence class 'fav' must appear in rendered HTML"
    )
    # Legend
    assert "favorable" in html, "legend must contain 'favorable'"
    assert "有利" in html, "legend must contain '有利'"


def test_matrix_dots_use_valence_class_not_raw_band(tmp_path):
    """Matrix dots use valence class (fav/caut/neut/null), not raw band (low/med/high).

    crowding_hazard=high should produce class='dot caut' (not 'dot high').
    bottleneck_tightness=high should produce class='dot fav' (not 'dot high').
    """
    root = _make_sot_root(tmp_path)
    import scripts.build_state_of_themes as sot
    ctx = sot.compose(root)
    themes = {t["theme_id"]: t for t in ctx["themes"]}

    ai_legs_ordered = {lg["id"]: lg for lg in themes["ai_infrastructure"]["legs_ordered"]}

    crw_dot = ai_legs_ordered["crowding_hazard"]["dot_valence"]
    assert crw_dot == "caut", f"crowding_hazard high dot_valence should be 'caut'; got: {crw_dot}"

    btl_dot = ai_legs_ordered["bottleneck_tightness"]["dot_valence"]
    assert btl_dot == "fav", f"bottleneck_tightness high dot_valence should be 'fav'; got: {btl_dot}"

    # Raw band must NOT appear as a CSS class in the rendered HTML
    html = sot.render(root)
    assert 'class="dot high"' not in html, (
        "raw band 'high' must not appear as a dot class in rendered HTML"
    )
    assert 'class="dot low"' not in html, (
        "raw band 'low' must not appear as a dot class in rendered HTML"
    )


# ---------------------------------------------------------------------------
# 17. Clinical + import-flows stance lines (Fix 3)
# ---------------------------------------------------------------------------

def test_clinical_stance_line_renders(tmp_path):
    """Clinical section renders the 'Background evidence' stance line."""
    root = _make_sot_root(tmp_path)
    import scripts.build_state_of_themes as sot
    html = sot.render(root)
    assert "Background evidence" in html, (
        "clinical section must render 'Background evidence' stance line"
    )
    assert "非买入信号" in html, (
        "clinical section must render ZH stance line '非买入信号'"
    )


def test_import_flows_stance_line_renders(tmp_path):
    """Populated import-flows section renders the 'physical-demand check' stance line."""
    root = _make_sot_root(tmp_path, trade_flows_populated=True)
    import scripts.build_state_of_themes as sot
    html = sot.render(root)
    assert "physical-demand check" in html, (
        "import-flows section must render 'physical-demand check' stance line"
    )
    assert "实物需求核对" in html, (
        "import-flows section must render ZH stance '实物需求核对'"
    )


# ---------------------------------------------------------------------------
# 18. Mixed-direction trade-flow per-leg rows (Fix 4)
# ---------------------------------------------------------------------------

def _make_sot_root_mixed_tf(tmp_path: Path) -> Path:
    """Like _make_sot_root but with a mixed-direction trade_flows fixture."""
    root = _make_sot_root(tmp_path, include_trade_flows=False)
    bkd = root / "site" / "basketdata"
    bkd.mkdir(parents=True, exist_ok=True)
    (bkd / "trade_flows.json").write_text(json.dumps({
        "as_of": "2026-07-17",
        "coverage_stats": {"themes_with_data": 1},
        "themes": {
            "ai_infrastructure": {
                "n_codes_with_data": 3,
                "confirmation": "mixed_direction",
                "is_mixed_direction": True,
                "yoy_pct": None,
                "direction_legs": {
                    "rising_imports_confirms": {
                        "expected_direction": "rising_imports_confirms",
                        "yoy_pct": 15.0,
                        "confirmation": "confirms",
                        "magnitude_band": "moderate",
                    },
                    "falling_imports_confirms": {
                        "expected_direction": "falling_imports_confirms",
                        "yoy_pct": -8.0,
                        "confirmation": "contradicts",
                        "magnitude_band": "small",
                    },
                },
                "coverage_note": "3 of 4 HS codes have data",
                "coverage_note_zh": "4个HS编码中3个有数据",
            },
        },
    }), encoding="utf-8")
    return root


def test_mixed_direction_tf_per_leg_rows_compose(tmp_path):
    """Mixed-direction trade_flows → tf_section has direction_leg_rows with per-leg data."""
    root = _make_sot_root_mixed_tf(tmp_path)
    import scripts.build_state_of_themes as sot
    ctx = sot.compose(root)
    themes = {t["theme_id"]: t for t in ctx["themes"]}

    ai_tf = themes["ai_infrastructure"]["tf_section"]
    assert ai_tf.get("available") is True
    assert ai_tf.get("is_mixed") is True

    rows = ai_tf.get("direction_leg_rows", [])
    assert len(rows) == 2, f"expected 2 direction leg rows; got {len(rows)}"

    row_by_dir = {r["direction"]: r for r in rows}
    rising = row_by_dir["rising_imports_confirms"]
    falling = row_by_dir["falling_imports_confirms"]

    # Rising leg confirms → confirmation word present in line
    assert "confirm" in rising["line_en"].lower(), (
        f"rising leg should confirm; got: {rising['line_en']}"
    )
    # Falling leg contradicts
    assert "contradict" in falling["line_en"].lower() or "against" in falling["line_en"].lower(), (
        f"falling leg should contradict; got: {falling['line_en']}"
    )
    # yoy_pct should appear
    assert "15" in rising["line_en"], f"yoy 15% missing; got: {rising['line_en']}"


def test_mixed_direction_tf_rows_in_html(tmp_path):
    """Mixed-direction trade_flows → per-leg direction rows rendered in HTML."""
    root = _make_sot_root_mixed_tf(tmp_path)
    import scripts.build_state_of_themes as sot
    html = sot.render(root)

    # The mixed-direction top-level line should appear
    assert "mixed" in html.lower() or "mixed picture" in html.lower(), (
        "mixed-direction top-line must appear in HTML"
    )
    # Per-leg rows should appear
    assert "rising" in html.lower(), "direction leg label must appear in HTML"
    assert "confirm" in html.lower(), "per-leg confirmation word must appear in HTML"


def test_non_mixed_tf_single_line_form(tmp_path):
    """Non-mixed populated trade_flows → single-line form (no direction_leg_rows)."""
    root = _make_sot_root(tmp_path, trade_flows_populated=True)
    import scripts.build_state_of_themes as sot
    ctx = sot.compose(root)
    themes = {t["theme_id"]: t for t in ctx["themes"]}
    ai_tf = themes["ai_infrastructure"]["tf_section"]
    assert not ai_tf.get("is_mixed"), "non-mixed theme should not be flagged is_mixed"
    assert ai_tf.get("direction_leg_rows", []) == [], (
        "non-mixed theme should have empty direction_leg_rows"
    )
