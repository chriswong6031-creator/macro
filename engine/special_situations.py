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

import hashlib
import json
import logging
import re
from datetime import date, datetime, time as dtime, timezone
from pathlib import Path

import pandas as pd

from engine import special_arb as arb
from lib import config, nyse_calendar

log = logging.getLogger(__name__)

SCORED = False
DISCLAIMER = ("Context only — an event-tracking display of public filings, not a "
             "signal, recommendation, or sizing input.")

# --- mature taxonomy categories (the ~16 live labels) -----------------------
ACQ, DIV, ACT, REV = "Acquisitions", "Divestitures", "Activist Campaigns", "Strategic Reviews"
TO, GP, CAP, SPIN = "Tender Offers", "Going-Private", "Capital Returns", "Spin-Offs"
RIGHTS, RESTR, LIQ, DELIST = "Rights Offerings", "Restructuring", "Liquidations", "Delistings"
ITEND, TERM, SPAC, MGMT = "Issuer Tenders", "Deal Terminations", "SPACs", "Management Changes"
OTHER = "Other"

# the mature taxonomy an LLM verdict (P1.1) may legitimately promote to (excludes "None")
MATURE_CATEGORIES = frozenset({
    ACQ, DIV, ACT, REV, TO, GP, CAP, SPIN, RIGHTS, RESTR, LIQ, DELIST, ITEND, TERM, SPAC, MGMT, OTHER,
})
# categories the LLM lane may auto-promote to the desk. Management Changes is EXCLUDED: a
# verification sample showed the model over-fires it on foreign-6-K AGM / "management
# information circular" / meeting-reminder notices (4 of 5 sampled were misfires), and the
# recon says it's a tiny category that only matters when it co-occurs with activism. Keep it
# off the desk rather than admit that noise; the activist 13D/proxy lane already catches the
# real cases.
LLM_PROMOTABLE = MATURE_CATEGORIES - {MGMT}
# default stage when the LLM promotes an ambiguous filing and no stage is already set
LLM_STAGE_DEFAULT: dict[str, str] = {
    ACQ: "announced", DIV: "announced", ACT: "initiated", REV: "initiated", TO: "live",
    GP: "live", CAP: "announced", SPIN: "announced", RIGHTS: "live", RESTR: "announced",
    LIQ: "announced", DELIST: "notice", ITEND: "live", TERM: "terminated", SPAC: "de-SPAC",
    MGMT: "change", OTHER: "announced",
}

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
        # 8-K 5.02 (officer change) dropped: 0% precision vs digest — routine changes are
        # not situations, and activist-context CEO exits already surface via the 13D/proxy.
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
        "merger agreement was terminated", "terminated the merger", "termination of the business combination")),
    # SPAC before Acquisitions — STRICT (tuned vs digest: "business combination"/"trust
    # account" were too broad and stole real mergers). SPAC-only terminology:
    (SPAC, "de-SPAC", (
        "blank check company", "special purpose acquisition", "initial business combination")),
    (REV, "initiated", (
        "strategic alternatives", "strategic review", "review of strategic",
        "explore strategic", "evaluating strategic", "range of strategic", "exploring a sale")),
    (SPIN, "announced", (
        "spin-off", "spinoff", "spin off of", "plan to separate", "separation into two",
        "intends to separate", "tax-free distribution", "as an independent public company",
        "complete the separation")),
    # Rights before Divest/Acq — STRICT (tuned vs digest: most 424B5 are ordinary shelf
    # takedowns, not rights offerings; require true rights-offering mechanics):
    (RIGHTS, "live", (
        "non-transferable subscription rights", "oversubscription privilege",
        "basic subscription right", "rights offering of")),
    # Divestiture: selling a business unit (not products). Moderate breadth restored.
    (DIV, "announced", (
        "to divest", "divestiture", "agreed to divest", "definitive agreement to sell",
        "agreement to sell its", "agreed to sell its", "sale of its subsidiary",
        "sale of its business", "sale of the business", "sale of its division",
        "sale of its segment", "sale of its stake", "carve-out")),
    # Acquisition: require a real merger/acquisition agreement — tightened (dropped bare
    # "will acquire" / "agreement to acquire" which fire on product/license deals)
    (ACQ, "announced", (
        "agreement and plan of merger", "definitive merger agreement", "plan of merger",
        "to be acquired by", "agreed to be acquired", "definitive agreement to acquire",
        "agreed to acquire all", "entered into a merger agreement", "merger consideration of")),
    (CAP, "announced", (
        "share repurchase program", "stock repurchase program", "accelerated share repurchase",
        "special dividend", "special cash dividend", "increased its quarterly dividend",
        "authorized the repurchase", "return of capital", "increase to its repurchase")),
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


def passes_floor(mc_musd: object, confidence: object = None,
                 floor: float = 100.0, floor_high: float = 25.0) -> bool:
    """Desk floor gate WITH a confidence relaxation (decision 2026-06-21): unknown mc kept;
    >= floor always kept; a HIGH-confidence situation (structured form / LLM-verified /
    digest) is kept down to floor_high ($25M) to capture the small-cap activist / take-private
    niche — without admitting low-confidence micro-cap keyword noise."""
    if mc_musd is None or (isinstance(mc_musd, float) and pd.isna(mc_musd)):
        return True
    mc = float(mc_musd)
    if mc >= float(floor):
        return True
    return str(confidence or "").lower() == "high" and mc >= float(floor_high)


