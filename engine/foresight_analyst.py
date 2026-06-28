"""Foresight analyst — the LLM reasoning layer over the convergence "neural web"
(research/THEMATIC_FORESIGHT_INSTITUTIONAL_UPGRADE.md §4/§5).

WHAT IT IS (and is NOT). The deterministic stack already finds WHERE independent leading
surfaces converge early (engine/foresight_convergence). This layer hands that board, plus the
raw per-theme evidence, to Claude and asks the judgement a transparent score cannot make:
WHY are these particular independent surfaces aligning, what is the NON-OBVIOUS cross-surface
pattern a human would miss in the noise, and what concrete observation would KILL the thesis.

It is an EXTRACTOR + JUDGE, never an oracle. Code-enforced honesty (the house contract):
  - It reasons ONLY from the evidence pack; it cites the surface behind every claim.
  - It is FORBIDDEN to forecast a price, a return %, or a directional bet — a deterministic
    linter strips any thesis that does (the model adds reasoning, never a number).
  - Every thesis is logged with the deterministic HEAT it was built on, so engine/thesis_monitor
    can fire "THESIS BROKEN" the moment that convergence decays — fully reproducible.
  - No credential -> graceful no-op (returns None), exactly like engine/altdata_brain. The
    desk is fully functional with the LLM disabled.

Reuses engine.altdata_brain's Anthropic client (OAuth token -> API key -> None). DISPLAY-ONLY.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone

from lib import config

log = logging.getLogger(__name__)

MAX_ITEMS = 8                      # bound the daily call (cost) — the top convergences only
LEDGER = ("data", "foresight", "analyst_theses.jsonl")
# language that would make a claim a price/return FORECAST — the no-forecast guardrail
_FORECAST_RE = re.compile(
    r"(price target|\bPT\b|will (?:rise|fall|go|reach|hit|double|triple)|%\s*(?:up|down|gain|return|upside|downside)"
    r"|\bupside\b|\bdownside\b|\$\d|\d+\s*%|expect[a-z]* (?:a )?(?:return|gain|move)|target of)", re.I)


def _cfg() -> dict:
    base = {
        "oauth_token_env": "CLAUDE_CODE_OAUTH_TOKEN",
        "api_key_env": "ANTHROPIC_API_KEY",
        "models": {"reasoning": "claude-opus-4-8"},
        "max_tokens": 6000,
    }
    try:
        return {**base, **(config.load().get("foresight_analyst") or {})}
    except Exception:  # noqa: BLE001
        return base


_SYSTEM = (
    "You are the lead analyst of a THEMATIC FORESIGHT desk. You are handed the desk's OWN "
    "deterministic CONVERGENCE board: per theme, which INDEPENDENT LEADING surfaces are lit "
    "(physical bottleneck, customer capex, management guidance, insider-cluster/award accel, "
    "subsector scarcity, small-cap discovery echo), a HEAT score, an EARLINESS (how un-priced "
    "the analyst revisions still are), the stage, and the raw evidence behind each surface.\n\n"
    "Your job: for the themes where independent surfaces genuinely ALIGN while still EARLY, "
    "explain the MECHANISM (why these particular surfaces are lining up), and name the "
    "NON-OBVIOUS cross-surface pattern a human would miss in the noise (e.g. an insider cluster "
    "AND a subsector-scarcity read AND flat revisions = supply tightening before the street "
    "models it). Omit themes where the evidence does not cohere — honesty over content.\n\n"
    "EXTRACTOR + JUDGE, NOT ORACLE — hard rules:\n"
    "- Reason ONLY from the evidence pack. NEVER fabricate a number, level, or event. Cite the "
    "surface behind every claim (e.g. [physical], [guidance], [subsector_scarcity]).\n"
    "- FORBIDDEN: a price target, a return %, a directional price bet, or any '$' / '%' figure. "
    "You describe DURABILITY and EARLINESS, never a forecast. A thesis with a number is rejected.\n"
    "- Convergence is UNUSUAL ALIGNMENT, not proven edge. A single surface is not a thesis.\n"
    "- Pre-register KILL-CRITERIA in terms of the desk's OWN legs (e.g. 'bottleneck loosens to "
    "NEUTRAL', 'guidance turns to cuts', 'insider cluster reverses', 'revisions broaden then "
    "roll over') — concrete, observable, machine-checkable conditions that would prove it wrong.\n"
    "- If a track record is present, CALIBRATE down on tiny samples.\n\n"
    "Return ONLY a JSON object (no markdown fences) with keys:\n"
    "  regime_read: string — one or two sentences on what the convergence picture shows today.\n"
    "  regime_read_zh: string — the same in 简体中文.\n"
    "  theses: array of 0..N objects, each:\n"
    "     theme: string — the theme key from the pack.\n"
    "     mechanism: string — WHY these independent surfaces are aligning (no numbers).\n"
    "     non_obvious: string — the cross-surface pattern that is hard to see in the noise.\n"
    "     kill_criteria: array of strings — concrete conditions (desk legs) that would prove it wrong.\n"
    "     evidence: array of strings — the specific surfaces cited.\n"
    "     dissent: string — the single strongest contrary case.\n"
    "     confidence: one of \"low\",\"medium\",\"high\" (be modest; default low).\n"
    "  confidence: one of \"low\",\"medium\",\"high\"."
)


def _evidence_pack(convergence: dict, cascade: dict | None) -> list[dict]:
    """Deterministic PIT evidence pack from the convergence board + the matching cascade legs.
    The top MAX_ITEMS by heat, each with its lit surfaces and the raw leg reads."""
    rows = {r.get("theme"): r for r in (cascade or {}).get("themes", [])}
    pack = []
    for it in (convergence.get("ranked") or [])[:MAX_ITEMS]:
        r = rows.get(it.get("theme")) or {}
        pack.append({
            "theme": it.get("theme"),
            "name": it.get("name"),
            "stage": it.get("stage"),
            "heat": it.get("heat"),
            "earliness": it.get("earliness"),
            "n_surfaces": it.get("n_signals"),
            "surfaces_lit": it.get("signals"),
            "physical_confirmed": it.get("physical_confirmed"),
            "evidence": {
                "bottleneck_band": r.get("bottleneck_band"),
                "demand_band": r.get("demand_band"),
                "guidance_band": r.get("guidance_band"),
                "guidance_raisers": r.get("guidance_raisers"),
                "altdata": r.get("altdata_summary"),
                "altdata_members": r.get("altdata_members"),
                "revision_breadth": r.get("revision_breadth"),
                "cross_surface": it.get("cross_surface"),
                "rationale": r.get("rationale"),
            },
        })
    return pack


def _strip_fence(text: str) -> str:
    t = (text or "").strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\n?", "", t)
        t = re.sub(r"\n?```$", "", t)
    return t.strip()


def _has_forecast(thesis: dict) -> bool:
    """True if any reasoning field smells like a price/return forecast (no-forecast guardrail)."""
    for f in ("mechanism", "non_obvious", "dissent"):
        if _FORECAST_RE.search(str(thesis.get(f) or "")):
            return True
    return False


def _parse(text: str, valid_themes: set[str]) -> dict | None:
    try:
        obj = json.loads(_strip_fence(text))
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(obj, dict):
        return None
    theses = []
    for th in (obj.get("theses") or []):
        if not isinstance(th, dict) or th.get("theme") not in valid_themes:
            continue
        if not th.get("mechanism") or not th.get("kill_criteria"):
            continue
        if _has_forecast(th):                       # no-forecast guardrail: drop, don't display
            log.info("foresight_analyst: dropped a thesis with forecast language (%s)", th.get("theme"))
            continue
        if th.get("confidence") not in ("low", "medium", "high"):
            th["confidence"] = "low"
        theses.append({k: th.get(k) for k in
                       ("theme", "mechanism", "non_obvious", "kill_criteria", "evidence", "dissent", "confidence")})
    return {"regime_read": obj.get("regime_read"), "regime_read_zh": obj.get("regime_read_zh"),
            "theses": theses, "confidence": obj.get("confidence") or "low"}


def compute_foresight_analyst(convergence: dict | None, cascade: dict | None = None,
                              call=None, write_ledger: bool = True) -> dict | None:
    """LLM synthesis over the convergence board. `call(system, user) -> (text, degraded)` is
    injectable (tests); defaults to the real Anthropic client. Returns None with no credential,
    no convergence, or an unparseable reply — the desk runs unchanged without it."""
    if not convergence or not convergence.get("ranked"):
        return None
    if call is None:
        try:
            from engine.altdata_brain import _make_call
            call = _make_call(_cfg())
        except Exception as e:  # noqa: BLE001
            log.warning("foresight_analyst: client init failed: %s", e)
            call = None
    if call is None:
        return None                                 # graceful no-op (no token) — house pattern

    pack = _evidence_pack(convergence, cascade)
    if not pack:
        return None
    valid = {p["theme"] for p in pack}
    user = ("EVIDENCE PACK (the desk's deterministic convergence board + raw legs):\n"
            + json.dumps(pack, separators=(",", ":"), default=str))
    text, degraded = call(_SYSTEM, user)
    if not text:
        log.info("foresight_analyst: no usable reply (%s)", degraded)
        return None
    out = _parse(text, valid)
    if out is None:
        return None
    out["asof"] = convergence.get("asof")
    out["n_theses"] = len(out["theses"])
    out["disclaimer"] = ("An AI reading of the desk's OWN deterministic convergence — "
                         "falsifiable and forward-graded, never a price forecast.")
    if write_ledger:
        try:
            _append_ledger(out, convergence)
        except Exception as e:  # noqa: BLE001
            log.warning("foresight_analyst ledger append failed: %s", e)
    return out


def _append_ledger(out: dict, convergence: dict) -> None:
    """Append each thesis with the deterministic HEAT it was built on, so thesis_monitor can
    fire when that convergence decays. Deduped by (theme, asof)."""
    d = config.data_dir() / "foresight"
    d.mkdir(parents=True, exist_ok=True)
    p = d / "analyst_theses.jsonl"
    seen = set()
    if p.exists():
        for line in p.read_text().splitlines():
            try:
                e = json.loads(line)
                seen.add((e.get("theme"), e.get("asof")))
            except Exception:  # noqa: BLE001
                continue
    heat = {it.get("theme"): it for it in (convergence.get("ranked") or [])}
    ts = datetime.now(timezone.utc).isoformat()
    asof = out.get("asof")
    lines = []
    for th in out["theses"]:
        tkey = th.get("theme")
        if (tkey, asof) in seen:
            continue
        h = heat.get(tkey) or {}
        lines.append(json.dumps({
            "theme": tkey, "asof": asof, "ts": ts, "confidence": th.get("confidence"),
            "kill_criteria": th.get("kill_criteria"),
            "heat_at_open": h.get("heat"), "physical_at_open": h.get("physical_confirmed"),
            "n_surfaces_at_open": h.get("n_signals"),
        }, separators=(",", ":")))
    if lines:
        with p.open("a") as fh:
            fh.write("\n".join(lines) + "\n")
