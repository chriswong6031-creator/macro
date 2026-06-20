"""Influence graph engine — pure-Python (no DB, no networkx).

Loads + MERGES the curated multi-actor seed (data/altdata/influence_seed.json) with the
Trump-family seed (data/trumpflow/intel.json) into one provenance-weighted graph, then
runs the queries that turn affiliations into a signal:

  short_paths()        actor → THEME chains (BFS) — the latent path to an investable proxy.
  label_mismatches()   an entity branded theme X whose value accrues to a parent in theme Y
                       (the ABTC→Hut-8 trap), generalized to every actor's holdings.
  affiliations()       per-ticker roll-up of every actor edge that resolves to a ticker —
                       the qualitative "who is connected to this name" layer.
  recent_edges()       affiliation edges dated within N days ("new this week").

build_view() assembles those + a per-ticker watch list, cross-referenced against the live
Quiver alt-data (engine.altdata_signals by_ticker) for corroboration. Display/context for
the page; the affiliation roll-up also feeds the convergence kernel + the brain.
"""
from __future__ import annotations

import json
import logging
from collections import deque
from datetime import datetime, timezone

import pandas as pd

from lib import config

log = logging.getLogger(__name__)

# edges that mean "this actor is connected to this name's value"
_OWNERSHIP = {"OPERATED_BY", "HOLDS_STAKE", "FORMED", "CONTROLS", "LINKED_TO", "INVESTS_IN"}
_QUALITATIVE = {"TALKS_ABOUT", "AFFILIATES_WITH", "PARTNERS_WITH", "ENDORSES", "ADVISES",
                "ATTENDS_EVENT", "MEETS"}
_AFFIL_RELS = _OWNERSHIP | _QUALITATIVE
_MAX_HOPS = 5

_KIND_LABEL = {
    "politician": ("Politician", "政界"),
    "trump_family": ("Trump family", "特朗普家族"),
    "exec": ("Founder / exec", "创始人/高管"),
    "fund": ("Fund / activist", "基金/激进投资者"),
    "influencer": ("Influencer", "意见领袖"),
}


