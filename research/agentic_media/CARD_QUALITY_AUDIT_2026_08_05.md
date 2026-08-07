# Marketing card + post quality audit — 2026-08-05

Commissioned after three live @mastermindx001 posts (Aug 4-5) each shipped a
RADAR/BREAKING card that restated the tweet, truncated mid-clause on a static
PNG, and printed the source's brand.

**Method.** 14 agents, six independent defect lenses over the real code and the
shipped artifacts, every finding adversarially refuted by a second reviewer
before it counted. 40 findings raised, **35 confirmed, 5 refuted**.

## Confirmed defects

| # | severity | defect | site |
|---|---|---|---|
| 1 | BLOCKER | card_earns_attachment has NO code path that can veto a card whose BODY restates the post — the post-vs-summary check is an attach-branch, not a veto | `engine/marketing/breaking_summary.py:972` |
| 2 | BLOCKER | The summary branch returns True without ever asking whether the CARD HEADLINE restates the post | `engine/marketing/breaking_summary.py:974` |
| 3 | BLOCKER | The citation decision that says 'no credit' is applied to the post body only; the card's source chip is built from the raw source_name and never sees it | `engine/marketing/breaking_summary.py:1093` |
| 4 | CRITICAL | The card chip prints the publication name BY DESIGN; the only suppressor is a 6-word generic denylist | `/Users/chriswong/Documents/Cluade/Macro Dashboard/.claude/worktrees/publish-runner/engine/marketing/chart_render.py:4818` |
| 5 | CRITICAL | The only gate that screens card metadata matches '@handle' shapes; a bare brand word is invisible to it | `/Users/chriswong/Documents/Cluade/Macro Dashboard/.claude/worktrees/publish-runner/engine/marketing/copywriter.py:1315` |
| 6 | CRITICAL | The card names a source the post-text lane already ruled must NOT be named — source_authority is never consulted by the card builder | `/Users/chriswong/Documents/Cluade/Macro Dashboard/.claude/worktrees/publish-runner/engine/marketing/breaking_summary.py:1093` |
| 7 | CRITICAL | Card body is rendered at a FIXED 41px with a hard 3-line cap against a 320-char producer budget — ellipsis is mathematically guaranteed, not incidental | `/Users/chriswong/Documents/Cluade/Macro Dashboard/.claude/worktrees/publish-runner/engine/marketing/chart_render.py:5284` |
| 8 | CRITICAL | card_earns_attachment is approval-only — the summary branch returns True before the headline-vs-post check can ever veto | `engine/marketing/breaking_summary.py:972` |
| 9 | CRITICAL | The post-text restatement gate's own remedy manufactures the card defect — short_form makes the card hero identical to the post | `engine/marketing/press_lane.py:2406` |
| 10 | CRITICAL | card_earns_attachment can only ever veto on the headline; the card-body branch is attach-only, so a card whose visible body restates the post cannot be dropped | `/Users/chriswong/Documents/Cluade/Macro Dashboard/.claude/worktrees/publish-runner/engine/marketing/breaking_summary.py:972` |
| 11 | CRITICAL | The value gate accepts any attached media as both 'hard proof' and 'informational surplus' without inspecting it — a card that restates the tweet is what makes the tweet shippable | `/Users/chriswong/Documents/Cluade/Macro Dashboard/.claude/worktrees/publish-runner/engine/marketing/value_gate.py:381` |
| 12 | BLOCKER | No configured length budget matches the card's measured body capacity — every summary written to its configured budget is ellipsised (L4 by construction) | `config/press_sources.yml:817` |
| 13 | MAJOR | The card summary is ellipsis-clipped and the overflow flag is discarded; the headline has ladder protection against exactly this and the summary has none | `engine/marketing/chart_render.py:5306` |
| 14 | MAJOR | Earnings-call lane renders a card whose headline is a literal prefix of the post text, with no restatement gate anywhere in the lane | `engine/marketing/earnings_call_lane.py:407` |
| 15 | MAJOR | The gate's own test suite pins the bypass as correct behaviour | `tests/test_marketing_card_earns_pixels.py:260` |
| 16 | HIGH | De-handling is lane-scoped: the RSS and Alpaca lanes never call display_source_name, and one of them actively prettifies the brand | `/Users/chriswong/Documents/Cluade/Macro Dashboard/.claude/worktrees/publish-runner/engine/marketing/breaking_feed.py:155` |
| 17 | HIGH | The guard suite pins the branded chip as correct behavior — a compliant fix fails CI | `/Users/chriswong/Documents/Cluade/Macro Dashboard/.claude/worktrees/publish-runner/tests/test_marketing_card_earns_pixels.py:647` |
| 18 | HIGH | _bc_wrap_w's `overflowed` return — the only signal that the card truncated — is discarded at the summary call site, so no gate, alarm, or provenance field can see the clip | `/Users/chriswong/Documents/Cluade/Macro Dashboard/.claude/worktrees/publish-runner/engine/marketing/chart_render.py:5306` |
| 19 | MAJOR | The documented W4g invariant 'the hero is never truncated with an ellipsis, at any length' is false whenever the ticker strip is present | `/Users/chriswong/Documents/Cluade/Macro Dashboard/.claude/worktrees/publish-runner/engine/marketing/chart_render.py:5074` |
| 20 | MAJOR | The no-clip guard test exercises only the single best-case configuration, so it cannot see either live truncation | `/Users/chriswong/Documents/Cluade/Macro Dashboard/.claude/worktrees/publish-runner/tests/test_marketing_card_earns_pixels.py:609` |
| 21 | HIGH | The card's own overflow signal is discarded — every truncated body ships silently while provenance.card_fit reports zero characters dropped | `engine/marketing/chart_render.py:5306` |
| 22 | HIGH | _BREAK_SUMMARY_MAX_CHARS is a dead constant — the only written bound on card body capacity is never read | `engine/marketing/chart_render.py:4531` |
| 23 | MAJOR | earnings_call_lane renders a breaking card with NO value gate and no text-only path — but the lane has no production caller | `engine/marketing/earnings_call_lane.py:407` |
| 24 | HIGH | The cashtag branch disarms the whole card-value gate for ticker posts — and every earnings-call post is a ticker post by construction | `engine/marketing/breaking_summary.py:965` |
| 25 | HIGH | _BC_GENERIC_SOURCE_NAMES cannot fire on any real outlet — the de-handling gate is a 6-entry placeholder denylist policing a population of publication names | `engine/marketing/chart_render.py:4774` |
| 26 | MAJOR | The card gate scores `headline` while the card draws `card_headline` — it can be handed a string that is not on the card | `engine/marketing/press_lane.py:2526` |
| 27 | MAJOR | The RADAR breaking card carries nothing the tweet does not — every drawn element is either already in the post text or is brand chrome | `/Users/chriswong/Documents/Cluade/Macro Dashboard/.claude/worktrees/publish-runner/engine/marketing/chart_render.py:5301` |
| 28 | MAJOR | The gate scores the full card_summary, but the card draws at most 3 lines and hard-clips with an ellipsis — the 'adds detail' justification is computed on words the reader never sees | `/Users/chriswong/Documents/Cluade/Macro Dashboard/.claude/worktrees/publish-runner/engine/marketing/chart_render.py:5304` |
| 29 | MAJOR | The cashtag short-circuit returns attach=True before any content check, and the card it green-lights need not carry a single price | `/Users/chriswong/Documents/Cluade/Macro Dashboard/.claude/worktrees/publish-runner/engine/marketing/breaking_summary.py:965` |
| 30 | MAJOR | No test can observe the card-body branch saying no — every card_earns_attachment assertion with a summary asserts attach=True | `/Users/chriswong/Documents/Cluade/Macro Dashboard/.claude/worktrees/publish-runner/tests/test_marketing_card_earns_pixels.py:261` |
| 31 | MAJOR | wire.voice.llm_tier_salience_floor: 80.0 can never bind — the "sonnet flagship" tier is dead config and silently overrides breaking.llm.model_key | `config/press_sources.yml:805` |
| 32 | MAJOR | breaking.salience_threshold: 60 is a dead key — nothing reads the flag it computes, yet two config files document it as an admission gate | `config/marketing.yml:2390` |
| 33 | MEDIUM | The publisher's last gate screens post TEXT only — a queued card with a brand chip cannot be caught at dispatch | `/Users/chriswong/Documents/Cluade/Macro Dashboard/.claude/worktrees/publish-runner/scripts/marketing_publisher.py:2382` |
| 34 | MINOR | earnings_call_lane truncates its summary twice, and the first cut appends a fabricated full stop that deletes the qualification while reading as a finished sentence | `/Users/chriswong/Documents/Cluade/Macro Dashboard/.claude/worktrees/publish-runner/engine/marketing/earnings_call_lane.py:414` |
| 35 | MINOR | earnings_call_lane attaches a breaking card unconditionally, with no earns-pixels gate, and makes the card mandatory — its card headline is byte-identical to the post's first line | `/Users/chriswong/Documents/Cluade/Macro Dashboard/.claude/worktrees/publish-runner/engine/marketing/earnings_call_lane.py:292` |

