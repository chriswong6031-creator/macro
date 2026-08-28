"""scripts/check_design_system.py — design-system ratchet (R0: report-only).

Static lint over the Jinja/HTML/CSS template estate.  It answers one question:
where does a surface hand-roll something the design system already owns — a raw
colour, a font stack, a radius, a token, a card, a banner word, an emoji?

R0 SHIPS REPORT-ONLY ON PURPOSE.  `--mode report` (the default) always exits 0,
however many findings it prints, because the estate has thousands of pre-existing
literals and a gate that reds on day one is a gate somebody disables in week one.
The BLOCKING arm exists and is tested from the first commit anyway: `--mode
enforce` exits non-zero on rules 1-4, and the R1 flip is then a one-line wiring
change plus a registry severity bump — not a new script written under pressure.

Enforcement scope in `--mode enforce` is deliberately narrow: a template is
GOVERNED only when the page registry says a row that renders it is
`design_system.compliant`, or when the template is NEW (unknown to the registry).
Everything else reports.  That is the ratchet: compliant surfaces cannot regress,
new surfaces are born compliant, and the backlog is migrated on a schedule rather
than in one heroic red-build weekend.

A THIRD mode, `enforce-added`, blocks forward-only: it takes a unified diff via
`--diff-file` (a real file path, or `-` for stdin) and exits non-zero only when
a finding in `ADDED_BLOCKING_RULES` lands on a line the diff actually ADDED.
Pre-existing debt on an unchanged line never blocks, however many rules it
trips — that is what lets a NEW violation fail closed without reddening the
whole estate the day this ships. `report` and full `enforce` are unchanged.

Usage::

    python3 scripts/check_design_system.py                  # report (exit 0)
    python3 scripts/check_design_system.py --mode enforce   # blocking arm
    python3 scripts/check_design_system.py --mode enforce-added \
        --diff-file /tmp/design.diff                        # forward-only arm
    python3 scripts/check_design_system.py --self-check     # prove the rules bite

CLOSURE LEGIBILITY (load-bearing, do not regress): this module names exactly ONE
scan root, ``templates``, and makes NO subprocess call.  scripts/run_ci_pack.py
infers a CI job's path ownership from the scan-root string constants of the
modules it loads and widens an opaque edge (a traversal, a subprocess) to every
root the module names.  A single stray literal naming another root would hand the
wired job that entire tree and push the narrow-diff selector over its ceiling
(measured incident #5396).  Keep every path literal here under ``templates``.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from pathlib import Path
from typing import Iterable, NamedTuple, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]

# The one scan root this module may name.  See CLOSURE LEGIBILITY above.
TEMPLATES_DIR = "templates"

# The token source of truth.  Colour literals, font stacks and radius values are
# legal here and nowhere else — this file IS the palette.
THEME_CSS = "templates/theme.css"

# Sanctioned asset files: hand-authored or vendored surfaces that legitimately
# carry literals because they predate (or deliberately sit outside) the token
# layer.  Every entry is a DEBT, not an endorsement; the migration factory
# retires them one at a time.
SANCTIONED_LITERAL_FILES: frozenset[str] = frozenset({
    "templates/theme.css",
    "templates/landing.css",
    "templates/navigation-refresh.css",
})

MODES = ("report", "enforce", "enforce-added")

# Rules 1-4 are mechanical and exact — they are what `--mode enforce` blocks on.
# Rules 5-6 are HEURISTICS by design (a regex cannot know whether `.foo-card` is
# a new component or a rename), and rule 7 is a measurement, so all three are
# warn-tier for as long as this script exists.
BLOCKING_RULES = ("color-literal", "font-family-literal", "radius-literal",
                  "literal-custom-property")

# `--mode enforce-added` blocks on rules 1-4 PLUS the two rules whose whole
# reason for existing is a NEW decision (an emoji nobody had before, a second
# token root nobody had before) — rules that would be absurd to whole-estate
# enforce given the legacy debt, but are exactly what forward-only enforcement
# exists to catch on a line nobody had touched until this PR.  `BLOCKING_RULES`
# stays a plain tuple (other code reads it as one); `frozenset(...)` of it here
# is just this constant's own type, not a mutation of the original (C3).
# R3: "emoji" membership here still means the RULE, not every glyph rule 8
# reports — `added_blocking_findings` narrows an `emoji` finding further, to
# `EMOJI_BLOCKING_RE` only, before it is allowed to actually block.
ADDED_BLOCKING_RULES = frozenset(BLOCKING_RULES) | {"emoji", "parallel-token-root"}

# Rule 6 seed.  DELIBERATELY SMALL: this is the vocabulary the Tier-1 glance
# doctrine bans outright (internal state names, untranslated statistics,
# falsifier language), not the full doctrine lint.  EXTENSIBLE — the complete
# banned-vocabulary pass is a later wave with its own per-surface allowlist, and
# a word added here without that machinery will produce false positives on
# methodology and calibration pages, which legitimately explain these terms.
BANNED_VOCABULARY_SEED: tuple[str, ...] = (
    "falsifier",
    "refuted",
    "证伪",
    "z-score",
    "percentile rank",
)

# --- rule patterns ----------------------------------------------------------

HEX_RE = re.compile(r"#(?:[0-9a-fA-F]{3,4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})\b")
FUNC_COLOR_RE = re.compile(r"\b(?:rgba?|hsla?)\s*\(")
FONT_FAMILY_RE = re.compile(r"font-family\s*:\s*([^;}\n]+)")
RADIUS_RE = re.compile(r"border-radius\s*:\s*([^;}\n]+)")
CUSTOM_PROP_RE = re.compile(r"(--[A-Za-z0-9_-]+)\s*:\s*([^;}\n]+)")
CARD_CLASS_RE = re.compile(r"\.([A-Za-z0-9_-]*-card)\b\s*(?=[,{:.\[])")
STYLE_BLOCK_RE = re.compile(r"<style\b[^>]*>(.*?)</style>", re.DOTALL | re.IGNORECASE)

# A `:root` selector block, captured whole so its body can be checked for ANY
# custom-property declaration regardless of whether the value is a literal or a
# derivation — see rule 9 (parallel-token-root) below.  Naive about nested
# braces, same as STYLE_BLOCK_RE; CSS custom-property blocks do not nest them.
ROOT_BLOCK_RE = re.compile(r"(?<![\w-]):root\b\s*\{([^}]*)\}", re.DOTALL)

# A custom property whose value is ONLY composition over other tokens is a
# DERIVATION, not a literal — that is exactly how a surface is supposed to extend
# the palette, so it passes.  Decided by subtraction rather than by matching a
# whole-value shape: strip the composition (token references, calc/min/max/clamp,
# inert keywords) and ask whether any literal SURVIVES.  A whole-value regex got
# this wrong in both directions — `var(--b,#fff)` passed because the fallback fit
# inside `[^)]*`, while `var(--b,rgba(1,2,3))` failed only because its nested
# parens happened to break the same group.  A literal in a fallback is a literal.
COMPOSITION_RE = re.compile(
    r"var\(\s*--[A-Za-z0-9_-]+\s*"
    r"|\b(?:calc|min|max|clamp)\s*\("
    r"|\b(?:inherit|initial|unset|revert|none|transparent|currentColor|auto)\b",
    re.IGNORECASE)
# What counts as a surviving literal: a colour, a word (keyword, font name,
# colour function), a QUANTITY WITH A UNIT, or a quoted string.  A bare unitless
# number is left alone so `calc(var(--sp-2) * 2)` stays a derivation.
VALUE_LITERAL_RE = re.compile(
    r"#[0-9a-fA-F]{3,8}"
    r"|[A-Za-z]{2,}"
    r"|\d+\s*(?:px|rem|em|%|vh|vw|vmin|vmax|ch|ex|pt|deg|ms|s|fr)\b"
    r"|[\"']")


def is_derived_value(value: str) -> bool:
    """True when a custom-property value composes tokens and adds no literal."""
    return not VALUE_LITERAL_RE.search(COMPOSITION_RE.sub(" ", value))

# Emoji: the pictographic planes plus the standalone dingbats that render as
# colour glyphs.  Ranges, not a list, so a new vendor emoji cannot slip through.
# This is the RULE 8 REPORTING regex (`--mode report` census) — left exactly as
# it is (R3): it deliberately over-matches typography (✓ ★ ⚠) and country
# flags, because a census wants to SEE the whole estate, warn-tier.
EMOJI_RE = re.compile(
    "[" "\U0001F300-\U0001FAFF" "\U00002600-\U000027BF" "\U0001F000-\U0001F2FF"
    "\U0000FE0F" "\U0001F900-\U0001F9FF" "]")

# R3: the NARROW pattern used ONLY to decide whether an `emoji` finding is
# allowed to BLOCK in `--mode enforce-added`. `EMOJI_RE` above is wrong for
# that job — measured across templates/**: 1,597 hits in 145 files, the vast
# majority ordinary typography (⚠×188, ✓×147, ★×82, ⚠×72, ✕×59, ✗×47, all in
# the Misc Symbols + Dingbats block `\U00002600-\U000027BF`) or country-flag
# regional indicators (`\U0001F1E6-\U0001F1FF`, 290 codepoints / ~145 flags in
# templates/stock-logos.js, intl.html.j2, chat.html, _navlinks.html.j2 — market
# identifiers in data structures, not emoji-as-UI decoration; adding a market
# is ordinary roadmapped work this gate must never block). Only the
# pictographic planes are emoji-as-icon, which the design doctrine bans and
# the architecture authorizes blocking on a newly ADDED line — `\U0001F900-
# \U0001F9FF` is already a subset of `\U0001F300-\U0001FAFF` but is spelled out
# to match the frozen ruling literally.
EMOJI_BLOCKING_RE = re.compile("[" "\U0001F300-\U0001FAFF" "\U0001F900-\U0001F9FF" "]")

# Extracts the codepoint check_design_system.py's own `emoji` Finding.detail
# carries (`f"emoji U+{ord(...):04X}"` below) so `added_blocking_findings` can
# test it against `EMOJI_BLOCKING_RE` without a second scan of the source line.
_EMOJI_DETAIL_CODEPOINT_RE = re.compile(r"U\+([0-9A-Fa-f]{4,6})")


def _emoji_finding_is_narrowly_blocking(finding: "Finding") -> bool:
    """True only when an `emoji` Finding's own glyph is in `EMOJI_BLOCKING_RE`.

    Typography (✓ ⚠ ★) and country flags fire rule 8 (`EMOJI_RE`, unchanged,
    still reported) but must never block `--mode enforce-added` — see
    `EMOJI_BLOCKING_RE` above.
    """
    match = _EMOJI_DETAIL_CODEPOINT_RE.search(finding.detail)
    if not match:
        return False
    return bool(EMOJI_BLOCKING_RE.match(chr(int(match.group(1), 16))))

# A radius is compliant only when it reads a radius token.
RADIUS_TOKEN_RE = re.compile(r"var\(\s*--r-[A-Za-z0-9_-]+")
# Radius keywords that carry no design decision.
RADIUS_INERT = frozenset({"0", "0px", "inherit", "initial", "unset", "revert"})

TEXT_SUFFIXES = (".j2", ".html", ".css", ".js")


class Finding(NamedTuple):
    rule: str
    path: str
    line: int
    detail: str


# --- scanning ---------------------------------------------------------------

def iter_template_files(root: Path) -> list[Path]:
    """Every lintable file under the templates root, sorted for determinism."""
    base = root / TEMPLATES_DIR
    if not base.is_dir():
        return []
    out = [p for p in base.rglob("*")
           if p.is_file() and p.suffix in TEXT_SUFFIXES]
    return sorted(out)


def _rel(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _blank(match: re.Match[str]) -> str:
    """Replace a match with spaces, preserving newlines so line numbers hold."""
    return re.sub(r"[^\n]", " ", match.group(0))


JINJA_RE = re.compile(r"\{[{%#].*?[}%#]\}", re.DOTALL)

# Fragment references are NOT colours.  `href="#abc"` and `url(#fade)` both end
# in three-or-six characters that happen to be hex digits, and rule 1 blocks in
# enforce mode — a false positive there would block a correct new template.
FRAGMENT_REF_RE = re.compile(
    r"""(?:xlink:)?href\s*=\s*"#[^"]*"|(?:xlink:)?href\s*=\s*'#[^']*'"""
    r"""|url\(\s*#[^)]*\)""", re.IGNORECASE)


