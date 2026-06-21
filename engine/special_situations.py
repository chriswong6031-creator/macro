"""Special Situations classifier engine (Phase-1 — display-only leaf).

Turns the raw EDGAR event rows collected by `collectors.special_situations` into
classified, floored, cross-border-tagged situations for the Special Situations
desk. DISPLAY-ONLY: `SCORED = False`, imports nothing from the scoring path
(`conditions`/`regime`/`run`), and the snapshot is flagged `is_context_only`.

Classification is deterministic, distilled from the reverse-engineered taxonomy
(research/SPECIAL_SITUATIONS_RECON_FINDINGS.md §D2/§B1):
- Structured forms (SC 13D, SC TO, SC 13E3, merger proxies, Form 25/15/10) map
  straight to a mature category — high precision, no document text needed.
- Decisive 8-K items (1.02/1.03/3.01/5.02) map directly.
- Ambiguous 8-K items (1.01/2.01/8.01), 6-K and 424B5 need the filing TEXT to
  disambiguate (Acquisition vs Divestiture vs Spin-Off vs Strategic Review vs a
  plain shelf raise). Those are returned status="defer" and handled by the text
  lane (P1.1b) — NOT guessed here, to keep the desk clean.
- Passive Schedule 13G is status="skip" (tracked only to spot a 13G→13D flip).

A cross-filing rule upgrades a merger proxy / third-party tender to Going-Private
when the same filer also filed an SC 13E-3 (affiliate take-private), per §B1.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

import pandas as pd

from lib import config

log = logging.getLogger(__name__)

SCORED = False
DISCLAIMER = ("Context only — an event-tracking display of public filings, not a "
             "signal, recommendation, or sizing input.")

# --- mature taxonomy categories (the ~16 live labels) -----------------------
ACQ, DIV, ACT, REV = "Acquisitions", "Divestitures", "Activist Campaigns", "Strategic Reviews"
TO, GP, CAP, SPIN = "Tender Offers", "Going-Private", "Capital Returns", "Spin-Offs"
RIGHTS, RESTR, LIQ, DELIST = "Rights Offerings", "Restructuring", "Liquidations", "Delistings"
ITEND, TERM, SPAC, MGMT = "Issuer Tenders", "Deal Terminations", "SPACs", "Management Changes"

# --- form_type -> (category, stage) for structured forms --------------------
STRUCTURED: dict[str, tuple[str, str]] = {
    "SC 13D": (ACT, "initiated"),
    "SC 13D/A": (ACT, "escalation"),
    "SC TO-T": (TO, "live"),
    "SC TO-T/A": (TO, "live"),
    "SC TO-I": (ITEND, "live"),
    "SC TO-I/A": (ITEND, "live"),
    "SC 14D9": (TO, "target-response"),
    "SC 14D9/A": (TO, "target-response"),
    "SC 13E3": (GP, "live"),
    "SC 13E3/A": (GP, "live"),
    "DEFM14A": (ACQ, "vote-scheduled"),
    "PREM14A": (ACQ, "announced"),
    "DEFC14A": (ACT, "proxy-fight"),
    "PREC14A": (ACT, "proxy-fight"),
    "25": (DELIST, "live"),
    "25-NSE": (DELIST, "live"),
    "15-12B": (DELIST, "completed"),
    "15-12G": (DELIST, "completed"),
    "10-12B": (SPIN, "registered"),
    "10-12B/A": (SPIN, "registered"),
    "S-4": (ACQ, "registered"),       # stock-deal/de-SPAC; SPAC split needs text (low conf)
    "S-4/A": (ACQ, "registered"),
}
# forms whose category genuinely needs the filing text to decide
DEFER_FORMS = {"6-K", "424B5"}
# passive — not a situation on its own (kept only to detect a later 13G->13D flip)
SKIP_FORMS = {"SC 13G", "SC 13G/A"}

# --- 8-K Item -> (category, stage); checked in this priority order ----------
DECISIVE_8K: dict[str, tuple[str, str]] = {
    "1.03": (RESTR, "filed"),         # bankruptcy / receivership (Liquidation split needs text)
    "3.01": (DELIST, "notice"),       # delisting / listing-rule failure
}
_8K_PRIORITY = ["1.03", "3.01"]
# Item 1.02 (termination of a material definitive agreement) fires for ANY contract
# termination (supply deal, lease, credit facility) — not just M&A — so it is text-
# classified (the Deal-Terminations keyword rule is deal-specific), not decisive.
DEFER_8K_ITEMS = {"1.01", "1.02", "2.01", "8.01"}   # Acq/Divest/Spin/Review/Cap-Return/Term -> text lane
# Item 5.02 (officer/director change) is NOT a situation on its own — the recon
# shows Management Changes is a tiny category (only when it co-occurs with an
# active campaign). Returned status="mgmt_maybe" and upgraded in build_situations
# only if the same filer has an active activist/review/restructuring situation.

GROUP = "special_situations"
_US_STATES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID", "IL",
    "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT",
    "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI",
    "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
    "DC", "PR", "VI", "GU", "AS", "MP",
}


# High-confidence non-operating-company filers — securitization shells, ETFs/funds,
# and exchanges/clearing entities. These file the same forms (Form 25, 8-K) but are
# never equity special situations, so they are dropped before the desk.
_NOISE_RE = re.compile(
    r"\b(ABS FUNDING|FUNDING LLC|FUNDING CORP|SECURITIZATION|STATUTORY TRUST|"
    r"MASTER TRUST|OWNER TRUST|GRANTOR TRUST|RECEIVABLES|ASSET[- ]BACKED|"
    r"ETF TRUST|INDEX FUND|ISHARES|GRANITESHARES|NYSE|NASDAQ|CBOE|BATS|ARCA)\b",
    re.I)


def _is_noise_filer(company: object) -> bool:
    return bool(company and _NOISE_RE.search(str(company)))


def _cfg() -> dict:
    return config.load().get("special_situations", {}) or {}


def _items_set(items: object) -> set[str]:
    if not items or (isinstance(items, float) and pd.isna(items)):
        return set()
    return {p.strip() for p in str(items).split("|") if p.strip()}


def classify(form_type: str, items: object = None) -> tuple[str | None, str | None, str]:
    """(category, stage, status). status ∈ {ok, defer, skip}.
    `ok` = classified; `defer` = needs filing text (P1.1b); `skip` = not a situation."""
    form_type = (form_type or "").strip()
    if form_type in SKIP_FORMS:
        return None, None, "skip"
    if form_type in STRUCTURED:
        cat, stage = STRUCTURED[form_type]
        return cat, stage, "ok"
    if form_type in DEFER_FORMS:
        return None, None, "defer"
    if form_type in {"8-K", "8-K/A"}:
        s = _items_set(items)
        for code in _8K_PRIORITY:
            if code in s:
                cat, stage = DECISIVE_8K[code]
                return cat, stage, "ok"
        if s & DEFER_8K_ITEMS:
            return None, None, "defer"          # Acq/Divest/Spin/Review/Cap-Return need text
        if "5.02" in s:
            return MGMT, "change", "mgmt_maybe"  # only a situation if filer is already active
        return None, None, "skip"
    return None, None, "skip"


# --- text lane (P1.1b): keyword classifier for the ambiguous 8-K/6-K filings ---
# Ordered (category, stage, [phrases]); first matching bucket wins. Divestiture-
# specific phrases are checked before Acquisition so "sell its X division" is not
# mislabeled as an acquisition. Distilled from the recon prose (§B1/§E).
_TEXT_RULES: list[tuple[str, str, tuple[str, ...]]] = [
    (TERM, "terminated", (
        "mutually agreed to terminate", "agreed to terminate the", "terminated the previously announced",
        "termination of the merger agreement", "termination of the agreement and plan",
        "merger agreement was terminated", "terminated the merger")),
    (REV, "initiated", (
        "strategic alternatives", "strategic review", "review of strategic",
        "explore strategic", "evaluating strategic", "range of strategic")),
    (SPIN, "announced", (
        "spin-off", "spinoff", "spin off of", "plan to separate", "separation into two",
        "intends to separate", "tax-free distribution", "as an independent public company")),
    (DIV, "announced", (
        "agreement to sell its", "definitive agreement to sell", "to divest", "divestiture of",
        "sale of its", "agreed to sell its", "sale of the business", "disposition of")),
    (ACQ, "announced", (
        "agreement and plan of merger", "definitive merger agreement", "merger agreement",
        "to be acquired by", "agreed to acquire", "definitive agreement to acquire",
        "will acquire", "agreement to acquire", "enter into a merger")),
    (CAP, "announced", (
        "share repurchase program", "stock repurchase program", "accelerated share repurchase",
        "special dividend", "special cash dividend", "increased its quarterly dividend",
        "new repurchase", "authorized the repurchase", "return of capital")),
    (RESTR, "announced", (
        "chapter 11", "restructuring support agreement", "out-of-court restructuring",
        "liability management", "forbearance agreement", "exchange offer for its")),
]


def classify_text(text: str | None) -> tuple[str | None, str | None]:
    """Keyword-classify an ambiguous filing body (8-K Ex-99.1 / 6-K) into a mature
    category. Returns (None, None) when no special-situations signal is present."""
    if not text:
        return None, None
    t = " ".join(str(text).lower().split())
    for cat, stage, phrases in _TEXT_RULES:
        if any(p in t for p in phrases):
            return cat, stage
    return None, None


def _is_cross_border(row: pd.Series) -> bool:
    """6-K filers are foreign private issuers by definition; otherwise infer from a
    non-US incorporation/business state code (EDGAR uses A0–Z9 for foreign)."""
    if str(row.get("form_type", "")).startswith("6-K"):
        return True
    toks: list[str] = []
    for col in ("inc_states", "biz_locations"):
        v = row.get(col)
        if v and not (isinstance(v, float) and pd.isna(v)):
            for part in str(v).split("|"):
                # biz_locations look like "Rye, NY"; inc_states like "DE" or a foreign code
                state = part.split(",")[-1].strip().upper()
                if state:
                    toks.append(state)
    if not toks:
        return False
    return any(t not in _US_STATES for t in toks)


def apply_floor(mc_musd: float | None, floor: float) -> bool | None:
    """True = passes (>= floor), False = below floor, None = market cap unknown
    (kept and flagged; broad/off-universe mc resolution is P1.2)."""
    if mc_musd is None or (isinstance(mc_musd, float) and pd.isna(mc_musd)):
        return None
    return float(mc_musd) >= float(floor)


# ---- enrichment (market cap for the floor) ---------------------------------

def _universe_caps() -> tuple[dict[int, str], dict[str, float]]:
    """(cik->ticker, ticker->market_cap_$M) for our in-universe names, from
    fundamentals shares x latest broad close. Off-universe names resolve to None."""
    import json
    cik_ticker: dict[int, str] = {}
    mc: dict[str, float] = {}
    # broad CIK->ticker map (all SEC filers with tickers, ~10k incl small caps & ADRs).
    # Read the on-disk cache only — the collector refreshes it with the email-bearing
    # UA (www.sec.gov 403s the plain UA); the engine stays a leaf (no network).
    try:
        ctp = config.data_dir() / "edgar" / "company_tickers.json"
        if ctp.exists():
            ct = json.loads(ctp.read_text())
            for e in ct.values():
                cs, tk = e.get("cik_str"), e.get("ticker")
                if cs is not None and tk:
                    cik_ticker[int(cs)] = tk
    except Exception as e:  # noqa: BLE001
        log.warning("special_situations company_tickers map failed: %s", e)
    try:
        f = pd.read_parquet(config.data_dir() / "edgar" / "fundamentals.parquet")
        # read the US-equity close caches directly (stay a leaf — don't import the
        # factor/scoring engines just to get a price row)
        frames = []
        for g in ("breadth", "midcap_breadth", "smallcap_breadth"):
            p = config.data_dir() / g / "_closes_cache.parquet"
            if p.exists():
                frames.append(pd.read_parquet(p))
        closes = pd.concat(frames, axis=1, sort=False) if frames else pd.DataFrame()
        if not closes.empty:
            closes = closes.loc[:, ~closes.columns.duplicated()].sort_index()
        last = closes.iloc[-1] if not closes.empty else pd.Series(dtype=float)
        for tkr, r in f.iterrows():
            cik = r.get("cik")
            if pd.notna(cik):
                cik_ticker.setdefault(int(cik), tkr)   # broad map wins; fill gaps
            sh, px = r.get("shares"), last.get(tkr)
            if pd.notna(sh) and px is not None and pd.notna(px) and sh > 0:
                mc[tkr] = float(sh) * float(px) / 1e6
    except Exception as e:  # noqa: BLE001 — enrichment is best-effort
        log.warning("special_situations mc resolution failed: %s", e)
    return cik_ticker, mc


def build_situations() -> pd.DataFrame:
    """Classify + enrich + floor every stored event. Returns the full frame
    (all rows, with category/stage/status/ticker/mc/floor_pass/cross_border)."""
    p = config.data_dir() / GROUP / "events.parquet"
    if not p.exists():
        return pd.DataFrame()
    df = pd.read_parquet(p)
    if df.empty:
        return df

    cats, stages, status = [], [], []
    for _, row in df.iterrows():
        c, s, st = classify(row.get("form_type"), row.get("items"))
        cats.append(c); stages.append(s); status.append(st)
    df = df.assign(category=cats, stage=stages, status=status)

    # text lane (P1.1b): deferred filings that the enrichment step has classified
    # from their document text get promoted to a real situation.
    if "text_category" in df.columns:
        promote = (df.status == "defer") & df.text_category.notna() & (df.text_category != "")
        df.loc[promote, "category"] = df.loc[promote, "text_category"]
        df.loc[promote, "stage"] = df.loc[promote, "text_stage"] if "text_stage" in df.columns else "announced"
        df.loc[promote, "status"] = "ok"

    # cross-filing Going-Private upgrade: any CIK with an SC 13E-3 -> its merger
    # proxy / third-party tender is an affiliate take-private (§B1).
    gp_ciks = set(df.loc[df.form_type.str.startswith("SC 13E3"), "cik"].astype(str))
    upg = df.cik.astype(str).isin(gp_ciks) & df.category.isin([ACQ, TO])
    df.loc[upg, ["category", "stage"]] = [GP, "live"]

    # 5.02 (mgmt_maybe) becomes a real Management Changes situation ONLY if the
    # same filer already has an active activist/review/restructuring/deal situation;
    # otherwise a routine officer change is not a special situation -> skip.
    active_ciks = set(df.loc[(df.status == "ok") &
                             df.category.isin([ACT, REV, RESTR, GP, TO]), "cik"].astype(str))
    mm = df.status == "mgmt_maybe"
    df.loc[mm & df.cik.astype(str).isin(active_ciks), "status"] = "ok"
    drop_mm = mm & ~df.cik.astype(str).isin(active_ciks)
    df.loc[drop_mm, ["status", "category", "stage"]] = ["skip", None, None]

    # SPAC reclassification: a de-SPAC S-4 / merger proxy / 8-K from a blank-check
    # shell is a SPAC combination, not a plain acquisition (benchmark gap §P1.5).
    spac_name = df.company.str.contains(r"ACQUISITION CORP|BLANK CHECK|\bSPAC\b",
                                        case=False, na=False, regex=True)
    spac = spac_name & (df.status == "ok") & df.category.isin([ACQ, SPIN])
    df.loc[spac, ["category", "stage"]] = [SPAC, "de-SPAC"]

    # collapse multi-security-class delistings: one filer files separate Form 25 for
    # common + warrants + units + rights (esp. de-SPACs) -> one event per filer/day.
    dl = df[(df.status == "ok") & (df.category == DELIST)]
    if not dl.empty:
        dup_idx = dl[dl.duplicated(subset=["cik", "date_filed"], keep="first")].index
        df.loc[dup_idx, "status"] = "skip"

    # drop high-confidence non-operating-company filers (ABS/ETF/exchange shells)
    noise = df.company.apply(_is_noise_filer)
    df.loc[noise, ["status", "category", "stage"]] = ["skip", None, None]

    df["cross_border"] = df.apply(_is_cross_border, axis=1)

    cik_ticker, mc = _universe_caps()
    df["ticker"] = df.cik.apply(lambda c: cik_ticker.get(int(c)) if str(c).isdigit() else None)
    df["mc_musd"] = df.ticker.apply(lambda t: mc.get(t))
    floor = float(_cfg().get("market_cap_floor_musd", 100))
    df["floor_pass"] = df.mc_musd.apply(lambda m: apply_floor(m, floor))
    return df


def snapshot() -> dict:
    """Display payload for the desk: classified situations passing the floor,
    grouped by category, plus honest coverage counts. SCORED=False / context-only."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    df = build_situations()
    if df.empty:
        return {"scored": SCORED, "is_context_only": True, "disclaimer": DISCLAIMER,
                "built": now, "situations": [], "counts": {}, "coverage": {}}

    ok = df[df.status == "ok"].copy()
    # desk view: classified AND not below the floor (unknown mc kept, flagged)
    desk = ok[ok.floor_pass != False]  # noqa: E712 — keep True and None, drop False

    by_cat = desk.category.value_counts().to_dict()
    coverage = {
        "events_total": int(len(df)),
        "classified": int((df.status == "ok").sum()),
        "deferred_to_text_lane": int((df.status == "defer").sum()),
        "skipped": int((df.status == "skip").sum()),
        "below_floor_dropped": int((ok.floor_pass == False).sum()),  # noqa: E712
        "mc_unknown_kept": int(ok.floor_pass.isna().sum()),
        "cross_border": int(desk.cross_border.sum()),
        "floor_musd": float(_cfg().get("market_cap_floor_musd", 100)),
    }
    keep_cols = ["id", "ticker", "company", "category", "stage", "form_type",
                 "cross_border", "mc_musd", "date_filed", "source_url"]
    keep_cols = [c for c in keep_cols if c in desk.columns]
    sits = (desk.sort_values("date_filed", ascending=False)[keep_cols]
            .to_dict("records"))
    return {
        "scored": SCORED, "is_context_only": True, "disclaimer": DISCLAIMER,
        "built": now, "counts": by_cat, "coverage": coverage, "situations": sits,
    }


