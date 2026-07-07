"""check_ruling_conflicts.py — CI guard for the Ruling Graph (RUL-CL-6/7/8).

Hard failures (exit 1):
  H1 — New fdr_family token in changed files not in meta.known_fdr_families (RUL-CL-6a).
  H2 — Privacy-boundary token (meta.site_privacy_tokens) found in site/ changed files
       or scripts that write to site/ (RUL-CL-6b BRIDGE law).

Warnings (stderr, never fatal):
  W1 — Changed research/config file contains a match_term from a killed/deferred/blocked/
       no_build/duplicate row, and the changed file does NOT cite the row's ruling_id
       (re-proposal detection per RUL-CL-7, deterministic substring only).
  W2 — Row with come_back_on strictly before today (expired clock; RUL-CL-8).
  W3 — Clocked row with come_back_on but no experiment_ref (mirror of build WARN; RUL-CL-8).

Diff base: env RULING_DIFF_BASE (default origin/main).
  Changed files = git diff --name-only <merge-base>...HEAD plus uncommitted.
  If git is unavailable: print notice, skip H1/H2/W1 (diff-scoped), still run W2/W3.

Today override: env RULING_GRAPH_TODAY (ISO date YYYY-MM-DD) for deterministic tests.

Allowlist: data/neuralweb/ruling_conflicts_allowlist.json
  [{\"path\": \"...\", \"token\": \"...\", \"reason\": \"...\"}] — silences H2 entries only
  (still printed as allowlisted).

Exit codes: 1 if any non-allowlisted HARD, else 0.

Usage:
  python scripts/check_ruling_conflicts.py
  python scripts/check_ruling_conflicts.py --selftest
  RULING_DIFF_BASE=main python scripts/check_ruling_conflicts.py
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Dead statuses that trigger W1 re-proposal scan (RUL-CL-7)
# ---------------------------------------------------------------------------
_DEAD_STATUSES = frozenset({"killed", "no_build", "deferred", "duplicate", "blocked"})

# ---------------------------------------------------------------------------
# FDR family token regex (same family as the meta grep in ruling_graph.yml)
# ---------------------------------------------------------------------------
_FDR_RE = re.compile(r"fdr_family['\"]?\s*[:=]\s*['\"]?([a-z][a-z0-9_]+)")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_graph(root: Path) -> dict:
    yml_path = root / "config" / "ruling_graph.yml"
    with yml_path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _load_allowlist(root: Path) -> list[dict]:
    path = root / "data" / "neuralweb" / "ruling_conflicts_allowlist.json"
    if not path.exists():
        return []
    try:
        return json.loads(path.read_bytes())
    except Exception:
        return []


def _today(root: Path | None = None) -> datetime.date:
    """Return today's date; allow override via RULING_GRAPH_TODAY env (for tests)."""
    env_val = os.environ.get("RULING_GRAPH_TODAY", "").strip()
    if env_val:
        try:
            return datetime.date.fromisoformat(env_val)
        except ValueError:
            pass
    return datetime.date.today()


# ---------------------------------------------------------------------------
# Changed-file detection
# ---------------------------------------------------------------------------

def _get_changed_files(root: Path) -> tuple[list[Path], bool]:
    """Return (list_of_changed_paths, git_ok).

    git_ok=False means git was unavailable and diff-scoped checks should be skipped.
    Returns both staged/unstaged and HEAD..merge-base changes.
    """
    diff_base = os.environ.get("RULING_DIFF_BASE", "origin/main").strip()
    try:
        merge_base_result = subprocess.run(
            ["git", "merge-base", "HEAD", diff_base],
            cwd=root, capture_output=True, text=True, timeout=15,
        )
        if merge_base_result.returncode != 0:
            return [], False
        merge_base = merge_base_result.stdout.strip()

        committed = subprocess.run(
            ["git", "diff", "--name-only", f"{merge_base}...HEAD"],
            cwd=root, capture_output=True, text=True, timeout=15,
        )
        uncommitted = subprocess.run(
            ["git", "diff", "--name-only"],
            cwd=root, capture_output=True, text=True, timeout=15,
        )
        unstaged = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard"],
            cwd=root, capture_output=True, text=True, timeout=15,
        )
        names: set[str] = set()
        for proc in (committed, uncommitted, unstaged):
            if proc.returncode == 0:
                names.update(proc.stdout.splitlines())

        paths = [root / n for n in names if n.strip()]
        return [p for p in paths if p.exists()], True

    except Exception:
        return [], False


