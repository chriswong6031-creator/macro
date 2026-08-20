# V4-D2B2-CN-HK FROZEN CONTRACT — China/HK canonical identity admission (2026-08-20)

Status: FROZEN — Sol (AI CEO) authority adjudication 2026-08-20, relayed through the
FABLE-00 China Alpha activation seat. Sol authorized **exactly one bounded child**:
`D2B2-CN-HK`, under `WS:PROPHET-US-V4-RECOVERY` wave V4-D2 / Data OS identity
authority. **This is NOT authorization for the full D2B2 US/Canada backlog** —
US and Canada expansion remain unauthorized; Sol reviews per child.

Origin: the China Alpha wave `pr0d` builder stopped at the D2B2 collision
escalation (its commission pointed at a mistaken `WS:STOCK-IDENTITY` /
`engine/stock_identity/` seam; canonical identity authority is the Data OS master
per the Sol 2026-08-18 Gate-1 amendment recorded on the V4 `d2` wave). Sol's
ruling: the China product outcome is still required, but the China lane is not
authorized to implement canonical identity expansion itself. China `pr0d` is
OWNER_ROUTED_WAIT / consumer-verifier on this child. Decision record:
`DEC:CHINA-IDENTITY-OWNER-ROUTE-D2B2-CN-HK`.

Parent authority chain: `research/prophet_v4/d2/D2A_FROZEN_CONTRACT_2026-08-18.md`
(gmi.identity_resolution/v1 seam), `D2B1_FROZEN_CONTRACT_2026-08-19.md` (issuer
law), `D2B1_R1_FROZEN_CONTRACT_2026-08-20.md` (supersession/pending-transition
fence), `research/MASTERMIND_SECURITY_MASTER_SPEC.md`. Text below the FROZEN line
changes only via an appended `## AMENDMENTS` section (D2A precedent).

---

## Mission (Sol's words, binding)

Admit the current source-supported China/HK listing population into the canonical
Data OS security/issuer/listing master, **or return a typed refusal for every
targeted object**, then re-derive the existing GMI identity projection so real
China/HK company nodes resolve through canonical Mastermind IDs.

## Frozen boundaries (Sol 2026-08-20, verbatim-faithful)

1. **Start pin census.** At the start pin, re-census `NOT_IN_MASTER` by market.
   Current main happens to report 1,868 total; **that is observation, not
   contract** — the child's target N is its own start-pin census.
2. **Scope = China/HK only**, objects supported by lawful primary sources. US and
   Canada expansion remain unauthorized.
3. **Canonical builder only.** Extend the existing canonical master through its
   canonical builder (`scripts/build_security_master.py` +
   `lib/dataos/identity.py` + the `data/reference/` master/aliases/receipts
   family). No hand-written master rows, no parallel China master, no alternate
   allocator or reader.
4. **D2B1 issuer law preserved.** Mastermind IDs remain canonical; USCC, LEI,
   ISIN, exchange identifiers and official listing keys are deterministic
   external evidence/aliases only — never canonical identity.
