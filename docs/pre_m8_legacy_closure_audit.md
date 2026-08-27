# PRE-M8 Legacy Closure Master Audit Report

Audit date: 2026-08-25

## 1. Executive Summary

The M0-M7.6 product baseline is broadly coherent: Excel remains the authoritative business store, Creator and Account identity is stable, multi-account behavior is implemented, the normal Feishu write surface is singular, M7.6 chat is packaged, and the current post-reset workbook has no detected orphan references.

M8 entry is not yet safe. One evidence-backed blocker remains:

1. Synthetic scale measurements crossed the formal SQLite/read-index trigger by a wide margin. Medium reads took 17-34 seconds and a common write took about 272 seconds in an earlier valid run.

PRE-M8 P0-C Batch 1 established C0-C3, and Batch 2 implements C4-C10:
runtime repository compatibility over SQLite authority, explicit factory selection,
Dashboard revision cache, Feishu/Assistant integration, backup/restore/export/import,
and Clean Reset. Synthetic runtime cutover is validated; no production migration
or activation has occurred. C11-C12 engineering gates now pass; production
migration remains a separate human-authorized acceptance step.

PRE-M8 Closure Phase 1 closed the other two P0 findings. Task byte writes now use the shared unique-temp/fsync/atomic-replace implementation with bounded Windows contention retry. Creator hard delete now persists a secret-free Feishu delete intent before local commit and reconciles remote Account records before the Creator with durable retry, progress, idempotency, and fail-closed identity checks.

The current production workbook is a valid small post-reset library, not the historical 2,453-Creator dataset. No real Feishu mutation, Full Sync, Creator mutation, or Campaign mutation was performed. The closure build produced a fresh PyInstaller EXE in the packaging dist directory, but release replacement was blocked because two running KOLConnect processes held the existing release EXE open.

## 2. Baseline

- HEAD: `da31ea887cd457308e36978ef4f17388388efc40`
- origin/main: `da31ea887cd457308e36978ef4f17388388efc40`
- HEAD == origin/main: YES
- Commit: `da31ea8 Complete M7.6 Feishu chat assistant and real chat hotfixes`
- Working tree before audit: no tracked changes
- M7.6 dirty state: NO; M7.6 is committed
- Audit-created tracked artifacts: this document and `docs/pre_m8_storage_architecture.md`
- Audit benchmark sandbox cleanup: blocked by managed filesystem policy; `.pre_m8_benchmark_sandbox/` remains untracked and must not be committed

## 3. Current Production Data

Read-only inspection of `%APPDATA%/KOLConnect/Creator_Library.xlsx`:

| Sheet | Rows |
|---|---:|
| Creators | 4 |
| CreatorAccounts | 6 |
| Videos | 0 |
| VideoSnapshots | 0 |
| Campaigns | 1 |
| CampaignCreators | 3 |
| CreatorSnapshots | 6 |
| Insights | 0 |
| Products | 1 |
| Cooperations | 0 |
| FollowUpLogs | 0 |
| Agencies | 0 |
| AgencyContacts | 0 |
| `_AnalysisData` | 4 |
| `_Metadata` | 4 |

Workbook size: 17,560 bytes.

`POST_RESET_SMALL_LIBRARY = YES`

Identity checks found unique non-empty Creator and Account IDs and zero orphan references in CreatorAccounts, CampaignCreators, CreatorSnapshots, and VideoSnapshots.

## 4. Historical vs Current Data Boundary

The historical 2,453-Creator / roughly 2,392-account evidence predates Clean Reset and is useful only for capacity history. It is not the current restore target and must not be treated as missing production data. The authoritative current baseline is 4 Creators, 6 Accounts, 1 Campaign, and 3 CampaignCreator relations.

## 5. Evidence Method

Evidence was taken from current code, tests, Git history, packaged artifacts, read-only production workbook inspection, runtime logs, deterministic focused tests, the canonical Python runner, the unified frontend runner, static checks, and isolated synthetic workbooks. No conclusion relies only on milestone labels or comments.

Status vocabulary is restricted to: `DONE`, `CLOSED_BY_DESIGN_DECISION`, `ENGINEERING_DONE_USER_ACCEPTANCE_PENDING`, `PARTIAL`, `MISSING`, `OBSOLETE_SUPERSEDED`, `EXPLICITLY_DEFERRED`, and `NOT_APPLICABLE`.

## 6. Historical Inventory

| Status | Count |
|---|---:|
| DONE | 22 |
| CLOSED_BY_DESIGN_DECISION | 1 |
| ENGINEERING_DONE_USER_ACCEPTANCE_PENDING | 1 |
| PARTIAL | 5 |
| MISSING | 0 |
| OBSOLETE_SUPERSEDED | 2 |
| EXPLICITLY_DEFERRED | 3 |
| NOT_APPLICABLE | 0 |

Total classified items: 34. Unresolved items, defined as every item not `DONE`, `CLOSED_BY_DESIGN_DECISION`, `OBSOLETE_SUPERSEDED`, or `NOT_APPLICABLE`: 9.

## 7. M0-M1 Foundation

Status: `DONE`.