def _terms_dict(raw: object) -> dict:
    """Parse the LLM `llm_terms` JSON string (deal terms) into a dict; {} on anything else."""
    if not raw or (isinstance(raw, float) and pd.isna(raw)):
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        import json as _json
        obj = _json.loads(str(raw))
        return obj if isinstance(obj, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


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


# categories that progress along an announced -> closed / terminated arc (P3.1)
_DEAL_ARC = frozenset({ACQ, TO, GP, SPIN, DIV})


def lifecycle(df: pd.DataFrame) -> dict[tuple, dict]:
    """Link the SAME deal's filings into a timeline — our edge over the stageless weekly
    digest. Group classified events by (cik, category), order by filing date, and derive a
    current stage + stage history + amendment count. Terminal states ("terminated" / "closed")
    are inferred from the filer's OTHER rows: a Deal-Terminations event, an 8-K Item 2.01
    completion, or a Form 15 deregistration. Returns {(cik, category): {...}}. Pure."""
    out: dict[tuple, dict] = {}
    if df is None or df.empty:
        return out
    # per-filer terminal signals, read across ALL of a CIK's rows (not just one category)
    term: dict[str, set] = {}
    for cik, g in df.groupby(df.cik.astype(str)):
        flags: set[str] = set()
        if (g.category == TERM).any():
            flags.add("terminated")
        items = g["items"].astype(str) if "items" in g.columns else pd.Series("", index=g.index)
        if items.str.contains("2.01", na=False).any() or g.form_type.isin(["15-12B", "15-12G"]).any():
            flags.add("closed")
        if flags:
            term[cik] = flags
    work = df[df.status == "ok"]
    for (cik, cat), g in work.groupby([work.cik.astype(str), work.category]):
        g = g.sort_values("date_filed")
        hist = [{"date": r.get("date_filed"), "stage": r.get("stage"), "form": r.get("form_type")}
                for _, r in g.iterrows()]
        cur = g.iloc[-1].get("stage")
        terminal = None
        if cat in _DEAL_ARC:
            flags = term.get(str(cik), set())
            if "terminated" in flags:
                terminal, cur = "terminated", "terminated"
            elif "closed" in flags:
                terminal, cur = "closed", "closed"
        out[(str(cik), cat)] = {
            "current_stage": cur, "stage_history": hist,
            "n_amendments": int(g.form_type.astype(str).str.contains(r"/A", na=False).sum()),
            "n_filings": int(len(g)), "first_date": g.date_filed.min(),
            "last_date": g.date_filed.max(), "terminal": terminal,
        }
    return out


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

    # confidence: structured-form / decisive-item classifications are HIGH; the keyword
    # text lane is a HEURISTIC (audit found ~67% FP on unvalidated extras) -> LOW, so the
    # desk + trading brain never treat keyword guesses as facts. The LLM lane (P1.3) or a
    # digest match upgrades a situation's standing downstream.
    df["confidence"] = "high"

    # text lane (P1.1b): deferred filings the enrichment step classified from document text.
    if "text_category" in df.columns:
        items_s = df["items"].astype(str) if "items" in df.columns else pd.Series("", index=df.index)
        promote = (df.status == "defer") & df.text_category.notna() & (df.text_category != "")
        # a 424B5 is a securities OFFERING (shelf raise) — its boilerplate trips M&A
        # keywords; only a genuine Rights Offering qualifies, never Acq/Divest/Spin/etc.
        promote &= ~((df.form_type == "424B5") & (df.text_category != RIGHTS))
        # Deal Terminations needs the 8-K termination item (1.02); without it, the keyword
        # is usually deal-ENTRY/progress boilerplate (audit: 5/6 Deal-Term extras were FPs).
        promote &= ~((df.text_category == TERM) & ~items_s.str.contains("1.02", na=False))
        df.loc[promote, "category"] = df.loc[promote, "text_category"]
        df.loc[promote, "stage"] = df.loc[promote, "text_stage"] if "text_stage" in df.columns else "announced"
        df.loc[promote, "status"] = "ok"
        df.loc[promote, "confidence"] = "low"        # keyword heuristic, not verified

    # LLM verify lane (P1.1): the model read the deferred filings and returned a verified
    # category + role + confidence. This OVERRIDES the noisy keyword text-lane — a real
    # category becomes high/medium-confidence; category "None" is the model judging it not a
    # special situation, which DROPS the keyword false positive (the ~67%-FP precision fix).
    if "llm_category" in df.columns:
        for col in ("llm_confidence", "llm_role", "role"):
            if col not in df.columns:
                df[col] = pd.NA
        llm = df.llm_category.astype("string").str.strip()
        valid = llm.isin(LLM_PROMOTABLE).fillna(False)
        is_none = llm.str.lower().eq("none").fillna(False)
        if valid.any():
            df.loc[valid, "category"] = llm[valid]
            df.loc[valid, "status"] = "ok"
            df.loc[valid, "role"] = df.loc[valid, "llm_role"]
            conf = df.loc[valid, "llm_confidence"].astype("string").str.lower()
            df.loc[valid, "confidence"] = conf.where(conf.isin(["high", "medium", "low"]), "medium")
            df.loc[valid, "stage"] = df.loc[valid].apply(
                lambda r: r["stage"] if (r.get("stage") and not (isinstance(r["stage"], float) and pd.isna(r["stage"])))
                else LLM_STAGE_DEFAULT.get(r["category"], "announced"), axis=1)
        if is_none.any():
            df.loc[is_none, ["status", "category", "stage", "confidence"]] = ["skip", None, None, "high"]

    # cross-filing Going-Private upgrade: any CIK with an SC 13E-3 -> its merger
    # proxy / third-party tender is an affiliate take-private (§B1).
    gp_ciks = set(df.loc[df.form_type.str.startswith("SC 13E3"), "cik"].astype(str))
    upg = df.cik.astype(str).isin(gp_ciks) & df.category.isin([ACQ, TO])
    df.loc[upg, ["category", "stage"]] = [GP, "live"]

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

    # lifecycle / stage tracking (P3.1): link each deal's filings into a timeline and stamp
    # the current stage (incl. terminal "terminated"/"closed") + amendment count per row.
    lc = lifecycle(df)
    keys = list(zip(df.cik.astype(str), df.category))
    df["current_stage"] = [(lc.get(k) or {}).get("current_stage") for k in keys]
    df["n_amendments"] = [(lc.get(k) or {}).get("n_amendments") for k in keys]
    df["deal_terminal"] = [(lc.get(k) or {}).get("terminal") for k in keys]
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
    keep_cols = ["id", "accession", "ticker", "company", "category", "stage", "form_type",
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
            "source_lane": "digest", "live": False, "confidence": "high",  # editor-curated
        })
    return rows


