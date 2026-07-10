"""engine.metabolism.provenance — Freshness stamping for context blocks (R-V3-1).

stamp_context()          — annotate a list of context blocks with age / staleness
render_freshness_header() — compact markdown summary for the loop

All functions are NEVER-RAISE and return safe fallbacks on any error.
No LLM calls, no network, no reads from ~/. Deterministic.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# Hardcoded SLA defaults (used when config/metabolism_context_sla.yml is missing)
_HARDCODED_SLA: dict[str, int] = {
    "organism_state": 2,
    "fitness": 3,
    "trajectory": 7,
    "lessons": 30,
    "case_law": 120,
    "charter": 365,
}
_DEFAULT_SLA_DAYS = 14


def _repo_root(root: Path | None = None) -> Path:
    if root is not None:
        return Path(root)
    return Path(__file__).resolve().parent.parent.parent


def _load_sla(root: Path | None = None) -> tuple[dict[str, int], int]:
    """Return (per_source_sla_dict, default_sla_days).

    Reads config/metabolism_context_sla.yml.  Falls back to hardcoded
    defaults on any error without raising.
    """
    try:
        import yaml  # noqa: PLC0415
        p = _repo_root(root) / "config" / "metabolism_context_sla.yml"
        if not p.exists():
            return _HARDCODED_SLA.copy(), _DEFAULT_SLA_DAYS
        raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        sources = raw.get("sources") or {}
        per_source: dict[str, int] = {}
        for key, val in sources.items():
            if isinstance(val, dict):
                sla = val.get("sla_days")
            elif isinstance(val, (int, float)):
                sla = int(val)
            else:
                sla = None
            if isinstance(sla, (int, float)):
                per_source[str(key)] = int(sla)
        default = int(raw.get("default_sla_days", _DEFAULT_SLA_DAYS))
        return per_source, default
    except Exception as exc:  # noqa: BLE001
        log.warning("provenance._load_sla: %s — using hardcoded defaults", exc)
        return _HARDCODED_SLA.copy(), _DEFAULT_SLA_DAYS


def _parse_iso(iso: str) -> datetime | None:
    """Parse an ISO 8601 string to a timezone-aware UTC datetime.  Returns None on failure."""
    try:
        # Python 3.11+ handles Z natively; for older versions strip Z and add +00:00
        iso = iso.strip()
        if iso.endswith("Z"):
            iso = iso[:-1] + "+00:00"
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:  # noqa: BLE001
        return None


def stamp_context(
    blocks: list[dict[str, Any]],
    *,
    now_iso: str | None = None,
    root: Path | None = None,
) -> list[dict[str, Any]]:
    """Return a new list of blocks each augmented with freshness metadata.

    Input block schema:
        {
            "name": str,
            "source": str,        # repo-relative path OR logical source key
            "text": str,
            "as_of": str | None,  # optional ISO timestamp
        }

    Added keys on each output block:
        age_days         float | None
        is_stale         bool
        sla_days         int
        staleness_reason str

    Freshness resolution order:
      (a) explicit as_of on the block
      (b) mtime of source path if it exists under repo root
      (c) unknown → age_days=None, is_stale=False, staleness_reason="unknown-age"

    NEVER-RAISE: returns a copy of the input blocks (un-stamped) on any
    top-level error.
    """
    try:
        per_source, default_sla = _load_sla(root)
        repo = _repo_root(root)

        if now_iso is not None:
            now_dt = _parse_iso(now_iso)
            if now_dt is None:
                log.warning("provenance.stamp_context: bad now_iso %r, falling back to utcnow", now_iso)
                now_dt = datetime.now(timezone.utc)
        else:
            now_dt = datetime.now(timezone.utc)

        stamped: list[dict[str, Any]] = []
        for block in blocks:
            try:
                out = dict(block)  # shallow copy so original is untouched
                name = str(out.get("name") or "")
                source = str(out.get("source") or "")
                as_of = out.get("as_of")

                # Determine SLA
                sla = per_source.get(source, per_source.get(name, default_sla))

                age_days: float | None = None
                staleness_reason = "unknown-age"

                # (a) explicit as_of
                if as_of:
                    as_of_dt = _parse_iso(str(as_of))
                    if as_of_dt is not None:
                        delta = now_dt - as_of_dt
                        age_days = delta.total_seconds() / 86400.0
                        staleness_reason = "as_of"

                # (b) mtime of source path
                if age_days is None and source:
                    candidate = repo / source
                    try:
                        if candidate.exists():
                            mtime = candidate.stat().st_mtime
                            mtime_dt = datetime.fromtimestamp(mtime, tz=timezone.utc)
                            delta = now_dt - mtime_dt
                            age_days = delta.total_seconds() / 86400.0
                            staleness_reason = "file-mtime"
                    except Exception:  # noqa: BLE001
                        pass

                # (c) unknown
                if age_days is None:
                    out["age_days"] = None
                    out["is_stale"] = False
                    out["sla_days"] = sla
                    out["staleness_reason"] = "unknown-age"
                else:
                    is_stale = age_days > sla
                    out["age_days"] = age_days
                    out["is_stale"] = is_stale
                    out["sla_days"] = sla
                    out["staleness_reason"] = staleness_reason

                stamped.append(out)

            except Exception as exc:  # noqa: BLE001
                log.warning("provenance.stamp_context: block error %s", exc)
                stamped.append(dict(block))  # pass through un-stamped

        return stamped

    except Exception as exc:  # noqa: BLE001
        log.warning("provenance.stamp_context: top-level error %s", exc)
        return list(blocks)


def render_freshness_header(stamped: list[dict[str, Any]]) -> str:
    """Return a compact markdown block titled '### Context freshness'.

    Stale blocks are prefixed with '⚠ STALE'.
    NEVER-RAISE.
    """
    try:
        lines: list[str] = ["### Context freshness"]
        for block in stamped:
            try:
                name = str(block.get("name") or "(unnamed)")
                age_days = block.get("age_days")
                sla_days = block.get("sla_days", _DEFAULT_SLA_DAYS)
                is_stale = bool(block.get("is_stale", False))
                staleness_reason = str(block.get("staleness_reason") or "unknown-age")

                if age_days is None:
                    age_str = "age unknown"
                else:
                    age_str = f"{age_days:.1f}d old (SLA {sla_days}d)"

                prefix = "⚠ STALE" if is_stale else "  ok   "
                lines.append(f"- {prefix} | {name} | {age_str} [{staleness_reason}]")

            except Exception as exc:  # noqa: BLE001
                log.warning("provenance.render_freshness_header: block error %s", exc)
                lines.append(f"- (error rendering block: {exc})")

        return "\n".join(lines)

    except Exception as exc:  # noqa: BLE001
        log.warning("provenance.render_freshness_header: %s", exc)
        return "### Context freshness\n(error generating header)"
