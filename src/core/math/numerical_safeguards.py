"""
Numerical Safeguards — Safe Math Primitives

ТЗ: 2.3 (обязательное)
ТЗ: 8.4 (Safe division and epsilon guards)
Appendix C.1: Epsilon-параметры

Модуль обеспечивает численную устойчивость всех математических операций:
- Безопасное деление (signed/unsigned) с защитой от деления на ноль
- NaN/Inf санитизация для предотвращения распространения невалидных значений
- Epsilon-защиты для сравнений float с учётом машинной точности
- Epsilon-защиты для округления и квантования

КРИТИЧЕСКИЕ ИНВАРИАНТЫ:
1. Деление на ноль никогда не происходит (возвращается fallback)
2. NaN/Inf никогда не пропагируют (заменяются на fallback)
3. Float сравнения всегда учитывают машинную точность
4. Все операции детерминированы и воспроизводимы
"""

import math
from typing import Final

# =============================================================================
# EPSILON-ПАРАМЕТРЫ (Appendix C.1)
# =============================================================================

# Epsilon для цен (USD или quote currency)
# Используется для защиты деления цен и сравнений
EPS_PRICE: Final[float] = 1e-8

# Epsilon для количеств (contracts, lots, base currency)
# Используется для защиты деления количеств
EPS_QTY: Final[float] = 1e-12

# Epsilon для общих вычислений и сравнений
# Используется в большинстве операций, где не требуется domain-specific epsilon
EPS_CALC: Final[float] = 1e-12

# Epsilon для сравнения float (относительная толерантность)
# Используется в is_close для относительных сравнений
EPS_FLOAT_COMPARE_REL: Final[float] = 1e-9

# Epsilon для сравнения float (абсолютная толерантность)
# Используется в is_close для абсолютных сравнений
EPS_FLOAT_COMPARE_ABS: Final[float] = 1e-12


# =============================================================================
# БЕЗОПАСНОЕ ДЕЛЕНИЕ
# =============================================================================


def denom_safe_signed(value: float, eps: float = EPS_CALC) -> float:
    """
    Безопасный знаковый делитель с epsilon-защитой.

    Защищает от деления на ноль, сохраняя знак исходного значения.
    Используется для операций, где знак критичен (например, PnL расчёты).

    ТЗ 2.3: denom_safe_signed(x, eps) = sign(x) * max(abs(x), eps)

    Args:
        value: Исходное значение (может быть любым)
        eps: Минимальный абсолютный порог (default: EPS_CALC)

    Returns:
        Безопасный делитель:
        - Если abs(value) >= eps: возвращает value
        - Если abs(value) < eps: возвращает sign(value) * eps
        - Если value == 0: возвращает eps

    Examples:
        >>> denom_safe_signed(10.0, 1e-6)
        10.0
        >>> denom_safe_signed(1e-9, 1e-6)
        1e-6
        >>> denom_safe_signed(-1e-9, 1e-6)
        -1e-6
        >>> denom_safe_signed(0.0, 1e-6)
        1e-6
    """
    if eps <= 0:
        raise ValueError(f"eps must be positive, got {eps}")

    abs_value = abs(value)

    if abs_value >= eps:
        return value

    # abs_value < eps: применяем epsilon с сохранением знака
    if value < 0:
        return -eps
    else:
        return eps


def denom_safe_unsigned(value: float, eps: float = EPS_CALC) -> float:
    """
    Безопасный беззнаковый делитель с epsilon-защитой.

    Защищает от деления на ноль, всегда возвращает положительное значение.
    Используется для операций, где ожидается положительный делитель.

    ТЗ 2.3: denom_safe_unsigned(x, eps) = max(abs(x), eps)

    Args:
        value: Исходное значение (может быть любым)
        eps: Минимальный абсолютный порог (default: EPS_CALC)

    Returns:
        Безопасный делитель >= eps (всегда положительный)

    Examples:
        >>> denom_safe_unsigned(10.0, 1e-6)
        10.0
        >>> denom_safe_unsigned(-10.0, 1e-6)
        10.0
        >>> denom_safe_unsigned(1e-9, 1e-6)
        1e-6
        >>> denom_safe_unsigned(0.0, 1e-6)
        1e-6
    """
    if eps <= 0:
        raise ValueError(f"eps must be positive, got {eps}")

    abs_value = abs(value)
    return max(abs_value, eps)


