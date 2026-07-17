"""scripts/check_capability_redline.py — F3 capability-broker redline scanner.

THE REDLINE (the single unforgivable defect in the Metabolism):
    A secret value MUST NEVER land in a git artifact.

This script enforces that line by scanning:
  - config/capability_manifest.yml
  - engine/neuralweb/capability_broker.py

…for two classes of violation:

  1. HIGH-ENTROPY STRINGS — strings that look like they could be secret values.
     Pattern: 20+ contiguous base64 chars, or 40-char hex (API keys, tokens, SSH).
     Any such string in the scanned files is a hard failure.

  2. VALUE-CAPTURE PATTERNS — code or config that would plumb a secret VALUE into
     a tracked literal:
       - 'secrets.<name>' (GitHub Actions value reference)
       - os.environ[<name>] assigned to a tracked literal (in the broker)

     The broker is ALLOWED to reference os.environ key names in comments and
     docstrings (it documents that callers should do this).  The ban targets
     VALUE CAPTURE: `x = os.environ["SECRET"]` stored in a module-level or
     class-level constant.

Fail-closed: any scan error (file missing, parse error) → exit 1.

Usage:
    python3 scripts/check_capability_redline.py           # scan; exit 1 on finding
    python3 scripts/check_capability_redline.py --selftest  # synthetic proof; exit 0/1

Exit codes:
    0   all clear
    1   one or more findings, or scan error
"""
from __future__ import annotations

import argparse
import fnmatch
import re
import sys
import tempfile
from pathlib import Path

# ── Files scanned ────────────────────────────────────────────────────────────

# Files that MUST exist and be clean (fail-closed if missing).
# The metabolism PROPOSE/ADJUDICATE modules reference the OAuth capability by
# NAME and write git artifacts (dockets, governance rows) — they must never
# capture the VALUE. They are added here so the redline scanner covers them
# (post-review, PR #2082 hardening). NOTE: engine/llm_auth.py is deliberately
# NOT scanned — it is the single sanctioned boundary that reads the token value
# to make the API call; scanning it would flag that legitimate read.
SCAN_PATHS = [
    "config/capability_manifest.yml",
    "engine/neuralweb/capability_broker.py",
    "engine/neuralweb/key_pool.py",       # V2-B: multi-key pool (NEVER reads token values)
    "engine/metabolism/propose.py",
    "engine/metabolism/adjudicate.py",
    "engine/metabolism/audit.py",         # V7: AUDIT stage (reads diff text, never token values)
    "scripts/metabolism_propose.py",
    "scripts/metabolism_adjudicate.py",
    "scripts/metabolism_dispatch.py",     # V2-B: dispatcher (returns cap_id only)
    "scripts/metabolism_audit.py",        # V7: AUDIT CLI (reads pr/diff, never token values)
]

# Git-committed artifacts that must be clean IF present (written at run time,
# NOT gitignored → committed redline surfaces). Absence is fine. Entries may be
# literal paths OR globs.
# Only CONTROLLED-SCHEMA artifacts are scanned here. The general governance.jsonl,
# dockets, and adversary_ledger are deliberately NOT scanned: they carry
# legitimate high-entropy tokens (16-hex event_ids, run_ids, hashes, and
# LLM-generated free text) that would false-positive. Their leak risk is instead
# controlled at the source — the writer modules are in SCAN_PATHS above, so a
# token VALUE cannot be captured into them in the first place.
SCAN_IF_PRESENT = [
    "data/neuralweb/capability_audit.jsonl",
    "data/metabolism/key_ledger.jsonl",   # V2-B: key usage belief-state (NEVER a token value)
    "data/metabolism/journal/*.json",     # V2-B: freeze/stage journals (committed; symmetry w/ ledger)
                                          #   (base64 rule path-stripped here — see _PATH_TELEMETRY_GLOBS)
    "data/ai_costs/usage.jsonl",          # FIX 4: AI usage ledger (written by _capture_usage; NEVER a token value)
]

