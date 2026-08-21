"""Sparse session-worktree profile — research/WORKTREE_GC_POLICY.md §0 R8.

These tests run identically in a sparse session worktree and in a full CI
checkout: every behavioural assertion is made against a SYNTHETIC git repo built
in tmp_path, so the ambient checkout's own sparseness never decides the verdict.
The handful of ambient assertions (config ↔ default drift, the wiring) are
tree-shape independent.

What is actually being pinned, and why each one has bitten:

  * the config's exclude list and the module's hard-coded fallback cannot drift
    — the fallback is what the WorktreeCreate hook uses when the config is
    unreadable, so a silent divergence would ship a different profile;
  * every excluded name is really tracked at HEAD — a typo excludes nothing and
    the profile quietly stops saving anything;
  * the detector answers from git's sparse state, NOT from directory presence:
    `data/` measurably survives `git reset --hard` as a 0-byte HUSK, so
    `is_dir()` reads True while the tree holds none of its 2.3 GiB;
  * `check_template_site_sync` REFUSES on a sparse tree instead of reporting
    "sync OK (0 pairs checked)" — the vacuous pass this whole change exists to
    prevent;
  * a write into an omitted tree still reaches `git status`, so ship_loop_guard's
    dirty snapshot keeps working and nothing becomes silently committable.
"""
from __future__ import annotations

import importlib.util
import io
import json
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

from scripts import worktree_sparse as WS

ROOT = Path(__file__).resolve().parents[1]
HOOK_PATH = ROOT / ".claude" / "hooks" / "worktree_create_sparse.py"
SETTINGS_PATH = ROOT / ".claude" / "settings.json"
CONFIG_PATH = ROOT / "config" / "sparse_worktree.json"
CODEX_ENVIRONMENT_PATH = ROOT / ".codex" / "environments" / "environment.toml"
CODEX_HOOKS_PATH = ROOT / ".codex" / "hooks.json"
CURSOR_HOOKS_PATH = ROOT / ".cursor" / "hooks.json"
CURSOR_WORKTREES_PATH = ROOT / ".cursor" / "worktrees.json"
GROK_HOOKS_PATH = ROOT / ".grok" / "hooks" / "sparse-worktree.json"
GROK_SESSION_START_PATH = ROOT / ".grok" / "hooks" / "session_start_sparse.py"


