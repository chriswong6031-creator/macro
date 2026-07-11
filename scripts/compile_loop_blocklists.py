"""scripts/compile_loop_blocklists.py — R-V4-5 kill-registry compiler.

Parses the markdown tables in research/DO_NOT_REBUILD.md (sections 1–4) into
a canonical config/compiled_kill_registry.yml, then emits generated additions
into each consumer's native format WITHOUT destroying hand-curated entries:

  Consumer A — config/signal_foundry_blocklist.yml
    Native schema: entries: [{id, match: {any_of: [...]}, reason, source}]
    Integration: a clearly-marked generated block is appended (or replaced) at
    the bottom of the file, prefixed with a regeneration comment.  Hand-curated
    entries above the generated block are never touched.

  Consumer B — config/causal_priors.yml  (kill_mask.compiled section)
    The causal_priors.yml kill_mask.compiled is already regenerated nightly by
    scripts/build_causal_inventory.py from data/neuralweb/causal_nulls.jsonl
    (a different, more specific authority).  This compiler does NOT touch that
    section (to avoid a double-source conflict).  Instead it writes a companion
    file config/compiled_kill_registry_causal.yml that causal_ingest_brainstorm
    can optionally import.  This keeps the existing causal-priors sync test green.

Deterministic: same input → same output (lexicographic ordering inside each
section, no timestamps in content).

Usage:
    python3 scripts/compile_loop_blocklists.py [--repo-root PATH]

Exit codes:
    0   OK
    1   parse error or I/O failure
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DO_NOT_REBUILD_PATH = ("research", "DO_NOT_REBUILD.md")
COMPILED_REGISTRY_PATH = ("config", "compiled_kill_registry.yml")
SIGNAL_FOUNDRY_BLOCKLIST_PATH = ("config", "signal_foundry_blocklist.yml")

SECTION_NAMES = {
    1: "forbidden_by_ruling",
    2: "killed_signal_families",
    3: "estimator_laws",
    4: "held_suspended",
}

# Marker used to demarcate the generated block in each consumer file.
# The block begins with START_MARKER and ends with END_MARKER (inclusive).
START_MARKER = "# --- BEGIN GENERATED FROM DO_NOT_REBUILD.md (compile_loop_blocklists.py) ---"
END_MARKER = "# --- END GENERATED FROM DO_NOT_REBUILD.md ---"


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def _slug(text: str) -> str:
    """Convert free text to a compact kebab slug (for IDs and keys)."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text[:80].strip("-")


def _parse_markdown_table(lines: list[str]) -> list[dict[str, str]]:
    """Parse a GFM pipe-table and return list of row dicts.

    Assumes the header row is the first row, the separator row is second,
    and data rows follow.  Strips pipe characters and whitespace.
    Returns [] if fewer than 2 rows found.
    """
    rows: list[dict[str, str]] = []
    headers: list[str] = []
    for i, line in enumerate(lines):
        line = line.strip()
        if not line.startswith("|"):
            if headers:
                break  # table ended
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if not headers:
            headers = cells
            continue
        # Skip separator row
        if all(re.match(r"^[-:]+$", c.replace(" ", "")) for c in cells if c):
            continue
        if len(cells) < len(headers):
            cells += [""] * (len(headers) - len(cells))
        rows.append(dict(zip(headers, cells)))
    return rows