# There is NO default price basis, and the arb lane no longer reads the broad close panels at
# all. `_closes_*` below still serve the activist track record and the price backfill; they are
# `auto_adjust=True` stores (breadth.py:402, special_prices.py:86), so labelling any of them a
# raw close is a false receipt — and a back-adjusted reference close runs LOW, which inflated
# `filing_reference_premium_pct` systematically rather than randomly.
#
# V1's verified path reads exactly one provenance: the per-ticker U.S. Yahoo store's
# `close_price` (`auto_adjust=False`, split-adjusted / dividend-unadjusted).
_CALENDAR_REVISION = "nyse_calendar.v1"


def _closes_frames() -> list[tuple[str, pd.DataFrame]]:
    """(artifact identity, frame) for every close panel the arb lane may price from.

    The artifact name travels with the price so a published spread can name the file it was
    priced from, and so two incompatible price BASES can never be silently mixed.
    """
    out: list[tuple[str, pd.DataFrame]] = []
    for g in ("breadth", "midcap_breadth", "smallcap_breadth"):
        p = config.data_dir() / g / "_closes_cache.parquet"
        if p.exists():
            try:
                out.append((f"{g}/_closes_cache.parquet", pd.read_parquet(p)))
            except Exception:  # noqa: BLE001
                pass
    for f in ("bt_prices.parquet", "arb_prices.parquet"):   # backtest + deal-target backfills
        p = config.data_dir() / GROUP / f
        if p.exists():
            try:
                out.append((f"{GROUP}/{f}", pd.read_parquet(p)))
            except Exception:  # noqa: BLE001
                pass
    for sub, fn in (("canada_search", "closes.parquet"), ("intl_search", "closes.parquet"),
                    ("hk_search", "closes_deep.parquet")):
        p = config.data_dir() / sub / fn
        if p.exists():
            try:
                out.append((f"{sub}/{fn}", pd.read_parquet(p)))
            except Exception:  # noqa: BLE001
                pass
    return out


def _closes_panel(frames: list[tuple[str, pd.DataFrame]] | None = None) -> pd.DataFrame:
    """Daily closes (tickers as columns) for the cash-deal spread lane. US breadth + the
    backtest backfill (bare tickers, USD) PLUS the foreign stock-search closes — Canada
    (.TO, CAD), intl/UK (.L GBP, .T JPY, ...) and HK (.HK) — so cross-border deal targets can be
    priced in their own currency. Columns keep their exchange suffix for the foreign sets."""
    frames = _closes_frames() if frames is None else frames
    if not frames:
        return pd.DataFrame()
    df = pd.concat([f for _, f in frames], axis=1, sort=False)
    try:
        df.index = pd.to_datetime(df.index)
    except Exception:  # noqa: BLE001
        return pd.DataFrame()
    return df.loc[:, ~df.columns.duplicated()].sort_index()


def _artifact_digest(path: Path) -> str | None:
    """sha256 of the exact price artifact bytes. A path is a location, not an identity."""
    try:
        h = hashlib.sha256()
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def us_listing_price_store(listing: str) -> Path | None:
    """`data/yahoo/<LISTING>.parquet` iff it exists AND carries `close_price`, else None.

    The resolved-listing receipt V1 is built on. `collectors/yahoo.py` fetches this store with
    `auto_adjust=False` and documents `close_price` as split-adjusted / dividend-UNadjusted — the
    structure-math basis — so the store's existence with that exact column is what establishes
    both the listing and its USD quote currency. Nothing here reads ticker syntax.
    """
    if not listing:
        return None
    p = config.data_dir() / "yahoo" / f"{listing}.parquet"
    if not p.exists():
        return None
    try:
        import pyarrow.parquet as pq
        names = set(pq.read_schema(p).names)
    except Exception:  # noqa: BLE001
        return None
    from engine import special_arb as arb
    return p if arb.PRICE_COLUMN in names else None


