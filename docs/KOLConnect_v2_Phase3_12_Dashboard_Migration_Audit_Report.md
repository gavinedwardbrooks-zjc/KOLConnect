# KOLConnect v2 Phase 3.12 Dashboard Migration Audit Report

## 1. 审计范围与结论

本次仅审计以下文件和运行链路，未修改代码、Excel、UI 或构建配置：

- `app/dashboard_repository.py`
- `app/dashboard_service.py`
- `app/server.py`
- `webapp/app.js`
- `webapp/index.html`
- `webapp/pages/`
- `app/campaign_repository.py`
- `app/campaign_creator_repository.py`
- 相关 Dashboard 回归测试

结论：当前 Dashboard 仍是 v0.x 的合作数据实现。达人数量、状态和趋势来自 `Creators` 与 `CreatorSnapshots`，可以继续保留；所有合作金额、播放、ROI、Top 达人和合作待办仍来自旧 `Cooperations`，尚未接入 v2 的 `Campaigns` 与 `CampaignCreators`。

Dashboard 可以迁移到 v2 数据源，但应保持现有 `/api/dashboard` 返回结构兼容，并将后端数据源迁移与前端生命周期迁移拆成两个步骤。迁移时禁止同时累计 `Cooperations` 与 `CampaignCreators`，否则会发生重复统计。

## 2. 当前真实运行链路

```text
webapp/index.html Dashboard DOM
        |
webapp/app.js loadDashboard()
        |
GET /api/dashboard
        |
app/server.py get_dashboard_data()
        |
DashboardService
        |
DashboardRepository
        |
CreatorRepository
        |
Creators + CreatorSnapshots + Cooperations
```

当前 `DashboardRepository` 只接收 `CreatorRepository`。虽然 `server.py` 已经具备 `CampaignRepository` 和 `CampaignCreatorRepository`，Dashboard 工厂函数并未把它们接入。

`webapp/pages/` 当前不存在 `dashboard.js`。Dashboard 仍在 `app.js` 的 `registerLegacyPages()` 中注册，刷新按钮也由全局 `bindEvents()` 绑定，不属于新的 `load/bind/unbind` 页面生命周期。

## 3. Dashboard 指标数据来源地图

| Dashboard 模块 | API 字段 | 当前来源 | 当前计算方式 | 依赖 Cooperations | v2 目标来源 |
|---|---|---|---|---|---|
| 今日概览 | `total_creators` | Creators | Creator 记录数 | 否 | 保持 Creators |
| 今日概览 | `new_creators_7d` | Creators | `analysis_time` 在最近 7 天 | 否 | 保持 Creators；后续可评估改用 `created_at` |
| 今日概览 | `discovered_count` | Creators | `status=discovered` | 否 | 保持 Creators |
| 今日概览 | `cooperating_count` | Creators | `status=cooperating` | 否 | 暂时保持兼容；需注意它不是 CampaignCreator 阶段统计 |
| 今日概览 | `cooperation_spend` | Cooperations | `price` 求和 | 是 | CampaignCreators 的 `cost` 求和 |
| 今日概览 | `average_roi` | Cooperations | 非空 `roi` 平均值 | 是 | CampaignCreators 的非空 `roi` 平均值 |
| 达人健康 | `rising_creators` | CreatorSnapshots | 优先比较 `median_views`，其次 `followers` | 否 | 保持 CreatorSnapshots |
| 达人健康 | `falling_creators` | CreatorSnapshots | 优先比较 `median_views`，其次 `followers` | 否 | 保持 CreatorSnapshots |
| 达人健康 | `expired_creators` | CreatorSnapshots | `freshness.status=stale` | 否 | 保持 CreatorSnapshots |
| 合作表现 | `total_campaigns` | Cooperations | 当前实际为 Cooperation 行数 | 是 | CampaignCreators 活跃关系数；字段语义需冻结 |
| 合作表现 | `total_cost` | Cooperations | `price` 求和 | 是 | CampaignCreators 的 `cost` 求和 |
| 合作表现 | `total_views` | Cooperations | `total_views` 求和 | 是 | CampaignCreators 的 `views` 求和 |
| 合作表现 | `average_roi` | Cooperations | 非空 `roi` 平均值 | 是 | CampaignCreators 的非空 `roi` 平均值 |
| 合作表现 | `top_creators` | Cooperations + Creators | 按 creator 聚合合作数、成本、播放、ROI | 是 | CampaignCreators + Creators 聚合 |
| 待处理 | `expired_creators` | CreatorSnapshots | 复用达人健康结果 | 否 | 保持 CreatorSnapshots |
| 待处理 | `pending_contact` | Creators | `status=discovered` | 否 | 暂时保持 Creators |
| 待处理 | `incomplete_cooperations` | Cooperations | `result` 为空 | 是 | CampaignCreators；需先冻结“不完整”判定规则 |

## 4. Cooperations 依赖与字段迁移

当前 Dashboard 对旧 `Cooperations` 的直接入口是：

