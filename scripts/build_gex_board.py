"""Build the Options Desk — dealer-gamma + options-flow page -> site/gex.html (display-only).

Standalone (like build_discovery.py). For a broad universe of liquid optionable
underlyings it fetches the live Cboe delayed chain, runs engine.gex_model (the rich
modeling layer: net-gamma profile curve, GEX-by-strike walls, strike×expiry heatmap,
vol smile + IV term structure, expected move, max-pain per expiry), and writes:

  * site/gex/<KEY>.json  — one rich payload per underlying, fetched on demand by the
                           page so any prebuilt ticker is instantly look-up-able.
  * site/gex/index.json  — a lightweight manifest (regime / net-GEX / flip / IV per
                           symbol) that drives the at-a-glance board + the search.
  * site/gex.html        — the interactive shell (templates/gex.html.j2 + site/gex.js).

HONEST FRAMING (carried onto the page): daily delayed Cboe levels, NOT live intraday
flow; a VOL-REGIME + LEVELS MAP, not a buy list; the dealer long-call/short-put SIGN is
an unobservable assumption — robust for indices, fragile for single names. See
LIMITATIONS.md.

Run: .venv/bin/python -m scripts.build_gex_board
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from jinja2 import Environment, FileSystemLoader

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config  # noqa: E402
from lib.pages import write_page  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("build_gex_board")

# (cboe symbol, key, en label, zh label, group). cboe index tickers carry a leading
# underscore (_SPX). Groups drive the board's section headers + search filters. A
# failed/thin symbol is skipped gracefully — partial coverage is still useful.
UNIVERSE = [
    ("_SPX", "SPX", "S&P 500", "标普500", "Index"),
    ("_NDX", "NDX", "Nasdaq 100", "纳指100", "Index"),
    ("_RUT", "RUT", "Russell 2000", "罗素2000", "Index"),
    ("SPY", "SPY", "S&P 500 ETF", "标普500 ETF", "ETF"),
    ("QQQ", "QQQ", "Nasdaq 100 ETF", "纳指100 ETF", "ETF"),
    ("IWM", "IWM", "Russell 2000 ETF", "小盘ETF", "ETF"),
    ("DIA", "DIA", "Dow ETF", "道指ETF", "ETF"),
    ("SMH", "SMH", "Semiconductors ETF", "半导体ETF", "Sector ETF"),
    ("XLK", "XLK", "Technology ETF", "科技板块ETF", "Sector ETF"),
    ("XLF", "XLF", "Financials ETF", "金融板块ETF", "Sector ETF"),
    ("XLE", "XLE", "Energy ETF", "能源板块ETF", "Sector ETF"),
    ("GLD", "GLD", "Gold ETF", "黄金ETF", "Macro ETF"),
    ("TLT", "TLT", "20Y+ Treasury ETF", "长债ETF", "Macro ETF"),
    ("HYG", "HYG", "High-Yield Credit ETF", "高收益债ETF", "Macro ETF"),
    ("ARKK", "ARKK", "ARK Innovation ETF", "ARK创新ETF", "Macro ETF"),
    ("NVDA", "NVDA", "Nvidia", "英伟达", "Mega-cap Tech"),
    ("AAPL", "AAPL", "Apple", "苹果", "Mega-cap Tech"),
    ("MSFT", "MSFT", "Microsoft", "微软", "Mega-cap Tech"),
    ("AMZN", "AMZN", "Amazon", "亚马逊", "Mega-cap Tech"),
    ("GOOGL", "GOOGL", "Alphabet", "谷歌", "Mega-cap Tech"),
    ("META", "META", "Meta", "Meta", "Mega-cap Tech"),
    ("TSLA", "TSLA", "Tesla", "特斯拉", "Mega-cap Tech"),
    ("AMD", "AMD", "AMD", "超威", "Semis & AI"),
    ("AVGO", "AVGO", "Broadcom", "博通", "Semis & AI"),
    ("MU", "MU", "Micron", "美光", "Semis & AI"),
    ("SMCI", "SMCI", "Super Micro", "超微电脑", "Semis & AI"),
    ("MRVL", "MRVL", "Marvell", "迈威尔", "Semis & AI"),
    ("ARM", "ARM", "Arm Holdings", "Arm", "Semis & AI"),
    ("PLTR", "PLTR", "Palantir", "Palantir", "Popular / Retail"),
    ("COIN", "COIN", "Coinbase", "Coinbase", "Popular / Retail"),
    ("MSTR", "MSTR", "MicroStrategy", "微策略", "Popular / Retail"),
    ("NFLX", "NFLX", "Netflix", "奈飞", "Popular / Retail"),
    ("BABA", "BABA", "Alibaba", "阿里巴巴", "Popular / Retail"),
    ("HOOD", "HOOD", "Robinhood", "Robinhood", "Popular / Retail"),
    ("UBER", "UBER", "Uber", "优步", "Popular / Retail"),
    ("GME", "GME", "GameStop", "游戏驿站", "Popular / Retail"),
]

# dividend yields used by the dividend-adjusted greeks (small effect; names -> 0)
DIV_Q = {"SPX": 0.013, "SPY": 0.013, "QQQ": 0.006, "IWM": 0.013, "DIA": 0.018,
         "NDX": 0.008, "RUT": 0.013, "GLD": 0.0, "TLT": 0.038, "HYG": 0.058,
         "XLK": 0.006, "XLF": 0.016, "XLE": 0.032, "SMH": 0.004}

HISTORY_DAYS = 40  # net-GEX history sparkline depth (from the stored daily summary)
# Concurrent Cboe chain fetches. The free cdn.cboe.com feed rate-limits (HTTP 429) under
# heavy parallelism, so keep this modest — at ~313 symbols, 5 workers covers the board in
# a few minutes without tripping the limiter (12 lost ~half the universe to 429s).
MAX_WORKERS = 5
FETCH_TRIES = 5    # extra 429-aware retries on top of http_get's own backoff
# honesty gate for DERIVED (basket-member) names: skip when the chain is too thin or one
# position dominates so much the dealer long-call/short-put SIGN can't be trusted.
THEME_MIN_STRIKES = 8
THEME_MAX_OI_SHARE = 0.55


def _history(key: str) -> list[dict]:
    """Last HISTORY_DAYS of stored daily {date, net_gex_bn, regime, iv30} for the
    sparkline + the short-window IV rank. Reads the cboe summary parquet the daily
    collector accrues; empty if absent (so newly-added basket names just lack history
    until it accrues — iv-rank / sparkline degrade gracefully). iv30 is converted to
    PERCENT to match summary.iv30."""
    try:
        from lib import store
        df = store.read("cboe", f"gex_{key}")
        if df is None or not len(df) or "net_gex_bn" not in df.columns:
            return []
        df = df.tail(HISTORY_DAYS)
        regs = df.get("gamma_regime", pd.Series([None] * len(df)))
        ivs = df.get("iv30", pd.Series([None] * len(df)))
        return [{"date": str(pd.Timestamp(i).date()),
                 "net_gex_bn": (round(float(v), 2) if pd.notna(v) else None),
                 "regime": (str(r) if pd.notna(r) else None),
                 "iv30": (round(float(iv) * 100, 2) if pd.notna(iv) else None)}
                for i, v, r, iv in zip(df.index, df["net_gex_bn"], regs, ivs)]
    except Exception:  # noqa: BLE001 — history is a nicety, never fatal
        return []


def _fetch_chain(adapter, sym: str):
    """adapter._chain with extra 429-aware backoff (the CDN throttles at scale). A small
    random jitter desynchronises the worker pool so the limiter clears between bursts."""
    import random
    import time
    for i in range(FETCH_TRIES):
        try:
            if i == 0:
                time.sleep(random.random() * 0.4)        # initial jitter
            return adapter._chain(sym)
        except Exception as e:  # noqa: BLE001
            if i < FETCH_TRIES - 1 and ("429" in str(e) or "too many" in str(e).lower()):
                time.sleep(3.0 * (i + 1) + random.random() * 2.0)
                continue
            raise


def _build_one(adapter, row: dict) -> tuple[dict, dict] | None:
    """Fetch + model one underlying -> (full payload, manifest row). None on failure or
    when a derived name fails the honesty gate (too thin / too concentrated to trust)."""
    from engine.gex_model import build_model
    sym, key, src = row["sym"], row["key"], row.get("src", "core")
    try:
        chain, spot = _fetch_chain(adapter, sym)
    except Exception as e:  # noqa: BLE001 — partial board still useful
        log.warning("gex: %s chain failed: %s", sym, e)
        return None
    gcfg = adapter.cfg.get("gex", {})
    cfg = {"q": DIV_Q.get(key, 0.0), "r": 0.043,
           "max_expiry_days": gcfg.get("max_expiry_days", 365)}
    meta = {"key": key, "en": row["en"], "zh": row["zh"], "grp": row["grp"],
            "src": src, "asof": str(date.today())}
    model = build_model(chain, spot, cfg, meta=meta, history=_history(key))
    if model is None:
        return None
    s = model["summary"]
    # derived-name honesty gate: don't surface a basket member whose sign we can't trust
    if src == "theme" and ((s.get("n_strikes") or 0) < THEME_MIN_STRIKES
                           or (s.get("top_oi_share") or 1.0) > THEME_MAX_OI_SHARE):
        return None
    em = model["expected_move"]
    vh = model.get("vol_hole") or {}
    tilt = model.get("tilt") or {}
    skew = s.get("skew") or {}
    ivr = s.get("iv_rank") or {}
    manifest = {
        "key": key, "en": row["en"], "zh": row["zh"], "grp": row["grp"], "src": src,
        "spot": s["spot"], "regime": s["regime"], "tier": s["tier"],
        "thin": (s["tier"] == "thin_chain"),
        "net_gex_bn": s["net_gex_bn"], "gamma_flip": s["gamma_flip"],
        "dist_to_flip_pct": s["dist_to_flip_pct"], "iv30": s["iv30"],
        "call_wall": s["call_wall"], "put_wall": s["put_wall"],
        "call_wall_band": s.get("call_wall_band"), "put_wall_band": s.get("put_wall_band"),
        "max_pain": s["max_pain"], "daily_move_pct": em.get("daily_pct"),
        "put_call_oi_ratio": s["put_call_oi_ratio"],
        "vh_state": vh.get("state"), "vh_bias": vh.get("bias"),
        "tilt_read": tilt.get("read"), "skew_tone": skew.get("tone"),
        "iv_rank_band": ivr.get("band"),
        "asof": str(date.today()),
    }
    return model, manifest


def _basket_universe(existing: set[str]) -> list[tuple]:
    """Derive the thematic-basket members from data/baskets/membership.json so the board
    auto-covers every curated theme name. Each row is (cboe_sym, key, en, zh, grp) with
    grp='Theme · <category>'; de-duped against the curated UNIVERSE (curated group wins)
    and across baskets (first basket's category wins). name left blank (ticker-centric)."""
    path = config.ROOT / "data" / "baskets" / "membership.json"
    try:
        data = json.loads(path.read_text())
    except Exception as e:  # noqa: BLE001 — basket expansion is additive, never fatal
        log.warning("gex: basket membership unreadable (%s); core universe only", e)
        return []
    rows, seen = [], set()
    for b in data.get("baskets", {}).values():
        grp = f"Theme · {b.get('category') or 'Other'}"
        for m in b.get("members", []):
            if m.get("removed"):
                continue
            tk = (m.get("ticker") or "").strip().upper()
            if not tk or tk in existing or tk in seen:
                continue
            seen.add(tk)
            rows.append((tk, tk, "", "", grp))
    return rows


def _ordered_groups(universe: list[tuple]) -> list[str]:
    """Board section order: curated groups first (in UNIVERSE order), then the
    Theme · <category> groups alphabetically."""
    core, themes = [], []
    for _, _, _, _, grp in universe:
        bucket = themes if grp.startswith("Theme · ") else core
        if grp not in bucket:
            bucket.append(grp)
    return core + sorted(themes)


# Index/ETF GEX is the *validatable* slice — the dealer long-call/short-put SIGN is
# robust for broad indices, fragile for single names (LIMITATIONS.md) — so the daily
# archive snapshot keeps that slice plus the market-wide CBOE SKEW / put-call context.
# scripts.archive_signals folds data/gex/latest.json into the unified signal_archive
# corpus, so the day's options state is recorded PIT alongside the regime labels (the
# un-backfillable input the eventual GEX→forward-vol validation will train on).
ARCHIVE_KEYS = ("SPX", "NDX", "RUT", "SPY", "QQQ", "IWM", "DIA")
_ARCHIVE_FIELDS = ("spot", "regime", "tier", "net_gex_bn", "gamma_flip",
                   "dist_to_flip_pct", "iv30", "put_call_oi_ratio",
                   "call_wall", "put_wall", "max_pain", "daily_move_pct")


def _market_context(data_dir: Path) -> dict:
    """Latest market-wide options context (CBOE SKEW + index/equity put-call) from the
    collector parquets, co-located so the snapshot pairs the systematic tail read with
    the index GEX state. Best-effort — a missing series just drops that field."""
    ctx: dict = {}
    try:
        sk = pd.read_parquet(data_dir / "cboe" / "skew.parquet")["skew"].dropna()
        if len(sk):
            ctx["skew"] = round(float(sk.iloc[-1]), 2)
            ctx["skew_asof"] = str(pd.Timestamp(sk.index[-1]).date())
    except Exception:  # noqa: BLE001 — context is a nicety, never fatal
        pass
    try:
        pc = pd.read_parquet(data_dir / "cboe" / "putcall.parquet").dropna(how="all")
        if len(pc):
            last = pc.iloc[-1]
            for c in ("index_pc_ratio", "equity_pc_ratio"):
                if c in pc.columns and pd.notna(last.get(c)):
                    ctx[c] = round(float(last[c]), 3)
            ctx["put_call_asof"] = str(pd.Timestamp(pc.index[-1]).date())
    except Exception:  # noqa: BLE001
        pass
    return ctx


def _write_archive_snapshot(manifest: list[dict], data_dir: Path) -> None:
    """Write data/gex/latest.json — the index/ETF GEX summary + market context — for
    scripts.archive_signals to fold into the signal_archive corpus. Best-effort: a
    failure here never affects the page build (callers do not depend on it)."""
    try:
        by_key = {m["key"]: m for m in manifest}
        indices = {k: {f: by_key[k].get(f) for f in _ARCHIVE_FIELDS}
                   for k in ARCHIVE_KEYS if k in by_key}
        if not indices:
            return
        snap = {"asof": str(date.today()), "source": "cboe_delayed",
                "indices": indices, "market": _market_context(data_dir)}
        out = data_dir / "gex"
        out.mkdir(parents=True, exist_ok=True)
        (out / "latest.json").write_text(json.dumps(snap, default=float, indent=1))
        log.info("gex: archive snapshot -> %s (%d indices)", out / "latest.json", len(indices))
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("gex: archive snapshot skipped: %s", e)


def _write_gex_state(model: dict, key: str, gex_state_dir: "Path") -> None:
    """Derive, validate, and write options_structure.gex_state/<KEY>.json.

    Package C emitter — zero new network calls; derived entirely from the model
    already computed by _build_one.  A failure here is NEVER fatal to the board
    build (additive side-effect, logged and swallowed).
    """
    from engine.gex_state import compute_gex_state
    from engine.options_structure import validate_gex_state

    try:
        asof = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")
        state = compute_gex_state(model, key, asof=asof)
        if state is None:
            log.debug("gex_state: %s skipped (thin/no options)", key)
            return

        errors = validate_gex_state(state)
        if errors:
            log.warning("gex_state: %s schema errors: %s", key, errors)
            return

        gex_state_dir.mkdir(parents=True, exist_ok=True)
        out_path = gex_state_dir / f"{key}.json"
        out_path.write_text(json.dumps(state, default=float, allow_nan=False, separators=(",", ":")))
        log.debug("gex_state: wrote %s", out_path)
    except Exception as e:  # noqa: BLE001 — never abort the board for a gex_state failure
        log.warning("gex_state: %s failed: %s", key, e)


def main() -> int:
    from concurrent.futures import ThreadPoolExecutor
    from collectors.cboe import GexAdapter
    adapter = GexAdapter()
    site = config.ROOT / config.load()["storage"]["site_dir"]
    out_dir = site / "gex"
    out_dir.mkdir(parents=True, exist_ok=True)
    gex_state_dir = site / "options_structure" / "gex_state"

    core_keys = {key for _, key, *_ in UNIVERSE}
    universe = list(UNIVERSE) + _basket_universe(core_keys)
    rows = [{"sym": s, "key": k, "en": e, "zh": z, "grp": g,
             "src": ("theme" if g.startswith("Theme · ") else "core")}
            for s, k, e, z, g in universe]
    attempted: dict[str, int] = {}
    for r in rows:
        attempted[r["grp"]] = attempted.get(r["grp"], 0) + 1
    log.info("gex: universe = %d symbols (%d core + %d theme members)",
             len(rows), len(UNIVERSE), len(rows) - len(UNIVERSE))

    def work(row):
        # the WHOLE unit (fetch → model → serialize → write) is guarded so one bad symbol
        # (fetch error, OS write failure, or a stray NaN that allow_nan=False rejects) is
        # skipped, never aborting the board or crashing main() — partial coverage is fine.
        try:
            res = _build_one(adapter, row)
            if not res:
                return None
            model, mrow = res
            (out_dir / f"{mrow['key']}.json").write_text(
                json.dumps(model, default=float, allow_nan=False, separators=(",", ":")))
            # Package C: emit gex_state after board payload — zero new network calls
            _write_gex_state(model, mrow["key"], gex_state_dir)
            return mrow
        except Exception as e:  # noqa: BLE001 — one bad symbol never aborts the board
            log.warning("gex: %s errored: %s", row["key"], e)
            return None

    manifest: list[dict] = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        for mrow in ex.map(work, rows):
            if mrow:
                manifest.append(mrow)

    if not manifest:
        log.error("gex: no symbols computed; leaving prior site/gex.html in place")
        return 0

    # per-group coverage (covered of attempted) so the board can be honest about gaps
    covered: dict[str, int] = {}
    for m in manifest:
        covered[m["grp"]] = covered.get(m["grp"], 0) + 1
    coverage = {g: {"covered": covered.get(g, 0), "total": t} for g, t in attempted.items()}
    coverage["__all__"] = {"covered": len(manifest), "total": len(rows)}

    (out_dir / "index.json").write_text(json.dumps(manifest, default=float, separators=(",", ":")))
    _write_archive_snapshot(manifest, config.data_dir())

    built = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    from engine.i18n import td, tr
    env = Environment(loader=FileSystemLoader(str(config.ROOT / "templates")), autoescape=True)
    env.globals.update(td=td, tr=tr)
    present = {m["grp"] for m in manifest}
    groups = [g for g in _ordered_groups(universe) if g in present]
    keys = {m["key"] for m in manifest}
    default_key = "SPY" if "SPY" in keys else manifest[0]["key"]
    html = env.get_template("gex.html.j2").render(
        manifest=manifest, groups=groups, built=built, default_key=default_key,
        coverage=coverage, coverage_json=json.dumps(coverage, default=float),
        manifest_json=json.dumps(manifest, default=float))
    write_page(site / "gex.html", html)
    log.info("gex: wrote %s/gex.html + %d payloads (%d of %d symbols had liquid options)",
             site, len(manifest), len(manifest), len(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
