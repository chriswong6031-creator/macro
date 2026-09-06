#!/usr/bin/env python3
"""FRONT-END CLARITY copy guard for Macro Command (Charter §7.x / spec §5).

Fails the build when customer-visible copy on a Macro Command page carries
machine text: raw closed-vocabulary tokens, internal method names, or bare
timestamps. Details/primer subtrees are exempt — professionals still get the
verbatim receipts there. The global header sits outside ``<main>`` and is out
of scope.

Run:
  python3 scripts/check_macro_command_copy.py [HTML…]
  python3 scripts/check_macro_command_copy.py --all-suite
  python3 scripts/check_macro_command_copy.py --selftest
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import lib.macro_suite_labels as _labels  # noqa: E402

# Spec §5 banned-substring CI list (verbatim phrases / tokens). Single lowercase
# words in BOUNDARY_WORDS match on word boundaries; everything else is a
# case-sensitive substring. Underscore tokens always match as substrings.
_SPEC_BANNED: tuple[str, ...] = (
    "accepted print",
    "accepted snapshot",
    "method version",
    "method-comparable",
    "hysteresis",
    "axis",
    "Axis",
    "authority ceiling",
    "content hash",
    "generation id",
    "producer",
    "artifact",
    "manifest",
    "trace_ref",
    "definition_id",
    "owner_ref",
    "standardized",
    "Diagnostics",
    "Vector",
    "vector",
    "snapshot",
    "deterministic",
    "schema",
    "Regime map",
    "Freshness",
    "Presence",
    "coverage_ratio",
    "null_reason",
)

# Single lowercase words: word-boundary only so "taxis" is not a hit.
_BOUNDARY_WORDS: frozenset[str] = frozenset(
    {
        "axis",
        "producer",
        "artifact",
        "manifest",
        "schema",
        "snapshot",
        "vector",
        "standardized",
        "deterministic",
        "hysteresis",
    }
)

# G2b: bare ISO date not immediately preceded by a plain word + space/NBSP;
# and any ``THH:MM`` clock fragment at all.
_BARE_DATE_RE = re.compile(r"(?<![A-Za-z一-鿿][ \u00a0])\d{4}-\d{2}-\d{2}")
_ISO_TIME_RE = re.compile(r"T\d{2}:\d{2}")

_SKIP_TAGS = frozenset({"script", "style", "template"})
_ATTRS = ("title", "aria-label", "alt", "placeholder")
_VOID = frozenset(
    "area base br col embed hr img input link meta param source track wbr".split()
)

_DEFAULT_PAGE = _REPO_ROOT / "site" / "macro_monetary.html"


@dataclass(frozen=True)
class Hit:
    """One banned match in extracted visible text."""

    matched: str
    context: str


def closed_vocab_tokens() -> frozenset[str]:
    """Uppercase / underscore closed-vocabulary keys from ``macro_suite_labels``.

    Enumerated from the module's public vocab and tone dicts so a contract
    extension cannot ship a new SCREAMING token without the guard seeing it.
    Two-letter region codes (``US``, ``EU``, …) are excluded — they are not the
    machine-state leak this gate exists to catch and would false-positive
    everywhere.
    """
    tokens: set[str] = set()
    for name, obj in vars(_labels).items():
        if name.startswith("_") or not isinstance(obj, dict):
            continue
        if not (name.isupper() or name.endswith("_TONE")):
            continue
        for key in obj:
            if not isinstance(key, str):
                continue
            if key.isupper() or "_" in key:
                if key.isupper() and "_" not in key and len(key) <= 2:
                    continue
                tokens.add(key)
    return frozenset(tokens)


def _boundary_pattern(word: str) -> re.Pattern[str]:
    return re.compile(rf"(?<![A-Za-z0-9_]){re.escape(word)}(?![A-Za-z0-9_])")


def _compile_rules() -> list[tuple[str, re.Pattern[str]]]:
    rules: list[tuple[str, re.Pattern[str]]] = []
    seen: set[str] = set()
    for token in _SPEC_BANNED:
        if token in seen:
            continue
        seen.add(token)
        if token in _BOUNDARY_WORDS:
            rules.append((token, _boundary_pattern(token)))
        else:
            rules.append((token, re.compile(re.escape(token))))
    for token in sorted(closed_vocab_tokens()):
        if token in seen:
            continue
        seen.add(token)
        # Underscore machine slugs + SCREAMING tokens: case-sensitive substring.
        rules.append((token, re.compile(re.escape(token))))
    return rules


_RULES = _compile_rules()


def _context_around(text: str, start: int, end: int, width: int = 40) -> str:
    left = max(0, start - width // 2)
    right = min(len(text), end + width // 2)
    snippet = text[left:right].replace("\n", " ").replace("\r", " ")
    if left > 0:
        snippet = "…" + snippet
    if right < len(text):
        snippet = snippet + "…"
    if len(snippet) > width:
        snippet = snippet[: width - 1] + "…"
    return snippet


def _scan_text(text: str) -> list[Hit]:
    hits: list[Hit] = []
    for matched, pattern in _RULES:
        for m in pattern.finditer(text):
            hits.append(Hit(matched=matched, context=_context_around(text, m.start(), m.end())))
    for m in _BARE_DATE_RE.finditer(text):
        hits.append(Hit(matched=m.group(0), context=_context_around(text, m.start(), m.end())))
    for m in _ISO_TIME_RE.finditer(text):
        hits.append(Hit(matched=m.group(0), context=_context_around(text, m.start(), m.end())))
    return hits


class VisibleTextExtractor(HTMLParser):
    """Collect visible text inside ``<main>`` and ``<title>``, with exemptions."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.chunks: list[str] = []
        self.text_nodes = 0
        self._skip_stack: list[str] = []
        self._exempt_stack: list[str] = []
        self._main_depth = 0
        self._title_depth = 0

    def _scanning(self) -> bool:
        return (
            not self._skip_stack
            and not self._exempt_stack
            and (self._main_depth > 0 or self._title_depth > 0)
        )

    @staticmethod
    def _classes(attrs: list[tuple[str, str | None]]) -> set[str]:
        for key, val in attrs:
            if key == "class" and val:
                return {c for c in val.split() if c}
        return set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _SKIP_TAGS:
            self._skip_stack.append(tag)
            return
        classes = self._classes(attrs)
        if "mc-details" in classes or "mc-primer" in classes:
            self._exempt_stack.append(tag)
        if tag == "main":
            self._main_depth += 1
        elif tag == "title":
            self._title_depth += 1
        if self._scanning():
            attr_map = {k: (v or "") for k, v in attrs}
            for name in _ATTRS:
                val = attr_map.get(name, "").strip()
                if val:
                    self.chunks.append(val)
                    self.text_nodes += 1
        if tag in _VOID and self._exempt_stack and self._exempt_stack[-1] == tag:
            self._exempt_stack.pop()

    def handle_endtag(self, tag: str) -> None:
        if self._skip_stack and self._skip_stack[-1] == tag:
            self._skip_stack.pop()
            return
        if tag == "main":
            self._main_depth = max(0, self._main_depth - 1)
        elif tag == "title":
            self._title_depth = max(0, self._title_depth - 1)
        if self._exempt_stack and self._exempt_stack[-1] == tag:
            self._exempt_stack.pop()

    def handle_data(self, data: str) -> None:
        if not self._scanning():
            return
        if not data or not data.strip():
            return
        self.chunks.append(data)
        self.text_nodes += 1

    def handle_comment(self, data: str) -> None:
        return


