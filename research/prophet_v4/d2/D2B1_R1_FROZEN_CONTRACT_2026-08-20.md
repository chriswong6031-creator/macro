# V4-D2B1-R1 FROZEN CONTRACT — VMRK duplicate-mint supersession + pending-transition fence (2026-08-20)

Parent: `research/prophet_v4/d2/D2B1_FROZEN_CONTRACT_2026-08-19.md` (all D2B1 laws remain
binding except where this contract explicitly amends them). Authority: Sol amendment
2026-08-20 to WS:PROPHET-US-V4-RECOVERY — "FIRST prove/falsify SEC:US-XNYS-VMRK in the
committed master. If proven, R1 must perform an explicit correction/supersession — not
deletion — onto the continuing EQR identity, establish correct dated/current aliases from
canonical evidence, and ship the general pending-transition fence."

Frozen by the orchestrating session (Fable) after the prove/falsify probe, an Opus
root-cause investigation, and a primary-source evidence hunt. The builder executes this
contract; it does not redesign it. A guard rejection or an impossibility discovered
mid-build comes back to the orchestrator — never a silent improvisation.

## §0 Adjudicated verdict (the prove/falsify step — COMPLETE)

**PROVEN.** At `origin/main` (nightly commit `b6e0062ca889`, generated 2026-08-20T01:30:18):
`SEC:US-XNYS-VMRK` exists as a fresh mint (`effective_at` 2026-08-20, `NO_ISSUER_EVIDENCE`,
null issuer) while `SEC:US-XNYS-EQR` remains (RESOLVED, CIK 0000906107, evidence pinned
2026-08-18). One economic security, two master rows. Receipt `coverage.unresolved_names`
swapped VMRK→EQR. Root cause: the mint join in `mint_master_rows`
(`scripts/build_security_master.py:1020-1028`) keys on **listing key only**; a rename
produces a new listing key and therefore a new security_id unconditionally, and no
EQR→VMRK signal existed anywhere in-repo (`rename_events`, `undated_renames`, aliases,
config maps all silent). EQR's simultaneous disappearance was fully computable in the mint
frame (`set(by_listing_key) - {re-derived keys}` = {US-XNYS-EQR, US-XNYS-AVB,
US-XNYS-CTRA, US-XNYS-TPH}) — the builder simply never evaluates it.

## §1 Ratified evidence (the ONLY identity evidence this repair may cite)

**E1 — the rename.** SEC EDGAR, CIK 0000906107, Form 8-K filed 2026-08-17 (accession
0001140361-26-033377), Item 5.03: corporate name changed from Equity Residential to
Vivmark Residential effective 2026-08-17; NYSE ticker changed from EQR to **VMRK effective
2026-08-18** (open of trading). Corroborated by live EDGAR submissions
(`data.sec.gov/submissions/CIK0000906107.json`: name VIVMARK RESIDENTIAL, ticker VMRK,
formerNames chain unbroken under one CIK) and `www.sec.gov/files/company_tickers.json`
(CIK 906107 → VMRK). Falsification attempted and failed (spin-off / unrelated new listing
/ different registrant all refuted: same CIK, same Commission File Number 1-12252,
surviving Maryland trust).

**E2 — the AVB exit.** Same 8-K family (second 8-K accession 0001193125-26-354068, filed
2026-08-17, already receipted in-repo at
`data/special_situations/classify_cache/0001193125-26-354068.json`): AvalonBay
Communities Inc. was **extinguished** — merged into Canopy Merger Sub LLC (a Company
subsidiary), then into ERP Operating Limited Partnership; closing 2026-08-17. NYSE AVB
ended. **VMRK continues EQR only. VMRK does NOT continue AVB.** Never alias, rename, or
join AVB to VMRK on any axis.

**E3 — the reassignment trap (binding forbidden-join).** SEC's live
`company_tickers.json` now maps the bare string "EQR" to **CIK 931182 — ERP OPERATING LTD
PARTNERSHIP**, a different registrant. Any post-2026-08-17 evidence join keyed on the
string "EQR" is forbidden; the continuing row's evidence join key must be its CURRENT
symbol (VMRK) via the rename chain. Test-pinned as H3.

