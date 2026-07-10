"""scripts/run_causal_brainstorm.py — CHF W5 LLM chain runner.

Operator trigger + auto_loop gate + OAuth identity + ISO-week idempotency.
Mirrors the cortex job architecture (tool loop client pattern, provider waterfall,
run_status dict, never-raise contract, exit 0 always except unexpected crash).

CHF-R8 (as amended by operator ruling 2026-07-09 — masterplan §9): the LLM chain
runs only when:
  (i)  trigger == 'operator'   — any available auth provider (full waterfall)
  (ii) trigger == 'scheduled'  AND config auto_loop is true  AND the
       CLAUDE_CODE_OAUTH_TOKEN (oauth) provider is available. The operator
       directed OAuth-ONLY identity for scheduled runs, superseding the
       original service-key requirement; the ANTHROPIC_API_KEY provider is
       explicitly excluded from the scheduled path.
Without auth or gate: pack-only mode (operator-paste workflow).

CHF-R17: LLM actor law — the chain is a mechanical rule-application pipeline.
The script never transitions card status; cards land status='inbox' via the ingest.

Usage:
    python -m scripts.run_causal_brainstorm [--root PATH] [--trigger operator|scheduled] [--dry-run]

Outputs (non-fatal on any individual failure):
  /tmp/causal_brainstorm_pack_<isoweek>.txt  — brainstorm pack (always rebuilt fresh)
  data/neuralweb/causal_brainstorm_runs.jsonl — LLM raw replies + token counts (append)
  data/neuralweb/causal_llm_lane.json        — W3-readable lane status
  data/neuralweb/causal_mechanisms.jsonl     — cards filed via ingest (write mode only)
  data/neuralweb/governance.jsonl            — a6_llm_proposed event per filed batch
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_CONFIG_PATH = ROOT / "config" / "causal_llm.yml"
_LANE_FILE = ROOT / "data" / "neuralweb" / "causal_llm_lane.json"
_RUNS_FILE = ROOT / "data" / "neuralweb" / "causal_brainstorm_runs.jsonl"
_MECHANISMS_DIR = ROOT / "data" / "neuralweb"

# ---------------------------------------------------------------------------
# Config loader
# ---------------------------------------------------------------------------

def _load_config() -> dict:
    """Load config/causal_llm.yml; fail-open with defaults."""
    try:
        import yaml
        return yaml.safe_load(_CONFIG_PATH.read_text(encoding="utf-8")) or {}
    except Exception as exc:  # noqa: BLE001
        log.warning("run_causal_brainstorm: could not load causal_llm.yml (%s); using defaults", exc)
        return {}


# ---------------------------------------------------------------------------
# ISO week helpers (idempotency)
# ---------------------------------------------------------------------------

def _current_iso_week() -> str:
    now = datetime.now(timezone.utc)
    year, week, _ = now.isocalendar()
    return f"{year}-W{week:02d}"


def _already_filed_this_week() -> bool:
    """Return True if ISO-week lock says we already filed this week."""
    try:
        from scripts.causal_ingest_brainstorm import (  # noqa: PLC0415
            _count_filed_this_week,
            _BUDGET_PER_WEEK,
        )
        count = _count_filed_this_week(_MECHANISMS_DIR)
        return count >= _BUDGET_PER_WEEK
    except Exception:  # noqa: BLE001
        return False


# ---------------------------------------------------------------------------
# Lane status file
# ---------------------------------------------------------------------------

def _write_lane_status(
    status: str,
    reason: str,
    root: Path | None = None,
) -> None:
    """Write data/neuralweb/causal_llm_lane.json with current lane status.

    Statuses:
      degraded_pack_only — no auth or gate not passed; pack written, no LLM
      awaiting_phase_a   — auto_loop=False and no operator trigger
      ok                 — full LLM run completed
    """
    base = root or ROOT
    lane_path = base / "data" / "neuralweb" / "causal_llm_lane.json"
    try:
        lane_path.parent.mkdir(parents=True, exist_ok=True)
        doc = {
            "status": status,
            "asof": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "reason": reason,
        }
        lane_path.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        log.warning("run_causal_brainstorm: could not write lane status (%s)", exc)


# ---------------------------------------------------------------------------
# Provider builders for scheduled vs operator triggers
# ---------------------------------------------------------------------------

def _build_scheduled_providers(cfg: dict) -> list[dict]:
    """For scheduled trigger: ONLY the CLAUDE_CODE_OAUTH_TOKEN (oauth) provider.

    Operator ruling 2026-07-09 (masterplan §9) overrides the original W-AUTO
    service-key requirement for CHF: scheduled auto-loop runs on the user's
    OAuth identity. The ANTHROPIC_API_KEY and deepseek providers are explicitly
    EXCLUDED from the scheduled path — the operator directed "don't use api
    key, use oauth". A missing/invalid OAuth token degrades to pack-only mode.
    """
    from engine import llm_auth  # noqa: PLC0415

    model = cfg.get("model_roles", {}).get("generator", "claude-sonnet-4-6")
    try:
        providers = llm_auth.build_providers(cfg, opus_model=model)
    except Exception as exc:  # noqa: BLE001
        log.warning("run_causal_brainstorm: provider build failed (%s)", exc)
        return []
    return [p for p in providers if p.get("name") == "oauth"]


def _build_operator_providers(cfg: dict, model_override: str | None = None) -> list[dict]:
    """For operator trigger: full waterfall (oauth → anthropic → deepseek)."""
    from engine import llm_auth  # noqa: PLC0415
    model = model_override or cfg.get("model_roles", {}).get("generator", "claude-sonnet-4-6")
    return llm_auth.build_providers(cfg, opus_model=model)


def _build_providers_for_model(
    cfg: dict,
    trigger: str,
    model_role: str,
) -> list[dict]:
    """Build providers selecting the right model from model_roles."""
    model = cfg.get("model_roles", {}).get(model_role)
    if trigger == "scheduled":
        # OAuth only (operator ruling 2026-07-09); swap the model
        providers = _build_scheduled_providers(cfg)
        if providers and model:
            for p in providers:
                p["model"] = model
        return providers
    else:
        return _build_operator_providers(cfg, model_override=model)


# ---------------------------------------------------------------------------
# Numeric field rejection (RF-7 / CHF-R17 skeptic validator)
# ---------------------------------------------------------------------------

_NUMERIC_FIELD_NAMES = frozenset({
    "confidence", "confidence_score", "probability", "prob",
    "score", "weight", "numeric_confidence", "confidence_pct",
})


def _has_numeric_confidence(obj: Any, depth: int = 0) -> bool:
    """Return True if obj (dict or list) contains a numeric confidence-like field."""
    if depth > 8:
        return False
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k.lower() in _NUMERIC_FIELD_NAMES and isinstance(v, (int, float)):
                return True
            if _has_numeric_confidence(v, depth + 1):
                return True
    elif isinstance(obj, list):
        for item in obj:
            if _has_numeric_confidence(item, depth + 1):
                return True
    return False


def _validate_skeptic_findings(findings: list[dict]) -> tuple[list[dict], list[str]]:
    """Validate skeptic output: reject any finding with numeric confidence (RF-7).

    Returns (valid_findings, rejection_reasons).
    """
    valid: list[dict] = []
    rejected: list[str] = []
    for i, f in enumerate(findings):
        if _has_numeric_confidence(f):
            card_id = f.get("card_id", f"finding[{i}]")
            rejected.append(f"{card_id}: contains numeric confidence field (RF-7 violation — skeptic output must be categorical only)")
        else:
            valid.append(f)
    return valid, rejected


# ---------------------------------------------------------------------------
# LLM call helpers (mirror cortex.py client usage + run_status pattern)
# ---------------------------------------------------------------------------

def _llm_call(
    providers: list[dict],
    system: str,
    user: str,
    max_tokens: int,
    context: str,
) -> tuple[str | None, str | None, str | None, dict]:
    """Make one LLM call via the provider waterfall.

    Returns (text, degraded_reason, provider_used, token_counts_dict).
    """
    from engine import llm_auth  # noqa: PLC0415

    token_counts: dict = {}

    def _call_fn(client, model: str) -> tuple[str | None, str | None]:
        resp = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
            temperature=0,
        )
        text = "".join(
            b.text for b in resp.content if getattr(b, "type", "") == "text"
        )
        usage = getattr(resp, "usage", None)
        if usage is not None:
            token_counts["input_tokens"] = getattr(usage, "input_tokens", None)
            token_counts["output_tokens"] = getattr(usage, "output_tokens", None)
        return text, None

    text, reason, provider = llm_auth.make_call(providers, _call_fn, context=context)
    return text, reason, provider, token_counts


# ---------------------------------------------------------------------------
# Pack builder (always fresh — CHF-R8: never reuse a persisted pack)
# ---------------------------------------------------------------------------

def _build_fresh_pack(root: Path, n_cards: int = 3) -> str:
    """Build a fresh brainstorm pack via scripts.causal_brainstorm_pack.build_pack.

    CHF-R8 mandates the pack be rebuilt fresh every run — never reusing a persisted pack.
    The n_cards cap aligns with the weekly budget (CHF-R8: weekly_budget_cards: 3).
    """
    from scripts.causal_brainstorm_pack import build_pack  # noqa: PLC0415
    return build_pack(n_requested=n_cards)


# ---------------------------------------------------------------------------
# Pack-only mode
# ---------------------------------------------------------------------------

def _run_pack_only_mode(
    cfg: dict,
    reason: str,
    iso_week: str,
    root: Path,
) -> int:
    """Build fresh pack, write to /tmp, update lane status. Always returns 0."""
    print(f"[run_causal_brainstorm] {reason}")
    print("[run_causal_brainstorm] Entering pack-only mode.")

    try:
        n_cards = int(cfg.get("weekly_budget_cards", 3))
        pack_text = _build_fresh_pack(root, n_cards=n_cards)
        pack_path = Path(tempfile.gettempdir()) / f"causal_brainstorm_pack_{iso_week}.txt"
        pack_path.write_text(pack_text, encoding="utf-8")
        print(f"[run_causal_brainstorm] Pack written to: {pack_path}")
    except Exception as exc:  # noqa: BLE001
        print(f"[run_causal_brainstorm] WARNING: pack build failed ({exc}); continuing")

    # Determine lane status: if auto_loop is False this is the expected state
    if "auto_loop disabled" in reason:
        lane_status = "awaiting_phase_a"
    else:
        lane_status = "degraded_pack_only"

    _write_lane_status(lane_status, reason, root=root)
    return 0


# ---------------------------------------------------------------------------
# Full mode: generator → skeptic → compiler → ingest
# ---------------------------------------------------------------------------

def _run_full_mode(
    cfg: dict,
    trigger: str,
    iso_week: str,
    dry_run: bool,
    root: Path,
) -> int:
    """Run the full LLM chain: generator → skeptic (filter) → compiler → ingest.

    Returns 0 always (non-fatal pattern).
    """
    import tempfile  # noqa: PLC0415
    run_status: dict[str, Any] = {
        "trigger": trigger,
        "iso_week": iso_week,
        "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "mode": "full",
        "dry_run": dry_run,
        "stages": {},
    }

    n_cards = int(cfg.get("weekly_budget_cards", 3))
    model_roles = cfg.get("model_roles", {})
    generator_model = model_roles.get("generator", "claude-sonnet-4-6")
    skeptic_model = model_roles.get("skeptic", "claude-opus-4-8")
    compiler_model = model_roles.get("compiler", "claude-haiku-4-5-20251001")

    # ---- Step 1: Build fresh pack ----
    print("[run_causal_brainstorm] Building fresh brainstorm pack...")
    try:
        pack_text = _build_fresh_pack(root, n_cards=n_cards)
        pack_path = Path(tempfile.gettempdir()) / f"causal_brainstorm_pack_{iso_week}.txt"
        pack_path.write_text(pack_text, encoding="utf-8")
        print(f"[run_causal_brainstorm] Pack written to: {pack_path}")
        run_status["stages"]["pack"] = "ok"
    except Exception as exc:  # noqa: BLE001
        print(f"[run_causal_brainstorm] ERROR: pack build failed ({exc}); aborting full mode")
        run_status["stages"]["pack"] = f"error: {exc}"
        _write_run_log(run_status, root=root)
        _write_lane_status("degraded_pack_only", f"pack build failed: {exc}", root=root)
        return 0

    # ---- Step 2: GENERATOR — pack → JSON array of candidate cards ----
    print(f"[run_causal_brainstorm] Stage: GENERATOR (model={generator_model})")
    gen_providers = _build_providers_for_model(cfg, trigger, "generator")
    gen_system = (
        "You are the CHF brainstorm generator. Read the BRAINSTORM PACK carefully. "
        "Produce EXACTLY the requested number of candidate mechanism cards as a JSON array. "
        "Obey all forbidden-output constraints in the pack. Return JSON array ONLY."
    )
    gen_text, gen_reason, gen_provider, gen_tokens = _llm_call(
        gen_providers, gen_system, pack_text,
        max_tokens=4000, context="chf_generator",
    )

    run_status["stages"]["generator"] = {
        "model": generator_model,
        "provider": gen_provider,
        "degraded_reason": gen_reason,
        "token_counts": gen_tokens,
    }

    if gen_text is None:
        print(f"[run_causal_brainstorm] WARNING: generator failed (reason={gen_reason}); falling to pack-only")
        _write_run_log(run_status, root=root)
        _write_lane_status("degraded_pack_only", f"generator failed: {gen_reason}", root=root)
        return 0

    # Parse generator output
    try:
        candidate_cards = _parse_json_array(gen_text)
    except Exception as exc:  # noqa: BLE001
        print(f"[run_causal_brainstorm] WARNING: could not parse generator output ({exc}); falling to pack-only")
        run_status["stages"]["generator"]["parse_error"] = str(exc)
        _write_run_log(run_status, root=root)
        _write_lane_status("degraded_pack_only", f"generator parse error: {exc}", root=root)
        return 0

    print(f"[run_causal_brainstorm] Generator produced {len(candidate_cards)} card(s)")
    run_status["stages"]["generator"]["n_cards_raw"] = len(candidate_cards)

    # ---- Step 3: SKEPTIC — cards → per-card ADVISORY findings (categorical only) ----
    print(f"[run_causal_brainstorm] Stage: SKEPTIC (model={skeptic_model})")
    skeptic_providers = _build_providers_for_model(cfg, trigger, "skeptic")

    skeptic_system = (
        "You are the CHF adversarial skeptic. Your job is to find confounders, "
        "colliders, circular definitions, and missing falsifiers in proposed mechanism cards. "
        "\n\nRULES:\n"
        "- Produce ONLY categorical findings per card: NO numeric confidence scores, "
        "probabilities, weights, or any numeric field that represents confidence.\n"
        "- recommendation MUST be one of: ADVISORY_DROP or ADVISORY_KEEP (no other values).\n"
        "- blockers[] must be a list of strings describing specific methodological problems.\n"
        "- Return a JSON array where each element has: "
        "{card_id: str, recommendation: 'ADVISORY_DROP'|'ADVISORY_KEEP', blockers: [str]}.\n"
        "- If a card has a circular definition (outcome causes the cause), or a known "
        "collider as a conditioning variable, or fewer than 2 falsifiers: recommend ADVISORY_DROP.\n"
        "- This is ADVISORY-ONLY input to a mechanical rule-application script. "
        "Your output never directly transitions a card's status."
    )
    skeptic_user = (
        f"Review these {len(candidate_cards)} candidate mechanism cards for confounders, "
        f"colliders, and missing falsifiers. Return JSON array only.\n\n"
        f"CARDS:\n{json.dumps(candidate_cards, indent=2, ensure_ascii=False)}"
    )

    skep_text, skep_reason, skep_provider, skep_tokens = _llm_call(
        skeptic_providers, skeptic_system, skeptic_user,
        max_tokens=2000, context="chf_skeptic",
    )

    run_status["stages"]["skeptic"] = {
        "model": skeptic_model,
        "provider": skep_provider,
        "degraded_reason": skep_reason,
        "token_counts": skep_tokens,
    }

    # Mechanically apply skeptic findings (CHF-R17: actor stays 'script')
    surviving_cards = candidate_cards
    if skep_text is not None:
        try:
            findings_raw = _parse_json_array(skep_text)
            # Validate: reject numeric fields (RF-7)
            valid_findings, rf7_rejections = _validate_skeptic_findings(findings_raw)
            if rf7_rejections:
                print(f"[run_causal_brainstorm] WARNING: skeptic RF-7 violations (numeric confidence): {rf7_rejections}")
                run_status["stages"]["skeptic"]["rf7_rejections"] = rf7_rejections

            # Build drop set from valid ADVISORY_DROP recommendations
            drop_ids: set[str] = set()
            for f in valid_findings:
                if f.get("recommendation") == "ADVISORY_DROP":
                    cid = str(f.get("card_id", ""))
                    if cid:
                        drop_ids.add(cid)
                        blockers = f.get("blockers", [])
                        print(f"[run_causal_brainstorm] ADVISORY_DROP: card_id={cid!r} blockers={blockers}")

            # Drop ADVISORY_DROP cards (mechanical rule-application on advisory output)
            surviving_cards = [
                c for c in candidate_cards
                if str(c.get("mechanism_id", "")) not in drop_ids
            ]
            n_dropped = len(candidate_cards) - len(surviving_cards)
            print(f"[run_causal_brainstorm] Skeptic: {n_dropped} card(s) dropped by ADVISORY_DROP, "
                  f"{len(surviving_cards)} surviving")
            run_status["stages"]["skeptic"]["n_dropped"] = n_dropped
            run_status["stages"]["skeptic"]["n_surviving"] = len(surviving_cards)
            run_status["stages"]["skeptic"]["drop_ids"] = sorted(drop_ids)
        except Exception as exc:  # noqa: BLE001
            print(f"[run_causal_brainstorm] WARNING: skeptic parse failed ({exc}); proceeding with all cards")
            run_status["stages"]["skeptic"]["parse_error"] = str(exc)
    else:
        print(f"[run_causal_brainstorm] WARNING: skeptic unavailable (reason={skep_reason}); all cards survive")

    if not surviving_cards:
        print("[run_causal_brainstorm] All cards dropped by skeptic; nothing to file")
        _write_run_log(run_status, root=root)
        _write_lane_status("ok", "all cards dropped by skeptic; no filing this week", root=root)
        return 0

    # ---- Step 4: COMPILER — surviving cards → strict schema JSON ----
    # Skip if generator output already looks schema-valid (compiler is optional
    # refinement; if it fails we proceed with surviving generator cards)
    print(f"[run_causal_brainstorm] Stage: COMPILER (model={compiler_model})")
    compiler_providers = _build_providers_for_model(cfg, trigger, "compiler")

    compiler_system = (
        "You are the CHF schema compiler. Convert the given candidate mechanism cards "
        "to strictly conform to the neuralweb.causal_mechanism_card.v1 schema. "
        "Fix any missing required fields by inference from context. "
        "Do NOT change the meaning, cause, target, or falsifiers. "
        "Return a JSON array only — no prose."
    )
    compiler_user = (
        f"Compile these {len(surviving_cards)} surviving cards to strict schema. "
        f"Return JSON array only.\n\n"
        f"CARDS:\n{json.dumps(surviving_cards, indent=2, ensure_ascii=False)}"
    )

    comp_text, comp_reason, comp_provider, comp_tokens = _llm_call(
        compiler_providers, compiler_system, compiler_user,
        max_tokens=3000, context="chf_compiler",
    )

    run_status["stages"]["compiler"] = {
        "model": compiler_model,
        "provider": comp_provider,
        "degraded_reason": comp_reason,
        "token_counts": comp_tokens,
    }

    final_cards = surviving_cards  # default: use pre-compiler cards
    if comp_text is not None:
        try:
            compiled = _parse_json_array(comp_text)
            if compiled and len(compiled) >= len(surviving_cards) * 0.5:
                final_cards = compiled
                run_status["stages"]["compiler"]["n_compiled"] = len(compiled)
                print(f"[run_causal_brainstorm] Compiler produced {len(compiled)} compiled card(s)")
            else:
                print(f"[run_causal_brainstorm] WARNING: compiler output too short; using pre-compiler cards")
        except Exception as exc:  # noqa: BLE001
            print(f"[run_causal_brainstorm] WARNING: compiler parse failed ({exc}); using pre-compiler cards")
            run_status["stages"]["compiler"]["parse_error"] = str(exc)
    else:
        print(f"[run_causal_brainstorm] NOTE: compiler unavailable (reason={comp_reason}); using pre-compiler cards")

    # ---- Step 5: Write raw LLM replies to runs log ----
    pack_id = f"chf-{iso_week}-{trigger}"
    _write_run_log(
        run_status,
        root=root,
        pack_id=pack_id,
        raw_replies={
            "generator": gen_text,
            "skeptic": skep_text,
            "compiler": comp_text,
        },
        models={
            "generator": generator_model,
            "skeptic": skeptic_model,
            "compiler": compiler_model,
        },
        trigger=trigger,
    )

    # ---- Step 6: Write cards to temp inbox and invoke W4 ingest ----
    if not final_cards:
        print("[run_causal_brainstorm] No cards to file after pipeline")
        _write_lane_status("ok", "pipeline produced no cards to file", root=root)
        return 0

    # Write cards to a temp inbox dir for the ingest
    with tempfile.TemporaryDirectory(prefix="chf_inbox_") as tmp_inbox_str:
        tmp_inbox = Path(tmp_inbox_str)
        cards_file = tmp_inbox / "brainstorm_cards.json"
        cards_file.write_text(json.dumps(final_cards, ensure_ascii=False, indent=2), encoding="utf-8")

        try:
            from scripts.causal_ingest_brainstorm import ingest  # noqa: PLC0415
            rc = ingest(
                inbox=tmp_inbox,
                out_dir=root / "data" / "neuralweb",
                dry_run=dry_run,
                model_label=generator_model,
            )
            run_status["stages"]["ingest"] = {"rc": rc, "dry_run": dry_run}
            print(f"[run_causal_brainstorm] Ingest completed (rc={rc}, dry_run={dry_run})")
        except Exception as exc:  # noqa: BLE001
            print(f"[run_causal_brainstorm] WARNING: ingest failed ({exc}); cards not filed")
            run_status["stages"]["ingest"] = {"error": str(exc)}

    # ---- Step 7: Governance event ----
    try:
        from engine.neuralweb import governance  # noqa: PLC0415
        n_filed = len(final_cards)
        governance.append_event(
            "a6_llm_proposed",
            target="causal_mechanisms",
            article=None,
            authored_by="run_causal_brainstorm",
            evidence={
                "pack_id": pack_id,
                "n_cards": n_filed,
                "trigger": trigger,
                "models": {
                    "generator": generator_model,
                    "skeptic": skeptic_model,
                    "compiler": compiler_model,
                },
            },
            root=root,
            note=f"CHF W5 LLM brainstorm batch; iso_week={iso_week}; dry_run={dry_run}",
        )
        print(f"[run_causal_brainstorm] Governance event appended (a6_llm_proposed, n_cards={n_filed})")
    except Exception as exc:  # noqa: BLE001
        print(f"[run_causal_brainstorm] WARNING: governance event failed ({exc}); non-fatal")

    _write_lane_status("ok", f"full run completed; {len(final_cards)} card(s) processed", root=root)
    return 0


# ---------------------------------------------------------------------------
# Run log writer
# ---------------------------------------------------------------------------

def _write_run_log(
    run_status: dict,
    root: Path | None = None,
    pack_id: str | None = None,
    raw_replies: dict | None = None,
    models: dict | None = None,
    trigger: str | None = None,
) -> None:
    """Append one row to data/neuralweb/causal_brainstorm_runs.jsonl."""
    base = root or ROOT
    runs_path = base / "data" / "neuralweb" / "causal_brainstorm_runs.jsonl"
    try:
        runs_path.parent.mkdir(parents=True, exist_ok=True)
        row: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "pack_id": pack_id,
            "run_status": run_status,
        }
        if models:
            row["models"] = models
        if trigger:
            row["trigger"] = trigger
        if raw_replies:
            # Truncate raw replies to avoid gigantic log rows
            row["raw_replies"] = {
                k: (v[:2000] + "... [truncated]" if v and len(v) > 2000 else v)
                for k, v in raw_replies.items()
            }
        with runs_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, default=str, ensure_ascii=False) + "\n")
    except Exception as exc:  # noqa: BLE001
        log.warning("run_causal_brainstorm: could not write runs log (%s)", exc)


# ---------------------------------------------------------------------------
# JSON array parser (tolerant — mirrors causal_ingest_brainstorm pattern)
# ---------------------------------------------------------------------------

def _parse_json_array(text: str) -> list[dict]:
    """Parse LLM output that should be a JSON array. Tries multiple strategies."""
    import json as _json

    text = text.strip()

    # Direct parse
    try:
        obj = _json.loads(text)
        if isinstance(obj, list):
            return [c for c in obj if isinstance(c, dict)]
    except _json.JSONDecodeError:
        pass

    # Strip markdown code fences
    for fence in ("```json", "```"):
        if fence in text:
            start = text.find(fence) + len(fence)
            end = text.rfind("```")
            if end > start:
                inner = text[start:end].strip()
                try:
                    obj = _json.loads(inner)
                    if isinstance(obj, list):
                        return [c for c in obj if isinstance(c, dict)]
                except _json.JSONDecodeError:
                    pass

    # Find first '[' and last ']'
    start = text.find("[")
    end = text.rfind("]")
    if start != -1 and end > start:
        try:
            obj = _json.loads(text[start:end + 1])
            if isinstance(obj, list):
                return [c for c in obj if isinstance(c, dict)]
        except _json.JSONDecodeError:
            pass

    raise ValueError(f"could not parse JSON array from text of length {len(text)}")


# ---------------------------------------------------------------------------
# Main entrypoint
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    """Main entrypoint. Always returns 0 except unexpected crash."""
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", type=Path, default=None,
                    help="Repo root (default: inferred from script location)")
    ap.add_argument("--trigger", choices=["operator", "scheduled"], default="operator",
                    help="Trigger mode (default: operator)")
    ap.add_argument("--dry-run", action="store_true", default=False,
                    help="Dry-run: build pack + run LLM chain but do not write cards to disk")
    args = ap.parse_args(argv)

    root = Path(args.root) if args.root else ROOT
    trigger = args.trigger
    dry_run = args.dry_run
    iso_week = _current_iso_week()

    print(f"[run_causal_brainstorm] trigger={trigger}, iso_week={iso_week}, dry_run={dry_run}")

    # Load config
    cfg = _load_config()

    # ---- GATE 1: scheduled + auto_loop disabled → pack-only ----
    if trigger == "scheduled":
        auto_loop = cfg.get("auto_loop", False)
        if not auto_loop:
            return _run_pack_only_mode(
                cfg,
                reason="auto_loop disabled — pack-only mode",
                iso_week=iso_week,
                root=root,
            )

    # ---- GATE 2: ISO-week idempotency ----
    if not dry_run and _already_filed_this_week():
        print(f"[run_causal_brainstorm] ISO-week lock: already filed budget this week ({iso_week}); skip filing, exit 0")
        _write_lane_status("ok", f"already filed this week ({iso_week}); idempotent skip", root=root)
        return 0

    # ---- GATE 3: auth availability check ----
    if trigger == "scheduled":
        # Scheduled MUST use service-key (ANTHROPIC_API_KEY)
        providers = _build_scheduled_providers(cfg)
        if not providers:
            return _run_pack_only_mode(
                cfg,
                reason="scheduled trigger requires ANTHROPIC_API_KEY service-key — not available; pack-only mode",
                iso_week=iso_week,
                root=root,
            )
    else:
        # Operator can use any provider (full waterfall)
        providers = _build_operator_providers(cfg)
        if not providers:
            return _run_pack_only_mode(
                cfg,
                reason="no LLM auth available (operator trigger); pack-only mode",
                iso_week=iso_week,
                root=root,
            )

    # ---- FULL MODE ----
    print("[run_causal_brainstorm] Auth available; running full LLM chain")
    return _run_full_mode(
        cfg=cfg,
        trigger=trigger,
        iso_week=iso_week,
        dry_run=dry_run,
        root=root,
    )


if __name__ == "__main__":
    sys.exit(main())
