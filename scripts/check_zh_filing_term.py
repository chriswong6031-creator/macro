"""i18n.zh_filing_term — 申报 must never reach user-facing Chinese copy.

WHY THIS EXISTS. To a native Chinese reader 申报 is what you do at customs or with
the tax authority (海关申报, 申报纳税): a self-declaration you file about yourself,
under legal compulsion, to the state. It is the wrong word for what this platform
shows. An SEC 10-K, a 13F, a congressional STOCK Act trade report is a 披露 — a
DISCLOSURE, published to the market. Using 申报 makes the filings desk read like a
tax portal, which is exactly the impression a markets product must not give.

The term has been swept by hand twice already — PR #4830 (Filing Forensics) and
PR #4855 (SEC / 13F / congress copy, site-wide). It recurs 20-50x site-wide because
every builder that writes a zh label about a filing reaches for the same wrong word,
so a third hand-sweep was only ever a matter of time. Hence a gate.

WHAT IS SCANNED (deliberately narrow — user-facing copy, at its SOURCE):
  • templates/ — every text asset (.j2 / .html / .js / .css / .json / .txt / .svg),
    line by line. This is where the copy is authored.
  • engine/ and scripts/ — Python STRING LITERALS only, via AST. Builders emit zh
    labels from source; gating only the rendered page catches the defect a nightly
    render late and on somebody else's PR (the #3765 → #3790 latency that
    check_validated_claims was widened to close).

WHAT IS NOT SCANNED, and why:
  • site/ — render OUTPUT. A hit there is a hit in templates/ or a builder, already
    covered; scanning it would red main on a stale render nobody can fix by hand.
  • data/ — collected upstream text. Exchange announcements genuinely use 申报 as
    an order-entry term; the platform does not author it.
  • Python COMMENTS and DOCSTRINGS — developer documentation, never rendered. This
    is a structural skip, not an allowlist: without it, the sentence "translate
    filings as 披露, never 申报" reds the build wherever it is written down, which
    would make explaining the law the cheapest way to break it.

THE ALLOWLIST IS PHRASE-SCOPED AND FILE-SCOPED, never file-scoped alone. 申报 has
legitimate other senses in this repo (申报失业金 = filing for unemployment benefits;
买入申报 = a HK/SSE order-entry term), so each exemption names the EXACT phrase and
the EXACT file it is licensed on. An occurrence is exempt only when it falls inside
a licensed phrase's span, in a licensed file — a bare 申报 elsewhere on the same
line still fails, and the same phrase in a different file still fails.

`pending` is the temporary half: a file whose 申报 is already being removed by an
open PR. Each entry freezes today's count as a RATCHET — more than the budget is a
hard failure (someone added a new one), fewer prints a ::notice asking for the entry
to be dropped. A pending entry never hard-fails on its own removal, because a gate
that reds main the moment somebody else's PR lands is a scheduled outage.

Run:  python3 scripts/check_zh_filing_term.py            # scan; exit 1 on any hit
      python3 scripts/check_zh_filing_term.py --list     # every occurrence + status
      python3 scripts/check_zh_filing_term.py --selftest # prove the gate fires
"""
from __future__ import annotations

import argparse
import ast
import json
import sys
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ALLOWLIST = ROOT / "config" / "zh_filing_term_allowlist.json"

# The banned term. Kept as a module constant so the test suite and --selftest build
# their fixtures from the same string the scan looks for (a fixture that spells the
# token itself can drift out of agreement with the guard and pass for free).
TERM = "申报"
# The word the copy should use instead — named in every annotation so the fix is in
# the failure message, not in a doc somebody has to go find.
FIX = "披露"

# templates/ text assets. Suffix-keyed rather than "every file" so the fonts/ and
# other binary subtrees are never decoded.
TEXT_DIRS = ("templates",)
TEXT_SUFFIXES = (".j2", ".html", ".htm", ".js", ".css", ".json", ".txt", ".svg", ".md")

# Python sources whose STRING LITERALS are scanned (scan_python).
PY_DIRS = ("engine", "scripts")

# This file. Its docstring, its constants, and its selftest fixtures all spell the
# banned term on purpose; scanning itself would make the guard unwritable.
SELF_REL = "scripts/check_zh_filing_term.py"


# ── Allowlist ─────────────────────────────────────────────────────────────────

