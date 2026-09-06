"""release_hold_text neutralizes Sol-era holds the way the merge-on-green sweeper reads them."""
from __future__ import annotations

import importlib.util
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import merge_on_green as mog  # noqa: E402

_spec = importlib.util.spec_from_file_location("release_hold_text", ROOT / ".claude" / "workflows" / "release_hold_text.py")
rht = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(rht)


def test_title_marker_is_stripped_and_sweeper_agrees():
    for title in (
        "HOLD-FOR-SOL — [F01][R1] Macro & Monetary hub",
        "HOLD-FOR-SOL: F04-X1 WTI Live Trace",
        "[DRAFT / HOLD-FOR-SOL] F02-X1 official sanctions geography",
        "[F10-X1] HOLD-FOR-SOL: Research implication cards",
        "[MARKET OS][REVIEW APPROVED][HOLD-FOR-SOL] MSFT security_state owner composition",
        "HOLD-FOR-SOL: feat(special-situations): evidence-bound cash-deal premium (F09-1)",
    ):
        clean = rht.neutralize_title(title)
        assert "HOLD-FOR" not in clean.upper()
        assert clean.strip()
        assert mog.recorded_hold("plain body", [], clean) is None


def test_body_hold_lines_are_released_and_sweeper_agrees():
    body = "## HOLD-FOR-SOL — do not merge\n\nsome text\n\n**HOLD-FOR-SOL — DRAFT. Do not mark ready.**\n"
    assert mog.recorded_hold(body, [], "x")
    out = rht.neutralize_body(body, "2026-09-06", "A")
    assert mog.recorded_hold(out, [], "x") is None
    assert "some text" in out
    assert rht.RELEASE_SENTINEL in out


def test_neutralize_is_idempotent():
    body = "HOLD-FOR-SOL — do not merge\n"
    once = rht.neutralize_body(body, "2026-09-06", "B")
    twice = rht.neutralize_body(once, "2026-09-06", "B")
    assert once == twice
