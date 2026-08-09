"""Completed-quarter breadth and research-readiness projections for the 13F census.

This module is intentionally downstream of the immutable SEC evidence/catalog
plane.  It never discovers filings and never promotes a manager into the curated
Smart Money cohort.  Its public result is a bounded, completed-quarter aggregate;
pending filers therefore cannot become synthetic sellers.
"""
from __future__ import annotations

import hashlib
import math
import sqlite3
import tempfile
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .models import canonical_json_bytes

PUBLIC_SCHEMA = "institutional_13f.census_public/v1"
RESEARCH_BENCH_SCHEMA = "institutional_13f.research_bench/v1"
PUBLIC_MAX_BYTES = 16 * 1024
DEFAULT_ACTION_THRESHOLD_PCT = 5.0
DEFAULT_MAX_ROWS = 6
DEFAULT_MINIMUM_MAPPING_COVERAGE_PCT = 20.0
COMMON_SHARE_FACTORS = (
    0.1, 0.125, 0.2, 0.25, 1 / 3, 0.5,
    2.0, 3.0, 4.0, 5.0, 8.0, 10.0,
)


@dataclass(frozen=True)
class CensusCompilation:
    """One bounded public view plus a private, unpromoted screening bench."""

    public_summary: dict[str, Any]
    research_bench: dict[str, Any]
    receipt: dict[str, Any]


@dataclass(frozen=True)
class _EffectiveQuarter:
    period_end: str
    accession_to_cik: dict[str, str]
    accession_to_lineage: dict[str, tuple[str, str]]
    effective_accessions_by_lineage: dict[tuple[str, str], frozenset[str]]
    additive_accessions: frozenset[str]
    effective_filers: frozenset[str]
    filer_names: dict[str, str]
    original_filers: frozenset[str]
    notice_filers: frozenset[str]
    amendment_count: int
    duplicate_original_lineages: int
    orphan_amendment_lineages: int


def compilation_json_bytes(value: Mapping[str, Any]) -> bytes:
    """Return the exact canonical bytes used for hashes, writes, and readback."""
    return canonical_json_bytes(value)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _clean(value: Any) -> Any:
    """Turn pandas nullable scalars into ordinary Python values."""
    if value is None:
        return None
    try:
        # pandas.NA cannot be used as a bool; NaN is the only value unequal to itself.
        unequal = value != value
        if isinstance(unequal, bool) and unequal:
            return None
    except (TypeError, ValueError):
        return None
    text = str(value).strip()
    if not text or text.lower() in {"nan", "nat", "<na>", "none"}:
        return None
    return value


def _text(value: Any) -> str:
    value = _clean(value)
    return "" if value is None else str(value).strip()


def _cik10(value: Any) -> str:
    raw = _text(value)
    return raw.zfill(10) if raw.isdigit() and len(raw) <= 10 else ""


def _frame_records(frame: Any) -> Iterable[dict[str, Any]]:
    """Yield mappings without materializing a multi-million-row DataFrame copy."""
    if frame is None:
        return
    if hasattr(frame, "columns") and hasattr(frame, "itertuples"):
        columns = [str(c) for c in frame.columns]
        for values in frame.itertuples(index=False, name=None):
            yield dict(zip(columns, values))
        return
    for row in frame:
        if isinstance(row, Mapping):
            yield dict(row)
        elif hasattr(row, "_asdict"):
            yield dict(row._asdict())
        else:
            yield dict(vars(row))


def _column_indexes(frame: Any) -> tuple[dict[str, int], Iterable[tuple[Any, ...]]]:
    if hasattr(frame, "columns") and hasattr(frame, "itertuples"):
        indexes = {str(name): idx for idx, name in enumerate(frame.columns)}
        return indexes, frame.itertuples(index=False, name=None)
    rows = list(_frame_records(frame))
    names = sorted({key for row in rows for key in row})
    indexes = {name: idx for idx, name in enumerate(names)}
    return indexes, (tuple(row.get(name) for name in names) for row in rows)


def _pick(row: Mapping[str, Any], *names: str) -> Any:
    for name in names:
        if name in row:
            value = _clean(row[name])
            if value is not None:
                return value
    return None