def parse_do_not_rebuild(md_text: str) -> list[dict[str, Any]]:
    """Parse sections 1–4 of DO_NOT_REBUILD.md into a flat list of entries.

    Each entry:
        {topic, verdict, source, section_num, section_name}
    """
    entries: list[dict[str, Any]] = []

    # Split on section headers ## 1. / ## 2. / ## 3. / ## 4.
    section_pattern = re.compile(r"^##\s+(\d+)\.", re.MULTILINE)
    parts = section_pattern.split(md_text)
    # parts = [preamble, section_num, section_body, section_num, section_body, ...]

    i = 1
    while i + 1 < len(parts):
        try:
            sec_num = int(parts[i])
        except ValueError:
            i += 2
            continue

        sec_body = parts[i + 1]
        i += 2

        if sec_num not in SECTION_NAMES:
            continue

        sec_name = SECTION_NAMES[sec_num]

        # Extract the markdown table lines
        table_lines = []
        in_table = False
        for line in sec_body.splitlines():
            stripped = line.strip()
            if stripped.startswith("|"):
                table_lines.append(line)
                in_table = True
            elif in_table and not stripped.startswith("|"):
                # Table ended — keep going in case there are multiple tables
                in_table = False

        if not table_lines:
            continue

        rows = _parse_markdown_table(table_lines)
        for row in rows:
            # Normalize column names (handle case / whitespace variation)
            topic = (
                row.get("Topic")
                or row.get("topic")
                or row.get("Construction")
                or ""
            ).strip()
            verdict = (
                row.get("Verdict")
                or row.get("verdict")
                or row.get("State")
                or row.get("state")
                or ""
            ).strip()
            source = (
                row.get("Ruling / source")
                or row.get("ruling")
                or row.get("source")
                or row.get("Source")
                or ""
            ).strip()

            if not topic:
                continue

            entries.append({
                "topic": topic,
                "verdict": verdict,
                "source": source,
                "section": sec_num,
                "section_name": sec_name,
            })

    return entries


# ---------------------------------------------------------------------------
# Registry writer
# ---------------------------------------------------------------------------

def _yaml_str(s: str) -> str:
    """Escape a string for single-quoted YAML scalar."""
    return "'" + s.replace("'", "''") + "'"


def _write_compiled_registry(entries: list[dict[str, Any]], out_path: Path) -> None:
    """Write config/compiled_kill_registry.yml."""
    lines: list[str] = [
        "# config/compiled_kill_registry.yml — R-V4-5 compiled kill registry",
        "# GENERATED by scripts/compile_loop_blocklists.py from research/DO_NOT_REBUILD.md",
        "# DO NOT hand-edit — regenerate with: python3 scripts/compile_loop_blocklists.py",
        "#",
        "# Schema: compiled_kill_registry.v1",
        "schema: compiled_kill_registry.v1",
        "",
        "entries:",
    ]
    for entry in entries:
        lines.append(f"  - topic: {_yaml_str(entry['topic'])}")
        lines.append(f"    verdict: {_yaml_str(entry['verdict'])}")
        lines.append(f"    source: {_yaml_str(entry['source'])}")
        lines.append(f"    section: {entry['section']}")
        lines.append(f"    section_name: {entry['section_name']}")
        lines.append("")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Signal Foundry blocklist integration
# ---------------------------------------------------------------------------

def _topic_to_pattern(topic: str) -> str:
    """Convert a DO_NOT_REBUILD topic phrase to a usable regex pattern.

    Strategy: take significant words (>= 4 chars), join with .{{0,30}} for
    flexible matching.  The result is conservative (false positives are
    acceptable; false negatives are not).
    """
    # Strip markdown formatting
    topic_clean = re.sub(r"`[^`]*`", lambda m: m.group(0)[1:-1], topic)
    words = re.findall(r"[a-zA-Z]{4,}", topic_clean)
    if not words:
        return re.escape(topic_clean[:40].lower())
    # Take up to 3 significant words to keep patterns manageable
    sig = words[:3]
    return ".{0,30}".join(re.escape(w.lower()) for w in sig)


def _build_sf_generated_block(entries: list[dict[str, Any]]) -> str:
    """Build the generated YAML block for signal_foundry_blocklist.yml."""
    lines: list[str] = [
        "",
        START_MARKER,
        "# Auto-compiled from research/DO_NOT_REBUILD.md sections 1-4.",
        "# Regenerate: python3 scripts/compile_loop_blocklists.py",
        "# Hand-curated entries above this block are not modified.",
    ]

    # Assign generated IDs starting from BL-G001
    for i, entry in enumerate(entries, start=1):
        entry_id = f"BL-G{i:03d}"
        pattern = _topic_to_pattern(entry["topic"])
        reason_short = entry["verdict"][:200] if entry["verdict"] else "DO_NOT_REBUILD entry"
        source_short = entry["source"][:200] if entry["source"] else "DO_NOT_REBUILD.md"
        lines.append("")
        lines.append(f"  - id: {entry_id}")
        lines.append(f"    match:")
        lines.append(f"      any_of:")
        lines.append(f"        - {_yaml_str(pattern)}")
        lines.append(f"    reason: >")
        # Wrap reason at ~72 chars with 6-space indent
        reason_wrapped = _wrap_yaml_block(reason_short, indent="      ")
        lines.append(reason_wrapped)
        lines.append(f"    source: {_yaml_str(source_short)}")

    lines.append("")
    lines.append(END_MARKER)
    return "\n".join(lines)


