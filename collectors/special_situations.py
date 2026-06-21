"""Special Situations event collector (Phase-1, Lane A — EDGAR).

Discovers event-driven corporate special situations from the SEC EDGAR
dissemination feed and stores them as an append-only event table. This is the
deterministic ingestion layer for the display-only Special Situations desk
(see research/SPECIAL_SITUATIONS_BUILD_SPEC.md); classification, market-cap
floor, enrichment and the LLM summary are downstream (engine/special_situations).

Why a hybrid discovery (daily-index + EFTS):
- The EDGAR **daily index** (Archives/edgar/daily-index/.../form.YYYYMMDD.idx) is
  the authoritative dissemination feed — it lists EVERY filing for a day by form
  type, including Schedule 13D/13G (the highest-value activist signal).
- **EFTS full-text search** (efts.sec.gov) returns 8-K `items`, business location
  and SIC in one paginated JSON call — but it does NOT index Schedule 13D/13G
  (verified: 0 SC 13D hits over a full month while the daily index had them).
So we discover with the daily index (complete) and join EFTS *only* to attach
8-K items + geography by accession number, which lets us drop the ~hundreds of
non-special-situations 8-Ks per day without downloading any filing document.

Honesty: this captures US-registered filers (which inherently includes
cross-listed ADRs / foreign private issuers via 6-K, i.e. US-anchored
cross-border). Pure foreign-domestic filings (EDINET/TDnet/RNS) are out of scope
for Phase 1. Append-only with keep-first first_seen — the first market-observable
moment a situation hit EDGAR is never overwritten on later amendments.
"""
from __future__ import annotations

import json
import logging
import re
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from lib import config

log = logging.getLogger(__name__)

# Structured event forms — classified directly from the form type (low volume).
STRUCTURED_FORMS = {
    "SC 13D", "SC 13D/A",
    "SC 13G", "SC 13G/A",                 # passive; tracked to detect 13G->13D conversion
    "SC TO-T", "SC TO-T/A",
    "SC TO-I", "SC TO-I/A",
    "SC 14D9", "SC 14D9/A",
    "SC 13E3", "SC 13E3/A",
    "DEFM14A", "PREM14A",
    "DEFC14A", "PREC14A",
    "25", "25-NSE",                       # delisting
    "15-12B", "15-12G",                   # deregistration
    "10-12B", "10-12B/A",                 # Form 10 (spin-off registration)
    "S-4", "S-4/A",                       # merger / de-SPAC stock registration
    "424B5",                              # rights-offering context
    "6-K",                                # foreign private issuer current report (cross-border)
}
EIGHT_K_FORMS = {"8-K", "8-K/A"}
GROUP = "special_situations"
_DAILY_IDX = "https://www.sec.gov/Archives/edgar/daily-index/{yr}/QTR{q}/form.{ds}.idx"
_EFTS = "https://efts.sec.gov/LATEST/search-index"


def _cfg() -> dict:
    return config.load().get("special_situations", {}) or {}


def _headers() -> dict:
    ua = _cfg().get("user_agent") or config.load()["smart_money"]["user_agent"]
    return {"User-Agent": ua, "Accept-Encoding": "gzip, deflate"}


def _eight_k_items() -> set[str]:
    return set(_cfg().get("eight_k_items", ["1.01", "1.02", "1.03", "2.01", "3.01", "5.02", "8.01"]))


def _get(url: str, *, as_json: bool, retries: int | None = None):
    """GET with SEC fair-access pacing + retry/backoff. Returns text|json|None.
    404 (e.g. weekend/holiday daily index) short-circuits to None."""
    import requests
    retries = retries if retries is not None else _cfg().get("retries", 3)
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=_headers(), timeout=30)
            if r.status_code == 404:
                return None
            r.raise_for_status()
            time.sleep(0.12)              # <10 req/s SEC fair-access ceiling
            return r.json() if as_json else r.text
        except Exception as e:  # noqa: BLE001 — tolerate per-request failure
            if attempt == retries - 1:
                log.warning("special_situations GET failed %s: %s", url[:90], e)
                return None
            time.sleep(1.5 * (attempt + 1))
    return None


