"""GitHub Actions integration: watch builds and trigger a rebuild/redeploy.

Reads run status unauthenticated (public repo) and POSTs a workflow_dispatch when a
token is present (env GH_TOKEN or GITHUB_TOKEN, optionally via <repo>/.env). The live
site is rebuilt by daily.yml and redeployed by pages.yml — both expose workflow_dispatch.
"""
from __future__ import annotations

import os
import re
import subprocess
import threading
import time

from .paths import ROOT

API = "https://api.github.com"
_REPO_CACHE: tuple[str, str] | None = None
_RUNS_CACHE_TTL_SECONDS = 30
_RUNS_CACHE: dict[tuple[str, str, str], tuple[float, int, list[dict]]] = {}
_RUNS_CACHE_LOCK = threading.Lock()

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
    """Recent workflow runs, with one short shared cache for every admin viewer.

    The browser refreshes its live-run strip every 20 seconds. Without a
    server-side cache, every open tab and every panel rendered in the same
    process spent a separate GitHub REST request. Thirty seconds keeps the
    operator view current while collapsing simultaneous viewers and adjacent
    polls into one request.
    """
    if requests is None:
        return {"ok": False, "error": "requests not installed", "runs": []}
    owner, name = repo()
    if not (owner and name):
        return {"ok": False, "error": "could not detect owner/repo from git remote", "runs": []}
    base = f"{API}/repos/{owner}/{name}/actions"
    url = (f"{base}/workflows/{workflow}/runs" if workflow else f"{base}/runs")
    key = (owner, name, workflow or "")
    now = time.monotonic()
    with _RUNS_CACHE_LOCK:
        cached = _RUNS_CACHE.get(key)
        if (
            cached
            and now - cached[0] < _RUNS_CACHE_TTL_SECONDS
            and cached[1] >= per_page
        ):
            return {"ok": True, "runs": [dict(run) for run in cached[2][:per_page]]}
        try:
            resp = requests.get(
                url,
                headers=_headers(),
                params={"per_page": per_page},
                timeout=12,
            )
            if resp.status_code != 200:
                return {"ok": False, "error": f"HTTP {resp.status_code}", "runs": []}
            runs = [_slim_run(r) for r in resp.json().get("workflow_runs", [])]
            _RUNS_CACHE[key] = (time.monotonic(), per_page, runs)
            return {"ok": True, "runs": [dict(run) for run in runs]}
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


def list_repo_variables() -> dict[str, str] | None:
    """Return {name: value} for all GitHub Actions repository variables, or None.

    Fetches the full variable list in ONE API call (a single page of 100 covers
    the handful of METAB_*/AUTONOMY_*/CODEX_* vars this repo uses), collapsing
    what used to be N sequential get_repo_variable() round-trips into one.

    Returns None (not {}) when no token is configured, requests is unavailable,
    the owner/repo cannot be detected, or the API returns a non-200 — callers
    then fall back to per-variable get_repo_variable() reads.  Never raises.
    """
    if requests is None:
        return None
    if not token():
        return None
    owner, name_repo = repo()
    if not (owner and name_repo):
        return None
    url = f"{API}/repos/{owner}/{name_repo}/actions/variables"
    try:
        resp = requests.get(url, headers=_headers(),
                            params={"per_page": 100}, timeout=12)
        if resp.status_code != 200:
            return None
        out: dict[str, str] = {}
        for v in resp.json().get("variables", []):
            n = v.get("name")
            if isinstance(n, str):
                out[n] = v.get("value")
        return out
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


