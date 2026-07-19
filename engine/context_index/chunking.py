"""
CXI-1 chunkers — pure functions, no I/O.

Every chunker returns list[ChunkDraft].
Target: 300-900 tokens (~1200-3600 chars).  token_count = len(text)//4.

Chunkers:
  whole_file        — entire file as one chunk (CLAUDE.md)
  markdown_sections — ATX heading splits; supports Unicode/Chinese headings
  python_symbols    — AST-based; falls back to whole-file-split on parse error
  yaml_keys         — top-level + second-level keys; line-based fallback
  registry_rows     — research/DO_NOT_REBUILD.md only: one chunk per table row
                      within sections 1-4; status derived from verdict cell.
"""

from __future__ import annotations

import ast
import re
import unicodedata
from typing import List

import yaml  # stdlib-only shim: falls back if unavailable

from .schema import ChunkDraft

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_CHUNK_TARGET_MAX = 3600   # chars ≈ 900 tokens
_CHUNK_TARGET_MIN = 1200   # chars ≈ 300 tokens

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _slug(text: str) -> str:
    """Produce a URL-safe heading slug; handles ASCII and Unicode."""
    out = []
    for ch in text.lower():
        cat = unicodedata.category(ch)
        if ch in " -_":
            out.append("-")
        elif ch.isalnum() or cat.startswith("L") or cat.startswith("N"):
            out.append(ch)
        # else: drop punctuation/symbols
    slug = "".join(out).strip("-")
    # collapse repeated dashes
    slug = re.sub(r"-{2,}", "-", slug)
    return slug or "section"


def _split_by_paragraphs(text: str, max_chars: int) -> List[str]:
    """Split text at paragraph boundaries to stay under max_chars."""
    paragraphs = re.split(r"\n{2,}", text)
    chunks: List[str] = []
    buf = ""
    for para in paragraphs:
        candidate = (buf + "\n\n" + para).lstrip() if buf else para
        if len(candidate) <= max_chars:
            buf = candidate
        else:
            if buf:
                chunks.append(buf)
            # para itself oversized? take it as-is
            buf = para
    if buf:
        chunks.append(buf)
    return chunks or [text]


# ---------------------------------------------------------------------------
# whole_file
# ---------------------------------------------------------------------------


def whole_file(path: str, content: str) -> List[ChunkDraft]:
    return [ChunkDraft(locator=f"{path}#whole", text=content)]


# ---------------------------------------------------------------------------
# markdown_sections
# ---------------------------------------------------------------------------

_ATX_RE = re.compile(r"^(#{1,6})\s+(.+)", re.MULTILINE)


def markdown_sections(path: str, content: str) -> List[ChunkDraft]:
    """Split on ATX headings; carry full parent heading path."""
    drafts: List[ChunkDraft] = []

    lines = content.splitlines(keepends=True)
    # Find heading positions
    headings: list[tuple[int, int, str]] = []  # (char_offset, level, title)
    pos = 0
    for line in lines:
        m = re.match(r"^(#{1,6})\s+(.+)", line.rstrip())
        if m:
            headings.append((pos, len(m.group(1)), m.group(2).strip()))
        pos += len(line)

    if not headings:
        # No headings — treat as one chunk
        if content.strip():
            return [ChunkDraft(locator=f"{path}#chunk-0", text=content)]
        return []

    # Build sections: text between consecutive headings
    sections: list[tuple[list[str], str]] = []  # (heading_path, text)
    heading_stack: list[tuple[int, str]] = []   # (level, title)

    for idx, (char_off, level, title) in enumerate(headings):
        next_off = headings[idx + 1][0] if idx + 1 < len(headings) else len(content)
        section_text = content[char_off:next_off]

        # Maintain heading stack
        while heading_stack and heading_stack[-1][0] >= level:
            heading_stack.pop()
        heading_stack.append((level, title))

        hpath = [t for _, t in heading_stack]
        sections.append((list(hpath), section_text))

    # Convert sections to ChunkDrafts; split oversized
    slug_counter: dict[str, int] = {}
    for hpath, text in sections:
        base_slug = _slug(hpath[-1]) if hpath else "section"
        n = slug_counter.get(base_slug, 0)
        slug_counter[base_slug] = n + 1
        heading_slug = f"{base_slug}-{n}" if n > 0 else base_slug
        locator_base = f"{path}#{heading_slug}"

        if len(text) <= _CHUNK_TARGET_MAX:
            drafts.append(ChunkDraft(
                locator=locator_base,
                heading_path=hpath,
                text=text,
            ))
        else:
            # Split by paragraphs
            parts = _split_by_paragraphs(text, _CHUNK_TARGET_MAX)
            for i, part in enumerate(parts):
                drafts.append(ChunkDraft(
                    locator=f"{locator_base}#chunk-{i}",
                    heading_path=hpath,
                    text=part,
                ))

    return [d for d in drafts if d.text.strip()]


