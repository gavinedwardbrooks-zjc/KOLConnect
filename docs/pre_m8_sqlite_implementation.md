# PRE-M8 P0-C SQLite Implementation

Status: `C0_C12_ENGINEERING_COMPLETE_PRODUCTION_MIGRATION_NOT_AUTHORIZED`

Implementation date: 2026-08-25

## 1. Boundary

Batch 1 implements the SQLite runtime gate, storage primitives, schema v1, and a read-only Excel-to-staged-SQLite migration adapter. It does not change `RepositoryFactory`, normal application startup, production repositories, or runtime authority. Excel remains the current production authority until the later cutover batch completes.

## 2. C0 Runtime Decision

The default Windows Python runtime exposes SQLite 3.50.4, which does not meet the frozen WAL policy. The Windows package therefore carries a pinned SQLite 3.53.1 native library at `packaging/vendor/sqlite/windows-x64/sqlite3.dll`. Its SHA-256 is `09435aa9de52c533f69fc3f6a23337e0276ad54567c808b80db64923c871257e`.

The gate accepts SQLite 3.51.3 or later and the fixed backport lines 3.50.7+ and 3.44.6+. It fails closed before any database connection when the engine is unsafe. Windows validates and preloads the pinned library before importing `sqlite3`. macOS uses the packaged Python runtime only when that runtime passes the same gate.

Both canonical build scripts run `scripts/check_sqlite_runtime.py`. The PyInstaller spec removes an automatically discovered `sqlite3.dll` and explicitly collects the pinned binary. `launcher.py --sqlite-runtime-check` validates the packaged engine without starting services or creating business storage.

## 3. C1 Runtime Layout

The canonical per-user paths are:

```text
<app data>/data/kolconnect.db
<app data>/backups/database/
<app data>/backups/migration/
<app data>/storage_migrations/<migration_id>/manifest.json
<app data>/storage_authority.json
```

Tests inject an isolated application-data root. No database is created in the repository root, TEMP, or production application-data directory.

## 4. Connection and Transaction Contract

`SQLiteConnectionFactory` creates short-lived, thread-affine connections. Connections are never globally shared. Every connection verifies:

- `journal_mode=WAL`
- `synchronous=FULL`
- `foreign_keys=ON`
- `busy_timeout=5000`
- `temp_store=MEMORY`
- `cache_size=-32768`
- `wal_autocheckpoint=1000`

Read contexts close deterministically. Writes acquire the process-local database `RLock`, issue `BEGIN IMMEDIATE`, commit once on success, and roll back and rethrow on failure. Read paths do not acquire the write lock. The future combined lock order remains shared mutation lock, OS shared-storage lock, database write lock, then connection/transaction.

Database backups use SQLite `Connection.backup()` into a unique sibling staging file, validate the result, and atomically replace the destination.

## 5. Storage Errors

The infrastructure defines stable classifications for unsafe runtime, unavailable WAL, busy storage, unsupported schema, integrity failure, migration failure, ambiguous identity, backup failure, and activation failure. User-facing messages do not require exposing absolute paths.

## 6. Schema Version 1

Schema v1 contains 20 tables:

```text
storage_metadata
creators
creator_tags
creator_accounts
videos
insights
creator_snapshots
video_snapshots
cooperations
agencies
agency_contacts
follow_up_logs
products
campaigns
campaign_platforms
campaign_creators
campaign_creator_accounts
campaign_creator_planned_dates
campaign_creator_publish_links
analysis_data
```

Schema migration is centralized, ordered, transactional, and currently contains only migration v1. Normal reads never mutate schema. A newer schema version fails closed.

## 7. Field and Identity Mapping

All fields in the current workbook contract are represented. The main mapping is:

| Workbook | SQLite | Identity | Compatibility |
|---|---|---|---|
| Creators | creators + creator_tags | creator_id | IDs preserved; tags normalized |
| CreatorAccounts | creator_accounts | account_uid | many Accounts per Creator |
| Videos | videos | creator_id + video_url | existing composite identity preserved |
| Insights | insights | creator_id | optional metrics remain NULL |
| CreatorSnapshots | creator_snapshots | snapshot_id | Creator/Account ownership preserved |
| VideoSnapshots | video_snapshots | video_snapshot_id | snapshot ownership preserved |
| Products | products | product_id | archived state preserved |
| Campaigns | campaigns + campaign_platforms | campaign_id | platforms normalized |
| CampaignCreators | campaign_creators + three child tables | id | selected accounts, planned dates, and links normalized |
| Cooperations | cooperations | cooperation_id | legacy read compatibility retained |
| Agencies | agencies | agency_id | current nullable fields retained |
| AgencyContacts | agency_contacts | contact_id | Agency relation retained |
| FollowUpLogs | follow_up_logs | follow_up_id | object identity retained |
| _AnalysisData | analysis_data | creator_id | JSON remains opaque text |

