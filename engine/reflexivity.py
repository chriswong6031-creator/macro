"""Reflexivity overlay — board-level duplicate-exposure read (W4, Signal Commons).

Answers: "Is this candidate a NEW bet, or the same hidden trade again?"

This is a DISPLAY-ONLY, held-agnostic overlay (R-F ruling). It operates over the
board candidate set only — it cannot and does not read Mastermind bot.db holdings
(R-A ruling). The held-aware read is chartered to the Mastermind repo.

Two similarity legs (R-C ruling):
  1. Membership-Jaccard:  Jaccard(groups(c), groups(d)) over {sector} ∪ {baskets}
     This is the PRIMARY leg — deterministic, no OOS-instability, catches
     cross-basket/cross-theme hidden concentration exactly.
  2. Factor-beta cosine:  cosine(β_c, β_d) over HIGH-TIER factors ONLY:
     mkt / growth / size / rates (scope=single, persist ≥ 0.36).
     OOS-instability caveat is printed, never silently used.

Similarity = max(membership_jaccard, beta_cosine) clipped to [0, 1]  (R-C).

Earnings-week leg: wired in W-D. Annotates same-earnings-week clusters per
candidate and group as a Jaccard-adjacent annotation. Does NOT affect the
similarity matrix, N_eff, or verdicts. (R-D ruling, W-D wave)
CN/HK names: out of scope in v1. (R-E ruling)

N_eff (effective independent bets) uses the participation-ratio of the
pairwise similarity matrix eigenvalues:
    N_eff = (sum λ_i)² / sum λ_i²
This SUPERSEDES the sector-only HHI in scripts/build_stock_board_v2._concentration
(R-B ruling). The board emits ONE effective_bets number with basis labelled.

Five-candidates-one-thesis detector (W-D wave): connected components over the
pairwise similarity matrix at DUPLICATE_THRESH (0.65). Components of size ≥3
are emitted as same_thesis_groups. A board banner fires when any group size ≥5.
Display/annotation only — does NOT affect card order or any ranking (R-F).

All outputs are display-only (is_context_only=true). No behavioral consumer
may read this overlay (R-F / R7 masterplan ruling).
"""
from __future__ import annotations

import json
import logging
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np

log = logging.getLogger(__name__)

# ── constants ────────────────────────────────────────────────────────────────

SCHEMA = "reflexivity_overlay.v1"

# High-tier factors for beta cosine (R-C: scope=single, persist≥0.36).
# "rates" included (persist=0.36, scope=single, tier=medium/single).
# oil/china/usd/btc/gold are book/low scope — excluded per R-C.
# gold has persist=None (Phase-0 not run) — excluded per design doc §2a.
HIGH_TIER_FACTORS = ("mkt", "growth", "size", "rates")

FACTOR_CAVEAT = (
    "Per-name secondary betas (oil/usd/btc/gold/china) are OOS-unstable and excluded. "
    "Similarity uses high-tier factors only (mkt/growth/size/rates, scope=single). "
    "Trust the MEMBERSHIP leg more than the factor leg for individual names."
)

# R² floor below which a stock's beta vector is too thin to use.
R2_FLOOR = 0.20

# Verdict thresholds on the combined (max) similarity score.
DUPLICATE_THRESH = 0.65   # >= this → DUPLICATE (same hidden trade)
PARTIAL_THRESH   = 0.35   # >= this < DUPLICATE → PARTIAL overlap
# < PARTIAL_THRESH → NEW


# ── public API ───────────────────────────────────────────────────────────────

def build_groups_index(
    membership_data: Optional[dict],
    tickers: list[str],
    sector_by_ticker: dict[str, str],
) -> dict[str, frozenset]:
    """Build groups frozenset per ticker: {sector} ∪ {basket_ids}.

    membership_data: the parsed data/baskets/membership.json dict
                     (keys = basket_id, values = basket spec with 'members' list)
    tickers: candidate set (uppercase)
    sector_by_ticker: ticker → GICS sector string (may be absent/None)

    Returns dict[ticker → frozenset of group labels]
    """
    # Build basket_id → {tickers} from membership
    basket_members: dict[str, set[str]] = {}
    if membership_data and isinstance(membership_data.get("baskets"), dict):
        for bid, spec in membership_data["baskets"].items():
            members = spec.get("members") or []
            for m in members:
                t = (m.get("ticker") or m.get("symbol") or "").upper()
                if t:
                    basket_members.setdefault(bid, set()).add(t)

    result: dict[str, frozenset] = {}
    for tkr in tickers:
        tkr_up = tkr.upper()
        groups: set[str] = set()
        sec = sector_by_ticker.get(tkr_up) or sector_by_ticker.get(tkr)
        if sec:
            groups.add(f"sector:{sec}")
        for bid, members_set in basket_members.items():
            if tkr_up in members_set:
                groups.add(f"basket:{bid}")
        result[tkr_up] = frozenset(groups)
    return result


