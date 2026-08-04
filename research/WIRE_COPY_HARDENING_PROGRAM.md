# Wire copy hardening — why "More info on this" got through, and what actually closes the class

**Status:** program charter. Written 2026-08-04, from the postmortem of the live
post below. §1–§2 are the diagnosis; §3 is the standing law; §4 is the build
queue, ordered. §5 answers the model question directly.

---

## §0 The post

```
More info on this - South Korea core inflation hits 2-1/2 year high
despite headline cooling -- wire reports
```

@mastermindx001, 2026-08-04T01:11Z. Both halves were defects, from opposite
directions: the first is ForexLive/InvestingLive's own headline relayed verbatim
(their prefix for a follow-up to their earlier post — on their page "this" has an
antecedent), the second is a string we invented to avoid naming a source.

It was not an outlier. Of the four items that feed produced in its first 30
hours, **three carried a defect of the same family.** And of the 25 items on the
feed's live window, **six are the publisher's own page furniture** — calendars,
house wraps, "What are the main events for today?" — admitted at `tier: wire`
with a +8 salience bonus.

---

## §1 Why every gate passed it

This is the part worth sitting with, because the gates are *good* and they all
said yes.

| Gate | Verdict | What it asked |
|---|---|---|
| `garbage_gate` (5 detectors) | pass | satire? blocklist? promo? paywall? horoscope? |
| `validate_summary` | pass | every number in the source? stance words? ≤2 sentences? |
| `banned_language` | pass | study names, internal jargon, em dash? |
| `foreign_handle_mentions` | pass | any `@handle`? |
| `restatement_verdict` | **fired** | does line 2 re-say line 1? → dropped line 2 |
| `card_earns_attachment` | **fired** | does the card add anything? → dropped the card |
| `value_gate` | pass | gift / grip / proof / bridge — all true |
| `validate_postable` | pass | non-empty, under 280, link policy |

Look at what that table actually says. **The system correctly detected that there
was almost nothing there. It deleted everything that was empty, and posted what
was left.**

Two structural facts explain it.

**(a) Every gate is a question about the STRING. None is a question about the
READER.** Under 280 chars, no banned word, no `@`, numbers all sourced, tokens
don't overlap. "More info on this" passes all of it. It fails exactly one test —
*can someone who sees only this post resolve it?* — and that test is not asked
anywhere in the pipeline. It cannot be asked by a word list, because the defect
is about what is **missing from the reader's context**, not about what is present
in the text. The repo already names this trap, in `copywriter.jargon_violations`:

