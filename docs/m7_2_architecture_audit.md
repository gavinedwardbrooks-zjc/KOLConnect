# M7.2 Integration Architecture Audit

## Route inventory scope

The supported external surface is documented in `openapi.yaml`. All routes pass through `Handler._allow_local_request`, so the localhost Host gate applies to reads and the Origin gate additionally applies to mutations. Existing UI-only Settings, Dashboard, Analytics, Risk, Agency, mail, scrape-control, and binary transfer routes remain internal compatibility contracts.

Legacy account/Creator identity backfill and legacy Creator cleanup handler modules still exist for historical tests, but are not registered in `server.HANDLERS`. The removed capture-page direct Feishu write route is not part of the supported surface. They remain internal/retired and are excluded from OpenAPI.

## Cross-layer findings

| File/function | Finding | Severity | Decision |
|---|---|---|---|
| `http_handlers/feishu_sync_handler.py:handle` | Correct handler -> service -> Feishu client boundary | None | Keep |
| `http_handlers/creator_handler.py:handle` | Uses Creator services for core integration operations | None | Keep |
| `http_handlers/task_handler.py:handle` | Uses TaskService/ports; no direct task artifact writes | None | Keep |
| `http_handlers/campaign_handler.py:handle` | Stable handler directly invokes repository factory entries | Medium | Defer broad migration; no M7.2 integration correctness defect proven |
| `http_handlers/settings_handler.py:handle` | Mail operations call the `mail_sync` module through injected context instead of a formal service | Medium | Defer service extraction; parser defect fixed at existing boundary |
| `server.py` compatibility helpers | Historical four-table sync wrapper remains, but no normal capture-page Feishu write UI route calls it | Low | Keep internal compatibility code; do not document externally |
| Frontend API client | No storage access; now understands structured and legacy errors | None | Keep |
| OpenClaw | No runtime implementation or direct Excel access exists | None | Contract only |

No high-severity handler-to-workbook or plugin-to-workbook integration path was found in the registered M7.2 external surface. Migrating stable Campaign and mail modules to new service classes would be a broad refactor and is deliberately deferred.

## Relation parser classification

| Parser | Classification | Reason |
|---|---|---|
| `mail_sync._relation_record_ids` | SHARE_COMMON_PARSER | Active mail matching needs strict `record_id`/`record_ids` support |
| `feishu_relation.relation_record_ids` | SHARE_COMMON_PARSER | New strict active parser; explicit IDs only |
| `FeishuSyncService._relation_ids` | SPECIAL_CASE_REQUIRED | Active reconciliation accepts multiple API shapes and has established safety tests |
| `FeishuSyncService._legacy_relation_ids` | KEEP_FROZEN_LEGACY | Frozen one-way legacy matching semantics |
| `scraper._four_table_relation_record_ids` | KEEP_FROZEN_LEGACY | Retired/compatibility four-table flow; changing it would broaden this hotfix |
| identity backfill/cleanup use of service parsers | KEEP_FROZEN_LEGACY | Retired migration behavior must not change |

## Lifecycle decision

Archive and restore already converge via confirmed Full Sync while retaining stable local identity and history. Manual merge reconciles moved Account relations to the primary Creator; without a remote-delete contract, a secondary remote Creator can remain.

Hard-delete Feishu propagation is **DESIGNED_ONLY**. Current local hard delete is transactional and has no Feishu side effect, tombstone, or outbox. A safe future implementation requires a durable exact-identity delete intent written within the local transaction boundary, Account-before-Creator deletion, idempotent retries, and reconciliation. Local hard delete should not roll back solely because Feishu is temporarily unavailable, and archive must never enqueue physical deletion.

## Trace scope

Every JSON HTTP response now carries a request-level trace ID and logs append the same ContextVar value. Background task persistence is not changed because that would alter task document schemas. Existing `task_id` remains the durable task correlation key; request `trace_id` covers request-time creation and error diagnosis only.
