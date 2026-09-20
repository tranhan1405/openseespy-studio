# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import collect_all, copy_metadata


ROOT = Path(SPECPATH).parent
SRC = ROOT / "src"

datas = [
    (
        str(SRC / "openseespy_studio" / "resources"),
        "openseespy_studio/resources",
    )
]
binaries = []
hiddenimports = []

for package_name in (
    "openseespy",
    "openseespywin",
    "pyvista",
    "pyvistaqt",
):
    try:
        package_datas, package_binaries, package_hidden = collect_all(
            package_name
        )
    except Exception:
        continue
    datas.extend(package_datas)
    binaries.extend(package_binaries)
    hiddenimports.extend(package_hidden)

try:
    datas.extend(copy_metadata("openseespy-studio"))
except Exception:
    pass

a = Analysis(
    [str(ROOT / "run.py")],
    pathex=[str(SRC)],
    binaries=binaries,
    datas=datas,
    hiddenimports=sorted(set(hiddenimports)),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="OpenSeesPyStudio",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="OpenSeesPyStudio",
)
