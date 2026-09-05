from __future__ import annotations

import json
import re
import tempfile
import unittest
from pathlib import Path

from report_pipeline import (
    ReportPipelineError,
    ReportRuntimeSettings,
    SourceSegment,
    TranscriptDocument,
    parse_bound_universal_evidence,
    parse_report_template,
    run_report_with_lifecycle,
    split_source_segments,
    write_new_report,
)
from report_engine import TextChunk


def template() -> object:
    return parse_report_template(
        {
            "schema_version": 1,
            "id": "test-report",
            "title": "Тестовый отчёт",
            "language": "ru",
            "rules": ["Пиши только по evidence records."],
            "sections": [
                {"id": "summary", "heading": "Краткий итог", "instruction": "Передай главное."},
                {"id": "decisions", "heading": "Решения", "instruction": "Укажи решения и предложения."},
            ],
        }
    )


class FakeClient:
    def __init__(self, *, oversized_evidence: bool = False, unknown_selection_id: bool = False) -> None:
        self._is_running = False
        self.started = 0
        self.pings = 0
        self.shutdowns = 0
        self.prompts: list[str] = []
        self.oversized_evidence = oversized_evidence
        self.unknown_selection_id = unknown_selection_id

    @property
    def is_running(self) -> bool:
        return self._is_running

    def start(self) -> None:
        self.started += 1
        self._is_running = True

    def ping(self, timeout: float) -> None:
        self.pings += 1
        self.assert_running()

    def shutdown(self, timeout: float) -> None:
        self.shutdowns += 1
        self._is_running = False

    def assert_running(self) -> None:
        if not self._is_running:
            raise AssertionError("client was not running")

    @staticmethod
    def _tagged_json(prompt: str, tag: str) -> object:
        match = re.search(rf"<{tag}>\n(?P<body>.*?)\n</{tag}>", prompt, flags=re.DOTALL)
        if match is None:
            raise AssertionError(f"missing <{tag}> payload")
        return json.loads(match.group("body"))

    def generate(self, prompt: str, **kwargs: object) -> str:
        self.assert_running()
        self.prompts.append(prompt)
        if "<untrusted_numeric_candidates>" in prompt:
            payload = self._tagged_json(prompt, "untrusted_numeric_candidates")
            assert isinstance(payload, list)
            records = [
                {
                    "candidate_id": item["candidate_id"],
                    "relevant": True,
                    "text": f"Числовой факт: {item['raw']}",
                    "explicitness": "explicit",
                    "temporal_kind": "number",
                    "confidence": None,
                }
                for item in payload
            ]
            return json.dumps({"schema_version": 1, "records": records}, ensure_ascii=False)
        if "Ты отбираешь записи доказательств" in prompt:
            payload = self._tagged_json(prompt, "validated_evidence_records")
            assert isinstance(payload, dict)
            if self.unknown_selection_id:
                return '{"schema_version":1,"ids":["invented-id"]}'
            return json.dumps({"schema_version": 1, "ids": [payload["records"][0]["id"]]}, ensure_ascii=False)
        if "<untrusted_transcript>" in prompt:
            if "Ты извлекаешь только решения и предложения" in prompt:
                if "Предлагаю запустить пилот." in prompt:
                    records = [
                        {
                            "id": "r1",
                            "type": "proposal",
                            "text": "Предложен запуск пилота.",
                            "explicitness": "explicit",
                            "source_quote": "Предлагаю запустить пилот.",
                            "confidence": None,
                        }
                    ]
                else:
                    records = []
                return json.dumps({"schema_version": 1, "records": records}, ensure_ascii=False)
            source_id_match = re.search(r"\[(s\d{3})\]", prompt)
            if source_id_match is None:
                raise AssertionError("bound universal extraction did not include source IDs")
            source_id = source_id_match.group(1)
            if self.oversized_evidence:
                records = [
                    {
                        "id": f"r{index}",
                        "type": "fact",
                        "text": ("Содержательный факт " * 150) + str(index),
                        "explicitness": "explicit",
                        "source_ids": [source_id],
                        "confidence": None,
                    }
                    for index in range(30)
                ]
            elif "Команда обсудила запуск продукта." in prompt:
                records = [
                    {
                        "id": "r1",
                        "type": "fact",
                        "text": "Команда обсудила запуск продукта.",
                        "explicitness": "explicit",
                        "source_ids": [source_id],
                        "confidence": None,
                    }
                ]
            else:
                records = []
            return json.dumps({"schema_version": 1, "records": records}, ensure_ascii=False)
        if "<sources>" in prompt:
            source_id_match = re.search(r"\[(s\d{3})\]", prompt)
            if source_id_match is None:
                raise AssertionError("bound universal extraction did not include source IDs")
            source_id = source_id_match.group(1)
            if self.oversized_evidence:
                records = [
                    {
                        "id": f"r{index}",
                        "type": "fact",
                        "text": ("Содержательный факт " * 150) + str(index),
                        "explicitness": "explicit",
                        "source_ids": [source_id],
                        "confidence": None,
                    }
                    for index in range(30)
                ]
            elif "Команда обсудила запуск продукта." in prompt:
                records = [
                    {
                        "id": "r1",
                        "type": "fact",
                        "text": "Команда обсудила запуск продукта.",
                        "explicitness": "explicit",
                        "source_ids": [source_id],
                        "confidence": None,
                    }
                ]
            else:
                records = []
            return json.dumps({"schema_version": 1, "records": records}, ensure_ascii=False)
        return (
            "# Тестовый отчёт\n\n"
            "## Краткий итог\n\nОбсуждены подтверждённые evidence records.\n\n"
            "## Решения\n\nПредложение сохранено как предложение."
        )


