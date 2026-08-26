# PRE-M8 SQLite Performance and Synthetic Acceptance

Status: `C11_C12_ENGINEERING_PASS_PRODUCTION_MIGRATION_NOT_AUTHORIZED`

Evidence date: 2026-08-26

## Environment

- OS: Windows 11 build 26200, 64-bit
- Python: 3.14.3, MSC v.1944 AMD64
- SQLite: 3.53.1, runtime gate PASS
- CPU inventory: unavailable because the managed environment denied WMI access
- Timing: `time.perf_counter()`, deterministic seed, isolated repository sandboxes
- Warmup: one unmeasured call per operation unless explicitly cold
- Samples: five for reads; three to five for writes; p95 is the nearest-rank sample

Generated databases, XLSX files, backups, and JSON evidence live only under
`.pre_m8_batch3_benchmark/` and `.pre_m8_batch3_acceptance/`; both are ignored.
No production workbook, authority marker, or application-data directory was used.

## Fixtures

| Dimension | Medium | Large |
|---|---:|---:|
| Creators | 2,500 | 10,000 |
| CreatorAccounts | 3,000 | 15,000 |
| Videos | 5,000 | 20,000 |
| CreatorSnapshots | 5,000 | 20,000 |
| VideoSnapshots | 25,000 | 100,000 |
| Campaigns | 100 | 400 |
| CampaignCreators | 2,500 | 10,000 |
| Products | 20 | 80 |
| Insights | 2,500 | 10,000 |

Both fixtures contain multi-account Creators, archives, null metrics and
quote/cost, tags, three platforms, selected execution Accounts, and multiple
planned publish dates.

## Runtime Results

All values are milliseconds (`p50 / p95 / max`).

| Operation | Medium | Large |
|---|---:|---:|
| Creator Library initial | 603.305 / 725.123 / 725.123 | 2915.016 / 3117.495 / 3117.495 |
| Cached pagination | 10.607 / 14.451 / 14.451 | 43.378 / 43.531 / 43.531 |
| Country filter | 6.439 / 8.493 / 8.493 | 48.723 / 56.249 / 56.249 |
| Platform filter | 7.599 / 7.680 / 7.680 | 42.555 / 47.505 / 47.505 |
| Followers filter | 6.639 / 7.109 / 7.109 | 26.046 / 36.340 / 36.340 |
| Combined filter | 3.021 / 3.788 / 3.788 | 19.629 / 20.874 / 20.874 |
| Creator Detail | 56.151 / 63.160 / 63.160 | 214.117 / 287.833 / 287.833 |
| Campaign list | 263.566 / 310.220 / 310.220 | 1055.472 / 1361.779 / 1361.779 |
| Campaign Detail | 227.014 / 240.158 / 240.158 | 916.765 / 982.623 / 982.623 |
| Campaign members | 582.680 / 597.899 / 597.899 | 2347.754 / 2422.521 / 2422.521 |
| Creator snapshot history | 76.233 / 81.291 / 81.291 | 224.338 / 234.546 / 234.546 |
| Dashboard cold | 311.831 / 384.423 / 384.423 | 1123.711 / 1264.321 / 1264.321 |
| Dashboard warm | 37.107 / 44.557 / 44.557 | 104.960 / 143.858 / 143.858 |
| VideoSnapshot latest | 3.400 / 4.150 / 4.150 | 3.747 / 4.233 / 4.233 |
| VideoSnapshot history | 4.224 / 4.725 / 4.725 | 3.894 / 4.536 / 4.536 |

## Durable Writes

| Operation | Medium p50/p95/max | Large p50/p95/max |
|---|---:|---:|
| Creator update | 11.544 / 12.667 / 12.667 | 9.634 / 14.712 / 14.712 |
| Account-affecting Creator update | 10.133 / 13.960 / 13.960 | 9.963 / 12.954 / 12.954 |
| Campaign update | 249.461 / 321.126 / 321.126 | 869.918 / 920.739 / 920.739 |
| Campaign membership update | 477.418 / 524.474 / 524.474 | 2377.644 / 2852.721 / 2852.721 |
| Snapshot append | 16.339 / 17.667 / 17.667 | 28.923 / 37.827 / 37.827 |

