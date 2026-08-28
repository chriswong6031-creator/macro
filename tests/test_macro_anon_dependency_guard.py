"""Self-tests for the anonymous canonical-Macro dependency fence
(``scripts/check_macro_anon_dependency.py``, B1 Day-6 AMENDMENT clause E).

The fence exists so a future PR cannot silently reintroduce a data
dependency on the macro repo's anonymous GitHub distribution surfaces
(``raw.githubusercontent.com``, the ``<owner>.github.io`` Pages mirror,
``cdn.jsdelivr.net/gh``, ``api.github.com/repos/.../contents``, or a bare
``https://github.com/<owner>/macro`` clone/fetch/ls-remote target) now that
the repo is private. These tests exercise the detector directly against
synthetic strings (NON-VACUITY: one per banned shape), confirm it leaves
unrelated third-party GitHub URLs alone (PRECISION), prove it catches a
constant-plus-join construction a line-local grep would miss
(MULTILINE/ASSEMBLED), and exercise the allowlist contract.

Run: python -m pytest tests/test_macro_anon_dependency_guard.py -q
"""
from __future__ import annotations

import json
import os
import plistlib
import re
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import macro_machine_git
from scripts.check_macro_anon_dependency import (
    REPO_ROOT,
    _load_allowlist,
    _walk,
    find_anonymous_macro_dependencies,
)

OWNER = "mastermindx-market-intelligence"
ALT_OWNER = "chriswong6031-creator"


def _shapes(findings) -> set[str]:
    return {f.shape for f in findings}


# ---------------------------------------------------------------------------
# NON-VACUITY — one synthetic case per banned shape, each must be flagged.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "label, snippet",
    [
        (
            "raw_githubusercontent",
            f'URL = "https://raw.githubusercontent.com/{OWNER}/macro/main/data/prophet/ledger.jsonl"\n',
        ),
        (
            "github_pages_mirror",
            f'MIRROR = "https://{OWNER}.github.io/macro/flow/index.json"\n',
        ),
        (
            "jsdelivr_gh",
            f'CDN = "https://cdn.jsdelivr.net/gh/{OWNER}/macro@main/site/index.json"\n',
        ),
        (
            "clone_fetch_target",
            f'ORIGIN = "https://github.com/{OWNER}/macro.git"\n',
        ),
        (
            "api_contents_read",
            f'API = "https://api.github.com/repos/{OWNER}/macro/contents/data/prophet/ledger.jsonl"\n',
        ),
    ],
)
def test_each_banned_shape_is_flagged(label, snippet) -> None:
    findings = find_anonymous_macro_dependencies(snippet, "synthetic.py")
    assert label in _shapes(findings), (
        f"shape {label!r} not flagged for input:\n{snippet}\nfindings={findings}"
    )


def test_alias_owner_is_also_flagged() -> None:
    """chriswong6031-creator is the pre-rename alias for the same project."""
    findings = find_anonymous_macro_dependencies(
        f'URL = "https://raw.githubusercontent.com/{ALT_OWNER}/macro/main/x.json"\n',
        "synthetic.py",
    )
    assert "raw_githubusercontent" in _shapes(findings)


def test_git_clone_subprocess_call_is_flagged() -> None:
    """shape 4 via subprocess argv, not just a bare string literal."""
    src = (
        "import subprocess\n"
        f'REMOTE = "https://github.com/{OWNER}/macro.git"\n'
        "def clone():\n"
        "    subprocess.run(['git', 'clone', '--depth', '1', REMOTE, '/tmp/x'])\n"
    )
    findings = find_anonymous_macro_dependencies(src, "synthetic.py")
    assert "clone_fetch_target" in _shapes(findings)


