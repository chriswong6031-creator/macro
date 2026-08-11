"""scripts/build_prophet.py — Prophet Origination Bridge + artifact publisher (W1).

Reads us_standouts.json, originates prophet.trade_plan/v1 envelopes,
runs the management confidence engine for every active plan, and writes:

    site/prophet/index.json          — every plan the management engine could state,
                                       with its state inline.  NOTE THE MISNOMER:
                                       `active_count` and `plans[]` include plans that
                                       have CLOSED in the forward ledger (16 of 74 on
                                       2026-08-03).  That population is fixed — several
                                       downstream consumers read it — so W1 added
                                       `open_count` (the live subset) and a per-plan
                                       `closed` flag instead of redefining it.  A closed
                                       plan's `pulse` says "closed · <outcome>" and never
                                       narrates its still-updating phase/human_state.
    site/prophet/plans/<ID>.json     — per-plan artifact
    site/prophet/states/<ID>.json    — per-state artifact
    site/prophet/showcase.json       — public landing teaser: DELAYED winning
                                       calls from the board ledger, never the
                                       live board (templates/index.html
                                       #f-prophet; also --showcase-only)
    data/prophet/ledger.jsonl        — forward outcome ledger (INITIALIZED here;
                                       nightly is the SOLE future advancer)

R2 publication is deliberately unavailable from this builder.  The daily workflow
first commits the exact build-owned delta under Git authority, then conditionally
publishes that accepted checkpoint with provenance metadata.

Usage
-----
    python -m scripts.build_prophet [--date YYYY-MM-DD]

Environment variables
---------------------
    THETADATA_STORE        Path to ThetaData EOD store root (optional)

SCHEDULING NOTE
---------------
NO daily.yml wiring in this PR.  Scheduling follows after operator reviews
the first output.  This script is safe to run manually at any time; it is
idempotent (duplicate plans are suppressed by ID).

AUTHORITY NOTE
--------------
All output artifacts carry authority_tier='display'.  No signal, score, or
escalation originates from an LLM in this pipeline.  The word "validated"
is forbidden in site artifacts (enforced by check_validated_claims.py).
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import os
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

# ── repo path ─────────────────────────────────────────────────────────────────
_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))

from engine import ledger_lane
from engine.prophet_bridge import (
    ADMITTED_STATUSES,
    LEGACY_N_CANDIDATES,
    QUARANTINE_FILENAME,
    QUARANTINE_REASON,
    QUARANTINE_SCHEMA,
    SELECTION_ERA,
    _panel_close_history,
    _PLAN_PRICE_DIRS,
    append_legacy_shadow,
    evaluate_entry_zone,
    legacy_shadow_rows,
    load_quarantined_ids,
    originate_plans,
    plan_clock_date,
    plan_key,
    refusal_receipts,
)
from engine.prophet_management import compute_management_state
from engine.prophet_integrity import (
    LEDGER_CORRECTIONS_FILENAME,
    PLAN_CORRECTIONS_FILENAME,
    apply_ledger_corrections,
    apply_plan_corrections,
    load_ledger_corrections,
    load_plan_corrections,
)
from engine.options_structure import validate_trade_plan

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

STANDOUTS_PATH = _REPO / "site" / "factordata" / "us_standouts.json"
SITE_PROPHET   = _REPO / "site" / "prophet"
PLANS_DIR      = SITE_PROPHET / "plans"
STATES_DIR     = SITE_PROPHET / "states"
INDEX_PATH     = SITE_PROPHET / "index.json"
LEDGER_DIR     = _REPO / "data" / "prophet"
LEDGER_PATH    = LEDGER_DIR / "ledger.jsonl"

R2_INDEX_KEY   = "prophet/index.json"

# R0.7 market-overlay inputs (compute_management_state macro_stance/futures_chg)
MARKET_STATE_PATH = _REPO / "data" / "market_state" / "latest.json"
YAHOO_DIR         = _REPO / "data" / "yahoo"


# ---------------------------------------------------------------------------
# R2 helpers (mirrors build_options_matrix.py exactly)
# ---------------------------------------------------------------------------

def _r2_client():
    """Build a boto3 S3 client for R2, or None if creds are absent."""
    ep = os.environ.get("R2_ENDPOINT")
    ak = os.environ.get("R2_ACCESS_KEY_ID")
    sk = os.environ.get("R2_SECRET_ACCESS_KEY")
    if not (ep and ak and sk):
        return None
    try:
        import boto3
        from botocore.config import Config
        kw = dict(
            region_name="auto",
            signature_version="s3v4",
            max_pool_connections=16,
            retries={"max_attempts": 3, "mode": "standard"},
        )
        try:
            cfg = Config(**kw,
                         request_checksum_calculation="when_required",
                         response_checksum_validation="when_required")
        except TypeError:
            cfg = Config(**kw)
        return boto3.client(
            "s3",
            endpoint_url=ep,
            aws_access_key_id=ak,
            aws_secret_access_key=sk,
            config=cfg,
        )
    except Exception as e:  # noqa: BLE001
        log.warning("build_prophet: R2 client build failed: %s", e)
        return None


def _upload_r2(s3, bucket: str, local_path: Path, r2_key: str) -> bool:
    """Upload local file to R2. Returns True on success."""
    try:
        s3.upload_file(
            str(local_path),
            bucket,
            r2_key,
            ExtraArgs={"ContentType": "application/json"},
        )
        log.info("build_prophet: R2 upload ok → %s", r2_key)
        return True
    except Exception as e:  # noqa: BLE001
        log.warning("build_prophet: R2 upload failed for %s: %s", r2_key, e)
        return False


# ---------------------------------------------------------------------------
# JSON helpers
# ---------------------------------------------------------------------------

def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, allow_nan=False, default=str, indent=2),
        encoding="utf-8",
    )


def _read_json(path: Path) -> dict | None:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            log.warning("build_prophet: failed to read %s: %s", path, e)
    return None


# ---------------------------------------------------------------------------
# Landing showcase slice — public teaser payload for the marketing landing
# (templates/index.html #f-prophet). DELAYED WINNERS, never the live board
# (operator order 2026-07-24: the current board is paid product — the free
# teaser shows winning calls from ~2 weeks back, labelled as exactly that).
# Source: data/us_board_ledger (grade_us_board.py) — the latest board whose
# 10-session grades have fully matured AND whose snapshot is stored; winners
# only (ret > 0), ranked by return, each card stamped with its since_pct.
# Card derivation MIRRORS the pv_card cx construction in
# templates/dashboard.html.j2 (verb / stage / zone_kind / flags) — keep the two
# in sync when the board mapping changes.
# ---------------------------------------------------------------------------

SHOWCASE_PATH = SITE_PROPHET / "showcase.json"
SHOWCASE_LIMIT = 12
SHOWCASE_HORIZON = 10       # sessions after next-bar entry (grader convention)
SHOWCASE_MIN_WINNERS = 6    # fewer than this → keep the previous payload

BOARD_LEDGER_DIR = _REPO / "data" / "us_board_ledger"
GRADES_PATH      = BOARD_LEDGER_DIR / "retro_grades.parquet"
SNAPSHOTS_PATH   = BOARD_LEDGER_DIR / "snapshots.jsonl"

# EN → ZH sector names, byte-matched to the rendered board (site/us_stocks.html
# pv-ind l-zh spans) so the landing teaser and the board never disagree.
_SECTOR_ZH = {
    "Communication Services": "通信服务",
    "Consumer Discretionary": "可选消费",
    "Consumer Staples": "必需消费",
    "Energy": "能源",
    "Financials": "金融",
    "Health Care": "医疗保健",
    "Industrials": "工业",
    "Information Technology": "信息技术",
    "Materials": "原材料",
    "Real Estate": "房地产",
    "Utilities": "公用事业",
}

_STAGE_BY_LANE = {"bottoming": 1, "recovery": 2, "continuation": 3, "trend": 4}


def derive_showcase_card(row: dict) -> dict | None:
    """One landing card from one us_standouts.buy row (None = not showable).

    Mirrors templates/dashboard.html.j2 pv_card derivation exactly.
    """
    tk = row.get("ticker")
    price = row.get("price")
    spark = row.get("spark_svg")
    if not tk or price is None or not spark:
        return None

    es = row.get("entry_signal") or {}
    c = row.get("conviction") or {}
    st = es.get("status")

    if st in ("buy_now", "partial"):
        verb = "buy"
    elif st in ("buy_soon", "await_confluence"):
        verb = "near"
    elif st in ("hold", "topping"):
        verb = "hold"
    elif st in ("exit", "avoid"):
        verb = "avoid"
    elif st:
        verb = "wait"
    else:
        d = row.get("dir")
        verb = "near" if d == "up" else ("avoid" if d == "down" else "wait")

    stage = _STAGE_BY_LANE.get(row.get("lane") or "", 0)

    # ── caution flags (same folds as the board card) ─────────────────────────
    flags: list[list[str]] = []
    cautions = c.get("cautions") or []
    cautions_zh = c.get("cautions_zh") or []
    for i, cau in enumerate(cautions):
        if cau == "accounting watch":
            continue
        zh = cautions_zh[i] if i < len(cautions_zh) else cau
        flags.append([cau, zh])
    vs = c.get("vol_squeeze") or {}
    vs_fired = vs.get("state") in ("FIRED_UP", "EXPANSION")
    entry_ok = st not in ("extended", "topping", "exit", "avoid", "blocked")
    if (vs_fired or row.get("alpha_entry") == "extended") and entry_ok:
        flags.append(["Already moving — don't chase above the zone",
                      "已在异动 — 勿在买区上方追高"])
    ext_z = row.get("ext_z")
    if ext_z is not None and ext_z > 2.0:
        flags.append([f"Extended {ext_z:.1f}σ over trend — chase risk",
                      f"高于趋势{ext_z:.1f}σ — 追高风险"])
    if row.get("antichase_shadow_blocked"):
        flags.append(["Anti-chase watch — parabolic tail", "反追涨观察 — 抛物线尾部"])
    esoon = row.get("earnings_soon") or {}
    if esoon.get("days_to") is not None:
        flags.append([esoon.get("chip_en") or f"Earnings in {esoon['days_to']}d",
                      esoon.get("chip_zh") or f"财报还有{esoon['days_to']}天"])
    if row.get("sector_stance") in ("Reduce", "Cautious"):
        flags.append([
            f"Sector stance: {row['sector_stance']} — single-stock trigger, not a sector call",
            f"板块态度：{row.get('sector_stance_zh') or row['sector_stance']} — 个股信号，非板块判断",
        ])
    if (row.get("hold") or {}).get("state") == "broken":
        flags.append(["Base broken — thesis void level hit", "筑底破位 — 失效价已触发"])
    # DELIBERATE OMISSION (OEU M-PRO): the live board's options flags (call wall
    # overhead / options priced for a bigger move) are NOT folded here. This showcase
    # replays a snapshot that matured ~2 weeks ago; today's dealer positioning and
    # today's IV percentile describe a different day, and stamping them onto an old
    # card would misdate the claim. If options context is ever wanted here it must be
    # read from the snapshot's own date, not from the live store.

    # ── zone footer ──────────────────────────────────────────────────────────
    bz = es.get("buy_zone") or {}
    if bz.get("high") is not None:
        zone_kind = ("readd" if verb == "hold"
                     else "active" if verb in ("buy", "near") else "muted")
        zone_lo = f"${bz['low']:.2f}" if bz.get("low") is not None else None
        zone_hi = f"${bz['high']:.2f}"
    else:
        zone_kind = "confirm" if verb in ("wait", "near") else "none"
        zone_lo = zone_hi = None

    edge = c.get("score_edge")
    sec = row.get("sector") or ""
    return {
        "tk": tk,
        "name": row.get("name") or tk,
        "sec": sec,
        "sec_zh": _SECTOR_ZH.get(sec, sec),
        "price_txt": f"${price:.2f}",
        "verb": verb,
        "edge": int(edge) if edge is not None else None,
        "stage": stage,
        "zone_kind": zone_kind,
        "zone_lo": zone_lo,
        "zone_hi": zone_hi,
        "date": (row.get("signal") or {}).get("asof"),
        "flags": flags,
        "triage": bool(edge is not None and edge >= 80 and st in ("buy_now", "partial")),
        "spark": spark,
    }


def _load_board_snapshots(path: Path) -> dict:
    """as_of → board snapshot dict from the append-only JSONL. Fail-soft {}."""
    snaps: dict = {}
    try:
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except Exception:  # noqa: BLE001 — one bad line never kills the file
                    continue
                if d.get("as_of"):
                    snaps[d["as_of"]] = d
    except Exception as e:  # noqa: BLE001
        log.warning("build_prophet: showcase snapshots unreadable: %s", e)
    return snaps


def build_showcase_payload(grades, snapshots: dict,
                           limit: int = SHOWCASE_LIMIT,
                           horizon: int = SHOWCASE_HORIZON,
                           min_winners: int = SHOWCASE_MIN_WINNERS) -> dict | None:
    """Delayed-winners slice: winning calls from the freshest fully-graded board.

    Walks board dates newest-first; a board qualifies when its buy-lane rows
    have matured `horizon`-session grades (retro_grades) AND its snapshot is
    stored (card fields + spark). Winners only (ret > 0), ranked by return,
    capped at `limit`, each stamped with `since_pct`. Returns None when no
    board yields >= min_winners — callers keep the previous payload then.
    Grade semantics inherit grade_us_board.py honesty conventions: entry =
    next session's close after the board date; dividend-adjusted total-return
    closes; survivorship handled via the dead-name store.
    """
    df = grades[(grades["lane"] == "buy")
                & (grades["horizon"] == horizon)
                & grades["ret"].notna()]
    for as_of in sorted(df["as_of"].unique(), reverse=True):
        snap = snapshots.get(as_of)
        if not snap:
            continue
        rows_by_tk = {r.get("ticker"): r for r in (snap.get("buy") or [])}
        winners = df[(df["as_of"] == as_of) & (df["ret"] > 0)] \
            .sort_values("ret", ascending=False)
        cards: list[dict] = []
        for rec in winners.itertuples():
            row = rows_by_tk.get(rec.ticker)
            if not row:
                continue
            card = derive_showcase_card(row)
            if card is None:
                continue
            card["since_pct"] = round(float(rec.ret) * 100, 1)
            cards.append(card)
            if len(cards) >= limit:
                break
        if len(cards) >= min_winners:
            return {
                "schema": "prophet.showcase/v2",
                "kind": "delayed_winners",
                "as_of": as_of,
                "window_sessions": horizon,
                "authority_tier": "display",
                "count": len(cards),
                "note": (
                    f"DISPLAY-ONLY, DELAYED. Winning calls from the board of {as_of},"
                    f" graded at {horizon} sessions from the next session's close"
                    " after the call (grade_us_board conventions, survivorship-"
                    "adjusted). Selected because they worked; the live board ships"
                    " nightly behind registration and includes wins and losses."
                    " No signal originates here."
                ),
                "cards": cards,
            }
    return None


def write_showcase(grades_path: Path = GRADES_PATH,
                   snapshots_path: Path = SNAPSHOTS_PATH,
                   out_path: Path = SHOWCASE_PATH) -> dict | None:
    """Board ledger → landing showcase payload. Fail-soft: on any miss the
    PREVIOUS showcase.json is kept (a stale winners wall beats an empty one,
    and the live board is never the fallback)."""
    payload = None
    try:
        import pandas as pd  # noqa: PLC0415
        grades = pd.read_parquet(grades_path)
        payload = build_showcase_payload(grades, _load_board_snapshots(snapshots_path))
    except Exception as e:  # noqa: BLE001
        log.warning("build_prophet: showcase build failed: %s", e)
    if payload is None:
        log.warning("build_prophet: showcase NOT refreshed — keeping previous %s",
                    out_path)
        return None
    _write_json(out_path, payload)
    log.info("build_prophet: wrote showcase.json (%d winners, board_as_of=%s)",
             payload["count"], payload["as_of"])
    return payload


# ---------------------------------------------------------------------------
# Ledger
# ---------------------------------------------------------------------------

LEDGER_SCHEMA_COMMENT = (
    "# prophet ledger row schema — see research/PROPHET_LEDGER_SCHEMA.md\n"
    "# Fields: schema, id, asset, direction, formation_date, signal_date,\n"
    "#         confirmed_date, observed_date, signal_tier, signal_date_basis,\n"
    "#         signal_provisional, source_marker_date,\n"
    "#         price_basis_date, entry_date, recorded_at, close_date,\n"
    "#         outcome (T1_HIT|T2_HIT|INVALIDATED|EXPIRED|CLOSED_EARLY|NO_ENTRY),\n"
    "#         stock_result_pct, option_result_pct (null when no rec),\n"
    "#         days_held, plan_adherence, asof\n"
    "# NO_ENTRY = the plan's trigger never confirmed inside the horizon. Its\n"
    "#            stock_result_pct is null and it belongs in NEITHER side of a rate.\n"
    "# Nightly is the SOLE advancer of this ledger.\n"
)

# Outcomes that resolve a POSITION. NO_ENTRY is deliberately absent: a trade that
# never opened is not a win and not a loss, so it belongs in neither the numerator
# nor the denominator of any rate computed over this file.
RESOLVED_OUTCOMES = ("T1_HIT", "T2_HIT", "INVALIDATED", "EXPIRED", "CLOSED_EARLY")

QUARANTINE_PATH = LEDGER_DIR / QUARANTINE_FILENAME
# The day the pre-origination-clock defect was found and the poisoned rows listed.
QUARANTINE_DATE = "2026-08-06"
QUARANTINE_NOTE_EN = (
    "{n} early rows quarantined {date} — graded on a clock that predated the plan"
)
QUARANTINE_NOTE_ZH = "{n} 条早期记录于 {date} 隔离 — 结算所用的时间早于计划本身"


def _initialize_ledger() -> None:
    """Create ledger.jsonl + header comment if it doesn't exist."""
    LEDGER_DIR.mkdir(parents=True, exist_ok=True)
    if not LEDGER_PATH.exists():
        LEDGER_PATH.write_text(LEDGER_SCHEMA_COMMENT, encoding="utf-8")
        log.info("build_prophet: initialized empty ledger at %s", LEDGER_PATH)
    else:
        log.info("build_prophet: ledger exists at %s; not overwriting", LEDGER_PATH)


