"""Apple Silicon onedir .app. Run on an arm64 macOS runner only."""

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules


project_root = Path(SPECPATH).resolve().parent
stage_root = project_root / ".release-staging-macos"
ffmpeg = stage_root / "tools" / "ffmpeg" / "bin" / "ffmpeg"
if not ffmpeg.is_file():
    raise SystemExit(f"Pinned macOS FFmpeg is missing: {ffmpeg}")

datas = []
datas += collect_data_files("customtkinter")
datas += collect_data_files("whisper")
datas += collect_data_files("tkinterdnd2")
datas += [
    (str(project_root / "resources" / "report_models.json"), "resources"),
    (str(project_root / "report_templates" / "product_meeting.json"), "report_templates"),
    (str(project_root / "packaging" / "README_MACOS.md"), "."),
    (str(project_root / "packaging" / "MACOS_THIRD_PARTY_NOTICES.md"), "."),
    (str(stage_root / "licenses"), "LICENSES"),
]

hiddenimports = [
    "torch", "whisper", "tiktoken", "tiktoken_ext",
    "tiktoken_ext.openai_public", "numpy", "numba", "llvmlite",
    "llvmlite.binding",
]
hiddenimports += collect_submodules("tiktoken_ext")

a = Analysis(
    [str(project_root / "transcriber_entry.py")],
    pathex=[str(project_root)],
    binaries=[(str(ffmpeg), "tools/ffmpeg/bin")],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[str(project_root / "packaging" / "hooks")],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Transcriber 9000",
    console=False,
    target_arch="arm64",
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="Transcriber 9000", upx=False)
app = BUNDLE(
    coll,
    name="Transcriber 9000.app",
    bundle_identifier="dev.sanchezibnalehandro.transcriber9000",
    info_plist={"NSHighResolutionCapable": True},
)
