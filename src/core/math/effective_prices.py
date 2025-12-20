"""
EffectivePrices — All-In Effective Price Calculation

ТЗ: 2.1.1.1 (обязательное)
Appendix A.2: Формулы эффективных цен LONG/SHORT
Appendix C.1: Epsilon-параметры

Модуль вычисляет эффективные цены с учётом всех издержек:
- spread (half-spread = 0.5 * spread_bps)
- fees (entry/exit)
- slippage (entry/tp/stop with multiplier)
- impact (entry/exit/stop)

Формула unit_risk_allin_net для корректного расчёта риска в R-value.
"""

from enum import Enum
from typing import Final, Optional


# =============================================================================
# EPSILON-ПАРАМЕТРЫ (Appendix C.1, C.2)
# =============================================================================

# Минимальный абсолютный unit risk (USD)
ABS_MIN_UNIT_RISK_USD: Final[float] = 1e-6

# Epsilon для сравнения float
EPS_FLOAT_COMPARE: Final[float] = 1e-12

# Epsilon для ATR (используется в валидации ATR-based минимумов)
ATR_EPS: Final[float] = 1e-12

# Stop slippage multiplier (по умолчанию из ТЗ 3.2)
DEFAULT_STOP_SLIPPAGE_MULT: Final[float] = 2.0

# Минимальный множитель ATR для unit risk (по умолчанию, можно переопределить)
DEFAULT_UNIT_RISK_MIN_ATR_MULT: Final[float] = 0.02  # 2% от ATR


# =============================================================================
# ТИПЫ
# =============================================================================


class PositionSide(Enum):
    """Направление позиции"""

    LONG = "LONG"
    SHORT = "SHORT"


# =============================================================================
# ЭФФЕКТИВНЫЕ ЦЕНЫ
# =============================================================================


def bps_to_fraction(bps: float) -> float:
    """
    Конверсия basis points в дробь.

    Args:
        bps: Basis points (например, 10 bps = 0.10%)

    Returns:
        Дробь (например, 10 bps → 0.001)
    """
    return bps / 10000.0