Missing numeric values remain SQL `NULL`; migration never converts missing quote, cost, follower, date, or metric values to zero. Dates/timestamps remain existing ISO-compatible text. No identity is generated from names.

## 8. Relations, Foreign Keys, and Indexes

Important business-parent foreign keys use restrictive behavior. Cascades are limited to true owned child collections such as tags, Campaign platforms, selected execution Accounts, planned publish dates, and publish links. Foreign keys are enabled and checked after import.

Indexes cover Creator and Account lookup, Account platform/ownership, Campaign membership, archive/status access, video ownership, and latest/history Snapshot queries. Query-plan tests confirm the Creator-to-Accounts hot path uses its index.

## 9. C3 Migration Adapter

`ExcelToSQLiteMigrator` performs this staged-only flow:

```text
read-only source validation
-> exact source backup
-> unique staged database
-> schema v1
-> one transactional import
-> integrity/FK/count/semantic validation
-> ready_for_activation
```

It hashes the source before and after migration and rejects any change. Unknown non-empty sheets or columns fail closed; empty legacy placeholders are tolerated. Duplicate stable identities, malformed relations, invalid numeric values, and orphan references fail closed. It does not keep-first, keep-last, auto-merge, or guess ownership.

## 10. Manifest and Recovery

Each migration has a secret-free manifest with migration ID, safe source name and hash, staged target name, timestamps, phase, failure classification, and activation state. Atomic JSON writes provide durable transitions.

The implemented phases are prepared, source validated, backup created, schema created, data imported, validated, ready for activation, database activated, authority activated, completed, and failed. Failure injection tests cover every pre-activation boundary. A failed or interrupted staged migration never changes authority.

Synthetic-only activation first atomically installs the validated DB and then writes the explicit authority marker. An interruption between those operations leaves legacy Excel authoritative and can be deterministically completed from the proven manifest. Production activation is explicitly refused in Batch 1.

Authority is never inferred from timestamps or file presence. A SQLite marker is accepted only when the database exists, its schema is supported, and integrity/foreign-key validation passes.

## 11. Synthetic Evidence

Focused tests cover current, empty, older compatible, multi-account, archived, normalized Campaign relation, nullable quote/cost, duplicate identity, orphan, malformed relation, unknown legacy shape, interrupted phase, activation recovery, corrupt authority, unsupported schema, concurrency, backup, and medium synthetic fixtures.

The medium smoke fixture contains 500 Creators and 2,500 Creator/Video snapshots. It validates indexed Creator and Campaign lookups and completes migration within the deterministic 30-second test budget. No production workbook is used.

## 12. Packaging Strategy

Windows packages the pinned SQLite 3.53.1 library. The build fails before PyInstaller if the runtime gate does not pass. The packaged diagnostic validates the engine without opening the application database. macOS retains its platform SQLite library only when it satisfies the same fixed-version policy.

## 13. Batch 2 Runtime Repository Cutover

`RepositoryFactory.for_runtime()` now resolves the explicit authority marker. A
validated `sqlite_active` marker selects `SQLiteWorkbookStore`; legacy installs
without an active marker retain `ExcelWorkbookStore`. A marker that names a
missing, corrupt, or unsupported database fails closed and never falls back to
Excel. New-install bootstrap creates an empty schema and explicit SQLite marker
only when neither legacy workbook nor database exists.

The existing Creator, Account, Campaign, Product, Agency, Snapshot, Insight,
Cooperation, FollowUp, Risk, Dashboard, merge, and hard-delete repositories keep
their frozen service/API contracts. `SQLiteWorkbookStore` materializes a detached
repository-compatible workbook snapshot for those contracts and synchronizes
changed normalized rows by stable identity inside one `BEGIN IMMEDIATE`
transaction on a write. Existing unchanged base rows retain their SQLite rowid;
Snapshot append does not delete/reinsert the Creator or historical Snapshot rows.
This provides one runtime authority and avoids a second divergent business
repository implementation. It is a compatibility cutover, not a dual write:

- SQLite writes never save the historical workbook.
- historical workbook edits are ignored while the SQLite marker is active.
- normalized tags, Campaign platforms, selected Account identities, planned
  dates, and publish links flatten back to the established external shape.
- missing numeric values remain SQL `NULL`; legacy projections remain unchanged.
- successful commits increment `business_revision`; rollback does not.

`SQLiteCreatorRepository` adds a Creator-scoped read boundary for snapshot-heavy
Creator Detail, Trend, Summary, Intelligence, and cooperation reads. Those paths
project only the requested Creator's rows and use
`idx_creator_snapshots_creator_time`; they no longer scan every Creator snapshot.
Whole-library compatibility projections materialize detached rows with bulk
child-collection prefetching and bounded query counts. Dashboard uses a dedicated
set-based SQLite source repository while preserving the existing DashboardService
business calculations and response contract.

