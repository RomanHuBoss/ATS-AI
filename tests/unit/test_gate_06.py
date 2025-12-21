"""Unit тесты для GATE 6: MLE Decision

ТЗ 3.3.2 строка 1023, 1051 (GATE 6: Решение MLE)
ТЗ раздел 1688-1709 (EV_R_price формула и decision thresholds)
ТЗ раздел 2142-2158 (expected_cost_R_postMLE и net_edge check)

Проверяет:
- MLE decision categories (REJECT, WEAK, NORMAL, STRONG)
- EV_R_price calculation
- expected_cost_R_postMLE calculation
- Net edge check
- Risk multiplier assignment
- Integration с GATE 0-5
- Edge cases
"""

import pytest
import math

from src.core.domain.signal import Direction, EngineType, Signal, SignalLevels
from src.core.domain.portfolio_state import DRPState, TradingMode
from src.core.domain.regime import FinalRegime
from src.data.quality.dqs import DQSResult, DQSComponents
from src.drp.state_machine import DRPTransitionResult

from src.gatekeeper.gates import (
    Gate00Result,
    Gate01Result,
    Gate02Result,
    Gate03Result,
    Gate04Result,
    Gate05Result,
    Gate06Result,
    Gate06MLEDecision,
    Gate06Config,
    MLEDecision,
)


# =============================================================================
# HELPERS
# =============================================================================


def make_signal(
    direction: Direction = Direction.LONG,
    entry_price: float = 100.0,
    take_profit: float = 105.0,
    stop_loss: float = 98.0,
    engine_type: EngineType = EngineType.TREND,
) -> Signal:
    """Создание signal для тестов."""
    from src.core.domain.signal import SignalContext, SignalConstraints
    
    return Signal(
        instrument="BTCUSDT",
        engine=engine_type,
        direction=direction,
        signal_ts_utc_ms=1234567890000,
        levels=SignalLevels(
            entry_price=entry_price,
            take_profit=take_profit,
            stop_loss=stop_loss,
        ),
        context=SignalContext(
            expected_holding_hours=24.0,
            regime_hint=None,
            setup_id="test_setup",
        ),
        constraints=SignalConstraints(
            RR_min_engine=1.5,
            sl_min_atr_mult=0.5,
            sl_max_atr_mult=3.0,
        ),
    )


def make_passing_gate00() -> Gate00Result:
    """GATE 0 PASS result."""
    return Gate00Result(
        entry_allowed=True,
        block_reason="",
        dqs_result=None,
        drp_transition=DRPTransitionResult(
            new_state=DRPState.NORMAL,
            warmup_bars_remaining=0,
            drp_flap_count=0,
            hibernate_until_ts_utc_ms=None,
            transition_occurred=False,
            transition_reason="",
            previous_state=DRPState.NORMAL,
            details="NORMAL state",
        ),
        new_drp_state=DRPState.NORMAL,
        new_warmup_bars_remaining=0,
        new_drp_flap_count=0,
        new_hibernate_until_ts_utc_ms=None,
        details="GATE 0 PASS",
    )


def make_passing_gate01() -> Gate01Result:
    """GATE 1 PASS result."""
    return Gate01Result(
        entry_allowed=True,
        block_reason="",
        drp_state=DRPState.NORMAL,
        trading_mode=TradingMode.LIVE,
        manual_halt_new_entries=False,
        manual_halt_all_trading=False,
        is_shadow_mode=False,
        details="GATE 1 PASS",
    )


def make_passing_gate02() -> Gate02Result:
    """GATE 2 PASS result."""
    from src.core.domain.regime import MRCResult, MRCClass, BaselineResult, BaselineClass
    
    return Gate02Result(
        entry_allowed=True,
        block_reason="",
        mrc_result=MRCResult(
            mrc_class=MRCClass.TREND_UP,
            confidence=0.85,
        ),
        baseline_result=BaselineResult(
            baseline_class=BaselineClass.TREND_UP,
            confidence=0.80,
        ),
        final_regime=FinalRegime.TREND_UP,
        conflict_info=None,
        is_probe_mode=False,
        regime_risk_mult=1.0,
        details="GATE 2 PASS",
    )


