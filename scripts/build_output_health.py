"""scripts/build_output_health.py — evidence gathering for Eval OS T4 (output health).

THE ADAPTER, NOT THE CONTRACT. Every rule about what a state MEANS lives in the pure
resolver :mod:`engine.output_health`; this file only goes and looks. It probes presence,
reads the one declared watermark field, normalizes the existing health surfaces
(freshness sentinel, R2 audit, Neural Web lobes, foresight legs, provider telemetry) into
the resolver's input shapes, and prints the resulting view.

IT WRITES NOTHING, EVER. The view is derived on demand and emitted on stdout — same
architecture as the T1 registry it joins against, and for the same measured reason: there
is no stable input to pin a committed health file against (``config/synapse.yml`` alone
took 69 commits in the trailing 14 days), so a committed artifact plus an equality check
would be a scheduled fleet-wide red. A caller that wants the view holds it in memory or
reads this JSON.

THE PRESENCE LADDER IS STORAGE-AWARE, AND ITS DEFAULTS ARE ASYMMETRIC ON PURPOSE
-------------------------------------------------------------------------------
``git`` / ``git+r2``   worktree file, else the blob at HEAD (``read_tracked``'s ladder).
                       A tracked-but-unmaterialized artifact read from HEAD is a REAL
                       observation, not blindness — that is what makes a sparse agent
                       worktree answer the same as a full checkout. Unreachable BOTH ways
                       is a definitive absence **only when git itself answered**; where
                       git cannot be consulted at all the same silence is blindness, and
                       minting 600 "unavailable" verdicts out of a broken probe is the
                       failure this asymmetry exists to prevent.
``gitignored-local``   worktree only. Absent means INVISIBLE FROM A CHECKOUT (the file is
                       written at runtime on another host), never ``exists=False``.
``r2``                 not probeable from here at all: ``exists=None`` unless the R2 audit
                       covers its anchor, in which case the reader plane supplies presence.
                       Presence is never fabricated from an anchor that was not checked.
placeholder paths      ``<SYM>``-style paths name a family, not a file — no probe.

WATERMARKS: THE DECLARED FIELD ONLY
-----------------------------------
The governing field is ``staleness_from`` when declared, else ``asof_field``, and this
adapter looks for THAT KEY AND NO OTHER. When it is absent from the content it reports the
absence (``asof_field_present=False``) instead of reaching for whatever timestamp the file
happens to carry — ``engine/neuralweb/health.py``'s ``_AS_OF_KEYS`` fallback ladder is
deliberately NOT inherited, because a fallback makes a frozen store read fresh forever.

``--trust-mtime`` IS OFF BY DEFAULT. File mtimes in this repo are observer-stamped —
``git status`` sweeps, a Finder visit and ``reflog expire`` all rewrite them, measured
across the fleet pinning 137 of 143 dead worktrees as "fresh" — so from a checkout mtime
is not freshness evidence. A live-estate caller whose files are only written by their
producer opts in.

Usage
-----
  python3 scripts/build_output_health.py                 # the whole view as JSON
  python3 scripts/build_output_health.py --summary        # counts + top reason codes
  python3 scripts/build_output_health.py --now 2026-08-14T00:00:00+00:00 --root <path>
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import yaml  # noqa: E402

from engine.output_health import resolve_output_health  # noqa: E402
from scripts.build_intelligence_registry import (  # noqa: E402
    _READ_CACHE,
    _tracked_file_exists,
    build as build_registry,
    read_tracked,
)

SYNAPSE_REL = Path("config") / "synapse.yml"
NW_HEALTH_REL = Path("data") / "neuralweb" / "health.json"
FORESIGHT_CASCADE_REL = Path("site") / "basketdata" / "foresight_cascade.json"
PROVIDER_HEALTH_REL = Path("data") / "ai_costs" / "provider_health.jsonl"
R2_AUDIT_REL = Path("data") / "quality" / "r2_audit.json"
STALENESS_REL = Path("site") / "live" / "staleness.json"

#: Bytes above which an artifact's content is NOT read for its watermark. A watermark
#: lives in a header or a last line; nothing here justifies pulling a multi-megabyte store
#: into memory, and the cap is disclosed as a parse error rather than as a clean read.
CONTENT_READ_CAP = 8 * 1024 * 1024

#: Neural Web lobe status -> the resolver's normalized semantic vocabulary (§9).
#: ``stale`` maps to ``ok`` DELIBERATELY: NW's staleness verdict is weekend-aware and runs
#: its own as_of fallback ladder, and T4's own watermark read is the freshness authority.
#: Importing NW's verdict would import its calendar rule with it.
NW_STATUS_MAP = {
    "fresh": "ok",
    "fresh_partial": "degraded",
    "degraded": "degraded",
    "stale": "ok",
    "missing": "missing",
    "not_locally_verifiable": "unknown",
    "unknown": "unknown",
}


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------

def _git_answers(root: Path) -> bool:
    """True when ``git`` can resolve HEAD at *root*.

    The whole absence/blindness split hangs on this one question: a both-ways miss means
    the artifact is gone only if the second way was actually consulted.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--verify", "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def _load_yaml(root: Path, rel: Path) -> tuple[dict | None, str]:
    text, source = read_tracked(root, rel)
    if text is None:
        return None, source
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError:
        return None, "unparseable"
    return (data, source) if isinstance(data, dict) else (None, "unparseable")


