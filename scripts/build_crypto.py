"""Build the Crypto Intelligence Cockpit -> site/crypto.html.

The hub is a class-level display surface.  It reads the existing Bitcoin
authority contract plus additive crypto-class state and never writes a score,
strategy result, or forward ledger.
"""
from __future__ import annotations

import json
import logging
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd
from jinja2 import Environment, FileSystemLoader

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import alt_cycle, btc_mtf  # noqa: E402
from engine.btc_options import build_contract as build_btc_options, write_contract as write_btc_options  # noqa: E402
from engine.crypto_market_state import build_market_state  # noqa: E402
from engine.crypto_universe import breadth_read, load_universe  # noqa: E402
from engine.eth_state import build_states as build_asset_states  # noqa: E402
from engine.event_calendar import us_macro_events  # noqa: E402
from lib import config, store  # noqa: E402
from lib.illus import illus, regime_tape  # noqa: E402
from lib.pages import rendered_ticker_pages, write_page  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("build_crypto")


def _series(group: str, name: str, columns: tuple[str, ...] = ("close", "close_price")):
    frame = store.read(group, name)
    if frame is None or frame.empty:
        return pd.Series(dtype=float)
    for column in columns:
        if column in frame.columns:
            return pd.to_numeric(frame[column], errors="coerce").dropna().sort_index()
    return pd.Series(dtype=float)


def _payload(series: pd.Series, days: int = 90) -> dict:
    clean = series.dropna().tail(days)
    return {
        "dates": [str(pd.Timestamp(x).date()) for x in clean.index],
        "vals": [float(x) for x in clean.to_numpy()],
    }


def _money(value, *, compact: bool = False) -> str:
    if value is None or pd.isna(value):
        return "—"
    value = float(value)
    if compact:
        if abs(value) >= 1e12:
            return f"${value / 1e12:,.2f}T"
        if abs(value) >= 1e9:
            return f"${value / 1e9:,.1f}B"
        if abs(value) >= 1e6:
            return f"${value / 1e6:,.0f}M"
    if abs(value) < 1:
        return f"${value:,.4f}"
    if abs(value) < 100:
        return f"${value:,.2f}"
    return f"${value:,.0f}"


def _pct(value, digits: int = 1, signed: bool = True) -> str:
    if value is None or pd.isna(value):
        return "—"
    sign = "+" if signed and float(value) > 0 else ""
    return f"{sign}{float(value):,.{digits}f}%"


def _state_zh(state: str) -> str:
    return {
        "Rising": "上升",
        "Falling": "下降",
        "Steady": "平稳",
        "Unavailable": "暂无",
        "Extreme fear": "极度恐惧",
        "Fearful": "恐惧",
        "Neutral": "中性",
        "Greedy": "贪婪",
        "Extreme greed": "极度贪婪",
        "Leading": "领先",
        "Firm": "稳健",
        "Weak": "偏弱",
        "Fading": "走弱",
        "Range": "震荡",
        "Building": "积累中",
        "Building history": "积累历史中",
        "High participation": "参与活跃",
        "Quiet tape": "交投清淡",
        "Normal": "正常",
        "Longs crowded": "多头拥挤",
        "Shorts paying": "空头付费",
        "Balanced": "均衡",
        "Leverage elevated": "杠杆偏高",
        "Leverage light": "杠杆偏低",
        "Leverage normal": "杠杆正常",
        "Volatility hot": "波动偏热",
        "Volatility compressed": "波动受压",
        "Volatility normal": "波动正常",
        "Alt participation broad": "山寨参与广泛",
        "Bitcoin-led": "比特币主导",
        "Mixed participation": "参与度混合",
        "Broad": "广泛",
        "Narrow": "狭窄",
        "Mixed": "混合",
    }.get(state, state)


def _load_e0(site: Path) -> dict:
    path = site / "crypto_cockpit.json"
    if not path.exists():
        return {
            "as_of": "—",
            "hero": {
                "price": None,
                "change_24h_pct": None,
                "stance_en": "Unavailable",
                "stance_zh": "暂无",
                "summary_en": "Bitcoin authority contract is awaiting its next build.",
                "summary_zh": "比特币权威合约正在等待下一次构建。",
                "exposure_pct": 0,
                "gate_active": False,
            },
            "axes": [],
        }
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        log.warning("crypto cockpit E0 read failed: %s", exc)
        return _load_e0(Path("__missing__"))


