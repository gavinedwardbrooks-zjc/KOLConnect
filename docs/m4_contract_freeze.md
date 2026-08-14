# M4.0 Agency Boundary and Creator Delete Contract Freeze

This document freezes implementation contracts only. It does not authorize runtime, API, or workbook schema changes.

## 1. T4 current ownership

| Current method/route | Current owner | Reads/Writes | Proposed owner | Compatibility requirement |
|---|---|---|---|---|
| `getAgencies()` | `CreatorRepository` | Reads `Agencies`, `Creators`, `AgencyContacts`; adds creator/contact counts | Raw reads to `AgencyRepository`; aggregation to `AgencyService` | Preserve ordering and response fields |
| `getAgencyDetail(agency_id)` | `CreatorRepository` | Reads Agency, contacts, and Creators | `AgencyService`, using `AgencyPort` plus narrow Creator reads | Preserve not-found text and response keys |
| `saveAgency(payload)` | `CreatorRepository` | Creates/updates `Agencies` | `AgencyService` validation, `AgencyRepository` persistence | Preserve ID generation, timestamps, and errors |
| `getAgencyContacts(agency_id)` | `CreatorRepository` | Reads/sorts `AgencyContacts` | `AgencyPort`/`AgencyRepository` | Preserve optional filter and ordering |
| `saveAgencyContact(payload)` | `CreatorRepository` | Validates Agency and writes `AgencyContacts` | `AgencyService` orchestration, `AgencyRepository` persistence | Preserve optional Agency and errors |
| `upsertExternalAgencyContact(...)` | `CreatorRepository` | Deterministic upsert by external record ID | `AgencyService`/`AgencyPort` | Preserve deterministic contact ID and never infer Agency |
| `updateCreatorRelations(...)` | `CreatorRepository` | Validates Agency/contact IDs and writes Creator relation fields | Creator domain, with narrow `AgencyPort` validation | Preserve allowed fields and error text |
| `updateCreator(... agency_id ...)` | `CreatorRepository` | Validates Agency and updates Creator/analysis CRM data | Creator domain, with narrow `AgencyPort` validation | Preserve PATCH behavior and analysis mirror |
| Agency facade methods | `CreatorService` | Forward to CreatorRepository | Move Agency methods to `AgencyService`; keep temporary wrappers only while callers migrate | Handler response remains unchanged |
| Local Agency routes | `creator_handler` | HTTP parsing and response mapping | May remain in the same handler during T4, calling `AgencyService` | Same method/path/status/body |
| `GET /api/agency-contacts` | `server` provider via creator handler | Reads Feishu contact options, no local writes | Keep as external compatibility provider during T4 | Do not conflate with local Agency contacts |
| `RepositoryFactory.creator()` | `RepositoryFactory` | Supplies CreatorRepository for both domains | Add `agency()` provider; stop using `creator()` for Agency persistence | Same request-scoped store |
| CampaignCreator Agency label join | `CampaignCreatorRepository` | Reads `Agencies` to derive `agency_name` | Narrow Agency label read dependency; temporary direct read allowed during staged migration | Preserve Campaign API output |
| Follow-up Agency access | Schema only | No operational repository/service methods exist | Future FollowUp boundary; AgencyService may consume a narrow read port | No T4 behavior to migrate |

There is no current Agency campaign-count aggregation. T4 must not invent one. Creator and contact counts are current behavior; Agency detail creator records are current behavior.

## 2. T4 ownership contract

### AgencyRepository

Owns raw persistence and lookup for `Agencies` and `AgencyContacts`, stable ID generation, timestamps, row mapping, and Excel access. It does not read Creator, Campaign, FollowUp, HTTP, or task state.

### AgencyService

Owns Agency/contact input validation and orchestration, list/detail response assembly, creator/contact counts, and cross-domain read coordination. It does not access workbook sheets directly.

### Creator boundary

CreatorService/CreatorRepository continue to own `Creator.agency_id`, `current_contact_id`, and `source_contact_id`. They validate referenced IDs through a narrow AgencyPort dependency and never call AgencyService, preventing Service-to-Service cycles.

### Cross-domain decisions

| Operation | Contract |
|---|---|
| Creator count and Agency detail Creator list | AgencyService orchestration using a narrow Creator read dependency |
| Contact count | AgencyService over AgencyPort contact reads |
| Campaign Agency labels | Campaign domain uses a narrow Agency label read dependency; no reverse Service dependency |
| Campaign counts by Agency | Not current behavior; out of T4 scope |
| Creator relationship mutation | Stays in Creator domain; AgencyPort validates IDs |
| Follow-up history | No implementation exists; remain unimplemented and do not infer ownership beyond a future narrow FollowUp dependency |

## 3. Minimal AgencyPort proposal

