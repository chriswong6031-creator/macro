"""BC-2 — the 'validated' grep gate (PREREGISTRATION.md §4, D2 §4.3).

DOCTRINE (measurement.html): every number the platform shows must trace to a stored,
leak-free, pre-registered artifact — or it does not ship with the word 'validated'.
This gate makes that mechanically true. It scans the user-facing surfaces
(templates/, site/*.js, generated *_data.js, and the engine/ display-copy fields that
FEED them) in BOTH English and Chinese ('validated', '已验证') and fails if an
AFFIRMATIVE 'validated' claim maps to NO backing:

  A claim is BACKED iff either
    (a) it matches a justified entry in data/regime/validated_claims_allowlist.json
        (each entry names the evidence artifact / study it rests on), or
    (b) the line references an artifact JSON whose top-level `validated == true`.

NEGATED / HEDGED uses are NOT claims and are ignored automatically:
  'no validated ...', 'not a validated ...', 'unvalidated', 'not ... validated',
  'un-validated', "hasn't/doesn't/won't/… (any n't contraction) ... validated",
  'cannot ... validated', '无...验证', '非...验证', '未...验证', '未经验证', '不...已验证'.
These are honest disclaimers ("HK has no validated selection edge") and must never be
forced to cite an artifact.

The gate is phrase-scoped, not file:line-scoped, so it survives page regeneration (the
per-basket/per-stock pages repeat one template phrase; one allowlist entry covers them all).
Rendered site HTML is autoescaped ('&' -> '&amp;', quotes -> '&#39;'/'&#34;'), so token,
negation, and allowlist matching all run on the html.unescape()d text of each line; the
raw line is kept for error reporting.
Its real power: a NEW affirmative 'validated' claim that matches no allowlisted justification
FAILS the build — which is exactly the discipline BC-2 buys.

QUOTED THIRD-PARTY RESEARCH is a STRUCTURAL non-claim (see _THIRD_PARTY_PAGES). The
research vault mirrors syndicated institutional notes verbatim on the nightly render
path, and 'validated' is ordinary English in economics prose ("the June CPI print
validated two likely sources of ongoing disinflation"). BC-2 governs what THE PLATFORM
asserts; reported speech from a named external author asserts nothing about a Macro
Dashboard signal, rank, gate, or artifact, so its stored-artifact requirement has
nothing to attach to. Those spans are skipped by construction rather than allowlisted
one quote at a time — see the module comment above _THIRD_PARTY_PAGES for the safety
invariant that keeps this from weakening the gate.

ENGINE SOURCE COPY is scanned too — see _COPY_BARE / scan_python_copy below. A claim
authored in engine/ used to be gated only once a nightly render carried it onto a page,
which is a day late and on somebody else's PR (#3765 → #3790).

Run:  python -m scripts.check_validated_claims          # scan; exit 1 on any unearned claim
      python -m scripts.check_validated_claims --list    # list every affirmative claim + status
      python -m scripts.check_validated_claims --selftest # prove the gate fires on a synthetic EN+zh
"""
from __future__ import annotations

import argparse
import ast
import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ALLOWLIST = ROOT / "data" / "regime" / "validated_claims_allowlist.json"

# The scanned surfaces (D2 §4.3): templates (source), hand-written + generated site JS,
# generated *_data.js, and the rendered site HTML. EN + zh both.
SCAN_GLOBS = [
    ("templates", ("*.j2", "*.js")),
    ("site", ("*.js", "*.html")),
    # Prophet plan JSONs are rendered user-facing (terminal oracle-tab); scan them too.
    ("site/prophet/plans", ("*.json",)),
]

# Python sources whose DISPLAY-COPY FIELDS are scanned (scan_python_copy). Not the whole
# file — see the _COPY_BARE comment for why.
PY_COPY_GLOBS = [
    ("engine", ("*.py",)),
]

TOKEN = re.compile(r"validated|已验证", re.IGNORECASE)
# KNOWN GAP — 经验证. The zh token list is '已验证' only, so the equally common '经验证'
# ("having been validated") is invisible: #3790's zh copy said 经验证的港股利率／汇率压力
# and sailed through while its EN twin reddened main. Live affirmative uses sit on
# templates/spvector.html.j2, sector_central.html.j2, discovery.html.j2 and others.
#
# NOT widened here, deliberately — it is a separate adjudication, not a token edit.
# MEASURED on this tree (2026-07-27) by adding 经验证 to this pattern and re-scanning:
#   23 newly-red lines — 21 genuinely affirmative claims (each needs an allowlist entry
#   citing an artifact, or de-escalated copy), and 2 FALSE POSITIVES that are honest
#   disclaimers the negation guard cannot see: '香港没有经验证的选股阿尔法' ("HK has no
#   validated selection alpha", templates/hk_lookup.html.j2 + its render).
# _NEG_ZH is [无非未不] — it covers 未经验证 (which is why 641 hedged uses stay ignored)
# but NOT 没有, 尚未, 缺乏. Widening TOKEN without widening _NEG_ZH would therefore turn
# two of the estate's most honest sentences into gate failures, and the cheapest way out
# of that red is to delete the disclaimer — the exact inversion this gate exists to
# prevent. Sequence: widen _NEG_ZH first, then TOKEN, then adjudicate the 21.

