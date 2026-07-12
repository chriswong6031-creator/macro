# Metabolism v6 — Lobe Genesis (the orchestrator may charter new organs, under law)

**Status:** RATIFIED design 2026-07-12; W1 ships with this doc, W2/W3 dispatched.
**Owner program:** `autonomic-loop` (extends `METABOLISM_V4_FIRST_BREATH_BY_FABLE.md`, `METABOLISM_V5_DURABILITY_AND_SELF_REPAIR_BY_FABLE.md`).
**Operator directive (2026-07-12):** allow the master orchestrator to create new lobes — each with its own Opus-tier self-learning loop — as it sees fit to serve the mission ("superintelligent neural web"), explicitly NOT "go build random stuff for the sake of building."
**Method:** file:line census of the existing charter/lifecycle/scout machinery (receipts in the census record) + this Fable adjudication.

---

## 0. Executive ruling — the power already exists in law; the machinery is dark and half-born

The operator's directive is not a new constitutional grant — it is already ratified in the IMMUTABLE mission file (`config/nw_mission.yml`, pillar 3: *"Lobe stewardship: charter new lobes for uncovered domains… display-tier lobes are T1-autonomous"*; standing law R-V2-3: *"prune freely, anoint never"*). v4/v5 built most of the pipeline: the scout detects uncovered domains and emits display-tier charter proposals with evidence refs and roster-budget snapshots (`engine/metabolism/scout.py:425`); the applier consumes them inside the PROPOSE stage with a double tier-raise fence (`engine/metabolism/applier.py`, called at `scripts/metabolism_propose.py:145-163`); the two-key gauntlet, the build lane, and lifecycle states all exist; `config/lobe_charters.yml` is deliberately loop-writable (NOT in the self-mod-fence immutable set) so the fenced draft-PR lane can author charter edits.

What actually blocks genesis today, verified:

| # | Gap | Consequence |
|---|---|---|
| G1 | `scout.scan()` has **no scheduled caller** — grep of all workflows: zero invocations | Uncovered domains are never observed; `charter_proposals/` stays empty forever; the applier consumes nothing. Genesis is structurally OFF. |
| G2 | Newborn lobes are **born mute**: only TIL has a fitness-card builder (`build_til_fitness.py`, bespoke); a chartered lobe without a card is SENSE-only and PROPOSE serves it the R-V4-10 inert prompt | A genesis lobe could be chartered but never enters the learn loop — no contracts, no verify, no lessons. "Its own learning loop" cannot start. |
| G3 | PROPOSE runs for **one hardcoded lobe** (`LOBE = "til"`, `propose.py:85`); the parameterization exists (`--lobe`) but no lane iterates | Even a matured second lobe would never get authorship cycles. |
| G4 | No genesis-specific screens: charter proposals convert to `kind="engine"` (applier `_item_to_proposal`), adjudicate has no kind branching; the CHF metabolism-family deferral (DO_NOT_REBUILD §4, clock 2026-10-15), the "is it actually a lobe" case law (NARR-NWC, NEXT3-U5), and the roster cap are not enforced at the genesis gate (scout is advisory-only BY DESIGN, R-V2-7) | The gauntlet would judge a new-organ decision with generic screens — the "don't go crazy" half of the directive is under-specified in code. |

**The ruling:** wake the feelers (W1), harden the genesis gate (W2), give newborns a working metabolism (W3). Everything display-tier, everything through the existing cage; no new workflows per lobe — a lobe's "own Opus loop" is the existing SENSE→AGENDA→PROPOSE→ADJUDICATE→BUILD→VERIFY→DREAM stages iterating over it (propose/adjudicate brains are already Opus-tier by config). Nothing here arms anything; all of it is exercisable in shadow first (R-V4-1).

---

## 1. Rulings (R-V6-1 … R-V6-8)

**R-V6-1 — Genesis is evidence-gated, never taste-gated.** A charter may only enter the gauntlet from a scout `charter_proposal` artifact — which by construction requires the domain uncovered across ≥K distinct cycles (default 3) plus demand-evidence refs. The applier refuses hand-waved charters (no artifact → nothing to consume). The LLM may rank and REFUSE charters; it can never originate one without the deterministic evidence trail. This is the codified form of "as it sees fit, not for the sake of building."