# ---------------------------------------------------------------- daily index

def _qtr(d: date) -> int:
    return (d.month - 1) // 3 + 1


def _parse_idx(text: str) -> list[dict]:
    """Parse a form.YYYYMMDD.idx into target-form rows.
    Fixed-width: Form Type | Company | CIK | Date Filed | File Name."""
    out: list[dict] = []
    lines = text.splitlines()
    start = 0
    for i, ln in enumerate(lines):
        if set(ln.strip()) == {"-"}:
            start = i + 1
            break
    want = STRUCTURED_FORMS | EIGHT_K_FORMS
    for ln in lines[start:]:
        if not ln.strip():
            continue
        parts = re.split(r"\s{2,}", ln.strip())
        if len(parts) < 5:
            continue
        form = parts[0].strip()
        if form not in want:
            continue
        filename = parts[-1].strip()           # edgar/data/{cik}/{accession}.txt
        date_filed = parts[-2].strip()
        cik = parts[-3].strip()
        company = " ".join(parts[1:-3]).strip()
        accession = Path(filename).stem        # 0001193125-26-275494
        acc_nodash = accession.replace("-", "")
        out.append({
            "id": accession,
            "form_type": form,
            "company": company,
            "cik": cik,
            "date_filed": f"{date_filed[:4]}-{date_filed[4:6]}-{date_filed[6:8]}",
            "accession": accession,
            "source_url": f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc_nodash}/{accession}-index.htm",
            "source_lane": "edgar",
        })
    return out


def _fetch_idx(d: date) -> list[dict]:
    ds = d.strftime("%Y%m%d")
    url = _DAILY_IDX.format(yr=d.year, q=_qtr(d), ds=ds)
    text = _get(url, as_json=False)
    if not text:
        return []
    return _parse_idx(text)


# ---------------------------------------------------------------- EFTS (8-K enrichment)

def _efts_8k_map(d: date) -> dict[str, dict]:
    """{accession: {items, biz_locations, inc_states, sics}} for all 8-Ks on day d.
    Used only to attach items + geography to daily-index 8-K rows."""
    ds = d.strftime("%Y-%m-%d")
    out: dict[str, dict] = {}
    frm = 0
    while True:
        url = f"{_EFTS}?q=&forms=8-K&startdt={ds}&enddt={ds}&from={frm}"
        data = _get(url, as_json=True)
        hits = (data or {}).get("hits", {}).get("hits", [])
        if not hits:
            break
        for h in hits:
            s = h.get("_source", {})
            adsh = s.get("adsh")
            if not adsh:
                continue
            out[adsh] = {
                "items": s.get("items") or [],
                "biz_locations": s.get("biz_locations") or [],
                "inc_states": s.get("inc_states") or [],
                "sics": s.get("sics") or [],
            }
        frm += len(hits)
        total = (data or {}).get("hits", {}).get("total", {}).get("value", 0)
        if frm >= total:
            break
        time.sleep(0.15)
    return out


def _enrich_eight_ks(rows: list[dict], efts: dict[str, dict]) -> list[dict]:
    """Keep only 8-Ks whose items intersect the special-situations set; attach
    items + geography. Structured forms pass through untouched. If EFTS returned
    nothing for the day (outage), keep 8-Ks with items_unknown=True (don't lose a day)."""
    keep_items = _eight_k_items()
    efts_ok = bool(efts)
    out: list[dict] = []
    dropped = 0
    for r in rows:
        if r["form_type"] not in EIGHT_K_FORMS:
            out.append(r)
            continue
        meta = efts.get(r["accession"])
        if meta is None:
            if efts_ok:
                dropped += 1            # EFTS had the day but not this 8-K's items -> not special-sits
                continue
            r = {**r, "items": "", "items_unknown": True}
            out.append(r)
            continue
        items = [str(it) for it in meta["items"]]
        if not (set(items) & keep_items):
            dropped += 1
            continue
        r = {**r,
             "items": "|".join(items),
             "biz_locations": "|".join(meta["biz_locations"]),
             "inc_states": "|".join(meta["inc_states"]),
             "sics": "|".join(str(s) for s in meta["sics"])}
        out.append(r)
    if dropped:
        log.info("special_situations: dropped %d non-special-situations 8-Ks", dropped)
    return out


