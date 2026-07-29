# Reply doctrine — what a reply must carry to be worth posting

**Program:** Content Studio LLM-first, §10 **E4 — reply-craft intelligence**
(`research/MARKETING_CONTENT_STUDIO_LLM_FIRST_MASTERPLAN_BY_FABLE.md`).
**Ground truth:** `research/marketing_dockets/reply_corpus_2026_07_29/`
(`playbook.md` + `replies.jsonl`) — 180 top replies under 12 large finance posts,
captured 2026-07-29. Every number and every quoted line in this file traces to
that corpus; nothing here is invented.

**Consumed by three things, which is why it is a file and not a comment:**

1. `engine/marketing/reply_voice.py` — the LLM phrasing pass builds its system
   prompt from §2, §3, §6, §7 and §8.
2. `engine/marketing/reply_critics.py::reply_value` — the deterministic critic
   that kills the §8 anti-patterns before a human ever sees them.
3. The M1 operator, via `docs/reply_desk_runbook.md` §7 — the same bar the
   machine is held to is the bar the human approves against.

---

## §0. ACCEPTANCE GATES

A change to the reply lane is not done unless:

1. **The deterministic draft still ships when the model path fails.** Voice is
   an upgrade on top of `reply_drafter.compose()`, never a dependency of it. Any
   gate hit, any provider failure, any disarmed key → the template posts.
2. **No number reaches X that our engine did not compute.** The model phrases;
   it never originates a figure (CLAUDE.md §Epistemics; `fact_discipline`).
3. **The critic roster is complete at the store.** `reply_queue.enqueue` refuses
   an item whose stamp does not list every critic in `reply_critics.CRITICS`.
   Adding a critic without updating the roster pins breaks enqueue, loudly.
4. **Nothing here opens a send.** The mode dial is the only thing that sends,
   the standing cap is 0, and this doctrine changes neither.

---

## §1. The one-sentence law

> A reply is rent paid for someone else's audience. The rent is a **gift the
> thread did not already have**, delivered in **about eleven words**, aimed at
> **the room** and not at the poster.

Everything below is that sentence with evidence attached.

---

## §2. The value taxonomy — the five things a reply may carry

A draft that carries none of these is not a short reply, it is noise. The corpus
classification of the global top 60 is the evidence column.

### Data drop

A concrete, checkable number or level the parent post did not have. The
highest-density winning pattern in the market-analysis threads (data-drop = 8 of
the top 60 on its own, and 39.4% of all 180 replies contain a number).

> "Support at 900-925" — **22 likes**, under a -17% SanDisk day.

Ours comes from an own-feed fact builder, so it is already whitelisted. This is
Kelly's home and the flagship's second gear.

### Sharp read

One sentence that reframes the stat into something felt. The highest ceiling per
unit of parent size in the whole corpus — 96 likes off an account far smaller
than the megacaps.

> "KOSPI is a semiconductor ETF with miscellaneous stocks added for
> diversification." — **80 likes**, under the South Korea chip selloff.

### Dry wit

Deadpan, native idiom, no explanation, no setup. 28.3% of the top 60 is humor,
which makes it the single largest category — and the one most likely to be
mis-executed (see §8: a joke that does not parse gets 0).

> "The nerve of them to miss earnings after that whole ipo commotion" —
> **23 likes**.

House constraint: our humor law is already written (`copywriter.copy_laws`, v3
fintwit register) — deadpan understatement, aimed at forecasts and crowds, never
at people. The corpus's slang register is **evidence about the audience, not a
licence to change ours**.

### Useful reframe

Grant the frame, change what the move is *about*, or zoom out to the rule the
audience already half-believes.

> "Doesn't matter now if companies beat or not, every earnings announcement
> results in a lower stock price" — **44 likes**.

### Missing-number correction

Fix or sharpen the record with one figure. Works at every account size and is
the pattern with the cleanest fit to what we can actually produce.

> "Actually closer to -10%" — **23 likes**.
> "You missed the fact that they blew out net profit the bottom line. Q o Q up
> 133%" — **12 likes**.

**House amendment, non-negotiable:** correction without humiliation
(constitution §9.4). We fix the fact and never name the person, so the corpus's
"You missed…" opener ships here as "Worth adding: net profit was up 133% QoQ."

---

## §3. The length law

n=180 replies, URLs stripped: **min 1, median 11, mean 14.5, max 110 words.**

| bucket | count | share |
|---|---|---|
| 1-5 words | 47 | 26.1% |
| 6-15 words | 73 | 40.6% |
| 16-30 words | 37 | 20.6% |
| 31-50 words | 21 | 11.7% |
| 51+ words | 2 | 1.1% |

**Two-thirds of high-engagement replies are under 16 words.** The operating
targets:

* **Target 11 words. Ceiling 30 words / 240 characters.** The 240 is a hard law
  in the prompt; X's cap is 280 and the headroom is deliberate.
* **One thought, not three.** The 110-word winner in the corpus closes on one
  crisp line; the 0-like essay of comparable length carries three disconnected
  claims. Length is not the defect — *unclosed* length is.