The Port exposes domain DTOs, never worksheets, rows, paths, or openpyxl objects.

| Method | Input | Output | Mode | Expected errors | Current equivalent |
|---|---|---|---|---|---|
| `list_agencies()` | none | `tuple[AgencyRecord, ...]` | Read | storage/read error | Raw part of `getAgencies()` |
| `get_agency(agency_id)` | stable ID | `AgencyRecord` | Read | `AgencyNotFound` mapped to current message | Agency part of `getAgencyDetail()` |
| `save_agency(command)` | `SaveAgencyCommand` | `AgencyRecord` | Write | invalid payload/name/not-found/storage | `saveAgency()` |
| `list_contacts(agency_id=None)` | optional stable Agency ID | `tuple[AgencyContactRecord, ...]` | Read | storage/read error | `getAgencyContacts()` |
| `get_contact(contact_id)` | stable ID | `AgencyContactRecord` | Read | contact not found | Existing internal row lookup |
| `save_contact(command)` | `SaveAgencyContactCommand` | `AgencyContactRecord` | Write | invalid name/Agency/not-found/storage | `saveAgencyContact()` |
| `upsert_external_contact(command)` | external ID, name, WhatsApp, source | `AgencyContactRecord` | Write | missing external ID/storage | `upsertExternalAgencyContact()` |
| `agency_exists(agency_id)` | stable ID | `bool` | Read | storage/read error | Creator relation validation lookup |
| `contacts_exist(contact_ids)` | stable IDs | `set[str]` | Read | storage/read error | Creator relation validation lookups |
| `agency_labels(agency_ids)` | stable IDs | `dict[str, str]` | Read | storage/read error | CampaignCreator display join |

`AgencyRecord` preserves all current Agency columns. `AgencyContactRecord` preserves all current contact columns. Save commands distinguish omitted fields from explicit empty values so existing partial-update behavior remains intact.

## 4. API compatibility freeze

| Endpoint | Current request | Current response | T4 behavior | Coverage |
|---|---|---|---|---|
| `GET /api/local/agencies` | none | `{"ok":true,"agencies":[...]}` | Unchanged | HTTP smoke plus repository behavior |
| `GET /api/local/agencies/{agency_id}` | path ID | `{"ok":true,"agency":{...},"contacts":[...],"creators":[...]}` | Unchanged | Repository test; HTTP contract gap |
| `GET /api/local/agency-contacts` | none | `{"ok":true,"contacts":[...]}` | Unchanged | HTTP smoke; filtering contract gap |
| `POST /api/local/agencies` | current JSON payload | `{"ok":true,"agency":{...}}` | Unchanged | Repository test; HTTP contract gap |
| `POST /api/local/agency-contacts` | current JSON payload | `{"ok":true,"contact":{...}}` | Unchanged | Repository test; HTTP contract gap |
| `GET /api/agency-contacts` | none | `{"ok":true,"configured":bool,"contacts":[...]}` | Keep external Feishu compatibility behavior | TEST GAP |
| `POST /api/creator-library/{creator_id}/relations` | Agency/contact IDs | Existing relation response | Unchanged; Creator domain calls AgencyPort | Repository test; HTTP contract gap |
| `PATCH /api/creator-library/{creator_id}` | may include `agency_id` | Existing Creator response | Unchanged | Existing Creator lifecycle/UI coverage |

No endpoint, status code, Chinese error text, request key, or response field changes are authorized by T4.

## 5. Excel compatibility freeze

T4 preserves sheet names and every existing column:

- `Agencies`: `agency_id`, `name`, `country`, `website`, `public_email`, `whatsapp`, `cooperation_stage`, `tags`, `last_contact_time`, `next_follow_up_time`, `owner`, `note`, `resource_files`, `created_at`, `updated_at`.
- `AgencyContacts`: `contact_id`, `name`, `agency_id`, `position`, `email`, `whatsapp`, `language`, `status`, `last_contact_time`, `next_follow_up_time`, `owner`, `note`, `external_record_id`, `source`, `created_at`, `updated_at`.
- `Creators` relation columns: `agency_id`, `current_contact_id`, `source_contact_id`.

T4 does not rename sheets/columns, migrate IDs, regenerate IDs, or change relation semantics. Schema migration required for T4: **NO**.

## 6. T4 migration sequence and files

1. Add DTOs and `app/ports/agency_port.py` with characterization tests.
2. Add `app/repositories/agency_repository.py` over the existing shared ExcelWorkbookStore.
3. Add `app/services/agency_service.py` and narrow cross-domain read providers.
4. Add `RepositoryFactory.agency()` and composition-root wiring.
5. Move local Agency persistence/query callers while preserving handler contracts.
6. Migrate Creator relation validation and Campaign label reads to narrow AgencyPort methods.
7. Remove obsolete Agency methods from CreatorRepository only after all callers and patch points migrate.

