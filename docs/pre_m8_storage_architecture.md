# PRE-M8 P0-C Storage Architecture

Status: `APPROVED_C0_C3_IMPLEMENTED_C4_C12_PENDING`

Design date: 2026-08-25

## 1. Executive Summary

KOLConnect will replace the Excel workbook as its mutable runtime business store with one per-user SQLite database. Excel remains a migration input, explicit import/export format, user-readable artifact, and compatibility backup. Normal runtime operations must never dual-write SQLite and Excel.

The proposed runtime database is `get_app_data_dir() / "data" / "kolconnect.db"`. Services continue to use repository contracts; handlers, Dashboard, Feishu Sync, Assistant, and Feishu Chat must not issue SQL. Connections are short-lived and owned by one request, background operation, or transaction. Every multi-table mutation is one explicit SQLite transaction.

The current packaged Windows runtime contains SQLite 3.50.4. SQLite's official WAL documentation identifies a WAL-reset race fixed in 3.50.7 and 3.51.3. Therefore production WAL cutover is gated on packaging a fixed SQLite version. The target configuration is WAL with `synchronous=FULL`; implementation must fail closed rather than silently use an affected WAL runtime.

PRE-M8 Phase 1 contracts remain frozen: Task atomic writes are closed, durable Feishu delete propagation is closed, and Feishu delete intents remain independent JSON lifecycle manifests. Batch 1 now implements isolated C0-C3 infrastructure and staged migration tooling; it performs no production migration or runtime repository cutover. Implementation evidence is recorded in `docs/pre_m8_sqlite_implementation.md`.

## 2. Decision / ADR

**Decision:** SQLite is the single mutable runtime business authority.

**Status:** `APPROVED`; C0-C3 are implemented and C4-C12 remain pending.

**Context:** Excel benchmark results reached 17-34 seconds for common medium reads, approximately 272 seconds for a common write, and 62-127 seconds for large reads. Workbook parsing, whole-sheet scans, and whole-file replacement cannot support M8 growth.

**Options considered:**

| Option | Decision | Reason |
|---|---|---|
| Excel authority plus SQLite read cache | Rejected | Leaves write scalability, whole-workbook mutation, invalidation, and two-format drift unresolved. |
| SQLite authority plus Excel compatibility | Selected | Gives indexed reads and transactional writes while preserving migration/import/export compatibility. |
| Dual mutable SQLite and Excel authority | Rejected | Cannot guarantee atomic cross-file commits and creates irreconcilable authority conflicts. |

**Consequences:** Migration and repository work are substantial now; runtime ownership, transactionality, concurrency, and performance become simpler afterward.

## 3. Current State

- Runtime business authority: `Creator_Library.xlsx`.
- Current path: `get_app_data_dir() / "Creator_Library.xlsx"`, optionally overridden by existing settings.
- Runtime: `ThreadingHTTPServer`, scraper/background threads, Feishu Chat executor, startup delete reconciliation, and possible worker processes.
- Repository construction: `RepositoryFactory` supplies request-scoped repositories sharing one `ExcelWorkbookStore`.
- Business sheets: Creators, CreatorAccounts, Videos, Insights, CreatorSnapshots, VideoSnapshots, Products, Campaigns, CampaignCreators, Cooperations, Agencies, AgencyContacts, FollowUpLogs, `_AnalysisData`, and `_Metadata`.
- Independent stores: settings, mail cache/config, data protection, task documents, diagnostics, staged-delete manifests, Feishu delete intents, logs, Chrome profile, and assistant in-memory confirmations.
- Current production baseline is valid: 4 Creators, 6 Accounts, 1 Campaign, and 3 CampaignCreator rows. Historical 2,453-Creator data is not a restore target.

## 4. Performance Evidence

| Fixture | Creator Library | Creator Detail | Campaign Detail | Dashboard | Common write | VideoSnapshot write |
|---|---:|---:|---:|---:|---:|---:|
| Current, 4 Creators | Fast | Fast | Fast | Fast | Fast | n/a |
| Small, 100/150/1,000 | 0.23s | 0.22s | 1.58s | 0.87s | 1.59s | 1.40s |
| Medium, 2,500/3,000/25,000 | ~17s | ~18s | ~34s | ~18s | ~272s | Triggered |
| Large, 10,000/12,000/100,000 | 62-127s reads |  |  |  |  |  |

The redesign trigger is met. The target is indexed SQL proportional to the requested page/entity/date range rather than workbook size.

## 5. Authority Model

```text
Application -> Service -> Repository interface -> SQLite repository -> kolconnect.db
```

- `RUNTIME_BUSINESS_AUTHORITY = SQLITE`
- `EXCEL_ROLE = IMPORT_EXPORT_BACKUP_COMPATIBILITY`
- `DUAL_AUTHORITY = NO`
- Excel is never watched for external edits after activation.
- Explicit Excel import is a validated transactional command; export creates a new artifact.
- Feishu remains a replica, never authority.
- Caches are disposable projections keyed by database revision, never authority.

## 6. File / Runtime Layout

Resolved from existing cross-platform `get_app_data_dir()`:

```text
KOLConnect/
  data/
    kolconnect.db
    kolconnect.db-wal                 # SQLite-managed, when open
    kolconnect.db-shm                 # SQLite-managed, when open
    kolconnect.db.migrating.<uuid>    # never treated as active
  backups/
    database/
    migration/
    clean-reset/
  storage_migrations/<uuid>/manifest.json
  storage_authority.json
  feishu_delete_intents/              # frozen independent lifecycle state
  delete_transactions/                # frozen staged lifecycle state
  tasks/
  settings.json
  data_protection.json
  mail_messages.json
```