> the open-ended half of this class ("does this sentence cite something the
> reader cannot see?") is not enumerable

**(b) Subtraction had no floor.** `restatement_verdict` removed line 2.
`card_earns_attachment` removed the card. Neither could say "…and what's left is
no longer a post." A pipeline of subtractive gates with no terminal re-qualifier
converges on the thinnest thing that still parses.

And one aggravating fact: **the LLM fallback was dark.** `press_lane` read
`mode = payload.get("mode")` and never used it again — not logged, not counted,
not in provenance. So "the summarizer wrote this sentence" and "the summarizer's
output was thrown away and we relayed the raw RSS title" were the same observable
event. Eight of the outbox's press items were headline relays. Nothing said so.

---

## §2 The measurement that changed the priority

While fixing the above I counted the queue:

```
308 queued items, oldest 2026-07-24 — ELEVEN days
  5 still carry a foreign @handle, banned 2026-08-02
  1 of those is the "-- @FirstSquawk reporting" post that IS
    the de-handling postmortem's own fixture
```

Content laws in this repo run at **compose** time. Every item enqueued before a
law existed keeps its pre-law text forever. The relay-hygiene fix would have had
exactly the same blind spot — it repairs the writer, and the writer cannot reach
copy already written.

This is not a new discovery so much as a rediscovery: the publisher already
carries two post-time screens built after the same lesson (the language gate,
after the $AVGO "POC held" post fired days after its ban; the voice gate, after
187 machine-voice posts sat queued through a rule change). The relay laws simply
were not among them. They are now.

> **Fixing the generator fixes tomorrow's posts. Only a last gate fixes the
> queue, and the queue is what reaches the timeline.**

---

## §3 Standing laws

Six, in the order they would have stopped this post.

**L1 — Every gate needs a reader, not just a regex.**
A rule list can only catch the defects someone already named. The open-ended half
("can a stranger resolve this sentence?") needs something that reads the post as a
stranger. This is not an argument for letting a model write — it is an argument
for letting one *refuse*. Constitutionally that is the permitted direction: the
epistemics law already says LLMs may only **de-escalate**, never originate.

**L2 — Subtraction needs a floor.**
Any gate that can REMOVE material must be followed by a gate that can VETO the
remainder. "Everything empty was deleted" is not the same as "what's left is
worth posting."

**L3 — Degrade the destination, not the content.**
Every failure path in this pipeline currently ends at *relay the source verbatim*
— so the more of our processing failed, the **less processed** the thing we
publish. That is backwards. A failure should cost **reach**, not quality: the
summarizer failed → the item goes to the rail, not to the flagship. This
inversion alone would have stopped the live post, because it fell back twice.

**L4 — A law that runs at compose time protects nothing already composed.**
Every content law needs a post-time twin. *(Shipped.)*

**L5 — A new source is unproven until its output has been read.**
ForexLive went from absent to flagship-posting in a single PR, at wire tier with
a salience bonus, and 30 hours later three of its four posts were defective.
Nothing shadow-ran it. Nothing measured it. Nothing demoted it.

**L6 — Someone has to read what we posted.**
This defect was found by the operator, on their own timeline, by eye. There is no
automated read-back of published copy anywhere in the repo. Every defect class we
have not yet imagined will be found the same way until there is.

---

## §4 Build queue

Ordered by (defect classes closed) ÷ (effort). Everything below is unbuilt unless
marked.

### P0 — Cold-read veto on relayed lanes *(the one that matters)*

One local-model call per relayed post, immediately before it goes out, answering
a single question:

> Reading only this post — no other context — is there anything a reader cannot
> resolve? A pronoun with no antecedent, a reference to something not shown, a
> promise from someone unnamed, a brand that isn't ours.

**Veto only. It never rewrites, never scores, never originates.** Output is
`{blocked: bool, reason: str}`; a block quarantines with the reason attached. Runs
on `_RELAYED_PROVENANCES` only.

Why this is the high-value item: it is the only proposal here that closes the
**unenumerated** half of the class. Every rule in `relay_hygiene.py` catches a
defect we already saw. This catches the next one. It is also nearly free — a 9B
local model, one short prompt, on the ~30 relayed posts/day — and it fails safe
(model unreachable → unscreened, exactly like the existing screens).

The prompt is the whole design. It must ask about the **reader's** ability to
resolve the text, never about quality, tone, or importance — those are judgment
calls that would let a model start editing the desk.

### P1 — Invert the fallback ladder (L3)

`summary_mode in ("deterministic", "llm_fallback")` → the item is rail-eligible
but **not** flagship-eligible. The plumbing landed with this PR (`summary_mode`
is now recorded per item); what remains is the routing rule and a threshold.

### P2 — Source probation and auto-demotion (L5)

* A newly-configured feed enters `shadow`: composed, logged to the rail, never
  posted, for N items or 48h.
* Per-source rolling defect rate over the fields this PR started recording —
  `summary_mode`, `post_shape`, `citation_tier`, `relay_stub` drops. A source
  whose LLM-fallback rate or furniture-drop rate crosses a threshold is demoted
  out of the flagship automatically, with a `::warning` naming it.
* Graduation from shadow is an explicit config flip, not a timer.

Note what this needs that we now have: **before this PR the fallback rate was
unobservable.** Probation was unbuildable, not deprioritised.

### P3 — Published-post auditor (L6)

A scheduled pass over the last N *published* texts — local model, same veto
prompt as P0 plus "anything odd here?" — writing findings to the marketing radar.
This is the backstop for classes nobody has enumerated, including P0's own
misses. Cheap, off the render path.

### P4 — Frozen adversarial corpus in CI

Every live defect becomes a permanent fixture with its expected outcome. Seeded
by this PR with four (the pointer, the branded wrap, the first-person body, the
filler line). The rule: **a defect that reached the timeline is a test before it
is a fix.**

### P5 — Typography normalization

Live and unhandled: 3 queued posts relay the squawk feeds' ALL-CAPS verbatim —

```
On the tape: GOLD ROSE ABOUT 0.6% TO AROUND $4,070 AN OUNCE AFTER TRUMP SAID...
```

Same family as everything above: a terminal squawk shouts because that is the
convention on a terminal. A research desk does not. Sentence-case the relay, keep
genuine acronyms and tickers.

### P6 — Source identity drift check

Config said `ForexLive`; the site writes `investingLive` and 301s to
`investinglive.com`. The brand screen missed every branded wrap until it was
taught to read the URL host. A periodic check that a feed's configured
`source_name` still matches what it publishes would have surfaced the rebrand
before it mattered. Low priority, but it is exactly the shape of thing that goes
unnoticed for months.

---

## §5 The model question, answered

**"Is this being posted with no LLM touch-up at all?"**

Not quite — and the truth is worse than a plain no. The LLM was **armed**
(`MARKETING_LLM_ENABLED: "1"` in `marketing-press-wire.yml`, `llm.enabled: true`
in config) and the provider waterfall is four deep, DeepSeek already the last
hosted rung. For this post it produced nothing that survived, and the pipeline
fell back to relaying the raw RSS title — **silently**, with no counter, no
warning, and no provenance field. A lane that is armed, paid for, and discarded
on every item is indistinguishable from a healthy one when you read the outbox.

Three things landed in this PR:

* **One repair attempt.** A rejected draft used to go straight in the bin. The
  validator's complaints are specific ("number 4,070 not in source", "summary
  near-verbatim of source headline") — usable as an instruction, not just a
  score. The model now gets its draft back with the complaints and one more try.
  One retry, never two: a second failure means the packet cannot support a
  compliant restatement, and more calls buy drift, not quality.
* **The fallback is loud.** Per-item warning, per-tick census, and
  `summary_mode` / `summary_violations` on every outbox row.
* **Qwen is wired** as the final rung (`ollama` after `deepseek`), pinned as a
  *tail* so a local model can never be promoted ahead of a hosted one by a config
  edit. It runs only when every hosted rung has failed — at which point the
  alternative is not a better sentence, it is the raw-headline relay. A
  restatement from a local 9B beats no restatement.

**"Should we use Qwen / DeepSeek?"** — for *generation*, they are already there
and generation was never the bottleneck. The real answer is a different job:

> We have **four ways to write** and **zero ways to read.**

Every model call in this lane produces copy. Not one evaluates it. The local Qwen
is well suited to the job the pipeline is actually missing (P0): a short,
binary-ish, veto-only cold read, on ~30 posts a day, on hardware we already pay
for, where being a 9B model costs nothing because the question is not hard — *is
there a "this" here with no antecedent?* is not a frontier-model problem.

That is where the next model call should go. Not into writing better sentences —
into refusing the ones that shouldn't leave the building.

---

## Appendix — what shipped alongside this document

* `engine/marketing/relay_hygiene.py` — scrub / drop rules for source page furniture
* `engine/marketing/source_authority.py` — primary / marquee / unnamed citation tiers
* `copywriter.queued_relay_violations` + the publisher's third post-time screen
* the deterministic lead **scan** (never a truncation), the substance-aware
  restatement gate, the repair retry, and the summarizer census

Live-corpus effect: 5 furniture items drop, 1 pointer is scrubbed to a clean
story, 11 items gain a real masthead, 22 post clean with no invented credit,
and no post carries "wire reports".