def calculate_effective_prices(
    side: PositionSide,
    entry_price: float,
    tp_price: float,
    sl_price: float,
    spread_bps: float,
    fee_entry_bps: float,
    fee_exit_bps: float,
    slippage_entry_bps: float,
    slippage_tp_bps: float,
    slippage_stop_bps: float,
    impact_entry_bps: float,
    impact_exit_bps: float,
    impact_stop_bps: float,
    stop_slippage_mult: float = DEFAULT_STOP_SLIPPAGE_MULT,
) -> tuple[float, float, float]:
    """
    Вычисление all-in эффективных цен (entry, tp, sl).

    ТЗ Appendix A.2: Формулы LONG/SHORT

    LONG:
        entry_eff_allin = entry * (1 + b(0.5*spread + slippage_entry + impact_entry + fee_entry))
        tp_eff_allin    = tp    * (1 - b(0.5*spread + slippage_tp    + impact_exit  + fee_exit))
        sl_eff_allin    = sl    * (1 - b(0.5*spread + stop_slippage_mult*slippage_stop + impact_stop + fee_exit))

    SHORT:
        entry_eff_allin = entry * (1 - b(0.5*spread + slippage_entry + impact_entry + fee_entry))
        tp_eff_allin    = tp    * (1 + b(0.5*spread + slippage_tp    + impact_exit  + fee_exit))
        sl_eff_allin    = sl    * (1 + b(0.5*spread + stop_slippage_mult*slippage_stop + impact_stop + fee_exit))

    Args:
        side: Направление позиции (LONG/SHORT)
        entry_price: Цена входа (mark price)
        tp_price: Цена take profit
        sl_price: Цена stop loss
        spread_bps: Спред в basis points (полный, half-spread = 0.5 * spread_bps)
        fee_entry_bps: Комиссия входа в basis points
        fee_exit_bps: Комиссия выхода в basis points
        slippage_entry_bps: Проскальзывание входа в basis points
        slippage_tp_bps: Проскальзывание TP в basis points
        slippage_stop_bps: Проскальзывание SL в basis points (базовое)
        impact_entry_bps: Impact входа в basis points
        impact_exit_bps: Impact выхода в basis points
        impact_stop_bps: Impact SL в basis points
        stop_slippage_mult: Множитель проскальзывания для SL (default 2.0)

    Returns:
        (entry_eff_allin, tp_eff_allin, sl_eff_allin)

    Raises:
        ValueError: Если параметры некорректны
    """
    # Валидация входных параметров
    if entry_price <= 0 or tp_price <= 0 or sl_price <= 0:
        raise ValueError("Prices must be positive")

    if spread_bps < 0:
        raise ValueError("spread_bps cannot be negative")

    if any(
        x < 0
        for x in [
            fee_entry_bps,
            fee_exit_bps,
            slippage_entry_bps,
            slippage_tp_bps,
            slippage_stop_bps,
            impact_entry_bps,
            impact_exit_bps,
            impact_stop_bps,
        ]
    ):
        raise ValueError("Fees, slippage, and impact must be non-negative")

    if stop_slippage_mult < 1.0:
        raise ValueError("stop_slippage_mult must be >= 1.0")

    # Валидация направления цен
    if side == PositionSide.LONG:
        if tp_price <= entry_price:
            raise ValueError("LONG: tp_price must be > entry_price")
        if sl_price >= entry_price:
            raise ValueError("LONG: sl_price must be < entry_price")
    else:  # SHORT
        if tp_price >= entry_price:
            raise ValueError("SHORT: tp_price must be < entry_price")
        if sl_price <= entry_price:
            raise ValueError("SHORT: sl_price must be > entry_price")

    # Half-spread (ТЗ: используем половину спреда для каждой стороны)
    half_spread_bps = 0.5 * spread_bps

    # Вычисление компонентов в basis points
    entry_cost_bps = (
        half_spread_bps + slippage_entry_bps + impact_entry_bps + fee_entry_bps
    )
    tp_cost_bps = half_spread_bps + slippage_tp_bps + impact_exit_bps + fee_exit_bps
    sl_cost_bps = (
        half_spread_bps
        + stop_slippage_mult * slippage_stop_bps
        + impact_stop_bps
        + fee_exit_bps
    )

    # Конверсия в дроби
    entry_cost_frac = bps_to_fraction(entry_cost_bps)
    tp_cost_frac = bps_to_fraction(tp_cost_bps)
    sl_cost_frac = bps_to_fraction(sl_cost_bps)

    # Вычисление эффективных цен по формулам из ТЗ
    if side == PositionSide.LONG:
        # LONG: entry хуже (выше), tp/sl лучше (ниже для нас)
        entry_eff_allin = entry_price * (1.0 + entry_cost_frac)
        tp_eff_allin = tp_price * (1.0 - tp_cost_frac)
        sl_eff_allin = sl_price * (1.0 - sl_cost_frac)
    else:  # SHORT
        # SHORT: entry хуже (ниже), tp/sl лучше (выше для нас)
        entry_eff_allin = entry_price * (1.0 - entry_cost_frac)
        tp_eff_allin = tp_price * (1.0 + tp_cost_frac)
        sl_eff_allin = sl_price * (1.0 + sl_cost_frac)

    return entry_eff_allin, tp_eff_allin, sl_eff_allin


def calculate_unit_risk_allin_net(
    side: PositionSide,
    entry_eff_allin: float,
    sl_eff_allin: float,
) -> float:
    """
    Вычисление unit_risk_allin_net — риск на 1 единицу контракта с учётом всех издержек.

    ТЗ 2.1.1.1: unit_risk_allin_net_i = abs(entry_eff_allin_i - sl_eff_allin_i)

    Args:
        side: Направление позиции (LONG/SHORT)
        entry_eff_allin: Эффективная цена входа (all-in)
        sl_eff_allin: Эффективная цена SL (all-in)

    Returns:
        unit_risk_allin_net (всегда положительное число)

    Raises:
        ValueError: Если параметры некорректны
    """
    if entry_eff_allin <= 0 or sl_eff_allin <= 0:
        raise ValueError("Effective prices must be positive")

    # Проверка корректности направления
    if side == PositionSide.LONG:
        if sl_eff_allin >= entry_eff_allin:
            raise ValueError(
                f"LONG: sl_eff_allin ({sl_eff_allin}) must be < entry_eff_allin ({entry_eff_allin})"
            )
    else:  # SHORT
        if sl_eff_allin <= entry_eff_allin:
            raise ValueError(
                f"SHORT: sl_eff_allin ({sl_eff_allin}) must be > entry_eff_allin ({entry_eff_allin})"
            )

    unit_risk = abs(entry_eff_allin - sl_eff_allin)
    return unit_risk