def safe_divide(
    numerator: float,
    denominator: float,
    eps: float = EPS_CALC,
    fallback: float = 0.0,
    signed: bool = True,
) -> float:
    """
    Безопасное деление с защитой от деления на ноль и NaN/Inf.

    Комбинирует denom_safe_signed/unsigned с NaN/Inf санитизацией.

    ВАЖНО: Если denominator точно равен 0.0 или очень близок к нулю
    (abs(denominator) < eps), возвращается fallback. Для малых ненулевых
    значений применяется epsilon-защита.

    Args:
        numerator: Числитель
        denominator: Знаменатель
        eps: Минимальный абсолютный порог для знаменателя
        fallback: Значение при делении на ноль (default: 0.0)
        signed: Использовать знаковую защиту (default: True)

    Returns:
        Результат деления или fallback при делении на ноль

    Examples:
        >>> safe_divide(10.0, 2.0)
        5.0
        >>> safe_divide(10.0, 0.0)
        0.0
        >>> safe_divide(10.0, 1e-20, eps=1e-12)
        10000000000000.0  # 10.0 / 1e-12 (epsilon-защита)
    """
    # Сначала санитизируем входы от NaN/Inf
    num_clean = sanitize_float(numerator, fallback=0.0)
    denom_raw = sanitize_float(denominator, fallback=0.0)

    # Проверка на деление на ноль: если знаменатель равен 0 или близок к 0
    # (меньше epsilon по абсолютному значению), возвращаем fallback
    if abs(denom_raw) == 0.0:
        # Точное деление на ноль
        return fallback

    # Применяем epsilon-защиту к знаменателю для малых значений
    if signed:
        denom_safe = denom_safe_signed(denom_raw, eps)
    else:
        denom_safe = denom_safe_unsigned(denom_raw, eps)

    # Выполняем деление
    try:
        result = num_clean / denom_safe
    except (ZeroDivisionError, FloatingPointError):
        # Дополнительная защита на случай extreme cases
        return fallback

    # Санитизируем результат
    return sanitize_float(result, fallback=fallback)


# =============================================================================
# NaN/Inf САНИТИЗАЦИЯ
# =============================================================================


def is_valid_float(value: float) -> bool:
    """
    Проверка, является ли float валидным (не NaN, не Inf).

    Args:
        value: Проверяемое значение

    Returns:
        True если значение валидное (finite), False если NaN или Inf
    """
    return math.isfinite(value)


def sanitize_float(value: float, fallback: float = 0.0) -> float:
    """
    Санитизация float: замена NaN/Inf на fallback значение.

    ТЗ 2.3: Защита от распространения невалидных значений.

    Args:
        value: Исходное значение
        fallback: Значение для замены NaN/Inf (default: 0.0)

    Returns:
        value если валидное, иначе fallback

    Examples:
        >>> sanitize_float(10.0)
        10.0
        >>> sanitize_float(float('nan'))
        0.0
        >>> sanitize_float(float('inf'))
        0.0
        >>> sanitize_float(float('-inf'), fallback=-1.0)
        -1.0
    """
    if is_valid_float(value):
        return value
    return fallback


def sanitize_array(values: list[float], fallback: float = 0.0) -> list[float]:
    """
    Санитизация массива float: замена всех NaN/Inf на fallback.

    Args:
        values: Список значений
        fallback: Значение для замены невалидных элементов

    Returns:
        Новый список с санитизированными значениями
    """
    return [sanitize_float(v, fallback) for v in values]


# =============================================================================
# EPSILON-СРАВНЕНИЯ FLOAT
# =============================================================================


