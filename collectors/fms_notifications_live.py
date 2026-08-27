"""Live acquisition adapter for the FMS congressional-notification rail.

Supplies what ``collectors/fms_notifications.py`` deliberately leaves out:
network fetches (State listing + articles by CLI, Federal Register API +
raw-text sweep by CLI), the DSCA bounded browser-transport archival replay
(staged bytes committed at ``data/government_revenue/fms_staged_objects/``),
the immutable R2 object store put+verify, and the CLI that runs the whole
chain and durably writes the receipt-bound triad plus the derived read
model.

Mirrors ``collectors/dod_budget_live.py``'s order-is-law discipline (D6-A
design): fetch -> sha256 -> (store put -> strict bounded readback) only for
bytes destined for the immutable store -> receipt -> observation. There is no
fail-open local-store fallback anywhere in this module's production path.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import urlsplit

from collectors import fms_notifications as fms
from engine.government_revenue import fms_cases
from engine.research_vault.r2_store import BoundedStrictReadStore, R2Store, Store

# ---------------------------------------------------------------------------
# Frozen source constants (spec §2/§3; URLs live in code, never CLI args).
# ---------------------------------------------------------------------------

STATE_HOST = "www.state.gov"
FR_HOST = "www.federalregister.gov"
STATE_LISTING_URL = "https://www.state.gov/arms-sales-congressional-notifications"
FR_API_DOCUMENTS_URL = "https://www.federalregister.gov/api/v1/documents.json"

FR_STATE_PUBLISHER = "U.S. Department of State, Bureau of Political-Military Affairs"
DSCA_PUBLISHER = "Defense Security Cooperation Agency"
FR_PUBLISHER = "Federal Register / Government Publishing Office"

FMS_STATE_EXTRACTOR_VERSION = "fms-state-html.v1"
FMS_STATE_PARSER_VERSION = "fms-state-parser.v1"
FMS_DSCA_EXTRACTOR_VERSION = "fms-dsca-html.v1"
FMS_DSCA_PARSER_VERSION = "fms-dsca-parser.v1"
FMS_FR_EXTRACTOR_VERSION = "fms-fr-rawtext.v1"
FMS_FR_PARSER_VERSION = "fms-fr-parser.v1"

FETCH_TIMEOUT_SECONDS = 60.0
MAX_FETCH_BYTES = 8 * 1024 * 1024  # 8 MiB — HTML/text/PDF notices are small
_FETCH_CHUNK_BYTES = 256 * 1024

_TRIAD_RECEIPTS_FILENAME = "fms_collection_receipts.jsonl"
_TRIAD_OBSERVATIONS_FILENAME = "fms_observations.jsonl"
_TRIAD_STATE_FILENAME = "fms_projection_state.json"
_CASE_GRAPH_FILENAME = "fms_case_graph.json"
_STAGED_OBJECTS_DIRNAME = "fms_staged_objects"


class FmsFetchRefused(RuntimeError):
    """One acquisition fetch failed a hermetic fail-closed check."""


class FmsStoreUnavailable(RuntimeError):
    """No object store could be resolved; acquisition refuses without a receipt."""


class FmsStoreWriteFailed(RuntimeError):
    """The object store rejected (or raised on) the write."""


class FmsStoreReadbackFailed(RuntimeError):
    """The strict bounded readback did not return the exact written bytes."""


class FmsStagedIntegrityFailed(RuntimeError):
    """A staged DSCA file's bytes did not match its manifest sha256 (B10)."""


@dataclass(frozen=True)
class FetchedResource:
    source_url: str
    final_url: str
    content: bytes
    sha256: str
    content_type: str
    http_status: int


# ---------------------------------------------------------------------------
# Fetch discipline (D6-A §3.4: allowlisted hosts, no cross-host/any redirect,
# size caps, content-type checks)
# ---------------------------------------------------------------------------


def _checked_https_url(url: str, *, allowed_hosts: Sequence[str]) -> str:
    parsed = urlsplit(str(url or "").strip())
    if (
        parsed.scheme.lower() != "https"
        or not parsed.hostname
        or parsed.hostname.lower() not in {h.lower() for h in allowed_hosts}
        or parsed.username
        or parsed.password
    ):
        raise FmsFetchRefused(f"FMS source URL is not an allowlisted official HTTPS URL: {url!r}")
    return str(url)


