"""Pydantic-схемы. Они же формируют документацию Swagger (/docs)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class LocationOut(BaseModel):
    code: str = Field(examples=["main"])
    title: str = Field(examples=["Учебный корпус (Толе би 59)"])
    lat: float = Field(examples=[43.2364])
    lon: float = Field(examples=[76.9457])
    description: str = ""


class RecommendationOut(BaseModel):
    aqi: int = Field(examples=[87])
    category: str = Field(examples=["Умеренно"])
    color: str = Field(examples=["#ffde33"])
    text: str = Field(examples=["Норма; чувствительным людям — сократить нагрузку"])
    outdoor_sport: bool = Field(description="Можно ли проводить занятия спортом на улице")
    open_windows: bool = Field(description="Можно ли открывать окна в аудиториях")
    mask_advised: bool = Field(description="Рекомендована ли маска/респиратор")
    sensitive_groups_note: str


class CurrentOut(BaseModel):
    """Текущее состояние воздуха в точке кампуса."""

    location: LocationOut
    ts: datetime = Field(description="Метка времени наблюдения, UTC")
    ts_local: datetime = Field(description="То же время в часовом поясе Алматы")
    source: str = Field(examples=["open-meteo"])
    pm25: float | None
    pm10: float | None
    no2: float | None
    o3: float | None
    aqi: int | None
    aqi_category: str | None
    dominant_pollutant: str | None
    recommendation: RecommendationOut | None
    stale: bool = Field(description="Данные старше 3 часов — источник, вероятно, отстаёт")


class HistoryPoint(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ts: datetime
    pm25: float | None
    pm10: float | None
    aqi: int | None
    aqi_category: str | None


class HistoryOut(BaseModel):
    location: str
    from_ts: datetime
    to_ts: datetime
    count: int
    points: list[HistoryPoint]


class ForecastPointOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    target_ts: datetime
    horizon_h: int
    pm25_pred: float
    aqi_pred: int
    aqi_category: str | None


class ForecastOut(BaseModel):
    location: str
    model_version: str
    generated_at: datetime | None
    horizon_hours: int
    points: list[ForecastPointOut]
    worst: ForecastPointOut | None = Field(
        default=None, description="Самый грязный час в горизонте прогноза"
    )


class SubscribeIn(BaseModel):
    tg_id: int = Field(gt=0, examples=[123456789], description="Telegram user id")
    threshold_aqi: int = Field(default=100, ge=1, le=500, examples=[100])
    location: str = Field(default="main", examples=["main"])
    lang: str = Field(default="ru", max_length=8)


class SubscribeOut(BaseModel):
    tg_id: int
    threshold_aqi: int
    location: str
    subscribed: bool
    created: bool = Field(description="True, если подписка создана, False — обновлена")


class UnsubscribeOut(BaseModel):
    tg_id: int
    subscribed: bool


class SubscriberOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    tg_id: int
    threshold_aqi: int
    location: str
    lang: str


class ModelRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    model_version: str
    algorithm: str
    created_at: datetime
    rows_used: int
    mae: float
    rmse: float
    baseline_mae: float
    baseline_rmse: float
    is_active: bool
    notes: str | None


class HealthOut(BaseModel):
    status: str
    version: str
    database: str
    measurements: int
    last_measurement_ts: datetime | None
    active_model: str | None
