# KOLConnect v2 Phase 3.2 Product API Contract Report

## 1. 审计范围

本轮只读检查了：

- `app/product_repository.py`
- `app/campaign_repository.py`
- `app/data_repository_base.py`
- `app/server.py`
- Phase 1、Phase 2 相关自动测试与报告

未修改代码、Excel、Web 页面、Chrome Extension 或飞书，也未执行 commit、push 或 build。

## 2. 当前 Product 数据结构

Product 当前持久化字段为：

| 字段 | 类型/格式 | 写入规则 |
|---|---|---|
| `product_id` | 字符串，`product_` 加随机标识 | 服务端创建，不允许客户端修改 |
| `name` | 字符串 | 必填，去除首尾空白 |
| `company_name` | 字符串 | 可选，去除首尾空白 |
| `note` | 字符串 | 可选，去除首尾空白 |
| `created_at` | UTC ISO 8601 时间 | 服务端创建 |
| `updated_at` | UTC ISO 8601 时间 | 服务端创建或更新 |
| `archived_at` | 空字符串或 UTC ISO 8601 时间 | 服务端归档时写入 |

当前只有 `product_id` 是技术唯一键。`name`、`company_name` 以及两者组合均没有唯一约束，因此相同名称和公司可以创建多条 Product。

当前代码中 Product 只作为 Campaign 的父级使用。没有 Creator、CreatorAccount、Agency 或其他实体直接引用 `product_id`。

## 3. 当前 API 状态

### 3.1 `GET /api/products`

当前响应：

```json
{
  "ok": true,
  "products": [
    {
      "product_id": "product_xxx",
      "name": "BlockBlast",
      "company_name": "Hungry Studio",
      "note": "",
      "created_at": "2026-07-01T00:00:00Z",
      "updated_at": "2026-07-01T00:00:00Z",
      "archived_at": ""
    }
  ]
}
```

当前行为：

- 返回 Products Sheet 的全部持久化字段。
- 默认隐藏 `archived_at` 非空的 Product。
- 已支持 `include_archived=true`。
- 按 `created_at`、`product_id` 倒序排列。
- 不支持分页。
- 不支持名称、公司等过滤。
- 不返回总数或分页元数据。
- 不返回 `campaigns_count`。

### 3.2 `GET /api/products/{product_id}`

当前行为：

- 返回与列表相同的 Product 持久化字段。
- 可以读取已归档 Product。
- Product 不存在时返回 HTTP 404。
- 不包含关联 Campaign。
- 不包含 Campaign 数量。

详情接口保持 Product 单体返回是合理的。未来 Product 详情页如需 Campaign 列表，可单独调用一次 `GET /api/campaigns?product_id=...`，无需把完整 Campaign 集合嵌入 Product 详情。

### 3.3 `POST /api/products`

允许客户端提交：

| 字段 | 是否支持 | 规则 |
|---|---|---|
| `name` | 是 | 必填 |
| `company_name` | 是 | 可选 |
| `note` | 是 | 可选 |

以下字段由服务端生成或忽略客户端输入：

- `product_id`
- `created_at`
- `updated_at`
- `archived_at`
- 未识别字段

成功时返回 HTTP 201 和完整 Product。

### 3.4 `PATCH /api/products/{product_id}`

普通更新支持：

- `name`
- `company_name`
- `note`

不可更新：

- `product_id`
- `created_at`
- 客户端指定的 `updated_at`
- 客户端指定的 `archived_at`

传入 `{"archived": true}` 时进入归档逻辑，其他字段不会在同一次请求中更新。

已归档 Product 不能继续普通修改。当前没有恢复归档能力；`{"archived": false}` 或 `{"archived_at": null}` 都不会恢复 Product。

即使 PATCH 没有包含有效业务字段，当前实现仍会刷新 `updated_at`。

## 4. Product 列表字段需求对比

| 页面字段 | 当前支持 | 建议来源 |
|---|---|---|
| 产品名称 | 是 | `name` |
| 公司名称 | 是 | `company_name` |
| Campaign 数量 | 否 | API 聚合生成 `campaigns_count` |
| 创建时间 | 是 | `created_at` |
| 更新时间 | 是 | `updated_at` |
| 当前状态 | 间接支持 | 根据 `archived_at` 是否为空派生 |

不建议新增或持久化 Product `status` 字段。

页面状态规则应固定为：

```text
archived_at 为空     -> active
archived_at 非空     -> archived
```

## 5. `campaigns_count` 审计与建议

### 当前结论

当前 `GET /api/products` 不支持 `campaigns_count`。如果前端为每条 Product 分别调用 `GET /api/campaigns?product_id=...`，会形成 N+1 请求，不适合作为正式列表实现。

### 推荐实现

在 Repository 内一次打开工作簿，同时读取 Products 和 Campaigns：

