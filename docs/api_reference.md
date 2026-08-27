# KOLConnect Local API Reference

## Runtime and trust boundary

KOLConnect serves its API on `127.0.0.1`. The server validates the `Host` header and validates `Origin` for mutations. This is a local product API, not a public internet API and not a replacement for authentication on a remotely exposed service.

`Creator_Library.xlsx` and task artifacts remain authoritative. Integrations must call KOLConnect APIs through handler -> service -> repository boundaries; they must never edit the workbook directly.

## HTTP application coordinator boundary

Existing Campaign and Settings handlers are supported application coordinators.
A handler may validate the HTTP contract, invoke repositories or services supplied
by the request-scoped composition root, coordinate one use case, invalidate a cache
after a successful mutation, and translate the result into an HTTP response.

A handler must not import or manipulate workbook/SQLite/file storage directly,
bypass repository transaction rules, duplicate domain normalization, persist data
outside an injected persistence interface, or coordinate unrelated domains. This
is the formal boundary for the existing Campaign and Settings implementation; a
service class is required only when a use case cannot remain within these limits.

## Response contract

New or touched integration APIs use:

```json
{"ok": true, "data": {}, "trace_id": "trace_..."}
```

```json
{"ok": false, "error": {"code": "VALIDATION_ERROR", "message": "Safe message", "details": {}}, "trace_id": "trace_..."}
```

Every JSON API response includes a server-generated `trace_id`, also returned as `X-Trace-ID`. Client-provided trace IDs are not trusted or reused. During migration, frozen routes retain their existing top-level fields. Feishu validate/dry-run/full-sync expose both the envelope and their existing top-level result fields.

Stable error categories are `VALIDATION_ERROR`, `INVALID_REQUEST`, `NOT_FOUND`, `CONFLICT`, `CONFIGURATION_ERROR`, `AUTHENTICATION_ERROR`, `PERMISSION_ERROR`, `RATE_LIMITED`, `TRANSIENT_NETWORK_ERROR`, `REMOTE_SERVICE_ERROR`, `STORAGE_ERROR`, `LOCK_TIMEOUT`, `UNSUPPORTED_OPERATION`, and `INTERNAL_ERROR`. Existing M7.1 Feishu machine codes remain valid.

HTTP conventions are 200 for reads/updates, 201 for creates already using that contract, 400 invalid input, 403 rejected local origin, 404 absent entity, 409 conflict, 423 lock timeout where supported, 429 rate limiting, 500 internal failure, and 502/503 remote/transient failure where a handler can distinguish them safely.

## Compatibility classification

| Surface | Classification | Strategy |
|---|---|---|
| Feishu validate/dry-run/full-sync | SAFE_TO_STANDARDIZE_NOW | Envelope plus existing top-level result fields |
| Creator, Campaign, Task UI APIs | NEED_COMPATIBILITY_ADAPTER | Add trace only; retain current payload fields |
| binary import template/export | FROZEN_LEGACY_CONTRACT | Preserve binary body; add trace response header |
| retired identity backfill and cleanup routes | REMOVED | Runtime modules and routes physically removed; Clean Reset is supported |
| legacy Cooperation writes | FROZEN_LEGACY_CONTRACT | Continue rejecting as read-only |

## Supported integration surface

| Method | Path | Purpose | R/W | Current contract |
|---|---|---|---|---|
| GET | `/api/creator-library` | Creator search/pagination | Read | Compatibility + trace |
| GET/PATCH | `/api/creator-library/{creator_id}` | Creator detail/update | Read/Write | Compatibility + trace |
| GET | `/api/creator-library/{creator_id}/delete-impact` | Hard-delete preview | Read | Frozen safety contract |
| DELETE | `/api/creator-library/{creator_id}` | Confirmed hard delete | Write | Frozen safety contract |
| POST | `/api/creator-library/merge/preview` | Merge preview | Read | Frozen fingerprint contract |
| POST | `/api/creator-library/merge/execute` | Confirmed merge | Write | Frozen fingerprint contract |
| GET/POST | `/api/campaigns` | Campaign list/create | Read/Write | Compatibility + trace |
| GET/PATCH/DELETE | `/api/campaigns/{campaign_id}` | Campaign lifecycle | Read/Write | Compatibility + trace |
| GET/POST | `/api/campaigns/{campaign_id}/creators` | Campaign membership | Read/Write | Compatibility + trace |
| POST | `/api/campaigns/{campaign_id}/creators/batch` | Batch membership | Write | Compatibility + trace |
| PATCH/DELETE | `/api/campaign-creators/{id}` | Membership update/removal | Write | Compatibility + trace |
| GET/POST | `/api/tasks` | Task list/create | Read/Write | Compatibility + trace |
| GET | `/api/tasks/{task_id}/details` | Task detail | Read | Compatibility + trace |
| GET | `/api/tasks/{task_id}/results` | Review queue | Read | Compatibility + trace |
| POST | `/api/tasks/{task_id}/results/review` | Review transition | Write | Frozen review contract |
| POST | `/api/tasks/{task_id}/results/retry-failed` | Retry selected results | Write | Compatibility + trace |
| POST | `/api/feishu-sync/validate` | Connection/schema validation | Read-only remote | Standard + compatibility |
| POST | `/api/feishu-sync/dry-run` | Synchronization plan | Read-only remote | Standard + compatibility |
| POST | `/api/feishu-sync/full-sync` | Confirmed business synchronization | Write | Standard + compatibility |
| GET | `/api/feishu-delete-intents/status` | Inspect durable remote-delete lifecycle state | Read | Internal Settings/diagnostics contract |
| POST | `/api/feishu-delete-intents/reconcile` | Confirmed bounded lifecycle reconciliation | Write | Internal Settings/diagnostics contract |
| GET | `/api/assistant/capabilities` | List allowlisted assistant intents | Read | M7.2 envelope |
| POST | `/api/assistant/message` | Interpret and execute a grounded read or return write preview | Read/Preview | M7.2 envelope |
| POST | `/api/assistant/confirm` | Execute one session-bound confirmed write | Confirmed Write | M7.2 envelope |
| GET | `/api/feishu-chat/status` | Inspect optional Feishu Assistant transport state | Read | Internal Settings contract |
| POST | `/api/feishu-chat/enable` | Enable the configured official long connection | Runtime control | Internal Settings contract |
| POST | `/api/feishu-chat/disable` | Stop the optional long connection | Runtime control | Internal Settings contract |
| POST | `/api/feishu-chat/test` | Check local credentials/SDK readiness without sending messages | Read-only check | Internal Settings contract |