Expected modified files are limited to the three new boundary files, `repository_factory.py`, composition wiring in `server.py`, `creator_handler.py`, `creator_service.py`, `creator_repository.py`, `campaign_creator_repository.py`, and dedicated tests. No workbook migration is expected.

## 7. D5 complete reference and retention matrix

| Entity/storage | Reference | Direct/indirect | Classification | Proposed action/reason |
|---|---|---|---|---|
| `Creators` | `creator_id` | Direct root | DELETE | Physically remove the approved Creator row |
| `CreatorAccounts` | `creator_id`; own `account_id/account_uid` | Direct | DELETE | Creator-owned accounts; only after all account references are handled |
| `Videos` | `creator_id` | Direct | DELETE | Current analysis child data |
| `Insights` | `creator_id` | Direct | DELETE | Current analysis child data |
| `_AnalysisData` | `creator_id`, `task_id`, `account_uid`, embedded `analysis_json` | Direct and embedded | DELETE | Creator-owned technical analysis and personal data |
| `CreatorSnapshots` | `creator_id`, `account_uid` | Direct | UNRESOLVED | Historical retention policy is not established |
| `VideoSnapshots` | `creator_id`, `snapshot_id` | Direct/indirect | UNRESOLVED | Must follow snapshot retention decision |
| `Cooperations` | `creator_id` | Direct | UNRESOLVED | Legacy commercial history retention is not established |
| `CampaignCreators` | `creator_id`, `account_id` | Direct | UNRESOLVED | Campaign history may require retention, detach, or deletion |
| `FollowUpLogs` | `object_type/object_id` | Conditional direct | UNRESOLVED | Polymorphic history policy and object type vocabulary are not implemented |
| `Agencies` | none back to Creator | Not applicable | RETAIN | Agency is independent and must never cascade-delete |
| `AgencyContacts` | none back to Creator | Not applicable | RETAIN | Contacts are independent; Creator-side links disappear with Creator row |
| `Products` | no Creator reference | Not applicable | RETAIN | Independent entity |
| `Campaigns` | relationship is through CampaignCreators | Indirect | RETAIN | Campaign must never cascade-delete |
| Task `task.json` | `creator_analysis_id`, `creator_snapshot_id`, Creator/Account ID arrays | Direct historical linkage | UNRESOLVED | Task audit/repair semantics are not established |
| Task `results.csv`/`progress.csv` | account UID, profile and captured result fields | Indirect identity | UNRESOLVED | Raw task retention and privacy policy are not established |
| Task links/filter/modification/sync files | profile links/account UID and import summaries | Indirect identity | UNRESOLVED | Multi-file retention policy is not established |
| `data_protection.json` | keyed by account UID | Indirect identity | UNRESOLVED | Manual-value protection may contain personal data |
| Legacy analysis/library files | Creator/account identity when present | Indirect migration source | UNRESOLVED | Active-vs-legacy retention policy is not established |
| `_Metadata` | workbook-level schema/version only | Not applicable | RETAIN | No Creator reference |

`ANONYMIZE` and `DETACH` are not assigned without a product decision. They remain candidate actions for the unresolved historical entities, not implicit behavior.

## 8. D5 hard-delete semantics

Hard delete means physical removal of the Creator root and all entities classified `DELETE`, in one approved operation. It never deletes Agency, AgencyContacts, Product, or Campaign. It may not run while any related entity remains `UNRESOLVED`; the preview must return `can_delete=false`.

The current soft archive remains the reversible default. A Creator must be archived before hard delete is eligible. Creator contact and Agency links disappear only because the Creator row is removed; referenced Agency/contact records remain unchanged.

## 9. D5 impact preview and dry-run contract

Conceptual operation: `GET /api/creator-library/{creator_id}/delete-impact`. This is a design placeholder, not an authorized endpoint.

Response semantics:

```json
{
  "ok": true,
  "creator": {"creator_id": "...", "display_name": "...", "archived": true},
  "affected_counts": {"Creators": 1, "CreatorAccounts": 0},
  "retained_counts": {"Agencies": 0, "Products": 0, "Campaigns": 0},
  "unresolved_references": [{"entity": "CampaignCreators", "count": 0}],
  "warnings": [],
  "blockers": [],
  "can_delete": false,
  "preview_fingerprint": "..."
}
```

Only minimal Creator identity is returned; no email, phone, profile URL, task row, or captured content is included. The fingerprint covers Creator `updated_at`, relevant IDs/counts, and the applicable retention policy version.

Impact preview and dry-run are the same operation here: both fully validate and count the proposed mutation with zero persistence. A second endpoint would be redundant.

