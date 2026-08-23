"""FIF-3A1/3A2 filing-native statement graph.

Walks presentation/calculation/label linkbases and joins them to the strict
offline iXBRL parse. Displayed row/column composition for the bounded AAPL
golden filing set comes from the captured primary HTML tables, not from raw
hypercube order. Deterministic. No network. No implicit now. No LLM.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Mapping
from xml.etree import ElementTree as ET

from collectors.sec_filing_parser import parse_sec_filing_document

LINK = "http://www.xbrl.org/2003/linkbase"
XLINK = "http://www.w3.org/1999/xlink"
XML = "http://www.w3.org/XML/1998/namespace"

LABEL_STANDARD = "http://www.xbrl.org/2003/role/label"
LABEL_TERSE = "http://www.xbrl.org/2003/role/terseLabel"
LABEL_PERIOD_START = "http://www.xbrl.org/2003/role/periodStartLabel"
LABEL_PERIOD_END = "http://www.xbrl.org/2003/role/periodEndLabel"

PRIMARY_STATEMENT_ROLES: dict[str, str] = {
    "income_statement": "http://www.apple.com/role/CONSOLIDATEDSTATEMENTSOFOPERATIONS",
    "balance_sheet": "http://www.apple.com/role/CONSOLIDATEDBALANCESHEETS",
    "cash_flow": "http://www.apple.com/role/CONSOLIDATEDSTATEMENTSOFCASHFLOWS",
}

STATEMENT_TITLES: dict[str, str] = {
    "income_statement": "CONSOLIDATED STATEMENTS OF OPERATIONS",
    "balance_sheet": "CONSOLIDATED BALANCE SHEETS",
    "cash_flow": "CONSOLIDATED STATEMENTS OF CASH FLOWS",
}

_ABSTRACT_TOKENS = (
    "Abstract",
    "Axis",
    "Domain",
    "Member",
    "Table",
    "LineItems",
)
_PERIOD_BANNER_LABELS = frozenset(
    {
        "years ended",
        "three months ended",
        "six months ended",
        "nine months ended",
        "twelve months ended",
    }
)

_PREFIXES = (
    "us-gaap_",
    "srt_",
    "dei_",
    "ecd_",
    "country_",
    "apple_",
    "aapl_",
    "iso4217_",
)

_MAX_LINKBASE_BYTES = 8 * 1024 * 1024
_MAX_ARCS = 20_000
_FORBIDDEN_DECL = b"<!DOCTYPE", b"<!ENTITY"
GOLDEN_AAPL_FIXTURES: dict[str, str] = {
    "0000320193-25-000079": "tests/fixtures/fundamental_forensics/aapl_10k_2025",
    "0000320193-26-000020": "tests/fixtures/fundamental_forensics/aapl_10q_2026q3",
}
_DEFAULT_GOLDEN_ACCESSION = "0000320193-25-000079"
_RELATED_EVENT_REF_KEYS = frozenset(
    {"plane", "event_id", "relation", "source_filing_distinction"}
)
_DATE_RE = re.compile(
    r"(January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s+(\d{1,2}),\s*(\d{4})",
    re.I,
)
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


class StatementGraphError(ValueError):
    """The filing package cannot yield an as-reported statement tree."""


@dataclass(frozen=True)
class GoldenFilingPackage:
    """Pinned AAPL 10-K members plus the complete archive inventory."""

    manifest: dict[str, Any]
    members: dict[str, bytes]


def mint_fixture_recorded_at(now: datetime | None = None) -> str:
    """Capture-process clock. Request time must never mint this."""
    stamp = now or datetime.now(timezone.utc)
    if stamp.tzinfo is None:
        raise StatementGraphError("fixture_recorded_at requires an aware UTC clock")
    return stamp.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_json_object(path: Path, *, name: str) -> dict[str, Any]:
    raw = path.read_bytes()
    if _FORBIDDEN_DECL[0] in raw or b"\x00" in raw:
        raise StatementGraphError(f"{name} is malformed")
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise StatementGraphError(f"{name} is malformed") from exc
    if not isinstance(parsed, dict):
        raise StatementGraphError(f"{name} is malformed")
    return parsed


def _admit_statement_roles(manifest: Mapping[str, Any]) -> None:
    extras = manifest.get("statement_roles")
    if extras is None:
        return
    if not isinstance(extras, dict):
        raise StatementGraphError("golden AAPL statement_roles are malformed")
    for kind in ("income_statement", "balance_sheet", "cash_flow"):
        spec = extras.get(kind)
        if not isinstance(spec, dict):
            raise StatementGraphError(f"golden AAPL statement role is missing: {kind}")
        if not isinstance(spec.get("role_uri"), str) or not spec["role_uri"]:
            raise StatementGraphError(f"golden AAPL statement role_uri is missing: {kind}")
        if not isinstance(spec.get("title"), str) or not spec["title"]:
            raise StatementGraphError(f"golden AAPL statement title is missing: {kind}")


def _admit_related_event_ref(manifest: Mapping[str, Any]) -> None:
    raw = manifest.get("related_event_ref")
    if raw is None:
        return
    if not isinstance(raw, dict) or set(raw) != _RELATED_EVENT_REF_KEYS:
        raise StatementGraphError("golden AAPL related_event_ref is not the stable reference")
    if "generation_id" in raw:
        raise StatementGraphError("golden AAPL related_event_ref must not mint generation identity")
    if not all(isinstance(raw.get(key), str) and raw[key] for key in ("plane", "event_id", "relation")):
        raise StatementGraphError("golden AAPL related_event_ref is not the stable reference")
    distinction = raw.get("source_filing_distinction")
    if not isinstance(distinction, dict):
        raise StatementGraphError("golden AAPL related_event_ref is not the stable reference")
    eight_k = distinction.get("earnings_release_8k_accession")
    periodic = distinction.get("periodic_report_accession")
    if not isinstance(eight_k, str) or not isinstance(periodic, str) or not eight_k or not periodic:
        raise StatementGraphError("golden AAPL related_event_ref is not the stable reference")
    if eight_k == periodic:
        raise StatementGraphError("golden AAPL related_event_ref collapses distinct filings")
    if periodic != manifest.get("accession"):
        raise StatementGraphError("golden AAPL related_event_ref is not bound to this filing")


def admit_golden_aapl_package(fixture: Path) -> GoldenFilingPackage:
    """Strictly admit the committed AAPL package. No network. No writes."""
    fixture = Path(fixture)
    manifest = _load_json_object(fixture / "package_manifest.json", name="golden AAPL package manifest")
    index_path = fixture / "index.json"
    if not index_path.is_file():
        raise StatementGraphError("golden AAPL archive index is missing")
    index_bytes = index_path.read_bytes()
    index_sha = hashlib.sha256(index_bytes).hexdigest()
    if index_sha != manifest.get("index_sha256"):
        raise StatementGraphError("golden AAPL archive index digest mismatch")
    if len(index_bytes) != manifest.get("index_byte_length"):
        raise StatementGraphError("golden AAPL archive index length mismatch")
    try:
        index_payload = json.loads(index_bytes.decode("utf-8"))
        items = index_payload["directory"]["item"]
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise StatementGraphError("golden AAPL archive index is malformed") from exc
    if not isinstance(items, list):
        raise StatementGraphError("golden AAPL archive index is malformed")
    index_names = [str(item.get("name") or "") for item in items]
    if any(not name for name in index_names):
        raise StatementGraphError("golden AAPL archive index has an unnamed member")
    if len(index_names) != len(set(index_names)):
        raise StatementGraphError("golden AAPL archive index has duplicate members")
    members_meta = manifest.get("members")
    if not isinstance(members_meta, list):
        raise StatementGraphError("golden AAPL package inventory is malformed")
    manifest_names = [str(item.get("name") or "") for item in members_meta]
    if any(not name for name in manifest_names):
        raise StatementGraphError("golden AAPL package inventory has an unnamed member")
    if len(manifest_names) != len(set(manifest_names)):
        raise StatementGraphError("golden AAPL package inventory has duplicate members")
    extra = set(manifest_names) - set(index_names)
    missing = set(index_names) - set(manifest_names)
    if extra or missing:
        raise StatementGraphError("golden AAPL package inventory does not match the archive index")
    committed = manifest.get("member_count")
    if not isinstance(committed, int) or committed < 1 or len(index_names) != committed:
        raise StatementGraphError("golden AAPL package inventory count does not match the committed index")
    _admit_statement_roles(manifest)
    _admit_related_event_ref(manifest)

    witness_meta = manifest.get("acceptance_witness")
    if not isinstance(witness_meta, dict) or not isinstance(witness_meta.get("path"), str):
        raise StatementGraphError("golden AAPL acceptance witness is missing")
    witness_path = fixture / str(witness_meta["path"])
    if not witness_path.is_file():
        raise StatementGraphError("golden AAPL acceptance witness is missing")
    witness_bytes = witness_path.read_bytes()
    if hashlib.sha256(witness_bytes).hexdigest() != witness_meta.get("content_sha256"):
        raise StatementGraphError("golden AAPL acceptance witness digest mismatch")
    if len(witness_bytes) != witness_meta.get("byte_length"):
        raise StatementGraphError("golden AAPL acceptance witness length mismatch")
    witness = _load_json_object(witness_path, name="golden AAPL acceptance witness")
    expected_bind = {
        "accession": "accessionNumber",
        "form": "form",
        "primary_document": "primaryDocument",
        "period_of_report": "reportDate",
        "filing_date": "filingDate",
        "source_accepted_at": "acceptanceDateTime",
    }
    for manifest_field, witness_field in expected_bind.items():
        if manifest.get(manifest_field) != witness.get(witness_field):
            raise StatementGraphError(f"golden AAPL {manifest_field} is not bound to the acceptance witness")
    if not isinstance(manifest.get("fixture_recorded_at"), str) or not manifest["fixture_recorded_at"]:
        raise StatementGraphError("golden AAPL fixture_recorded_at is missing")

    members: dict[str, bytes] = {}
    stored_count = 0
    for item in members_meta:
        if not isinstance(item, dict):
            raise StatementGraphError("golden AAPL stored member is malformed")
        name = item.get("name")
        if item.get("state") != "stored":
            continue
        stored_count += 1
        if name not in set(index_names):
            raise StatementGraphError(f"golden AAPL stored member is not in the archive index: {name}")
        rel = item.get("path")
        if not isinstance(name, str) or not isinstance(rel, str):
            raise StatementGraphError("golden AAPL stored member is malformed")
        payload = (fixture / rel).read_bytes()
        digest = hashlib.sha256(payload).hexdigest()
        if digest != item.get("content_sha256") or len(payload) != item.get("byte_length"):
            raise StatementGraphError(f"golden AAPL member digest mismatch: {name}")
        members[name] = payload
    if stored_count != manifest.get("retained_count"):
        raise StatementGraphError("golden AAPL retained count does not match stored members")
    if manifest.get("primary_document") not in members:
        raise StatementGraphError("golden AAPL primary document is not retained")
    return GoldenFilingPackage(manifest=manifest, members=members)


def load_golden_aapl_package(repo_root: Path, accession: str | None = None) -> GoldenFilingPackage:
    """Load and strictly admit one committed AAPL golden fixture. Performs no network I/O."""
    chosen = accession or _DEFAULT_GOLDEN_ACCESSION
    relative = GOLDEN_AAPL_FIXTURES.get(chosen)
    if relative is None:
        raise StatementGraphError("unknown golden AAPL filing")
    return admit_golden_aapl_package(Path(repo_root) / relative)


def _stored_member(package: GoldenFilingPackage, role: str) -> bytes:
    for item in package.manifest.get("members") or []:
        if not isinstance(item, dict):
            continue
        if item.get("state") == "stored" and item.get("role") == role:
            name = item.get("name")
            if not isinstance(name, str) or name not in package.members:
                raise StatementGraphError(f"golden AAPL stored {role} member is missing")
            return package.members[name]
    raise StatementGraphError(f"golden AAPL stored {role} member is missing")


def _statement_identity(package: GoldenFilingPackage, statement_type: str) -> tuple[str, str, str]:
    extras = package.manifest.get("statement_roles")
    spec = extras.get(statement_type) if isinstance(extras, dict) else None
    if isinstance(spec, dict) and spec.get("role_uri") and spec.get("title"):
        title = str(spec["title"])
        search = str(spec.get("title_search") or title)
        return str(spec["role_uri"]), title, search
    return (
        PRIMARY_STATEMENT_ROLES[statement_type],
        STATEMENT_TITLES[statement_type],
        STATEMENT_TITLES[statement_type],
    )


def _parse_xml(content: bytes, *, name: str) -> ET.Element:
    if not content or len(content) > _MAX_LINKBASE_BYTES:
        raise StatementGraphError(f"{name} exceeds linkbase bound")
    if b"\x00" in content:
        raise StatementGraphError(f"{name} contains NUL")
    upper = content.upper()
    if b"<!DOCTYPE" in upper or b"<!ENTITY" in upper:
        raise StatementGraphError(f"{name} declares a DTD or entity")
    try:
        return ET.fromstring(content)
    except ET.ParseError as exc:
        raise StatementGraphError(f"{name} is not well-formed XML") from exc


def _xlink(el: ET.Element, attr: str) -> str | None:
    return el.get(f"{{{XLINK}}}{attr}")


def concept_from_href(href: str) -> str:
    frag = href.rsplit("#", 1)[-1]
    for prefix in _PREFIXES:
        if frag.startswith(prefix):
            return f"{prefix[:-1]}:{frag[len(prefix):]}"
    if "_" in frag:
        head, rest = frag.split("_", 1)
        return f"{head}:{rest}"
    return frag


def _local_name(concept: str) -> str:
    if ":" in concept:
        return concept.split(":", 1)[1]
    if concept.startswith("{") and "}" in concept:
        return concept.split("}", 1)[1]
    return concept


def fact_matches_concept(concept_qname: str, concept: str) -> bool:
    local = _local_name(concept)
    if not concept_qname.endswith("}" + local) and concept_qname != local:
        return False
    prefix = concept.split(":", 1)[0] if ":" in concept else ""
    if not prefix:
        return True
    return prefix in concept_qname


def _is_abstract_concept(concept: str) -> bool:
    local = _local_name(concept)
    return any(token in local for token in _ABSTRACT_TOKENS)


def parse_presentation_tree(content: bytes, *, role_uri: str) -> list[dict[str, Any]]:
    root = _parse_xml(content, name="presentation linkbase")
    link = None
    for el in root.iter(f"{{{LINK}}}presentationLink"):
        if _xlink(el, "role") == role_uri:
            link = el
            break
    if link is None:
        raise StatementGraphError(f"presentation role is absent: {role_uri}")
    locs: dict[str, str] = {}
    for loc in link.findall(f"{{{LINK}}}loc"):
        label = _xlink(loc, "label")
        href = _xlink(loc, "href")
        if label and href:
            locs[label] = href
    children: dict[str, list[tuple[float, str, str | None, str | None]]] = {}
    parents: set[str] = set()
    targets: set[str] = set()
    arcs = list(link.findall(f"{{{LINK}}}presentationArc"))
    if len(arcs) > _MAX_ARCS:
        raise StatementGraphError("presentation arc limit exceeded")
    for arc in arcs:
        if arc.get("use") == "prohibited":
            continue
        frm = _xlink(arc, "from")
        to = _xlink(arc, "to")
        if not frm or not to:
            continue
        order_raw = arc.get("order") or "0"
        try:
            order = float(order_raw)
        except ValueError:
            order = 0.0
        children.setdefault(frm, []).append((order, to, arc.get("preferredLabel"), order_raw))
        parents.add(frm)
        targets.add(to)
    roots = sorted(p for p in parents if p not in targets)
    if len(roots) != 1:
        raise StatementGraphError(f"presentation role does not have a unique root: {role_uri}")
    rows: list[dict[str, Any]] = []

    def walk(label: str, depth: int, path: tuple[str, ...], preferred: str | None) -> None:
        href = locs.get(label)
        if href is None:
            raise StatementGraphError("presentation locator is missing")
        concept = concept_from_href(href)
        rows.append(
            {
                "order": len(rows),
                "depth": depth,
                "concept": concept,
                "href": href,
                "preferred_label_role": preferred,
                "presentation_path": list(path + (concept,)),
                "abstract": _is_abstract_concept(concept),
            }
        )
        kids = sorted(children.get(label, []), key=lambda item: (item[0], item[1]))
        for _order, child, pref, _raw in kids:
            walk(child, depth + 1, path + (concept,), pref)

    walk(roots[0], 0, (), None)
    return rows


def parse_labels(content: bytes) -> dict[tuple[str, str], str]:
    root = _parse_xml(content, name="label linkbase")
    out: dict[tuple[str, str], str] = {}
    for link in root.iter(f"{{{LINK}}}labelLink"):
        locs: dict[str, str] = {}
        resources: dict[str, list[tuple[str, str]]] = {}
        for loc in link.iter(f"{{{LINK}}}loc"):
            label = _xlink(loc, "label")
            href = _xlink(loc, "href")
            if label and href:
                locs[label] = concept_from_href(href)
        for lab in link.iter(f"{{{LINK}}}label"):
            key = _xlink(lab, "label")
            role = _xlink(lab, "role") or LABEL_STANDARD
            text = "".join(lab.itertext()).strip()
            if key and text:
                resources.setdefault(key, []).append((role, text))
        for arc in link.iter(f"{{{LINK}}}labelArc"):
            if arc.get("use") == "prohibited":
                continue
            frm = _xlink(arc, "from")
            to = _xlink(arc, "to")
            if frm not in locs or to not in resources:
                continue
            for role, text in resources[to]:
                out[(locs[frm], role)] = text
    return out


def parse_calculations(content: bytes) -> dict[str, dict[str, tuple[tuple[str, str], ...]]]:
    """Map role_uri -> parent concept -> ((child_concept, weight), ...) from calc arcs.

    A primary statement may consume only the relationships belonging to its
    exact xlink:role. Cross-role parents are not merged.
    """
    root = _parse_xml(content, name="calculation linkbase")
    by_role: dict[str, dict[str, list[tuple[str, str]]]] = {}
    for link in root.iter(f"{{{LINK}}}calculationLink"):
        role = _xlink(link, "role")
        if not role:
            raise StatementGraphError("calculation network is missing xlink:role")
        locs: dict[str, str] = {}
        for loc in link.findall(f"{{{LINK}}}loc"):
            label = _xlink(loc, "label")
            href = _xlink(loc, "href")
            if label and href:
                locs[label] = concept_from_href(href)
        by_parent = by_role.setdefault(role, {})
        for arc in link.findall(f"{{{LINK}}}calculationArc"):
            if arc.get("use") == "prohibited":
                continue
            frm = _xlink(arc, "from")
            to = _xlink(arc, "to")
            if frm not in locs or to not in locs:
                continue
            weight = arc.get("weight") or "1"
            by_parent.setdefault(locs[frm], []).append((locs[to], weight))
    return {
        role: {parent: tuple(children) for parent, children in parents.items()}
        for role, parents in by_role.items()
    }


def _iso_dates_from_text(text: str) -> list[str]:
    out: list[str] = []
    for match in _DATE_RE.finditer(text):
        month = _MONTHS[match.group(1).lower()]
        out.append(f"{int(match.group(3)):04d}-{month:02d}-{int(match.group(2)):02d}")
    return out


def _is_ix_numeric(tag: str) -> bool:
    compact = tag.replace("-", "").lower()
    return compact.endswith("nonfraction") or compact.endswith(":nonfraction")


class _StatementTableParser(HTMLParser):
    """Visible HTML table for one captured primary statement title."""

    def __init__(self, title: str) -> None:
        super().__init__(convert_charrefs=True)
        self.title = title
        self.rows: list[list[dict[str, Any]]] = []
        self._hidden = 0
        self._table_depth = 0
        self._capturing = False
        self._seen_title = False
        self._ended = False
        self._in_row = False
        self._in_cell = False
        self._cell_text: list[str] = []
        self._cell_facts: list[dict[str, Any]] = []
        self._row_cells: list[dict[str, Any]] = []
        self._ix_open: dict[str, Any] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self._ended:
            return
        ad = {key.lower(): value for key, value in attrs}
        if tag.endswith(":hidden") or tag == "ix:hidden":
            self._hidden += 1
            return
        if self._hidden:
            return
        if tag == "table":
            self._table_depth += 1
            return
        if tag == "tr" and (self._capturing or self._seen_title):
            self._capturing = True
            self._in_row = True
            self._row_cells = []
            return
        if tag in {"td", "th"} and self._in_row:
            self._in_cell = True
            self._cell_text = []
            self._cell_facts = []
            return
        if self._in_cell and _is_ix_numeric(tag):
            self._ix_open = {
                "name": ad.get("name"),
                "context_ref": ad.get("contextref"),
                "fact_id": ad.get("id"),
                "unit_ref": ad.get("unitref"),
                "scale": ad.get("scale"),
                "decimals": ad.get("decimals"),
                "nil": (ad.get("xsi:nil") or ad.get("nil") or "").lower() in {"true", "1"},
            }

    def handle_endtag(self, tag: str) -> None:
        if self._ended:
            return
        if tag.endswith(":hidden") or tag == "ix:hidden":
            if self._hidden:
                self._hidden -= 1
            return
        if self._hidden:
            return
        if tag in {"td", "th"} and self._in_cell:
            text = re.sub(r"\s+", " ", "".join(self._cell_text)).strip()
            self._row_cells.append({"text": text, "facts": list(self._cell_facts)})
            self._in_cell = False
            self._cell_text = []
            self._cell_facts = []
            return
        if tag == "tr" and self._in_row:
            self._in_row = False
            if self._row_cells:
                joined = " ".join(cell["text"] for cell in self._row_cells)
                if self.title in joined:
                    self._seen_title = True
                    self._capturing = True
                elif self._capturing:
                    if "see accompanying notes" in joined.lower():
                        self._ended = True
                        self._row_cells = []
                        return
                    self.rows.append(self._row_cells)
            self._row_cells = []
            return
        if tag == "table" and self._table_depth:
            self._table_depth -= 1
            if self._capturing and self._table_depth == 0:
                self._ended = True
        if self._ix_open is not None and _is_ix_numeric(tag):
            self._cell_facts.append(self._ix_open)
            self._ix_open = None

    def handle_data(self, data: str) -> None:
        if self._ended or self._hidden:
            return
        if self._in_cell:
            self._cell_text.append(data)
        elif self.title in data:
            self._seen_title = True


def parse_displayed_primary_table(html: str, *, title: str) -> dict[str, Any]:
    """Source-backed composition of one captured primary filing table."""
    parser = _StatementTableParser(title)
    parser.feed(html)
    if not parser.rows:
        raise StatementGraphError(f"displayed statement table is absent: {title}")
    header_dates: list[str] = []
    display_rows: list[dict[str, Any]] = []
    for cells in parser.rows:
        joined = " ".join(cell["text"] for cell in cells)
        dates = _iso_dates_from_text(joined)
        if not header_dates and len(dates) >= 2:
            header_dates = dates
            continue
        label_cell = next((cell for cell in cells if cell["text"] and cell["text"] != "$"), None)
        if label_cell is None and not any(cell["facts"] for cell in cells):
            continue
        label = str(label_cell["text"]).strip() if label_cell else ""
        if not label and not any(cell["facts"] for cell in cells):
            continue
        if label.strip().lower() in _PERIOD_BANNER_LABELS:
            continue
        value_facts: list[dict[str, Any]] = []
        seen_label = False
        for cell in cells:
            if not seen_label:
                if cell is label_cell:
                    seen_label = True
                continue
            if cell["text"] == "$":
                continue
            value_facts.extend(cell["facts"])
        display_rows.append(
            {
                "label": label,
                "value_facts": value_facts,
                "abstract": not bool(value_facts),
            }
        )
    if len(header_dates) < 2:
        raise StatementGraphError(f"displayed statement columns are absent: {title}")
    return {"columns_iso": header_dates, "rows": display_rows}


def resolve_label(labels: Mapping[tuple[str, str], str], concept: str, preferred: str | None) -> tuple[str, str]:
    for role in (preferred, LABEL_TERSE, LABEL_STANDARD):
        if role and (concept, role) in labels:
            return labels[(concept, role)], role
    return _local_name(concept), "concept_local_name"


def _undimensioned(context: Mapping[str, Any]) -> bool:
    dims = context.get("dimensions") or []
    return isinstance(dims, list) and len(dims) == 0


def _unit_label(units: Mapping[str, Any], unit_ref: str | None) -> str | None:
    if not unit_ref or unit_ref not in units:
        return None
    unit = units[unit_ref]
    nums = [m.rsplit("}", 1)[-1] for m in unit.get("numerator_measures") or []]
    dens = [m.rsplit("}", 1)[-1] for m in unit.get("denominator_measures") or []]
    if nums and dens:
        return f"{nums[0]}/{'*'.join(dens)}"
    if nums:
        return nums[0]
    return unit_ref


def _period_key(context: Mapping[str, Any]) -> tuple[str, str | None, str | None]:
    period = context.get("period") or {}
    kind = str(period.get("kind") or "")
    if kind == "instant":
        return ("instant", None, period.get("instant_date"))
    return ("duration", period.get("start_date"), period.get("end_date"))


def _period_for_displayed_column(
    *,
    index: int,
    iso: str,
    prefer_kind: str,
    displayed_rows: list[dict[str, Any]],
    facts_by_id: Mapping[str, dict[str, Any]],
    contexts: Mapping[str, dict[str, Any]],
) -> dict[str, Any] | None:
    """Bind one displayed column from same-column facts of the preferred period kind."""
    for spec in displayed_rows:
        value_facts = spec.get("value_facts") or []
        if index >= len(value_facts):
            continue
        html_fact = value_facts[index]
        parsed = facts_by_id.get(str(html_fact.get("fact_id") or ""))
        context_ref = (parsed or {}).get("context_ref") or html_fact.get("context_ref")
        context = contexts.get(str(context_ref or ""))
        if not context:
            continue
        period = context.get("period") or {}
        if period.get("kind") != prefer_kind:
            continue
        if prefer_kind == "instant" and period.get("instant_date") == iso:
            return period
        if prefer_kind == "duration" and period.get("end_date") == iso and period.get("start_date"):
            return period
    return None


def _columns_from_display(
    *,
    statement_type: str,
    iso_dates: list[str],
    displayed_rows: list[dict[str, Any]],
    facts_by_id: Mapping[str, dict[str, Any]],
    contexts: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Columns are the dates printed on the captured table, bound to complete filing periods."""
    if len(iso_dates) < 2:
        raise StatementGraphError("displayed statement columns are absent")
    prefer_kind = "instant" if statement_type == "balance_sheet" else "duration"
    columns: list[dict[str, Any]] = []
    seen: set[tuple[str, str | None, str]] = set()
    for index, iso in enumerate(iso_dates):
        period = _period_for_displayed_column(
            index=index,
            iso=iso,
            prefer_kind=prefer_kind,
            displayed_rows=displayed_rows,
            facts_by_id=facts_by_id,
            contexts=contexts,
        )
        if prefer_kind == "instant":
            if not period:
                raise StatementGraphError("displayed balance-sheet column is not bound to the filing date")
            identity: tuple[str, str | None, str] = ("instant", None, iso)
            columns.append({"kind": "instant", "start": None, "end": iso, "label": iso})
        else:
            if not period:
                raise StatementGraphError("displayed duration column is not bound to the filing period")
            start = str(period.get("start_date"))
            identity = ("duration", start, iso)
            columns.append({"kind": "duration", "start": start, "end": iso, "label": iso})
        if identity in seen:
            raise StatementGraphError("displayed statement columns collapse distinct filing periods")
        seen.add(identity)
    return columns


