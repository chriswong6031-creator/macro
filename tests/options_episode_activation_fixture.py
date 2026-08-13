"""Activation-vintage slice of the live options episode ledger.

The production-record first-capture suite and the frozen v1 campaign audit are
incident replays of the 384-row activation prefix. The live ledger is allowed
to grow (it did, 384 → 1206, on the 2026-08-13 options-pit checkpoint); feeding
those replays today's full file is the same bomb as a hand-typed census
literal. The prefix is a stable watermark (``ACTIVATION_PREFIX_SHA256``) on the
live artifact, so the slice is derived from the committed ledger rather than
re-typed.
"""

from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import subprocess

from engine.neuralweb import market_memory_production_records as records

ROOT = Path(__file__).resolve().parents[1]
LEDGER_DIR = ROOT / "data" / "options_signal_episode"
CANARY_CONFIG = ROOT / "config" / "market_memory_canary.v1.json"


def jsonl_prefix(body: bytes, rows: int) -> bytes:
    """Return the first ``rows`` JSONL records, preserving each row's terminator."""
    lines = body.splitlines(True)
    if len(lines) < rows:
        raise AssertionError(
            f"owner source artifact has {len(lines)} rows; activation prefix "
            f"requires {rows}"
        )
    return b"".join(lines[:rows])


def activation_episode_body() -> bytes:
    """Return the live ledger's activation prefix, bound before believed."""
    body = (LEDGER_DIR / "episodes.jsonl").read_bytes()
    prefix = jsonl_prefix(body, records.ACTIVATION_PREFIX_ROWS)
    if sha256(prefix).hexdigest() != records.ACTIVATION_PREFIX_SHA256:
        raise AssertionError(
            "live options episode ledger prefix mutated: the activation "
            "watermark no longer hashes as the production-record contract recorded"
        )
    last = json.loads(prefix.splitlines()[-1])
    if last["episode_id"] != records.ACTIVATION_LAST_EPISODE_ID:
        raise AssertionError(
            "live options episode ledger prefix last identity drifted: "
            f"{last['episode_id']!r} != {records.ACTIVATION_LAST_EPISODE_ID!r}"
        )
    return prefix


def activation_h60_body() -> bytes:
    """Return H+60 outcomes whose episode sits in the activation prefix.

    Filtering by the prefix's episode ids — not a row-count literal — keeps
    the slice coherent when later outcomes append after the watermark.
    """
    prefix_ids = {
        json.loads(line)["episode_id"]
        for line in activation_episode_body().splitlines()
        if line
    }
    kept: list[bytes] = []
    for line in (LEDGER_DIR / "outcomes_h60.jsonl").read_bytes().splitlines(True):
        if not line.strip():
            continue
        row = json.loads(line)
        if row["episode_id"] in prefix_ids:
            kept.append(line if line.endswith(b"\n") else line + b"\n")
    return b"".join(kept)


def materialize_frozen_options_corpus(destination: Path) -> Path:
    """Write the activation-vintage episode/campaign/H+60 trio plus canary config."""
    root = destination.resolve()
    data_root = root / "data" / "options_signal_episode"
    config_root = root / "config"
    data_root.mkdir(parents=True)
    config_root.mkdir(parents=True)
    (data_root / "episodes.jsonl").write_bytes(activation_episode_body())
    shutil.copy2(LEDGER_DIR / "campaigns.jsonl", data_root / "campaigns.jsonl")
    (data_root / "outcomes_h60.jsonl").write_bytes(activation_h60_body())
    shutil.copy2(CANARY_CONFIG, config_root / "market_memory_canary.v1.json")
    return root


def materialize_activation_git_repo(destination: Path) -> Path:
    """Commit the activation prefix at the production source path so the CLI
    can ``cat-file`` it. First-activation is legal only against that vintage.
    """
    repo = materialize_frozen_options_corpus(destination)
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "activation-fixture",
        "GIT_AUTHOR_EMAIL": "activation-fixture@test",
        "GIT_COMMITTER_NAME": "activation-fixture",
        "GIT_COMMITTER_EMAIL": "activation-fixture@test",
    }
    subprocess.run(
        ["git", "-c", "user.name=activation-fixture", "-c", "user.email=activation-fixture@test", "init", "-q"],
        cwd=repo,
        check=True,
        env=env,
        timeout=30,
    )
    subprocess.run(
        [
            "git",
            "add",
            "data/options_signal_episode/episodes.jsonl",
            "data/options_signal_episode/campaigns.jsonl",
            "data/options_signal_episode/outcomes_h60.jsonl",
            "config/market_memory_canary.v1.json",
        ],
        cwd=repo,
        check=True,
        env=env,
        timeout=30,
    )
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=activation-fixture",
            "-c",
            "user.email=activation-fixture@test",
            "commit",
            "-q",
            "-m",
            "activation prefix",
        ],
        cwd=repo,
        check=True,
        env=env,
        timeout=30,
    )
    return repo