def get_file(path: str, ref: str = "main") -> dict:
    """Read a repo file via the Contents API → {ok, content: str|None, sha: str|None}.

    ``content`` is the decoded UTF-8 text, or None when the file does not exist
    (HTTP 404 — still ``ok: True`` so a caller can create it). Never raises;
    transport/permission failures return {ok: False, error}. Requires a token
    with Contents: Read.
    """
    if requests is None:
        return {"ok": False, "error": "requests unavailable"}
    if not token():
        return {"ok": False, "error": "no GH_TOKEN / GITHUB_TOKEN set"}
    owner, name_repo = repo()
    if not (owner and name_repo):
        return {"ok": False, "error": "repo not resolved"}
    url = f"{API}/repos/{owner}/{name_repo}/contents/{path}"
    try:
        resp = requests.get(url, headers=_headers(), params={"ref": ref}, timeout=12)
        if resp.status_code == 404:
            return {"ok": True, "content": None, "sha": None}
        if resp.status_code != 200:
            return {"ok": False, "error": f"HTTP {resp.status_code}"}
        j = resp.json()
        import base64  # noqa: PLC0415
        raw = base64.b64decode(j.get("content", "") or "").decode("utf-8")
        # THE 1 MB INLINE CEILING IS A TRUNCATION TRAP. Past ~1 MB the Contents
        # API still answers 200 with the real sha, but `content` comes back EMPTY
        # and `encoding: "none"` (the blob has to be fetched through the Blob or
        # raw media API instead). Returning that as an ok-but-empty read is
        # fail-OPEN for any caller that rebuilds the file from it:
        # `append_jsonl_line` would PUT a single row over the whole ledger under
        # a sha the API happily accepts, replacing the live outbox queue on main.
        # Its own size guard cannot catch it — the size it measures is 0. An
        # unreadable file is recoverable; a truncated ledger is not.
        encoding = str(j.get("encoding") or "base64")
        try:
            reported = int(j.get("size") or 0)
        except (TypeError, ValueError):
            reported = 0
        if encoding != "base64" or (reported > 0 and not raw):
            return {"ok": False, "error": (
                f"{path} was not inlined by the Contents API "
                f"(encoding={encoding!r}, size={reported}) — it is over the 1 MB "
                f"inline ceiling and needs rotating")}
        return {"ok": True, "content": raw, "sha": j.get("sha")}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


def put_file(path: str, content: str, message: str, *, sha: str | None = None,
             branch: str = "main") -> dict:
    """Create/update a repo file via the Contents API — commits directly to *branch*.

    This is the deployed-mode write path (the VPS admin has no authenticated git
    working tree). Pass *sha* (from get_file) to update an existing file; omit it
    to create. Returns {ok, commit_sha?} or {ok: False, error}. Never raises.
    Requires a token with Contents: Read & write.
    """
    if requests is None:
        return {"ok": False, "error": "requests unavailable"}
    if not token():
        return {"ok": False, "error": "no GH_TOKEN / GITHUB_TOKEN set (needs Contents: write)"}
    owner, name_repo = repo()
    if not (owner and name_repo):
        return {"ok": False, "error": "repo not resolved"}
    import base64  # noqa: PLC0415
    url = f"{API}/repos/{owner}/{name_repo}/contents/{path}"
    body: dict = {
        "message": message,
        "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
        "branch": branch,
    }
    if sha:
        body["sha"] = sha
    try:
        resp = requests.put(url, headers=_headers(), json=body, timeout=15)
        if resp.status_code in (200, 201):
            j = resp.json()
            return {"ok": True, "commit_sha": ((j.get("commit") or {}).get("sha"))}
        if resp.status_code == 403:
            return {"ok": False, "error":
                    "HTTP 403 — the GitHub token can't write repo contents. It needs "
                    "Contents: Read & write. Update GH_TOKEN in /etc/macro-admin.env "
                    "on the admin host, then restart the admin service."}
        if resp.status_code == 409:
            return {"ok": False, "error": "HTTP 409 — sha conflict (file changed under us); retry"}
        return {"ok": False, "error": f"HTTP {resp.status_code}: {resp.text[:200]}"}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


#: Refuse a Contents-API append once the file we would have to re-upload gets
#: near the endpoint's 1 MB ceiling. The API rejects the whole write above that,
#: so an append that squeaks past today fails outright a few rows later; better
#: to stop early and say the file needs rotating. Not a tunable: it is a
#: headroom margin under a GitHub limit, not a policy.
CONTENTS_APPEND_MAX_BYTES = 900_000

#: Error fragments that mean "the file moved under us between the read and the
#: write" — the one failure a retry can actually fix. GitHub answers a stale sha
#: with 409 on some paths and 422 ("does not match") on others.
_CONFLICT_MARKERS = ("409", "422", "conflict", "does not match")


