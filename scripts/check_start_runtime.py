#!/usr/bin/env python3
"""Lane guard: site/start.html must load each page runtime exactly once.

2026-08-01 incident, second act: after the autostash-conflict clobber
(d29e4dd44d) was fixed by #4163 (emitter + bytes + tests), an engine-render
whose checkout predated the merge re-rendered start.html with the OLD builder
and pushed it post-rebase (adad513bdfe) — live_config.js and live.js twice,
wh_banner.js gone, no conflict markers anywhere. git.no_conflict_markers passed
by design and the duplicate-runtime page shipped straight to main, where only
the next PR's pytest run (tests/test_start_publish_integrity.py) could see it.
Browsers executing the doubled tags start two live-price patch loops on the
same DOM. This guard gives the start-writing lanes the fail-closed gate the
pytest suite can only apply to PRs.

Check: every runtime in RUNTIMES appears as a <script src> basename exactly
once (query strings and path prefixes ignored, same parse as the pytest).

Heal (--heal-from REF): a violating page is restored wholesale from REF and
rechecked — the committed copy is at most one render old and PR-gated, so an
older-but-single-instance page beats a freshly rendered double. Exit 0 after a
clean heal (the lane keeps the rest of its render), 1 if still violating.

Usage:
    python3 scripts/check_start_runtime.py [--file PATH] [--heal-from REF]
    python3 scripts/check_start_runtime.py --self-test
Exit codes: 0 = clean / healed clean / self-test passed · 1 = violation · 2 = usage.
"""
from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PAGE = ROOT / "site" / "start.html"

# Keep in sync with tests/test_start_publish_integrity.py (the PR-side gate);
# test_lane_guard_checks_the_same_runtimes pins the two lists to each other.
RUNTIMES = (
    "globe-deck.js",
    "sky.js",
    "hub-welcome.js",
    "live_config.js",
    "live.js",
    "wh_banner.js",
)

_SCRIPT_SRC = re.compile(r'<script\b[^>]*\bsrc=["\']([^"\']+)["\']')


def script_basenames(html: str) -> list[str]:
    return [
        src.split("?", 1)[0].rsplit("/", 1)[-1]
        for src in _SCRIPT_SRC.findall(html)
    ]


def check_text(html: str) -> list[str]:
    """Return one violation line per runtime not loaded exactly once."""
    names = script_basenames(html)
    return [
        f"{asset} loaded {names.count(asset)} time(s), expected exactly 1"
        for asset in RUNTIMES
        if names.count(asset) != 1
    ]


def check_page(path: Path) -> list[str]:
    if not path.exists():
        # start.html is committed; a lane that lost it has bigger damage —
        # never green a missing page.
        return [f"{path}: missing"]
    try:
        html = path.read_text(encoding="utf-8")
    except Exception as e:  # noqa: BLE001 — unreadable page = loud violation
        return [f"{path}: unreadable ({e})"]
    return check_text(html)


def heal_from(ref: str, path: Path) -> bool:
    """Restore `path` wholesale from `ref`; True if git succeeded."""
    res = subprocess.run(
        ["git", "checkout", ref, "--", path.name],
        cwd=path.parent,
        capture_output=True,
        text=True,
    )
    if res.returncode != 0:
        print(f"  heal failed: git checkout {ref} -- {path}: {res.stderr.strip()}")
    return res.returncode == 0


def _self_test() -> int:
    """Fixture check: known-bad shapes must be flagged, known-good must not."""
    one_each = "".join(f'<script defer src="{a}?v=abc123"></script>' for a in RUNTIMES)
    nav_prefixed = "".join(f'<script src="../{a}"></script>' for a in RUNTIMES)
    # The exact adad513bdfe shape: doubled live pair, missing banner rail.
    stale_builder = one_each.replace(
        '<script defer src="wh_banner.js?v=abc123"></script>',
        '<script src="live_config.js"></script><script src="live.js"></script>',
    )
    cases = {
        "clean page (stamped)": (f"<html><body>{one_each}</body></html>", 0),
        "clean page (prefixed src)": (f"<html><body>{nav_prefixed}</body></html>", 0),
        "stale-builder shape (2x live pair, 0x banner)": (
            f"<html><body>{stale_builder}</body></html>", 3),
        "one runtime doubled": (
            f"<html><body>{one_each}<script defer src=\"sky.js\"></script></body></html>", 1),
        "inline scripts only (all runtimes absent)": (
            "<html><body><script>1</script></body></html>", len(RUNTIMES)),
    }
    failed = False
    with tempfile.TemporaryDirectory(prefix="check_start_runtime_selftest_") as tmp:
        fixture = Path(tmp) / "fixture_page.html"
        for label, (html, want) in cases.items():
            fixture.write_text(html, encoding="utf-8")
            got = check_page(fixture)
            ok = len(got) == want
            print(f"  {'PASS' if ok else 'FAIL'} {label}: {len(got)} violation(s), expected {want}")
            failed |= not ok
        missing = Path(tmp) / "never_written_page.html"
        got = check_page(missing)
        ok = len(got) == 1
        print(f"  {'PASS' if ok else 'FAIL'} missing page: {len(got)} violation(s), expected 1")
        failed |= not ok
    if failed:
        print("check_start_runtime: SELF-TEST FAIL", file=sys.stderr)
        return 1
    print("check_start_runtime: self-test OK — bad shapes flagged, good shapes clean.")
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv == ["--self-test"]:
        return _self_test()

    heal_ref: str | None = None
    if "--heal-from" in argv:
        i = argv.index("--heal-from")
        try:
            heal_ref = argv[i + 1]
        except IndexError:
            print("--heal-from requires a git ref", file=sys.stderr)
            return 2
        argv = argv[:i] + argv[i + 2:]

    page = DEFAULT_PAGE
    if "--file" in argv:
        i = argv.index("--file")
        try:
            page = Path(argv[i + 1])
        except IndexError:
            print("--file requires a path", file=sys.stderr)
            return 2
        argv = argv[:i] + argv[i + 2:]
    if argv:
        print(f"unknown argument(s): {argv}", file=sys.stderr)
        return 2

    violations = check_page(page)
    if not violations:
        print(f"check_start_runtime: OK — every runtime single-instance in {page}.")
        return 0

    print(f"::error title=start-runtime-duplicate::{page}: " + "; ".join(violations), flush=True)
    for v in violations:
        print(f"  {v}")

    if heal_ref is None:
        return 1

    print(f"healing {page} from {heal_ref} (single-instance-but-older beats a doubled runtime):")
    if heal_from(heal_ref, page) and not check_page(page):
        print(
            f"::warning title=start-runtime-healed::{page} restored from {heal_ref}; "
            "this run's rendered copy was discarded (stale or broken start emitter?)",
            flush=True,
        )
        print(f"  healed: {page}")
        return 0
    print(f"  STILL VIOLATING after restore from {heal_ref}: {page}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
