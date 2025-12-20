"""
Compounding — Safe Geometric Growth & Variance Drag

ТЗ: 2.1.2 (обязательное)
Appendix C.2: Epsilon-параметры

Модуль обеспечивает безопасное вычисление геометрического роста equity:
- Domain restriction для log(1+r): r > -1 + compounding_r_floor_eps
- Численно стабильный расчёт log-returns с использованием log1p
- Расчёт variance drag метрик
- Детекция критического variance drag
- Обработка экстремальных случаев (r < -1) через exception

КРИТИЧЕСКИЕ ИНВАРИАНТЫ:
1. Domain violation (r ≤ -1 + eps) → CompoundingDomainViolation exception
2. log1p используется для |r| < log1p_switch_threshold (численная стабильность)
3. Все операции детерминированы и воспроизводимы
4. NaN/Inf не распространяются (санитизация через numerical_safeguards)

ФОРМУЛЫ (ТЗ 2.1.2):
    Equity(t_K) = Equity(t_0) × Π (1 + r_k)
    log(Equity(t_K)) = log(Equity(t_0)) + Σ log(1 + r_k)
    
    mean_ln = mean(ln(1+r_k))  (geometric mean of log returns)
    g_trade = exp(mean_ln) - 1  (geometric mean return per trade)
    
    variance_drag_per_trade = E[r] - g_trade
    variance_drag_annual = variance_drag_per_trade * trades_per_year
    geo_return_annual = exp(mean_ln * trades_per_year) - 1
    arith_return_annual_approx = E[r] * trades_per_year
"""

import math
from typing import Final, NamedTuple

from src.core.math.numerical_safeguards import (
    EPS_CALC,
    is_valid_float,
    sanitize_float,
)

# =============================================================================
# COMPOUNDING EPSILON-ПАРАМЕТРЫ (Appendix C.2)
# =============================================================================

# Domain floor для log(1+r): r должно быть > -1 + COMPOUNDING_R_FLOOR_EPS
# При r ≤ -1 + eps → CompoundingDomainViolation
COMPOUNDING_R_FLOOR_EPS: Final[float] = 1.0e-6

# Порог переключения между log(1+r) и log1p(r) для численной стабильности
# Если |r| < LOG1P_SWITCH_THRESHOLD → используем log1p(r)
# Иначе → используем log(1 + r)
LOG1P_SWITCH_THRESHOLD: Final[float] = 0.01

# Критическая доля variance drag относительно целевой годовой доходности
# Если variance_drag_annual > VARIANCE_DRAG_CRITICAL_FRAC * target_return_annual
# → формируется предупреждение variance_drag_critical_event
VARIANCE_DRAG_CRITICAL_FRAC: Final[float] = 0.35

# Количество сделок в год по умолчанию (для оценки variance drag)
TRADES_PER_YEAR_DEFAULT: Final[int] = 140

# Целевая годовая доходность по умолчанию (для проверки variance drag)
TARGET_RETURN_ANNUAL_DEFAULT: Final[float] = 0.12


# =============================================================================
# EXCEPTIONS
# =============================================================================


class CompoundingDomainViolation(Exception):
    """
    Критическое нарушение domain для log(1+r): r ≤ -1 + eps.
    
    При возникновении требуется:
    1. Запись события compounding_domain_violation_event
    2. Активация DRP режима EMERGENCY
    3. Запрет новых входов до ручного подтверждения восстановления
    
    ТЗ 2.1.2: "если r_k ≤ -1 + compounding_r_floor_eps, фиксируется критический 
    инцидент compounding_domain_violation_event, активируется DRP-режим EMERGENCY"
    """
    pass


# =============================================================================
# SAFE COMPOUND RATE
# =============================================================================


