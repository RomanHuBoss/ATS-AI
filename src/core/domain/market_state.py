"""
MarketState — Модель состояния рынка

ТЗ: Appendix B.1 (market_state)

Immutable Pydantic модель, представляющая снапшот состояния рынка.
Полная совместимость с JSON Schema (contracts/schema/market_state.json).
"""

from typing import Optional

from pydantic import BaseModel, Field


# =============================================================================
# NESTED MODELS
# =============================================================================


class Price(BaseModel):
    """
    Ценовые данные.

    ТЗ: Appendix B.1 (market_state.price)
    """

    last: float = Field(..., gt=0, description="Последняя цена сделки")
    mid: float = Field(..., gt=0, description="Средняя цена (bid+ask)/2")
    bid: float = Field(..., gt=0, description="Лучшая цена покупки")
    ask: float = Field(..., gt=0, description="Лучшая цена продажи")
    tick_size: float = Field(..., gt=0, description="Минимальный шаг цены")

    model_config = {"frozen": True}


class Volatility(BaseModel):
    """
    Данные волатильности.

    ТЗ: Appendix B.1 (market_state.volatility)
    """

    atr: float = Field(..., gt=0, description="Average True Range")
    atr_z_short: float = Field(..., description="ATR z-score (короткое окно)")
    atr_z_long: float = Field(..., description="ATR z-score (длинное окно)")
    atr_window_short: int = Field(..., gt=0, description="Короткое окно ATR (бары)")
    hv30: Optional[float] = Field(
        None, gt=0, description="30-дневная историческая волатильность (nullable)"
    )
    hv30_z: Optional[float] = Field(None, description="HV30 z-score (nullable)")

    model_config = {"frozen": True}


class Liquidity(BaseModel):
    """
    Данные ликвидности и orderbook.

    ТЗ: Appendix B.1 (market_state.liquidity)
    """

    spread_bps: float = Field(..., ge=0, description="Спред bid-ask (базисные пункты)")
    depth_bid_usd: float = Field(..., ge=0, description="Глубина bid стороны (USD)")
    depth_ask_usd: float = Field(..., ge=0, description="Глубина ask стороны (USD)")
    impact_bps_est: float = Field(
        ..., ge=0, description="Оценка рыночного impact (базисные пункты)"
    )
    orderbook_staleness_ms: int = Field(
        ..., ge=0, description="Возраст данных orderbook (миллисекунды)"
    )
    orderbook_last_update_id: Optional[int] = Field(
        None, ge=0, description="ID последнего обновления orderbook (nullable)"
    )
    orderbook_update_id_age_ms: Optional[int] = Field(
        None, ge=0, description="Возраст ID обновления (миллисекунды, nullable)"
    )

    model_config = {"frozen": True}


class Derivatives(BaseModel):
    """
    Данные деривативов (funding, OI, basis).

    ТЗ: Appendix B.1 (market_state.derivatives)
    """

    funding_rate_spot: float = Field(..., description="Текущий funding rate")
    funding_rate_forecast: Optional[float] = Field(
        None, description="Прогноз funding rate (nullable)"
    )
    funding_period_hours: float = Field(..., gt=0, description="Период funding (часы)")
    time_to_next_funding_sec: int = Field(
        ..., ge=0, description="Время до следующего funding (секунды)"
    )
    oi: Optional[float] = Field(None, ge=0, description="Open interest (nullable)")
    basis_value: Optional[float] = Field(None, description="Значение basis (nullable)")
    basis_z: Optional[float] = Field(None, description="Basis z-score (nullable)")
    basis_vol_z: Optional[float] = Field(
        None, description="Basis volatility z-score (nullable)"
    )
    adl_rank_quantile: Optional[float] = Field(
        None, ge=0, le=1, description="ADL rank quantile (nullable, 0-1)"
    )

    model_config = {"frozen": True}


class Correlations(BaseModel):
    """
    Данные корреляций и tail risk.

    ТЗ: Appendix B.1 (market_state.correlations)
    """

    tail_metrics_reliable: bool = Field(
        ..., description="Флаг надежности tail метрик"
    )
    tail_reliability_score: float = Field(
        ..., ge=0, le=1, description="Скор надежности tail метрик (0-1)"
    )
    tail_corr_to_btc: Optional[float] = Field(
        None, ge=-1, le=1, description="Tail корреляция к BTC (nullable, -1 to 1)"
    )
    stress_beta_to_btc: Optional[float] = Field(
        None, description="Stress beta к BTC (nullable)"
    )
    lambda_tail_dep: Optional[float] = Field(
        None, ge=0, le=1, description="Коэффициент tail dependence (nullable, 0-1)"
    )
    corr_matrix_snapshot_id: Optional[int] = Field(
        None, ge=0, description="ID снапшота корреляционной матрицы (nullable)"
    )
    corr_matrix_age_sec: Optional[int] = Field(
        None, ge=0, description="Возраст корреляционной матрицы (секунды, nullable)"
    )
    gamma_s: Optional[float] = Field(
        None, ge=0, description="Stress gamma коэффициент (nullable)"
    )

    model_config = {"frozen": True}