def _yahoo_close_series(listing: str) -> tuple[object, str, int] | None:
    """(close_price series indexed by session, artifact digest, artifact byte length) or None."""
    path = us_listing_price_store(listing)
    if path is None:
        return None
    from engine import special_arb as arb
    try:
        df = pd.read_parquet(path, columns=[arb.PRICE_COLUMN])
        idx = pd.to_datetime(df.index)
    except Exception as e:  # noqa: BLE001
        log.warning("special_situations arb: yahoo store unreadable for %s: %s", listing, e)
        return None
    s = pd.Series(df[arb.PRICE_COLUMN].to_numpy(), index=idx).dropna()
    if s.empty:
        return None
    digest = _artifact_digest(path)
    try:
        nbytes = path.stat().st_size
    except OSError:
        return None
    if not digest:
        return None
    return s, digest, int(nbytes)


def _yahoo_price_input(listing: str, series, digest: str, nbytes: int, session,
                       value: float, now_utc: datetime) -> dict:
    """One narrow-V1 price receipt over the exact Yahoo artifact bytes.

    Every field the pure reducer independently re-derives or checks against a closed vocabulary
    is stated here by the producer that actually opened the file — including the two series-level
    facts a pure owner cannot recompute (unique monotonic sessions, finite positive values).
    """
    from engine import special_arb as arb
    sessions = [x.date() for x in series.index]
    unique_monotonic = all(b > a for a, b in zip(sessions, sessions[1:]))
    finite_positive = bool(((series > 0) & series.notna()).all()) and \
        bool(pd.Series(series).map(lambda v: v == v and abs(v) != float("inf")).all())
    return arb.price_input(
        ticker=listing, listing=arb.US_CALENDAR_ID, session=session.isoformat(),
        value=float(value), currency="USD", basis=arb.PRICE_BASIS_SPLIT_ADJ,
        column=arb.PRICE_COLUMN, source_artifact=f"yahoo/{listing}.parquet",
        artifact_sha256=digest, artifact_bytes=nbytes,
        writer_owner=arb.PRICE_WRITER_OWNER, writer_blob=arb.PRICE_WRITER_BLOB,
        calendar_owner=arb.CALENDAR_OWNER, calendar_blob=arb.CALENDAR_BLOB,
        calendar_revision=_CALENDAR_REVISION, calendar_id=arb.US_CALENDAR_ID,
        expected_session=nyse_calendar.expected_last_session(now_utc).isoformat(),
        sessions_behind=int(nyse_calendar.sessions_behind(session, now_utc)),
        sessions_unique_monotonic=unique_monotonic, values_finite_positive=finite_positive,
        read_validated=True, recorded_at=now_utc.isoformat())


def _observations_path() -> Path:
    return config.data_dir() / GROUP / "observations" / "observations.jsonl"


def _load_observations() -> tuple[dict[str, list[dict]], dict]:
    """The deal-term ledger keyed by EVENT ACCESSION, with an integrity census. Fails CLOSED.

    Two separate defects closed here.

    **The join key.** Rows were grouped under `source.cik` and that whole issuer bucket was
    compiled for every situation, so two unrelated deals by one filer shared a price. An issuer
    is not a deal. Special Situations events already set `id = accession`, so the accession IS
    the transaction key, and a cross-accession lineage now has to be proven by explicit
    supersession rather than assumed from a shared filer.

    **The rebind.** `validate_observation()` re-derives a row's id from the row's OWN fields, so
    a forger who edits a value, moves a span and recomputes the id passed it — and nothing ever
    re-opened the retained object or the projection the offsets claim to index. Every row is now
    re-bound to the retained bytes: raw digest and byte length, projection digest/length/
    revision, locator bounds, excerpt digest, document identity, accession identity and
    completeness, all recomputed before a single term is compiled.
    """
    from collectors import special_situations as col
    from engine import special_arb as arb
    p = _observations_path()
    census = {"lines": 0, "malformed": 0, "invalid": 0, "unbound": 0, "kept": 0,
              "integrity_failed": False}
    if not p.exists():
        return {}, census
    out: dict[str, list[dict]] = {}
    try:
        lines = p.read_text(errors="replace").splitlines()
    except Exception as e:  # noqa: BLE001
        log.warning("special_situations: observation ledger unreadable: %s", e)
        census["integrity_failed"] = True
        return {}, census
    # the SAME canonical authority the collector's reader uses: clock and listing come from the
    # event owner and the price owner, never from the untrusted row
    authority = col.canonical_event_authority()
    verified_cache: dict[str, tuple[bytes, dict] | None] = {}
    # re-extraction is per (document, listing currency), not per row: a ledger with hundreds of
    # rows over a handful of accessions would otherwise re-parse each document once per row
    authored_cache: dict[tuple[str, object], set[tuple]] = {}
    for line in lines:
        line = line.strip()
        if not line:
            continue
        census["lines"] += 1
        try:
            o = json.loads(line)
        except ValueError:
            census["malformed"] += 1          # a truncated last write is a REAL failure
            continue
        if not arb.validate_observation(o):
            census["invalid"] += 1
            continue
        accession = str((o.get("source") or {}).get("accession") or "")
        if not accession:
            census["unbound"] += 1
            continue
        if accession not in verified_cache:
            receipt = col._source_receipt(accession)
            raw = col.retained_source_bytes(receipt) if receipt else None
            verified_cache[accession] = (raw, receipt) if (raw and receipt) else None
        bound = verified_cache[accession]
        if bound is None:
            census["unbound"] += 1            # a row citing bytes this host does not retain
            continue
        raw, receipt = bound
        event = authority.get(accession)
        # the CANONICAL listing currency decides whether a bare `$` may be USD. Keying this on
        # `o.get("currency")` let the untrusted row nominate the authority that then blessed it.
        canonical_ccy = (event or {}).get("currency")
        akey = (accession, canonical_ccy)
        if akey not in authored_cache:
            authored_cache[akey] = arb.authored_terms(
                arb.normalized_projection(raw.decode("utf-8", "replace")),
                listing_currency=canonical_ccy)
        if arb.rebind_observation(o, raw_bytes=raw, receipt=receipt, accession=accession,
                                  authored=authored_cache[akey], event=event):
            census["unbound"] += 1            # a row that does not descend from those bytes
            continue
        out.setdefault(accession, []).append(o)
        census["kept"] += 1
    lineage = arb.validate_lineage([o for rows in out.values() for o in rows])
    if lineage:
        census["lineage"] = lineage
    census["integrity_failed"] = bool(census["malformed"] or census["invalid"]
                                      or census["unbound"] or lineage)
    if census["integrity_failed"]:
        log.warning("special_situations: observation ledger integrity: %d malformed, %d invalid, "
                    "%d unbound of %d rows", census["malformed"], census["invalid"],
                    census["unbound"], census["lines"])
    return out, census