All routes are protected by the same local Host/Origin gate. Frontend and extension callers use many additional local UI routes; those remain internal product contracts and are intentionally not presented as an external integration surface.

## Campaign monetary contract

CampaignCreator create/update responses preserve the legacy `creator_quote` and
`cost` totals and may additionally expose:

- `quote_currency`: uppercase three-letter currency identity.
- `quote_unit_amount`: recorded amount per pricing unit.
- `quote_quantity`: positive integer deliverable count.
- `quote_unit`: one of `video`, `post`, `reel`, `short`, `story`, `package`, or `other`.
- `cost_currency`: currency identity for the confirmed/payable total `cost`.

When structured quote fields are populated, `creator_quote` is computed as
`quote_unit_amount * quote_quantity`; a contradictory supplied total is rejected.
`cost` remains the confirmed/payable total and defaults to the quote currency when
the workflow supplies a structured quote without a separate cost currency.

Legacy rows containing only `creator_quote` or `cost` remain valid and do not gain
an invented currency, quantity, or unit. Currency-aware Dashboard and Analytics
responses retain their existing scalar fields, add grouped currency totals, and
set the scalar to `null` rather than summing unlike currencies. No exchange-rate
conversion is performed.

## Campaign publication contract

CampaignCreator responses preserve `publish_links` as a compatibility alias and expose
`publications`, one record per actual deliverable. Each record contains `publication_id`,
`actual_publish_url`, nullable `actual_account_id`, `platform`, nullable
`actual_published_at`, independent `observed_at`, optional `video_id`, and `source`.
Planning remains separate in `account_ids` and `planned_publish_dates`; planned or observed times
are never promoted to actual publication time.

## Creator export name contract

`POST /api/creator-library/export` emits one workbook row per selected
`creator_id`, not one row per Creator Account. The legacy `name` column is the
canonical Creator-level `creator_name` used by the Creator Library read model.
Platform-specific account `username` values are not substituted into that column,
including when one merged Creator owns multiple accounts or an account username is
blank. The legacy header remains unchanged so the generated workbook continues to
be accepted by the existing import parser.

Assistant endpoints accept no arbitrary tool name, URL target, filesystem path,
or raw intent execution. `message` requires a bounded `session_id`. Confirmations
expire after five minutes and cannot be replayed or moved between sessions.
Supported reads are Creator/Campaign/Task queries, Feishu Dry Run, and a simple
operational summary. Confirmed writes are capture-task creation and the existing
Full Sync safety workflow. Campaign membership is deferred in M7.3.

## Identity and write safety

Use `creator_id`, `account_uid`, `campaign_id`, and `task_id` exactly as returned. Do not identify entities by name, handle, profile URL, or display text.

Creator/Account replica writes have one normal workflow: Settings -> Validate -> Dry Run -> explicitly confirmed Full Sync. Validate and Dry Run do not write business records. Full Sync rebuilds its plan at execution time. The separate mail reply workflow may update its established CRM reply fields and is not a Creator inventory synchronization path. Hard delete and merge require their existing explicit confirmation and preview fingerprint contracts.

Retries must re-read current state. Callers must not assume that a failed write was applied, and must use the returned machine code and `trace_id` for diagnosis. Full Sync is designed to converge stable identities; callers must not replay vague user instructions as authorization.

## Lifecycle consistency

| Operation | Local effect | Feishu expectation | Campaign/mail/history | Current status |
|---|---|---|---|---|
| Create | Creator/account persisted | Created on confirmed Full Sync | Available to future relations | Supported |
| Archive | Identity and history retained | `已归档=true` on next Full Sync | Existing history retained | Supported |
| Restore | Same identity restored | `已归档=false` on next Full Sync | Existing history retained | Supported |
| Manual merge | Secondary merged locally | Account relations converge to primary on Full Sync | References reconciled locally | Partial: old remote Creator may remain |
| Hard delete | Local transactional removal | Exact-identity remote deletion required eventually | Local safety scanner/transaction applies | Designed only; no durable remote tombstone yet |

Future remote hard-delete propagation must use an auditable durable intent, exact stable IDs, Account-before-Creator ordering, idempotent retry, and reconciliation. Archive must never trigger physical remote deletion.

## Logging and privacy

Logs correlate request events using `trace_id`. Never place App Secret, tenant/access tokens, authorization headers, passwords, cookies, email bodies, WhatsApp values, or raw private payloads in errors, logs, or `details`.