# STRUCTURAL non-claims — the token here is a code identifier, a data-field key/value, or an
# i18n token, NOT a displayed prose claim. BC-2 targets DISPLAYED CLAIMS, so these are skipped
# BY CONSTRUCTION (not per-line allowlisted): re-litigating engine-stamped data values or CSS
# class names would be scope creep the gate was never meant to cover.
_STRUCTURAL = [
    # engine-stamped reasoning-trace / scoring field values in generated data + their emitters
    re.compile(r'"tier"\s*:\s*"validated"'),
    re.compile(r'"verdict"\s*:\s*"validated"'),
    re.compile(r'"validated"\s*:\s*(?:true|false)'),          # a data field, not a claim
    re.compile(r"'validated'\s*:\s*(?:True|False)"),
    re.compile(r'"invalidated_membership"'),
    re.compile(r'validated_risk_control'),                    # engine gate-status enum value
    re.compile(r'"(?:absolute_trend_gate|weighting|timing|note)"\s*:.*validated'),
    # CSS class / DOM identifier tokens (e.g. .tr-validated, nbb-validated, val-chip validated)
    re.compile(r'[.\-]validated\b'),
    re.compile(r'class="[^"]*\bvalidated\b[^"]*"'),
    re.compile(r"_vs\s*==\s*'validated'"),                    # template state-var comparison
    re.compile(r"verdict\s*===?\s*'validated'"),
    re.compile(r"=\s*'validated'\s*if"),                      # jinja set _vs = 'validated' if ...
    # conditional-expression literal WITHOUT an '=' — val: {{ ('validated' if ... )|tojson }}
    # (factors drawer payload, #3823) — same code shape as the {% set %} form above
    re.compile(r"\(\s*'validated'\s+if\b"),
    re.compile(r'\bval\s*:\s*"validated"'),                   # its rendered form: val: "validated",
    re.compile(r"scored=True\s*\(validated\)"),
    # engine-emitted 'validated_tag' honesty field: the tag VALUE is earned per-basket in
    # engine.cn_ai_semis_confirmer (only where t=3.27 survives the horse race, #773). Its
    # template plumbing — the {{ ... }} interpolation, the {% set %}, and the {% if == %}
    # comparison — is code, not a displayed prose claim (the displayed prose IS gated).
    re.compile(r"\bvalidated_tag\b"),                         # jinja var / attr interpolation
    re.compile(r"[=!]=\s*'validated'"),                       # {% if htag == 'validated' %}
    # i18n token-map / lexicon dictionary entries: 'key': ['Validated','已验证'] (a label pair)
    re.compile(r"['\"][^'\"]*['\"]\s*:\s*\[\s*['\"]Validated"),
    re.compile(r"validated\s*:\s*\[\s*['\"]Validated"),
    re.compile(r"'(?:go|event-edge|validated|context)'\s*:\s*\[\s*'Validated edge'"),
]