def safe_compound_rate(r: float, eps: float = COMPOUNDING_R_FLOOR_EPS) -> float:
    """
    Проверка и clamp rate для безопасного compounding.
    
    ТЗ 2.1.2: r_k > -1 + compounding_r_floor_eps
    
    Args:
        r: Rate of return (безразмерный, например 0.05 для 5%)
        eps: Domain floor epsilon (default: COMPOUNDING_R_FLOOR_EPS)
    
    Returns:
        r если r > -1 + eps
    
    Raises:
        CompoundingDomainViolation: если r ≤ -1 + eps (требуется EMERGENCY)
        ValueError: если r содержит NaN/Inf
    
    Examples:
        >>> safe_compound_rate(0.05)
        0.05
        >>> safe_compound_rate(-0.5)
        -0.5
        >>> safe_compound_rate(-0.999999)  # -1 + 1e-6
        -0.999999
        >>> safe_compound_rate(-1.0)  # doctest: +SKIP
        Traceback (most recent call last):
            ...
        CompoundingDomainViolation: ...
    """
    if not is_valid_float(r):
        raise ValueError(f"Rate contains NaN/Inf: {r}")
    
    domain_floor = -1.0 + eps
    
    if r <= domain_floor:
        # ТЗ 2.1.2: CRITICAL VIOLATION → EMERGENCY
        raise CompoundingDomainViolation(
            f"Compounding domain violation: r={r:.12f} <= -1 + eps={eps:.12e}. "
            f"This requires EMERGENCY DRP activation. "
            f"Original r_k must be logged for audit."
        )
    
    return r


def clamp_compound_rate_emergency(
    r: float, 
    eps: float = COMPOUNDING_R_FLOOR_EPS
) -> tuple[float, bool]:
    """
    Экстренный clamp rate при domain violation (для диагностики).
    
    ТЗ 2.1.2: "записать факт r_k_raw, r_k_clamped = -1 + compounding_r_floor_eps,
    построить диагностический 'квази-лог' на clamped значении только для 
    предотвращения MathDomainError"
    
    ВНИМАНИЕ: Эта функция используется ТОЛЬКО для диагностики после того, как
    CompoundingDomainViolation уже был зафиксирован и DRP переведён в EMERGENCY.
    
    Args:
        r: Rate of return (может быть < -1)
        eps: Domain floor epsilon
    
    Returns:
        (clamped_r, was_violated):
            - clamped_r: безопасное значение для предотвращения MathDomainError
            - was_violated: True если r был < -1 + eps
    
    Examples:
        >>> clamp_compound_rate_emergency(0.05)
        (0.05, False)
        >>> clamp_compound_rate_emergency(-1.0)
        (-0.999999, True)
        >>> clamp_compound_rate_emergency(-2.0)
        (-0.999999, True)
    """
    if not is_valid_float(r):
        # Sanitize NaN/Inf перед проверкой
        r = sanitize_float(r, fallback=0.0)
    
    domain_floor = -1.0 + eps
    
    if r <= domain_floor:
        return (domain_floor, True)
    
    return (r, False)


# =============================================================================
# SAFE LOG RETURN
# =============================================================================


def safe_log_return(r: float, check_domain: bool = True) -> float:
    """
    Численно стабильное вычисление log(1 + r).
    
    ТЗ 2.1.2: 
    - Если |r| < log1p_switch_threshold → log1p(r)
    - Иначе → log(1 + r)
    - Доменная проверка выполняется до вызова log/log1p
    
    Args:
        r: Rate of return
        check_domain: Если True, выполняет safe_compound_rate проверку
    
    Returns:
        log(1 + r) вычисленный численно стабильно
    
    Raises:
        CompoundingDomainViolation: если check_domain=True и r ≤ -1 + eps
        ValueError: если r содержит NaN/Inf
    
    Examples:
        >>> abs(safe_log_return(0.0) - 0.0) < 1e-15
        True
        >>> abs(safe_log_return(0.001) - 0.0009995) < 1e-9
        True
        >>> abs(safe_log_return(0.05) - 0.04879) < 1e-5
        True
        >>> safe_log_return(-0.5)  # ~-0.693
        -0.6931471805599453
    """
    if check_domain:
        # Проверка domain: r > -1 + eps
        r = safe_compound_rate(r)
    else:
        # Минимальная проверка на NaN/Inf
        if not is_valid_float(r):
            raise ValueError(f"Rate contains NaN/Inf: {r}")
    
    # Численно стабильное вычисление
    if abs(r) < LOG1P_SWITCH_THRESHOLD:
        # Для малых r: log1p(r) более точен чем log(1+r)
        return math.log1p(r)
    else:
        # Для больших r: используем стандартный log
        return math.log(1.0 + r)


# =============================================================================
# COMPOUND EQUITY
# =============================================================================