def extract_visible_text(html: str) -> tuple[str, int]:
    """Return joined visible text and the count of text/attr nodes scanned."""
    parser = VisibleTextExtractor()
    parser.feed(html)
    parser.close()
    return "\n".join(parser.chunks), parser.text_nodes


def scan_html(text: str) -> list[Hit]:
    """Pure scan: return every banned hit in the HTML's visible reading path."""
    visible, _ = extract_visible_text(text)
    return _scan_text(visible)


def suite_pages(root: Path | None = None) -> list[Path]:
    """The ``site/macro_*.html`` suite (hub + workspace pages) for ``--all-suite``."""
    base = (root or _REPO_ROOT) / "site"
    return sorted(base.glob("macro_*.html"))


def format_error(path: Path, hit: Hit, root: Path | None = None) -> str:
    rel = path
    try:
        rel = path.resolve().relative_to((root or _REPO_ROOT).resolve())
    except ValueError:
        rel = path
    return (
        f'::error title=macro-command-copy::{rel}: "{hit.matched}" '
        f'in visible text: "{hit.context}"'
    )


def check_files(paths: Iterable[Path]) -> tuple[int, int, list[str]]:
    """Scan ``paths``. Returns (files, text_nodes, error_lines)."""
    errors: list[str] = []
    files = 0
    nodes = 0
    for path in paths:
        files += 1
        html = path.read_text(encoding="utf-8")
        visible, n = extract_visible_text(html)
        nodes += n
        for hit in _scan_text(visible):
            errors.append(format_error(path, hit))
    return files, nodes, errors