def _enrich_universe(rows: list[dict]) -> list[dict]:
    deep = {
        "BTC": _series("coinbase", "btc_daily"),
        "ETH": _series("coinbase", "eth_daily"),
        "SOL": _series("coinbase", "sol_daily"),
    }
    for symbol in ("BTC", "ETH", "SOL"):
        if deep[symbol].empty:
            deep[symbol] = _series("yahoo", f"{symbol}-USD")
    for row in rows:
        series = deep.get(row["symbol"])
        if series is not None and len(series) >= 30:
            hist = series.tail(90)
            row["spark_dates"] = [str(pd.Timestamp(x).date()) for x in hist.index]
            row["spark_values"] = [float(x) for x in hist.to_numpy()]
            row["history_days"] = len(hist)
            row["history_chip"] = "90D"
        if len(row.get("spark_values") or []) >= 4:
            row["spark"] = illus(
                {"dates": row["spark_dates"], "vals": row["spark_values"]},
                kind="line",
                accent="var(--tone)",
                height=42,
                max_points=50,
                value_fmt="{:,.3g}",
                aria_en=f"{row['symbol']} available price history",
            )
        else:
            row["spark"] = ""
        row["price_label"] = _money(row.get("price"))
        row["change_label"] = _pct(row.get("change_24h"))
        row["state_zh"] = _state_zh(row["state"])
        row["live_symbol"] = f"{row['symbol']}-USD"
    return rows


def _allocation(signals: pd.DataFrame, market: dict) -> dict:
    if signals is None or signals.empty or "close" not in signals.columns:
        return {
            "btc": 0,
            "eth": 0,
            "alts": 0,
            "cash": 100,
            "exposure": 0,
            "season": "Unavailable",
            "season_score": None,
            "regime": "neutral",
            "ethbtc": None,
        }
    cfg = config.load()["vector"]["alt_cycle"]
    close = pd.to_numeric(signals["close"], errors="coerce").dropna()
    btc_bars = store.read("coinbase", "btc_daily")
    high = (
        pd.to_numeric(btc_bars["high"], errors="coerce").reindex(close.index).ffill()
        if btc_bars is not None and "high" in btc_bars.columns
        else close
    )
    ladder = btc_mtf.mtf_ladder(close, high).get("ladder") or {}
    regime = ladder.get("regime")
    eth = _series("yahoo", "ETH-USD")
    eb = alt_cycle.ethbtc_signal(eth, close, cfg)
    score, bucket = alt_cycle.alt_season_score(
        eb, market.get("btc_dominance"), cfg
    )
    grid = alt_cycle.alloc_grid(regime, bucket)

    # Load-bearing parity with the retired allocation page: alloc_optimal sets
    # the TOTAL crypto budget; the alt grid only splits that budget.
    latest = signals.iloc[-1]
    alloc_pct = (
        round(100 * latest["alloc_optimal"])
        if pd.notna(latest.get("alloc_optimal"))
        else 0
    )
    risk_assets = grid["btc"] + grid["eth"] + grid["alts"]
    if risk_assets > 0 and alloc_pct > 0:
        btc_pct = round(alloc_pct * grid["btc"] / risk_assets)
        eth_pct = round(alloc_pct * grid["eth"] / risk_assets)
        alt_pct = alloc_pct - btc_pct - eth_pct
    else:
        btc_pct = eth_pct = alt_pct = 0
    return {
        "btc": btc_pct,
        "eth": eth_pct,
        "alts": alt_pct,
        "cash": 100 - alloc_pct,
        "exposure": alloc_pct,
        "season": bucket,
        "season_score": score,
        "regime": grid["regime_key"],
        "ethbtc": round(eb["level"], 4) if eb and eb.get("level") is not None else None,
    }


