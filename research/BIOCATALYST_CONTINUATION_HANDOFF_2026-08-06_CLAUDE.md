# BioCatalyst remaining waves — continuation handoff, 2026-08-06 (Claude/Fable session)

| Field | Value |
|---|---|
| Predecessor | `research/BIOCATALYST_REMAINING_BUILD_WAVES_HANDOFF_FOR_CLAUDE_2026-08-06.md` (Codex) — still the canonical wave map |
| This session | Executed Wave 0 in full, Wave 2 (D0b premium product), Wave 7-A/B, plus the unscheduled verifier lane the D0a ruling exposed |
| Audited base | `origin/main` `b70deb5cf817c5ed32d6de2f07bfaa82717c51d8` |
| Production | `https://www.mastermind-x.com` — `/biocatalyst.html` 200 / 61,226 B; `/api/health` checkout `cbee4e0e7ff`; anonymous `/api/biocatalyst/v1/trials` → 401, `private, no-store`, `Vary: Authorization` |

## 1. What shipped this session

| Lane | PR | State |
|---|---|---|
| D0a named design adjudication + parity ledger | #4796 | armed `merge-on-green` |
| W0-C+E F0-delta reconciliation + closed-beta source manifest | #4810 | armed |
| W0-D BC-O1a inert operational persistence + M0a policy | #4814 | armed |
| W0-A B1S2a private bounded fixed-cohort transport (dark) | #4820 | armed |
| W7-A/B N0a operating packet producer + N0b allowlisted reader | #4822 | armed |
| W0-B2 v2 acceptance contract + trusted browser verifier | #4825 | open, **deliberately NOT armed** — see §2 |
| W2/D0b premium trial product (Screen+facets, Peer Matrix, Change Tape, primitives) | branch `claude/bio-d0b-premium-trial-product` | pushed; PR pending |

### Integration evidence (run by the commissioning session, on an idle-ish machine)

The four backend lanes were merged into one scratch branch and the full suite run once:

```
pytest tests/ -k "biocatalyst or clinicaltrials" -q -p no:randomly
1 failed, 1024 passed, 57100 deselected in 629.86s
```

Baseline on the lanes' bases was **844** (measured independently by two lanes; the
commissioning session measured 850 on a slightly different commit — not a contradiction).
**1024 passed = 844 + 180 new tests, with zero cross-lane regressions.**

The single failure is
`tests/test_biocatalyst_deploy.py::test_biocatalyst_ci_uses_bounded_complete_lanes_with_no_unowned_test_file`
and it is an **artifact of how the integration branch was built**, not a defect in any lane:
the `legacy-jobs.yml` conflict was resolved by taking `origin/main`'s copy, which stripped every
lane's test registration and left the new suites unowned. On their own branches each lane carries
its registration and that test passes (B1S2a reports it at 44 passed). Do not "fix" it.

Cross-lane conflict surface: **exactly one file**, `.github/ci/legacy-jobs.yml`. Everything else
merged clean.

Per-lane regression, self-reported and consistent: B1S2a 844 → **907** (63 new, 0 failed);
N0 844 → **881** (37 new, 0 failed).

## 2. THE MERGE CHAIN IS SERIAL — this is not optional

`tests/test_biocatalyst_deploy.py::test_biocatalyst_ci_uses_bounded_complete_lanes_with_no_unowned_test_file`
forces every new `test_biocatalyst_*.py` to be registered in `.github/ci/legacy-jobs.yml`
**before it can merge**. So every bio lane is compelled to edit the same few lines, and all
bio PRs conflict with each other there. Local integration proved that block is the **only**
cross-lane conflict — everything else merges clean and the lanes compose.

**Procedure:** merge one → rebase the next onto main → let its checks re-run → repeat.
Do NOT expect a parallel sweep. The sweeper labels the losers `merge-blocked` on conflict,
which is correct; the label stays armed, so a rebase-and-push heals it on the next sweep.

