"""
Sanity-тест для модуля RiskUnits

ТЗ: 2.1.1.0 (обязательное)
ТЗ: 2.2 (проверка единиц риска)
ТЗ: Appendix C.3 (обязательные автотесты)

Проверяет:
1. Корректность конверсий USD ↔ % equity ↔ R-value
2. Инварианты преобразований (обратимость)
3. Валидацию минимальных значений
4. Epsilon-защиты
"""

import pytest

from src.core.domain.units import (
    RISK_AMOUNT_MIN_ABSOLUTE_USD,
    equity_effective,
    pnl_to_r_value,
    r_value_to_pnl,
    risk_pct_to_usd,
    risk_usd_to_pct,
    validate_equity,
    validate_risk_amount,
)


class TestEquityEffective:
    """Тесты для equity_effective"""

    def test_positive_equity_unchanged(self) -> None:
        """Положительный equity остаётся без изменений"""
        assert equity_effective(1000.0) == 1000.0
        assert equity_effective(10_000.0) == 10_000.0

    def test_zero_equity_protected(self) -> None:
        """Нулевой equity защищён epsilon"""
        result = equity_effective(0.0)
        assert result > 0
        assert result == 1e-6

    def test_negative_equity_protected(self) -> None:
        """Отрицательный equity защищён epsilon"""
        result = equity_effective(-100.0)
        assert result > 0
        assert result == 1e-6


class TestRiskConversions:
    """Тесты конверсий USD ↔ % equity"""

    def test_pct_to_usd_basic(self) -> None:
        """Базовая конверсия % → USD"""
        equity = 10_000.0
        risk_pct = 0.005  # 0.5%
        risk_usd = risk_pct_to_usd(risk_pct, equity)
        assert risk_usd == pytest.approx(50.0, abs=1e-6)

    def test_usd_to_pct_basic(self) -> None:
        """Базовая конверсия USD → %"""
        equity = 10_000.0
        risk_usd = 50.0
        risk_pct = risk_usd_to_pct(risk_usd, equity)
        assert risk_pct == pytest.approx(0.005, abs=1e-9)

    def test_roundtrip_pct_usd_pct(self) -> None:
        """Инвариант: % → USD → % возвращает исходное значение"""
        equity = 10_000.0
        risk_pct_original = 0.005
        risk_usd = risk_pct_to_usd(risk_pct_original, equity)
        risk_pct_back = risk_usd_to_pct(risk_usd, equity)
        assert risk_pct_back == pytest.approx(risk_pct_original, abs=1e-9)

    def test_roundtrip_usd_pct_usd(self) -> None:
        """Инвариант: USD → % → USD возвращает исходное значение"""
        equity = 10_000.0
        risk_usd_original = 50.0
        risk_pct = risk_usd_to_pct(risk_usd_original, equity)
        risk_usd_back = risk_pct_to_usd(risk_pct, equity)
        assert risk_usd_back == pytest.approx(risk_usd_original, abs=1e-6)

    def test_minimum_risk_rejection(self) -> None:
        """Риск ниже минимума отклоняется"""
        equity = 10_000.0
        risk_pct_too_small = 0.000001  # Даёт ~0.01 USD < 0.10 USD минимум

        with pytest.raises(ValueError, match="risk_amount_below_minimum_block"):
            risk_pct_to_usd(risk_pct_too_small, equity)

    def test_zero_equity_protected_in_conversion(self) -> None:
        """При equity=0 используется epsilon-защита, но риск всё равно ниже минимума"""
        # equity_eff = 1e-6, риск = 0.1 * 1e-6 = 1e-7 < 0.10 USD минимум
        # Должна быть ошибка
        with pytest.raises(ValueError, match="risk_amount_below_minimum_block"):
            risk_pct_to_usd(0.1, equity_before_usd=0.0)


