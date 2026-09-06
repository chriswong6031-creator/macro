#!/usr/bin/env python3
"""Acquisition-truth bake: the landing page's derived claims must equal the
committed canonical artifacts they are derived from.

The anonymous landing page (templates/index.html + site/index.html — a
byte-identical plain-copy pair, see scripts/check_template_site_sync.py and the
ui.template_site_sync law) carries two DERIVED regions:

  * the one-line ``<script type="application/json" id="ph-data">`` island —
    the Prophet "delayed winners" teaser slice. Canonical source:
    site/prophet/showcase.json (the nightly emit of scripts/build_prophet.py).
    showcase.json's as_of is SNAPSHOT IDENTITY, never site freshness — the
    artifact is deliberately DELAYED (scripts/freshness_sentinel.py) — so the
    island must be that artifact VERBATIM: never hand-refreshed, never
    hand-frozen.
  * the dossier-coverage claim in the pricing feature table ("N published
    dossiers …"). Canonical source: site/stocks/index.html — the "Every one
    of the <b>N</b>" strapline of the estate we actually publish (meta
    description as fallback).

2026-09-03 drift this exists to end: the island shipped the board of
2026-07-06 with 11 cards while showcase.json said 2026-08-14 with 12, and the
coverage line said "2,700+" against 1,955 published dossiers — un-derived
numbers on the one page a stranger cannot audit.

Enforcement points (mirrors check_template_site_sync.py):
  * pr_ci / template-site-sync CI pack: ``--check`` reds a PR whose landing
    claims drifted from the artifacts (tests/test_landing_acquisition_truth.py
    is the same law as pytest).
  * render lanes: ``--fix`` runs immediately BEFORE each
    ``check_template_site_sync --fix`` heal, so a nightly that refreshes
    showcase.json re-derives the island in the same commit, in BOTH pair
    copies, byte-identically — the sync law is preserved at every commit.

Usage:
    python -m scripts.bake_landing_preview             # --check is the default
    python -m scripts.bake_landing_preview --check     # report + exit 1 on drift
    python -m scripts.bake_landing_preview --fix       # rewrite BOTH pair copies
    python -m scripts.bake_landing_preview --selftest  # gate fires on synthetic drift
Exit codes: 0 = true / fixed / selftest passed · 1 = drift found, or a canonical
artifact is absent/malformed (MISSING_CANONICAL_ARTIFACT). ``--fix`` REFUSES to
invent values when the truth is unavailable — an absent artifact is
UNAVAILABLE, never a guess.

Idempotent: ``--fix`` twice = no diff, and ``--check`` is green immediately
after ``--fix``.
"""
from __future__ import annotations

import json
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

PAIR = ("templates/index.html", "site/index.html")
SHOWCASE_REL = "site/prophet/showcase.json"
STOCKS_INDEX_REL = "site/stocks/index.html"
MISSING = "MISSING_CANONICAL_ARTIFACT"

ISLAND_RE = re.compile(
    r'(<script type="application/json" id="ph-data">)(.*?)(</script>)', re.S)
STOCKS_TOTAL_RE = re.compile(r"Every one of the <b>([\d,]+)</b>")
STOCKS_TOTAL_FALLBACK_RE = re.compile(r"dossiers for ([\d,]+) US stocks")
DOSSIER_TIP_RE = re.compile(
    r'(<span class="ft" data-zh="个股档案">Stock dossiers</span>'
    r'<span class="tipbox" data-zh=")([^"]*)(">)([^<]*)(</span>)')
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def canonical_island_json(showcase: dict) -> str:
    """THE one serialization of the island: json.dumps of the artifact object
    itself — key order as committed, compact separators, unescaped UTF-8 (the
    island's surrounding idiom; sec_zh stays readable in view-source). Byte
    equality against this string is what makes --check exact and --fix
    idempotent."""
    text = json.dumps(showcase, ensure_ascii=False, separators=(",", ":"))
    if re.search(r"</script", text, re.I):
        raise ValueError(
            "serialized showcase would close the island's <script> element")
    return text


def expected_tip_copy(total: int) -> tuple[str, str]:
    """(en, zh) dossier-coverage claim: derived count + named denominator."""
    en = f"{total:,} published dossiers with trend, stage and ownership context."
    zh = f"{total:,} 份已发布个股档案，含趋势、所处阶段和股东情况。"
    return en, zh