def _norm_ticker(t: object) -> str | None:
    """Match key across lanes: upper-case, strip the exchange suffix (ARX.TO->ARX)."""
    if not t or (isinstance(t, float) and pd.isna(t)):
        return None
    return str(t).upper().split(".")[0].strip() or None


def _digest_rows(latest_issue_only: bool = True) -> list[dict]:
    """Digest situations (with their ready-made summaries) as situation dicts. The
    site is private/internal, so the curated summaries are used directly."""
    p = config.data_dir() / GROUP / "digest_db.parquet"
    if not p.exists():
        return []
    d = pd.read_parquet(p)
    if d.empty:
        return []
    if latest_issue_only:
        d = d[d.issue == d.issue.max()]
    rows = []
    for _, r in d.iterrows():
        rows.append({
            "id": f"digest-{r.id}", "ticker": r.get("ticker"), "company": r.get("company"),
            "category": r.get("category"), "stage": "",
            "form_type": f"Digest #{int(r.issue)}" if pd.notna(r.get("issue")) else "Digest",
            "cross_border": (r.get("country") != "US"),
            "mc_musd": r.get("market_cap_musd"), "date_filed": r.get("issue_date"),
            "source_url": r.get("source_url"), "summary": r.get("summary"),
            "business_desc": r.get("business_desc"), "country": r.get("country"),
            "source_lane": "digest", "live": False,
        })
    return rows


