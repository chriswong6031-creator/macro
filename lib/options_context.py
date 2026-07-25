"""Display-tier options context for the Prophet / stock-picking surfaces (OEU M-PRO).

WHAT THIS IS
------------
One loader + one plain-word vocabulary shared by the four Prophet-side hook points:

  1. Prophet card ⚠ flags   — scripts/build_site.py → templates/dashboard.html.j2
  2. entry_read caveats     — scripts/build_leader_radar.py → engine.leader_lifecycle
  3. thesis prose sentence  — engine/prophet_bridge.py (_build_thesis / _build_thesis_zh)
  4. structure receipt      — engine/prophet_bridge.py (resolve_option)

Every function here returns DISPLAY STRINGS or EVIDENCE BOOLEANS. There is no
score, no rank, no probability and no direction claim anywhere in this module.

HARD FENCE (LRV-O9 / LRV-R3 idiom; OEU_MASTERPLAN §4 M-PRO; DO_NOT_REBUILD)
---------------------------------------------------------------------------
Nothing produced by this module may enter:
  · any K-of-N chip set                · any state condition or fire rule
  · any rows[] / board sort key        · prophet_bridge.select_candidates gates or sort
  · engine/entry_signal.py             · any conviction / edge / confidence score

Options context is a CAVEAT and a RECEIPT. It de-escalates and it explains; it
never promotes, ranks, sizes or gates. A name with no options coverage must
render EXACTLY as it did before this module existed — every loader is null-safe
and every derivation returns None on missing data (absent = no flag, never a
placeholder).

DATA SOURCES (read-only, already built by other lanes — no new compute)
-----------------------------------------------------------------------
  site/gex/index.json                     — the GEX board manifest (one file, ~650
      rows): spot, call_wall, put_wall, *_band, max_pain, gamma_flip, asof.
      Written by scripts/build_gex_board.py.
  data/polygon_gex/summary_<TICKER>.parquet — daily iv30 history (~400 names,
      accruing since 2026-06-15). The IV percentile is computed with the OPTIONS
      SCREENER'S OWN convention (scripts/build_options_screener._compute_iv_rank):
      percentile of today's IV30 within available history, labelled "young" while
      history depth < 252 calendar days. Today EVERY name is young — the copy
      discloses the sample size inline rather than hiding it.

PLAIN-WORD LAW (docs/DESIGN_DOCTRINE.md)
----------------------------------------
Glance-tier copy uses the house's own gloss from the gex.html primer — a call
wall above "acts like a ceiling", and "price tends to stall there; it doesn't aim
there". No "GEX", no "IV rank", no "percentile", no raw slugs. Numbers and the
sample size ride along in the same string because that string IS the Tier-2
popover row. Every string ships as an (en, zh) pair.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Iterable

log = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Thresholds — display-tier framing constants, NOT calibrated gates.           #
# They decide whether a caveat is worth a reader's attention, nothing else.    #
# --------------------------------------------------------------------------- #

# A call wall this close overhead is worth mentioning. Deliberately loose: the
# claim is "there is structure just above", not "price will stop".
WALL_NEAR_PCT = 3.0

# Walls whose strength the GEX model could actually score. A wall with no band
# (or a 'faint' one) is not something we will put in front of a reader.
WALL_BANDS_SHOWN = frozenset({"very_strong", "strong", "moderate"})

# IV percentile at/above which "the options market is pricing a bigger move than
# usual" is a fair plain-word reading of the name's own recent history.
IV_ELEVATED_PCT = 80.0

# Below this many observations we say nothing at all — a percentile over a
# handful of days is noise, and an honest surface prints no flag rather than a
# hedged one.
IV_MIN_OBS = 20

# Mirrors scripts/build_options_screener.YOUNG_THRESHOLD_DAYS. Every name is
# young today; the constant exists so the two surfaces cannot drift apart.
YOUNG_THRESHOLD_DAYS = 252

# Structure-receipt bands (plan cards). Spread is % of mid; OI is contracts.
SPREAD_TIGHT_PCT = 8.0
SPREAD_WIDE_PCT = 15.0
OI_DEEP = 500
OI_THIN = 100


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _site_dir(site_root: Path | str | None) -> Path:
    if site_root is not None:
        return Path(site_root)
    try:
        from lib import config  # noqa: PLC0415 — optional; tests pass site_root
        return config.site_dir()
    except Exception:  # noqa: BLE001
        return _repo_root() / "site"


def _data_dir(data_root: Path | str | None) -> Path:
    if data_root is not None:
        return Path(data_root)
    try:
        from lib import config  # noqa: PLC0415
        return config.data_dir()
    except Exception:  # noqa: BLE001
        return _repo_root() / "data"


def _f(v) -> float | None:
    """Coerce to a finite float, or None. Never raises."""
    if v is None:
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if x == x and x not in (float("inf"), float("-inf")) else None


# --------------------------------------------------------------------------- #
# Loaders                                                                      #
# --------------------------------------------------------------------------- #

def load_gex_walls(site_root: Path | str | None = None) -> dict[str, dict]:
    """Load the dealer-positioning manifest → {TICKER: context}.

    ONE file read (site/gex/index.json), no per-name fan-out. Returns {} when the
    manifest is absent or unreadable — the caller then renders exactly as before.

    Each context carries only what the display layer needs:
        spot, call_wall, call_wall_band, call_wall_dist_pct (signed, % of spot),
        put_wall, put_wall_band, max_pain, gamma_flip, asof

    call_wall_dist_pct is positive when the wall sits ABOVE spot.
    """
    path = _site_dir(site_root) / "gex" / "index.json"
    if not path.exists():
        log.debug("options_context: %s absent; no wall context", path)
        return {}
    try:
        manifest = json.loads(path.read_text())
    except Exception as e:  # noqa: BLE001 — display context is never fatal
        log.warning("options_context: gex/index.json unreadable (%s); no wall context", e)
        return {}
    if not isinstance(manifest, list):
        log.warning("options_context: gex/index.json is not a list; no wall context")
        return {}

    out: dict[str, dict] = {}
    for row in manifest:
        if not isinstance(row, dict):
            continue
        key = row.get("key")
        if not key:
            continue
        spot = _f(row.get("spot"))
        cw = _f(row.get("call_wall"))
        dist = None
        if spot is not None and spot > 0 and cw is not None:
            dist = (cw - spot) / spot * 100.0
        out[str(key)] = {
            "spot": spot,
            "call_wall": cw,
            "call_wall_band": row.get("call_wall_band"),
            "call_wall_dist_pct": dist,
            "put_wall": _f(row.get("put_wall")),
            "put_wall_band": row.get("put_wall_band"),
            "max_pain": _f(row.get("max_pain")),
            "gamma_flip": _f(row.get("gamma_flip")),
            "asof": row.get("asof"),
        }
    return out


def load_iv_rank(
    tickers: Iterable[str],
    data_root: Path | str | None = None,
) -> dict[str, dict]:
    """IV percentile within each name's OWN history → {TICKER: context}.

    Mirrors scripts/build_options_screener._compute_iv_rank exactly (percentile of
    the latest IV30 within available history; "young" while depth < 252 calendar
    days) so the Prophet card and the screener can never disagree about a name.

    Only the tickers asked for are read (the Prophet board is ~40 names), so this
    is a handful of small columnar reads — O(milliseconds), safe on the render path.

    Each context: {rank_pct, n_obs, history_days, young}. Names with no store
    entry, an unreadable file or < 2 observations are simply absent from the result.
    """
    root = _data_dir(data_root) / "polygon_gex"
    if not root.exists():
        log.debug("options_context: %s absent; no IV context", root)
        return {}
    try:
        import pandas as pd  # noqa: PLC0415 — heavy import stays out of module load
    except Exception as e:  # noqa: BLE001
        log.warning("options_context: pandas unavailable (%s); no IV context", e)
        return {}

    out: dict[str, dict] = {}
    for raw in tickers:
        ticker = str(raw or "").strip()
        if not ticker or ticker in out:
            continue
        path = root / f"summary_{ticker}.parquet"
        if not path.exists():
            continue
        try:
            df = pd.read_parquet(path, columns=["iv30"])
        except Exception as e:  # noqa: BLE001
            log.debug("options_context: %s unreadable (%s)", path, e)
            continue
        series = df["iv30"].dropna()
        n = len(series)
        if n < 2:
            continue
        try:
            current = float(series.iloc[-1])
            rank = float((series < current).sum()) / (n - 1) * 100.0
            idx = pd.to_datetime(df.index)
            history_days = int((idx[-1] - idx[0]).days)
        except Exception as e:  # noqa: BLE001
            log.debug("options_context: iv rank failed for %s (%s)", ticker, e)
            continue
        out[ticker] = {
            "rank_pct": round(rank, 1),
            "n_obs": n,
            "history_days": history_days,
            "young": history_days < YOUNG_THRESHOLD_DAYS,
        }
    return out


# --------------------------------------------------------------------------- #
# Evidence booleans — the ONLY thing entry_read() is allowed to see.           #
# Tri-state honest: a missing input yields False, never a guess.               #
# --------------------------------------------------------------------------- #

def wall_overhead(ctx: dict | None) -> bool:
    """True when a scorable call wall sits within WALL_NEAR_PCT above spot."""
    if not ctx:
        return False
    dist = _f(ctx.get("call_wall_dist_pct"))
    if dist is None or dist < 0 or dist > WALL_NEAR_PCT:
        return False
    return ctx.get("call_wall_band") in WALL_BANDS_SHOWN


def iv_elevated(ivr: dict | None) -> bool:
    """True when the name's own IV sits at/above IV_ELEVATED_PCT of its history."""
    if not ivr:
        return False
    if int(ivr.get("n_obs") or 0) < IV_MIN_OBS:
        return False
    rank = _f(ivr.get("rank_pct"))
    return rank is not None and rank >= IV_ELEVATED_PCT