# ── QUOTED THIRD-PARTY RESEARCH — structural non-claims, same family as _STRUCTURAL ──
#
# The research vault mirrors syndicated institutional notes (Goldman, BofA, …) into three
# render targets on the nightly path. Their text is not ours: the pages say so in the
# footer ("ratings and views are the authors', not ours"). 'validated' is ordinary English
# in economics prose, so without this every future note that happens to use the word turns
# main red on ci-pack-0 — far from the render that caused it — until someone hand-writes an
# allowlist entry that is not, in fact, a claim of record.
#
# SAFETY INVARIANT (this is what keeps the skip from weakening the gate):
#   Every PLATFORM-AUTHORED string on these pages exists literally in templates/research_*.j2,
#   which the gate scans with NO exemption. Third-party text reaches site/ only through the
#   named Jinja interpolations enumerated below. Masking those SINKS in the rendered copy
#   therefore cannot hide a claim of ours — the source of that claim is still gated, and so
#   is the rest of the rendered page (the .rr-gate paywall copy, the footer, the crawl-hub
#   chrome, the nav). This is a sink exemption, NOT a path exemption.
#
# Two independent conditions must hold before ANY masking happens: the file must be a known
# syndicated render target, AND it must carry that render's attestation literal. Everything
# else about the file is scanned normally.
#
# A region is ("span", open, close) — protect from the end of `open` to the start of the next
# `close`, across lines — or ("line", pat) — protect the whole line. Spans are used where the
# sink shares a line with our own markup; whole-line where the template emits the tag alone.
_THIRD_PARTY_PAGES = (
    # 1. Per-report landing pages (templates/research_report.html.j2). Third-party sinks:
    #    n.title (title/h1/og/twitter/JSON-LD headline), n.teaser + meta_desc, the verbatim
    #    first-pages excerpt, and the related-reports list (other notes' titles).
    (re.compile(r"^site/research/(?!index\.html$)[^/]+\.html$"),
     # Brand-invariant core of the attestation note: #3850 renamed the corporate entity
     # Mastermind -> MastermindX in research_report.html.j2, and live pages exist in both
     # vintages until every page is re-rendered. The substring matches both.
     "hosts third-party institutional research",
     (
         ("span", re.compile(r"<title>"), re.compile(r"</title>")),
         ("span", re.compile(r'<script type="application/ld\+json">'), re.compile(r"</script>")),
         ("span", re.compile(r"<h1>"), re.compile(r"</h1>")),
         ("span", re.compile(r'<p class="rr-teaser">'), re.compile(r"</p>")),
         # closes on </section>, not the first </div>: .rr-x-fade nests inside .rr-x-body
         ("span", re.compile(r'<div class="rr-x-body">'), re.compile(r"</section>")),
         ("span", re.compile(r'<span class="r-title">'), re.compile(r"</span>")),
         ("line", re.compile(r'^\s*<meta (?:name="description"|property="og:title"'
                             r'|property="og:description"|name="twitter:title"'
                             r'|name="twitter:description") content=')),
     )),
    # 2. The crawl hub (templates/research_index.html.j2) — 160+ third-party report titles
    #    wrapped in our own chrome. Only the title spans are theirs.
    (re.compile(r"^site/research/index\.html$"),
     "Every desk report in the vault",
     (("span", re.compile(r'<span class="ti">'), re.compile(r"</span>")),)),
    # 3. The vault app's SSR-baked catalog snapshot: every third-party title + summary point.
    (re.compile(r"^site/research_vault\.html$"),
     '<script id="rv-catalog"',
     (("span", re.compile(r'<script id="rv-catalog" type="application/json">'),
       re.compile(r"</script>")),)),
)

# Joiner for the surviving fragments of a partly-masked line. Chosen because it is outside
# every character class in _NEG_EN / _NEG_ZH / TOKEN, so excising a span can neither forge a
# token nor let a negation lookback reach across the cut — splicing fails CLOSED (a spliced
# line yields MORE claims, never fewer).
_TP_CUT = "\x00"


def _third_party_specs(rel_path: str, text: str) -> tuple:
    """Regions of `rel_path` holding verbatim third-party research text, or ().

    Living under site/research/ earns nothing on its own: the file must also carry the
    attestation literal its builder emits. A hand-dropped page in that directory, or a
    render whose disclaimer was removed, gets no exemption and is scanned in full.
    """
    for path_re, attest, regions in _THIRD_PARTY_PAGES:
        if path_re.match(rel_path) and attest in text:
            return regions
    return ()


def _mask_third_party(lines: list[str], regions: tuple) -> list[str]:
    """Return each line with its third-party spans excised (the 'visible' platform text).

    Fails CLOSED on anything ambiguous: an opener with no closer before EOF is DISCARDED
    rather than run to the end of the file, so a malformed page is scanned in full instead
    of being silently exempted from its last opener onward.
    """
    line_pats = [r[1] for r in regions if r[0] == "line"]
    span_pats = [(r[1], r[2]) for r in regions if r[0] == "span"]

    cuts: list[tuple[int, int, int, int]] = []          # (line_i, col, line_j, col)
    pending: tuple[int, int, re.Pattern] | None = None   # (line_i, col, close_re)
    for i, raw in enumerate(lines):
        pos = 0
        while pos <= len(raw):
            if pending is not None:
                m = pending[2].search(raw, pos)
                if m is None:
                    break                                # region continues on the next line
                cuts.append((pending[0], pending[1], i, m.start()))
                pos, pending = m.start(), None
                continue
            best = None
            for opener, closer in span_pats:
                mo = opener.search(raw, pos)
                if mo is not None and (best is None or mo.start() < best[0].start()):
                    best = (mo, closer)
            if best is None:
                break
            mo, closer = best
            pending = (i, mo.end(), closer)
            pos = max(mo.end(), pos + 1)                 # always make progress

    per_line: dict[int, list[tuple[int, int]]] = {}
    for si, sc, ej, ec in cuts:                          # `pending` at EOF is dropped
        for i in range(si, ej + 1):
            per_line.setdefault(i, []).append(
                (sc if i == si else 0, ec if i == ej else len(lines[i])))

    out: list[str] = []
    for i, raw in enumerate(lines):
        if any(p.search(raw) for p in line_pats):
            out.append("")
            continue
        iv = per_line.get(i)
        if not iv:
            out.append(raw)
            continue
        keep: list[str] = []
        col = 0
        for a, b in sorted(iv):
            if a > col:
                keep.append(raw[col:a])
            col = max(col, b)
        if col < len(raw):
            keep.append(raw[col:])
        out.append(_TP_CUT.join(k for k in keep if k))
    return out