def fetch_official_resource(
    url: str,
    *,
    allowed_hosts: Sequence[str],
    expected_content_types: Sequence[str] | None = None,
    session: Any = None,
    timeout: float = FETCH_TIMEOUT_SECONDS,
    max_bytes: int = MAX_FETCH_BYTES,
) -> FetchedResource:
    """GET one allowlisted official resource with every hostile check fail-closed.

    No redirects are followed across ANY host — the response must be a
    direct 200. The body is streamed under a hard byte cap.
    """
    checked_url = _checked_https_url(url, allowed_hosts=allowed_hosts)
    transport = session
    if transport is None:
        import requests as _requests

        transport = _requests
    try:
        response = transport.get(
            checked_url, timeout=timeout, allow_redirects=False, stream=True, verify=True,
        )
    except Exception as exc:  # noqa: BLE001 - any transport failure is a refusal
        raise FmsFetchRefused(f"FMS resource fetch failed: {exc}") from exc
    try:
        status = getattr(response, "status_code", None)
        if isinstance(status, bool) or not isinstance(status, int):
            raise FmsFetchRefused("FMS resource fetch returned no usable status code")
        if 300 <= status < 400:
            raise FmsFetchRefused(f"FMS resource fetch refused a redirect (status {status})")
        if status != 200:
            raise FmsFetchRefused(f"FMS resource fetch returned status {status}")
        final_url = str(getattr(response, "url", None) or checked_url)
        _checked_https_url(final_url, allowed_hosts=allowed_hosts)
        content_type = str(response.headers.get("Content-Type", "")).split(";")[0].strip().lower()
        if expected_content_types and content_type not in expected_content_types:
            raise FmsFetchRefused(
                f"FMS resource fetch returned unexpected content-type {content_type!r}"
            )
        chunks: list[bytes] = []
        total = 0
        iter_content = getattr(response, "iter_content", None)
        if not callable(iter_content):
            raise FmsFetchRefused("FMS resource fetch response cannot be streamed")
        for chunk in iter_content(chunk_size=_FETCH_CHUNK_BYTES):
            if not chunk:
                continue
            if not isinstance(chunk, bytes):
                raise FmsFetchRefused("FMS resource fetch returned a non-bytes chunk")
            total += len(chunk)
            if total > max_bytes:
                raise FmsFetchRefused(f"FMS resource exceeds the {max_bytes}-byte acquisition cap")
            chunks.append(chunk)
        content = b"".join(chunks)
    finally:
        close = getattr(response, "close", None)
        if callable(close):
            close()
    digest = fms._sha256(content)
    return FetchedResource(
        source_url=checked_url, final_url=final_url, content=content,
        sha256=digest, content_type=content_type, http_status=status,
    )


# ---------------------------------------------------------------------------
# Immutable object store (generalizes dod_budget_live.put_and_verify_pdf to
# html/pdf/txt; PDF still requires the %PDF magic, spec §3).
# ---------------------------------------------------------------------------

_CONTENT_TYPE_BY_EXT = {"html": "text/html", "pdf": "application/pdf", "txt": "text/plain"}


def immutable_object_key(content: bytes, *, ext: str) -> str:
    if ext not in _CONTENT_TYPE_BY_EXT:
        raise ValueError(f"unsupported FMS immutable object extension: {ext!r}")
    if ext == "pdf" and not content.startswith(b"%PDF"):
        raise ValueError("FMS PDF object is not a %PDF byte stream")
    digest = fms._sha256(content)
    return f"{fms.IMMUTABLE_R2_PREFIX}{digest}.{ext}"


def put_and_verify_object(store: Store, content: bytes, *, ext: str, max_bytes: int = MAX_FETCH_BYTES) -> str:
    """PUT one object and require an exact strict-bounded readback before trusting it."""
    key = immutable_object_key(content, ext=ext)
    if max_bytes < len(content):
        raise ValueError("FMS store byte cap must cover the exact object length")
    try:
        wrote = store.put_bytes(key, content, content_type=_CONTENT_TYPE_BY_EXT[ext])
    except Exception as exc:  # noqa: BLE001 - a raising backend is still a refusal
        raise FmsStoreWriteFailed(f"FMS object write raised: {exc}") from exc
    if not wrote:
        raise FmsStoreWriteFailed("FMS object store rejected the write")
    if not isinstance(store, BoundedStrictReadStore):
        raise FmsStoreUnavailable("FMS object store lacks bounded strict-read capability")
    try:
        readback = store.get_bytes_strict_bounded(
            key, expected_byte_length=len(content), max_byte_length=max_bytes,
        )
    except Exception as exc:  # noqa: BLE001 - no fail-open readback fallback
        raise FmsStoreReadbackFailed(f"FMS object readback raised: {exc}") from exc
    if not isinstance(readback, bytes) or readback != content or fms._sha256(readback) != fms._sha256(content):
        raise FmsStoreReadbackFailed("FMS object readback did not match the written bytes")
    return key


def _r2_client():
    endpoint = os.environ.get("R2_ENDPOINT")
    access_key = os.environ.get("R2_ACCESS_KEY_ID")
    secret_key = os.environ.get("R2_SECRET_ACCESS_KEY")
    if not (endpoint and access_key and secret_key):
        return None
    import boto3
    from botocore.config import Config

    config = Config(
        region_name="auto", signature_version="s3v4", max_pool_connections=8,
        retries={"max_attempts": 5, "mode": "adaptive"}, connect_timeout=15, read_timeout=120,
    )
    return boto3.client(
        "s3", endpoint_url=endpoint, aws_access_key_id=access_key,
        aws_secret_access_key=secret_key, config=config,
    )