def _strip_jinja(text: str) -> str:
    """Blank Jinja expressions and fragment refs, keeping line numbers intact.

    A `{{ '#fff' if dark else '#000' }}` is a template decision, not a stylesheet
    literal, and flagging it teaches people to ignore the rule.
    """
    return FRAGMENT_REF_RE.sub(_blank, JINJA_RE.sub(_blank, text))


def scan_text(rel_path: str, text: str) -> list[Finding]:
    """Apply all eight rules to one file's text."""
    findings: list[Finding] = []
    sanctioned = rel_path in SANCTIONED_LITERAL_FILES
    is_theme = rel_path == THEME_CSS
    cleaned = _strip_jinja(text)
    lines = cleaned.splitlines()

    for n, line in enumerate(lines, 1):
        # 1 — colour literals
        if not sanctioned:
            for match in HEX_RE.finditer(line):
                findings.append(Finding("color-literal", rel_path, n,
                                        f"hex colour {match.group(0)}"))
            for match in FUNC_COLOR_RE.finditer(line):
                findings.append(Finding("color-literal", rel_path, n,
                                        f"colour function {match.group(0).strip()}"))
        # 2 — font-family literals
        if not sanctioned:
            for match in FONT_FAMILY_RE.finditer(line):
                value = match.group(1).strip()
                if "var(" not in value:
                    findings.append(Finding("font-family-literal", rel_path, n,
                                            f"font-family: {value[:60]}"))
        # 3 — radius values that are not var(--r-*)
        for match in RADIUS_RE.finditer(line):
            value = match.group(1).strip()
            if RADIUS_TOKEN_RE.search(value) or value.lower() in RADIUS_INERT:
                continue
            findings.append(Finding("radius-literal", rel_path, n,
                                    f"border-radius: {value[:60]}"))
        # 4 — literal-valued custom properties declared outside theme.css.
        #     ANY selector counts: :root, body.page-*, a class scope alike — a
        #     shadow palette hurts just as much when it hides in a page class.
        if not is_theme:
            for match in CUSTOM_PROP_RE.finditer(line):
                name, value = match.group(1), match.group(2).strip()
                if is_derived_value(value):
                    continue
                findings.append(Finding("literal-custom-property", rel_path, n,
                                        f"{name}: {value[:60]}"))
        # 5 — new *-card class definitions (heuristic)
        for match in CARD_CLASS_RE.finditer(line):
            findings.append(Finding("card-class", rel_path, n,
                                    f"card class .{match.group(1)}"))
        # 6 — banned Tier-1 vocabulary (heuristic, seed list)
        lowered = line.lower()
        for word in BANNED_VOCABULARY_SEED:
            if word in lowered:
                findings.append(Finding("banned-vocabulary", rel_path, n,
                                        f"banned term {word!r}"))
        # 8 — emoji codepoints in markup
        for match in EMOJI_RE.finditer(line):
            findings.append(Finding("emoji", rel_path, n,
                                    f"emoji U+{ord(match.group(0)[0]):04X}"))

    # 7 — inline <style> byte size (R0 measures; no growth gate yet)
    inline = sum(len(m.group(1).encode("utf-8"))
                 for m in STYLE_BLOCK_RE.finditer(cleaned))
    if inline:
        line_no = next((i for i, m in enumerate(cleaned.splitlines(), 1)
                        if "<style" in m.lower()), 1)
        findings.append(Finding("inline-style-bytes", rel_path, line_no,
                                f"{inline} bytes of inline <style>"))

    # 9 — parallel token root: a `:root` block outside theme.css that declares a
    # custom property is a SECOND palette definition, even when every value is a
    # pure token derivation — the violation is the second root, not the literal.
    # theme.css is the sole legitimate root (not even SANCTIONED_LITERAL_FILES is
    # exempt: that list exempts literals, never a parallel root). A scoped
    # (non-`:root`) derived custom property stays legal — that is how a surface
    # is supposed to extend the palette.
    if not is_theme:
        for match in ROOT_BLOCK_RE.finditer(cleaned):
            if CUSTOM_PROP_RE.search(match.group(1)):
                line_no = cleaned.count("\n", 0, match.start()) + 1
                findings.append(Finding("parallel-token-root", rel_path, line_no,
                                        ":root block declares a custom property "
                                        "outside theme.css"))
    return findings


