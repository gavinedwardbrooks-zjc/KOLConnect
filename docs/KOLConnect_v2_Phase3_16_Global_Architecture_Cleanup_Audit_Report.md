# KOLConnect v2 Phase 3.16 Global Architecture Cleanup Audit Report

## 1. 审计范围与结论

本轮只读检查了：

- `webapp/app.js`
- `webapp/pages/`
- `webapp/index.html`
- `webapp/core/`
- `webapp/services/`
- `packaging/`
- `packaging/spec/KOLConnect.spec`
- 与 Legacy Cooperation、Dashboard 数据来源和静态资源加载直接相关的后端代码

未修改业务代码、数据、Excel 或打包产物，未执行 build、commit、push。

总体结论：v2 新页面架构已经有效接管 Dashboard、Creator Library、Product 和 Campaign 页面，但迁移尚未覆盖抓取、任务详情、审核、链接清洗、账号、邮件和日志页面。当前没有发现 Dashboard 或 Creator Library 的重复事件绑定；最大架构残留是 Legacy Cooperation 仍然可写。打包 spec 可以包含新增 JS，但当前 EXE 已过期，且构建脚本、安装器与 v2 开发版版本策略存在冲突。

## 2. app.js 当前职责

当前 `webapp/app.js` 约 2208 行、85 KB，仍不是纯应用入口。它承担以下职责：

| 领域 | 当前职责 | 状态 |
|---|---|---|
| 应用基础 | 中英文文案、全局 state、DOM 帮助函数、Toast、错误提示 | 使用中 |
| API 兼容 | `apiGet/apiPost/apiPatch/apiDelete` 对 `KOLConnectAPI` 的薄封装 | 使用中，但与统一 API Client 存在一层重复包装 |
| 导航 | `setPage()`、legacy 页面注册、启动默认进入 Dashboard | 使用中 |
| 抓取任务 | 任务列表、创建、重命名、删除、启动、暂停、继续、停止、恢复 | 使用中，尚未迁移 |
| 任务详情 | 链接搜索、筛选、编辑、删除、新增 | 使用中，尚未迁移 |
| 审核 | 结果加载、分页、编辑、重试、分析查看、飞书同步 | 使用中，尚未迁移 |
| 链接清洗 | 清洗、复制、清空 | 使用中，尚未迁移 |
| 账号 | Chrome Profile 列表、打开、保存 | 使用中，尚未迁移 |
| 邮件 | 邮箱设置、测试、收件箱同步、CRM 回复同步和安全渲染 | 使用中，尚未迁移 |
| 设置共享渲染 | 状态加载、飞书配置显示、Creator Library 工作簿路径显示、系统健康信息 | 使用中；事件已经迁移到 `pages/settings.js` |
| 全局轮询 | 抓取状态 3 秒轮询、任务列表 2 秒轮询 | 使用中，属于全局生命周期 |

`app.js` 目前仍包含大量业务代码，不符合最终“只保留初始化、全局状态、导航、页面注册”的目标，但这不是本轮可安全直接删除的代码。后续应按页面逐步迁移，不能一次性重构。

## 3. 迁移残留审计

### 3.1 Creator Library

Creator Library 的列表、筛选、排序、状态修改、详情、Snapshot、Trend、Campaign 集成和 Legacy Cooperation 展示已经位于：

- `webapp/pages/creator-library.js`
- `webapp/pages/creator-library-detail.js`

`app.js` 中只剩以下关联内容：

- `state.creatorLibrary`：保存列表视图与详情 Tab 状态。
- `setPage()`：为 Creator Library 两个页面提供 state、API、PageResources、params 和导航上下文。
- `renderCreatorLibraryConfig()`：设置页显示工作簿路径。

结论：没有发现 Creator Library 列表或详情业务的重复实现。以上残留目前仍被新页面依赖，应保留。长期可将页面 context 的构造统一化，但不是发布阻塞项。

### 3.2 Dashboard

Dashboard 数据加载、渲染、刷新、页面状态和事件已全部迁移至 `webapp/pages/dashboard.js`。

`app.js` 中只剩：

- Dashboard 国际化标题文本。
- 启动时导航到 Dashboard。
- Dashboard API 失败不阻止其他初始化的保护性注释和错误捕获。

未发现以下旧逻辑：

- `loadDashboard()`
- `renderDashboard()`
- `state.dashboard`
- 全局 `dashboard-refresh` 事件
- `registerLegacyPages()` 中的 Dashboard 注册

结论：Dashboard 迁移完整，没有业务残留或重复事件绑定。

### 3.3 Cooperation 统计

Dashboard 前端仍保留 `cooperation_performance`、`incomplete_cooperations` 等兼容字段名，但实际后端数据已经来自 `CampaignCreator`：