def compound_equity(
    initial_equity: float,
    returns: list[float],
    check_domain: bool = True
) -> float:
    """
    Вычисление конечного equity через геометрический рост.
    
    ТЗ 2.1.2: Equity(t_K) = Equity(t_0) × Π (1 + r_k)
    
    Численно стабильная реализация через log:
    log(Equity(t_K)) = log(Equity(t_0)) + Σ log(1 + r_k)
    
    Args:
        initial_equity: Начальный equity (USD)
        returns: Список returns r_k (безразмерные)
        check_domain: Если True, проверяет domain для каждого r_k
    
    Returns:
        final_equity: Конечный equity после применения всех returns
    
    Raises:
        CompoundingDomainViolation: если check_domain=True и любой r_k ≤ -1 + eps
        ValueError: если initial_equity ≤ 0 или returns содержат NaN/Inf
    
    Examples:
        >>> compound_equity(100.0, [0.1, 0.2])  # 100 * 1.1 * 1.2 = 132
        132.0
        >>> compound_equity(100.0, [0.0, 0.0])
        100.0
        >>> abs(compound_equity(100.0, [-0.1, -0.2]) - 72.0) < 1e-9
        True
    """
    if initial_equity <= 0:
        raise ValueError(f"initial_equity must be positive, got {initial_equity}")
    
    if not returns:
        return initial_equity
    
    # Вычисление через log для численной стабильности
    log_equity = math.log(initial_equity)
    
    for r in returns:
        log_return = safe_log_return(r, check_domain=check_domain)
        log_equity += log_return
    
    final_equity = math.exp(log_equity)
    
    # Санитизация на случай переполнения
    return sanitize_float(final_equity, fallback=initial_equity)


def compound_equity_trajectory(
    initial_equity: float,
    returns: list[float],
    check_domain: bool = True
) -> list[float]:
    """
    Вычисление полной траектории equity через геометрический рост.
    
    Args:
        initial_equity: Начальный equity (USD)
        returns: Список returns r_k
        check_domain: Если True, проверяет domain для каждого r_k
    
    Returns:
        trajectory: Список equity значений [E_0, E_1, ..., E_K]
                   длины len(returns) + 1
    
    Examples:
        >>> compound_equity_trajectory(100.0, [0.1, 0.2])
        [100.0, 110.0, 132.0]
        >>> compound_equity_trajectory(100.0, [])
        [100.0]
    """
    if initial_equity <= 0:
        raise ValueError(f"initial_equity must be positive, got {initial_equity}")
    
    trajectory = [initial_equity]
    current_equity = initial_equity
    
    for r in returns:
        r_safe = safe_compound_rate(r) if check_domain else r
        current_equity = current_equity * (1.0 + r_safe)
        current_equity = sanitize_float(current_equity, fallback=trajectory[-1])
        trajectory.append(current_equity)
    
    return trajectory


# =============================================================================
# VARIANCE DRAG METRICS
# =============================================================================


class VarianceDragMetrics(NamedTuple):
    """
    Метрики variance drag для контроля геометрического vs арифметического роста.
    
    ТЗ 2.1.2: Контроль variance drag (обязательный автотест/мониторинг)
    """
    mean_return: float  # E[r] — среднее арифметическое return
    mean_log_return: float  # mean(ln(1+r)) — среднее логарифмическое
    geometric_mean_return_per_trade: float  # g_trade = exp(mean_ln) - 1
    variance_drag_per_trade: float  # E[r] - g_trade
    variance_drag_annual: float  # variance_drag_per_trade * trades_per_year
    geometric_return_annual: float  # exp(mean_ln * trades_per_year) - 1
    arithmetic_return_annual_approx: float  # E[r] * trades_per_year
    num_trades: int  # Количество сделок в выборке
    trades_per_year: float  # Количество сделок в год (для экстраполяции)