- `Creator_Library.xlsx` is the authoritative Creator/business store.
- JSON stores hold settings, mail state, task documents, data protection, and staged-delete manifests; none is a second Creator authority.
- Workbook mutation is guarded by the shared process-local and OS-backed storage lock.
- `runtime_paths.atomic_write_json()` uses unique sibling temp files, flush/fsync/close, atomic replace, and bounded Windows retry for WinErrors 5, 32, and 33.
- Workbook open can apply an intentional schema migration and save. Audit reads used read-only workbook access to avoid mutation.
- `TaskRepository` byte writes now delegate to the hardened unique sibling temp, flush/fsync/close, atomic replace, cleanup, and bounded Windows WinError 5/32/33 retry implementation.

## 8. M2 Architecture

`M2_6_ARCHITECTURE_CLOSED = YES` for the frozen task/creator lifecycle scope.

- Task runtime, finalizing, summary reads, manual compatibility, and review documents flow through TaskService/ports/TaskManagerAdapter.
- No prohibited direct TaskManager persistence calls remain in the server contract.
- Residual broader debt: campaign handlers still use repository-factory entries directly, and settings mail flow uses an injected mail module rather than a formal service port.
- Disposition: `EXPLICITLY_DEFERRED`. Reopen when those handlers are changed by M8. M8 does not currently require their redesign.

Special decision H: `SAFE_FOR_M8`; the independent Task atomic-write P0 is closed.

## 9. ChromeDriver

Status: `OBSOLETE_SUPERSEDED`.

`app/chromedriver_resolver.py` delegates version-compatible resolution to `webdriver_manager.chrome.ChromeDriverManager().install()`, validates the resulting path, and returns user-safe errors. Windows and macOS packaging collect `webdriver_manager`.

Special decision B: `SUPERSEDED`. A custom auto-match subsystem should not be implemented.

## 10. M3.1 TikTok

Original audit status: `PARTIAL`. Subsequent status: `CLOSED_BY_DESIGN_DECISION`.

- Passive MAIN-world capture protocol, bridge, sanitized item-list parser, fixture, and focused tests exist.
- Authoritative fixture: `tests/fixtures/tiktok/item_list_normal.json`; it is a sanitized, structure-preserving observed `/api/post/item_list/` sample.
- Parser coverage includes video identity, title/description, create time, play/like/comment/share counts, and missing-vs-zero semantics.
- No complete production subscriber/import path from the passive bridge into the normal capture pipeline was found.

Subsequent product decision: the old M3.1 contract is retired. Production manifest wiring is
disabled; parser/fixture/bridge artifacts remain experimental reference. Any passive capture V2 is
a new post-M8 project documented separately.

## 11. M3.4 / T3

Status: `DONE`.

M3.4 completion: 5/5. T3 completion: 5/5.

Evidence covers task-result field enrichment, bundled Creator/Account writes, one-load/one-save batch behavior, idempotent account update, orphan-account repair, bulk Creator import, batch Campaign association, validation, partial-failure reporting, multi-account preservation, and UI regressions.

## 12. M3.5 Quote / Cost

Status: `DONE` for the PRE-M8 monetary identity and pricing-composition scope.

`CampaignCreators` persists `quote_currency`, `quote_unit_amount`,
`quote_quantity`, `quote_unit`, total `creator_quote`, total `cost`, and
`cost_currency`. Structured quotes enforce total = unit amount x positive integer
quantity. Legacy total-only rows remain readable without invented currency,
quantity, or unit. Currency-aware aggregation groups known currencies and suppresses
the scalar total when unlike or known/unknown currency groups coexist. FX conversion,
accounting, approval, negotiation history, and payment processing remain explicit
non-goals rather than hidden quote-contract debt.

Current production data contains 2 rows with `creator_quote` and 2 rows with `cost`; both lack currency.

`ZERO_QUOTE_ROWS_EXPECTED = NO`

Special decision D: `CLOSED`. Quote/cost semantics and currency identity are frozen;
mixed-currency silent aggregation is prohibited without introducing FX.

## 13. Creator / Account Identity

Status: `DONE`.

- Creator cross-system identity: `creator_id`.
- Account identity: `account_uid`.
- Names, handles, platform, and profile URLs are matching/display inputs, not authoritative cross-system keys.
- IDs survive archive/restore and account changes.
- Current workbook identity checks: unique/non-empty Creator IDs YES; unique/non-empty Account IDs YES; orphan Account references 0.

## 14. Multi-Account

Status: `DONE`.

One Creator to many Accounts is supported in Creator detail, Campaign selection, Campaign relation `account_ids`, Feishu Creator-Account relations, assistant rendering, merge, and hard delete. Campaign membership remains one CampaignCreator row per Creator/Campaign; account selection does not duplicate the Creator. Intelligence and assistant views do not sum followers across accounts.

## 15. Mail Relation Parser

Status: `DONE`.

`mail_sync._relation_record_ids()` delegates to the shared Feishu relation parser. It accepts singular and plural record IDs, list and nested-value shapes, preserves order, and de-duplicates. Display text is not treated as identity. Focused parser tests passed 2/2.

## 16. Hard Delete

Local hard delete status: `DONE`.