# ---------------------------------------------------------------------------
# PRECISION — unrelated third-party GitHub URLs must never be flagged.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "snippet",
    [
        'FONTS = "https://raw.githubusercontent.com/google/fonts/main/ofl/inter/Inter.ttf"\n',
        'CSV_URL = "https://raw.githubusercontent.com/fja05680/sp500/master/sp500_ticker_start_end.csv"\n',
        'ICON = "https://cdn.jsdelivr.net/gh/nvstly/icons@main/ticker_icons/{ticker}.png"\n',
        'SB_JS = "https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2/dist/umd/supabase.js"\n',
        'URL = f"https://api.github.com/repos/{repo}/contents/site/prophet/index.json"\n',
        'PR = "https://github.com/mastermindx-market-intelligence/macro/pull/5660"\n',
        'BLOB = "https://github.com/mastermindx-market-intelligence/macro/blob/main/engine/x.py"\n',
        'CMP = "https://github.com/mastermindx-market-intelligence/macro/compare/a...b"\n',
        'CMT = "https://github.com/mastermindx-market-intelligence/macro/commit/deadbeef"\n',
    ],
)
def test_third_party_and_citation_urls_are_never_flagged(snippet) -> None:
    findings = find_anonymous_macro_dependencies(snippet, "synthetic.py")
    assert findings == [], f"false positive on lawful URL:\n{snippet}\nfindings={findings}"


# github.com serves BYTES on four sub-paths. A repo-root-only rule (shape 4)
# leaves every one of them open, and each is a complete anonymous read of
# premium content — the tarball is the WHOLE TREE.
@pytest.mark.parametrize(
    "snippet",
    [
        'TAR = "https://github.com/mastermindx-market-intelligence/macro/archive/refs/heads/main.tar.gz"\n',
        'ZIP = "https://github.com/chriswong6031-creator/macro/archive/main.zip"\n',
        'RAW = "https://github.com/mastermindx-market-intelligence/macro/raw/main/site/prophet/index.json"\n',
        'REL = "https://github.com/mastermindx-market-intelligence/macro/releases/download/v1/book.json"\n',
        'BLB = "https://github.com/mastermindx-market-intelligence/macro/blob/main/site/prophet/index.json?raw=1"\n',
    ],
)
def test_github_com_byte_serving_subpaths_are_flagged(snippet) -> None:
    findings = find_anonymous_macro_dependencies(snippet, "synthetic.py")
    assert findings, f"MISSED an anonymous download path:\n{snippet}"


def test_unrelated_repo_under_the_same_owner_is_not_flagged() -> None:
    """The fence is keyed on owner+macro, not the owner alone."""
    findings = find_anonymous_macro_dependencies(
        f'URL = "https://raw.githubusercontent.com/{OWNER}/mastermind-terminal/main/x.json"\n',
        "synthetic.py",
    )
    assert findings == []


# ---------------------------------------------------------------------------
# MULTILINE / ASSEMBLED — a line-local grep misses this; the fence must not.
# ---------------------------------------------------------------------------
def test_module_constant_joined_with_a_path_at_the_call_site_is_flagged() -> None:
    src = (
        "from __future__ import annotations\n"
        "\n"
        "#: base host+owner+repo prefix, joined with a commit path far below.\n"
        f'CANONICAL_LEDGER_RAW_TEMPLATE = "https://raw.githubusercontent.com/{OWNER}/macro/"\n'
        "\n"
        "\n"
        "def _fetch_ledger_at(commit: str) -> str:\n"
        '    return CANONICAL_LEDGER_RAW_TEMPLATE + commit + "/data/prophet/ledger.jsonl"\n'
    )
    findings = find_anonymous_macro_dependencies(src, "synthetic_multiline.py")
    assert "raw_githubusercontent" in _shapes(findings), (
        "a module constant carrying the banned prefix, joined with a path "
        f"variable elsewhere in the file, must still be caught: {findings}"
    )
    # And it must be pinned to the CONSTANT's own line, not the join site —
    # proving this is a whole-file text scan, not a same-line grep.
    hit = next(f for f in findings if f.shape == "raw_githubusercontent")
    assert hit.line == 4


