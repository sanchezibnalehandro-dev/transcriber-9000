from PyInstaller.utils.hooks import collect_data_files


# TkDnD is loaded by Tcl at runtime; its scripts and native DLL are data, not
# discoverable Python imports.
datas = collect_data_files("tkinterdnd2")