def _price_inputs(listing: str, now_utc: datetime) -> tuple[dict | None, object]:
    """The narrow-V1 live price for one EXACT resolved U.S. listing, plus its close series.

    Reads only `data/yahoo/<LISTING>.parquet::close_price`. The previous version searched a
    concatenated panel of breadth + backtest + Canada/intl/HK search stores, fell back from a
    suffixed target to `raw.split(".")[0]`, took the currency from whichever COLUMN it selected,
    and stamped `calendar_id="XNYS"` on all of it — so on 2026-07-03 (NYSE closed, HKEX open) an
    HK row one local session stale reported `sessions_behind=0` and reached VERIFIED.

    Freshness comes from `lib/nyse_calendar` and the file's own bytes are digested, because
    grading a store against itself lets a globally frozen panel certify every listing current.
    """
    read = _yahoo_close_series(listing)
    if read is None:
        return None, None
    series, digest, nbytes = read
    session = series.index[-1].date()
    live = _yahoo_price_input(listing, series, digest, nbytes, session,
                              float(series.iloc[-1]), now_utc)
    return live, series


def _reference_price(listing: str, series, acceptance: object, now_utc: datetime) -> dict | None:
    """Last completed session strictly BEFORE the exact SEC availability moment, or None.

    A date-only filing date cannot say whether the market had already closed when the filing
    became available, so without an exact acceptance timestamp there is no defensible reference
    session and the reducer reports REFERENCE_SESSION_UNRESOLVED.
    """
    if series is None or acceptance is None:
        return None
    read = _yahoo_close_series(listing)
    if read is None:
        return None
    _, digest, nbytes = read
    try:
        cut = pd.Timestamp(acceptance)
    except Exception:  # noqa: BLE001
        return None
    if cut.tzinfo is None:
        cut = cut.tz_localize("UTC")
    cut_et = cut.tz_convert(nyse_calendar.ET)
    # A session qualifies only once it has CLOSED. Comparing the session's midnight index
    # against the acceptance moment made a premarket filing pick that same day's unclosed
    # session — the exact premarket/after-close confusion the exact timestamp exists to remove.
    qualified = [d for d in (x.date() for x in series.index)
                 if pd.Timestamp(datetime.combine(d, dtime(16, 0)),
                                 tz=nyse_calendar.ET) < cut_et]
    if not qualified:
        return None
    rs = pd.Timestamp(qualified[-1])
    return _yahoo_price_input(listing, series, digest, nbytes, rs.date(),
                              float(series.loc[rs]), now_utc)


