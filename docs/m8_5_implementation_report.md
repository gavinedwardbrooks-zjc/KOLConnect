# M8.5 Performance Analytics + Historical Performance

## Baseline and scope

- HEAD / origin/main: `e86a81d084d64c82abbb86af5983a1cc8d1a7c87`.
- PRE_M8_5_DIRTY_COUNT = 60. Existing M8 work was retained, not reverted.
- SQLite remains authoritative; schema remains v4. No schema migration was added by M8.5.
- Production data, production APPDATA, real capture and external services were not used for validation.

### PRE_M8_5_DIRTY_FILES

```text
README.md
app/campaign_creator_repository.py
app/creator_repository.py
app/http_handlers/campaign_handler.py
app/http_handlers/creator_handler.py
app/repository_factory.py
app/scraper.py
app/server.py
app/services/campaign_creator_service.py
app/services/creator_service.py
app/storage/schema.py
app/storage/sqlite_creator_repository.py
chrome_extension/background.js
chrome_extension/capture/passive_capture_main.js
chrome_extension/capture/passive_capture_protocol.js
chrome_extension/content/floating_assistant.js
chrome_extension/content/passive_capture_bridge.js
chrome_extension/core/content_analysis.js
chrome_extension/manifest.json
chrome_extension/platform/tiktok.js
chrome_extension/platform/tiktok_network.js
chrome_extension/services/local_api.js
chrome_extension/tests/phase_2.test.mjs
docs/post_m8_tiktok_passive_capture_v2.md
tests/test_m3_1_passive_capture_bridge.js
tests/test_m3_1_tiktok_item_list_parser.mjs
tests/test_phase4_2_task_lifecycle.py
tests/test_pre_m8_9_documentation_contract.py
tests/test_pre_m8_item_12_actual_publications.py
tests/test_pre_m8_item_7_multicurrency_quote.py
tests/test_pre_m8_legacy_closure_contracts.py
tests/test_pre_m8_sqlite_storage_foundation.py
webapp/index.html
webapp/pages/campaign-detail.js
webapp/pages/creator-library-detail.js
webapp/styles.css
app/domain/creator_url_resolver.py
app/repositories/publication_performance_repository.py
app/services/creator_similarity_engine.py
app/services/email_url_capture_service.py
app/services/publication_tracking_service.py
app/services/similar_creator_search_service.py
app/services/similarity_explanation.py
chrome_extension/capture/tiktok_capture_session.js
chrome_extension/content/tiktok_capture_runtime.js
docs/m8_3_t_completion_report.md
tests/test_m8_1_similar_creator_search.py
tests/test_m8_1_similar_creator_ui.js
tests/test_m8_2_similarity_engine.py
tests/test_m8_2_similarity_ui.js
tests/test_m8_3_campaign_publication_ui.js
tests/test_m8_3_campaign_publications.py
tests/test_m8_3_t_observability.mjs
tests/test_m8_3_t_tiktok_passive_capture.mjs
tests/test_m8_3_t_tiktok_passive_import.py
tests/test_m8_3_t_tiktok_preview.js
tests/test_m8_4_publication_tracking.py
tests/test_m8_4_publication_tracking_ui.js
tests/test_m8_6_creator_url_resolver.py
tests/test_m8_7_email_url_capture.py
```

### PREEXISTING_DIRTY_FILES_TOUCHED_WITH_REASON

| File | M8.5-only reason |
|---|---|
| `app/http_handlers/campaign_handler.py` | Campaign and nested Publication analytics GET routes; existing M8.3/M8.4 writes retained. |
| `app/http_handlers/creator_handler.py` | Creator historical-performance GET route. |
| `app/server.py` | Inject existing observation repository and historical-evidence provider. |
| `app/repositories/publication_performance_repository.py` | Scoped, parameterized batch analytics SELECT; no observation write changes. |
| `app/services/similar_creator_search_service.py` | Attach read-only historical evidence after unchanged base ranking. |
| `webapp/index.html` | Add analytics sections inside current Campaign/Creator pages. |
| `webapp/pages/campaign-detail.js` | Totals, coverage, deterministic highlights, trend table; batch hydration replaces per-Publication initial GETs. |
| `webapp/pages/creator-library-detail.js` | Historical performance and recommendation evidence rendering. |
| `webapp/styles.css` | Responsive styles for these sections only. |
| `tests/test_m8_4_publication_tracking_ui.js` | Verify latest-observation hydration from the new batch read, retaining refresh checks. |

PREEXISTING_DIRTY_FILES_UNTOUCHED = the other 50 files in PRE_M8_5_DIRTY_FILES, including README, schema, scraper, all extension files and TikTok diagnostics.

### Additional M8.5 changes

