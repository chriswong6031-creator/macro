"""SEC EDGAR 8-K MATERIAL-EVENT collector — the filing-time latency channel.

8-K current reports are filed within ~4 business days of a material corporate event, so
they lead the news narrative AND the tape. This collector reads the structured SEC
submissions feed (data.sec.gov/submissions/CIK##########.json — keyless, the `items` field
is machine-readable, not text-parsed) for every narrative-basket member, keeps only MATERIAL
item codes (new material agreements, acquisitions, financings, leadership changes, Reg-FD /
other material events — NOT routine earnings 2.02 / voting 5.07 / exhibits 9.01), and writes:

  * data/edgar/material_8k_events.parquet  — append-only, key-deduped per accession (PIT +
      _first_seen). Per-TICKER convergence channel (engine.altdata `material_events`).
  * data/edgar/material_8k_velocity.parquet — derived per-BASKET count, recent-60d vs
      prior-60d (the 'theme_event' Divergence-Radar leg in engine.theme_activity).

The ONLY new source that touches all 31 themes — including the healthcare blind spot, where
FDA actions land as 8-K item 8.01. Keyless; reuses edgar.py's cached CIK map + fair-access UA.
Display / context only.
"""
from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime, timezone

import pandas as pd
import requests

from collectors.base import Adapter, is_connection_error
from lib import config

log = logging.getLogger(__name__)

SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{:010d}.json"
TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
# SEC fair-access requires a descriptive name + contact email; www.sec.gov 403s a UA without
# one (data.sec.gov is more lenient). RFC2606 placeholder — same pattern as edgar_trumpflow.
_SEC_UA = "macro-dashboard admin@macro-dashboard.example.com"


def _sec_get_json(url: str, retries: int = 3, timeout: int = 30) -> dict | None:
    last = None
    for attempt in range(retries):
        try:
            r = requests.get(url, headers={"User-Agent": _SEC_UA, "Accept-Encoding": "gzip, deflate"}, timeout=timeout)
            if r.status_code in (429, 500, 502, 503, 504):
                raise requests.HTTPError(f"HTTP {r.status_code}", response=r)
            r.raise_for_status()
            return r.json()
        except Exception as e:  # noqa: BLE001
            last = e
            if attempt < retries - 1:
                time.sleep(1.5 * (attempt + 1))
    if last is not None and is_connection_error(last):
        raise last
    return None


def _company_tickers() -> dict | None:
    """SEC ticker->CIK file, cached locally (shared with collectors/edgar.py). Fetched with a
    fair-access UA so www.sec.gov doesn't 403; falls back to the cache on any fetch failure."""
    cache = config.data_dir() / "edgar" / "company_tickers.json"
    if cache.exists():
        try:
            return json.loads(cache.read_text())
        except Exception:  # noqa: BLE001
            pass
    data = _sec_get_json(TICKERS_URL)
    if data:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(data))
    return data


def _cik_map(universe: list[str]) -> dict[str, int]:
    """ticker -> CIK from SEC company_tickers.json (exact + dash/dot variants)."""
    data = _company_tickers()
    if not data:
        return {}
    sec = {row["ticker"].upper(): int(row["cik_str"]) for row in data.values()}
    out: dict[str, int] = {}
    for t in universe:
        u = t.upper()
        for cand in (u, u.replace("-", "."), u.replace(".", "-"), u.split("-")[0], u.split(".")[0]):
            if cand in sec:
                out[t] = sec[cand]
                break
    return out
# material item codes worth a signal (activity, not routine housekeeping):
#   1.01 material definitive agreement · 1.02 termination of material agreement ·
#   1.03 bankruptcy/receivership · 2.01 completion of acquisition ·
#   2.03 creation of a direct financial obligation ·
#   2.04 triggering of direct financial obligation (default/acceleration) ·
#   3.01 delisting notice / listing-standard failure ·
#   3.02 unregistered equity sales · 4.02 non-reliance on prior financials
#   (restatement/material weakness) · 5.02 director/officer change ·
#   7.01 Reg-FD disclosure · 8.01 other material event (where FDA/major news lands)
# LHB-R7 expansion for long-hold A6 hard-stop routing + B1 hardening ladder
# (research/LONG_HOLD_LOBE_BRAINSTORM_ADJUDICATION_BY_FABLE.md)
MATERIAL_ITEMS = {
    "1.01", "1.02", "1.03",
    "2.01", "2.03", "2.04",
    "3.01", "3.02",
    "4.02",
    "5.02",
    "7.01", "8.01",
}