# Negation / hedge guards — if any of these appears in the ~30 chars BEFORE the token on the
# same line, the use is a disclaimer, not a claim.
_NEG_EN = re.compile(
    r"(?:\bno\b|\bnot\b|\bnon-?|\bun-?|\bnever\b|\bno-\b|without|"
    r"lacks?|\bwithout\b|\bcannot\b|\b\w+n['’]t\b)\s*[\w\s,'’\-/×&()]{0,30}$",
    re.IGNORECASE)
# 'un'/'in'/'re' glued directly to the token, e.g. 'unvalidated', 'invalidated', 're-validated'
_GLUED_UN = re.compile(r"un-?$|re-?$|in$", re.IGNORECASE)
_NEG_ZH = re.compile(r"[无非未不][一-鿿\s]{0,12}$")


def _load_allowlist() -> list[dict]:
    if not ALLOWLIST.exists():
        return []
    d = json.loads(ALLOWLIST.read_text(encoding="utf-8"))
    return d.get("allow", [])


def _is_negated(line: str, start: int) -> bool:
    """Is the token at char `start` a negated/hedged (non-claim) use?"""
    pre = line[:start]
    low = pre.lower()
    if _NEG_EN.search(pre):
        return True
    if _GLUED_UN.search(pre):                       # unvalidated / re-validated
        return True
    if _NEG_ZH.search(pre):
        return True
    # 'not ... validated' / 'no ... validated edge' with words in between
    tail = low[-60:]
    if re.search(r"\b(no|not|never|without|un)\b[\w\s,'’\-/×&()]{0,55}$", tail):
        return True
    return False


def _artifact_backed(line: str) -> bool:
    """Does the line reference an artifact JSON with top-level validated==true?"""
    for m in re.finditer(r"data/[\w/\-]+\.json", line):
        p = ROOT / m.group(0)
        try:
            if p.exists() and json.loads(p.read_text(encoding="utf-8")).get("validated") is True:
                return True
        except Exception:  # noqa: BLE001
            continue
    return False


def _allow_match(line: str, allow: list[dict]) -> dict | None:
    low = line.lower()
    for entry in allow:
        m = entry.get("match", "")
        if m and m.lower() in low:
            return entry
    return None


def _scan_line(line: str, allow: list[dict]) -> tuple[int, list[tuple[bool, dict | None]]]:
    """Evaluate one raw line. Returns (n_negated, hits) — one (backed, allow_entry) per
    affirmative token occurrence. Token/negation/allowlist matching runs on the
    html.unescape()d text: rendered site HTML is autoescaped, so an allowlist entry
    containing '&' can never match its '&amp;' rendered form, and an entity-bearing
    negation prefix ("isn&#39;t a validated") reads as an affirmative claim. Callers
    keep the raw line for reporting."""
    if any(sp.search(line) for sp in _STRUCTURAL):
        return 0, []                                    # structural non-claim line
    norm = html.unescape(line)
    n_negated = 0
    hits: list[tuple[bool, dict | None]] = []
    for m in TOKEN.finditer(norm):
        if _is_negated(norm, m.start()):
            n_negated += 1
            continue
        entry = _allow_match(norm, allow)
        backed = entry is not None or _artifact_backed(norm)
        hits.append((backed, entry))
    return n_negated, hits


# ── ENGINE SOURCE COPY (PY_COPY_GLOBS) ───────────────────────────────────────────────
#
# WHY THIS EXISTS (#3765 → #3790). BC-2 used to scan only RENDERED surfaces, so copy
# authored in engine/ was gated only AFTER a nightly render carried it onto a page — a
# day later, on a PR that did not write it. #3765 added an unearned "Validated HK
# rate/FX pressure" to engine/intl_recovery_quality.macro_backdrop, passed CI green, and
# reddened main on ci-pack-0 with the 2026-07-27 render; every open PR inherited the
# failure until #3790 landed. The claim now fails at its OWN PR, next to its author.
#
# WHY AST AND NOT A LINE SCAN. The #3765 defect was shaped like this:
#
#     "read_en": (
#         "Macro backdrop is shown separately from the price state. Validated HK "
#         "rate/FX pressure lives in the pullback radar; ..."
#     ),
#
# The field name and the token are on DIFFERENT LINES. A grep-shaped rule keyed on "a
# display-copy field name and 'validated' on the same line" would have sailed straight
# past the exact defect it was written for. Python folds implicit concatenation at parse
# time, so the AST sees ONE string: we scan the folded value and report the node's line.
#
# WHY FIELD-RESTRICTED, NOT WHOLE-FILE. engine/ carries ~939 token occurrences; scanning
# whole files the way templates/ are scanned surfaces 509 findings, essentially all of
# them code identifiers, enum values, `"validated": True` data fields, LLM system
# prompts, and research-registry bookkeeping. BC-2 targets DISPLAYED CLAIMS. Binding the
# scan to the fields that ARE display copy reduces that to 10 real strings — all of which
# this change resolves, so the rule ships with zero pre-existing debt.
#
# RELATION TO _STRUCTURAL. `"note": ...validated` is a structural skip on the RENDERED
# side (an engine-stamped field inside a minified data blob, where one match suppresses a
# whole 100kB line). Scanning `note` HERE is the other half of that bargain, not a
# contradiction: the claim is gated once, at the source, where a human can fix it.
#
# The house's display-copy marker is the bilingual `_en`/`_zh` suffix — there is no
# reason to translate an internal note into Chinese — so ANY suffixed field counts. The
# bare names below are the display-copy fields the codebase also uses unsuffixed.
# DELIBERATELY EXCLUDED (checked against the census, all internal): `notes` (plural —
# engine/intl_claims research-registry bookkeeping, "W4-C7 VERDICT: CONTEXT (do NOT
# wire)"), `description` (LLM tool schemas in engine/neuralweb), and `reason` / `tier` /
# `verdict` / `status` (scoring enums and trace fields).
_COPY_BARE = frozenset({
    "label", "caveat", "blurb", "headline", "summary", "detail", "read",
    "note", "disclaimer", "tooltip", "takeaway", "subtitle",
})
_COPY_SUFFIX = re.compile(r"_(?:en|zh)$")