Windows resolves under `%APPDATA%/KOLConnect`; macOS under `~/Library/Application Support/KOLConnect`; Linux under `$XDG_DATA_HOME/KOLConnect` or `~/.local/share/KOLConnect`. No database is created in the repository, TEMP, executable directory, or a network share.

## 7. SQLite Configuration

Target connection initialization:

```sql
PRAGMA foreign_keys = ON;
PRAGMA busy_timeout = 5000;
PRAGMA journal_mode = WAL;
PRAGMA synchronous = FULL;
PRAGMA temp_store = MEMORY;
PRAGMA cache_size = -32768;
PRAGMA wal_autocheckpoint = 1000;
PRAGMA journal_size_limit = 67108864;
```

- Standard-library `sqlite3`; no ORM or new service dependency.
- WAL is selected because readers can continue while one writer commits and the database is strictly local.
- `synchronous=FULL` preserves the destructive-lifecycle durability standard. `NORMAL` is not selected for release authority.
- The app verifies that `journal_mode` actually returns `wal`, `foreign_keys` returns `1`, and the SQLite library is fixed for the WAL-reset issue.
- Minimum preferred SQLite is 3.51.3. Explicitly accepted fixed backports may include 3.50.7 or 3.44.6 after packaging verification.
- Current Windows SQLite 3.50.4 is not eligible for WAL cutover. P0-C implementation must upgrade the packaged runtime or return a safe initialization error. No silent downgrade to another journal mode.
- Keep default 4 KiB page size for v1; do not change it after WAL activation.
- Automatic checkpoint remains at 1,000 pages initially. A passive checkpoint runs during graceful shutdown; `TRUNCATE` is reserved for maintenance/backup windows after readers close.

## 8. Connection Model

- `SQLiteConnectionFactory` owns path validation, version gate, connection creation, PRAGMAs, row factory, and close.
- One connection per HTTP request scope, background job, reconciliation inventory read, or migration operation.
- `check_same_thread=True`; a connection never crosses threads.
- No connection pool in v1. Short-lived connections avoid stale transactions and thread ownership ambiguity.
- Use `autocommit=True` on Python 3.12+ and explicit `BEGIN` / `BEGIN IMMEDIATE`, `COMMIT`, and `ROLLBACK` in a unit of work.
- Read-only operations use a short `BEGIN` snapshot only when multiple queries must be mutually consistent; single queries use SQLite autocommit reads.
- Write operations use `BEGIN IMMEDIATE` to obtain writer intent before reading mutation preconditions.
- Repository factory closes the connection in `finally`, and rollback is mandatory on any exception.
- Feishu network calls, browser automation, mail network calls, and long-running CPU work happen after database connections/transactions close.

## 9. Locking / Concurrency

Lock order is frozen:

```text
1. bootstrap/migration or cross-store lifecycle OS lock, when required
2. process-local DB write RLock
3. SQLite BEGIN IMMEDIATE transaction
4. commit/rollback and close
5. cache invalidation after commit
```

- Ordinary reads acquire no application-global lock.
- Ordinary writes use the process-local DB writer RLock plus SQLite's own cross-process writer serialization and 5-second busy timeout.
- Migration/activation, restore, Clean Reset, and hard-delete operations that span DB plus files/manifests retain an outer OS-backed lifecycle lock.
- No code may acquire the shared OS lock or DB writer lock while holding a cache lock.
- No code may acquire an outer lifecycle lock after beginning a DB transaction.
- SQLite permits concurrent readers but one writer; write transactions must contain only database work and bounded local manifest/file steps required by an existing staged transaction.
- The current broad workbook lock is retired from ordinary DB reads/writes after cutover. It remains for Excel import/export, legacy workbook access, migration, and independent JSON/file mutations until those paths receive narrower locks.

## 10. Transaction Model

| Mutation | Boundary |
|---|---|
| Creator create/update/archive/restore | One `BEGIN IMMEDIATE` transaction. |
| Account create/update/ownership change | One transaction including Creator projection changes. |
| Creator merge | One transaction covering all FK rewrites, conflict checks, and secondary removal. |
| Creator hard delete | Existing staged lifecycle manifest + prepared Feishu intent + one DB transaction; no Feishu network inside. |
| Product/Campaign create/update/archive/delete | One transaction including dependency validation. |
| CampaignCreator add/update/remove/batch add | One transaction including account/date/link child rows. |
| Creator XLSX/extension/task-result batch import | One transaction per user operation; validate before write. |
| CreatorSnapshot/VideoSnapshot append | One transaction for parent and all child observations. |
| Insights/analysis update | One transaction with the related snapshot/projection update. |
| Clean Reset | Backup + staged external-file plan + one child-first DB transaction. |
| Feishu Full Sync | Consistent read snapshot to build plan, close DB, confirm, then remote calls. |

Services own business transaction scope through a unit-of-work abstraction. Repositories do not independently commit when participating in an existing unit of work.

## 11. Entity Schema

Proposed v1 tables:

```text
app_metadata, schema_migrations, migration_issues
creators, creator_tags, creator_accounts
videos, insights, creator_snapshots, video_snapshots, analysis_records
products, campaigns, campaign_platforms
campaign_creators, campaign_creator_accounts
campaign_creator_planned_dates, campaign_creator_publish_links
cooperations, agencies, agency_contacts, follow_up_logs
```

No parallel PublishedContent table, tracking scheduler, recommendation, persistent AI tag,
task-document, mail, settings, or Feishu-delete-intent table is introduced. Actual publications
evolve the existing `campaign_creator_publish_links` child table in schema v3.

## 12. Table-by-Table Design

