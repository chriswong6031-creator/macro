"""Safe, comment-preserving edits to the repo's config.yml.

config.yml is 3000+ lines of hand-authored YAML with dense inline comments, and
lib/config.py loads it read-only via yaml.safe_load (which discards comments). So we
NEVER round-trip the parsed object back to YAML — that would obliterate every comment.
Instead we:
  (1) READ current values with a fresh yaml.safe_load (never cached), and
  (2) CHANGE a single flag via a surgical, anchored line edit that rewrites ONLY the
      value token on the located line, leaving indentation + the trailing comment
      byte-identical.

The leaf line is located by walking the YAML structure via indentation (a stack of
(indent, key)), NOT by a hard-coded line number — robust to the ~30 reused `enabled:`
keys and to the file shifting over time. Writes are atomic (temp file + os.replace).
"""
from __future__ import annotations

import os
import re
import tempfile
import threading

import yaml

from .paths import CONFIG

# serialize read-modify-write so concurrent toggles (ThreadingHTTPServer) can't
# clobber each other's edit (lost update)
_WRITE_LOCK = threading.Lock()

# a bare "key:" line (key has no spaces); captures indent + key + the rest after the colon
_KEY_RE = re.compile(r"^(?P<indent>[ \t]*)(?P<key>[A-Za-z0-9_]+):(?P<after>.*)$")
_BOOL_RE = re.compile(
    r"^(?P<indent>[ \t]*)(?P<key>[A-Za-z0-9_]+):(?P<gap>[ \t]*)"
    r"(?P<val>true|false|True|False)(?P<rest>[ \t]*(#.*)?)$")
_INT_RE = re.compile(
    r"^(?P<indent>[ \t]*)(?P<key>[A-Za-z0-9_]+):(?P<gap>[ \t]*)"
    r"(?P<val>\d+)(?P<rest>[ \t]*(#.*)?)$")


def read_config() -> dict:
    """Fresh parse (never cached) so the admin always reflects on-disk state."""
    with open(CONFIG) as f:
        return yaml.safe_load(f) or {}


def get_value(dotted: str, cfg: dict | None = None):
    """Read a value by dotted path (e.g. 'master_brain.enabled'); None if absent."""
    node = cfg if cfg is not None else read_config()
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def _read_lines() -> list[str]:
    text = CONFIG.read_text()
    if "\r" in text:
        raise RuntimeError("config.yml has CRLF/CR line endings; refusing surgical edit")
    return text.split("\n")


def _write_lines(lines: list[str]) -> None:
    """Atomic write preserving the exact byte layout (LF endings, trailing newline)."""
    new = "\n".join(lines)
    fd, tmp = tempfile.mkstemp(dir=str(CONFIG.parent), prefix=".config.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(new)
        os.replace(tmp, CONFIG)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


def locate_line(dotted: str, lines: list[str] | None = None) -> int | None:
    """0-based index of the line defining the LEAF key of `dotted`, found by walking
    the YAML tree via indentation. None if not found."""
    lines = lines if lines is not None else _read_lines()
    target = dotted.split(".")
    stack: list[tuple[int, str]] = []   # (indent, key)
    for i, raw in enumerate(lines):
        stripped = raw.lstrip()
        if not stripped or stripped.startswith("#"):
            continue
        m = _KEY_RE.match(raw)
        if not m:
            continue            # list items / block content — don't disturb the stack
        indent = len(m.group("indent"))
        key = m.group("key")
        while stack and stack[-1][0] >= indent:
            stack.pop()
        stack.append((indent, key))
        if [k for _, k in stack] == target:
            return i
    return None


def set_bool(dotted: str, value: bool) -> dict:
    """Flip a boolean flag in place. Returns {ok, path, old, new, line} or {ok:False,error}."""
    with _WRITE_LOCK:
        # fail closed: only edit a path that actually resolves to a YAML boolean
        # scalar (guards against locate_line matching a `key:` inside a list/block).
        cur = get_value(dotted)
        if not isinstance(cur, bool):
            return {"ok": False, "path": dotted,
                    "error": f"{dotted} is not a boolean scalar in config.yml"}
        lines = _read_lines()
        idx = locate_line(dotted, lines)
        if idx is None:
            return {"ok": False, "path": dotted, "error": f"path not found: {dotted}"}
        leaf = dotted.split(".")[-1]
        m = _BOOL_RE.match(lines[idx])
        if not m or m.group("key") != leaf:
            return {"ok": False, "path": dotted,
                    "error": f"line {idx + 1} is not a boolean flag for {dotted}: {lines[idx]!r}"}
        new_token = "true" if value else "false"
        lines[idx] = f"{m.group('indent')}{m.group('key')}:{m.group('gap')}{new_token}{m.group('rest')}"
        _write_lines(lines)
        return {"ok": True, "path": dotted, "old": m.group("val"), "new": new_token, "line": idx + 1}


def set_int(dotted: str, value: int, lo: int = 1, hi: int = 7) -> dict:
    """Set an integer field (clamped to [lo, hi]) in place. Used for interval_days."""
    try:
        value = max(lo, min(hi, int(value)))
    except (TypeError, ValueError):
        return {"ok": False, "path": dotted, "error": f"not an integer: {value!r}"}
    with _WRITE_LOCK:
        cur = get_value(dotted)
        if not isinstance(cur, int) or isinstance(cur, bool):
            return {"ok": False, "path": dotted,
                    "error": f"{dotted} is not an integer scalar in config.yml"}
        lines = _read_lines()
        idx = locate_line(dotted, lines)
        if idx is None:
            return {"ok": False, "path": dotted, "error": f"path not found: {dotted}"}
        leaf = dotted.split(".")[-1]
        m = _INT_RE.match(lines[idx])
        if not m or m.group("key") != leaf:
            return {"ok": False, "path": dotted,
                    "error": f"line {idx + 1} is not an integer field for {dotted}: {lines[idx]!r}"}
        lines[idx] = f"{m.group('indent')}{m.group('key')}:{m.group('gap')}{value}{m.group('rest')}"
        _write_lines(lines)
        return {"ok": True, "path": dotted, "old": m.group("val"), "new": str(value), "line": idx + 1}
