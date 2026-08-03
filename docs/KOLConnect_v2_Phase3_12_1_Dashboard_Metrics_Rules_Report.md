# KOLConnect v2 Phase 3.12.1 Dashboard Metrics Rules Report

## 1. 审计范围

本报告冻结 Dashboard 从 Legacy `Cooperations` 迁移到 `CampaignCreators` 后的指标口径。审计依据包括：

- `app/campaign_creator_repository.py`
- `app/campaign_repository.py`
- `app/dashboard_repository.py`
- `app/dashboard_service.py`
- `app/server.py`
- `webapp/app.js`
- `webapp/pages/campaign-detail.js`
- `docs/KOLConnect_v2_Phase2_API_Report.md`
- `docs/KOLConnect_v2_Phase3_12_Dashboard_Migration_Audit_Report.md`
- 《KOLConnect v2 Product-Campaign 模型重构 PRD》

本轮未修改代码、Excel、API、页面或业务数据。

## 2. 当前数据事实

当前 `CampaignCreators` 字段为：

```text
id
campaign_id
creator_id
account_id
stage
owner
creator_quote
cost
publish_links
publish_date
views
likes
comments
roi
performance_note
created_at
updated_at
archived_at
```

当前阶段枚举为：

```text
pending_contact
contacted
quoted
negotiating
agreed
executing
completed
rejected
```

当前 Schema 存在 `cost` 和 `roi`，不存在 `revenue`。Repository 只校验 `roi` 是非负数字，并不能验证它是否确实等于 `revenue / cost`。

## 3. 全局统计边界

所有 Dashboard CampaignCreator 指标遵守以下共同规则：

1. `CampaignCreator.archived_at` 非空的关系一律排除。
2. 外键缺失的孤立关系不参与统计，但应记录警告，不能导致整个 Dashboard API 失败。
3. 空数值表示“未知”，不得自动当作业务上的 `0`；聚合结果没有有效记录时，API 为兼容前端返回 `0`。
4. `rejected` 表示合作未成立，不参与合作数量、花费、ROI、播放或 Top 达人统计。
5. Legacy `Cooperations` 不与 CampaignCreator 混合累计。

Campaign 归档状态按指标类型区别处理：

- 历史累计指标保留已归档 Campaign 的有效合作结果，避免归档后累计花费、播放和合作数量下降。
- 待联系、执行中、待复盘等运营待办只读取未归档 Campaign，避免历史 Campaign 继续产生工作提醒。

## 4. 合作数量

### 4.1 冻结定义

“合作数量”定义为符合以下条件的 CampaignCreator 关系数：

```text
archived_at 为空
且 stage 属于 agreed / executing / completed
```

阶段处理规则：

| stage | 是否计入合作数量 | 原因 |
|---|---:|---|
| `pending_contact` | 否 | 尚未联系，不构成合作 |
| `contacted` | 否 | 仅完成联系，不构成合作 |
| `quoted` | 否 | 报价阶段尚未达成合作 |
| `negotiating` | 否 | 洽谈阶段尚未达成合作 |
| `agreed` | 是 | 已达成合作 |
| `executing` | 是 | 合作正在执行 |
| `completed` | 是 | 合作已完成 |
| `rejected` | 否 | 合作未成立 |

### 4.2 计数单位

计数单位为 CampaignCreator 关系，不是去重 Campaign 数，也不是去重 Creator 数。同一 Creator 参加两个 Campaign，计为两次合作。

为保持现有前端兼容，`cooperation_performance.total_campaigns` 暂时继续承载该数值。该字段名称并不精确，但本阶段不改名、不增加 API 字段。

### 4.3 归档规则

- 已归档 CampaignCreator：排除。
- 已归档 Campaign 下仍未归档且阶段为 `agreed/executing/completed` 的关系：保留在历史累计合作数量中。
- 归档 Campaign 不再产生待联系、执行中或待复盘提醒。

## 5. 花费

### 5.1 `cost` 字段语义

`cost` 冻结为该 Campaign 与该 Creator 已确认产生的实际或应付合作成本。

它不是：

- Creator 初始报价，初始报价使用 `creator_quote`。
- Campaign 总预算，预算使用 Campaign.`budget`。
- 预计成本或未确认报价。

原则上从 `agreed` 阶段开始才应录入 `cost`，`executing` 与 `completed` 阶段可以继续修正为最终成本。

### 5.2 Dashboard 花费规则

Dashboard 花费只累计：

```text
CampaignCreator.archived_at 为空
stage 属于 agreed / executing / completed
cost 为有效非负数
```

不统计所有非 archived 记录。`pending_contact`、`contacted`、`quoted`、`negotiating` 和 `rejected` 即使误填了 `cost`，也不进入 Dashboard 花费。

已归档 Campaign 中的有效历史合作仍计入累计花费；已归档 CampaignCreator 不计入。

API 映射：

- `overview.cooperation_spend`
- `cooperation_performance.total_cost`

