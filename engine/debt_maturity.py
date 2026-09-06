"""Issuer debt-maturity ladder — pure functions over SEC XBRL companyfacts.

No I/O. No network. No clock except an injected ``as_of``. This module reads an
already-parsed companyfacts mapping (as returned by the SEC XBRL companyfacts
API / collectors/sec_capital_structure_companyfacts.py) and extracts the
six-bucket annual debt-maturity ladder:

    next 12 months, year 2, year 3, year 4, year 5, after year 5

Every number is a reported XBRL fact or arithmetic over reported facts. No
score, no rank, no LLM text, no escalation is produced here (Neural Web A7 /
epistemics: this module never originates a signal).

Identity is by CIK only (packet B-F09-3 GATE 0 identity gate) — this module
never accepts or infers a ticker or company name.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Mapping

# Annual filing forms accepted as the ladder's source period.
_ANNUAL_FORMS = frozenset({"10-K", "10-K/A", "20-F", "40-F"})

# The only tag knowledge in the repo (frozen spec §2.1). key, XBRL tag, EN label, ZH label.
BUCKETS: tuple[tuple[str, str, str, str], ...] = (
    ("y1", "LongTermDebtMaturitiesRepaymentsOfPrincipalInNextTwelveMonths", "Next 12 months", "未来12个月"),
    ("y2", "LongTermDebtMaturitiesRepaymentsOfPrincipalInYearTwo", "Year 2", "第2年"),
    ("y3", "LongTermDebtMaturitiesRepaymentsOfPrincipalInYearThree", "Year 3", "第3年"),
    ("y4", "LongTermDebtMaturitiesRepaymentsOfPrincipalInYearFour", "Year 4", "第4年"),
    ("y5", "LongTermDebtMaturitiesRepaymentsOfPrincipalInYearFive", "Year 5", "第5年"),
    ("after5", "LongTermDebtMaturitiesRepaymentsOfPrincipalAfterYearFive", "After year 5", "5年以后"),
)

_STALE_DAYS = 550


def _canonical_cik(value: object) -> str:
    """Strict zero-padded 10-digit CIK. Mirrors
    collectors/sec_capital_structure_companyfacts.py:canonical_cik without
    importing a collector (I/O-adjacent module) into this pure engine."""
    raw = str(value or "").strip()
    if not raw.isdigit() or len(raw) > 10 or int(raw) == 0:
        raise ValueError(f"invalid CIK: {value!r}")
    return raw.zfill(10)


def _parse_date(value: Any) -> date | None:
    if not value:
        return None
    if isinstance(value, date):
        return value
    try:
        y, m, d = str(value).split("-")
        return date(int(y), int(m), int(d))
    except Exception:  # noqa: BLE001 — a malformed date is treated as absent, never fatal
        return None


def _usd_dollars(amount: float) -> str:
    a = abs(amount)
    sign = "-" if amount < 0 else ""
    if a >= 1_000_000_000:
        return f"{sign}${a / 1_000_000_000:.1f}B"
    if a >= 1_000_000:
        return f"{sign}${a / 1_000_000:.1f}M"
    if a >= 1_000:
        return f"{sign}${a / 1_000:.1f}K"
    return f"{sign}${a:.0f}"


def _candidate_periods(companyfacts: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Every (accn, end) period across all six bucket tags that is an annual
    filing, deduped and sorted by (filed desc, end desc)."""
    seen: dict[tuple[str, str], dict[str, Any]] = {}
    facts = ((companyfacts or {}).get("facts") or {}).get("us-gaap") or {}
    for _key, tag, _en, _zh in BUCKETS:
        tag_facts = facts.get(tag) or {}
        units = (tag_facts.get("units") or {})
        for entry in units.get("USD") or []:
            form = entry.get("form")
            fp = entry.get("fp")
            if form not in _ANNUAL_FORMS or fp != "FY":
                continue
            accn = entry.get("accn")
            end = entry.get("end")
            if not accn or not end:
                continue
            k = (accn, end)
            existing = seen.get(k)
            filed = entry.get("filed") or ""
            if existing is None or filed > existing.get("filed", ""):
                seen[k] = {"accn": accn, "end": end, "filed": filed, "form": form, "fy": entry.get("fy"), "fp": fp}
    return sorted(seen.values(), key=lambda p: (p.get("filed") or "", p.get("end") or ""), reverse=True)