def load_showcase(root: Path) -> tuple[dict | None, str | None]:
    """(payload, error). Absent or malformed truth is UNAVAILABLE, never a
    guess — the caller must refuse to bake, not improvise a payload."""
    p = root / SHOWCASE_REL
    if not p.is_file():
        return None, f"{MISSING}: {SHOWCASE_REL} is absent — nothing to derive the island from"
    try:
        obj = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        return None, f"{MISSING}: {SHOWCASE_REL} is unreadable as JSON ({e})"
    if not isinstance(obj, dict) or obj.get("schema") != "prophet.showcase/v2":
        return None, f"{MISSING}: {SHOWCASE_REL} schema is not prophet.showcase/v2"
    if not isinstance(obj.get("as_of"), str) or not _DATE_RE.match(obj["as_of"]):
        return None, f"{MISSING}: {SHOWCASE_REL} as_of is not an ISO date"
    cards = obj.get("cards")
    if not isinstance(cards, list) or not cards:
        return None, f"{MISSING}: {SHOWCASE_REL} carries no cards"
    if obj.get("count") != len(cards):
        return None, (f"{MISSING}: {SHOWCASE_REL} count={obj.get('count')!r} != "
                      f"len(cards)={len(cards)}")
    return obj, None


def load_stocks_total(root: Path) -> tuple[int | None, str | None]:
    """(published-dossier total, error) from the stocks index we ship."""
    p = root / STOCKS_INDEX_REL
    if not p.is_file():
        return None, (f"{MISSING}: {STOCKS_INDEX_REL} is absent — nothing to "
                      "derive the dossier count from")
    try:
        text = p.read_text(encoding="utf-8")
    except OSError as e:
        return None, f"{MISSING}: {STOCKS_INDEX_REL} is unreadable ({e})"
    m = STOCKS_TOTAL_RE.search(text) or STOCKS_TOTAL_FALLBACK_RE.search(text)
    if not m:
        return None, (f"{MISSING}: {STOCKS_INDEX_REL} carries neither the "
                      "'Every one of the <b>N</b>' strapline nor the "
                      "meta-description total")
    total = int(m.group(1).replace(",", ""))
    if total <= 0:
        return None, f"{MISSING}: {STOCKS_INDEX_REL} total parsed as {total}"
    return total, None


def _island_asof(raw: str) -> str:
    try:
        return str(json.loads(raw).get("as_of", "?"))
    except ValueError:
        return "unparseable"


def check(root: Path, fix: bool = False) -> list[str]:
    """Return drift/problem messages (empty = the page tells the truth).

    In fix mode the healable drifts are rewritten in BOTH pair copies with the
    SAME derived bytes, so the template↔site sync law holds at every commit.
    Copies that could not be healed (missing anchor, unavailable artifact) are
    recorded in ``check.unfixed`` so main() can report honestly and exit
    nonzero rather than reporting a refusal as a heal.
    """
    problems: list[str] = []
    check.unfixed = []
    showcase, err1 = load_showcase(root)
    total, err2 = load_stocks_total(root)
    for err in (err1, err2):
        if err:
            problems.append(err)
            print(err)
    if err1 or err2:
        if fix:
            check.unfixed = list(PAIR)
            print("REFUSED: --fix will not invent derived values while a "
                  "canonical artifact is unavailable")
        return problems
    try:
        island = canonical_island_json(showcase)
    except ValueError as e:
        msg = f"{MISSING}: {e}"
        problems.append(msg)
        print(msg)
        if fix:
            check.unfixed = list(PAIR)
        return problems
    tip_en, tip_zh = expected_tip_copy(total)

    for rel in PAIR:
        p = root / rel
        if not p.is_file():
            msg = f"{rel}: absent — the landing pair is incomplete"
            problems.append(msg)
            print(msg)
            check.unfixed.append(rel)
            continue
        text = p.read_text(encoding="utf-8")
        diverged = unfixable = False

        m = ISLAND_RE.search(text)
        if not m:
            unfixable = True
            msg = f"{rel}: #ph-data island anchor missing — cannot derive or heal"
            problems.append(msg)
            print(msg)
        elif m.group(2) != island:
            diverged = True
            msg = (f"DIVERGED: {rel} #ph-data island (as_of "
                   f"{_island_asof(m.group(2))}) != {SHOWCASE_REL} "
                   f"(as_of {showcase['as_of']})")
            problems.append(msg)
            print(msg)
            text = text[:m.start(2)] + island + text[m.end(2):]

        t = DOSSIER_TIP_RE.search(text)
        if not t:
            unfixable = True
            msg = f"{rel}: dossier-coverage tipbox anchor missing — cannot derive or heal"
            problems.append(msg)
            print(msg)
        elif t.group(2) != tip_zh or t.group(4) != tip_en:
            diverged = True
            msg = (f"DIVERGED: {rel} dossier-coverage claim != "
                   f"{STOCKS_INDEX_REL} total {total:,}")
            problems.append(msg)
            print(msg)
            text = DOSSIER_TIP_RE.sub(
                lambda mm: mm.group(1) + tip_zh + mm.group(3) + tip_en + mm.group(5),
                text, count=1)

        if unfixable:
            check.unfixed.append(rel)
        if fix and diverged:
            p.write_bytes(text.encode("utf-8"))
            print(f"FIXED: {rel} rebaked from {SHOWCASE_REL} + {STOCKS_INDEX_REL}")
    return problems


