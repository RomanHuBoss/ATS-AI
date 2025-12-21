"""Тесты для GATE 5: Pre-sizing

ТЗ 3.3.2 строка 1022 (GATE 5: Pre-sizing + size-invariant издержки)
ТЗ раздел 2128-2150 (unit_risk_bps, expected_cost_R_preMLE)

Покрытие:
- unit_risk_bps вычисление (~2 теста)
- expected_cost_R_preMLE вычисление (~3 теста)
- Size-invariance (~2 теста)
- GATE 0-4 integration (~2 теста)
- Custom costs (~2 теста)
- Edge cases (~2 теста)
"""

import pytest

from src.core.domain.portfolio_state import DRPState, TradingMode
from src.core.domain.regime import (
    BaselineClass,
    BaselineResult,
    FinalRegime,
    MRCClass,
    MRCResult,
)
from src.core.domain.signal import Direction, EngineType, Signal, SignalConstraints, SignalContext, SignalLevels
from src.gatekeeper.gates import (
    Gate00Result,
    Gate01Result,
    Gate02Result,
    Gate03Result,
    Gate04Result,
    Gate05Config,
    Gate05PreSizing,
)


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def gate05():
    """GATE 5 instance."""
    return Gate05PreSizing()


@pytest.fixture
def gate00_pass():
    """GATE 0 PASS результат."""
    return Gate00Result(
        entry_allowed=True,
        block_reason="",
        dqs_result=None,
        drp_transition=None,
        new_drp_state=DRPState.NORMAL,
        new_warmup_bars_remaining=0,
        new_drp_flap_count=0,
        new_hibernate_until_ts_utc_ms=None,
        details="PASS"
    )


@pytest.fixture
def gate01_pass():
    """GATE 1 PASS результат."""
    return Gate01Result(
        entry_allowed=True,
        block_reason="",
        drp_state=DRPState.NORMAL,
        trading_mode=TradingMode.LIVE,
        manual_halt_new_entries=False,
        manual_halt_all_trading=False,
        is_shadow_mode=False,
        details="PASS"
    )


@pytest.fixture
def gate02_pass():
    """GATE 2 PASS результат."""
    mrc = MRCResult(mrc_class=MRCClass.TREND_UP, confidence=0.80)
    baseline = BaselineResult(baseline_class=BaselineClass.TREND_UP)
    
    return Gate02Result(
        entry_allowed=True,
        block_reason="",
        mrc_result=mrc,
        baseline_result=baseline,
        final_regime=FinalRegime.TREND_UP,
        conflict_info=None,
        is_probe_mode=False,
        regime_risk_mult=1.0,
        details="PASS"
    )


@pytest.fixture
def gate03_pass():
    """GATE 3 PASS результат."""
    return Gate03Result(
        entry_allowed=True,
        block_reason="",
        engine_type=EngineType.TREND,
        final_regime=FinalRegime.TREND_UP,
        is_compatible=True,
        details="PASS"
    )


@pytest.fixture
def gate04_pass():
    """GATE 4 PASS результат."""
    return Gate04Result(
        entry_allowed=True,
        block_reason="",
        raw_rr=2.0,
        sl_distance_abs=1000.0,
        sl_distance_atr=2.0,
        rr_valid=True,
        sl_distance_valid=True,
        prices_valid=True,
        details="PASS"
    )


def make_signal_long(
    entry: float = 50000.0,
    sl: float = 49000.0,
    tp: float = 52000.0,
) -> Signal:
    """Helper: создает LONG signal."""
    return Signal(
        instrument="BTCUSDT",
        engine=EngineType.TREND,
        direction=Direction.LONG,
        signal_ts_utc_ms=1700000000000,
        levels=SignalLevels(
            entry_price=entry,
            stop_loss=sl,
            take_profit=tp,
        ),
        context=SignalContext(
            expected_holding_hours=24.0,
            regime_hint="TREND_UP",
            setup_id="setup_001",
        ),
        constraints=SignalConstraints(
            RR_min_engine=1.5,
            sl_min_atr_mult=0.5,
            sl_max_atr_mult=3.0,
        ),
    )


