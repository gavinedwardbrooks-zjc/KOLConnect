# KOLConnect 2.0 外部同步首次配置指南

本文面向第一次配置飞书多维表格或 Google Sheets 的 KOLConnect 2.0 用户。文中的字段、按钮、错误码和同步边界均来自当前代码与测试。

## 1. 开始前先理解一件事

KOLConnect 本机 SQLite 是业务数据权威。飞书多维表格和 Google Sheets 都是手动触发的 replica/export 目标：

- KOLConnect 可以把本地数据创建或更新到外部表格。
- 飞书或 Google 中的人工修改不会反向覆盖 KOLConnect。
- 外部同步失败不会改变 SQLite 中的 Creator、CreatorAccount 或 Campaign。
- 缺失值不等于零；同步不会为了补齐表格而猜测数据。

完整的数据权威与实体关系见 [KOLConnect 架构说明](../ARCHITECTURE.md)。如果要开发新的同步 provider，请参阅 [KOLConnect 二次开发指南](../CUSTOMIZATION_GUIDE.md)。

## 2. 飞书多维表格：从零配置

### 2.1 准备飞书应用

1. 打开飞书开放平台并创建一个企业自建应用。
2. 记录应用的 `App ID` 和 `App Secret`。
3. 创建或选择一个飞书多维表格 Base。
4. 确保该应用能够访问目标 Base 和其中的目标数据表。
5. 为应用开通多维表格读取和写入能力并发布可用版本。

当前仓库可以确认同步会：

- 获取 tenant access token。
- 读取多维表格字段和记录。
- 批量创建 Creator/CreatorAccount 记录。
- 批量更新受管理字段和 Creator/CreatorAccount 关系。

### 2.1.1 飞书最小权限要求

常规 Creator/CreatorAccount 同步推荐只开通 `bitable:app`（查看、评论、编辑和管理多维表格），权限身份为**应用身份**。KOLConnect 使用 App ID/App Secret 获取 `tenant_access_token`，飞书数据同步不需要用户 OAuth。

- Validate 读取 Creator 与 CreatorAccount 的字段元数据；Dry Run 还会读取两张表的记录。这两步可使用 `bitable:app:readonly` 或 `bitable:app`。
- Full Sync 会批量创建、更新记录并通过记录更新维护关系，因此必须使用 `bitable:app`。
- 当前 Full Sync 不删除远端记录，不创建、删除或更新表/字段，也不把飞书数据反向写入 SQLite。

`bitable:app` 是 API 权限层，不会自动授予某个 Base 的数据访问权。还必须把应用/机器人加入目标 Base，确保 Creator 与 CreatorAccount 两张表都可访问；如果 Base 启用了高级权限，Validate/Dry Run 至少需要读取权限，Full Sync 需要应用身份对两张表的读写权限。只有只读数据权限时，Validate/Dry Run 可能通过，但 Full Sync 会因写权限不足而失败。

新增或修改 API 权限后，需要创建并发布新的应用版本；租户要求时还需完成管理员审批。仅调整 Base 协作者或高级权限时通常不需要重新发布应用版本。

当前同步不要求 Calendar、Contacts、Docs、Drive、IM、Wiki、Search、cardkit、`offline_access` 或应用自管理权限，也不要求记录删除、表创建/删除/更新、字段创建/删除/更新或视图写入权限。飞书 Chat/AI Assistant 的机器人、消息与事件权限属于独立功能，不要混入 Feishu Sync 的最小权限集合。更窄的 `base:*` 权限可作为高级替代配置，但不是 KOLConnect 推荐的常规设置。

### 2.2 准备多维表格

常规「飞书数据同步」只要求两个数据表：

1. Creator 表，对应设置中的「达人 Table ID」。
2. CreatorAccount 表，对应设置中的「达人账号 Table ID」。

设置页提供「Agency 联系人 Table ID」，对应配置键 `feishu.contact_table_id`。它属于独立的 Agency 联系人功能，是可选配置；常规 Creator/CreatorAccount Full Sync 只要求 Creator 表与 CreatorAccount 表，不使用该联系人表。

#### Creator 表字段