The local flow includes preview/confirmation, shared mutation locking, workbook backup, durable transaction manifest, artifact quarantine, workbook/JSON mutation, rollback before commit, cleanup-pending semantics after commit, and recovery. It covers Creators, Accounts, Videos, Insights, analysis data, snapshots, CampaignCreators, FollowUpLogs, task artifacts, and protected legacy references. Legacy Cooperations are scanned as dependencies rather than silently fabricated or ignored.

Remote Feishu propagation status: `DONE`.

Hard delete durably prepares a secret-free external-delete intent before local transaction preparation, promotes it only after local commit, and aborts it on local rollback/failure. Local commit remains independent of remote availability. Startup recovery resolves interrupted local outcomes and performs a bounded reconciliation pass. Reconciliation verifies exact Creator/Account identities, deletes Accounts before the Creator, persists partial progress, treats known absence as converged, retries transient failures with a bounded schedule, blocks auth/config/permission/schema/ambiguity failures, and never caches secrets or raw remote payloads.

Special decision C: `CLOSED_BEFORE_M8`. Local deletion commits independently while the durable intent remains until remote removal is proven or explicit operator action resolves a blocked state.

## 17. Feishu Sync

Status: `DONE` for current one-way synchronization scope.

- Authoritative source remains KOLConnect/Excel; Feishu is a replica.
- The normal product workflow is Settings Validate -> Dry Run -> confirmed Full Sync.
- Active production business-write workflow count: 1 logical workflow.
- Capture/task-result direct Feishu write UI and route are retired.
- Full Sync rebuilds the plan at execution, preserves non-destructive merge behavior, and retains batch-stop safety.
- Relation schema validation supports legacy type 18 and validated bidirectional type 21 with linked-table identity checks.
- Multi-account planning is covered and second Dry Run is idempotent.

## 18. Historical M7.1d / Clean Reset

Clean Reset is the current supported clean-baseline mechanism. It backs up the workbook before clearing business data and preserves workbook schema/metadata, Chrome configuration, mail accounts, and Feishu configuration.

Historical account/Creator identity backfill and unmanaged-Creator cleanup UI/routes are retired from the normal product. Their six unregistered service/handler modules and three legacy-only test files were physically removed after confirming zero runtime, support, recovery, dynamic-import, CLI, and packaging dependencies.

Special decision K: `SUPERSEDED_BY_CLEAN_RESET`.

Special decision K closure: `CLOSED`. Clean Reset remains the supported workflow.

## 19. Feishu Chat M7.6

Status: `DONE`.

- Official `lark-oapi==1.7.2` long-connection transport is packaged.
- Runtime includes readiness signaling, a 20-second connecting watchdog, generation isolation, controlled reconnect, shutdown/disconnect, deduplication, safe result rendering, and confirmation cancellation.
- Current runtime logs show successful connection transitions, including 2026-08-25 15:54:46 connecting -> 15:54:57 connected.
- Prior real acceptance evidence covers message receive/send, Creator and multi-account detail, Dry Run rendering, and confirmation gating without Full Sync.

Special decision G: `ENGINEERING_DONE`. The earlier stuck-connecting observation is obsolete after the M7.6a readiness/watchdog fix and current connected runtime evidence.

## 20. Assistant / OpenClaw

Assistant status: `DONE`. OpenClaw runtime status: `CLOSED_BY_DESIGN_DECISION`.

Assistant tools are allowlisted and service-mediated. There is no direct workbook, filesystem, shell, generic HTTP, or Bitable access from chat. Full Sync uses the same confirmation-gated Feishu service. `ASSISTANT_BYPASS = NO` and `DIRECT_BITABLE_ACCESS_FROM_CHAT = NO`.

OpenClaw is retired from active product architecture by explicit product decision. The canonical AI path is User / Feishu -> Feishu long-connection transport -> KOLConnect Assistant -> allowlisted tools/services. No OpenClaw host, authentication, or transport deployment is required, and M8 does not depend on OpenClaw. Existing OpenClaw material is historical/reference-only.

## 21. Normalization

Status: `DONE` for current analytics/intelligence scope.

`app/domain/normalization.py` centralizes supported country aliases, follower/number normalization, compact display, and tag normalization. Unknown regions are not guessed. Missing/invalid metrics remain unavailable. Compatibility parsers that remain in scraper/frontend serve ingestion or presentation boundaries rather than becoming a second authoritative analytics normalization layer.

## 22. User Tags / AI Tags

Status: `DONE`.

User tags are persisted in `Creators.tags`. AI tags are deterministic, derived category/platform labels returned separately as `ai_tags`; they are not written over user tags. Creator Intelligence exposes `user_tags` and `ai_tags` independently.

## 23. Creator Intelligence

Status: `DONE`.

The service produces factual, per-account summaries with explicit freshness, confidence, and limitations. It does not sum followers across accounts, fabricate missing metrics, expose sensitive contact/cost/quote data, or claim predictive pricing. Price readiness is reported only as recorded-data availability.

## 24. Campaign

Core status: `DONE`.

Campaign detail safely supports empty/optional data, stale Creator references, multi-account Creator selection, one relation per Creator, and create-to-detail round trips. CampaignCreators retain account IDs and planned publish dates.