# ---------------------------------------------------------------------------
# Ledger advancement (nightly is the SOLE advancer)
# ---------------------------------------------------------------------------

def _load_closed_outcomes() -> dict[str, str]:
    """``{plan_id: outcome}`` for every plan that has a forward-ledger row.

    ONE read of ledger.jsonl serving both W1 consumers: the re-origination block
    (which needs only the id set, via ``_load_closed_ids`` below) and the index's
    ``closed`` flag + closed-shaped pulse (which need the outcome word).  Lines
    beginning with '#' are header comments (skipped); an unparseable line is
    skipped rather than fatal, exactly as before.

    First-wins on a duplicate id: ``_determine_outcome`` is first-trigger-closes,
    so if a second row for one plan ever appeared, the FIRST is the real close.
    Missing/blank ``outcome`` maps to "" — the plan is still closed, its outcome
    is merely unnamed, and the pulse degrades to a bare "closed".
    """
    outcomes: dict[str, str] = {}
    if not LEDGER_PATH.exists():
        return outcomes
    for line in LEDGER_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            row = json.loads(line)
            plan_id = row.get("id")
            if plan_id:
                outcomes.setdefault(str(plan_id), str(row.get("outcome") or ""))
        except Exception:
            pass
    return outcomes


def _load_closed_ids() -> set[str]:
    """Return plan IDs that already have a ledger row (idempotency guard)."""
    return set(_load_closed_outcomes())


def _load_ledger_rows() -> list[dict]:
    """Every parsable data row of ledger.jsonl, in file order (header lines skipped)."""
    rows: list[dict] = []
    if not LEDGER_PATH.exists():
        return rows
    for line in LEDGER_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            pass
    return rows


def derive_quarantine(ledger_rows: list[dict], plans: dict[str, dict]) -> list[dict]:
    """Ledger rows whose close_date STRICTLY PREDATES their plan's origination date.

    DERIVED, never enumerated.  The poisoned set is defined by the arithmetic — a row
    graded on bars the plan was not alive for — so it recomputes from whatever the
    ledger and the plans say, and a hand-typed id list cannot drift away from it.  On
    the 2026-08-05 artifacts this returns exactly 9 of 16 rows; that count is an
    OBSERVATION, not an input.

    Origination date = the plan's ``asof`` (the run that created it).  Deliberately not
    ``entry_date``: a plan originated before the P1 fix has no ``entry_date``, and the
    whole point is to judge the OLD rows.  A plan that cannot be located, or a row with
    no close_date, is NOT quarantined — silence is not evidence of poison.
    """
    out: list[dict] = []
    for row in ledger_rows:
        plan_id = str(row.get("id") or "")
        plan = plans.get(plan_id)
        if not plan_id or not plan:
            continue
        origination = str(plan.get("asof") or "")[:10]
        close_date = str(row.get("close_date") or "")[:10]
        if not origination or not close_date:
            continue
        try:
            poisoned = date.fromisoformat(close_date) < date.fromisoformat(origination)
        except ValueError:
            continue
        if poisoned:
            out.append({
                "id": plan_id,
                "reason": QUARANTINE_REASON,
                "quarantined": QUARANTINE_DATE,
                "close_date": close_date,
                "origination_date": origination,
            })
    return out


def write_quarantine(
    ledger_rows: list[dict],
    plans: dict[str, dict],
    correction_quarantines: dict[str, str] | None = None,
) -> dict:
    """Derive + persist ``data/prophet/ledger_quarantine.json``; return the payload.

    The ledger itself is NEVER touched — it is append-only, and a record you can edit
    is not a record.  This file is the exclusion list every RECORD SUMMARY reads
    (``engine.prophet_bridge.load_quarantined_ids``).  Per-plan closure facts must not
    read it: those plans really did close; it is only the NUMBER that is unusable.
    """
    rows = derive_quarantine(ledger_rows, plans)
    by_id = {str(row["id"]): row for row in rows}
    for plan_id, reason in sorted((correction_quarantines or {}).items()):
        if plan_id in by_id:
            by_id[plan_id]["sources"] = ["derived_chronology", "ledger_correction"]
            by_id[plan_id]["correction_reason"] = reason
            continue
        ledger_row = next(
            (row for row in ledger_rows if str(row.get("id") or "") == plan_id), {}
        )
        plan = plans.get(plan_id, {})
        row = {
            "id": plan_id,
            "reason": reason,
            "quarantined": QUARANTINE_DATE,
            "close_date": ledger_row.get("close_date"),
            "origination_date": plan.get("asof"),
            "sources": ["ledger_correction"],
        }
        rows.append(row)
        by_id[plan_id] = row
    payload = {
        "schema": QUARANTINE_SCHEMA,
        "quarantined_on": QUARANTINE_DATE,
        "count": len(rows),
        "rule": (
            "a forward-ledger row whose close_date strictly predates the plan's own "
            "origination date (plan.asof) — the outcome was scanned from the base "
            "formation anchor, so it was graded on bars the plan was never live for"
        ),
        "effect": (
            "the row STAYS in ledger.jsonl (append-only); every reader that summarises "
            "the record excludes these ids from both numerator and denominator"
        ),
        "note": QUARANTINE_NOTE_EN.format(n=len(rows), date=QUARANTINE_DATE),
        "note_zh": QUARANTINE_NOTE_ZH.format(n=len(rows), date=QUARANTINE_DATE),
        "quarantined": rows,
    }
    # Resolved from LEDGER_DIR at call time, not from the module constant, so a test
    # that redirects the ledger to a tmp_path redirects its quarantine file with it.
    _write_json(LEDGER_DIR / QUARANTINE_FILENAME, payload)
    log.info("build_prophet: quarantine — %d ledger row(s) excluded from summaries: %s",
             len(rows), ", ".join(r["id"] for r in rows) or "none")
    return payload


