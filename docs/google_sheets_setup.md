# Google Sheets 配置指南

本指南帮助你把 KOLConnect 中的达人和达人账号复制到指定的 Google Spreadsheet。

> 同步方向只有一个：KOLConnect → Google Sheets。在 Google Sheets 中修改数据，不会自动回写 KOLConnect。

[返回外部服务配置总指南](EXTERNAL_SYNC_SETUP_GUIDE_ZH.md)

## 你需要准备什么

- 一个 Google 账号
- 一个 Google Cloud 项目
- 一个普通 Google Spreadsheet
- KOLConnect 的“设置” → “集成”页面

KOLConnect 使用 Google 官方授权页面连接你的账号。当前实现不使用 API Key 或 Service Account（服务账号）。

## 一、创建或选择 Google Cloud 项目

1. 打开 [Google Cloud Console](https://console.cloud.google.com/)。
2. 在页面顶部选择已有项目，或创建一个新项目。
3. 确认后续所有操作都在同一个项目中完成。

## 二、启用 Google Sheets API

1. 在 Google Cloud Console 打开“API 和服务”。
2. 进入“库”或“API Library”。
3. 搜索 **Google Sheets API**。
4. 打开结果并点击“启用”。

不需要启用 Google Drive API。

## 三、配置 Google 授权页面

Google Cloud 的界面名称可能显示为“Google Auth Platform”或“OAuth 同意屏幕”。

1. 打开“Google Auth Platform”。
2. 按提示填写应用名称和联系邮箱。
3. 选择使用范围：
   - 仅公司 Google Workspace 成员使用时，可选择“内部”。
   - 个人 Gmail 或公司外账号使用时，选择“外部”。
4. 如果应用处于“测试”状态，把实际用于同步的 Google 账号加入“测试用户”。
5. 保存配置。

测试模式只允许已加入测试用户列表的账号授权，而且授权可能需要定期重新进行。详情可参考 [Google 的应用受众说明](https://support.google.com/cloud/answer/15549945?hl=zh-Hans)。

## 四、创建桌面 OAuth 客户端

OAuth 可以理解为“让你在 Google 页面确认 KOLConnect 可以访问指定表格”的授权方式。

1. 在 Google Auth Platform 中打开“客户端”或“Clients”。
2. 点击“创建客户端”。
3. 应用类型选择 **桌面应用（Desktop app）**。
4. 输入一个容易识别的名称，例如 `KOLConnect Desktop`。
5. 创建后复制：
   - `OAuth Client ID`
   - `OAuth Client Secret`

不要创建 Web 应用客户端、Service Account 或 API Key。Google 的官方步骤可参考 [Google Sheets Python 快速入门中的桌面授权部分](https://developers.google.com/workspace/sheets/api/quickstart/python)。

## 五、准备 Spreadsheet

1. 使用之后要授权的 Google 账号创建一个普通 Google Spreadsheet。
2. 确认该账号对 Spreadsheet 有编辑权限。
3. 复制完整的 Spreadsheet 地址。

地址通常类似：

```text
https://docs.google.com/spreadsheets/d/1AbCdEfGhIjKlMnOpQrStUvWxYz/edit
```

`/d/` 与 `/edit` 之间的内容是 Spreadsheet ID。KOLConnect 的“Spreadsheet URL 或 ID”字段既可以填写完整地址，也可以只填写 ID。

KOLConnect 不会通过 Google Drive 帮你浏览或选择文件，因此请先在浏览器中创建并打开目标 Spreadsheet。

## 六、在 KOLConnect 中连接 Google

进入“设置” → “集成” → “Google Sheets 数据同步”。

填写：

| KOLConnect 字段 | 填写内容 |
| --- | --- |
| `OAuth Client ID` | 桌面 OAuth 客户端的 Client ID |
| `OAuth Client Secret` | 同一个客户端的 Client Secret |
| `Spreadsheet URL 或 ID` | 目标 Spreadsheet 的完整地址或 ID |

然后按顺序操作：

1. 点击“保存配置”。
2. 点击“连接 Google”。
3. 系统浏览器会打开 Google 登录和授权页面。
4. 选择对目标 Spreadsheet 有编辑权限的账号。
5. 确认授权。
6. 回到 KOLConnect，确认连接状态显示“已连接”。
7. 点击“同步数据到 Google Sheets”。

“断开连接”只会移除本机保存的 Google 授权，不会删除 Spreadsheet 或其中的数据。

## 七、KOLConnect 会管理哪些工作表

设置页同步会创建或更新：

- `KOLConnect Creators`
- `KOLConnect Creator Accounts`

如果工作表不存在，KOLConnect 会自动创建。如果同名工作表已经包含普通用户数据，KOLConnect 会停止并显示 `WORKSHEET_NAME_CONFLICT`，不会直接覆盖。

不要把无关数据手工放入这两个由 KOLConnect 管理的工作表。其他工作表不会被设置页的达人同步删除。

Campaign 报告和邮件跟进也可以使用同一份 Google 配置，但它们由各自页面单独触发，并使用独立的工作表。

## 八、Google 会要求什么权限

KOLConnect 只请求 Google Sheets 读写权限：

```text
https://www.googleapis.com/auth/spreadsheets
```

当前不会请求：

- Google Drive 权限
- Gmail 权限
- Drive 文件浏览权限
- Service Account 权限

因为没有 Drive 浏览权限，KOLConnect 只能访问你明确填写、且授权账号有权编辑的 Spreadsheet。

## 九、常见问题

| 现象或错误 | 常见原因 | 建议 |
| --- | --- | --- |
| Google 提示应用被阻止或未验证 | 应用仍处于测试状态，当前账号不是测试用户 | 在 Google Auth Platform 的“受众”中加入该账号 |
| 浏览器授权未完成 | 默认浏览器被阻止、页面被关闭或本机回调未完成 | 保持 KOLConnect 运行，重新点击“连接 Google”并完成整个流程 |
| `AUTH_REQUIRED` | 尚未授权、授权已失效或测试授权已过期 | 重新点击“连接 Google” |
| Spreadsheet 找不到 | URL/ID 错误，或授权账号没有编辑权限 | 用同一 Google 账号打开该表，检查地址和共享权限 |
| `REMOTE_PERMISSION_DENIED` | 授权账号无权编辑，或 Sheets API 未启用 | 检查账号、Spreadsheet 共享设置和 API 状态 |
| `WORKSHEET_NAME_CONFLICT` | 同名工作表已有非 KOLConnect 数据 | 重命名原工作表，或改用新的空白 Spreadsheet |
| 浏览器登录了错误账号 | 多个 Google 账号同时登录 | 重新连接，并在授权页选择有编辑权限的账号 |

请勿在截图、Issue 或聊天中公开 OAuth Client Secret、授权令牌或私人 Spreadsheet 内容。
