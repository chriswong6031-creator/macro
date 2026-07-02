"""Group (rotation) context for the US Buy Board 2.0 shadow build.

Maps each name → its sector / subsector / theme memberships → the leadership
states those cycle pages ALREADY publish, and fuses them into a single
leadership score ∈ [-1, +1] plus display chips and a ``surfaced_by`` list.

WHY this module exists (W6-US §2, "borrow strength from the hierarchy level
where edge exists"): name-level cross-sectional selection IC ≈ 0, but the
GROUP-level rotation engines are validated / forward-tracked (sector_central is
a gated-confluence merge of 4 engines; subsectors LAS Running/Coiling carries a
forward track record; subsector_rotation is an RRG read). The board therefore
borrows conviction from the group. The leadership score is used ONLY for
(a) ordering and (b) edge-floor MODULATION — **never** as a hard gate. The
standing caution is the China falsification: hard-gating a name by its group's
state HURT A-share reversal (research/china-subsector-gate-falsified). Group
state modulates the bar; it never slams the door.

DEFENSIVE COUPLING (mandatory). Every rotation artifact this module reads is
pending its OWN improvement session. A missing file, a missing field, or a
schema change MUST degrade to neutral (score 0, empty chips) with a freshness /
``degraded`` flag on the passport — it must NEVER crash the board build. The
reader contract (artifact path + the minimal fields we depend on) is versioned
in ``READER_CONTRACT`` in ONE place so the coupling is auditable; when a cycle
page changes shape, update the contract here, not scattered call sites.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

try:  # keep importable even if lib.config is unavailable in an odd harness
    from lib import config

    _ROOT = config.ROOT
except Exception:  # noqa: BLE001
    _ROOT = Path(__file__).resolve().parent.parent

log = logging.getLogger("group_context")

# --------------------------------------------------------------------------- #
#  READER CONTRACT — the ONE place the coupling to the cycle pages is declared. #
#  Each entry: the artifact path (relative to site/) + the minimal fields we    #
#  read. If a cycle page renames/moves these, update HERE (and the reader).     #
#  Version bump = contract changed; the passport carries it so a stale reader   #
#  against a new artifact is visible downstream.                                #
# --------------------------------------------------------------------------- #
READER_CONTRACT = {
    "version": 1,
    "sources": {
        "sector_central": {
            "path": "site/sectordata/sector_central.json",
            "join": "row.sector (GICS name) → sectors[].name",
            "fields": ["as_of", "sectors[].name", "sectors[].conviction.score",
                       "sectors[].conviction.dir", "sectors[].forward.trend_pass",
                       "sectors[].cycle.pos", "sectors[].heat.heat_1M"],
            "weight": 0.45,   # always-present leadership backbone (covers every sector)
        },
        "subsector_confluence": {
            "path": "site/marketdata/subsector_confluence.json",
            "join": "row.ticker → subsectors[].members[].ticker",
            "fields": ["as_of", "subsectors[].key", "subsectors[].label",
                       "subsectors[].class", "subsectors[].entry.tier",
                       "subsectors[].regime.state", "subsectors[].members[].ticker"],
            "weight": 0.25,
        },
        "index_leadership": {
            "path": "site/marketdata/index_leadership.json",
            "join": "subsector key (via confluence) → tabs[*].rising[]/coiling[].key",
            "fields": ["as_of", "tabs[*].rising[].key", "tabs[*].coiling[].key",
                       "tabs[*].las", "tabs[*].quadrant", "rising_star.label"],
            "weight": 0.10,   # LAS Running/Coiling — forward-tracked, so a real chip
        },
        "subsector_rotation": {
            "path": "site/marketdata/subsector_rotation.json",
            "join": "row.ticker → subsectors[].members[].t",
            "fields": ["asof", "subsectors[].quadrant", "subsectors[].rs_mom",
                       "subsectors[].emerging_score", "subsectors[].members[].t"],
            "weight": 0.10,
        },
        "baskets": {
            "path": "site/basketdata/baskets.json",
            "join": "row.ticker → baskets[].members[].symbol; theme via theme_intel",
            "fields": ["as_of", "baskets[].id", "baskets[].members[].symbol",
                       "theme_intel.themes[].id", "theme_intel.themes[].score",
                       "theme_intel.themes[].label", "theme_intel.themes[].reco"],
            "weight": 0.10,
        },
    },
}

# GICS naming differs between artifacts (standouts "Information Technology" vs
# sector_central "Technology"; "Communication Services" absent from standouts).
# Normalise on the way in so the sector join is not silently dropped.
_SECTOR_ALIASES = {
    "information technology": "technology",
    "info tech": "technology",
    "healthcare": "health care",
    "comm services": "communication services",
    "communications": "communication services",
    "consumer disc": "consumer discretionary",
    "consumer staple": "consumer staples",
}

# RRG / confluence quadrant → a signed leadership contribution in [-1, +1].
_QUADRANT_SCORE = {
    "leading": 1.0,
    "improving": 0.4,
    "weakening": -0.3,
    "lagging": -1.0,
}
# subsector confluence `class` → contribution.
_CLASS_SCORE = {
    "entry_now": 0.8,
    "forming": 0.3,
    "headwind": -0.6,
}
# subsector regime `state` → a modest tilt (EXTENDED is late, not leadership).
_REGIME_TILT = {
    "TAILWIND": 0.3, "SETUP": 0.2, "MIXED": 0.0,
    "EXTENDED": -0.1, "HEADWIND": -0.5, "AVOID": -0.5,
}


def _norm_sector(s: str | None) -> str:
    if not s:
        return ""
    k = s.strip().lower()
    return _SECTOR_ALIASES.get(k, k)


def _safe_load(path: Path) -> tuple[dict | None, str | None]:
    """Load a JSON artifact tolerantly. Returns (data, error). Never raises."""
    try:
        if not path.exists():
            return None, "missing"
        return json.loads(path.read_text()), None
    except Exception as e:  # noqa: BLE001
        return None, f"read_error:{type(e).__name__}"


def _artifact_age_days(as_of: Any) -> int | None:
    """Trading-ish staleness of an artifact's as_of date vs today (calendar days)."""
    if not as_of:
        return None
    try:
        d = datetime.fromisoformat(str(as_of)[:10]).date()
        return (date.today() - d).days
    except Exception:  # noqa: BLE001
        return None


