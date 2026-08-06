# KOLConnect v2 Phase 3.19 Release Candidate Audit Report

审计日期：2026-08-03
审计分支：`develop`
审计方式：只读代码、资源引用、Git 状态和现有 EXE 元数据检查；未修改代码、未修改数据、未提交、未推送、未构建。

## 一、结论摘要

当前 v2 Product-Campaign 核心链路已经具备内部测试基础：Product、Campaign、CampaignCreator 页面已接入页面生命周期；Creator Library 与 Campaign 已打通；Dashboard 已改用 CampaignCreator；Legacy Cooperation 已收口为只读历史模块。

但是，当前状态**不适合直接生成并分发 `v2.0.0-dev` EXE**。阻塞原因集中在发布工程，而非核心业务：源码显示版本为 `v0.2.0-dev.1`，安装脚本仍为 `v0.1.2`；现有构建脚本会覆盖稳定版 `release/KOLConnect.exe`；大量运行依赖仍未纳入 Git，无法将候选包可靠对应到一个提交；现有 EXE 也明显落后于当前源码。

发布判定：**No-Go（当前状态） / Conditional Go（完成本文 Critical 项后可进入内部测试版打包）**。

## 二、前端架构检查

### 2.1 app.js 当前职责

`webapp/app.js` 当前为 2,208 行、约 85 KB，仍不是纯应用启动文件。它目前负责：

- 应用初始化、全局状态、文案、导航与旧页面注册。
- 抓取任务、任务详情、审核结果、发现达人链接整理。
- 账号管理、邮件账户和收件箱管理。
- Settings 共用数据渲染辅助函数。
- 全局抓取状态轮询和任务列表轮询。

已经从 `app.js` 迁出的主要业务模块：Dashboard、Creator Library 列表、Creator Detail、Product、Campaign 列表、Campaign Detail、Settings。

结论：仍存在大块业务逻辑残留，但不构成内部测试 EXE 的直接阻塞；属于后续分阶段迁移的维护性风险，不建议在候选版打包前进行大范围整理。

### 2.2 页面生命周期覆盖

| 页面 | `load()` | `bind()` | `unbind()` | 当前状态 | 打包前是否必须迁移 |
|---|---:|---:|---:|---|---|
| Dashboard | 是 | 是 | 是 | 已迁移至 `pages/dashboard.js` | 否 |
| Creator Library | 是 | 是 | 是 | 已迁移至 `pages/creator-library.js` | 否 |
| Creator Detail | 是 | 是 | 是 | 已迁移至 `pages/creator-library-detail.js` | 否 |
| Products | 是 | 是 | 是 | 已迁移至 `pages/products.js` | 否 |
| Campaigns | 是 | 是 | 是 | 已迁移至 `pages/campaigns.js` | 否 |
| Campaign Detail | 是 | 是 | 是 | 已迁移至 `pages/campaign-detail.js` | 否 |
| Settings | 是 | 是 | 是 | 已迁移至 `pages/settings.js` | 否 |
| Review | 是 | 空实现 | 空实现 | 仅进入时加载，事件仍由全局绑定 | 否，建议下一轮迁移 |
| Scrape | 空实现 | 空实现 | 空实现 | 业务和事件仍在 `app.js` | 否，建议后续迁移 |
| Task Details | 空实现 | 空实现 | 空实现 | 业务和事件仍在 `app.js` | 否，建议后续迁移 |
| Discover | 空实现 | 空实现 | 空实现 | 业务和事件仍在 `app.js` | 否 |
| Accounts | 空实现 | 空实现 | 空实现 | 业务和事件仍在 `app.js` | 否 |
| Mail | 空实现 | 空实现 | 空实现 | 业务和事件仍在 `app.js` | 否，邮件页面复杂度较高 |
| Logs | 空实现 | 空实现 | 空实现 | 静态页面，暂无页面资源 | 否 |

`registerLegacyPages()` 仍注册 Scrape、Task Details、Review、Discover、Accounts、Mail 和 Logs。全局事件只在 `DOMContentLoaded` 时绑定一次，因此目前没有发现因页面重复进入而重复注册同一批全局事件的问题；但这些事件不受页面退出生命周期管理。