def _load_hook():
    spec = importlib.util.spec_from_file_location("worktree_create_sparse", HOOK_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_grok_hook():
    spec = importlib.util.spec_from_file_location(
        "session_start_sparse", GROK_SESSION_START_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(("git", "-C", str(repo)) + args,
                          capture_output=True, text=True, check=True)
    return proc.stdout.strip()


@pytest.fixture
def synthetic_repo(tmp_path: Path) -> Path:
    """A committed repo with heavy dirs, so sparseness can be exercised for real."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "t")
    for name in ("engine", "scripts", "templates", "data", "site", "mockups"):
        d = repo / name
        d.mkdir()
        (d / "keep.txt").write_text(f"{name} content\n", encoding="utf-8")
    (repo / "templates" / "asset.js").write_text("console.log(1)\n", encoding="utf-8")
    (repo / "site" / "asset.js").write_text("console.log(1)\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "base")
    return repo


def _make_sparse(repo: Path, keep: list[str]) -> None:
    _git(repo, "sparse-checkout", "init", "--cone")
    _git(repo, "sparse-checkout", "set", "--cone", "--", *keep)


# --------------------------------------------------------------------------
# Config ↔ fallback, and the R8 floor
# --------------------------------------------------------------------------

def test_config_and_module_fallback_cannot_drift():
    configured = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))["exclude_dirs"]
    assert list(WS.DEFAULT_EXCLUDE_DIRS) == configured, (
        "scripts/worktree_sparse.DEFAULT_EXCLUDE_DIRS is what the WorktreeCreate hook "
        "falls back to when config/sparse_worktree.json is unreadable — the two must match"
    )


def test_profile_excludes_at_least_the_two_dirs_policy_r8_names():
    excluded = set(WS.load_profile()["exclude_dirs"])
    assert {"data", "site"} <= excluded, "R8 names data/ and site/ as the floor"


def test_every_excluded_directory_is_actually_tracked_at_head():
    """A typo excludes nothing and the profile silently stops saving anything."""
    tracked = set(WS.tracked_top_level_dirs(ROOT))
    if not tracked:
        pytest.skip("git unavailable or HEAD unreadable")
    unknown = sorted(set(WS.load_profile()["exclude_dirs"]) - tracked)
    assert not unknown, f"config/sparse_worktree.json excludes untracked names: {unknown}"


# --------------------------------------------------------------------------
# Detection — the part that must not be a directory check
# --------------------------------------------------------------------------

def test_full_checkout_reports_nothing_missing(synthetic_repo: Path):
    assert WS.missing_dirs(synthetic_repo) == []
    assert WS.is_sparse(synthetic_repo) is False


def test_sparse_checkout_names_exactly_the_omitted_dirs(synthetic_repo: Path):
    _make_sparse(synthetic_repo, ["engine", "scripts", "templates"])
    assert WS.missing_dirs(synthetic_repo) == ["data", "mockups", "site"]
    assert WS.is_sparse(synthetic_repo) is True


def test_a_zero_byte_husk_is_still_reported_missing(synthetic_repo: Path):
    """`git reset --hard` leaves `data/` as an empty dir; is_dir() then lies True."""
    _make_sparse(synthetic_repo, ["engine", "scripts", "templates"])
    husk = synthetic_repo / "data"
    husk.mkdir(exist_ok=True)
    assert husk.is_dir(), "precondition: the husk exists on disk"
    assert "data" in WS.missing_dirs(synthetic_repo), (
        "presence-based detection would call this materialized; git's sparse state must win"
    )


def test_require_full_checkout_raises_with_the_opt_in_command(synthetic_repo: Path):
    _make_sparse(synthetic_repo, ["engine", "scripts", "templates"])
    WS.require_full_checkout(["engine"], synthetic_repo)  # present -> no raise
    with pytest.raises(RuntimeError) as excinfo:
        WS.require_full_checkout(["site", "engine"], synthetic_repo)
    assert WS.FULL_CHECKOUT_CMD in str(excinfo.value)
    assert "site" in str(excinfo.value)


def test_opt_in_restores_the_omitted_trees(synthetic_repo: Path):
    _make_sparse(synthetic_repo, ["engine", "scripts", "templates"])
    assert WS.disable_profile(synthetic_repo) == 0
    assert WS.missing_dirs(synthetic_repo) == []
    assert (synthetic_repo / "site" / "asset.js").is_file()


def test_add_materializes_one_tree_and_leaves_the_rest_sparse(synthetic_repo: Path):
    _make_sparse(synthetic_repo, ["engine", "scripts", "templates"])
    assert WS.add_dirs(["site"], synthetic_repo) == 0
    missing = WS.missing_dirs(synthetic_repo)
    assert "site" not in missing
    assert "data" in missing and "mockups" in missing


def test_apply_profile_is_reversible_and_drops_husks(synthetic_repo: Path):
    assert WS.apply_profile(synthetic_repo, exclude_dirs=["data", "site"]) == 0
    assert WS.missing_dirs(synthetic_repo) == ["data", "site"]
    assert not (synthetic_repo / "data").exists(), "husk directories are cleaned up"


def test_auto_profile_never_changes_the_primary_checkout(synthetic_repo: Path):
    assert WS.is_linked_worktree(synthetic_repo) is False
    assert WS.auto_profile(synthetic_repo, CONFIG_PATH) == 0
    assert WS.is_sparse(synthetic_repo) is False
    assert (synthetic_repo / "data" / "keep.txt").is_file()


def _session_linked(synthetic_repo: Path, tmp_path: Path, name: str) -> Path:
    """A linked worktree under a session root — the only tree ``auto`` will touch."""
    linked = tmp_path / ".claude" / "worktrees" / name
    linked.parent.mkdir(parents=True, exist_ok=True)
    _git(synthetic_repo, "worktree", "add", "-q", "--detach", str(linked), "HEAD")
    return linked


def test_auto_profile_applies_to_a_new_linked_worktree(
        synthetic_repo: Path, tmp_path: Path):
    linked = _session_linked(synthetic_repo, tmp_path, "linked")
    assert WS.is_linked_worktree(linked) is True
    assert WS.is_session_worktree(linked) is True
    assert WS.auto_profile(linked, CONFIG_PATH) == 0
    assert WS.missing_dirs(linked) == ["data", "mockups", "site"]
    assert _git(linked, "status", "--porcelain") == ""


def test_auto_profile_skips_a_linked_worktree_outside_session_roots(
        synthetic_repo: Path, tmp_path: Path):
    """macro-main is a linked worktree of the occupied primary; SessionStart must
    not sparsify it. The discriminator is the session-root path, not merely
    git-dir != common-dir.
    """
    linked = tmp_path / "macro-main-analog"
    _git(synthetic_repo, "worktree", "add", "-q", "--detach", str(linked), "HEAD")
    assert WS.is_linked_worktree(linked) is True
    assert WS.is_session_worktree(linked) is False
    assert WS.auto_profile(linked, CONFIG_PATH) == 0
    assert WS.is_sparse(linked) is False
    assert (linked / "data" / "keep.txt").is_file()


def test_auto_profile_respects_the_repo_wide_off_switch(
        synthetic_repo: Path, tmp_path: Path):
    linked = _session_linked(synthetic_repo, tmp_path, "linked-disabled")
    profile = tmp_path / "disabled.json"
    profile.write_text('{"enabled": false, "exclude_dirs": ["data", "site"]}',
                       encoding="utf-8")
    assert WS.auto_profile(linked, profile) == 0
    assert WS.is_sparse(linked) is False


def test_auto_profile_preserves_a_sessions_manual_sparse_addition(
        synthetic_repo: Path, tmp_path: Path):
    linked = _session_linked(synthetic_repo, tmp_path, "linked-custom")
    _make_sparse(linked, ["engine", "scripts", "templates", "site"])
    assert (linked / "site" / "asset.js").is_file()
    assert WS.auto_profile(linked, CONFIG_PATH) == 0
    assert (linked / "site" / "asset.js").is_file(), (
        "Codex startup must not undo an explicit `worktree_sparse.py add site` opt-in"
    )


def test_apply_profile_refuses_to_exclude_everything(synthetic_repo: Path):
    tracked = WS.tracked_top_level_dirs(synthetic_repo)
    assert WS.apply_profile(synthetic_repo, exclude_dirs=tracked) == 1


def test_clean_is_report_first_and_deletes_only_under_force(synthetic_repo: Path):
    """A stray write REPLACES a committed artifact, so this must not be a no-op.

    Measured 2026-08-13: a test suite run in a sparse tree left
    data/hk_southbound/holdings.parquet at 45,157 bytes against 7,295,941
    committed — the real content was never on disk, so the writer truncated
    rather than modified. `git add -A` there ships the truncation.
    """
    _make_sparse(synthetic_repo, ["engine", "scripts", "templates"])
    (synthetic_repo / "data").mkdir(exist_ok=True)
    victim = synthetic_repo / "data" / "keep.txt"
    victim.write_text("truncated by an unredirected writer\n", encoding="utf-8")
    assert "data/keep.txt" in _git(synthetic_repo, "status", "--porcelain")

    assert WS.clean_stray(synthetic_repo, force=False) == 0
    assert victim.exists(), "report-first: nothing is deleted without --force"

    assert WS.clean_stray(synthetic_repo, force=True) == 0
    assert not victim.exists()
    assert _git(synthetic_repo, "status", "--porcelain") == "", (
        "after cleaning, the committed artifact is intact and the tree is clean"
    )


def test_clean_never_touches_a_materialized_tree(synthetic_repo: Path):
    """Only sparse-OMITTED trees are cleanable; real work must be safe."""
    _make_sparse(synthetic_repo, ["engine", "scripts", "templates"])
    edited = synthetic_repo / "engine" / "keep.txt"
    edited.write_text("real session work\n", encoding="utf-8")
    assert WS.clean_stray(synthetic_repo, force=True) == 0
    assert edited.read_text(encoding="utf-8") == "real session work\n"


def test_stray_content_inside_an_omitted_tree_is_reported(synthetic_repo: Path):
    _make_sparse(synthetic_repo, ["engine", "scripts", "templates"])
    (synthetic_repo / "site").mkdir(exist_ok=True)
    (synthetic_repo / "site" / "asset.js").write_text("written by a test\n", encoding="utf-8")
    stray = WS.stray_content(synthetic_repo, WS.missing_dirs(synthetic_repo))
    assert "site/asset.js" in stray


# --------------------------------------------------------------------------
# The two properties the operator named: no vacuous green, guard still sees dirt
# --------------------------------------------------------------------------

def test_a_write_into_an_omitted_tree_still_reaches_git_status(synthetic_repo: Path):
    """ship_loop_guard's dirty snapshot reads `git status --porcelain`.

    A sparse tree must not become a place where edits to tracked files go
    unnoticed and therefore un-committable-but-invisible.
    """
    _make_sparse(synthetic_repo, ["engine", "scripts", "templates"])
    assert _git(synthetic_repo, "status", "--porcelain") == "", "sparse tree starts clean"
    (synthetic_repo / "site").mkdir(exist_ok=True)
    (synthetic_repo / "site" / "asset.js").write_text("synthetic\n", encoding="utf-8")
    porcelain = _git(synthetic_repo, "status", "--porcelain")
    assert "site/asset.js" in porcelain, (
        "a write into a sparse-omitted tracked path must stay visible to git status"
    )


def test_template_site_sync_refuses_instead_of_passing_vacuously(synthetic_repo: Path):
    """The guard enumerates its own pair list by walking site/ — empty must not read OK."""
    import scripts.check_template_site_sync as sync

    assert sync._sparse_refusal(synthetic_repo) is None, "full checkout -> no refusal"
    assert list(sync.find_pairs(synthetic_repo)), "precondition: the fixture has a pair"

    _make_sparse(synthetic_repo, ["engine", "scripts", "templates"])
    assert list(sync.find_pairs(synthetic_repo)) == [], (
        "precondition: this is exactly the vacuous-pass shape being defended against"
    )
    refusal = sync._sparse_refusal(synthetic_repo)
    assert refusal is not None, "a sparse tree must not report 'sync OK (0 pairs checked)'"
    assert WS.FULL_CHECKOUT_CMD in refusal


# --------------------------------------------------------------------------
# The marker must skip ONLY in a sparse tree — never silently in CI
# --------------------------------------------------------------------------

class _FakeMark:
    def __init__(self, *args):
        self.args = args


class _FakeItem:
    """Minimal stand-in for a collected item: markers in, skip markers out."""

    def __init__(self, *mark_args):
        self._marks = [_FakeMark(*mark_args)]
        self.added = []

    def iter_markers(self, name=None):
        return iter(self._marks if name == "needs_full_checkout" else [])

    def add_marker(self, marker):
        self.added.append(marker)


def _conftest_module():
    path = ROOT / "tests" / "conftest.py"
    spec = importlib.util.spec_from_file_location("sparse_conftest_probe", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_needs_full_checkout_does_not_skip_in_a_full_checkout(monkeypatch):
    """CI runs full checkouts — the marker must be inert there, not a silent skip."""
    conftest = _conftest_module()
    monkeypatch.setattr(conftest, "_SPARSE_MISSING", [])
    item = _FakeItem("site")
    conftest.pytest_collection_modifyitems(None, [item])
    assert item.added == [], "a full checkout must run the test, not skip it"


def test_needs_full_checkout_skips_only_for_dirs_that_are_actually_missing(monkeypatch):
    conftest = _conftest_module()
    monkeypatch.setattr(conftest, "_SPARSE_MISSING", ["data"])

    unaffected = _FakeItem("site")  # needs site/, only data/ is missing
    conftest.pytest_collection_modifyitems(None, [unaffected])
    assert unaffected.added == []

    affected = _FakeItem("data")
    conftest.pytest_collection_modifyitems(None, [affected])
    assert len(affected.added) == 1
    assert WS.FULL_CHECKOUT_CMD in affected.added[0].kwargs["reason"]


# --------------------------------------------------------------------------
# The hook itself, and its wiring
# --------------------------------------------------------------------------

def test_worktree_create_hook_is_wired_in_checked_in_settings():
    """settings.local.json is globally gitignored, so the wiring must live here."""
    settings = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    entries = settings["hooks"]["WorktreeCreate"]
    commands = [h["command"] for entry in entries for h in entry["hooks"]]
    assert any("worktree_create_sparse.py" in c for c in commands), commands
    assert HOOK_PATH.is_file(), "the wired hook script must exist in the repo"


def test_codex_default_environment_applies_the_same_sparse_profile():
    environment = tomllib.loads(CODEX_ENVIRONMENT_PATH.read_text(encoding="utf-8"))
    assert environment["version"] == 1
    assert environment["name"]
    script = environment["setup"]["script"]
    assert "scripts/worktree_sparse.py auto" in script


def test_codex_session_start_fallback_is_wired_in_checked_in_hooks():
    settings = json.loads(CODEX_HOOKS_PATH.read_text(encoding="utf-8"))
    entries = settings["hooks"]["SessionStart"]
    assert any(entry.get("matcher") == "^startup$" for entry in entries)
    commands = [hook["command"] for entry in entries for hook in entry["hooks"]]
    assert any("scripts/worktree_sparse.py" in command and command.endswith(" auto")
               for command in commands), commands


def test_cursor_session_hooks_apply_the_same_sparse_profile():
    """Cursor IDE has no WorktreeCreate; sessionStart + workspaceOpen are the analog."""
    settings = json.loads(CURSOR_HOOKS_PATH.read_text(encoding="utf-8"))
    assert settings.get("version") == 1
    for event in ("sessionStart", "workspaceOpen"):
        entries = settings["hooks"][event]
        commands = [
            hook["command"]
            for entry in entries
            for hook in (entry if isinstance(entry, list) else [entry])
        ]
        assert any("scripts/worktree_sparse.py" in command and command.endswith(" auto")
                   for command in commands), (event, commands)


def test_cursor_worktree_setup_applies_the_same_sparse_profile():
    settings = json.loads(CURSOR_WORKTREES_PATH.read_text(encoding="utf-8"))
    unix = settings.get("setup-worktree-unix") or settings.get("setup-worktree")
    assert isinstance(unix, list), unix
    assert any("scripts/worktree_sparse.py" in command and command.endswith(" auto")
               for command in unix), unix


def test_grok_session_start_applies_the_same_sparse_profile():
    settings = json.loads(GROK_HOOKS_PATH.read_text(encoding="utf-8"))
    entries = settings["hooks"]["SessionStart"]
    commands = [hook["command"] for entry in entries for hook in entry["hooks"]]
    assert any(".grok/hooks/session_start_sparse.py" in command
               for command in commands), commands


def test_aionui_temp_predicate_matches_only_grok_temp_workspaces(tmp_path: Path):
    aion = tmp_path / ".aionui" / "conversations" / "users" / "u1" / "2026" / "08" / "18" / "grok-temp-abcd1234"
    aion.mkdir(parents=True)
    assert WS.is_aionui_temp(aion) is True
    other = tmp_path / ".aionui" / "conversations" / "users" / "u1" / "notes"
    other.mkdir(parents=True)
    assert WS.is_aionui_temp(other) is False
    assert WS.is_aionui_temp(tmp_path / "macro-main") is False


def test_mint_session_worktree_is_sparse_and_skips_heavy_trees(
        synthetic_repo: Path, tmp_path: Path):
    dest = tmp_path / ".grok" / "worktrees" / "grok-temp-test"
    assert WS.mint_session_worktree(
        synthetic_repo, dest, branch="grok/grok-temp-test",
        base="HEAD", fetch=False,
    ) == 0
    assert WS.is_session_worktree(dest) is True
    assert WS.missing_dirs(dest) == ["data", "mockups", "site"]
    assert (dest / "engine" / "keep.txt").is_file()
    assert not (dest / "data").exists()
    assert _git(dest, "status", "--porcelain") == ""


def test_mint_session_worktree_refuses_a_path_outside_session_roots(
        synthetic_repo: Path, tmp_path: Path):
    dest = tmp_path / "not-a-session-root" / "tree"
    assert WS.mint_session_worktree(
        synthetic_repo, dest, branch="grok/outside",
        base="HEAD", fetch=False,
    ) == 1
    assert not dest.exists()


def test_mint_session_worktree_reuses_an_existing_sparse_tree(
        synthetic_repo: Path, tmp_path: Path):
    dest = tmp_path / ".grok" / "worktrees" / "grok-temp-reuse"
    assert WS.mint_session_worktree(
        synthetic_repo, dest, branch="grok/grok-temp-reuse",
        base="HEAD", fetch=False,
    ) == 0
    _git(dest, "sparse-checkout", "add", "--", "site")
    assert (dest / "site" / "asset.js").is_file()
    assert WS.mint_session_worktree(
        synthetic_repo, dest, branch="grok/grok-temp-reuse",
        base="HEAD", fetch=False,
    ) == 0
    assert (dest / "site" / "asset.js").is_file(), (
        "a second SessionStart must not undo an explicit add site"
    )


def test_grok_session_start_hook_mints_from_an_aionui_temp(
        synthetic_repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    hook = _load_grok_hook()
    temp = (
        tmp_path / ".aionui" / "conversations" / "users" / "u"
        / "2026" / "08" / "18" / "grok-temp-hooktest"
    )
    temp.mkdir(parents=True)
    monkeypatch.setattr(hook, "discover_donor", lambda cwd: synthetic_repo)
    monkeypatch.setattr(hook, "_load_ws", lambda donor: WS)
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"cwd": str(temp)})))
    assert hook.main() == 0
    dest = synthetic_repo / ".grok" / "worktrees" / "grok-temp-hooktest"
    assert dest.is_dir()
    assert (temp / ".session-worktree").read_text(encoding="utf-8").strip() == str(dest)
    assert WS.missing_dirs(dest) == ["data", "mockups", "site"]


def test_hook_name_validation_rejects_path_traversal():
    hook = _load_hook()
    for bad in ("../escape", "a/b", "", "na me", "x;rm -rf /"):
        assert not hook.SAFE_NAME.match(bad), bad
    for good in ("agent-abc123", "sparse-session-worktree-2f2e4a", "pr-5502"):
        assert hook.SAFE_NAME.match(good), good


def test_hook_recognises_pr_worktree_names():
    hook = _load_hook()
    assert hook.PR_NAME.match("pr-5502").group(1) == "5502"
    assert hook.PR_NAME.match("pr-abc") is None


def test_hook_reads_the_same_profile_as_the_cli():
    """One source of truth: a config edit must move the hook and the CLI together."""
    hook = _load_hook()
    assert hook.load_profile(ROOT)["exclude_dirs"] == WS.load_profile()["exclude_dirs"]


def test_hook_falls_back_to_the_r8_floor_when_config_is_unreadable(tmp_path: Path):
    """A checkout predating the config still gets a sparse tree, never a full one."""
    hook = _load_hook()
    profile = hook.load_profile(tmp_path)  # no config/sparse_worktree.json there
    assert {"data", "site"} <= set(profile["exclude_dirs"])
    assert profile["enabled"] is True


def test_hook_fallback_never_exceeds_the_configured_profile():
    """The degraded path may exclude less than the config, never something else."""
    hook = _load_hook()
    assert set(hook.FALLBACK_EXCLUDE_DIRS) <= set(WS.load_profile()["exclude_dirs"])


def test_hook_rejects_a_malformed_config_rather_than_trusting_it(tmp_path: Path):
    hook = _load_hook()
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "sparse_worktree.json").write_text(
        '{"exclude_dirs": "data"}', encoding="utf-8")
    assert list(hook.load_profile(tmp_path)["exclude_dirs"]) == list(hook.FALLBACK_EXCLUDE_DIRS)