def _load_allowlist(path: Path | None = None) -> tuple[list[dict], dict[str, dict]]:
    """Return (allow entries, pending-by-file map). Fails CLOSED on a broken file.

    A malformed or missing allowlist raises rather than degrading to "nothing is
    exempt" or "everything is exempt": either silent mode is a guard whose behaviour
    nobody can predict from the repo contents.
    """
    p = path or ALLOWLIST
    raw = json.loads(p.read_text(encoding="utf-8"))
    allow = raw.get("allow") or []
    pending = raw.get("pending") or []

    for i, e in enumerate(allow):
        for field in ("phrase", "files", "why"):
            if not e.get(field):
                raise ValueError(f"{p.name}: allow[{i}] is missing '{field}'")
        if TERM not in e["phrase"]:
            raise ValueError(
                f"{p.name}: allow[{i}] phrase {e['phrase']!r} does not contain {TERM} "
                "— an exemption that cannot cover an occurrence is dead weight"
            )
    by_file: dict[str, dict] = {}
    for i, e in enumerate(pending):
        for field in ("file", "pr", "max_occurrences", "why"):
            if e.get(field) in (None, "", []):
                raise ValueError(f"{p.name}: pending[{i}] is missing '{field}'")
        by_file[e["file"]] = e
    return allow, by_file


def _exempt_spans(unit: str, rel_path: str, allow: list[dict]) -> list[tuple[int, int]]:
    """Half-open [start, end) spans of `unit` covered by a licensed phrase."""
    spans: list[tuple[int, int]] = []
    for entry in allow:
        if rel_path not in entry["files"]:
            continue
        phrase = entry["phrase"]
        start = unit.find(phrase)
        while start != -1:
            spans.append((start, start + len(phrase)))
            start = unit.find(phrase, start + 1)
    return spans


def _unlicensed(unit: str, rel_path: str, allow: list[dict]) -> int:
    """Count occurrences of TERM in `unit` that no licensed phrase covers.

    Per-OCCURRENCE, not per-line: a line that carries an allowlisted phrase AND a
    bare 申报 still reports the bare one. Keying the exemption on the line would let
    one licensed phrase launder every other use beside it.
    """
    spans = _exempt_spans(unit, rel_path, allow)
    n = 0
    at = unit.find(TERM)
    while at != -1:
        if not any(s <= at and at + len(TERM) <= e for s, e in spans):
            n += 1
        at = unit.find(TERM, at + 1)
    return n


# ── Scanners (pure — the test suite pins the same code path CI runs) ───────────

def scan_text(rel_path: str, text: str, allow: list[dict]) -> list[dict]:
    """Scan one text asset line by line. Returns [{file, line_no, count, text}]."""
    out: list[dict] = []
    for i, line in enumerate(text.splitlines(), 1):
        if TERM not in line:
            continue
        n = _unlicensed(line, rel_path, allow)
        if n:
            out.append({"file": rel_path, "line_no": i, "count": n,
                        "text": line.strip()[:160]})
    return out


def _docstring_ids(tree: ast.AST) -> set[int]:
    """id()s of the Constant nodes that are docstrings — skipped, see module doc."""
    ids: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.ClassDef,
                                 ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        body = getattr(node, "body", None)
        if not body:
            continue
        first = body[0]
        if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) \
           and isinstance(first.value.value, str):
            ids.add(id(first.value))
    return ids


def scan_python(rel_path: str, text: str, allow: list[dict]) -> list[dict]:
    """Scan one Python source's string literals (f-string literal parts included).

    Fails CLOSED on an unparseable file: a syntax error is reported as a finding
    rather than skipped, so the gate can never be bypassed by a file it cannot read.
    """
    try:
        tree = ast.parse(text)
    except SyntaxError as e:
        return [{"file": rel_path, "line_no": e.lineno or 1, "count": 1,
                 "text": f"UNPARSEABLE ({e.msg}) — cannot prove it carries no {TERM}"}]

    skip = _docstring_ids(tree)
    out: list[dict] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        if id(node) in skip or TERM not in node.value:
            continue
        n = _unlicensed(node.value, rel_path, allow)
        if n:
            out.append({"file": rel_path, "line_no": node.lineno, "count": n,
                        "text": node.value.strip().replace("\n", " ")[:160]})
    return out


@lru_cache(maxsize=1)
def _targets() -> tuple[tuple[str, Path, object], ...]:
    """(rel_path, path, scanner) for every scannable file. Paths only — the bodies are
    read lazily, so --list does not hold ~2,700 file contents in memory at once."""
    out: list[tuple[str, Path, object]] = []
    for sub in TEXT_DIRS:
        base = ROOT / sub
        if not base.exists():
            continue
        for f in sorted(base.rglob("*")):
            if not f.is_file() or f.suffix not in TEXT_SUFFIXES:
                continue
            # Prune on the path RELATIVE to the scan root, never the absolute one:
            # an absolute-parts test also matches every directory ABOVE the root, so
            # a checkout that happens to live under a matching ancestor silently
            # scans nothing at all (#3802).
            if "node_modules" in f.relative_to(ROOT).parts:
                continue
            out.append((f.relative_to(ROOT).as_posix(), f, scan_text))
    for sub in PY_DIRS:
        base = ROOT / sub
        if not base.exists():
            continue
        for f in sorted(base.rglob("*.py")):
            rel_path = f.relative_to(ROOT)
            rel = rel_path.as_posix()
            if rel == SELF_REL or "node_modules" in rel_path.parts:
                continue
            out.append((rel, f, scan_python))
    return tuple(out)


