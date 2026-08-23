# BioCatalyst P1-1 production acceptance — 2026-08-22

## Verdict

**P1-1 PRODUCTION ACCEPTANCE: FAIL**

The merged Catalyst Radar implementation is naturally deployed, byte-preserved,
authenticated, entitled, populated from the current public generation, safe at
the API/public-evidence boundary, and functional in the real 390 px EN/ZH
journey. It is **not production accepted** because the real desktop EN and ZH
views violate the explicit no-clipping gate: the fixed-height Radar queue lets
every `.bci-radar-card` flex item shrink to about 96 px while its live title,
metadata chips, and date block require 116-150 px. Those descendants extend
outside their row boxes and visibly collide with the following row.

P1-1 therefore remains `in_progress`. `PROVEN_LIVE_COHORT_LIMITED` is **not**
claimed. The broader parity ledger remains `PARTIAL`. This record changes no
runtime/product asset, performs no deployment, and starts no P1-2 work.

## Authority and scope

- Workstream: `WS:BIOCATALYST-CORE-PRODUCT`, wave P1-1 only.
- Implementation merge: `a7e09a974eac26a3cdf5f85491962b19013e122e`.
- Sol-approved source head: `35988aa7e8f859a291da35dbfbe8369133d22952`.
- Proof was read-only against the natural production process. No updater,
  restart, redeploy, runtime mutation, source/cadence/cohort change, or
  production fixture was used.
- Open PR #6139 remained ignored as superseded/unmerged.

## Fresh source and process identity

| Evidence | Exact result |
|---|---|
| fresh `origin/main` at the browser/process proof cut | `0bcfef045517bcaae23271b1218f37c59bcaa864` |
| final records branch base after non-overlap fast-forwards | `fa73271632a7cf5eb214e4e68bdfcb96c22422b0` |
| `/api/health.commit` | `e92238244f0` = `e92238244f0a28ad642bca803de762ed63a18c37` |
| `/api/health.checkout` | `de66109a7ac` = `de66109a7aca4ef41324b54dda14041ccef05941` |
| VPS `/opt/macro` checkout | `de66109a7aca4ef41324b54dda14041ccef05941` |
| `macro-api` | active, MainPID `1659274` |
| process start | `2026-08-22 22:06:09 UTC` |
| final health probe | HTTP 200 in `0.960156 s` |

Full local history proved this ancestry chain:

`a7e09a974eac26a3cdf5f85491962b19013e122e` ->
`e92238244f0a28ad642bca803de762ed63a18c37` ->
`de66109a7aca4ef41324b54dda14041ccef05941` ->
`0bcfef045517bcaae23271b1218f37c59bcaa864`.

At the proof cut, `git log a7e09a9..0bcfef0 -- <all 21 #6191 paths>`
returned no post-merge touch. While this record was being authored, main
advanced and the records branch fast-forwarded without conflict to
`facbaa29c5467ce55bd3a18816fb7731ad4f245c`, then to the final records base
`fa73271632a7cf5eb214e4e68bdfcb96c22422b0`. The first later movement touched the
administrative `.github/ci/legacy-jobs.yml` among #6191 paths, but none of the
P1-1 runtime/product/browser paths or the three records in this PR. The final
`facbaa2..fa7327` movement touched none of #6191's paths and none of the three
records in this PR.
`git diff --name-only a7e09a9 e922382 -- <all non-CI #6191 paths>` remained
empty. The process under test therefore contains #6191 and its P1-1
runtime/product/browser bytes remain the accepted merge bytes.

The normal updater had already converged before this proof. No manual
`macro-update`, `systemctl restart`, or synthetic deployment was run.

## Current public generation

| Field | Production value |
|---|---|
| generation | `ctgov_run_20260822T220030672261Z_e679bb3d2518` |
| schema | `1.6.0` |
| last success / published | `2026-08-22T22:00:31.310115Z` |
| source dataset timestamp | `2026-08-21T09:00:05` |
| coverage class | `current_only` |
| configured / observed cohort | `4 / 4` |

The generation was read through the production checkout and production
interpreter from the current pointer-bound public cut. It was not copied,
rewritten, or substituted.

## Authentication and live HTTP contract

The existing operator Google Chrome session was used through the production
`MDXAuth.client().then(client => client.auth.getSession())` shape. The session
value remained inside the page. Only `hasSession=true`, status, timings,
headers, and `site_full=true` were returned. No token, cookie, email, name, user
id, or other credential was printed, persisted, screenshotted, or committed.