def scan(root: Path, paths: Optional[Iterable[Path]] = None) -> list[Finding]:
    files = list(paths) if paths is not None else iter_template_files(root)
    findings: list[Finding] = []
    for path in files:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        findings.extend(scan_text(_rel(path, root), text))
    return findings


# --- governance -------------------------------------------------------------

def governed_templates(registry: Optional[dict]) -> set[str]:
    """Templates under enforcement: those a `design_system.compliant` row names.

    `governed_regions` narrows a claim to part of a template; R0 enforcement is
    whole-file, so a region entry still puts its template in the set.  Region
    ACCURACY becomes load-bearing at R1, when a partially-migrated template must
    be able to hold a compliant region beside a legacy one.
    """
    if not isinstance(registry, dict):
        return set()
    out: set[str] = set()
    for row in registry.get("pages") or []:
        if not isinstance(row, dict):
            continue
        design = row.get("design_system")
        if not isinstance(design, dict) or design.get("compliant") is not True:
            continue
        regions = design.get("governed_regions")
        if isinstance(regions, list) and regions:
            for region in regions:
                if isinstance(region, dict) and isinstance(region.get("template"), str):
                    out.add(region["template"])
            continue
        template = row.get("source_template")
        if isinstance(template, str) and template.startswith(TEMPLATES_DIR):
            out.add(template)
    return out


