"""
Юнит-тесты для модуля EffectivePrices

ТЗ: 2.1.1.1 (обязательное)
ТЗ: Appendix A.2 (формулы LONG/SHORT)
ТЗ: Appendix C (epsilon-параметры)

Проверяет:
1. Корректность расчёта эффективных цен LONG/SHORT
2. Симметрию LONG/SHORT
3. Инвариант: SL hit даёт -1R при использовании unit_risk_allin_net
4. Валидацию минимального unit_risk (абсолютный + ATR-based)
5. Epsilon-защиты
"""

import pytest

from src.core.domain.units import pnl_to_r_value
from src.core.math.effective_prices import (
    ABS_MIN_UNIT_RISK_USD,
    DEFAULT_STOP_SLIPPAGE_MULT,
    DEFAULT_UNIT_RISK_MIN_ATR_MULT,
    EPS_FLOAT_COMPARE,
    PositionSide,
    bps_to_fraction,
    calculate_effective_prices,
    calculate_unit_risk_allin_net,
    compute_effective_prices_with_validation,
    validate_unit_risk,
)


class TestBpsConversion:
    """Тесты конверсии basis points"""

    def test_bps_to_fraction_basic(self) -> None:
        """Базовая конверсия bps в дробь"""
        assert bps_to_fraction(10) == pytest.approx(0.001, abs=1e-9)
        assert bps_to_fraction(100) == pytest.approx(0.01, abs=1e-9)
        assert bps_to_fraction(1) == pytest.approx(0.0001, abs=1e-9)

    def test_bps_to_fraction_zero(self) -> None:
        """Ноль bps даёт ноль"""
        assert bps_to_fraction(0) == 0.0


