# KOLConnect v2 Phase 3.14 Dashboard Frontend Audit Report

## 1. 审计范围

本次只读检查：

- `webapp/index.html`
- `webapp/app.js`
- `webapp/services/api-client.js`
- `webapp/core/page-registry.js`
- `webapp/core/page-resources.js`
- `webapp/pages/`
- Dashboard 相关前端测试

本轮未修改代码、API、数据、UI 或构建配置。

## 2. 总体结论

Dashboard 前端在数据结构层面可以继续消费 Phase 3.13 的 CampaignCreator 聚合结果：它只调用一次 `GET /api/dashboard`，没有直接读取 Legacy `Cooperations`，也没有绕过 Dashboard API 请求旧合作数据。

但前端尚未“完全适配”，存在两类遗留：

1. 产品文案与新指标语义不完全一致。
2. Dashboard 仍是 `app.js` 中的 legacy page，没有真正使用 `load/bind/unbind` 生命周期和 PageResources。

建议选择 **B：迁移到 `webapp/pages/dashboard.js`**。该迁移是小范围前端架构整理，不需要修改 Dashboard DOM、API 或数据模型。

## 3. 当前 Dashboard 前端链路

```text
webapp/index.html
  Dashboard section 与展示节点
        |
webapp/app.js
  registerLegacyPages()
        |
loadDashboard()
        |
apiGet("/api/dashboard")
        |
window.KOLConnectAPI.get()
        |
renderDashboard()
```

当前实际位置：

- Dashboard DOM：`webapp/index.html` 第 39-109 行附近。
- Dashboard 格式化、列表渲染、主渲染和加载逻辑：`webapp/app.js` 第 1336-1416 行附近，共约 81 行。
- Legacy 页面注册：`webapp/app.js` 的 `registerLegacyPages()`。
- Dashboard 刷新事件：`webapp/app.js` 全局 `bindEvents()`。
- 启动时加载：`init()` 调用 `setPage("dashboard")`。
- 独立 `webapp/pages/dashboard.js`：当前不存在。

`app.js` 当前约 2293 行、90 KB。Dashboard 本身不算大，但继续留在全局文件会扩大 legacy 页面边界。

## 4. Legacy Cooperations 依赖审计

### 4.1 Dashboard 是否直接读取 Cooperations

否。

Dashboard 唯一数据请求为：

```text
GET /api/dashboard
```

前端未调用：

- `/api/creator-library/{creator_id}/cooperations`
- 任何 Cooperation 列表 API
- 任何 Excel 或本地文件接口
- 任何 CampaignCreator 明细 API

因此，Phase 3.13 后端更换数据源后，Dashboard 前端不需要知道底层来自 `CampaignCreator` 还是 `Cooperations`。

### 4.2 cooperation 相关字段渲染

Dashboard 仍使用以下兼容字段名：

- `overview.cooperation_spend`
- `cooperation_performance`
- `cooperation_performance.total_campaigns`
- `cooperation_performance.total_cost`
- `cooperation_performance.total_views`
- `cooperation_performance.average_roi`
- `cooperation_performance.top_creators`
- `action_items.incomplete_cooperations`

这些是 `/api/dashboard` 的兼容契约名称，不代表前端仍读取 Legacy `Cooperations`。不应仅因名称含有 `cooperation` 就删除或改名。

### 4.3 绕过 `/api/dashboard` 的旧请求

未发现。

Dashboard 的统计卡片、Top 达人、达人健康和待办事项全部来自同一次 `/api/dashboard` 响应，没有 N+1 请求。

### 4.4 Dashboard 之外的 Legacy Cooperation

以下位置仍存在 Legacy Cooperation 展示或写入，但不属于 Dashboard 链路：

- `webapp/index.html` Creator Detail 的“合作记录”区域。
- `webapp/pages/creator-library-detail.js` 的 `renderCooperations()`。
- `webapp/pages/creator-library-detail.js` 调用 `/api/creator-library/{creator_id}/cooperations` 保存旧合作记录。

这些内容不应在 Dashboard 前端迁移中删除。根据 Phase 3.12.1 规则，它们后续应单独收口为 Legacy 只读展示。

## 5. CampaignCreator 数据契约适配

Phase 3.13 保持了 `/api/dashboard` 返回结构，因此现有渲染代码在字段类型上兼容：