| 字段名 | 必需 | 兼容字段类型 | 用途 |
| --- | --- | --- | --- |
| `KOLConnect Creator ID` | 是 | 文本 | Creator 权威身份键 |
| `达人名称` | 是 | 文本 | 显示名称 |
| `国家/地区` | 是 | 文本或单选 | 地区 |
| `语言` | 是 | 文本或单选 | 语言 |
| `内容类型` | 是 | 文本或单选 | 内容分类 |
| `已归档` | 是 | 文本、单选或复选框 | 归档状态 |
| `最近同步时间` | 是 | 文本或日期时间 | 同步时间 |
| `社媒账号` | 是 | 关联记录 | 关联到 CreatorAccount 表，必须允许多条记录 |
| `Insight等级` | 否 | 文本或单选 | 可选分析信息 |
| `最后分析时间` | 否 | 文本或日期时间 | 可选分析时间 |

#### CreatorAccount 表字段

| 字段名 | 必需 | 兼容字段类型 | 用途 |
| --- | --- | --- | --- |
| `账号唯一ID` | 是 | 文本 | CreatorAccount 权威身份键 |
| `KOLConnect Creator ID` | 是 | 文本 | 所属 Creator 的稳定 ID |
| `平台` | 是 | 文本或单选 | TikTok、Instagram、YouTube 等 |
| `主页链接` | 是 | 文本或 URL | 平台主页 |
| `粉丝数` | 是 | 文本或数字 | 粉丝数；缺失仍保持缺失 |
| `最近同步时间` | 是 | 文本或日期时间 | 同步时间 |
| `达人` | 是 | 关联记录 | 关联到 Creator 表 |
| `平均播放量` | 否 | 文本或数字 | 可选表现字段 |
| `最后分析时间` | 否 | 文本或日期时间 | 可选分析时间 |

关系字段支持当前双向关联类型，也兼容符合目标表约束的旧关系类型。Creator 表的「社媒账号」必须指向已配置的 CreatorAccount 表并允许多选；CreatorAccount 表的「达人」必须指向已配置的 Creator 表。

不要手工复用或伪造 `KOLConnect Creator ID`、`账号唯一ID`。重复身份会在 Dry Run 中产生冲突并阻止同步。

### 2.3 获取 App ID / App Secret

1. 在飞书开放平台打开刚创建的应用。
2. 进入应用凭证页面。
3. 复制 `App ID`。
4. 安全查看并复制 `App Secret`。

`App ID` 是应用标识；`App Secret` 是应用秘密。不要把 App Secret 发到聊天、Issue、截图或代码仓库。

### 2.4 获取 Bitable/App Token

飞书不同界面可能使用「App Token」「Bitable Token」或「Base Token」描述同一类 Base 标识。KOLConnect 设置字段名称是「App Token」，配置键为 `app_token`。

请按飞书当前帮助文档，从目标多维表格 Base 的信息或 URL 中确认 App Token，并只填写 token 本身。当前 KOLConnect 不解析完整飞书 URL。

### 2.5 获取各 Table ID

分别打开 Creator 表和 CreatorAccount 表，按飞书当前界面或开发文档取得各自的 Table ID，然后对应填写：

- Creator 表 ID →「达人 Table ID」
- CreatorAccount 表 ID →「达人账号 Table ID」
- 可选 Agency 联系人表 ID →「Agency 联系人 Table ID」

Table ID 标识 Base 内的一张表，不是 App Token，也不是表名。当前 KOLConnect 需要原始 Table ID，不解析完整 URL。

### 2.6 在 KOLConnect 中填写

1. 打开 KOLConnect。
2. 进入「设置」。
3. 切换到「集成」。
4. 找到「飞书配置（同一个 App）」。
5. 填写以下字段：

| UI 字段 | 配置键 | Creator/Account 同步是否必填 |
| --- | --- | --- |
| `App ID` | `feishu.app_id` | 是 |
| `App Secret` | `feishu.app_secret` | 是 |
| `App Token` | `feishu.app_token` | 是 |
| `达人 Table ID` | `feishu.creator_table_id` | 是 |
| `达人账号 Table ID` | `feishu.account_table_id` | 是 |
| `Agency 联系人 Table ID` | `feishu.contact_table_id` | 否，独立功能使用 |