| Table | Key / ownership | Required and nullable data | Migration / compatibility |
|---|---|---|---|
| `app_metadata` | `key TEXT PK` | values for schema version, created time, business revision, authority marker, source workbook fingerprint, migration ID, minimum app version | Replaces `_Metadata` runtime role; not exported as ordinary business rows. |
| `schema_migrations` | `version INTEGER PK` | name, checksum, applied_at, app_version | Numbered, centralized migrations only. |
| `migration_issues` | `issue_id INTEGER PK` | migration_id, severity, sheet, row, field, code, sanitized detail | Audit/remediation only; never silently repairs ambiguity. |
| `creators` | `creator_id TEXT PK` | Preserve all current Creator-owned columns; optional values are NULL. Name is not unique. Current platform/profile/followers/email presentation fields remain compatibility columns until a separately approved ownership cleanup. | Source `Creators`; API adapter preserves current response names. |
| `creator_tags` | `(creator_id, ordinal) PK`; FK creator | exact user tag plus normalized comparison key | Source `Creators.tags`; AI tags are derived and not persisted. |
| `creator_accounts` | `account_uid TEXT PK`; FK creator; `account_id` UNIQUE when non-null | platform, username, profile URL, followers, account email, latest post/scrape data, status, attribution, note, task/source timestamps | Source `CreatorAccounts`; one Creator to many Accounts. |
| `videos` | `(creator_id, video_url) PK`; FK creator | Current latest video metrics and captured_at; account/platform nullable only when source proves them | Source `Videos`. No synthetic business video ID is invented. |
| `insights` | `creator_id TEXT PK/FK` | average/median views, stability, risks, recommendation; all nullable | Source `Insights`; persisted derived business output, not discarded. |
| `creator_snapshots` | `snapshot_id TEXT PK`; FK creator; optional FK account | platform, followers, average/median views, video_count, score, level, captured_at, source | Source `CreatorSnapshots`; historical immutable observations. |
| `video_snapshots` | `video_snapshot_id TEXT PK`; FK snapshot and creator | existing video_id/url/platform, nullable metrics, captured_at | Source `VideoSnapshots`; account is obtained through CreatorSnapshot, avoiding duplicate ownership. |
| `analysis_records` | `creator_id TEXT PK/FK` | task_id, account_uid, status_updated_at, exact `analysis_json`, source | Source `_AnalysisData`; preserve because it supports detail reconstruction and task/review handoff. It is not treated as a cache that can currently be dropped. |
| `products` | `product_id TEXT PK` | name required; company, note, timestamps/archive nullable | Source `Products`. |
| `campaigns` | `campaign_id TEXT PK`; FK product RESTRICT | Preserve current name, country, legacy platform, dates, owner, status, nullable budget/goal/note/timestamps | Source `Campaigns`; no M8 Published Content fields. |
| `campaign_platforms` | `(campaign_id, ordinal) PK`; FK campaign | validated platform value; unique per campaign | Source `Campaigns.platforms`; legacy `platform` remains export fallback. |
| `campaign_creators` | `id TEXT PK`; FKs campaign/creator | stage, owner, nullable quote currency/unit amount/quantity/unit/total, nullable total cost/currency, publish_date, metrics, ROI, note, timestamps/archive | Source `CampaignCreators`; one row per Campaign/Creator remains enforced by a partial unique active index. |
| `campaign_creator_accounts` | `(campaign_creator_id, ordinal) PK`; FK relation/account | account_uid, unique within relation | Normalizes current `account_ids`; ordinal 0 supplies legacy `account_id` projection. |
| `campaign_creator_planned_dates` | `(campaign_creator_id, ordinal) PK` | ISO date, unique within relation | Normalizes `planned_publish_dates`; export recreates ordered JSON. |
| `campaign_creator_publish_links` | `(campaign_creator_id, ordinal) PK`; unique `publication_id`; optional FK `actual_account_uid` | normalized URL, platform, actual published time, observed time, optional video ID, source | One row per actual deliverable; legacy links retain unknown account/time and `publish_links` compatibility. |
| `cooperations` | `cooperation_id TEXT PK`; FK creator | Preserve all legacy price/performance/result/note fields | Legacy read/write compatibility until separately retired; not merged into CampaignCreators. |
| `agencies` | `agency_id TEXT PK` | Preserve current agency/contact-cycle fields; `resource_files` remains validated JSON TEXT | Source `Agencies`. |
| `agency_contacts` | `contact_id TEXT PK`; FK agency | Preserve position/contact/status/source/timestamps | Source `AgencyContacts`. |
| `follow_up_logs` | `follow_up_id TEXT PK` | polymorphic object_type/object_id, contact/stage/timing/owner fields | Source `FollowUpLogs`; polymorphic target validated by service, not an invalid multi-table FK. |

Schema v2 adds nullable `quote_currency`, `quote_unit_amount`, `quote_quantity`,
`quote_unit`, and `cost_currency` while preserving nullable `creator_quote`, `cost`,
and `roi` `REAL` compatibility columns. Structured quotes enforce
`creator_quote = quote_unit_amount * quote_quantity`; quantity is a positive integer
and the pricing unit uses the bounded product vocabulary. Legacy total-only rows
remain NULL for the new fields rather than receiving invented values.

Currency identity uses uppercase three-letter codes. Aggregates may sum only rows
within the same known currency. Mixed known currencies, or known plus unidentified
legacy amounts, suppress the scalar total and expose grouped totals. No exchange
rate, conversion, invoice, tax, payment, or accounting subsystem is implied.

An active schema-v1 SQLite authority is backed up under `backups/database/` before
the transactional v1-to-v2 column migration. The backup is validated against its
source schema version; ordinary backups continue to require the current schema.

## 13. Index Plan

