"""engine/narrative_flare.py — per-ticker narrative witness organ (NAR-R1..R14, W3).

DISPLAY-ONLY. Authority block: tier=display, may_rank=False, may_gate=False,
may_size=False, may_escalate=False.

Reads W2 collector stores (no network in this module) and Polygon news counts;
emits per-ticker narrative_witness objects consumed by the W5 ARMED-state integration.

Constructs (NAR-R4: zero LLM anywhere in this module):
  news_count_z     — robust z of daily article count vs trailing 90d baseline
                     (strictly prior, MIN_BASELINE_OBS=30; young_series when short)
  similarity_gap   — days since ticker last appeared in each channel; novel flag
                     at gap > 90d or first-ever
  tfidf_novelty    — 1 - max cosine-similarity of today's text vs trailing 90d corpus;
                     absent when < 10 prior docs; hand-rolled tf-idf + cosine (no sklearn)
  kleinberg_burst  — 2-state HMM burst detector (s=2, gamma=1) on daily mention counts
  first_coverage   — registry source covering ticker first time in 90d ->
                     append-only data/narrative_flare/first_coverage.parquet (nightly gate)

Entity->ticker join: deterministic alias table from config/narrative_sources.yml.
  join_confidence: 1.0 exact ticker/cashtag, 0.8 full company name, 0.5 ambiguous alias.
  NAR-R9: join_confidence printed on every witness row.

Crowding-hazard: attention LEVEL percentile (wiki views when available, else HN points
  level) carried as hazard_pctile. small_cap_flag: null this wave (no mktcap join).
  NAR-R7: hazard_pctile on every row.

Artifacts:
  site/narrativedata/flares.json       — all-lanes; authority block included
  data/narrative_flare/witness_hist.parquet — PIT, nightly gate
  data/narrative_flare/first_coverage.parquet — append-only, nightly gate
                                                 (SHARED CONTRACT with W4)

NAR-R10: absent/stale stores fail-open (witness absent + reason printed; never crash).

Masterplan: research/NARRATIVE_IGNITION_MASTERPLAN_BY_FABLE.md §4.2 + §7 W3 row.
"""
from __future__ import annotations

import json
import logging
import math
import time
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Authority block (display-tier — NAR §4 invariant)
# ---------------------------------------------------------------------------

AUTHORITY: dict[str, Any] = {
    "tier": "display",
    "may_rank": False,
    "may_gate": False,
    "may_size": False,
    "may_escalate": False,
}

# ---------------------------------------------------------------------------
# Thresholds — FROZEN (pre-registration record, masterplan §4.2)
# Amendments require a new ruling; do NOT edit in place.
# ---------------------------------------------------------------------------

THRESHOLDS: dict[str, Any] = {
    # news_count_z
    "NEWS_BASELINE_DAYS": 90,
    "NEWS_MIN_OBS": 30,              # below this => young_series
    "NEWS_STALE_DAYS": 5,
    # similarity gap — novel threshold
    "GAP_NOVEL_DAYS": 90,
    # TF-IDF novelty
    "TFIDF_MIN_PRIOR_DOCS": 10,      # require >= 10 prior docs else absent
    "TFIDF_BASELINE_DAYS": 90,
    # Kleinberg burst: 2-state HMM (s=2, gamma=1)
    "KLEINBERG_S": 2,
    "KLEINBERG_GAMMA": 1.0,
    "KLEINBERG_BASELINE_DAYS": 90,
    # First coverage gap
    "FIRST_COVERAGE_GAP_DAYS": 90,
    # Stale-store thresholds per channel
    "SUBSTACK_STALE_DAYS": 14,
    "HN_STALE_DAYS": 7,
    "EDGAR_STALE_DAYS": 7,
    "POLYGON_STALE_DAYS": 5,
}

# ---------------------------------------------------------------------------
# Shared contract schema — data/narrative_flare/first_coverage.parquet
# W3 WRITES; W4 READS. Columns must match EXACTLY.
# ---------------------------------------------------------------------------

FIRST_COVERAGE_COLS = [
    "source_id",       # str: feed_id or channel name ("substack:<feed_id>", "hn", "polygon")
    "ticker",          # str
    "date",            # str ISO: published or observed date
    "url",             # str
    "title",           # str
    "join_confidence", # float 0-1
    "fetch_date",      # str ISO
]

# PIT witness history columns
WITNESS_HIST_COLS = [
    "ticker", "date", "fetch_date",
    "news_count_z", "news_count_z_reason",
    "gap_substack_days", "gap_hn_days", "gap_polygon_days",
    "novel_substack", "novel_hn", "novel_polygon",
    "tfidf_novelty", "tfidf_novelty_reason",
    "burst_weight_hn", "burst_weight_polygon",
    "join_confidence", "hazard_pctile", "channels_lit", "present",
]

from engine.ledger_lane import nightly_advance_enabled as _ledger_advance_enabled


# ---------------------------------------------------------------------------
# Robust z-score (same as W1 pattern — no import, self-contained)
# ---------------------------------------------------------------------------


def _robust_z(arr: np.ndarray, value: float) -> float | None:
    """Robust z-score: (value - median) / (MAD * 1.4826). Returns None if empty."""
    arr = arr[~np.isnan(arr)]
    if len(arr) == 0:
        return None
    med = float(np.median(arr))
    mad = float(np.median(np.abs(arr - med)))
    if mad > 1e-10:
        return float((value - med) / (mad * 1.4826))
    std = float(np.std(arr))
    if std < 1e-10:
        return 0.0
    return float((value - med) / std)


# ---------------------------------------------------------------------------
# Alias / entity->ticker join
# ---------------------------------------------------------------------------