1. 读取 Product 列表。
2. 读取一次 Campaign 列表。
3. 按 `product_id` 在内存中计数。
4. 将 `campaigns_count` 作为只读派生字段加入 API 响应。
5. 不把 `campaigns_count` 写入 Products Sheet。

这样仍然只发生一次工作簿加载和一次 API 请求，不绕过 Repository，也不会出现 N+1。

### 推荐计数口径

建议冻结：

```text
campaigns_count = 与 Product 关联的全部 Campaign 行数，包括 archived Campaign
```

原因：

- 该字段名称表达历史总 Campaign 数量，而不是进行中数量。
- Product 归档前要求所有关联 Campaign 已归档；若只统计活跃 Campaign，历史 Product 会统一显示 0，失去业务价值。
- 如果未来需要活跃 Campaign 数，应另命名为 `active_campaigns_count`，不要改变 `campaigns_count` 的既有语义。

### 推荐列表返回结构

```json
{
  "ok": true,
  "products": [
    {
      "product_id": "product_xxx",
      "name": "BlockBlast",
      "company_name": "Hungry Studio",
      "note": "",
      "campaigns_count": 5,
      "created_at": "2026-07-01T00:00:00Z",
      "updated_at": "2026-07-20T09:30:00Z",
      "archived_at": null
    }
  ]
}
```

目标契约已经冻结为：API 中 active Product 的 `archived_at` 返回 `null`。当前 Repository 返回空字符串，因此后续 API 实施需要在响应层规范化；迁移期间前端可以防御性兼容 `null` 和 `""`，但正式契约以 `null` 为准。

## 6. Product 归档机制

### 6.1 当前 PATCH 是否支持 `archived_at`

结论：**当前不支持通过 PATCH 修改 `archived_at`。**

当前 `PATCH /api/products/{product_id}` 的真实分支为：

1. 请求包含 `{"archived": true}` 时，调用 `archiveProduct()`，由服务端把 `archived_at` 写为当前时间。
2. 其他请求进入 `updateProduct()`，但该方法只处理 `name`、`company_name` 和 `note`。
3. `{"archived_at": null}` 会被忽略，不能恢复 Product。
4. `{"archived": false}` 也不会恢复 Product；已归档 Product 会因为禁止普通修改而返回冲突错误。

因此，现有 API 只完成了“归档”命令，没有完成冻结规则要求的 `archived_at` 双向修改契约。

### 6.2 当前归档行为

- 列表默认隐藏归档 Product：已实现。
- `GET /api/products?include_archived=true`：已实现。
- Product 存在未归档 Campaign 时禁止归档：已实现，返回 HTTP 409。
- Product 没有 Campaign 或只有已归档 Campaign 时允许归档：已实现。
- 归档操作幂等：已归档 Product 再次归档不会新增数据行。
- 已归档 Product 恢复：未实现。

### 6.3 冻结后的 PATCH 契约

继续使用 `archived_at` 作为唯一持久化状态，不增加 `status`。

现有 `PATCH /api/products/{product_id}` 需要扩展对 `archived_at` 的处理，不新增 `/restore` 或其他独立接口。

冻结规则：

```text
归档：archived_at = 服务端当前 UTC 时间
恢复：archived_at = null
```

推荐请求语义：

```json
{
  "archived_at": "2026-07-31T12:00:00Z"
}
```

表示归档。服务端不应信任客户端时间作为最终审计时间，而应写入服务端当前 UTC 时间并在响应中返回实际 `archived_at`。

```json
{
  "archived_at": null
}
```

表示恢复。服务端清空 `archived_at` 并更新 `updated_at`。

Phase 2 已有归档请求可以作为向后兼容别名继续接受：

```json
{
  "archived": true
}
```

但 Phase 3.3 Product 页面应统一使用冻结后的 `archived_at` 契约，不再依赖单向的 `archived` 命令。

明确结论：

- 需要扩展现有 PATCH 字段支持 `archived_at`。
- 无需、也不应新增独立恢复接口。
- 归档与恢复均通过 `PATCH /api/products/{product_id}` 完成。
- 不新增 Product `status` 字段。

### 6.4 恢复 Product 对关系数据的影响

当前关系为：

```text
Product
  -> Campaign.product_id
  -> CampaignCreator.campaign_id
```

Product 归档本身没有删除或改写 Campaign。恢复时也只需要修改 Product 行的 `archived_at`，并正常刷新元数据字段 `updated_at`。

恢复 Product 后：

- 已有 Campaign 的 `product_id` 保持不变，全部关联保留。
- 已有 CampaignCreator 的 `campaign_id`、`creator_id`、`account_id` 和合作数据保持不变。
- Campaign 当前状态保持不变，不自动从 `archived` 恢复。
- CampaignCreator 当前阶段或归档状态保持不变，不自动恢复。
- Product 的名称、公司、备注、创建时间等业务数据不变。
- 除 `archived_at` 和审计元数据 `updated_at` 外，不修改任何业务字段或关系数据。