class TestEffectivePricesLONG:
    """Тесты эффективных цен для LONG позиций"""

    def test_long_basic_no_costs(self) -> None:
        """LONG: без издержек цены не меняются"""
        entry, tp, sl = calculate_effective_prices(
            side=PositionSide.LONG,
            entry_price=50000.0,
            tp_price=51000.0,
            sl_price=49500.0,
            spread_bps=0.0,
            fee_entry_bps=0.0,
            fee_exit_bps=0.0,
            slippage_entry_bps=0.0,
            slippage_tp_bps=0.0,
            slippage_stop_bps=0.0,
            impact_entry_bps=0.0,
            impact_exit_bps=0.0,
            impact_stop_bps=0.0,
        )

        assert entry == pytest.approx(50000.0, abs=1e-6)
        assert tp == pytest.approx(51000.0, abs=1e-6)
        assert sl == pytest.approx(49500.0, abs=1e-6)

    def test_long_with_spread(self) -> None:
        """LONG: учёт спреда ухудшает entry, улучшает tp/sl"""
        entry_price = 50000.0
        tp_price = 51000.0
        sl_price = 49500.0
        spread_bps = 10.0  # 0.10% full spread, half = 0.05%

        entry, tp, sl = calculate_effective_prices(
            side=PositionSide.LONG,
            entry_price=entry_price,
            tp_price=tp_price,
            sl_price=sl_price,
            spread_bps=spread_bps,
            fee_entry_bps=0.0,
            fee_exit_bps=0.0,
            slippage_entry_bps=0.0,
            slippage_tp_bps=0.0,
            slippage_stop_bps=0.0,
            impact_entry_bps=0.0,
            impact_exit_bps=0.0,
            impact_stop_bps=0.0,
        )

        half_spread_frac = bps_to_fraction(5.0)  # 0.5 * 10 bps

        # LONG: entry выше (хуже), tp/sl ниже (хуже для нас)
        assert entry == pytest.approx(
            entry_price * (1.0 + half_spread_frac), abs=1e-6
        )
        assert tp == pytest.approx(tp_price * (1.0 - half_spread_frac), abs=1e-6)
        assert sl == pytest.approx(sl_price * (1.0 - half_spread_frac), abs=1e-6)

    def test_long_with_fees(self) -> None:
        """LONG: учёт комиссий"""
        entry_price = 50000.0
        tp_price = 51000.0
        sl_price = 49500.0
        fee_entry_bps = 10.0  # 0.10%
        fee_exit_bps = 10.0

        entry, tp, sl = calculate_effective_prices(
            side=PositionSide.LONG,
            entry_price=entry_price,
            tp_price=tp_price,
            sl_price=sl_price,
            spread_bps=0.0,
            fee_entry_bps=fee_entry_bps,
            fee_exit_bps=fee_exit_bps,
            slippage_entry_bps=0.0,
            slippage_tp_bps=0.0,
            slippage_stop_bps=0.0,
            impact_entry_bps=0.0,
            impact_exit_bps=0.0,
            impact_stop_bps=0.0,
        )

        fee_entry_frac = bps_to_fraction(fee_entry_bps)
        fee_exit_frac = bps_to_fraction(fee_exit_bps)

        assert entry == pytest.approx(entry_price * (1.0 + fee_entry_frac), abs=1e-6)
        assert tp == pytest.approx(tp_price * (1.0 - fee_exit_frac), abs=1e-6)
        assert sl == pytest.approx(sl_price * (1.0 - fee_exit_frac), abs=1e-6)

    def test_long_with_all_costs(self) -> None:
        """LONG: учёт всех издержек (spread+fees+slippage+impact)"""
        entry_price = 50000.0
        tp_price = 51000.0
        sl_price = 49500.0

        entry, tp, sl = calculate_effective_prices(
            side=PositionSide.LONG,
            entry_price=entry_price,
            tp_price=tp_price,
            sl_price=sl_price,
            spread_bps=10.0,
            fee_entry_bps=10.0,
            fee_exit_bps=10.0,
            slippage_entry_bps=5.0,
            slippage_tp_bps=5.0,
            slippage_stop_bps=10.0,
            impact_entry_bps=2.0,
            impact_exit_bps=2.0,
            impact_stop_bps=3.0,
            stop_slippage_mult=2.0,
        )

        # Вручную вычисляем ожидаемые значения
        # entry: 0.5*10 + 10 + 5 + 2 = 22 bps
        # tp: 0.5*10 + 10 + 5 + 2 = 22 bps
        # sl: 0.5*10 + 2*10 + 3 + 10 = 38 bps

        entry_cost_frac = bps_to_fraction(22.0)
        tp_cost_frac = bps_to_fraction(22.0)
        sl_cost_frac = bps_to_fraction(38.0)

        assert entry == pytest.approx(entry_price * (1.0 + entry_cost_frac), abs=1e-6)
        assert tp == pytest.approx(tp_price * (1.0 - tp_cost_frac), abs=1e-6)
        assert sl == pytest.approx(sl_price * (1.0 - sl_cost_frac), abs=1e-6)

    def test_long_stop_slippage_multiplier(self) -> None:
        """LONG: stop slippage multiplier работает корректно"""
        entry_price = 50000.0
        tp_price = 51000.0
        sl_price = 49500.0
        slippage_stop_bps = 10.0
        stop_slippage_mult = 3.0

        _, _, sl = calculate_effective_prices(
            side=PositionSide.LONG,
            entry_price=entry_price,
            tp_price=tp_price,
            sl_price=sl_price,
            spread_bps=0.0,
            fee_entry_bps=0.0,
            fee_exit_bps=0.0,
            slippage_entry_bps=0.0,
            slippage_tp_bps=0.0,
            slippage_stop_bps=slippage_stop_bps,
            impact_entry_bps=0.0,
            impact_exit_bps=0.0,
            impact_stop_bps=0.0,
            stop_slippage_mult=stop_slippage_mult,
        )

        # sl_cost = stop_slippage_mult * slippage_stop_bps = 3 * 10 = 30 bps
        sl_cost_frac = bps_to_fraction(30.0)
        assert sl == pytest.approx(sl_price * (1.0 - sl_cost_frac), abs=1e-6)


