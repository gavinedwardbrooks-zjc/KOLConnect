# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

from PyInstaller.utils.hooks import collect_all

PROJECT_ROOT = Path(SPECPATH).resolve().parents[1]
APP_DIR = PROJECT_ROOT / "app"
PACKAGING_DIR = PROJECT_ROOT / "packaging"
SQLITE_DLL = PACKAGING_DIR / "vendor" / "sqlite" / "windows-x64" / "sqlite3.dll"
RELEASE_NAME = "KOLConnect_v1.0.0"

if not SQLITE_DLL.is_file():
    raise SystemExit(f"Pinned SQLite runtime is missing: {SQLITE_DLL}")

datas = [
    (str(PROJECT_ROOT / "webapp"), "webapp"),
    (str(PROJECT_ROOT / "assets"), "assets"),
    (str(PROJECT_ROOT / "chrome_extension"), "chrome_extension"),
]
binaries = [(str(SQLITE_DLL), ".")]
hiddenimports = ['webview.platforms.edgechromium', 'selenium.webdriver', 'selenium.webdriver.chrome', 'selenium.webdriver.chrome.webdriver', 'webdriver_manager', 'webdriver_manager.chrome']
tmp_ret = collect_all('webview')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('selenium')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('webdriver_manager')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('lark_oapi')
# All SDK modules remain hidden imports in the PYZ. Avoid also extracting the
# same 10k+ Python sources as individual data entries.
datas += [item for item in tmp_ret[0] if not item[0].lower().endswith('.py')]
binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    [str(APP_DIR / "launcher.py")],
    pathex=[str(APP_DIR)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
# PyInstaller also discovers the interpreter's sqlite3.dll. Keep exactly the
# pinned WAL-safe runtime in the packaged application.
a.binaries = type(a.binaries)(
    item for item in a.binaries if Path(item[0]).name.lower() != "sqlite3.dll"
)
a.binaries.append(("sqlite3.dll", str(SQLITE_DLL), "BINARY"))
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=RELEASE_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version=str(PACKAGING_DIR / "windows_version_info.txt"),
    icon=[str(PROJECT_ROOT / "assets" / "KOLConnect.ico")],
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name=RELEASE_NAME,
)