| 前端区域 | 使用字段 | 适配状态 |
|---|---|---|
| 达人资产 | `overview.total_creators` | 已适配 |
| 本周新增 | `overview.new_creators_7d` | 已适配 |
| 等待联系 | `overview.discovered_count` | 可正常显示 CampaignCreator `pending_contact` 数量 |
| 正在合作 | `overview.cooperating_count` | 可正常显示 `agreed/executing` 数量 |
| 累计合作花费 | `overview.cooperation_spend` | 已适配 CampaignCreator.`cost` |
| 平均 ROI | `overview.average_roi` | 可显示加权 ROI |
| Campaign 数量 | `cooperation_performance.total_campaigns` | 数值兼容，当前文案不准确 |
| 总花费 | `cooperation_performance.total_cost` | 已适配 |
| 总播放 | `cooperation_performance.total_views` | 已适配 |
| 合作 ROI | `cooperation_performance.average_roi` | 已适配 |
| Top 达人 | `cooperation_performance.top_creators` | 字段兼容，支持新排序结果 |
| 待联系列表 | `action_items.pending_contact` | `creator_id`、名称、平台可正常渲染和跳转 |
| 待复盘列表 | `action_items.incomplete_cooperations` | 数据兼容，当前标题不准确 |

### 5.1 语义偏差一：Campaign 数量

Phase 3.13 已将 `total_campaigns` 定义为未归档 CampaignCreator 关系中的去重 `campaign_id` 数量。

当前页面标题仍为：

```text
合作数量
```

建议后续迁移时仅把显示文案调整为：

```text
Campaign 数量
```

DOM id `dashboard-campaigns` 和 API 字段 `total_campaigns` 可保持不变。

### 5.2 语义偏差二：待复盘

Phase 3.13 已将 `incomplete_cooperations` 定义为：

```text
stage=completed 且 performance_note 为空
```

当前页面标题仍为：

```text
合作记录缺失
```

建议后续调整为：

```text
待复盘
```

当前渲染器不读取 `reason`，所以 `missing_performance_note` 不会引发前端错误，但页面没有向用户说明真正待处理的是表现复盘。

## 6. 当前生命周期审计

### 6.1 页面注册

Dashboard 当前由 `registerLegacyPages()` 注册：

```javascript
{
  load: () => loadDashboard(),
  bind: noop,
  unbind: noop
}
```

它形式上通过 PageRegistry 的接口校验，但不符合现有页面生命周期的实际目标。

### 6.2 事件资源

刷新按钮在全局 `bindEvents()` 中绑定：

```text
dashboard-refresh -> loadDashboard()
```

该监听在应用初始化时注册一次，当前不会因反复进入 Dashboard 而重复绑定，因此不是立即可复现的重复事件 Bug。

但它存在以下架构问题：

- 离开 Dashboard 后监听仍常驻。
- `unbind()` 无法释放该监听。
- Dashboard 请求没有绑定页面级 AbortController。
- 离开页面后，请求仍可能完成并更新隐藏 DOM。
- 快速重复刷新时，旧请求结果可能晚于新请求返回并覆盖新结果。

### 6.3 与已迁移页面的差异

`products.js`、`campaigns.js`、`campaign-detail.js`、`creator-library.js`、`creator-library-detail.js` 和 `settings.js` 已实现独立页面模块及 `load/bind/unbind`。

Dashboard 是当前主要页面中仍由 `app.js` legacy 注册管理的页面之一。

## 7. 是否需要迁移到 `pages/dashboard.js`

### 7.1 方案 A：暂不迁移

优点：

- 当前 CampaignCreator 数据能够正常显示。
- 不需要改动任何前端文件。
- 全局刷新监听只注册一次，短期不会产生重复绑定。

风险：

- Dashboard 继续游离于已建立的页面生命周期架构之外。
- 无法在离页时取消请求。
- 后续每次增加 Dashboard 展示逻辑都可能继续扩大 `app.js`。
- 语义文案仍不准确。
- 缺少独立 Dashboard 前端测试。

### 7.2 方案 B：迁移到 `pages/dashboard.js`

优点：

- 与 Product、Campaign、Creator Library、Settings 的页面架构一致。
- 请求和事件可由 PageResources 管理。
- 重复进入页面不会重复绑定。
- 离开页面可取消请求，避免旧响应覆盖。
- Dashboard 逻辑可以独立测试。
- `app.js` 可减少约 81 行 Dashboard 专属代码和两处 legacy 接线。

风险较低，因为：

- DOM 保持在 `index.html`，不需要拆 HTML。
- API 只调用 `/api/dashboard`。
- 不修改返回结构。
- 不改变页面导航 key `dashboard`。

### 7.3 推荐

推荐 **方案 B**。

该迁移应作为独立小阶段实施，不与 Dashboard 指标计算或 UI 重设计混合。

