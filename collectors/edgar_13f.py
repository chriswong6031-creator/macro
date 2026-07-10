"""SEC 13F-HR collector — quarterly institutional ("super-investor") holdings.

Every institutional manager with >$100M in 13(f) securities must file a Form
13F-HR within 45 days of quarter-end, listing each US-listed long position
(CUSIP, issuer, market value, shares). It is FREE and keyless from SEC EDGAR —
squarely on our SEC-native stack (collectors/edgar.py) — so a Dataroma /
WhaleWisdom-style "who owns this" context layer needs no paid vendor.

We track a CURATED list of well-known super-investor funds (config.smart_money),
NOT the ~10,000-filer long tail. For each fund we pull its filing list from the
submissions API, fetch the INFORMATION TABLE XML of the latest few 13F-HR
filings, and write one snapshot per (fund, period_end) under
data/smart_money/<slug>/<period_end>.parquet — mirroring collectors/holdings.py.
engine/smart_money.py then diffs consecutive quarters into new/add/trim/exit.

HONESTY (surfaced in the UI disclaimer): 13F is QUARTERLY with a ~45-day lag
(amendments after that) — a stale, partial picture of LONG-ONLY US equity stakes
>= $100M, with no shorts, no options detail, no non-US/private positions. CUSIPs
are name-matched to our ticker universe (no free CUSIP master), so some lines are
unresolved and hidden. This is CONTEXT on who holds a name, never a buy list or a
real-time signal, and it is NEVER wired into any score/allocation.
"""
from __future__ import annotations

import logging
import re
import time
from datetime import date, datetime

import pandas as pd

from collectors import edgar
from collectors.base import Adapter
from lib import config

log = logging.getLogger(__name__)

ARCHIVES = "https://www.sec.gov/Archives/edgar/data"
SUBMISSIONS = "https://data.sec.gov/submissions/CIK{:010d}.json"

# The 13F "value" column was reported in THOUSANDS of dollars until the SEC
# amendment took effect for periods ending on/after 2022-12-31, after which it is
# reported in actual dollars. We normalise to dollars using the period end. (Only
# the absolute $ display depends on this; pct-of-portfolio and share deltas — what
# the engine actually ranks on — are scale-invariant within a fund-quarter.)
_DOLLARS_FROM = date(2022, 12, 31)


def _ua() -> str:
    """SEC fair-access UA with a contact email (required by www.sec.gov/Archives)."""
    return (config.load().get("smart_money", {}) or {}).get("user_agent") \
        or edgar._cfg()["user_agent"]


def _headers() -> dict:
    return {"User-Agent": _ua(), "Accept-Encoding": "gzip, deflate"}


def _get_json(url: str, retries: int = 3) -> dict | None:
    import requests
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=_headers(), timeout=30)
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return r.json()
        except Exception as e:  # noqa: BLE001 — tolerate per-call failure
            if attempt == retries - 1:
                log.warning("13f GET failed %s: %s", url.split("edgar/")[-1], e)
                return None
            time.sleep(1.5 * (attempt + 1))
    return None


def _strip_ns(tag: str) -> str:
    """'{http://www.sec.gov/edgar/document/thirteenf/informationtable}infoTable'
    -> 'infoTable'. 13F info tables are namespaced and the namespace URI varies by
    filing year, so we match on the local name."""
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _txt(node, name: str) -> str:
    """First descendant whose local tag == name, text stripped ('' if absent)."""
    if node is None:
        return ""
    for el in node.iter():
        if _strip_ns(el.tag) == name and el.text:
            return el.text.strip()
    return ""


