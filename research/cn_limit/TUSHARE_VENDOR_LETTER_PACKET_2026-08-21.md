# TuShare vendor-letter packet — CN-Limit DEP-EXACT (2026-08-21)

Commissioned by `DEC:CNLI-EXACT-PLANE-REQUIRES-WRITTEN-COMMERCIAL-GRANT`
(ceo-sol, 2026-08-21). This packet is the **operator-executable** half of
closing DEP-EXACT: one letter to the vendor, plus the pre-staged (NOT
activated) procedure that turns the vendor's written reply into runtime
authority. Cash outlay expected: **¥0** (rights matrix
`research/TUSHARE_P0_ENTITLEMENT_RIGHTS_MATRIX_2026-08-19.md` §3 — the only
missing artifact is rights clarity, not a purchase).

Standing constraints, unchanged by this packet:

- `CODE_REVIEWED_AUTHORIZATION_TRUST_ALLOWLIST_SHA256 = frozenset()` and
  `BULK_HISTORICAL_BACKFILL_READY = False` in
  `collectors/china_tushare_spine.py` stay exactly as they are until their
  own separately reviewed changes in §3.
- **The DEC alone does not satisfy the runtime authorization gate.** The gate
  validates bytes (receipt JSON + grant document + allowlist + code-reviewed
  SHA-256 pin); no ruling, label, or config flag substitutes.
- No TuShare API call, no campaign dispatch, no receipt minting, no
  DEP-ID-ELIG/I1A work until §3 steps authorize them in order.
- `DNR:KILL-CN-ADJUSTED-TAPE-LEGAL-LIMIT` binds throughout.

---

## 1. The letter (operator sends; do not alter the five questions' substance)

Send from the account-holder identity to TuShare Pro support
(`tushare.pro` contact channel / vendor WeChat / email on file). The five
questions map 1:1 onto the runtime receipt's scope booleans (§2), so the
reply — if affirmative and written — is directly transcribable into the
authorization receipt. Chinese is the operative text; the English mirror is
for our records.

### 中文（发送正文）

> 您好，我是 Tushare Pro 账号 [账号ID/注册手机或邮箱] 的持有人。我们计划在
> 公司内部量化研究及一个商业化数据产品中使用贵方接口数据（主要为
> `daily`、`daily_basic`、`stk_limit`、`suspend_d`、`stock_st` 等积分内
> 权限接口）。为合规使用，烦请以书面形式确认以下五点：
>
> 1. **账户类别**：当前账号按贵方分类属于个人账户还是机构/公司账户？若我们
>    以公司主体使用，需要何种账户类别或书面授权？
> 2. **API 访问与本地批量留存**：是否允许通过 API 获取上述接口数据，并在
>    我方内部以追加方式**批量本地留存多年历史**（仅内部存储，不对外提供
>    原始数据）？
> 3. **量化研究与内部衍生**：是否允许将上述数据用于**量化策略研究**及生成
>    仅供内部使用的衍生指标/信号？
> 4. **商业化衍生展示**：是否允许在我方**商业化**面板/产品中展示由上述数据
>    **加工得到的衍生结果**（统计量、计数、状态标签等，非原始行情行）？
> 5. **限制条款**：关于**原始数据再分发**（我方默认理解为禁止）、**留存期限**、
>    以及**云端/服务器部署访问**（自建服务器调用与存储），贵方有哪些书面限制？
>    如商业使用需机构合同，请一并提供机构合同条款与报价。
>
> 请以可存档的书面形式（邮件正文或盖章文件）回复，我们将据此存档合规凭据。
> 谢谢！

### English mirror (records only)

> I am the holder of Tushare Pro account [account id]. We plan to use API
> data (principally `daily`, `daily_basic`, `stk_limit`, `suspend_d`,
> `stock_st` within our credit tier) for internal quantitative research and
> in a commercial data product. Please confirm in writing:
>
> 1. **Account class** — is this account classified personal or
>    institutional/company? If we operate as a company, what account class or
>    written authorization is required?
> 2. **API access + bulk local retention** — may we fetch these endpoints via
>    the API and retain multi-year history locally in bulk, append-only,
>    internal-only, never redistributing raw rows?
> 3. **Quantitative research + internal derivatives** — may the data be used
>    for quantitative strategy research and internal-only derived
>    indicators/signals?
> 4. **Commercial derived outputs** — may a commercial dashboard display
>    derived results (statistics, counts, state labels — never raw rows)
>    built from these data?
> 5. **Restrictions** — what written restrictions apply to raw
>    redistribution (our default reading: forbidden), retention duration, and
>    cloud/server deployment access (self-hosted server calls and storage)?
>    If commercial use requires an institutional contract, please provide its
>    terms and price.
>
> Please reply in archivable written form (email body or stamped document).

