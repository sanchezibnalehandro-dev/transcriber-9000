Transcriber 9000 — Portable Release Candidate

1. Распакуйте папку целиком в место, доступное для записи текущему пользователю.
2. Запустите "Transcriber 9000.exe".
3. В настройках AI скачайте Recommended 9B или Lightweight 4B модель.

Python, virtualenv и инструменты разработчика не требуются.
Модели и выбор активной модели хранятся в:
%LOCALAPPDATA%\Transcriber 9000\

Папки input, output и рабочий cache в этом portable RC находятся рядом с EXE,
поэтому папка приложения должна оставаться доступной для записи.

На компьютере без NVIDIA/CUDA AI-отчёт автоматически использует CPU helper.
Драйвер NVIDIA и nvcuda.dll в пакет не входят.

Сведения о сторонних компонентах: THIRD_PARTY_NOTICES.md