def parse_information_table(xml_text: str) -> pd.DataFrame:
    """Parse a 13F INFORMATION TABLE XML into a tidy holdings frame. PURE — no
    network, no config; unit tested directly. Columns:
    [cusip, issuer, title_class, value_raw, shares, sh_type]. Empty frame if the
    document carries no infoTable rows (e.g. the cover-page primary doc)."""
    from lxml import etree
    try:
        root = etree.fromstring(xml_text.encode("utf-8") if isinstance(xml_text, str)
                                else xml_text)
    except Exception:  # noqa: BLE001 — a non-XML / cover-page doc just yields nothing
        return pd.DataFrame(columns=["cusip", "issuer", "title_class",
                                     "value_raw", "shares", "sh_type"])
    rows = []
    for el in root.iter():
        if _strip_ns(el.tag) != "infoTable":
            continue
        cusip = _txt(el, "cusip").upper()
        val = _txt(el, "value").replace(",", "")
        # shares + type live under shrsOrPrnAmt -> sshPrnamt / sshPrnamtType
        shrs_node = next((c for c in el.iter() if _strip_ns(c.tag) == "shrsOrPrnAmt"), None)
        shares = _txt(shrs_node, "sshPrnamt").replace(",", "")
        sh_type = _txt(shrs_node, "sshPrnamtType") or "SH"
        try:
            value_raw = float(val) if val else 0.0
        except ValueError:
            value_raw = 0.0
        try:
            shares_f = float(shares) if shares else 0.0
        except ValueError:
            shares_f = 0.0
        if not cusip:
            continue
        rows.append({
            "cusip": cusip,
            "issuer": _txt(el, "nameOfIssuer"),
            "title_class": _txt(el, "titleOfClass"),
            "value_raw": value_raw,
            "shares": shares_f,
            "sh_type": sh_type,
        })
    df = pd.DataFrame(rows, columns=["cusip", "issuer", "title_class",
                                     "value_raw", "shares", "sh_type"])
    if df.empty:
        return df
    # collapse a manager's multiple lots of the same security/class into one row
    df = (df.groupby(["cusip", "issuer", "title_class", "sh_type"], as_index=False)
            .agg(value_raw=("value_raw", "sum"), shares=("shares", "sum")))
    return df


def value_to_dollars(value_raw: float, period_end: date) -> float:
    """Apply the thousands->dollars convention by period end."""
    return value_raw * (1.0 if period_end >= _DOLLARS_FROM else 1000.0)