# Tokens that the regex can match but are not real fdr_family values
_FDR_NON_TOKENS = frozenset({"null", "none", "false", "true"})

# Paths to exclude from changed-file scanning (these are scratch dirs per spec)
_EXCLUDED_PATH_PREFIXES = (".rgx_scratch",)


def _is_excluded(path: Path, root: Path) -> bool:
    """Return True if path is in an excluded directory."""
    try:
        rel = str(path.relative_to(root)).replace("\\", "/")
    except ValueError:
        return False
    return any(rel.startswith(p) for p in _EXCLUDED_PATH_PREFIXES)


# ---------------------------------------------------------------------------
# H1 — New FDR family check (RUL-CL-6a)
# ---------------------------------------------------------------------------

# Build products of the graph itself: their fdr_family content is already
# validated by build_ruling_graph.py (row fdr_family must be in known_fdr_families),
# so H1 scanning them is self-referential and can only produce phantom tokens.
_H1_GENERATED_ARTIFACTS = ("docs/NEURAL_WEB_CASE_LAW.md", "site/neuralwebdata/ruling_graph.json")


def _check_h1(data: dict, changed_files: list[Path], root: Path) -> list[dict]:
    """HARD: scan changed files for fdr_family tokens not in meta.known_fdr_families."""
    known = set(data.get("meta", {}).get("known_fdr_families", []))
    findings: list[dict] = []

    for path in changed_files:
        if not path.is_file():
            continue
        if _is_excluded(path, root):
            continue
        try:
            rel_check = str(path.relative_to(root)).replace("\\", "/")
        except ValueError:
            rel_check = str(path)
        if rel_check in _H1_GENERATED_ARTIFACTS:
            continue
        try:
            rel = str(path.relative_to(root))
        except ValueError:
            rel = str(path)
        # Only scan text-like files
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for m in _FDR_RE.finditer(text):
            token = m.group(1)
            if not token or token in _FDR_NON_TOKENS:
                continue
            if token not in known:
                line_no = text[: m.start()].count("\n") + 1
                findings.append({
                    "severity": "HARD",
                    "check": "H1",
                    "file": rel,
                    "line": line_no,
                    "token": token,
                    "message": (
                        f"H1 [HARD] {rel}:{line_no} — new fdr_family token {token!r} not in "
                        f"meta.known_fdr_families. Either use an existing family or register the "
                        f"new one in config/ruling_graph.yml meta.known_fdr_families and cite a "
                        f"ruling (RUL-CL-6a)."
                    ),
                })
    return findings


# ---------------------------------------------------------------------------
# H2 — Privacy boundary check (RUL-CL-6b)
# ---------------------------------------------------------------------------

def _is_site_writer(path: Path, root: Path) -> bool:
    """Heuristic: does this script WRITE to site/?

    Looks for patterns like open('site/...', 'w') or Path('site/...').write_text
    or mkdir+write combos.  Simple heuristic: look for write_text|write_bytes|open.*w
    alongside 'site/' on the same or adjacent line.

    Does NOT flag scripts that merely reference 'site/' in read-only contexts
    or in comments/docstrings about the path.
    """
    if path.suffix != ".py":
        return False
    # Self-exempt: this script and the build script scan/reference site/ for governance purposes
    this_script = Path(__file__).resolve()
    if path.resolve() == this_script:
        return False
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    # Look for write patterns next to site/
    write_indicators = ["write_text", "write_bytes", ".write(", "open(", ".mkdir("]
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if "site/" not in line:
            continue
        # Check current line and ±2 neighbors for write patterns
        context = "\n".join(lines[max(0, i - 2): i + 3])
        if any(w in context for w in write_indicators):
            return True
    return False


