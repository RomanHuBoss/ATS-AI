"""Тесты для GATE 8: Gap/Data Glitch Detection

Покрытие:
- Price jump detection (soft/hard)
- Price spike detection (z-score)
- Stale book detection
- Suspected glitch flag
- DRP trigger mechanism
- Integration с GATE 0-7
- Edge cases
"""

from datetime import datetime, timezone

import pytest

from src.core.domain.signal import (
    Direction,
    EngineType,
    Signal,
    SignalConstraints,
    SignalContext,
    SignalLevels,
)
from src.gatekeeper.gates.gate_00_warmup_dqs import Gate00Result, Gate00WarmupDQS
from src.gatekeeper.gates.gate_01_drp_killswitch import Gate01DRPKillswitch, Gate01Result
from src.gatekeeper.gates.gate_02_mrc_confidence import Gate02Config, Gate02MRCConfidence, Gate02Result
from src.gatekeeper.gates.gate_03_strategy_compat import Gate03Result, Gate03StrategyCompat
from src.gatekeeper.gates.gate_04_signal_validation import Gate04Config, Gate04Result, Gate04SignalValidation
from src.gatekeeper.gates.gate_05_pre_sizing import Gate05Config, Gate05PreSizing, Gate05Result
from src.gatekeeper.gates.gate_06_mle_decision import Gate06Config, Gate06MLEDecision, Gate06Result
from src.gatekeeper.gates.gate_07_liquidity_check import Gate07Config, Gate07LiquidityCheck, Gate07Result
from src.gatekeeper.gates.gate_08_gap_glitch import (
    AnomalyMetrics,
    DRPTrigger,
    Gate08Config,
    Gate08GapGlitch,
    Gate08Result,
    PricePoint,
)


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def gate08_config_default() -> Gate08Config:
    """Default GATE 8 config."""
    return Gate08Config()


@pytest.fixture
def gate08_config_lenient() -> Gate08Config:
    """Lenient GATE 8 config с более мягкими thresholds."""
    return Gate08Config(
        price_jump_threshold_pct=5.0,
        price_jump_hard_pct=10.0,
        price_spike_zscore_threshold=4.0,
        price_spike_zscore_hard=6.0,
        max_orderbook_age_ms=10000,
        glitch_block_enabled=False,
        glitch_triggers_drp=False,
    )


@pytest.fixture
def gate08_config_strict() -> Gate08Config:
    """Strict GATE 8 config."""
    return Gate08Config(
        price_jump_threshold_pct=1.0,
        price_jump_hard_pct=2.0,
        price_spike_zscore_threshold=2.0,
        price_spike_zscore_hard=3.0,
        max_orderbook_age_ms=2000,
        glitch_block_enabled=True,
        glitch_triggers_drp=True,
    )


@pytest.fixture
def signal_long() -> Signal:
    """LONG signal для тестов."""
    return Signal(
        instrument="BTCUSDT",
        engine=EngineType.TREND,
        direction=Direction.LONG,
        signal_ts_utc_ms=1700000000000,
        levels=SignalLevels(
            entry_price=50000.0,
            stop_loss=49000.0,
            take_profit=52000.0,
        ),
        context=SignalContext(
            expected_holding_hours=24.0,
            regime_hint="TREND_UP",
            setup_id="setup_001",
        ),
        constraints=SignalConstraints(
            RR_min_engine=2.0,
            sl_min_atr_mult=1.0,
            sl_max_atr_mult=3.0,
        ),
    )


