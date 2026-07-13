"""GitHub Actions integration: watch builds and trigger a rebuild/redeploy.

Reads run status unauthenticated (public repo) and POSTs a workflow_dispatch when a
token is present (env GH_TOKEN or GITHUB_TOKEN, optionally via <repo>/.env). The live
site is rebuilt by daily.yml and redeployed by pages.yml — both expose workflow_dispatch.
"""
from __future__ import annotations

import os
import re
import subprocess

from .paths import ROOT

API = "https://api.github.com"
_REPO_CACHE: tuple[str, str] | None = None

# Last actionable error from set_repo_variable, for callers that surface details.
# Reset to None on success; set to a plain-English message on HTTP 403/error.
# Never contains the token value.
_last_set_variable_error: str | None = None

try:
    import requests  # already a project dependency
except Exception:  # noqa: BLE001
    requests = None  # type: ignore


def repo() -> tuple[str | None, str | None]:
    """(owner, name) parsed from `git remote get-url origin`. Cached."""
    global _REPO_CACHE
    if _REPO_CACHE is not None:
        return _REPO_CACHE
    owner = name = None
    try:
        url = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=str(ROOT), capture_output=True, text=True, timeout=5,
        ).stdout.strip().rstrip("/")
        m = re.search(r"[:/]([^/]+)/([^/]+?)(?:\.git)?$", url)
        if m:
            owner, name = m.group(1), m.group(2)
    except Exception:  # noqa: BLE001
        pass
    _REPO_CACHE = (owner, name)
    return _REPO_CACHE


def token() -> str | None:
    for k in ("GH_TOKEN", "GITHUB_TOKEN"):
        v = os.environ.get(k, "").strip()
        if v:
            return v
    return None


def _headers() -> dict:
    h = {"Accept": "application/vnd.github+json",
         "X-GitHub-Api-Version": "2022-11-28",
         "User-Agent": "macro-admin"}
    t = token()
    if t:
        h["Authorization"] = f"Bearer {t}"
    return h


def available() -> dict:
    owner, name = repo()
    return {
        "ok": bool(requests and owner and name),
        "owner": owner, "repo": name,
        "has_token": bool(token()),
        "lib": bool(requests),
    }


def _slim_run(r: dict) -> dict:
    return {
        "id": r.get("id"),
        "name": r.get("name"),
        "display_title": r.get("display_title"),
        "status": r.get("status"),
        "conclusion": r.get("conclusion"),
        "event": r.get("event"),
        "branch": r.get("head_branch"),
        "created_at": r.get("created_at"),
        "run_started_at": r.get("run_started_at"),
        "updated_at": r.get("updated_at"),
        "html_url": r.get("html_url"),
        "workflow": (r.get("path") or "").replace(".github/workflows/", ""),
    }


def list_runs(per_page: int = 15, workflow: str | None = None) -> dict:
    """Recent workflow runs (newest first). Works without a token on a public repo."""
    if requests is None:
        return {"ok": False, "error": "requests not installed", "runs": []}
    owner, name = repo()
    if not (owner and name):
        return {"ok": False, "error": "could not detect owner/repo from git remote", "runs": []}
    base = f"{API}/repos/{owner}/{name}/actions"
    url = (f"{base}/workflows/{workflow}/runs" if workflow else f"{base}/runs")
    try:
        resp = requests.get(url, headers=_headers(),
                            params={"per_page": per_page}, timeout=12)
        if resp.status_code != 200:
            return {"ok": False, "error": f"HTTP {resp.status_code}", "runs": []}
        runs = [_slim_run(r) for r in resp.json().get("workflow_runs", [])]
        return {"ok": True, "runs": runs}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e), "runs": []}


def get_repo_variable(name: str) -> str | None:
    """Return the value of a GitHub Actions repository variable, or None.

    Returns None when no token is configured, when requests is unavailable,
    when the owner/repo cannot be detected, or when the variable does not
    exist (HTTP 404).  Never raises.
    """
    if requests is None:
        return None
    if not token():
        return None
    owner, name_repo = repo()
    if not (owner and name_repo):
        return None
    url = f"{API}/repos/{owner}/{name_repo}/actions/variables/{name}"
    try:
        resp = requests.get(url, headers=_headers(), timeout=12)
        if resp.status_code == 404:
            return None
        if resp.status_code != 200:
            return None
        return resp.json().get("value")
    except Exception:  # noqa: BLE001
        return None


def set_repo_variable(name: str, value: str) -> bool:
    """Set (or create) a GitHub Actions repository variable.

    PATCHes the variable if it exists; POSTs to create it on a 404 response.
    Returns True on success, False on any error.  Never logs the token value.
    Requires a token with Variables: Read & write permission.

    On HTTP 403 or other actionable errors, sets the module-level
    _last_set_variable_error string so callers can surface a friendly message.
    """
    global _last_set_variable_error
    _last_set_variable_error = None
    if requests is None:
        return False
    if not token():
        return False
    owner, name_repo = repo()
    if not (owner and name_repo):
        return False
    base = f"{API}/repos/{owner}/{name_repo}/actions/variables"
    body = {"name": name, "value": value}
    try:
        # Try PATCH first (update existing variable)
        resp = requests.patch(f"{base}/{name}", headers=_headers(),
                              json=body, timeout=12)
        if resp.status_code in (204, 200):
            return True
        if resp.status_code == 403:
            _last_set_variable_error = (
                "HTTP 403 — the GitHub token can't write repository variables. "
                "It needs Variables: Read & write (fine-grained PAT) or the repo "
                "scope (classic PAT). Update GH_TOKEN in /etc/macro-admin.env on "
                "the admin host, then restart the admin service."
            )
            return False
        if resp.status_code == 404:
            # Variable does not exist yet — create via POST
            resp2 = requests.post(base, headers=_headers(),
                                  json=body, timeout=12)
            if resp2.status_code in (201, 204, 200):
                return True
            if resp2.status_code == 403:
                _last_set_variable_error = (
                    "HTTP 403 — the GitHub token can't write repository variables. "
                    "It needs Variables: Read & write (fine-grained PAT) or the repo "
                    "scope (classic PAT). Update GH_TOKEN in /etc/macro-admin.env on "
                    "the admin host, then restart the admin service."
                )
            return False
        return False
    except Exception:  # noqa: BLE001
        return False


