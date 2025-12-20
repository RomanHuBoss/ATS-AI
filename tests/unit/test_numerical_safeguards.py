"""
Тесты для модуля Numerical Safeguards

ТЗ: 2.3 (обязательное)
ТЗ: 8.4 (Safe division and epsilon guards)
ТЗ: Appendix C.3 (обязательные автотесты)

Проверяет:
1. Безопасное деление (signed/unsigned)
2. NaN/Inf санитизацию
3. Epsilon-сравнения float
4. Округление и квантование
5. Валидацию параметров
6. Граничные случаи и устойчивость
"""


import pytest

from src.core.math.numerical_safeguards import (
    EPS_CALC,
    EPS_FLOAT_COMPARE_ABS,
    EPS_FLOAT_COMPARE_REL,
    EPS_PRICE,
    EPS_QTY,
    clamp,
    compare_with_tolerance,
    denom_safe_signed,
    denom_safe_unsigned,
    is_close,
    is_negative,
    is_positive,
    is_valid_float,
    is_zero,
    normalize_to_range,
    round_to_epsilon,
    safe_divide,
    sanitize_array,
    sanitize_float,
    validate_in_range,
    validate_non_negative,
    validate_positive,
)

# =============================================================================
# ТЕСТЫ БЕЗОПАСНОГО ДЕЛЕНИЯ
# =============================================================================


class TestDenomSafeSigned:
    """Тесты для denom_safe_signed"""

    def test_large_positive_value_unchanged(self) -> None:
        """Большие положительные значения остаются без изменений"""
        assert denom_safe_signed(100.0, eps=1e-6) == 100.0
        assert denom_safe_signed(1.0, eps=1e-6) == 1.0

    def test_large_negative_value_unchanged(self) -> None:
        """Большие отрицательные значения остаются без изменений"""
        assert denom_safe_signed(-100.0, eps=1e-6) == -100.0
        assert denom_safe_signed(-1.0, eps=1e-6) == -1.0

    def test_small_positive_value_clamped_to_eps(self) -> None:
        """Малые положительные значения ограничены eps"""
        result = denom_safe_signed(1e-9, eps=1e-6)
        assert result == 1e-6
        assert result > 0

    def test_small_negative_value_clamped_to_minus_eps(self) -> None:
        """Малые отрицательные значения ограничены -eps"""
        result = denom_safe_signed(-1e-9, eps=1e-6)
        assert result == -1e-6
        assert result < 0

    def test_zero_clamped_to_eps(self) -> None:
        """Ноль ограничен eps (положительный)"""
        result = denom_safe_signed(0.0, eps=1e-6)
        assert result == 1e-6
        assert result > 0

    def test_sign_preservation(self) -> None:
        """Знак сохраняется при всех значениях"""
        # Положительные
        assert denom_safe_signed(10.0, eps=1e-6) > 0
        assert denom_safe_signed(1e-9, eps=1e-6) > 0

        # Отрицательные
        assert denom_safe_signed(-10.0, eps=1e-6) < 0
        assert denom_safe_signed(-1e-9, eps=1e-6) < 0

        # Ноль → положительный eps
        assert denom_safe_signed(0.0, eps=1e-6) > 0

    def test_invalid_eps_raises(self) -> None:
        """Невалидный eps вызывает ошибку"""
        with pytest.raises(ValueError, match="eps must be positive"):
            denom_safe_signed(10.0, eps=0.0)

        with pytest.raises(ValueError, match="eps must be positive"):
            denom_safe_signed(10.0, eps=-1e-6)

    def test_boundary_at_eps(self) -> None:
        """Граничные случаи ровно на eps"""
        eps = 1e-6

        # Ровно eps: не изменяется
        assert denom_safe_signed(eps, eps=eps) == eps
        assert denom_safe_signed(-eps, eps=eps) == -eps

        # Чуть больше eps: не изменяется
        assert denom_safe_signed(eps * 1.1, eps=eps) == pytest.approx(eps * 1.1)
        assert denom_safe_signed(-eps * 1.1, eps=eps) == pytest.approx(-eps * 1.1)

        # Чуть меньше eps: ограничено
        assert denom_safe_signed(eps * 0.9, eps=eps) == eps
        assert denom_safe_signed(-eps * 0.9, eps=eps) == -eps