def _check_h2(
    data: dict,
    changed_files: list[Path],
    root: Path,
    allowlist: list[dict],
) -> list[dict]:
    """HARD: scan changed site/ files and site-writing scripts for privacy tokens."""
    privacy_tokens: list[str] = [
        t.lower() for t in data.get("meta", {}).get("site_privacy_tokens", [])
    ]
    # Build allowlist lookup: set of (path_pattern, token_lower)
    allowed_pairs: set[tuple[str, str]] = {
        (e.get("path", ""), e.get("token", "").lower())
        for e in allowlist
    }

    findings: list[dict] = []

    for path in changed_files:
        if not path.is_file():
            continue
        try:
            rel = str(path.relative_to(root))
        except ValueError:
            rel = str(path)
        rel_fwd = rel.replace("\\", "/")

        is_site = rel_fwd.startswith("site/")
        is_writer = (not is_site) and _is_site_writer(path, root)
        if not (is_site or is_writer):
            continue

        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        text_lower = text.lower()
        lines = text.splitlines()

        for token in privacy_tokens:
            if token not in text_lower:
                continue
            # Find which lines
            for i, line in enumerate(lines, start=1):
                if token in line.lower():
                    is_allowlisted = (rel_fwd, token) in allowed_pairs or (rel, token) in allowed_pairs
                    severity = "HARD/allowlisted" if is_allowlisted else "HARD"
                    findings.append({
                        "severity": severity,
                        "check": "H2",
                        "file": rel,
                        "line": i,
                        "token": token,
                        "allowlisted": is_allowlisted,
                        "message": (
                            f"H2 [{severity}] {rel}:{i} — privacy token {token!r} found in "
                            f"{'site/ path' if is_site else 'site-writing script'}. "
                            f"Held-book/fill/position fields must not appear on public paths "
                            f"(RUL-CL-6b BRIDGE law)."
                            + (" [allowlisted]" if is_allowlisted else "")
                        ),
                    })
    return findings


# ---------------------------------------------------------------------------
# W1 — Re-proposal detection (RUL-CL-7)
# ---------------------------------------------------------------------------

def _check_w1(data: dict, changed_files: list[Path], root: Path) -> list[dict]:
    """WARN: changed research/config file contains match_term from dead row without citing ruling_id."""
    rulings: list[dict] = data.get("rulings", [])
    dead_rows = [r for r in rulings if r.get("status") in _DEAD_STATUSES]

    # Only scan research/*.md, research/**/*.md, config/*.yml.
    # The graph's own files are excluded: the registry restates every dead
    # ruling's vocabulary by construction, so scanning it is pure self-noise.
    _w1_self = {"config/ruling_graph.yml", "docs/NEURAL_WEB_CASE_LAW.md",
                "site/neuralwebdata/ruling_graph.json"}
    scan_paths = [
        p for p in changed_files
        if p.is_file() and (
            (p.suffix in (".md", ".yml")) and
            (
                str(p.relative_to(root)).startswith("research/") or
                str(p.relative_to(root)).startswith("config/")
            ) and
            str(p.relative_to(root)).replace("\\", "/") not in _w1_self
        )
    ]

    findings: list[dict] = []

    for path in scan_paths:
        try:
            rel = str(path.relative_to(root))
        except ValueError:
            rel = str(path)
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        text_lower = text.lower()

        for row in dead_rows:
            rid = row.get("ruling_id", "")
            match_terms: list[str] = row.get("match_terms") or []
            unblock = (row.get("unblock_condition") or "").strip()
            status = row.get("status", "")

            for term in match_terms:
                # Word-boundary match: a bare substring test lets short terms
                # like 'nc-1' fire inside 'func-1' or 'demark' inside
                # 'demarketing'. Alphanumeric lookarounds keep hyphenated terms
                # matchable while blocking mid-token hits (RUL-CL-7).
                pat = r"(?<![a-z0-9])" + re.escape(term.lower()) + r"(?![a-z0-9])"
                if re.search(pat, text_lower):
                    # If the ruling_id itself appears in the file, it is cited — clear
                    if rid in text:
                        continue
                    findings.append({
                        "severity": "WARN",
                        "check": "W1",
                        "file": rel,
                        "term": term,
                        "ruling_id": rid,
                        "status": status,
                        "unblock": unblock,
                        "message": (
                            f"W1 [WARN] {rel} — contains term {term!r} which matches "
                            f"{rid} (status={status!r}) but does not cite {rid}. "
                            f"Reopen/unblock condition: {unblock or 'none specified'} (RUL-CL-7)."
                        ),
                    })
                    break  # one match_term per row per file is enough

    return findings


