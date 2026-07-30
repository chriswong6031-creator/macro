"""scripts/ci/push_retry.sh — the shared lane push-retry policy.

Replays the 2026-07-25 failure that motivated it: render.yml run 30167139398 built a
correct scope=all render (1121 locked special-situations rows) and then lost all five
push attempts to

    ! [remote rejected] main -> main (cannot lock ref 'refs/heads/main':
      is at <X> but expected <Y>)

~95 minutes of render discarded. That rejection is a lost RACE for the ref, not a
conflict — the old loop applied the conflict remedy (`git rebase --abort` + a growing
deterministic sleep, 70s of budget across 5 attempts) to a race that only ever needed
one more re-sync-and-push.

The assertions that matter here:
  * a ref-lock loss and a non-fast-forward classify as `contention`, NOT as a conflict
  * an interrupted rebase classifies as `rebase-conflict` and gets the SLOW ladder
  * contention backs off strictly faster than a conflict at the same attempt number
  * the backoff is jittered (the old deterministic ladder made colliding lanes collide
    again on every retry)
  * the wall-clock deadline is a hard ceiling, so no loop outlives its job timeout
  * a real two-clone race is won on a later attempt instead of being thrown away
"""

from __future__ import annotations

import os
import re
import subprocess
import textwrap
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
LIB = REPO_ROOT / "scripts" / "ci" / "push_retry.sh"


def run_sh(body: str, *, env: dict | None = None, cwd: Path | None = None) -> subprocess.CompletedProcess:
    """Source the library into a `bash -e` shell (GitHub's shell) and run `body`."""
    script = f'. "{LIB}"\n' + textwrap.dedent(body)
    full_env = {**os.environ, **(env or {})}
    return subprocess.run(
        ["bash", "-eo", "pipefail", "-c", script],
        capture_output=True,
        text=True,
        env=full_env,
        cwd=str(cwd or REPO_ROOT),
    )


def test_library_exists_and_is_sourceable():
    assert LIB.is_file(), f"{LIB} missing — the workflows source it by path"
    r = run_sh('push_retry_init "smoke"; echo "attempt=$PUSH_ATTEMPT max=$PUSH_MAX_ATTEMPTS"')
    assert r.returncode == 0, r.stderr
    assert "attempt=0 max=10" in r.stdout


# ---------------------------------------------------------------------------
# 1. Classification — the load-bearing table
# ---------------------------------------------------------------------------

CONTENTION_OUTPUTS = [
    # the exact 2026-07-25 render.yml run 30167139398 rejection
    "To github.com:user/repo.git\n ! [remote rejected] main -> main "
    "(cannot lock ref 'refs/heads/main': is at 0f2a1b3 but expected 9c8d7e6)\n"
    "error: failed to push some refs",
    "error: cannot lock ref 'refs/heads/main': unable to resolve reference",
    "error: Unable to create '/repo/.git/refs/heads/main.lock': File exists.",
    " ! [rejected]        main -> main (fetch first)\nerror: failed to push some refs",
    " ! [rejected]        main -> main (non-fast-forward)",
    "hint: Updates were rejected because the remote contains work that you do not have",
    " ! [rejected]        main -> main (stale info)",
]

NON_CONTENTION_OUTPUTS = [
    "remote: Permission to user/repo.git denied to dashboard-bot.\nfatal: unable to access",
    "remote: error: GH006: Protected branch update failed for refs/heads/main.",
    "remote: error: hook declined to update refs/heads/main",
]


@pytest.mark.parametrize("out", CONTENTION_OUTPUTS)
def test_ref_lock_and_non_ff_classify_as_contention(out):
    """A lost ref race must NOT be treated as a conflict — that was the whole bug."""
    r = run_sh(f'push_retry_init "t"; push_classify 1 {out!r}; echo "$PUSH_FAIL_CLASS"')
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "contention", f"misclassified: {out!r}"


@pytest.mark.parametrize("out", NON_CONTENTION_OUTPUTS)
def test_auth_and_hook_rejections_are_not_contention(out):
    """Retrying faster never fixes a permission or hook rejection — don't call it a race."""
    r = run_sh(f'push_retry_init "t"; push_classify 1 {out!r}; echo "$PUSH_FAIL_CLASS"')
    assert r.stdout.strip() == "push-error", f"misclassified: {out!r}"


def test_signal_death_classifies_as_push_timeout():
    """The lanes alarm-bound git ops (macOS runners have no GNU timeout); a SIGALRM kill
    exits >=128 with no output and must not be read as a race."""
    r = run_sh('push_retry_init "t"; push_classify 142 ""; echo "$PUSH_FAIL_CLASS"')
    assert r.stdout.strip() == "push-timeout"


def test_git_exit_128_without_sigalrm_is_not_misclassified_as_timeout():
    out = "fatal: could not read Username for 'https://github.com': No such device or address"
    r = run_sh(f'push_retry_init "t"; push_classify 128 {out!r}; echo "$PUSH_FAIL_CLASS"')
    assert r.stdout.strip() == "push-error"