## Failure scenarios

### 1. card_earns_attachment has NO code path that can veto a card whose BODY restates the post — the post-vs-summary check is an attach-branch, not a veto
`engine/marketing/breaking_summary.py:972` — **BLOCKER**

Input: post text = the composed tweet; card_summary = a sentence 100% contained in that tweet; card headline distinct (rs 0.625). Code: :972 outer test passes, :973 inner test fails, falls through to :988-990 and returns True. Reader sees a PNG whose body block is the tweet's own opening sentence, ellipsised mid-clause.

*Fix:* Make the summary leg a veto rather than an escape hatch: compute rs(post,summary) and rs(post,headline) first and attach only when no element the card DRAWS is at/above threshold — an AND over rendered elements, not an OR over the ones that happen to differ.

### 2. The summary branch returns True without ever asking whether the CARD HEADLINE restates the post
`engine/marketing/breaking_summary.py:974` — **BLOCKER**

Input: post text == item['headline'] (rs = 1.000, the worst possible) plus any card_summary that differs from the headline by >=30%. Code: :972 passes, :973 passes (0.636 < 0.70), :974 returns True. Reader sees a card whose hero text is the tweet reproduced word for word at poster scale.

*Fix:* Guard the early return: require rs(post, headline) < _RESTATE_THRESHOLD as a precondition on the summary leg, or suppress the hero from the card when it restates the post and let the summary stand alone.

### 3. The citation decision that says 'no credit' is applied to the post body only; the card's source chip is built from the raw source_name and never sees it
`engine/marketing/breaking_summary.py:1093` — **BLOCKER**

Input: a wire item whose citation decision is tier='unnamed' (or 'corroborated') with attribution=''. Code: press_lane.py:2294 correctly omits the credit from the post body, while breaking_summary.py:1093 hands the raw source_name to the renderer, which composes the chip at chart_render.py:4818. Reader sees a tweet with no attribution and an attached PNG stamped 'ZeroHedge · WIRE SERVICE' — the engine's own 'do not name this source' decision overruled by a path that never asked.

*Fix:* Thread the resolved citation tier into build_breaking_payload and pass source_name='' when the tier is 'unnamed'/'corroborated'; the chip already degrades to the tier word alone, and the tier is still carried by the chip's weight/fill/rail so nothing launders up.

### 4. The card chip prints the publication name BY DESIGN; the only suppressor is a 6-word generic denylist
`/Users/chriswong/Documents/Cluade/Macro Dashboard/.claude/worktrees/publish-runner/engine/marketing/chart_render.py:4818` — **CRITICAL**

