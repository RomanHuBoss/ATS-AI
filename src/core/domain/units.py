"""
RiskUnits — Централизованный модуль конверсии единиц риска

ТЗ: 2.1.1.0 (обязательное)
Appendix C.1: epsilon-параметры

Единственный допустимый способ преобразований между:
- risk_amount_usd (USD)
- risk_pct_equity (безразмерная доля)
- R_value (безразмерная, нормированная)

ЗАПРЕЩЕНО смешивать единицы без явного конвертера из этого модуля.
"""

from typing import Final


# =============================================================================
# EPSILON-ПАРАМЕТРЫ (Appendix C.1)
# =============================================================================
# Минимальный equity для защиты от деления на ноль
PNL_EPS_USD: Final[float] = 1e-6

# Минимальный риск для конверсии в R-единицы
RISK_AMOUNT_EPS_USD: Final[float] = 1e-6

# Абсолютный минимум риска сделки (USD)
RISK_AMOUNT_MIN_ABSOLUTE_USD: Final[float] = 0.10

# Минимальный equity для расчёта риска в процентах
EQUITY_MIN_FOR_PCT_CALC_USD: Final[float] = 1.0


# =============================================================================
# БАЗОВЫЕ КОНВЕРТЕРЫ
# =============================================================================


def equity_effective(equity_before_usd: float) -> float:
    """
    Эффективный equity для расчётов.

    Защита от деления на ноль или отрицательного equity.

    Args:
        equity_before_usd: Equity до сделки (USD)

    Returns:
        max(equity_before_usd, pnl_eps_usd)
    """
    return max(equity_before_usd, PNL_EPS_USD)


def risk_pct_to_usd(risk_pct_equity: float, equity_before_usd: float) -> float:
    """
    Конверсия: риск в % equity → риск в USD

    ТЗ: risk_amount_usd = risk_pct_equity * equity_eff

    Args:
        risk_pct_equity: Риск в долях equity (безразмерная, например 0.005 = 0.5%)
        equity_before_usd: Equity до сделки (USD)

    Returns:
        Риск в USD

    Raises:
        ValueError: Если риск ниже абсолютного минимума
    """
    equity_eff = equity_effective(equity_before_usd)
    risk_usd = risk_pct_equity * equity_eff

    if risk_usd < RISK_AMOUNT_MIN_ABSOLUTE_USD:
        raise ValueError(
            f"Risk amount {risk_usd:.6f} USD below minimum "
            f"{RISK_AMOUNT_MIN_ABSOLUTE_USD} USD (risk_amount_below_minimum_block)"
        )

    return risk_usd


def risk_usd_to_pct(risk_amount_usd: float, equity_before_usd: float) -> float:
    """
    Конверсия: риск в USD → риск в % equity

    ТЗ: risk_pct_equity = risk_amount_usd / equity_eff

    Args:
        risk_amount_usd: Риск в USD
        equity_before_usd: Equity до сделки (USD)

    Returns:
        Риск в долях equity (безразмерная)

    Raises:
        ValueError: Если риск ниже абсолютного минимума
    """
    if risk_amount_usd < RISK_AMOUNT_MIN_ABSOLUTE_USD:
        raise ValueError(
            f"Risk amount {risk_amount_usd:.6f} USD below minimum "
            f"{RISK_AMOUNT_MIN_ABSOLUTE_USD} USD (risk_amount_below_minimum_block)"
        )

    equity_eff = equity_effective(equity_before_usd)
    return risk_amount_usd / equity_eff


def pnl_to_r_value(pnl_usd: float, risk_amount_usd: float) -> float:
    """
    Конверсия: PnL в USD → R-единицы

    ТЗ: R_value = PnL_usd / denom_safe_signed(risk_amount_usd, risk_amount_eps_usd)

    Args:
        pnl_usd: PnL в USD (может быть отрицательным)
        risk_amount_usd: Риск сделки в USD (положительный)

    Returns:
        PnL в R-единицах (безразмерный)
        Например: -1.0R означает потерю 1 единицы риска (SL hit)
    """
    # Безопасный знаковый делитель
    denom = max(abs(risk_amount_usd), RISK_AMOUNT_EPS_USD)
    if risk_amount_usd < 0:
        denom = -denom

    return pnl_usd / denom


def r_value_to_pnl(r_value: float, risk_amount_usd: float) -> float:
    """
    Конверсия: R-единицы → PnL в USD

    Args:
        r_value: Результат в R-единицах (например, 2.5R)
        risk_amount_usd: Риск сделки в USD

    Returns:
        PnL в USD
    """
    return r_value * risk_amount_usd


# =============================================================================
# ВАЛИДАЦИЯ
# =============================================================================


def validate_risk_amount(risk_amount_usd: float) -> None:
    """
    Проверка, что риск удовлетворяет абсолютному минимуму.

    Args:
        risk_amount_usd: Риск в USD

    Raises:
        ValueError: Если риск ниже минимума или отрицательный
    """
    if risk_amount_usd < 0:
        raise ValueError(f"Risk amount cannot be negative: {risk_amount_usd}")

    if risk_amount_usd < RISK_AMOUNT_MIN_ABSOLUTE_USD:
        raise ValueError(
            f"Risk amount {risk_amount_usd:.6f} USD below minimum "
            f"{RISK_AMOUNT_MIN_ABSOLUTE_USD} USD (risk_amount_below_minimum_block)"
        )


def validate_equity(equity_usd: float) -> None:
    """
    Проверка корректности equity.

    Args:
        equity_usd: Equity в USD

    Raises:
        ValueError: Если equity слишком мал или отрицательный
    """
    if equity_usd < 0:
        raise ValueError(f"Equity cannot be negative: {equity_usd}")

    if equity_usd < EQUITY_MIN_FOR_PCT_CALC_USD:
        raise ValueError(
            f"Equity {equity_usd:.2f} USD below minimum "
            f"{EQUITY_MIN_FOR_PCT_CALC_USD} USD for percentage calculations"
        )