def known_templates(registry: Optional[dict]) -> set[str]:
    """Every template the registry has ever seen, compliant or not."""
    if not isinstance(registry, dict):
        return set()
    out: set[str] = set()
    for row in registry.get("pages") or []:
        if not isinstance(row, dict):
            continue
        template = row.get("source_template")
        if isinstance(template, str) and template.startswith(TEMPLATES_DIR):
            out.add(template)
        design = row.get("design_system")
        if isinstance(design, dict):
            for region in design.get("governed_regions") or []:
                if isinstance(region, dict) and isinstance(region.get("template"), str):
                    out.add(region["template"])
    return out


def blocking_findings(findings: Iterable[Finding], governed: set[str],
                      known: set[str]) -> list[Finding]:
    """Rules 1-4 on a governed-compliant template, or on a template nobody knows."""
    out = []
    for finding in findings:
        if finding.rule not in BLOCKING_RULES:
            continue
        if finding.path in governed or finding.path not in known:
            out.append(finding)
    return out


# --- diff parsing (forward-only enforcement) ---------------------------------
#
# Pure text parsing, no subprocess call (CLOSURE LEGIBILITY) — the diff always
# arrives as text via --diff-file, produced by the CALLER's own `git diff`.

HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")

# C-style backslash escapes git uses inside a quoted diff path (RFC-ish, see
# `quote.c`'s `sq_quote_buf`/`quote_c_style`). Octal (`\NNN`) escapes are
# handled separately below since they encode raw BYTES of a UTF-8 sequence,
# not one escape per character.
_GIT_QUOTE_ESCAPES: dict[str, int] = {
    "n": 0x0A, "t": 0x09, "a": 0x07, "b": 0x08, "f": 0x0C, "r": 0x0D, "v": 0x0B,
    "\\": 0x5C, '"': 0x22,
}


