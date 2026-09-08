Transcriber 9000 — Windows Installer Release Candidate

Installer устанавливает приложение только для текущего пользователя в:
%LOCALAPPDATA%\Programs\Transcriber 9000

Python, virtualenv и инструменты разработчика не требуются. CPU/CUDA helpers,
Whisper base model и ffmpeg входят в установленное приложение. GGUF в обычный
installer не входит: Recommended 9B или Lightweight 4B скачивается через
встроенный менеджер моделей и хранится в:
%LOCALAPPDATA%\Transcriber 9000\models

Удаление приложения удаляет установленные файлы и runtime assets. Модели и
настройки в %LOCALAPPDATA%\Transcriber 9000 не удаляются. Папки input/output в
каталоге установки также сохраняются, чтобы uninstall не удалял добавленные
пользователем исходники и результаты.

