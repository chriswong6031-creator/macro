from __future__ import annotations

import contextlib
import json
import os
import plistlib
import shutil
import stat
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "ops" / "launchd" / "run_earnings_worker.sh"
BOOTSTRAP = ROOT / "ops" / "bootstrap_earnings_worker.sh"
PLIST = ROOT / "ops" / "launchd" / "com.mastermind.earnings-worker.plist"
REQUIREMENTS = ROOT / "ops" / "earnings_worker_requirements.txt"
QUAL_CONFIG = ROOT / "config" / "earnings_qual.yml"


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
        "/Users/chriswong/hub-ops-wt/.env",
        "/Users/chriswong/earnings-ops-wt/ops/launchd/run_earnings_worker.sh",
    ]
    assert payload["StartCalendarInterval"] == [
        {"Hour": 17, "Minute": 45},
        {"Hour": 20, "Minute": 45},
        {"Hour": 23, "Minute": 45},
    ]
    assert payload["EnvironmentVariables"] == {
        "EARNINGS_LLM_BASE_URL": "http://127.0.0.1:11435/v1",
        "EARNINGS_LLM_MODEL": "qwen3.5:9b",
    }
    assert not any(
        marker in key.upper()
        for key in payload["EnvironmentVariables"]
        for marker in ("KEY", "TOKEN", "PASSWORD", "SECRET")
    )
    assert "/Documents/" not in " ".join(payload["ProgramArguments"])
    assert "/Documents/" not in payload["WorkingDirectory"]


def test_plist_model_matches_the_config_openai_compat_default():
    """The scheduler's env var OVERRIDES config/earnings_qual.yml.

    EARNINGS_LLM_MODEL wins over ``openai_compat.model`` for every scheduled
    run, so a value that drifts from the config default is not a cosmetic
    mismatch: the local rung 404s on every call and the harness silently
    completes on the paid DeepSeek rung.  That is exactly what shipped — the
    plist said ``qwen3:14b`` while the endpoint served only ``qwen3.5:9b`` —
    and nothing in the estate could see it.  Pin the two together.
    """
    with PLIST.open("rb") as handle:
        payload = plistlib.load(handle)
    config = yaml.safe_load(QUAL_CONFIG.read_text(encoding="utf-8"))
    config_model = str((config.get("openai_compat") or {}).get("model") or "")

    assert config_model, "config/earnings_qual.yml is missing openai_compat.model"
    assert payload["EnvironmentVariables"]["EARNINGS_LLM_MODEL"] == config_model


class _ModelsEndpointHandler(BaseHTTPRequestHandler):
    """Minimal OpenAI-compatible /v1/models responder (loopback, no network)."""

    served_ids: tuple[str, ...] = ()

    def do_GET(self) -> None:  # noqa: N802 (BaseHTTPRequestHandler contract)
        if not self.path.rstrip("/").endswith("/models"):
            self.send_response(404)
            self.end_headers()
            return
        body = json.dumps(
            {
                "object": "list",
                "data": [
                    {"id": model_id, "object": "model"}
                    for model_id in type(self).served_ids
                ],
            }
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args) -> None:
        return


@contextlib.contextmanager
def _models_endpoint(served_ids: tuple[str, ...]):
    handler = type(
        "_BoundModelsHandler",
        (_ModelsEndpointHandler,),
        {"served_ids": served_ids},
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/v1"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


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

    # A reachable local endpoint promotes Qwen automatically while retaining
    # the cheap cloud fallback. A half-configured endpoint fails closed.
    env.pop("EARNINGS_PROVIDER_ORDER")
    env["EARNINGS_LLM_BASE_URL"] = "http://192.0.2.10:11434/v1"
    result = _run(RUNNER, "--check-env", env=env)
    assert result.returncode != 0
    assert "must be configured together" in result.stderr
    env["EARNINGS_LLM_MODEL"] = "qwen3:14b"
    env["DEEPSEEK_API_KEY"] = "fixture-deepseek"
    result = _run(RUNNER, "--check-env", env=env)
    assert result.returncode == 0, result.stderr
    assert "DEEPSEEK_API_KEY" in result.stdout

    env["EARNINGS_PROVIDER_ORDER"] = "codex"
    result = _run(RUNNER, "--check-env", env=env)
    assert result.returncode == 0, result.stderr
    assert "DEEPSEEK_API_KEY" not in result.stdout


def _build_ops_clone_fixture(tmp_path: Path) -> dict:
    """Stand up the appliance's origin/clone/venv fixture.

    Returns the pieces both the fast-forward contract test and the local-LLM
    preflight test need to drive a full (non ``--check-env``) runner pass.
    """
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
            # Keep the diagnostic probe from adding real seconds to the suite.
            "EARNINGS_LLM_PREFLIGHT_TIMEOUT": "2",
        }
    )
    return {
        "runner": runner_dest,
        "env": env,
        "capture": capture,
        "env_capture": env_capture,
        "ops": ops,
        "runtime": runtime,
        "lock": lock,
    }


