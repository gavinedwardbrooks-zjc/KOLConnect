# KOLConnect v2 Phase 3.10 Campaign Detail UI Implementation Report

## 1. 实施范围

本阶段在现有 pywebview、原生 JavaScript、`page-registry` 和 `api-client` 架构内实现 Campaign Detail 页面，不新增导航入口，不修改后端接口、Repository、Excel、Chrome Extension 或飞书逻辑。

页面 key：`campaign-detail`

入口：Campaign 列表每行的“查看”按钮。

## 2. 页面结构

当前采用单页面分区展示，并通过 `data-campaign-section` 保留未来 Tab 化能力：

- `overview`：Campaign 名称、Product、国家、平台、日期、业务状态、预算、目标、负责人及归档状态。
- `creator-management`：参与达人、Agency、执行账号、阶段、报价、成本、发布链接、播放及 ROI。
- `execution-data`：发布链接与发布日期。
- `performance-result`：播放、点赞、评论、ROI 和复盘备注。

归档 Campaign 显示只读提示，禁用添加达人，并隐藏 CampaignCreator 编辑入口。恢复 Campaign 后由现有列表生命周期重新进入即可编辑。

## 3. 数据加载与 N+1 控制

首次进入页面使用 `Promise.all()` 并行请求：

- `GET /api/campaigns/{campaign_id}`
- `GET /api/campaigns/{campaign_id}/creators`

首次展示不请求 Product、Creator 或 Agency API。Campaign Detail 使用 Campaign API 已聚合的 `product_name`，达人列表使用 CampaignCreator API 已聚合的 `creator_name`、`agency_name`、`account_platform` 和 `account_url`。

只有用户主动打开“添加达人”时才请求一次 Creator Library 列表；选择达人或编辑合作关系时才按需请求该达人的账号详情。账号结果在当前页面生命周期内缓存，避免重复读取。

## 4. 添加与编辑合作关系

添加流程：

1. 从 Creator Library 下拉选择已有达人。
2. 读取并选择该达人的已有账号。
3. 调用 `POST /api/campaigns/{campaign_id}/creators`。

页面不支持直接输入达人名称创建 Creator。

编辑调用 `PATCH /api/campaign-creators/{id}`，支持：

- `stage`
- `account_id`
- `creator_quote`
- `cost`
- `publish_links`
- `publish_date`
- `views`
- `likes`
- `comments`
- `roi`
- `performance_note`

发布链接仅以安全的 HTTP/HTTPS 地址渲染为可点击链接。

## 5. 页面生命周期

页面实现完整生命周期：

- `load(context)`：读取 `campaignId`，创建页面资源并并行加载详情数据。
- `bind()`：绑定返回、重试、添加、编辑、保存、取消及达人账号选择事件。
- `unbind()`：移除事件监听、终止未完成请求、清空页面缓存和编辑状态。

重复进入页面不会重复绑定事件，离开页面后 AbortController 会终止页面所属请求。

## 6. 修改文件

- `webapp/index.html`
- `webapp/styles.css`
- `webapp/pages/campaigns.js`
- `webapp/pages/campaign-detail.js`
- `tests/test_phase3_10_campaign_detail_ui.js`
- `docs/KOLConnect_v2_Phase3_10_Campaign_Detail_UI_Implementation_Report.md`

## 7. 自动测试覆盖

新增测试覆盖：

- Campaign Detail 注册和首次加载。
- 首次加载严格使用两次聚合请求，无 Product、Creator、Agency N+1。
- Creator 无 Agency 时正常显示。
- 从已有 Creator 和 Account 创建 CampaignCreator。
- CampaignCreator 编辑字段通过现有 PATCH 接口提交。
- 归档 Campaign 只读。
- 页面离开后事件监听和请求资源释放。
- Campaign 列表存在详情入口并传递 `campaignId`。
- 页面不直接调用 `fetch()`。

执行结果：

- Python 完整测试：39/39 通过。
- 前端自动化测试：6/6 文件通过。
- `webapp` 全部 JavaScript 语法检查通过。
- `app` 全部 Python 语法检查通过。
- HTML 静态审计通过：250 个唯一 DOM ID，8 个脚本引用均存在。
- `git diff --check` 通过。

## 8. 未修改内容

- Campaign、CampaignCreator、Creator、Account、Agency 数据模型。
- Excel Schema 和迁移逻辑。
- Chrome Extension。
- 飞书同步。
- 后端 API Contract。
- CampaignCreator 唯一规则与执行账号定义。
