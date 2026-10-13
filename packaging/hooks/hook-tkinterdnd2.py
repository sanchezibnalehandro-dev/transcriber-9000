from PyInstaller.utils.hooks import collect_data_files
from pathlib import Path
import sys


# TkDnD is loaded by Tcl at runtime; its scripts and native DLL are data, not
# discoverable Python imports.
datas = collect_data_files("tkinterdnd2")
if sys.platform == "darwin":
    datas = [
        (source, destination)
        for source, destination in datas
        if "tkdnd" not in Path(source).parts
        or Path(source).parts[Path(source).parts.index("tkdnd") + 1]
        in {"osx-arm64", "osx-arm64-tcl9"}
    ]