def build_default_store() -> Store | None:
    """Resolve the production immutable R2 store; never a local fallback.

    A ``LocalStore`` is reachable only through an explicit ``store``
    argument a caller (a test) passes directly — never selected from the
    environment here (mirrors ``dod_budget_live.build_default_store``).
    """
    bucket = os.environ.get("R2_BUCKET")
    if not bucket:
        return None
    store = R2Store(bucket, client=_r2_client())
    return store if store.available else None


# ---------------------------------------------------------------------------
# DSCA bounded browser-transport archival replay (spec §3.4/§8: refuse any
# staged file whose bytes do not match its manifest sha256; never fetch
# dsca.mil live).
# ---------------------------------------------------------------------------


def load_staged_dsca_manifest(staged_dir: Path) -> dict[str, Any]:
    manifest_path = staged_dir / "manifest.json"
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def verify_staged_bytes(staged_dir: Path, *, local_path: str, expected_sha256: str) -> bytes:
    """Read one staged file and refuse if its bytes don't match the manifest sha256.

    ``local_path`` in the manifest is repo-root-relative by convention, but
    the staged file always lives directly inside ``staged_dir`` — resolve by
    basename against ``staged_dir`` so this works identically whether
    ``staged_dir`` is the real committed
    ``data/government_revenue/fms_staged_objects/`` or a sparse-safe test
    fixture directory carrying a trimmed manifest.
    """
    candidate = Path(local_path)
    full_path = candidate if candidate.is_absolute() and candidate.is_file() else staged_dir / candidate.name
    if not full_path.is_file():
        raise FmsStagedIntegrityFailed(f"staged DSCA file not found: {local_path!r}")
    content = full_path.read_bytes()
    actual = fms._sha256(content)
    if actual != expected_sha256:
        raise FmsStagedIntegrityFailed(
            f"staged DSCA file {local_path!r} sha256 mismatch: expected {expected_sha256}, got {actual}"
        )
    return content


def replay_staged_dsca_objects(
    staged_dir: Path, *, store: Store | None, observed_at: str | datetime,
) -> list[dict[str, Any]]:
    """Verify + (if a store is given) durably replay every staged DSCA object into R2.

    Returns one receipt per staged article (``certification_pdf`` handled
    separately by the caller, since it attaches to the article's case, not
    its own). Every staged file is integrity-checked BEFORE any store write
    (B10); a store write additionally requires strict-bounded readback
    equality before its receipt records an ``r2_object_key`` (B11).
    """
    manifest = load_staged_dsca_manifest(staged_dir)
    receipts: list[dict[str, Any]] = []
    for article in manifest.get("articles", []):
        content = verify_staged_bytes(
            staged_dir, local_path=article["local_path"], expected_sha256=article["sha256"],
        )
        r2_key = None
        if store is not None:
            r2_key = put_and_verify_object(store, content, ext="html")
        receipt = fms.build_receipt(
            source_url=article["url"], final_url=article.get("final_url", article["url"]),
            content=content, publisher=DSCA_PUBLISHER,
            transport="browser_in_page_fetch_staged", content_type="text/html",
            http_status=int(article.get("http_status", 200)), observed_at=observed_at,
            extractor_version=FMS_DSCA_EXTRACTOR_VERSION, parser_version=FMS_DSCA_PARSER_VERSION,
            r2_object_key=r2_key,
        )
        receipts.append(receipt)
    return receipts


def replay_staged_certification_pdf(
    staged_dir: Path, *, store: Store | None, observed_at: str | datetime,
) -> dict[str, Any]:
    manifest = load_staged_dsca_manifest(staged_dir)
    pdf = manifest["certification_pdf"]
    content = verify_staged_bytes(staged_dir, local_path=pdf["local_path"], expected_sha256=pdf["sha256"])
    if not content.startswith(b"%PDF"):
        raise FmsStagedIntegrityFailed("staged DSCA certification PDF is not a %PDF byte stream")
    r2_key = None
    if store is not None:
        r2_key = put_and_verify_object(store, content, ext="pdf")
    return fms.build_receipt(
        source_url=pdf["url"], final_url=pdf.get("final_url", pdf["url"]), content=content,
        publisher=DSCA_PUBLISHER, transport="browser_in_page_fetch_staged",
        content_type="application/pdf", http_status=int(pdf.get("http_status", 200)),
        observed_at=observed_at, extractor_version=FMS_DSCA_EXTRACTOR_VERSION,
        parser_version=FMS_DSCA_PARSER_VERSION, r2_object_key=r2_key,
    )


# ---------------------------------------------------------------------------
# State PM-Bureau listing + article CLI acquisition
# ---------------------------------------------------------------------------


def fetch_state_listing_page(page: int, *, session: Any = None) -> FetchedResource:
    url = STATE_LISTING_URL if page <= 1 else f"{STATE_LISTING_URL}/page/{page}/"
    return fetch_official_resource(
        url, allowed_hosts=(STATE_HOST,), expected_content_types=("text/html",), session=session,
    )


def fetch_state_article(url: str, *, session: Any = None) -> FetchedResource:
    return fetch_official_resource(
        url, allowed_hosts=(STATE_HOST,), expected_content_types=("text/html",), session=session,
    )


