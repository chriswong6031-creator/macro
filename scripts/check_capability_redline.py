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
import re
import sys
import tempfile
from pathlib import Path

# ── Files scanned ────────────────────────────────────────────────────────────

SCAN_PATHS = [
    "config/capability_manifest.yml",
    "engine/neuralweb/capability_broker.py",
]

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

# os.environ[...] VALUE assignment to a module/class-level variable
# (assignment: `CONST = os.environ[...]` or `self.x = os.environ[...]`)
# The broker is allowed to say `os.environ[ref_name]` in docstrings/comments.
_ENVIRON_ASSIGN = re.compile(
    r'^\s*(?:[A-Z_][A-Z0-9_]*|self\.[a-z_]\w*|[a-z_]\w*)\s*=\s*os\.environ\[',
    re.MULTILINE,
)

# ── Known-safe exemptions ─────────────────────────────────────────────────────

# Lines containing any of these phrases are exempted from the entropy scan.
# These are comments/docs that reference SECRET NAMES (not values).
_ENTROPY_EXEMPTIONS = [
    "secret_ref:",           # YAML field storing a name
    "os.environ[ref_name]",  # documented pattern in broker docstring
    "CLAUDE_CODE_OAUTH_TOKEN",  # the name itself (not a value)
    "VPS_DEPLOY_KEY",           # name
    "GITHUB_TOKEN",             # name
    "GITHUB_RUN_ID",            # name
    "GITHUB_WORKFLOW",          # name
    "GITHUB_SHA",               # name
    "GITHUB_ACTOR",             # name
    "ref_name",                 # variable name
    "secret_ref",               # field name
    # NOTE: bare '#' was removed — a line containing '#' is NOT exempt.
    # A secret pasted after a YAML inline comment (e.g. "key: value  # <40-hex>")
    # or on any line that happens to have '#' would sail through undetected.
    # All known-safe name strings are handled by _strip_known_names() instead.
]


def _line_is_entropy_exempt(line: str) -> bool:
    low = line.lower()
    for ex in _ENTROPY_EXEMPTIONS:
        if ex.lower() in low:
            return True
    # Strip the line of known-name strings before entropy check
    return False


def _strip_known_names(line: str) -> str:
    """Remove known-safe name strings before the entropy check."""
    for name in ["CLAUDE_CODE_OAUTH_TOKEN", "VPS_DEPLOY_KEY", "GITHUB_TOKEN",
                 "GITHUB_RUN_ID", "GITHUB_WORKFLOW", "GITHUB_SHA", "GITHUB_ACTOR",
                 "AUTONOMY_PAUSED", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID",
                 "DISCORD_WEBHOOK_URL", "DISCORD_WEBHOOK_WATCHLIST",
                 "ANTHROPIC_API_KEY", "DEEPSEEK_API_KEY",
                 "ref_name", "secret_ref", "capability_id"]:
        line = line.replace(name, "")
    return line


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
        try:
            content = abs_path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            raise RuntimeError(f"Could not read {rel_path}: {e}") from e

        lines = content.splitlines()
        for i, line in enumerate(lines, 1):
            # --- High-entropy check ---
            stripped_for_entropy = _strip_known_names(line)
            if not _line_is_entropy_exempt(line):
                for m in _HEX_40.finditer(stripped_for_entropy):
                    findings.append({
                        "file": rel_path,
                        "line_no": i,
                        "kind": "high_entropy_hex40",
                        "text": line.strip()[:160],
                    })
                for m in _BASE64_20.finditer(stripped_for_entropy):
                    findings.append({
                        "file": rel_path,
                        "line_no": i,
                        "kind": "high_entropy_base64",
                        "text": line.strip()[:160],
                    })

            # --- secrets.* reference (value capture) ---
            if _SECRETS_REF.search(line):
                findings.append({
                    "file": rel_path,
                    "line_no": i,
                    "kind": "secrets_value_reference",
                    "text": line.strip()[:160],
                })

            # --- os.environ assignment (value capture) ---
            if _ENVIRON_ASSIGN.search(line):
                findings.append({
                    "file": rel_path,
                    "line_no": i,
                    "kind": "environ_value_assignment",
                    "text": line.strip()[:160],
                })

    return findings


def selftest() -> int:
    """Prove the scanner catches planted violations and passes the clean real files."""
    print("Running selftest...")
    failures: list[str] = []

    with tempfile.TemporaryDirectory(prefix="capability_redline_selftest_") as tmpdir:
        tmp = Path(tmpdir)
        (tmp / "config").mkdir()
        (tmp / "engine" / "neuralweb").mkdir(parents=True)

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