def make_signal_short(
    entry: float = 50000.0,
    sl: float = 51000.0,
    tp: float = 48000.0,
) -> Signal:
    """Helper: создает SHORT signal."""
    return Signal(
        instrument="BTCUSDT",
        engine=EngineType.TREND,
        direction=Direction.SHORT,
        signal_ts_utc_ms=1700000000000,
        levels=SignalLevels(
            entry_price=entry,
            stop_loss=sl,
            take_profit=tp,
        ),
        context=SignalContext(
            expected_holding_hours=24.0,
            regime_hint="TREND_DOWN",
            setup_id="setup_002",
        ),
        constraints=SignalConstraints(
            RR_min_engine=1.5,
            sl_min_atr_mult=0.5,
            sl_max_atr_mult=3.0,
        ),
    )


# =============================================================================
# ТЕСТЫ: unit_risk_bps вычисление
# =============================================================================


def test_gate05_unit_risk_bps_long(gate05, gate00_pass, gate01_pass, gate02_pass, gate03_pass, gate04_pass):
    """PASS: unit_risk_bps вычисляется корректно для LONG."""
    # entry=50000, sl=49000 → SL distance = 1000
    # Effective prices с default costs:
    # entry_eff = 50000 * (1 + (0.5*2 + 1 + 0.5 + 3)/10000) = 50000 * 1.00055 = 50027.5
    # sl_eff = 49000 * (1 - (0.5*2 + 2*2.0*2 + 1 + 3)/10000) = 49000 * (1 - 0.0012) = 49000 * 0.9988 = 48941.2
    # unit_risk_allin_net = |50027.5 - 48941.2| = 1086.3
    # unit_risk_bps = 10000 * 1086.3 / 50000 = 217.26 bps
    signal = make_signal_long(entry=50000, sl=49000, tp=52000)
    
    result = gate05.evaluate(
        gate00_pass, gate01_pass, gate02_pass, gate03_pass, gate04_pass,
        signal
    )
    
    assert result.entry_allowed
    assert result.unit_risk_bps > 0
    # Проверяем приблизительно (зависит от точных costs)
    assert 200 < result.unit_risk_bps < 250


def test_gate05_unit_risk_bps_short(gate05, gate00_pass, gate01_pass, gate02_pass, gate03_pass, gate04_pass):
    """PASS: unit_risk_bps вычисляется корректно для SHORT."""
    signal = make_signal_short(entry=50000, sl=51000, tp=48000)
    
    result = gate05.evaluate(
        gate00_pass, gate01_pass, gate02_pass, gate03_pass, gate04_pass,
        signal
    )
    
    assert result.entry_allowed
    assert result.unit_risk_bps > 0
    # Проверяем приблизительно
    assert 200 < result.unit_risk_bps < 250


# =============================================================================
# ТЕСТЫ: expected_cost_R_preMLE вычисление
# =============================================================================


def test_gate05_expected_cost_r_premle(gate05, gate00_pass, gate01_pass, gate02_pass, gate03_pass, gate04_pass):
    """PASS: expected_cost_R_preMLE вычисляется корректно."""
    signal = make_signal_long(entry=50000, sl=49000, tp=52000)
    
    result = gate05.evaluate(
        gate00_pass, gate01_pass, gate02_pass, gate03_pass, gate04_pass,
        signal
    )
    
    assert result.entry_allowed
    # expected_cost_bps_preMLE = entry_cost + sl_exit_cost
    # entry_cost = 0.5*spread + slippage + impact + fee = 0.5*2 + 1 + 0.5 + 3 = 5.5 bps
    # sl_exit_cost = 0.5*spread + stop_mult*slippage + impact + fee = 0.5*2 + 2*2 + 1 + 3 = 9.0 bps
    # expected_cost_bps_preMLE = 5.5 + 9.0 = 14.5 bps
    assert result.entry_cost_bps == pytest.approx(5.5, abs=0.01)
    assert result.sl_exit_cost_bps == pytest.approx(9.0, abs=0.01)
    assert result.expected_cost_bps_preMLE == pytest.approx(14.5, abs=0.01)
    
    # expected_cost_R_preMLE = expected_cost_bps / unit_risk_bps
    # Должно быть < 0.1R при нормальных издержках
    assert result.expected_cost_R_preMLE > 0
    assert result.expected_cost_R_preMLE < 0.2  # Разумный upper bound


