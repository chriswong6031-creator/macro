"""W8 Live Entry Radar reference-integrity — static + mutation battery.

These tests pin the REFERENCE package under mockups/refs/entry_radar/.
They must not be satisfied by a production templates/entry_radar.html.j2
(that file is forbidden until W9).
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
REF = REPO / "mockups" / "refs" / "entry_radar"
VERIFY = REF / "tools" / "verify.py"
MUTATE = REF / "tools" / "mutation_test.py"


def test_reference_tree_exists() -> None:
    for name in ("index.html", "radar.css", "radar.js", "radar-data.js",
                 "DESIGN_NOTES.md", "PINNED_PROPHET_REFERENCE.md",
                 "COMPONENT_INVENTORY.md", "STATE_INVENTORY.md",
                 "DATA_TO_UI_MAPPING.md", "W9_IMPLEMENTATION_HANDOFF.md",
                "CRITIQUE.md", "FINDING_DISPOSITIONS.md"):
        assert (REF / name).is_file(), name


def test_required_crops_exist() -> None:
    crops = REF / "crops"
    required = (
        "01-desktop-dark-en.png",
        "02-desktop-light-en.png",
        "03-desktop-dark-zh.png",
        "04-desktop-light-zh.png",
        "05-mobile390-dark-en.png",
        "06-mobile390-dark-zh.png",
        "07-mobile390-light-en.png",
        "10-quiet-dark-en.png",
        "20-stale-dark-en.png",
        "30-multi-dark-en.png",
        "40-invalidated-dark-en.png",
        "50-unavailable-dark-en.png",
        "51-partial-dark-en.png",
        "70-anon-dark-en.png",
    )
    for name in required:
        assert (crops / name).is_file(), name


def test_not_production_ui() -> None:
    assert not (REPO / "templates" / "entry_radar.html.j2").exists()
    assert not (REPO / "site" / "entry_radar.html").exists()


def test_pinned_prophet_sha() -> None:
    pin = (REF / "PINNED_PROPHET_REFERENCE.md").read_text(encoding="utf-8")
    assert "168a9be006914441051cff393927ce465e39138e" in pin
    assert "d540f493a097cb37f3f91e4c7bc81a39b876d069" in pin


def test_verify_static_green() -> None:
    proc = subprocess.run(
        [sys.executable, str(VERIFY)],
        cwd=str(REF),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_mutations_are_caught() -> None:
    proc = subprocess.run(
        [sys.executable, str(MUTATE)],
        cwd=str(REF),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "23/23 mutations caught" in proc.stdout
