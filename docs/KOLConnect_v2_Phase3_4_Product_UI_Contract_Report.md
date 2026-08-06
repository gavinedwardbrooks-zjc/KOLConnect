# KOLConnect v2 Phase 3.4 Product UI Contract Report

## 1. 审计范围

本轮只读检查了当前 Web 前端：

- `webapp/index.html`
- `webapp/app.js`
- `webapp/styles.css`
- `webapp/core/page-registry.js`
- `webapp/core/page-resources.js`
- `webapp/services/api-client.js`
- `webapp/pages/settings.js`

未修改代码、页面、数据或 API，也未执行 commit、push 或 build。

## 2. 当前前端架构确认

当前 Web UI 是原生 JavaScript 单页应用：

```text
index.html 单文件
-> data-page section
-> page-registry 切换 active section
-> pages/* 页面生命周期模块
-> api-client 调用本地 API
```

页面不是 Hash 路由，也不是服务端页面路由。页面切换由 `.nav-btn[data-page]` 和 `.page[data-page]` 完成。

Phase 3.1 已提供：

- `registerPage()`
- `getPage()`
- `navigate()`
- `load(context)`
- `bind(context)`
- `unbind(context)`
- 页面级事件、定时器和 AbortController 释放能力

Settings 已验证该模式可以在重复进入时避免重复绑定。Product 页面应完全沿用该结构。

## 3. Product 页面接入方式

### 3.1 页面标识

冻结页面键：

```text
products
```

HTML section：

```html
<section class="page" data-page="products">
```

页面模块建议位置：

```text
webapp/pages/products.js
```

模块通过以下方式注册：

```text
KOLConnectPages.registerPage("products", productPage)
```

Product 不应加入 `registerLegacyPages()`，因为它从第一版开始就应使用完整生命周期。

### 3.2 导航位置

Product 属于合作业务域，建议作为现有“合作管理”主导航下的子入口：

```html
<button
  class="nav-btn nav-sub"
  data-page="products"
  data-primary="mail"
>
  产品管理
</button>
```

这样进入 Product 页面时，顶部“合作管理”保持 active，不需要新增一级导航，也为后续 Campaign 页面保留同一业务分组。

### 3.3 脚本加载顺序

建议顺序：

```text
services/api-client.js
core/page-resources.js
core/page-registry.js
app.js
pages/products.js
pages/settings.js
```

`products.js` 必须在 DOMContentLoaded 前完成页面注册。HTML 仍保持单文件，不在本阶段拆分模板。

## 4. Product Management MVP 页面结构

### 4.1 页面头部

显示：

- 标题：产品管理
- 说明：管理产品及其 Campaign 归属
- 主操作：创建 Product
- 历史切换：显示已归档

建议结构：

```text
产品管理                         [显示已归档] [创建 Product]
管理产品及其 Campaign 归属
```

“显示已归档”默认关闭。关闭时请求 active Product；打开时请求 `include_archived=true`。

### 4.2 列表区域

MVP 使用管理表格，不使用卡片模式。原因：Product 字段少、操作明确，表格更适合比较公司、Campaign 数量和状态。

冻结列顺序：

| 列 | 数据来源 | 展示规则 |
|---|---|---|
| 产品名称 | `name` | 必须显示，空值视为异常数据 |
| 公司名称 | `company_name` | 必须显示，历史空值显示 `--` |
| Campaign 数量 | `campaigns_count` | 显示非负整数，只统计 active Campaign |
| 更新时间 | `updated_at` | 转换为本地可读时间 |
| 状态 | `archived_at` | `null` 为 Active，非空为 Archived |
| 操作 | 页面动作 | 根据状态动态显示 |

状态标签：

```text
Active   -> 绿色状态标签
Archived -> 灰色状态标签
```

不得从 Product `status` 字段读取状态，也不得新增该字段。

### 4.3 列表状态

页面必须支持：

- Loading：正在加载产品。
- Empty：暂无产品，提供创建入口。
- Error：显示友好错误并提供重新加载。
- Loaded：显示 Product 表格。

用户字段必须通过 `textContent` 或安全 DOM 创建方式渲染，不使用未转义 `innerHTML`。

## 5. Product 操作契约

