# M8.3-T Completion and Acceptance Report

## Decision

M8_3_T_STATUS = AUTOMATED_IMPLEMENTATION_COMPLETE / REAL_E2E_PENDING

TIKTOK_PRODUCTION_SUPPORT = NO

M8_3_T_GATE = BLOCKED_FOR_REAL_E2E

This report records synthetic/fixture verification, not real TikTok production acceptance.
The pre-existing M8 working-tree changes were preserved. No backend business files were
edited for this slice. SQLite, Creator identity and Campaign publication contracts are unchanged.

## Retained asset audit

| Asset | Before this slice | Reuse / change |
|---|---|---|
| `capture/passive_capture_main.js` | EXPERIMENTAL / DISABLED | Reused fetch/clone and XHR wrappers; bounded sanitized replay; request-context isolation |
| `capture/passive_capture_protocol.js` | EXPERIMENTAL / REFERENCE_ONLY | Reused endpoint/token schema; allowlisted bounded payload; profile/time validation |
| `content/passive_capture_bridge.js` | EXPERIMENTAL / DISABLED | Removed trust in page bootstrap; extension-background token retrieval; receiver sanitization |
| `platform/tiktok_network.js` | REFERENCE_ONLY | Reused fixture-backed parser, strict IDs and missing/zero rules; optional author/pinned data |
| `platform/tiktok.js` hydration/DOM | ACTIVE_PRODUCTION | Reused page extraction; explicit L2/L3; bounded ownership checks; removed active video-detail requests |
| `core/analysis_session.js` | ACTIVE_PRODUCTION | Existing UI cancellation/stale-response protection retained; not a video buffer |
| Floating preview and `services/local_api.js` | ACTIVE_PRODUCTION | Existing explicit import retained; per-field provenance and reset added |
| `/api/extension/import` and CreatorService | ACTIVE_PRODUCTION | Unchanged authoritative import path |
| Manifest passive entries | DISABLED | TikTok-only document_start MAIN/ISOLATED acceptance wiring; no additional permissions |

EXISTING_ASSETS_AUDITED = YES
EXISTING_ASSETS_REUSED = YES

## L1 and bridge

MAIN_WORLD_SCRIPT = chrome_extension/capture/passive_capture_main.js
FETCH_INTERCEPT = Existing fetch wrapper; clone only; original response remains readable
XHR_INTERCEPT = Existing open/send wrapper; loadend observation; original send preserved
WRAPPER_IDEMPOTENCY = PASS
EXTRA_L1_NETWORK_REQUESTS = 0 in deterministic tests; real-network verification pending
BRIDGE_LOCATION = chrome_extension/content/passive_capture_bridge.js
BRIDGE_COMPLETE = YES
BRIDGE_TOKEN_IMPLEMENTATION = crypto.getRandomValues, 128-bit token per document
BRIDGE_TOKEN_VALIDATION = PASS; trusted token obtained by background MAIN scripting, not page bootstrap
POSTMESSAGE_VALIDATION = source window, HTTPS origin, namespace/type, token, endpoint/path, method, profile, timestamp, object payload
PAYLOAD_SANITIZATION = Allowlist of item IDs, captions, timestamp, counts, optional author handle/pinned; no headers/cookies/credentials
TARGET_ENDPOINT_FAMILIES = /api/post/item_list/, /api/user/detail/, /api/comment/list/

Only item-list content is consumed. The other endpoint families forward no user/contact/comment
payload. A response carries at most 100 items; pending replay holds at most 10 envelopes.
Fetch clones with streams are capped at 3 MB; oversized declared responses/text XHR are ignored.
Replay means replaying sanitized local envelopes, never network requests.

The token is a transport guard, not proof of TikTok authenticity against hostile same-origin
scripts that can observe postMessage. Incoming content remains untrusted, sanitized and requires
explicit user import. No permission or CSP expansion was made.

## Parser, fallbacks and session

