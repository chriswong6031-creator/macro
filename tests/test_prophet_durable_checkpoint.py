"""Workflow contract for the early, narrow Prophet durability checkpoint.

The Prophet build runs midway through the long ``engine`` job because it needs
the board that ``build_site`` just produced.  It must not wait behind the
regional-builder barrier before its tracked artifacts reach main, and it must
not rebase the engine's dirty working tree to get there.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import yaml

from scripts.workflow_run_source import resolve_run_source

ROOT = Path(__file__).resolve().parents[1]
DAILY = ROOT / ".github" / "workflows" / "daily.yml"
PROPHET_STEP = "Prophet nightly (plan refresh + ledger advancement; R2 after checkpoint)"
CHECKPOINT_STEP = "checkpoint Prophet outputs to main (durable before engine tail)"
R2_PUBLISH_STEP = "publish Prophet public health receipt to R2 (and enforce index tombstone)"
ACCEPTED_SOURCE_STEP = "restore accepted Prophet source for downstream derivations"
STAGE_SHADOW_STEP = (
    "Prophet × Stage forward-shadow (tag actual entries + nightly grade advance)"
)
STAGE_CHECKPOINT_STEP = "checkpoint Prophet Stage-shadow accrual to main"
ENGINE_BARRIER_STEP = (
    "regional + desk builders "
    "(parallelised — independent clusters, barrier before the hub)"
)
HEATMAP_CAP_STEP = "S&P 500 heatmap real-cap reference (weekly Polygon refresh; committed)"


def _engine_steps() -> list[dict]:
    doc = yaml.safe_load(DAILY.read_text(encoding="utf-8"))
    steps = doc["jobs"]["engine"]["steps"]
    # 512KB-cap diet: some bodies live in scripts/ci/ — resolve the effective
    # source so these assertions keep reading what the step actually runs.
    for step in steps:
        if isinstance(step.get("run"), str):
            step["run"] = resolve_run_source(step["run"], ROOT)
    return steps


def _step(name: str) -> dict:
    return next(s for s in _engine_steps() if s.get("name") == name)


def _python_heredocs(run: str) -> list[str]:
    blocks: list[str] = []
    current: list[str] | None = None
    for line in run.splitlines():
        if current is None and "<<'PY'" in line and "python" in line:
            current = []
        elif current is not None and line == "PY":
            blocks.append("\n".join(current) + "\n")
            current = None
        elif current is not None:
            current.append(line)
    assert current is None, "unterminated Python heredoc in workflow"
    return blocks


def _git(
    cwd: Path, *args: str, check: bool = True
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=check,
        capture_output=True,
        text=True,
    )


def _write(repo: Path, relative: str, content: str) -> None:
    path = repo / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _accepted_source_fixture(
    tmp_path: Path,
) -> tuple[Path, str, dict[str, str], tuple[str, ...]]:
    origin = tmp_path / "origin.git"
    runner = tmp_path / "runner"
    _git(tmp_path, "init", "--bare", str(origin))
    _git(tmp_path, "init", str(runner))
    _git(runner, "checkout", "-b", "main")
    _git(runner, "config", "user.name", "Prophet restore test")
    _git(runner, "config", "user.email", "prophet-restore@example.invalid")

    base = {
        "site/prophet/index.json": '{"generation":"stale"}\n',
        "data/prophet/ledger.jsonl": '{"id":"existing"}\n',
        "data/prophet_arena/scoreboard.json": '{"generation":"stale"}\n',
        "data/prophet_stage_shadow/summary.json": '{"generation":"stale"}\n',
    }
    for relative, content in base.items():
        _write(runner, relative, content)
    _git(runner, "add", ".")
    _git(runner, "commit", "-m", "stale engine checkout")
    stale_sha = _git(runner, "rev-parse", "HEAD").stdout.strip()
    _git(runner, "remote", "add", "origin", str(origin))
    _git(runner, "push", "-u", "origin", "main")

    accepted = {
        "site/prophet/index.json": '{"generation":"accepted"}\n',
        "site/prophet/plans/NEW-BULL-20260808.json": '{"id":"NEW-BULL-20260808"}\n',
        "data/prophet/origination_receipts/run-2.json": '{"schema":"receipt/v1"}\n',
        "data/prophet_arena/price_basis_trigger_v2/C0_champion_mirror.jsonl": (
            '{"plan_id":"NEW-BULL-20260808"}\n'
        ),
    }
    for relative, content in accepted.items():
        _write(runner, relative, content)
    _git(runner, "add", ".")
    _git(runner, "commit", "-m", "accepted Prophet checkpoint")
    accepted_sha = _git(runner, "rev-parse", "HEAD").stdout.strip()
    _git(runner, "push", "origin", "main")

    _git(runner, "reset", "--hard", stale_sha)
    local_only = (
        "site/prophet/plans/LOCAL-ONLY.json",
        "data/prophet_arena/local-only.json",
    )
    _write(runner, "site/prophet/index.json", '{"generation":"dirty-build"}\n')
    for relative in local_only:
        _write(runner, relative, "local-only\n")
    return runner, accepted_sha, accepted, local_only


def _run_accepted_source_restore(
    repo: Path, output: Path
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.update(
        {
            "GITHUB_OUTPUT": str(output),
            "GITHUB_REF": "refs/heads/main",
        }
    )
    return subprocess.run(
        ["bash", "-c", _step(ACCEPTED_SOURCE_STEP)["run"]],
        cwd=repo,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )


def test_successful_prophet_build_is_checkpointed_immediately_before_the_tail() -> None:
    steps = _engine_steps()
    names = [s.get("name") for s in steps]
    build_i = names.index(PROPHET_STEP)
    checkpoint_i = names.index(CHECKPOINT_STEP)
    r2_i = names.index(R2_PUBLISH_STEP)
    source_i = names.index(ACCEPTED_SOURCE_STEP)

    assert checkpoint_i == build_i + 1
    assert r2_i == checkpoint_i + 1
    assert source_i == r2_i + 1
    assert source_i < names.index(STAGE_SHADOW_STEP)
    assert checkpoint_i < names.index(ENGINE_BARRIER_STEP)
    assert checkpoint_i < names.index("commit engine outputs")


def test_prophet_workflow_embedded_python_is_syntactically_valid() -> None:
    names = (PROPHET_STEP, R2_PUBLISH_STEP, STAGE_SHADOW_STEP)
    blocks = [block for name in names for block in _python_heredocs(_step(name)["run"])]
    assert len(blocks) >= 6
    for i, source in enumerate(blocks):
        compile(source, f"daily.yml:{names}:{i}", "exec")


def test_stage_shadow_has_its_own_immediate_atomic_checkpoint() -> None:
    steps = _engine_steps()
    names = [s.get("name") for s in steps]
    stage_i = names.index(STAGE_SHADOW_STEP)
    checkpoint_i = names.index(STAGE_CHECKPOINT_STEP)
    checkpoint = _step(STAGE_CHECKPOINT_STEP)

    assert checkpoint_i == stage_i + 1
    assert checkpoint_i < names.index(ENGINE_BARRIER_STEP)
    assert checkpoint_i < names.index("commit engine outputs")
    assert checkpoint["if"] == "steps.prophet_stage_shadow.outputs.succeeded == 'true'"
    assert checkpoint["continue-on-error"] is True
    assert checkpoint["timeout-minutes"] == 10


def test_failed_prophet_build_cannot_publish_a_checkpoint() -> None:
    build = _step(PROPHET_STEP)
    checkpoint = _step(CHECKPOINT_STEP)

    assert build["id"] == "prophet_nightly"
    run = build["run"]
    assert 'echo "succeeded=true" >> "$GITHUB_OUTPUT"' in run
    assert 'echo "succeeded=false" >> "$GITHUB_OUTPUT"' in run
    assert 'echo "delta_manifest=$PROPHET_DELTA" >> "$GITHUB_OUTPUT"' in run
    assert checkpoint["if"] == "steps.prophet_nightly.outputs.succeeded == 'true'"
    assert checkpoint["env"]["PROPHET_DELTA_MANIFEST"].endswith(
        "steps.prophet_nightly.outputs.delta_manifest }}"
    )


def test_r2_credentials_and_publish_are_absent_from_generation() -> None:
    build = _step(PROPHET_STEP)
    run = build["run"]

    assert "scripts.build_prophet --publish" not in run
    assert "python -m scripts.build_prophet 2>&1" in run
    for secret in (
        "R2_ENDPOINT",
        "R2_ACCESS_KEY_ID",
        "R2_SECRET_ACCESS_KEY",
        "R2_BUCKET",
    ):
        assert secret not in build.get("env", {})


def test_r2_is_armed_only_after_a_successfully_pushed_checkpoint() -> None:
    checkpoint = _step(CHECKPOINT_STEP)
    run = checkpoint["run"]
    push_i = run.index("if push_do origin HEAD:main; then")
    remote_proof_i = run.index(
        'git merge-base --is-ancestor "$CHECKPOINT_SHA" origin/main'
    )
    hash_proof_i = run.index(
        'if [ "$CHECKPOINT_INDEX_SHA256" != "$INDEX_SHA256" ]'
    )
    arm_i = run.index('echo "r2_ready=true" >> "$GITHUB_OUTPUT"')

    assert checkpoint["id"] == "prophet_checkpoint"
    assert push_i < remote_proof_i < hash_proof_i < arm_i
    assert run.count('echo "r2_ready=true" >> "$GITHUB_OUTPUT"') == 1
    assert 'git diff --quiet "$CHECKPOINT_SHA" origin/main --' in run
    assert "data/prophet" in run[remote_proof_i:arm_i]
    assert "site/prophet" in run[remote_proof_i:arm_i]


def test_r2_publisher_reconstructs_and_hashes_the_checkpointed_git_blob() -> None:
    publish = _step(R2_PUBLISH_STEP)
    run = publish["run"]

    assert publish["if"] == "steps.prophet_checkpoint.outputs.r2_ready == 'true'"
    assert publish["continue-on-error"] is True
    assert publish["timeout-minutes"] == 5
    assert publish["env"]["PROPHET_CHECKPOINT_SHA"].endswith(
        "steps.prophet_checkpoint.outputs.checkpoint_sha }}"
    )
    assert publish["env"]["PROPHET_INDEX_SHA256"].endswith(
        "steps.prophet_checkpoint.outputs.index_sha256 }}"
    )
    for secret in (
        "R2_ENDPOINT",
        "R2_ACCESS_KEY_ID",
        "R2_SECRET_ACCESS_KEY",
        "R2_BUCKET",
    ):
        assert "secrets." in publish["env"][secret]
        assert secret not in _step(CHECKPOINT_STEP).get("env", {})
    assert (
        'git show "${PROPHET_CHECKPOINT_SHA}:site/prophet/index.json"'
        in run
    )
    assert "hashlib.sha256" in run
    assert 'if [ "$ACTUAL_SHA256" != "$PROPHET_INDEX_SHA256" ]' in run
    assert "from scripts.build_prophet import (" in run
    for name in ("R2_HEALTH_KEY", "_r2_client", "build_public_health_projection", "guarded_put_object"):
        assert name in run
    assert "client.head_object(Bucket=bucket, Key=R2_HEALTH_KEY)" in run
    assert 'condition = {"IfNoneMatch": "*"}' in run
    assert 'condition = {"IfMatch": etag}' in run
    assert "guarded_put_object(" in run
    assert "client.put_object(" not in run
    assert '"git-checkpoint": checkpoint_sha' in run
    assert '"sha256": expected_sha' in run
    assert 'if status == 412:' in run
    assert 'os.environ.get("R2_BUCKET") or "mastermindx"' in run
    # DEC:B1-PROPHET-PUBLIC-SPLIT: the full plan book must never reach R2 again,
    # and the forbidden key is enforced closed by a self-healing tombstone.
    assert "FORBIDDEN_INDEX_KEY = \"prophet/index.json\"" in run
    assert "enforce_index_tombstone" in run
    assert "client.delete_object(Bucket=bucket, Key=FORBIDDEN_INDEX_KEY)" in run
    assert "Prophet R2 tombstone::" in run
    assert "removed forbidden public object {FORBIDDEN_INDEX_KEY}" in run
    assert "R2_INDEX_KEY" not in run


def test_r2_publisher_rechecks_all_prophet_authority_paths_before_upload() -> None:
    run = _step(R2_PUBLISH_STEP)["run"]
    verify_body = run.split("verify_prophet_checkpoint_current() {", 1)[1].split(
        "}", 1
    )[0]

    assert "refs/remotes/origin/main" in verify_body
    assert 'merge-base --is-ancestor "$PROPHET_CHECKPOINT_SHA" origin/main' in verify_body
    for path in ("data/prophet", "data/prophet_arena", "site/prophet"):
        assert path in verify_body
    # Once before materialising the blob and once immediately before upload.
    assert run.count("if ! verify_prophet_checkpoint_current; then") == 2
    first_verify = run.index("if ! verify_prophet_checkpoint_current; then")
    materialize = run.index('git show "${PROPHET_CHECKPOINT_SHA}:site/prophet/index.json"')
    second_verify = run.index(
        "if ! verify_prophet_checkpoint_current; then", first_verify + 1
    )
    upload = run.index("guarded_put_object(")
    assert first_verify < materialize < second_verify < upload


def test_stage_shadow_reads_only_a_current_main_prophet_projection() -> None:
    steps = _engine_steps()
    names = [s.get("name") for s in steps]
    source = _step(ACCEPTED_SOURCE_STEP)
    stage = _step(STAGE_SHADOW_STEP)
    run = source["run"]

    assert names.index(ACCEPTED_SOURCE_STEP) < names.index(STAGE_SHADOW_STEP)
    assert source["id"] == "prophet_accepted_source"
    assert source["if"] == "always()"
    assert source["continue-on-error"] is True
    assert source["timeout-minutes"] == 3
    assert '[ "$EVENT_REF" != "refs/heads/main" ]' in run
    assert '[ "$SOURCE_BRANCH" != "main" ]' in run
    assert "refs/remotes/origin/main" in run
    checkout_i = run.index('git checkout "$ACCEPTED_PROPHET_SHA" --')
    verify_index_i = run.index(
        'git diff --cached --quiet "$ACCEPTED_PROPHET_SHA" --'
    )
    verify_worktree_i = run.index("git diff --quiet --", verify_index_i)
    reset_i = run.index("git reset -q --", verify_worktree_i)
    ready_i = run.index('echo "ready=true" >> "$GITHUB_OUTPUT"')
    assert checkout_i < verify_index_i < verify_worktree_i < reset_i < ready_i
    for root in ("site/prophet", "data/prophet", "data/prophet_arena"):
        assert root in run[checkout_i:ready_i]
    clean_block = run.split("git clean -fd --", 1)[1].split("git reset", 1)[0]
    for root in (
        "site/prophet",
        "data/prophet/origination_receipts",
        "data/prophet_arena",
        "data/prophet_stage_shadow",
    ):
        assert root in clean_block
    assert "git clean -fd -- data/prophet" not in run
    assert "git ls-files --others --exclude-standard -- data/prophet" in run
    assert stage["if"] == "steps.prophet_accepted_source.outputs.ready == 'true'"


def test_accepted_source_restore_handles_new_paths_over_a_stale_head(
    tmp_path: Path,
) -> None:
    repo, accepted_sha, accepted, local_only = _accepted_source_fixture(tmp_path)
    output = tmp_path / "github-output"

    result = _run_accepted_source_restore(repo, output)

    assert result.returncode == 0, result.stdout + result.stderr
    outputs = output.read_text(encoding="utf-8").splitlines()
    assert "ready=true" in outputs
    assert f"accepted_sha={accepted_sha}" in outputs
    for relative, content in accepted.items():
        assert (repo / relative).read_text(encoding="utf-8") == content
    for relative in local_only:
        assert not (repo / relative).exists()
    # Downstream readers get accepted bytes without staging them against the
    # engine job's older checkout-time HEAD.
    assert _git(repo, "diff", "--cached", "--quiet", check=False).returncode == 0


def test_accepted_source_restore_withholds_a_true_extra_prophet_file(
    tmp_path: Path,
) -> None:
    repo, _, _, _ = _accepted_source_fixture(tmp_path)
    output = tmp_path / "github-output"
    extra = repo / "data/prophet/operator-extra.json"
    _write(repo, "data/prophet/operator-extra.json", '{"not_in_main":true}\n')

    result = _run_accepted_source_restore(repo, output)

    assert result.returncode == 1
    assert "Prophet downstream source mismatch" in result.stdout
    assert not output.exists() or "ready=true" not in output.read_text(encoding="utf-8")
    assert extra.is_file()
    # A withheld restore must also leave no accepted-source paths staged for a
    # later broad commit to pick up accidentally.
    assert _git(repo, "diff", "--cached", "--quiet", check=False).returncode == 0


def test_off_main_or_detached_source_checkout_is_rejected_before_copying() -> None:
    run = _step(CHECKPOINT_STEP)["run"]
    guard_i = run.index('SOURCE_BRANCH="$(git -C "$GITHUB_WORKSPACE" symbolic-ref')
    copy_i = run.index('git worktree add -b "$CHECKPOINT_BRANCH"')

    assert guard_i < copy_i
    assert '[ "$EVENT_REF" != "refs/heads/main" ]' in run
    assert '[ -z "$EVENT_SHA" ]' in run
    assert '[ "$SOURCE_BRANCH" != "main" ]' in run
    assert "merge-base --is-ancestor" in run
    assert '"$SOURCE_HEAD" origin/main' in run
    assert "off-main workflow_dispatch output will not publish" in run


def test_checkpoint_never_rebases_the_dirty_engine_worktree() -> None:
    checkpoint = _step(CHECKPOINT_STEP)
    run = checkpoint["run"]

    assert 'git worktree add -b "$CHECKPOINT_BRANCH" "$CHECKPOINT_DIR" origin/main' in run
    assert 'cd "$CHECKPOINT_DIR"' in run
    assert "push_fetch_main_for_rebase" in run
    assert "git rebase origin/main" in run
    assert "git rebase -X" not in run
    assert "-X theirs" not in run
    assert "push_do origin HEAD:main" in run
    assert "git pull --rebase --autostash" not in run
    assert checkpoint["continue-on-error"] is True
    assert checkpoint["timeout-minutes"] == 12


def test_build_emits_a_hashed_closed_allowlist_delta_manifest() -> None:
    run = _step(PROPHET_STEP)["run"]
    for path in (
        "site/prophet/index.json",
        "site/prophet/showcase.json",
        "site/prophet/plans",
        "site/prophet/states",
        "data/prophet/ledger.jsonl",
        "data/prophet/ledger_quarantine.json",
        "data/prophet_arena",
        "data/prophet/origination_receipts",
    ):
        assert path in run
    assert "hashlib.sha256" in run
    assert "st_mode & 0o7777" in run
    assert "refusing symlinked Prophet output" in run
    assert "before.get(path, 'MISSING')" in run
    assert "after[path]" in run
    assert "data/prophet/plan_corrections.jsonl" not in run
    assert "data/prophet/ledger_corrections.jsonl" not in run
    # This is an intentionally ignored R2/Pages-side cache, not a tracked
    # publication. A normal `git add` cannot make it durable and must not turn
    # the whole checkpoint into a guaranteed failure.
    assert "site/stockdata/prophet_arena.json" not in run


def test_legacy_shadow_parts_are_checkpointed_like_the_receipts() -> None:
    """R6 (2026-08-10): the §6.5 legacy-shadow accrual store must survive the
    runner.

    The 2026-08-09 nightly wrote data/prophet/legacy_shadow/2026-08/
    2026-08-09.parquet (intake receipt legacy_shadow.rows_in_part: 30) and it
    never reached git: the engine tail's `git reset -q -- data/prophet`
    unstages the whole root, so the hash-guarded checkpoint manifest is the
    ONLY publication path — and the store was not registered in it. Registered
    here on exactly the origination_receipts terms: hashed into both the
    baseline and post-build snapshots, and inside the closed allowlist the
    checkpoint stages from.
    """
    build_run = _step(PROPHET_STEP)["run"]
    checkpoint_run = _step(CHECKPOINT_STEP)["run"]

    # Month-grouped DAY parts: legacy_shadow/YYYY-MM/YYYY-MM-DD.parquet.
    assert build_run.count('"data/prophet/legacy_shadow": "*/*.parquet"') == 2
    assert "data/prophet/legacy_shadow/*/*.parquet" in checkpoint_run
    # Same closed allowlist the receipts pass through — not a whole-root add.
    case_allowlist = checkpoint_run.split('case "$rel" in', 1)[1].split("*)", 1)[0]
    assert "data/prophet/legacy_shadow/*/*.parquet" in case_allowlist
    # Append-only correction ledgers stay out, as before.
    assert "plan_corrections" not in case_allowlist


def test_origination_receipt_freezes_exact_rows_and_ranked_price_staleness() -> None:
    run = _step(PROPHET_STEP)["run"]
    snapshot_i = run.index('"schema": "prophet.origination_source_snapshot/v1"')
    build_i = run.index("python -m scripts.build_prophet 2>&1")
    receipt_i = run.index('"schema": "prophet.origination_receipt/v1"')
    delta_i = run.index("after = snapshot()", receipt_i)

    assert snapshot_i < build_i < receipt_i < delta_i
    assert "select_candidates(board, n=None)" in run
    assert '"board_row": row' in run
    assert '"board_row": candidate["board_row"]' in run
    assert '"board_row_sha256"' in run
    assert '"plan_sha256"' in run
    assert '"source_asof": str(staleness.get("price_through")' in run
    assert '"price_through": str(staleness.get("price_through")' in run
    assert '"source_basis": staleness.get("basis")' in run
    assert '"basis": staleness.get("basis")' in run
    assert '"delayed": staleness.get("delayed")' in run
    assert '"unknown": staleness.get("unknown")' in run
    assert '"staleness": staleness' in run
    assert '"board_asof": board_asof' in run
    assert '"source_checkout": subprocess.check_output' in run
    assert 'receipt_path.open("xb")' in run
    assert run.count("except FileExistsError:") == 1


def test_origination_receipt_rejects_board_drift_and_survives_tail_loss() -> None:
    steps = _engine_steps()
    names = [step.get("name") for step in steps]
    build_run = _step(PROPHET_STEP)["run"]
    checkpoint_run = _step(CHECKPOINT_STEP)["run"]

    assert "live_sha != expected_sha" in build_run
    assert "blob_sha != expected_sha" in build_run
    assert "live_bytes != blob_bytes" in build_run
    assert "no output from an ambiguous source snapshot will publish" in build_run
    assert '"data/prophet/origination_receipts": "*.json"' in build_run
    assert "data/prophet/origination_receipts/*.json" in checkpoint_run
    assert names.index(CHECKPOINT_STEP) < names.index(ENGINE_BARRIER_STEP)
    # Provenance is self-contained; it does not depend on whatever board HEAD has
    # by the time a chronology audit runs after an engine-tail cancellation.
    receipt_body = build_run[build_run.index('"schema": "prophet.origination_receipt/v1"'):]
    assert '"source": source' in receipt_body
    assert 'git show HEAD:site/factordata/us_standouts.json' not in receipt_body


def test_arena_checkpoint_uses_only_the_seven_active_v2_ledgers() -> None:
    build_run = _step(PROPHET_STEP)["run"]
    checkpoint_run = _step(CHECKPOINT_STEP)["run"]
    policies = (
        "C0_champion_mirror",
        "C1_buy_soon_first",
        "C3_door_w_union",
        "C4_dispersion_cap",
        "C5_align2_gate",
        "C6_time_stop_21",
        "C7_buy_soon_admitted",
    )
    for policy in policies:
        path = f"data/prophet_arena/price_basis_trigger_v2/{policy}.jsonl"
        assert build_run.count(f'"{path}"') == 2
        assert path in checkpoint_run
    assert '"data/prophet_arena": "*.jsonl"' not in build_run
    assert "data/prophet_arena/*.jsonl" not in checkpoint_run
    # A RETIRED key's ledger is sealed: never staged again, in either era. Re-adding it
    # here would let the nightly advance a file whose policy stopped accruing.
    retired = ("C2_stage_ran_preferred",)
    # Sealed v1 evidence cannot be selected by a broad top-level ledger pattern.
    for policy in (*policies, *retired):
        assert f"data/prophet_arena/{policy}.jsonl" not in checkpoint_run
    for policy in retired:
        path = f"data/prophet_arena/price_basis_trigger_v2/{policy}.jsonl"
        assert path not in build_run
        assert path not in checkpoint_run


def test_checkpoint_stages_each_manifest_path_and_never_a_whole_root() -> None:
    run = _step(CHECKPOINT_STEP)["run"]

    # A broad add here would publish half-built pages and unrelated ledgers
    # before their normalizers and guards have run.
    for forbidden in (
        "git add data/",
        "git add site/",
        "git add -A .",
        "git add --all",
        "git add reports/",
        "git add templates/",
        "git add -A --",
        "rsync ",
        "--delete",
    ):
        assert forbidden not in run
    assert 'git add -- "$rel"' in run
    assert 'cp -p "$GITHUB_WORKSPACE/$rel" "$CHECKPOINT_DIR/$rel"' in run


def test_deletions_are_refused_instead_of_propagated() -> None:
    build_run = _step(PROPHET_STEP)["run"]
    checkpoint_run = _step(CHECKPOINT_STEP)["run"]

    assert "deleted = sorted(set(before) - set(after))" in build_run
    assert "early checkpoint refuses all deletions" in build_run
    assert 'if [ ! -f "$GITHUB_WORKSPACE/$rel" ]' in checkpoint_run
    assert "deletions are forbidden" in checkpoint_run
    assert 'rm -f "$CHECKPOINT_DIR/$rel"' not in checkpoint_run


def test_concurrent_main_corrections_are_preserved_and_stale_projection_refused() -> None:
    run = _step(CHECKPOINT_STEP)["run"]
    for correction in (
        "data/prophet/plan_corrections.jsonl",
        "data/prophet/ledger_corrections.jsonl",
    ):
        assert correction in run
    assert 'git diff --quiet "$SOURCE_HEAD" origin/main --' in run
    assert "correction ledgers advanced during publish" in run
    case_allowlist = run.split('case "$rel" in', 1)[1].split("*)", 1)[0]
    assert "plan_corrections" not in case_allowlist
    assert "ledger_corrections" not in case_allowlist


def test_concurrent_same_path_main_update_aborts_without_merge_override() -> None:
    run = _step(CHECKPOINT_STEP)["run"]
    conflict_i = run.index(
        'git diff --quiet "$CHECKPOINT_PARENT" origin/main -- "$rel"'
    )
    rebase_i = run.index("git rebase origin/main")

    assert conflict_i < rebase_i
    assert "origin/main advanced build-owned path(s)" in run
    assert "no merge strategy override is allowed" in run
    assert "-X theirs" not in run


def test_checkpoint_revalidates_source_bytes_against_manifest_before_copy() -> None:
    run = _step(CHECKPOINT_STEP)["run"]
    assert 'current_after="$(python3 -c' in run
    assert 'if [ "$current_after" != "$after_sha" ]' in run
    assert "changed after build completion" in run
    assert "Prophet checkpoint symlink rejected" in run
    assert "push_staged_clean" in run


def test_final_engine_commit_cannot_bypass_checkpoint_refusal() -> None:
    steps = _engine_steps()
    names = [s.get("name") for s in steps]
    checkpoint_i = names.index(CHECKPOINT_STEP)
    final_i = names.index("commit engine outputs")

    assert final_i > checkpoint_i
    final_run = steps[final_i]["run"]
    broad_add_i = final_run.index("git add data/ site/ reports/")
    safe_ref_i = final_run.index("git checkout HEAD -- ")
    reset_i = final_run.index("git reset -q -- ", safe_ref_i)
    scoped_clean_i = final_run.index("git clean -fd --", reset_i)
    push_i = final_run.index("push_staged_heal data/ site/ reports/ templates/")

    assert broad_add_i < safe_ref_i < reset_i < scoped_clean_i < push_i
    assert "PROPHET_SAFE_REF=origin/main" not in final_run
    assert "git checkout origin/main --" not in final_run
    for path in (
        "site/prophet",
        "data/prophet/ledger.jsonl",
        "data/prophet/ledger_quarantine.json",
        "data/prophet_arena",
        "data/prophet_stage_shadow",
    ):
        assert path in final_run[safe_ref_i:reset_i]
    reset_block = final_run[reset_i:push_i]
    for root in (
        "site/prophet",
        "data/prophet",
        "data/prophet_arena",
    ):
        assert root in reset_block
    # Corrections are source-of-truth inputs: never overwrite or clean them.
    assert "data/prophet/plan_corrections.jsonl" not in final_run
    assert "data/prophet/ledger_corrections.jsonl" not in final_run
    assert "site/stockdata/prophet_arena.json" not in final_run


def test_final_engine_cleanup_removes_first_publication_prophet_additions(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.name", "Prophet cleanup test")
    _git(repo, "config", "user.email", "prophet-cleanup@example.invalid")
    _write(repo, "baseline.txt", "safe\n")
    tracked_legacy = "data/prophet/legacy_shadow/2026-08/existing.parquet"
    tracked_receipt = "data/prophet/origination_receipts/existing.json"
    _write(repo, tracked_legacy, "safe legacy bytes\n")
    _write(repo, tracked_receipt, "safe receipt bytes\n")
    _git(repo, "add", "baseline.txt", tracked_legacy, tracked_receipt)
    _git(repo, "commit", "-m", "baseline")

    new_paths = (
        "site/prophet/plans/new.json",
        "data/prophet_arena/new.json",
        "data/prophet_stage_shadow/new.json",
        "data/prophet/legacy_shadow/2026-08/new.parquet",
    )
    for path in new_paths:
        _write(repo, path, "{}\n")
    _write(repo, tracked_legacy, "mutated legacy bytes\n")
    _git(repo, "add", "site", "data")
    assert {line[0] for line in _git(repo, "status", "--short").stdout.splitlines()} == {
        "A",
        "M",
    }

    _git(
        repo,
        "checkout",
        "HEAD",
        "--",
        "data/prophet/origination_receipts",
        "data/prophet/legacy_shadow",
    )

    _git(
        repo,
        "reset",
        "-q",
        "--",
        "site/prophet",
        "data/prophet",
        "data/prophet_arena",
        "data/prophet_stage_shadow",
    )
    _git(
        repo,
        "clean",
        "-fd",
        "--",
        "site/prophet",
        "data/prophet_arena",
        "data/prophet_stage_shadow",
        "data/prophet/legacy_shadow",
    )

    assert _git(repo, "status", "--porcelain").stdout == ""
    assert all(not (repo / path).exists() for path in new_paths)
    assert (repo / tracked_legacy).read_text() == "safe legacy bytes\n"
    assert (repo / tracked_receipt).read_text() == "safe receipt bytes\n"


def test_stage_checkpoint_is_hash_closed_and_rejects_authority_races() -> None:
    stage = _step(STAGE_SHADOW_STEP)
    checkpoint = _step(STAGE_CHECKPOINT_STEP)
    stage_run = stage["run"]
    run = checkpoint["run"]
    owned = (
        "data/prophet_stage_shadow/ledger.jsonl",
        "data/prophet_stage_shadow/revisions.jsonl",
        "data/prophet_stage_shadow/summary.json",
    )

    assert stage["id"] == "prophet_stage_shadow"
    assert 'echo "succeeded=true" >> "$GITHUB_OUTPUT"' in stage_run
    assert "shadow._project_shadow_ledger(data_root)" in stage_run
    assert "projection.authority_error is not None" in stage_run
    assert "receipt.get(\"raw_rows\") != projection.raw_count" in stage_run
    assert "missing_ids, unexpected_ids = shadow.projection_membership_gaps(" in stage_run
    assert "or missing_ids" in stage_run
    assert "or unexpected_ids" in stage_run
    assert "append-only checkpoint refuses deletions" in stage_run
    for path in owned:
        assert path in stage_run
        assert path in run
    assert checkpoint["env"]["ACCEPTED_PROPHET_SHA"].endswith(
        "steps.prophet_accepted_source.outputs.accepted_sha }}"
    )
    assert 'merge-base --is-ancestor "$ACCEPTED_PROPHET_SHA" origin/main' in run
    for authority in ("data/prophet", "data/prophet_arena", "site/prophet"):
        assert authority in run
    assert run.count("data/prophet_stage_shadow") >= 5
    assert 'git add -- "$rel"' in run
    assert "git rebase origin/main" in run
    assert "-X theirs" not in run
    assert "no conflict override is allowed" in run


def test_stage_forward_history_is_tracked_restored_and_never_broad_published() -> None:
    ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    source_run = _step(ACCEPTED_SOURCE_STEP)["run"]
    final_run = _step("commit engine outputs")["run"]

    assert "data/prophet_stage_shadow/ledger.jsonl" not in {
        line.strip()
        for line in ignore.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    assert "data/prophet_stage_shadow" in source_run
    broad_add_i = final_run.index("git add data/ site/ reports/")
    safe_i = final_run.index("git checkout HEAD --")
    reset_i = final_run.index("git reset -q --", safe_i)
    push_i = final_run.index("push_staged_heal data/ site/ reports/ templates/")
    assert broad_add_i < safe_i < reset_i < push_i
    assert "data/prophet_stage_shadow" in final_run[safe_i:push_i]


def test_heatmap_reference_wedge_is_bounded_and_cannot_skip_prophet_again() -> None:
    """Aug 6 stopped here for 3h36m, so the Prophet step was never scheduled."""
    steps = _engine_steps()
    names = [s.get("name") for s in steps]
    heatmap = _step(HEATMAP_CAP_STEP)

    assert names.index(HEATMAP_CAP_STEP) < names.index(PROPHET_STEP)
    assert heatmap["timeout-minutes"] == 15
    assert heatmap["continue-on-error"] is True
    assert "--refresh-caps-only" in heatmap["run"]
