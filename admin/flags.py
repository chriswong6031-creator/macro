"""Curated registry of the config.yml feature flags worth exposing in the admin UI.

Only flags a SITE OWNER would plausibly toggle — not deep calibration/tuning knobs.
`requires` lists the secret env vars a flag needs to actually do anything when ON
(the admin warns when a required secret is absent). Line numbers are hints for
display/debug only; config_store locates the leaf by walking YAML structure.
"""
from __future__ import annotations

from . import config_store

# secret -> human label, for the "missing secret" warnings
SECRETS = {
    "DEEPSEEK_API_KEY": "DeepSeek API key (LLM)",
    "ANTHROPIC_API_KEY": "Anthropic API key (LLM)",
    "TELEGRAM_BOT_TOKEN": "Telegram bot token",
    "TELEGRAM_CHAT_ID": "Telegram chat id",
    "DISCORD_WEBHOOK_URL": "Discord webhook URL",
    "FINNHUB_KEY": "Finnhub key",
    "FRED_API_KEY": "FRED API key",
    "POLYGON_API_KEY": "Polygon/massive.com key",
}

# Each: path (dotted, in config.yml) · label · category · note · requires (secret names)
FLAGS: list[dict] = [
    # ---- AI / LLM -----------------------------------------------------------
    {"path": "master_brain.enabled", "label": "AI Daily Brief (Master Brain)",
     "category": "AI", "master": True, "requires": ["DEEPSEEK_API_KEY"],
     "note": "Master switch for the 3-lens morning briefs (macro / china / btc)."},
    {"path": "master_brain.translate_zh", "label": "Brief — Chinese translation",
     "category": "AI", "requires": ["DEEPSEEK_API_KEY"],
     "note": "Adds a 中文 version per brief (extra cheap LLM pass); off saves cost."},
    {"path": "ai_desk.enabled", "label": "AI Desk (accountable analyst)",
     "category": "AI", "master": True, "requires": ["DEEPSEEK_API_KEY"],
     "note": "Falsifiable conditional leans, scored over time. Context-only."},
    {"path": "ai_desk.panel.enabled", "label": "AI Desk — 4-analyst panel",
     "category": "AI", "requires": ["DEEPSEEK_API_KEY"],
     "note": "ON = 5 LLM calls (adversarial panel); OFF = 1 call (cheaper)."},
    {"path": "catalyst_tone.enabled", "label": "Catalyst Tone (FOMC/release digest)",
     "category": "AI", "requires": ["DEEPSEEK_API_KEY"],
     "note": "LLM tone digest of FOMC/releases; also gates the stock-brief news leg."},
    {"path": "catalyst_tone.event_enabled", "label": "Catalyst Tone — event-day news",
     "category": "AI", "requires": ["DEEPSEEK_API_KEY"],
     "note": "Digest dislocation-day news when there's no FOMC read."},
    {"path": "catalyst_stock.enabled", "label": "Per-stock AI research briefs",
     "category": "AI", "master": True, "requires": ["DEEPSEEK_API_KEY"],
     "note": "Precomputed single-stock briefs (~$0.04 each, capped per build)."},
    {"path": "catalyst_stock.news_enabled", "label": "Stock briefs — news digest leg",
     "category": "AI", "requires": ["DEEPSEEK_API_KEY"],
     "note": "Adds a company-news digest to each stock brief."},
    {"path": "profile_translation.enabled", "label": "Auto-translate stock blurbs (中文)",
     "category": "AI", "requires": ["DEEPSEEK_API_KEY"],
     "note": "Machine-translates business-profile blurbs; no-op without a key."},
    {"path": "macro_news.llm_brief", "label": "Macro news — AI narrator paragraph",
     "category": "AI", "requires": ["DEEPSEEK_API_KEY"],
     "note": "One-paragraph LLM context brief on the macro page."},

    # ---- Notifications ------------------------------------------------------
    {"path": "notify.telegram.enabled", "label": "Telegram alerts",
     "category": "Notifications", "requires": ["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"],
     "note": "Daily snapshot + fired alerts to Telegram."},
    {"path": "notify.discord.enabled", "label": "Discord alerts",
     "category": "Notifications", "requires": ["DISCORD_WEBHOOK_URL"],
     "note": "Daily snapshot + fired alerts to a Discord webhook."},

    # ---- News / data feeds --------------------------------------------------
    {"path": "macro_news.enabled", "label": "Macro news layer (GDELT)",
     "category": "News & data", "requires": [],
     "note": "Keyless GDELT news annotations on macro.html."},
    {"path": "news_vector.enabled", "label": "Narrative event bus (GDELT)",
     "category": "News & data", "requires": [],
     "note": "Append-only narrative event store (keyless)."},
    {"path": "commodity_news.enabled", "label": "Commodity news layer",
     "category": "News & data", "requires": [],
     "note": "Event-annotation layer for commodities (default off)."},

    # ---- Data sources -------------------------------------------------------
    {"path": "edgar.enabled", "label": "EDGAR factor rankings",
     "category": "Data sources", "requires": [],
     "note": "SEC XBRL value/quality/profitability factors + Factor Rankings page."},
    {"path": "smart_money.enabled", "label": "Smart Money (13F holdings)",
     "category": "Data sources", "requires": [],
     "note": "Keyless SEC 13F 'who holds this' context."},
    {"path": "fundamentals.enabled", "label": "Fundamentals (Finnhub)",
     "category": "Data sources", "requires": ["FINNHUB_KEY"],
     "note": "Low-confidence module; engine works without it."},
    {"path": "prediction_markets.enabled", "label": "Prediction markets (Polymarket)",
     "category": "Data sources", "requires": [],
     "note": "Keyless Polymarket odds for Fed/recession events."},
    {"path": "bis.enabled", "label": "BIS global credit cycle",
     "category": "Data sources", "requires": [],
     "note": "Keyless credit-to-GDP gap + DSR context on bonds."},
    {"path": "treasury_auctions.enabled", "label": "Treasury auction results",
     "category": "Data sources", "requires": [],
     "note": "Keyless TreasuryDirect auction-demand panel."},

    # ---- Dashboards / pages -------------------------------------------------
    {"path": "engine.macro_overlay.enabled", "label": "Macro-risk overlay (sizing)",
     "category": "Dashboards", "requires": [],
     "note": "Global kill-switch; off = pre-overlay sector-heat/buy-setup behavior."},
    {"path": "watchlist.enabled", "label": "Holdings Watchlist page",
     "category": "Dashboards", "requires": [],
     "note": "Client-side holdings watchlist (needs stock search)."},
    {"path": "stock_search.enabled", "label": "US stock search library",
     "category": "Dashboards", "requires": [],
     "note": "Searchable S&P 1500 + ETFs library; watchlist depends on it."},
    {"path": "china.search_universe.enabled", "label": "China stock search",
     "category": "Dashboards", "requires": [],
     "note": "Top-800 A-shares searchable library."},
    {"path": "canada.search_universe.enabled", "label": "Canada stock search",
     "category": "Dashboards", "requires": [],
     "note": "Top-250 TSX Composite searchable library."},
    {"path": "intl.search_universe.enabled", "label": "International stock search",
     "category": "Dashboards", "requires": [],
     "note": "iShares UCITS universe powering /intl.html standouts."},
]


def secret_present(name: str) -> bool:
    import os
    return bool(os.environ.get(name, "").strip())


def snapshot() -> dict:
    """Current value + secret-readiness for every managed flag, grouped by category."""
    cfg = config_store.read_config()
    groups: dict[str, list[dict]] = {}
    for f in FLAGS:
        val = config_store.get_value(f["path"], cfg)
        missing = [s for s in f.get("requires", []) if not secret_present(s)]
        row = {
            "path": f["path"],
            "label": f["label"],
            "note": f["note"],
            "master": bool(f.get("master")),
            "value": bool(val) if isinstance(val, bool) else val,
            "requires": f.get("requires", []),
            "missing_secrets": missing,
            # ON but a required secret is absent → silently a no-op; surface it
            "inert": bool(val) and bool(missing),
        }
        groups.setdefault(f["category"], []).append(row)
    return {"groups": groups, "order": list(groups.keys())}
