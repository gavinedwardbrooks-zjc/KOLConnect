# KOLConnect

KOLConnect 是一款面向海外达人营销团队的本地桌面工作台，帮助你集中管理达人资料、Campaign、邮件跟进、Agency 关系和跨平台公开数据。

数据默认保存在你的电脑上。只有在你主动配置飞书、Google Sheets 或邮箱等外部服务后，KOLConnect 才会连接对应服务。

## 主要功能

### 达人管理

- 集中管理达人及其 TikTok、Instagram、YouTube 账号。
- 搜索、筛选、归档、恢复和合并重复达人。
- 保存公开邮箱、账号数据、合作记录和备注。
- 按需导出所选达人数据。

### Campaign 管理

- 创建 Campaign 并添加合作达人。
- 记录报价、币种、计划发布日期和实际发布内容。
- 跟踪 Brief、草稿、待发布、已完成等合作阶段。
- 汇总内容表现、成本和需要处理的事项。

### 邮件与跟进

- 通过标准 IMAP 同步收件箱和已发送邮件。
- 将邮件与已有达人账号进行匹配。
- 查看待回复、等待达人回复、稍后处理和停止跟进等状态。
- 邮件事实保存在本地，方便持续跟进。

### Agency 管理

- 管理 Agency、联系人和旗下达人。
- 维护机构资料、联系方式、负责人和合作状态。
- 将达人、Agency 与联系人关系集中到同一工作流中。

### 飞书集成

- 将达人和达人账号同步到飞书多维表格。
- 同步前可先验证配置并预览变更。
- 可选启用飞书聊天助手。

首次配置请阅读 [飞书设置指南](docs/feishu_setup.md)。

### 浏览器采集与 Chrome 扩展

- 在 Instagram、YouTube 和 TikTok 达人页面查看公开资料并添加或更新账号。
- 支持 Instagram Reels 和 YouTube Shorts 的可用公开指标。
- 可将新平台账号明确关联到已有 Creator，减少重复记录。

Chrome 扩展需要与正在运行的 KOLConnect 桌面应用配合使用。

## 下载与安装