class TestDenomSafeUnsigned:
    """Тесты для denom_safe_unsigned"""

    def test_large_positive_value_unchanged(self) -> None:
        """Большие положительные значения остаются без изменений"""
        assert denom_safe_unsigned(100.0, eps=1e-6) == 100.0
        assert denom_safe_unsigned(1.0, eps=1e-6) == 1.0

    def test_large_negative_value_absolute(self) -> None:
        """Большие отрицательные значения → abs(value)"""
        assert denom_safe_unsigned(-100.0, eps=1e-6) == 100.0
        assert denom_safe_unsigned(-1.0, eps=1e-6) == 1.0

    def test_small_positive_value_clamped_to_eps(self) -> None:
        """Малые положительные значения ограничены eps"""
        result = denom_safe_unsigned(1e-9, eps=1e-6)
        assert result == 1e-6

    def test_small_negative_value_clamped_to_eps(self) -> None:
        """Малые отрицательные значения ограничены eps (положительный)"""
        result = denom_safe_unsigned(-1e-9, eps=1e-6)
        assert result == 1e-6
        assert result > 0

    def test_zero_clamped_to_eps(self) -> None:
        """Ноль ограничен eps"""
        result = denom_safe_unsigned(0.0, eps=1e-6)
        assert result == 1e-6

    def test_always_positive(self) -> None:
        """Результат всегда положительный"""
        assert denom_safe_unsigned(10.0, eps=1e-6) > 0
        assert denom_safe_unsigned(-10.0, eps=1e-6) > 0
        assert denom_safe_unsigned(0.0, eps=1e-6) > 0
        assert denom_safe_unsigned(1e-9, eps=1e-6) > 0

    def test_invalid_eps_raises(self) -> None:
        """Невалидный eps вызывает ошибку"""
        with pytest.raises(ValueError, match="eps must be positive"):
            denom_safe_unsigned(10.0, eps=0.0)

        with pytest.raises(ValueError, match="eps must be positive"):
            denom_safe_unsigned(10.0, eps=-1e-6)


class TestSafeDivide:
    """Тесты для safe_divide"""

    def test_normal_division(self) -> None:
        """Обычное деление работает корректно"""
        assert safe_divide(10.0, 2.0) == 5.0
        assert safe_divide(100.0, 4.0) == 25.0
        assert safe_divide(-10.0, 2.0) == -5.0

    def test_division_by_zero_returns_fallback(self) -> None:
        """Деление на ноль возвращает fallback"""
        assert safe_divide(10.0, 0.0, fallback=0.0) == 0.0
        assert safe_divide(10.0, 0.0, fallback=1.0) == 1.0

    def test_division_by_small_value_uses_eps(self) -> None:
        """Деление на малое значение использует eps"""
        result = safe_divide(10.0, 1e-20, eps=1e-12)
        # Знаменатель будет 1e-12, результат ~ 1e13
        assert result == pytest.approx(1e13, rel=1e-6)

    def test_nan_numerator_returns_fallback(self) -> None:
        """NaN в числителе возвращает fallback"""
        assert safe_divide(float("nan"), 2.0, fallback=0.0) == 0.0

    def test_nan_denominator_returns_fallback(self) -> None:
        """NaN в знаменателе возвращает fallback"""
        result = safe_divide(10.0, float("nan"), fallback=0.0, eps=1e-6)
        # NaN санитизируется в 0.0, затем возвращается fallback
        assert result == 0.0

    def test_inf_numerator_returns_fallback(self) -> None:
        """Inf в числителе возвращает fallback"""
        assert safe_divide(float("inf"), 2.0, fallback=0.0) == 0.0

    def test_signed_vs_unsigned_mode(self) -> None:
        """Режимы signed/unsigned работают корректно"""
        # Signed: сохраняет знак знаменателя
        result_signed = safe_divide(10.0, -1e-20, eps=1e-12, signed=True)
        assert result_signed < 0  # Отрицательный знаменатель

        # Unsigned: всегда положительный знаменатель
        result_unsigned = safe_divide(10.0, -1e-20, eps=1e-12, signed=False)
        assert result_unsigned > 0  # Положительный знаменатель


# =============================================================================
# ТЕСТЫ NaN/Inf САНИТИЗАЦИИ
# =============================================================================


