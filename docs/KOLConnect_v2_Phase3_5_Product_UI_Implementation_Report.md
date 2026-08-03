# KOLConnect v2 Phase 3.5 Product UI Implementation Report

## 1. 实施范围

本阶段在现有 pywebview、原生 JavaScript 和单文件 `index.html` 架构下实现 Product Management 页面。

未引入 React、Vue、Vite、Webpack 或其他前端框架和构建工具。

未修改：

- `app/server.py`
- Repository
- Excel 结构
- Chrome Extension
- 飞书
- 邮件模块
- Product API 字段

未执行 commit、push 或 build。

## 2. 修改文件

### 新增

- `webapp/pages/products.js`
- `tests/test_phase3_5_product_ui.js`
- `docs/KOLConnect_v2_Phase3_5_Product_UI_Implementation_Report.md`

### 修改

- `webapp/index.html`
- `webapp/styles.css`
- `tests/test_phase3_1_frontend_foundation.js`

`webapp/app.js` 未增加 Product 业务逻辑。

## 3. 页面接入

页面键：

```text
products
```

导航归属：

```text
合作管理
```

新增子导航“产品管理”。进入页面时，顶部“合作管理”保持 active。

Product 页面通过以下方式注册：

```text
KOLConnectPages.registerPage("products", productPage)
```

Product 没有加入旧页面兼容注册器，从第一版开始即使用完整生命周期。

## 4. 页面结构

### 页面头部

- 产品管理标题。
- 显示已归档开关。
- 创建 Product 按钮。

### 同页创建/编辑卡片

字段：

- 产品名称，必填。
- 公司名称，必填。
- 备注，可选。

表单中没有：

- `status`
- `archived`
- `archived_at`
- ID 或时间字段

### Product 列表

显示：

- 产品名称。
- 公司名称。
- active Campaign 数量。
- 创建时间。
- 更新时间。
- Active/Archived 状态。
- 可用操作。

页面支持 Loading、Empty、Error 和 Loaded 四种列表状态。

## 5. Product 操作

### 创建

通过：

```text
POST /api/products
```

发送 `name`、`company_name`、`note`。

### 编辑

通过：

```text
PATCH /api/products/{id}
```

只更新 `name`、`company_name`、`note`。Archived Product 不显示编辑入口，需先恢复。

### 归档

通过：

```json
{
  "archived_at": "ISO时间"
}
```

归档前显示确认说明。存在 active Campaign 时，页面展示 API 返回的归档保护错误。

### 恢复

通过：

```json
{
  "archived_at": null
}
```

恢复不会修改 Campaign 或 CampaignCreator。

### 删除

页面没有 DELETE 调用、删除按钮或物理删除入口。

## 6. API 调用

所有请求只使用：

```text
window.KOLConnectAPI
```

页面代码不存在直接 `fetch()`。

列表加载：

- 默认：`GET /api/products`
- 包含归档：`GET /api/products?include_archived=true`

列表直接使用 API 返回的 `campaigns_count`，没有调用 `/api/campaigns`，不存在 N+1 请求。

所有请求都传递页面 AbortController signal。

## 7. 页面生命周期

### `load()`

- 清理旧页面资源。
- 创建新的 PageResources。
- 恢复“显示已归档”选择状态。
- 发起一次 Product 列表请求。
- 渲染列表状态和数据。

### `bind()`

绑定：

- 创建入口。
- 保存和取消。
- 编辑、归档、恢复事件委托。
- 显示已归档切换。
- 错误状态重新加载。

### `unbind()`

- 移除所有 Product 页面监听器。
- Abort 未完成的列表和修改请求。
- 清理临时编辑状态。
- 重置保存和归档操作状态。

页面没有 interval 或轮询任务。

重复进入会依次执行：

```text
unbind -> load -> bind
```

不会重复绑定事件。

## 8. 安全与稳定性

- Product 名称、公司名称和列表内容通过 `textContent` 创建，不拼接用户数据到 `innerHTML`。
- Product 使用 `product_id` 定位，不使用数组下标作为业务 ID。
- 列表请求切换时会取消上一请求，避免旧结果覆盖新筛选结果。
- 页面离开后，异步结果通过生命周期 ID 和 AbortController 双重阻止回写。
- 保存期间禁用保存按钮，防止重复提交。
- 归档和恢复增加操作锁，防止重复 PATCH。

## 9. 自动测试

新增 Product UI 测试覆盖：

1. 进入 Product 页面。
2. 列表正常加载。
3. 创建 Product。
4. 编辑 Product。
5. 归档 Product。
6. 显示 archived Product。
7. 恢复 Product。
8. 重复进入不会重复绑定。
9. 离开页面释放监听并 Abort 请求 signal。
10. 不调用 Campaign API。
11. 不调用 DELETE。
12. 页面不存在直接 `fetch()`。

结果：通过。

## 10. 回归结果

- Product UI 自动测试：通过。
- Phase 3.1 前端基础测试：通过。
- 达人分析、详情和趋势页面测试：通过。
- 邮件安全渲染测试：通过。
- 全部 Web JavaScript 语法检查：通过。
- Python 全量回归：34/34 通过。
- `git diff --check`：通过。

Dashboard、Creator Library、Task、Review、Mail 和 Settings 的原有实现未被迁移或改写。

## 11. 当前边界

- 本阶段没有 Product 详情页。
- 本阶段没有 Campaign 页面。
- Product 列表没有分页，符合当前 API 契约。
- 公司名称由 UI 强制必填；当前后端仍允许其他 API 客户端提交空公司名称。
- 未执行 EXE 构建或真实 pywebview 手工验收。

## 12. 结论

Product Management MVP 已接入现有前端基础架构。页面使用统一 API Client、Page Registry 和 Page Resources，完成 Product 列表、创建、编辑、归档和恢复，并保持旧页面与现有后端业务兼容。
