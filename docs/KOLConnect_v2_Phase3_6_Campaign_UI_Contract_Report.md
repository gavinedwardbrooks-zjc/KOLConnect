# KOLConnect v2 Phase 3.6 Campaign UI Contract Report

## 1. 审计范围与结论

本轮只审计以下现有实现，没有修改运行代码、Excel、Chrome Extension、飞书或页面：

- `app/campaign_repository.py`
- `app/campaign_creator_repository.py`
- `app/server.py`
- `app/data_repository_base.py`
- `app/creator_repository.py`
- `webapp/index.html`
- `webapp/app.js`
- `webapp/core/page-registry.js`
- `webapp/core/page-resources.js`
- `webapp/services/api-client.js`
- `webapp/pages/products.js`

结论：Campaign 与 CampaignCreator 的基础 CRUD、枚举校验、外键保护和软归档已经可用，但当前 API 仍是原始 Excel 行返回，尚不足以直接开发正式 Campaign 列表和 Campaign Detail。

页面开发前必须先补齐两组只读聚合：

1. Campaign 列表与详情返回 `product_name` 和 active `creators_count`。
2. CampaignCreator 列表返回 Creator 与执行账号的展示字段。

这些聚合必须在 Repository/API 层完成，禁止前端按行循环请求 Product、Creator 或 CreatorAccount。

---

## 2. 当前 Campaign API 能力

### 2.1 `GET /api/campaigns`

当前支持查询参数：

| 参数 | 当前行为 |
|---|---|
| `product_id` | 按 Product ID 过滤 |
| `status` | 按 Campaign 状态过滤，并校验枚举 |
| `include_archived=true` | 未指定 `status` 时同时返回 archived Campaign |

默认隐藏 `status=archived` 的记录。显式请求 `status=archived` 时可以查询已归档 Campaign。

当前每条记录直接来自 `Campaigns` Sheet，返回字段为：

| 字段 | 当前是否返回 | Campaign 列表用途 |
|---|---:|---|
| `campaign_id` | 是 | 行标识与详情导航 |
| `product_id` | 是 | Product 关联 ID |
| `name` | 是 | Campaign 名称 |
| `country` | 是 | 国家 |
| `platform` | 是 | 平台 |
| `start_date` | 是 | 开始日期 |
| `end_date` | 是 | 结束日期 |
| `owner` | 是 | 负责人 |
| `status` | 是 | 当前状态 |
| `budget` | 是 | 预算 |
| `goal` | 是 | 目标 |
| `note` | 是 | 备注 |
| `created_at` | 是 | 创建时间 |
| `updated_at` | 是 | 更新时间 |
| `product_name` | **否** | Product 名称展示 |
| `creators_count` | **否** | Campaign 达人数展示 |

当前不支持分页。MVP 数据量较小时可以接受，但应避免再叠加前端 N+1 请求。

### 2.2 列表聚合冻结规则

`GET /api/campaigns` 必须在 Campaign 页面实施前补充：

```json
{
  "campaign_id": "campaign_xxx",
  "product_id": "product_xxx",
  "product_name": "BlockBlast",
  "name": "Brazil Launch",
  "country": "Brazil",
  "platform": "TikTok",
  "start_date": "2026-08-01",
  "end_date": "2026-08-31",
  "status": "sourcing",
  "budget": 10000,
  "created_at": "2026-07-31T10:00:00Z",
  "updated_at": "2026-07-31T10:00:00Z",
  "creators_count": 12
}
```

冻结计算规则：

- `product_name`：通过 `Campaigns.product_id -> Products.product_id` 获取，即使 Product 已归档，历史 Campaign 仍应显示原 Product 名称。
- `creators_count`：统计该 Campaign 下 `CampaignCreators.archived_at` 为空的关系行。
- 因唯一键已经是 `campaign_id + creator_id`，active 关系行数即 active 达人数。
- 聚合字段只返回给 API，不写入 `Campaigns` Sheet。
- Repository 应在同一次工作簿读取中建立 Product 和 CampaignCreator 索引。
- 禁止前端为每条 Campaign 调用 `/api/products/{id}` 或 `/api/campaigns/{id}/creators`。