def _unquote_git_diff_path(quoted: str) -> str:
    """Decode a C-style-quoted git diff path: surrounding double quotes, the
    escapes in ``_GIT_QUOTE_ESCAPES``, and octal byte escapes (``\\NNN``) for
    non-ASCII bytes (e.g. ``\\303\\251`` for ``é``). Octal escapes are raw
    BYTES of a multi-byte UTF-8 sequence, so they accumulate into one byte
    buffer and are decoded as UTF-8 once at the end, never escape-by-escape.
    """
    if len(quoted) < 2 or quoted[0] != '"' or quoted[-1] != '"':
        return quoted
    body = quoted[1:-1]
    out = bytearray()
    i, n = 0, len(body)
    while i < n:
        ch = body[i]
        if ch == "\\" and i + 1 < n:
            nxt = body[i + 1]
            if nxt in "01234567":
                j = i + 1
                digits = ""
                while j < n and body[j] in "01234567" and len(digits) < 3:
                    digits += body[j]
                    j += 1
                out.append(int(digits, 8) & 0xFF)
                i = j
                continue
            mapped = _GIT_QUOTE_ESCAPES.get(nxt)
            if mapped is not None:
                out.append(mapped)
                i += 2
                continue
            # Unknown escape: keep the backslash and the character literally.
            out.extend(ch.encode("utf-8"))
            i += 1
            continue
        out.extend(ch.encode("utf-8"))
        i += 1
    return out.decode("utf-8", errors="replace")


def _normalize_diff_header_path(candidate: str) -> str:
    """Normalize the text after a ``+++ ``/``--- `` diff header marker (R1).

    Git appends a literal TAB after the path when the path contains a space
    (``+++ b/templates/panel v2.css<TAB>``) — strip everything from the first
    TAB onward FIRST, because a quoted-AND-spaced path carries both the quotes
    and the trailing tab. Then, if what remains is wrapped in double quotes
    (git quotes any path with a space, control char, or non-ASCII byte —
    ``"templates/pa\\303\\251nel.css"``), unquote it. Finally strip a leading
    ``a/``/``b/`` prefix. ``/dev/null`` (pure addition/deletion) passes through
    unchanged — callers treat that literal as "no path".
    """
    tab = candidate.find("\t")
    if tab != -1:
        candidate = candidate[:tab]
    if len(candidate) >= 2 and candidate[0] == '"' and candidate[-1] == '"':
        candidate = _unquote_git_diff_path(candidate)
    if candidate[:2] in ("a/", "b/"):
        candidate = candidate[2:]
    return candidate


