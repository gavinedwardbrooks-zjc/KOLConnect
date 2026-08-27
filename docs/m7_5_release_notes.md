# M7 Release Notes

> Historical release record: references to OpenClaw describe the interface
> position at release time. OpenClaw was later retired from active architecture;
> KOLConnect Assistant with Feishu long-connection transport is canonical.

Release version: `0.2.3`

## Delivered

- Local authoritative Creator and multi-account management with stable
  `creator_id` and `account_uid` identities.
- Campaign multi-platform selection, multiple execution accounts, multiple
  planned publication dates, and resilient Campaign Detail loading.
- Feishu schema validation, deterministic Dry Run, confirmation-gated Full Sync,
  and reciprocal Creator/Account relations.
- Manual Creator merge, safe Clean Reset, local missing-email scan, and retired
  legacy migration/direct-sync product surfaces.
- M7.2 API envelope compatibility, server trace IDs, OpenAPI documentation, and
  integration boundaries.
- Deterministic Assistant/OpenClaw-facing API with allowlisted tools, privacy
  controls, prompt-injection resistance, and confirmation-gated writes.
- Shared country/follower normalization and grounded Creator Intelligence with
  separate user tags and non-persistent AI tags.
- Explicit Outlook Basic Auth rejection classification and a separate Microsoft
  OAuth2 proposal.

## Known Limitations and Deferred Work

- Microsoft OAuth2 mail authentication is deferred to M7.4a.
- Local Creator hard delete does not yet provide an automatic remote Feishu
  hard-delete lifecycle.
- A stale secondary Creator may remain remotely after local manual merge; normal
  Full Sync repairs account relations but does not physically delete it.
- M8 Published Content, tracking, analytics, URL resolver, Similar Creator,
  recommendation, and Google Sheets are not part of this release.
- M8 numbering is not implementation order. Start with M8.0 architecture audit;
  Google Sheets requires a separate sync architecture audit and must not rewrite
  stable Feishu Sync.

## Acceptance Status

- Automated regression: PASS. Two consecutive full Python runs each completed
  586 tests with 585 passing and 1 skipped; the unified frontend runner passed
  all 39 test files.
- Windows package build: PASS.
- Packaged GUI, real Feishu, and Feishu mobile acceptance: user required.
- Packaged HTTP smoke in the managed environment: environment blocked during
  PyInstaller startup/extraction before the localhost service began listening.
  This does not replace the required Windows GUI acceptance.

## Build

- Canonical Windows format: portable ONEDIR ZIP.
- Directory: `release/KOLConnect_v0.2.3/`
- Executable: `release/KOLConnect_v0.2.3/KOLConnect_v0.2.3.exe`
- Distribution archive: `release/KOLConnect_v0.2.3.zip`
- Extract and retain the complete folder; the EXE is not a standalone distribution.
- File version: `0.2.3.0`
- Product version: `0.2.3`
- Application data and SQLite authority remain under `%APPDATA%\KOLConnect`;
  the executable directory contains runtime files only.

## M7.5a Dashboard Concurrency Hotfix

- Fixed the first packaged Dashboard request incorrectly treating its own
  workbook schema initialization save as an external concurrent modification.
- Dashboard builds now retry the complete response at most twice and cache or
  return a payload only when its before/after workbook fingerprints match.
- A continuously changing workbook still fails closed with the original
  controlled error and trace-correlated, privacy-safe fingerprint diagnostics.