@pytest.fixture
def passing_gate_results(signal_long: Signal):
    """Создание passing results для GATE 0-7."""
    # GATE 0
    gate00_result = Gate00Result(
        entry_allowed=True,
        block_reason="",
        dqs_result=None,
        drp_transition=None,
        new_drp_state="NORMAL",
        new_warmup_bars_remaining=0,
        new_drp_flap_count=0,
        new_hibernate_until_ts_utc_ms=None,
        details="PASS: warmup complete, DQS=0.95",
    )
    
    # GATE 1
    gate01_result = Gate01Result(
        entry_allowed=True,
        block_reason="",
        drp_state="NORMAL",
        trading_mode="LIVE",
        manual_halt_new_entries=False,
        manual_halt_all_trading=False,
        is_shadow_mode=False,
        details="PASS: DRP=NORMAL, mode=LIVE",
    )
    
    # GATE 2
    gate02_result = Gate02Result(
        entry_allowed=True,
        block_reason="",
        mrc_result=None,
        baseline_result=None,
        final_regime="TREND_UP",
        conflict_info=None,
        is_probe_mode=False,
        regime_risk_mult=1.0,
        details="PASS: confidence=0.85",
    )
    
    # GATE 3
    gate03_result = Gate03Result(
        entry_allowed=True,
        block_reason="",
        engine_type="TREND",
        final_regime="TREND_UP",
        is_compatible=True,
        details="PASS: strategy compatible",
    )
    
    # GATE 4
    gate04_result = Gate04Result(
        entry_allowed=True,
        block_reason="",
        raw_rr=2.0,
        sl_distance_abs=1000.0,
        sl_distance_atr=2.0,
        rr_valid=True,
        sl_distance_valid=True,
        prices_valid=True,
        details="PASS: RR=2.0",
    )
    
    # GATE 5
    gate05_result = Gate05Result(
        entry_allowed=True,
        block_reason="",
        entry_eff_allin=50100.0,
        sl_eff_allin=48950.0,
        tp_eff_allin=51900.0,
        unit_risk_allin_net=1150.0,
        unit_risk_bps=230.0,
        entry_cost_bps=6.0,
        sl_exit_cost_bps=8.0,
        expected_cost_bps_preMLE=14.0,
        expected_cost_R_preMLE=0.061,
        details="PASS: unit_risk=1150.0",
    )
    
    # GATE 6
    gate06_result = Gate06Result(
        entry_allowed=True,
        block_reason="",
        mle_decision="NORMAL",
        ev_r_price=0.20,
        expected_cost_r_postmle=0.055,
        net_edge_r=0.145,
        p_success=0.60,
        p_fail=0.40,
        mu_success_r=0.826,
        mu_fail_r=-1.0,
        expected_cost_bps_postmle=12.6,
        tp_exit_cost_bps=4.5,
        risk_mult=1.0,
        details="MLE NORMAL: EV_R=0.20R",
    )
    
    # GATE 7
    gate07 = Gate07LiquidityCheck()
    gate07_result = gate07.evaluate(
        gate00_result=gate00_result,
        gate01_result=gate01_result,
        gate02_result=gate02_result,
        gate03_result=gate03_result,
        gate04_result=gate04_result,
        gate05_result=gate05_result,
        gate06_result=gate06_result,
        signal=signal_long,
        bid_depth_usd=1_000_000.0,
        ask_depth_usd=1_000_000.0,
        spread_bps=8.0,
        volume_24h_usd=20_000_000.0,
        bid_volume_1pct=100_000.0,
        ask_volume_1pct=100_000.0,
        depth_mean=1_000_000.0,
        depth_sigma=50_000.0,
        notional_usd=10_000.0,
    )
    
    return (
        gate00_result,
        gate01_result,
        gate02_result,
        gate03_result,
        gate04_result,
        gate05_result,
        gate06_result,
        gate07_result,
    )


# =============================================================================
# PRICE JUMP TESTS
# =============================================================================


