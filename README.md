# KOLConnect v0.1.2

海外 KOL 达人管理与合作分析工具。

KOLConnect 帮助海外营销团队完成达人发现、资料采集、人工审核、达人管理、合作记录和 CRM 同步。桌面端、Chrome Extension、Creator Library 与 Dashboard 共同组成完整的 KOL 运营工作流。

## 功能介绍

### 1. Chrome Extension

支持在以下平台的公开达人主页中采集和分析资料：

- TikTok
- Instagram
- YouTube

达人资料采集包括：

- 用户名
- 达人名称
- 粉丝或订阅数据
- 公开简介

最近内容分析包括：

- 视频、Reels 或 Shorts 列表
- 播放数据
- 发布时间
- 点赞、评论等互动数据

采集结果取决于平台当前公开的数据、页面结构和登录状态。无法确认的字段会保留为空，不会自动猜测。

### 2. Creator Library

Creator Library 用于长期维护达人资产，支持：

- 达人数据库
- Creator Snapshot 数据快照
- 粉丝与内容表现趋势
- 达人状态管理
- 合作历史记录
- 合作花费、播放表现和 ROI 汇总

同一达人再次分析时可以保存新的数据快照，用于查看不同时间的数据变化。

### 3. Dashboard

Dashboard 是 KOL 运营工作台，提供：

- 达人总量和新增概览
- 待联系与合作中达人统计
- 达人数据健康状态
- 上升、下滑和数据过期提醒
- 合作数量、花费、播放和 ROI 表现
- 待处理事项

### 4. 邮件与飞书同步

KOLConnect 支持：

- 连接工作邮箱并同步近期邮件
- 按公开邮箱匹配达人账号和达人
- 将允许更新的回复状态同步到达人表
- 管理 Agency、Agency 联系人和来源联系人
- 将有效审核结果同步到飞书达人表与达人账号表

飞书仍可作为最终 CRM 数据库直接维护。KOLConnect 主要负责数据采集、整理、审核、补全和同步。

## 飞书集成配置

飞书四表字段、开放平台权限和 Table ID 配置请参阅：

- [飞书集成配置指南](docs/飞书集成配置指南.md)

## 安装方式

### Windows

1. 下载 `KOLConnect.exe`。
2. 双击运行。
3. 首次启动时，系统会自动创建：

```text
%APPDATA%\KOLConnect
```

4. 打开“设置”，按需配置达人库文件、飞书信息和邮箱账户。

运行达人抓取功能前，请确保 Windows 已安装 Google Chrome。部分平台可能需要先在抓取所使用的 Chrome Profile 中完成登录。

## Chrome Extension 安装

1. 在 Chrome 地址栏打开：

```text
chrome://extensions
```

2. 开启右上角的“开发者模式”。
3. 点击“加载已解压的扩展程序”。
4. 选择项目中的：

```text
chrome_extension/
```

5. 在 Chrome 工具栏固定 KOLConnect 插件图标。
6. 打开支持的达人主页，点击插件图标开始分析。

导入功能需要桌面端 KOLConnect 正在运行。

## 项目结构

```text
KOLConnect/
├─ app/                # 桌面入口、本地服务、任务、抓取、邮件和数据仓库
├─ webapp/             # 本地 Web 管理界面
├─ chrome_extension/   # Chrome Extension 正式源码
├─ assets/             # 应用图标等正式资源
├─ packaging/          # PyInstaller、版本资源和安装器配置
├─ tests/              # 桌面端与前端回归测试
├─ docs/               # 用户说明和文档资源
├─ release/            # Windows 发布产物
├─ CHANGELOG.md
├─ LICENSE
└─ README.md
```

## 数据存储

默认数据目录：

```text
%APPDATA%\KOLConnect
```

其中包括：

- 软件配置
- 邮箱设置
- 任务记录
- 运行日志
- 邮件缓存
- Creator Library 数据
- 数据备份
- Chrome Profile 运行数据

Creator Library 默认使用 Excel 工作簿保存，也可以在设置中指定 WPS 云盘或其他同步目录。为避免文件冲突，建议同一时间只在一台设备上写入该工作簿。

请勿将真实配置、邮箱密码、飞书密钥、任务数据、达人数据或 Chrome Profile 提交到公共代码仓库。

## 使用流程

```text
发现达人
  ↓
Chrome Extension 分析或创建抓取任务
  ↓
导入 KOLConnect
  ↓
人工审核和补充资料
  ↓
Creator Library 管理
  ↓
联系达人并记录合作
  ↓
查看结果和复盘
```

需要同步 CRM 时，可在审核页面将有效结果同步到飞书四表。同步不会自动替代运营人员的合作判断。

## 当前版本说明

当前版本：

```text
KOLConnect v0.1.2
```

包含：

- Windows 桌面端 Tool
- Chrome Extension
- Dashboard 工作台
- Creator Library
- 动态数据快照
- 合作历史
- Excel 数据存储
- 任务管理与审核
- 邮件匹配
- 飞书四表同步

## 已知限制

- Creator Library 当前使用 Excel 作为本地数据存储，建议避免多设备同时写入。
- 社交平台采集能力受登录状态、地区、公开范围和页面结构影响。
- TikTok、Instagram、YouTube 页面更新后，部分字段可能暂时无法读取。
- 点赞、评论、播放量和发布时间仅在平台公开时采集；缺失字段不会填入虚假数据。
- 邮件与飞书功能需要用户自行提供有效配置和访问权限。

## 开发说明

主要技术：

- Python
- JavaScript
- Chrome Extension Manifest V3
- PyInstaller
- pywebview

安装桌面端运行依赖：

```bash
pip install -r packaging/requirements.txt
```

从源码运行：

```bash
python app/launcher.py
```

执行基础检查：

```bash
python -m py_compile app/*.py
node --check webapp/app.js
```

构建 Windows EXE：

```powershell
powershell -ExecutionPolicy Bypass -File packaging/build_release.ps1
```

构建产物：

```text
release/KOLConnect.exe
```

修改业务逻辑时，应保持账号 UID、数据快照、飞书字段保护、邮件匹配和历史 Excel 兼容规则稳定。

## License

本项目采用 [MIT License](LICENSE)。