def test_gate05_expected_cost_r_with_custom_costs(gate05, gate00_pass, gate01_pass, gate02_pass, gate03_pass, gate04_pass):
    """PASS: expected_cost_R_preMLE с custom costs."""
    signal = make_signal_long(entry=50000, sl=49000, tp=52000)
    
    # Custom costs: более высокие издержки
    result = gate05.evaluate(
        gate00_pass, gate01_pass, gate02_pass, gate03_pass, gate04_pass,
        signal,
        spread_bps=5.0,
        fee_entry_bps=5.0,
        fee_exit_bps=5.0,
        slippage_entry_bps=3.0,
        slippage_stop_bps=5.0,
    )
    
    assert result.entry_allowed
    # entry_cost = 0.5*5 + 3 + 0.5 + 5 = 11.0 bps
    # sl_exit_cost = 0.5*5 + 2*5 + 1 + 5 = 18.5 bps
    # expected_cost_bps_preMLE = 11.0 + 18.5 = 29.5 bps
    assert result.entry_cost_bps == pytest.approx(11.0, abs=0.01)
    assert result.sl_exit_cost_bps == pytest.approx(18.5, abs=0.01)
    assert result.expected_cost_bps_preMLE == pytest.approx(29.5, abs=0.01)


def test_gate05_effective_prices_computed(gate05, gate00_pass, gate01_pass, gate02_pass, gate03_pass, gate04_pass):
    """PASS: эффективные цены вычисляются корректно."""
    signal = make_signal_long(entry=50000, sl=49000, tp=52000)
    
    result = gate05.evaluate(
        gate00_pass, gate01_pass, gate02_pass, gate03_pass, gate04_pass,
        signal
    )
    
    assert result.entry_allowed
    # entry_eff_allin > entry (LONG платит издержки при входе)
    assert result.entry_eff_allin > signal.levels.entry_price
    # tp_eff_allin < tp (LONG платит издержки при выходе)
    assert result.tp_eff_allin < signal.levels.take_profit
    # sl_eff_allin < sl (LONG платит издержки при SL)
    assert result.sl_eff_allin < signal.levels.stop_loss


# =============================================================================
# ТЕСТЫ: Size-invariance
# =============================================================================


def test_gate05_size_invariance_different_prices(gate05, gate00_pass, gate01_pass, gate02_pass, gate03_pass, gate04_pass):
    """PASS: unit_risk_bps остаётся размеро-инвариантным при разных ценах."""
    # Два сигнала с одинаковым SL distance в % от entry, но разными абсолютными ценами
    signal1 = make_signal_long(entry=50000, sl=49000, tp=52000)  # 2% SL
    signal2 = make_signal_long(entry=100000, sl=98000, tp=104000)  # 2% SL
    
    result1 = gate05.evaluate(gate00_pass, gate01_pass, gate02_pass, gate03_pass, gate04_pass, signal1)
    result2 = gate05.evaluate(gate00_pass, gate01_pass, gate02_pass, gate03_pass, gate04_pass, signal2)
    
    # unit_risk_bps должен быть примерно одинаковым (в пределах погрешности из-за округления)
    assert result1.unit_risk_bps == pytest.approx(result2.unit_risk_bps, rel=0.01)


def test_gate05_no_qty_dependency(gate05, gate00_pass, gate01_pass, gate02_pass, gate03_pass, gate04_pass):
    """PASS: результаты не зависят от qty (qty не передаётся)."""
    signal = make_signal_long(entry=50000, sl=49000, tp=52000)
    
    # Несколько вызовов должны давать идентичные результаты
    result1 = gate05.evaluate(gate00_pass, gate01_pass, gate02_pass, gate03_pass, gate04_pass, signal)
    result2 = gate05.evaluate(gate00_pass, gate01_pass, gate02_pass, gate03_pass, gate04_pass, signal)
    
    assert result1.unit_risk_bps == result2.unit_risk_bps
    assert result1.expected_cost_R_preMLE == result2.expected_cost_R_preMLE