def _read(f: Path) -> str | None:
    try:
        return f.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def scan(list_all: bool = False) -> tuple[list[dict], list[str]]:
    """Return (hard findings, ::notice messages).

    Findings inside a `pending` file are withheld while its count stays at or under
    the frozen budget — that file is already being fixed by the named open PR.
    """
    allow, pending = _load_allowlist()
    raw: list[dict] = []
    carriers: list[tuple[str, str, object]] = []   # only the files that carry TERM
    for rel, path, scanner in _targets():
        text = _read(path)
        if text is None or TERM not in text:
            continue
        carriers.append((rel, text, scanner))
        raw.extend(scanner(rel, text, allow))

    per_file: dict[str, int] = {}
    for r in raw:
        per_file[r["file"]] = per_file.get(r["file"], 0) + r["count"]

    findings = [r for r in raw if r["file"] not in pending]
    notices: list[str] = []
    for rel, entry in sorted(pending.items()):
        found = per_file.get(rel, 0)
        budget = int(entry["max_occurrences"])
        if found > budget:
            notices.append(
                f"::error title=zh-filing-term-pending::{rel} carries {found} "
                f"occurrence(s) of {TERM}, above its frozen budget of {budget} "
                f"(pending PR #{entry['pr']}) — a NEW one was added; use {FIX}"
            )
            findings.extend(r for r in raw if r["file"] == rel)
        elif found < budget:
            gone = "all of them" if found == 0 else f"{budget - found} of {budget}"
            notices.append(
                f"::notice title=zh-filing-term-pending::{rel} has lost {gone} "
                f"— PR #{entry['pr']} has landed (fully or in part). Tighten "
                f"max_occurrences, or drop the entry from {ALLOWLIST.name}"
            )

    if list_all:
        for rel, text, scanner in carriers:
            hits = scanner(rel, text, allow)
            total = text.count(TERM)
            flagged = sum(h["count"] for h in hits)
            state = "PENDING" if rel in pending else ("MISS" if flagged else "OK")
            print(f"  {state:8} {rel}  {flagged} flagged / {total} present")
            for h in hits:
                print(f"           :{h['line_no']}  {h['text'][:110]}")
        print(f"\nfiles scanned: {len(_targets())}  files carrying {TERM}: "
              f"{len(carriers)}  licensed phrases: {len(allow)}  "
              f"pending files: {len(pending)}  "
              f"UNLICENSED: {sum(f['count'] for f in findings)}")
    return findings, notices


# ── Selftest ──────────────────────────────────────────────────────────────────

_ZH_COPY = f"这不代表每项{TERM}都没有变化；请查看{TERM}轨迹。"
_GOOD_COPY = f"这不代表每项{FIX}都没有变化；请查看{FIX}轨迹。"
_CLAIMS = f"假日周：{TERM}失业金数据接近元旦、7月4日、感恩节或圣诞节"
_ORDER = f"买入{TERM}"