# ---------------------------------------------------------------- storage

def _events_path() -> Path:
    p = config.data_dir() / GROUP / "events.parquet"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _meta_path() -> Path:
    return config.data_dir() / GROUP / "_meta.json"


def _read_events() -> pd.DataFrame | None:
    p = _events_path()
    return pd.read_parquet(p) if p.exists() else None


def _save_events(new_rows: list[dict]) -> pd.DataFrame:
    """Append-only event store keyed by accession id, keep-FIRST so first_seen and
    the earliest source are never overwritten by later amendments/re-discovery."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    new = pd.DataFrame(new_rows)
    if not new.empty:
        new["first_seen"] = now
        new["built"] = now
    old = _read_events()
    if old is not None and not old.empty:
        merged = pd.concat([old, new], ignore_index=True)
    else:
        merged = new
    if merged.empty:
        return merged
    merged = merged.drop_duplicates(subset=["id"], keep="first").reset_index(drop=True)
    merged.to_parquet(_events_path(), index=False)
    return merged


def _load_meta() -> dict:
    p = _meta_path()
    return json.loads(p.read_text()) if p.exists() else {}


def _save_meta(meta: dict) -> None:
    _meta_path().write_text(json.dumps(meta, indent=2, default=str))


# ---------------------------------------------------------------- driver

def _dates_to_sweep(today: date) -> list[date]:
    """From the watermark (exclusive) up to today; first run backfills N days."""
    meta = _load_meta()
    last = meta.get("last_index_date")
    if last:
        start = datetime.strptime(last, "%Y-%m-%d").date() + timedelta(days=1)
    else:
        start = today - timedelta(days=int(_cfg().get("backfill_days", 7)) - 1)
    days = []
    d = start
    while d <= today:
        if d.weekday() < 5:                  # filings only on weekdays; skip Sat/Sun
            days.append(d)
        d += timedelta(days=1)
    return days


def backfill_range(start: date, end: date) -> pd.DataFrame:
    """Sweep an explicit date range (ignores the watermark) and append — used to
    widen historical coverage (e.g. align to a digest issue window, or seed a
    longer backtest). Append-only keep-first, so it's safe to overlap existing dates."""
    if not _cfg().get("enabled", False):
        return _read_events() if _read_events() is not None else pd.DataFrame()
    all_new: list[dict] = []
    d = start
    while d <= end:
        if d.weekday() < 5:
            rows = _fetch_idx(d)
            if rows:
                efts = _efts_8k_map(d) if any(r["form_type"] in EIGHT_K_FORMS for r in rows) else {}
                rows = _enrich_eight_ks(rows, efts)
                for r in rows:
                    r["index_date"] = d.strftime("%Y-%m-%d")
                all_new.extend(rows)
                log.info("special_situations backfill %s: %d target filings", d, len(rows))
        d += timedelta(days=1)
    return _save_events(all_new)


def _ensure_company_tickers(max_age_days: int = 30) -> None:
    """Cache the broad CIK->ticker map (data/edgar/company_tickers.json) using the
    email-bearing UA — www.sec.gov 403s the plain edgar UA. Refreshed monthly. The
    engine reads this cache (no network) to resolve tickers for off-universe filers."""
    import json
    from datetime import datetime as _dt
    p = config.data_dir() / "edgar" / "company_tickers.json"
    if p.exists():
        age = (_dt.now().timestamp() - p.stat().st_mtime) / 86400
        if age < max_age_days:
            return
    data = _get("https://www.sec.gov/files/company_tickers.json", as_json=True)
    if data:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data))
        log.info("special_situations: cached company_tickers.json (%d filers)", len(data))


