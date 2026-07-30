"""Keep self-hosted render checkouts from accumulating generated-site history."""

import os
from pathlib import Path
import shutil
import subprocess

import yaml


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "render.yml"


def _steps() -> list[dict]:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    return workflow["jobs"]["render"]["steps"]


def test_oversized_checkout_is_bounded_before_checkout_runs():
    steps = _steps()
    bound_index = next(
        index
        for index, step in enumerate(steps)
        if step.get("name") == "bound persisted render checkout"
    )
    checkout_index = next(
        index
        for index, step in enumerate(steps)
        if step.get("uses") == "actions/checkout@v4"
    )
    assert bound_index < checkout_index

    script = steps[bound_index]["run"]
    assert "8388608" in script, "8 GiB checkout bound disappeared"
    assert "*/_work/*/*)" in script, "workspace-shape safety check disappeared"
    assert '[ "$PWD" = "$GITHUB_WORKSPACE" ]' in script
    assert 'git reset --hard "$SEED_SHA"' in script
    assert "git clean -ffdx" in script
    assert 'mv .git "$CHECKOUT_TRASH"' in script
    assert 'find "$GITHUB_WORKSPACE"' not in script, (
        "the 2.85 GB current tree must survive metadata compaction"
    )
    assert "--filter=blob:none" in script
    assert '"file://$CHECKOUT_TRASH"' in script
    assert "macro.renderMetadataCheckout" in script
    assert 'git reset --mixed HEAD' in script
    assert 'git update-index --refresh' in script


def test_render_checkout_uses_a_shallow_blobless_partial_clone():
    checkout = next(
        step for step in _steps() if step.get("uses") == "actions/checkout@v4"
    )
    assert checkout["if"] == "steps.bound.outputs.checkout_ready != 'true'"
    assert checkout["with"]["ref"] == "main"
    assert checkout["with"]["filter"] == "blob:none"
    assert checkout["with"]["fetch-depth"] == 1
    assert "sparse-checkout" not in checkout["with"], (
        "render builders require the complete current data/ and site/ tree"
    )


def test_quarantine_cleanup_is_exact_and_runs_even_after_failure():
    cleanup = next(
        step
        for step in _steps()
        if step.get("name") == "remove oversized-checkout quarantine"
    )
    assert "always()" in cleanup["if"]
    script = cleanup["run"]
    assert '"${RUNNER_TEMP:?}"/macro-git-' in script
    assert 'rm -rf -- "$CHECKOUT_TRASH"' in script


def _git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return result.stdout.strip()


def _object_is_local(repo: Path, oid: str) -> bool:
    if (repo / ".git" / "objects" / oid[:2] / oid[2:]).exists():
        return True
    for index in (repo / ".git" / "objects" / "pack").glob("*.idx"):
        objects = subprocess.run(
            ["git", "verify-pack", "-v", index],
            cwd=repo,
            check=True,
            text=True,
            capture_output=True,
        ).stdout
        if any(line.startswith(f"{oid} ") for line in objects.splitlines()):
            return True
    return False


