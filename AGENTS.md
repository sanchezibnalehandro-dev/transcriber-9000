# Transcriber 9000

## Product

Transcriber 9000 — локальный Windows-транскрибатор с автоматическим локальным AI-отчётом.

Базовый flow:

аудио/видео → локальная транскрипция → TXT/SRT → локальный AI-report → русский Markdown-отчёт.

Это meeting summarizer, а не юридически или аудиторски заверенный протокол.

Не оптимизировать систему под нулевой процент semantic errors ценой полезности, простоты и broad semantic recall.

## Transcription rules

- Source audio/video не удалять, не перемещать и не изменять.
- Русский — основной язык транскрипции.
- Не переводить речь на другой язык.
- TXT — основной результат транскрипции.
- SRT создаётся по выбору пользователя.
- Сохранять исходное имя файла в имени результата.
- Не перезаписывать существующие результаты молча.
- Транскрипция и AI-report работают локально; внешний AI API не является production dependency.

## Source of truth

Перед AI/report-работой прочитать:

`AI_REPORT_STATUS_2026-09-07.md`

Для архитектуры AI/report также обязательно проверить актуальную реализацию:

https://github.com/Zackriya-Solutions/meetily

Особенно:

- `llama-helper/`
- `frontend/src-tauri/src/summary/summary_engine/`
- `frontend/src-tauri/src/summary/processor.rs`
- `frontend/src-tauri/src/summary/service.rs`
- `frontend/src-tauri/src/summary/templates/`
- `frontend/src-tauri/templates/`

Не считать старые research-фазы production-направлением, если они противоречат актуальному status.

## Proven foundation

Сохранять без конкретной технической причины:

`Python → llama-helper → JSONL → llama.cpp → local GGUF`

Также уже доказаны/полезны:

- CUDA;
- CPU fallback;
- long-lived helper/model lifecycle;
- context budgeting;
- gap-free Unicode chunking;
- no-overwrite;
- fail on corrupted machine output;
- external report templates;
- portable PyInstaller onedir flow;
- frozen worker dispatch;
- downloadable local report models via static catalog.

AI/report-логику не смешивать с `transcriber_core.py`.

Локальный production path не должен требовать Ollama или внешний AI API.

## Model policy

Production recommendation:

`Qwen 3.5 9B Q4_K_M`

Lightweight alternative:

`Qwen 3.5 4B Q4_K_M`

4B требует меньше ресурсов, но имеет более низкое semantic quality и не является равнозначным production-quality candidate.

Любая новая production model должна иметь:

- рабочий llama.cpp/GGUF path;
- CUDA;
- CPU fallback;
- измеренный artifact size;
- измеренную RAM/VRAM;
- измеренную CUDA latency;
- измеренную CPU latency.

## Architecture

Начинать с самого простого решения, подходящего product goal.

Не восстанавливать автоматически:

- EvidenceRecord pipeline;
- evidence-only report;
- Draft→Verify;
- Hybrid;
- B/C targeted patch;
- universal semantic extractor;
- ontology/provenance system;
- старые Phase.

Новая abstraction, extractor, verifier или дополнительный LLM pass допустимы только при конкретной пользовательски существенной причине.

Не превращать каждую локальную narrative-неточность в повод для новой architecture.

## Quality

Deterministic tests проверяют code contracts, но не доказывают качество AI-отчёта.

Качество оценивается на реальных транскрипциях.

Приоритет:

- broad semantic recall;
- useful Russian report;
- readable structure;
- отсутствие glaring invented decisions/actions/owners/deadlines/numbers;
- practical latency;
- число LLM calls;
- CPU/GPU viability.

Critical/material failures:

- выдуманное принятое решение;
- выдуманная задача;
- выдуманный исполнитель;
- выдуманный срок;
- выдуманная currency/unit/duration;
- существенная неверная сумма или numeric fact;
- неподдержанный выбранный вариант;
- opposite-to-source material fact;
- существенная потеря основного содержания;
- технически неполный source coverage.

Локальная attribution/relation-неточность сама по себе не обязана уничтожать architecture,
если не создаёт существенную ложную договорённость или факт.

Не overfit production prompt под wording acceptance fixtures.

## Workflow

Для substantial report architecture change:

1. inspect;
2. предложить короткий plan;
3. дождаться approval;
4. implement approved plan.

После approval не перепланировать задачу без новой причины.

Обычные implementation bugs исправлять и прогонять tests.

Если real acceptance показывает material quality failure:
сначала зафиксировать failure;
не запускать автоматически новую цепочку architecture/model/prompt experiments.

Первичное acceptance нового candidate:

- один SHORT real run;
- один LONG real run.

Повторные identical runs — только для конкретной проверки stochastic instability / stability.

Не commit/push без явного запроса пользователя.
Research-код не удалять автоматически.