def _load_json(root: Path, rel: Path) -> tuple[Any, str]:
    text, source = read_tracked(root, rel)
    if text is None:
        return None, source
    try:
        return json.loads(text), source
    except (json.JSONDecodeError, ValueError):
        return None, "unparseable"


def _content_text(root: Path, rel: str) -> tuple[str | None, str | None]:
    """Artifact content through the same ladder, size-capped. Returns (text, parse_error).

    The read_tracked cache is dropped for artifact content: it exists so ONE build is a
    function of one snapshot of its CONFIG inputs, and holding several hundred artifact
    bodies for the life of the process is not what it is for.
    """
    path = Path(rel)
    try:
        on_disk = root / path
        if on_disk.is_file() and on_disk.stat().st_size > CONTENT_READ_CAP:
            size = on_disk.stat().st_size
            return None, f"content is {size} bytes (cap {CONTENT_READ_CAP}) — not read"
    except OSError:
        pass
    text, _ = read_tracked(root, path)
    _READ_CACHE.pop((str(root), path.as_posix()), None)
    if text is None:
        return None, None
    if len(text) > CONTENT_READ_CAP:
        return None, f"content is {len(text)} chars (cap {CONTENT_READ_CAP}) — not read"
    return text, None


# ---------------------------------------------------------------------------
# Observation per artifact
# ---------------------------------------------------------------------------

def _governing_field(entry: dict) -> str | None:
    for key in ("staleness_from", "asof_field"):
        value = entry.get(key)
        if isinstance(value, str) and value.strip() and value.strip() != "null":
            return value.strip()
    return None


def _watermark_from_json(payload: Any, field: str) -> tuple[bool, Any]:
    """(field_present, raw_value) for a top-level key, else ``meta.<field>`` one level."""
    if isinstance(payload, dict):
        if field in payload:
            return True, payload[field]
        meta = payload.get("meta")
        if isinstance(meta, dict) and field in meta:
            return True, meta[field]
    return False, None