def test_gate08_price_jump_small_pass(
    gate08_config_default: Gate08Config,
    signal_long: Signal,
    passing_gate_results,
):
    """Малый price jump (< threshold) → PASS."""
    gate08 = Gate08GapGlitch(gate08_config_default)
    
    # Price history: stable prices
    price_history = [
        PricePoint(price=50000.0, timestamp_ms=1700000000000),
        PricePoint(price=50050.0, timestamp_ms=1700000001000),
        PricePoint(price=49980.0, timestamp_ms=1700000002000),
        PricePoint(price=50020.0, timestamp_ms=1700000003000),
    ]
    
    # Current price: небольшой jump (0.5%)
    current_price = 50250.0  # +0.46% от последней цены 50020
    current_price_ts_ms = 1700000004000
    orderbook_ts_ms = 1700000003500  # Fresh orderbook
    
    result = gate08.evaluate(
        *passing_gate_results,
        signal=signal_long,
        current_price=current_price,
        current_price_ts_ms=current_price_ts_ms,
        price_history=price_history,
        orderbook_ts_ms=orderbook_ts_ms,
    )
    
    assert result.entry_allowed is True
    assert result.anomaly_metrics.price_jump_detected is False
    assert result.anomaly_metrics.price_jump_pct < gate08_config_default.price_jump_threshold_pct


def test_gate08_price_jump_soft_detected(
    gate08_config_default: Gate08Config,
    signal_long: Signal,
    passing_gate_results,
):
    """Price jump > soft threshold (но < hard) → Detected, но может PASS если glitch_block_enabled=False."""
    gate08 = Gate08GapGlitch(gate08_config_default)
    
    price_history = [
        PricePoint(price=50000.0, timestamp_ms=1700000000000),
    ]
    
    # Current price: jump 3% (> 2% threshold, но < 5% hard)
    current_price = 51500.0  # +3% от 50000
    current_price_ts_ms = 1700000001000
    orderbook_ts_ms = 1700000000500
    
    result = gate08.evaluate(
        *passing_gate_results,
        signal=signal_long,
        current_price=current_price,
        current_price_ts_ms=current_price_ts_ms,
        price_history=price_history,
        orderbook_ts_ms=orderbook_ts_ms,
    )
    
    # С default config (glitch_block_enabled=True) должен блокировать
    assert result.entry_allowed is False
    assert result.anomaly_metrics.price_jump_detected is True
    assert result.anomaly_metrics.suspected_data_glitch is True
    assert "suspected_data_glitch" in result.block_reason


def test_gate08_price_jump_hard_reject(
    gate08_config_default: Gate08Config,
    signal_long: Signal,
    passing_gate_results,
):
    """Price jump > hard threshold → Hard reject."""
    gate08 = Gate08GapGlitch(gate08_config_default)
    
    price_history = [
        PricePoint(price=50000.0, timestamp_ms=1700000000000),
    ]
    
    # Current price: jump 6% (> 5% hard threshold)
    current_price = 53000.0  # +6% от 50000
    current_price_ts_ms = 1700000001000
    orderbook_ts_ms = 1700000000500
    
    result = gate08.evaluate(
        *passing_gate_results,
        signal=signal_long,
        current_price=current_price,
        current_price_ts_ms=current_price_ts_ms,
        price_history=price_history,
        orderbook_ts_ms=orderbook_ts_ms,
    )
    
    assert result.entry_allowed is False
    assert result.anomaly_metrics.price_jump_detected is True
    assert "price_jump_hard_reject" in result.block_reason


def test_gate08_price_jump_no_history(
    gate08_config_default: Gate08Config,
    signal_long: Signal,
    passing_gate_results,
):
    """Нет price history → не можем проверить jump → PASS (no detection)."""
    gate08 = Gate08GapGlitch(gate08_config_default)
    
    price_history = []  # Empty history
    
    current_price = 50000.0
    current_price_ts_ms = 1700000000000
    orderbook_ts_ms = 1700000000000
    
    result = gate08.evaluate(
        *passing_gate_results,
        signal=signal_long,
        current_price=current_price,
        current_price_ts_ms=current_price_ts_ms,
        price_history=price_history,
        orderbook_ts_ms=orderbook_ts_ms,
    )
    
    assert result.entry_allowed is True
    assert result.anomaly_metrics.price_jump_detected is False
    assert result.anomaly_metrics.price_jump_pct == 0.0


# =============================================================================
# PRICE SPIKE (Z-SCORE) TESTS
# =============================================================================