def fetch_events(today: date | None = None) -> pd.DataFrame:
    """Sweep the daily index (+EFTS 8-K join) for new dates and append to the store."""
    if not _cfg().get("enabled", False):
        log.info("special_situations collector disabled in config")
        return _read_events() if _read_events() is not None else pd.DataFrame()
    _ensure_company_tickers()
    today = today or datetime.now(timezone.utc).date()
    dates = _dates_to_sweep(today)
    all_new: list[dict] = []
    last_seen: date | None = None
    for d in dates:
        rows = _fetch_idx(d)
        if not rows:
            continue                          # 404 (holiday) or empty; don't advance watermark past a real gap
        has_8k = any(r["form_type"] in EIGHT_K_FORMS for r in rows)
        efts = _efts_8k_map(d) if has_8k else {}
        rows = _enrich_eight_ks(rows, efts)
        for r in rows:
            r["index_date"] = d.strftime("%Y-%m-%d")
        all_new.extend(rows)
        last_seen = d
        log.info("special_situations %s: %d target filings", d, len(rows))
    merged = _save_events(all_new)
    if last_seen:
        meta = _load_meta()
        meta.update({
            "last_index_date": last_seen.strftime("%Y-%m-%d"),
            "built": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "n_events": int(len(merged)),
            "n_new_this_run": int(len(all_new)),
        })
        _save_meta(meta)
    log.info("special_situations: +%d new rows, %d total", len(all_new), len(merged))
    return merged


# ---------------------------------------------------------------- text lane (P1.1b)

def _filing_text_url(cik: str, accession: str) -> str:
    return f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession}.txt"


def _strip_markup(html: str) -> str:
    html = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", html)
    html = re.sub(r"(?s)<[^>]+>", " ", html)
    html = re.sub(r"&#?\w+;", " ", html)
    return re.sub(r"\s+", " ", html).strip()


def _fetch_filing_text(cik: str, accession: str, max_chars: int = 40000) -> str | None:
    """Fetch + cache the stripped text of a filing's full submission (8-K body +
    Exhibit 99.1 sit near the top). Cached so daily rebuilds never re-fetch."""
    cache = config.data_dir() / GROUP / "doc_cache" / f"{accession}.txt"
    if cache.exists():
        return cache.read_text(errors="replace")
    raw = _get(_filing_text_url(cik, accession), as_json=False)
    if not raw:
        return None
    txt = _strip_markup(raw)[:max_chars]
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(txt)
    return txt


def enrich_text(limit: int | None = None,
                forms: tuple[str, ...] = ("8-K", "8-K/A", "6-K", "424B5")) -> pd.DataFrame:
    """Classify the ambiguous deferred filings from their document text and write
    `text_category`/`text_stage` back to the event store. Empty string = tried, no
    special-situations signal (won't be re-fetched); NaN = not yet attempted."""
    from engine import special_situations as sse
    df = _read_events()
    if df is None or df.empty:
        return df if df is not None else pd.DataFrame()
    if "text_category" not in df.columns:
        df["text_category"] = pd.NA
        df["text_stage"] = pd.NA

    cand = df[df.form_type.isin(forms) & df.text_category.isna()]
    keep = [sse.classify(r.form_type, r.get("items"))[2] == "defer" for _, r in cand.iterrows()]
    cand = cand[pd.Series(keep, index=cand.index)].sort_values("date_filed", ascending=False)
    if limit:
        cand = cand.head(limit)

    updates: dict[str, tuple[str, str]] = {}
    for _, r in cand.iterrows():
        txt = _fetch_filing_text(str(r.cik), str(r.accession))
        cat, stage = sse.classify_text(txt) if txt else (None, None)
        updates[r.id] = (cat or "", stage or "")
    if updates:
        df.loc[df.id.isin(updates), "text_category"] = df.loc[df.id.isin(updates), "id"].map(lambda i: updates[i][0])
        df.loc[df.id.isin(updates), "text_stage"] = df.loc[df.id.isin(updates), "id"].map(lambda i: updates[i][1])
        df.to_parquet(_events_path(), index=False)
    classified = sum(1 for v in updates.values() if v[0])
    log.info("special_situations text lane: %d filings read, %d classified", len(updates), classified)
    return df