**E4 — freshness honesty.** The committed CIK rail (2026-08-18) carries no VMRK row; the
committed prong "fresh CIK map maps VMRK to EQR's registrant CIK" is NOT yet satisfiable
from repo artifacts and self-heals on the next weekly capture. The repair's receipts cite
E1 verbatim — never a hand-restamped map, never a hand-created snapshot (parent §10 law).

## §2 Repair A — the dated RenameEvent (EQR→VMRK)

1. Add to `RENAME_EVENTS` in `scripts/build_security_master.py` (the builder's only
   authored data, per its own docstring law): `old=EQR, new=VMRK, on=2026-08-18`, evidence
   string quoting E1 (accession + Item 5.03 + both effective dates). Never a timeless
   alias; `UNDATED_RENAMES` must NOT gain an entry.
2. Wire the mechanical counterparts the MMC→MRSH / SATS→ECHO precedents require so that
   `unmodelled_renames()` stays empty and the build exits green: `config.yml`
   `breadth.ticker_fixups` and/or `quality.ticker_key_migrations` and/or
   `lib/ticker_aliases.py` fetch aliases — **exactly those the existing precedents use for
   a store that actually carries EQR keys, verified per store, receipted in the PR body.**
   Do not invent new map kinds; do not touch stores that carry no EQR key.
3. Post-event derivations that MUST hold (test-pinned): `_current_symbol('EQR') == 'VMRK'`;
   `_inception_code('VMRK', ...) == 'EQR'`; a VMRK directory row resolves to listing key
   `US-XNYS-EQR` and therefore to the existing `SEC:US-XNYS-EQR` — **no mint**. The
   membership-sourced seed EQR and the constituents-sourced seed VMRK resolve to the SAME
   listing key and must yield ONE master row (dedup explicitly test-pinned, H2).

## §3 Repair B — supersession of `SEC:US-XNYS-VMRK` (correction, never deletion)

1. **New security-axis columns** on `security_master` (nullable, era-seamed exactly like
   `ISSUER_AXIS_COLUMNS` so pre-era parquets still read): `security_state` (closed enum;
   the only non-null value this era: `SUPERSEDED_DUPLICATE_MINT`; null = active) and
   `superseded_by` (nullable security_id). `config/dataset_registry.yml` schema updated in
   the same PR; `config/identity_seams.yml` updated if the seam census requires it.
2. **The tombstone.** `SEC:US-XNYS-VMRK` gets `security_state=SUPERSEDED_DUPLICATE_MINT`,
   `superseded_by=SEC:US-XNYS-EQR`. Every other field of that row is byte-frozen as
   committed (issuer columns stay `NO_ISSUER_EVIDENCE` / null — that was and remains
   true). The row is NEVER deleted: 705 rows before, 705 after (H9).
3. **Exclusions.** A superseded row is excluded from: issuer re-examination (the
   `_REOPENABLE` pending selection), issuer aggregation and `issuer_master` membership,
   and every consumer join index (§6). A future CIK map carrying VMRK→0000906107 must
   neither resolve the tombstone nor trip the multi-member allowlist gate into
   EVIDENCE_CONFLICT (H4 — this is the dated escalation the repair pre-empts).
4. **Re-mint refusal.** A resolution rendering listing key `US-XNYS-VMRK` (hitting the
   tombstone) is a typed refusal disclosed in the receipt — never a silent re-mint and
   never a silent resurrection (H8). Reuse of a superseded listing key requires a future
   ratified identity-break record, per the GOLD precedent.
5. **New dataset `data/reference/security_migrations.parquet`** — columns
   `security_id, superseded_by, reason, evidence, migrated_at`; this era writes exactly
   one row: (`SEC:US-XNYS-VMRK`, `SEC:US-XNYS-EQR`,
   `security_supersession_duplicate_mint_v1`, E1 string, build timestamp). Registry entry
   (EVENT temporal profile, grain over all identity columns), append-only dedup merge
   mirroring `_merge_issuer_migrations`. This is the durable old→new mapping Sol's
   conditions require.