6. 点击「保存飞书配置」。

重新打开设置时，已保存的 App Secret 和 App Token 会显示为掩码。若不想修改 App Secret，请保持秘密输入框为空；不要把掩码当作新的 secret 粘贴回去。

### 2.7 验证连接

在同一「集成」页面找到「飞书数据同步」，点击「验证连接」。

验证会：

1. 使用 App ID/App Secret 获取 tenant access token。
2. 读取 Creator 与 CreatorAccount 表的字段定义。
3. 校验必需字段、兼容字段类型和关系目标。
4. 返回 `missing_fields`、`incompatible_fields`、warnings 或安全错误码。

验证不会创建、更新或删除记录。验证通过时仍可能显示 `WRITE_PERMISSION_NOT_TESTED_WITHOUT_MUTATION`，因为只读验证无法证明写权限。

### 2.8 预检查 / Dry Run

连接与字段合同通过后，点击「预检查 / Dry Run」。该步骤会读取本地 SQLite 和两个远端表，构建计划，但不会写入飞书。

当前 UI 显示：

- 「本地达人」：当前本地 Creator 总数。
- 「飞书达人」：远端 Creator 表记录总数。
- 「待新增」：将创建的 Creator 数量。
- 「待更新」：将更新的 Creator 数量。
- 「冲突」：Creator 身份冲突数；身份重复或映射歧义会 fail closed。
- 「未管理记录」：缺少 KOLConnect 身份键、因此不会被普通同步接管的远端记录。
- 「关系待建立」：本地存在、远端尚缺的 Creator/Account 关系。
- 「关系待更新」：需要重写关系字段的记录数。
- 「关系待移除」：将从受管理关系字段移除的过期 KOLConnect 关系；这不是删除远端记录。
- 「关系冲突」：无法安全建立的关系数。

服务响应还包含账号待新增/待更新/不变数量和 payload safety 摘要；当前设置页没有把所有账号计数单独显示成卡片。

#### 如何理解 Dry Run

- 「待新增」表示远端没有对应稳定 ID 的本地 Creator。
- 「待更新」只包含可安全比较且本地有有效值的受管理字段。
- 本地缺失值在更新时会被省略，远端已有非空值会保留。
- 「冲突」不是“尽量匹配”；同步会停止，要求先修正重复 ID 或歧义。
- 「未管理记录」会保留，不会因 Full Sync 被删除。
- 重复运行在没有新变化时应收敛为不变项。

### 2.9 第一次同步

只有验证和 Dry Run 都符合预期时：

1. 再次核对 Creator/CreatorAccount 表 ID。
2. 检查冲突、未管理记录和关系变更数量。
3. 点击「同步到飞书」。
4. 阅读确认提示后明确继续。

Full Sync 会重新构建计划，而不是直接执行旧 Dry Run：

- 创建缺失的受管理 Creator/CreatorAccount。
- 更新稳定 ID 精确匹配记录的受管理字段。
- 同步 Creator 与 CreatorAccount 关系。
- 不读取飞书业务修改回写 SQLite。
- 不删除飞书记录。
- 保留未管理记录和不属于 KOLConnect 管理范围的关系。
- 某批次失败后停止后续批次，并返回 partial/failed 状态；修正后可重新同步。

普通 Full Sync 不执行远端 record delete。代码中存在独立、显式确认的删除协调生命周期，但它不是本指南的首次同步流程。

### 2.10 常见错误

