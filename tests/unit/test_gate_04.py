"""Тесты для GATE 4: Signal Validation

ТЗ 3.3.2 строка 1021 (GATE 4: Валидация сигнала движка)
ТЗ 3.3.5 строки 1238-1240 (SL distance в ATR)

Покрытие:
- RR validation (~3 теста)
- SL distance validation (~4 теста)
- Price sanity checks (~3 теста)
- GATE 0-3 integration (~2 теста)
- Edge cases (~2 теста)
"""

import math

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
    Gate04Config,
    Gate04SignalValidation,
)


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def gate04():
    """GATE 4 instance."""
    return Gate04SignalValidation()


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


def make_signal_long(
    entry: float = 50000.0,
    sl: float = 49000.0,
    tp: float = 52000.0,
    rr_min: float = 1.5,
    sl_min_atr: float = 0.5,
    sl_max_atr: float = 3.0,
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
            RR_min_engine=rr_min,
            sl_min_atr_mult=sl_min_atr,
            sl_max_atr_mult=sl_max_atr,
        ),
    )


def make_signal_short(
    entry: float = 50000.0,
    sl: float = 51000.0,
    tp: float = 48000.0,
    rr_min: float = 1.5,
    sl_min_atr: float = 0.5,
    sl_max_atr: float = 3.0,
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
            RR_min_engine=rr_min,
            sl_min_atr_mult=sl_min_atr,
            sl_max_atr_mult=sl_max_atr,
        ),
    )


# =============================================================================
# ТЕСТЫ: RR validation
# =============================================================================


def test_gate04_rr_valid_long(gate04, gate00_pass, gate01_pass, gate02_pass, gate03_pass):
    """PASS: LONG signal с RR >= RR_min_engine."""
    # RR = (52000 - 50000) / (50000 - 49000) = 2000 / 1000 = 2.0 >= 1.5
    signal = make_signal_long(entry=50000, sl=49000, tp=52000, rr_min=1.5)
    atr = 500.0  # SL distance = 1000, в ATR = 1000/500 = 2.0 ATR (в пределах [0.5, 3.0])
    
    result = gate04.evaluate(gate00_pass, gate01_pass, gate02_pass, gate03_pass, signal, atr)
    
    assert result.entry_allowed
    assert result.block_reason == ""
    assert result.rr_valid
    assert result.sl_distance_valid
    assert result.prices_valid
    assert result.raw_rr == pytest.approx(2.0, abs=1e-6)
    assert result.sl_distance_abs == 1000.0
    assert result.sl_distance_atr == pytest.approx(2.0, abs=1e-6)


def test_gate04_rr_valid_short(gate04, gate00_pass, gate01_pass, gate02_pass, gate03_pass):
    """PASS: SHORT signal с RR >= RR_min_engine."""
    # RR = (50000 - 48000) / (51000 - 50000) = 2000 / 1000 = 2.0 >= 1.5
    signal = make_signal_short(entry=50000, sl=51000, tp=48000, rr_min=1.5)
    atr = 500.0  # SL distance = 1000, в ATR = 1000/500 = 2.0 ATR (в пределах [0.5, 3.0])
    
    result = gate04.evaluate(gate00_pass, gate01_pass, gate02_pass, gate03_pass, signal, atr)
    
    assert result.entry_allowed
    assert result.block_reason == ""
    assert result.rr_valid
    assert result.sl_distance_valid
    assert result.raw_rr == pytest.approx(2.0, abs=1e-6)


def test_gate04_rr_too_low(gate04, gate00_pass, gate01_pass, gate02_pass, gate03_pass):
    """BLOCK: RR < RR_min_engine."""
    # RR = (51000 - 50000) / (50000 - 49000) = 1000 / 1000 = 1.0 < 2.0
    signal = make_signal_long(entry=50000, sl=49000, tp=51000, rr_min=2.0)
    atr = 500.0
    
    result = gate04.evaluate(gate00_pass, gate01_pass, gate02_pass, gate03_pass, signal, atr)
    
    assert not result.entry_allowed
    assert "rr_too_low" in result.block_reason
    assert not result.rr_valid
    assert result.raw_rr == pytest.approx(1.0, abs=1e-6)