- `DashboardRepository.get_campaign_creator_records()` 读取未归档 CampaignCreator。
- `DashboardRepository.get_cooperation_records()` 只是兼容别名，也返回 CampaignCreator。
- `DashboardService` 的 Campaign 数量、成本、播放、ROI、待联系、执行中和待复盘均基于 CampaignCreator。

结论：Legacy `Cooperations` 不再参与 Dashboard 统计。字段名属于 API 兼容层，不代表旧数据源。

### 3.4 重复事件绑定

已迁移页面均使用 `PageResources.listen()` 并在 `unbind()` 中清理。Dashboard、Creator Library、Product、Campaign、Campaign Detail 与 Settings 没有发现同一控件同时由 `app.js` 和页面模块重复绑定。

legacy 页面事件仍由 `bindEvents()` 在 `DOMContentLoaded` 时统一绑定一次，并在整个应用生命周期常驻。页面切换不会再次调用 `bindEvents()`，因此当前没有直接的重复绑定；但这些事件不受页面生命周期管理，未来若局部迁移而未同步删除全局绑定，将产生重复执行风险。

## 4. 页面生命周期覆盖

| 页面 key | 实现位置 | load | bind | unbind | 结论 |
|---|---|---:|---:|---:|---|
| `dashboard` | `pages/dashboard.js` | 完整 | 完整 | 完整 | 已迁移，请求可取消并防止旧响应写回 |
| `creator-library` | `pages/creator-library.js` | 完整 | 完整 | 完整 | 已迁移 |
| `creator-library-detail` | `pages/creator-library-detail.js` | 完整 | 完整 | 完整 | 已迁移 |
| `products` | `pages/products.js` | 完整 | 完整 | 完整 | 已迁移 |
| `campaigns` | `pages/campaigns.js` | 完整 | 完整 | 完整 | 已迁移 |
| `campaign-detail` | `pages/campaign-detail.js` | 完整 | 完整 | 完整 | 已迁移 |
| `settings` | `pages/settings.js` | 完整 | 完整 | 完整 | 已迁移 |
| `scrape` | `app.js` legacy 注册 | 空 | 空 | 空 | 业务和事件均在 app.js，全局轮询常驻 |
| `task-details` | `app.js` legacy 注册 | 空 | 空 | 空 | 业务和事件均在 app.js |
| `review` | `app.js` legacy 注册 | 加载审核任务 | 空 | 空 | 只有 load，事件仍为全局绑定 |
| `discover` | `app.js` legacy 注册 | 空 | 空 | 空 | 业务和事件均在 app.js |
| `accounts` | `app.js` legacy 注册 | 空 | 空 | 空 | 业务和事件均在 app.js |
| `mail` | `app.js` legacy 注册 | 空 | 空 | 空 | 业务和事件均在 app.js |
| `logs` | `app.js` legacy 注册 | 空 | 空 | 空 | 静态展示，无页面资源管理 |

当前生命周期覆盖率：14 个注册页面中，7 个已完整迁移，1 个仅实现 load，6 个仍为空生命周期。

## 5. Legacy Cooperation 定位

### 5.1 当前事实

Legacy Cooperation 当前并非只读：

- Creator Detail 仍展示 `Cooperations` Sheet 的历史记录和统计。
- Creator Detail 仍显示“新增合作记录”表单。
- `creator-library-detail.js` 仍调用 `POST /api/creator-library/{creator_id}/cooperations`。
- `server.py` 仍将该请求转发至 `CreatorRepository.saveCooperation()`。
- `saveCooperation()` 会向 `Cooperations` Sheet 新增记录，并可根据表单值修改 Creator 的当前状态。

### 5.2 对 v2 模型的影响

Legacy Cooperation 不影响 Dashboard 指标，也不会创建 Campaign 或 CampaignCreator。但它会形成第二套可写合作数据源：

- v2 主模型：Product → Campaign → CampaignCreator。
- 旧模型：Creator → Cooperation 文本记录。

两者不会自动同步。用户继续使用旧表单时，Campaign 页面和 Dashboard 看不到该合作；同时 Creator 状态可能被旧表单修改，造成“Creator 显示合作中，但不存在 CampaignCreator”的业务不一致。

此外，`CreatorRepository.getCooperations()` 当前没有生产调用方，且其注释仍称供 Dashboard 使用，属于已过时说明和潜在清理候选；`getCreatorCooperations()`、`saveCooperation()` 和对应 API 仍有真实调用，不能直接删除。

### 5.3 建议定位

进入 v2 稳定版本前，应明确二选一：

1. 推荐：Legacy Cooperation 只读展示，停止新增入口，历史数据继续保留。
2. 临时兼容：继续允许写入，但界面明确标记“旧版合作记录，不参与 Campaign 和 Dashboard”。