| Query | Index |
|---|---|
| Creator list, archive/status, sorting | `creators(archived_at, status, created_at, creator_id)` plus focused indexes on country/language/category only after query-plan proof |
| Creator account lookup/filter | PK account_uid; `creator_accounts(creator_id, platform, account_uid)`; `creator_accounts(platform)` |
| Creator tags | `creator_tags(normalized_key, creator_id)` |
| Latest/history Creator snapshot | `creator_snapshots(creator_id, captured_at DESC)` and `(account_uid, captured_at DESC)` |
| Video history/latest | `video_snapshots(video_id, captured_at DESC)`, `(creator_id, captured_at DESC)`, `(snapshot_id)` |
| Campaign list/filter | `campaigns(archived_at, status, start_date, campaign_id)`, `(product_id)` |
| Campaign membership/detail | `campaign_creators(campaign_id, archived_at, stage)`, `(creator_id, archived_at)`, unique active `(campaign_id, creator_id)` |
| Relation account lookup | `campaign_creator_accounts(account_uid, campaign_creator_id)` |
| Publish/date risk and analytics | planned date/date child indexes; `campaign_creators(publish_date, stage, archived_at)`; publish-link FK index |
| Agency lookup | `creators(agency_id)`, `agency_contacts(agency_id, status)` |
| Follow-up | `follow_up_logs(object_type, object_id, contacted_at DESC)` and `(next_follow_up_time)` |
| Legacy cooperation | `cooperations(creator_id, created_at DESC)` |
| Analysis lookup | PK creator_id; optional unique task_id when non-empty after migration validation |

Every index must be justified with `EXPLAIN QUERY PLAN` during implementation. Avoid redundant single-column indexes already covered by composite prefixes.

### VideoSnapshot retention contract

`video_snapshots` is historical time-series data. Distinct CreatorSnapshot captures
are intentionally retained; the runtime does not prune them by age. Rewriting the
same snapshot replaces that snapshot's child rows, and
`video_snapshot_id = <snapshot_id>:<video_id>` prevents duplicate identity within a
capture. The video/time and creator/time indexes are the supported latest/history
query paths.

The current private/local product scale is bounded by the demonstrated large
benchmark of 100,000 VideoSnapshot rows, where latest and history queries remained
approximately four milliseconds. Retention or partitioning is reconsidered only
after observed production scale or measured query performance exceeds that proven
boundary; no speculative TTL or background pruning is part of the current design.

## 14. Foreign Keys

- `PRAGMA foreign_keys=ON` is verified for every connection.
- Business parent relationships use `ON DELETE RESTRICT`. Hard delete, merge, Clean Reset, and Campaign deletion remove children explicitly in reviewed order.
- Pure owned child collections (`creator_tags`, campaign platforms/accounts/dates/links) may use `ON DELETE CASCADE` from their immediate parent because they have no independent lifecycle.
- Account, snapshot, video, CampaignCreator, Product, Agency, and Cooperation rows are never silently cascaded from a Creator/Campaign statement.
- Orphaned legacy rows block activation unless a frozen deterministic repair rule proves ownership.
- `PRAGMA foreign_key_check` must return no rows before migration activation and after restore.

## 15. Data Type Conventions

- IDs and raw business text: UTF-8 `TEXT`; trimmed only where current contracts trim.
- Timestamps: UTC RFC3339 `TEXT` ending in `Z`; timestamps with offsets are normalized to UTC during validated import.
- Dates: ISO `YYYY-MM-DD` `TEXT` with application validation.
- Booleans: `INTEGER NOT NULL CHECK(value IN (0,1))` where needed.
- Counts: non-negative `INTEGER`; rates/scores/current approximate monetary fields: nullable `REAL` with finite/non-negative checks where current semantics require.
- Missing values: SQL NULL. API/export adapters map NULL back to the existing blank/`None` contract.
- Raw country, language, and category values are preserved. Existing normalization is query/projection behavior, not destructive migration rewriting.
- Followers are canonical non-negative integers where parseable. A non-empty unsupported legacy numeric value blocks migration with row/field evidence rather than becoming zero.

## 16. JSON vs Normalized Relations

| Current value | Decision | Reason |
|---|---|---|
| Campaign `platforms` | Normalize child table | Filtered/joined and integrity-sensitive. |
| CampaignCreator `account_ids` | Normalize junction table | Must enforce Account ownership and support multi-account joins. |
| `planned_publish_dates` | Normalize ordered child table | Queried by date and requires date validation. |
| `publish_links` / `publications` | Evolve ordered child table | URL compatibility remains while actual account/time/source are explicit. |
| Creator `tags` | Normalize user-tag table | Search/filter semantics; exact raw tag remains preserved. |
| `_AnalysisData.analysis_json` | Keep validated JSON TEXT | Opaque full analysis payload with compatibility value; not queried field-by-field in v1. |
| Agency `resource_files` | Keep validated JSON TEXT | Small opaque list, not a relational query path. |

Import/export adapters own flattening and expansion. JSON validity is checked before commit. No normalization is performed only for aesthetics.

## 17. Migration Detection

| Startup state | Required behavior |
|---|---|
| No DB, no workbook | Create a new empty staged DB, validate, activate SQLite. |
| No DB, valid workbook | Run one migration from a read-only workbook snapshot. |
| Valid active marker + valid DB, workbook also exists | Use SQLite only; workbook is historical/compatibility. |
| Valid DB but marker absent | Inspect migration manifest; finish only a proven interrupted activation, otherwise block. |
| Marker says SQLite but DB missing/invalid | Enter `storage_error`; never fall back silently to Excel. |
| `.migrating` DB or in-progress manifest | Recover according to durable migration phase; never open as live. |
| DB schema newer than app supports | Fail safely with “data store created by a newer KOLConnect version.” |
| Multiple candidate DBs or contradictory manifests | Block for operator recovery; never choose by mtime. |

`storage_authority.json` is an atomic runtime marker with version, authority, active relative DB path, migration ID, schema version, and activation timestamp. It contains no secrets or arbitrary frontend-supplied path.