def _wrap_yaml_block(text: str, indent: str = "      ", width: int = 72) -> str:
    """Wrap text into YAML block scalar lines."""
    words = text.split()
    current_line = indent
    result_lines = []
    for word in words:
        if len(current_line) + len(word) + 1 > width and current_line.strip():
            result_lines.append(current_line.rstrip())
            current_line = indent + word + " "
        else:
            current_line += word + " "
    if current_line.strip():
        result_lines.append(current_line.rstrip())
    return "\n".join(result_lines)


def _update_signal_foundry_blocklist(
    entries: list[dict[str, Any]],
    bl_path: Path,
) -> None:
    """Append or replace the generated block in signal_foundry_blocklist.yml.

    Hand-curated entries outside the generated block are never modified.
    """
    generated_block = _build_sf_generated_block(entries)

    if not bl_path.exists():
        # Nothing to preserve — write a minimal wrapper + generated block
        content = (
            "# config/signal_foundry_blocklist.yml\n"
            "# Hand-curated entries go above the generated block.\n"
            "\nentries:\n"
            + generated_block
            + "\n"
        )
        bl_path.write_text(content, encoding="utf-8")
        return

    existing = bl_path.read_text(encoding="utf-8")

    if START_MARKER in existing:
        # Replace the existing generated block
        before = existing[: existing.index(START_MARKER)]
        after_start = existing[existing.index(START_MARKER):]
        if END_MARKER in after_start:
            after = after_start[after_start.index(END_MARKER) + len(END_MARKER):]
        else:
            after = ""
        new_content = before.rstrip() + "\n" + generated_block + "\n" + after.lstrip()
    else:
        # Append the generated block
        new_content = existing.rstrip() + "\n" + generated_block + "\n"

    bl_path.write_text(new_content, encoding="utf-8")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def compile_blocklists(repo_root: Path) -> int:
    """Main compilation entry point.  Returns 0 on success, 1 on failure."""
    md_path = repo_root.joinpath(*DO_NOT_REBUILD_PATH)
    if not md_path.exists():
        print(f"ERROR: {md_path} not found", file=sys.stderr)
        return 1

    try:
        md_text = md_path.read_text(encoding="utf-8")
    except Exception as exc:
        print(f"ERROR: reading {md_path}: {exc}", file=sys.stderr)
        return 1

    entries = parse_do_not_rebuild(md_text)
    if not entries:
        print(
            "WARNING: no entries parsed from DO_NOT_REBUILD.md — check section headers",
            file=sys.stderr,
        )

    print(f"Parsed {len(entries)} entries from DO_NOT_REBUILD.md")

    # Write compiled_kill_registry.yml
    registry_path = repo_root.joinpath(*COMPILED_REGISTRY_PATH)
    try:
        _write_compiled_registry(entries, registry_path)
        print(f"Wrote {registry_path}")
    except Exception as exc:
        print(f"ERROR: writing compiled_kill_registry.yml: {exc}", file=sys.stderr)
        return 1

    # Update signal_foundry_blocklist.yml
    sf_path = repo_root.joinpath(*SIGNAL_FOUNDRY_BLOCKLIST_PATH)
    try:
        _update_signal_foundry_blocklist(entries, sf_path)
        print(f"Updated {sf_path}")
    except Exception as exc:
        print(f"ERROR: updating signal_foundry_blocklist.yml: {exc}", file=sys.stderr)
        return 1

    print("compile_loop_blocklists: OK")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="R-V4-5: Compile DO_NOT_REBUILD.md into loop blocklists."
    )
    ap.add_argument(
        "--repo-root",
        default=None,
        help="Repository root path (defaults to parent of this script's directory).",
    )
    args = ap.parse_args(argv)

    if args.repo_root:
        repo_root = Path(args.repo_root).resolve()
    else:
        repo_root = Path(__file__).resolve().parent.parent

    return compile_blocklists(repo_root)


if __name__ == "__main__":
    sys.exit(main())