# ---------------------------------------------------------------------------
# W2 — Expired clocks (RUL-CL-8)
# ---------------------------------------------------------------------------

def _check_w2(data: dict, root: Path) -> list[dict]:
    """WARN: row come_back_on is strictly before today."""
    today = _today(root)
    rulings: list[dict] = data.get("rulings", [])
    findings: list[dict] = []

    for r in rulings:
        cbo = r.get("come_back_on")
        if not cbo:
            continue
        try:
            cbo_date = datetime.date.fromisoformat(str(cbo))
        except (ValueError, TypeError):
            continue
        if cbo_date < today:
            rid = r.get("ruling_id", "<missing>")
            findings.append({
                "severity": "WARN",
                "check": "W2",
                "ruling_id": rid,
                "come_back_on": str(cbo_date),
                "today": str(today),
                "message": (
                    f"W2 [WARN] [{rid}]: come_back_on={cbo_date} is in the past "
                    f"(today={today}). Clock has fired — adjudicate or supersede (RUL-CL-8)."
                ),
            })
    return findings


# ---------------------------------------------------------------------------
# W3 — Clocked row with null experiment_ref (RUL-CL-8)
# ---------------------------------------------------------------------------

def _check_w3(data: dict) -> list[dict]:
    """WARN: row with come_back_on but no experiment_ref."""
    rulings: list[dict] = data.get("rulings", [])
    findings: list[dict] = []

    for r in rulings:
        cbo = r.get("come_back_on")
        eref = r.get("experiment_ref")
        if cbo and not eref:
            rid = r.get("ruling_id", "<missing>")
            findings.append({
                "severity": "WARN",
                "check": "W3",
                "ruling_id": rid,
                "message": (
                    f"W3 [WARN] [{rid}]: come_back_on={cbo!r} but experiment_ref is null. "
                    f"Prefer an experiments-registry entry for clocks (RUL-CL-8)."
                ),
            })
    return findings


# ---------------------------------------------------------------------------
# Selftest
# ---------------------------------------------------------------------------