def membership_jaccard(groups_a: frozenset, groups_b: frozenset) -> float:
    """Jaccard similarity of two group frozensets.  Range [0, 1].
    Returns 0.0 when both are empty (no groups → no shared groups)."""
    if not groups_a and not groups_b:
        return 0.0
    union = len(groups_a | groups_b)
    if union == 0:
        return 0.0
    return len(groups_a & groups_b) / union


def factor_cosine(
    betas_a: dict,
    betas_b: dict,
    factors: tuple[str, ...] = HIGH_TIER_FACTORS,
    r2_floor: float = R2_FLOOR,
) -> tuple[float | None, str]:
    """Cosine similarity over high-tier factor betas.

    Returns (similarity, basis_flag):
      similarity: float in [0, 1], or None if either name is too thin
      basis_flag: human-readable note about coverage/quality
    """
    r2_a = betas_a.get("r2") if betas_a else None
    r2_b = betas_b.get("r2") if betas_b else None

    if r2_a is None and r2_b is None:
        return None, "beta-read-thin:both-missing"
    if r2_a is not None and r2_a < r2_floor:
        return None, f"beta-read-thin:r2={r2_a:.2f}<{r2_floor}"
    if r2_b is not None and r2_b < r2_floor:
        return None, f"beta-read-thin:r2={r2_b:.2f}<{r2_floor}"

    vals_a, vals_b = [], []
    for f in factors:
        va = betas_a.get(f) if betas_a else None
        vb = betas_b.get(f) if betas_b else None
        if va is None or vb is None:
            continue
        vals_a.append(float(va))
        vals_b.append(float(vb))

    if len(vals_a) < 2:
        return None, "beta-read-thin:insufficient-factors"

    a = np.array(vals_a)
    b = np.array(vals_b)
    norm_a = float(np.linalg.norm(a))
    norm_b = float(np.linalg.norm(b))
    if norm_a < 1e-12 or norm_b < 1e-12:
        return None, "beta-read-thin:zero-norm"

    cos = float(np.dot(a, b) / (norm_a * norm_b))
    # Clip to [0, 1]: negative cosine means anti-correlated, treat as 0 for
    # the purpose of duplicate-exposure detection (R-C: clipped to [0,1])
    sim = max(0.0, min(1.0, cos))
    used = len(vals_a)
    return sim, f"high-tier-factors:{used}of{len(factors)}"


def pairwise_similarity(
    tickers: list[str],
    groups_index: dict[str, frozenset],
    betas_index: dict[str, dict],
) -> tuple[np.ndarray, list[str], dict[str, dict]]:
    """Build N×N pairwise similarity matrix and per-pair basis dict.

    similarity[i,j] = max(membership_jaccard(i,j), factor_cosine(i,j))
    clipped to [0, 1] per R-C. Diagonal = 1.0.

    Returns:
        S: np.ndarray shape (N, N), dtype float64
        ordered_tickers: the row/col ordering
        pair_basis: dict keyed by "TICKER_A__TICKER_B" → {membership, factor, combined, flags}
    """
    n = len(tickers)
    tickers_up = [t.upper() for t in tickers]
    S = np.eye(n, dtype=np.float64)
    pair_basis: dict[str, dict] = {}

    for i in range(n):
        for j in range(i + 1, n):
            ti, tj = tickers_up[i], tickers_up[j]
            g_i = groups_index.get(ti, frozenset())
            g_j = groups_index.get(tj, frozenset())
            jac = membership_jaccard(g_i, g_j)

            beta_i = betas_index.get(ti) or {}
            beta_j = betas_index.get(tj) or {}
            cos_val, cos_flag = factor_cosine(beta_i, beta_j)

            sim = jac if cos_val is None else max(jac, cos_val)
            sim = max(0.0, min(1.0, sim))
            S[i, j] = S[j, i] = sim

            key = f"{ti}__{tj}"
            pair_basis[key] = {
                "membership_jaccard": round(jac, 4),
                "factor_cosine": round(cos_val, 4) if cos_val is not None else None,
                "combined": round(sim, 4),
                "factor_basis": cos_flag,
                "shared_groups": sorted(g_i & g_j),
            }

    return S, tickers_up, pair_basis