| 错误码/状态 | 含义 | 安全处理 |
| --- | --- | --- |
| `CONFIGURATION_ERROR` | App ID、Secret、App Token 或两个核心 Table ID 缺失 | 返回设置页逐项核对并保存 |
| `AUTHENTICATION_FAILED` | App ID/Secret 无效或应用不可用 | 重新复制凭据，检查应用状态 |
| `PERMISSION_DENIED` | 应用无权读取或写入目标 Base/表 | 检查应用权限、Base 授权和应用发布状态 |
| `NOT_FOUND` | App Token/Table ID 错误或目标不可访问 | 重新核对 Base 与 Table ID |
| `FEISHU_SCHEMA_INVALID` | 缺少字段、类型不兼容或关系目标错误 | 按 UI 的 missing/incompatible 列表修正表结构 |
| `IDENTITY_CONFLICT` | 本地或远端稳定 ID 重复 | 不要继续同步；先消除重复身份 |
| `AMBIGUOUS_LEGACY_MAPPING` | 旧关系无法唯一映射 | 人工核对旧记录，避免猜测关联 |
| `REMOTE_CONFLICT` | 飞书拒绝并发或冲突写入 | 刷新远端状态后重新 Dry Run |
| `RATE_LIMITED` | 飞书限流 | 等待后重试，不增加并发 |
| `TRANSIENT_NETWORK_ERROR` / `TRANSIENT_REMOTE_ERROR` | 网络或飞书服务暂时不可用 | 保持本地数据不动，稍后重新验证 |
| `FEISHU_SYNC_CONFIRMATION_REQUIRED` | Full Sync 没有明确确认 | 从 UI 确认后再运行 |

## 3. Google Sheets：从零配置

### 3.1 当前实现状态

Google Sheets 同步已在 KOLConnect 2.0 中实现。当前支持：

- Google Sheets 设置 UI。
- Installed/Desktop App OAuth 2.0。
- 系统浏览器授权与本机临时回调端口。
- 手工选择目标 Spreadsheet URL 或 ID。
- 手动同步 Creator/CreatorAccount 副本。
- Campaign 页面单独导出 Campaign 报告。
- Mail Follow-up 页面单独 keyed-upsert 跟进表。

不支持：

- service account。
- API key 模式。
- Google Drive 浏览或选择器。
- 从 Google Sheets 导入或反向覆盖 SQLite。
- 后台定时同步。
- 设置页 Dry Run。

### 3.2 准备 Google Cloud OAuth

1. 在 Google Cloud Console 创建或选择项目。
2. 启用 Google Sheets API。
3. 配置 OAuth consent screen。
4. 创建 OAuth 2.0 Client，应用类型选择 Desktop app。
5. 复制 OAuth Client ID 和 OAuth Client Secret。

KOLConnect 只请求：

```text
https://www.googleapis.com/auth/spreadsheets
```

它不请求 Google Drive scope。授权时 KOLConnect 会打开系统浏览器，并在本机随机端口接收 `http://localhost` 回调。

### 3.3 准备 Spreadsheet

1. 使用将完成 OAuth 授权的 Google 账号创建一个 Spreadsheet。
2. 确认该账号对 Spreadsheet 有编辑权限。
3. 从地址栏复制完整 Spreadsheet URL，或复制 `/spreadsheets/d/` 后的 Spreadsheet ID。

KOLConnect 不会自动通过 Drive 创建或选择 Spreadsheet。设置字段接受受支持的 `https://docs.google.com/spreadsheets/d/.../` URL 或原始 ID。

### 3.4 在 KOLConnect 中填写并连接

1. 打开 KOLConnect。
2. 进入「设置」→「集成」。
3. 找到「Google Sheets 数据同步」。
4. 填写：

| UI 字段 | 配置键 | 说明 |
| --- | --- | --- |
| `OAuth Client ID` | `google_sheets.client_id` | Desktop app Client ID |
| `OAuth Client Secret` | `google_sheets.client_secret` | Desktop app Client Secret |
| `Spreadsheet URL 或 ID` | `google_sheets.spreadsheet_id` | 已存在且当前账号可编辑的目标 |

5. 点击「保存配置」。
6. 点击「连接 Google」。
7. 在系统浏览器完成 Google 授权。
8. 回到 KOLConnect，确认连接状态为「已连接」。

「断开连接」会删除本机保存的 OAuth token，但不会删除 Google Spreadsheet 或其中的数据。

### 3.5 第一次同步

Google 设置页当前没有「验证连接」或 Dry Run。首次操作应使用专门准备的空白 Spreadsheet，并先确认 URL/ID 和授权账号。