def test_oversized_reset_retains_clean_tree_and_replaces_only_metadata(tmp_path):
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", remote], check=True, capture_output=True)

    workspace = tmp_path / "runner" / "_work" / "macro" / "macro"
    workspace.parent.mkdir(parents=True)
    subprocess.run(
        ["git", "clone", remote, workspace],
        check=True,
        capture_output=True,
    )
    _git(workspace, "config", "user.name", "Render Test")
    _git(workspace, "config", "user.email", "render@example.test")
    (workspace / "site").mkdir()
    payload = "current generated site\n" + ("x" * 1024 * 1024)
    (workspace / "site" / "macro.html").write_text(payload, encoding="utf-8")
    (workspace / "tracked.txt").write_text("committed\n", encoding="utf-8")
    _git(workspace, "add", "site/macro.html", "tracked.txt")
    _git(workspace, "commit", "-m", "seed")
    _git(workspace, "branch", "-M", "main")
    _git(workspace, "push", "-u", "origin", "main")

    updater = tmp_path / "updater"
    subprocess.run(
        ["git", "clone", "--branch", "main", remote, updater],
        check=True,
        capture_output=True,
    )
    _git(updater, "config", "user.name", "Render Updater")
    _git(updater, "config", "user.email", "updater@example.test")
    (updater / "tracked.txt").write_text("updated on main\n", encoding="utf-8")
    (updater / "new-on-main.txt").write_text("main delta\n", encoding="utf-8")
    _git(updater, "add", "tracked.txt", "new-on-main.txt")
    _git(updater, "commit", "-m", "advance main")
    _git(updater, "push", "origin", "main")

    old_git_kib = int(
        subprocess.run(
            ["du", "-sk", workspace / ".git"],
            check=True,
            text=True,
            capture_output=True,
        ).stdout.split()[0]
    )
    (workspace / "tracked.txt").write_text("dirty render output\n", encoding="utf-8")
    (workspace / "ignored.tmp").write_text("throwaway\n", encoding="utf-8")

    runner_temp = tmp_path / "runner-temp"
    runner_temp.mkdir()
    github_env = tmp_path / "github-env"
    github_output = tmp_path / "github-output"
    env = {
        **os.environ,
        "CHECKOUT_GIT_MAX_KIB": "1",
        "GITHUB_WORKSPACE": str(workspace),
        "RUNNER_TEMP": str(runner_temp),
        "GITHUB_RUN_ID": "123",
        "GITHUB_RUN_ATTEMPT": "1",
        "GITHUB_ENV": str(github_env),
        "GITHUB_OUTPUT": str(github_output),
    }
    bound = next(
        step
        for step in _steps()
        if step.get("name") == "bound persisted render checkout"
    )
    subprocess.run(
        ["bash", "-c", bound["run"]],
        cwd=workspace,
        env=env,
        check=True,
        text=True,
        capture_output=True,
    )

    assert (workspace / "site" / "macro.html").read_text(encoding="utf-8") == payload
    assert (workspace / "tracked.txt").read_text(encoding="utf-8") == "updated on main\n"
    assert (workspace / "new-on-main.txt").read_text(encoding="utf-8") == "main delta\n"
    assert not (workspace / "ignored.tmp").exists()
    assert _git(workspace, "status", "--porcelain") == ""
    assert _git(workspace, "rev-parse", "--is-shallow-repository") == "true"
    assert _git(workspace, "config", "remote.origin.partialclonefilter") == "blob:none"
    assert _git(workspace, "remote", "get-url", "origin") == str(remote)
    assert (
        github_env.read_text(encoding="utf-8").strip()
        == f"CHECKOUT_TRASH={runner_temp / 'macro-git-123-1'}"
    )
    assert github_output.read_text(encoding="utf-8").strip() == "checkout_ready=true"
    assert (runner_temp / "macro-git-123-1").is_dir()
    new_git_kib = int(
        subprocess.run(
            ["du", "-sk", workspace / ".git"],
            check=True,
            text=True,
            capture_output=True,
        ).stdout.split()[0]
    )
    assert new_git_kib < old_git_kib
    assert _git(workspace, "config", "--get", "macro.renderMetadataCheckout") == "true"

    # A later run must keep using the managed metadata path even though .git is
    # now far below the size threshold. In particular, an unchanged large blob
    # must stay absent from the partial object store: actions/checkout would
    # download it (and every other current-tree blob) during its forced detach.
    stable_blob = _git(workspace, "rev-parse", "HEAD:site/macro.html")
    assert not _object_is_local(workspace, stable_blob)
    shutil.rmtree(runner_temp / "macro-git-123-1")
    _git(workspace, "config", "--unset", "macro.renderMetadataCheckout")

    (updater / "new-on-main.txt").write_text("second main delta\n", encoding="utf-8")
    (updater / "another-main-file.txt").write_text("new path\n", encoding="utf-8")
    _git(updater, "add", "new-on-main.txt", "another-main-file.txt")
    _git(updater, "commit", "-m", "advance main again")
    _git(updater, "push", "origin", "main")

    (workspace / "tracked.txt").write_text("dirty again\n", encoding="utf-8")
    (workspace / "ignored-again.tmp").write_text("throwaway\n", encoding="utf-8")
    github_env.write_text("", encoding="utf-8")
    github_output.write_text("", encoding="utf-8")
    env["CHECKOUT_GIT_MAX_KIB"] = "999999999"
    subprocess.run(
        ["bash", "-c", bound["run"]],
        cwd=workspace,
        env=env,
        check=True,
        text=True,
        capture_output=True,
    )

    assert (workspace / "site" / "macro.html").read_text(encoding="utf-8") == payload
    assert (
        workspace / "new-on-main.txt"
    ).read_text(encoding="utf-8") == "second main delta\n"
    assert (workspace / "another-main-file.txt").read_text(encoding="utf-8") == "new path\n"
    assert not (workspace / "ignored-again.tmp").exists()
    assert _git(workspace, "status", "--porcelain") == ""
    assert _git(workspace, "config", "--get", "macro.renderMetadataCheckout") == "true"
    assert github_env.read_text(encoding="utf-8") == ""
    assert github_output.read_text(encoding="utf-8").strip() == "checkout_ready=true"
    assert not _object_is_local(workspace, stable_blob)