# Velocity radar leg pinned to the original six codes — the per-basket velocity feeds
# the live theme Divergence-Radar leg (engine.theme_activity); the LHB-R7 expansion
# must not silently shift that signal, so velocity stays pinned to the original six
# codes.  Expanded codes are for downstream long-hold consumers of
# material_8k_events.parquet only.
LEGACY_VELOCITY_ITEMS = frozenset({"1.01", "2.01", "2.03", "5.02", "7.01", "8.01"})
_ITEM_RE = re.compile(r"\d\.\d{2}")
RECENT_D = 60
PRIOR_D = 60
PACE_S = 0.12  # SEC fair-access: <=10 req/s


def _membership() -> dict:
    try:
        return json.loads((config.data_dir() / "baskets" / "membership.json").read_text()).get("baskets", {})
    except Exception:  # noqa: BLE001
        return {}


def _universe(mem: dict) -> list[str]:
    seen, out = set(), []
    for b in mem.values():
        for m in b.get("members", []):
            t = m.get("ticker")
            if t and not m.get("removed") and t not in seen:
                seen.add(t)
                out.append(t)
    return out


class Edgar8KAdapter(Adapter):
    name = "edgar_8k"
    group = "edgar"
    stale_after_days = 5

    def _events_path(self):
        p = config.data_dir() / "edgar" / "material_8k_events.parquet"
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def _velocity_path(self):
        return config.data_dir() / "edgar" / "material_8k_velocity.parquet"

    def _pull_ticker(self, ticker: str, cik: int) -> list[dict]:
        """Material-8K rows for one CIK from the structured submissions feed."""
        data = _sec_get_json(SUBMISSIONS_URL.format(int(cik)), retries=3)
        if not data:
            return []
        rec = (data.get("filings") or {}).get("recent") or {}
        forms = rec.get("form") or []
        out = []
        for i, form in enumerate(forms):
            if form != "8-K":
                continue
            raw = (rec.get("items") or [None] * len(forms))[i] or ""
            codes = set(_ITEM_RE.findall(raw))
            mat = sorted(codes & MATERIAL_ITEMS)
            if not mat:
                continue
            out.append({
                "ticker": ticker, "cik": int(cik), "form": form,
                "filing_date": (rec.get("filingDate") or [None] * len(forms))[i],
                "items": ",".join(mat),
                "accession": (rec.get("accessionNumber") or [None] * len(forms))[i],
            })
        return out

    def _merge_events(self, new: pd.DataFrame) -> pd.DataFrame:
        new = new.copy()
        now_ts = datetime.now(timezone.utc).isoformat()
        # Only stamp rows that are genuinely new (will not exist in the stored file yet).
        new["_first_seen"] = now_ts
        path = self._events_path()
        if path.exists():
            old = pd.read_parquet(path)
            combined = pd.concat([old, new], ignore_index=True)
        else:
            combined = new

        # Groupby-accession merge: for each accession that appears more than once
        # (e.g. an accession already stored with truncated items before the LHB-R7
        # expansion, or a re-scan after back-fill), produce exactly one output row:
        #   items        — comma-joined sorted union of all codes seen across all rows
        #   _first_seen  — earliest (minimum) _first_seen stamp (preserves PIT)
        #   other cols   — values from the earliest-_first_seen row; for optional
        #                  LLM-extraction fields (amount_usd, counterparty,
        #                  extraction_ok) take the first non-null across duplicates so
        #                  enrichment results survive the merge
        def _agg_accession(grp: pd.DataFrame) -> pd.Series:
            # Sort so the earliest _first_seen row comes first
            grp = grp.sort_values("_first_seen")
            base = grp.iloc[0].copy()
            # Union of items codes
            all_codes: set[str] = set()
            for raw in grp["items"].dropna():
                for code in str(raw).split(","):
                    code = code.strip()
                    if code:
                        all_codes.add(code)
            base["items"] = ",".join(sorted(all_codes))
            # First non-null for optional enrichment columns
            for col in ("amount_usd", "counterparty", "extraction_ok"):
                if col in grp.columns:
                    non_null = grp[col].dropna()
                    base[col] = non_null.iloc[0] if not non_null.empty else None
            return base

        if combined.duplicated(subset=["accession"]).any():
            # groupby(as_index=False) keeps the key column in the result so we never
            # lose the accession column after apply() consumes it as the group key.
            combined = (
                combined.groupby("accession", sort=False, as_index=False)
                .apply(_agg_accession, include_groups=False)
                .reset_index(drop=True)
            )
            # Restore column order: mandatory cols first, then any extras
            mandatory = ["ticker", "cik", "form", "filing_date", "items", "accession", "_first_seen"]
            extras = [c for c in combined.columns if c not in mandatory]
            combined = combined[mandatory + extras]
        else:
            combined = combined.reset_index(drop=True)

        combined.to_parquet(path)
        return combined

    def _velocity(self, events: pd.DataFrame, mem: dict) -> pd.DataFrame:
        """Per-basket material-8K counts: recent RECENT_D days vs the prior PRIOR_D.

        Only events whose items field intersects LEGACY_VELOCITY_ITEMS are counted here.
        The LHB-R7 expansion added six new codes to MATERIAL_ITEMS; those codes must not
        silently shift the Divergence-Radar signal — velocity is pinned to the original
        six codes that the live theme_activity engine was calibrated against.
        """
        ev = events.copy()
        # Filter to LEGACY_VELOCITY_ITEMS: keep rows where at least one code in the
        # comma-joined items string is a member of the original six-code set.
        def _intersects_legacy(items_str: str) -> bool:
            if not items_str:
                return False
            return bool({c.strip() for c in str(items_str).split(",")} & LEGACY_VELOCITY_ITEMS)

        ev = ev[ev["items"].fillna("").apply(_intersects_legacy)]
        ev["d"] = pd.to_datetime(ev["filing_date"], errors="coerce")
        ev = ev[ev["d"].notna()]
        t0 = ev["d"].max() if not ev.empty else pd.Timestamp(datetime.now(timezone.utc).replace(tzinfo=None))
        rec_lo = t0 - pd.Timedelta(days=RECENT_D)
        pri_lo = t0 - pd.Timedelta(days=RECENT_D + PRIOR_D)
        rows = []
        for bid, b in mem.items():
            members = {m.get("ticker") for m in b.get("members", []) if m.get("ticker") and not m.get("removed")}
            if not members:
                continue
            sub = ev[ev["ticker"].isin(members)]
            rec = sub[(sub["d"] > rec_lo) & (sub["d"] <= t0)]
            pri = sub[(sub["d"] > pri_lo) & (sub["d"] <= rec_lo)]
            if rec.empty and pri.empty:
                continue
            covered = sorted(rec["ticker"].unique())
            rows.append({"basket_id": bid, "recent_count": int(len(rec)), "prior_count": int(len(pri)),
                         "n_members": int(len(covered)), "covered": ",".join(covered)})
        return pd.DataFrame(rows).set_index("basket_id") if rows else pd.DataFrame()

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        mem = _membership()
        universe = _universe(mem)
        if not universe:
            raise ValueError("edgar_8k: no basket members to scan")
        cikmap = _cik_map(universe)
        if not cikmap:
            raise ValueError("edgar_8k: could not map any ticker -> CIK (company_tickers.json unavailable)")

        events, errors = [], 0
        for ticker, cik in cikmap.items():
            try:
                events.extend(self._pull_ticker(ticker, cik))
                time.sleep(PACE_S)
            except Exception as e:  # noqa: BLE001
                errors += 1
                if is_connection_error(e):
                    raise  # host down -> fail fast, don't grind 345x
                log.debug("edgar_8k %s (CIK %s) failed: %s", ticker, cik, e)
                continue

        if not events:
            raise ValueError(f"edgar_8k: no material 8-K rows returned (errors={errors})")
        df = pd.DataFrame(events)
        merged = self._merge_events(df)
        velocity = self._velocity(merged, mem)
        if not velocity.empty:
            velocity.to_parquet(self._velocity_path())
        log.info("edgar_8k: %d/%d tickers mapped, +%d events scanned, %d total, %d baskets, %d errors",
                 len(cikmap), len(universe), len(df), len(merged), len(velocity), errors)
        ingest = pd.DataFrame(
            {"new_scanned": [len(df)], "total_rows": [len(merged)], "baskets": [len(velocity)]},
            index=[pd.Timestamp(datetime.now(timezone.utc).date())],
        )
        return {"edgar_8k__ingest": ingest}


