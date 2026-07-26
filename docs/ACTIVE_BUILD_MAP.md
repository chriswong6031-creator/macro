<!-- GENERATED — do not edit by hand; regenerate with `python scripts/build_active_build_map.py`. Advisory only: this map informs sessions; it gates nothing. -->

# Active Build Map

Generated: 2026-07-26T14:29:31.438534+00:00  |  Open PRs: 20  |  Merged (window): 500  |  base: `9cac7bc0f139e7919fd87ddafe67e1b3e7ee2336`

## Open PRs

| PR | Title | Branch | Updated | Flags |
|----|-------|--------|---------|-------|
| #3677 | fix(hooks): base-side-red awareness for the ship-loop CI gate — stop pinning merged heads forever | `claude/wizardly-leavitt-005749` | 2026-07-26 | — |
| #3676 | perf(landing,chat): lift the inline page CSS into paired stylesheets — cacheable, cascade-identical (#3650 follow-up) | `claude/amazing-chatterjee-907c08` | 2026-07-26 | ⚠ CONFLICTING |
| #3675 | fix(free-estate): 52 stale pages + 15 CTA-less calculators; wire the drift law into CI | `claude/quirky-mirzakhani-a31ef1` | 2026-07-26 | ⚠ protected:2 |
| #3674 | fix(china-breadth): fail a truncated Sina walk instead of publishing a short count | `claude/china-board-breadth-truncation-guard` | 2026-07-26 | — |
| #3673 | fix(landing): self-host Archivo — the display face never arrived in China | `claude/serene-almeida-29ea46` | 2026-07-26 | ⚠ CONFLICTING |
| #3671 | feat(brain): light-mode theme for the Mastermind chat + a launcher that survives white | `claude/mastermind-light-mode-theme-3878ac` | 2026-07-26 | — |
| #3670 | PSS-F4: downside-vol asymmetry flip (semivariance regime turn) — prereg + analysis | `research/pss-f4-semivar` | 2026-07-26 | ⚠ protected:1 |
| #3668 | test(ci): close P1 — 136 unrun-but-triggerable publish-path suites (12 lanes) + 4 red-on-main repairs | `claude/exciting-bhaskara-83fbf8` | 2026-07-26 | ⚠ CONFLICTING / ⚠ protected:1 |
| #3667 | docs(census): record the FTR product call — resolved as marker rot, both suites wired | `claude/ftr-census-record-97d486` | 2026-07-26 | — |
| #3652 | fix(shim): the guard's other blind spot — variable *.html targets in 9 builders | `claude/admiring-hellman-07c1cb` | 2026-07-26 | ⚠ protected:2 |
| #3651 | fix(chronicle): arm gate 1's byte tooth at the manifest's recorded source vintage (teeth 4+5 + import-closure hardening) | `claude/eloquent-williamson-68a777` | 2026-07-26 | ⚠ CONFLICTING |
| #3650 | fix(css): externalize_css must skip the plain-copy pairs — reclaim 92KB of unprunable dead CSS | `claude/vigilant-hodgkin-b2d1cb` | 2026-07-26 | ⚠ protected:1 |
| #3640 | feat(support): ship the public /support.html desk + the pinned email base and ticket ack (SEE W2) | `claude/w2-support-page` | 2026-07-26 | ⚠ protected:1 |
| #3637 | feat(research-vault): measure PDF metadata instead of trusting the sidecar (Tier A) | `claude/rv-tier-a-metadata` | 2026-07-26 | ⚠ protected:1 |
| #3633 | feat(billing-email): W3 — webhook receipts, trial-ending sweeper, account prefs, portal deep link | `claude/w3-billing-emails` | 2026-07-26 | ⚠ protected:2 |
| #3622 | feat(case): winner autopsy JD 2023 | `codex/case-jd-2023` | 2026-07-26 | — |
| #3620 | feat(case): winner autopsy SEDG 2016 | `codex/case-sedg-2016` | 2026-07-26 | — |
| #3618 | feat(case): winner autopsy GTLB 2022 | `codex/case-gtlb-2022` | 2026-07-26 | — |
| #3614 | feat(case): winner autopsy TMDX 2022 | `codex/case-tmdx-2022` | 2026-07-26 | — |
| #3608 | fix(marketing): rewrite today's stale queued copy; collapse go-live checklist | `claude/outbox-requeue-and-checklist` | 2026-07-26 | ⚠ CONFLICTING / ⚠ protected:1 |

> ⚠ CONFLICTING means mergeStateStatus=DIRTY — pull_request CI is suppressed on conflicting PRs (known repo failure mode).

## File Collisions

| PR A | PR B | Shared files | Files |
|------|------|-------------|-------|
| #3676 | #3640 | 4 | `app/deploy/Caddyfile`, `config/site_access.yml`, `site/index.html`, `templates/index.html` |
| #3675 | #3652 | 3 ⚠ | `.github/workflows/ci-main-heartbeat.yml`, `.github/workflows/ci.yml`, `scripts/build_free_content.py` |
| #3676 | #3673 | 2 | `site/index.html`, `templates/index.html` |
| #3673 | #3640 | 2 | `site/index.html`, `templates/index.html` |
| #3640 | #3633 | 2 ⚠ | `.github/workflows/ci.yml`, `templates/plans.html.j2` |
| #3675 | #3668 | 1 ⚠ | `.github/workflows/ci.yml` |
| #3675 | #3650 | 1 ⚠ | `.github/workflows/ci.yml` |
| #3675 | #3640 | 1 ⚠ | `.github/workflows/ci.yml` |
| #3675 | #3637 | 1 ⚠ | `.github/workflows/ci.yml` |
| #3675 | #3633 | 1 ⚠ | `.github/workflows/ci.yml` |
| #3668 | #3667 | 1 | `docs/UNRUN_TEST_CENSUS.md` |
| #3668 | #3652 | 1 ⚠ | `.github/workflows/ci.yml` |
| #3668 | #3650 | 1 ⚠ | `.github/workflows/ci.yml` |
| #3668 | #3640 | 1 ⚠ | `.github/workflows/ci.yml` |
| #3668 | #3637 | 1 ⚠ | `.github/workflows/ci.yml` |
| #3668 | #3633 | 1 ⚠ | `.github/workflows/ci.yml` |
| #3652 | #3650 | 1 ⚠ | `.github/workflows/ci.yml` |
| #3652 | #3640 | 1 ⚠ | `.github/workflows/ci.yml` |
| #3652 | #3637 | 1 ⚠ | `.github/workflows/ci.yml` |
| #3652 | #3633 | 1 ⚠ | `.github/workflows/ci.yml` |
| #3650 | #3640 | 1 ⚠ | `.github/workflows/ci.yml` |
| #3650 | #3637 | 1 ⚠ | `.github/workflows/ci.yml` |
| #3650 | #3633 | 1 ⚠ | `.github/workflows/ci.yml` |
| #3640 | #3637 | 1 ⚠ | `.github/workflows/ci.yml` |
| #3637 | #3633 | 1 ⚠ | `.github/workflows/ci.yml` |

## Recently Merged (last 14 days) (showing most recent 500; window truncated)