@dataclass
class _Source:
    """A loaded rotation source with its coverage/freshness passport."""

    key: str
    data: dict | None
    error: str | None
    as_of: Any = None
    age_days: int | None = None
    degraded: bool = False

    def __post_init__(self) -> None:
        self.degraded = self.data is None or self.error is not None


class GroupContext:
    """Loads the rotation artifacts ONCE and resolves per-name context.

    Construct once per board build (cheap: five small JSON reads), then call
    :meth:`for_name` per ticker. All lookups are membership joins on already
    committed artifacts — no price math, no recompute — so the whole pass is
    well under the runtime budget.
    """

    STALE_DAYS = 4  # a rotation read older than this is flagged (weekend-tolerant)

    def __init__(self, site: Path | None = None) -> None:
        base = (site or (_ROOT / "site")).parent if site and site.name != "site" else _ROOT
        self._root = base
        self._sources: dict[str, _Source] = {}
        self._sector_by_name: dict[str, dict] = {}
        self._sub_by_ticker: dict[str, list[dict]] = {}
        self._subkey_lead: dict[str, dict] = {}   # subsector key → {running, coiling, tab, las}
        self._rot_by_ticker: dict[str, list[dict]] = {}
        self._basket_by_ticker: dict[str, list[str]] = {}
        self._theme_by_basket: dict[str, dict] = {}
        self._load_all()

    # ---- loading ---------------------------------------------------------- #
    def _load_all(self) -> None:
        for key, spec in READER_CONTRACT["sources"].items():
            data, err = _safe_load(self._root / spec["path"])
            as_of = None
            if isinstance(data, dict):
                as_of = data.get("as_of") or data.get("asof") or data.get("generated_utc")
            src = _Source(key=key, data=data, error=err, as_of=as_of,
                          age_days=_artifact_age_days(as_of))
            if src.age_days is not None and src.age_days > self.STALE_DAYS:
                src.degraded = True  # present but stale → treat as degraded for passport
            self._sources[key] = src
            if not src.degraded and isinstance(data, dict):
                try:
                    getattr(self, f"_index_{key}")(data)
                except Exception as e:  # noqa: BLE001  never let one bad shape break the rest
                    log.warning("group_context: indexing %s failed (%s) — degrading", key, e)
                    src.degraded = True

    def _index_sector_central(self, data: dict) -> None:
        for s in data.get("sectors", []) or []:
            nm = _norm_sector(s.get("name"))
            if nm:
                self._sector_by_name[nm] = s

    def _index_subsector_confluence(self, data: dict) -> None:
        for s in data.get("subsectors", []) or []:
            for m in s.get("members", []) or []:
                t = m.get("ticker")
                if t:
                    self._sub_by_ticker.setdefault(t.upper(), []).append(s)

    def _index_index_leadership(self, data: dict) -> None:
        tabs = data.get("tabs") or {}
        if not isinstance(tabs, dict):
            return
        for tab_name, tab in tabs.items():
            if not isinstance(tab, dict):
                continue
            las = tab.get("las")
            for row in tab.get("rising", []) or []:
                k = row.get("key")
                if k:
                    self._subkey_lead.setdefault(k, {}).update(
                        running=True, tab=tab_name, las=las,
                        quadrant=row.get("quadrant"))
            for row in tab.get("coiling", []) or []:
                k = row.get("key")
                if k:
                    self._subkey_lead.setdefault(k, {}).setdefault("coiling", True)
                    self._subkey_lead[k].setdefault("tab", tab_name)

    def _index_subsector_rotation(self, data: dict) -> None:
        for s in data.get("subsectors", []) or []:
            for m in s.get("members", []) or []:
                t = m.get("t") or m.get("ticker")
                if t:
                    self._rot_by_ticker.setdefault(t.upper(), []).append(s)

    def _index_baskets(self, data: dict) -> None:
        for b in data.get("baskets", []) or []:
            bid = b.get("id")
            for m in b.get("members", []) or []:
                sym = m.get("symbol") or m.get("ticker")
                if sym and bid:
                    self._basket_by_ticker.setdefault(sym.upper(), []).append(bid)
        ti = data.get("theme_intel") or {}
        for th in (ti.get("themes") or []):
            tid = th.get("id")
            if tid:
                self._theme_by_basket[tid] = th

    # ---- passport --------------------------------------------------------- #
    def source_passport(self) -> dict:
        """One record per source: found / degraded / stale + age. For the board's
        rotation-artifact coverage report and the per-lane passport summary."""
        out = {}
        for key, src in self._sources.items():
            out[key] = {
                "found": src.data is not None,
                "degraded": bool(src.degraded),
                "reason": src.error,
                "as_of": src.as_of,
                "age_days": src.age_days,
                "stale": bool(src.age_days is not None and src.age_days > self.STALE_DAYS),
            }
        return out

    def contract_version(self) -> int:
        return int(READER_CONTRACT["version"])

    # ---- per-name resolution --------------------------------------------- #
    def for_name(self, ticker: str, sector: str | None = None) -> dict:
        """Resolve rotation context for one name.

        Returns a dict:
          leadership : float in [-1, +1]  (0 = neutral / no coverage)
          chips      : list[{label, tone}]  display chips (running, leading, entry-now, ...)
          surfaced_by: list[str]   which rotation surface flagged this name
          components : dict         per-source signed contributions (audit)
          passport   : {frame, freshness, degraded, coverage}  honesty metadata
        Every path degrades to neutral rather than raising.
        """
        tkr = (ticker or "").upper()
        comps: dict[str, float | None] = {}
        weights: dict[str, float] = {}
        chips: list[dict] = []
        surfaced: list[str] = []
        degraded_sources: list[str] = []
        covered = 0

        specs = READER_CONTRACT["sources"]

        # 1) SECTOR CENTRAL — always-present backbone (join on GICS sector name)
        sc = self._sources.get("sector_central")
        sec_row = None
        if sc and not sc.degraded:
            sec_row = self._sector_by_name.get(_norm_sector(sector))
        if sec_row is not None:
            score = _clip_score((sec_row.get("conviction") or {}).get("score"), 0, 100)
            trend_pass = bool((sec_row.get("forward") or {}).get("trend_pass"))
            # conviction 0..100 → -1..+1, nudged by the forward trend gate
            contrib = (score - 50) / 50.0 if score is not None else 0.0
            if not trend_pass:
                contrib = min(contrib, 0.0) - 0.15   # a closed sector trend-gate is a drag
            comps["sector_central"] = round(contrib, 3)
            weights["sector_central"] = specs["sector_central"]["weight"]
            covered += 1
            label = (sec_row.get("conviction") or {}).get("label_en") or "Sector"
            chips.append({"label": f"Sector: {label}",
                          "tone": _tone(contrib), "src": "sector_central"})
        elif sc and sc.degraded:
            degraded_sources.append("sector_central")

        # 2) SUBSECTOR CONFLUENCE — class + entry tier + regime state (join on ticker)
        sub_row = _best_subsector(self._sub_by_ticker.get(tkr))
        sub_key = None
        conf_src = self._sources.get("subsector_confluence")
        if sub_row is not None:
            sub_key = sub_row.get("key")
            cls = sub_row.get("class")
            reg = ((sub_row.get("regime") or {}).get("state") or "").upper()
            contrib = _CLASS_SCORE.get(cls, 0.0) + _REGIME_TILT.get(reg, 0.0)
            contrib = max(-1.0, min(1.0, contrib))
            comps["subsector_confluence"] = round(contrib, 3)
            weights["subsector_confluence"] = specs["subsector_confluence"]["weight"]
            covered += 1
            if cls == "entry_now":
                chips.append({"label": f"Subsector ENTRY-NOW: {sub_row.get('label')}",
                              "tone": "pos", "src": "subsectors"})
                surfaced.append(f"subsectors:entry_now:{sub_row.get('label')}")
            elif cls == "headwind":
                chips.append({"label": f"Subsector headwind: {sub_row.get('label')}",
                              "tone": "neg", "src": "subsectors"})
        elif conf_src and conf_src.degraded:
            degraded_sources.append("subsector_confluence")

        # 3) INDEX LEADERSHIP — LAS Running / Coiling (join subsector key)
        lead_src = self._sources.get("index_leadership")
        if sub_key and lead_src and not lead_src.degraded:
            lead = self._subkey_lead.get(sub_key)
            if lead:
                if lead.get("running"):
                    comps["index_leadership"] = 0.7
                    weights["index_leadership"] = specs["index_leadership"]["weight"]
                    covered += 1
                    chips.append({"label": "LAS Running", "tone": "pos",
                                  "src": "subsectors_lead"})
                    surfaced.append(f"subsectors_running:{sub_key}")
                elif lead.get("coiling"):
                    comps["index_leadership"] = 0.3
                    weights["index_leadership"] = specs["index_leadership"]["weight"]
                    covered += 1
                    chips.append({"label": "LAS Coiling", "tone": "warm",
                                  "src": "subsectors_lead"})
                    surfaced.append(f"subsectors_coiling:{sub_key}")
        elif lead_src and lead_src.degraded:
            degraded_sources.append("index_leadership")

        # 4) SUBSECTOR ROTATION (RRG) — quadrant + rs_mom (join on ticker)
        rot_row = _best_rotation(self._rot_by_ticker.get(tkr))
        rot_src = self._sources.get("subsector_rotation")
        if rot_row is not None:
            quad = (rot_row.get("quadrant") or "").lower()
            contrib = _QUADRANT_SCORE.get(quad, 0.0)
            # rs_mom sign refines a borderline quadrant
            rs_mom = rot_row.get("rs_mom")
            if isinstance(rs_mom, (int, float)) and abs(contrib) < 0.5:
                contrib += 0.1 if rs_mom > 0 else -0.1
            contrib = max(-1.0, min(1.0, contrib))
            comps["subsector_rotation"] = round(contrib, 3)
            weights["subsector_rotation"] = specs["subsector_rotation"]["weight"]
            covered += 1
            if quad in ("leading", "improving"):
                chips.append({"label": f"RRG {quad.title()}", "tone": "pos",
                              "src": "rotation"})
                if quad == "leading":
                    surfaced.append(f"rotation_leading:{rot_row.get('key')}")
            elif quad in ("lagging", "weakening"):
                chips.append({"label": f"RRG {quad.title()}", "tone": "neg",
                              "src": "rotation"})
        elif rot_src and rot_src.degraded:
            degraded_sources.append("subsector_rotation")

        # 5) BASKETS / THEMES — theme leadership (join on ticker → basket → theme)
        bk_src = self._sources.get("baskets")
        basket_ids = self._basket_by_ticker.get(tkr) or []
        if basket_ids and bk_src and not bk_src.degraded:
            best_theme, best_score = None, None
            for bid in basket_ids:
                th = self._theme_by_basket.get(bid)
                if th and isinstance(th.get("score"), (int, float)):
                    if best_score is None or th["score"] > best_score:
                        best_score, best_theme = th["score"], th
            if best_theme is not None:
                contrib = (best_score - 50) / 50.0
                comps["baskets"] = round(max(-1.0, min(1.0, contrib)), 3)
                weights["baskets"] = specs["baskets"]["weight"]
                covered += 1
                lbl = best_theme.get("label_en") or best_theme.get("label") or "theme"
                chips.append({"label": f"Theme: {lbl}", "tone": _tone(contrib),
                              "src": "baskets"})
                if (best_theme.get("reco_en") or best_theme.get("reco") or "").lower() in (
                        "buy", "accumulate", "add"):
                    surfaced.append(f"baskets_buy:{best_theme.get('id')}")
            elif basket_ids:
                # in a basket but the theme desk had no read → mild membership credit
                comps["baskets"] = 0.0
                weights["baskets"] = specs["baskets"]["weight"]
                covered += 1
        elif bk_src and bk_src.degraded:
            degraded_sources.append("baskets")

        # ---- fuse (weighted mean of PRESENT sources; absent = not diluted) ---
        leadership = _weighted_mean(comps, weights)

        # de-dup chips/surfaced while preserving order
        chips = _dedup(chips, key=lambda c: (c["label"], c["tone"]))
        surfaced = list(dict.fromkeys(surfaced))

        # freshest as_of across the sources that actually contributed
        contrib_ages = [self._sources[k].age_days for k in comps
                        if self._sources.get(k) and self._sources[k].age_days is not None]
        freshness = max(contrib_ages) if contrib_ages else None

        passport = {
            "basis": "rotation-artifacts",
            "frame": "group",
            "freshness": freshness,           # calendar days of the oldest contributing source
            "n": covered,                     # how many of the 5 sources covered this name
            "coverage": round(covered / 5.0, 2),
            "degraded": degraded_sources,     # sources that were missing/stale for THIS build
            "contract_version": READER_CONTRACT["version"],
        }
        return {
            "leadership": round(leadership, 3),
            "state": _state_word(leadership),
            "chips": chips,
            "surfaced_by": surfaced,
            "components": comps,
            "passport": passport,
        }


