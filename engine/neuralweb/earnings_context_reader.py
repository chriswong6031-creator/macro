"""Fail-closed private-store reader for exact, receipt-bound earnings context.

Production reads the same private Research Vault generation served by the paid
Earnings API.  A deliberate off-repository local context directory remains for
tests and operator replay; no default ever points into public ``site/`` bytes.
"""
from __future__ import annotations

from datetime import date, datetime, time, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import threading
from typing import Any, Mapping

from engine.earnings_narrative.context_packets import (
    canonical_json_bytes,
    validate_context_manifest,
    validate_context_packet_at_cutoff,
)
from engine.earnings_narrative.private_publication import (
    load_private_context_packet,
    load_private_manifest,
)


_ROOT = Path(__file__).resolve().parents[2]
_TICKER = re.compile(r"^[A-Z0-9.\-]{1,16}$")
_MAX_MANIFEST_BYTES = 8 * 1024 * 1024
_MAX_PACKET_BYTES = 512 * 1024
_STORE_LOCK = threading.Lock()
_STORE: Any | None = None
_STORE_READY = False


class EarningsEvidenceReadError(RuntimeError):
    """The local publication is absent, malformed, or receipt-inconsistent."""


def _context_dir(root: Path | None = None) -> Path | None:
    """Resolve an explicit off-repo replay directory, never a site/ default."""
    override = os.environ.get("EARNINGS_EVIDENCE_CONTEXT_DIR", "").strip()
    if not override and root is None:
        return None
    candidate = Path(override or root).expanduser().resolve()
    repository = _ROOT.resolve()
    # Brain/Cortex pass their repository root. Neither that runtime context nor
    # a misconfigured environment override authorizes reading formerly public
    # static bytes back into the intelligence plane.
    if candidate == repository or repository in candidate.parents:
        return None
    if override:
        return candidate
    return candidate if candidate.name == "context" else candidate / "context"


def _build_private_store():
    global _STORE, _STORE_READY
    with _STORE_LOCK:
        if _STORE_READY:
            return _STORE
        from engine.research_vault.r2_store import build_store  # noqa: PLC0415

        _STORE = build_store()
        _STORE_READY = True
        return _STORE


def _reset_store_cache() -> None:
    global _STORE, _STORE_READY
    with _STORE_LOCK:
        _STORE = None
        _STORE_READY = False


