"""scripts/check_fms_bundle.py — FMS publication-bundle guards.

Extracted from ``.github/workflows/government-revenue-live.yml``'s "commit
complete evidence projection" step (CI repair, post-§11b red-team packet):
that step's inline shell function definitions for the FMS
congressional-notification rail pushed the whole ``run:`` block past
GitHub's 21,000-character hard limit on a single workflow expression
(measured 22,878 chars; ``tests/test_public_render_fastlane.py::
test_no_workflow_run_expression_can_hit_githubs_21000_character_limit``).
This script is a byte-for-byte behavioral mirror of the three removed shell
functions, invoked from the SAME step via one-liner CLI calls instead of
inline bash.

Phases (each maps to exactly one removed shell function):
  bundle        assert_fms_bundle — all-or-nothing tracked+present bundle;
                a wholly absent bundle is a lawful "not initialized yet"
                (rc 0), a PARTIAL bundle (some but not all paths present or
                tracked) refuses (rc 1), and a bundle that was tracked but
                has now disappeared from the checkout refuses (rc 1).
  clean         assert_fms_source_clean — the SAM fast path may not publish
                a locally changed or staged FMS source bundle.
  twins         assert_optional_fms_case_graph_twins — the FMS case graph
                is lawful only absent-on-both-sides or byte-identical on
                both the canonical and public path.
  stage         the two-line `if [ -f fms_case_graph.json ]; then git add
                -- ...; fi` conditional this workflow ran inline at both
                staging points — `git add`s the canonical+public twin ONLY
                when the canonical file exists, a no-op otherwise. Also
                extracted purely for run: block length (this step's own
                `set -euo pipefail` still aborts the step if this fails).
  precheck      bundle then clean, short-circuiting on the first refusal
                (see `precheck_fms_bundle_and_clean`) — the two are always
                called back-to-back at both workflow call sites, so this
                combines them into one CLI invocation purely to save run:
                block characters; each remains independently callable.

Every refusal prints a GitHub Actions annotation via a bare
``print(..., flush=True)`` — NEVER through a logger (CI-guarded house law:
tests/test_gh_annotation_line_start.py; stdout is block-buffered when piped
in CI so the flush is load-bearing).

Each phase also accepts its first letter (b/c/t/s/p) as a terse alias — the
workflow's own call sites use the letters to stay inside the run: block's
character budget; a human running this directly may use either form.

Usage:
    python3 scripts/check_fms_bundle.py bundle
    python3 scripts/check_fms_bundle.py clean
    python3 scripts/check_fms_bundle.py twins
    python3 scripts/check_fms_bundle.py stage
    python3 scripts/check_fms_bundle.py b      # same as: bundle
    python3 scripts/check_fms_bundle.py <name> --root PATH

Exit codes:
    0   the named phase is satisfied (including the lawful "not yet
        initialized" absence for `bundle`)
    1   the named phase refuses to publish
"""
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

FMS_BUNDLE_PATHS: tuple[str, ...] = (
    "data/government_revenue/fms_collection_receipts.jsonl",
    "data/government_revenue/fms_observations.jsonl",
    "data/government_revenue/fms_projection_state.json",
    "data/government_revenue/fms_case_graph.json",
)

FMS_CASE_GRAPH_CANONICAL = "data/government_revenue/fms_case_graph.json"
FMS_CASE_GRAPH_PUBLIC = "site/government-revenue-data/fms-cases.json"


