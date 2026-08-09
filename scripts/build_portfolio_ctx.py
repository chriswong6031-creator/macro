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

W1 scope: the bake reads only committed source artifacts (READS ONLY — no engine
module that could advance a ledger) and is nightly-wired (daily.yml, after
build_sector_central). With no --tickers the universe is the full holdings-eligible
set = union of validated ticker keys across the loaded sources (screener ∪
smartmoney ∪ insider ∪ by_ticker ∪ membership ∪ standouts ∪ congress-in-window);
--tickers stays a dev/stub flag. Congress rows are read from a parquet and indexed
in ONE pass (W0's per-ticker rescan was quadratic on the real universe). Theme lanes
join from the theme_lanes.v1 side-artifact; Yahoo sector names are unified to the
GICS-family names sector_central uses via a static rename table.

PSI-W2 scope (schema `portfolio_ctx.v2`, charter
research/PORTFOLIO_SUPERINTELLIGENCE_MASTERPLAN_BY_FABLE.md §5.1/§6/§9): STRICTLY
ADDITIVE. Every v1 key keeps its exact shape and meaning (gate 7); v2 adds per-ticker
`tech`/`msens`/`fq`/`pers`/`dossier` state blocks and ONE top-level `market` block of
tape-context states, plus the matching `coverage` counts. Every value is copied
VERBATIM from an existing nightly artifact — no classifier, no fusion, no threshold,
no derived word. A block is OMITTED when its source has no data for the name.

W2 field census (verify-then-build, §5.1): run against the REAL rendered artifacts
(the public R2 mirror of site/stockdata, asof 2026-08-06, 7 names sampled). Fields the
charter sketched that NO nightly source prints are DROPPED, not fabricated:
  - `tech.atr_z`  — no ATR z-score anywhere (site/stockdata carries atr14 / atr_pct only)
  - `tech.rvol63` — realized_vol_63d exists only in a research script
                    (scripts/research/run_w4_controls_fingerprints.py), not as a
                    nightly per-ticker artifact
  - `tech.rs`     — no per-name RS *state word* exists. The WRI L1 lanes read the raw
                    numbers (templates/watchlist_risk.js reads tech.rs_1m / tech.rs_3m),
                    so `rs` carries those SAME numbers verbatim ({m1,m3,m6}); minting a
                    word from them would be a new threshold, i.e. originating.
  - `vol`/`gex`/`flow` (OIP) — data/live_flow_out/ is git-ignored AND
                    scripts/build_options_hub_nightly.py is not a daily.yml step, so the
                    options_hub artifacts are NOT on the render-path checkout. Omitted
                    this wave; they ride W4's wiring.

Sources added in W2 are read at bake time from the render workspace, NOT from git:
site/stockdata/<T>.json and site/stockdata/washout_turn.json are git-ignored but are
written earlier in the SAME nightly `engine` job (build_site → build_stock_library, and
build_baskets → engine.washout_turn) before this serial step, so they are on disk here.
A fresh worktree has neither → every v2 per-ticker block simply omits (fail-open).

Usage:
    python -m scripts.build_portfolio_ctx                     # full universe (nightly)
    python -m scripts.build_portfolio_ctx --tickers NVDA,AAPL,XOM   # dev/stub subset
    python -m scripts.build_portfolio_ctx --out site/data/portfolio_ctx.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SCHEMA = "portfolio_ctx.v2"
SCHEMA_V = 2

# Gate 8 budgets (charter §0.8): the nightly bake stays under these. main() PRINTS both
# measurements every run so a breach is visible in the Actions log, not discovered later.
BUDGET_SECONDS = 60.0
BUDGET_BYTES = 2.5 * 1024 * 1024

# W0 stub universe — kept as the --tickers dev/stub fallback. W1 default (no
# --tickers) is the full holdings-eligible universe = union of the loaded sources.
STUB_TICKERS = ["NVDA", "AAPL", "XOM"]

# ── ticker hygiene ───────────────────────────────────────────────────────────
# Replicated from engine.altdata_models._valid_ticker (the #3211 hygiene gate) —
# copied here rather than imported because importing altdata_models pulls
# `import pandas` at its module top, which would break this bake's deliberately
# pandas-free unit-test path (congress parquet is the ONLY pandas dependency and
# it lives behind a local import in load_congress). Same regex/junk intent; if the
# upstream gate changes, mirror it here. This is display-tier string hygiene — it
# drops foreign/placeholder codes from the universe, not a new classification.
_TICKER_JUNK = {"NA", "N/A", "N.A.", "NAN", "NONE", "NULL", "TBD", "TBA", "NOTAV",
                "UNKNOWN", "PRIVATE", "VARIOUS", "MULTIPLE", "-", "—", "?"}
# US-equity ticker shape: a letter, then alnum, with an optional .-/-suffixed
# share class (BRK.B / BRK-B). Rejects "N/A" (slash), spaces, commas, empties.
_TICKER_RE = re.compile(r"^[A-Z][A-Z0-9]{0,8}([.\-][A-Z0-9]{1,3})?$")


def _valid_ticker(v) -> str | None:
    """A canonical uppercase ticker, or None. Rejects placeholder junk and
    shape-invalid strings (mirrors engine.altdata_models._valid_ticker)."""
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None
    u = s.upper()
    if u in _TICKER_JUNK or not _TICKER_RE.match(u):
        return None
    return u


# ── sector-name unification (Yahoo → the GICS-family names sector_central uses) ──
# W0 discovery: subsector_confluence tags sectors with Yahoo names ("Technology",
# "Financial", "Healthcare", …) while sector_central emits the GICS-family names
# ("Technology", "Financials", "Health Care", …). This is a DETERMINISTIC RENAME of
# the SAME reads — not a new classification — so the two sources land under one key
# and the `sectors` block is keyed by GICS-family names only. A source name with no
# table entry keeps its verbatim name as key (never dropped, never guessed); value
# strings are always passed through verbatim.
#
# NOTE (deviation from the W1 brief's proposed table, verified against the live
# artifacts): the join target for Yahoo "Technology" is "Technology", NOT
# "Information Technology". sector_central.json calls the sector "Technology"
# verbatim and joins DIRECTLY (its name becomes the key unchanged); mapping the
# subsector side to "Information Technology" would split the same sector across two
# keys — the exact fragmentation this table exists to fix. Every other row matches
# the brief. (Verified name sets: subsector = Yahoo; sector_central = "Technology"
# + GICS for the rest; the strict-GICS "Information Technology" only appears on the
# per-ticker `sector` field, which is a different field and left untouched.)
_YAHOO_TO_GICS_SECTOR = {
    "Technology": "Technology",              # sector_central's own name (identity)
    "Financial": "Financials",
    "Healthcare": "Health Care",
    "Consumer Cyclical": "Consumer Discretionary",
    "Consumer Defensive": "Consumer Staples",
    "Basic Materials": "Materials",
    # identity rows (already GICS-family in both sources)
    "Energy": "Energy",
    "Utilities": "Utilities",
    "Industrials": "Industrials",
    "Real Estate": "Real Estate",
    "Communication Services": "Communication Services",
}


def _gics_sector_name(name: str) -> str:
    """Rename a Yahoo sector name to the GICS-family key; unknown → verbatim."""
    return _YAHOO_TO_GICS_SECTOR.get(name, name)


# Theme lanes: W0 imported build_state_of_themes._classify_lane but the classifier's
# forensic inputs are not on the compact artifact, so W0 shipped lane=null. W1 instead
# reads the theme_lanes.v1 side-artifact that build_state_of_themes now writes from the
# SAME ctx it renders the page from (single source of truth) and joins lane by theme id
# in _themes_block — no classifier import, no re-derivation, no pandas/jinja pull.
# PR-A1 (2026-08): the same-id join only ever hit for the 7 of 18 stories that happen to
# be spelled like their basket; the artifact now also ships `basket_lanes` (the explicit
# theme_crosswalk primary_basket_id projection) which _themes_block prefers, with the
# same-id lookup kept as the fallback so the join is a strict superset.


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


def load_theme_lanes(root: Path) -> dict:
    """site/basketdata/theme_lanes.json → {theme_id: lane}. Fail-open to {}.

    The theme_lanes.v1 side-artifact written by build_state_of_themes (the SAME
    lane computed for the State-of-Themes page). Missing/corrupt → {} so a theme's
    lane is simply omitted (W0 behavior: lane null) rather than fabricated.
    """
    d = _read_json(root / "site" / "basketdata" / "theme_lanes.json")
    lanes = d.get("lanes") if isinstance(d, dict) else None
    return lanes if isinstance(lanes, dict) else {}


def load_basket_lanes(root: Path) -> dict:
    """site/basketdata/theme_lanes.json → {basket_id: lane}. Fail-open to {}.

    The BASKET-keyed half of the same side-artifact. `lanes` is keyed by STORY id
    (a ledger key — never renamed); a portfolio ticker's membership yields BASKET
    ids, and only 7 of the 18 stories happen to share their basket's spelling. This
    map is the explicit crosswalk projection (theme_crosswalk.yml primary_basket_id),
    so power_grid / obesity_glp1 / payments_fintech / defense / … resolve a lane
    instead of silently reading null. Missing/corrupt → {} and the caller falls back
    to the legacy same-id join, so the result is a strict superset of W1 behaviour.
    """
    d = _read_json(root / "site" / "basketdata" / "theme_lanes.json")
    bl = d.get("basket_lanes") if isinstance(d, dict) else None
    return bl if isinstance(bl, dict) else {}


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


def load_chain_state(root: Path) -> dict:
    """data/transmission/chain_state.json → the transmission_chains.v1 state (TXI W4).

    Fail-open to {}. Absent (a runner drop before the chains step ever ran, or a fresh
    checkout) → {} so the per-ticker chains block is simply omitted, never fabricated.
    NOTE: build_site (which invokes this bake path in the nightly) runs BEFORE the chains
    step, so this reads the PRIOR nightly's state — one render stale, matching the site
    subset's lag_note.
    """
    d = _read_json(root / "data" / "transmission" / "chain_state.json")
    return d if isinstance(d, dict) else {}


# ── W2 sources ───────────────────────────────────────────────────────────────

class _StockdataDir:
    """Lazy, memory-flat reader over the render-workspace site/stockdata/<T>.json blobs.

    The stock library writes ~2.9k per-name blobs of ~80-105 KB each. Loading them all
    into a dict would cost ~270 MB of resident JSON for the handful of state words this
    bake copies, so this reader parses ONE blob at a time inside the per-ticker loop and
    drops it immediately. It exposes only `.get()`, which is the whole surface build_ctx
    uses — so a unit test can inject a plain {ticker: blob} dict interchangeably.

    Absent file / unreadable / non-dict → None, i.e. every v2 stockdata block omits.
    """

    __slots__ = ("_dir",)

    def __init__(self, directory: Path) -> None:
        self._dir = directory

    def get(self, ticker, default=None):
        d = _read_json(self._dir / f"{ticker}.json")
        return d if isinstance(d, dict) else default


def load_stockdata(root: Path) -> "object":
    """site/stockdata/ → a lazy per-ticker reader, or {} when the directory is absent.

    Git-ignored render output: present in the nightly `engine` job (build_site →
    build_stock_library runs earlier in the SAME job/workspace), absent in a fresh
    worktree → {} → every v2 stockdata-sourced block omits (fail-open, never fabricated).
    """
    d = root / "site" / "stockdata"
    return _StockdataDir(d) if d.is_dir() else {}


def load_washout_turn(root: Path) -> dict:
    """site/stockdata/washout_turn.json → tickers[T] (washout_turn.v1). Fail-open to {}.

    Written by build_baskets (engine.washout_turn) earlier in the same nightly. DISPLAY
    STATE ONLY (DNR:KILL-WASHOUT-TURN): the ctx copies the state WORD and never any entry
    implication. Names not in a washout/turn-watch state are simply absent from the map.
    """
    d = _read_json(root / "site" / "stockdata" / "washout_turn.json")
    tk = d.get("tickers") if isinstance(d, dict) else None
    return tk if isinstance(tk, dict) else {}


def load_dossier_index(root: Path) -> set:
    """site/stocks/<T>.html → the set of tickers that HAVE a Company-Intelligence dossier.

    Link-out only (§6): the ctx carries a boolean so a client can decide whether to render
    the link, never any dossier content. Committed (~2.1k pages). Absent dir → empty set.
    """
    d = root / "site" / "stocks"
    if not d.is_dir():
        return set()
    try:
        return {p.stem.upper() for p in d.glob("*.html")}
    except Exception:  # noqa: BLE001
        return set()


def load_regime_latest(root: Path) -> dict:
    """data/regime/latest.json — the sole authority chain's composed state (MSP-R2).

    Carries quad/cycle_tag/transition_state at top level plus the embedded `risk_radar`
    and `vol_regime` blocks the market block reads verbatim. Fail-open to {}.
    """
    d = _read_json(root / "data" / "regime" / "latest.json")
    return d if isinstance(d, dict) else {}


def load_dispersion(root: Path) -> dict:
    """data/dispersion/regime.json (`dispersion_regime.v1`). Fail-open to {}."""
    d = _read_json(root / "data" / "dispersion" / "regime.json")
    return d if isinstance(d, dict) else {}


def load_rates_command(root: Path) -> dict:
    """data/rates_command/latest.json (`rates_command.v1`) — deterministic stance sentence."""
    d = _read_json(root / "data" / "rates_command" / "latest.json")
    return d if isinstance(d, dict) else {}


def load_group_flow(root: Path) -> dict:
    """site/basketdata/flow.json — per-sector / per-basket flow stages (group_flow)."""
    d = _read_json(root / "site" / "basketdata" / "flow.json")
    return d if isinstance(d, dict) else {}


def load_subsector_rotation(root: Path) -> dict:
    """site/marketdata/subsector_rotation.json — RRG quadrant per sector."""
    d = _read_json(root / "site" / "marketdata" / "subsector_rotation.json")
    return d if isinstance(d, dict) else {}


def load_covariance_spine(root: Path) -> dict:
    """data/neuralweb/covariance_spine.json — market effective-bets counts (display-only)."""
    d = _read_json(root / "data" / "neuralweb" / "covariance_spine.json")
    return d if isinstance(d, dict) else {}


def load_crossasset(root: Path) -> dict:
    """data/crossasset/latest.json — cross-asset regime + absorption/correlation word."""
    d = _read_json(root / "data" / "crossasset" / "latest.json")
    return d if isinstance(d, dict) else {}


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
        "theme_lanes": load_theme_lanes(root),
        "basket_lanes": load_basket_lanes(root),
        "congress": load_congress(root),
        "chain_state": load_chain_state(root),
        # ── W2 ──
        "stockdata": load_stockdata(root),
        "washout_turn": load_washout_turn(root),
        "dossier_index": load_dossier_index(root),
        "regime_latest": load_regime_latest(root),
        "dispersion": load_dispersion(root),
        "rates_command": load_rates_command(root),
        "group_flow": load_group_flow(root),
        "subsector_rotation": load_subsector_rotation(root),
        "covariance_spine": load_covariance_spine(root),
        "crossasset": load_crossasset(root),
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
    """Sector-level context keyed by GICS-family names only (deterministic rename).

    `class` from subsector_confluence (Yahoo sector names → GICS via the static
    _YAHOO_TO_GICS_SECTOR table); conviction labels + rotation state from
    sector_central (GICS-family names, joined directly). This is a deterministic
    rename of the SAME reads — NOT a new classification — so both sources land under
    one key. A source name with no table entry keeps its verbatim name (never
    dropped, never guessed); value strings are always passed through verbatim.
    """
    out: dict[str, dict] = {}

    # subsector_confluence: sector `class` (name lives in `sector`/`label`, not
    # `name`); rename Yahoo → GICS so it merges with the sector_central rows.
    secs = subsector.get("sectors") if isinstance(subsector, dict) else None
    if isinstance(secs, list):
        for s in secs:
            if not isinstance(s, dict) or s.get("kind") != "sector":
                continue
            name = s.get("sector") or s.get("label")
            cls = s.get("class")
            if name and cls is not None:
                out.setdefault(_gics_sector_name(str(name)), {})["class"] = cls

    # sector_central: conviction label_en/label_zh + rotation.state_plain_en.
    # Its names are already GICS-family — join directly (verbatim key).
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


def _themes_block(ticker: str, membership: dict, baskets: dict,
                  theme_lanes: dict, basket_lanes: dict | None = None) -> list[dict] | None:
    """Ticker → its live basket ids, joined to theme meta (name/name_zh/rank/reco/lane).

    Verbatim meta from baskets.json; lane joined from theme_lanes.json (the
    theme_lanes.v1 side-artifact written by build_state_of_themes — the SAME lane
    shown on the Theme Tracker page).

    The lane join prefers `basket_lanes` (basket-id keyed, projected through
    theme_crosswalk.yml's primary_basket_id) and falls back to the legacy same-id
    lookup in `lanes` (story-id keyed). The fallback makes this a strict superset:
    every basket that resolved a lane before still resolves the same one, and the
    11 baskets whose story is spelled differently now resolve too. Fail-open: a
    basket in neither map gets lane=None (W0 behavior — honest "no lane read"). A
    basket with no meta still lists its id (the ticker is a member; no meta join).
    """
    ids = membership.get(ticker)
    if not ids:
        return None
    lanes = theme_lanes if isinstance(theme_lanes, dict) else {}
    b_lanes = basket_lanes if isinstance(basket_lanes, dict) else {}
    themes: list[dict] = []
    for bid in ids:
        meta = baskets.get(bid)
        entry: dict = {"id": bid}
        if isinstance(meta, dict):
            for src, dst in (("name", "name"), ("name_zh", "name_zh"),
                             ("reco", "reco"), ("rank", "rank")):
                if meta.get(src) is not None:
                    entry[dst] = meta[src]
        # lane: explicit basket-keyed map first, then the legacy same-id lookup;
        # missing from both → None (fail-open, no fabrication). Never re-derives.
        lane = b_lanes.get(bid)
        if not isinstance(lane, str):
            lane = lanes.get(bid)
        entry["lane"] = lane if isinstance(lane, str) else None
        themes.append(entry)
    return themes or None


_ARMED_CHAIN_STATES = {"arming", "propagating", "expressed"}


def _chains_index(chain_state: dict) -> dict[str, list[dict]]:
    """Invert the transmission_chains.v1 blast lists ONCE into {ticker: [membership, ...]}.

    A membership row is display-tier context (TXI-R3/R7): which ARMED chain this ticker sits
    downstream of, via which named channel, with the chain's plain state + bilingual label —
    NEVER a score, size, or call. Only chains in an armed state (arming|propagating|expressed)
    resolve a blast radius; dormant chains contribute nothing. A ticker may appear in several
    chains and several channels — each is a separate membership row (dedup identical
    chain×channel pairs). Pure — no IO.
    """
    idx: dict[str, list[dict]] = {}
    if not isinstance(chain_state, dict):
        return idx
    for c in (chain_state.get("chains") or []):
        if not isinstance(c, dict) or c.get("state") not in _ARMED_CHAIN_STATES:
            continue
        chain_id = c.get("chain")
        title = c.get("title") if isinstance(c.get("title"), dict) else {}
        state = c.get("state")
        tier = c.get("tier")
        blast = c.get("blast") or {}
        if not isinstance(blast, dict):
            continue
        for flag, entry in blast.items():
            if not isinstance(entry, dict):
                continue
            names = entry.get("names") or []
            if not isinstance(names, list) or not names:
                continue
            lbl = entry.get("label") if isinstance(entry.get("label"), dict) else {}
            for tkr in names:
                tk = _valid_ticker(tkr)
                if tk is None:
                    continue
                row = {
                    "id": chain_id,
                    "label": {"en": title.get("en"), "zh": title.get("zh")},
                    "state": state,
                    "tier": tier,
                    "channel": flag,
                    "channel_label": {"en": lbl.get("en"), "zh": lbl.get("zh")},
                }
                bucket = idx.setdefault(tk, [])
                # dedup identical chain×channel (a ticker is listed once per channel)
                if not any(r["id"] == chain_id and r["channel"] == flag for r in bucket):
                    bucket.append(row)
    return idx


def _chains_block(ticker: str, chains_index: dict[str, list[dict]]) -> list[dict] | None:
    """Ticker → the ARMED transmission chains it sits downstream of (display-tier WATCH
    context; TXI-R7 per-ticker merge). None when the name is in no armed chain's blast — so
    the block is OMITTED for the vast majority of names (avoids the top-level contract-drift
    trap by living entirely inside tickers.<T>). Never a signal, size, or call."""
    rows = chains_index.get(ticker)
    return rows or None


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


def _build_congress_index(congress_rows, asof: str) -> dict[str, list[dict]]:
    """ONE pass over the congress rows → {TICKER: [normalized disclosure, …]}.

    W1 performance: the W0 `_congress_block` re-scanned the whole rows iterable per
    ticker (~99k rows × ~2,700 tickers = quadratic → blows the <30s budget). This
    builds the ticker→rows index in a single pass with the same deterministic
    semantics: ReportDate within 90 days of `asof` (relative to the passed asof, not
    wall-clock), same side/chamber/party/amount mapping, NaN amounts coerced to null.
    Per-ticker sort+cap happens in _congress_block on the small per-ticker list.

    Rows outside the window are dropped here (not indexed), so the index holds only
    in-window disclosures. Empty/None input → {}.
    """
    index: dict[str, list[dict]] = {}
    if congress_rows is None:
        return index
    try:
        cutoff = (datetime.strptime(asof, "%Y-%m-%d").date()
                  - timedelta(days=90)).isoformat()
    except Exception:  # noqa: BLE001
        return index

    for row in congress_rows:
        if not isinstance(row, dict):
            continue
        tk = _valid_ticker(row.get("Ticker"))
        if tk is None:
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
        index.setdefault(tk, []).append({
            "side": _congress_side(str(row.get("Transaction") or "")),
            "chamber": _congress_chamber(str(row.get("House") or "")),
            "party": (str(party)[0] if party else None),
            "tx_date": (str(tx)[:10] if tx is not None else None),
            "filed": report_s,
            "amount_mid": amount_mid,
        })
    return index


def _congress_block(ticker: str, congress_index: dict) -> list[dict] | None:
    """Congress disclosures for a ticker from the prebuilt index: cap 5, filed desc.

    The window filter already happened in _build_congress_index; this just sorts the
    ticker's small in-window list (most-recent disclosure first) and caps at 5.
    """
    matched = congress_index.get(ticker) if isinstance(congress_index, dict) else None
    if not matched:
        return None
    # Sort by filed date descending (most-recent disclosure first), then cap.
    ordered = sorted(matched, key=lambda r: r["filed"], reverse=True)
    return ordered[:5]


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


# ── W2 per-ticker state blocks (§5.1) ────────────────────────────────────────
# Every one is a VERBATIM copy out of an already-baked nightly artifact. None of them
# thresholds, grades, rounds, renames or blends anything: the words and numbers below are
# the source's own. A sub-key is dropped when its source field is absent and the whole
# block is omitted when nothing resolved — absence means "no desk coverage", which is a
# different statement from a null, and the clients render it differently.

def _copy_bilingual(d) -> dict | None:
    """{'en':…, 'zh':…} copied verbatim (missing halves dropped), else None."""
    if not isinstance(d, dict):
        return None
    out = {k: d[k] for k in ("en", "zh") if d.get(k) is not None}
    return out or None


def _tech_block(sd: dict | None, washout_row) -> dict | None:
    """Per-name technical state from site/stockdata/<T>.json + the washout watcher.

    `ext`     ← ext.grade                (in-trend/steady/stretched/parabolic — verbatim word)
    `ma`      ← tech.above50 / above200  (the source's own booleans)
    `rs`      ← tech.rs_1m/rs_3m/rs_6m   (the SAME numbers the WRI L1 lanes read; the
                                          charter asked for a state word, none exists —
                                          see the module docstring's census)
    `dd252`   ← tech.off_52w_high_pct    (verbatim; NOT re-rounded)
    `washout` ← washout_turn.tickers[T].state (display state word only — DNR:KILL-WASHOUT-TURN)
    """
    sd = sd if isinstance(sd, dict) else {}
    ext = sd.get("ext") if isinstance(sd.get("ext"), dict) else {}
    tech = sd.get("tech") if isinstance(sd.get("tech"), dict) else {}
    blk: dict = {}
    if ext.get("grade") is not None:
        blk["ext"] = ext["grade"]
    ma = {dst: tech[src] for src, dst in (("above50", "m50"), ("above200", "m200"))
          if tech.get(src) is not None}
    if ma:
        blk["ma"] = ma
    rs = {dst: tech[src] for src, dst in (("rs_1m", "m1"), ("rs_3m", "m3"), ("rs_6m", "m6"))
          if tech.get(src) is not None}
    if rs:
        blk["rs"] = rs
    if tech.get("off_52w_high_pct") is not None:
        blk["dd252"] = tech["off_52w_high_pct"]
    state = washout_row.get("state") if isinstance(washout_row, dict) else None
    if isinstance(state, str) and state:
        blk["washout"] = state
    return blk or None


def _msens_block(sd: dict | None) -> dict | None:
    """Macro-sensitivity chip from stockdata.macro_sensitivity — verbatim tier words (§6).

    `rate_tier` ← macro_sensitivity.tier (the source's own precision tier: low/medium/high)
    `read`      ← macro_sensitivity.regime_label {en, zh} (e.g. "rate tailwind"), bilingual
                  because every user-facing string on both surfaces is a dual-span pair.
    """
    ms = sd.get("macro_sensitivity") if isinstance(sd, dict) else None
    if not isinstance(ms, dict):
        return None
    blk: dict = {}
    if ms.get("tier") is not None:
        blk["rate_tier"] = ms["tier"]
    read = _copy_bilingual(ms.get("regime_label"))
    if read:
        blk["read"] = read
    return blk or None


def _fq_block(sd: dict | None) -> dict | None:
    """COUNT of fired solvency/dilution/quality flags (§5.1: `fq: {flags: 2}`).

    Source: stockdata.thesis_funnel.flags — the PRD lane-5 sensors (s1_dilution,
    s2_moat_falsifier, s3_solvency, s4_coverage), each already carrying its own `fired`
    boolean. This tallies those booleans; it evaluates no threshold of its own and the
    flag detail stays in stockdata for the Tier-2 list.

    `{"flags": 0}` is emitted when the desk HAS coverage and nothing fired — that is a
    measurement, not a placeholder. No flags dict at all → block omitted.
    """
    tf = sd.get("thesis_funnel") if isinstance(sd, dict) else None
    flags = tf.get("flags") if isinstance(tf, dict) else None
    if not isinstance(flags, dict) or not flags:
        return None
    n = sum(1 for v in flags.values() if isinstance(v, dict) and v.get("fired") is True)
    return {"flags": n}


def _pers_block(sd: dict | None) -> dict | None:
    """Personality archetype key from stockdata.personality (stock_personality.v1).

    Context only, never a score (PRD-R12). Verbatim key word, e.g. quality_compounder.
    """
    p = sd.get("personality") if isinstance(sd, dict) else None
    base = p.get("base") if isinstance(p, dict) else None
    arch = base.get("archetype") if isinstance(base, dict) else None
    key = arch.get("key") if isinstance(arch, dict) else None
    return {"arch": key} if isinstance(key, str) and key else None


# ── W2 top-level `market` block (§9 tape context) ────────────────────────────
# Verbatim states + their own asof stamps, one sub-key per home artifact. This composes;
# it builds NO new regime classifier and NO parallel fusion (MSP-R2: the
# risk_radar→market_state→regime_vector chain stays the sole authority). A sub-key whose
# home artifact is absent is OMITTED — fail-open, never a fabricated neutral state. The
# `market` key itself is ALWAYS present ({} when nothing resolved) so the top-level key
# set stays fixed for the cross-repo contract, exactly like v1's `regime`/`sectors`.

def _pick(src, *fields) -> dict:
    """{dst: src[key]} for each (key, dst) — dropping absent/None values. Verbatim copy."""
    if not isinstance(src, dict):
        return {}
    out: dict = {}
    for key, dst in fields:
        if src.get(key) is not None:
            out[dst] = src[key]
    return out


def _flow_rows(rows) -> list[dict]:
    """[{id, name, name_zh, stage}] verbatim from a group_flow sectors/baskets list."""
    out: list[dict] = []
    if not isinstance(rows, list):
        return out
    for r in rows:
        if not isinstance(r, dict) or r.get("id") is None or r.get("stage") is None:
            continue
        out.append(_pick(r, ("id", "id"), ("name", "name"), ("name_zh", "name_zh"),
                        ("stage", "stage")))
    return out


def _as_dict(v) -> dict:
    """v when it is a dict, else {} — so a corrupt source can never raise here."""
    return v if isinstance(v, dict) else {}


def _market_block(sources: dict) -> dict:
    """The tape-context states (§9), each copied verbatim from its home artifact."""
    sources = _as_dict(sources)
    regime_latest = _as_dict(sources.get("regime_latest"))
    dispersion = _as_dict(sources.get("dispersion"))
    rates = _as_dict(sources.get("rates_command"))
    gflow = _as_dict(sources.get("group_flow"))
    rot = _as_dict(sources.get("subsector_rotation"))
    spine = _as_dict(sources.get("covariance_spine"))
    xasset = _as_dict(sources.get("crossasset"))

    out: dict = {}

    # Daily regime read — quad / cycle_tag / transition_state (engine/regime.py).
    blk = _pick(regime_latest, ("quad", "quad"), ("quad_name", "quad_name"),
                ("cycle_tag", "cycle_tag"), ("transition_state", "transition_state"),
                ("liquidity_overlay", "liquidity_overlay"), ("asof", "asof"))
    if blk:
        out["regime"] = blk

    # Risk radar verdict — the SOLE stress authority (MSP-R2). State + dominant scare.
    rr = regime_latest.get("risk_radar")
    blk = _pick(rr, ("state", "state"), ("dominant_scare", "dominant_scare"),
                ("dominant_label_en", "label_en"), ("dominant_label_zh", "label_zh"),
                ("asof", "asof"))
    if blk:
        out["risk_radar"] = blk

    # Vol regime — term-structure / VRP / fragility state words.
    vr = regime_latest.get("vol_regime")
    blk = _pick(vr, ("regime", "regime"), ("ts_slope_state", "ts_slope_state"),
                ("vrp_state", "vrp_state"), ("vvix_state", "vvix_state"),
                ("fragility_confluence", "fragility_confluence"), ("asof", "asof"))
    if blk:
        out["vol_regime"] = blk

    # Market concentration — NO dedicated engine exists (§9 census 2026-08-03). The one
    # committed read is the risk_radar bubble leg's cap_leadership flag; we print that
    # single fact and nothing more. (The top-10-weight-share arithmetic is W5's.)
    if isinstance(rr, dict) and rr.get("cap_leadership") is not None:
        out["concentration"] = {"cap_leadership": rr["cap_leadership"]}

    # Dispersion regime (`dispersion_regime.v1`) — stock-picker's tape vs one-trade tape.
    blk = _pick(dispersion, ("state", "state"), ("label", "label_en"),
                ("label_zh", "label_zh"), ("dispersion_pctile", "pctile"),
                ("avg_corr", "avg_corr"), ("as_of", "asof"))
    if blk:
        out["dispersion"] = blk

    # Market effective bets — the §9 juxtaposition input ("the market runs ~N bets").
    blocks = spine.get("blocks")
    if isinstance(blocks, dict):
        blk = {}
        blk.update(_pick(blocks.get("factors"),
                         ("effective_factor_bets_pr", "factor_bets")))
        blk.update(_pick(blocks.get("dispersion"),
                         ("effective_universe_bets_pr", "universe_bets")))
        lobes = blocks.get("lobes")
        blk.update(_pick(lobes, ("effective_independent_lobes", "lobes")))
        warn = lobes.get("same_bet_warning") if isinstance(lobes, dict) else None
        if isinstance(warn, dict) and warn.get("active") is not None:
            blk["same_bet_warning"] = warn["active"]
        if spine.get("as_of") is not None:
            blk["asof"] = spine["as_of"]
        if blk:
            out["effective_bets"] = blk

    # Cross-asset backdrop (absorption/correlation words from engine/cross_asset.py).
    blk = _pick(xasset, ("regime", "regime"), ("correlation", "correlation"),
                ("breadth", "breadth"), ("asof", "asof"))
    if blk:
        out["crossasset"] = blk

    # Policy / rates — the rates_command.v1 deterministic stance sentence (Tier-1 line).
    stance = _copy_bilingual(rates.get("stance"))
    if stance:
        blk = {"stance": stance}
        if rates.get("asof") is not None:
            blk["asof"] = rates["asof"]
        out["rates"] = blk

    # Sector/theme flow tape — which sectors and baskets sit in which flow stage.
    fblk: dict = {}
    secs = _flow_rows(gflow.get("sectors"))
    bskts = _flow_rows(gflow.get("baskets"))
    if secs:
        fblk["sectors"] = secs
    if bskts:
        fblk["baskets"] = bskts
    if fblk and gflow.get("as_of") is not None:
        fblk["asof"] = gflow["as_of"]
    if fblk:
        out["flow"] = fblk

    # Rotation quadrant per sector (RRG). Keyed by the SOURCE's own sector ETF key + name —
    # no rename table is invented here (the v1 GICS table maps the ctx `sectors` block's
    # two sources onto each other; this artifact names sectors a third way and a consumer
    # joins on the key it needs).
    rows = rot.get("sectors")
    if isinstance(rows, list):
        rblk = [_pick(r, ("key", "key"), ("name", "name"), ("name_zh", "name_zh"),
                      ("quadrant", "quadrant"))
                for r in rows
                if isinstance(r, dict) and r.get("quadrant") is not None]
        rblk = [r for r in rblk if r]
        if rblk:
            blk = {"sectors": rblk}
            if rot.get("asof") is not None:
                blk["asof"] = rot["asof"]
            out["rotation"] = blk

    return out


# ── pure core ────────────────────────────────────────────────────────────────

def _universe_union(sources: dict, standouts_index: dict,
                    congress_index: dict) -> list[str]:
    """Full holdings-eligible universe = union of validated ticker keys across the
    loaded sources: screener ∪ smartmoney ∪ insider ∪ by_ticker ∪ membership ∪
    standouts boards ∪ congress tickers (already window-filtered in the index).

    Every candidate passes the _valid_ticker hygiene gate (upper + shape/junk
    filter) so foreign/placeholder codes never enter the universe. The
    zero-coverage drop rule in build_ctx still removes any name that, despite being
    a key here, ends up with no desk block. Returns a sorted list (deterministic).
    """
    uni: set[str] = set()
    # Already-keyed-by-upper-ticker maps: screener / insider / smartmoney(by_ticker) /
    # by_ticker / membership. Re-validate each key (they came from raw feeds).
    for src_key in ("screener", "insider", "smartmoney", "by_ticker", "membership"):
        m = sources.get(src_key)
        if isinstance(m, dict):
            for k in m:
                tk = _valid_ticker(k)
                if tk is not None:
                    uni.add(tk)
    # standouts board rows (already indexed by upper ticker in build_ctx)
    for k in standouts_index:
        tk = _valid_ticker(k)
        if tk is not None:
            uni.add(tk)
    # congress: index keys are validated tickers with in-window rows
    for k in congress_index:
        uni.add(k)  # already _valid_ticker in _build_congress_index
    return sorted(uni)


def build_ctx(sources: dict, tickers: list[str] | None, asof: str) -> dict:
    """Assemble the portfolio_ctx.v1 payload from already-loaded sources. Pure, no I/O.

    When `tickers` is None (the W1 nightly default) the universe is the union of
    validated ticker keys across every loaded source (see _universe_union). Pass an
    explicit list (the --tickers dev/stub flag) to bake a fixed subset.

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
    theme_lanes = sources.get("theme_lanes") or {}
    basket_lanes = sources.get("basket_lanes") or {}
    congress_rows = _congress_iter(sources.get("congress"))
    # TXI W4 — invert the transmission chains blast lists ONCE into a per-ticker index.
    chains_index = _chains_index(sources.get("chain_state") or {})
    # W2 per-ticker sources. `stockdata` is a lazy reader in the nightly and a plain dict
    # in unit tests — both answer .get(ticker) and nothing else is used.
    stockdata = sources.get("stockdata") or {}
    washout = sources.get("washout_turn") or {}
    dossier_index = sources.get("dossier_index") or set()

    # ONE pass over the congress rows → window-filtered ticker→rows index (W1 perf:
    # replaces the W0 per-ticker full scan that went quadratic on the real universe).
    congress_index = _build_congress_index(congress_rows, asof)

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

    # W1 default: no explicit tickers → full holdings-eligible universe (union of
    # sources). An explicit list stays the dev/stub path. Both are uppercased +
    # hygiene-gated so junk codes never enter.
    if tickers is None:
        tick_list = _universe_union(sources, standouts_index, congress_index)
    else:
        tick_list = [tk for tk in (_valid_ticker(t) for t in tickers)
                     if tk is not None]
    ticker_out: dict[str, dict] = {}
    cov = {"tickers": 0, "stage": 0, "themes": 0, "earnings": 0,
           "insider": 0, "congress": 0, "f13": 0, "entry": 0, "chains": 0,
           # W2 additions — one count per new block, for the honesty chips (§5.1).
           "tech": 0, "msens": 0, "fq": 0, "pers": 0, "dossier": 0}

    for t in tick_list:
        screener_row = screener.get(t)
        block: dict = {}

        sector = _ticker_sector(t, standouts_index, screener_row)
        if sector is not None:
            block["sector"] = sector

        themes = _themes_block(t, membership, baskets, theme_lanes, basket_lanes)
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

        cong = _congress_block(t, congress_index)
        if cong is not None:
            block["congress"] = cong
            cov["congress"] += 1

        f13 = _f13_block(smartmoney.get(t))
        if f13 is not None:
            block["f13"] = f13
            cov["f13"] += 1

        # TXI W4 — the armed transmission chains this ticker sits downstream of (per-ticker,
        # display-tier WATCH context). Omitted for names in no armed chain's blast.
        chains = _chains_block(t, chains_index)
        if chains is not None:
            block["chains"] = chains
            cov["chains"] += 1

        # ── W2 state blocks (§5.1). One stockdata blob is parsed per ticker and dropped
        # immediately; all four blocks read from it, so this is ONE file read per name.
        sd = stockdata.get(t)

        tech = _tech_block(sd, washout.get(t))
        if tech is not None:
            block["tech"] = tech
            cov["tech"] += 1

        msens = _msens_block(sd)
        if msens is not None:
            block["msens"] = msens
            cov["msens"] += 1

        fq = _fq_block(sd)
        if fq is not None:
            block["fq"] = fq
            cov["fq"] += 1

        pers = _pers_block(sd)
        if pers is not None:
            block["pers"] = pers
            cov["pers"] += 1

        if t in dossier_index:
            block["dossier"] = True
            cov["dossier"] += 1

        # A ticker with zero coverage anywhere is omitted entirely (sector alone is
        # metadata, not desk coverage — require at least one desk block to include).
        desk_blocks = ("themes", "stage", "entry", "earnings", "insider",
                       "congress", "f13", "chains",
                       "tech", "msens", "fq", "pers", "dossier")
        if any(k in block for k in desk_blocks):
            ticker_out[t] = block
            cov["tickers"] += 1

    # Top-level structure is STABLE (fixed key set) so the cross-repo contract does not
    # drift when a source is empty: `regime`, `sectors` and (W2) `market` are
    # always-present keys ({} when their source has no data). The OMIT rule (absence =
    # "no desk coverage") applies to per-ticker sub-blocks and zero-coverage tickers, not
    # to top-level keys. Key ORDER also keeps `market` after the v1 keys so a v1 reader
    # diffing the head of the file sees an unchanged prefix.
    return {
        "schema": SCHEMA,
        "v": SCHEMA_V,
        "asof": asof,
        "built": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "gate_go": bool(standouts.get("gate_go")) if "gate_go" in standouts else None,
        "regime": regime or {},
        "sectors": sectors or {},
        "market": _market_block(sources),
        "coverage": cov,
        "tickers": ticker_out,
    }


# ── entrypoint ───────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tickers", default=None,
                    help="comma list e.g. NVDA,AAPL,XOM (dev/stub subset). Omit for "
                         "the full holdings-eligible universe = union of the sources.")
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
    n_bytes = len(text.encode("utf-8"))
    elapsed = time.perf_counter() - t0
    cov = payload.get("coverage") or {}

    # Gate-8 budget stamps — PRINTED every run (charter §0.8: "report both in the bake
    # log"). Both are measurements, not assertions: a breach warns loudly and still ships
    # the artifact, because a silently-missing portfolio_ctx is worse than a fat one.
    print(f"[portfolio_ctx total] {elapsed:.2f}s, {n} tickers, "
          f"{n_bytes / 1024:.0f} KB", flush=True)
    print(f"[portfolio_ctx budget] time {elapsed:.2f}s / {BUDGET_SECONDS:.0f}s  "
          f"size {n_bytes / 1024 / 1024:.2f} MB / {BUDGET_BYTES / 1024 / 1024:.1f} MB",
          flush=True)
    print("[portfolio_ctx coverage] "
          + " ".join(f"{k}={v}" for k, v in cov.items()), flush=True)
    # GitHub annotations must START the line and go through a bare print (house law;
    # tests/test_gh_annotation_line_start.py) — never a logger, which would prefix them.
    if elapsed > BUDGET_SECONDS:
        print(f"::warning title=portfolio-ctx-budget::bake took {elapsed:.1f}s, over the "
              f"{BUDGET_SECONDS:.0f}s gate-8 budget", flush=True)
    if n_bytes > BUDGET_BYTES:
        print(f"::warning title=portfolio-ctx-budget::artifact is "
              f"{n_bytes / 1024 / 1024:.2f} MB, over the "
              f"{BUDGET_BYTES / 1024 / 1024:.1f} MB gate-8 budget", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
