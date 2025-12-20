"""
Тесты для Compounding — Safe Geometric Growth & Variance Drag

ТЗ: 2.1.2 (обязательное)
ТЗ: 2.2 (Тестирование)
Appendix C.3: Автотесты численной устойчивости

Проверяемые инварианты:
1. Domain restriction: r > -1 + eps
2. CompoundingDomainViolation при r ≤ -1 + eps
3. Численная стабильность log1p vs log
4. Детерминизм и воспроизводимость
5. Корректность variance drag метрик
6. Устойчивость к переполнениям
"""

import math

import pytest

from src.core.math.compounding import (
    COMPOUNDING_R_FLOOR_EPS,
    LOG1P_SWITCH_THRESHOLD,
    TARGET_RETURN_ANNUAL_DEFAULT,
    TRADES_PER_YEAR_DEFAULT,
    VARIANCE_DRAG_CRITICAL_FRAC,
    CompoundingDomainViolation,
    VarianceDragMetrics,
    check_variance_drag_critical,
    clamp_compound_rate_emergency,
    compound_equity,
    compound_equity_trajectory,
    compute_variance_drag_metrics,
    estimate_trades_per_year,
    safe_compound_rate,
    safe_log_return,
)


# =============================================================================
# ТЕСТЫ: Safe Compound Rate
# =============================================================================


class TestSafeCompoundRate:
    """Тесты safe_compound_rate: domain restriction и валидация."""
    
    def test_valid_positive_rate(self):
        """Позитивные rates проходят без изменений."""
        assert safe_compound_rate(0.05) == 0.05
        assert safe_compound_rate(0.001) == 0.001
        assert safe_compound_rate(1.0) == 1.0
        assert safe_compound_rate(10.0) == 10.0
    
    def test_valid_negative_rate(self):
        """Негативные rates в допустимом диапазоне проходят."""
        assert safe_compound_rate(-0.5) == -0.5
        assert safe_compound_rate(-0.1) == -0.1
        assert safe_compound_rate(-0.9) == -0.9
    
    def test_edge_valid_rate(self):
        """Rate на границе domain (r > -1 + eps) проходит."""
        # r = -1 + eps + tiny_delta должен пройти
        r_edge = -1.0 + COMPOUNDING_R_FLOOR_EPS + 1e-9
        assert safe_compound_rate(r_edge) == r_edge
    
    def test_domain_violation_exact_floor(self):
        """r = -1 + eps (точно на границе) → violation."""
        r_floor = -1.0 + COMPOUNDING_R_FLOOR_EPS
        with pytest.raises(CompoundingDomainViolation):
            safe_compound_rate(r_floor)
    
    def test_domain_violation_below_floor(self):
        """r < -1 + eps → violation."""
        with pytest.raises(CompoundingDomainViolation):
            safe_compound_rate(-1.0)
        
        with pytest.raises(CompoundingDomainViolation):
            safe_compound_rate(-1.5)
        
        with pytest.raises(CompoundingDomainViolation):
            safe_compound_rate(-2.0)
    
    def test_nan_inf_rejected(self):
        """NaN/Inf отвергаются."""
        with pytest.raises(ValueError, match="NaN/Inf"):
            safe_compound_rate(float('nan'))
        
        with pytest.raises(ValueError, match="NaN/Inf"):
            safe_compound_rate(float('inf'))
        
        with pytest.raises(ValueError, match="NaN/Inf"):
            safe_compound_rate(float('-inf'))
    
    def test_custom_eps(self):
        """Работа с кастомным epsilon."""
        custom_eps = 1e-3
        r_edge = -1.0 + custom_eps + 1e-6
        
        # Должен пройти с custom_eps
        assert safe_compound_rate(r_edge, eps=custom_eps) == r_edge
        
        # Должен упасть с custom_eps
        with pytest.raises(CompoundingDomainViolation):
            safe_compound_rate(-0.999, eps=custom_eps)


