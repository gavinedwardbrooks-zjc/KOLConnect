# M7.5 Release Architecture Audit

Baseline: `2dad4a5b51f7836d365120264416ac0d93df1fa7`

## Authoritative Architecture

```text
Creator_Library.xlsx and local JSON/task artifacts
        -> repositories and services
        -> localhost HTTP API
        -> packaged web UI

Creator_Library.xlsx
        -> FeishuSyncService
        -> Validate -> Dry Run -> confirmed Full Sync
        -> Feishu Bitable replica

Assistant/OpenClaw
        -> documented Assistant API
        -> allowlisted KOLConnect services
        -> confirmation gate for writes
```

Excel and local runtime files remain authoritative. Feishu is a replica. The
assistant has no direct workbook, filesystem, shell, generic HTTP, or direct
Feishu access.

## Production Areas

| Area | Authoritative data | Active path | Release status |
|---|---|---|---|
| Creator | `Creators` | Creator repository/service/API/UI | Active |
| Accounts | `CreatorAccounts` | `account_uid` scoped reads and writes | Active |
| Videos and snapshots | `Videos`, `VideoSnapshots`, `CreatorSnapshots` | Account/Creator evidence reads | Active |
| Campaigns | `Campaigns` | Campaign API and UI | Active |
| Campaign membership | `CampaignCreators` | One Creator relation with multiple `account_ids` | Active |
| Products | `Products` | Campaign context | Active |
| Tasks | task directory and review documents | TaskService and task API | Active |
| Mail | settings plus mail runtime JSON | Settings/mail services | Active; Microsoft OAuth2 deferred |
| Feishu | remote Bitable replica | Validate, Dry Run, confirmed Full Sync | Active |
| Assistant | session-local confirmation records | narrow Assistant API | Active |
| Creator Intelligence | computed from local recorded facts | AI-summary read path | Active, non-persistent |
| Settings | `settings.json` | Settings API/UI | Active |
| Dashboard | computed/cached local read model | Dashboard API/UI | Active |

## Identity Contract

- Creator identity is `creator_id`; names and display names are not identity.
- Account identity is stable `account_uid`, derived from platform and canonical
  profile identity. Username alone is not identity.
- One Creator may own multiple accounts. Account snapshots join by
  `account_uid`; follower counts are never summed across platforms.
- Manual merge keeps the primary `creator_id`, removes the secondary local
  Creator, and reparents accounts without changing `account_uid`.

## Normalization and Intelligence

Country and follower normalization is centralized in `domain.normalization`.
Recognized country aliases are compared as ISO alpha-2 while original workbook
text remains untouched. Missing and malformed metrics remain unavailable, not
zero. M6.2, M7.3, and M7.4 share this contract.

`Creators.tags` remains the sole user-tag store. AI tags are deterministic,
computed, non-persistent labels. Creator Intelligence reports grounded facts,
per-account signals, limitations, freshness, and discrete confidence without
inventing demographics, engagement quality, or price.

## Campaign Contract

`Campaigns.platforms` is authoritative for multi-platform Campaigns; legacy
`platform` is compatibility-only. A Creator has one Campaign membership, with
zero or more execution `account_ids`. `planned_publish_dates` supports multiple
dates; legacy `publish_date` is compatibility-only. Published Content with an
exact account and actual publication timestamp is deferred to M8.3.

Campaign Detail tolerates zero Creators, missing Product, sparse optional dates,
and missing-publish widget failure. A real Campaign API failure remains visible
and retryable.

## Feishu Surface Classification

| Surface | Classification | Reachability |
|---|---|---|
| Settings Validate | Active read-only | Registered |
| Settings Dry Run | Active read-only | Registered |
| Settings confirmed Full Sync | Active write | Registered |
| Assistant Feishu sync intent | Active wrapper over Dry Run/confirmation/Full Sync | Registered |
| Task `sync_four_tables` | Internal local four-table persistence | Not a Feishu UI write route |
| Account/Creator identity backfill | Internal compatibility only | Handler modules not registered |
| Legacy unmanaged Creator cleanup | Internal compatibility only | Handler module not registered |
| Old capture-page direct Feishu sync | Dead product surface | UI and route absent |
| Historical scraper Feishu helpers | Internal compatibility only | Not exposed by normal UI/API |

Normal production Feishu business-write workflows: **one logical workflow**,
confirmed Full Sync through `FeishuSyncService`.

## Lifecycle and Safety

- Local hard delete is supported through the staged local transaction.
- Remote Feishu hard delete is not part of normal Full Sync.
- A remotely retained secondary Creator after local merge is an acknowledged
  `SECONDARY_REMOTE_CREATOR_RESIDUAL`, not an automatic-delete trigger.
- Clean Reset requires preview and literal confirmation, creates a validated
  workbook backup before mutation, preserves `_Metadata` and `settings.json`,
  and clears only defined business data. It is not run during release closure.
- Local missing-email scan reads `CreatorAccounts.account_email` by
  `account_uid`; Feishu is not its authority.

## Security and Privacy

The server remains localhost-only with Host and Origin validation. Trace IDs are
server-generated and returned on JSON and binary responses. Assistant outputs
exclude secrets, raw mail, local paths, and arbitrary workbook rows. Mail errors
are sanitized. Current Outlook authentication is Basic IMAP LOGIN; Microsoft
OAuth2 is documented separately and deferred to M7.4a.

## Deferred Boundaries

Microsoft OAuth2, remote hard-delete convergence, Published Content, tracking,
analytics expansion, URL resolution, Similar Creator, recommendations, and
Google Sheets belong to later milestones. M8 numbering does not imply build
order; M8 begins with architecture audit and must not redesign stable Feishu
sync without a separate sync audit.