# ---------------------------------------------------------------------------
# python_symbols
# ---------------------------------------------------------------------------


def python_symbols(path: str, content: str) -> List[ChunkDraft]:
    """AST-based Python chunker.  Falls back to whole-file-split on error."""
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return _python_fallback(path, content)

    lines = content.splitlines(keepends=True)
    drafts: List[ChunkDraft] = []

    # Module header: leading docstring + import lines
    header_lines: list[str] = []
    body_start = 0
    if (tree.body and isinstance(tree.body[0], ast.Expr)
            and isinstance(tree.body[0].value, ast.Constant)):
        doc_node = tree.body[0]
        end = doc_node.end_lineno or 1
        header_lines = lines[:end]
        body_start = end
    # Add import lines that follow
    import_lines: list[str] = []
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            lo = node.lineno - 1
            hi = (node.end_lineno or node.lineno)
            import_lines.extend(lines[lo:hi])
    header_text = "".join(header_lines) + ("\n" + "".join(import_lines) if import_lines else "")
    if header_text.strip():
        drafts.append(ChunkDraft(
            locator=f"{path}#module-header",
            symbol="<module>",
            text=header_text.strip(),
        ))

    # Track used locators to avoid collisions (e.g. same name at module-level and inside a class)
    locator_counts: dict[str, int] = {}

    def _unique_locator(base: str) -> str:
        n = locator_counts.get(base, 0)
        locator_counts[base] = n + 1
        return base if n == 0 else f"{base}-{n}"

    def _node_lo(node: ast.AST) -> int:
        """Return the 0-based start line for a class/function node, including decorators."""
        if getattr(node, "decorator_list", None):
            return min(d.lineno for d in node.decorator_list) - 1
        return node.lineno - 1  # type: ignore[attr-defined]

    # Top-level classes and functions (pinned design: one chunk per top-level node only)
    for node in tree.body:
        if not isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        lo = _node_lo(node)
        hi = node.end_lineno or node.lineno
        node_lines = lines[lo:hi]
        node_text = "".join(node_lines)
        qualname = node.name

        if len(node_text) > _CHUNK_TARGET_MAX:
            node_text = node_text[:_CHUNK_TARGET_MAX] + "\n# … truncated"

        loc = _unique_locator(f"{path}#symbol-{qualname}")
        drafts.append(ChunkDraft(
            locator=loc,
            symbol=qualname,
            text=node_text,
        ))

    return [d for d in drafts if d.text.strip()] or _python_fallback(path, content)


def _python_fallback(path: str, content: str) -> List[ChunkDraft]:
    """Split by _CHUNK_TARGET_MAX chars for unparseable files."""
    if not content.strip():
        return []
    parts = [content[i:i + _CHUNK_TARGET_MAX] for i in range(0, len(content), _CHUNK_TARGET_MAX)]
    return [ChunkDraft(locator=f"{path}#chunk-{n}", text=p) for n, p in enumerate(parts)]


# ---------------------------------------------------------------------------
# yaml_keys
# ---------------------------------------------------------------------------


