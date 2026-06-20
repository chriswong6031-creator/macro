"""TrumpFlow entity graph — pure-Python (no DB, no networkx dependency).

Loads the curated provenance-weighted edge seed (data/trumpflow/intel.json) and runs
the two queries that catch a latent stake the structured feeds miss:

  short_paths()      BFS from a Trump person to a THEME node — the chain that would have
                     surfaced "Eric Trump -> American Bitcoin -> Hut 8 -> AI power infra"
                     at formation, before the market re-rated it.
  label_mismatches() an entity BRANDED as theme X whose value actually accrues to a
                     parent in theme Y (via OPERATED_BY / HOLDS_STAKE) — the ABTC trap:
                     branded 'crypto', but the real engine is Hut 8, an AI-power-infra
                     hyperscaler. The flag REPOINTS the subject to the parent ticker.

build_view() assembles those + a per-ticker watch list, cross-referenced against the
live Quiver alt-data (engine.altdata_signals.by_ticker) for corroboration. Everything
is display/context-only.
"""
from __future__ import annotations

import json
import logging
from collections import deque
from datetime import datetime, timezone

from lib import config

log = logging.getLogger(__name__)

_OWNERSHIP = {"OPERATED_BY", "HOLDS_STAKE", "FORMED", "CONTROLS", "LINKED_TO"}
_MAX_HOPS = 5


def load_intel(root=None) -> dict:
    base = (config.data_dir() if root is None else (root / "data")) / "trumpflow" / "intel.json"
    if not base.exists():
        return {}
    try:
        return json.loads(base.read_text())
    except Exception as e:  # noqa: BLE001
        log.warning("trumpflow: cannot read intel.json: %s", e)
        return {}


def _index(intel: dict):
    people = {p["id"]: p for p in intel.get("people", [])}
    ents = {e["id"]: e for e in intel.get("entities", [])}
    adj: dict[str, list] = {}
    for e in intel.get("edges", []):
        adj.setdefault(e["src"], []).append(e)
    return people, ents, adj


def _theme_label(intel: dict, theme_id: str) -> dict:
    t = intel.get("themes", {}).get(theme_id, {})
    return {"id": theme_id, "en": t.get("en", theme_id), "zh": t.get("zh", theme_id)}


def _node_name(people, ents, intel, nid: str) -> str:
    if nid.startswith("theme:"):
        return _theme_label(intel, nid.split(":", 1)[1])["en"]
    if nid in people:
        return people[nid]["name"]
    if nid in ents:
        return ents[nid]["name"]
    return nid


def short_paths(intel: dict) -> list[dict]:
    """BFS from every Trump person to each reachable THEME node."""
    people, ents, adj = _index(intel)
    out = []
    for pid in people:
        seen = {pid}
        q = deque([(pid, [], 1.0)])
        while q:
            node, path, minc = q.popleft()
            if len(path) >= _MAX_HOPS:
                continue
            for e in adj.get(node, []):
                dst, conf = e["dst"], float(e.get("confidence", 0.5))
                step = {"src": node, "src_name": _node_name(people, ents, intel, node),
                        "rel": e["rel"], "dst": dst, "dst_name": _node_name(people, ents, intel, dst),
                        "provenance": e.get("provenance"), "confidence": conf}
                npath, nminc = path + [step], min(minc, conf)
                if dst.startswith("theme:"):
                    out.append({
                        "person": people[pid]["name"], "person_zh": people[pid].get("name_zh", ""),
                        "theme": _theme_label(intel, dst.split(":", 1)[1]),
                        "hops": npath, "min_confidence": round(nminc, 2),
                        "endpoint_ticker": _last_ticker(npath, ents),
                    })
                elif dst not in seen:
                    seen.add(dst)
                    q.append((dst, npath, nminc))
    # strongest, longest-supported paths first; de-dup (person, theme) keeping best conf
    best: dict = {}
    for p in sorted(out, key=lambda r: (r["min_confidence"], len(r["hops"])), reverse=True):
        key = (p["person"], p["theme"]["id"])
        best.setdefault(key, p)
    return list(best.values())


def _last_ticker(hops: list, ents: dict) -> str | None:
    """The ticker of the last tickered entity on the path (the investable proxy)."""
    for step in reversed(hops):
        e = ents.get(step["dst"]) or ents.get(step["src"])
        if e and e.get("ticker"):
            return e["ticker"]
    return None