5. **Primary sources only**: exchanges, CNInfo/HKEX, GLEIF and lawful official
   registries. No Qichacha/Tianyancha/Wind API or purchased resolver (the CN-B
   #5947 NO-BUY stands).
6. **A/H dual listings** remain separate securities/listings, sharing an issuer
   only when deterministic evidence law supports it. No name/fuzzy/LLM grouping.
7. **Current-identity semantics only** unless a separately receipted historical
   source supports a dated boundary. Do not manufacture historical issuer
   lineage from current registrant evidence.
8. **Complete accounting.** Every target must finish `RESOLVED`, an existing
   typed exception, or a named typed refusal. No silent drop.
9. **GMI sidecar re-derived** from the merged canonical master; never resolve a
   sidecar conflict by choosing a stale file.
10. **Zero Earnings event-adapter work.** No `china_corporate_event.v1`; no
    `engine/company_intelligence/` edits.
11. **Zero score/rank/Prophet behavior change.**

## Acceptance tests / proof (Sol, binding)

- Frozen hostile fixtures: A/H dual listing, renamed security, SOE/subsidiary,
  unresolved issuer, alias-only vendor ID.
- US existing identity fixtures remain behaviorally unchanged.
- Complete accounting of the child target population:
  resolved + typed refusals/exceptions = target N.
- Before/after China and HK GMI resolution rates measured **separately**.
- Canonical Data OS tests + GMI identity-resolution/contracts green.
- No duplicate identity surface introduced.
- `python3 scripts/agentos.py validate` exits 0.

## Completion law

Merge of D2B2-CN-HK = **BUILT_NOT_PROVEN**. At that point China `pr0d` adopts the
owner result by reference and also becomes `BUILT_NOT_PROVEN`. Either flips to
`done` only after a **natural production nightly** demonstrates real China/HK
nodes flowing source → canonical master → GMI projection, with run ID and
measured resolution delta recorded in the owning workstream records. Prefer
immutable merge SHAs in durable receipts — never mutable branch-head SHAs.

---

## Builder commission (spawn contract — paste this file; SECTION labels below)

ROUTE: build

MISSION: Under `WS:PROPHET-US-V4-RECOVERY` wave V4-D2 child D2B2-CN-HK, admit the
current source-supported China/HK listing population into the canonical Data OS
security/issuer/listing master via its canonical builder, or return a typed
refusal for every targeted object; then re-derive the existing GMI identity
projection (gmi.identity_resolution/v1, D2A seam) so real China/HK company nodes
resolve through canonical Mastermind IDs.

WHY: ~75% of GMI China company nodes are unresolved/NOT_IN_MASTER; the China
Alpha program (wave `pr0d`, consumer-verifier) and GMI both key on canonical
identity. Sol authorized exactly this one bounded child on 2026-08-20; the China
lane itself is NOT authorized to implement identity expansion.

SCOPE: Everything in "Frozen boundaries" and "Acceptance tests" above — they are
the contract. Start by pinning main and re-censusing `NOT_IN_MASTER` by market;
your target N is that census's China/HK slice. Read the D2A/D2B1/D2B1-R1 frozen
contracts and `research/MASTERMIND_SECURITY_MASTER_SPEC.md` before touching the
builder; the D2B1-R1 pending-transition fence and supersession axis are live law.

OUT OF SCOPE: US/Canada expansion; any second identity plane or hand-written
master rows; vendor resolver APIs or purchases; `engine/company_intelligence/`
edits or any event surface; `china_corporate_event.v1`; score/rank/Prophet
behavior; committing `data/` bytes from a sparse session worktree (opt into the
full tree via `python3 scripts/worktree_sparse.py full` where the builder's
outputs genuinely require it, and never `git add` an unexpected `data/` diff).

FROZEN SPEC: this file above the commission block; on any conflict between this
commission and the canonical builder's actual seam, STOP and return the conflict
— do not improvise.

OWNED FILES: `scripts/build_security_master.py`, `lib/dataos/` extension seams,
`data/reference/` datasets ONLY through the canonical builder, the GMI
identity-resolution projection re-derivation path (D2A seam), new/extended tests
and fixtures. Nothing under `engine/company_intelligence/`.

TESTS: the "Acceptance tests / proof" list above, implemented as real pytest
suites wired into CI owner lanes (unwired new suites red `contract-delta` —
name the suites in `.github/ci/legacy-jobs.yml` owner jobs in the same PR).

NOT DONE UNLESS: every acceptance test green with receipts in the PR body;
complete accounting reported (resolved + typed refusals/exceptions = N, by
market); before/after CN and HK GMI resolution rates reported separately; zero
`engine/company_intelligence/` edits; `python3 scripts/agentos.py validate`
exit 0; ship loop owned to merged (commit → push → PR → CI → same-day
squash-merge); V4 WS `d2` wave note updated with the child's merge SHA and
BUILT_NOT_PROVEN state in the same PR.

RETURN: STATUS / RESULT (census N by market; resolved/refused accounting; CN and
HK resolution-rate deltas; seams touched) / EVIDENCE (test output, PR number,
merge SHA) / GAPS / DEVIATIONS.
