"""Тесты для GATE 3: Strategy Compatibility

ТЗ 3.3.2 строка 1020 (GATE 3: Совместимость режима и стратегии)

Покрытие:
- TREND engine совместимость (~6 тестов)
- RANGE engine совместимость (~3 теста)
- GATE 0-2 integration (~3 теста)
- Edge cases (~3 теста)
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
from src.core.domain.signal import EngineType
from src.gatekeeper.gates import (
    Gate00Result,
    Gate01Result,
    Gate02Result,
    Gate03StrategyCompat,
)


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def gate03():
    """GATE 3 instance."""
    return Gate03StrategyCompat()


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


def make_gate02_pass(final_regime: FinalRegime) -> Gate02Result:
    """Helper: создает GATE 2 PASS результат с заданным final_regime."""
    mrc = MRCResult(mrc_class=MRCClass.TREND_UP, confidence=0.80)
    baseline = BaselineResult(baseline_class=BaselineClass.TREND_UP)
    
    return Gate02Result(
        entry_allowed=True,
        block_reason="",
        mrc_result=mrc,
        baseline_result=baseline,
        final_regime=final_regime,
        conflict_info=None,
        is_probe_mode=False,
        regime_risk_mult=1.0,
        details="PASS"
    )


# =============================================================================
# ТЕСТЫ: TREND engine compatibility
# =============================================================================


def test_gate03_trend_engine_trend_up(gate03, gate00_pass, gate01_pass):
    """PASS: TREND engine + TREND_UP regime → compatible."""
    gate02_pass = make_gate02_pass(FinalRegime.TREND_UP)
    
    result = gate03.evaluate(
        gate00_result=gate00_pass,
        gate01_result=gate01_pass,
        gate02_result=gate02_pass,
        engine_type=EngineType.TREND
    )
    
    assert result.entry_allowed is True
    assert result.is_compatible is True
    assert result.engine_type == EngineType.TREND
    assert result.final_regime == FinalRegime.TREND_UP


def test_gate03_trend_engine_trend_down(gate03, gate00_pass, gate01_pass):
    """PASS: TREND engine + TREND_DOWN regime → compatible."""
    gate02_pass = make_gate02_pass(FinalRegime.TREND_DOWN)
    
    result = gate03.evaluate(
        gate00_result=gate00_pass,
        gate01_result=gate01_pass,
        gate02_result=gate02_pass,
        engine_type=EngineType.TREND
    )
    
    assert result.entry_allowed is True
    assert result.is_compatible is True


def test_gate03_trend_engine_breakout_up(gate03, gate00_pass, gate01_pass):
    """PASS: TREND engine + BREAKOUT_UP regime → compatible."""
    gate02_pass = make_gate02_pass(FinalRegime.BREAKOUT_UP)
    
    result = gate03.evaluate(
        gate00_result=gate00_pass,
        gate01_result=gate01_pass,
        gate02_result=gate02_pass,
        engine_type=EngineType.TREND
    )
    
    assert result.entry_allowed is True
    assert result.is_compatible is True


def test_gate03_trend_engine_breakout_down(gate03, gate00_pass, gate01_pass):
    """PASS: TREND engine + BREAKOUT_DOWN regime → compatible."""
    gate02_pass = make_gate02_pass(FinalRegime.BREAKOUT_DOWN)
    
    result = gate03.evaluate(
        gate00_result=gate00_pass,
        gate01_result=gate01_pass,
        gate02_result=gate02_pass,
        engine_type=EngineType.TREND
    )
    
    assert result.entry_allowed is True
    assert result.is_compatible is True


def test_gate03_trend_engine_probe_trade(gate03, gate00_pass, gate01_pass):
    """PASS: TREND engine + PROBE_TRADE regime → compatible."""
    gate02_pass = make_gate02_pass(FinalRegime.PROBE_TRADE)
    
    result = gate03.evaluate(
        gate00_result=gate00_pass,
        gate01_result=gate01_pass,
        gate02_result=gate02_pass,
        engine_type=EngineType.TREND
    )
    
    assert result.entry_allowed is True
    assert result.is_compatible is True


def test_gate03_trend_engine_range_incompatible(gate03, gate00_pass, gate01_pass):
    """BLOCK: TREND engine + RANGE regime → incompatible."""
    gate02_pass = make_gate02_pass(FinalRegime.RANGE)
    
    result = gate03.evaluate(
        gate00_result=gate00_pass,
        gate01_result=gate01_pass,
        gate02_result=gate02_pass,
        engine_type=EngineType.TREND
    )
    
    assert result.entry_allowed is False
    assert result.block_reason == "strategy_regime_incompatible"
    assert result.is_compatible is False


# =============================================================================
# ТЕСТЫ: RANGE engine compatibility
# =============================================================================


def test_gate03_range_engine_range(gate03, gate00_pass, gate01_pass):
    """PASS: RANGE engine + RANGE regime → compatible."""
    gate02_pass = make_gate02_pass(FinalRegime.RANGE)
    
    result = gate03.evaluate(
        gate00_result=gate00_pass,
        gate01_result=gate01_pass,
        gate02_result=gate02_pass,
        engine_type=EngineType.RANGE
    )
    
    assert result.entry_allowed is True
    assert result.is_compatible is True
    assert result.engine_type == EngineType.RANGE
    assert result.final_regime == FinalRegime.RANGE


def test_gate03_range_engine_trend_incompatible(gate03, gate00_pass, gate01_pass):
    """BLOCK: RANGE engine + TREND_UP regime → incompatible."""
    gate02_pass = make_gate02_pass(FinalRegime.TREND_UP)
    
    result = gate03.evaluate(
        gate00_result=gate00_pass,
        gate01_result=gate01_pass,
        gate02_result=gate02_pass,
        engine_type=EngineType.RANGE
    )
    
    assert result.entry_allowed is False
    assert result.block_reason == "strategy_regime_incompatible"
    assert result.is_compatible is False


def test_gate03_range_engine_breakout_incompatible(gate03, gate00_pass, gate01_pass):
    """BLOCK: RANGE engine + BREAKOUT_UP regime → incompatible."""
    gate02_pass = make_gate02_pass(FinalRegime.BREAKOUT_UP)
    
    result = gate03.evaluate(
        gate00_result=gate00_pass,
        gate01_result=gate01_pass,
        gate02_result=gate02_pass,
        engine_type=EngineType.RANGE
    )
    
    assert result.entry_allowed is False
    assert result.is_compatible is False


# =============================================================================
# ТЕСТЫ: NO_TRADE и NOISE блокировки
# =============================================================================


def test_gate03_no_trade_blocks_all_engines(gate03, gate00_pass, gate01_pass):
    """BLOCK: NO_TRADE regime → блокировка для любого engine."""
    gate02_pass = make_gate02_pass(FinalRegime.NO_TRADE)
    
    # TREND engine
    result_trend = gate03.evaluate(
        gate00_result=gate00_pass,
        gate01_result=gate01_pass,
        gate02_result=gate02_pass,
        engine_type=EngineType.TREND
    )
    
    assert result_trend.entry_allowed is False
    assert result_trend.is_compatible is False
    
    # RANGE engine
    result_range = gate03.evaluate(
        gate00_result=gate00_pass,
        gate01_result=gate01_pass,
        gate02_result=gate02_pass,
        engine_type=EngineType.RANGE
    )
    
    assert result_range.entry_allowed is False
    assert result_range.is_compatible is False


def test_gate03_noise_blocks_all_engines(gate03, gate00_pass, gate01_pass):
    """BLOCK: NOISE regime → блокировка для любого engine."""
    gate02_pass = make_gate02_pass(FinalRegime.NOISE)
    
    # TREND engine
    result_trend = gate03.evaluate(
        gate00_result=gate00_pass,
        gate01_result=gate01_pass,
        gate02_result=gate02_pass,
        engine_type=EngineType.TREND
    )
    
    assert result_trend.entry_allowed is False
    assert result_trend.is_compatible is False


# =============================================================================
# ТЕСТЫ: GATE 0-2 integration
# =============================================================================


def test_gate03_gate00_blocked(gate03, gate01_pass):
    """BLOCK: GATE 0 заблокировал → GATE 3 также блокирует."""
    gate00_blocked = Gate00Result(
        entry_allowed=False,
        block_reason="emergency_mode",
        dqs_result=None,
        drp_transition=None,
        new_drp_state=DRPState.EMERGENCY,
        new_warmup_bars_remaining=0,
        new_drp_flap_count=0,
        new_hibernate_until_ts_utc_ms=None,
        details="EMERGENCY mode"
    )
    
    gate02_pass = make_gate02_pass(FinalRegime.TREND_UP)
    
    result = gate03.evaluate(
        gate00_result=gate00_blocked,
        gate01_result=gate01_pass,
        gate02_result=gate02_pass,
        engine_type=EngineType.TREND
    )
    
    assert result.entry_allowed is False
    assert "gate00_blocked" in result.block_reason


def test_gate03_gate01_blocked(gate03, gate00_pass):
    """BLOCK: GATE 1 заблокировал → GATE 3 также блокирует."""
    gate01_blocked = Gate01Result(
        entry_allowed=False,
        block_reason="manual_halt_new_entries",
        drp_state=DRPState.NORMAL,
        trading_mode=TradingMode.LIVE,
        manual_halt_new_entries=True,
        manual_halt_all_trading=False,
        is_shadow_mode=False,
        details="Manual kill-switch"
    )
    
    gate02_pass = make_gate02_pass(FinalRegime.TREND_UP)
    
    result = gate03.evaluate(
        gate00_result=gate00_pass,
        gate01_result=gate01_blocked,
        gate02_result=gate02_pass,
        engine_type=EngineType.TREND
    )
    
    assert result.entry_allowed is False
    assert "gate01_blocked" in result.block_reason


def test_gate03_gate02_blocked(gate03, gate00_pass, gate01_pass):
    """BLOCK: GATE 2 заблокировал → GATE 3 также блокирует."""
    gate02_blocked = Gate02Result(
        entry_allowed=False,
        block_reason="regime_no_trade",
        mrc_result=MRCResult(mrc_class=MRCClass.NOISE, confidence=0.60),
        baseline_result=BaselineResult(baseline_class=BaselineClass.TREND_UP),
        final_regime=FinalRegime.NO_TRADE,
        conflict_info=None,
        is_probe_mode=False,
        regime_risk_mult=1.0,
        details="NOISE regime"
    )
    
    result = gate03.evaluate(
        gate00_result=gate00_pass,
        gate01_result=gate01_pass,
        gate02_result=gate02_blocked,
        engine_type=EngineType.TREND
    )
    
    assert result.entry_allowed is False
    assert "gate02_blocked" in result.block_reason


# =============================================================================
# ТЕСТЫ: Edge cases
# =============================================================================


def test_gate03_immutability(gate03, gate00_pass, gate01_pass):
    """PASS: Gate03Result immutable (frozen=True)."""
    gate02_pass = make_gate02_pass(FinalRegime.TREND_UP)
    
    result = gate03.evaluate(
        gate00_result=gate00_pass,
        gate01_result=gate01_pass,
        gate02_result=gate02_pass,
        engine_type=EngineType.TREND
    )
    
    # Попытка модификации должна вызвать ошибку
    with pytest.raises(Exception):  # FrozenInstanceError или AttributeError
        result.entry_allowed = False