def make_passing_gate03() -> Gate03Result:
    """GATE 3 PASS result."""
    return Gate03Result(
        entry_allowed=True,
        block_reason="",
        engine_type=EngineType.TREND,
        final_regime=FinalRegime.TREND_UP,
        is_compatible=True,
        details="GATE 3 PASS",
    )


def make_passing_gate04() -> Gate04Result:
    """GATE 4 PASS result."""
    return Gate04Result(
        entry_allowed=True,
        block_reason="",
        raw_rr=2.5,
        sl_distance_abs=2.0,
        sl_distance_atr=1.5,
        rr_valid=True,
        sl_distance_valid=True,
        prices_valid=True,
        details="GATE 4 PASS",
    )


def make_passing_gate05(
    unit_risk_bps: float = 200.0,
    entry_cost_bps: float = 6.5,
    sl_exit_cost_bps: float = 9.0,
    expected_cost_r_premle: float = 0.0775,
    entry_eff_allin: float = 100.065,
    tp_eff_allin: float = 104.955,
    sl_eff_allin: float = 98.09,
) -> Gate05Result:
    """GATE 5 PASS result."""
    unit_risk_allin_net = abs(entry_eff_allin - sl_eff_allin)
    expected_cost_bps_premle = entry_cost_bps + sl_exit_cost_bps
    
    return Gate05Result(
        entry_allowed=True,
        block_reason="",
        unit_risk_allin_net=unit_risk_allin_net,
        unit_risk_bps=unit_risk_bps,
        entry_cost_bps=entry_cost_bps,
        sl_exit_cost_bps=sl_exit_cost_bps,
        expected_cost_bps_preMLE=expected_cost_bps_premle,
        expected_cost_R_preMLE=expected_cost_r_premle,
        entry_eff_allin=entry_eff_allin,
        tp_eff_allin=tp_eff_allin,
        sl_eff_allin=sl_eff_allin,
        details="GATE 5 PASS",
    )


# =============================================================================
# TESTS: MLE DECISION CATEGORIES
# =============================================================================


def test_gate06_mle_decision_reject_negative_ev():
    """GATE 6: MLE REJECT при отрицательном EV_R_price."""
    gate = Gate06MLEDecision(Gate06Config())
    
    result = gate.evaluate(
        gate00_result=make_passing_gate00(),
        gate01_result=make_passing_gate01(),
        gate02_result=make_passing_gate02(),
        gate03_result=make_passing_gate03(),
        gate04_result=make_passing_gate04(),
        gate05_result=make_passing_gate05(),
        signal=make_signal(),
        p_success=0.2,  # Low p_success
        p_fail=0.8,  # High p_fail → negative EV
    )
    
    assert not result.entry_allowed
    assert result.mle_decision == MLEDecision.REJECT
    assert "mle_reject" in result.block_reason
    assert result.ev_r_price < 0
    assert result.risk_mult == 0.0


def test_gate06_mle_decision_reject_zero_ev():
    """GATE 6: MLE REJECT при EV_R_price ~ 0."""
    gate = Gate06MLEDecision(Gate06Config())
    
    # p_success и p_fail подбираем так чтобы EV ~ 0
    # mu_success_R ~ (104.955 - 100.065) / 1.975 ~ 2.477
    # mu_fail_R = -1.0
    # EV = p_success * 2.477 + p_fail * (-1.0) ~ 0
    # p_success * 2.477 ~ p_fail
    # p_success + p_fail = 1.0 → p_success = 0.288, p_fail = 0.712
    
    result = gate.evaluate(
        gate00_result=make_passing_gate00(),
        gate01_result=make_passing_gate01(),
        gate02_result=make_passing_gate02(),
        gate03_result=make_passing_gate03(),
        gate04_result=make_passing_gate04(),
        gate05_result=make_passing_gate05(),
        signal=make_signal(),
        p_success=0.29,
        p_fail=0.71,
    )
    
    assert not result.entry_allowed
    assert result.mle_decision == MLEDecision.REJECT
    assert abs(result.ev_r_price) < 0.05  # Near zero