def sweep_state_qualifying_articles(
    *, session: Any = None, max_pages: int = 20,
) -> tuple[list[dict[str, Any]], int]:
    """Paginate the State listing; return (qualifying entries, pages fetched).

    An empty page is the ONLY lawful "the listing is exhausted" signal
    (spec §11b.4/§11b.6: a successful listing fetch+parse that finds zero
    qualifying entries on its final page is the ``empty_valid`` state, never
    a failure). Reaching ``max_pages`` while the last fetched page STILL had
    entries means coverage cannot be confirmed complete -- this is a typed
    failure (``FmsFetchRefused``), never a silent "ok" that quietly drops
    every page beyond the cap.
    """
    entries: list[dict[str, Any]] = []
    pages_fetched = 0
    for page in range(1, max_pages + 1):
        fetched = fetch_state_listing_page(page, session=session)
        pages_fetched += 1
        page_entries = fms.parse_state_listing(fetched.content.decode("utf-8", errors="replace"))
        if not page_entries:
            return entries, pages_fetched
        entries.extend(entry for entry in page_entries if entry["is_qualifying"])
    raise FmsFetchRefused(
        f"FMS State listing sweep reached the {max_pages}-page cap while page {max_pages} "
        "still had entries -- coverage cannot be confirmed complete"
    )


# ---------------------------------------------------------------------------
# State PM-Bureau STAGED replay (production amendment §6b, 2026-08-26)
#
# The first production dispatch (run 32952963771) proved the live CLI leg
# blind from a hosted runner: the same listing URL that presents 11
# qualifying articles to a residential fetch served the datacenter runner
# bytes that parse to ZERO, and the empty_valid law then published
# `status: ok, qualifying_articles: 0` with no byte receipt. In CI the
# State family therefore acquires exactly like DSCA: sha-frozen staged
# bytes captured from a residential CLI (`stage-state` below), replayed
# with R2 put + strict readback. A staged listing that parses to zero
# qualifying entries is a STAGING ERROR and refuses -- the ok-with-zero
# hole is closed; "the surface really is empty" must be proven by staging
# the listing bytes that show it, and those bytes then fail the
# >=1-qualifying check only when genuinely empty, which flips this refusal
# into the one deliberate exception below.
# ---------------------------------------------------------------------------

STATE_STAGED_MANIFEST_NAME = "state_manifest.json"
STATE_STAGED_TRANSPORT = "cli_residential_staged"
# The capture UA is part of the staging tool's provenance (recorded in the
# manifest): state.gov's edge serves the python-requests default UA a
# challenge page that parses to zero entries even from a residential
# network, while a mainstream desktop UA receives the real listing. The
# production path never uses this -- CI replays the sha-frozen bytes.
STATE_CAPTURE_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/127.0 Safari/537.36"
)


def load_staged_state_manifest(staged_dir: Path) -> dict[str, Any]:
    manifest_path = staged_dir / STATE_STAGED_MANIFEST_NAME
    if not manifest_path.is_file():
        raise FmsStagedIntegrityFailed(
            f"staged State manifest not found: {manifest_path} -- run "
            "`python3 -m collectors.fms_notifications_live stage-state` from a "
            "residential network and commit the capture"
        )
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def replay_staged_state_objects(
    staged_dir: Path, *, store: Store | None, observed_at: str | datetime,
) -> tuple[list[tuple[dict[str, Any], dict[str, Any], str]], int]:
    """Verify + durably replay the staged State capture.

    Returns ``([(receipt, parsed_fields, source_url), ...], listing_pages)``.
    Refusals (all ``FmsStagedIntegrityFailed``): missing manifest, any sha
    mismatch, a staged listing that parses to zero qualifying entries, or a
    listing entry with no staged article bytes (an incomplete capture would
    silently shrink the presented surface).
    """
    manifest = load_staged_state_manifest(staged_dir)
    listing = manifest["listing"]
    listing_bytes = verify_staged_bytes(
        staged_dir, local_path=listing["local_path"], expected_sha256=listing["sha256"],
    )
    entries = fms.parse_state_listing(listing_bytes.decode("utf-8", errors="replace"))
    qualifying = [entry for entry in entries if entry["is_qualifying"]]
    if not qualifying:
        raise FmsStagedIntegrityFailed(
            "staged State listing parses to zero qualifying entries -- an empty "
            "staged capture is a staging error, never a publishable empty surface"
        )
    staged_by_url = {article["url"]: article for article in manifest.get("articles", [])}
    missing = [e["source_url"] for e in qualifying if e["source_url"] not in staged_by_url]
    if missing:
        raise FmsStagedIntegrityFailed(
            f"staged State capture is incomplete -- listing presents {len(missing)} "
            f"qualifying article(s) with no staged bytes: {missing[:3]}"
        )
    pairs: list[tuple[dict[str, Any], dict[str, Any], str]] = []
    for entry in qualifying:
        article = staged_by_url[entry["source_url"]]
        content = verify_staged_bytes(
            staged_dir, local_path=article["local_path"], expected_sha256=article["sha256"],
        )
        fields = fms.parse_state_article(
            content.decode("utf-8", errors="replace"), source_url=article["url"],
        )
        r2_key = None
        if store is not None:
            r2_key = put_and_verify_object(store, content, ext="html")
        receipt = fms.build_receipt(
            source_url=article["url"], final_url=article.get("final_url", article["url"]),
            content=content, publisher=FR_STATE_PUBLISHER, transport=STATE_STAGED_TRANSPORT,
            content_type="text/html", http_status=int(article.get("http_status", 200)),
            observed_at=observed_at, extractor_version=FMS_STATE_EXTRACTOR_VERSION,
            parser_version=FMS_STATE_PARSER_VERSION, r2_object_key=r2_key,
        )
        pairs.append((receipt, fields, article["url"]))
    return pairs, 1


