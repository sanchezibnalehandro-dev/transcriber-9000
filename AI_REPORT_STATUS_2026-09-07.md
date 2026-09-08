# TRANSCRIBER 9000 — AI/REPORT STATUS
## Source of truth as of 2026-09-07

Этот файл фиксирует актуальное состояние AI/report-подсистемы после серии экспериментов 2026-09-06 — 2026-09-07 и итоговое принятие backend v1 production candidate.

Если старые чаты, заметки, планы, Phase или research-код противоречат этому файлу и актуальным project instructions, приоритет у этого файла и актуальных project instructions.

---

## 1. PRODUCT GOAL

Transcriber 9000 должен автоматически превращать обычную транскрипцию обычной человеческой встречи в полезный структурированный русский Markdown-отчёт.

Это meeting summarizer, а не юридически или аудиторски заверенный протокол.

Базовый продукт НЕ требует:
- специального поведения участников встречи;
- ручной разметки решений;
- финального ритуала подведения итогов;
- обязательного подтверждения каждого факта человеком;
- изменения естественного стиля разговора.

Отчёт должен:
- сохранять общий смысл, темы, проблемы, идеи и контекст;
- полезно структурировать разговор;
- корректно передавать существенные решения, предложения, задачи, числа и сроки;
- по возможности сохранять исходную неопределённость;
- не выдумывать существенные детали.

Нулевой процент semantic errors без человеческой проверки не является обещанием продукта.

Локальная неточность пересказа сама по себе не является причиной перепроектировать систему.

Критичны ошибки, существенно меняющие смысл, например:
- выдуманное решение;
- выдуманная задача;
- выдуманный исполнитель;
- выдуманный срок;
- выдуманная сумма/единица;
- неподдержанный выбранный вариант;
- противоположный исходнику существенный факт.

---

## 2. GIT / RESET POINT

Основной исторический branch:

`cleanup/transcriber-9000`

Зафиксированные checkpoints:

- `4a0912af3af52b931b5aa91fa3a1f6a59c42d6c7` — `feat: establish local AI report foundation`
- `035f412f10df06dd906ed4dc39a25bfa691cd8f1` — `chore: ignore local AI runtime assets`
- `b91ba1e1c36c4472803e400bb03308b9c7eb2d3a` — `feat: add evidence-based report pipeline baseline`

Предыдущий экспериментальный checkout исторически находился на:

`b91ba1e1c36c4472803e400bb03308b9c7eb2d3a`

с последующими локальными незакоммиченными AI/report experiments.

Этот checkout следует сохранить как research history и не использовать как чистую основу нового production design.

Чистый checkpoint для нового production design:

`035f412f10df06dd906ed4dc39a25bfa691cd8f1`

Он находится после доказанной local-AI runtime foundation и до evidence-based report architecture.

Backend v1 реализован в отдельной ветке:

`reset/ai-report-2026-09-07`

от reset point `035f412f10df06dd906ed4dc39a25bfa691cd8f1`. Текущая реализация и документация остаются локальными незакоммиченными изменениями; commit/push не выполнялись.

---

## 3. PROVEN RUNTIME FOUNDATION

Рабочая схема:

`Python → llama-helper → JSON Lines → llama.cpp → local GGUF`

Pinned proven runtime:

- `llama-cpp-2 = 0.1.156`
- `llama-cpp-sys-2 = 0.1.156`

Подтверждено:

- CPU execution работает;
- CUDA execution работает;
- RTX 3060 успешно использовалась для full offload Qwen 3.5 4B;
- RTX 3060 успешно использовалась для full offload Qwen 3.5 9B при context 32768 (`34/34` layers);
- один helper/model lifecycle обслуживает несколько generate calls;
- JSONL protocol работает;
- local mode не требует Ollama;
- helper/runtime не является текущей проблемой продукта.

Из старой foundation также полезны:

- context budgeting;
- gap-free Unicode chunking;
- absolute/source offsets там, где они нужны;
- deterministic validation code contracts;
- no-overwrite;
- fail on corrupted machine output;
- external report templates.

Эту foundation без конкретной причины не перепроектировать.

CPU fallback остаётся обязательным product requirement.

---

## 4. MEETILY — ОБЯЗАТЕЛЬНЫЙ ENGINEERING REFERENCE

Repo:

https://github.com/Zackriya-Solutions/meetily

Перед существенным AI/report design необходимо проверять актуальную реализацию Meetily, особенно:

- `llama-helper/`
- `frontend/src-tauri/src/summary/summary_engine/`
- `frontend/src-tauri/src/summary/processor.rs`
- `frontend/src-tauri/src/summary/service.rs`
- `frontend/src-tauri/src/summary/templates/`
- `frontend/src-tauri/templates/`

Полезные доказанные идеи Meetily:

- separate transcription / summary engines;
- local llama-helper;
- llama.cpp + GGUF;
- long-lived model lifecycle;
- external JSON report templates;
- SHORT/LONG routing;
- narrative processing для длинного контекста;
- Markdown result;
- background processing;
- отсутствие обязательной зависимости от Ollama в Built-in AI path.

Meetily является рабочим engineering reference локального meeting summarizer.

Его не нужно копировать механически, но перед созданием новой архитектуры сначала надо понять, как аналогичная проблема решена там.

---

## 5. MODEL STATUS

Исторический baseline:

`Qwen 3.5 4B Q4_K_M`

Она:

- технически работает через текущий llama.cpp runtime;
- работает на CUDA;
- работает на CPU;
- сохраняет широкий semantic recall лучше формальных evidence-only pipelines;
- даёт полезный русский narrative report.

Direct full-transcript 4B candidate сохранил хороший broad recall, но LONG acceptance выявил material semantic defects: усиление proposal/role wording, ложную duration текущей встречи и другие ошибки статуса существенных фактов. Поэтому 4B сохранён как доказанный runtime/quality baseline, но не выбран production model.

Принятая production-модель backend v1:

`Qwen 3.5 9B Q4_K_M`

Pinned artifact:

- repository: `bartowski/Qwen_Qwen3.5-9B-GGUF`;
- revision: `2dcd842c59ea5eb119267064550a7a4c592b16c3`;
- file: `Qwen_Qwen3.5-9B-Q4_K_M.gguf`;
- size: `6169341984` bytes;
- SHA-256: `d784ce9eda1a5a7b51e8f705a9e6310844bf4f173654d115823c775fdea56d43`.

9B принята по совокупности practical report quality и измеренной local viability, а не только по benchmark.

---

## 6. WHAT PREVIOUS RESEARCH SHOWED

### 6.1 Evidence-only pipeline

Evidence-only pipeline технически работал:

- deterministic source binding;
- strict validation;
- exact numeric provenance;
- final report from validated evidence;
- deterministic tests проходили;
- CUDA E2E работал.

Но real acceptance показал потерю broad semantic recall.

Если тема не превращалась в EvidenceRecord, final report её не видел.

Терялись, в частности, широкие темы и контекст встречи.

Вывод:

EvidenceRecord не должен автоматически быть центральной representation production report engine.

---

### 6.2 Draft→Verify / B-C targeted correction

Проверялись:
- critical-first targeted correction;
- Draft→Verify targeted correction;
- Hybrid-подобные варианты.

Они не дали устойчивого production winner.

На LONG known failures не были стабильно устранены, а отдельные варианты добавляли новые critical errors.

Вывод:

- Draft→Verify не продвигать автоматически;
- B/C targeted patch не считать production architecture;
- Hybrid не считать подтверждённым направлением;
- старые Phase не являются roadmap.

---

### 6.3 Direct Qwen 3.5 4B SHORT

Direct SHORT path:

`full transcript → conservative Russian prompt + template → Qwen 4B → Markdown`

