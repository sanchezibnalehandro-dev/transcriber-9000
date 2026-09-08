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

При первом запуске откройте раздел `Настройки` и скачайте нужную модель Whisper. Для начала обычно достаточно `base` или `small`.

## 5. Подготовить backend AI-отчёта

Этот шаг подготавливает локальный AI/report backend v1 для GUI и CLI. После успешной TXT-транскрипции GUI автоматически использует готовый CUDA path. CPU остаётся явным медленным fallback; для SRT-only результата AI report не запускается.

Установите Rust MSVC toolchain, Visual Studio Build Tools с C++ workload и LLVM/libclang. Для CUDA-сборки дополнительно нужен совместимый NVIDIA CUDA Toolkit. Запускайте сборку из Developer PowerShell/`VsDevCmd`, где доступны compiler, Windows SDK и `LIBCLANG_PATH`.

CPU helper:

```powershell
$env:CARGO_TARGET_DIR = ".cache\llama-helper-cpu"
cargo build --manifest-path ".\llama-helper\Cargo.toml" --release
```

CUDA helper:

```powershell
$env:CARGO_TARGET_DIR = ".cache\llama-helper-cuda"
cargo build --manifest-path ".\llama-helper\Cargo.toml" --release --features cuda
```

Скачайте только этот production-candidate artifact в `models\report`:

```text
Repository: bartowski/Qwen_Qwen3.5-9B-GGUF
Revision:   2dcd842c59ea5eb119267064550a7a4c592b16c3
File:       Qwen_Qwen3.5-9B-Q4_K_M.gguf
Bytes:      6169341984
SHA-256:    d784ce9eda1a5a7b51e8f705a9e6310844bf4f173654d115823c775fdea56d43
```

Проверьте локальный файл:

```powershell
Get-Item ".\models\report\Qwen_Qwen3.5-9B-Q4_K_M.gguf" | Select-Object Length
Get-FileHash -Algorithm SHA256 ".\models\report\Qwen_Qwen3.5-9B-Q4_K_M.gguf"
```

Запуск на CPU:

```powershell
python -X utf8 report_pipeline.py `
  --transcript ".\output\meeting.txt" `
  --template ".\report_templates\product_meeting.json" `
  --helper ".\.cache\llama-helper-cpu\release\llama-helper.exe" `
  --model ".\models\report\Qwen_Qwen3.5-9B-Q4_K_M.gguf" `
  --device cpu
```

CUDA — основной production path: замените helper на `.cache\llama-helper-cuda\release\llama-helper.exe` и укажите `--device cuda`. Если CUDA runtime DLL не находится, добавьте `bin` установленного CUDA Toolkit в `PATH` текущего процесса. CPU mode поддерживается как degraded fallback и на измеренном LONG fixture занял около 8 минут 51 секунды против примерно 56 секунд на CUDA. Production inference после подготовки использует только локальные файлы.

Проверка report contracts без запуска модели:

```powershell
python -X utf8 -m unittest tests.test_report_pipeline -v
```

## Что не хранится в GitHub

- `.venv`
- `.cache`
- модели Whisper `*.pt`
- пользовательские папки `input` и `output`
- локальные бинарные файлы ffmpeg
- локальные GGUF-модели и сборки `llama-helper`