class TestEffectivePricesSHORT:
    """Тесты эффективных цен для SHORT позиций"""

    def test_short_basic_no_costs(self) -> None:
        """SHORT: без издержек цены не меняются"""
        entry, tp, sl = calculate_effective_prices(
            side=PositionSide.SHORT,
            entry_price=50000.0,
            tp_price=49000.0,
            sl_price=50500.0,
            spread_bps=0.0,
            fee_entry_bps=0.0,
            fee_exit_bps=0.0,
            slippage_entry_bps=0.0,
            slippage_tp_bps=0.0,
            slippage_stop_bps=0.0,
            impact_entry_bps=0.0,
            impact_exit_bps=0.0,
            impact_stop_bps=0.0,
        )

        assert entry == pytest.approx(50000.0, abs=1e-6)
        assert tp == pytest.approx(49000.0, abs=1e-6)
        assert sl == pytest.approx(50500.0, abs=1e-6)

    def test_short_with_spread(self) -> None:
        """SHORT: учёт спреда ухудшает entry, улучшает tp/sl"""
        entry_price = 50000.0
        tp_price = 49000.0
        sl_price = 50500.0
        spread_bps = 10.0

        entry, tp, sl = calculate_effective_prices(
            side=PositionSide.SHORT,
            entry_price=entry_price,
            tp_price=tp_price,
            sl_price=sl_price,
            spread_bps=spread_bps,
            fee_entry_bps=0.0,
            fee_exit_bps=0.0,
            slippage_entry_bps=0.0,
            slippage_tp_bps=0.0,
            slippage_stop_bps=0.0,
            impact_entry_bps=0.0,
            impact_exit_bps=0.0,
            impact_stop_bps=0.0,
        )

        half_spread_frac = bps_to_fraction(5.0)

        # SHORT: entry ниже (хуже), tp/sl выше (хуже для нас)
        assert entry == pytest.approx(
            entry_price * (1.0 - half_spread_frac), abs=1e-6
        )
        assert tp == pytest.approx(tp_price * (1.0 + half_spread_frac), abs=1e-6)
        assert sl == pytest.approx(sl_price * (1.0 + half_spread_frac), abs=1e-6)

    def test_short_with_all_costs(self) -> None:
        """SHORT: учёт всех издержек"""
        entry_price = 50000.0
        tp_price = 49000.0
        sl_price = 50500.0

        entry, tp, sl = calculate_effective_prices(
            side=PositionSide.SHORT,
            entry_price=entry_price,
            tp_price=tp_price,
            sl_price=sl_price,
            spread_bps=10.0,
            fee_entry_bps=10.0,
            fee_exit_bps=10.0,
            slippage_entry_bps=5.0,
            slippage_tp_bps=5.0,
            slippage_stop_bps=10.0,
            impact_entry_bps=2.0,
            impact_exit_bps=2.0,
            impact_stop_bps=3.0,
            stop_slippage_mult=2.0,
        )

        entry_cost_frac = bps_to_fraction(22.0)
        tp_cost_frac = bps_to_fraction(22.0)
        sl_cost_frac = bps_to_fraction(38.0)

        # SHORT: обратные знаки по сравнению с LONG
        assert entry == pytest.approx(entry_price * (1.0 - entry_cost_frac), abs=1e-6)
        assert tp == pytest.approx(tp_price * (1.0 + tp_cost_frac), abs=1e-6)
        assert sl == pytest.approx(sl_price * (1.0 + sl_cost_frac), abs=1e-6)