# ---------------------------------------------------------------------------
# W1c — contract-dollar magnitude extraction for Item 1.01 / 2.03 filings
# ---------------------------------------------------------------------------
# EDGAR Archives primary-doc URL: https://www.sec.gov/Archives/edgar/data/{cik}/{acc_nodash}/{doc}
# Fetching is bounded to filings <= 45 days old on the incremental path (see enrich_contract_amounts).

_ARCHIVES = "https://www.sec.gov/Archives/edgar/data"
_ENRICH_WINDOW_DAYS = 45   # only fetch primary doc for recent filings on incremental runs

# Dollar-amount regex: captures 'approximately $1.2 billion', '$450 million', '$3,200,000',
# '$12.5M', numbers with decimal/comma thousands separators.
# EVERY multiplier alternative is word-bounded (\b): without it '$5 mmBtu' reads as $5M,
# '$10 millionaire' as $10M, '$4 bnb tokens' as $4B — and since the parser keeps the
# LARGEST match, one spurious suffix hit would corrupt amount_usd → contract_dollar_z →
# a false pre_drift flag on the graded ledger. '$X mmBtu' is common in energy 1.01 filings.
_DOLLAR_RE = re.compile(
    r"\$\s*([\d,]+(?:\.\d+)?)\s*(billion\b|million\b|bn\b|mm\b|m\b)?",
    re.IGNORECASE,
)
# Counterparty: 'with <Company Name>, Inc.' / 'between ... and <Company Name>'
_COUNTERPARTY_RE = re.compile(
    r"(?:with|by|from|to|between\s+\S+\s+and)\s+([A-Z][A-Za-z0-9 ,\.&']{3,60}?)(?:\s*[,\.;]|LLC|Inc|Corp|Ltd|LP|plc|AG|SA\b)",
    re.IGNORECASE,
)


