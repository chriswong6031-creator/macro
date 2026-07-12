"""Alt-data falsifiable ledger — what EARNS alt-data a scored vote.

Every cross-signal CONVERGENCE (a ticker lit by >=2 independent alt-data channels)
becomes a DATED, BENCHMARKED, FALSIFIABLE thesis:

    "alt-data convergence on X  =>  X beats SPY over the next ~63 trading days"

We log it on the detection day with entry levels snapshotted, then grade it vs SPY
once the window elapses — reusing the EXACT engine.ai_desk_scorer evaluators (no new
scoring code, no LLM). This is the honest path into the score / model layer: the
signal earns a vote only after the track record shows it predicts forward returns.
Until then it stays display/context-only (conviction starts 'low', never sized).

  data/altdata/theses.jsonl       append-only falsifiable theses (we own this)
  data/altdata/scored.jsonl       one outcome row per matured thesis (idempotent)
  data/altdata/track_record.json  rolling hit-rate the page + brain read back

Only SCORABLE names are logged: the ticker AND SPY must have a price series. Thin /
private vehicles (ABTC, WLFI, …) are recorded in by_ticker but never scored.

Per-channel claim families (ALTDATA_REBOOT W2, active 2026-07-12):
  Each thesis is tagged with a claim_family based on the HIGHEST-WEIGHT channel present.
  This routes to pre-registered horizon rulers in the qledger. See research/ALTDATA_REBOOT.md.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone, timedelta
from pathlib import Path

from lib import config
from engine import ai_desk as _desk
from engine import ai_desk_scorer as _scorer

log = logging.getLogger(__name__)

HORIZON_D = 63          # ~3 trading months — alt-data flow signals are medium-horizon
_CAL_DAYS = 91          # ≈ 63 trading days in calendar days (for the check_by date)
THRESHOLD = -0.05       # falsified iff the name UNDERperforms SPY by >5% over the window
MIN_SCORE = 2
BENCH = "SPY"
SCHEMA = "altdata_track_record.v1"

# ---------------------------------------------------------------------------
# Per-channel family routing (ALTDATA_REBOOT W2 — research/ALTDATA_REBOOT.md)
# Assignment: highest-weight channel present on the thesis → family.
# Horizon rulers are PRE-REGISTERED; see masterplan for the promotion gate.
# ---------------------------------------------------------------------------

# Lazy import to avoid circular imports at module load.
def _channel_weights() -> dict[str, float]:
    from engine.altdata_models import CHANNEL_WEIGHTS
    return CHANNEL_WEIGHTS


# Family → set of channels that trigger it (when that channel has the highest weight).
_FAMILY_CHANNELS: list[tuple[str, set]] = [
    # ordered by descending max-weight in the family (so the highest-priority
    # family is tested first in the rare tie-breaking edge cases).
    ("altdata_event", {
        "special_situation", "material_8k", "gov_contract", "gov_contract_accel",
        "gov_grant", "gov_grant_accel", "fda_approval", "fda_label_expansion",
        "clinical_phase3_start", "activist_13d",
        # previously unmapped — event-horizon catalysts (earnings beats, FDA-adjacent)
        "github_momentum", "hf_model_momentum", "earnings_beat",
    }),
    ("altdata_flow", {
        "darkpool_accum", "unusual_options",
    }),
    ("altdata_mid", {
        "insider_cluster", "insider_buy", "app_demand",
        "analyst_upgrade_cluster", "insider_mspr",
        # previously unmapped — mid-horizon, attention-adjacent but attention dormant
        "cnbc_pick", "news_sentiment",
    }),
    ("altdata_slow", {
        "congress_cluster", "congress_buy", "trump", "lobbying", "lobbying_spike",
        "smart_money_13f", "13f_add", "patent_cluster", "affiliation",
        # previously unmapped — legislation horizon (multi-month catalyst window)
        "bill_catalyst",
    }),
    ("altdata_attention", {
        "retail_buzz",
    }),
]

# Per-family horizon_d (pre-registered; must match masterplan §1).
FAMILY_HORIZON_D: dict[str, int] = {
    "altdata_event": 21,
    "altdata_flow": 21,
    "altdata_mid": 63,
    "altdata_slow": 63,
    "altdata_attention": 5,
}

# Per-family direction override (attention reverses — fade the buzz).
# +1 means "use the thesis lean"; ATTENTION overrides to -1 regardless of lean.
FAMILY_DIRECTION_OVERRIDE: dict[str, int | None] = {
    "altdata_event": None,
    "altdata_flow": None,
    "altdata_mid": None,
    "altdata_slow": None,
    "altdata_attention": -1,  # pre-registered fade construction
}

# Per-family cooldown in business days after check_by before same ticker re-opens.
FAMILY_COOLDOWN_BD: dict[str, int] = {
    "altdata_event": 21,
    "altdata_flow": 21,
    "altdata_mid": 63,
    "altdata_slow": 63,
    "altdata_attention": 5,
}

# Channel lookup: channel → family name (built once at module load time).
def _build_channel_to_family() -> dict[str, str]:
    out: dict[str, str] = {}
    for family, channels in _FAMILY_CHANNELS:
        for ch in channels:
            out[ch] = family
    return out


_CHANNEL_TO_FAMILY: dict[str, str] = _build_channel_to_family()


def assign_claim_family(channels: list[str]) -> str:
    """Return the claim_family for a thesis based on its highest-weight channel.

    Deterministic: ties broken by family order in _FAMILY_CHANNELS (highest-weight
    family wins). Unmapped channels map to 'altdata_mid' (safer mid-horizon fallback;
    event family has the narrowest 21d window which is wrong for truly unknown channels).
    Mapped channels: see _FAMILY_CHANNELS for the complete routing table including
    github_momentum/hf_model_momentum/earnings_beat → event; cnbc_pick/news_sentiment →
    mid; bill_catalyst → slow.
    """
    if not channels:
        return "altdata_event"
    weights = _channel_weights()
    best_ch = max(channels, key=lambda c: weights.get(c, 0.2))
    family = _CHANNEL_TO_FAMILY.get(best_ch)
    if family is None:
        log.warning("altdata_ledger: unmapped channel %r → altdata_mid (unknown horizon; "
                    "routes to mid as safer fallback)", best_ch)
        return "altdata_mid"
    return family

_LEDGER = ("data", "altdata", "theses.jsonl")
_SCORED = ("data", "altdata", "scored.jsonl")
_TRACK = ("data", "altdata", "track_record.json")


def _p(root, parts):
    return Path(root).joinpath(*parts)


def _active_subjects(ledger_rows: list, asof: str) -> set:
    """(ticker, family) pairs with a thesis whose window has NOT elapsed yet.

    Dedup is per-(ticker, family) so a ticker may hold theses in different families
    simultaneously (required for W3 independent attention emission). Per-family cooldown
    after expiry is handled separately by _cooldown_blocked.
    """
    return {
        (r.get("ticker"), r.get("claim_family") or "altdata")
        for r in ledger_rows
        if r.get("ticker") and str(r.get("check_by", "")) >= asof
    }


def _cooldown_blocked(ledger_rows: list, asof: str) -> set[tuple[str, str]]:
    """(ticker, family) pairs blocked by the episode cooldown window.

    After a thesis's check_by date passes, the same (ticker, family) is blocked for
    FAMILY_COOLDOWN_BD business days. Returns the set of (ticker, family) pairs
    that should NOT receive a new thesis on asof.
    """
    import pandas as pd
    blocked: set[tuple[str, str]] = set()
    try:
        asof_ts = pd.Timestamp(asof)
    except Exception:  # noqa: BLE001
        return blocked

    for r in ledger_rows:
        tk = r.get("ticker")
        fam = r.get("claim_family") or "altdata"
        check_by_str = r.get("check_by")
        if not tk or not check_by_str:
            continue
        try:
            check_by_ts = pd.Timestamp(check_by_str)
        except Exception:  # noqa: BLE001
            continue
        # Window still open → covered by _active_subjects; skip here
        if check_by_ts >= asof_ts:
            continue
        # Cooldown period after expiry
        cooldown_bd = FAMILY_COOLDOWN_BD.get(fam, 63)
        try:
            cutoff = (check_by_ts + pd.offsets.BusinessDay(cooldown_bd)).normalize()
        except Exception:  # noqa: BLE001
            continue
        if asof_ts < cutoff:
            blocked.add((tk, fam))
    return blocked


def _thesis_check_by(family: str, today: date) -> str:
    """Compute check_by date for a thesis given its family (determines horizon_d)."""
    import pandas as pd
    horizon_d = FAMILY_HORIZON_D.get(family, HORIZON_D)
    # calendar-day approximation: horizon_d business days ≈ horizon_d * 7/5 calendar days
    cal_days = int(horizon_d * 7 / 5) + 1
    # Use pandas for accuracy
    try:
        check_by = (pd.Timestamp(str(today)) + pd.offsets.BusinessDay(horizon_d)).date().isoformat()
    except Exception:  # noqa: BLE001
        check_by = (today + timedelta(days=cal_days)).isoformat()
    return check_by


def build_theses(by_ticker: dict, root=None, today=None) -> list:
    root = Path(root) if root else config.ROOT
    today = today or date.today()
    asof = str(today)
    existing = _scorer._load_jsonl(_p(root, _LEDGER))
    active = _active_subjects(existing, asof)
    cooldown_blocked = _cooldown_blocked(existing, asof)
    existing_ids = {r.get("id") for r in existing}

    new = []
    for tk, rec in (by_ticker.get("tickers") or {}).items():
        score = int(rec.get("convergence_score", 0) or 0)
        if score < MIN_SCORE:
            continue
        e0 = _desk._level_asof(tk, root, asof)
        b0 = _desk._level_asof(BENCH, root, asof)
        if e0 is None or b0 is None:        # not SCORABLE (thin / private) -> skip, never score
            continue
        chans = rec.get("channels", [])

        # ALTDATA_REBOOT W2: assign per-channel family and horizon
        family = assign_claim_family(chans)
        # Per-(ticker, family) active dedup: skip if already open in this family
        if (tk, family) in active:
            log.debug("altdata ledger: %s/%s already active — skipping", tk, family)
            continue
        if (tk, family) in cooldown_blocked:
            log.debug("altdata ledger: %s/%s in cooldown — skipping", tk, family)
            continue

        horizon_d = FAMILY_HORIZON_D.get(family, HORIZON_D)
        check_by = _thesis_check_by(family, today)

        rid = f"{asof}-{tk}-altconv"
        if rid in existing_ids:
            continue

        # Direction: most theses are overweight; attention family reverses
        direction_override = FAMILY_DIRECTION_OVERRIDE.get(family)
        lean = "overweight" if direction_override is None else (
            "underweight" if direction_override == -1 else "overweight"
        )

        # Build falsifier check with correct semantics for direction.
        # LONG (direction=+1): falsified iff realized < -THRESHOLD (underperforms SPY by >5%)
        #   → op="<", threshold=THRESHOLD (negative)
        # FADE (direction=-1): falsified iff realized > +abs(THRESHOLD) (stock RISES vs SPY)
        #   → op=">", threshold=+abs(THRESHOLD), text updated to fade semantics
        if direction_override == -1:
            _check_op = ">"
            _check_threshold = abs(THRESHOLD)
            _falsifier_text = (
                f"{tk} fails to underperform {BENCH} — fade thesis broken "
                f"(outperforms by >{abs(THRESHOLD) * 100:.0f}% over ~{horizon_d} trading days "
                f"despite {score}-channel retail-buzz convergence ({', '.join(chans)}))."
            )
        else:
            _check_op = "<"
            _check_threshold = THRESHOLD
            _falsifier_text = (
                f"{tk} fails to beat {BENCH} (underperforms by >{abs(THRESHOLD) * 100:.0f}%) "
                f"over ~{horizon_d} trading days despite {score}-channel convergence "
                f"({', '.join(chans)})."
            )

        new.append({
            "id": rid, "ticker": tk, "logged_at": datetime.now(timezone.utc).isoformat(),
            "state_asof": asof,
            "subject": f"{tk} alt-data convergence",
            "lean": lean, "conviction": "low", "horizon_d": horizon_d,
            "claim_family": family,
            "convergence_score": score, "channels": chans,
            "trump_linked": bool(rec.get("trump_linked")),
            "falsifier": {
                "text": _falsifier_text,
                "text_zh": None,  # future: add Chinese translation
                "check": {"kind": "rel_return", "subject_ticker": tk, "vs": BENCH,
                          "op": _check_op, "threshold": _check_threshold,
                          "horizon_d": horizon_d},
            },
            "check_by": check_by,
            "entry_levels": {tk: e0, BENCH: b0},
            "status": "open", "scored_at": None, "outcome": None, "realized": None,
        })
    if new:
        path = _p(root, _LEDGER)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a") as fh:
            for r in new:
                fh.write(json.dumps(r, default=str) + "\n")
        log.info("altdata ledger: logged %d new thesis(es): %s",
                 len(new), ", ".join(r["ticker"] for r in new))
    return new


def score(root=None, today=None) -> dict | None:
    try:
        root = Path(root) if root else config.ROOT
        today = today or date.today()
        ledger = _scorer._dedupe_by_id(_scorer._load_jsonl(_p(root, _LEDGER)))
        already = _scorer._dedupe_by_id(_scorer._load_jsonl(_p(root, _SCORED)))
        new_rows = []
        for tid, row in ledger.items():
            if tid in already:
                continue
            res = _scorer._score_one(row, root, today)   # reuse the exact evaluator
            if res is not None:
                new_rows.append(res)
        combined = list(_scorer._dedupe_by_id(list(already.values()) + new_rows).values())
        track = _scorer._aggregate(combined, ledger, today)
        track["schema"] = SCHEMA
        track["note"] = ("Alt-data convergence theses graded vs SPY. Context-only — the signal "
                         "earns a scored vote only once this track record shows forward edge.")

        sp = _p(root, _SCORED)
        sp.parent.mkdir(parents=True, exist_ok=True)
        if new_rows:
            with open(sp, "a") as fh:
                for r in new_rows:
                    fh.write(json.dumps(r, default=str) + "\n")
        _p(root, _TRACK).write_text(json.dumps(track, indent=2, default=str))
        # derive from root (== config.ROOT in prod) so root=tmp_path tests
        # don't overwrite the tracked site/altdata/track_record.json
        site = root / "site" / "altdata"
        site.mkdir(parents=True, exist_ok=True)
        (site / "track_record.json").write_text(json.dumps(track, indent=2, default=str))
        if new_rows:
            log.info("altdata ledger: scored %d (%s)", len(new_rows),
                     ", ".join(f"{r['id']}:{r['outcome']}" for r in new_rows))
        return track
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("altdata ledger score failed: %s", e)
        return None


def load_track(root=None) -> dict:
    p = _p(root or config.ROOT, _TRACK)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except Exception:  # noqa: BLE001
        return {}


def rebuild(by_ticker: dict, root=None, today=None) -> dict | None:
    build_theses(by_ticker, root=root, today=today)
    return score(root=root, today=today)


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    logging.basicConfig(level=logging.INFO)
    from engine import altdata_signals
    bt = altdata_signals.load()
    t = rebuild(bt) if bt else None
    print(json.dumps(t, indent=2) if t else "altdata_ledger: no by_ticker substrate yet")