# --------------------------------------------------------------------------- load + merge
def _read_json(path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception as e:  # noqa: BLE001
        log.warning("influence: cannot read %s: %s", path, e)
        return {}


def load_seed(root=None) -> dict:
    """Merge the Trump-family seed (trumpflow/intel.json) + the multi-actor seed
    (altdata/influence_seed.json) into one graph. Actor `tickers` become CONTROLS edges so
    the affiliation roll-up picks up an actor's own company."""
    data = config.data_dir() if root is None else (root / "data")
    intel = _read_json(data / "trumpflow" / "intel.json")
    seed = _read_json(data / "altdata" / "influence_seed.json")

    actors: dict[str, dict] = {}
    for p in intel.get("people", []):
        actors[p["id"]] = {**p, "kind": p.get("kind", "trump_family"), "tickers": p.get("tickers", [])}
    for a in seed.get("actors", []):
        actors[a["id"]] = {**a, "kind": a.get("kind", "exec"), "tickers": a.get("tickers", [])}

    themes = {**intel.get("themes", {}), **seed.get("themes", {})}
    entities: dict[str, dict] = {e["id"]: e for e in intel.get("entities", [])}
    for e in seed.get("entities", []):
        entities[e["id"]] = e

    edges = list(intel.get("edges", [])) + list(seed.get("edges", []))
    # synthesize a primary-affiliation edge from each actor's `tickers`, but ONLY label it
    # CONTROLS for a founder/exec/family member — a politician or influencer who appears with
    # a ticker is AFFILIATED_WITH it, not in control of it (don't assert false control).
    have = {(e.get("src"), e.get("rel"), e.get("dst")) for e in edges}
    have_pair = {(e.get("src"), e.get("dst")) for e in edges}      # any rel already linking them
    for aid, a in actors.items():
        rel = "CONTROLS" if a.get("kind") in ("exec", "trump_family") else "AFFILIATES_WITH"
        for tk in a.get("tickers", []) or []:
            dst = f"ticker:{tk}"
            # skip if the seed already links this actor→ticker with any (more specific) rel
            if (aid, dst) in have_pair or (aid, rel, dst) in have:
                continue
            edges.append({"src": aid, "rel": rel, "dst": dst,
                          "provenance": "FACT" if rel == "CONTROLS" else "DISCLOSED",
                          "confidence": 0.9 if rel == "CONTROLS" else 0.6,
                          "note": f"{a['name']} primary affiliation"})
            have.add((aid, rel, dst))
            have_pair.add((aid, dst))

    return {
        "as_of": seed.get("as_of") or intel.get("as_of"),
        "note": seed.get("note") or intel.get("note"),
        "actors": list(actors.values()),
        "themes": themes,
        "entities": list(entities.values()),
        "edges": edges,
        "n_seeds": int(bool(intel)) + int(bool(seed)),
    }


def _index(g: dict):
    actors = {a["id"]: a for a in g.get("actors", [])}
    ents = {e["id"]: e for e in g.get("entities", [])}
    adj: dict[str, list] = {}
    for e in g.get("edges", []):
        adj.setdefault(e["src"], []).append(e)
    return actors, ents, adj


def _theme_label(g: dict, theme_id: str) -> dict:
    t = g.get("themes", {}).get(theme_id, {})
    return {"id": theme_id, "en": t.get("en", theme_id), "zh": t.get("zh", theme_id)}


def _resolve_ticker(dst: str, ents: dict) -> str | None:
    """A dst → its investable ticker, or None (theme / person / un-tickered)."""
    if not dst:
        return None
    if dst.startswith("ticker:"):
        return dst.split(":", 1)[1].upper()
    e = ents.get(dst)
    if e and e.get("ticker"):
        return str(e["ticker"]).upper()
    return None


def _node_name(actors, ents, g, nid: str) -> str:
    if nid.startswith("theme:"):
        return _theme_label(g, nid.split(":", 1)[1])["en"]
    if nid.startswith("ticker:"):
        return nid.split(":", 1)[1].upper()
    if nid in actors:
        return actors[nid]["name"]
    if nid in ents:
        return ents[nid]["name"]
    return nid


# --------------------------------------------------------------------------- queries
def short_paths(g: dict) -> list[dict]:
    """BFS from every actor to each reachable THEME node — the latent chain to a proxy."""
    actors, ents, adj = _index(g)
    out = []
    for aid, a in actors.items():
        seen = {aid}
        q = deque([(aid, [], 1.0)])
        while q:
            node, path, minc = q.popleft()
            if len(path) >= _MAX_HOPS:
                continue
            for e in adj.get(node, []):
                dst, conf = e["dst"], float(e.get("confidence", 0.5))
                step = {"src": node, "src_name": _node_name(actors, ents, g, node),
                        "rel": e["rel"], "dst": dst, "dst_name": _node_name(actors, ents, g, dst),
                        "provenance": e.get("provenance"), "confidence": conf}
                npath, nminc = path + [step], min(minc, conf)
                if dst.startswith("theme:"):
                    out.append({
                        "actor": a["name"], "actor_zh": a.get("name_zh", ""),
                        "actor_kind": a.get("kind"),
                        "theme": _theme_label(g, dst.split(":", 1)[1]),
                        "hops": npath, "min_confidence": round(nminc, 2),
                        "endpoint_ticker": _last_ticker(npath, ents),
                    })
                elif dst not in seen and not dst.startswith("ticker:"):
                    seen.add(dst)
                    q.append((dst, npath, nminc))
    best: dict = {}
    for p in sorted(out, key=lambda r: (r["min_confidence"], len(r["hops"])), reverse=True):
        best.setdefault((p["actor"], p["theme"]["id"]), p)
    return list(best.values())


def _last_ticker(hops: list, ents: dict) -> str | None:
    for step in reversed(hops):
        tk = _resolve_ticker(step["dst"], ents) or _resolve_ticker(step["src"], ents)
        if tk:
            return tk
    return None


def label_mismatches(g: dict) -> list[dict]:
    """Entity branded theme X whose value accrues to a parent in theme Y (the repoint)."""
    actors, ents, adj = _index(g)
    member = {}
    for e in g.get("edges", []):
        if e["rel"] == "MEMBER_OF" and e["dst"].startswith("theme:"):
            member.setdefault(e["src"], []).append((e["dst"].split(":", 1)[1], float(e.get("confidence", 0.5))))
    out, seen = [], set()
    for eid, ent in ents.items():
        brand = ent.get("brand_theme")
        if not brand:
            continue
        parents = {x["dst"] for x in adj.get(eid, []) if x["rel"] == "OPERATED_BY"}
        parents |= {e["src"] for e in g.get("edges", [])
                    if e["rel"] == "HOLDS_STAKE" and e["dst"] == eid}
        for pid in parents:
            for th, conf in member.get(pid, []):
                if th != brand and (eid, pid, th) not in seen:
                    seen.add((eid, pid, th))
                    pent = ents.get(pid, {})
                    out.append({
                        "entity": ent["name"], "entity_ticker": ent.get("ticker"),
                        "brand_theme": _theme_label(g, brand), "real_theme": _theme_label(g, th),
                        "parent": pent.get("name", pid), "parent_ticker": pent.get("ticker"),
                        "confidence": round(conf, 2), "note": pent.get("note", ""),
                        "repointed_ticker": pent.get("ticker") or ent.get("ticker"),
                    })
    return out


def affiliations(g: dict) -> dict[str, list[dict]]:
    """Per-ticker roll-up: every actor edge that resolves to a ticker. The qualitative
    'who is connected to this name' layer (control, holding, advocacy, partnership)."""
    actors, ents, _ = _index(g)
    out: dict[str, list[dict]] = {}
    for e in g.get("edges", []):
        src, rel = e.get("src"), e.get("rel")
        if src not in actors or rel not in _AFFIL_RELS:
            continue
        tk = _resolve_ticker(e.get("dst"), ents)
        if not tk:
            continue
        a = actors[src]
        out.setdefault(tk, []).append({
            "actor": a["name"], "actor_kind": a.get("kind"), "rel": rel,
            "provenance": e.get("provenance"), "confidence": float(e.get("confidence", 0.5)),
            "note": e.get("note", ""), "url": e.get("url"), "date": e.get("date"),
            "qualitative": rel in _QUALITATIVE,
        })
    for tk in out:
        out[tk].sort(key=lambda r: r["confidence"], reverse=True)
    return out


def affiliation_details(g: dict) -> dict[str, str]:
    """Compact {ticker: 'short detail'} for the convergence channel."""
    out = {}
    for tk, edges in affiliations(g).items():
        lead = edges[0]
        extra = f" +{len(edges) - 1}" if len(edges) > 1 else ""
        out[tk] = f"{lead['actor']} {lead['rel'].replace('_', ' ').lower()}{extra}"
    return out


def recent_edges(g: dict, days: int = 30) -> list[dict]:
    """Affiliation edges dated within `days` — the 'new this week' surface."""
    actors, ents, _ = _index(g)
    cutoff = pd.Timestamp(datetime.now(timezone.utc).date()) - pd.Timedelta(days=days)
    out = []
    for e in g.get("edges", []):
        d = pd.to_datetime(e.get("date"), errors="coerce")
        if pd.isna(d) or d < cutoff or e.get("src") not in actors:
            continue
        out.append({
            "actor": actors[e["src"]]["name"], "rel": e["rel"],
            "target": _node_name(actors, ents, g, e["dst"]),
            "ticker": _resolve_ticker(e["dst"], ents),
            "provenance": e.get("provenance"), "note": e.get("note", ""),
            "url": e.get("url"), "date": e.get("date"),
        })
    out.sort(key=lambda r: r["date"], reverse=True)
    return out


# --------------------------------------------------------------------------- view
def build_view(by_ticker: dict | None = None, root=None) -> dict:
    g = load_seed(root)
    if not g.get("actors"):
        return {}
    actors, ents, _ = _index(g)
    paths = short_paths(g)
    mismatches = label_mismatches(g)
    affil = affiliations(g)
    bt = (by_ticker or {}).get("tickers", {}) if by_ticker else {}

    # per-ticker watch list (every tickered affiliation), cross-referenced w/ live alt-data
    watch = []
    for tk, edges in affil.items():
        adrec = bt.get(tk) or {}
        watch.append({
            "ticker": tk,
            "actors": [{"actor": e["actor"], "kind": e["actor_kind"], "rel": e["rel"],
                        "provenance": e["provenance"], "qualitative": e["qualitative"]} for e in edges[:6]],
            "n_actors": len(edges),
            "alt_corroborated": int(adrec.get("convergence_score", 0) or 0) >= 2,
            "alt_score": adrec.get("convergence_score"),
            "alt_weighted": adrec.get("weighted_score"),
            "alt_channels": adrec.get("channels", []),
            "top_holder": _top_holder(tk, root),
        })
    watch.sort(key=lambda w: (w["alt_corroborated"], w["n_actors"]), reverse=True)

    try:
        from engine.influence import extract as _extract
        n_candidates = len(_extract.load_candidates(root))
    except Exception:  # noqa: BLE001
        n_candidates = 0

    # roster summary by kind (for the page)
    roster = {}
    for a in g.get("actors", []):
        roster.setdefault(a.get("kind", "exec"), []).append(a["name"])

    view = {
        "schema": "influence.graph.v1",
        "as_of": g.get("as_of"),
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "note": g.get("note"),
        "n_actors": len(actors), "n_entities": len(ents),
        "n_themes": len(g.get("themes", {})), "n_edges": len(g.get("edges", [])),
        "kind_label": _KIND_LABEL,
        "roster": roster,
        "paths": paths,
        "mismatches": mismatches,
        "watch": watch,
        "recent": recent_edges(g, days=45),
        "n_candidates": n_candidates,
        "filings": _recent_filings(root),
    }
    _write(view)
    log.info("influence graph: %d actors, %d affiliated tickers, %d paths, %d mismatches",
             len(actors), len(affil), len(paths), len(mismatches))
    return view


def _top_holder(ticker: str, root=None) -> dict | None:
    """Largest reported shareholder (Quiver topshareholders)."""
    try:
        p = (config.data_dir() if root is None else (root / "data")) / "quiver" / "topshareholders.parquet"
        if not p.exists():
            return None
        df = pd.read_parquet(p)
        df = df[df["ticker"].astype(str).str.upper() == str(ticker).upper()]
        if df.empty:
            return None
        df = df.assign(_sh=pd.to_numeric(df["shares"], errors="coerce")).sort_values("_sh", ascending=False)
        r = df.iloc[0]
        return {"owner": r.get("owner_name"), "title": r.get("owner_title"),
                "shares": int(r["_sh"]) if pd.notna(r["_sh"]) else None}
    except Exception:  # noqa: BLE001
        return None


def _recent_filings(root=None, n: int = 12) -> list[dict]:
    """Recent tracked-entity SEC filings (the early channel), newest first."""
    try:
        p = (config.data_dir() if root is None else (root / "data")) / "trumpflow" / "edgar_filings.parquet"
        if not p.exists():
            return []
        df = pd.read_parquet(p)
    except Exception:  # noqa: BLE001
        return []
    df = df.assign(_d=pd.to_datetime(df["file_date"], errors="coerce")).sort_values("_d", ascending=False)
    out = []
    for _, r in df.head(n).iterrows():
        tk = r.get("ticker")
        out.append({"date": r.get("file_date"), "form": r.get("form"), "company": r.get("company"),
                    "ticker": (tk if (tk is not None and str(tk) != "nan") else None),
                    "items": r.get("items") or "", "url": r.get("url")})
    return out


def _write(view: dict) -> None:
    for base in (config.data_dir() / "altdata", config.ROOT / "site" / "altdata"):
        base.mkdir(parents=True, exist_ok=True)
    (config.data_dir() / "altdata" / "influence_graph.json").write_text(json.dumps(view, indent=2, default=str))
    (config.ROOT / "site" / "altdata" / "influence.json").write_text(json.dumps(view, indent=2, default=str))


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent.parent))
    logging.basicConfig(level=logging.INFO)
    v = build_view()
    print(json.dumps({k: v.get(k) for k in ("n_actors", "n_entities", "n_edges")}, indent=2) if v
          else "influence: no seed present")