def test_gate06_mle_decision_weak():
    """GATE 6: MLE WEAK при 0 < EV_R_price < 0.10."""
    gate = Gate06MLEDecision(Gate06Config(
        ev_r_weak_threshold=0.10,
        ev_r_normal_threshold=0.25,
        net_edge_floor_r=-0.05,  # Разрешаем небольшой negative net edge для WEAK
    ))
    
    # mu_success_R ~ 2.477, mu_fail_R = -1.0
    # EV = p_success * 2.477 - p_fail
    # Для WEAK нужно 0 < EV < 0.10
    # p_success = 0.30, p_fail = 0.70 → EV = 0.743 - 0.70 = 0.043
    # expected_cost_R ~ 0.071 → net_edge = 0.043 - 0.071 = -0.028
    
    result = gate.evaluate(
        gate00_result=make_passing_gate00(),
        gate01_result=make_passing_gate01(),
        gate02_result=make_passing_gate02(),
        gate03_result=make_passing_gate03(),
        gate04_result=make_passing_gate04(),
        gate05_result=make_passing_gate05(),
        signal=make_signal(),
        p_success=0.30,
        p_fail=0.70,
    )
    
    assert result.entry_allowed
    assert result.mle_decision == MLEDecision.WEAK
    assert 0.0 < result.ev_r_price < 0.10
    assert result.risk_mult == 0.5


def test_gate06_mle_decision_normal():
    """GATE 6: MLE NORMAL при 0.10 <= EV_R_price < 0.25."""
    gate = Gate06MLEDecision(Gate06Config(
        ev_r_weak_threshold=0.10,
        ev_r_normal_threshold=0.25,
    ))
    
    # mu_success_R ~ 2.477, mu_fail_R = -1.0
    # EV = p_success * 2.477 - p_fail
    # Для NORMAL нужно 0.10 <= EV < 0.25
    # p_success = 0.35, p_fail = 0.65 → EV = 0.867 - 0.65 = 0.217
    
    result = gate.evaluate(
        gate00_result=make_passing_gate00(),
        gate01_result=make_passing_gate01(),
        gate02_result=make_passing_gate02(),
        gate03_result=make_passing_gate03(),
        gate04_result=make_passing_gate04(),
        gate05_result=make_passing_gate05(),
        signal=make_signal(),
        p_success=0.35,
        p_fail=0.65,
    )
    
    assert result.entry_allowed
    assert result.mle_decision == MLEDecision.NORMAL
    assert 0.10 <= result.ev_r_price < 0.25
    assert result.risk_mult == 1.0


def test_gate06_mle_decision_strong():
    """GATE 6: MLE STRONG при EV_R_price >= 0.25."""
    gate = Gate06MLEDecision(Gate06Config(
        ev_r_weak_threshold=0.10,
        ev_r_normal_threshold=0.25,
    ))
    
    result = gate.evaluate(
        gate00_result=make_passing_gate00(),
        gate01_result=make_passing_gate01(),
        gate02_result=make_passing_gate02(),
        gate03_result=make_passing_gate03(),
        gate04_result=make_passing_gate04(),
        gate05_result=make_passing_gate05(),
        signal=make_signal(),
        p_success=0.65,
        p_fail=0.35,
    )
    
    assert result.entry_allowed
    assert result.mle_decision == MLEDecision.STRONG
    assert result.ev_r_price >= 0.25
    assert result.risk_mult == 1.25