### 5.1 创建 Product

入口：页面头部“创建 Product”。

行为：打开同页编辑区，不增加新路由。

成功后：

1. 关闭编辑区。
2. 重新加载 Product 列表。
3. 显示保存成功提示。

### 5.2 编辑 Product

active Product 显示“编辑”。

编辑时使用列表中已有 Product 数据填充表单，不需要额外调用 Product 详情 API。

archived Product 不允许直接编辑；用户必须先恢复，再进行修改。这与当前 Repository 对已归档 Product 的保护保持一致。

### 5.3 归档 Product

active Product 显示“归档”。

归档前显示确认提示：

```text
归档后，该产品将从默认列表隐藏。已有 Campaign 和合作数据不会删除。
```

如果 Product 仍有 active Campaign，API 返回 HTTP 409。页面直接显示服务端友好错误，不绕过保护。

### 5.4 恢复 Product

archived Product 显示“恢复”。

恢复后：

- Product 回到默认 active 列表。
- 保留全部 Campaign 关联。
- 保留全部 CampaignCreator 关联和合作数据。
- 不自动恢复 archived Campaign。
- 不自动修改 CampaignCreator 阶段或归档状态。

### 5.5 禁止操作

Product 页面不得提供：

- 删除按钮
- `DELETE /api/products/{id}` 调用
- 物理删除确认框
- Product 状态选择框

## 6. 创建与编辑表单

### 6.1 表单字段

| 字段 | UI 要求 | API 字段 |
|---|---|---|
| 产品名称 | 必填 | `name` |
| 公司名称 | 必填 | `company_name` |
| 备注 | 可选，多行文本 | `note` |

表单不得出现：

- `product_id` 可编辑输入框
- `status`
- `archived_at`
- `created_at`
- `updated_at`
- Campaign 数量输入框

这些字段由系统生成或操作生命周期控制。

### 6.2 校验规则

前端提交前：

- 产品名称去除首尾空白后不能为空。
- 公司名称去除首尾空白后不能为空。
- 备注允许为空。
- 保存期间禁用重复提交。

当前后端只强制 Product 名称必填，公司名称仍允许为空。Product 页面契约已经冻结公司名称为必填，因此首版 UI 必须校验；正式发布前建议后端同步收紧规则，避免其他 API 客户端写入空公司名称。

### 6.3 编辑区形式

MVP 建议使用同页可隐藏编辑卡片，而不是新增详情路由或依赖复杂 Modal：

```text
[页面头部]
[创建/编辑表单卡片，可隐藏]
[Product 列表卡片]
```

表单操作：

- 保存
- 取消

取消时清空当前编辑 ID 和未提交表单状态。

## 7. API 映射

页面只通过 `window.KOLConnectAPI` 调用 API。

### 7.1 加载默认列表

```text
KOLConnectAPI.get(
  "/api/products",
  { signal: resources.signal }
)
```

### 7.2 加载归档历史

```text
KOLConnectAPI.get(
  "/api/products?include_archived=true",
  { signal: resources.signal }
)
```

### 7.3 创建

```text
KOLConnectAPI.post(
  "/api/products",
  {
    name,
    company_name,
    note
  },
  { signal: resources.signal }
)
```

### 7.4 编辑

```text
KOLConnectAPI.patch(
  `/api/products/${encodeURIComponent(productId)}`,
  {
    name,
    company_name,
    note
  },
  { signal: resources.signal }
)
```

### 7.5 归档

```text
KOLConnectAPI.patch(
  `/api/products/${encodeURIComponent(productId)}`,
  { archived_at: new Date().toISOString() },
  { signal: resources.signal }
)
```

API 校验 ISO 时间，并由服务端写入实际归档时间。

### 7.6 恢复

```text
KOLConnectAPI.patch(
  `/api/products/${encodeURIComponent(productId)}`,
  { archived_at: null },
  { signal: resources.signal }
)
```

不新增 `/restore` API。

## 8. 页面状态模型

建议页面内部只维护：

```text
products            当前列表
includeArchived     是否包含归档 Product
editingProductId    当前编辑 Product ID，创建时为 null
formMode            create 或 edit
loading             是否正在加载
saving              是否正在保存
```