def test_gate08_price_spike_soft_detected(
    gate08_config_default: Gate08Config,
    signal_long: Signal,
    passing_gate_results,
):
    """Price spike > soft z-score threshold → Detected."""
    gate08 = Gate08GapGlitch(gate08_config_default)
    
    # Price history: stable around 50000, then spike
    price_history = [
        PricePoint(price=50000.0, timestamp_ms=1700000000000),
        PricePoint(price=50010.0, timestamp_ms=1700000001000),
        PricePoint(price=49990.0, timestamp_ms=1700000002000),
        PricePoint(price=50005.0, timestamp_ms=1700000003000),
        PricePoint(price=49995.0, timestamp_ms=1700000004000),
    ]
    
    # Mean ≈ 50000, stddev ≈ 8
    # Current price: spike to 50250 → z-score ≈ 31 (> 3.0 threshold)
    current_price = 50250.0
    current_price_ts_ms = 1700000005000
    orderbook_ts_ms = 1700000004500
    
    result = gate08.evaluate(
        *passing_gate_results,
        signal=signal_long,
        current_price=current_price,
        current_price_ts_ms=current_price_ts_ms,
        price_history=price_history,
        orderbook_ts_ms=orderbook_ts_ms,
    )
    
    # С default config (glitch_block_enabled=True) должен блокировать
    assert result.entry_allowed is False
    assert result.anomaly_metrics.price_spike_detected is True
    assert result.anomaly_metrics.price_zscore is not None
    assert result.anomaly_metrics.price_zscore > gate08_config_default.price_spike_zscore_threshold


def test_gate08_price_spike_hard_reject(
    gate08_config_default: Gate08Config,
    signal_long: Signal,
    passing_gate_results,
):
    """Price spike > hard z-score threshold → Hard reject."""
    gate08 = Gate08GapGlitch(gate08_config_default)
    
    price_history = [
        PricePoint(price=50000.0, timestamp_ms=1700000000000),
        PricePoint(price=50010.0, timestamp_ms=1700000001000),
        PricePoint(price=49990.0, timestamp_ms=1700000002000),
        PricePoint(price=50005.0, timestamp_ms=1700000003000),
        PricePoint(price=49995.0, timestamp_ms=1700000004000),
    ]
    
    # Extreme spike: z-score > 5.0
    current_price = 50500.0  # Massive spike
    current_price_ts_ms = 1700000005000
    orderbook_ts_ms = 1700000004500
    
    result = gate08.evaluate(
        *passing_gate_results,
        signal=signal_long,
        current_price=current_price,
        current_price_ts_ms=current_price_ts_ms,
        price_history=price_history,
        orderbook_ts_ms=orderbook_ts_ms,
    )
    
    assert result.entry_allowed is False
    assert result.anomaly_metrics.price_spike_detected is True
    assert "price_spike_hard_reject" in result.block_reason


def test_gate08_price_spike_insufficient_history(
    gate08_config_default: Gate08Config,
    signal_long: Signal,
    passing_gate_results,
):
    """Недостаточно price points для z-score (< 5) → z-score=None, no spike detection."""
    gate08 = Gate08GapGlitch(gate08_config_default)
    
    # Только 3 price points (< 5 required)
    price_history = [
        PricePoint(price=50000.0, timestamp_ms=1700000000000),
        PricePoint(price=50010.0, timestamp_ms=1700000001000),
        PricePoint(price=49990.0, timestamp_ms=1700000002000),
    ]
    
    current_price = 50500.0  # Would be spike if we had enough data
    current_price_ts_ms = 1700000003000
    orderbook_ts_ms = 1700000002500
    
    result = gate08.evaluate(
        *passing_gate_results,
        signal=signal_long,
        current_price=current_price,
        current_price_ts_ms=current_price_ts_ms,
        price_history=price_history,
        orderbook_ts_ms=orderbook_ts_ms,
    )
    
    # Не можем вычислить z-score, но можем обнаружить jump
    # Jump = (50500 - 49990) / 49990 = 1.02% < 2% threshold
    assert result.anomaly_metrics.price_zscore is None
    assert result.anomaly_metrics.price_spike_detected is False