class TestClampCompoundRateEmergency:
    """Тесты clamp_compound_rate_emergency: экстренный clamp для диагностики."""
    
    def test_valid_rate_unchanged(self):
        """Валидные rates не изменяются."""
        r, violated = clamp_compound_rate_emergency(0.05)
        assert r == 0.05
        assert violated is False
        
        r, violated = clamp_compound_rate_emergency(-0.5)
        assert r == -0.5
        assert violated is False
    
    def test_edge_valid_rate(self):
        """Rate на границе проходит."""
        r_edge = -1.0 + COMPOUNDING_R_FLOOR_EPS + 1e-9
        r, violated = clamp_compound_rate_emergency(r_edge)
        assert r == r_edge
        assert violated is False
    
    def test_clamp_at_floor(self):
        """r = -1 + eps → clamped."""
        r_floor = -1.0 + COMPOUNDING_R_FLOOR_EPS
        r_clamped, violated = clamp_compound_rate_emergency(r_floor)
        assert r_clamped == r_floor
        assert violated is True
    
    def test_clamp_below_floor(self):
        """r < -1 → clamped to floor."""
        r_clamped, violated = clamp_compound_rate_emergency(-1.0)
        assert r_clamped == -1.0 + COMPOUNDING_R_FLOOR_EPS
        assert violated is True
        
        r_clamped, violated = clamp_compound_rate_emergency(-2.0)
        assert r_clamped == -1.0 + COMPOUNDING_R_FLOOR_EPS
        assert violated is True
    
    def test_nan_inf_sanitized(self):
        """NaN/Inf санитизируются."""
        r_clamped, violated = clamp_compound_rate_emergency(float('nan'))
        # sanitize_float(nan, fallback=0.0) → 0.0
        # 0.0 > -1 + eps, поэтому violated=False
        assert r_clamped == 0.0
        assert violated is False


# =============================================================================
# ТЕСТЫ: Safe Log Return
# =============================================================================


class TestSafeLogReturn:
    """Тесты safe_log_return: численная стабильность log(1+r)."""
    
    def test_zero_return(self):
        """log(1 + 0) = 0."""
        result = safe_log_return(0.0)
        assert abs(result - 0.0) < 1e-15
    
    def test_small_positive_return(self):
        """Малые позитивные returns используют log1p."""
        # r = 0.001 < LOG1P_SWITCH_THRESHOLD → log1p
        r = 0.001
        result = safe_log_return(r)
        expected = math.log1p(r)
        assert abs(result - expected) < 1e-15
    
    def test_small_negative_return(self):
        """Малые негативные returns используют log1p."""
        # r = -0.001 < LOG1P_SWITCH_THRESHOLD → log1p
        r = -0.001
        result = safe_log_return(r)
        expected = math.log1p(r)
        assert abs(result - expected) < 1e-15
    
    def test_large_positive_return(self):
        """Большие позитивные returns используют log."""
        # r = 0.5 > LOG1P_SWITCH_THRESHOLD → log(1+r)
        r = 0.5
        result = safe_log_return(r)
        expected = math.log(1.0 + r)
        assert abs(result - expected) < 1e-15
    
    def test_large_negative_return(self):
        """Большие негативные returns используют log."""
        # r = -0.5 > LOG1P_SWITCH_THRESHOLD → log(1+r)
        r = -0.5
        result = safe_log_return(r)
        expected = math.log(1.0 + r)
        assert abs(result - expected) < 1e-15
    
    def test_threshold_boundary(self):
        """Returns на границе threshold."""
        r_boundary = LOG1P_SWITCH_THRESHOLD - 1e-10
        result = safe_log_return(r_boundary)
        expected = math.log1p(r_boundary)  # Должен использовать log1p
        assert abs(result - expected) < 1e-12
    
    def test_domain_check_enabled(self):
        """Domain check включён → violation при r ≤ -1 + eps."""
        with pytest.raises(CompoundingDomainViolation):
            safe_log_return(-1.0, check_domain=True)
    
    def test_domain_check_disabled(self):
        """Domain check отключён → можно вычислить log(1+r) для r > -1."""
        # r = -0.9 > -1 (технически валиден для log, но бы упал с check_domain=True)
        r = -0.9
        result = safe_log_return(r, check_domain=False)
        expected = math.log(1.0 + r)
        assert abs(result - expected) < 1e-12
    
    def test_nan_inf_rejected(self):
        """NaN/Inf отвергаются."""
        with pytest.raises(ValueError, match="NaN/Inf"):
            safe_log_return(float('nan'), check_domain=False)


