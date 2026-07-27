"""BC-2 — the 'validated' grep gate (PREREGISTRATION.md §4, D2 §4.3).

DOCTRINE (measurement.html): every number the platform shows must trace to a stored,
leak-free, pre-registered artifact — or it does not ship with the word 'validated'.
This gate makes that mechanically true. It scans the user-facing surfaces
(templates/, site/*.js, generated *_data.js) in BOTH English and Chinese ('validated',
'已验证') and fails if an AFFIRMATIVE 'validated' claim maps to NO backing:

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

REPUBLISHED THIRD-PARTY TEXT is not a house claim either. The research vault mirrors
institutional notes onto ``site/research/`` — a report's own title, its provider-written
summary bullets, and a verbatim first-pages excerpt of the PDF. When a sell-side analyst
writes that a CPI print "validated two likely sources of disinflation", the estate is
quoting, not claiming: there is no Macro Dashboard signal, rank or gate behind it, so
BC-2's stored-artifact requirement has nothing to attach to and an allowlist entry would
assert evidence we do not have. Such text is therefore exempt BY PROVENANCE, not by
allowlisting: a token on a ``site/research/`` page is skipped only when it sits inside a
long enough run of text reproduced VERBATIM from the committed vault snapshots
(data/research_vault/{excerpts,catalog}.json), the same snapshots the render itself
reads. The run is grown from the token outward and stops where our own words start, so
the exemption ends at the quotation mark rather than at the page boundary: house prose
on the very same page — the paywall pitch, the footer, a teaser we composed, any copy we
wrote — is still fully scanned, and no page can opt itself out by wrapping a claim in
the right markup.

The gate is phrase-scoped, not file:line-scoped, so it survives page regeneration (the
per-basket/per-stock pages repeat one template phrase; one allowlist entry covers them all).
Rendered site HTML is autoescaped ('&' -> '&amp;', quotes -> '&#39;'/'&#34;'), so token,
negation, and allowlist matching all run on the html.unescape()d text of each line; the
raw line is kept for error reporting.
Its real power: a NEW affirmative 'validated' claim that matches no allowlisted justification
FAILS the build — which is exactly the discipline BC-2 buys.

Run:  python -m scripts.check_validated_claims          # scan; exit 1 on any unearned claim
      python -m scripts.check_validated_claims --list    # list every affirmative claim + status
      python -m scripts.check_validated_claims --selftest # prove the gate fires on a synthetic EN+zh
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ALLOWLIST = ROOT / "data" / "regime" / "validated_claims_allowlist.json"

# The republication surface: scripts/build_research_pages.py renders one page per
# catalog item here (plus the crawl hub). Everything on those pages is either the
# scanned template's own copy or third-party data from the two snapshots below.
VAULT_SURFACE = "site/research"
VAULT_EXCERPTS = ROOT / "data" / "research_vault" / "excerpts.json"
VAULT_CATALOG = ROOT / "data" / "research_vault" / "catalog.json"

# The scanned surfaces (D2 §4.3): templates (source), hand-written + generated site JS,
# generated *_data.js, and the rendered site HTML. EN + zh both.
SCAN_GLOBS = [
    ("templates", ("*.j2", "*.js")),
    ("site", ("*.js", "*.html")),
    # Prophet plan JSONs are rendered user-facing (terminal oracle-tab); scan them too.
    ("site/prophet/plans", ("*.json",)),
]

TOKEN = re.compile(r"validated|已验证", re.IGNORECASE)

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


# ---------------------------------------------------------------------------
# republished third-party text (research vault) — exempt BY PROVENANCE
# ---------------------------------------------------------------------------

# The render cleans markdown emphasis out of the teaser (build_research_pages._clean)
# and collapses whitespace, so normalize both sides the same way before comparing.
_MD = re.compile(r"[*_`]+")
# How far around a token to look for quoted text. Generous: the run is bounded by what
# actually matches, not by this.
_QUOTE_CONTEXT = 160
# How long the verbatim run around the token must be to read as a quotation. This is the
# whole safety margin: to launder a house claim you would have to find this many
# consecutive characters of a third-party note that ALREADY make your claim, around a
# 'validated' the note itself wrote — at which point you are quoting them, not claiming.
# A shorter run (a bare 'Validated' chip, a label) is left to the normal gate.
_MIN_QUOTE_CHARS = 40


def _flat(s: str) -> str:
    """Normalize rendered text or a snapshot string to one comparable form."""
    return re.sub(r"\s+", " ", html.unescape(str(s or ""))).strip().lower()


def _external_corpus() -> str:
    """Everything the vault republishes from a third-party document that CONTAINS the
    token, normalized and newline-joined. Filtering to token-bearing strings up front
    keeps this a handful of entries instead of the whole 600 KB snapshot, and costs
    nothing: a quoted run always carries the token, so it can only ever match an entry
    that carries it too. The newline join stops a run from matching across two
    unrelated documents.

    Sources are the committed snapshots the render itself reads:
      * excerpts.json — verbatim first-pages paragraphs, derived from the PDF text
        layer by engine.research_vault.excerpt.derive (no LLM in that path);
      * catalog.json  — the report title and the provider's summary bullets, taken
        from the sidecar shipped with the PDF (engine.research_vault.sidecar, which
        never fabricates a bullet).
    Each string is kept BOTH as-is and markdown-stripped, because the render strips
    emphasis out of the teaser (build_research_pages._clean) and the run matcher below
    compares against the rendered form character for character.
    Fail-soft: a missing or malformed snapshot yields an EMPTY corpus, so the gate
    stays strict rather than silently opening up.
    """
    out: list[str] = []
    try:
        raw = json.loads(VAULT_EXCERPTS.read_text(encoding="utf-8"))
        blob = raw.get("excerpts") if isinstance(raw, dict) else None
        for paras in (blob or {}).values():
            if isinstance(paras, list):
                out.extend(p for p in paras if isinstance(p, str))
    except Exception:  # noqa: BLE001 — repo data; never let it break the gate
        pass
    try:
        raw = json.loads(VAULT_CATALOG.read_text(encoding="utf-8"))
        for it in (raw.get("items") if isinstance(raw, dict) else raw) or []:
            if not isinstance(it, dict):
                continue
            out.append(str(it.get("title") or ""))
            out.extend(str(p) for p in (it.get("summary_points") or []) if p)
    except Exception:  # noqa: BLE001
        pass
    keep = set()
    for s in out:
        flat = _flat(s)
        for form in (flat, _MD.sub("", flat)):
            if form and TOKEN.search(form):
                keep.add(form)
    return "\n".join(sorted(keep))


def _bounds(norm: str, start: int, end: int) -> tuple[int, int]:
    """How far the search may reach, clipped at markup.

    A republished sentence is contiguous text inside ONE element or attribute value —
    '<p>{{ p }}</p>', '<h1>{{ n.title }}</h1>', 'content="… {{ n.teaser }}"' — so the
    reach stops at the nearest '>' before and '<' after: a run may never span two
    elements, which is what keeps a quote in one paragraph from covering house copy in
    the next.
    """
    lo, hi = max(0, start - _QUOTE_CONTEXT), min(len(norm), end + _QUOTE_CONTEXT)
    gt = norm.rfind(">", lo, start)
    if gt >= 0:
        lo = gt + 1
    lt = norm.find("<", end, hi)
    if lt >= 0:
        hi = lt
    return lo, hi


def _quoted_run(norm: str, start: int, end: int, corpus: str) -> int:
    """Length of the verbatim run around THIS token occurrence, 0 if it is not quoted.

    Grows the token outward for as long as the growing string still appears in the
    republication corpus, so the run ends exactly where our own words begin: the house
    prefix on a meta description ("J.P. Morgan research. …"), the ' | Mastermind' suffix
    in <title>, the '…' the teaser truncation appends, or a claim someone grafted onto
    the end of a quote. Both grow orders are tried because greedy growth in one
    direction can block the other.

    Case folding is applied per SLICE, never to the whole line: lowering a line can
    change its length (a handful of Unicode letters fold to two characters) and would
    silently shift every offset the token scan handed us.
    """
    lo, hi = _bounds(norm, start, end)

    def _quotes(a: int, b: int) -> bool:
        return norm[a:b].lower() in corpus

    if not _quotes(start, end):
        return 0                                        # not even the token itself

    def _grow(right_first: bool) -> int:
        a, b = start, end
        for grow_right in ((True, False) if right_first else (False, True)):
            if grow_right:
                while b < hi and _quotes(a, b + 1):
                    b += 1
            else:
                while a > lo and _quotes(a - 1, b):
                    a -= 1
        return b - a

    return max(_grow(True), _grow(False))


def _is_quoted(norm: str, start: int, end: int, corpus: str) -> bool:
    """Is this token occurrence republished verbatim from a third-party document?"""
    if not corpus:
        return False
    return _quoted_run(norm, start, end, corpus) >= _MIN_QUOTE_CHARS


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


def _scan_line(line: str, allow: list[dict],
               ext: str = "") -> tuple[int, int, list[tuple[bool, dict | None]]]:
    """Evaluate one raw line. Returns (n_negated, n_quoted, hits) — one (backed,
    allow_entry) per affirmative token occurrence. Token/negation/allowlist matching runs
    on the html.unescape()d text: rendered site HTML is autoescaped, so an allowlist entry
    containing '&' can never match its '&amp;' rendered form, and an entity-bearing
    negation prefix ("isn&#39;t a validated") reads as an affirmative claim. Callers
    keep the raw line for reporting.

    `ext` is the republished-third-party corpus, passed ONLY for files on the research
    vault's republication surface; empty everywhere else, so the exemption cannot reach
    a page the estate authored."""
    if any(sp.search(line) for sp in _STRUCTURAL):
        return 0, 0, []                                 # structural non-claim line
    norm = html.unescape(line)
    n_negated = n_quoted = 0
    hits: list[tuple[bool, dict | None]] = []
    for m in TOKEN.finditer(norm):
        if _is_quoted(norm, m.start(), m.end(), ext):
            n_quoted += 1                               # someone else's sentence
            continue
        if _is_negated(norm, m.start()):
            n_negated += 1
            continue
        entry = _allow_match(norm, allow)
        backed = entry is not None or _artifact_backed(norm)
        hits.append((backed, entry))
    return n_negated, n_quoted, hits


def scan(list_all: bool = False) -> list[dict]:
    """Return the list of UNEARNED affirmative 'validated' claims. Prints per-claim status
    when list_all. Each unearned finding is {file, line_no, text}."""
    allow = _load_allowlist()
    external = _external_corpus()
    unearned: list[dict] = []
    n_claims = n_negated = n_backed = n_quoted = 0
    for sub, pats in SCAN_GLOBS:
        base = ROOT / sub
        if not base.exists():
            continue
        for pat in pats:
            for f in sorted(base.rglob(pat)):
                if "node_modules" in str(f):
                    continue
                try:
                    lines = f.read_text(encoding="utf-8").splitlines()
                except Exception:  # noqa: BLE001
                    continue
                rel = f.relative_to(ROOT).as_posix()
                ext = external if rel.startswith(VAULT_SURFACE + "/") else ""
                for i, line in enumerate(lines, 1):
                    n_neg, n_q, hits = _scan_line(line, allow, ext)
                    n_negated += n_neg
                    n_quoted += n_q
                    for backed, entry in hits:
                        n_claims += 1
                        if backed:
                            n_backed += 1
                            if list_all:
                                why = ("allow:" + entry["match"]) if entry else "artifact validated:true"
                                print(f"  OK   {f.relative_to(ROOT)}:{i}  [{why}]")
                        else:
                            rec = {"file": str(f.relative_to(ROOT)), "line_no": i,
                                   "text": line.strip()[:160]}
                            unearned.append(rec)
                            if list_all:
                                print(f"  MISS {f.relative_to(ROOT)}:{i}  {line.strip()[:120]}")
    if list_all:
        print(f"\naffirmative claims: {n_claims}  backed: {n_backed}  "
              f"negated/hedged (ignored): {n_negated}  "
              f"republished third-party (ignored): {n_quoted}  UNEARNED: {len(unearned)}")
    return unearned


def selftest() -> int:
    """Prove the gate FIRES on a synthetic unearned 'validated' in EN and in zh, does NOT
    fire on negated uses, matches through HTML autoescaping ('&' vs '&amp;'), and that the
    republished-third-party exemption never covers a house-authored claim.
    Synthetic lines only — never touches the tree."""
    allow = _load_allowlist()
    # Synthetic allowlist for the autoescape cases: an '&'-bearing match string must cover
    # its '&amp;' rendered form. Deliberately NOT in the real allowlist — it exercises
    # _scan_line's html.unescape normalization, nothing on the tree cites it.
    amp_allow = [{"match": "validated & wired for selftest"}]
    # Synthetic republication corpus: two foreign strings, normalized exactly as
    # _external_corpus() would pull them out of the vault snapshots. Nothing cites them.
    _q = ("The slowdown was fairly broad-based and validated two likely sources of "
          "ongoing disinflation, chiefly shelter.")
    _q_amp = ("Oil rebounded 35% & validated the near-term disinflation channel that "
              "the June print had already flagged.")
    quote = "\n".join(sorted({_flat(_q), _flat(_q_amp)}))
    cases = [
        # name, line, should_fire, allowlist, republished-third-party corpus
        ("EN affirmative unearned",
         "This signal is validated as a real cross-sectional alpha.", True, allow, ""),
        ("zh affirmative unearned", "该信号是已验证的方向性优势。", True, allow, ""),
        ("EN negated (disclaimer)", "The rank has no validated forward edge here.", False, allow, ""),
        ("zh negated (disclaimer)", "此处无已验证方向信号。", False, allow, ""),
        ("EN allowlisted",
         "gated by the validated MACD-2D × StochRSI-3D confluence.", False, allow, ""),
        ("allowlisted '&' entry matches rendered '&amp;'",
         "<h2>Scored — validated &amp; wired for selftest</h2>", False, amp_allow, ""),
        ("unearned claim behind '&amp;' still fires",
         "This edge is validated &amp; deployed everywhere.", True, amp_allow, ""),
        ("negation behind entity apostrophe ignored",
         "This isn&#39;t a validated edge.", False, allow, ""),
        ("EN negated perfect-tense contraction",
         "the PRIOR hasn't been validated, so trade the tape, not the narrative.", False, allow, ""),
        ("perfect-tense contraction behind entity apostrophe",
         "the PRIOR hasn&#39;t been validated, so trade the tape.", False, allow, ""),
        ("EN negated 'cannot be validated'",
         "This construction cannot be validated on the available window.", False, allow, ""),
        # --- republished third-party text (research vault) -------------------------
        # The exemption must cover the quoted sentence and NOTHING else: not the same
        # words off the republication surface, not house prose beside the quote, not a
        # house claim grafted onto the quote, not a bare label.
        ("verbatim third-party paragraph exempt", f"<p>{_q}</p>", False, allow, quote),
        ("quoted note inside a meta attribute exempt",
         f'<meta name="description" content="J.P. Morgan research. {_q}">', False, allow, quote),
        ("truncated teaser prefix stays exempt",
         f"<p class=\"rr-teaser\">{_q[:70].rstrip()}…</p>", False, allow, quote),
        ("quoted '&amp;' unescapes into the corpus",
         f"<p>{_q_amp.replace('&', '&amp;')}</p>", False, allow, quote),
        ("SAME sentence off the vault surface still fires", f"<p>{_q}</p>", True, allow, ""),
        ("HOUSE prose beside the quote still fires",
         f"<p>{_q}</p><p class=\"rr-teaser\">Our own shelter rank is validated on the "
         f"forward record.</p>", True, allow, quote),
        ("HOUSE claim grafted onto the quote still fires",
         f"<p>{_q[:-1]}, and our own shelter rank is validated by it.</p>", True, allow, quote),
        ("bare label never attributes to the corpus", "<span>Validated</span>", True, allow, quote),
    ]
    ok = True
    for name, line, should_fire, allow_entries, ext in cases:
        _, _, hits = _scan_line(line, allow_entries, ext)
        fired = any(not backed for backed, _ in hits)
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
              f"data/regime/validated_claims_allowlist.json (a hit inside a quoted "
              f"third-party note on {VAULT_SURFACE}/ means the span no longer matches the "
              f"vault snapshot — fix the provenance, do NOT allowlist it):", file=sys.stderr)
        for r in unearned[:40]:
            print(f"  {r['file']}:{r['line_no']}  {r['text']}", file=sys.stderr)
        if len(unearned) > 40:
            print(f"  ... and {len(unearned) - 40} more", file=sys.stderr)
        sys.exit(1)
    print("check_validated_claims: OK — every affirmative 'validated' claim is backed.")


if __name__ == "__main__":
    main()
