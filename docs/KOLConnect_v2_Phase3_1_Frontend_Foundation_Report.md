# KOLConnect v2 Phase 3.1 前端基础架构报告

## 1. 实施范围

本阶段只建立前端基础架构，没有开发 Product 或 Campaign 页面。

未修改桌面服务、Repository、Excel 数据、Chrome Extension、飞书和打包配置。Web 端继续使用原生 JavaScript 与 pywebview，`index.html` 继续保持单文件。

## 2. 修改文件

### 新增

- `webapp/services/api-client.js`
- `webapp/core/page-registry.js`
- `webapp/core/page-resources.js`
- `webapp/pages/settings.js`
- `tests/test_phase3_1_frontend_foundation.js`

### 修改

- `webapp/index.html`
- `webapp/app.js`
- `tests/test_frontend_detail_pages.js`

## 3. API Client

`webapp/services/api-client.js` 现在是浏览器端统一 HTTP 请求入口。

支持：

- `GET`
- `POST`
- `PATCH`
- `DELETE`，用于兼容现有任务删除操作

所有请求均支持可选的 `AbortController.signal`。`app.js` 中原有 `apiGet`、`apiPost`、`apiDelete` 调用方式保持兼容，内部改为委托给统一客户端；同时预留 `apiPatch` 供后续页面使用。

原有服务连接失败和返回异常的友好错误信息保持不变。

## 4. 页面注册与生命周期

`webapp/core/page-registry.js` 提供：

- `registerPage(name, lifecycle)`
- `getPage(name)`
- `navigate(name, context)`

每个注册页面必须完整定义：

```text
load(context)
bind(context)
unbind(context)
```

页面切换顺序为：

```text
currentPage.unbind()
-> 切换导航和 active section
-> nextPage.load()
-> nextPage.bind()
```

重复进入当前页面也会执行完整生命周期。这样既保留原先重复点击 Dashboard、审核或达人库时重新加载的行为，也能防止 Settings 监听器累积。

Dashboard、Creator Library、Scrape、Task、Review、Mail、Accounts、Discover 和 Logs 通过兼容生命周期注册，原有页面逻辑未迁移、未重写。

## 5. 页面资源管理

`webapp/core/page-resources.js` 统一管理页面拥有的资源：

- 事件监听器
- interval
- timeout
- 页面生命周期 `AbortController`
- 页面额外创建的请求 `AbortController`

调用 `cleanup()` 会移除监听、清理定时器并取消未完成请求。重复调用 `cleanup()` 是安全的。

## 6. Settings 页面迁移

Settings 是本阶段唯一迁移到完整生命周期的页面。

### `load()`

- 通过 `/api/state` 加载当前设置。
- 将页面生命周期 signal 传给 API Client。
- 更新界面语言、Profile、达人库路径、飞书和调试设置。

### `bind()`

- 绑定界面设置保存。
- 绑定系统健康检查。
- 绑定 Debug 显示切换。
- 绑定飞书设置保存。
- 绑定达人库文件路径保存。
- 绑定语言预览。

### `unbind()`

- 移除 Settings 的全部事件监听。
- 取消未完成的 Settings 请求。
- 释放页面拥有的定时器和控制器。

Settings 事件已从全局 `bindEvents()` 移除，因此离开后再次进入不会出现重复保存或重复回调。

## 7. 资源分类结果

现有两个状态轮询仍属于全局生命周期：

- 抓取状态：每 3 秒刷新一次。
- 任务列表状态：每 2 秒刷新一次。

离开 Scrape 后，两者继续保持原有运行方式。本阶段明确不迁移 Scrape，因此其后台任务监控行为没有变化。

迁移后的 Settings 页面不持有 interval 或 timeout。

## 8. 测试结果

### JavaScript 语法

以下文件全部通过：

- `webapp/services/api-client.js`
- `webapp/core/page-resources.js`
- `webapp/core/page-registry.js`
- `webapp/pages/settings.js`
- `webapp/app.js`
- `tests/test_phase3_1_frontend_foundation.js`

### Phase 3.1 专项测试

全部通过：

- GET、POST、PATCH 请求行为。
- Abort signal 传递。
- 页面生命周期切换顺序。
- Settings 同页重复进入。
- Settings 离开后再次进入。
- 重复监听防护。
- 页面资源自动释放。
- HTML 脚本依赖顺序与文件存在性。
- Scrape 和任务轮询保持原行为。

### 现有前端回归

全部通过：

- 达人分析、达人详情和趋势页面。
- 邮件内容安全渲染。

### Python 全量回归

32/32 通过，未发现后端回归。

## 9. 当前边界

- 目前只有 Settings 使用完整页面资源生命周期。
- 旧页面仍在应用启动时全局绑定原有事件。
- `app.js` 仍然较大，其他页面拆分留到后续阶段。
- 未开发 Product、Campaign 或 Agency 页面。
- 本阶段未构建 EXE。

## 10. Phase 4 HTML 页面模块化待办

本阶段有意不拆分 HTML。Phase 3 期间继续保留单文件 `index.html`，避免在 JavaScript 生命周期和服务层尚未稳定时改变 pywebview 静态资源加载方式。

进入 Phase 4 前，应先确认目标页面均已具备独立的 `load`、`bind`、`unbind`。之后再评估 HTML section 的安全模块化方案，不引入前端框架或构建工具。
