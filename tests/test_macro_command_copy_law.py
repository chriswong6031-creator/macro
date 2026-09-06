"""The FRONT-END CLARITY LAW gate for Macro Command (frozen spec G2/G2b, §9 P1).

`scripts/check_macro_command_copy.py` is the CI-wired guard. This file proves:

  1. it correctly ignores banned copy relocated inside `.mc-details` /
     `.mc-primer`, and correctly fails on the same copy left in the reading
     path (G2);
  2. the G2b bare-timestamp rule fires on an unprefixed `YYYY-MM-DD` /
     `T\\d\\d:\\d\\d` and passes a properly prefixed one;
  3. it is green against the REAL built `site/macro_monetary.html` (the
     frozen spec §9 P1 acceptance: "the copy guard is green");
  4. it is actually wired into CI next to the other Macro Command test files
     (`.github/ci/legacy-jobs.yml`), so a P2+ regression cannot ship
     unguarded.

Every packet after P1 ships new copy through this same guard (§9 standing
note: "green against the page that packet builds"), so this file's fixtures
and assertions are meant to survive unchanged as later packets add real
stance/primer/Read/chip content — only `test_the_real_built_page_is_clean`
runs against a moving target.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from scripts import build_macro_suite_pages as builder
from scripts import check_macro_command_copy as guard

ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = ROOT / "site" / "macrodata"
BUILT_AT = "2026-09-06T00:00:00Z"


@pytest.fixture(scope="module")
def built_hub(tmp_path_factory) -> str:
    """The real `macro_monetary.html`, rendered from the CURRENT templates
    against the real repo root — same convention as
    `tests/test_macro_command_shell.py`."""
    out = tmp_path_factory.mktemp("macro_command_copy") / "site"
    pages = builder.render(ROOT, data_root=DATA_ROOT, out_dir=out, page_built_at=BUILT_AT)
    hub = [p for p in pages if p.name == builder.HUB_PAGE.output]
    assert hub, "the builder did not write macro_monetary.html"
    return hub[0].read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# G2 — banned vocabulary outside mc-details / mc-primer
# --------------------------------------------------------------------------

@pytest.mark.parametrize("phrase", [
    "accepted snapshot", "Regime map", "authority ceiling", "content hash",
    "falsifier", "refuted", "证伪",
])
def test_banned_phrase_left_in_the_reading_path_fails(phrase: str) -> None:
    html = f'<main class="mc-shell"><p>{phrase} appears here.</p></main>'
    violations = guard.find_violations(html)
    assert any(phrase in v for v in violations), violations


@pytest.mark.parametrize("phrase", ["accepted snapshot", "falsifier", "证伪"])
def test_the_same_phrase_inside_mc_details_is_exempt(phrase: str) -> None:
    html = (
        '<main class="mc-shell">'
        '<details class="mc-details"><summary>Details, methods and sources</summary>'
        f'<div class="mc-details-body">{phrase}</div></details>'
        '</main>'
    )
    assert guard.find_violations(html) == []


def test_the_same_phrase_inside_mc_primer_is_exempt() -> None:
    html = (
        '<main class="mc-shell">'
        '<details class="mc-primer"><summary>New to this? 30 seconds</summary>'
        '<div class="mc-primer-body">accepted snapshot</div></details>'
        '</main>'
    )
    assert guard.find_violations(html) == []


def test_closed_vocabulary_token_from_labels_module_is_banned() -> None:
    tokens = guard._closed_vocabulary_tokens()
    assert "SOURCE_FAILED" in tokens
    html = '<main class="mc-shell"><p>SOURCE_FAILED</p></main>'
    violations = guard.find_violations(html)
    assert any("SOURCE_FAILED" in v for v in violations)


def test_script_content_is_never_scanned() -> None:
    """`macro_command.js`'s own header comment quotes the very substrings it
    forbids (G9) in prose — a copy-law scan of raw <script> text would flag
    the guard's OWN houseeeping comment. Script content is out of scope: this
    guard is about what a reader sees, not what the source code says about
    itself."""
    html = (
        '<main class="mc-shell"></main>'
        '<script>// this producer artifact snapshot is a code comment, not copy</script>'
    )
    assert guard.find_violations(html) == []


# --------------------------------------------------------------------------
# G2b — bare timestamp
# --------------------------------------------------------------------------

def test_bare_timestamp_with_no_preceding_word_fails() -> None:
    """G2b's own regex (`(?<![A-Za-z一-鿿][  ])\\d{4}-\\d{2}-\\d{2}`) only
    exempts a date preceded by a letter-then-space — "As of:" ends in a
    colon and a space, not a letter and a space, so this is a genuine bare
    timestamp under the spec's own definition."""
    html = '<main class="mc-shell"><p>As of: 2026-09-06.</p></main>'
    violations = guard.find_violations(html)
    assert any("bare timestamp" in v for v in violations), violations


def test_timestamp_prefixed_by_a_plain_word_passes() -> None:
    html = '<main class="mc-shell"><p>Data to 2026-09-06.</p></main>'
    assert guard.find_violations(html) == []


def test_datetime_attribute_value_is_never_scanned() -> None:
    """The machine value legitimately lives in `datetime=`; tag-stripping
    removes the attribute along with the tag, so it never reaches the scan
    even though the surrounding visible text is plain words."""
    html = ('<main class="mc-shell"><p><span>Data to</span> '
            '<time datetime="2026-09-06">3 Sep 2026</time></p></main>')
    assert guard.find_violations(html) == []


def test_raw_iso_time_fragment_always_fails() -> None:
    html = '<main class="mc-shell"><p>Built 2026-09-06T00:00:00Z</p></main>'
    violations = guard.find_violations(html)
    assert any("ISO time" in v for v in violations), violations


# --------------------------------------------------------------------------
# the real built page (§9 P1 acceptance: "the copy guard is green")
# --------------------------------------------------------------------------

def test_the_real_built_page_is_clean(built_hub: str) -> None:
    assert guard.find_violations(built_hub) == []


def test_guard_script_exits_zero_on_the_real_built_page(built_hub: str, tmp_path: Path) -> None:
    clean = tmp_path / "clean.html"
    clean.write_text(built_hub, encoding="utf-8")
    assert guard.main([str(clean)]) == 0


def test_guard_script_exits_nonzero_on_a_dirty_file(tmp_path: Path) -> None:
    dirty = tmp_path / "dirty.html"
    dirty.write_text('<main class="mc-shell"><p>accepted snapshot</p></main>', encoding="utf-8")
    assert guard.main([str(dirty)]) == 1


def test_guard_script_reports_a_missing_file_rather_than_crashing(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist.html"
    assert guard.main([str(missing)]) == 1


# --------------------------------------------------------------------------
# CI wiring — a P2+ regression must not ship unguarded
# --------------------------------------------------------------------------

def test_guard_is_wired_into_ci() -> None:
    ci = (ROOT / ".github" / "ci" / "legacy-jobs.yml").read_text(encoding="utf-8")
    assert "tests/test_macro_command_copy_law.py" in ci
