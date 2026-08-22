# Установка после скачивания с GitHub

Эта версия рассчитана на запуск через Codex или локальную Python-среду на Windows. Исходные аудио и видео не отправляются во внешние сервисы.

## 1. Создать окружение

В папке проекта:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Если нужен GPU-режим, установите CUDA-сборку PyTorch, подходящую для вашей видеокарты. Если этого не сделать, Whisper продолжит работать на CPU, но `medium` и `large-v3` будут очень медленными.

## 2. Проверить ffmpeg

Приложению нужен локальный файл:

```text
tools\ffmpeg\bin\ffmpeg.exe
```

Если его нет, попросите Codex подготовить локальный ffmpeg для этого проекта или установите его вручную в указанную папку.

## 3. Запустить приложение

Двойной клик:

```text
Транскрибатор 9000.cmd
```

При первом запуске откройте раздел `Сервис` и скачайте нужные модели Whisper. Для старта достаточно `base` или `small`.

## 4. Проверить готовность

```powershell
.venv\Scripts\python.exe -X utf8 topgun_razbor.py --env-check
.venv\Scripts\python.exe -X utf8 topgun_minimal_app.py --smoke-test
```

## Что не хранится в GitHub

- `.venv`
- `.cache`
- модели Whisper `*.pt`
- пользовательские папки `input` и `output`
- локальный ffmpeg-бинарь
