#!/usr/bin/env python3
"""Rebuild templates/fonts/Outfit-latin.woff2 — the landing + onboarding display face.

Run from the repo root:

    python3 mockups/refs/landing-modern-sans/build_outfit_subset.py

Writes `templates/fonts/Outfit-latin.woff2` and copies it to `site/fonts/`
(both are tracked; site/fonts is what actually ships). Requires `fonttools[woff]`.

Three things this script does that a plain `pyftsubset` call would not, each of
which is load-bearing — see the module docstring notes below.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]

# Outfit, SIL Open Font License 1.1 (Smartsheet / Rodrigo Fuenzalida).
SRC_URL = "https://raw.githubusercontent.com/google/fonts/main/ofl/outfit/Outfit%5Bwght%5D.ttf"

# Mirrors the range the retired Archivo-latin.woff2 carried, EXACTLY. Keeping the
# boundary identical means the swap changes the display face and nothing else:
# every symbol that used to fall through to the system stack (→ ⓘ ⚡ ✓ ✗ and all
# CJK) still falls through, so no glyph on the page silently changes shape.
UNICODES = (
    "U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,"
    "U+0304,U+0308,U+0329,U+2000-206F,U+20AC,U+2122,U+2191,U+2193,"
    "U+2212,U+2215,U+FEFF,U+FFFD"
)

OUT = REPO / "templates" / "fonts" / "Outfit-latin.woff2"
MIRROR = REPO / "site" / "fonts" / "Outfit-latin.woff2"


def make_figures_tabular_by_default(font) -> None:
    """Point the digit codepoints at Outfit's *tabular* glyphs in `cmap`.

    Outfit's default figures are PROPORTIONAL — all ten digits have different
    advances (13.45px of spread at 48px/800). The face this replaces (Archivo)
    was tabular by default, so every price column, ticker cell and the live
    gauge score on the landing silently depends on fixed-width digits: without
    this, `#gz-score` jitters as it counts up and every `$…` column goes ragged.

    Baking the feature in beats adding `font-variant-numeric` to ~80 CSS rules:
    it cannot be forgotten on the one rule that matters, and it keeps the swap
    behaviour-preserving. `pnum` still maps back to proportional for anyone who
    ever wants it, so nothing is actually lost.
    """
    gsub = font["GSUB"].table
    mapping: dict[str, str] = {}
    for rec in gsub.FeatureList.FeatureRecord:
        if rec.FeatureTag != "tnum":
            continue
        for idx in rec.Feature.LookupListIndex:
            for sub in gsub.LookupList.Lookup[idx].SubTable:
                mapping.update(getattr(sub, "mapping", {}) or {})
    if len(mapping) != 10:
        sys.exit(f"expected 10 tnum substitutions, found {len(mapping)}: {mapping}")

    remapped = 0
    for table in font["cmap"].tables:
        for cp, glyph in list(table.cmap.items()):
            if 0x30 <= cp <= 0x39 and glyph in mapping:
                table.cmap[cp] = mapping[glyph]
                remapped += 1
    print(f"  tabular figures: remapped {remapped} cmap entries")


def main() -> None:
    # Set BEFORE fontTools is imported or any save happens: head.modified is
    # re-stamped by every TTFont.save(), the parent's included, so exporting it
    # only for the subsetter subprocess still left the build non-deterministic
    # (three runs: 41,480 / 41,568 / 41,652 bytes).
    os.environ["SOURCE_DATE_EPOCH"] = "0"

    from fontTools import ttLib
    from fontTools.varLib import instancer

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        src = tmp / "Outfit[wght].ttf"
        print(f"fetching {SRC_URL}")
        with urllib.request.urlopen(SRC_URL) as resp:
            src.write_bytes(resp.read())

        font = ttLib.TTFont(src)
        # Deterministic output. fontTools stamps head.modified with the build
        # time, so two runs of this script over identical input produce
        # different bytes (observed: 41,512 / 41,640 / 41,852). That would make
        # the digest this build is pinned to in
        # tests/test_check_font_ui_defined.py flaky-by-construction, and it
        # makes "did the font actually change?" unanswerable from a diff.
        # SOURCE_DATE_EPOCH is fontTools' own reproducible-build knob.
        font["head"].created = font["head"].modified = 0
        # A TUPLE is partial instancing: the wght axis stays LIVE. A scalar would
        # pin it and silently kill every interpolated weight the CSS asks for —
        # the landing drives 400/500/600/650/700/800/900, and 650 (.stg) exists
        # only by interpolation.
        instancer.instantiateVariableFont(
            font, {"wght": (400, 900)}, inplace=True, updateFontNames=False
        )
        make_figures_tabular_by_default(font)
        clipped = tmp / "clipped.ttf"
        font.save(clipped)

        OUT.parent.mkdir(parents=True, exist_ok=True)
        # --layout-features='*' keeps `rvrn` (Required Variation Alternates), which
        # variable rendering needs, and which an allow-list would quietly drop.
        # SOURCE_DATE_EPOCH is set HERE rather than left to the caller: the
        # subsetter re-saves the font and re-stamps head.modified, so without it
        # the output is non-deterministic even though we zeroed the timestamps
        # above (two runs differed by 128 bytes).
        subprocess.run(
            [
                sys.executable, "-m", "fontTools.subset", str(clipped),
                f"--output-file={OUT}", "--flavor=woff2",
                f"--unicodes={UNICODES}", "--layout-features=*",
                "--no-hinting", "--desubroutinize",
            ],
            check=True,
            env={**os.environ, "SOURCE_DATE_EPOCH": "0"},
        )

    shutil.copy2(OUT, MIRROR)

    # ── verify the two properties the landing silently depends on ────────────
    check = ttLib.TTFont(OUT)
    axes = {a.axisTag: (a.minValue, a.maxValue) for a in check["fvar"].axes}
    assert axes == {"wght": (400.0, 900.0)}, f"wght axis did not survive: {axes}"

    cmap: dict[int, str] = {}
    for table in check["cmap"].tables:
        cmap.update(table.cmap)
    advances = {check["hmtx"][cmap[cp]][0] for cp in range(0x30, 0x3A)}
    assert len(advances) == 1, (
        f"digits are NOT tabular — {len(advances)} distinct advances {sorted(advances)}. "
        f"The live gauge score would jitter and every price column would go ragged."
    )

    digest = hashlib.sha256(OUT.read_bytes()).hexdigest()
    print(f"\nwrote {OUT.relative_to(REPO)} ({OUT.stat().st_size:,} bytes)")
    print(f"  mirrored to {MIRROR.relative_to(REPO)}")
    print(f"  axes            : {axes}")
    print(f"  digit advance   : {advances.pop()} (all ten identical — tabular)")
    print(f"  sha256          : {digest}")
    print(
        "\nIf this digest changed, update it in "
        "tests/test_check_font_ui_defined.py::"
        "test_display_face_figures_are_tabular_by_default"
    )


if __name__ == "__main__":
    main()