def desk_payload(latest_issue_only: bool = True) -> dict:
    """Merged desk: latest-issue digest situations (with summaries) + live EDGAR,
    deduped by (ticker, category). EDGAR-confirmed digest rows get live=True and the
    fresh filing link; EDGAR-only situations (ahead of the next digest) are included.
    $100M floor applied across both lanes. SCORED=False / context-only."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    floor = float(_cfg().get("market_cap_floor_musd", 100))

    edf = build_situations()
    elive = edf[edf.status == "ok"] if not edf.empty else edf
    # the desk is a CURRENT-events view: only show EDGAR filings from the last ~14
    # days (the full Feb–Jun history lives in events.parquet for backtest/benchmark).
    if elive is not None and not elive.empty and "date_filed" in elive.columns:
        maxd = elive.date_filed.dropna().max()
        if maxd:
            cutoff = (pd.Timestamp(maxd) - pd.Timedelta(days=14)).strftime("%Y-%m-%d")
            elive = elive[elive.date_filed >= cutoff]
    edgar_tickers = ({_norm_ticker(t) for t in elive.ticker.dropna()} - {None}
                     if not (elive is None or elive.empty) else set())

    merged: dict[tuple, dict] = {}
    for r in _digest_rows(latest_issue_only):
        nt = _norm_ticker(r["ticker"])
        r["live"] = nt in edgar_tickers                       # our pipeline independently flagged this name
        merged[(nt, r["category"])] = r

    if not (elive is None or elive.empty):
        for _, r in elive.iterrows():
            k = (_norm_ticker(r.get("ticker")), r.get("category"))
            if k in merged and k[0] is not None:
                merged[k]["live"] = True                       # same situation, confirmed
                merged[k]["edgar_url"] = r.get("source_url")
            else:
                merged[k] = {
                    "id": r.get("id"), "ticker": r.get("ticker"), "company": r.get("company"),
                    "category": r.get("category"), "stage": r.get("stage") or "",
                    "form_type": r.get("form_type"), "cross_border": bool(r.get("cross_border")),
                    "mc_musd": r.get("mc_musd"), "date_filed": r.get("date_filed"),
                    "source_url": r.get("source_url"),
                    "summary": (r.get("summary") if pd.notna(r.get("summary")) else None),
                    "business_desc": None, "country": "US",
                    "source_lane": "edgar", "live": True,
                }

    sits = [s for s in merged.values()
            if apply_floor(s.get("mc_musd"), floor) is not False]   # keep True + unknown
    sits.sort(key=lambda s: (s.get("date_filed") or "", s.get("category") or ""), reverse=True)

    counts: dict[str, int] = {}
    for s in sits:
        counts[s["category"]] = counts.get(s["category"], 0) + 1
    coverage = {
        "shown": len(sits),
        "digest_situations": sum(1 for s in sits if s["source_lane"] == "digest"),
        "edgar_confirmed": sum(1 for s in sits if s["source_lane"] == "digest" and s.get("live")),
        "edgar_only": sum(1 for s in sits if s["source_lane"] == "edgar"),
        "cross_border": sum(1 for s in sits if s.get("cross_border")),
        "with_summary": sum(1 for s in sits if s.get("summary")),
        "floor_musd": floor,
    }
    return {"scored": SCORED, "is_context_only": True, "disclaimer": DISCLAIMER,
            "built": now, "counts": counts, "coverage": coverage, "situations": sits}


def mastermind_emit() -> dict:
    """Per-ticker special-situations context for the trading brain + cross-surface
    chips. Keyed by normalized ticker, most-recent situation wins. Pulls the FULL
    digest history (curated, with summaries) + our live EDGAR detections. Strictly
    CONTEXT — `is_context_only`, never a size/score."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    by_ticker: dict[str, dict] = {}

    def consider(tkr, rec):
        k = _norm_ticker(tkr)
        if not k:
            return
        prev = by_ticker.get(k)
        if prev is None or (rec.get("date") or "") > (prev.get("date") or ""):
            by_ticker[k] = rec

    p = config.data_dir() / GROUP / "digest_db.parquet"
    if p.exists():
        d = pd.read_parquet(p)
        for _, r in d.iterrows():
            summ = r.get("summary")
            consider(r.get("ticker"), {
                "ticker": r.get("ticker"), "company": r.get("company"),
                "category": r.get("category"), "stage": "",
                "date": r.get("issue_date"), "country": r.get("country"),
                "cross_border": bool(r.get("country") != "US"),
                "source": "digest", "source_url": r.get("source_url"),
                "brief": (str(summ)[:300] if summ and pd.notna(summ) else r.get("headline")),
                "mc_musd": (float(r["market_cap_musd"]) if pd.notna(r.get("market_cap_musd")) else None),
            })

    edf = build_situations()
    if not edf.empty:
        for _, r in edf[edf.status == "ok"].iterrows():
            consider(r.get("ticker"), {
                "ticker": r.get("ticker"), "company": r.get("company"),
                "category": r.get("category"), "stage": r.get("stage") or "",
                "date": r.get("date_filed"), "country": "US",
                "cross_border": bool(r.get("cross_border")),
                "source": "edgar", "source_url": r.get("source_url"),
                "brief": (r.get("summary") if pd.notna(r.get("summary")) else r.get("hk")),
                "mc_musd": (float(r["mc_musd"]) if pd.notna(r.get("mc_musd")) else None),
            })

    return {
        "schema": "special_situations.v1", "generated_at": now,
        "is_context_only": True, "disclaimer": DISCLAIMER,
        "n": len(by_ticker), "by_ticker": by_ticker,
    }


def main() -> int:
    import json
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    snap = snapshot()
    print(json.dumps({"counts": snap["counts"], "coverage": snap["coverage"]}, indent=2))
    print(f"\ntop situations ({len(snap['situations'])}):")
    for s in snap["situations"][:15]:
        xb = " [cross-border]" if s.get("cross_border") else ""
        mc = f"${s['mc_musd']:.0f}M" if s.get("mc_musd") else "mc?"
        print(f"  {s['category']:18} {s.get('ticker') or '—':8} {s['company'][:34]:34} {s['stage']:16} {mc}{xb}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