def _effective_quarter(
    tables: Any,
    period_end: str,
    supplemental_tables: Sequence[Any] = (),
) -> _EffectiveQuarter:
    table_sets = (tables, *tuple(supplemental_tables))
    covers: dict[str, dict[str, Any]] = {}
    for source in table_sets:
        for row in _frame_records(getattr(source, "cover_pages", ())):
            accession = _text(_pick(row, "accession", "accession_number"))
            if accession:
                if accession in covers and covers[accession] != row:
                    raise ValueError(f"conflicting cover-page overlay for {accession}")
                covers[accession] = row

    lineages: dict[tuple[str, str], list[dict[str, Any]]] = {}
    original_filers: set[str] = set()
    notice_filers: set[str] = set()
    amendment_count = 0
    filer_names: dict[str, str] = {}
    accession_to_lineage: dict[str, tuple[str, str]] = {}

    seen_submissions: dict[str, tuple[str, str, str]] = {}
    for source in table_sets:
        for row in _frame_records(getattr(source, "submissions", ())):
            accession = _text(_pick(row, "accession", "accession_number"))
            cik = _cik10(_pick(row, "cik", "filer_cik"))
            form = _text(_pick(row, "form", "submission_type", "submissiontype")).upper()
            period = _text(_pick(row, "period_end", "period_of_report", "periodofreport"))
            if not accession or not cik or period != period_end:
                continue
            identity = (cik, form, period)
            if accession in seen_submissions:
                if seen_submissions[accession] != identity:
                    raise ValueError(f"conflicting submission overlay for {accession}")
                # Catalog adapters must remove byte-identical bulk duplicates; a
                # duplicate here is ambiguous and is never counted twice.
                continue
            seen_submissions[accession] = identity
            if form in {"13F-NT", "13F-NT/A"}:
                notice_filers.add(cik)
                continue
            if form not in {"13F-HR", "13F-HR/A"}:
                continue
            cover = covers.get(accession, {})
            file_number = _text(_pick(cover, "form_13f_file_number", "form13f_file_number"))
            # CIK is a better fallback than accession: it keeps duplicate originals visible.
            lineage = (cik, file_number or "__missing_file_number__")
            accession_to_lineage[accession] = lineage
            # EDGAR's submitted form type governs original/amendment identity.  The
            # official bulk set contains at least one 13F-HR whose cover-page flag says
            # amendment; that conflict is a quality finding, not permission to silently
            # remove an original filer from the denominator.
            is_amendment = form.endswith("/A")
            amendment_type = _text(_pick(cover, "amendment_type")).upper()
            filing_date = _text(_pick(row, "filing_date"))
            accepted_at = _text(_pick(row, "accepted_at"))
            if is_amendment:
                amendment_count += 1
            else:
                original_filers.add(cik)
            manager_name = _text(_pick(cover, "filing_manager_name"))
            if manager_name:
                filer_names.setdefault(cik, manager_name)
            lineages.setdefault(lineage, []).append({
                "accession": accession,
                "cik": cik,
                "filing_date": filing_date,
                "accepted_at": accepted_at,
                "is_amendment": is_amendment,
                "amendment_type": amendment_type,
            })

    effective: dict[str, str] = {}
    effective_by_lineage: dict[tuple[str, str], frozenset[str]] = {}
    additive_accessions: set[str] = set()
    duplicate_originals = 0
    orphan_amendments = 0
    for lineage, records in lineages.items():
        records.sort(
            key=lambda item: (
                item["accepted_at"], item["filing_date"], item["accession"]
            )
        )
        originals = [item for item in records if not item["is_amendment"]]
        replacements = [
            item for item in records
            if item["is_amendment"] and item["amendment_type"] != "NEW HOLDINGS"
        ]
        additive = [
            item for item in records
            if item["is_amendment"] and item["amendment_type"] == "NEW HOLDINGS"
        ]
        if len(originals) > 1:
            duplicate_originals += 1
        base_candidates = originals + replacements
        selected: set[str] = set()
        if base_candidates:
            base = max(
                base_candidates,
                key=lambda item: (
                    item["accepted_at"], item["filing_date"], item["accession"]
                ),
            )
            effective[base["accession"]] = base["cik"]
            selected.add(base["accession"])
            for item in additive:
                item_order = (item["accepted_at"], item["filing_date"], item["accession"])
                base_order = (base["accepted_at"], base["filing_date"], base["accession"])
                if item_order >= base_order:
                    effective[item["accession"]] = item["cik"]
                    selected.add(item["accession"])
                    additive_accessions.add(item["accession"])
        else:
            # Retain additive disclosure rather than inventing an empty book, but make
            # the missing original explicit in coverage/quality metadata.
            orphan_amendments += 1
            for item in additive:
                effective[item["accession"]] = item["cik"]
                selected.add(item["accession"])
                additive_accessions.add(item["accession"])
        if selected:
            effective_by_lineage[lineage] = frozenset(selected)

    return _EffectiveQuarter(
        period_end=period_end,
        accession_to_cik=effective,
        accession_to_lineage=accession_to_lineage,
        effective_accessions_by_lineage=effective_by_lineage,
        additive_accessions=frozenset(additive_accessions),
        effective_filers=frozenset(effective.values()),
        filer_names=filer_names,
        original_filers=frozenset(original_filers),
        notice_filers=frozenset(notice_filers),
        amendment_count=amendment_count,
        duplicate_original_lineages=duplicate_originals,
        orphan_amendment_lineages=orphan_amendments,
    )


def _number(value: Any) -> float:
    value = _clean(value)
    if value is None:
        return 0.0
    try:
        out = float(value)
    except (TypeError, ValueError):
        return 0.0
    return out if math.isfinite(out) else 0.0


def _normalize_ticker_map(source: Mapping[str, Any] | None) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for raw_cusip, value in (source or {}).items():
        cusip = _text(raw_cusip).upper()
        if not cusip:
            continue
        if isinstance(value, Mapping):
            ticker = _text(value.get("ticker")).upper()
            name = _text(value.get("name") or value.get("issuer"))
        else:
            ticker = _text(value).upper()
            name = ""
        if ticker:
            out[cusip] = {"ticker": ticker, "name": name}
    return out


