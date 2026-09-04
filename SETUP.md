# Установка после скачивания с GitHub

Приложение рассчитано на Windows и работает локально. Исходные аудио и видео не отправляются во внешние сервисы.

## 1. Создать Python-окружение

Откройте PowerShell в папке проекта и выполните:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Если нужен GPU-режим, установите CUDA-сборку PyTorch, подходящую для вашей видеокарты. Без неё Whisper продолжит работать на CPU, но `medium` и `large-v3` будут значительно медленнее.

## 2. Проверить ffmpeg

Приложению нужен локальный файл:

```text
tools\ffmpeg\bin\ffmpeg.exe
```

Если его нет, установите ffmpeg в указанную папку.

## 3. Проверить приложение

Проверка ядра:

```powershell
.venv\Scripts\python.exe -X utf8 transcriber_core.py --env-check
```

Проверка GUI без открытия рабочего окна:

```powershell
.venv\Scripts\python.exe -X utf8 transcriber_app.py --smoke-test
```

## 4. Запустить приложение

Двойной клик по файлу:

```text
Транскрибатор 9000.cmd
```

При первом запуске откройте раздел `Сервис` и скачайте нужную модель Whisper. Для начала обычно достаточно `base` или `small`.

## Что не хранится в GitHub

- `.venv`
- `.cache`
- модели Whisper `*.pt`
- пользовательские папки `input` и `output`
- локальные бинарные файлы ffmpeg