def stage_state(argv: list[str] | None = None) -> int:
    """Capture the live State presentation into the staged-objects dir.

    Run from a RESIDENTIAL network (the Mac), never from CI: fetches the
    listing plus every qualifying article over the ordinary CLI transport,
    writes their bytes next to the DSCA staged objects, and rewrites
    ``state_manifest.json`` with per-file sha256s. Refuses to stage a
    capture whose listing parses to zero qualifying entries.
    """
    parser = argparse.ArgumentParser(prog="fms-stage-state")
    parser.add_argument(
        "--staged-dir",
        default="data/government_revenue/fms_staged_objects",
        help="directory holding the committed staged objects + manifests",
    )
    args = parser.parse_args(argv)
    staged_dir = Path(args.staged_dir).resolve()
    staged_dir.mkdir(parents=True, exist_ok=True)

    import requests as _requests

    capture_session = _requests.Session()
    capture_session.headers.update({
        "User-Agent": STATE_CAPTURE_USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    })
    captured_at = datetime.now(timezone.utc).isoformat()
    listing_fetched = fetch_state_listing_page(1, session=capture_session)
    entries = fms.parse_state_listing(listing_fetched.content.decode("utf-8", errors="replace"))
    qualifying = [entry for entry in entries if entry["is_qualifying"]]
    if not qualifying:
        print(
            "::error title=fms-stage-state::live State listing parsed to zero "
            "qualifying entries -- refusing to stage an empty capture",
            flush=True,
        )
        return 1
    listing_name = "state-listing.html"
    (staged_dir / listing_name).write_bytes(listing_fetched.content)
    manifest: dict[str, Any] = {
        "kind": "fms_state_staged_v1",
        "captured_at": captured_at,
        "transport": "cli_residential",
        "user_agent": STATE_CAPTURE_USER_AGENT,
        "listing": {
            "url": listing_fetched.source_url,
            "final_url": listing_fetched.final_url,
            "http_status": listing_fetched.http_status,
            "local_path": listing_name,
            "sha256": hashlib.sha256(listing_fetched.content).hexdigest(),
        },
        "articles": [],
    }
    for entry in qualifying:
        fetched = fetch_state_article(entry["source_url"], session=capture_session)
        slug = entry["source_url"].rstrip("/").rsplit("/", 1)[-1][:80] or "article"
        local_name = f"state-{slug}.html"
        (staged_dir / local_name).write_bytes(fetched.content)
        manifest["articles"].append({
            "url": entry["source_url"],
            "final_url": fetched.final_url,
            "http_status": fetched.http_status,
            "local_path": local_name,
            "sha256": hashlib.sha256(fetched.content).hexdigest(),
        })
        print(f"staged {local_name} ({len(fetched.content)} bytes)", flush=True)
    manifest_path = staged_dir / STATE_STAGED_MANIFEST_NAME
    manifest_path.write_text(
        json.dumps(manifest, indent=1, sort_keys=True) + "\n", encoding="utf-8",
    )
    print(
        f"staged State capture: {len(manifest['articles'])} article(s) + listing "
        f"-> {manifest_path}",
        flush=True,
    )
    return 0


# ---------------------------------------------------------------------------
# Federal Register API sweep + raw-text fetch
# ---------------------------------------------------------------------------


def fetch_fr_document_index(
    *, publication_from: str, publication_through: str, session: Any = None, per_page: int = 1000,
) -> dict[str, Any]:
    """Query the FR API for in-window Defense-Department Arms Sales Notification NOTICEs."""
    params = {
        "conditions[term]": "arms sales notification",
        "conditions[agencies][]": "defense-department",
        "conditions[type][]": "NOTICE",
        "conditions[publication_date][gte]": publication_from,
        "conditions[publication_date][lte]": publication_through,
        "per_page": per_page,
        "fields[]": ["document_number", "raw_text_url", "publication_date", "title", "citation"],
    }
    transport = session
    if transport is None:
        import requests as _requests

        transport = _requests
    response = transport.get(FR_API_DOCUMENTS_URL, params=params, timeout=FETCH_TIMEOUT_SECONDS)
    status = getattr(response, "status_code", None)
    if status != 200:
        raise FmsFetchRefused(f"FR API document index returned status {status}")
    return response.json()


def fetch_fr_raw_text(url: str, *, session: Any = None) -> FetchedResource:
    return fetch_official_resource(
        url, allowed_hosts=(FR_HOST,), expected_content_types=("text/plain",), session=session,
    )