def parse_added_line_numbers(diff_text: str) -> dict[str, set[int]]:
    """Which NEW-file line numbers a unified diff ADDED, keyed by new-side path.

    Deliberately naive about anything but the `+`/`-`/context markers and the
    `diff --git` / `--- ` / `+++ ` headers — no git plumbing.  Two shapes need
    explicit handling or the line numbers silently desync (C2, binding):

    - ``\\ No newline at end of file`` is not a real diff line.  Counting it
      shifts every subsequent line number in the hunk by one.
    - An added line whose CONTENT happens to start with ``++``/``--`` must not
      be mistaken for a ``+++ file``/``--- file`` header.  A real header only
      ever appears between a file's ``diff --git`` line and its first ``@@``
      hunk; once a hunk has started, an ``in_hunk`` flag keeps a
      header-shaped content line from being misread as a header.

    A third shape (R1, binding): git escapes the ``+++ b/<path>`` header when
    the path is unusual — a literal TAB appended for a path containing a
    space, or the whole path double-quoted with C-style/octal escapes for a
    path containing a non-ASCII or control byte.  ``_normalize_diff_header_path``
    strips the tab, unquotes, and strips the ``a/``/``b/`` prefix, in that
    order, before the path is used as a dict key.
    """
    out: dict[str, set[int]] = {}
    path: Optional[str] = None
    new_line = 0
    in_hunk = False
    for raw in diff_text.splitlines():
        if raw.startswith("\\"):
            # "\ No newline at end of file" — not a real line; do not count it.
            continue
        if raw.startswith("diff --git "):
            in_hunk = False
            continue
        if not in_hunk and raw.startswith("--- "):
            continue
        if not in_hunk and raw.startswith("+++ "):
            candidate = _normalize_diff_header_path(raw[4:])
            if candidate == "/dev/null":
                # Pure deletion — behaves exactly as before: no path is
                # tracked, and a deletion hunk carries no "+" lines anyway.
                path = None
            else:
                path = candidate
                out.setdefault(path, set())
            continue
        match = HUNK_RE.match(raw)
        if match:
            in_hunk = True
            new_line = int(match.group(1))
            continue
        if path is None or not in_hunk:
            continue
        if raw.startswith("+"):
            out[path].add(new_line)
            new_line += 1
        elif raw.startswith("-"):
            continue
        else:
            new_line += 1
    return out


def added_blocking_findings(findings: Iterable[Finding],
                            added_lines: dict[str, set[int]]) -> list[Finding]:
    """Findings whose rule is forward-blocking AND whose line was just added.

    R3: an `emoji` finding on an added line blocks only when its OWN glyph is
    in the narrow `EMOJI_BLOCKING_RE` set — typography (✓ ⚠ ★) and country
    flags reported by rule 8's wide `EMOJI_RE` must never block a build.
    """
    out: list[Finding] = []
    for finding in findings:
        if finding.rule not in ADDED_BLOCKING_RULES:
            continue
        if finding.line not in added_lines.get(finding.path, set()):
            continue
        if finding.rule == "emoji" and not _emoji_finding_is_narrowly_blocking(finding):
            continue
        out.append(finding)
    return out


# --- reporting --------------------------------------------------------------

ANNOTATION_CAP = 10


def annotate(level: str, message: str) -> None:
    """Emit ONE GitHub annotation.

    Bare `print`, never a logger: every builder here logs through a prefixing
    formatter, and GitHub silently drops an annotation that does not START the
    line.  `flush` is load-bearing — stdout is block-buffered when piped in CI.
    """
    print(f"::{level} title=design-system::{message}", flush=True)


def report_added(findings: list[Finding], blocking: list[Finding]) -> None:
    """Forward-only reporting for `--mode enforce-added`.

    Deliberately NOT `report()`.  `report()` always dumps the whole estate
    census, which is exactly right for `report`/`enforce` (both mean "show me
    everything") but would be a defect here: on the real estate the census runs
    ~19,000 findings, so an unscoped dump makes forward-only enforcement LOOK
    like it reddened the whole estate on every PR (the outcome TP-0 exists to
    avoid), floods CI logs by roughly a megabyte, and buries the one line a
    developer actually needs to act on.  The summary annotation therefore leads
    with the BLOCKING count — the number the developer must act on — and the
    estate total is surfaced only as explicitly-labelled non-blocking context,
    never as this mode's error count.  `--mode report` remains the way to see
    the full census; this function never substitutes for it.
    """
    non_blocking_estate = len(findings) - len(blocking)
    census_note = (f"{non_blocking_estate} further pre-existing, non-blocking "
                   f"finding(s) in the estate — run --mode report for the full "
                   f"census")
    if not blocking:
        annotate("notice", f"R0 enforce-added: 0 blocking finding(s) "
                           f"({census_note})")
        print(f"design-system ratchet — mode=enforce-added blocking=0 "
              f"(estate pre-existing, non-blocking: {non_blocking_estate})",
              flush=True)
        return

    annotate("error", f"R0 enforce-added: {len(blocking)} blocking finding(s) "
                      f"on line(s) added by this diff ({census_note})")
    emitted = 1
    for finding in blocking[:ANNOTATION_CAP - emitted]:
        annotate("error",
                 f"{finding.path}:{finding.line} [{finding.rule}] {finding.detail}")
        emitted += 1
    if len(blocking) > ANNOTATION_CAP - 1:
        print(f"... {len(blocking) - (ANNOTATION_CAP - 1)} further blocking "
              f"finding(s) not annotated (cap {ANNOTATION_CAP}); full detail "
              f"follows", flush=True)

    print(f"design-system ratchet — mode=enforce-added blocking={len(blocking)} "
          f"(estate pre-existing, non-blocking: {non_blocking_estate})",
          flush=True)
    for finding in blocking:
        print(f"{finding.path}:{finding.line}: {finding.rule}: {finding.detail}",
              flush=True)


