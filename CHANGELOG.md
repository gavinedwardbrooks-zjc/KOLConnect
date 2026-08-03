# Changelog

KOLConnect 的重要版本变化记录在此文件中。

## v0.2.0-dev.2

> Internal development build. This version is not a stable public release.

### Added

- Creator Library CRM capabilities.
- Creator profile editing.
- Creator Agency assignment management.
- Creator archive and restore.
- Product Management.
- Campaign Management.
- Campaign Detail.
- CampaignCreator collaboration and execution tracking.
- Dashboard analytics based on CampaignCreator data.

### Changed

- CampaignCreator became the primary collaboration model.
- Legacy Cooperation changed to read-only historical compatibility.
- Dashboard migrated to an independent page lifecycle module.
- Creator Library list and detail migrated to independent lifecycle modules.
- Campaign archive state separated from Campaign business status.

### Fixed

- Product list error banner remaining visible after successful loading.
- Campaign list error banner remaining visible after successful loading.
- Frontend page lifecycle, event cleanup, request cancellation, and stale result handling.
- Campaign empty-data handling and missing Product-name fallback.

### Architecture

- Added modular frontend pages under `webapp/pages/`.
- Added page registration and lifecycle infrastructure under `webapp/core/`.
- Added PageResources management for events, timers, and request cancellation.
- Added a shared API Client under `webapp/services/`.
- Improved Repository aggregation for Product, Campaign, Creator, Account, and Agency display data.

### Known Scope

- Agency assignment is supported from Creator records; a standalone Agency management page is not yet implemented.
- Legacy Cooperation remains available for read-only historical review.
- This build uses Excel-based local storage and is intended for internal testing.