AUTHORITATIVE_FIXTURE = tests/fixtures/tiktok/item_list_normal.json
FIXTURE_SOURCE_TYPE = Existing repository fixture documented by the retained parser tests as a sanitized, structure-preserving manually captured response
FIXTURE_SANITIZED = YES; reused unchanged, not represented as a newly collected real response
NETWORK_PARSER_LOCATION = chrome_extension/platform/tiktok_network.js
NETWORK_FIELDS_CAPTURED = video_id, caption, views, likes, comments, shares, createTime; author/pinned only when supplied
NETWORK_MISSING_VALUE_BEHAVIOR = null/missing; true zero preserved
L2_HYDRATION_LOCATION = chrome_extension/platform/tiktok.js::discoverTikTokContent
L2_FALLBACK_BEHAVIOR = Embedded page JSON only, explicit hydration/medium provenance
L3_DOM_LOCATION = Same collector; visible current-profile video links only
L3_FALLBACK_BEHAVIOR = Explicit dom/low provenance; no invented metrics/timestamps
LAYER_PRECEDENCE = L1 > L2 > L3
FIELD_MERGE_POLICY = By exact video_id; higher layer wins; absent data cannot overwrite valid values; same-layer later observation wins
SESSION_BUFFER_LOCATION = capture/tiktok_capture_session.js + content/tiktok_capture_runtime.js
VIDEO_ID_DEDUPE = PASS; at most 200 IDs per tab session
SESSION_ISOLATION = Per isolated tab/profile, random session ID; navigation/reset isolation; pre-reset in-flight observations rejected
PROVENANCE_MODEL = field_provenance plus existing per-metric source and observed_at; observation time is not publication time
CONFIDENCE_MODEL = L1 high / L2 medium / L3 low; missing confidence stays missing

Hydration needs a matching author or matching visible profile video ID. Unknown/feed identity is
not imported. Fallback parsing failure is explicit and does not discard already-valid L1 data.

CAPTCHA_DETECTION = Visible CAPTCHA selectors or CAPTCHA path; synthetic coverage PASS
LOGIN_WALL_DETECTION = Login path / visible login modal or dialog form; synthetic coverage PASS
CHALLENGE_BEHAVIOR = Sticky stop and clear; explicit reset after user resolves normally; import rechecks current page
CAPTCHA_BYPASS = NO
AUTO_SCROLL_PRESENT = NO
AUTO_SCROLL_BOUNDS = N/A
AUTO_SCROLL_CADENCE = N/A

## Preview and authoritative import

PREVIEW_FLOW = Existing floating assistant; source/confidence by field; explicit new-session button; stale videos cleared on failure
IMPORT_FLOW = Explicit user import -> existing /api/extension/import -> CreatorService -> SQLiteCreatorRepository
AUTHORITATIVE_IMPORT_JOIN = PASS, isolated SQLite integration using the actual extension-generated payload
IMPORT_IDEMPOTENCY = PASS under existing observation semantics
CREATOR_ACCOUNT_IDENTITY_BEHAVIOR = Repeated import reuses Creator/account IDs; no display-name merge

Each capture contains one logical row per video ID. Separate imports retain separate capture
observations as required by the existing snapshot contract; this is not duplicate CreatorAccount
creation. Provenance is retained in existing analysis JSON, without adding schema columns.
Preview/import is capped at the existing backend's 20-video bound.

INSTAGRAM_SHARED_CODE_CHANGED = Only conditional TikTok metadata and UI branches in shared modules; Instagram parser unchanged
INSTAGRAM_REGRESSION_TESTS = PASS in canonical extension suite, including profile/API/fallback/import tests
MANIFEST_CHANGED = YES
MANIFEST_CHANGES = Two TikTok-only document_start entries, MAIN observer and ISOLATED receiver/session
NEW_PERMISSIONS_ADDED = NO
ACTIVE_PER_VIDEO_FETCH = NO
M8_4_TRACKING_ADDED = NO
AUTO_CAMPAIGN_BINDING = NO

## Changed files for this slice

