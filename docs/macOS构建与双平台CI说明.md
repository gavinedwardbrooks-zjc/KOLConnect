# KOLConnect v2.0.0 macOS 构建与双平台 CI 说明

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
6. 使用 `hdiutil` 生成 `release/KOLConnect_v2.0.0_mac_arm64.dmg`。
7. 输出 APP 路径、DMG 路径、实际 CPU 架构和 SHA-256。

不要直接在缺少 `assets/KOLConnect.icns` 时运行 Mac spec；应始终通过 `packaging/build_macos.sh` 先生成图标。

## 签名与 Gatekeeper

当前使用 ad-hoc signing，不是 Apple Developer ID 签名，也没有 notarization。因此从互联网下载的 APP 仍可能被 Gatekeeper 拦截。内部测试可在 Finder 中右键选择“打开”，或在明确确认来源后执行：

```bash
xattr -cr /Applications/KOLConnect.app
```

这不代表正式分发所需的 Developer ID 与 notarization 已完成。

## GitHub Actions

`.github/workflows/ci.yml` 负责源码验证：

- 推送到 `main`、向 `main` 提交 Pull Request，或手动运行 `workflow_dispatch` 时，在 Windows x64 与 `macos-15` arm64 上执行 Python 全量测试、Extension 自动发现测试和静态检查。
- CI 不执行打包、签名、DMG 创建或 GitHub Release。
- Extension 测试由 `tests/run_extension_tests.js` 自动发现 `tests/test_*.js` 与 `tests/test_*.mjs`，新增符合命名规则的测试无需修改 workflow。

`.github/workflows/build.yml` 只负责常规打包与 tag 发布：

- 手动 `workflow_dispatch`：构建 Windows x64、macOS arm64 与 macOS Intel 产物，仅保存 Actions artifacts，不创建 Release。
- 推送未来的 `v*` tag：各平台构建成功后，Release job 下载 artifacts 并上传到对应 tag 的 GitHub Release。
- 普通 `main` push 不触发 Build。

macOS job 使用 `macos-15` arm64 runner，并同时检查 `uname -m` 与 `platform.machine()`。任一结果不是 `arm64` 时立即失败，禁止把其他架构错误标记为 arm64。

## v2.0.0 冻结源码手动构建

`.github/workflows/build-macos-client.yml` 是 v2.0.0 macOS 14+ 双架构发布候选的手动构建入口。workflow root checkout 保留触发时的最新主线基础设施和合同测试；每个 matrix job 将冻结应用源码单独 checkout 到 `frozen-src/`，并在该目录中验证 SHA：

```text
5aa4f5f50d1decd4fc49b84b268526e96e52a231
```

该 workflow 分别使用 `macos-14` 原生 arm64 runner 和 `macos-15-intel` 原生 x86_64 runner。每个 job 在构建前验证版本元数据并运行 macOS packaging、版本一致性和 Keychain 合同测试。构建后使用 `file`、`lipo`、`otool` 和 `vtool -show-build` 验证 APP 与包内 `pyexpat` 的架构及最低 macOS 版本；任一关键二进制要求高于 macOS 14 时，该架构 job 必须失败，不能标记为 macOS 14+。

每个 job 使用隔离的临时 `HOME` 启动实际 `KOLConnect.app`，验证 localhost UI、用户数据目录以及通过 server 启动加载的 `openpyxl`、`ElementTree` 和 `pyexpat`。最终会分别上传：

```text
KOLConnect-v2.0.0-macOS14-arm64
  KOLConnect_v2.0.0_macOS14+_arm64.dmg
KOLConnect-v2.0.0-macOS14-x64
  KOLConnect_v2.0.0_macOS14+_x64.dmg
```

workflow 会挂载每个 DMG 确认其中包含正确架构的 `KOLConnect.app`，并在日志和 Job Summary 中输出实际文件大小与 DMG 文件的 SHA-256。运行完成后，在 GitHub Actions 对应 run 的 Artifacts 区域下载；该手动 workflow 不创建或修改 GitHub Release。

当前 APP 仅使用 ad-hoc signing，不包含 Apple Developer ID 签名，也未 notarize。从 GitHub 下载后 macOS Gatekeeper 可能显示警告，这是当前分发边界，不应将该产物描述为已公证。

## 首次 CI 验证

首次验证只应从 GitHub Actions 手动运行 `Build macOS 14+ Clients` workflow，不创建 tag。成功后确认 artifacts 包含：

- `KOLConnect_v2.0.0_macOS14+_arm64.dmg`
- `KOLConnect_v2.0.0_macOS14+_x64.dmg`

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
