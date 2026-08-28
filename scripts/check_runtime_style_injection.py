#!/usr/bin/env python3
"""TP-0 Task 2 — ratchet runtime stylesheet-injection debt in user-facing JS.

WHY THIS EXISTS. `scripts/check_design_system.py` scans `templates/` only,
deliberately (its closure contract names exactly one path literal and makes
no subprocess call — see that module's docstring). A page composer under
`site/` can therefore obey the design system in templates while building a
parallel, ungoverned presentation layer entirely inside runtime JS strings
(`el.style.textContent = "..."`, `document.createElement('style')`,
`<style>...</style>` markup baked into a template literal, or a raw
`sheet.insertRule(...)`). That is the enforcement escape hatch this guard
closes. It is a SEPARATE script, on purpose: widening check_design_system.py
to cover `site/` too would break its one-root/no-subprocess closure law.

WHAT IT DOES. Scans every `.js` file under `templates/` and `site/` for four
injection signatures (PATTERNS below) and compares the counts against a
frozen baseline (`config/runtime_style_injection_allowlist.json`). TP-0 does
not remove any existing injection — it only FREEZES the current debt so it
cannot silently grow:

  * a file that injects but is ABSENT from the baseline is a hard fail (a
    brand-new opaque runtime stylesheet);
  * a file whose actual count EXCEEDS its pinned per-pattern allowance is a
    hard fail (more debt added to an already-known offender);
  * a file whose actual count is LOWER than its pinned allowance emits a
    GitHub `::notice` requiring the SAME PR to shrink the stale allowance —
    the ratchet only ever tightens, it never quietly keeps slack around for a
    future re-injection.

`theme.js` (both `templates/` and `site/`) is the canonical theme owner the
architecture explicitly permits and is, by a wide margin, the single biggest
entry in the baseline — that is expected and is not debt TP-0 is asking
anyone to remove. Vendored minified libraries (e.g. `plotly-2.32.0.min.js`)
are IN SCOPE and frozen like anything else: no vendor exemption class is
carved out, because an exemption class is exactly the bypass shape this guard
exists to close. A future vendor upgrade that changes its injection count is
expected to require a visible baseline update — that is the intended ratchet
behavior, not a false positive.

Usage:
    python3 scripts/check_runtime_style_injection.py
        # scan the committed tree against the committed baseline; exit 1 on
        # any new/absent/over-budget file, exit 0 otherwise (stale-budget
        # notices do not fail the build by themselves)
    python3 scripts/check_runtime_style_injection.py --emit-baseline \\
        --generated-from "$(git rev-parse HEAD)" > config/runtime_style_injection_allowlist.json
        # regenerate the baseline from the CURRENT tree. --generated-from is
        # REQUIRED and is never guessed or substituted by this script — the
        # caller supplies the real commit sha (read-only `git rev-parse`).
    python3 scripts/check_runtime_style_injection.py --selftest
        # exercise the gate against planted fixtures; exit 0 on success

Exit codes: 0 = clean (or --emit-baseline / --selftest succeeded) · 1 =
new/absent/over-budget injection found, or the baseline file could not be
read · 2 = --emit-baseline invoked without --generated-from.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASELINE_PATH_REL = "config/runtime_style_injection_allowlist.json"
BASELINE_SCHEMA = "mastermind.runtime_style_allowlist.v1"
SCAN_ROOTS = ("templates", "site")

# The four injection signatures. Kept in one place, exactly as frozen by the
# TP-0 spec — do not add a fifth without a corresponding baseline regen and a
# documented reason (a new pattern makes every currently-unlisted file that
# happens to match it read as a brand-new offender).
PATTERNS: dict[str, re.Pattern[str]] = {
    "create_style": re.compile(r"createElement\(\s*['\"]style['\"]\s*\)"),
    "style_text": re.compile(r"(?:style|css)\.textContent\s*="),
    "insert_rule": re.compile(r"\.sheet\.insertRule\s*\("),
    "style_markup": re.compile(r"<style(?:\s|>)", re.IGNORECASE),
}


def iter_js_files(root: Path):
    """Every `.js` file under `templates/` and `site/`, sorted, deduplicated per root."""
    for sub in SCAN_ROOTS:
        d = root / sub
        if not d.is_dir():
            continue
        yield from sorted(p for p in d.rglob("*.js") if p.is_file())


def file_counts(text: str) -> dict[str, int]:
    """Per-pattern hit counts for one file's text, with zero-count patterns omitted."""
    counts = {name: len(pat.findall(text)) for name, pat in PATTERNS.items()}
    return {name: n for name, n in counts.items() if n}