# =============================================================================
# TESTS: NET EDGE CHECK
# =============================================================================


def test_gate06_net_edge_below_floor():
    """GATE 6: блокировка при net_edge < net_edge_floor."""
    gate = Gate06MLEDecision(Gate06Config(
        net_edge_floor_r=0.20,  # High floor
    ))
    
    # mu_success_R ~ 2.477, mu_fail_R = -1.0
    # EV = p_success * 2.477 - p_fail
    # expected_cost_bps ~ 6.5 + p_success*4.5 + p_fail*9.0
    # expected_cost_R = expected_cost_bps / 200
    # net_edge = EV - expected_cost_R
    #
    # Для net_edge < 0.20 при положительном EV:
    # p_success = 0.36, p_fail = 0.64
    # EV = 0.36 * 2.477 - 0.64 = 0.252
    # expected_cost_bps = 6.5 + 1.62 + 5.76 = 13.88
    # expected_cost_R = 0.0694
    # net_edge = 0.252 - 0.0694 = 0.183 < 0.20 ✓
    
    result = gate.evaluate(
        gate00_result=make_passing_gate00(),
        gate01_result=make_passing_gate01(),
        gate02_result=make_passing_gate02(),
        gate03_result=make_passing_gate03(),
        gate04_result=make_passing_gate04(),
        gate05_result=make_passing_gate05(),
        signal=make_signal(),
        p_success=0.36,
        p_fail=0.64,
    )
    
    assert not result.entry_allowed
    assert "net_edge_too_low" in result.block_reason
    assert result.net_edge_r < 0.20
    assert result.risk_mult == 0.0


def test_gate06_net_edge_above_floor():
    """GATE 6: PASS при net_edge >= net_edge_floor."""
    gate = Gate06MLEDecision(Gate06Config(
        net_edge_floor_r=0.05,  # Low floor
    ))
    
    result = gate.evaluate(
        gate00_result=make_passing_gate00(),
        gate01_result=make_passing_gate01(),
        gate02_result=make_passing_gate02(),
        gate03_result=make_passing_gate03(),
        gate04_result=make_passing_gate04(),
        gate05_result=make_passing_gate05(),
        signal=make_signal(),
        p_success=0.60,
        p_fail=0.40,
    )
    
    assert result.entry_allowed
    assert result.net_edge_r >= 0.05


# =============================================================================
# TESTS: EV_R_PRICE CALCULATION
# =============================================================================


def test_gate06_ev_r_price_calculation():
    """GATE 6: корректное вычисление EV_R_price."""
    gate = Gate06MLEDecision(Gate06Config())
    
    p_success = 0.60
    p_fail = 0.40
    
    result = gate.evaluate(
        gate00_result=make_passing_gate00(),
        gate01_result=make_passing_gate01(),
        gate02_result=make_passing_gate02(),
        gate03_result=make_passing_gate03(),
        gate04_result=make_passing_gate04(),
        gate05_result=make_passing_gate05(),
        signal=make_signal(),
        p_success=p_success,
        p_fail=p_fail,
    )
    
    # mu_success_R = (tp_eff - entry_eff) / unit_risk
    # = (104.955 - 100.065) / 1.975 ~ 2.477
    # mu_fail_R = -1.0
    # EV = 0.60 * 2.477 + 0.40 * (-1.0) = 1.486 - 0.40 = 1.086
    
    assert result.entry_allowed
    assert result.mu_fail_r == -1.0
    assert abs(result.mu_success_r - 2.477) < 0.01
    expected_ev = p_success * result.mu_success_r + p_fail * (-1.0)
    assert abs(result.ev_r_price - expected_ev) < 0.001


