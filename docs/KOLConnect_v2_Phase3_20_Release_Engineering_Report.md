# KOLConnect v2 Phase 3.20 Release Engineering Report

执行日期：2026-08-03
当前分支：`develop`
目标内部测试版本：`KOLConnect v0.2.0-dev.2`

## 一、执行边界

本阶段仅调整版本显示和发布工程配置，并执行静态完整性检查。未执行 PyInstaller、未生成 EXE、未修改业务数据、未提交、未推送。

现有稳定版 `release/KOLConnect.exe` 未被修改：

- FileVersion：`0.1.2`
- ProductVersion：`0.1.2`
- 修改时间：`2026-07-29 18:38:20`
- 文件大小：`69,959,118` bytes

## 二、版本管理

### 2.1 当前版本来源审计

项目没有 `package.json`，也没有独立的 `config/version` 或统一版本清单。当前活动版本由以下位置分别维护：

| 位置 | 用途 | 调整结果 |
|---|---|---|
| `app/launcher.py` | 桌面窗口标题 | `KOLConnect v0.2.0-dev.2` |
| `app/server.py` | 系统健康信息、启动日志 | `KOLConnect v0.2.0-dev.2` |
| `webapp/index.html` | Web 顶部版本显示 | `KOLConnect v0.2.0-dev.2` |
| `webapp/app.js` | Debug 信息回退版本 | `KOLConnect v0.2.0-dev.2` |
| `packaging/windows_version_info.txt` | Windows EXE 元数据 | 已更新 |
| `packaging/installer/KOLConnect.iss` | 安装器版本和输入文件 | 已更新 |
| `packaging/build_release.ps1` | 候选 EXE 文件名和输出路径 | 已更新 |

README 和 CHANGELOG 仍保留当前稳定公开版本及历史版本记录，不作为本次内部开发包的运行时或构建版本来源。本阶段没有批量改写历史报告中的版本号。

### 2.2 Windows 元数据

已统一为：

- FileDescription：`KOLConnect v0.2.0-dev.2`
- FileVersion：`0.2.0.2`
- ProductVersion：`0.2.0-dev.2`
- ProductName：`KOL Connect`
- OriginalFilename：`KOLConnect.exe`

Windows 固定版本字段使用合法四段数字 `0.2.0.2`，产品展示版本保留预发布标识 `0.2.0-dev.2`。

## 三、构建隔离

`packaging/build_release.ps1` 已改为将未来构建结果复制到：

```text
release/dev/KOLConnect_v0.2.0-dev.2.exe
```

不再复制或覆盖：

```text
release/KOLConnect.exe
```

安装器配置同步改为从 `release/dev/KOLConnect_v0.2.0-dev.2.exe` 读取候选包。安装后仍使用标准文件名 `KOLConnect.exe`，避免桌面快捷方式和卸载信息失效。

安装器输出名调整为：

```text
KOLConnect_v0.2.0-dev.2_setup
```

`release/` 已在 `.gitignore` 中整体忽略，因此未来生成的 `release/dev/` 产物不会进入 Git。

## 四、依赖完整性

### 4.1 磁盘文件完整性

以下构建入口和资源均存在：

- `packaging/spec/KOLConnect.spec`
- `packaging/windows_version_info.txt`
- `packaging/build_release.ps1`
- `packaging/installer/KOLConnect.iss`
- `assets/KOLConnect.ico`
- `app/launcher.py`
- `app/server.py`
- `webapp/index.html`

`index.html` 引用的 CSS、API Client、Page Registry、Page Resources 和 7 个页面模块全部存在。spec 会递归包含整个 `webapp/` 目录，因此无需为新增 JS 文件逐项修改 spec。

`server.py` 直接导入 Product、Campaign、CampaignCreator 和 Dashboard 数据模块；对应 Python 文件均存在，当前未发现 PyInstaller hidden import 缺口。

### 4.2 Git 未跟踪的运行依赖

以下文件实际存在且参与运行，但当前未被 Git 跟踪：

```text
app/campaign_creator_repository.py
app/campaign_repository.py
app/data_repository_base.py
app/product_repository.py
webapp/core/page-registry.js
webapp/core/page-resources.js
webapp/services/api-client.js
webapp/pages/campaign-detail.js
webapp/pages/campaigns.js
webapp/pages/creator-library-detail.js
webapp/pages/creator-library.js
webapp/pages/dashboard.js
webapp/pages/products.js
webapp/pages/settings.js
```

结论：当前本地工作区具备物理构建条件，但 Git 检出的同一分支尚不具备完整构建条件。正式打包前必须确认这些运行依赖进入待提交清单，并由一个明确 commit 固定构建基线。

### 4.3 缺失列表

磁盘缺失文件：**无**。
HTML 引用缺失：**无**。
spec 必需路径缺失：**无**。
Git 跟踪缺失：**上述 14 个运行文件**。

## 五、构建前静态检查结果

| 检查项 | 结果 |
|---|---|
| 当前分支 | `develop` |
| PowerShell 构建脚本语法 | 通过 |
| Python 版本相关入口语法 | 通过（`launcher.py`、`server.py`） |
| Web 版本相关脚本语法 | 通过（`app.js`） |
| PyInstaller spec 路径 | 存在 |
| Windows 版本资源路径 | 存在 |
| 应用图标 | 存在 |
| Python 桌面入口 | 存在 |
| Web 静态目录 | 存在 |
| index.html JS/CSS 引用 | 全部存在 |
| 活动代码中 `dev.1` 残留 | 未发现（排除缓存和历史文档） |
| 活动代码中 `v2.0.0-dev` 残留 | 未发现 |
| Git diff 空白错误 | 未发现，仅有行尾格式提示 |
| `release/dev/` 输出 | 未生成，符合“不实际 build”要求 |
| 稳定版 EXE | 未修改 |

## 六、修改文件

- `app/launcher.py`
- `app/server.py`
- `webapp/index.html`
- `webapp/app.js`
- `packaging/windows_version_info.txt`
- `packaging/installer/KOLConnect.iss`
- `packaging/build_release.ps1`
- `docs/KOLConnect_v2_Phase3_20_Release_Engineering_Report.md`

## 七、打包前剩余条件

1. 将全部运行依赖纳入可追溯的 Git 提交；本阶段按要求未执行提交。
2. 确认工作区除已审查的 v2 代码、测试和报告外没有未知修改。
3. 执行完整 Python、前端和 v2 回归测试。
4. 使用修改后的构建脚本生成隔离候选包。
5. 在隔离 APPDATA 下验证首次启动、旧数据迁移、页面/API、退出和端口释放。
6. 构建后核对实际 EXE 的 FileVersion、ProductVersion、大小、SHA-256 和源码 commit。

## 八、结论

版本冲突和稳定 EXE 覆盖风险已经完成工程修复。当前源码的 spec、静态资源和本地依赖均存在，具备下一阶段执行测试和隔离构建的技术条件。

但在 Git 未跟踪的运行依赖纳入提交之前，候选包仍不可复现。因此当前状态为：

**可以进入构建前完整回归；完成源码追踪和回归后，方可生成 `KOLConnect_v0.2.0-dev.2.exe`。**
