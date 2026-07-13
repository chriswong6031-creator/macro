"""engine.metabolism.attention — Discretionary attention allocation (V9 Layer 2).

Stateless Opus pass: reads criticality evidence + optional LLM call → assigns
each lobe an attention band (FOCUS/STANDARD/MAINTENANCE/DORMANT) with guardrails.

INERTNESS GUARANTEE:
    Writes data/metabolism/attention_allocation.json (display-tier artifact) and
    appends one line to data/metabolism/attention_history.jsonl.
    Dispatches NOTHING, grants NOTHING, opens NO PR, touches NO lobe roster.
    Does NOT touch any market-facing surface.

SCHEMA: metabolism.attention.v1

GUARDRAILS (enforced in code, post-LLM):
    G1 — structural CRITICAL may never sit below STANDARD; HIGH may never be DORMANT.
    G2 — at most max_focus_lobes in FOCUS (structural priority order + alpha for ties).
    G3 — urgent-fix supremacy: DORMANT lobe with high/critical insight row is exempted.
    G4 — no provider/parse failure → pure structural mapping + degraded_reason.
    G5 — docket_share scales resources DOWN only; never raises past budget caps.

NEVER-RAISE CONTRACT: every public function catches all exceptions, logs, returns safe fallback.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from math import floor
from pathlib import Path
from typing import Any

from engine.metabolism.criticality import (  # noqa: PLC2403
    AUTHORITY_BLOCK,
    build_criticality,
    load_criticality,
)

log = logging.getLogger(__name__)

SCHEMA = "metabolism.attention.v1"
BANDS = ("FOCUS", "STANDARD", "MAINTENANCE", "DORMANT")

BAND_WEIGHT: dict[str, float] = {
    "FOCUS": 1.0,
    "STANDARD": 0.6,
    "MAINTENANCE": 0.2,
    "DORMANT": 0.0,
}

# Structural band → default attention band mapping (G4 pure-structural degraded path)
STRUCTURAL_TO_BAND: dict[str, str] = {
    "CRITICAL": "FOCUS",
    "HIGH": "STANDARD",
    "STANDARD": "STANDARD",
    "ANCILLARY": "MAINTENANCE",
}

# Structural band ordinal for G2 sort (lower = higher priority)
_STRUCTURAL_ORDER: dict[str, int] = {
    "CRITICAL": 0,
    "HIGH": 1,
    "STANDARD": 2,
    "ANCILLARY": 3,
}

ALLOCATION_PATH = Path("data") / "metabolism" / "attention_allocation.json"
HISTORY_PATH = Path("data") / "metabolism" / "attention_history.jsonl"

# Default attention config (used when file is absent/unreadable)
_DEFAULT_CONFIG: dict[str, Any] = {
    "max_focus_lobes": 8,
    "docket_share": {
        "FOCUS": 1.0,
        "STANDARD": 0.6,
        "MAINTENANCE": 0.2,
        "DORMANT": 0.0,
    },
    "dispatch_priority": {
        "FOCUS": 0,
        "STANDARD": 1,
        "MAINTENANCE": 2,
        "DORMANT": 3,
    },
}


def _repo_root(root: Path | None = None) -> Path:
    if root is not None:
        return Path(root)
    return Path(__file__).resolve().parent.parent.parent


def _now_date() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _now_ts() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ── Config loader ─────────────────────────────────────────────────────────────

def load_attention_config(root: Path | None = None) -> dict:
    """Read config/metabolism_attention.yml.

    Returns hardcoded defaults on any error. NEVER raises.
    """
    try:
        import yaml  # noqa: PLC0415
        repo = _repo_root(root)
        p = repo / "config" / "metabolism_attention.yml"
        data = yaml.safe_load(p.read_text(encoding="utf-8"))
        if not data:
            return _DEFAULT_CONFIG.copy()
        cfg: dict[str, Any] = {
            "max_focus_lobes": int(data.get("max_focus_lobes") or _DEFAULT_CONFIG["max_focus_lobes"]),
            "docket_share": dict(data.get("docket_share") or _DEFAULT_CONFIG["docket_share"]),
            "dispatch_priority": dict(data.get("dispatch_priority") or _DEFAULT_CONFIG["dispatch_priority"]),
        }
        return cfg
    except Exception as exc:  # noqa: BLE001
        log.warning("attention.load_attention_config: %s — using defaults", exc)
        return _DEFAULT_CONFIG.copy()


# ── LLM call ─────────────────────────────────────────────────────────────────

def _call_llm(
    providers: list[dict],
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = 4000,
) -> tuple[str | None, str | None, str | None]:
    """Call the LLM via llm_auth.make_call.

    Returns (text, degraded_reason, provider_used). NEVER raises.
    """
    try:
        from engine.llm_auth import make_call  # noqa: PLC0415

        def _call_fn(client: Any, model: str) -> tuple[str | None, str | None]:
            resp = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )
            text = resp.content[0].text if resp.content else None
            return text, None

        return make_call(providers, _call_fn, context="metabolism_attention")
    except Exception as exc:  # noqa: BLE001
        log.warning("attention._call_llm: failed — %s", exc)
        return None, f"llm_error: {exc}", None


def _parse_deviations(text: str | None) -> tuple[dict[str, dict], str | None]:
    """Parse LLM output into deviation map.

    Returns (deviations, degraded_reason). On bad parse returns ({}, reason).
    NEVER raises.
    """
    if not text:
        return {}, "empty_llm_response"
    try:
        import re  # noqa: PLC0415
        stripped = re.sub(r"```[a-z]*\n?", "", text).strip()
        data = json.loads(stripped)
        devs = data.get("deviations") or {}
        if not isinstance(devs, dict):
            return {}, "deviations_not_dict"
        return devs, None
    except Exception as exc:  # noqa: BLE001
        log.warning("attention._parse_deviations: JSON parse failed — %s", exc)
        return {}, f"parse_error: {exc}"


# ── Attention builder ─────────────────────────────────────────────────────────

def build_attention(
    cycle_id: str,
    root: Path | None = None,
    providers: list[dict] | None = None,
    model: str | None = None,
) -> dict:
    """Build the attention allocation artifact.

    NEVER raises.
    """
    try:
        return _build_attention_inner(
            cycle_id=cycle_id,
            root=root,
            providers=providers,
            model=model,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("attention.build_attention: fatal — %s", exc)
        return {
            "schema": SCHEMA,
            "cycle_id": cycle_id,
            "as_of": _now_date(),
            "generated_by": "metabolism_attention",
            "provider": None,
            "degraded_reason": f"fatal error: {exc}",
            "allocations": {},
            "focus_lobes": [],
            "authority": AUTHORITY_BLOCK,
        }


def _build_attention_inner(
    cycle_id: str,
    root: Path | None,
    providers: list[dict] | None,
    model: str | None,
) -> dict:
    """Inner builder — may raise; wrapped by build_attention."""
    repo = _repo_root(root)
    cfg = load_attention_config(root=repo)
    max_focus_lobes: int = cfg["max_focus_lobes"]
    docket_share: dict[str, float] = cfg["docket_share"]

    # 1. Load criticality (build on the fly if file absent)
    crit = load_criticality(root=repo)
    if not crit or not crit.get("lobes"):
        log.info("attention: criticality file absent — building on the fly")
        crit = build_criticality(root=repo, write=False)

    lobe_profiles: dict[str, dict] = crit.get("lobes") or {}

    # 2. Baseline allocation = STRUCTURAL_TO_BAND applied to every lobe
    baseline: dict[str, str] = {}
    for lobe_id, profile in lobe_profiles.items():
        sband = profile.get("structural_band") or "ANCILLARY"
        baseline[lobe_id] = STRUCTURAL_TO_BAND.get(sband, "MAINTENANCE")

    # 3. Optional LLM call for deviations
    provider_used: str | None = None
    degraded_reason: str | None = None
    deviations: dict[str, dict] = {}

    if providers:
        try:
            from engine.metabolism.orchestrator_brain import _build_orchestrator_system  # noqa: PLC0415
            system_prompt = _build_orchestrator_system(
                model=model, role="attention", lobe=None, root=repo
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("attention: _build_orchestrator_system failed — %s", exc)
            system_prompt = "You are the Attention Allocator. Return only JSON deviations."

        # Build compact per-lobe criticality table (byte-capped ~8000)
        table_rows: list[dict] = []
        for lobe_id, profile in lobe_profiles.items():
            table_rows.append({
                "lobe_id": lobe_id,
                "structural_band": profile.get("structural_band"),
                "default_band": baseline.get(lobe_id),
                "nw_core": profile.get("nw_core", False),
                "nw_anchor": profile.get("nw_anchor", False),
                "nw_context": profile.get("nw_context", False),
                "market_data": profile.get("market_data", False),
                "fanout": profile.get("consumer_fanout", 0),
                "tier": profile.get("tier"),
                "lifecycle_state": profile.get("lifecycle_state"),
                "cadence": profile.get("cadence"),
            })
        table_json = json.dumps(table_rows, ensure_ascii=False)
        # Byte-cap at ~8000
        if len(table_json.encode()) > 8000:
            table_json = table_json[:8000] + "... [truncated]"

        user_prompt = (
            f"Lobe criticality evidence (compact table):\n{table_json}\n\n"
            "Return ONLY JSON {\"deviations\": {\"<lobe_id>\": {\"band\": "
            "\"FOCUS|STANDARD|MAINTENANCE|DORMANT\", \"rationale\": \"one line citing evidence\"}}} "
            "listing ONLY lobes whose band should DIFFER from the structural default shown; "
            "unlisted lobes keep the default. "
            "Focus = lobes most critical to Neural Web context/data and crucial engines; "
            "deprioritize ancillary low-frequency support."
        )

        text, llm_degraded, provider_used = _call_llm(
            providers=providers,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_tokens=4000,
        )
        if llm_degraded:
            degraded_reason = llm_degraded
        else:
            devs, parse_degraded = _parse_deviations(text)
            if parse_degraded:
                degraded_reason = parse_degraded
            else:
                deviations = devs
    else:
        degraded_reason = "no_provider"

    # 4. Apply deviations over baseline
    allocations: dict[str, dict] = {}
    for lobe_id, default_band in baseline.items():
        profile = lobe_profiles.get(lobe_id) or {}
        sband = profile.get("structural_band") or "ANCILLARY"

        if lobe_id in deviations:
            dev = deviations[lobe_id]
            proposed_band = str(dev.get("band") or "").upper()
            if proposed_band not in BANDS:
                # Unknown band from LLM → treat as no-deviation
                proposed_band = default_band
                llm_band: str | None = None
                rationale = ""
            else:
                llm_band = proposed_band
                rationale = str(dev.get("rationale") or "")
        else:
            proposed_band = default_band
            llm_band = None
            rationale = ""

        allocations[lobe_id] = {
            "band": proposed_band,
            "weight": BAND_WEIGHT.get(proposed_band, 0.6),
            "structural_band": sband,
            "llm_band": llm_band,
            "floored": False,
            "rationale": rationale,
        }

    # 5. GUARDRAILS
    # G1 — criticality floors
    for lobe_id, alloc in allocations.items():
        profile = lobe_profiles.get(lobe_id) or {}
        sband = profile.get("structural_band") or "ANCILLARY"
        band = alloc["band"]

        if sband == "CRITICAL" and band in ("MAINTENANCE", "DORMANT"):
            alloc["band"] = "STANDARD"
            alloc["weight"] = BAND_WEIGHT["STANDARD"]
            alloc["floored"] = True
        elif sband == "HIGH" and band == "DORMANT":
            alloc["band"] = "MAINTENANCE"
            alloc["weight"] = BAND_WEIGHT["MAINTENANCE"]
            alloc["floored"] = True

    # G2 — focus scarcity cap
    focus_lobes_list = [lid for lid, alloc in allocations.items() if alloc["band"] == "FOCUS"]
    if len(focus_lobes_list) > max_focus_lobes:
        # Sort by structural band priority (CRITICAL<HIGH<STANDARD<ANCILLARY), then lobe_id alpha
        def _focus_sort_key(lobe_id: str) -> tuple[int, str]:
            sband = (lobe_profiles.get(lobe_id) or {}).get("structural_band") or "ANCILLARY"
            return (_STRUCTURAL_ORDER.get(sband, 3), lobe_id)

        focus_lobes_list_sorted = sorted(focus_lobes_list, key=_focus_sort_key)
        keep = set(focus_lobes_list_sorted[:max_focus_lobes])
        demote = set(focus_lobes_list_sorted[max_focus_lobes:])
        for lobe_id in demote:
            alloc = allocations[lobe_id]
            alloc["band"] = "STANDARD"
            alloc["weight"] = BAND_WEIGHT["STANDARD"]
            alloc["floored"] = True
            if alloc["rationale"]:
                alloc["rationale"] += " [focus-cap demotion]"
            else:
                alloc["rationale"] = "[focus-cap demotion]"

    # Final weight pass — ensure band/weight are consistent after all guardrails
    for alloc in allocations.values():
        alloc["weight"] = BAND_WEIGHT.get(alloc["band"], 0.6)

    # Focus lobes sorted list (post-guardrails)
    focus_lobes_sorted = sorted(
        [lid for lid, alloc in allocations.items() if alloc["band"] == "FOCUS"]
    )

    # Counts by band
    counts_by_band: dict[str, int] = {b: 0 for b in BANDS}
    for alloc in allocations.values():
        counts_by_band[alloc["band"]] = counts_by_band.get(alloc["band"], 0) + 1

    artifact: dict[str, Any] = {
        "schema": SCHEMA,
        "cycle_id": cycle_id,
        "as_of": _now_date(),
        "generated_by": "metabolism_attention",
        "provider": provider_used,
        "degraded_reason": degraded_reason,
        "allocations": allocations,
        "focus_lobes": focus_lobes_sorted,
        "authority": AUTHORITY_BLOCK,
    }

    # 6. Write allocation artifact
    out_path = repo / ALLOCATION_PATH
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(artifact, indent=2, ensure_ascii=False), encoding="utf-8")
    log.info("attention: wrote %s (%d lobes)", out_path, len(allocations))

    # 7. Append history line
    history_line = json.dumps({
        "cycle_id": cycle_id,
        "as_of": _now_ts(),
        "focus_lobes": focus_lobes_sorted,
        "counts_by_band": counts_by_band,
        "degraded_reason": degraded_reason,
    }, ensure_ascii=False)
    hist_path = repo / HISTORY_PATH
    hist_path.parent.mkdir(parents=True, exist_ok=True)
    with hist_path.open("a", encoding="utf-8") as fh:
        fh.write(history_line + "\n")

    return artifact


# ── Read helpers ──────────────────────────────────────────────────────────────

def load_allocation(root: Path | None = None) -> dict:
    """Read the attention allocation artifact from disk.

    Returns {} on any error. NEVER raises.
    """
    try:
        repo = _repo_root(root)
        p = repo / ALLOCATION_PATH
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        log.debug("attention.load_allocation: %s", exc)
        return {}


def effective_allocation(cycle_id: str | None = None, root: Path | None = None) -> dict:
    """Return the allocation to act on, healing stage-local absence (R-V9-2).

    Stage artifacts travel on metabolism/* branches and never land on main, so
    a downstream stage's checkout (PROPOSE, BUILD) may lack the agenda-stage
    allocation file.  House pattern (stateless-cattle): rebuild sensors fresh
    in the stage workspace.  Loads the committed allocation when present;
    otherwise builds a STRUCTURAL-ONLY allocation here (providers=None — the
    LLM discretion layer runs in the AGENDA stage only; a stage-local rebuild
    never spends tokens).  The rebuilt artifact rides whatever branch the
    stage commits (or stays uncommitted in read-only lanes like the BUILD
    pick).  Returns {} only on total failure.  NEVER raises.
    """
    try:
        alloc = load_allocation(root=root)
        if (alloc or {}).get("allocations"):
            return alloc
        log.info(
            "attention.effective_allocation: no allocation in this workspace — "
            "rebuilding structural-only (stage-local heal)"
        )
        return build_attention(
            cycle_id=cycle_id or "stage-local",
            root=root,
            providers=None,
            model=None,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("attention.effective_allocation: %s — returning empty", exc)
        return {}


def band_for(lobe_id: str, allocation: dict | None = None, root: Path | None = None) -> str:
    """Return the attention band for a lobe.

    Returns "STANDARD" for unknown lobe or empty allocation. NEVER raises.
    """
    try:
        if allocation is None:
            allocation = load_allocation(root=root)
        allocs = (allocation or {}).get("allocations") or {}
        entry = allocs.get(lobe_id)
        if entry:
            b = entry.get("band")
            if b in BANDS:
                return b
        return "STANDARD"
    except Exception as exc:  # noqa: BLE001
        log.debug("attention.band_for: %s", exc)
        return "STANDARD"


def weight_for(lobe_id: str, allocation: dict | None = None, root: Path | None = None) -> float:
    """Return the attention weight for a lobe. NEVER raises."""
    try:
        b = band_for(lobe_id, allocation=allocation, root=root)
        return BAND_WEIGHT.get(b, 0.6)
    except Exception as exc:  # noqa: BLE001
        log.debug("attention.weight_for: %s", exc)
        return 0.6


def effective_docket_size(
    lobe_id: str,
    base_size: int,
    root: Path | None = None,
    allocation: dict | None = None,
) -> int:
    """Scale base_size by docket_share for the lobe's band.

    DORMANT → 0. Never exceeds base_size (G5). NEVER raises.
    """
    try:
        b = band_for(lobe_id, allocation=allocation, root=root)
        if b == "DORMANT":
            return 0
        cfg = load_attention_config(root=root)
        share = cfg["docket_share"].get(b, 0.6)
        scaled = floor(base_size * share)
        result = max(1, scaled)
        return min(result, base_size)
    except Exception as exc:  # noqa: BLE001
        log.debug("attention.effective_docket_size: %s", exc)
        return base_size


def propose_skip(
    lobe_id: str,
    root: Path | None = None,
    allocation: dict | None = None,
) -> tuple[bool, str]:
    """Return (skip, reason) for the PROPOSE stage.

    (False, "") when band != DORMANT.
    When DORMANT: checks G3 exemption (high/critical insight row targeting this lobe).
    Any error → (False, "attention_error") — fail open, never block work. NEVER raises.
    """
    try:
        b = band_for(lobe_id, allocation=allocation, root=root)
        if b != "DORMANT":
            return (False, "")

        # G3 — urgent-fix supremacy exemption check
        try:
            from engine.metabolism.insight_bus import get_open_rows  # noqa: PLC0415
            open_rows = get_open_rows(root=root)
            for row in open_rows:
                if row.get("severity") in ("high", "critical"):
                    entities = row.get("entities") or []
                    if lobe_id in entities:
                        return (False, "urgent_fix_exemption")
        except Exception as exc:  # noqa: BLE001
            log.warning("attention.propose_skip: insight_bus error (fail open) — %s", exc)
            return (False, "attention_error")

        return (True, "attention_dormant")
    except Exception as exc:  # noqa: BLE001
        log.warning("attention.propose_skip: error (fail open) — %s", exc)
        return (False, "attention_error")


def dispatch_priority(
    lobe_id: str,
    allocation: dict | None = None,
    root: Path | None = None,
) -> int:
    """Return the BUILD dispatch priority for a lobe.

    Default 1 (STANDARD). NEVER raises.
    """
    try:
        b = band_for(lobe_id, allocation=allocation, root=root)
        cfg = load_attention_config(root=root)
        return int(cfg["dispatch_priority"].get(b, 1))
    except Exception as exc:  # noqa: BLE001
        log.debug("attention.dispatch_priority: %s", exc)
        return 1


# ── R-V9-9: BUILD cycle selection ─────────────────────────────────────────────

_CYCLE_DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")


def _cycle_lobe(cycle_id: str, lobe_ids: list[str]) -> str:
    """Derive the lobe id from a per-lobe cycle_id suffix.

    ``--all-lobes`` PROPOSE gives the first lobe (til, backward-compat) the
    bare base cycle_id and every other lobe ``{base}-{lobe_id}``.  Longest
    suffix match wins so nested-hyphen lobe ids resolve correctly.
    """
    for lid in sorted(lobe_ids, key=len, reverse=True):
        if lid and cycle_id.endswith("-" + lid):
            return lid
    return "til"


def rank_cycle_ids(
    cycle_ids: list[str],
    root: Path | None = None,
    allocation: dict | None = None,
) -> list[str]:
    """Order candidate BUILD cycle_ids so higher-attention lobes dispatch first.

    The scheduled BUILD lane processes ONE docket per run; the choice among
    open ``metabolism/propose-*`` branches is the binding dispatch-scarcity
    point (R-V9-9).  Ranking (first element = the cycle to build):
      1. newest cycle DATE first — a stale FOCUS docket never shadows today's
         work (the lane is idempotent via journal claims, so an already-built
         cycle would waste the day's run as a no-op),
      2. attention dispatch priority within the same date (FOCUS first),
      3. lexicographic DESCENDING (the pre-V9 ``sort | tail -1`` tie-break).

    NEVER raises; on any failure returns plain lexicographic-descending order
    (exactly the pre-V9 pick). Never drops a candidate (R-V9-9 no-starvation).
    """
    try:
        ids = [str(c).strip() for c in cycle_ids if str(c).strip()]
        if not ids:
            return []
        # Stage-local heal (R-V9-2): the BUILD lane runs on a main checkout that
        # never carries the agenda-branch allocation — rebuild structural-only.
        alloc = allocation if allocation is not None else effective_allocation(root=root)
        try:
            from engine.metabolism import lobe_registry  # noqa: PLC0415
            lobe_ids = list(lobe_registry.load(root)["charters"].keys())
        except Exception as exc:  # noqa: BLE001
            log.debug("attention.rank_cycle_ids: charter load failed — %s", exc)
            lobe_ids = []

        def _date_key(cid: str) -> str:
            m = _CYCLE_DATE_RE.search(cid)
            return m.group(1) if m else ""

        # Stable multi-pass sort: last-applied key dominates.
        ranked = sorted(ids, reverse=True)  # 3. lexicographic desc
        ranked = sorted(
            ranked,
            key=lambda c: dispatch_priority(
                _cycle_lobe(c, lobe_ids), allocation=alloc, root=root
            ),
        )  # 2. attention priority
        ranked = sorted(ranked, key=_date_key, reverse=True)  # 1. newest date
        return ranked
    except Exception as exc:  # noqa: BLE001
        log.warning("attention.rank_cycle_ids: %s — lexicographic fallback", exc)
        try:
            return sorted([str(c).strip() for c in cycle_ids if str(c).strip()], reverse=True)
        except Exception:  # noqa: BLE001
            return []
