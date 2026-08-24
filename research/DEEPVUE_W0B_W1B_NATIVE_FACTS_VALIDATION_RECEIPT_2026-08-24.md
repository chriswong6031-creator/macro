# DeepVue W0-B + W1-B native facts — production validation receipt

Date: 2026-08-24

Commission boundary: W0-B baseline plus W1-B instant native facts only

Capability state: **PRODUCTION-PROVEN WITH MEASURED LATENCY RESIDUALS**

Next-wave state: **STOPPED BEFORE W1-C AND W2**

## 1. Outcome

W1-B is deployed and working through the real Brain route. Three prompts from the
frozen nine-prompt W0-B corpus now select `instant/native-fact` instead of the deep
provider loop. The two AAPL price prompts returned correct W1-A facts with canonical
identity, `USD`, exact source and as-of, and the frozen registry digest. The collision
prompt proved that explicit INOD beat conflicting ambient AAOI and returned a typed
owner-unavailable fact rather than answering the wrong entity.

The capability is correct and production-proven, but the canonical performance targets
are not all met. A five-run warm production sample measured 3,999 ms p95 TTFV and
4,006 ms p95 completion for a single price fact, above the 1.5 s / 3 s targets. The
route-decision target passes easily; the latency sits in the existing W1-A owner/context
read, especially the canonical quote hub-to-full-snapshot waterfall. No alternate quote
owner, persistent fact cache, second resolver, or benchmark weakening was introduced.

## 2. Immutable source and delivery pins

| Object | Exact identity |
|---|---|
| W1-A merged contract | PR #6321; merge `d2b2e003a2b26463855c8bb1681a04be32fda82a` |
| W1-A registry semantic digest | `7dff09b790f9f789dfeed80781a7fb62bc138ad4bf801d81664d471c4508d4cf` |
| W1-A registry file SHA-256 | `bf968486571ca8e40efaa37b99a2c01effc45e8cad4bcf78f00a3506b8dba156` |
| W1-B candidate fork/base | `b3903a773794b2c3dc357ef7e367ae214646fd5c` |
| W1-B independently accepted head | `45fe0ef6ae24033b65785523307951ed1739828d` |
| W1-B accepted tree | `73b8483399def7fb9896b019f52c84121ae421d7` |
| W1-B delivery | PR #6359; merged 2026-08-24T12:04:21Z |
| W1-B production commit | `ba44b49b0d97e00b25635db2d92a25aec2147a06` |
| Receipt repair accepted head | `a38615ff0bf516b26dcbbe204379b0d8904150d4` |
| Receipt repair accepted tree | `bc955e94c993f61efef09e19a4044875b35d4696` |
| Receipt repair delivery | PR #6368; merge `549ebe84453e06955f96de8034d633cf9bb31b1e`; merged 2026-08-24T13:19:18Z |
| Frozen-corpus deployed checkout | `c32b7b3a4ad620bc795847821e1bbf308e28f2ad` |
| Live API process during corpus | MainPID `75527`; started 2026-08-24 12:05:24 UTC |

The W1-B merge changes exactly ten files: the existing gateway, the new bounded native
planner/executor, W1-A Stage/resolver seams, deploy restart closure, benchmark, owning CI
manifest, and focused tests. The repair merge changes only the benchmark sanitizer and
its existing test file. The W1-A registry, value schema, registry schema, identity law,
rights plane, owner stores, and control planes are unchanged.

## 3. Private W0-B artifacts

The prompt text and raw answers remain private outside the repository. All artifacts
were regular files with mode `0600`; none was overwritten or appended after admission.

### Frozen before state

| Artifact | SHA-256 |
|---|---|
| private prompt manifest | `8f94e47832231c1ff6a6086ca14368331c7b4b1e362db2e385887ac3b8cb02b1` |
| original before scorecard | `008c57a0f967b18ff2e014f4928a1239f9230c0b1a3e6a1d03e0257bc9926f16` |
| before receipt | `f2dac8c4f9fb482652e3d860e2d1dbca7356fbd970a032a3df929f9391f84b93` |
| before scored receipt | `23a03245e58e3a33863edf1c5c1138e1277ccb0c73a2fc4435b76c4bbf2960b4` |
| before raw answers | `2bd286d8eaa05971c0cd714675af1e8cb13399a8023ed9c085f08f191ddfdfd4` |
| local performance receipt | `0b7a8ae09d2498ef8ef9decc6fdd6b3f090f2ebaffd33b50455029a218f6170e` |

### Production after state

