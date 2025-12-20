"""
Trade — Модель завершённой сделки

ТЗ: 2.1.1.0 (RiskUnits), 2.1.1 (Expectancy в R-единицах)

Immutable Pydantic модель, представляющая закрытую позицию с результатами.
Trade создаётся при закрытии Position и содержит полную информацию о сделке.
"""

from enum import Enum

from pydantic import BaseModel, Field, field_validator


# =============================================================================
# ENUMS
# =============================================================================


class Direction(str, Enum):
    """Направление сделки"""

    LONG = "long"
    SHORT = "short"


class ExitReason(str, Enum):
    """Причина закрытия сделки"""

    TAKE_PROFIT = "take_profit"  # TP достигнут
    STOP_LOSS = "stop_loss"  # SL достигнут
    MANUAL = "manual"  # Ручное закрытие
    TIMEOUT = "timeout"  # Таймаут по времени
    EMERGENCY = "emergency"  # Экстренное закрытие (DRP EMERGENCY)
    SIGNAL_REVERSE = "signal_reverse"  # Разворот сигнала


# =============================================================================
# TRADE MODEL
# =============================================================================


class Trade(BaseModel):
    """
    Модель завершённой сделки.

    Trade представляет закрытую позицию с полной информацией о входе, выходе и результатах.
    Используется для расчёта метрик (Expectancy, WinRate, ProfitFactor) и анализа производительности.

    Immutable модель (frozen=True).
    """

    # Идентификация
    trade_id: str = Field(..., min_length=1, description="Уникальный идентификатор сделки")
    instrument: str = Field(..., min_length=1, description="Инструмент (например, 'BTCUSDT')")
    cluster_id: str = Field(..., min_length=1, description="Идентификатор кластера корреляций")
    direction: Direction = Field(..., description="Направление сделки (long/short)")

    # Вход
    entry_price: float = Field(..., gt=0, description="Цена входа")
    entry_eff_allin: float = Field(
        ..., gt=0, description="Эффективная цена входа (all-in, с учётом всех издержек)"
    )
    entry_qty: float = Field(..., gt=0, description="Количество при входе")
    entry_ts_utc_ms: int = Field(..., gt=0, description="Время входа (UTC, миллисекунды)")

    # Выход
    exit_price: float = Field(..., gt=0, description="Цена выхода")
    exit_eff_allin: float = Field(
        ..., gt=0, description="Эффективная цена выхода (all-in, с учётом всех издержек)"
    )
    exit_qty: float = Field(..., gt=0, description="Количество при выходе")
    exit_ts_utc_ms: int = Field(..., gt=0, description="Время выхода (UTC, миллисекунды)")
    exit_reason: ExitReason = Field(..., description="Причина закрытия")

    # Риск
    risk_amount_usd: float = Field(..., gt=0, description="Риск сделки в USD")
    risk_pct_equity: float = Field(..., gt=0, description="Риск сделки в % от equity")
    sl_eff_allin: float = Field(
        ..., gt=0, description="Эффективная цена SL (all-in, для расчёта риска)"
    )
    tp_eff_allin: float | None = Field(
        None, gt=0, description="Эффективная цена TP (all-in), если задан"
    )

    # Результаты
    gross_pnl_usd: float = Field(..., description="Gross PnL (до издержек)")
    net_pnl_usd: float = Field(..., description="Net PnL (после всех издержек)")
    funding_pnl_usd: float = Field(..., description="Funding PnL за время удержания позиции")
    commission_usd: float = Field(..., ge=0, description="Комиссии (entry + exit)")

    # Equity контекст
    equity_before_usd: float = Field(..., gt=0, description="Equity до сделки")

    model_config = {"frozen": True}  # Immutable

    @field_validator("exit_ts_utc_ms")
    @classmethod
    def validate_exit_after_entry(cls, v: int, info) -> int:
        """Проверка, что выход после входа"""
        if "entry_ts_utc_ms" in info.data:
            entry_ts = info.data["entry_ts_utc_ms"]
            if v <= entry_ts:
                raise ValueError(f"exit_ts_utc_ms {v} must be after entry_ts_utc_ms {entry_ts}")
        return v

    @field_validator("exit_qty")
    @classmethod
    def validate_exit_qty_matches_entry(cls, v: float, info) -> float:
        """Проверка, что количество при выходе совпадает с входом (частичное закрытие пока не поддерживается)"""
        if "entry_qty" in info.data:
            entry_qty = info.data["entry_qty"]
            # Допуск 1e-8 для float сравнения
            if abs(v - entry_qty) > 1e-8:
                raise ValueError(
                    f"exit_qty {v} must equal entry_qty {entry_qty} (partial closes not yet supported)"
                )
        return v

    def r_value(self) -> float:
        """
        Результат сделки в R-единицах.

        ТЗ: 2.1.1.0 (R_value = PnL_usd / risk_amount_usd)

        Returns:
            Net PnL в R-единицах (безразмерный)
            Например: -1.0R означает SL hit, +2.0R означает TP hit при RR=2
        """
        return self.net_pnl_usd / self.risk_amount_usd

    def holding_time_hours(self) -> float:
        """
        Время удержания позиции в часах.

        Returns:
            Время удержания в часах
        """
        duration_ms = self.exit_ts_utc_ms - self.entry_ts_utc_ms
        return duration_ms / (1000 * 60 * 60)

    def is_winner(self) -> bool:
        """
        Проверка, была ли сделка прибыльной.

        Returns:
            True если net_pnl_usd > 0
        """
        return self.net_pnl_usd > 0

    def is_loser(self) -> bool:
        """
        Проверка, была ли сделка убыточной.

        Returns:
            True если net_pnl_usd < 0
        """
        return self.net_pnl_usd < 0

    def is_breakeven(self, tolerance: float = 1e-6) -> bool:
        """
        Проверка, была ли сделка в безубытке.

        Args:
            tolerance: Допуск для сравнения с нулём

        Returns:
            True если |net_pnl_usd| <= tolerance
        """
        return abs(self.net_pnl_usd) <= tolerance
