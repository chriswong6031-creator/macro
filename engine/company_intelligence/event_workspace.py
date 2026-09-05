"""``event_workspace.v1`` — compact earnings payload + sibling publication.

E1 publishes this object under ``company_intelligence/event_workspaces/`` with
the same marker-last immutable-generation discipline as ``write_generation``.
It does not mutate the closed v1 teaser maps.

Authority is ``context_only``.  Nothing here ranks, sizes, gates, or feeds
Prophet.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from hashlib import sha256
from pathlib import Path
import re
import tempfile
from typing import Any, Mapping, Sequence, Union

from .contracts import (
    ContractError,
    canonical_json_bytes,
    iso_timestamp,
    safe_ticker,
)
from .documents import (
    TypedAbsence,
    text_span,
)
from .event_id_adapter import EventAliasIndex, aliases_for
from .events import AUTHORITY, CompanyEvent, FiscalPeriod
from .identity import IssuerIdentity, IssuerRegistry, ListingAlias, company_id_for_cik


WORKSPACE_SCHEMA = "event_workspace.v1"
# IMCE A5C (Sol A5C directive, 2026-08-23, item A): the manifest chain.
# v1 stays readable forever as the chain ROOT/backward-compatible generation
# (A2) -- nothing ever rewrites or deletes a v1 object.  Every generation
# minted BY THIS MODULE going forward (write_workspace_generation) is v2:
# v1's exact closed key set PLUS previous_generation_id/previous_manifest_
# sha256, so a source revision's bytes are never stranded with no
# discoverable predecessor pointer once a newer generation supersedes it.
MANIFEST_SCHEMA_V1 = "event_workspace_manifest.v1"
MANIFEST_SCHEMA_V2 = "event_workspace_manifest.v2"
# Legacy alias -- historically "the" manifest schema constant.  Nothing
# outside this module keys off its current value (grep-verified); kept
# pointing at v1 so a caller that only ever compared against the OLD
# published schema string keeps comparing against a real, still-valid value.
MANIFEST_SCHEMA = MANIFEST_SCHEMA_V1
PROCESSOR_VERSION = "event_workspace/1.0.0"
NEST = "event_workspaces"
AUTHORITY = AUTHORITY

PROPHET_FLAGS = {
    "may_rank": False,
    "may_size": False,
    "may_gate": False,
    "prophet_authority": False,
}

WORKSPACE_KEYS = (
    "schema",
    "event_id",
    "aliases",
    "issuer",
    "fiscal_period",
    "lifecycle",
    "completeness",
    "facts",
    "deltas",
    "guidance",
    "claims",
    "sources",
    "warnings",
    "generation_id",
    "generated_at",
    "authority",
    "prophet_flags",
    "claim_citations_pending",
    "qa_exchanges",
)

MANIFEST_KEYS = (
    "schema",
    "generation_id",
    "generated_at",
    "status",
    "event_count",
    "files",
    "aliases",
    "authority",
    "warnings",
)

# v2 = v1's exact key set PLUS the two chain-link keys (A1).  Both are
# REQUIRED in a v2 manifest -- never optional-and-silently-absent (A3).
MANIFEST_KEYS_V2 = MANIFEST_KEYS + ("previous_generation_id", "previous_manifest_sha256")

WORKSPACE_WARNINGS = frozenset({
    "wire_record_not_found",
    "collector_filing_unjoinable",
    "consensus_unlicensed",
    "slides_absent",
    "reaction_not_joined",
    "questions_count_unstructured",
})

_GENERATION_RE = re.compile(r"^[0-9a-f]{24,64}$")
_EVENT_ID_RE = re.compile(r"^evt_cik\d{10}_\d{4}(?:q[1-4]|fy)_[a-z0-9]+$")

# Flagship AAPL FY2026 Q3 — real issuer/SEC identity.  Not a synthetic CIK.
AAPL_CIK = "0000320193"
AAPL_ACCESSION = "0000320193-26-000018"
AAPL_CALL_DATE = date(2026, 7, 30)
AAPL_PERIOD_END = date(2026, 6, 27)
FLAGSHIP_EVENT_ID = "evt_cik0000320193_2026q3_results"
LIVE_CIE_ALIAS = "cie_98e318c37ec1a2a1f83c45e1"
LIVE_NARRATIVE_ALIAS = "AAPL/2026Q3"
LIVE_PUBLIC_SLUG = "aapl-2026q3-call-record"


class WorkspaceError(ContractError):
    """The workspace payload or its publication contract cannot be trusted."""


def _utc(value: object, *, field_name: str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime.combine(value, datetime.min.time(), tzinfo=timezone.utc)
    else:
        text = str(value or "").strip()
        if not text:
            raise WorkspaceError(f"{field_name} is required")
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")


def _require_mapping(value: object, *, name: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise WorkspaceError(f"{name} must be an object")
    return dict(value)


def _require_exact_keys(item: Mapping[str, Any], keys: Sequence[str], *, name: str) -> None:
    if set(item) != set(keys):
        raise WorkspaceError(f"{name} keys mismatch")


def apple_issuer() -> IssuerIdentity:
    """Real EDGAR identity for Apple Inc. as of the FY2026 Q3 print."""
    return IssuerIdentity(
        company_id=company_id_for_cik(AAPL_CIK),
        display_name="Apple Inc.",
        fiscal_year_end_month=9,
        reporting_currency="USD",
        listings=(
            ListingAlias(
                ticker="AAPL",
                mic="XNAS",
                share_class="common",
                trading_currency="USD",
                is_primary=True,
            ),
        ),
        external_ids={"cik": AAPL_CIK},
    )


def apple_registry() -> IssuerRegistry:
    return IssuerRegistry([apple_issuer()])


def production_registry() -> IssuerRegistry:
    """``apple_registry()`` plus the four A5A homebuilders (DHI/PHM/KBH/TOL).

    Identity for DHI/PHM/KBH/TOL lives in ``engine/company_intelligence/
    issuer_profiles.py`` (CIKs sourced from ``data/edgar/ticker_cik_ledger.json``
    at commit time; MIC and fiscal-year-end verified against each issuer's own
    SEC submissions JSON — see that module's docstring for the receipts). The
    import is deferred to the function body: ``issuer_profiles`` imports
    private helpers from this module for its Apple transcript-claims profile,
    so a module-level import here would cycle.
    """
    from .issuer_profiles import dhi_issuer, kbh_issuer, phm_issuer, tol_issuer

    return IssuerRegistry([apple_issuer(), dhi_issuer(), phm_issuer(), kbh_issuer(), tol_issuer()])


def flagship_fiscal_period() -> FiscalPeriod:
    return FiscalPeriod(year=2026, quarter=3, calendar_end=AAPL_PERIOD_END)


def _atomic_write(path: Path, body: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.", delete=False) as handle:
        temporary = Path(handle.name)
        handle.write(body)
    try:
        temporary.replace(path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def _unique_utf8_span(text: str, literal: str) -> tuple[int, int] | None:
    raw = text.encode("utf-8")
    needle = literal.encode("utf-8")
    start = raw.find(needle)
    if start < 0:
        return None
    if raw.find(needle, start + 1) >= 0:
        return None
    return start, start + len(needle)


def _absence(
    *,
    reason: str,
    subject: str,
    detail: str,
    event_id: str,
    document_id: str | None = None,
) -> dict[str, Any]:
    return TypedAbsence(
        reason=reason,
        subject=subject,
        detail=detail,
        event_id=event_id,
        document_id=document_id,
    ).to_payload()


def _span_payload_from_transcript(
    *,
    document_id: str,
    body_sha256: str,
    segment_index: int,
    segment: Mapping[str, Any],
    literal: str,
) -> dict[str, Any] | None:
    text = str(segment.get("text") or "")
    bounds = _unique_utf8_span(text, literal)
    if bounds is None:
        return None
    start, end = bounds
    span = text_span(
        document_id=document_id,
        document_version=1,
        body_sha256=body_sha256,
        segment_index=segment_index,
        segment_text=text,
        start_byte=start,
        end_byte=end,
        text=literal,
        speaker=segment.get("speaker"),
        role=segment.get("role") or None,
        rights_profile="rp_public_primary_v1",
    )
    return span.to_payload()


def _lifecycle_payload(event: CompanyEvent) -> dict[str, Any]:
    return {
        "state": event.state,
        "observed_at": _iso(event.observed_at) if event.observed_at else None,
        "source_available_at": (
            _iso(event.source_available_at) if event.source_available_at else None
        ),
    }


def validate_event_workspace(payload: object) -> None:
    item = _require_mapping(payload, name="event_workspace")
    _require_exact_keys(item, WORKSPACE_KEYS, name="event_workspace")
    if item.get("schema") != WORKSPACE_SCHEMA:
        raise WorkspaceError("event_workspace schema mismatch")
    if not _EVENT_ID_RE.fullmatch(str(item.get("event_id") or "")):
        raise WorkspaceError("event_workspace event_id is not canonical")
    if item.get("authority") != AUTHORITY:
        raise WorkspaceError("event_workspace authority must be context_only")
    flags = _require_mapping(item.get("prophet_flags"), name="prophet_flags")
    if flags != PROPHET_FLAGS:
        raise WorkspaceError("event_workspace prophet flags must all be false")
    if not isinstance(item.get("claim_citations_pending"), bool):
        raise WorkspaceError("claim_citations_pending must be derived bool")
    if iso_timestamp(item.get("generated_at")) is None:
        raise WorkspaceError("generated_at missing")
    if not _GENERATION_RE.fullmatch(str(item.get("generation_id") or "")):
        raise WorkspaceError("invalid generation_id")
    warnings = item.get("warnings")
    if (
        not isinstance(warnings, list)
        or warnings != sorted(set(warnings))
        or any(value not in WORKSPACE_WARNINGS for value in warnings)
    ):
        raise WorkspaceError("event_workspace warnings invalid")
    for name in ("facts", "deltas", "guidance", "claims", "sources", "aliases", "qa_exchanges"):
        if not isinstance(item.get(name), list):
            raise WorkspaceError(f"{name} must be a list")
    transcript_source = next(
        (
            source for source in item.get("sources") or []
            if isinstance(source, Mapping) and source.get("kind") == "transcript"
        ),
        None,
    )
    transcript_document_id = None
    transcript_sha256 = None
    transcript_clock = None
    if isinstance(transcript_source, Mapping) and transcript_source.get("receipt_state") == "byte_replayed":
        transcript_document_id = transcript_source.get("document_id")
        transcript_sha256 = transcript_source.get("source_sha256")
        clock = transcript_source.get("source_clock")
        if clock is not None:
            from .qa_exchange import validate_source_clock
            transcript_clock = validate_source_clock(
                clock,
                document_id=str(transcript_document_id or ""),
                source_sha256=str(transcript_sha256 or ""),
            )
    elif isinstance(transcript_source, Mapping) and transcript_source.get("source_clock") is not None:
        raise WorkspaceError("typed-absence transcript cannot carry a revision clock")
    from .qa_exchange import validate_qa_exchanges
    validate_qa_exchanges(
        item.get("qa_exchanges"),
        event_id=str(item.get("event_id") or ""),
        document_id=str(transcript_document_id) if transcript_document_id else None,
        document_sha256=str(transcript_sha256) if transcript_sha256 else None,
        transcript_clock=transcript_clock,
    )
    for delta in item["deltas"]:
        if not isinstance(delta, Mapping):
            raise WorkspaceError("delta must be an object")
        if delta.get("basis_match") is True:
            raise WorkspaceError("basis_match true is not minted in E1 without a licensed consensus")
        if "beat" in delta or "miss" in delta or "beat_miss" in delta:
            raise WorkspaceError("beat/miss is forbidden unless basis_match is true")


def validate_workspace_manifest(payload: object) -> None:
    item = _require_mapping(payload, name="event_workspace_manifest")
    schema = item.get("schema")
    if schema == MANIFEST_SCHEMA_V2:
        _require_exact_keys(item, MANIFEST_KEYS_V2, name="event_workspace_manifest")
    elif schema == MANIFEST_SCHEMA_V1:
        _require_exact_keys(item, MANIFEST_KEYS, name="event_workspace_manifest")
    else:
        raise WorkspaceError("workspace manifest schema mismatch")
    if not _GENERATION_RE.fullmatch(str(item.get("generation_id") or "")):
        raise WorkspaceError("invalid manifest generation_id")
    if iso_timestamp(item.get("generated_at")) is None:
        raise WorkspaceError("manifest generated_at missing")
    if item.get("authority") != AUTHORITY:
        raise WorkspaceError("workspace manifest authority must be context_only")
    if item.get("status") not in {"ready", "degraded", "partial", "empty"}:
        raise WorkspaceError("invalid workspace manifest status")
    event_count = item.get("event_count")
    if isinstance(event_count, bool) or not isinstance(event_count, int) or event_count < 0:
        raise WorkspaceError("manifest event_count must be a nonnegative integer")
    files = _require_mapping(item.get("files"), name="manifest.files")
    if len(files) != event_count:
        raise WorkspaceError("manifest event_count must match files")
    for name, block in files.items():
        if (
            not isinstance(name, str)
            or not name.startswith("workspaces/")
            or not name.endswith(".json")
            or ".." in name.split("/")
        ):
            raise WorkspaceError("manifest file path is unsafe")
        event_id = name[len("workspaces/"):-len(".json")]
        if not _EVENT_ID_RE.fullmatch(event_id):
            raise WorkspaceError("manifest file is not a canonical event workspace")
        block_map = _require_mapping(block, name=f"manifest file {name}")
        if set(block_map) != {"bytes", "sha256"}:
            raise WorkspaceError("manifest file receipt keys mismatch")
        digest = str(block_map.get("sha256") or "")
        if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
            raise WorkspaceError("manifest file sha256 invalid")
        size = block_map.get("bytes")
        if isinstance(size, bool) or not isinstance(size, int) or size <= 0:
            raise WorkspaceError("manifest file bytes invalid")
    aliases = _require_mapping(item.get("aliases"), name="manifest.aliases")
    for legacy, canonical in aliases.items():
        if not isinstance(legacy, str) or not isinstance(canonical, str):
            raise WorkspaceError("manifest aliases must be strings")
        if not _EVENT_ID_RE.fullmatch(canonical):
            raise WorkspaceError("manifest alias does not resolve to a canonical event")
    warnings = item.get("warnings")
    if not isinstance(warnings, list) or warnings != sorted(set(warnings)):
        raise WorkspaceError("manifest warnings invalid")
    if schema == MANIFEST_SCHEMA_V2:
        previous_id = item.get("previous_generation_id")
        previous_sha = item.get("previous_manifest_sha256")
        # A2: previous_generation_id may be null ONLY for a genuine
        # first-ever generation of the nest -- but a v2 manifest ALWAYS
        # carries both keys (A3); when there is no predecessor, both are
        # null together, never one without the other.
        if previous_id is None:
            if previous_sha is not None:
                raise WorkspaceError(
                    "manifest previous_manifest_sha256 must be null when "
                    "previous_generation_id is null"
                )
        else:
            if not _GENERATION_RE.fullmatch(str(previous_id)):
                raise WorkspaceError("invalid manifest previous_generation_id")
            if (
                not isinstance(previous_sha, str)
                or len(previous_sha) != 64
                or any(ch not in "0123456789abcdef" for ch in previous_sha)
            ):
                raise WorkspaceError("invalid manifest previous_manifest_sha256")
            if str(previous_id) == str(item.get("generation_id") or ""):
                raise WorkspaceError("manifest previous_generation_id cannot equal its own generation_id")


def _strip_private(workspace: Mapping[str, Any]) -> dict[str, Any]:
    return {key: workspace[key] for key in WORKSPACE_KEYS}


def _register_alias(alias_map: dict[str, str], alias: object, event_id: str) -> None:
    """Bind one alias to a canonical event before marker promotion.

    Same alias → same event is idempotent. Same alias → a different canonical
    event raises ``WorkspaceError`` so dictionary assignment cannot silently
    overwrite ownership.
    """
    key = str(alias or "").strip()
    if not key:
        return
    existing = alias_map.get(key)
    if existing is None:
        alias_map[key] = event_id
        return
    if existing != event_id:
        raise WorkspaceError(
            f"alias {key!r} is already owned by {existing}; "
            f"cannot reassign to {event_id}"
        )


def _generation_identity(
    workspaces: Mapping[str, Mapping[str, Any]],
    generated_at: str,
    *,
    previous_generation_id: str | None = None,
) -> str:
    """Content address for one nest generation.

    A4: *previous_generation_id* is folded into the hash so identical
    workspace content atop a DIFFERENT predecessor mints a DISTINCT
    generation_id -- a content cycle A -> B -> A must mint a distinct third
    generation, never collide with the original A.  The semantic no-op (an
    unchanged-source re-run atop the SAME predecessor) is preserved: same
    content + same previous_generation_id -> same hash -> short-circuits
    before any new generation is minted.
    """
    pre_id = {
        event_id: {key: payload[key] for key in WORKSPACE_KEYS if key != "generation_id"}
        for event_id, payload in sorted(workspaces.items())
    }
    return sha256(canonical_json_bytes({
        "generated_at": generated_at,
        "previous_generation_id": previous_generation_id,
        "workspaces": pre_id,
    })).hexdigest()[:24]


def preview_generation_identity(
    workspaces: Mapping[str, Mapping[str, Any]],
    generated_at: str,
    *,
    previous_generation_id: str | None = None,
) -> str:
    """Pure preview of the ``generation_id`` :func:`write_workspace_generation`
    would mint for *workspaces* at *generated_at* atop *previous_generation_id*
    — no disk writes.  A caller that must decide, BEFORE writing, whether a
    cycle's freshly-assembled content reproduces the CURRENTLY published
    generation (the semantic no-op, A4) needs this: with
    ``previous_generation_id`` folded into the hash, that decision requires
    computing the candidate id against the CURRENT generation's OWN
    predecessor first (see ``scripts/refresh_event_workspaces.py``'s
    chain-pointer resolution)."""
    cleaned = {event_id: _strip_private(payload) for event_id, payload in workspaces.items()}
    return _generation_identity(cleaned, str(generated_at), previous_generation_id=previous_generation_id)


def write_workspace_generation(
    out_dir: Path,
    workspaces: Mapping[str, Mapping[str, Any]],
    *,
    generated_at: str | None = None,
    status: str = "ready",
    previous_generation_id: str | None = None,
    previous_manifest_sha256: str | None = None,
) -> Path:
    """Write immutable workspace objects, then atomically advance the nest marker.

    ``out_dir`` is the Company Intelligence product prefix
    (``company_intelligence/``).  Objects land under ``event_workspaces/``.

    IMCE A5C (manifest chain, frozen spec A): *previous_generation_id* is the
    predecessor generation's id -- the currently-published generation (v1 OR
    v2; A2) at the moment this generation is minted, or the immediately
    prior generation minted EARLIER in the SAME publish cycle when several
    source revisions are being chained in one run (frozen spec B3).
    *previous_manifest_sha256* is the sha256 of that predecessor's own
    immutable ``manifest.json`` bytes -- the verification receipt for the
    link (A1).  Both are ``None`` ONLY for a genuine first-ever generation of
    the nest (A2); every OTHER call must supply the real predecessor, or the
    resulting v2 manifest's chain link would be undiscoverable.  Every
    generation minted by this function is v2 going forward -- v1 stays
    readable only as pre-existing history.
    """
    if not workspaces:
        raise WorkspaceError("write_workspace_generation requires at least one workspace")
    if previous_generation_id is not None and not previous_manifest_sha256:
        raise WorkspaceError(
            "previous_manifest_sha256 is required whenever previous_generation_id is set"
        )
    stamped: dict[str, dict[str, Any]] = {}
    generated = generated_at or next(iter(workspaces.values())).get("generated_at")
    if not generated:
        generated = _iso(datetime.now(timezone.utc))
    cleaned = {
        event_id: _strip_private(payload)
        for event_id, payload in workspaces.items()
    }
    generation_id = _generation_identity(
        cleaned, str(generated), previous_generation_id=previous_generation_id,
    )
    alias_map: dict[str, str] = {}
    for event_id, payload in cleaned.items():
        if event_id != payload.get("event_id"):
            raise WorkspaceError("workspace map key must equal event_id")
        row = dict(payload)
        row["generation_id"] = generation_id
        row["generated_at"] = str(generated)
        validate_event_workspace(row)
        stamped[event_id] = row
        _register_alias(alias_map, event_id, event_id)
        for alias in row.get("aliases") or []:
            _register_alias(alias_map, alias, event_id)
        private = workspaces[event_id]
        extra = private.get("_aliases") if isinstance(private, Mapping) else None
        if isinstance(extra, Mapping):
            _register_alias(alias_map, extra.get("canonical_event_id"), event_id)
            for family in (
                extra.get("company_intelligence_ids") or [],
                extra.get("earnings_narrative_keys") or [],
                extra.get("public_slugs") or [],
            ):
                for alias in family:
                    _register_alias(alias_map, alias, event_id)

    nest = Path(out_dir) / NEST
    generation_dir = nest / "generations" / generation_id
    file_blocks: dict[str, dict[str, Any]] = {}
    for event_id in sorted(stamped):
        relative = f"workspaces/{event_id}.json"
        path = generation_dir / relative
        body = canonical_json_bytes(stamped[event_id])
        if path.exists() and path.read_bytes() != body:
            raise WorkspaceError(f"immutable generation collision: {path}")
        if not path.exists():
            _atomic_write(path, body)
        file_blocks[relative] = {
            "bytes": len(body),
            "sha256": sha256(body).hexdigest(),
        }

    manifest = {
        "aliases": dict(sorted(alias_map.items())),
        "authority": AUTHORITY,
        "event_count": len(stamped),
        "files": dict(sorted(file_blocks.items())),
        "generated_at": str(generated),
        "generation_id": generation_id,
        "schema": MANIFEST_SCHEMA_V2,
        "status": status,
        "warnings": [],
        "previous_generation_id": previous_generation_id,
        "previous_manifest_sha256": previous_manifest_sha256,
    }
    # Re-order to MANIFEST_KEYS_V2.
    manifest = {key: manifest[key] for key in MANIFEST_KEYS_V2}
    validate_workspace_manifest(manifest)
    manifest_body = canonical_json_bytes(manifest)
    immutable_manifest_path = generation_dir / "manifest.json"
    if immutable_manifest_path.exists() and immutable_manifest_path.read_bytes() != manifest_body:
        raise WorkspaceError(f"immutable generation collision: {immutable_manifest_path}")
    if not immutable_manifest_path.exists():
        _atomic_write(immutable_manifest_path, manifest_body)
    _atomic_write(nest / "manifest.json", manifest_body)
    return generation_dir


def resolve_workspace_event_id(event_id: object, aliases: Mapping[str, str]) -> str:
    """Resolve a canonical id or published alias through the generation manifest."""
    text = str(event_id or "").strip()
    if not text:
        raise WorkspaceError("event_id is required")
    if text in aliases:
        return str(aliases[text])
    if _EVENT_ID_RE.fullmatch(text):
        return text
    raise WorkspaceError(f"unresolved event id: {text}")


@dataclass(frozen=True)
class SelectedEvent:
    """Result of ``select_current_event_from_aliases``.

    ``alias`` is the T/YYYYQn key that matched (e.g. ``"AAPL/2026Q3"``).
    """

    event_id: str
    ticker: str
    year: int
    quarter: int
    alias: str


def select_current_event_from_aliases(
    ticker: str,
    aliases: Union[Mapping[str, str], Sequence[tuple[str, str]]],
) -> SelectedEvent:
    """Select the most-recent T/YYYYQn event for *ticker* from *aliases*.

    *aliases* is the ``aliases`` dict from an ``event_workspace_manifest.v1``
    (a ``Mapping[str, str]``), or a sequence of ``(alias, canonical)`` pairs
    so tests can inject duplicate keys that a plain dict cannot represent.

    Rules
    -----
    * Only aliases whose key matches ``^TICKER/YYYYQn$`` (after
      ``safe_ticker``) are admitted.
    * At most one distinct canonical ``event_id`` is permitted per fiscal
      period (year, quarter).  If a period maps to two or more distinct ids,
      the call fails closed with a ``WorkspaceError`` whose message contains
      ``"ambiguous"``.
    * When no admitted alias exists the error message contains
      ``"does not cover"``.
    * The admitted alias with the greatest ``(year, quarter)`` is returned.
    """
    try:
        normalized = safe_ticker(ticker)
    except ContractError as exc:
        raise WorkspaceError(str(exc)) from exc

    # Build per-ticker pattern: ^AAPL/(\d{4})Q([1-4])$ for ticker AAPL.
    pattern = re.compile(r"^" + re.escape(normalized) + r"/(\d{4})Q([1-4])$")

    # Normalize to a sequence of pairs so duplicate keys are visible.
    if isinstance(aliases, Mapping):
        pairs: list[tuple[str, str]] = list(aliases.items())
    else:
        pairs = [(str(a), str(c)) for a, c in aliases]

    # period → set of distinct canonical event_ids admitted under that period.
    period_ids: dict[tuple[int, int], set[str]] = {}
    # period → the first matching alias key (for the return value).
    period_alias: dict[tuple[int, int], str] = {}

    for alias_key, canonical in pairs:
        m = pattern.fullmatch(str(alias_key))
        if m is None:
            continue
        canonical_str = str(canonical)
        if not _EVENT_ID_RE.fullmatch(canonical_str):
            continue
        year = int(m.group(1))
        quarter = int(m.group(2))
        period = (year, quarter)
        if period not in period_ids:
            period_ids[period] = set()
            period_alias[period] = alias_key
        period_ids[period].add(canonical_str)

    if not period_ids:
        raise WorkspaceError(
            f"Event workspace does not cover {normalized}"
        )

    # Fail closed on any fiscal period with >1 distinct canonical owner.
    for (year, quarter), ids in period_ids.items():
        if len(ids) > 1:
            raise WorkspaceError(
                f"{normalized}/{year}Q{quarter} is ambiguous: "
                f"{len(ids)} distinct canonical ids"
            )

    best_period = max(period_ids)
    best_year, best_quarter = best_period
    best_event_id = next(iter(period_ids[best_period]))
    best_alias = period_alias[best_period]

    return SelectedEvent(
        event_id=best_event_id,
        ticker=normalized,
        year=best_year,
        quarter=best_quarter,
        alias=best_alias,
    )


def index_from_workspace(payload: Mapping[str, Any]) -> EventAliasIndex:
    extra = payload.get("_aliases")
    if isinstance(extra, Mapping) and extra.get("canonical_event_id"):
        aliases = aliases_for(
            extra["company_id"],
            FiscalPeriod(
                year=int(extra["fiscal_period"]["year"]),
                quarter=extra["fiscal_period"].get("quarter"),
            ),
            extra.get("tickers") or (),
        )
    else:
        aliases = aliases_for(
            payload["issuer"]["company_id"],
            FiscalPeriod(
                year=int(payload["fiscal_period"]["year"]),
                quarter=payload["fiscal_period"].get("quarter"),
            ),
            [
                listing["ticker"]
                for listing in payload.get("issuer", {}).get("listings") or []
            ],
        )
    index = EventAliasIndex()
    index.register(aliases)
    return index