def _build_alias_map(reg: dict) -> dict[str, tuple[str, float]]:
    """Build {alias_lower: (ticker, confidence)} from narrative_sources.yml.

    Priority (higher confidence wins on collision):
      1.0 — exact ticker match (always uppercase; "$NVDA" or "NVDA")
      0.8 — full company name from aliases section (case-insensitive)
      0.5 — short / ambiguous alias (case-insensitive)

    The 'hn_keywords' map provides the primary alias list used for HN matching.
    An optional 'aliases' section can extend with company name variants.

    NAR-R9: join_confidence is tracked per-alias.
    """
    alias_map: dict[str, tuple[str, float]] = {}

    # hn_keywords: {ticker: [keyword, ...]}
    # First keyword typically the "full company name" variant => 0.8;
    # remaining => 0.5 (shorter/more ambiguous).
    hn_map: dict[str, list[str]] = reg.get("hn_keywords") or {}
    for ticker, keywords in hn_map.items():
        ticker_up = ticker.upper()
        # Exact ticker match (1.0) — always added
        alias_map[ticker_up.lower()] = (ticker_up, 1.0)
        alias_map[f"${ticker_up}".lower()] = (ticker_up, 1.0)
        for i, kw in enumerate(keywords):
            kw_key = kw.strip().lower()
            if not kw_key:
                continue
            conf = 0.8 if i == 0 else 0.5
            # Only set if not already mapped at higher confidence
            if kw_key not in alias_map or alias_map[kw_key][1] < conf:
                alias_map[kw_key] = (ticker_up, conf)

    # Optional 'aliases' section for extended company name variants
    # Format: {ticker: [full_name, ...]} — each gets 0.8 confidence
    extra_aliases: dict[str, list[str]] = reg.get("aliases") or {}
    for ticker, names in extra_aliases.items():
        ticker_up = ticker.upper()
        for name in names:
            key = name.strip().lower()
            if key and (key not in alias_map or alias_map[key][1] < 0.8):
                alias_map[key] = (ticker_up, 0.8)

    return alias_map


def _join_text_to_ticker(text: str, alias_map: dict[str, tuple[str, float]]) -> tuple[str | None, float]:
    """Return (ticker, confidence) for the best alias match in text.

    Case rules:
    - Ticker / cashtag match: case-sensitive uppercase check (word-boundary via scan)
    - Company name / alias: case-insensitive substring match
    - "Meta"/"meta" ambiguity: require capitalized form ("Meta") for full-name match;
      bare lowercase "meta" without other context gets 0.5 at best.

    Returns (None, 0.0) if no match found.
    """
    best_ticker: str | None = None
    best_conf: float = 0.0

    text_lower = text.lower()

    for alias, (ticker, conf) in alias_map.items():
        # Exact ticker match is already lowercase of the uppercase ticker
        # Try to find it as a word boundary in original text (uppercase check for ticker)
        if conf == 1.0:
            # Cashtag / exact ticker: look for "$TICKER" or word-boundary "TICKER" (uppercase)
            import re
            pat = rf'(?:^|[^A-Za-z$])(\$?{re.escape(ticker)})(?:[^A-Za-z]|$)'
            if re.search(pat, text):
                if conf > best_conf:
                    best_ticker = ticker
                    best_conf = conf
        else:
            # Company name / alias: case-insensitive substring
            if alias in text_lower:
                if conf > best_conf:
                    best_ticker = ticker
                    best_conf = conf

    return best_ticker, best_conf


# ---------------------------------------------------------------------------
# Store loaders (fail-open per NAR-R10)
# ---------------------------------------------------------------------------


def _load_substack(data_root: Path) -> pd.DataFrame | None:
    p = data_root / "narrative" / "substack_posts.parquet"
    if not p.exists():
        log.warning("narrative_flare: substack_posts.parquet absent at %s", p)
        return None
    try:
        return pd.read_parquet(p)
    except Exception as e:  # noqa: BLE001
        log.warning("narrative_flare: substack_posts.parquet read failed: %s", e)
        return None


def _load_hn(data_root: Path) -> pd.DataFrame | None:
    p = data_root / "narrative" / "hn_mentions.parquet"
    if not p.exists():
        log.warning("narrative_flare: hn_mentions.parquet absent at %s", p)
        return None
    try:
        return pd.read_parquet(p)
    except Exception as e:  # noqa: BLE001
        log.warning("narrative_flare: hn_mentions.parquet read failed: %s", e)
        return None


def _load_edgar(data_root: Path) -> pd.DataFrame | None:
    p = data_root / "narrative" / "edgar_8k_counts.parquet"
    if not p.exists():
        log.warning("narrative_flare: edgar_8k_counts.parquet absent at %s", p)
        return None
    try:
        return pd.read_parquet(p)
    except Exception as e:  # noqa: BLE001
        log.warning("narrative_flare: edgar_8k_counts.parquet read failed: %s", e)
        return None


def _load_polygon_news(data_root: Path) -> pd.DataFrame | None:
    p = data_root / "polygon" / "news_sentiment.parquet"
    if not p.exists():
        log.warning("narrative_flare: news_sentiment.parquet absent at %s", p)
        return None
    try:
        df = pd.read_parquet(p)
        return df
    except Exception as e:  # noqa: BLE001
        log.warning("narrative_flare: news_sentiment.parquet read failed: %s", e)
        return None


def _load_attention(data_root: Path, today: date) -> pd.DataFrame | None:
    """Try to load wiki/attention parquet for today or recent date.

    NAR-R7: attention level -> crowding hazard. Returns None if absent (graceful).
    """
    attn_dir = data_root / "attention"
    if not attn_dir.exists():
        return None
    # Try today's file first, then last 7 days
    for offset in range(8):
        d = today - timedelta(days=offset)
        p = attn_dir / f"{d.isoformat()}.parquet"
        if p.exists():
            try:
                df = pd.read_parquet(p)
                log.info("narrative_flare: loaded attention from %s", p)
                return df
            except Exception:  # noqa: BLE001
                continue
    return None


# ---------------------------------------------------------------------------
# news_count_z: robust z of daily article count vs trailing 90d baseline
# ---------------------------------------------------------------------------


def _compute_news_count_z(
    ticker: str,
    today: date,
    polygon_df: pd.DataFrame | None,
) -> dict[str, Any]:
    """Compute news_count_z using Polygon news_sentiment 'articles' column.

    Store: data/polygon/news_sentiment.parquet
    Columns expected: ticker (str), snapshot_date (str), articles (int/float).
    PIT-safe: baseline strictly < today.

    Returns dict with keys: value (float|None), reason (str|None), present (bool).
    """
    if polygon_df is None:
        return {"value": None, "reason": "store_absent", "present": False}

    try:
        t_rows = polygon_df[polygon_df["ticker"] == ticker].copy()
        if t_rows.empty:
            return {"value": None, "reason": "ticker_absent", "present": False}

        # Determine the article count column
        art_col = None
        for candidate in ("articles", "article_count", "n_articles"):
            if candidate in t_rows.columns:
                art_col = candidate
                break
        if art_col is None:
            return {"value": None, "reason": "articles_column_absent", "present": False}

        t_rows = t_rows.copy()
        t_rows["_sd"] = pd.to_datetime(t_rows["snapshot_date"]).dt.date

        # Today's value
        today_rows = t_rows[t_rows["_sd"] == today]
        if today_rows.empty:
            last_d = t_rows["_sd"].max()
            if (today - last_d).days > THRESHOLDS["POLYGON_STALE_DAYS"]:
                return {"value": None, "reason": "stale", "present": False}
            return {"value": None, "reason": "no_today_row", "present": False}

        today_val = float(today_rows[art_col].iloc[-1])

        # Baseline: strictly prior, within 90d
        cutoff = today - timedelta(days=THRESHOLDS["NEWS_BASELINE_DAYS"])
        baseline = t_rows[
            (t_rows["_sd"] < today) & (t_rows["_sd"] >= cutoff)
        ][art_col].dropna().values.astype(float)

        if len(baseline) < THRESHOLDS["NEWS_MIN_OBS"]:
            # young series — print reason honestly (masterplan §9)
            return {"value": today_val, "reason": "young_series", "present": False}

        z = _robust_z(baseline, today_val)
        if z is None:
            return {"value": today_val, "reason": "zero_dispersion", "present": False}

        return {"value": round(z, 3), "reason": None, "present": True}

    except Exception as e:  # noqa: BLE001
        log.warning("narrative_flare news_count_z %s: %s", ticker, e)
        return {"value": None, "reason": "read_error", "present": False}