# --------------------------------------------------------------------------- #
# Plain-word display strings — every one an (en, zh) pair.                     #
# --------------------------------------------------------------------------- #

def wall_flag(ctx: dict | None) -> tuple[str, str] | None:
    """Prophet-card ⚠ row for a call wall just overhead, or None.

    Copy follows the gex.html primer's own gloss: a call wall above "acts like a
    ceiling", and "price tends to stall there; it doesn't aim there".
    """
    if not wall_overhead(ctx):
        return None
    dist = _f((ctx or {}).get("call_wall_dist_pct"))
    if dist is None:
        return None
    d = f"{dist:.1f}"
    return (
        f"Options ceiling {d}% above — price tends to stall where dealer hedging is heaviest",
        f"上方{d}%有期权天花板 — 价格倾向在做市商对冲最重处停滞",
    )


def iv_flag(ivr: dict | None) -> tuple[str, str] | None:
    """Prophet-card ⚠ row for an unusually expensive options market, or None.

    The sample size rides INSIDE the sentence: this history is short (~40 days,
    accruing since 2026-06-15), and a reader who sees the claim must see the
    caveat in the same breath.
    """
    if not iv_elevated(ivr):
        return None
    days = int((ivr or {}).get("history_days") or 0)
    return (
        f"Options pricing a bigger move than usual — top of its own {days}-day record"
        " (short history)",
        f"期权定价高于平常的波动 — 处于自身{days}日记录的高位（历史尚短）",
    )


