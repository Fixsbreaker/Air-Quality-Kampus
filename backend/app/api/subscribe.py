"""Подписки Telegram-бота: POST /api/subscribe, POST /api/unsubscribe."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import require_admin
from app.locations import LOCATIONS_BY_CODE
from app.models import User
from app.schemas import SubscribeIn, SubscribeOut, SubscriberOut, UnsubscribeOut

router = APIRouter(prefix="/api", tags=["Подписки"])


@router.post(
    "/subscribe",
    response_model=SubscribeOut,
    status_code=status.HTTP_200_OK,
    summary="Подписаться на уведомления",
    description=(
        "Идемпотентная операция: повторный вызов с тем же tg_id обновляет "
        "порог и локацию, а не создаёт дубликат."
    ),
)
def subscribe(payload: SubscribeIn, db: Annotated[Session, Depends(get_db)]) -> SubscribeOut:
    if payload.location not in LOCATIONS_BY_CODE:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Неизвестная локация '{payload.location}'",
        )

    user = db.scalars(select(User).where(User.tg_id == payload.tg_id)).first()
    created = user is None

    if user is None:
        user = User(tg_id=payload.tg_id)
        db.add(user)

    user.threshold_aqi = payload.threshold_aqi
    user.location = payload.location
    user.lang = payload.lang
    user.subscribed = True

    db.commit()
    db.refresh(user)

    return SubscribeOut(
        tg_id=user.tg_id,
        threshold_aqi=user.threshold_aqi,
        location=user.location,
        subscribed=user.subscribed,
        created=created,
    )


@router.post(
    "/unsubscribe",
    response_model=UnsubscribeOut,
    summary="Отписаться от уведомлений",
    description="Запись не удаляется — снимается только флаг subscribed.",
)
def unsubscribe(tg_id: int, db: Annotated[Session, Depends(get_db)]) -> UnsubscribeOut:
    user = db.scalars(select(User).where(User.tg_id == tg_id)).first()
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Подписка не найдена")

    user.subscribed = False
    db.commit()
    return UnsubscribeOut(tg_id=tg_id, subscribed=False)


@router.get(
    "/subscribers",
    response_model=list[SubscriberOut],
    dependencies=[Depends(require_admin)],
    summary="Список активных подписчиков (служебный)",
    description="Используется рассыльщиком бота. Требует заголовок X-Admin-Token.",
)
def list_subscribers(db: Annotated[Session, Depends(get_db)]) -> list[SubscriberOut]:
    rows = db.scalars(select(User).where(User.subscribed.is_(True)).order_by(User.id)).all()
    return [SubscriberOut.model_validate(row) for row in rows]