def test_every_class_has_a_plain_word_reason():
    r = run_sh(
        """
        push_retry_init "t"
        for c in contention rebase-conflict push-timeout push-error sync; do
          PUSH_FAIL_CLASS="$c"; printf '%s: %s\\n' "$c" "$(push_why)"
        done
        """
    )
    assert r.returncode == 0, r.stderr
    for line in r.stdout.strip().splitlines():
        cls, _, why = line.partition(": ")
        assert why.strip(), f"{cls} has no reason text"
    assert "no conflict, just retry" in r.stdout  # contention says so in plain words


# ---------------------------------------------------------------------------
# 2. Budgets — attempts and the hard wall-clock ceiling
# ---------------------------------------------------------------------------


def test_attempt_budget_is_ten_by_default_not_five():
    r = run_sh(
        """
        push_retry_init "t"
        n=0; while push_attempt; do n=$((n+1)); done
        echo "attempts=$n stop=$PUSH_STOP"
        """
    )
    assert "attempts=10" in r.stdout
    assert "attempt budget exhausted" in r.stdout


def test_attempt_budget_is_tunable():
    r = run_sh(
        """
        PUSH_MAX_ATTEMPTS=3
        push_retry_init "t"
        n=0; while push_attempt; do n=$((n+1)); done
        echo "attempts=$n"
        """
    )
    assert "attempts=3" in r.stdout


def test_deadline_is_a_hard_ceiling_that_stops_the_loop_early():
    """A job must never hang past its timeout-minutes waiting for a ref."""
    r = run_sh(
        """
        PUSH_BUDGET_SECS=0
        push_retry_init "t"
        n=0; while push_attempt; do n=$((n+1)); done
        echo "attempts=$n stop=$PUSH_STOP"
        """
    )
    # the first attempt is always allowed; the deadline stops everything after it
    assert "attempts=1" in r.stdout
    assert "time budget exhausted" in r.stdout


def test_backoff_never_sleeps_past_the_deadline():
    r = run_sh(
        """
        sleep() { echo "SLEPT $1"; }
        PUSH_BUDGET_SECS=3
        push_retry_init "t"
        push_attempt
        PUSH_FAIL_CLASS=rebase-conflict   # slow ladder, would want far more than 3s
        push_backoff
        """
    )
    slept = [int(l.split()[1]) for l in r.stdout.splitlines() if l.startswith("SLEPT")]
    assert slept and slept[0] <= 3, r.stdout


# ---------------------------------------------------------------------------
# 3. Backoff shape — the right remedy per class, and jitter
# ---------------------------------------------------------------------------


def _backoff_samples(cls: str, attempt: int, n: int = 30) -> list[int]:
    r = run_sh(
        f"""
        sleep() {{ echo "SLEPT $1"; }}
        for _ in $(seq {n}); do
          push_retry_init "t"
          PUSH_ATTEMPT={attempt}
          PUSH_FAIL_CLASS={cls}
          push_backoff
        done
        """
    )
    assert r.returncode == 0, r.stderr
    return [int(l.split()[1]) for l in r.stdout.splitlines() if l.startswith("SLEPT")]


def test_contention_backs_off_faster_than_a_real_conflict():
    """The core policy split: a lost ref race wants to retry INTO main's next gap; a
    conflict wants main to settle first.

    Compared on the mean, not the extremes — the ladders are fully jittered, so their
    ranges are allowed to overlap at the tails. What must hold is that spending ten
    attempts on contention is far cheaper in wall-clock than spending ten on conflicts.
    """
    for attempt in (1, 3, 5, 8):
        contention = _backoff_samples("contention", attempt, n=60)
        conflict = _backoff_samples("rebase-conflict", attempt, n=60)
        mean_c = sum(contention) / len(contention)
        mean_x = sum(conflict) / len(conflict)
        assert mean_c * 1.5 < mean_x, (
            f"attempt {attempt}: contention mean {mean_c:.1f} is not decisively faster "
            f"than conflict mean {mean_x:.1f}"
        )


def test_backoff_is_jittered_not_a_deterministic_ladder():
    """Load-bearing: the old `sleep $((i * 7))` was identical in every lane, so two
    lanes that collided once collided again on every retry."""
    for cls in ("contention", "rebase-conflict"):
        samples = _backoff_samples(cls, 4, n=40)
        assert len(set(samples)) > 1, f"{cls} backoff is deterministic: {samples}"


def test_backoff_is_capped_so_attempts_stay_inside_the_budget():
    # contention cap 20 -> jitter tops out at 20 + 20/2 = 30
    assert max(_backoff_samples("contention", 20)) <= 30
    # rebase-conflict cap 60 -> jitter tops out at 60 + 60/2 = 90
    assert max(_backoff_samples("rebase-conflict", 20)) <= 90


def test_backoff_logs_the_class_and_the_attempt_number():
    """`grep` on a failed run must show WHICH remedy was spent, and how often."""
    r = run_sh(
        """
        sleep() { :; }
        push_retry_init "rendered site"
        push_attempt
        PUSH_FAIL_CLASS=contention
        push_backoff
        """
    )
    assert "rendered site push attempt 1/10 failed [contention]" in r.stdout
    assert "budget left" in r.stdout