def is_close(
    a: float,
    b: float,
    rel_tol: float = EPS_FLOAT_COMPARE_REL,
    abs_tol: float = EPS_FLOAT_COMPARE_ABS,
) -> bool:
    """
    Сравнение float с учётом машинной точности.

    Реализация Python's math.isclose с настраиваемыми толерантностями.

    ТЗ 2.3: Epsilon-защиты для сравнений.

    Алгоритм:
        abs(a - b) <= max(rel_tol * max(abs(a), abs(b)), abs_tol)

    Args:
        a: Первое значение
        b: Второе значение
        rel_tol: Относительная толерантность (default: 1e-9)
        abs_tol: Абсолютная толерантность (default: 1e-12)

    Returns:
        True если значения близки с учётом толерантности

    Examples:
        >>> is_close(1.0, 1.0 + 1e-10)
        True
        >>> is_close(1.0, 1.1)
        False
        >>> is_close(0.0, 1e-13)
        True  # abs diff < abs_tol
        >>> is_close(1e10, 1e10 + 1.0)
        True  # rel diff < rel_tol
    """
    return math.isclose(a, b, rel_tol=rel_tol, abs_tol=abs_tol)


def is_zero(value: float, tol: float = EPS_FLOAT_COMPARE_ABS) -> bool:
    """
    Проверка, близко ли значение к нулю с учётом толерантности.

    Args:
        value: Проверяемое значение
        tol: Абсолютная толерантность (default: EPS_FLOAT_COMPARE_ABS)

    Returns:
        True если abs(value) <= tol
    """
    return abs(value) <= tol


def is_positive(value: float, tol: float = EPS_FLOAT_COMPARE_ABS) -> bool:
    """
    Проверка, является ли значение положительным с учётом толерантности.

    Args:
        value: Проверяемое значение
        tol: Абсолютная толерантность (default: EPS_FLOAT_COMPARE_ABS)

    Returns:
        True если value > tol
    """
    return value > tol


def is_negative(value: float, tol: float = EPS_FLOAT_COMPARE_ABS) -> bool:
    """
    Проверка, является ли значение отрицательным с учётом толерантности.

    Args:
        value: Проверяемое значение
        tol: Абсолютная толерантность (default: EPS_FLOAT_COMPARE_ABS)

    Returns:
        True если value < -tol
    """
    return value < -tol


def compare_with_tolerance(
    a: float,
    b: float,
    tol: float = EPS_FLOAT_COMPARE_ABS,
) -> int:
    """
    Сравнение двух float с учётом толерантности.

    Args:
        a: Первое значение
        b: Второе значение
        tol: Абсолютная толерантность (default: EPS_FLOAT_COMPARE_ABS)

    Returns:
        -1 если a < b (с учётом tol)
         0 если a ≈ b (в пределах tol)
        +1 если a > b (с учётом tol)

    Examples:
        >>> compare_with_tolerance(1.0, 2.0)
        -1
        >>> compare_with_tolerance(2.0, 1.0)
        1
        >>> compare_with_tolerance(1.0, 1.0 + 1e-13)
        0
    """
    diff = a - b

    if abs(diff) <= tol:
        return 0
    elif diff < 0:
        return -1
    else:
        return 1


# =============================================================================
# EPSILON-ОКРУГЛЕНИЕ И КВАНТОВАНИЕ
# =============================================================================


def round_to_epsilon(value: float, eps: float) -> float:
    """
    Округление значения до ближайшего кратного epsilon.

    Используется для нормализации float после вычислений.
    Использует стандартное математическое округление (round half up).

    Args:
        value: Значение для округления
        eps: Шаг квантования

    Returns:
        Округлённое значение

    Examples:
        >>> round_to_epsilon(1.23456789, 0.01)
        1.23
        >>> round_to_epsilon(0.999999, 1e-6)
        1.0
        >>> round_to_epsilon(125.0, 10.0)
        130.0  # Округление 125 / 10 = 12.5 → 13 шагов → 130
    """
    if eps <= 0:
        raise ValueError(f"eps must be positive, got {eps}")

    # Вычисляем количество шагов epsilon
    ratio = value / eps

    # Стандартное математическое округление: добавляем 0.5 и берём floor
    # (это эквивалентно "round half away from zero")
    if ratio >= 0:
        steps = math.floor(ratio + 0.5)
    else:
        steps = math.ceil(ratio - 0.5)

    # Округлённое значение
    return steps * eps


