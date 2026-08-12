# KOLConnect v0.2.3

**KOL Management & Campaign Operations Platform**

KOLConnect 是用于 KOL/Creator 管理、达人关系维护、Influencer Campaign 执行和数据分析的平台。它将达人发现、资料审核、长期维护、Campaign 协作与效果复盘连接为一套本地运营工作流。

> 当前版本为内部测试版，适合功能验收和日常试用，不属于正式稳定版本。

## Product Workflow

```text
Creator Discovery
        ↓
Data Review
        ↓
Creator Library
        ↓
Campaign Management
        ↓
Performance Analytics
```

## Features

### Creator Management

- Creator Library 达人库
- Creator 资料编辑
- 达人 Agency 归属维护
- Creator Account 账号管理
- Creator 归档与恢复
- Creator Campaign 历史查看
- Creator Snapshot、Insight 和历史趋势

### Product & Campaign Management

- Product 管理
- Campaign 创建与编辑
- Campaign 业务状态与归档生命周期
- CampaignCreator 合作关系管理
- 合作阶段跟踪
- 执行账号选择
- 报价与成本记录

### Campaign Detail

- Campaign 概览
- Product 信息
- Creator 与 Agency 归属信息
- Creator 执行账号
- 发布链接与发布时间
- 播放、点赞和评论结果
- ROI 记录与复盘信息

### Dashboard

- 活跃 Campaign 概览
- 成本统计
- ROI 分析
- Creator 表现排行
- 执行中事项
- 待联系与待复盘事项

### Supporting Workflows

- Chrome Extension 达人资料采集与导入
- 抓取任务与数据审核
- 邮件匹配
- 飞书四表同步
- Legacy Cooperation 历史合作只读查看

## Data Workflow

```text
Creator Discovery
        → Data Review
        → Creator Library
        → Campaign Collaboration
        → Analytics
```

1. 通过 Chrome Extension 或抓取任务发现 Creator。
2. 在审核流程中确认资料质量。
3. 将 Creator 保存到 Creator Library，并维护账号和 Agency 归属。
4. 创建 Product 和 Campaign，将 Creator 加入 CampaignCreator 协作关系。
5. 记录执行账号、合作阶段、成本、发布信息和表现结果。
6. 通过 Dashboard 与 Campaign Detail 查看执行进度和数据表现。

## Architecture

### Backend

- Python 本地服务
- Repository 数据访问层
- API Service Layer
- Excel-based storage
- PyInstaller Windows 打包

### Frontend

- 原生 JavaScript 模块化页面架构
- `load()` / `bind()` / `unbind()` 页面生命周期管理
- PageResources 资源释放管理
- 统一 API Client
- PyWebView compatible interface

```text
webapp/
├── core/       # 页面注册、导航和资源生命周期
├── services/   # API Client 等共享服务
└── pages/      # Product、Campaign、Dashboard、Creator Library 等页面模块
```

### Project Structure

```text
KOLConnect/
├── app/                # Python 服务、Repository、任务及同步模块
├── webapp/             # PyWebView 本地管理界面
├── chrome_extension/   # Chrome Extension 源码
├── assets/             # 应用图标和静态资源
├── packaging/          # PyInstaller 与 Windows 构建配置
├── tests/              # Python 和前端回归测试
├── docs/               # 架构、配置及阶段报告
├── release/            # 本地构建产物，不提交 Git
├── CHANGELOG.md
├── LICENSE
└── README.md
```

## Data Model

```text
Creator
 |
 ├── CreatorAccount
 ├── CreatorSnapshot
 ├── Insights
 |
 └── CampaignCreator
          |
       Campaign
          |
        Product
```

- `Creator` 保存达人主体资料和 Agency 归属。
- `CreatorAccount` 保存 TikTok、Instagram、YouTube 等平台账号。
- `CreatorSnapshot` 与 `Insights` 保存阶段性分析结果。
- `Product` 是 Campaign 的业务父级。
- `Campaign` 保存项目目标、周期、预算和业务状态。
- `CampaignCreator` 保存 Creator 在具体 Campaign 中的合作阶段、执行账号、成本和表现结果。
- `Legacy Cooperation` 仅保留历史兼容读取，不再作为新合作的写入模型。