Технически работал хорошо:
- один основной LLM call;
- хороший broad semantic recall;
- useful Russian narrative output;
- быстрый CUDA execution.

Повторяемые semantic defects:
- actor/recipient/object relation distortions;
- attribution distortions;
- иногда усиление uncertainty;
- иногда normalization proposal/idea into stronger wording.

При этом широкие темы встречи сохранялись хорошо.

---

### 6.4 Prompt-only semantic preservation

Prompt усиливался правилами:
- preserve epistemic status;
- preserve speech-act status;
- preserve actor/recipient/object relations;
- conservative fallback.

Результат:
- risk/possibility preservation улучшился;
- proposal/decision distinction улучшился;
- broad recall сохранился;
- actor/recipient/object distortions стабильно не исчезли.

Вывод:

prompt-only tuning не решает все relation errors.

Не продолжать бесконечный fixture-specific prompt tuning.

---

### 6.5 Phi-4-mini 3.8B spike

Проверялась Microsoft Phi-4-mini-instruct 3.8B Q4_K_M.

Технически:
- current pinned runtime её загрузил;
- CUDA работала;
- native Phi chat formatting работал;
- модель была заметно быстрее Qwen 4B.

Semantic result:
- broad recall был существенно хуже;
- терялись Confluence/Jira и широкий контекст;
- появлялись unsupported next actions;
- конкретные relations часто не исправлялись, а просто исчезали.

Вывод:

Phi-4-mini 3.8B не является production candidate для текущего report use case.

---

### 6.6 Template audit

Проверялось, не является ли `product_meeting.json` основной причиной material semantic failures.

Результат:

- template pressure действительно мог провоцировать некоторые локальные ошибки, особенно в action/question sections у Phi;
- однако главные Qwen relation/attribution failures возникали и в нейтральных sections: summary, context, topics, hypotheses;
- decision/action sections у Qwen часто оставались корректно пустыми.

Verdict:

`TEMPLATE IS NOT THE MAIN CAUSE`

Дальнейший template tuning не является обоснованным основным решением relation problems.

---

### 6.7 Narrative LONG Qwen 4B experiment

Был реализован минимальный Meetily-like LONG candidate:

`gap-free chunks → narrative chunk summaries → optional combine → final report`

Deterministic code contracts прошли.

Real acceptance не прошёл.

Наблюдались material failures:

- proposal → decision;
- обсуждаемые роли → определённая структура;
- добавленная отсутствующая currency;
- число/цена → неподдержанная численность участников;
- `+13 минут` → ложная meeting duration;
- повреждённый ASR-фрагмент → срок;
- условный пример про четверг → scheduled call;
- потеря структуры ranges/alternatives.

Также `<<<END_SUMMARY>>>` оказался ненадёжным техническим marker: модель могла не вернуть marker при нормальной/почти нормальной генерации, из-за чего LONG run fail-closed завершался технической ошибкой.

Вывод:

- текущий narrative LONG Qwen4B candidate не принят;
- END_SUMMARY marker не считать доказанным production guardrail;
- этот FAIL не означает автоматически, что продукту нужен universal evidence/verifier architecture.

---

## 7. MAIN LESSON FROM RESEARCH

Предыдущая разработка местами переоптимизировала semantic purity относительно реального product goal.

В ряде этапов acceptance фактически приближался к требованиям формального протокола/аудита, хотя product contract этого не требует.

Главный практический вывод:

Qwen 4B лучше проявляла себя в задаче:

`прочитать человеческую встречу → написать содержательный отчёт`

чем в длинной цепочке:

`extract → classify → validate IDs → verify → patch → report`

Поэтому новый production design должен снова начинаться с самого простого решения.

Не считать любую локальную semantic неточность доказательством необходимости новой architecture.

---

## 8. PRODUCT ACCEPTANCE RESET

Для v1 требуется хороший практически полезный automatic meeting report.

