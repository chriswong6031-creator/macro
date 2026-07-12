"""engine/experiments_registry.py — the running-experiments manifest.

Emits site/marketdata/experiments.json: EVERY accruing forward-validation track-record,
calibration accrual, PIT / vintage accrual, parked-research trigger, and long-horizon
data-collection pipeline in the codebase — each with a STATUS and a concrete COME-BACK
date, so the admin console (admin/experiments.py) tells the owner exactly when to return
for each experiment's next step (and alerts when results are ready).

Two layers:
  • SEED (data/experiments/registry_seed.json): curated metadata for every tracked
    experiment — name, kind, source, what it measures, maturation criteria, next-step,
    priority, and a come-back date. Grounded once by an exhaustive codebase audit; edit
    the seed to add / retire an experiment. This is the source of truth for WHAT is tracked.
  • DYNAMIC overlay: for the high-value track-records that carry a machine-readable verdict
    (snapshot jsonl + *_track_record.json), read the REAL current state each build and
    refresh status / state / ready. Everything degrades safely to the seed values.

DISPLAY-ONLY operational metadata; never sizes anything. Additive, never fatal.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone

from lib import config

log = logging.getLogger(__name__)

OUT = "marketdata/experiments.json"
SEED = "data/experiments/registry_seed.json"
_DONE = {"validated", "proven", "gate_open"}  # already concluded — don't re-flag on come-back date
_NO_AUTO_READY = {"parked_research"}           # never auto-matures a result on a date


def _root():
    return config.ROOT


def _read_json(rel: str):
    if not rel:
        return None
    try:
        return json.loads((_root() / rel).read_text())
    except Exception:  # noqa: BLE001
        return None


def _jsonl_dates(rel: str) -> tuple[int, int]:
    """(distinct-date count, total rows) from a snapshot jsonl; (0,0) if absent/parquet."""
    p = _root() / rel if rel else None
    if not p or not p.exists() or p.suffix != ".jsonl":
        return 0, 0
    dates, n = set(), 0
    try:
        for line in p.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            n += 1
            try:
                d = json.loads(line).get("date") or json.loads(line).get("snapshot_date")
                if d:
                    dates.add(str(d)[:10])
            except Exception:  # noqa: BLE001
                continue
    except Exception:  # noqa: BLE001
        return 0, 0
    return len(dates), n


def _refresh_track_record(e: dict) -> dict:
    """Live overlay for a forward track-record: real row/day counts + published verdict +
    max matured obs → refined {status, state, ready}. Falls back to the seed on any gap."""
    ndays, nrows = _jsonl_dates(e.get("storage") or "")
    tr = _read_json(e.get("track_json") or "")
    verdict = (tr or {}).get("verdict")
    max_mat = 0
    for hv in ((tr or {}).get("horizons") or {}).values():
        try:
            max_mat = max(max_mat, int(hv.get("n_matured") or 0))
        except Exception:  # noqa: BLE001
            pass
    out: dict = {}
    if verdict:
        out["status"] = verdict
    elif ndays:
        out["status"] = "accruing"
    if nrows:
        s = f"{nrows} calls · {ndays} day{'s' if ndays != 1 else ''} logged · {max_mat} matured"
        if verdict:
            s += f" · verdict={verdict}"
        out["state"] = s
    # results are "ready" once the read has GRADED. 'accruing' and 'measuring' are both
    # pre-verdict accrual states ('measuring' = rows matured but the significance gate is
    # not yet callable — engine/subsector_track_record.py); any other verdict (validated /
    # a printed null / …) is a real result and must flag ready.
    if verdict and verdict not in ("accruing", "measuring"):
        out["ready"] = True
    return out


def _refresh_qledger_promotion(e: dict) -> dict:
    """Live overlay for a qledger promotion-gate experiment.

    Reads site/qledger/track_record.json["promotion_readiness"][claim_family] and
    surfaces the live n_dates, wilson_ci_low, ready/approaching state, and the
    duel-context line (challenger vs placebo |excess| at 5d) so the admin
    Experiments tab shows real decision evidence rather than a static counter.

    Fields updated:
      status  — "accruing" | "gate_open" (ready=True at any horizon)
      state   — live summary line: n_dates/needed, CI-low, excess_mean, duel context
      ready   — True when §3 gate passes (n_dates>=25 AND wilson_ci_low>0)
      duel_context_line — challenger vs placebo |excess| at 5d (injected into next_step)
    """
    family = e.get("claim_family") or ""
    tr = _read_json("site/qledger/track_record.json")
    if not tr:
        return {}

    readiness = (tr.get("promotion_readiness") or {}).get(family) or {}
    duel_ctx = (tr.get("promotion_readiness") or {}).get("_duel_context", {}).get(family) or {}

    # Pick the most-advanced horizon (smallest h with most n_dates)
    best: dict = {}
    for h_str in ("5", "21", "63"):
        rec = readiness.get(h_str)
        if rec and rec.get("n_dates", 0) > best.get("n_dates", -1):
            best = dict(rec)
            best["_horizon"] = int(h_str)

    if not best:
        # promotion_readiness not yet written — fall back gracefully
        return {}

    n_dates = best.get("n_dates", 0)
    needed = best.get("needed", 25)
    ci_low = best.get("wilson_ci_low")
    hr = best.get("hit_rate")
    ex = best.get("excess_mean")
    horizon = best.get("_horizon", 5)
    ready = bool(best.get("ready"))
    approaching = bool(best.get("approaching"))
    proj = best.get("projected_ready_date")

    # Build a readable state line
    ci_str = f"{ci_low:.3f}" if ci_low is not None else "n/a"
    hr_str = f"{hr*100:.1f}%" if hr is not None else "salience-only"
    ex_str = f"{ex*100:.2f}%" if ex is not None else "n/a"
    state = (
        f"n_dates={n_dates}/{needed} @ {horizon}d · CI-low={ci_str} · "
        f"hit={hr_str} · excess={ex_str}"
    )
    if approaching and not ready:
        state += " · APPROACHING (≥20)"
    if proj and not ready:
        state += f" · proj_ready≈{proj}"

    # Duel context line: challenger vs placebo |excess| at 5d
    ch_ex = duel_ctx.get("challenger_excess_mean_5d")
    pl_ex = duel_ctx.get("placebo_covered_abs_excess_5d")
    duel_line = ""
    if ch_ex is not None and pl_ex is not None:
        duel_line = (
            f"Duel @5d: challenger excess_mean={ch_ex*100:.2f}% vs "
            f"placebo |excess|={pl_ex*100:.2f}% (covered-ticker tape) · "
            f"n_dates={duel_ctx.get('n_dates_5d',0)}"
        )

    out: dict = {
        "status": "gate_open" if ready else "accruing",
        "state": state,
        "ready": ready,
    }
    if duel_line:
        # Append duel context to next_step so it surfaces in the admin tab
        existing_next = e.get("next_step") or ""
        out["next_step"] = (f"{duel_line}\n{existing_next}").strip()
    return out


def _refresh_cortex_evaluator(e: dict) -> dict:
    """Live overlay for a cortex_hypothesis experiment.

    Reads data/neuralweb/machine_registry.jsonl for the matching id and
    surfaces the current status, verdict, and come_back.
    Falls back gracefully to seed values on any read error.
    """
    hyp_id = e.get("id")
    if not hyp_id:
        return {}
    try:
        from engine.neuralweb.metabolism import load_by_id  # type: ignore[import]
        row = load_by_id(hyp_id)
        if not row:
            return {}
        status = row.get("status", "registered")
        # Map metabolism status to experiments_registry vocabulary
        status_map = {
            "registered": "accruing",
            "accruing": "accruing",
            "passed": "gate_open",
            "failed": "no_go",
            "insufficient-n": "accruing",
            "budget-rejected": "accruing",
            "retired": "no_go",
            "invalid": "no_go",
        }
        out_status = status_map.get(status, "accruing")
        come_back = row.get("come_back")
        gate = row.get("pre_committed_gate") or {}
        state = (
            f"status={status} · "
            f"shape={row.get('claim_shape', '?')} · "
            f"gate={gate.get('metric','?')} {gate.get('threshold','?')} · "
            f"horizon={row.get('horizon_d','?')}d"
        )
        out: dict = {"status": out_status, "state": state}
        if status in ("passed", "gate_open"):
            out["ready"] = True
            out["state"] = state + " · PASSED — queued for quarterly FDR batch"
        if come_back:
            out["come_back_on"] = come_back
        return out
    except Exception as exc:  # noqa: BLE001
        import logging
        logging.getLogger(__name__).warning(
            "experiments_registry: cortex_evaluator hook failed for %s: %s", hyp_id, exc
        )
        return {}


_HOOKS = {"track_record": _refresh_track_record,
          "qledger_promotion": _refresh_qledger_promotion,
          "cortex_evaluator": _refresh_cortex_evaluator}


# Newer seed entries (hazard-live-reliability-*, w5a-reversal-rederive, hkca-*, w3*-…)
# were authored with an alternate keyset: title/hypothesis/registered_on/pr plus
# program/wave/channel/phase and verdict/result. compute() normalizes both keysets so
# the manifest never emits name/what=null — the admin Experiments tab renders those
# fields directly and shows blank cards otherwise.

def _alt_phase_hint(e: dict) -> str | None:
    """phase_hint fallback: 'program · wave · channel · phase' (blanks and N/A skipped)."""
    parts = [str(v) for v in (e.get("program"), e.get("wave"), e.get("channel"), e.get("phase"))
             if v and str(v).strip().lower() not in ("", "n/a")]
    return " · ".join(parts) or None


def _alt_state(e: dict) -> str | None:
    """state fallback: verdict + result, capped — some seed verdicts run to a paragraph."""
    bits = []
    if e.get("verdict"):
        bits.append(f"verdict={e['verdict']}")
    if e.get("result"):
        bits.append(str(e["result"]))
    s = " · ".join(bits)
    return (s[:397] + "…") if len(s) > 400 else (s or None)


def _load_machine_registry_entries() -> list[dict]:
    """Load cortex_hypothesis entries from data/neuralweb/machine_registry.jsonl.

    Converts machine-registration schema to the experiments-registry row format
    so compute() processes them through the standard hook pipeline.
    Only the LATEST status per id is included (last write wins in append-only log).
    """
    try:
        p = _root() / "data" / "neuralweb" / "machine_registry.jsonl"
        if not p.exists():
            return []
        # Load all rows, keep latest per id
        seen: dict[str, dict] = {}
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
                if row.get("kind") == "cortex_hypothesis":
                    seen[row["id"]] = row
            except Exception:  # noqa: BLE001
                pass
        # Convert to experiments-registry format
        out = []
        for row in seen.values():
            gate = row.get("pre_committed_gate") or {}
            out.append({
                "id": row["id"],
                "name": f"Cortex: {row.get('hypothesis', '')[:60]}",
                "kind": "cortex_hypothesis",
                "status": row.get("status", "registered"),
                "priority": "low",
                "what": row.get("hypothesis", ""),
                "hypothesis": row.get("hypothesis", ""),
                "source": f"cortex/{row.get('registered_by', 'cortex')}",
                "storage": "data/neuralweb/machine_registry.jsonl",
                "started": (row.get("registered_at") or "")[:10],
                "registered_on": (row.get("registered_at") or "")[:10],
                "maturation": f"horizon={row.get('horizon_d', '?')}d",
                "come_back_on": row.get("come_back"),
                "come_back_note": f"Evaluate against pre-committed gate: {gate.get('metric','?')} {gate.get('threshold','?')}",
                "next_step": (
                    f"Wait for evaluator on come_back date. "
                    f"Passed → quarterly cortex FDR batch. "
                    f"fdr_family=cortex (own family; never raises human program bar)."
                ),
                "phase_hint": f"neural-web · W7b · cortex · {row.get('claim_shape', '?')}",
                "state": f"status={row.get('status','registered')} shape={row.get('claim_shape','?')}",
                "hook": "cortex_evaluator",
                "claim_family": "cortex",
            })
        return out
    except Exception as exc:  # noqa: BLE001
        log.warning("experiments_registry: machine_registry load failed: %s", exc)
        return []


def compute() -> dict:
    today = datetime.now(timezone.utc).date()
    seed = _read_json(SEED) or {}
    rows_in = list(seed.get("experiments") or [])
    # Inject cortex_hypothesis entries from machine registry (W7b PR2)
    rows_in += _load_machine_registry_entries()
    out = []
    for e in rows_in:
        rec = {
            "id": e.get("id"), "name": e.get("name") or e.get("title"), "kind": e.get("kind"),
            "status": e.get("status") or "accruing", "priority": e.get("priority", "medium"),
            "what": e.get("what") or e.get("hypothesis"),
            "source": e.get("source") or e.get("pr"), "storage": e.get("storage", ""),
            "surfaced": e.get("surfaced"), "cadence": e.get("cadence"),
            "started": e.get("started") or e.get("registered_on"), "maturation": e.get("maturation"),
            "come_back_on": e.get("come_back_on"), "come_back_note": e.get("come_back_note"),
            "next_step": e.get("next_step"), "phase_hint": e.get("phase_hint") or _alt_phase_hint(e),
            "state": e.get("state") or _alt_state(e), "ready": False,
        }
        hook = _HOOKS.get(e.get("hook") or "")
        if hook:
            try:
                rec.update({k: v for k, v in hook(e).items() if v is not None})
            except Exception as ex:  # noqa: BLE001 — one bad reader never aborts the manifest
                log.warning("experiments_registry: hook failed for %s: %s", e.get("id"), ex)
        try:
            if rec.get("come_back_on"):
                rec["days_until"] = (date.fromisoformat(str(rec["come_back_on"])[:10]) - today).days
        except Exception:  # noqa: BLE001
            pass
        # comprehensive 'ready' = a track-record verdict advanced (set by the hook) OR the
        # come-back date has arrived — but not for already-concluded / parked / on-demand items.
        if not rec.get("ready"):
            du = rec.get("days_until")
            if (du is not None and du <= 0 and (rec.get("status") or "") not in _DONE
                    and (rec.get("kind") or "") not in _NO_AUTO_READY):
                rec["ready"] = True
        out.append(rec)

    ready = sum(1 for r in out if r.get("ready"))
    by_status: dict[str, int] = {}
    by_kind: dict[str, int] = {}
    for r in out:
        by_status[r.get("status") or "?"] = by_status.get(r.get("status") or "?", 0) + 1
        by_kind[r.get("kind") or "?"] = by_kind.get(r.get("kind") or "?", 0) + 1
    return {
        "schema": "experiments_registry.v1",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "as_of": today.isoformat(), "n": len(out), "ready_count": ready,
        "by_status": by_status, "by_kind": by_kind, "experiments": out,
        "note": ("Every running experiment & long-horizon data-collection accrual in the "
                 "codebase, with the date to come back for each next step. Track-records grade "
                 "the read's own calls against realized forward returns; nothing here sizes a "
                 "position. Seed: data/experiments/registry_seed.json (audited 2026-06-30)."),
    }


def _notify_newly_ready(prev_path, payload) -> None:
    """One-shot push to the configured telegram/discord channel when an experiment BECOMES
    ready (verdict advanced or come-back date arrived) that wasn't ready in the previous
    manifest. Fires once per transition; a no-op if notify.experiments_alerts is off or no
    channel/secret is configured (send_* self-skip). Never raises."""
    cfg = (config.load().get("notify") or {})
    if not cfg.get("experiments_alerts", True):
        return
    try:
        prev = {e.get("id"): e for e in (json.loads(prev_path.read_text()).get("experiments") or [])}
    except Exception:  # noqa: BLE001
        prev = {}
    newly = [e for e in payload["experiments"]
             if e.get("ready") and not (prev.get(e.get("id")) or {}).get("ready")]
    if not newly:
        return
    lines = ["🔔 <b>Experiment results ready</b> — come back for the next step:"]
    for e in newly[:8]:
        lines.append(f"• <b>{e.get('name')}</b>" + (f" — {e['phase_hint']}" if e.get("phase_hint") else ""))
        if e.get("next_step"):
            lines.append(f"   {str(e['next_step'])[:220]}")
    lines.append("→ admin Experiments tab: https://admin.mastermind-x.com")
    msg = "\n".join(lines)
    try:
        from scripts import notify
        notify.send_telegram(msg)
        notify.send_discord(msg)
        log.info("experiments alert: pinged %d newly-ready experiment(s)", len(newly))
    except Exception as e:  # noqa: BLE001
        log.warning("experiments alert send failed: %s", e)


def build(site=None) -> int:
    """Emit site/marketdata/experiments.json + push a ping on any newly-ready experiment.
    Additive, never fatal."""
    site = site or (config.ROOT / config.load()["storage"]["site_dir"])
    try:
        payload = compute()
    except Exception as e:  # noqa: BLE001
        log.error("experiments_registry compute failed: %s", e)
        return 0
    p = site / OUT
    p.parent.mkdir(parents=True, exist_ok=True)
    try:
        _notify_newly_ready(p, payload)   # diff against the PREVIOUS manifest before overwriting
    except Exception as e:  # noqa: BLE001 — a notify failure never blocks the manifest
        log.warning("experiments alert failed: %s", e)
    p.write_text(json.dumps(payload, separators=(",", ":"), ensure_ascii=False))
    log.info("experiments_registry: %d experiments (%d ready)", payload["n"], payload["ready_count"])
    return 1


def main() -> dict:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    return {"ok": bool(build())}


if __name__ == "__main__":
    main()