def _read_watermark(root: Path, entry: dict, field: str) -> dict[str, Any]:
    """Read ONLY the declared field. Never falls back to another timestamp key."""
    fmt = str(entry.get("format") or "").lower()
    rel = str(entry.get("path") or "")
    out: dict[str, Any] = {
        "content_asof_raw": None,
        "asof_field_present": None,
        "watermark_field_used": field,
        "parse_error": None,
    }
    if fmt == "parquet":
        # The envelope sidecar or nothing — pyarrow is deliberately kept off this path.
        sidecar, err = _content_text(root, rel + ".envelope.json")
        if sidecar is None:
            out["parse_error"] = err or "watermark_unreadable_format"
            return out
        try:
            payload = json.loads(sidecar)
        except (json.JSONDecodeError, ValueError) as exc:
            out["parse_error"] = f"envelope sidecar does not parse ({type(exc).__name__})"
            return out
        present, raw = _watermark_from_json(payload, field)
        out["asof_field_present"] = present
        out["content_asof_raw"] = raw if isinstance(raw, str) else None
        return out
    if fmt not in ("json", "jsonl"):
        out["parse_error"] = "watermark_unreadable_format"
        return out

    text, err = _content_text(root, rel)
    if text is None:
        out["parse_error"] = err
        return out
    if fmt == "jsonl":
        lines = [line for line in text.splitlines() if line.strip()]
        if not lines:
            out["parse_error"] = "jsonl store has no rows"
            return out
        try:
            payload = json.loads(lines[-1])
        except (json.JSONDecodeError, ValueError) as exc:
            out["parse_error"] = f"last jsonl row does not parse ({type(exc).__name__})"
            return out
    else:
        try:
            payload = json.loads(text)
        except (json.JSONDecodeError, ValueError) as exc:
            out["parse_error"] = f"content does not parse ({type(exc).__name__})"
            return out
    present, raw = _watermark_from_json(payload, field)
    out["asof_field_present"] = present
    out["content_asof_raw"] = raw if isinstance(raw, str) else None
    return out


def observe(
    root: Path, entry: dict, *, trust_mtime: bool, git_ok: bool
) -> dict[str, Any]:
    """One storage-aware observation of one artifact. No verdicts — evidence only."""
    rel = str(entry.get("path") or "")
    storage = str(entry.get("storage") or "")
    obs: dict[str, Any] = {
        "exists": None,
        "presence_source": None,
        "content_asof_raw": None,
        "asof_field_present": None,
        "watermark_field_used": None,
        "mtime_utc": None,
        "mtime_trusted": trust_mtime,
        "parse_error": None,
        "sparse_unmaterialized": False,
    }
    if not rel:
        return obs

    on_disk = root / rel
    if on_disk.is_file():
        obs["exists"] = True
        obs["presence_source"] = "filesystem"
        try:
            obs["mtime_utc"] = datetime.fromtimestamp(
                on_disk.stat().st_mtime, tz=timezone.utc
            )
        except OSError:
            pass
    elif storage == "gitignored-local":
        # Written at runtime and never committed: from a checkout its absence says
        # nothing about the live estate, so it stays unobserved rather than missing.
        return obs
    elif storage == "r2":
        return obs
    elif _tracked_file_exists(root, rel):
        obs["exists"] = True
        obs["presence_source"] = "git_head"
    elif git_ok:
        obs["exists"] = False
        obs["presence_source"] = "git_head"
    else:
        obs["sparse_unmaterialized"] = True
        return obs

    field = _governing_field(entry)
    if field and obs["exists"]:
        obs.update(_read_watermark(root, entry, field))
    return obs


# ---------------------------------------------------------------------------
# Semantic self-health adapters (§9) — normalize, never import a rollup
# ---------------------------------------------------------------------------

def _artifact_by_path(synapse: dict) -> dict[str, str]:
    return {
        str(entry.get("path") or ""): aid
        for aid, entry in (synapse.get("artifacts") or {}).items()
        if isinstance(entry, dict) and entry.get("path")
    }