| PR | Title | Merged |
|----|-------|--------|
| #3672 | feat(brain): read_china_flows — the brain can finally cite the Tushare plane | 2026-07-26 |
| #3669 | harden(chronicle): take the renderer out of the adapter's import closure | 2026-07-26 |
| #3666 | feat(china): quote the whole-board 涨跌家数, not the map's 1,510-name sample | 2026-07-26 |
| #3664 | fix(track-record): score real trades, not board membership marked to today (US + CN) | 2026-07-26 |
| #3663 | docs(census): heal the unrun-test census against merged main | 2026-07-26 |
| #3662 | fix(research-vault): show transfer progress — the download was working, silently | 2026-07-26 |
| #3661 | docs(theta-r2sync): record the 2026-07-25 M2→M1 host migration in the runbook | 2026-07-26 |
| #3660 | fix(chronicle): survive the hourly vault-catalog lane — regen store, pin catalog vintage, declare jinja2 | 2026-07-26 |
| #3659 | fix(daily): pin collect_tail to theta-m1 so tape_flow lands on the Terminal host nightly | 2026-07-26 |
| #3658 | feat(brain-chat): Enter writes a new line; Stop hands the message back | 2026-07-26 |
| #3657 | fix(chronicle): rebuild the committed store so main's staleness gate goes green | 2026-07-26 |
| #3656 | fix(brain): Terminal chat degraded on every chart turn — synthesis had no way to answer | 2026-07-26 |
| #3655 | design(landing): serif display figures — Newsreader replaces Archivo Expanded Black on every big number | 2026-07-26 |
| #3654 | feat(research-vault): raise the daily download cap to 50/day for lifetime Pro | 2026-07-26 |
| #3649 | research(personality): PSS-F3 idiosyncratic residual reset — prereg + results (falsifier = residual-vs-raw + low-R² mechanism) | 2026-07-26 |
| #3648 | fix(chronicle): gate 1 asserted cross-lane synchrony the pipeline never provides (M11) + unblank vault site links | 2026-07-26 |
| #3646 | fix(signal-lab): publish the DSR the calibrator computed, not a hardcoded quote | 2026-07-26 |
| #3645 | test(ftr): re-pin the 3 red tape-surface guards to the shipped surface + wire both suites into CI | 2026-07-26 |
| #3644 | fix(daily): Terminal probe-only — never auto-launch from CI post M2→M1 migration | 2026-07-26 |
| #3642 | fix(brain): make the language override symmetric (follow-up to #3639) | 2026-07-26 |
| #3639 | fix(brain): pin every turn's language to the user's profile, chips included | 2026-07-26 |
| #3636 | test(ci): close the strictly-dark unrun-suite subset (130 suites, 9 lanes) + repair 5 rotted guards | 2026-07-26 |
| #3635 | fix(leader-radar,pages): the shim guard's blind spot, its cache trap, and its missing CI lane | 2026-07-26 |
| #3632 | fix(assets): unfreeze ?v= stamps for real — stage the pair, re-stamp post-rebase | 2026-07-26 |
| #3630 | fix(china): W1 review pass — atomic PIT writes, partial-day honesty, coverage-null ledger | 2026-07-26 |
| #3629 | fix(hooks): ship-loop guard render gate accepts descendant coverage (coalescing-lane law) | 2026-07-26 |
| #3628 | research(personality): PSS-F2 overnight-vs-intraday decomposition flip — prereg + results (falsifier = decomposition-vs-aggregate) | 2026-07-26 |
| #3627 | fix(api): coarsen /api/status error strings to stop path disclosure to anon callers | 2026-07-26 |
| #3626 | fix(admin-deploy): provision boto3 for the deployed panel's R2 refresh | 2026-07-26 |
| #3625 | fix(shim): index.html could never heal — sweep the templates/ side of paired pages | 2026-07-26 |
| #3624 | fix(landing): bump the onboard ?v= stamps so #3617's CSS actually reaches browsers | 2026-07-26 |
| #3623 | design(factors + macro_context): honest-verdict hero, plain words, and a site-wide chrome cleanup | 2026-07-26 |
| #3621 | feat(china): W1 — 互动易/e互动 investor Q&A, sell-side revision stream, 股东户数 collectors | 2026-07-26 |
| #3619 | feat(china-native): W2 — funding curve, CB plane, fund issuance, full-universe ETF shares | 2026-07-26 |
| #3617 | fix(onboarding): load real expanded Archivo (wdth 125) — the sheet's display face never rendered | 2026-07-26 |
| #3616 | test(china-alpha): repair the w2a/w2b suites and wire them into CI | 2026-07-26 |
| #3615 | fix(api,billing,tape): rate-limit /api/collect, cap /ws/tape per IP, stop raw exception leakage | 2026-07-26 |
| #3613 | ci(render): fire the render lane when the post-render sweeps change | 2026-07-26 |
| #3612 | feat(leader-radar): admit build_leader_radar to both express render lanes (scope=all, serial post-band) | 2026-07-26 |
| #3611 | fix(commodities): don't claim a downtrend the timeframe table refutes; repair dead per-timeframe wire | 2026-07-26 |
| #3610 | design(vector): rebuild the Deep Dive shelf on the macro.html fold idiom | 2026-07-26 |
| #3609 | fix(brain): review fix-forward on #3586 — timeout ceiling, param-rejection failover, timeline polish | 2026-07-26 |
| #3607 | fix(ccw): unfreeze credit momentum — duplicate ISINs crashed the nightly organ | 2026-07-26 |
| #3606 | fix(nav): expose nav_market.js publicly — it 401'd behind the regwall | 2026-07-26 |
| #3605 | fix(research_vault): detect the all-lowercase filename stem + guard the committed catalog | 2026-07-26 |
| #3604 | feat(admin): ingest-dark warning on the AI Response Logs tab | 2026-07-26 |
| #3603 | feat(labs): W-LAB dual-ruler combo columns + codex-class Pick Lab cuts (V-LAB-1/4/5/6) | 2026-07-26 |
| #3602 | design(support-email): pin the support page + email visual system (W-D) | 2026-07-26 |
| #3601 | fix(billing): unbreak the portal for subscribers, land checkout on the desk, script the portal config | 2026-07-26 |
| #3600 | fix(marketing): serve the launch card from a public path | 2026-07-26 |
| #3599 | fix(odds): restore data/odds_ohlcv from R2 in the engine preamble | 2026-07-26 |
| #3598 | feat(support-email): W1 spine — schema, mailer ledger, public ticket intake, admin Support console | 2026-07-26 |
| #3597 | fix(china-validation): count evidence, not rows — the fundflow/chips grid went daily | 2026-07-26 |
| #3596 | fix(tushare-history): kill the structural 4-day staleness — contiguous daily grid anchored on the newest close | 2026-07-26 |
| #3595 | test(desk-writers): run the six scored-ledger suites that no CI job named | 2026-07-26 |
| #3593 | fix(landing): load real expanded Archivo (wdth 125) — the display face never rendered | 2026-07-26 |
| #3592 | feat(legal): Privacy Policy, Terms & Disclaimer pages + public-boundary wiring | 2026-07-26 |
| #3591 | perf(research-vault): parallelize ingest receipt scan (unblocks 20k backfill) | 2026-07-26 |
| #3590 | feat(options): the Options workspace — one canonical surface, 4 modes (OEU M-CMD) | 2026-07-26 |
| #3589 | test(research-vault): guard report titles over the REAL catalog, not a fixture | 2026-07-26 |
| #3588 | feat(chronicle): W0 — deterministic market-context timeline spine | 2026-07-26 |
| #3587 | fix(ci): un-deaden 69 GitHub annotations that logging silently swallowed | 2026-07-26 |
| #3586 | feat(brain): live reasoning timeline + Fast/Pro latency overhaul | 2026-07-26 |
| #3585 | fix(marketing): stop the weekend lane shipping one repeated headline | 2026-07-26 |
| #3584 | research(china): native data + Mastermind context masterplan — W0 catalogs + probe harness | 2026-07-26 |
| #3583 | feat(personality): PSS-W3 Prophet tailored-gate shadow lane | 2026-07-26 |
| #3582 | feat(nav): fold the non-home country menus into International | 2026-07-26 |
| #3581 | research(personality): PSS-F1 down-volume envelope decay — prereg + results (falsifier not cleared) | 2026-07-26 |
| #3580 | feat(spine): give stock_desk the scored ledger the spine already registered | 2026-07-26 |
| #3579 | fix(pooling): pre-register an arming margin floor — a 1e-5 lift must not arm the live desk weights | 2026-07-26 |
| #3578 | fix(leader-radar): express-lane safety — provenance gate, PIT view caps, rs freshness, loud fail-softs, byte-stable rebakes | 2026-07-26 |
| #3577 | research(personality): W-LAB §5 audit verdicts (audit-before-change gate satisfied) | 2026-07-26 |
| #3576 | feat(txi): W5 — Loop-C closure (autonomous chain proposals via the CHF lane, gated) | 2026-07-26 |
| #3575 | docs(support-email): charter the Support & Email Estate masterplan | 2026-07-26 |
| #3574 | feat(brain): chat turns survive the browser; sticky Pro lane; Deep Research pill | 2026-07-26 |
| #3573 | fix(assets,onboarding): unfreeze ?v= stamps, load the sheet at any page depth, detect dark-by-default pages | 2026-07-26 |
| #3572 | fix(odds): loud fail-soft + coverage census for the nightly odds desk | 2026-07-26 |
| #3571 | fix(ci): drop the deleted test path that was disabling 2084 heartbeat tests | 2026-07-26 |
| #3570 | fix(research_vault): recover real report titles instead of shipping PDF filenames | 2026-07-26 |
| #3568 | fix(calibration): sweep thematic_desk's null — theme_rel_return was unmeasured | 2026-07-26 |
| #3567 | fix(calibration): thematic_desk's null uses the window it was GRADED on, + its missing outcome spine | 2026-07-26 |
| #3566 | test(site-access): catch the exemption+gitignore pair, not just the gitignore | 2026-07-26 |
| #3564 | test(tier-gate): pin the job to its own ci.yml trigger paths | 2026-07-26 |
| #3563 | fix(render-lanes): light up the daily-only class — tech_lab/impulse/foresight express coverage, odds/leader_radar documented out, real ::warning annotations | 2026-07-26 |
| #3562 | research_vault: repair truncated report titles before they reach public <title> | 2026-07-26 |
| #3561 | fix(flow-velocity): unpin the flow readout — demean the measure, size windows to the daily grid | 2026-07-26 |
| #3560 | feat(onboarding): in-sheet feature compare, a real upgrade lane, and desk prefs you can change | 2026-07-26 |
| #3559 | fix(ship-loop): a merged branch deleted on merge is not "unpushed" | 2026-07-26 |
| #3558 | perf(mobile): remove two blocking round-trips from every page; desktop globe back to ≥60fps | 2026-07-26 |
| #3557 | fix(txi): W3 calibration counts episodes not bars (rising-edge activations) | 2026-07-26 |
| #3556 | marketing: @mastermindx001 intro card + reproducible renderer | 2026-07-26 |
| #3555 | fix(marketing): arm the LLM voice lane for real + unstick marketing CI | 2026-07-26 |
| #3554 | test(tier-gate): key the paid-row leak check on the row, not the ticker | 2026-07-26 |
| #3553 | test: isolate marketing suites from live operator account overrides | 2026-07-26 |
| #3552 | fix(ci): unrot chart_render suites — MACD colour probe + wire them into CI | 2026-07-26 |
| #3551 | fix(marketing): stop bot-voice, image-less flagship posts (incident) | 2026-07-26 |
| #3550 | design(vector): stronger stance dial + declutter Today's Read | 2026-07-25 |
| #3549 | fix(ops): stop render retry storms | 2026-07-25 |
| #3548 | revert(hooks): restore #3519's guard — #3545 clobbered it from a stale worktree | 2026-07-26 |
| #3547 | Fix Prophet stage labels under text scaling | 2026-07-25 |
| #3546 | fix(render): normalize site/ before the always() commit — cancelled renders shipped raw pages | 2026-07-25 |
| #3545 | fix(hooks): ship-loop guard was rate-limited into reporting "github_unreachable" | 2026-07-25 |
| #3544 | fix(seo): close sitemap-to-static-page publication gap | 2026-07-25 |
| #3543 | feat(canada): illustrate the Market Participation dialog (breadth field + contribution bars) | 2026-07-25 |
| #3542 | fix(special-situations): refuse a no-refresh rebake that would thin the desk | 2026-07-25 |
| #3541 | feat(intl): World Risk Appetite v2 — cap-weighted 10-market dial (US/CN/HK included), state-aware | 2026-07-25 |
| #3540 | fix(ci): collapse hosted runner fanout | 2026-07-25 |
| #3539 | feat(admin-analytics): attach registered users (email) to Sessions + Visitors + soft device/IP linkage | 2026-07-25 |
| #3538 | feat(wri): W6.1 — crypto in the book model + coverage honesty + HK/CN/CA factor-model charter | 2026-07-25 |
| #3537 | fix(canada): match US 3:7 hero split so the score-path chart fills the panel | 2026-07-25 |
| #3536 | feat(txi): W3 — historical episode miner + regime-conditional hop calibration | 2026-07-25 |
| #3535 | fix(risk-radar): flatten the odds box — one amber card, not a box-in-a-box | 2026-07-25 |
| #3534 | fix(ci): retry lost ref races long enough to actually land the push | 2026-07-25 |
| #3533 | test(support-map): heal stale regime-latest census band (59→98, legitimate growth) | 2026-07-25 |
| #3532 | test(site-access): tripwire the ignored-estate freeze #3507 caused and #3522 could not catch | 2026-07-25 |
| #3530 | fix(leader-radar): rebuild broken breadth gauge — value marker, mono numerals, zh-flip | 2026-07-25 |
| #3529 | docs(personalization): market-preference masterplan + wire macro instruments into the nightly | 2026-07-25 |
| #3528 | fix(nav): expose shared icon stylesheet publicly | 2026-07-25 |
| #3527 | feat(txi): W4 — distribution (site publish + NW/world_state + portfolio_ctx + Cascade Monitor + watchlist chain lane) | 2026-07-25 |
| #3526 | fix(brain): SSE keepalive — stop slow answers being culled to "reply didn't make it through" | 2026-07-25 |
| #3525 | fix(nav): preserve custom icons across renders | 2026-07-25 |
| #3523 | fix(calibration): govern thematic_desk / narrative_brain / master_brain + report the Holm family actually applied | 2026-07-25 |
| #3522 | fix(site-access): un-exempt /research/ — it is committed content, not a runtime plane | 2026-07-25 |
| #3521 | fix(ops): options-matrix gate T+1 semantics — lane never published autonomously | 2026-07-25 |
| #3519 | fix(ship-loop): authenticate the guard's GitHub calls; never leak the token off-host | 2026-07-25 |
| #3518 | test(personality): re-pin rotted W4 surfaces suite after Prophet card v1 + wire into CI | 2026-07-25 |
| #3516 | fix(seo): align sitemap with public access boundary | 2026-07-25 |
| #3515 | fix(render-lanes): light up flow_leaders — express-lane coverage + loud fail-soft | 2026-07-25 |
| #3514 | fix(ci): heal the two reds #3499 landed on main — dag.yml declaration + flow-surface job deps (OEU M-XP) | 2026-07-25 |
| #3512 | fix(site-access): give /research/ a tracked target in fresh checkouts | 2026-07-25 |
| #3511 | ci: wire flow-leaders / market-structure / options-screener / support-map suites (OEU rot guard) | 2026-07-25 |
| #3509 | ci(tier-gate): trigger on the serving-boundary files the job tests | 2026-07-25 |
| #3508 | feat(nav): replace Research mega-menu emojis | 2026-07-25 |
| #3507 | fix(ci): heal tier-gate red on main — /research/ runtime-plane exemption | 2026-07-25 |
| #3506 | test(flow-leaders): retire the exact-27 registry pin — count-agnostic + structural asserts | 2026-07-25 |
| #3504 | fix(site-access): un-exempt /research/ + wire tier-gate to its own inputs | 2026-07-25 |
| #3503 | test(research-factory): un-rot the governance double + guard it against re-drift | 2026-07-25 |
| #3502 | docs(media): heal three stale cross-references left by rev 3 | 2026-07-25 |
| #3501 | build(research): land the /research/ SEO estate #3488 opened at the edge | 2026-07-25 |
| #3500 | feat(prophet): display-tier options context — wall/IV flags, entry_read caveats, thesis sentence, structure receipt (OEU M-PRO) | 2026-07-25 |
| #3499 | feat(options-estate): dated surface retention + R2 mirrors + screener export + flow_desk session curve + Terminal deep links (OEU M-XP) | 2026-07-25 |
| #3498 | design(oeu): Options workspace pinned spec + static mockup (4 modes, bilingual) | 2026-07-25 |
| #3497 | docs(chronicle): align third-party event constraint with AM-R4 rev 3 | 2026-07-25 |
| #3496 | fix(options-estate): flow_leaders washout truth, market_structure week_map/DAG/copy, screener denominators (OEU M-FIX) | 2026-07-25 |
| #3495 | fix(calibration): judge desks against their own null, not a 0.5 "coin-flip" bar | 2026-07-25 |
| #3494 | fix(experiments): live-read the 13 stale admin panel states + past-due 'next in -10d' card | 2026-07-25 |
| #3493 | fix(ship-loop): scope the render precondition to the merge's own diff | 2026-07-25 |
| #3492 | fix(factor-panel): anchor dna_class.json on the PIT-evaluable cross-section | 2026-07-25 |
| #3491 | fix(brain): Pro-lane degraded fallbacks + OAuth-pool load-balancing (Opus 5 capacity) | 2026-07-25 |
| #3490 | research(agentic-media): rev 3 — operator ruling on posture; isolation layer replaces disclosure regime | 2026-07-25 |
| #3489 | feat(research-vault): public first-pages excerpt on SEO report pages (quote-search lane) | 2026-07-25 |
| #3488 | feat(site-access): open /research/ as public SEO estate — the #3392 landing pages' missing edge half | 2026-07-25 |
| #3487 | fix(research-vault): light up the /research/ SEO pages — render-lane coverage + loud fail-soft | 2026-07-25 |
| #3486 | feat(account): revamp the settings dashboard — larger card, Billing + Usage tabs, richer UX | 2026-07-25 |
| #3485 | research(oeu): Options Estate Unification masterplan (workspace ruling + lane charters) | 2026-07-25 |
| #3484 | Replace regional submenu emoji with product icons | 2026-07-25 |
| #3483 | fix(brain): Fast lane down — DeepSeek retired deepseek-chat → deepseek-v4-pro | 2026-07-25 |
| #3482 | research(agentic-media): charter Chronicle + Persona Network (D13) + Media Network (D14) | 2026-07-25 |
| #3481 | ci(tier-gate): wire the registration-wall suites — the boundary's last unwatched half | 2026-07-25 |
| #3479 | China Special Situations: Insider+ gate behind a free overhang preview | 2026-07-25 |
| #3478 | marketing Phase 3: breaking dispatch — Buffer share-now, floor-respecting immediate sends, admin "Post now" | 2026-07-25 |
| #3477 | fix(neural-web): regenerate SIGNAL_BUS.md for personality-timing-codex (#3460) | 2026-07-25 |
| #3475 | Fix landing hero card overlap and responsive sizing | 2026-07-25 |
| #3474 | fix(access): heal site_access boundary drift from #3418 and wire it into CI | 2026-07-25 |
| #3473 | Correct Canada flag maple leaf geometry | 2026-07-25 |
| #3472 | admin: make the desk on/off toggle work in deployed mode (GitHub Contents API) | 2026-07-25 |
| #3471 | feat(special-situations): lock the desk to Insider/Pro behind a free preview shell | 2026-07-25 |
| #3470 | feat(onboarding): rebuild the sign-up sheet — animated tier-lattice stage, scrollable steps, mobile | 2026-07-25 |
| #3469 | marketing: fix Buffer "dueAt must be in the future" — the real zero-posts cause | 2026-07-25 |
| #3468 | marketing(outbox): seed today's weekend reach batch + de-dup ROST | 2026-07-25 |
| #3467 | marketing: weekend reach lane — popular-ticker "levels into the week" posts | 2026-07-25 |
| #3466 | marketing: weekend posting — tape gate treats last close as fresh when market closed | 2026-07-25 |
| #3465 | perf(start): thermal guard for hero animation loops — fix iPhone overheating | 2026-07-25 |
| #3464 | fix(account): light-theme the shared settings dashboard on the landing + declutter profile + Insider→Pro-forward upgrade | 2026-07-25 |
| #3463 | feat(brain): Mastermind Pro/Research lane → claude-opus-5 at high intensity | 2026-07-25 |
| #3462 | Refine navigation icons for institutional styling | 2026-07-25 |
| #3461 | feat(flow): intraday greek grids — gex/dex/vanna/charm surfaces in the Flow-Surface store | 2026-07-25 |
| #3460 | personality-codex: W2 Personality Timing Codex (display-tier measurement store) | 2026-07-25 |
| #3459 | research(personality): PSS §4 brainstorm — W-SIG slate (4 reset-ID families + shared terminality gate) + foundry lens config | 2026-07-25 |
| #3458 | Modernize primary navigation with flag-derived icons | 2026-07-25 |
| #3457 | fix(brain): fail over on provider-unavailable (402 / DeepSeek Insufficient Balance) | 2026-07-25 |
| #3456 | feat(txi): per-ticker revenue-geography collector (EDGAR 10-K XBRL) — geo_revenue block + dollar-chain screens re-enabled (rev 2) | 2026-07-25 |
| #3454 | fix(auth): sticky login — silent wall-resume instead of re-prompting signed-in visitors | 2026-07-25 |
| #3453 | fix(brain): Mastermind lanes blacked out — fail over to Anthropic fallback on 401/403 | 2026-07-25 |
| #3452 | feat(flow): intraday Flow-Surface snapshot store — per-strike net-premium grids for the Terminal surface pane | 2026-07-25 |
| #3451 | feat(learn): Options & Dealer Positioning track — 7 bilingual-chrome lessons + Signal-Ink diagrams | 2026-07-25 |
| #3450 | deploy(macro): publish rebuilt risk sentiment popup | 2026-07-25 |
| #3449 | feat(marketing): publisher sweeps the 2h ladder — 9 runs/day, every day | 2026-07-25 |
| #3448 | fix(macro): rebuild risk sentiment layout and enforce ship loop | 2026-07-25 |
| #3447 | research(quanted): quantedoptions.com teardown — RECON, masterplan, API samples, decoded shader | 2026-07-25 |
| #3446 | feat(marketing): 2h Pacific signal ladder — 8 clock slots, DST-safe (cadence Phase 2) | 2026-07-25 |
| #3445 | research(personality): Signal Suite masterplan — codex, lab upgrade, families, confluence, idea foundry | 2026-07-25 |
| #3444 | research_vault: recover MarketDesk-truncated titles from the PDF /Title | 2026-07-25 |
| #3443 | feat(case): winner autopsy MNSO 2023 | 2026-07-25 |
| #3442 | Nightly timeout fix: GDELT circuit breaker (build_news 26min → 2min when IP is 429-boxed) | 2026-07-25 |
| #3441 | feat(case): winner autopsy VCYT 2020 | 2026-07-25 |
| #3440 | feat(case): winner autopsy TNDM 2024 | 2026-07-25 |
| #3439 | feat(mag7): MWR shadow-book additive timing scorecard — §7 item 4, both rulers side-by-side (PTT-W1-T R-W1T-5) | 2026-07-25 |
| #3438 | feat(case): winner autopsy BIDU 2006 | 2026-07-25 |
| #3437 | canada: hero-first header, commodity/TSX-V tiles, emoji→icon testbed | 2026-07-25 |
| #3436 | fix(us_stocks): rework market-state banner, sector-leader chip & accumulation panel; drop Mag7 pin + stale copy | 2026-07-25 |
| #3435 | feat(case): winner autopsy CHWY 2022 | 2026-07-25 |
| #3434 | feat(marketing): global 10-min post-spacing floor — drain the backlog, no bursts | 2026-07-25 |
| #3433 | research(personality): PTT-W1-T — §7 bottom-picking re-grade: structure arm clears random CI-clean; audition = two-ruler kill; reset-confirmer copy law | 2026-07-25 |
| #3432 | Stage Analysis: region filter → US-first (US/China/HK/Canada/Other), drop All | 2026-07-25 |
| #3431 | feat(txi): W2 — blast-radius resolver (structured screens + universe sweep) | 2026-07-25 |
| #3430 | research(personality): §7 ruler amendment — bottom-picking primary, hold-returns demoted (operator correction) | 2026-07-25 |
| #3429 | fix(marketing): flagship auto-posts — enable auto_approve + fix -1 (unlimited) cap dropping every item | 2026-07-25 |
| #3428 | docs(live-tape): close Phase 3 by audit (cadence + hero freshness already satisfied) | 2026-07-25 |
| #3427 | research(personality): PTT-W1 persistence-of-fit — audition-tailoring killed; structure lane (W2 codex + W3 shadow) proceeds | 2026-07-25 |
| #3426 | fix(live-tape): 10Y ws delta in bps (derive prevClose from chgPct) + kill -0.00% | 2026-07-25 |
| #3425 | research_vault: continuous-scroll PDF viewer (fix stuck-on-page-1) | 2026-07-25 |
| #3424 | feat(txi): W1 — chain ledger + compiler + episode state machine (4 seed chains) | 2026-07-25 |
| #3423 | feat(wri): W4 — pre-trade check (what-if diagnostic, operator-signed NWP-U18 carve-out) | 2026-07-25 |
| #3422 | fix(marketing): publisher cancelled before it runs — raise timeout 15→25m + cap jitter 10→5m | 2026-07-25 |
| #3421 | fix(breadth): track the midcap closes cache (stale-tier root fix for the live poller) | 2026-07-25 |
| #3420 | fix(live-tape): scale-aware ^TNX transform (live feed delivers percent) | 2026-07-25 |
| #3419 | ops(caddy): fix invalid multi-path bare handle from #3418 | 2026-07-25 |
| #3418 | ops(caddy): open /ws/tape + /live/breadth.json through the access gate | 2026-07-25 |
| #3417 | research(personality): handoff v2 — W1b structure-tailoring arm (operator's measurement thesis formalized) | 2026-07-25 |
| #3416 | ops(caddy): route /ws/tape to macro-api — arm the live tape relay | 2026-07-25 |
| #3415 | feat(us_stocks): compact live breadth scoreboard — glance bar + tiles, full board demoted to dialog (Phase 2 surface) | 2026-07-25 |
| #3414 | feat(live-tape): live intraday breadth poller → site/live/breadth.json (Phase 2 engine lane) | 2026-07-25 |
| #3413 | research(personality): timing-tailoring handoff charter — W1 persistence study pinned + roadmap | 2026-07-25 |
| #3412 | test(china): re-pin rotted copy_w09 suite to Prophet h2 tooltip + wire into CI | 2026-07-25 |
| #3411 | fix(china): re-pin act_now organ-chip tests to plain-word copy + CI-wire suite | 2026-07-25 |
| #3410 | research(mag7): MWR §2d — timeframe×personality ladder (MCD-rung confirmed; basket 2W home robust) | 2026-07-24 |
| #3409 | feat(mag7): MWR Amendment 2 — operator override, Use-B conditional-live behind the accelerating-tightening veto | 2026-07-24 |
| #3408 | Fix landing pricing responsiveness and compact hero cards | 2026-07-24 |
| #3407 | research(txi): charter Transmission Intelligence — cascade tracking + blast radius + self-improving chain ledger (W0) | 2026-07-24 |
| #3406 | watchlist: fix double-escaped ampersand in page h1 | 2026-07-24 |
| #3405 | feat(wri): W3 — wire the book-structure risk read into watchlist.html | 2026-07-24 |
| #3404 | feat: move live macro orchestration to VPS | 2026-07-24 |
| #3403 | fix(deploy): reconcile security config on no-op updates | 2026-07-24 |
| #3402 | research(mag7): MWR phase-1 adjudication — census cannot ratify Use-B (base-rate 69%) | 2026-07-24 |
| #3401 | Prophet: move daily changes into dashboard popup | 2026-07-24 |
| #3400 | feat(live-tape): six-instrument futures tape + same-origin /ws/tape relay (Phase 1) | 2026-07-24 |
| #3399 | test(china): re-pin w1c render suite to Prophet-card markup + wire into CI | 2026-07-24 |
| #3398 | feat(mag7): MWR-W1 — shadow book, Prophet confluence sidecar, NW lobe, operator trigger ping | 2026-07-24 |
| #3397 | security(site): protect static data and stage paid wall | 2026-07-24 |
| #3396 | design(wri): W2 — pinned design spec + patch-bay mockup + reference crops | 2026-07-24 |
| #3395 | feat(us_stocks): Prophet × Top-setups presentation merge — ⚡ trigger chip + residual-only sub-board | 2026-07-24 |
| #3394 | feat(wri): W1 — stress-conditioned factor covariance in factor_betas.json | 2026-07-24 |
| #3393 | feat(regwall): gate paid JSON payloads (/factordata + /labdata) at the edge | 2026-07-24 |
| #3392 | feat(research-vault): programmatic SEO — one indexable landing page per report | 2026-07-24 |
| #3391 | feat(landing): Prophet teaser → 2-week-delayed winners, never the live board | 2026-07-24 |
| #3390 | fix(landing): prophet belt keeps drifting on hover (0.7x), no full stop | 2026-07-24 |
| #3389 | research(wri): charter Watchlist Risk Intelligence — risk-detecting watchlist revamp (W0) | 2026-07-24 |
| #3388 | feat(mag7): washout re-entry gate — prereg + background engine + phase-0 census (MWR-W0) | 2026-07-24 |
| #3387 | feat(regwall): open the SEO estate to crawlers + faster/smarter login | 2026-07-24 |
| #3386 | feat(research-vault): static filter bar + show-more pagination | 2026-07-24 |
| #3385 | fix(ci): heal contract-drift — canada_standouts conditional fields reclassified as optional_fields | 2026-07-24 |
| #3384 | feat(research-vault): lock glyph on the Pro-only Top Picks tab | 2026-07-24 |
| #3383 | Hub welcome: a refresh isn't a visit (gap-based counting + clearer recall) | 2026-07-24 |
| #3382 | Regime dynamics: never emit a regime label without its trajectory | 2026-07-24 |
| #3381 | Hub welcome: market-aware conversation + slower dissolve (fix dropped greeting) | 2026-07-24 |
| #3380 | feat(research-vault): desk constellation, macro fonts, publish times, full-page reader, Pro tiering | 2026-07-24 |
| #3379 | feat(mastermind): log all Mastermind AI responses to an admin eval corpus | 2026-07-24 |
| #3378 | Personal dashboard: fix stuck "Loading your plan…" + tier/expiry + upgrade CTA | 2026-07-24 |
| #3377 | Landing login persistence (CORS fix) + start.html personal welcome & home globe | 2026-07-24 |
| #3376 | feat(marketing): autonomous cadence Phase 1 — lift daily post/media cap to unlimited | 2026-07-24 |
| #3375 | fix(admin): Outbox — approved posts leave the review list into a collapsed "awaiting publish" shelf | 2026-07-24 |
| #3374 | ci(render-lanes): heal template↔site pairs BEFORE the first commit in all 6 externalizing lanes | 2026-07-24 |
| #3373 | ops(daily): engine timeout 150→200m — nightly engine cancelled at the cap 5 of last 8 nights | 2026-07-24 |
| #3372 | perf(cycles): split cycle payloads + parallel preloaded loader + immutable-cacheable URLs + skeleton | 2026-07-24 |
| #3371 | fix(fonts): "SF Mono"-first --num stacks render numerals as serif in Chrome — lead with ui-monospace sitewide | 2026-07-24 |
| #3370 | fix(leader-radar): LRV-O9 — entry-read stance layer, parabolic sign guard, Tonight's Focus stance shelves | 2026-07-24 |
| #3369 | China track record: log ticker names + fix vs-CSI300 nulls-last sort | 2026-07-24 |
| #3367 | onboard: materializing desk pane replaces the assembly-card rail | 2026-07-24 |
| #3366 | authfe: post-login redirect, upgrade sheet, landing auth chrome + gear parity | 2026-07-24 |
| #3365 | feat(landing): Prophet showcase section — real card belt below the Terminal | 2026-07-24 |
| #3364 | feat(billing): generalize upgrade matrix + expose plan interval | 2026-07-24 |
| #3363 | docs(marketing): masterplan go-live reflects the panel toggle (#3361) | 2026-07-24 |
| #3362 | fix(tests): heal test_seo_meta_rollout (12 reds) + wire it into the ci.yml whitelist | 2026-07-24 |
| #3361 | feat(admin): publisher Arm/Disarm toggle + token paste-box — kill-switch moves to repo variable | 2026-07-24 |
| #3360 | feat(admin): revenue analytics + projections — live Stripe MRR/ARR/cash/forecast | 2026-07-24 |
| #3359 | fix(us_stocks/macro): remove forced Mag-7 'Big Seven' board + demote Ignition Radar to background-only | 2026-07-24 |
| #3358 | fix(sync): re-sync site/index.html + site/chat.html from templates/ — heal template-site-sync red on main | 2026-07-24 |
| #3357 | fix(tests): anchor W-OVC fixture expiries to the frozen chain date — front7 keying test was vacuous | 2026-07-24 |
| #3356 | chore(admin): drop token-rotation prompts from go-live checklist | 2026-07-24 |
| #3355 | feat(billing): prorated Insider→Pro upgrade + plan/expiry in the personal dashboard | 2026-07-24 |
| #3354 | feat(admin): users/subscribers suite — per-tier roster, comps, trials, passes | 2026-07-24 |
| #3353 | feat(regwall): registration lockdown — all dashboard pages require an account | 2026-07-24 |
| #3352 | fix(tests): UTC-midnight fixture-bomb audit — pin test_symbol_directory to the engine's UTC clock | 2026-07-24 |
| #3351 | fix(auth): the onboarding sheet is SITE-WIDE on www — no auth entry navigates to app.* | 2026-07-24 |
| #3350 | fix(ci): parquet-reader guard on PLTR load_closes test (heals marketing-engine lane) | 2026-07-24 |
| #3349 | docs(marketing): suite audit masterplan + forward roadmap | 2026-07-24 |
| #3348 | feat(admin): marketing operator console — pipeline hero, controls, go-live checklist | 2026-07-24 |
| #3347 | fix(marketing): engine correctness — per-day caps, account liveness, receipts, slot times (1/3) | 2026-07-24 |
| #3346 | feat(marketing): per-post metrics poller + chart-image pipeline (Buffer) | 2026-07-24 |
| #3345 | fix(tests): de-flake marketing sentinel UTC-midnight fixture bomb + whitelist suite in CI | 2026-07-24 |
| #3344 | feat(landing): the onboarding sheet — landing-native signup/trial flow (§0 primary surface) | 2026-07-24 |
| #3343 | fix(marketing): publisher daily-cap counts ledger-based, not as_of-based | 2026-07-24 |
| #3342 | docs(onboarding): §0 surface ruling — sheet belongs to the landing, not the terminal app | 2026-07-24 |
| #3341 | fix(gex): Options Desk remaster — repair shipped UI bugs, rebuild layout & levels map | 2026-07-24 |
| #3340 | fix(flow_desk): nav dropdown painted behind the hero | 2026-07-24 |
| #3339 | feat(auth): every login/signup entry routes to the Terminal onboarding sheet | 2026-07-23 |
| #3338 | docs(claude): Spawn-handoff law — binding context for commissioned build sessions | 2026-07-23 |
| #3337 | fix(nav): remove '✨ Plans' from the site-wide dashboard menu | 2026-07-23 |
| #3336 | fix(research-vault): batch receipts behind the publish barrier (heals #3334 red test) + W6 charter | 2026-07-23 |
| #3335 | fix(landing+settings): operator 12-item pass — LIVE pill, brand marks, clear closing copy, Live-prices toggle removed | 2026-07-23 |
| #3334 | feat(research-vault): backfill hardening — checkpoints, body cap, non-blocking corpus refresh (+W6 charter) | 2026-07-23 |
| #3333 | feat(marketing): publish-time mover/theme generation + scoped auto-approve | 2026-07-23 |
| #3331 | feat(landing): closing-band bookend + real footer + hero gradient signature | 2026-07-23 |
| #3330 | fix(billing): SetupIntent card-family only (allow_redirects=never) | 2026-07-23 |
| #3329 | fix(research-vault): call the research API same-origin (not app.*) | 2026-07-23 |
| #3328 | feat(billing): Stripe Elements subscription lane — in-sheet card-up-front trials (W2) | 2026-07-23 |
| #3327 | feat(landing): MOST POPULAR badge + primary CTA move Insider -> Pro (operator ruling) | 2026-07-23 |
| #3326 | feat(marketing): fintwit voice v3 + post-time tape gate + outbox persistence heal | 2026-07-23 |
| #3325 | feat(landing): pricing-tier CTAs deep-link into the Terminal onboarding sheet (?plan= params) | 2026-07-23 |
| #3324 | fix(gex): restore body top padding — heal repo-wide nav-gap red | 2026-07-23 |
| #3323 | feat(portfolio): W1 — brief composer + GET /api/portfolio/brief + Brain get_portfolio_brief tool | 2026-07-24 |
| #3322 | feat(china-altdata): trading-intensity waterline in the tape hero | 2026-07-23 |
| #3321 | feat(research-vault): separate-account R2 credentials (R2_RESEARCH_*) | 2026-07-23 |
| #3320 | feat(flow-velocity): rotation/momentum/confluence dashboard + glance engine | 2026-07-23 |
| #3319 | feat(heatmap): mx5 dashboard revamp — pulse, breadth & movers on all 5 heatmaps | 2026-07-23 |
| #3318 | feat(china-altdata): mx5 editorial revamp + institutional alt-data planes | 2026-07-23 |
| #3317 | fix(ops): deploy-api-secrets _add no longer trips set -e on an absent secret | 2026-07-23 |
| #3316 | ops(billing): deliver Stripe secrets to VPS via deploy-api-secrets (W0) | 2026-07-23 |
| #3315 | feat(research-vault): W3 flagship page + gated pdf.js viewer (blue mx5) | 2026-07-23 |
| #3314 | feat(darkpool): actionable Fable revamp + darkpool_context.v1 Neural Web lobe | 2026-07-23 |
| #3313 | feat(portfolio): W1 — full-universe portfolio_ctx nightly bake (sector unification + theme lanes) | 2026-07-24 |
| #3312 | feat(news-translate): translate fresh titles on render lanes (render_lanes on) | 2026-07-23 |
| #3311 | feat(committee): mx5 revamp — living-brain hero, chapter tabs, curated IA | 2026-07-23 |
| #3310 | feat(subsectors): answer-first mx5 revamp — rotation hero, confluence ribbon, buy/avoid board | 2026-07-23 |
| #3309 | fix(billing): align plans.yml to LOCKED onboarding pricing ($69/$99 monthly) — W0 | 2026-07-23 |
| #3306 | feat(portfolio): W0 — portfolio_ctx.v1 contract + stubbed 3-ticker bake + tests | 2026-07-23 |
| #3305 | feat(pricing): v2 ladder + onboarding/subscription-flow masterplan | 2026-07-23 |
| #3304 | docs(research): Portfolio-Aware Intelligence masterplan (Pro-pillar handoff) | 2026-07-23 |
| #3303 | feat(case): winner autopsy SG 2023 | 2026-07-24 |
| #3302 | ci(heartbeat): schedule pure guards against main so silent rot is visible | 2026-07-23 |
| #3301 | feat(case): winner autopsy TSM 2000 | 2026-07-24 |
| #3300 | feat(case): winner autopsy ASPI 2025 | 2026-07-24 |
| #3299 | feat(case): winner autopsy MNSO 2021 | 2026-07-23 |
| #3298 | feat(case): winner autopsy CENX 2024 | 2026-07-24 |
| #3297 | feat(landing): hero whitespace fix + tier ladder rebalance (Flash AI / Pro AI) | 2026-07-23 |
| #3296 | harden(font-ui): guard recognizes Jinja-prefixed theme.css hrefs ({{ rel }}theme.css) | 2026-07-23 |
| #3295 | fix(ci): declare asia/weekly template-site-sync steps in dag.yml — heal dag-conformance lane | 2026-07-23 |
| #3294 | polish(landing): static INSIDER/PRO chips — no animation | 2026-07-23 |
| #3293 | polish(landing): tighter hero gap, gradient-border chips with glint, tier-card auroras | 2026-07-23 |
| #3292 | fix(deploy): macro-api restart trigger covers the /api/brain import chain (brings CMX W4 live) | 2026-07-23 |
| #3291 | feat(cmx-w4): Technician Doctrine library — intent-routed chart-reading craft for Terminal brain sessions | 2026-07-23 |
| #3290 | fix(render-guards): re-pin sector-stance tests to the prophet-card popover home | 2026-07-23 |
| #3289 | fix(ci): heal 3 red lanes — font-ui guard on seo_base, sector-pulse consumer contract, canada_standouts schema drift | 2026-07-23 |
| #3288 | fix(marketing): emit content plan into outbox nightly + persist it | 2026-07-23 |
| #3287 | feat(news): Markets News revamp — hero-led ranked feed, real aging + stronger ranking + AI-feed connector | 2026-07-23 |
| #3286 | feat(landing): iteration 7 — pyramid hero + choreographed cycle, 1m live terminal, extended AI demo, skimmable pricing | 2026-07-23 |
| #3285 | fix(landing): re-sync plain-copy index/chat + heal the two render lanes that diverge them | 2026-07-23 |
| #3284 | chore(marketing): wire flagship Buffer channel id (@mastermindx001) | 2026-07-23 |
| #3283 | feat(research-vault): W2 serving API + download gate | 2026-07-23 |
| #3282 | feat(baskets): Rotation Map revamp — verdict hero + act board + strength×momentum quadrant | 2026-07-24 |
| #3281 | fix(workflows): autoresolve hashed-css rename/rename in push-rebase loops; asia-close fails loudly | 2026-07-23 |
| #3280 | perf(tools): Risk of Ruin Monte-Carlo runs in a Web Worker (UI never blocks) | 2026-07-23 |
| #3279 | fix(nav): restore the 18px top gap the topbar→site-nav sweep dropped (nav-gap CI red) | 2026-07-23 |
| #3278 | feat(bonds): flagship revamp — macro design language + Signal-Ink charts, glance-first IA | 2026-07-23 |
| #3277 | fix(marketing): correct stale seed-ledger test + whitelist it in CI | 2026-07-23 |
| #3275 | fix(hk-pick-lab): _col container crash + snapshot upsert Series bug + CI whitelist | 2026-07-23 |
| #3274 | fix(mobile): remove the floating back-to-top button (twin of the chat orb) | 2026-07-23 |
| #3273 | fix(mobile): collapse chat launcher to an orb, stack back-to-top above it | 2026-07-23 |
| #3272 | feat(landing): live-quote override — /live/quotes.json re-anchors baked hero/econ/tri-panel/watchlist values on load | 2026-07-23 |
| #3271 | fix(hk): hk_stocks revamp — plain-word IA, chronic false STALE banner, Pick Lab crash, southbound units ×100 | 2026-07-23 |
| #3270 | feat(landing): Terminal section → Safari-framed live product showcase + hero real-quote refresh | 2026-07-23 |
| #3269 | fix(boards): prophet card fit — no clipped stage labels or dates, wider card minimum | 2026-07-22 |
| #3268 | feat(tools): macro-terminal revamp of /tools + 20 new SEO calculators | 2026-07-22 |
| #3267 | feat(marketing): live social publisher (Buffer, dark by default) | 2026-07-22 |
| #3266 | feat(macro): remove Macro Dashboard topbar strip (brand + as-of date + divider) | 2026-07-22 |
| #3265 | research: postmortem 2026-07-22 — crossovers vs capex bind (Mag-7 dispersion) + integration charter | 2026-07-22 |
| #3264 | feat(commodities): oil→XEG cross-asset context chip (display-tier, C1-R2) | 2026-07-22 |
| #3263 | fix(landing): hide Research Reports teaser on mobile compact card (no icon overlap) | 2026-07-22 |
| #3262 | feat(prophet-card): buy-zone band on the card sparkline (E1 phase 2) | 2026-07-22 |
| #3261 | feat(admin): compute + surface bot-loop liveness on the Mastermind AI hero | 2026-07-22 |
| #3260 | fix(landing): terminal chart fills its column (no dead space under axis) | 2026-07-22 |
| #3259 | fix(landing): fixed-height chat + AI section side-by-side, neural web archived | 2026-07-22 |
| #3258 | feat(research-vault): W0 masterplan + W1 ingestion spine | 2026-07-23 |
| #3257 | feat(landing): iteration 3 — diagram layout, mx5 gauge, real scorecard-v2, locked terminal feed | 2026-07-22 |
| #3256 | feat(boards): Prophet card v1 — one flagship scorecard across US/CN/HK/CA/INTL | 2026-07-22 |
| #3255 | fix(landing): composer class collision, prophet rail legend, economies clipping | 2026-07-22 |
| #3254 | feat(intl): World Command hero + user-first IA revamp (macro.html design system) | 2026-07-22 |
| #3252 | feat(reports): shareable deep-link filter state + Esc-to-clear | 2026-07-23 |
| #3251 | feat(foresight): Fable-quality UI revamp — lead-time relay + user-first IA | 2026-07-23 |
| #3250 | feat(themes): State of Themes revamp — stance-lane board + lifecycle signature | 2026-07-22 |
| #3249 | feat(china): National Team Radar + mx5 revamp of policy-watch & special-situations | 2026-07-22 |
| #3248 | fix(brain-widget): chip labels never wrap — title ellipsizes instead | 2026-07-22 |
| #3247 | feat(brain-widget): chat v2 — streaming engine, smooth reveal, message redesign, thread management, power features | 2026-07-22 |
| #3246 | feat(ipo): gated "Demand (vs range)" revision column + dark-red fix | 2026-07-22 |
| #3245 | feat(admin): surface alert-triage calibration on the Alerts page | 2026-07-22 |
| #3244 | feat(landing): iteration 2 — top-down hero, real NVDA data, animated AI chat, pricing aurora | 2026-07-22 |
| #3243 | feat(hub): wire IPO Radar card onto the AURORA landing hub | 2026-07-22 |
| #3242 | feat(admin): surface the degraded AI cortex on the Observatory + Master Brain heroes | 2026-07-22 |
| #3241 | perf(admin): behavioral fixes — cache link crawl, batch GitHub calls, guard deploys | 2026-07-22 |
| #3240 | fix(tests): retrack test_brain_reconcile_clamps to post-#2372 deterministic-ceiling _reconcile | 2026-07-22 |
| #3239 | feat(brain): thread rename + delete endpoints (owned, guest-locked) | 2026-07-22 |
| #3238 | fix(marketing): unbreak earnings fast lane (em dash) + bare-domain link tagging (www host) | 2026-07-22 |
| #3237 | perf(admin): trim ~415KB of unread payload off the landing + heavy panels | 2026-07-22 |
| #3236 | fix(nav): rename Flow Desk link "Group Flow Heatmap" → "US Options Flow" | 2026-07-22 |
| #3235 | fix(nav): restore .site-nav wrapper on the remaining 12 standalone templates (menu sweep complete) | 2026-07-22 |
| #3234 | render(flow-desk): bake "Options Tape" revamp to live | 2026-07-22 |
| #3233 | feat(altdata): gauntlet special_situation + de-escalate 0.40→0.20 to its null gate | 2026-07-22 |
| #3232 | feat(ipo): mx5 aurora-glass flagship revamp — hero, AVOID panel, lock-up timeline, ilx chart + lobe hardening | 2026-07-22 |
| #3231 | feat(etfs): Fable-design revamp of Real Fund Moves — consensus board, stances & rotation backdrop | 2026-07-22 |
| #3230 | feat(leader-radar): mx5 design revamp — hero verdict + funnel, de-noised layout | 2026-07-22 |
| #3229 | feat(intraday-flow): mx5 design revamp — Session Pulse hero + "Look here first" spotlight (V3 UI) | 2026-07-22 |
| #3228 | design(vector): hero balance + keyboard-focus polish | 2026-07-22 |
| #3227 | fix(marketing): TSMC earnings-card padding/logo + D05 Truth Social red-team memo | 2026-07-22 |
| #3226 | feat(flow-desk): user-first "Options Tape" revamp — Fable aurora-glass, honest read, fixed cohorts | 2026-07-22 |
| #3225 | fix(admin): panel-truth wave 2 — 8 more broken-data bugs across 6 lobes | 2026-07-22 |
| #3224 | feat(flow-leaders): revamp UI + engine — macro design language + user-first doctrine | 2026-07-22 |
| #3223 | feat(gex): Options Desk "Gravity Map" revamp — transmission-grade UI | 2026-07-23 |
| #3222 | feat(radar): user-first Divergence Radar revamp — Fable mx-hero + honest track record | 2026-07-22 |
| #3221 | design(vector): transmission-grade revamp — orange identity, vector signature, forces rail, deep-dive shelf | 2026-07-22 |
| #3220 | feat(china-news): flash-wire tape revamp — timestamped stories, transmission-grade UI | 2026-07-22 |
| #3219 | fix(altdata): reconcile earnings_beat test + weight with #3211 metric-only demotion | 2026-07-22 |
| #3218 | feat(reports): rebuild Research Reports as an aurora-glass research center | 2026-07-22 |
| #3217 | fix(admin): panel-truth pass — Health/Prophet/Context-Lobe stop misreporting status | 2026-07-22 |
| #3216 | fix(altdata): down-weight activist_13d 0.55→0.20 to its null gauntlet (board-ranking honesty) | 2026-07-22 |
| #3215 | feat(intel-hub): regime-condition the hub track-record (V3 regime hardening) | 2026-07-22 |
| #3214 | fix(admin): security hardening — critical login-lockout bypass + document CSP | 2026-07-22 |
| #3213 | feat(intel-hub): insider-cluster selection edge — strength ordering + per-feed measurement (V3 Phase 2) | 2026-07-22 |
| #3212 | feat(commodities): C1-R2 oil→XEG prereg + honest Phase-0 caveat + program reconciliation | 2026-07-22 |
| #3211 | feat(altdata): robust names + de-noised channels + earnings catalyst clock | 2026-07-22 |
| #3210 | test(froth-fragility): reconcile bilingual smoke test with mx5 v2 card | 2026-07-22 |
| #3208 | feat(stock-desk): stop shorting momentum leaders — lean recalibration (V3 Phase 3) | 2026-07-22 |
| #3207 | feat(china-radar): CN radar-IC grader — CN parity for the signal governor (V3 Phase 1b) | 2026-07-22 |
| #3206 | fix(commodities): honest active-model verdicts (copper fails DSR, silver marginal) | 2026-07-22 |
| #3205 | AI Cost: complete remote-ledger sync for remaining Opus lanes | 2026-07-22 |
| #3204 | AI Cost: unified per-lobe token tracking + illustrative page + remote-ledger sync | 2026-07-22 |
| #3203 | feat(psq-tilt): W1 hold-leash — Stage-2∩EC picks get 45→56d horizon (provisional, bear-gated, shadow auto-demote) | 2026-07-22 |
| #3202 | feat(wa): W4 matched-controls fingerprint study (Layer-3b) — pre-onset breakaway vs same-day controls | 2026-07-22 |
| #3199 | congress: fold long tables behind "Show more" toggles | 2026-07-22 |
| #3198 | fix(nav): restore .site-nav wrapper on BTC/commodity strategy pages (menus were dead) | 2026-07-22 |
| #3197 | design(settings): larger dashboard (860×660) + mobile height fallback | 2026-07-22 |
| #3196 | feat(china-intel-hub): CN/HK parity — signal governor + CN track-record grader (V3 Phase 1b) | 2026-07-22 |
| #3195 | fix(macro): dialog & popup polish sweep — 11 flagship fixes | 2026-07-22 |
| #3194 | design(china/hk/canada): port the macro.html mx5 design system to the country dashboards | 2026-07-22 |
| #3193 | chore(registry): register commodity xsec-momentum phase-0 kill in DO_NOT_REBUILD §2 | 2026-07-22 |
| #3192 | fix(smart-money): repair Ownership Desk UI/text bugs — tooltip leak, holdings pills, board overflow, machine text | 2026-07-22 |
| #3191 | feat(intel-hub): close the measure→act loop — de-escalation-only signal governor (V3 Phase 1) | 2026-07-22 |
| #3190 | fix(site): repair 4 slow/broken sector & subsector pages | 2026-07-22 |
| #3189 | intl turn-tile popovers → plain-word LENS cards; +commodities title spacing | 2026-07-22 |
| #3188 | feat(brain): guest access — free Fast lane for everyone, admin-tunable daily cap | 2026-07-22 |
| #3187 | feat(cmx-w2): Eyes — deterministic chart digests + measure_line + ChartSession + v2 command validation | 2026-07-22 |
| #3186 | research(cmx): Chart Mastermind masterplan — chartered (W0) | 2026-07-22 |
| #3185 | feat(metabolism): V12 Surface Curator + Metered Loop — quality gate for UI additions, real token throttle | 2026-07-22 |
| #3184 | bottom-ledger: policy-free bottom-calling learning instrument (P1) | 2026-07-22 |
| #3183 | fix(track-record): "Below entry" not "Stopped" + open-marks disclosure (display honesty) | 2026-07-22 |
| #3182 | research(signal): veto-leg audit — macd_bear hard-blank fails its keep test; Washout Watch shelf proposed | 2026-07-22 |
| #3181 | residual-alpha: admit curated non-index extras to the board candidate set (CRCL fix) | 2026-07-22 |
| #3180 | fix(brain-widget): re-localize the widget live on a host language switch | 2026-07-22 |
| #3179 | chore(routing): Opus builds code, not Sonnet (operator 2026-07-21) | 2026-07-22 |
| #3178 | Stripe billing spine — checkout/webhook/portal + entitlements (MNZ W2) | 2026-07-22 |
| #3177 | fix(cls): pre-collapse the mobile nav at parse — 0.33 → 0.03 CLS on phone loads | 2026-07-21 |
| #3176 | feat(i18n): zh 红涨绿跌 color sweep — remaining 18 dashboards | 2026-07-22 |
| #3175 | fix(macro): zh 红涨绿跌 coherence — state JS, sparklines, chips, odometer, quad map, heat bars | 2026-07-22 |
| #3174 | fix(china): zh direction-convention flip on state gauge + pullback family (reverses #2947 no-flip) | 2026-07-22 |
| #3173 | feat(brain-widget): wire the sidebar Search into a live chat filter | 2026-07-21 |
| #3172 | design(settings): full settings dashboard modal — Account / Preferences / Sync | 2026-07-21 |
| #3171 | design(landing): round 2 suite mockups + V3.1 'Daylight, Live' build spec (operator pick) | 2026-07-22 |
| #3170 | design(brain-widget): drop redundant "New" pill from Chats header | 2026-07-21 |
| #3169 | fix(markets): defer/load-order heal — same class as the cycle.html blank | 2026-07-21 |
| #3168 | perf(mobile): breathing-animation sweep wave 2 — 9 more page families off the main thread | 2026-07-21 |
| #3167 | feat(brain): reflect unlimited-operator grant in the widget UI (Pro/Research/attach unlock) | 2026-07-21 |
| #3166 | perf(mobile): compositor-only breathing glows — macro 15/100 Lighthouse fix, wave 1 | 2026-07-21 |
| #3165 | fix(externalize_css): never lift <style> blocks inside inline <svg> — restores blank report figures | 2026-07-21 |
| #3164 | fix(levels): rebase board unconditionally — dividend basis, not just splits (follow-up to #3155) | 2026-07-21 |
| #3163 | feat(seo): D12 W1 — free acquisition estate: Calculator Lab, Learning Center, Blog + trading-journal spreadsheet | 2026-07-21 |
| #3162 | feat(psq): Prophet × Stage quality re-grade — PSQ prereg + pre-registered median/EA/stopped falsifiers, full run | 2026-07-21 |
| #3161 | feat(wa): W3 census fingerprint study (Layer-3a) — W2 candidates vs full-census base rates | 2026-07-21 |
| #3160 | feat(seo): Search Console ingestion adapter — credentials-gated demand loop (MKT-SEO-07 W0) | 2026-07-20 |
| #3159 | fix(cycle): repair blank cycle.html — defer/load-order regression | 2026-07-20 |
| #3158 | feat(universe): Russell 2000 + Dow 30 — dossier coverage grows to 2,778 names | 2026-07-20 |
| #3157 | feat(sga): Prophet × Stage forward-shadow — definitive on-Prophet fusion test, accruing from go-live | 2026-07-20 |
| #3156 | research(sga): Prophet×Stage fusion backtest — pre-registered NULL, kill the win-rate-gate construction | 2026-07-20 |
| #3155 | fix(levels): rebase reconstructed board onto adjusted price basis (split-basis bug) | 2026-07-20 |
| #3154 | fix(hub): keep a11y-critical CSS inline on index.html through the externalize pass | 2026-07-20 |
| #3153 | fix(master_brain): retry empty/refusal LLM replies so a lens can't go blank for the day | 2026-07-20 |
| #3152 | fix(seo): dossier mobile hardening — kill every small-screen bleed | 2026-07-20 |
| #3151 | feat(sga): Stage Analysis v2 — full EquityDesk transfer (6 surfaces) + dark hub redo | 2026-07-20 |
| #3150 | fix(theta): keepalive key via THETADATA_API_KEY env, never --api-key argv | 2026-07-20 |
| #3149 | fix(marketing): earnings card typography — sans-serif verdict chip, larger stat fonts | 2026-07-20 |
| #3148 | docs(seo): D12A status → W1 SHIPPED; retire stale apex-era NOTE in seo_director | 2026-07-20 |
| #3147 | feat(seo): meta rollout — _seo_head + ratified titles/descriptions across 94 public templates (D12A PR B) | 2026-07-20 |
| #3146 | design(seo): dossier v6b — popup dashboards (deep tier), machine-text scrub, Performance retired | 2026-07-20 |
| #3145 | chore(seo): source seo_director host constants from lib.seo | 2026-07-20 |
| #3144 | fix(seo): seo-director.yml invalid YAML — dispatch rejected, phantom 0s failures | 2026-07-20 |
| #3143 | feat(marketing): brand bar 'AI stock signals' tagline next to mastermind-x.com | 2026-07-20 |
| #3142 | feat(admin): Beacon SEO control plane — Marketing → SEO page (D12A PR D) | 2026-07-20 |
| #3141 | feat(seo): SEO Director — deterministic weekly audit engine + gated loop (D12A PR C) | 2026-07-20 |
| #3140 | feat(seo): technical foundation — www canonical host, full core sitemap, llms.txt + brand-facts, homepage JSON-LD (D12A PR A) | 2026-07-20 |
| #3139 | design(seo): dossier v6 — Terminal embed chart, trade-levels ladder, Inter-only type | 2026-07-20 |
| #3138 | ops(theta): zombie-proof terminal health checks (200+body law) + in-run watchdog; upstream current-day-400 skip | 2026-07-20 |
| #3137 | fix(seo): 24px top gap above site-nav on ticker dossier pages (nav-gap gate) | 2026-07-20 |
| #3136 | fix(theta): keepalive stdin via anonymous FIFO — tail-pipe deadlocked on java death | 2026-07-20 |
| #3135 | feat(illus): ilx "Signal Ink" illustration format — china/hk/canada off Plotly + HK news revamp | 2026-07-20 |
| #3134 | feat(brain): env-gated unlimited quota + token ceiling for operator allowlist (both lanes) | 2026-07-20 |
| #3133 | docs(marketing): define affiliate creator launch strategy | 2026-07-22 |
| #3132 | Docs: add Beacon SEO publishing and tools docket | 2026-07-20 |
| #3131 | feat(marketing): watchlist card v2 — portrait 4:5 mobile-first, color-logo avatar chips | 2026-07-20 |
| #3130 | perf(site): externalize inline CSS to cached hash files (HTML -44%) | 2026-07-20 |
| #3129 | ops(theta): stdin-safe run_theta_terminal.sh + runbook §3 launchd lanes | 2026-07-20 |
| #3128 | feat(cxi): CXI-R23a — operator-allowlist internals tools in Brain gateway | 2026-07-20 |

---

Before proposing or adjudicating new work: check your topic against the open-PR lanes above AND against `research/DO_NOT_REBUILD.md` (standing kills/forbidden designs).