两者在当前版本使用同一累计口径。

## 6. ROI 模型审计与冻结

### 6.1 当前矛盾

Phase 2 已冻结：

```text
ROI = revenue / cost
```

但当前 `CampaignCreators` 没有 `revenue` 字段。因此系统只能保存调用方人工提交的 ROI 倍数，无法：

- 自动计算 ROI。
- 验证 ROI 是否与收入、成本一致。
- 在成本改变后自动重算 ROI。
- 审计 ROI 的收入依据。

这是数据语义和计算能力之间的模型缺口，但不阻塞 v2.0 第一阶段的运营使用。

### 6.2 方案 A：保留现有模型

规则：

- `roi` 是运营人员根据外部已知收入和 `cost` 计算后录入的最终 ROI 倍数。
- 例如 `roi=2.5` 表示该合作归因收入约为成本的 2.5 倍。
- KOLConnect 保存最终倍数，不保存收入明细，也不自动计算。
- 当前 Schema 不需要修改。

优点：

- 不修改 Excel Schema。
- 不引入财务数据管理责任。
- 与当前 Campaign Detail 表单、Repository 和 API 完全兼容。
- 适合 v0.2.0 当前“本地 KOL 运营与合作管理工具”的产品定位。

限制：

- ROI 可信度依赖人工录入。
- 无法自动验证或追溯收入来源。
- 成本变化后需要人工同步更新 ROI。

### 6.3 方案 B：新增 `revenue`

需要至少新增：

- CampaignCreators.`revenue`
- 可选 `revenue_source`
- 可选 `revenue_updated_at`

系统再通过 `revenue / cost` 自动计算 ROI。

主要风险：

- 需要 Excel 缺列迁移、Repository/API/UI 全链路修改。
- 需要确定收入币种、税费、退款、归因窗口和多链接收入分摊。
- 已有手工 ROI 无法可靠反推出原始收入依据。
- 会把当前产品从合作运营管理扩展到财务归因管理，超出 v0.2.0 第一阶段范围。

### 6.4 最终推荐

推荐 **方案 A**。

冻结语义：

```text
CampaignCreator.roi = 运营人员人工确认并录入的最终 ROI 倍数
理论定义仍为 revenue / cost
系统当前不保存 revenue，不自动计算或校验
```

本阶段不修改 Schema。

### 6.5 Dashboard 平均 ROI

符合以下条件的记录进入平均 ROI：

```text
CampaignCreator.archived_at 为空
stage = completed
cost > 0
roi 不为空且为有效非负数
```

计算方式冻结为简单算术平均：

```text
average_roi = sum(valid roi) / count(valid roi)
```

补充规则：

- `roi=0` 是有效结果，必须参与平均。
- `roi` 为空不参与分母。
- `cost` 为空或等于 0 时，即使填写了 ROI，也视为无法验证基本计算前提，不参与 Dashboard 平均值。
- 没有有效 ROI 时，为兼容现有 API 返回 `0`。
- 只使用 CampaignCreator.`roi`，禁止读取或混入 Legacy Cooperation.`roi`。
- 已归档 Campaign 中已完成的有效关系可进入历史平均；已归档 CampaignCreator 不进入。

该指标是“单次合作 ROI 倍数的平均值”，不是投资组合加权 ROI。未来如需要整体 ROI，应单独增加明确指标，并优先在具备 `revenue` 数据后计算。

## 7. Top 达人

### 7.1 候选范围

Top 达人只使用：

```text
CampaignCreator.archived_at 为空
stage = completed
```

同一 Creator 的多条有效关系按 `creator_id` 聚合。

### 7.2 默认排序

三个候选指标比较：

| 指标 | 优点 | 风险 | 是否作为默认排序 |
|---|---|---|---:|
| 总播放 `views` | 直观、覆盖率通常高、与达人内容表现直接相关 | 不代表盈利能力 | 是 |
| 平均 ROI | 体现商业效率 | 当前为人工录入，可能缺失且缺少 revenue 校验 | 否，作为次级排序 |
| 合作次数 | 体现复用和信任程度 | 容易偏向合作历史较长的达人 | 否，作为第三排序 |

冻结排序顺序：

```text
1. total_views 降序
2. average_roi 降序
3. campaign_count 降序
4. creator_id 稳定排序
```

其中：

- `total_views`：该 Creator 所有符合条件关系的有效 `views` 之和。
- `average_roi`：该 Creator 符合 ROI 有效规则的简单平均值；缺失排在有值之后。
- `campaign_count`：该 Creator 符合条件的完成合作关系数。

推荐原因：播放数据比当前人工 ROI 更稳定，适合作为 v2.0 第一阶段默认排序。ROI 保留为辅助判断，不作为唯一排名依据。

## 8. 状态指标

状态类指标只统计未归档 Campaign 下、`archived_at` 为空的 CampaignCreator。

### 8.1 待联系

冻结条件：

