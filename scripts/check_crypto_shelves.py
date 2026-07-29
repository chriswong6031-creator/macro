"""Structural governor for the BTC Vector and Crypto Cockpit Tier-1 shelves.

The script lands in W0 and arms per template when that template contains its
first ``data-shelf`` marker. Once armed, the marker set must be exact: no
missing, extra, or duplicate shelf roots. Vector must also contain exactly one
``data-verdict``. This lets the old template pass W0 while making a partial W1
migration fail loudly.

Usage:
    python scripts/check_crypto_shelves.py
    python scripts/check_crypto_shelves.py --selftest
"""
from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SHELF_RE = re.compile(r"""\bdata-shelf\s*=\s*["']([^"']+)["']""")
VERDICT_RE = re.compile(r"""\bdata-verdict(?:\s*=\s*["'][^"']*["'])?""")
COMMENT_RE = re.compile(r"<!--.*?-->|{#.*?#}", re.DOTALL)


@dataclass(frozen=True)
class Surface:
    name: str
    path: Path
    expected_shelves: tuple[str, ...]
    expected_verdicts: int | None


SURFACES = (
    Surface(
        "vector",
        ROOT / "templates" / "vector.html.j2",
        tuple(f"S{i}" for i in range(1, 7)),
        1,
    ),
    Surface(
        "crypto",
        ROOT / "templates" / "crypto.html.j2",
        tuple(f"H{i}" for i in range(1, 9)),
        None,
    ),
)


def audit_text(
    text: str,
    expected_shelves: tuple[str, ...],
    expected_verdicts: int | None,
) -> list[str]:
    """Return structural errors; an unmarked legacy template is not armed."""
    source = COMMENT_RE.sub("", text)
    shelves = SHELF_RE.findall(source)
    if not shelves:
        return []

    errors = []
    expected = set(expected_shelves)
    actual = set(shelves)
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    duplicates = sorted({shelf for shelf in shelves if shelves.count(shelf) > 1})
    if missing:
        errors.append(f"missing shelves: {', '.join(missing)}")
    if extra:
        errors.append(f"unexpected shelves: {', '.join(extra)}")
    if duplicates:
        errors.append(f"duplicate shelf roots: {', '.join(duplicates)}")

    if expected_verdicts is not None:
        verdicts = len(VERDICT_RE.findall(source))
        if verdicts != expected_verdicts:
            errors.append(
                f"expected {expected_verdicts} data-verdict marker, found {verdicts}"
            )
    return errors


def check_surface(surface: Surface) -> bool:
    if not surface.path.exists():
        print(
            f"::notice title=Crypto shelf governor::{surface.name} template not present; "
            "governor remains unarmed",
            flush=True,
        )
        return True

    text = surface.path.read_text(encoding="utf-8")
    if not SHELF_RE.search(text):
        print(
            f"::notice title=Crypto shelf governor::{surface.name} has no shelf markers; "
            "governor remains unarmed until its rebuild wave",
            flush=True,
        )
        return True

    errors = audit_text(
        text, surface.expected_shelves, surface.expected_verdicts
    )
    for error in errors:
        print(
            f"::error title=Crypto shelf governor::{surface.name}: {error}",
            flush=True,
        )
    if not errors:
        print(
            f"crypto shelf governor OK — {surface.name}: "
            f"{', '.join(surface.expected_shelves)}",
            flush=True,
        )
    return not errors


def selftest() -> int:
    cases = (
        ("legacy-unarmed", "<main></main>", ("S1", "S2"), 1, []),
        (
            "exact",
            '<section data-shelf="S1"></section><section data-shelf="S2" '
            "data-verdict></section>",
            ("S1", "S2"),
            1,
            [],
        ),
        (
            "partial",
            '<section data-shelf="S1" data-verdict></section>',
            ("S1", "S2"),
            1,
            ["missing shelves: S2"],
        ),
        (
            "duplicate",
            '<i data-shelf="S1"></i><i data-shelf="S1"></i>'
            '<i data-shelf="S2" data-verdict></i>',
            ("S1", "S2"),
            1,
            ["duplicate shelf roots: S1"],
        ),
        (
            "extra-and-verdict",
            '<i data-shelf="S1"></i><i data-shelf="S2"></i>'
            '<i data-shelf="S3"></i>',
            ("S1", "S2"),
            1,
            ["unexpected shelves: S3", "expected 1 data-verdict marker, found 0"],
        ),
        (
            "comments-do-not-count",
            '<!-- data-shelf="S9" data-verdict -->'
            '<i data-shelf="S1"></i><i data-shelf="S2" data-verdict></i>',
            ("S1", "S2"),
            1,
            [],
        ),
    )
    failed = []
    for name, text, shelves, verdicts, expected in cases:
        actual = audit_text(text, shelves, verdicts)
        if actual != expected:
            failed.append(f"{name}: expected {expected!r}, got {actual!r}")
    if failed:
        for error in failed:
            print(f"::error title=Crypto shelf governor selftest::{error}", flush=True)
        return 1
    print("crypto shelf governor selftest OK — 6 cases", flush=True)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()
    if args.selftest:
        return selftest()
    results = [check_surface(surface) for surface in SURFACES]
    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
