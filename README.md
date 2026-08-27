# KOLConnect

KOLConnect is a local workspace for managing global creators, coordinating influencer campaigns, and keeping day-to-day KOL operations organized.

## Overview

KOLConnect is an overseas KOL / Creator management and marketing collaboration platform. It brings creator records, agency relationships, campaign collaboration, mail operations, and browser-assisted data capture into one local workflow backed by an Excel workbook.

The desktop application is designed for operational teams that need a practical working system without moving their creator data to a hosted database. Recent M4.8 and M4.8.5 work improves workflow clarity, link handling, result-folder access, and everyday interface density.

KOLConnect Assistant is the active AI runtime. Feishu long-connection chat is the supported external conversational entry point, and all actions remain constrained to allowlisted KOLConnect tools and services. OpenClaw has been retired from the active product architecture and requires no host, authentication, or transport deployment.

## Features

### Creator Management

- Creator Library for searching, filtering, reviewing, and maintaining creator records.
- Creator profile, account, snapshot, insight, status, archive, restore, and permanent-delete workflows.
- Agency and agency-contact management, including creator-to-agency relationships.
- Excel import template download, creator import, and selected-creator Excel export.
- Campaign history and collaboration context from Creator detail pages.

### Campaign Management

- Product and Campaign creation, editing, archiving, and removal workflows.
- Campaign lifecycle management using the existing Campaign status model.
- Creator collaboration tracking through CampaignCreator records.
- Collaboration stage, execution account, quote, cost, publish date, publish links, engagement metrics, ROI, and performance-note fields.
- Missing publish-link detection for completed collaborations.
- Campaign Detail shows a read-only list of completed collaborations that still need publish information.

### Risk Management

- Campaign risk cards for high, medium, and low data risks.
- Missing publish-link risks: overdue publish dates without links are high risk; missing dates or future dates without links remain low risk.
- Missing creator-email detection.
- Historical Campaign data checks for missing product or start-date values.
- Read-only risk aggregation API: `GET /api/risks`.
- Campaign-specific missing-publish API: `GET /api/campaigns/{id}/missing-publish-links`.

### Mail Management

- Multiple mail-account configuration and management.
- Reusable mail subject and body templates.
- Recent mail list and operational mail workflows.
- Partial-update protection: saving account settings does not overwrite templates, and saving templates does not overwrite account settings.

### Browser Extension

The included Chrome extension provides browser-assisted capture foundations; results depend on the target platform and the page state available to the browser.

- TikTok page analysis utilities; the historical passive network-import pipeline is retained only as experimental reference and is not enabled in production.
- Instagram public-profile and related API capture support.
- YouTube Shorts metrics support.

The extension is intentionally not described as a guarantee of complete platform coverage or unrestricted data access.

## Screenshots

Screenshots will be added for the Creator Library, Campaign Detail, risk cards, and mail-management workflows.

## Installation

### Windows

Download `KOLConnect_v0.2.3.zip`, extract the entire `KOLConnect_v0.2.3` folder, and run `KOLConnect_v0.2.3.exe` inside that folder. The Windows release is a portable ONEDIR package: do not move or run the EXE without its adjacent `_internal` runtime directory. On first launch, KOLConnect creates its local application data under:

```text
%APPDATA%\KOLConnect
```

This directory contains local settings, logs, task data, and the default Creator Library workbook. Back up operational workbooks before migration or large batch changes.

To upgrade, close KOLConnect, extract the complete new release folder, and launch its EXE. Do not merge old and new `_internal` directories. User data remains under `%APPDATA%\KOLConnect` and is not stored in the release folder.

### Chrome Extension

1. Open `chrome://extensions`.
2. Enable Developer mode.
3. Select **Load unpacked**.
4. Choose the repository's `chrome_extension/` directory.
5. Keep the KOLConnect desktop application running when using extension import workflows.

## Development

KOLConnect uses a local Python backend with a native JavaScript web frontend.

- `app/`: Python HTTP service, services, repositories, storage, and desktop integration.
- `webapp/`: native JavaScript interface, page lifecycle modules, styles, and local assets.
- `chrome_extension/`: Chrome extension source for supported browser capture workflows.
- `tests/`: Python and JavaScript regression coverage.

Excel remains the current source of truth for Creator, Campaign, and related operational data.

## Testing

The repository includes several verification layers:

- Python unit and regression tests for services, repositories, API behavior, storage safety, and migrations.
- JavaScript frontend and Chrome-extension test runner: `node tests/run_extension_tests.js`.
- Authoritative Python regression runner: `python scripts/run_python_tests.py`. Raw `python -m unittest discover ...` is not authoritative unless it is already running inside the repository test sandbox.
- Python compile check: `python -m compileall app`.
- Diff whitespace check: `git diff --check`.

Test suites are intentionally reported by their actual runtime results rather than a fixed published test count.

## Roadmap

The following items are planned and are not described above as current product capabilities:

- **Planned: M5.1 Health visualization**
- **Planned: M5.3 Advanced analytics**
- **Planned: M5.4 Final polish**
- **Planned: M6 Browser mode**

## Version History

### v0.2.4

- M4.8.5 UX improvements and workflow polish.
- Mail partial-update safety hotfix.
- M5.2 publish-link tracking and Campaign risk cards.

## License

This project is licensed under the [MIT License](LICENSE).
