"""scripts/build_prophet.py — Prophet Origination Bridge + artifact publisher (W1).

Reads us_standouts.json, originates prophet.trade_plan/v1 envelopes,
runs the management confidence engine for every active plan, and writes:

    site/prophet/index.json          — all active plans + states inline
    site/prophet/plans/<ID>.json     — per-plan artifact
    site/prophet/states/<ID>.json    — per-state artifact
    site/prophet/showcase.json       — public landing teaser: DELAYED winning
                                       calls from the board ledger, never the
                                       live board (templates/index.html
                                       #f-prophet; also --showcase-only)
    data/prophet/ledger.jsonl        — forward outcome ledger (INITIALIZED here;
                                       nightly is the SOLE future advancer)

With --publish, also uploads site/prophet/index.json to R2 key
"prophet/index.json" (mirrors build_options_matrix.py upload pattern).

Usage
-----
    python -m scripts.build_prophet [--date YYYY-MM-DD] [--publish]

Environment variables
---------------------
    THETADATA_STORE        Path to ThetaData EOD store root (optional)
    R2_ENDPOINT            Cloudflare R2 endpoint URL
    R2_ACCESS_KEY_ID       R2 access key
    R2_SECRET_ACCESS_KEY   R2 secret
    R2_BUCKET              R2 bucket name

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
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from engine.prophet_bridge import originate_plans
from engine.prophet_management import compute_management_state
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
    "# Fields: schema, id, asset, direction, signal_date, close_date,\n"
    "#         outcome (T1_HIT|T2_HIT|INVALIDATED|EXPIRED|CLOSED_EARLY),\n"
    "#         stock_result_pct, option_result_pct (null when no rec),\n"
    "#         days_held, plan_adherence, asof\n"
    "# Nightly is the SOLE advancer of this ledger.\n"
)


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

def _load_closed_ids() -> set[str]:
    """Return plan IDs that already have a ledger row (idempotency guard).

    Lines beginning with '#' are header comments (skipped).
    """
    closed: set[str] = set()
    if not LEDGER_PATH.exists():
        return closed
    for line in LEDGER_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            row = json.loads(line)
            plan_id = row.get("id")
            if plan_id:
                closed.add(plan_id)
        except Exception:
            pass
    return closed


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

    Close triggers (in priority order):
      1. INVALIDATED   — any close <= invalidation (BULL) after signal_date
      2. T2_HIT        — any close >= T2 after signal_date
      3. T1_HIT        — any close >= T1 after signal_date (and T2 not yet hit)
      4. EXPIRED       — days since signal_date >= horizon_days

    DESIGN (first-trigger-closes): the loop breaks on the FIRST trigger hit and
    records that outcome permanently.  A plan that touches T1 then later T2 is
    recorded as T1_HIT only.  T2_HIT fires only when the price clears T2 without
    a prior close >= T1 (i.e., a gap day that skips T1).  This is intentional:
    the ledger records first-observable-close outcomes, not eventual maximum reach.
    Ledger consumers must not read T2_HIT frequency as "ever reached T2" — it
    reflects "cleared T2 in a single close without a prior T1 close."

    PIT correctness: `after = price_history_pit[index > sig_ts]` uses strict
    greater-than so the signal day's own close is excluded (plan was not live yet).
    If the PIT frame ends before signal_date + horizon_days, the plan stays open
    indefinitely — this is correct behaviour, not a missed-expiry bug.

    Stock result = (close_price_on_close_date / entry - 1) * 100 (%).
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
    signal_date_str = plan.get("signal_date") or plan.get("_signal_date")

    if entry is None or signal_date_str is None:
        return None, None, None, None

    try:
        sig_ts = pd.Timestamp(signal_date_str)
    except Exception:
        return None, None, None, None

    # Filter to rows strictly AFTER signal_date (the plan wasn't live yet)
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

    for ts, px in closes.items():
        px = float(px)
        days = (ts - sig_ts).days

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

        # Determine close_date from the plan signal_date + days_held
        signal_date_str = plan.get("signal_date") or plan.get("_signal_date")
        close_date_str: str | None = None
        if signal_date_str and days_held is not None:
            try:
                from datetime import timedelta  # noqa: PLC0415
                close_date = date.fromisoformat(signal_date_str) + timedelta(days=days_held)
                close_date_str = close_date.isoformat()
            except Exception:
                close_date_str = asof

        row: dict = {
            "schema": "prophet.ledger/v1",
            "id": plan_id,
            "asset": plan.get("asset"),
            "direction": plan.get("direction"),
            "signal_date": signal_date_str,
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


# ---------------------------------------------------------------------------
# Price history loader (for management engine)
# ---------------------------------------------------------------------------

def _load_price_history_for_management(ticker: str):
    """Load OHLCV price history for the management engine."""
    import pandas as pd  # noqa: PLC0415
    for sub in ["data/baskets/ohlcv", "data/stocks"]:
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
    return None


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
        help="ISO-8601 asof date (sole time anchor; no wall-clock reads beyond this).",
    )
    parser.add_argument(
        "--publish",
        action="store_true",
        help="Also upload site/prophet/index.json to R2.",
    )
    parser.add_argument(
        "--showcase-only",
        action="store_true",
        help="Only (re)write site/prophet/showcase.json from us_standouts.json "
             "— no origination, no management, NO ledger touch. Safe to run "
             "locally at any time.",
    )
    args = parser.parse_args()

    if args.showcase_only:
        write_showcase()
        return None

    asof: str = args.date
    log.info("build_prophet: starting — asof=%s publish=%s", asof, args.publish)

    # ── 0. Initialize ledger ──────────────────────────────────────────────────
    _initialize_ledger()

    # ── 1. Load existing plans (duplicate suppression) ────────────────────────
    existing_plans = _load_existing_plans()
    existing_ids: set[str] = set(existing_plans.keys())
    log.info("build_prophet: %d existing plans loaded", len(existing_ids))

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
    new_plans = originate_plans(
        standouts_path=STANDOUTS_PATH,
        asof=asof,
        existing_ids=existing_ids,
        thetadata_store=thetadata_store,
    )
    log.info("build_prophet: %d new plans originated", len(new_plans))

    # Merge all plans
    all_plans = {**existing_plans}
    for p in new_plans:
        all_plans[p["id"]] = p

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

    for plan_id, plan in all_plans.items():
        ticker = plan.get("asset", "")
        ph = _load_price_history_for_management(ticker)

        if ph is None:
            log.warning(
                "build_prophet: no price history for %s; skipping management", ticker
            )
            # Write plan only
            _write_json(PLANS_DIR / f"{plan_id}.json", plan)
            continue

        # PIT: filter price_history to <= asof
        asof_ts = pd.Timestamp(asof)
        ph_pit = ph[ph.index <= asof_ts]

        if ph_pit.empty:
            log.warning(
                "build_prophet: empty price history for %s up to %s", ticker, asof
            )
            _write_json(PLANS_DIR / f"{plan_id}.json", plan)
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
            _write_json(PLANS_DIR / f"{plan_id}.json", plan)
            continue

        # Write artifacts
        _write_json(PLANS_DIR / f"{plan_id}.json", plan)
        _write_json(STATES_DIR / f"{plan_id}.json", state)

        # Rebuild what_to_do_now and profit_plan with the phase resolved by the
        # management engine (phase may differ from what originate_plans stored).
        # Thesis is already in the plan dict if originated by new code; leave it
        # as-is for pre-existing plans that lack it.
        from engine.prophet_bridge import (  # noqa: PLC0415
            _build_what_to_do_now,
            _build_profit_plan,
        )
        resolved_phase = state.get("phase") or plan.get("phase", "pre_trigger")
        t1 = plan["targets"][0] if plan.get("targets") else None
        t2 = plan["targets"][1] if plan.get("targets") and len(plan["targets"]) > 1 else None
        what_to_do_now = _build_what_to_do_now(
            phase=resolved_phase,
            entry=plan.get("entry"),
            trigger=plan.get("trigger"),
            invalidation=plan.get("invalidation"),
            t1=t1,
            t2=t2,
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
            "_signal_date": plan.get("_signal_date"),
            "phase": resolved_phase,
            "management_confidence": state.get("management_confidence"),
            "recommended_action": state.get("recommended_action"),
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
            "what_to_do_now": what_to_do_now,
            "profit_plan": profit_plan,
            "thesis": plan.get("thesis") or "",  # originated by prophet_bridge.py
            # ZH half of the thesis — whitelisted by OEU M-PRO so the bilingual pair
            # the originator already writes actually reaches the payload (house law:
            # every EN string ships with its ZH pair). Older plans lack the key → "".
            "thesis_zh": plan.get("thesis_zh") or "",
            # PSQ-TILT W1 provenance (whitelisted so the Terminal can consume it).
            "horizon_days": plan.get("horizon_days"),
            "stage_tilt": plan.get("stage_tilt"),
        })

    # ── 3b. Advance ledger (nightly-only — idempotent close-event writer) ────────
    # Must run AFTER all plans + price histories have been processed so we have
    # a complete all_plans dict.  Nightly is the SOLE caller of advance_ledger().
    try:
        advance_ledger(all_plans, asof)
    except Exception as e:
        log.warning("build_prophet: ledger advancement failed (non-fatal): %s", e)

    # ── 4. Write index.json ───────────────────────────────────────────────────
    # Sort for determinism: conviction desc, then plan id asc (same-inputs-same-output).
    active_entries.sort(
        key=lambda e: (-(e.get("_conviction_score") or 0), e.get("id", "")),
    )
    index: dict[str, Any] = {
        "schema": "prophet.index/v1",
        "asof": asof,
        "cadence": "nightly-EOD",
        "authority_tier": "display",
        "gate_go": _read_standouts_gate_go(),
        "plan_count": len(all_plans),
        "active_count": len(active_entries),
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

    # ── 5. R2 publish ─────────────────────────────────────────────────────────
    if args.publish:
        s3 = _r2_client()
        if s3:
            bucket = os.environ.get("R2_BUCKET", "mastermindx")
            _upload_r2(s3, bucket, INDEX_PATH, R2_INDEX_KEY)
        else:
            log.warning("build_prophet: --publish set but R2 creds unavailable; skipping")

    # ── 6. Report ─────────────────────────────────────────────────────────────
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
