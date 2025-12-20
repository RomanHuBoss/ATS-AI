"""
Signal — Модель торгового сигнала от Engine

ТЗ: Appendix B.3 (engine_signal)
ТЗ: 8.1 (RR sanity gates)

Immutable Pydantic модель, представляющая сигнал от торгового движка (TREND или RANGE).
Соответствует схеме из engine_signal.
"""

from enum import Enum
from typing import Final

from pydantic import BaseModel, Field, field_validator


# =============================================================================
# ENUMS
# =============================================================================


class EngineType(str, Enum):
    """Тип торгового движка"""

    TREND = "TREND"
    RANGE = "RANGE"


class Direction(str, Enum):
    """Направление сигнала"""

    LONG = "long"
    SHORT = "short"


# =============================================================================
# NESTED MODELS
# =============================================================================


class SignalLevels(BaseModel):
    """
    Уровни входа, стопа и тейк-профита.

    ТЗ: Appendix B.3 (engine_signal.levels)
    """

    entry_price: float = Field(..., gt=0, description="Цена входа")
    stop_loss: float = Field(..., gt=0, description="Уровень stop-loss")
    take_profit: float = Field(..., gt=0, description="Уровень take-profit")

    model_config = {"frozen": True}

    @field_validator("stop_loss")
    @classmethod
    def validate_stop_loss(cls, v: float, info) -> float:
        """Проверка, что SL не равен entry (базовая валидация, направление проверяется в Signal)"""
        if "entry_price" in info.data:
            entry = info.data["entry_price"]
            if abs(v - entry) < 1e-8:
                raise ValueError("stop_loss must differ from entry_price")
        return v

    @field_validator("take_profit")
    @classmethod
    def validate_take_profit(cls, v: float, info) -> float:
        """Проверка, что TP не равен entry (базовая валидация, направление проверяется в Signal)"""
        if "entry_price" in info.data:
            entry = info.data["entry_price"]
            if abs(v - entry) < 1e-8:
                raise ValueError("take_profit must differ from entry_price")
        return v


class SignalContext(BaseModel):
    """
    Контекст сигнала: ожидаемое время удержания, режим рынка, идентификатор setup.

    ТЗ: Appendix B.3 (engine_signal.context)
    """

    expected_holding_hours: float = Field(
        ..., gt=0, description="Ожидаемое время удержания позиции (часы)"
    )
    regime_hint: str | None = Field(None, description="Подсказка о рыночном режиме")
    setup_id: str = Field(..., min_length=1, description="Идентификатор торговой setup")

    model_config = {"frozen": True}


class SignalConstraints(BaseModel):
    """
    Ограничения сигнала: минимальный RR, границы SL в ATR.

    ТЗ: Appendix B.3 (engine_signal.constraints)
    ТЗ: 8.1 (RR sanity gates)
    """

    RR_min_engine: float = Field(
        ..., gt=0, description="Минимальный RR от Engine (до учёта издержек)"
    )
    sl_min_atr_mult: float = Field(..., gt=0, description="Минимальный SL в единицах ATR")
    sl_max_atr_mult: float = Field(..., gt=0, description="Максимальный SL в единицах ATR")

    model_config = {"frozen": True}

    @field_validator("sl_max_atr_mult")
    @classmethod
    def validate_sl_max_greater_than_min(cls, v: float, info) -> float:
        """Проверка, что sl_max_atr_mult > sl_min_atr_mult"""
        if "sl_min_atr_mult" in info.data:
            sl_min = info.data["sl_min_atr_mult"]
            if v <= sl_min:
                raise ValueError(f"sl_max_atr_mult {v} must be > sl_min_atr_mult {sl_min}")
        return v


# =============================================================================
# SIGNAL MODEL
# =============================================================================


class Signal(BaseModel):
    """
    Модель торгового сигнала от Engine.

    ТЗ: Appendix B.3 (engine_signal)

    Immutable модель (frozen=True). Содержит все параметры сигнала:
    - Идентификацию (инструмент, движок, направление)
    - Уровни (entry, SL, TP)
    - Контекст (время удержания, режим, setup)
    - Ограничения (RR, SL в ATR)
    """

    # Идентификация
    instrument: str = Field(..., min_length=1, description="Инструмент (например, 'BTCUSDT')")
    engine: EngineType = Field(..., description="Тип движка (TREND/RANGE)")
    direction: Direction = Field(..., description="Направление сигнала (long/short)")
    signal_ts_utc_ms: int = Field(
        ..., gt=0, description="Время генерации сигнала (UTC, миллисекунды)"
    )

    # Структурированные данные
    levels: SignalLevels = Field(..., description="Уровни входа, SL, TP")
    context: SignalContext = Field(..., description="Контекст сигнала")
    constraints: SignalConstraints = Field(..., description="Ограничения сигнала")

    model_config = {"frozen": True}

    @field_validator("levels")
    @classmethod
    def validate_levels_direction(cls, v: SignalLevels, info) -> SignalLevels:
        """
        Проверка корректности уровней в зависимости от направления.

        LONG: entry < TP, entry > SL
        SHORT: entry > TP, entry < SL
        """
        if "direction" not in info.data:
            return v

        direction = info.data["direction"]
        entry = v.entry_price
        sl = v.stop_loss
        tp = v.take_profit

        if direction == Direction.LONG:
            if tp <= entry:
                raise ValueError(f"LONG: take_profit {tp} must be > entry_price {entry}")
            if sl >= entry:
                raise ValueError(f"LONG: stop_loss {sl} must be < entry_price {entry}")
        elif direction == Direction.SHORT:
            if tp >= entry:
                raise ValueError(f"SHORT: take_profit {tp} must be < entry_price {entry}")
            if sl <= entry:
                raise ValueError(f"SHORT: stop_loss {sl} must be > entry_price {entry}")

        return v

    def potential_profit(self) -> float:
        """
        Потенциальная прибыль (entry → TP) в абсолютных единицах цены.

        Returns:
            abs(TP - entry)
        """
        return abs(self.levels.take_profit - self.levels.entry_price)

    def potential_loss(self) -> float:
        """
        Потенциальный убыток (entry → SL) в абсолютных единицах цены.

        Returns:
            abs(entry - SL)
        """
        return abs(self.levels.entry_price - self.levels.stop_loss)

    def raw_rr(self) -> float:
        """
        Raw Risk-Reward (без учёта издержек).

        ТЗ: 8.1 (RR sanity gates)

        Returns:
            potential_profit / potential_loss
        """
        return self.potential_profit() / self.potential_loss()

    def validate_rr_constraint(self) -> bool:
        """
        Проверка, что raw RR >= RR_min_engine.

        ТЗ: 8.1 (RR sanity gates)

        Returns:
            True если RR >= RR_min_engine, иначе False
        """
        return self.raw_rr() >= self.constraints.RR_min_engine
