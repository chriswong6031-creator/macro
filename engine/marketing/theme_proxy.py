"""Theme-level proxy cashtags — the bigger ticker for a group that moves as one.

WHY THIS EXISTS (operator, live post 2026-08-05). A "Commodities Metals bid up"
post named ``$GFI $AEM $KGC``. Those are the three biggest MOVERS on the card,
and they are also three of the least-watched tickers in the group:

    $GFI  ADV20   $117M   <- the post's LEAD cashtag
    $AEM  ADV20   $358M   <- biggest of the three it named
    $HL   ADV20   $599M   <- biggest name ON the card, never named
    $GDX  ADV20 $1,321M   <- the sector ETF: 3.7x $AEM, 11.3x $GFI
    $GLD  ADV20 $2,321M   <- the metal itself

    "for this kind of theme, shouldnt u be prioritizing tagging the underlying
    major ETF or even the underlying commodity/asset class ... these are much
    larger tickers that are able to get much more reach than the three u used"

The operator also set the bound in the same breath: "some themes ETFS arent that
popular, or their individual tickers are more popular, so this is a fine tuned
adjustment ... its case by case basis." That bound is the whole design problem —
a rule that always prefers the ETF is wrong more often than the status quo, and
the sweep in ``scripts/build_theme_proxy_map.py`` says so numerically.

THE THREE-LEG GATE. A proxy tag ships only when all three hold. Each leg exists
because dropping it admits a specific, measured failure:

  1. REACH — the proxy must out-trade the biggest name the text will name.
     Drop it and we tag $SIL ($71M) on a card whose own $HL trades $599M: a
     smaller ticker wearing a sector badge. (The operator's own suggestion of
     $SIL fails here; $SLV at $770M is the silver tag that clears.)

  2. COHESION — mean pairwise correlation of the card's members over 252
     sessions must clear ``min_cohesion``. This is the executable form of the
     operator's own mechanism: "they all rise together as one sector anyways,
     and it doesn't matter whihc name u buy everything goes up". It separates by
     a factor of four and it is the leg that saves us from the worst tag in the
     inventory:

         gold miners (GDX)     rho_bar 0.80   <- one trade
         regional banks (KRE)  rho_bar 0.79   <- one trade
         semis (SMH)           rho_bar 0.48
         retail (XRT)          rho_bar 0.26
         biotech (XBI)         rho_bar 0.21   <- NOT one trade

     $XBI out-trades every one of its own holdings by 2.5x, so a reach-only rule
     tags it eagerly. But biotech names do not move together at all — binary
     trial/approval risk is idiosyncratic by construction — so "Healthcare &
     Biotech is +3% on average, $XBI" asserts a coherence the tape denies. Reach
     buys attention; cohesion is what makes the tag true.

  3. REPRESENTATIVENESS — the fund must actually be ABOUT these names, tested
     in both directions: it holds a majority of the card's rows, AND a material
     share of its own weight sits in them. One direction alone is not enough,
     and the sweep produced a live example of each failure:

         $SMH  on Industrial Automation: holds 1/8 rows, 1.8% of the fund
         $XOP  on Commodities Agriculture: holds 2/8 rows, 1.5% of the fund

     Both are coincidental single-name overlaps — $SMH on an $ETN/$FTNT post is
     cashtag-piggybacking, which is the exact fingerprint
     ``max_theme_cashtags_in_text`` exists to keep off this account. Contrast
     the case that started this: $GDX holds 8 of the 8 rows that shipped, and
     those 8 names are 30.3% of the fund.

TWO CLASSES OF PROXY, ONE DIFFERENT BASIS.

  * ``holdings`` — an equity ETF whose stored constituents are checked against
    the card's rows at resolve time. Self-verifying: the receipt is the fund's
    own holdings file.

  * ``declared`` — the underlying commodity or asset class ($GLD, $SLV). A
    bullion fund holds metal, not miners, so no holdings test can select it and
    the link is declared per theme in the map and reviewed by a human. It still
    faces legs 1 and 2 unchanged.

    The copy says nothing special about which class it is (operator ruling
    2026-08-05, asked and answered explicitly): "ignoring ur 'copy has to say
    that' thingy. When gold goes up, its miners go up, its that simple, don't
    need to overcomplicate". Gold beta is not a subtlety that needs a disclosure
    sentence, and a tag is a tag.

WHAT THIS MODULE DOES NOT DO. It never invents a candidate at post time. The
inventory — which funds exist, what they hold, how much they trade — is read from
``data/marketing/theme_proxy_map.json``, which ``scripts/build_theme_proxy_map.py``
regenerates from committed inputs (finviz theme map, ETF holdings, cashtag tiers).

WHY COHESION IS MEASURED HERE AND NOT IN THE BUILDER. It was in the builder
first, over each theme's full membership, and that reading is wrong by a factor
of two: the finviz taxonomy is mega-cap polluted and sprawling, so "Commodities
Metals" spans gold, silver, copper, steel, aluminium and lithium and scores
rho_bar 0.39 across all 51 names. The eight rows that actually shipped were all
precious-metals miners and score 0.81 — the same 0.81 GDX's own top holdings
score. Gating on the theme-wide number would have refused every theme in the
inventory, including the one the operator asked for. The cohort that matters is
the one the card is about to show, so cohesion is computed on THOSE rows, at post
time, from the same curated bar trees the card renderer draws its sparklines
from. The builder still records a theme-wide rho for a human reading the file,
labelled ``diagnostic_`` so nothing mistakes it for the gate input.

Fail-soft everywhere: a missing map, a malformed row, an unknown theme, absent
bars or a failed leg all return None, and the caller posts exactly what it posts
today.
"""
from __future__ import annotations