6. **Reader.** `lib/dataos/identity.py`: `SecurityIssuerRow` (or a sibling surface on
   `IssuerMaster`) exposes `security_state`/`superseded_by` so consumers can filter;
   superseded rows are excluded from `securities_of_issuer` aggregation by default.
   `security_id()` / `parse_id()` grammar unchanged.
7. **Vendor aliases preserved** (Sol condition): the EQR alias family is retained; the
   VMRK alias rows regenerated by the canonical builder must converge to one coherent
   family for the continuing security. No alias row hand-deleted.

## §4 Repair C — AVB typed exit (separate class; never part of the rename)

Add AVB to `config/delisted_symbols.yml` via the existing CTRA/TPH machinery, evidence =
E2 (both 8-K accessions, closing 2026-08-17, extinguished-by-merger), effective date per
that ledger's existing semantics (receipted in the PR body). Result: the AVB master row is
RETAINED with its issuer history (RESOLVED / 0000915912 — historically true); the AVB seed
resolves through the exit ledger and leaves `coverage.unresolved_names`. FORBIDDEN: any
alias/rename/join AVB→VMRK (H5); any edit to `data/baskets/membership.json`.

## §5 Repair D — the general pending-transition fence

1. **Predicate (computed every build, in the mint stage):** `lost` = committed master rows
   that are active (`security_state` null), whose current symbol is NOT exit-ledgered, and
   whose listing key is re-derived by NO resolution in this build.
2. **Fence:** for each would-be NEW mint (listing-key miss), if `lost` is non-empty AND
   the candidate lacks independent registrant evidence (current CIK map carries the
   candidate's symbol with a CIK distinct from every `lost` row's `issuer_cik`), the mint
   is REFUSED: no row is created; the receipt's new `pending_transition_refusals` block
   records {symbol, listing_key, lost rows, snapshot date, reason}; a `::warning` is
   emitted (bare `print`, line-start, `flush=True` — CI-guarded house law). Independent
   CIK evidence, or an empty `lost` set, lets the mint proceed (H7: IPOs are not
   collateral damage). Rename-event-covered symbols never reach the fence (they resolve to
   existing rows).
3. **Refusals are re-examined every build** and clear naturally when evidence arrives (a
   ratified RenameEvent, or independent CIK) or the `lost` set empties. Fence proposals
   are DETECTOR OUTPUT — parent-contract law: name-similarity may propose, only curation
   ratifies. The fence itself must not consult `security_name` similarity to auto-join.
4. **Standing instrument:** the receipt gains a `listing_continuity` census (the `lost`
   set, by name). After this repair it must be EMPTY (EQR heals via the rename chain; AVB
   via the exit ledger; CTRA/TPH already exit-ledgered) — and a non-empty census on any
   future nightly is a visible `::warning`, so a killed or missing signal can never again
   be silent for a week.

## §6 Consumers (same-PR migration, parent §8 law)