def n_eff_participation_ratio(S: np.ndarray) -> float:
    """Effective independent bets via participation ratio of similarity matrix eigenvalues.

    N_eff = (Σλ_i)² / Σλ_i²

    For N identical names: N_eff = 1.
    For N orthogonal names: N_eff = N.
    Range: [1, N].
    """
    if S.shape[0] == 0:
        return 0.0
    if S.shape[0] == 1:
        return 1.0
    # Symmetrize for numerical safety
    sym = (S + S.T) / 2.0
    eigvals = np.linalg.eigvalsh(sym)
    # eigvalsh returns in ascending order; all should be >= 0 for PSD matrix
    # Clip small negatives from floating point
    eigvals = np.clip(eigvals, 0.0, None)
    s1 = float(eigvals.sum())
    s2 = float((eigvals ** 2).sum())
    if s2 < 1e-14:
        return float(S.shape[0])
    return round(s1 * s1 / s2, 2)


def same_thesis_groups(
    S: np.ndarray,
    ordered_tickers: list[str],
    pair_basis: dict[str, dict],
    threshold: float = DUPLICATE_THRESH,
    min_size: int = 3,
) -> list[dict]:
    """Find connected components of the similarity graph at `threshold`.

    Uses a simple union-find to extract connected components where every edge
    weight >= threshold. Emits groups of size >= min_size.

    Membership is single-linkage/transitive: a name may join a group via ONE
    strong edge >= 0.65, not pairwise cohesion. Hidden concentration through a
    common hub is intentionally captured; a chained member is not necessarily
    similar to every other member in the component.

    Returns list of dicts, each with:
      members: list[str]        — tickers in the component (sorted)
      size: int                 — component size
      basis: str                — dominant similarity leg for the component
                                  (the pair_basis key whose 'combined' is highest
                                  within the component)
      label: str                — human tag: dominant shared_group label(s)
                                  e.g. "ai_infra" or "Information Technology"

    Components are sorted by size desc, then by members[0] asc.
    Display/annotation only — does NOT affect similarity matrix or verdicts (R-F).
    """
    n = len(ordered_tickers)
    if n == 0:
        return []

    # Union-find
    parent = list(range(n))

    def _find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def _union(a: int, b: int) -> None:
        ra, rb = _find(a), _find(b)
        if ra != rb:
            parent[rb] = ra

    for i in range(n):
        for j in range(i + 1, n):
            if S[i, j] >= threshold:
                _union(i, j)

    # Group by root
    from collections import defaultdict  # noqa: PLC0415
    comp: dict[int, list[int]] = defaultdict(list)
    for i in range(n):
        comp[_find(i)].append(i)

    groups: list[dict] = []
    for indices in comp.values():
        if len(indices) < min_size:
            continue

        members = sorted(ordered_tickers[i] for i in indices)
        size = len(members)

        # Dominant pair: highest combined similarity within the component
        best_combined = -1.0
        best_basis_str = "membership-jaccard"
        best_shared: list[str] = []
        for ii in range(len(indices)):
            for jj in range(ii + 1, len(indices)):
                ti = ordered_tickers[indices[ii]]
                tj = ordered_tickers[indices[jj]]
                key = f"{ti}__{tj}" if f"{ti}__{tj}" in pair_basis else f"{tj}__{ti}"
                pb = pair_basis.get(key, {})
                c = pb.get("combined", 0.0) or 0.0
                if c > best_combined:
                    best_combined = c
                    # Determine dominant leg
                    jac = pb.get("membership_jaccard") or 0.0
                    cos = pb.get("factor_cosine") or 0.0
                    if jac >= (cos or 0.0):
                        best_basis_str = "membership-jaccard"
                    else:
                        best_basis_str = "factor-cosine"
                    best_shared = pb.get("shared_groups", [])

        # Label: derive from most common shared group across the component,
        # stripping "sector:" / "basket:" prefixes for display.
        label_counts: dict[str, int] = {}
        for ii in range(len(indices)):
            for jj in range(ii + 1, len(indices)):
                ti = ordered_tickers[indices[ii]]
                tj = ordered_tickers[indices[jj]]
                key = f"{ti}__{tj}" if f"{ti}__{tj}" in pair_basis else f"{tj}__{ti}"
                pb = pair_basis.get(key, {})
                for g in pb.get("shared_groups", []):
                    label_counts[g] = label_counts.get(g, 0) + 1

        if label_counts:
            # Top-1 shared group, strip prefix
            top_g = max(label_counts, key=label_counts.get)  # type: ignore[arg-type]
            label = top_g.split(":", 1)[1] if ":" in top_g else top_g
        elif best_shared:
            label = best_shared[0].split(":", 1)[1] if ":" in best_shared[0] else best_shared[0]
        else:
            label = "shared-membership"

        groups.append({
            "members": members,
            "size": size,
            "basis": best_basis_str,
            "label": label,
        })

    # Sort: largest first, then alphabetical by first member
    groups.sort(key=lambda g: (-g["size"], g["members"][0]))
    return groups