def test_bare_line_local_grep_would_have_missed_the_split_construction() -> None:
    """Sanity check on the test above: confirm the two halves never sit on
    one line, so a naive same-line regex genuinely could not have caught it."""
    src = (
        f'CANONICAL_LEDGER_RAW_TEMPLATE = "https://raw.githubusercontent.com/{OWNER}/macro/"\n'
        "def _fetch_ledger_at(commit):\n"
        '    return CANONICAL_LEDGER_RAW_TEMPLATE + commit\n'
    )
    lines = src.splitlines()
    assert not any("commit" in ln and "raw.githubusercontent.com" in ln for ln in lines)


# ---------------------------------------------------------------------------
# ALLOWLIST — reported as an exception, never silently skipped; a
# non-allowlisted sibling in the same walk still fails.
# ---------------------------------------------------------------------------
def test_allowlisted_path_is_reported_but_not_blocking(tmp_path: Path) -> None:
    root = tmp_path
    (root / "config").mkdir()
    (root / "scripts").mkdir()

    allowlisted_file = root / "config" / "audited_catalog.json"
    allowlisted_file.write_text(
        json.dumps({"legacy_url": f"https://raw.githubusercontent.com/{OWNER}/macro/main/x.json"}),
        encoding="utf-8",
    )
    sibling_file = root / "scripts" / "still_anonymous.py"
    sibling_file.write_text(
        f'URL = "https://raw.githubusercontent.com/{OWNER}/macro/main/y.json"\n',
        encoding="utf-8",
    )

    allowlist_path = root / "config" / "macro_anon_dependency_allowlist.json"
    allowlist_path.write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "path": "config/audited_catalog.json",
                        "reason": "test fixture — pre-migration audit catalog",
                        "reviewed_by": "test",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    allowlist = _load_allowlist(root)
    findings = _walk(root, allowlist)

    by_path = {f.path: f for f in findings}
    assert by_path["config/audited_catalog.json"].allowlisted is True
    assert by_path["config/audited_catalog.json"].reason
    assert by_path["scripts/still_anonymous.py"].allowlisted is False

    blocking = [f for f in findings if not f.allowlisted]
    assert len(blocking) == 1
    assert blocking[0].path == "scripts/still_anonymous.py"


def test_allowlist_file_documents_clean_deploy_scripts_and_the_finished_ledger_label() -> None:
    """DEC:B1-CUTOVER-HARDENING — the premise this test originally pinned has
    changed. It used to assert all three of app/deploy/setup.sh,
    app/deploy/bootstrap_repo.sh, and scripts/build_prophet_option_shadow_lifecycle.py
    were absent from the allowlist, because all three still carried a live
    anonymous fetch leg a parallel builder was actively de-anonymizing —
    allowlisting any of them then would have hidden a regression in that work
    rather than surfaced it.

    scripts/build_prophet_option_shadow_lifecycle.py's migration is now
    COMPLETE: its anonymous `git ls-remote`/`curl raw.githubusercontent.com`
    fetch legs were removed and replaced with reads through the local
    checkout's own authenticated origin remote. The only remaining flagged
    string in that file is CANONICAL_LEDGER_REPOSITORY, a display-only
    `source_repository` provenance IDENTITY label recorded on a receipt — it
    is correctly allowlisted now, not a hidden regression. Deleting this
    protection outright would lose real coverage, so it is updated to pin the
    NEW truth instead:
      * app/deploy/setup.sh and app/deploy/bootstrap_repo.sh must stay ABSENT
        from the allowlist and CLEAN of any fetch-leg string — those are true
        acquisition code paths and must never be excused.
      * scripts/build_prophet_option_shadow_lifecycle.py must be PRESENT,
        with a reason that actually says "display-only"/"no network use" (not
        merely present with an empty or unrelated justification, which would
        let a future entry smuggle in a real fetch leg under this same path).
      * That file must still contain no raw.githubusercontent.com / other
        fetch-leg string — the allowlisted entry covers an identity label,
        never a live fetch, so a reintroduced fetch leg must still be caught
        by the plain text/AST scan regardless of the allowlist.
    """
    allowlist_path = REPO_ROOT / "config" / "macro_anon_dependency_allowlist.json"
    allowlist = json.loads(allowlist_path.read_text(encoding="utf-8"))
    entries_by_path = {e["path"]: e for e in allowlist.get("entries", [])}

    # Deploy acquisition scripts: still absent, still must never be excused.
    clean_only = {"app/deploy/setup.sh", "app/deploy/bootstrap_repo.sh"}
    assert not (set(entries_by_path) & clean_only), (
        f"forbidden path allowlisted: {set(entries_by_path) & clean_only}"
    )
    for rel in clean_only:
        text = (REPO_ROOT / rel).read_text(encoding="utf-8")
        assert "raw.githubusercontent.com" not in text
        assert "https://github.com/mastermindx-market-intelligence/macro.git" not in text

    # The finished ledger-provenance label: present, and its reason actually
    # says what makes the exception safe — not just present with a blank or
    # unrelated justification.
    shadow_path = "scripts/build_prophet_option_shadow_lifecycle.py"
    assert shadow_path in entries_by_path, (
        f"{shadow_path}'s migration is complete; its remaining display-only "
        "provenance label must be an allowlisted notice, not an unexplained gap"
    )
    reason = entries_by_path[shadow_path]["reason"].lower()
    assert "display-only" in reason or "no network use" in reason
    assert "provenance" in reason or "identity" in reason

    # The allowlisted entry must never be able to cover a REAL fetch leg: the
    # file itself must still carry none, allowlist or no allowlist.
    shadow_text = (REPO_ROOT / shadow_path).read_text(encoding="utf-8")
    assert "raw.githubusercontent.com" not in shadow_text
    assert "CANONICAL_LEDGER_RAW_TEMPLATE" not in shadow_text