class TestLongShortSymmetry:
    """Тесты симметрии LONG/SHORT"""

    def test_symmetry_costs_equal_magnitude(self) -> None:
        """
        LONG/SHORT: при одинаковых издержках, magnitude изменений симметрична
        """
        base_price = 50000.0
        spread_bps = 10.0

        # LONG
        entry_long, tp_long, sl_long = calculate_effective_prices(
            side=PositionSide.LONG,
            entry_price=base_price,
            tp_price=base_price * 1.02,  # +2%
            sl_price=base_price * 0.99,  # -1%
            spread_bps=spread_bps,
            fee_entry_bps=10.0,
            fee_exit_bps=10.0,
            slippage_entry_bps=5.0,
            slippage_tp_bps=5.0,
            slippage_stop_bps=10.0,
            impact_entry_bps=2.0,
            impact_exit_bps=2.0,
            impact_stop_bps=3.0,
        )

        # SHORT (с зеркальными ценами)
        entry_short, tp_short, sl_short = calculate_effective_prices(
            side=PositionSide.SHORT,
            entry_price=base_price,
            tp_price=base_price * 0.98,  # -2%
            sl_price=base_price * 1.01,  # +1%
            spread_bps=spread_bps,
            fee_entry_bps=10.0,
            fee_exit_bps=10.0,
            slippage_entry_bps=5.0,
            slippage_tp_bps=5.0,
            slippage_stop_bps=10.0,
            impact_entry_bps=2.0,
            impact_exit_bps=2.0,
            impact_stop_bps=3.0,
        )

        # Проверяем симметрию изменений относительно base_price
        long_entry_change = (entry_long - base_price) / base_price
        short_entry_change = (entry_short - base_price) / base_price

        # Magnitude должна быть одинаковой
        assert abs(long_entry_change) == pytest.approx(
            abs(short_entry_change), abs=1e-9
        )


class TestUnitRiskCalculation:
    """Тесты расчёта unit_risk_allin_net"""

    def test_unit_risk_long_basic(self) -> None:
        """LONG: unit_risk = abs(entry_eff - sl_eff)"""
        entry_eff = 50025.0
        sl_eff = 49500.0

        unit_risk = calculate_unit_risk_allin_net(
            side=PositionSide.LONG,
            entry_eff_allin=entry_eff,
            sl_eff_allin=sl_eff,
        )

        assert unit_risk == pytest.approx(525.0, abs=1e-6)

    def test_unit_risk_short_basic(self) -> None:
        """SHORT: unit_risk = abs(entry_eff - sl_eff)"""
        entry_eff = 49975.0
        sl_eff = 50500.0

        unit_risk = calculate_unit_risk_allin_net(
            side=PositionSide.SHORT,
            entry_eff_allin=entry_eff,
            sl_eff_allin=sl_eff,
        )

        assert unit_risk == pytest.approx(525.0, abs=1e-6)

    def test_unit_risk_always_positive(self) -> None:
        """unit_risk всегда положительный (abs)"""
        # LONG
        unit_risk_long = calculate_unit_risk_allin_net(
            side=PositionSide.LONG,
            entry_eff_allin=50000.0,
            sl_eff_allin=49500.0,
        )
        assert unit_risk_long > 0

        # SHORT
        unit_risk_short = calculate_unit_risk_allin_net(
            side=PositionSide.SHORT,
            entry_eff_allin=50000.0,
            sl_eff_allin=50500.0,
        )
        assert unit_risk_short > 0

    def test_unit_risk_validation_long_wrong_direction(self) -> None:
        """LONG: sl >= entry должно давать ошибку"""
        with pytest.raises(ValueError, match="sl_eff_allin .* must be <"):
            calculate_unit_risk_allin_net(
                side=PositionSide.LONG,
                entry_eff_allin=50000.0,
                sl_eff_allin=50500.0,  # SL выше entry — неверно для LONG
            )

    def test_unit_risk_validation_short_wrong_direction(self) -> None:
        """SHORT: sl <= entry должно давать ошибку"""
        with pytest.raises(ValueError, match="sl_eff_allin .* must be >"):
            calculate_unit_risk_allin_net(
                side=PositionSide.SHORT,
                entry_eff_allin=50000.0,
                sl_eff_allin=49500.0,  # SL ниже entry — неверно для SHORT
            )