---

## 2. What the reply must contain to count as a grant

The runtime gate (`load_authorization_grant`,
`collectors/china_tushare_spine.py`) accepts only a receipt with schema
`cn_tushare_written_authorization.v1` — exactly these keys:
`schema_version, authorization_id, vendor, grantee, grantor, granted_by,
issued_on, expires_on, grant_document_path, grant_document_sha256,
entitlement_chain, scope` — where `scope` carries all seven booleans
(`AUTHORIZATION_RECORDED_SCOPE`) and the five **required** ones must be true:

| Receipt scope boolean (required=true) | Satisfied by letter question |
|---|---|
| `api_access` | Q2 (API access affirmed) |
| `bulk_local_retention` | Q2 (multi-year append-only local retention affirmed) |
| `quantitative_strategy_research` | Q3 |
| `commercial_use` | Q1 + Q4 (account class permits it, or institutional grant obtained) |
| `private_internal_derivatives` | Q3 |

Recorded-only booleans (may be false): `redistribution` (expected **false**
per Q5 — false is fine, we never redistribute raw rows),
`public_derivatives` (Q4's answer; recorded honestly).

Validity requirements the gate enforces mechanically: `vendor` ∈
{tushare, tushare pro}; `granted_by` ∈ {vendor, institution};
`issued_on ≤ collection date ≤ expires_on`; `grant_document_sha256` must
match the stored grant bytes; a `granted_by: institution` receipt must carry
the full entitlement chain (vendor→institution entitlement + institution→us
delegation documents, each SHA-256-verified); a direct vendor grant must
leave the chain null. **A reply that answers "personal account,
non-commercial only" is a NO** — then the path is the institutional
contract in Q5, and DEP-EXACT stays waiting; do not shade a negative answer
into a receipt.

---

## 3. Pre-staged post-grant procedure (STAGED, NOT ACTIVATED)

No step below is authorized until the previous one's artifact exists and its
review concluded. Nothing here is running today.

1. **Private written grant** — archive the vendor reply bytes verbatim in the
   private store (never this public repo; the repo is public —
   `prophet-book-public-git-twin` blast radius applies to any private doc).
2. **Authorization receipt** — transcribe into a
   `cn_tushare_written_authorization.v1` JSON whose
   `grant_document_sha256` = SHA-256 of the archived grant bytes. No receipt
   without a grant document that hashes.
3. **Independent allowlist** — a separate
   `cn_tushare_authorization_trust_allowlist.v1` file (distinct path from
   the receipt; the gate refuses `trust_path == receipt_path`).
4. **Reviewed trust-root pin** — ONE reviewed code change adding the
   allowlist file's exact SHA-256 to
   `CODE_REVIEWED_AUTHORIZATION_TRUST_ALLOWLIST_SHA256`. This is the only
   lawful way the frozenset gains a member (no CLI/env mint).
5. **Licensed live canary** — campaign lane `mode=plan` first, then one
   bounded `mode=execute` window; exact-schema parity + throughput receipts.
6. **Canary review** — adversarial review of the canary receipts (opus
   `reviewer` per model routing) before any scale-up.
7. **Separately reviewed READY flip** — a second, independent reviewed code
   change flipping `BULK_HISTORICAL_BACKFILL_READY = True`, citing the
   canary receipts. Never combined with step 4's change.
8. **Range-shard campaign** — authorized bulk backfill across the full-A
   `daily × daily_basic × stk_limit × suspend_d × stock_st` range shards.
9. **Completeness manifest** — sanitized (no token, no identity/path text)
   manifest closing every contract gate; this is the artifact that flips
   DEP-EXACT to done and opens DEP-ID-ELIG (jointly with the already-closed
   DEP-CAI).

Failure semantics: a red `execute` run before step 4 concludes is the gate
working, not a defect. A vendor "no" at step 1 returns the question to the
operator (institutional contract or program stop) — never to a coding
workaround.

---

## 4. Exact operator action

Send §1's Chinese letter from the account-holder identity. That is the whole
action. When a written reply exists, hand its bytes to a records session to
run §3 steps 1–4 under normal review; everything after is gated on those
artifacts.