def yaml_keys(path: str, content: str) -> List[ChunkDraft]:
    """Top-level and second-level YAML keys; graceful line-based fallback."""
    try:
        data = yaml.safe_load(content)
    except Exception:
        return _yaml_fallback(path, content)

    if not isinstance(data, dict):
        return _yaml_fallback(path, content)

    drafts: List[ChunkDraft] = []
    for top_key, top_val in data.items():
        key_path = [str(top_key)]
        # Serialize top-level value for chunk text
        try:
            top_text = yaml.dump({top_key: top_val}, allow_unicode=True, default_flow_style=False)
        except Exception:
            top_text = f"{top_key}: <unparseable>"

        if len(top_text) <= _CHUNK_TARGET_MAX:
            drafts.append(ChunkDraft(
                locator=f"{path}#yaml.{top_key}",
                heading_path=key_path,
                symbol=str(top_key),
                text=top_text,
            ))
        else:
            # Drill into second-level
            if isinstance(top_val, dict):
                for sub_key, sub_val in top_val.items():
                    sub_path = [str(top_key), str(sub_key)]
                    try:
                        sub_text = yaml.dump({sub_key: sub_val}, allow_unicode=True, default_flow_style=False)
                    except Exception:
                        sub_text = f"{sub_key}: <unparseable>"
                    if len(sub_text) > _CHUNK_TARGET_MAX:
                        sub_text = sub_text[:_CHUNK_TARGET_MAX] + "\n# … truncated"
                    drafts.append(ChunkDraft(
                        locator=f"{path}#yaml.{top_key}.{sub_key}",
                        heading_path=sub_path,
                        symbol=f"{top_key}.{sub_key}",
                        text=sub_text,
                    ))
            else:
                # Scalar / list oversized — split
                parts = _split_by_paragraphs(top_text, _CHUNK_TARGET_MAX)
                for i, p in enumerate(parts):
                    drafts.append(ChunkDraft(
                        locator=f"{path}#yaml.{top_key}#chunk-{i}",
                        heading_path=key_path,
                        symbol=str(top_key),
                        text=p,
                    ))

    return [d for d in drafts if d.text.strip()]


def _yaml_fallback(path: str, content: str) -> List[ChunkDraft]:
    """Line-based fallback when YAML parse fails."""
    parts = [content[i:i + _CHUNK_TARGET_MAX] for i in range(0, len(content), _CHUNK_TARGET_MAX)]
    return [ChunkDraft(locator=f"{path}#chunk-{n}", text=p) for n, p in enumerate(parts) if p.strip()]


# ---------------------------------------------------------------------------
# registry_rows  (research/DO_NOT_REBUILD.md ONLY)
# ---------------------------------------------------------------------------

# Verdict keywords → status
_FORBIDDEN_KW = re.compile(
    r"\b(FORBIDDEN|ILLEGAL|DON[''']T.TEST|DO NOT BUILD)\b", re.I
)
_KILLED_KW = re.compile(
    r"\b(KILLED|STRUCK|FALSIFIED|REFUTED|REJECT|DEAD|RETIRED|NO.GO|ALL.NULL)\b", re.I
)
_DEFERRED_KW = re.compile(r"\b(HOLD|DEFER|PARKED|SUSPENDED)\b", re.I)


def _derive_status(verdict_cell: str) -> str:
    if _FORBIDDEN_KW.search(verdict_cell):
        return "forbidden"
    if _KILLED_KW.search(verdict_cell):
        return "killed"
    if _DEFERRED_KW.search(verdict_cell):
        return "deferred"
    return "unknown"


def _parse_header_verdict_col(header_line: str) -> int:
    """
    Given a markdown table header row, return the 0-based index of the column
    whose title contains 'verdict' or 'state' (case-insensitive).
    Falls back to 1 (second column) for 2-column tables or when no match found.
    """
    cells = [c.strip() for c in header_line.strip().split("|") if c.strip() != ""]
    for idx, cell in enumerate(cells):
        if re.search(r"\b(verdict|state)\b", cell, re.I):
            return idx
    # Default: second column (index 1) — covers 2-col tables where cells[-1]==verdict
    return min(1, len(cells) - 1) if cells else 1