class DataQuality(BaseModel):
    """
    Данные качества данных (DQS).

    ТЗ: Appendix B.1 (market_state.data_quality)
    """

    suspected_data_glitch: bool = Field(
        ..., description="Флаг подозрения на data glitch"
    )
    stale_book_glitch: bool = Field(
        ..., description="Флаг glitch stale orderbook"
    )
    data_quality_score: float = Field(
        ..., ge=0, le=1, description="Общий скор качества данных (0-1)"
    )
    dqs_critical: float = Field(
        ..., ge=0, le=1, description="Критический компонент DQS (0-1)"
    )
    dqs_noncritical: float = Field(
        ..., ge=0, le=1, description="Некритический компонент DQS (0-1)"
    )
    dqs_sources: float = Field(
        ..., ge=0, le=1, description="Скор качества источников (0-1)"
    )
    dqs_mult: float = Field(..., ge=0, le=1, description="DQS мультипликатор (0-1)")
    staleness_price_ms: int = Field(
        ..., ge=0, description="Staleness ценовых данных (миллисекунды)"
    )
    staleness_liquidity_ms: int = Field(
        ..., ge=0, description="Staleness данных ликвидности (миллисекунды)"
    )
    staleness_derivatives_sec: int = Field(
        ..., ge=0, description="Staleness данных деривативов (секунды)"
    )
    cross_exchange_dev_bps: float = Field(
        ..., ge=0, description="Отклонение между биржами (базисные пункты)"
    )
    oracle_dev_frac: Optional[float] = Field(
        None, ge=0, description="Отклонение от oracle (фракция, nullable)"
    )
    oracle_staleness_ms: Optional[int] = Field(
        None, ge=0, description="Staleness данных oracle (миллисекунды, nullable)"
    )
    price_sources_used: list[str] = Field(
        ..., min_length=1, description="Список используемых источников цен"
    )
    toxic_flow_suspected: bool = Field(
        ..., description="Флаг подозрения на toxic flow"
    )
    execution_price_improvement_bps: Optional[float] = Field(
        None, description="Улучшение цены исполнения (базисные пункты, nullable)"
    )

    model_config = {"frozen": True}


# =============================================================================
# MARKET STATE MODEL
# =============================================================================


class MarketState(BaseModel):
    """
    Модель состояния рынка (market snapshot).

    ТЗ: Appendix B.1 (market_state)

    Immutable модель (frozen=True). Содержит полный снапшот состояния рынка:
    - Метаданные снапшота (snapshot_id, timestamp, gaps)
    - Ценовые данные (price)
    - Волатильность (volatility)
    - Ликвидность (liquidity)
    - Деривативы (derivatives)
    - Корреляции (correlations)
    - Качество данных (data_quality)
    """

    # Метаданные
    schema_version: str = Field(
        ..., pattern="^7$", description="Версия схемы для tracking совместимости"
    )
    snapshot_id: int = Field(..., ge=0, description="Монотонный идентификатор снапшота")
    ts_utc_ms: int = Field(
        ..., ge=0, description="Timestamp снапшота (UTC, миллисекунды)"
    )
    market_data_id: int = Field(
        ..., ge=0, description="Идентификатор обновления рыночных данных"
    )
    data_gap_sec: int = Field(
        ..., ge=0, description="Обнаруженная длительность data gap (секунды)"
    )
    is_gap_contaminated: bool = Field(
        ..., description="Флаг загрязнения данных из-за gap"
    )

    # Идентификация инструмента
    instrument: str = Field(
        ..., min_length=1, description="Торговый инструмент (например, 'BTCUSDT')"
    )
    timeframe: str = Field(
        ..., pattern="^H1$", description="Торговый таймфрейм"
    )

    # Структурированные данные
    price: Price = Field(..., description="Ценовые данные")
    volatility: Volatility = Field(..., description="Данные волатильности")
    liquidity: Liquidity = Field(..., description="Данные ликвидности")
    derivatives: Derivatives = Field(..., description="Данные деривативов")
    correlations: Correlations = Field(..., description="Данные корреляций")
    data_quality: DataQuality = Field(..., description="Данные качества данных")

    model_config = {"frozen": True}
