# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files


root = Path(SPECPATH)
datas = collect_data_files(
    "rapidocr_onnxruntime",
    includes=[
        "config.yaml",
        "models/ch_PP-OCRv4_det_infer.onnx",
        "models/ch_PP-OCRv4_rec_infer.onnx",
        "models/ch_ppocr_mobile_v2.0_cls_infer.onnx",
    ],
)
binaries = []
hiddenimports = [
    "PIL._tkinter_finder",
    "pyautogui",
    "pyscreeze",
    "pygetwindow",
    "mouseinfo",
    "winotify._notify",
]

analysis = Analysis(
    [str(root / "run_app.pyw")],
    pathex=[str(root)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "IPython",
        "matplotlib",
        "numpy.testing",
        "onnxruntime.quantization",
        "onnxruntime.transformers",
        "pytest",
        "shapely.tests",
    ],
    noarchive=False,
    optimize=1,
)

pyz = PYZ(analysis.pure)

exe = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="JoinHelper",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=[str(root / "assets" / "wecom-rusher.ico")],
)

bundle = COLLECT(
    exe,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="JoinHelper",
)