_MANAGER_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("passive", ("vanguard", "blackrock", "ishares", "dimensional fund", "geode capital")),
    ("custody", ("state street bank", "bank of new york mellon", "northern trust")),
    ("bank", ("jpmorgan chase", "bank of america", "wells fargo", "morgan stanley", "goldman sachs group")),
    ("insurer", (" insurance", "assurance", " life insurance")),
    ("pension", ("retirement system", "pension", "superannuation")),
    ("quant_market_maker", ("two sigma", "virtu financial", "susquehanna international", "optiver", "jump trading")),
)


def classify_manager_name(name: str) -> tuple[str, str]:
    """Conservative structural label with explicit rule provenance."""
    lowered = f" {_text(name).lower()} "
    for label, needles in _MANAGER_PATTERNS:
        if any(needle in lowered for needle in needles):
            return label, "name_pattern_v1"
    return "unknown", "name_pattern_v1"


def is_structural_holder_discontinuity(
    *, holder_delta: int, new_filers: int, exiting_filers: int, activity: int
) -> bool:
    """Conservative rank fence for likely corporate-action/identifier breaks."""
    if activity <= 0:
        return False
    identity_turnover = (new_filers + exiting_filers) / activity
    return abs(holder_delta) >= 250 and identity_turnover >= 0.45


def infer_common_share_factor(
    ratios: Iterable[float],
    *,
    minimum_holders: int = 2,
    dominance: float = 0.9,
    relative_tolerance: float = 0.01,
) -> float | None:
    """Detect a known split factor shared by a stable holder cohort.

    This is deliberately narrower than a generic clustering algorithm.  Only
    conventional split/consolidation factors qualify, at least two continuing
    filers must agree, and a supermajority must fall within a one-percent band.
    """
    values: list[float] = []
    for raw in ratios:
        try:
            value = float(raw)
        except (TypeError, ValueError):
            continue
        if math.isfinite(value) and value > 0:
            values.append(value)
    if len(values) < minimum_holders:
        return None
    required = max(minimum_holders, math.ceil(len(values) * dominance))
    matches: list[tuple[int, float]] = []
    for factor in COMMON_SHARE_FACTORS:
        count = sum(
            1 for ratio in values
            if abs(ratio / factor - 1.0) <= relative_tolerance
        )
        matches.append((count, factor))
    count, factor = max(matches, key=lambda item: (item[0], -abs(math.log(item[1]))))
    return factor if count >= required else None