def record_summary(ledger_rows: list[dict], quarantined: set[str]) -> dict:
    """The honest closed-plan record: quarantined rows out, NO_ENTRY out of the rate.

    Two exclusions, for two different reasons, both disclosed as counts:
      * quarantined — graded on a clock that predated the plan (the number is wrong).
      * NO_ENTRY    — the trigger never confirmed, so no position ever existed.  It is
        neither a win nor a loss; putting it in the denominator would report a losing
        trade the plan explicitly told the reader not to take.
    """
    kept = [r for r in ledger_rows if str(r.get("id") or "") not in quarantined]
    resolved = [r for r in kept if str(r.get("outcome") or "") in RESOLVED_OUTCOMES]
    scored = [r for r in resolved
              if isinstance(r.get("stock_result_pct"), (int, float))
              and not isinstance(r.get("stock_result_pct"), bool)]
    wins = [r for r in scored if float(r["stock_result_pct"]) > 0]
    n = len(scored)
    return {
        "n_rows_total": len(ledger_rows),
        "n_quarantined": len(ledger_rows) - len(kept),
        "n_no_entry": sum(1 for r in kept if str(r.get("outcome") or "") == "NO_ENTRY"),
        "n_scored": n,
        "n_wins": len(wins),
        "win_rate": round(len(wins) / n, 4) if n else None,
        "avg_result_pct": (round(sum(float(r["stock_result_pct"]) for r in scored) / n, 4)
                           if n else None),
    }


def _effective_index_entries(
    entries: list[dict], quarantined_ids: set[str]
) -> list[dict]:
    """Public/Brain/marketing projection; raw plan/state evidence stays untouched."""
    return [
        row for row in entries
        if str(row.get("id") or "") not in quarantined_ids
    ]


def _append_ledger_row(row: dict) -> None:
    """Append one JSON row to ledger.jsonl (non-atomic; nightly-only caller)."""
    LEDGER_DIR.mkdir(parents=True, exist_ok=True)
    with LEDGER_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, allow_nan=False, default=str) + "\n")


def _determine_outcome(
    plan: dict,
    price_history_pit: "pd.DataFrame",
    asof: str,
) -> tuple[str | None, float | None, float | None, int | None]:
    """Check whether a plan has hit a close trigger as of asof.

    Returns (outcome, stock_result_pct, option_result_pct, days_held) or
    (None, None, None, None) when the plan is still open.

    THE CLOCK IS ``entry_date``, NOT ``signal_date`` (P1, 2026-08-06)
    ----------------------------------------------------------------
    Legacy ``signal_date`` values were formation anchors and could precede the plan's
    publication by months; tier-aware values are causal T1/T2 event closes. Neither is
    the entry-price/grading clock. Scanning from the legacy alias graded plans on bars
    that PREDATED them: every EXPIRED row in the shipped ledger and both winners closed
    before their plan existed, and 14 plans were born already past horizon. The scan
    start AND horizon expiry now both read :func:`plan_clock_date` — the evidenced
    ``price_basis_date``/``entry_date`` whose close supplied ``entry``. Plan identity is
    separately frozen by ``formation_date``.

    THE TRIGGER IS READ (P2, 2026-08-06)
    ------------------------------------
    The plan's own copy says "No position until trigger is confirmed", and this
    function used to ignore ``plan["trigger"]`` entirely — 5 of 16 shipped rows
    booked full P&L on positions the plan never told a reader to take.  The
    outcome scan now starts at the first close at-or-through the trigger (>= for
    BULL, <= for BEAR) at or after the clock start.  A plan whose trigger is never
    confirmed inside the horizon closes ``NO_ENTRY`` with ``stock_result_pct=None``
    and is excluded from BOTH the numerator and the denominator wherever rates are
    computed — it is not a loss, it is a trade that never happened.
    ``trigger is None`` means "no trigger condition" and is treated as confirmed on
    the clock start (legacy plans and fixtures predate the field).

    Close triggers (in priority order), scanned from the CONFIRMATION bar onward:
      1. INVALIDATED   — any close <= invalidation (BULL)
      2. T2_HIT        — any close >= T2
      3. T1_HIT        — any close >= T1 (and T2 not yet hit)
      4. EXPIRED       — days since the clock start >= horizon_days
      5. NO_ENTRY      — horizon reached with the trigger never confirmed

    DESIGN (first-trigger-closes): the loop breaks on the FIRST trigger hit and
    records that outcome permanently.  A plan that touches T1 then later T2 is
    recorded as T1_HIT only.  T2_HIT fires only when the price clears T2 without
    a prior close >= T1 (i.e., a gap day that skips T1).  This is intentional:
    the ledger records first-observable-close outcomes, not eventual maximum reach.
    Ledger consumers must not read T2_HIT frequency as "ever reached T2" — it
    reflects "cleared T2 in a single close without a prior T1 close."

    PIT correctness: `after = price_history_pit[index > clock_ts]` uses strict
    greater-than so the entry day's own close is excluded (it IS the entry price).
    If the PIT frame ends before entry_date + horizon_days, the plan stays open
    indefinitely — this is correct behaviour, not a missed-expiry bug.

    Stock result = (close_price_on_close_date / entry - 1) * 100 (%).  The
    entry-fill convention for a TRIGGERED plan is unchanged (pre-registered
    territory): P&L is still measured from the plan's stated ``entry``.
    Option result = null (premium-mark data not available in this pipeline).

    OURS (nightly-only; PIT-safe): we scan daily closes on the price_history_pit
    frame (already filtered to <= asof by the caller).  The first day a close
    crosses a trigger is the close_date for that trigger.  This is conservative
    (may miss intraday crosses) and documented here as a display-tier limitation.
    """
    import pandas as pd  # noqa: PLC0415

    direction = plan.get("direction", "BULL")
    entry = plan.get("entry")
    invalidation = plan.get("invalidation")
    targets = plan.get("targets", [])
    t1 = targets[0] if len(targets) > 0 else None
    t2 = targets[1] if len(targets) > 1 else None
    horizon_days = plan.get("horizon_days", 45)
    trigger = plan.get("trigger")
    clock_date_str = plan_clock_date(plan) or plan.get("_signal_date")

    if entry is None or clock_date_str is None:
        return None, None, None, None

    try:
        sig_ts = pd.Timestamp(clock_date_str)
    except Exception:
        return None, None, None, None

    # Filter to rows strictly AFTER the clock start (entry day's close IS the entry)
    after = price_history_pit[price_history_pit.index > sig_ts]
    if after.empty:
        return None, None, None, None

    close_col = None
    for col in ["close", "Close", "adj_close", "Adj Close"]:
        if col in after.columns:
            close_col = col
            break
    if close_col is None:
        return None, None, None, None

    closes = after[close_col].dropna()
    if closes.empty:
        return None, None, None, None

    # Scan chronologically for first trigger hit
    close_date_str: str | None = None
    outcome: str | None = None
    close_price: float | None = None

    # P2: no position exists until the trigger prints.  `None` = no trigger condition
    # on this plan (legacy/fixture), which is confirmed from the clock start.
    triggered = trigger is None

    for ts, px in closes.items():
        px = float(px)
        days = (ts - sig_ts).days

        if not triggered:
            # Confirmation is INCLUSIVE of the level: the plan publishes "above
            # <trigger>" as the level to act on, so trading AT it is acting on the plan.
            if direction == "BULL":
                triggered = px >= float(trigger)
            else:
                triggered = px <= float(trigger)
            if not triggered:
                # Horizon can still expire while waiting — that is NO_ENTRY, not EXPIRED.
                if days >= horizon_days:
                    outcome = "NO_ENTRY"
                    close_date_str = ts.date().isoformat()
                    close_price = None
                    break
                continue
            # Fall through: the confirmation bar is itself the first scanned bar.

        if direction == "BULL":
            if invalidation is not None and px <= invalidation:
                outcome = "INVALIDATED"
                close_date_str = ts.date().isoformat()
                close_price = px
                break
            if t2 is not None and px >= t2:
                outcome = "T2_HIT"
                close_date_str = ts.date().isoformat()
                close_price = px
                break
            if t1 is not None and px >= t1:
                outcome = "T1_HIT"
                close_date_str = ts.date().isoformat()
                close_price = px
                break
        else:  # BEAR
            if invalidation is not None and px >= invalidation:
                outcome = "INVALIDATED"
                close_date_str = ts.date().isoformat()
                close_price = px
                break
            if t2 is not None and px <= t2:
                outcome = "T2_HIT"
                close_date_str = ts.date().isoformat()
                close_price = px
                break
            if t1 is not None and px <= t1:
                outcome = "T1_HIT"
                close_date_str = ts.date().isoformat()
                close_price = px
                break

        if days >= horizon_days:
            outcome = "EXPIRED"
            close_date_str = ts.date().isoformat()
            close_price = px
            break

    if outcome is None:
        return None, None, None, None

    # Stock result (signed %)
    stock_result_pct: float | None = None
    if close_price is not None and entry and entry > 0:
        raw = (close_price / entry - 1.0) * 100.0
        stock_result_pct = round(raw, 4)

    # Option result: not computable from EOD chain snapshots in this pipeline
    option_result_pct: float | None = None

    # Days held
    days_held: int | None = None
    if close_date_str:
        try:
            days_held = (date.fromisoformat(close_date_str) - sig_ts.date()).days
        except Exception:
            pass

    return outcome, stock_result_pct, option_result_pct, days_held