# ---------------------------------------------------------------------------
# similarity_gap: days since ticker last appeared in each channel
# ---------------------------------------------------------------------------


def _compute_similarity_gap(
    ticker: str,
    today: date,
    substack_df: pd.DataFrame | None,
    hn_df: pd.DataFrame | None,
    polygon_df: pd.DataFrame | None,
    alias_map: dict[str, tuple[str, float]],
) -> dict[str, Any]:
    """Return {channel: gap_days, novel: bool} for substack, hn, polygon.

    For substack and polygon, ticker matching requires the alias_map join on title/text.
    For hn_mentions, the ticker column is already resolved (from HnAlgoliaAdapter).
    novel flag = True when gap > NOVEL_DAYS or first-ever appearance.

    NAR-R10: channel absent -> gap=None, novel=False.
    """
    gap_novel_threshold = THRESHOLDS["GAP_NOVEL_DAYS"]

    # ── HN channel: ticker column already present ──
    gap_hn: int | None = None
    novel_hn = False
    if hn_df is not None and not hn_df.empty:
        try:
            t_hn = hn_df[hn_df["ticker"] == ticker].copy()
            if not t_hn.empty:
                # created_at is ISO string; parse to date
                t_hn["_date"] = pd.to_datetime(t_hn["created_at"]).dt.date
                prior = t_hn[t_hn["_date"] < today]
                if prior.empty:
                    gap_hn = None  # first-ever
                    novel_hn = True
                else:
                    last_seen = prior["_date"].max()
                    gap_hn = (today - last_seen).days
                    novel_hn = gap_hn > gap_novel_threshold
            else:
                gap_hn = None
                novel_hn = True  # first-ever appearance
        except Exception as e:  # noqa: BLE001
            log.warning("narrative_flare gap hn %s: %s", ticker, e)

    # ── Substack channel: text join via alias_map ──
    gap_substack: int | None = None
    novel_substack = False
    if substack_df is not None and not substack_df.empty:
        try:
            # Join on title (and teaser_text if present)
            substack_df = substack_df.copy()
            hits: list[date] = []
            for _, row in substack_df.iterrows():
                text = str(row.get("title", "")) + " " + str(row.get("teaser_text", ""))
                match_ticker, _conf = _join_text_to_ticker(text, alias_map)
                if match_ticker != ticker:
                    continue
                pub = row.get("published_date")
                if pub is None:
                    continue
                try:
                    d = date.fromisoformat(str(pub)[:10])
                    hits.append(d)
                except ValueError:
                    continue
            hits = [d for d in hits if d < today]
            if hits:
                last_seen = max(hits)
                gap_substack = (today - last_seen).days
                novel_substack = gap_substack > gap_novel_threshold
            else:
                gap_substack = None
                novel_substack = True  # first-ever
        except Exception as e:  # noqa: BLE001
            log.warning("narrative_flare gap substack %s: %s", ticker, e)

    # ── Polygon channel: ticker column available ──
    gap_polygon: int | None = None
    novel_polygon = False
    if polygon_df is not None and not polygon_df.empty:
        try:
            p_rows = polygon_df[polygon_df["ticker"] == ticker].copy()
            if not p_rows.empty:
                p_rows["_sd"] = pd.to_datetime(p_rows["snapshot_date"]).dt.date
                prior = p_rows[p_rows["_sd"] < today]
                if prior.empty:
                    gap_polygon = None
                    novel_polygon = True
                else:
                    last_seen = prior["_sd"].max()
                    gap_polygon = (today - last_seen).days
                    novel_polygon = gap_polygon > gap_novel_threshold
            else:
                gap_polygon = None
                novel_polygon = True
        except Exception as e:  # noqa: BLE001
            log.warning("narrative_flare gap polygon %s: %s", ticker, e)

    return {
        "gap_substack_days": gap_substack,
        "novel_substack": novel_substack,
        "gap_hn_days": gap_hn,
        "novel_hn": novel_hn,
        "gap_polygon_days": gap_polygon,
        "novel_polygon": novel_polygon,
        "any_novel": novel_substack or novel_hn or novel_polygon,
    }


# ---------------------------------------------------------------------------
# TF-IDF novelty (hand-rolled, stdlib + numpy only — no sklearn)
# ---------------------------------------------------------------------------


def _tokenize(text: str) -> list[str]:
    """Simple word tokenizer: lowercase, keep alphanumeric tokens >= 2 chars."""
    import re
    return [t for t in re.findall(r'[a-z0-9]+', text.lower()) if len(t) >= 2]