def registry_rows(path: str, content: str) -> List[ChunkDraft]:
    """
    Parse research/DO_NOT_REBUILD.md:
    - Table rows within ATX sections 1-4 → one chunk each, status derived from
      the Verdict column (found by header parse, not positional cells[-1]).
    - Section number gates the status: §1→forbidden, §2→killed, §4→deferred.
      §3 rows default to 'unknown' regardless of keyword to avoid false forbidden.
    - Header rows (immediately before a separator row) are skipped.
    - Non-table prose → markdown_sections chunking.
    """
    drafts: List[ChunkDraft] = []

    lines = content.splitlines(keepends=True)
    in_section_14 = False
    current_section_num: int = 0
    current_section_heading: list[str] = []
    non_table_parts: list[str] = []
    current_nonblock: list[str] = []

    # Per-table state
    verdict_col_idx: int = 1   # which column holds the verdict
    header_row_stripped: str | None = None  # detect and skip header rows

    i = 0
    while i < len(lines):
        line = lines[i]
        hm = re.match(r"^(#{1,3})\s+(.+)", line.rstrip())
        if hm:
            # Flush pending non-table content
            if current_nonblock:
                non_table_parts.extend(current_nonblock)
                current_nonblock = []
            # Reset per-table state at each new section
            verdict_col_idx = 1
            header_row_stripped = None
            num_match = re.match(r"(\d+)", hm.group(2))
            if num_match:
                current_section_num = int(num_match.group(1))
                in_section_14 = 1 <= current_section_num <= 4
                current_section_heading = [hm.group(2).strip()]
            else:
                current_section_num = 0
                in_section_14 = False
                current_section_heading = [hm.group(2).strip()]
            non_table_parts.append(line)
            i += 1
            continue

        # Table row detection: starts with |
        if in_section_14 and line.startswith("|"):
            stripped = line.strip()

            # Separator row (|---|---| style) — signals preceding row was a header
            if re.match(r"^\|[\s\-:|]+\|", stripped):
                # The previous | row (if any) was the header — parse verdict col
                if header_row_stripped is not None:
                    verdict_col_idx = _parse_header_verdict_col(header_row_stripped)
                    header_row_stripped = None
                i += 1
                continue

            cells = [c.strip() for c in stripped.split("|") if c.strip() != ""]
            if len(cells) >= 2:
                # If we haven't seen a separator yet, this might be a header row.
                # Peek: if next non-empty line is a separator, treat current as header.
                next_i = i + 1
                while next_i < len(lines) and not lines[next_i].strip():
                    next_i += 1
                if next_i < len(lines) and re.match(r"^\|[\s\-:|]+\|", lines[next_i].strip()):
                    # This is the header row — record it, skip (do not emit a chunk
                    # and do not add to prose reconstruction)
                    header_row_stripped = stripped
                    i += 1
                    continue

                # Data row — derive verdict from the correct column
                verdict_cell = cells[verdict_col_idx] if verdict_col_idx < len(cells) else cells[-1]

                # Section-gated status: §3 (methodology) → always unknown
                if current_section_num == 3:
                    status = "unknown"
                else:
                    status = _derive_status(verdict_cell)

                row_text = " | ".join(cells)
                full_heading = " ".join(current_section_heading)
                chunk_text = f"{full_heading}\n{row_text}"
                drafts.append(ChunkDraft(
                    locator=f"{path}#row-{len(drafts)}",
                    heading_path=list(current_section_heading),
                    symbol=status,
                    text=chunk_text,
                ))
                i += 1
                continue

        # Non-table content
        current_nonblock.append(line)
        i += 1

    if current_nonblock:
        non_table_parts.extend(current_nonblock)

    # Non-table prose → markdown_sections
    if non_table_parts:
        prose = "".join(non_table_parts)
        drafts.extend(markdown_sections(path, prose))

    return [d for d in drafts if d.text.strip()]


# ---------------------------------------------------------------------------
# code_blocks  (.ts/.tsx/.js/.mjs/.sql/.sh/.toml and similar)
# ---------------------------------------------------------------------------

