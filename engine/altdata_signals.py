"""Per-ticker alt-data rollup — the shared substrate the score / narrative / model
layers read.

`engine.altdata` produces CROSS-SECTIONAL signal lists (top congress buys, top
contract winners, …). This module INVERTS them into one record per ticker, so any
downstream consumer (the per-stock conviction chip, theme discovery, the falsifiable
ledger, the Claude-CLI brain) can look a ticker up in O(1):

    data/altdata/by_ticker.json
    { "tickers": { "EFX": {convergence_score, channels, congress_net, gov_contract_usd_30d,
                            insider_net_usd, lobbying_usd, dpi_lean, trump_side, donor_usd}, ... } }

Display / context-only. Pure read of the feed signals; no network, no LLM. The
`convergence_score` = count of DISTINCT independent channels lit on a ticker — the
connection / unusual-activity measure. Corporate-PAC donations are recorded but do
NOT count toward convergence (nearly every large-cap donates, so it would over-fire).
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from lib import config

log = logging.getLogger(__name__)


def _slot(by: dict, tk) -> dict | None:
    tk = (str(tk).strip() if tk is not None else "")
    if not tk or tk.lower() in ("nan", "none", "n/a"):
        return None
    return by.setdefault(tk, {"ticker": tk, "channels": []})


def build(feed: dict) -> dict:
    """Invert feed['signals'] into a per-ticker dict and persist it."""
    s = (feed or {}).get("signals", {})
    by: dict[str, dict] = {}

    for r in s.get("political", {}).get("buys", []):
        rec = _slot(by, r.get("ticker"))
        if rec:
            rec["congress_net"] = r.get("net")
            rec["congress_members"] = r.get("members")
            rec["channels"].append("congress_buy")
    for r in s.get("gov_contracts", []):
        rec = _slot(by, r.get("ticker"))
        if rec:
            rec["gov_contract_usd_30d"] = r.get("total_usd")
            rec["channels"].append("gov_contract")
    for r in s.get("lobbying", []):
        rec = _slot(by, r.get("ticker"))
        if rec:
            rec["lobbying_usd"] = r.get("spend_usd")
            rec["channels"].append("lobbying")
    for r in s.get("insiders", {}).get("buys", []):
        rec = _slot(by, r.get("ticker"))
        if rec:
            rec["insider_net_usd"] = r.get("net_usd")
            rec["channels"].append("insider_buy")
    for r in s.get("offexchange", []):
        if r.get("lean") == "accumulation":
            rec = _slot(by, r.get("ticker"))
            if rec:
                rec["dpi_lean"] = "accumulation"
                rec["channels"].append("darkpool_accum")
    for r in s.get("inst_13f", {}).get("adds", [])[:15]:
        rec = _slot(by, r.get("ticker"))
        if rec and "13f_add" not in rec["channels"]:
            rec["channels"].append("13f_add")
    for r in s.get("cnbc", []):
        if (r.get("Direction") or "").lower() in ("buy", "final trade"):
            rec = _slot(by, r.get("Ticker"))
            if rec and "cnbc_pick" not in rec["channels"]:
                rec["channels"].append("cnbc_pick")
    for r in s.get("trump", []):
        if r.get("side"):
            rec = _slot(by, r.get("ticker"))
            if rec:
                rec["trump_side"] = r.get("side")
                # a single 'trump' channel — a buy+sell round-trip on one name is one
                # source of conviction, not two (avoid a false 2-channel convergence)
                if "trump" not in rec["channels"]:
                    rec["channels"].append("trump")
    # donors recorded but NOT a convergence channel (too broad)
    for r in s.get("corporate_donors", []):
        rec = _slot(by, r.get("ticker"))
        if rec:
            rec["donor_usd"] = r.get("total_usd")

    for rec in by.values():
        rec["channels"] = sorted(set(rec["channels"]))
        rec["convergence_score"] = len(rec["channels"])
        rec["trump_linked"] = any(c.startswith("trump") for c in rec["channels"])

    now = datetime.now(timezone.utc)
    out = {
        "schema": "altdata.by_ticker.v1",
        "as_of": (feed or {}).get("as_of") or now.date().isoformat(),
        "generated_utc": now.isoformat(),
        "n_tickers": len(by),
        "note": "Display/context-only per-ticker alt-data rollup. convergence_score = "
                "distinct independent channels; donors excluded from the score.",
        "tickers": by,
    }
    _write(out)
    log.info("altdata by_ticker: %d tickers, %d with convergence>=2",
             len(by), sum(1 for r in by.values() if r["convergence_score"] >= 2))
    return out


def _write(out: dict) -> None:
    for base in (config.data_dir() / "altdata", config.ROOT / "site" / "altdata"):
        base.mkdir(parents=True, exist_ok=True)
        (base / "by_ticker.json").write_text(json.dumps(out, indent=2, default=str))


def load() -> dict:
    p = config.data_dir() / "altdata" / "by_ticker.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except Exception:  # noqa: BLE001
        return {}