def _asset_lanes(e0: dict, asset_states: dict) -> list[dict]:
    hero = e0.get("hero") or {}
    lanes = [
        {
            "symbol": "BTC",
            "live_symbol": "BTC-USD",
            "name": "Bitcoin",
            "name_zh": "比特币",
            "price": _money(hero.get("price")),
            "change": _pct(hero.get("change_24h_pct")),
            "state": hero.get("stance_en") or "Unavailable",
            "state_zh": hero.get("stance_zh") or "暂无",
            "summary": hero.get("summary_en") or "",
            "summary_zh": hero.get("summary_zh") or "",
            "tone": "bear" if "OFF" in str(hero.get("stance_en")) else "bull",
            "href": "vector.html",
            "cta": "Open Bitcoin Vector",
            "cta_zh": "打开比特币向量",
        }
    ]
    names = {
        "ETH": ("Ethereum", "以太坊"),
        "SOL": ("Solana", "索拉纳"),
    }
    for symbol in ("ETH", "SOL"):
        state = ((asset_states.get("assets") or {}).get(symbol) or {})
        trend = state.get("trend") or {}
        coverage = state.get("coverage") or {}
        name_en, name_zh = names[symbol]
        lanes.append(
            {
                "symbol": symbol,
                "live_symbol": f"{symbol}-USD",
                "name": name_en,
                "name_zh": name_zh,
                "price": _money(state.get("price")),
                "change": _pct(state.get("change_30d_pct")),
                "state": trend.get("state") or "Unavailable",
                "state_zh": trend.get("state_zh") or "暂无",
                "summary": state.get("summary_en") or coverage.get("note_en") or "",
                "summary_zh": state.get("summary_zh") or coverage.get("note_zh") or "",
                "coverage": coverage.get("note_en") or "",
                "coverage_zh": coverage.get("note_zh") or "",
                "tone": state.get("tone") or "neutral",
                "href": "crypto.html#market-board",
                "cta": "See the class board",
                "cta_zh": "查看全市场看板",
            }
        )
    return lanes


def _equities(linkable: frozenset[str] | None = None) -> list[dict]:
    """Crypto-rails equities shelf.

    Members come from data/baskets/membership.json, which names symbols we do
    not necessarily render a dossier for (IBIT and MSTR were both linked to
    404s). `linkable` is the set of tickers that ship a page; a member without
    one keeps its tile and its quote but loses the anchor. None = link
    everything, the pre-filter behaviour.
    """
    try:
        membership = json.loads(
            (config.data_dir() / "baskets" / "membership.json").read_text(encoding="utf-8")
        )
        basket = (membership.get("baskets") or {}).get("crypto_rails") or {}
        members = [
            m for m in (basket.get("members") or []) if not m.get("removed")
        ][:8]
    except Exception:
        members = []
    out = []
    for member in members:
        ticker = str(member.get("ticker") or "").upper()
        close = _series("yahoo", ticker)
        change = 100 * (close.iloc[-1] / close.iloc[-21] - 1) if len(close) > 21 else None
        state = (
            "Firm" if change is not None and change > 5 else (
                "Fading" if change is not None and change < -5 else "Range"
            )
        )
        out.append(
            {
                "ticker": ticker,
                "price": _money(close.iloc[-1]) if not close.empty else "—",
                "change": _pct(change),
                "state": state,
                "state_zh": _state_zh(state),
                "tone": "bull" if state == "Firm" else ("bear" if state == "Fading" else "neutral"),
                "href": (f"stocks/{ticker}.html"
                         if linkable is None or ticker in linkable else None),
            }
        )
    return out


def _calendar(as_of: str) -> list[dict]:
    try:
        today = date.fromisoformat(as_of)
    except Exception:
        today = datetime.now(timezone.utc).date()
    macro = [
        event
        for event in us_macro_events(today, horizon_days=45, use_fred=False)
        if event.get("impact") == "high"
    ][:5]
    out = [
        {
            "date": event["date"],
            "day": event["date"][5:],
            "label": event["label"],
            "label_zh": event["label_zh"],
            "type": event["type"],
            "note": f"{event.get('time_et') or 'Time TBA'} ET · macro catalyst",
            "note_zh": f"{event.get('time_et') or '时间待定'} 美东 · 宏观催化",
        }
        for event in macro
    ]
    halving = date(2028, 4, 15)
    out.append(
        {
            "date": str(halving),
            "day": "2028",
            "label": "Bitcoin halving window",
            "label_zh": "比特币减半窗口",
            "type": "BTC",
            "note": f"Estimated · {max((halving - today).days, 0):,} days",
            "note_zh": f"估计 · 约 {max((halving - today).days, 0):,} 天",
        }
    )
    return out[:6]


