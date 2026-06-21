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
OTHER = "Other"

# the mature taxonomy an LLM verdict (P1.1) may legitimately promote to (excludes "None")
MATURE_CATEGORIES = frozenset({
    ACQ, DIV, ACT, REV, TO, GP, CAP, SPIN, RIGHTS, RESTR, LIQ, DELIST, ITEND, TERM, SPAC, MGMT, OTHER,
})
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
        valid = llm.isin(MATURE_CATEGORIES).fillna(False)
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
            "source_lane": "digest", "live": False, "confidence": "high",  # editor-curated
        })
    return rows


def _closes_panel() -> pd.DataFrame:
    """US daily closes (breadth caches + the backtest backfill), tickers as columns.
    Reused by the merger-arb spread lane (P1.2) to read live + unaffected prices."""
    frames = []
    for g in ("breadth", "midcap_breadth", "smallcap_breadth"):
        p = config.data_dir() / g / "_closes_cache.parquet"
        if p.exists():
            frames.append(pd.read_parquet(p))
    btp = config.data_dir() / GROUP / "bt_prices.parquet"
    if btp.exists():
        frames.append(pd.read_parquet(btp))
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, axis=1, sort=False)
    try:
        df.index = pd.to_datetime(df.index)
    except Exception:  # noqa: BLE001
        return pd.DataFrame()
    return df.loc[:, ~df.columns.duplicated()].sort_index()


def _price_before(series: pd.Series, date_str: object, offset_rows: int) -> float | None:
    """Close ~offset_rows trading days before date_str — the unaffected-price proxy."""
    s = series.dropna()
    if s.empty or not date_str or (isinstance(date_str, float) and pd.isna(date_str)):
        return None
    try:
        d = pd.Timestamp(date_str)
    except Exception:  # noqa: BLE001
        return None
    pos = s.index.searchsorted(d)
    j = int(pos) - int(offset_rows)
    return float(s.iloc[j]) if 0 <= j < len(s) else None


def _enrich_arb(sits: list[dict]) -> int:
    """Attach an `arb` block (spread / annualized / days-to-close / downside-on-break) to
    each Acquisition / Tender Offer / Going-Private situation that carries a deal price.
    Mutates `sits` in place; returns how many were enriched. Best-effort, never raises."""
    from engine import special_arb as arb
    try:
        panel = _closes_panel()
    except Exception as e:  # noqa: BLE001
        log.warning("special_situations arb: closes panel failed: %s", e)
        return 0
    if panel.empty:
        return 0
    last = panel.iloc[-1]
    n = 0
    for s in sits:
        if s.get("category") not in arb.ARB_CATEGORIES:
            continue
        terms = arb.parse_terms(s.get("deal_terms"))
        if not terms.get("price_per_share"):
            continue
        base = _norm_ticker(s.get("ticker"))
        if not base or base not in panel.columns:
            continue
        lp = last.get(base)
        when = s.get("date_filed") or s.get("date")
        unaff = _price_before(panel[base], when, 30)
        m = arb.arb_metrics(terms["price_per_share"], lp,
                            expected_close=terms.get("expected_close"),
                            consideration=terms.get("consideration"),
                            currency=terms.get("currency"),
                            unaffected_price=unaff)
        if m:
            s["arb"] = m
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


def _prior_for(cat, stage, stage_p: dict, cat_p: dict) -> dict | None:
    """Best prior for a situation: (category, stage) if it clears the sample floor, else
    the category-level prior. None when neither has enough history. Context, not a forecast."""
    def _mk(p, scope):
        return {"scope": scope, "n": int(p.get("n") or 0),
                "win_20d_pct": p.get("win_20d_pct"), "med_ret_20d_pct": p.get("med_ret_20d_pct"),
                "med_ret_60d_pct": p.get("med_ret_60d_pct")}
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
            else:
                merged[k] = {
                    "id": r.get("id"), "ticker": r.get("ticker"), "company": r.get("company"),
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

    # P1.2 merger-arb book: attach spread economics + surface a risk-arb context list for
    # the trading brain (announced cash deals with a price). Context only, never a size.
    _enrich_arb(list(by_ticker.values()))
    risk_arb = sorted(
        ({"ticker": r.get("ticker"), "company": r.get("company"), "category": r.get("category"),
          "source": r.get("source"), **r["arb"]}
         for r in by_ticker.values() if r.get("arb")),
        key=lambda a: (a.get("annualized_pct") is not None, a.get("annualized_pct") or -1e9),
        reverse=True)

    # P3.2 activist track-record book: filers with enough priced campaigns to be "tracked".
    activist_filers = {k: v for k, v in track["by_filer"].items() if v.get("status") == "tracked"}

    return {
        "schema": "special_situations.v1", "generated_at": now,
        "is_context_only": True, "disclaimer": DISCLAIMER,
        "n": len(by_ticker), "by_ticker": by_ticker,
        "risk_arb": risk_arb, "activist_filers": activist_filers,
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