# The ONLY env keys the broker may legitimately READ (non-secret attribution
# fields written into the audit tape). A value-read of any other key — or a
# DYNAMIC key (e.g. os.environ[ref_name], which resolves to a secret name at
# run time) — is a redline violation: the broker must never read a secret value.
_SAFE_ENV_KEYS = frozenset({
    "GITHUB_RUN_ID", "GITHUB_WORKFLOW", "GITHUB_ACTOR", "GITHUB_SHA",
    "GITHUB_REPOSITORY", "GITHUB_REF", "GITHUB_EVENT_NAME",
    # Notification channels — these carry webhook URLs / bot tokens, NOT OAuth
    # secrets.  They may be read to send operator notify messages.  They are
    # listed here so metabolism_dispatch._notify_freeze() can read them without
    # triggering the environ_value_capture redline rule.
    "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID",
    "DISCORD_WEBHOOK_URL", "DISCORD_WEBHOOK_WATCHLIST",
    # V10 operator throttle (R-V10-1): a repo VARIABLE (csv of key ids like
    # "1,3,legacy"), never a token value — key_pool.enabled_key_ids() reads it
    # to filter the pool to operator-enabled keys.
    "METAB_KEYS_ENABLED",
    # V11 auto-run mode (R-V11-1): an operator mode string (off|5h_max|weekly_max),
    # never a secret — metabolism_dispatch reads it to select the run-until budget
    # gate branch.
    "METAB_RUN_UNTIL",
})

# ── Entropy pattern ───────────────────────────────────────────────────────────

# 40-char hex (SHA-1 / OAuth tokens / API keys that are purely hex)
_HEX_40 = re.compile(r"(?<![a-fA-F0-9])[a-fA-F0-9]{40}(?![a-fA-F0-9])")

# 20+ contiguous base64url chars (API keys, JWT segments, etc.)
# Avoid matching normal English words (require at least one digit or slash/plus/=)
_BASE64_20 = re.compile(
    r"(?<![A-Za-z0-9+/=])"
    r"(?=[A-Za-z0-9+/=]{20,})"
    r"(?=.*[0-9])"               # must contain at least one digit to reduce FP
    r"[A-Za-z0-9+/]{20,}={0,2}" # base64 body with optional padding
    r"(?![A-Za-z0-9+/=])"
)

# ── Value-capture patterns ────────────────────────────────────────────────────

# 'secrets.<anything>' in YAML or code — references the VALUE of a GitHub Secret
_SECRETS_REF = re.compile(r'\bsecrets\.[A-Za-z_][A-Za-z0-9_]*')

# Env VALUE read into a variable / dict-item / return — covers os.environ[...],
# os.environ.get(...), os.getenv(...). Anchored to assignment or `return` so a
# bare docstring/comment mention of `os.environ[ref_name]` (no `=`/`return`) does
# NOT match. The captured group is the accessor key (quoted literal or bare
# identifier); _env_key_is_safe() decides whether it is a redline finding.
_ENV_VALUE_READ = re.compile(
    r'(?:^\s*return\s+|^\s*[\w.]+(?:\[[^\]]*\])?\s*=\s*)'   # `return ` OR `lhs = `
    r'os\.(?:environ\.get|getenv|environ)\s*'
    r'[\[(]\s*'
    r'(?P<key>"[^"]*"|\'[^\']*\'|[A-Za-z_]\w*)',            # "LIT" | 'LIT' | ident
    re.MULTILINE,
)


def _env_key_is_safe(key_token: str) -> bool:
    """A read is safe ONLY when the key is a quoted literal in the allowlist.
    A dynamic (bare-identifier) key is NEVER safe — it could resolve to a
    secret ref name at run time."""
    t = key_token.strip()
    if len(t) >= 2 and t[0] in "\"'" and t[-1] == t[0]:
        return t[1:-1] in _SAFE_ENV_KEYS
    return False  # bare identifier / dynamic key → fail-closed

# ── Known-safe exemptions ─────────────────────────────────────────────────────