Given source_name='ZeroHedge', source_tier='wire', `_break_chip_label` falls through the generic check at chart_render.py:4816 and returns `_fit('ZeroHedge · WIRE SERVICE')` at :4818. `render_breaking_card` composes it at chart_render.py:5235 (`chip_label = _break_chip_label(source_name, tier["label"])`) and draws it as the card's closing seal. The reader sees the outlet's masthead burned into a PNG.

*Fix:* Drop the name half of the chip. chart_render.py:4822-4874 already encodes the tier in chip weight/fill/stroke and the `bc-tier-*` class, so the D05 anti-laundering property survives a name-less chip.

### 5. The only gate that screens card metadata matches '@handle' shapes; a bare brand word is invisible to it
`/Users/chriswong/Documents/Cluade/Macro Dashboard/.claude/worktrees/publish-runner/engine/marketing/copywriter.py:1315` — **CRITICAL**

`build_breaking_payload` assembles card_kwargs with source_name='ZeroHedge' (breaking_summary.py:1091-1103) then calls `_card_param_violations(card_kwargs)` at breaking_summary.py:1112. That flattens every string and calls `foreign_handle_mentions` (copywriter.py:1265), which iterates `_HANDLE_MENTION_RE.finditer` — an @-anchored regex. 'ZeroHedge' yields no match, the screen returns [], no `_CardHandleLeak` is raised, and the branded card renders and ships.

*Fix:* Call relay_hygiene.self_brand_hit on source_name/headline/summary inside `_card_param_violations` (breaking_summary.py:880) and raise the existing `_CardHandleLeak`, which already drops the picture and keeps the post.

### 6. The card names a source the post-text lane already ruled must NOT be named — source_authority is never consulted by the card builder
`/Users/chriswong/Documents/Cluade/Macro Dashboard/.claude/worktrees/publish-runner/engine/marketing/breaking_summary.py:1093` — **CRITICAL**

For ob-2026-08-05-a13e444da9 the item's persisted metadata is `citation_tier: 'unnamed'`, `citation_reason: 'no credit: macro_print — a published figure the reader can check'`, `via_source: 'ZeroHedge'` — the post text ships with NO credit clause. The same payload builder then passes `source_name=item.get('source_name', ...)` raw at breaking_summary.py:1093 into render_breaking_card, and the attached PNG prints 'ZeroHedge · WIRE SERVICE'. Two surfaces of one post give opposite answers to 'whose name goes on this', and the one that leaks is the one the reader cannot edit or click away.

*Fix:* Resolve the chip through source_authority.citation(item, cfg=...) in build_breaking_payload so the card can never out-name the copy lane; under L3 the correct value for every tier is no name.

### 7. Card body is rendered at a FIXED 41px with a hard 3-line cap against a 320-char producer budget — ellipsis is mathematically guaranteed, not incidental
`/Users/chriswong/Documents/Cluade/Macro Dashboard/.claude/worktrees/publish-runner/engine/marketing/chart_render.py:5284` — **CRITICAL**

Given the P3 summary (146 chars, well inside the 320-char producer budget at engine/marketing/breaking_summary.py:96 `_MAX_SUMMARY_CHARS = 320`), render_breaking_card draws it at the bare constant `sm_size = u(41)` (chart_render.py:5284) into `col_w - sm_indent`, capped by `sm_cap = min(3, int(sm_room // sm_lh))` (chart_render.py:5304) and in practice 2 lines because `sm_reserve = (sm_gap + 2 * sm_lh)` (chart_render.py:5293) only reserves two. The reader of the PNG sees 'week, with July headline estimates at +80k…' and never sees the +57k the +80k is measured against.

*Fix:* Give the summary the same descending size ladder + fitter the headline already has (41 → ~28), and let the box, not `min(3, ...)`, govern the line count. If the copy still overflows at the ladder floor, drop the summary block entirely — a text-only body is lawful under L2, an ellipsised one is not under L4.

### 8. card_earns_attachment is approval-only — the summary branch returns True before the headline-vs-post check can ever veto
`engine/marketing/breaking_summary.py:972` — **CRITICAL**

A card whose hero is a verbatim copy of the post text is attached whenever the card's second line happens to differ from the post. Reader sees the same sentence twice: once as tweet text, once as the card headline. Verified live on ob-2026-08-05-3f3a1f19c9.

*Fix:* Make the function veto-capable: evaluate restatement_score(post, headline) FIRST and return False on >= threshold regardless of what the summary adds, or require BOTH lines to clear the threshold before returning True.

### 9. The post-text restatement gate's own remedy manufactures the card defect — short_form makes the card hero identical to the post
`engine/marketing/press_lane.py:2406` — **CRITICAL**

Given a two-line wire post whose line 2 restates line 1, the restatement gate collapses the post to the headline alone; the card then renders that same headline as its hero. Every firing of the text gate produces a card that is a screenshot of the tweet it just repaired. 15 of 15 shipped short_form cards.

*Fix:* When shape == short_form the post has been reduced to one line; either suppress the card outright on that path, or force the card gate to compare against the hero the renderer will actually draw (see finding 8) so the 1.00 score reaches the veto.

### 10. card_earns_attachment can only ever veto on the headline; the card-body branch is attach-only, so a card whose visible body restates the post cannot be dropped
`/Users/chriswong/Documents/Cluade/Macro Dashboard/.claude/worktrees/publish-runner/engine/marketing/breaking_summary.py:972` — **CRITICAL**

post_text == headline == "India's central bank keeps benchmark rates steady, cites 'moderate' core inflation" with card_summary = 'The Reserve Bank of India maintained its benchmark interest rates unchanged, citing moderate core inflation.' returns (True, 'card summary adds detail the post text does not carry'). The headline veto at breaking_summary.py:988-995 — the ONLY `return False` in the function — is never reached because the summary branch at :972-974 returns first. The reader sees a card whose hero is the tweet word-for-word.