Actual publication engineering is complete in schema v3: one record per deliverable with stable
publication identity, optional actual CreatorAccount, actual published timestamp, independent
observation timestamp, legacy-link compatibility, and distinct planned fields. Packaged manual UI
acceptance remains pending.

## 25. Desktop Save As

Status: `DONE`.

The pywebview bridge restricts writes to user-selected `.xlsx` paths, sanitizes suggested names, strictly decodes base64, reports cancellation/failure, and preserves browser Blob fallback. Unit/frontend coverage exists.

The user subsequently accepted all four packaged Windows cases: template Save As,
Creator export Save As, cancellation, and a path containing Chinese characters and
spaces. No known code or acceptance gap remains.

Special decision I: `CLOSED`.

## 26. Dashboard Cold Start

Status: `DONE`.

The response cache, fingerprint/date invalidation, immutable copies, double-check locking, mutation invalidation, packaged-runtime migration ordering, and concurrent cold-start fix are committed and packaged. The canonical ONEDIR release passed portability and isolated packaged startup checks. Real Windows manual acceptance confirmed that Dashboard was visible and usable; normal desktop close exited and released port 8765.

Special decision I-2: `CLOSED_BY_EXISTING_ACCEPTANCE_EVIDENCE`. The historical contract did not require a sub-five-second threshold, reboot, or additional cold-start cycle.

## 27. Excel Performance Benchmark

Synthetic workbooks were isolated from production. Timings are wall-clock milliseconds. Read values are medians of repeated measurements; write trigger evidence includes the completed small test and an earlier valid medium run.

| Dataset | Workbook size | Workbook open | Creator Library | Creator Detail | Campaign Detail | Dashboard projection | Common write | VideoSnapshot write |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Current production: 4 C / 6 A | 17,560 B | 6.72 | 15.29 | 13.27 | 26.07 | 14.28 | not mutated | not mutated |
| Small: 100 C / 150 A / 500 CS / 20 campaigns / 100 relations / 1,000 VS | 124,907 B | 11.78 | 227.59 | 218.94 | 1,575.86 | 869.32 | 1,593.37 | 1,397.49 |
| Medium: 2,500 C / 3,000 A / 5,000 CS / 500 campaigns / 2,000 relations / 25,000 VS | 2,280,416 B | 29.03 | 16,975.74 | 18,307.09 | 34,372.94 | 18,162.64 | about 272,000 in an earlier valid run | not repeated |
| Large: 10,000 C / 12,000 A / 20,000 CS / 2,000 campaigns / 8,000 relations / 100,000 VS | 9,143,644 B | 21.12 | 64,445.60 | 62,020.26 | 126,865.93 | 71,928.15 | skipped after trigger | skipped after trigger |

The low lazy workbook-open number does not mean repository reads are cheap; repository paths materialize and repeatedly scan sheets. The medium and large results are architectural, not merely file-size effects.

Special decision F: `TRIGGERED`. A read index/persistence architecture, expected to be SQLite-backed, is required before data-heavy M8 features. Excel remains the source of truth until a separately approved migration contract exists.

## 28. VideoSnapshot Scale Readiness

Status: `CLOSED_BY_DESIGN_DECISION`.

VideoSnapshot is retained historical time-series data. Same-snapshot children are
deterministically replaced, identity and latest/history indexes are explicit, and
the 100,000-row SQLite benchmark establishes the current local-product boundary.
No speculative TTL is required; retention is reconsidered only after measured
production scale or query evidence crosses that boundary.

## 29. Test Infrastructure

Status: `DONE` for the repository hygiene contract.

The canonical `scripts/run_python_tests.py` isolates APPDATA, LOCALAPPDATA, TEMP/TMP/TMPDIR, locks, settings, backups, and runtime state. It does not leak production paths in the observed run. Raw direct unittest commands remain unreliable in the managed Windows environment, and many historical ignored fixture directories have permission-denied cleanup residue.

Special decision J: `CLOSED`. Canonical production-path isolation is mandatory,
and the known manual diagnostic/acceptance paths are narrowly ignored and
documented without hiding source or release configuration.

The audit benchmark directory could not be removed because managed policy rejected the verified recursive target. It is untracked, not a product artifact, and must be excluded from any commit.

## 30. Frontend Harness

Status: `DONE`.

The unified runner recursively discovers frontend tests. Result: 40 files passed. Extension syntax validation passed for 24 source files. An additional all-JavaScript syntax pass covered 79 `.js`/`.mjs` files in webapp, extension, and tests with no failure.

## 31. Packaging

Status: `DONE` for current Windows/M7.6 engineering scope.

- Windows and macOS specs collect webapp, assets, extension resources, pywebview, Selenium, webdriver-manager, and lark-oapi runtime modules.
- Build requirements pin the official Feishu SDK.
- PyInstaller inventory includes M7.6 chat service/transport, `lark_oapi.channel`, websocket/http dependencies, and crypto dependencies.
- Release artifact: `release/KOLConnect_v0.2.3.exe`
- Size: 99,048,818 bytes
- Timestamp: 2026-08-25T15:49:56.7320015+08:00
- SHA256: `34AA08D8A6CA0BB15BC9C242DFD8750EFDDEC088DA2960F4501D9151AFD0472E`