def advance_ledger(
    all_plans: dict[str, dict],
    asof: str,
) -> list[dict]:
    """Evaluate every plan for close triggers and append ledger rows for newly-closed plans.

    Idempotent: plans already recorded in the ledger (by ID) are skipped.
    Nightly is the SOLE caller of this function (enforced by the call site in main()).

    Returns list of newly-appended rows (for logging / tests).
    """
    import pandas as pd  # noqa: PLC0415

    closed_ids = _load_closed_ids()
    new_rows: list[dict] = []

    for plan_id, plan in all_plans.items():
        if plan_id in closed_ids:
            continue  # idempotency: already in ledger

        ticker = plan.get("asset", "")
        ph = _load_price_history_for_management(ticker)
        if ph is None:
            continue

        # PIT filter
        asof_ts = pd.Timestamp(asof)
        ph_pit = ph[ph.index <= asof_ts]
        if ph_pit.empty:
            continue

        outcome, stock_result_pct, option_result_pct, days_held = _determine_outcome(
            plan, ph_pit, asof
        )
        if outcome is None:
            continue  # plan still open

        # close_date = the CLOCK start + days_held.  `days_held` is measured from the
        # price-basis clock inside _determine_outcome. The old implementation added it
        # to the legacy signal/formation alias (up to 152 days earlier), producing close
        # dates that predated the plan; a tier-native signal event is also not a fill.
        signal_date_str = plan.get("signal_date") or plan.get("_signal_date")
        clock_date_str = plan_clock_date(plan) or signal_date_str
        close_date_str: str | None = None
        if clock_date_str and days_held is not None:
            try:
                from datetime import timedelta  # noqa: PLC0415
                close_date = (date.fromisoformat(str(clock_date_str)[:10])
                              + timedelta(days=days_held))
                close_date_str = close_date.isoformat()
            except Exception:
                close_date_str = asof

        row: dict = {
            "schema": "prophet.ledger/v1",
            "id": plan_id,
            "asset": plan.get("asset"),
            "direction": plan.get("direction"),
            # Additive temporal provenance for newly closed rows.  Existing ledger
            # rows are append-only and are never rewritten to manufacture these fields.
            "formation_date": plan.get("formation_date"),
            "signal_date": signal_date_str,
            "confirmed_date": plan.get("confirmed_date"),
            "observed_date": plan.get("observed_date"),
            "signal_tier": plan.get("signal_tier"),
            "signal_date_basis": plan.get("signal_date_basis"),
            "signal_provisional": plan.get("signal_provisional"),
            "source_marker_date": plan.get("source_marker_date"),
            "price_basis_date": plan.get("price_basis_date"),
            # The date the horizon/outcome scan actually ran from — kept on the row so a
            # reader can tell a formation anchor from an entry without opening the plan.
            "entry_date": clock_date_str,
            "recorded_at": plan.get("recorded_at"),
            "close_date": close_date_str,
            "outcome": outcome,
            "stock_result_pct": stock_result_pct,
            "option_result_pct": option_result_pct,
            "days_held": days_held,
            "plan_adherence": (
                f"nightly-auto: outcome={outcome} asset={plan.get('asset')} "
                f"entry={plan.get('entry')} inval={plan.get('invalidation')} "
                f"T1={plan.get('targets', [None])[0] if plan.get('targets') else None}"
            ),
            "asof": asof,
        }
        _append_ledger_row(row)
        new_rows.append(row)
        log.info(
            "build_prophet: ledger close → %s outcome=%s stock_result=%.2f%% days=%s",
            plan_id, outcome, stock_result_pct or 0.0, days_held,
        )

    if new_rows:
        log.info("build_prophet: advanced ledger — %d new rows", len(new_rows))
    else:
        log.info("build_prophet: ledger advancement: no plans closed this run")

    return new_rows


# ---------------------------------------------------------------------------
# Existing plan loader
# ---------------------------------------------------------------------------

def _load_existing_plans() -> dict[str, dict]:
    """Load all existing plan JSON files. Returns {id: plan_dict}."""
    plans: dict[str, dict] = {}
    if not PLANS_DIR.exists():
        return plans
    for p in PLANS_DIR.glob("*.json"):
        data = _read_json(p)
        if data and data.get("schema") == "prophet.trade_plan/v1":
            plans[data["id"]] = data
    return plans


def _load_existing_state(plan_id: str) -> dict | None:
    """Load existing management state for a plan (for prev_state EMA chain)."""
    state_path = STATES_DIR / f"{plan_id}.json"
    return _read_json(state_path)


def open_plan_keys(plans: dict[str, dict], closed_ids: set[str]) -> set[str]:
    """``<TICKER>-<DIRECTION>`` keys that still have an OPEN plan (W1 intake repair).

    "Closed" is exactly what the forward ledger already says: ``advance_ledger`` appends
    one row the first time a plan hits INVALIDATED / T1_HIT / T2_HIT / EXPIRED, and
    ``_load_closed_ids`` reads that file back.  No new store is introduced — this reads
    the plans dict and the ledger this pipeline already loads, and a plan that closes
    frees its ticker+direction slot for a fresh origination.

    Timing (deliberate, one-night lag): origination runs BEFORE this run's
    ``advance_ledger`` call, so a plan whose exit is being written tonight still blocks
    tonight and frees the slot tomorrow.  The lag errs toward NOT re-originating a name
    whose close is in flight, which is the conservative direction.

    Cross-check on the 2026-08-03 artifacts: every plan whose management state reads
    ``phase == "invalidated"`` (QCOM ×2, MS, COIN) already carries a ledger row, so the
    ledger is a sufficient closure authority here and a second, divergeable one is not
    introduced.
    """
    keys: set[str] = set()
    for plan_id, plan in plans.items():
        if plan_id in closed_ids:
            continue
        asset = plan.get("asset")
        direction = plan.get("direction")
        if not asset or not direction:
            continue
        keys.add(plan_key(str(asset), str(direction)))
    return keys


# ---------------------------------------------------------------------------
# Index hygiene (W1) — aging + pulse. DATA ONLY; W2 renders it.
# ---------------------------------------------------------------------------
# The index lists every plan the management engine could state, with no sense of
# time: a 3-day-old thesis and a 138-day-old one read identically, which is how a
# live PLTR plan stayed invisible to the operator (masterplan §1.3, PLTR case).
# These fields add the age, and one plain-word line per plan.  Nothing is removed
# and nothing is re-ordered — the graded population is fenced (G0.4).

AGE_BUCKET_KEYS = ("le_7d", "d8_21d", "gt_21d", "unknown")

# Phase → plain word.  Raw phase slugs (``pre_trigger``, ``triggered_pre_t1``) are
# banned from any string a surface may print (glance-tier word law), so an UNMAPPED
# phase drops the leg rather than leaking the slug.
_PHASE_WORD: dict[str, tuple[str, str]] = {
    "pre_trigger":         ("pre-trigger", "触发前"),
    "triggered_pre_t1":    ("triggered",   "已触发"),
    "at_t1":               ("at T1",       "已达 T1"),
    "between_t1_t2":       ("past T1",     "T1 之上"),
    "post_t1_failed_hold": ("giveback",    "回吐"),
    "at_t2":               ("at T2",       "已达 T2"),
    "post_t2":             ("past T2",     "T2 之上"),
    "overtime":            ("overtime",    "超时"),
    "invalidated":         ("invalidated", "已失效"),
}

# Forward-ledger outcome → plain word.  `T1_HIT` / `INVALIDATED` are ledger enum
# slugs, not language; a closed plan's pulse says what happened in words a reader
# already knows.  An unmapped/blank outcome degrades to a bare "closed" — the plan
# is still unambiguously finished, which is the load-bearing half.
_OUTCOME_WORD: dict[str, tuple[str, str]] = {
    "T1_HIT":      ("hit first target",  "达到首个目标"),
    "T2_HIT":      ("hit second target", "达到第二目标"),
    "INVALIDATED": ("stopped out",       "止损离场"),
    "EXPIRED":     ("timed out",         "到期未达标"),
}

# human_state strings emitted by engine/prophet_management._human_state.  An
# unmapped value drops from BOTH halves so the pair can never desync into an
# EN-only chip (house bilingual law).
_HUMAN_STATE_ZH: dict[str, str] = {
    "Awaiting Trigger":          "等待触发",
    "Approaching Trigger":       "接近触发",
    "Advancing Cleanly":         "顺利推进",
    "On Track":                  "按计划推进",
    "Needs Follow-Through":      "需要跟进确认",
    "Stalling":                  "停滞",
    "T1 Hit — Holding":          "已达 T1 — 持有",
    "Advancing to T2":           "向 T2 推进",
    "T1 Giveback Warning":       "T1 回吐预警",
    "Deep Giveback — Reassess":  "大幅回吐 — 重新评估",
    "High Conviction":           "高确信",
    "Extended — Watch Giveback": "涨幅拉伸 — 留意回吐",
    "Overtime Stall":            "超时停滞",
    "Invalidated":               "已失效",
}


def _closed_state_lines(outcome: str | None) -> tuple[list[str], list[str]]:
    """(EN, ZH) single-line ``what_to_do_now`` for a plan that has already closed.

    A closed plan kept shipping the live instruction block — "buy above <trigger>,
    stop below <invalidation>, trim at T1" — for a position that was stopped out or
    timed out weeks earlier.  That is an instruction a reader can act on, attached to
    a thesis that is over.  It is replaced by ONE line that states the end and asks for
    nothing, reusing the same plain-word outcome vocabulary the pulse uses (raw ledger
    enum slugs like ``T1_HIT`` are banned from any string a surface may print).

    Both halves are always returned together: an EN-only line would desync the
    bilingual pair, which is exactly the failure ``_plan_pulse`` was written to avoid.
    """
    words = _OUTCOME_WORD.get(str(outcome or "").strip().upper())
    if not words:
        return (["This plan is closed. Nothing to do — kept here for the record."],
                ["该计划已结束。无需操作 — 保留以供记录。"])
    return ([f"This plan is closed — {words[0]}. Nothing to do; kept here for the record."],
            [f"该计划已结束 — {words[1]}。无需操作；保留以供记录。"])


def _age_days(signal_date: str | None, asof: str) -> int | None:
    """Whole days from signal_date to the index asof; None when either is unusable.

    Clamped at 0 (matching ``prophet_management.days_elapsed``) so a plan anchored on a
    later date than the run reads "0d" rather than a negative age.
    """
    if not signal_date:
        return None
    try:
        return max(0, (date.fromisoformat(str(asof)[:10])
                       - date.fromisoformat(str(signal_date)[:10])).days)
    except (TypeError, ValueError):
        return None


def _age_bucket(age_days: int | None) -> str:
    """≤7d / 8-21d / >21d, or 'unknown' when the age could not be computed.

    'unknown' is a real bucket, not a dropped row: the buckets must sum to
    ``active_count`` or the surface would under-report its own population.
    """
    if age_days is None:
        return "unknown"
    if age_days <= 7:
        return "le_7d"
    if age_days <= 21:
        return "d8_21d"
    return "gt_21d"


