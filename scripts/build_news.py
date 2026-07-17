"""Build the Research → News JSON side-artifacts under site/news/.

Aggregates every news feed in the suite (LLM-enriching the headlines in place):
  • Macro news, sentiment & catalysts        (engine.macro_news + event_calendar)
  • Financial / sector / Mag-7 / basket news  (engine.financial_news)
  • China macro / markets / tech / politics    (engine.china_news)
  • Narrative event bus (PIT)                  (engine.news_vector)

An OPTIONAL Claude-Haiku / DeepSeek pass (engine.news_llm) adds one-line summaries
and an "importance" re-rank on top of the deterministic quality score — it never
adds or removes a headline, and feeds NO score.

The PAGE itself — site/news.html — is rendered by scripts/build_site.py from the
shared macro view-model (it carries `latest`/`ndi`/`event_strip`/`prediction_markets`/
`narrative_regime`, which this standalone script does not). build_news runs AFTER
build_site and owns ONLY the JSON side-artifacts below; it deliberately does NOT
render news.html (doing so would crash on the missing `latest` and, if "fixed",
would clobber build_site's richer page with a lean one).

Side-artifacts written under site/news/:
  • financial.json   — the full sectioned financial feed
  • by_ticker.json   — compact per-ticker news flow (stock pages + Mastermind lens)
  • macro.json, china.json, narrative.json — per-feed snapshots

Run:   python -m scripts.build_news
Fast:  feeds are disk-cached (12 h TTL); re-runs are ~instant.
Standalone & degrade-safe — any feed that fails is simply omitted; the artifacts
that do have data are still written (each write is independently guarded).
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config  # noqa: E402
from engine import news_common as nc  # noqa: E402

# --------------------------------------------------------------------------- #
# NEVER-DARKEN GUARD — prevents a keyless re-render from overwriting a healthy
# keyed-build artifact with a darker (fewer-providers / fewer-tickers) feed.
#
# "Darker" is defined as:
#   (a) existing artifact is strictly healthier in provider coverage (more providers
#       true in the boolean dict), OR
#   (b) existing artifact covers materially more tickers (>3× as many tickers_covered).
# "Fresh enough" = existing artifact's fetched_at is within 36 h of now.
# When the guard fires the existing JSON is stamped with refresh_skipped_reason
# and returned as-is, so the caller sees the kept feed but the state is honest.
# --------------------------------------------------------------------------- #
_NEVER_DARKEN_STALE_H = 36.0   # existing artifact older than this may be replaced
_TICKER_DARKEN_RATIO = 3.0     # new / old < 1/ratio => "materially fewer"


def _should_keep_existing(existing: dict, candidate: dict) -> bool:
    """Return True when the existing artifact is fresher than 36 h AND strictly
    healthier than the candidate feed (more provider coverage or materially more
    tickers covered). PURE — no I/O."""
    try:
        import dateutil.parser  # stdlib-free: always present via pandas transitive dep
        fetched_str = existing.get("fetched_at") or ""
        if not fetched_str:
            return False
        fetched = dateutil.parser.parse(fetched_str)
        age_h = (datetime.now(timezone.utc) - fetched).total_seconds() / 3600.0
        if age_h > _NEVER_DARKEN_STALE_H:
            return False            # existing is stale — allow replacement
    except Exception:  # noqa: BLE001
        return False

    ex_providers = existing.get("providers") or {}
    ca_providers = candidate.get("providers") or {}
    ex_ok = sum(1 for v in ex_providers.values() if v)
    ca_ok = sum(1 for v in ca_providers.values() if v)

    ex_tickers = (existing.get("counts") or {}).get("tickers_covered", 0) or 0
    ca_tickers = (candidate.get("counts") or {}).get("tickers_covered", 0) or 0

    # Condition (a): fewer providers live in the candidate
    if ca_ok < ex_ok:
        return True
    # Condition (b): candidate covers materially fewer tickers (>3× gap)
    if ex_tickers > 0 and ca_tickers < ex_tickers / _TICKER_DARKEN_RATIO:
        return True
    return False

log = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# LLM enrichment + final re-rank (shared across every section)
# --------------------------------------------------------------------------- #
def _blend_key(h: dict) -> float:
    """Final display order: quality is primary, LLM importance a 40% tiebreaker."""
    q = float(h.get("quality", 0))
    imp = h.get("llm_importance")
    return 0.6 * q + 0.4 * (float(imp) if imp is not None else q)


def _enrich(sections: list[list[dict]]) -> str:
    """Annotate (dedup'd) and re-rank a list of headline lists in place. Returns the
    active LLM provider label (or '')."""
    from engine import news_llm
    # one representative per (title,domain) so the cap isn't wasted on cross-section dupes
    reps: dict[str, dict] = {}
    order: list[dict] = []
    groups: dict[str, list[dict]] = {}
    for sec in sections:
        for h in sec:
            i = nc.event_id(h.get("title", ""), h.get("domain", ""))
            groups.setdefault(i, []).append(h)
            if i not in reps:
                reps[i] = h
                order.append(h)
    try:
        news_llm.annotate(order)
    except Exception as e:  # noqa: BLE001
        log.warning("news_llm enrich failed (%s)", e)
    # propagate the representative's enrichment to its duplicates
    for i, grp in groups.items():
        rep = reps[i]
        for h in grp:
            if h is rep:
                continue
            if rep.get("summary") and not (h.get("summary") or "").strip():
                h["summary"] = rep["summary"]
            if "llm_importance" not in h and rep.get("llm_importance") is not None:
                h["llm_importance"] = rep["llm_importance"]
                h["llm_tone"] = rep.get("llm_tone")
    for sec in sections:
        sec.sort(key=_blend_key, reverse=True)
    try:
        return news_llm.provider_label()
    except Exception:  # noqa: BLE001
        return ""


# --------------------------------------------------------------------------- #
def build(write: bool = True) -> dict:
    cfg = config.load()
    now = datetime.now(timezone.utc)
    vm: dict = {"built": now.isoformat(), "built_date": now.date().isoformat(),
                "llm_provider": ""}

    # ---- macro news + catalysts ---------------------------------------------
    macro = None
    macro_catalysts: list = []
    macro_disc = macro_disc_zh = ""
    try:
        from engine import macro_news as mn
        macro = mn.macro_headlines()
        macro_catalysts = mn.upcoming_catalysts(horizon_days=14)
        macro_disc, macro_disc_zh = mn.DISCLAIMER_TEXT, mn.DISCLAIMER_TEXT_ZH
        vm["macro_theme_label"] = mn.THEME_LABEL
    except Exception as e:  # noqa: BLE001
        log.error("macro_news failed: %s", e)
    vm.update(macro=macro, macro_catalysts=macro_catalysts,
              macro_disclaimer=macro_disc, macro_disclaimer_zh=macro_disc_zh)
    vm.setdefault("macro_theme_label", {})

    # ---- financial / sector / Mag-7 / basket --------------------------------
    fin = None
    rss_rejected: list[dict] = []
    try:
        from engine import financial_news as fnews
        from engine import news_rss as _nrss
        _rss_col, _rss_tok = _nrss.start_reject_log()
        try:
            fin = fnews.feed()
        finally:
            _nrss.stop_reject_log(_rss_tok)
            rss_rejected = list(_rss_col)
    except Exception as e:  # noqa: BLE001
        log.error("financial_news failed: %s", e)
    vm["fin"] = fin

    # ---- china (macro / markets / tech / politics) --------------------------
    china = None
    try:
        from engine import china_news as cnews
        china = cnews.panel()
    except Exception as e:  # noqa: BLE001
        log.error("china_news failed: %s", e)
    vm["china"] = china

    # ---- narrative event bus (PIT) ------------------------------------------
    narrative = None
    try:
        from engine import news_vector as nv
        if nv.enabled():
            ingest_result = nv.ingest()
            # freshness is always checked inside ingest(); surface stale-store
            # warning so it appears in CI/build logs (broken ≠ quiet).
            if ingest_result:
                fr = ingest_result.get("freshness") or {}
                if fr.get("warn"):
                    log.warning(
                        "news_vector store STALE: newest=%s age=%s days — "
                        "check GDELT rate-limit or fetch_cache for cached failures",
                        fr.get("newest_event"), fr.get("age_days"),
                    )
            # wire accrued events into qbus after each successful ingest
            nv.ingest_to_qbus()
        narrative = nv.recent_panel()
    except Exception as e:  # noqa: BLE001
        log.error("news_vector failed: %s", e)
    vm["narrative"] = narrative

    # ---- optional LLM enrichment (priority order) + macro brief -------------
    sections: list[list[dict]] = []
    if macro and macro.get("headlines"):
        sections.append(macro["headlines"])
    if fin:
        sections.append(fin.get("market", []))
        for t in nc.MAG7:
            sections.append(fin.get("mag7", {}).get(t, {}).get("headlines", []))
        for etf in nc.SECTOR_ETFS:
            sections.append(fin.get("sectors", {}).get(etf, {}).get("headlines", []))
        for bk in (fin.get("baskets", {}) or {}).values():
            sections.append(bk.get("headlines", []))
    if china and china.get("news", {}).get("headlines"):
        sections.append(china["news"]["headlines"])
    vm["llm_provider"] = _enrich([s for s in sections if s])

    vm["sector_etfs"] = nc.SECTOR_ETFS
    vm["mag7_order"] = nc.MAG7

    if not write:
        return vm

    # ---- side-artifacts -----------------------------------------------------
    # site/news.html is rendered by scripts/build_site.py (the full, rich page from
    # the shared macro view-model). build_news runs AFTER build_site and writes ONLY
    # the JSON side-artifacts below — it must NOT render news.html. Each write is
    # independently guarded so one bad feed can never block the rest.
    site = config.ROOT / cfg["storage"]["site_dir"]
    outdir = site / "news"
    outdir.mkdir(parents=True, exist_ok=True)

    def _write(name: str, payload) -> None:
        try:
            (outdir / name).write_text(json.dumps(payload, default=str))
        except Exception as e:  # noqa: BLE001 — one artifact must never block the others
            log.warning("news artifact %s failed (%s)", name, e)

    if fin:
        # NEVER-DARKEN GUARD: read the on-disk artifact before overwriting. A keyless
        # re-render (engine-render.yml) must not replace a healthy keyed-build output
        # with a darker feed. If the existing artifact is fresh (<36 h) AND strictly
        # healthier (more providers live OR materially more tickers covered), keep it
        # and stamp refresh_skipped_reason so the JSON state remains honest.
        _fin_out_path = outdir / "financial.json"
        _fin_to_write = fin
        try:
            if _fin_out_path.exists():
                _existing = json.loads(_fin_out_path.read_text())
                if _should_keep_existing(_existing, fin):
                    _skip_reason = (
                        f"existing feed healthier (providers={_existing.get('providers')} "
                        f"tickers_covered={(_existing.get('counts') or {}).get('tickers_covered')})"
                        f" vs candidate (providers={fin.get('providers')} "
                        f"tickers_covered={( fin.get('counts') or {}).get('tickers_covered')})"
                    )
                    log.warning("never-darken guard: keeping existing financial.json — %s",
                                _skip_reason)
                    _existing["refresh_skipped_reason"] = _skip_reason
                    _fin_to_write = _existing
        except Exception as _guard_exc:  # noqa: BLE001 — guard must never block the build
            log.warning("never-darken guard read failed (%s) — writing candidate", _guard_exc)
        _write("financial.json", _fin_to_write)
        try:
            from engine import financial_news as fnews
            bt = fnews.mastermind_by_ticker(_fin_to_write)
            _write("by_ticker.json", {"schema": "news_flow.v1", "is_context_only": True,
                                      "asof": vm["built_date"], "tickers": bt})
            log.info("news by_ticker: %d tickers", len(bt))
        except Exception as e:  # noqa: BLE001
            log.warning("by_ticker artifact failed (%s)", e)
    if macro:
        _write("macro.json", macro)
    if china:
        _write("china.json", china)
    if narrative:
        _write("narrative.json", narrative)

    # ---- macro surprise cards -----------------------------------------------
    # Pass the prior artifact path so build_release_cards can apply the last-good
    # fallback: if a fresh FRED fetch returns an older observation than what was in
    # the previous run's artifact, the prior card is kept (marked last_good_fallback)
    # rather than silently dropping it from the board.
    macro_releases = None
    _prior_releases_path = outdir / "macro_releases.json"
    try:
        from engine import macro_surprise as ms
        macro_releases = ms.build_release_cards(
            prior_artifact_path=_prior_releases_path if _prior_releases_path.exists() else None,
        )
        if macro_releases:
            n_cards = macro_releases.get("n_cards", 0)
            n_fetched = macro_releases.get("n_fetched", 0)
            log.info("macro_releases: %d cards from %d/%d series",
                     n_cards, n_fetched, macro_releases.get("n_registry", 0))
    except Exception as e:  # noqa: BLE001 — degrade to empty, never block
        log.warning("macro_surprise failed (%s)", e)
        macro_releases = {"schema": "macro_releases.v1", "is_context_only": True,
                          "cards": [], "n_cards": 0, "degraded_reason": str(e)}

    _write("macro_releases.json", macro_releases or {
        "schema": "macro_releases.v1", "is_context_only": True, "cards": []
    })
    vm["macro_releases"] = macro_releases

    # ---- reject log (aggregate all feed buckets) ----------------------------
    try:
        macro_rejected = (macro or {}).get("rejected") or []
        fin_rejected = (fin or {}).get("rejected") or []
        n_total = len(macro_rejected) + len(fin_rejected) + len(rss_rejected)
        _write("rejected.json", {
            "schema": "news_reject_log.v1",
            "is_context_only": True,
            "built": vm["built"],
            "n_total": n_total,
            "feeds": {
                "macro": macro_rejected,
                "financial": fin_rejected,
                "rss": rss_rejected,
            },
        })
        log.info("news reject log: %d total (%d macro / %d fin / %d rss)",
                 n_total, len(macro_rejected), len(fin_rejected), len(rss_rejected))
    except Exception as e:  # noqa: BLE001
        log.warning("rejected.json artifact failed (%s)", e)

    # ---- W4: persist kept events + reject sample (fire-and-forget) ----------
    # Collect kept events from macro and financial feeds. Each kept headline dict
    # may carry an 'event' field (from news_events.classify_event enrichment).
    try:
        from engine import news_event_ledger as _nel  # noqa: PLC0415
        kept_all: list[dict] = []
        if macro and macro.get("headlines"):
            kept_all.extend(macro["headlines"])
        if fin:
            # W4-FIN-MARKET CHECK: financial.json['market'] should always be a list of
            # dicts, but guard defensively in case a stale / malformed artifact was kept
            # by the never-darken guard or a disk corruption.
            _fin_market = fin.get("market", [])
            if not isinstance(_fin_market, list):
                log.warning("fin['market'] unexpected shape %s — skipping extend",
                            type(_fin_market).__name__)
                _fin_market = []
            for _mh in _fin_market:
                if isinstance(_mh, dict):
                    kept_all.append(_mh)
                else:
                    log.warning("fin['market'] item is not a dict: %r (skipping)", _mh)
            for t in nc.MAG7:
                kept_all.extend(fin.get("mag7", {}).get(t, {}).get("headlines", []))
            for etf in nc.SECTOR_ETFS:
                kept_all.extend(fin.get("sectors", {}).get(etf, {}).get("headlines", []))
            for bk in (fin.get("baskets") or {}).values():
                kept_all.extend(bk.get("headlines", []))
        n_evt = _nel.persist_kept_events(kept_all, asof_utc=now.isoformat())
        if n_evt:
            log.info("news_event_ledger: %d new event rows persisted", n_evt)
    except Exception as _nel_exc:  # noqa: BLE001 — never breaks the build
        log.warning("news_event_ledger persist_kept_events failed (non-fatal): %s", _nel_exc)

    try:
        from engine import news_event_ledger as _nel  # noqa: PLC0415, F811
        macro_rejected = (macro or {}).get("rejected") or []
        fin_rejected = (fin or {}).get("rejected") or []
        rejected_by_feed: dict[str, list] = {}
        if macro_rejected:
            rejected_by_feed["macro"] = macro_rejected
        if fin_rejected:
            rejected_by_feed["financial"] = fin_rejected
        if rss_rejected:
            rejected_by_feed["rss"] = rss_rejected
        n_rej = _nel.persist_reject_sample(rejected_by_feed, asof_utc=now.isoformat())
        if n_rej:
            log.info("news_event_ledger: %d new reject-sample rows persisted", n_rej)
    except Exception as _rej_exc:  # noqa: BLE001 — never breaks the build
        log.warning("news_event_ledger persist_reject_sample failed (non-fatal): %s", _rej_exc)

    log.info("built site/news/*.json (llm=%s)", vm["llm_provider"] or "off")
    return vm


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    try:
        build()
        return 0
    except Exception as e:  # noqa: BLE001
        log.error("build_news failed: %s", e)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