def _parse_dollar_amounts(text: str) -> tuple[float | None, bool]:
    """Extract the largest contract USD amount from filing text.

    Returns (amount_usd, extraction_ok).  extraction_ok=True iff at least one
    parseable $ figure was found; amount_usd is the largest such figure in USD.
    Many 8-K/Item-1.01 filings bury the $ in exhibits or omit it entirely — those
    return (None, False) and degrade to count-only.
    """
    best: float | None = None
    for m in _DOLLAR_RE.finditer(text):
        raw = m.group(1).replace(",", "")
        try:
            val = float(raw)
        except ValueError:
            continue
        suffix = (m.group(2) or "").lower()
        if suffix in ("billion", "bn"):
            val *= 1_000_000_000
        elif suffix in ("million", "mm", "m"):
            val *= 1_000_000
        # skip noise values under $10k (page numbers, percentages formatted as $0.XX)
        if val < 10_000:
            continue
        if best is None or val > best:
            best = val
    return best, best is not None


def _parse_counterparty(text: str) -> str | None:
    """Best-effort counterparty from filing text. None when unextractable."""
    m = _COUNTERPARTY_RE.search(text)
    if not m:
        return None
    cp = m.group(1).strip().rstrip(",. ")
    # ignore very long / very short matches (noise)
    if len(cp) < 3 or len(cp) > 80:
        return None
    return cp