def _degraded_index_entry(
    plan_id: str,
    plan: dict[str, Any],
    *,
    asof: str,
    reason: str,
    closed: bool,
    outcome: str | None,
) -> dict[str, Any]:
    """Discoverable long-tail row when management cannot state a plan tonight.

    Lossless origination is meaningless if an admitted plan is written to disk and then
    vanishes from the only ranked index because a price or management enrichment failed.
    This row carries the immutable plan facts and an explicit unavailable state.  It does
    not invent a price, phase transition, recommendation, or confidence value.
    """
    formation = plan.get("formation_date") or plan.get("signal_date")
    signal = plan.get("signal_date")
    age = _age_days(signal or plan.get("observed_date") or formation, asof)
    phase = plan.get("phase") or "pre_trigger"
    pulse_en, pulse_zh = _plan_pulse(
        age, phase, None, closed=closed, outcome=outcome
    )
    if closed:
        now_en, now_zh = _closed_state_lines(outcome)
    else:
        now_en = plan.get("what_to_do_now") or []
        now_zh = plan.get("what_to_do_now_zh") or []
    return {
        "id": plan_id,
        "asset": plan.get("asset"),
        "direction": plan.get("direction"),
        "entry": plan.get("entry"),
        "invalidation": plan.get("invalidation"),
        "targets": plan.get("targets", []),
        "trigger": plan.get("trigger"),
        "option_contract": plan.get("option_contract"),
        "_r_unit": plan.get("_r_unit"),
        "_conviction_score": plan.get("_conviction_score"),
        "_priority_score": plan.get("_priority_score"),
        "_signal_date": signal,
        "formation_date": formation,
        "signal_date": signal,
        "confirmed_date": plan.get("confirmed_date"),
        "observed_date": plan.get("observed_date"),
        "price_basis_date": plan.get("price_basis_date"),
        "recorded_at": plan.get("recorded_at") or plan.get("asof"),
        "plan_asof": plan.get("asof"),
        "entry_date": plan_clock_date(plan),
        "signal_tier": plan.get("signal_tier"),
        "signal_date_basis": plan.get("signal_date_basis"),
        "signal_provisional": plan.get("signal_provisional"),
        "source_marker_date": plan.get("source_marker_date"),
        "integrity_status": plan.get("integrity_status"),
        "integrity_reason": plan.get("integrity_reason"),
        # Same provenance stamp as the healthy row above.  A backfilled plan whose
        # management degrades tonight must not become UNSPLITTABLE as a side effect
        # of a missing price history — the degraded row is still a shipped row.
        "origination_mode": plan.get("origination_mode"),
        "backfill_executed_at": plan.get("backfill_executed_at"),
        "phase": phase,
        "age_days": age,
        "closed": closed,
        "pulse": pulse_en,
        "pulse_zh": pulse_zh,
        "management_status": "unavailable",
        "management_error": reason,
        "management_confidence": None,
        "recommended_action": None,
        "last_price": None,
        "state": {
            "phase": phase,
            "management_confidence": None,
            "recommended_action": None,
            "components": None,
            "geometry": None,
            "change_reason": reason,
        },
        "what_to_do_now": now_en,
        "what_to_do_now_zh": now_zh,
        "profit_plan": plan.get("profit_plan") or [],
        "thesis": plan.get("thesis") or "",
        "thesis_zh": plan.get("thesis_zh") or "",
        "horizon_days": plan.get("horizon_days"),
        "stage_tilt": plan.get("stage_tilt"),
    }


def _plan_pulse(
    age_days: int | None,
    phase: str | None,
    human_state: str | None,
    *,
    closed: bool = False,
    outcome: str | None = None,
) -> tuple[str, str]:
    """(EN, ZH) one-line pulse for a plan — e.g. ``("32d · triggered · stalling", …)``.

    Composed from fields the state engine already computes; adds no judgement of its own.
    Every leg is independently optional, so a plan missing an age or an unmapped phase
    still gets the legs it does have, and a plan with nothing readable returns ``("", "")``
    rather than a half-built string.  DATA ONLY — W2 owns how (and whether) this renders.

    CLOSED PLANS (W1 amendment).  ``closed=True`` — the plan has a forward-ledger row —
    returns ``("closed · stopped out", "已结 · 止损离场")`` and reads NEITHER phase nor
    human_state.  Both keep updating for a closed plan (the management engine states
    every plan in the index), so a closed plan would otherwise pulse "138d · overtime ·
    overtime stall" as though the thesis were still running.  The age leg is dropped
    too: ``age_days`` counts from signal_date to TODAY, so on a dead plan it grows
    forever and reads as duration-still-open.  ``age_days`` stays on the row as raw
    data; it is only the plain-word line that must not imply life.
    """
    if closed:
        words = _OUTCOME_WORD.get(str(outcome or "").strip().upper())
        if not words:
            return "closed", "已结"
        return f"closed · {words[0]}", f"已结 · {words[1]}"

    parts_en: list[str] = []
    parts_zh: list[str] = []

    if isinstance(age_days, int) and age_days >= 0:
        parts_en.append(f"{age_days}d")
        parts_zh.append(f"{age_days}天")

    words = _PHASE_WORD.get(str(phase or ""))
    if words:
        parts_en.append(words[0])
        parts_zh.append(words[1])

    state_zh = _HUMAN_STATE_ZH.get(str(human_state or "").strip())
    state_en = str(human_state or "").strip().lower()
    # "invalidated · invalidated" says nothing twice — drop the echo, keep the pair.
    if state_zh and not (words and state_en == words[0].lower()):
        parts_en.append(state_en)
        parts_zh.append(state_zh)

    if not parts_en:
        return "", ""
    return " · ".join(parts_en), " · ".join(parts_zh)


# ---------------------------------------------------------------------------
# Price history loader (for management engine)
# ---------------------------------------------------------------------------

def _load_price_history_for_management(ticker: str):
    """Load OHLCV price history for the management engine.

    Same three rungs, in the same priority order, as
    ``engine.prophet_bridge._load_price_history``: per-ticker ohlcv → per-ticker stocks
    → the wide index-constituent close panels.  The panel list and its order live in
    the bridge and are imported, not re-typed: origination and management MUST resolve
    a name to the same series, or a plan is priced at birth and unmanageable a night
    later (27 of 103 live plans were priced by nothing at all before the panel rung).
    """
    import pandas as pd  # noqa: PLC0415
    for sub in _PLAN_PRICE_DIRS:
        p = _REPO / sub / f"{ticker}.parquet"
        if p.exists():
            try:
                df = pd.read_parquet(p)
                if not isinstance(df.index, pd.DatetimeIndex):
                    for c in ["date", "Date"]:
                        if c in df.columns:
                            df = df.set_index(c)
                            break
                df.index = pd.to_datetime(df.index)
                return df
            except Exception as e:
                log.warning("build_prophet: price history load failed %s: %s", ticker, e)
    return _panel_close_history(ticker, _REPO)


# ---------------------------------------------------------------------------
# Market overlay inputs (R0.7 — macro_stance / futures_chg for the management
# engine's overlay component; both loaded once per run, shared by every plan)
# ---------------------------------------------------------------------------

# market_state verdict vocabulary (engine/market_state.py) → engine stance
# vocabulary (engine/prophet_management.py docstring: 'bull'|'bear'|'neutral').
_VERDICT_TO_STANCE = {"RISK_ON": "bull", "MIXED": "neutral", "RISK_OFF": "bear"}

# A market snapshot or index close older than this (vs asof) is omitted rather
# than fed to the overlay as if it were current.
_OVERLAY_MAX_AGE_DAYS = 7


def _load_macro_stance(asof: str) -> str | None:
    """Map data/market_state/latest.json risk verdict to the engine's stance.

    PIT + freshness guarded: the snapshot must be dated on or before asof and
    at most _OVERLAY_MAX_AGE_DAYS old; otherwise return None so the overlay
    component omits the stance term instead of reading a stale or future-dated
    market state (a backfill --date run must never see a later verdict).
    """
    try:
        with MARKET_STATE_PATH.open(encoding="utf-8") as f:
            ms = json.load(f)
        ms_asof = date.fromisoformat(str(ms.get("asof", ""))[:10])
        asof_d = date.fromisoformat(str(asof)[:10])
        if ms_asof > asof_d or (asof_d - ms_asof).days > _OVERLAY_MAX_AGE_DAYS:
            log.info(
                "build_prophet: market_state asof=%s unusable for asof=%s — "
                "macro_stance omitted", ms_asof, asof_d)
            return None
        return _VERDICT_TO_STANCE.get(str(ms.get("verdict", "")).upper())
    except Exception as e:
        log.info("build_prophet: macro_stance unavailable (%s) — omitted", e)
        return None