* **Long form is a permitted exception, not a default.** Only 2 of the top 60
  are mini-essays. Our `micro_framework` family is the one that may run long,
  because its structure is the payload.

---

## §4. What lives and what dies under a big post

**Lives:**

* Crowd-voiced rhetoric. A question mark aimed at *everyone reading* is an
  accusation, not an ask: "Isn't FIFA supposed to be a non profit?" (30 likes).
* Being early. Reply timing inside the post's first minutes is a real, separate
  factor from content (see §9).
* One beat. Every winner in the top 60 has exactly one move in it.

**Dies:**

* **A genuine question addressed to the OP.** "What do you think of TIPS in this
  environment?" — **0 likes**. It reads as a DM: it asks the original account to
  do work for one person and gives bystanders nothing to like. Genuine
  OP-directed questions clustered in the zero-like pool.
* **Advice-column boilerplate.** Text that could be pasted under any headline.
* **Restating a fact already in the thread.** "All intercepted" — 0 likes.
* **One-word reactions.** "Oh wonderful." — 0 likes. Too generic to be dry wit,
  which needs the specific native-idiom phrasing.
* **Off-topic self-promo.** A plug wearing a news reaction as a costume.
* **Formatting tells.** One 11-like outlier padded itself with dozens of
  invisible whitespace characters before an @-mention. A manipulation artifact a
  generator must never reproduce.

**Standing brand exclusion — the moral-outrage pattern.** The two highest-liked
replies in the entire corpus (2,186 and 1,877 likes) are blunt moral verdicts on
a political-crossover post. **We never write that pattern.** It is the highest
ceiling in the data and it is forbidden here: it carries no information, it
borrows a crowd's anger, and one screenshot of it next to our profile costs more
than every like it could earn. The corpus's ceiling is not our objective
function.

---

## §5. Persona-register map

Which desk owns which pattern. The reply families
(`reply_drafter.FAMILIES`) are the mechanical form; this is the register.

| Desk | Primary patterns | Families it leans on | Never |
|---|---|---|---|
| **Kelly** (mechanism detective) | missing-number correction, data drop, receipts | `correction`, `missing_variable`, `compression`, `cross_market_lead` | hedging softeners; a number she cannot verify |
| **Sophia** (narrative architect) | sharp read via precedent and analogy | `reframe`, `second_order`, `micro_framework` | forced metaphor; exclamations; hype verbs |
| **Cici** (cross-border correspondent) | the group read — what the Asia session did and what New York inherits | `cross_market_lead`, `reframe` | untranslated Chinese; "China up/down" simplifications |
| **Meagan** (crowd translator) | process read — what the room feels against what positioning did | `human_reaction`, `acknowledgment_plus_one` | finance-bro irony; more than one exclamation |
| **flagship** (The Desk) | sharp read + data drop, terse verdict | `compression`, `missing_variable`, `conditional_prediction` | any exclamation; anything warm |
| **founder** | plain first-person read, dry about his own misses | `human_reaction`, `compression` | pitching the product; victory laps |

**Nobody gets the moral-outrage pattern (§4).** Nobody gets meme cosplay. Dry
wit is available to every desk within its own emoji and sarcasm budget, which
`expression_dial` already enforces per account and per kind.

---

## §6. Compliance rails — unchanged by this doctrine

This file changes *what we say*, never *what we are allowed to say*. All of the
following continue to bind, and all of them are enforced in code, not prose:

* **No advice, no calls.** No entry/exit/sizing/target language anywhere
  (`hot_tape_llm.call_violations`, and the house ban list in
  `copywriter.banned_language`).
* **No position claims.** We do not say what we own.
* **Zero cross-account engagement, ever.** No reply from one of our accounts to
  another; enforced by the `blocklist` critic against `desk_network`, not by
  operator discipline.
* **Numbers only from the own-feed whitelist** (`fact_discipline`).
* **No em dashes, no hashtags, one emoji at most** per the persona budget.
* **Sensitive events are a hard stop.** We do not borrow distribution from a
  tragedy (`DEFAULT_SENSITIVE_TERMS`).
* **The dignity rubric.** If it would read badly screenshotted next to our
  profile, it does not ship.
* **M0 is the standing state.** Nothing in this file sends anything.

---

## §7. Exemplars — verbatim, with their like counts as evidence

These ten are what `reply_voice.PLAYBOOK_EXEMPLARS` ships to the model. They are
transcribed exactly as posted; **their phrasing is evidence about the audience,
not a licence** — our own rails (§6) still decide what may ship.