class TestSLHitGivesMinusOneR:
    """
    Критический инвариант: SL hit даёт -1R при использовании unit_risk_allin_net

    ТЗ 2.1.1.1: Инвариант "SL даёт −1R"
    """

    def test_long_sl_hit_minus_one_r(self) -> None:
        """LONG: при выходе по SL получаем ровно -1R"""
        # Эффективные цены с издержками
        entry_eff = 50025.0
        sl_eff = 49500.0

        # unit_risk по формуле
        unit_risk = calculate_unit_risk_allin_net(
            side=PositionSide.LONG,
            entry_eff_allin=entry_eff,
            sl_eff_allin=sl_eff,
        )

        # При выходе по SL: PnL = -(entry_eff - sl_eff) = -unit_risk
        pnl_at_sl = -(entry_eff - sl_eff)
        risk_amount = unit_risk  # Для qty=1

        # Конверсия в R
        r_value = pnl_to_r_value(pnl_at_sl, risk_amount)

        # Инвариант: должно быть -1.0R
        assert r_value == pytest.approx(-1.0, abs=1e-9)

    def test_short_sl_hit_minus_one_r(self) -> None:
        """SHORT: при выходе по SL получаем ровно -1R"""
        entry_eff = 49975.0
        sl_eff = 50500.0

        unit_risk = calculate_unit_risk_allin_net(
            side=PositionSide.SHORT,
            entry_eff_allin=entry_eff,
            sl_eff_allin=sl_eff,
        )

        # SHORT: при выходе по SL (цена выросла до sl_eff)
        # PnL = entry_eff - sl_eff = -unit_risk
        pnl_at_sl = entry_eff - sl_eff
        risk_amount = unit_risk

        r_value = pnl_to_r_value(pnl_at_sl, risk_amount)

        assert r_value == pytest.approx(-1.0, abs=1e-9)

    def test_long_sl_hit_with_all_costs_minus_one_r(self) -> None:
        """LONG: SL hit с учётом всех издержек даёт -1R"""
        entry_price = 50000.0
        sl_price = 49500.0

        # Вычисляем эффективные цены с издержками
        entry_eff, _, sl_eff = calculate_effective_prices(
            side=PositionSide.LONG,
            entry_price=entry_price,
            tp_price=51000.0,  # Не важно для SL
            sl_price=sl_price,
            spread_bps=10.0,
            fee_entry_bps=10.0,
            fee_exit_bps=10.0,
            slippage_entry_bps=5.0,
            slippage_tp_bps=5.0,
            slippage_stop_bps=10.0,
            impact_entry_bps=2.0,
            impact_exit_bps=2.0,
            impact_stop_bps=3.0,
        )

        unit_risk = calculate_unit_risk_allin_net(
            side=PositionSide.LONG,
            entry_eff_allin=entry_eff,
            sl_eff_allin=sl_eff,
        )

        # PnL при SL hit
        pnl_at_sl = -(entry_eff - sl_eff)
        r_value = pnl_to_r_value(pnl_at_sl, unit_risk)

        assert r_value == pytest.approx(-1.0, abs=1e-9)


class TestUnitRiskValidation:
    """Тесты валидации минимального unit_risk"""

    def test_validate_unit_risk_above_absolute_minimum(self) -> None:
        """unit_risk выше абсолютного минимума проходит валидацию"""
        validate_unit_risk(unit_risk=10.0)  # Не должно быть исключений

    def test_validate_unit_risk_below_absolute_minimum(self) -> None:
        """unit_risk ниже абсолютного минимума отклоняется"""
        with pytest.raises(ValueError, match="unit_risk_too_small_block"):
            validate_unit_risk(unit_risk=1e-9)

    def test_validate_unit_risk_atr_based_pass(self) -> None:
        """unit_risk выше ATR-based минимума проходит валидацию"""
        atr = 500.0
        unit_risk_min_mult = 0.02
        unit_risk = 12.0  # > 500 * 0.02 = 10.0

        validate_unit_risk(
            unit_risk=unit_risk,
            atr=atr,
            unit_risk_min_atr_mult=unit_risk_min_mult,
        )

    def test_validate_unit_risk_atr_based_fail(self) -> None:
        """unit_risk ниже ATR-based минимума отклоняется"""
        atr = 500.0
        unit_risk_min_mult = 0.02
        unit_risk = 8.0  # < 500 * 0.02 = 10.0

        with pytest.raises(ValueError, match="unit_risk_too_small_block"):
            validate_unit_risk(
                unit_risk=unit_risk,
                atr=atr,
                unit_risk_min_atr_mult=unit_risk_min_mult,
            )

    def test_validate_unit_risk_atr_too_small(self) -> None:
        """ATR слишком маленький или отрицательный — ошибка"""
        with pytest.raises(ValueError, match="ATR .* is too small"):
            validate_unit_risk(
                unit_risk=10.0,
                atr=1e-15,  # Меньше ATR_EPS
            )

    def test_validate_unit_risk_no_atr_only_absolute(self) -> None:
        """Без ATR проверяется только абсолютный минимум"""
        # unit_risk выше абсолютного минимума
        validate_unit_risk(unit_risk=5.0, atr=None)

        # unit_risk ниже абсолютного минимума
        with pytest.raises(ValueError, match="below absolute minimum"):
            validate_unit_risk(unit_risk=1e-9, atr=None)