class TestRValueConversions:
    """Тесты конверсий PnL ↔ R-value"""

    def test_pnl_to_r_positive(self) -> None:
        """Положительный PnL в R-единицах"""
        pnl = 100.0
        risk = 50.0
        r_value = pnl_to_r_value(pnl, risk)
        assert r_value == pytest.approx(2.0, abs=1e-6)

    def test_pnl_to_r_negative(self) -> None:
        """Отрицательный PnL (убыток) в R-единицах"""
        pnl = -50.0
        risk = 50.0
        r_value = pnl_to_r_value(pnl, risk)
        assert r_value == pytest.approx(-1.0, abs=1e-6)

    def test_r_to_pnl_positive(self) -> None:
        """R-value в положительный PnL"""
        r_value = 2.0
        risk = 50.0
        pnl = r_value_to_pnl(r_value, risk)
        assert pnl == pytest.approx(100.0, abs=1e-6)

    def test_r_to_pnl_negative(self) -> None:
        """R-value в отрицательный PnL"""
        r_value = -1.0
        risk = 50.0
        pnl = r_value_to_pnl(r_value, risk)
        assert pnl == pytest.approx(-50.0, abs=1e-6)

    def test_roundtrip_pnl_r_pnl(self) -> None:
        """Инвариант: PnL → R → PnL возвращает исходное значение"""
        pnl_original = 75.0
        risk = 50.0
        r_value = pnl_to_r_value(pnl_original, risk)
        pnl_back = r_value_to_pnl(r_value, risk)
        assert pnl_back == pytest.approx(pnl_original, abs=1e-6)

    def test_sl_hit_gives_minus_one_r(self) -> None:
        """
        Критический инвариант: SL hit даёт -1R

        ТЗ: unit_risk_allin_net = abs(entry - sl)
        При выходе по SL: PnL = -unit_risk → R = -1.0
        """
        unit_risk = 50.0
        risk_amount = unit_risk
        pnl_at_sl = -unit_risk

        r_value = pnl_to_r_value(pnl_at_sl, risk_amount)
        assert r_value == pytest.approx(-1.0, abs=1e-9)


class TestValidation:
    """Тесты валидации"""

    def test_validate_risk_amount_positive(self) -> None:
        """Корректный риск проходит валидацию"""
        validate_risk_amount(50.0)  # Не должно быть исключений
        validate_risk_amount(RISK_AMOUNT_MIN_ABSOLUTE_USD)  # Минимум допустим

    def test_validate_risk_amount_below_minimum(self) -> None:
        """Риск ниже минимума отклоняется"""
        with pytest.raises(ValueError, match="below minimum"):
            validate_risk_amount(0.05)

    def test_validate_risk_amount_negative(self) -> None:
        """Отрицательный риск отклоняется"""
        with pytest.raises(ValueError, match="cannot be negative"):
            validate_risk_amount(-10.0)

    def test_validate_equity_positive(self) -> None:
        """Корректный equity проходит валидацию"""
        validate_equity(10_000.0)  # Не должно быть исключений

    def test_validate_equity_negative(self) -> None:
        """Отрицательный equity отклоняется"""
        with pytest.raises(ValueError, match="cannot be negative"):
            validate_equity(-100.0)

    def test_validate_equity_too_small(self) -> None:
        """Слишком малый equity отклоняется"""
        with pytest.raises(ValueError, match="below minimum"):
            validate_equity(0.5)


class TestEdgeCases:
    """Тесты граничных случаев"""

    def test_very_small_risk_protected_by_epsilon(self) -> None:
        """Очень малый риск защищён epsilon в конверсии R"""
        pnl = 10.0
        risk_tiny = 1e-9  # Меньше epsilon
        r_value = pnl_to_r_value(pnl, risk_tiny)
        # Должно использовать epsilon, не деление на ноль
        assert r_value > 0
        assert not (r_value != r_value)  # Не NaN

    def test_zero_pnl_gives_zero_r(self) -> None:
        """Нулевой PnL даёт 0R"""
        r_value = pnl_to_r_value(0.0, risk_amount_usd=50.0)
        assert r_value == 0.0
