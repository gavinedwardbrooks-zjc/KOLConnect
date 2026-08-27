# M7.5 User Acceptance Checklist

Automated tests do not replace the following real Windows, Feishu, and mobile
checks. Do not run destructive operations without reviewing the displayed plan.

## Windows Package

- [ ] Extract the complete `KOLConnect_v0.2.3.zip` archive.
- [ ] Start `KOLConnect_v0.2.3\KOLConnect_v0.2.3.exe`; do not run the EXE without its adjacent `_internal` directory.
- [ ] Confirm the local UI loads and Settings reports version `0.2.3`.
- [ ] Open Dashboard immediately after startup and confirm no
      `Dashboard workbook changed while building its response` error appears.
- [ ] Refresh Dashboard at least five times and confirm KPI, Health, Risk, and
      chart sections continue loading without a concurrency popup.
- [ ] Close and reopen the EXE, then confirm the first Dashboard load remains
      successful after startup.
- [ ] Open Creator Library and test country, follower, and AI-tag filters.
- [ ] Open a Creator with TikTok, Instagram, and YouTube accounts.
- [ ] Switch accounts and confirm platform, username, profile URL, followers,
      account metrics, and follower band change without changing Creator name,
      `creator_id`, user tags, or Creator-level summary.
- [ ] Confirm no account follower values are added together.
- [ ] Create an unrestricted Campaign and a multi-platform Campaign.
- [ ] Add one multi-account Creator with multiple execution accounts and
      multiple planned publication dates.
- [ ] Confirm Campaign Detail loads with zero Creators and sparse optional data.
- [ ] Confirm an optional missing-publish widget failure does not produce a
      full-page Campaign error.
- [ ] Confirm the email action says `扫描达人库缺失邮箱`; no old Feishu email-scan
      or capture-page direct Feishu-sync action is visible.
- [ ] Test read-only Assistant queries and confirm every write requires preview,
      a confirmation token, and explicit confirmation.

## Feishu Desktop Acceptance

1. Open Settings -> 飞书数据同步.
2. Run Validate and record PASS/FAIL: __________.
3. Run Dry Run. Record Creator create/update: __________ / __________.
4. Record Account create/update: __________ / __________.
5. Record relation add/update/remove: __________ / __________ / __________.
6. Record conflicts and exact reasons: ________________________________.
7. Review the complete plan. Run Full Sync only after explicit user approval.
8. Open the Creator table and verify count, `creator_id`, name, archived state,
   and `社媒账号` relations.
9. Open the Account table and verify `account_uid`, platform, profile URL,
   followers, and reverse `达人` relation.
10. Select a multi-account Creator: it must link to all corresponding Account
    records, and each Account must link back to the same Creator.
11. Run Dry Run again. Target: zero create, update, relation mutation, and
    conflict. Document every reasonable nonzero field and reason; do not simply
    declare convergence.

Full Sync acceptance: PASS / FAIL / NOT RUN: __________.

## Feishu Mobile Acceptance

- [ ] In the Feishu mobile app, open Creator and Account Bitable tables.
- [ ] Open a Creator detail and follow its relation to Account records.
- [ ] Verify name, platform, profile link, followers, and relations are readable.
- [ ] Verify a multi-account Creator can reach each account and each account
      links back to the Creator.
- [ ] Record any Bitable mobile presentation issue as `PLATFORM_UI_LIMITATION`;
      do not request a separate KOLConnect mobile frontend for M7 closure.

Mobile result: PASS / FAIL / PLATFORM_UI_LIMITATION: __________.

## Standard IMAP/SMTP Acceptance

- [ ] Save a provider configuration and confirm the UI says configuration saved.
- [ ] Test authentication separately with a password/app password supported by that provider.
- [ ] Confirm Basic-auth rejection remains distinct from settings-save failure.
- [ ] Confirm no password, token, or raw Python/server payload is displayed.

Microsoft OAuth2 and guaranteed Outlook/Microsoft 365 compatibility are not supported by this
release. Future OAuth2 work would be a new product feature.
