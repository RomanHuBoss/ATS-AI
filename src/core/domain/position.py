"""
Position — Модель открытой позиции

ТЗ: Appendix B.2 (portfolio_state.positions)
ТЗ: 2.1.1.0 (RiskUnits)

Immutable Pydantic модель, представляющая открытую позицию в портфеле.
Соответствует схеме из portfolio_state.positions.
"""

from enum import Enum
from typing import Final

from pydantic import BaseModel, Field, field_validator


# =============================================================================
# ENUMS
# =============================================================================


class Direction(str, Enum):
    """Направление позиции"""

    LONG = "long"
    SHORT = "short"


# =============================================================================
# POSITION MODEL
# =============================================================================


class Position(BaseModel):
    """
    Модель открытой позиции.

    ТЗ: Appendix B.2 (portfolio_state.positions)

    Immutable модель (frozen=True) для предотвращения случайных изменений.
    Все изменения позиции должны создавать новый экземпляр.
    """

    # Идентификация
    instrument: str = Field(..., min_length=1, description="Инструмент (например, 'BTCUSDT')")
    cluster_id: str = Field(..., min_length=1, description="Идентификатор кластера корреляций")
    direction: Direction = Field(..., description="Направление позиции (long/short)")

    # Параметры позиции
    qty: float = Field(..., gt=0, description="Количество (всегда положительное)")
    entry_price: float = Field(..., gt=0, description="Цена входа")
    entry_eff_allin: float = Field(
        ..., gt=0, description="Эффективная цена входа (all-in, с учётом всех издержек)"
    )
    sl_eff_allin: float = Field(
        ..., gt=0, description="Эффективная цена SL (all-in, с учётом всех издержек)"
    )

    # Риск и размер
    risk_amount_usd: float = Field(..., gt=0, description="Риск позиции в USD")
    risk_pct_equity: float = Field(..., gt=0, description="Риск позиции в % от equity")
    notional_usd: float = Field(..., gt=0, description="Notional размер позиции в USD")

    # PnL
    unrealized_pnl_usd: float = Field(..., description="Нереализованный PnL в USD")
    funding_pnl_usd: float = Field(
        ..., description="Накопленный funding PnL (может быть отрицательным)"
    )

    # Время
    opened_ts_utc_ms: int = Field(
        ..., gt=0, description="Время открытия позиции (UTC, миллисекунды)"
    )

    model_config = {"frozen": True}  # Immutable

    @field_validator("risk_amount_usd")
    @classmethod
    def validate_risk_minimum(cls, v: float) -> float:
        """
        Проверка абсолютного минимума риска.

        ТЗ: 2.1.1.0 (RISK_AMOUNT_MIN_ABSOLUTE_USD = 0.10)
        """
        RISK_AMOUNT_MIN_ABSOLUTE_USD: Final[float] = 0.10
        if v < RISK_AMOUNT_MIN_ABSOLUTE_USD:
            raise ValueError(
                f"risk_amount_usd {v:.6f} below minimum {RISK_AMOUNT_MIN_ABSOLUTE_USD}"
            )
        return v

    @field_validator("risk_pct_equity")
    @classmethod
    def validate_risk_pct_range(cls, v: float) -> float:
        """
        Проверка разумности риска в процентах.

        Максимум 100% (вся equity) — защита от ошибок ввода.
        """
        if v > 1.0:
            raise ValueError(f"risk_pct_equity {v:.4f} exceeds 100% of equity")
        return v

    def r_value(self, current_pnl_usd: float) -> float:
        """
        Конверсия PnL в R-единицы.

        ТЗ: 2.1.1.0 (R_value = PnL_usd / risk_amount_usd)

        Args:
            current_pnl_usd: Текущий PnL в USD (unrealized + funding)

        Returns:
            PnL в R-единицах (безразмерный)
        """
        return current_pnl_usd / self.risk_amount_usd

    def total_pnl_usd(self) -> float:
        """
        Полный PnL позиции (unrealized + funding).

        Returns:
            Суммарный PnL в USD
        """
        return self.unrealized_pnl_usd + self.funding_pnl_usd