# ---------------------------------------------------------------- LLM lanes (P1.3 summary + P1.1 verify)

# The summary half of the JSON contract (the house style; see recon §E). Both lanes
# share ONE call: the model returns a compact JSON object so we get the summary AND the
# verified classification / deal terms for the same token spend.
_SS_SUMMARY_RUBRIC = (
    "summary: ONE ~88-word analysis paragraph in this order — what was filed / who acted; "
    "exact terms (stake %, price/share, implied value, premium %, dates); board "
    "recommendation / advisor if named; mechanics & structural notes (collateral, overhang, "
    "ownership split, regulatory clock); a closing 'what to watch / risk-arb angle'. "
    "Neutral-analytical, declarative, no first person, no recommendation. If a non-US filing, "
    "map it to its US equivalent in-prose."
)
_SS_TERMS_RUBRIC = (
    'deal_terms: object with ONLY the fields explicitly stated in the filing, drawn from '
    '{price_per_share (number), currency (ISO code, default "USD"), '
    'consideration ("cash"|"stock"|"cash+stock"|"other"), premium_pct (number), '
    'expected_close ("YYYY-MM" or "YYYY-MM-DD"), break_fee_musd (number in $M)}; '
    "{} if the filing states none."
)
# Mature taxonomy the verifier may choose from (mirrors engine.special_situations); "None"
# means NOT a special situation (routine 8-K, plain shelf takedown, supply/lease/credit deal).
_LLM_CATEGORIES = (
    "Acquisitions, Divestitures, Activist Campaigns, Strategic Reviews, Tender Offers, "
    "Going-Private, Capital Returns, Spin-Offs, Rights Offerings, Restructuring, Liquidations, "
    "Delistings, Issuer Tenders, Deal Terminations, SPACs, Management Changes, Other, None"
)

SS_SUMMARY_SYSTEM = (
    "You write terse special-situations notes in the house style of an event-driven research "
    "desk. Given a corporate-event filing whose category is already known, return ONLY a "
    "compact JSON object (no markdown fence, no prose) with keys:\n"
    f"- {_SS_SUMMARY_RUBRIC}\n"
    f"- {_SS_TERMS_RUBRIC}"
)
SS_CLASSIFY_SYSTEM = (
    "You are an event-driven research analyst classifying an SEC filing into a special-"
    "situations category. Read the excerpt and return ONLY a compact JSON object (no markdown "
    "fence, no prose) with keys:\n"
    f"- category: EXACTLY one of [{_LLM_CATEGORIES}]. Use \"None\" if the filing is NOT a "
    "special situation (routine current report, ordinary shelf takedown, product/supply/lease/"
    "credit-facility contract). Be conservative — prefer \"None\" over a wrong category.\n"
    "- role: the registrant's role — one of [acquirer, target, seller, issuer, filer, none].\n"
    "- confidence: \"high\" | \"medium\" | \"low\".\n"
    f"- {_SS_SUMMARY_RUBRIC}\n"
    f"- {_SS_TERMS_RUBRIC}"
)


def _llm_ready(cfg: dict) -> bool:
    import os
    if not cfg.get("enabled") or not cfg.get("llm_brief"):
        return False
    if os.environ.get("DISABLE_SPECIAL_SITUATIONS_LLM"):
        return False
    return bool(config.secret(cfg.get("api_key_env", "DEEPSEEK_API_KEY")))


def _llm_client(cfg: dict):
    """(client, model) for the DeepSeek Anthropic-compatible endpoint. Isolated so tests
    can monkeypatch a fake client without a network/key."""
    import anthropic
    client = anthropic.Anthropic(base_url=cfg.get("llm_base_url"),
                                 api_key=config.secret(cfg.get("api_key_env", "DEEPSEEK_API_KEY")))
    return client, cfg.get("llm_model", "deepseek-chat")