# =============================================================================
# ТЕСТЫ: Compound Equity
# =============================================================================


class TestCompoundEquity:
    """Тесты compound_equity: геометрический рост."""
    
    def test_no_returns(self):
        """Пустой список returns → equity не меняется."""
        result = compound_equity(100.0, [])
        assert result == 100.0
    
    def test_zero_returns(self):
        """Нулевые returns → equity не меняется."""
        result = compound_equity(100.0, [0.0, 0.0, 0.0])
        assert abs(result - 100.0) < 1e-9
    
    def test_positive_returns(self):
        """Позитивные returns → рост equity."""
        # 100 * 1.1 * 1.2 = 132
        result = compound_equity(100.0, [0.1, 0.2])
        assert abs(result - 132.0) < 1e-9
    
    def test_negative_returns(self):
        """Негативные returns → снижение equity."""
        # 100 * 0.9 * 0.8 = 72
        result = compound_equity(100.0, [-0.1, -0.2])
        assert abs(result - 72.0) < 1e-9
    
    def test_mixed_returns(self):
        """Смешанные returns."""
        # 100 * 1.05 * 0.95 * 1.1 = 109.725
        result = compound_equity(100.0, [0.05, -0.05, 0.1])
        expected = 100.0 * 1.05 * 0.95 * 1.1
        assert abs(result - expected) < 1e-9
    
    def test_large_equity(self):
        """Большой initial equity."""
        result = compound_equity(1_000_000.0, [0.1])
        assert abs(result - 1_100_000.0) < 1e-6
    
    def test_small_equity(self):
        """Малый initial equity."""
        result = compound_equity(1.0, [0.5])
        assert abs(result - 1.5) < 1e-15
    
    def test_domain_violation(self):
        """Domain violation → exception."""
        with pytest.raises(CompoundingDomainViolation):
            compound_equity(100.0, [0.1, -1.0, 0.1])
    
    def test_invalid_initial_equity(self):
        """Невалидный initial equity → exception."""
        with pytest.raises(ValueError):
            compound_equity(0.0, [0.1])
        
        with pytest.raises(ValueError):
            compound_equity(-100.0, [0.1])
    
    def test_numerical_stability_many_small_returns(self):
        """Численная стабильность для многих малых returns."""
        # 1000 returns по 0.001
        returns = [0.001] * 1000
        result = compound_equity(100.0, returns)
        # (1 + 0.001)^1000 ≈ 2.717
        expected = 100.0 * (1.001 ** 1000)
        assert abs(result - expected) < 1e-6


class TestCompoundEquityTrajectory:
    """Тесты compound_equity_trajectory: полная траектория."""
    
    def test_no_returns(self):
        """Пустой список → траектория [initial_equity]."""
        result = compound_equity_trajectory(100.0, [])
        assert result == [100.0]
    
    def test_single_return(self):
        """Один return → траектория [E0, E1]."""
        result = compound_equity_trajectory(100.0, [0.1])
        assert len(result) == 2
        assert result[0] == 100.0
        assert abs(result[1] - 110.0) < 1e-9
    
    def test_multiple_returns(self):
        """Несколько returns → полная траектория."""
        result = compound_equity_trajectory(100.0, [0.1, 0.2])
        assert len(result) == 3
        assert result[0] == 100.0
        assert abs(result[1] - 110.0) < 1e-9
        assert abs(result[2] - 132.0) < 1e-9
    
    def test_trajectory_length(self):
        """Длина траектории = len(returns) + 1."""
        returns = [0.01] * 10
        result = compound_equity_trajectory(100.0, returns)
        assert len(result) == 11


# =============================================================================
# ТЕСТЫ: Variance Drag Metrics
# =============================================================================


