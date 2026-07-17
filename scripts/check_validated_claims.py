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


def scan(list_all: bool = False) -> list[dict]:
    """Return the list of UNEARNED affirmative 'validated' claims. Prints per-claim status
    when list_all. Each unearned finding is {file, line_no, text}."""
    allow = _load_allowlist()
    unearned: list[dict] = []
    n_claims = n_negated = n_backed = 0
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
                for i, line in enumerate(lines, 1):
                    n_neg, hits = _scan_line(line, allow)
                    n_negated += n_neg
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
              f"negated/hedged (ignored): {n_negated}  UNEARNED: {len(unearned)}")
    return unearned


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
    ]
    ok = True
    for name, line, should_fire, allow_entries in cases:
        _, hits = _scan_line(line, allow_entries)
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
              f"data/regime/validated_claims_allowlist.json:", file=sys.stderr)
        for r in unearned[:40]:
            print(f"  {r['file']}:{r['line_no']}  {r['text']}", file=sys.stderr)
        if len(unearned) > 40:
            print(f"  ... and {len(unearned) - 40} more", file=sys.stderr)
        sys.exit(1)
    print("check_validated_claims: OK — every affirmative 'validated' claim is backed.")


if __name__ == "__main__":
    main()