def discover_counts(root: Path) -> dict[str, dict[str, int]]:
    """relpath (posix, e.g. "site/theme.js") -> nonzero pattern counts, for every
    injecting `.js` file under `templates/` and `site/`. Clean files (no injection
    signature at all) are simply absent from the result."""
    out: dict[str, dict[str, int]] = {}
    for path in iter_js_files(root):
        text = path.read_text(encoding="utf-8", errors="replace")
        counts = file_counts(text)
        if counts:
            out[path.relative_to(root).as_posix()] = counts
    return out


def evaluate(
    discovered: dict[str, dict[str, int]],
    baseline_files: dict[str, dict[str, int]],
) -> tuple[list[str], list[tuple[str, str, int, int]]]:
    """Compare `discovered` (current tree) against `baseline_files` (frozen debt).

    Returns (violations, stale):
      * `violations` — human-readable strings; any non-empty list means the
        caller must exit 1. Two shapes: a file that injects but has no
        baseline entry at all, and a per-(file, pattern) actual > allowance.
        A pattern absent from a file's baseline entry has an IMPLICIT
        allowance of 0, so a brand-new pattern type on an already-known file
        is caught the same way a brand-new file is.
      * `stale` — (relpath, pattern, actual, allowed) tuples where actual <
        allowed. Never blocks by itself; the caller turns each into a
        `::notice` requiring the same PR to shrink the allowance. A file
        whose baseline entry survives but whose actual count for a pattern
        dropped to 0 (or that stopped injecting altogether) is stale for
        every pattern that used to be nonzero, precisely because the ratchet
        must never leave quiet headroom for a future re-injection.
    """
    violations: list[str] = []
    stale: list[tuple[str, str, int, int]] = []
    for relpath in sorted(set(discovered) | set(baseline_files)):
        counts = discovered.get(relpath, {})
        entry = baseline_files.get(relpath, {})
        if relpath not in baseline_files:
            # counts is guaranteed non-empty here (relpath came from `discovered`
            # if it is not in `baseline_files`, since baseline-only paths are
            # already covered by the `relpath in baseline_files` branch below).
            violations.append(
                f"{relpath}: NEW injecting file not present in the frozen baseline "
                f"(counts={counts}) — this is exactly the ungoverned runtime "
                f"stylesheet TP-0 exists to block. Either remove the injection, or "
                f"if it is a deliberate, reviewed exception, regenerate the baseline "
                f"with --emit-baseline --generated-from <sha> in this PR."
            )
            continue
        for name in sorted(set(PATTERNS) & (set(counts) | set(entry))):
            actual = counts.get(name, 0)
            allowed = entry.get(name, 0)
            if actual > allowed:
                violations.append(
                    f"{relpath}: {name} actual={actual} exceeds pinned allowance={allowed} "
                    f"in {BASELINE_PATH_REL}"
                )
            elif actual < allowed:
                stale.append((relpath, name, actual, allowed))
    return violations, stale


def _baseline_path(root: Path) -> Path:
    return root / BASELINE_PATH_REL


