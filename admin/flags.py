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
# `note` is written for a non-technical site owner — plain language, no jargon.
FLAGS: list[dict] = [
    # ---- AI / LLM -----------------------------------------------------------
    {"path": "master_brain.enabled", "label": "AI morning briefs",
     "category": "AI", "master": True, "requires": ["DEEPSEEK_API_KEY"],
     "note": "Main switch for the AI-written morning briefs (three topics: big-picture macro, China, Bitcoin)."},
    {"path": "master_brain.translate_zh", "label": "Morning briefs — Chinese version",
     "category": "AI", "requires": ["DEEPSEEK_API_KEY"],
     "note": "Also writes a Chinese (中文) version of each brief. Costs a little more; turn off to save."},
    {"path": "ai_desk.enabled", "label": "AI analyst desk",
     "category": "AI", "master": True, "requires": ["DEEPSEEK_API_KEY"],
     "note": "An AI analyst that makes testable market calls and keeps score of how they turn out. Background context only."},
    {"path": "ai_desk.panel.enabled", "label": "AI analyst desk — debate panel",
     "category": "AI", "requires": ["DEEPSEEK_API_KEY"],
     "note": "On = a 4-analyst debate (5 AI calls, richer). Off = a single analyst (cheaper)."},
    {"path": "catalyst_tone.enabled", "label": "Fed / economic-release summaries",
     "category": "AI", "requires": ["DEEPSEEK_API_KEY"],
     "note": "AI read of the mood around Fed meetings and economic releases. Also needed for the news part of stock briefs."},
    {"path": "catalyst_tone.event_enabled", "label": "Big-market-day news summaries",
     "category": "AI", "requires": ["DEEPSEEK_API_KEY"],
     "note": "Summarizes the news on large market-moving days when there's no Fed meeting."},
    {"path": "catalyst_stock.enabled", "label": "Per-stock AI research write-ups",
     "category": "AI", "master": True, "requires": ["DEEPSEEK_API_KEY"],
     "note": "AI research notes for individual stocks (about $0.04 each, capped per run)."},
    {"path": "catalyst_stock.news_enabled", "label": "Stock write-ups — add company news",
     "category": "AI", "requires": ["DEEPSEEK_API_KEY"],
     "note": "Adds a short company-news summary to each stock write-up."},
    {"path": "profile_translation.enabled", "label": "Auto-translate company descriptions (中文)",
     "category": "AI", "requires": ["DEEPSEEK_API_KEY"],
     "note": "Auto-translates company descriptions into Chinese. Does nothing without an API key."},
    {"path": "macro_news.llm_brief", "label": "Macro page — AI summary paragraph",
     "category": "AI", "requires": ["DEEPSEEK_API_KEY"],
     "note": "A one-paragraph AI summary at the top of the macro page."},

    # ---- Notifications ------------------------------------------------------
    {"path": "notify.telegram.enabled", "label": "Telegram alerts",
     "category": "Notifications", "requires": ["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"],
     "note": "Sends the daily snapshot and any triggered alerts to Telegram."},
    {"path": "notify.discord.enabled", "label": "Discord alerts",
     "category": "Notifications", "requires": ["DISCORD_WEBHOOK_URL"],
     "note": "Sends the daily snapshot and any triggered alerts to Discord."},
    {"path": "notify.experiments_alerts", "label": "\"Experiment ready\" pings",
     "category": "Notifications", "requires": [],
     "note": "Pings Telegram/Discord when a tracked experiment is ready for its next step. "
             "See the Experiments tab."},

    # ---- News / data feeds --------------------------------------------------
    {"path": "macro_news.enabled", "label": "Macro page news headlines",
     "category": "News & data", "requires": [],
     "note": "Adds free news headlines to the macro page (source: GDELT, no key needed)."},
    {"path": "news_vector.enabled", "label": "News event log",
     "category": "News & data", "requires": [],
     "note": "Records news-driven story events over time, so trends can be tracked (free, no key)."},
    {"path": "commodity_news.enabled", "label": "Commodity news headlines",
     "category": "News & data", "requires": [],
     "note": "News headlines for commodities (off by default)."},

    # ---- Data sources -------------------------------------------------------
    {"path": "edgar.enabled", "label": "Company fundamentals rankings",
     "category": "Data sources", "requires": [],
     "note": "Value / quality / profitability rankings built from free SEC filings. Powers the Factor Rankings page."},
    {"path": "smart_money.enabled", "label": "Smart Money (institutions' holdings)",
     "category": "Data sources", "requires": [],
     "note": "Shows which big institutions hold a stock, from free SEC filings."},
    {"path": "fundamentals.enabled", "label": "Extra fundamentals (Finnhub)",
     "category": "Data sources", "requires": [],
     "note": "Extra fundamentals data. Low quality; the engine runs fine without it."},
    {"path": "prediction_markets.enabled", "label": "Betting-market odds (Polymarket)",
     "category": "Data sources", "requires": [],
     "note": "Betting-market odds for Fed and recession events (Polymarket, free)."},
    {"path": "bis.enabled", "label": "Global credit cycle (BIS)",
     "category": "Data sources", "requires": [],
     "note": "Global debt-and-credit context for the bond outlook, from free BIS data."},
    {"path": "treasury_auctions.enabled", "label": "Treasury auction demand",
     "category": "Data sources", "requires": [],
     "note": "How strong demand was at U.S. Treasury bond auctions (free, from TreasuryDirect)."},

    # ---- Dashboards / pages -------------------------------------------------
    {"path": "engine.macro_overlay.enabled", "label": "Macro-risk position sizing",
     "category": "Dashboards", "requires": [],
     "note": "Main switch. When off, the dashboard ignores big-picture risk when sizing sector and buy signals."},
    {"path": "watchlist.enabled", "label": "Holdings watchlist page",
     "category": "Dashboards", "requires": [],
     "note": "A personal watchlist for your holdings (needs the U.S. stock search turned on)."},
    {"path": "stock_search.enabled", "label": "U.S. stock search",
     "category": "Dashboards", "requires": [],
     "note": "A search box for U.S. stocks (S&P 1500 + ETFs). The watchlist depends on this."},
    {"path": "china.search_universe.enabled", "label": "China stock search",
     "category": "Dashboards", "requires": [],
     "note": "Searchable list of the top 800 China A-shares."},
    {"path": "canada.search_universe.enabled", "label": "Canada stock search",
     "category": "Dashboards", "requires": [],
     "note": "Searchable list of the top 250 Canadian (TSX) stocks."},
    {"path": "intl.search_universe.enabled", "label": "International stock search",
     "category": "Dashboards", "requires": [],
     "note": "Searchable list of international stocks that powers the picks on the International page."},
]


def secret_present(name: str) -> bool:
    import os
    return bool(os.environ.get(name, "").strip())


def snapshot(cfg: dict | None = None) -> dict:
    """Current value + secret-readiness for every managed flag, grouped by category."""
    cfg = cfg if cfg is not None else config_store.read_config()
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