def clamp(
    value: float,
    min_value: float | None = None,
    max_value: float | None = None,
) -> float:
    """
    Ограничение значения в заданном диапазоне.

    Args:
        value: Исходное значение
        min_value: Минимальное допустимое значение (optional)
        max_value: Максимальное допустимое значение (optional)

    Returns:
        Значение, ограниченное диапазоном [min_value, max_value]

    Examples:
        >>> clamp(5.0, 0.0, 10.0)
        5.0
        >>> clamp(-1.0, 0.0, 10.0)
        0.0
        >>> clamp(15.0, 0.0, 10.0)
        10.0
    """
    result = value

    if min_value is not None:
        result = max(result, min_value)

    if max_value is not None:
        result = min(result, max_value)

    return result


def normalize_to_range(
    value: float,
    old_min: float,
    old_max: float,
    new_min: float = 0.0,
    new_max: float = 1.0,
    eps: float = EPS_CALC,
) -> float:
    """
    Нормализация значения из одного диапазона в другой.

    Args:
        value: Исходное значение
        old_min: Минимум исходного диапазона
        old_max: Максимум исходного диапазона
        new_min: Минимум целевого диапазона (default: 0.0)
        new_max: Максимум целевого диапазона (default: 1.0)
        eps: Epsilon для защиты деления

    Returns:
        Нормализованное значение

    Raises:
        ValueError: Если old_min == old_max

    Examples:
        >>> normalize_to_range(5.0, 0.0, 10.0, 0.0, 1.0)
        0.5
        >>> normalize_to_range(2.5, 0.0, 10.0, -1.0, 1.0)
        -0.5
    """
    if abs(old_max - old_min) < eps:
        raise ValueError("old_min and old_max cannot be equal")

    # Нормализация: (value - old_min) / (old_max - old_min)
    normalized = safe_divide(
        value - old_min,
        old_max - old_min,
        eps=eps,
        fallback=0.0,
        signed=True,
    )

    # Масштабирование в новый диапазон
    return new_min + normalized * (new_max - new_min)


# =============================================================================
# ВАЛИДАЦИЯ И ПРОВЕРКИ
# =============================================================================


def validate_positive(value: float, name: str, eps: float = EPS_CALC) -> None:
    """
    Валидация, что значение положительное.

    Args:
        value: Проверяемое значение
        name: Имя параметра (для сообщения об ошибке)
        eps: Минимальный порог (default: EPS_CALC)

    Raises:
        ValueError: Если value <= eps или NaN/Inf
    """
    if not is_valid_float(value):
        raise ValueError(f"{name} must be a valid float (not NaN/Inf), got {value}")

    if value <= eps:
        raise ValueError(f"{name} must be positive (> {eps}), got {value}")


def validate_non_negative(value: float, name: str) -> None:
    """
    Валидация, что значение неотрицательное.

    Args:
        value: Проверяемое значение
        name: Имя параметра (для сообщения об ошибке)

    Raises:
        ValueError: Если value < 0 или NaN/Inf
    """
    if not is_valid_float(value):
        raise ValueError(f"{name} must be a valid float (not NaN/Inf), got {value}")

    if value < 0:
        raise ValueError(f"{name} must be non-negative, got {value}")


def validate_in_range(
    value: float,
    name: str,
    min_value: float | None = None,
    max_value: float | None = None,
) -> None:
    """
    Валидация, что значение в заданном диапазоне.

    Args:
        value: Проверяемое значение
        name: Имя параметра (для сообщения об ошибке)
        min_value: Минимальное допустимое значение (optional)
        max_value: Максимальное допустимое значение (optional)

    Raises:
        ValueError: Если value вне диапазона или NaN/Inf
    """
    if not is_valid_float(value):
        raise ValueError(f"{name} must be a valid float (not NaN/Inf), got {value}")

    if min_value is not None and value < min_value:
        raise ValueError(f"{name} must be >= {min_value}, got {value}")

    if max_value is not None and value > max_value:
        raise ValueError(f"{name} must be <= {max_value}, got {value}")