def _slim_pr(p: dict) -> dict:
    return {
        "number": p.get("number"),
        "title": p.get("title"),
        "state": p.get("state"),
        "draft": bool(p.get("draft")),
        "merged_at": p.get("merged_at"),
        "created_at": p.get("created_at"),
        "head_ref": (p.get("head") or {}).get("ref"),
        "html_url": p.get("html_url"),
    }


def list_prs(per_page: int = 100) -> dict:
    """Recent PRs (newest first). Fail-soft: returns {ok: False, error: ..., prs: []} on any error."""
    if requests is None:
        return {"ok": False, "error": "requests not installed", "prs": []}
    owner, name = repo()
    if not (owner and name):
        return {"ok": False, "error": "could not detect owner/repo from git remote", "prs": []}
    url = f"{API}/repos/{owner}/{name}/pulls"
    try:
        resp = requests.get(url, headers=_headers(),
                            params={"state": "all", "sort": "created",
                                    "direction": "desc", "per_page": per_page},
                            timeout=12)
        if resp.status_code != 200:
            return {"ok": False, "error": f"HTTP {resp.status_code}", "prs": []}
        prs = [_slim_pr(p) for p in resp.json()]
        return {"ok": True, "prs": prs}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e), "prs": []}


def run_jobs(run_id: int | str, cap: int = 10) -> list[dict]:
    """Slim job list for a single workflow run.

    Returns a list of dicts (up to *cap* jobs):
        {name, status, conclusion, started_at, completed_at,
         current_step: str | None, steps_done: int, steps_total: int}

    Fail-soft: returns [] on any error (no token, requests unavailable,
    API error, network failure). Never raises.
    """
    if requests is None:
        return []
    owner, name = repo()
    if not (owner and name):
        return []
    url = f"{API}/repos/{owner}/{name}/actions/runs/{run_id}/jobs"
    try:
        resp = requests.get(url, headers=_headers(),
                            params={"per_page": cap}, timeout=12)
        if resp.status_code != 200:
            return []
        jobs_raw = resp.json().get("jobs", [])[:cap]
        out = []
        for j in jobs_raw:
            steps = j.get("steps") or []
            steps_done = sum(1 for s in steps if s.get("status") == "completed")
            steps_total = len(steps)
            current_step: str | None = None
            for s in steps:
                if s.get("status") == "in_progress":
                    current_step = s.get("name")
                    break
            out.append({
                "name": j.get("name"),
                "status": j.get("status"),
                "conclusion": j.get("conclusion"),
                "started_at": j.get("started_at"),
                "completed_at": j.get("completed_at"),
                "current_step": current_step,
                "steps_done": steps_done,
                "steps_total": steps_total,
            })
        return out
    except Exception:  # noqa: BLE001
        return []


def dispatch(workflow: str = "daily.yml", ref: str = "main",
             inputs: dict | None = None) -> dict:
    """Trigger a workflow_dispatch. Requires a token with Actions: write."""
    if requests is None:
        return {"ok": False, "error": "requests not installed"}
    if not token():
        return {"ok": False, "error": "no GH_TOKEN / GITHUB_TOKEN set (needs Actions:write)"}
    owner, name = repo()
    if not (owner and name):
        return {"ok": False, "error": "could not detect owner/repo"}
    url = f"{API}/repos/{owner}/{name}/actions/workflows/{workflow}/dispatches"
    body: dict = {"ref": ref}
    if inputs:
        body["inputs"] = inputs
    try:
        resp = requests.post(url, headers=_headers(), json=body, timeout=12)
        if resp.status_code == 204:
            return {"ok": True, "workflow": workflow, "ref": ref}
        if resp.status_code == 403:
            return {
                "ok": False,
                "error": (
                    "HTTP 403 — the GitHub token can't dispatch workflows. "
                    "It needs Actions: Read & write (fine-grained PAT) or the "
                    "workflow scope (classic PAT). Update GH_TOKEN in "
                    "/etc/macro-admin.env on the admin host, then restart the admin service."
                ),
            }
        if resp.status_code == 404:
            return {
                "ok": False,
                "error": (
                    "HTTP 404 — workflow not found or the GitHub token cannot see this "
                    "repository. For fine-grained PATs the repo must be explicitly selected. "
                    "Update GH_TOKEN in /etc/macro-admin.env on the admin host, "
                    "then restart the admin service."
                ),
            }
        msg = ""
        try:
            msg = resp.json().get("message", "")
        except Exception:  # noqa: BLE001
            msg = resp.text[:300]
        return {"ok": False, "error": f"HTTP {resp.status_code}: {msg}"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}
