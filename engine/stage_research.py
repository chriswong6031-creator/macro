"""Research index builder for the Stage Analysis hub (SGA-2 §F).

Reads the EquityDesk `research.parquet` seed (their `company_generated_info`
deep-dive table) and emits data/stage_analysis/research_index.json — a per-ticker
index the Research surface + transcript reader consume:

  {tickerb, ticker_ui, thesis_summary, model_used, tier,
   has_openai, has_claude, has_gemini, research_url}

The transcript reader ALSO reads the earnings-call text (summary / unified_analysis
from earnings_calls_text.parquet, joined on document_ticker) at render time — this
index is the entry list + thesis seed; the transcript body is fetched per-ticker by
the page lane.

EPISTEMICS (DISPLAY-TIER, is_context_only): these are company primers, NOT
recommendations. Every thesis string is passed through a trading-verb / advice
SCRUB so no "buy / sell / accumulate / price target / overweight" language ever
reaches the user surface. Nothing here is a signal, gate, score, or sizing input.

EVERYTHING fail-open: a missing seed, column, or row degrades to an empty index;
the artifact always writes with the scaffold so a broken store never crashes a
build or blanks the page.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path

import numpy as np
import pandas as pd

from lib import config

log = logging.getLogger(__name__)

_BACKFILL_SUBDIR = ("stage_analysis", "backfill")
_RESEARCH_SEED = "research.parquet"
_OUT_REL = ("stage_analysis", "research_index.json")

# ---------------------------------------------------------------------------
# FIX 1c — region for the flagship region toggle (N.America / Europe / Asia)
# ---------------------------------------------------------------------------
# The research seed carries no native region column, but `tickerb` is a
# Bloomberg-style symbol whose 2-letter COMPOSITE exchange suffix IS the region
# key (e.g. "AAPL US", "BABA HK", "SAP GY"). We map it to the SAME 3-bucket scheme
# EquityDesk uses for every other surface (USA / EUROPE / ASIA) so the toggle
# filters the Research surface instead of blanking it. This is a display-tier
# region HINT — not authority. LATAM / rest-of-world composites (BZ Brazil, AR
# Argentina, …) fold into ASIA as the Asia-Pacific/RoW catch-all: EquityDesk's
# 3-region scheme has no LATAM tab, and this is the least-misleading home given a
# 3-way toggle. A bare (suffix-less) tickerb is treated as US.
_SUFFIX_REGION: dict[str, str] = {
    # North America
    "US": "USA", "CN": "USA", "CT": "USA",          # CN/CT = Canada (Toronto)
    # Europe / EMEA
    "LN": "EUROPE", "FP": "EUROPE", "GY": "EUROPE", "GR": "EUROPE", "IM": "EUROPE",
    "SM": "EUROPE", "NA": "EUROPE", "SW": "EUROPE", "VX": "EUROPE", "BB": "EUROPE",
    "ID": "EUROPE", "SS": "EUROPE", "FH": "EUROPE", "NO": "EUROPE", "DC": "EUROPE",
    "PW": "EUROPE", "PL": "EUROPE", "CP": "EUROPE", "GA": "EUROPE", "IT": "EUROPE",
    "LX": "EUROPE", "MC": "EUROPE", "PM": "EUROPE", "AV": "EUROPE", "SJ": "EUROPE",
    "RU": "EUROPE", "TI": "EUROPE", "TE": "EUROPE",
    # Asia-Pacific (+ LATAM / RoW catch-all)
    "CH": "ASIA", "C1": "ASIA", "C2": "ASIA", "HK": "ASIA", "KS": "ASIA", "KP": "ASIA",
    "JT": "ASIA", "JP": "ASIA", "TT": "ASIA", "TB": "ASIA", "IN": "ASIA", "IB": "ASIA",
    "IS": "ASIA", "MK": "ASIA", "SP": "ASIA", "AU": "ASIA", "AT": "ASIA", "NZ": "ASIA",
    "PH": "ASIA", "VN": "ASIA", "MM": "ASIA", "BZ": "ASIA", "AR": "ASIA", "PA": "ASIA",
    "CI": "ASIA", "PB": "ASIA",
}


def _region_from_tickerb(tickerb: str | None, ticker_ui: str | None) -> str:
    """Map a Bloomberg-suffixed symbol to USA / EUROPE / ASIA (display hint).
    A bare (suffix-less) symbol → USA. Unknown suffix → ASIA (RoW catch-all)."""
    for cand in (tickerb, ticker_ui):
        if not cand:
            continue
        parts = str(cand).split()
        if len(parts) < 2:
            # No exchange suffix — treat a bare symbol as US-listed.
            return "USA"
        return _SUFFIX_REGION.get(parts[-1].upper(), "ASIA")
    return "USA"

# The index is an ENTRY LIST + thesis SNIPPET; the full thesis + transcript body
# live in the per-ticker transcript view (fetched at render time). Keep the
# committed seed under the ~1.2MB page budget: a lean per-entry thesis snippet +
# a cap on the entry count (thesis-carrying, broadest-tier first). The full set
# stays in the backfill / R2 detail lane. n_total is disclosed honestly.
_MAX_THESIS_CHARS = 180    # snippet for the list; full text lives in the transcript view
_MAX_INDEX_ITEMS = 2600    # committed-seed entry cap (~1.15MB, under the ~1.2MB budget)

# ---------------------------------------------------------------------------
# Trading-verb / advice scrub (display-tier law: primers, never advice)
# ---------------------------------------------------------------------------
# Single source of truth lives in engine/_text_scrub.py so the Earnings-Calls
# surfaces (engine/earnings_qual.py) scrub through the SAME rules. Re-exported
# under the historical names (tests reference R._scrub_advice / R._VERB_MAP).
from engine._text_scrub import (  # noqa: E402,F401 — re-exported for callers/tests
    _ADVICE_PHRASES,
    _VERB_MAP,
    _VERB_RE,
    scrub_advice as _scrub_advice,
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _data_root(root: str | Path | None) -> Path:
    if root is not None:
        return Path(root)
    try:
        return config.data_dir()
    except Exception:  # noqa: BLE001
        return Path("/nonexistent-research-root")


def _seed_dir(root: Path) -> Path:
    return root.joinpath(*_BACKFILL_SUBDIR)


def _atomic_write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2, ensure_ascii=False))
    os.replace(tmp, path)


def _clean_str(v) -> str | None:
    if v is None:
        return None
    try:
        if isinstance(v, float) and np.isnan(v):
            return None
    except Exception:  # noqa: BLE001
        pass
    s = str(v).strip()
    if not s or s.lower() in ("nan", "none", "null"):
        return None
    return s


def _has_provider(row, col: str, model: str | None, needles: tuple[str, ...]) -> bool:
    """True if the provider's reasoning column is populated OR model_used names it."""
    if _clean_str(row.get(col)) is not None:
        return True
    if model:
        m = model.lower()
        return any(n in m for n in needles)
    return False


# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------
def build_research_index(root: str | Path | None = None) -> dict:
    """Build + write data/stage_analysis/research_index.json (SGA-2 §F).

    Returns the artifact dict (also written to disk). DISPLAY-TIER,
    is_context_only, read-only over the committed research seed, fully
    fail-open. Every thesis string is advice-scrubbed.

    Args:
        root: data-root override (tests); defaults to config.data_dir().
    """
    data_root = _data_root(root)
    seed = _seed_dir(data_root) / _RESEARCH_SEED

    items: list[dict] = []
    by_ticker: dict[str, dict] = {}

    df = None
    if seed.exists():
        try:
            df = pd.read_parquet(seed)
        except Exception:  # noqa: BLE001 — unreadable seed -> empty index
            log.warning("research_index: unreadable seed (fail-open)", exc_info=True)
            df = None

    if df is not None and not df.empty:
        # one row per ticker: prefer the richer tier (lower tier number = broader)
        # and a populated thesis
        cols = set(df.columns)
        for _, row in df.iterrows():
            tickerb = _clean_str(row.get("tickerb"))
            ticker_ui = _clean_str(row.get("ticker_ui")) or tickerb
            if tickerb is None and ticker_ui is None:
                continue
            key = ticker_ui or tickerb

            model = _clean_str(row.get("model_used")) if "model_used" in cols else None
            thesis_raw = (_clean_str(row.get("summary_thesis_answer"))
                          if "summary_thesis_answer" in cols else None)
            thesis = _scrub_advice(thesis_raw)
            if thesis and len(thesis) > _MAX_THESIS_CHARS:
                thesis = thesis[:_MAX_THESIS_CHARS].rstrip() + "…"

            tier_v = None
            if "tier" in cols:
                try:
                    tier_v = int(row.get("tier"))
                except (TypeError, ValueError):
                    tier_v = None

            has_openai = _has_provider(
                row, "openai_reasoning_analysis", model, ("openai", "gpt", "sonar", "perplexity"),
            ) if "openai_reasoning_analysis" in cols else bool(
                model and any(n in model.lower() for n in ("openai", "gpt", "sonar", "perplexity")))
            has_claude = _has_provider(
                row, "claude_reasoning_analysis", model, ("claude", "anthropic", "opus", "sonnet"),
            ) if "claude_reasoning_analysis" in cols else bool(
                model and any(n in model.lower() for n in ("claude", "anthropic", "opus", "sonnet")))
            research_url = (_clean_str(row.get("gemini_reasoning_research_url"))
                            if "gemini_reasoning_research_url" in cols else None)
            has_gemini = bool(research_url) or bool(
                model and "gemini" in model.lower())

            item = {
                "tickerb": tickerb,
                "ticker_ui": ticker_ui,
                "region": _region_from_tickerb(tickerb, ticker_ui),   # FIX 1c
                "thesis_summary": thesis,
                "model_used": model,
                "tier": tier_v,
                "has_openai": bool(has_openai),
                "has_claude": bool(has_claude),
                "has_gemini": bool(has_gemini),
                "research_url": research_url,
            }

            prev = by_ticker.get(key)
            if prev is None:
                by_ticker[key] = item
            else:
                # keep the entry with a thesis; break ties toward the broader tier
                prev_has = bool(prev.get("thesis_summary"))
                cur_has = bool(item.get("thesis_summary"))
                if cur_has and not prev_has:
                    by_ticker[key] = item
                elif cur_has == prev_has:
                    pt, ct = prev.get("tier"), item.get("tier")
                    if ct is not None and (pt is None or ct < pt):
                        by_ticker[key] = item

    all_items = list(by_ticker.values())
    n_total = len(all_items)
    with_thesis_total = sum(1 for i in all_items if i.get("thesis_summary"))
    # Cap the committed seed to the most useful entries (thesis-carrying first,
    # then broadest tier), then present alphabetically for the page. The full set
    # stays in the backfill / R2 detail lane — never gitignored into warm-up.
    ranked = sorted(
        all_items,
        key=lambda r: (
            not bool(r.get("thesis_summary")),          # thesis-carrying first
            r.get("tier") if r.get("tier") is not None else 9,  # broadest tier
            r.get("ticker_ui") or "",
        ),
    )
    kept = ranked[:_MAX_INDEX_ITEMS]
    items = sorted(kept, key=lambda r: (r["ticker_ui"] or ""))

    # Per-region counts (FIX 1c) so the toggle can show a badge / hide empty tabs.
    region_counts: dict[str, int] = {"USA": 0, "EUROPE": 0, "ASIA": 0}
    for i in items:
        region_counts[i.get("region", "USA")] = region_counts.get(i.get("region", "USA"), 0) + 1

    artifact = {
        "schema": "research_index.v1",
        "is_context_only": True,
        "display_only": True,
        "note": ("Per-company research primers (thesis snippets). Context only — "
                 "company background, never a recommendation, signal, or sizing input. "
                 "Transcript reader surfaces the full thesis + earnings summary."),
        "note_zh": ("公司研究简介（论点摘要）。仅供参考——公司背景，"
                    "绝非推荐、信号或仓位依据。"),
        # FIX 1c — the Research surface is genuinely 3-region; each item carries a
        # `region` (USA/EUROPE/ASIA) derived from the Bloomberg exchange suffix so
        # the flagship region toggle filters it instead of blanking EU/Asia.
        "has_region": True,
        "region_scheme": "bloomberg_suffix",
        "region_note": ("region is a display hint derived from the Bloomberg "
                        "exchange suffix on tickerb (US→USA, LN/FP/GY…→EUROPE, "
                        "CH/HK/KS…→ASIA); LATAM/RoW folds into ASIA (no LATAM tab)."),
        "region_counts": region_counts,
        "count": len(items),
        "n_total": n_total,       # full universe before the artifact-budget cap
        "cap": _MAX_INDEX_ITEMS,
        "with_thesis": sum(1 for i in items if i.get("thesis_summary")),
        "with_thesis_total": with_thesis_total,
        "items": items,
    }

    try:
        out_path = data_root.joinpath(*_OUT_REL)
        _atomic_write_json(out_path, artifact)
    except Exception:  # noqa: BLE001 — write failure never crashes the build
        log.warning("research_index: write failed (fail-open)", exc_info=True)
    return artifact