def _is_copy_field(name: str) -> bool:
    return name in _COPY_BARE or bool(_COPY_SUFFIX.search(name))


def _copy_strings(tree: ast.AST) -> list[tuple[str, ast.Constant]]:
    """Every string literal bound to a display-copy field name, as (field, node).

    Covers the shapes engine/ actually uses to emit copy: dict literals
    ({"read_en": ...}), call keywords (RadarProfile(caveat_en=...), _row(why_zh=...)),
    plain/annotated assignment, attribute and constant-subscript assignment. Values are
    unwrapped through ternaries, `+` concatenation, f-string literal parts, and
    list/tuple elements, because each of those is a live way to write shipping copy.
    """
    out: list[tuple[str, ast.Constant]] = []
    seen: set[tuple[int, int]] = set()

    def emit(name: str, node: ast.AST) -> None:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            key = (node.lineno, node.col_offset)
            if key not in seen:
                seen.add(key)
                out.append((name, node))
        elif isinstance(node, ast.IfExp):                 # x if cond else y
            emit(name, node.body); emit(name, node.orelse)
        elif isinstance(node, ast.BinOp):                 # "a" + var + "b"
            emit(name, node.left); emit(name, node.right)
        elif isinstance(node, ast.JoinedStr):             # f"...{v}..." — literal parts
            for v in node.values:
                emit(name, v)
        elif isinstance(node, (ast.List, ast.Tuple)):
            for e in node.elts:
                emit(name, e)

    for n in ast.walk(tree):
        if isinstance(n, ast.Dict):
            for k, v in zip(n.keys, n.values):
                if isinstance(k, ast.Constant) and isinstance(k.value, str) \
                        and _is_copy_field(k.value):
                    emit(k.value, v)
        elif isinstance(n, ast.Call):
            for kw in n.keywords:
                if kw.arg and _is_copy_field(kw.arg):
                    emit(kw.arg, kw.value)
        elif isinstance(n, ast.Assign):
            for t in n.targets:
                if isinstance(t, ast.Name) and _is_copy_field(t.id):
                    emit(t.id, n.value)
                elif isinstance(t, ast.Attribute) and _is_copy_field(t.attr):
                    emit(t.attr, n.value)
                elif isinstance(t, ast.Subscript) and isinstance(t.slice, ast.Constant) \
                        and isinstance(t.slice.value, str) and _is_copy_field(t.slice.value):
                    emit(t.slice.value, n.value)
        elif isinstance(n, ast.AnnAssign) and n.value is not None \
                and isinstance(n.target, ast.Name) and _is_copy_field(n.target.id):
            emit(n.target.id, n.value)
    return out


def scan_python_copy(rel_path: str, text: str, allow: list[dict]) -> tuple[list[dict], dict]:
    """Scan the display-copy field values of one Python source. Same contract as scan_text.

    Fails CLOSED on an unparseable file: a syntax error is reported as a finding rather
    than skipped, so the gate can never be silently bypassed by a file it cannot read.
    """
    stats = {"claims": 0, "backed": 0, "negated": 0, "third_party": 0, "ok": []}
    try:
        tree = ast.parse(text)
    except SyntaxError as e:
        return ([{"file": rel_path, "line_no": e.lineno or 1,
                  "text": f"UNPARSEABLE ({e.msg}) — cannot prove it carries no unearned claim"}],
                stats)

    unearned: list[dict] = []
    for field, node in _copy_strings(tree):
        if not TOKEN.search(node.value):
            continue
        n_neg, hits = _scan_line(node.value, allow)
        stats["negated"] += n_neg
        for backed, entry in hits:
            stats["claims"] += 1
            if backed:
                stats["backed"] += 1
                stats["ok"].append((node.lineno, ("allow:" + entry["match"]) if entry
                                    else "artifact validated:true"))
            else:
                unearned.append({"file": rel_path, "line_no": node.lineno,
                                 "text": f"[{field}] " + node.value.strip()[:160]})
    return unearned, stats