def selftest() -> int:
    """Prove the gate fires, and prove the allowlist is narrow. Exit 0 when all pass."""
    allow, pending = _load_allowlist()
    ok = True

    cases: list[tuple[str, bool, object, str, str]] = [
        # ── it FIRES on the defect the two hand-sweeps had to fix ──────────────
        (f"zh template copy carrying {TERM} FIRES", True, scan_text,
         "templates/fundamental_forensics.js", f"      pair('Filing trail', '{TERM}轨迹'),\n"),
        (f"jinja t() copy carrying {TERM} FIRES", True, scan_text,
         "templates/_selftest.html.j2", f"<p>{{{{ t('Filing trail', '{TERM}轨迹') }}}}</p>\n"),
        (f"data-zh attribute carrying {TERM} FIRES", True, scan_text,
         "templates/index.html", f'<span class="kicker" data-zh="盯紧{TERM}">Follow the filings</span>\n'),
        (f"builder zh label carrying {TERM} FIRES", True, scan_python,
         "engine/_selftest.py", f'ROW = {{"label_zh": "SEC {TERM}文件"}}\n'),
        (f"f-string literal part carrying {TERM} FIRES", True, scan_python,
         "engine/_selftest.py", f'note = f"{TERM}于 {{d}}"\n'),
        ("unparseable python FAILS CLOSED", True, scan_python,
         "engine/_selftest.py", "def broken(:\n"),

        # ── it stays QUIET on correct copy ─────────────────────────────────────
        (f"the same copy written with {FIX} is clean", False, scan_text,
         "templates/fundamental_forensics.js", _GOOD_COPY + "\n"),
        (f"a python COMMENT mentioning {TERM} is not copy", False, scan_python,
         "engine/_selftest.py", f"# never write {TERM}; the disclosure sense is {FIX}\n"),
        (f"a DOCSTRING mentioning {TERM} is not copy", False, scan_python,
         "engine/_selftest.py", f'"""Sweep {TERM} to {FIX} in zh labels."""\n'),

        # ── the allowlist is NARROW: phrase AND file, per occurrence ───────────
        ("申报失业金 on release_quirks is licensed", False, scan_python,
         "engine/release_quirks.py", f'Q = {{"zh": "{_CLAIMS}"}}\n'),
        ("申报失业金 on ANOTHER file FIRES", True, scan_python,
         "engine/_selftest.py", f'Q = {{"zh": "{_CLAIMS}"}}\n'),
        ("买入申报 on the hk-connect roster is licensed", False, scan_python,
         "scripts/collect_hk_connect_roster.py", f'EXCLUDE = ("额度", "{_ORDER}")\n'),
        ("买入申报 on ANOTHER file FIRES", True, scan_python,
         "scripts/_selftest.py", f'EXCLUDE = ("额度", "{_ORDER}")\n'),
        ("a licensed phrase does NOT launder a bare 申报 beside it", True, scan_python,
         "engine/release_quirks.py", f'Q = {{"zh": "{_CLAIMS}；另见{TERM}轨迹"}}\n'),
        ("a licensed phrase does NOT launder a bare 申报 on a template line", True,
         scan_text, "templates/_selftest.html.j2", f"<p>{_CLAIMS} · {TERM}轨迹</p>\n"),
    ]
    for name, should_fire, scanner, rel, src in cases:
        fired = bool(scanner(rel, src, allow))
        status = "PASS" if fired == should_fire else "FAIL"
        if fired != should_fire:
            ok = False
        print(f"  [{status}] {name}: fired={fired} expected={should_fire}")

    # The two licensed phrases must actually match the live repo sites they name —
    # an exemption whose phrase has drifted out of the file is a silent hole.
    for entry in allow:
        for rel in entry["files"]:
            p = ROOT / rel
            present = p.exists() and entry["phrase"] in (_read(p) or "")
            status = "PASS" if present else "FAIL"
            if not present:
                ok = False
            print(f"  [{status}] licensed phrase {entry['phrase']!r} is present in {rel}")

    # Every pending file must still exist and must still be over zero, or the entry
    # is stale — reported here as a visible FAIL of the selftest's own hygiene pass
    # only when the file is gone (a merged fix is a ::notice from scan(), not a red).
    for rel in sorted(pending):
        present = (ROOT / rel).exists()
        status = "PASS" if present else "FAIL"
        if not present:
            ok = False
        print(f"  [{status}] pending file {rel} still exists")

    return 0 if ok else 1


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(description=f"Ban {TERM} from user-facing Chinese copy.")
    ap.add_argument("--list", action="store_true",
                    help=f"print every file carrying {TERM} and its status")
    ap.add_argument("--selftest", action="store_true",
                    help="prove the gate fires on a synthetic insertion")
    args = ap.parse_args()

    if args.selftest:
        sys.exit(selftest())

    findings, notices = scan(list_all=args.list)

    # GitHub workflow commands MUST start their line, so these are bare prints with
    # flush=True — never a logger, whose prefixing format ("WARNING %(message)s")
    # makes GitHub silently drop the annotation. See CLAUDE.md and
    # tests/test_gh_annotation_line_start.py.
    for note in notices:
        print(note, flush=True)

    if findings:
        total = sum(f["count"] for f in findings)
        print(f"::error title=zh-filing-term::{total} occurrence(s) of {TERM} in "
              f"user-facing Chinese copy across {len({f['file'] for f in findings})} "
              f"file(s) — {TERM} reads as a TAX or CUSTOMS declaration. A filing this "
              f"platform shows is a {FIX} (disclosure). Fix the copy, or license the "
              f"exact phrase in {ALLOWLIST.relative_to(ROOT).as_posix()}", flush=True)
        for r in findings[:40]:
            snippet = r["text"].replace("\r", " ").replace("\n", " ")
            print(f"::error file={r['file']},line={r['line_no']},"
                  f"title=zh-filing-term::use {FIX} instead of {TERM}: {snippet}",
                  flush=True)
        if len(findings) > 40:
            print(f"  ... and {len(findings) - 40} more", file=sys.stderr)
        sys.exit(1)

    print(f"check_zh_filing_term: OK — no unlicensed {TERM} in user-facing zh copy.")


if __name__ == "__main__":
    main()
