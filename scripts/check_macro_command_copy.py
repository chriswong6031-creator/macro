#!/usr/bin/env python3
"""scripts/check_macro_command_copy.py — Macro Command copy guard.

Frozen spec (F01 Macro Command, 2026-09-06) §5 "Copy law" + §9 P1 acceptance:
Macro Command (`site/macro_monetary.html`) is the single customer-facing
dashboard for the fourteen `macro_*` research workspaces, and the FRONT-END
CLARITY LAW (CLAUDE.md "Design (user-first law)") forbids machine text — raw
slugs, internal state/study names, untranslated stat names, bare timestamps —
anywhere a non-quant reader's eye lands. G2 makes that mechanically true:
zero occurrences of the banned vocabulary OUTSIDE a
`<details class="mc-details">` subtree or a `class="mc-primer"` body, in
either theme or language. G2b adds one more shape: no bare `YYYY-MM-DD` /
`YYYY-MM-DDTHH:MM` in visible text without an immediately preceding plain
word — every as-of the page shows must read "Data to 3 Sep 2026" /
"数据截至 2026年9月3日" in the TEXT, with the machine value living only in
`datetime=`.

This guard ships in P1 (frozen spec §9 P1 standing note: "the guard ships in
P1, not at the end, because a customer-visible page that is ungated against
the FRONT-END CLARITY LAW cannot lawfully be reviewed PASS") even though P1
itself ships no stance/primer/Read/chip copy — later packets (P2-P5) populate
that copy and this guard is what keeps it honest as it lands.

Usage:
    python3 scripts/check_macro_command_copy.py
        # scan the built site/macro_monetary.html; exit 1 on any violation
    python3 scripts/check_macro_command_copy.py path/to/some.html
        # scan an arbitrary built HTML file instead (used by the test suite
        # against a freshly rendered page in a tmp_path, and available for a
        # later packet's deep-link pages)
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TARGET = ROOT / "site" / "macro_monetary.html"
LABELS_PATH = ROOT / "lib" / "macro_suite_labels.py"

# §5's banned-substring CI list, verbatim from the frozen spec's table
# footer. Case-sensitive and taken literally — the spec lists both cases of
# a word ("axis"/"Axis", "vector"/"Vector") exactly where it wants both
# banned, and leaves the other case alone where it does not.
BANNED_SUBSTRINGS: tuple[str, ...] = (
    "accepted print", "accepted snapshot", "method version", "method-comparable",
    "hysteresis", "axis", "Axis", "authority ceiling", "content hash",
    "generation id", "producer", "artifact", "manifest", "trace_ref",
    "definition_id", "owner_ref", "standardized", "Diagnostics", "Vector",
    "vector", "snapshot", "deterministic", "schema", "Regime map", "Freshness",
    "Presence", "coverage_ratio", "null_reason",
)

# Falsifier/refutation vocabulary is never front-facing (CLAUDE.md "Design
# (user-first law)", #3821 — tripwires keep evaluating in the background,
# but user surfaces never say "falsifier fired / thesis refuted / 证伪").
# Not itself a row in the frozen spec's §5 table, but exactly the shape of
# internal-study-name leak G2 exists to catch, and named explicitly in this
# packet's own commission.
FALSIFIER_SUBSTRINGS: tuple[str, ...] = ("falsifier", "refuted", "证伪")

# G2b — no bare timestamp in visible text. A YYYY-MM-DD with no immediately
# preceding plain word (a letter followed by a space), or any ISO
# "T\d\d:\d\d" fragment at all — the datetime separator has no legitimate
# reason to reach visible text; the machine value belongs only in
# `datetime=`, which tag-stripped visible text never sees in the first place.
_BARE_DATE_RE = re.compile(r'(?<![A-Za-z\u4e00-\u9fff][ \u00a0])\d{4}-\d{2}-\d{2}')
_ISO_TIME_RE = re.compile(r'T\d{2}:\d{2}')

_DETAILS_RE = re.compile(r'<details\s+class="mc-details"[^>]*>.*?</details>', re.S)
_PRIMER_RE = re.compile(r'<details\s+class="mc-primer"[^>]*>.*?</details>', re.S)
_SCRIPT_RE = re.compile(r'<script\b[^>]*>.*?</script>', re.S)
_TAG_RE = re.compile(r'<[^>]+>')

# Every ALL-CAPS closed-vocabulary dict key in lib/macro_suite_labels.py
# (§5 row 61: "CURRENT", "WARMUP", "SOURCE_FAILED", ... — "must never reach
# screen"). Matched as a dict-key assignment line so a stray all-caps English
# word elsewhere in the module's prose docstrings is never mistaken for a
# closed-vocabulary token.
_LABEL_TOKEN_RE = re.compile(r'^\s*"([A-Z][A-Z0-9_]{2,})":\s', re.M)


def _closed_vocabulary_tokens() -> tuple[str, ...]:
    """Read the closed-vocabulary tokens from source rather than duplicating
    them by hand, so the guard tracks `lib/macro_suite_labels.py` as it grows
    in P2+. Returns an empty tuple (never raises) if the module cannot be
    read — a missing file is a different, louder failure elsewhere."""
    try:
        text = LABELS_PATH.read_text(encoding="utf-8")
    except OSError:
        return ()
    return tuple(sorted(set(_LABEL_TOKEN_RE.findall(text))))


def reading_path_text(html: str) -> str:
    """The page's reading path: the built HTML with every `<script>`,
    `<details class="mc-details">` and `<details class="mc-primer">`
    subtree removed (G2 — those are the two places machine text and primer
    copy may legitimately live), then every remaining tag stripped so
    attribute values (`id=`, `href=`, `datetime=`) never feed the
    banned-substring or bare-timestamp scan — only what a reader actually
    sees does."""
    stripped = _SCRIPT_RE.sub(" ", html)
    stripped = _DETAILS_RE.sub(" ", stripped)
    stripped = _PRIMER_RE.sub(" ", stripped)
    return _TAG_RE.sub(" ", stripped)


def find_violations(html: str) -> list[str]:
    """Return every copy-law violation found in `html`'s reading path. An
    empty list means the page is clean."""
    text = reading_path_text(html)
    violations: list[str] = []

    banned = BANNED_SUBSTRINGS + FALSIFIER_SUBSTRINGS + _closed_vocabulary_tokens()
    for phrase in banned:
        if phrase in text:
            violations.append(
                f"banned phrase {phrase!r} found in the reading path (outside "
                "mc-details/mc-primer) — move it into <details class=\"mc-details\"> "
                "or replace it with the plain-word copy from spec §5"
            )

    for match in _BARE_DATE_RE.finditer(text):
        violations.append(
            f"bare timestamp {match.group(0)!r} in visible text with no preceding "
            "plain word (G2b) — prefix it (\"Data to\" / \"数据截至\") in the visible "
            "text; the machine value belongs only in datetime="
        )

    for match in _ISO_TIME_RE.finditer(text):
        violations.append(
            f"raw ISO time fragment {match.group(0)!r} in visible text (G2b) — "
            "no ISO datetime separator belongs in what a reader sees"
        )

    return violations


def check_file(path: Path) -> list[str]:
    if not path.exists():
        return [f"{path} does not exist — build the page first"]
    html = path.read_text(encoding="utf-8")
    return find_violations(html)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "target", nargs="?", default=str(DEFAULT_TARGET),
        help="built HTML page to scan (default: site/macro_monetary.html)",
    )
    args = parser.parse_args(argv)

    violations = check_file(Path(args.target))
    if violations:
        for violation in violations:
            # House law: a GitHub annotation must START the line, so this is
            # a bare print, never a logger call (CLAUDE.md "GitHub
            # annotations must START the line").
            print(f"::error title=macro-command-copy-law::{violation}", flush=True)
        print(
            f"macro command copy guard: {len(violations)} violation(s) in {args.target}",
            file=sys.stderr,
        )
        return 1

    print(f"macro command copy guard: clean ({args.target})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
