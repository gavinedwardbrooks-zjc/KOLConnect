# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

from PyInstaller.utils.hooks import collect_all

PROJECT_ROOT = Path(SPECPATH).resolve().parents[1]
APP_DIR = PROJECT_ROOT / "app"
PACKAGING_DIR = PROJECT_ROOT / "packaging"

datas = [
    (str(PROJECT_ROOT / "webapp"), "webapp"),
    (str(PROJECT_ROOT / "assets"), "assets"),
    (str(PROJECT_ROOT / "chrome_extension"), "chrome_extension"),
]
binaries = []
hiddenimports = ['webview.platforms.edgechromium', 'selenium.webdriver', 'selenium.webdriver.chrome', 'selenium.webdriver.chrome.webdriver', 'webdriver_manager', 'webdriver_manager.chrome']
tmp_ret = collect_all('webview')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('selenium')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('webdriver_manager')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('lark_oapi')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


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
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='KOLConnect',
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