def _load_baseline(root: Path) -> dict | None:
    """Load the committed baseline, or print an informative error and return None.

    A missing/malformed baseline is a CHECKOUT/INFRASTRUCTURE fault, not "zero
    debt is frozen" — printing that distinction plainly matters here for the
    same reason it matters for check_validated_claims's allowlist: silently
    treating an absent file as an empty baseline would make every one of the
    46 already-known injecting files read as a brand-new offender.
    """
    path = _baseline_path(root)
    if not path.exists():
        try:
            shown = path.relative_to(root)
        except ValueError:
            shown = path
        print(
            f"::error title=runtime-style-injection-baseline-missing::{shown} is absent — "
            f"this checkout cannot answer what runtime-style-injection debt is frozen. "
            f"Regenerate with --emit-baseline --generated-from <sha>, or restore the "
            f"committed file. This is a CHECKOUT fault, not evidence that 46 known "
            f"injecting files are suddenly new.",
            flush=True,
        )
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(
            f"::error title=runtime-style-injection-baseline-malformed::"
            f"{BASELINE_PATH_REL} is not valid JSON ({e}).",
            flush=True,
        )
        return None
    if not isinstance(data, dict) or "files" not in data:
        print(
            f"::error title=runtime-style-injection-baseline-malformed::"
            f"{BASELINE_PATH_REL} is missing the required 'files' key.",
            flush=True,
        )
        return None
    return data


def _sparse_refusal(root: Path) -> str | None:
    """The remedy line when this checkout cannot see the trees this guard covers.

    A sparse session worktree (policy R8) can omit `site/`; without this check
    the walk in `iter_js_files` would silently see only `templates/` and report
    a vacuous "OK" on a checkout that was never asked to answer for `site/` at
    all — the same false-green shape `check_template_site_sync.py` guards
    against for the same reason.
    """
    try:
        from scripts.worktree_sparse import missing_dirs, remedy_line
    except Exception:  # noqa: BLE001 — never let the detector break the guard
        return None
    try:
        absent = [d for d in missing_dirs(root) if d in SCAN_ROOTS]
    except Exception:  # noqa: BLE001
        return None
    return remedy_line(absent) if absent else None


def _emit_baseline(root: Path, generated_from: str) -> dict:
    return {
        "schema": BASELINE_SCHEMA,
        "generated_from": generated_from,
        "files": discover_counts(root),
    }


