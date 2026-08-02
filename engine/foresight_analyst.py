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
    linter strips any thesis that violates this from the mechanism field ONLY (the one field
    that MUST be clean to have any thesis at all); violations in OTHER fields are CLAMPED
    (the offending fragment is replaced with "[forecast removed]") so the thesis is kept.
    See _clamp_forecast() and _clamp_all_fields().
  - CITATION GROUNDING (W4b): every evidence item is checked against the evidence pack that
    was fed to the model.  Items not found as substrings of the pack are tagged
    "ungrounded": true and excluded from display copy; kept in the ledger for audit.
    n_grounded/n_total are surfaced per thesis.
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

from engine.ledger_lane import nightly_advance_enabled as _ledger_advance_enabled
from lib import config

log = logging.getLogger(__name__)

MAX_ITEMS = 8                      # bound the daily call (cost) — the top convergences only
LEDGER = ("data", "foresight", "analyst_theses.jsonl")
# language that would make a claim a price/return FORECAST — the no-forecast guardrail
#
# REGEX NOTES (B1 fix):
#  - \$\s*\d[\d,.]* — matches "$120", "$ 1,200" etc. as a full NUMBER token (not "$1" of "$120")
#  - \d[\d,.]*\s*% — matches "20%", "1,200%" etc. as a full number-percent token
#  - reach\s+\d+ by — catches "reach 120 by Q4" style patterns
#  These replacements widen the match to the full number token, fixing the sub-fragment bug.
_FORECAST_RE = re.compile(
    r"(price target|\bPT\b|will (?:rise|fall|go|reach|hit|double|triple)"
    r"|%\s*(?:up|down|gain|return|upside|downside)"
    r"|\bupside\b|\bdownside\b"
    r"|\$\s*\d[\d,.]*"          # full $ number token — e.g. "$120" not just "$1" of "$120"
    r"|\d[\d,.]*\s*%"           # full %-number token — e.g. "20%" not "20" only
    r"|reach\s+\d[\d,.]*\s+by"  # "reach 120 by Q4" style
    r"|expect[a-z]* (?:a )?(?:return|gain|move)|target of)", re.I)

# Fields that can be CLAMPED (stripped) vs dropped — mechanism is the hard gate.
# NOTE (B1 fix): evidence and kill_criteria are NOT mutated in-place; instead items that
# match are tagged forecast_suspect=True and excluded from display.  Only free-prose
# fields (mechanism handled separately, non_obvious/dissent/regime_read*) are clamped.
_CLAMPABLE_PROSE_FIELDS = ("regime_read", "regime_read_zh", "dissent", "non_obvious")
# List fields that use forecast_suspect tagging (not in-place mutation)
_SUSPECT_LIST_FIELDS = ("kill_criteria", "evidence")
# All fields considered for clamping (union — for logging)
_CLAMPABLE_FIELDS = _CLAMPABLE_PROSE_FIELDS + _SUSPECT_LIST_FIELDS
# Fields that are lists of strings (need item-level handling)
_LIST_FIELDS = ("kill_criteria", "evidence")


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
    """True if the MECHANISM field smells like a price/return forecast.
    This is the HARD GATE — only mechanism is checked here; other fields are clamped."""
    return bool(_FORECAST_RE.search(str(thesis.get("mechanism") or "")))


def _clamp_string(s: str) -> tuple[str, list[str]]:
    """Strip forecast fragments from a free-prose string.
    Returns (clamped_str, [removed fragments]).
    Replaces the ENTIRE matched forecast phrase (the full regex group), never a sub-fragment."""
    removed: list[str] = []

    def _replace(m: re.Match) -> str:  # type: ignore[type-arg]
        removed.append(m.group(0))
        return "[forecast removed]"

    clamped = _FORECAST_RE.sub(_replace, s)
    return clamped, removed