## 10. D5 confirmation and stale-write gate

The eventual DELETE request should require:

```json
{
  "confirm_creator_id": "creator_...",
  "preview_fingerprint": "..."
}
```

An additional boolean flag adds no protection and is not required. Under the workbook write lock, the implementation must recompute the impact and fingerprint before mutation. A mismatch blocks deletion and requires a new preview. Expected counts are covered by the fingerprint rather than duplicated in the request.

## 11. D5 transaction strategy

For workbook-only mutation, the current store is safe **only** if one repository operation opens one workbook, validates every delete, mutates all approved sheets in memory, and performs exactly one save. ExcelWorkbookStore writes a temporary workbook, reopens it for validation, copies the old workbook to backup, and atomically replaces the target. A save failure leaves the pre-delete workbook in place.

Sequential Service calls to repositories are forbidden because request scope currently uses `defer_writes=False` and would persist partial steps. The delete operation therefore needs one dedicated workbook mutation boundary.

If the approved policy requires mutation of task files, `data_protection.json`, or a separate audit store in the same operation, current infrastructure cannot provide cross-store atomicity. That case requires infrastructure or a recoverable compensation journal before confirmed delete.

Current classification: **INFRASTRUCTURE CHANGE REQUIRED** for the complete D5 contract, because external-file retention remains unresolved. Workbook-only atomic deletion itself is supported by the current store.

## 12. D5 failure semantics

| Condition | Decision |
|---|---|
| Creator not found | BLOCK DELETE |
| Creator not archived | BLOCK DELETE |
| Creator already archived | ALLOW WITH WARNING |
| Active CampaignCreator relation | BLOCK DELETE |
| Historical/archived CampaignCreator relation | UNRESOLVED |
| Legacy Cooperation history | UNRESOLVED |
| Broken CreatorAccount/Creator relationship | BLOCK DELETE |
| CampaignCreator references unknown account | BLOCK DELETE |
| Unknown FollowUpLogs object/reference | BLOCK DELETE |
| Unknown hidden metadata referencing Creator/account | BLOCK DELETE |
| Workbook validation/save failure | BLOCK DELETE; original workbook must remain |
| Preview or payload validation failure | BLOCK DELETE |
| Concurrent change/fingerprint mismatch | BLOCK DELETE and require a new preview |

## 13. Audit record decision

No existing sheet is an immutable delete-audit ledger. `_Metadata` is workbook metadata and must not be repurposed. Application logs do not provide a structured immutable record.

If an immutable audit record is required, **SCHEMA CHANGE REQUIRED**. A future audit record should contain only deleted Creator ID, timestamp, policy/fingerprint, affected counts, and outcome. It must not preserve deleted personal fields.

## 14. Unresolved product decisions

1. Retain, detach/anonymize, or delete historical CampaignCreator rows.
2. Retain, anonymize, or delete legacy Cooperation history.
3. Retain/anonymize or delete CreatorSnapshot and VideoSnapshot history.
4. Retain/anonymize or delete Creator FollowUpLogs and define valid `object_type` values.
5. Retain, detach, anonymize, or delete task metadata and task result/link/modification files.
6. Remove or retain `data_protection.json` entries for deleted account UIDs.
7. Whether structured immutable deletion audit is mandatory, accepting the required schema change.
8. How legacy analysis/library source files participate after a hard delete.

These decisions block confirmed D5 implementation but do not block T4 extraction or read-only D5 impact discovery.

## 15. B5 boundary

B5 depends on Agency list/query capability, stable Agency IDs/labels, and an explicitly compatible Creator relationship/import contract. It does not depend on TikTok MAIN hook, item_list capture, M3 session, auto-scroll, user/detail, or any resumed M3 work.

## 16. Recommended M4 order

1. M4.0: this contract freeze.
2. M4.1: T4 AgencyPort/AgencyRepository/AgencyService extraction with unchanged API/schema.
3. M4.2: D5 read-only impact scanner and characterization tests; resolve retention decisions before exposing mutation.
4. M4.3: D1 Agency page, once AgencyService is stable. This can proceed while destructive D5 policy remains under review.
5. M4.4: D2 Creator Library upgrade on stable Agency/Creator boundaries.
6. M4.5: B5 Extension Agency dropdown, independently of M3.
7. M4.6: D5 confirmed hard delete only after all unresolved retention and audit decisions are frozen and any required transaction infrastructure exists.
8. M4.7: D3 batch add to Campaign.
9. M4.8: D4 review UI redesign.

This differs from the initial hypothesis by not placing confirmed hard delete before normal Agency/Creator UI work. Read-only impact discovery is low risk, while destructive mutation is gated by unresolved historical-data policy and possible cross-store transaction requirements.