*Fix:* Make the card-body test a VETO: if card_summary is present and restatement_score(post, card_summary) >= _RESTATE_THRESHOLD, return False regardless of headline; and evaluate the headline branch first so a verbatim card headline is never rescued by a reworded body.

### 11. The value gate accepts any attached media as both 'hard proof' and 'informational surplus' without inspecting it — a card that restates the tweet is what makes the tweet shippable
`/Users/chriswong/Documents/Cluade/Macro Dashboard/.claude/worktrees/publish-runner/engine/marketing/value_gate.py:381` — **CRITICAL**

A press item with no digit, no cashtag, no mechanism/rule/explanation and no citation URL abstains with ['gift:no_informational_surplus','proof:below_hard']. Attach ANY card and _proof_tier returns 'hard' at value_gate.py:381-382 and surplus['media'] flips True at :486, so the item passes. The card is never examined. Because value_gate.enforce is TRUE and 'breaking' is in enforce_kinds, press_lane.py:1270-1271 does `return None` on an abstention — so the restating card is literally the reason the post shipped at all.

*Fix:* has_media must not be a proof tier or a surplus leg on its own — gate it on the card's payload (finite tape row, chart series, comparison). Fix the dead `url`→`source_url` key at press_lane.py:1244 and the dead `source_headline` key at :1243.

### 12. No configured length budget matches the card's measured body capacity — every summary written to its configured budget is ellipsised (L4 by construction)
`config/press_sources.yml:817` — **BLOCKER**

The summarizer is told ≤320 characters (breaking_summary.py:438-439). It returns 155 chars for the RBI item. chart_render.py:5304 computes sm_cap = 2 because the 4-line headline ate the copy box, _bc_wrap_w clips at 41px/906px and appends U+2026, the overflow flag is discarded at :5305, and the reader sees a static PNG ending 'unchanged, citing…' with nothing that can reveal the rest — operator law L4, by construction, on every card whose summary exceeds ~85-122 chars.

*Fix:* Add `wire.card.summary_max_chars` sized to the measured capacity and enforce it in build_breaking_payload before the summary reaches the renderer; better, have chart_render return the discarded `overflowed` flag and set summary=None (the renderer already handles an absent summary) rather than ship an ellipsis. Extend provenance.card_fit to record summary_chars_dropped so the clip stops being invisible.

### 13. The card summary is ellipsis-clipped and the overflow flag is discarded; the headline has ladder protection against exactly this and the summary has none
`engine/marketing/chart_render.py:5306` — **MAJOR**

Input: any card_summary whose wrap exceeds sm_cap lines at the summary type size. Code: _bc_wrap_w clips the last line with '…' (:4986-4991), the caller at :5306 discards the overflow flag, and card_fit (breaking_summary.py:1164) counts nothing. Reader sees a static PNG ending mid-clause with no way to reveal the rest, and the 'COUNTED, never silent' provenance record reports a clean fit.

*Fix:* Apply the dead _BREAK_SUMMARY_MAX_CHARS bound whole-sentence before wrapping (same discipline as derive_card_headline), treat a still-overflowing summary as summary=None rather than clipping, and extend card_fit + the ::warning to count summary chars dropped.

### 14. Earnings-call lane renders a card whose headline is a literal prefix of the post text, with no restatement gate anywhere in the lane
`engine/marketing/earnings_call_lane.py:407` — **MAJOR**

Input: any committed earnings-call event. Code: :215 composes headline '$TICKER Q# FY####  call: <tone> tone.', :239 makes it the first line of the post text, :408 makes the same string the card hero, and nothing in the lane can drop the media on content grounds. Reader sees a tweet whose opening line is reproduced at poster scale as the attached PNG's hero — one fact on two surfaces.

*Fix:* Give the card a hero the post does not already open with (a metric, a comparison, or the tape) — do NOT add a card_earns_attachment call, which the cashtag exemption at breaking_summary.py:966-970 makes unconditionally True for this lane.

### 15. The gate's own test suite pins the bypass as correct behaviour
`tests/test_marketing_card_earns_pixels.py:260` — **MAJOR**

Input: a builder fixing the :972-974 hole. Code: the corrected gate returns False (or attaches with the hero suppressed) for GOLD_POST/GOLD_HEAD + distinct summary; :266 `assert attach is True` fails. Result: the fix reads as a regression and is reverted, and the defect the test was written to prevent stays shipped.

*Fix:* Rewrite the test to the intended contract: a distinct summary earns the SUMMARY BLOCK, not the whole card. Expected outcome for a restating hero plus a distinct summary is attach=False, or attach=True with the hero suppressed — assert on the rendered element set, not just the boolean.

### 16. De-handling is lane-scoped: the RSS and Alpaca lanes never call display_source_name, and one of them actively prettifies the brand
`/Users/chriswong/Documents/Cluade/Macro Dashboard/.claude/worktrees/publish-runner/engine/marketing/breaking_feed.py:155` — **HIGH**

An item from `zerohedge_feed` (config/marketing.yml:2502-2506, kind rss, source_name 'ZeroHedge', tier wire) takes `source_name = source_cfg.get('source_name', source_key)` at breaking_feed.py:155 verbatim and plumbs it unchanged into FeedItem at :216/:269/:310, straight to the card chip. An Alpaca row takes `_pretty_wire_name(row.get('source'))` at press_providers.py:812, which title-cases the raw wire brand ('benzinga' → 'Benzinga') for display. Neither lane ever passes through the fail-closed de-handling function, so 100% of the branded cards come from the two lanes de-handling cannot reach.

*Fix:* Apply the display-name policy once at FeedItem construction for every provider, not per-lane at the X provider.

### 17. The guard suite pins the branded chip as correct behavior — a compliant fix fails CI
`/Users/chriswong/Documents/Cluade/Macro Dashboard/.claude/worktrees/publish-runner/tests/test_marketing_card_earns_pixels.py:647` — **HIGH**

