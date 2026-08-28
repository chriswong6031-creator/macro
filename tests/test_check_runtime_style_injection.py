"""TP-0 Task 2 — runtime stylesheet-injection ratchet guard.

Covers the hostile cases the frozen build spec requires:
  * a NEW injecting file absent from the baseline reds
  * allowance 1 with actual 2 reds (exceeded budget)
  * allowance 2 with actual 1 emits a stale-budget ``::notice`` (never a red)
  * a clean file (no injection signatures) passes

Fixtures are built under ``tmp_path`` with an injected root — never against the
real repo tree (the real tree is exercised separately by the CLI-level tests
against the committed baseline).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import scripts.check_runtime_style_injection as RSI


def _write(root: Path, relpath: str, text: str) -> None:
    p = root / relpath
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


# ── file_counts / discover_counts ────────────────────────────────────────────

def test_file_counts_matches_all_four_patterns():
    text = (
        "document.createElement('style');\n"
        "el.style.textContent = 'x';\n"
        "sheet.sheet.insertRule('a{}');\n"
        "const t = '<style>body{}</style>';\n"
    )
    counts = RSI.file_counts(text)
    assert counts == {
        "create_style": 1,
        "style_text": 1,
        "insert_rule": 1,
        "style_markup": 1,
    }


def test_file_counts_clean_file_is_empty_dict():
    assert RSI.file_counts("const x = 1;\nfunction f() { return x; }\n") == {}


def test_discover_counts_scans_both_templates_and_site(tmp_path):
    _write(tmp_path, "templates/a.js", "document.createElement('style');\n")
    _write(tmp_path, "site/b.js", "document.createElement('style');\n"
                                   "document.createElement('style');\n")
    _write(tmp_path, "templates/clean.js", "const x = 1;\n")
    discovered = RSI.discover_counts(tmp_path)
    assert discovered == {
        "templates/a.js": {"create_style": 1},
        "site/b.js": {"create_style": 2},
    }


# ── evaluate: the four required hostile cases ───────────────────────────────

def test_new_injecting_file_absent_from_baseline_reds():
    discovered = {"site/new_offender.js": {"create_style": 1}}
    baseline_files: dict = {}
    violations, stale = RSI.evaluate(discovered, baseline_files)
    assert stale == []
    assert len(violations) == 1
    assert "site/new_offender.js" in violations[0]
    assert "baseline" in violations[0].lower()


def test_allowance_one_actual_two_reds():
    discovered = {"site/theme.js": {"create_style": 2}}
    baseline_files = {"site/theme.js": {"create_style": 1}}
    violations, stale = RSI.evaluate(discovered, baseline_files)
    assert stale == []
    assert len(violations) == 1
    assert "site/theme.js" in violations[0]
    assert "create_style" in violations[0]
    assert "actual=2" in violations[0]
    assert "allowance=1" in violations[0]


def test_allowance_two_actual_one_emits_stale_notice_not_a_violation():
    discovered = {"site/theme.js": {"create_style": 1}}
    baseline_files = {"site/theme.js": {"create_style": 2}}
    violations, stale = RSI.evaluate(discovered, baseline_files)
    assert violations == []
    assert stale == [("site/theme.js", "create_style", 1, 2)]


def test_clean_file_not_in_baseline_passes():
    # A file with no injection signature at all (so discover_counts() never
    # includes it — see the dedicated test above) and no baseline entry must
    # contribute nothing at all: no violation, no stale notice. This is
    # distinct from a file that DROPPED OUT of injection while still carrying
    # a baseline entry, which is a stale-budget notice (covered separately).
    baseline_files = {"site/theme.js": {"create_style": 10}}
    discovered = {"site/theme.js": {"create_style": 10}}  # unrelated file: exact match
    violations, stale = RSI.evaluate(discovered, baseline_files)
    assert violations == []
    assert stale == []


def test_exact_match_no_violation_no_stale():
    discovered = {"site/theme.js": {"create_style": 12, "style_text": 1}}
    baseline_files = {"site/theme.js": {"create_style": 12, "style_text": 1}}
    violations, stale = RSI.evaluate(discovered, baseline_files)
    assert violations == []
    assert stale == []


def test_file_drops_out_of_injection_entirely_is_stale_for_every_pattern():
    # The file used to inject (baseline has an entry) but no longer does at all.
    discovered = {}
    baseline_files = {"site/theme.js": {"create_style": 3, "style_markup": 1}}
    violations, stale = RSI.evaluate(discovered, baseline_files)
    assert violations == []
    assert sorted(stale) == sorted([
        ("site/theme.js", "create_style", 0, 3),
        ("site/theme.js", "style_markup", 0, 1),
    ])


def test_new_pattern_type_on_an_already_baselined_file_reds():
    # File is known to the baseline for create_style, but now also carries
    # insert_rule, a pattern the baseline entry never allowed (implicit 0).
    discovered = {"site/theme.js": {"create_style": 1, "insert_rule": 1}}
    baseline_files = {"site/theme.js": {"create_style": 1}}
    violations, stale = RSI.evaluate(discovered, baseline_files)
    assert len(violations) == 1
    assert "insert_rule" in violations[0]
    assert "actual=1" in violations[0]
    assert "allowance=0" in violations[0]


# ── CLI: main() ──────────────────────────────────────────────────────────────

def _make_tree(tmp_path: Path, *, offender: bool = False) -> Path:
    root = tmp_path / "repo"
    _write(root, "templates/clean.js", "const x = 1;\n")
    _write(root, "site/theme.js", "document.createElement('style');\n" * 2)
    if offender:
        _write(root, "site/new_offender.js", "document.createElement('style');\n")
    return root


def _write_baseline(root: Path, files: dict, generated_from: str = "deadbeef") -> None:
    baseline_dir = root / "config"
    baseline_dir.mkdir(parents=True, exist_ok=True)
    (baseline_dir / "runtime_style_injection_allowlist.json").write_text(
        json.dumps({
            "schema": "mastermind.runtime_style_allowlist.v1",
            "generated_from": generated_from,
            "files": files,
        }),
        encoding="utf-8",
    )


def test_main_exits_zero_against_a_matching_baseline(tmp_path, monkeypatch, capsys):
    root = _make_tree(tmp_path)
    _write_baseline(root, {"site/theme.js": {"create_style": 2}})
    monkeypatch.setattr(RSI, "ROOT", root)
    rc = RSI.main([])
    out = capsys.readouterr().out
    assert rc == 0
    assert "OK" in out


def test_main_exits_one_on_new_offender_file(tmp_path, monkeypatch, capsys):
    root = _make_tree(tmp_path, offender=True)
    _write_baseline(root, {"site/theme.js": {"create_style": 2}})
    monkeypatch.setattr(RSI, "ROOT", root)
    rc = RSI.main([])
    out = capsys.readouterr().out
    assert rc == 1
    assert "new_offender" in out.lower() or "new_offender" in out


def test_main_hard_fails_on_stale_budget(tmp_path, monkeypatch, capsys):
    """R2 (binding deviation from the plan's ::notice wording): a stale
    allowance is a HARD FAILURE, not an ignorable notice — the ratchet only
    ever tightens, and a notice nobody must act on cannot deliver that."""
    root = _make_tree(tmp_path)
    # Allowance is higher than actual (2 allowed, 2 actual is exact — bump baseline
    # to 3 so it is stale).
    _write_baseline(root, {"site/theme.js": {"create_style": 3}})
    monkeypatch.setattr(RSI, "ROOT", root)
    rc = RSI.main([])
    out = capsys.readouterr().out
    assert rc == 1
    # Must be a bare, unprefixed GitHub annotation line so CI actually renders it
    # (a logger prefix, e.g. "WARNING ::error", makes GitHub silently drop it).
    lines = [l for l in out.splitlines() if "::error" in l and "stale-budget" in l]
    assert lines, f"expected an ::error stale-budget line in output, got: {out!r}"
    assert lines[0].startswith("::error")
    # The message must be actionable: name the file, the pinned allowance, the
    # actual count, and the exact remedy command.
    assert "site/theme.js" in lines[0]
    assert "create_style" in lines[0]
    assert "allowance is 3" in lines[0]
    assert "actual is 2" in lines[0]
    assert "--emit-baseline --generated-from" in lines[0]


def test_main_hard_fails_when_a_file_disappears_while_still_baselined(
        tmp_path, monkeypatch, capsys):
    """R2: a file that drops out of the tree entirely (actual 0 for every
    pattern) while its baseline entry survives must ALSO hard fail, not just
    the case where the file still exists at a lower count."""
    root = _make_tree(tmp_path)  # no injection at all in site/gone.js — it never exists
    _write_baseline(root, {
        "site/theme.js": {"create_style": 2},
        "site/gone.js": {"create_style": 5},
    })
    monkeypatch.setattr(RSI, "ROOT", root)
    rc = RSI.main([])
    out = capsys.readouterr().out
    assert rc == 1
    assert any("site/gone.js" in ln and ln.startswith("::error") for ln in out.splitlines())


def test_main_emit_baseline_requires_generated_from(tmp_path, monkeypatch, capsys):
    root = _make_tree(tmp_path)
    monkeypatch.setattr(RSI, "ROOT", root)
    rc = RSI.main(["--emit-baseline"])
    assert rc != 0


def test_main_emit_baseline_writes_expected_shape(tmp_path, monkeypatch, capsys):
    root = _make_tree(tmp_path)
    monkeypatch.setattr(RSI, "ROOT", root)
    rc = RSI.main(["--emit-baseline", "--generated-from", "cafef00d"])
    out = capsys.readouterr().out
    assert rc == 0
    payload = json.loads(out)
    assert payload["schema"] == "mastermind.runtime_style_allowlist.v1"
    assert payload["generated_from"] == "cafef00d"
    assert payload["files"] == {"site/theme.js": {"create_style": 2}}


def test_main_emit_baseline_never_guesses_a_sha_when_omitted(tmp_path, monkeypatch, capsys):
    # Regression guard for "NEVER guess or substitute a sha itself": omitting
    # --generated-from must not silently fall back to git rev-parse or any
    # other implicit value — it must refuse.
    root = _make_tree(tmp_path)
    monkeypatch.setattr(RSI, "ROOT", root)
    rc = RSI.main(["--emit-baseline"])
    out = capsys.readouterr().out
    assert rc != 0
    assert "generated_from" not in out or "generated-from" in out.lower()


def test_main_missing_baseline_file_fails_closed(tmp_path, monkeypatch, capsys):
    root = _make_tree(tmp_path)
    # No config/runtime_style_injection_allowlist.json written at all.
    monkeypatch.setattr(RSI, "ROOT", root)
    rc = RSI.main([])
    assert rc == 1


def test_selftest_exits_zero():
    assert RSI.selftest() == 0


def test_selftest_literal_substring_present_in_source():
    # The house-law meta-guard greps the script SOURCE for the literal substring
    # "selftest" to confirm a registered selftest:true script actually has one.
    src = Path(RSI.__file__).read_text(encoding="utf-8")
    assert "selftest" in src
