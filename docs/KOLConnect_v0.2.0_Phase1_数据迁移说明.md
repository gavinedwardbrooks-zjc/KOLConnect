# KOLConnect v0.2.0 Phase 1 数据迁移说明

本文记录 v0.2.0 第一阶段的本地数据结构与迁移行为，供开发、测试和回滚使用。它不是用户使用说明，也不代表 v0.2.0 已正式发布。

## 1. 迁移目标

v0.1.2 的 `Creators` 同时保存达人主体和平台账号属性。Phase 1 在不删除旧 Sheet、旧列或历史记录的前提下，引入独立账号、Agency 和联系人实体，并继续兼容现有 Creator Library、Dashboard、任务、插件导入和飞书集成。

迁移后的工作簿 Schema 标识为：

```text
2.0-phase1
```

## 2. 旧结构

v0.1.2 工作簿包含：

- `Creators`
- `Videos`
- `Insights`
- `CreatorSnapshots`
- `VideoSnapshots`
- `Cooperations`
- `_AnalysisData`
- `_Metadata`

其中 `Creators.platform`、`profile_url` 和 `followers` 实际属于社媒账号，但为兼容现有页面和 API，本阶段不删除这些列。

## 3. 新结构

Phase 1 新增：

- `CreatorAccounts`：独立保存平台账号。
- `Agencies`：保存机构基础资料。
- `AgencyContacts`：保存机构联系人，允许暂时没有 Agency。
- `FollowUpLogs`：为后续统一跟进记录预留本地结构，本阶段不开发跟进页面。

同时在 `Creators` 尾部追加达人主体字段和关系字段。已有列保持原顺序和原值。

### 3.1 Creator

主体字段包括：

- `creator_id`
- `name`
- `country`
- `language`
- `email`
- `whatsapp`
- `cooperation_stage`
- `tags`
- `recent_product`
- `quote`
- `owner`
- `last_contact_time`
- `next_follow_up_time`
- `note`

关系字段包括：

- `agency_id`
- `current_contact_id`
- `source_contact_id`

`current_contact_id` 与 `source_contact_id` 独立保存，不会互相覆盖。

### 3.2 Creator Account

`CreatorAccounts` 字段：

- `account_id`
- `creator_id`
- `account_uid`
- `platform`
- `username`
- `profile_url`
- `followers`
- `account_email`
- `latest_post_date`
- `last_scrape_time`
- `data_source`
- `scrape_status`
- `platform_account_id`
- `attribution_status`
- `note`
- `source_task_id`
- `created_at`
- `updated_at`

### 3.3 Agency

`Agencies` 保存：

- `agency_id`
- `name`
- `country`
- `website`
- `public_email`
- `whatsapp`
- `cooperation_stage`
- `tags`
- `last_contact_time`
- `next_follow_up_time`
- `owner`
- `note`
- `resource_files`
- `created_at`
- `updated_at`

### 3.4 Agency Contact

`AgencyContacts` 保存：

- `contact_id`
- `name`
- `agency_id`
- `position`
- `email`
- `whatsapp`
- `language`
- `status`
- `last_contact_time`
- `next_follow_up_time`
- `owner`
- `note`
- `external_record_id`
- `source`
- `created_at`
- `updated_at`

`agency_id` 可以为空。飞书兼容联系人以 `external_record_id` 保留来源，但不会根据 Agency 显示名称自动创建或绑定本地 Agency。

## 4. 旧字段映射

| v0.1.2 来源 | Phase 1 目标 | 规则 |
| --- | --- | --- |
| `Creators.creator_id` | `Creators.creator_id` | 原值保留 |
| `Creators.name` | `Creators.name` | 原值保留 |
| `Creators.country` | `Creators.country` | 原值保留 |
| `Creators.language` | `Creators.language` | 原值保留 |
| `Creators.platform` | `CreatorAccounts.platform` | 创建账号时复制，旧列保留 |
| `Creators.profile_url` | `CreatorAccounts.profile_url` | 创建账号时复制，旧列保留 |
| `Creators.followers` | `CreatorAccounts.followers` | 优先使用最新 Snapshot，旧列保留 |
| `_AnalysisData.account_uid` | `CreatorAccounts.account_uid` | 作为账号去重键 |
| `_AnalysisData.task_id` | `CreatorAccounts.source_task_id` | 保留任务追溯 |
| `CreatorSnapshots.account_uid` | `CreatorAccounts.account_uid` | `_AnalysisData` 缺失时作为兼容来源 |