def earnings_week_annotation(
    tickers: list[str],
    earnings_store: "pd.DataFrame | None",
    as_of_date: str,
    window_days: int = 3,
) -> dict[str, dict]:
    """Annotate each ticker with same-earnings-week cluster info.

    This is a Jaccard-adjacent annotation ONLY — it does NOT affect the
    similarity matrix, N_eff, or verdicts (R-D ruling, W-D wave).

    Parameters
    ----------
    tickers: list of uppercase ticker strings (US board only, R-E)
    earnings_store: pd.DataFrame loaded from data/earnings/earnings.parquet,
                    indexed by ticker (upper-case), with 'next_date' column.
                    May be None (fail-open).
    as_of_date: reference date string (ISO format) for week-window computation
    window_days: number of calendar days defining "same week" (default 3,
                 i.e. ±3 calendar days ≈ same trading week per the spec)

    Returns
    -------
    dict[ticker → {
        "next_date": str | None,
        "same_week_peers": list[str],   — other board candidates with next_date
                                          within window_days of this ticker's
        "has_data": bool,               — whether next_date was found
    }]
    """
    try:
        import pandas as pd  # noqa: PLC0415
        from datetime import timedelta  # noqa: PLC0415
    except ImportError:
        return {t: {"next_date": None, "same_week_peers": [], "has_data": False}
                for t in tickers}

    result: dict[str, dict] = {}

    if earnings_store is None or earnings_store.empty:
        return {t: {"next_date": None, "same_week_peers": [], "has_data": False}
                for t in tickers}

    try:
        as_of_ts = pd.Timestamp(as_of_date)
    except Exception:  # noqa: BLE001
        return {t: {"next_date": None, "same_week_peers": [], "has_data": False}
                for t in tickers}

    # Build ticker → next_date map for board candidates
    ticker_dates: dict[str, pd.Timestamp | None] = {}
    store_index_upper = earnings_store.index.str.upper() if hasattr(earnings_store.index, "str") else earnings_store.index
    for t in tickers:
        t_up = t.upper()
        try:
            if t_up in store_index_upper:
                idx_pos = list(store_index_upper).index(t_up)
                actual_idx = earnings_store.index[idx_pos]
                row = earnings_store.loc[actual_idx]
                if isinstance(row, pd.DataFrame):
                    row = row.iloc[0]
                nd = row.get("next_date") if hasattr(row, "get") else row["next_date"]
                if nd and pd.notna(nd):
                    nd_ts = pd.Timestamp(str(nd)).normalize()
                    # Only future/current dates (same fail-open semantics as blackout)
                    if nd_ts >= as_of_ts:
                        ticker_dates[t_up] = nd_ts
                    else:
                        ticker_dates[t_up] = None
                else:
                    ticker_dates[t_up] = None
            else:
                ticker_dates[t_up] = None
        except Exception:  # noqa: BLE001
            ticker_dates[t_up] = None

    window = pd.Timedelta(days=window_days)

    for t in tickers:
        t_up = t.upper()
        nd_ts = ticker_dates.get(t_up)
        has_data = nd_ts is not None

        same_week_peers: list[str] = []
        if nd_ts is not None:
            for other, other_nd in ticker_dates.items():
                if other == t_up:
                    continue
                if other_nd is not None and abs(nd_ts - other_nd) <= window:
                    same_week_peers.append(other)
            same_week_peers.sort()

        result[t_up] = {
            "next_date": nd_ts.strftime("%Y-%m-%d") if nd_ts is not None else None,
            "same_week_peers": same_week_peers,
            "has_data": has_data,
        }

    return result