def neural_web_self_health(root: Path, synapse: dict) -> dict[str, dict[str, Any]]:
    """Per-lobe NW statuses, normalized. ``overall_status`` is NOT imported."""
    payload, _ = _load_json(root, NW_HEALTH_REL)
    if not isinstance(payload, dict):
        return {}
    by_path = _artifact_by_path(synapse)
    source_artifact = by_path.get(NW_HEALTH_REL.as_posix())
    out: dict[str, dict[str, Any]] = {}
    for lobe in payload.get("lobes") or []:
        if not isinstance(lobe, dict):
            continue
        aid = str(lobe.get("id") or "")
        status = NW_STATUS_MAP.get(str(lobe.get("status") or ""), "unknown")
        if not aid:
            continue
        row: dict[str, Any] = {
            "source": f"neuralweb_health:{NW_HEALTH_REL.as_posix()}",
            "status": status,
            "detail": f"lobe status {lobe.get('status')!r}",
        }
        if source_artifact:
            # Lets the resolver refuse this evidence wherever the monitor would be
            # grading its own producer's output — mechanically, with no hand list.
            row["source_artifact"] = source_artifact
        out[aid] = row
    return out


def foresight_self_health(root: Path, synapse: dict) -> dict[str, dict[str, Any]]:
    """Per-leg foresight completeness for the cascade artifact itself.

    A DARK sub-leg is reduced completeness, not a missing output: the cascade file exists
    and the presence axis owns absence.
    """
    payload, _ = _load_json(root, FORESIGHT_CASCADE_REL)
    if not isinstance(payload, dict):
        return {}
    health = payload.get("health")
    if not isinstance(health, dict):
        return {}
    aid = _artifact_by_path(synapse).get(FORESIGHT_CASCADE_REL.as_posix())
    if not aid:
        return {}
    legs = health.get("legs") if isinstance(health.get("legs"), dict) else {}
    reduced = sorted(
        name
        for name, leg in legs.items()
        if isinstance(leg, dict) and str(leg.get("status")) in ("PARTIAL", "DARK")
    )
    confirmer_only = str(health.get("mode") or "") == "CONFIRMER-ONLY"
    if not legs:
        status, detail = "unknown", "cascade carries no leg statuses"
    elif reduced or confirmer_only:
        status = "degraded"
        detail = "reduced legs: " + (", ".join(reduced) or "none")
        if confirmer_only:
            detail += "; mode CONFIRMER-ONLY"
    else:
        status, detail = "ok", "every leg LIVE"
    return {
        aid: {
            "source": f"foresight_health:{FORESIGHT_CASCADE_REL.as_posix()}",
            "status": status,
            "detail": detail,
        }
    }