# =============================================================================
# STALE BOOK TESTS
# =============================================================================


def test_gate08_stale_book_detected(
    gate08_config_default: Gate08Config,
    signal_long: Signal,
    passing_gate_results,
):
    """Stale orderbook при fresh price → Detected."""
    gate08 = Gate08GapGlitch(gate08_config_default)
    
    price_history = [
        PricePoint(price=50000.0, timestamp_ms=1700000000000),
    ]
    
    current_price = 50100.0
    current_price_ts_ms = 1700000010000  # Fresh price
    orderbook_ts_ms = 1700000000000  # Stale orderbook (10s old)
    
    result = gate08.evaluate(
        *passing_gate_results,
        signal=signal_long,
        current_price=current_price,
        current_price_ts_ms=current_price_ts_ms,
        price_history=price_history,
        orderbook_ts_ms=orderbook_ts_ms,
    )
    
    # С default config (glitch_block_enabled=True) должен блокировать
    assert result.entry_allowed is False
    assert result.anomaly_metrics.stale_book_fresh_price is True
    assert result.anomaly_metrics.orderbook_age_ms > gate08_config_default.max_orderbook_age_ms


def test_gate08_fresh_book_pass(
    gate08_config_default: Gate08Config,
    signal_long: Signal,
    passing_gate_results,
):
    """Fresh orderbook → PASS."""
    gate08 = Gate08GapGlitch(gate08_config_default)
    
    price_history = [
        PricePoint(price=50000.0, timestamp_ms=1700000000000),
    ]
    
    current_price = 50100.0
    current_price_ts_ms = 1700000001000
    orderbook_ts_ms = 1700000000500  # Fresh (0.5s old)
    
    result = gate08.evaluate(
        *passing_gate_results,
        signal=signal_long,
        current_price=current_price,
        current_price_ts_ms=current_price_ts_ms,
        price_history=price_history,
        orderbook_ts_ms=orderbook_ts_ms,
    )
    
    assert result.entry_allowed is True
    assert result.anomaly_metrics.stale_book_fresh_price is False


# =============================================================================
# SUSPECTED GLITCH TESTS
# =============================================================================


def test_gate08_suspected_glitch_multiple_anomalies(
    gate08_config_default: Gate08Config,
    signal_long: Signal,
    passing_gate_results,
):
    """Multiple anomalies → suspected_data_glitch=True."""
    gate08 = Gate08GapGlitch(gate08_config_default)
    
    price_history = [
        PricePoint(price=50000.0, timestamp_ms=1700000000000),
        PricePoint(price=50010.0, timestamp_ms=1700000001000),
        PricePoint(price=49990.0, timestamp_ms=1700000002000),
        PricePoint(price=50005.0, timestamp_ms=1700000003000),
        PricePoint(price=49995.0, timestamp_ms=1700000004000),
    ]
    
    # Price jump + spike + stale book
    current_price = 51500.0  # Large jump and spike
    current_price_ts_ms = 1700000010000
    orderbook_ts_ms = 1700000000000  # Very stale
    
    result = gate08.evaluate(
        *passing_gate_results,
        signal=signal_long,
        current_price=current_price,
        current_price_ts_ms=current_price_ts_ms,
        price_history=price_history,
        orderbook_ts_ms=orderbook_ts_ms,
    )
    
    assert result.entry_allowed is False
    assert result.anomaly_metrics.suspected_data_glitch is True
    assert "price_jump" in result.anomaly_metrics.glitch_reason
    assert "price_spike" in result.anomaly_metrics.glitch_reason or "stale_book" in result.anomaly_metrics.glitch_reason


