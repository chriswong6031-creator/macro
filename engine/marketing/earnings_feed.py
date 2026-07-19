"""engine.marketing.earnings_feed — Pluggable provider seam for earnings events.

Produces a stream of earnings release dicts for the real-time fast lane daemon.

Public API:
    fetch_events(since, *, provider=None) -> list[dict]

Event dict schema:
    {
        "id":          str,        # deterministic: "<TICKER>-<quarter>-<source>"
        "ticker":      str,        # uppercase
        "when":        str,        # ISO-8601 datetime or date ("YYYY-MM-DDTHH:MM:SS")
        "eps_actual":  float,
        "eps_est":     float,
        "rev_actual":  float | None,
        "rev_est":     float | None,
        "quarter":     str | None,  # e.g. "Q2 2026"
        "source":      str,         # provider id string
    }

Providers:
    FreePollProvider  — best-effort public earnings-wire poll.  Returns []
                        on ANY failure (network, bad response, error banner in body).
    PaidProviderStub  — reads env EARNINGS_API_KEY; returns [] with a log line
                        when the key is absent.  Full implementation deferred to W1.

Design contract:
    - fetch_events(since, provider=None) selects FreePollProvider when provider is
      None; the test suite injects a fake provider — never hits the network.
    - ALL providers must be fail-soft: return [] rather than raise on any error.
    - Classify response TEXT strictly: an ok-looking HTTP 200 can carry an error
      banner in the body (see memory mm-bot-key-rotation).  Providers must inspect
      the body, not just the status code.
"""
from __future__ import annotations

import hashlib
import logging
import os
from datetime import datetime, timezone
from typing import Any, Protocol

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Provider protocol
# ─────────────────────────────────────────────────────────────────────────────

class EarningsProvider(Protocol):
    """Any callable that accepts a since-datetime and returns event dicts."""

    def fetch(self, since: datetime) -> list[dict[str, Any]]:
        ...


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _event_id(ticker: str, quarter: str | None, source: str) -> str:
    """Deterministic opaque event id from ticker + quarter + source."""
    raw = f"{ticker.upper()}-{quarter or 'unk'}-{source}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _looks_like_error_body(text: str) -> bool:
    """Return True if the response body carries an error banner.

    Classify strictly — a polished 200 response can embed:
      "error", "rate limit", "forbidden", "unauthorized", etc.
    """
    low = text.lower()
    error_markers = (
        '"error"',
        '"message":',
        "rate limit",
        "rate_limit",
        "forbidden",
        "unauthorized",
        "access denied",
        "too many requests",
        "invalid api",
        "api key",
        "subscription required",
        "no data",
        "not found",
        "<html",
        "503 service",
        "502 bad gateway",
    )
    return any(m in low for m in error_markers)


# ─────────────────────────────────────────────────────────────────────────────
# FreePollProvider — best-effort public-RSS/wire poll
# ─────────────────────────────────────────────────────────────────────────────

_FREE_SOURCE_ID = "free_poll"

# Public Finviz earnings calendar RSS endpoint (no key required, polite ~120s interval).
# Returns an RSS/XML feed.  We parse ticker + EPS if parseable; return [] otherwise.
_FINVIZ_RSS_URL = "https://finviz.com/rss.ashx?v=3&auth=0"


class FreePollProvider:
    """Best-effort public earnings-wire poll.

    Polls a public earnings RSS/JSON feed.  Returns [] on ANY failure —
    network timeout, non-200, error banner in body, or parse exception.

    UA is set politely.  Timeout is short (5 s) to keep the daemon loop snappy.

    The free-poll data model is EPS-only (no revenue); eps_est may be None when
    the feed omits consensus.  The caller (fastlane.run_tick) handles those nulls.
    """

    _UA = "Mozilla/5.0 (compatible; MacroDashboard/1.0; +https://mastermind-x.com)"
    _TIMEOUT_S = 5

    def fetch(self, since: datetime) -> list[dict[str, Any]]:  # noqa: ARG002
        try:
            import urllib.request  # stdlib only — no requests dep required
            req = urllib.request.Request(
                _FINVIZ_RSS_URL,
                headers={"User-Agent": self._UA},
            )
            with urllib.request.urlopen(req, timeout=self._TIMEOUT_S) as resp:  # noqa: S310
                raw = resp.read().decode("utf-8", errors="replace")

            if _looks_like_error_body(raw):
                logger.warning(
                    "[earnings_feed] FreePollProvider: error banner in response body — returning []"
                )
                return []

            return self._parse(raw, since)

        except Exception as exc:  # noqa: BLE001
            logger.debug("[earnings_feed] FreePollProvider.fetch() swallowed: %s", exc)
            return []

    def _parse(self, raw: str, since: datetime) -> list[dict[str, Any]]:
        """Parse the feed text.  Returns [] on any parse error."""
        try:
            return self._parse_rss(raw, since)
        except Exception as exc:  # noqa: BLE001
            logger.debug("[earnings_feed] FreePollProvider._parse() error: %s", exc)
            return []

    def _parse_rss(self, raw: str, since: datetime) -> list[dict[str, Any]]:
        """Attempt minimal RSS/XML parse for earnings items."""
        import xml.etree.ElementTree as ET  # stdlib

        root = ET.fromstring(raw)
        items: list[dict[str, Any]] = []
        ns = {"atom": "http://www.w3.org/2005/Atom"}

        # Try both <item> (RSS 2) and <entry> (Atom)
        entries = root.findall(".//item") or root.findall(".//entry", ns)
        for entry in entries:
            try:
                item = self._parse_rss_entry(entry, since, ns)
                if item:
                    items.append(item)
            except Exception:  # noqa: BLE001
                continue

        return items

    def _parse_rss_entry(
        self, entry: Any, since: datetime, ns: dict
    ) -> dict[str, Any] | None:
        """Parse one RSS/Atom entry into an event dict.  Returns None to skip."""
        import xml.etree.ElementTree as ET  # stdlib

        # Try to extract a ticker symbol from <title> or <link>
        title_el = entry.find("title") or entry.find("title", ns)
        title = (title_el.text or "") if title_el is not None else ""

        # Look for a pattern like "$AAPL" or "AAPL earnings"
        import re
        ticker_m = re.search(r"\$([A-Z]{1,5})", title) or re.search(
            r"\b([A-Z]{1,5})\s+(?:earnings|EPS|results|reports?)\b", title
        )
        if not ticker_m:
            return None
        ticker = ticker_m.group(1)

        # Published time
        pub_el = (
            entry.find("pubDate")
            or entry.find("published", ns)
            or entry.find("updated", ns)
        )
        pub_text = (pub_el.text or "") if pub_el is not None else ""
        when_dt = _parse_pub_date(pub_text)
        if when_dt is None:
            when_dt = datetime.now(timezone.utc)

        if when_dt < since:
            return None

        # Attempt to extract EPS from description/summary
        desc_el = (
            entry.find("description")
            or entry.find("summary", ns)
            or entry.find("content", ns)
        )
        desc = (desc_el.text or "") if desc_el is not None else ""

        eps_actual, eps_est = _extract_eps_from_text(desc or title)

        if eps_actual is None:
            # Cannot post without an actual figure
            return None

        quarter = _extract_quarter_from_text(desc or title)
        event_id = _event_id(ticker, quarter, _FREE_SOURCE_ID)

        return {
            "id": event_id,
            "ticker": ticker.upper(),
            "when": when_dt.strftime("%Y-%m-%dT%H:%M:%S"),
            "eps_actual": eps_actual,
            "eps_est": eps_est if eps_est is not None else eps_actual,
            "rev_actual": None,
            "rev_est": None,
            "quarter": quarter,
            "source": _FREE_SOURCE_ID,
        }