这意味着恢复 Product 只是重新启用 Product 本身，不代表自动恢复其历史 Campaign 或合作执行记录。

## 7. 删除规则

当前 HTTP `DELETE /api/products/{id}` 不存在。`server.py` 的 DELETE 只处理本地任务，Product DELETE 会返回 404。

Repository 中的 `deleteProduct()` 仅为旧调用兼容名称，内部调用 `archiveProduct()`，不会删除 Excel 行。该方法当前只在数据层测试中使用，没有被 Product HTTP API 调用。

推荐继续冻结：

- Product 不提供物理删除 API。
- 有未归档 Campaign 时拒绝归档。
- 无 Campaign 时也使用软归档，不物理删除。
- 页面只调用 PATCH 归档，不调用 DELETE。

## 8. 分页与过滤建议

当前 Product 数量预期远低于 Creator 数量。Phase 3.3 首版页面可以继续使用完整列表，不要求立即增加分页。

建议冻结首版行为：

- 默认返回全部 active Product。
- 只支持 `include_archived=true`。
- 名称和公司搜索由前端在已加载列表中完成。
- 后续数据量明确增长后，再以向后兼容方式增加 `page`、`page_size` 和分页元数据。

## 9. 当前问题与风险

### P0：页面开发前必须解决

1. `campaigns_count` 缺失，不能让前端采用 N+1 请求补齐。
2. 当前 active Product 返回空字符串，与已冻结的 `archived_at=null` 契约不一致。
3. 当前 PATCH 不支持 `archived_at=null` 恢复，必须按冻结规则扩展现有接口。

### P1：页面开发前必须作出决定

1. `campaigns_count` 是否包含 archived Campaign；本报告建议包含。
2. Product 重复定义：当前只保证 `product_id` 唯一，同名同公司可以重复。
3. PATCH 空请求是否允许仅刷新 `updated_at`；建议无有效字段时返回 400，避免无意义更新时间变化。

### P2：可以延期

1. Product 分页。
2. 服务端名称或公司筛选。
3. 活跃 Campaign 单独计数。

## 10. Phase 3.2 最小 API 修改建议

Product 页面开发前，建议仅补充以下 API 能力：

1. Repository 一次读取 Products 和 Campaigns，生成只读 `campaigns_count`。
2. `GET /api/products` 返回聚合后的 Product 列表。
3. 明确 `campaigns_count` 统计全部 Campaign，包括 archived。
4. 将 active Product 的 `archived_at` API 响应统一为 `null`。
5. 扩展现有 PATCH：非空 `archived_at` 表示归档，`archived_at=null` 表示恢复。
6. 恢复只更新 Product 的 `archived_at` 与 `updated_at`，不修改 Campaign 或 CampaignCreator。
7. 增加聚合计数、默认归档过滤、恢复和 `include_archived=true` 的 API 测试。

不建议把完整 Campaign 列表嵌入 Product 列表或详情响应。

## 11. Phase 3.3 页面开发前必须冻结事项

| 项目 | 推荐冻结结果 |
|---|---|
| Product 主键 | `product_id`，不可修改 |
| Product 必填字段 | `name` |
| Product 可编辑字段 | `name`、`company_name`、`note` |
| Product 状态来源 | 仅由 `archived_at` 派生 |
| Product 状态字段 | 不新增 `status` |
| 列表默认范围 | 只返回 active Product |
| 历史查询 | `include_archived=true` |
| Campaign 数量 | `campaigns_count`，统计全部关联 Campaign |
| Campaign 详情加载 | 使用一次 `/api/campaigns?product_id=...` 请求 |
| 删除方式 | 禁止物理删除，只允许 PATCH 软归档 |
| 归档请求 | PATCH 非空 `archived_at`，服务端写当前 UTC 时间 |
| 恢复请求 | PATCH `archived_at=null`，不新增恢复接口 |
| 恢复影响 | 只更新 Product 归档元数据，保留全部 Campaign 和 CampaignCreator 关联 |
| 重复 Product | 当前允许；是否增加业务去重需产品确认 |
| 时间格式 | UTC ISO 8601 |
| 分页 | Phase 3.3 首版暂不启用 |

## 12. 审计结论

当前 Product API 的 CRUD、默认归档过滤、历史查询和删除保护已经具备，能够作为 Product 页面基础。

在 Phase 3.3 页面开发前，必须先补齐 `campaigns_count` 聚合、将 active Product 的 `archived_at` 响应统一为已冻结的 `null`，并扩展现有 PATCH 支持 `archived_at=null` 恢复。归档和恢复必须共用 `PATCH /api/products/{product_id}`，不得新增独立恢复接口；恢复不得改变任何 Campaign、CampaignCreator 或其他业务数据。