# ---------------------------------------------------------------------------
# Scope exclusions — a guard's own tests/docs must be free to NAME the
# banned strings without becoming a finding themselves.
# ---------------------------------------------------------------------------
def test_scope_excludes_tests_and_md_and_worktrees(tmp_path: Path) -> None:
    root = tmp_path
    for rel in (
        "tests/test_something.py",
        "docs/NOTES.md",
        "research/SOMETHING.md",
        ".claude/worktrees/sess/scripts/x.py",
        # All four documented fleet session-worktree roots (CLAUDE.md "Worktree
        # GC"). `.codex-worktrees/` is the one that a `part == "worktrees"`
        # equality test silently MISSES — it is a single path component — so a
        # sibling session's checkout would be scanned and this guard would fail
        # on code the current tree does not contain.
        ".claire/worktrees/sess/scripts/x.py",
        ".codex/worktrees/sess/scripts/x.py",
        ".codex-worktrees/sess/scripts/x.py",
    ):
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            f'URL = "https://raw.githubusercontent.com/{OWNER}/macro/main/x.json"\n',
            encoding="utf-8",
        )
    findings = _walk(root, {})
    assert findings == [], f"scope exclusion failed: {findings}"


def test_scope_exclusion_is_not_vacuous(tmp_path: Path) -> None:
    """The exclusion test above only means something if an ORDINARY path with the
    same content IS flagged — otherwise it would pass with a detector that finds
    nothing at all."""
    p = tmp_path / "scripts" / "x.py"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        f'URL = "https://raw.githubusercontent.com/{OWNER}/macro/main/x.json"\n',
        encoding="utf-8",
    )
    assert _walk(tmp_path, {}), "detector found nothing on a non-excluded path"