def test_gate06_ev_r_price_short_position():
    """GATE 6: EV_R_price для SHORT позиции."""
    gate = Gate06MLEDecision(Gate06Config())
    
    # SHORT: entry=100, TP=95, SL=102
    signal = make_signal(
        direction=Direction.SHORT,
        entry_price=100.0,
        take_profit=95.0,
        stop_loss=102.0,
    )
    
    # Gate05 для SHORT
    gate05 = make_passing_gate05(
        unit_risk_bps=200.0,
        entry_eff_allin=99.935,  # Worse for SHORT (lower)
        tp_eff_allin=95.045,  # Better for SHORT (lower)
        sl_eff_allin=101.91,  # Worse for SHORT (higher)
    )
    
    result = gate.evaluate(
        gate00_result=make_passing_gate00(),
        gate01_result=make_passing_gate01(),
        gate02_result=make_passing_gate02(),
        gate03_result=make_passing_gate03(),
        gate04_result=make_passing_gate04(),
        gate05_result=gate05,
        signal=signal,
        p_success=0.60,
        p_fail=0.40,
    )
    
    assert result.entry_allowed
    assert result.mu_fail_r == -1.0
    # mu_success_R = (tp_eff - entry_eff) / unit_risk
    # = (95.045 - 99.935) / 1.975 ~ -2.476 (negative for SHORT)
    # Но unit_risk = |entry - sl| = |99.935 - 101.91| = 1.975
    # tp_distance = 95.045 - 99.935 = -4.89 (negative для SHORT)
    # mu_success_R = -4.89 / 1.975 = -2.476
    # Ожидаем положительный mu_success_R для SHORT после корректного расчёта
    
    # На самом деле для SHORT:
    # entry_eff = 99.935, tp_eff = 95.045, sl_eff = 101.91
    # TP более выгодный → tp_eff < entry_eff (для SHORT это прибыль)
    # Но в R units мы считаем как: (tp_eff - entry_eff) / unit_risk
    # = (95.045 - 99.935) / 1.975 = -4.89 / 1.975 = -2.476
    
    # Это неправильно! Для SHORT мы должны инвертировать знак
    # или считать unit_risk с учетом направления
    
    # В текущей реализации effective_prices уже учитывает направление
    # поэтому tp_eff - entry_eff должно быть положительным для прибыли
    
    # Проверим что EV положительный
    assert result.ev_r_price > 0


# =============================================================================
# TESTS: EXPECTED_COST_R_POSTMLE
# =============================================================================


def test_gate06_expected_cost_r_postmle_calculation():
    """GATE 6: корректное вычисление expected_cost_R_postMLE."""
    gate = Gate06MLEDecision(Gate06Config())
    
    p_success = 0.60
    p_fail = 0.40
    
    gate05 = make_passing_gate05(
        unit_risk_bps=200.0,
        entry_cost_bps=6.5,
        sl_exit_cost_bps=9.0,
    )
    
    result = gate.evaluate(
        gate00_result=make_passing_gate00(),
        gate01_result=make_passing_gate01(),
        gate02_result=make_passing_gate02(),
        gate03_result=make_passing_gate03(),
        gate04_result=make_passing_gate04(),
        gate05_result=gate05,
        signal=make_signal(),
        p_success=p_success,
        p_fail=p_fail,
        tp_exit_cost_bps=4.5,
    )
    
    # expected_cost_bps_post = entry_cost + p_success*tp_exit + p_fail*sl_exit
    # = 6.5 + 0.60*4.5 + 0.40*9.0
    # = 6.5 + 2.7 + 3.6 = 12.8
    # expected_cost_R = 12.8 / 200.0 = 0.064
    
    assert result.entry_allowed
    expected_cost_bps = 6.5 + p_success * 4.5 + p_fail * 9.0
    assert abs(result.expected_cost_bps_postmle - expected_cost_bps) < 0.001
    expected_cost_r = expected_cost_bps / 200.0
    assert abs(result.expected_cost_r_postmle - expected_cost_r) < 0.0001


