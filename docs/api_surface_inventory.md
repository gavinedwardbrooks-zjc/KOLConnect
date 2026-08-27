# M7.2 HTTP Surface Inventory

All entries below are registered through `server.HANDLERS` (plus the Browser Mode shutdown route), pass the localhost Host gate, and mutations pass the Origin gate. `Compat` means the existing top-level response/error shape is frozen and now receives `trace_id`; `Standard+compat` means an M7.2 envelope is added while old result fields remain.

| Method | Path | Handler | Purpose | R/W | Contract | Frontend | Tests | Legacy |
|---|---|---|---|---|---|---|---|---|
| GET | `/api/dashboard` | dashboard | Dashboard payload | R | Compat | Yes | Yes | No |
| GET | `/api/risks` | risk | Risk summary/cards | R | Compat | Yes | Yes | No |
| GET | `/api/campaigns/{id}/missing-publish-links` | risk | Publish-link risks | R | Compat | Yes | Yes | No |
| GET | `/api/analytics/platforms` | analytics | Platform analytics | R | Compat | Yes | Yes | No |
| GET | `/api/analytics/geography` | analytics | Geography analytics | R | Compat | Yes | Yes | No |
| GET | `/api/analytics/roi-trend` | analytics | Recorded ROI trend | R | Compat | Yes | Yes | No |
| GET/POST | `/api/products` | campaign | List/create products | R/W | Compat | Yes | Yes | No |
| GET/PATCH | `/api/products/{id}` | campaign | Product detail/update/archive | R/W | Compat | Yes | Yes | No |
| GET/POST | `/api/campaigns` | campaign | List/create Campaigns | R/W | Compat | Yes | Yes | No |
| GET/PATCH/DELETE | `/api/campaigns/{id}` | campaign | Campaign detail/lifecycle | R/W | Compat | Yes | Yes | No |
| GET/POST | `/api/campaigns/{id}/creators` | campaign | Membership list/add | R/W | Compat | Yes | Yes | No |
| POST | `/api/campaigns/{id}/creators/batch` | campaign | Batch membership | W | Compat | Yes | Yes | No |
| PATCH/DELETE | `/api/campaign-creators/{id}` | campaign | Membership update/remove | W | Compat | Yes | Yes | No |
| GET | `/api/creator-library` | creator | Creator search/page | R | Compat | Yes | Yes | No |
| GET/PATCH/DELETE | `/api/creator-library/{id}` | creator | Detail/update/hard delete | R/W | Frozen safety + trace | Yes | Yes | No |
| GET | `/api/creator-library/{id}/trend` | creator | Snapshot trend | R | Compat | Yes | Yes | No |
| GET | `/api/creator-library/{id}/snapshots` | creator | Snapshot history | R | Compat | Yes | Yes | No |
| GET | `/api/creator-library/{id}/ai-summary` | creator | Deterministic local summary | R | Compat | Yes | Yes | No |
| GET | `/api/creator-library/{id}/delete-impact` | creator | Hard-delete preview | R | Frozen safety + trace | Yes | Yes | No |
| POST | `/api/creator-library/{id}/status` | creator | Status update | W | Compat | Yes | Yes | No |
| POST | `/api/creator-library/{id}/relations` | creator | Agency relation update | W | Compat | Yes | Yes | No |
| POST | `/api/creator-library/{id}/create-task` | creator | Open/create linked task | W | Compat | Yes | Yes | No |
| POST | `/api/creator-library/merge/preview` | creator | Merge preview | R | Frozen fingerprint | Yes | Yes | No |
| POST | `/api/creator-library/merge/execute` | creator | Confirmed merge | W | Frozen fingerprint | Yes | Yes | No |
| GET | `/api/creator-library/import-template` | creator | XLSX template | R | Binary | Yes | Yes | No |
| POST | `/api/creator-library/import` | creator | XLSX batch import | W | Compat | Yes | Yes | No |
| POST | `/api/creator-library/export` | creator | XLSX selected export | R | Binary/errors compat | Yes | Yes | No |
| POST | `/api/extension/import` | creator | Extension capture import | W | Compat | Extension | Yes | No |
| GET/POST | `/api/local/agencies` | creator | Agency list/save | R/W | Compat | Yes | Yes | No |
| GET | `/api/local/agencies/{id}` | creator | Agency detail | R | Compat | Yes | Yes | No |
| GET/POST | `/api/local/agency-contacts` | creator | Agency contacts | R/W | Compat | Yes | Yes | No |
| GET | `/api/agency-contacts` | creator | Contact options | R | Compat | Yes | Yes | No |
| GET | `/api/tasks` | task | Task list | R | Compat | Yes | Yes | No |
| POST | `/api/tasks` | task | Capture task create | W | Compat | Yes | Yes | No |
| DELETE | `/api/tasks/{id}` | task | Task delete | W | Compat | Yes | Yes | No |
| GET | `/api/tasks/{id}/details` | task | Task detail | R | Compat | Yes | Yes | No |
| GET | `/api/tasks/{id}/results` | task | Review result list | R | Compat | Yes | Yes | No |
| GET | `/api/tasks/{id}/creator-analysis` | task | Task analysis | R | Compat | Yes | Yes | No |
| POST | `/api/tasks/{id}/links` | task | Link update | W | Compat | Yes | Yes | No |
| POST | `/api/tasks/{id}/resume` | task | Resume task | W | Compat | Yes | Yes | No |
| POST | `/api/tasks/{id}/stop` | task | Stop task | W | Compat | Yes | Yes | No |
| POST | `/api/tasks/{id}/results/update` | task | Save result fields | W | Compat | Yes | Yes | No |
| POST | `/api/tasks/{id}/results/review` | task | Review transition | W | Frozen D4 | Yes | Yes | No |
| POST | `/api/tasks/{id}/results/retry-failed` | task | Retry failed results | W | Compat | Yes | Yes | No |
| POST | `/api/tasks/{id}/results/open` | task | Open result file | W/local OS | Compat | Yes | Yes | No |
| POST | `/api/tasks/{id}/results/open-folder` | task | Open result folder | W/local OS | Compat | Yes | Yes | No |
| POST | `/api/tasks/{id}/rename` | task | Rename task | W | Compat | Yes | Yes | No |
| POST | `/api/tasks/manual` | task | Manual task create | W | Compat | Yes | Yes | No |
| POST | `/api/tasks/email-recheck/scan` | task | Local missing-email scan | W | Compat | Yes | Yes | No |
| POST | `/api/normalize-links` | task | Normalize links | R | Compat | Yes | Yes | No |
| GET | `/api/scrape/status` | task | Runtime status | R | Compat | Yes | Yes | No |
| POST | `/api/scrape/start|stop|pause|resume` | task | Runtime control | W | Compat | Yes | Yes | No |
| POST | `/api/feishu-sync/validate` | feishu_sync | Validate config/schema | R remote | Standard+compat | Yes | Yes | No |
| POST | `/api/feishu-sync/dry-run` | feishu_sync | Build sync plan | R remote | Standard+compat | Yes | Yes | No |
| POST | `/api/feishu-sync/full-sync` | feishu_sync | Confirmed sync | W remote | Standard+compat | Yes | Yes | No |
| GET | `/api/system/health` | settings | System checks | R | Compat | Internal UI | Yes | No |
| GET | `/api/state` | settings | Masked settings state | R | Compat | Yes | Yes | No |
| POST | `/api/settings/ui|profiles|accounts|feishu|mail|creator-library` | settings | Settings mutations | W | Compat | Yes | Yes | No |
| POST | `/api/settings/creator-library/backup` | settings | Workbook backup | W files | Compat | Yes | Yes | No |
| POST | `/api/settings/clean-reset/preview` | clean_reset | Reset preview | R | Frozen safety | Yes | Yes | No |
| POST | `/api/settings/clean-reset/execute` | clean_reset | Confirmed reset | W | Frozen safety | Yes | Yes | No |
| POST | `/api/account/open` | settings | Open Chrome Profile | W/local OS | Compat | Yes | Yes | No |
| GET | `/api/mail/inbox/messages` | settings | Recent mail | R | Compat | Yes | Yes | No |
| POST | `/api/mail/test` | settings | Mail connection test | R remote | Compat | Yes | Yes | No |
| POST | `/api/mail/inbox/sync` | settings | Fetch and match mail | R/W local | Compat | Yes | Yes | No |
| POST | `/api/mail/inbox/sync-crm-replies` | settings | Apply reply state to Feishu | W remote | Compat | Yes | Yes | No |
| POST | `/api/runtime/shutdown` | server | Browser Mode exit | W runtime | Compat | Yes | Yes | No |
| POST/PATCH/PUT/DELETE | `/api/creator-library/{id}/cooperations` | creator | Reject legacy Cooperation writes | W rejected | Frozen 403 | No | Yes | Yes |

Account backfill, Creator backfill, and legacy Creator cleanup runtime modules and routes are removed. Clean Reset is the supported replacement workflow. Static web files are not API routes.
