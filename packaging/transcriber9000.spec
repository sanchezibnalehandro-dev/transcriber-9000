from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules


project_root = Path(SPECPATH).resolve().parent
stage_root = project_root / ".release-staging"

required_stage_files = (
    stage_root / ".cache" / "whisper" / "base.pt",
    stage_root / "tools" / "ffmpeg" / "bin" / "ffmpeg.exe",
    stage_root / ".cache" / "llama-helper-cpu" / "release" / "llama-helper.exe",
    stage_root / ".cache" / "llama-helper-cuda" / "release" / "llama-helper.exe",
)
missing = [str(path) for path in required_stage_files if not path.is_file()]
if missing:
    raise SystemExit("Portable staging is incomplete:\n" + "\n".join(missing))

datas = []
datas += collect_data_files("customtkinter")
datas += collect_data_files("whisper")
datas += collect_data_files("tkinterdnd2")
datas += [
    (str(project_root / "resources" / "report_models.json"), "resources"),
    (str(project_root / "report_templates" / "product_meeting.json"), "report_templates"),
    (str(project_root / "THIRD_PARTY_NOTICES.md"), "."),
    (str(project_root / "README_PORTABLE.txt"), "."),
    (str(stage_root / ".cache" / "whisper" / "base.pt"), ".cache/whisper"),
    (str(stage_root / "tools" / "ffmpeg" / "bin" / "ffmpeg.exe"), "tools/ffmpeg/bin"),
]

for helper_name in ("llama-helper-cpu", "llama-helper-cuda"):
    helper_dir = stage_root / ".cache" / helper_name / "release"
    for source in helper_dir.iterdir():
        if source.is_file():
            datas.append((str(source), f".cache/{helper_name}/release"))

hiddenimports = [
    "torch",
    "whisper",
    "tiktoken",
    "tiktoken_ext",
    "tiktoken_ext.openai_public",
    "numpy",
    "numba",
    "llvmlite",
    "llvmlite.binding",
]
hiddenimports += collect_submodules("tiktoken_ext")

a = Analysis(
    [str(project_root / "transcriber_entry.py")],
    pathex=[str(project_root)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[str(project_root / "packaging" / "hooks")],
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
    [],
    exclude_binaries=True,
    name="Transcriber 9000",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    contents_directory=".",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Transcriber 9000",
)