import json
import logging
import math
from itertools import combinations
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

PathLike = "str | Path"

#: Bars, in the order the publish lane's own card renderer prefers them. The
#: curated basket tree is FIRST and that ordering is load-bearing: ``data/yahoo``
#: carries 1 of GDX's 16 US-listed constituents, so a yahoo-first loader measures
#: gold-miner cohesion as "panel too thin" and silently kills the flagship case
#: this module was built for. ``data/baskets/ohlcv`` has 2,768 names including the
#: small miners.
BAR_TREES: tuple[str, ...] = ("data/baskets/ohlcv", "data/stocks", "data/yahoo")

#: Correlation window. 252 sessions ~ one year: long enough that a single macro
#: week cannot manufacture cohesion, short enough to describe the group as it
#: trades now.
CORR_DAYS = 252
#: A panel narrower than this, or shorter than this, is UNMEASURED — which is
#: neither cohesion 0 nor cohesion 1. :func:`cohesion` returns None and the gate
#: reads a non-finite rho as a refusal.
MIN_CORR_NAMES = 4
MIN_CORR_ROWS = 120

#: Where the builder writes and this module reads.
MAP_REL = ("data", "marketing", "theme_proxy_map.json")

#: Thresholds. Defaults live here so a map produced by an older builder — or a
#: hand-edited one — still gates on something, rather than gating on nothing.
#: The map may carry its own ``gate`` block, which wins when present, so an
#: operator retune is a data edit and not a deploy.
DEFAULT_GATE: dict[str, float] = {
    #: rho_bar floor. 0.65 sits in the empty band between the two "one trade"
    #: cohorts measured (gold miners 0.80, regional banks 0.79) and the densest
    #: part of the stock-pickers' distribution (semis 0.48 and below), so the
    #: threshold is not perched on top of any observation.
    "min_cohesion": 0.65,
    #: The proxy must out-trade the biggest name the TEXT will name. 1.0 = a
    #: strict win; there is no reach argument for a tie.
    "min_reach_ratio": 1.0,
    #: Fraction of the card's rows the fund must hold (``holdings`` class only).
    #: 0.5 is the majority reading of "the fund is about these names".
    "min_row_coverage": 0.5,
    #: Share of the FUND's own weight that must sit in the card's rows. Kills
    #: the $SMH-on-Industrial-Automation shape (1.8%) while clearing $GDX on
    #: gold miners (30.3%). ``holdings`` class only.
    "min_weight_coverage": 10.0,
}


