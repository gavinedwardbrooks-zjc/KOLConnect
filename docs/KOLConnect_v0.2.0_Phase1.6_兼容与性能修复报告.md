# KOLConnect v0.2.0 Phase 1.6 兼容与性能修复报告

## 1. 验收状态

- 当前分支：`feature/v0.2.0-data-foundation`
- 自动化测试：通过
- 正式工作簿副本演练：通过
- 两次启动幂等验证：通过
- 正式工作簿迁移：通过
- 正式 Tool 与 API 冒烟测试：通过
- 是否回滚：否

## 2. 历史任务自动回填触发点

修改前，`app/server.py` 中的 `ensure_completed_tasks_in_creator_library()` 会扫描全部历史任务。该函数不是在服务进程启动时立即执行，而是在首次请求以下页面数据时触发：

- `GET /api/dashboard`
- `GET /api/creator-library`

因此，打开 Dashboard 或 Creator Library 会把符合旧条件的历史任务批量导入本地达人库。此前正式验收中 Creator 数量从 2 增长到 1332，即由该兼容回填路径导致。

## 3. 历史任务边界修复

修改后：

- 删除页面读取路径中的全量历史任务扫描。
- Dashboard、Creator Library 和 Repository 初始化不再从历史任务生成业务数据。
- 旧任务缺少 `creator_library_import_eligible` 时，默认按 `false` 处理。
- 升级后新建任务明确保存 `creator_library_import_eligible=true`。
- 任务完成后的现有增量导入入口继续使用，不通过启动或页面加载补偿。
- `email_recheck`、未完成任务和无有效结果任务继续跳过。
- 历史任务未来只能通过单独的人工预览与确认流程导入，本阶段未增加该入口。

## 4. 新任务增量导入与幂等

新任务在完成后调用现有达人库导入函数。重复保存、重复回调或服务重启后再次处理时，继续使用现有账号 UID 和规范化主页规则定位记录。

验证结果：

- 同一新任务首次导入：新增 1 个 Creator、1 个 CreatorAccount、1 个 Snapshot。
- 同一任务再次导入：Creator 和 CreatorAccount 不重复。
- 服务重启后再次导入：数量保持不变。
- `source_task_id` 保持原任务 ID。

## 5. getCreators 性能问题根因

修改前，`getCreators()` 在 Creator 循环内部调用 Snapshot 查询，每个 Creator 都重新遍历整张 `CreatorSnapshots` Sheet，复杂度接近：

`Creator 数量 × Snapshot 数量`

此外，达人详情会先打开工作簿，再调用 `getCreators()` 重新打开工作簿；Dashboard 合作统计也会按 Creator 分别读取合作记录。

## 6. Snapshot 索引方案

单次 Creator Library 请求现在执行：

1. 工作簿打开一次。
2. Creators 读取一次。
3. CreatorAccounts 读取一次。
4. CreatorSnapshots 读取一次。
5. 在请求内建立 `accounts_by_creator` 和 `snapshots_by_creator` 索引。
6. 一次遍历选择每个 Creator 的最新 Snapshot。
7. 组装原有兼容返回字段。

索引仅在当前请求对象内存在，不使用全局永久缓存。下一次请求会重新读取最新工作簿。

修改后复杂度接近：

`Creator 数量 + Account 数量 + Snapshot 数量`

达人详情复用同一次工作簿读取和同一组请求内索引。Dashboard 在单次请求中缓存 Creator 与 Cooperation 读取结果，避免重复读取和按达人查询。

## 7. 性能与隐私日志

Creator Library 装配日志只记录：

- `creators_count`
- `accounts_count`
- `snapshots_count`
- `load_duration_ms`
- `index_duration_ms`
- `response_duration_ms`

日志不包含邮箱、WhatsApp、主页链接或完整个人资料。

## 8. 自动化测试

测试数据规模：

- 1500 个 Creator
- 1500 个 CreatorAccount
- 15000 条 CreatorSnapshot

性能演练结果：

- 总耗时：4.517 秒
- 工作簿打开次数：1
- Creators 遍历次数：1
- CreatorAccounts 遍历次数：1
- CreatorSnapshots 遍历次数：1
- 最新 Snapshot 选择：正确
- 未出现分钟级等待或接口超时