class CensusAccumulator:
    """Disk-backed compiler; peak memory depends on securities, not filing rows."""

    def __init__(self, database_path: str | Path | None = None) -> None:
        self._temporary: tempfile.TemporaryDirectory[str] | None = None
        if database_path is None:
            self._temporary = tempfile.TemporaryDirectory(prefix="institutional-13f-")
            database_path = Path(self._temporary.name) / "census.sqlite"
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(str(self.database_path))
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA synchronous=NORMAL")
        self.connection.execute("PRAGMA temp_store=FILE")
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS positions (
              side TEXT NOT NULL,
              cik TEXT NOT NULL,
              security_key TEXT NOT NULL,
              issuer TEXT NOT NULL,
              shares REAL NOT NULL,
              value_reported REAL NOT NULL,
              PRIMARY KEY (side, cik, security_key)
            ) WITHOUT ROWID;
            CREATE TABLE IF NOT EXISTS paired (cik TEXT PRIMARY KEY) WITHOUT ROWID;
            """
        )
        self.quarters: dict[str, _EffectiveQuarter] = {}
        self.row_counts: dict[str, dict[str, int]] = {}

    def close(self) -> None:
        self.connection.close()
        if self._temporary is not None:
            self._temporary.cleanup()
            self._temporary = None

    def __enter__(self) -> "CensusAccumulator":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def ingest(
        self,
        side: str,
        tables: Any,
        *,
        period_end: str,
        excluded_accessions: Iterable[str] = (),
        supplemental_tables: Sequence[Any] = (),
    ) -> _EffectiveQuarter:
        if side not in {"current", "baseline"}:
            raise ValueError("side must be current or baseline")
        table_sets = (tables, *tuple(supplemental_tables))
        effective = _effective_quarter(tables, period_end, supplemental_tables)
        effective_accessions_before_quality = set(effective.accession_to_cik)
        excluded = {_text(value) for value in excluded_accessions if _text(value)}
        excluded_effective = excluded & effective_accessions_before_quality
        quality_excluded_lineages = {
            effective.accession_to_lineage[accession]
            for accession in excluded_effective
        }
        if quality_excluded_lineages:
            filtered = {
                accession: cik for accession, cik in effective.accession_to_cik.items()
                if effective.accession_to_lineage[accession]
                not in quality_excluded_lineages
            }
            filtered_by_lineage = {
                lineage: accessions
                for lineage, accessions in effective.effective_accessions_by_lineage.items()
                if lineage not in quality_excluded_lineages
            }
            effective = replace(
                effective,
                accession_to_cik=filtered,
                effective_accessions_by_lineage=filtered_by_lineage,
                additive_accessions=frozenset(
                    effective.additive_accessions & set(filtered)
                ),
                effective_filers=frozenset(filtered.values()),
            )

        # NEW HOLDINGS is additive only when it contains securities omitted from
        # the effective base layer.  Real filings sometimes repeat most of the
        # base despite that label.  Discover cross-accession CUSIP overlap before
        # inserting anything; an ambiguous lineage is quarantined atomically.
        overlap_candidates = {
            lineage for lineage, accessions in effective.effective_accessions_by_lineage.items()
            if len(accessions) > 1 and bool(accessions & effective.additive_accessions)
        }
        first_accession_by_security: dict[tuple[tuple[str, str], str], str] = {}
        overlapping_lineages: set[tuple[str, str]] = set()
        if overlap_candidates:
            for source in table_sets:
                indexes, rows = _column_indexes(getattr(source, "holdings", ()))

                def overlap_value(values: tuple[Any, ...], *names: str) -> Any:
                    for name in names:
                        idx = indexes.get(name)
                        if idx is not None:
                            value = _clean(values[idx])
                            if value is not None:
                                return value
                    return None

                for values in rows:
                    accession = _text(overlap_value(values, "accession", "accession_number"))
                    if accession not in effective.accession_to_cik:
                        continue
                    lineage = effective.accession_to_lineage[accession]
                    if lineage not in overlap_candidates:
                        continue
                    put_call = _text(overlap_value(values, "put_call", "putcall")).upper()
                    amount_type = _text(overlap_value(
                        values,
                        "shares_or_principal_amount_type", "ssh_prn_type", "sshprnamttype",
                    )).upper()
                    security_key = _text(overlap_value(values, "cusip")).upper()
                    shares = _number(overlap_value(
                        values,
                        "shares_or_principal_amount", "ssh_prn_amt", "sshprnamt",
                    ))
                    if put_call or amount_type != "SH" or not security_key or shares <= 0:
                        continue
                    key = (lineage, security_key)
                    first = first_accession_by_security.setdefault(key, accession)
                    if first != accession:
                        overlapping_lineages.add(lineage)

        if overlapping_lineages:
            filtered = {
                accession: cik for accession, cik in effective.accession_to_cik.items()
                if effective.accession_to_lineage[accession] not in overlapping_lineages
            }
            effective = replace(
                effective,
                accession_to_cik=filtered,
                effective_accessions_by_lineage={
                    lineage: accessions
                    for lineage, accessions in effective.effective_accessions_by_lineage.items()
                    if lineage not in overlapping_lineages
                },
                additive_accessions=frozenset(
                    effective.additive_accessions & set(filtered)
                ),
                effective_filers=frozenset(filtered.values()),
            )
        self.connection.execute("DELETE FROM positions WHERE side = ?", (side,))

        sql = """
            INSERT INTO positions(side,cik,security_key,issuer,shares,value_reported)
            VALUES(?,?,?,?,?,?)
            ON CONFLICT(side,cik,security_key) DO UPDATE SET
              shares = shares + excluded.shares,
              value_reported = value_reported + excluded.value_reported,
              issuer = CASE WHEN positions.issuer = '' THEN excluded.issuer ELSE positions.issuer END
        """
        batch: list[tuple[Any, ...]] = []
        retained_rows = 0
        long_share_rows = 0
        holding_filers: set[str] = set()
        for source in table_sets:
            indexes, rows = _column_indexes(getattr(source, "holdings", ()))

            def at(values: tuple[Any, ...], *names: str) -> Any:
                for name in names:
                    idx = indexes.get(name)
                    if idx is not None:
                        value = _clean(values[idx])
                        if value is not None:
                            return value
                return None

            for values in rows:
                accession = _text(at(values, "accession", "accession_number"))
                cik = effective.accession_to_cik.get(accession)
                if not cik:
                    continue
                retained_rows += 1
                put_call = _text(at(values, "put_call", "putcall")).upper()
                amount_type = _text(at(
                    values, "shares_or_principal_amount_type", "ssh_prn_type", "sshprnamttype"
                )).upper()
                if put_call or amount_type != "SH":
                    continue
                security_key = _text(at(values, "cusip")).upper()
                shares = _number(at(values, "shares_or_principal_amount", "ssh_prn_amt", "sshprnamt"))
                if not security_key or shares <= 0:
                    continue
                issuer = _text(at(values, "issuer_name", "name_of_issuer", "nameofissuer"))
                # The live ecosystem contains both X0202 dollar values and legacy
                # thousand-dollar values.  Preserve the raw report value; this
                # share-based projection never guesses a USD unit.
                value_reported = _number(at(values, "value", "value_reported"))
                batch.append((side, cik, security_key, issuer, shares, value_reported))
                long_share_rows += 1
                holding_filers.add(cik)
                if len(batch) >= 20_000:
                    self.connection.executemany(sql, batch)
                    batch.clear()
        if batch:
            self.connection.executemany(sql, batch)
        self.connection.commit()
        self.quarters[side] = effective
        self.row_counts[side] = {
            "retained_holding_rows": retained_rows,
            "long_share_rows": long_share_rows,
            "holding_filers": len(holding_filers),
            "quality_excluded_accessions": len(
                excluded_effective
            ),
            "quality_excluded_lineages": len(quality_excluded_lineages),
            "overlapping_amendment_lineages": len(overlapping_lineages),
        }
        return effective

    def compile(
        self,
        *,
        ticker_by_cusip: Mapping[str, Any] | None = None,
        sector_by_ticker: Mapping[str, Any] | None = None,
        generated_at: str | None = None,
        current_source: Mapping[str, Any] | None = None,
        baseline_source: Mapping[str, Any] | None = None,
        identifier_resolution: Mapping[str, Any] | None = None,
        classification_resolution: Mapping[str, Any] | None = None,
        source_cutoff_at: str | None = None,
        latest_known: bool = False,
        action_threshold_pct: float = DEFAULT_ACTION_THRESHOLD_PCT,
        max_rows: int = DEFAULT_MAX_ROWS,
        minimum_mapping_coverage_pct: float = DEFAULT_MINIMUM_MAPPING_COVERAGE_PCT,
        research_minimum_quarters: int = 8,
        research_maximum_candidates: int = 500,
        compilation_inputs: Mapping[str, Any] | None = None,
    ) -> CensusCompilation:
        if set(self.quarters) != {"current", "baseline"}:
            raise RuntimeError("both current and baseline quarters must be ingested")
        if action_threshold_pct <= 0:
            raise ValueError("action_threshold_pct must be positive")
        if max_rows < 1 or max_rows > DEFAULT_MAX_ROWS:
            raise ValueError(f"max_rows must be between 1 and {DEFAULT_MAX_ROWS}")
        if not 0 < minimum_mapping_coverage_pct <= 100:
            raise ValueError("minimum_mapping_coverage_pct must be in (0, 100]")

        current = self.quarters["current"]
        baseline = self.quarters["baseline"]
        paired = (
            set(current.original_filers)
            & set(baseline.original_filers)
            & set(current.effective_filers)
            & set(baseline.effective_filers)
        )
        self.connection.execute("DELETE FROM paired")
        self.connection.executemany("INSERT INTO paired(cik) VALUES(?)", ((cik,) for cik in sorted(paired)))
        self.connection.commit()

        ticker_map = _normalize_ticker_map(ticker_by_cusip)
        if not ticker_map:
            raise RuntimeError("a non-empty, provenance-bound ticker map is required")
        sectors: dict[str, str] = {}
        for ticker, value in (sector_by_ticker or {}).items():
            if isinstance(value, Mapping):
                sector = _text(value.get("sector"))
            else:
                sector = _text(value)
            if sector:
                sectors[_text(ticker).upper()] = sector

        security_stats: dict[str, dict[str, Any]] = {}
        filer_actions: dict[str, int] = {}
        sector_filer_scores: dict[tuple[str, str], int] = {}
        def action_for(now_shares: float, prior_shares: float) -> str:
            if prior_shares <= 0 < now_shares:
                return "new"
            if now_shares <= 0 < prior_shares:
                return "exit"
            if prior_shares > 0:
                change_pct = (now_shares - prior_shares) / prior_shares * 100.0
                if change_pct >= action_threshold_pct:
                    return "add"
                if change_pct <= -action_threshold_pct:
                    return "trim"
            return "unchanged"
        query = """
          WITH keys AS (
            SELECT cik, security_key FROM positions WHERE side='current'
            UNION
            SELECT cik, security_key FROM positions WHERE side='baseline'
          )
          SELECT k.cik, k.security_key,
                 COALESCE(c.shares,0), COALESCE(b.shares,0),
                 CASE WHEN COALESCE(c.issuer,'') <> '' THEN c.issuer ELSE COALESCE(b.issuer,'') END
            FROM keys k
            JOIN paired p ON p.cik=k.cik
            LEFT JOIN positions c ON c.side='current' AND c.cik=k.cik AND c.security_key=k.security_key
            LEFT JOIN positions b ON b.side='baseline' AND b.cik=k.cik AND b.security_key=k.security_key
        """
        for cik, security_key, now_shares, prior_shares, issuer in self.connection.execute(query):
            now_shares = float(now_shares)
            prior_shares = float(prior_shares)
            action = action_for(now_shares, prior_shares)
            stat = security_stats.setdefault(str(security_key), {
                "issuer": str(issuer or ""), "current_holders": 0, "baseline_holders": 0,
                "continuing_holders": 0, "continuing_share_ratios": [],
                "new": 0, "add": 0, "trim": 0, "exit": 0,
            })
            if now_shares > 0:
                stat["current_holders"] += 1
            if prior_shares > 0:
                stat["baseline_holders"] += 1
            if now_shares > 0 and prior_shares > 0:
                stat["continuing_holders"] += 1
                stat["continuing_share_ratios"].append(now_shares / prior_shares)
            if action != "unchanged":
                stat[action] += 1

        mapped_current_positions = 0
        total_current_positions = 0
        filer_current: dict[str, dict[str, float]] = {}
        for cik, security_key, value_reported in self.connection.execute(
            "SELECT cik, security_key, value_reported FROM positions WHERE side='current'"
        ):
            total_current_positions += 1
            mapped = str(security_key) in ticker_map
            if mapped:
                mapped_current_positions += 1
            metrics = filer_current.setdefault(str(cik), {"positions": 0, "mapped": 0})
            metrics["positions"] += 1
            metrics["mapped"] += int(mapped)

        mapping_pct = (
            round(mapped_current_positions / total_current_positions * 100.0, 1)
            if total_current_positions else 0.0
        )
        if total_current_positions and mapping_pct < minimum_mapping_coverage_pct:
            raise RuntimeError(
                "ticker mapping coverage is below the configured publication fence: "
                f"{mapping_pct:.1f}% < {minimum_mapping_coverage_pct:.1f}%"
            )

        leaders: list[dict[str, Any]] = []
        sector_stats: dict[str, dict[str, int]] = {}
        structural_security_keys: set[str] = set()
        share_factor_security_keys: set[str] = set()
        for cusip, stat in security_stats.items():
            mapped = ticker_map.get(cusip)
            if not mapped:
                continue
            ticker = mapped["ticker"]
            net = int(stat["new"] + stat["add"] - stat["trim"] - stat["exit"])
            activity = int(stat["new"] + stat["add"] + stat["trim"] + stat["exit"])
            if net == 0 or activity == 0:
                continue
            holder_delta = int(stat["current_holders"] - stat["baseline_holders"])
            # Large one-quarter holder discontinuities dominated by entries/exits
            # are usually mergers, spin-offs, take-privates, or CUSIP changes.  They
            # stay in evidence but are withheld from a board described as buying.
            if is_structural_holder_discontinuity(
                holder_delta=holder_delta,
                new_filers=int(stat["new"]),
                exiting_filers=int(stat["exit"]),
                activity=activity,
            ):
                structural_security_keys.add(cusip)
                continue
            continuing_holders = int(stat["continuing_holders"])
            holder_stability = (
                continuing_holders
                / max(int(stat["current_holders"]), int(stat["baseline_holders"]), 1)
            )
            common_factor = infer_common_share_factor(
                stat["continuing_share_ratios"]
            )
            if common_factor is not None and holder_stability >= 0.9:
                structural_security_keys.add(cusip)
                share_factor_security_keys.add(cusip)
                continue
            sector = sectors.get(ticker, "Unclassified")
            row = {
                "ticker": ticker,
                "name": mapped.get("name") or ticker,
                "issuer": stat["issuer"],
                "sector": sector,
                "net_increasers": net,
                "net_filer_delta": net,
                "holder_delta": holder_delta,
                "paired_observations": activity,
                "new_filers": int(stat["new"]),
                "adding_filers": int(stat["add"]),
                "trimming_filers": int(stat["trim"]),
                "exiting_filers": int(stat["exit"]),
            }
            leaders.append(row)
            sec = sector_stats.setdefault(sector, {"net": 0, "activity": 0, "securities": 0})
            sec["securities"] += 1

        # Re-run the disk-backed paired comparison for the much smaller eligible
        # mapped universe so sector counts are unique filers, not security actions.
        for cik, security_key, now_shares, prior_shares, _issuer in self.connection.execute(query):
            security_key = str(security_key)
            mapped = ticker_map.get(security_key)
            if not mapped or security_key in structural_security_keys:
                continue
            action = action_for(float(now_shares), float(prior_shares))
            if action == "unchanged":
                continue
            filer_actions[str(cik)] = filer_actions.get(str(cik), 0) + 1
            sector = sectors.get(mapped["ticker"], "Unclassified")
            direction = 1 if action in {"new", "add"} else -1
            key = (sector, str(cik))
            sector_filer_scores[key] = sector_filer_scores.get(key, 0) + direction

        for (sector, _cik), score in sector_filer_scores.items():
            if score == 0:
                continue
            sec = sector_stats.setdefault(sector, {"net": 0, "activity": 0, "securities": 0})
            sec["net"] += 1 if score > 0 else -1
            sec["activity"] += 1

        broadening = sorted(
            (row for row in leaders if row["net_filer_delta"] > 0),
            key=lambda row: (row["net_filer_delta"], row["holder_delta"], row["paired_observations"], row["ticker"]),
            reverse=True,
        )[:max_rows]
        narrowing = sorted(
            (row for row in leaders if row["net_filer_delta"] < 0),
            key=lambda row: (row["net_filer_delta"], row["holder_delta"], -row["paired_observations"], row["ticker"]),
        )[:max_rows]
        sector_breadth = [
            {
                "sector": sector,
                "name": sector,
                "net_filer_delta": values["net"],
                "net_increasers": values["net"],
                "paired_observations": values["activity"],
                "security_count": values["securities"],
            }
            for sector, values in sorted(
                sector_stats.items(),
                key=lambda item: (abs(item[1]["net"]), item[1]["activity"], item[0]),
                reverse=True,
            )[:max_rows]
        ]

        generated = generated_at or _utc_now()
        cutoff = source_cutoff_at or generated
        current_count = len(current.original_filers)
        paired_count = len(paired)
        public = {
            "schema": PUBLIC_SCHEMA,
            "state": "complete",
            "generated_at": generated,
            "identity_grain": "filer",
            "periods": {"current": current.period_end, "baseline": baseline.period_end},
            "coverage": {
                "current_original_filings": current_count,
                "baseline_original_filings": len(baseline.original_filers),
                "paired_filings": paired_count,
                "progress_pct": round(paired_count / current_count * 100.0, 1) if current_count else 0.0,
                "current_notice_filers": len(current.notice_filers),
                "current_amendments": current.amendment_count,
                "current_holding_filers": self.row_counts["current"]["holding_filers"],
                "current_long_positions": total_current_positions,
                "mapped_long_positions": mapped_current_positions,
                "mapping_coverage_pct": mapping_pct,
                "value_unit_status": "excluded_mixed_reported_units",
                "current_quality_excluded_reports": self.row_counts["current"]["quality_excluded_accessions"],
                "baseline_quality_excluded_reports": self.row_counts["baseline"]["quality_excluded_accessions"],
                "current_quality_excluded_lineages": self.row_counts["current"]["quality_excluded_lineages"],
                "baseline_quality_excluded_lineages": self.row_counts["baseline"]["quality_excluded_lineages"],
                "current_overlapping_amendment_lineages": self.row_counts["current"]["overlapping_amendment_lineages"],
                "baseline_overlapping_amendment_lineages": self.row_counts["baseline"]["overlapping_amendment_lineages"],
                "structural_event_security_exclusions": len(structural_security_keys),
                "share_factor_security_exclusions": len(share_factor_security_keys),
            },
            "scope": {
                "population": "all_sec_13f_filers",
                "includes_passive_quant_custody": True,
                "skill_weighted": False,
                "comparison_basis": "same_filer_completed_quarters",
                "action_basis": "long_share_count_change",
                "reported_value_use": "excluded_until_unit_resolved",
                "corporate_action_filter": "holder_discontinuity_and_common_share_factor_v2",
                "materiality_threshold_pct": float(action_threshold_pct),
                "notices_are_zero_portfolios": False,
                "authority": "context_only",
            },
            "leaders": {"broadening": broadening, "narrowing": narrowing},
            "sector_breadth": sector_breadth,
            "freshness": {
                "as_of": generated,
                "source_cutoff_at": cutoff,
                "latest_known": bool(latest_known),
                "current_source": dict(current_source or {}),
                "baseline_source": dict(baseline_source or {}),
                "identifier_resolution": dict(identifier_resolution or {}),
                "sector_classification": dict(classification_resolution or {
                    "temporal_policy": "current_map_not_point_in_time",
                }),
                "duplicate_original_lineages": current.duplicate_original_lineages,
                "orphan_amendment_lineages": current.orphan_amendment_lineages,
                "relationship_deduplication": "as_filed_filer_grain",
            },
        }
        encoded_public = compilation_json_bytes(public)
        if len(encoded_public) > PUBLIC_MAX_BYTES:
            raise ValueError(f"public census payload exceeds {PUBLIC_MAX_BYTES} bytes")

        excluded_classes = {"passive", "quant_market_maker", "custody", "bank", "insurer", "pension"}
        candidates: list[dict[str, Any]] = []
        for cik, metrics in filer_current.items():
            positions = int(metrics["positions"])
            mapped_pct = float(metrics["mapped"]) / positions * 100.0 if positions else 0.0
            decisions = int(filer_actions.get(cik, 0))
            density = decisions / positions if positions else 0.0
            name = current.filer_names.get(cik, "")
            manager_class, provenance = classify_manager_name(name)
            interpretability = 1.0 if 10 <= positions <= 250 else max(0.0, 1.0 - abs(positions - 130) / 1_000.0)
            readiness = (
                min(mapped_pct / 100.0, 1.0) * 35.0
                + min(2 / max(research_minimum_quarters, 1), 1.0) * 25.0
                + min(density / 0.25, 1.0) * 25.0
                + interpretability * 15.0
            )
            candidates.append({
                "cik": cik,
                "manager_name": name,
                "manager_class": manager_class,
                "classification_provenance": provenance,
                "position_count": positions,
                "mapping_coverage_pct": round(mapped_pct, 1),
                "material_decisions": decisions,
                "decision_density_pct": round(density * 100.0, 2),
                "retained_quarters": 2,
                "readiness_score": round(readiness, 2),
                "research_eligible": False,
                "exclusion_reason": (
                    f"manager_class:{manager_class}" if manager_class in excluded_classes
                    else f"history_lt_{research_minimum_quarters}_quarters"
                ),
                "performance_status": "ungraded",
            })
        candidates.sort(key=lambda row: (row["readiness_score"], row["mapping_coverage_pct"], -row["position_count"], row["cik"]), reverse=True)
        candidates = candidates[:research_maximum_candidates]
        bench = {
            "schema": RESEARCH_BENCH_SCHEMA,
            "status": "screened_not_promoted",
            "generated_at": generated,
            "as_of_period": current.period_end,
            "point_in_time": False,
            "temporal_policy": "current_identifier_and_classification_maps",
            "minimum_quarters_for_scoring": research_minimum_quarters,
            "candidate_count": len(candidates),
            "eligible_count": 0,
            "authority": "research_only",
            "candidates": candidates,
        }
        bench_bytes = compilation_json_bytes(bench)
        if compilation_inputs is None:
            identity_inputs: dict[str, Any] = {
                "schema": "institutional_13f.compilation_inputs/v1",
                "periods": {"current": current.period_end, "baseline": baseline.period_end},
                "generated_at": generated,
                "source_cutoff_at": cutoff,
                "current_source": dict(current_source or {}),
                "baseline_source": dict(baseline_source or {}),
                "identifier_resolution": dict(identifier_resolution or {}),
                "classification_resolution": dict(classification_resolution or {}),
                "parameters": {
                    "action_threshold_pct": float(action_threshold_pct),
                    "max_rows": int(max_rows),
                    "minimum_mapping_coverage_pct": float(minimum_mapping_coverage_pct),
                    "research_minimum_quarters": int(research_minimum_quarters),
                    "research_maximum_candidates": int(research_maximum_candidates),
                },
            }
        else:
            identity_inputs = dict(compilation_inputs)
        compilation_id = hashlib.sha256(
            compilation_json_bytes(identity_inputs)
        ).hexdigest()
        receipt = {
            "schema": "institutional_13f.compilation_receipt/v1",
            "compilation_id": compilation_id,
            "compilation_inputs": identity_inputs,
            "generated_at": generated,
            "current_period": current.period_end,
            "baseline_period": baseline.period_end,
            "public_sha256": hashlib.sha256(encoded_public).hexdigest(),
            "public_bytes": len(encoded_public),
            "research_bench_sha256": hashlib.sha256(bench_bytes).hexdigest(),
            "research_bench_bytes": len(bench_bytes),
            "research_candidate_count": len(candidates),
            "authority": "context_only",
        }
        return CensusCompilation(public_summary=public, research_bench=bench, receipt=receipt)


def load_ticker_map(path: str | Path) -> dict[str, dict[str, str]]:
    """Load the bounded OpenFIGI CUSIP map used only for display resolution."""
    import pandas as pd

    source = Path(path)
    if not source.is_file():
        return {}
    frame = pd.read_parquet(
        source, columns=["cusip", "ticker", "name", "exch", "sec_type"]
    )
    us_exchange_codes = {
        "US", "UN", "UQ", "UA", "UB", "UC", "UD", "UF", "UM", "UP",
        "UR", "UV", "UW", "NEW YORK", "NASDAQ/NGS",
    }
    eligible_equity_types = {
        "COMMON STOCK", "DEPOSITARY RECEIPT", "REIT", "PARTNERSHIP SHARES"
    }
    out: dict[str, dict[str, str]] = {}
    for cusip, ticker, name, exchange, security_type in frame.itertuples(index=False, name=None):
        key = _text(cusip).upper()
        symbol = _text(ticker).upper()
        # A retired US CUSIP can later resolve to a foreign symbol in OpenFIGI
        # (for example AZN's old ADR CUSIP resolving to AZNN in Mexico).  Only a
        # US trading composite/venue is eligible for a public ticker label.
        if (
            key and symbol
            and _text(exchange).upper() in us_exchange_codes
            and _text(security_type).upper() in eligible_equity_types
        ):
            out[key] = {
                "ticker": symbol,
                "name": _text(name),
                "security_type": _text(security_type),
            }
    return out


def write_compilation(
    compilation: CensusCompilation,
    *,
    public_path: str | Path,
    research_bench_path: str | Path | None = None,
    receipt_path: str | Path | None = None,
) -> None:
    """Write canonical projections atomically and prove exact readback bytes."""
    public_bytes = compilation_json_bytes(compilation.public_summary)
    bench_bytes = compilation_json_bytes(compilation.research_bench)
    receipt = compilation.receipt
    if (
        receipt.get("public_sha256") != hashlib.sha256(public_bytes).hexdigest()
        or receipt.get("public_bytes") != len(public_bytes)
        or receipt.get("research_bench_sha256") != hashlib.sha256(bench_bytes).hexdigest()
        or receipt.get("research_bench_bytes") != len(bench_bytes)
    ):
        raise ValueError("compilation receipt does not bind exact canonical artifact bytes")
    inputs = receipt.get("compilation_inputs")
    if not isinstance(inputs, Mapping) or receipt.get("compilation_id") != hashlib.sha256(
        compilation_json_bytes(inputs)
    ).hexdigest():
        raise ValueError("compilation receipt identity is invalid")

    outputs: list[tuple[Path, bytes]] = [(Path(public_path), public_bytes)]
    if research_bench_path is not None:
        outputs.append((Path(research_bench_path), bench_bytes))
    if receipt_path is not None:
        outputs.append((Path(receipt_path), compilation_json_bytes(receipt)))

    staged: list[tuple[Path, Path, bytes]] = []
    try:
        for path, payload in outputs:
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_name(path.name + ".tmp")
            temporary.write_bytes(payload)
            if temporary.read_bytes() != payload:
                raise OSError(f"staged compilation readback failed: {path}")
            staged.append((path, temporary, payload))
        # The receipt is intentionally last: it is the completion marker for the
        # already materialized public and private projections.
        for path, temporary, _payload in staged:
            temporary.replace(path)
        for path, _temporary, payload in staged:
            if path.read_bytes() != payload:
                raise OSError(f"compilation readback failed: {path}")
    finally:
        for _path, temporary, _payload in staged:
            if temporary.exists():
                temporary.unlink()