Removing the publication name from the chip to satisfy L3 makes tests/test_marketing_card_earns_pixels.py:647 `assert "Federal Reserve · OFFICIAL SOURCE" in named` fail — a compliant fix goes red in CI, so the suite defends the defect. Separately no test in the repo can observe a bare-brand leak onto a card: the only chip-level de-handling assertion (test_marketing_wire_dehandle.py:437) uses `chip="@BRICSinfo · AGGREGATOR"`, an @-form the current regex already catches.

*Fix:* Rewrite :647 to the L3 form (chip text equals the tier label alone) and add a mutation-style test rendering with source_name='ZeroHedge' asserting 'ZeroHedge' is absent from the SVG.

### 18. _bc_wrap_w's `overflowed` return — the only signal that the card truncated — is discarded at the summary call site, so no gate, alarm, or provenance field can see the clip
`/Users/chriswong/Documents/Cluade/Macro Dashboard/.claude/worktrees/publish-runner/engine/marketing/chart_render.py:5306` — **HIGH**

A press-wire item whose summary overflows the 41px body is clipped inside the renderer at chart_render.py:5306 (`sm_lines, _ = _bc_wrap_w(...)`), after every gate has run. `card_earns_attachment` at press_lane.py:2524-2528 is handed `payload.get('card_summary')` — the full un-rendered string — so it cannot measure what the card actually shows. The durable record `card_fit` (breaking_summary.py:1164-1168) carries only headline fields, and the `::warning title=breaking-card-headline-compressed` alarm (breaking_summary.py:1078-1088) fires only on headline compression. The ledger therefore records a clean fit while the PNG ends in '…'.

*Fix:* Surface the summary overflow flag out of render_breaking_card (or re-run the wrap in build_breaking_payload), add summary_source_chars/summary_card_chars/summary_chars_dropped to card_fit, and make a non-zero summary drop a hard veto in card_earns_attachment rather than a warning.

### 19. The documented W4g invariant 'the hero is never truncated with an ellipsis, at any length' is false whenever the ticker strip is present
`/Users/chriswong/Documents/Cluade/Macro Dashboard/.claude/worktrees/publish-runner/engine/marketing/chart_render.py:5074` — **MAJOR**

Given a 174-char headline (inside the 180-char `_BREAK_HEADLINE_MAX_CHARS` at chart_render.py:4530), 4 enriched tickers, and a summary, `tick_block_h` (chart_render.py:5257) takes 202px off the copy box and the two-line summary reservation (chart_render.py:5293) takes the rest, leaving the hero ~206px. At the extended ladder floor of 46px the fitter gets 3 lines for 5 lines of text and clips the hero itself. The reader sees 'steady until the disinflation path is…' — the warning, which is the news, is what gets cut — while `derive_card_headline` returns the text unchanged, so headline_chars_dropped == 0, card_fit records a clean fit, and the breaking-card-headline-compressed alarm never fires.

*Fix:* Either correct the two docstrings to state the real precondition (no ticker strip), or make the invariant true: when the ladder floor still overflows the ACTUAL remaining box, drop the ticker strip or the summary block — both optional chrome — before clipping the hero. Add a regression rendering with tickers=4 AND a summary asserting no '…' in any >=46px text node.

### 20. The no-clip guard test exercises only the single best-case configuration, so it cannot see either live truncation
`/Users/chriswong/Documents/Cluade/Macro Dashboard/.claude/worktrees/publish-runner/tests/test_marketing_card_earns_pixels.py:609` — **MAJOR**

`test_long_headline_fills_the_box_rather_than_clipping` asserts `"…" not in body` over the whole card (tests/test_marketing_card_earns_pixels.py:615-619) but calls render_breaking_card(CENTCOM_HEAD, 'Newswire', 'aggregator', '2026-08-02T23:13:34Z') with four positional args — no summary, no tickers: the maximum-copy-box configuration. Adding only a summary to that identical call clips the body; adding tickers too clips the hero. The suite therefore stays green while 56 of 58 shipped breaking cards carry an ellipsis, and will stay green through any regression of the summary path.

*Fix:* Parametrize the no-clip guards over the live argument matrix — {summary: None, 320-char} x {tickers: None, 4 rows} x {height: 1080, 1350} — asserting no '…' in any text node above chip size, and add an artifact-level check over data/marketing/outbox/media/**/*.svg so a clipped card is caught at publish time.

### 21. The card's own overflow signal is discarded — every truncated body ships silently while provenance.card_fit reports zero characters dropped
`engine/marketing/chart_render.py:5306` — **HIGH**

Any card_summary longer than ~80 characters is silently clipped mid-clause with an ellipsis on a static PNG. The durable record (source.card_fit) reports 0 chars dropped, so no monitor, log line, or test can see it. 27 of 34 shipped press cards.

*Fix:* Read the flag at :5306; on overflow either drop the summary block entirely (the geometry already supports sm_lines=[]) or count the dropped characters into card_fit alongside the headline count and emit the same ::warning.

### 22. _BREAK_SUMMARY_MAX_CHARS is a dead constant — the only written bound on card body capacity is never read
`engine/marketing/chart_render.py:4531` — **HIGH**

The summarizer validates a 135-character summary as in-bounds (limit 320) and hands it to a box that holds ~80. No component in the chain holds a bound that would have caught the mismatch, so the renderer clips. Given any LLM summary over ~80 chars, the card body ends mid-clause.

*Fix:* Either delete the two dead constants and derive the producer bound from the measured geometry, or wire _BREAK_SUMMARY_MAX_CHARS/_STRIP into the summarizer's validation and re-derive their values from the current 41px/2-line box (they are stale: 240 was set for a 4-line 26px body).

### 23. earnings_call_lane renders a breaking card with NO value gate and no text-only path — but the lane has no production caller
`engine/marketing/earnings_call_lane.py:407` — **MAJOR**