def selftest() -> int:
    """Exercise the gate end-to-end against planted fixtures (never the real tree)."""
    import shutil
    import tempfile

    tmp = Path(tempfile.mkdtemp(prefix="check_runtime_style_injection_selftest_"))
    try:
        (tmp / "templates").mkdir()
        (tmp / "site").mkdir()

        # Clean file: no injection signature anywhere.
        (tmp / "templates" / "clean.js").write_text("const x = 1;\nfunction f(){return x;}\n")

        # Known, budgeted offender: 2 create_style hits, baseline allows exactly 2.
        (tmp / "site" / "theme.js").write_text(
            "document.createElement('style');\ndocument.createElement('style');\n"
        )

        # A file the baseline knows about but that regressed: allowance 1, actual 2.
        (tmp / "site" / "over_budget.js").write_text(
            "document.createElement('style');\ndocument.createElement('style');\n"
        )

        # A file the baseline over-allows: allowance 2, actual 1 -> stale notice.
        (tmp / "templates" / "shrinking.js").write_text("document.createElement('style');\n")

        baseline_files = {
            "site/theme.js": {"create_style": 2},
            "site/over_budget.js": {"create_style": 1},
            "templates/shrinking.js": {"create_style": 2},
        }
        discovered = discover_counts(tmp)

        # 1. Clean tree control: no offenders at all -> no violations, no staleness.
        clean_v, clean_s = evaluate({}, {})
        if clean_v or clean_s:
            print(f"selftest FAIL: empty discovery against empty baseline should be silent, "
                  f"got violations={clean_v} stale={clean_s}")
            return 1

        # 2. Real fixture tree.
        violations, stale = evaluate(discovered, baseline_files)

        if not any("over_budget.js" in v and "actual=2" in v and "allowance=1" in v
                   for v in violations):
            print(f"selftest FAIL: expected an over-budget violation for over_budget.js, "
                  f"got {violations}")
            return 1
        if any("theme.js" in v for v in violations):
            print(f"selftest FAIL: theme.js is exactly at its allowance and must not violate, "
                  f"got {violations}")
            return 1
        if ("templates/shrinking.js", "create_style", 1, 2) not in stale:
            print(f"selftest FAIL: expected a stale-budget entry for shrinking.js, got {stale}")
            return 1

        # 3. A brand-new injecting file absent from the baseline must red.
        (tmp / "site" / "new_offender.js").write_text("document.createElement('style');\n")
        discovered2 = discover_counts(tmp)
        violations2, _ = evaluate(discovered2, baseline_files)
        if not any("new_offender.js" in v and "baseline" in v.lower() for v in violations2):
            print(f"selftest FAIL: expected new_offender.js to red as absent from baseline, "
                  f"got {violations2}")
            return 1

        # 4. --emit-baseline never guesses a sha.
        emitted = _emit_baseline(tmp, "deadbeefcafe")
        if emitted["generated_from"] != "deadbeefcafe" or emitted["schema"] != BASELINE_SCHEMA:
            print(f"selftest FAIL: --emit-baseline shape wrong: {emitted}")
            return 1
        if emitted["files"].get("site/theme.js") != {"create_style": 2}:
            print(f"selftest FAIL: emitted baseline counts wrong: {emitted['files']}")
            return 1

        print(
            "selftest PASS: new-injecting-file reds, over-budget reds, exact-budget passes, "
            "under-budget emits a stale-budget notice, and --emit-baseline reproduces the "
            "current tree's counts under the caller-supplied sha."
        )
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _build_arg_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description="Ratchet guard: runtime stylesheet-injection debt in user-facing JS "
                    "under templates/ and site/ can only stay flat or shrink."
    )
    ap.add_argument("--emit-baseline", action="store_true",
                     help="print the baseline JSON for the CURRENT tree to stdout")
    ap.add_argument("--generated-from", default=None,
                     help="git commit sha for the emitted baseline's 'generated_from' field "
                          "(required with --emit-baseline; never guessed or substituted — "
                          "pass $(git rev-parse HEAD) yourself)")
    ap.add_argument("--selftest", action="store_true",
                     help="exercise the gate against planted fixtures and exit")
    return ap


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)

    if args.selftest:
        return selftest()

    root = ROOT

    if args.emit_baseline:
        if not args.generated_from:
            print(
                "::error title=runtime-style-injection-emit-baseline::--emit-baseline requires "
                "--generated-from SHA (e.g. --generated-from \"$(git rev-parse HEAD)\") — this "
                "script never guesses or substitutes a commit sha itself.",
                flush=True,
            )
            return 2
        baseline = _emit_baseline(root, args.generated_from)
        print(json.dumps(baseline, indent=2, sort_keys=True))
        return 0

    refusal = _sparse_refusal(root)
    if refusal:
        print(f"runtime style injection guard REFUSED: {refusal}")
        return 1

    baseline = _load_baseline(root)
    if baseline is None:
        return 1

    discovered = discover_counts(root)
    violations, stale = evaluate(discovered, baseline.get("files", {}))

    for relpath, name, actual, allowed in stale:
        print(
            f"::notice title=runtime-style-injection-stale-budget::{relpath}: {name} allowance "
            f"is {allowed} but actual is {actual} — shrink (or remove) this pinned allowance in "
            f"{BASELINE_PATH_REL} in the SAME PR. TP-0 only freezes existing runtime-style "
            f"injection debt; it must not accumulate quiet headroom for a future re-injection.",
            flush=True,
        )

    if violations:
        print(
            f"::error title=runtime-style-injection::{len(violations)} runtime stylesheet "
            f"injection violation(s) against {BASELINE_PATH_REL}:",
            flush=True,
        )
        for v in violations:
            print(f"  {v}")
        return 1

    n_scanned = sum(1 for _ in iter_js_files(root))
    n_injecting = len(discovered)
    n_hits = sum(sum(c.values()) for c in discovered.values())
    print(
        f"runtime style injection guard OK ({n_scanned} .js files scanned, "
        f"{n_injecting} injecting, {n_hits} total hits — all within frozen allowances)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