请前往 [KOLConnect v2.0.0 Releases](https://github.com/gavinedwardbrooks-zjc/KOLConnect/releases/tag/v2.0.0) 下载与你设备匹配的文件。

### Windows x64

下载：[`KOLConnect_v2.0.0_Windows_x64.zip`](https://github.com/gavinedwardbrooks-zjc/KOLConnect/releases/download/v2.0.0/KOLConnect_v2.0.0_Windows_x64.zip)

1. 完整解压 ZIP，不要直接在压缩包内运行。
2. 保持解压后的所有文件和文件夹在一起。
3. 双击 `KOLConnect_v2.0.0.exe` 启动。

不要只移动 EXE。它需要与同目录中的运行文件保持在一起。

### macOS Apple Silicon

适用于 M1、M2、M3、M4 等 Apple Silicon Mac，系统要求为 **macOS 14 或更高版本**。

下载：[`KOLConnect_v2.0.0_macOS_arm64.dmg`](https://github.com/gavinedwardbrooks-zjc/KOLConnect/releases/download/v2.0.0/KOLConnect_v2.0.0_macOS_arm64.dmg)

打开 DMG，将 `KOLConnect.app` 拖入 `/Applications` 后再启动。

### macOS Intel

适用于 Intel 处理器 Mac，系统要求为 **macOS 14 或更高版本**。

下载：[`KOLConnect_v2.0.0_macOS_x64.dmg`](https://github.com/gavinedwardbrooks-zjc/KOLConnect/releases/download/v2.0.0/KOLConnect_v2.0.0_macOS_x64.dmg)

打开 DMG，将 `KOLConnect.app` 拖入 `/Applications` 后再启动。

### macOS 首次启动

当前 macOS 应用使用 ad-hoc 签名，尚未经过 Apple 公证。Gatekeeper 可能会阻止首次启动。

先将应用拖入 `/Applications`，确认文件来自本项目的正式 Release，然后打开“终端”并运行：

```bash
xattr -dr com.apple.quarantine /Applications/KOLConnect.app
open /Applications/KOLConnect.app
```

第一条命令用于移除下载文件的隔离标记，正常情况下不会显示输出；第二条命令用于启动应用。未来完成 Developer ID 签名和 Apple 公证后，将不再需要此操作。

### Chrome 扩展

下载：[`KOLConnect_Chrome_Extension_v2.0.0.zip`](https://github.com/gavinedwardbrooks-zjc/KOLConnect/releases/download/v2.0.0/KOLConnect_Chrome_Extension_v2.0.0.zip)

1. 解压 ZIP。
2. 在 Chrome 地址栏打开 `chrome://extensions/`。
3. 开启“开发者模式”。
4. 选择“加载已解压的扩展程序”，并选择解压后的扩展目录。
5. 先启动 KOLConnect 桌面应用，再打开支持的达人主页。

## 快速开始

1. 启动 KOLConnect。
2. 在“达人库”中手动添加达人，或使用任务导入公开主页链接。
3. 创建 Campaign，并将达人加入合作流程。
4. 如需页面采集，安装 Chrome 扩展并保持桌面应用运行。
5. 如需邮箱、飞书或 Google Sheets，同步前先在“设置”中完成对应配置。

## 开源与自行开发

KOLConnect 是开源项目，源代码就在这个 GitHub 仓库中。你可以下载、Fork 或 Clone 项目，并使用能够读取本地项目文件夹的 AI 编程助手，在自己的电脑上继续开发。

项目使用 MIT License。修改和运行开发版本产生的结果由使用者自行负责；开始前请先备份本地数据，并将正式安装包与开发版本分开保存。

第一次接触源码，请阅读 [用 AI 继续开发 KOLConnect](docs/AI_LOCAL_DEVELOPMENT_GUIDE_ZH.md)。

## 数据与隐私

- KOLConnect 采用本地优先设计，主要业务数据保存在你的电脑上。
- 邮箱密码或授权码使用操作系统提供的安全凭据存储能力。
- 飞书、Google Sheets 和邮箱同步均为可选功能，未配置时不会连接这些服务。
- 请勿在 Issue、截图或聊天中公开密码、授权码、Token、Cookie 或其他敏感信息。

## 当前限制

- TikTok 页面分析可用，但 `TikTok Passive Capture V2` 尚不是正式生产功能，部分近期内容指标可能无法获取。
- 不支持 Outlook / Microsoft 365 邮箱，后续也不计划支持。
- 暂不提供自动实时汇率；汇率需要手动维护。
- 邮箱功能用于同步和跟进，不会从 KOLConnect 直接发送邮件。
- macOS 应用尚未经过 Apple 公证，首次启动可能需要按上方说明解除隔离。
- 平台公开页面、登录状态或访问限制可能导致部分资料和内容指标缺失；KOLConnect 不会猜测或伪造缺失数据。

## 获取帮助

- 外部服务配置总指南：[docs/EXTERNAL_SYNC_SETUP_GUIDE_ZH.md](docs/EXTERNAL_SYNC_SETUP_GUIDE_ZH.md)
- 飞书设置：[docs/feishu_setup.md](docs/feishu_setup.md)
- 邮箱设置：[docs/mail_setup.md](docs/mail_setup.md)
- Google Sheets 设置：[docs/google_sheets_setup.md](docs/google_sheets_setup.md)
- 用 AI 继续开发 KOLConnect：[docs/AI_LOCAL_DEVELOPMENT_GUIDE_ZH.md](docs/AI_LOCAL_DEVELOPMENT_GUIDE_ZH.md)
- 问题反馈：[GitHub Issues](https://github.com/gavinedwardbrooks-zjc/KOLConnect/issues)

提交问题时，请描述操作步骤和错误提示，但不要附带密码、Token、Cookie 或个人数据。

## 许可证

KOLConnect 使用 [MIT License](LICENSE) 授权。