def _values_agree(left: str, right: str) -> bool:
    if left == right:
        return True
    try:
        return Decimal(left) == Decimal(right)
    except (InvalidOperation, ValueError):
        return False


def _cell_dimensions(context: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    if not context:
        return []
    out: list[dict[str, Any]] = []
    for dim in context.get("dimensions") or []:
        out.append(
            {
                "kind": dim.get("kind"),
                "dimension_qname": dim.get("dimension_qname"),
                "member_qname": dim.get("member_qname"),
            }
        )
    return out


def _duplicate_identity_occurrences(
    displayed: Mapping[str, Any], facts: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """All occurrences sharing concept/context/unit. Agreement is not pre-filtered."""
    identity = (
        displayed.get("concept_qname"),
        displayed.get("context_ref"),
        displayed.get("unit_ref"),
    )
    siblings = [
        fact
        for fact in facts
        if (
            fact.get("concept_qname"),
            fact.get("context_ref"),
            fact.get("unit_ref"),
        )
        == identity
    ]
    siblings.sort(
        key=lambda fact: (
            (fact.get("source_span") or {}).get("start", 0),
            str(fact.get("fact_id") or ""),
        )
    )
    return siblings


def _presentation_occurrences(presentation: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    by_concept: dict[str, list[dict[str, Any]]] = {}
    for row in presentation:
        if _is_abstract_concept(row["concept"]):
            continue
        by_concept.setdefault(row["concept"], []).append(row)
    return by_concept


def _select_presentation_row(
    spec: Mapping[str, Any],
    occurrences: list[dict[str, Any]],
) -> dict[str, Any] | None:
    if not occurrences:
        return None
    if len(occurrences) == 1:
        return occurrences[0]
    label = str(spec.get("label") or "").strip().lower()
    if "beginning" in label:
        start = [row for row in occurrences if row.get("preferred_label_role") == LABEL_PERIOD_START]
        if start:
            return start[0]
    if "ending" in label:
        end = [row for row in occurrences if row.get("preferred_label_role") == LABEL_PERIOD_END]
        if end:
            return end[0]
    return occurrences[0]


def _row_explicit_dimensions(
    *,
    value_facts: list[Mapping[str, Any]],
    facts_by_id: Mapping[str, dict[str, Any]],
    contexts: Mapping[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    for item in value_facts:
        fact = facts_by_id.get(str(item.get("fact_id") or ""))
        if fact is None:
            continue
        context = contexts.get(str(fact.get("context_ref") or ""))
        dims = _cell_dimensions(context)
        if dims:
            return dims
    return []


def _empty_cell(*, column: Mapping[str, Any], quality_state: str) -> dict[str, Any]:
    return {
        "period": dict(column),
        "value": None,
        "unit": None,
        "scale": None,
        "decimals": None,
        "dimensions": [],
        "direct_or_calculated": None,
        "quality_state": quality_state,
        "source_receipt": None,
    }


def _cell_from_facts(
    *,
    facts: list[dict[str, Any]],
    column: Mapping[str, Any],
    units: dict[str, Any],
    document_name: str,
    content_sha256: str,
    abstract: bool,
    contexts: Mapping[str, dict[str, Any]] | None = None,
    representative: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if abstract:
        return _empty_cell(column=column, quality_state="abstract")
    if not facts:
        return _empty_cell(column=column, quality_state="missing_fact")
    values = [f.get("normalized_value") for f in facts]
    comparable = [("" if v is None else str(v)) for v in values]
    if representative is None:
        representative = min(
            facts,
            key=lambda f: ((f.get("source_span") or {}).get("start", 0), str(f.get("fact_id") or "")),
        )
    disagree = any(
        not _values_agree(comparable[0], item) if comparable[0] != "" or item != "" else False
        for item in comparable[1:]
    )
    mixed_nil = any(bool(f.get("nil")) for f in facts) and not all(bool(f.get("nil")) for f in facts)
    mixed_presence = any(v is None for v in values) and any(v is not None for v in values)
    context = None
    if contexts is not None:
        context = contexts.get(str(representative.get("context_ref") or ""))
    dimensions = _cell_dimensions(context)
    if disagree or mixed_nil or mixed_presence:
        return {
            "period": dict(column),
            "value": None,
            "unit": None,
            "scale": None,
            "decimals": None,
            "dimensions": dimensions,
            "direct_or_calculated": None,
            "quality_state": "ambiguous",
            "source_receipt": {
                "document_name": document_name,
                "content_sha256": content_sha256,
                "occurrence_count": len(facts),
                "competing_fact_ids": sorted(str(f.get("fact_id")) for f in facts),
                "competing_values": comparable,
            },
        }
    if representative.get("nil") or representative.get("normalized_value") is None:
        cell = _empty_cell(column=column, quality_state="nil")
        cell["dimensions"] = dimensions
        cell["source_receipt"] = {
            "document_name": document_name,
            "content_sha256": content_sha256,
            "fact_id": representative.get("fact_id"),
            "concept_qname": representative.get("concept_qname"),
            "context_ref": representative.get("context_ref"),
            "unit_ref": representative.get("unit_ref"),
            "source_span": representative.get("source_span"),
            "occurrence_count": len(facts),
        }
        return cell
    span = representative.get("source_span")
    return {
        "period": dict(column),
        "value": representative.get("normalized_value"),
        "unit": _unit_label(units, representative.get("unit_ref")),
        "scale": representative.get("scale"),
        "decimals": representative.get("decimals"),
        "dimensions": dimensions,
        "direct_or_calculated": "direct",
        "quality_state": "available",
        "source_receipt": {
            "document_name": document_name,
            "content_sha256": content_sha256,
            "fact_id": representative.get("fact_id"),
            "concept_qname": representative.get("concept_qname"),
            "context_ref": representative.get("context_ref"),
            "unit_ref": representative.get("unit_ref"),
            "source_span": span,
            "occurrence_count": len(facts),
        },
    }


def map_standardized_metric(
    concept: str,
    registry: Any,
    *,
    dimensions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    local = _local_name(concept)
    prefix = concept.split(":", 1)[0] if ":" in concept else ""
    hits: list[str] = []
    contracts = getattr(registry, "contracts", None)
    if contracts is None:
        return {"metric_id": None, "mapping_state": "unmapped", "mapping_receipt": None}
    iterable = contracts.values() if isinstance(contracts, dict) else contracts
    for contract in iterable:
        for alias in getattr(contract, "taxonomy_concept_aliases", ()):
            if alias.concept == local and alias.taxonomy == prefix:
                hits.append(contract.metric_id)
    unique = sorted(set(hits))
    if len(unique) == 1:
        metric_id = unique[0]
        contract = None
        metric_lookup = getattr(registry, "metric", None)
        if callable(metric_lookup):
            try:
                contract = metric_lookup(metric_id)
            except KeyError:
                contract = None
        if contract is None:
            contract = next((item for item in iterable if getattr(item, "metric_id", None) == metric_id), None)
        profile = getattr(contract, "dimensional_profile", None) if contract is not None else None
        mode = getattr(profile, "mode", None)
        if mode == "consolidated_only" and dimensions:
            return {
                "metric_id": None,
                "mapping_state": "unmapped",
                "mapping_receipt": {
                    "taxonomy": prefix,
                    "concept": local,
                    "reason": "dimensional_profile",
                    "mode": mode,
                },
            }
        return {
            "metric_id": metric_id,
            "mapping_state": "mapped",
            "mapping_receipt": {
                "taxonomy": prefix,
                "concept": local,
                "metric_id": metric_id,
            },
        }
    if len(unique) > 1:
        return {
            "metric_id": None,
            "mapping_state": "ambiguous_mapping",
            "mapping_receipt": {"taxonomy": prefix, "concept": local, "metric_ids": unique},
        }
    return {"metric_id": None, "mapping_state": "unmapped", "mapping_receipt": None}


def _assign_display_depth(rows: list[dict[str, Any]]) -> None:
    open_header = False
    for row in rows:
        if row["abstract"]:
            row["depth"] = 0
            open_header = True
            continue
        label = row["as_reported_label"].strip().lower()
        if open_header and not label.startswith("total "):
            row["depth"] = 1
        else:
            row["depth"] = 0
            if label.startswith("total "):
                open_header = False


def _prefixed_from_html_name(name: str | None) -> str:
    if not name:
        return ""
    return name.replace("_", ":", 1) if ":" not in name and "_" in name else name


def reconstruct_statement(
    *,
    statement_type: str,
    package: GoldenFilingPackage,
    parsed_instance: Mapping[str, Any],
    registry: Any,
) -> dict[str, Any]:
    role_uri, title, title_search = _statement_identity(package, statement_type)
    pre = _stored_member(package, "presentation")
    lab = _stored_member(package, "label")
    cal = _stored_member(package, "calculation")
    presentation = parse_presentation_tree(pre, role_uri=role_uri)
    by_concept = _presentation_occurrences(presentation)
    parse_labels(lab)
    calcs = parse_calculations(cal).get(role_uri) or {}
    facts = list(parsed_instance.get("facts") or [])
    facts_by_id = {str(f.get("fact_id")): f for f in facts if f.get("fact_id")}
    contexts = {c["context_id"]: c for c in parsed_instance.get("contexts") or []}
    units = {u["unit_id"]: u for u in parsed_instance.get("units") or []}
    primary = package.manifest["primary_document"]
    primary_sha = next(
        item["content_sha256"]
        for item in package.manifest["members"]
        if item.get("name") == primary and item.get("state") == "stored"
    )
    html = package.members[primary].decode("utf-8")
    displayed = parse_displayed_primary_table(html, title=title_search)
    table_facts: list[dict[str, Any]] = []
    for spec in displayed["rows"]:
        for item in spec["value_facts"]:
            fact = facts_by_id.get(str(item.get("fact_id") or ""))
            if fact is None:
                raise StatementGraphError("displayed statement fact is missing from the iXBRL parse")
            table_facts.append(fact)
    if not table_facts:
        raise StatementGraphError(f"displayed statement has no numeric rows: {title}")
    columns = _columns_from_display(
        statement_type=statement_type,
        iso_dates=displayed["columns_iso"],
        displayed_rows=displayed["rows"],
        facts_by_id=facts_by_id,
        contexts=contexts,
    )
    out_rows: list[dict[str, Any]] = []
    for spec in displayed["rows"]:
        value_facts = spec["value_facts"]
        concept = ""
        if value_facts:
            names = sorted({_prefixed_from_html_name(item.get("name")) for item in value_facts})
            concept = names[0]
        presentation_row = _select_presentation_row(spec, by_concept.get(concept) or [])
        preferred = presentation_row.get("preferred_label_role") if presentation_row else None
        path = list(presentation_row["presentation_path"]) if presentation_row else ([concept] if concept else [spec["label"]])
        first_fact = facts_by_id.get(str(value_facts[0].get("fact_id") or "")) if value_facts else None
        first_context = contexts.get(str(first_fact.get("context_ref") or "")) if first_fact else None
        dimensions = _cell_dimensions(first_context)
        if dimensions:
            member = dimensions[0].get("member_qname")
            if member and member not in path:
                path = path + [str(member)]
        mapping_dimensions = _row_explicit_dimensions(
            value_facts=value_facts,
            facts_by_id=facts_by_id,
            contexts=contexts,
        )
        mapping = map_standardized_metric(
            concept,
            registry,
            dimensions=mapping_dimensions,
        ) if concept else {
            "metric_id": None,
            "mapping_state": "unmapped",
            "mapping_receipt": None,
        }
        children = calcs.get(concept) if concept and not dimensions else None
        formula = None
        if children:
            formula = [{"concept": child, "weight": weight} for child, weight in children]
        cells = []
        for index, column in enumerate(columns):
            html_fact = value_facts[index] if index < len(value_facts) else None
            parsed_fact = facts_by_id.get(str(html_fact.get("fact_id") or "")) if html_fact else None
            selected = _duplicate_identity_occurrences(parsed_fact, facts) if parsed_fact else []
            cell = _cell_from_facts(
                facts=selected,
                column=column,
                units=units,
                document_name=primary,
                content_sha256=primary_sha,
                abstract=spec["abstract"],
                contexts=contexts,
                representative=parsed_fact,
            )
            cells.append(cell)
        out_rows.append(
            {
                "order": len(out_rows),
                "depth": 0,
                "concept": concept or None,
                "abstract": spec["abstract"],
                "as_reported_label": spec["label"],
                "preferred_label_role": preferred,
                "label_role_used": "filing_display",
                "presentation_path": path,
                "standardized_metric_id": mapping["metric_id"],
                "mapping_state": mapping["mapping_state"],
                "mapping_receipt": mapping["mapping_receipt"],
                "formula_dependencies": formula,
                "cells": cells,
            }
        )
    _assign_display_depth(out_rows)
    return {
        "statement_type": statement_type,
        "role_uri": role_uri,
        "title": title,
        "columns": columns,
        "row_count": len(out_rows),
        "rows": out_rows,
    }


def reconstruct_primary_statements(
    *,
    package: GoldenFilingPackage,
    registry: Any,
) -> dict[str, Any]:
    primary = package.manifest["primary_document"]
    parsed = parse_sec_filing_document(package.members[primary], document_name=primary)
    entity_ids = []
    for context in parsed.get("contexts") or []:
        ident = ((context.get("entity") or {}).get("identifier"))
        if ident:
            entity_ids.append(str(ident))
    unique_entities = sorted(set(entity_ids))
    if unique_entities != [package.manifest["cik"]]:
        raise StatementGraphError("XBRL entity identifier is not the source-native AAPL CIK")
    statements = [
        reconstruct_statement(
            statement_type=kind,
            package=package,
            parsed_instance=parsed,
            registry=registry,
        )
        for kind in ("income_statement", "balance_sheet", "cash_flow")
    ]
    return {
        "parsed_document_kind": (parsed.get("document") or {}).get("kind"),
        "fact_count": len(parsed.get("facts") or []),
        "context_count": len(parsed.get("contexts") or []),
        "statements": statements,
    }


__all__ = [
    "GOLDEN_AAPL_FIXTURES",
    "GoldenFilingPackage",
    "LABEL_PERIOD_END",
    "LABEL_PERIOD_START",
    "PRIMARY_STATEMENT_ROLES",
    "STATEMENT_TITLES",
    "StatementGraphError",
    "admit_golden_aapl_package",
    "concept_from_href",
    "fact_matches_concept",
    "load_golden_aapl_package",
    "mint_fixture_recorded_at",
    "parse_calculations",
    "parse_displayed_primary_table",
    "parse_labels",
    "parse_presentation_tree",
    "map_standardized_metric",
    "reconstruct_primary_statements",
    "reconstruct_statement",
]

