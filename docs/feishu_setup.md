# Feishu Setup

This is the canonical setup guide for the current KOLConnect Feishu integration. It covers two independent optional capabilities that reuse the same Feishu app:

1. **Bitable synchronization**: an explicit KOLConnect-to-Feishu replica workflow for Creator and CreatorAccount data.
2. **Feishu Chat Assistant**: an optional official long-connection transport to KOLConnect Assistant.

KOLConnect's SQLite database remains authoritative. Feishu is not an independent source of truth, and Chat does not directly access Bitable or local files.

## Configure KOLConnect

Open **Settings -> Feishu configuration** and save the values below. They are stored locally in %APPDATA%\KOLConnect\settings.json; the Settings API masks the saved App Secret and App Token when reading state. Protect the Windows user profile and do not share or commit that settings file.

| Setting | Required for Bitable sync | Required for Chat | Notes |
|---|---:|---:|---|
| App ID | Yes | Yes | Feishu app identifier, such as cli_xxx |
| App Secret | Yes | Yes | Secret; leave the masked Settings value empty to keep it unchanged |
| App Token | Yes | No | Bitable app/base token |
| Creator Table ID | Yes | No | Target Creator table ID |
| Creator Account Table ID | Yes | No | Target CreatorAccount table ID |
| Agency Contact Table ID | No | No | Optional, used only by the separate Agency-contact lookup path |

agency_table_id exists in local compatibility state but is not required by the current Bitable sync or Chat setup flow. The desktop app does not load .env.example or environment variables for these Settings values. Environment variables are only a command-line compatibility input for scraper.py.

Use placeholders in examples only:

~~~text
FEISHU_APP_ID=cli_xxx
FEISHU_APP_SECRET=your_app_secret
FEISHU_APP_TOKEN=your_bitable_app_token
FEISHU_CREATOR_TABLE_ID=tbl_creator
FEISHU_ACCOUNT_TABLE_ID=tbl_creator_account
~~~

## Bitable Sync

The normal write workflow is:

~~~text
Settings -> Validate -> Dry Run -> confirmed Full Sync
~~~

Validate and Dry Run are read-only remote operations. Full Sync requires an explicit confirmation, rebuilds the plan at execution time, and stops later batches after a batch failure. Do not use Chat or a task-result page as an alternate business-record write path.

For sync, configure a Bitable app/base with the Creator and CreatorAccount tables. The application authenticates with the tenant access-token endpoint, reads table fields/records, and plans batched Creator/Account create and update operations plus relation changes. Remote deletion is governed separately by the durable Creator hard-delete lifecycle, not inferred from an ordinary Full Sync. Grant only the Bitable permissions that permit those actual table operations for the configured app and tables; KOLConnect does not need broad tenant, drive, mail, or contact access for the base sync flow.

The current schema validator requires these fields:

| Table | Required fields |
|---|---|
| Creator | KOLConnect Creator ID, 达人名称, 国家/地区, 语言, 内容类型, 已归档, 最近同步时间, 社媒账号 |
| CreatorAccount | 账号唯一ID, KOLConnect Creator ID, 平台, 主页链接, 粉丝数, 最近同步时间, 达人 |

Insight等级, 最后分析时间, and CreatorAccount 平均播放量 are optional when present with compatible field types. Creator 社媒账号 must be a relation to the configured CreatorAccount table and must allow multiple records. CreatorAccount 达人 must relate to the configured Creator table. The validator supports legacy relation type 18 and current bidirectional relation type 21 only when the linked table identity and multiplicity meet those rules.

## Feishu Chat Assistant

Chat is disabled by default. It uses the official lark-oapi SDK long connection and only needs the saved App ID and App Secret. In the Feishu Open Platform:

1. Enable the Bot capability.
2. Subscribe to im.message.receive_v1 with long-connection delivery.
3. Grant the message scopes used by the runtime:
   - im:message.p2p_msg:readonly
   - im:message.group_at_msg:readonly
   - im:message:send_as_bot
4. Publish the app version and make the bot available to intended users.

No public callback or webhook URL is required for this Chat event path. Direct messages are accepted; group messages require an explicit bot mention. The transport has a 20-second connection watchdog, reports connection errors in Settings, and stops cleanly when disabled or when KOLConnect exits. Saving Feishu configuration restarts an already enabled Chat transport so it uses the new App ID/App Secret.

Use **Check local configuration** first, then **Enable Assistant**. This local check validates credentials/SDK construction without sending a message. A real connection still requires network access, an installed/published app, Bot capability, and the event/scopes above.

## Verify Safely

1. Save configuration in Settings.
2. Select **Validate** and resolve any missing or incompatible schema fields.
3. Select **Dry Run** and inspect counts/conflicts. It does not write records.
4. If using Chat, select **Check local configuration**, enable it, and make a disposable read-only request.
5. Run Full Sync only after reviewing a successful Dry Run and explicitly confirming the action.

Common codes include CONFIGURATION_ERROR, AUTHENTICATION_FAILED, PERMISSION_DENIED, FEISHU_SCHEMA_INVALID, FEISHU_CHAT_INVALID_CREDENTIALS, FEISHU_CHAT_EVENT_CONFIGURATION_ERROR, and FEISHU_CHAT_CONNECT_TIMEOUT. Use the Settings result and sanitized runtime logs for diagnosis. Never paste App Secrets, App Tokens, tenant/access tokens, or Authorization headers into issues or chat.

## Documentation Status

- docs/feishu_setup.md: **CURRENT** canonical setup.
- docs/feishu_chat_assistant_setup.md: **CURRENT** Chat-specific supplement.
- docs/assistant_architecture.md: **CURRENT** Assistant boundary and intent contract.
- docs/feishu-openclaw-skill.md: **HISTORICAL / REFERENCE-ONLY**; OpenClaw is retired from the active runtime.
- docs/飞书集成配置指南.md: **HISTORICAL / REFERENCE-ONLY** v0.1.2 material.