def board_flags(
    ticker: str,
    walls: dict[str, dict] | None = None,
    iv_ranks: dict[str, dict] | None = None,
) -> list[tuple[str, str]]:
    """Up to two options ⚠ rows for one Prophet card (wall first, then IV).

    Returns [] for every name without coverage — which is most of the universe.
    """
    out: list[tuple[str, str]] = []
    w = wall_flag((walls or {}).get(ticker))
    if w:
        out.append(w)
    i = iv_flag((iv_ranks or {}).get(ticker))
    if i:
        out.append(i)
    return out


def dealer_context_sentence(
    ctx: dict | None,
    entry: float | None = None,
) -> tuple[str, str] | None:
    """ONE deterministic sentence of dealer-positioning context for thesis prose.

    Template string, no LLM. Past tense + an explicit as-of date because a thesis
    is written once at origination and read for weeks afterwards — an undated
    level would quietly become a lie.

    Returns None unless a scorable call wall sits above the reference price.
    """
    if not ctx:
        return None
    cw = _f(ctx.get("call_wall"))
    ref = _f(entry) if entry is not None else _f(ctx.get("spot"))
    if cw is None or ref is None or ref <= 0 or cw <= ref:
        return None
    if ctx.get("call_wall_band") not in WALL_BANDS_SHOWN:
        return None
    dist = (cw - ref) / ref * 100.0
    if dist > WALL_NEAR_PCT * 4:  # too far overhead to be context for this plan
        return None
    asof = str(ctx.get("asof") or "").strip()
    stamp_en = f" (as of {asof})" if asof else ""
    stamp_zh = f"（截至{asof}）" if asof else ""
    d = f"{dist:.1f}"
    return (
        f"Options positioning{stamp_en}: the heaviest call open interest sat at "
        f"${cw:,.2f}, about {d}% above the entry — dealer hedging tends to add "
        f"friction into that level, which is a place price stalls, not a target.",
        f"期权持仓{stamp_zh}：最重的看涨持仓位于 ${cw:,.2f}，约在入场价上方{d}% —"
        f" 做市商对冲通常在该价位形成阻力；那是价格容易停滞之处，并非目标价。",
    )


# --------------------------------------------------------------------------- #
# Structure receipt — plan cards (hook 4)                                      #
# --------------------------------------------------------------------------- #

_BAND_COPY = {
    "liquid": ("liquid", "流动性好"),
    "workable": ("workable", "尚可"),
    "wide": ("wide", "价差偏大"),
    "thin": ("thin", "持仓稀薄"),
}