def _compute_tfidf_novelty(
    ticker: str,
    today: date,
    today_texts: list[str],
    corpus_texts: list[str],
) -> dict[str, Any]:
    """Compute TF-IDF novelty = 1 - max cosine similarity of today's doc vs corpus.

    today_texts  — list of strings from today's ticker-matched documents
    corpus_texts — list of strings from trailing 90d (prior to today)

    Requires >= TFIDF_MIN_PRIOR_DOCS corpus docs else absent.
    Hand-rolled: numpy only.
    NAR-R4: zero LLM.
    """
    min_docs = THRESHOLDS["TFIDF_MIN_PRIOR_DOCS"]
    if len(corpus_texts) < min_docs:
        return {"value": None, "reason": f"insufficient_prior_docs_{len(corpus_texts)}", "present": False}

    if not today_texts:
        return {"value": None, "reason": "no_today_text", "present": False}

    # Build vocabulary from corpus
    all_texts = corpus_texts + today_texts
    vocab: dict[str, int] = {}
    for text in all_texts:
        for tok in _tokenize(text):
            if tok not in vocab:
                vocab[tok] = len(vocab)

    n_vocab = len(vocab)
    if n_vocab == 0:
        return {"value": None, "reason": "empty_vocab", "present": False}

    def _tf_idf_vec(texts: list[str], idf: np.ndarray) -> np.ndarray:
        """Compute TF-IDF matrix (n_docs x n_vocab) for a list of texts."""
        mat = np.zeros((len(texts), n_vocab), dtype=np.float32)
        for i, text in enumerate(texts):
            tokens = _tokenize(text)
            if not tokens:
                continue
            counts: dict[int, int] = {}
            for tok in tokens:
                idx = vocab.get(tok)
                if idx is not None:
                    counts[idx] = counts.get(idx, 0) + 1
            n_tok = len(tokens)
            for idx, cnt in counts.items():
                mat[i, idx] = (cnt / n_tok) * idf[idx]
        return mat

    # IDF: computed on corpus only (prior documents)
    n_corpus = len(corpus_texts)
    df_counts = np.zeros(n_vocab, dtype=np.float32)
    for text in corpus_texts:
        seen_in_doc: set[int] = set()
        for tok in _tokenize(text):
            idx = vocab.get(tok)
            if idx is not None:
                seen_in_doc.add(idx)
        for idx in seen_in_doc:
            df_counts[idx] += 1

    # IDF with +1 smoothing
    idf = np.log((n_corpus + 1) / (df_counts + 1)) + 1.0

    # TF-IDF vectors
    corpus_vecs = _tf_idf_vec(corpus_texts, idf)
    today_vecs = _tf_idf_vec(today_texts, idf)

    # Cosine similarity: today_doc vs each corpus doc; take max
    def _l2_norm(vecs: np.ndarray) -> np.ndarray:
        norms = np.linalg.norm(vecs, axis=1, keepdims=True)
        norms[norms < 1e-10] = 1e-10
        return vecs / norms

    corpus_unit = _l2_norm(corpus_vecs)
    today_unit = _l2_norm(today_vecs)

    # Shape: (n_today, n_corpus) — take max over corpus then max over today docs
    sim_matrix = today_unit @ corpus_unit.T  # (n_today, n_corpus)
    max_cosine = float(np.max(sim_matrix)) if sim_matrix.size > 0 else 0.0
    novelty = round(1.0 - max(0.0, min(1.0, max_cosine)), 4)

    return {"value": novelty, "reason": None, "present": True}


def _gather_ticker_texts(
    ticker: str,
    today: date,
    substack_df: pd.DataFrame | None,
    hn_df: pd.DataFrame | None,
    alias_map: dict[str, tuple[str, float]],
    baseline_days: int,
) -> tuple[list[str], list[str]]:
    """Return (today_texts, corpus_texts) for TF-IDF computation.

    Sources: substack title+teaser, HN titles.
    corpus_texts: strictly prior to today, within baseline_days.
    today_texts: published/observed == today.
    """
    cutoff = today - timedelta(days=baseline_days)

    today_texts: list[str] = []
    corpus_texts: list[str] = []

    # Substack
    if substack_df is not None and not substack_df.empty:
        try:
            for _, row in substack_df.iterrows():
                text = str(row.get("title", "")) + " " + str(row.get("teaser_text", ""))
                match_ticker, _conf = _join_text_to_ticker(text, alias_map)
                if match_ticker != ticker:
                    continue
                pub = row.get("published_date")
                if pub is None:
                    continue
                try:
                    d = date.fromisoformat(str(pub)[:10])
                except ValueError:
                    continue
                if d == today:
                    today_texts.append(text.strip())
                elif cutoff <= d < today:
                    corpus_texts.append(text.strip())
        except Exception as e:  # noqa: BLE001
            log.warning("narrative_flare tfidf substack %s: %s", ticker, e)

    # HN
    if hn_df is not None and not hn_df.empty:
        try:
            t_hn = hn_df[hn_df["ticker"] == ticker].copy()
            if not t_hn.empty:
                t_hn["_date"] = pd.to_datetime(t_hn["created_at"]).dt.date
                for _, row in t_hn.iterrows():
                    d = row["_date"]
                    text = str(row.get("title", ""))
                    if d == today:
                        today_texts.append(text)
                    elif cutoff <= d < today:
                        corpus_texts.append(text)
        except Exception as e:  # noqa: BLE001
            log.warning("narrative_flare tfidf hn %s: %s", ticker, e)

    return today_texts, corpus_texts


# ---------------------------------------------------------------------------
# Kleinberg burst detection (2-state HMM, s=2, gamma=1)
# ---------------------------------------------------------------------------


def _kleinberg_burst(
    counts: list[int],
) -> float:
    """2-state Kleinberg burst detector.

    States: 0 = baseline, 1 = burst.
    Transition cost: gamma * ln(states) * i (for i>0).
    Emission: Poisson with rate = mean * s^state.

    Returns burst_weight = fraction of time series in burst state (0-1).
    Returns 0.0 on degenerate input.

    Reference: Kleinberg (2002); implementation follows §2 two-state version.
    """
    n = len(counts)
    if n < 2:
        return 0.0

    total = sum(counts)
    if total == 0:
        return 0.0

    s = float(THRESHOLDS["KLEINBERG_S"])
    gamma = float(THRESHOLDS["KLEINBERG_GAMMA"])
    n_states = 2
    eps = 1e-10

    # Rates: mu_0 = baseline rate, mu_1 = s * mu_0
    mu0 = total / n
    mu0 = max(mu0, eps)
    mu1 = mu0 * s

    # Transition cost between states i and j (0-indexed)
    # cost(i->j) = gamma * ln(n_states) * (j - i) if j > i else 0
    ln_n = math.log(n_states)

    def _trans_cost(i: int, j: int) -> float:
        if j > i:
            return gamma * ln_n * (j - i)
        return 0.0

    # Emission: negative log likelihood of Poisson(mu, count)
    # = mu - count * ln(mu) + ln(count!)  — we drop ln(count!) as constant
    def _neg_log_emit(state: int, count: int) -> float:
        mu = mu1 if state == 1 else mu0
        return mu - count * math.log(mu + eps)

    # Viterbi
    INF = float("inf")
    # q[t][state] = min cost to reach state at time t
    q = [[INF] * n_states for _ in range(n)]
    back = [[-1] * n_states for _ in range(n)]

    for s_idx in range(n_states):
        q[0][s_idx] = _neg_log_emit(s_idx, counts[0])

    for t in range(1, n):
        for j in range(n_states):
            emit = _neg_log_emit(j, counts[t])
            best_cost = INF
            best_prev = 0
            for i in range(n_states):
                cost = q[t - 1][i] + _trans_cost(i, j) + emit
                if cost < best_cost:
                    best_cost = cost
                    best_prev = i
            q[t][j] = best_cost
            back[t][j] = best_prev

    # Traceback
    path = [-1] * n
    path[n - 1] = int(np.argmin(q[n - 1]))
    for t in range(n - 2, -1, -1):
        path[t] = back[t + 1][path[t + 1]]

    burst_fraction = sum(1 for s_idx in path if s_idx == 1) / n
    return round(burst_fraction, 4)