- `app/services/analytics_service.py`: extend the existing service with scoped analytics methods.
- `app/services/performance_analytics.py`: new pure projections over Publication observation history.
- `tests/test_m8_5_performance_analytics.py`: deterministic analytics, real isolated SQLite and route tests.
- `tests/test_m8_5_performance_ui.js`: executable DOM rendering and stale-response tests, plus UI contract checks.
- `tests/test_phase3_10_campaign_detail_ui.js`: explicit performance fixture and URL-set assertion for four initial GETs; old interaction assertions retained.
- `docs/m8_5_implementation_report.md`: this report.

M8_5_FILES_CHANGED = the 10 scoped pre-existing files above plus these 6 files (16 total).

## Analytics contracts

ANALYTICS_SERVICE_LOCATION = `app/services/analytics_service.py`.
HISTORICAL_PERFORMANCE_SERVICE_LOCATION = the same service, using pure functions in `app/services/performance_analytics.py`.
OBSERVATION_SOURCE = canonical Publication + `publication_performance_observations`, joined by `publication_id`.
LEGACY_VIDEOSNAPSHOT_USED_AS_ANALYTICS_AUTHORITY = NO.

- PUBLICATION_TREND_CONTRACT = full observation series ordered by actual `observed_at` time, stable observation-ID tie-break. Original timestamps, nullable metrics and provenance retained; no interpolation.
- GROWTH_ABSOLUTE_FORMULA = latest valid metric minus first valid metric.
- GROWTH_PERCENT_FORMULA = absolute delta / first valid metric * 100.
- ZERO_DENOMINATOR_BEHAVIOR = percentage null; absolute delta preserved.
- MISSING_ENDPOINT_BEHAVIOR = select valid endpoints independently per metric; fewer than two valid observations means growth null.
- NEGATIVE_DELTA_BEHAVIOR = negative delta preserved with `status=decrease`; equal values produce real zero with `status=unchanged`.
- VIEWS_GROWTH / LIKES_GROWTH / COMMENTS_GROWTH / ER_GROWTH = implemented and covered by focused tests.
- ER uses the already stored M8.4 authoritative ER: `(likes + comments) / views * 100`, only when all required inputs are valid. M8.5 does not invent ER from missing inputs. ER absolute change is in percentage points.

CAMPAIGN_LATEST_METRIC_RULE = latest valid value per Publication per metric, not latest row with missing metrics coerced to zero.
TOTAL_VIEWS_CONTRACT / TOTAL_LIKES_CONTRACT / TOTAL_COMMENTS_CONTRACT = sum valid latest values, return null if none; explicit zero remains valid.
TOTAL_COVERAGE_OUTPUT = `valid_count`, `missing_count`, `total_publications` per metric.
AVERAGE_ER_CONTRACT = arithmetic mean of one latest valid ER per Publication, not all observations.
AVERAGE_ER_COVERAGE = `valid_er_count`, `total_publications`.

- TOP_VIDEO_CONTRACT = highest latest valid views, then highest latest valid ER, then stable publication ID.
- TOP_CREATOR_CONTRACT = sum latest valid views across the Creator's Campaign Publications, then average valid ER, then stable Creator ID; valid/publication counts returned.
- HIGHEST_ER_CONTRACT = highest latest valid ER, then stable publication ID.
- FASTEST_GROWING_CONTRACT = eligible Publication with greatest unrounded views/day, stable publication ID tie-break.
- FASTEST_GROWING_FORMULA = `(latest_valid_views - first_valid_views) / elapsed_days`; elapsed duration must be positive.
- FASTEST_GROWING_WINDOW_OUTPUT = start/end observed timestamps, elapsed days/seconds, views delta and growth rate. Negative rates remain negative.

COOPERATION_IDENTITY = `CampaignCreator.id`.
COOPERATION_COUNT_BEHAVIOR = distinct existing active relations, independent of Publication/observation count.
HISTORICAL_CAMPAIGN_BEHAVIOR = dedupe by campaign ID, retain real status/start/end fields. Current read scope excludes archived relations and archived Campaigns; it does not infer completion from metrics.
AVERAGE_HISTORICAL_VIEWS_CONTRACT / AVERAGE_HISTORICAL_ER_CONTRACT = one latest valid metric per Publication, arithmetic average with coverage. `actual_account_uid` and platform stay attributable in Publication evidence.

## Money and recommendation contracts