点击「同步数据到 Google Sheets」后，KOLConnect 会管理：

#### `KOLConnect Creators`

`creator_id`、`name`、`country`、`language`、`content_category`、`archived_at`、`created_at`、`updated_at`

#### `KOLConnect Creator Accounts`

`account_uid`、`creator_id`、`platform`、`profile_url`、`account_name`、`followers`、`account_email`、`created_at`、`updated_at`

行为边界：

- 缺少的 worksheet 会自动创建。
- KOLConnect 管理的 worksheet 使用 marker 和稳定表头。
- 已受 KOLConnect 管理的 Creator/Account worksheet 会清空其 `A:AZ` 受管范围后写入当前完整副本。
- 若同名 worksheet 已有非 KOLConnect 内容，则以 `WORKSHEET_NAME_CONFLICT` fail closed，不清除用户数据。
- 其他 worksheet 不会被删除或改写。
- 不从 Google 读取业务修改回写 SQLite。

其他独立入口：

- Campaign Detail 可写出 `Campaign Summary`、`Publications`、`Performance History`。
- Mail Follow-up 可创建或复用 `Mail Follow-up` worksheet，并按稳定键新增或更新行，不以当前可见分页作为导出范围。

这些独立入口共享同一个 OAuth 与 Spreadsheet 配置，但不属于设置页 Creator/Account 同步按钮。

### 3.6 Google 常见错误

| 错误码/状态 | 含义 | 安全处理 |
| --- | --- | --- |
| `NOT_CONFIGURED` | Client ID、Secret 或 Spreadsheet 未完整配置 | 返回设置页保存完整配置 |
| `INVALID_SPREADSHEET` | URL/ID 格式无效或目标不存在 | 使用受支持的 Sheets URL 或原始 ID |
| `AUTH_REQUIRED` | 尚未授权、授权失效或缺少 refresh token | 点击「连接 Google」重新授权 |
| `REMOTE_PERMISSION_DENIED` | 当前 Google 账号无编辑权限或 Sheets API 拒绝访问 | 检查账号、共享权限和 API 状态 |
| `WORKSHEET_NAME_CONFLICT` | 同名 worksheet 存在非 KOLConnect 内容或表头不匹配 | 重命名现有表或改用空白 Spreadsheet；不要强行覆盖 |
| `GOOGLE_SDK_UNAVAILABLE` | 当前运行包缺少 Google OAuth/Sheets 依赖 | 使用正式完整分发包或修复开发环境依赖 |
| `NETWORK_ERROR` / `REMOTE_ERROR` | 网络或 Google API 暂时失败 | 保留 SQLite 不动，稍后重试 |
| `PARTIAL` | 部分 worksheet 写入失败 | 查看每个 worksheet 状态，修复后再次手动同步 |

Google 没有独立 Dry Run，因此不要把「连接 Google」理解为数据预检查：它只建立授权，不会计算待写入数量。

## 4. 飞书与 Google 的差异

| 项目 | 飞书多维表格 | Google Sheets |
| --- | --- | --- |
| 当前状态 | 已实现 | 已实现 |
| 认证 | App ID + App Secret 获取 tenant token | Desktop OAuth 2.0 |
| 目标定位 | App Token + 两个核心 Table ID | Spreadsheet URL 或 ID |
| 连接/schema 验证 | 有「验证连接」 | 无独立验证按钮 |
| Dry Run | 有「预检查 / Dry Run」 | 无 |
| 设置页主同步 | Creator、CreatorAccount、关系 | Creator、CreatorAccount 两个 worksheet |
| 写入方式 | 稳定 ID create/update + sparse merge | 受管 worksheet 完整副本 |
| 远端记录删除 | 普通 Full Sync 不删除 | 不删除 worksheet；会重写受管范围 |
| 远端回写 SQLite | 不支持 | 不支持 |
| 外部业务权威 | 否 | 否 |

## 5. 凭据与安全

### 5.1 当前本机存储事实

当前代码的存储行为是：