完整回归结果：

- Python 单元测试：19/19 通过
- `app/*.py` 语法检查：通过
- `webapp/app.js` 语法检查：通过
- 达人分析、详情、趋势页回归：通过
- 邮件安全渲染回归：通过

## 9. 正式工作簿副本演练

使用正式工作簿和历史任务元数据的隔离副本完成两轮演练：

- schema 1.3 成功迁移至 `2.0-phase1`
- Creator 始终为 2 条
- CreatorAccount 为 2 条
- CreatorSnapshot 为 1 条
- 历史任务元数据未变化
- Dashboard、Creator Library、两个 Creator 详情、Task、Mail、Settings、账号管理页面均可加载
- API 返回正常
- 第二次服务启动后副本哈希不变
- `error.log` 为空
- 8765 端口在测试结束后正常释放

## 10. 正式数据保护记录

正式工作簿：

`%APPDATA%\KOLConnect\Creator_Library.xlsx`

迁移前 SHA-256：

`1cd863d969780a6b4e1386fb8a69b122df296b405b7412829e661d2b9f9c6c9f`

迁移后 SHA-256：

`8bad810288a07c72dfe5f90ccd1bc1c060df8e183ffad0f2a3de4d43762f1f13`

正式工作簿当前为 schema `2.0-phase1`、Creators 2 条、CreatorAccounts 2 条。原有 Videos、Insights、Cooperations、CreatorSnapshots 和 VideoSnapshots 行数未减少。

隔离 UI 测试首次启动时曾发现子进程未继承临时 `APPDATA`。测试立即停止，并对正式文件进行哈希复核；文件哈希与基线完全一致，未发生内容变化。为遵守回滚规则，随后仍使用既有手工备份执行了一次原子恢复，并再次确认 SHA-256 与基线一致。该次证据文件和原失败报告均保留。

## 11. 正式迁移结果

用户保存并关闭 WPS 后，独占读写锁检查通过。迁移前创建并验证：

- 手工备份：`Creator_Library.manual_backup_20260731T055538437847Z.xlsx`
- 自动备份：`Creator_Library.pre_v2_20260731T055538465587Z.xlsx`
- 两份备份 SHA-256：`1cd863d969780a6b4e1386fb8a69b122df296b405b7412829e661d2b9f9c6c9f`

正式迁移结果：

- from schema：`1.3`
- to schema：`2.0-phase1`
- Creator 保留：2
- Creator 新增：0
- CreatorAccount 新增：2
- 重复账号：0
- 无法确认归属：0
- 新建空表：Agencies、AgencyContacts、FollowUpLogs
- 回滚：未触发

第二次运行结果：

- 工作簿 SHA-256 不变
- Creator 与 CreatorAccount 数量不变
- 未创建第二份 `pre_v2` 备份
- 未创建重复 Sheet 或重复字段

正式 AppData 冒烟结果：

- Dashboard：HTTP 200，约 123ms，Creator 总数 2
- Creator Library：HTTP 200，约 45ms，记录数 2
- 两位 Creator 详情与趋势：HTTP 200
- Task、Mail、State、Agency、AgencyContact API：正常
- Dashboard、达人库、两位达人详情、历史趋势、任务、邮件、设置、账号管理页面：正常
- 页面日志：无错误
- 重启后 Creator 仍为 2，工作簿与任务元数据哈希不变
- 最终 `error.log`：0 字节
- 测试结束后 8765 无监听进程

## 12. 修改范围

- `app/creator_repository.py`
- `app/dashboard_repository.py`
- `app/server.py`
- `app/task_manager.py`
- `tests/test_data_foundation_phase1_6.py`

未修改飞书同步规则、邮件匹配规则、UID 规则、Excel Sheet 结构、前端页面结构或 Phase 2 功能。

## 13. 剩余风险

- Excel 仍是文件型存储；多进程或 WPS 同时写入时仍可能产生文件锁，正式迁移必须独占文件。
- 历史任务人工预览导入仅保留架构边界，本阶段未开发 UI。