def _is_tracked(root: Path, relative_path: str) -> bool:
    result = subprocess.run(
        ["git", "ls-files", "--error-unmatch", "--", relative_path],
        cwd=root, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    return result.returncode == 0


def _git_diff_clean(root: Path, *, cached: bool, paths: tuple[str, ...]) -> bool:
    args = ["git", "diff"]
    if cached:
        args.append("--cached")
    args += ["--quiet", "--", *paths]
    result = subprocess.run(args, cwd=root)
    return result.returncode == 0


def assert_fms_bundle(root: Path) -> int:
    present = sum(1 for p in FMS_BUNDLE_PATHS if (root / p).is_file())
    tracked = sum(1 for p in FMS_BUNDLE_PATHS if _is_tracked(root, p))
    if present == 0:
        if tracked != 0:
            print(
                "::error title=fms bundle missing::tracked FMS congressional-notification "
                "artifacts disappeared from the checkout; refusing a partial rail",
                flush=True,
            )
            return 1
        print(
            "FMS congressional-notification bundle not initialized yet; "
            "keeping the optional rail unavailable",
            flush=True,
        )
        return 0
    if present != len(FMS_BUNDLE_PATHS) or tracked != len(FMS_BUNDLE_PATHS):
        print(
            "::error title=fms bundle incomplete::FMS receipts, observations, projection "
            "state, and case graph must arrive as one committed bundle",
            flush=True,
        )
        return 1
    return 0


def assert_fms_source_clean(root: Path) -> int:
    if not _git_diff_clean(root, cached=False, paths=FMS_BUNDLE_PATHS):
        print(
            "::error title=fms source mutation::the SAM fast path cannot publish a "
            "locally changed FMS source bundle",
            flush=True,
        )
        return 1
    if not _git_diff_clean(root, cached=True, paths=FMS_BUNDLE_PATHS):
        print(
            "::error title=fms source staged::the SAM fast path cannot stage a FMS "
            "source mutation",
            flush=True,
        )
        return 1
    return 0


def assert_optional_fms_case_graph_twins(root: Path) -> int:
    canonical = root / FMS_CASE_GRAPH_CANONICAL
    public = root / FMS_CASE_GRAPH_PUBLIC
    if not canonical.exists() and not public.exists():
        return 0
    if not canonical.is_file() or not public.is_file():
        print(
            "::error title=fms case graph twin incomplete::the FMS case graph must be "
            "absent or present as exact canonical/public twins",
            flush=True,
        )
        return 1
    if canonical.read_bytes() != public.read_bytes():
        print(
            "::error title=fms case graph twin mismatch::canonical and public FMS case "
            "graph bytes differ",
            flush=True,
        )
        return 1
    return 0


def stage_optional_fms_case_graph_twins(root: Path) -> int:
    canonical = root / FMS_CASE_GRAPH_CANONICAL
    if not canonical.is_file():
        return 0
    result = subprocess.run(
        ["git", "add", "--", FMS_CASE_GRAPH_CANONICAL, FMS_CASE_GRAPH_PUBLIC], cwd=root,
    )
    return result.returncode


def precheck_fms_bundle_and_clean(root: Path) -> int:
    """bundle then clean, short-circuiting on the first refusal.

    Byte-equivalent to the original two bare sequential shell calls
    (``assert_fms_bundle; assert_fms_source_clean``) under this workflow
    step's own ``set -euo pipefail`` -- a non-zero return there aborts the
    step immediately, so ``clean`` never ran once ``bundle`` had already
    refused. Combined into one CLI call purely to save run: block chars at
    the two call sites (both always called back-to-back, never
    independently); each still has its own standalone phase for direct use.
    """
    rc = assert_fms_bundle(root)
    if rc != 0:
        return rc
    return assert_fms_source_clean(root)


_PHASES = {
    "bundle": assert_fms_bundle,
    "clean": assert_fms_source_clean,
    "twins": assert_optional_fms_case_graph_twins,
    "stage": stage_optional_fms_case_graph_twins,
    "precheck": precheck_fms_bundle_and_clean,
}

# First-letter aliases (b/c/t/s/p never collide) so the workflow's own call
# sites can stay terse without sacrificing the script's own readability.
_PHASE_ALIASES = {name[0]: name for name in _PHASES}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", help="bundle|clean|twins|stage, or first letter")
    parser.add_argument(
        "--root", default=".",
        help="repo root the FMS bundle paths are relative to (default: cwd)",
    )
    args = parser.parse_args(argv)
    phase = _PHASE_ALIASES.get(args.phase, args.phase)
    if phase not in _PHASES:
        parser.error(f"unknown phase {args.phase!r}; choose from {sorted(_PHASES)} or their first letters")
    return _PHASES[phase](Path(args.root).resolve())


if __name__ == "__main__":
    raise SystemExit(main())