- 飞书 `app_id`、`app_secret`、`app_token` 和 Table IDs 保存在 KOLConnect 用户数据目录的 `settings.json`。
- Google `client_id`、`client_secret` 和 `spreadsheet_id` 同样保存在 `settings.json`。
- Settings API 返回前会遮罩 Feishu App Secret、App Token 和 Google Client Secret。
- Google OAuth token 单独保存在用户数据目录的 `google_sheets_token.json`；保存后会尽力将文件权限设为仅当前用户可读写。
- 当前 Feishu/Google secrets 与 Google token 不使用 KOLConnect 的 Mail DPAPI/Keychain 凭据存储，也没有应用层加密；安全性依赖操作系统用户目录权限。

因此：

1. 保护操作系统用户账号和 KOLConnect 用户数据目录。
2. 不共享 `settings.json`、其备份或 `google_sheets_token.json`。
3. 不把真实凭据放进截图、日志、Issue、聊天或测试 fixture。
4. 设备丢失或凭据疑似泄漏时，在飞书/Google 控制台撤销并轮换凭据。

### 5.2 永远不要提交

- App Secret
- OAuth Client Secret
- refresh token / access token
- service account private key 或 credentials JSON
- 敏感的生产 Spreadsheet ID、App Token、Table ID
- Cookie、浏览器 session 或 Authorization header

本文所有标识均使用字段名，没有提供真实凭据或可用 ID。

## 6. 常见问题

### 飞书验证通过，为什么仍可能无法写入？

「验证连接」只读取 token、字段和记录合同，不执行 mutation，因此无法证明写权限。看到 `WRITE_PERMISSION_NOT_TESTED_WITHOUT_MUTATION` 时，先确认开放平台权限和 Base 授权，再审阅 Dry Run，最后执行一次明确确认的 Full Sync。

### 飞书 Dry Run 为什么显示未管理记录？

这些远端记录缺少 KOLConnect 稳定身份字段，普通同步不会自动认领或删除它们。不要仅凭名称或邮箱补写身份。

### 「关系待移除」会删除达人或账号吗？

不会。它表示受管理关系字段中的旧 KOLConnect 链接将被移除；普通 Full Sync 不删除远端 record。

### Google 为什么没有 Dry Run？

当前产品没有 Google 数据预检查 API。Google 「连接」只负责 OAuth；「同步数据到 Google Sheets」会直接写入受管 worksheet。首次同步请使用空白或专门准备的 Spreadsheet。

### 可以在飞书或 Google 修改后同步回 KOLConnect 吗？

不可以。两者都不是双向业务 authority。需要修改业务数据时，请回到 KOLConnect。

### 能否只同步当前页面看到的 Mail Follow-up 行？

Mail Follow-up 的 Google 导出使用完整的当前筛选结果和 keyed-upsert，不以 20 行可见分页作为 authority。

## 7. 第一次同步安全检查清单

### 飞书

- [ ] 已确认 SQLite/KOLConnect 是业务权威。
- [ ] 如数据重要，已有可恢复的本地备份。
- [ ] App ID、App Secret 和 App Token 来自同一飞书应用/Base。
- [ ] Creator 与 CreatorAccount Table ID 对应正确。
- [ ] 「验证连接」通过。
- [ ] schema 的缺失字段和不兼容字段均已处理。
- [ ] 已审阅「预检查 / Dry Run」。
- [ ] 冲突为 0，或已理解并修复所有冲突。
- [ ] 已核对待新增、待更新、未管理记录和关系变更数量。
- [ ] 只在上述检查完成后点击「同步到飞书」并明确确认。

### Google Sheets

- [ ] 已确认 SQLite/KOLConnect 是业务权威。
- [ ] 已启用 Google Sheets API，并创建 Desktop app OAuth Client。
- [ ] 目标 Spreadsheet 已存在，授权账号有编辑权限。
- [ ] 首次同步使用空白或专门准备的 Spreadsheet。
- [ ] 已保存配置并完成「连接 Google」。
- [ ] 已理解 Google 当前没有 Dry Run，点击同步会直接写受管 worksheet。
- [ ] 已确认同名 worksheet 不包含需要保留的非 KOLConnect 内容。
- [ ] 只在上述检查完成后点击「同步数据到 Google Sheets」。