def label_mismatches(intel: dict) -> list[dict]:
    """Entity branded theme X whose value accrues to a parent in theme Y."""
    people, ents, adj = _index(intel)
    # entity -> its own MEMBER_OF theme(s)
    member = {}
    for e in intel.get("edges", []):
        if e["rel"] == "MEMBER_OF" and e["dst"].startswith("theme:"):
            member.setdefault(e["src"], []).append((e["dst"].split(":", 1)[1], float(e.get("confidence", 0.5))))

    out = []
    seen = set()
    for eid, ent in ents.items():
        brand = ent.get("brand_theme")
        if not brand:
            continue
        # operating / controlling parents of this entity (dedup — a parent can be reached
        # via both OPERATED_BY and HOLDS_STAKE)
        parents = {x["dst"] for x in adj.get(eid, []) if x["rel"] == "OPERATED_BY"}
        parents |= {e["src"] for e in intel.get("edges", [])
                    if e["rel"] == "HOLDS_STAKE" and e["dst"] == eid}
        for pid in parents:
            pthemes = member.get(pid, [])
            for th, conf in pthemes:
                if th != brand and (eid, pid, th) not in seen:
                    seen.add((eid, pid, th))
                    pent = ents.get(pid, {})
                    out.append({
                        "entity": ent["name"], "entity_ticker": ent.get("ticker"),
                        "brand_theme": _theme_label(intel, brand),
                        "real_theme": _theme_label(intel, th),
                        "parent": pent.get("name", pid), "parent_ticker": pent.get("ticker"),
                        "confidence": round(conf, 2),
                        "note": pent.get("note", ""),
                        "repointed_ticker": pent.get("ticker") or ent.get("ticker"),
                    })
    return out


def build_view(by_ticker: dict | None = None, root=None) -> dict:
    intel = load_intel(root)
    if not intel:
        return {}
    people, ents, adj = _index(intel)
    paths = short_paths(intel)
    mismatches = label_mismatches(intel)

    # per-ticker watch list, cross-referenced against the live alt-data
    bt = (by_ticker or {}).get("tickers", {}) if by_ticker else {}
    who = {}  # ticker -> set of Trump people controlling/linked (via any path)
    for p in paths:
        tk = p.get("endpoint_ticker")
        if tk:
            who.setdefault(tk, set()).add(p["person"])
    watch = []
    for eid, ent in ents.items():
        tk = ent.get("ticker")
        if not tk:
            continue
        adrec = bt.get(tk) or {}
        themes = sorted({th for th, _ in
                         [(e["dst"].split(":", 1)[1], 0) for e in intel.get("edges", [])
                          if e["src"] == eid and e["rel"] == "MEMBER_OF" and e["dst"].startswith("theme:")]})
        watch.append({
            "ticker": tk, "name": ent["name"], "brand_theme": ent.get("brand_theme"),
            "themes": [_theme_label(intel, t) for t in themes],
            "trump_people": sorted(who.get(tk, set())),
            "note": ent.get("note", ""),
            "alt_corroborated": int(adrec.get("convergence_score", 0) or 0) >= 2,
            "alt_score": adrec.get("convergence_score"),
            "alt_channels": adrec.get("channels", []),
        })
    watch.sort(key=lambda w: (w["alt_corroborated"], len(w["trump_people"])), reverse=True)

    try:
        from engine.trumpflow import extract as _extract
        n_candidates = len(_extract.load_candidates(root))
    except Exception:  # noqa: BLE001
        n_candidates = 0

    view = {
        "schema": "trumpflow.graph.v1",
        "as_of": intel.get("as_of"),
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "note": intel.get("note"),
        "paths": paths,
        "mismatches": mismatches,
        "watch": watch,
        "n_nodes": len(people) + len(ents) + len(intel.get("themes", {})),
        "n_edges": len(intel.get("edges", [])),
        "n_candidates": n_candidates,
    }
    _write(view)
    log.info("trumpflow graph: %d paths, %d mismatches, %d watch tickers",
             len(paths), len(mismatches), len(watch))
    return view


def _write(view: dict) -> None:
    for base in (config.data_dir() / "trumpflow", config.ROOT / "site" / "altdata"):
        base.mkdir(parents=True, exist_ok=True)
    (config.data_dir() / "trumpflow" / "graph_view.json").write_text(json.dumps(view, indent=2, default=str))
    (config.ROOT / "site" / "altdata" / "latent.json").write_text(json.dumps(view, indent=2, default=str))
