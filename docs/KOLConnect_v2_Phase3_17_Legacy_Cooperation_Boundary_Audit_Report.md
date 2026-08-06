# KOLConnect v2 Phase 3.17 Legacy Cooperation Boundary Audit Report

## 1. 审计范围与结论

本轮只读检查了 `webapp/`、`app/` 以及直接验证 Legacy Cooperation 兼容边界的测试代码。未修改业务代码、Excel 或用户数据，未执行 build、commit、push。

最终建议规则：

> Legacy Cooperation 定位为“已废弃、只读兼容”；CampaignCreator 是 v2 唯一可写合作记录。

历史 `Cooperations` Sheet、兼容读取和历史展示必须保留；旧版新增入口和写入 API 应关闭；旧数据不得自动转换成 CampaignCreator，也不得参与 Dashboard、Campaign 统计或 Creator 当前合作阶段推导。

## 2. Creator Detail 当前功能

### 2.1 展示位置

Creator Detail 页面在 `webapp/index.html` 的 `cooperations` Tab 中展示 Legacy Cooperation：

- 标题：合作记录。
- 统计：合作次数、总花费、平均播放、平均 ROI。
- 明细：项目、平台、联系日期、价格、发布数量、总播放、平均播放、ROI、结果、备注。
- 数据来源：`GET /api/creator-library/{creator_id}` 返回的 `cooperations` 和 `cooperation_statistics`。
- 渲染位置：`webapp/pages/creator-library-detail.js` 的 `renderCooperations()`。

同一详情页的 Overview 还单独展示“参与 Campaign”，该区域来自 `GET /api/campaigns?creator_id={creator_id}`，明确不包含旧版合作记录。

### 2.2 新增入口

当前仍存在完整新增入口：

- 页面标题：新增合作记录。
- 输入字段：项目、平台、联系日期、价格、发布数量、总播放、平均播放、ROI、结果、备注。
- 可选副作用：通过“更新达人状态”修改 Creator 状态。
- 保存按钮：`cooperation-save`。
- 前端方法：`saveCooperation()`。
- 请求：`POST /api/creator-library/{creator_id}/cooperations`。

新增成功后会重新加载 Creator Detail，因此旧记录和旧统计立即更新。

### 2.3 编辑入口

未发现 Legacy Cooperation 编辑入口：

- 明细表没有编辑按钮。
- 前端没有更新 Cooperation 的函数。
- 后端没有 PATCH/PUT Cooperation 路由。
- Repository 没有 `updateCooperation()`。

### 2.4 删除入口

未发现 Legacy Cooperation 删除或归档入口：

- 前端没有删除按钮。
- 后端没有 DELETE Cooperation 路由。
- Repository 没有 `deleteCooperation()` 或 `archiveCooperation()`。

## 3. Backend API 审计

### 3.1 API 矩阵

| 能力 | 当前接口 | 当前实现 | 结论 |
|---|---|---|---|
| 查询单个 Creator 的旧记录 | `GET /api/creator-library/{creator_id}` | Creator Detail 响应内嵌 `cooperations` 和 `cooperation_statistics` | 使用中，必须保留兼容读取 |
| 独立查询 Cooperation | 无 | 没有 `/cooperations` GET 路由 | 无需新增 |
| 创建 | `POST /api/creator-library/{creator_id}/cooperations` | 调用 `CreatorRepository.saveCooperation()` | 使用中，但应在 v2 关闭 |
| 更新 | 无 | 无前端、路由和 Repository 方法 | 保持不提供 |
| 删除 | 无 | 无前端、路由和 Repository 方法 | 保持不提供 |
| 归档/恢复 | 无 | Legacy 表没有 `archived_at` | 不应为旧模型补充新生命周期 |

### 3.2 Repository 行为

`CreatorRepository` 当前包含：

- `getCreatorCooperations(creator_id)`：按 Creator 查询并排序历史记录。
- `getCooperations()`：读取全表；当前没有生产调用方，注释仍声称供 Dashboard 使用，已过时。
- `saveCooperation(creator_id, payload)`：创建随机 `cooperation_id` 并写入 `Cooperations` Sheet。
- `_cooperation_statistics()`：计算旧记录数量、价格合计、平均播放和平均 ROI。

`saveCooperation()` 还会读取请求中的 `status`，并更新 `Creators.status`。这使旧合作记录不仅写入旧表，还可能改变 Creator Library 当前状态。