def test_class_counters_census_the_two_failure_modes_separately():
    r = run_sh(
        """
        sleep() { :; }
        push_retry_init "t"
        for c in contention contention rebase-conflict push-error; do
          push_attempt; PUSH_FAIL_CLASS="$c"; push_backoff
        done
        echo "contention=$PUSH_N_CONTENTION conflict=$PUSH_N_CONFLICT other=$PUSH_N_OTHER"
        """
    )
    assert "contention=2 conflict=1 other=1" in r.stdout


# ---------------------------------------------------------------------------
# 4. push_abort_rebase — only an interrupted rebase is a conflict
# ---------------------------------------------------------------------------


def _init_repo(path: Path) -> None:
    subprocess.run(["git", "init", "-q", "-b", "main", str(path)], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.name", "t"], check=True)


def _git_output(repo: Path, *args: str, input_text: str | None = None) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
        input=input_text,
    ).stdout.strip()


def _object_is_local(repo: Path, oid: str) -> bool:
    loose = repo / ".git" / "objects" / oid[:2] / oid[2:]
    if loose.exists():
        return True
    for index in (repo / ".git" / "objects" / "pack").glob("*.idx"):
        packed = subprocess.run(
            ["git", "verify-pack", "-v", index],
            cwd=repo,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        if any(line.startswith(f"{oid} ") for line in packed.splitlines()):
            return True
    return False


def test_metadata_replay_preserves_new_main_without_fetching_promised_blobs(tmp_path):
    """The render's common race path is a tree merge, not a checkout/rebase.

    A concurrent data commit must survive, the generated site must land, and an
    unchanged 1 MiB promised blob must remain absent from the blobless lane clone.
    """
    bare = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(bare)], check=True)
    _git_output(bare, "config", "uploadpack.allowFilter", "true")

    seed = tmp_path / "seed"
    _init_repo(seed)
    (seed / "site").mkdir()
    (seed / "data").mkdir()
    (seed / "site" / "index.html").write_text("<html>old</html>\n")
    (seed / "site" / "unchanged.bin").write_bytes(b"x" * 1024 * 1024)
    (seed / "data" / "live.txt").write_text("base\n")
    _git_output(seed, "add", ".")
    _git_output(seed, "commit", "-m", "seed")
    _git_output(seed, "push", "-q", str(bare), "main")

    lane = tmp_path / "lane"
    subprocess.run(
        [
            "git",
            "clone",
            "-q",
            "--no-checkout",
            "--filter=blob:none",
            "--depth=1",
            "--branch",
            "main",
            f"file://{bare}",
            str(lane),
        ],
        check=True,
    )
    _git_output(lane, "config", "user.email", "render@example.test")
    _git_output(lane, "config", "user.name", "render-test")
    render_parent = _git_output(lane, "rev-parse", "HEAD")
    stable_blob = _git_output(lane, "rev-parse", "HEAD:site/unchanged.bin")
    assert not _object_is_local(lane, stable_blob)

    # Build a site-only render commit directly from the index. No checkout is needed.
    _git_output(lane, "read-tree", "HEAD")
    rendered_blob = _git_output(
        lane,
        "hash-object",
        "-w",
        "--stdin",
        input_text="<html>fresh render</html>\n",
    )
    _git_output(
        lane,
        "update-index",
        "--add",
        "--cacheinfo",
        "100644",
        rendered_blob,
        "site/index.html",
    )
    rendered_tree = _git_output(lane, "write-tree", "--missing-ok")
    render_commit = _git_output(
        lane,
        "commit-tree",
        rendered_tree,
        "-p",
        render_parent,
        input_text="render: site re-render\n",
    )
    assert not _object_is_local(lane, stable_blob)

    # Main advances while the render is running, but only outside generated outputs.
    (seed / "data" / "live.txt").write_text("concurrent main\n")
    (seed / "code.txt").write_text("new code\n")
    _git_output(seed, "add", "data/live.txt", "code.txt")
    _git_output(seed, "commit", "-m", "advance main")
    _git_output(seed, "push", "-q", str(bare), "main")
    _git_output(lane, "fetch", "-q", "--depth=2", "origin", "main")
    concurrent_main = _git_output(lane, "rev-parse", "origin/main")
    assert not _object_is_local(lane, stable_blob)

    index_path = tmp_path / "publish.index"
    r = run_sh(
        """
        replay=$(push_metadata_replay_commit \
          "$RENDER_PARENT" origin/main "$RENDER_COMMIT" \
          "render: site re-render" "$PUBLISH_INDEX")
        echo "replay=$replay"
        """,
        env={
            "RENDER_PARENT": render_parent,
            "RENDER_COMMIT": render_commit,
            "PUBLISH_INDEX": str(index_path),
        },
        cwd=lane,
    )
    assert r.returncode == 0, f"{r.stdout}\n{r.stderr}"
    replay = next(line.removeprefix("replay=") for line in r.stdout.splitlines() if line.startswith("replay="))
    assert not _object_is_local(lane, stable_blob)
    _git_output(lane, "update-ref", "refs/heads/render-publish-test", replay)
    assert not _object_is_local(lane, stable_blob)
    _git_output(
        lane,
        "push",
        "-q",
        "origin",
        "refs/heads/render-publish-test:refs/heads/main",
    )
    published = _git_output(bare, "rev-parse", "refs/heads/main")
    assert _git_output(bare, "rev-parse", f"{published}^") == concurrent_main
    assert _git_output(bare, "show", f"{published}:site/index.html") == (
        "<html>fresh render</html>"
    )
    assert _git_output(bare, "show", f"{published}:data/live.txt") == "concurrent main"
    assert _git_output(bare, "show", f"{published}:code.txt") == "new code"
    assert not index_path.exists()
    assert not _object_is_local(lane, stable_blob)