## 18. Migration Algorithm

1. Enter bootstrap state `initializing_storage`; do not bind the HTTP business server.
2. Acquire the OS-backed migration lock and verify no active migration/restore/reset.
3. Resolve the workbook from current settings; open read-only without applying workbook migrations.
4. Validate sheets, headers, workbook schema, and known legacy versions.
5. Create and validate an untouched workbook backup in `backups/migration/`.
6. Persist a JSON migration manifest as `prepared`, including source fingerprint and staged/final relative paths.
7. Create `kolconnect.db.migrating.<uuid>` and apply schema migration v1.
8. Import in FK order using current deterministic compatibility transforms; record warnings/issues.
9. Normalize child relations without changing public semantics.
10. Validate row/identity counts, FKs, multi-account ownership, Campaign membership, projections, and analysis preservation.
11. Set staged DB metadata to `validated`, commit, checkpoint, close, fsync the database and containing directory where supported.
12. Advance manifest to `validated`; atomically replace the final inactive DB path.
13. Reopen the final DB, run `quick_check`, FK check, schema/version and semantic checks.
14. Atomically write `storage_authority.json` with authority `sqlite`.
15. Mark migration completed, release the migration lock, construct SQLite repositories, then enter `ready`.

The source workbook and its original path are never renamed, deleted, or modified.

## 19. Activation

Migration manifest phases:

```text
prepared -> building -> imported -> validated -> database_activated
         -> authority_activated -> completed
                              \-> failed
```

Database rename and authority-marker write cannot be one filesystem atomic operation, so recovery is deliberately idempotent:

- Crash before `database_activated`: delete/rebuild only the staged DB after validating the manifest; Excel remains authority.
- Crash after final DB rename but before authority marker: final DB is not live. Revalidate it against the manifest, then finish marker activation or block.
- Crash after marker: marker plus valid DB selects SQLite; finish manifest bookkeeping.
- No business request is accepted until marker, DB metadata, schema version, and integrity agree.

## 20. Validation

Activation requires all of the following:

- Exact row counts for every source sheet and normalized child expansion counts.
- Unique non-empty `creator_id`, `account_uid`, and all other required IDs.
- `foreign_key_check` empty and `quick_check` equal to `ok`.
- Creator-to-Account ownership and multi-account counts equivalent.
- CampaignCreator active uniqueness and account membership equivalent.
- Ordered `platforms`, `account_ids`, planned dates, publish links, and tags round-trip to current projections.
- Archive/status/null semantics preserved.
- Snapshot-to-Creator and VideoSnapshot-to-CreatorSnapshot ownership preserved.
- Product/Campaign joins and sparse optional data preserved.
- `_AnalysisData` JSON decodes and representative Creator detail/intelligence projections match.
- Sampled API-equivalent projections for Creator list/detail, Campaign detail, Dashboard, Risk, and Analytics match the workbook adapter.

Validation compares deterministic digests of canonical projections, not row counts alone.

## 21. Failure Handling

- Any validation/import/IO/SQLite error moves the manifest to `failed` with a sanitized code and phase.
- The staged DB is never selected as runtime authority.
- Original Excel and its migration backup remain untouched.
- Startup presents a safe retry/recovery message and does not start partial business services.
- Retry creates a new migration ID/staged DB after cleaning only a verified prior staged artifact.
- No generic fallback to Excel occurs after an active SQLite marker exists.
- Busy/locked failures are bounded and reported; no infinite retry or sleep-based success.

Legacy classification:

| Condition | Action |
|---|---|
| Blank optional value | Convert to NULL. |
| Known old schema/version | Apply a registered, tested in-memory compatibility transform and record it. |
| Duplicate Creator/Account identity | Block. |
| Orphan Account | Repair only through an existing deterministic identity rule with one owner; otherwise block. |
| Orphan CampaignCreator/snapshot | Block; never drop. |
| Plain scalar accepted by current list parser | Convert to one ordered item and warn. |
| Invalid/ambiguous JSON list | Block. |
| Excel date or valid ISO value | Normalize; malformed non-empty date blocks. |
| Invalid non-empty numeric value | Block with row/field evidence; never coerce to zero. |
| Unknown empty column | Warn. |
| Unknown non-empty column or sheet | Block until a mapper or explicit exclusion is approved. |

## 22. Rollback

**Before activation:** discard only the verified staged DB, retain Excel authority, and allow migration retry.

**After activation:** do not automatically switch back to the old workbook because runtime changes may no longer exist there. Supported recovery order is:

1. stop business services and acquire maintenance lock;
2. restore a known-good SQLite backup into a staged DB;
3. validate schema, integrity, FKs, and app compatibility;
4. atomically activate the restored DB and increment recovery metadata;
5. restart services and reconcile caches/external lifecycle intents.

SQLite-to-Excel export is a data portability path, not an automatic rollback mechanism. Returning to Excel authority requires a separately reviewed emergency migration and is not promised lossless.

## 23. Backup / Restore

- Use Python `Connection.backup()` to a unique staged destination; never copy a live WAL database file alone.
- Validate backup with `quick_check`, FK check, schema version, and metadata before atomic publication.
- Backup before initial migration, every DB schema migration, Clean Reset, hard delete, and explicit manual backup.
- Ordinary application updates without a schema migration do not create automatic DB backups.
- Retain the newest 10 automatic backups per operation category, matching current launcher retention intent. Manual backups are user-managed and never silently deleted.
- Restore runs only in maintenance/bootstrap mode after request acceptance stops and all app-owned connections close.
- Restore targets a staged DB and uses the same validation/activation protocol; it never overwrites the active DB with an unvalidated file.
- A passive checkpoint may precede backup, but correctness relies on the backup API, not raw copying.