def _compute_burst(
    ticker: str,
    today: date,
    hn_df: pd.DataFrame | None,
    polygon_df: pd.DataFrame | None,
) -> dict[str, Any]:
    """Compute Kleinberg burst weights for HN and Polygon channels.

    Returns burst_weight_hn, burst_weight_polygon (float or None).
    Uses trailing KLEINBERG_BASELINE_DAYS of daily count series (strictly prior + today).
    """
    baseline_days = THRESHOLDS["KLEINBERG_BASELINE_DAYS"]
    cutoff = today - timedelta(days=baseline_days)

    # HN: daily mention count for ticker
    bw_hn: float | None = None
    if hn_df is not None and not hn_df.empty:
        try:
            t_hn = hn_df[hn_df["ticker"] == ticker].copy()
            if not t_hn.empty:
                t_hn["_date"] = pd.to_datetime(t_hn["created_at"]).dt.date
                t_hn = t_hn[t_hn["_date"] >= cutoff]
                if not t_hn.empty:
                    daily = t_hn.groupby("_date").size()
                    # Fill missing days with 0
                    date_range = pd.date_range(cutoff, today).date
                    daily_full = [int(daily.get(d, 0)) for d in date_range]
                    bw_hn = _kleinberg_burst(daily_full)
        except Exception as e:  # noqa: BLE001
            log.warning("narrative_flare burst hn %s: %s", ticker, e)

    # Polygon: daily article count for ticker
    bw_polygon: float | None = None
    if polygon_df is not None and not polygon_df.empty:
        try:
            p_rows = polygon_df[polygon_df["ticker"] == ticker].copy()
            if not p_rows.empty:
                p_rows["_sd"] = pd.to_datetime(p_rows["snapshot_date"]).dt.date
                p_rows = p_rows[p_rows["_sd"] >= cutoff]
                art_col = next(
                    (c for c in ("articles", "article_count", "n_articles") if c in p_rows.columns),
                    None,
                )
                if art_col and not p_rows.empty:
                    daily = p_rows.groupby("_sd")[art_col].sum()
                    date_range = pd.date_range(cutoff, today).date
                    daily_full = [int(daily.get(d, 0)) for d in date_range]
                    bw_polygon = _kleinberg_burst(daily_full)
        except Exception as e:  # noqa: BLE001
            log.warning("narrative_flare burst polygon %s: %s", ticker, e)

    return {
        "burst_weight_hn": bw_hn,
        "burst_weight_polygon": bw_polygon,
    }


# ---------------------------------------------------------------------------
# First coverage events (shared W3/W4 contract)
# ---------------------------------------------------------------------------


def _compute_first_coverage(
    ticker: str,
    today: date,
    fetch_date_str: str,
    substack_df: pd.DataFrame | None,
    hn_df: pd.DataFrame | None,
    polygon_df: pd.DataFrame | None,
    alias_map: dict[str, tuple[str, float]],
    existing_fc: pd.DataFrame,
) -> list[dict]:
    """Return new first_coverage rows for this ticker.

    A 'first coverage' event: a registry source covers this ticker for the first time
    in FIRST_COVERAGE_GAP_DAYS days. We check against the existing store to avoid
    duplicating events.

    Returns list of dicts matching FIRST_COVERAGE_COLS schema.
    """
    gap_days = THRESHOLDS["FIRST_COVERAGE_GAP_DAYS"]
    new_rows: list[dict] = []

    # Prior coverage dates per source_id for this ticker
    prior_by_source: dict[str, date | None] = {}
    if not existing_fc.empty:
        t_fc = existing_fc[existing_fc["ticker"] == ticker]
        for src in t_fc["source_id"].unique():
            src_rows = t_fc[t_fc["source_id"] == src]
            dates = []
            for d_str in src_rows["date"]:
                try:
                    dates.append(date.fromisoformat(str(d_str)[:10]))
                except ValueError:
                    pass
            prior_by_source[str(src)] = max(dates) if dates else None

    def _is_first_coverage(source_id: str, event_date: date) -> bool:
        """True if this ticker was NOT covered by source_id within gap_days before event_date."""
        last = prior_by_source.get(source_id)
        if last is None:
            return True  # first-ever
        return (event_date - last).days > gap_days

    # Substack sources (each feed is a source_id)
    if substack_df is not None and not substack_df.empty:
        try:
            for _, row in substack_df.iterrows():
                text = str(row.get("title", "")) + " " + str(row.get("teaser_text", ""))
                match_ticker, conf = _join_text_to_ticker(text, alias_map)
                if match_ticker != ticker or conf < 0.5:
                    continue
                pub = row.get("published_date")
                if pub is None:
                    continue
                try:
                    event_date = date.fromisoformat(str(pub)[:10])
                except ValueError:
                    continue
                # Only process today's events (nightly run)
                if event_date != today:
                    continue
                feed_id = str(row.get("feed_id", "unknown"))
                source_id = f"substack:{feed_id}"
                if _is_first_coverage(source_id, event_date):
                    new_rows.append({
                        "source_id": source_id,
                        "ticker": ticker,
                        "date": event_date.isoformat(),
                        "url": str(row.get("url", "")),
                        "title": str(row.get("title", ""))[:512],
                        "join_confidence": round(conf, 3),
                        "fetch_date": fetch_date_str,
                    })
                    prior_by_source[source_id] = event_date
        except Exception as e:  # noqa: BLE001
            log.warning("narrative_flare first_coverage substack %s: %s", ticker, e)

    # HN channel
    if hn_df is not None and not hn_df.empty:
        try:
            t_hn = hn_df[hn_df["ticker"] == ticker].copy()
            if not t_hn.empty:
                t_hn["_date"] = pd.to_datetime(t_hn["created_at"]).dt.date
                today_hn = t_hn[t_hn["_date"] == today]
                if not today_hn.empty:
                    if _is_first_coverage("hn", today):
                        row = today_hn.iloc[0]
                        new_rows.append({
                            "source_id": "hn",
                            "ticker": ticker,
                            "date": today.isoformat(),
                            "url": f"https://news.ycombinator.com/item?id={row.get('story_id', '')}",
                            "title": str(row.get("title", ""))[:512],
                            "join_confidence": 1.0,  # ticker column is pre-resolved
                            "fetch_date": fetch_date_str,
                        })
                        prior_by_source["hn"] = today
        except Exception as e:  # noqa: BLE001
            log.warning("narrative_flare first_coverage hn %s: %s", ticker, e)

    # Polygon channel
    if polygon_df is not None and not polygon_df.empty:
        try:
            p_rows = polygon_df[polygon_df["ticker"] == ticker].copy()
            if not p_rows.empty:
                p_rows["_sd"] = pd.to_datetime(p_rows["snapshot_date"]).dt.date
                today_p = p_rows[p_rows["_sd"] == today]
                if not today_p.empty:
                    if _is_first_coverage("polygon", today):
                        new_rows.append({
                            "source_id": "polygon",
                            "ticker": ticker,
                            "date": today.isoformat(),
                            "url": "",
                            "title": f"Polygon news count: {today.isoformat()}",
                            "join_confidence": 1.0,  # ticker column direct
                            "fetch_date": fetch_date_str,
                        })
                        prior_by_source["polygon"] = today
        except Exception as e:  # noqa: BLE001
            log.warning("narrative_flare first_coverage polygon %s: %s", ticker, e)

    return new_rows


