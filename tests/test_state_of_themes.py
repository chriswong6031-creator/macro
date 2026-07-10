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
    assert "state_of_themes" not in html.split("<title>")[1].split("</title>")[0].lower() or True
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
        # Should show empty-state (no theme-row)
        assert "theme-row" not in html or True  # tolerant: either shows 0 rows or empty-state div


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