## 24. Excel Import

After cutover, import is explicit:

```text
XLSX upload/path selected by existing trusted UI
-> parse read-only
-> validate and preview
-> normalize through current import contract
-> one SQLite transaction
-> post-commit cache invalidation
```

- Existing Creator template headers and API responses remain stable.
- Re-import merge/overwrite behavior stays service-owned.
- The old workbook path is not watched and external edits do not auto-apply.
- Import never changes schema and never accepts arbitrary SQL/table names.

## 25. Excel Export

Export is a point-in-time artifact generated from a consistent SQLite read transaction into a new XLSX file.

- Preserve current public templates and frozen column order.
- Normalized campaign platforms/accounts/dates/links and Creator tags are flattened into current JSON/text shapes.
- `_AnalysisData` is exported when full compatibility backup/export is requested; ordinary Creator exports retain their existing limited contract.
- `_Metadata` is regenerated with export schema/version, export timestamp, and a clear `non_authoritative_export=true` marker.
- Export never becomes a mirrored runtime write and never changes database authority.
- UI must label the retained pre-migration workbook and new exports as non-live artifacts.

## 26. Clean Reset

- Preserve current confirmation, preview, backup-first, fail-closed, and verification semantics.
- Block if a local hard-delete transaction or Feishu intent is in `prepared`/`processing`, because lifecycle outcome is unresolved.
- Preserve `pending_remote`, `retry_wait`, `blocked`, completed, and aborted Feishu intents; never erase remote-delete obligations.
- Create a validated DB backup, then delete business rows child-first in one transaction while preserving schema metadata and migration history.
- Continue clearing data-protection, mail-message cache, and task artifacts through the existing staged external-file rollback protocol.
- Preserve settings, Chrome profile, mail account configuration, Feishu configuration, schema, and delete-intent runtime state.
- Clean Reset does not automatically Full Sync or delete Feishu records; current external behavior remains unchanged.

## 27. Hard Delete / Feishu Intent Boundary

The Phase-1 contract is frozen:

```text
prepared independent JSON Feishu intent
-> staged local lifecycle transaction
-> SQLite BEGIN IMMEDIATE business delete
-> commit local business state
-> pending_remote intent
-> asynchronous Account-before-Creator reconciliation
```

- `FEISHU_DELETE_INTENT_STORE = INDEPENDENT_JSON_MANIFEST`
- Intent storage is outside SQLite and Excel and is not migrated.
- The DB transaction replaces workbook row deletion; external task/data-protection artifacts remain coordinated by the staged manifest.
- Local commit remains independent of Feishu availability.
- Archive, restore, merge, and Clean Reset do not accidentally create hard-delete intents.

## 28. Feishu Sync

- Feishu remains a replica with the existing Validate -> Dry Run -> confirmed Full Sync workflow.
- Build a consistent Creator/Account inventory from SQLite repositories, then close the read transaction before network calls.
- Preserve `creator_id`, `account_uid`, type 18/21 relation validation, multi-account links, archive/restore, merge convergence, batch-stop safety, and idempotent second Dry Run.
- Full Sync never reads the retained workbook after activation.
- Feishu responses never write raw remote payloads into the business DB.

## 29. Assistant / Feishu Chat

- Assistant and Feishu Chat remain storage-agnostic: AssistantService -> business service -> repository interface.
- No direct `sqlite3`, SQL strings, arbitrary database access, or generic query tool is exposed.
- Existing confirmation, trace ID, safe projection, and no-bypass rules remain.
- Feishu Chat transport and Bitable Sync remain independent of database connection lifetime.

## 30. Dashboard

- Dashboard repositories become indexed SQL projections; no workbook scan or workbook fingerprint remains.
- Initially preserve the full response cache API and immutability contract, keyed by `app_metadata.business_revision` plus UTC date.
- Every successful business write increments `business_revision` in the same transaction. Failed writes do not.
- Cache hits perform one lightweight revision read and no full aggregation.
- Creator Library cache follows the same transition; remove it only after indexed queries meet targets and compatibility tests pass.
- Cache locks remain outside DB/lifecycle locks, and returned payloads remain deep-copied.

## 31. Mail / Tasks / Runtime JSON Stores

| Store | Classification | P0-C decision |
|---|---|---|
| `tasks/` task/progress/result/review documents | Workflow/runtime artifacts with established atomic-file contract | Remain JSON/CSV/files outside SQLite. |
| `mail_messages.json` | Bounded mail cache and account message state | Remains independent; business Creator matching uses repository service. |
| `settings.json` | Configuration and secrets/settings references | Remains outside business DB. |
| `data_protection.json` | Protected contact attribution state | Remains independent in P0-C; cross-store mutations keep staged rollback. |
| diagnostics/logs | Operational state | Remain files; never business authority. |
| assistant confirmations | Ephemeral session state | Remain in memory. |
| Feishu delete intents/delete transactions | Durable lifecycle state | Remain atomic JSON manifests. |
| Chrome profile/resources | Browser/runtime state | Remain unchanged. |

Mail/task code must stop reading stale Excel through incidental helpers after cutover; Creator/account joins go through repository interfaces.

## 32. VideoSnapshot Scale

- Append snapshots, never rewrite history.
- Query latest snapshots with descending composite indexes and `LIMIT`, not Python scans.
- Query history by video, Creator, Account through CreatorSnapshot, and date range using covering composite indexes where query plans justify them.
- Batch snapshot insertion uses `executemany` inside one transaction.
- Pagination is mandatory for large history APIs.
- Retention is deferred to M8.4. Schema supports later time-horizon deletion, per-video caps, and downsample/aggregate tables, but no destructive policy is selected now.

## 33. M8 Future Compatibility