def test_metadata_replay_reports_a_real_same_path_conflict(tmp_path):
    repo = tmp_path / "repo"
    _init_repo(repo)
    (repo / "site").mkdir()
    (repo / "site" / "index.html").write_text("base\n")
    _git_output(repo, "add", ".")
    _git_output(repo, "commit", "-m", "base")
    base = _git_output(repo, "rev-parse", "HEAD")

    (repo / "site" / "index.html").write_text("render\n")
    _git_output(repo, "commit", "-am", "render")
    render_commit = _git_output(repo, "rev-parse", "HEAD")
    _git_output(repo, "checkout", "-q", "-b", "new-main", base)
    (repo / "site" / "index.html").write_text("new main\n")
    _git_output(repo, "commit", "-am", "new main")
    new_main = _git_output(repo, "rev-parse", "HEAD")

    r = run_sh(
        """
        if push_metadata_replay_commit "$BASE" "$ONTO" "$RENDER" \
             "should conflict" "$INDEX"; then
          echo "unexpected success"
          exit 1
        fi
        echo "fallback required"
        """,
        env={
            "BASE": base,
            "ONTO": new_main,
            "RENDER": render_commit,
            "INDEX": str(tmp_path / "conflict.index"),
        },
        cwd=repo,
    )
    assert r.returncode == 0, f"{r.stdout}\n{r.stderr}"
    assert "fallback required" in r.stdout


def test_abort_rebase_flags_a_conflict_only_when_a_rebase_is_in_progress(tmp_path):
    repo = tmp_path / "repo"
    _init_repo(repo)
    (repo / "a").write_text("a")
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "c"], check=True)

    # no rebase in progress: a contention verdict must survive untouched
    r = run_sh(
        'push_retry_init "t"; PUSH_FAIL_CLASS=contention; push_abort_rebase; echo "$PUSH_FAIL_CLASS"',
        cwd=repo,
    )
    assert r.stdout.strip() == "contention", r.stderr

    # a stopped rebase IS a conflict, and gets the slow ladder
    (repo / ".git" / "rebase-merge").mkdir()
    r = run_sh(
        'push_retry_init "t"; PUSH_FAIL_CLASS=contention; push_abort_rebase; echo "$PUSH_FAIL_CLASS"',
        cwd=repo,
    )
    assert r.stdout.strip() == "rebase-conflict", r.stderr


# ---------------------------------------------------------------------------
# 5. Step summary — contention becomes visible instead of silent
# ---------------------------------------------------------------------------


def test_summary_reports_attempts_used_and_the_contention_census(tmp_path):
    summary = tmp_path / "summary.md"
    summary.touch()
    r = run_sh(
        """
        sleep() { :; }
        push_retry_init "rendered site"
        for _ in 1 2 3; do push_attempt; PUSH_FAIL_CLASS=contention; push_backoff; done
        push_attempt
        push_won
        """,
        env={"GITHUB_STEP_SUMMARY": str(summary)},
    )
    assert r.returncode == 0, r.stderr
    text = summary.read_text()
    assert "push-retry" in text and "rendered site" in text
    assert "attempts=4/10" in text
    assert "ref-lock losses=3" in text


def test_summary_is_quiet_on_a_clean_first_attempt_win(tmp_path):
    """20 loops across the lanes — a summary line per successful push would be noise."""
    summary = tmp_path / "summary.md"
    summary.touch()
    run_sh(
        'push_retry_init "t"; push_attempt; push_won',
        env={"GITHUB_STEP_SUMMARY": str(summary)},
    )
    assert summary.read_text() == ""


def test_give_up_always_reports_why(tmp_path):
    summary = tmp_path / "summary.md"
    summary.touch()
    run_sh(
        """
        PUSH_MAX_ATTEMPTS=2
        push_retry_init "engine outputs"
        sleep() { :; }
        while push_attempt; do PUSH_FAIL_CLASS=contention; push_backoff; done
        push_lost
        """,
        env={"GITHUB_STEP_SUMMARY": str(summary)},
    )
    text = summary.read_text()
    assert "NOT pushed" in text and "attempt budget exhausted" in text