## 14. Lifecycle and Integration Cutover

Dashboard cache fingerprints use SQLite `business_revision` plus UTC date while
SQLite is active; legacy Excel continues to use resolved path, `mtime_ns`, and
size. Ordinary SQLite cache hits do not open a workbook or acquire the OS storage
lock.

Feishu inventory, Assistant Creator/Campaign tools, Analytics, Risk, and Creator
mail-ownership mutation paths continue through repositories/services and therefore
read the active SQLite authority. Feishu Chat and Task JSON remain storage-backend
independent. Mail inbox matching remains a Feishu-record join and does not acquire
a new direct database dependency. No Assistant or handler exposes SQL.

Hard-delete manifests now record `storage_kind`. SQLite hard delete creates a
validated database transaction backup and rollback restores it safely; old
manifests without the field retain Excel restore behavior. Durable Feishu delete
intents remain independent JSON manifests and are promoted only after the local
SQLite delete commits.

## 15. Backup, Export, Import, and Clean Reset

SQLite backup uses the online backup API, a unique staged destination, schema and
integrity/FK validation, a representative Creator-table read, and atomic publish.
Restore checkpoints the old database, publishes a validated staged database under
the global lock order, removes stale WAL/SHM sidecars, and revalidates the reopened
schema. Managed manual backups use the database backup directory and retain the
newest 10; unrelated exports and migration-source workbooks are not selected.

Explicit SQLite-to-XLSX compatibility export reads SQLite only. Existing Creator
XLSX/task-result import continues through its established parser/repository path,
and the resulting business write is one SQLite transaction; injected failures
leave no partial Creator/Account rows.

Clean Reset previews the active store, creates a validated backup before mutation,
and clears every business sheet/table in one SQLite transaction while preserving
schema, authority metadata, settings, Feishu/mail/Chrome configuration, and the
independent delete-intent directory. A backup failure prevents mutation. A later
JSON/Task cleanup failure restores the database and staged files.

## 16. Batch 2 Synthetic Evidence

The 18-test isolated cutover suite migrates a legacy fixture, activates only its sandbox
marker, restarts repository factories, and covers no-dual-write, multi-account
detail, Campaign relations, NULL quote/cost, remaining business sheets, revision
cache, transactional import, merge, hard delete plus pending Feishu intent,
backup/restore/export retention, Clean Reset, failure injection, and thread-affine
concurrent reads with a bounded writer.

Final authoritative regression ran twice after the indexed Creator read boundary:
707 tests passed with one expected skip in 369.830s and 371.824s. Unified frontend
regression passed 40 files; JavaScript syntax passed 24 files; compileall and
`git diff --check` passed. The packaged SQLite runtime probe reports 3.53.1.

A non-final medium smoke used 500 Creators and 2,000 snapshots:

| Operation | Observed |
|---|---:|
| Creator Library page | 461.22 ms |
| Creator Detail | 394.06 ms |
| Campaign Detail | 359.21 ms |
| Dashboard build | 1511.15 ms |
| Snapshot append | 729.92 ms |

This catches immediate multi-second regressions only. It is not the C11 current,
medium (2,500/25,000), or large p95 acceptance.

## 17. C11-C12 Final Engineering Evidence

The deterministic Medium fixture reached 2,500 Creators, 3,000 Accounts, and
25,000 VideoSnapshots. The Large fixture reached 10,000 Creators, 15,000 Accounts,
and 100,000 VideoSnapshots. Medium p95 common reads were at most 725.123 ms and
durable writes at most 524.474 ms. Large p95 common reads were at most 3,117.495
ms and writes at most 2,852.721 ms. Both frozen performance gates pass.

Query counts are bounded at 9-13 SELECTs for Creator Library, Creator Detail,
Campaign Detail, and Dashboard. Critical point/history plans use the schema v1
indexes. Full evidence is in `docs/pre_m8_sqlite_performance.md`.

The final C12 harness ran the actual C3 migration and synthetic activation path,
verified source immutability, semantic parity, no dual authority, restart,
backup/restore, and XLSX export/fresh reimport. It also exposed and closed the
legacy account ID versus account UID semantic-validation gap.

Canonical Python regression passed twice: 710 tests, one expected skip, in
280.940s and 332.237s. Frontend, syntax, compileall, and diff checks pass.

## 18. Remaining Work

SQLite engineering C0-C12 is complete. Real production migration and authority
activation remain explicitly unauthorized and require human review plus a separate
production acceptance instruction. `M8_ENTRY = BLOCKED` until that review occurs.

## 18. Safety Status

```text
SQLITE_SYNTHETIC_RUNTIME_CUTOVER = YES
REAL_PRODUCTION_SQLITE_RUNTIME_CUTOVER = NO
REAL_SQLITE_MIGRATION_EXECUTED = NO
PRODUCTION_WORKBOOK_MUTATED = NO
DUAL_AUTHORITY = NO
```