If the lane is armed, every earnings-call post ships a card whose hero is the post's first line verbatim (measured r=1.0 on the repo fixture), with no gate able to drop it and no text-only fallback — :531-532 kills the post rather than posting it card-less. Today the scenario is unreachable because nothing calls the lane.

*Fix:* Before arming, call card_earns_attachment in _media_for_event and make the no-media path fall through to a text-only outbox item instead of returning media_unhosted. Note the cashtag branch (finding 6) must be fixed first or the wired gate is dead on arrival here.

### 24. The cashtag branch disarms the whole card-value gate for ticker posts — and every earnings-call post is a ticker post by construction
`engine/marketing/breaking_summary.py:965` — **HIGH**

Given any post containing a cashtag, card_earns_attachment returns True without comparing a single word, so a card that is a 1.00 verbatim restatement on both lines is approved. Verified on the earnings fixture; currently reaches 2 of 43 press-lane media items and would reach 100% of earnings-call posts.

*Fix:* Split the two questions: keep the ticker law as a floor on WHETHER a picture ships, but require the picture that ships to be a non-restating one — e.g. on a cashtag post with a restating card, fall back to the chart/tape card rather than approving the restating breaking card.

### 25. _BC_GENERIC_SOURCE_NAMES cannot fire on any real outlet — the de-handling gate is a 6-entry placeholder denylist policing a population of publication names
`engine/marketing/chart_render.py:4774` — **HIGH**

Given source_name='CNBC' and source_tier='wire', the card prints 'CNBC · WIRE SERVICE'. The de-handling gate never fires on any of the 26 branded chips shipped. The reader sees the source outlet named on our card, which L3 bans.

*Fix:* Invert the rule: the chip carries the tier word alone (plus the unnamed-credit form) unless the source is on an explicit allowlist of official ISSUERS (Federal Reserve, BEA, BLS) whose identity is itself the fact. Denylisting publication names cannot enumerate the population.

### 26. The card gate scores `headline` while the card draws `card_headline` — it can be handed a string that is not on the card
`engine/marketing/press_lane.py:2526` — **MAJOR**

Given a long relay (e.g. the 814-char Truth Social item named in the code comment), the gate measures containment against the full source text and approves, while the 180-char hero the reader actually sees restates the post at 0.82. Demonstrated at 0.64 approved vs 0.82 drawn.

*Fix:* Pass payload.get('card_headline') into card_earns_attachment at press_lane.py:2526 — the field already exists and is already computed; the gate must score what is drawn.

### 27. The RADAR breaking card carries nothing the tweet does not — every drawn element is either already in the post text or is brand chrome
`/Users/chriswong/Documents/Cluade/Macro Dashboard/.claude/worktrees/publish-runner/engine/marketing/chart_render.py:5301` — **MAJOR**

A press-lane wire item with no matched tickers renders a card whose only informational block is `card_summary` — which is `summary_result["summary"]` (breaking_summary.py:1061-1065), the exact same string press_lane composes the post body from (press_lane.py:2284 → 2325 `base_summary` → 2340 `_apply_wire_voice`). The tape strip is skipped entirely when `card_tickers` is empty (`tick_block_h = 0.0 if not rows`, chart_render.py:5257). The reader sees a PNG restating the tweet, at a Chrome raster + R2 upload cost (press_lane.py:1198-1203).

*Fix:* Gate the summary block on a payload the post text cannot carry (a populated tape strip with finite price/pct, or a comparison/history panel). Empty payload ⇒ no card, post ships text-only.

### 28. The gate scores the full card_summary, but the card draws at most 3 lines and hard-clips with an ellipsis — the 'adds detail' justification is computed on words the reader never sees
`/Users/chriswong/Documents/Cluade/Macro Dashboard/.claude/worktrees/publish-runner/engine/marketing/chart_render.py:5304` — **MAJOR**

card_earns_attachment measures the WHOLE card_summary string (breaking_summary.py:973), scores it below threshold, and attaches. render_breaking_card independently computes `sm_cap = min(3, int(sm_room // sm_lh))` (chart_render.py:5304) and _bc_wrap_w hard-clips the final line, trimming characters until '…' fits (chart_render.py:4986-4991). The differentiating tokens that earned the attachment are cut. Reader sees a PNG whose visible body is a strict prefix of the tweet, ending mid-clause, unrecoverable.

*Fix:* Gate against the text the renderer will actually draw (return the wrapped/clipped sm_lines and score their join), and refuse to draw a summary block that clips at all.

### 29. The cashtag short-circuit returns attach=True before any content check, and the card it green-lights need not carry a single price
`/Users/chriswong/Documents/Cluade/Macro Dashboard/.claude/worktrees/publish-runner/engine/marketing/breaking_summary.py:965` — **MAJOR**

Any $TICKER in the post text returns True at breaking_summary.py:966-970 before the summary, tape, or headline checks run. _enrich_tickers (breaking_summary.py:659-675) appends `{"ticker": t, "price": None, "pct": None}` unconditionally when load_closes fails, and render_breaking_card draws a cashtag-only chip with no number (chart_render.py:5385-5405). The 'picture' the operator law demands is satisfied by a card whose entire content is the tweet plus the cashtag the tweet already contains.

*Fix:* Keep the ticker-post picture law but require the picture to carry the tape (≥1 finite price/pct row) or a chart; a cashtag post whose only card is a restatement routes to render_chart_v2 or does not post.

### 30. No test can observe the card-body branch saying no — every card_earns_attachment assertion with a summary asserts attach=True
`/Users/chriswong/Documents/Cluade/Macro Dashboard/.claude/worktrees/publish-runner/tests/test_marketing_card_earns_pixels.py:261` — **MAJOR**

The restatement_score(post, summary) guard at breaking_summary.py:973 can be deleted and CI stays green, so finding #2's live defect is invisible to the suite named for this exact law.

*Fix:* Add a pinning case from the live artifact: post = the India RBI text, headline = the same string, summary = the RBI paraphrase; assert attach is False. Add a second case asserting the gate is evaluated against the wrapped/clipped body the renderer draws.