def test_give_up_is_silent_when_the_loop_left_on_a_win(tmp_path):
    """asia-close's data commit sits inside an if/else, so its loop exits with `break`
    and falls through to the give-up tail even after a successful push. push_lost must
    not claim a loss there."""
    summary = tmp_path / "summary.md"
    summary.touch()
    r = run_sh(
        """
        sleep() { :; }
        push_retry_init "asia data"
        while push_attempt; do
          echo "pushed asia data (attempt $PUSH_ATTEMPT)"; push_won; break
        done
        push_lost
        """,
        env={"GITHUB_STEP_SUMMARY": str(summary)},
    )
    assert r.returncode == 0, r.stderr
    assert "pushed asia data (attempt 1)" in r.stdout
    assert "NOT pushed" not in summary.read_text(), summary.read_text()


def test_summary_is_a_no_op_outside_actions():
    """Sourcing the library locally (or in a test) must never blow up on a missing
    GITHUB_STEP_SUMMARY."""
    env = {k: v for k, v in os.environ.items() if k != "GITHUB_STEP_SUMMARY"}
    r = subprocess.run(
        ["bash", "-eo", "pipefail", "-c", f'. "{LIB}"\npush_retry_init "t"; push_attempt; push_lost; echo done'],
        capture_output=True, text=True, env=env, cwd=str(REPO_ROOT),
    )
    assert r.returncode == 0, r.stderr
    assert "done" in r.stdout


# ---------------------------------------------------------------------------
# 6. End-to-end — a real lost race is WON on a later attempt, not thrown away
# ---------------------------------------------------------------------------


def test_real_race_against_a_moving_main_is_won_on_a_retry(tmp_path):
    """Two clones of one main, exactly the lanes' situation. Clone B commits, clone A
    lands first, so B's push is rejected non-fast-forward. Under the old loop that
    burned an attempt on the conflict remedy; here it must classify as contention and
    the very next rebase+push must land B's work.
    """
    bare = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(bare)], check=True)

    seed = tmp_path / "seed"
    _init_repo(seed)
    (seed / "base").write_text("base")
    subprocess.run(["git", "-C", str(seed), "add", "."], check=True)
    subprocess.run(["git", "-C", str(seed), "commit", "-qm", "seed"], check=True)
    subprocess.run(["git", "-C", str(seed), "push", "-q", str(bare), "main"], check=True)

    def clone(name: str) -> Path:
        p = tmp_path / name
        subprocess.run(["git", "clone", "-q", str(bare), str(p)], check=True)
        subprocess.run(["git", "-C", str(p), "config", "user.email", "t@t"], check=True)
        subprocess.run(["git", "-C", str(p), "config", "user.name", "t"], check=True)
        return p

    a, b = clone("a"), clone("b")

    # B renders its work and commits it locally...
    (b / "rendered.txt").write_text("1121 locked rows")
    subprocess.run(["git", "-C", str(b), "add", "."], check=True)
    subprocess.run(["git", "-C", str(b), "commit", "-qm", "render: site re-render"], check=True)

    # ...and A lands on main first, so B's push is now stale.
    (a / "other.txt").write_text("marketing-publish outbox run")
    subprocess.run(["git", "-C", str(a), "add", "."], check=True)
    subprocess.run(["git", "-C", str(a), "commit", "-qm", "other lane"], check=True)
    subprocess.run(["git", "-C", str(a), "push", "-q", "origin", "main"], check=True)

    r = run_sh(
        """
        sleep() { :; }
        push_retry_init "rendered site"
        while push_attempt; do
          git fetch origin main >/dev/null 2>&1 || true
          if git pull --rebase --autostash -X theirs origin main >/dev/null 2>&1; then
            if push_do; then echo "PUSHED on attempt $PUSH_ATTEMPT"; push_won; exit 0; fi
          fi
          push_abort_rebase
          push_backoff
        done
        push_lost
        echo "GAVE UP after $PUSH_ATTEMPT"
        exit 1
        """,
        cwd=b,
    )
    assert r.returncode == 0, f"the render was discarded:\n{r.stdout}\n{r.stderr}"
    assert "PUSHED on attempt 1" in r.stdout or "PUSHED on attempt 2" in r.stdout, r.stdout

    # both lanes' work is on main
    files = subprocess.run(
        ["git", "-C", str(bare), "ls-tree", "-r", "--name-only", "main"],
        capture_output=True, text=True, check=True,
    ).stdout.split()
    assert "rendered.txt" in files, "the render never landed"
    assert "other.txt" in files, "the racing lane's commit was clobbered"