# NO whole-line entropy exemptions. A phrase-based line exemption is an attack
# surface: "secret_ref: <40-hex-secret>" would exempt the whole line and let the
# secret through. Instead, known SECRET NAME tokens are removed token-by-token by
# _strip_known_names() BEFORE the entropy scan, so a name is stripped but a value
# pasted next to it is still caught.
def _line_is_entropy_exempt(line: str) -> bool:  # retained for API stability
    return False


def _strip_known_names(line: str) -> str:
    """Remove known-safe name strings before the entropy check."""
    for name in ["CLAUDE_CODE_OAUTH_TOKEN_1", "CLAUDE_CODE_OAUTH_TOKEN_2",
                 "CLAUDE_CODE_OAUTH_TOKEN_3", "CLAUDE_CODE_OAUTH_TOKEN",
                 "VPS_DEPLOY_KEY", "GITHUB_TOKEN",
                 "GITHUB_RUN_ID", "GITHUB_WORKFLOW", "GITHUB_SHA", "GITHUB_ACTOR",
                 "AUTONOMY_PAUSED", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID",
                 "DISCORD_WEBHOOK_URL", "DISCORD_WEBHOOK_WATCHLIST",
                 "ANTHROPIC_API_KEY", "DEEPSEEK_API_KEY",
                 "ref_name", "secret_ref", "capability_id",
                 # Known-safe module path substrings that can appear in docstrings.
                 # Stripping path components (not values) prevents false-positives
                 # when a path like 'engine/neuralweb/key_pool.py' matches the
                 # base64 lookahead via a digit elsewhere on the same line.
                 "engine/neuralweb/key_pool", "scripts/metabolism_dispatch",
                 "engine/neuralweb/capability_broker", "engine/metabolism/",
                 "scripts/metabolism_", "data/metabolism/key_ledger"]:
        line = line.replace(name, "")
    return line


# ── Filesystem-path telemetry (base64 rule only) ──────────────────────────────

# Some committed artifacts legitimately embed FILESYSTEM PATHS. The metabolism
# journal `artifacts` array records docket paths on the self-hosted runner, e.g.
#   "/Users/…/data/metabolism/dockets/cycle-2026-07-13-e159-…-standouts.json"
# '/' is a base64 char, so a slash-joined path ≥20 chars is a run of base64-valid
# characters and false-positives the base64 entropy heuristic (a digit elsewhere
# on the line satisfies the digit requirement). A repo-RELATIVE path trips it too
# ("data/metabolism/dockets/cycle" is 29 base64 chars), so this cannot be fixed
# by rewriting the writer to store relative paths — it must be handled here.
#
# For the files matched below ONLY, path tokens are stripped before the base64
# check. This is NOT a blanket base64 disable: the 40-hex, secrets.* and
# environ-capture rules still run in full, AND a non-path base64 blob (no '/',
# so not a path token) in a journal is still caught. Mirrors the existing
# _strip_known_names() path-substring stripping, and is stricter than the
# precedent that omits governance.jsonl / dockets from scanning entirely.
_PATH_TELEMETRY_GLOBS = ("data/metabolism/journal/*.json",)

# A filesystem-path token: one or more `<seg>/` groups then a final segment.
# Path chars only — deliberately EXCLUDES '+' and '=' so a genuine base64 secret
# (which uses '+' / '=' padding) is never mistaken for a path and stripped.
_PATH_TOKEN = re.compile(r"(?:[A-Za-z0-9_.\-]*/)+[A-Za-z0-9_.\-]+")


def _is_path_telemetry(rel_path: str) -> bool:
    """True if rel_path is a committed artifact that legitimately embeds paths."""
    return any(fnmatch.fnmatch(rel_path, g) for g in _PATH_TELEMETRY_GLOBS)


def _strip_path_tokens(line: str) -> str:
    """Remove filesystem-path tokens so a path is not read as base64 entropy."""
    return _PATH_TOKEN.sub(" ", line)