1. **Sidecar** (`engine/theme_graph/identity_resolution.py` + re-derived
   `data/theme_graph/identity_resolution.parquet` + `_meta.json`): every join index
   excludes superseded master rows. Post-repair assertions: `co:us:EQR` still resolves
   RESOLVED → `SEC:US-XNYS-EQR` / `ISS:US-XNYS-EQR`; `co:us:AVB` still resolves RESOLVED →
   `SEC:US-XNYS-AVB`; NO `co:us:VMRK` node is created (graph node minting is the theme
   graph's own lane, forbidden here); no sidecar cell may reference `SEC:US-XNYS-VMRK`.
2. **Guard** (`scripts/check_theme_graph_contracts.py`): new clause — a sidecar
   `security_id` referencing a master row with non-null `security_state` is a violation;
   selftest fixture extended to prove the clause fires.
3. Re-derive over the CURRENT merged nodes plane at PR time (the parent's merge-resolution
   law: re-derivation, never pick-a-side, on any conflict with the nightly engine lane).

## §7 Hostile cases (all test-pinned; extend EXISTING suites only — no new test files)

- **H1** Race replay without the RenameEvent (fixture): snapshot flip EQR→VMRK → fence
  REFUSES the VMRK mint, receipt discloses, no new security_id.
- **H2** With the RenameEvent: VMRK resolves to `SEC:US-XNYS-EQR`; membership seed EQR +
  constituents seed VMRK → ONE row; no mint.
- **H3** Hostile future map `EQR→0000931182` (live-real, per E3): the EQR row is
  untouched — its evidence join key is VMRK; 931182 must never bind to `ISS:US-XNYS-EQR`.
- **H4** Hostile future map `VMRK→0000906107`: tombstone stays unexamined and unresolved;
  no allowlist trip; no EVIDENCE_CONFLICT on the EQR row.
- **H5** AVB: exit-typed only; any AVB→VMRK join path asserted absent.
- **H6** Idempotency: re-running the canonical builder on the repaired artifacts is
  byte-stable with `generated_at` preserved (parent no-op law).
- **H7** A new symbol with its own independent CIK mints normally even while `lost` is
  non-empty.
- **H8** A seed rendering `US-XNYS-VMRK` post-supersession → typed refusal, no
  resurrection.
- **H9** 705 rows in, 705 rows out; the tombstone differs from its committed bytes ONLY in
  the two new columns; zero other rows change any value.

## §8 Regeneration + expected post-state (canonical builder ONLY — no hand-written rows)

Run the canonical builder against real committed inputs (fresh `origin/main` data; the
worktree is sparse by default — opt in with `python3 scripts/worktree_sparse.py full`
BEFORE regenerating, and never `git add -A` an unexpected `data/` diff). Expected:

- `security_master.parquet`: 705 rows = 704 active + 1 superseded; active issuer states
  {RESOLVED 699, NO_ISSUER_EVIDENCE 4, DEFERRED_IDENTITY_EXCEPTION 1}; receipt reports
  states split by `security_state`.
- `security_migrations.parquet`: exactly 1 row. `issuer_migrations.parquet`: 3 rows,
  untouched. `issuer_master.parquet`: 701 rows, untouched.
- Receipt: `coverage.unresolved_names` = ['ANGPY','B','BLD','CBOE','EA','GATO','IMPUY',
  'MAG','RHHBY'] (9 — EQR and AVB leave); `rename_events` gains the E1-cited EQR→VMRK
  entry; `pending_transition_refusals` = []; `listing_continuity` = [].
- Sidecar re-derived; the four assertions of §6.1 hold.
- **Survival proof (post-merge, NOT this session's gate):** the next natural nightly must
  re-derive one canonical identity — no new mint, no tombstone resurrection, receipt
  byte-consistent modulo genuine input advance. This lands after merge; the wave reports
  it as pending, exactly like the parent's §10 discipline.

## §9 Mutation controls (each must DIE — demonstrated, not asserted)

1. Remove the RenameEvent → H1/H2 red (fence refusal visible, or duplicate detected).
2. Break the fence predicate (always-empty `lost`) → H1 red.
3. Break the independence check (fence ignores CIK) → H7 red.
4. Drop the tombstone exclusion from issuer re-examination → H4 red.
5. Drop the `security_migrations` write → registry/receipt test red.
6. Drop the registry schema for the new columns → registry test red.
7. Drop the guard clause → guard selftest red.
8. Delete the tombstone row → H9 red.
9. Re-point the AVB exit to a rename → H5 red.
10. Hand-edit `generated_at` / restamp manifests → idempotency/no-op test red.

## §10 File scope

ALLOWED: `scripts/build_security_master.py`; `lib/dataos/identity.py`;
`lib/ticker_aliases.py` (only if §2.2 requires); `config.yml` (rename/fixup maps only);
`config/delisted_symbols.yml` (AVB only); `config/dataset_registry.yml`;
`config/identity_seams.yml` (if seam census requires); `data/reference/*`;
`engine/theme_graph/identity_resolution.py`; `data/theme_graph/identity_resolution.parquet`
+ `_meta.json`; `scripts/check_theme_graph_contracts.py`;
`contracts/theme_graph/identity_resolution.v1.schema.json` (description only, if needed);
the EXISTING test suites (`tests/test_dataos_identity.py`,
`tests/test_dataos_security_master.py`, `tests/test_dataos_registry.py`,
`tests/test_theme_graph_identity_resolution.py`, `tests/test_theme_graph_contracts.py`);
this contract file; an AMENDMENTS pointer in the parent contract; the AgentOS handoff + WS
row (orchestrator writes those).

FORBIDDEN: Prophet rank/admission/Fusion/Radar/B5A; ThemeState; GMI node ids, node
minting, memberships, edges; `data/baskets/membership.json`; Stock Identity; qledger;
price/breadth stores; the snapshot/CIK collectors and their manifests (NEVER restamp);
`.github/workflows/*`; any D2B2 expansion (the 1,868 NOT_IN_MASTER queue is untouched);
new test files; new timers/schedulers/control planes.

## AMENDMENTS

### AMENDMENT §1 (2026-08-20, post-review adjudication — binding for the fix pass)

The Opus adversarial review returned FAIL (B1 + M1-M6 + m1-m4 + n1-n3). Orchestrator
rulings, superseding the base text where they conflict:

1. **B1 (fence crash).** A refused mint (pending-transition or resurrection) must leave
   `build()` fully functional: refused resolutions are excluded from EVERY downstream
   stage (alias derivation included), the receipt blocks land, and the artifacts write.
   §7 gains **H10**: an end-to-end `build()` run through BOTH refusal classes on a
   fixture — receipt discloses, `::warning` emitted, no exception, artifacts complete.
   Mutation control 2 is re-scoped to this end-to-end surface.
2. **M2 (null-CIK fail-open).** §5.2's independence clause is amended: a mint proceeds
   only if the candidate's symbol has a CIK in the current map AND every fence-scoped
   lost row carries a NON-NULL `issuer_cik` differing from it. A null anywhere makes
   independence unprovable → refuse. (Fail-closed; the incident's own row class was
   null-CIK.)
3. **M1 (lost-set scope).** §5.1 is amended: the FENCE-scoped lost set excludes only
   rows whose inception code is a REGISTERED identity exception (GOLD/B class — those
   identities are already quarantined fail-closed at their own layer, and their
   permanently-null CIKs would otherwise jam all future minting under ruling 2). The
   `listing_continuity` census NEVER silently drops them: exception losses appear as
   typed entries `{code, explained: "identity_exception"}`. §8's expectation is
   corrected: post-repair `listing_continuity` = exactly one explained GOLD entry, not
   `[]`. The `rename_new_symbols` exclusion is REMOVED — superseded rows are excluded
   via `security_state`, with evaluation ordered after supersession. **Documented
   accepted residual:** a rename of an exception-quarantined listing (e.g. GOLD→GLDC)
   can mint a new id without a fence refusal; this cannot corrupt a clean identity
   (the quarantined row is not the newcomer's identity) and the adjacent explained
   census line keeps it visible. Test-pinned in both directions.
4. **M3 (supersession gate).** §3 is amended: supersession is executed ONLY from an
   authored `SECURITY_SUPERSESSIONS` registry in the builder (same evidence-string law
   as `RENAME_EVENTS`), each entry naming the exact superseded listing key, canonical
   security_id, evidence, and date. This era's registry: exactly
   (`US-XNYS-VMRK` → `SEC:US-XNYS-EQR`, E1). RenameEvents NEVER auto-tombstone; a
   rename-implied duplicate that is not in the registry is a receipt disclosure, not an
   execution. The same-venue invariant the docstring claims is enforced structurally
   (exact listing-key match). The reviewer's cross-MIC scenario must yield no
   supersession and a disclosure. Test-pinned.
5. **M4 (dead collision note).** The dedup/collision discriminator is the CURRENT
   symbol: two resolutions rendering one listing key dedup lawfully iff their seeds'
   `_current_symbol` values are identical (the H2 shape); differing current symbols =
   genuine reuse collision → the receipt note (restoring `run_nightly_refresh`'s
   collision arm). Both directions test-pinned.
6. **M5 (alias pruning).** Committed alias rows may be deleted ONLY when they point at
   a superseded security_id, and every deletion is receipted in a new
   `vendor_alias_prunes` block plus a `::warning`. A fresh row overlapping a committed
   row that points at an ACTIVE id is a fail-closed build error, never a silent
   replacement. Append-only semantics otherwise unchanged.
7. **M6 (store receipt).** `config.yml` gains `breadth.ticker_fixups: {VMRK: EQR}`
   (the MMC→MRSH precedent: store stays keyed at the inception code; consistent with
   `YAHOO_FETCH_ALIASES["EQR"]="VMRK"` under `unmodelled_renames()`). The
   `data/stocks/EQR.parquet` + `data/stocks/VMRK.parquet` double store is OUT OF SCOPE
   to edit (§10 forbids price stores) but must be named in the PR body and the handoff
   as an owed breadth-lane retirement. The per-store receipt is corrected to include
   `data/stocks`.
8. **m1/m2 (pinning).** §6.1's four sidecar assertions get a test in
   `tests/test_theme_graph_identity_resolution.py`; the §6.2 guard clause gets a
   fixture test in `tests/test_theme_graph_contracts.py`.
9. **m3 (store alias).** The `store` vendor space keeps a dated answer for `VMRK`
   pointing at the continuing id, per the same derivation rules as the yahoo family.
10. **m4/n1/n2 (artifact provenance).** The final artifact regeneration runs AFTER the
    last code commit and is committed separately, so the receipt's `code_version`
    names a commit whose code produces the artifacts. The sidecar is re-derived once
    on that final code (single final epoch appended). If `issuer_master.parquet` /
    `issuer_migrations.parquet` regenerate content-identical, their original committed
    bytes are restored to keep the diff content-true.
11. **n3.** The parent-contract AMENDMENTS pointer is owned by the orchestrator, in
    this PR.

## §11 Builder return

STATUS / RESULT / EVIDENCE / GAPS / DEVIATIONS packet; PR opened but NOT self-merged (the
orchestrator reviews, an Opus reviewer attacks, the orchestrator merges). Every §7 case
green with named tests; every §9 control demonstrated dying; targeted suites + guard
strict + selftest green; PR body carries the §2.2 store-by-store receipt and the §8
post-state numbers.

### AMENDMENT §2 (2026-08-20) — ruling 9 deferred on a genuine rulings conflict

Executing ruling 9 (dated `store`-space VMRK alias) requires closing the pre-existing
committed open row `(store, EQR, SEC:US-XNYS-EQR, None, None)`, which ruling 6's strict
fail-closed prune rule forbids (overlap with a committed row pointing at an ACTIVE id).
The builder correctly reverted rather than redesign either ruling. Orchestrator ruling:
**M5 stays strict this era; ruling 9 is DEFERRED.** The principled completion — a
same-id-refinement carve-out (a fresh dated family that points at the SAME active
security_id and fully covers the committed open row's mapping is a lawful refinement,
matching the reviewer's own lawful/unlawful classification of the pass-1 closures) —
is the named follow-up design, to be implemented with its own review alongside the owed
breadth-lane retirement of `data/stocks/VMRK.parquet`. Until then the `store` space has
no VMRK answer (absence is strictly better than the wrong-id answer it replaced), and
any future dated rename will fail closed at the prune conflict with a visible
`::warning` until that carve-out lands — accepted, disclosed behavior.

### AMENDMENT §3 (2026-08-20) — re-verification regression ruling

Re-verification found all original findings FIXED and one NEW MAJOR introduced by the
fix pass: `VendorAliasPruneConflict(SystemExit)` escapes `run_nightly_refresh`'s
`except Exception`, breaking the seam's "always returns 0" invariant, skipping
`_restore_artifacts`, and emitting no annotation on the exact path AMENDMENT §2
promises will fire on every future dated rename. Ruling: the class re-bases on
`Exception`, and `run_nightly_refresh` catches it EXPLICITLY before the generic
handler — dedicated `::warning` naming the conflicting alias rows and that curation is
required, last-good artifacts restored, return 0. The CLI path stays fail-closed
(uncaught → non-zero). Test-pinned on the nightly seam (conflict → rc 0 + dedicated
warning + artifacts restored). Ruling-10 completion: the sidecar diff must add exactly
ONE epoch over origin/main (re-derive once over main's committed parquet with the final
code; the two pass-1 intermediate epochs never belonged on main); the two content-equal
issuer parquets restore their base bytes.
