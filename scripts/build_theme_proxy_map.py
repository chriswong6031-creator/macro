"""Build data/marketing/theme_proxy_map.json — the theme -> proxy-cashtag map.

The offline half of the design documented in ``engine/marketing/theme_proxy``.
This script does the expensive, auditable work once (read every ETF holdings
store, correlate every theme's members over 252 sessions) and writes a small
artifact the publish-time lane can read for free.

WHY OFFLINE. Post time knows one thing the builder cannot — which eight names
showed up on today's card — and the builder knows two things post time cannot
afford: the holdings of 75 funds and a 252-day correlation matrix per theme.
Splitting on that line keeps the render/publish path cheap AND makes the decision
auditable: the committed map IS the receipt for every tag that ships.

WHAT IT WRITES, per theme:
  * ``candidates``     — proxies ordered most-traded-first, each carrying the
                         constituent list + weights that leg 3 is checked against
  * ``diagnostic_cohesion_rho`` — mean pairwise correlation across the theme's
                         FULL membership. Named ``diagnostic_`` because it is NOT
                         the gate input and must never become one: the finviz
                         taxonomy is mega-cap polluted and sprawling, so
                         "Commodities Metals" spans gold, silver, copper, steel,
                         aluminium and lithium and scores 0.39 across all 51
                         names, while the eight precious-metals rows that
                         actually shipped score 0.81. An earlier draft of this
                         script gated on the theme-wide number and refused all 40
                         themes — including the one the operator asked for.
                         Cohesion is measured at post time on the card's own
                         rows; see ``engine.marketing.theme_proxy.cohesion``.

SELECTION IS NOT ASSERTION. Equity candidates are DERIVED: any stored fund that
holds enough of the theme's members is a candidate, and the gate does the
rejecting at post time against the live card. The only hand-authored input is
:data:`DECLARED` — the commodity/asset-class links, which no holdings file can
express because a bullion fund holds metal rather than miners.

Usage:
    python -m scripts.build_theme_proxy_map            # write the map
    python -m scripts.build_theme_proxy_map --dry-run  # print the table only
"""
from __future__ import annotations

import argparse
import glob
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from collectors.holdings import drop_non_equity  # noqa: E402
from engine.marketing import theme_proxy  # noqa: E402

log = logging.getLogger("build_theme_proxy_map")

ROOT = Path(__file__).resolve().parents[1]

THEMES_JSON = ROOT / "finviz_themes" / "finviz_themes_map.json"
TIERS_JSON = ROOT / "data" / "marketing" / "cashtag_tiers.json"
HOLDINGS_DIR = ROOT / "data" / "etf_holdings"
OUT_JSON = ROOT / "data" / "marketing" / "theme_proxy_map.json"

#: Broad index funds are never a THEME proxy. $SPY on "Artificial Intelligence"
#: would pass a naive weight test through sheer mega-cap overlap and says
#: nothing about the group that moved.
BROAD = frozenset({"SPY", "QQQ", "DIA", "MDY", "RSP", "MOAT", "IWM", "VTI"})

#: Declared commodity / asset-class proxies — the ``declared`` basis.
#:
#: These cannot be derived: a bullion ETF's holdings are metal, so it shares no
#: constituent with any equity theme and every holdings test scores it zero.
#: The link is an economic one (the miners are levered to the metal), it is
#: reviewed by a human, and it still has to clear the reach and cohesion legs at
#: post time like any other candidate.
#:
#: Operator ruling 2026-08-05, on whether the copy must explain the difference:
#: "When gold goes up, its miners go up, its that simple, don't need to
#: overcomplicate and shit." So the class is recorded here for the audit trail
#: and changes nothing about how the tag reads in the post.
#:
#: NOT included, deliberately: ``$GOLD`` and ``$SILVER``. ``GOLD`` is not a live
#: ticker — it is absent from the 2,655-name cashtag universe because Barrick
#: renamed to ``$B``, so the cashtag is a stale-ticker collision carrying another
#: company's history; ``SILVER`` was never a US ticker. Both still resolve to X
#: search surfaces, which makes them a real reach question, but they are
#: non-instruments: no price, no card row, and nothing the engine can verify.
#: They stay out until an operator asks for a non-instrument tag class by name.
DECLARED: dict[str, list[str]] = {
    "Commodities Metals": ["GLD", "SLV"],
    "Commodities Energy": ["USO", "UNG"],
    "Commodities Agriculture": ["DBA", "CORN"],
}