def _is_sha_conflict(error: str) -> bool:
    low = (error or "").lower()
    return any(m in low for m in _CONFLICT_MARKERS)


def append_jsonl_line(path: str, line: str, message: str, *,
                      branch: str = "main", if_absent: str | None = None,
                      attempts: int = 3) -> dict:
    """Append ONE line to an append-only file on *branch* via the Contents API.

    GET the file, optionally skip when *if_absent* already appears in it, append
    *line*, PUT it back under the sha we just read. This is the deployed-admin
    write path for the git-tracked ledgers: that host has no authenticated git
    working tree, and its checkout is reset --hard to origin/main every few
    minutes, so anything committed locally is discarded before it can be read.

    Concurrency: several lanes append to these ledgers, so origin moves often. A
    stale-sha rejection re-reads and re-appends (up to *attempts* times) rather
    than force-writing — the retry rebuilds the body from the file as it now is,
    so no one else's row is ever dropped.

    if_absent: a substring whose presence means "already delivered" — the
    idempotency guard for a re-click after a slow response. Checked against the
    file ON *branch*, so it also covers the case where the local copy was reset
    away between the two clicks.

    Returns one of:
      {ok: True,  appended: True,  commit_sha, attempts}   — the line is on branch
      {ok: True,  appended: False, reason: "already_present", attempts}
      {ok: False, step, error, attempts}

    *step* names the part that failed — "unavailable" (no token/library/repo),
    "read", "too_large", "write" — so a caller can tell an operator which step
    stopped, in its own words, without parsing the error string. Never raises.
    """
    av = available()
    if not av.get("ok"):
        missing = ("requests unavailable" if not av.get("lib")
                   else "repo not resolved")
        return {"ok": False, "step": "unavailable", "error": missing, "attempts": 0}
    if not av.get("has_token"):
        return {"ok": False, "step": "unavailable", "attempts": 0,
                "error": "no GH_TOKEN / GITHUB_TOKEN set (needs Contents: Read & write)"}
    try:
        attempts = max(1, int(attempts))
    except (TypeError, ValueError):
        attempts = 1
    row = line if line.endswith("\n") else line + "\n"

    last_error = "the write step reported no result"
    for attempt in range(1, attempts + 1):
        try:
            gf = get_file(path, ref=branch)
        except Exception as exc:  # noqa: BLE001 — get_file is fail-soft, belt and braces
            return {"ok": False, "step": "read", "error": str(exc), "attempts": attempt}
        if not gf.get("ok"):
            return {"ok": False, "step": "read", "attempts": attempt,
                    "error": str(gf.get("error") or "read failed")}
        current = gf.get("content") or ""
        if if_absent and if_absent in current:
            return {"ok": True, "appended": False, "reason": "already_present",
                    "attempts": attempt}
        size = len(current.encode("utf-8"))
        if size > CONTENTS_APPEND_MAX_BYTES:
            return {"ok": False, "step": "too_large", "attempts": attempt,
                    "error": (f"{path} is {size} bytes on {branch}; this write path "
                              f"stops at {CONTENTS_APPEND_MAX_BYTES} (the API ceiling "
                              f"is 1 MB) — the file needs rotating")}
        body = current
        if body and not body.endswith("\n"):
            body += "\n"
        body += row
        try:
            pf = put_file(path, body, message, sha=gf.get("sha"), branch=branch)
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "step": "write", "error": str(exc), "attempts": attempt}
        if pf.get("ok"):
            return {"ok": True, "appended": True, "attempts": attempt,
                    "commit_sha": pf.get("commit_sha")}
        last_error = str(pf.get("error") or "write failed")
        if not _is_sha_conflict(last_error):
            # 403, 404, transport — retrying re-reads and fails the same way.
            return {"ok": False, "step": "write", "error": last_error,
                    "attempts": attempt}
    return {"ok": False, "step": "write", "attempts": attempts, "conflict": True,
            "error": f"{last_error} (still conflicting after {attempts} attempts)"}


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