def compute_variance_drag_metrics(
    returns: list[float],
    trades_per_year: float = TRADES_PER_YEAR_DEFAULT,
    check_domain: bool = True
) -> VarianceDragMetrics:
    """
    Вычисление variance drag метрик.
    
    ТЗ 2.1.2:
        mean_ln = mean(ln(1+r_k))  (только для r_k > -1 + eps)
        g_trade = exp(mean_ln) - 1
        variance_drag_per_trade = E[r] - g_trade
        variance_drag_annual = variance_drag_per_trade * trades_per_year
        geo_return_annual = exp(mean_ln * trades_per_year) - 1
        arith_return_annual_approx = E[r] * trades_per_year
    
    Args:
        returns: Список returns r_k
        trades_per_year: Оценка количества сделок в год
        check_domain: Если True, проверяет domain для каждого r_k
    
    Returns:
        VarianceDragMetrics с полными метриками
    
    Raises:
        ValueError: если returns пустой или trades_per_year ≤ 0
        CompoundingDomainViolation: если check_domain=True и любой r_k ≤ -1 + eps
    
    Examples:
        >>> returns = [0.02, -0.01, 0.03, -0.015, 0.025]
        >>> metrics = compute_variance_drag_metrics(returns, trades_per_year=100)
        >>> metrics.num_trades
        5
        >>> abs(metrics.mean_return - 0.012) < 1e-9
        True
        >>> metrics.geometric_mean_return_per_trade < metrics.mean_return
        True
        >>> metrics.variance_drag_per_trade > 0
        True
    """
    if not returns:
        raise ValueError("returns list cannot be empty")
    
    if trades_per_year <= 0:
        raise ValueError(f"trades_per_year must be positive, got {trades_per_year}")
    
    # Вычисление средних
    mean_return = sum(returns) / len(returns)
    
    # Вычисление mean(ln(1+r))
    log_returns = [safe_log_return(r, check_domain=check_domain) for r in returns]
    mean_log_return = sum(log_returns) / len(log_returns)
    
    # Geometric mean return per trade
    geometric_mean_return_per_trade = math.exp(mean_log_return) - 1.0
    
    # Variance drag per trade
    variance_drag_per_trade = mean_return - geometric_mean_return_per_trade
    
    # Annual metrics
    variance_drag_annual = variance_drag_per_trade * trades_per_year
    geometric_return_annual = math.exp(mean_log_return * trades_per_year) - 1.0
    arithmetic_return_annual_approx = mean_return * trades_per_year
    
    return VarianceDragMetrics(
        mean_return=mean_return,
        mean_log_return=mean_log_return,
        geometric_mean_return_per_trade=geometric_mean_return_per_trade,
        variance_drag_per_trade=variance_drag_per_trade,
        variance_drag_annual=variance_drag_annual,
        geometric_return_annual=geometric_return_annual,
        arithmetic_return_annual_approx=arithmetic_return_annual_approx,
        num_trades=len(returns),
        trades_per_year=trades_per_year
    )


def check_variance_drag_critical(
    variance_drag_annual: float,
    target_return_annual: float = TARGET_RETURN_ANNUAL_DEFAULT,
    critical_frac: float = VARIANCE_DRAG_CRITICAL_FRAC
) -> tuple[bool, float]:
    """
    Проверка критичности variance drag.
    
    ТЗ 2.1.2: "если variance_drag_annual > variance_drag_critical_frac * 
    target_return_annual, формируется предупреждение variance_drag_critical_event"
    
    Args:
        variance_drag_annual: Годовой variance drag
        target_return_annual: Целевая годовая доходность (default: 0.12)
        critical_frac: Критическая доля (default: 0.35)
    
    Returns:
        (is_critical, drag_ratio):
            - is_critical: True если variance drag превышает порог
            - drag_ratio: variance_drag_annual / target_return_annual
    
    Examples:
        >>> check_variance_drag_critical(0.02, target_return_annual=0.12)
        (False, 0.16666666666666666)
        >>> check_variance_drag_critical(0.05, target_return_annual=0.12)
        (True, 0.4166666666666667)
    """
    if target_return_annual <= 0:
        raise ValueError(
            f"target_return_annual must be positive, got {target_return_annual}"
        )
    
    drag_ratio = variance_drag_annual / target_return_annual
    is_critical = drag_ratio > critical_frac
    
    return (is_critical, drag_ratio)


# =============================================================================
# UTILITIES
# =============================================================================


def estimate_trades_per_year(
    num_trades: int,
    period_days: float,
    eps: float = EPS_CALC
) -> float:
    """
    Оценка количества сделок в год из эмпирического окна.
    
    Args:
        num_trades: Количество сделок в окне
        period_days: Длительность окна в днях
        eps: Epsilon для защиты деления
    
    Returns:
        Оценка trades_per_year = num_trades * (365.25 / period_days)
    
    Examples:
        >>> abs(estimate_trades_per_year(30, 90) - 121.75) < 1e-6
        True
        >>> abs(estimate_trades_per_year(100, 365.25) - 100.0) < 1e-6
        True
    """
    if num_trades < 0:
        raise ValueError(f"num_trades must be non-negative, got {num_trades}")
    
    if period_days <= 0:
        raise ValueError(f"period_days must be positive, got {period_days}")
    
    # Защита от деления на очень малый period
    period_safe = max(period_days, eps)
    
    trades_per_year = num_trades * (365.25 / period_safe)
    
    return sanitize_float(trades_per_year, fallback=float(TRADES_PER_YEAR_DEFAULT))