class TestComputeVarianceDragMetrics:
    """Тесты compute_variance_drag_metrics: расчёт variance drag."""
    
    def test_constant_returns(self):
        """Константные returns → variance drag = 0."""
        returns = [0.01] * 100
        metrics = compute_variance_drag_metrics(returns, trades_per_year=100)
        
        assert abs(metrics.mean_return - 0.01) < 1e-9
        # Для константных returns: variance = 0 → variance drag ≈ 0
        assert abs(metrics.variance_drag_per_trade) < 1e-6
        assert abs(metrics.variance_drag_annual) < 1e-5
    
    def test_variable_returns(self):
        """Переменные returns → variance drag > 0."""
        returns = [0.02, -0.01, 0.03, -0.015, 0.025]
        metrics = compute_variance_drag_metrics(returns, trades_per_year=100)
        
        # Mean return
        expected_mean = sum(returns) / len(returns)
        assert abs(metrics.mean_return - expected_mean) < 1e-9
        
        # Geometric mean < arithmetic mean для переменных returns
        assert metrics.geometric_mean_return_per_trade < metrics.mean_return
        
        # Variance drag > 0
        assert metrics.variance_drag_per_trade > 0
        assert metrics.variance_drag_annual > 0
    
    def test_metrics_types(self):
        """Проверка типов возвращаемых значений."""
        returns = [0.01, 0.02]
        metrics = compute_variance_drag_metrics(returns, trades_per_year=100)
        
        assert isinstance(metrics, VarianceDragMetrics)
        assert isinstance(metrics.mean_return, float)
        assert isinstance(metrics.mean_log_return, float)
        assert isinstance(metrics.geometric_mean_return_per_trade, float)
        assert isinstance(metrics.variance_drag_per_trade, float)
        assert isinstance(metrics.variance_drag_annual, float)
        assert isinstance(metrics.geometric_return_annual, float)
        assert isinstance(metrics.arithmetic_return_annual_approx, float)
        assert isinstance(metrics.num_trades, int)
        # trades_per_year может быть int или float
        assert isinstance(metrics.trades_per_year, (int, float))
    
    def test_annual_extrapolation(self):
        """Годовая экстраполяция."""
        returns = [0.01, 0.02]
        metrics = compute_variance_drag_metrics(returns, trades_per_year=100)
        
        # Arithmetic approximation
        assert abs(
            metrics.arithmetic_return_annual_approx - metrics.mean_return * 100
        ) < 1e-9
        
        # Geometric annual
        expected_geo = math.exp(metrics.mean_log_return * 100) - 1.0
        assert abs(metrics.geometric_return_annual - expected_geo) < 1e-9
    
    def test_empty_returns(self):
        """Пустой список → exception."""
        with pytest.raises(ValueError, match="cannot be empty"):
            compute_variance_drag_metrics([])
    
    def test_invalid_trades_per_year(self):
        """Невалидный trades_per_year → exception."""
        with pytest.raises(ValueError, match="must be positive"):
            compute_variance_drag_metrics([0.01], trades_per_year=0)
        
        with pytest.raises(ValueError, match="must be positive"):
            compute_variance_drag_metrics([0.01], trades_per_year=-100)