### 2.3 `GET /api/campaigns/{campaign_id}`

当前返回单条 Campaign 原始字段，不包含：

- `product_name`
- `creators_count`
- Product 详情
- CampaignCreator 列表

建议详情响应与列表保持同样的 `product_name`、`creators_count` 派生字段，但 CampaignCreator 列表继续使用独立接口，避免把详情响应无限扩大。

---

## 3. Campaign 创建与编辑契约

### 3.1 当前 `POST /api/campaigns` 支持字段

| 字段 | Repository 当前规则 | UI 契约 |
|---|---|---|
| `name` | 必填，不能为空 | 必填 |
| `product_id` | 必填；Product 必须存在且未归档 | 必填 |
| `status` | 可省略，默认 `draft`；必须符合枚举 | **UI 必填** |
| `platform` | 可选文本 | 可选 |
| `country` | 可选文本 | 可选 |
| `start_date` | 可选文本 | 可选日期 |
| `end_date` | 可选文本 | 可选日期 |
| `owner` | 可选文本 | 可选 |
| `budget` | 可选非负数字 | 可选 |
| `goal` | 可选文本 | 可选 |
| `note` | 可选文本 | 可选 |

补充结论：当前 API 已完整支持 `start_date`、`end_date`、`owner`、`goal`，Phase 3.6 前不需要为这四个字段扩展 POST。

“date”不是现有字段。前端必须分别提交 `start_date` 与 `end_date`，不得新增通用 `date` 字段。

### 3.2 当前 `PATCH /api/campaigns/{campaign_id}` 支持字段

当前支持更新：

- `name`
- `product_id`
- `country`
- `platform`
- `start_date`
- `end_date`
- `owner`
- `status`
- `budget`
- `goal`
- `note`

补充结论：PATCH 已完整支持 `start_date`、`end_date`、`owner`、`goal`，Phase 3.6 前不需要补充字段白名单。

更新 `product_id` 时，新 Product 必须存在且未归档。未知字段会被忽略，不应依赖未知字段透传。

### 3.3 状态契约

当前冻结枚举：

- `draft`
- `sourcing`
- `running`
- `completed`
- `archived`

UI 创建与普通编辑应提供 `draft`、`sourcing`、`running`、`completed`。`archived` 建议作为独立生命周期操作，不作为新建 Campaign 的普通状态选项。

当前归档方式：

```http
PATCH /api/campaigns/{campaign_id}
```

```json
{
  "archived": true
}
```

Repository 通过把 `status` 改为 `archived` 实现软归档，不删除 Excel 行。当前没有 Campaign DELETE 路由。

恢复可以通过现有 PATCH 把 `status` 改为一个有效业务状态，但恢复目标状态尚未冻结。Campaign UI 实施前应明确恢复到 `draft`，还是要求用户选择原业务状态；不得在前端自行猜测。

### 3.4 日期和预算校验边界

当前 Repository：

- 只把 `start_date`、`end_date` 保存为文本。
- 不验证日期格式。
- 不验证 `end_date >= start_date`。
- `budget` 必须是非负数字，空值允许。

MVP 页面可使用 `input[type=date]` 限制基本格式，但服务端日期顺序校验仍是发布前数据质量风险。

---

## 4. Campaign 列表页面契约

页面 key 冻结为：

```text
campaigns
```

导航归属：

```text
合作管理
```

### 4.1 列表列顺序

| 列 | 数据字段 | 当前 API 状态 |
|---|---|---|
| Campaign 名称 | `name` | 已有 |
| Product 名称 | `product_name` | **需聚合** |
| 国家 | `country` | 已有 |
| 平台 | `platform` | 已有 |
| 状态 | `status` | 已有 |
| 日期 | `start_date`、`end_date` | 已有 |
| 预算 | `budget` | 已有 |
| 创建时间 | `created_at` | 已有 |
| 达人数 | `creators_count` | **需聚合** |

列表只允许一次调用 `GET /api/campaigns` 获取展示行。Product 名称和达人数必须随列表响应直接返回。