def extract_maturity_ladder(
    companyfacts: Mapping[str, Any] | None,
    *,
    cik: str,
    as_of: date | None = None,
) -> dict[str, Any]:
    """Extract the six-bucket annual debt-maturity ladder for one issuer.

    ``cik`` is the canonical zero-padded 10-digit SEC CIK — the only identity
    this function accepts. It never takes a ticker or company name.
    """
    canon_cik = _canonical_cik(cik)
    as_of = as_of or date.today()

    if not companyfacts:
        return {
            "schema": "debt_maturity.v1",
            "status": "no_filings",
            "cik": canon_cik,
            "buckets": [],
            "total_reported_usd": None,
            "total_display": None,
            "near_share_pct": None,
            "buckets_reported": 0,
            "buckets_total": len(BUCKETS),
            "as_of": as_of.isoformat(),
        }

    periods = _candidate_periods(companyfacts)
    if not periods:
        return {
            "schema": "debt_maturity.v1",
            "status": "no_maturity_facts",
            "cik": canon_cik,
            "buckets": [],
            "total_reported_usd": None,
            "total_display": None,
            "near_share_pct": None,
            "buckets_reported": 0,
            "buckets_total": len(BUCKETS),
            "as_of": as_of.isoformat(),
        }

    winner = periods[0]
    win_accn, win_end = winner["accn"], winner["end"]

    facts = ((companyfacts or {}).get("facts") or {}).get("us-gaap") or {}
    buckets: list[dict[str, Any]] = []
    total = 0.0
    n_reported = 0

    for key, tag, en, zh in BUCKETS:
        tag_facts = facts.get(tag) or {}
        units = tag_facts.get("units") or {}
        row = {
            "key": key, "label_en": en, "label_zh": zh,
            "usd": None, "display": None, "share_pct": None,
            "reported": False, "tag": tag, "drop_reason": "absent",
        }
        # Search ALL unit keys for the winning (accn, end); a non-USD unit is a
        # deliberate not-reported (never scaled by a guess).
        found_any_unit = False
        found_usd = None
        for unit_key, entries in units.items():
            for entry in entries or []:
                if entry.get("accn") == win_accn and entry.get("end") == win_end and entry.get("form") in _ANNUAL_FORMS and entry.get("fp") == "FY":
                    found_any_unit = True
                    if unit_key == "USD":
                        found_usd = entry.get("val")
        if found_usd is not None:
            row["usd"] = found_usd
            row["reported"] = True
            row["display"] = _usd_dollars(found_usd)
            row["drop_reason"] = None
            total += found_usd
            n_reported += 1
        elif found_any_unit:
            row["drop_reason"] = "unit_not_usd"
        else:
            # check whether this tag exists at all, just under a different period
            other_period_present = False
            for unit_key, entries in units.items():
                for entry in entries or []:
                    if entry.get("form") in _ANNUAL_FORMS and entry.get("fp") == "FY":
                        other_period_present = True
            row["drop_reason"] = "period_mismatch" if other_period_present else "absent"
        buckets.append(row)

    for row in buckets:
        if row["reported"] and total:
            row["share_pct"] = round((row["usd"] / total) * 100)

    near_share_pct = buckets[0]["share_pct"] if buckets and buckets[0]["reported"] else None
    end_date = _parse_date(win_end)
    stale = bool(end_date and (as_of - end_date).days > _STALE_DAYS)

    return {
        "schema": "debt_maturity.v1",
        "status": "reported" if n_reported > 0 else "no_maturity_facts",
        "cik": canon_cik,
        "unit": "USD",
        "period": {
            "form": winner["form"],
            "fy": winner.get("fy"),
            "fp": winner.get("fp"),
            "end": win_end,
            "filed": winner.get("filed"),
            "accn": win_accn,
            "label": f"FY{winner.get('fy')}" if winner.get("fy") else win_end,
            "stale": stale,
        },
        "buckets": buckets,
        "total_reported_usd": total if n_reported else None,
        "total_display": _usd_dollars(total) if n_reported else None,
        "near_share_pct": near_share_pct,
        "buckets_reported": n_reported,
        "buckets_total": len(BUCKETS),
        "as_of": as_of.isoformat(),
    }