def _parse_pub_date(text: str) -> datetime | None:
    """Parse RFC-2822 or ISO-8601 date strings to UTC datetime."""
    if not text:
        return None
    text = text.strip()
    formats = [
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S GMT",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%d",
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(text, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except ValueError:
            continue
    return None


def _extract_eps_from_text(text: str) -> tuple[float | None, float | None]:
    """Return (eps_actual, eps_est) from a text string, or (None, None)."""
    import re
    # Match "EPS: $X.XX vs $Y.YY" or similar
    m = re.search(
        r"EPS[:\s]+\$?([\-\d\.]+)\s*(?:vs\.?|versus|est(?:imate)?[:\s]*)\$?([\-\d\.]+)",
        text,
        re.IGNORECASE,
    )
    if m:
        try:
            return float(m.group(1)), float(m.group(2))
        except (ValueError, AttributeError):
            pass

    # Match bare "reported $X.XX"
    m2 = re.search(r"reported\s+\$?([\-\d\.]+)", text, re.IGNORECASE)
    if m2:
        try:
            return float(m2.group(1)), None
        except ValueError:
            pass

    return None, None


def _extract_quarter_from_text(text: str) -> str | None:
    """Return "Q2 2026"-style label if extractable, else None."""
    import re
    m = re.search(r"(Q[1-4])\s*(\d{4})", text, re.IGNORECASE)
    if m:
        return f"{m.group(1).upper()} {m.group(2)}"
    return None


# ─────────────────────────────────────────────────────────────────────────────
# PaidProviderStub — placeholder for a low-latency paid feed (W1)
# ─────────────────────────────────────────────────────────────────────────────

_PAID_SOURCE_ID = "paid_feed"
_PAID_KEY_ENV = "EARNINGS_API_KEY"


class PaidProviderStub:
    """Stub for a paid low-latency earnings feed (W1 implementation).

    When EARNINGS_API_KEY is unset, logs a note and returns [].
    The full implementation (low-latency WebSocket or polling feed) is
    deferred to W1 once the operator provisions the key.
    """

    def fetch(self, since: datetime) -> list[dict[str, Any]]:  # noqa: ARG002
        key = os.environ.get(_PAID_KEY_ENV, "")
        if not key:
            logger.info(
                "[earnings_feed] PaidProviderStub: %s not set — returning []. "
                "Provision the key in W1 for the low-latency feed.",
                _PAID_KEY_ENV,
            )
            return []
        # Full implementation deferred to W1.
        logger.info(
            "[earnings_feed] PaidProviderStub: key present but implementation "
            "is a W1 deliverable — returning []."
        )
        return []


# ─────────────────────────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────────────────────────

def fetch_events(
    since: datetime,
    *,
    provider: EarningsProvider | None = None,
) -> list[dict[str, Any]]:
    """Return earnings events newer than *since*.

    Args:
        since: Only return events whose ``when`` is at or after this datetime.
               Must be timezone-aware (UTC).
        provider: Injectable provider (EarningsProvider protocol).  Defaults to
                  FreePollProvider().  Tests pass a fixture provider here so the
                  suite never hits the network.

    Returns:
        List of event dicts (see module docstring for schema).  Always a list,
        never raises.
    """
    if provider is None:
        provider = FreePollProvider()
    try:
        return provider.fetch(since)
    except Exception as exc:  # noqa: BLE001
        logger.error("[earnings_feed] fetch_events swallowed top-level error: %s", exc)
        return []