# ---------------------------------------------------------------------------
# Triad I/O (atomic writes, append-only)
# ---------------------------------------------------------------------------


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    temp_path = Path(temp_name)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_path, path)
    except BaseException:
        temp_path.unlink(missing_ok=True)
        raise


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = raw.strip()
        if not stripped:
            continue
        value = json.loads(stripped)
        if not isinstance(value, dict):
            raise ValueError(f"{path}:{number} is not a JSON object")
        rows.append(value)
    return rows


def _write_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    raw = "\n".join(json.dumps(row, sort_keys=True, separators=(",", ":")) for row in rows)
    _atomic_write_text(path, raw + ("\n" if rows else ""))


# ---------------------------------------------------------------------------
# CLI acquisition orchestrator
# ---------------------------------------------------------------------------


def _append_new_receipt(
    new_receipts: list[dict[str, Any]],
    existing_receipts: Sequence[Mapping[str, Any]],
    receipt: Mapping[str, Any],
) -> None:
    """Append ``receipt`` only if it is not a same-URL-same-bytes duplicate.

    Mirrors ``dod_budget_live.acquire_official_document``'s
    ``receipt_is_duplicate`` discipline (spec §11b.3): the receipt's own
    identity folds ``observed_at`` (always fresh per run), so an unguarded
    append would double the receipts plane on every re-run regardless of
    whether the underlying bytes changed. Consulting the timestamp-free
    predicate BEFORE appending is what makes a re-run over unchanged bytes a
    genuine no-op on the receipts file.
    """
    if not fms.receipt_is_duplicate(existing_receipts, receipt):
        new_receipts.append(dict(receipt))