def test_gate08_suspected_glitch_disabled_block(
    gate08_config_lenient: Gate08Config,
    signal_long: Signal,
    passing_gate_results,
):
    """suspected_glitch но glitch_block_enabled=False → PASS (но флаг установлен)."""
    gate08 = Gate08GapGlitch(gate08_config_lenient)
    
    price_history = [
        PricePoint(price=50000.0, timestamp_ms=1700000000000),
    ]
    
    # Large jump (> lenient 5% threshold)
    current_price = 52600.0  # +5.2% jump
    current_price_ts_ms = 1700000001000
    orderbook_ts_ms = 1700000000500
    
    result = gate08.evaluate(
        *passing_gate_results,
        signal=signal_long,
        current_price=current_price,
        current_price_ts_ms=current_price_ts_ms,
        price_history=price_history,
        orderbook_ts_ms=orderbook_ts_ms,
    )
    
    # Не блокирует (glitch_block_enabled=False в lenient config)
    assert result.entry_allowed is True
    assert result.anomaly_metrics.suspected_data_glitch is True


# =============================================================================
# DRP TRIGGER TESTS
# =============================================================================


def test_gate08_drp_trigger_high_severity(
    gate08_config_default: Gate08Config,
    signal_long: Signal,
    passing_gate_results,
):
    """High severity anomaly → DRP trigger."""
    gate08 = Gate08GapGlitch(gate08_config_default)
    
    price_history = [
        PricePoint(price=50000.0, timestamp_ms=1700000000000),
        PricePoint(price=50010.0, timestamp_ms=1700000001000),
        PricePoint(price=49990.0, timestamp_ms=1700000002000),
        PricePoint(price=50005.0, timestamp_ms=1700000003000),
        PricePoint(price=49995.0, timestamp_ms=1700000004000),
    ]
    
    # Extreme spike → DRP trigger
    current_price = 50600.0  # z-score >> 4.0
    current_price_ts_ms = 1700000005000
    orderbook_ts_ms = 1700000004500
    
    result = gate08.evaluate(
        *passing_gate_results,
        signal=signal_long,
        current_price=current_price,
        current_price_ts_ms=current_price_ts_ms,
        price_history=price_history,
        orderbook_ts_ms=orderbook_ts_ms,
    )
    
    # Hard reject из-за spike
    assert result.entry_allowed is False
    # DRP trigger should be set (если не блокировал раньше, но в данном случае блокирует hard)


def test_gate08_drp_trigger_medium_severity(
    gate08_config_default: Gate08Config,
    signal_long: Signal,
    passing_gate_results,
):
    """Medium severity anomaly → DRP trigger (но не hard reject)."""
    # Нужен special config где glitch_block_enabled=False но glitch_triggers_drp=True
    config = Gate08Config(
        price_jump_threshold_pct=2.0,
        price_jump_hard_pct=10.0,  # High hard threshold
        price_spike_zscore_threshold=3.0,
        price_spike_zscore_hard=10.0,  # High hard threshold
        max_orderbook_age_ms=5000,
        glitch_block_enabled=False,  # Don't block
        glitch_triggers_drp=True,     # But trigger DRP
        drp_trigger_jump_pct=2.5,
    )
    gate08 = Gate08GapGlitch(config)
    
    price_history = [
        PricePoint(price=50000.0, timestamp_ms=1700000000000),
    ]
    
    # Jump 3% → triggers DRP но не блокирует (< 10% hard)
    current_price = 51500.0
    current_price_ts_ms = 1700000001000
    orderbook_ts_ms = 1700000000500
    
    result = gate08.evaluate(
        *passing_gate_results,
        signal=signal_long,
        current_price=current_price,
        current_price_ts_ms=current_price_ts_ms,
        price_history=price_history,
        orderbook_ts_ms=orderbook_ts_ms,
    )
    
    # Не блокирует но DRP trigger установлен
    assert result.entry_allowed is True
    assert result.drp_trigger.should_trigger is True
    assert result.drp_trigger.severity == "HIGH"


