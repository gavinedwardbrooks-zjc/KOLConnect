# Google Sheets 数据同步设置

KOLConnect 通过 Google Sheets API 手动写入用户指定的现有 Spreadsheet。SQLite 始终是业务数据权威；Google Sheets 只是单向只读副本，绝不会从 Google 回写。

## Google Cloud 配置

1. 在 Google Cloud Console 创建或选择项目，并启用 Google Sheets API。
2. 配置 OAuth consent screen。
3. 创建类型为 Desktop app 的 OAuth 2.0 Client。
4. 在 KOLConnect 设置页填写 `OAuth Client ID`、`OAuth Client Secret` 和目标 `Spreadsheet URL` 或 `Spreadsheet ID`。
5. 保存后点击“连接 Google”，在系统浏览器完成授权。

KOLConnect 仅请求：

```text
https://www.googleapis.com/auth/spreadsheets
```

不请求 Google Drive scope，不提供 Drive 浏览、Google Sheets 导入、双向同步或计划任务。

## Spreadsheet 合同

目标 Spreadsheet 必须已存在，并允许当前 Google 账号编辑。Settings 中的“同步数据到 Google Sheets”只管理以下 worksheet 的 `A:AZ` 范围：

- `KOLConnect Creators`
- `KOLConnect Creator Accounts`

Campaign 详情页的报告导出仍独立管理：

- `Campaign Summary`
- `Publications`
- `Performance History`

缺失 worksheet 会自动创建。若同名 worksheet 已包含非 KOLConnect 内容，操作会以 `WORKSHEET_NAME_CONFLICT` 失败，不会清除用户内容。重复同步生成确定性副本，不会写回 SQLite；不相关 worksheet 不会被读取、清空或修改。

## 本地凭据

- OAuth Client 配置保存在 `%APPDATA%\KOLConnect\settings.json`，Settings UI 会遮罩 `client_secret`。
- OAuth token 单独保存在 `%APPDATA%\KOLConnect\google_sheets_token.json`，不会返回前端或写入日志。
- 当前 token-at-rest 依赖操作系统用户目录访问控制，并非应用层加密。请保护 Windows 用户账号和本地配置目录。

断开连接会删除本地 OAuth token。应用未配置 Google 或离线时，Creator/Campaign、M8.4 tracking 与 M8.5 analytics 仍可正常使用。