全局定时器包括抓取状态每 3 秒刷新、任务列表每 2 秒刷新。它们属于应用级轮询，而非当前页面级资源。不会随页面切换重复创建，但会在所有页面持续运行，属于性能优化项。

## 三、旧系统残留检查

### 3.1 Legacy Cooperation

Legacy Cooperation 已达到 v2 只读边界：

- Creator Detail 仅保留“Legacy Cooperation / 历史合作（只读）”展示。
- 前端未发现新增、保存、编辑或删除 Legacy Cooperation 的调用和按钮。
- 后端对匹配 `/api/creator-library/{id}/cooperations` 的 `POST`、`PUT`、`PATCH`、`DELETE` 均返回 HTTP 403。
- `CreatorRepository.saveCooperation()` 仍保留为防御入口，但会拒绝写入。
- `Cooperations` Sheet、历史查询和历史统计保留，旧数据不会被删除或迁移。

残留项：`server.py` 中仍有未被路由调用的 `save_creator_library_cooperation()` 辅助函数；`creator_repository.py` 中有一条旧注释仍写着“read/write compatible”；`getCooperations()` 的旧说明仍提及 Dashboard。这些均不形成运行写入口，但应在后续纯清理阶段修正文案或移除无引用包装函数。

### 3.2 Dashboard 数据源

Dashboard 已不读取 Legacy Cooperations：

- Repository 使用 `CampaignCreatorRepository.getCampaignCreators(include_archived=False)`。
- 合作阶段、花费、播放、ROI、待联系、执行中和待复盘均来自 CampaignCreator。
- `get_cooperation_records()` 只是兼容方法名，返回的仍是 CampaignCreator 数据。
- `/api/dashboard` 返回结构保持兼容，前端仍使用 `cooperation_performance` 和 `incomplete_cooperations` 字段名；这是兼容命名，不是旧数据依赖。

结论：Legacy Cooperation 不参与 Dashboard，无发布阻塞。

### 3.3 旧 API、按钮与事件

未发现 Dashboard 绕过 `/api/dashboard` 读取 Cooperations；未发现 Creator Detail 调用 Legacy Cooperation 写接口；未发现已删除的新增/编辑合作按钮事件残留。

现存旧架构主要是 `app.js` 对 Scrape、Review、Task、Discover、Accounts 和 Mail 的全局管理。这些是仍在使用的旧实现，不应在候选版前误删。

## 四、打包检查

### 4.1 PyInstaller 资源

正式 spec 位于 `packaging/spec/KOLConnect.spec`，入口为 `app/launcher.py`。spec 使用：

```text
datas = [(PROJECT_ROOT / "webapp", "webapp")]
```

因此整个 `webapp/` 目录会递归进入 EXE。新增的 `webapp/pages/*.js`、`webapp/core/*.js` 和 `webapp/services/api-client.js` 无需逐个加入 spec。

`webapp/index.html` 已引用以下资源，且审计时路径均存在：

- `services/api-client.js`
- `core/page-resources.js`
- `core/page-registry.js`
- `app.js`
- `pages/dashboard.js`
- `pages/creator-library.js`
- `pages/creator-library-detail.js`
- `pages/products.js`
- `pages/campaigns.js`
- `pages/campaign-detail.js`
- `pages/settings.js`

Python 端 `server.py` 直接导入 Product、Campaign、CampaignCreator 和 Dashboard Repository/Service，符合 PyInstaller 静态依赖发现方式。基于当前引用关系，不需要为这些模块增加 hidden import。

### 4.2 当前 EXE 是否落后源码

当前 `release/KOLConnect.exe`：

- FileVersion：`0.1.2`
- ProductVersion：`0.1.2`
- ProductName：`KOL Connect`
- 修改时间：`2026-07-29 18:38:20`
- 大小：`69,959,118` bytes

关键 v2 源码修改时间为 2026-08-01 至 2026-08-03。现有 EXE 明确落后于当前源码，不能用于 v2 验收。

### 4.3 版本和输出路径冲突

当前用户可见/构建元数据并未统一：

- 应用窗口、Web、服务日志和 Windows 版本资源：`v0.2.0-dev.1`
- Windows FileVersion：`0.2.0.1`
- 安装器：`v0.1.2`
- 本轮目标表述：`v2.0.0-dev`

