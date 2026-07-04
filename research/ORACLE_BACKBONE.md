# Oracle Institutional Backbone — architecture

**Goal.** Convert Oracle from a set of good artifacts into a *factory with contracts*: hypotheses flow through one standardized pipeline (generate → screen → accrue → promote), every consumer builds against a versioned interface, and forward time does validation work passively. Authored by Fable 2026-07-04 on the operator's double-down directive; extends [ORACLE_MASTERPLAN_BY_FABLE.md](ORACLE_MASTERPLAN_BY_FABLE.md) + [ORACLE_COMPOUND_LIBRARY.md](ORACLE_COMPOUND_LIBRARY.md).

## The five pillars

### W-B1 — The Research Factory (compound specs as DATA, screens as EXECUTION)
The single highest-leverage piece. Today a screen = someone writes pandas; causality bugs ride in with every author. Instead:
- **`data/oracle/compounds/registry.jsonl`** — append-only compound registry. A compound is a JSON spec: `{id, family, name, mechanism_en/zh, entry_rule, condition_rule, universe, horizons, status, created, lineage}`. Status ∈ {exploratory, screened, accruing, promoted, refuted}.
- **A constrained rule grammar** (declarative, no code): filters over panel/episode columns — comparators, `crossed_above/below`, `within_k_sessions_of(episode_event)`, `personality_is`, `regime_tag_is`. The grammar is the CAUSALITY FIREWALL: the runner joins everything as-of entry date by construction, so **a cheap model (ChatGPT/Haiku) contributes a compound by writing a spec, never code** — screening outsourced without outsourcing correctness.
- **`scripts/oracle_screen.py --compound <id|--all-pending>`** — the generic Tier-1 runner: parses the grammar, computes effect/n/hit/era-splits on the panels, appends the trial-ledger row, flips status exploratory→screened. Deterministic, seeded, ~seconds per compound.
- **`scripts/oracle_promotion_scan.py`** (nightly step): flags screened/accruing compounds crossing the economic floor (|63d excess| ≥ 1% or hit ≥ 55%, n ≥ 100, ≥3/4 era-consistent) into `data/oracle/promotion_queue.json` — a queue Fable adjudicates, never an auto-promotion. The scan also computes the CURRENT search-width count for the promotion-stage FDR (the factor-zoo accounting, automated).

### W-B2 — The Red Queen Interface Contract
The sibling brain must be able to build against Oracle without reading our source.
- **`engine/oracle/contract.py`** + **`docs/ORACLE_RED_QUEEN_INTERFACE.md`**: `payload_version` (semver) on `oracle_state.json`; REQUIRED core fields validated by `validate_payload()` which the nightly asserts BEFORE writing (a broken payload never ships); additive fields explicitly allowed (tolerant-reader pattern — the A3 regime tag and B1 personalities land as additive).
- **Confidence taxonomy on every signal-bearing field**: `validated | display_with_edge | exploratory | descriptive`, each with `lineage` (registration doc + verdict) — a consumer can filter to validated-only mechanically. **The "never" guarantees, in the contract**: no field implies a forecast without validated lineage; every alert-class field carries its measured error rate; Tier-M facts carry the survivorship watermark inline.
- Staleness contract: `asof` + `max_age_hours`; consumers must treat stale payloads as absent.

### W-B3 — Passive forward validation (time as the backtester)
Generalize the episode forward-ledger to EVERY registry compound: each nightly run evaluates every exploratory/accruing compound's rule on the live panel; fires get logged PIT (keep-first) into `data/oracle/compounds/live_ledger.jsonl`; outcomes auto-grade as horizons mature; the registry accrues **uncontaminated live n** per compound. This is the cheapest validation that exists — cond_b's path from n=194-backtest to promotable runs through here without another token of backtest compute. The promotion scan reads BOTH ledgers (historical screen + live accrual) and weights live evidence explicitly.

### W-B4 — Health & decay sentinels (second wave)
Panel schema-version stamp + drift tripwires (null-rate jumps, coverage drops — mirror the repo's audit_* and circuit-breaker patterns); **edge-decay monitors** on anything displayed (the 6 routing cells, onset alerts): rolling realized-vs-published stats with a "decayed below display floor" demotion path. Institutions assume signals die; the backbone notices.

### W-B5 — The Constitution (second wave)
One loadable `research/ORACLE_CONSTITUTION.md` consolidating the laws now scattered across P3/P8 adjudications, the library phase rules, R4 bindings, watermark law, verdict vocabulary, and the model-tier routing — so the governance survives session turnover; every future agent loads one doc.

## Sequencing & coordination
W-B1 + W-B2 + W-B3 build now (W-B3 folds into W-B1's nightly step). W-B4/W-B5 follow once the in-flight A3/B1/C1-C4 wave and this wave are merged (the constitution should codify their final shapes, not their drafts). Merge coordination: the in-flight wave and this wave both touch `oracle_nightly.py`/`live.py` — all step additions append-only at END; serialized merges; Fable resolves.

## Status
- 2026-07-04 — Architecture authored; W-B1/2/3 dispatched to the build tier.