No build was performed by this audit.

## 32. Outlook

Status: `CLOSED_BY_DESIGN_DECISION`.

Current mail authentication is standard IMAP/SMTP password or app-password authentication where
the provider permits it. Microsoft OAuth2 and guaranteed Outlook/Microsoft 365 compatibility are
not current product contracts. Future OAuth2 work is a new feature, not PRE-M8 legacy debt.

## 33. Security

Status: `DONE` for the audited local product boundary.

Desktop/browser runtime binds to `127.0.0.1`; Host/Origin policy guards browser mutations. Feishu chat uses long connection and requires no public callback. No 0.0.0.0 listener, arbitrary file API, direct assistant workbook access, generic HTTP proxy, or secret exposure was found in the audited contracts.

## 34. Privacy

Sensitive email, phone/WhatsApp, notes, quote/cost, credentials, tokens, filesystem paths, workbook payloads, and mail bodies are excluded from assistant safe projections and normal Feishu Creator sync scope. UI rendering uses structured/sanitized data rather than exposing secrets. No real external payload was emitted during the audit.

## 35. API / OpenAPI Drift

Status: `DONE` for supported public contracts.

Focused OpenAPI tests passed 3/3 and verify key public routes plus retired-route absence. Feishu chat control endpoints are intentionally internal UI endpoints documented in the API reference rather than promoted as public OpenAPI contracts. No unsupported alias or second public mutation contract was found.

## 36. Legacy Route Audit

Normal registered handler groups include assistant, analytics, dashboard, risk, campaign, Feishu chat, Feishu sync, clean reset, settings, Creator, and task. Legacy identity-backfill and unmanaged-cleanup runtime modules are physically removed and absent from normal UI. Capture-page direct Feishu business sync is retired.

Disposition for dead modules: `DONE`; six modules and three legacy-only test files were removed after confirming no runtime, support, recovery, dynamic-import, CLI, or packaging dependency. Clean Reset remains supported. Priority P3, non-blocking.

## 37. Git Closure Audit

- HEAD equals origin/main.
- No commit, push, tag, or reset occurred.
- Product and focused test changes are restricted to PRE-M8 Closure Phase 1; no schema, dependency, or packaging configuration changed.
- The canonical build was run. PyInstaller completed, but copying over the release EXE was blocked by two running instances of that EXE.
- `.pre_m8_benchmark_sandbox/` is an audit-created untracked directory whose cleanup was denied by managed policy; it must remain unstaged and be removed in a normal local environment.

## 38. Regression

| Gate | Result | Classification |
|---|---|---|
| Canonical full Python run #1 | 669 run, 1 skipped, 0 failures | PASS; 257.919s |
| Canonical full Python run #2 | 669 run, 1 skipped, 0 failures | PASS; 273.034s |
| Batch-2 final Python run #1 | 707 run, 1 skipped, 0 failures | PASS; 369.830s |
| Batch-2 final Python run #2 | 707 run, 1 skipped, 0 failures | PASS; 371.824s |
| SQLite runtime cutover focused | 18/18 passed | PASS: authority, transactions, indexed Creator detail, lifecycle and integrations |
| Task atomic-write focused | 8/8 passed | PASS: concurrency, cleanup, binary/empty, unique temp, WinError 5/32/33 retry |
| Feishu delete intent/reconcile focused | 24/24 passed | PASS: lifecycle, retry, idempotency, partial progress, identity and archive/restore/merge safety |
| M4.6 safety | 50 passed, 1 skipped | PASS |
| M7.1 Feishu | 121/121 passed | PASS |
| M7.3 Assistant | 23/23 passed | PASS |
| M7.6 Chat | 43/43 passed | PASS |
| M6 | 33/33 passed | PASS |
| M5 Dashboard/Analytics | 73/73 passed | PASS |
| M7.2 OpenAPI | 3/3 passed | PASS |
| M7.2 mail relation parser | 2/2 passed | PASS |
| M3.1 passive bridge/parser JS | passed | PASS |
| Unified frontend | 40 files passed | PASS |
| All project JS syntax | 74 files passed | PASS |
| `python -m compileall app` | passed | PASS |
| `git diff --check` | passed | PASS |
| Canonical Windows build | PyInstaller EXE created; release copy blocked | ENVIRONMENT BLOCKED: running release EXE holds target file |

The former full-Python TaskRepository failure was a real Windows product race and is now closed by the shared hardened atomic-byte writer plus deterministic and repeated full-suite evidence.

## 39. External Mutation Verification

- Real Feishu create: 0
- Real Feishu update: 0
- Real Feishu delete: 0
- Real Feishu message: 0
- Real Full Sync: NOT RUN
- Real Clean Reset: NOT RUN
- Real Creator/Campaign/task mutation: 0
- Build: PYINSTALLER PASS; RELEASE COPY BLOCKED BY RUNNING EXE

## 40. Special Decisions A-K