Не требуется гарантированно безошибочный formal protocol.

### Critical/material FAIL

В первую очередь критичны ошибки, которые создают существенную ложную информацию:

- выдуманное принятое решение;
- выдуманная задача;
- выдуманный исполнитель;
- выдуманный срок;
- выдуманная currency/unit/duration;
- существенная неверная сумма или числовой факт;
- неподдержанный выбранный вариант;
- opposite-to-source material fact;
- существенная потеря основного содержания встречи;
- технически неполный source coverage.

### Known/minor defect

Локальная narrative attribution/relation неточность фиксируется как defect, но сама по себе не обязана уничтожать report architecture, если она:

- не создаёт ложное решение;
- не создаёт ложную задачу;
- не создаёт ложного владельца/срок/число;
- не меняет существенный product meaning;
- не делает отчёт практически непригодным.

Не оптимизировать product pipeline ради формального нуля мелких замечаний ценой broad semantic recall и сложности.

---

## 9. ACCEPTED BACKEND V1

Итоговое product decision:

- model: `Qwen 3.5 9B Q4_K_M`;
- route: `direct full transcript`;
- context: `32768`;
- LLM calls: `1`;
- CUDA: primary path;
- CPU: supported degraded fallback;
- output: validated Russian Markdown;
- overflow: fail-closed без truncation и output-файла;
- existing output: no-overwrite.

Production flow:

`TXT → report_pipeline.py → llama-helper/JSONL → llama.cpp → local GGUF → validated Markdown`

Для v1 не требуются chunking, EvidenceRecord, verifier, extractor, второй semantic pass или внешний AI API.

---

## 10. REPORT ARCHITECTURE PRINCIPLE

Для SHORT и LONG backend v1 использует один и тот же direct route:

`full transcript + external template → one local LLM call → Markdown validation → exclusive write`

32K context practically validated на текущих acceptance fixtures. При overflow pipeline завершается fail-closed без truncation, partial report или автоматического перехода к chunking.

Один LLM call является свойством direct backend v1, а не вечным архитектурным законом.

Не добавлять:
- extractor;
- verifier;
- evidence schema;
- ontology;
- patch pipeline;
- дополнительный semantic LLM pass;
- новую abstraction

только потому, что модель иногда ошибается.

Новая сложность в будущих версиях допустима только если:
1. существует повторяемая пользовательски существенная ошибка;
2. она реально делает продукт непригодным;
3. более простое решение не работает;
4. новая механика имеет понятную цену и проверяемый выигрыш.

---

## 11. REAL ACCEPTANCE FIXTURES

### SHORT

`video_2026-07-30_11-22-46.txt`

Проверять прежде всего:
- broad semantic recall;
- useful Russian report;
- employee skills;
- security;
- opacity of tools;
- knowledge base;
- product/technical context;
- Confluence/Jira;
- отсутствие glaring invented decisions/actions/numbers.

### LONG

`Встреча в Телемосте 10.08.26 12-03-14 — запись.txt`

Known diagnostic traps:
- proposal vs decision;
- roles vs headcount;
- tentative 2023;
- `+13 minutes` vs meeting duration;
- numeric alternatives;
- group-size ranges;
- conditional example vs scheduled action.

Эти traps являются diagnostic evidence.

Они не должны автоматически превращаться в fixture-specific production prompt.

---

## 12. ACCEPTANCE PROCESS

Deterministic tests проверяют code contracts.

Они не доказывают качество AI-отчёта.

Первичное real acceptance нового candidate:

- один реальный SHORT run;
- один реальный LONG run.

Оценивать:
- broad semantic recall;
- практическую полезность;
- material unsupported claims;
- readability;
- total time;
- LLM calls;
- CUDA viability;
- CPU viability.

Не выполнять автоматически по три identical runs после каждого prompt/model change.

Повторные runs нужны только если требуется проверить:
- stochastic instability;
- production stability;
- конкретный повторяемый failure.