def _clamp_all_fields(thesis: dict) -> tuple[dict, list[str]]:
    """Clamp forecast language from non-mechanism fields.  Returns (clamped_thesis, removed_fragments).

    B1 FIX — two-tier treatment:
      Free-prose fields (dissent, non_obvious, regime_read*): mutated in-place — the offending
        phrase is replaced with "[forecast removed]".
      List fields (evidence, kill_criteria): NOT mutated — items that match are tagged
        forecast_suspect=True (kept in ledger, excluded from display_copy); the list itself
        is preserved so grounding can check the ORIGINAL strings.

    The thesis is KEPT (not dropped) even when violations are found in these fields.
    """
    all_removed: list[str] = []
    clamped = dict(thesis)

    # Prose fields: in-place mutation safe (no grounding dependency)
    for field in _CLAMPABLE_PROSE_FIELDS:
        val = thesis.get(field)
        if val is None or not isinstance(val, str):
            continue
        c, rem = _clamp_string(val)
        clamped[field] = c
        all_removed.extend(rem)

    # List fields: tag forecast_suspect items; do NOT mutate the string
    for field in _SUSPECT_LIST_FIELDS:
        val = thesis.get(field)
        if val is None or not isinstance(val, list):
            continue
        new_list = []
        for item in val:
            if isinstance(item, str) and _FORECAST_RE.search(item):
                matched = _FORECAST_RE.findall(item)
                all_removed.extend(matched if isinstance(matched[0], str) else
                                   [m[0] if isinstance(m, tuple) else m for m in matched])
                log.info("foresight_analyst: forecast_suspect item in %s: %r", field, item[:80])
                new_list.append({"text": item, "forecast_suspect": True})
            else:
                new_list.append(item)
        clamped[field] = new_list

    return clamped, all_removed


def _build_pack_text(pack: list[dict]) -> str:
    """Flatten the evidence pack into a single normalised text for substring matching."""
    return " ".join(
        _normalise(str(v))
        for item in pack
        for v in _flatten_values(item)
        if v is not None
    )


def _flatten_values(obj: object, _depth: int = 0) -> list:
    """Recursively collect all leaf values from a dict/list."""
    if _depth > 6:
        return [str(obj)]
    if isinstance(obj, dict):
        result = []
        for v in obj.values():
            result.extend(_flatten_values(v, _depth + 1))
        return result
    if isinstance(obj, list):
        result = []
        for v in obj:
            result.extend(_flatten_values(v, _depth + 1))
        return result
    return [obj]


def _normalise(s: str) -> str:
    """Normalise for case-insensitive, whitespace-collapsed substring matching.

    B1b: unicode folding applied to BOTH sides (pack text and evidence item) before
    the substring check, so curly-quote variants in LLM output match ASCII pack text.
    """
    # Unicode typographic quote/dash folding
    s = s.replace("‘", "'").replace("’", "'")   # LEFT/RIGHT SINGLE QUOTATION MARK
    s = s.replace("“", '"').replace("”", '"')   # LEFT/RIGHT DOUBLE QUOTATION MARK
    s = s.replace("–", "-").replace("—", "-")   # EN DASH / EM DASH
    return re.sub(r"\s+", " ", s).strip().lower()


def _check_evidence_grounding(evidence_items: list, pack_text: str) -> tuple[list, int, int]:
    """Check each evidence item against the pack text.

    Returns (annotated_items, n_grounded, n_total).
    An item is 'grounded' if it (or a meaningful fragment of it) appears as a
    case-insensitive, whitespace-normalised substring of pack_text.
    Items that are too short (<4 chars) are accepted as trivially present.
    """
    annotated: list = []
    n_grounded = 0
    n_total = 0

    for item in evidence_items:
        if not isinstance(item, str):
            annotated.append(item)
            continue
        n_total += 1
        normalised = _normalise(item)
        if len(normalised) < 4:
            # Too short to meaningfully check — treat as grounded
            annotated.append(item)
            n_grounded += 1
            continue
        grounded = normalised in pack_text
        if grounded:
            annotated.append(item)
            n_grounded += 1
        else:
            # Tag as ungrounded — excluded from display, kept in ledger
            annotated.append({"text": item, "ungrounded": True})
            log.info("foresight_analyst: ungrounded evidence item in pack: %r", item[:80])

    return annotated, n_grounded, n_total


