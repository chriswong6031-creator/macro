"""i18n.zh_filing_term — the 申报 diction gate (scripts/check_zh_filing_term.py).

WHAT THIS PINS. 申报 reads to a native Chinese speaker as a TAX or CUSTOMS declaration;
a filing this platform shows is a 披露. The term was swept by hand twice — PR #4830
(Filing Forensics) and PR #4855 (SEC / 13F / congress, site-wide) — before any gate
existed, so the failure mode this suite guards against is not "the guard is wrong", it
is "the guard never fires and reads green forever".

Every assertion goes through the REAL scanners and the REAL live allowlist, never a
substring match, so the exemption semantics live in exactly one place. Three properties
carry the suite:

  1. It FIRES — a synthetic 申报 written into templates/ or engine/ turns the live CLI
     red with exit 1 and a line-starting ::error annotation.
  2. The allowlist is LOAD-BEARING and NARROW — the two licensed phrases go green on
     the files that license them, and the very same bytes go RED everywhere else. If
     someone widens an entry to a whole file, test_allowlist_is_file_scoped fails.
  3. The pending ratchet cannot become a scheduled red — going OVER a frozen budget
     fails, going UNDER only prints a ::notice, because the budget drops the moment
     somebody else's PR merges and a gate that reds main on that is an outage.

Run: .venv/bin/python -m pytest tests/test_zh_filing_term.py -q
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.check_zh_filing_term import (
    FIX,
    TERM,
    _load_allowlist,
    _targets,
    _unlicensed,
    scan,
    scan_python,
    scan_text,
    selftest,
)

ROOT = Path(__file__).resolve().parent.parent
GUARD = ROOT / "scripts" / "check_zh_filing_term.py"

# The two real sites the allowlist licenses. Named here (not derived from the
# allowlist) so a test-visible rename of either file is a failure, not a silent skip.
CLAIMS_SITE = "engine/release_quirks.py"          # 申报失业金 — jobless claims
ORDER_SITE = "scripts/collect_hk_connect_roster.py"   # 买入申报 — HK order entry


@pytest.fixture(autouse=True)
def _fresh_file_census():
    """_targets() is lru_cached for the one-shot CLI; tests create files mid-process."""
    _targets.cache_clear()
    yield
    _targets.cache_clear()


@pytest.fixture
def probe(tmp_path):
    """Write throwaway files into the scanned trees and always remove them.

    Templates use a .html.j2 suffix on purpose: a non-.j2 file directly under
    templates/ is a plain-copy PAIRED asset (ui.template_site_sync) and would need a
    byte-matching site/ twin even for the few milliseconds it exists.
    """
    made: list[Path] = []

    def _write(rel: str, body: str) -> str:
        p = ROOT / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
        made.append(p)
        _targets.cache_clear()
        return rel

    yield _write
    for p in made:
        p.unlink(missing_ok=True)


def _tag(name: str) -> str:
    """A probe path unique to this process, so parallel runs never collide."""
    return f"_zh_term_probe_{os.getpid()}_{name}"


# ── 1. The gate fires ─────────────────────────────────────────────────────────

def test_selftest_passes():
    assert selftest() == 0


def test_the_live_repo_is_clean():
    """The gate itself: no unlicensed 申报 in user-facing zh copy, right now."""
    findings, _ = scan()
    assert findings == [], (
        f"{sum(f['count'] for f in findings)} unlicensed {TERM}: "
        + "; ".join(f"{f['file']}:{f['line_no']}" for f in findings[:10])
    )


def test_fires_on_a_synthetic_template_insertion(probe):
    rel = probe(f"templates/{_tag('tpl')}.html.j2",
                f"<p>{{{{ t('Filing trail', '{TERM}轨迹') }}}}</p>\n")
    findings, _ = scan()
    assert [f["file"] for f in findings] == [rel]


def test_fires_on_a_synthetic_builder_insertion(probe):
    rel = probe(f"engine/{_tag('eng')}.py", f'ROW = {{"label_zh": "SEC {TERM}文件"}}\n')
    findings, _ = scan()
    assert [f["file"] for f in findings] == [rel]


def test_fires_on_a_synthetic_scripts_insertion(probe):
    rel = probe(f"scripts/{_tag('bld')}.py", f'LABEL_ZH = "{TERM}轨迹"\n')
    findings, _ = scan()
    assert [f["file"] for f in findings] == [rel]


def test_the_cli_goes_red_with_a_line_starting_annotation(probe):
    """End to end: exit 1, and every annotation STARTS its line.

    A workflow command GitHub cannot parse is worse than no check — the job looks
    like it alarmed and the Actions summary shows nothing. See CLAUDE.md and
    tests/test_gh_annotation_line_start.py.
    """
    rel = probe(f"templates/{_tag('cli')}.html.j2", f'<p data-zh="盯紧{TERM}">Follow</p>\n')
    proc = subprocess.run([sys.executable, str(GUARD)], cwd=ROOT,
                          capture_output=True, text=True)
    assert proc.returncode == 1, proc.stdout + proc.stderr

    annotations = [ln for ln in proc.stdout.splitlines() if "::error" in ln]
    assert annotations, f"no ::error emitted:\n{proc.stdout}"
    for ln in annotations:
        assert ln.startswith("::error"), f"annotation does not start its line: {ln!r}"
    assert any(f"file={rel},line=1," in ln for ln in annotations)
    assert any(FIX in ln for ln in annotations), "the fix must be in the failure message"


def test_an_unparseable_python_file_fails_closed():
    assert scan_python("engine/_selftest.py", "def broken(:\n", [])


# ── 2. The allowlist is load-bearing and narrow ───────────────────────────────

def test_the_two_licensed_phrases_go_green_on_their_real_files():
    allow, _ = _load_allowlist()
    for rel in (CLAIMS_SITE, ORDER_SITE):
        text = (ROOT / rel).read_text(encoding="utf-8")
        assert TERM in text, f"{rel} no longer carries {TERM} — retire its allow entry"
        assert scan_python(rel, text, allow) == []


def test_the_allowlist_is_load_bearing_not_decorative():
    """With the allowlist emptied, both licensed sites go red.

    Without this, an allow entry whose phrase had drifted out of the file would sit
    there proving nothing, and the suite above would pass for the wrong reason.
    """
    for rel in (CLAIMS_SITE, ORDER_SITE):
        text = (ROOT / rel).read_text(encoding="utf-8")
        assert scan_python(rel, text, []), f"{rel} did not fire with an empty allowlist"


def test_allowlist_is_file_scoped():
    """The same licensed bytes, on any other file, still fail."""
    allow, _ = _load_allowlist()
    for entry in allow:
        src = f'X = {{"zh": "{entry["phrase"]}"}}\n'
        assert scan_python("engine/_not_licensed.py", src, allow), (
            f"{entry['phrase']!r} is exempt outside {entry['files']} — the entry has "
            "been widened past the file that justifies it"
        )


def test_allowlist_is_phrase_scoped_per_occurrence():
    """A licensed phrase does not launder a bare 申报 sitting next to it."""
    allow, _ = _load_allowlist()
    entry = next(e for e in allow if e["files"] == [CLAIMS_SITE])
    src = f'X = {{"zh": "{entry["phrase"]}；另见{TERM}轨迹"}}\n'
    found = scan_python(CLAIMS_SITE, src, allow)
    assert found and found[0]["count"] == 1, "the bare occurrence must still be reported"


def test_every_allow_entry_carries_a_justification():
    allow, _ = _load_allowlist()
    assert allow, "the allowlist must not be empty — the two legitimate senses exist"
    for e in allow:
        assert TERM in e["phrase"]
        assert len(e["why"]) > 40, f"{e['phrase']}: 'why' must explain the OTHER sense"
        for rel in e["files"]:
            assert (ROOT / rel).exists(), f"{e['phrase']}: {rel} does not exist"


def test_a_broken_allowlist_fails_closed(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"allow": [{"phrase": "披露", "files": ["x"], "why": "w"}]}),
                   encoding="utf-8")
    with pytest.raises(ValueError):
        _load_allowlist(bad)

    missing = tmp_path / "gone.json"
    with pytest.raises(OSError):
        _load_allowlist(missing)


# ── 3. Structural skips — comments, docstrings, correct copy ──────────────────

def test_correct_copy_is_silent():
    good = f"这不代表每项{FIX}都没有变化；请查看{FIX}轨迹。"
    assert scan_text("templates/x.html.j2", good, []) == []
    assert scan_python("engine/x.py", f'ZH = "{good}"\n', []) == []


def test_comments_and_docstrings_are_not_copy():
    """Writing the law down must not break the law."""
    src = (f'"""Sweep {TERM} to {FIX} in zh labels."""\n'
           f"# never write {TERM} in user-facing copy\n"
           f"def f():\n    '''{TERM} is a customs term.'''\n    return 1\n")
    assert scan_python("engine/x.py", src, []) == []


def test_site_and_data_are_out_of_scope():
    """Render output and collected upstream text are never scanned."""
    scanned = {rel.split("/", 1)[0] for rel, _, _ in _targets()}
    assert scanned == {"templates", "engine", "scripts"}
    assert not any(rel == "scripts/check_zh_filing_term.py" for rel, _, _ in _targets())


def test_unlicensed_counts_occurrences_not_lines():
    line = f"{TERM}轨迹 · {TERM}日期 · {TERM}表格"
    assert _unlicensed(line, "templates/x.html.j2", []) == 3


# ── 4. The pending ratchet cannot become a scheduled red ──────────────────────

def _with_pending(tmp_path, rel: str, budget: int, pr: int = 4765) -> Path:
    """The LIVE allowlist plus one synthetic pending entry for the probe file.

    Built on top of the real file rather than replacing it: a fixture that dropped
    the three live pending entries would make every one of these tests fail for the
    unrelated reason that fundamental_forensics is still in flight.
    """
    raw = json.loads((ROOT / "config" / "zh_filing_term_allowlist.json")
                     .read_text(encoding="utf-8"))
    raw["pending"] = list(raw.get("pending") or []) + [
        {"file": rel, "pr": pr, "max_occurrences": budget, "why": "synthetic fixture"}
    ]
    p = tmp_path / "pending.json"
    p.write_text(json.dumps(raw), encoding="utf-8")
    return p


def _about(rel: str, items: list) -> list:
    """Only the findings/notices that concern the probe file."""
    return [i for i in items if (i["file"] if isinstance(i, dict) else i).count(rel)]


def test_pending_file_at_budget_is_withheld(probe, tmp_path, monkeypatch):
    rel = probe(f"templates/{_tag('pend')}.html.j2", f"<p>{TERM}轨迹</p>\n")
    monkeypatch.setattr("scripts.check_zh_filing_term.ALLOWLIST",
                        _with_pending(tmp_path, rel, 1))
    findings, notices = scan()
    assert _about(rel, findings) == []
    assert _about(rel, notices) == []


def test_pending_file_over_budget_fails_hard(probe, tmp_path, monkeypatch):
    rel = probe(f"templates/{_tag('over')}.html.j2",
                f"<p>{TERM}轨迹</p>\n<p>{TERM}日期</p>\n")
    monkeypatch.setattr("scripts.check_zh_filing_term.ALLOWLIST",
                        _with_pending(tmp_path, rel, 1))
    findings, notices = scan()
    assert [f["line_no"] for f in _about(rel, findings)] == [1, 2], \
        "every line in the file must be reported once the budget is breached"
    assert [n.split("::")[1] for n in _about(rel, notices)] == \
        ["error title=zh-filing-term-pending"]


def test_pending_file_under_budget_only_notices(probe, tmp_path, monkeypatch):
    """The partial-landing case: PR removed some. A ::notice, never a red."""
    rel = probe(f"templates/{_tag('under')}.html.j2", f"<p>{TERM}轨迹</p>\n")
    monkeypatch.setattr("scripts.check_zh_filing_term.ALLOWLIST",
                        _with_pending(tmp_path, rel, 5))
    findings, notices = scan()
    assert _about(rel, findings) == []
    mine = _about(rel, notices)
    assert len(mine) == 1 and mine[0].startswith("::notice "), \
        "must start its line to be parsed by GitHub"
    assert "4 of 5" in mine[0]


def test_a_landed_pending_pr_does_not_red_main(probe, tmp_path, monkeypatch):
    """Count drops to zero (the fix merged). Stale entry ⇒ ::notice, exit 0.

    A guard that hard-fails on its own exemption becoming unnecessary is a red
    scheduled for whenever somebody else's PR lands.
    """
    rel = probe(f"templates/{_tag('landed')}.html.j2", f"<p>{FIX}轨迹</p>\n")
    monkeypatch.setattr("scripts.check_zh_filing_term.ALLOWLIST",
                        _with_pending(tmp_path, rel, 9))
    findings, notices = scan()
    assert _about(rel, findings) == []
    mine = _about(rel, notices)
    assert len(mine) == 1 and "has lost all of them" in mine[0]


def test_live_pending_entries_are_honest():
    """Each pending file exists, is at or under its frozen budget, and names a PR."""
    allow, pending = _load_allowlist()
    assert pending, "the three in-flight files are exempt via pending, not via allow"
    for rel, entry in pending.items():
        path = ROOT / rel
        assert path.exists(), f"pending {rel} is gone — drop the entry"
        found = sum(h["count"] for h in
                    scan_text(rel, path.read_text(encoding="utf-8"), allow))
        assert found <= entry["max_occurrences"], (
            f"{rel} carries {found} > budget {entry['max_occurrences']} — a NEW {TERM} "
            f"was added under the exemption for PR #{entry['pr']}"
        )
        assert isinstance(entry["pr"], int) and entry["pr"] > 0