class TestComputeWithValidation:
    """Тесты комплексной функции с валидацией"""

    def test_compute_long_valid(self) -> None:
        """LONG: корректные параметры, все проверки проходят"""
        entry_eff, tp_eff, sl_eff, unit_risk = (
            compute_effective_prices_with_validation(
                side=PositionSide.LONG,
                entry_price=50000.0,
                tp_price=51000.0,
                sl_price=49500.0,
                spread_bps=10.0,
                fee_entry_bps=10.0,
                fee_exit_bps=10.0,
                slippage_entry_bps=5.0,
                slippage_tp_bps=5.0,
                slippage_stop_bps=10.0,
                impact_entry_bps=2.0,
                impact_exit_bps=2.0,
                impact_stop_bps=3.0,
                atr=500.0,
                unit_risk_min_atr_mult=0.02,
            )
        )

        # Проверяем, что вернулись корректные значения
        assert entry_eff > 50000.0  # LONG: entry хуже (выше)
        assert tp_eff < 51000.0  # LONG: tp хуже (ниже)
        assert sl_eff < 49500.0  # LONG: sl хуже (ниже)
        assert unit_risk > 10.0  # > ATR * 0.02 = 10.0

    def test_compute_short_valid(self) -> None:
        """SHORT: корректные параметры, все проверки проходят"""
        entry_eff, tp_eff, sl_eff, unit_risk = (
            compute_effective_prices_with_validation(
                side=PositionSide.SHORT,
                entry_price=50000.0,
                tp_price=49000.0,
                sl_price=50500.0,
                spread_bps=10.0,
                fee_entry_bps=10.0,
                fee_exit_bps=10.0,
                slippage_entry_bps=5.0,
                slippage_tp_bps=5.0,
                slippage_stop_bps=10.0,
                impact_entry_bps=2.0,
                impact_exit_bps=2.0,
                impact_stop_bps=3.0,
                atr=500.0,
                unit_risk_min_atr_mult=0.02,
            )
        )

        assert entry_eff < 50000.0  # SHORT: entry хуже (ниже)
        assert tp_eff > 49000.0  # SHORT: tp хуже (выше)
        assert sl_eff > 50500.0  # SHORT: sl хуже (выше)
        assert unit_risk > 10.0

    def test_compute_unit_risk_too_small_rejection(self) -> None:
        """Отказ, если unit_risk слишком мал (ATR-based)"""
        with pytest.raises(ValueError, match="unit_risk_too_small_block"):
            compute_effective_prices_with_validation(
                side=PositionSide.LONG,
                entry_price=50000.0,
                tp_price=50001.0,  # Минимальная дистанция для TP
                sl_price=49999.5,  # Очень малая дистанция для SL
                spread_bps=0.1,  # Минимальные издержки
                fee_entry_bps=0.1,
                fee_exit_bps=0.1,
                slippage_entry_bps=0.1,
                slippage_tp_bps=0.1,
                slippage_stop_bps=0.1,
                impact_entry_bps=0.1,
                impact_exit_bps=0.1,
                impact_stop_bps=0.1,
                stop_slippage_mult=1.0,  # Минимальный множитель
                atr=5000.0,  # Большой ATR → высокий порог
                unit_risk_min_atr_mult=0.05,  # 5% ATR = 250 USD minimum
            )