### 31. wire.voice.llm_tier_salience_floor: 80.0 can never bind — the "sonnet flagship" tier is dead config and silently overrides breaking.llm.model_key
`config/press_sources.yml:805` — **MAJOR**

An operator reads config/press_sources.yml:800-807 and config/marketing.yml:2534 and believes wire card copy is written by claude-sonnet-4-6. It never is: breaking_summary.py:388-392 discards marketing.yml's model_key, resolve_llm_tier returns "volume" on 71 of 71 emitted items (max salience 78.0 < floor 80.0), so the Claude-side model id is always claude-haiku-4-5 and the marketing.yml key has no effect at all.

*Fix:* Either recalibrate llm_tier_salience_floor onto the emitted distribution (p90 ≈ 63) or delete the tiering block and name one model_key. Whichever, make breaking_summary print/persist the override (`provenance.model_key_source`) so marketing.yml:2534 stops reading as authoritative, and add a precedence line at both config sites.

### 32. breaking.salience_threshold: 60 is a dead key — nothing reads the flag it computes, yet two config files document it as an admission gate
`config/marketing.yml:2390` — **MAJOR**

An operator reacting to the P1/P2/P3 cards raises breaking.salience_threshold from 60 to 90 in config/marketing.yml to stop low-value wire relays. Nothing changes: score_item still stamps a `relevant` flag no caller reads, press_lane still admits on flagship_salience_floor 30.0, and the same class of item ships that night. The operator concludes the lane ignores config.

*Fix:* Delete `salience_threshold` from config/marketing.yml and correct both comments (marketing.yml:2397, press_sources.yml:545). Do NOT arm it at 60 as documented — with flagship_salience_floor at 30 that is a large unmeasured tightening.

### 33. The publisher's last gate screens post TEXT only — a queued card with a brand chip cannot be caught at dispatch
`/Users/chriswong/Documents/Cluade/Macro Dashboard/.claude/worktrees/publish-runner/scripts/marketing_publisher.py:2382` — **MEDIUM**

Once an outbox item exists whose media[].path points at an SVG carrying 'CNBC · WIRE SERVICE', nothing between the queue and the network re-examines the picture for source metadata. The publisher's language screen at :2382 runs `_banned_language(text)` on the copy string; the only media-content check is `_card_ticker_mismatch` at :2136, which reads ticker identity. So items queued before any L3 fix ships will post their branded cards after it lands — the exact 'queue is a bypass' shape the copywriter module documents for post text.

*Fix:* Add a post-time media screen reading the queued SVG's chip text (or the persisted source.via_source) and drop the attachment rather than the post, mirroring `_CardHandleLeak`.

### 34. earnings_call_lane truncates its summary twice, and the first cut appends a fabricated full stop that deletes the qualification while reading as a finished sentence
`/Users/chriswong/Documents/Cluade/Macro Dashboard/.claude/worktrees/publish-runner/engine/marketing/earnings_call_lane.py:414` — **MINOR**

Given a 231-char digit-free model summary, `_short_clause(event.get('summary'), 190)` (earnings_call_lane.py:414) cuts at a word boundary (line 113-114) and then returns `f"{text}."` (line 116), producing '…are expected to reverse most of that benefit in.' — a sentence ending on the preposition 'in' with the object of the caution deleted, disguised as complete. render_breaking_card then wraps that to two 41px lines and ships ['Management said gross margin expanded on', 'pricing and mix across both segments during…']. The reader sees only the margin expansion; the hedge is gone from the image, leaving a directionally bullish card built from a two-sided statement, and the lane makes no card_earns_attachment call so nothing can veto it.

*Fix:* Set the budget to the card's real capacity rather than 190, and make _short_clause return '' when the text does not fit whole — the SCAN-NEVER-TRUNCATE rule already written for the press lane at engine/marketing/breaking_summary.py:588-597 ('A sentence either fits whole or is skipped whole'). Route this lane through card_earns_attachment before wiring it to production.

### 35. earnings_call_lane attaches a breaking card unconditionally, with no earns-pixels gate, and makes the card mandatory — its card headline is byte-identical to the post's first line
`/Users/chriswong/Documents/Cluade/Macro Dashboard/.claude/worktrees/publish-runner/engine/marketing/earnings_call_lane.py:292` — **MINOR**

compose_event builds headline = f"${ticker} {quarter} FY{year} call: {tone} tone." (earnings_call_lane.py:215) and text = headline + '\n\n' + body (:239). _media_for_event calls render_breaking_card(headline=composed['headline'], summary=_short_clause(event['summary'], 190)) at :406-419 — the card hero is the post's first line character-for-character. When body candidate #2 wins (:190, summary at 145 chars) the card body is the SAME event['summary'] field cut at 190 instead of 145. build_outbox_item raises ValueError('earnings-call ticker posts require a hosted card') at :293 when media is absent, so the lane is structurally incapable of shipping text-only.

