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

Exemption: `{% set ns = namespace(...) %}` variables. On a jinja2.utils.Namespace,
`.items` is plain attribute access (there is no dict method to shadow it), so
`ns.items` is safe and idiomatic — variables assigned from namespace() in the same
file are whitelisted.
"""
from __future__ import annotations

import re
from pathlib import Path

TEMPLATES = Path(__file__).resolve().parents[1] / "templates"

# `.items` NOT followed by `(` (method call is fine: .items()) and not part of a longer
# identifier (.items_foo). The optional leading identifier captures the receiver so
# namespace variables can be exempted; a non-identifier receiver (`foo['x'].items`)
# leaves the group empty and is always flagged. Checked only inside Jinja spans.
_BARE_ITEMS = re.compile(r"(\w+)?\.items(?![\w(])")
_JINJA_SPAN = re.compile(r"({%.*?%}|{{.*?}})", re.S)
_NS_DECL = re.compile(r"{%-?\s*set\s+(\w+)\s*=\s*namespace\(")


def _bare_items_offenses(text: str) -> list[tuple[int, str]]:
    """Return (line, snippet) for each Jinja span with a bare `.items` access,
    skipping accesses on variables declared via `{% set x = namespace(...) %}`."""
    ns_vars = set(_NS_DECL.findall(text))
    offenses: list[tuple[int, str]] = []
    for span in _JINJA_SPAN.finditer(text):
        for m in _BARE_ITEMS.finditer(span.group(0)):
            if m.group(1) in ns_vars:
                continue
            line = text[: span.start()].count("\n") + 1
            offenses.append((line, span.group(0)[:80]))
            break  # one report per span
    return offenses


def test_no_bare_dot_items_in_templates():
    offenders: list[str] = []
    for p in sorted(TEMPLATES.rglob("*.j2")):
        text = p.read_text(errors="replace")
        for line, snippet in _bare_items_offenses(text):
            offenders.append(f"{p.name}:{line}: {snippet}")
    assert not offenders, (
        "bare `.items` attribute access in Jinja (resolves to the dict METHOD, "
        "crashes on iteration) — use ['items'] or rename the key:\n" + "\n".join(offenders)
    )


def test_fixture_bare_items_still_caught():
    # The original W1a bug shape must still fail the scan.
    bad = "{% if divergence_board %}{% for x in divergence_board.items %}{{ x }}{% endfor %}{% endif %}"
    assert _bare_items_offenses(bad)
    # Non-identifier receivers are never exempt, even with a namespace in scope.
    bad_subscript = "{% set ns = namespace(items=[]) %}{% for x in board['us'].items %}{{ x }}{% endfor %}"
    assert _bare_items_offenses(bad_subscript)
    # A namespace declaration does not launder OTHER variables' .items access.
    mixed = "{% set ns = namespace(items=[]) %}{% for x in some_dict.items %}{{ x }}{% endfor %}"
    assert _bare_items_offenses(mixed)


def test_fixture_namespace_items_exempt():
    good = (
        "{%- set ns = namespace(items=[]) -%}"
        "{%- set ns.items = ns.items + [1] -%}"
        "{% if ns.items %}{% for x in ns.items %}{{ x }}{% endfor %}{% endif %}"
    )
    assert not _bare_items_offenses(good)
    # .items() method calls and longer identifiers were never flagged; keep it so.
    still_fine = "{% for k, v in d.items() %}{{ d.items_total }}{% endfor %}"
    assert not _bare_items_offenses(still_fine)