Product 行通过 `product_id` 定位。不得使用数组下标作为长期标识。

状态显示只由 `archived_at` 推导：

```text
archived_at === null -> Active
其他非空值           -> Archived
```

迁移防护期可将空字符串也视为 Active，但正式 API 契约以 `null` 为准。

## 9. 页面生命周期

Product 页面必须实现完整生命周期：

### `load(context)`

1. 清理上一次残留资源。
2. 创建新的 `PageResources`。
3. 设置 Loading 状态。
4. 根据 `includeArchived` 调用一次 Product 列表 API。
5. 保存响应并渲染列表。
6. 捕获非 Abort 错误并渲染 Error 状态。

### `bind(context)`

通过 `resources.listen()` 绑定：

- 创建按钮。
- 显示归档切换。
- 表单 submit。
- 表单取消。
- 列表操作事件。
- 错误状态重新加载。

列表操作建议使用一个事件委托监听器，不为每一行永久绑定独立监听器。

### `unbind(context)`

1. 调用 `resources.cleanup()`。
2. 取消未完成 GET、POST、PATCH 请求。
3. 移除页面事件监听。
4. 清理页面级 timeout 或 interval。
5. 清空临时编辑状态。

Product 页面不需要轮询定时器。

### 重复进入

当前 Page Registry 会执行：

```text
Product.unbind()
-> 切换 section
-> Product.load()
-> Product.bind()
```

因此重复进入会重新加载列表，但不会重复绑定事件。

## 10. 现有组件复用

可以复用现有样式：

- `.page-header`
- `.section-card`
- `.form-grid`
- `.field`
- `.action-row`
- `.primary-btn`
- `.secondary-btn`
- `.soft-btn`
- `.status-pill`
- `.review-table-wrap`
- `.review-table`
- `.empty-note`

实现时只需增加少量 Product 专用布局样式，不应复制 Creator Library 的整套渲染逻辑。

## 11. MVP 验收标准

### 列表

- 默认只显示 active Product。
- 可以切换显示 archived Product。
- 正确显示产品、公司、active Campaign 数量、更新时间和状态。
- 列表加载只发起一次 Product GET，不产生 N+1 Campaign 请求。

### 创建与编辑

- 产品名称和公司名称不能为空。
- 创建后列表出现新 Product。
- 编辑不改变 `product_id`。
- archived Product 不能直接编辑。

### 归档与恢复

- 归档后默认列表隐藏 Product。
- 历史列表仍能看到 Product。
- 恢复后 Product 回到默认列表。
- Campaign 与 CampaignCreator 关联不变。
- 页面不存在物理删除入口。

### 生命周期

- 首次进入只绑定一次事件。
- 离开页面后请求被取消、事件被释放。
- 连续进入三次不会产生重复保存或重复 PATCH。
- 页面切换过程中旧请求结果不会覆盖离开后的界面。

## 12. 页面开发前冻结结果

| 项目 | 冻结结果 |
|---|---|
| 页面键 | `products` |
| 导航归属 | 合作管理 |
| 页面形式 | 单页 Product 表格 + 同页编辑卡片 |
| 列表字段 | 名称、公司、Campaign 数、更新时间、状态、操作 |
| Campaign 数量 | 只统计 active Campaign |
| 状态来源 | `archived_at` |
| Product `status` | 不存在、不新增 |
| 创建字段 | `name`、`company_name`、`note` |
| 编辑字段 | `name`、`company_name`、`note` |
| 必填字段 | 产品名称、公司名称 |
| 删除 | 禁止 |
| 归档 | PATCH 非空 `archived_at` |
| 恢复 | PATCH `archived_at=null` |
| 恢复接口 | 不新增 |
| 页面生命周期 | `load`、`bind`、`unbind` |
| 页面轮询 | 不需要 |
| HTML | 继续保持单文件 `index.html` |

## 13. 结论

现有 Phase 3.1 前端基础已经可以直接承载 Product 页面。Product MVP 不需要新增前端框架、路由系统或 API 服务层，也不需要修改 `app.js` 的业务结构。

按本报告冻结的结构，下一阶段可以只新增 `index.html` 中的 Product section 与导航入口、`pages/products.js` 页面模块，以及必要的最小样式和自动测试。