# =============================================================================
# ТЕСТЫ: SL distance validation
# =============================================================================


def test_gate04_sl_distance_valid(gate04, gate00_pass, gate01_pass, gate02_pass, gate03_pass):
    """PASS: SL distance в пределах [sl_min_atr_mult, sl_max_atr_mult]."""
    # SL distance = 1000, ATR = 500 → 2.0 ATR (в пределах [0.5, 3.0])
    signal = make_signal_long(entry=50000, sl=49000, tp=52000, sl_min_atr=0.5, sl_max_atr=3.0)
    atr = 500.0
    
    result = gate04.evaluate(gate00_pass, gate01_pass, gate02_pass, gate03_pass, signal, atr)
    
    assert result.entry_allowed
    assert result.sl_distance_valid
    assert result.sl_distance_atr == pytest.approx(2.0, abs=1e-6)


def test_gate04_sl_too_tight(gate04, gate00_pass, gate01_pass, gate02_pass, gate03_pass):
    """BLOCK: SL distance < sl_min_atr_mult."""
    # SL distance = 250, ATR = 500 → 0.5 ATR < 1.0 ATR (min)
    signal = make_signal_long(entry=50000, sl=49750, tp=52000, sl_min_atr=1.0, sl_max_atr=3.0)
    atr = 500.0
    
    result = gate04.evaluate(gate00_pass, gate01_pass, gate02_pass, gate03_pass, signal, atr)
    
    assert not result.entry_allowed
    assert "sl_too_tight" in result.block_reason
    assert not result.sl_distance_valid
    assert result.sl_distance_atr == pytest.approx(0.5, abs=1e-6)


def test_gate04_sl_too_wide(gate04, gate00_pass, gate01_pass, gate02_pass, gate03_pass):
    """BLOCK: SL distance > sl_max_atr_mult."""
    # SL distance = 2000, ATR = 500 → 4.0 ATR > 3.0 ATR (max)
    # RR = (54000 - 50000) / 2000 = 2.0 >= 1.5 (валидный RR чтобы дойти до SL check)
    signal = make_signal_long(entry=50000, sl=48000, tp=54000, sl_min_atr=0.5, sl_max_atr=3.0)
    atr = 500.0
    
    result = gate04.evaluate(gate00_pass, gate01_pass, gate02_pass, gate03_pass, signal, atr)
    
    assert not result.entry_allowed
    assert "sl_too_wide" in result.block_reason
    assert not result.sl_distance_valid
    assert result.sl_distance_atr == pytest.approx(4.0, abs=1e-6)


def test_gate04_sl_distance_edge_min(gate04, gate00_pass, gate01_pass, gate02_pass, gate03_pass):
    """PASS: SL distance ровно на минимальной границе."""
    # SL distance = 500, ATR = 500 → 1.0 ATR (ровно на границе [1.0, 3.0])
    signal = make_signal_long(entry=50000, sl=49500, tp=52000, sl_min_atr=1.0, sl_max_atr=3.0)
    atr = 500.0
    
    result = gate04.evaluate(gate00_pass, gate01_pass, gate02_pass, gate03_pass, signal, atr)
    
    assert result.entry_allowed
    assert result.sl_distance_valid
    assert result.sl_distance_atr == pytest.approx(1.0, abs=1e-6)


# =============================================================================
# ТЕСТЫ: Price sanity checks
# =============================================================================


def test_gate04_prices_valid_boundary(gate04, gate00_pass, gate01_pass, gate02_pass, gate03_pass):
    """PASS: цены на границе допустимых значений."""
    # Очень маленькие но валидные цены
    signal = make_signal_long(entry=1.0, sl=0.99, tp=1.02)
    atr = 0.01  # SL distance = 0.01, в ATR = 1.0 ATR
    
    result = gate04.evaluate(gate00_pass, gate01_pass, gate02_pass, gate03_pass, signal, atr)
    
    assert result.entry_allowed
    assert result.prices_valid