# ---------------------------------------------------------------------------
# main() exit-code contract, exercised as a subprocess so it also proves the
# CLI (``--root``) works end to end.
# ---------------------------------------------------------------------------
def test_main_exits_zero_on_a_clean_synthetic_tree(tmp_path: Path) -> None:
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "clean.py").write_text(
        'FONTS = "https://raw.githubusercontent.com/google/fonts/main/x.ttf"\n',
        encoding="utf-8",
    )
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "check_macro_anon_dependency.py"), "--root", str(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_main_exits_nonzero_and_annotates_on_a_planted_offender(tmp_path: Path) -> None:
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "dirty.py").write_text(
        f'URL = "https://raw.githubusercontent.com/{OWNER}/macro/main/x.json"\n',
        encoding="utf-8",
    )
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "check_macro_anon_dependency.py"), "--root", str(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1, result.stdout + result.stderr
    assert result.stdout.startswith("::error") or "\n::error" in result.stdout
    for line in result.stdout.splitlines():
        if "::" in line:
            assert line.startswith("::"), f"annotation did not start the line: {line!r}"


# ---------------------------------------------------------------------------
# M1 publisher machine-Git seam — the two pre-existing host writers must use
# one explicit write-capable deploy key after the canonical repo goes private.
# ---------------------------------------------------------------------------
def test_machine_git_key_is_owner_only_under_private_root(monkeypatch, tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir(mode=0o700)
    private_root = home / ".ssh"
    private_root.mkdir(mode=0o700)
    key = private_root / "macro-publisher"
    key.write_text("fixture-key-material", encoding="utf-8")
    key.chmod(0o600)

    monkeypatch.setattr(macro_machine_git, "_process_home", lambda: home)
    monkeypatch.setenv(macro_machine_git.MACHINE_GIT_KEY_ENV, str(key))
    assert macro_machine_git._deploy_key() == key.resolve()

    os.link(key, private_root / "macro-publisher-alias")
    with pytest.raises(macro_machine_git.MachineGitError, match="filesystem aliases"):
        macro_machine_git._deploy_key()


def test_machine_git_environment_has_no_ambient_auth_or_user_config(
    monkeypatch,
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    key = home / ".ssh" / "machine key"
    key.parent.mkdir(parents=True, mode=0o700)
    key.write_text("fixture-key-material", encoding="utf-8")
    key.chmod(0o600)
    monkeypatch.setattr(macro_machine_git, "_process_home", lambda: home)
    monkeypatch.setenv("SSH_AUTH_SOCK", "/tmp/human-agent.sock")
    monkeypatch.setenv("GIT_ASKPASS", "/tmp/human-askpass")
    monkeypatch.setenv("GIT_CONFIG_COUNT", "99")

    environment = macro_machine_git._git_environment(key)

    assert set(environment) == {
        "PATH",
        "HOME",
        "LANG",
        "LC_ALL",
        "GIT_CONFIG_GLOBAL",
        "GIT_CONFIG_SYSTEM",
        "GIT_CONFIG_NOSYSTEM",
        "GIT_TERMINAL_PROMPT",
        "GCM_INTERACTIVE",
        "GIT_SSH_COMMAND",
        "GIT_SSH_VARIANT",
        "GIT_CONFIG_COUNT",
        "GIT_CONFIG_KEY_0",
        "GIT_CONFIG_VALUE_0",
    }
    assert environment["GIT_CONFIG_GLOBAL"] == "/dev/null"
    assert environment["GIT_CONFIG_SYSTEM"] == "/dev/null"
    assert environment["GIT_TERMINAL_PROMPT"] == "0"
    assert environment["GCM_INTERACTIVE"] == "never"
    assert environment["GIT_CONFIG_COUNT"] == "1"
    assert environment["GIT_CONFIG_KEY_0"] == "core.hooksPath"
    assert environment["GIT_CONFIG_VALUE_0"] == "/dev/null"
    assert "SSH_AUTH_SOCK" not in environment
    assert "GIT_ASKPASS" not in environment
    ssh_command = environment["GIT_SSH_COMMAND"]
    assert ssh_command.startswith("/usr/bin/ssh -F /dev/null -i ")
    assert "-o BatchMode=yes" in ssh_command
    assert "-o IdentitiesOnly=yes" in ssh_command
    assert "-o IdentityAgent=none" in ssh_command
    assert "-o StrictHostKeyChecking=yes" in ssh_command


def test_machine_git_refuses_ambient_remote_names_and_other_urls() -> None:
    macro_machine_git._validate_repository_arguments(
        ["ls-remote", macro_machine_git.CANONICAL_REPOSITORY_SSH, "refs/heads/main"]
    )
    macro_machine_git._validate_repository_arguments(
        ["fetch", *macro_machine_git._CANONICAL_FETCH]
    )
    macro_machine_git._validate_repository_arguments(
        ["push", *macro_machine_git._CANONICAL_PUSH]
    )
    macro_machine_git._validate_repository_arguments(
        ["push", "--dry-run", *macro_machine_git._CANONICAL_PUSH]
    )
    with pytest.raises(macro_machine_git.MachineGitError, match="literal repository"):
        macro_machine_git._validate_repository_arguments(["fetch", "origin", "main"])
    with pytest.raises(macro_machine_git.MachineGitError, match="non-canonical"):
        macro_machine_git._validate_repository_arguments(
            ["clone", "https://github.com/mastermindx-market-intelligence/macro.git"]
        )
    with pytest.raises(macro_machine_git.MachineGitError, match="non-canonical"):
        macro_machine_git._validate_repository_arguments(
            ["push", "git@github.com:someone-else/macro.git", "HEAD:main"]
        )
    with pytest.raises(macro_machine_git.MachineGitError, match="non-canonical"):
        macro_machine_git._validate_repository_arguments(
            ["push", "git@evil.invalid:other.git", "HEAD:refs/heads/main"]
        )
    with pytest.raises(macro_machine_git.MachineGitError, match="clone contract"):
        macro_machine_git._validate_repository_arguments(
            [
                "clone",
                "--depth",
                "1",
                "--filter=blob:none",
                "--sparse",
                "/tmp/local-macro",
                "/tmp/destination",
            ]
        )
    with pytest.raises(macro_machine_git.MachineGitError, match="push contract"):
        macro_machine_git._validate_repository_arguments(
            [
                "push",
                macro_machine_git.CANONICAL_REPOSITORY_SSH,
                "HEAD:refs/heads/other",
            ]
        )
    with pytest.raises(macro_machine_git.MachineGitError, match="fetch contract"):
        macro_machine_git._validate_repository_arguments(
            [
                "fetch",
                "--no-tags",
                "--depth",
                "1",
                macro_machine_git.CANONICAL_REPOSITORY_SSH,
                "+refs/heads/main:refs/remotes/origin/main",
            ]
        )
    with pytest.raises(macro_machine_git.MachineGitError, match="push contract"):
        macro_machine_git._validate_repository_arguments(
            [
                "push",
                macro_machine_git.CANONICAL_REPOSITORY_SSH,
                "HEAD:refs/heads/main",
            ]
        )
    with pytest.raises(macro_machine_git.MachineGitError, match="command-line configuration"):
        macro_machine_git._validate_repository_arguments(
            ["-c", "url.ssh://attacker.invalid/.insteadOf=git@github.com:", "fetch"]
        )
    with pytest.raises(macro_machine_git.MachineGitError, match="environment-backed"):
        macro_machine_git._validate_repository_arguments(
            ["--config-env=url.ssh://attacker.invalid/.insteadOf=POISON", "fetch"]
        )
    macro_machine_git._validate_repository_arguments(
        [
            "-c",
            "user.name=dashboard-bot",
            "-c",
            "user.email=actions@users.noreply.github.com",
            "commit",
        ]
    )


def _canonical_sparse_config_fixture(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    repo = tmp_path / "push-repo"
    subprocess.run(["git", "init", "-b", "main", str(repo)], check=True, capture_output=True)
    for key, value in macro_machine_git._CANONICAL_LOCAL_CONFIG.items():
        subprocess.run(
            ["git", "-C", str(repo), "config", "--local", key, value],
            check=True,
            capture_output=True,
        )
    for key, value in macro_machine_git._CANONICAL_WORKTREE_CONFIG.items():
        subprocess.run(
            ["git", "-C", str(repo), "config", "--worktree", key, value],
            check=True,
            capture_output=True,
        )
    environment = {
        "PATH": "/usr/bin:/bin",
        "HOME": str(tmp_path),
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_SYSTEM": "/dev/null",
        "GIT_CONFIG_NOSYSTEM": "1",
    }
    macro_machine_git._refuse_unsafe_local_configuration(repo, environment)
    return repo, environment


@pytest.mark.parametrize(
    "scope,key,value",
    [
        (scope, key, value)
        for scope in ("--local", "--worktree")
        for key, value in (
            (
                "url.ssh://attacker.invalid/.insteadOf",
                macro_machine_git.CANONICAL_REPOSITORY_SSH,
            ),
            ("fetch.recurseSubmodules", "on-demand"),
            ("push.recurseSubmodules", "on-demand"),
            ("submodule.payload.url", "git@evil.invalid:payload.git"),
            ("core.fsmonitor", "/tmp/attacker-fsmonitor"),
            ("diff.external", "/tmp/attacker-diff"),
            ("diff.trustExitCode", "true"),
            ("diff.payload.command", "/tmp/attacker-command"),
            ("diff.payload.textconv", "/tmp/attacker-textconv"),
            ("filter.payload.clean", "/tmp/attacker-clean"),
            ("filter.payload.smudge", "/tmp/attacker-smudge"),
            ("filter.payload.process", "/tmp/attacker-process"),
        )
    ],
)
def test_machine_git_refuses_every_unknown_local_or_worktree_config(
    tmp_path: Path,
    scope: str,
    key: str,
    value: str,
) -> None:
    repo, environment = _canonical_sparse_config_fixture(tmp_path)
    subprocess.run(
        ["git", "-C", str(repo), "config", scope, key, value],
        check=True,
        capture_output=True,
    )
    with pytest.raises(macro_machine_git.MachineGitError, match="canonical sparse-clone schema"):
        macro_machine_git._refuse_unsafe_local_configuration(repo, environment)


def test_machine_git_blocks_external_diff_that_hides_a_staged_change(tmp_path: Path) -> None:
    repo, environment = _canonical_sparse_config_fixture(tmp_path)
    tracked = repo / "artifact.json"
    tracked.write_text('{"state":"old"}\n', encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "artifact.json"], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "-c",
            "user.name=fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "commit",
            "-m",
            "fixture",
        ],
        check=True,
        capture_output=True,
    )
    tracked.write_text('{"state":"new"}\n', encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "artifact.json"], check=True)
    honest = subprocess.run(
        ["git", "-C", str(repo), "diff", "--cached", "--quiet", "--", "artifact.json"],
        check=False,
    )
    assert honest.returncode == 1, "fixture must contain a real staged change"

    quiet_diff = tmp_path / "quiet-diff.sh"
    quiet_diff.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    quiet_diff.chmod(0o700)
    subprocess.run(
        ["git", "-C", str(repo), "config", "--local", "diff.external", str(quiet_diff)],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(repo), "config", "--local", "diff.trustExitCode", "true"],
        check=True,
    )
    poisoned = subprocess.run(
        ["git", "-C", str(repo), "diff", "--cached", "--quiet", "--", "artifact.json"],
        check=False,
    )
    assert poisoned.returncode in {0, 1}
    if poisoned.returncode == 1:
        # Git 2.43 (Ubuntu 24.04, including the sealed PC runners) records
        # diff.trustExitCode but does not yet let that setting override the
        # --quiet staged-diff result.  The configuration is still forbidden:
        # upgrading Git must not silently turn an accepted repository into the
        # demonstrated return-0 bypass used by newer clients.
        configured = subprocess.run(
            ["git", "-C", str(repo), "config", "--local", "--get", "diff.trustExitCode"],
            check=True,
            capture_output=True,
            text=True,
        )
        assert configured.stdout.strip() == "true"

    with pytest.raises(macro_machine_git.MachineGitError, match="canonical sparse-clone schema"):
        macro_machine_git._refuse_unsafe_local_configuration(repo, environment)