def structure_band(spread_pct: float | None, open_interest: int | None) -> str | None:
    """Plain word for how tradeable the chosen contract looked at the close.

    Precedence is worst-first so the honest warning always wins:
        wide  — you pay a lot just to get in and out
        thin  — almost nobody holds this strike
        liquid— tight spread AND real open interest
        workable — everything in between (the honest middle; neither word above
                   is true of a 10%-spread / 200-contract line)
    Returns None when neither input is available.
    """
    s = _f(spread_pct)
    oi = None if open_interest is None else int(open_interest)
    if s is None and oi is None:
        return None
    if s is not None and s > SPREAD_WIDE_PCT:
        return "wide"
    if oi is not None and oi < OI_THIN:
        return "thin"
    if s is not None and s <= SPREAD_TIGHT_PCT and (oi is None or oi >= OI_DEEP):
        return "liquid"
    return "workable"


def structure_receipt(
    bid: float | None,
    ask: float | None,
    open_interest: int | None = None,
    implied_vol: float | None = None,
    iv_rank_ctx: dict | None = None,
) -> dict | None:
    """Display-tier receipt for the plan's resolved option contract, or None.

    Answers three questions a reader actually has about a named contract:
      · how much does the spread cost me?      (spread_pct, spread_abs)
      · is anyone else in this strike?         (open_interest, prior-session vintage)
      · is the option expensive for THIS name? (iv_pct + its own-history percentile)

    Plain word on the glance tier (``band_en`` / ``band_zh``); the numbers belong
    in the Tier-2 hover (``note_en`` / ``note_zh``). Every field is independently
    nullable — a contract with a bid/ask but no OI still gets a receipt.
    """
    b, a = _f(bid), _f(ask)
    spread_abs = spread_pct = None
    if b is not None and a is not None and a >= b >= 0:
        mid = (a + b) / 2.0
        spread_abs = round(a - b, 4)
        if mid > 0:
            spread_pct = round((a - b) / mid * 100.0, 1)

    oi = None
    if open_interest is not None:
        try:
            oi = int(open_interest)
        except (TypeError, ValueError):
            oi = None

    iv_pct = None
    iv = _f(implied_vol)
    if iv is not None and iv > 0:
        # ThetaData greeks carry IV as a fraction; the display tier speaks percent.
        iv_pct = round(iv * 100.0, 1) if iv < 5 else round(iv, 1)

    band = structure_band(spread_pct, oi)
    if band is None and iv_pct is None:
        return None

    rank_pct = n_obs = history_days = None
    young = None
    if iv_rank_ctx:
        rank_pct = _f(iv_rank_ctx.get("rank_pct"))
        n_obs = iv_rank_ctx.get("n_obs")
        history_days = iv_rank_ctx.get("history_days")
        young = bool(iv_rank_ctx.get("young"))

    band_en, band_zh = _BAND_COPY.get(band or "", ("", ""))

    bits_en: list[str] = []
    bits_zh: list[str] = []
    if spread_pct is not None:
        bits_en.append(f"bid/ask gap {spread_pct}% of the mid price")
        bits_zh.append(f"买卖价差为中间价的{spread_pct}%")
    if oi is not None:
        bits_en.append(f"{oi:,} contracts open at this strike (prior session)")
        bits_zh.append(f"该行权价未平仓{oi:,}张（上一交易日）")
    if iv_pct is not None:
        if rank_pct is not None and n_obs and int(n_obs) >= IV_MIN_OBS:
            tail_en = (
                f"; that is around the {int(round(rank_pct))}th percentile of this"
                f" name's own {history_days}-day record"
                + (" (short history)" if young else "")
            )
            tail_zh = (
                f"；约处于该标的自身{history_days}日记录的第{int(round(rank_pct))}百分位"
                + ("（历史尚短）" if young else "")
            )
        else:
            tail_en = tail_zh = ""
        bits_en.append(f"option priced at {iv_pct}% expected swing{tail_en}")
        bits_zh.append(f"该期权定价隐含波动{iv_pct}%{tail_zh}")

    return {
        "band": band,
        "band_en": band_en,
        "band_zh": band_zh,
        "spread_pct": spread_pct,
        "spread_abs": spread_abs,
        "open_interest": oi,
        "oi_vintage": "prior session close (OPRA reports OI for the previous day)"
        if oi is not None else None,
        "iv_pct": iv_pct,
        "iv_rank_pct": None if rank_pct is None else round(rank_pct, 1),
        "iv_rank_n_obs": n_obs,
        "iv_rank_history_days": history_days,
        "iv_rank_young": young,
        "note_en": "; ".join(bits_en),
        "note_zh": "；".join(bits_zh),
        "authority_tier": "display",
    }