# ── Scanner ───────────────────────────────────────────────────────────────────

def scan(root: Path | None = None) -> list[dict]:
    """Scan the target files for redline violations.

    Returns a list of finding dicts:
        {file, line_no, kind, text}
    An empty list means all clear.

    Any scan error (file missing, read error) → raises RuntimeError.
    """
    if root is None:
        root = Path(__file__).resolve().parent.parent

    findings: list[dict] = []

    for rel_path in SCAN_PATHS:
        abs_path = root / rel_path
        if not abs_path.exists():
            raise RuntimeError(
                f"Redline scan target not found: {rel_path}. "
                f"This file is required and must exist — fail-closed."
            )
        findings.extend(_scan_file(abs_path, rel_path))

    # Scan-if-present: absence is fine (nothing to leak yet); presence must be clean.
    for rel_path in SCAN_IF_PRESENT:
        if any(ch in rel_path for ch in "*?["):
            for abs_path in sorted(root.glob(rel_path)):
                if abs_path.is_file():
                    findings.extend(_scan_file(abs_path, str(abs_path.relative_to(root))))
        else:
            abs_path = root / rel_path
            if abs_path.exists():
                findings.extend(_scan_file(abs_path, rel_path))

    return findings


def _scan_file(abs_path: Path, rel_path: str) -> list[dict]:
    """Scan one file line-by-line for redline violations. Read error → fail-closed."""
    try:
        content = abs_path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        raise RuntimeError(f"Could not read {rel_path}: {e}") from e

    # Path-telemetry files (journal artifacts) embed filesystem paths that read
    # as base64 entropy; strip path tokens before the base64 check for those ONLY.
    path_telemetry = _is_path_telemetry(rel_path)

    out: list[dict] = []
    for i, line in enumerate(content.splitlines(), 1):
        # --- High-entropy check (names stripped token-wise first) ---
        stripped_for_entropy = _strip_known_names(line)
        # 40-hex still scans the un-path-stripped text (a hex secret inside a path
        # segment must still be caught); base64 drops path tokens for telemetry.
        base64_input = (_strip_path_tokens(stripped_for_entropy)
                        if path_telemetry else stripped_for_entropy)
        for _ in _HEX_40.finditer(stripped_for_entropy):
            out.append({"file": rel_path, "line_no": i,
                        "kind": "high_entropy_hex40", "text": line.strip()[:160]})
        for _ in _BASE64_20.finditer(base64_input):
            out.append({"file": rel_path, "line_no": i,
                        "kind": "high_entropy_base64", "text": line.strip()[:160]})

        # --- secrets.* reference (value capture) ---
        if _SECRETS_REF.search(line):
            out.append({"file": rel_path, "line_no": i,
                        "kind": "secrets_value_reference", "text": line.strip()[:160]})

        # --- env VALUE read (assignment/return of environ/getenv) ---
        for m in _ENV_VALUE_READ.finditer(line):
            if not _env_key_is_safe(m.group("key")):
                out.append({"file": rel_path, "line_no": i,
                            "kind": "environ_value_capture", "text": line.strip()[:160]})
    return out


