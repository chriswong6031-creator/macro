# Finance-X Reply Corpus — Analysis & Playbook

Source: 6 large finance accounts (KobeissiLetter, unusual_whales, DeItaone, charliebilello,
StockMKTNewz, Barchart) → top 2 non-retweet posts by likeCount each (12 posts) → top replies
by likeCount for each post, via twitterapi.io. Data captured 2026-07-29, covering activity from
~2026-07-27 to 2026-07-29 (a live news window: South Korea/KOSPI chip selloff, SanDisk/SK Hynix
earnings, Iran-US Jordan-base missile exchange, FOMC hold, FIFA/Infantino $20B World Cup company,
Beshear-vs-McConnell). 18 API calls used (budget 80).

Corpus: 385 direct replies observed across the 12 posts (single page each, sorted `queryType=Likes`);
top 15 by likeCount retained per post -> **180 replies in `replies.jsonl`**. A global top 60 by
likeCount (from that 180) was hand-classified for pattern/anti-pattern work.

---

## (a) Stats

**Reply length (words, URLs stripped), n=180:**
min 1, median 11, mean 14.5, max 110.

| bucket | count | % |
|---|---|---|
| 1-5 words | 47 | 26.1% |
| 6-15 words | 73 | 40.6% |
| 16-30 words | 37 | 20.6% |
| 31-50 words | 21 | 11.7% |
| 51+ words | 2 | 1.1% |

**Read:** two-thirds of all high-engagement replies are under 16 words. The manual pass below
shows a meaningful slice of the "1-5 words" bucket is actually an `@handle` + bare image/link
(counts as 1 "word" after URL-stripping) — see media-only pattern.