def test_runner_ff_updates_and_invokes_forward_only_deepseek(tmp_path: Path):
    fixture = _build_ops_clone_fixture(tmp_path)
    runner_dest = fixture["runner"]
    env = fixture["env"]
    capture = fixture["capture"]
    env_capture = fixture["env_capture"]
    ops = fixture["ops"]
    runtime = fixture["runtime"]
    lock = fixture["lock"]

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

    # Once an explicit reachable endpoint/model pair is provisioned, the same
    # worker switches to Qwen-first without changing source or its scheduler.
    capture.unlink()
    local_env = dict(env)
    local_env["EARNINGS_LLM_BASE_URL"] = "http://192.0.2.10:11434/v1"
    local_env["EARNINGS_LLM_MODEL"] = "qwen3.5:9b"
    result = _run(runner_dest, env=local_env)
    assert result.returncode == 0, result.stdout + result.stderr
    local_argv = capture.read_text(encoding="utf-8").splitlines()
    provider_index = local_argv.index("--provider-order")
    assert local_argv[provider_index + 1] == "openai_compat,deepseek"

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


def test_local_llm_preflight_names_each_outcome_without_changing_the_run(
    tmp_path: Path,
):
    """The probe is diagnostic only, and each outcome is named distinctly.

    A model id the endpoint does not serve 404s every openai_compat call, after
    which the harness completes on DeepSeek and writes a row that looks healthy.
    The preflight makes that legible in the scheduler log BEFORE the first call,
    but it must never abort the run or edit PROVIDER_ORDER — DeepSeek stays the
    automatic fallback.
    """
    fixture = _build_ops_clone_fixture(tmp_path)
    runner_dest = fixture["runner"]
    capture = fixture["capture"]

    def _provider_order(argv: list[str]) -> str:
        return argv[argv.index("--provider-order") + 1]

    with _models_endpoint(("qwen3.5:9b",)) as base_url:
        # (1) endpoint healthy and the configured model is served.
        env = dict(fixture["env"])
        env["EARNINGS_LLM_BASE_URL"] = base_url
        env["EARNINGS_LLM_MODEL"] = "qwen3.5:9b"
        result = _run(runner_dest, env=env)
        assert result.returncode == 0, result.stdout + result.stderr
        assert "local-llm preflight OK" in result.stdout
        assert "served=qwen3.5:9b" in result.stdout
        assert _provider_order(
            capture.read_text(encoding="utf-8").splitlines()
        ) == "openai_compat,deepseek"

        # (2) endpoint reachable, configured model NOT in the served list.
        #     This is the shipped defect: the plist's qwen3:14b against an
        #     endpoint whose entire catalogue is qwen3.5:9b.
        capture.unlink()
        env["EARNINGS_LLM_MODEL"] = "qwen3:14b"
        result = _run(runner_dest, env=env)
        assert result.returncode == 0, result.stdout + result.stderr
        assert "local-llm preflight MODEL_NOT_SERVED" in result.stdout
        assert "model=qwen3:14b" in result.stdout
        # The served ids must be printed, or the drift is not legible.
        assert "served=qwen3.5:9b" in result.stdout
        # Diagnostic only: the run proceeds and the waterfall is untouched.
        assert _provider_order(
            capture.read_text(encoding="utf-8").splitlines()
        ) == "openai_compat,deepseek"

    # (3) endpoint unreachable — the fixture server is now shut down, so the
    #     same port refuses the connection.
    capture.unlink()
    env = dict(fixture["env"])
    env["EARNINGS_LLM_BASE_URL"] = base_url
    env["EARNINGS_LLM_MODEL"] = "qwen3.5:9b"
    result = _run(runner_dest, env=env)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "local-llm preflight UNREACHABLE" in result.stdout
    # The curl exit code is what distinguishes refused (7) from timeout (28).
    assert "curl_exit=" in result.stdout
    assert "curl_exit=0" not in result.stdout
    assert _provider_order(
        capture.read_text(encoding="utf-8").splitlines()
    ) == "openai_compat,deepseek"


def test_local_llm_preflight_is_skipped_without_a_configured_endpoint(
    tmp_path: Path,
):
    """No endpoint pair means no probe and no misleading log line."""
    fixture = _build_ops_clone_fixture(tmp_path)
    result = _run(fixture["runner"], env=fixture["env"])
    assert result.returncode == 0, result.stdout + result.stderr
    assert "local-llm preflight" not in result.stdout