def _verdict(max_sim: float) -> str:
    if max_sim >= DUPLICATE_THRESH:
        return "duplicate"
    if max_sim >= PARTIAL_THRESH:
        return "partial"
    return "new"


def _shared_group_labels(shared: list[str]) -> list[str]:
    """Convert group labels like 'basket:ai_infra' → 'ai_infra' for display."""
    out = []
    for g in shared:
        if ":" in g:
            out.append(g.split(":", 1)[1])
        else:
            out.append(g)
    return out


def _why_en(ticker: str, nearest: list[dict]) -> str:
    if not nearest:
        return f"{ticker}: no close peers found in the candidate set."
    n = nearest[0]
    peer = n.get("ticker", "?")
    sim = n.get("combined", 0.0)
    shared = _shared_group_labels(n.get("shared_groups", []))
    v = _verdict(sim)
    if v == "duplicate":
        g_str = ", ".join(shared[:3]) if shared else "shared factor profile"
        return f"Same bet as {peer} — {g_str} (similarity {sim:.0%})."
    if v == "partial":
        g_str = ", ".join(shared[:3]) if shared else "partially overlapping exposure"
        return f"Partial overlap with {peer} — {g_str} (similarity {sim:.0%})."
    return f"Distinct bet — nearest peer {peer} at {sim:.0%} similarity."


def _why_zh(ticker: str, nearest: list[dict]) -> str:
    if not nearest:
        return f"{ticker}：候选集中未找到相近的名称。"
    n = nearest[0]
    peer = n.get("ticker", "?")
    sim = n.get("combined", 0.0)
    shared = _shared_group_labels(n.get("shared_groups", []))
    v = _verdict(sim)
    if v == "duplicate":
        g_str = "、".join(shared[:3]) if shared else "共同因子敞口"
        return f"与 {peer} 押注相同 — {g_str}（相似度 {sim:.0%}）。"
    if v == "partial":
        g_str = "、".join(shared[:3]) if shared else "部分重叠敞口"
        return f"与 {peer} 部分重叠 — {g_str}（相似度 {sim:.0%}）。"
    return f"独立押注 — 最近的候选名称 {peer}，相似度 {sim:.0%}。"