def _parse_llm_json(out: str | None) -> dict:
    """Robustly pull the JSON object out of an LLM reply (tolerates a ```json fence or
    leading prose). Returns {} on any failure — the caller degrades, never breaks."""
    if not out:
        return {}
    s = str(out).strip()
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*|\s*```$", "", s, flags=re.I).strip()
    try:
        obj = json.loads(s)
        return obj if isinstance(obj, dict) else {}
    except Exception:  # noqa: BLE001
        m = re.search(r"\{.*\}", s, re.S)
        if m:
            try:
                obj = json.loads(m.group(0))
                return obj if isinstance(obj, dict) else {}
            except Exception:  # noqa: BLE001
                return {}
        return {}


def _llm_prompt(row: pd.Series, text: str | None, *, known_category: bool) -> str:
    cat = f"Event category: {row.get('category')} · " if known_category else ""
    head = (f"Company: {row.get('company')} ({row.get('ticker') or '—'})\n"
            f"{cat}form {row.get('form_type')} (items {row.get('items') or '—'}) · "
            f"filed {row.get('date_filed')}\nFiling source: {row.get('source_url')}\n\n")
    body = (text or "")[:6000]
    return head + "Filing text excerpt:\n" + body if body else head + "(no document text available)"


def _llm_call(client, model, system: str, prompt: str) -> dict:
    """One LLM call -> parsed JSON dict ({} on failure)."""
    try:
        resp = client.messages.create(model=model, max_tokens=420, system=system,
                                       messages=[{"role": "user", "content": prompt}])
        out = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text").strip()
    except Exception as e:  # noqa: BLE001 — degrade, never break the build
        log.warning("special_situations LLM call failed: %s", e)
        return {}
    return _parse_llm_json(out)


def _terms_json(obj: dict) -> str | None:
    t = obj.get("deal_terms")
    if isinstance(t, dict) and t:
        return json.dumps(t, default=str)
    return None


def enrich_summaries(limit: int | None = None) -> pd.DataFrame:
    """Generate the ~88-word house-style summary (+ any deal terms) for live EDGAR
    situations our deterministic classifier already accepts (status=ok) that lack one.
    Digest situations carry their own curated summary. Gated + cached per situation id,
    so daily rebuilds only pay for new situations. No-op without a key."""
    from engine import special_situations as sse
    cfg = _cfg()
    df = _read_events()
    if df is None or df.empty:
        return df if df is not None else pd.DataFrame()
    for col in ("summary", "llm_terms"):
        if col not in df.columns:
            df[col] = pd.NA
    if not _llm_ready(cfg):
        log.info("special_situations summary lane: gated off (no key / disabled)")
        return df

    cache_dir = config.data_dir() / GROUP / "digest_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    client, model = _llm_client(cfg)

    # only situations our classifier accepts and that have no summary yet
    need = []
    for _, r in df.iterrows():
        if pd.notna(r.get("summary")) and str(r.get("summary")).strip():
            continue
        if sse.classify(r.get("form_type"), r.get("items"))[2] != "ok":
            continue
        need.append(r)
    need = sorted(need, key=lambda r: r.get("date_filed") or "", reverse=True)
    if limit:
        need = need[:limit]

    summ: dict[str, str] = {}
    terms: dict[str, str] = {}
    for r in need:
        cpath = cache_dir / f"{r.id}.json"
        if cpath.exists():
            cached = json.loads(cpath.read_text())
        else:
            text = _fetch_filing_text(str(r.cik), str(r.accession))
            obj = _llm_call(client, model, SS_SUMMARY_SYSTEM, _llm_prompt(r, text, known_category=True))
            if not obj:
                continue
            cached = {"summary": str(obj.get("summary") or "").strip(), "terms": _terms_json(obj)}
            if not cached["summary"]:
                continue
            cpath.write_text(json.dumps(cached))
        if cached.get("summary"):
            summ[r.id] = cached["summary"]
        if cached.get("terms"):
            terms[r.id] = cached["terms"]
    if summ:
        df.loc[df.id.isin(summ), "summary"] = df.loc[df.id.isin(summ), "id"].map(summ)
    if terms:
        df.loc[df.id.isin(terms), "llm_terms"] = df.loc[df.id.isin(terms), "id"].map(terms)
    if summ or terms:
        df.to_parquet(_events_path(), index=False)
    log.info("special_situations summary lane: wrote %d summaries, %d term-sets", len(summ), len(terms))
    return df


def enrich_classify(limit: int | None = None) -> pd.DataFrame:
    """P1.1 — let the LLM VERIFY the category for the ambiguous filings the deterministic
    classifier deferred (8-K 1.01/1.02/2.01/8.01, 6-K, 424B5). One call returns the verified
    category + registrant role + confidence + summary + deal terms, converting the noisy
    keyword text-lane (~67% FP) into high-confidence classifications and killing false
    positives (category="None"). Gated + cached per id; no-op without a key."""
    from engine import special_situations as sse
    cfg = _cfg()
    df = _read_events()
    if df is None or df.empty:
        return df if df is not None else pd.DataFrame()
    for col in ("llm_category", "llm_role", "llm_confidence", "llm_terms", "summary"):
        if col not in df.columns:
            df[col] = pd.NA
    if not _llm_ready(cfg):
        log.info("special_situations classify lane: gated off (no key / disabled)")
        return df

    cache_dir = config.data_dir() / GROUP / "classify_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    client, model = _llm_client(cfg)

    # candidates: filings the deterministic classifier could not resolve (status=defer)
    # and which we have not already asked the LLM about.
    need = []
    for _, r in df.iterrows():
        if pd.notna(r.get("llm_category")) and str(r.get("llm_category")).strip():
            continue
        if sse.classify(r.get("form_type"), r.get("items"))[2] != "defer":
            continue
        need.append(r)
    need = sorted(need, key=lambda r: r.get("date_filed") or "", reverse=True)
    if limit:
        need = need[:limit]

    cat: dict[str, str] = {}
    role: dict[str, str] = {}
    conf: dict[str, str] = {}
    summ: dict[str, str] = {}
    terms: dict[str, str] = {}
    for r in need:
        cpath = cache_dir / f"{r.id}.json"
        if cpath.exists():
            obj = json.loads(cpath.read_text())
        else:
            text = _fetch_filing_text(str(r.cik), str(r.accession))
            obj = _llm_call(client, model, SS_CLASSIFY_SYSTEM, _llm_prompt(r, text, known_category=False))
            if not obj:
                continue
            obj = {"category": str(obj.get("category") or "").strip(),
                   "role": str(obj.get("role") or "").strip().lower(),
                   "confidence": str(obj.get("confidence") or "").strip().lower(),
                   "summary": str(obj.get("summary") or "").strip(),
                   "terms": _terms_json(obj)}
            cpath.write_text(json.dumps(obj))
        c = obj.get("category") or ""
        if not c:
            continue
        cat[r.id] = c                                  # "None" is a valid, FP-killing verdict
        if obj.get("role"):
            role[r.id] = obj["role"]
        if obj.get("confidence"):
            conf[r.id] = obj["confidence"]
        if obj.get("summary"):
            summ[r.id] = obj["summary"]
        if obj.get("terms"):
            terms[r.id] = obj["terms"]
    for col, upd in (("llm_category", cat), ("llm_role", role), ("llm_confidence", conf),
                     ("summary", summ), ("llm_terms", terms)):
        if upd:
            df.loc[df.id.isin(upd), col] = df.loc[df.id.isin(upd), "id"].map(upd)
    if cat:
        df.to_parquet(_events_path(), index=False)
    promoted = sum(1 for v in cat.values() if v and v != "None")
    log.info("special_situations classify lane: %d verified (%d real, %d cleared as None)",
             len(cat), promoted, len(cat) - promoted)
    return df


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    df = fetch_events()
    if df is None or df.empty:
        print("special_situations: no events stored")
        return 0
    print(f"\nstored {len(df)} total events")
    print("by form_type:")
    print(df["form_type"].value_counts().to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