| Probe | Result |
|---|---|
| signed-out default Radar | HTTP **401** in `1.049154 s`; `private, no-store`; `Vary: Authorization`; `missing bearer token` |
| authenticated `/api/me` | HTTP **200** in `0.981 s`; `site_full=true` |
| entitled default Radar | HTTP **200** in `5.002 s` |
| entitled invalid horizon | HTTP **400** in `0.191 s`; `detail=invalid horizon` |

The default Radar response carried `Cache-Control: private, no-store`, `Vary:
Authorization, Accept-Encoding`, `X-Content-Type-Options: nosniff`, and
`X-Robots-Tag: noindex, noarchive`. The authenticated 400 retained the private
fence and `Vary: Authorization`.

The default request was exactly `horizon=next_365d`,
`milestone_kind=all`, `limit=50`. Its response was:

- 4 returned milestone rows, no next cursor;
- 3 `upcoming`, 1 `occurred`, 0 `current`;
- 4 events beyond horizon, 8 total source milestone events;
- 4 trials in cohort, 4 trials with events;
- 0 absent dates, 0 unusable dates, 0 trials missing identity;
- represented NCTs: `NCT06602479`, `NCT05020236`;
- revision states: 2 `has_revisions`, 2 `history_not_collected`;
- 6 total public revision-lineage entries.

This `5.002 s` Radar read is inside the prior P0 live range of approximately
`4.5-7.9 s`; no new latency SLO is invented and no material regression is
claimed. Uvicorn access lines on PID `1659274` recorded `/api/me` 200, default
Radar 200, invalid horizon 400, natural page Radar 200, and real NCT detail 200.
There was no 5xx in the proof window and no browser/API 524.

The pre-claim tab initially displayed a temporary-unavailable state. One normal
page reload, after the authenticated browser connection was established,
performed a natural page boot and returned the populated Radar 200. It remained
stable for the EN/ZH desktop/mobile journey. No data was injected into the page.

## Live safety walk

The actual authenticated Radar response was recursively inspected. Results:

| Boundary | Violations |
|---|---:|
| score/probability/materiality/rank/composite/confidence/weight keys | 0 |
| private receipt/object-key/source-pointer/manifest/generation/query keys | 0 |
| filesystem-like values | 0 |
| R2-like object-key values | 0 |
| bare 40-64 character hashes | 0 |

The authority block remained `classification=source_fact`,
`decision_authority=false`; forbidden uses still include originating a signal,
ranking/selecting a security, sizing a position, gating a decision, executing a
trade, and raising authority.

The visible EN and ZH page/inspector contained no machine state names, private
receipt language, source pointers, hashes, object keys, or generation ids. It
did not call a registry completion date a readout date or catalyst date.

## Real Chrome journey

Drive: authenticated standard Google Chrome against
`https://www.mastermind-x.com/biocatalyst.html`. Page-origin console warnings
and errors were empty after the natural reload. Two earlier warnings came from
unrelated Chrome extensions, not the MastermindX page, and are not product
errors.

### Desktop EN — **FAIL**

- Browser-reported viewport: `2055 x 1270`.
- Page-level horizontal overflow: none.
- Populated arithmetic and labels were correct: 3 upcoming, 1 reached, 4 beyond
  horizon, current cohort 4/4.
- All four `.bci-radar-card` elements had `clientHeight=94`, while their
  `scrollHeight` values were `[150, 120, 116, 116]`.
- Titles, phase/issuer metadata, and date/days-to-milestone blocks extended
  below the card rectangle. Two long titles also line-clamped as designed, but
  the acceptance blocker is the entire row-content overflow, not the deliberate
  title ellipsis.
- Populated screenshot SHA-256:
  `3a2e95ecd77d665295fd1d42aa0e198ae703ac1c4102780668e2704b0eb87226`.
- Open-inspector screenshot SHA-256:
  `a6114ab20f315eca0eda255466a3f8eef5da57f7261145f854799120d3b6bb67`.

The screenshot visibly shows the first row's title/meta/date content colliding
with the second row. This fails the commissioned no-chip-clipping/no-collision
gate even though the individual chip elements do not truncate their own text.

### Desktop ZH — **FAIL**

- `data-lang=zh`; document language `zh-CN`.
- Row arithmetic, reached grouping, evidence copy, and lineage labels localized
  correctly.
- Page-level horizontal overflow: none.
- The same four row boxes remained `clientHeight=94`; `scrollHeight` values
  were `[120, 120, 116, 116]`.
- Phase/issuer chips and date blocks again extended outside every row; the two
  longest titles retained their deliberate two-line clamp.
- Screenshot SHA-256:
  `66d5798ceb42cd41033989d4f1bebcd79bc21676c8e147c0fdc5698291dc2b30`.

### Exact 390 px mobile EN — pass for the measured mobile gate