- `DashboardRepository.get_cooperation_records()` 调用 `CreatorRepository.getCooperations()`。
- `DashboardService.getOverview()` 使用 `price` 和 `roi`。
- `DashboardService.getCooperationPerformance()` 使用 `price`、`total_views` 和 `roi`。
- `DashboardService.getActionItems()` 使用 `result`、`campaign` 和 `contact_date`。

建议映射如下：

| Cooperations 旧字段 | CampaignCreator 新字段或来源 | 迁移说明 |
|---|---|---|
| `cooperation_id` | `id` | API 兼容期可把 `id` 同时输出为 `cooperation_id` 别名 |
| `creator_id` | `creator_id` | 可直接对应 |
| `campaign` | `campaign_id` 关联 Campaigns.`name` | Repository 一次建立 Campaign 索引，禁止前端逐条查询 |
| `platform` | `account_id` 关联 CreatorAccount.`platform`，或 Campaign.`platform` | 应优先使用执行账号平台 |
| `price` | `cost` | Dashboard 花费应使用实际成本，不使用达人报价 |
| `total_views` | `views` | 可直接用于总播放统计 |
| `roi` | `roi` | v2 已冻结为 `revenue / cost` 倍数 |
| `result` | 无完全等价字段 | 可结合 `stage`、`performance_note`、`views`、`roi` 定义待复盘规则 |
| `contact_date` | 无完全等价字段 | 不应无提示地改成其他业务日期；兼容展示可暂用 `created_at`，但需标明语义变化 |
| `published_count` | 无直接字段 | 可从 `publish_links` 解析链接数量，但当前 Dashboard 未使用 |
| `average_views` | 无直接字段 | 如未来需要，可由 `views / 有效发布链接数` 计算 |

旧 `Cooperations` 应继续保留给 Creator Detail 的 Legacy Cooperation 展示，但 v2 Dashboard 不应将其与 CampaignCreator 合并统计。

## 5. CampaignCreator 迁移规则

### 5.1 统计范围

建议 Dashboard 默认只统计：

- `CampaignCreator.archived_at` 为空的关系。
- 所属 `Campaign.archived_at` 为空的 Campaign。
- 引用存在的 Creator；孤立关系应记录警告并跳过，不应导致整个 Dashboard API 失败。

### 5.2 合作数量语义

当前 `total_campaigns` 实际返回 Cooperation 行数，并非去重 Campaign 数量。为避免前端数字突然变化，Phase 3.12 实施时建议保持现有字段名和现有有效语义：统计活跃 CampaignCreator 关系数。

如果产品后续需要“独立 Campaign 数量”，应新增明确字段，例如 `distinct_campaigns_count`，不要静默改变 `total_campaigns` 的含义。

### 5.3 待补全合作规则

CampaignCreator 没有旧 `result` 字段，现阶段不能直接等价迁移。实施前需要冻结以下规则之一：

1. `stage=completed` 且 `performance_note` 为空，视为待复盘。
2. `stage` 为 `executing/completed`，且 `views`、`roi`、`performance_note` 均为空，视为结果不完整。
3. 按阶段分别定义必填字段，返回具体缺失原因。

推荐采用第 3 种，但第一轮可先采用第 2 种以保持实现范围可控。无论选择哪种，都应保持 API 输出中的 `reason` 字段，便于旧前端继续展示。

### 5.4 Creator 全局状态风险

`cooperating_count` 和 `pending_contact` 当前来自 Creator 全局 `status`，而 CampaignCreator 已有独立 `stage`。两者代表不同层级：

- Creator `status`：达人库全局关系状态。
- CampaignCreator `stage`：某个 Campaign 内的合作阶段。

本次迁移不应直接用 CampaignCreator stage 覆盖 Creator status。建议先保持现有两个指标，后续若新增 Campaign 执行指标，应使用新字段而不是修改旧字段语义。

## 6. Repository 与 Service 调整建议

未来实施时，`DashboardRepository` 应继续作为只读聚合层，不直接读取 Excel。建议注入：

- `CreatorRepository`
- `CampaignRepository`
- `CampaignCreatorRepository`

建议新增的只读能力：

- 获取 Creator 及 Snapshot 健康数据。
- 一次获取活跃 Campaign 并建立 `campaign_id` 索引。
- 一次获取活跃 CampaignCreator。
- 将 CampaignCreator 与 Creator、Campaign 聚合为 Dashboard 所需记录。
- 在单次 Dashboard 请求内缓存读取结果，避免重复打开工作簿和 N+1 查询。

`server.py` 的 `/api/dashboard` 路由无需变化，只需在未来修改 `get_dashboard_data()` 创建 Repository 的依赖方式。

## 7. API 兼容性结论

建议保持 `/api/dashboard` 当前顶层结构：

```json
{
  "ok": true,
  "overview": {},
  "creator_health": {},
  "cooperation_performance": {},
  "action_items": {}
}
```

以下字段在数据源迁移后应继续保留：