创建/编辑表单需要 Product 下拉选项时，可以额外一次调用 `GET /api/products`。这不是按行 N+1，且应只加载 active Product。

### 4.2 创建/编辑表单

冻结字段：

必填：

- Campaign 名称：`name`
- Product：`product_id`
- 状态：`status`

可选：

- 平台：`platform`
- 国家：`country`
- 预算：`budget`
- 开始日期：`start_date`
- 结束日期：`end_date`
- 负责人：`owner`
- 目标：`goal`
- 备注：`note`

不得新增 Excel 字段或通用 `date` 字段。

---

## 5. Campaign Detail 与 CampaignCreator 契约

页面 key 冻结为：

```text
campaign-detail
```

进入详情页时通过页面上下文传递：

```js
KOLConnectPages.navigate("campaign-detail", { campaignId })
```

不得依赖全局临时 DOM 文本推断 Campaign ID。

### 5.1 当前接口能力

当前详情需要调用：

```text
GET /api/campaigns/{campaign_id}
GET /api/campaigns/{campaign_id}/creators
```

第二个接口当前只返回 CampaignCreator 原始字段：

- `id`
- `campaign_id`
- `creator_id`
- `account_id`
- `stage`
- `owner`
- `creator_quote`
- `cost`
- `publish_links`
- `publish_date`
- `views`
- `likes`
- `comments`
- `roi`
- `performance_note`
- `created_at`
- `updated_at`
- `archived_at`

它不返回 Creator 名称，也不返回执行账号的平台、用户名或主页链接。因此当前 API 不能直接满足正式详情表格。

### 5.2 详情页所需展示字段

| 展示项 | 当前字段/来源 | 当前是否可直接展示 |
|---|---|---:|
| 达人 | `creator_name` | **否** |
| Creator ID | `creator_id` | 是 |
| 执行账号 | `account_username` / `account_profile_url` | **否** |
| 账号平台 | `account_platform` | **否** |
| Account ID | `account_id` | 是 |
| 合作阶段 | `stage` | 是 |
| 报价 | `creator_quote` | 是 |
| 成本 | `cost` | 是 |
| 播放 | `views` | 是 |
| ROI | `roi` | 是 |
| 发布链接 | `publish_links` | 是，但当前为 JSON 字符串 |

建议 `GET /api/campaigns/{id}/creators` 在 Repository 层一次读取 CampaignCreators、Creators 和 CreatorAccounts，并增加只读字段：

```json
{
  "id": "campaign_creator_xxx",
  "creator_id": "creator_xxx",
  "creator_name": "Maria",
  "account_id": "account_xxx",
  "account_platform": "TikTok",
  "account_username": "maria",
  "account_profile_url": "https://www.tiktok.com/@maria",
  "stage": "negotiating",
  "creator_quote": 500,
  "cost": 400,
  "views": 100000,
  "roi": 2.5,
  "publish_links": "[\"https://example.com/video\"]"
}
```

这些展示字段不写入 `CampaignCreators` Sheet。

禁止详情页对每条关系分别调用 `/api/creator-library/{creator_id}`。现有 Creator Detail 接口可以返回单个达人的账号，但逐行调用会形成 N+1，并把 Campaign 页面耦合到 Creator Library 的分析详情结构。

### 5.3 添加达人时的现有数据来源

现有接口可用于选择流程：

1. `GET /api/creator-library`：一次获取 Creator 候选列表。
2. 用户选定 Creator 后，`GET /api/creator-library/{creator_id}`：一次获取该 Creator 的 `accounts`。
3. `POST /api/campaigns/{campaign_id}/creators`：提交 `creator_id`、`account_id` 和合作字段。

这是用户选择后的单次明细请求，不是列表逐行 N+1。若后续需要大规模搜索，应另行设计轻量查询接口，但不属于本轮 UI 契约。

### 5.4 CampaignCreator 关系规则

唯一规则保持不变：

```text
campaign_id + creator_id
```

`account_id` 仅表示本次 Campaign 的默认执行账号，不参与唯一键。

当前 Repository 已验证：

- Campaign 必须存在且不是 archived。
- Creator 必须存在。
- CreatorAccount 必须存在。
- Account 必须属于所选 Creator。
- 同一 Campaign 不允许重复添加同一 Creator。

