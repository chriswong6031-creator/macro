"""Sanitized, read-only project runtime-state collection.

The durable topology is reviewed in ``config/production_topology.yml``.  This
module turns that topology plus bounded VPS evidence into a canonical snapshot.
It deliberately does not expose raw probe payloads: every record is rebuilt
field-by-field from a small vocabulary before it can leave the collector.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import subprocess
import tempfile
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import yaml

SCHEMA = "mastermind.runtime_state.v1"
TOPOLOGY_SCHEMA = "mastermind.production_topology.v1"
DEFAULT_VALID_FOR_SECONDS = 600

STATES = frozenset({
    "healthy", "degraded", "failed", "stale", "missing", "indeterminate",
    "not_due", "ran_no_change", "in_progress", "disabled", "operator_armed",
})
ISSUE_STATES = frozenset({"degraded", "failed", "stale", "missing", "indeterminate"})
EXPECTATIONS = frozenset({"required", "optional", "disabled", "operator_armed"})

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_.:-]{0,127}$")
_UNIT_RE = re.compile(r"^[a-zA-Z0-9_.@:-]+\.(?:service|timer)$")
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_SHORT_SHA_RE = re.compile(r"^[0-9a-f]{7,40}$")
_SAFE_VERSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,63}$")
_SAFE_METRIC_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_FORBIDDEN_KEY_RE = re.compile(
    r"(?:^|_)(?:api_?key|access_?token|refresh_?token|oauth|authorization|cookie|"
    r"password|passwd|secret|credential|private_?key|env|command|cmdline|error|"
    r"detail|stack|traceback|email|holding|fill|balance|account)(?:$|_)", re.I,
)
_FORBIDDEN_TEXT_RES = (
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"\b(?:Bearer|Basic)\s+[A-Za-z0-9._~+/=-]+", re.I),
    re.compile(r"\b(?:sk|rk|pk|ghp|github_pat)_[A-Za-z0-9_-]{8,}\b", re.I),
    re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I),
    re.compile(r"[a-z][a-z0-9+.-]*://[^/\s:@]+:[^/\s@]+@", re.I),
    re.compile(r"(?:^|\s)(?:/Users/|/home/|/root/|/opt/|/etc/|/var/lib/)[^\s]*"),
    re.compile(r"Traceback \(most recent call last\):"),
)

_ALLOWED_PATH_ROOTS = tuple(Path(p).resolve() for p in (
    "/opt/macro", "/opt/terminal", "/opt/mastermind", "/opt/mastermind-live-data",
    "/var/lib/macro-live",
))
_ALLOWED_HTTP_PORTS = {3000, 3100, 8000, 8001, 8090, 8787}
_SYSTEMD_PROPS = (
    "LoadState", "ActiveState", "SubState", "UnitFileState", "Result",
    "NRestarts", "ExecMainStartTimestamp", "LastTriggerUSec",
    "NextElapseUSecRealtime",
)
_CADENCE_SPECS: dict[str, dict[str, Any]] = {
    "every_3_minutes": {"max_age_seconds": 600},
    "every_minute": {"max_age_seconds": 300},
    "five_minutes_weekdays": {"window_aware": True},
    "hourly_us_window_weekdays": {"window_aware": True},
    "five_minutes_evening_window_weekdays": {"window_aware": True},
    "five_minutes_us_window_weekdays": {"window_aware": True},
    "hourly": {"max_age_seconds": 9_000},
    "weekday_morning": {"window_aware": True},
    "every_30_minutes": {"max_age_seconds": 3_600},
    "hourly_when_armed": {"window_aware": True},
    "daily_2130_utc": {"max_age_seconds": 172_800, "window_aware": True},
    "apscheduler_managed": {"window_aware": True},
    "systemd_timer": {"window_aware": True},
}

_TOPOLOGY_SECTIONS = {
    "releases": "repositories",
    "services": "services",
    "scheduled_systems": "scheduled_systems",
    "data_planes": "data_planes",
    "bridges": "bridges",
    "storage": "storage",
    "providers": "providers",
}


class RuntimeStateError(RuntimeError):
    """Base error for invalid topology or evidence."""


class PrivacyViolation(RuntimeStateError):
    """Raised when a canonical snapshot violates the privacy boundary."""


class TopologyError(RuntimeStateError):
    """Raised when durable topology is malformed or unsafe."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Keep reviewed loopback probes from being redirected off-host."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001, D401
        return None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return _as_utc(value).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    # systemd uses "n/a" and an English timestamp; the latter is normalized by
    # ``date --iso-8601`` on newer hosts but this fallback handles its stable form.
    if text.lower() in {"n/a", "never", "none", "null"}:
        return None
    try:
        return _as_utc(datetime.fromisoformat(text.replace("Z", "+00:00")))
    except ValueError:
        pass
    for fmt in ("%a %Y-%m-%d %H:%M:%S %Z", "%Y-%m-%d %H:%M:%S %Z"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _safe_id(value: Any, *, field: str = "id") -> str:
    text = str(value or "")
    if not _ID_RE.fullmatch(text):
        raise TopologyError(f"invalid {field}: {text!r}")
    return text


def _safe_expectation(value: Any) -> str:
    text = str(value or "required")
    text = {
        "active": "required",
        "scheduled": "required",
        "healthy": "required",
        "indeterminate": "optional",
    }.get(text, text)
    if text not in EXPECTATIONS:
        raise TopologyError(f"invalid expectation: {text!r}")
    return text


def _safe_unit(value: Any) -> str:
    text = str(value or "")
    if not _UNIT_RE.fullmatch(text):
        raise TopologyError(f"invalid systemd unit: {text!r}")
    return text


def _safe_path(value: Any, *, mode: str, repo_root: Path) -> Path:
    raw = Path(str(value or ""))
    if mode == "local" and (raw == Path("/opt/macro") or str(raw).startswith("/opt/macro/")):
        raw = repo_root if raw == Path("/opt/macro") else repo_root / raw.relative_to("/opt/macro")
    lexical = raw.absolute()
    resolved = lexical.resolve()
    if mode == "local" and (resolved == repo_root.resolve() or repo_root.resolve() in resolved.parents):
        return lexical
    if not any(resolved == root or root in resolved.parents for root in _ALLOWED_PATH_ROOTS):
        raise TopologyError(f"probe path is outside reviewed runtime roots: {value!r}")
    # Preserve the lexical path after validating its resolved target. The
    # Macro→Portfolio bridge explicitly proves a reviewed symlink; returning
    # only the resolved target would erase that evidence and false-report it.
    return lexical


def _safe_http_url(value: Any) -> str:
    text = str(value or "")
    parsed = urllib.parse.urlparse(text)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise TopologyError("runtime HTTP probes must target loopback over http")
    if parsed.port not in _ALLOWED_HTTP_PORTS or parsed.username or parsed.password:
        raise TopologyError("runtime HTTP probe has an unapproved port or credentials")
    if parsed.fragment:
        raise TopologyError("runtime HTTP probe fragments are not allowed")
    return text


def _nested(raw: Any, selector: str | None) -> Any:
    if not selector:
        return raw
    cur = raw
    for part in selector.split("."):
        if not _SAFE_METRIC_RE.fullmatch(part) or _FORBIDDEN_KEY_RE.search(part):
            raise TopologyError(f"unsafe evidence selector: {selector!r}")
        if not isinstance(cur, Mapping) or part not in cur:
            return None
        cur = cur[part]
    return cur


def _full_sha(value: Any) -> str | None:
    text = str(value or "").strip().lower()
    return text if _SHA_RE.fullmatch(text) else None


def _safe_version(value: Any) -> str | None:
    text = str(value or "").strip()
    return text if _SAFE_VERSION_RE.fullmatch(text) else None


def _bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "yes", "ok", "healthy", "available", "active", "1"}:
            return True
        if lowered in {"false", "no", "failed", "unhealthy", "unavailable", "inactive", "0"}:
            return False
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    return None


