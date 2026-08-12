# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

from PyInstaller.utils.hooks import collect_all

PROJECT_ROOT = Path(SPECPATH).resolve().parents[1]
APP_DIR = PROJECT_ROOT / "app"
MAC_ICON = PROJECT_ROOT / "assets" / "KOLConnect.icns"

# KOLConnect.icns is generated from assets/KOLConnect.png by build_macos.sh.
if not MAC_ICON.is_file():
    raise SystemExit("KOLConnect.icns is missing. Run packaging/build_macos.sh first.")

datas = [
    (str(PROJECT_ROOT / "webapp"), "webapp"),
    (str(PROJECT_ROOT / "assets"), "assets"),
    (str(PROJECT_ROOT / "chrome_extension"), "chrome_extension"),
]
binaries = []
hiddenimports = [
    "webview.platforms.cocoa",
    "selenium.webdriver",
    "selenium.webdriver.chrome",
    "selenium.webdriver.chrome.webdriver",
    "webdriver_manager",
    "webdriver_manager.chrome",
]

for package_name in ("webview", "selenium", "webdriver_manager"):
    package_datas, package_binaries, package_hiddenimports = collect_all(package_name)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hiddenimports

hiddenimports = [
    module_name
    for module_name in hiddenimports
    if module_name != "webview.platforms.edgechromium"
]

a = Analysis(
    [str(APP_DIR / "launcher.py")],
    pathex=[str(APP_DIR)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["webview.platforms.edgechromium"],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="KOLConnect",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch="x86_64",
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="KOLConnect",
)
app = BUNDLE(
    coll,
    name="KOLConnect.app",
    icon=str(MAC_ICON),
    bundle_identifier="com.kolconnect.app",
    info_plist={
        "CFBundleName": "KOLConnect",
        "CFBundleDisplayName": "KOLConnect",
        "CFBundleShortVersionString": "0.2.0",
        "CFBundleVersion": "0.2.0",
        "NSHighResolutionCapable": True,
    },
)