class Edgar13FAdapter(Adapter):
    """Curated super-investor 13F snapshots. Quarterly + 45d lag, so stale_after is
    set high and this is best routed to the weekly collect."""

    name = "edgar_13f"
    group = "smart_money"
    stale_after_days = 120

    def __init__(self) -> None:
        self.cfg = config.load().get("smart_money", {}) or {}
        self.dir = config.data_dir() / self.group
        if not self.cfg.get("enabled", True):
            self.expected_failure = "smart_money disabled in config"

    # snapshots are written directly (one file per fund per quarter), so fetch()
    # returns only a tiny freshness summary series (mirrors collectors/holdings.py).
    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        if not self.cfg.get("enabled", True):
            raise RuntimeError("smart_money disabled in config")
        funds = self.cfg.get("funds", {}) or {}
        keep = int(self.cfg.get("history_quarters", 2))
        if full_history:
            keep = max(keep, int(self.cfg.get("backfill_quarters", 8)))
        processed, wrote, errors, written = 0, 0, [], 0
        for slug, spec in funds.items():
            try:
                n = self._fetch_fund(slug, spec, keep)
                processed += 1            # reached + parsed the fund's filing list
                if n:
                    wrote += 1
                    written += n
            except Exception as e:  # noqa: BLE001 — one fund must not kill the rest
                errors.append(f"{slug}: {e}")
                log.warning("13f %s failed: %s", slug, e)
        # Only a TRUE outage (EVERY fund errored) is a failure. "Processed fine,
        # nothing new to write" is the NORMAL steady state for a quarterly source
        # with a 45-day filing lag — between windows every snapshot is already on
        # disk, so written==0 is expected and must NOT trip the breaker.
        if processed == 0:
            raise RuntimeError(f"all 13F funds failed: {errors[:5]}")
        log.info("13f: %d/%d funds processed, %d wrote new (%d snapshots)",
                 processed, len(funds), wrote, written)
        s = pd.DataFrame({"funds_ok": [processed]}, index=[pd.Timestamp(date.today())])
        return {"smart_money_runs": s}

    # -- per-fund ------------------------------------------------------------- #
    def _fetch_fund(self, slug: str, spec: dict, keep: int) -> int:
        cik = int(spec["cik"])
        name = spec.get("name", slug)
        originals, amendments = self._list_13f(cik)
        if not originals:
            log.info("13f %s (CIK %d): no 13F-HR filings", slug, cik)
            return 0
        d = self.dir / slug
        d.mkdir(parents=True, exist_ok=True)
        written = 0

        # Originals stay at top-level: data/smart_money/<slug>/<period_end>.parquet
        for f in originals[:keep]:
            period_end = f["period_end"]
            out = d / f"{period_end}.parquet"
            if out.exists():                       # immutable once filed; never refetch
                continue
            snap = self._fetch_filing(cik, slug, name, f)
            if snap is not None and not snap.empty:
                snap.to_parquet(out)
                written += 1
                time.sleep(0.12)                   # SEC fair-access pacing

        # Amendments go under amendments/ subdir (SM2-R7 PIT-honest snapshots).
        # Only ingest amendments whose period_end is within the kept-quarters window.
        # Engine default paths use d.glob("*.parquet") — top-level only — so
        # amendments/ subdir CANNOT leak into engine scoring paths.
        kept_periods = {f["period_end"] for f in originals[:keep]}
        amend_dir = d / "amendments"
        for f in amendments:
            if f["period_end"] not in kept_periods:
                continue                           # outside the retained window
            period_end = f["period_end"]
            filing_date = f.get("filing_date", "unknown")
            amend_out = amend_dir / f"{period_end}__{filing_date}.parquet"
            if amend_out.exists():                 # immutable; never refetch
                continue
            amend_dir.mkdir(parents=True, exist_ok=True)
            snap = self._fetch_filing(cik, slug, name, f)
            if snap is not None and not snap.empty:
                snap.to_parquet(amend_out)
                written += 1
                time.sleep(0.12)

        return written

    def _list_13f(self, cik: int) -> tuple[list[dict], list[dict]]:
        """Most-recent-first lists of this fund's 13F-HR and 13F-HR/A filings.

        Returns (originals, amendments) where each entry is:
            {accession, period_end, filing_date}

        Originals (13F-HR) are the scoring anchors; amendments (13F-HR/A) are
        ingested as separate PIT snapshots under an amendments/ subdir (SM2-R7).
        13F-NT (notice of late filing) and other variants are excluded.
        """
        data = _get_json(SUBMISSIONS.format(cik), edgar._cfg()["retries"])
        time.sleep(0.12)
        if not data:
            return [], []
        recent = (data.get("filings", {}) or {}).get("recent", {}) or {}
        forms = recent.get("form", [])
        accs = recent.get("accessionNumber", [])
        reps = recent.get("reportDate", [])
        fils = recent.get("filingDate", [])
        originals: list[dict] = []
        amendments: list[dict] = []
        for i, form in enumerate(forms):
            if form not in ("13F-HR", "13F-HR/A"):
                continue
            entry = {
                "accession": accs[i],
                "period_end": reps[i],
                "filing_date": fils[i] if i < len(fils) else "",
            }
            if form == "13F-HR":
                originals.append(entry)
            else:
                amendments.append(entry)
        # newest-first by period_end (filings feed is already newest-first, but sort to be safe)
        originals = sorted(originals, key=lambda r: r["period_end"], reverse=True)
        amendments = sorted(amendments, key=lambda r: r["period_end"], reverse=True)
        return originals, amendments

    def _fetch_filing(self, cik: int, slug: str, name: str, f: dict) -> pd.DataFrame | None:
        acc_nodash = f["accession"].replace("-", "")
        base = f"{ARCHIVES}/{cik}/{acc_nodash}"
        idx = _get_json(f"{base}/index.json", edgar._cfg()["retries"])
        time.sleep(0.12)
        if not idx:
            return None
        items = ((idx.get("directory", {}) or {}).get("item", []) or [])
        xmls = [it["name"] for it in items if str(it.get("name", "")).lower().endswith(".xml")]
        # prefer the obvious info-table filenames; fall back to scanning every xml
        pref = [n for n in xmls if re.search(r"(info.?table|form13f|13flist)", n, re.I)]
        for fname in (pref + [n for n in xmls if n not in pref]):
            html = self._get_text(f"{base}/{fname}")
            if not html:
                continue
            df = parse_information_table(html)
            if not df.empty:
                return self._finalize(df, cik, slug, name, f)
        log.info("13f %s %s: no info table among %d xml files", slug, f["period_end"], len(xmls))
        return None

    def _finalize(self, df: pd.DataFrame, cik: int, slug: str, name: str,
                  f: dict) -> pd.DataFrame:
        pe = pd.to_datetime(f["period_end"]).date()
        df = df.copy()
        df["value_usd"] = df["value_raw"].apply(lambda v: value_to_dollars(v, pe))
        df["fund_slug"] = slug
        df["fund_name"] = name
        df["fund_cik"] = cik
        df["period_end"] = f["period_end"]
        df["filing_date"] = f.get("filing_date", "")
        df["as_of"] = f["period_end"]
        return df.drop(columns=["value_raw"])

    def _get_text(self, url: str) -> str | None:
        import requests
        try:
            r = requests.get(url, headers=_headers(), timeout=30)
            time.sleep(0.12)
            if r.status_code != 200:
                return None
            return r.text
        except Exception as e:  # noqa: BLE001
            log.debug("13f GET text failed %s: %s", url, e)
            return None
