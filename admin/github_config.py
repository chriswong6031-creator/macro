"""Edit config.yml directly on origin/main via the GitHub Contents API.

The deployed console runs against /opt/macro — a depth-1 clone that's reset every
few minutes — so it can't carry a working-tree edit the way the local admin does.
Instead, when a token with Contents:write is present, a flag toggle is applied as
a surgical, comment-preserving commit straight to main on GitHub; the VPS pulls
the change on its normal cadence. Same guarantee as config_store: only the value
token on the located line changes (the line is found by walking the YAML tree via
indentation, reusing config_store's locator + regexes).

Read works token-lessly on a public repo; writes need GH_TOKEN/GITHUB_TOKEN with
Contents:write on the repo.
"""
from __future__ import annotations

import base64

from . import config_store, github_api

try:
    import requests
except Exception:  # noqa: BLE001
    requests = None  # type: ignore

API = "https://api.github.com"
_PATH = "config.yml"


def available() -> bool:
    return bool(requests and github_api.token() and all(github_api.repo()))


def _get_file(ref: str = "main") -> tuple[str, str]:
    owner, name = github_api.repo()
    url = f"{API}/repos/{owner}/{name}/contents/{_PATH}"
    r = requests.get(url, headers=github_api._headers(), params={"ref": ref}, timeout=15)
    if r.status_code != 200:
        raise RuntimeError(f"GET config.yml: HTTP {r.status_code}: {r.text[:160]}")
    j = r.json()
    return base64.b64decode(j["content"]).decode(), j["sha"]


def _put_file(text: str, sha: str, message: str, branch: str = "main") -> str | None:
    owner, name = github_api.repo()
    url = f"{API}/repos/{owner}/{name}/contents/{_PATH}"
    body = {"message": message, "sha": sha, "branch": branch,
            "content": base64.b64encode(text.encode()).decode()}
    r = requests.put(url, headers=github_api._headers(), json=body, timeout=20)
    if r.status_code not in (200, 201):
        raise RuntimeError(f"PUT config.yml: HTTP {r.status_code}: {r.text[:200]}")
    return (r.json().get("commit") or {}).get("sha")


def set_bool(dotted: str, value: bool, message: str | None = None) -> dict:
    if not available():
        return {"ok": False, "error": "needs GH_TOKEN (Contents:write) to edit main on GitHub"}
    try:
        text, sha = _get_file()
        if "\r" in text:
            return {"ok": False, "error": "config.yml has CR line endings; refusing edit"}
        lines = text.split("\n")
        idx = config_store.locate_line(dotted, lines)
        if idx is None:
            return {"ok": False, "error": f"path not found on main: {dotted}"}
        leaf = dotted.split(".")[-1]
        m = config_store._BOOL_RE.match(lines[idx])
        if not m or m.group("key") != leaf:
            return {"ok": False, "error": f"line {idx + 1} is not a boolean flag for {dotted}"}
        new_token = "true" if value else "false"
        if m.group("val").lower() == new_token:
            return {"ok": True, "path": dotted, "new": new_token, "noop": True}
        lines[idx] = f"{m.group('indent')}{m.group('key')}:{m.group('gap')}{new_token}{m.group('rest')}"
        commit = _put_file("\n".join(lines), sha, message or f"admin: set {dotted}={new_token}")
        return {"ok": True, "path": dotted, "old": m.group("val"), "new": new_token,
                "commit": commit, "line": idx + 1}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}


def set_int(dotted: str, value, lo: int = 1, hi: int = 7, message: str | None = None) -> dict:
    if not available():
        return {"ok": False, "error": "needs GH_TOKEN (Contents:write) to edit main on GitHub"}
    try:
        value = max(lo, min(hi, int(value)))
    except (TypeError, ValueError):
        return {"ok": False, "error": f"not an integer: {value!r}"}
    try:
        text, sha = _get_file()
        lines = text.split("\n")
        idx = config_store.locate_line(dotted, lines)
        if idx is None:
            return {"ok": False, "error": f"path not found on main: {dotted}"}
        leaf = dotted.split(".")[-1]
        m = config_store._INT_RE.match(lines[idx])
        if not m or m.group("key") != leaf:
            return {"ok": False, "error": f"line {idx + 1} is not an integer field for {dotted}"}
        lines[idx] = f"{m.group('indent')}{m.group('key')}:{m.group('gap')}{value}{m.group('rest')}"
        commit = _put_file("\n".join(lines), sha, message or f"admin: set {dotted}={value}")
        return {"ok": True, "path": dotted, "old": m.group("val"), "new": str(value),
                "commit": commit, "line": idx + 1}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}