**#4796 is the exception and must go first** — it touches no CI file, and the v2 contract
binds the ruling by sha256. Until #4796 is on main, the v2 lane correctly emits
`product_acceptance_v2.design_adjudication_pending_base`. Heal = merge #4796 then rebase.
Never weaken the binding or vendor a copy of the ruling.

## 3. The finding that changes the wave map

`tests/test_biocatalyst_d0a_design_contract.py:245-300` proves that even a fully materialized
repo with every field forged still fails on `product_acceptance.trusted_browser_verifier_unavailable`.
**No self-authored artifact can ever clear it.** Named design approval was necessary and is now
recorded (#4796) — it is NOT sufficient. The verifier was an unscheduled prerequisite and is
now built (`scripts/biocatalyst_browser_verifier.py`, 22 tests, degrades to
`verifier_unavailable` and never to a pass).

**Still open:** the browser matrix has not been CAPTURED. `config/biocatalyst_product_acceptance_v2.yml`
honestly says `state: draft_awaiting_browser_capture`, `capture_state: not_run`. The next
session's first D0b task is to RUN the verifier against the merged page and bind the receipt.

## 4. Verification posture

- Backend lanes (B1S2a / O1a / F0-delta / N0 / v2) are DARK by design. `git diff origin/main -- app/`
  is EMPTY for all four — the live proof is that **no new route appears** and the anonymous 401 +
  `private, no-store` + `Vary: Authorization` boundary is unchanged.
- **D0b splits its delivery path:** `templates/biocatalyst.{css,js}` ARE byte-identical plain-copy
  pairs with `site/` → live in ~3 min via the VPS pull, NO render needed. `site/biocatalyst.html`
  comes from the `.j2` → needs a covering render. Verify assets first, markup only after a
  covering render concludes. BioCatalyst is NOT on the Caddyfile `immutable` list, so the
  forfeited `?v=` re-stamp costs nothing.

## 5. Known-open items

- **D0b defect (EN only):** `1 trials do not record this field.` — pluralization. ZH twin
  `1 项试验未记录此字段。` is correct.
- **Pre-existing main red, NOT ours:** `tests/test_house_law_registry.py` 5 failed —
  `check_ci_trigger_closure.py` on disk but unregistered in `config/house_law_checks.yml`
  (landed #4649). Owned by open PR #4787.
- **CI saturation at hand-off:** 104 queued workflow runs; self-hosted runners share a host at
  load 82. Merges are slow. Do not re-run or cancel to "unblock".

## 6. What CANNOT be completed by any session (state this honestly, do not re-plan it)

- **W1-B `B1S2c`** — operator arming decision + **14 continuous days** of soak. A calendar, not a task.
- **W3 `BC-I1a/I1b`** — no owning plane publishes an executable versioned PIT identity contract.
  Measured: 2 of 6 shared-plane adapters eligible; the 4 blocked carry exact blocker strings.
- **W4-D/E `C2`/`MKT0`** — Capital Structure PIT + licensed market/options; #4740/#4746 unmerged,
  and `EST1` needs a vendor contract that does not exist.
- **W8-D `BC-P3a/P3b`** — deliberately unscheduled; needs matured forward evidence + a fresh
  operator ruling. First possible authority is shrink-only.

## 7. Parity denominator

`research/BIOCATALYST_PARITY_LEDGER_2026-08-06.md` (#4796) scores the 32-row benchmark matrix:
**6 of 32 rows satisfy §17 today.** Eleven of the thirteen BLOCK rows reduce to ONE missing
shape — an executable, versioned, PIT read contract from a plane BioCatalyst does not own.
Five more are a rights decision, not engineering. **The fastest route to parity is one owning
plane publishing one PIT contract**, each unblocking two to four rows.

## 8. Next session's first three actions

1. Merge #4796. Then rebase + merge the code PRs serially (§2).
2. Push and open PRs for `claude/bio-d0b-premium-trial-product` and
   `claude/bio-d0a-successor-and-verifier`; fix the EN pluralization defect in the same push.
3. Run `scripts/biocatalyst_browser_verifier.py` against the merged D0b page, bind the receipt
   into the v2 manifest, and move it off `draft_awaiting_browser_capture`.
