# KOLConnect

KOLConnect 是一个本地桌面工作台，用于管理海外达人 Creator、Campaign 协作、内容发布及相关数据。

## 当前支持的能力

- **Creator Library**：支持搜索、筛选、归档/恢复、永久删除、Agency 关系、导入，以及按所选 达人导出 Excel。
- **Creator / CreatorAccount 多账号模型**：一个 达人可拥有多个平台账号 （比如：达人A 同时有YouTube tiktok Instagram 账号）。
- **Campaign 管理**：支持产品、CampaignCreator 协作记录、执行账号选择、互动/表现数据及风险检查。
- **邮箱管理**：支持除outlook邮箱外、gmail 网易邮箱 qq邮箱等邮箱，可以读取收件箱内容，同步达人邮件 （注：暂不支持发邮件 ）
- **Feishu 集成**：可选 Feishu Bitable 同步，以及可选的 Feishu Chat Assistant。
- **浏览器采集**：支持 Instagram 公开主页/相关 API 采集和 YouTube Shorts 指标；TikTok 提供页面分析工具，但被动网络采集不是当前生产功能。（之后会更新tiktok采集功能）

## 存储与运行时

KOLConnect 是本地应用，**SQLite 是当前应用数据权威（application authority）**：

~~~text
%APPDATA%\KOLConnect\data\kolconnect.db
%APPDATA%\KOLConnect\storage_authority.json
~~~

当前 SQLite schema version 为 **3**。`storage_authority.json` 记录活动数据权威与预期 schema，应用会在启动时验证。

`Creator_Library.xlsx` 是历史导入/兼容性文件，不再是当前权威数据库。KOLConnect 不提供整库 SQLite 到 Excel 的导出；Creator Library 的所选 Creator Excel 导出是独立且受限的导出功能。

Windows 应用通过仅限 localhost 的服务（`127.0.0.1`）和原生 JavaScript 前端运行。默认桌面壳使用 `pywebview`，`Browser Mode` 是本地替代模式。用户设置、日志、任务数据与存储均位于 `%APPDATA%\KOLConnect`，不会写入 release 文件夹。

## Creator 与 CreatorAccount 模型

**Creator** 是规范化的个人或业务实体；**CreatorAccount** 是归属于该 Creator 的单个、平台专属账号。二者为一对多关系：一个 Creator 可以拥有 TikTok、Instagram、YouTube 或其他已支持平台上的多个账号。

Creator 导出遵循当前 Creator 级别合同：每个规范化 Creator 一行，并以 Creator 名称作为导出名称。它不是数据库备份，也不是按账号导出的原始数据转储。

## Campaign 与内容发布模型

Campaign 计划和实际发布证据被明确区分：

- **Planned** 协作数据记录执行账号与计划发布日期。
- **Actual** 发布数据记录公开 URL、实际发布账号、实际发布时间，以及可用时的观察时间戳。

一个 `CampaignCreator` 可以有多条实际发布记录。KOLConnect 不会将计划日期和实际日期折叠为一个含义不明确的 `publish date`。

## 报价与成本

金额记录使用 ISO 风格代码保留明确的币种身份。结构化报价包含 `unit amount`、正数 `quantity` 与 `pricing unit`；总 `creator_quote` 为 `unit amount × quantity`。`cost` 为已确认或应支付的合作总成本。历史的仅总额 quote/cost 记录仍然有效。

系统可以存储多种币种，但混合币种金额绝不会被静默相加为单一总额。KOLConnect 当前不提供 FX 换算、实时或历史汇率，也不提供会计账本。

## Feishu

Feishu 使用 **Settings** 中的一套本地配置。Bitable 同步是明确的 KOLConnect 到 Feishu 工作流：Validate、Dry Run，再执行确认后的 Full Sync。Feishu Chat 为可选功能，默认关闭；它使用官方 `lark-oapi` long connection，通过 KOLConnect Assistant 的允许工具集处理消息。Chat 不具备对 workbook、filesystem、SQL 或 Bitable 的直接访问权限。

当前 Chat 事件通道不需要 public callback 或 webhook URL。OpenClaw 不是当前运行时依赖，运行 KOLConnect 不需要它。关于配置、事件、权限与安全细节，请参阅 [Feishu setup](docs/feishu_setup.md)。

## 邮箱

当前支持的邮箱认证合同为：服务商允许时，通过密码或 app-password 使用标准 IMAP/SMTP。`Microsoft Outlook / Microsoft 365 OAuth2` 不属于官方支持范围。未来 Microsoft OAuth2 集成属于新功能，不是当前的兼容性承诺。

## Chrome 扩展

在本地 KOLConnect 应用运行时，可通过 Chrome 的 **Load unpacked** 流程加载仓库中的 `chrome_extension/` 目录。采集能力按平台和页面状态严格限定：

- Instagram 公开主页及相关 API 采集。
- YouTube Shorts 指标支持。
- TikTok 页面分析工具。

历史 TikTok 被动网络导入管线仅作为实验性参考，未接入生产扩展。`TikTok Passive Capture V2` 不是当前生产功能；请参阅独立的 Post-M8 提案：[TikTok Passive Capture V2](docs/post_m8_tiktok_passive_capture_v2.md)。

## 开发与测试

仓库包含 Python 后端、原生 JavaScript Web 前端及 Chrome 扩展源码。

权威 Python 全量测试命令为：

~~~powershell
python scripts/run_python_tests.py --verbosity 1
~~~

该命令创建仓库测试沙箱，并隔离生产 `APPDATA`、运行时目录、临时目录、SQLite 与 workbook 路径。除非已在该沙箱内运行，否则不要将原始 `python -m unittest discover` 视为权威测试命令。

其他当前检查命令：

~~~powershell
node tests/run_extension_tests.js
node tests/run_extension_tests.js --syntax
python -m compileall app
git diff --check
~~~

## Windows 发布

Windows 的规范发布格式为 **ONEDIR + ZIP**。请解压完整的版本目录并运行其中的 EXE，不要将其与相邻的 `_internal` 目录分离。

使用以下命令构建发布包：

~~~powershell
powershell -ExecutionPolicy Bypass -File .\packaging\build_release.ps1
~~~

构建会生成 `release/KOLConnect_v1.0.0/` 和 `release/KOLConnect_v1.0.0.zip`，验证固定的 SQLite runtime，并检查 ZIP 仅包含一个版本化顶层目录。

## 当前限制与 Post-M8 工作

- `TikTok Passive Capture V2` 尚未实现。
- Microsoft OAuth2 邮箱支持尚未实现。
- FX 换算与会计功能尚未实现。
- OpenClaw 部署不是当前产品要求。

## 许可证

KOLConnect 使用 [MIT License](LICENSE) 授权。