def validate_unit_risk(
    unit_risk: float,
    atr: Optional[float] = None,
    unit_risk_min_atr_mult: float = DEFAULT_UNIT_RISK_MIN_ATR_MULT,
) -> None:
    """
    Валидация минимального unit_risk.

    ТЗ 2.1.1.1: Если unit_risk_allin_net < unit_risk_min_abs
    или unit_risk_allin_net < unit_risk_min_atr_mult * ATR
    — вход запрещён (unit_risk_too_small_block)

    Args:
        unit_risk: Риск на единицу контракта (USD)
        atr: Average True Range (опционально, для ATR-based проверки)
        unit_risk_min_atr_mult: Минимальный множитель ATR для unit risk

    Raises:
        ValueError: Если unit_risk не удовлетворяет минимумам
    """
    # Проверка абсолютного минимума
    if unit_risk < ABS_MIN_UNIT_RISK_USD:
        raise ValueError(
            f"unit_risk {unit_risk:.6e} below absolute minimum "
            f"{ABS_MIN_UNIT_RISK_USD:.6e} USD (unit_risk_too_small_block)"
        )

    # Проверка ATR-based минимума (если ATR предоставлен)
    if atr is not None:
        if atr < ATR_EPS:
            raise ValueError(f"ATR {atr:.6e} is too small or negative")

        min_unit_risk_atr = unit_risk_min_atr_mult * atr

        if unit_risk < min_unit_risk_atr - EPS_FLOAT_COMPARE:
            raise ValueError(
                f"unit_risk {unit_risk:.6f} below ATR-based minimum "
                f"{min_unit_risk_atr:.6f} "
                f"(ATR={atr:.6f}, mult={unit_risk_min_atr_mult}) "
                f"(unit_risk_too_small_block)"
            )


# =============================================================================
# КОМПЛЕКСНЫЙ РАСЧЁТ С ВАЛИДАЦИЕЙ
# =============================================================================


def compute_effective_prices_with_validation(
    side: PositionSide,
    entry_price: float,
    tp_price: float,
    sl_price: float,
    spread_bps: float,
    fee_entry_bps: float,
    fee_exit_bps: float,
    slippage_entry_bps: float,
    slippage_tp_bps: float,
    slippage_stop_bps: float,
    impact_entry_bps: float,
    impact_exit_bps: float,
    impact_stop_bps: float,
    stop_slippage_mult: float = DEFAULT_STOP_SLIPPAGE_MULT,
    atr: Optional[float] = None,
    unit_risk_min_atr_mult: float = DEFAULT_UNIT_RISK_MIN_ATR_MULT,
) -> tuple[float, float, float, float]:
    """
    Комплексный расчёт эффективных цен с валидацией unit_risk.

    Возвращает:
        (entry_eff_allin, tp_eff_allin, sl_eff_allin, unit_risk_allin_net)

    Raises:
        ValueError: Если параметры некорректны или unit_risk слишком мал
    """
    # 1. Вычисляем эффективные цены
    entry_eff, tp_eff, sl_eff = calculate_effective_prices(
        side=side,
        entry_price=entry_price,
        tp_price=tp_price,
        sl_price=sl_price,
        spread_bps=spread_bps,
        fee_entry_bps=fee_entry_bps,
        fee_exit_bps=fee_exit_bps,
        slippage_entry_bps=slippage_entry_bps,
        slippage_tp_bps=slippage_tp_bps,
        slippage_stop_bps=slippage_stop_bps,
        impact_entry_bps=impact_entry_bps,
        impact_exit_bps=impact_exit_bps,
        impact_stop_bps=impact_stop_bps,
        stop_slippage_mult=stop_slippage_mult,
    )

    # 2. Вычисляем unit_risk
    unit_risk = calculate_unit_risk_allin_net(
        side=side,
        entry_eff_allin=entry_eff,
        sl_eff_allin=sl_eff,
    )

    # 3. Валидируем unit_risk
    validate_unit_risk(
        unit_risk=unit_risk,
        atr=atr,
        unit_risk_min_atr_mult=unit_risk_min_atr_mult,
    )

    return entry_eff, tp_eff, sl_eff, unit_risk
