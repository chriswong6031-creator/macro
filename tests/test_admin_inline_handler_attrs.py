"""Inline `on*=` handlers in the admin console must not interpolate JS string literals.

`admin/static/app.js` builds its markup from template literals, and several
helpers paste a JS SNIPPET into a double-quoted HTML attribute:

    function entChip(label, active, on) {
      return `<button class="ent-chip" onclick="${on}">...`;
    }

Callers built `on` with `JSON.stringify`, which emits DOUBLE quotes:

    entChip(..., `entSetFilter('tier',${JSON.stringify(t)})`)
    -> onclick="entSetFilter('tier',"pro")"

The HTML parser ends the attribute at the second `"`, so the browser stores
`entSetFilter('tier',` — an incomplete expression that throws on parse. The chip
renders looking completely normal and the click does NOTHING. Six call sites
shipped this way: the entitlements tier + status chips, the support-ticket status
chips, the ticket thread's Resolve/Close buttons, its Send-reply button (the
operator could not answer a support ticket at all), and the marketing department
cards.

Why no existing guard caught it: `scripts/check_inline_js.py` DOES parse `on*=`
attributes (the #2321 gap) and would have flagged this instantly — but it scans
`site/` and `templates/`, where the attribute exists on disk. Here the attribute
is only ever materialised in the browser, so there was nothing on disk to parse.
The defect is visible only in the SOURCE that builds it, which is what this scans.

The fix is to keep `on` a fixed, code-only string and carry values in `data-`
attributes (attribute-escaped) read back via `this.dataset.<key>`:

    <button data-tier="pro" onclick="entSetFilter('tier', this.dataset.tier)">

Scope of this guard: the `JSON.stringify`-into-an-attribute shape, which is the
one that shipped broken and is mechanically detectable with no false positives.
It deliberately does NOT flag `onclick="go('${s.key}')"`-style interpolation of a
code-defined constant — deciding whether such a value can contain a quote needs
type information, and an allowlist of "safe" call sites would rot. Those sites
were surveyed when this guard landed and every one carries a literal defined in
this repo (route names, `#anchor` ids, `'monthly'|'annual'|'lifetime'`).

Run: python3 -m pytest tests/test_admin_inline_handler_attrs.py -q
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ADMIN_STATIC = ROOT / "admin" / "static"

# A double-quoted inline event-handler attribute. Matching `[^"]*` is not a
# limitation here, it is the point: the HTML parser stops at the same character
# this regex stops at, so what the pattern captures IS what the browser stores.
HANDLER_ATTR_RE = re.compile(r'\bon[a-z]+="([^"]*)"')

# A `${...}` template interpolation, tolerating one level of nested braces.
INTERP_RE = re.compile(r"\$\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}")


def find_offenders(text: str) -> list[tuple[int, str, str]]:
    """Return (line, attribute, expression) for each way an attribute can truncate.

    Two rules, because the defect shipped in two positions:

    1. A raw `JSON.stringify(...)` interpolated into the attribute. This is the
       direct form (`onclick="supReply(${JSON.stringify(id)})"`).

    2. A whole-attribute interpolation (`onclick="${on}"`) that is not esc()
       wrapped. This is the CHOKE POINT form: `entChip`/`supChip`/`ecChip` each
       paste a caller-supplied snippet in as the entire attribute value, so the
       JSON.stringify lives at the call site and rule 1 cannot see it. Four of
       the six shipped call sites were only reachable through here — a guard with
       rule 1 alone would have missed the two chips this defect was reported for.
       A value that becomes an entire handler is author-supplied text of unknown
       provenance; requiring esc() makes it survive the parser whatever it holds.

    `esc(JSON.stringify(x))` is NOT an offender under either rule: esc turns `"`
    into `&quot;`, which the parser decodes back inside the attribute value, so
    the handler survives intact. Only the raw forms truncate.
    """
    offenders: list[tuple[int, str, str]] = []
    for match in HANDLER_ATTR_RE.finditer(text):
        body = match.group(1)
        if "${" not in body:
            continue
        line = text.count("\n", 0, match.start()) + 1
        interps = INTERP_RE.findall(body)

        # Rule 2: the attribute is exactly one interpolation and nothing else.
        if len(interps) == 1 and body.strip() == "${" + interps[0] + "}":
            expr = interps[0].strip()
            if not expr.startswith("esc("):
                offenders.append((line, match.group(0), expr))
                continue

        # Rule 1: a raw JSON.stringify anywhere in the attribute.
        for expr in interps:
            stripped = expr.strip()
            if "JSON.stringify" in stripped and not stripped.startswith("esc("):
                offenders.append((line, match.group(0), stripped))
    return offenders


def _admin_js_files() -> list[Path]:
    return sorted(ADMIN_STATIC.glob("*.js"))


def test_admin_static_dir_is_present():
    """Fail loudly rather than pass over an empty glob.

    A guard whose scan set is empty refuses nothing and still reads green —
    the shape that let #3802 scan 0 of 130 files. Assert the subject exists.
    """
    assert ADMIN_STATIC.is_dir(), f"missing admin static dir: {ADMIN_STATIC}"
    files = _admin_js_files()
    assert files, f"no *.js found under {ADMIN_STATIC} — this guard scanned nothing"
    assert (ADMIN_STATIC / "app.js") in files, "app.js is not in the scan set"


def test_no_json_stringify_interpolated_into_a_handler_attribute():
    findings: list[str] = []
    for path in _admin_js_files():
        text = path.read_text(encoding="utf-8")
        for line, attr, expr in find_offenders(text):
            rel = path.relative_to(ROOT)
            findings.append(f"  {rel}:{line}\n    attribute: {attr}\n    expression: ${{{expr}}}")

    assert not findings, (
        "JSON.stringify emits DOUBLE quotes, which close the HTML attribute they "
        "are interpolated into. The browser keeps only the text before the second "
        'quote, so `onclick=\"fn(${JSON.stringify(v)})\"` is stored as `fn(` — the '
        "control renders normally and clicking it does nothing.\n\n"
        "Carry the value in a data- attribute instead and read it in the handler:\n"
        '  `<button data-tier="${esc(t)}" onclick="fn(this.dataset.tier)">`\n\n'
        "Offending sites:\n" + "\n".join(findings)
    )


def test_guard_catches_a_planted_offender():
    """The shipped shape verbatim, through the SAME function the real test uses.

    A mutation test that re-implements the scan proves nothing about the scan
    that actually runs. This calls find_offenders directly.
    """
    planted = (
        '"use strict";\n'
        "function entChip(label, active, on) {\n"
        '  return `<button class="ent-chip" onclick="${on}">${esc(label)}</button>`;\n'
        "}\n"
        "function render(tiers) {\n"
        "  return tiers.map(t => entChip(t, false,\n"
        "    `entSetFilter('tier',${JSON.stringify(t)})`)).join('');\n"
        "}\n"
        "function card(dept) {\n"
        '  return `<a href="#/d" onclick="event.preventDefault();goto(${JSON.stringify(dept.id)})">x</a>`;\n'
        "}\n"
    )
    offenders = find_offenders(planted)
    attrs = [attr for _, attr, _ in offenders]

    # Rule 2 — the choke point. Without this the two chips the defect was
    # REPORTED for go undetected: their JSON.stringify sits at the call site,
    # where no attribute is being written, so rule 1 cannot see it.
    assert 'onclick="${on}"' in attrs, (
        "guard missed the unescaped whole-attribute interpolation in entChip — "
        "this is the shape that made the tier and status chips dead.\n"
        f"got: {offenders}"
    )
    # Rule 1 — the direct form.
    direct = [(a, e) for _, a, e in offenders if "JSON.stringify" in e]
    assert direct, f"guard missed the raw JSON.stringify in card(): {offenders}"
    assert "goto(" in direct[0][0], f"finding does not name the offending attribute: {offenders}"


def test_guard_does_not_flag_the_escaped_form():
    """Clean control: a guard that flags everything is as useless as one that flags nothing."""
    clean = (
        '"use strict";\n'
        "function chip(k, on) {\n"
        '  return `<button data-kind="${esc(k)}" onclick="filter(this.dataset.kind)">x</button>`;\n'
        "}\n"
        "function toggle(id, on) {\n"
        "  /* esc() re-encodes the quotes, so the attribute survives the parser */\n"
        '  return `<button onclick="chanToggle(this, ${esc(JSON.stringify(id))}, ${on ? "false" : "true"})"></button>`;\n'
        "}\n"
        "function pager(page) {\n"
        '  return `<button onclick="goto(${page - 1})">prev</button>`;\n'
        "}\n"
    )
    assert find_offenders(clean) == [], "guard flagged a safe construction"