class SystemEvidenceReader:
    """Bounded, read-only evidence reader used on the VPS and in local checks."""

    def __init__(self, *, mode: str = "vps", repo_root: Path | None = None):
        if mode not in {"vps", "local"}:
            raise ValueError("mode must be vps or local")
        self.mode = mode
        self.repo_root = (repo_root or Path(__file__).resolve().parent.parent).resolve()
        # One invocation is one point-in-time observation. Reuse repeated reads
        # (notably the Portfolio scheduler and sentinel artifact) so sections
        # cannot disagree merely because a producer advanced mid-collection.
        self._text_cache: dict[tuple[str, int], str | None] = {}
        self._jsonl_cache: dict[tuple[str, int], list[Any]] = {}
        self._http_json_cache: dict[str, tuple[int | None, Any]] = {}
        self._http_text_cache: dict[str, tuple[int | None, str | None]] = {}

    def path(self, value: Any) -> Path:
        return _safe_path(value, mode=self.mode, repo_root=self.repo_root)

    def run(self, argv: Sequence[str], *, timeout: float = 8.0) -> tuple[int, str]:
        try:
            result = subprocess.run(
                list(argv), capture_output=True, text=True, timeout=timeout,
                check=False, shell=False,
            )
        except (OSError, subprocess.SubprocessError):
            return 127, ""
        return result.returncode, result.stdout[:262_144]

    def read_text(self, path: Any, *, max_bytes: int = 2_000_000) -> str | None:
        target = self.path(path)
        cache_key = (str(target), max_bytes)
        if cache_key in self._text_cache:
            return self._text_cache[cache_key]
        try:
            with target.open("rb") as handle:
                data = handle.read(max_bytes + 1)
        except OSError:
            self._text_cache[cache_key] = None
            return None
        if len(data) > max_bytes:
            self._text_cache[cache_key] = None
            return None
        try:
            result = data.decode("utf-8")
        except UnicodeDecodeError:
            result = None
        self._text_cache[cache_key] = result
        return result

    def read_json(self, path: Any) -> Any:
        text = self.read_text(path)
        if text is None:
            return None
        try:
            return json.loads(text)
        except (TypeError, ValueError):
            return None

    def read_jsonl(self, path: Any, *, tail: int = 100) -> list[Any]:
        target = self.path(path)
        bounded_tail = max(1, min(tail, 500))
        cache_key = (str(target), bounded_tail)
        if cache_key in self._jsonl_cache:
            return list(self._jsonl_cache[cache_key])
        # The provider ledger rotates at 8 MiB. Read only a bounded tail so a
        # healthy 2–8 MiB file cannot disappear behind the generic whole-file
        # cap used for small receipts.
        try:
            size = target.stat().st_size
            read_size = min(size, 2_000_000)
            with target.open("rb") as handle:
                if size > read_size:
                    handle.seek(-read_size, os.SEEK_END)
                data = handle.read(read_size)
            if size > read_size:
                _, separator, data = data.partition(b"\n")
                if not separator:
                    data = b""
            text = data.decode("utf-8")
        except (OSError, UnicodeDecodeError):
            self._jsonl_cache[cache_key] = []
            return []
        rows: list[Any] = []
        for line in text.splitlines()[-bounded_tail:]:
            try:
                rows.append(json.loads(line))
            except ValueError:
                continue
        self._jsonl_cache[cache_key] = rows
        return list(rows)

    def mtime(self, path: Any) -> datetime | None:
        try:
            return datetime.fromtimestamp(self.path(path).stat().st_mtime, tz=timezone.utc)
        except OSError:
            return None

    def http_json(self, url: Any, *, timeout: float = 5.0) -> tuple[int | None, Any]:
        safe_url = _safe_http_url(url)
        if safe_url in self._http_json_cache:
            return self._http_json_cache[safe_url]
        req = urllib.request.Request(safe_url, headers={"Accept": "application/json"}, method="GET")
        try:
            with urllib.request.build_opener(_NoRedirect).open(req, timeout=timeout) as response:
                body = response.read(2_000_001)
                if len(body) > 2_000_000:
                    result = (response.status, None)
                else:
                    result = (response.status, json.loads(body))
        except Exception:  # noqa: BLE001 - raw exception text is intentionally discarded
            result = (None, None)
        self._http_json_cache[safe_url] = result
        return result

    def http_text(self, url: Any, *, timeout: float = 5.0) -> tuple[int | None, str | None]:
        safe_url = _safe_http_url(url)
        if safe_url in self._http_text_cache:
            return self._http_text_cache[safe_url]
        req = urllib.request.Request(safe_url, method="GET")
        try:
            with urllib.request.build_opener(_NoRedirect).open(req, timeout=timeout) as response:
                body = response.read(2_000_001)
                if len(body) > 2_000_000:
                    result = (response.status, None)
                else:
                    result = (response.status, body.decode("utf-8", errors="replace"))
        except Exception:  # noqa: BLE001
            result = (None, None)
        self._http_text_cache[safe_url] = result
        return result


def load_topology(path: Path | str) -> dict[str, Any]:
    target = Path(path)
    raw = yaml.safe_load(target.read_text())
    if not isinstance(raw, dict) or raw.get("schema") != TOPOLOGY_SCHEMA:
        raise TopologyError(f"{target} is not {TOPOLOGY_SCHEMA}")
    _topology_ids(raw)
    return raw