- `chrome_extension/background.js`
- `chrome_extension/capture/passive_capture_main.js`
- `chrome_extension/capture/passive_capture_protocol.js`
- `chrome_extension/capture/tiktok_capture_session.js` (new)
- `chrome_extension/content/passive_capture_bridge.js`
- `chrome_extension/content/tiktok_capture_runtime.js` (new)
- `chrome_extension/content/floating_assistant.js`
- `chrome_extension/core/content_analysis.js`
- `chrome_extension/manifest.json`
- `chrome_extension/platform/tiktok.js`
- `chrome_extension/platform/tiktok_network.js`
- `chrome_extension/services/local_api.js`
- `chrome_extension/tests/phase_2.test.mjs`
- `tests/test_m3_1_passive_capture_bridge.js`
- `tests/test_m3_1_tiktok_item_list_parser.mjs`
- `tests/test_pre_m8_legacy_closure_contracts.py`
- `tests/test_m8_3_t_tiktok_passive_capture.mjs` (new)
- `tests/test_m8_3_t_tiktok_passive_import.py` (new)
- `tests/test_m8_3_t_tiktok_preview.js` (new)
- `docs/post_m8_tiktok_passive_capture_v2.md`
- `docs/m8_3_t_completion_report.md` (new)

The old manifest-disabled assertions and active-detail-fetch assertions were updated to the new
explicit contract, not removed without replacement. Wrapper safety, security, parser and import
assertions remain covered. Unrelated dirty files in app/webapp/tests belong to preceding work.

## Verification

TESTS_ADDED = Three focused M8.3-T files; retained wrapper/parser tests extended
CANONICAL_PYTHON = PASS: python scripts/run_python_tests.py --verbosity 1; 790 tests, 395.571s, skipped=1
EXTENSION_TESTS = PASS: node tests/run_extension_tests.js; 47 files
FRONTEND_TESTS = PASS: real floating-assistant code exercised with isolated fake DOM
JS_TESTS = PASS for canonical and M8.3-T suites; optional old core.test.mjs has a pre-existing failure described below
JS_SYNTAX = PASS: node tests/run_extension_tests.js --syntax; 26 extension files; both new JS tests also checked
COMPILEALL = PASS: python -m compileall app
GIT_DIFF_CHECK = PASS: git diff --check
PRODUCTION_DATA_MUTATED = NO

Final targeted Python rerun passed after final JS refinements. Additional direct extension internal
tests phase_1_1, phase_2, and floating_assistant_guard passed. The optional `node --test` wrapper hit
spawn EPERM in this managed environment; the underlying direct Phase 2 test passed.

`chrome_extension/tests/core.test.mjs:76` fails because its expected Creator payload keys omit
`agency_id`. HEAD already includes `agency_id` in local_api.js, and this test file is unchanged.
This is a pre-existing assertion mismatch, not classified as environment blocked or silently
reported as PASS. It is outside the canonical runner and was not repaired in this TikTok slice.

## Real runtime gate

REAL_TIKTOK_E2E_ACCEPTANCE = NOT_RUN
REAL_E2E_EVIDENCE = Browser inventory only; user's normal Chrome is connected, no verified candidate extension plus isolated import runtime acceptance session
EXTRA_REQUEST_E2E_EVIDENCE = NOT_RUN; zero-additional-request evidence is deterministic, not live network evidence
IMPORT_E2E_EVIDENCE = Synthetic fixture -> actual extension serializer -> actual Python import -> isolated SQLite PASS; live TikTok import NOT_RUN
KNOWN_LIMITATIONS = DOM/challenge selectors and current real response shape still require browser validation; exact profile identity required; 20-row import limit
NON_BLOCKING_TECH_DEBT = Pre-existing optional core.test.mjs agency_id expectation
BLOCKERS = Real TikTok L1/zero-extra-request/preview/import E2E and real Instagram smoke acceptance remain pending
TIKTOK_PRODUCTION_SUPPORT = NO
M8_3_T_GATE = BLOCKED_FOR_REAL_E2E
COMMIT = NO
PUSH = NO
BUILD = NOT_RUN
