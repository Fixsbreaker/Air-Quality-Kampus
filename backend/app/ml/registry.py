"""Реестр моделей: сохранение артефактов и указатель на активную версию.

Модель кладётся в MODEL_DIR как <version>.joblib, рядом пишется <version>.json
с метриками. Файл active.json содержит имя версии, которую использует
боевой прогноз. Откат к предыдущей модели — это правка одной строки в
active.json, без пересборки образа.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import joblib

from app.config import settings

logger = logging.getLogger(__name__)

ACTIVE_POINTER = "active.json"


@dataclass
class ModelMetadata:
    version: str
    algorithm: str
    trained_at: str
    rows_used: int
    horizons: list[int]
    feature_columns: list[str]
    metrics: dict[str, Any] = field(default_factory=dict)
    baseline_metrics: dict[str, Any] = field(default_factory=dict)
    notes: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def model_dir() -> Path:
    path = Path(settings.model_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


def new_version(algorithm: str) -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    return f"{algorithm}-{stamp}"


def save_model(model: Any, metadata: ModelMetadata, *, activate: bool = True) -> Path:
    directory = model_dir()
    artifact = directory / f"{metadata.version}.joblib"
    joblib.dump(model, artifact)

    meta_path = directory / f"{metadata.version}.json"
    meta_path.write_text(
        json.dumps(metadata.as_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
    )

    if activate:
        set_active(metadata.version)

    logger.info("Модель сохранена: %s", artifact)
    return artifact


def set_active(version: str) -> None:
    (model_dir() / ACTIVE_POINTER).write_text(
        json.dumps({"active_version": version}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def active_version() -> str | None:
    pointer = model_dir() / ACTIVE_POINTER
    if not pointer.exists():
        return None
    try:
        return json.loads(pointer.read_text(encoding="utf-8")).get("active_version")
    except (ValueError, OSError) as exc:  # pragma: no cover - повреждённый файл
        logger.error("Не удалось прочитать %s: %s", pointer, exc)
        return None


def load_active() -> tuple[Any, ModelMetadata]:
    version = active_version()
    if not version:
        raise FileNotFoundError(
            "Активная модель не найдена. Сначала выполните обучение: python -m scripts.train"
        )
    return load_version(version)


def load_version(version: str) -> tuple[Any, ModelMetadata]:
    directory = model_dir()
    artifact = directory / f"{version}.joblib"
    meta_path = directory / f"{version}.json"

    if not artifact.exists():
        raise FileNotFoundError(f"Артефакт модели не найден: {artifact}")

    model = joblib.load(artifact)
    raw = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    metadata = ModelMetadata(
        version=raw.get("version", version),
        algorithm=raw.get("algorithm", "unknown"),
        trained_at=raw.get("trained_at", ""),
        rows_used=raw.get("rows_used", 0),
        horizons=raw.get("horizons", []),
        feature_columns=raw.get("feature_columns", []),
        metrics=raw.get("metrics", {}),
        baseline_metrics=raw.get("baseline_metrics", {}),
        notes=raw.get("notes", ""),
    )
    return model, metadata


def list_versions() -> list[str]:
    return sorted(path.stem for path in model_dir().glob("*.joblib"))