def test_gate04_very_wide_price_range(gate04, gate00_pass, gate01_pass, gate02_pass, gate03_pass):
    """PASS: очень широкий price range но валидный."""
    # Широкий price range
    # entry=50000, sl=10000, tp=110000
    # Profit = 110000 - 50000 = 60000
    # Loss = 50000 - 10000 = 40000
    # RR = 60000 / 40000 = 1.5 >= 1.5 (валидно)
    signal = make_signal_long(entry=50000, sl=10000, tp=110000)
    atr = 20000.0  # SL distance = 40000, в ATR = 2.0 ATR (валидно)
    
    result = gate04.evaluate(gate00_pass, gate01_pass, gate02_pass, gate03_pass, signal, atr)
    
    assert result.entry_allowed
    assert result.prices_valid


def test_gate04_atr_nan(gate04, gate00_pass, gate01_pass, gate02_pass, gate03_pass):
    """BLOCK: ATR = NaN."""
    signal = make_signal_long()
    atr = math.nan
    
    result = gate04.evaluate(gate00_pass, gate01_pass, gate02_pass, gate03_pass, signal, atr)
    
    assert not result.entry_allowed
    assert "invalid_atr" in result.block_reason


# =============================================================================
# ТЕСТЫ: GATE 0-3 integration
# =============================================================================


def test_gate04_gate00_blocked(gate04, gate01_pass, gate02_pass, gate03_pass):
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
    atr = 500.0
    
    result = gate04.evaluate(gate00_blocked, gate01_pass, gate02_pass, gate03_pass, signal, atr)
    
    assert not result.entry_allowed
    assert "gate00_blocked" in result.block_reason


def test_gate04_gate03_blocked(gate04, gate00_pass, gate01_pass, gate02_pass):
    """BLOCK: GATE 3 заблокировал."""
    gate03_blocked = Gate03Result(
        entry_allowed=False,
        block_reason="incompatible_regime_strategy",
        engine_type=EngineType.RANGE,
        final_regime=FinalRegime.TREND_UP,
        is_compatible=False,
        details="RANGE engine incompatible with TREND_UP"
    )
    
    signal = make_signal_long()
    atr = 500.0
    
    result = gate04.evaluate(gate00_pass, gate01_pass, gate02_pass, gate03_blocked, signal, atr)
    
    assert not result.entry_allowed
    assert "gate03_blocked" in result.block_reason


# =============================================================================
# ТЕСТЫ: Edge cases
# =============================================================================


def test_gate04_atr_very_small(gate04, gate00_pass, gate01_pass, gate02_pass, gate03_pass):
    """BLOCK: ATR слишком маленький (< min_atr_for_validation)."""
    config = Gate04Config(min_atr_for_validation=1e-6)
    gate04_custom = Gate04SignalValidation(config)
    
    signal = make_signal_long()
    atr = 1e-9  # Слишком маленький
    
    result = gate04_custom.evaluate(gate00_pass, gate01_pass, gate02_pass, gate03_pass, signal, atr)
    
    assert not result.entry_allowed
    assert "invalid_atr" in result.block_reason


def test_gate04_multiple_validations_pass(gate04, gate00_pass, gate01_pass, gate02_pass, gate03_pass):
    """PASS: Все валидации проходят одновременно."""
    # entry=50000, sl=49250, tp=52875
    # Profit = 52875 - 50000 = 2875
    # Loss = 50000 - 49250 = 750
    # RR = 2875 / 750 ≈ 3.833
    # SL distance = 750, в ATR = 1.5
    signal = make_signal_long(entry=50000, sl=49250, tp=52875, rr_min=1.5, sl_min_atr=0.5, sl_max_atr=3.0)
    atr = 500.0  # SL distance = 750, в ATR = 1.5
    
    result = gate04.evaluate(gate00_pass, gate01_pass, gate02_pass, gate03_pass, signal, atr)
    
    assert result.entry_allowed
    assert result.rr_valid
    assert result.sl_distance_valid
    assert result.prices_valid
    assert result.raw_rr == pytest.approx(3.833333, abs=1e-3)
    assert result.sl_distance_atr == pytest.approx(1.5, abs=1e-6)