| Decision | Result | Reason |
|---|---|---|
| A. TikTok M3.1 | RETIRED | Old incomplete production wiring disabled; retained artifacts are experimental reference for a new post-M8 V2 project |
| B. ChromeDriver Auto Match | SUPERSEDED | webdriver-manager is the supported implementation |
| C. Hard Delete Propagation | CLOSED_BEFORE_M8 | Durable intent, recovery, retry, reconciliation, progress, and safe status are implemented and tested |
| D. M3.5 Quote Management | CLOSED | Currency, unit amount, quantity, pricing unit, total quote, and total cost semantics are implemented without FX |
| E. Microsoft OAuth2 | CLOSED_BY_DESIGN_DECISION | Not part of current mail contract; future OAuth2 is a new feature |
| F. SQLite | TRIGGERED | Medium reads/writes exceed formal thresholds |
| G. Feishu Chat | ENGINEERING_DONE | Current package/logs and prior real acceptance support closure |
| H. M2.6 Architecture | SAFE_FOR_M8 | Frozen port boundaries are complete; broader handler debt is trigger-scoped |
| I. Desktop Save As | CLOSED | Unit/UI engineering plus four packaged Windows acceptance cases pass |
| J. Test infrastructure | CLOSED | Canonical runner isolates production paths; cleanup hygiene remains |
| K. Historical M7.1d Gavin cleanup | SUPERSEDED_BY_CLEAN_RESET | Legacy product UI/routes retired |

## 41. PRE-M8 Closure Queue

| Order | Item | Current status | Priority | M8 blocker | Closure contract |
|---:|---|---|---|---|---|
| 1 | TaskRepository Windows atomic bytes | DONE | P0 | NO | Closed: shared hardened atomic writer, 8/8 focused tests, two 669-test canonical runs |
| 2 | Feishu permanent-delete propagation | DONE | P0 | NO | Closed: durable intent/outbox, recovery, idempotent retry, progress, status, and reconciliation |
| 3 | Excel scale/read-index architecture | C0_C12_ENGINEERING_COMPLETE | P0 | NO | Human review, then separately authorize production migration acceptance |
| 4 | Dashboard packaged cold acceptance | CLOSED | P1 | NO | Closed by current ONEDIR portability plus real Windows manual acceptance: Dashboard usable, normal close exited and released port 8765 |
| 5 | Desktop Save As acceptance | CLOSED | P2 | NO | User accepted packaged template, export, cancellation, and Chinese/space-path Save As cases |
| 6 | M3.1 passive TikTok runtime integration | CLOSED_BY_DESIGN_DECISION | P1 | NO | Production manifest wiring retired; experimental components retained for post-M8 V2 revalidation |
| 7 | M3.5 quote/currency contract | CLOSED | P1 | NO | Monetary identity and pricing composition implemented; FX remains out of scope |
| 8 | VideoSnapshot retention/index strategy | CLOSED_BY_DESIGN_DECISION | P1 | NO | Retain historical time series at the demonstrated local-product scale |
| 9 | Test artifact cleanup hygiene | CLOSED | P2 | NO | Canonical sandbox self-cleans and narrow manual diagnostic paths are ignored/documented |
| 10 | Campaign/settings service-boundary debt | CLOSED_BY_DESIGN_DECISION | P2 | NO | Existing injected application-coordinator boundary is documented and contract-tested |
| 11 | OpenClaw deployed runtime | CLOSED_BY_DESIGN_DECISION | P2 | NO | OpenClaw retired; Assistant + Feishu transport is canonical and requires no OpenClaw deployment |
| 12 | Actual published-content account/date model | PARTIALLY_CLOSED | P1 | YES | Engineering complete with schema v3/API/UI/tests; packaged manual UI acceptance pending |
| 13 | Microsoft OAuth2 | CLOSED_BY_DESIGN_DECISION | P2 | NO | Current contract is standard IMAP/SMTP; future OAuth2 is a new feature |
| 14 | Dead legacy backfill/cleanup modules | CLOSED | P3 | NO | Six runtime modules and three legacy-only tests removed after zero-dependency audit |

## 42. M8 Blockers

Under the current strict zero-legacy-debt gate, M8 remains blocked only by item #12 manual
acceptance. Items #1-#11, #13, and #14 are closed. Storage item #3 is closed
by its separately accepted production migration work and is not reopened here.

## 43. Remaining Unresolved Items

- Actual publication account/date model: engineering complete; packaged manual UI acceptance pending.

## 44. User Acceptance Queue

No PRE-M8 Save As acceptance remains. The user accepted template, Creator export,
cancellation, and Chinese/space-path behavior in the packaged Windows application.
Feishu Chat is not listed because current runtime connection logs and prior real chat acceptance provide closure evidence. No Full Sync is required for this audit.

## 45. Final Legacy Matrix