def scan_text(rel_path: str, text: str, allow: list[dict]) -> tuple[list[dict], dict]:
    """Scan one file's `text` as if it lived at repo-relative `rel_path`.

    Pure — no filesystem beyond _artifact_backed's citation lookup. Returns
    (unearned findings, counters). The path matters: it decides whether the file is a
    syndicated-research render whose third-party sinks are masked (_third_party_specs).
    Shared by scan(), --selftest, and tests/test_validated_claims_thirdparty.py so the
    regression test pins the SAME code path CI runs.
    """
    lines = text.splitlines()
    specs = _third_party_specs(rel_path, text)
    visible = _mask_third_party(lines, specs) if specs else lines
    unearned: list[dict] = []
    stats = {"claims": 0, "backed": 0, "negated": 0, "third_party": 0, "ok": []}
    for i, (raw, vis) in enumerate(zip(lines, visible), 1):
        if specs and raw != vis:
            stats["third_party"] += (len(TOKEN.findall(html.unescape(raw)))
                                     - len(TOKEN.findall(html.unescape(vis))))
        n_neg, hits = _scan_line(vis, allow)
        stats["negated"] += n_neg
        for backed, entry in hits:
            stats["claims"] += 1
            if backed:
                stats["backed"] += 1
                stats["ok"].append((i, ("allow:" + entry["match"]) if entry
                                    else "artifact validated:true"))
            else:
                unearned.append({"file": rel_path, "line_no": i, "text": raw.strip()[:160]})
    return unearned, stats


def scan(list_all: bool = False) -> list[dict]:
    """Return the list of UNEARNED affirmative 'validated' claims. Prints per-claim status
    when list_all. Each unearned finding is {file, line_no, text}."""
    allow = _load_allowlist()
    unearned: list[dict] = []
    n_claims = n_negated = n_backed = n_tp = 0
    # Rendered surfaces are scanned whole-file; Python sources only through their
    # display-copy fields (scan_python_copy) — same reporting shape either way.
    surfaces = ([(sub, pats, scan_text) for sub, pats in SCAN_GLOBS]
                + [(sub, pats, scan_python_copy) for sub, pats in PY_COPY_GLOBS])
    for sub, pats, scanner in surfaces:
        base = ROOT / sub
        if not base.exists():
            continue
        for pat in pats:
            for f in sorted(base.rglob(pat)):
                if "node_modules" in str(f):
                    continue
                try:
                    text = f.read_text(encoding="utf-8")
                except Exception:  # noqa: BLE001
                    continue
                rel = f.relative_to(ROOT).as_posix()
                found, st = scanner(rel, text, allow)
                n_claims += st["claims"]; n_backed += st["backed"]
                n_negated += st["negated"]; n_tp += st["third_party"]
                unearned.extend(found)
                if list_all:
                    for i, why in st["ok"]:
                        print(f"  OK   {rel}:{i}  [{why}]")
                    for r in found:
                        print(f"  MISS {rel}:{r['line_no']}  {r['text'][:120]}")
    if list_all:
        print(f"\naffirmative claims: {n_claims}  backed: {n_backed}  "
              f"negated/hedged (ignored): {n_negated}  "
              f"quoted third-party (structural skip): {n_tp}  UNEARNED: {len(unearned)}")
    return unearned


# A research-vault report page reduced to its load-bearing shape — the same sinks, the same
# nesting, the same attestation footer the real render emits. Exported so the regression test
# and --selftest exercise one fixture: if the template's structure moves, both notice.
# `body` is verbatim third-party text; `platform` is OUR copy inside the .rr-gate paywall.
SELFTEST_REPORT_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<title>{title} — Goldman Sachs · Jul 24, 2026 | Mastermind Research Vault</title>
<meta name="description" content="Goldman Sachs institutional research · Jul 24, 2026. {teaser}">
<meta property="og:title" content="{title} — Goldman Sachs">
<script type="application/ld+json">{{"headline": "{title}", "author": "Goldman Sachs"}}</script>
</head>
<body>
<main class="rr-wrap">
  <article class="rr">
    <h1>{title}</h1>
    <p class="rr-teaser"><span class="lead"><span class="l-en">From the report</span><span class="l-zh">报告摘录</span></span>{teaser}</p>
    <section class="rr-x" aria-label="First pages of the report">
      <div class="rr-x-head">
        <span class="rr-x-eyebrow"><span class="l-en">Inside the report</span></span>
        <span class="rr-x-src"><span class="l-en">Verbatim from the original PDF — first pages</span></span>
      </div>
      <div class="rr-x-body">