### 3.3 Dashboard 隔离

Dashboard 已不读取 `Cooperations`：

- 合作指标来源为 `CampaignCreatorRepository.getCampaignCreators()`。
- `DashboardRepository.get_cooperation_records()` 只是兼容方法名，返回的仍是 CampaignCreator。
- 回归测试明确加入高金额 Legacy Cooperation，并验证其不影响 Dashboard。

因此当前不存在“旧记录直接影响 Dashboard 指标”的生产路径。该隔离规则必须继续保留。

## 4. 必须保留的能力

### 4.1 历史查看

必须保留：

- `Cooperations` Sheet 及其现有字段。
- Creator Detail 对当前 Creator 历史记录的读取。
- 历史统计与历史明细展示。
- 老工作簿升级时原 Cooperation 行保持不变。
- 没有旧记录时返回空数组和零统计，不报错。

保留原因：旧记录是已经发生的业务事实。删除 Sheet、隐藏全部历史或自动清空都会造成数据丢失。

### 4.2 兼容读取

当前 `GET /api/creator-library/{creator_id}` 返回结构应继续保留：

```json
{
  "cooperations": [],
  "cooperation_statistics": {}
}
```

第一阶段不建议改名，以免破坏已有 Creator Detail 和旧客户端。前端应通过文案明确其为“旧版历史合作记录”。

### 4.3 数据结构兼容

以下内容应继续保留：

- `_COOPERATIONS_HEADERS`。
- 工作簿创建和缺失 Sheet 修复逻辑。
- Schema 检查中的 `Cooperations`。
- 旧工作簿迁移幂等测试。
- `getCreatorCooperations()` 和 `_cooperation_statistics()`。

## 5. 应关闭的能力

### 5.1 新建合作

应关闭 Creator Detail 的“新增合作记录”表单和保存按钮。v2 新合作必须通过：

```text
Product
↓
Campaign
↓
CampaignCreator
```

Creator 可以从 Creator Library 加入 Campaign，但不能再直接创建无 Campaign ID、无 Product ID、无 Account ID 的文本合作记录。

### 5.2 修改合作状态

应关闭 Legacy Cooperation 请求中的 `status` 副作用：

- 旧记录不能修改 `Creators.status`。
- Campaign 执行阶段只能由 `CampaignCreator.stage` 表示。
- Creator Library 的人工状态如果继续存在，应通过独立 Creator 状态接口维护，不能由旧 Cooperation 保存动作隐式修改。

### 5.3 影响 Dashboard 的操作

当前 Legacy Cooperation 已不影响 Dashboard。最终规则应明确禁止：

- 将 `Cooperations.price` 计入 Dashboard 成本。
- 将 `Cooperations.roi` 计入 Dashboard ROI。
- 将 `Cooperations.total_views` 计入 Dashboard 播放。
- 将旧记录数量计入活跃 Campaign 或合作达人数量。
- 使用旧记录推导待联系、执行中或待复盘。

Dashboard 的唯一合作数据源保持 CampaignCreator。

### 5.4 更新和删除

当前没有更新、删除、归档 API，不应为即将废弃的旧模型新增这些能力。

## 6. v2 最终边界规则

| 规则项 | Legacy Cooperation | CampaignCreator |
|---|---|---|
| 产品定位 | 旧版历史记录，只读兼容 | v2 正式合作记录 |
| 是否可创建 | 否 | 是 |
| 是否可编辑 | 否 | 是 |
| 是否可删除 | 否 | 否，使用归档 |
| 是否可归档/恢复 | 不新增 | 是，使用 `archived_at` |
| 是否关联 Product/Campaign | 否 | 是 |
| 是否要求执行账号 | 否 | 是 |
| 是否参与 Dashboard | 否 | 是 |
| 是否表示合作阶段 | 否 | 是，使用 `stage` |
| 是否可修改 Creator 状态 | 否 | 不隐式修改 Creator 状态 |
| 历史数据是否保留 | 是，永久保留 | 是 |

最终状态定义：

```text
Legacy Cooperation = Deprecated + Read Only + Preserved
CampaignCreator = Active Collaboration Source of Truth
```

## 7. 迁移方案

### 7.1 UI 处理

建议分一步完成，不需要迁移数据：