def _parse(text: str, valid_themes: set[str], pack: list[dict] | None = None) -> dict | None:
    """Parse and validate LLM reply.

    Changes vs pre-W4b:
    - Forecast filter now covers ALL output fields (not just mechanism/non_obvious/dissent):
      mechanism = hard drop gate; other fields = clamp and keep.
    - Citation grounding: evidence items checked against the pack text; ungrounded items
      tagged and excluded from display copy, kept in ledger.
    """
    try:
        obj = json.loads(_strip_fence(text))
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(obj, dict):
        return None

    # Build pack text for citation grounding
    pack_text = _build_pack_text(pack or [])

    # Clamp regime_read / regime_read_zh at top level
    regime_read = str(obj.get("regime_read") or "")
    regime_read_zh = str(obj.get("regime_read_zh") or "")
    regime_read, _ = _clamp_string(regime_read)
    regime_read_zh, _ = _clamp_string(regime_read_zh)

    theses = []
    for th in (obj.get("theses") or []):
        if not isinstance(th, dict) or th.get("theme") not in valid_themes:
            continue
        if not th.get("mechanism") or not th.get("kill_criteria"):
            continue

        # HARD GATE: mechanism contains a forecast -> drop the whole thesis
        if _has_forecast(th):
            log.info("foresight_analyst: dropped thesis (mechanism forecast): %s", th.get("theme"))
            continue

        # B1 FIX: CITATION GROUNDING runs FIRST, on the ORIGINAL (unclamped) strings.
        # This ensures clamping cannot corrupt evidence strings before the grounding check.
        raw_evidence = (th.get("evidence") or [])
        # Only pass plain strings to grounding — skip any dicts already in the list
        plain_evidence = [e for e in raw_evidence if isinstance(e, str)]
        annotated_evidence, n_grounded, n_total = _check_evidence_grounding(
            plain_evidence, pack_text
        )

        # Now CLAMP other fields (prose fields mutated; list fields tagged forecast_suspect)
        # We work on a copy that already has grounded evidence annotations in place.
        th_with_grounded = {**th, "evidence": annotated_evidence}
        clamped, removed = _clamp_all_fields(th_with_grounded)
        if removed:
            log.info("foresight_analyst: clamped forecast language from %s in %s: %r",
                     list(set(
                         f for f in _CLAMPABLE_FIELDS
                         if any(r in str(th.get(f) or "") for r in removed)
                     )),
                     th.get("theme"), removed)
            clamped["_forecast_clamped"] = removed  # kept in ledger, not displayed

        # After clamp, the evidence list may contain grounding dicts AND forecast_suspect dicts.
        # Build display-only evidence: exclude items tagged ungrounded or forecast_suspect.
        final_evidence = clamped.get("evidence") or []
        clamped["n_grounded"] = n_grounded
        clamped["n_total_evidence"] = n_total
        clamped["evidence_display"] = [
            e for e in final_evidence
            if isinstance(e, str)  # dicts are either ungrounded or forecast_suspect — exclude both
        ]

        if clamped.get("confidence") not in ("low", "medium", "high"):
            clamped["confidence"] = "low"

        theses.append({k: clamped.get(k) for k in (
            "theme", "mechanism", "non_obvious", "kill_criteria", "evidence",
            "evidence_display", "dissent", "confidence",
            "n_grounded", "n_total_evidence", "_forecast_clamped",
        )})

    return {
        "regime_read": regime_read,
        "regime_read_zh": regime_read_zh,
        "theses": theses,
        "confidence": obj.get("confidence") or "low",
    }


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
    out = _parse(text, valid, pack=pack)
    if out is None:
        return None
    out["asof"] = convergence.get("asof")
    out["n_theses"] = len(out["theses"])
    out["disclaimer"] = ("An AI reading of the desk's OWN deterministic convergence — "
                         "checkable and forward-graded, never a price forecast.")
    if write_ledger:
        try:
            _append_ledger(out, convergence)
        except Exception as e:  # noqa: BLE001
            log.warning("foresight_analyst ledger append failed: %s", e)
    return out