当前实现不满足“Legacy Cooperation 只读”的目标，是 Phase 3 后续需要处理的高优先级架构项。

## 6. EXE 打包资源审计

### 6.1 Spec 与静态资源

项目根目录不存在 `KOLConnect.spec`；正式构建实际使用：

```text
packaging/spec/KOLConnect.spec
```

该 spec 使用动态项目根路径：

```python
PROJECT_ROOT = Path(SPECPATH).resolve().parents[1]
datas = [(str(PROJECT_ROOT / "webapp"), "webapp")]
```

该规则会递归复制整个 `webapp` 目录，因此下一次 PyInstaller 构建会包含：

- `pages/dashboard.js`
- `pages/creator-library.js`
- `pages/creator-library-detail.js`
- `pages/products.js`
- `pages/campaigns.js`
- `pages/campaign-detail.js`
- `pages/settings.js`
- `core/page-registry.js`
- `core/page-resources.js`
- `services/api-client.js`

`index.html` 当前引用的 12 个 CSS/JS 资源全部存在。运行时 `server.py` 从 `_MEIPASS/webapp` 提供静态文件，并支持 `.js` MIME 类型。因此从配置层面看，新增 JS 会被包含并可正常请求。

### 6.2 当前 EXE 状态

现有 `release/KOLConnect.exe` 修改时间为 2026-07-29 18:38:20，早于 2026-08-03 新增和修改的页面模块。该 EXE 不包含 Phase 3.15 Dashboard 页面迁移，也不能作为当前 v2 源码验收包。

### 6.3 打包风险

| 等级 | 风险 | 说明 |
|---|---|---|
| High | 构建输出覆盖稳定包 | `build_release.ps1` 固定复制到 `release/KOLConnect.exe`，没有 v2 开发版隔离目录。直接运行会覆盖旧稳定包。 |
| High | 安装器版本不一致 | EXE 版本资源和窗口标题为 `0.2.0-dev.1`，但 `KOLConnect.iss` 仍为 `0.1.2`，安装包名称也仍为 v0.1.2。 |
| High | 安装器可能读取旧 EXE | Inno Setup 固定读取 `release/KOLConnect.exe`；若未先正确构建，可能把 2026-07-29 的旧 EXE 打入安装包。 |
| Medium | 无实际冻结构建验证 | 本轮禁止 build，因此只能确认 spec 规则和文件引用，尚未验证生成 EXE 内的资源清单与运行时 404。 |
| Low | 大型依赖全量收集 | spec 对 webview、selenium、webdriver_manager 使用 `collect_all()`，会增加体积，但不影响新增 JS 是否被包含。 |

## 7. 风险与清理优先级

### High

1. Legacy Cooperation 仍可新增，并可修改 Creator 状态，形成与 CampaignCreator 并行的第二套合作真相。
2. v2 开发版版本资源与 v0.1.2 安装器元数据不一致。
3. 正式构建脚本固定覆盖 `release/KOLConnect.exe`，不适合 v2 内部测试包隔离。

### Medium

1. `app.js` 仍承载 7 个 legacy 页面的大量业务和全局事件。
2. legacy 页面没有真正的资源释放；后续迁移时容易与现有全局事件重复绑定。
3. 当前 EXE 早于新页面代码，不能用于验证当前源码。

### Low

1. `getCooperations()` 已无生产调用，注释也已过时，但在正式冻结 Legacy Cooperation 前不建议直接删除。
2. Dashboard API 仍使用 cooperation 命名作为兼容结构，可暂时保留，避免破坏前端和旧客户端。
3. `app.js` 的 API 薄封装与 `api-client.js` 重复一层，待 legacy 页面迁移时自然消除即可。

## 8. 推荐后续顺序

1. 先冻结 Legacy Cooperation 的产品定位，优先改为只读兼容，避免继续产生双轨合作数据。
2. 在下一次打包前建立 v2 独立输出目录和一致的版本元数据，禁止覆盖 v0.1.2 稳定 EXE。
3. 按风险顺序迁移 legacy 页面：Review → Scrape/Task Detail → Mail → Accounts/Discover/Logs。
4. 每迁移一个页面，同步移除 `bindEvents()` 中对应事件和 `registerLegacyPages()` 注册项。
5. legacy 页面迁移完成后，再收缩 `app.js` 的 API 包装、页面 state 和设置渲染职责。

## 9. 最终判断

- 新页面架构：可继续使用，Dashboard 与 Creator Library 迁移没有发现回退。
- Legacy Cooperation：尚未收口，不是只读，存在 v2 数据语义风险。
- 打包配置：新增 JS 会被下一次构建包含，但当前 EXE 已过期。
- v2 打包准备：在解决输出隔离与安装器版本不一致前，不建议直接执行现有正式构建/安装流程。
