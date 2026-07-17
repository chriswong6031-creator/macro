"""Extraction-drift monitor — re-score the anchor set against the current model.

Spec reference: §2.4 (drift protocol), research/QUALITATIVE_INTELLIGENCE_UPGRADE_BY_FABLE.md

Usage
-----
Full mode (all 50 anchors — model-upgrade gate):
    python scripts/check_extraction_drift.py
    Exit 0 = pass (field_agree_rate ≥ 0.85).
    Exit 1 = drift detected — do NOT upgrade the extraction model.

Light / weekly mode (10-sample rolling re-score, alert on deviation):
    python scripts/check_extraction_drift.py --light
    Writes a JSON summary line to data/qledger/run_status.json under the key
    "extraction_drift" and exits 0 even if the sample drifts (generates an alert
    line only — the weekly cron reads the status file).

Dry-run (no LLM calls — validates anchor schema and gate math only):
    python scripts/check_extraction_drift.py --dry-run

How the gate works
------------------
For each anchor the current extraction model is asked for:
  direction       — enum {bullish, bearish, neutral}
  magnitude       — int 0-3
  confidence      — enum {low, medium, high}
  reversibility   — enum {permanent, temporary, unclear}

Agreement metrics (compared against gold labels in the anchor file):
  field_agree_rate     — fraction where direction matches exactly
  magnitude_band_rate  — fraction where |predicted − gold| ≤ 1
  confidence_band_rate — fraction where |confidence_ord − gold_ord| ≤ 1
  quote_verify_rate    — fraction where the model's quote_span substring
                         appears verbatim in the anchor body

Gate (model-upgrade gate, full mode): field_agree_rate < 0.85 → exit 1.
Weekly light mode: alert line if field_agree_rate < 0.85 on the sample.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import random
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lib import config

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
ANCHOR_FILE = ROOT / "data" / "drift_anchors" / "extraction_anchors.jsonl"
STATUS_FILE = ROOT / "data" / "qledger" / "run_status.json"

_DIRECTION_VALID = {"bullish", "bearish", "neutral"}
_MAGNITUDE_VALID = {0, 1, 2, 3}
_CONFIDENCE_VALID = {"low", "medium", "high"}
_REVERSIBILITY_VALID = {"permanent", "temporary", "unclear"}
_CONF_ORD = {"low": 0, "medium": 1, "high": 2}

FIELD_AGREE_GATE = 0.85   # §2.4: model-upgrade gate

# ---------------------------------------------------------------------------
# Anchor loading + schema validation
# ---------------------------------------------------------------------------

def load_anchors(path: Path = ANCHOR_FILE) -> list[dict]:
    """Load and validate the anchor JSONL file. Raises on schema errors."""
    if not path.exists():
        raise FileNotFoundError(f"Anchor file not found: {path}")
    anchors = []
    with path.open() as fh:
        for i, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError as e:
                raise ValueError(f"Anchor JSONL parse error at line {i}: {e}") from e
            _validate_anchor(rec, i)
            anchors.append(rec)
    if not anchors:
        raise ValueError("Anchor file is empty — cannot run drift check.")
    return anchors


def _validate_anchor(rec: dict, line_num: int) -> None:
    """Raise ValueError if the anchor record is malformed."""
    required = ("anchor_id", "source_lane", "source_id", "body", "gold", "gold_source")
    for k in required:
        if k not in rec:
            raise ValueError(f"Anchor line {line_num}: missing field '{k}'")
    gold = rec["gold"]
    for gk in ("direction", "magnitude", "confidence", "reversibility"):
        if gk not in gold:
            raise ValueError(f"Anchor line {line_num}: gold missing '{gk}'")
    if gold["direction"] not in _DIRECTION_VALID:
        raise ValueError(f"Anchor line {line_num}: invalid gold direction '{gold['direction']}'")
    if gold["confidence"] not in _CONFIDENCE_VALID:
        raise ValueError(f"Anchor line {line_num}: invalid gold confidence '{gold['confidence']}'")

# ---------------------------------------------------------------------------
# LLM extraction (current model)
# ---------------------------------------------------------------------------

_EXTRACT_SYSTEM = (
    "You are a financial-text extraction engine implementing qual_extraction.v1.\n"
    "Given a body of text from a financial filing, news headline, or policy announcement, "
    "extract the following fields and return STRICT JSON ONLY (no prose, no fences):\n"
    "  direction:     'bullish' | 'bearish' | 'neutral'\n"
    "  magnitude:     int 0 (not material) | 1 (minor) | 2 (moderate) | 3 (major)\n"
    "  confidence:    'low' | 'medium' | 'high'\n"
    "  reversibility: 'permanent' | 'temporary' | 'unclear'\n"
    "  quote_span:    a verbatim substring from the body (≤120 chars) that most "
    "supports your direction judgment. Must appear EXACTLY in the body text.\n"
    "  dropped_fields: array of field names you cannot reliably determine from the body.\n\n"
    "If the body is a headline-only (very short, no full sentences), set dropped_fields "
    "to ['magnitude','reversibility'] and magnitude/reversibility to null.\n"
    "Return ONLY a valid JSON object. No markdown fences."
)


def _call_model(body: str, model: str, providers: list) -> dict | None:
    """Call the extraction model for one anchor body via llm_auth waterfall.

    Returns parsed dict or None.  providers is a list of provider descriptors
    from llm_auth.build_providers (pool-aware failover + usage capture).
    """
    from engine import llm_auth  # noqa: PLC0415

    def _call_fn(client, m: str):
        resp = client.messages.create(
            model=m,
            max_tokens=400,
            system=_EXTRACT_SYSTEM,
            messages=[{"role": "user", "content": f"TEXT:\n{body[:2000]}"}],
        )
        if getattr(resp, "stop_reason", "") == "refusal":
            return None, "stop_refusal", resp
        text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
        return text, None, resp

    try:
        text, _, _ = llm_auth.make_call(providers, _call_fn, context="extraction_drift")
        if not text:
            return None
        # tolerant JSON extraction (handle fences)
        m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
        body_text = (m.group(1) if m else text).strip()
        parsed = json.loads(body_text)
        return parsed if isinstance(parsed, dict) else None
    except Exception as e:  # noqa: BLE001
        log.warning("extraction_drift: model call failed (%s)", e)
        return None


def _get_providers_and_model(cfg: dict) -> tuple | None:
    """Return (providers, model_id) for the extraction model, or None.

    Uses llm_auth.build_providers for pool-aware failover and usage capture.
    """
    model_id = cfg.get("qual_extraction", {}).get("model_id") or cfg.get(
        "altdata_brain", {}).get("model_id", "claude-haiku-4-5")
    try:
        from engine import llm_auth  # noqa: PLC0415
        llm_cfg = {
            "provider_order": ["oauth", "anthropic"],
            "oauth_token_env": "CLAUDE_CODE_OAUTH_TOKEN",
            "api_key_env": "ANTHROPIC_API_KEY",
            "oauth_pool_lane": "extraction-drift",
            "usage_lane": "extraction-drift",
        }
        providers = llm_auth.build_providers(llm_cfg, opus_model=model_id)
        if not providers:
            return None
        return providers, model_id
    except Exception as e:  # noqa: BLE001
        log.warning("extraction_drift: provider init failed (%s)", e)
        return None

# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def _score_predictions(anchors: list[dict], predictions: list[dict | None]) -> dict:
    """Compute agreement metrics between anchor golds and model predictions."""
    n = len(anchors)
    n_pred = sum(1 for p in predictions if p is not None)
    dir_agree = 0
    mag_band = 0
    conf_band = 0
    quote_ok = 0
    n_mag = 0   # only for records where gold has a concrete magnitude
    n_conf = 0
    n_quote = 0

    for anchor, pred in zip(anchors, predictions):
        if pred is None:
            continue
        gold = anchor["gold"]
        body = anchor.get("body", "")

        # Direction exact match
        if pred.get("direction") in _DIRECTION_VALID and pred["direction"] == gold["direction"]:
            dir_agree += 1

        # Magnitude ±1 band
        g_mag = gold.get("magnitude")
        p_mag = pred.get("magnitude")
        if g_mag is not None and p_mag is not None:
            try:
                if abs(int(p_mag) - int(g_mag)) <= 1:
                    mag_band += 1
                n_mag += 1
            except (TypeError, ValueError):
                pass

        # Confidence ±1 ordinal band
        g_conf = _CONF_ORD.get(gold.get("confidence", ""), -1)
        p_conf = _CONF_ORD.get(str(pred.get("confidence", "")).lower(), -1)
        if g_conf >= 0 and p_conf >= 0:
            if abs(p_conf - g_conf) <= 1:
                conf_band += 1
            n_conf += 1

        # Quote span verbatim verification
        p_quote = str(pred.get("quote_span", "") or "")
        if p_quote and body:
            if p_quote in body:
                quote_ok += 1
            n_quote += 1

    return {
        "n_anchors": n,
        "n_predicted": n_pred,
        "field_agree_rate": round(dir_agree / n_pred, 4) if n_pred else 0.0,
        "direction_exact_n": dir_agree,
        "magnitude_band_rate": round(mag_band / n_mag, 4) if n_mag else None,
        "confidence_band_rate": round(conf_band / n_conf, 4) if n_conf else None,
        "quote_verify_rate": round(quote_ok / n_quote, 4) if n_quote else None,
        "gate_pass": (dir_agree / n_pred >= FIELD_AGREE_GATE) if n_pred else False,
    }


# ---------------------------------------------------------------------------
# Dry-run (no LLM — schema gate only)
# ---------------------------------------------------------------------------

def dry_run(anchors: list[dict]) -> dict:
    """Validate anchor schema and return a synthetic 100% score (gate math check)."""
    # Simulate perfect predictions from gold
    preds = [
        {"direction": a["gold"]["direction"],
         "magnitude": a["gold"]["magnitude"],
         "confidence": a["gold"]["confidence"],
         "reversibility": a["gold"]["reversibility"],
         "quote_span": a["gold"].get("quote_span", "")[:60],
         "dropped_fields": a["gold"].get("dropped_fields", [])}
        for a in anchors
    ]
    scores = _score_predictions(anchors, preds)
    scores["mode"] = "dry-run"
    scores["note"] = "Schema valid; predictions are synthetic gold echoes."
    return scores


# ---------------------------------------------------------------------------
# Main entry points
# ---------------------------------------------------------------------------

def full_check(anchors: list[dict]) -> dict:
    """Run all 50 anchors through the current extraction model."""
    cfg = config.load()
    result = _get_providers_and_model(cfg)
    if result is None:
        log.error("extraction_drift: no LLM provider available — set ANTHROPIC_API_KEY or "
                  "CLAUDE_CODE_OAUTH_TOKEN to run the drift gate.")
        return {"error": "no_client", "gate_pass": False}

    providers, model_id = result
    log.info("extraction_drift: full check — %d anchors, model=%s", len(anchors), model_id)

    predictions = []
    for i, anchor in enumerate(anchors):
        pred = _call_model(anchor["body"], model_id, providers)
        predictions.append(pred)
        if (i + 1) % 10 == 0:
            log.info("  %d/%d anchors scored", i + 1, len(anchors))

    scores = _score_predictions(anchors, predictions)
    scores["mode"] = "full"
    scores["model_id"] = model_id
    scores["run_utc"] = datetime.now(timezone.utc).isoformat()
    return scores


def light_check(anchors: list[dict], n: int = 10, seed: Optional[int] = None) -> dict:
    """Sample n anchors for the weekly rolling re-score."""
    rng = random.Random(seed)
    sample = rng.sample(anchors, min(n, len(anchors)))
    cfg = config.load()
    result = _get_providers_and_model(cfg)
    if result is None:
        return {"error": "no_client", "gate_pass": None, "mode": "light"}

    providers, model_id = result
    log.info("extraction_drift: light check — %d anchors, model=%s", len(sample), model_id)

    predictions = [_call_model(a["body"], model_id, providers) for a in sample]
    scores = _score_predictions(sample, predictions)
    scores["mode"] = "light"
    scores["model_id"] = model_id
    scores["n_sample"] = len(sample)
    scores["run_utc"] = datetime.now(timezone.utc).isoformat()
    return scores


def _write_status(scores: dict) -> None:
    """Append/update the extraction_drift key in data/qledger/run_status.json."""
    STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        status = json.loads(STATUS_FILE.read_text()) if STATUS_FILE.exists() else {}
    except Exception:
        status = {}
    status["extraction_drift"] = scores
    STATUS_FILE.write_text(json.dumps(status, indent=2, ensure_ascii=False, default=str))
    log.info("extraction_drift: wrote status → %s", STATUS_FILE)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true",
                        help="Validate anchor schema + gate math only — no LLM calls.")
    parser.add_argument("--light", action="store_true",
                        help="10-sample rolling re-score; writes status, does not exit 1 on drift.")
    parser.add_argument("--anchor-file", default=str(ANCHOR_FILE),
                        help="Path to extraction_anchors.jsonl (default: %(default)s)")
    parser.add_argument("--seed", type=int, default=None, help="RNG seed for --light sampling.")
    args = parser.parse_args(argv)

    anchor_path = Path(args.anchor_file)
    anchors = load_anchors(anchor_path)

    bearish_n = sum(1 for a in anchors if a["gold"]["direction"] == "bearish")
    log.info("extraction_drift: loaded %d anchors (%d bearish)", len(anchors), bearish_n)

    if args.dry_run:
        scores = dry_run(anchors)
        print(json.dumps(scores, indent=2))
        log.info("Dry-run complete — gate math OK, schema valid.")
        return 0

    if args.light:
        scores = light_check(anchors, n=10, seed=args.seed)
        _write_status(scores)
        print(json.dumps(scores, indent=2))
        rate = scores.get("field_agree_rate")
        if rate is not None and rate < FIELD_AGREE_GATE:
            # alert line written to run_status; caller decides action
            log.warning(
                "extraction_drift LIGHT ALERT: field_agree_rate=%.3f < %.2f gate — "
                "run full check: python scripts/check_extraction_drift.py",
                rate, FIELD_AGREE_GATE)
        return 0

    # Full check — the model-upgrade gate
    scores = full_check(anchors)
    _write_status(scores)
    print(json.dumps(scores, indent=2))

    if scores.get("error"):
        log.error("extraction_drift: %s", scores["error"])
        return 1

    rate = scores.get("field_agree_rate", 0.0)
    gate = scores.get("gate_pass", False)
    if gate:
        log.info("extraction_drift: PASS — field_agree_rate=%.3f ≥ %.2f", rate, FIELD_AGREE_GATE)
        return 0
    else:
        log.error(
            "extraction_drift: FAIL — field_agree_rate=%.3f < %.2f gate. "
            "Do NOT update the extraction model_id until this clears.",
            rate, FIELD_AGREE_GATE)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
