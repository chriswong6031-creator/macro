"""Private-repo cutover: the clean-bootstrap path must be private-safe (DEC:B1-MACRO-PRIVATE-CUTOVER).

Sol Day-6 AMENDMENT clause A requires the clean-bootstrap path to be
private-safe before the Chairman flips repository visibility: no
``curl <public-raw-blob-host>/.../macro/... | bash`` dependency may remain
for canonical private bootstrap, clone must use the governed authenticated
path, and no personal PAT/key may be required.

This suite is hermetic: it reads the shipped shell/py files as text and
asserts on their contents. It never clones a repository, never touches the
network, and never SSHes anywhere.

Run: python -m pytest tests/test_deploy_bootstrap_private.py -q
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SETUP_SH = ROOT / "app" / "deploy" / "setup.sh"
BOOTSTRAP_SH = ROOT / "app" / "deploy" / "bootstrap_repo.sh"
OPTION_SHADOW_PY = ROOT / "scripts" / "build_prophet_option_shadow_lifecycle.py"


# ---------------------------------------------------------------------------
# Detection helper (case 8 self-tests THIS function, not an inline assertion,
# so a future edit that reintroduces the anonymous-raw pattern cannot pass the
# suite silently just because the helper it would have used moved).
# ---------------------------------------------------------------------------

def contains_anonymous_raw_dependency(text: str) -> bool:
    """True if ``text`` still depends on the anonymous public raw-blob host.

    Flags both the bare domain (``raw`` + ``.githubusercontent.com``,
    deliberately not spelled as one literal in *this* module either — the
    module itself must pass its own check) and the classic
    ``curl ... | bash`` one-shot bootstrap shape built on top of it.
    """
    domain = "raw" + "." + "githubusercontent" + "." + "com"
    if domain in text:
        return True
    if "curl" in text and "| bash" in text and "/app/deploy/setup.sh" in text and domain in text:
        return True
    return False


def test_detection_helper_self_test_is_clean() -> None:
    """The helper itself must not trip on its own source (no literal domain)."""
    assert not contains_anonymous_raw_dependency(
        Path(__file__).read_text(encoding="utf-8")
    )


# ---------------------------------------------------------------------------
# Case 8: non-vacuity — prove the detector actually catches the pattern it
# exists to forbid, using a synthetic snippet that mirrors the exact one-liner
# this cutover removed from app/deploy/setup.sh's header comment.
# ---------------------------------------------------------------------------

def test_detection_helper_flags_reintroduced_curl_raw_pattern() -> None:
    synthetic = (
        "# One-shot from a clean droplet:\n"
        "#   curl -fsSL https://" + "raw" + "." + "githubusercontent" + "." + "com"
        + "/mastermindx-market-intelligence/macro/main/app/deploy/setup.sh | bash\n"
    )
    assert contains_anonymous_raw_dependency(synthetic)


def test_detection_helper_flags_bare_domain_anywhere() -> None:
    synthetic = "see " + "raw" + "." + "githubusercontent" + "." + "com" + " for details"
    assert contains_anonymous_raw_dependency(synthetic)


def test_detection_helper_passes_governed_ssh_bootstrap() -> None:
    synthetic = (
        "install -m 0600 <key> /root/.ssh/macro_ro_selfupdate && "
        "git -c core.sshCommand='ssh -i /root/.ssh/macro_ro_selfupdate "
        "-o IdentitiesOnly=yes' clone --depth 1 "
        "git@github.com:mastermindx-market-intelligence/macro.git /opt/macro "
        "&& bash /opt/macro/app/deploy/setup.sh"
    )
    assert not contains_anonymous_raw_dependency(synthetic)


# ---------------------------------------------------------------------------
# Case 1 + 2: setup.sh carries no anonymous acquisition path at all.
# ---------------------------------------------------------------------------

def test_setup_sh_has_no_raw_githubusercontent_reference() -> None:
    text = SETUP_SH.read_text(encoding="utf-8")
    assert not contains_anonymous_raw_dependency(text)


def test_setup_sh_has_no_anonymous_https_clone_url() -> None:
    text = SETUP_SH.read_text(encoding="utf-8")
    assert "https://github.com/mastermindx-market-intelligence/macro.git" not in text
    # No standalone REPO_URL constant pointed at an unauthenticated clone either.
    assert "REPO_URL=" not in text


# ---------------------------------------------------------------------------
# Case 3: bootstrap_repo.sh shape.
# ---------------------------------------------------------------------------

def test_bootstrap_repo_sh_exists_and_is_executable_shebanged() -> None:
    assert BOOTSTRAP_SH.exists(), "app/deploy/bootstrap_repo.sh must exist"
    text = BOOTSTRAP_SH.read_text(encoding="utf-8")
    assert text.startswith("#!/usr/bin/env bash\n")


def test_bootstrap_repo_sh_sets_strict_mode() -> None:
    text = BOOTSTRAP_SH.read_text(encoding="utf-8")
    assert "set -euo pipefail" in text


def test_bootstrap_repo_sh_ssh_command_has_identities_only() -> None:
    text = BOOTSTRAP_SH.read_text(encoding="utf-8")
    assert "IdentitiesOnly=yes" in text
    # It must be part of the actual ssh command construction, not just a
    # comment referencing it.
    assert "MACRO_SSH_COMMAND=" in text
    ssh_line = next(
        line for line in text.splitlines() if line.strip().startswith("MACRO_SSH_COMMAND=")
    )
    assert "IdentitiesOnly=yes" in ssh_line
    assert ssh_line.strip().startswith("MACRO_SSH_COMMAND=\"ssh ")


# ---------------------------------------------------------------------------
# Case 4: core.sshCommand persistence (survives update.sh's `git reset --hard`).
# ---------------------------------------------------------------------------

def test_bootstrap_repo_sh_persists_ssh_command_into_target_checkout() -> None:
    text = BOOTSTRAP_SH.read_text(encoding="utf-8")
    assert 'git -C "$TARGET" config core.sshCommand "$MACRO_SSH_COMMAND"' in text
    # Persisted on BOTH the converge-existing-checkout path and the fresh-clone
    # path — count occurrences rather than trusting a single line.
    assert (
        text.count('git -C "$TARGET" config core.sshCommand "$MACRO_SSH_COMMAND"') >= 2
    )


# ---------------------------------------------------------------------------
# Case 5: fails closed when the SSH form is configured and the key is missing.
# Driven directly with env vars pointed at tmp_path — no network access.
# ---------------------------------------------------------------------------

def test_bootstrap_repo_sh_guard_block_exists_in_source() -> None:
    text = BOOTSTRAP_SH.read_text(encoding="utf-8")
    assert "MACRO_DEPLOY_KEY" in text
    assert "-f \"$MACRO_DEPLOY_KEY\"" in text or "! -f \"$MACRO_DEPLOY_KEY\"" in text
    assert "exit 1" in text


def test_bootstrap_repo_sh_exits_nonzero_when_ssh_key_missing(tmp_path) -> None:
    target = tmp_path / "opt_macro"
    missing_key = tmp_path / "no-such-key"
    assert not missing_key.exists()
    result = subprocess.run(
        ["bash", str(BOOTSTRAP_SH), str(target)],
        env={
            "PATH": "/usr/bin:/bin:/usr/local/bin",
            "MACRO_REPO_URL": "git@github.com:mastermindx-market-intelligence/macro.git",
            "MACRO_DEPLOY_KEY": str(missing_key),
            "MACRO_APP_DIR": str(target),
        },
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode != 0
    assert not target.exists()
    combined = result.stdout + result.stderr
    assert "macro_ro_selfupdate" in combined or str(missing_key) in combined


def test_bootstrap_repo_sh_guard_is_ssh_form_only_in_source() -> None:
    """The missing-key guard is scoped to SSH-form remotes only (``git@``/
    ``ssh://``) — an HTTPS remote never requires the deploy key file. Asserted
    from source rather than by driving a real clone, so this stays fully
    network-free (an HTTPS run would otherwise attempt an actual clone)."""
    text = BOOTSTRAP_SH.read_text(encoding="utf-8")
    assert "git@*|ssh://*" in text or ("git@*" in text and "ssh://*" in text)


# ---------------------------------------------------------------------------
# Case 6: GIT_TERMINAL_PROMPT=0 — no credential prompt on a headless box.
# ---------------------------------------------------------------------------

def test_bootstrap_repo_sh_disables_terminal_prompt() -> None:
    text = BOOTSTRAP_SH.read_text(encoding="utf-8")
    assert "GIT_TERMINAL_PROMPT=0" in text
    assert "export GIT_TERMINAL_PROMPT=0" in text


# ---------------------------------------------------------------------------
# Case 7: the Prophet option-shadow lifecycle builder has no anonymous leg.
# ---------------------------------------------------------------------------

def test_option_shadow_lifecycle_has_no_raw_githubusercontent_reference() -> None:
    text = OPTION_SHADOW_PY.read_text(encoding="utf-8")
    assert not contains_anonymous_raw_dependency(text)


def test_option_shadow_lifecycle_has_no_raw_template_symbol() -> None:
    text = OPTION_SHADOW_PY.read_text(encoding="utf-8")
    assert "CANONICAL_LEDGER_RAW_TEMPLATE" not in text


def test_option_shadow_lifecycle_module_imports_cleanly() -> None:
    """Import-level proof that removing the raw-HTTPS leg did not break the
    module (NameError on a stray reference to the deleted symbol would only
    surface at import/call time, not at grep time)."""
    sys.path.insert(0, str(ROOT))
    try:
        import importlib

        module = importlib.import_module("scripts.build_prophet_option_shadow_lifecycle")
        importlib.reload(module)
        assert not hasattr(module, "CANONICAL_LEDGER_RAW_TEMPLATE")
        assert not hasattr(module, "CANONICAL_LEDGER_GIT_REMOTE")
        assert callable(module.prophet_canonical_git.read_canonical_blob)
    finally:
        if str(ROOT) in sys.path:
            sys.path.remove(str(ROOT))


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