def _enrich_arb(sits: list[dict], *, now_utc: datetime | None = None) -> int:
    """Attach the typed `arb` economics block to every fixed-cash-eligible situation.

    Every arb-category situation gets a block, INCLUDING the degraded ones, so a missing term,
    a stale price or a failed ledger row is reported in its own visible state rather than
    vanishing. Returns the VERIFIED count.
    """
    from engine import special_arb as arb
    now_utc = now_utc or datetime.now(timezone.utc)
    obs_by_accession, census = _load_observations()
    n = 0
    for s in sits:
        if s.get("category") not in arb.ARB_CATEGORIES:
            continue
        # the event id IS the accession for the EDGAR lane (collectors set `id=accession`), and
        # an accession is the transaction. The issuer CIK is deliberately not consulted.
        accession = str(s.get("accession") or s.get("id") or "")
        rows = obs_by_accession.get(accession)
        if census.get("integrity_failed"):
            # partial generation must not present as a healthy projection of survivors
            s["arb"] = arb.reduce_cash_deal(
                {"status": "ambiguous", "reasons": ["INTEGRITY_FAILED", "PARTIAL_GENERATION"],
                 "terms": {}, "evidence": {}, "accession": None, "amendment_chain": []},
                category=s.get("category"), stage=s.get("stage"), now_utc=now_utc)
            s["arb"]["ledger_census"] = census
            continue
        # an explicitly linked lineage may reach past this accession, so the connected component
        # is offered to the compiler — which admits ONLY rows it can reach by a validated edge
        candidates = list(rows or [])
        if candidates:
            linked = {o.get("supersedes_observation_id") for o in
                      (r for group in obs_by_accession.values() for r in group)}
            ids = {o.get("observation_id") for o in candidates}
            if linked & ids or any(o.get("supersedes_observation_id") for o in candidates):
                candidates = [o for group in obs_by_accession.values() for o in group]
        compiled = arb.compile_current_terms(candidates, accession=accession or None)
        listing = arb.resolve_us_listing(s.get("ticker"))
        live = ref = None
        if listing:
            live, series = _price_inputs(listing, now_utc)
            acceptance = next((ev.get("acceptance_datetime")
                               for ev in (compiled.get("evidence") or {}).values()
                               if ev.get("acceptance_datetime")), None)
            ref = _reference_price(listing, series, acceptance, now_utc)
        econ = arb.reduce_cash_deal(compiled, category=s.get("category"), stage=s.get("stage"),
                                    live_price=live, reference_price=ref, now_utc=now_utc,
                                    ticker=listing or s.get("ticker"))
        s["arb"] = econ
        if econ.get("quality_state") == arb.QUALITY_VERIFIED:
            n += 1
    return n


def _news_rows() -> list[dict]:
    """Newswire-lane situations (P2.1) for the form-absent categories. Separate low-confidence
    lane (data/special_situations/news.parquet); kept out of build_situations / the backtest
    so the EDGAR point-in-time signal stays clean. Empty unless the gated lane has run."""
    p = config.data_dir() / GROUP / "news.parquet"
    if not p.exists():
        return []
    d = pd.read_parquet(p)
    if d.empty:
        return []
    rows = []
    for _, r in d.iterrows():
        rows.append({
            "id": f"news-{r.get('id')}", "ticker": r.get("ticker"), "company": r.get("company"),
            "category": r.get("category"), "stage": r.get("stage") or "announced",
            "form_type": "Newswire", "cross_border": False, "mc_musd": None,
            "date_filed": r.get("date"), "source_url": r.get("url"),
            "summary": (r.get("summary") if pd.notna(r.get("summary")) else None),
            "business_desc": None, "country": "US", "source_lane": "newswire",
            "live": False, "confidence": r.get("confidence") or "low",
        })
    return rows


def _intl_rows() -> list[dict]:
    """International-lane situations (Phase 4) from the gated UK/Canada collectors. Separate
    cross-border lane (data/special_situations/intl.parquet); empty unless a market is on."""
    p = config.data_dir() / GROUP / "intl.parquet"
    if not p.exists():
        return []
    d = pd.read_parquet(p)
    if d.empty:
        return []
    rows = []
    for _, r in d.iterrows():
        rows.append({
            "id": f"intl-{r.get('id')}", "ticker": r.get("ticker"), "company": r.get("company"),
            "category": r.get("category"), "stage": r.get("stage") or "announced",
            "form_type": f"Intl·{str(r.get('market') or '').upper()}", "cross_border": True,
            "mc_musd": None, "date_filed": r.get("date"), "source_url": r.get("url"),
            "summary": (r.get("summary") if pd.notna(r.get("summary")) else None),
            "business_desc": None, "country": (r.get("country") or None),
            "source_lane": "intl", "live": False, "confidence": r.get("confidence") or "low",
        })
    return rows


PRIOR_MIN_N = 5          # don't show a prior thinner than this (noise floor)


def _priors() -> tuple[dict, dict]:
    """Historical forward-return context from the P5.1 backtest, read-only:
    ((category, stage) -> prior) from the EDGAR by-stage priors, and (category -> prior)
    from the by-category priors as a fallback. {} if the artifacts are absent."""
    import json as _json
    stage_p: dict = {}
    cat_p: dict = {}
    sp = config.data_dir() / GROUP / "edgar_backtest_priors.json"
    if sp.exists():
        try:
            for v in (_json.loads(sp.read_text()).get("by_category_stage") or {}).values():
                stage_p[(v.get("category"), v.get("stage"))] = v
        except Exception:  # noqa: BLE001
            pass
    cp = config.data_dir() / GROUP / "backtest_priors.json"
    if cp.exists():
        try:
            cat_p = _json.loads(cp.read_text()).get("by_category") or {}
        except Exception:  # noqa: BLE001
            pass
    return stage_p, cat_p


def _load_event_priors() -> dict:
    """Load W3 event-intelligence priors (ss_event_priors.v2) from
    data/special_situations/event_priors/*.json.  Returns {event_type: prior_dict}.
    Returns {} gracefully if the directory is absent (artifact not yet generated)."""
    import json as _json
    ev_dir = config.data_dir() / GROUP / "event_priors"
    result: dict = {}
    if not ev_dir.exists():
        return result
    for jf in sorted(ev_dir.glob("*.json")):
        try:
            d = _json.loads(jf.read_text())
            if d.get("schema", "").startswith("ss_event_priors"):
                result[d["event_type"]] = d
        except Exception:  # noqa: BLE001
            pass
    return result