def test_gate06_custom_tp_exit_cost():
    """GATE 6: использование custom tp_exit_cost."""
    gate = Gate06MLEDecision(Gate06Config())
    
    custom_tp_cost = 3.0
    
    result = gate.evaluate(
        gate00_result=make_passing_gate00(),
        gate01_result=make_passing_gate01(),
        gate02_result=make_passing_gate02(),
        gate03_result=make_passing_gate03(),
        gate04_result=make_passing_gate04(),
        gate05_result=make_passing_gate05(),
        signal=make_signal(),
        p_success=0.60,
        p_fail=0.40,
        tp_exit_cost_bps=custom_tp_cost,
    )
    
    assert result.entry_allowed
    assert result.tp_exit_cost_bps == custom_tp_cost


# =============================================================================
# TESTS: INTEGRATION GATE 0-5
# =============================================================================


def test_gate06_block_gate00():
    """GATE 6: блокировка при GATE 0 FAIL."""
    gate = Gate06MLEDecision(Gate06Config())
    
    gate00 = Gate00Result(
        entry_allowed=False,
        block_reason="dqs_critical_too_low",
        dqs_result=None,
        drp_transition=DRPTransitionResult(
            new_state=DRPState.EMERGENCY,
            warmup_bars_remaining=0,
            drp_flap_count=0,
            hibernate_until_ts_utc_ms=None,
            transition_occurred=True,
            transition_reason="dqs_emergency",
            previous_state=DRPState.NORMAL,
            details="EMERGENCY triggered",
        ),
        new_drp_state=DRPState.EMERGENCY,
        new_warmup_bars_remaining=0,
        new_drp_flap_count=0,
        new_hibernate_until_ts_utc_ms=None,
        details="Hard gate",
    )
    
    result = gate.evaluate(
        gate00_result=gate00,
        gate01_result=make_passing_gate01(),
        gate02_result=make_passing_gate02(),
        gate03_result=make_passing_gate03(),
        gate04_result=make_passing_gate04(),
        gate05_result=make_passing_gate05(),
        signal=make_signal(),
        p_success=0.60,
        p_fail=0.40,
    )
    
    assert not result.entry_allowed
    assert "gate00_blocked" in result.block_reason


def test_gate06_block_gate05():
    """GATE 6: блокировка при GATE 5 FAIL."""
    gate = Gate06MLEDecision(Gate06Config())
    
    gate05 = Gate05Result(
        entry_allowed=False,
        block_reason="gate04_blocked",
        unit_risk_allin_net=0.0,
        unit_risk_bps=0.0,
        entry_cost_bps=0.0,
        sl_exit_cost_bps=0.0,
        expected_cost_bps_preMLE=0.0,
        expected_cost_R_preMLE=0.0,
        entry_eff_allin=0.0,
        tp_eff_allin=0.0,
        sl_eff_allin=0.0,
        details="gate04_blocked",
    )
    
    result = gate.evaluate(
        gate00_result=make_passing_gate00(),
        gate01_result=make_passing_gate01(),
        gate02_result=make_passing_gate02(),
        gate03_result=make_passing_gate03(),
        gate04_result=make_passing_gate04(),
        gate05_result=gate05,
        signal=make_signal(),
        p_success=0.60,
        p_fail=0.40,
    )
    
    assert not result.entry_allowed
    assert "gate05_blocked" in result.block_reason


# =============================================================================
# TESTS: EDGE CASES
# =============================================================================


def test_gate06_invalid_p_success_negative():
    """GATE 6: блокировка при p_success < 0."""
    gate = Gate06MLEDecision(Gate06Config())
    
    result = gate.evaluate(
        gate00_result=make_passing_gate00(),
        gate01_result=make_passing_gate01(),
        gate02_result=make_passing_gate02(),
        gate03_result=make_passing_gate03(),
        gate04_result=make_passing_gate04(),
        gate05_result=make_passing_gate05(),
        signal=make_signal(),
        p_success=-0.1,
        p_fail=0.5,
    )
    
    assert not result.entry_allowed
    assert "invalid_p_success" in result.block_reason


