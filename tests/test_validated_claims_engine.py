"""BC-2: the engine-source half of the 'validated' gate (scripts/check_validated_claims).

WHAT THIS PINS. Until #3790, BC-2 scanned only rendered surfaces, so copy authored in
engine/ was gated only once a nightly render carried it onto a page — a day late, on a
PR that did not write it, with main red on ci-pack-0 and every open PR inheriting the
failure. scan_python_copy closes that latency.

The load-bearing case is `test_the_3765_defect_fires_at_the_engine_source`: the original
defect put the field name and the token on DIFFERENT LINES, so a same-line grep rule
would have missed the very thing it was written for. That test is the reason the scan
parses instead of grepping — if someone ever swaps the AST walk for a regex, it fails.

Everything asserts through the REAL gate (scan_python_copy + the live allowlist), never
a substring match, so negation, allowlist and structural semantics stay in one place.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from scripts.check_validated_claims import (
    PY_COPY_GLOBS,
    _copy_strings,
    _is_copy_field,
    _load_allowlist,
    scan_python_copy,
)

ROOT = Path(__file__).resolve().parent.parent
ALLOW = _load_allowlist()


def _fires(src: str) -> bool:
    """Does the gate report an unearned claim in this engine source?"""
    found, _ = scan_python_copy("engine/_probe.py", src, ALLOW)
    return bool(found)


# ── the incident ─────────────────────────────────────────────────────────────────────

# engine/intl_recovery_quality.macro_backdrop as #3765 shipped it. Verbatim: the token
# sits on a bare continuation line with no field name anywhere on it.
_PRE_FIX_3765 = '''
def macro_backdrop() -> dict:
    return {
        "read_en": (
            "Macro backdrop is shown separately from the price state. Validated HK "
            "rate/FX pressure lives in the pullback radar; Iran/oil and the midterm "
            "calendar remain unscored context."
        ),
        "display_only": True,
    }
'''

# The #3790 repair — "Measured", the term the module's own rates item already uses.
_POST_FIX_3790 = _PRE_FIX_3765.replace(
    "Validated HK \"\n            \"rate/FX pressure lives in",
    "Measured HK \"\n            \"rate/FX pressure is carried by",
)


def test_the_3765_defect_fires_at_the_engine_source():
    """The exact string that reddened main on 2026-07-27, caught at its own PR."""
    assert _fires(_PRE_FIX_3765)


def test_the_3790_repair_passes():
    assert _POST_FIX_3790 != _PRE_FIX_3765, "fixture rot: the replace matched nothing"
    assert not _fires(_POST_FIX_3790)


def test_a_same_line_rule_would_have_missed_it():
    """Why the scan parses instead of grepping.

    No line of the defect carries BOTH a display-copy field name and the token, so any
    'field name and validated on one line' rule scores zero on it. This test fails the
    moment someone replaces the AST walk with a line-scoped regex.
    """
    lines = _PRE_FIX_3765.splitlines()
    both = [ln for ln in lines
            if "validated" in ln.lower()
            and any(f'"{f}"' in ln for f in ("read_en", "read_zh", "label_en", "detail_en"))]
    assert both == [], f"fixture rot — the token is no longer on a bare line: {both}"
    assert _fires(_PRE_FIX_3765), "but the real gate still catches it"


# ── field restriction: the rule that keeps 509 findings down to a real one ────────────

@pytest.mark.parametrize("src", [
    'X = {"label_zh": "已验证的选股优势"}',                       # zh token
    'P = RadarProfile(caveat_en="This sleeve is validated on HK breadth.")',
    'note = f"validated macro gauge ({band})"',                    # f-string literal part
    'D = {"summary_en": "A" + " validated edge" + " here."}',      # + concatenation
    'D = {"detail_en": "validated edge" if hot else "no read"}',   # ternary branch
    'obj.headline_en = "A validated cross-sectional alpha."',      # attribute assign
    'd["blurb_zh"] = "已验证的方向性优势"',                          # subscript assign
])
def test_display_copy_shapes_are_scanned(src):
    assert _fires(src), f"display copy went ungated: {src}"


@pytest.mark.parametrize("src", [
    'row = {"validated": True, "tier": "scored"}',                 # data field
    'row = {"verdict": "validated"}',                              # enum value
    'validated_tag = compute()',                                   # identifier
    'if verdict == "validated": ship()',                           # comparison
    '_row(notes="W4-C7 VERDICT: validated at index level, do NOT wire")',   # registry
    'TOOL = {"description": "Read the validated mechanism-pathways artifact."}',  # LLM schema
    'CLS = "chip validated"',                                      # css token
    '# the parabolic flag (ext_z>2, validated -94% DD) blocks independently',  # comment
])
def test_engine_internals_are_out_of_scope(src):
    """BC-2 targets DISPLAYED CLAIMS. Whole-file scanning engine/ surfaces 509 findings,
    essentially all of this shape; the field rule is what makes the gate usable."""
    assert not _fires(src), f"false positive on engine internals: {src}"


def test_negated_engine_copy_is_not_a_claim():
    assert not _fires('{"detail_en": "HK has no validated selection edge; context only."}')
    assert not _fires('{"caveat_zh": "此处无已验证方向信号。"}')


def test_unparseable_source_fails_closed():
    """A file the gate cannot read must not be silently exempt."""
    found, _ = scan_python_copy("engine/_probe.py", "def broken(:\n", ALLOW)
    assert found and "UNPARSEABLE" in found[0]["text"]


# ── wiring: the guard is worthless if the trigger never reaches it ───────────────────

def test_engine_is_actually_in_the_scan_surfaces():
    assert any(sub == "engine" and "*.py" in pats for sub, pats in PY_COPY_GLOBS)


def test_ci_triggers_on_engine_changes():
    """ci.yml must list engine/** or an engine-only PR never runs this gate."""
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert '"engine/**"' in ci


def test_the_live_engine_tree_is_clean():
    """Every display-copy 'validated' in engine/ today is backed. Ships with no debt."""
    misses = []
    for f in sorted((ROOT / "engine").rglob("*.py")):
        found, _ = scan_python_copy(f.relative_to(ROOT).as_posix(),
                                    f.read_text(encoding="utf-8"), ALLOW)
        misses.extend(found)
    assert misses == [], f"unearned engine claims: {misses}"


# ── the de-escalation shipped with this change ───────────────────────────────────────

def test_flow_signing_direction_note_is_de_escalated():
    """What cleared the bar is a signing-ACCURACY calibration, not a gauntleted edge.

    Asserted on the ENGINE's emitted string so a re-escalation fails here, at the source,
    rather than on a page far from the edit a render later.
    """
    from engine import flow_signing

    v = flow_signing.verdict({}, {"net_sign_recovery": 0.91}, bar=0.70)
    assert v["direction_reliable"] is True
    assert "validated" not in v["note"].lower()
    assert "RELIABLE" in v["note"]
    assert not _fires(f'{{"note": {v["note"]!r}}}')


# ── the new allowlist entries are live, not decorative ───────────────────────────────

_NEW_ENTRY_MATCHES = [
    "Validated but modest: China drawdowns are led by",
    "已验证但偏温和：A股回撤由美债利率冲击",
    "Validated forward-drawdown composite on external drivers",
    "validated per-name extension brake",
    "已验证的个股延展刹车",
    "已验证状态计的宏观倾斜",
    "Validated — pending wiring on this branch",
    "已验证 — 本分支待接入",
    "validated macro-stress drawdown gauge",
]


@pytest.mark.parametrize("match", _NEW_ENTRY_MATCHES)
def test_each_new_allowlist_entry_still_covers_real_engine_copy(match):
    """An entry whose copy was reworded is a claim of record with nothing under it.

    The gate going green does not distinguish 'backed' from 'the string moved', so pin
    each entry to a live engine string. If copy changes, re-justify the entry or drop it.
    """
    entry = next((e for e in ALLOW if e["match"] == match), None)
    assert entry is not None, f"allowlist entry vanished: {match}"
    assert entry.get("backing"), "an entry must cite an artifact or documented study"

    needle = match.lower()
    for f in (ROOT / "engine").rglob("*.py"):
        tree = ast.parse(f.read_text(encoding="utf-8"))
        for field, node in _copy_strings(tree):
            if needle in node.value.lower():
                assert _is_copy_field(field)
                return
    pytest.fail(f"no engine display-copy string matches {match!r} — entry is dead")