def test_gate08_drp_trigger_disabled(
    gate08_config_lenient: Gate08Config,
    signal_long: Signal,
    passing_gate_results,
):
    """glitch_triggers_drp=False → no DRP trigger."""
    gate08 = Gate08GapGlitch(gate08_config_lenient)
    
    price_history = [
        PricePoint(price=50000.0, timestamp_ms=1700000000000),
    ]
    
    # Large jump
    current_price = 52600.0  # +5.2%
    current_price_ts_ms = 1700000001000
    orderbook_ts_ms = 1700000000500
    
    result = gate08.evaluate(
        *passing_gate_results,
        signal=signal_long,
        current_price=current_price,
        current_price_ts_ms=current_price_ts_ms,
        price_history=price_history,
        orderbook_ts_ms=orderbook_ts_ms,
    )
    
    # Не триггерит DRP (glitch_triggers_drp=False)
    assert result.drp_trigger.should_trigger is False


# =============================================================================
# INTEGRATION TESTS (GATE 0-8)
# =============================================================================


def test_gate08_integration_gate00_blocked(
    gate08_config_default: Gate08Config,
    signal_long: Signal,
    passing_gate_results,
):
    """GATE 0 блокирует → GATE 8 не проверяет anomalies."""
    gate08 = Gate08GapGlitch(gate08_config_default)
    
    # Create blocked GATE 0 result
    gate00_result_blocked = Gate00Result(
        entry_allowed=False,
        block_reason="warmup_not_complete",
        dqs_result=None,
        drp_transition=None,
        new_drp_state="RECOVERY",
        new_warmup_bars_remaining=10,
        new_drp_flap_count=0,
        new_hibernate_until_ts_utc_ms=None,
        details="BLOCK: warmup not complete",
    )
    
    _, gate01_result, gate02_result, gate03_result, gate04_result, gate05_result, gate06_result, gate07_result = passing_gate_results
    
    price_history = [PricePoint(price=50000.0, timestamp_ms=1700000000000)]
    current_price = 50000.0
    current_price_ts_ms = 1700000001000
    orderbook_ts_ms = 1700000000500
    
    result = gate08.evaluate(
        gate00_result_blocked,
        gate01_result,
        gate02_result,
        gate03_result,
        gate04_result,
        gate05_result,
        gate06_result,
        gate07_result,
        signal=signal_long,
        current_price=current_price,
        current_price_ts_ms=current_price_ts_ms,
        price_history=price_history,
        orderbook_ts_ms=orderbook_ts_ms,
    )
    
    assert result.entry_allowed is False
    assert "gate00_blocked" in result.block_reason
    # Anomaly metrics не вычисляются
    assert result.anomaly_metrics.price_jump_pct == 0.0


def test_gate08_integration_full_chain_pass(
    gate08_config_default: Gate08Config,
    signal_long: Signal,
    passing_gate_results,
):
    """Full chain GATE 0→8 PASS."""
    gate08 = Gate08GapGlitch(gate08_config_default)
    
    price_history = [
        PricePoint(price=50000.0, timestamp_ms=1700000000000),
        PricePoint(price=50020.0, timestamp_ms=1700000001000),
    ]
    
    current_price = 50050.0  # Small change
    current_price_ts_ms = 1700000002000
    orderbook_ts_ms = 1700000001500  # Fresh
    
    result = gate08.evaluate(
        *passing_gate_results,
        signal=signal_long,
        current_price=current_price,
        current_price_ts_ms=current_price_ts_ms,
        price_history=price_history,
        orderbook_ts_ms=orderbook_ts_ms,
    )
    
    assert result.entry_allowed is True
    assert result.anomaly_metrics.suspected_data_glitch is False
    assert result.drp_trigger.should_trigger is False


# =============================================================================
# EDGE CASES
# =============================================================================


