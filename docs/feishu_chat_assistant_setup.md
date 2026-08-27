# Feishu Chat Assistant Setup (Current Supplement)

> This document covers the optional Chat Assistant only. Use
> [Feishu setup](feishu_setup.md) as the canonical configuration guide for
> Bitable sync and Chat together.

M7.6 uses the official Feishu long connection. It does not expose a public
webhook and does not change the KOLConnect SQLite authoritative-data contract.

## Application strategy

Reuse the same Feishu application configured in KOLConnect Settings. The chat
transport needs only the existing App ID and App Secret; Bitable App Token and
table IDs remain exclusive to data synchronization.

In Feishu Developer Console:

1. Enable the Bot capability.
2. Add event `im.message.receive_v1` using long-connection delivery.
3. Grant least-privilege scopes:
   - `im:message.p2p_msg:readonly`
   - `im:message.group_at_msg:readonly`
   - `im:message:send_as_bot`
4. Publish the application version and make the bot available to intended users.
5. In KOLConnect Settings, save App ID/App Secret, then use **检查本机配置**.
6. Select **启用助手** and verify the status becomes **已连接**.

Do not grant mail, contact, drive, or broad tenant permissions for this feature.

## Message behavior

- Direct text messages are processed.
- Group text messages are processed only when the bot is mentioned.
- Attachments, images, cards, and other message types receive a safe unsupported
  response.
- Read requests return bounded, privacy-filtered KOLConnect results.
- Writes return a preview. Reply `确认` within five minutes in the same chat to
  execute, or `取消` to invalidate the pending operation.
- Full Sync keeps its existing Dry Run, conflict, plan-rebuild, and batch-stop
  safety contracts.

## Manual acceptance

Use disposable/read-only queries first:

1. Send a Creator search in a direct chat.
2. Request one Creator detail and verify multiple accounts are readable.
3. Mention the bot in a group and repeat a read query.
4. Send a group message without a mention and verify there is no reply.
5. Request Feishu Dry Run and verify no business mutation occurs.
6. Request a write preview, reply `取消`, and verify nothing executes.
7. Request another preview and verify a different user/chat cannot confirm it.

Do not run a real Full Sync solely to validate chat transport.

## Troubleshooting

| Code | Meaning | Check |
|---|---|---|
| `INVALID_APP_CREDENTIALS` | App ID or App Secret is absent/invalid | Save credentials again without exposing them in logs |
| `SDK_NOT_AVAILABLE` | Official SDK is missing from the runtime | Install/build with `packaging/requirements.txt` |
| `BOT_CAPABILITY_NOT_ENABLED` | Bot capability is not enabled/published | Enable Bot capability, publish, and reinstall the app |
| `EVENT_PERMISSION_MISSING` | Receive event or scope is absent | Enable `im.message.receive_v1` and required receive scopes |
| `BOT_PERMISSION_MISSING` | Bot cannot send replies | Enable Bot capability and `im:message:send_as_bot` |
| `LONG_CONNECTION_FAILED` | Connection failed or was interrupted | Check network, app publication, and Feishu service status |
| Assistant safe error | KOLConnect could not complete an allowlisted tool | Retry the read; for writes, request a fresh preview |
| Full Sync conflict | Existing Dry Run reported ambiguous identities | Resolve the conflict in Settings; chat cannot bypass this gate |

Logs include trace/session/event identities for diagnosis but must never include
App Secret, tenant/access tokens, message Authorization data, or private workbook
paths.