class TestCheckVarianceDragCritical:
    """Тесты check_variance_drag_critical: проверка критичности."""
    
    def test_not_critical_low_drag(self):
        """Малый variance drag → не критично."""
        is_critical, ratio = check_variance_drag_critical(
            variance_drag_annual=0.02,
            target_return_annual=0.12,
            critical_frac=0.35
        )
        assert is_critical is False
        assert abs(ratio - 0.02 / 0.12) < 1e-9
    
    def test_critical_high_drag(self):
        """Большой variance drag → критично."""
        is_critical, ratio = check_variance_drag_critical(
            variance_drag_annual=0.05,
            target_return_annual=0.12,
            critical_frac=0.35
        )
        assert is_critical is True
        assert abs(ratio - 0.05 / 0.12) < 1e-9
    
    def test_edge_critical(self):
        """На границе критичности."""
        # Точно на границе: drag = critical_frac * target
        drag = 0.35 * 0.12
        is_critical, ratio = check_variance_drag_critical(
            variance_drag_annual=drag,
            target_return_annual=0.12,
            critical_frac=0.35
        )
        # Должен быть не критичен (> но не >=)
        assert is_critical is False
        
        # Чуть выше границы
        is_critical, ratio = check_variance_drag_critical(
            variance_drag_annual=drag + 1e-9,
            target_return_annual=0.12,
            critical_frac=0.35
        )
        assert is_critical is True
    
    def test_default_parameters(self):
        """Работа с параметрами по умолчанию."""
        is_critical, ratio = check_variance_drag_critical(
            variance_drag_annual=0.03
        )
        assert isinstance(is_critical, bool)
        assert isinstance(ratio, float)
    
    def test_invalid_target_return(self):
        """Невалидный target_return → exception."""
        with pytest.raises(ValueError, match="must be positive"):
            check_variance_drag_critical(0.03, target_return_annual=0)
        
        with pytest.raises(ValueError, match="must be positive"):
            check_variance_drag_critical(0.03, target_return_annual=-0.12)


# =============================================================================
# ТЕСТЫ: Utilities
# =============================================================================


class TestEstimateTradesPerYear:
    """Тесты estimate_trades_per_year: оценка частоты сделок."""
    
    def test_full_year(self):
        """Полный год → trades_per_year = num_trades."""
        result = estimate_trades_per_year(100, period_days=365.25)
        assert abs(result - 100.0) < 1e-6
    
    def test_quarter(self):
        """Квартал → экстраполяция на год."""
        result = estimate_trades_per_year(30, period_days=90)
        expected = 30 * (365.25 / 90)
        assert abs(result - expected) < 1e-6
    
    def test_month(self):
        """Месяц → экстраполяция."""
        result = estimate_trades_per_year(10, period_days=30)
        expected = 10 * (365.25 / 30)
        assert abs(result - expected) < 1e-6
    
    def test_zero_trades(self):
        """Ноль сделок → 0."""
        result = estimate_trades_per_year(0, period_days=365)
        assert result == 0.0
    
    def test_small_period(self):
        """Малый период → защита от деления."""
        result = estimate_trades_per_year(1, period_days=1e-15)
        # Должен вернуть fallback или очень большое число
        assert result > 0
    
    def test_invalid_inputs(self):
        """Невалидные входы → exception."""
        with pytest.raises(ValueError):
            estimate_trades_per_year(-1, period_days=365)
        
        with pytest.raises(ValueError):
            estimate_trades_per_year(10, period_days=0)
        
        with pytest.raises(ValueError):
            estimate_trades_per_year(10, period_days=-365)


# =============================================================================
# ТЕСТЫ: Integration & Invariants
# =============================================================================