| ID | Historical Item | Current Status | Evidence | Priority | M8 Blocker | Closure |
|---|---|---|---|---|---|---|
| L01 | Excel business authority | DONE | Workbook/repository/config audit | P0 | NO | Keep contract |
| L02 | Shared lock and atomic JSON | DONE | lock/runtime_paths code and tests | P0 | NO | Keep contract |
| L03 | Task document atomic bytes | DONE | Hardened shared atomic writer; 8/8 focused and two 669-test full runs | P0 | NO | Keep contract |
| L04 | M2.6 task/creator boundaries | DONE | ports/adapters/static tests | P0 | NO | Keep contract |
| L05 | Campaign/settings handler boundaries | CLOSED_BY_DESIGN_DECISION | injected application-coordinator contract and bypass tests | P2 | NO | Keep contract |
| L06 | ChromeDriver matching | OBSOLETE_SUPERSEDED | webdriver-manager resolver | P2 | NO | No custom subsystem |
| L07 | M3.1 TikTok passive capture | CLOSED_BY_DESIGN_DECISION | production wiring retired; parser/fixture retained as experimental reference | P1 | NO | Future V2 is a new project |
| L08 | M3.4/T3 batch foundation | DONE | focused batch/import/Campaign tests | P1 | NO | Keep contract |
| L09 | M3.5 quote management | DONE | structured quote/cost currency contract, v2 migration, mixed-currency-safe aggregation | P1 | NO | Keep contract |
| L10 | Creator/Account identity | DONE | ID contracts and current-data audit | P0 | NO | Keep contract |
| L11 | Multi-account | DONE | UI/Campaign/Feishu/assistant tests | P0 | NO | Keep contract |
| L12 | Mail relation parser | DONE | shared parser and 2/2 tests | P1 | NO | Keep contract |
| L13 | Local hard delete | DONE | transaction/lock/recovery tests | P0 | NO | Keep contract |
| L14 | Remote Feishu hard delete | DONE | Durable intent/recovery/retry/progress/reconcile tests 24/24 | P0 | NO | Keep contract |
| L15 | Feishu sync foundation | DONE | one workflow, relation/idempotency tests | P0 | NO | Keep contract |
| L16 | M7.1d legacy cleanup | OBSOLETE_SUPERSEDED | runtime modules removed, Clean Reset active | P3 | NO | Closed by physical cleanup |
| L17 | Feishu chat M7.6 | DONE | package, logs, tests, prior acceptance | P0 | NO | Keep contract |
| L18 | OpenClaw deployed runtime | CLOSED_BY_DESIGN_DECISION | OpenClaw retired; Assistant + Feishu transport canonical | P2 | NO | No deployment required |
| L19 | Normalization foundation | DONE | centralized domain helper/tests | P1 | NO | Keep contract |
| L20 | User/AI tag separation | DONE | persistence/projection code/tests | P1 | NO | Keep contract |
| L21 | Creator Intelligence | DONE | factual safe projection/tests | P1 | NO | Keep contract |
| L22 | Campaign core | DONE | sparse/multi-account/detail tests | P0 | NO | Keep contract |
| L23 | Actual published-content model | PARTIALLY_CLOSED | schema v3/API/UI/tests complete; packaged manual acceptance pending | P1 | YES | Complete acceptance checklist |
| L24 | Desktop Save As | DONE | bridge/UI tests plus packaged Windows user acceptance for all four cases | P2 | NO | Keep contract |
| L25 | Dashboard cold-start fix | CLOSED | ONEDIR portability, packaged startup evidence, real Windows usable Dashboard and clean runtime exit | P1 | NO | Closed |
| L26 | SQLite/read-index migration | C0_C12_ENGINEERING_COMPLETE | Performance and final synthetic evidence in `docs/pre_m8_sqlite_performance.md` | P0 | NO | Human review, then explicit production migration acceptance |
| L27 | VideoSnapshot scale/retention | CLOSED_BY_DESIGN_DECISION | retain-history contract and 100,000-row benchmark | P1 | NO | Revisit only on measured scale change |
| L28 | Test environment hygiene | DONE | canonical isolation plus narrow manual-artifact policy | P2 | NO | Keep gate |
| L29 | Frontend discovery/harness | DONE | 40 files and syntax gates pass | P1 | NO | Keep gate |
| L30 | Packaging dependencies | DONE | specs/requirements/TOC audit | P0 | NO | Keep gate |
| L31 | Microsoft OAuth2 | CLOSED_BY_DESIGN_DECISION | current contract is standard IMAP/SMTP; proposal retained as deprecated reference | P2 | NO | Future OAuth2 is a new feature |
| L32 | Security/privacy boundaries | DONE | localhost/Origin/safe projection | P0 | NO | Keep contract |
| L33 | API/OpenAPI contract | DONE | focused tests 3/3 | P1 | NO | Keep gate |
| L34 | Dead legacy service modules | CLOSED | source/tests removed after runtime/support/recovery/package dependency audit | P3 | NO | Closed |

## 46. Audit Artifact

Artifacts:

- `docs/pre_m8_legacy_closure_audit.md`
- `docs/pre_m8_storage_architecture.md`

Status: approved; C0-C10 implemented in isolated engineering/synthetic runtime,
C11-C12 engineering complete, real production migration not authorized, M8 blocked.

These are the only intended tracked architecture/audit artifacts from this design turn.

## 47. Final Decision

