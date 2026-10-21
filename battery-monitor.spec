# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置。

产物是 onedir（目录式），不是 onefile —— onefile 每次启动都要把
几十 MB 解压到临时目录，冷启动会多 2~4 秒，对这个常驻小工具不划算。

关键点：
- pywebview 依赖 Microsoft.Web.WebView2.*.dll，在 webview/lib 下，必须整包带上；
- pythonnet 需要 Python.Runtime.dll 与 .NET 运行时探测文件；
- ui/ 是运行时读取的（每次请求都重读 index.html），必须作为数据文件带上。
"""
from PyInstaller.utils.hooks import collect_all

datas, binaries, hiddenimports = [], [], []

for pkg in ("webview", "pythonnet", "clr_loader"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

datas += [
    ("ui/index.html", "ui"),
    ("ui/app.ico", "ui"),
]

hiddenimports += [
    "hid",
    "bleak",
    "PIL.Image",
    "PIL.ImageDraw",
    "PIL.ImageFont",
    "PIL.ImageFilter",
    "PIL.ImageChops",
    "winrt.windows.devices.bluetooth",
    "winrt.windows.devices.bluetooth.genericattributeprofile",
    "winrt.windows.storage.streams",
    "winrt.windows.devices.enumeration",
    "winrt.windows.foundation",
]

a = Analysis(
    ["app.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "numpy", "scipy", "pandas", "IPython", "pytest"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="BatteryPulse",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    icon="ui/app.ico",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="BatteryPulse",
)