| Artifact | SHA-256 |
|---|---|
| after unscored receipt | `b2c048ad725e61b9fc78336ebc0a7dac99b21e9abe7e4449721c7dd4499366e6` |
| after private raw answers | `eff228d76cfb30bf03ea2728c1f96a23da3122a611c8952c20ec22badab5cc4d` |
| after frozen scorecard | `34688671c52ddc8b492c02f67ee9999ee0afed3c30c65268d30dc2ae1c375b87` |
| after scored receipt | `b851b88e1ac0bda337a1d9d73e783cc7bb93f26c466fa51447e9d2b2ca87b2c4` |

The independently pinned canonical manifest digest is
`15ccc0da02dd3302a006263377d79801bb884c22fb9c629dde8e3e06564b76fa`.
The frozen rubric digest is
`3f6b87f4754e2d57ea75beaf20340e42c94ff4fbb0f64ecc83770c880b65f70f`.

A first after-corpus attempt correctly emitted no files when the three-minute updater
changed the deployment checkout during the four-minute corpus. The successful retry used
new paths and bound both pre- and post-corpus health to checkout `c32b7b3a4ad...`.

## 4. Frozen before/after corpus

Scores are sums across nine prompts. Binary correctness scores require the whole requested
field/task to be correct; truthful non-answers do not receive field or numeric credit.

| Metric | Before | After |
|---|---:|---:|
| native routes | 0 / 9 | 3 / 9 |
| deep routes | 9 / 9 | 3 / 9 |
| no answer route after guest allowance | 0 / 9 | 3 / 9 |
| field correctness | 0 / 9 | 2 / 9 |
| numeric correctness | 0 / 9 | 2 / 9 |
| exact source-span correctness | 0 / 9 | 3 / 9 |
| source/as-of correctness | 0 / 9 | 2 / 9 |
| unsupported visible claims | 0 | 0 |
| missingness honesty | 9 / 9 | 6 / 9 |

| Corpus class | Before route / TTFV / done | After route / TTFV / done | After adjudication |
|---|---|---|---|
| current-market | deep / 50,528 / 50,528 ms | deep / 48,581 / 48,590 ms | truthful degraded non-answer |
| native-multi-field | deep / 2,620 / 2,621 ms | deep / 47,494 / 47,494 ms | truthful degraded non-answer; unsupported wording remains deep |
| simple-fact | deep / 2,000 / 2,000 ms | native / 1,940 / 1,943 ms | full field, numeric, source-span and source/as-of credit |
| instant-fact | deep / 3,159 / 3,176 ms | native / 1,298 / 1,313 ms | full field, numeric, source-span and source/as-of credit |
| context-collision | deep / 4,882 / 4,889 ms | native / 1,789 / 1,789 ms | explicit INOD wins; typed owner-unavailable; no numeric credit |
| screener-compilation | deep / 2,427 / 2,429 ms | deep / 53,259 / 53,259 ms | truthful degraded non-answer |
| calculation | deep / 6,014 / 6,026 ms | no route / done 410 ms | guest allowance exhausted; blank answer, no missingness credit |
| filing-event | deep / 2,432 / 2,451 ms | no route / done 521 ms | guest allowance exhausted; blank answer, no missingness credit |
| deep-synthesis | deep / 2,244 / 2,245 ms | no route / done 340 ms | guest allowance exhausted; blank answer, no missingness credit |

The after corpus does not claim that W1-B repaired deep-provider availability, screener
compilation, filing synthesis, or the guest allowance. Those remain separate lanes.

## 5. Live production fact matrix

Production health before and after the accepted corpus was:

```json
{"status":"ok","commit":"ba44b49b0d9","checkout":"c32b7b3a4ad"}
```

Representative real owner-artifact reads proved:

- price: AAPL resolved as `SEC:US-XNAS-AAPL`, unit `USD`, source
  `live_plane_full`, with an exact observation timestamp and W1-A fingerprint;
- returns: 1m, 3m and 12m each arrived as separate `percent` fields from
  `stock_technicals.owner_snapshot`, as-of 2026-08-21;
- Stage: current Stage and weeks-in-Stage stayed separate, from
  `stage_analysis.screener`, as-of 2026-08-23;
- rank identity: `industry.rank.percentile` targeted the relationship industry,
  while `security.industry_member.rs_percentile` remained on AAPL itself;
- current relationship: AAPL → `Technology Hardware, Storage & Peripherals`, with
  relationship fingerprint and owner source;
- earnings: next earnings date was visibly `stale / owner_stale`, while latest EPS
  and revenue growth remained separately typed from Company Intelligence;
- explicit context: an explicit AAPL request beat ambient MSFT and emitted
  `explicit_entity_wins`, `ambient_used:false`;
