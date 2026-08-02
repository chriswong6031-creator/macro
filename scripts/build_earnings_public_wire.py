"""Build the public, exact-evidence earnings-call wire under ``/stocks/earnings``.

This builder consumes an immutable public story-packet generation, verifies
every object receipt and packet contract in memory, and emits a source-record
archive.  It is *not* a Press publication lane: it never uses upstream story
copy/SEO fields, does not call a model, and cannot publish an unverified
summary.

Git retains rendered public pages plus a tiny redacted route catalog only. No
packet, source marker, receipt graph, or last-good manifest is persisted. A
source outage preserves existing bytes for at most 48 hours; it then fails
closed rather than indefinitely masquerading stale research as current.

Usage:
    python -m scripts.build_earnings_public_wire
    python -m scripts.build_earnings_public_wire --offline
    python -m scripts.build_earnings_public_wire --out-dir /tmp/earnings-wire
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
import email.utils
from hashlib import sha256
import html
import json
import logging
import os
from pathlib import Path
import re
import sys
import tempfile
from typing import Any, Callable, Mapping
from urllib.parse import urlsplit
import requests

from jinja2 import Environment, FileSystemLoader, StrictUndefined


_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from engine.earnings_narrative.public_wire import (  # noqa: E402
    PUBLIC_WIRE_MANIFEST_SCHEMA,
    PublicWireContractError,
    build_public_wire_manifest,
    compile_public_wire_article,
    source_manifest_sha256,
    verify_public_wire_manifest,
)
from engine.earnings_narrative.story_packets import (  # noqa: E402
    validate_story_packet,
    validate_story_packet_manifest,
)
from lib.pages import write_page  # noqa: E402
from lib.seo import BRAND_NAME, SITE_BASE, page_url  # noqa: E402
from engine.neuralweb import company_intelligence_reader as _company_reader  # noqa: E402


log = logging.getLogger("build_earnings_public_wire")

DEFAULT_SOURCE_BASE = "https://pub-f7ffb4441c5f4ad983ca56ec7c651c61.r2.dev"
DEFAULT_SOURCE_MANIFEST = "earnings_story_packets/manifest.json"
OUTPUT_RELATIVE = Path("stocks") / "earnings"
ROUTE_CATALOG_FILENAME = "route-catalog.json"
FEED_FILENAME = "feed.xml"
WIRE_SITEMAP_FILENAME = "sitemap.xml"
ASSET_DIRNAME = "assets"
ASSET_NAMES = ("earnings-wire.css", "earnings-wire.js")
FEED_LIMIT = 100
INDEX_PAGE_SIZE = 96
# This lane is intentionally memory-bound while it hydrates a generation.  The
# served route catalog is its only persisted state; the packet graph and source
# marker must never become a Git artifact or a public bulk-data endpoint.
MAX_MANIFEST_BYTES = 8 * 1024 * 1024
MAX_PACKET_BYTES = 2 * 1024 * 1024
MAX_SOURCE_PACKET_COUNT = 10_000
MAX_EXISTING_AGE_SECONDS = 48 * 60 * 60
ROUTE_CATALOG_SCHEMA = "earnings.public_wire_routes/v1"


def _renderer_version() -> str:
    """Fingerprint every code/template input that can change rendered bytes.

    Source and Company generations can remain unchanged while this product's
    templates, shared public chrome, or renderer logic advances.  Pinning this
    digest in the redacted route catalog makes those deploys invalidate the
    packet-hydration fast path instead of leaving stale HTML in production.
    """
    inputs = [
        Path(__file__),
        _REPO / "engine" / "earnings_narrative" / "public_wire.py",
        _REPO / "lib" / "pages.py",
        _REPO / "lib" / "seo.py",
        _REPO / "templates" / "seo_base.html.j2",
        _REPO / "templates" / "_public_nav.html.j2",
        _REPO / "templates" / "_public_chrome_css.html.j2",
        *sorted((_REPO / "templates" / "earnings_wire").glob("*")),
    ]
    digest = sha256()
    for path in inputs:
        if not path.is_file():
            raise PublicWireBuildError(f"renderer input missing: {path}")
        digest.update(str(path.relative_to(_REPO)).encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


class PublicWireBuildError(RuntimeError):
    """Fresh source collection failed before a safe public publication existed."""


@dataclass(frozen=True)
class BuildResult:
    manifest_id: str
    source: str
    article_count: int
    output_dir: Path


def _canonical_json(payload: object) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8") + b"\n"


def _safe_jsonld(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")


def _json_bytes(value: bytes, *, label: str) -> Mapping[str, Any]:
    try:
        decoded = json.loads(value.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PublicWireBuildError(f"{label} is not valid JSON") from exc
    if not isinstance(decoded, Mapping):
        raise PublicWireBuildError(f"{label} must be a JSON object")
    return decoded


def _http_fetch(url: str, *, timeout: float, max_bytes: int) -> bytes:
    """Fetch one immutable-source object without unbounded buffering.

    Public packet storage is an input boundary, not a trusted local file.  The
    source never needs redirects, so rejecting them also closes a server-side
    request pivot.  ``max_bytes`` protects both builder memory and CI time.
    """
    parsed = urlsplit(url)
    expected_origin = (parsed.scheme.lower(), (parsed.hostname or "").lower(), parsed.port or 443)
    if parsed.scheme.lower() != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise PublicWireBuildError("public story packet source must be a safe https URL")
    try:
        response = requests.get(
            url,
            headers={"User-Agent": "MastermindX-EarningsWire/1.0 (+https://www.mastermind-x.com)"},
            timeout=timeout,
            stream=True,
            allow_redirects=False,
        )
        with response:
            landed = urlsplit(str(getattr(response, "url", url) or url))
            landed_origin = (landed.scheme.lower(), (landed.hostname or "").lower(), landed.port or 443)
            if response.is_redirect or 300 <= response.status_code < 400 or landed_origin != expected_origin:
                raise PublicWireBuildError("public story packet source redirected or changed origin")
            response.raise_for_status()
            content_length = response.headers.get("Content-Length")
            if content_length:
                try:
                    if int(content_length) > max_bytes:
                        raise PublicWireBuildError("public story packet object exceeds safe size bound")
                except ValueError as exc:
                    raise PublicWireBuildError("public story packet object has invalid Content-Length") from exc
            chunks: list[bytes] = []
            used = 0
            for chunk in response.iter_content(chunk_size=65_536):
                if not chunk:
                    continue
                used += len(chunk)
                if used > max_bytes:
                    raise PublicWireBuildError("public story packet object exceeds safe size bound")
                chunks.append(chunk)
            return b"".join(chunks)
    except requests.RequestException as exc:
        raise PublicWireBuildError(f"unable to fetch {url}: {exc}") from exc


def _source_url(base: str, relative: str) -> str:
    cleaned = relative.lstrip("/")
    if ".." in Path(cleaned).parts or not cleaned:
        raise PublicWireBuildError("unsafe public story packet object path")
    return base.rstrip("/") + "/" + cleaned


def _validate_remote_manifest(manifest: Mapping[str, Any]) -> None:
    try:
        validate_story_packet_manifest(manifest)
    except Exception as exc:  # noqa: BLE001 - domain contract error converted at this boundary.
        raise PublicWireBuildError(f"public story packet manifest failed contract verification: {exc}") from exc


def fetch_current_publication(
    *, source_base: str = DEFAULT_SOURCE_BASE,
    fetch: Callable[[str], bytes] | None = None,
    workers: int = 12,
    timeout: float = 30.0,
) -> dict[str, Any]:
    """Hydrate every current packet only after its immutable receipt is known.

    The function is deliberately all-or-nothing. A single missing, altered, or
    malformed object raises before a candidate public-wire manifest is built;
    callers can then retain their prior verified publication rather than emit a
    silently shrunken archive.
    """
    if workers < 1 or workers > 32:
        raise PublicWireBuildError("workers must be between 1 and 32")
    if timeout <= 0:
        raise PublicWireBuildError("timeout must be positive")
    source_base = source_base.rstrip("/")
    if not source_base.startswith("https://"):
        raise PublicWireBuildError("public packet source must use https")
    read = fetch or (lambda url, limit: _http_fetch(url, timeout=timeout, max_bytes=limit))
    def read_source(url: str, *, limit: int) -> bytes:
        try:
            try:
                payload = read(url, limit)  # type: ignore[misc]
            except TypeError:
                # The tiny one-argument seam keeps deterministic unit fixtures
                # ergonomic; the production implementation always receives the
                # explicit byte ceiling above.
                payload = read(url)  # type: ignore[call-arg]
        except PublicWireBuildError:
            raise
        except Exception as exc:  # noqa: BLE001 - injected fetchers share the same fail-closed boundary.
            raise PublicWireBuildError(f"unable to fetch {url}: {exc}") from exc
        if not isinstance(payload, bytes):
            raise PublicWireBuildError(f"source fetch did not return bytes for {url}")
        if len(payload) > limit:
            raise PublicWireBuildError("public story packet object exceeds safe size bound")
        return payload
    manifest_url = _source_url(source_base, DEFAULT_SOURCE_MANIFEST)
    raw_manifest = read_source(manifest_url, limit=MAX_MANIFEST_BYTES)
    manifest = _json_bytes(raw_manifest, label="public story packet manifest")
    if raw_manifest != _canonical_json(manifest):
        raise PublicWireBuildError("public story packet marker is not canonical bytes")
    _validate_remote_manifest(manifest)

    files = manifest.get("files")
    packets = manifest.get("packets")
    policy = manifest.get("policy")
    if not isinstance(files, Mapping) or not isinstance(packets, Mapping) or not isinstance(policy, Mapping):
        raise PublicWireBuildError("public story packet manifest lacks files, packets, or policy")
    policy_snapshot = policy.get("snapshot")
    generation_id = manifest.get("generation_id")
    if not isinstance(policy_snapshot, Mapping) or not isinstance(generation_id, str):
        raise PublicWireBuildError("public story packet manifest policy or generation is invalid")
    immutable_url = _source_url(
        source_base, f"earnings_story_packets/generations/{generation_id}/manifest.json",
    )
    raw_immutable = read_source(immutable_url, limit=MAX_MANIFEST_BYTES)
    immutable = _json_bytes(raw_immutable, label="immutable public story packet manifest")
    if raw_immutable != _canonical_json(immutable):
        raise PublicWireBuildError("immutable public story packet manifest is not canonical bytes")
    _validate_remote_manifest(immutable)
    if (
        raw_manifest != raw_immutable
        or manifest != immutable
        or sha256(raw_manifest).hexdigest() != sha256(raw_immutable).hexdigest()
    ):
        raise PublicWireBuildError("mutable story packet marker does not equal immutable generation manifest")
    if len(packets) > MAX_SOURCE_PACKET_COUNT:
        raise PublicWireBuildError("public story packet catalog exceeds safe count bound")

    def one(event_key: str, index: object) -> tuple[str, dict[str, Any] | None]:
        if not isinstance(index, Mapping):
            raise PublicWireBuildError(f"packet index is invalid for {event_key}")
        object_key = index.get("object_key")
        if not isinstance(object_key, str):
            raise PublicWireBuildError(f"packet index object key missing for {event_key}")
        receipt = files.get(object_key)
        if not isinstance(receipt, Mapping):
            raise PublicWireBuildError(f"packet receipt missing for {event_key}")
        expected_sha = receipt.get("sha256")
        expected_bytes = receipt.get("bytes")
        if not isinstance(expected_sha, str) or not isinstance(expected_bytes, int) or expected_bytes <= 0:
            raise PublicWireBuildError(f"packet receipt is invalid for {event_key}")
        if expected_bytes > MAX_PACKET_BYTES:
            raise PublicWireBuildError(f"packet receipt exceeds safe size bound for {event_key}")
        raw_packet = read_source(
            _source_url(source_base, f"earnings_story_packets/{object_key}"),
            limit=MAX_PACKET_BYTES,
        )
        if len(raw_packet) != expected_bytes or sha256(raw_packet).hexdigest() != expected_sha:
            raise PublicWireBuildError(f"packet receipt mismatch for {event_key}")
        packet = _json_bytes(raw_packet, label=f"story packet {event_key}")
        if packet.get("packet_id") != index.get("packet_id"):
            raise PublicWireBuildError(f"packet identity mismatch for {event_key}")
        story = packet.get("story")
        if not isinstance(story, Mapping) or story.get("story_id") != index.get("story_id") or story.get("story_revision_id") != index.get("story_revision_id"):
            raise PublicWireBuildError(f"story identity mismatch for {event_key}")
        try:
            validate_story_packet(packet, policy=policy_snapshot)
        except Exception as exc:  # noqa: BLE001 - never quietly skip a malformed receipt-bound packet.
            raise PublicWireBuildError(f"story packet contract failed for {event_key}: {exc}") from exc
        # The upstream catalog deliberately retains Tier-C/non-ready objects.
        # They are valid context artifacts, but have no public wire derivative.
        # Excluding them is distinct from accepting an incomplete download: every
        # current packet has already been fetched, hashed, and contract-checked.
        digest = packet.get("digest")
        source = story.get("source") if isinstance(story, Mapping) else None
        promotion = story.get("promotion") if isinstance(story, Mapping) else None
        if not (
            story.get("status") == "source_ready"
            and isinstance(promotion, Mapping)
            and promotion.get("article_eligible") is True
            and promotion.get("tier") in {"A", "B"}
            and isinstance(digest, Mapping)
            and digest.get("citation_coverage") == 1.0
            and isinstance(digest.get("quality"), Mapping)
            and digest["quality"].get("status") == "ready"
            and isinstance(source, Mapping)
            and source.get("source_kind") == "transcript"
        ):
            return event_key, None
        article = compile_public_wire_article(
            packet,
            policy_snapshot=policy_snapshot,
            generation_id=generation_id,
            object_key=object_key,
            object_sha256=expected_sha,
            object_bytes=expected_bytes,
        )
        expected_event_key = f"{article['event']['ticker']}/{article['event']['transcript_id']}"
        if event_key != expected_event_key:
            raise PublicWireBuildError(f"packet event identity mismatch for {event_key}")
        return event_key, article

    outcomes: dict[str, dict[str, Any]] = {}
    # Submit in key order so the audit surface and failures are deterministic;
    # completion order is intentionally irrelevant to the frozen final manifest.
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="earnings-wire") as executor:
        futures = {executor.submit(one, key, index): key for key, index in sorted(packets.items())}
        for future in as_completed(futures):
            event_key = futures[future]
            try:
                key, article = future.result()
            except Exception as exc:  # noqa: BLE001 - preserve first source error with its event identity.
                for outstanding in futures:
                    outstanding.cancel()
                raise PublicWireBuildError(f"public packet hydration failed at {event_key}: {exc}") from exc
            if article is not None:
                outcomes[key] = article
    if not outcomes:
        raise PublicWireBuildError("current packet catalog contains no public-wire-eligible exact evidence")
    publication = build_public_wire_manifest(
        list(outcomes.values()),
        source_generation_id=generation_id,
        source_manifest_sha256=source_manifest_sha256(raw_manifest),
        source_packet_count=len(packets),
        source_packet_manifest_schema=str(manifest.get("schema") or ""),
        canonical_base=SITE_BASE.rstrip("/"),
    )
    return publication


def load_public_build_state(out_dir: Path) -> dict[str, Any] | None:
    """Read the redacted public routing state, never a retained packet manifest.

    The state is deliberately safe to serve: it contains route identity,
    presentation names, and a generation/hash receipt only.  It is sufficient
    to skip a no-change hydration, but deliberately insufficient to recreate a
    page or leak the evidence corpus.
    """
    path = Path(out_dir) / ROUTE_CATALOG_FILENAME
    if not path.is_file():
        return None
    payload = _json_bytes(path.read_bytes(), label="public earnings wire route catalog")
    expected = {
        "schema", "source_generation_id", "source_manifest_sha256", "verified_at",
        "company_generation_id", "renderer_version", "article_count", "as_of", "routes",
    }
    if set(payload) != expected or payload.get("schema") != ROUTE_CATALOG_SCHEMA:
        return None
    if not isinstance(payload.get("source_generation_id"), str) or not re.fullmatch(r"[0-9a-f]{32}", payload["source_generation_id"]):
        return None
    if not isinstance(payload.get("source_manifest_sha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", payload["source_manifest_sha256"]):
        return None
    if not isinstance(payload.get("verified_at"), str) or not isinstance(payload.get("article_count"), int):
        return None
    if payload.get("company_generation_id") is not None and not isinstance(payload.get("company_generation_id"), str):
        return None
    if not isinstance(payload.get("renderer_version"), str) or not re.fullmatch(r"[0-9a-f]{64}", payload["renderer_version"]):
        return None
    if not isinstance(payload.get("routes"), Mapping):
        return None
    return dict(payload)


def _state_age_seconds(state: Mapping[str, Any], *, now: datetime) -> float:
    value = state.get("verified_at")
    if not isinstance(value, str):
        return float("inf")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return float("inf")
    if parsed.tzinfo is None:
        return float("inf")
    return max(0.0, (now.astimezone(timezone.utc) - parsed.astimezone(timezone.utc)).total_seconds())


def _safe_existing_state_or_raise(out_dir: Path, *, now: datetime) -> dict[str, Any]:
    state = load_public_build_state(out_dir)
    if state is None:
        raise PublicWireBuildError("no safe existing earnings-wire build state")
    if _state_age_seconds(state, now=now) > MAX_EXISTING_AGE_SECONDS:
        raise PublicWireBuildError("existing earnings-wire publication is older than 48 hours")
    if not (Path(out_dir) / "index.html").is_file():
        raise PublicWireBuildError("existing earnings-wire publication has no index page")
    return state


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def _route_catalog(
    manifest: Mapping[str, Any], *, alignment: Mapping[str, Mapping[str, Any]], verified_at: str,
    company_generation_id: str | None,
) -> bytes:
    """Emit the smallest public routing contract needed by ticker dossiers.

    No facts, excerpts, hashes, source locators, packet keys, or receipt
    coordinates cross this boundary.
    """
    routes: dict[str, dict[str, Any]] = {}
    for article in manifest["articles"]:
        event = article["event"]
        ticker = str(event["ticker"])
        tx = str(event["transcript_id"])
        row = alignment.get(str(article["article_id"]), {})
        candidate = {
            "href": f"{event['slug']}.html",
            "period": str(event["period"]),
            "date": str(event["date"]),
            "transcript_id": tx,
            "dossier_available": row.get("dossier_available") is True,
        }
        current = routes.setdefault(ticker, {
            "company_name": str(row.get("company_name") or ticker), "latest": None, "events": {},
        })
        events = current["events"]
        assert isinstance(events, dict)
        events[tx] = candidate
        latest = current["latest"]
        if latest is None or (candidate["date"], candidate["period"], candidate["href"]) > (
            latest["date"], latest["period"], latest["href"]
        ):
            current["latest"] = candidate
    payload = {
        "schema": ROUTE_CATALOG_SCHEMA,
        "source_generation_id": str(manifest["source"]["generation_id"]),
        "source_manifest_sha256": str(manifest["source"]["manifest_sha256"]),
        "company_generation_id": company_generation_id,
        "renderer_version": _renderer_version(),
        "verified_at": verified_at,
        "article_count": len(manifest["articles"]),
        "as_of": max((str(route["lastmod"]) for route in manifest["routes"]), default=""),
        "routes": {
            ticker: {
                "company_name": routes[ticker]["company_name"],
                "latest": routes[ticker]["latest"],
                "events": {tx: routes[ticker]["events"][tx] for tx in sorted(routes[ticker]["events"])},
            }
            for ticker in sorted(routes)
        },
    }
    return _canonical_json(payload)


def _remove_legacy_public_state(out_dir: Path) -> None:
    """Delete the old served bulk manifests after the redacted catalog exists."""
    (out_dir / "article_manifest.json").unlink(missing_ok=True)
    legacy_publications = out_dir / "publications"
    if not legacy_publications.exists():
        return
    if not legacy_publications.is_dir():
        raise PublicWireBuildError("legacy public-wire publications path is not a directory")
    for entry in legacy_publications.iterdir():
        if not entry.is_file() or entry.suffix != ".json":
            raise PublicWireBuildError(f"unexpected file in legacy public-wire state: {entry}")
        entry.unlink()
    legacy_publications.rmdir()




def _copy_assets(out_dir: Path) -> None:
    asset_dir = out_dir / ASSET_DIRNAME
    template_dir = _REPO / "templates" / "earnings_wire"
    for name in ASSET_NAMES:
        source = template_dir / name
        if not source.is_file():
            raise PublicWireBuildError(f"earnings wire asset missing: {source}")
        _atomic_write(asset_dir / name, source.read_bytes())


def _rfc822(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        parsed = datetime.fromisoformat(value + "T00:00:00+00:00")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return email.utils.format_datetime(parsed.astimezone(timezone.utc), usegmt=True)


_BOILERPLATE_PREVIEW = re.compile(
    r"\b(safe\s+harbor|forward[- ]looking|operator|replay|webcast|good\s+morning|thank\s+you)\b",
    re.IGNORECASE,
)
_MATERIAL_PREVIEW = re.compile(
    r"\b(revenue|margin|guidance|demand|backlog|growth|profit|cash|bookings|outlook|expect)\b",
    re.IGNORECASE,
)
_NUMBER_PREVIEW = re.compile(r"(?:\$?\d[\d,.]*%?|\b\d+(?:\.\d+)?\s*(?:bps|million|billion|percent)\b)", re.IGNORECASE)


def _preview_score(fact: Mapping[str, Any]) -> int:
    """Rank visible record previews without generating or changing a claim."""
    quote = fact.get("quote") if isinstance(fact.get("quote"), Mapping) else {}
    text = str(quote.get("text") or "")
    score = 0
    role = str(fact.get("role") or "").lower()
    if role in {"executive", "management"}:
        score += 18
    if role == "analyst":
        score -= 30
    score += 14 * len(set(str(item) for item in fact.get("categories", []) if str(item) in {
        "performance", "guidance", "demand", "margins", "risks",
    }))
    if fact.get("numeric"):
        score += 12
    if _NUMBER_PREVIEW.search(text):
        score += 8
    if _MATERIAL_PREVIEW.search(text):
        score += 10
    if _BOILERPLATE_PREVIEW.search(text):
        score -= 45
    # Prefer an informative complete sentence, without letting length swamp
    # relevance or elevate a long analyst question.
    score += min(len(text) // 80, 5)
    return score


def _view_article(article: Mapping[str, Any], *, alignment: Mapping[str, Any]) -> dict[str, Any]:
    """Add UI-only counters and labels without altering the frozen evidence payload."""
    facts = article["facts"]
    spans = [fact["quote"] for fact in facts] + [numeric for fact in facts for numeric in fact["numeric"]]
    spans.sort(key=lambda row: (
        int(row["receipt"]["segment_index"]),
        int(row["receipt"]["span_start_byte"]),
        str(row["claim_id"]),
    ))
    categories = []
    for fact in facts:
        categories.extend(str(item) for item in fact["categories"])
    unique_categories = list(dict.fromkeys(categories))
    preview = max(enumerate(facts), key=lambda row: (_preview_score(row[1]), -row[0]))[1]
    ticker = str(article["event"]["ticker"])
    company_name = str(alignment.get("company_name") or ticker).strip() or ticker
    company_label = company_name if company_name.upper() != ticker else ticker
    searchable = " ".join([
        ticker, company_name, str(article["event"]["period"]),
        str(article["event"]["date"]), " ".join(categories),
        " ".join(str(fact["speaker"]) for fact in facts),
    ]).lower()
    return {
        **article,
        "facts": facts,
        "spans": spans,
        "fact_count": len(facts),
        "numeric_count": sum(len(fact["numeric"]) for fact in facts),
        "display_categories": [item.replace("_", " ") for item in unique_categories[:3]],
        "category_search": " ".join(unique_categories).lower(),
        "search_text": searchable,
        "preview_quote": preview["quote"]["text"],
        "preview_speaker": preview["speaker"],
        "href": f"{article['event']['slug']}.html",
        "company_name": company_name,
        "company_label": company_label,
        "dossier_available": alignment.get("dossier_available") is True,
    }


def _index_jsonld(manifest: Mapping[str, Any], *, route: str, item_count: int) -> str:
    return _safe_jsonld({
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": "MastermindX Earnings Wire",
        "description": "Receipt-bound excerpts from earnings-call transcripts.",
        "url": page_url(route),
        "isPartOf": {"@type": "WebSite", "name": BRAND_NAME, "url": SITE_BASE},
        "numberOfItems": item_count,
    })


def _article_jsonld(article: Mapping[str, Any]) -> str:
    route = f"stocks/earnings/{article['event']['slug']}.html"
    title = f"{article['event']['ticker']} — {article['company_label']} {article['event']['period']} earnings call record"
    return _safe_jsonld({
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": title,
        "description": f"Receipt-bound excerpts from {article['company_label']}'s earnings-call transcript. Transcript-only source record; not investment advice.",
        "mainEntityOfPage": {"@type": "WebPage", "@id": page_url(route)},
        # This is the durable source-record indexing time, not a fabricated
        # editorial publication timestamp.
        "dateCreated": article["source"]["index_generated_at"],
        "dateModified": article["source"]["index_generated_at"],
        "temporalCoverage": article["event"]["date"],
        "author": {"@type": "Organization", "name": BRAND_NAME},
        "publisher": {"@type": "Organization", "name": BRAND_NAME},
        "isBasedOn": f"https://app.mastermind-x.com/terminal?sym={article['event']['ticker']}&pane=transcripts&tx={article['event']['transcript_id']}&from=macro",
    })


def _feed(views: list[Mapping[str, Any]]) -> bytes:
    rows = views[:FEED_LIMIT]
    items = []
    for article in rows:
        route = f"stocks/earnings/{article['event']['slug']}.html"
        title = f"{article['event']['ticker']} — {article['company_label']} {article['event']['period']} earnings call record"
        description = f"Receipt-bound excerpts from {article['company_label']}'s earnings-call transcript. Transcript-only source record; not a recommendation."
        items.append(
            "<item>"
            f"<title>{html.escape(title)}</title>"
            f"<link>{html.escape(page_url(route))}</link>"
            f"<guid isPermaLink=\"true\">{html.escape(page_url(route))}</guid>"
            f"<pubDate>{html.escape(_rfc822(str(article['source']['index_generated_at'])))}</pubDate>"
            f"<description><![CDATA[{description}]]></description>"
            "</item>"
        )
    body = "".join(items)
    return (
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
        "<rss version=\"2.0\"><channel>"
        "<title>MastermindX Earnings Wire</title>"
        f"<link>{html.escape(page_url('stocks/earnings/index.html'))}</link>"
        "<description>Receipt-bound excerpts from company earnings-call transcripts.</description>"
        "<language>en</language>"
        f"{body}</channel></rss>\n"
    ).encode("utf-8")


def _wire_sitemap(manifest: Mapping[str, Any]) -> bytes:
    """Build the wire-owned sitemap; the nightly remains sole root owner."""
    routes = list(manifest["routes"])
    latest = max((str(route["lastmod"]) for route in routes), default="")
    rows = [
        "  <url><loc>"
        + html.escape(page_url("stocks/earnings/index.html"), quote=False)
        + "</loc>"
        + (f"<lastmod>{html.escape(latest, quote=False)}</lastmod>" if latest else "")
        + "<changefreq>hourly</changefreq><priority>0.7</priority></url>"
    ]
    rows.extend(
        "  <url><loc>"
        + html.escape(str(route["canonical"]), quote=False)
        + "</loc><lastmod>"
        + html.escape(str(route["lastmod"]), quote=False)
        + "</lastmod><changefreq>weekly</changefreq><priority>0.6</priority></url>"
        for route in routes
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(rows)
        + "\n</urlset>\n"
    ).encode("utf-8")


def _local_company_name(out_dir: Path, ticker: str) -> str | None:
    """Recover a presentational name from an already-rendered safe ticker page."""
    path = out_dir.parent / f"{ticker}.html"
    if not path.is_file():
        return None
    try:
        title = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    match = re.search(r"<title>\s*[^<]*?\b" + re.escape(ticker) + r"\b\s*[—-]\s*([^<:|]{2,180})", title, re.IGNORECASE)
    return match.group(1).strip() if match else None


def _company_event_is_exact(event: Mapping[str, Any], *, transcript_id: str, call_date: str) -> bool:
    """Require the same transcript identity (or fiscal tuple) *and* call date."""
    if str(event.get("call_date") or "") != call_date:
        return False
    explicit = str(event.get("transcript_id") or "")
    event_id = str(event.get("event_id") or "")
    if explicit == transcript_id or event_id.rsplit(":", 1)[-1] == transcript_id:
        return True
    year = event.get("fiscal_year")
    quarter = event.get("fiscal_quarter")
    try:
        normalized = f"{int(year)}Q{int(quarter)}"
    except (TypeError, ValueError):
        return False
    return normalized == transcript_id


def _company_alignment_snapshot(
    manifest: Mapping[str, Any], *, out_dir: Path,
    company_reader: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None,
) -> tuple[dict[str, dict[str, Any]], str | None]:
    """Return a fail-closed, redacted public alignment for every wire article.

    A static ticker page is necessary but not sufficient: an article earns a
    dossier route only when the Company Intelligence history independently
    contains that exact transcript/fiscal tuple on the same call date.  Reader
    outages, partial history, stale quarters and identity mismatches always
    fall back to Terminal rather than manufacturing a cross-layer join.
    """
    reader = company_reader or _company_reader.read_company_intelligence
    by_ticker: dict[str, list[Mapping[str, Any]]] = {}
    for article in manifest["articles"]:
        by_ticker.setdefault(str(article["event"]["ticker"]), []).append(article)
    def read_one(ticker: str) -> tuple[str, Mapping[str, Any]]:
        try:
            result = reader({"ticker": ticker, "limit": 12})
        except Exception:  # noqa: BLE001 - public links must fail closed on reader failure.
            result = {"available": False}
        return ticker, result if isinstance(result, Mapping) else {"available": False}

    contexts: dict[str, Mapping[str, Any]] = {}
    # The reader internally caches the immutable Company snapshot, while this
    # bounded fan-out keeps a new wire generation from taking one network
    # round-trip per ticker serially. Each failed ticker still becomes a
    # Terminal-only CTA; no parallel failure can make a link more permissive.
    with ThreadPoolExecutor(max_workers=min(12, max(1, len(by_ticker))), thread_name_prefix="wire-company-align") as executor:
        futures = {executor.submit(read_one, ticker): ticker for ticker in sorted(by_ticker)}
        for future in as_completed(futures):
            ticker, result = future.result()
            contexts[ticker] = result

    generations = {
        str(context.get("generation_id"))
        for context in contexts.values()
        if isinstance(context.get("generation_id"), str) and context.get("generation_id")
    }
    # A mixed reader snapshot is not a meaningful release receipt.  Preserve
    # the rendered alignment but omit a generation pin, forcing the next same-
    # earnings pass to probe again rather than claiming a false joint snapshot.
    company_generation_id = next(iter(generations)) if len(generations) == 1 else None
    rows: dict[str, dict[str, Any]] = {}
    for ticker, articles in by_ticker.items():
        context = contexts[ticker]
        company = context.get("company") if isinstance(context.get("company"), Mapping) else {}
        reader_name = company.get("display_name") if isinstance(company.get("display_name"), str) else None
        # Local ticker pages are operator-curated presentation surfaces.  Their
        # spelling/casing wins over an upstream all-caps display name, while
        # the reader remains the useful fallback for unrendered pages.
        name = _local_company_name(out_dir, ticker) or reader_name or ticker
        raw_history = context.get("history") if isinstance(context.get("history"), list) else []
        history = [item for item in raw_history if isinstance(item, Mapping)] if context.get("available") is True else []
        latest = context.get("latest_event") if isinstance(context.get("latest_event"), Mapping) else None
        static_dossier = (out_dir.parent / f"{ticker}.html").is_file()
        for article in articles:
            event = article["event"]
            exact_history = any(
                _company_event_is_exact(
                    candidate,
                    transcript_id=str(event["transcript_id"]),
                    call_date=str(event["date"]),
                )
                for candidate in history
            )
            exact_latest = latest is not None and _company_event_is_exact(
                latest,
                transcript_id=str(event["transcript_id"]),
                call_date=str(event["date"]),
            )
            status = "aligned_latest" if exact_latest and static_dossier else (
                "missing_static_dossier" if exact_latest else (
                    "historical_only" if exact_history else "unavailable_or_stale"
                )
            )
            rows[str(article["article_id"])] = {
                "company_name": str(name),
                # The anonymous dossier intentionally returns only its latest
                # event.  A history-only match would make an old public wire
                # page appear to deep-link into its own analysis while the
                # browser actually rendered the latest quarter.
                "dossier_available": exact_latest and static_dossier,
                "alignment_status": status,
            }
    return rows, company_generation_id


def build_company_alignment(
    manifest: Mapping[str, Any], *, out_dir: Path,
    company_reader: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None,
) -> dict[str, dict[str, Any]]:
    """Compatibility façade for direct alignment tests and callers."""
    return _company_alignment_snapshot(
        manifest, out_dir=out_dir, company_reader=company_reader,
    )[0]


def _probe_company_generation(
    state: Mapping[str, Any], *, company_reader: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None,
) -> str | None:
    """Read one covered ticker to decide whether a same-wire run is truly stale."""
    reader = company_reader or _company_reader.read_company_intelligence
    routes = state.get("routes") if isinstance(state.get("routes"), Mapping) else {}
    for ticker in sorted(str(key) for key in routes):
        try:
            result = reader({"ticker": ticker, "limit": 1})
        except Exception:  # noqa: BLE001 - a failed probe never widens publication work.
            return None
        if isinstance(result, Mapping) and isinstance(result.get("generation_id"), str):
            return str(result["generation_id"])
        return None
    return None


def _render_pages(
    manifest: Mapping[str, Any], *, out_dir: Path, alignment: Mapping[str, Mapping[str, Any]],
) -> tuple[dict[Path, str], list[dict[str, Any]]]:
    templates = _REPO / "templates"
    env = Environment(
        loader=FileSystemLoader(str(templates)), autoescape=True, undefined=StrictUndefined,
        trim_blocks=True, lstrip_blocks=True,
    )
    env.globals["t"] = lambda en, zh="": en  # seo_base defines its own bilingual macro; only nested fallback calls use this.
    views = [_view_article(article, alignment=alignment.get(str(article["article_id"]), {})) for article in manifest["articles"]]
    summary = {
        "article_count": len(views),
        "ticker_count": len({str(view["event"]["ticker"]) for view in views}),
        "source_packet_count": int(manifest["source"]["packet_count"]),
        "held_count": max(0, int(manifest["source"]["packet_count"]) - len(views)),
    }
    site = {"base": SITE_BASE, "brand": BRAND_NAME}
    index_template = env.get_template("earnings_wire/earnings_wire_index.html.j2")
    page_count = max(1, (len(views) + INDEX_PAGE_SIZE - 1) // INDEX_PAGE_SIZE)
    rendered: dict[Path, str] = {}
    for page_number in range(1, page_count + 1):
        filename = "index.html" if page_number == 1 else f"page-{page_number}.html"
        route = f"stocks/earnings/{filename}"
        start = (page_number - 1) * INDEX_PAGE_SIZE
        items = views[start:start + INDEX_PAGE_SIZE]
        index_page = {
            "title": "Earnings call records" + (f" — page {page_number}" if page_number > 1 else ""),
            "description": "Receipt-bound excerpts from company earnings-call transcripts.",
            "canonical": page_url(route),
            "url_path": "/" + route,
            "breadcrumbs": [
                {"label": "Home", "href": "/index.html"},
                {"label": "Earnings call records", "href": None},
            ],
        }
        pages = [
            {
                "number": number,
                "href": "index.html" if number == 1 else f"page-{number}.html",
                "current": number == page_number,
            }
            for number in range(1, page_count + 1)
        ]
        rendered[out_dir / filename] = index_template.render(
            page=index_page,
            rel="../../",
            site=site,
            items=items,
            summary=summary,
            pagination={
                "number": page_number,
                "count": page_count,
                "start": start + 1 if items else 0,
                "end": start + len(items),
                "pages": pages,
                "previous": pages[page_number - 2]["href"] if page_number > 1 else None,
                "next": pages[page_number]["href"] if page_number < page_count else None,
            },
            jsonld=_index_jsonld(manifest, route=route, item_count=len(items)),
        )
    article_template = env.get_template("earnings_wire/earnings_wire_article.html.j2")
    for view in views:
        route = f"stocks/earnings/{view['event']['slug']}.html"
        page = {
            "title": f"{view['event']['ticker']} — {view['company_label']} {view['event']['period']} earnings call record",
            "description": f"Receipt-bound excerpts from {view['company_label']}'s {view['event']['period']} earnings call transcript.",
            "canonical": page_url(route),
            "url_path": "/" + route,
            "breadcrumbs": [
                {"label": "Home", "href": "/index.html"},
                {"label": "Earnings call records", "href": "/stocks/earnings/index.html"},
                {"label": str(view["event"]["ticker"]), "href": None},
            ],
        }
        rendered[out_dir / f"{view['event']['slug']}.html"] = article_template.render(
            page=page, rel="../../", site=site, article=view, jsonld=_article_jsonld(view),
        )
    return rendered, views


def _prior_page_paths(out_dir: Path, state: Mapping[str, Any] | None) -> set[Path]:
    """Read stale article names from the prior *redacted* route catalog only."""
    if state is None:
        return set()
    paths: set[Path] = set()
    routes = state.get("routes") if isinstance(state.get("routes"), Mapping) else {}
    for company in routes.values():
        events = company.get("events") if isinstance(company, Mapping) and isinstance(company.get("events"), Mapping) else {}
        for event in events.values():
            href = event.get("href") if isinstance(event, Mapping) else None
            if not isinstance(href, str) or not re.fullmatch(r"[a-z0-9.-]{1,180}\.html", href):
                continue
            paths.add(out_dir / href)
    return paths


def _route_path(out_dir: Path, route: Mapping[str, Any]) -> Path:
    prefix = "/stocks/earnings/"
    raw = str(route["url_path"])
    if not raw.startswith(prefix):
        raise PublicWireBuildError("wire route escapes its public family")
    name = raw[len(prefix):]
    if not name.endswith(".html") or "/" in name or "\\" in name:
        raise PublicWireBuildError("wire route filename is invalid")
    return out_dir / name


def publish_public_wire(
    manifest: Mapping[str, Any], *, out_dir: Path,
    prior_state: Mapping[str, Any] | None = None,
    company_reader: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None,
    now: datetime | None = None,
) -> BuildResult:
    """Render a fully verified catalog and atomically replace only wire files."""
    verify_public_wire_manifest(manifest)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    alignment, company_generation_id = _company_alignment_snapshot(
        manifest, out_dir=out_dir, company_reader=company_reader,
    )
    rendered, views = _render_pages(manifest, out_dir=out_dir, alignment=alignment)
    for destination, markup in rendered.items():
        # All static HTML goes through the shared injection path so this family
        # retains the same data-base bootstrap and future page hygiene as the
        # rest of the public estate.
        write_page(destination, markup, encoding="utf-8")
    current_index_pages = {path for path in rendered if path.name == "index.html" or path.name.startswith("page-")}
    for stale_index in out_dir.glob("page-*.html"):
        if stale_index not in current_index_pages:
            stale_index.unlink(missing_ok=True)
    _copy_assets(out_dir)
    _atomic_write(out_dir / FEED_FILENAME, _feed(views))
    _atomic_write(out_dir / WIRE_SITEMAP_FILENAME, _wire_sitemap(manifest))
    verified_at = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    _atomic_write(
        out_dir / ROUTE_CATALOG_FILENAME,
        _route_catalog(
            manifest, alignment=alignment, verified_at=verified_at,
            company_generation_id=company_generation_id,
        ),
    )
    _remove_legacy_public_state(out_dir)

    current_paths = {_route_path(out_dir, route) for route in manifest["routes"]}
    if prior_state is not None:
        for stale in _prior_page_paths(out_dir, prior_state) - current_paths:
            stale.unlink(missing_ok=True)
    return BuildResult(str(manifest["manifest_id"]), "remote", len(manifest["articles"]), out_dir)


def build(
    *, out_dir: Path | None = None, source_base: str = DEFAULT_SOURCE_BASE,
    offline: bool = False, force: bool = False, workers: int = 12, timeout: float = 30.0,
    fetch: Callable[[str], bytes] | None = None,
    company_reader: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None,
    now: datetime | None = None,
) -> BuildResult:
    """Build from fresh immutable source, or retain a recent existing public wire.

    There is intentionally no offline manifest replay.  On an upstream outage,
    the already-rendered public bytes are the fallback and are never rewritten;
    after 48 hours that fallback becomes a hard failure instead of silently
    presenting stale research as current.
    """
    destination = Path(out_dir) if out_dir is not None else _REPO / "site" / OUTPUT_RELATIVE
    now = now or datetime.now(timezone.utc)
    state = load_public_build_state(destination)
    if offline:
        safe = _safe_existing_state_or_raise(destination, now=now)
        return BuildResult("existing", "existing", int(safe["article_count"]), destination)
    try:
        # Fetch marker + immutable manifest first.  This is purposefully split
        # from packet hydration so an unchanged verified generation costs two
        # tiny GETs, not another full 500-packet run.
        manifest_url = _source_url(source_base.rstrip("/"), DEFAULT_SOURCE_MANIFEST)
        read = fetch or (lambda url: _http_fetch(url, timeout=timeout, max_bytes=MAX_MANIFEST_BYTES))
        try:
            marker_raw = read(manifest_url)  # type: ignore[call-arg]
        except Exception as exc:  # noqa: BLE001
            raise PublicWireBuildError(f"unable to fetch {manifest_url}: {exc}") from exc
        if not isinstance(marker_raw, bytes) or len(marker_raw) > MAX_MANIFEST_BYTES:
            raise PublicWireBuildError("public story packet marker exceeds safe size bound")
        marker = _json_bytes(marker_raw, label="public story packet marker")
        if marker_raw != _canonical_json(marker):
            raise PublicWireBuildError("public story packet marker is not canonical bytes")
        _validate_remote_manifest(marker)
        generation_id = str(marker["generation_id"])
        marker_sha = sha256(marker_raw).hexdigest()
        immutable_url = _source_url(source_base.rstrip("/"), f"earnings_story_packets/generations/{generation_id}/manifest.json")
        try:
            immutable_raw = read(immutable_url)  # type: ignore[call-arg]
        except Exception as exc:  # noqa: BLE001
            raise PublicWireBuildError(f"unable to fetch {immutable_url}: {exc}") from exc
        if not isinstance(immutable_raw, bytes) or len(immutable_raw) > MAX_MANIFEST_BYTES:
            raise PublicWireBuildError("immutable story packet manifest exceeds safe size bound")
        immutable = _json_bytes(immutable_raw, label="immutable public story packet manifest")
        if (
            immutable_raw != _canonical_json(immutable)
            or marker_raw != immutable_raw
            or marker != immutable
            or marker_sha != sha256(immutable_raw).hexdigest()
        ):
            raise PublicWireBuildError("mutable story packet marker does not equal immutable generation manifest")
        _validate_remote_manifest(immutable)
        if not force and state is not None and (
            state["source_generation_id"] == generation_id
            and state["source_manifest_sha256"] == marker_sha
            and state["renderer_version"] == _renderer_version()
        ):
            safe = _safe_existing_state_or_raise(destination, now=now)
            company_generation = _probe_company_generation(safe, company_reader=company_reader)
            if company_generation is None or company_generation == safe.get("company_generation_id"):
                return BuildResult("unchanged", "unchanged", int(safe["article_count"]), destination)
        # ``fetch_current_publication`` repeats marker validation to preserve a
        # standalone fail-closed API.  Its packets are only hydrated on a new
        # verified source generation.
        manifest = fetch_current_publication(
            source_base=source_base, fetch=fetch, workers=workers, timeout=timeout,
        )
    except PublicWireBuildError as fresh_error:
        safe = _safe_existing_state_or_raise(destination, now=now)
        log.warning("fresh earnings wire source failed; retaining recent existing publication: %s", fresh_error)
        return BuildResult("existing", "existing", int(safe["article_count"]), destination)

    result = publish_public_wire(
        manifest,
        out_dir=destination,
        prior_state=state,
        company_reader=company_reader,
        now=now,
    )
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build receipt-bound public earnings-call records.")
    parser.add_argument("--out-dir", type=Path, default=None)
    parser.add_argument("--source-base", default=DEFAULT_SOURCE_BASE)
    parser.add_argument("--offline", action="store_true", help="Validate and retain a recent existing publication without fetching.")
    parser.add_argument(
        "--force", action="store_true",
        help="Rehydrate and render even when the verified source generations are unchanged.",
    )
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    try:
        result = build(
            out_dir=args.out_dir,
            source_base=args.source_base, offline=args.offline, force=args.force,
            workers=args.workers, timeout=args.timeout,
        )
    except PublicWireBuildError as exc:
        log.error("earnings public wire failed: %s", exc)
        return 1
    print(json.dumps({
        "schema": "earnings.public_wire_build_result/v1", "status": "ready",
        "source": result.source, "manifest_id": result.manifest_id,
        "article_count": result.article_count, "out_dir": str(result.output_dir),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