The Account measurement uses the existing Creator mutation contract that updates
the primary Account follower projection; no independent Account-edit API exists.
Every write includes `BEGIN IMMEDIATE`, commit, and business revision update.

## Backup, Export, and Migration

| Operation | Medium | Large |
|---|---:|---:|
| Online SQLite backup p95 | 145.082 ms | 428.564 ms |
| SQLite to XLSX export | 4.434 s, 2,647,343 B | 18.148 s, 10,467,233 B |
| Main DB after workload | 12,767,232 B | 50,683,904 B |
| WAL after explicit checkpoint | 0 B | 0 B |

The representative Medium C3 migration used a 2,646,849-byte XLSX and imported
2,500 Creators, 3,000 Accounts, 5,000 Videos, 5,000 CreatorSnapshots, 25,000
VideoSnapshots, 100 Campaigns, and 2,500 CampaignCreators in 15.990 seconds.
The staged DB was 12,763,136 bytes. Source SHA256 before and after was
`136aefa3409e25461577cb085af40e4c8249a9ad986b8e7b1e518298217f85e4`.
It stopped at `ready_for_activation`; activation was not performed.

## Query Plans and N+1

EXPLAIN confirms indexed searches for Creator primary identity,
`idx_creator_accounts_creator`, `idx_creator_snapshots_creator_time`,
`idx_video_snapshots_video_time`, and `idx_campaign_creators_campaign`.

Measured SELECT counts are independent of result cardinality:

| Projection | SELECT count |
|---|---:|
| Creator Library | 12 |
| Creator Detail | 13 |
| Campaign Detail | 12 |
| Dashboard | 9 |

Before Batch 3 hardening, Creator tags and Campaign relation children produced
2,511 and 7,608 SELECTs at Medium scale. They are now bulk-prefetched. Dashboard
uses two set-based business reads and does not materialize a workbook.

## Concurrency

The mixed workload completed in 3.411 seconds at Medium and 13.484 seconds at
Large. It combined 20 Creator reads and 10 Campaign reads across six workers.
Focused tests additionally mix reads with bounded writes and prove thread-affine
connections, no deadlock, no corruption, and no lost commit. No persistent
`SQLITE_BUSY` storm occurred.

## Gates

- Medium common p95 reads <2s: PASS
- Medium durable writes <3s: PASS
- Large common p95 reads <5s: PASS
- Large durable writes <10s: PASS
- Export/migration: reported separately, not treated as online operations

Historical Excel evidence was 17-34 seconds for reads and about 272 seconds for
a write. Those runs differ in storage architecture and methodology, so no
percentage improvement is claimed.

## Final Synthetic Cutover

The C12 harness created a legacy workbook with 100 Creators, 102 Accounts, 1,000
CreatorSnapshots, 1,000 VideoSnapshots, and all supported business entities. It
ran the real C3 migration and activation primitives in an isolated sandbox.

- authority before: `legacy_excel`
- authority after: `sqlite`
- source SHA256 before/after migration:
  `bc6b5902e03b862eaddcf76464c56e21f864630631969c1194a410af1a0870bb`
- legacy Excel edits ignored after activation: PASS
- SQLite writes do not touch Excel: PASS
- restart: PASS
- online backup/restore: PASS
- XLSX export and fresh C3 reimport: PASS
- multi-account ownership and Campaign execution Accounts: PASS

An acceptance run exposed and fixed semantic validation of legacy `account_id`
versus canonical `account_uid` during export/reimport. The validator now maps
both representations through the existing identity contract; validation was not
weakened.

## Future Production Acceptance (Not Authorized Yet)

After explicit human authorization only:

1. Close the old EXE.
2. Back up the production workbook.
3. Launch the approved build.
4. Execute the explicit migration.
5. Verify Dashboard and Creator Library.
6. Verify a known multi-account Creator.
7. Verify Campaign data.
8. Restart and verify the same authority and records.
9. Export a compatibility workbook.
10. Preserve the original historical workbook.

This Batch 3 stops before step 4 on real data.
