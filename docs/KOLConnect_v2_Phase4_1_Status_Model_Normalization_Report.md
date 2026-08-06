# KOLConnect v2 Phase 4.1 Status Model Normalization Report

## 1. 修改文件

- `app/scraper.py`
  - 将抓取访问结果与数据可用状态分离。
  - 新增 `status_reason` 字段及 CSV 往返兼容。
  - 新增统一状态重算逻辑，保护人工审核字段。
- `app/server.py`
  - 审核结果读取时透传 `status_reason`。
- `app/migrate_scrape_status.py`
  - 新增一次性、可重复执行的历史任务状态重分类工具。
  - 支持 dry-run、自动备份、原子写入和受保护字段摘要校验。
- `tests/test_phase4_1_status_model.py`
  - 新增状态矩阵、历史重分类、CSV 兼容和 Creator Library 入库测试。
- `docs/KOLConnect_v2_Phase4_1_Status_Model_Normalization_Report.md`
  - 本报告。

## 2. 新状态模型

### success

同时满足：

- `platform + profile_url + creator_name` 完整；
- 至少存在 `email / whatsapp / followers / video data` 中一个增强字段；
- 页面访问过程没有 warning 或 fallback 标记。

### partial_success

存在 `creator_name / email / whatsapp` 中至少一个身份字段，但存在以下任一情况：

- 页面出现 warning；
- 使用 fallback 通道；
- 缺少 creator name；
- 缺少增强字段；
- 身份或平台信息不完整。

`partial_success` 可以进入 Creator Library。

### failed

`creator_name / email / whatsapp` 全部缺失，无法确认有效达人。

### status_reason

未来抓取会记录可追踪原因，例如：

- `warning_text_detected:try again`
- `fallback_channel`
- `selenium_exception:<异常摘要>`
- `unsupported_platform`
- `missing_identity`
- `missing_creator_name`
- `missing_enhanced_fields`

历史任务原来没有保存具体 warning 文本，因此迁移时使用 `legacy_platform_error`、`legacy_missing_data` 保留原状态来源，不伪造具体错误。

## 3. 历史重分类结果

处理任务：`task_20260805T112717Z_0bf99398`

总记录数：2251。

| 状态 | 重分类前 | 重分类后 |
|---|---:|---:|
| success | 1355 | 1013 |
| partial_success | 0 | 1216 |
| platform_error | 875 | 0 |
| missing_data | 21 | 0 |
| failed | 0 | 22 |

说明：

- 原 875 条 `platform_error` 中，874 条包含有效身份数据，重分类为 `partial_success`；1 条身份字段全部为空，重分类为 `failed`。
- 原 21 条 `missing_data` 身份字段全部为空，重分类为 `failed`。
- 原 1355 条 `success` 中，342 条不满足新 success 完整条件，重分类为 `partial_success`；其中 324 条只有 creator name，18 条缺少 creator name 但有 email。
- `results.csv` 与 `progress.csv` 均修改 1238 行。
- 除 `scrape_status`、`status_reason` 外的保护字段摘要保持一致：`42389609f5940bb0cc24cb9c4b7ec2702fd564b9b6e914aec7b3d3985690725d`。
- 迁移后再次 dry-run 的 `changed_rows=0`，确认幂等。

备份：

- 任务 CSV：`%APPDATA%\KOLConnect\tasks\task_20260805T112717Z_0bf99398\phase4_1_backup_20260806T093317Z\`
- 入库前工作簿：`%APPDATA%\KOLConnect\backups\Creator_Library.phase4_1_before_import_20260806_173316.xlsx`

## 4. Creator Library 入库结果

通过现有 `import_task_results_to_creator_library` 流程执行入库：

| 项目 | 数量 |
|---|---:|
| 输入记录 | 2251 |
| 创建达人 | 863 |
| 创建账号 | 863 |
| 更新账号 | 1366 |
| 重复记录 | 0 |
| 跳过失败 | 22 |
| 跳过无效 | 0 |

有效记录处理总数为 2229。874 条原 `platform_error` 有效记录中，有 11 个账号已存在于达人库，因此更新已有账号，不重复创建 Creator。

工作簿变化：

- Creators：1417 -> 2280（+863）
- CreatorAccounts：1417 -> 2280（+863）
- CreatorSnapshots：1432 -> 2306（+874）
- Campaign、CampaignCreator、Product、Insights、Videos、VideoSnapshots 等现有业务记录数量未减少。

## 5. 测试结果

- Python 全部 `app/*.py` 语法检查：通过。
- Phase 4.1 状态模型测试：7/7 通过。
- Phase 1 数据基础测试：10/10 通过。
- v2 Phase 1 数据基础测试：10/10 通过。
- Release Critical 测试：3/3 通过。
- 完整 Python 测试：54/55 通过。

完整测试唯一失败：

- `test_data_foundation_phase1_6.CreatorLibraryPerformanceTests.test_get_creators_reads_snapshots_once_for_large_workbook`
- 期望首条记录 followers 为 `9`，实际为 `0`。
- 该问题位于既有 Creator Library 大工作簿排序/测试假设，不涉及本次 scraper 状态、历史重分类或导入逻辑。

## 6. 数据保护验证

- `merge_scrape_result_with_review` 仍先保留人工姓名、邮箱、WhatsApp、备注、审核状态和修改时间，再重新计算抓取状态。
- 历史迁移只写入 `scrape_status` 与 `status_reason`。
- 未修改 Creator ID、account UID、人工审核字段、Excel Schema、飞书同步结构或 UI。
- Creator Library 入库继续使用现有唯一规则；已有达人和账号被更新，不创建重复记录。

## 7. 风险说明

- 历史 CSV 未保存原 warning 的具体文本，只能标记为 `legacy_platform_error`；未来新抓取可以记录具体 warning 或异常摘要。
- 当前任务没有粉丝数，增强字段主要来自 email/WhatsApp；无增强字段但有达人身份的记录按规则进入 `partial_success`，仍建议人工审核。
- 本次 2251 条 Excel 入库耗时约 4 分钟，说明现有 Excel Repository 在大批量导入时存在性能风险，但最终写入成功且未发生部分保存。
- 现有 retry history 仍以 `success` 作为完全成功口径；`partial_success` 会保留为未完全成功，符合需要继续补全数据的语义。
- 完整测试中的 Creator Library 大工作簿排序断言应在后续独立处理，本阶段未越界修改。
