# KOLConnect 外部服务配置指南

KOLConnect 可以独立在本机使用。飞书、邮箱和 Google Sheets 都是可选功能，只在你主动配置并操作时连接外部服务。

## 飞书

将达人和达人账号同步到飞书多维表格，也可以选择启用飞书 AI 助手。配置指南提供可直接复制的飞书 AI 提示词，帮助你创建所需数据表。

[打开飞书配置指南](feishu_setup.md)

## 邮箱

连接支持标准 IMAP 的邮箱，同步收件箱和可用的已发送邮件，并查看达人邮件跟进状态。KOLConnect 当前不会直接发送邮件。

[打开邮箱配置指南](mail_setup.md)

## Google Sheets

将达人和达人账号单向复制到指定 Google Spreadsheet。Google Sheets 中的修改不会自动回写 KOLConnect。

[打开 Google Sheets 配置指南](google_sheets_setup.md)

## 建议配置顺序

1. 先在不连接外部服务的情况下熟悉 KOLConnect。
2. 需要邮件跟进时，再配置邮箱。
3. 需要团队在飞书查看数据时，再配置飞书。
4. 需要 Google 表格副本时，再配置 Google Sheets。

每项集成都可以单独使用，不需要一次全部配置。首次连接建议使用少量测试数据，并先完成各指南中的验证或预检查步骤。

## 安全提醒

- 不要在截图、聊天、Issue 或公开文档中分享密码、授权码、App Secret 或 OAuth Client Secret。
- 只开通指南中列出的最小权限。
- 外部同步前先确认目标表格和账号，避免把业务数据写入错误位置。
- 遇到错误时，记录错误码和操作步骤，不要公开完整日志中的个人数据。
