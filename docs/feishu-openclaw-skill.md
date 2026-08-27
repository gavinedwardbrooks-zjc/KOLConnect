# Feishu / OpenClaw Skill Contract

> **DEPRECATED / HISTORICAL / REFERENCE-ONLY**
>
> This document does not describe the active runtime. OpenClaw is retired from
> the product architecture and no OpenClaw deployment is required. The active
> conversational architecture is Feishu long-connection transport -> KOLConnect
> Assistant -> allowlisted KOLConnect tools and services.

## Boundary

The supported architecture is:

`Feishu/OpenClaw -> KOLConnect local API -> handler -> service -> repository -> store`

OpenClaw must not read or edit `Creator_Library.xlsx`, task files, browser storage, mail stores, or arbitrary local files directly. KOLConnect remains authoritative; Feishu is a synchronized replica.

## M7.3 implemented intents

| Intent | Required | Optional | Endpoint | Class | Confirmation |
|---|---|---|---|---|---|
| `search_creators` | none | search, platform, country, page | `GET /api/creator-library` | Read | No |
| `get_creator_detail` | creator_id | none | `GET /api/creator-library/{creator_id}` | Read | No |
| `create_capture_task` | links/text | name, platforms | `POST /api/tasks` | Write | Explicit user command |
| `get_task_status` | task_id | none | `GET /api/tasks/{task_id}/details` | Read | No |
| `list_campaigns` | none | status, product_id, date filters | `GET /api/campaigns` | Read | No |
| `get_campaign_detail` | campaign_id | none | `GET /api/campaigns/{campaign_id}` | Read | No |
| `feishu_sync_dry_run` | none | none | `POST /api/feishu-sync/dry-run` | Read-only remote | No |
| `get_daily_summary` | none | none | Existing Dashboard/Risk read APIs | Read | No |

The local adapter is implemented through `/api/assistant/capabilities`,
`/api/assistant/message`, and `/api/assistant/confirm`. It uses deterministic
routing in M7.3; no real AI provider or public Feishu webhook is configured.
`add_creator_to_campaign` remains deferred until explicit multi-account execution
selection is part of the assistant contract.

OpenClaw sends `{message, session_id}` and consumes the M7.2 envelope. Writes
return a five-minute, session-bound, single-use confirmation token. Restarting
KOLConnect expires all assistant state. A Full Sync request always performs Dry
Run first and cannot obtain a token when conflicts exist.

## Write policy

- Read-only intents are the default.
- Task creation is allowed only after an explicit command containing the intended links or scope.
- Feishu Full Sync must never be inferred from “update Feishu” or another vague phrase. It requires a displayed Dry Run and explicit confirmation under the existing API contract.
- Creator merge and permanent delete require the product's preview fingerprint and explicit confirmation. An assistant must summarize impact before requesting confirmation.
- No generic HTTP proxy, arbitrary file API, raw workbook operation, or unrestricted mutation tool is allowed.

## Response and errors

Consume `ok`, `data`, `error.code`, `error.message`, and `trace_id`. During compatibility migration, known top-level fields may also be present. Never display `error.details` blindly. A user-visible integration failure should include `错误参考：<trace_id>` without exposing local paths or secrets.

## Feishu policy

Validate and Dry Run are non-mutating. Full Sync is the sole normal Creator/Account replica-write workflow; the separate mail reply workflow is outside the initial OpenClaw tool contract. The assistant must not call retired direct task-result sync or identity-migration routes. Feishu display text is not identity; use `creator_id`, `account_uid`, and explicit Bitable record IDs returned by trusted APIs.

## Security assumptions

The current API is localhost-only and protected by Host/Origin checks. This historical contract never authorized cloud or remote access. No OpenClaw runtime is planned or required; any future reversal of that product decision would require a new authentication and transport design review.