def compute(
    tickers: list[str],
    sector_by_ticker: dict[str, str],
    betas_index: dict[str, dict],
    membership_data: Optional[dict],
    as_of: str,
    earnings_store: "Optional[pd.DataFrame]" = None,
) -> dict:
    """Core computation: build similarity matrix, N_eff, per-ticker chip data.

    tickers: ordered list of candidate tickers (US board only, R-E)
    sector_by_ticker: ticker → sector string
    betas_index: ticker → beta dict (from factor_betas.json['betas'])
    membership_data: parsed membership.json (may be None → membership-only fallback)
    as_of: date string for the artifact
    earnings_store: optional pd.DataFrame from data/earnings/earnings.parquet
                    (indexed by ticker, 'next_date' column).  None = no annotation.

    Returns the full reflexivity_overlay artifact dict.
    """
    tickers_up = [t.upper() for t in tickers]
    n = len(tickers_up)

    # Per-ticker basis flag: if betas absent/thin → membership-only sim
    ticker_basis: dict[str, str] = {}

    groups_index = build_groups_index(membership_data, tickers_up, sector_by_ticker)

    # Build betas_index for the candidate set, annotate basis
    cand_betas: dict[str, dict] = {}
    for t in tickers_up:
        beta_rec = betas_index.get(t) or {}
        cand_betas[t] = beta_rec
        r2 = beta_rec.get("r2")
        if not beta_rec:
            ticker_basis[t] = "membership-only:no-beta"
        elif r2 is not None and r2 < R2_FLOOR:
            ticker_basis[t] = f"membership-only:r2={r2:.2f}<{R2_FLOOR}"
        else:
            ticker_basis[t] = "membership+high-tier-factor"

    # Build pairwise similarity matrix
    if n >= 2:
        S, ordered, pair_basis = pairwise_similarity(tickers_up, groups_index, cand_betas)
        neff = n_eff_participation_ratio(S)
    else:
        S = np.eye(max(n, 1))
        ordered = tickers_up
        pair_basis = {}
        neff = float(n)

    # ── Earnings-week annotation (W-D, R-D) ──────────────────────────────────
    # Jaccard-adjacent annotation only. Does NOT affect S, n_eff, or verdicts.
    ew_ann = earnings_week_annotation(tickers_up, earnings_store, as_of)
    coverage = sum(1 for a in ew_ann.values() if a.get("has_data", False))
    earnings_coverage_frac = round(coverage / n, 3) if n > 0 else 0.0

    # Per-ticker chip: nearest peers sorted by similarity desc
    by_ticker: dict[str, dict] = {}
    for i, tkr in enumerate(ordered):
        sims_row = [(ordered[j], float(S[i, j])) for j in range(n) if j != i]
        sims_row.sort(key=lambda x: -x[1])

        ew_rec = ew_ann.get(tkr, {})

        nearest: list[dict] = []
        for peer, sim in sims_row[:3]:
            key = f"{tkr}__{peer}" if f"{tkr}__{peer}" in pair_basis else f"{peer}__{tkr}"
            pb = pair_basis.get(key, {})
            # same_earnings_week: True if peer is in same-week cluster for this ticker
            peer_in_same_week = peer in ew_rec.get("same_week_peers", [])
            nearest.append({
                "ticker": peer,
                "combined": round(sim, 4),
                "membership_jaccard": pb.get("membership_jaccard"),
                "factor_cosine": pb.get("factor_cosine"),
                "factor_basis": pb.get("factor_basis"),
                "shared_groups": pb.get("shared_groups", []),
                "same_earnings_week": peer_in_same_week if ew_rec.get("has_data") else None,
            })

        max_sim = sims_row[0][1] if sims_row else 0.0
        v = _verdict(max_sim)

        by_ticker[tkr] = {
            "verdict": v,
            "max_similarity": round(max_sim, 4),
            "basis": ticker_basis.get(tkr, "membership+high-tier-factor"),
            "nearest": nearest,
            "earnings_leg": {
                "next_date": ew_rec.get("next_date"),
                "same_week_peers": ew_rec.get("same_week_peers", []),
                "has_data": ew_rec.get("has_data", False),
            },
            "earnings_leg_note": (
                "earnings-cluster annotation (W-D): Jaccard-adjacent, display-only. "
                "Does not affect similarity matrix, N_eff, or verdicts."
            ),
            "why_en": _why_en(tkr, nearest),
            "why_zh": _why_zh(tkr, nearest),
        }

    # ── Five-candidates-one-thesis detector (W-D) ─────────────────────────
    # Connected components at DUPLICATE_THRESH, size ≥3 emitted as groups.
    # Display/annotation only — no ordering/ranking effect (R-F).
    thesis_groups = same_thesis_groups(S, ordered, pair_basis,
                                       threshold=DUPLICATE_THRESH, min_size=3)

    return {
        "schema": SCHEMA,
        "is_context_only": True,
        "as_of": as_of,
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "note": (
            "Risk-clustering read: 'is this the same hidden trade?'. "
            "NOT an alpha claim. Board-level, held-agnostic (US only, v1). "
            "Display-only per R-F / Signal Commons R7."
        ),
        "factor_caveat": FACTOR_CAVEAT,
        "board_concentration": {
            "n": n,
            "n_eff": neff,
            "basis": "membership-jaccard+high-tier-factor-cosine",
            "note": (
                "Supersedes sector-only HHI effective_bets in build_stock_board_v2 per R-B. "
                "N_eff = participation-ratio of similarity-matrix eigenvalues. "
                f"{n} candidates ≈ {neff} independent bets."
            ),
        },
        "same_thesis_groups": thesis_groups,
        "earnings_coverage_frac": earnings_coverage_frac,
        "by_ticker": by_ticker,
        "pair_basis": pair_basis,
        "verdicts": {
            "duplicate_thresh": DUPLICATE_THRESH,
            "partial_thresh": PARTIAL_THRESH,
            "duplicate_note": f"similarity >= {DUPLICATE_THRESH} → same hidden trade",
            "partial_note": f"similarity >= {PARTIAL_THRESH} → partial overlap",
            "new_note": f"similarity < {PARTIAL_THRESH} → distinct bet",
        },
    }
