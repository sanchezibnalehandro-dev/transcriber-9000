from __future__ import annotations

import hashlib
import json
import os
import shutil
import threading
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from runtime_paths import (
    REPORT_MODEL_CATALOG_PATH,
    report_model_settings_path,
    report_models_directory,
)


DOWNLOAD_CHUNK_BYTES = 4 * 1024 * 1024
MINIMUM_FREE_SPACE_RESERVE_BYTES = 512 * 1024 * 1024


class ReportModelError(Exception):
    """A local model operation that can be shown to the user."""


class ReportModelDownloadCancelled(ReportModelError):
    pass


@dataclass(frozen=True)
class ReportModel:
    model_id: str
    name: str
    badge: str
    description: str
    quality_note: str
    repository: str
    revision: str
    url: str
    filename: str
    size_bytes: int
    sha256: str


@dataclass(frozen=True)
class ReportModelStatus:
    model: ReportModel
    path: Path
    state: str
    bytes_count: int
    active: bool

    @property
    def installed(self) -> bool:
        return self.state == "installed"


ProgressCallback = Callable[[int, int], None]


def load_catalog(path: Path = REPORT_MODEL_CATALOG_PATH) -> tuple[ReportModel, ...]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ReportModelError(f"Не удалось прочитать каталог AI-моделей: {error}") from error
    if payload.get("schema_version") != 1 or not isinstance(payload.get("models"), list):
        raise ReportModelError("Каталог AI-моделей имеет неподдерживаемый формат")

    models: list[ReportModel] = []
    seen_ids: set[str] = set()
    seen_filenames: set[str] = set()
    for value in payload["models"]:
        try:
            model = ReportModel(
                model_id=str(value["id"]),
                name=str(value["name"]),
                badge=str(value["badge"]),
                description=str(value["description"]),
                quality_note=str(value["quality_note"]),
                repository=str(value["repository"]),
                revision=str(value["revision"]),
                url=str(value["url"]),
                filename=str(value["filename"]),
                size_bytes=int(value["size_bytes"]),
                sha256=str(value["sha256"]).casefold(),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise ReportModelError(f"Некорректная запись в каталоге AI-моделей: {error}") from error
        if not model.model_id or model.model_id in seen_ids:
            raise ReportModelError(f"Повторяющийся ID AI-модели: {model.model_id}")
        if not model.filename.lower().endswith(".gguf") or Path(model.filename).name != model.filename:
            raise ReportModelError(f"Некорректное имя GGUF-файла: {model.filename}")
        if model.filename.casefold() in seen_filenames:
            raise ReportModelError(f"Повторяющееся имя GGUF-файла: {model.filename}")
        if model.size_bytes <= 0 or len(model.sha256) != 64:
            raise ReportModelError(f"Некорректные size/hash для AI-модели: {model.model_id}")
        if model.revision not in model.url:
            raise ReportModelError(f"URL AI-модели не закреплён на revision: {model.model_id}")
        seen_ids.add(model.model_id)
        seen_filenames.add(model.filename.casefold())
        models.append(model)
    if len(models) != 2:
        raise ReportModelError("Milestone A поддерживает ровно две AI-модели")
    return tuple(models)


class ReportModelManager:
    def __init__(
        self,
        *,
        catalog_path: Path = REPORT_MODEL_CATALOG_PATH,
        models_dir: Path | None = None,
        settings_path: Path | None = None,
    ) -> None:
        self.catalog_path = Path(catalog_path)
        self.models_dir = Path(models_dir) if models_dir is not None else report_models_directory()
        self.settings_path = (
            Path(settings_path) if settings_path is not None else report_model_settings_path()
        )
        self.models = load_catalog(self.catalog_path)
        self._by_id = {model.model_id: model for model in self.models}
        self._settings_lock = threading.Lock()

    def model(self, model_id: str) -> ReportModel:
        try:
            return self._by_id[model_id]
        except KeyError as error:
            raise ReportModelError(f"Неизвестная AI-модель: {model_id}") from error

    def model_path(self, model_id: str) -> Path:
        return self.models_dir / self.model(model_id).filename

    def part_path(self, model_id: str) -> Path:
        return self.model_path(model_id).with_name(self.model(model_id).filename + ".part")

    def _read_settings(self) -> dict:
        try:
            value = json.loads(self.settings_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {"schema_version": 1, "active_report_model_id": None, "validated_models": {}}
        except (OSError, json.JSONDecodeError):
            return {"schema_version": 1, "active_report_model_id": None, "validated_models": {}}
        if not isinstance(value, dict):
            return {"schema_version": 1, "active_report_model_id": None, "validated_models": {}}
        value.setdefault("schema_version", 1)
        value.setdefault("active_report_model_id", None)
        if not isinstance(value.get("validated_models"), dict):
            value["validated_models"] = {}
        return value

    def _write_settings(self, settings: dict) -> None:
        self.settings_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.settings_path.with_name(self.settings_path.name + ".tmp")
        temporary.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, self.settings_path)

    def _validation_record_matches(self, model: ReportModel, path: Path, settings: dict) -> bool:
        record = settings.get("validated_models", {}).get(model.model_id)
        if not isinstance(record, dict):
            return False
        try:
            stat = path.stat()
        except OSError:
            return False
        return (
            record.get("sha256") == model.sha256
            and record.get("size_bytes") == model.size_bytes
            and record.get("mtime_ns") == stat.st_mtime_ns
            and stat.st_size == model.size_bytes
        )

    def status(self, model_id: str) -> ReportModelStatus:
        model = self.model(model_id)
        path = self.model_path(model_id)
        settings = self._read_settings()
        try:
            bytes_count = path.stat().st_size
        except OSError:
            bytes_count = 0
        if not path.exists():
            state = "not_installed"
        elif bytes_count != model.size_bytes:
            state = "corrupted"
        elif self._validation_record_matches(model, path, settings):
            state = "installed"
        else:
            state = "unverified"
        return ReportModelStatus(
            model=model,
            path=path,
            state=state,
            bytes_count=bytes_count,
            active=state == "installed" and settings.get("active_report_model_id") == model.model_id,
        )

    def statuses(self) -> tuple[ReportModelStatus, ...]:
        return tuple(self.status(model.model_id) for model in self.models)

    def active_model_id(self) -> str | None:
        model_id = self._read_settings().get("active_report_model_id")
        if not isinstance(model_id, str) or model_id not in self._by_id:
            return None
        return model_id if self.status(model_id).installed else None

    def active_model_path(self) -> Path | None:
        model_id = self.active_model_id()
        return self.model_path(model_id).resolve() if model_id is not None else None

    def select(self, model_id: str) -> Path:
        status = self.status(model_id)
        if not status.installed:
            raise ReportModelError("Сначала скачайте и проверьте выбранную AI-модель")
        with self._settings_lock:
            settings = self._read_settings()
            settings["active_report_model_id"] = model_id
            self._write_settings(settings)
        return status.path.resolve()

    def _record_validation(self, model: ReportModel, path: Path) -> None:
        stat = path.stat()
        with self._settings_lock:
            settings = self._read_settings()
            settings["validated_models"][model.model_id] = {
                "sha256": model.sha256,
                "size_bytes": model.size_bytes,
                "mtime_ns": stat.st_mtime_ns,
            }
            if settings.get("active_report_model_id") not in self._by_id:
                settings["active_report_model_id"] = None
            self._write_settings(settings)

    def verify(self, model_id: str, progress: ProgressCallback | None = None) -> Path:
        model = self.model(model_id)
        path = self.model_path(model_id)
        try:
            size = path.stat().st_size
        except OSError as error:
            raise ReportModelError(f"GGUF-файл не найден: {path}") from error
        if size != model.size_bytes:
            raise ReportModelError(
                f"Размер GGUF не совпадает: ожидалось {model.size_bytes}, получено {size} bytes"
            )
        digest = hashlib.sha256()
        done = 0
        with path.open("rb") as source:
            while chunk := source.read(DOWNLOAD_CHUNK_BYTES):
                digest.update(chunk)
                done += len(chunk)
                if progress is not None:
                    progress(done, model.size_bytes)
        if digest.hexdigest().casefold() != model.sha256:
            raise ReportModelError("SHA-256 GGUF-модели не совпадает")
        self._record_validation(model, path)
        return path.resolve()

    def _ensure_disk_space(self, model: ReportModel) -> None:
        self.models_dir.mkdir(parents=True, exist_ok=True)
        required = model.size_bytes + MINIMUM_FREE_SPACE_RESERVE_BYTES
        free = shutil.disk_usage(self.models_dir).free
        if free < required:
            raise ReportModelError(
                "Недостаточно места для AI-модели: "
                f"нужно не менее {required} bytes, свободно {free} bytes"
            )

    def download(
        self,
        model_id: str,
        *,
        progress: ProgressCallback | None = None,
        cancel_event: threading.Event | None = None,
        urlopen: Callable[..., object] = urllib.request.urlopen,
    ) -> Path:
        model = self.model(model_id)
        self._ensure_disk_space(model)
        target = self.model_path(model_id)
        part = self.part_path(model_id)
        if part.exists():
            part.unlink()
        digest = hashlib.sha256()
        done = 0
        request = urllib.request.Request(model.url, headers={"User-Agent": "Transcriber-9000/1"})
        try:
            with urlopen(request, timeout=60) as response, part.open("wb") as output:
                while True:
                    if cancel_event is not None and cancel_event.is_set():
                        raise ReportModelDownloadCancelled("Скачивание отменено")
                    chunk = response.read(DOWNLOAD_CHUNK_BYTES)
                    if not chunk:
                        break
                    output.write(chunk)
                    digest.update(chunk)
                    done += len(chunk)
                    if done > model.size_bytes:
                        raise ReportModelError("Загруженный файл больше ожидаемого размера")
                    if progress is not None:
                        progress(done, model.size_bytes)
                output.flush()
                os.fsync(output.fileno())
            if done != model.size_bytes:
                raise ReportModelError(
                    f"Размер загрузки не совпадает: ожидалось {model.size_bytes}, получено {done} bytes"
                )
            if digest.hexdigest().casefold() != model.sha256:
                raise ReportModelError("SHA-256 загруженной GGUF-модели не совпадает")
            os.replace(part, target)
            self._record_validation(model, target)
            if self.active_model_id() is None:
                self.select(model_id)
            return target.resolve()
        except BaseException:
            try:
                if part.exists():
                    part.unlink()
            except OSError:
                pass
            raise

    def delete(self, model_id: str) -> None:
        model = self.model(model_id)
        target = self.model_path(model_id)
        part = self.part_path(model_id)
        for path in (target, part):
            try:
                path.unlink()
            except FileNotFoundError:
                pass
            except OSError as error:
                raise ReportModelError(f"Не удалось удалить AI-модель: {error}") from error
        with self._settings_lock:
            settings = self._read_settings()
            settings["validated_models"].pop(model.model_id, None)
            if settings.get("active_report_model_id") == model.model_id:
                settings["active_report_model_id"] = None
            self._write_settings(settings)


__all__ = [
    "ReportModel",
    "ReportModelDownloadCancelled",
    "ReportModelError",
    "ReportModelManager",
    "ReportModelStatus",
    "load_catalog",
]