```text
stage = pending_contact
```

映射：

- `overview.discovered_count`
- `action_items.pending_contact`

计数和待办均以 CampaignCreator 关系为单位。同一 Creator 在两个 Campaign 都待联系时，属于两个运营事项。

### 8.2 执行中

冻结条件：

```text
stage in (agreed, executing)
```

映射：

- `overview.cooperating_count`

`agreed` 表示合作已经成立、等待或开始执行，因此纳入执行中。`negotiating` 尚未达成，不纳入。

### 8.3 待复盘

冻结条件：

```text
stage = completed
且 trim(performance_note) 为空
```

映射：

- `action_items.incomplete_cooperations`

待复盘记录按 CampaignCreator 关系返回，并需要聚合：

- CampaignCreator.`id`
- `creator_id`
- Creator 名称
- Campaign 名称
- 执行账号平台
- `reason = missing_performance_note`

为兼容当前前端，可以继续提供 `cooperation_id` 作为 CampaignCreator.`id` 的响应别名，并保留 `campaign` 文本字段。

### 8.4 其他阶段

- `contacted`、`quoted`、`negotiating` 属于推进中的线索阶段，但本版 Dashboard 不新增对应指标。
- `rejected` 不进入合作与执行统计。
- 本轮不使用 Creator 全局 `status` 替代 CampaignCreator stage。

## 9. Legacy Cooperations

v2 目标规则冻结为：

1. `Cooperations` 仅用于历史只读展示。
2. 不参与 `/api/dashboard` 的任何指标。
3. 不与 CampaignCreator 合并统计。
4. 不自动迁移、不自动删除。
5. 新合作记录应进入 CampaignCreator。

当前实现尚未完全符合“只读”目标：

- `CreatorRepository.saveCooperation()` 仍存在。
- `POST /api/creator-library/{creator_id}/cooperations` 仍存在。
- Creator Detail 仍保留 Legacy Cooperation 录入表单和保存按钮。

本轮不修改这些代码。后续收口时应停止新增 Legacy Cooperation，但继续保留历史读取与展示能力。

## 10. `/api/dashboard` 兼容规则

`GET /api/dashboard` 顶层结构保持不变：

```json
{
  "ok": true,
  "overview": {},
  "creator_health": {},
  "cooperation_performance": {},
  "action_items": {}
}
```

必须保持现有字段：

```text
overview.total_creators
overview.new_creators_7d
overview.discovered_count
overview.cooperating_count
overview.cooperation_spend
overview.average_roi

creator_health.rising_creators
creator_health.falling_creators
creator_health.expired_creators

cooperation_performance.total_campaigns
cooperation_performance.total_cost
cooperation_performance.total_views
cooperation_performance.average_roi
cooperation_performance.top_creators

action_items.expired_creators
action_items.pending_contact
action_items.incomplete_cooperations
```

兼容要求：

- 数值字段继续返回数字。
- 无数据时数值返回 `0`，列表返回 `[]`。
- 不修改前端字段名。
- 不要求前端循环查询 Campaign、Creator 或 Account。
- Campaign、Creator 和执行账号展示字段由 Repository 一次聚合。
- 本阶段不新增 API，不改变 `/api/dashboard` 路由。

## 11. 最终冻结表

| 指标 | 冻结口径 |
|---|---|
| 合作数量 | 未归档 CampaignCreator，stage 为 `agreed/executing/completed`；按关系计数 |
| 待联系是否算合作 | 不算 |
| rejected 是否算合作 | 不算 |
| 历史归档 Campaign | 可保留在累计合作、花费、播放、ROI 中 |
| 已归档 CampaignCreator | 所有 Dashboard 指标均排除 |
| 花费 | `agreed/executing/completed` 的有效 `cost` 之和 |
| `cost` 语义 | 已确认产生的实际或应付合作成本 |
| ROI 模型 | 方案 A，人工录入最终倍数，不新增 `revenue` |
| 平均 ROI | `completed`、`cost>0`、ROI 非空记录的简单算术平均 |
| Top 达人 | 完成合作聚合后按总播放、平均 ROI、合作次数依次排序 |
| 待联系 | `pending_contact` |
| 执行中 | `agreed/executing` |
| 待复盘 | `completed` 且 `performance_note` 为空 |
| Legacy Cooperation | 只读展示，不进入 Dashboard，不参与任何统计 |
| API | `/api/dashboard` 路由、结构、字段名和类型保持兼容 |

## 12. 结论

Dashboard Metrics 规则已具备进入后端迁移实施的条件。

v2.0 第一阶段不新增 `revenue`，不修改 CampaignCreator Schema。`roi` 作为人工确认的最终倍数保存，Dashboard 只使用符合条件的 CampaignCreator ROI，禁止继续读取 Legacy Cooperation ROI。

实施阶段必须同步验证：归档过滤、阶段过滤、空值处理、Legacy 排除、Top 达人排序及现有 API 契约兼容。
