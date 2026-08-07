# KOLConnect v0.2.0 macOS 构建与双平台 CI 说明

## 支持边界

KOLConnect 使用同一份 Python、Web UI 和 Chrome Extension 源码构建 Windows x64 EXE 与 macOS Apple Silicon arm64 APP/DMG。macOS 流程目前提供构建能力，仍需通过真实 Apple Silicon Mac 完成人工验收后才能确认正式支持。

## 运行数据目录

- Windows：`%APPDATA%\KOLConnect\`
- macOS：`~/Library/Application Support/KOLConnect/`
- Linux：`${XDG_DATA_HOME}/KOLConnect/`；未设置时使用 `~/.local/share/KOLConnect/`

工作簿、日志、配置和用户凭证属于运行数据，不进入 APP bundle 或 Git 仓库。

## macOS 本地构建

环境要求：

- Apple Silicon arm64 Mac
- Python 3.12
- Xcode Command Line Tools 提供的 `sips`、`iconutil`、`codesign` 和 `hdiutil`

执行：

```bash
python -m pip install -r packaging/requirements-build.txt
bash packaging/build_macos.sh
```

构建脚本会完成以下步骤：

1. 检查 Darwin、`uname -m` 和 Python 均为 arm64。
2. 验证 `assets/KOLConnect.png` 至少为 1024 x 1024。
3. 使用 `sips` 和 `iconutil` 临时生成 `assets/KOLConnect.icns`。
4. 使用 `packaging/spec/KOLConnect_mac.spec` 生成 `KOLConnect.app`。
5. 对 APP 执行 ad-hoc signing 并严格验证签名。
6. 使用 `hdiutil` 生成 `release/KOLConnect_v0.2.0_mac_arm64.dmg`。
7. 输出 APP 路径、DMG 路径、实际 CPU 架构和 SHA-256。

不要直接在缺少 `assets/KOLConnect.icns` 时运行 Mac spec；应始终通过 `packaging/build_macos.sh` 先生成图标。

## 签名与 Gatekeeper

当前使用 ad-hoc signing，不是 Apple Developer ID 签名，也没有 notarization。因此从互联网下载的 APP 仍可能被 Gatekeeper 拦截。内部测试可在 Finder 中右键选择“打开”，或在明确确认来源后执行：

```bash
xattr -cr /Applications/KOLConnect.app
```

这不代表正式分发所需的 Developer ID 与 notarization 已完成。

## GitHub Actions

`.github/workflows/build.yml` 支持：

- 手动 `workflow_dispatch`：构建 Windows x64 EXE 和 macOS arm64 DMG，仅保存 Actions artifacts，不创建 Release。
- 推送未来的 `v*` tag：两端构建成功后，Release job 下载两个 artifacts 并上传到对应 tag 的 GitHub Release。

macOS job 使用 `macos-15` arm64 runner，并同时检查 `uname -m` 与 `platform.machine()`。任一结果不是 `arm64` 时立即失败，禁止把其他架构错误标记为 arm64。

## 首次 CI 验证

首次验证只应从 GitHub Actions 手动运行 `Build` workflow，不创建 tag。成功后确认 artifacts 包含：

- `KOLConnect_v0.2.0.exe`
- `KOLConnect_v0.2.0_mac_arm64.dmg`

然后在真实 Apple Silicon Mac 上检查：

1. DMG 可以挂载，APP 可以复制到 Applications。
2. Gatekeeper 的用户确认流程可行。
3. APP、Python server 与 WebView 能正常启动。
4. Creator Library 能加载。
5. Chrome/Selenium 基础路径正常，未内置驱动时可使用现有 driver fallback。
6. 退出后本地端口正常释放。

## 当前 v0.2.0 Release

当前已有的 `v0.2.0` Release 不由本阶段自动修改。手动 CI 验证成功后，可由维护者选择：

- 将 DMG 手动补充到现有 `v0.2.0` Release；或
- 在后续正式版本（例如 `v0.2.1`）通过 tag 流程同时发布 EXE 和 DMG。

不要为了补 Mac 包自动创建 `v0.2.0-mac1` tag 或新的 Release。