Chrome was at 90% browser zoom, so the viewport override was calibrated until
the page reported exactly `innerWidth=390`, `innerHeight=844`; the device pixel
ratio was `0.9`. Document/body widths were `377/378`, so no page-level
horizontal overflow existed.

- All four row containers had `scrollHeight == clientHeight` and no tracked
  title/chip/date descendant escaped its row.
- Row heights were `[267, 238, 234, 262]`.
- Only the designed two-line title clamp reported internal text overflow; every
  id, milestone, status, revision, phase, issuer, date, and timing chip/label
  fit.
- Screenshot SHA-256:
  `16a9b45820d2965d08350c841f87fc894b94eeb98ca016a3c2c49dd0265d46c8`.

### Exact 390 px mobile ZH — pass for the measured mobile gate

- `data-lang=zh`; document language `zh-CN`.
- No page-level horizontal overflow.
- All four row containers had `scrollHeight == clientHeight`; no tracked
  descendant escaped its row and no chip clipped.
- Row heights were `[238, 238, 204, 204]`.
- Screenshot SHA-256:
  `5f49b818760bd52f6f986114bd72d473863f6d1c94e6e141346f58ae906885c3`.

### Real evidence inspector and revision lineage

The live `NCT06602479` primary-completion row was opened, not a synthetic row.
The inspector showed the real current trial record, source clocks, and
`https://clinicaltrials.gov/study/NCT06602479`. The public source resolved HTTP
200 in `0.666399 s`.

The production row carried three revisions and rendered all three, newest
recorded change first:

1. `2025-09-15 -> 2026-12-18`, record version `9 -> 10`, observed
   `2026-08-22T02:24:05.756562Z`;
2. `2026-09-07 -> 2025-09-15`, record version `6 -> 7`, observed
   `2026-08-22T02:24:05.006169Z`;
3. `2026-09-02 -> 2026-09-07`, record version `1 -> 2`, observed
   `2026-08-22T02:24:03.752731Z`.

At exactly 390 px the inspector was an `aria-modal=true` dialog, had no pane or
body horizontal overflow, and all three lineage cards had
`clientWidth=scrollWidth=344`. Evidence-inspector screenshot SHA-256:
`8920013ac8510159a19f143e842b78c226a51bcedb11fd722bff6c676ca69b15`.
Full-lineage screenshot SHA-256:
`abcd98a7cec688389b0fdcc44528871bea97220ca9555678dc556b84b5f2bb72`.

The Chrome tab was restored to desktop English with the inspector closed and
the temporary viewport override reset.

## Production blocker and falsifier

**Blocker:** real desktop Radar cards are shrinkable flex children inside the
fixed-height scroll queue. The base `.bci-trial` declares only
`min-height: 96px`; `.bci-radar-card` adds `align-items: stretch` but no
Radar-only `flex-shrink` protection. With the current live content, flex sizing
holds every row near the minimum instead of its natural content height. Mobile
escapes because its queue becomes height-auto/overflow-visible.

This is an evidence-backed cause hypothesis, not an authorized implementation
change. The smallest repair for Sol to authorize and test is a Radar-only
desktop flex-sizing correction (the likely candidate is preventing
`.bci-radar-card` from shrinking), with the paired
`templates/biocatalyst.css` / `site/biocatalyst.css` asset and focused browser
regression coverage. It must not re-architect the queue or P1-1.

**Repair falsifier:** against the same kind of real populated desktop EN and ZH
journey, every Radar row must satisfy `scrollHeight <= clientHeight`, every
tracked title/meta/date descendant rectangle must remain within the row
rectangle, adjacent rows must not collide, and page/chip horizontal overflow
must remain absent. The exact 390 px EN/ZH results and full inspector lineage
must remain clean. If a Radar-only no-shrink rule does not achieve those facts,
the hypothesis is false and the repair must stop for renewed diagnosis.

## State and non-claims

- P1-1 status remains `in_progress`.
- Production acceptance is **FAIL**, not partial PASS.
- `PROVEN_LIVE_COHORT_LIMITED` is not claimed.
- Broader BioCatalyst parity remains `PARTIAL`.
- No runtime/product/browser asset was changed in this proof wave.
- No manual deploy, restart, updater run, or synthetic production data occurred.
- No cohort expansion, CT.gov source/cadence, source-soak, closed-beta,
  ownership, authority, scoring, alerting, persistence, or regulatory/PDUFA
  scope changed.
- No P1-2 work began.
- The controlled pre-merge Chromium fixture remains test evidence only and was
  not used as production acceptance.

The next authority action is Sol review of this records-only failure receipt.
Do not implement the bounded CSS repair, merge the records PR, claim live
acceptance, or start P1-2 until Sol explicitly authorizes the next step.