- Actual Campaign publications now reference CampaignCreator and optionally CreatorAccount through
  stable IDs. A Video row is not required; optional future linkage remains additive.
- Current Videos use `(creator_id, video_url)` because no stable Videos-sheet ID exists. Future content identity must be separately frozen rather than inferred during migration.
- M8.5 may replace approximate nullable quote/cost fields with exact amount-minor and currency columns through a numbered migration. No currency default is invented.
- Existing raw country/language/category remain preserved; canonical normalization stays a projection unless a later migration explicitly separates raw and canonical values.

## 34. Packaging

- Python standard-library `sqlite3` requires no ORM/runtime dependency.
- Existing Windows PyInstaller output already contains `sqlite3`, `_sqlite3.pyd`, and `sqlite3.dll`.
- Current packaged SQLite is 3.50.4 and fails the WAL safety prerequisite. Implementation packaging must provide a verified fixed SQLite runtime, preferably >=3.51.3, and assert it in build tests.
- Windows and both macOS specs must collect the actual `_sqlite3` extension/runtime library and expose the same version gate.
- Add packaged smoke checks for open, WAL activation, transaction, backup, checkpoint, and restart recovery.
- No packaging file is modified in this design phase.

## 35. Windows / macOS

- All paths derive from `get_app_data_dir`; no PowerShell or NTFS-only runtime behavior.
- Database and WAL files must be local per-user storage, not OneDrive/network shares.
- SQLite owns database locking. The existing OS lock is retained only for migration and cross-store lifecycle coordination.
- Windows tests cover busy/locked handling, abrupt process exit, antivirus contention, backup, activation rename, and two-process migration exclusion.
- macOS tests cover Application Support paths, WAL/shared-memory availability, crash recovery, backup/restore, and package architecture.
- The SQLite version/WAL safety gate is identical on both platforms.

## 36. Security / Privacy

- No public listener, SQL endpoint, generic file-path database opener, Assistant SQL tool, or frontend-selected DB path.
- All SQL uses bound parameters. User values never become table/column names or SQL fragments.
- Database file permissions rely on the existing user-local application directory; no custom ACL complexity in v1.
- Backups/exports may contain business/contact data and remain in user-local storage or an explicitly selected Save As destination.
- Secrets, tokens, mail credentials, browser state, and Feishu App Secret remain outside the business DB.
- Logs redact payloads and record only operation names, safe counts, durations, error codes, schema versions, and trace IDs.

## 37. Observability

Record safely:

- SQLite runtime/library version and schema version at startup.
- Bootstrap state, migration ID/phase, source fingerprint, row counts, duration, and validation result.
- Backup/restore result and duration without content/path leakage to remote clients.
- Named repository operation duration, safe row count, trace ID, and whether lock/busy retry occurred.
- Write transaction duration, rollback count, WAL/checkpoint result, and business revision.
- Slow operation warning threshold: 500 ms for ordinary reads/writes; migration/backup use phase-level timings.

Do not log SQL parameter values, contact data, notes, mail body, credentials, or analysis JSON.

## 38. Test Strategy

**New install:** empty DB creation, metadata, schema, authority marker, restart.

**Migration:** current small workbook, empty workbook, medium fixture, known legacy versions, multi-account, Campaigns, snapshots, archive states, analysis JSON, malformed rows, duplicates, orphans, invalid arrays/dates/numbers, unknown columns, interrupted phases, and retry.

**Transactions:** Creator create/update/archive/restore/merge/hard delete, Account ownership, Campaign/Product/CampaignCreator, batch imports, snapshots, Insights, analysis, and Clean Reset.

**Concurrency:** concurrent reads, writer contention, Dashboard during capture import, Feishu Dry Run during write, abrupt writer death, two-process startup, and no-deadlock lock-order tests.

**Backup:** live backup API under WAL, validation, retention, interrupted backup, restore, schema compatibility, and rollback.

**Compatibility:** frozen API payloads, Creator/Campaign UI, Analytics, Dashboard, Feishu 18/21 relations, Assistant/Chat, mail matching, task storage, Excel import/export round-trip.

**Safety:** production path redirection before imports; tests use workspace-local disposable DB/Excel/intent roots and never production APPDATA.

## 39. Benchmark Acceptance

Datasets must be semantically equivalent to the Excel audit:

| Fixture | Creators | Accounts | VideoSnapshots |
|---|---:|---:|---:|
| Current | current post-reset | current | current |
| Small | 100 | 150 | 1,000 |
| Medium | 2,500 | 3,000 | 25,000 |
| Large | 10,000 | 12,000 | 100,000 |

Mandatory medium p95 targets after five warmups and at least 20 measured operations:

- Creator Library, Creator Detail, Campaign Detail, Dashboard: `<2s` each.
- Common durable write and VideoSnapshot append: `<3s` each.
- Report cold and warm p50/p95, DB/WAL size, row counts, platform, SQLite version, journal/synchronous mode, and query plans.
- Large must remain operational: p95 reads `<5s`, writes `<10s`, no minute-scale operation, unbounded memory growth, or full-table scan on indexed paths.
- Correctness tests remain fast; medium/large benchmarks run as a separate release gate, not every unit-test invocation.

## 40. Implementation Phases

