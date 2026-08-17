#!/usr/bin/env python3
"""Fail-closed secret / session-value scan. Never persist cookie values."""
from __future__ import annotations

import re
from pathlib import Path

TEXT_SUFFIXES = {".json", ".md", ".txt", ".html", ".js", ".csv", ".yml", ".yaml", ".log"}

# Structural mentions are allowed. Values are not.
ALLOWED_SNIPPETS = (
    "cookies_injected",
    "cookie_count",
    "authenticated_session_used",
    "session\": \"playwright-chrome",
    "session\": \"playwright",
)

PATTERNS = [
    ("SET_COOKIE_HEADER", re.compile(r"(?i)set-cookie\s*:")),
    ("COOKIE_HEADER", re.compile(r"(?i)(?:^|[\s\"'])cookie\s*:\s*[^=\s]+=\S+")),
    ("AUTHORIZATION_HEADER", re.compile(r"(?i)authorization\s*:")),
    ("BEARER_TOKEN", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]{16,}")),
    ("API_KEY_ASSIGNMENT", re.compile(r"(?i)(api[_-]?key|secret_key)\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{12,}")),
    ("PASSWORD_ASSIGNMENT", re.compile(r"(?i)password\s*[:=]\s*['\"]?\S{4,}")),
]


def scan_text(text: str, *, known_secret_values: list[str] | None = None) -> list[dict]:
    hits = []
    for name, rx in PATTERNS:
        for m in rx.finditer(text):
            snippet = text[max(0, m.start() - 20) : m.end() + 20]
            if any(ok in snippet for ok in ALLOWED_SNIPPETS):
                continue
            hits.append({"code": name, "excerpt": snippet.replace("\n", " ")[:160]})
    for val in known_secret_values or []:
        if val and len(val) >= 6 and val in text:
            hits.append({"code": "KNOWN_SESSION_VALUE", "excerpt": "[redacted match]"})
    return hits


def scan_tree(root: Path, *, known_secret_values: list[str] | None = None) -> list[dict]:
    findings = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        if path.name.startswith("."):
            continue
        try:
            text = path.read_text(errors="replace")
        except Exception:
            continue
        for hit in scan_text(text, known_secret_values=known_secret_values):
            findings.append({"path": str(path), **hit})
    return findings
