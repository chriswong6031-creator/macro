"""FRONT-END CLARITY copy law — Macro Command guard (spec §5 / G2b)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from scripts.check_macro_command_copy import (
    Hit,
    check_files,
    closed_vocab_tokens,
    format_error,
    main,
    scan_html,
)

ROOT = Path(__file__).resolve().parents[1]
GUARD = ROOT / "scripts" / "check_macro_command_copy.py"
HUB = ROOT / "site" / "macro_monetary.html"

# One representative of every banned family outside Details/primer.
_DIRTY_MAIN = """\
<!doctype html><html><head><title>Hub</title></head>
<body>
<header class="site-nav">Freshness Presence CURRENT</header>
<main>
  <p id="phrase">latest accepted print on the board</p>
  <p id="boundary">the axis of the reading</p>
  <p id="underscore">see coverage_ratio here</p>
  <p id="label">state is CURRENT today</p>
  <p id="date">2026-09-05</p>
  <p id="time">stamp T12:00 inside</p>
  <p id="taxis">taxis corridor stays clean</p>
  <p>Data to 5 Sep 2026</p>
  <time datetime="2026-09-05">Data to 5 Sep 2026</time>
  <details class="mc-details">
    <p>accepted print axis coverage_ratio CURRENT 2026-09-05 T12:00</p>
  </details>
  <p class="mc-primer">accepted print axis coverage_ratio CURRENT 2026-09-05 T12:00</p>
</main>
</body></html>
"""

_CLEAN_MAIN = """\
<!doctype html><html><head><title>Macro Command</title></head>
<body>
<header>Freshness Presence CURRENT accepted print</header>
<main>
  <p>Data to 5 Sep 2026</p>
  <time datetime="2026-09-05">Data to 5 Sep 2026</time>
  <p>taxis corridor</p>
  <details class="mc-details">
    <summary>Dates</summary>
    <p>accepted print axis coverage_ratio CURRENT 2026-09-05 T12:00 Freshness</p>
  </details>
  <p class="mc-primer">method version Freshness Presence</p>
</main>
</body></html>
"""


def test_closed_vocab_tokens_include_expected_machine_ids():
    tokens = closed_vocab_tokens()
    for expected in (
        "CURRENT",
        "WARMUP",
        "SOURCE_FAILED",
        "STALE_SOURCE",
        "USD_bn",
        "higher_tighter",
    ):
        assert expected in tokens
    # Region codes must not poison the substring scan.
    assert "US" not in tokens
    assert "EU" not in tokens


def test_dirty_fixture_reports_every_banned_family():
    hits = scan_html(_DIRTY_MAIN)
    matched = {h.matched for h in hits}
    assert "accepted print" in matched  # phrase
    assert "axis" in matched  # boundary word
    assert "coverage_ratio" in matched  # underscore token
    assert "CURRENT" in matched  # labels.py token
    assert "2026-09-05" in matched  # bare date
    assert "T12:00" in matched  # ISO time fragment
    assert all(isinstance(h, Hit) for h in hits)


def test_exempt_details_and_primer_are_silent():
    hits = scan_html(_CLEAN_MAIN)
    assert hits == []


def test_plain_as_of_and_datetime_attr_are_silent():
    html = """<!doctype html><html><head><title>t</title></head>
    <body><main>
      <p>Data to 5 Sep 2026</p>
      <time datetime="2026-09-05">Data to 5 Sep 2026</time>
    </main></body></html>"""
    assert scan_html(html) == []


def test_bare_iso_date_is_a_hit():
    html = """<!doctype html><html><head><title>t</title></head>
    <body><main><p>2026-09-05</p></main></body></html>"""
    matched = {h.matched for h in scan_html(html)}
    assert "2026-09-05" in matched


def test_header_outside_main_is_not_scanned():
    html = """<!doctype html><html><head><title>t</title></head>
    <body><header>Freshness Presence</header><main><p>ok</p></main></body></html>"""
    assert scan_html(html) == []


def test_taxis_is_not_a_boundary_hit():
    html = """<!doctype html><html><head><title>t</title></head>
    <body><main><p>taxis</p></main></body></html>"""
    assert scan_html(html) == []


def test_error_annotation_starts_the_line(capsys, tmp_path):
    page = tmp_path / "dirty.html"
    page.write_text(_DIRTY_MAIN, encoding="utf-8")
    files, nodes, errors = check_files([page])
    assert files == 1 and nodes > 0 and errors
    # format_error + main() both emit bare ::error lines (never via a logger).
    line = format_error(page, Hit(matched="axis", context="the axis of"), root=tmp_path)
    assert line.startswith("::")
    assert line.startswith("::error title=macro-command-copy::")
    rc = main([str(page)])
    captured = capsys.readouterr()
    assert rc == 1
    err_lines = [ln for ln in captured.out.splitlines() if ln.startswith("::")]
    assert err_lines, captured.out
    for ln in err_lines:
        assert ln.startswith("::error title=macro-command-copy::")


def test_selftest_exits_zero():
    proc = subprocess.run(
        [sys.executable, str(GUARD), "--selftest"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "selftest OK" in proc.stdout


@pytest.mark.xfail(
    strict=False,
    reason="P1-A replaces the hub page; strict green from P1 merge on",
)
def test_live_hub_page_is_clean():
    assert HUB.is_file(), f"missing built hub page: {HUB}"
    hits = scan_html(HUB.read_text(encoding="utf-8"))
    assert hits == [], [h.matched for h in hits[:20]]
