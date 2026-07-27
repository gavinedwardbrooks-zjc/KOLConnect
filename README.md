# KOLConnect

> **An influencer relationship management tool for overseas marketing teams.**  
> 海外达人关系管理工具。

KOLConnect 是一个面向海外营销团队的达人关系管理工具，帮助团队从发现达人开始，完成账号整理、公开商务邮箱收集、人工审核、Agency 关系管理和 CRM 同步。

它不是 AI Agent，也不定位为单纯的爬虫工具。数据采集只是工作流的一部分；系统的核心目标是让达人、社交账号、联系人、Agency 与合作信息保持清晰、可审核、可持续维护。

**建议 GitHub Topics：** `influencer-marketing` `creator-economy` `kol-management` `crm` `marketing-automation`

## 功能概览

- **Creator 管理**：维护达人基本资料、合作阶段、负责人、备注和来源联系人。
- **Social Account 管理**：统一管理 TikTok、Instagram、YouTube 账号及其主页、粉丝数、邮箱和抓取状态。
- **Email Discovery**：从公开主页和外部链接中寻找商务邮箱，并支持缺失邮箱补全任务。
- **Agency 管理**：管理 Agency、商务联系人、来源联系人和达人归属关系。
- **飞书 CRM 同步**：将审核后的任务数据同步到达人表和达人账号表，保护已有人工运营信息。
- **Chrome 插件**：在达人主页上手动采集基础资料并创建人工录入任务。
- **任务管理**：支持平台筛选、独立任务进度、暂停、继续、优雅停止和异常中断提示。
- **邮件管理**：同步工作邮箱的近期邮件，按账号邮箱关联达人，并手动同步允许更新的联系状态。

## 工作流程

```text
发现达人
  ↓
导入主页链接或使用 Chrome 插件人工录入
  ↓
数据采集与整理
  ↓
人工审核、补充资料
  ↓
同步到飞书 CRM
  ↓
管理 Agency、联系人、合作阶段与邮件沟通
```

飞书多维表格是最终 CRM 数据库。KOLConnect 负责采集、整理、补全和同步；运营人员可以继续直接在飞书中维护合作决策。

## 主要模块

### 链接清洗

输入 TikTok、Instagram、YouTube 链接后，系统会识别平台、整理为标准主页链接，并保留无法使用链接的原因。账号唯一 ID 由系统内部维护，用于账号去重，无需人工复制或填写。

### 达人和社交账号

一个达人可以关联多个社交账号：

```text
Maria
├─ TikTok
├─ Instagram
└─ YouTube
```

账号层保存平台、主页链接、粉丝数、账号邮箱、最近发布时间和抓取状态；达人层保存合作关系和人工运营信息。

### 邮箱发现与审核

系统从公开主页和外部链接中寻找商务邮箱。抓取结果会先进入任务审核页，运营人员可补充或修正达人名称、邮箱、WhatsApp、粉丝数和备注，再同步到 CRM。

### Agency 与联系人

Agency 可维护机构信息、联系人和旗下达人。联系人可在尚未确认所属 Agency 时独立存在；后续确认后再关联机构。人工录入达人时可选择“来源联系人”，记录最初提供该达人资源的对接人。

### 邮件管理

系统可连接工作邮箱，读取近期收件箱邮件，并按邮箱精确关联：

```text
邮件发件人邮箱 → 达人账号邮箱 → 达人
```

它不会自动发送邮件，也不会替运营人员判断合作意向。

## 快速开始

### 使用桌面版

1. 从 GitHub Releases 下载 `KOLConnect.exe`。
2. 双击启动应用。
3. 在“设置”中填写飞书配置和需要使用的邮箱账户。
4. 创建任务、抓取或人工录入、审核后同步到飞书。

### 从源码运行

适合维护者和开发环境：

```bash
pip install -r packaging/requirements.txt
python app/launcher.py
```

运行抓取功能前，请安装 Google Chrome。默认使用应用自己的 ChromeProfile；首次使用需要登录的平台时，请在该独立窗口中完成登录。

### 构建桌面版

```powershell
powershell -ExecutionPolicy Bypass -File packaging/build_release.ps1
```

构建产物位于 `release/KOLConnect.exe`。

## 飞书 CRM 配置

在同一个飞书多维表格文件中配置以下四张表：

| 表 | 用途 | 关键字段 |
| --- | --- | --- |
| 达人 | 保存达人基本资料和合作信息 | 达人名称、WhatsApp、合作阶段、负责人、来源联系人 |
| 达人账号 | 保存社交媒体账号 | 账号唯一ID、平台、主页链接、粉丝数、账号邮箱、达人 |
| Agency | 保存机构资料 | Agency名称、官网、公共邮箱、旗下达人、联系人 |
| Agency联系人 | 保存商务或资源联系人 | 联系人姓名、WhatsApp、邮箱、所属 Agency、负责达人 |

在应用“设置”中填写：

- 飞书 App ID
- 飞书 App Secret
- 飞书 App Token
- 达人表 Table ID
- 达人账号表 Table ID
- Agency 表 Table ID
- Agency 联系人表 Table ID

字段名称和关联关系应保持一致。账号唯一ID由系统维护，请不要手工修改。

## Chrome 插件

浏览器插件位于 `chrome_extension/`，用于在 TikTok、Instagram、YouTube 达人主页上进行**人工辅助采集**。

1. 在 Chrome 扩展程序页面启用“开发者模式”。
2. 选择“加载已解压的扩展程序”。
3. 选择项目中的 `chrome_extension/` 目录。
4. 打开达人主页，点击 “KOL Connect 插件”。
5. 确认平台、主页、用户名、粉丝数和简介后发送到本地 KOLConnect。

插件不会登录平台、不会批量自动抓取，也不会上传数据到云端。

## 截图展示

截图统一存放在 `docs/images/`。建议补充以下页面截图：

| 页面 | 建议文件名 |
| --- | --- |
| 任务管理 | `docs/images/task-management.png` |
| 审核结果 | `docs/images/review-results.png` |
| 飞书配置 | `docs/images/feishu-settings.png` |
| 邮件管理 | `docs/images/mail-inbox.png` |
| Chrome 插件 | `docs/images/chrome-extension.png` |

## 项目结构

```text
KOLConnect/
├─ app/                # 本地服务、任务、抓取和邮件模块
├─ assets/             # 应用图标等正式资源
├─ chrome_extension/   # Chrome 辅助采集插件
├─ docs/               # 使用说明和项目截图
├─ packaging/          # 构建、版本信息和安装器配置
├─ release/            # 桌面版构建产物
├─ webapp/             # 本地网页界面
├─ CHANGELOG.md
├─ LICENSE
└─ .env.example
```

本地任务、设置、邮件缓存、日志和独立 Chrome 登录状态均保存在当前 Windows 用户的应用数据目录中，不应提交到代码仓库。

## 贡献

欢迎提交 Issue、改进建议和 Pull Request。

提交前请：

1. 不提交真实飞书凭据、邮箱密码、Cookie、ChromeProfile、任务数据或真实达人资料。
2. 保持账号唯一ID、飞书四表同步和人工数据保护规则兼容。
3. 运行 Python 与前端语法检查。
4. 在 Pull Request 中说明功能影响范围和验证方式。

## License

本项目采用 [MIT License](LICENSE)。