def _load_futures_chg(asof: str) -> dict | None:
    """Prior close-to-close % change for SPY/QQQ from the yahoo price store.

    Nightly-cadence proxy for the engine's futures overlay term (the
    compute_management_state docstring specifies prior close-to-close changes,
    not live futures). PIT-filtered to closes <= asof; a symbol whose latest
    PIT close is older than _OVERLAY_MAX_AGE_DAYS is dropped. Returns None when
    nothing resolves so the overlay omits the term honestly.
    """
    import pandas as pd  # noqa: PLC0415

    out: dict[str, float] = {}
    asof_ts = pd.Timestamp(str(asof)[:10])
    for sym in ("SPY", "QQQ"):
        p = YAHOO_DIR / f"{sym}.parquet"
        if not p.exists():
            continue
        try:
            df = pd.read_parquet(p)
            df.index = pd.to_datetime(df.index)
            closes = df.loc[df.index <= asof_ts, "close"].dropna()
            if len(closes) < 2:
                continue
            if (asof_ts - closes.index[-1]).days > _OVERLAY_MAX_AGE_DAYS:
                continue
            prev = float(closes.iloc[-2])
            if prev == 0.0:
                continue
            out[sym] = round((float(closes.iloc[-1]) - prev) / abs(prev), 6)
        except Exception as e:
            log.info("build_prophet: futures_chg %s unavailable (%s)", sym, e)
    return out or None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    parser = argparse.ArgumentParser(
        description="Prophet origination bridge + artifact publisher (W1, display-only)."
    )
    parser.add_argument(
        "--date",
        default=date.today().isoformat(),
        help=(
            "ISO-8601 run/publication date; entry price basis comes from "
            "us_standouts.staleness.price_through."
        ),
    )
    parser.add_argument(
        "--publish",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--showcase-only",
        action="store_true",
        help="Only (re)write site/prophet/showcase.json from us_standouts.json "
             "— no origination, no management, NO ledger touch. Safe to run "
             "locally at any time.",
    )
    args = parser.parse_args()

    if args.publish:
        parser.error(
            "--publish is disabled: R2 publication requires the accepted Git "
            "checkpoint and conditional workflow publisher"
        )

    if args.showcase_only:
        write_showcase()
        return None

    asof: str = args.date
    log.info("build_prophet: starting — asof=%s publish=%s", asof, args.publish)
    _standouts_doc = _read_json(STANDOUTS_PATH) or {}
    _source_staleness = (
        _standouts_doc.get("staleness")
        if isinstance(_standouts_doc.get("staleness"), dict) else {}
    )
    # The freshness authority is the ranked-price watermark.  A board wrapper can be
    # rebuilt tonight while its cross-section still ends days earlier, so top-level
    # `as_of` remains a separate publication/source-board disclosure only.
    source_asof = str(_source_staleness.get("price_through") or "")[:10] or None
    source_board_asof = str(_standouts_doc.get("as_of") or "")[:10] or None
    source_delayed = _source_staleness.get("delayed")
    source_unknown = _source_staleness.get("unknown")
    source_basis = _source_staleness.get("basis")
    _source_inputs = (
        _source_staleness.get("inputs")
        if isinstance(_source_staleness.get("inputs"), dict) else {}
    )
    _source_panel = (
        _source_inputs.get("panel")
        if isinstance(_source_inputs.get("panel"), dict) else {}
    )
    source_mixed_vintage = bool(
        _source_panel.get("mixed_vintage")
    )

    # ── 0. Initialize ledger ──────────────────────────────────────────────────
    _initialize_ledger()

    # ── 1. Load existing plans (duplicate suppression) ────────────────────────
    # Plan JSONs are immutable publication records.  Audited date corrections are an
    # append-only overlay; every downstream clock reads the effective projection, while
    # the raw files are never rewritten to make history look cleaner than it was.
    raw_existing_plans = _load_existing_plans()
    correction_rows = load_plan_corrections(
        LEDGER_DIR / PLAN_CORRECTIONS_FILENAME
    )
    correction_projection = apply_plan_corrections(
        raw_existing_plans, correction_rows
    )
    existing_plans = correction_projection.plans
    plan_quarantined_ids = set(correction_projection.quarantined_ids)
    existing_ids: set[str] = set(raw_existing_plans.keys())
    # W1: same-id suppression is not enough — the id carries signal_date, so a fresh
    # signal on a live name used to originate a SECOND plan for it and burn a slot.
    # The ticker+direction keys of still-OPEN plans block that; closure frees the key.
    # ONE ledger read for both W1 consumers: the block needs the id set, the index
    # needs the outcome word for each closed plan's `closed` flag and pulse.
    closed_outcomes = _load_closed_outcomes()
    closed_ids = set(closed_outcomes)
    # An audit-quarantined plan is not actionable and must not monopolise the ticker's
    # future opportunity slot.  Same-ID suppression remains, so identity never forks.
    actionable_existing = {
        plan_id: plan for plan_id, plan in existing_plans.items()
        if plan_id not in plan_quarantined_ids
    }
    active_keys = open_plan_keys(actionable_existing, closed_ids)
    log.info(
        "build_prophet: %d existing plans loaded (%d closed in the ledger; "
        "%d open ticker+direction keys blocking re-origination)",
        len(existing_ids), len(existing_ids & closed_ids), len(active_keys),
    )
    log.info(
        "build_prophet: correction overlay — %d row(s), %d corrected plan(s), "
        "%d quarantined plan(s)",
        len(correction_rows), len(correction_projection.applied_by_plan),
        len(plan_quarantined_ids),
    )

    # ── 2. Originate new plans ────────────────────────────────────────────────
    # WP-RESOLVER: canonical store resolution (THETADATA_STORE env →
    # data_dir()/thetadata_eod → ops-wt, content-checked). Option resolution is
    # an optional enrichment — plans/ledger still advance without a store — but
    # a missing store is now LOUD instead of a silent per-plan info line, and a
    # store that exists without the env var being set is now actually found.
    from engine.thetadata_store import resolve_thetadata_store  # noqa: PLC0415
    _resolved_store = resolve_thetadata_store(
        required=False, purpose="build_prophet option-resolution")
    if _resolved_store is None:
        log.error(
            "build_prophet: no ThetaData store resolves — option recommendations "
            "will be SKIPPED for all new plans (plans/ledger still advance)")
    thetadata_store = str(_resolved_store) if _resolved_store is not None else None
    intake_stats: dict[str, Any] = {}
    new_plans = originate_plans(
        standouts_path=STANDOUTS_PATH,
        asof=asof,
        existing_ids=existing_ids,
        thetadata_store=thetadata_store,
        active_keys=active_keys,
        intake_stats=intake_stats,
    )
    log.info(
        "build_prophet: %d new plans originated (%d candidate(s) blocked by an open "
        "same-ticker plan: %s)",
        len(new_plans),
        intake_stats.get("reorigination_blocked", 0),
        ", ".join(intake_stats.get("reorigination_blocked_keys") or []) or "none",
    )

    # ── 2b. Prophet Arena — champion-vs-challenger shadow harness (ZERO AUTHORITY) ──
    # Frozen challenger intake/closure policies re-slice THIS night's artifact into
    # shadow plan sets, graded by the same closure rules as the champion, onto their own
    # prospective ledgers (data/prophet_arena/) plus a scoreboard. Registration + frozen
    # policy definitions: research/PROPHET_ARENA_REGISTRATION.md.
    #
    # NOTHING HERE REACHES THE LIVE CHAIN. This block only CALLS the arena; build_prophet
    # never reads an arena ledger, scoreboard, or artifact back (fence test-pinned in
    # tests/test_prophet_arena.py::TestImportFence). `all_plans` below is built from
    # `new_plans` exactly as it was before this hook existed.
    #
    # existing_ids is REBUILT from existing_plans rather than reused: originate_plans
    # MUTATES the set it is handed (it adds each id it originates), so by this line the
    # original set already contains tonight's new ids and would suppress everything C0
    # tried to mirror. existing_plans itself is untouched.
    #
    # The standouts artifact is loaded HERE and passed in-memory, so the arena provably
    # slices the same world the live origination did rather than re-reading a file that
    # another lane could have rewritten in between. C0's plan ids are checked against the
    # live ids as the harness-validity pin.
    try:
        from engine.prophet_arena import run_arena  # noqa: PLC0415

        with STANDOUTS_PATH.open(encoding="utf-8") as _f:
            _arena_standouts = json.load(_f)
        _arena_board = run_arena(
            _arena_standouts,
            asof=asof,
            existing_ids=set(existing_plans.keys()),
            active_keys=active_keys,
            live_plan_ids={p["id"] for p in new_plans},
            repo_root=_REPO,
        )
        log.info(
            "build_prophet: prophet_arena ran — %d policies, harness_ok=%s",
            len(_arena_board.get("policies") or []),
            (_arena_board.get("harness_validity") or {}).get("harness_ok"),
        )
    except Exception as e:  # noqa: BLE001 — a shadow harness is NEVER fatal to the nightly
        # Bare print, NOT a logger call: GitHub parses a workflow command only when "::"
        # STARTS the line, and this module's logging format prefixes every record.
        print(f"::warning::prophet_arena hook failed: {e}", flush=True)
        log.warning("build_prophet: prophet_arena hook failed", exc_info=True)

    # ── 2c. Legacy shadow ledger (ANTICIPATION §6.5) — ZERO AUTHORITY ─────────
    # The pre-2026-08-08 admission gate keeps running every night against the same
    # artifact and writes what it WOULD have selected.  Nothing in the live pick chain
    # reads this store; it exists so the operator's "compare them later" is answerable
    # from two accrued ledgers instead of from memory.
    #
    # THE LANE IS DECLARED HERE, AT THE PRODUCTION CALL SITE.  `append_legacy_shadow`
    # takes `lane_nightly` as a keyword-only argument with NO DEFAULT, so this line is
    # the only thing that can open the gate — a writer whose caller passes nothing and
    # whose default branch is "allow" is a guard only the test suite ever exercises
    # (the #5000 shape).  The writer then re-checks the process lane itself, so a caller
    # that claims nightly in a render or intraday process still writes nothing.
    #
    # `existing_plans.keys()` rather than `existing_ids`: originate_plans MUTATES the
    # set it is handed, so by this line `existing_ids` already carries tonight's new ids
    # and the legacy replay would suppress rows the legacy gate never saw.  Same
    # reasoning as the arena block above.
    #
    # The store is CO-LOCATED with the forward ledger — `LEDGER_DIR/legacy_shadow`,
    # which in production is `data/prophet/legacy_shadow`.  tests/conftest.py arms
    # COLLECT_LANE=nightly for EVERY test, so a writer that resolves its own data dir
    # would write the repo's REAL data tree from any test that reaches this line.
    # Handing the directory outright is the fail-CLOSED form: every bp.main() harness
    # must already redirect LEDGER_DIR or advance_ledger would do the same damage.
    _shadow_store = LEDGER_DIR / "legacy_shadow"
    shadow_rows: list[dict] = []
    shadow_written = 0
    try:
        with STANDOUTS_PATH.open(encoding="utf-8") as _f:
            _shadow_standouts = json.load(_f)
        shadow_rows = legacy_shadow_rows(
            _shadow_standouts,
            asof=asof,
            existing_ids=set(existing_plans.keys()),
            active_keys=active_keys,
        )
        shadow_written = append_legacy_shadow(
            shadow_rows, asof, store_dir=_shadow_store,
            lane_nightly=ledger_lane.nightly_advance_enabled(),
        )
        log.info(
            "build_prophet: legacy shadow — %d legacy-admitted row(s), %d would have "
            "been planned (cap %d); part now holds %d row(s)",
            len(shadow_rows),
            sum(1 for r in shadow_rows if r.get("would_have_planned")),
            LEGACY_N_CANDIDATES,
            shadow_written,
        )
    except Exception as e:  # noqa: BLE001 — a shadow ledger is NEVER fatal to the nightly
        # Bare print at line start: a logger prefix makes GitHub drop the annotation.
        print(f"::warning title=prophet-legacy-shadow::legacy shadow ledger failed: {e}",
              flush=True)
        log.warning("build_prophet: legacy shadow ledger failed", exc_info=True)

    # Merge the effective projection with tonight's raw new publications.  Existing
    # plan files stay immutable; only IDs in ``new_plan_ids`` may be written below.
    all_plans = {**existing_plans}
    for p in new_plans:
        all_plans[p["id"]] = p
    new_plan_ids = {str(plan["id"]) for plan in new_plans}
    actionable_plans = {
        plan_id: plan for plan_id, plan in all_plans.items()
        if plan_id not in plan_quarantined_ids
    }

    # ── 3. Run management engine for every active plan ────────────────────────
    # R0.7: market overlay inputs — one load per run, passed to every plan so
    # the engine's dormant macro-stance/futures terms actually activate.
    macro_stance = _load_macro_stance(asof)
    futures_chg = _load_futures_chg(asof)
    log.info(
        "build_prophet: market overlay — macro_stance=%s futures_chg=%s",
        macro_stance, futures_chg,
    )

    active_entries: list[dict] = []
    import pandas as pd  # noqa: PLC0415

    for plan_id, plan in actionable_plans.items():
        ticker = plan.get("asset", "")
        _closed = plan_id in closed_ids
        ph = _load_price_history_for_management(ticker)

        if ph is None:
            log.warning(
                "build_prophet: no price history for %s; skipping management", ticker
            )
            # A new publication must persist even when management has no tape.  An
            # existing publication is immutable and therefore is not rewritten.
            if plan_id in new_plan_ids:
                _write_json(PLANS_DIR / f"{plan_id}.json", plan)
            active_entries.append(_degraded_index_entry(
                plan_id, plan, asof=asof,
                reason="price_history_unavailable",
                closed=_closed, outcome=closed_outcomes.get(plan_id),
            ))
            continue

        # PIT: filter price_history to <= asof
        asof_ts = pd.Timestamp(asof)
        ph_pit = ph[ph.index <= asof_ts]

        if ph_pit.empty:
            log.warning(
                "build_prophet: empty price history for %s up to %s", ticker, asof
            )
            if plan_id in new_plan_ids:
                _write_json(PLANS_DIR / f"{plan_id}.json", plan)
            active_entries.append(_degraded_index_entry(
                plan_id, plan, asof=asof,
                reason="price_history_empty_through_publication_date",
                closed=_closed, outcome=closed_outcomes.get(plan_id),
            ))
            continue

        prev_state = _load_existing_state(plan_id)

        try:
            state = compute_management_state(
                plan=plan,
                price_history=ph_pit,
                asof=asof,
                macro_stance=macro_stance,
                futures_chg=futures_chg,
                prev_state=prev_state,
            )
        except Exception as e:
            log.warning(
                "build_prophet: management engine failed for %s: %s", plan_id, e
            )
            if plan_id in new_plan_ids:
                _write_json(PLANS_DIR / f"{plan_id}.json", plan)
            active_entries.append(_degraded_index_entry(
                plan_id, plan, asof=asof,
                reason=f"management_engine_error:{type(e).__name__}",
                closed=_closed, outcome=closed_outcomes.get(plan_id),
            ))
            continue

        # Write artifacts
        if plan_id in new_plan_ids:
            _write_json(PLANS_DIR / f"{plan_id}.json", plan)
        _write_json(STATES_DIR / f"{plan_id}.json", state)

        # Rebuild what_to_do_now and profit_plan with the phase resolved by the
        # management engine (phase may differ from what originate_plans stored).
        # Thesis is already in the plan dict if originated by new code; leave it
        # as-is for pre-existing plans that lack it.
        from engine.prophet_bridge import (  # noqa: PLC0415
            _build_what_to_do_now,
            _build_what_to_do_now_zh,
            _build_profit_plan,
        )
        resolved_phase = state.get("phase") or plan.get("phase", "pre_trigger")
        t1 = plan["targets"][0] if plan.get("targets") else None
        t2 = plan["targets"][1] if plan.get("targets") and len(plan["targets"]) > 1 else None
        # ── §6.9 R3: nightly zone re-evaluation (zone-with-expiry-to-starter) ──
        # DERIVED every night from the plan's own zone and the SAME PIT frame the
        # management engine just read.  Nothing is written back into the plan JSON:
        # plan files are immutable publication records and corrections are an
        # append-only overlay, so a converted stance is recomputed rather than
        # back-dated into the artifact that originated it.
        try:
            zone_state = evaluate_entry_zone(plan, ph_pit, asof)
        except Exception as e:  # noqa: BLE001 — a zone read never breaks the publish
            log.warning("build_prophet: zone re-evaluation failed for %s: %s", plan_id, e)
            zone_state = {"state": "error", "reason": f"{type(e).__name__}: {e}"}
        # A plan with a forward-ledger row is FINISHED. The management engine still
        # states it (it is still in all_plans), so without this flag the row is
        # indistinguishable from a live one and its pulse would narrate a dead thesis.
        # closed_ids is the same set the re-origination block uses — one ledger read.
        if _closed:
            # P5: a closed plan must not ship live instructions. It kept shipping
            # "buy above <trigger>, stop at <invalidation>" for a position that was
            # already stopped out or timed out — an instruction a reader could act on.
            what_to_do_now, what_to_do_now_zh = _closed_state_lines(
                closed_outcomes.get(plan_id)
            )
        else:
            what_to_do_now = _build_what_to_do_now(
                phase=resolved_phase,
                entry=plan.get("entry"),
                trigger=plan.get("trigger"),
                invalidation=plan.get("invalidation"),
                t1=t1,
                t2=t2,
                entry_zone=plan.get("entry_zone"),
                zone_state=zone_state,
            )
            what_to_do_now_zh = _build_what_to_do_now_zh(
                phase=resolved_phase,
                entry=plan.get("entry"),
                trigger=plan.get("trigger"),
                invalidation=plan.get("invalidation"),
                t1=t1,
                t2=t2,
                entry_zone=plan.get("entry_zone"),
                zone_state=zone_state,
            )
        profit_plan = _build_profit_plan(
            phase=resolved_phase,
            entry=plan.get("entry"),
            t1=t1,
            t2=t2,
        )
        # R0.7 last_price guard: 0 = missing for equity prices (house law), and
        # a NaN would render json.dump output unparseable for the Terminal.
        _last_close = float(ph_pit["close"].iloc[-1])
        if not (math.isfinite(_last_close) and _last_close > 0.0):
            _last_close = None  # type: ignore[assignment]
        # ── W1 index hygiene: age + pulse (data only; W2 renders it) ──────────
        # age_days is computed from signal_date against THIS run's asof rather than
        # read off state.days_elapsed, so it exists for the same reason the row does
        # and cannot go missing when a state field is absent.
        _age = _age_days(
            plan.get("signal_date")
            or plan.get("observed_date")
            or plan.get("_signal_date")
            or plan.get("formation_date"),
            asof,
        )
        _pulse_en, _pulse_zh = _plan_pulse(
            _age, resolved_phase, state.get("human_state"),
            closed=_closed, outcome=closed_outcomes.get(plan_id),
        )
        active_entries.append({
            "id": plan_id,
            "asset": plan.get("asset"),
            "direction": plan.get("direction"),
            "entry": plan.get("entry"),
            "invalidation": plan.get("invalidation"),
            "targets": plan.get("targets", []),
            "trigger": plan.get("trigger"),
            "option_contract": plan.get("option_contract"),
            "_r_unit": plan.get("_r_unit"),
            "_conviction_score": plan.get("_conviction_score"),
            # P6: the us_prophet_v1 priority score `plans[]` is actually sorted by.
            # It ships on the row so a reader can verify the declared order rather
            # than take the artifact's word for it. None on pre-P6 plans.
            "_priority_score": plan.get("_priority_score"),
            "_signal_date": plan.get("_signal_date"),
            # Explicit temporal clocks for new plans.  Legacy plans retain nulls rather
            # than receiving a backfill inference in this publishing pass.
            "formation_date": plan.get("formation_date"),
            "signal_date": plan.get("signal_date"),
            "confirmed_date": plan.get("confirmed_date"),
            "observed_date": plan.get("observed_date"),
            "price_basis_date": plan.get("price_basis_date"),
            "recorded_at": plan.get("recorded_at"),
            "plan_asof": plan.get("asof"),
            "signal_tier": plan.get("signal_tier"),
            "signal_date_basis": plan.get("signal_date_basis"),
            "signal_provisional": plan.get("signal_provisional"),
            "source_marker_date": plan.get("source_marker_date"),
            "integrity_status": plan.get("integrity_status"),
            "integrity_reason": plan.get("integrity_reason"),
            # The compatibility clock every horizon/outcome/τ read resolves to.
            "entry_date": plan_clock_date(plan),
            "phase": resolved_phase,
            # W1 index hygiene — how old this thesis is, whether it is finished, and
            # one plain-word line saying where it stands.  Additive: nothing was
            # removed or re-ordered.
            "age_days": _age,
            "closed": _closed,
            "pulse": _pulse_en,
            "pulse_zh": _pulse_zh,
            "management_confidence": state.get("management_confidence"),
            "recommended_action": state.get("recommended_action"),
            "management_status": "available",
            "management_error": None,
            # R0.7 — last close the management engine saw (same PIT frame).
            # The Terminal's GAINERS sort and T1-progress/P&L bars render only
            # when last_price is present.
            "last_price": round(_last_close, 4) if _last_close is not None else None,
            # R0.7 — nested state block. The Terminal reads components /
            # geometry / change_reason via plan.state (SignalCard PlanSummary
            # nested shape), so these ride under "state", not top-level. The
            # hoisted flat trio above stays for existing consumers.
            "state": {
                "phase": resolved_phase,
                "management_confidence": state.get("management_confidence"),
                "recommended_action": state.get("recommended_action"),
                "components": state.get("components"),
                "geometry": state.get("geometry"),
                "change_reason": state.get("change_reason"),
            },
            # ── Content blocks (W2 — deterministic, no LLM) ───────────────────
            # A CLOSED plan ships a closed-state line here, never live instructions
            # (P5).  The ZH half rides with it so the pair can never desync.
            "what_to_do_now": what_to_do_now,
            "what_to_do_now_zh": what_to_do_now_zh,
            "profit_plan": profit_plan,
            "thesis": plan.get("thesis") or "",  # originated by prophet_bridge.py
            # ZH half of the thesis — whitelisted by OEU M-PRO so the bilingual pair
            # the originator already writes actually reaches the payload (house law:
            # every EN string ships with its ZH pair). Older plans lack the key → "".
            "thesis_zh": plan.get("thesis_zh") or "",
            # PSQ-TILT W1 provenance (whitelisted so the Terminal can consume it).
            "horizon_days": plan.get("horizon_days"),
            "stage_tilt": plan.get("stage_tilt"),
            # ── ANTICIPATION §6.2 A1 / §6.9 R3 provenance (ADDITIVE — nothing
            # renamed).  Whitelisted onto the index row for the same reason
            # stage_tilt is: the Terminal and the showcase read `index.json`, not the
            # per-plan files, so a stamp that never reaches this dict is a stamp no
            # surface can show.  None on every plan originated before the era — that
            # null IS the era boundary, and it is printed rather than back-filled.
            "admission_class": plan.get("admission_class"),
            "entry_status": plan.get("entry_status"),
            "selection_era": plan.get("selection_era"),
            # HOW this row came to exist, not what it selected.  `None` on every
            # plan a nightly bake originated — that null IS "live", and it is
            # printed rather than defaulted to a word.  The only non-null value
            # today is the 2026-08-09 force-majeure replay
            # (research/PROPHET_OUTAGE_BACKFILL_2026_08.md; enumerated in
            # data/prophet/backfill_disclosures.json).  Whitelisted for the same
            # reason `selection_era` is: the Terminal, the showcase and every
            # track-record aggregate read index.json, not the per-plan files, so
            # a stamp that never reaches this dict is a stamp no reader can split
            # a rate by.  Segregation is pinned in tests/test_prophet_outage_backfill.py.
            "origination_mode": plan.get("origination_mode"),
            "backfill_executed_at": plan.get("backfill_executed_at"),
            "entry_basis": plan.get("entry_basis"),
            "entry_zone": plan.get("entry_zone"),
            # DERIVED tonight, never stored on the plan.
            "entry_zone_state": zone_state,
            "early_turn": plan.get("early_turn"),
        })

    # ── 3b. Advance ledger (nightly-only — idempotent close-event writer) ────────
    # Must run AFTER all plans + price histories have been processed so we have
    # a complete all_plans dict.  Nightly is the SOLE caller of advance_ledger().
    # This is part of the accepted Prophet state, not optional enrichment.  Publishing
    # plans/index after a partial or failed ledger advance would split the system's
    # clocks; let the build fail so the guarded checkpoint withholds the whole delta.
    advance_ledger(actionable_plans, asof)

    # ── 3c. Forward-ledger quarantine (derived, then disclosed) ──────────────────
    # Runs AFTER advance_ledger so tonight's closes are judged by the same rule as
    # every earlier row, and the file the surfaces read is never a run behind.
    _raw_ledger_rows = _load_ledger_rows()
    ledger_correction_rows = load_ledger_corrections(
        LEDGER_DIR / LEDGER_CORRECTIONS_FILENAME
    )
    ledger_projection = apply_ledger_corrections(
        _raw_ledger_rows, ledger_correction_rows
    )
    _ledger_rows = list(ledger_projection.rows)
    _ledger_correction_reasons = {
        str(row.get("id")): str(row.get("integrity_reason") or "ledger correction")
        for row in _ledger_rows
        if row.get("integrity_status") == "quarantined" and row.get("id")
    }
    # The exclusion receipt changes the published record denominator and is therefore
    # authoritative.  Failure must withhold the checkpoint, never substitute an empty
    # set that silently rehabilitates poisoned outcomes.
    quarantine = write_quarantine(
        _ledger_rows, all_plans,
        correction_quarantines=_ledger_correction_reasons,
    )
    _derived_ledger_quarantined_ids = {
        str(r.get("id")) for r in (quarantine.get("quarantined") or [])
    }
    _ledger_quarantined_ids = (
        _derived_ledger_quarantined_ids
        | set(ledger_projection.quarantined_ids)
    )
    _quarantined_ids = _ledger_quarantined_ids | plan_quarantined_ids
    # ``active_entries`` is also the sole public/index supply for Brain and the
    # marketing desks. A terminal row quarantined after management ran must not stay
    # alive there merely because this run built the index row before deriving the
    # ledger exclusion receipt. Raw plans/states remain immutable evidence; only the
    # effective publication is filtered.
    active_entries = _effective_index_entries(active_entries, _quarantined_ids)
    _record = record_summary(_ledger_rows, _quarantined_ids)
    log.info("build_prophet: honest record over %d non-quarantined scored row(s) — "
             "win_rate=%s avg=%s%%", _record["n_scored"],
             _record["win_rate"], _record["avg_result_pct"])

    # ── 4. Write index.json ───────────────────────────────────────────────────
    # P6: `plans[]` ships in the order the artifact DECLARES — the us_prophet_v1
    # priority score, the same key intake ranks by.  It used to sort by
    # `_conviction_score`, an input the board ruling gives ZERO ordering authority
    # (research/US_BOARD_MEASUREMENT.md: published conviction order was
    # anti-predictive at the top, P@1 0.20 vs 0.60 re-ordered by alpha), while the
    # artifact's own `intake.sort_key` claimed the priority score.  Legacy self-heal
    # mirrors select_candidates: an unscored plan sorts BELOW every scored one and,
    # among its own kind, by the old conviction key.
    active_entries.sort(
        key=lambda e: (
            0 if isinstance(e.get("_priority_score"), (int, float))
            and not isinstance(e.get("_priority_score"), bool) else 1,
            -(e.get("_priority_score")
              if isinstance(e.get("_priority_score"), (int, float))
              and not isinstance(e.get("_priority_score"), bool)
              else (e.get("_conviction_score") or 0)),
            e.get("id", ""),
        ),
    )
    # W1 index hygiene: age census over exactly the rows that ship, so the buckets
    # always sum to active_count (an under-reporting surface is its own defect).
    age_counts: dict[str, int] = {key: 0 for key in AGE_BUCKET_KEYS}
    for entry in active_entries:
        age_counts[_age_bucket(entry.get("age_days"))] += 1

    index: dict[str, Any] = {
        "schema": "prophet.index/v1",
        # Compatibility run clock.  Freshness sentinels MUST use source_asof below:
        # a successful rerun can refresh this publication stamp while its input freezes.
        "asof": asof,
        "recorded_at": asof,
        "source_asof": source_asof,
        "source_board_asof": source_board_asof,
        "source_delayed": source_delayed,
        "source_unknown": source_unknown,
        "source_basis": source_basis,
        "source_mixed_vintage": source_mixed_vintage,
        "cadence": "nightly-EOD",
        "authority_tier": "display",
        # ANTICIPATION §6.2 A1 — the selection rule tonight's plans were originated
        # under.  Stamped at the top level as well as on every plan so a reader (and a
        # later side-by-side) never has to infer the era from a date.
        "selection_era": SELECTION_ERA,
        "gate_go": _read_standouts_gate_go(),
        "plan_count": len(all_plans),
        # MISNOMER, deliberately preserved: `active_count` (and `plans[]`) count every
        # plan the management engine could state, INCLUDING forward-ledger-closed ones.
        # Downstream consumers read that population, so it does not move. `open_count`
        # below is the live subset, and each row carries its own `closed` flag.
        "active_count": len(active_entries),
        "open_count": sum(1 for entry in active_entries if not entry.get("closed")),
        # W1 — how the shipped plans distribute by age (≤7d / 8-21d / >21d, plus the
        # rows whose signal_date could not be read).  Sums to active_count by design —
        # closed rows are bucketed too, because they are in `plans[]` too.
        "active_count_by_age": age_counts,
        # P6 — the order `plans[]` actually ships in, stated where the reader can check
        # it against the `_priority_score` on every row.
        "plans_sort_key": (
            "us_prophet_v1 priority score desc, then plan id asc; a plan with no"
            " numeric priority score sorts below every scored plan and, among those,"
            " by the legacy conviction score"
        ),
        # Lossless intake disclosure.  Every admitted row has a terminal disposition:
        # duplicate, open-plan blocked, explicit validation failure, or originated.
        "intake": {
            "sort_key": "us_prophet_v1 priority score desc, act_level desc, ticker asc",
            "mode": intake_stats.get("mode", "lossless"),
            "reorigination_blocked": intake_stats.get("reorigination_blocked", 0),
            "reorigination_blocked_keys": intake_stats.get(
                "reorigination_blocked_keys", []
            ),
            "open_plan_keys": len(active_keys),
            "admitted": intake_stats.get("admitted"),
            "duplicate_id_blocked": intake_stats.get("duplicate_id_blocked"),
            "eligible_after_skips": intake_stats.get("eligible_after_skips"),
            "cap": intake_stats.get("cap"),
            "cap_applied": intake_stats.get("cap_applied", False),
            "truncated": intake_stats.get("truncated", 0),
            "validation_failed": intake_stats.get("validation_failed", 0),
            "validation_failures": intake_stats.get("validation_failures", []),
            "originated": intake_stats.get("originated", len(new_plans)),
            "unaccounted": intake_stats.get("unaccounted", 0),
            "lossless": intake_stats.get("lossless", False),
            "all_survivors_originated": intake_stats.get(
                "all_survivors_originated", False
            ),
            # ── A1 disclosure: the new admission and every refusal, by name ──────
            "selection_era": intake_stats.get("selection_era", SELECTION_ERA),
            "admitted_statuses": intake_stats.get(
                "admitted_statuses", sorted(ADMITTED_STATUSES)),
            "admitted_directions": intake_stats.get("admitted_directions", []),
            "buy_rows": intake_stats.get("buy_rows", 0),
            "admitted_by_class": intake_stats.get("admitted_by_class", {}),
            "originated_by_class": intake_stats.get("originated_by_class", {}),
            "unknown_status": intake_stats.get("unknown_status", 0),
            "unknown_status_values": intake_stats.get("unknown_status_values", []),
            "refused_status": intake_stats.get("refused_status", {}),
            "refused_direction": intake_stats.get("refused_direction", {}),
            "refused_no_entry_signal": intake_stats.get("refused_no_entry_signal", 0),
            "refused_band_low": intake_stats.get("refused_band_low", 0),
            "refused_tier": intake_stats.get("refused_tier", {}),
            "stale_basis_max": intake_stats.get("stale_basis_max"),
            "stale_basis_skipped": intake_stats.get("stale_basis_skipped", []),
            # ── §6.9 R3 disclosure: zones, the anti-chase refusals, starters ─────
            "zone_class_counts": intake_stats.get("zone_class_counts", {}),
            "zone_conversion_classes": intake_stats.get("zone_conversion_classes", {}),
            "zone_extension_unavailable": intake_stats.get(
                "zone_extension_unavailable", 0),
            "wait_reset": intake_stats.get("wait_reset", []),
            "early_turn_starters": intake_stats.get("early_turn_starters", []),
            "leader_pullback_source": intake_stats.get("leader_pullback_source", []),
            # ── §6.9 R5: the PER-NAME layer over the tallies above ───────────────
            # Everything else in this block is an aggregate — `refused_status` and
            # friends count refusals without keeping a ticker, which is why the
            # subscriber question "why isn't this name on the board?" cannot be answered
            # from them. `refusal_receipts` re-reads the SAME rows through the SAME
            # admission helpers (entry_status / admission_class) and returns the
            # per-name view. Additive and display tier: it reports the gate above, it
            # never moves it. This call site — unlike build_site's — knows tonight's
            # origination run, so it can also disclose the `plan_not_built` cohort.
            "receipts": refusal_receipts(
                _standouts_doc,
                active_keys,
                {str(p.get("asset") or "") for p in new_plans},
            ),
            # The receipt that separates "the organ saw these names and none qualified"
            # from "the organ saw none of them" — a bare zero admission count cannot.
            "leader_pullback_coverage": intake_stats.get(
                "leader_pullback_coverage", {}),
            # ── §6.5 comparison contract: the OLD gate, still accruing ───────────
            "legacy_shadow": {
                "admitted": len(shadow_rows),
                "would_have_planned": sum(
                    1 for r in shadow_rows if r.get("would_have_planned")),
                "cap": LEGACY_N_CANDIDATES,
                "rows_in_part": shadow_written,
                "authority": "none",
            },
            "basis": (
                "Admission is a STATUS CLASS (ANTICIPATION A1): an entry status in"
                " admitted_statuses, a signal tone in admitted_directions, conviction"
                " band above low, and a T1-T3 signal tier. The prior act-level gate is"
                " frozen with zero authority and keeps accruing a legacy shadow ledger"
                " so the two selections can be compared on the same tape. Ranking is"
                " unchanged. Every admitted candidate that is neither a duplicate ID nor"
                " blocked by an open plan is attempted; there is no positional"
                " plan-origination cap. Any candidate that cannot produce a plan is"
                " listed under validation_failures. Every plan carries a"
                " structure-anchored entry zone; the disclosed entry price remains the"
                " point-in-time price-basis close. Featured-board, sector, alert and"
                " portfolio-risk controls are separate and unchanged."
            ),
        },
        # Append-only plan correction projection.  Raw plan JSON files are publication
        # records and never change; corrected dates/dispositions exist only in memory
        # and on this index.  Quarantined plans are excluded from management, action
        # copy and future ledger advancement, but remain fully enumerated here.
        "plan_integrity": {
            "correction_count": len(correction_rows),
            "corrected_plan_count": len(correction_projection.applied_by_plan),
            "corrected_ids": sorted(correction_projection.applied_by_plan),
            "quarantined_count": len(plan_quarantined_ids),
            "quarantined_ids": sorted(plan_quarantined_ids),
            "file": f"data/prophet/{PLAN_CORRECTIONS_FILENAME}",
            "effect": (
                "raw plan publications stay immutable; corrections form the effective "
                "clock view; quarantined plans cannot emit live instructions or ledger rows"
            ),
        },
        "ledger_corrections": {
            "correction_count": len(ledger_correction_rows),
            "corrected_row_count": len(ledger_projection.applied_by_id),
            "corrected_ids": sorted(ledger_projection.applied_by_id),
            "quarantined_ids": sorted(ledger_projection.quarantined_ids),
            "file": f"data/prophet/{LEDGER_CORRECTIONS_FILENAME}",
            "effect": (
                "ledger.jsonl stays append-only; date corrections are projected for "
                "readers and never rehabilitate a quarantined outcome"
            ),
        },
        # ── Forward-ledger quarantine (2026-08-06) ────────────────────────────
        # Rows graded on a clock that predated their own plan. They STAY in
        # ledger.jsonl — it is append-only — and are excluded from every summary.
        "ledger_quarantine": {
            "count": len(_ledger_quarantined_ids),
            "quarantined_on": QUARANTINE_DATE,
            "reason": QUARANTINE_REASON,
            "ids": sorted(_ledger_quarantined_ids),
            "note": quarantine.get("note"),
            "note_zh": quarantine.get("note_zh"),
            "file": f"data/prophet/{QUARANTINE_FILENAME}",
        },
        # The record after both exclusions — quarantined rows, and NO_ENTRY plans
        # whose trigger never confirmed (no position, so neither side of the rate).
        "record": _record,
        "plans": active_entries,
        "note": (
            "DISPLAY-ONLY. All plans are display-tier artifacts. No signal has"
            " passed a forward ledger gate. The word 'validated' is forbidden in"
            " user-facing text. Nightly is the sole advancer of the forward ledger."
        ),
    }
    _write_json(INDEX_PATH, index)
    log.info("build_prophet: wrote index.json (%d active plans)", len(active_entries))

    # ── 4b. Landing showcase slice (public teaser for templates/index.html) ──
    try:
        write_showcase()
    except Exception as e:  # noqa: BLE001
        log.warning("build_prophet: showcase write failed (non-fatal): %s", e)

    # ── 5. Report ─────────────────────────────────────────────────────────────
    log.info("build_prophet: done — %d plans total, %d active", len(all_plans), len(active_entries))
    for e in active_entries:
        log.info(
            "  %s %s | entry=%.2f | inval=%s | T1=%s T2=%s | phase=%s | conf=%s | opt=%s",
            e["asset"],
            e["direction"],
            e.get("entry") or 0,
            e.get("invalidation"),
            e.get("targets", [None])[0] if e.get("targets") else None,
            e.get("targets", [None, None])[1] if len(e.get("targets", [])) > 1 else None,
            e.get("phase"),
            e.get("management_confidence"),
            "Y" if e.get("option_contract") else "N",
        )

    return active_entries


def _read_standouts_gate_go() -> bool:
    """Read gate_go from standouts for the index."""
    try:
        with STANDOUTS_PATH.open(encoding="utf-8") as f:
            return bool(json.load(f).get("gate_go", False))
    except Exception:
        return False


if __name__ == "__main__":
    main()