def test_gate06_invalid_p_success_above_one():
    """GATE 6: блокировка при p_success > 1."""
    gate = Gate06MLEDecision(Gate06Config())
    
    result = gate.evaluate(
        gate00_result=make_passing_gate00(),
        gate01_result=make_passing_gate01(),
        gate02_result=make_passing_gate02(),
        gate03_result=make_passing_gate03(),
        gate04_result=make_passing_gate04(),
        gate05_result=make_passing_gate05(),
        signal=make_signal(),
        p_success=1.5,
        p_fail=0.5,
    )
    
    assert not result.entry_allowed
    assert "invalid_p_success" in result.block_reason


def test_gate06_invalid_p_fail():
    """GATE 6: блокировка при invalid p_fail."""
    gate = Gate06MLEDecision(Gate06Config())
    
    result = gate.evaluate(
        gate00_result=make_passing_gate00(),
        gate01_result=make_passing_gate01(),
        gate02_result=make_passing_gate02(),
        gate03_result=make_passing_gate03(),
        gate04_result=make_passing_gate04(),
        gate05_result=make_passing_gate05(),
        signal=make_signal(),
        p_success=0.6,
        p_fail=1.2,
    )
    
    assert not result.entry_allowed
    assert "invalid_p_fail" in result.block_reason


def test_gate06_zero_unit_risk():
    """GATE 6: блокировка при unit_risk ~ 0."""
    gate = Gate06MLEDecision(Gate06Config())
    
    gate05 = make_passing_gate05(
        unit_risk_bps=200.0,
        entry_eff_allin=100.0,
        tp_eff_allin=100.0,  # Same as entry → zero unit_risk
        sl_eff_allin=100.0,
    )
    
    result = gate.evaluate(
        gate00_result=make_passing_gate00(),
        gate01_result=make_passing_gate01(),
        gate02_result=make_passing_gate02(),
        gate03_result=make_passing_gate03(),
        gate04_result=make_passing_gate04(),
        gate05_result=gate05,
        signal=make_signal(),
        p_success=0.6,
        p_fail=0.4,
    )
    
    assert not result.entry_allowed
    assert "unit_risk_too_small" in result.block_reason


def test_gate06_result_immutability():
    """GATE 6: Gate06Result immutable (frozen=True)."""
    gate = Gate06MLEDecision(Gate06Config())
    
    result = gate.evaluate(
        gate00_result=make_passing_gate00(),
        gate01_result=make_passing_gate01(),
        gate02_result=make_passing_gate02(),
        gate03_result=make_passing_gate03(),
        gate04_result=make_passing_gate04(),
        gate05_result=make_passing_gate05(),
        signal=make_signal(),
        p_success=0.60,
        p_fail=0.40,
    )
    
    # Попытка изменения должна выбросить FrozenInstanceError
    with pytest.raises(Exception):  # dataclass frozen raises different exceptions
        result.entry_allowed = False


# =============================================================================
# TESTS: SIZE-INVARIANCE
# =============================================================================


