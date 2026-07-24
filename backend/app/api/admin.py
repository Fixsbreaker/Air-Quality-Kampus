"""Служебные эндпоинты: выгрузка отчёта и история обучений модели."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import require_admin, utcnow
from app.locations import LOCATIONS_BY_CODE
from app.models import ModelRun
from app.schemas import ModelRunOut
from app.services.report import report_filename, stream_measurements_csv

router = APIRouter(prefix="/api/admin", tags=["Администрирование"])

MAX_REPORT_DAYS = 731


@router.get(
    "/report",
    dependencies=[Depends(require_admin)],
    summary="Выгрузка наблюдений в CSV",
    description=(
        "Отчёт для администрации кампуса. Разделитель — точка с запятой "
        "(так файл корректно открывается в Excel с русской локалью). "
        "Требует заголовок X-Admin-Token."
    ),
    responses={200: {"content": {"text/csv": {}}, "description": "CSV-файл с наблюдениями"}},
)
def download_report(
    db: Annotated[Session, Depends(get_db)],
    from_ts: Annotated[datetime | None, Query(alias="from")] = None,
    to_ts: Annotated[datetime | None, Query(alias="to")] = None,
    location: Annotated[str | None, Query()] = None,
) -> StreamingResponse:
    now = utcnow()
    to_ts = to_ts or now
    from_ts = from_ts or (to_ts - timedelta(days=30))

    if from_ts >= to_ts:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Параметр 'from' должен быть раньше 'to'"
        )
    if (to_ts - from_ts) > timedelta(days=MAX_REPORT_DAYS):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Слишком широкий период: максимум {MAX_REPORT_DAYS} дней",
        )
    if location and location not in LOCATIONS_BY_CODE:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail=f"Неизвестная локация '{location}'"
        )

    filename = report_filename(from_ts, to_ts, location)
    return StreamingResponse(
        stream_measurements_csv(db, from_ts, to_ts, location),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get(
    "/models",
    response_model=list[ModelRunOut],
    dependencies=[Depends(require_admin)],
    summary="История обучений модели",
    description="Метрики каждого запуска обучения и сравнение с baseline.",
)
def list_model_runs(db: Annotated[Session, Depends(get_db)]) -> list[ModelRunOut]:
    rows = db.scalars(select(ModelRun).order_by(ModelRun.created_at.desc())).all()
    return [ModelRunOut.model_validate(row) for row in rows]