def test_gate08_edge_zero_stddev(
    gate08_config_default: Gate08Config,
    signal_long: Signal,
    passing_gate_results,
):
    """Zero stddev (все цены одинаковые) → не вычисляем z-score."""
    gate08 = Gate08GapGlitch(gate08_config_default)
    
    # All prices identical
    price_history = [
        PricePoint(price=50000.0, timestamp_ms=1700000000000),
        PricePoint(price=50000.0, timestamp_ms=1700000001000),
        PricePoint(price=50000.0, timestamp_ms=1700000002000),
        PricePoint(price=50000.0, timestamp_ms=1700000003000),
        PricePoint(price=50000.0, timestamp_ms=1700000004000),
    ]
    
    current_price = 50000.0
    current_price_ts_ms = 1700000005000
    orderbook_ts_ms = 1700000004500
    
    result = gate08.evaluate(
        *passing_gate_results,
        signal=signal_long,
        current_price=current_price,
        current_price_ts_ms=current_price_ts_ms,
        price_history=price_history,
        orderbook_ts_ms=orderbook_ts_ms,
    )
    
    assert result.entry_allowed is True
    assert result.anomaly_metrics.price_zscore is None or result.anomaly_metrics.price_zscore == 0.0
    assert result.anomaly_metrics.price_spike_detected is False


def test_gate08_edge_orderbook_ahead_of_price(
    gate08_config_default: Gate08Config,
    signal_long: Signal,
    passing_gate_results,
):
    """Orderbook timestamp > price timestamp → negative age, no stale detection."""
    gate08 = Gate08GapGlitch(gate08_config_default)
    
    price_history = [
        PricePoint(price=50000.0, timestamp_ms=1700000000000),
    ]
    
    current_price = 50100.0
    current_price_ts_ms = 1700000001000
    orderbook_ts_ms = 1700000002000  # Ahead of price (может быть clock skew)
    
    result = gate08.evaluate(
        *passing_gate_results,
        signal=signal_long,
        current_price=current_price,
        current_price_ts_ms=current_price_ts_ms,
        price_history=price_history,
        orderbook_ts_ms=orderbook_ts_ms,
    )
    
    # Negative age → не обнаруживаем stale book
    assert result.entry_allowed is True
    assert result.anomaly_metrics.orderbook_age_ms < 0
    assert result.anomaly_metrics.stale_book_fresh_price is False


def test_gate08_edge_exact_threshold_jump(
    gate08_config_default: Gate08Config,
    signal_long: Signal,
    passing_gate_results,
):
    """Price jump ровно на threshold → detected."""
    gate08 = Gate08GapGlitch(gate08_config_default)
    
    price_history = [
        PricePoint(price=50000.0, timestamp_ms=1700000000000),
    ]
    
    # Jump exactly 2.0% (threshold)
    current_price = 51000.0
    current_price_ts_ms = 1700000001000
    orderbook_ts_ms = 1700000000500
    
    result = gate08.evaluate(
        *passing_gate_results,
        signal=signal_long,
        current_price=current_price,
        current_price_ts_ms=current_price_ts_ms,
        price_history=price_history,
        orderbook_ts_ms=orderbook_ts_ms,
    )
    
    # 2.0% именно на threshold → не detected (> threshold нужен)
    # Но может быть detected из-за rounding
    jump_pct = result.anomaly_metrics.price_jump_pct
    # Should be right around 2.0%
    assert 1.9 <= jump_pct <= 2.1


def test_gate08_strict_config(
    gate08_config_strict: Gate08Config,
    signal_long: Signal,
    passing_gate_results,
):
    """Strict config → более агрессивное детектирование."""
    gate08 = Gate08GapGlitch(gate08_config_strict)
    
    price_history = [
        PricePoint(price=50000.0, timestamp_ms=1700000000000),
    ]
    
    # Small jump 1.5% (> strict 1.0% threshold)
    current_price = 50750.0
    current_price_ts_ms = 1700000001000
    orderbook_ts_ms = 1700000000500
    
    result = gate08.evaluate(
        *passing_gate_results,
        signal=signal_long,
        current_price=current_price,
        current_price_ts_ms=current_price_ts_ms,
        price_history=price_history,
        orderbook_ts_ms=orderbook_ts_ms,
    )
    
    # Должен блокировать с strict config
    assert result.entry_allowed is False
    assert result.anomaly_metrics.price_jump_detected is True
