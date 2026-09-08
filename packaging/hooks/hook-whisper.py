from PyInstaller.utils.hooks import collect_data_files


# Whisper reads tokenizer assets by package-relative path.
datas = collect_data_files("whisper")