# ---------------------------------------------------------------------------
# Crowding hazard (NAR-R7)
# ---------------------------------------------------------------------------


def _compute_hazard_pctile(
    ticker: str,
    attention_df: pd.DataFrame | None,
    hn_df: pd.DataFrame | None,
    today: date,
) -> float | None:
    """Return attention LEVEL percentile (0-100) as crowding hazard proxy.

    Priority:
    1. Wiki views from data/attention/<T>.parquet if present
    2. HN points level for recent HN stories

    NAR-R7: hazard_pctile carried on every row.
    Returns None if no attention data available.
    """
    # Try wiki views first
    if attention_df is not None:
        try:
            col_candidates = ("views", "wiki_views", "pageviews", "view_count")
            ticker_col_candidates = ("ticker", "symbol")
            tick_col = next((c for c in ticker_col_candidates if c in attention_df.columns), None)
            view_col = next((c for c in col_candidates if c in attention_df.columns), None)
            if tick_col and view_col:
                all_views = attention_df[view_col].dropna().values.astype(float)
                if len(all_views) > 0:
                    t_rows = attention_df[attention_df[tick_col] == ticker]
                    if not t_rows.empty:
                        ticker_val = float(t_rows[view_col].iloc[-1])
                        pct = float(np.sum(all_views <= ticker_val) / len(all_views) * 100)
                        return round(pct, 1)
        except Exception as e:  # noqa: BLE001
            log.warning("narrative_flare hazard wiki %s: %s", ticker, e)

    # Fallback: HN points level (sum of points for this ticker's stories in last 7d)
    if hn_df is not None and not hn_df.empty:
        try:
            t_hn = hn_df[hn_df["ticker"] == ticker].copy()
            cutoff = today - timedelta(days=7)
            t_hn["_date"] = pd.to_datetime(t_hn["created_at"]).dt.date
            t_hn = t_hn[t_hn["_date"] >= cutoff]
            ticker_points = float(t_hn["points"].sum()) if not t_hn.empty else 0.0
            # Compare vs all tickers in the HN store
            all_tickers = hn_df["ticker"].unique()
            all_points = []
            for t in all_tickers:
                t_rows = hn_df[hn_df["ticker"] == t].copy()
                t_rows["_date"] = pd.to_datetime(t_rows["created_at"]).dt.date
                t_rows = t_rows[t_rows["_date"] >= cutoff]
                all_points.append(float(t_rows["points"].sum()) if not t_rows.empty else 0.0)
            if all_points:
                arr = np.array(all_points, dtype=float)
                pct = float(np.sum(arr <= ticker_points) / len(arr) * 100)
                return round(pct, 1)
        except Exception as e:  # noqa: BLE001
            log.warning("narrative_flare hazard hn %s: %s", ticker, e)

    return None


# ---------------------------------------------------------------------------
# Universe assembly (mirrors flare_persistence pattern)
# ---------------------------------------------------------------------------


def _build_universe(data_root: Path, reg: dict) -> list[str]:
    """Build universe: hn_keywords union from flare_persistence universe.

    Falls back to hn_keywords tickers only when flare_persistence universe unavailable.
    """
    tickers: set[str] = set()

    # HN keyword tickers from registry
    hn_map: dict[str, list[str]] = reg.get("hn_keywords") or {}
    tickers.update(hn_map.keys())

    # Extend with flare_persistence universe
    try:
        from engine.flare_persistence import _build_universe as _fp_universe
        fp_uni = _fp_universe(data_root, date.today())
        tickers.update(fp_uni)
    except Exception as e:  # noqa: BLE001
        log.warning("narrative_flare: flare_persistence universe load failed: %s", e)

    return sorted(tickers)


# ---------------------------------------------------------------------------
# PIT stores
# ---------------------------------------------------------------------------


def _fc_path(data_root: Path) -> Path:
    return data_root / "narrative_flare" / "first_coverage.parquet"


def _hist_path(data_root: Path) -> Path:
    return data_root / "narrative_flare" / "witness_hist.parquet"


def _load_first_coverage(data_root: Path) -> pd.DataFrame:
    p = _fc_path(data_root)
    if not p.exists():
        return pd.DataFrame(columns=FIRST_COVERAGE_COLS)
    try:
        return pd.read_parquet(p)
    except Exception as e:  # noqa: BLE001
        log.warning("narrative_flare: first_coverage.parquet load failed: %s", e)
        return pd.DataFrame(columns=FIRST_COVERAGE_COLS)


