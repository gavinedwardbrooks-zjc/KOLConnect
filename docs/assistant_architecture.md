# M7.3 Assistant Architecture

## Boundary

The assistant is a localhost-only adapter over KOLConnect capabilities:

`Feishu/OpenClaw -> assistant API -> allowlisted service tool -> KOLConnect service/repository/store`

It has no workbook, filesystem, shell, SQL, generic HTTP, or credential tool.
M7.6 adds an optional Feishu long-connection transport that normalizes messages
and delegates only to this same AssistantService boundary. It does not expose the
localhost API remotely and does not add workbook or Bitable access to the bot.

## Provider and intents

The first implementation uses a versioned deterministic parser. It is reported
as `mode=deterministic` and never presented as model-generated output. The
provider protocol permits a future real adapter, but no provider dependency,
credential, or network call is included.

Read intents are `search_creators`, `get_creator_detail`, `list_campaigns`,
`get_campaign_detail`, `get_task_status`, `feishu_sync_dry_run`, and
`daily_summary`. Confirmed writes are `create_capture_task` and
`feishu_full_sync`. `add_creator_to_campaign` is advertised as deferred because
multi-account execution requires explicit account selection and must not guess.

## Confirmation and context

Writes first return a preview and a random in-memory confirmation token. Tokens
expire after five minutes, bind to the session, intent, argument hash, and prior
trace, and are consumed before one execution. Restarting KOLConnect invalidates
all tokens and bounded session context. Full Sync always runs Dry Run before a
token is issued and still delegates to the existing execution-time plan rebuild.
Conflicts prevent token issuance.

Session context retains only the most recent Creator, Campaign, Task identity and
expires after 30 minutes. No chat transcript or assistant output is persisted.

## Privacy and grounding

Search happens inside KOLConnect and results are bounded to 50. Missing metrics
remain null/unavailable, never zero. Assistant output removes contact details,
mail data, notes, prices/costs, secrets, tokens, passwords, and local paths.
Entity names and biographies are treated only as data. Ambiguous names return
safe candidates and require user selection.

## OpenClaw flow

1. Call `GET /api/assistant/capabilities`.
2. Send a message and stable local conversation ID to `POST /api/assistant/message`.
3. Display the grounded reply and any preview.
4. For a write, send the returned token, the same session ID, and literal
   `confirm: true` to `POST /api/assistant/confirm`.
5. Display `trace_id`; confirmed responses also link `confirmation_trace_id`.

Do not retry a confirmation token. Reissue the original message for a fresh
preview after expiry, restart, conflict, or uncertain write result.

## Feishu chat transport

The Feishu transport uses the official `lark-oapi` long connection and is disabled
by default. Direct messages are accepted; group messages require an explicit bot
mention. Session IDs bind direct chats to the chat and group chats to both chat
and sender. Event/message IDs are deduplicated in a bounded ten-minute process
cache. Only text is supported in M7.6.

The transport never executes a write from natural-language text alone. A preview
creates the existing five-minute, single-use confirmation token, and only a later
`确认` or `confirm` message from the same session can execute it. `取消` consumes
the pending token without execution. Restarting KOLConnect clears chat sessions,
dedup state, and pending confirmations.