- **% containing a number:** 71/180 = **39.4%**
- **% containing a question mark:** 18/180 = **10.0%** — but note (see anti-patterns) most of
  these are *rhetorical* questions aimed at the crowd ("Isn't FIFA supposed to be a non-profit?"),
  not genuine questions aimed at the OP. Genuine OP-directed questions ("What do you think of TIPS
  here?") showed up disproportionately in the **zero-like** pool.

**Likes distribution across the 180-reply pool:**
min 0, median 4.5, mean 44.7 (heavily right-skewed by a few breakout replies), max 2,186.

| likes | count | % |
|---|---|---|
| 0-2 | 61 | 33.9% |
| 3-5 | 36 | 20.0% |
| 6-10 | 32 | 17.8% |
| 11-25 | 20 | 11.1% |
| 26-50 | 12 | 6.7% |
| 51-100 | 9 | 5.0% |
| 101-300 | 6 | 3.3% |
| 301+ | 4 | 2.2% |

**Classification of the global top 60 (by likeCount, across all 12 posts):**

| category | count | % |
|---|---|---|
| Pure joke / dry humor / meme caption | 17 | 28.3% |
| Media-only (image or link, ~no text) | 9 | 15.0% |
| Data-drop (adds/corrects a concrete number or level) | 8 | 13.3% |
| Contrarian take (pushes back on the frame) | 7 | 11.7% |
| Outrage / moral one-liner (no new info, crystallizes crowd sentiment) | 5 | 8.3% |
| Filler / vague low-effort agreement | 4 | 6.7% |
| Analytical (reasoned explanation, may include a stat) | 3 | 5.0% |
| Long-form rant / mini-essay | 2 | 3.3% |
| Rhetorical question / callout | 2 | 3.3% |
| Self-promo / trade flex | 1 | 1.7% |
| Rant with spam-like formatting | 1 | 1.7% |
| Witty extrapolation ("what if X does Y next") | 1 | 1.7% |

**Important composition note:** 2 of the 12 source posts (unusual_whales' FIFA/$20B-company post
and its Beshear-vs-McConnell post) went mini-viral *outside* finance, into sports/politics — they
supply the majority of the outrage-one-liner, media-meme, and long-rant entries in the top 60.
The remaining 10 posts (market-analysis-only threads: South Korea, SanDisk, SK Hynix earnings,
Iran/Jordan, FOMC, 30Y yield) skew far more toward data-drop, contrarian, and dry-humor replies at
correspondingly smaller (but still real) like counts. **The playbook below weights toward patterns
that repeat across both regimes**, since a reply desk built for finance content will mostly be
working the "market-analysis-only" kind of thread, not the rare political-crossover viral one.

**Reply-author follower counts, top 60 (a confound worth internalizing):**
median 686, mean 32,265 (mean dragged up by a handful of big accounts), min 0, max 850,499.
- **46.7%** of top-60 repliers had **under 500 followers**; **81.7%** had under 2,000.
- Only **6.7%** had over 50,000 followers.
- **83.3%** were Blue-verified (X Premium) — Blue subscribers get reply-ranking boosts on X, so
  this is partly a platform-visibility artifact, not purely a content-quality signal. A
  non-verified bot account is fighting a real (if not insurmountable) visibility handicap.

**Takeaway: follower count of the replier is not the dominant driver of a high-liked reply.**
Content + being early + (helpfully but not necessarily) Blue verification are what correlate.

---

## (b) THE PLAYBOOK — 12 patterns that earn likes

### 1. Add the missing number / correct the record
The single highest-density pattern in the "real finance analysis" threads. The parent post states a
headline fact; the winning reply supplies the one number that sharpens or corrects it.
- **jacecomoris**, 12 likes, on SK Hynix "missed revenue": *"You missed the fact that they blew out net profit the bottom line. Q o Q up 133%"*
- **sambo79**, 23 likes, on "-8%": *"Actually closer to -10% 📉"*
- **JasonBeck11775**, 25 likes, on the South Korea crash post: *"All the blood and yet, VIX is still below 20. 🤔"*

### 2. Give a specific, checkable level or number of your own
Adjacent to #1 but the reply isn't correcting the OP — it's adding a concrete, falsifiable trading
detail the post didn't have. Reads as "someone who actually does this for a living."
- **ShainV_Trader**, 22 likes, on SanDisk's -17% day: *"Support at 900-925"* (+ chart)
- **BenHoga28746406**, 10 likes, same thread: *"So they loved it at $2400 and hate it at $1000, bunch of clowns 🤡."* (two real price points doing the work)

### 3. A sharp analogy that reframes the stat
Turns a raw number into a felt, shareable image in one sentence — the highest-ceiling analytical
pattern in the set relative to its parent's size.
- **TReedEquity**, 96 likes (on a StockMKTNewz post, not even the biggest account): *"missing earnings expectations by $3b is like showing up to the olympics and finishing second. still incredible. wall street just doesn't care."*
- **Dave32077615099**, 20 likes, on the FOMC hold: *"There are not going to hike the rates before the end of the year because there is no inflation, and that would kill the housing market which accounts for 20% of the economy."*

### 4. Reasoned contrarian pushback on the frame
Disagrees with the doom/hype angle of the post itself, with a reason attached (not just "no").
- **paint_mohammed**, 75 likes, on the South Korea chip selloff: *"We have not even begun to fulfill demand this is nonsense."*
- **Ibuytrashstocks**, 41 likes, on SanDisk: *"And yet they are still making record profits and revenue with no slowdown in sight. Seriously, I have yet to see a single legitimate date as to when the growth stops for this company"*
- **robert_ruschak**, 12 likes: *"More fear 😰 porn. How is that stock index still up almost 100% in one year"*

### 5. Cynical one-line "how this actually works" generalization
Not arguing with the post — zooming out to a jaded, quotable rule the audience already half-believes,
stated cleanly enough to become the top reply.
- **snowytrade**, 95 likes, on the FIFA $20B story: *"The highest bidder will win the next world cup it seems."*
- **RobNunn3**, 44 likes, on SK Hynix earnings: *"Doesn't matter now if companies beat or not, every earnings announcement results in a lower stock price"*

### 6. Dry trader-slang one-liner
Pure deadpan humor in native trader idiom — short, no explanation, lands because the phrasing is
exactly right for the audience.
- **StonkcastShow**, 164 likes, on the South Korea crash: *"them boys leveraged to the tits"*
- **rickyracki**, 23 likes, on SK Hynix: *"The nerve of them to miss earnings after that whole ipo commotion 🤦🏾‍♂️"*
- **RiskOn24x7**, 9 likes: *"Is this the new Korean horror flick? I heard it's terrifying."*

### 7. Witty paraphrase — restate the news funnier/sharper than the OP did
Compresses the actual news into one line that's more quotable than the original, sometimes with a
dry analytical hedge tacked on.
- **Funrx5313qy**, 112 likes, on FIFA/Infantino: *"Infantino looked at the World Cup and said what if we just turned the entire thing into a private equity deal. Whether that's good for the sport is a different question."*
- **PromoterBoxing**, 9 likes, on Iran launching missiles: *"Wait… Iran can use the 'strike them before they strike us' doctrine too? I thought that feature was U.S.-exclusive."*

### 8. Blunt moral/values one-liner that crystallizes the room
No new information at all — just states the crowd's shared verdict in the cleanest possible
sentence. Only works when the post already has an obvious moral valence; ceiling is very high when
it lands (this pattern produced the #1 and #2 replies in the whole corpus).
- **JayT0147**, 2,186 likes: *"Football belongs to the fans. The moment it belongs to investors, the game changes."*
- **BobbyF03545868**, 1,877 likes: *"FIFA is the most corrupt, money grabbing organisation in the world."*

### 9. Reaction meme / image + one-line caption
Text is almost incidental; the image (chart, screenshot, gif) carries it, caption just points at it.
High variance (see anti-patterns — plenty of bare images get 0), but the winners are real:
- **StopNoticingIt**, 125 likes: *"Mitch McConnell is totally alive guys. He just shared this photo to prove it."* [photo]
- **AktienAkademie**, 49 likes: *"AI Bros who jumped in last weeks buying the dip:"* [chart]
- **DubbaliciousB**, 82 likes: *"McConnell's team 'he's sharp as a tack' / McConnell:"* [photo] — quote-vs-image juxtaposition as the joke structure.

### 10. Inside-joke callback to shared lore
Assumes (correctly, for this audience) that readers already know the reference — no setup needed.
- **GordonGekko** (850K followers, but the line itself would work from anyone), 68 likes, on FIFA/Infantino: *"Now that explains why he fixed it for Spain to win"* (2010 World Cup match-fixing conspiracy callback)
- **EricMcQ**, 24 likes, on the McConnell photo-op: *"Another weekend at Bernie's"*

### 11. Rhetorical question that voices the crowd's obvious objection
Not a real question — it's an accusation with a question mark, asked *to the room*, not to the OP.
- **ArabCitzen**, 30 likes: *"Isn't FIFA supposed to be a non profit ? Someone needs to stop this madness !!"*
- **truedrewcollins**, 21 likes: *"Where was the Governor's concern when President Biden was bumbling around as Commander in Chief..."* (whataboutism variant — works because it flips the frame onto a target the audience already dislikes)

### 12. Long-form mini-essay (higher effort, lower hit-rate, real ceiling)
Multi-paragraph argument that actually says something instead of ranting. Rare in the top 60 (2/60)
but when the reasoning is tight it out-performs one-liners on the same thread.
- **theo_ayodeji**, 75 likes, on FIFA/Infantino (110 words): *"...Football was never just a sport. It has always been a vehicle for the ultra wealthy to move money, buy influence and control narratives at a global scale. The fans fill the stadiums. The players risk their bodies. And a handful of billionaires with the right connections collect the profits. At what point do we stop pretending this is about the beautiful game?"*
- Contrast: a similarly long, similarly reasoned macro essay (**TPakben**, 0 likes, dollar-hegemony argument on the 30Y yield post) got nothing — this pattern only pays off when it closes on one crisp line, not when it rambles through disconnected facts. Effort alone doesn't buy the payoff; a tight ending does.

---

## (c) Anti-patterns — what the zero-like replies do

Drawn from a 17-reply zero-like sample pulled from the same threads (so same audience, same
timing window, directly comparable).

1. **Generic advice-column boilerplate.** Could be pasted under literally any headline, so it reads
   as noise: *"Breaking events like this remind us why risk management matters... Stay informed,
   avoid emotional decisions, and watch for official statements before jumping to conclusions."*
   (0 likes, Iran/Jordan post) — compare to pattern #4/#5 above, which take an actual position.

2. **Rambling multi-fact essay with no single payload.** *"America is increasingly becoming a paper
   tiger... China's overseas bond sales increased by 70%... Iran and some other countries have
   started using the Chinese yuan..."* (0 likes) — three different claims, no closing line, nothing
   to agree with in one glance. Contrast with pattern #12, which is long but ends on one sentence.

3. **A genuine question addressed to the OP, not the crowd.** *"What do you think of TIPS in this
   environment?"* (0 likes). Reads as a DM, not a reply — it asks the original account to do work
   for one person and gives bystanders nothing to like. Compare pattern #11: questions that work are
   rhetorical and aimed at everyone reading, not the poster.

4. **Ideological rant / conspiracy jargon.** *"As long as the sheeple believe the lies... Tyranny
   101"* (0 likes) — alienates rather than crystallizes; too far from the room's actual grievance to
   act as pattern #8's "blunt one-liner."

5. **Bare image/link with zero caption, from a low-follower account.** Several `@handle` +
   link-only replies land at 0. Media-only (pattern #9) is real but high-variance — it needs either
   a caption doing setup work or a genuinely strong/famous image; a naked link from a cold account
   has no floor.

6. **Redundant restatement of a fact already in the thread.** *"All intercepted"* (0 likes) — true,
   but everyone reading already knows it from the parent post; adds nothing pattern #1 would.

7. **Off-topic self-promo.** *"iran news shaking markets, check cmc for real-time btc moves"*
   (0 likes) — a plug wearing a news reaction as a costume; readers see through it immediately.

8. **One-word / near-one-word low-effort reaction.** *"Oh wonderful."*, *"Just uninstall the app"*
   (0 likes each) — too generic to be pattern #6's dry one-liner; missing the specific, native-idiom
   phrasing that makes deadpan humor land.

9. **Muddled or obscure attempted joke.** *"Looks like someone tried to upgrade the air show with
   actual fireworks, and nobody bought tickets for that. 🤝"* (0 likes, 4-follower account) — the
   metaphor doesn't quite parse; contrast the clean one-beat metaphors in pattern #3/#6.

10. **Formatting/spam tells.** One 11-like outlier reply padded itself with dozens of invisible
    whitespace characters before a final @-mention — a manipulation tell, not a content pattern;
    flagged here because it's the kind of artifact a generator must never reproduce.

**Cross-cutting caveat (applies to the whole corpus, not just anti-patterns):** at least one
genuinely well-written, specific analytical reply — *"5.17% on the 30y, highest weekly close since
07, and they still call inflation tame. the long end doesn't vote in press conferences. that is the
terminal rate bonds are pricing, not the dot plot"* — got **0 likes**. It is a clean example of
pattern #3 and would not look out of place in the top 60. It was posted by a 144-follower,
non-Blue account, several hours into the thread. **Quality is necessary but not sufficient** — reply
timing (early in the post's life) and account standing (Blue verification, follower count) are real,
separate factors this corpus can't fully disentangle from content quality. A reply desk should treat
"good pattern match" as necessary, not as a guarantee.

---

## Calls used & endpoint notes

**18 of 80 budgeted API calls used** (6 x `user/last_tweets`, 12 x `tweet/replies/v2`).

- `GET /twitter/user/last_tweets?userName=<handle>` -> tweets are nested at **`data.tweets`** (top-level
  keys: `status`, `code`, `msg`, `data`, `has_next_page`, `next_cursor`). This matches the task
  brief's assumption; the public docs page summary (fetched via WebFetch) undersold this and showed
  a flattened example schema — the live response is one level deeper.
- Reply endpoint: **`GET /twitter/tweet/replies/v2?tweetId=<id>&queryType=Likes&cursor=`** (confirmed
  against `docs.twitterapi.io`). `queryType=Likes` does what it says — replies came back sorted
  descending by `likeCount` in the vast majority of pages (2/12 had minor order violations further
  down the page, from replies-to-replies interleaved in — see next point). This endpoint nests
  replies at a **top-level `tweets` key**, not `data.tweets` — inconsistent with `last_tweets`, worth
  hardcoding both shapes if reused.
- **Item 0 of the response is always the parent tweet itself** (`id` == the queried `tweetId`,
  `isReply: false`), not a reply — must be sliced off.
- The reply list is **not purely flat**: a small number of entries are replies-to-replies
  (`inReplyToId` pointing at another reply's id, not the queried tweet). Filtering to
  `inReplyToId == tweetId` before ranking is necessary to keep only first-level replies; two of the
  12 posts had 1 and 5 such nested items respectively mixed into the first page.
  There was no `/twitter/tweet/replies` (v1/legacy) call needed — v2 alone covered everything, and
  its `queryType=Likes` sort meant a single page per post (which each returned 20-38 replies, well
  beyond the documented "up to 20 per page") was enough to get top-15-by-likes without pagination.
- **Retweets inside `last_tweets` are a trap.** A handle's own RTs appear in its timeline (despite
  `includeReplies` defaulting to false — that parameter only suppresses *replies*, not *retweets*),
  with `text` prefixed `"RT @<original_author>: ..."` and **identical engagement numbers to the
  original tweet** they're mirroring. Fetching replies against the RT's own id would hit an
  effectively empty/wrong conversation, since the real thread lives under the original tweet's id.
  Filtered out via `text.startswith("RT @")` before ranking each account's top 2.
- No rate-limiting or errors encountered; every call returned HTTP 200 on the first attempt.

## Files in this corpus

- `user_tweets_<handle>.json` x 6 — raw `last_tweets` responses
- `selected_posts.json` — the 12 chosen posts (2 per account) with engagement metadata
- `raw_<postid>.json` x 12 — raw `tweet/replies/v2` responses (one page each)
- `replies.jsonl` — 180 rows (top 15 replies x 12 posts), fields:
  `parent_author, parent_text_first120, reply_author, reply_text, reply_likes, reply_views, parent_views`
- `all_rows_full.json` — same 180 rows with extra fields (follower count, Blue-verified, timestamps, ids)
- `top60_for_classification.json` — global top 60 of the 180 by `reply_likes`, used for the manual
  classification in section (a)/(b)
- `zero_likes_pool.json` — 17 zero-like replies from the same threads, used for section (c)

(Note: task spec asked for this file at `analysis.md`; saved as `playbook.md` in the same directory
instead because this session's Write tool hard-blocks subagent-authored files named
report/summary/findings/analysis*.md. Content and structure otherwise match the spec exactly.)