@pytest.mark.parametrize(
    "runner_name",
    ["run_index_gex_history.sh", "run_theme_options_witness.sh"],
)
def test_m1_publishers_use_only_the_private_safe_machine_git_seam(runner_name: str) -> None:
    text = (REPO_ROOT / "ops" / "launchd" / runner_name).read_text(encoding="utf-8")
    executable_lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    assert 'REMOTE_URL="git@github.com:mastermindx-market-intelligence/macro.git"' in text
    assert "MACRO_PUBLISH_GIT_SSH_KEY is required" in text
    assert 'MACHINE_GIT="$RUNTIME/scripts/macro_machine_git.py"' in text
    assert 'export PYTHONPATH="$REPO"' in text
    assert "https://github.com/mastermindx-market-intelligence/macro.git" not in text
    assert not any(line == "git" or line.startswith("git ") for line in executable_lines)
    assert not any("$(git " in line for line in executable_lines)
    assert " push origin " not in text
    assert 'fetch --no-tags --no-recurse-submodules --depth 1 "$REMOTE_URL"' in text
    assert 'push --recurse-submodules=no "$REMOTE_URL" HEAD:refs/heads/main' in text
    post_source_manual_binding = (
        "/Users/chriswong/macro-publisher-runtime/ops/launchd/run_with_env.sh \\\n"
        "#     /Users/chriswong/flow-ops-wt/.env \\\n"
        "#     /usr/bin/env \\\n"
        "#     MACRO_PUBLISH_GIT_SSH_KEY=/Users/chriswong/.ssh/macro_dashboard_deploy \\\n"
        "#     PYTHONPATH=/Users/chriswong/flow-ops-wt \\\n"
        "#     /bin/sh \\\n"
        f"#     /Users/chriswong/macro-publisher-runtime/ops/launchd/{runner_name}"
    )
    assert post_source_manual_binding in text