def selftest() -> int:
    """Prove the scanner catches planted violations and passes the clean real files."""
    print("Running selftest...")
    failures: list[str] = []

    with tempfile.TemporaryDirectory(prefix="capability_redline_selftest_") as tmpdir:
        tmp = Path(tmpdir)
        (tmp / "config").mkdir()
        (tmp / "engine" / "neuralweb").mkdir(parents=True)
        (tmp / "engine" / "metabolism").mkdir(parents=True)
        (tmp / "scripts").mkdir(parents=True)

        # All SCAN_PATHS beyond the two under test must exist (fail-closed on
        # missing). Stub the metabolism writer modules as clean files so the
        # planted-secret cases exercise the entropy/value-capture logic rather
        # than tripping the missing-file RuntimeError.
        for rel in SCAN_PATHS:
            if rel in ("config/capability_manifest.yml",
                       "engine/neuralweb/capability_broker.py"):
                continue
            p = tmp / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("# clean metabolism module stub — references names only\n")

        # Test 1: clean manifest passes
        (tmp / "config" / "capability_manifest.yml").write_text(
            "schema: capability_manifest.v1\ncapabilities:\n"
            "  - capability_id: test_cap\n"
            "    kind: llm_oauth\n"
            "    secret_ref: MY_SECRET_NAME\n"
            "    storage_locus: gh-secret\n"
        )
        # Clean broker (no entropy, no secrets.*, no environ assign)
        (tmp / "engine" / "neuralweb" / "capability_broker.py").write_text(
            "# clean broker\ndef resolve(id, lane): return {'ref_name': 'MY_SECRET_NAME', 'allowed': True}\n"
        )

        try:
            found = scan(root=tmp)
        except RuntimeError as e:
            failures.append(f"Clean files raised RuntimeError: {e}")
            found = []
        if found:
            failures.append(f"Clean files should have no findings but got: {found}")
        else:
            print("  [PASS] clean files produce no findings")

        # Test 2: planted fake secret (40-char hex) is caught
        fake_token = "a" * 5 + "1" + "b" * 34   # 40-char hex-like
        (tmp / "config" / "capability_manifest.yml").write_text(
            f"schema: capability_manifest.v1\nsome_secret: {fake_token}\n"
        )
        try:
            found = scan(root=tmp)
        except RuntimeError:
            found = []
        hex_found = any(f["kind"] == "high_entropy_hex40" for f in found)
        if hex_found:
            print("  [PASS] planted 40-char hex is caught")
        else:
            failures.append("Planted 40-char hex string not caught by entropy scan")

        # Test 3: planted secrets.* reference is caught
        (tmp / "config" / "capability_manifest.yml").write_text(
            "schema: capability_manifest.v1\ntoken: ${{ secrets.MY_SECRET }}\n"
        )
        try:
            found = scan(root=tmp)
        except RuntimeError:
            found = []
        secrets_found = any(f["kind"] == "secrets_value_reference" for f in found)
        if secrets_found:
            print("  [PASS] secrets.* reference is caught")
        else:
            failures.append("Planted secrets.* reference not caught")

        # Test 3b: secret on a line that contains '#' is caught (regression guard —
        #   the bare '#' exemption was removed because it let secrets smuggled after
        #   an inline comment or on any '#'-containing line sail through undetected).
        (tmp / "config" / "capability_manifest.yml").write_text(
            f"schema: capability_manifest.v1\n"
            f"x: 'value_pad_{fake_token}#comment'\n"  # secret value on a '#'-bearing line
        )
        try:
            found = scan(root=tmp)
        except RuntimeError:
            found = []
        hash_line_found = any(f["kind"] == "high_entropy_hex40" for f in found)
        if hash_line_found:
            print("  [PASS] secret on a '#'-bearing line is caught (no bare-'#' exemption)")
        else:
            failures.append(
                "Secret on a '#'-bearing line NOT caught — bare '#' exemption may have returned"
            )

        # Test 4: missing scan target is a hard failure (fail-closed)
        (tmp / "config" / "capability_manifest.yml").unlink()
        try:
            scan(root=tmp)
            failures.append("Missing scan target should raise RuntimeError but did not")
        except RuntimeError:
            print("  [PASS] missing scan target raises RuntimeError (fail-closed)")

    # Test 5a: planted fake token in key_ledger (SCAN_IF_PRESENT) is caught
    with tempfile.TemporaryDirectory(prefix="capability_redline_ledger_selftest_") as tmpdir2:
        tmp2 = Path(tmpdir2)
        (tmp2 / "config").mkdir()
        (tmp2 / "engine" / "neuralweb").mkdir(parents=True)
        (tmp2 / "engine" / "metabolism").mkdir(parents=True)
        (tmp2 / "scripts").mkdir(parents=True)
        (tmp2 / "data" / "metabolism").mkdir(parents=True)
        # Stub all SCAN_PATHS as clean
        for rel in SCAN_PATHS:
            p2 = tmp2 / rel
            p2.parent.mkdir(parents=True, exist_ok=True)
            p2.write_text("# clean stub — names only\n")
        # Plant a fake token in key_ledger.jsonl (SCAN_IF_PRESENT)
        fake_tok2 = "a" * 5 + "1" + "b" * 34  # 40-char hex-like
        import json as _json
        ledger_row = _json.dumps({"schema": "metabolism.key_ledger.v1", "key_id": "x",
                                  "bad_field": fake_tok2})
        (tmp2 / "data" / "metabolism" / "key_ledger.jsonl").write_text(
            ledger_row + "\n"
        )
        try:
            found2 = scan(root=tmp2)
        except RuntimeError:
            found2 = []
        ledger_found = any(f["kind"] == "high_entropy_hex40" for f in found2)
        if ledger_found:
            print("  [PASS] planted fake token in key_ledger.jsonl is caught by SCAN_IF_PRESENT")
        else:
            failures.append(
                "Planted fake token in key_ledger.jsonl NOT caught — SCAN_IF_PRESENT may not cover it"
            )

    # Test 5b: planted fake token in usage.jsonl (SCAN_IF_PRESENT) is caught
    with tempfile.TemporaryDirectory(prefix="capability_redline_usage_selftest_") as tmpdir_u:
        tmp_u = Path(tmpdir_u)
        (tmp_u / "config").mkdir()
        (tmp_u / "engine" / "neuralweb").mkdir(parents=True)
        (tmp_u / "engine" / "metabolism").mkdir(parents=True)
        (tmp_u / "scripts").mkdir(parents=True)
        (tmp_u / "data" / "ai_costs").mkdir(parents=True)
        # Stub all SCAN_PATHS as clean
        for rel in SCAN_PATHS:
            pu = tmp_u / rel
            pu.parent.mkdir(parents=True, exist_ok=True)
            pu.write_text("# clean stub — names only\n")
        # Plant a fake token in usage.jsonl (SCAN_IF_PRESENT)
        fake_tok_u = "a" * 5 + "1" + "b" * 34  # 40-char hex-like
        import json as _json
        usage_row = _json.dumps({"schema": "ai_costs.usage.v1", "lane": "test",
                                 "bad_field": fake_tok_u})
        (tmp_u / "data" / "ai_costs" / "usage.jsonl").write_text(usage_row + "\n")
        try:
            found_u = scan(root=tmp_u)
        except RuntimeError:
            found_u = []
        usage_found = any(f["kind"] == "high_entropy_hex40" for f in found_u)
        if usage_found:
            print("  [PASS] planted fake token in usage.jsonl is caught by SCAN_IF_PRESENT")
        else:
            failures.append(
                "Planted fake token in usage.jsonl NOT caught — SCAN_IF_PRESENT may not cover it"
            )

    # Test 6: journal path-telemetry exemption — the base64 rule ignores
    # filesystem paths BUT the stronger rules (and non-path base64) still fire.
    with tempfile.TemporaryDirectory(prefix="capability_redline_journal_selftest_") as tmpdir3:
        tmp3 = Path(tmpdir3)
        (tmp3 / "config").mkdir()
        for rel in SCAN_PATHS:
            p3 = tmp3 / rel
            p3.parent.mkdir(parents=True, exist_ok=True)
            p3.write_text("# clean stub — names only\n")
        jdir = tmp3 / "data" / "metabolism" / "journal"
        jdir.mkdir(parents=True)
        import json as _json

        # 6a: a journal whose ONLY entropy is a filesystem-path artifact (exactly
        #     the real-world shape) must produce NO base64 finding.
        (jdir / "cycle-2026-07-13-e159-site-us-standouts.json").write_text(_json.dumps({
            "schema": "metabolism.journal.v1",
            "cycle_id": "cycle-2026-07-13-e159-site-us-standouts",
            "artifacts": ["/Users/x/actions-runner-1/_work/macro/macro/data/"
                          "metabolism/dockets/cycle-2026-07-13-e159-site-us-standouts.json"],
        }, indent=2))
        try:
            found3 = scan(root=tmp3)
        except RuntimeError:
            found3 = []
        if any(f["kind"] == "high_entropy_base64" for f in found3):
            failures.append(
                "Filesystem path in journal artifacts STILL flagged base64 — path strip ineffective"
            )
        else:
            print("  [PASS] journal filesystem-path artifact is NOT a base64 false-positive")

        # 6b: a NON-path base64 blob planted in a journal is STILL caught
        #     (proves the exemption is a path strip, not a blanket base64 disable).
        (jdir / "cycle-2026-07-13-e159-site-us-standouts.json").write_text(_json.dumps({
            "schema": "metabolism.journal.v1",
            "leak": "Zm9vYmFyMTIzNDU2Nzg5MGFiY2RlZmdo",  # 33 base64 chars, digits, no '/'
        }, indent=2))
        try:
            found3b = scan(root=tmp3)
        except RuntimeError:
            found3b = []
        if any(f["kind"] == "high_entropy_base64" for f in found3b):
            print("  [PASS] non-path base64 blob in a journal is STILL caught (not a blanket disable)")
        else:
            failures.append(
                "Non-path base64 blob in a journal NOT caught — exemption over-broadened to a blanket disable"
            )

        # 6c: a 40-hex token planted in a journal is STILL caught (hex40 unaffected).
        fake_tok3 = "a" * 5 + "1" + "b" * 34  # 40-char hex-like, no '/'
        (jdir / "cycle-2026-07-13-e159-site-us-standouts.json").write_text(_json.dumps({
            "schema": "metabolism.journal.v1", "leak": fake_tok3,
        }, indent=2))
        try:
            found3c = scan(root=tmp3)
        except RuntimeError:
            found3c = []
        if any(f["kind"] == "high_entropy_hex40" for f in found3c):
            print("  [PASS] 40-hex token in a journal is STILL caught (hex40 rule unaffected)")
        else:
            failures.append(
                "40-hex token in a journal NOT caught — path strip wrongly weakened the hex40 rule"
            )

    # Test 5: real production files pass (no planted violations)
    real_root = Path(__file__).resolve().parent.parent
    try:
        real_findings = scan(root=real_root)
        if real_findings:
            failures.append(
                f"Real production files have {len(real_findings)} finding(s): "
                + "; ".join(f['kind'] + "@" + f['file'] for f in real_findings[:5])
            )
        else:
            print("  [PASS] real production files are clean")
    except RuntimeError as e:
        # Files may not exist yet in the test environment — that is OK for selftest
        print(f"  [SKIP] real file check: {e}")

    if failures:
        print("\nSELFTEST FAILED:")
        for f in failures:
            print(f"  - {f}")
        return 1

    print("selftest OK")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="F3 capability-broker redline scanner — hard-fail on secret values in tracked files."
    )
    ap.add_argument(
        "--selftest",
        action="store_true",
        help="Run synthetic selftest; exit 0 on pass, 1 on failure.",
    )
    args = ap.parse_args(argv)

    if args.selftest:
        return selftest()

    try:
        findings = scan()
    except RuntimeError as e:
        print(f"HARD: {e}", file=sys.stderr)
        return 1

    if findings:
        print(
            f"::error:: {len(findings)} capability-redline violation(s) — "
            f"secret values must NEVER land in tracked git artifacts:",
            file=sys.stderr,
        )
        for f in findings[:20]:
            print(
                f"  {f['file']}:{f['line_no']} [{f['kind']}]  {f['text']}",
                file=sys.stderr,
            )
        if len(findings) > 20:
            print(f"  ... and {len(findings) - 20} more", file=sys.stderr)
        return 1

    print(
        "check_capability_redline: OK — no secret values or value-capture patterns "
        "found in capability manifest or broker."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
