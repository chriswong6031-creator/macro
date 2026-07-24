"""Bake the versioned per-ticker portfolio context artifact → site/data/portfolio_ctx.json.

Portfolio-Aware Intelligence, W0 (charter:
research/PORTFOLIO_BRIEF_MASTERPLAN_BY_FABLE.md §2, §6). This is the cross-repo
contract the mastermind-terminal Portfolio page consumes: the macro nightly bakes
ONE compact per-ticker context blob keyed by ticker; the terminal composes each
user's brief on demand by joining the user's holdings against this artifact — off
the render path, cacheable per day.

Design-tier law (§4): this artifact RE-EXPRESSES existing nightly reads. It
originates nothing — no new signal, score, classification, or threshold of our own.
Every stance/vocabulary string is copied VERBATIM from its source artifact. A ticker
block (or a per-desk sub-block) is OMITTED ENTIRELY when the desk has no data for it
(absence = "no desk coverage yet" on the terminal side); we never emit a null-filled
or zero-filled placeholder, and never fabricate a value.

W0 scope: the bake reads only committed source artifacts (READS ONLY — no engine
module that could advance a ledger), stubs to 3 tickers, and is NOT yet wired into
the nightly (that is W1, which flips the default to the full universe and adds the
daily.yml step). Congress rows are read from a parquet.

Usage:
    python -m scripts.build_portfolio_ctx --tickers NVDA,AAPL,XOM
    python -m scripts.build_portfolio_ctx --out site/data/portfolio_ctx.json
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SCHEMA = "portfolio_ctx.v1"
SCHEMA_V = 1

# W0 stub universe — W1 flips the default to the full holdings-eligible universe.
STUB_TICKERS = ["NVDA", "AAPL", "XOM"]

# Reuse the deterministic glance-tier lane classifier shipped in the state_of_themes
# revamp (#3250) — do NOT reimplement. Its inputs (stage_key / any_fired / raw_legs /
# div_quadrant) are theme-forensics structures assembled inside build_state_of_themes;
# they are NOT present on the compact baskets.json theme records, so for W0 every
# theme's lane is null (honest "not derivable from this artifact"). The import keeps
# the single source of truth and lets W1 wire real inputs without a vocabulary fork.
try:
    from scripts.build_state_of_themes import _classify_lane  # noqa: F401
except Exception:  # noqa: BLE001 — never let an import failure break the bake
    _classify_lane = None  # type: ignore[assignment]


# ── source loaders (every one fail-open: missing/corrupt → empty, never raises) ──

def _read_json(path: Path):
    """Load JSON from path. Return None on any error (missing / corrupt / unreadable)."""
    try:
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def load_risk_state(root: Path) -> dict:
    """site/live/risk_state.json → the `display` block (score/verdict/labels/color)."""
    d = _read_json(root / "site" / "live" / "risk_state.json")
    if not isinstance(d, dict):
        return {}
    disp = d.get("display")
    return disp if isinstance(disp, dict) else {}


def load_us_standouts(root: Path) -> dict:
    """site/factordata/us_standouts.json — gate_go + buy/watch/laggards board rows."""
    d = _read_json(root / "site" / "factordata" / "us_standouts.json")
    return d if isinstance(d, dict) else {}


def load_subsector_confluence(root: Path) -> dict:
    """site/marketdata/subsector_confluence.json — sector `class` (tailwind/…)."""
    d = _read_json(root / "site" / "marketdata" / "subsector_confluence.json")
    return d if isinstance(d, dict) else {}


def load_sector_central(root: Path) -> dict:
    """site/sectordata/sector_central.json — sector conviction labels + rotation state.

    Nightly-populated; may be absent in a fresh worktree → {} (fail-open, omit).
    """
    d = _read_json(root / "site" / "sectordata" / "sector_central.json")
    return d if isinstance(d, dict) else {}


def load_screener(root: Path) -> dict:
    """site/stagedata/screener.json → {TICKER: row} for region USA, source live.

    Keyed by upper ticker; first matching (USA, live) row wins.
    """
    d = _read_json(root / "site" / "stagedata" / "screener.json")
    rows = d.get("rows") if isinstance(d, dict) else None
    out: dict[str, dict] = {}
    if isinstance(rows, list):
        for r in rows:
            if not isinstance(r, dict):
                continue
            if r.get("region") != "USA" or r.get("source") != "live":
                continue
            t = str(r.get("ticker") or "").strip().upper()
            if t and t not in out:
                out[t] = r
    return out


def load_by_ticker(root: Path) -> dict:
    """site/altdata/by_ticker.json → tickers[T] (earnings clock lives here)."""
    d = _read_json(root / "site" / "altdata" / "by_ticker.json")
    tk = d.get("tickers") if isinstance(d, dict) else None
    return tk if isinstance(tk, dict) else {}


def load_insider(root: Path) -> dict:
    """site/factordata/insider_signals.json — keyed directly by ticker."""
    d = _read_json(root / "site" / "factordata" / "insider_signals.json")
    return d if isinstance(d, dict) else {}


def load_smartmoney(root: Path) -> dict:
    """site/factordata/smartmoney.json → by_ticker[T] (13F adds/trims)."""
    d = _read_json(root / "site" / "factordata" / "smartmoney.json")
    bt = d.get("by_ticker") if isinstance(d, dict) else None
    return bt if isinstance(bt, dict) else {}


def load_baskets(root: Path) -> dict:
    """site/basketdata/baskets.json → theme_intel.themes indexed by id.

    Provides theme meta (name / name_zh / rank / reco) for a ticker's basket ids.
    """
    d = _read_json(root / "site" / "basketdata" / "baskets.json")
    ti = d.get("theme_intel") if isinstance(d, dict) else None
    themes = ti.get("themes") if isinstance(ti, dict) else None
    out: dict[str, dict] = {}
    if isinstance(themes, list):
        for t in themes:
            if isinstance(t, dict) and t.get("id"):
                out[str(t["id"])] = t
    return out


def load_membership(root: Path) -> dict:
    """data/baskets/membership.json → {TICKER: [basket_id, …]} respecting PIT dates.

    A member is live in a basket iff it has been `added` (or has no added date) and
    not yet `removed` as of today. Inverts basket→members to ticker→baskets. Fail-open
    to {} on any error.
    """
    d = _read_json(root / "data" / "baskets" / "membership.json")
    if not isinstance(d, dict):
        return {}
    baskets = d.get("baskets")
    # membership.json shape: {"baskets": {bid: {"members": [{ticker, added, removed}]}}}
    # or a bare {bid: [...]} mapping. Handle both defensively.
    if not isinstance(baskets, dict):
        baskets = d if all(isinstance(v, (list, dict)) for v in d.values()) else {}
    today = date.today().isoformat()
    out: dict[str, list[str]] = {}
    for bid, entry in baskets.items():
        members = entry.get("members") if isinstance(entry, dict) else entry
        if not isinstance(members, list):
            continue
        for m in members:
            if not isinstance(m, dict):
                continue
            tk = str(m.get("ticker") or "").strip().upper()
            if not tk:
                continue
            added = m.get("added")
            removed = m.get("removed")
            if added and str(added) > today:
                continue  # not yet added as of today (PIT)
            if removed and str(removed) <= today:
                continue  # already removed as of today (PIT)
            out.setdefault(tk, []).append(str(bid))
    return out


def load_congress(root: Path) -> "object | None":
    """data/quiver/congress.parquet → a DataFrame (or None if pandas/parquet unavailable).

    Kept out of build_ctx so unit tests inject a plain list of row-dicts instead of a
    parquet: build_ctx accepts congress as an iterable of dicts.
    """
    try:
        import pandas as pd  # local import — CI job for unit tests need not have pandas
    except Exception:  # noqa: BLE001
        return None
    p = root / "data" / "quiver" / "congress.parquet"
    if not p.exists():
        return None
    try:
        return pd.read_parquet(p)
    except Exception:  # noqa: BLE001
        return None


def load_sources(root: Path) -> dict:
    """Load every source once. Each loader fails open; the dict is always well-formed."""
    return {
        "risk_state": load_risk_state(root),
        "us_standouts": load_us_standouts(root),
        "subsector": load_subsector_confluence(root),
        "sector_central": load_sector_central(root),
        "screener": load_screener(root),
        "by_ticker": load_by_ticker(root),
        "insider": load_insider(root),
        "smartmoney": load_smartmoney(root),
        "baskets": load_baskets(root),
        "membership": load_membership(root),
        "congress": load_congress(root),
    }


# ── per-block builders (all return None → block omitted) ─────────────────────────

def _regime_block(risk_state: dict) -> dict | None:
    """US regime read, copied verbatim from risk_state.display."""
    if not isinstance(risk_state, dict) or not risk_state:
        return None
    keys = ("score", "verdict", "label_en", "label_zh", "color")
    us = {k: risk_state[k] for k in keys if k in risk_state and risk_state[k] is not None}
    if not us:
        return None
    return {"us": us}


def _sectors_block(subsector: dict, sector_central: dict) -> dict:
    """Sector-level context keyed by the source's own sector name (verbatim).

    `class` from subsector_confluence; conviction labels + rotation state from
    sector_central. The two sources use different sector taxonomies; we merge only
    on an exact name match and omit any field its source did not supply. Never
    fabricates — a sector with only a class and no central match gets just `class`.
    """
    out: dict[str, dict] = {}

    # subsector_confluence: sector `class` (name lives in `sector`/`label`, not `name`).
    secs = subsector.get("sectors") if isinstance(subsector, dict) else None
    if isinstance(secs, list):
        for s in secs:
            if not isinstance(s, dict) or s.get("kind") != "sector":
                continue
            name = s.get("sector") or s.get("label")
            cls = s.get("class")
            if name and cls is not None:
                out.setdefault(str(name), {})["class"] = cls

    # sector_central: conviction label_en/label_zh + rotation.state_plain_en.
    csecs = sector_central.get("sectors") if isinstance(sector_central, dict) else None
    if isinstance(csecs, list):
        for s in csecs:
            if not isinstance(s, dict):
                continue
            name = s.get("name")
            if not name:
                continue
            blk = out.setdefault(str(name), {})
            conv = s.get("conviction")
            if isinstance(conv, dict):
                if conv.get("label_en") is not None:
                    blk["conviction_en"] = conv["label_en"]
                if conv.get("label_zh") is not None:
                    blk["conviction_zh"] = conv["label_zh"]
            rot = s.get("rotation")
            if isinstance(rot, dict) and rot.get("state_plain_en") is not None:
                blk["rotation_state"] = rot["state_plain_en"]

    # Drop any sector that ended up with nothing (defensive; shouldn't happen).
    return {k: v for k, v in out.items() if v}


def _ticker_sector(ticker: str, standouts_index: dict, screener_row: dict | None) -> str | None:
    """Cheapest committed per-ticker sector: prefer the board row, else the screener row."""
    row = standouts_index.get(ticker)
    if isinstance(row, dict) and row.get("sector"):
        return row["sector"]
    if isinstance(screener_row, dict) and screener_row.get("sector"):
        return screener_row["sector"]
    return None


def _themes_block(ticker: str, membership: dict, baskets: dict) -> list[dict] | None:
    """Ticker → its live basket ids, joined to theme meta (name/name_zh/rank/reco/lane).

    Verbatim meta from baskets.json; lane from _classify_lane iff its inputs exist
    (they do not on the compact artifact → null). A theme with no meta still lists its
    id (honest: the ticker is a member; we just have no meta join for it).
    """
    ids = membership.get(ticker)
    if not ids:
        return None
    themes: list[dict] = []
    for bid in ids:
        meta = baskets.get(bid)
        entry: dict = {"id": bid}
        if isinstance(meta, dict):
            for src, dst in (("name", "name"), ("name_zh", "name_zh"),
                             ("reco", "reco"), ("rank", "rank")):
                if meta.get(src) is not None:
                    entry[dst] = meta[src]
        # lane: _classify_lane's inputs are not present on baskets.json theme records
        # (they are theme-forensics structures inside build_state_of_themes) → null.
        entry["lane"] = None
        themes.append(entry)
    return themes or None


def _stage_block(screener_row: dict | None) -> dict | None:
    """Prophet/stage read from a screener (USA, live) row — verbatim fields."""
    if not isinstance(screener_row, dict):
        return None
    blk: dict = {}
    if screener_row.get("stage") is not None:
        blk["n"] = screener_row["stage"]
    if screener_row.get("stage_label") is not None:
        blk["label"] = screener_row["stage_label"]
    if screener_row.get("weeks_in_stage") is not None:
        blk["weeks"] = screener_row["weeks_in_stage"]
    if screener_row.get("fresh") is not None:
        blk["fresh"] = screener_row["fresh"]
    return blk or None


def _entry_block(ticker: str, standouts: dict) -> dict | None:
    """Entry-gate state from a us_standouts board entry (buy/watch/laggards).

    Only board tickers carry this — omit otherwise. Every field verbatim.
    """
    for board in ("buy", "watch", "laggards"):
        rows = standouts.get(board)
        if not isinstance(rows, list):
            continue
        for r in rows:
            if not isinstance(r, dict):
                continue
            if str(r.get("ticker") or "").strip().upper() != ticker:
                continue
            blk: dict = {}
            es = r.get("entry_signal")
            if isinstance(es, dict):
                if es.get("status") is not None:
                    blk["status"] = es["status"]
                if es.get("act_level") is not None:
                    blk["act_level"] = es["act_level"]
                if es.get("urgency") is not None:
                    blk["urgency"] = es["urgency"]
            if r.get("label") is not None:
                blk["label"] = r["label"]
            if r.get("state") is not None:
                blk["state"] = r["state"]
            return blk or None
    return None


def _earnings_block(by_ticker_row: dict | None) -> dict | None:
    """Earnings clock — omit if absent or days_to is null (never guess a date)."""
    if not isinstance(by_ticker_row, dict):
        return None
    nxt = by_ticker_row.get("next_earnings")
    days_to = by_ticker_row.get("days_to_earnings")
    if nxt is None or days_to is None:
        return None
    return {"next": nxt, "days_to": days_to}


def _insider_block(insider_row: dict | None) -> dict | None:
    """Insider tallies — buyers/sellers/net_mn/bps, verbatim. Omit if the ticker absent."""
    if not isinstance(insider_row, dict):
        return None
    blk: dict = {}
    for k in ("buyers", "sellers", "net_mn", "bps"):
        if k in insider_row:
            blk[k] = insider_row[k]
    return blk or None


def _f13_block(sm_row: dict | None) -> dict | None:
    """13F adds/trims from smartmoney.by_ticker[T] — verbatim direction/asof."""
    if not isinstance(sm_row, dict):
        return None
    blk: dict = {}
    if sm_row.get("n_holders") is not None:
        blk["holders"] = sm_row["n_holders"]
    if sm_row.get("n_buying") is not None:
        blk["adds"] = sm_row["n_buying"]
    if sm_row.get("n_selling") is not None:
        blk["trims"] = sm_row["n_selling"]
    trend = sm_row.get("trend")
    if isinstance(trend, dict) and trend.get("direction") is not None:
        blk["direction"] = trend["direction"]
    if sm_row.get("as_of") is not None:
        blk["asof"] = sm_row["as_of"]
    return blk or None


def _congress_side(transaction: str) -> str:
    t = (transaction or "").lower()
    if "purchase" in t:
        return "buy"
    if "sale" in t:
        return "sell"
    return "other"


def _congress_chamber(house: str) -> str | None:
    h = (house or "").strip().lower()
    if h.startswith("represent"):
        return "house"
    if h.startswith("senate"):
        return "senate"
    return None


def _congress_block(ticker: str, congress_rows, asof: str) -> list[dict] | None:
    """Congress disclosures for a ticker: ReportDate within 90 days of asof, cap 5, desc.

    `congress_rows` is any iterable of row-dicts (columns Ticker/Transaction/House/
    Party/TransactionDate/ReportDate/Amount). The 90-day window is relative to the
    passed `asof` (not wall-clock) so the artifact is deterministic under test.
    """
    if congress_rows is None:
        return None
    try:
        cutoff = (datetime.strptime(asof, "%Y-%m-%d").date() - timedelta(days=90)).isoformat()
    except Exception:  # noqa: BLE001
        return None

    matched: list[dict] = []
    for row in congress_rows:
        if not isinstance(row, dict):
            continue
        if str(row.get("Ticker") or "").strip().upper() != ticker:
            continue
        report = row.get("ReportDate")
        report_s = str(report)[:10] if report is not None else None
        if not report_s or report_s < cutoff or report_s > asof:
            continue
        party = row.get("Party")
        amount = row.get("Amount")
        try:
            amount_mid = float(amount) if amount is not None else None
            # guard against NaN (a float column with a missing value) → null, so the
            # artifact always passes json.dumps(allow_nan=False).
            if amount_mid is not None and amount_mid != amount_mid:
                amount_mid = None
        except (TypeError, ValueError):
            amount_mid = None
        tx = row.get("TransactionDate")
        matched.append({
            "side": _congress_side(str(row.get("Transaction") or "")),
            "chamber": _congress_chamber(str(row.get("House") or "")),
            "party": (str(party)[0] if party else None),
            "tx_date": (str(tx)[:10] if tx is not None else None),
            "filed": report_s,
            "amount_mid": amount_mid,
        })

    if not matched:
        return None
    # Sort by filed date descending (most-recent disclosure first), then cap.
    matched.sort(key=lambda r: r["filed"], reverse=True)
    return matched[:5]


def _congress_iter(congress):
    """Normalize the congress source (DataFrame | list-of-dicts | None) to row-dicts."""
    if congress is None:
        return None
    # pandas DataFrame → records without importing pandas here.
    if hasattr(congress, "to_dict") and hasattr(congress, "columns"):
        return congress.to_dict("records")
    if isinstance(congress, list):
        return congress
    return None


# ── pure core ────────────────────────────────────────────────────────────────

def build_ctx(sources: dict, tickers: list[str] | None, asof: str) -> dict:
    """Assemble the portfolio_ctx.v1 payload from already-loaded sources. Pure, no I/O.

    A per-ticker sub-block is omitted when its desk has no data. A ticker with zero
    coverage anywhere is omitted from `tickers`. Every stance string is verbatim from
    its source. No fabricated or placeholder values.
    """
    sources = sources or {}
    risk_state = sources.get("risk_state") or {}
    standouts = sources.get("us_standouts") or {}
    subsector = sources.get("subsector") or {}
    sector_central = sources.get("sector_central") or {}
    screener = sources.get("screener") or {}
    by_ticker = sources.get("by_ticker") or {}
    insider = sources.get("insider") or {}
    smartmoney = sources.get("smartmoney") or {}
    baskets = sources.get("baskets") or {}
    membership = sources.get("membership") or {}
    congress_rows = _congress_iter(sources.get("congress"))

    # Index standouts board rows by ticker once (sector lookup + reused by _entry_block).
    standouts_index: dict[str, dict] = {}
    for board in ("buy", "watch", "laggards"):
        rows = standouts.get(board)
        if isinstance(rows, list):
            for r in rows:
                if isinstance(r, dict):
                    t = str(r.get("ticker") or "").strip().upper()
                    if t and t not in standouts_index:
                        standouts_index[t] = r

    regime = _regime_block(risk_state)
    sectors = _sectors_block(subsector, sector_central)

    tick_list = [str(t).strip().upper() for t in (tickers or STUB_TICKERS)]
    ticker_out: dict[str, dict] = {}
    cov = {"tickers": 0, "stage": 0, "themes": 0, "earnings": 0,
           "insider": 0, "congress": 0, "f13": 0, "entry": 0}

    for t in tick_list:
        screener_row = screener.get(t)
        block: dict = {}

        sector = _ticker_sector(t, standouts_index, screener_row)
        if sector is not None:
            block["sector"] = sector

        themes = _themes_block(t, membership, baskets)
        if themes is not None:
            block["themes"] = themes
            cov["themes"] += 1

        stage = _stage_block(screener_row)
        if stage is not None:
            block["stage"] = stage
            cov["stage"] += 1

        entry = _entry_block(t, standouts)
        if entry is not None:
            block["entry"] = entry
            cov["entry"] += 1

        earnings = _earnings_block(by_ticker.get(t))
        if earnings is not None:
            block["earnings"] = earnings
            cov["earnings"] += 1

        ins = _insider_block(insider.get(t))
        if ins is not None:
            block["insider"] = ins
            cov["insider"] += 1

        cong = _congress_block(t, congress_rows, asof)
        if cong is not None:
            block["congress"] = cong
            cov["congress"] += 1

        f13 = _f13_block(smartmoney.get(t))
        if f13 is not None:
            block["f13"] = f13
            cov["f13"] += 1

        # A ticker with zero coverage anywhere is omitted entirely (sector alone is
        # metadata, not desk coverage — require at least one desk block to include).
        desk_blocks = ("themes", "stage", "entry", "earnings", "insider",
                       "congress", "f13")
        if any(k in block for k in desk_blocks):
            ticker_out[t] = block
            cov["tickers"] += 1

    # Top-level structure is STABLE (fixed key set) so the cross-repo contract does not
    # drift when a source is empty: `regime` and `sectors` are always-present keys
    # ({} when their source has no data). The OMIT rule (absence = "no desk coverage")
    # applies to per-ticker sub-blocks and zero-coverage tickers, not to top-level keys.
    return {
        "schema": SCHEMA,
        "v": SCHEMA_V,
        "asof": asof,
        "built": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "gate_go": bool(standouts.get("gate_go")) if "gate_go" in standouts else None,
        "regime": regime or {},
        "sectors": sectors or {},
        "coverage": cov,
        "tickers": ticker_out,
    }


# ── entrypoint ───────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tickers", default=None,
                    help="comma list e.g. NVDA,AAPL,XOM (W0 stub default: "
                         f"{','.join(STUB_TICKERS)}; W1 flips to full universe)")
    ap.add_argument("--out", default="site/data/portfolio_ctx.json",
                    help="output path (default: site/data/portfolio_ctx.json)")
    ap.add_argument("--asof", default=None,
                    help="as-of date YYYY-MM-DD (default: today)")
    ap.add_argument("--root", default=str(ROOT),
                    help="repo root (default: this file's repo)")
    args = ap.parse_args(argv)

    t0 = time.perf_counter()
    root = Path(args.root)
    asof = args.asof or date.today().isoformat()
    tickers = ([s.strip().upper() for s in args.tickers.split(",") if s.strip()]
               if args.tickers else None)

    sources = load_sources(root)
    payload = build_ctx(sources, tickers, asof)

    out_path = (Path(args.out) if Path(args.out).is_absolute()
                else root / args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, separators=(",", ":"), allow_nan=False,
                      ensure_ascii=False)
    out_path.write_text(text, encoding="utf-8")

    n = len(payload.get("tickers", {}))
    size_kb = len(text.encode("utf-8")) / 1024
    print(f"[portfolio_ctx total] {time.perf_counter()-t0:.2f}s, {n} tickers, "
          f"{size_kb:.0f} KB", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