@pytest.mark.parametrize(
    "plist_name,runner_name",
    [
        ("com.macro.indexgexhistory.plist", "run_index_gex_history.sh"),
        ("com.macro.theme-options-witness.plist", "run_theme_options_witness.sh"),
    ],
)
def test_m1_publisher_launch_contract_separates_current_launcher_from_pinned_engine(
    plist_name: str,
    runner_name: str,
) -> None:
    # The production plists contain legacy comments that macOS plutil accepts,
    # including long separator runs that strict cross-platform XML parsers
    # reject as invalid ``--`` comment bodies.  Comments are not plist data:
    # remove them permissively, parse the actual dictionary with the stdlib,
    # and retain native ``plutil -lint`` as a separate macOS acceptance check.
    plist_text = (REPO_ROOT / "ops" / "launchd" / plist_name).read_text(
        encoding="utf-8"
    )
    plist_without_comments = re.sub(r"<!--.*?-->", "", plist_text, flags=re.DOTALL)
    payload = plistlib.loads(plist_without_comments.encode("utf-8"))
    assert payload["ProgramArguments"] == [
        "/Users/chriswong/macro-publisher-runtime/ops/launchd/run_with_env.sh",
        "/Users/chriswong/flow-ops-wt/.env",
        "/usr/bin/env",
        "MACRO_PUBLISH_GIT_SSH_KEY=/Users/chriswong/.ssh/macro_dashboard_deploy",
        "PYTHONPATH=/Users/chriswong/flow-ops-wt",
        "/bin/sh",
        f"/Users/chriswong/macro-publisher-runtime/ops/launchd/{runner_name}",
    ]
    assert payload["WorkingDirectory"] == "/Users/chriswong/flow-ops-wt"
    assert "EnvironmentVariables" not in payload


def test_run_with_env_reasserts_publisher_identity_after_a_poisoned_env_file(
    tmp_path: Path,
) -> None:
    env_file = tmp_path / "publisher.env"
    env_file.write_text(
        "MACRO_PUBLISH_GIT_SSH_KEY=/tmp/stale-or-human-key\n"
        "PYTHONPATH=/tmp/stale-engine\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [
            str(REPO_ROOT / "ops" / "launchd" / "run_with_env.sh"),
            str(env_file),
            "/usr/bin/env",
            "MACRO_PUBLISH_GIT_SSH_KEY=/Users/chriswong/.ssh/macro_dashboard_deploy",
            "PYTHONPATH=/Users/chriswong/flow-ops-wt",
            "/bin/sh",
            "-c",
            'test "$MACRO_PUBLISH_GIT_SSH_KEY" = '
            "'/Users/chriswong/.ssh/macro_dashboard_deploy' && "
            'test "$PYTHONPATH" = "/Users/chriswong/flow-ops-wt"',
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