def _load_json(path: Path) -> Any:
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:  # noqa: BLE001
        return None


def load_map(root: PathLike | None) -> dict[str, Any]:
    """Read the proxy map. ``{}`` on any failure — never raises."""
    if root is None:
        return {}
    raw = _load_json(Path(root).joinpath(*MAP_REL))
    if not isinstance(raw, dict):
        return {}
    if not isinstance(raw.get("themes"), dict):
        return {}
    return raw


def load_tiers(root: PathLike | None) -> dict[str, Any]:
    """The FULL ``tickers`` block of cashtag_tiers.json — rows, not tier labels.

    ``movers_source._load_cashtag_tiers`` flattens the same file to
    ``{ticker: tier}``, which throws away the ``proxies.adv20_musd`` this module's
    whole reach leg is measured in. Two loaders over one file is the smaller evil
    against silently reading ``"T2"`` as a dollar volume.
    """
    if root is None:
        return {}
    raw = _load_json(Path(root) / "data" / "marketing" / "cashtag_tiers.json")
    if not isinstance(raw, dict):
        return {}
    tickers = raw.get("tickers")
    return tickers if isinstance(tickers, dict) else {}


def adv20_musd(tiers: dict[str, Any], ticker: str) -> float:
    """ADV20 in $M for *ticker*; 0.0 when unknown. The lane's watchedness proxy.

    ADV IS NOT X REACH and the difference is worth stating where it is read: this
    measures dollars traded, not followers watching a cashtag. They correlate —
    a ticker nobody trades is a ticker nobody posts about — but a retail-narrative
    name can out-chatter its dollar volume and an institutional instrument can
    under-chatter its own. It is the best in-house proxy we have that is rebuilt
    nightly from our own data and cannot be gamed by a vendor, and every tag it
    picks is stamped on the outbox item so ``post_metrics`` can grade the two arms
    against real impressions later instead of trusting this prior forever.
    """
    return _adv(tiers, ticker)


def gate_of(pmap: dict[str, Any]) -> dict[str, float]:
    """Thresholds for *pmap*: its own ``gate`` block over :data:`DEFAULT_GATE`.

    A malformed or partial block degrades PER KEY rather than wholesale, so one
    bad value cannot silently un-gate the other three legs.
    """
    out = dict(DEFAULT_GATE)
    block = pmap.get("gate")
    if isinstance(block, dict):
        for k in DEFAULT_GATE:
            if k in block:
                try:
                    out[k] = float(block[k])
                except (TypeError, ValueError):
                    log.warning("theme_proxy: bad gate.%s=%r — keeping %s",
                                k, block[k], out[k])
    return out