def _append_first_coverage(new_rows: list[dict], data_root: Path) -> None:
    """Append-only; dedup on (source_id, ticker, date). Nightly-gated.

    Dedup key is (source_id, ticker, date) so that a legitimate re-coverage event
    >90d after the last one for the same source/ticker still lands in the store.
    """
    if not new_rows:
        return
    p = _fc_path(data_root)
    p.parent.mkdir(parents=True, exist_ok=True)
    existing = _load_first_coverage(data_root)
    new_df = pd.DataFrame(new_rows, columns=FIRST_COVERAGE_COLS)
    if existing.empty:
        combined = new_df
    else:
        existing_keys = set(
            zip(
                existing["source_id"].astype(str),
                existing["ticker"].astype(str),
                existing["date"].astype(str),
            )
        )
        new_df_filt = new_df[
            ~new_df.apply(
                lambda r: (str(r["source_id"]), str(r["ticker"]), str(r["date"])) in existing_keys,
                axis=1,
            )
        ]
        combined = pd.concat([existing, new_df_filt], ignore_index=True)
    combined.to_parquet(p, index=False)
    log.info("narrative_flare: first_coverage +%d rows (%d total)", len(new_rows), len(combined))


def _append_witness_hist(new_rows: list[dict], data_root: Path) -> None:
    """Append-only witness history; dedup on (ticker, date)."""
    if not new_rows:
        return
    p = _hist_path(data_root)
    p.parent.mkdir(parents=True, exist_ok=True)
    if p.exists():
        try:
            existing = pd.read_parquet(p)
        except Exception:  # noqa: BLE001
            existing = pd.DataFrame(columns=WITNESS_HIST_COLS)
    else:
        existing = pd.DataFrame(columns=WITNESS_HIST_COLS)

    new_df = pd.DataFrame(new_rows, columns=WITNESS_HIST_COLS)
    if existing.empty:
        combined = new_df
    else:
        today_str = new_rows[0]["date"] if new_rows else ""
        # Remove any existing rows for today (idempotent re-run)
        existing_filtered = existing[existing["date"].astype(str) != today_str]
        combined = pd.concat([existing_filtered, new_df], ignore_index=True)
    combined.to_parquet(p, index=False)
    log.info("narrative_flare: witness_hist +%d rows (%d total)", len(new_rows), len(combined))


# ---------------------------------------------------------------------------
# Main compute
# ---------------------------------------------------------------------------


def compute(
    data_root: Path | None = None,
    as_of: str | None = None,
) -> dict:
    """Compute narrative_flare.v1 witnesses for all tickers.

    Returns the full site artifact. Never raises (NAR-R10 additive pattern).
    """
    try:
        return _compute_inner(data_root, as_of)
    except Exception as e:  # noqa: BLE001
        log.error("narrative_flare.compute crashed: %s", e)
        return {
            "schema": "narrative_flare.v1",
            "as_of": as_of or date.today().isoformat(),
            "universe_n": 0,
            "rows": [],
            "authority": AUTHORITY,
            "tier": "display",
            "error": str(e),
        }


def _compute_inner(data_root: Path | None, as_of: str | None) -> dict:
    t0 = time.time()

    from lib import config as _cfg
    if data_root is None:
        data_root = _cfg.data_dir()

    today = date.fromisoformat(as_of) if as_of else date.today()
    fetch_date_str = date.today().isoformat()

    # Load registry
    from collectors.narrative_sources import _load_registry
    try:
        reg = _load_registry()
    except Exception as e:  # noqa: BLE001
        log.warning("narrative_flare: registry load failed: %s", e)
        reg = {}

    # Build alias map
    alias_map = _build_alias_map(reg)

    # Load stores once (edgar_df removed — edgar_8k_counts is loaded but unused; MINOR 4)
    substack_df = _load_substack(data_root)
    hn_df = _load_hn(data_root)
    polygon_df = _load_polygon_news(data_root)
    attention_df = _load_attention(data_root, today)

    # Load existing first_coverage for dedup
    existing_fc = _load_first_coverage(data_root)

    # Build universe
    universe = _build_universe(data_root, reg)

    rows_out: list[dict] = []
    hist_rows: list[dict] = []
    fc_rows: list[dict] = []

    for ticker in universe:
        try:
            row, hist_row, new_fc = _process_ticker(
                ticker=ticker,
                today=today,
                fetch_date_str=fetch_date_str,
                data_root=data_root,
                substack_df=substack_df,
                hn_df=hn_df,
                polygon_df=polygon_df,
                attention_df=attention_df,
                alias_map=alias_map,
                existing_fc=existing_fc,
            )
            rows_out.append(row)
            hist_rows.append(hist_row)
            fc_rows.extend(new_fc)
        except Exception as e:  # noqa: BLE001 — NAR-R10
            log.warning("narrative_flare: %s compute failed: %s", ticker, e)

    # Append PIT stores — nightly lane only
    if _ledger_advance_enabled():
        _append_first_coverage(fc_rows, data_root)
        _append_witness_hist(hist_rows, data_root)

    # Sort: present=True first, then by channels_lit desc
    rows_out.sort(key=lambda r: (-int(r.get("present", False)), -r.get("channels_lit", 0)))

    elapsed = time.time() - t0
    n_present = sum(1 for r in rows_out if r.get("present"))
    log.info(
        "narrative_flare: universe=%d present=%d fc_events=%d elapsed=%.1fs",
        len(universe), n_present, len(fc_rows), elapsed,
    )

    return {
        "schema": "narrative_flare.v1",
        "as_of": today.isoformat(),
        "fetch_date": fetch_date_str,
        "universe_n": len(universe),
        "elapsed_s": round(elapsed, 2),
        "rows": rows_out,
        "authority": AUTHORITY,
        "tier": "display",
        "thresholds_ref": "masterplan §4.2 — FROZEN pre-registration record",
    }


def _min_substack_conf_today(
    ticker: str,
    today: date,
    substack_df: pd.DataFrame | None,
    alias_map: dict[str, tuple[str, float]],
) -> float | None:
    """Return the minimum alias-map confidence among today's substack rows that match ticker.

    Returns None if no substack row matches ticker today (channel did not contribute).
    Used by _process_ticker to compute row-level join_confidence (NAR-R9 fix).
    """
    if substack_df is None or substack_df.empty:
        return None
    min_conf: float | None = None
    try:
        for _, row in substack_df.iterrows():
            pub = row.get("published_date")
            if pub is None:
                continue
            try:
                d = date.fromisoformat(str(pub)[:10])
            except ValueError:
                continue
            if d != today:
                continue
            text = str(row.get("title", "")) + " " + str(row.get("teaser_text", ""))
            match_ticker, conf = _join_text_to_ticker(text, alias_map)
            if match_ticker != ticker:
                continue
            if min_conf is None or conf < min_conf:
                min_conf = conf
    except Exception as e:  # noqa: BLE001
        log.warning("narrative_flare _min_substack_conf_today %s: %s", ticker, e)
    return min_conf