即使更换 `account_id`，仍然更新同一条 CampaignCreator，不新增第二条关系。

当前更新 API 技术上允许修改 `campaign_id` 和 `creator_id`。正式 UI 不应暴露移动关系功能；创建后只允许更新执行账号和合作数据。

### 5.5 CampaignCreator 阶段

冻结枚举：

- `pending_contact`
- `contacted`
- `quoted`
- `negotiating`
- `agreed`
- `executing`
- `completed`
- `rejected`

UI 必须发送枚举值，显示层可以使用中文标签。

### 5.6 CampaignCreator 归档限制

当前支持 `PATCH /api/campaign-creators/{id}` + `{ "archived": true }` 归档，但没有恢复 `archived_at` 的现有契约。并且唯一性检查包含已归档关系，因此归档后不能重新添加同一 Creator。

Phase 3.6 页面开发前必须决定：

- MVP 暂不提供移除/归档 CampaignCreator；或
- 先补充同一 PATCH 的恢复语义。

在规则冻结前，不应在详情页提供“删除达人”按钮。

---

## 6. 页面生命周期契约

### 6.1 `campaigns` 页面

```js
{
  async load(context) {},
  bind(context) {},
  unbind(context) {}
}
```

`load()`：

- 创建页面级 `PageResources`。
- 一次请求 Campaign 列表。
- 一次请求 active Product 作为表单选项。
- 渲染 loading、empty、error、loaded 状态。

`bind()`：

- 绑定创建、编辑、归档、筛选和进入详情事件。
- 使用列表事件委托，避免逐行重复绑定。

`unbind()`：

- 移除全部页面监听。
- 中止未完成请求。
- 清理 timeout/interval。
- 清空编辑态和 mutation lock。

### 6.2 `campaign-detail` 页面

`load(context)`：

- 校验 `context.campaignId`。
- 并行请求 Campaign 详情与 CampaignCreator 列表。
- 保存本次 lifecycle ID，防止旧请求覆盖新 Campaign。
- 按需加载 Creator 候选；不要在未打开“添加达人”表单时预取每位达人详情。

`bind(context)`：

- 绑定返回列表、添加达人、编辑关系、切换执行账号和保存结果。
- 事件委托只绑定一次。

`unbind(context)`：

- 中止 Campaign、关系、Creator 和 Account 请求。
- 关闭编辑表单并清理选中状态。
- 移除全部监听和定时器。

两个页面都必须通过 `page-registry` 注册，只能通过 `api-client` 调用 API，禁止页面直接 `fetch()`。

---

## 7. 当前 Web 架构接入方式

建议未来实施时新增：

```text
webapp/pages/campaigns.js
webapp/pages/campaign-detail.js
```

`index.html` 继续保持单文件，新增：

- `data-page="campaigns"` section
- `data-page="campaign-detail"` section
- 合作管理下的 Campaign 子导航按钮
- 两个页面脚本引用

脚本顺序继续保持：

```text
services/api-client.js
core/page-resources.js
core/page-registry.js
app.js
pages/products.js
pages/campaigns.js
pages/campaign-detail.js
pages/settings.js
```

### 7.1 详情页导航高亮风险

当前 `page-registry` 只从同名导航按钮读取 `data-primary`。`campaign-detail` 通常没有独立导航按钮，因此进入详情页后“合作管理”可能失去 active 状态。

页面实施前应采用一个最小兼容方案，让详情 section 声明父级导航，例如 `data-primary="mail"`，并让 registry 在找不到同名按钮时读取 section 的 `data-primary`。不要为详情页创建可见的重复导航入口，也不要引入新路由框架。

---

## 8. API 缺口与前置修改

### P0：页面开发前必须补齐

1. `GET /api/campaigns` 增加 `product_name`。
2. `GET /api/campaigns` 增加 active `creators_count`。
3. `GET /api/campaigns/{id}` 建议同步返回上述两个字段。
4. `GET /api/campaigns/{id}/creators` 增加 Creator 名称和执行账号展示字段。
5. 聚合必须在 Repository 层完成，并增加回归测试。