| likes | pattern | reply |
|---|---|---|
| 96 | sharp analogy | "missing earnings expectations by $3b is like showing up to the olympics and finishing second. still incredible. wall street just doesn't care." |
| 80 | sharp read | "KOSPI is a semiconductor ETF with miscellaneous stocks added for diversification." |
| 75 | reasoned contrarian | "We have not even begun to fulfill demand this is nonsense." |
| 44 | cynical rule | "Doesn't matter now if companies beat or not, every earnings announcement results in a lower stock price" |
| 41 | contrarian with a demand for evidence | "And yet they are still making record profits and revenue with no slowdown in sight. Seriously, I have yet to see a single legitimate date as to when the growth stops for this company" |
| 25 | cross-market missing number | "All the blood and yet, VIX is still below 20." |
| 23 | correct the record | "Actually closer to -10%" |
| 23 | dry wit | "The nerve of them to miss earnings after that whole ipo commotion" |
| 22 | checkable level | "Support at 900-925" |
| 13 | human reaction + stance | "Kind of a rough quarter, but I'm still watching their long-term memory play closely." |

Two of these carry a lesson the like count alone does not:

* **"This is such an overreaction" (43 likes) is deliberately excluded.** It
  earns, and it fails our own `informational_surplus` gate: no referent, no
  number, nothing the thread did not have. A pattern that wins on X and loses
  here is still a loss here.
* The corpus's top two replies (2,186 / 1,877 likes) are excluded for the
  reason given in §4.

---

## §8. Anti-exemplars — the shapes that got zero

Quoted from `playbook.md` §(c), drawn from the same threads and the same
timing window, so they are directly comparable to §7.

1. **Advice-column boilerplate** — *"Breaking events like this remind us why
   risk management matters… Stay informed, avoid emotional decisions, and watch
   for official statements before jumping to conclusions."* (0 likes)
2. **A genuine question aimed at the OP** — *"What do you think of TIPS in this
   environment?"* (0 likes)
3. **Rambling multi-fact essay with no single payload** — three claims, no
   closing line, nothing to agree with in one glance. (0 likes)
4. **Redundant restatement** — *"All intercepted"* (0 likes)
5. **One-word reaction** — *"Oh wonderful."* (0 likes)
6. **Off-topic self-promo** — *"iran news shaking markets, check cmc for
   real-time btc moves"* (0 likes)
7. **Muddled joke** — a metaphor that does not parse. (0 likes)
8. **Ideological rant / conspiracy jargon** — alienates instead of
   crystallizing. (0 likes)

Anti-patterns 1, 2, 3 and 5 are enforced deterministically by the `reply_value`
critic. The rest are already covered: 4 by `informational_surplus`, 6 by
`persona_label` + the house ban list, 7 and 8 by `dignity` and `vocab`.

---

## §9. What this doctrine does NOT claim

The corpus is honest about its own confounds and so is this file. Carried
forward from `playbook.md` §(a) and §(c):

* **Quality is necessary, not sufficient.** One genuinely sharp, specific
  analytical reply in the corpus — *"5.17% on the 30y, highest weekly close
  since 07, and they still call inflation tame…"* — got **0 likes**. It is a
  clean example of the sharp-read pattern and would not look out of place in the
  top 60. It came from a 144-follower non-Blue account, several hours into the
  thread. **Treat a good pattern match as necessary, never as a guarantee.**
* **Timing and account standing are separate, unmeasured factors.** 83.3% of the
  top-60 repliers were Blue-verified, and Blue buys reply-ranking placement on
  X. That is a platform artifact tangled up in the content signal, and this
  corpus cannot disentangle them.
* **Follower count is not the driver.** 46.7% of top-60 repliers had under 500
  followers; only 6.7% had over 50,000. This is the encouraging half of the
  same finding.
* **Two of the twelve source posts went viral outside finance** (a FIFA story
  and a US-politics story) and supply most of the outrage, meme and long-rant
  entries in the top 60. The patterns weighted here are the ones that repeat in
  the ten **market-analysis** threads, because that is the regime a finance
  reply desk actually works.
* **n is small and the window is three days** (2026-07-27 → 2026-07-29), inside
  one live news cycle. Nothing here is a measurement and nothing here is a
  backtest. It is a documented prior with its evidence attached, and the labels
  loop (`engine/marketing/labels.py`, reply outcomes polled by
  `reply_producer.poll_reply_outcomes`) is what will eventually grade it.
* **The like count is not our objective function.** Charter §3 says the
  highest-value reply outcome is the **author replying back**, which is exactly
  what the zero-like "genuine question to the OP" optimises for. That is why the
  `author_question` family survives §4: a question that *also* carries a gift
  gives the room something and gives the author a reason to answer. A question
  with no gift is what dies.

---

## §10. Where this is enforced

| Law | Enforced by |
|---|---|
| taxonomy + register + exemplars | `engine/marketing/reply_voice.py` (system prompt) |
| ≤240 chars, one thought | `reply_voice.validate_reply_copy` |
| numbers from the packet only | `hot_tape_llm.numeric_violations` (imported) + `reply_critics.fact_discipline` |
| no advice / no calls | `copywriter.banned_language` + `hot_tape_llm.call_violations` (both imported) |
| OP-directed questions, boilerplate, one-word reactions, unclosed length | `reply_critics.reply_value` |
| everything in §6 | the eight pre-existing critics, unchanged |
| the model never scores | `reply_critics.run_critics` — the LLM hook may only de-escalate |