def topology_sha256(topology: Mapping[str, Any]) -> str:
    canonical = json.dumps(topology, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(canonical).hexdigest()


def _records(topology: Mapping[str, Any], key: str) -> list[Mapping[str, Any]]:
    value = topology.get(key, [])
    if isinstance(value, Mapping):
        value = [dict(v, id=k) if isinstance(v, Mapping) else v for k, v in value.items()]
    if not isinstance(value, list) or not all(isinstance(row, Mapping) for row in value):
        raise TopologyError(f"topology {key!r} must be a list or mapping")
    return list(value)


def _topology_ids(topology: Mapping[str, Any]) -> dict[str, list[str]]:
    """Validate the durable census and return expected IDs by output section."""
    if topology.get("schema") != TOPOLOGY_SCHEMA:
        raise TopologyError(f"expected topology schema {TOPOLOGY_SCHEMA}")
    if topology.get("project_id") != "mastermind-x":
        raise TopologyError("topology project_id must be mastermind-x")
    result: dict[str, list[str]] = {}
    for output_key, topology_key in _TOPOLOGY_SECTIONS.items():
        ids = [_safe_id(row.get("id"), field=f"{topology_key} id") for row in _records(topology, topology_key)]
        duplicates = sorted(item_id for item_id, count in Counter(ids).items() if count > 1)
        if duplicates:
            raise TopologyError(f"duplicate {topology_key} ids: {', '.join(duplicates)}")
        result[output_key] = sorted(ids)
    if set(result["releases"]) != {"macro", "terminal", "portfolio"}:
        raise TopologyError("topology must name macro, terminal, and portfolio repositories")
    return result


def _systemd(reader: SystemEvidenceReader, unit: str) -> dict[str, Any]:
    safe_unit = _safe_unit(unit)
    code, out = reader.run([
        "systemctl", "show", safe_unit, "--no-pager",
        "--property=" + ",".join(_SYSTEMD_PROPS),
    ])
    if code not in (0, 1) or not out:
        return {"observed": False}
    parsed: dict[str, str] = {}
    for line in out.splitlines():
        key, sep, value = line.partition("=")
        if sep and key in _SYSTEMD_PROPS:
            parsed[key] = value
    load = parsed.get("LoadState")
    if load in {None, "not-found", "error", "bad-setting"}:
        return {"observed": True, "present": False}
    restarts = parsed.get("NRestarts", "")
    return {
        "observed": True,
        "present": load == "loaded",
        "activity": parsed.get("ActiveState"),
        "substate": parsed.get("SubState"),
        "enablement": parsed.get("UnitFileState"),
        "result": parsed.get("Result"),
        "restart_count": int(restarts) if restarts.isdigit() else None,
        "last_start": _parse_time(parsed.get("ExecMainStartTimestamp")),
        "last_trigger": _parse_time(parsed.get("LastTriggerUSec")),
        "next_trigger": _parse_time(parsed.get("NextElapseUSecRealtime")),
    }


def _json_probe(probe: Mapping[str, Any], reader: SystemEvidenceReader) -> tuple[bool, Any, datetime | None]:
    kind = probe.get("kind")
    if kind == "json_file":
        raw = reader.read_json(probe.get("path"))
        observed = raw is not None
        return observed, raw, reader.mtime(probe.get("path")) if observed else None
    if kind in {"http_json", "scheduler_api"}:
        status, raw = reader.http_json(probe.get("url"))
        return status is not None, raw, None
    if kind in {None, "none"}:
        return False, None, None
    raise TopologyError(f"unsupported JSON probe kind: {kind!r}")


def _probe_sha(probe: Any, reader: SystemEvidenceReader) -> str | None:
    if not isinstance(probe, Mapping):
        return None
    kind = probe.get("kind")
    value: Any = None
    resolution_path: Path | None = None
    if kind in {"git_head", "git_ref"}:
        path = reader.path(probe.get("path"))
        ref = "HEAD" if kind == "git_head" else str(probe.get("ref") or "HEAD")
        if not re.fullmatch(r"[A-Za-z0-9_./@{}^~:-]+", ref):
            raise TopologyError(f"unsafe git ref: {ref!r}")
        code, out = reader.run(["git", "-C", str(path), "rev-parse", "--verify", f"{ref}^{{commit}}"])
        value = out.strip().splitlines()[0] if code == 0 and out.strip() else None
        resolution_path = path
    elif kind == "git_remote_ref" and probe.get("path"):
        path = reader.path(probe.get("path"))
        ref = str(probe.get("ref") or "")
        if not re.fullmatch(r"(?:origin/)?(?:main|master)", ref):
            raise TopologyError("unapproved canonical local git ref")
        code, out = reader.run(["git", "-C", str(path), "rev-parse", "--verify", f"{ref}^{{commit}}"])
        value = out.strip().splitlines()[0] if code == 0 and out.strip() else None
        resolution_path = path
    elif kind in {"git_remote_ref", "github_ref"}:
        slug = str(probe.get("slug") or "")
        remote = str(probe.get("remote") or (f"https://github.com/{slug}.git" if slug else ""))
        if remote not in {
            "https://github.com/mastermindx-market-intelligence/macro.git",
            "https://github.com/mastermindx-market-intelligence/mastermind-terminal.git",
            "https://github.com/mastermindx-market-intelligence/Mastermind.git",
        }:
            raise TopologyError("unapproved canonical git remote")
        ref = str(probe.get("ref") or "")
        if ref in {"main", "master"}:
            ref = f"refs/heads/{ref}"
        if not re.fullmatch(r"refs/heads/(?:main|master)", ref):
            raise TopologyError("unapproved canonical git remote ref")
        code, out = reader.run(["git", "ls-remote", remote, ref], timeout=12)
        value = out.split()[0] if code == 0 and out.split() else None
    elif kind in {"marker_file", "text_file"}:
        value = reader.read_text(probe.get("path"), max_bytes=512)
        resolution = probe.get("resolve_path")
        resolution_path = reader.path(resolution) if resolution else None
    elif kind == "http_json":
        status, raw = reader.http_json(probe.get("url"))
        value = _nested(raw, str(probe.get("sha_field") or "version")) if status == 200 else None
        resolution = probe.get("resolve_path")
        resolution_path = reader.path(resolution) if resolution else None
    elif kind == "http_html_attribute":
        status, body = reader.http_text(probe.get("url"))
        attr = str(probe.get("attribute") or "")
        if not re.fullmatch(r"data-[a-z0-9-]{1,40}", attr):
            raise TopologyError("unsafe HTML release attribute")
        if status == 200 and body:
            match = re.search(rf"\b{re.escape(attr)}=[\"']([0-9a-f]{{7,40}})[\"']", body, re.I)
            value = match.group(1) if match else None
    elif kind in {None, "none", "http"}:
        return None
    else:
        raise TopologyError(f"unsupported SHA probe kind: {kind!r}")
    lines = str(value or "").strip().splitlines()
    text = lines[0].lower() if lines else ""
    if _SHA_RE.fullmatch(text):
        return text
    if _SHORT_SHA_RE.fullmatch(text) and resolution_path is not None:
        code, out = reader.run([
            "git", "-C", str(resolution_path), "rev-parse", "--verify", f"{text}^{{commit}}",
        ])
        resolved = out.strip().lower() if code == 0 else ""
        return resolved if _SHA_RE.fullmatch(resolved) else None
    return None


def _git_lag(
    reader: SystemEvidenceReader, probe: Any, deployed: str | None, canonical: str | None,
) -> int | None:
    if not deployed or not canonical or not isinstance(probe, Mapping):
        return None
    path_value = probe.get("resolve_path")
    if not path_value and probe.get("kind") in {"git_head", "git_ref"}:
        path_value = probe.get("path")
    if not path_value:
        return 0 if deployed == canonical else None
    path = reader.path(path_value)
    code, out = reader.run([
        "git", "-C", str(path), "rev-list", "--count", f"{deployed}..{canonical}",
    ])
    text = out.strip()
    return int(text) if code == 0 and text.isdigit() else None


def _health_probe(probe: Any, reader: SystemEvidenceReader) -> str:
    if not isinstance(probe, Mapping):
        return "indeterminate"
    kind = probe.get("kind")
    if kind in {"http_json", "http"}:
        if kind == "http_json":
            status, raw = reader.http_json(probe.get("url"))
        else:
            status, _ = reader.http_text(probe.get("url"))
            raw = None
        if status is None:
            return "indeterminate"
        if status != int(probe.get("expected_http_status", 200)):
            return "failed"
        field = probe.get("status_field")
        if not field:
            return "healthy"
        value = _nested(raw, str(field))
        mapping = probe.get("direct_status_map", {})
        if isinstance(mapping, Mapping) and str(value).lower() in mapping:
            state = mapping[str(value).lower()]
            return state if state in STATES else "indeterminate"
        truth = _bool(value)
        return "healthy" if truth is True else "failed" if truth is False else "indeterminate"
    if kind in {None, "none"}:
        return "indeterminate"
    raise TopologyError(f"unsupported health probe kind: {kind!r}")


def freshness_state(
    observed_at: datetime | None,
    *,
    now: datetime,
    max_age_seconds: int | None,
    direct_state: str | None = None,
) -> str:
    """Classify freshness without conflating missing, stale, or future evidence."""
    if direct_state in STATES and direct_state not in {"healthy", "degraded"}:
        return direct_state
    if observed_at is None:
        return "missing"
    age = int((_as_utc(now) - _as_utc(observed_at)).total_seconds())
    if age < -300:
        return "indeterminate"
    if max_age_seconds is not None and age > int(max_age_seconds):
        return "stale"
    return direct_state if direct_state in {"healthy", "degraded"} else "healthy"


def _direct_state(value: Any, mapping: Any) -> str | None:
    if not isinstance(mapping, Mapping):
        return None
    state = mapping.get(str(value).strip().lower())
    return state if state in STATES else None


def _safe_metrics(raw: Any, spec: Any) -> dict[str, int | float | bool | None]:
    if not isinstance(raw, Mapping) or not isinstance(spec, Mapping):
        return {}
    result: dict[str, int | float | bool | None] = {}
    for output_key, selector in sorted(spec.items()):
        key = str(output_key)
        if not _SAFE_METRIC_RE.fullmatch(key) or _FORBIDDEN_KEY_RE.search(key):
            raise TopologyError(f"unsafe metric name: {key!r}")
        value = _nested(raw, str(selector))
        if value is None or isinstance(value, (bool, int)) or isinstance(value, float) and math.isfinite(value):
            result[key] = value
    return result


def _ownership(row: Mapping[str, Any], repos: set[str]) -> tuple[str, str, bool]:
    repo = str(row.get("repo", row.get("owner_repo", "unresolved")) or "unresolved")
    owner = str(row.get("owner", "unresolved") or "unresolved")
    repo_ok = repo in repos
    owner_ok = bool(_ID_RE.fullmatch(owner))
    return (repo if repo_ok else "unresolved", owner if owner_ok else "unresolved", repo_ok and owner_ok)


def _collect_releases(
    topology: Mapping[str, Any], reader: SystemEvidenceReader, now: datetime,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for repo in _records(topology, "repositories"):
        repo_id = _safe_id(repo.get("id"), field="repository id")
        expected_branch = str(repo.get("branch", repo.get("canonical_branch", "")))
        if expected_branch not in {"main", "master"}:
            raise TopologyError(f"invalid expected branch for {repo_id}")
        deployed_probe = repo.get("deployed_probe")
        canonical_probe = repo.get("canonical_probe")
        runtime_probe = repo.get("runtime_probe")
        runtime_identity_expected = isinstance(runtime_probe, Mapping) and runtime_probe.get("kind") not in {None, "none", "http"}
        if isinstance(runtime_probe, Mapping) and runtime_probe.get("kind") == "http_json" and isinstance(deployed_probe, Mapping):
            resolve_path = deployed_probe.get("resolve_path")
            if not resolve_path and deployed_probe.get("kind") in {"git_head", "git_ref"}:
                resolve_path = deployed_probe.get("path")
            if resolve_path:
                runtime_probe = dict(runtime_probe, resolve_path=resolve_path)
        deployed = _probe_sha(deployed_probe, reader)
        canonical = _probe_sha(canonical_probe, reader)
        runtime = _probe_sha(runtime_probe, reader)
        lag = _git_lag(reader, deployed_probe, deployed, canonical)
        match = runtime == deployed if runtime and deployed else None
        policy = str(repo.get("runtime_match_policy") or "exact")
        if deployed is None or canonical is None:
            state = "indeterminate"
        elif deployed != canonical:
            state = "degraded"
        elif runtime_identity_expected and runtime is None:
            state = "indeterminate"
        elif match is False:
            # Macro intentionally keeps an older API process when a release
            # changes no import-cached API path. Without a deploy receipt that
            # proves the changed-path decision, disagreement is unknown rather
            # than either green or failed.
            state = "indeterminate" if policy == "selective_restart" else "degraded"
        else:
            state = "healthy"
        rows.append({
            "id": repo_id,
            "repo": repo_id,
            "expected_branch": expected_branch,
            "deployed_sha": deployed,
            "canonical_branch_sha": canonical,
            "runtime_sha": runtime,
            "state": state,
            "deployment_lag": lag,
            "runtime_match": match,
            "runtime_match_policy": policy,
        })
    return sorted(rows, key=lambda row: row["id"])


def _collect_services(
    topology: Mapping[str, Any], reader: SystemEvidenceReader, now: datetime, repos: set[str],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in _records(topology, "services"):
        item_id = _safe_id(item.get("id"))
        repo, owner, _ = _ownership(item, repos)
        expectation = _safe_expectation(item.get("expected_state", item.get("expectation")))
        unit_names = item.get("units", item.get("expected_units", []))
        if isinstance(unit_names, str):
            unit_names = [unit_names]
        if not isinstance(unit_names, list) or not unit_names:
            raise TopologyError(f"service {item_id} has no units")
        units: list[dict[str, Any]] = []
        evidence_rows = []
        for unit_name in unit_names:
            ev = _systemd(reader, str(unit_name))
            evidence_rows.append(ev)
            if not ev.get("observed"):
                unit_state = "unknown"
            elif not ev.get("present"):
                unit_state = "not_found"
            else:
                unit_state = str(ev.get("activity") or "indeterminate")
                if unit_state not in {"active", "inactive", "failed", "activating", "deactivating"}:
                    unit_state = "unknown"
            units.append({
                "name": _safe_unit(unit_name),
                "state": unit_state,
                "substate": _safe_version(ev.get("substate")),
                "restart_count": ev.get("restart_count"),
                "last_start": _iso(ev.get("last_start")),
            })
        health = _health_probe(item.get("health_probe"), reader) if item.get("health_probe") else "indeterminate"
        if expectation == "disabled":
            state = "disabled" if all(u["state"] in {"inactive", "not_found", "unknown"} for u in units) else "degraded"
        elif expectation == "operator_armed" and any(u["state"] == "not_found" for u in units):
            state = "indeterminate"
        elif expectation == "operator_armed" and all(u["state"] == "inactive" for u in units):
            state = "operator_armed"
        elif any(u["state"] == "not_found" for u in units):
            state = "missing" if expectation == "required" else "indeterminate"
        elif any(u["state"] in {"failed", "inactive"} for u in units):
            state = "failed" if expectation == "required" else "degraded"
        elif any(u["state"] == "unknown" for u in units):
            state = "indeterminate"
        elif health == "failed":
            state = "failed"
        elif health == "indeterminate" and item.get("health_probe"):
            state = "degraded"
        else:
            state = "healthy"
        rows.append({
            "id": item_id,
            "repo": repo,
            "owner": owner,
            "kind": _safe_id(item.get("kind", "service"), field="service kind"),
            "host_class": _safe_id(item.get("host_class", "vps"), field="host class"),
            "state": state,
            "units": units,
            "health_state": health,
        })
    return sorted(rows, key=lambda row: row["id"])


def _schedule_probe(
    item: Mapping[str, Any], reader: SystemEvidenceReader,
) -> tuple[bool, datetime | None, datetime | None, datetime | None, str | None, str | None]:
    probe = item.get("probe")
    if not isinstance(probe, Mapping):
        return False, None, None, None, None, None
    kind = probe.get("kind")
    if kind in {None, "none"}:
        return False, None, None, None, None, None
    if kind == "systemd_timer":
        ev = _systemd(reader, str(probe.get("unit")))
        service_unit = str(probe.get("service") or str(probe.get("unit")).removesuffix(".timer") + ".service")
        service_ev = _systemd(reader, service_unit)
        service_result = service_ev.get("result")
        if service_result in {"failed", "exit-code", "signal", "timeout", "core-dump", "watchdog"}:
            outcome = "failed"
        elif service_result == "success" and ev.get("last_trigger"):
            outcome = "succeeded"
        else:
            outcome = None
        activity = "not_found" if ev.get("observed") and not ev.get("present") else ev.get("activity")
        return bool(ev.get("observed")), ev.get("last_trigger"), ev.get("last_trigger") if outcome == "succeeded" else None, ev.get("next_trigger"), outcome, activity
    if kind == "artifact":
        probe = dict(probe, kind="json_file")
        kind = "json_file"
    if kind in {"scheduler_api", "json_file"}:
        observed, raw, mtime = _json_probe(probe, reader)
        if kind == "scheduler_api":
            jobs = _nested(raw, str(probe.get("jobs_field") or "jobs"))
            configured = probe.get("jobs")
            if isinstance(configured, list):
                selected = [row for row in jobs if isinstance(row, Mapping) and str(row.get("id")) in configured] if isinstance(jobs, list) else []
                if {str(row.get("id")) for row in selected} != {str(value) for value in configured}:
                    return False, None, None, None, None, None
                started_field = str(probe.get("last_started_field") or "last_started")
                finished_field = str(probe.get("last_finished_field") or "last_finished")
                skipped_field = str(probe.get("last_skipped_field") or "last_skipped")
                status_field = str(probe.get("outcome_field") or "last_status")
                next_field = str(probe.get("next_expected_field") or "next_run_time")
                outcome_map = probe.get("outcome_map", {})
                if not isinstance(outcome_map, Mapping):
                    outcome_map = {}
                normalized: list[tuple[datetime | None, datetime | None, datetime | None, str | None]] = []
                for row in selected:
                    raw_status = str(_nested(row, status_field) or "").lower()
                    completed_outcome = outcome_map.get(raw_status) or {
                        "ok": "succeeded", "success": "succeeded", "succeeded": "succeeded",
                        "no_change": "ran_no_change", "ran_no_change": "ran_no_change",
                        "error": "failed", "failed": "failed", "skipped": "skipped", "skip": "skipped",
                        "warn": "warning", "warning": "warning",
                        "running": "in_progress",
                    }.get(raw_status)
                    started = _parse_time(_nested(row, started_field))
                    finished = _parse_time(_nested(row, finished_field))
                    skipped = _parse_time(_nested(row, skipped_field))
                    if started and started > max((value for value in (finished, skipped) if value), default=datetime.min.replace(tzinfo=timezone.utc)):
                        outcome = "in_progress"
                        last_run = started
                    elif skipped and (finished is None or skipped > finished):
                        outcome = "skipped"
                        last_run = skipped
                    else:
                        outcome = completed_outcome
                        last_run = finished or started
                    normalized.append((
                        last_run,
                        finished if completed_outcome in {"succeeded", "ran_no_change"} else None,
                        _parse_time(_nested(row, next_field)),
                        outcome,
                    ))
                starts = [value for value, _, _, _ in normalized if value is not None]
                successes = [finished for _, finished, _, _ in normalized if finished is not None]
                next_runs = [value for _, _, value, _ in normalized if value is not None]
                outcomes = [outcome for *_, outcome in normalized]
                aggregate = (
                    "failed" if "failed" in outcomes else
                    "in_progress" if "in_progress" in outcomes else
                    "ran_no_change" if outcomes and all(outcome in {"succeeded", "ran_no_change"} for outcome in outcomes) and "ran_no_change" in outcomes else
                    "succeeded" if outcomes and all(outcome == "succeeded" for outcome in outcomes) else
                    "skipped" if outcomes and all(outcome == "skipped" for outcome in outcomes) else
                    None
                )
                return True, max(starts, default=None), max(successes, default=None), min(next_runs, default=None), aggregate, None
            else:
                job_id = str(probe.get("job_id") or item.get("id"))
                raw = next((row for row in jobs if isinstance(row, Mapping) and str(row.get("id")) == job_id), None) if isinstance(jobs, list) else None
            observed = observed and raw is not None
        last_run_selector = probe.get("last_run_field") or probe.get("as_of_field") or "last_run"
        last_run = _parse_time(_nested(raw, str(last_run_selector)))
        last_success = _parse_time(_nested(raw, str(probe.get("last_success_field") or "last_success")))
        next_expected = _parse_time(_nested(raw, str(probe.get("next_expected_field") or "next_expected")))
        raw_outcome = _nested(raw, str(probe.get("outcome_field") or "outcome"))
        outcome_map = probe.get("outcome_map", {})
        outcome = outcome_map.get(str(raw_outcome).lower()) if isinstance(outcome_map, Mapping) else None
        if outcome is None:
            default_outcomes = {
                "ok": "succeeded", "healthy": "succeeded", "success": "succeeded",
                "succeeded": "succeeded", "ran_no_change": "ran_no_change",
                "no_change": "ran_no_change", "failed": "failed", "error": "failed",
                "skipped": "skipped", "skip": "skipped", "warn": "warning",
                "warning": "warning", "running": "in_progress",
            }
            outcome = default_outcomes.get(str(raw_outcome).lower())
        if outcome not in {"succeeded", "ran_no_change", "failed", "skipped", "warning", "in_progress"}:
            outcome = None
        if kind == "scheduler_api":
            started = _parse_time(_nested(raw, str(probe.get("last_started_field") or "last_started")))
            finished = _parse_time(_nested(raw, str(probe.get("last_finished_field") or probe.get("last_run_field") or "last_finished")))
            skipped = _parse_time(_nested(raw, str(probe.get("last_skipped_field") or "last_skipped")))
            completed_outcome = outcome
            if started and started > max((value for value in (finished, skipped) if value), default=datetime.min.replace(tzinfo=timezone.utc)):
                outcome = "in_progress"
                last_run = started
            elif skipped and (finished is None or skipped > finished):
                outcome = "skipped"
                last_run = skipped
            else:
                last_run = finished or started
            if last_success is None and completed_outcome in {"succeeded", "ran_no_change"}:
                last_success = finished
        if last_run is None and probe.get("mtime_is_run_evidence"):
            last_run = mtime
        if last_success is None and outcome in {"succeeded", "ran_no_change"}:
            last_success = last_run
        return observed, last_run, last_success, next_expected, outcome, None
    if kind == "release_match":
        deployed_path = probe.get("deployed_repo")
        canonical_ref = str(probe.get("canonical_ref") or "")
        if not deployed_path or canonical_ref not in {"origin/main", "origin/master"}:
            return False, None, None, None, None, None
        deployed = _probe_sha({"kind": "git_head", "path": deployed_path}, reader)
        canonical_remote = probe.get("canonical_remote")
        canonical = _probe_sha(
            {"kind": "git_remote_ref", "remote": canonical_remote, "ref": f"refs/heads/{canonical_ref.split('/')[-1]}"}
            if canonical_remote else
            {"kind": "git_ref", "path": deployed_path, "ref": canonical_ref},
            reader,
        )
        if not deployed or not canonical:
            return False, None, None, None, None, None
        if probe.get("required_cron_id") == "macro_update":
            code, cron = reader.run(["crontab", "-l"])
            cron_present = code == 0 and any(
                re.fullmatch(r"\s*\*/3\s+\*\s+\*\s+\*\s+\*\s+/usr/local/bin/macro-update(?:\s+.*)?", line)
                for line in cron.splitlines()
            )
            if not cron_present:
                return True, None, None, None, "failed", None
        # Equality plus an installed cron proves configuration, not that the
        # cron has executed successfully. Without a durable run receipt the
        # schedule remains indeterminate.
        return True, None, None, None, None if deployed == canonical else "failed", None
    raise TopologyError(f"unsupported schedule probe kind: {kind!r}")


def _collect_schedules(
    topology: Mapping[str, Any], reader: SystemEvidenceReader, now: datetime, repos: set[str],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in _records(topology, "scheduled_systems"):
        item_id = _safe_id(item.get("id"))
        repo, owner, _ = _ownership(item, repos)
        expectation = _safe_expectation(item.get("expected_state", item.get("expectation")))
        observed, last_run, last_success, next_expected, outcome, activity = _schedule_probe(item, reader)
        raw_cadence = item.get("cadence", {})
        if isinstance(raw_cadence, Mapping):
            cadence = dict(raw_cadence)
        elif isinstance(raw_cadence, str):
            cadence = dict(_CADENCE_SPECS.get(raw_cadence, {}))
        else:
            cadence = {}
        probe = item.get("probe") if isinstance(item.get("probe"), Mapping) else {}
        default_scheduler_age = 345_600 if probe.get("kind") == "scheduler_api" else None
        max_age = cadence.get(
            "max_age_seconds",
            cadence.get("stale_after_seconds", probe.get("max_age_seconds", default_scheduler_age)),
        )
        max_run = cadence.get("max_run_seconds", probe.get("max_run_seconds"))
        if expectation == "disabled":
            if not observed:
                state = "indeterminate"
            else:
                state = "degraded" if activity == "active" or next_expected is not None or outcome == "in_progress" else "disabled"
        elif activity == "not_found":
            state = "missing" if expectation == "required" else "indeterminate"
        elif not observed:
            state = "indeterminate"
        elif expectation == "operator_armed" and activity != "active":
            state = "operator_armed"
        elif outcome == "failed" or activity == "failed":
            state = "failed"
        elif outcome == "in_progress" and max_run is not None and last_run is not None and (now - last_run).total_seconds() > int(max_run):
            state = "failed"
        elif outcome == "in_progress":
            state = "in_progress"
        elif probe.get("kind") == "scheduler_api" and next_expected is None:
            state = "indeterminate"
        elif next_expected is not None and next_expected < now - timedelta(minutes=5):
            state = "stale"
        elif max_age is not None and last_success is not None and (now - last_success).total_seconds() > int(max_age):
            state = "stale"
        elif outcome == "ran_no_change":
            state = "ran_no_change"
        elif outcome == "warning":
            state = "degraded"
        elif outcome == "skipped":
            state = "not_due"
        elif outcome == "succeeded" and last_run is None:
            state = "healthy"
        elif last_run is None and next_expected and next_expected > now:
            state = "not_due"
        elif activity == "inactive" and expectation == "required":
            state = "failed"
        elif last_run is not None and outcome is None:
            state = "indeterminate"
        elif last_run is None:
            state = "indeterminate"
        else:
            state = "healthy"
        rows.append({
            "id": item_id,
            "repo": repo,
            "owner": owner,
            "kind": _safe_id(item.get("kind", (item.get("probe") or {}).get("kind", "cron")), field="scheduled kind"),
            "host_class": _safe_id(item.get("host_class", "vps"), field="host class"),
            "state": state,
            "last_run": _iso(last_run),
            "last_success": _iso(last_success),
            "next_expected": _iso(next_expected),
            "run_outcome": outcome or "indeterminate",
        })
    return sorted(rows, key=lambda row: row["id"])


def _collect_fresh_records(
    topology: Mapping[str, Any], key: str, reader: SystemEvidenceReader,
    now: datetime, repos: set[str],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in _records(topology, key):
        item_id = _safe_id(item.get("id"))
        repo, owner, _ = _ownership(item, repos)
        probe = item.get("probe", {})
        if not isinstance(probe, Mapping):
            raise TopologyError(f"{key} {item_id} has invalid probe")
        if probe.get("kind") == "symlink_and_json":
            link = reader.path(probe.get("path"))
            expected_target = reader.path(probe.get("expected_target"))
            try:
                link_ok = link.is_symlink() and link.resolve() == expected_target
            except OSError:
                link_ok = False
            artifact_probe = dict(probe, kind="json_file", path=probe.get("artifact_path"))
            observed, raw, mtime = _json_probe(artifact_probe, reader)
            observed = observed and link_ok
            probe = artifact_probe
        else:
            observed, raw, mtime = _json_probe(probe, reader)
        status_value = _nested(raw, str(probe.get("status_field"))) if probe.get("status_field") else None
        direct = _direct_state(status_value, probe.get("direct_status_map"))
        if probe.get("status_field") and isinstance(probe.get("direct_status_map"), Mapping) and direct is None:
            direct = "indeterminate"
        if probe.get("minimum_field"):
            measured = _nested(raw, str(probe.get("minimum_field")))
            minimum = probe.get("minimum_value")
            if isinstance(measured, (int, float)) and not isinstance(measured, bool) and isinstance(minimum, (int, float)):
                direct = "healthy" if measured >= minimum else "degraded"
            else:
                direct = "indeterminate"
        timestamp = _parse_time(_nested(raw, str(probe.get("timestamp_field")))) if probe.get("timestamp_field") else None
        as_of = _parse_time(_nested(raw, str(probe.get("as_of_field")))) if probe.get("as_of_field") else None
        configured_basis = str(probe.get("freshness_basis") or "")
        if configured_basis == "as_of":
            evidence_time = as_of
        elif configured_basis == "timestamp":
            evidence_time = timestamp
        elif configured_basis == "mtime":
            evidence_time = mtime if probe.get("allow_mtime") else None
        else:
            # Publication time is the correct wall-clock recency proof when a
            # receipt also carries a date-only source watermark.
            evidence_time = timestamp or as_of or (mtime if probe.get("allow_mtime") else None)
        freshness_basis = configured_basis or ("timestamp" if timestamp else "as_of" if as_of else "mtime" if evidence_time is mtime and mtime else "unavailable")
        state = "missing" if not observed else freshness_state(
            evidence_time,
            now=now,
            max_age_seconds=probe.get("max_age_seconds"),
            direct_state=direct,
        )
        if state == "healthy" and probe.get("healthy_result_state") in STATES:
            state = str(probe.get("healthy_result_state"))
        base = {
            "id": item_id,
            "owner": owner,
            "state": state,
            "as_of": _iso(as_of),
            "observed_at": _iso(timestamp or mtime or now),
            "freshness_basis": freshness_basis,
        }
        if key == "data_planes":
            base["repo"] = repo
            base["metrics"] = _safe_metrics(raw, probe.get("metric_fields"))
        elif key == "bridges":
            base.update({
                "producer_repo": _safe_id(item.get("producer_repo", owner), field="producer repo"),
                "consumer_repo": _safe_id(item.get("consumer_repo"), field="consumer repo"),
                "authority": _safe_id(item.get("authority", "sanitized_observability"), field="bridge authority"),
            })
        rows.append(base)
    return sorted(rows, key=lambda row: row["id"])


def _collect_storage(
    topology: Mapping[str, Any], reader: SystemEvidenceReader, now: datetime, repos: set[str],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in _records(topology, "storage"):
        item_id = _safe_id(item.get("id"))
        repo, owner, _ = _ownership(item, repos)
        probe = item.get("probe", {})
        observed, raw, mtime = (False, None, None)
        original_probe_kind = probe.get("kind") if isinstance(probe, Mapping) else None
        if isinstance(probe, Mapping) and probe.get("kind") == "sentinel_surface":
            raw_all = reader.read_json(probe.get("path"))
            surface_id = str(probe.get("surface_id") or "")
            surfaces = raw_all.get("surfaces", {}) if isinstance(raw_all, Mapping) else {}
            raw = surfaces.get(surface_id) if isinstance(surfaces, Mapping) else None
            observed = isinstance(raw, Mapping)
            mtime = reader.mtime(probe.get("path")) if observed else None
            probe = dict(probe, timestamp_field="bake_stamp", status_field="status", direct_status_map={"ok": "healthy", "healthy": "healthy", "stale": "stale", "missing": "missing", "indeterminate": "indeterminate"})
        elif isinstance(probe, Mapping) and probe.get("kind") == "path_exists":
            target = reader.path(probe.get("path"))
            observed = target.exists()
            raw = {}
            mtime = reader.mtime(probe.get("path")) if observed else None
        elif isinstance(probe, Mapping) and probe.get("kind") == "schema_contract_only":
            observed, raw, mtime = False, None, None
        elif isinstance(probe, Mapping):
            observed, raw, mtime = _json_probe(probe, reader)
        expected_schema = _safe_version(item.get("expected_schema"))
        observed_schema = _safe_version(_nested(raw, str(probe.get("schema_field")))) if observed and probe.get("schema_field") else None
        timestamp = _parse_time(_nested(raw, str(probe.get("timestamp_field")))) if observed and probe.get("timestamp_field") else None
        direct = _direct_state(_nested(raw, str(probe.get("status_field"))), probe.get("direct_status_map")) if observed and probe.get("status_field") else None
        if not observed:
            state = "indeterminate" if original_probe_kind in {None, "none", "schema_contract_only"} else "missing"
        elif original_probe_kind == "path_exists":
            # Existence proves only that the mount point is present, not that
            # its contents are current, non-empty, or schema-compatible.
            state = "indeterminate"
        elif expected_schema and observed_schema and expected_schema != observed_schema:
            state = "degraded"
        else:
            state = freshness_state(timestamp or (mtime if probe.get("allow_mtime") else None), now=now, max_age_seconds=probe.get("max_age_seconds"), direct_state=direct)
        rows.append({
            "id": item_id,
            "repo": repo,
            "owner": owner,
            "kind": _safe_id(item.get("kind", "storage"), field="storage kind"),
            "state": state,
            "as_of": _iso(timestamp),
            "observed_at": _iso(mtime or now),
            "expected_schema": expected_schema,
            "observed_schema": observed_schema,
        })
    return sorted(rows, key=lambda row: row["id"])


def _collect_providers(
    topology: Mapping[str, Any], reader: SystemEvidenceReader, now: datetime, repos: set[str],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in _records(topology, "providers"):
        item_id = _safe_id(item.get("id"))
        repo, owner, _ = _ownership(item, repos)
        probe = item.get("probe", {})
        primary_state = "indeterminate"
        fallback_state = "indeterminate"
        metrics: dict[str, int | float | bool | None] = {}
        observed_at = now
        if isinstance(probe, Mapping) and probe.get("kind") in {"provider_jsonl", "jsonl_summary"}:
            rows_raw = reader.read_jsonl(probe.get("path"), tail=int(probe.get("tail", 100)))
            roles = probe.get("roles", {})
            if not isinstance(roles, Mapping):
                roles = {}
            counts = {"primary_attempts": 0, "primary_successes": 0, "fallback_attempts": 0, "fallback_successes": 0}
            newest: datetime | None = None
            latest: dict[str, tuple[datetime, int, bool]] = {}
            for index, raw in enumerate(rows_raw):
                if not isinstance(raw, Mapping):
                    continue
                if probe.get("kind") == "jsonl_summary" and raw.get("event") != "attempt":
                    continue
                role_selector = probe.get("role_field") or ("rung" if probe.get("kind") == "jsonl_summary" else "rung_role")
                role_value = str(_nested(raw, str(role_selector)) or "")
                bucket = roles.get(role_value)
                if bucket not in {"primary", "fallback"}:
                    continue
                ok = _bool(_nested(raw, str(probe.get("ok_field") or probe.get("status_field") or "ok")))
                if ok is None:
                    continue
                counts[f"{bucket}_attempts"] += 1
                counts[f"{bucket}_successes"] += int(ok)
                ts = _parse_time(_nested(raw, str(probe.get("timestamp_field") or "ts")))
                if ts:
                    if newest is None or ts > newest:
                        newest = ts
                    prior = latest.get(bucket)
                    if prior is None or (ts, index) >= (prior[0], prior[1]):
                        latest[bucket] = (ts, index, ok)
            observed_at = newest or reader.mtime(probe.get("path")) or now
            max_age = probe.get("max_age_seconds")
            for bucket in ("primary", "fallback"):
                latest_attempt = latest.get(bucket)
                state = "indeterminate" if latest_attempt is None else "healthy" if latest_attempt[2] else "failed"
                if latest_attempt is not None and max_age is not None:
                    age = int((now - latest_attempt[0]).total_seconds())
                    if age < -300:
                        state = "indeterminate"
                    elif age > int(max_age):
                        state = "stale"
                if bucket == "primary":
                    primary_state = state
                else:
                    fallback_state = state
            metrics = counts
        elif isinstance(probe, Mapping) and probe.get("kind") in {"json_file", "http_json"}:
            observed, raw, mtime = _json_probe(probe, reader)
            observed_at = mtime or now
            if observed:
                mapping = probe.get("direct_status_map", {})
                primary_state = _direct_state(_nested(raw, str(probe.get("primary_field") or "primary")), mapping) or "indeterminate"
                fallback_state = _direct_state(_nested(raw, str(probe.get("fallback_field") or "fallback")), mapping) or "indeterminate"
        state = (
            "healthy" if primary_state == "healthy" else
            "degraded" if fallback_state == "healthy" else
            "failed" if primary_state == fallback_state == "failed" else
            "stale" if "stale" in {primary_state, fallback_state} else
            "indeterminate"
        )
        rows.append({
            "id": item_id,
            "repo": repo,
            "owner": owner,
            "state": state,
            "observed_at": _iso(observed_at),
            "primary_state": primary_state,
            "fallback_state": fallback_state,
            "metrics": metrics,
        })
    return sorted(rows, key=lambda row: row["id"])


def _summaries(snapshot: Mapping[str, Any]) -> tuple[dict[str, dict[str, int]], list[dict[str, str]]]:
    summary: dict[str, dict[str, int]] = {}
    issues: list[dict[str, str]] = []
    singular = {
        "releases": "release", "services": "service", "scheduled_systems": "scheduled_system",
        "data_planes": "data_plane", "bridges": "bridge", "storage": "storage", "providers": "provider",
    }
    for key in ("releases", "services", "scheduled_systems", "data_planes", "bridges", "storage", "providers"):
        rows = snapshot.get(key, [])
        counts = Counter(str(row.get("state", "indeterminate")) for row in rows)
        summary[key] = {state: counts[state] for state in sorted(counts)}
        for row in rows:
            state = str(row.get("state", "indeterminate"))
            if state in ISSUE_STATES:
                issues.append({
                    "component_type": singular[key],
                    "component_id": str(row["id"]),
                    "state": state,
                    "owner": str(row.get("owner", row.get("repo", "UNRESOLVED"))),
                })
    issues.sort(key=lambda row: (row["component_type"], row["component_id"]))
    return summary, issues


def collect_runtime_state(
    topology: Mapping[str, Any],
    *,
    reader: SystemEvidenceReader | None = None,
    now: datetime | None = None,
    mode: str = "vps",
    valid_for_seconds: int = DEFAULT_VALID_FOR_SECONDS,
) -> dict[str, Any]:
    """Collect one canonical, sanitized runtime snapshot without mutating producers."""
    expected_ids = _topology_ids(topology)
    checked = _as_utc(now or _utc_now()).replace(microsecond=0)
    evidence = reader or SystemEvidenceReader(mode=mode)
    repo_rows = _records(topology, "repositories")
    repos = {_safe_id(row.get("id"), field="repository id") for row in repo_rows}

    runtime_policy = topology.get("runtime_state_policy", {})
    if not isinstance(runtime_policy, Mapping):
        runtime_policy = {}

    snapshot: dict[str, Any] = {
        "schema": SCHEMA,
        "project_id": str(topology.get("project_id") or "mastermind-x"),
        "environment": str(topology.get("environment") or "production"),
        "visibility": str(runtime_policy.get("visibility") or topology.get("runtime_visibility") or "private_authenticated"),
        "checked_at": _iso(checked),
        "valid_until": _iso(checked + timedelta(seconds=int(valid_for_seconds))),
        "collector_mode": mode,
        "topology_version": topology_sha256(topology),
        "releases": _collect_releases(topology, evidence, checked),
        "services": _collect_services(topology, evidence, checked, repos),
        "scheduled_systems": _collect_schedules(topology, evidence, checked, repos),
        "data_planes": _collect_fresh_records(topology, "data_planes", evidence, checked, repos),
        "bridges": _collect_fresh_records(topology, "bridges", evidence, checked, repos),
        "storage": _collect_storage(topology, evidence, checked, repos),
        "providers": _collect_providers(topology, evidence, checked, repos),
    }
    all_rows = [
        row for key in ("releases", "services", "scheduled_systems", "data_planes", "bridges", "storage", "providers")
        for row in snapshot[key]
    ]
    reported_ids = {
        key: sorted(str(row["id"]) for row in snapshot[key])
        for key in _TOPOLOGY_SECTIONS
    }
    omitted = sorted({
        item_id
        for key in _TOPOLOGY_SECTIONS
        for item_id in set(expected_ids[key]) - set(reported_ids[key])
    })
    unresolved = sorted(row["id"] for row in all_rows if row.get("owner", row.get("repo")) == "unresolved" or row.get("repo") == "unresolved")
    evidence_gaps = sorted(row["id"] for row in all_rows if row.get("state") == "indeterminate")
    missing = sorted(set(omitted) | {str(row["id"]) for row in all_rows if row.get("state") == "missing"})
    snapshot["coverage"] = {
        "state": "complete" if not (unresolved or omitted or evidence_gaps) else "degraded",
        "expected_by_kind": {
            key: len(expected_ids[key]) for key in _TOPOLOGY_SECTIONS
        },
        "reported_by_kind": {
            key: len(reported_ids[key]) for key in _TOPOLOGY_SECTIONS
        },
        "missing_ids": missing,
        "evidence_gap_ids": evidence_gaps,
        "unresolved_owner_ids": unresolved,
    }
    snapshot["summary"], snapshot["issues"] = _summaries(snapshot)
    assert_private_safe(snapshot)
    return snapshot


def assert_private_safe(value: Any, *, path: str = "$.") -> None:
    """Fail closed if canonical output contains a secret/private-data shape."""
    if isinstance(value, Mapping):
        for key, child in value.items():
            key_text = str(key)
            if _FORBIDDEN_KEY_RE.search(key_text):
                raise PrivacyViolation(f"forbidden key at {path}{key_text}")
            assert_private_safe(child, path=f"{path}{key_text}.")
        return
    if isinstance(value, list):
        for index, child in enumerate(value):
            assert_private_safe(child, path=f"{path}{index}.")
        return
    if isinstance(value, str):
        if any(ord(char) < 32 and char not in "\t" for char in value) or "\n" in value or "\r" in value:
            raise PrivacyViolation(f"control character at {path}")
        if any(pattern.search(value) for pattern in _FORBIDDEN_TEXT_RES):
            raise PrivacyViolation(f"forbidden text at {path}")
        return
    if isinstance(value, float) and not math.isfinite(value):
        raise PrivacyViolation(f"non-finite number at {path}")


def snapshot_expired(snapshot: Mapping[str, Any], *, at: datetime | None = None) -> bool:
    """Fail closed when a snapshot lacks a valid future expiry."""
    valid_until = _parse_time(snapshot.get("valid_until"))
    return valid_until is None or _as_utc(at or _utc_now()) > valid_until


def render_markdown(snapshot: Mapping[str, Any], *, evaluated_at: datetime | None = None) -> str:
    """Render a deterministic operator report from an already-safe snapshot."""
    assert_private_safe(snapshot)
    lines = [
        "# Mastermind-X runtime state",
        "",
        f"Checked: {snapshot.get('checked_at')} · Valid until: {snapshot.get('valid_until')}",
        "",
    ]
    if snapshot_expired(snapshot, at=evaluated_at):
        lines.extend(["**EXPIRED — do not use this snapshot as current production evidence.**", ""])
    sections = (
        ("Deployed releases", "releases", ("id", "deployed_sha", "expected_branch", "state")),
        ("Services", "services", ("id", "owner", "health_state", "state")),
        ("Scheduled systems", "scheduled_systems", ("id", "last_success", "run_outcome", "state")),
        ("Critical data planes", "data_planes", ("id", "owner", "as_of", "state")),
        ("Cross-repo bridges", "bridges", ("id", "owner", "as_of", "state")),
        ("Storage", "storage", ("id", "owner", "observed_schema", "state")),
        ("Providers", "providers", ("id", "primary_state", "fallback_state", "state")),
    )
    for title, key, columns in sections:
        lines.extend([f"## {title}", "", "| " + " | ".join(columns) + " |", "| " + " | ".join("---" for _ in columns) + " |"])
        for row in sorted(snapshot.get(key, []), key=lambda item: str(item.get("id", ""))):
            values = []
            for column in columns:
                value = row.get(column)
                text = "—" if value is None or value == "" else str(value)
                values.append(text.replace("|", "\\|"))
            lines.append("| " + " | ".join(values) + " |")
        if not snapshot.get(key):
            lines.append("| — | " + " | ".join("—" for _ in columns[1:]) + " |")
        lines.append("")
    lines.extend(["## Degraded, stale, or indeterminate", ""])
    issues = snapshot.get("issues", [])
    if not issues:
        lines.append("None.")
    else:
        for issue in issues:
            lines.append(f"- {issue['component_type']}/{issue['component_id']}: {issue['state']} — owner {issue['owner']}")
    lines.append("")
    return "\n".join(lines)


def canonical_json(snapshot: Mapping[str, Any]) -> str:
    assert_private_safe(snapshot)
    return json.dumps(snapshot, sort_keys=True, indent=2, separators=(",", ": "), allow_nan=False) + "\n"


def write_private_atomic(path: Path | str, content: str, *, mode: int = 0o600) -> None:
    """Atomically replace an explicitly private output without touching producers."""
    target = Path(path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{target.name}.", dir=str(target.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp_name, mode)
        os.replace(temp_name, target)
    finally:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass


def validate_snapshot(snapshot: Mapping[str, Any], schema_path: Path | str) -> None:
    from jsonschema import Draft202012Validator, FormatChecker

    assert_private_safe(snapshot)
    schema = json.loads(Path(schema_path).read_text())
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(snapshot)


__all__ = [
    "DEFAULT_VALID_FOR_SECONDS", "PrivacyViolation", "RuntimeStateError", "SCHEMA",
    "STATES", "SystemEvidenceReader", "TOPOLOGY_SCHEMA", "TopologyError",
    "assert_private_safe", "canonical_json", "collect_runtime_state", "freshness_state",
    "load_topology", "render_markdown", "snapshot_expired", "topology_sha256", "validate_snapshot",
    "write_private_atomic",
]
