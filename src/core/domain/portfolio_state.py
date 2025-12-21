"""
PortfolioState — Модель состояния портфеля

ТЗ: Appendix B.2 (portfolio_state)

Immutable Pydantic модель, представляющая снапшот состояния портфеля.
Полная совместимость с JSON Schema (contracts/schema/portfolio_state.json).
Интеграция с Position модель для позиций.
"""

from enum import Enum

from pydantic import BaseModel, Field

from .position import Position


# =============================================================================
# ENUMS
# =============================================================================


class DRPState(str, Enum):
    """
    Состояние Disaster Recovery Protocol.

    ТЗ: Appendix B.2 (portfolio_state.states.DRP_state)
    """

    NORMAL = "NORMAL"
    DEGRADED = "DEGRADED"
    DEFENSIVE = "DEFENSIVE"
    EMERGENCY = "EMERGENCY"
    RECOVERY = "RECOVERY"
    HIBERNATE = "HIBERNATE"


class MLOpsState(str, Enum):
    """
    Состояние MLOps системы.

    ТЗ: Appendix B.2 (portfolio_state.states.MLOps_state)
    """

    OK = "OK"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class TradingMode(str, Enum):
    """
    Режим торговли.

    ТЗ: Appendix B.2 (portfolio_state.states.trading_mode)
    """

    LIVE = "LIVE"
    PAPER = "PAPER"
    SHADOW = "SHADOW"
    BACKTEST = "BACKTEST"


# =============================================================================
# NESTED MODELS
# =============================================================================


class Equity(BaseModel):
    """
    Состояние капитала (equity).

    ТЗ: Appendix B.2 (portfolio_state.equity)
    """

    equity_usd: float = Field(..., gt=0, description="Текущая equity (USD)")
    peak_equity_usd: float = Field(..., gt=0, description="Пиковая equity (USD)")
    drawdown_pct: float = Field(
        ..., ge=0, le=1, description="Текущая просадка (фракция, 0-1)"
    )
    drawdown_smoothed_pct: float = Field(
        ..., ge=0, le=1, description="Сглаженная просадка (фракция, 0-1)"
    )

    model_config = {"frozen": True}


class Risk(BaseModel):
    """
    Состояние риска портфеля.

    ТЗ: Appendix B.2 (portfolio_state.risk)
    """

    # Текущий риск
    current_portfolio_risk_pct: float = Field(
        ..., description="Текущий портфельный риск (%)"
    )
    current_cluster_risk_pct: float = Field(
        ..., description="Текущий риск кластера (%)"
    )
    reserved_portfolio_risk_pct: float = Field(
        ..., description="Зарезервированный портфельный риск (%)"
    )
    reserved_cluster_risk_pct: float = Field(
        ..., description="Зарезервированный риск кластера (%)"
    )
    current_sum_abs_risk_pct: float = Field(
        ..., description="Текущая сумма абсолютных рисков (%)"
    )
    reserved_sum_abs_risk_pct: float = Field(
        ..., description="Зарезервированная сумма абсолютных рисков (%)"
    )
    reserved_heat_upper_bound_pct: float = Field(
        ..., description="Верхняя граница зарезервированного heat (%)"
    )

    # Adjusted heat метрики
    adjusted_heat_base_pct: float = Field(..., description="Base adjusted heat (%)")
    adjusted_heat_blend_pct: float = Field(..., description="Blend adjusted heat (%)")
    adjusted_heat_worst_pct: float = Field(..., description="Worst adjusted heat (%)")
    heat_uni_abs_pct: float = Field(..., description="Uniform absolute heat (%)")

    # Лимиты
    max_portfolio_risk_pct: float = Field(
        ..., description="Максимальный портфельный риск (%)"
    )
    max_sum_abs_risk_pct: float = Field(
        ..., description="Максимальная сумма абсолютных рисков (%)"
    )
    cluster_risk_limit_pct: float = Field(..., description="Лимит риска кластера (%)")
    max_adjusted_heat_pct: float = Field(
        ..., description="Максимальный adjusted heat (%)"
    )
    max_trade_risk_cap_pct: float = Field(
        ..., description="Максимальный лимит риска одной сделки (%)"
    )

    model_config = {"frozen": True}


class States(BaseModel):
    """
    Состояния системы (DRP, MLOps, trading mode).

    ТЗ: Appendix B.2 (portfolio_state.states)
    """

    DRP_state: DRPState = Field(..., description="Состояние Disaster Recovery Protocol")
    MLOps_state: MLOpsState = Field(..., description="Состояние MLOps системы")
    trading_mode: TradingMode = Field(..., description="Режим торговли")
    warmup_bars_remaining: int = Field(
        ..., description="Оставшихся баров для прогрева"
    )
    drp_flap_count: int = Field(..., description="Счетчик flapping DRP состояний")
    hibernate_until_ts_utc_ms: int | None = Field(
        None, description="Timestamp окончания hibernate (UTC, миллисекунды, nullable)"
    )
    
    # Manual halt flags (GATE 1)
    manual_halt_new_entries: bool = Field(
        default=False, description="Ручная блокировка новых входов (kill-switch)"
    )
    manual_halt_all_trading: bool = Field(
        default=False, description="Ручная блокировка всей торговли (emergency stop)"
    )

    model_config = {"frozen": True}


# =============================================================================
# PORTFOLIO STATE MODEL
# =============================================================================


class PortfolioState(BaseModel):
    """
    Модель состояния портфеля (portfolio snapshot).

    ТЗ: Appendix B.2 (portfolio_state)

    Immutable модель (frozen=True). Содержит полный снапшот состояния портфеля:
    - Метаданные снапшота (snapshot_id, portfolio_id, timestamp)
    - Состояние капитала (equity)
    - Состояние риска (risk)
    - Состояния системы (states)
    - Позиции (positions)
    """

    # Метаданные
    schema_version: str = Field(
        ..., pattern="^7$", description="Версия схемы для tracking совместимости"
    )
    snapshot_id: int = Field(..., ge=0, description="Монотонный идентификатор снапшота")
    portfolio_id: int = Field(
        ..., ge=0, description="Идентификатор версии портфеля"
    )
    ts_utc_ms: int = Field(
        ..., ge=0, description="Timestamp снапшота (UTC, миллисекунды)"
    )

    # Структурированные данные
    equity: Equity = Field(..., description="Состояние капитала")
    risk: Risk = Field(..., description="Состояние риска")
    states: States = Field(..., description="Состояния системы")
    positions: list[Position] = Field(
        default_factory=list, description="Список открытых позиций"
    )

    model_config = {"frozen": True}