**R-V6-2 — A charter is its own proposal kind.** `kind: "charter"` joins the taxonomy (was: mis-filed as `"engine"`). The applier stamps it; the propose prompt vocabulary includes it; adjudicate gains a kind-specific deterministic screen (W2). Kind-blind screens judge code; charters are org-structure decisions and get org-structure law.

**R-V6-3 — The genesis screen (deterministic, deny-only, LLM may only further de-escalate):**
(a) **Roster cap is a hard deny**: `active_nonscored_count() >= max_active_nonscored_lobes` (`config/metabolism_budget.yml:68`, IMMUTABLE) → deny unless a demotion/retire docket item is co-pending in the same cycle (swap, not sprawl).
(b) **Probation capacity, not a count** (REVISED per operator directive 2026-07-12: "if it has good ideas, it's allowed to implement — just not random stuff for the sake of creating"): there is NO per-cycle genesis cap. Any number of charters may pass in one cycle if EACH independently clears the evidence floor, this screen, and its own two-key grant — the adversary ranks and vetoes junk per candidate. The binding limit is capacity: a newborn lands in `probation`, and `max_probation_lobes` (existing anti-cascade key, 5) bounds how many unproven newborns may exist at once; grants earlier in the same cycle consume slots immediately. Free a slot by proving a newborn (matured contract) or demoting it (accountability clock, R-V6-6). The genesis board (`data/metabolism/genesis_board.json`, display-tier) records the ranked candidate queue and each candidate's screen/adjudication status so the operator sees exactly what the organism wants to build and why.
(c) **CHF-family deferral — NO auto-lift** (REVISED W2 2026-07-12): charter proposals token-matching the causal/CHF machine-registration AND structure-learner (NOTEARS/DAG-GNN/LoRAM/CMIN) family are **unconditionally denied**. DO_NOT_REBUILD §4 line ~111 says the 2026-10-15 clock is a PRECONDITION requiring ≥8 matured exit-(a)/(b) candidates + a fresh operator ruling — it is NOT an automatic lift trigger. The `adjudicate._genesis_screen` CHF check has no date gate; lifting requires an explicit operator-tap ruling that replaces this policy (operator: edit `_CHF_DENY_TOKENS` in `adjudicate.py` via a human-lane T2-tapped PR).
(d) **Tier fence (triple)**: `proposed_tier` must be `display` and `proposed_lifecycle_state` must be `proposed` — enforced at scout (hard constants), applier (tier-raise fence), and now the adjudicate screen. Promotion to confirmer/scored/authority stays T2 + gauntlet + operator, unconditionally (R-V2-3).
(e) **"Is it actually a lobe" law**: the adversary prompt for `kind=charter` carries NARR-NWC + NEXT3-U5 verbatim (waves, rails, and connective tissue are not lobes; misfiling waves as lobes is how program sprawl happens) — the adversary is instructed to veto misfiled non-lobes.

**R-V6-4 — Newborns are born with a working metabolism (generic fitness scaffold).** `engine/metabolism/generic_fitness.py` builds `data/metabolism/fitness/<lobe_id>.json` for every charter lobe with structured `fitness_sensors` (id+store) in `probation`/`active` that lacks a bespoke builder: per-sensor store freshness, row-accrual counts, and honest `accruing` status until each sensor's `maturity_date`; composite stays null until matured (nulls printed, never fabricated). Cards land where `organism_state._discover_fitness_cards()` already looks (filename-stem discovery — zero changes to the reader). A genesis charter that declares structured sensors therefore enters SENSE on its first nightly.

