from __future__ import annotations

import os
import plistlib
import shutil
import stat
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "ops" / "launchd" / "run_earnings_worker.sh"
BOOTSTRAP = ROOT / "ops" / "bootstrap_earnings_worker.sh"
PLIST = ROOT / "ops" / "launchd" / "com.mastermind.earnings-worker.plist"
REQUIREMENTS = ROOT / "ops" / "earnings_worker_requirements.txt"


def _run(script: Path, *args: str, env: dict[str, str] | None = None):
    return subprocess.run(
        ["/bin/bash", str(script), *args],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def _required_env() -> dict[str, str]:
    env = os.environ.copy()
    env.pop("AI_COSTS_STATE_ROOT", None)
    env.pop("METABOLISM_STATE_ROOT", None)
    env.pop("EARNINGS_RUNTIME_ROOT", None)
    env.update(
        {
            "R2_ENDPOINT": "fixture-endpoint-value",
            "R2_ACCESS_KEY_ID": "fixture-access-value",
            "R2_SECRET_ACCESS_KEY": "fixture-key-value",
            "R2_BUCKET": "fixture-bucket-value",
            "DEEPSEEK_API_KEY": "fixture-deepseek-value",
        }
    )
    return env


def test_control_scripts_parse_and_requirements_are_pinned():
    for path in (RUNNER, BOOTSTRAP):
        result = subprocess.run(
            ["/bin/bash", "-n", str(path)], text=True, capture_output=True, check=False
        )
        assert result.returncode == 0, result.stderr
    rows = [line for line in REQUIREMENTS.read_text().splitlines() if line.strip()]
    assert rows
    assert all("==" in row for row in rows)
    assert {row.split("==", 1)[0].lower() for row in rows} == {
        "pandas",
        "pyarrow",
        "requests",
        "boto3",
        "pyyaml",
        "anthropic",
    }


def test_bootstrap_check_verifies_installed_and_loaded_agent():
    source = BOOTSTRAP.read_text(encoding="utf-8")
    assert '/usr/bin/cmp -s "$PLIST" "$DEST_PLIST"' in source
    assert '"$LAUNCHCTL" print "$DOMAIN/$LABEL"' in source
    assert "EARNINGS_LAUNCHCTL" in source
    assert 'payload.get("initialized") is not True' in source


def test_plist_is_tcc_safe_secretless_and_has_two_retry_windows():
    with PLIST.open("rb") as handle:
        payload = plistlib.load(handle)
    assert payload["Label"] == "com.mastermind.earnings-worker"
    assert payload["WorkingDirectory"] == "/Users/chriswong/earnings-ops-wt"
    assert payload["ProgramArguments"] == [
        "/Users/chriswong/earnings-ops-wt/ops/launchd/run_with_env.sh",
        "/Users/chriswong/flow-ops-wt/.env",
        "/Users/chriswong/earnings-ops-wt/ops/launchd/run_earnings_worker.sh",
    ]
    assert payload["StartCalendarInterval"] == [
        {"Hour": 17, "Minute": 45},
        {"Hour": 20, "Minute": 45},
        {"Hour": 23, "Minute": 45},
    ]
    assert "EnvironmentVariables" not in payload
    assert "/Documents/" not in " ".join(payload["ProgramArguments"])
    assert "/Documents/" not in payload["WorkingDirectory"]


def test_env_check_reports_names_only_and_respects_local_qwen_override():
    env = _required_env()
    result = _run(RUNNER, "--check-env", env=env)
    assert result.returncode == 0, result.stderr
    combined = result.stdout + result.stderr
    for value in env.values():
        if value.startswith("fixture-"):
            assert value not in combined
    assert "DEEPSEEK_API_KEY" in result.stdout

    env.pop("DEEPSEEK_API_KEY")
    result = _run(RUNNER, "--check-env", env=env)
    assert result.returncode != 0
    assert "DEEPSEEK_API_KEY" in result.stderr

    env["EARNINGS_PROVIDER_ORDER"] = "openai_compat"
    result = _run(RUNNER, "--check-env", env=env)
    assert result.returncode == 0, result.stderr
    assert "DEEPSEEK_API_KEY" not in result.stdout

    env["EARNINGS_PROVIDER_ORDER"] = "codex"
    result = _run(RUNNER, "--check-env", env=env)
    assert result.returncode == 0, result.stderr
    assert "DEEPSEEK_API_KEY" not in result.stdout


def test_runner_ff_updates_and_invokes_forward_only_deepseek(tmp_path: Path):
    source = tmp_path / "source"
    origin = tmp_path / "origin.git"
    ops = tmp_path / "earnings-ops-wt"
    lock = tmp_path / "lock"
    fake_python = tmp_path / "fake-python"
    capture = tmp_path / "argv.txt"
    env_capture = tmp_path / "env.txt"
    runtime = tmp_path / "earnings-runtime"
    source.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=source, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"], cwd=source, check=True
    )
    subprocess.run(["git", "config", "user.name", "Test"], cwd=source, check=True)
    (source / ".gitignore").write_text("data/earnings_calls/\n", encoding="utf-8")
    runner_dest = source / "ops" / "launchd" / RUNNER.name
    runner_dest.parent.mkdir(parents=True)
    shutil.copy2(RUNNER, runner_dest)
    worker = source / "tools" / "earnings_worker" / "run_worker.py"
    worker.parent.mkdir(parents=True)
    worker.write_text("# fake worker target\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=source, check=True)
    subprocess.run(["git", "commit", "-m", "fixture"], cwd=source, check=True, capture_output=True)
    subprocess.run(["git", "clone", "--bare", str(source), str(origin)], check=True, capture_output=True)
    subprocess.run(["git", "clone", str(origin), str(ops)], check=True, capture_output=True)

    # Prove the runner performs a real fast-forward, rather than merely issuing
    # a no-op fetch against an already-current fixture.
    (source / "upstream-marker").write_text("new main revision\n", encoding="utf-8")
    subprocess.run(["git", "add", "upstream-marker"], cwd=source, check=True)
    subprocess.run(
        ["git", "commit", "-m", "advance origin"], cwd=source, check=True, capture_output=True
    )
    subprocess.run(["git", "push", str(origin), "main"], cwd=source, check=True, capture_output=True)

    fake_python.write_text(
        "#!/bin/bash\n"
        "printf '%s\\n' \"$@\" > \"$EARNINGS_TEST_CAPTURE\"\n"
        "printf '%s\\n%s\\n' \"$AI_COSTS_STATE_ROOT\" \"$METABOLISM_STATE_ROOT\" "
        "> \"$EARNINGS_TEST_ENV_CAPTURE\"\n",
        encoding="utf-8",
    )
    fake_python.chmod(fake_python.stat().st_mode | stat.S_IXUSR)
    state_dir = ops / "data" / "earnings_calls"
    state_dir.mkdir(parents=True)
    (state_dir / "terminal_intake_state.json").write_text("ignored", encoding="utf-8")

    env = _required_env()
    env.update(
        {
            "EARNINGS_OPS_ROOT": str(ops),
            "EARNINGS_PYTHON": str(fake_python),
            "EARNINGS_REMOTE_URL": str(origin),
            "EARNINGS_LOCK_DIR": str(lock),
            "EARNINGS_RUNTIME_ROOT": str(runtime),
            "EARNINGS_TEST_CAPTURE": str(capture),
            "EARNINGS_TEST_ENV_CAPTURE": str(env_capture),
        }
    )
    result = _run(runner_dest, env=env)
    assert result.returncode == 0, result.stdout + result.stderr
    argv = capture.read_text(encoding="utf-8").splitlines()
    assert argv == [
        str(ops / "tools" / "earnings_worker" / "run_worker.py"),
        "--terminal-auto",
        "--limit",
        "64",
        "--provider-order",
        "deepseek",
        "--repo-root",
        str(ops),
        "--terminal-state",
        str(ops / "data" / "earnings_calls" / "terminal_intake_state.json"),
    ]
    assert env_capture.read_text(encoding="utf-8").splitlines() == [
        str(runtime),
        str(runtime),
    ]
    assert not runtime.is_relative_to(ops)
    assert not lock.exists()
    assert subprocess.run(
        ["git", "-C", str(ops), "rev-parse", "HEAD"],
        text=True,
        capture_output=True,
        check=True,
    ).stdout == subprocess.run(
        ["git", "-C", str(ops), "rev-parse", "origin/main"],
        text=True,
        capture_output=True,
        check=True,
    ).stdout
    assert subprocess.run(
        ["git", "-C", str(ops), "status", "--porcelain", "--untracked-files=all"],
        text=True,
        capture_output=True,
        check=True,
    ).stdout == ""

    # Catch-up is opt-in and is forwarded exactly once after the update exec.
    capture.unlink()
    result = _run(runner_dest, "--bootstrap-since", "2026-07-24", env=env)
    assert result.returncode == 0, result.stdout + result.stderr
    assert capture.read_text(encoding="utf-8").splitlines()[-2:] == [
        "--bootstrap-since",
        "2026-07-24",
    ]

    # A tracked modification fails closed before model invocation.
    capture.unlink()
    runner_in_ops = ops / "ops" / "launchd" / RUNNER.name
    runner_in_ops.write_text(runner_in_ops.read_text() + "\n# dirty\n", encoding="utf-8")
    result = _run(runner_dest, env=env)
    assert result.returncode != 0
    assert "clone is dirty" in result.stderr
    assert not capture.exists()


def test_runner_rejects_runtime_state_inside_code_clone(tmp_path: Path):
    env = _required_env()
    ops = tmp_path / "earnings-ops-wt"
    env.update(
        {
            "EARNINGS_OPS_ROOT": str(ops),
            "EARNINGS_RUNTIME_ROOT": str(ops / "runtime"),
        }
    )
    result = _run(RUNNER, env=env)
    assert result.returncode != 0
    assert "outside the immutable code clone" in result.stderr


def test_check_env_rejects_canonical_aliases_into_clone(tmp_path: Path):
    env = _required_env()
    ops = tmp_path / "earnings-ops-wt"
    ops.mkdir()
    alias = tmp_path / "runtime-link"
    alias.symlink_to(ops, target_is_directory=True)
    env.update(
        {
            "EARNINGS_OPS_ROOT": str(ops),
            "EARNINGS_RUNTIME_ROOT": str(alias),
        }
    )
    result = _run(RUNNER, "--check-env", env=env)
    assert result.returncode != 0
    assert "outside the immutable code clone" in result.stderr

    env["EARNINGS_RUNTIME_ROOT"] = str(ops / "child" / "..")
    result = _run(RUNNER, "--check-env", env=env)
    assert result.returncode != 0
    assert "outside the immutable code clone" in result.stderr


def test_check_env_rejects_relative_broad_and_tcc_unsafe_roots(tmp_path: Path):
    env = _required_env()
    home = tmp_path / "home"
    documents = home / "Documents"
    documents.mkdir(parents=True)
    ops = tmp_path / "earnings-ops-wt"
    runtime = tmp_path / "runtime"
    env.update(
        {
            "HOME": str(home),
            "EARNINGS_OPS_ROOT": str(ops),
            "EARNINGS_RUNTIME_ROOT": "relative-runtime",
        }
    )
    result = _run(RUNNER, "--check-env", env=env)
    assert result.returncode != 0
    assert "must be an absolute path" in result.stderr

    env["EARNINGS_RUNTIME_ROOT"] = str(runtime)
    env["AI_COSTS_STATE_ROOT"] = str(documents / "ai-costs")
    result = _run(RUNNER, "--check-env", env=env)
    assert result.returncode != 0
    assert "outside ~/Documents" in result.stderr