def selftest() -> int:
    import shutil

    tmp = Path(tempfile.mkdtemp(prefix="bake_landing_preview_selftest_"))
    try:
        (tmp / "templates").mkdir()
        (tmp / "site" / "prophet").mkdir(parents=True)
        (tmp / "site" / "stocks").mkdir()
        showcase = {
            "schema": "prophet.showcase/v2", "kind": "delayed_winners",
            "as_of": "2026-08-14", "window_sessions": 10,
            "authority_tier": "display", "count": 1, "note": "selftest",
            "cards": [{"tk": "NEW", "sec_zh": "原材料",
                       "spark": "<svg class=\"nch\"></svg>"}],
        }
        (tmp / SHOWCASE_REL).write_text(
            json.dumps(showcase, indent=2), encoding="utf-8")
        (tmp / STOCKS_INDEX_REL).write_text(
            "<p>Every one of the <b>1,955</b> US names we publish a dossier "
            "for, ranked.</p>", encoding="utf-8")
        stale = ('{"schema":"prophet.showcase/v2","as_of":"2026-07-06",'
                 '"count":1,"cards":[{"tk":"OLD"}]}')
        page = ('<html><script type="application/json" id="ph-data">' + stale
                + '</script><span class="ft" data-zh="个股档案">Stock dossiers'
                + '</span><span class="tipbox" data-zh="2,700+ 只股票。">'
                + '2,700+ names.</span></html>')
        for rel in PAIR:
            (tmp / rel).write_text(page, encoding="utf-8")

        # 1. drift detected: island + coverage claim, in BOTH copies
        bad = check(tmp)
        if len(bad) != 4 or not all("DIVERGED" in msg for msg in bad):
            print(f"selftest FAIL: expected 4 DIVERGED messages, got {bad}")
            return 1

        # 2. --fix heals both copies byte-identically; --check green after
        check(tmp, fix=True)
        a = (tmp / PAIR[0]).read_bytes()
        b = (tmp / PAIR[1]).read_bytes()
        if a != b:
            print("selftest FAIL: --fix left the pair copies diverged")
            return 1
        healed = a.decode("utf-8")
        if canonical_island_json(showcase) not in healed:
            print("selftest FAIL: --fix did not bake the canonical island")
            return 1
        if "1,955 published dossiers" not in healed or "已发布个股档案" not in healed:
            print("selftest FAIL: --fix did not derive the coverage claim")
            return 1
        if check(tmp) != []:
            print("selftest FAIL: --check still red after --fix")
            return 1

        # 3. idempotent: a second --fix changes nothing
        check(tmp, fix=True)
        if (tmp / PAIR[0]).read_bytes() != a:
            print("selftest FAIL: --fix is not idempotent")
            return 1

        # 4. UNAVAILABLE artifact: --check names it, --fix refuses to invent
        (tmp / SHOWCASE_REL).unlink()
        bad = check(tmp)
        if not any(MISSING in msg for msg in bad):
            print(f"selftest FAIL: missing artifact not reported, got {bad}")
            return 1
        check(tmp, fix=True)
        if (tmp / PAIR[0]).read_bytes() != a or check.unfixed != list(PAIR):
            print("selftest FAIL: --fix must refuse when the artifact is absent")
            return 1

        print("selftest PASS: drift detected, --fix derives both copies "
              "byte-identically + idempotently, and refuses absent artifacts")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _sparse_refusal(root: Path) -> str | None:
    """Refuse a sparse checkout that cannot see the trees this law covers
    (same shape as check_template_site_sync._sparse_refusal — a walk over an
    absent site/ would be a vacuous pass on the exact drift this guards)."""
    try:
        from scripts.worktree_sparse import missing_dirs, remedy_line
    except Exception:  # noqa: BLE001 — never let the detector break the guard
        return None
    try:
        absent = [d for d in missing_dirs(root) if d in {"site", "templates"}]
    except Exception:  # noqa: BLE001
        return None
    return remedy_line(absent) if absent else None


def main(argv: list[str]) -> int:
    if "--selftest" in argv:
        return selftest()
    fix = "--fix" in argv
    root = Path(__file__).resolve().parent.parent
    refusal = _sparse_refusal(root)
    if refusal:
        print(f"landing acquisition-truth bake REFUSED: {refusal}")
        return 1
    problems = check(root, fix=fix)
    if not problems:
        print("landing acquisition truth OK (#ph-data island + dossier count "
              f"match the canonical artifacts; {len(PAIR)} copies checked)")
        return 0
    unfixed = getattr(check, "unfixed", [])
    if fix:
        if not unfixed:
            print(f"landing acquisition truth: derived regions rebaked in "
                  f"{len(PAIR)} copies from {SHOWCASE_REL} + {STOCKS_INDEX_REL}")
            return 0
        print(f"landing acquisition truth: NOT healed — {len(unfixed)} "
              f"cop{'y' if len(unfixed) == 1 else 'ies'} refused: {unfixed}")
        return 1
    print(f"landing acquisition truth FAILED: {len(problems)} problem(s) — "
          "run: python -m scripts.bake_landing_preview --fix")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