def test_gate06_size_invariance():
    """GATE 6: все расчёты size-invariant (не зависят от qty)."""
    gate = Gate06MLEDecision(Gate06Config())
    
    # Создаём два результата с разными unit_risk_allin_net
    # но одинаковыми unit_risk_bps (size-invariant метрика)
    
    gate05_1 = make_passing_gate05(
        unit_risk_bps=200.0,  # Same
        entry_eff_allin=100.0,
        tp_eff_allin=105.0,
        sl_eff_allin=98.0,
    )
    
    gate05_2 = make_passing_gate05(
        unit_risk_bps=200.0,  # Same
        entry_eff_allin=200.0,
        tp_eff_allin=210.0,
        sl_eff_allin=196.0,
    )
    
    result1 = gate.evaluate(
        gate00_result=make_passing_gate00(),
        gate01_result=make_passing_gate01(),
        gate02_result=make_passing_gate02(),
        gate03_result=make_passing_gate03(),
        gate04_result=make_passing_gate04(),
        gate05_result=gate05_1,
        signal=make_signal(),
        p_success=0.60,
        p_fail=0.40,
    )
    
    result2 = gate.evaluate(
        gate00_result=make_passing_gate00(),
        gate01_result=make_passing_gate01(),
        gate02_result=make_passing_gate02(),
        gate03_result=make_passing_gate03(),
        gate04_result=make_passing_gate04(),
        gate05_result=gate05_2,
        signal=make_signal(),
        p_success=0.60,
        p_fail=0.40,
    )
    
    # EV_R_price должен быть одинаковым (size-invariant)
    assert abs(result1.ev_r_price - result2.ev_r_price) < 0.01
    # expected_cost_R_postMLE должен быть одинаковым
    assert abs(result1.expected_cost_r_postmle - result2.expected_cost_r_postmle) < 0.01
    # net_edge_R должен быть одинаковым
    assert abs(result1.net_edge_r - result2.net_edge_r) < 0.01
    # MLE decision должен быть одинаковым
    assert result1.mle_decision == result2.mle_decision
    # Risk multiplier должен быть одинаковым
    assert result1.risk_mult == result2.risk_mult


# =============================================================================
# TESTS: INTEGRATION CHAIN GATE 0-6
# =============================================================================


def test_gate06_integration_chain_full_pass():
    """GATE 6: Integration test для полного прохода GATE 0→6."""
    gate00 = make_passing_gate00()
    gate01 = make_passing_gate01()
    gate02 = make_passing_gate02()
    gate03 = make_passing_gate03()
    gate04 = make_passing_gate04()
    gate05 = make_passing_gate05()
    
    gate06 = Gate06MLEDecision(Gate06Config())
    
    result = gate06.evaluate(
        gate00_result=gate00,
        gate01_result=gate01,
        gate02_result=gate02,
        gate03_result=gate03,
        gate04_result=gate04,
        gate05_result=gate05,
        signal=make_signal(),
        p_success=0.65,
        p_fail=0.35,
    )
    
    assert result.entry_allowed
    assert result.mle_decision in [MLEDecision.NORMAL, MLEDecision.STRONG]
    assert result.ev_r_price > 0
    assert result.net_edge_r > 0
    assert result.risk_mult > 0


def test_gate06_integration_chain_block_at_gate02():
    """GATE 6: Integration test с блокировкой на GATE 2."""
    gate00 = make_passing_gate00()
    
    gate01 = make_passing_gate01()
    
    # GATE 2 blocks
    from src.core.domain.regime import MRCResult, MRCClass, BaselineResult, BaselineClass
    
    gate02 = Gate02Result(
        entry_allowed=False,
        block_reason="mrc_noise_block",
        mrc_result=MRCResult(
            mrc_class=MRCClass.NOISE,
            confidence=0.85,
        ),
        baseline_result=BaselineResult(
            baseline_class=BaselineClass.NOISE,
            confidence=0.80,
        ),
        final_regime=FinalRegime.NO_TRADE,
        conflict_info=None,
        is_probe_mode=False,
        regime_risk_mult=0.0,
        details="NOISE regime",
    )
    
    gate03 = make_passing_gate03()
    gate04 = make_passing_gate04()
    gate05 = make_passing_gate05()
    
    gate06 = Gate06MLEDecision(Gate06Config())
    
    result = gate06.evaluate(
        gate00_result=gate00,
        gate01_result=gate01,
        gate02_result=gate02,
        gate03_result=gate03,
        gate04_result=gate04,
        gate05_result=gate05,
        signal=make_signal(),
        p_success=0.65,
        p_fail=0.35,
    )
    
    assert not result.entry_allowed
    assert "gate02_blocked" in result.block_reason
