"""Модели SQLAlchemy.

Соглашение по времени: все метки времени хранятся как naive datetime в UTC.
Перевод в Asia/Almaty делается только на границе — в API-ответах и в боте.
Это избавляет от расхождений между PostgreSQL и SQLite (тесты) и от
неоднозначности при переходе на летнее время.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class Measurement(Base):
    """Часовое наблюдение по загрязнителям в конкретной точке кампуса."""

    __tablename__ = "measurements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    location: Mapped[str] = mapped_column(String(64), nullable=False)
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lon: Mapped[float] = mapped_column(Float, nullable=False)

    pm25: Mapped[float | None] = mapped_column(Float)
    pm10: Mapped[float | None] = mapped_column(Float)
    no2: Mapped[float | None] = mapped_column(Float)
    o3: Mapped[float | None] = mapped_column(Float)

    aqi: Mapped[int | None] = mapped_column(Integer)
    aqi_category: Mapped[str | None] = mapped_column(String(48))
    dominant_pollutant: Mapped[str | None] = mapped_column(String(16))

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("ts", "source", "location", name="uq_measurement_ts_source_loc"),
        Index("ix_measurements_location_ts", "location", "ts"),
        Index("ix_measurements_ts", "ts"),
    )

    def __repr__(self) -> str:  # pragma: no cover - отладочное представление
        return f"<Measurement {self.location} {self.ts:%Y-%m-%d %H:%M} pm25={self.pm25}>"


class Weather(Base):
    """Метеоусловия — главные внешние признаки для прогноза загрязнения."""

    __tablename__ = "weather"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    location: Mapped[str] = mapped_column(String(64), nullable=False)

    temp: Mapped[float | None] = mapped_column(Float)
    wind_speed: Mapped[float | None] = mapped_column(Float)
    wind_dir: Mapped[float | None] = mapped_column(Float)
    humidity: Mapped[float | None] = mapped_column(Float)
    pressure: Mapped[float | None] = mapped_column(Float)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("ts", "location", name="uq_weather_ts_loc"),
        Index("ix_weather_location_ts", "location", "ts"),
    )


class Forecast(Base):
    """Прогноз PM2.5/AQI, посчитанный моделью на конкретный момент времени."""

    __tablename__ = "forecasts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    target_ts: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    location: Mapped[str] = mapped_column(String(64), nullable=False)
    horizon_h: Mapped[int] = mapped_column(Integer, nullable=False)

    pm25_pred: Mapped[float] = mapped_column(Float, nullable=False)
    aqi_pred: Mapped[int] = mapped_column(Integer, nullable=False)
    aqi_category: Mapped[str | None] = mapped_column(String(48))
    model_version: Mapped[str] = mapped_column(String(64), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "target_ts", "location", "model_version", name="uq_forecast_target_loc_model"
        ),
        Index("ix_forecasts_location_target", "location", "target_ts"),
    )


class User(Base):
    """Подписчик Telegram-бота."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tg_id: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True, index=True)
    threshold_aqi: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    subscribed: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    lang: Mapped[str] = mapped_column(String(8), default="ru", nullable=False)
    location: Mapped[str] = mapped_column(String(64), default="main", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    alerts: Mapped[list[Alert]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class Alert(Base):
    """Журнал отправленных предупреждений — защищает от повторных рассылок."""

    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sent_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    aqi: Mapped[int] = mapped_column(Integer, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)

    user: Mapped[User] = relationship(back_populates="alerts")


class ModelRun(Base):
    """История обучений: нужна для отчёта и для сравнения модели с baseline."""

    __tablename__ = "model_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    model_version: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    algorithm: Mapped[str] = mapped_column(String(32), nullable=False)
    rows_used: Mapped[int] = mapped_column(Integer, nullable=False)

    mae: Mapped[float] = mapped_column(Float, nullable=False)
    rmse: Mapped[float] = mapped_column(Float, nullable=False)
    baseline_mae: Mapped[float] = mapped_column(Float, nullable=False)
    baseline_rmse: Mapped[float] = mapped_column(Float, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