<p>{body}</p>        <div class="rr-x-fade" aria-hidden="true"></div>
      </div>
    </section>
    <div class="rr-gate">
      <h2><span class="l-en">Read the full report + PDF</span></h2>
      <p><span class="l-en">{platform}</span><span class="l-zh">{platform_zh}</span></p>
    </div>
  </article>
  <section class="rr-rel">
    <ul>
      <li><a href="other.html"><span class="r-inst">Goldman Sachs</span><span class="r-title">{related}</span></a></li>
    </ul>
  </section>
  <p class="rr-foot">
    <span class="l-en"><b>Not investment advice.</b> {attest} for reference and education; ratings and views are the authors', not ours.</span>
  </p>
</main>
</body>
</html>
"""
_ATTEST = "hosts third-party institutional research"
_NEUTRAL = {"title": "Oil Prices and Upcoming Inflation Prints", "teaser": "Oil rebounded 35%.",
            "body": "Core CPI slowed broadly in June.", "platform": "Pro members get the PDF.",
            "platform_zh": "Pro 会员可读全文。", "related": "Three things in China",
            "attest": _ATTEST}


def _page(**over) -> str:
    return SELFTEST_REPORT_PAGE.format(**{**_NEUTRAL, **over})


def selftest() -> int:
    """Prove the gate FIRES on a synthetic unearned 'validated' in EN and in zh, does NOT
    fire on negated uses, and matches through HTML autoescaping ('&' vs '&amp;').
    Synthetic lines only — never touches the tree."""
    allow = _load_allowlist()
    # Synthetic allowlist for the autoescape cases: an '&'-bearing match string must cover
    # its '&amp;' rendered form. Deliberately NOT in the real allowlist — it exercises
    # _scan_line's html.unescape normalization, nothing on the tree cites it.
    amp_allow = [{"match": "validated & wired for selftest"}]
    cases = [
        ("EN affirmative unearned", "This signal is validated as a real cross-sectional alpha.", True, allow),
        ("zh affirmative unearned", "该信号是已验证的方向性优势。", True, allow),
        ("EN negated (disclaimer)", "The rank has no validated forward edge here.", False, allow),
        ("zh negated (disclaimer)", "此处无已验证方向信号。", False, allow),
        ("EN allowlisted", "gated by the validated MACD-2D × StochRSI-3D confluence.", False, allow),
        ("allowlisted '&' entry matches rendered '&amp;'",
         "<h2>Scored — validated &amp; wired for selftest</h2>", False, amp_allow),
        ("unearned claim behind '&amp;' still fires",
         "This edge is validated &amp; deployed everywhere.", True, amp_allow),
        ("negation behind entity apostrophe ignored",
         "This isn&#39;t a validated edge.", False, allow),
        ("EN negated perfect-tense contraction",
         "the PRIOR hasn't been validated, so trade the tape, not the narrative.", False, allow),
        ("perfect-tense contraction behind entity apostrophe",
         "the PRIOR hasn&#39;t been validated, so trade the tape.", False, allow),
        ("EN negated 'cannot be validated'",
         "This construction cannot be validated on the available window.", False, allow),
        ("jinja ternary literal (factors val payload source) is code, not prose",
         "    val: {{ ('validated' if (r.survives_fdr and r.mean_ic is not none and r.mean_ic > 0)", False, allow),
        ("rendered factors val payload is a data value, not a claim",
         '    val: "validated",', False, allow),
    ]
    ok = True
    for name, line, should_fire, allow_entries in cases:
        _, hits = _scan_line(line, allow_entries)
        fired = any(not backed for backed, _ in hits)
        status = "PASS" if fired == should_fire else "FAIL"
        if fired != should_fire:
            ok = False
        print(f"  [{status}] {name}: fired={fired} expected={should_fire}")

    # ── page-level: the quoted-third-party structural skip ───────────────────────────
    # The point of every FIRES case below is that the exemption is scoped to third-party
    # SINKS, not to site/research/: our own copy on the very same page still fails.
    quoted = "the June print validated two likely sources of ongoing disinflation"
    ours = "This edge is validated across every desk."
    rp = "site/research/us-daily-oil-and-inflation-3da181.html"
    page_cases = [
        ("quoted 'validated' in the verbatim excerpt is not a claim",
         rp, _page(body=quoted), False),
        ("...in the third-party report title", rp, _page(title="Q2 Results Validated Our Thesis"), False),
        ("...in the third-party teaser (and the meta description)",
         rp, _page(teaser=quoted), False),
        ("...in a related report's title", rp, _page(related="Q2 Results Validated Our Thesis"), False),
        ("OUR copy in .rr-gate on the same page STILL FAILS", rp, _page(platform=ours), True),
        ("OUR zh copy on the same page STILL FAILS", rp, _page(platform_zh="该信号是已验证的。"), True),
        ("quoted text WITHOUT the attestation gets no exemption",
         rp, _page(body=quoted, attest="Mastermind hosts research"), True),
        ("same page shape in templates/ is never exempt",
         "templates/research_report.html.j2", _page(body=quoted), True),
        ("same page shape outside the research vault is never exempt",
         "site/leader_radar.html", _page(body=quoted), True),
        ("unclosed excerpt region fails CLOSED (nothing masked)",
         rp, _page(body=quoted).replace("</section>", "<!-- -->")
             .replace("</html>", f"<p>{ours}</p></html>"), True),
        ("crawl hub: third-party title in <span class=\"ti\">",
         "site/research/index.html",
         '<p class="rx-sub">Every desk report in the vault</p>\n'
         '<li><a href="x.html"><span class="ti">Q2 Results Validated Our Thesis</span></a></li>', False),
        ("crawl hub: our own chrome on that page STILL FAILS",
         "site/research/index.html",
         '<p class="rx-sub">Every desk report in the vault</p>\n'
         f"<p>{ours}</p>", True),
        ("vault page: third-party titles inside the baked catalog JSON",
         "site/research_vault.html",
         '<script id="rv-catalog" type="application/json">'
         '{"items":[{"title":"Q2 Results Validated Our Thesis"}]}</script>', False),
        ("vault page: our own copy outside the catalog STILL FAILS",
         "site/research_vault.html",
         '<script id="rv-catalog" type="application/json">{"items":[]}</script>\n'
         f"<p>{ours}</p>", True),
    ]
    for name, rel, text, should_fire in page_cases:
        found, _ = scan_text(rel, text, allow)
        fired = bool(found)
        status = "PASS" if fired == should_fire else "FAIL"
        if fired != should_fire:
            ok = False
        print(f"  [{status}] {name}: fired={fired} expected={should_fire}")

    # ── engine source copy: the #3765 → #3790 latency ────────────────────────────────
    # The first case is the ACTUAL defect, byte-for-byte in its original shape: the
    # field name on one line, the token on the next. It is the reason this scan parses
    # instead of grepping — a same-line rule scores 0 on it.
    py_cases = [
        ("#3765 read_en: token on a bare continuation line FIRES", True, '''
def macro_backdrop() -> dict:
    return {
        "read_en": (
            "Macro backdrop is shown separately from the price state. Validated HK "
            "rate/FX pressure lives in the pullback radar; Iran/oil and the midterm "
            "calendar remain unscored context."
        ),
    }
'''),
        ("zh 已验证 in a label_zh FIRES", True,
         'TIERS = [{"key": "x", "label_zh": "已验证的选股优势"}]\n'),
        ("dataclass/profile keyword copy FIRES",
         True, 'P = RadarProfile(key="x", caveat_en="This sleeve is validated on HK breadth.")\n'),
        ("f-string literal part FIRES",
         True, 'note = f"validated macro gauge ({band})"\n'.replace("{band}", "{b}")),
        ("negated engine copy is NOT a claim", False,
         '{"detail_en": "HK has no validated selection edge; context only."}\n'),
        ("allowlisted engine copy does not fire", False,
         '{"caveat_en": "gated by the validated MACD-2D × StochRSI-3D confluence."}\n'),
        # Everything below is why the scan is field-restricted rather than whole-file:
        # engine internals use this token constantly and assert nothing to a user.
        ("data field `\"validated\": True` is not copy", False,
         'row = {"validated": True, "tier": "scored"}\n'),
        ("code identifiers are not copy", False,
         'validated_tag = compute()\nif verdict == "validated":\n    ship()\n'),
        ("research-registry `notes` bookkeeping is out of scope", False,
         '_row(notes="W4-C7 VERDICT: validated at index level, do NOT wire")\n'),
        ("LLM tool `description` is out of scope", False,
         'TOOL = {"description": "Read the validated mechanism-pathways artifact."}\n'),
        ("unparseable engine file FAILS CLOSED", True, 'def broken(:\n'),
    ]
    for name, should_fire, src in py_cases:
        found, _ = scan_python_copy("engine/_selftest.py", src, allow)
        fired = bool(found)
        status = "PASS" if fired == should_fire else "FAIL"
        if fired != should_fire:
            ok = False
        print(f"  [{status}] {name}: fired={fired} expected={should_fire}")
    return 0 if ok else 1


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true", help="print every affirmative claim + status")
    ap.add_argument("--selftest", action="store_true", help="prove the gate fires on synthetic EN+zh")
    args = ap.parse_args()

    if args.selftest:
        sys.exit(selftest())

    unearned = scan(list_all=args.list)
    if unearned:
        print(f"\n::error:: {len(unearned)} UNEARNED 'validated' claim(s) — each must map to a "
              f"backing artifact (validated:true) or a justified entry in "
              f"data/regime/validated_claims_allowlist.json:", file=sys.stderr)
        for r in unearned[:40]:
            print(f"  {r['file']}:{r['line_no']}  {r['text']}", file=sys.stderr)
        if len(unearned) > 40:
            print(f"  ... and {len(unearned) - 40} more", file=sys.stderr)
        sys.exit(1)
    print("check_validated_claims: OK — every affirmative 'validated' claim is backed.")


if __name__ == "__main__":
    main()