class TestIsValidFloat:
    """Тесты для is_valid_float"""

    def test_normal_values_valid(self) -> None:
        """Обычные значения валидны"""
        assert is_valid_float(0.0)
        assert is_valid_float(1.0)
        assert is_valid_float(-1.0)
        assert is_valid_float(1e10)
        assert is_valid_float(-1e-10)

    def test_nan_invalid(self) -> None:
        """NaN невалиден"""
        assert not is_valid_float(float("nan"))

    def test_inf_invalid(self) -> None:
        """Inf невалиден"""
        assert not is_valid_float(float("inf"))
        assert not is_valid_float(float("-inf"))


class TestSanitizeFloat:
    """Тесты для sanitize_float"""

    def test_normal_values_unchanged(self) -> None:
        """Обычные значения не изменяются"""
        assert sanitize_float(10.0) == 10.0
        assert sanitize_float(-10.0) == -10.0
        assert sanitize_float(0.0) == 0.0

    def test_nan_replaced_with_fallback(self) -> None:
        """NaN заменяется на fallback"""
        assert sanitize_float(float("nan"), fallback=0.0) == 0.0
        assert sanitize_float(float("nan"), fallback=1.0) == 1.0

    def test_inf_replaced_with_fallback(self) -> None:
        """Inf заменяется на fallback"""
        assert sanitize_float(float("inf"), fallback=0.0) == 0.0
        assert sanitize_float(float("-inf"), fallback=-1.0) == -1.0

    def test_custom_fallback(self) -> None:
        """Пользовательский fallback работает"""
        assert sanitize_float(float("nan"), fallback=99.0) == 99.0


class TestSanitizeArray:
    """Тесты для sanitize_array"""

    def test_normal_array_unchanged(self) -> None:
        """Обычный массив не изменяется"""
        values = [1.0, 2.0, 3.0]
        result = sanitize_array(values)
        assert result == [1.0, 2.0, 3.0]

    def test_array_with_nan_sanitized(self) -> None:
        """Массив с NaN санитизируется"""
        values = [1.0, float("nan"), 3.0]
        result = sanitize_array(values, fallback=0.0)
        assert result == [1.0, 0.0, 3.0]

    def test_array_with_inf_sanitized(self) -> None:
        """Массив с Inf санитизируется"""
        values = [1.0, float("inf"), float("-inf"), 4.0]
        result = sanitize_array(values, fallback=0.0)
        assert result == [1.0, 0.0, 0.0, 4.0]


# =============================================================================
# ТЕСТЫ EPSILON-СРАВНЕНИЙ
# =============================================================================


class TestIsClose:
    """Тесты для is_close"""

    def test_exact_match(self) -> None:
        """Точное совпадение"""
        assert is_close(1.0, 1.0)
        assert is_close(0.0, 0.0)

    def test_close_values_within_tolerance(self) -> None:
        """Близкие значения в пределах толерантности"""
        assert is_close(1.0, 1.0 + 1e-10)
        assert is_close(1.0, 1.0 - 1e-10)

    def test_far_values_not_close(self) -> None:
        """Далёкие значения не близки"""
        assert not is_close(1.0, 2.0)
        assert not is_close(1.0, 1.1)

    def test_small_absolute_difference(self) -> None:
        """Малая абсолютная разница (вблизи нуля)"""
        # Абсолютная толерантность важна для малых значений
        assert is_close(0.0, 1e-13, abs_tol=1e-12)
        assert not is_close(0.0, 1e-10, abs_tol=1e-12)

    def test_relative_tolerance_for_large_values(self) -> None:
        """Относительная толерантность для больших значений"""
        # 1e10 и 1e10 + 1.0 близки относительно (rel_tol ~ 1e-9)
        assert is_close(1e10, 1e10 + 1.0, rel_tol=1e-9)

        # Но 1e10 и 1e10 + 100 не близки
        assert not is_close(1e10, 1e10 + 100.0, rel_tol=1e-9)

    def test_custom_tolerances(self) -> None:
        """Пользовательские толерантности работают"""
        # Строгая толерантность
        assert not is_close(1.0, 1.01, rel_tol=1e-6, abs_tol=1e-6)

        # Мягкая толерантность
        assert is_close(1.0, 1.01, rel_tol=1e-1, abs_tol=1e-1)


class TestIsZero:
    """Тесты для is_zero"""

    def test_exact_zero(self) -> None:
        """Точный ноль"""
        assert is_zero(0.0)

    def test_near_zero_within_tolerance(self) -> None:
        """Значения вблизи нуля в пределах толерантности"""
        assert is_zero(1e-13, tol=1e-12)
        assert is_zero(-1e-13, tol=1e-12)

    def test_not_zero(self) -> None:
        """Не ноль"""
        assert not is_zero(1.0)
        assert not is_zero(0.1)
        assert not is_zero(1e-10, tol=1e-12)


