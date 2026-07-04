"""Repo-wide guard: Jinja `.items` attribute access on a dict resolves to the built-in
METHOD, not a key — `{% for x in d.items %}` crashes with
"'builtin_function_or_method' object is not iterable" the first time d is a real dict.

This exact bug shipped in W1a (foresight.html.j2:448, divergence_board.items) and only
surfaced on the first merged-main render because each builder verified against data
where the guard `{% if divergence_board %}` short-circuited.  House law (memory
jinja/china gotchas): use `d['items']` — or better, name the key something else
(foresight_convergence returns {ranked: ...} for exactly this reason).

The guard is a grep over all templates: bare `.items` (no parens, not a subscript)
inside a Jinja statement/expression is banned.
"""
from __future__ import annotations

import re
from pathlib import Path

TEMPLATES = Path(__file__).resolve().parents[1] / "templates"

# `.items` NOT followed by `(` (method call is fine: .items()) and not part of a longer
# identifier (.items_foo). Checked only inside Jinja {% %} / {{ }} spans.
_BARE_ITEMS = re.compile(r"\.items(?![\w(])")
_JINJA_SPAN = re.compile(r"({%.*?%}|{{.*?}})", re.S)


def test_no_bare_dot_items_in_templates():
    offenders: list[str] = []
    for p in sorted(TEMPLATES.rglob("*.j2")):
        text = p.read_text(errors="replace")
        for span in _JINJA_SPAN.finditer(text):
            if _BARE_ITEMS.search(span.group(0)):
                line = text[: span.start()].count("\n") + 1
                offenders.append(f"{p.name}:{line}: {span.group(0)[:80]}")
    assert not offenders, (
        "bare `.items` attribute access in Jinja (resolves to the dict METHOD, "
        "crashes on iteration) — use ['items'] or rename the key:\n" + "\n".join(offenders)
    )
