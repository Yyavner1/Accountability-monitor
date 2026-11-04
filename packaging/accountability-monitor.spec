# PyInstaller spec — builds a self-contained Accountability Monitor executable.
#
#   pyinstaller packaging/accountability-monitor.spec
#
# Produces dist/accountability-monitor (one bundled app). Run per-OS: a macOS
# build runs on macOS, Windows on Windows, Linux on Linux. The heavy ML deps
# (nudenet, onnxruntime) are collected whole so the model loader works.

from PyInstaller.utils.hooks import collect_all

datas = [("../config.example.json", ".")]
binaries = []
hiddenimports = []

for pkg in ("nudenet", "onnxruntime", "mss", "PIL"):
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception:
        pass

a = Analysis(
    ["../accountability_monitor/app.py"],
    pathex=[".."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports + ["accountability_monitor"],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="accountability-monitor",
    console=False,          # no terminal window on launch
    disable_windowed_traceback=False,
    argv_emulation=True,    # lets macOS pass launch args
    target_arch=None,
    codesign_identity=None, # set by the signing step / env in CI
    entitlements_file=None,
)