```text
PRE_M8_LEGACY_AUDIT_COMPLETE = YES
LEGACY_UNRESOLVED_COUNT = 3
PRE_M8_P0_BLOCKERS_REMAINING = 0
P0_C_STORAGE_ARCHITECTURE_DESIGN = APPROVED_AND_IMPLEMENTED_THROUGH_C10
STORAGE_ARCHITECTURE_APPROVED = YES
M8_ENTRY = BLOCKED
NEXT_STEP = CLOSE_ITEMS_6_12_13
READY_FOR_P0_C_ARCHITECTURE_REVIEW = NO_ALREADY_APPROVED
```

M8 product implementation must not start until human review and explicit
production SQLite migration acceptance. Batch 3 did not migrate real data.

## Production Migration Enablement Addendum

The missing production-facing activation capability is now implemented as a
localhost Settings-only, prepare/confirm workflow with source-hash protection,
validated backup, single-use session confirmation, cancellation, crash recovery,
and strict canonical-root enforcement. This closes the engineering enablement gap
without executing a real migration.

`REAL_SQLITE_MIGRATION_EXECUTED = NO` and
`REAL_PRODUCTION_SQLITE_ACTIVATION = NO`. M8 remains blocked until the user runs
and accepts the documented production migration procedure.

## Zero-Debt Delta Closure Addendum (2026-08-27)

This addendum records subsequent closure work without rewriting the historical
findings above:

- Item #8 is `CLOSED_BY_DESIGN_DECISION`: VideoSnapshot is retained historical
  time-series data, same-snapshot children are deterministically replaced, the
  supported latest/history indexes are present, and the 100,000-row local-product
  benchmark is the current measured scale boundary. No TTL is required.
- Item #9 is `CLOSED`: the canonical sandbox remains self-cleaning, while the five
  known manual diagnostic/acceptance paths are narrowly ignored and documented as
  non-authoritative scratch output.
- Item #10 is `CLOSED_BY_DESIGN_DECISION`: Campaign and Settings handlers are
  formally supported application coordinators and are contract-tested against
  direct workbook, SQLite, and filesystem bypass.
- Item #7 is `CLOSED`: currency identity, unit amount, positive integer quantity,
  bounded pricing unit, computed total quote, total cost currency, backward-compatible
  legacy rows, and mixed-currency-safe aggregation are implemented. No default
  currency or FX conversion is invented.
- Item #5 is `CLOSED`: the user reported packaged Windows PASS for template Save As,
  Creator export Save As, cancellation, and Chinese/space-containing paths.
- Current strict-gate state: #6 and #13 are closed by design decision. Item #12 engineering is
  complete but packaged manual UI acceptance remains pending; therefore M8 entry remains blocked.

## Final PRE-M8 Seal (2026-08-27)

This final seal is the authoritative current status. Earlier pending, unresolved, and blocked
statements above are retained as historical audit snapshots and are superseded by this section.

| Item | Final status | Final closure evidence |
|---:|---|---|
| 1 | CLOSED | TaskRepository Windows atomic write contract and regression coverage complete |
| 2 | CLOSED | Durable Feishu hard-delete propagation, recovery, retry, and reconciliation complete |
| 3 | CLOSED | SQLite storage foundation, cutover engineering, and accepted production migration work complete |
| 4 | CLOSED | Packaged Dashboard and runtime lifecycle accepted on Windows |
| 5 | CLOSED | Packaged Save As flows accepted on Windows |
| 6 | CLOSED_BY_DESIGN_DECISION | Old M3.1 production contract retired; current production support is NO; TikTok Passive Capture V2 is a new post-M8 project |
| 7 | CLOSED | Multi-currency quote and cost identity contract complete |
| 8 | CLOSED_BY_DESIGN_DECISION | Historical VideoSnapshot retention remains the supported contract |
| 9 | CLOSED | Canonical isolated test runner and artifact hygiene contract complete |
| 10 | CLOSED_BY_DESIGN_DECISION | Campaign and Settings application-coordinator boundary is the supported contract |
| 11 | CLOSED_BY_DESIGN_DECISION | OpenClaw is retired; Assistant plus Feishu transport is canonical |
| 12 | CLOSED | Engineering complete; packaged Windows manual acceptance passed for planned/actual separation, multiple publications, and save/reopen persistence |
| 13 | CLOSED_BY_DESIGN_DECISION | Current mail contract is standard IMAP/SMTP; Outlook/Microsoft OAuth2 is not officially supported and its proposal is deprecated reference only |
| 14 | CLOSED | Dead legacy backfill and cleanup modules retired after dependency audit |

Item #12 packaged acceptance additionally confirms the planned-account selector UX, selection
persistence, actual publication creation, multiple independent publication records, and unknown
publication-time behavior where applicable. No blocking defect was found.

```text
ITEM_12_MANUAL_ACCEPTANCE = PASS
ITEM_12_STATUS = CLOSED
ITEM_12_COUNTS_AS_UNRESOLVED = NO
LEGACY_CLOSED_ITEMS = [1,2,3,4,5,6,7,8,9,10,11,12,13,14]
LEGACY_UNRESOLVED_ITEMS = []
LEGACY_CLOSED_TOTAL = 14
LEGACY_UNRESOLVED_COUNT = 0
ZERO_DEBT_GATE_PASS = YES
ALL_14_LEGACY_ITEMS_CLOSED = YES
M8_ENTRY = READY
```