def test_repeated_ref_lock_losses_are_retried_far_past_the_old_five(tmp_path):
    """The 2026-07-25 replay: main rejects with a ref-lock loss over and over. The old
    loop gave up after 5; this one must keep going and still land the render."""
    fakebin = tmp_path / "bin"
    fakebin.mkdir()
    counter = tmp_path / "n"
    counter.write_text("0")
    real_git = subprocess.run(["which", "git"], capture_output=True, text=True).stdout.strip()
    (fakebin / "git").write_text(
        textwrap.dedent(
            f"""\
            #!/usr/bin/env bash
            if [ "$1" = "push" ]; then
              n=$(cat {counter}); n=$((n+1)); echo "$n" > {counter}
              if [ "$n" -le 7 ]; then
                echo "To github.com:user/repo.git" >&2
                echo " ! [remote rejected] main -> main (cannot lock ref 'refs/heads/main': is at aaa but expected bbb)" >&2
                exit 1
              fi
              echo "pushed for real"; exit 0
            fi
            exec {real_git} "$@"
            """
        )
    )
    (fakebin / "git").chmod(0o755)

    r = run_sh(
        """
        sleep() { :; }
        push_retry_init "rendered site"
        while push_attempt; do
          if push_do; then echo "PUSHED on attempt $PUSH_ATTEMPT"; push_won; exit 0; fi
          push_abort_rebase
          push_backoff
        done
        push_lost
        echo "GAVE UP after $PUSH_ATTEMPT"; exit 1
        """,
        env={"PATH": f"{fakebin}:{os.environ['PATH']}"},
        cwd=tmp_path,
    )
    assert r.returncode == 0, f"gave up on a pure ref-lock race:\n{r.stdout}"
    assert "PUSHED on attempt 8" in r.stdout, r.stdout
    assert "[contention]" in r.stdout
    assert "[rebase-conflict]" not in r.stdout, "a ref-lock loss was miscalled a conflict"


# ---------------------------------------------------------------------------
# 7. PUSH_ALARM — 15 of the 21 loops alarm-bound their push
# ---------------------------------------------------------------------------


def _fake_git(tmp_path: Path, push_body: str) -> Path:
    """A `git` earlier on PATH whose `push` runs push_body; everything else is real."""
    fakebin = tmp_path / "bin"
    fakebin.mkdir(exist_ok=True)
    real_git = subprocess.run(["which", "git"], capture_output=True, text=True).stdout.strip()
    (fakebin / "git").write_text(
        f'#!/usr/bin/env bash\nif [ "$1" = "push" ]; then\n{push_body}\nfi\nexec {real_git} "$@"\n'
    )
    (fakebin / "git").chmod(0o755)
    return fakebin


def test_alarm_bounded_push_still_pushes(tmp_path):
    """daily.yml (×14) and closing-bell set PUSH_ALARM=420 because macOS runners have no
    GNU timeout. If the perl wrapper were malformed, every one of those pushes would
    break — so pin the happy path, not just the timeout."""
    fakebin = _fake_git(tmp_path, '  echo "PUSHED args=[$*]"; exit 0')
    r = run_sh(
        """
        PUSH_ALARM=420
        push_retry_init "alarm"
        push_attempt
        if push_do; then echo "OK class=[$PUSH_FAIL_CLASS]"; else echo "BROKEN rc=$?"; fi
        """,
        env={"PATH": f"{fakebin}:{os.environ['PATH']}"},
        cwd=tmp_path,
    )
    assert r.returncode == 0, r.stderr
    assert "PUSHED args=[push]" in r.stdout, r.stdout
    assert "OK class=[]" in r.stdout, r.stdout


def test_alarm_actually_kills_a_hung_push_and_classifies_it(tmp_path):
    """The 2026-07-17 incident behind the alarm: a hung push ate 57 minutes. The alarm
    must fire, and a SIGALRM kill must not be miscalled a race."""
    fakebin = _fake_git(tmp_path, "  sleep 30")
    r = run_sh(
        """
        PUSH_ALARM=1
        push_retry_init "alarm"
        push_attempt
        if push_do; then echo "NOT KILLED"; else echo "killed class=$PUSH_FAIL_CLASS"; fi
        """,
        env={"PATH": f"{fakebin}:{os.environ['PATH']}"},
        cwd=tmp_path,
    )
    assert "killed class=push-timeout" in r.stdout, r.stdout


def test_push_do_passes_extra_args_through(tmp_path):
    fakebin = _fake_git(tmp_path, '  echo "ARGS=[$*]"; exit 0')
    r = run_sh(
        'push_retry_init "t"; push_attempt; push_do origin HEAD:main',
        env={"PATH": f"{fakebin}:{os.environ['PATH']}"},
        cwd=tmp_path,
    )
    assert "ARGS=[push origin HEAD:main]" in r.stdout, r.stdout


# ---------------------------------------------------------------------------
# 8. End-to-end — render.yml's REAL run: block, executed against real git repos
#
# The rest of this file proves the library and the lane FILE CONTENTS. Neither
# catches a lane whose surrounding shell mis-wires the policy — a stray `fi`, a
# push_won that never runs, a give-up path that swallows the error. So run the
# shipped block itself, verbatim, with the python guards stubbed and the GitHub
# ${{ }} expressions substituted.
# ---------------------------------------------------------------------------

RENDER_STEP = "commit rendered site (site/ ONLY — never data/, so ledgers stay pristine)"