Если real acceptance показывает material product-quality failure:
- сначала зафиксировать его;
- не запускать автоматически новую цепочку experiments.

### Backend v1 acceptance result

- deterministic Python suite: `95/95 PASS`;
- Qwen 4B SHORT: хороший broad recall, minor relation/attribution defects;
- Qwen 4B LONG: production FAIL по material semantic defects;
- Qwen 9B technical feasibility: PASS, context 32768, CUDA offload `34/34`;
- Qwen 9B LONG CUDA: принят как semantic PASS for v1 с known non-blocking defect;
- Qwen 9B CPU viability: PASS;
- дополнительные model/prompt/architecture experiments не требуются.

Known v1 limitation: модель может изредка усиливать proposal или uncertain participation до более определённой формулировки, особенно внутри `Принятые решения`. В принятом LONG результате спорное участие Аиды одновременно осталось явно отмечено как open и `Требует уточнения`, поэтому section-level misclassification принято как non-blocking defect. Нулевое число semantic errors не гарантируется.

---

## 13. CPU / GPU

CUDA — основной acceleration path. CPU поддерживается как заметно более медленный degraded fallback; жёсткий CPU latency threshold не вводится.

Измерения Qwen 3.5 9B Q4_K_M на LONG fixture, context 32768:

### CUDA

- full offload: `34/34` layers;
- model load: `3.39 s`;
- prompt processing: `6.46 s`;
- generation: `45.54 s`;
- total workflow: `56.30 s`;
- tokens: `10108 → 2112`;
- observed GPU total peak: `9349 MiB` при baseline `2564 MiB`, estimated delta `6785 MiB`;
- helper working set: около `5.61 GiB`.

GPU memory — системное измерение Windows WDDM, а не точная per-process VRAM.

### CPU degraded fallback

- `gpu_layers=0`;
- model load: `1.15 s`;
- prompt processing: `30.90 s` (`327.14 token/s`);
- generation: `497.59 s` (`3.92 token/s`);
- total workflow: `530.62 s` (`≈8:51`);
- tokens: `10108 → 1951`;
- peak helper working set: `6.63 GiB`;
- generation and Markdown validation: PASS.

---

## 14. OPTIONAL “ТРЕБУЕТ УТОЧНЕНИЯ”

Допустим отдельный report section вида:

`Требует уточнения`

Его назначение:
- показать важные места, где status/owner/deadline/selected option действительно неясны;
- помочь пользователю быстро проверить спорный момент.

Этот section:
- не является обязательным approval flow;
- не должен блокировать создание отчёта;
- не является заменой semantic accuracy;
- не требует отдельной verifier architecture сам по себе.

---

## 15. DEVELOPMENT RULES

Для substantial report architecture change:
- сначала короткий plan;
- затем approval;
- затем implementation.

После утверждённого plan:
не перепланировать задачу без новой причины.

Исправлять обычные implementation bugs до прохождения deterministic tests.

Не commit/push без явного запроса.

Research-код не удалять автоматически.

Не продолжать старые Phase по инерции.

Предпочитать законченный простой продукт бесконечному исследованию идеальной semantic accuracy.

---

## 16. CURRENT STATUS

AI/report backend v1 production candidate принят.

Зафиксировано:

- production model: `Qwen 3.5 9B Q4_K_M`;
- direct full-transcript route;
- context 32768;
- one LLM call;
- CUDA primary;
- CPU degraded fallback;
- deterministic contracts `95/95 PASS`;
- LONG semantic acceptance принят с известным non-blocking proposal/decision classification defect.

Минимальная GUI integration реализована: после успешной TXT-транскрипции готовый CUDA path запускает `report_pipeline.py` автоматически в отдельном процессе; CPU доступен только как явный degraded fallback. `transcriber_core.py` и AI/report backend contracts не изменялись. Новая semantic/model acceptance не запускалась и для принятия backend v1 не требуется.