def build(site_dir: Path | None = None) -> Path:
    cfg = config.load()
    site = Path(site_dir) if site_dir is not None else Path(cfg["storage"]["site_dir"])
    site.mkdir(parents=True, exist_ok=True)
    e0 = _load_e0(site)
    market = build_market_state()
    universe = _enrich_universe(load_universe(50))
    breadth = breadth_read(universe)
    breadth["state_zh"] = _state_zh(breadth["state"])
    signals = store.read("vector", "signals")
    allocation = _allocation(signals, market)
    asset_states = build_asset_states()
    options_contract = build_btc_options()
    write_btc_options(site, options_contract)
    (site / "crypto_asset_states.json").write_text(
        json.dumps(asset_states, ensure_ascii=False, allow_nan=False, indent=2) + "\n",
        encoding="utf-8",
    )
    class_state = {
        "schema": "crypto.class_state/v1",
        "tier": "display",
        "display_only": True,
        "as_of": market["as_of"],
        "market": {
            "stance": market.get("stance"),
            "total_state": market.get("total_state"),
            "dominance_state": market.get("dominance_state"),
            "fear_state": market.get("fear_state"),
            "breadth_state": breadth.get("state"),
        },
        "flows": {
            key: value.get("state") for key, value in (market.get("flows") or {}).items()
        },
        "heat": {
            key: value.get("state") for key, value in (market.get("heat") or {}).items()
        },
        "assets": {
            symbol: {
                "trend": (state.get("trend") or {}).get("state"),
                "risk": (state.get("risk") or {}).get("state"),
                "relative": (state.get("relative") or {}).get("state"),
                "coverage": (state.get("coverage") or {}).get("note_en"),
            }
            for symbol, state in (asset_states.get("assets") or {}).items()
        },
    }
    (site / "crypto_class_state.json").write_text(
        json.dumps(class_state, ensure_ascii=False, allow_nan=False, indent=2) + "\n",
        encoding="utf-8",
    )

    cap_history = market["history"]
    cap_trillions = {
        "dates": cap_history["dates"],
        "vals": [value / 1e12 for value in cap_history["vals"]],
    }
    tape = regime_tape(
        cap_trillions,
        regimes=market["regimes"],
        events=[
            {
                "date": "2024-04-20",
                "label_en": "Fourth Bitcoin halving",
                "label_zh": "第四次比特币减半",
            }
        ],
        height=218,
        accent="var(--crypto)",
        value_fmt="${:,.2f}T",
        aria_en="Derived total crypto market cap with descriptive class-regime bands",
        aria_zh="衍生加密总市值及描述性市场阶段",
    )
    for flow in market["flows"].values():
        flow["state_zh"] = _state_zh(flow["state"])
    for heat in market["heat"].values():
        heat["state_zh"] = _state_zh(heat["state"])

    vm = {
        "as_of": market["as_of"],
        "built": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "market": market,
        "market_total": _money(market["total_market_cap"], compact=True),
        "market_30d": _pct(market["total_30d_pct"]),
        "dominance": _pct(market["btc_dominance"], signed=False),
        "dominance_30d": _pct(market["dominance_30d"]),
        "fear": (
            f"{market['fear_greed']:.0f}" if market["fear_greed"] is not None else "—"
        ),
        "total_state_zh": _state_zh(market["total_state"]),
        "dominance_state_zh": _state_zh(market["dominance_state"]),
        "fear_state_zh": _state_zh(market["fear_state"]),
        "tape": tape,
        "top_assets": universe[:20],
        "more_assets": universe[20:50],
        "universe_count": len(universe),
        "universe_sources": sorted({row.get("source") for row in universe if row.get("source")}),
        "breadth": breadth,
        "allocation": allocation,
        "e0": e0,
        "lanes": _asset_lanes(e0, asset_states),
        "asset_states": asset_states,
        "btc_options": options_contract,
        "equities": _equities(rendered_ticker_pages(site)),
        "calendar": _calendar(market["as_of"]),
        "fmt_money": _money,
        "fmt_pct": _pct,
    }

    env = Environment(
        loader=FileSystemLoader(str(config.ROOT / "templates")),
        autoescape=True,
    )
    try:
        from engine import i18n

        env.globals.update(td=i18n.td, tr=i18n.tr)
    except Exception:
        env.globals.update(td=lambda value: value, tr=lambda value: value)
    html = env.get_template("crypto.html.j2").render(**vm)
    html = re.sub(r">\s+<", "> <", html)
    output = site / "crypto.html"
    write_page(output, html, encoding="utf-8")
    log.info(
        "wrote %s (%d KB, %d universe assets)",
        output,
        len(html.encode("utf-8")) // 1024,
        len(universe),
    )
    return output


if __name__ == "__main__":
    build()