因此当前不能真实地把构建产物标记为 `v2.0.0-dev`。必须先由产品方冻结最终测试版版本字符串和合法 Windows 数字版本，再统一必要元数据。

此外，`packaging/build_release.ps1` 会强制复制并覆盖 `release/KOLConnect.exe`。在稳定版 `v0.1.2` 仍需保留的前提下，不应直接使用该默认输出行为生成 v2 测试包。候选包应输出到独立目录和独立文件名。

### 4.4 源码可追溯性

当前分支为 `develop`，工作区存在大量已修改和未跟踪文件。未跟踪项包括当前运行所需的 Product、Campaign、CampaignCreator Repository，以及 `webapp/core/`、`webapp/pages/`、`webapp/services/`。

从本地文件可以运行这些代码，但候选 EXE 无法可靠对应到一个完整 Git commit。若此时打包，其他环境检出同一提交将缺失关键运行文件，构建不可复现。

## 五、风险分级

### Critical

1. **候选版本身份未冻结。** 当前源码为 `v0.2.0-dev.1`，安装器为 `v0.1.2`，目标却写为 `v2.0.0-dev`。不解决会产生错误版本的测试包。
2. **默认构建脚本会覆盖稳定 EXE。** `build_release.ps1` 最终覆盖 `release/KOLConnect.exe`，存在破坏已保留 v0.1.2 稳定包的风险。
3. **候选源码不可复现。** 多个运行必需文件仍未跟踪，当前源码不能由某个 Git commit 完整重建。

### High

1. **现有 EXE 已过期。** 当前 EXE 为 v0.1.2，且早于 v2 页面和 Repository 修改时间，不能作为本轮验收对象。
2. **安装器元数据落后。** `KOLConnect.iss` 仍使用 v0.1.2 和旧输出名；即使 EXE 更新，安装包仍会被标记为旧版本。
3. **尚未进行当前源码的完整候选构建和隔离启动验收。** 本轮按要求未构建，因此资源实际装载、首次启动、迁移幂等、端口释放等仍需下一阶段验证。

### Medium

1. **`app.js` 仍包含多个业务模块。** 文件体积大，Scrape、Task、Review、Mail 等页面尚未完成生命周期迁移。
2. **旧页面事件不受页面资源管理。** 当前只绑定一次，暂未形成重复监听，但后续迁移时必须同时移除全局绑定。
3. **全局轮询持续运行。** 抓取和任务轮询在所有页面执行，长期运行会产生不必要请求。
4. **Legacy Cooperation 存在无引用包装函数和过时注释。** 不影响只读边界，但增加维护歧义。

### Low

1. Dashboard API 仍保留 `cooperation_performance`、`incomplete_cooperations` 等兼容字段名，语义已迁移但命名仍带旧模型痕迹。
2. 页面 HTML 仍为单文件；这是当前 pywebview 架构的既定约束，不影响候选版。

## 六、打包前最低门槛

在不继续扩展功能的前提下，建议仅完成以下发布工程动作后再打包：

1. 明确测试版究竟命名为 `v0.2.0-dev.1` 还是 `v2.0.0-dev`，统一窗口、Web、服务日志、Windows 版本资源和安装器元数据。
2. 将候选包输出到独立目录和独立文件名，禁止覆盖 `release/KOLConnect.exe`。
3. 确认全部运行依赖和测试已纳入 Git，并以一个明确 commit 作为构建基线；不要求本报告阶段提交。
4. 在干净或可追溯的工作区执行完整自动测试、JS/Python 语法检查。
5. 执行隔离 APPDATA 的首次启动、旧数据迁移、二次启动幂等、页面/API、退出和端口释放验收。
6. 检查候选目录不包含工作簿、备份、日志、凭证、`.env`、Chrome Profile 或用户数据。

## 七、最终建议

### 是否可以打包 v2.0.0-dev

**当前不可以直接打包。** 原因不是 Product-Campaign 业务链路未完成，而是版本身份、输出隔离和源码可追溯性尚未满足发布候选的最低条件。

完成 Critical 项后，可进入**内部测试版 EXE 打包与隔离验收**。剩余 `app.js` 页面迁移、兼容字段重命名和 Legacy 辅助代码清理可以延期，不应在首次 v2 测试包前扩大改动范围。

最终状态：**No-Go as-is；完成发布工程前置项后 Conditional Go。**