class TestIsPositive:
    """Тесты для is_positive"""

    def test_positive_values(self) -> None:
        """Положительные значения"""
        assert is_positive(1.0)
        assert is_positive(0.1)
        assert is_positive(1e10)

    def test_negative_values_not_positive(self) -> None:
        """Отрицательные значения не положительные"""
        assert not is_positive(-1.0)
        assert not is_positive(-0.1)

    def test_zero_not_positive(self) -> None:
        """Ноль не положительный (с учётом толерантности)"""
        assert not is_positive(0.0, tol=1e-12)
        assert not is_positive(1e-13, tol=1e-12)

    def test_just_above_tolerance_is_positive(self) -> None:
        """Значение чуть выше толерантности положительное"""
        tol = 1e-12
        assert is_positive(tol * 2, tol=tol)


class TestIsNegative:
    """Тесты для is_negative"""

    def test_negative_values(self) -> None:
        """Отрицательные значения"""
        assert is_negative(-1.0)
        assert is_negative(-0.1)
        assert is_negative(-1e10)

    def test_positive_values_not_negative(self) -> None:
        """Положительные значения не отрицательные"""
        assert not is_negative(1.0)
        assert not is_negative(0.1)

    def test_zero_not_negative(self) -> None:
        """Ноль не отрицательный (с учётом толерантности)"""
        assert not is_negative(0.0, tol=1e-12)
        assert not is_negative(-1e-13, tol=1e-12)

    def test_just_below_minus_tolerance_is_negative(self) -> None:
        """Значение чуть ниже -толерантности отрицательное"""
        tol = 1e-12
        assert is_negative(-tol * 2, tol=tol)


class TestCompareWithTolerance:
    """Тесты для compare_with_tolerance"""

    def test_a_less_than_b(self) -> None:
        """a < b"""
        assert compare_with_tolerance(1.0, 2.0) == -1
        assert compare_with_tolerance(-10.0, -5.0) == -1

    def test_a_greater_than_b(self) -> None:
        """a > b"""
        assert compare_with_tolerance(2.0, 1.0) == 1
        assert compare_with_tolerance(-5.0, -10.0) == 1

    def test_a_approximately_equal_to_b(self) -> None:
        """a ≈ b"""
        assert compare_with_tolerance(1.0, 1.0) == 0
        assert compare_with_tolerance(1.0, 1.0 + 1e-13, tol=1e-12) == 0

    def test_tolerance_threshold(self) -> None:
        """Граница толерантности"""
        tol = 1e-12

        # В пределах толерантности: равны
        assert compare_with_tolerance(1.0, 1.0 + tol * 0.5, tol=tol) == 0

        # Вне толерантности: не равны
        assert compare_with_tolerance(1.0, 1.0 + tol * 2, tol=tol) == -1


# =============================================================================
# ТЕСТЫ ОКРУГЛЕНИЯ И КВАНТОВАНИЯ
# =============================================================================


class TestRoundToEpsilon:
    """Тесты для round_to_epsilon"""

    def test_round_to_decimal_places(self) -> None:
        """Округление до десятичных разрядов"""
        assert round_to_epsilon(1.23456789, 0.01) == 1.23
        assert round_to_epsilon(1.23456789, 0.001) == 1.235

    def test_round_near_integer(self) -> None:
        """Округление вблизи целого"""
        # 0.9999995 / 1e-6 = 999999.5, округляется до 1000000 шагов = 1.0
        assert round_to_epsilon(0.9999995, 1e-6) == pytest.approx(1.0)
        # 1.0000005 / 1e-6 = 1000000.5, округляется до 1000001 шагов ≈ 1.000001
        # но мы хотим округление к ближайшему целому, так что это 1.0
        assert round_to_epsilon(1.0000004, 1e-6) == pytest.approx(1.0)

    def test_round_to_large_epsilon(self) -> None:
        """Округление с большим epsilon"""
        assert round_to_epsilon(123.456, 10.0) == 120.0
        assert round_to_epsilon(125.0, 10.0) == 130.0

    def test_invalid_eps_raises(self) -> None:
        """Невалидный eps вызывает ошибку"""
        with pytest.raises(ValueError, match="eps must be positive"):
            round_to_epsilon(1.0, 0.0)

        with pytest.raises(ValueError, match="eps must be positive"):
            round_to_epsilon(1.0, -0.01)


