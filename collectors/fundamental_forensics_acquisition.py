"""Explicit, bounded SEC acquisition for Filing Forensics Wave 2.

This is an operator/collect-lane module, never a render dependency.  Given an
explicit list of ``TICKER=CIK`` targets plus explicit SEC acceptance and
recording clocks, it retains only:

1. one Company Submissions response per target; and
2. at most the latest two comparable 10-K and two comparable 10-Q primary
   documents visible at the acceptance-time cutoff.

The underlying collectors retain content-addressed source bytes.  This module
adds conservative selection, run bounds, filing manifests retained one per
``(accession, content)``, and one immutable per-run observation log that keeps
every ticker's portable receipt even when one issuer fails.  It deliberately
does not fetch Company Facts, walk a universe, call a browser, or invoke a
render.

Nightly re-manifests of an unchanged accession are not evidence; the
*observation* they imply is, and it lives in the observation log rather than in
file multiplicity (``DNR:LAW-RUN-CLOCK-IN-CONTENT-IDENTITY``, 2026-08-08).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime
import functools
import gzip
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import time
from typing import Any, Callable, Iterable, Mapping

from collectors.edgar_forensics import SecForensicsCollector
from collectors.sec_document_spine import (
    ArchiveResponseTooLarge,
    SecFilingArchiveCollector,
    find_reusable_primary_retrieval,
    retain_filing_manifest,
    stored_manifest_content_index,
)
from engine.fundamental_forensics.models import canonical_json, parse_utc, utc_text
from engine.fundamental_forensics.sec_document_spine import (
    FilingManifestError,
    build_filing_manifests,
    canonical_cik,
    manifest_content_key,
    select_periodic_comparables,
    with_document_retrievals,
)


# ``ACQUISITION_RUN_SCHEMA`` is retained deliberately: it is hashed into
# ``_run_id`` and a run genuinely *is* a distinct event, so run ids must not
# move (adjudication 2026-08-08, R6).  What the run emits is now the
# observation log, which folds every per-ticker receipt into one object.
ACQUISITION_RUN_SCHEMA = "fundamental_forensics.sec_acquisition_run/v1"
ACQUISITION_TICKER_SCHEMA = "fundamental_forensics.sec_acquisition_ticker_receipt/v1"
SEC_OBSERVATION_LOG_SCHEMA = "fundamental_forensics.sec_observation_log/v1"
# The observation log lives OUTSIDE the restorable source tree: restore exists
# to reconstitute replay inputs, and our cron history is not one (R6).  The
# prefix is resolved against ``observation_root``, never against
# ``archive_root``/``raw_root``.
OBSERVATION_RELATIVE_ROOT = Path("runs/acquisition")
OBSERVATION_OUTCOMES = ("unchanged", "new_content", "new_filing", "missing")
# How the primary document was proved this run.  Kept separate from the outcome
# so a warm-archive run never logs a byte-level re-download it did not perform.
PRIMARY_VERIFICATIONS = ("network_refetch", "local_reuse")
FORM_FAMILIES = ("10-K", "10-Q")

# Hard ceilings prevent this command from becoming an accidental annual EDGAR
# mirror.  Users may lower them for a recovery run but cannot increase them.
HARD_MAX_TICKERS = 32
HARD_MAX_DOCUMENTS_PER_FORM = 2
HARD_MAX_DOCUMENT_BYTES = 32 * 1024 * 1024
HARD_MAX_TICKER_BYTES = 128 * 1024 * 1024
HARD_MAX_TOTAL_BYTES = 512 * 1024 * 1024

DEFAULT_MAX_TICKERS = 12
DEFAULT_MAX_DOCUMENTS_PER_FORM = 2
DEFAULT_MAX_SUBMISSIONS_BYTES = 16 * 1024 * 1024
DEFAULT_MAX_DOCUMENT_BYTES = 16 * 1024 * 1024
DEFAULT_MAX_TICKER_BYTES = 80 * 1024 * 1024
DEFAULT_MAX_TOTAL_BYTES = 256 * 1024 * 1024

_TICKER_RE = re.compile(r"^[A-Z0-9][A-Z0-9.\-]{0,15}$")
_SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
_RUN_ID_RE = re.compile(r"^ffsecacq_[a-f0-9]{64}$")


class AcquisitionError(RuntimeError):
    """The bounded SEC acquisition request or retained source is unsafe."""


@dataclass(frozen=True)
class AcquisitionTarget:
    """One user-authorized issuer target; no implicit universe lookup exists."""

    ticker: str
    cik: str

    def to_dict(self) -> dict[str, str]:
        return {"ticker": self.ticker, "cik": self.cik}


def _normalized_ticker(value: str) -> str:
    ticker = str(value or "").strip().upper()
    if not _TICKER_RE.fullmatch(ticker):
        raise AcquisitionError(f"invalid ticker: {value!r}")
    return ticker


def _normalized_cik(value: int | str) -> str:
    try:
        return canonical_cik(value)
    except FilingManifestError as exc:
        raise AcquisitionError(str(exc)) from exc


def parse_target(value: str | AcquisitionTarget | tuple[str, int | str]) -> AcquisitionTarget:
    """Parse one strict ``TICKER=CIK`` target without consulting local metadata."""
    if isinstance(value, AcquisitionTarget):
        return AcquisitionTarget(_normalized_ticker(value.ticker), _normalized_cik(value.cik))
    if isinstance(value, tuple) and len(value) == 2:
        ticker, cik = value
        return AcquisitionTarget(_normalized_ticker(str(ticker)), _normalized_cik(cik))
    text = str(value or "")
    if text.count("=") != 1:
        raise AcquisitionError("target must use TICKER=CIK")
    ticker, cik = text.split("=", 1)
    return AcquisitionTarget(_normalized_ticker(ticker), _normalized_cik(cik))


def normalize_targets(
    values: Iterable[str | AcquisitionTarget | tuple[str, int | str]], *, max_tickers: int = DEFAULT_MAX_TICKERS
) -> tuple[AcquisitionTarget, ...]:
    """Normalize an explicit target list and reject aliasing / unbounded requests."""
    if isinstance(max_tickers, bool) or not isinstance(max_tickers, int) or max_tickers < 1:
        raise AcquisitionError("max_tickers must be a positive integer")
    if max_tickers > HARD_MAX_TICKERS:
        raise AcquisitionError(f"max_tickers exceeds hard safety ceiling {HARD_MAX_TICKERS}")
    result: list[AcquisitionTarget] = []
    by_ticker: dict[str, str] = {}
    by_cik: dict[str, str] = {}
    for raw in values:
        target = parse_target(raw)
        known_cik = by_ticker.get(target.ticker)
        known_ticker = by_cik.get(target.cik)
        if known_cik is not None and known_cik != target.cik:
            raise AcquisitionError(f"ticker {target.ticker} is mapped to multiple CIKs")
        if known_ticker is not None and known_ticker != target.ticker:
            raise AcquisitionError(f"CIK {target.cik} is mapped to multiple tickers")
        if known_cik is not None:
            continue
        if len(result) >= max_tickers:
            raise AcquisitionError(f"explicit target list exceeds cap {max_tickers}")
        by_ticker[target.ticker] = target.cik
        by_cik[target.cik] = target.ticker
        result.append(target)
    if not result:
        raise AcquisitionError("at least one explicit TICKER=CIK target is required")
    return tuple(result)


def _normalized_clock(value: str | datetime, *, field: str) -> str:
    try:
        parsed = parse_utc(value, field=field)
    except ValueError as exc:
        raise AcquisitionError(str(exc)) from exc
    if parsed is None:  # pragma: no cover - signature requires a value
        raise AcquisitionError(f"{field} is required")
    return utc_text(parsed) or ""  # pragma: no cover - parsed is non-null


def _positive_limit(value: int, *, field: str, ceiling: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise AcquisitionError(f"{field} must be a positive integer")
    if value > ceiling:
        raise AcquisitionError(f"{field} exceeds hard safety ceiling {ceiling}")
    return value


def _validate_limits(
    *,
    max_tickers: int,
    max_documents_per_form: int,
    max_submissions_bytes: int,
    max_document_bytes: int,
    max_ticker_bytes: int,
    max_total_bytes: int,
) -> dict[str, int]:
    result = {
        "max_tickers": _positive_limit(max_tickers, field="max_tickers", ceiling=HARD_MAX_TICKERS),
        "max_documents_per_form": _positive_limit(
            max_documents_per_form,
            field="max_documents_per_form",
            ceiling=HARD_MAX_DOCUMENTS_PER_FORM,
        ),
        "max_submissions_bytes": _positive_limit(
            max_submissions_bytes,
            field="max_submissions_bytes",
            ceiling=HARD_MAX_DOCUMENT_BYTES,
        ),
        "max_document_bytes": _positive_limit(
            max_document_bytes,
            field="max_document_bytes",
            ceiling=HARD_MAX_DOCUMENT_BYTES,
        ),
        "max_ticker_bytes": _positive_limit(
            max_ticker_bytes,
            field="max_ticker_bytes",
            ceiling=HARD_MAX_TICKER_BYTES,
        ),
        "max_total_bytes": _positive_limit(
            max_total_bytes,
            field="max_total_bytes",
            ceiling=HARD_MAX_TOTAL_BYTES,
        ),
    }
    minimum = result["max_submissions_bytes"] + result["max_document_bytes"]
    if result["max_ticker_bytes"] < minimum:
        raise AcquisitionError("max_ticker_bytes must cover one submissions response and one document")
    if result["max_total_bytes"] < result["max_ticker_bytes"]:
        raise AcquisitionError("max_total_bytes must be at least max_ticker_bytes")
    return result


def _safe_relative(value: str | Path) -> Path:
    text = str(value)
    relative = Path(text)
    if (
        not text
        or "\\" in text
        or "\x00" in text
        or relative.is_absolute()
        or ".." in relative.parts
        or not relative.parts
    ):
        raise AcquisitionError(f"unsafe local source path: {value!r}")
    return relative


def _safe_child(root: Path, relative: str | Path) -> Path:
    checked_root = Path(root).resolve()
    child = (checked_root / _safe_relative(relative)).resolve()
    try:
        child.relative_to(checked_root)
    except ValueError as exc:
        raise AcquisitionError(f"source path escapes root: {relative!r}") from exc
    return child


def _receipt_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if is_dataclass(value):
        return asdict(value)
    if hasattr(value, "to_dict"):
        candidate = value.to_dict()
        if isinstance(candidate, Mapping):
            return dict(candidate)
    raise AcquisitionError("collector returned an invalid receipt")


def read_verified_submissions(
    raw_root: Path,
    cik: str | int,
    *,
    max_bytes: int = DEFAULT_MAX_SUBMISSIONS_BYTES,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Read the latest persisted Submissions payload with receipt/hash verification."""
    limit = _positive_limit(max_bytes, field="max_bytes", ceiling=HARD_MAX_DOCUMENT_BYTES)
    cik10 = _normalized_cik(cik)
    latest = _safe_child(Path(raw_root), Path(cik10) / "submissions" / "latest.json")
    try:
        receipt = json.loads(latest.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AcquisitionError(f"missing or invalid submissions pointer for CIK {cik10}") from exc
    if not isinstance(receipt, Mapping):
        raise AcquisitionError("submissions pointer must be an object")
    required = {
        "schema", "cik", "endpoint", "url", "retrieved_at", "sha256", "bytes", "object_path",
        "http_etag", "http_last_modified",
    }
    if set(receipt) != required:
        raise AcquisitionError("submissions pointer shape is invalid")
    if receipt.get("schema") != "fundamental_forensics_retrieval.v1" or receipt.get("endpoint") != "submissions":
        raise AcquisitionError("submissions pointer does not describe the SEC Submissions endpoint")
    if _normalized_cik(receipt.get("cik")) != cik10:
        raise AcquisitionError("submissions pointer CIK does not match request")
    digest = str(receipt.get("sha256") or "")
    length = receipt.get("bytes")
    if not _SHA256_RE.fullmatch(digest):
        raise AcquisitionError("submissions pointer has invalid SHA-256")
    if isinstance(length, bool) or not isinstance(length, int) or length < 0 or length > limit:
        raise AcquisitionError("submissions pointer exceeds bounded input limit")
    object_path = str(receipt.get("object_path") or "")
    expected_prefix = f"{cik10}/submissions/"
    if not object_path.startswith(expected_prefix) or not object_path.endswith(".json.gz"):
        raise AcquisitionError("submissions pointer object path is not in the CIK namespace")
    source = _safe_child(Path(raw_root), object_path)
    try:
        with gzip.open(source, "rb") as handle:
            content = handle.read(limit + 1)
    except (OSError, EOFError) as exc:
        raise AcquisitionError("submissions source object is unreadable") from exc
    if len(content) != length or len(content) > limit or sha256(content).hexdigest() != digest:
        raise AcquisitionError("submissions source checksum or length mismatch")
    try:
        document = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AcquisitionError("submissions source is not UTF-8 JSON") from exc
    if not isinstance(document, dict):
        raise AcquisitionError("submissions source must be a JSON object")
    response_cik = document.get("cik")
    if response_cik is not None and _normalized_cik(response_cik) != cik10:
        raise AcquisitionError("submissions body CIK does not match pointer")
    portable = {
        "schema": str(receipt["schema"]),
        "cik": cik10,
        "endpoint": "submissions",
        "url": str(receipt["url"]),
        "retrieved_at": _normalized_clock(str(receipt["retrieved_at"]), field="submissions.retrieved_at"),
        "sha256": digest,
        "bytes": length,
        "object_path": object_path,
        "http_etag": receipt.get("http_etag"),
        "http_last_modified": receipt.get("http_last_modified"),
    }
    return document, portable


def _temp_sibling(path: Path) -> Path:
    return path.with_name(f".{path.name}.{os.getpid()}.{time.time_ns()}.tmp")


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = _temp_sibling(path)
    try:
        with temporary.open("xb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        try:
            descriptor = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        except OSError:
            pass
    finally:
        temporary.unlink(missing_ok=True)


def _failure(stage: str, exc: BaseException) -> dict[str, str]:
    message = " ".join(str(exc).replace("\x00", "").split())
    # Collector errors may contain SEC URLs but never credentials.  Keep the
    # portable receipt compact enough for a private workbench state later.
    return {
        "stage": stage,
        "error_type": type(exc).__name__,
        "message": message[:480] if message else type(exc).__name__,
    }


def _run_id(
    *, targets: tuple[AcquisitionTarget, ...], as_of: str, recorded_at: str, limits: Mapping[str, int]
) -> str:
    body = {
        "schema": ACQUISITION_RUN_SCHEMA,
        "targets": [target.to_dict() for target in targets],
        "as_of": as_of,
        "recorded_at": recorded_at,
        "limits": dict(limits),
    }
    return "ffsecacq_" + sha256(canonical_json(body).encode("utf-8")).hexdigest()


def observation_log_path(observation_root: Path, run_id: str) -> Path:
    """Return the single immutable observation-log object for one run."""
    if not _RUN_ID_RE.fullmatch(str(run_id)):
        raise AcquisitionError("invalid acquisition run id")
    return _safe_child(observation_root, OBSERVATION_RELATIVE_ROOT / f"{run_id}.json")


def _observation_row(
    *,
    ticker: str,
    cik: str,
    accession: str,
    form: str,
    manifest: Mapping[str, Any] | None,
    manifest_key: str | None,
    observed_at: str,
    outcome: str,
    primary_verification: str | None,
) -> dict[str, Any]:
    """Bind one night's re-derivation of one accession to its exact outcome.

    The four outcomes are exhaustive and mutually exclusive:

    ``new_filing``
        No stored manifest existed for that ``(cik, accession)`` before this run.
    ``new_content``
        Stored manifests exist for the accession, but tonight's content key is
        not among them — the filing itself changed.
    ``unchanged``
        Tonight's content key matched a stored manifest.  This is the explicit
        "we looked, nothing changed" assertion; before this ruling it was
        implied only by minting a duplicate manifest object.
    ``missing``
        The run obtained no stored primary document for that accession — an
        explicit SEC miss (404), byte-budget exhaustion, or a fetch failure.
        ``missing`` takes precedence over the other three.

    A target whose submissions fetch failed outright observes no accession and
    therefore contributes no rows; its failure stays in ``ticker_receipts``.

    ``primary_verification`` states HOW the primary document was proved this
    run, so an outcome is never read as a stronger check than the one that ran
    (see ``acquire_bounded_filings``).  ``network_refetch`` re-downloaded the
    document from SEC and recomputed its digest from the fresh response;
    ``local_reuse`` re-proved the retained bytes against the recorded
    sha256/length locally without asking SEC for them; ``None`` means the run
    never reached the primary at all (a declaration-persist failure or an
    exhausted byte budget), which only ever pairs with ``missing``.
    """
    if outcome not in OBSERVATION_OUTCOMES:
        raise AcquisitionError(f"invalid observation outcome: {outcome!r}")
    if primary_verification is not None and primary_verification not in PRIMARY_VERIFICATIONS:
        raise AcquisitionError(f"invalid primary verification: {primary_verification!r}")
    content_key: str | None = None
    manifest_id: str | None = None
    if manifest is not None:
        content_key = manifest_content_key(manifest)
        manifest_id = str(manifest["manifest_id"])
    return {
        "ticker": ticker,
        "cik": cik,
        "accession": accession,
        "form": form,
        "outcome": outcome,
        "primary_verification": primary_verification,
        "manifest_id": manifest_id,
        "manifest_storage_key": manifest_key,
        "content_key": content_key,
        "observed_at": observed_at,
    }


def _write_observation_log(observation_root: Path, run: Mapping[str, Any]) -> Path:
    """Create one immutable observation-log object, never overwriting another.

    An identical object at the same key is accepted (a re-run of the same run
    id observing the same thing); different bytes at that key are refused
    rather than silently replaced, matching the immutable-create discipline the
    rest of the source store uses.
    """
    if run.get("schema") != SEC_OBSERVATION_LOG_SCHEMA:
        raise AcquisitionError("invalid observation log schema")
    path = observation_log_path(observation_root, str(run.get("run_id") or ""))
    content = canonical_json(dict(run)).encode("utf-8")
    if path.exists():
        try:
            existing = path.read_bytes()
        except OSError as exc:
            raise AcquisitionError(f"failed to read existing observation log: {path}") from exc
        if existing != content:
            raise AcquisitionError(
                f"observation log already exists with different bytes: {path}"
            )
        return path
    _atomic_write(path, content)
    try:
        readback = path.read_bytes()
        parsed = json.loads(readback.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AcquisitionError(f"failed to read back observation log: {path}") from exc
    if canonical_json(parsed).encode("utf-8") != readback or parsed != dict(run):
        raise AcquisitionError(f"observation log read-back mismatch: {path}")
    return path


def _primary_byte_length(manifest: Mapping[str, Any]) -> int:
    primary = next(
        (item for item in manifest.get("documents", []) if item.get("role") == "primary"),
        None,
    )
    if not isinstance(primary, Mapping):
        raise AcquisitionError("materialized filing manifest has no primary document")
    if primary.get("availability") == "missing":
        return 0
    if primary.get("availability") != "stored":
        raise AcquisitionError("primary document retrieval did not produce a stored or missing receipt")
    length = primary.get("byte_length")
    if isinstance(length, bool) or not isinstance(length, int) or length < 0:
        raise AcquisitionError("stored primary document has invalid byte length")
    return length


def _has_stored_primary(manifest: Mapping[str, Any]) -> bool:
    """Report whether the run actually retained this filing's primary bytes."""
    primary = next(
        (item for item in manifest.get("documents", []) if item.get("role") == "primary"),
        None,
    )
    return isinstance(primary, Mapping) and primary.get("availability") == "stored"


def _form_receipt(form: str) -> dict[str, Any]:
    return {
        "form": form,
        "requested_comparables": DEFAULT_MAX_DOCUMENTS_PER_FORM,
        "selected_accessions": [],
        "manifest_keys": [],
        "stored_documents": 0,
        "missing_documents": 0,
        # Always present, zero when the reuse flag is off, so one receipt shape
        # spans both flag states and a nightly diff stays readable.
        "reused_documents": 0,
        "status": "not_started",
        "failures": [],
    }


def acquire_bounded_filings(
    *,
    targets: Iterable[str | AcquisitionTarget | tuple[str, int | str]],
    raw_root: Path,
    archive_root: Path,
    user_agent: str,
    as_of: str | datetime,
    recorded_at: str | datetime,
    observation_root: Path | None = None,
    max_tickers: int = DEFAULT_MAX_TICKERS,
    max_documents_per_form: int = DEFAULT_MAX_DOCUMENTS_PER_FORM,
    max_submissions_bytes: int = DEFAULT_MAX_SUBMISSIONS_BYTES,
    max_document_bytes: int = DEFAULT_MAX_DOCUMENT_BYTES,
    max_ticker_bytes: int = DEFAULT_MAX_TICKER_BYTES,
    max_total_bytes: int = DEFAULT_MAX_TOTAL_BYTES,
    min_interval_seconds: float = 0.12,
    reuse_local_archive: bool = False,
    submissions_collector_factory: Callable[..., Any] = SecForensicsCollector,
    archive_collector_factory: Callable[..., Any] = SecFilingArchiveCollector,
) -> dict[str, Any]:
    """Fetch the bounded periodic filing slice and persist receipt-rich manifests.

    The function owns no scheduling and has no default targets/clocks.  Each
    target produces a durable result or failure receipt; a single failed SEC
    issuer therefore never erases evidence for the other explicit targets.

    ``reuse_local_archive`` (default off, so the fetch path is unchanged) lets a
    warm-archive lane satisfy an already-retrieved primary document from local
    sha256-verified bytes instead of re-downloading identical bytes from SEC.
    Submissions are ALWAYS fetched fresh — that is how a new filing is
    discovered — and a reuse miss falls through to the network fetch unchanged,
    so the ``--require-complete-acquisition`` gate keeps its meaning: a verified
    local hit IS the stored evidence, and anything uncovered still lands as
    partial.

    Byte-budget semantics: ``max_ticker_bytes``/``max_total_bytes`` and the
    per-document ``available`` cap bound NETWORK ingest.  Reused bytes traverse
    no network, consume no budget, and are accounted separately as
    ``bytes_reused``.  ``bytes_retained`` keeps meaning bytes retrieved over the
    network during this run — it is the number whose nightly drop proves the
    reuse path is live.

    Dedupe happens only at persist time — an accession whose content matches a
    stored manifest reuses that manifest verbatim and writes nothing.  The run
    emits one immutable observation object under ``observation_root``, which
    defaults to a sibling of ``archive_root`` and must never sit inside the
    restorable ``archive_root``/``raw_root`` trees.

    WHAT AN OBSERVATION ACTUALLY ASSERTS, and why it depends on
    ``reuse_local_archive``.  The adjudication requires the log to record a
    check that happened, never one that did not.  Submissions are ALWAYS
    fetched fresh, so the filing-level re-derivation — accession, form, report
    date, acceptance clock, lineage — is a genuine nightly re-derivation from a
    freshly retrieved SEC response in BOTH flag states.  The primary document
    is where the two states differ, so every row carries
    ``primary_verification`` saying which one actually occurred:

    * ``network_refetch`` — the document was re-downloaded from SEC this run and
      its digest recomputed from the fresh response;
    * ``local_reuse`` — the retained bytes were re-proved against the recorded
      sha256/length locally and the prior receipt reused verbatim; SEC was not
      asked for those bytes.

    An ``unchanged`` outcome therefore never silently implies a byte-level
    re-download.  Without this field a warm-archive run would log an assertion
    strictly stronger than the check it performed.
    """
    limits = _validate_limits(
        max_tickers=max_tickers,
        max_documents_per_form=max_documents_per_form,
        max_submissions_bytes=max_submissions_bytes,
        max_document_bytes=max_document_bytes,
        max_ticker_bytes=max_ticker_bytes,
        max_total_bytes=max_total_bytes,
    )
    # Two comparable filings is contractual.  Exposing a lower count would
    # silently make disclosure diffs impossible; a higher count violates the
    # bounded Wave-2 admission rule.
    if limits["max_documents_per_form"] != DEFAULT_MAX_DOCUMENTS_PER_FORM:
        raise AcquisitionError("Wave-2 requires exactly two comparables per form")
    normalized_targets = normalize_targets(targets, max_tickers=limits["max_tickers"])
    cutoff = _normalized_clock(as_of, field="as_of")
    recorded = _normalized_clock(recorded_at, field="recorded_at")
    if "@" not in str(user_agent):
        raise AcquisitionError("SEC user agent must identify an application and contact email")
    archive_path = Path(archive_root)
    if archive_path.is_symlink():
        raise AcquisitionError("archive_root cannot be a symlink")
    archive_path.mkdir(parents=True, exist_ok=True)
    archive_path = archive_path.resolve()
    raw_path = Path(raw_root)
    if raw_path.is_symlink():
        raise AcquisitionError("raw_root cannot be a symlink")
    raw_path.mkdir(parents=True, exist_ok=True)
    raw_path = raw_path.resolve()
    observation_path = (
        Path(observation_root) if observation_root is not None else archive_path.parent / "observations"
    )
    if observation_path.is_symlink():
        raise AcquisitionError("observation_root cannot be a symlink")
    observation_path.mkdir(parents=True, exist_ok=True)
    observation_path = observation_path.resolve()
    # The observation log is our cron history, not a replay input.  Keeping it
    # out of both synced trees is what stops restore/sync from paying for it,
    # and ``source_sync`` accepts exactly two trees (raw, archive) — a third
    # synced tree would fail validation on every already-published snapshot.
    for name, restorable in (("archive_root", archive_path), ("raw_root", raw_path)):
        if observation_path == restorable or observation_path.is_relative_to(restorable):
            raise AcquisitionError(f"observation_root must be outside {name}")

    submissions_collector = submissions_collector_factory(
        raw_path,
        user_agent=user_agent,
        min_interval_seconds=min_interval_seconds,
        max_response_bytes=limits["max_submissions_bytes"],
    )
    archive_collector = archive_collector_factory(
        archive_path,
        user_agent=user_agent,
        min_interval_seconds=min_interval_seconds,
        max_document_bytes=limits["max_document_bytes"],
    )
    run_id = _run_id(
        targets=normalized_targets,
        as_of=cutoff,
        recorded_at=recorded,
        limits=limits,
    )
    total_bytes = 0
    total_reused_bytes = 0
    results: list[dict[str, Any]] = []
    observations: list[dict[str, Any]] = []
    for target in normalized_targets:
        ticker_bytes = 0
        ticker_reused_bytes = 0
        ticker_failures: list[dict[str, str]] = []
        forms = {form: _form_receipt(form) for form in FORM_FAMILIES}
        receipt: dict[str, Any] = {
            "schema": ACQUISITION_TICKER_SCHEMA,
            "run_id": run_id,
            "ticker": target.ticker,
            "cik": target.cik,
            "as_of": cutoff,
            "recorded_at": recorded,
            "limits": dict(limits),
            "submissions": None,
            "forms": [forms[form] for form in FORM_FAMILIES],
            "bytes_retained": 0,
            "bytes_reused": 0,
            "status": "failed",
            "failures": ticker_failures,
        }
        try:
            available = min(
                limits["max_submissions_bytes"],
                limits["max_ticker_bytes"] - ticker_bytes,
                limits["max_total_bytes"] - total_bytes,
            )
            if available < 1:
                raise AcquisitionError("run byte budget exhausted before submissions fetch")
            fetched = submissions_collector.fetch(
                target.cik,
                "submissions",
                retrieved_at=recorded,
                max_response_bytes=available,
            )
            submissions, submission_receipt = read_verified_submissions(
                raw_path,
                target.cik,
                max_bytes=available,
            )
            # Pin the receipt returned by the network client and the receipt
            # read from disk to the same immutable object identity.
            fetched_dict = _receipt_dict(fetched)
            if any(fetched_dict.get(key) != submission_receipt.get(key) for key in ("cik", "sha256", "bytes", "object_path")):
                raise AcquisitionError("persisted submissions receipt differs from collector receipt")
            receipt["submissions"] = submission_receipt
            ticker_bytes += int(submission_receipt["bytes"])
            total_bytes += int(submission_receipt["bytes"])
        except Exception as exc:  # per-ticker continuation is intentional
            ticker_failures.append(_failure("submissions", exc))
            receipt["bytes_retained"] = ticker_bytes
            receipt["bytes_reused"] = ticker_reused_bytes
            receipt["status"] = "failed"
            results.append(receipt)
            continue

        try:
            manifests = build_filing_manifests(
                submissions,
                cik=target.cik,
                ticker=target.ticker,
                recorded_at=recorded,
            )
        except Exception as exc:
            ticker_failures.append(_failure("filing_manifest", exc))
            receipt["bytes_retained"] = ticker_bytes
            receipt["bytes_reused"] = ticker_reused_bytes
            receipt["status"] = "partial"
            results.append(receipt)
            continue

        for form in FORM_FAMILIES:
            form_result = forms[form]
            try:
                selected = select_periodic_comparables(
                    manifests,
                    form=form,
                    ticker=target.ticker,
                    as_of=cutoff,
                    count=limits["max_documents_per_form"],
                )
            except Exception as exc:
                form_result["status"] = "failed"
                failure = _failure(f"select_{form}", exc)
                form_result["failures"].append(failure)
                ticker_failures.append(failure)
                continue
            form_result["selected_accessions"] = [
                str(item["filing"]["accession"]) for item in selected
            ]
            if len(selected) < limits["max_documents_per_form"]:
                form_result["status"] = "partial"
                form_result["failures"].append(
                    {
                        "stage": f"select_{form}",
                        "error_type": "ComparableCoverageShortfall",
                        "message": f"only {len(selected)} of {limits['max_documents_per_form']} comparable {form} filings were eligible at as_of",
                    }
                )
            else:
                form_result["status"] = "complete"
            for manifest in selected:
                accession = str(manifest["filing"]["accession"])
                declared_manifest_key: str | None = None
                declared_manifest: dict[str, Any] | None = None
                observe = functools.partial(
                    _observation_row,
                    ticker=target.ticker,
                    cik=target.cik,
                    accession=accession,
                    form=form,
                    observed_at=recorded,
                )
                try:
                    # Whether ANY manifest for this accession was stored BEFORE
                    # tonight is what separates ``new_filing`` from
                    # ``new_content``; read it before the declaration mint,
                    # which would otherwise create the very evidence tested.
                    known_accession = bool(
                        stored_manifest_content_index(
                            archive_path, cik=target.cik, accession=accession
                        )
                    )
                    # Retain the selection before the network leg.  If the
                    # archive is temporarily unavailable, the durable receipt
                    # still proves which accession was admitted at this as-of.
                    # Unchanged content reuses the stored declaration verbatim.
                    (
                        declared_manifest_key,
                        declared_manifest,
                        _,
                    ) = retain_filing_manifest(archive_path, manifest)
                except Exception as exc:
                    failure = _failure(f"persist_{form}_declaration", exc)
                    form_result["failures"].append(failure)
                    ticker_failures.append(failure)
                    form_result["status"] = "partial"
                    observations.append(
                        observe(
                            manifest=None,
                            manifest_key=None,
                            outcome="missing",
                            primary_verification=None,
                        )
                    )
                    continue
                # Decided BEFORE the ingest budget, because a local hit spends
                # none of it.  The manifest was just validated by the declared
                # persist above, so the lookup can only report a local-store
                # anomaly (as None), never raise on this input.
                reused = (
                    find_reusable_primary_retrieval(archive_path, manifest)
                    if reuse_local_archive
                    else None
                )
                if reused is not None:
                    try:
                        # The prior receipt is attached verbatim: its clock,
                        # ETag and receipt id still describe the retrieval that
                        # actually happened over the wire.
                        materialized = with_document_retrievals(
                            manifest, {str(reused["document_id"]): reused}
                        )
                        primary_bytes = _primary_byte_length(materialized)
                        # Dedupe applies on this path too.  Reusing the receipt
                        # verbatim already holds the retrieval clocks still, so
                        # the only thing left moving is ``clocks.recorded_at``;
                        # minting here would re-create nightly duplicates on the
                        # exact path the lane runs.
                        manifest_key, retained, minted = retain_filing_manifest(
                            archive_path, materialized
                        )
                    except Exception as exc:
                        # No fetch fallback after a verified hit: a persist-side
                        # failure would kill the fetch leg identically, and the
                        # hard gate should see it rather than a silent re-download.
                        failure = _failure(f"reuse_{form}", exc)
                        form_result["failures"].append(failure)
                        ticker_failures.append(failure)
                        form_result["status"] = "partial"
                        form_result["manifest_keys"].append(declared_manifest_key)
                        continue
                    form_result["manifest_keys"].append(manifest_key)
                    form_result["stored_documents"] += 1
                    form_result["reused_documents"] += 1
                    ticker_reused_bytes += primary_bytes
                    total_reused_bytes += primary_bytes
                    # A reuse hit is still an observation.  Without this the log
                    # would be empty on the very path the lane runs, and "we
                    # looked, nothing changed" would go unrecorded.
                    if not _has_stored_primary(materialized):
                        outcome = "missing"
                    elif not known_accession:
                        outcome = "new_filing"
                    elif minted:
                        outcome = "new_content"
                    else:
                        outcome = "unchanged"
                    observations.append(
                        observe(
                            manifest=retained,
                            manifest_key=manifest_key,
                            outcome=outcome,
                            primary_verification="local_reuse",
                        )
                    )
                    continue
                available = min(
                    limits["max_document_bytes"],
                    limits["max_ticker_bytes"] - ticker_bytes,
                    limits["max_total_bytes"] - total_bytes,
                )
                if available < 1:
                    failure = {
                        "stage": f"fetch_{form}",
                        "error_type": "ByteBudgetExhausted",
                        "message": "bounded byte budget exhausted before primary-document fetch",
                    }
                    form_result["failures"].append(failure)
                    ticker_failures.append(failure)
                    form_result["status"] = "partial"
                    form_result["manifest_keys"].append(declared_manifest_key)
                    observations.append(
                        observe(
                            manifest=declared_manifest,
                            manifest_key=declared_manifest_key,
                            outcome="missing",
                            primary_verification=None,
                        )
                    )
                    break
                try:
                    # The nightly re-fetch and re-derivation are never skipped:
                    # tonight's freshly derived manifest is what goes to the
                    # network, never a reused stored one.  Dedupe is a persist
                    # decision only.
                    materialized = archive_collector.fetch_primary_document(
                        manifest,
                        retrieved_at=recorded,
                        max_document_bytes=available,
                    )
                    primary_bytes = _primary_byte_length(materialized)
                    if primary_bytes > available:
                        raise AcquisitionError("archive collector exceeded caller byte cap")
                    manifest_key, retained, minted = retain_filing_manifest(
                        archive_path, materialized
                    )
                    form_result["manifest_keys"].append(manifest_key)
                    if primary_bytes:
                        form_result["stored_documents"] += 1
                        ticker_bytes += primary_bytes
                        total_bytes += primary_bytes
                    else:
                        form_result["missing_documents"] += 1
                        form_result["status"] = "partial"
                    if not _has_stored_primary(materialized):
                        outcome = "missing"
                    elif not known_accession:
                        outcome = "new_filing"
                    elif minted:
                        outcome = "new_content"
                    else:
                        outcome = "unchanged"
                    observations.append(
                        observe(
                            manifest=retained,
                            manifest_key=manifest_key,
                            outcome=outcome,
                            primary_verification="network_refetch",
                        )
                    )
                except Exception as exc:
                    stage = f"fetch_{form}"
                    failure = _failure(stage, exc)
                    form_result["failures"].append(failure)
                    ticker_failures.append(failure)
                    form_result["status"] = "partial"
                    form_result["manifest_keys"].append(declared_manifest_key)
                    observations.append(
                        observe(
                            manifest=declared_manifest,
                            manifest_key=declared_manifest_key,
                            outcome="missing",
                            primary_verification=None,
                        )
                    )
                    # An explicit oversized source has no retry value and keeps
                    # the remaining selected document available for a later run.
                    if isinstance(exc, ArchiveResponseTooLarge):
                        continue
        receipt["bytes_retained"] = ticker_bytes
        receipt["bytes_reused"] = ticker_reused_bytes
        if ticker_failures or any(item["status"] != "complete" for item in receipt["forms"]):
            receipt["status"] = "partial"
        else:
            receipt["status"] = "complete"
        results.append(receipt)

    # One immutable object per run, carrying every field the retired
    # ``run.json`` held plus the explicit per-accession observations.  The
    # per-ticker receipts are folded in rather than written one file each
    # (R6), and the whole prefix now lives outside the restorable tree.
    run = {
        "schema": SEC_OBSERVATION_LOG_SCHEMA,
        "run_id": run_id,
        "as_of": cutoff,
        "recorded_at": recorded,
        "targets": [target.to_dict() for target in normalized_targets],
        "limits": dict(limits),
        "bytes_retained": total_bytes,
        "bytes_reused": total_reused_bytes,
        "reuse_local_archive": bool(reuse_local_archive),
        "status": "complete" if all(item["status"] == "complete" for item in results) else "partial",
        "ticker_receipts": results,
        "observations": observations,
    }
    _write_observation_log(observation_path, run)
    return run


__all__ = [
    "ACQUISITION_RUN_SCHEMA",
    "ACQUISITION_TICKER_SCHEMA",
    "AcquisitionError",
    "AcquisitionTarget",
    "DEFAULT_MAX_DOCUMENT_BYTES",
    "DEFAULT_MAX_SUBMISSIONS_BYTES",
    "DEFAULT_MAX_TICKER_BYTES",
    "DEFAULT_MAX_TICKERS",
    "DEFAULT_MAX_TOTAL_BYTES",
    "FORM_FAMILIES",
    "OBSERVATION_OUTCOMES",
    "OBSERVATION_RELATIVE_ROOT",
    "SEC_OBSERVATION_LOG_SCHEMA",
    "acquire_bounded_filings",
    "normalize_targets",
    "observation_log_path",
    "parse_target",
    "read_verified_submissions",
]