def _prior_for(cat, stage, stage_p: dict, cat_p: dict) -> dict | None:
    """Best prior for a situation: (category, stage) if it clears the sample floor, else
    the category-level prior.

    v2 additive fields (max_dd_20d_pct, pre_drift_pct, hac_t_20d, ci90_20d) are
    carried with None defaults for old-schema files — additive contract (M3 fix).

    When the prior is sub-floor: returns an explicit {insufficient: True, n: K} block
    so the display can print "insufficient history (n=K)" rather than silently absent
    or an empty string (m1 fix)."""
    def _mk(p, scope):
        n = int(p.get("n") or 0)
        if n < PRIOR_MIN_N or p.get("win_20d_pct") is None:
            return {"insufficient": True, "n": n, "scope": scope}
        return {
            "scope": scope,
            "n": n,
            "win_20d_pct": p.get("win_20d_pct"),
            "med_ret_20d_pct": p.get("med_ret_20d_pct"),
            "med_ret_60d_pct": p.get("med_ret_60d_pct"),
            # v2 additive fields (None when old-schema file)
            "max_dd_20d_pct": p.get("max_dd_20d_pct"),
            "pre_drift_pct": p.get("pre_drift_pct"),
            "hac_t_20d": p.get("hac_t_20d"),
            "ci90_20d": p.get("ci90_20d"),
        }
    p = stage_p.get((cat, stage))
    if p and (p.get("n") or 0) >= PRIOR_MIN_N and p.get("win_20d_pct") is not None:
        return _mk(p, f"{cat} · {stage}")
    c = cat_p.get(cat)
    if c and (c.get("n") or 0) >= PRIOR_MIN_N and c.get("win_20d_pct") is not None:
        return _mk(c, cat)
    return None


def _attach_priors(sits: list[dict]) -> int:
    """Attach a historical `prior` block to each situation by (category, stage). In place."""
    stage_p, cat_p = _priors()
    if not stage_p and not cat_p:
        return 0
    n = 0
    for s in sits:
        pr = _prior_for(s.get("category"), s.get("stage"), stage_p, cat_p)
        if pr:
            s["prior"] = pr
            n += 1
    return n