def run_fms_acquisition(
    *,
    root: Path,
    store: Store | None,
    session: Any = None,
    observed_at: str | datetime | None = None,
    staged_dir: Path | None = None,
    publication_from: str = "2026-01-01",
    publication_through: str | None = None,
) -> int:
    """Acquire State + FR + DSCA-staged evidence, then rebuild the read model.

    All-or-nothing at the triad level: any refusal writes NOTHING (the
    previously-committed triad, if any, is left byte-for-byte untouched).
    """
    if observed_at is None:
        observed_at = datetime.now(timezone.utc)
    as_of = date.today().isoformat()
    if publication_through is None:
        publication_through = as_of
    if staged_dir is None:
        staged_dir = root / "data" / "government_revenue" / _STAGED_OBJECTS_DIRNAME

    data_dir = root / "data" / "government_revenue"
    receipts_path = data_dir / _TRIAD_RECEIPTS_FILENAME
    observations_path = data_dir / _TRIAD_OBSERVATIONS_FILENAME
    state_path = data_dir / _TRIAD_STATE_FILENAME
    graph_path = data_dir / _CASE_GRAPH_FILENAME

    try:
        existing_receipts = _read_jsonl(receipts_path)
        existing_observations = _read_jsonl(observations_path)
    except (OSError, ValueError) as exc:
        print(f"::error title=fms-existing-triad-unreadable::{exc}", flush=True)
        return 1

    new_receipts: list[dict[str, Any]] = []
    new_observations: list[dict[str, Any]] = []
    fr_denominator: list[str] = []
    fr_docs_scanned = 0
    fr_amendments_excluded = 0
    fr_corrections = 0
    fr_out_of_scope_originals = 0
    fr_status = "unavailable"
    state_status = "unavailable"
    state_listing_pages = 0
    state_qualifying_articles = 0
    state_articles_succeeded = 0
    state_articles_failed = 0
    dsca_status = "unavailable"
    dsca_articles_staged = 0

    # --- DSCA staged replay (never fetched live) ---
    try:
        dsca_receipts = replay_staged_dsca_objects(staged_dir, store=store, observed_at=observed_at)
        manifest = load_staged_dsca_manifest(staged_dir)
        dsca_articles_staged = len(manifest.get("articles", []))
        for article, receipt in zip(manifest.get("articles", []), dsca_receipts):
            content = verify_staged_bytes(staged_dir, local_path=article["local_path"], expected_sha256=article["sha256"])
            fields = fms.parse_dsca_article(content.decode("utf-8", errors="replace"), source_url=article["url"])
            if fields["transmittal_number"] is None:
                continue
            case_key = fms.case_key_for_transmittal(fields["transmittal_number"])
            _append_new_receipt(new_receipts, existing_receipts, receipt)
            new_observations.append(fms.build_observation(
                case_key=case_key, source_surface="dsca", kind="listing_article",
                receipt=receipt, known_at=observed_at, version=1, fields=fields,
            ))
        # Canary A's certification PDF (freeze §15.1/§3.4 receipt R3): same
        # staged-replay -> R2 put+strict-readback -> receipt discipline as
        # the articles, attached to its own case by the manifest's own
        # "transmittal" field (never re-derived by parsing the PDF).
        cert_manifest = manifest.get("certification_pdf")
        if cert_manifest is not None:
            cert_receipt = replay_staged_certification_pdf(staged_dir, store=store, observed_at=observed_at)
            cert_transmittal = fms.normalize_transmittal(
                *cert_manifest["transmittal"].split("-", 1)
            )
            cert_case_key = fms.case_key_for_transmittal(cert_transmittal)
            _append_new_receipt(new_receipts, existing_receipts, cert_receipt)
            new_observations.append(fms.build_observation(
                case_key=cert_case_key, source_surface="dsca", kind="certification_pdf",
                receipt=cert_receipt, known_at=observed_at, version=1,
                fields={"transmittal_number": cert_transmittal},
            ))
        dsca_status = "ok"
    except (FmsStagedIntegrityFailed, OSError, ValueError) as exc:
        print(f"::error title=fms-dsca-staged-refused::{exc}", flush=True)
        return 1

    # --- State STAGED replay (production amendment §6b, 2026-08-26) ---
    # The live CLI sweep proved blind from a hosted runner (run 32952963771:
    # the listing that presents 11 qualifying articles to a residential
    # fetch parsed to ZERO from the datacenter, and empty_valid published
    # `ok` with no byte receipt). CI replays the sha-frozen residential
    # capture instead -- same fail-closed discipline as the DSCA leg; the
    # live sweep survives only inside the `stage-state` capture CLI.
    try:
        state_pairs, state_listing_pages = replay_staged_state_objects(
            staged_dir, store=store, observed_at=observed_at,
        )
        state_qualifying_articles = len(state_pairs)
        for receipt, fields, source_url in state_pairs:
            case_key = (
                fms.case_key_for_transmittal(fields["transmittal_number"])
                if fields["transmittal_number"] and not fields["identity_conflicted"]
                else fms.case_key_fallback(source_url)
            )
            state_articles_succeeded += 1
            _append_new_receipt(new_receipts, existing_receipts, receipt)
            new_observations.append(fms.build_observation(
                case_key=case_key, source_surface="state", kind="listing_article",
                receipt=receipt, known_at=observed_at, version=1, fields=fields,
            ))
        state_status = "ok"
    except (FmsStagedIntegrityFailed, OSError, ValueError) as exc:
        print(f"::error title=fms-state-staged-refused::{exc}", flush=True)
        return 1

    # --- Federal Register sweep ---
    try:
        index = fetch_fr_document_index(
            publication_from=publication_from, publication_through=publication_through, session=session,
        )
        results = index.get("results", [])
        fr_docs_scanned = len(results)
        for row in results:
            fetched = fetch_fr_raw_text(row["raw_text_url"], session=session)
            text = fetched.content.decode("utf-8", errors="replace")
            classification = fms.classify_fr_document(text)
            receipt = fms.build_receipt(
                source_url=fetched.source_url, final_url=fetched.final_url, content=fetched.content,
                publisher=FR_PUBLISHER, transport="cli", content_type=fetched.content_type,
                http_status=fetched.http_status, observed_at=observed_at,
                extractor_version=FMS_FR_EXTRACTOR_VERSION, parser_version=FMS_FR_PARSER_VERSION,
                r2_object_key=None,
            )
            if classification["classification"] == "amendment":
                fr_amendments_excluded += 1
                continue
            if classification["classification"] == "correction":
                bracket = classification["bracket"]
                if not fms._ORIGINAL_BRACKET_RE.fullmatch(bracket):
                    # A correction whose OWN bracket fails the numeric
                    # original grammar (26-1C, 0M-25 family, spec §11b.9) can
                    # never resolve a target transmittal to correct -- it is
                    # excluded with a typed reason exactly like an amendment
                    # notice, never a crash on the malformed bracket.
                    fr_amendments_excluded += 1
                    print(
                        f"::warning title=fms-fr-correction-bracket-non-numeric::correction "
                        f"bracket {bracket!r} is not a numeric original transmittal; excluded",
                        flush=True,
                    )
                    continue
                fr_corrections += 1
                # A correction's own bracket IS the transmittal it corrects.
                year, seq = bracket.split("-", 1)
                target_transmittal = fms.normalize_transmittal(year, seq)
                case_key = fms.case_key_for_transmittal(target_transmittal)
                _append_new_receipt(new_receipts, existing_receipts, receipt)
                new_observations.append(fms.build_observation(
                    case_key=case_key, source_surface="federal_register", kind="fr_correction",
                    receipt=receipt, known_at=observed_at, version=1,
                    fields={"classification": "correction", "bracket": bracket},
                ))
                continue
            fields = fms.parse_fr_document(text, source_url=fetched.source_url)
            # Shared membership predicate (spec §2/§11b.4): the denominator
            # and the engine's population filter must agree on the SAME
            # test -- an original DELIVERED outside [population start,
            # as_of] (the FR-lag class: published in the query window but
            # delivered to Congress before 2026-01-01) is never added to
            # the denominator and never mints anything, exactly like the
            # engine already excludes its case from the graph. Counting it
            # separately in the denominator while the engine dropped its
            # case is what produced `denominator_unbuilt` and a false
            # `FmsCoverageRefused` on the first real production run.
            delivered = fields.get("official_notification_date")
            if delivered is None:
                fr_out_of_scope_originals += 1
                print(
                    "::warning title=fms-fr-original-no-delivered-date::FR original "
                    f"{fields.get('transmittal_number')!r} has no parseable delivered-to-Congress "
                    "date; excluded from the denominator (cannot prove population-window membership)",
                    flush=True,
                )
                continue
            if not (fms_cases.FMS_POPULATION_WINDOW_START <= delivered <= as_of):
                fr_out_of_scope_originals += 1
                print(
                    "::warning title=fms-fr-original-out-of-scope::FR original "
                    f"{fields.get('transmittal_number')!r} delivered {delivered} falls outside the "
                    f"population window [{fms_cases.FMS_POPULATION_WINDOW_START}, {as_of}]; "
                    "excluded from the denominator",
                    flush=True,
                )
                continue
            fr_denominator.append(fields["transmittal_number"])
            case_key = fms.case_key_for_transmittal(fields["transmittal_number"])
            _append_new_receipt(new_receipts, existing_receipts, receipt)
            new_observations.append(fms.build_observation(
                case_key=case_key, source_surface="federal_register", kind="fr_raw_text",
                receipt=receipt, known_at=observed_at, version=1, fields=fields,
            ))
        fr_status = "ok"
    except FmsFetchRefused as exc:
        print(f"::error title=fms-fr-source-unavailable::{exc}", flush=True)
        return 1

    try:
        merged_receipts = fms.merge_receipts(existing_receipts, new_receipts)
        merged_observations = fms.append_observation_versions(existing_observations, new_observations)
        state = {
            "contract": "government_revenue.fms_projection_state.v1",
            "schema_version": fms.SCHEMA_VERSION,
            "receipt_count": len(merged_receipts),
            "observation_count": len(merged_observations),
            "generated_at": fms._utc_iso(observed_at),
        }
    except ValueError as exc:
        print(f"::error title=fms-triad-assembly-refused::{exc}", flush=True)
        return 1

    try:
        graph = fms_cases.build_fms_case_graph(
            observations=merged_observations,
            as_of=as_of,
            # scope is the POPULATION window (spec §11b.4): a fixed v1 start
            # date through today, NEVER the FR publication-query bounds
            # below -- those describe only what the FR API sweep asked for
            # and live exclusively in coverage.sources.federal_register.
            scope_delivered_from=fms_cases.FMS_POPULATION_WINDOW_START,
            scope_delivered_through=as_of,
            fr_publication_from=publication_from,
            fr_publication_through=publication_through,
            fr_denominator_transmittals=fr_denominator,
            fr_docs_scanned=fr_docs_scanned,
            fr_amendments_excluded=fr_amendments_excluded,
            fr_corrections=fr_corrections,
            fr_out_of_scope_originals=fr_out_of_scope_originals,
            fr_status=fr_status,
            state_listing_pages=state_listing_pages,
            state_qualifying_articles=state_qualifying_articles,
            state_status=state_status,
            state_articles_succeeded=state_articles_succeeded,
            state_articles_failed=state_articles_failed,
            dsca_articles_staged=dsca_articles_staged,
            dsca_status=dsca_status,
            history_disclosure=(
                "In-scope 2026 DSCA articles + the 26-13 certification PDF only; "
                "the pre-2026 DSCA archive is not covered in v1."
            ),
            generated_at=observed_at,
        )
    except fms_cases.FmsCoverageRefused as exc:
        print(f"::error title=fms-coverage-gate-refused::{exc}", flush=True)
        return 1

    try:
        _write_jsonl(receipts_path, merged_receipts)
        _write_jsonl(observations_path, merged_observations)
        _atomic_write_text(state_path, json.dumps(state, sort_keys=True, separators=(",", ":")))
        _atomic_write_text(graph_path, json.dumps(graph, sort_keys=True, separators=(",", ":")))
    except OSError as exc:
        print(f"::error title=fms-triad-write-failed::{exc}", flush=True)
        return 1

    print(
        f"FMS acquisition wrote {len(merged_observations)} observation(s), "
        f"{len(merged_receipts)} receipt(s), {len(graph['cases'])} case(s)",
        flush=True,
    )
    return 0


def acquire(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="FMS live acquisition (fetch/store/parse/publish)")
    parser.add_argument("command", choices=["acquire"], help="the only supported command")
    parser.parse_args(argv)
    store = build_default_store()
    if store is None:
        print(
            "::error title=fms-store-unavailable::FMS object store is unavailable "
            "(R2_BUCKET/R2_ENDPOINT/R2_ACCESS_KEY_ID/R2_SECRET_ACCESS_KEY); "
            "refusing acquisition without a receipt",
            flush=True,
        )
        return 1
    return run_fms_acquisition(root=Path.cwd(), store=store)


def main(argv: list[str] | None = None) -> int:
    import sys
    args = list(sys.argv[1:]) if argv is None else list(argv)
    if args and args[0] == "stage-state":
        return stage_state(args[1:])
    return acquire(args)


if __name__ == "__main__":
    raise SystemExit(main())
