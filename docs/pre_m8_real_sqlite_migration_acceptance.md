# PRE-M8 Real SQLite Migration Acceptance

Status: `NOT_EXECUTED_REQUIRES_EXPLICIT_USER_ACCEPTANCE`

This checklist is for a later, explicitly authorized Windows acceptance. Do not
run it until the approved release has passed review. The migration preserves the
historical `Creator_Library.xlsx`; SQLite becomes the only runtime authority only
after the user confirms the prepared and validated plan.

## Current Reference Evidence

- Expected Creators: `4`
- Expected CreatorAccounts: `6`
- Expected Campaigns: `1`
- Expected CampaignCreators: `3`
- Pre-migration workbook SHA256:
  `25FBF6DAFB7EA48BD9F21E8DA93ED22836744A280C96B918062436E5F31A4966`

Counts are acceptance references, not hard migration limits. Legitimate changes
before migration must be reviewed rather than rejected solely for differing counts.

## User Acceptance Sequence

1. Close every running KOLConnect EXE.
2. Verify the approved Git/release identity and executable SHA256.
3. Start the approved EXE.
4. Open Settings, then **本地数据存储升级**.
5. Run **检查迁移**, then **开始准备**. Do not confirm yet.
6. Verify source Creator, Account, Campaign, and CampaignCreator counts.
7. Verify the migration backup is reported as created.
8. Read the confirmation text and explicitly choose **确认迁移到 SQLite**.
9. Wait until Settings reports `SQLite 已启用`.
10. Verify Dashboard loads and totals are plausible.
11. Verify Creator count.
12. Verify Account count.
13. Verify Campaign and CampaignCreator counts.
14. Verify a known multi-account Creator retains every Account.
15. Close and restart the EXE.
16. Verify authority remains SQLite and the same records are visible.
17. Export a current XLSX compatibility workbook and inspect it.
18. Recompute the original historical workbook SHA256 and verify it is unchanged.

After migration, do not edit the historical workbook expecting live application
changes. Use KOLConnect for mutations and SQLite-to-Excel export for a current
spreadsheet copy. Preserve the original workbook and migration backup.