def _lane_block(lane: str, step_name: str, subs: dict) -> str:
    doc = yaml.safe_load((REPO_ROOT / ".github" / "workflows" / lane).read_text())
    for job in doc["jobs"].values():
        for s in job.get("steps") or []:
            if s.get("name") == step_name:
                body = s["run"]
                return re.sub(r"\$\{\{([^}]*)\}\}", lambda m: subs.get(m.group(1).strip(), ""), body)
    raise AssertionError(f"{lane}: step {step_name!r} not found")


def _lane_fixture(tmp_path: Path, rejects: int = 0):
    """A bare origin + a lane clone holding a fresh render + a racing lane that has
    already landed on main, so the lane's first push is stale."""
    bare = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(bare)], check=True)

    def git(repo, *a):
        return subprocess.run(["git", "-C", str(repo), *a], check=True,
                              capture_output=True, text=True)

    seed = tmp_path / "seed"
    _init_repo(seed)
    (seed / "site").mkdir()
    (seed / "site" / "index.html").write_text("<html>old</html>")
    git(seed, "add", "."); git(seed, "commit", "-qm", "seed")
    git(seed, "push", "-q", str(bare), "main")

    lane = tmp_path / "lane"
    subprocess.run(["git", "clone", "-q", str(bare), str(lane)], check=True)
    git(lane, "config", "user.email", "t@t"); git(lane, "config", "user.name", "t")
    other = tmp_path / "other"
    subprocess.run(["git", "clone", "-q", str(bare), str(other)], check=True)
    git(other, "config", "user.email", "t@t"); git(other, "config", "user.name", "t")

    # the render this run must not lose
    (lane / "site" / "index.html").write_text("<html>FRESH RENDER</html>")
    (lane / "site" / "premiumdata").mkdir(parents=True, exist_ok=True)
    (lane / "site" / "premiumdata" / "special_situations.json").write_text('{"rows": 1121}')
    # a throwaway data/ write — the step commits site/ ONLY (the nightly owns ledgers)
    (lane / "data").mkdir(exist_ok=True)
    (lane / "data" / "ledger.json").write_text('{"lane": "throwaway"}')

    # a racing lane lands on main first
    (other / "other.txt").write_text("marketing-publish outbox run")
    git(other, "add", "."); git(other, "commit", "-qm", "other lane")
    git(other, "push", "-q", "origin", "main")

    stub = tmp_path / "bin"
    stub.mkdir()
    for name in ("python", "python3"):
        (stub / name).write_text('#!/usr/bin/env bash\nexit 0\n')
        (stub / name).chmod(0o755)
    if rejects:
        counter = tmp_path / "n"
        counter.write_text("0")
        real_git = subprocess.run(["which", "git"], capture_output=True, text=True).stdout.strip()
        (stub / "git").write_text(textwrap.dedent(f"""\
            #!/usr/bin/env bash
            if [ "$1" = "push" ]; then
              n=$(cat {counter}); n=$((n+1)); echo "$n" > {counter}
              if [ "$n" -le {rejects} ]; then
                echo " ! [remote rejected] main -> main (cannot lock ref 'refs/heads/main': is at aaa but expected bbb)" >&2
                exit 1
              fi
            fi
            exec {real_git} "$@"
            """))
        (stub / "git").chmod(0o755)
    return bare, lane, stub


def _run_lane(block: str, lane: Path, stub: Path, summary: Path, render_ok: bool):
    runner_temp = summary.parent / "runner-temp"
    runner_temp.mkdir(exist_ok=True)
    env = {**os.environ, "PATH": f"{stub}:{os.environ['PATH']}",
           "GITHUB_WORKSPACE": str(REPO_ROOT), "GITHUB_STEP_SUMMARY": str(summary),
           "RUNNER_TEMP": str(runner_temp), "GITHUB_RUN_ID": "123",
           "GITHUB_RUN_ATTEMPT": "1"}
    if render_ok:
        env["RENDER_OK"] = "1"
    else:
        env.pop("RENDER_OK", None)
    # no real sleeping: the backoff ladder is unit-tested above
    return subprocess.run(["bash", "-eo", "pipefail", "-c", "sleep() { :; }\n" + block],
                          cwd=str(lane), capture_output=True, text=True, env=env)


def test_render_lane_block_lands_the_render_over_a_racing_commit(tmp_path):
    block = _lane_block("render.yml", RENDER_STEP,
                        {"steps.pick.outputs.scope": "all",
                         "steps.pick.outputs.rendered_from": "deadbeef"})
    bare, lane, stub = _lane_fixture(tmp_path)
    summary = tmp_path / "summary.md"; summary.touch()
    r = _run_lane(block, lane, stub, summary, render_ok=True)
    assert r.returncode == 0, f"{r.stdout}\n{r.stderr}"

    files = subprocess.run(["git", "-C", str(bare), "ls-tree", "-r", "--name-only", "main"],
                           capture_output=True, text=True, check=True).stdout.split()
    log = subprocess.run(["git", "-C", str(bare), "log", "--oneline", "-5", "main"],
                         capture_output=True, text=True, check=True).stdout

    assert "site/premiumdata/special_situations.json" in files, "the render never landed"
    assert "other.txt" in files, "the racing lane's commit was clobbered"
    assert "data/ledger.json" not in files, "the step committed data/ — must be site/ ONLY"
    assert "from=deadbeef" in log, "RENDER_OK=1 run did not stamp the from= watermark"
    assert summary.read_text() == "", "a first-attempt win should stay out of the summary"