# --------------------------------------------------------------------------- #
#  helpers                                                                      #
# --------------------------------------------------------------------------- #
def _clip_score(v: Any, lo: float, hi: float) -> float | None:
    if not isinstance(v, (int, float)):
        return None
    return max(lo, min(hi, float(v)))


def _weighted_mean(comps: dict[str, float | None], weights: dict[str, float]) -> float:
    num = den = 0.0
    for k, v in comps.items():
        if v is None:
            continue
        w = weights.get(k, 0.0)
        num += w * v
        den += w
    if den <= 0:
        return 0.0
    return max(-1.0, min(1.0, num / den))


def _tone(contrib: float) -> str:
    if contrib >= 0.25:
        return "pos"
    if contrib <= -0.25:
        return "neg"
    return "neutral"


def _state_word(x: float) -> str:
    if x >= 0.45:
        return "leading"
    if x >= 0.15:
        return "improving"
    if x <= -0.45:
        return "washed_out"
    if x <= -0.15:
        return "lagging"
    return "neutral"


def _best_subsector(rows: list[dict] | None) -> dict | None:
    """A name can belong to several sub-industries; prefer the strongest class."""
    if not rows:
        return None
    order = {"entry_now": 0, "forming": 1, "headwind": 3}
    return sorted(rows, key=lambda s: order.get(s.get("class"), 2))[0]


def _best_rotation(rows: list[dict] | None) -> dict | None:
    if not rows:
        return None
    order = {"leading": 0, "improving": 1, "weakening": 2, "lagging": 3}
    return sorted(rows, key=lambda s: order.get((s.get("quadrant") or "").lower(), 2))[0]


def _dedup(items: list, key) -> list:
    seen, out = set(), []
    for it in items:
        k = key(it)
        if k not in seen:
            seen.add(k)
            out.append(it)
    return out


__all__ = ["GroupContext", "READER_CONTRACT"]