**R-V6-5 — One loop, many lobes.** The PROPOSE lane iterates loop-managed lobes (structured sensors + `lifecycle_state ∈ {probation, active}`), each as its own `--lobe` invocation with its own `cycle_id` suffix (`<cycle>-<lobe>`) and thus its own propose branch — riding the existing per-branch machinery unchanged (adjudicate/build/merge already iterate ALL pending propose branches since #2287). Today that set is exactly `{til}`, so behavior is identical until the first genesis lobe matures — the capability lands dormant, not disruptive. Per-lobe memory, strategic gap, and recall already thread (post-#2285).

**R-V6-6 — Accountability clock: born on probation, prove or demote.** A genesis lobe enters at `proposed → probation`. If it produces zero matured (graded) contracts within `genesis_accountability_days` (new budget key, default 45), the lifecycle machine emits a demotion docket — operator-visible, two-key, never silent. Honest nulls do NOT trip the clock (a graded null IS a matured contract — context-accrual law); only silence does.

**R-V6-7 — Shadow-first, as always.** The shadow harness gains a synthetic-uncovered-domain exercise: scout scan → charter proposal artifact → applier (dry) → injected proposal → adjudicate screens — end-to-end under `AUTONOMY_PAUSED`, real stores untouched. Genesis arming evidence, same as v4's first breath.

**R-V6-8 — Refusals.** No money-path/authority lobe is ever born via genesis (display-tier only, triple-fenced). No per-lobe workflows or crons (workflow count and render budget stay flat). No edits to the neural-web two-lobe program cap case law (NWC-U2/RUL-P1 are program-scope rulings; the operative genesis cap is the metabolism budget's `max_active_nonscored_lobes` — this masterplan RECORDS that scoping rather than editing ruling_graph.yml). No LLM-originated sensors, scores, or fitness values anywhere in the scaffold.

---

## 2. Waves

**W1 — Wake the feelers (ships with this doc).** Add the scout step to the scheduled SENSE stage (`metabolism-agenda.yml`, after the anomaly monitor, same degraded-continue pattern) and to the shadow harness SENSE stage. Smallest possible diff; from the first armed agenda run onward, uncovered domains begin accruing observations and (after K cycles) charter proposals — which the applier already consumes.

**W2 — Genesis gauntlet hardening.** `kind: "charter"` taxonomy (applier stamp + propose vocabulary + `_item_to_proposal` validation); the R-V6-3 deterministic screen in adjudicate; probation-capacity gate + `genesis_accountability_days` budget keys (IMMUTABLE file — human-lane PR, `max_genesis_per_cycle` RETIRED); adversary prompt case-law block for charters; tests incl. cap-deny, CHF-deferral-deny, swap-allow, probation-capacity.
W2 adversarial-review FIX-FIRST resolutions (reconcile commit, 2026-07-12):
- **B1 (BLOCKER fixed)**: `propose.build_docket` now carries charter fields (`proposed_tier`, `proposed_lifecycle_state`, `domain_id`, `evidence_refs`, `uncovered_for_cycles`, `roster_budget`) via `**charter_extras` spread so the genesis screen tier fence is not dead code on the real path.
- **M1 (MAJOR fixed)**: `_has_copending_demotion` replaced by `_count_valid_swaps` which requires the target lobe to be present in `lobe_charters.yml` as `active` with a counted tier; excludes the charter's own text; charter's own "demote" wording no longer waives the cap.
- **M2 (MAJOR fixed)**: roster-cap path now calls `lobe_registry.load()` and checks `roster["ok"]`; an unreadable/malformed roster explicitly denies (the silent `active_nonscored_count()→0` fail-open is no longer the only gate).
- **CHF tokens extended**: `_CHF_DENY_TOKENS` includes `notears`, `dag-gnn`, `loram`, `cmin`, `structure learner`, `causal dag` (DO_NOT_REBUILD §4 ~line 110).
- **ADV observability**: genesis screen reason surfaced in adversary governance findings when genesis is the sole blocker.

**W3 — Newborn metabolism.** `generic_fitness.py` + SENSE wiring (runs BEFORE organism_state so cards feed the same cycle); multi-lobe PROPOSE iteration (R-V6-5); accountability-clock sweep (R-V6-6) in the verify lane; shadow genesis exercise (R-V6-7); arming-checklist note.

Sequencing: W1 merges first (it touches the agenda workflow other waves build on); W2 and W3 build in parallel worktrees off W1's main.