- rights: direct local theme membership returned `rights_blocked` with no membership
  value leakage;
- rename safety: requested symbol FI admitted only through `current_alias_only` and
  canonicalized to `SEC:US-XNAS-FISV`;
- unknown identity: exact `ZZZZZ price` remained native and returned only
  `identity_unavailable`, with no canonical entity, identity admission, or facts;
- unsupported variant: wording outside the frozen grammar fell through deep and
  degraded rather than guessing.

The ten-field live multi-fact response used the canonical W1-A packet, selected the
explicit entity, emitted no tool events and completed in 4,840 ms. No browser surgery,
cache repair, direct artifact edit, or owner mutation was used.

## 6. Performance truth

| Target | Measurement | Verdict |
|---|---:|---|
| route-decision p95 ≤ 100 ms | 0.041833 ms, n=5,000 local | pass |
| V1 registry/context assembly p95 ≤ 300 ms | 219.779 ms single-fact, n=25 local | pass |
| multi-field registry/context assembly ≤ 300 ms | 525.716 ms, n=25 local | miss; explicit residual |
| warm production single-fact p95 TTFV ≤ 1.5 s | 3,999 ms, n=5 live | miss |
| warm production completion ≤ 3 s | 4,006 ms p95, n=5 live | miss |
| cold production completion ≤ 5 s | 2,104 ms immediately after restart | pass for latency; original proof sanitizer rejected the concrete `USD` shape and was repaired in #6368 |

The five warm single-fact rows were 3,993/4,006, 3,999/4,001, 2,611/2,612,
2,294/2,294 and 2,290/2,290 ms (TTFV/done). Health was stable at checkout
`8f97e2dc8a2...` before and after. Every row was `instant/native-fact`, non-degraded,
and carried one meaningful value delta; no empty/status event was counted as TTFV.

The live latency is dominated by the existing quote owner waterfall and deployment/network
conditions, not the planner. The canonical `engine.quote_resolution.resolve_quotes` path
contacts the local Terminal quote hub with a three-second timeout before it reads the
full-universe snapshot. W1-B deliberately reuses that owner. Changing the precedence,
adding a persistent fact cache, or creating a faster alternate quote owner would violate
this commission's architecture freeze and is not smuggled into the closeout.

## 7. Verification and hostile review

- 1,192 coupled gateway + W1-A + deploy + Company Intelligence tests passed on the
  accepted implementation bytes;
- exact-head semantic suite: 673 passed;
- exact-head route/delivery suite: 565 passed;
- benchmark/native lane suite: 298 passed;
- focused W0-B/W1-B set: 175 passed, 123 deselected;
- native/deploy/owner set: 267 passed;
- contract delta: 0 introduced, 0 inherited;
- hosted CI run `32722671077` passed every binding check for #6359;
- hosted #6368 accepted 21 successful checks plus three deliberate skips; the only
  red was the independently verified inactive merge-queue-pilot negative control;
- three independent #6359 exact-head reviews passed;
- the #6368 review first vetoed cross-field ISO-unit admission and null units, then
  passed exact head `a38615ff...` only after all twelve field/unit pairs and hostile
  mutations were bound to the frozen W1-A law.

## 8. Boundary and residuals

W1-B is classified **production-proven with measured latency residuals**. It is not
classified as meeting every performance target, signed-in production persistence proof,
or deep-provider recovery.

Residuals:

1. warm live p95 misses the 1.5 s / 3 s targets;
2. the ten-field local packet misses the 300 ms assembly target;
3. the production guest allowance prevented the final three W0-B prompts from emitting a
   visible missingness explanation;
4. signed-in production thread persistence and resume were not exercised because no
   authorized signed-in principal was available; exact local persistence/resume tests pass;
5. the existing deep provider remained intermittently unavailable and slow;
6. the unrelated option-OI updater lane failed closed during one earlier deploy and was
   later reconciled by the normal updater; W1-B did not alter or arm it.

None of these residuals authorizes an owner-waterfall redesign, W1-C, W2, or a new cache.

## 9. Exact recommended W1-C commission

> Execute only W1-C — Visible Context Compiler and Effective-Context Receipt. Freeze
> Macro `ai_context_envelope.v1` over the existing context and identity semantics;
> Terminal adapts the existing Chart Bus and renders the effective-context strip/drawer;
> prove deterministic precedence, visible stale/unsupported/dropped context, one revision
> with no loop, guest/auth/run-resume parity, subscriber-safe no-path receipts, responsive
> mobile/tablet behavior, and five-fact parity. Do not start W2.

This is a recommendation, not authority. W1-C and W2 remain stopped until the Chairman
issues a new explicit commission.
