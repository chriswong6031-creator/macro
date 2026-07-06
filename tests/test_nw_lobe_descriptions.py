"""Never-stale guard for the admin Neural-Web lobe descriptions.

The lobe REGISTRY is derived live from config/synapse.yml, so new lobes appear
automatically and structural changes are always reflected. The curated PROSE
(admin/nw_lobe_descriptions.py) is the only hand-written layer; these tests make
sure it can never SILENTLY go stale:

  * test_no_drift            HARD FAIL — a lobe's synapse note changed but its
                             plain-English description was not refreshed.
  * test_coverage_or_auto    every lobe either has curated prose or renders an
                             auto-summary (never blank); missing prose is reported.
  * test_drift_is_detected   positive control: a changed note IS flagged 'stale'.

Fix a drift by refreshing the prose in admin/nw_lobe_descriptions.py, then run
`python scripts/nw_lobe_desc_audit.py --update`.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from admin import neural_web  # noqa: E402
from admin.nw_lobe_descriptions import LOBE_DESCRIPTIONS, SCHEMA_VERSION  # noqa: E402

FIX = "refresh prose in admin/nw_lobe_descriptions.py, then run `python scripts/nw_lobe_desc_audit.py --update`"


def _notes() -> dict:
    return {lid: (art.get("notes") or "") for lid, art in neural_web.nw_scoped_lobes().items()}


def test_module_schema():
    assert isinstance(SCHEMA_VERSION, int)
    assert isinstance(LOBE_DESCRIPTIONS, dict) and LOBE_DESCRIPTIONS
    for lid, e in LOBE_DESCRIPTIONS.items():
        assert set(e) >= {"short", "full", "src_fp"}, f"{lid} missing keys"
        assert isinstance(e["short"], str) and isinstance(e["full"], str)


def test_no_drift():
    """Every curated description's fingerprint must match its current synapse note."""
    notes = _notes()
    drifted = [
        lid for lid, e in LOBE_DESCRIPTIONS.items()
        if lid in notes and e.get("short")
        and e.get("src_fp") != neural_web._note_fingerprint(notes[lid])
    ]
    assert not drifted, (
        f"{len(drifted)} lobe description(s) are STALE (synapse note changed since the prose "
        f"was written): {', '.join(sorted(drifted))}. {FIX}"
    )


def test_coverage_or_auto():
    """No lobe is ever blank: it has curated prose or a non-empty auto-summary.
    Missing curated prose is reported (not a hard fail — auto-summaries keep the
    surface honest; run the audit's --strict to gate on this too)."""
    notes = _notes()
    missing = []
    for lid, note in notes.items():
        e = LOBE_DESCRIPTIONS.get(lid)
        if e and e.get("short"):
            continue
        missing.append(lid)
        short, full, status = neural_web._plain_desc(lid, note)
        assert status == "auto"
        assert short, f"{lid} has no curated prose AND an empty auto-summary"
    if missing:
        print(f"\n{len(missing)} lobe(s) on auto-summaries (add prose to upgrade): {', '.join(sorted(missing))}")


def test_no_orphan_descriptions():
    """Descriptions for lobes no longer in scope are reported (audit --update drops them)."""
    orphans = sorted(set(LOBE_DESCRIPTIONS) - set(_notes()))
    if orphans:
        print(f"\n{len(orphans)} orphaned description(s) (run audit --update to drop): {', '.join(orphans)}")


def test_plain_language():
    """Curated prose stays readable: no file paths / code identifiers / line refs."""
    bad = re.compile(r"\S+\.(?:py|json|jsonl|parquet|yml|yaml)\b|\b\w+/\w+/|:\d{3,}\b")
    offenders = []
    for lid, e in LOBE_DESCRIPTIONS.items():
        if e.get("short") and bad.search(e["short"] + " " + e["full"]):
            offenders.append(lid)
    assert not offenders, (
        f"{len(offenders)} description(s) contain file paths / code jargon — keep it plain: "
        f"{', '.join(sorted(offenders))}"
    )


def test_drift_is_detected():
    """Positive control — the guard has teeth: a changed note flips status to 'stale',
    and an unknown lobe falls back to 'auto'."""
    notes = _notes()
    curated = [lid for lid, e in LOBE_DESCRIPTIONS.items() if lid in notes and e.get("short")]
    assert curated, "no curated lobe to test against"
    lid = curated[0]
    # current note → curated
    _, _, status_now = neural_web._plain_desc(lid, notes[lid])
    assert status_now == "curated"
    # mutated note → stale
    _, _, status_changed = neural_web._plain_desc(lid, notes[lid] + " (an edit that changes the note)")
    assert status_changed == "stale"
    # unknown lobe → auto
    _, _, status_unknown = neural_web._plain_desc("__no_such_lobe__", "some note")
    assert status_unknown == "auto"


def test_descriptions_module_no_engine_imports():
    """The generated data module must stay pure data (no engine/scripts imports)."""
    src = (ROOT / "admin" / "nw_lobe_descriptions.py").read_text(encoding="utf-8")
    for bad in ("from engine", "import engine", "from scripts", "import scripts", "subprocess"):
        assert bad not in src, f"unexpected {bad!r} in nw_lobe_descriptions.py"