def get_event_priors_context() -> dict:
    """Return loaded W3 event-intelligence priors dict for cross-surface use.
    DISPLAY-ONLY: is_context_only=True on every entry. Returns {} if not yet generated."""
    return _load_event_priors()


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

    # newswire lane (P2.1): add the form-absent categories where the digest doesn't already
    # cover the same (ticker, category). Low-confidence; EDGAR confirmation upgrades below.
    for r in _news_rows():
        k = (_norm_ticker(r["ticker"]), r["category"])
        if k not in merged:
            merged[k] = r

    # international lane (Phase 4): UK/Canada cross-border situations (gated collectors).
    for r in _intl_rows():
        k = (_norm_ticker(r["ticker"]), r["category"])
        if k not in merged:
            merged[k] = r

    if not (elive is None or elive.empty):
        for _, r in elive.iterrows():
            k = (_norm_ticker(r.get("ticker")), r.get("category"))
            if k in merged and k[0] is not None:
                merged[k]["live"] = True                       # same situation, confirmed
                merged[k]["edgar_url"] = r.get("source_url")
                # a digest-confirmed row keeps the DIGEST dict, which carries no event identity —
                # take the ACCESSION from the confirming EDGAR filing, or the observation-ledger
                # join finds nothing. The CIK travels for display only; it is not a join key.
                merged[k].setdefault("accession", r.get("accession") or r.get("id"))
                merged[k].setdefault("cik", r.get("cik"))
            else:
                merged[k] = {
                    "id": r.get("id"), "ticker": r.get("ticker"), "company": r.get("company"),
                    # the EVENT ACCESSION is the join key for the deal-term observation ledger.
                    # It was the issuer CIK, which compiled one issuer bucket for every
                    # situation and let two unrelated deals by one filer share a price (F09-1).
                    "accession": r.get("accession") or r.get("id"),
                    "cik": r.get("cik"),
                    "category": r.get("category"),
                    "stage": r.get("current_stage") or r.get("stage") or "",
                    "n_amendments": int(r["n_amendments"]) if pd.notna(r.get("n_amendments")) else 0,
                    "terminal": (r.get("deal_terminal") if pd.notna(r.get("deal_terminal")) else None),
                    "form_type": r.get("form_type"), "cross_border": bool(r.get("cross_border")),
                    "mc_musd": r.get("mc_musd"), "date_filed": r.get("date_filed"),
                    "source_url": r.get("source_url"),
                    "summary": (r.get("summary") if pd.notna(r.get("summary")) else None),
                    "business_desc": None, "country": "US",
                    "source_lane": "edgar", "live": True,
                    "confidence": r.get("confidence") or "high",
                    "role": (r.get("role") if pd.notna(r.get("role")) else None),
                    "deal_terms": _terms_dict(r.get("llm_terms")),
                }

    floor_high = float(_cfg().get("market_cap_floor_high_conf_musd", 25))
    sits = [s for s in merged.values()
            if passes_floor(s.get("mc_musd"), s.get("confidence"), floor, floor_high)]
    sits.sort(key=lambda s: (s.get("date_filed") or "", s.get("category") or ""), reverse=True)

    n_arb = _enrich_arb(sits)        # P1.2 merger-arb spread on deal situations w/ a price
    n_prior = _attach_priors(sits)   # P5.1 historical category x stage forward-return context

    counts: dict[str, int] = {}
    for s in sits:
        counts[s["category"]] = counts.get(s["category"], 0) + 1
    coverage = {
        "shown": len(sits),
        "digest_situations": sum(1 for s in sits if s["source_lane"] == "digest"),
        "edgar_confirmed": sum(1 for s in sits if s["source_lane"] == "digest" and s.get("live")),
        "edgar_only": sum(1 for s in sits if s["source_lane"] == "edgar"),
        "newswire": sum(1 for s in sits if s["source_lane"] == "newswire"),
        "intl": sum(1 for s in sits if s["source_lane"] == "intl"),
        "cross_border": sum(1 for s in sits if s.get("cross_border")),
        "with_summary": sum(1 for s in sits if s.get("summary")),
        "with_arb": n_arb,
        "with_prior": n_prior,
        "high_confidence": sum(1 for s in sits if s.get("confidence") == "high"),
        "low_confidence": sum(1 for s in sits if s.get("confidence") == "low"),
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
                "source": "digest", "source_url": r.get("source_url"), "confidence": "high",
                "brief": (str(summ)[:300] if summ and pd.notna(summ) else r.get("headline")),
                "mc_musd": (float(r["market_cap_musd"]) if pd.notna(r.get("market_cap_musd")) else None),
            })

    for r in _news_rows():
        consider(r.get("ticker"), {
            "ticker": r.get("ticker"), "company": r.get("company"),
            "category": r.get("category"), "stage": r.get("stage") or "announced",
            "date": r.get("date_filed"), "country": "US", "cross_border": False,
            "source": "newswire", "source_url": r.get("source_url"), "confidence": "low",
            "brief": r.get("summary"), "mc_musd": None,
        })

    for r in _intl_rows():
        consider(r.get("ticker"), {
            "ticker": r.get("ticker"), "company": r.get("company"),
            "category": r.get("category"), "stage": r.get("stage") or "announced",
            "date": r.get("date_filed"), "country": r.get("country"), "cross_border": True,
            "source": "intl", "source_url": r.get("source_url"), "confidence": "low",
            "brief": r.get("summary"), "mc_musd": None,
        })

    from engine import activist
    edf = build_situations()
    track = activist.filer_track_record(edf, _closes_panel()) if not edf.empty else {"by_filer": {}}
    if not edf.empty:
        for _, r in edf[edf.status == "ok"].iterrows():
            fname = activist.filer_of(r)
            ftr = track["by_filer"].get(activist.norm_filer(fname)) if fname else None
            consider(r.get("ticker"), {
                "ticker": r.get("ticker"), "company": r.get("company"),
                # the ACCESSION is the observation-ledger join key; the CIK is an issuer, and an
                # issuer is not a transaction (F09-1 critical repair)
                "accession": r.get("accession") or r.get("id"),
                "cik": r.get("cik"),
                "category": r.get("category"),
                "stage": r.get("current_stage") or r.get("stage") or "",
                "n_amendments": int(r["n_amendments"]) if pd.notna(r.get("n_amendments")) else 0,
                "date": r.get("date_filed"), "country": "US",
                "cross_border": bool(r.get("cross_border")),
                "source": "edgar", "source_url": r.get("source_url"),
                "confidence": r.get("confidence") or "high",
                "role": (r.get("role") if pd.notna(r.get("role")) else None),
                "deal_terms": _terms_dict(r.get("llm_terms")) or None,
                "activist_filer": fname,
                "filer_track": ftr,
                "brief": (r.get("summary") if pd.notna(r.get("summary")) else r.get("hk")),
                "mc_musd": (float(r["mc_musd"]) if pd.notna(r.get("mc_musd")) else None),
            })

    # P5.1 historical-prior context (category x stage forward returns) on each name.
    _attach_priors(list(by_ticker.values()))

    # F09-1 cash-deal book: evidence-bound economics + ONE ordered projection shared with
    # `special_sits_intel.build_context_feed()`. The cash-only, date-precision, freshness and
    # amendment law all live in the reducer, so this consumer cannot reinterpret any of it —
    # which is what previously let one consumer exclude a row the other ranked first.
    rows = list(by_ticker.values())
    _enrich_arb(rows)
    ordered, arb_counts = arb.select_ordered_context(rows, limit=25)
    risk_arb = [dict(arb.context_row(r), source=r.get("source")) for r in ordered]

    # P3.2 activist track-record book: filers with enough priced campaigns to be "tracked".
    activist_filers = {k: v for k, v in track["by_filer"].items() if v.get("status") == "tracked"}

    return {
        "schema": "special_situations.v1", "generated_at": now,
        "is_context_only": True, "disclaimer": DISCLAIMER,
        "n": len(by_ticker), "by_ticker": by_ticker,
        "risk_arb": risk_arb, "risk_arb_census": arb_counts,
        "activist_filers": activist_filers,
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