def report(findings: list[Finding], *, mode: str, blocking: list[Finding]) -> None:
    """Summary-first annotations (capped), then full plain-text detail."""
    counts: dict[str, int] = {}
    for finding in findings:
        counts[finding.rule] = counts.get(finding.rule, 0) + 1

    emitted = 0
    level = "error" if (mode == "enforce" and blocking) else "notice"
    summary = ", ".join(f"{rule}={counts[rule]}" for rule in sorted(counts)) or "none"
    annotate(level, f"R0 {mode}: {len(findings)} finding(s) — {summary}")
    emitted += 1

    # Exemplars: the blocking ones first when they exist, since those are the
    # findings a reader can actually be asked to fix today.
    exemplars = blocking or findings
    for finding in exemplars[:ANNOTATION_CAP - emitted]:
        annotate(level,
                 f"{finding.path}:{finding.line} [{finding.rule}] {finding.detail}")
        emitted += 1
    if len(exemplars) > ANNOTATION_CAP - 1:
        # The cap is why the plain-text block below exists; say so in-band.
        print(f"... {len(exemplars) - (ANNOTATION_CAP - 1)} further finding(s) "
              f"not annotated (cap {ANNOTATION_CAP}); full detail follows",
              flush=True)

    print(f"design-system ratchet — mode={mode} findings={len(findings)} "
          f"blocking={len(blocking)}", flush=True)
    for rule in sorted(counts):
        print(f"  {rule}: {counts[rule]}", flush=True)
    for finding in findings:
        print(f"{finding.path}:{finding.line}: {finding.rule}: {finding.detail}",
              flush=True)


# --- self-check -------------------------------------------------------------

# One fixture per rule: the violation, and the clean counterpart that must pass.
# Written to a tempdir rather than asserted against the live estate — a
# self-check derived from what it checks cannot fail (house trap).
DIRTY_FIXTURES: dict[str, tuple[str, str]] = {
    "color-literal": ("a.css", ".x{color:#ff0044}"),
    "font-family-literal": ("b.css", ".x{font-family:Helvetica,sans-serif}"),
    "radius-literal": ("c.css", ".x{border-radius:7px}"),
    "literal-custom-property": ("d.css", "body.page-x{--brand:#123456}"),
    "card-class": ("e.css", ".insight-card{padding:0}"),
    "banned-vocabulary": ("f.html.j2", "<p>the falsifier fired</p>"),
    "inline-style-bytes": ("g.html.j2", "<style>.x{padding:0}</style>"),
    "emoji": ("h.html.j2", "<p>\U0001F600 hello</p>"),
}

CLEAN_FIXTURE = (
    "clean.css",
    # A SCOPED derived custom property, not `:root` — a non-theme `:root` block
    # is itself the parallel-token-root violation (rule 9), so a fixture meant
    # to prove "this is all legal" must not use one.
    ".x{color:var(--ink-1);font-family:var(--font-body);"
    "border-radius:var(--r-2)}\nbody.page-x{--ink-soft:var(--ink-1)}\n",
)


def self_check() -> int:
    """Prove each rule detects its own violation, and that clean text passes."""
    problems: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for rule, (name, body) in sorted(DIRTY_FIXTURES.items()):
            hits = {f.rule for f in scan_text(f"{TEMPLATES_DIR}/{name}", body)}
            if rule not in hits:
                problems.append(f"rule {rule!r} did NOT fire on its own fixture "
                                f"(fired: {sorted(hits)})")
        name, body = CLEAN_FIXTURE
        clean = scan_text(f"{TEMPLATES_DIR}/{name}", body)
        if clean:
            problems.append(
                "clean fixture produced findings: "
                + ", ".join(f"{f.rule}@{f.line}" for f in clean))
        # The traversal itself must work, or every rule above is vacuous in the
        # real run: plant one violation on disk and require the walk to find it.
        planted = root / TEMPLATES_DIR / "planted.css"
        planted.parent.mkdir(parents=True, exist_ok=True)
        planted.write_text(".x{color:#abcdef}", encoding="utf-8")
        walked = scan(root)
        if not any(f.rule == "color-literal" for f in walked):
            problems.append("scan() walked the templates root and found nothing")

    for problem in problems:
        annotate("error", f"self-check: {problem}")
    if problems:
        print(f"self-check FAILED: {len(problems)} problem(s)", flush=True)
        return 1
    print(f"self-check OK: {len(DIRTY_FIXTURES)} rule fixtures + clean fixture "
          f"+ traversal", flush=True)
    return 0