### P1：开发前必须冻结规则

1. Campaign 从 archived 恢复时的目标状态。
2. CampaignCreator 是否在 MVP 提供归档；如提供，必须先确定恢复方式。
3. `publish_links` API 是否继续返回 JSON 字符串，还是 API 层转换为数组。当前页面实现必须按真实字符串格式处理，不能假设已经是数组。
4. 是否由服务端校验日期范围；当前仅有前端日期控件仍不足以保护其他 API 调用方。

### 无需补充

- `POST /api/campaigns` 已支持 `start_date`、`end_date`、`owner`、`goal`。
- `PATCH /api/campaigns/{id}` 已支持 `start_date`、`end_date`、`owner`、`goal`。
- CampaignCreator 已支持阶段、报价、成本、执行账号、播放、点赞、评论、ROI、发布链接和表现备注。
- 不需要改变 `campaign_id + creator_id` 唯一规则。
- 不需要让 `account_id` 参与唯一键。
- 不需要修改 Excel Schema。

---

## 9. 推荐开发顺序

1. 冻结 Campaign 恢复状态、CampaignCreator 归档恢复和 `publish_links` 响应类型。
2. 在 Campaign Repository 中实现 `product_name`、`creators_count` 一次性聚合。
3. 在 CampaignCreator Repository 中实现 Creator/Account 展示字段一次性聚合。
4. 扩充 API 测试，验证无 N+1、归档计数、历史 Product 名称和账号归属。
5. 实现 `campaigns` DOM、页面模块和生命周期测试。
6. 实现 `campaign-detail` DOM、上下文导航、关系编辑和生命周期测试。
7. 回归 Product、Settings、Dashboard、Creator Library、Task、Review、Mail 页面。

---

## 10. 风险清单

### High

1. Campaign 列表缺少 `product_name` 和 `creators_count`，直接开发会导致 N+1 请求或 UI 缺列。
2. CampaignCreator 响应缺少 Creator/Account 展示字段，详情页无法可靠显示达人和执行账号。
3. Campaign Detail 没有同名导航按钮，当前 registry 可能无法保持“合作管理”高亮。

### Medium

1. Campaign 归档使用 `status=archived`，恢复目标状态未冻结。
2. CampaignCreator 归档后没有恢复契约，且唯一性校验会阻止重新添加。
3. API 的 `status` 可省略并默认 `draft`，但 UI 契约要求必填；测试需覆盖两者兼容。
4. 日期仅按文本保存，缺少格式和先后顺序校验。
5. `publish_links` 在 API 中是 JSON 字符串，前端若按数组处理会发生展示错误。
6. 编辑 archived Campaign 时，Repository 仍会验证父 Product 必须 active；Product 已归档时，Campaign 更新会被拒绝。

### Low

1. Campaign 列表暂不分页，数据量增长后需要再评估。
2. 当前 `app.js` 仍全局绑定旧页面事件；新 Campaign 页面必须保持独立生命周期，避免继续扩大旧逻辑。

---

## 11. 最终冻结结论

| 项目 | 冻结结果 |
|---|---|
| Campaign 页面 key | `campaigns` |
| Campaign Detail key | `campaign-detail` |
| 导航归属 | 合作管理 |
| Campaign 必填字段 | `name`、`product_id`、`status` |
| Campaign 可选字段 | `platform`、`country`、`budget`、`start_date`、`end_date`、`owner`、`goal`、`note` |
| CampaignCreator 唯一键 | `campaign_id + creator_id` |
| `account_id` 语义 | 本次 Campaign 默认执行账号 |
| 列表 Product 名称 | API/Repository 聚合，禁止前端 N+1 |
| 列表达人数 | active CampaignCreator 数，API/Repository 聚合 |
| 详情达人和账号 | API/Repository 聚合展示字段 |
| 页面请求 | 只能通过 `api-client` |
| 生命周期 | 必须实现 `load()`、`bind()`、`unbind()` |
| Excel Schema | 不修改 |

当前不建议直接进入 Campaign UI 编码。应先完成 P0 聚合契约实现与测试，再进入 Campaign 列表和详情页面开发。