旧工作簿无法可靠判断两个不同平台账号是否属于同一真实达人，因此迁移默认一条旧 Creator 对应一个 Creator 和一个 Account，不按名称合并。

## 5. 迁移执行规则

1. 打开旧工作簿时读取 `_Metadata.schema_version`。
2. 在任何结构写入前创建完整时间戳备份。
3. 在内存工作簿中追加缺失 Sheet 和缺失列。
4. 按旧 Creator、`_AnalysisData` 和 Snapshot 生成 `CreatorAccounts`。
5. 校验临时工作簿可以重新打开。
6. 保存前继续生成常规 `.xlsx.bak`。
7. 使用临时文件原子替换正式工作簿。
8. 写入 `schema_version=2.0-phase1`。

迁移日志记录：

- 旧 Creator 行数。
- 保留 Creator 数量。
- 新建 Account 数量。
- 重复 Account 数量。
- 无法确认 Account 数量。
- Agency、Contact 和 FollowUp Sheet 是否新建。
- 时间戳备份路径。
- 迁移结果。

## 6. 去重与归属规则

### Creator

- 不按达人名称自动合并。
- 不同账号即使显示名称相同，也默认创建不同 Creator。
- 已有 Account 匹配时，继续使用其原 `creator_id`。
- 调用方明确提供已有 `creator_id` 时，可以把新 Account 关联到该 Creator。

### Creator Account

- 唯一键继续使用现有 `account_uid`。
- `account_uid` 仍由现有 UID 逻辑生成，本阶段不修改规则。
- `account_id` 根据 `account_uid` 稳定生成。
- 同一 `account_uid` 重复导入只更新同一 Account。
- 迁移发现同一 `account_uid` 指向多个旧 Creator 时，保留首个 Account 归属并记录重复，不自动合并或删除 Creator。

## 7. 普通任务进入 Creator Library

任务进入本地达人库必须同时满足：

- 任务类型不是 `email_recheck`。
- 任务状态为 `completed`，或人工任务状态为 `manual_created`。
- 记录状态为 `success` 或 `partial_success`。
- 存在受支持的平台。
- 存在有效标准主页链接。
- 能按现有规则生成 `account_uid`。

以下记录不会创建达人：

- `failed`
- `login_required`
- `platform_error`
- `missing_data`
- 无平台记录
- 无主页链接记录
- 普通文本

任务完成后会记录关联的 Creator ID、Account ID、导入时间和导入摘要。历史已完成任务在首次打开达人库或工作台时执行一次幂等补录。插件任务继续使用原导入流程，不重复生成任务内快照。

## 8. 备份与回滚

迁移备份文件格式：

```text
Creator_Library.pre_v2_YYYYMMDDTHHMMSSffffffZ.xlsx
```

常规保存备份仍为：

```text
Creator_Library.xlsx.bak
```

迁移失败时，正式工作簿不会被替换。需要人工回滚已成功迁移的工作簿时：

1. 关闭 KOLConnect、WPS 和 Excel。
2. 另行保留当前 `Creator_Library.xlsx`。
3. 将时间戳备份复制回原工作簿路径。
4. 重新启动 KOLConnect。

任务目录、设置文件和飞书数据不参与本次工作簿替换。

## 9. 飞书兼容边界

本阶段不修改：

- 飞书配置字段。
- 飞书达人表和达人账号表同步。
- 邮件匹配及回复状态同步。
- 缺失邮箱补全。
- 来源联系人写入飞书。

本地 API 使用 `/api/local/agencies` 和 `/api/local/agency-contacts`。原 `/api/agency-contacts` 继续作为飞书联系人只读兼容入口。

飞书未配置或不可用时，Creator Library、Dashboard、任务和本地 Agency Repository 仍可使用。飞书同步失败只记录任务同步错误，不回滚或覆盖本地工作簿。

## 10. 本阶段不包含

- Agency 页面。
- Agency 联系人独立页面。
- 跟进看板。
- Campaign、合同、付款或寄样管理。
- 新 Dashboard。
- 邮件系统替换。
- 飞书双向同步。
- 飞书数据迁移或删除。
- Google Sheets。
- Chrome Extension 新功能。
- 正式 EXE 打包或版本发布。