class TestInputValidation:
    """Тесты валидации входных параметров"""

    def test_negative_prices_rejected(self) -> None:
        """Отрицательные цены отклоняются"""
        with pytest.raises(ValueError, match="Prices must be positive"):
            calculate_effective_prices(
                side=PositionSide.LONG,
                entry_price=-50000.0,
                tp_price=51000.0,
                sl_price=49500.0,
                spread_bps=0.0,
                fee_entry_bps=0.0,
                fee_exit_bps=0.0,
                slippage_entry_bps=0.0,
                slippage_tp_bps=0.0,
                slippage_stop_bps=0.0,
                impact_entry_bps=0.0,
                impact_exit_bps=0.0,
                impact_stop_bps=0.0,
            )

    def test_long_wrong_tp_direction(self) -> None:
        """LONG: TP <= entry отклоняется"""
        with pytest.raises(ValueError, match="tp_price must be > entry_price"):
            calculate_effective_prices(
                side=PositionSide.LONG,
                entry_price=50000.0,
                tp_price=49000.0,  # TP ниже entry — неверно для LONG
                sl_price=49500.0,
                spread_bps=0.0,
                fee_entry_bps=0.0,
                fee_exit_bps=0.0,
                slippage_entry_bps=0.0,
                slippage_tp_bps=0.0,
                slippage_stop_bps=0.0,
                impact_entry_bps=0.0,
                impact_exit_bps=0.0,
                impact_stop_bps=0.0,
            )

    def test_short_wrong_tp_direction(self) -> None:
        """SHORT: TP >= entry отклоняется"""
        with pytest.raises(ValueError, match="tp_price must be < entry_price"):
            calculate_effective_prices(
                side=PositionSide.SHORT,
                entry_price=50000.0,
                tp_price=51000.0,  # TP выше entry — неверно для SHORT
                sl_price=50500.0,
                spread_bps=0.0,
                fee_entry_bps=0.0,
                fee_exit_bps=0.0,
                slippage_entry_bps=0.0,
                slippage_tp_bps=0.0,
                slippage_stop_bps=0.0,
                impact_entry_bps=0.0,
                impact_exit_bps=0.0,
                impact_stop_bps=0.0,
            )

    def test_negative_costs_rejected(self) -> None:
        """Отрицательные издержки отклоняются"""
        with pytest.raises(
            ValueError, match="Fees, slippage, and impact must be non-negative"
        ):
            calculate_effective_prices(
                side=PositionSide.LONG,
                entry_price=50000.0,
                tp_price=51000.0,
                sl_price=49500.0,
                spread_bps=10.0,
                fee_entry_bps=-5.0,  # Отрицательная комиссия
                fee_exit_bps=10.0,
                slippage_entry_bps=5.0,
                slippage_tp_bps=5.0,
                slippage_stop_bps=10.0,
                impact_entry_bps=2.0,
                impact_exit_bps=2.0,
                impact_stop_bps=3.0,
            )

    def test_stop_slippage_mult_below_one(self) -> None:
        """stop_slippage_mult < 1.0 отклоняется"""
        with pytest.raises(ValueError, match="stop_slippage_mult must be >= 1.0"):
            calculate_effective_prices(
                side=PositionSide.LONG,
                entry_price=50000.0,
                tp_price=51000.0,
                sl_price=49500.0,
                spread_bps=0.0,
                fee_entry_bps=0.0,
                fee_exit_bps=0.0,
                slippage_entry_bps=0.0,
                slippage_tp_bps=0.0,
                slippage_stop_bps=10.0,
                impact_entry_bps=0.0,
                impact_exit_bps=0.0,
                impact_stop_bps=0.0,
                stop_slippage_mult=0.5,  # < 1.0
            )