- `overview.total_creators`
- `overview.new_creators_7d`
- `overview.discovered_count`
- `overview.cooperating_count`
- `overview.cooperation_spend`
- `overview.average_roi`
- `creator_health.rising_creators`
- `creator_health.falling_creators`
- `creator_health.expired_creators`
- `cooperation_performance.total_campaigns`
- `cooperation_performance.total_cost`
- `cooperation_performance.total_views`
- `cooperation_performance.average_roi`
- `cooperation_performance.top_creators`
- `action_items.expired_creators`
- `action_items.pending_contact`
- `action_items.incomplete_cooperations`

保持这些字段可使现有 Web 页面在后端切换数据源后继续运行。可以新增来源或迁移诊断字段，但不应删除、改名或改变值类型。

## 8. 前端是否需要修改

### 8.1 数据源迁移阶段

如果 `/api/dashboard` 保持上述兼容结构，前端不需要为了切换到 CampaignCreator 而修改页面结构。现有 `renderDashboard()` 可以继续渲染。

Repository 应继续为待补全关系提供当前前端依赖的：

- `creator_id`
- `creator_name`
- `platform`
- `campaign`
- `reason`

其中 `campaign` 应由 Campaigns.`name` 聚合得到。当前列表点击行为仍可跳转 Creator Detail。

### 8.2 前端架构阶段

Dashboard 仍是 legacy page，建议在后端迁移稳定后单独迁移为：

```text
webapp/pages/dashboard.js
```

并实现：

- `load()`：请求 `/api/dashboard` 并渲染。
- `bind()`：绑定刷新和列表跳转。
- `unbind()`：取消请求并释放事件。

届时应从 `registerLegacyPages()` 删除 Dashboard 注册，并从全局 `bindEvents()` 移除 `dashboard-refresh` 监听。该工作属于前端生命周期整理，不是 CampaignCreator 数据迁移的前置条件。

## 9. 测试影响

现有 `tests/test_data_foundation_phase1_6.py` 明确断言一次 Dashboard 计算读取一次 `Cooperations`。迁移后该测试必须调整，不能继续把读取旧 Cooperation 作为正确行为。

建议迁移实施时补充：

1. 只有 CampaignCreator 数据时，Dashboard 合作指标正确。
2. 已归档 CampaignCreator 不参与统计。
3. 已归档 Campaign 不参与统计。
4. Legacy Cooperations 与 CampaignCreator 同时存在时不重复累计。
5. 空 Campaign/CampaignCreator 返回稳定的零值和空数组。
6. Product、Campaign、Creator 或 Account 引用缺失时记录警告，Dashboard 不整体失败。
7. `/api/dashboard` 返回结构与现有前端契约一致。
8. Top Creator 的成本、播放和 ROI 聚合正确。
9. 待补全合作规则符合冻结后的业务定义。
10. Dashboard 前端在空数据和 API 异常时分别显示空状态与错误状态。

## 10. 风险分级

### High

- 同时累计 `Cooperations` 与 `CampaignCreators` 会造成金额、播放、ROI 和合作数量重复。
- `total_campaigns` 当前名称与实际“合作关系数”语义不一致，迁移时若改成去重 Campaign 数会造成用户可见数据突变。
- CampaignCreator 没有 `result` 字段，`incomplete_cooperations` 的新判断规则尚未冻结。
- Creator 全局状态与 CampaignCreator 阶段并不等价，直接替换会改变待联系和合作中指标含义。

### Medium

- 多个 Repository 若各自重复打开工作簿，会放大 Excel 读取成本；Dashboard 请求应做请求内缓存与批量索引。
- Campaign、Creator 或 Account 的孤立引用可能使展示字段为空，应容错并记录警告。
- `publish_links` 可能是序列化字符串，未来计算发布数量前需要统一解析。
- Dashboard 仍由 `app.js` 管理，缺少页面级请求取消和资源释放。

### Low

- `getActionItems()` 会再次调用 Creator Health 计算；当前 Repository 缓存避免了重复读取，但仍有重复计算。
- 当前 API 名称继续使用 `cooperation_performance`，与 v2 Campaign 命名不完全一致；为兼容不建议现在改名。

## 11. 推荐实施顺序

1. 冻结 `total_campaigns` 的统计语义和 CampaignCreator 待补全规则。
2. 扩展 DashboardRepository，注入 Campaign 与 CampaignCreator Repository，建立请求内索引。
3. 将合作类指标改为只读取活跃 CampaignCreator，明确排除 Legacy Cooperations。
4. 保持 `/api/dashboard` 返回结构和字段类型不变。
5. 更新后端聚合测试、空数据测试、归档过滤测试和 API 契约测试。
6. 完成数据源验收后，再把 Dashboard 从 `app.js` 迁移到独立 `dashboard.js` 生命周期模块。

## 12. 最终判断

当前 Dashboard 可以进入 CampaignCreator 数据源迁移，但需先冻结两个业务口径：

1. `total_campaigns` 是 CampaignCreator 关系数还是去重 Campaign 数。
2. CampaignCreator 在什么条件下属于“合作记录缺失”。

除这两项外，现有 Repository、Service、API 和前端结构都具备渐进迁移条件。推荐保持 API 兼容，先替换后端合作数据源，再单独进行 Dashboard 前端生命周期迁移。
