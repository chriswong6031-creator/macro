"""Deterministic parsers for official U.S. macro release documents.

The publication watcher uses two deliberately small entry points:

``extract_feed_entry(feed_kind, body, event_date)``
    Selects the *exact* BLS Atom or BEA RSS item published on ``event_date``.
    It never falls back to the newest item, which prevents a stale release from
    being attributed to a later calendar event.

``parse_actual(parser_name, body)``
    Extracts a fail-closed display packet from an official feed entry or release
    page.  A parser returns ``None`` unless all headline fields for its release
    are present.

Only the Python standard library is used so these helpers stay available in the
small VPS live-update process.
"""
from __future__ import annotations

import html
import re
from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin
from xml.etree import ElementTree


_MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}
_CHANGE_WORDS = (
    r"rose|risen|increased|advanced|moved up|edged up|"
    r"fell|fallen|decreased|declined|moved down|edged down|"
    r"was unchanged|were unchanged|remained unchanged|unchanged"
)


def _event_day(value: date | str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _children(
    node: ElementTree.Element | None,
    name: str,
) -> list[ElementTree.Element]:
    if node is None:
        return []
    return [child for child in list(node) if _local_name(child.tag) == name]


def _child(
    node: ElementTree.Element | None,
    name: str,
) -> ElementTree.Element | None:
    values = _children(node, name)
    return values[0] if values else None


def _node_text(node: ElementTree.Element | None) -> str:
    if node is None:
        return ""
    return re.sub(r"\s+", " ", "".join(node.itertext())).strip()


def _child_text(node: ElementTree.Element, name: str) -> str:
    return _node_text(_child(node, name))


def _parse_atom_time(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _parse_rss_time(value: str) -> datetime | None:
    try:
        parsed = parsedate_to_datetime(value.strip())
    except (TypeError, ValueError, OverflowError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _utc_iso(value: datetime | None) -> str | None:
    return value.astimezone(timezone.utc).isoformat() if value else None


def _absolute_bea_url(value: str) -> str:
    value = value.strip()
    if value.startswith("//"):
        return "https:" + value
    if value and "://" not in value:
        return urljoin("https://www.bea.gov/", value)
    return value


def _period_from_month_text(text: str, released_at: datetime | None) -> str | None:
    explicit = re.search(
        r"\b("
        + "|".join(month.title() for month in _MONTHS)
        + r")\s+((?:19|20)\d{2})\b",
        text,
        flags=re.IGNORECASE,
    )
    if explicit:
        return f"{explicit.group(1).title()} {explicit.group(2)}"
    month_match = re.search(
        r"\b(?:in|ending in)\s+("
        + "|".join(month.title() for month in _MONTHS)
        + r")\b",
        text,
        flags=re.IGNORECASE,
    )
    if not month_match or released_at is None:
        return None
    month_name = month_match.group(1).title()
    month_number = _MONTHS[month_name.lower()]
    release_year = released_at.year
    # A December reference period normally appears in a January publication.
    period_year = release_year - 1 if month_number > released_at.month else release_year
    return f"{month_name} {period_year}"


def _period_from_quarter_text(text: str) -> str | None:
    match = re.search(
        r"\b(?:the\s+)?(first|second|third|fourth|1st|2nd|3rd|4th)"
        r"\s+quarter(?:\s+of)?\s+((?:19|20)\d{2})\b",
        text,
        flags=re.IGNORECASE,
    )
    if not match:
        match = re.search(
            r"\bQ([1-4])\s+((?:19|20)\d{2})\b",
            text,
            flags=re.IGNORECASE,
        )
        return f"Q{match.group(1)} {match.group(2)}" if match else None
    quarter = {
        "first": 1,
        "1st": 1,
        "second": 2,
        "2nd": 2,
        "third": 3,
        "3rd": 3,
        "fourth": 4,
        "4th": 4,
    }[match.group(1).lower()]
    return f"Q{quarter} {match.group(2)}"


def _entry_packet(
    *,
    title: str,
    content: str,
    source_url: str,
    released_at: datetime | None,
    entry_id: str,
    reference_period: str | None,
) -> dict[str, Any]:
    text = "\n".join(
        part
        for part in (
            title.strip(),
            content.strip(),
            f"Reference period: {reference_period}" if reference_period else "",
        )
        if part
    )
    return {
        "body": text.encode("utf-8"),
        "source_url": source_url,
        "source_released_at": _utc_iso(released_at),
        "title": title.strip(),
        "entry_id": entry_id.strip(),
        "reference_period": reference_period,
    }


class _DOLClaimsListingParser(HTMLParser):
    """Capture one exact-date claims teaser from the DOL ETA release listing."""

    def __init__(self, target_path: str) -> None:
        super().__init__(convert_charrefs=True)
        self.target_path = target_path
        self.capture_depth = 0
        self.title_depth = 0
        self.parts: list[str] = []
        self.title_parts: list[str] = []
        self.source_path = target_path
        self.done = False

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        attributes = {key: value or "" for key, value in attrs}
        about = attributes.get("about", "").strip()
        if not self.capture_depth and not self.done and about == self.target_path:
            self.capture_depth = 1
            self.source_path = about
        elif self.capture_depth:
            self.capture_depth += 1
        if self.capture_depth and tag.lower() == "h3":
            self.title_depth += 1
        if self.capture_depth and attributes.get("href", "").strip():
            href = re.sub(r"\s+", "", attributes["href"])
            if href.endswith(self.target_path):
                self.source_path = href

    def handle_endtag(self, tag: str) -> None:
        if not self.capture_depth:
            return
        if tag.lower() == "h3" and self.title_depth:
            self.title_depth -= 1
        self.capture_depth -= 1
        if self.capture_depth == 0:
            self.done = True

    def handle_data(self, data: str) -> None:
        if not self.capture_depth:
            return
        if data.strip():
            self.parts.append(data)
            if self.title_depth:
                self.title_parts.append(data)


def _extract_dol_claims_listing(
    body: bytes,
    event_day: date,
) -> dict[str, Any] | None:
    target_path = f"/newsroom/releases/eta/eta{event_day:%Y%m%d}"
    parser = _DOLClaimsListingParser(target_path)
    try:
        parser.feed(body.decode("utf-8", errors="ignore"))
        parser.close()
    except (TypeError, ValueError):
        return None
    if not parser.done:
        return None
    text = re.sub(r"\s+", " ", " ".join(parser.parts)).strip()
    title = re.sub(r"\s+", " ", " ".join(parser.title_parts)).strip()
    if (
        "unemployment insurance weekly claims" not in title.lower()
        or "initial claims was" not in text.lower()
    ):
        return None
    source_url = urljoin("https://www.dol.gov/", parser.source_path)
    return _entry_packet(
        title=title,
        content=text,
        source_url=source_url,
        released_at=None,
        entry_id=target_path,
        reference_period=None,
    )


def _extract_bls_atom(
    feed_kind: str,
    root: ElementTree.Element,
    event_day: date,
) -> dict[str, Any] | None:
    feed_id = _child_text(root, "id").lower()
    feed_title = _child_text(root, "title").lower()
    expected_markers = {
        "bls_cpi": (("feed:cpi",), ("consumer price index",)),
        "bls_ppi": (("feed:ppi",), ("producer price index",)),
        "bls_nfp": (("feed:empsit",), ("employment situation",)),
    }
    id_markers, title_markers = expected_markers[feed_kind]
    if not (
        any(marker in feed_id for marker in id_markers)
        or any(marker in feed_title for marker in title_markers)
    ):
        return None
    for entry in (node for node in root.iter() if _local_name(node.tag) == "entry"):
        published = _parse_atom_time(
            _child_text(entry, "published") or _child_text(entry, "updated")
        )
        if published is None or published.date() != event_day:
            continue
        title = _child_text(entry, "title")
        content = _child_text(entry, "content") or _child_text(entry, "summary")
        link_node = _child(entry, "link")
        source_url = ""
        if link_node is not None:
            source_url = str(link_node.attrib.get("href") or _node_text(link_node))
        return _entry_packet(
            title=title,
            content=content,
            source_url=source_url,
            released_at=published,
            entry_id=_child_text(entry, "id"),
            reference_period=_period_from_month_text(
                f"{title} {content}", published
            ),
        )
    return None


def _bea_item_matches(feed_kind: str, item: ElementTree.Element) -> bool:
    item_name = str(item.attrib.get("name") or "").strip().lower()
    title = _child_text(item, "title").lower()
    if feed_kind == "bea_gdp":
        return item_name == "gdp" or title.startswith("gdp ")
    if feed_kind == "bea_pce":
        return item_name == "personal income and outlays" or title.startswith(
            "personal income and outlays"
        )
    return False


def _extract_bea_rss(
    feed_kind: str,
    root: ElementTree.Element,
    event_day: date,
) -> dict[str, Any] | None:
    for item in (node for node in root.iter() if _local_name(node.tag) == "item"):
        if not _bea_item_matches(feed_kind, item):
            continue
        published = _parse_rss_time(_child_text(item, "pubDate"))
        if published is None or published.date() != event_day:
            continue
        title = _child_text(item, "title")
        description = _child_text(item, "description")
        source_url = _absolute_bea_url(
            _child_text(item, "link") or _child_text(item, "guid")
        )
        if feed_kind == "bea_gdp":
            reference_period = (
                _child_text(_child(_child(_child(item, "data"), "main"), "current"), "infoDate")
                or _period_from_quarter_text(f"{title} {description}")
            )
        else:
            reference_period = (
                _child_text(_child(_child(_child(item, "data"), "main"), "current"), "infoDate")
                or _period_from_month_text(f"{title} {description}", published)
            )
        return _entry_packet(
            title=title,
            content=description,
            source_url=source_url,
            released_at=published,
            entry_id=_child_text(item, "guid"),
            reference_period=reference_period or None,
        )
    return None


_FEED_KIND_ALIASES = {
    "bls_cpi": "bls_cpi",
    "bls_cpi_atom": "bls_cpi",
    "bls_ppi": "bls_ppi",
    "bls_ppi_atom": "bls_ppi",
    "bls_nfp": "bls_nfp",
    "bls_employment": "bls_nfp",
    "bls_empsit": "bls_nfp",
    "bls_empsit_atom": "bls_nfp",
    "bea_gdp": "bea_gdp",
    "bea_gdp_rss": "bea_gdp",
    "bea_pce": "bea_pce",
    "bea_pce_rss": "bea_pce",
    "dol_claims": "dol_claims",
    "dol_eta_claims": "dol_claims",
    "dol_eta_listing": "dol_claims",
}


def extract_feed_entry(
    feed_kind: str,
    body: bytes,
    event_date: date | str,
) -> dict[str, Any] | None:
    """Return the exact official feed entry published on ``event_date``.

    ``None`` is returned for malformed XML, unknown feed kinds, or a feed that
    contains no matching-date item.  Most importantly, no "latest item"
    fallback is attempted.
    """
    normalized_kind = _FEED_KIND_ALIASES.get(str(feed_kind).strip().lower())
    if normalized_kind is None or not body:
        return None
    try:
        day = _event_day(event_date)
    except (TypeError, ValueError):
        return None
    if normalized_kind == "dol_claims":
        return _extract_dol_claims_listing(body, day)
    try:
        root = ElementTree.fromstring(body)
    except ElementTree.ParseError:
        return None
    if normalized_kind.startswith("bls_"):
        return _extract_bls_atom(normalized_kind, root, day)
    return _extract_bea_rss(normalized_kind, root, day)


def _html_text(body: bytes) -> str:
    decoded = body.decode("utf-8", errors="ignore")
    decoded = re.sub(
        r"<(?:script|style)\b[^>]*>.*?</(?:script|style)>",
        " ",
        decoded,
        flags=re.IGNORECASE | re.DOTALL,
    )
    decoded = re.sub(r"<!--.*?-->", " ", decoded, flags=re.DOTALL)
    decoded = re.sub(r"<[^>]+>", " ", decoded)
    decoded = html.unescape(decoded)
    decoded = (
        decoded.replace("\u00a0", " ")
        .replace("\u2011", "-")
        .replace("\u2012", "-")
        .replace("\u2013", "-")
        .replace("\u2014", "-")
        .replace("\u2212", "-")
    )
    return re.sub(r"\s+", " ", decoded).strip()


def _number(value: str) -> float:
    return float(value.replace(",", "").strip())


def _signed_change(verb: str, value: str | None) -> float | None:
    normalized = re.sub(r"\s+", " ", verb.strip().lower())
    if "unchanged" in normalized:
        return 0.0
    if value is None:
        return None
    amount = _number(value)
    if any(
        word in normalized
        for word in ("fell", "fallen", "decreased", "declined", "down")
    ):
        return -amount
    return amount


def _change_after(
    text: str,
    label: str,
    *,
    max_gap: int = 40,
) -> float | None:
    match = re.search(
        label
        + rf".{{0,{max_gap}}}?\b(?P<verb>{_CHANGE_WORDS})\b"
        + r"(?:\s+(?:by\s+)?(?P<value>\d+(?:\.\d+)?))?\s*percent\b",
        text,
        flags=re.IGNORECASE,
    )
    if match:
        return _signed_change(match.group("verb"), match.group("value"))
    unchanged = re.search(
        label + rf".{{0,{max_gap}}}?\b(?:was|were|remained)?\s*unchanged\b",
        text,
        flags=re.IGNORECASE,
    )
    return 0.0 if unchanged else None


def _format_percent(value: float, *, sign: bool = True) -> str:
    return f"{value:+.1f}%" if sign else f"{value:.1f}%"


def _embedded_reference_period(text: str) -> str | None:
    match = re.search(
        r"\bReference period:\s*"
        r"((?:Q[1-4]|[A-Z][a-z]+)\s+(?:19|20)\d{2})\b",
        text,
    )
    return match.group(1) if match else None


def _metric(
    metric_id: str,
    value: int | float,
    unit: str,
    period: str | None,
) -> dict[str, Any]:
    return {
        "metric_id": metric_id,
        "value": value,
        "unit": unit,
        "period": period,
    }


def parse_cpi_actual(body: bytes) -> dict[str, Any] | None:
    """Parse headline and core CPI monthly/yearly changes from a BLS release."""
    text = _html_text(body)
    headline_mom = _change_after(
        text, r"Consumer Price Index for All Urban Consumers"
    )
    headline_yoy_match = re.search(
        rf"(?:Consumer Price Index for All Urban Consumers|the index for all items)"
        rf".{{0,180}}?\b(?P<verb>{_CHANGE_WORDS})\b"
        r"(?:\s+(?:by\s+)?(?P<value>\d+(?:\.\d+)?))?\s*percent"
        r"\s+over the last 12 months",
        text,
        flags=re.IGNORECASE,
    )
    headline_yoy = (
        _signed_change(
            headline_yoy_match.group("verb"), headline_yoy_match.group("value")
        )
        if headline_yoy_match
        else None
    )
    core_match = re.search(
        r"(?:the )?index for all items less food and energy"
        rf"\s+(?P<verb>{_CHANGE_WORDS})"
        r"(?:\s+(?:by\s+)?(?P<value>\d+(?:\.\d+)?))?\s*percent?"
        r".{0,100}?(?:\(SA\)|seasonally adjusted|;)",
        text,
        flags=re.IGNORECASE,
    )
    if not core_match:
        core_match = re.search(
            r"(?:the )?index for all items less food and energy"
            rf"\s+(?P<verb>{_CHANGE_WORDS})"
            r"(?:\s+(?:by\s+)?(?P<value>\d+(?:\.\d+)?))?\s*"
            r"(?:percent)?\s+in\s+[A-Z][a-z]+",
            text,
            flags=re.IGNORECASE,
        )
    core_mom = (
        _signed_change(core_match.group("verb"), core_match.group("value"))
        if core_match
        else None
    )
    core_yoy_match = re.search(
        r"(?:the )?index for all items less food and energy"
        r".{0,180}?"
        rf"\b(?P<verb>up|down|{_CHANGE_WORDS})\b"
        r"(?:\s+(?:by\s+)?(?P<value>\d+(?:\.\d+)?))?\s*percent"
        r"\s+over the year",
        text,
        flags=re.IGNORECASE,
    )
    core_yoy = (
        _signed_change(core_yoy_match.group("verb"), core_yoy_match.group("value"))
        if core_yoy_match
        else None
    )
    required = (headline_mom, headline_yoy, core_mom, core_yoy)
    if any(value is None for value in required):
        return None
    period = _embedded_reference_period(text) or _period_from_month_text(text, None)
    headline_en = (
        f"CPI {_format_percent(headline_mom)} m/m; "
        f"core {_format_percent(core_mom)}"
    )
    headline_zh = (
        f"消费者价格指数环比 {_format_percent(headline_mom)}；"
        f"核心环比 {_format_percent(core_mom)}"
    )
    return {
        "kind": "inflation",
        "headline_mom": headline_mom,
        "core_mom": core_mom,
        "headline_yoy": headline_yoy,
        "core_yoy": core_yoy,
        "unit": "percent",
        "reference_period": period,
        "metrics": [
            _metric("cpi_headline_mom", headline_mom, "percent", period),
            _metric("cpi_core_mom", core_mom, "percent", period),
            _metric("cpi_headline_yoy", headline_yoy, "percent", period),
            _metric("cpi_core_yoy", core_yoy, "percent", period),
        ],
        "headline_en": headline_en,
        "headline_zh": headline_zh,
        "summary_en": (
            f"{headline_en}. Year over year: "
            f"{_format_percent(headline_yoy, sign=False)} headline and "
            f"{_format_percent(core_yoy, sign=False)} core."
        ),
        "summary_zh": (
            f"{headline_zh}。同比：整体 {_format_percent(headline_yoy, sign=False)}，"
            f"核心 {_format_percent(core_yoy, sign=False)}。"
        ),
    }


def parse_ppi_actual(body: bytes) -> dict[str, Any] | None:
    """Parse final-demand PPI headline, goods, services, and yearly changes."""
    text = _html_text(body)
    headline_mom = _change_after(text, r"Producer Price Index for final demand")
    goods_mom = _change_after(
        text, r"(?:Prices|the index) for final demand\s+goods"
    )
    services_mom = _change_after(
        text, r"(?:Prices|the index) for final demand\s+services"
    )
    yoy_match = re.search(
        r"(?:Prices|the index) for final demand"
        rf".{{0,80}}?\b(?P<verb>{_CHANGE_WORDS})\b"
        r"(?:\s+(?:by\s+)?(?P<value>\d+(?:\.\d+)?))?\s*percent"
        r"\s+for the 12 months ended",
        text,
        flags=re.IGNORECASE,
    )
    headline_yoy = (
        _signed_change(yoy_match.group("verb"), yoy_match.group("value"))
        if yoy_match
        else None
    )
    required = (headline_mom, goods_mom, services_mom, headline_yoy)
    if any(value is None for value in required):
        return None
    period = _embedded_reference_period(text) or _period_from_month_text(text, None)
    headline_en = (
        f"PPI {_format_percent(headline_mom)} m/m; "
        f"goods {_format_percent(goods_mom)}, "
        f"services {_format_percent(services_mom)}"
    )
    headline_zh = (
        f"生产者价格指数环比 {_format_percent(headline_mom)}；"
        f"商品 {_format_percent(goods_mom)}，"
        f"服务 {_format_percent(services_mom)}"
    )
    return {
        "kind": "producer_prices",
        "headline_mom": headline_mom,
        "headline_yoy": headline_yoy,
        "goods_mom": goods_mom,
        "services_mom": services_mom,
        "unit": "percent",
        "reference_period": period,
        "metrics": [
            _metric("ppi_headline_mom", headline_mom, "percent", period),
            _metric("ppi_headline_yoy", headline_yoy, "percent", period),
            _metric("ppi_goods_mom", goods_mom, "percent", period),
            _metric("ppi_services_mom", services_mom, "percent", period),
        ],
        "headline_en": headline_en,
        "headline_zh": headline_zh,
        "summary_en": (
            f"{headline_en}. Final demand was "
            f"{_format_percent(headline_yoy, sign=False)} higher year over year."
        ),
        "summary_zh": (
            f"{headline_zh}。最终需求同比 "
            f"{_format_percent(headline_yoy, sign=False)}。"
        ),
    }


def _payroll_change(text: str) -> int | None:
    parenthetical = re.search(
        r"total nonfarm payroll employment\s*\(\s*([+-]?\d[\d,]*)\s*\)",
        text,
        flags=re.IGNORECASE,
    )
    if parenthetical:
        return int(parenthetical.group(1).replace(",", ""))
    phrase = re.search(
        r"total nonfarm payroll employment\s+"
        r"(?P<verb>increased|rose|edged up|decreased|fell|declined|edged down)"
        r"(?:\s+by)?\s+(?P<value>[+-]?\d[\d,]*)",
        text,
        flags=re.IGNORECASE,
    )
    if not phrase:
        return None
    amount = int(phrase.group("value").replace(",", "").lstrip("+"))
    if any(
        word in phrase.group("verb").lower()
        for word in ("decreased", "fell", "declined", "down")
    ):
        amount = -abs(amount)
    return amount


def parse_nfp_actual(body: bytes) -> dict[str, Any] | None:
    """Parse the payroll change and unemployment rate from a BLS release."""
    text = _html_text(body)
    payroll_change = _payroll_change(text)
    unemployment = re.search(
        r"unemployment rate.{0,55}?(\d+(?:\.\d+)?)\s*percent",
        text,
        flags=re.IGNORECASE,
    )
    if payroll_change is None or not unemployment:
        return None
    unemployment_rate = _number(unemployment.group(1))
    period_match = re.search(
        r"(?:employment|unemployment rate).{0,100}?\bin\s+([A-Z][a-z]+)\b",
        text,
        flags=re.IGNORECASE,
    )
    period = (
        _embedded_reference_period(text)
        or (period_match.group(1).title() if period_match else None)
    )
    payroll_text = f"{payroll_change / 1_000:+.0f}k"
    headline_en = (
        f"Payrolls {payroll_text}; unemployment "
        f"{_format_percent(unemployment_rate, sign=False)}"
    )
    headline_zh = (
        f"非农就业 {payroll_text}；失业率 "
        f"{_format_percent(unemployment_rate, sign=False)}"
    )
    return {
        "kind": "employment",
        "payroll_change": payroll_change,
        "unemployment_rate": unemployment_rate,
        "unit": "persons",
        "reference_period": period,
        "metrics": [
            _metric("nfp_payroll_change", payroll_change, "persons", period),
            _metric("nfp_unemployment_rate", unemployment_rate, "percent", period),
        ],
        "headline_en": headline_en,
        "headline_zh": headline_zh,
        "summary_en": headline_en + ".",
        "summary_zh": headline_zh + "。",
    }


def parse_gdp_actual(body: bytes) -> dict[str, Any] | None:
    """Parse annualized real GDP growth from a BEA GDP release page."""
    text = _html_text(body)
    current = re.search(
        r"Real gross domestic product\s*\(GDP\)\s+"
        rf"(?P<verb>{_CHANGE_WORDS})\s+at an annual rate of\s+"
        r"(?P<value>\d+(?:\.\d+)?)\s+percent\s+in\s+"
        r"(?:the\s+)?(?P<quarter>first|second|third|fourth|1st|2nd|3rd|4th)"
        r"\s+quarter(?:\s+of)?\s+(?P<year>(?:19|20)\d{2})",
        text,
        flags=re.IGNORECASE,
    )
    if not current:
        return None
    real_gdp = _signed_change(current.group("verb"), current.group("value"))
    if real_gdp is None:
        return None
    quarter = {
        "first": 1,
        "1st": 1,
        "second": 2,
        "2nd": 2,
        "third": 3,
        "3rd": 3,
        "fourth": 4,
        "4th": 4,
    }[current.group("quarter").lower()]
    reference_period = f"Q{quarter} {current.group('year')}"
    remainder = text[current.end() :]
    prior_match = re.search(
        r"In\s+the\s+(?:first|second|third|fourth|1st|2nd|3rd|4th)"
        r"\s+quarter(?:\s+of\s+(?:19|20)\d{2})?,?\s+"
        r"real GDP\s+"
        rf"(?P<verb>{_CHANGE_WORDS})\s+"
        r"(?P<value>\d+(?:\.\d+)?)\s+percent",
        remainder,
        flags=re.IGNORECASE,
    )
    prior = (
        _signed_change(prior_match.group("verb"), prior_match.group("value"))
        if prior_match
        else None
    )
    vintage_match = re.search(
        r"\b(advance|initial|second|third)\s+estimate\b",
        text,
        flags=re.IGNORECASE,
    )
    vintage = vintage_match.group(1).lower() if vintage_match else None
    headline_en = (
        f"Real GDP {_format_percent(real_gdp)} annualized "
        f"({reference_period})"
    )
    headline_zh = (
        f"实际 GDP 年化 {_format_percent(real_gdp)}"
        f"（{reference_period}）"
    )
    summary_en = headline_en + "."
    summary_zh = headline_zh + "。"
    if prior is not None:
        summary_en += f" Previous quarter: {_format_percent(prior)}."
        summary_zh += f" 上季度：{_format_percent(prior)}。"
    return {
        "kind": "economic_growth",
        "real_gdp_annualized": real_gdp,
        "prior_real_gdp_annualized": prior,
        "vintage": vintage,
        "unit": "percent",
        "reference_period": reference_period,
        "metrics": [
            _metric(
                "gdp_real_annualized",
                real_gdp,
                "percent_annualized",
                reference_period,
            )
        ],
        "headline_en": headline_en,
        "headline_zh": headline_zh,
        "summary_en": summary_en,
        "summary_zh": summary_zh,
    }


def _pce_section_change(section: str, *, core: bool) -> float | None:
    if core:
        label = r"Excluding food and energy,?\s+the PCE price index"
    else:
        label = r"(?:the\s+)?PCE price index"
    return _change_after(section, label)


def parse_pce_actual(body: bytes) -> dict[str, Any] | None:
    """Parse headline/core PCE price changes from a BEA PIO release page."""
    text = _html_text(body)
    monthly = re.search(
        r"From the preceding month,?(?P<body>.*?)(?="
        r"From the same month one year ago|$)",
        text,
        flags=re.IGNORECASE,
    )
    yearly = re.search(
        r"From the same month one year ago,?(?P<body>.*?)(?="
        r"(?:The increase|The decrease|Personal income|$))",
        text,
        flags=re.IGNORECASE,
    )
    if not monthly or not yearly:
        return None
    headline_mom = _pce_section_change(monthly.group("body"), core=False)
    core_mom = _pce_section_change(monthly.group("body"), core=True)
    headline_yoy = _pce_section_change(yearly.group("body"), core=False)
    core_yoy = _pce_section_change(yearly.group("body"), core=True)
    required = (headline_mom, core_mom, headline_yoy, core_yoy)
    if any(value is None for value in required):
        return None
    period_match = re.search(
        r"Personal Income and Outlays,?\s+("
        + "|".join(month.title() for month in _MONTHS)
        + r")\s+((?:19|20)\d{2})",
        text,
        flags=re.IGNORECASE,
    )
    period = (
        f"{period_match.group(1).title()} {period_match.group(2)}"
        if period_match
        else None
    )
    headline_en = (
        f"PCE prices {_format_percent(headline_mom)} m/m; "
        f"core {_format_percent(core_mom)}"
    )
    headline_zh = (
        f"PCE 价格环比 {_format_percent(headline_mom)}；"
        f"核心环比 {_format_percent(core_mom)}"
    )
    return {
        "kind": "pce_inflation",
        "headline_mom": headline_mom,
        "core_mom": core_mom,
        "headline_yoy": headline_yoy,
        "core_yoy": core_yoy,
        "unit": "percent",
        "reference_period": period,
        "metrics": [
            _metric("pce_headline_mom", headline_mom, "percent", period),
            _metric("pce_core_mom", core_mom, "percent", period),
            _metric("pce_headline_yoy", headline_yoy, "percent", period),
            _metric("pce_core_yoy", core_yoy, "percent", period),
        ],
        "headline_en": headline_en,
        "headline_zh": headline_zh,
        "summary_en": (
            f"{headline_en}. Year over year: "
            f"{_format_percent(headline_yoy, sign=False)} headline and "
            f"{_format_percent(core_yoy, sign=False)} core."
        ),
        "summary_zh": (
            f"{headline_zh}。同比：整体 {_format_percent(headline_yoy, sign=False)}，"
            f"核心 {_format_percent(core_yoy, sign=False)}。"
        ),
    }


def parse_claims_actual(body: bytes) -> dict[str, Any] | None:
    """Parse weekly initial claims facts from a DOL ETA release page."""
    text = _html_text(body)
    claims = re.search(
        r"In the week ending\s+(?P<week>[A-Z][a-z]+\s+\d{1,2})"
        r",.{0,180}?initial claims was\s+(?P<actual>\d[\d,]*)"
        r",\s+an?\s+(?P<direction>increase|decrease)"
        r"\s+of\s+(?P<change>\d[\d,]*)",
        text,
        flags=re.IGNORECASE,
    )
    average = re.search(
        r"(?:The\s+)?4-week moving average was\s+(\d[\d,]*)",
        text,
        flags=re.IGNORECASE,
    )
    if not claims or not average:
        return None
    actual = int(claims.group("actual").replace(",", ""))
    change = int(claims.group("change").replace(",", ""))
    if claims.group("direction").lower() == "decrease":
        change = -change
    prior = actual - change
    four_week_average = int(average.group(1).replace(",", ""))
    release_date_match = re.search(
        r"\b("
        + "|".join(month.title() for month in _MONTHS)
        + r")\s+\d{1,2},\s+((?:19|20)\d{2})\b",
        text,
        flags=re.IGNORECASE,
    )
    reference_period = claims.group("week").title()
    if release_date_match:
        reference_period += f", {release_date_match.group(2)}"
    headline_en = f"Initial claims {actual / 1_000:.0f}k ({change / 1_000:+.0f}k)"
    headline_zh = f"初请失业金 {actual / 1_000:.0f}千（{change / 1_000:+.0f}千）"
    return {
        "kind": "jobless_claims",
        "initial_claims": actual,
        "change": change,
        "prior_initial_claims": prior,
        "four_week_average": four_week_average,
        "unit": "persons",
        "reference_period": reference_period,
        "metrics": [
            _metric("claims_initial", actual, "persons", reference_period),
            _metric("claims_change", change, "persons", reference_period),
            _metric(
                "claims_four_week_avg",
                four_week_average,
                "persons",
                reference_period,
            ),
        ],
        "headline_en": headline_en,
        "headline_zh": headline_zh,
        "summary_en": (
            f"{headline_en} for the week ending {reference_period}; "
            f"four-week average {four_week_average / 1_000:.1f}k."
        ),
        "summary_zh": (
            f"{headline_zh}，截至 {reference_period} 当周；"
            f"四周均值 {four_week_average / 1_000:.1f}千。"
        ),
    }


_PARSERS = {
    "cpi": parse_cpi_actual,
    "ppi": parse_ppi_actual,
    "nfp": parse_nfp_actual,
    "employment": parse_nfp_actual,
    "gdp": parse_gdp_actual,
    "pce": parse_pce_actual,
    "claims": parse_claims_actual,
}


def parse_actual(parser_name: str, body: bytes) -> dict[str, Any] | None:
    """Run a named official-release parser, returning ``None`` fail-closed."""
    parser = _PARSERS.get(str(parser_name).strip().lower())
    if parser is None or not body:
        return None
    return parser(body)
