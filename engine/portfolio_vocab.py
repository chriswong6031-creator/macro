"""Shared desk vocabulary for the portfolio composers — ONE definition, two readers.

Extracted in W6 (retention layer) so `engine/portfolio_brief.py` (the nightly brief) and
`engine/portfolio_changes.py` (the "since your last visit" diff) speak the SAME desk
words without either importing the other. Both modules render Weinstein stages and both
must resolve a held name's sector onto the rotation board's taxonomy; a second copy of
either table would drift the moment one surface was reworded, and the two surfaces sit
side by side in the same panel.

This module originates NOTHING. `STAGE_WORD` is the fixed display re-expression of the
stage number already carried by the ctx artifact; `SECTOR_ALIASES` is a pure display
alias between two existing taxonomies (it changes no value, only which block is read).
No thresholds, no scores, no classifications of our own.
"""
from __future__ import annotations

# Weinstein stage → plain word (DISPLAY re-expression, fixed wording per spec).
# Keys are the ctx's own `stage.n`; the pair is (en, zh).
STAGE_WORD: dict[int, tuple[str, str]] = {
    1: ("base", "筑底"),
    2: ("uptrend", "上升"),
    3: ("topping", "见顶"),
    4: ("decline", "下行"),
}

# Rotation-board `class` → plain word (DISPLAY re-expression, both languages).
#
# The ctx's `class` values are subsector_confluence's INTERNAL slugs. They are fine as
# machine keys and as `data.concentration.sectors[].class`, but they must never reach a
# rendered sentence: "Energy 在桌面轮动板上从 entry_now 转为 headwind。" puts untranslated
# English tokens inside a Chinese sentence. `late` is in the LIVE artifact today, so this
# is a shipping path, not a hypothetical.
#
# Callers MUST treat an unmapped class as "no renderable word" and omit the clause rather
# than falling back to the slug — that fallback is the defect this map exists to close.
CLASS_WORD: dict[str, tuple[str, str]] = {
    "tailwind": ("tailwind", "顺风"),
    "headwind": ("headwind", "逆风"),
    "neutral": ("neutral", "中性"),
    "entry_now": ("entry now", "可入场"),
    "late": ("late", "偏后段"),
    "forming": ("forming", "形成中"),
    # zh deliberately avoids 买入/建仓 — the advice-filter kill-list (RUL-NW4). A board
    # state is a description of the tape, not an instruction to trade.
    "buyable": ("buyable", "可参与"),
}


def class_word(cls: str | None) -> tuple[str, str] | None:
    """(en, zh) for a rotation-board class, or None when it has no display word."""
    if not cls or not isinstance(cls, str):
        return None
    return CLASS_WORD.get(cls.strip().lower())


# Sector-name reconciliation. The per-ticker `sector` field (from stockdata profiles via
# us_standouts / screener rows) uses one taxonomy ("Information Technology", "Health
# Care", "Financials", "Materials"); the ctx.sectors block is keyed by the rotation
# board's taxonomy ("Technology", "Healthcare", "Financial", "Basic Materials"). To read
# a held name's sector stance we must reconcile the two. This map is a pure display
# alias — it changes NO value, only which sector block we look up; when neither the raw
# name nor an alias matches a block the caller omits the stance clause and states the
# exposure honestly (the "no desk read for <sector>" path). Documented and descriptive,
# not a new classification.
SECTOR_ALIASES: dict[str, str] = {
    "information technology": "Technology",
    "health care": "Healthcare",
    "financials": "Financial",
    "consumer staples": "Consumer Defensive",
    "consumer discretionary": "Consumer Cyclical",
    "materials": "Basic Materials",
    "communication": "Communication Services",
    "telecommunication services": "Communication Services",
}


def sector_block(ctx_sectors: dict, sector: str | None) -> dict:
    """Return the ctx.sectors block for a held name's sector, reconciling taxonomies.

    Tries the raw sector name, then the display alias. Returns {} when neither matches
    (honest: the caller then omits the stance clause rather than fabricating a read)."""
    if not sector or not isinstance(ctx_sectors, dict):
        return {}
    if sector in ctx_sectors:
        blk = ctx_sectors[sector]
        return blk if isinstance(blk, dict) else {}
    alias = SECTOR_ALIASES.get(sector.strip().lower())
    if alias and alias in ctx_sectors:
        blk = ctx_sectors[alias]
        return blk if isinstance(blk, dict) else {}
    return {}