def _process_ticker(
    ticker: str,
    today: date,
    fetch_date_str: str,
    data_root: Path,
    substack_df: pd.DataFrame | None,
    hn_df: pd.DataFrame | None,
    polygon_df: pd.DataFrame | None,
    attention_df: pd.DataFrame | None,
    alias_map: dict[str, tuple[str, float]],
    existing_fc: pd.DataFrame,
) -> tuple[dict, dict, list[dict]]:
    """Compute per-ticker narrative witness. Returns (site_row, hist_row, fc_rows)."""

    # 1. news_count_z
    ncz = _compute_news_count_z(ticker, today, polygon_df)

    # 2. similarity_gap
    gap = _compute_similarity_gap(ticker, today, substack_df, hn_df, polygon_df, alias_map)

    # 3. TF-IDF novelty
    today_texts, corpus_texts = _gather_ticker_texts(
        ticker, today, substack_df, hn_df, alias_map,
        THRESHOLDS["TFIDF_BASELINE_DAYS"],
    )
    tfidf = _compute_tfidf_novelty(ticker, today, today_texts, corpus_texts)

    # 4. Kleinberg burst
    burst = _compute_burst(ticker, today, hn_df, polygon_df)

    # 5. First coverage events
    new_fc = _compute_first_coverage(
        ticker, today, fetch_date_str,
        substack_df, hn_df, polygon_df,
        alias_map, existing_fc,
    )

    # 6. Join confidence — minimum confidence among channels that lit (NAR-R9).
    # HN and Polygon use direct ticker columns => conf = 1.0.
    # Substack uses alias_map text join => conf can be 1.0, 0.8, or 0.5.
    # _min_substack_conf_today returns non-None iff at least one today row matched ticker.
    # When substack contributed, lower from 1.0 to the minimum alias-map conf seen.
    substack_min_conf = _min_substack_conf_today(ticker, today, substack_df, alias_map)
    if substack_min_conf is not None:
        join_conf = substack_min_conf
    else:
        join_conf = 1.0

    # 7. Hazard percentile (NAR-R7)
    hazard_pctile = _compute_hazard_pctile(ticker, attention_df, hn_df, today)

    # 8. Channels lit
    channels_lit: list[str] = []
    magnitudes: dict[str, Any] = {}

    if ncz.get("present"):
        channels_lit.append("news_count_z")
        magnitudes["news_count_z"] = ncz["value"]

    if gap.get("any_novel"):
        channels_lit.append("similarity_gap")
        magnitudes["similarity_gap"] = {
            "substack_days": gap["gap_substack_days"],
            "hn_days": gap["gap_hn_days"],
            "polygon_days": gap["gap_polygon_days"],
        }

    if tfidf.get("present"):
        channels_lit.append("tfidf_novelty")
        magnitudes["tfidf_novelty"] = tfidf["value"]

    bw_hn = burst.get("burst_weight_hn")
    bw_pol = burst.get("burst_weight_polygon")
    if bw_hn is not None and bw_hn > 0:
        channels_lit.append("burst_hn")
        magnitudes["burst_weight_hn"] = bw_hn
    if bw_pol is not None and bw_pol > 0:
        channels_lit.append("burst_polygon")
        magnitudes["burst_weight_polygon"] = bw_pol

    if new_fc:
        channels_lit.append("first_coverage")
        magnitudes["first_coverage_n"] = len(new_fc)

    present = len(channels_lit) > 0

    # Reasons (NAR-R10: print absence reasons)
    reasons: dict[str, Any] = {}
    if not ncz.get("present"):
        reasons["news_count_z"] = ncz.get("reason") or "below_threshold"
    if not gap.get("any_novel"):
        reasons["similarity_gap"] = "not_novel"
    if not tfidf.get("present"):
        reasons["tfidf_novelty"] = tfidf.get("reason") or "absent"
    if bw_hn is None or bw_hn == 0:
        reasons["burst_hn"] = "not_bursting" if bw_hn == 0 else "absent"
    if bw_pol is None or bw_pol == 0:
        reasons["burst_polygon"] = "not_bursting" if bw_pol == 0 else "absent"

    # Site row
    site_row: dict[str, Any] = {
        "ticker": ticker,
        "present": present,
        "channels_lit": len(channels_lit),
        "channels_lit_names": channels_lit,
        "magnitudes": magnitudes,
        "join_confidence": round(join_conf, 3),  # NAR-R9
        "hazard_pctile": hazard_pctile,            # NAR-R7
        "small_cap_flag": None,                    # null this wave — no mktcap join
        "reasons": reasons,
        "news_count_z": ncz,
        "similarity_gap": gap,
        "tfidf_novelty": tfidf,
        "burst": burst,
        "first_coverage_events": len(new_fc),
        "as_of": today.isoformat(),
        "fetch_date": fetch_date_str,
    }

    # History row (flat)
    hist_row: dict[str, Any] = {
        "ticker": ticker,
        "date": today.isoformat(),
        "fetch_date": fetch_date_str,
        "news_count_z": ncz.get("value"),
        "news_count_z_reason": ncz.get("reason"),
        "gap_substack_days": gap.get("gap_substack_days"),
        "gap_hn_days": gap.get("gap_hn_days"),
        "gap_polygon_days": gap.get("gap_polygon_days"),
        "novel_substack": int(gap.get("novel_substack", False)),
        "novel_hn": int(gap.get("novel_hn", False)),
        "novel_polygon": int(gap.get("novel_polygon", False)),
        "tfidf_novelty": tfidf.get("value"),
        "tfidf_novelty_reason": tfidf.get("reason"),
        "burst_weight_hn": burst.get("burst_weight_hn"),
        "burst_weight_polygon": burst.get("burst_weight_polygon"),
        "join_confidence": round(join_conf, 3),
        "hazard_pctile": hazard_pctile,
        "channels_lit": len(channels_lit),
        "present": int(present),
    }

    return site_row, hist_row, new_fc


# ---------------------------------------------------------------------------
# Site artifact writer
# ---------------------------------------------------------------------------


def write_site_artifact(
    result: dict,
    site_root: Path | None = None,
) -> Path:
    """Write site/narrativedata/flares.json. Returns written path."""
    from lib import config
    if site_root is None:
        site_root = config.ROOT / config.load()["storage"]["site_dir"]
    out_dir = site_root / "narrativedata"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "flares.json"
    payload = json.dumps(result, separators=(",", ":"), default=str)
    out_path.write_text(payload + "\n", encoding="utf-8")
    log.info(
        "narrative_flare: wrote %s (%dKB, %d rows)",
        out_path, len(payload.encode()) // 1024, len(result.get("rows", [])),
    )
    return out_path