_SELFTEST_BAD = """<!doctype html><html><head><title>ok</title></head>
<body>
<header>Freshness Presence</header>
<main>
  <p>accepted print and CURRENT and coverage_ratio</p>
  <p>2026-09-05</p>
  <p>stamp T12:00 here</p>
  <p>axis Vector snapshot producer</p>
  <p>taxis should pass</p>
  <details class="mc-details"><p>accepted print CURRENT 2026-09-05 T12:00 axis</p></details>
  <p class="mc-primer">Freshness Presence method version</p>
  <p>Data to 5 Sep 2026</p>
  <time datetime="2026-09-05">Data to 5 Sep 2026</time>
</main>
</body></html>
"""

_SELFTEST_GOOD = """<!doctype html><html><head><title>Macro Command</title></head>
<body>
<header>Freshness Presence CURRENT</header>
<main>
  <p>Data to 5 Sep 2026</p>
  <time datetime="2026-09-05">Data to 5 Sep 2026</time>
  <p>taxis corridor</p>
  <details class="mc-details"><p>accepted print CURRENT coverage_ratio 2026-09-05 T12:00</p></details>
  <p class="mc-primer">method version Freshness axis</p>
</main>
</body></html>
"""


def selftest() -> int:
    bad_hits = scan_html(_SELFTEST_BAD)
    needed = {
        "accepted print",
        "CURRENT",
        "coverage_ratio",
        "2026-09-05",
        "T12:00",
        "axis",
        "Vector",
        "snapshot",
        "producer",
    }
    found = {h.matched for h in bad_hits}
    missing = needed - found
    if missing:
        print(
            f"::error title=macro-command-copy-selftest::missing hits: {sorted(missing)}",
            flush=True,
        )
        return 1
    # Exempt / plain-as-of / taxis / header must not appear as the sole bad set
    good_hits = scan_html(_SELFTEST_GOOD)
    if good_hits:
        print(
            f"::error title=macro-command-copy-selftest::false positives: "
            f"{[h.matched for h in good_hits]}",
            flush=True,
        )
        return 1
    print("macro-command-copy: selftest OK", flush=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "paths",
        nargs="*",
        type=Path,
        help="Built HTML files to scan (default: site/macro_monetary.html)",
    )
    ap.add_argument(
        "--all-suite",
        action="store_true",
        help="Scan every site/macro_*.html page (P5 harness)",
    )
    ap.add_argument("--selftest", action="store_true", help="Run embedded fixtures")
    args = ap.parse_args(argv)

    if args.selftest:
        return selftest()

    if args.all_suite:
        paths = suite_pages()
        if not paths:
            print(
                "::error title=macro-command-copy::no site/macro_*.html pages found",
                flush=True,
            )
            return 1
    elif args.paths:
        paths = list(args.paths)
    else:
        paths = [_DEFAULT_PAGE]

    for path in paths:
        if not path.is_file():
            print(
                f"::error title=macro-command-copy::missing file: {path}",
                flush=True,
            )
            return 1

    files, nodes, errors = check_files(paths)
    for line in errors:
        print(line, flush=True)
    if errors:
        return 1
    print(
        f"macro-command-copy: OK ({files} files, {nodes} text nodes scanned)",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