- MONEY_COST_SOURCE = confirmed/payable `CampaignCreator.cost`; `creator_quote` is never substituted.
- MULTICURRENCY_BEHAVIOR = existing `domain.money.grouped_amounts` groups known currencies; unknown-currency records are counted separately, not silently combined. No scalar mixed-currency total.
- FX_IMPLEMENTED = NO.
- CPV_CONTRACT = same-currency confirmed cost / latest valid views of its costed relations' Publications. Every Publication in that cost scope must have valid views, and total views must be positive.
- CPE_CONTRACT = the same scope, using valid likes + comments only; both must exist for every scoped Publication and total engagement must be positive. Shares are not added.
- Efficiency responses expose costed cooperation count, Publication count and denominator completeness. Ratios use six decimal places; display may be more compact.
- ROI_INPUT_AVAILABLE = NO authoritative economic return input. The existing legacy recorded ROI field is not a revenue model.
- ROI_BEHAVIOR = null with `AUTHORITATIVE_RETURN_INPUT_UNAVAILABLE`; no inferred ROI.
- M8_2_FEEDBACK_IMPLEMENTATION = append `historical_performance_summary` and `historical_performance_evidence` after existing deterministic ranking; display evidence separately.
- M8_2_BASE_SCORE_CHANGED = NO. Nominal weights remain 30/20/15/15/10/5/5; no hidden weight or reranking.
- HISTORICAL_PERFORMANCE_SIGNAL = cooperation/Publication counts and latest-valid averages from local observation history; absent history is not fabricated.
- AI_ROLE = optional existing explanation only, not metric generation, currency conversion or score authority.

## API and UI

```text
GET /api/campaigns/{campaign_id}/performance
GET /api/creator-library/{creator_id}/historical-performance
GET /api/campaign-creators/{campaign_creator_id}/publications/{publication_id}/performance
```

Existing M8.4 latest/history/refresh endpoints remain intact. Campaign/Creator existence is checked through existing identity paths; nested Publication analytics verifies relation ownership.

CAMPAIGN_UI_CHANGES = totals with coverage, Top Creator/Video, highest ER, fastest views/day with actual interval, currency-grouped costs/quotes, and unchanged explicit refresh controls.
PUBLICATION_TREND_UI = lightweight chronological table for views/likes/comments/ER, plus metric-specific deltas and windows. No new chart dependency. Publication/account identity is visible.
CREATOR_HISTORY_UI = cooperation/Campaign counts, latest-valid averages and coverage, historical Campaign list, grouped costs/quotes, CPV/CPE and explicit unavailable ROI.
EMPTY_DATA_BEHAVIOR = unavailable metrics shown as dash, not demo values; no-history message.
SPARSE_DATA_BEHAVIOR = null cells retained, coverage exposed, true zero rendered as zero. Stale analytics reload responses cannot replace the current lifecycle.

## Query and safety evidence

INDEXES_ADDED = NONE.
INDEX_EVIDENCE = isolated SQLite fixture runs the actual repository SELECT with trace capture and EXPLAIN QUERY PLAN. Campaign lookup uses `idx_campaign_creators_campaign`; Publication join uses its relation index; observation join uses existing `publication_id` index (optimizer selected the unique operation index). No observation table scan and no per-Publication database query. Ordered full history requires an in-memory SQLite sort; no new index was justified.

Creator history uses a creator-ID filter; recommendation history uses one `IN (...)` batch for selected candidates. Publication detail uses relation and Publication filters. Empty candidate IDs return without querying. Campaign UI uses one batched performance GET rather than N initial latest requests.

PLATFORM_ACQUISITION_ADDED = NO.
M8_3_T_REOPENED = NO; TikTok production support remains NO / DEFERRED.
SCHEDULER_ADDED = NO.
PRODUCTION_DATA_MUTATED = NO.
M8.8 / M8.9 implementation = NOT STARTED.

## Validation

TESTS_ADDED = 10 Python methods plus executable JS rendering/async tests.

- Focused M8.5 Python: 10/10 PASS using the canonical sandbox runner.
- M8.4 tracking regression: 6/6 PASS.
- M8.2 similarity regression: 26/26 PASS.
- Initial canonical full Python: 805 tests, OK (skipped=1), 297.585s. This preceded the final boundary refinements.
- CANONICAL_PYTHON = PASS, final-tree `python scripts/run_python_tests.py --verbosity 1`: 806 tests, OK (skipped=1), 278.097s.
- FRONTEND_TESTS / JS_TESTS = PASS, unified `node tests/run_extension_tests.js`, 50 files.
- JS_SYNTAX = PASS, all 14 webapp JavaScript files checked with `node --check`; focused JS test also executed.
- COMPILEALL = PASS, `python -m compileall app`.
- GIT_DIFF_CHECK = PASS. Existing LF/CRLF advisory messages are not whitespace errors.

KNOWN_LIMITATIONS = no approved production metric provider; empty production observations legitimately yield unavailable analytics. The trend UI is a time-series table, not a graphical chart. No scheduler, FX, economic ROI, archived-Campaign history expansion or real-data manual acceptance was added. Very long histories are returned in full; pagination is not part of this slice.
NON_BLOCKING_TECH_DEBT = optional future trend chart/history pagination and separately approved metric providers.
BLOCKERS = NONE for this analytics slice; no production metric acquisition or manual real-data acceptance is claimed.
M8_5_STATUS = COMPLETE.
M8_5_GATE = PASS (automated engineering acceptance).
COMMIT = NO.
PUSH = NO.
BUILD = NOT RUN.