def _run_selftest(root: Path) -> int:
    """Plant synthetic violations for H1, H2, W1 and assert each fires."""
    all_passed = True

    # Load real graph for W1 test
    try:
        data = _load_graph(root)
    except Exception as e:
        print(f"selftest FAIL: could not load ruling graph: {e}")
        return 1

    print("Running check_ruling_conflicts selftest...")

    # --- H1: new fdr_family token not in known list ---
    # NOTE: synthetic token is built at runtime to avoid being caught by live scan of THIS file.
    _synthetic_fdr_token = "_".join(["zzz", "new", "synthetic", "family", "xyz"])
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        fake_file = tmp_path / "test_h1.py"
        fake_file.write_text(f"fdr_family = '{_synthetic_fdr_token}'\n")

        h1_findings = _check_h1(data, [fake_file], root)
        h1_match = any(
            f["check"] == "H1" and "zzz_new_synthetic_family_xyz" in f["token"]
            for f in h1_findings
        )
        status = "PASS" if h1_match else "FAIL"
        if not h1_match:
            all_passed = False
        print(f"  selftest [{status}] H1: new fdr_family token fires HARD")

    # --- H2: privacy token in synthetic site/ file ---
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        # Fake root so rel path resolves as site/
        fake_root = tmp_path
        site_dir = tmp_path / "site"
        site_dir.mkdir()
        fake_site_file = site_dir / "test_h2.html"
        # Use held_book token
        fake_site_file.write_text('<div class="held_book">test</div>\n')

        # Use a graph with held_book in site_privacy_tokens
        fake_data = {
            "meta": {
                "site_privacy_tokens": ["held_book"],
                "known_fdr_families": [],
            },
            "rulings": [],
        }
        h2_findings = _check_h2(fake_data, [fake_site_file], fake_root, [])
        h2_match = any(
            f["check"] == "H2" and "held_book" in f["token"]
            for f in h2_findings
        )
        status = "PASS" if h2_match else "FAIL"
        if not h2_match:
            all_passed = False
        print(f"  selftest [{status}] H2: privacy token in site/ file fires HARD")

    # --- W1: research file re-proposes a dead row term without citing the ruling_id ---
    # Use a synthetic dead row regardless of graph contents, to ensure the check fires.
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        research_dir = tmp_path / "research"
        research_dir.mkdir()
        fake_research = research_dir / "test_w1.md"
        # Use the term "synthetic_lobe_charter_w1_test" — does NOT appear in the file as ruling_id
        fake_research.write_text(
            "# Synthetic Proposal\n\nThis proposes synthetic_lobe_charter_w1_test.\n"
        )
        fake_dead_row = {
            "ruling_id": "TEST-KILLED-W1",
            "status": "killed",
            "match_terms": ["synthetic_lobe_charter_w1_test"],
            "unblock_condition": "New factual basis required",
        }
        fake_data_w1 = {
            "meta": {},
            "rulings": [fake_dead_row],
        }
        w1_findings = _check_w1(fake_data_w1, [fake_research], tmp_path)
        w1_match = any(
            f["check"] == "W1" and f.get("ruling_id") == "TEST-KILLED-W1"
            for f in w1_findings
        )
        status_w1 = "PASS" if w1_match else "FAIL"
        if not w1_match:
            all_passed = False
        print(f"  selftest [{status_w1}] W1: dead-row re-proposal detected (synthetic killed row)")

        # Also test that a file CITING the ruling_id is NOT flagged
        fake_research_citing = research_dir / "test_w1_citing.md"
        fake_research_citing.write_text(
            "# Proposal\n\nThis proposes synthetic_lobe_charter_w1_test. See TEST-KILLED-W1.\n"
        )
        w1_citing = _check_w1(fake_data_w1, [fake_research_citing], tmp_path)
        w1_citing_clean = not any(f["check"] == "W1" for f in w1_citing)
        status_cite = "PASS" if w1_citing_clean else "FAIL"
        if not w1_citing_clean:
            all_passed = False
        print(f"  selftest [{status_cite}] W1: file citing ruling_id is NOT flagged")

    # --- W2: expired clock ---
    fake_data_w2 = {
        "meta": {},
        "rulings": [{
            "ruling_id": "TEST-CLOCK-EXPIRED",
            "come_back_on": "2000-01-01",
            "experiment_ref": None,
            "status": "deferred",
        }],
    }
    old_env = os.environ.get("RULING_GRAPH_TODAY")
    os.environ["RULING_GRAPH_TODAY"] = "2026-07-06"
    try:
        w2_findings = _check_w2(fake_data_w2, root)
    finally:
        if old_env is None:
            os.environ.pop("RULING_GRAPH_TODAY", None)
        else:
            os.environ["RULING_GRAPH_TODAY"] = old_env
    w2_match = any(f["check"] == "W2" and f.get("ruling_id") == "TEST-CLOCK-EXPIRED" for f in w2_findings)
    status = "PASS" if w2_match else "FAIL"
    if not w2_match:
        all_passed = False
    print(f"  selftest [{status}] W2: expired clock fires WARN")

    # --- Selftest: H2 allowlist silences but still prints ---
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        fake_root2 = tmp_path
        site_dir2 = tmp_path / "site"
        site_dir2.mkdir()
        fake_site_file2 = site_dir2 / "allowed_h2.html"
        fake_site_file2.write_text('<div class="held_book">test</div>\n')
        rel_path = str(fake_site_file2.relative_to(tmp_path)).replace("\\", "/")
        fake_allowlist = [{"path": rel_path, "token": "held_book", "reason": "selftest allowlist"}]
        fake_data_h2al = {
            "meta": {"site_privacy_tokens": ["held_book"], "known_fdr_families": []},
            "rulings": [],
        }
        h2_al_findings = _check_h2(fake_data_h2al, [fake_site_file2], fake_root2, fake_allowlist)
        h2_al_match = any(
            f["check"] == "H2" and f.get("allowlisted") is True
            for f in h2_al_findings
        )
        status = "PASS" if h2_al_match else "FAIL"
        if not h2_al_match:
            all_passed = False
        print(f"  selftest [{status}] H2-allowlist: allowlisted token is still printed but marked allowlisted")

    print()
    if all_passed:
        print("selftest PASSED — all synthetic cases handled correctly")
        return 0
    else:
        print("selftest FAILED — one or more cases not caught")
        return 1


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--selftest", action="store_true",
                    help="Run selftest with synthetic violations; exit 0 on pass")
    ap.add_argument("--root", type=Path, default=ROOT,
                    help="Repo root (default: parent of scripts/)")
    args = ap.parse_args()

    root = args.root.resolve()

    if args.selftest:
        return _run_selftest(root)

    # Load graph + allowlist
    try:
        data = _load_graph(root)
    except Exception as e:
        print(f"[ERROR] Could not load ruling graph: {e}", file=sys.stderr)
        return 1

    allowlist = _load_allowlist(root)

    # Get changed files
    changed_files, git_ok = _get_changed_files(root)
    if not git_ok:
        print(
            "[NOTICE] check_ruling_conflicts: git unavailable or merge-base unreachable. "
            "Skipping diff-scoped checks (H1, H2, W1). W2/W3 still run.",
            file=sys.stderr,
        )

    # Collect all findings
    hard_findings: list[dict] = []
    warn_findings: list[dict] = []

    if git_ok:
        h1 = _check_h1(data, changed_files, root)
        hard_findings.extend(h1)

        h2 = _check_h2(data, changed_files, root, allowlist)
        # Split: allowlisted H2 → printed as warn (still printed), non-allowlisted → hard
        for f in h2:
            if f.get("allowlisted"):
                warn_findings.append(f)
            else:
                hard_findings.append(f)

        w1 = _check_w1(data, changed_files, root)
        warn_findings.extend(w1)

    w2 = _check_w2(data, root)
    warn_findings.extend(w2)

    w3 = _check_w3(data)
    warn_findings.extend(w3)

    # Print warnings
    for f in warn_findings:
        print(f"  {f['message']}", file=sys.stderr)

    if warn_findings:
        n_w2 = sum(1 for f in warn_findings if f["check"] == "W2")
        n_w3 = sum(1 for f in warn_findings if f["check"] == "W3")
        n_w1 = sum(1 for f in warn_findings if f["check"] == "W1")
        n_h2al = sum(1 for f in warn_findings if f["check"] == "H2")
        parts = []
        if n_h2al:
            parts.append(f"{n_h2al} H2-allowlisted")
        if n_w1:
            parts.append(f"{n_w1} W1 re-proposal")
        if n_w2:
            parts.append(f"{n_w2} W2 expired-clock")
        if n_w3:
            parts.append(f"{n_w3} W3 clock-no-ref")
        print(
            f"::warning::check_ruling_conflicts: {len(warn_findings)} warning(s): "
            + ", ".join(parts),
            file=sys.stderr,
        )

    # Print HARD errors
    for f in hard_findings:
        print(f"  {f['message']}", file=sys.stderr)

    if hard_findings:
        print(
            f"\n::error::check_ruling_conflicts: {len(hard_findings)} HARD violation(s). "
            f"Fix before merging.",
            file=sys.stderr,
        )
        return 1

    if not hard_findings and not warn_findings:
        print("check_ruling_conflicts: OK — no violations found.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