class ReportPipelineTests(unittest.TestCase):
    @staticmethod
    def _bound_record(source_id: str, *, explicitness: str = "explicit") -> str:
        return json.dumps(
            {
                "schema_version": 1,
                "records": [
                    {
                        "id": "r1",
                        "type": "proposal",
                        "text": "Содержимое записи определено моделью.",
                        "explicitness": explicitness,
                        "source_ids": [source_id],
                        "confidence": None,
                    }
                ],
            },
            ensure_ascii=False,
        )

    def test_bound_source_id_restores_exact_text_and_absolute_locator(self) -> None:
        transcript = "Первое предложение. Второе предложение?"
        chunk = TextChunk(0, 0, len(transcript), transcript)
        segments = split_source_segments(chunk)
        evidence = parse_bound_universal_evidence(
            self._bound_record("s001"), transcript=transcript, chunk=chunk, segments=segments
        )[0]
        self.assertEqual(evidence.provenance[0].source_quote, "Первое предложение.")
        self.assertEqual(
            (evidence.provenance[0].locator.start, evidence.provenance[0].locator.end),
            (0, len("Первое предложение.")),
        )

    def test_bound_source_rejects_unknown_id(self) -> None:
        transcript = "Первое предложение."
        chunk = TextChunk(0, 0, len(transcript), transcript)
        with self.assertRaisesRegex(Exception, "unknown source_id"):
            parse_bound_universal_evidence(
                self._bound_record("s999"), transcript=transcript, chunk=chunk, segments=split_source_segments(chunk)
            )

    def test_bound_source_never_accepts_model_source_quote(self) -> None:
        transcript = "Первое предложение."
        chunk = TextChunk(0, 0, len(transcript), transcript)
        raw = json.loads(self._bound_record("s001"))
        raw["records"][0]["source_quote"] = "Подменённая цитата"
        with self.assertRaisesRegex(Exception, "invalid fields"):
            parse_bound_universal_evidence(
                json.dumps(raw, ensure_ascii=False), transcript=transcript, chunk=chunk, segments=split_source_segments(chunk)
            )

    def test_uncertain_source_cannot_be_explicit(self) -> None:
        transcript = "Возможно, запустим пилот."
        chunk = TextChunk(0, 0, len(transcript), transcript)
        with self.assertRaisesRegex(Exception, "uncertainty marker"):
            parse_bound_universal_evidence(
                self._bound_record("s001"), transcript=transcript, chunk=chunk, segments=split_source_segments(chunk)
            )

    def test_ordinary_source_can_remain_explicit(self) -> None:
        transcript = "Запускаем пилот в понедельник."
        chunk = TextChunk(0, 0, len(transcript), transcript)
        evidence = parse_bound_universal_evidence(
            self._bound_record("s001"), transcript=transcript, chunk=chunk, segments=split_source_segments(chunk)
        )[0]
        self.assertEqual(evidence.explicitness.value, "explicit")

    def test_evidence_pipeline_uses_one_lifecycle_and_preserves_numeric_provenance(self) -> None:
        client = FakeClient()
        result = run_report_with_lifecycle(
            client,
            TranscriptDocument("Команда обсудила запуск продукта. Предлагаю запустить пилот. Бюджет 120 рублей."),
            template(),
            ReportRuntimeSettings(),
        )
        self.assertEqual((client.started, client.pings, client.shutdowns), (1, 1, 1))
        self.assertEqual(result.llm_passes, 4)
        self.assertIsNone(result.selected_evidence_ids)
        numeric = next(record for record in result.evidence if record.record_type.value == "numbers_dates")
        self.assertEqual(numeric.provenance[0].source_quote, "120")
        self.assertIn("## Решения", result.markdown)

    def test_final_overflow_uses_id_only_selection_and_original_records(self) -> None:
        client = FakeClient(oversized_evidence=True)
        result = run_report_with_lifecycle(
            client,
            TranscriptDocument("ФАКТ."),
            template(),
            ReportRuntimeSettings(),
        )
        self.assertGreater(result.selection_llm_passes, 0)
        self.assertLess(len(result.evidence), 30)
        self.assertEqual(result.selected_evidence_ids, tuple(record.record_id for record in result.evidence))
        self.assertTrue(all("Содержательный факт" in record.text for record in result.evidence))
        self.assertTrue(result.final_budget.fits)
        selection_prompts = [prompt for prompt in client.prompts if "Ты отбираешь записи доказательств" in prompt]
        self.assertTrue(selection_prompts)
        self.assertIn('"e0001"', selection_prompts[0])

    def test_unknown_selection_id_fails_closed(self) -> None:
        client = FakeClient(oversized_evidence=True, unknown_selection_id=True)
        with self.assertRaisesRegex(ReportPipelineError, "unknown|неизвестные"):
            run_report_with_lifecycle(
                client,
                TranscriptDocument("ФАКТ."),
                template(),
                ReportRuntimeSettings(),
            )
        self.assertEqual(client.shutdowns, 1)

    def test_large_transcript_is_split_without_gaps(self) -> None:
        text = ("содержательная фраза. " * 4_000).strip()
        from report_pipeline import make_transcript_chunks
        from report_engine import (
            build_focused_decision_extraction_prompt,
            build_structured_extraction_prompt,
            estimate_tokens,
            request_fits_context,
        )

        settings = ReportRuntimeSettings()
        chunks = make_transcript_chunks(text, settings)
        self.assertGreater(len(chunks), 1)
        self.assertEqual(chunks[0].start, 0)
        self.assertEqual(chunks[-1].end, len(text))
        self.assertTrue(all(left.end >= right.start for left, right in zip(chunks, chunks[1:])))
        self.assertTrue(all(estimate_tokens(chunk.text) <= settings.extraction_chunk_max_tokens for chunk in chunks))
        for chunk in chunks:
            for builder in (build_structured_extraction_prompt, build_focused_decision_extraction_prompt):
                self.assertTrue(
                    request_fits_context(
                        builder(text, source_start=chunk.start, source_end=chunk.end, strict_json=True),
                        context_size=settings.context_size,
                        output_reserve=settings.extraction_max_tokens,
                        safety_reserve=settings.extraction_safety_reserve,
                    )
                )

    def test_safe_write_never_overwrites(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "report.md"
            write_new_report(destination, "# Первый")
            with self.assertRaisesRegex(ReportPipelineError, "не будет перезаписан"):
                write_new_report(destination, "# Второй")
            self.assertEqual(destination.read_text(encoding="utf-8"), "# Первый\n")


if __name__ == "__main__":
    unittest.main()