def load_committed_theses() -> dict | None:
    """Read-only replay of the LAST COMMITTED analyst theses — zero LLM, zero network.

    Used by the express re-render lanes (RENDER_NO_DRIP=1), which carry a model
    credential but must not spend a call per bake.  Returns the same shape the
    foresight template consumes, assembled STRICTLY from committed ledger rows:
    one entry per theme, the most recent `asof` wins.

    The ledger stores `confidence` and `kill_criteria` but NOT the model's prose
    (`mechanism`, `non_obvious`, `regime_read`), so those are read opportunistically
    and left falsy when absent — the template already guards each one.  `regime_read`
    is a builder-authored disclosure line, not model output: it exists so the section
    renders at all (the template gates on it) and it says plainly that this is the
    last saved read.  Nothing here originates or escalates a signal.

    Returns None when the ledger is absent or carries no usable rows.
    """
    p = config.data_dir() / "foresight" / "analyst_theses.jsonl"
    if not p.exists():
        return None
    latest: dict[str, dict] = {}
    for line in p.read_text().splitlines():
        if not line.strip():
            continue
        try:
            e = json.loads(line)
        except Exception:  # noqa: BLE001
            continue
        t = e.get("theme")
        if not t:
            continue
        if t not in latest or str(e.get("asof")) > str(latest[t].get("asof")):
            latest[t] = e
    if not latest:
        return None

    rows = sorted(latest.values(), key=lambda e: str(e.get("asof")), reverse=True)
    theses = [{
        "theme": e.get("theme"),
        "mechanism": e.get("mechanism") or "",
        "non_obvious": e.get("non_obvious") or "",
        "kill_criteria": e.get("kill_criteria") or [],
        "evidence_display": [],
        "confidence": e.get("confidence") or "low",
    } for e in rows]
    asof = str(rows[0].get("asof") or "")

    return {
        "asof": asof,
        "n_theses": len(theses),
        "theses": theses,
        "from_ledger": True,
        "regime_read": (
            f"Last saved analyst read — {asof}. No new read was taken for this rebuild; "
            f"the break-conditions below are the ones it last set."
        ),
        "regime_read_zh": (
            f"上次保存的分析师解读 — {asof}。本次重建未重新解读；"
            f"以下失效条件为上次设定。"
        ),
        "confidence": "low",
        "disclaimer": ("An AI reading of the desk's OWN deterministic convergence — "
                       "checkable and forward-graded, never a price forecast. "
                       "Replayed from the last saved read; not regenerated for this page."),
    }


def _append_ledger(out: dict, convergence: dict) -> None:
    """Append each thesis with the deterministic HEAT it was built on, so thesis_monitor can
    fire when that convergence decays. Deduped by (theme, asof).

    Gate: COLLECT_LANE=nightly — nightly is the sole advancer of forward ledgers.
    """
    if not _ledger_advance_enabled():
        log.debug("foresight_analyst._append_ledger: skipped (COLLECT_LANE != nightly)")
        return
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
            # W4b audit fields
            "n_grounded": th.get("n_grounded"),
            "n_total_evidence": th.get("n_total_evidence"),
            "_forecast_clamped": th.get("_forecast_clamped"),
        }, separators=(",", ":")))
    if lines:
        with p.open("a") as fh:
            fh.write("\n".join(lines) + "\n")