*Fix:* Make the media requirement conditional (a cashtag post with no distinct card should fail closed, not raise), and call card_earns_attachment before _media_for_event — but note the cashtag branch must be fixed (finding #4) for that call to have any effect.

## Refuted (dropped, not defects)

- The gate scores the raw `headline`, not the `card_headline` the renderer actually draws
- The 44- (finding text truncated in the handoff)
- The entire wire_deep format branch is unreachable — deep_salience_floor 75.0 AND the deep-eligible register set are jointly unsatisfiable on live data
- sentinel max_media_posts_per_account_per_day cannot bind on a wire card — 135 shipped card items, zero visible to the cap
- wire_volume.breaking uncapping is justified in-config by a card gate that provably does not hold

## Census

```
{
  "total_posted_with_card": 79,
  "n_ellipsised": 20,
  "n_restating": 10,
  "n_source_branded": 18,
  "examples": [
    {
      "id": "ob-2026-08-05-a13e444da9",
      "post_text": "On the tape: Over 200 years, global economic leadership has shifted from China to the British Empire, then to the United States, and increasingly toward Asia. The share of global GDP held by major economies...",
      "card_text": "Headline: 'How Economic Power Has Shifted Over The Past 200 Years' / Body: 'Over 200 years, global economic leadership has shifted from China to the British Empire,\u2026' / Chip: 'ZeroHedge \u00b7 WIRE SERVICE'",
      "defects": "L1/L2: card body is the tweet's own first sentence verbatim, restated (0.40 word overlap; headline just paraphrases the same fact, card adds nothing the text doesn't say). L3: 'ZeroHedge \u00b7 WIRE SERVICE' chip names the source venue directly on the card. L4: body ends '\u2026' mid-clause on a static PNG with no way to reveal the rest."
    },
    {
      "id": "ob-2026-08-05-3f3a1f19c9",
      "post_text": "India's central bank keeps benchmark rates steady, cites 'moderate' core inflation",
      "card_text": "Headline: \"India's central bank keeps benchmark rates steady, cites 'moderate' core inflation\" (verbatim tweet) / Body: 'The Reserve Bank of India maintained its benchmark interest rates unchanged, citing\u2026' / Chip: 'CNBC \u00b7 WIRE SERVICE'",
      "defects": "L1: headline is the tweet text verbatim -- exact restatement. L2: card supplies zero information the 26-word tweet didn't already state. L3: CNBC chip. L4: body truncated with '\u2026' mid-clause, unrecoverable on a PNG."
    },
    {
      "id": "ob-2026-08-04-42617b3587",
      "post_text": "The US non-farm payrolls report is due this week, with July headline estimates at +80k versus June's +57k...",
      "card_text": "Headline: 'Reminder: US non-farm payrolls will be on the data docket this week' / Body: 'The US non-farm payrolls report is due this week, with July headline estimates at +80k\u2026' / Chip: 'ForexLive \u00b7 WIRE SERVICE'",
      "defects": "L1/L2: headline+body both restate the tweet's lead sentence (0.45 overlap) with no data the text lacks. L3: ForexLive chip. L4: '\u2026' truncation drops the +80k vs +57k comparison mid-thought."
    }
  ],
  "notes": "Scope: /Users/chriswong/Documents/Cluade/Macro Dashboard/.claude/worktrees/publish-runner, joined data/marketing/outbox/items.jsonl (419 rows) to the LAST transition per id in status_ledger.jsonl (981 rows). 109 items reached status \"posted\"; 79 of those carried media and fall in the last-14-days window (cutoff 2026-07-22 relative to today 2026-08-05; earliest posted-with-media item was 2026-07-25, so effectively all recent posted-media items are in scope). Card text was extracted from <text>/<tspan> nodes of the referenced SVG (data/marketing/outbox/media/<date>/<id>.svg or top-level media/ dir); 3 of the 79 had no SVG found at the recorded path and are counted as
```

```
{
  "lanes": [
    {
      "lane": "press_lane (wire/press stream, alpaca)",
      "file": "engine/marketing/press_lane.py:2279 (build_breaking_payload call), :2515-2530 (card_earns_attachment call)",
      "attaches_card": "yes, via breaking_summary.build_breaking_payload -> chart_render.render_breaking_card, then conditionally dropped",
      "renderer": "engine/marketing/chart_render.py:render_breaking_card (line 5032)",
      "gate": "card_earns_attachment (engine/marketing/breaking_summary.py:942) IS called at press_lane.py:2524 \u2014 but is BUGGY (see findings): its final fallback compares the post text against the raw `headline` field, never against the actual `card_summary` text drawn in the card body, so a card whose visible body restates the post can still pass."
    },
    {
      "lane": "earnings_call_lane",
      "file": "engine/marketing/earnings_call_lane.py:388-416 (_media_for_event)",
      "attaches_card": "yes, unconditionally whenever an earnings-call item is composed",
      "renderer": "engine/marketing/chart_render.py:render_breaking_card (eyebrow='EARNINGS CALL')",
      "gate": "NONE. No call to card_earns_attachment, summary_earns_the_card, or any restatement check anywhere in earnings_call_lane.py (grep confirmed zero hits). This is a lane->renderer edge with the gate entirely absent \u2014 a card can restate the composed post text and nothing stops it."
    },
    {
      "lane": "content_studio (nightly)",
      "file": "engine/marketing/content_studio.py:3950 / 4246 / 4819 / 5157 (render_chart_v2 call sites)",
      "attaches_card": "yes, chart cards (candles/AVWAP/POC overlays) built from chart_facts",
      "renderer": "engine/marketing/chart_render.py:render_chart_v2 / render_signal_chart",
      "gate": "Different mechanism: chart_director.py's in-frame-restatement gate (\u00a70 gate 5, chart_director.py:413-464) checks that CAPTION numbers are restated ON the chart (data-integrity direction), not that the CARD as a whole doesn't restate the post text. No card_earns_attachment-style post-vs-card check found in this lane."
    },
    {
      "lane": "hot_tape / hot_tape_llm",
      "file": "engine/marketing/hot_tape.py, hot_tape_llm.py",
      "attaches_card": "no direct render_* / card_svg reference found in these files (grep negative)",
      "renderer": "n/a in this lane directly \u2014 hot_tape composes text (BREAKING wire-register copy) only, per hot_tape_llm.py:167 prompt guidance",
      "gate": "n/a \u2014 no card path found"
    },
    {
      "lane": "publish_time_content",
      "file": "engine/marketing/publish_time_content.py",
      "attaches_card": "references share_cards (grep hit) but not render_breaking_card/render_chart_v2 directly in this census pass",
      "renderer": "share_cards.py (BRAND_URL footer, share-card family)",
      "gate": "not verified in this pass \u2014 flagged for follow-up, not confirmed either way"
    }
  ],
  "renderers": [
    {
      "name": "render_breaking_card",
 
```