def provider_events(root: Path, synapse: dict) -> dict[str, list[dict[str, Any]]]:
    """Failed provider rungs, joined to artifacts by producer name. DIAGNOSTIC ONLY.

    Filesystem only — the store is gitignored, so from a checkout its absence is normal
    and means nothing. A failed rung with a successful fallback never degrades an output;
    the resolver enforces that, and this function only supplies the rows.
    """
    path = root / PROVIDER_HEALTH_REL
    if not path.is_file():
        return {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {}
    rows: list[dict[str, Any]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(row, dict) and row.get("event") == "attempt" and not row.get("ok"):
            rows.append(row)
    if not rows:
        return {}
    out: dict[str, list[dict[str, Any]]] = {}
    for aid, entry in (synapse.get("artifacts") or {}).items():
        if not isinstance(entry, dict):
            continue
        stem = Path(str(entry.get("producer") or "").split(":")[0]).stem
        if not stem:
            continue
        hits = [
            row
            for row in rows
            if stem in (str(row.get("lane") or ""), str(row.get("context") or ""))
        ]
        if hits:
            out[str(aid)] = hits
    return out


# ---------------------------------------------------------------------------
# Reader plane (§8)
# ---------------------------------------------------------------------------

_SENTINEL_STATUS_MAP = {"ok": "fresh", "stale": "stale", "indeterminate": "indeterminate"}


def sentinel_readers(payload: Any, synapse: dict) -> dict[str, list[dict[str, Any]]]:
    """Freshness-sentinel surfaces joined to artifacts by the surface's own path.

    The surface table is IMPORTED from ``scripts.freshness_sentinel`` rather than copied —
    a second copy of the path list is a second thing to rot. Most artifacts have no
    sentinel surface at all; that is a census fact, not an error.
    """
    if not isinstance(payload, dict):
        return {}
    surfaces = payload.get("surfaces")
    if not isinstance(surfaces, dict):
        return {}
    try:
        from scripts.freshness_sentinel import SURFACES
    except Exception:  # noqa: BLE001 — the sentinel is a VPS script; absence is not fatal
        return {}
    by_path = _artifact_by_path(synapse)
    out: dict[str, list[dict[str, Any]]] = {}
    for surface in SURFACES:
        record = surfaces.get(surface.get("id"))
        if not isinstance(record, dict):
            continue
        rel = str(surface.get("path") or "").lstrip("/")
        aid = by_path.get(f"site/{rel}") if surface.get("kind") != "r2" else None
        if not aid:
            continue
        verdict = _SENTINEL_STATUS_MAP.get(str(record.get("status") or ""))
        if verdict is None:
            continue
        # CLOCK KIND BY WHAT WAS ACTUALLY MEASURED: the store's own asof and the board's
        # self-reported delay are content clocks; a bake stamp is transport.
        content = record.get("asof") is not None or bool(record.get("board_delayed"))
        row: dict[str, Any] = {
            "source": f"freshness_sentinel:{surface.get('id')}",
            "verdict": verdict,
            "clock_kind": "content" if content else "transport",
        }
        if record.get("asof"):
            row["observed_asof"] = str(record["asof"])
        if record.get("detail"):
            row["detail"] = str(record["detail"])
        out.setdefault(aid, []).append(row)
    return out


def _r2_anchor_verdicts(doc: dict) -> dict[str, tuple[str, str]]:
    """anchor -> (verdict, clock_kind), read off the audit's own fail/warn reasons."""
    verdicts: dict[str, tuple[str, str]] = {}
    for name in doc.get("anchors") or {}:
        anchor = str(name).split("/")[0]
        verdicts.setdefault(anchor, ("fresh", "transport"))
    for reason in doc.get("fail_reasons") or []:
        text = str(reason)
        head, _, rest = text.partition(":")
        subject = rest.strip().split()[0] if rest.strip() else ""
        anchor = subject.split("/")[0]
        if not anchor:
            continue
        if head.startswith("R2 CONTENT"):
            verdicts[anchor] = (
                ("stale", "content") if "STALE" in head else ("missing", "content")
            )
        elif head == "R2 DARK":
            verdicts[anchor] = ("missing", "transport")
        else:
            verdicts[anchor] = ("stale", "transport")
    for warning in doc.get("warnings") or []:
        text = str(warning)
        head, _, rest = text.partition(":")
        subject = rest.strip().split()[0] if rest.strip() else ""
        anchor = subject.split("/")[0]
        if anchor and verdicts.get(anchor, ("fresh", ""))[0] == "fresh":
            verdicts[anchor] = ("indeterminate", "transport")
    return verdicts


def r2_readers(doc: Any, synapse: dict) -> dict[str, list[dict[str, Any]]]:
    """R2 audit anchors joined to artifacts whose R2 key sits under the anchor prefix."""
    if not isinstance(doc, dict):
        return {}
    verdicts = _r2_anchor_verdicts(doc)
    out: dict[str, list[dict[str, Any]]] = {}
    for aid, entry in (synapse.get("artifacts") or {}).items():
        if not isinstance(entry, dict) or entry.get("storage") not in ("r2", "git+r2"):
            continue
        anchor = str(entry.get("path") or "").split("/")[0]
        hit = verdicts.get(anchor)
        if not hit:
            continue
        verdict, clock = hit
        out.setdefault(str(aid), []).append(
            {
                "source": f"r2_audit:{anchor}",
                "verdict": verdict,
                "clock_kind": clock,
                "detail": f"anchor {anchor} per data/quality/r2_audit.json",
            }
        )
    return out


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

def build(
    root: Path,
    *,
    now: datetime,
    trust_mtime: bool = False,
    staleness_json: Path | None = None,
    r2_audit: Path | None = None,
    limit_artifacts: list[str] | None = None,
) -> dict[str, Any]:
    """Gather evidence and resolve. Reads only; writes nothing."""
    synapse, synapse_source = _load_yaml(root, SYNAPSE_REL)
    if synapse is None:
        raise SystemExit(
            f"FATAL: {SYNAPSE_REL} is unreadable or unparseable ({synapse_source}) — "
            f"there is no artifact census to grade."
        )
    registry, _ = build_registry(root)

    artifacts = {
        aid: entry
        for aid, entry in (synapse.get("artifacts") or {}).items()
        if isinstance(entry, dict)
    }
    wanted = set(limit_artifacts) if limit_artifacts else None
    git_ok = _git_answers(root)
    observations = {
        aid: observe(root, entry, trust_mtime=trust_mtime, git_ok=git_ok)
        for aid, entry in sorted(artifacts.items())
        if wanted is None or aid in wanted
    }

    self_health = neural_web_self_health(root, synapse)
    self_health.update(foresight_self_health(root, synapse))

    staleness_payload: Any = None
    if staleness_json is not None and staleness_json.is_file():
        try:
            staleness_payload = json.loads(staleness_json.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, ValueError):
            staleness_payload = None
    audit_doc: Any
    if r2_audit is not None:
        audit_doc = None
        if r2_audit.is_file():
            try:
                audit_doc = json.loads(r2_audit.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError, ValueError):
                audit_doc = None
    else:
        audit_doc, _ = _load_json(root, R2_AUDIT_REL)

    readers = sentinel_readers(staleness_payload, synapse)
    for aid, rows in r2_readers(audit_doc, synapse).items():
        readers.setdefault(aid, []).extend(rows)

    return resolve_output_health(
        synapse=synapse,
        registry=registry,
        observations=observations,
        reader_observations=readers,
        self_health=self_health,
        provider_events=provider_events(root, synapse),
        now=now,
    )


def render_summary(view: dict[str, Any]) -> str:
    summary = view["summary"]
    lines = [
        f"output health ({view['schema']}) — {summary['n_outputs']} artifacts, "
        f"observed_at {view['generated']['observed_at']} "
        f"(root_mode {view['generated']['root_mode']})",
        f"  state:      {summary['by_state']}",
        f"  assessment: {summary['by_assessment_status']}",
        f"  decided_by: {summary['by_decided_by']}",
        f"  bound:      {summary['by_dependency_bound']}",
        "  top reason codes:",
    ]
    top = sorted(summary["reason_codes"].items(), key=lambda kv: (-kv[1], kv[0]))[:12]
    lines += [f"    {count:>5}  {code}" for code, count in top]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--json", action="store_true", help="the whole view as JSON (default)")
    parser.add_argument("--summary", action="store_true", help="counts + top reason codes")
    parser.add_argument(
        "--now",
        default=None,
        help="ISO instant to resolve against (offset-bearing); default now(UTC)",
    )
    parser.add_argument(
        "--trust-mtime",
        action="store_true",
        help="treat file mtimes as write-time evidence (live estate only)",
    )
    parser.add_argument("--staleness-json", type=Path, default=None)
    parser.add_argument("--r2-audit", type=Path, default=None)
    parser.add_argument(
        "--limit-artifacts",
        default=None,
        help="comma-separated artifact ids to OBSERVE (debug; the rest stay unobserved)",
    )
    args = parser.parse_args(argv)

    now = (
        datetime.fromisoformat(args.now)
        if args.now
        else datetime.now(timezone.utc)
    )
    staleness = args.staleness_json
    if staleness is None:
        candidate = args.root / STALENESS_REL
        staleness = candidate if candidate.is_file() else None

    view = build(
        args.root,
        now=now,
        trust_mtime=args.trust_mtime,
        staleness_json=staleness,
        r2_audit=args.r2_audit,
        limit_artifacts=(
            [a.strip() for a in args.limit_artifacts.split(",") if a.strip()]
            if args.limit_artifacts
            else None
        ),
    )
    if args.summary:
        print(render_summary(view), flush=True)
        return 0
    print(json.dumps(view, indent=1, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