def _adv(tiers: dict[str, Any], ticker: str) -> float:
    """ADV20 in $M for *ticker* from a loaded cashtag_tiers ``tickers`` map."""
    row = tiers.get(str(ticker).upper())
    if not isinstance(row, dict):
        return 0.0
    try:
        return float((row.get("proxies") or {}).get("adv20_musd") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def daily_returns(ticker: str, root: PathLike, *, days: int = CORR_DAYS):
    """Daily returns for *ticker* from the first :data:`BAR_TREES` tree with bars.

    Returns a pandas Series, or None when no tree has a usable series. pandas is
    imported lazily: importing this module must stay stdlib-only, because the
    publish lane imports it on every call and a missing optional dep has never
    been allowed to break a post.
    """
    try:
        import pandas as pd  # noqa: PLC0415
    except Exception:  # noqa: BLE001
        return None
    for tree in BAR_TREES:
        path = Path(root) / tree / f"{ticker}.parquet"
        if not path.exists():
            continue
        try:
            df = pd.read_parquet(path)
        except Exception:  # noqa: BLE001
            continue
        col = next((c for c in ("adj_close", "close", "Close", "Adj Close")
                    if c in df.columns), None)
        if col is None:
            continue
        dcol = next((c for c in ("date", "Date", "dt") if c in df.columns), None)
        if dcol is not None:
            try:
                df = df.set_index(pd.to_datetime(df[dcol]))
            except Exception:  # noqa: BLE001
                pass
        s = pd.to_numeric(df[col], errors="coerce").dropna()
        s = s.iloc[-(days + 1):].pct_change().dropna()
        if len(s) > 60:
            return s
    return None


def cohesion(tickers: list[str], root: PathLike) -> tuple[float | None, int]:
    """Mean pairwise correlation of *tickers*' daily returns; and the panel width.

    THE EXECUTABLE FORM OF THE OPERATOR'S OWN MECHANISM — "they all rise together
    as one sector anyways, and it doesn't matter whihc name u buy everything goes
    up". Measured on the card's rows, not on the theme (see the module header).

    Returns (None, n) when the panel is too thin or too short to mean anything.
    """
    try:
        import pandas as pd  # noqa: PLC0415
        import numpy as np  # noqa: PLC0415
    except Exception:  # noqa: BLE001
        return None, 0
    series = {}
    for t in tickers:
        s = daily_returns(t, root)
        if s is not None:
            series[t] = s
    if len(series) < MIN_CORR_NAMES:
        return None, len(series)
    panel = pd.DataFrame(series).dropna(how="any")
    if panel.shape[1] < MIN_CORR_NAMES or len(panel) < MIN_CORR_ROWS:
        return None, panel.shape[1]
    corr = panel.corr()
    vals = [corr.iloc[i, j] for i, j in combinations(range(corr.shape[0]), 2)]
    if not vals:
        return None, panel.shape[1]
    rho = float(np.mean(vals))
    return (rho if np.isfinite(rho) else None), panel.shape[1]


def resolve(
    theme: str,
    card_tickers: list[str],
    named_tickers: list[str],
    *,
    pmap: dict[str, Any],
    tiers: dict[str, Any],
    root: PathLike,
) -> dict[str, Any] | None:
    """The proxy cashtag for *theme*, or None when no candidate clears the gate.

    Args:
        theme: the theme name, exactly as the theme item carries it.
        card_tickers: the rows the CARD will show. Legs 2 and 3 are measured
            against these, because a map row computed over the whole theme
            cannot know which of its names showed up today — and for cohesion
            that difference is the whole answer (0.39 theme-wide vs 0.81 on the
            rows, for the case this module was built for).
        named_tickers: the member tickers the TEXT will name. Leg 1 is measured
            against the biggest of THESE — not against the card's biggest and
            not against the theme's biggest mega-cap. The point of the tag is to
            out-reach what we would otherwise have said out loud.
        pmap: a :func:`load_map` result.
        tiers: the ``tickers`` block of ``data/marketing/cashtag_tiers.json``.
        root: repo root, for the bar trees cohesion reads.

    Returns ``{"cashtag", "ticker", "basis", "receipts"}`` or None. Never raises.
    """
    try:
        return _resolve(theme, card_tickers, named_tickers,
                        pmap=pmap, tiers=tiers, root=root)
    except Exception as exc:  # noqa: BLE001 — a tag is never worth a dropped post
        log.warning("theme_proxy: resolve failed for %r (%s) — no proxy", theme, exc)
        return None


def _resolve(theme, card_tickers, named_tickers, *, pmap, tiers, root):
    row = (pmap.get("themes") or {}).get(str(theme))
    if not isinstance(row, dict):
        return None
    cands = row.get("candidates")
    if not isinstance(cands, list) or not cands:
        return None

    gate = gate_of(pmap)
    card = [str(t).upper() for t in (card_tickers or []) if t]
    named = [str(t).upper() for t in (named_tickers or []) if t]
    if not card or not named:
        return None

    # Leg 1's bar: the biggest ticker the text would name WITHOUT a proxy.
    named_max = max((_adv(tiers, t) for t in named), default=0.0)
    if named_max <= 0:
        # No ADV for anything we are about to name means the reach comparison has
        # no denominator. A ratio against 0 is not "infinitely good", it is
        # unmeasured — refuse rather than ship an unjustified tag.
        return None

    card_set = set(card)
    # The map lists candidates already ordered most-traded-first by the builder;
    # re-read ADV from tiers anyway so a stale map cannot pin a stale ordering.
    ordered = sorted(
        (c for c in cands if isinstance(c, dict) and c.get("ticker")),
        key=lambda c: -_adv(tiers, c["ticker"]),
    )
    # LEG 1 first, over the whole candidate list, BEFORE any bar reading: if not
    # one candidate out-trades what we were going to name anyway, there is no
    # proxy to be had and the correlation panel would be pure wasted I/O in the
    # publish path.
    ordered = [c for c in ordered
               if _adv(tiers, c["ticker"]) >= named_max * gate["min_reach_ratio"]]
    if not ordered:
        return None

    # LEG 2 — cohesion, over the CARD's rows. A property of the group, not of any
    # fund, so it is computed once and shared by every candidate below.
    rho, panel_n = cohesion(card, root)
    if rho is None or not math.isfinite(rho):
        log.info("theme_proxy: %r cohesion unmeasured (panel n=%s) — no proxy",
                 theme, panel_n)
        return None
    if rho < gate["min_cohesion"]:
        return None

    for cand in ordered:
        tkr = str(cand["ticker"]).upper()
        basis = str(cand.get("basis") or "holdings")
        padv = _adv(tiers, tkr)

        # LEG 3 — representativeness, for the holdings class only. A declared
        # commodity link has no constituents to check; its basis is the reviewed
        # map entry, and it still had to clear legs 1 and 2 above.
        receipts: dict[str, Any] = {
            "proxy_adv_musd": round(padv, 1),
            "named_max_adv_musd": round(named_max, 1),
            # Guarded division. `named_max <= 0` already returned above, so this
            # cannot divide by zero TODAY — and when it was written as a bare
            # `padv / named_max` the crash became the de-facto guard: removing the
            # `named_max <= 0` check still produced None, via the exception
            # handler, so the test pinning that check passed under mutation and
            # was measuring nothing. A guard whose only evidence is a traceback is
            # not a guard.
            "reach_ratio": (round(padv / named_max, 2) if named_max > 0 else None),
            "cohesion_rho": round(rho, 3),
            "cohesion_panel_n": panel_n,
            "card_rows": len(card),
        }
        if basis == "holdings":
            holds = {str(t).upper() for t in (cand.get("holdings") or [])}
            weights = cand.get("weights") or {}
            hit = card_set & holds
            row_cov = len(hit) / len(card_set)
            try:
                w_cov = float(sum(float(weights.get(t, 0.0)) for t in hit))
            except (TypeError, ValueError):
                w_cov = 0.0
            if row_cov < gate["min_row_coverage"]:
                continue
            if w_cov < gate["min_weight_coverage"]:
                continue
            receipts.update({
                "rows_held": len(hit),
                "row_coverage": round(row_cov, 3),
                "weight_coverage_pct": round(w_cov, 1),
                "holdings_asof": cand.get("asof"),
            })
        elif basis != "declared":
            # An unknown basis is not a free pass. Fail closed.
            log.warning("theme_proxy: unknown basis %r on %s/%s — skipped",
                        basis, theme, tkr)
            continue

        return {
            "cashtag": f"${tkr}",
            "ticker": tkr,
            "basis": basis,
            "receipts": receipts,
        }

    return None