def _fetch_primary_doc_text(cik: int, accession: str) -> str | None:
    """Fetch the primary HTML/htm document from EDGAR Archives for a filing.

    Strategy: fetch the filing index.json to find the primary document name,
    then fetch that document.  Paced to <=8 req/s (PACE_S already applied externally).
    Returns raw text (HTML/plain) or None on any failure.
    """
    acc_nodash = accession.replace("-", "")
    idx_url = f"{_ARCHIVES}/{int(cik)}/{acc_nodash}/index.json"
    try:
        r = requests.get(idx_url, headers={"User-Agent": _SEC_UA}, timeout=20)
        if r.status_code != 200:
            return None
        idx = r.json()
    except Exception:  # noqa: BLE001
        return None

    items = ((idx.get("directory") or {}).get("item") or [])
    # Prefer the primary document (type field), then any htm/html file
    primary = None
    for it in items:
        if str(it.get("type", "")).strip().upper() in ("8-K", "8-K/A"):
            primary = it.get("name")
            break
    if not primary:
        for it in items:
            nm = str(it.get("name", "")).lower()
            if nm.endswith(".htm") or nm.endswith(".html"):
                primary = it["name"]
                break
    if not primary:
        return None

    doc_url = f"{_ARCHIVES}/{int(cik)}/{acc_nodash}/{primary}"
    try:
        r2 = requests.get(doc_url, headers={"User-Agent": _SEC_UA}, timeout=30)
        if r2.status_code != 200:
            return None
        return r2.text
    except Exception:  # noqa: BLE001
        return None


def enrich_contract_amounts(
    events: pd.DataFrame,
    incremental: bool = True,
    pace_s: float = PACE_S,
) -> pd.DataFrame:
    """Add amount_usd, counterparty, extraction_ok columns to material_8k_events.

    For rows with items containing '1.01' or '2.03', fetch the primary filing doc
    and regex-extract the contract dollar amount + counterparty.

    Args:
        events:      The full material_8k_events DataFrame (must have cik/accession/
                     filing_date/items columns).
        incremental: When True, only process filings <= _ENRICH_WINDOW_DAYS old AND
                     not yet enriched (extraction_ok column absent or NaN).
                     When False (backfill), process all 1.01/2.03 rows missing enrichment.
        pace_s:      Seconds to sleep between EDGAR Archives requests.

    Returns:
        Updated DataFrame with amount_usd (float|None), counterparty (str|None),
        extraction_ok (bool) columns.  Rows not in scope are returned unchanged.
    """
    df = events.copy()
    # Ensure enrichment columns exist
    for col, default in [("amount_usd", None), ("counterparty", None), ("extraction_ok", None)]:
        if col not in df.columns:
            df[col] = default

    # Target: only 1.01 / 2.03 rows
    mask_items = df["items"].str.contains(r"1\.01|2\.03", na=False)

    if incremental:
        cutoff = pd.Timestamp.now(tz="UTC").normalize() - pd.Timedelta(days=_ENRICH_WINDOW_DAYS)
        dates = pd.to_datetime(df["filing_date"], errors="coerce", utc=True)
        mask_recent = dates >= cutoff
        mask_unenriched = df["extraction_ok"].isna()
        target_mask = mask_items & mask_recent & mask_unenriched
    else:
        mask_unenriched = df["extraction_ok"].isna()
        target_mask = mask_items & mask_unenriched

    targets = df[target_mask]
    log.info("edgar_8k enrich: %d rows to process (incremental=%s)", len(targets), incremental)

    for idx_pos, row in targets.iterrows():
        cik = row.get("cik")
        acc = row.get("accession")
        if not cik or not acc:
            df.at[idx_pos, "extraction_ok"] = False   # permanently unenrichable — no ids
            continue
        try:
            text = _fetch_primary_doc_text(int(cik), str(acc))
            time.sleep(pace_s)
        except Exception as e:  # noqa: BLE001
            # TRANSIENT fetch failure (network/503/timeout): leave extraction_ok as NaN so
            # the incremental mask retries next run — False is reserved for filings we
            # actually READ and found no parseable $ in (a real coverage fact the ledger
            # grades on; a sticky False here would silently shrink coverage forever).
            log.debug("edgar_8k enrich fetch failed (retry-eligible) %s %s: %s",
                      row.get("ticker"), acc, e)
            continue

        if not text:
            continue   # fetch returned nothing — also retry-eligible, not a coverage fact

        amount, ok = _parse_dollar_amounts(text)
        counterparty = _parse_counterparty(text) if ok else None
        df.at[idx_pos, "amount_usd"] = amount
        df.at[idx_pos, "counterparty"] = counterparty
        df.at[idx_pos, "extraction_ok"] = ok

    return df


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    Edgar8KAdapter().fetch()