#: A fund needs at least this many of a theme's members before it is even
#: recorded as a candidate. Cheap pre-filter only — the real coverage test runs
#: at post time against the live card, where it is measured against the eight
#: rows that actually showed up rather than the theme's whole sprawl.
MIN_MEMBER_HITS = 3

def load_tiers() -> dict:
    try:
        with open(TIERS_JSON, encoding="utf-8") as fh:
            return (json.load(fh) or {}).get("tickers") or {}
    except Exception as exc:  # noqa: BLE001
        print(f"::warning title=theme-proxy-tiers::cashtag_tiers unreadable ({exc}) "
              f"— every reach leg will be unmeasured", flush=True)
        return {}


def adv(tiers: dict, ticker: str) -> float:
    row = tiers.get(str(ticker).upper())
    if not isinstance(row, dict):
        return 0.0
    try:
        return float((row.get("proxies") or {}).get("adv20_musd") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def load_holdings() -> dict[str, dict]:
    """Latest holdings snapshot per stored ETF: {ticker -> weight_pct}."""
    out: dict[str, dict] = {}
    if not HOLDINGS_DIR.exists():
        print("::warning title=theme-proxy-holdings::data/etf_holdings absent — "
              "no holdings-class candidate can be derived", flush=True)
        return out
    for name in sorted(os.listdir(HOLDINGS_DIR)):
        d = HOLDINGS_DIR / name
        if not d.is_dir() or name in BROAD:
            continue
        files = sorted(glob.glob(str(d / "*.parquet")))
        if not files:
            continue
        try:
            df = pd.read_parquet(files[-1])
        except Exception:  # noqa: BLE001
            continue
        if "ticker" not in df.columns or "weight_pct" not in df.columns:
            continue
        # Stored snapshots RETAIN the sponsor's cash/FX/derivative sleeve rows —
        # weed them with the shared predicate before the weights are summed. The
        # space-filter below drops "USD CASH"-shaped lines as a side effect of
        # dropping foreign listings, but never a BARE code ("USD", "CASH_USD").
        # Inert while no cash string collides with a real ticker; `CASH` is both
        # a cash sentinel and a live published ticker (Pathward Financial), and a
        # collision would silently inflate a theme's holdings-coverage score.
        df = drop_non_equity(df)
        df = df[df["ticker"].notna()].copy()
        df["ticker"] = df["ticker"].astype(str).str.strip().str.upper()
        # Foreign listings arrive as "NST AU" / "1234 HK". They are real holdings
        # but they can never match a US card row, and keeping them would inflate
        # the denominator of nothing while adding noise to the stored weights.
        df = df[~df["ticker"].str.contains(" ")]
        if df.empty:
            continue
        w = df.groupby("ticker")["weight_pct"].sum().astype(float)
        out[name.upper()] = {
            "weights": {k: round(float(v), 4) for k, v in w.items()},
            "asof": (str(df["as_of"].iloc[0])[:10] if "as_of" in df.columns else None),
        }
    return out


def build(*, dry_run: bool = False) -> dict:
    with open(THEMES_JSON, encoding="utf-8") as fh:
        themes = (json.load(fh) or {}).get("themes") or []
    tiers = load_tiers()
    holdings = load_holdings()
    log.info("themes=%d etf_holdings=%d tiers=%d", len(themes), len(holdings), len(tiers))

    out_themes: dict[str, dict] = {}
    table: list[dict] = []

    for th in themes:
        name = str(th.get("theme") or "")
        if not name:
            continue
        members: set[str] = set()
        for ss in th.get("subsectors") or []:
            members.update(str(m).upper() for m in (ss.get("members") or []) if m)
        if not members:
            continue

        # Diagnostic only — see the module header on why this must never gate.
        rho, panel_n = theme_proxy.cohesion(sorted(members), ROOT)

        cands: list[dict] = []
        for etf, blob in holdings.items():
            weights = blob["weights"]
            hit = sorted(members & set(weights))
            if len(hit) < MIN_MEMBER_HITS:
                continue
            a = adv(tiers, etf)
            if a <= 0:
                # No ADV = no reach case to make. Recording it would only invite
                # a future edit to un-gate leg 1 for "candidates we already have".
                continue
            cands.append({
                "ticker": etf,
                "basis": "holdings",
                "adv20_musd": round(a, 1),
                "asof": blob["asof"],
                # Only the intersection is stored: the gate measures coverage of
                # the CARD's rows, and a card row is always a theme member, so
                # constituents outside the theme can never affect the answer.
                # Storing 60 unrelated names per fund would bloat the artifact
                # the publish lane parses on every call.
                "holdings": hit,
                "weights": {t: weights[t] for t in hit},
            })
        for etf in DECLARED.get(name, []):
            a = adv(tiers, etf)
            if a <= 0:
                log.info("declared proxy %s for %r has no ADV — skipped", etf, name)
                continue
            cands.append({
                "ticker": etf,
                "basis": "declared",
                "adv20_musd": round(a, 1),
            })

        cands.sort(key=lambda c: -c["adv20_musd"])
        if not cands:
            continue

        best = cands[0]
        out_themes[name] = {
            "diagnostic_cohesion_rho": (round(rho, 4) if rho is not None else None),
            "diagnostic_cohesion_panel_n": panel_n,
            "n_members": len(members),
            "candidates": cands,
        }
        table.append({
            "theme": name[:30],
            "diag_rho": (round(rho, 2) if rho is not None else None),
            "n": panel_n,
            "best": best["ticker"],
            "basis": best["basis"][:8],
            "adv_M": round(best["adv20_musd"]),
            "cands": len(cands),
        })

    payload = {
        "schema": "theme_proxy_map/1",
        "produced_by": "scripts/build_theme_proxy_map.py",
        "produced_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "inputs": {
            "themes": str(THEMES_JSON.relative_to(ROOT)),
            "tiers": str(TIERS_JSON.relative_to(ROOT)),
            "holdings_dir": str(HOLDINGS_DIR.relative_to(ROOT)),
            "etfs_with_holdings": len(holdings),
            "bar_trees": list(theme_proxy.BAR_TREES),
            "corr_days": theme_proxy.CORR_DAYS,
        },
        # The thresholds ship WITH the map so the artifact is self-describing:
        # a human reading the file can tell why a candidate is listed but never
        # tagged, and an operator can retune without a deploy. Keep in step with
        # engine.marketing.theme_proxy.DEFAULT_GATE, which is what a map without
        # this block falls back to.
        "gate": dict(theme_proxy.DEFAULT_GATE),
        "themes": out_themes,
    }

    if table:
        df = pd.DataFrame(table).sort_values("diag_rho", ascending=False,
                                            na_position="last")
        pd.set_option("display.width", 200, "display.max_rows", 60)
        print(df.to_string(index=False))
    print(f"\nthemes with candidates: {len(out_themes)}/{len(themes)}  "
          f"| ETFs with holdings: {len(holdings)}")
    print("diag_rho is theme-wide and DIAGNOSTIC — the gate measures cohesion on "
          "the card's own rows at post time.")

    if dry_run:
        print(f"(dry run — {OUT_JSON.relative_to(ROOT)} not written)")
        return payload

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=1, sort_keys=False)
        fh.write("\n")
    print(f"wrote {OUT_JSON.relative_to(ROOT)}")
    return payload


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true",
                    help="print the table without writing the map")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    build(dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