def _read_json(path: Path, *, limit: int, name: str) -> tuple[dict[str, Any], bytes]:
    try:
        size = path.stat().st_size
        if size <= 0 or size > limit:
            raise EarningsEvidenceReadError(f"{name} exceeds its safe size bound")
        body = path.read_bytes()
        payload = json.loads(body.decode("utf-8"), parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    except EarningsEvidenceReadError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise EarningsEvidenceReadError(f"{name} is unavailable or invalid") from exc
    if not isinstance(payload, dict) or body != canonical_json_bytes(payload):
        raise EarningsEvidenceReadError(f"{name} is not canonical JSON")
    return payload, body


def _as_of_cutoff(value: object) -> datetime | None:
    """Parse a trusted PIT cutoff; a date means the end of that UTC day."""
    if value is None or value == "":
        return None
    raw = str(value).strip()
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
            return datetime.combine(date.fromisoformat(raw), time.max, tzinfo=timezone.utc)
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise EarningsEvidenceReadError("earnings evidence as_of cutoff is invalid") from exc
    if parsed.tzinfo is None:
        raise EarningsEvidenceReadError("earnings evidence as_of timestamp needs a timezone")
    return parsed.astimezone(timezone.utc)


def read_earnings_evidence(params: Mapping[str, Any], *, root: Path | None = None) -> dict[str, Any]:
    """Return one ticker's exact evidence packet, or a bounded unavailable result."""
    raw = str(params.get("ticker") or "").strip().upper()
    unavailable = {
        "available": False, "ticker": raw[:16], "is_context_only": True,
        "authority": "context_only", "note": "exact earnings evidence unavailable",
    }
    if not _TICKER.fullmatch(raw):
        return {**unavailable, "note": "invalid ticker"}
    try:
        cutoff = _as_of_cutoff(params.get("as_of", params.get("asof")))
        directory = _context_dir(root)
        if directory is not None:
            manifest, _manifest_body = _read_json(
                directory / "latest.json",
                limit=_MAX_MANIFEST_BYTES,
                name="earnings context manifest",
            )
            validate_context_manifest(manifest)
            receipt = manifest["objects"].get(raw)
            if not isinstance(receipt, Mapping):
                return {
                    **unavailable,
                    "note": "ticker is not covered by the exact-evidence context generation",
                }
            object_path = str(receipt["path"])
            if not re.fullmatch(r"[a-z0-9.\-]{1,32}\.json", object_path):
                raise EarningsEvidenceReadError("earnings context object path is unsafe")
            packet, body = _read_json(
                directory / object_path,
                limit=_MAX_PACKET_BYTES,
                name="earnings context packet",
            )
            if len(body) != int(receipt["bytes"]) or sha256(body).hexdigest() != receipt["sha256"]:
                raise EarningsEvidenceReadError("earnings context object receipt mismatch")
            validate_context_packet_at_cutoff(
                packet,
                knowledge_cutoff=manifest["knowledge_cutoff"],
            )
            if packet["context_id"] != receipt["context_id"] or packet["event"]["ticker"] != raw:
                raise EarningsEvidenceReadError("earnings context identity mismatch")
        else:
            store = _build_private_store()
            if store is None:
                raise EarningsEvidenceReadError("private earnings evidence store is unavailable")
            private_manifest = load_private_manifest(store)
            private_objects = private_manifest.get("context", {}).get("objects", {})
            if not isinstance(private_objects, Mapping) or raw not in private_objects:
                return {
                    **unavailable,
                    "note": "ticker is not covered by the exact-evidence context generation",
                }
            packet, manifest, private_receipt = load_private_context_packet(
                store,
                raw,
                manifest=private_manifest,
            )
            receipt = manifest["objects"].get(raw)
            if not isinstance(receipt, Mapping):
                return {
                    **unavailable,
                    "note": "ticker is not covered by the exact-evidence context generation",
                }
            if (
                private_receipt.get("sha256") != receipt.get("sha256")
                or private_receipt.get("bytes") != receipt.get("bytes")
            ):
                raise EarningsEvidenceReadError("private context catalogs disagree")
        known_at = datetime.fromisoformat(
            str(packet["source"]["known_at"]).replace("Z", "+00:00")
        )
        if known_at.tzinfo is None:
            known_at = known_at.replace(tzinfo=timezone.utc)
        known_at = known_at.astimezone(timezone.utc)
        event_date = date.fromisoformat(str(packet["event"]["date"]))
        if cutoff is not None and (known_at > cutoff or event_date > cutoff.date()):
            return {
                **unavailable,
                "note": "no point-in-time earnings evidence was known by the requested as_of cutoff",
            }
        return {
            "available": True,
            "ticker": raw,
            "is_context_only": True,
            "authority": "context_only",
            "generation_id": manifest["generation_id"],
            "knowledge_cutoff": manifest["knowledge_cutoff"],
            "event": packet["event"],
            "categories": packet["categories"],
            "facts": packet["facts"],
            "source_completeness": packet["source_completeness"],
            "links": packet["links"],
            "receipts": {
                "context_id": packet["context_id"],
                "source_sha256": packet["source"]["source_sha256"],
                "known_at": packet["source"]["known_at"],
                "correction_status": packet["source"]["correction_status"],
                "object_sha256": receipt["sha256"],
            },
            "permissions": packet["authority"],
            "note": "exact transcript evidence; may explain or de-escalate, never originate or alter a signal",
        }
    except Exception as exc:  # noqa: BLE001 - customer tool fails closed, never raises into chat.
        return {**unavailable, "note": f"integrity failure: {exc}"}