class TestIntegrationInvariants:
    """Интеграционные тесты и проверка инвариантов."""
    
    def test_compound_log_equivalence(self):
        """
        Инвариант: compound через multiplication == compound через log sum.
        
        Equity(t_K) = Equity(t_0) × Π (1 + r_k)
        log(Equity(t_K)) = log(Equity(t_0)) + Σ log(1 + r_k)
        """
        returns = [0.05, -0.03, 0.08, -0.02, 0.04]
        initial = 1000.0
        
        # Прямое умножение
        equity_mult = initial
        for r in returns:
            equity_mult *= (1.0 + r)
        
        # Через compound_equity (log sum)
        equity_log = compound_equity(initial, returns)
        
        # Должны совпадать с высокой точностью
        assert abs(equity_mult - equity_log) < 1e-6
    
    def test_variance_drag_always_nonnegative(self):
        """
        Инвариант: variance drag >= 0 для переменных returns.
        
        Geometric mean <= Arithmetic mean (AM-GM inequality)
        """
        # Переменные returns
        returns = [0.01, 0.03, -0.01, 0.02, -0.005]
        metrics = compute_variance_drag_metrics(returns, trades_per_year=100)
        
        assert metrics.variance_drag_per_trade >= 0
        assert metrics.variance_drag_annual >= 0
        assert metrics.geometric_mean_return_per_trade <= metrics.mean_return
    
    def test_determinism(self):
        """Детерминизм: одинаковые inputs → одинаковые outputs."""
        returns = [0.02, -0.01, 0.03]
        
        result1 = compound_equity(100.0, returns)
        result2 = compound_equity(100.0, returns)
        assert result1 == result2
        
        metrics1 = compute_variance_drag_metrics(returns, trades_per_year=100)
        metrics2 = compute_variance_drag_metrics(returns, trades_per_year=100)
        assert metrics1 == metrics2
    
    def test_zero_variance_drag_for_constant_returns(self):
        """
        Инвариант: константные returns → variance drag = 0.
        
        Если все r_k одинаковы, то geometric mean = arithmetic mean.
        """
        returns = [0.015] * 50
        metrics = compute_variance_drag_metrics(returns, trades_per_year=100)
        
        # Variance drag должен быть очень близок к 0
        assert abs(metrics.variance_drag_per_trade) < 1e-9
        assert abs(metrics.variance_drag_annual) < 1e-8
    
    def test_overflow_protection(self):
        """Защита от переполнений при больших equity."""
        # Очень большой рост: 100% за 20 периодов → equity × 2^20
        returns = [1.0] * 20  # 100% каждый период
        result = compound_equity(1.0, returns)
        
        # Должен быть конечным (не inf)
        assert math.isfinite(result)
        assert result > 0
    
    def test_underflow_protection(self):
        """Защита от underflow при малых equity."""
        # Сильное падение: -50% за 20 периодов
        returns = [-0.5] * 20
        result = compound_equity(1_000_000.0, returns)
        
        # Должен быть конечным (не 0)
        assert math.isfinite(result)
        assert result > 0


# =============================================================================
# ТЕСТЫ: Edge Cases
# =============================================================================


class TestEdgeCases:
    """Граничные случаи и экстремальные сценарии."""
    
    def test_very_small_returns(self):
        """Очень малые returns (машинная точность)."""
        returns = [1e-15, -1e-15, 1e-14]
        result = compound_equity(100.0, returns)
        # Equity почти не изменяется
        assert abs(result - 100.0) < 1e-9
    
    def test_very_large_positive_returns(self):
        """Очень большие позитивные returns."""
        returns = [10.0, 5.0, 3.0]  # 1000%, 500%, 300%
        result = compound_equity(1.0, returns)
        expected = 1.0 * 11.0 * 6.0 * 4.0  # 264
        assert abs(result - expected) < 1e-6
    
    def test_alternating_returns(self):
        """Чередующиеся +/- returns."""
        returns = [0.1, -0.1] * 10
        result = compound_equity(100.0, returns)
        # 1.1 * 0.9 = 0.99 → падение на 1% каждые 2 периода
        expected = 100.0 * (0.99 ** 10)
        assert abs(result - expected) < 1e-6
    
    def test_many_returns(self):
        """Очень много returns (1000+)."""
        returns = [0.001] * 1000
        result = compound_equity(100.0, returns)
        # Должен завершиться без ошибок
        assert math.isfinite(result)
        assert result > 100.0
    
    def test_single_extreme_negative(self):
        """Один экстремальный negative return."""
        returns = [0.01, 0.01, -0.95, 0.01]  # -95% в середине
        result = compound_equity(100.0, returns)
        # 100 * 1.01 * 1.01 * 0.05 * 1.01 ≈ 5.15
        expected = 100.0 * 1.01 * 1.01 * 0.05 * 1.01
        assert abs(result - expected) < 1e-6
    
    def test_log_return_at_threshold(self):
        """Log return точно на пороге переключения."""
        r_threshold = LOG1P_SWITCH_THRESHOLD
        
        # Чуть ниже порога → log1p
        r_below = r_threshold - 1e-10
        result_below = safe_log_return(r_below)
        assert math.isfinite(result_below)
        
        # Чуть выше порога → log
        r_above = r_threshold + 1e-10
        result_above = safe_log_return(r_above)
        assert math.isfinite(result_above)
        
        # Результаты должны быть близки
        assert abs(result_below - result_above) < 1e-6