1. 将 Creator Detail Tab 文案从“合作记录”改为“旧版合作记录”。
2. 增加只读提示：“以下为旧版本历史数据，不参与 Campaign 和 Dashboard 统计。”
3. 保留统计卡片和历史明细表。
4. 移除或隐藏“新增合作记录”整块表单。
5. 移除 `cooperation-save` 事件绑定和 `saveCooperation()` 前端方法。
6. v2 当前合作继续通过“参与 Campaign”区域和 Campaign Detail 管理。
7. Legacy 与 CampaignCreator 统计不得合并展示。

不建议只把按钮设为 disabled：禁用控件仍会让用户误以为功能暂时不可用。明确的只读历史区域更符合最终产品边界。

### 7.2 API 处理

兼容读取：

- 保留 `GET /api/creator-library/{creator_id}` 中的旧记录与旧统计。

关闭写入：

- 保留旧 POST 路由作为一段兼容期的明确拒绝入口。
- 对 `POST /api/creator-library/{creator_id}/cooperations` 返回明确错误，例如 HTTP 410：

```text
旧版合作记录已设为只读，请通过 Campaign 添加和管理合作达人。
```

- 不再调用 `saveCooperation()`。
- 不新增 PATCH、DELETE、archive 或 restore API。

采用明确拒绝而不是直接删除路由，可以避免旧前端或缓存页面得到模糊的 404，并能告诉用户正确操作路径。

### 7.3 Repository 处理

必须保留：

- `getCreatorCooperations()`。
- `_cooperation_statistics()`。
- `Cooperations` Sheet 创建和兼容迁移逻辑。

停止生产调用：

- `saveCooperation()`。

清理候选：

- `getCooperations()` 当前无生产引用且注释过时。可在写入口关闭并完成全项目引用检查后删除，或暂时标记 deprecated。
- `saveCooperation()` 可先保留为未调用兼容代码，等一个稳定版本后再删除；禁止从 API 暴露。

### 7.4 数据处理

本阶段不要迁移、删除或重写 `Cooperations` 数据。

不建议自动迁移到 CampaignCreator，原因是旧记录通常缺少：

- `product_id`
- `campaign_id`
- `account_id`
- 标准 `stage`
- Campaign 归档状态
- 可验证的达人报价与成本区分

自动生成这些外键会制造伪业务关系。若未来确实需要将某条旧记录纳入 v2，应设计人工迁移工具，让用户逐条选择 Product、Campaign 和 Account，并保证幂等；该能力不属于当前收口阶段。

## 8. 测试调整建议

实施边界收口时应覆盖：

1. 老工作簿的 `Cooperations` 行数和内容保持不变。
2. Creator Detail 继续显示旧记录和旧统计。
3. 页面不再显示新增旧合作表单和保存按钮。
4. 旧 POST API 返回明确只读错误。
5. 被拒绝的 POST 不修改 Excel，不修改 Creator 状态。
6. Legacy Cooperation 仍不影响 Dashboard。
7. CampaignCreator 创建、编辑、归档和恢复保持正常。
8. 无旧数据时 Creator Detail 正常显示空状态。
9. 更新现有前端测试：移除“legacy cooperation must remain writable”断言，改为只读兼容断言。
10. 数据基础测试继续验证 `Cooperations` Sheet 和历史行不被删除。

## 9. 风险

### High

- 当前旧表单仍可创建第二套合作数据，且 Dashboard 和 Campaign 页面不可见。
- 当前旧保存动作可隐式修改 Creator 状态，造成 Creator 与 CampaignCreator 阶段不一致。

### Medium

- 直接删除 POST 路由会让旧前端得到不明确的 404；建议先返回明确的只读错误。
- 自动迁移旧数据会因缺少 Product、Campaign、Account 外键而产生错误关系。

### Low

- `getCooperations()` 的过时注释可能让维护者误以为 Dashboard 仍依赖旧表。
- API 兼容字段名继续使用 `cooperations`，需要通过文档和 UI 标识说明其为 Legacy 数据。

## 10. 最终判断

当前 Legacy Cooperation 尚未收口，因为它仍然可创建并可修改 Creator 状态。建议下一实施阶段只完成边界冻结：保留历史读取和展示，关闭 UI 与 API 写入，不迁移、不删除历史数据，并继续保证 Dashboard 只读取 CampaignCreator。
