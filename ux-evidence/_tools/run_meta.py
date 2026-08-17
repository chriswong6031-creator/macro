#!/usr/bin/env python3
"""Evidence-system run metadata. Full 40-char SHA only."""
from __future__ import annotations

import json
import platform
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path

from paths import evidence_root, repo_root


SCHEMA_CANDIDATE = "1.0-candidate"
SCHEMA_FROZEN = "1.0"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def utc_compact() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _git(*args: str) -> str:
    return subprocess.check_output(
        ["git", *args], cwd=str(repo_root()), text=True, stderr=subprocess.DEVNULL
    ).strip()


def git_head_sha() -> str:
    sha = _git("rev-parse", "HEAD")
    if len(sha) != 40:
        raise RuntimeError(f"expected 40-char SHA, got {sha!r}")
    return sha


def git_head_short() -> str:
    return git_head_sha()[:12]


def working_tree_dirty() -> bool:
    return bool(_git("status", "--porcelain"))


def load_system_config() -> dict:
    return json.loads((evidence_root() / "_config" / "evidence-system.json").read_text())


def new_run_id(head_sha: str | None = None) -> str:
    sha = head_sha or git_head_sha()
    return f"{utc_compact()}-{sha[:8]}"


def playwright_version() -> str:
    try:
        import playwright

        return getattr(playwright, "__version__", "unknown")
    except Exception:
        return "unknown"


def browser_info(browser=None) -> tuple[str, str]:
    if browser is not None:
        ver = ""
        try:
            ver = browser.version
        except Exception:
            ver = ""
        return "chrome", ver or "unknown"
    return "chrome", "unknown"


def base_run_manifest(*, schema_version: str | None = None, run_id: str | None = None) -> dict:
    cfg = load_system_config()
    sha = git_head_sha()
    rid = run_id or new_run_id(sha)
    return {
        "schema_version": schema_version or cfg.get("schema_version") or SCHEMA_CANDIDATE,
        "collector_version": sha,
        "collector_version_name": cfg.get("collector_version_name"),
        "run_id": rid,
        "run_started_at": now_iso(),
        "run_completed_at": None,
        "repository": "mastermindx-market-intelligence/macro",
        "repo_head_sha": sha,
        "working_tree_dirty": working_tree_dirty(),
        "browser_name": "chrome",
        "browser_version": "unknown",
        "playwright_version": playwright_version(),
        "device_scale_factor": cfg.get("device_scale_factor", 1),
        "authenticated_session_used": False,
        "source_parity_method": cfg.get("source_parity_method"),
        "operating_platform": platform.platform(),
        "unique_nonce": uuid.uuid4().hex,
    }


def finalize_run(manifest: dict, **extra) -> dict:
    out = dict(manifest)
    out.update(extra)
    out["run_completed_at"] = now_iso()
    return out


def dump_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n")