## 8. 推荐迁移范围

### 8.1 新增

新增：

```text
webapp/pages/dashboard.js
```

迁入：

- `formatDashboardNumber()`
- `formatDashboardTime()`
- `formatDashboardChange()`
- `renderDashboardCreatorList()`
- `renderDashboard()`
- `loadDashboard()`

### 8.2 页面生命周期

`dashboard.js` 应实现：

```text
load()
bind()
unbind()
```

职责建议：

- `load()`：创建 PageResources，通过 `KOLConnectAPI.get("/api/dashboard")` 加载和渲染。
- `bind()`：绑定刷新按钮和达人列表跳转。
- `unbind()`：清理监听、取消请求、使旧 lifecycle 结果失效。

### 8.3 app.js 调整

迁移时只需要：

- 从 `registerLegacyPages()` 移除 Dashboard loader 和 Dashboard legacy 注册。
- 从全局 `bindEvents()` 移除 `dashboard-refresh` 监听。
- 删除已经迁移的 Dashboard 专属函数。
- 为独立页面提供现有 `setPage()` 导航能力，确保点击达人仍可进入 `creator-library-detail`。

不应修改：

- `init()` 默认进入 Dashboard 的行为。
- Dashboard 页面 key。
- `/api/dashboard` 路径。
- Dashboard DOM 结构。

### 8.4 index.html 调整

仅在脚本区增加：

```html
<script src="pages/dashboard.js"></script>
```

脚本必须在 `app.js` 完成全局应用助手初始化之后、`DOMContentLoaded` 执行之前完成页面注册。现有同步 script 顺序可以满足。

指标文案可在同一小阶段修正：

- “合作数量”改为“Campaign 数量”。
- “合作记录缺失”改为“待复盘”。

这两项属于数据语义校正，不改变页面结构。

## 9. 测试建议

迁移实施时应增加 Dashboard 前端专项测试：

1. `dashboard` 页面完成独立注册。
2. 首次进入只请求一次 `/api/dashboard`。
3. 刷新按钮只触发一次请求。
4. 离开页面后请求被取消。
5. 重复进入不会重复绑定刷新事件。
6. 旧请求晚返回时不能覆盖新请求结果。
7. Phase 3.13 的完整响应可以渲染全部卡片和列表。
8. 空数组显示空状态，不报错。
9. API 异常显示错误但不影响其他页面导航。
10. Top 达人和待办点击仍进入正确 Creator Detail。
11. 页面显示“Campaign 数量”和“待复盘”。
12. Product、Campaign、Creator Library、Settings 页面回归正常。

## 10. 风险分级

### High

无。Phase 3.13 保持 API 契约后，未发现会导致 Dashboard 白屏或合作数据请求失败的前端阻塞项。

### Medium

- `total_campaigns` 已是去重 Campaign 数量，但页面显示“合作数量”。
- `incomplete_cooperations` 已是待复盘关系，但页面显示“合作记录缺失”。
- Dashboard 没有页面级 AbortController，存在旧请求覆盖新结果的可能。
- Dashboard 仍在 2293 行的 `app.js` 中，生命周期与其他新页面不一致。

### Low

- 本地变量和 API 分组仍使用 `cooperation` 命名；这是兼容命名，不影响数据正确性。
- 当前没有独立 Dashboard JS 测试，主要依赖后端 API 测试。

## 11. 最终回答

### 问题一：前端是否仍依赖 Legacy Cooperations

Dashboard 前端不依赖 Legacy `Cooperations`。它没有直接旧数据请求，只消费 `/api/dashboard` 的兼容响应。含 `cooperation` 的字段名可以保留，不应在本阶段删除。

Creator Detail 中仍有 Legacy Cooperation 展示与写入，但与 Dashboard 无关，应在后续独立阶段按“只读历史”规则收口。

### 问题二：是否需要迁移到 `pages/dashboard.js`

建议迁移。

当前 Dashboard 数据可以正常显示，但页面仍由 `app.js` 的 legacy 注册管理，`bind/unbind` 是空实现，刷新监听和请求不受 PageResources 管理。迁移范围清晰、风险低，不需要修改 API、数据模型或 Dashboard DOM。

## 12. 最终结论

Phase 3.13 的 CampaignCreator Dashboard 数据在字段结构上已经被当前前端正确消费，但页面语义和生命周期尚未完全适配。

建议下一阶段只实施 Dashboard 生命周期迁移与两处指标文案校正，不重构 UI，不改变 `/api/dashboard`，不触碰 Creator Detail 的 Legacy Cooperation 区域。