class TestClamp:
    """Тесты для clamp"""

    def test_value_within_range_unchanged(self) -> None:
        """Значение в пределах диапазона не изменяется"""
        assert clamp(5.0, 0.0, 10.0) == 5.0

    def test_value_below_min_clamped(self) -> None:
        """Значение ниже минимума ограничено"""
        assert clamp(-1.0, 0.0, 10.0) == 0.0
        assert clamp(-100.0, 0.0, 10.0) == 0.0

    def test_value_above_max_clamped(self) -> None:
        """Значение выше максимума ограничено"""
        assert clamp(15.0, 0.0, 10.0) == 10.0
        assert clamp(100.0, 0.0, 10.0) == 10.0

    def test_only_min_limit(self) -> None:
        """Только нижний предел"""
        assert clamp(-5.0, min_value=0.0) == 0.0
        assert clamp(5.0, min_value=0.0) == 5.0

    def test_only_max_limit(self) -> None:
        """Только верхний предел"""
        assert clamp(15.0, max_value=10.0) == 10.0
        assert clamp(5.0, max_value=10.0) == 5.0

    def test_no_limits(self) -> None:
        """Без пределов — значение не изменяется"""
        assert clamp(5.0) == 5.0
        assert clamp(-100.0) == -100.0


class TestNormalizeToRange:
    """Тесты для normalize_to_range"""

    def test_normalize_to_0_1(self) -> None:
        """Нормализация в диапазон [0, 1]"""
        # Середина диапазона [0, 10] → 0.5
        assert normalize_to_range(5.0, 0.0, 10.0, 0.0, 1.0) == pytest.approx(0.5)

        # Начало диапазона → 0.0
        assert normalize_to_range(0.0, 0.0, 10.0, 0.0, 1.0) == pytest.approx(0.0)

        # Конец диапазона → 1.0
        assert normalize_to_range(10.0, 0.0, 10.0, 0.0, 1.0) == pytest.approx(1.0)

    def test_normalize_to_custom_range(self) -> None:
        """Нормализация в произвольный диапазон"""
        # [0, 10] → [-1, 1]: середина = 0
        assert normalize_to_range(5.0, 0.0, 10.0, -1.0, 1.0) == pytest.approx(0.0)

        # [0, 10] → [-1, 1]: четверть = -0.5
        assert normalize_to_range(2.5, 0.0, 10.0, -1.0, 1.0) == pytest.approx(-0.5)

    def test_normalize_with_negative_range(self) -> None:
        """Нормализация с отрицательным исходным диапазоном"""
        # [-10, 0] → [0, 1]: середина = 0.5
        assert normalize_to_range(-5.0, -10.0, 0.0, 0.0, 1.0) == pytest.approx(0.5)

    def test_equal_min_max_raises(self) -> None:
        """Равные min и max вызывают ошибку"""
        with pytest.raises(ValueError, match="old_min and old_max cannot be equal"):
            normalize_to_range(5.0, 0.0, 0.0, 0.0, 1.0)


# =============================================================================
# ТЕСТЫ ВАЛИДАЦИИ
# =============================================================================


class TestValidatePositive:
    """Тесты для validate_positive"""

    def test_positive_value_passes(self) -> None:
        """Положительное значение проходит"""
        validate_positive(1.0, "test")
        validate_positive(0.1, "test")
        validate_positive(1e10, "test")

    def test_zero_fails(self) -> None:
        """Ноль не проходит"""
        with pytest.raises(ValueError, match="test must be positive"):
            validate_positive(0.0, "test")

    def test_negative_fails(self) -> None:
        """Отрицательное значение не проходит"""
        with pytest.raises(ValueError, match="test must be positive"):
            validate_positive(-1.0, "test")

    def test_nan_fails(self) -> None:
        """NaN не проходит"""
        with pytest.raises(ValueError, match="test must be a valid float"):
            validate_positive(float("nan"), "test")

    def test_inf_fails(self) -> None:
        """Inf не проходит"""
        with pytest.raises(ValueError, match="test must be a valid float"):
            validate_positive(float("inf"), "test")

    def test_custom_eps(self) -> None:
        """Пользовательский eps работает"""
        # Ниже eps — fail
        with pytest.raises(ValueError, match="test must be positive"):
            validate_positive(1e-9, "test", eps=1e-6)

        # Выше eps — pass
        validate_positive(1e-5, "test", eps=1e-6)