# Patterns that start a new top-level block (deterministic heuristic boundary detection).
# SQL patterns are case-insensitive; JS/TS patterns are case-sensitive.
_CODE_BLOCK_RE = re.compile(
    r"^(?:"
    # JS/TS: export (default)? (async)? function|class|const|interface|type|enum
    r"export\s+(?:default\s+)?(?:async\s+)?(?:function|class|const|interface|type|enum)\b"
    r"|function\s+\w"
    r"|class\s+\w"
    # SQL (case-insensitive via inline flag is not possible in Python alternation;
    # handled below by compiling a second pattern)
    r")",
)

_SQL_BLOCK_RE = re.compile(
    r"^(?:CREATE\s+(?:TABLE|INDEX|POLICY|TRIGGER|FUNCTION)\b)",
    re.IGNORECASE,
)


def _is_block_boundary(line: str) -> bool:
    stripped = line.rstrip()
    return bool(_CODE_BLOCK_RE.match(stripped) or _SQL_BLOCK_RE.match(stripped))


def code_blocks(path: str, content: str) -> List[ChunkDraft]:
    """
    Deterministic top-level boundary detection for .ts/.tsx/.js/.mjs/.sql/.sh/.toml.

    Lines matching top-level export/function/class/CREATE TABLE (etc.) start a new block.
    Blocks are accumulated until they reach _CHUNK_TARGET_MAX chars, then flushed.
    locator = path#block-<n> where n is the ordinal (stable for unchanged prefixes).
    heading_path = [first line of block truncated to 80 chars].
    Fallback: no boundaries found → fixed-size line windows (same as _python_fallback).
    Never crashes on weird syntax.
    """
    lines = content.splitlines(keepends=True)
    if not lines:
        return []

    # Collect boundary line indices
    boundaries: list[int] = []
    for i, line in enumerate(lines):
        if _is_block_boundary(line):
            boundaries.append(i)

    # Fallback: no boundaries found → fixed-size char windows
    if not boundaries:
        parts = [content[i:i + _CHUNK_TARGET_MAX] for i in range(0, len(content), _CHUNK_TARGET_MAX)]
        return [ChunkDraft(locator=f"{path}#block-{n}", text=p)
                for n, p in enumerate(parts) if p.strip()]

    # Build segments between boundaries; accumulate into size-capped chunks
    segments: list[tuple[str, str]] = []  # (first_line, text)
    for idx, start in enumerate(boundaries):
        end = boundaries[idx + 1] if idx + 1 < len(boundaries) else len(lines)
        seg_text = "".join(lines[start:end])
        first_line = lines[start].rstrip()[:80]
        segments.append((first_line, seg_text))

    # Prepend any leading content before the first boundary
    if boundaries[0] > 0:
        preamble = "".join(lines[:boundaries[0]])
        if preamble.strip():
            segments.insert(0, (lines[0].rstrip()[:80], preamble))

    # Accumulate segments into target-size chunks; large segments get their own chunk
    drafts: List[ChunkDraft] = []
    block_n = 0
    buf_text = ""
    buf_heading = ""

    def _flush(text: str, heading: str) -> None:
        nonlocal block_n
        if text.strip():
            drafts.append(ChunkDraft(
                locator=f"{path}#block-{block_n}",
                heading_path=[heading] if heading else [],
                text=text,
            ))
            block_n += 1

    for first_line, seg_text in segments:
        if not buf_text:
            buf_text = seg_text
            buf_heading = first_line
        elif len(buf_text) + len(seg_text) <= _CHUNK_TARGET_MAX:
            buf_text += seg_text
        else:
            _flush(buf_text, buf_heading)
            buf_text = seg_text
            buf_heading = first_line

    _flush(buf_text, buf_heading)

    return [d for d in drafts if d.text.strip()]


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

CHUNKERS = {
    "whole_file": whole_file,
    "markdown_sections": markdown_sections,
    "python_symbols": python_symbols,
    "yaml_keys": yaml_keys,
    "registry_rows": registry_rows,
    "code_blocks": code_blocks,
}


def chunk(path: str, content: str, chunker_name: str) -> List[ChunkDraft]:
    fn = CHUNKERS.get(chunker_name)
    if fn is None:
        raise ValueError(f"Unknown chunker: {chunker_name!r}")
    return fn(path, content)