# --- CLI --------------------------------------------------------------------

def load_registry(path: Path) -> Optional[dict]:
    """Read the page registry if present; absence is not fatal.

    Imported lazily and defensively: the ratchet must still report on a checkout
    where the registry has not been built.
    """
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _read_diff(path: Optional[str]) -> str:
    """Read unified diff text for `--mode enforce-added`.

    `path` is a caller-supplied file path (or `-` for stdin) — not a scan-root
    constant, so it does not touch CLOSURE LEGIBILITY.  No git plumbing: the
    caller's own `git diff` produced this text; this module only parses it.
    Absence (`None`) is not fatal — it means no line was ever "added", so
    `main()` fails open with a loud warning rather than crashing.

    A caller-SUPPLIED path that cannot be read is a DIFFERENT case (R6): that
    is a checkout/infrastructure fault (a typo'd path, a file the runner never
    produced), not "nothing was added" — silently returning "" would make
    `main()` read it as a clean diff and exit 0 with no annotation at all.
    This re-raises `OSError` rather than swallowing it; `main()` catches it
    and fails CLOSED with a loud `::error` and a non-zero exit instead.
    """
    if path is None:
        return ""
    if path == "-":
        return sys.stdin.read()
    return Path(path).read_text(encoding="utf-8", errors="replace")


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--mode", choices=MODES, default="report",
                    help="report (default; always exit 0), enforce (blocks on "
                         "rules 1-4 in governed-compliant or new templates), or "
                         "enforce-added (blocks only on ADDED_BLOCKING_RULES "
                         "findings whose line --diff-file actually added)")
    ap.add_argument("--root", type=Path, default=REPO_ROOT,
                    help="repository root to scan (tests point this at a fixture)")
    ap.add_argument("--registry", type=Path, default=None,
                    help="page registry JSON; governs which templates enforce")
    ap.add_argument("--diff-file", type=str, default=None,
                    help="unified diff text for --mode enforce-added (e.g. "
                         "`git diff --unified=0 -- templates`); '-' reads stdin")
    # `--selftest` is the house spelling every other guard uses, and the one
    # scripts/check_house_law_registry.py looks for when it verifies that a
    # `selftest: true` registry entry is not a stale claim. Both spellings run
    # the same code; neither is deprecated.
    ap.add_argument("--self-check", "--selftest", dest="self_check",
                    action="store_true",
                    help="prove each rule detects its own violation, then exit")
    args = ap.parse_args(argv)

    if args.self_check:
        return self_check()

    findings = scan(args.root)
    registry = load_registry(args.registry) if args.registry else None
    governed = governed_templates(registry)
    known = known_templates(registry)
    blocking = blocking_findings(findings, governed, known)

    if args.mode == "enforce" and registry is None:
        # Fail CLOSED, but say so: with no census loaded every template is
        # "unknown", so the new-template arm covers the whole estate. That is the
        # right default for a guard, and the wrong thing to wire by accident.
        annotate("warning",
                 "enforce ran with no readable --registry: every template counts "
                 "as NEW, so the whole estate is blocking. Pass --registry to "
                 "scope enforcement to design_system.compliant rows.")

    if args.mode == "enforce-added":
        # Fail OPEN, but say so: with no diff, no line was ever "added" by
        # definition, so nothing can block — the opposite default from
        # `enforce`, because this mode's entire contract is "only new lines
        # count" and there is no such thing as an unscoped forward-only gate.
        if args.diff_file is None:
            annotate("warning",
                     "enforce-added ran with no --diff-file: no line counts as "
                     "added, so nothing can block. Pass --diff-file (or '-' for "
                     "stdin) with the PR's own unified diff.")
        try:
            diff_text = _read_diff(args.diff_file)
        except OSError as exc:
            # R6: fail CLOSED — an unreadable --diff-file is a checkout fault,
            # never silent evidence that nothing was added.
            annotate("error",
                     f"enforce-added could not read --diff-file {args.diff_file!r}: "
                     f"{exc}. Failing closed rather than treating an unreadable "
                     f"diff as an empty one.")
            return 1
        added_lines = parse_added_line_numbers(diff_text)
        added_blocking = added_blocking_findings(findings, added_lines)
        report_added(findings, added_blocking)
        return 1 if added_blocking else 0

    report(findings, mode=args.mode, blocking=blocking)

    if args.mode == "enforce" and blocking:
        return 1
    # report mode ALWAYS exits 0 — see the module docstring.
    return 0


if __name__ == "__main__":
    sys.exit(main())