## Installation

### Windows Release

当前正式版本：

```text
release/KOLConnect_v0.2.3.exe
```

1. 获取正式版 EXE。
2. 双击启动 KOLConnect。
3. 首次运行时，应用会在 `%APPDATA%\KOLConnect` 创建本地配置、日志和数据目录。
4. 使用 Product、Campaign、Creator Library 等模块前，建议先备份现有 Creator Library 工作簿。

### macOS Apple Silicon

macOS arm64 支持目前处于构建与真人验收阶段。GitHub Actions 可生成 `KOLConnect_v0.2.3_mac_arm64.dmg`，但在完成真实 Apple Silicon 设备验收前，不应视为正式无障碍支持。

- macOS 数据目录：`~/Library/Application Support/KOLConnect/`
- 本地构建入口：`bash packaging/build_macos.sh`
- 构建环境：Apple Silicon arm64 Mac、Python 3.12、项目构建依赖
- 签名方式：ad-hoc signing，不包含 Developer ID 签名或 Apple notarization
- 首次运行可能需要在 Finder 中右键选择“打开”，或由用户确认后执行 `xattr -cr /Applications/KOLConnect.app`

详细步骤见 [macOS 构建与双平台 CI 说明](docs/macOS构建与双平台CI说明.md)。

### Chrome Extension

1. 打开 `chrome://extensions`。
2. 开启“开发者模式”。
3. 点击“加载已解压的扩展程序”。
4. 选择项目中的 `chrome_extension/`。
5. 使用导入功能时，请保持 KOLConnect 桌面端正在运行。

## Data Storage

默认运行数据目录：

```text
%APPDATA%\KOLConnect
```

Creator、Campaign、Snapshot 和相关运营数据当前保存在 Excel 工作簿中。建议避免多台设备同时写入同一云同步工作簿，并在迁移或大批量操作前保留备份。

真实工作簿、凭证、日志、Chrome Profile 和用户运行数据不应提交到 Git 仓库。

## Continuous Integration

- 推送到 `main` 或向 `main` 提交 Pull Request 时，`CI` workflow 会在 Windows x64 和 macOS arm64 上运行 Python、Chrome Extension 与静态检查，不生成安装包。
- 需要测试安装包时，手动运行 `Build` workflow，分别生成 Windows EXE 与 macOS arm64 DMG artifacts。
- 推送 `v*` tag 时，`Build` workflow 在双平台构建完成后创建对应 GitHub Release；普通 `main` push 不触发打包或 Release。

## Current Version

```text
KOLConnect v0.2.3
```

当前阶段已完成：

- Creator Library 与生命周期模块化
- Creator 资料编辑、Agency 归属和归档恢复
- Product Management
- Campaign Management
- Campaign Detail 与 CampaignCreator 管理
- Dashboard CampaignCreator 指标迁移
- Legacy Cooperation 只读收口
- 前端页面生命周期和资源管理基础

## Development Status

`v0.2.0` 是 Product-Campaign 模型的首个正式版本，包含 Creator、Product、Campaign 与本地数据工作流。

当前边界：

- CampaignCreator 是新合作的主要数据模型。
- Legacy Cooperation 仅用于查看历史记录。
- Agency 目前支持达人归属维护，独立 Agency 管理页尚未开发。
- Excel 仍是当前本地数据存储方案。

## Roadmap

- Agency 管理页
- 达人库 Excel 批量导入
- Chrome 插件 Agency 选择
- 批量加入 Campaign

## Documentation

- [飞书集成配置指南](docs/飞书集成配置指南.md)
- [macOS 构建与双平台 CI 说明](docs/macOS构建与双平台CI说明.md)
- [Changelog](CHANGELOG.md)

## License

本项目采用 [MIT License](LICENSE)。