class TestValidateNonNegative:
    """Тесты для validate_non_negative"""

    def test_positive_value_passes(self) -> None:
        """Положительное значение проходит"""
        validate_non_negative(1.0, "test")

    def test_zero_passes(self) -> None:
        """Ноль проходит"""
        validate_non_negative(0.0, "test")

    def test_negative_fails(self) -> None:
        """Отрицательное значение не проходит"""
        with pytest.raises(ValueError, match="test must be non-negative"):
            validate_non_negative(-1.0, "test")

    def test_nan_fails(self) -> None:
        """NaN не проходит"""
        with pytest.raises(ValueError, match="test must be a valid float"):
            validate_non_negative(float("nan"), "test")


class TestValidateInRange:
    """Тесты для validate_in_range"""

    def test_value_within_range_passes(self) -> None:
        """Значение в диапазоне проходит"""
        validate_in_range(5.0, "test", min_value=0.0, max_value=10.0)

    def test_value_below_min_fails(self) -> None:
        """Значение ниже минимума не проходит"""
        with pytest.raises(ValueError, match="test must be >= 0.0"):
            validate_in_range(-1.0, "test", min_value=0.0, max_value=10.0)

    def test_value_above_max_fails(self) -> None:
        """Значение выше максимума не проходит"""
        with pytest.raises(ValueError, match="test must be <= 10.0"):
            validate_in_range(15.0, "test", min_value=0.0, max_value=10.0)

    def test_only_min_check(self) -> None:
        """Только проверка минимума"""
        validate_in_range(5.0, "test", min_value=0.0)
        with pytest.raises(ValueError, match="test must be >= 0.0"):
            validate_in_range(-1.0, "test", min_value=0.0)

    def test_only_max_check(self) -> None:
        """Только проверка максимума"""
        validate_in_range(5.0, "test", max_value=10.0)
        with pytest.raises(ValueError, match="test must be <= 10.0"):
            validate_in_range(15.0, "test", max_value=10.0)

    def test_nan_fails(self) -> None:
        """NaN не проходит"""
        with pytest.raises(ValueError, match="test must be a valid float"):
            validate_in_range(float("nan"), "test", min_value=0.0, max_value=10.0)


# =============================================================================
# ИНТЕГРАЦИОННЫЕ ТЕСТЫ
# =============================================================================


class TestIntegration:
    """Интеграционные тесты: комбинации функций"""

    def test_safe_division_chain(self) -> None:
        """Цепочка безопасных делений"""
        # (a / b) / c, где b и c могут быть малыми
        a = 100.0
        b = 1e-20  # Будет заменён на eps
        c = 2.0

        step1 = safe_divide(a, b, eps=1e-12)  # 100 / 1e-12 = 1e14
        step2 = safe_divide(step1, c)  # 1e14 / 2 = 5e13

        assert step2 == pytest.approx(5e13, rel=1e-6)

    def test_sanitize_then_divide(self) -> None:
        """Санитизация перед делением"""
        # NaN санитизируется, затем безопасное деление
        numerator = sanitize_float(float("nan"), fallback=10.0)
        result = safe_divide(numerator, 2.0)

        assert result == 5.0

    def test_round_after_division(self) -> None:
        """Округление после деления"""
        result = safe_divide(10.0, 3.0)  # 3.333...
        rounded = round_to_epsilon(result, 0.01)  # Округление до 0.01

        assert rounded == 3.33

    def test_clamp_normalized_value(self) -> None:
        """Ограничение нормализованного значения"""
        # Нормализация может выйти за пределы при экстремальных входах
        normalized = normalize_to_range(12.0, 0.0, 10.0, 0.0, 1.0)  # > 1.0
        clamped = clamp(normalized, 0.0, 1.0)

        assert clamped == 1.0

    def test_epsilon_constants_consistency(self) -> None:
        """Константы epsilon согласованы"""
        # Все epsilon должны быть положительными
        assert EPS_PRICE > 0
        assert EPS_QTY > 0
        assert EPS_CALC > 0
        assert EPS_FLOAT_COMPARE_REL > 0
        assert EPS_FLOAT_COMPARE_ABS > 0

        # Проверка порядков величин (санитарный тест)
        assert EPS_PRICE >= 1e-12
        assert EPS_QTY >= 1e-12
        assert EPS_CALC >= 1e-12