def test_render_lane_block_survives_seven_ref_lock_losses(tmp_path):
    """The 2026-07-25 incident, replayed against the shipped lane shell. The old loop
    gave up at 5 and discarded ~95 minutes of render."""
    block = _lane_block("render.yml", RENDER_STEP,
                        {"steps.pick.outputs.scope": "all",
                         "steps.pick.outputs.rendered_from": "deadbeef"})
    bare, lane, stub = _lane_fixture(tmp_path, rejects=7)
    summary = tmp_path / "summary.md"; summary.touch()
    r = _run_lane(block, lane, stub, summary, render_ok=True)
    assert r.returncode == 0, f"{r.stdout}\n{r.stderr}"
    assert "pushed rendered site on attempt 8" in r.stdout, r.stdout
    assert "[contention]" in r.stdout
    assert "[rebase-conflict]" not in r.stdout, "a ref-lock loss was miscalled a conflict"

    files = subprocess.run(["git", "-C", str(bare), "ls-tree", "-r", "--name-only", "main"],
                           capture_output=True, text=True, check=True).stdout.split()
    assert "site/premiumdata/special_situations.json" in files, "the render was discarded"

    text = summary.read_text()
    assert "attempts=8/20" in text and "ref-lock losses=7" in text, text
    assert "rebase conflicts=0" in text, text


def test_render_lane_never_invokes_publish_on_a_partial_render():
    """A cancelled, timed-out, or guard-failed render must keep last-good main live."""
    doc = yaml.safe_load((REPO_ROOT / ".github" / "workflows" / "render.yml").read_text())
    steps = doc["jobs"]["render"]["steps"]
    publish = next(step for step in steps if step.get("name") == RENDER_STEP)

    assert publish["if"] == "${{ success() && steps.render_pages.outputs.complete == 'true' }}"
    assert "(scope=$SCOPE, from=$FROM)" in publish["run"]
    assert '(scope=$SCOPE)"' not in publish["run"]


# ---------------------------------------------------------------------------
# 9. The lanes actually use it
# ---------------------------------------------------------------------------

LANES = [
    "render.yml",
    "engine-render.yml",
    "daily.yml",
    "closing-bell.yml",
    "asia-close.yml",
    "weekly.yml",
    "earlyclose.yml",
]


def test_no_lane_still_carries_the_old_five_attempt_ladder():
    stale = []
    for lane in LANES:
        text = (REPO_ROOT / ".github" / "workflows" / lane).read_text()
        for pattern in ("for i in 1 2 3 4 5", "sleep $((i * 7))"):
            if pattern in text:
                stale.append(f"{lane}: {pattern}")
    assert not stale, "lanes still on the old deterministic ladder: " + ", ".join(stale)


def test_a_raised_time_budget_is_never_decorative():
    """A lane that raises PUSH_BUDGET_SECS must raise PUSH_MAX_ATTEMPTS with it.

    Measured 2026-07-25 against render.yml's real run block: ten contention retries
    spend only ~2 min of backoff, so the default attempt cap stops the loop with most
    of a raised 600s budget untouched — the budget reads as "we'll wait 10 minutes for
    the ref" while the loop actually gives up in two. On these lanes the DEADLINE is
    meant to be the governor; the attempt count is not doing the safety work.
    """
    for lane in LANES:
        text = (REPO_ROOT / ".github" / "workflows" / lane).read_text()
        lines = text.splitlines()
        for i, line in enumerate(lines):
            if not re.match(r"\s*PUSH_BUDGET_SECS=(\d+)", line):
                continue
            budget = int(re.match(r"\s*PUSH_BUDGET_SECS=(\d+)", line).group(1))
            if budget <= 420:
                continue
            window = "\n".join(lines[max(0, i - 4): i + 6])
            m = re.search(r"PUSH_MAX_ATTEMPTS=(\d+)", window)
            assert m, (
                f"{lane}:{i + 1} raises PUSH_BUDGET_SECS to {budget} but leaves the "
                f"attempt cap at the default — the extra budget can never be spent"
            )
            assert int(m.group(1)) > 10, (
                f"{lane}:{i + 1} raises the budget to {budget} but caps attempts at "
                f"{m.group(1)}"
            )


def test_every_lane_loop_sources_the_shared_policy():
    for lane in LANES:
        text = (REPO_ROOT / ".github" / "workflows" / lane).read_text()
        n_loops = text.count("while push_attempt")
        assert n_loops, f"{lane} carries no push_attempt loop"
        assert text.count("push_retry_init") == n_loops, f"{lane}: init/loop count mismatch"
        assert text.count('scripts/ci/push_retry.sh"') >= 1, f"{lane} never sources the policy"
