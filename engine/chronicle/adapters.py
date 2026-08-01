"""engine.chronicle.adapters — 5 of the 7 Chronicle source adapters.

(regime_flip lives in state_log.py because it derives from the
state_log.jsonl forward-capture ledger rather than a directly-committed source
file: world_state.json genuinely has no committed dated history, so state_log
exists to capture one dated snapshot per nightly run. risk_band moved HERE in
the B6 adversarial-review correction: the original W0 build derived it from
state_log too, but a real committed, dated, source-native risk-state series
already exists — data/risk_radar/forward_log.jsonl (20+ rows, one per trading
day) — so risk_band is a normal file adapter like the other 4, fully
rebuildable byte-stable from committed history with no forward-capture
ledger involved.)

Each adapter is a pure(-ish, filesystem-read-only) function:

    adapt_X(repo: Path) -> tuple[list[dict], str | None]

returning (events, gap_note). Fail-soft per masterplan §0: an absent/unreadable
source degrades to ([], "<gap note>") — never an exception. A malformed
individual row/item is skipped (counted, not fatal) rather than aborting the
whole adapter, so one bad line never blanks an otherwise-good source.

No LLM calls. No network. Read-only over committed repo artifacts.

The evidence-addressed earnings-call adapter lives in earnings_calls.py beside
the nightly-only projection it reads; this module retains the five original
direct-source adapters.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

from . import schema

log = logging.getLogger(__name__)

_CLOSE_WEIGHT_2 = frozenset({"T1_HIT", "T2_HIT", "INVALIDATED"})


# ─────────────────────────────────────────────────────────────────────────────
# 1. research_vault — data/research_vault/catalog.json
# ─────────────────────────────────────────────────────────────────────────────

def adapt_research_vault(repo: Path) -> tuple[list[dict], str | None]:
    rel = Path("data") / "research_vault" / "catalog.json"
    path = repo / rel
    if not path.exists():
        return [], f"{rel} absent"
    try:
        raw = path.read_text(encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        return [], f"{rel} unreadable: {exc}"
    try:
        catalog = json.loads(raw)
    except Exception as exc:  # noqa: BLE001
        return [], f"{rel} not valid JSON: {exc}"

    items = catalog.get("items") if isinstance(catalog, dict) else None
    if not isinstance(items, list):
        return [], f"{rel} malformed (no 'items' list)"

    # M8: every vault item that lands a page gets one at site/research/<slug>.html
    # (scripts/build_research_pages.py). slug_map() is the SAME deterministic
    # id->slug function the site builder uses (pure function of the ordered
    # items list), so this reproduces the real published URL exactly — imported
    # from the stdlib-only engine.research_vault.slugs, NEVER through the page
    # renderer. Routing through the renderer made THIS ADAPTER'S OUTPUT depend on
    # the runner's installed packages: the import below is fail-soft, so a heavy
    # module-scope dependency over there (jinja2, historically) silently blanked
    # links.site on all 105 vault events in ci.yml's minimal-deps chronicle lane,
    # so a rebuild there produced different bytes than a rebuild anywhere else —
    # exactly what a store-vs-rebuild gate compares. Deferring jinja2 (#3648)
    # fixed that one dependency; importing the leaf module closes the class.
    slug_by_id: dict[str, str] = {}
    slug_gap: str | None = None
    try:
        from engine.research_vault.slugs import slug_map  # noqa: PLC0415
        slug_by_id = slug_map(items)
    except Exception as exc:  # noqa: BLE001
        # Fail-soft, but NEVER silent. As a log.debug this blanked every
        # links.site indistinguishably from "the catalog legitimately has no
        # pages", which is how it survived long enough to be committed into the
        # store. Surfacing it as an adapter gap note puts the null in the
        # manifest, where the house epistemics law wants it.
        slug_gap = (f"links.site unavailable for all {len(items)} item(s) — "
                    f"slug_map import failed ({type(exc).__name__}: {exc})")
        log.warning("chronicle.research_vault: %s", slug_gap)

    events: list[dict] = []
    skipped = 0
    facts_dropped = 0
    for item in items:
        if not isinstance(item, dict):
            skipped += 1
            continue
        try:
            item_id = str(item.get("id") or "").strip()
            published_at = str(item.get("published_at") or "").strip()
            date = published_at[:10] if len(published_at) >= 10 else ""
            if not item_id or not date:
                skipped += 1
                continue
            institution = str(item.get("institution") or "").strip()
            raw_title = str(item.get("title") or "").strip()
            title = f"{institution}: {raw_title}" if institution and raw_title else (raw_title or institution or "(untitled report)")
            top_pick = bool(item.get("top_pick"))
            ts = published_at if "T" in published_at else f"{date}T00:00:00Z"
            raw_facts = item.get("summary_points") or []
            site_slug = slug_by_id.get(item_id)
            ev = schema.new_event(
                id=schema.make_id("research_vault", item_id, date),
                ts=ts,
                date=date,
                source="research_vault",
                source_ref=item_id,
                kind="report",
                title=title,
                facts=raw_facts,
                tickers=item.get("tickers") or [],
                themes=item.get("tags") or [],  # M6: was always [] -- silently dropped the catalog's own tags
                weight_hint=3 if top_pick else 2,
                links=schema.make_links(site=f"/research/{site_slug}.html" if site_slug else None),
            )
            n_raw_facts = len([f for f in raw_facts if str(f or "").strip()])
            if len(ev["facts"]) < n_raw_facts:
                facts_dropped += n_raw_facts - len(ev["facts"])
            events.append(ev)
        except Exception as exc:  # noqa: BLE001
            log.debug("chronicle.research_vault: skipped item: %s", exc)
            skipped += 1
            continue

    gap_bits = []
    if skipped:
        gap_bits.append(f"{skipped} malformed/incomplete catalog item(s) skipped")
    if facts_dropped:
        gap_bits.append(f"{facts_dropped} fact(s) dropped (too short after word-boundary truncation)")
    if slug_gap:
        gap_bits.append(slug_gap)
    gap = "; ".join(gap_bits) if gap_bits else None
    return events, gap


# ─────────────────────────────────────────────────────────────────────────────
# 2. prophet_ledger — data/prophet/ledger.jsonl
# ─────────────────────────────────────────────────────────────────────────────

def adapt_prophet_ledger(repo: Path) -> tuple[list[dict], str | None]:
    rel = Path("data") / "prophet" / "ledger.jsonl"
    path = repo / rel
    if not path.exists():
        return [], f"{rel} absent"
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception as exc:  # noqa: BLE001
        return [], f"{rel} unreadable: {exc}"

    events: list[dict] = []
    skipped = 0
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            row = json.loads(line)
        except Exception:  # noqa: BLE001
            skipped += 1
            continue
        try:
            outcome = row.get("outcome")
            close_date = row.get("close_date")
            row_id = str(row.get("id") or "").strip()
            asset = str(row.get("asset") or "").strip()
            if not outcome or not close_date or not row_id or not asset:
                # Still-open plan (close_date/outcome null) or malformed row —
                # not a close event yet, not an error either.
                continue
            close_date = str(close_date)[:10]
            direction = str(row.get("direction") or "").strip()
            stock_pct = row.get("stock_result_pct")
            option_pct = row.get("option_result_pct")
            days_held = row.get("days_held")

            # M3: stock_result_pct is a RAW price-direction move
            # ((close/entry-1)*100 for BOTH directions, scripts/build_prophet.py)
            # -- sign-adjust so the number reflects the PLAN's result, not the
            # underlying's raw move. A BEAR plan that HITS ITS TARGET on a
            # price DECLINE must render as a gain, not a loss.
            plan_pct = stock_pct
            if isinstance(stock_pct, (int, float)) and direction == "BEAR":
                plan_pct = stock_pct * -1

            pct_str = f"{plan_pct:+.1f}%" if isinstance(plan_pct, (int, float)) else "n/a"
            days_str = f"{days_held}d" if isinstance(days_held, (int, float)) else "n/a"
            title = f"Prophet close: {asset} {direction} → {outcome} ({pct_str} in {days_str})"

            fact_bits = [f"outcome={outcome}"]
            if isinstance(plan_pct, (int, float)):
                fact_bits.append(f"stock {plan_pct:+.2f}% (plan result)")
            if isinstance(option_pct, (int, float)):
                fact_bits.append(f"option {option_pct:+.2f}%")
            if isinstance(days_held, (int, float)):
                fact_bits.append(f"held {int(days_held)}d")
            fact = "; ".join(fact_bits)

            weight = 2 if outcome in _CLOSE_WEIGHT_2 else 1
            ev = schema.new_event(
                id=schema.make_id("prophet_ledger", row_id, close_date),
                ts=f"{close_date}T00:00:00Z",
                date=close_date,
                source="prophet_ledger",
                source_ref=row_id,
                kind="signal_close",
                title=title,
                facts=[fact],
                tickers=[asset],
                themes=[],
                weight_hint=weight,
                links=schema.make_links(),
            )
            events.append(ev)
        except Exception as exc:  # noqa: BLE001
            log.debug("chronicle.prophet_ledger: skipped row: %s", exc)
            skipped += 1
            continue

    gap = f"{skipped} malformed ledger row(s) skipped" if skipped else None
    return events, gap


# ─────────────────────────────────────────────────────────────────────────────
# 3. macro_release — data/release_forecast/forward_ledger.jsonl
# ─────────────────────────────────────────────────────────────────────────────

def adapt_macro_release(repo: Path) -> tuple[list[dict], str | None]:
    rel = Path("data") / "release_forecast" / "forward_ledger.jsonl"
    path = repo / rel
    if not path.exists():
        return [], f"{rel} absent"
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception as exc:  # noqa: BLE001
        return [], f"{rel} unreadable: {exc}"

    # m7: "reaction" rows never carry the print value itself -- join the
    # "scored" rows on (release, release_date) and lift ONLY the public-safe
    # actual/raw_initial_print field. Grade fields on scored rows
    # (interval_hit, skew_hit, our_surprise, ...) are deliberately left out --
    # those are forecast-accuracy internals, not part of the public-safe
    # projection this spine ships.
    actual_by_key: dict[tuple[str, str], float] = {}
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            row = json.loads(line)
        except Exception:  # noqa: BLE001
            continue
        if not isinstance(row, dict) or row.get("row_type") != "scored":
            continue
        rel_name = str(row.get("release") or "").strip()
        rel_date = str(row.get("release_date") or "").strip()[:10]
        if not rel_name or not rel_date:
            continue
        actual = row.get("actual")
        if not isinstance(actual, (int, float)):
            actual = row.get("raw_initial_print")
        if isinstance(actual, (int, float)):
            actual_by_key.setdefault((rel_name, rel_date), actual)

    events: list[dict] = []
    seen: set[tuple[str, str]] = set()
    skipped = 0
    n_joined = 0
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            row = json.loads(line)
        except Exception:  # noqa: BLE001
            skipped += 1
            continue
        try:
            # Only "reaction" rows carry the realized market reaction;
            # projection/shadow_projection are pre-print forecasts and "scored"
            # is a forecast-accuracy grade — neither is the print event itself.
            if row.get("row_type") != "reaction":
                continue
            release = str(row.get("release") or "").strip()
            release_date = str(row.get("release_date") or "").strip()[:10]
            if not release or not release_date:
                skipped += 1
                continue
            key = (release, release_date)
            if key in seen:
                continue  # dedupe by (release, release_date); keep first (file order)
            seen.add(key)

            actual = actual_by_key.get(key)
            actual_str = f"{actual:+g}" if isinstance(actual, (int, float)) else None
            if actual_str is not None:
                n_joined += 1

            facts: list[str] = []
            if actual_str is not None:
                facts.append(f"actual {actual_str}")
            dgs10 = row.get("dgs10_h0_bp")
            if isinstance(dgs10, (int, float)):
                facts.append(f"10y {dgs10:+.1f}bp")
            spread = row.get("spread_2s10s_h0_bp")
            if isinstance(spread, (int, float)):
                facts.append(f"2s10s {spread:+.1f}bp")
            spy0 = row.get("spy_h0_pct")
            if isinstance(spy0, (int, float)):
                facts.append(f"SPY day-0 {spy0:+.2f}%")
            spy1 = row.get("spy_h1_pct")
            if isinstance(spy1, (int, float)):
                facts.append(f"SPY day-1 {spy1:+.2f}%")
            dollar0 = row.get("dollar_h0_pct")
            if isinstance(dollar0, (int, float)):
                facts.append(f"Dollar day-0 {dollar0:+.2f}%")

            weight = 2 if isinstance(spy0, (int, float)) and abs(spy0) >= 1.0 else 1
            source_ref = f"{release}#{release_date}"
            title = (f"Macro print: {release} = {actual_str} ({release_date})" if actual_str is not None
                      else f"Macro print: {release} ({release_date})")
            ev = schema.new_event(
                id=schema.make_id("macro_release", source_ref, release_date),
                ts=f"{release_date}T00:00:00Z",
                date=release_date,
                source="macro_release",
                source_ref=source_ref,
                kind="print",
                title=title,
                facts=facts,
                tickers=[],
                themes=[release],  # M6: was always [] -- the release name is a natural theme
                weight_hint=weight,
                links=schema.make_links(),
            )
            events.append(ev)
        except Exception as exc:  # noqa: BLE001
            log.debug("chronicle.macro_release: skipped row: %s", exc)
            skipped += 1
            continue

    gap_bits = []
    if skipped:
        gap_bits.append(f"{skipped} malformed forward-ledger row(s) skipped")
    if events:
        gap_bits.append(f"{n_joined}/{len(events)} release event(s) joined to a scored actual print")
    gap = "; ".join(gap_bits) if gap_bits else None
    return events, gap


# ─────────────────────────────────────────────────────────────────────────────
# 4. earnings — data/earnings/earnings.parquet
# ─────────────────────────────────────────────────────────────────────────────

def _parse_us_date(s: str) -> str:
    """Parse 'M/D/YYYY' -> 'YYYY-MM-DD'. Raises ValueError on unparsable input."""
    dt = datetime.strptime(s.strip(), "%m/%d/%Y")
    return dt.strftime("%Y-%m-%d")


def adapt_earnings(repo: Path) -> tuple[list[dict], str | None]:
    rel = Path("data") / "earnings" / "earnings.parquet"
    path = repo / rel
    if not path.exists():
        return [], f"{rel} absent"
    try:
        import pandas as pd  # noqa: PLC0415
        df = pd.read_parquet(path)
    except Exception as exc:  # noqa: BLE001
        return [], f"{rel} unreadable: {exc}"

    events: list[dict] = []
    skipped = 0
    tickers_with_events = 0
    total_tickers = len(df)

    for ticker, row in df.iterrows():
        sj = row.get("surprises_json") if hasattr(row, "get") else None
        if sj is None:
            continue
        try:
            parsed = json.loads(sj) if isinstance(sj, str) else sj
        except Exception:  # noqa: BLE001
            skipped += 1
            continue
        if not isinstance(parsed, list) or not parsed:
            continue

        ticker_str = str(ticker).strip()
        had_event = False
        for entry in parsed:
            if not isinstance(entry, dict):
                continue
            reported = entry.get("reported")
            eps = entry.get("eps")
            if not reported or eps is None:
                # Not yet reported / malformed entry — skip, never fabricate.
                continue
            try:
                reported_date = _parse_us_date(str(reported))
            except Exception:  # noqa: BLE001
                skipped += 1
                continue

            consensus = entry.get("consensus")
            surprise_pct = entry.get("surprise_pct")
            qtr = entry.get("qtr")

            fact_bits = []
            if qtr:
                fact_bits.append(str(qtr))
            fact_bits.append(f"EPS {eps}")
            if consensus is not None:
                fact_bits.append(f"est {consensus}")
            if isinstance(surprise_pct, (int, float)):
                fact_bits.append(f"surprise {surprise_pct:+.1f}%")
            fact = " · ".join(fact_bits)

            weight = 2 if isinstance(surprise_pct, (int, float)) and abs(surprise_pct) >= 10 else 1
            source_ref = f"{ticker_str}#{reported_date}"
            try:
                ev = schema.new_event(
                    id=schema.make_id("earnings", source_ref, reported_date),
                    ts=f"{reported_date}T00:00:00Z",
                    date=reported_date,
                    source="earnings",
                    source_ref=source_ref,
                    kind="earnings",
                    title=f"Earnings: {ticker_str} actual vs est",
                    facts=[fact],
                    tickers=[ticker_str],
                    themes=["earnings"],  # M6: fixed tag; no committed ticker->sector mapping is
                                          # wired in here (see adapter docstring — do NOT invent one)
                    weight_hint=weight,
                    links=schema.make_links(),
                )
            except Exception as exc:  # noqa: BLE001
                log.debug("chronicle.earnings: skipped entry: %s", exc)
                skipped += 1
                continue
            events.append(ev)
            had_event = True
        if had_event:
            tickers_with_events += 1

    notes = [f"coverage: {tickers_with_events}/{total_tickers} tickers carried reported surprises"]
    if skipped:
        notes.append(f"{skipped} malformed surprise entries skipped")
    gap = "; ".join(notes)  # always emitted — honest coverage census, not just an error signal
    return events, gap


# ─────────────────────────────────────────────────────────────────────────────
# 5. risk_band — data/risk_radar/forward_log.jsonl (B6 correction)
# ─────────────────────────────────────────────────────────────────────────────
#
# B6: the original W0 build derived risk_band from state_log.jsonl's forward
# capture of world_state's intl_risk.em_stress_state — but a REAL committed,
# dated, source-native risk-state series already exists:
# data/risk_radar/forward_log.jsonl, one row per trading day, e.g.
# {"asof":"2026-06-23","state":"caution","alert":false,"dominant_scare":
# "growth","top_score":68.9,...}. That gives risk_band real backfilled
# history AND full gate-1 rebuildability (byte-stable from committed history,
# no forward-capture ledger involved) — unlike world_state, which genuinely
# has no committed dated history (that's why regime_flip still needs
# state_log; see that module's docstring).

def adapt_risk_band(repo: Path) -> tuple[list[dict], str | None]:
    rel = Path("data") / "risk_radar" / "forward_log.jsonl"
    path = repo / rel
    if not path.exists():
        return [], f"{rel} absent"
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception as exc:  # noqa: BLE001
        return [], f"{rel} unreadable: {exc}"

    rows: list[dict] = []
    skipped = 0
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except Exception:  # noqa: BLE001
            skipped += 1
            continue
        if isinstance(row, dict) and row.get("asof") and row.get("state"):
            rows.append(row)
        else:
            skipped += 1
    rows.sort(key=lambda r: str(r.get("asof") or ""))

    events: list[dict] = []
    for i in range(1, len(rows)):
        prev, cur = rows[i - 1], rows[i]
        p_state, c_state = prev.get("state"), cur.get("state")
        if not p_state or not c_state or p_state == c_state:
            continue
        cur_date = str(cur.get("asof"))[:10]
        source_ref = f"risk_radar_forward_log#{cur_date}"
        title = f"Risk radar: {p_state} → {c_state}"
        fact_bits = [f"{p_state} → {c_state}"]
        dominant = cur.get("dominant_scare")
        if dominant:
            fact_bits.append(f"dominant scare: {dominant}")
        top_score = cur.get("top_score")
        if isinstance(top_score, (int, float)):
            fact_bits.append(f"top score {top_score:.1f}")
        try:
            ev = schema.new_event(
                id=schema.make_id("risk_band", source_ref, cur_date),
                ts=f"{cur_date}T00:00:00Z",
                date=cur_date,
                source="risk_band",
                source_ref=source_ref,
                kind="state_flip",
                title=title,
                facts=fact_bits,
                tickers=[],
                themes=["risk"],
                weight_hint=2,
                links=schema.make_links(),
            )
        except Exception as exc:  # noqa: BLE001
            log.debug("chronicle.risk_band: skipped flip event: %s", exc)
            skipped += 1
            continue
        events.append(ev)

    if not rows:
        gap = f"{rel} has no rows yet"
    elif len(rows) == 1:
        gap = f"{rel} has one row — flips accrue from the next capture"
    elif skipped:
        gap = f"{skipped} malformed forward-log row(s) skipped"
    else:
        gap = None
    return events, gap