| Phase | Scope | Exit / rollback gate |
|---|---|---|
| C0 | Package fixed SQLite runtime and add version/WAL smoke | No product cutover; package tests pass on Windows/macOS. |
| C1 | Connection factory, schema v1, unit of work, migration manifest/marker | Disposable DB tests only. |
| C2 | Read-only Excel migration importer and validators | Small/legacy/medium equivalence; Excel untouched. |
| C3 | Creator/Account/tag repositories | Creator lifecycle and multi-account regressions. |
| C4 | Product/Campaign/CampaignCreator normalized repositories | Campaign detail/filter/risk regressions. |
| C5 | Video/Insight/Snapshot/analysis repositories | History/latest and scale tests. |
| C6 | Agency/Contact/FollowUp/Cooperation repositories | Full legacy compatibility tests. |
| C7 | RepositoryFactory/unit-of-work cutover behind internal test flag | Full Python/frontend pass with both adapters in tests. |
| C8 | Hard delete, merge, Feishu, Assistant, mail joins | Lifecycle/outbox and external-mock regressions. |
| C9 | Explicit Excel import/export adapters | Frozen templates and round-trip tests. |
| C10 | SQLite backup/restore and Clean Reset | Crash/rollback/recovery tests. |
| C11 | Current/small/medium/large benchmarks and query-plan tuning | All mandatory thresholds pass. |
| C12 | One-time production authority activation and remove runtime flag | Release build/smoke/user migration acceptance. |

Every phase is independently reviewable. No phase changes production authority before C12.

## 41. Cutover Plan

- Develop both adapters behind a build/test-only backend selector; never expose “Excel or SQLite” to users.
- Before C12, production still uses Excel. SQLite adapter tests use sandbox databases.
- C12 ships one deterministic bootstrap: existing users migrate once; new users create an empty DB.
- Authority is selected only by validated `storage_authority.json`, never a user toggle, mtime, or file existence alone.
- After activation, RepositoryFactory always creates SQLite repositories. Excel repositories remain in migration/import/export tooling only.
- Remove/freeze the internal selector after acceptance to prevent long-term mixed authority.
- Retire ordinary workbook loads, workbook fingerprint caches, workbook schema mutation-on-read, and broad workbook locks from runtime paths only after equivalent tests prove the cutover.

## 42. Disaster Recovery

| Scenario | Supported recovery |
|---|---|
| SQLite corruption | Stop services, restore latest validated SQLite backup through staged activation. |
| Initial migration failure | Keep original Excel authority, inspect safe report, correct/retry; staged DB is not live. |
| User needs spreadsheet | Explicit SQLite-to-XLSX export. |
| Only an old Excel survives catastrophic loss | Recovery import into a new staged SQLite DB with full migration validation. |
| Authority marker lost but DB exists | Recover only with matching completed migration metadata; otherwise operator block. |
| Pending Feishu delete intents | Preserve independent manifests and resume reconciliation after DB recovery. |

Documented recovery tools must never accept an arbitrary path from a remote/browser request.

## 43. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Current SQLite 3.50.4 WAL-reset defect | Rare corruption under concurrent checkpoint/write | C0 fixed-runtime gate; no WAL cutover on affected version. |
| Migration semantic drift | Wrong Creator/Campaign projections | Canonical projection digests, FK/identity checks, read-only source, human-visible issue report. |
| Mixed authority | Divergent Excel and DB | Atomic authority marker, no user backend toggle, no normal Excel writes. |
| Long write transactions | UI stalls / SQLITE_BUSY | Precompute/validate outside transaction, explicit short transactions, metrics, bounded busy timeout. |
| WAL growth/checkpoint starvation | Disk/read degradation | Short reads, default auto-checkpoint, shutdown/maintenance checkpoints, WAL size telemetry. |
| Legacy malformed data | Migration block | Deterministic compatibility transforms only; actionable row/field report and retry. |
| Cache staleness | Incorrect Dashboard/Creator views | Same-transaction business revision and post-commit invalidation. |
| Cross-store operation failure | DB/JSON inconsistency | Existing staged lifecycle manifests and explicit recovery state machines. |
| Backup privacy | Sensitive local copies | User-local path, explicit Save As, retention, no secret logging. |
| Repository cutover breadth | Behavioral regression | Phased adapters, contract suites, no handler SQL, final all-at-once authority cutover. |

## 44. Open Questions

These require human approval before implementation:

1. **SQLite runtime delivery:** approve upgrading the packaged SQLite runtime to >=3.51.3 (preferred) rather than changing the approved WAL design to rollback-journal mode.
2. **Automatic backup retention:** approve 10 newest automatic DB backups per operation category, with manual backups user-managed.
3. **Historical workbook labeling:** approve a non-authoritative sidecar/UI notice while leaving the original workbook bytes and filename untouched.
4. **Large-fixture gate:** approve the proposed large p95 `<5s` reads / `<10s` writes in addition to the mandatory medium targets.

No unresolved product field or M8 schema decision is hidden in this design. Published Content identity and currency remain intentionally deferred to their milestones.

## 45. Human Approval Checklist

- [ ] SQLite is the only runtime mutable business authority
- [ ] Excel is import/export/backup compatibility only
- [ ] no dual-write authority
- [ ] Feishu delete intents remain independent JSON manifests
- [ ] migration is atomic/fail-closed
- [ ] original Excel remains untouched
- [ ] rollback/recovery is explicit
- [ ] repository services remain storage-agnostic
- [ ] Feishu remains replica
- [ ] Assistant has no SQL access
- [ ] Clean Reset semantics preserved
- [ ] medium performance targets defined
- [ ] Windows/macOS considered
- [ ] implementation is staged
- [ ] no M8 product schema introduced prematurely
- [ ] packaged SQLite WAL safety version is approved

```text
STORAGE_ARCHITECTURE_APPROVED = NO - PENDING HUMAN REVIEW
```

Implementation must not begin until this checklist is reviewed and approval is explicitly changed to YES.

## References

- Python `sqlite3` connection, transaction, threading, and backup behavior: https://docs.python.org/3/library/sqlite3.html
- SQLite WAL behavior, checkpointing, and WAL-reset safety notice: https://www.sqlite.org/wal.html
- SQLite Online Backup API: https://www.sqlite.org/backup.html
- SQLite PRAGMA reference: https://www.sqlite.org/pragma.html