# =============================================================================
# ТЕСТЫ: GATE 0-4 integration
# =============================================================================


def test_gate05_gate00_blocked(gate05, gate01_pass, gate02_pass, gate03_pass, gate04_pass):
    """BLOCK: GATE 0 заблокировал."""
    gate00_blocked = Gate00Result(
        entry_allowed=False,
        block_reason="dqs_too_low",
        dqs_result=None,
        drp_transition=None,
        new_drp_state=DRPState.EMERGENCY,
        new_warmup_bars_remaining=0,
        new_drp_flap_count=0,
        new_hibernate_until_ts_utc_ms=None,
        details="DQS too low"
    )
    
    signal = make_signal_long()
    
    result = gate05.evaluate(gate00_blocked, gate01_pass, gate02_pass, gate03_pass, gate04_pass, signal)
    
    assert not result.entry_allowed
    assert "gate00_blocked" in result.block_reason


def test_gate05_gate04_blocked(gate05, gate00_pass, gate01_pass, gate02_pass, gate03_pass):
    """BLOCK: GATE 4 заблокировал."""
    gate04_blocked = Gate04Result(
        entry_allowed=False,
        block_reason="rr_too_low",
        raw_rr=1.0,
        sl_distance_abs=1000.0,
        sl_distance_atr=2.0,
        rr_valid=False,
        sl_distance_valid=True,
        prices_valid=True,
        details="RR too low"
    )
    
    signal = make_signal_long()
    
    result = gate05.evaluate(gate00_pass, gate01_pass, gate02_pass, gate03_pass, gate04_blocked, signal)
    
    assert not result.entry_allowed
    assert "gate04_blocked" in result.block_reason


# =============================================================================
# ТЕСТЫ: Edge cases
# =============================================================================


def test_gate05_very_tight_sl(gate05, gate00_pass, gate01_pass, gate02_pass, gate03_pass, gate04_pass):
    """PASS: очень tight SL → высокий unit_risk_bps и expected_cost_R."""
    # Очень tight SL: 0.1% от entry
    signal = make_signal_long(entry=50000, sl=49950, tp=52000)
    
    result = gate05.evaluate(gate00_pass, gate01_pass, gate02_pass, gate03_pass, gate04_pass, signal)
    
    assert result.entry_allowed
    # unit_risk_bps должен быть небольшим (tight SL)
    assert result.unit_risk_bps < 50  # Меньше 50 bps
    # expected_cost_R может быть высоким относительно unit_risk
    assert result.expected_cost_R_preMLE > 0


def test_gate05_config_defaults(gate00_pass, gate01_pass, gate02_pass, gate03_pass, gate04_pass):
    """PASS: использование custom config defaults."""
    custom_config = Gate05Config(
        default_spread_bps=10.0,
        default_fee_entry_bps=10.0,
        default_fee_exit_bps=10.0,
    )
    gate05_custom = Gate05PreSizing(custom_config)
    
    signal = make_signal_long(entry=50000, sl=49000, tp=52000)
    
    result = gate05_custom.evaluate(
        gate00_pass, gate01_pass, gate02_pass, gate03_pass, gate04_pass,
        signal
    )
    
    assert result.entry_allowed
    # С более высокими default costs → entry_cost должен быть выше
    assert result.entry_cost_bps > 10  # Минимум 10 bps от spread


# =============================================================================
# ТЕСТЫ: Integration chain GATE 0 → 5
# =============================================================================


def test_gate05_full_chain_pass(gate05, gate00_pass, gate01_pass, gate02_pass, gate03_pass, gate04_pass):
    """PASS: полный chain GATE 0 → 1 → 2 → 3 → 4 → 5."""
    signal = make_signal_long(entry=50000, sl=49000, tp=52000)
    
    result = gate05.evaluate(
        gate00_pass, gate01_pass, gate02_pass, gate03_pass, gate04_pass,
        signal
    )
    
    assert result.entry_allowed
    assert result.block_reason == ""
    assert result.unit_risk_bps > 0
    assert result.expected_cost_R_preMLE > 0
    assert result.entry_eff_allin > 0
    assert result.tp_eff_allin > 0
    assert result.sl_eff_allin > 0
