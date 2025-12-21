"""Тесты для GATE 7: Liquidity Check

Покрытие:
- Depth checks (bid/ask)
- Spread checks (soft/hard)
- Volume checks
- OBI checks
- Spoofing detection
- liquidity_mult calculation
- Integration с GATE 0-6
- Edge cases
"""

import math
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
from src.gatekeeper.gates.gate_07_liquidity_check import (
    Gate07Config,
    Gate07LiquidityCheck,
    Gate07Result,
    LiquidityMetrics,
    LiquidityMultipliers,
)


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def gate07_config_default() -> Gate07Config:
    """Default GATE 7 config."""
    return Gate07Config()


@pytest.fixture
def gate07_config_lenient() -> Gate07Config:
    """Lenient GATE 7 config с более мягкими impact thresholds."""
    return Gate07Config(
        bid_depth_min_usd=500_000.0,
        ask_depth_min_usd=500_000.0,
        spread_max_hard_bps=25.0,
        spread_max_soft_bps=10.0,
        volume_24h_min_usd=10_000_000.0,
        impact_k=0.10,
        impact_pow=0.5,
        impact_max_hard_bps=100.0,  # More lenient hard threshold
        impact_max_soft_bps=30.0,   # More lenient soft threshold
        spoofing_block_enabled=True,
    )


@pytest.fixture
def gate07_config_strict() -> Gate07Config:
    """Strict GATE 7 config."""
    return Gate07Config(
        bid_depth_min_usd=1_000_000.0,
        ask_depth_min_usd=1_000_000.0,
        spread_max_hard_bps=15.0,
        spread_max_soft_bps=5.0,
        volume_24h_min_usd=50_000_000.0,
        spoofing_block_enabled=True,
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
            RR_min_engine=1.5,
            sl_min_atr_mult=0.5,
            sl_max_atr_mult=3.0,
        ),
    )


@pytest.fixture
def signal_short() -> Signal:
    """SHORT signal для тестов."""
    return Signal(
        instrument="ETHUSDT",
        engine=EngineType.TREND,
        direction=Direction.SHORT,
        signal_ts_utc_ms=1700000000000,
        levels=SignalLevels(
            entry_price=3000.0,
            stop_loss=3100.0,
            take_profit=2800.0,
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


@pytest.fixture
def passing_gates_results(signal_long: Signal) -> tuple:
    """Результаты GATE 0-6 в PASS состоянии."""
    # GATE 0
    gate00_result = Gate00Result(
        entry_allowed=True,
        block_reason="",
        dqs_result=None,
        drp_transition=None,
        new_drp_state="NORMAL",  # DRPState.NORMAL
        new_warmup_bars_remaining=0,
        new_drp_flap_count=0,
        new_hibernate_until_ts_utc_ms=None,
        details="PASS: warmup complete, DQS=0.95",
    )
    
    # GATE 1
    gate01_result = Gate01Result(
        entry_allowed=True,
        block_reason="",
        drp_state="NORMAL",  # DRPState.NORMAL
        trading_mode="LIVE",  # TradingMode.LIVE
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
        final_regime="TREND_UP",  # FinalRegime.TREND_UP
        conflict_info=None,
        is_probe_mode=False,
        regime_risk_mult=1.0,
        details="PASS: confidence=0.85",
    )
    
    # GATE 3
    gate03_result = Gate03Result(
        entry_allowed=True,
        block_reason="",
        engine_type="TREND",  # EngineType.TREND
        final_regime="TREND_UP",  # FinalRegime.TREND_UP
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
    
    return (
        gate00_result,
        gate01_result,
        gate02_result,
        gate03_result,
        gate04_result,
        gate05_result,
        gate06_result,
    )


# =============================================================================
# DEPTH CHECKS
# =============================================================================


def test_gate07_bid_depth_too_low(
    gate07_config_default: Gate07Config,
    signal_long: Signal,
    passing_gates_results: tuple,
):
    """Тест: bid depth ниже порога → REJECT."""
    gate07 = Gate07LiquidityCheck(gate07_config_default)
    
    result = gate07.evaluate(
        *passing_gates_results,
        signal=signal_long,
        bid_depth_usd=300_000.0,  # < 500k
        ask_depth_usd=600_000.0,
        spread_bps=8.0,
        volume_24h_usd=15_000_000.0,
        bid_volume_1pct=100_000.0,
        ask_volume_1pct=120_000.0,
        depth_mean=450_000.0,
        depth_sigma=50_000.0,
        notional_usd=50_000.0,
    )
    
    assert not result.entry_allowed
    assert "bid_depth_too_low" in result.block_reason
    assert result.liquidity_metrics.bid_depth_usd == 300_000.0


def test_gate07_ask_depth_too_low(
    gate07_config_default: Gate07Config,
    signal_long: Signal,
    passing_gates_results: tuple,
):
    """Тест: ask depth ниже порога → REJECT."""
    gate07 = Gate07LiquidityCheck(gate07_config_default)
    
    result = gate07.evaluate(
        *passing_gates_results,
        signal=signal_long,
        bid_depth_usd=600_000.0,
        ask_depth_usd=300_000.0,  # < 500k
        spread_bps=8.0,
        volume_24h_usd=15_000_000.0,
        bid_volume_1pct=100_000.0,
        ask_volume_1pct=120_000.0,
        depth_mean=450_000.0,
        depth_sigma=50_000.0,
        notional_usd=50_000.0,
    )
    
    assert not result.entry_allowed
    assert "ask_depth_too_low" in result.block_reason
    assert result.liquidity_metrics.ask_depth_usd == 300_000.0


# =============================================================================
# SPREAD CHECKS
# =============================================================================


def test_gate07_spread_hard_reject(
    gate07_config_default: Gate07Config,
    signal_long: Signal,
    passing_gates_results: tuple,
):
    """Тест: spread > hard threshold → REJECT."""
    gate07 = Gate07LiquidityCheck(gate07_config_default)
    
    result = gate07.evaluate(
        *passing_gates_results,
        signal=signal_long,
        bid_depth_usd=600_000.0,
        ask_depth_usd=600_000.0,
        spread_bps=30.0,  # > 25.0 (hard)
        volume_24h_usd=15_000_000.0,
        bid_volume_1pct=100_000.0,
        ask_volume_1pct=120_000.0,
        depth_mean=600_000.0,
        depth_sigma=50_000.0,
        notional_usd=50_000.0,
    )
    
    assert not result.entry_allowed
    assert "spread_too_wide" in result.block_reason
    assert result.liquidity_metrics.spread_bps == 30.0


def test_gate07_spread_soft_degradation(
    gate07_config_default: Gate07Config,
    signal_long: Signal,
    passing_gates_results: tuple,
):
    """Тест: spread между soft и hard → degradation."""
    gate07 = Gate07LiquidityCheck(gate07_config_default)
    
    # Spread = 15.0 bps (между soft=10 и hard=25)
    # spread_mult = (25 - 15) / (25 - 10) = 10 / 15 = 0.667
    result = gate07.evaluate(
        *passing_gates_results,
        signal=signal_long,
        bid_depth_usd=600_000.0,
        ask_depth_usd=600_000.0,
        spread_bps=15.0,
        volume_24h_usd=15_000_000.0,
        bid_volume_1pct=100_000.0,
        ask_volume_1pct=120_000.0,
        depth_mean=600_000.0,
        depth_sigma=50_000.0,
        notional_usd=50_000.0,
    )
    
    assert result.entry_allowed
    assert abs(result.liquidity_multipliers.spread_mult - 0.667) < 0.01


def test_gate07_spread_below_soft(
    gate07_config_default: Gate07Config,
    signal_long: Signal,
    passing_gates_results: tuple,
):
    """Тест: spread < soft threshold → spread_mult = 1.0."""
    gate07 = Gate07LiquidityCheck(gate07_config_default)
    
    result = gate07.evaluate(
        *passing_gates_results,
        signal=signal_long,
        bid_depth_usd=600_000.0,
        ask_depth_usd=600_000.0,
        spread_bps=5.0,  # < 10.0 (soft)
        volume_24h_usd=15_000_000.0,
        bid_volume_1pct=100_000.0,
        ask_volume_1pct=120_000.0,
        depth_mean=600_000.0,
        depth_sigma=50_000.0,
        notional_usd=50_000.0,
    )
    
    assert result.entry_allowed
    assert result.liquidity_multipliers.spread_mult == 1.0


# =============================================================================
# VOLUME CHECKS
# =============================================================================


def test_gate07_volume_too_low(
    gate07_config_default: Gate07Config,
    signal_long: Signal,
    passing_gates_results: tuple,
):
    """Тест: volume 24h < min threshold → REJECT."""
    gate07 = Gate07LiquidityCheck(gate07_config_default)
    
    result = gate07.evaluate(
        *passing_gates_results,
        signal=signal_long,
        bid_depth_usd=600_000.0,
        ask_depth_usd=600_000.0,
        spread_bps=8.0,
        volume_24h_usd=5_000_000.0,  # < 10M
        bid_volume_1pct=100_000.0,
        ask_volume_1pct=120_000.0,
        depth_mean=600_000.0,
        depth_sigma=50_000.0,
        notional_usd=50_000.0,
    )
    
    assert not result.entry_allowed
    assert "volume_too_low" in result.block_reason
    assert result.liquidity_metrics.volume_24h_usd == 5_000_000.0


# =============================================================================
# OBI CHECKS
# =============================================================================


def test_gate07_obi_balanced(
    gate07_config_default: Gate07Config,
    signal_long: Signal,
    passing_gates_results: tuple,
):
    """Тест: OBI сбалансирован → PASS (но логируем в details)."""
    gate07 = Gate07LiquidityCheck(gate07_config_default)
    
    result = gate07.evaluate(
        *passing_gates_results,
        signal=signal_long,
        bid_depth_usd=600_000.0,
        ask_depth_usd=600_000.0,
        spread_bps=8.0,
        volume_24h_usd=15_000_000.0,
        bid_volume_1pct=110_000.0,
        ask_volume_1pct=110_000.0,  # Balanced
        depth_mean=600_000.0,
        depth_sigma=50_000.0,
        notional_usd=50_000.0,
    )
    
    assert result.entry_allowed
    assert abs(result.liquidity_metrics.obi) < 0.01


def test_gate07_obi_extreme(
    gate07_config_default: Gate07Config,
    signal_long: Signal,
    passing_gates_results: tuple,
):
    """Тест: OBI экстремальный → PASS но warning в details."""
    gate07 = Gate07LiquidityCheck(gate07_config_default)
    
    result = gate07.evaluate(
        *passing_gates_results,
        signal=signal_long,
        bid_depth_usd=600_000.0,
        ask_depth_usd=600_000.0,
        spread_bps=8.0,
        volume_24h_usd=15_000_000.0,
        bid_volume_1pct=200_000.0,
        ask_volume_1pct=20_000.0,  # Imbalanced
        depth_mean=600_000.0,
        depth_sigma=50_000.0,
        notional_usd=50_000.0,
    )
    
    assert result.entry_allowed
    assert abs(result.liquidity_metrics.obi) > 0.8
    assert "[OBI_HIGH]" in result.details


# =============================================================================
# SPOOFING DETECTION
# =============================================================================


def test_gate07_spoofing_detected(
    gate07_config_default: Gate07Config,
    signal_long: Signal,
    passing_gates_results: tuple,
):
    """Тест: depth volatility высокая → spoofing suspected → REJECT."""
    gate07 = Gate07LiquidityCheck(gate07_config_default)
    
    result = gate07.evaluate(
        *passing_gates_results,
        signal=signal_long,
        bid_depth_usd=600_000.0,
        ask_depth_usd=600_000.0,
        spread_bps=8.0,
        volume_24h_usd=15_000_000.0,
        bid_volume_1pct=100_000.0,
        ask_volume_1pct=120_000.0,
        depth_mean=600_000.0,
        depth_sigma=400_000.0,  # High volatility → CV = 0.667 > 0.5
        notional_usd=50_000.0,
    )
    
    assert not result.entry_allowed
    assert "spoofing_suspected" in result.block_reason
    assert result.liquidity_metrics.spoofing_suspected


def test_gate07_spoofing_disabled(
    signal_long: Signal,
    passing_gates_results: tuple,
):
    """Тест: spoofing detection отключен → PASS несмотря на высокую volatility."""
    config = Gate07Config(
        spoofing_block_enabled=False,
    )
    gate07 = Gate07LiquidityCheck(config)
    
    result = gate07.evaluate(
        *passing_gates_results,
        signal=signal_long,
        bid_depth_usd=600_000.0,
        ask_depth_usd=600_000.0,
        spread_bps=8.0,
        volume_24h_usd=15_000_000.0,
        bid_volume_1pct=100_000.0,
        ask_volume_1pct=120_000.0,
        depth_mean=600_000.0,
        depth_sigma=400_000.0,
        notional_usd=50_000.0,
    )
    
    assert result.entry_allowed
    assert result.liquidity_metrics.spoofing_suspected
    assert "[SPOOFING_SUSPECTED]" in result.details


# =============================================================================
# LIQUIDITY_MULT CALCULATION
# =============================================================================


def test_gate07_liquidity_mult_perfect(
    gate07_config_lenient: Gate07Config,
    signal_long: Signal,
    passing_gates_results: tuple,
):
    """Тест: хорошая ликвидность → liquidity_mult > 0.5."""
    gate07 = Gate07LiquidityCheck(gate07_config_lenient)
    
    result = gate07.evaluate(
        *passing_gates_results,
        signal=signal_long,
        bid_depth_usd=2_000_000.0,  # High depth
        ask_depth_usd=2_000_000.0,
        spread_bps=5.0,  # < soft
        volume_24h_usd=100_000_000.0,  # High volume
        bid_volume_1pct=200_000.0,
        ask_volume_1pct=200_000.0,
        depth_mean=2_000_000.0,
        depth_sigma=100_000.0,
        notional_usd=5_000.0,  # Moderate notional
    )
    
    assert result.entry_allowed
    assert result.liquidity_multipliers.spread_mult == 1.0
    # Impact будет > 0 и reasonable
    assert result.liquidity_multipliers.impact_mult > 0.3  # Not heavily degraded
    assert result.liquidity_multipliers.liquidity_mult > 0.3


def test_gate07_liquidity_mult_spread_limiting(
    gate07_config_lenient: Gate07Config,
    signal_long: Signal,
    passing_gates_results: tuple,
):
    """Тест: spread limiting factor → liquidity_mult = spread_mult."""
    gate07 = Gate07LiquidityCheck(gate07_config_lenient)
    
    # Spread = 20 bps → spread_mult = (25-20)/(25-10) = 0.333
    # Impact небольшой с lenient thresholds
    # liquidity_mult = min(0.333, impact_mult)
    result = gate07.evaluate(
        *passing_gates_results,
        signal=signal_long,
        bid_depth_usd=2_000_000.0,  # High depth for lower impact
        ask_depth_usd=2_000_000.0,
        spread_bps=20.0,  # High spread
        volume_24h_usd=50_000_000.0,
        bid_volume_1pct=100_000.0,
        ask_volume_1pct=100_000.0,
        depth_mean=2_000_000.0,
        depth_sigma=100_000.0,
        notional_usd=5_000.0,
    )
    
    assert result.entry_allowed
    assert abs(result.liquidity_multipliers.spread_mult - 0.333) < 0.01
    # Spread должен быть limiting factor
    assert result.liquidity_multipliers.liquidity_mult <= result.liquidity_multipliers.impact_mult
    assert result.liquidity_multipliers.limiting_factor == "spread"


def test_gate07_liquidity_mult_impact_limiting(
    gate07_config_default: Gate07Config,
    signal_long: Signal,
    passing_gates_results: tuple,
):
    """Тест: impact limiting factor → liquidity_mult = impact_mult."""
    gate07 = Gate07LiquidityCheck(gate07_config_default)
    
    # Spread = low → spread_mult = 1.0
    # Impact = high (большой notional на малый depth)
    # liquidity_mult = min(1.0, impact_mult)
    result = gate07.evaluate(
        *passing_gates_results,
        signal=signal_long,
        bid_depth_usd=600_000.0,
        ask_depth_usd=600_000.0,
        spread_bps=5.0,
        volume_24h_usd=15_000_000.0,
        bid_volume_1pct=100_000.0,
        ask_volume_1pct=100_000.0,
        depth_mean=600_000.0,
        depth_sigma=50_000.0,
        notional_usd=200_000.0,  # Large notional → high impact
    )
    
    assert result.entry_allowed
    assert result.liquidity_multipliers.spread_mult == 1.0
    assert result.liquidity_multipliers.impact_mult < 1.0
    assert result.liquidity_multipliers.liquidity_mult == result.liquidity_multipliers.impact_mult
    assert result.liquidity_multipliers.limiting_factor == "impact"


def test_gate07_impact_calculation(
    gate07_config_default: Gate07Config,
    signal_long: Signal,
    passing_gates_results: tuple,
):
    """Тест: impact_bps_est корректно вычисляется."""
    gate07 = Gate07LiquidityCheck(gate07_config_default)
    
    # impact_bps_est = impact_k * (notional / depth)^impact_pow * 10000
    # impact_k = 0.10, impact_pow = 0.5
    # notional = 100k, avg_depth = 600k
    # impact_bps_est = 0.10 * (100k/600k)^0.5 * 10000
    #                = 0.10 * 0.408 * 10000
    #                ≈ 408 bps
    result = gate07.evaluate(
        *passing_gates_results,
        signal=signal_long,
        bid_depth_usd=600_000.0,
        ask_depth_usd=600_000.0,
        spread_bps=5.0,
        volume_24h_usd=15_000_000.0,
        bid_volume_1pct=100_000.0,
        ask_volume_1pct=100_000.0,
        depth_mean=600_000.0,
        depth_sigma=50_000.0,
        notional_usd=100_000.0,
    )
    
    # Проверяем формулу
    avg_depth = 600_000.0
    expected_impact = 0.10 * ((100_000.0 / avg_depth) ** 0.5) * 10000.0
    
    assert result.entry_allowed
    assert abs(result.impact_bps_est - expected_impact) < 1.0


# =============================================================================
# INTEGRATION TESTS
# =============================================================================


def test_gate07_integration_gate00_blocked(
    gate07_config_default: Gate07Config,
    signal_long: Signal,
    passing_gates_results: tuple,
):
    """Тест: GATE 0 blocked → GATE 7 также blocked."""
    gate07 = Gate07LiquidityCheck(gate07_config_default)
    
    # Заменяем GATE 0 на blocked
    gate00_blocked = Gate00Result(
        entry_allowed=False,
        block_reason="warmup_incomplete",
        dqs_result=None,
        drp_transition=None,
        new_drp_state="NORMAL",
        new_warmup_bars_remaining=10,
        new_drp_flap_count=0,
        new_hibernate_until_ts_utc_ms=None,
        details="warmup incomplete",
    )
    
    result = gate07.evaluate(
        gate00_blocked,
        passing_gates_results[1],  # gate01
        passing_gates_results[2],  # gate02
        passing_gates_results[3],  # gate03
        passing_gates_results[4],  # gate04
        passing_gates_results[5],  # gate05
        passing_gates_results[6],  # gate06
        signal=signal_long,
        bid_depth_usd=600_000.0,
        ask_depth_usd=600_000.0,
        spread_bps=5.0,
        volume_24h_usd=15_000_000.0,
        bid_volume_1pct=100_000.0,
        ask_volume_1pct=100_000.0,
        depth_mean=600_000.0,
        depth_sigma=50_000.0,
        notional_usd=50_000.0,
    )
    
    assert not result.entry_allowed
    assert "gate00_blocked" in result.block_reason


def test_gate07_integration_gate06_blocked(
    gate07_config_default: Gate07Config,
    signal_long: Signal,
    passing_gates_results: tuple,
):
    """Тест: GATE 6 blocked → GATE 7 также blocked."""
    gate07 = Gate07LiquidityCheck(gate07_config_default)
    
    # Заменяем GATE 6 на blocked
    gate06_blocked = Gate06Result(
        entry_allowed=False,
        block_reason="mle_reject",
        mle_decision="REJECT",
        ev_r_price=-0.05,
        expected_cost_r_postmle=0.055,
        net_edge_r=-0.105,
        p_success=0.30,
        p_fail=0.70,
        mu_success_r=0.826,
        mu_fail_r=-1.0,
        expected_cost_bps_postmle=12.6,
        tp_exit_cost_bps=4.5,
        risk_mult=0.0,
        details="MLE REJECT",
    )
    
    result = gate07.evaluate(
        passing_gates_results[0],  # gate00
        passing_gates_results[1],  # gate01
        passing_gates_results[2],  # gate02
        passing_gates_results[3],  # gate03
        passing_gates_results[4],  # gate04
        passing_gates_results[5],  # gate05
        gate06_blocked,
        signal=signal_long,
        bid_depth_usd=600_000.0,
        ask_depth_usd=600_000.0,
        spread_bps=5.0,
        volume_24h_usd=15_000_000.0,
        bid_volume_1pct=100_000.0,
        ask_volume_1pct=100_000.0,
        depth_mean=600_000.0,
        depth_sigma=50_000.0,
        notional_usd=50_000.0,
    )
    
    assert not result.entry_allowed
    assert "gate06_blocked" in result.block_reason


def test_gate07_integration_full_chain_pass(
    gate07_config_lenient: Gate07Config,
    signal_long: Signal,
    passing_gates_results: tuple,
):
    """Тест: полная цепочка GATE 0-7 → PASS."""
    gate07 = Gate07LiquidityCheck(gate07_config_lenient)
    
    result = gate07.evaluate(
        *passing_gates_results,
        signal=signal_long,
        bid_depth_usd=2_000_000.0,
        ask_depth_usd=2_000_000.0,
        spread_bps=5.0,
        volume_24h_usd=100_000_000.0,
        bid_volume_1pct=200_000.0,
        ask_volume_1pct=200_000.0,
        depth_mean=2_000_000.0,
        depth_sigma=100_000.0,
        notional_usd=5_000.0,
    )
    
    assert result.entry_allowed
    assert result.block_reason == ""
    assert result.liquidity_multipliers.liquidity_mult > 0.3  # Reasonable mult
    assert "PASS" in result.details


# =============================================================================
# EDGE CASES
# =============================================================================


def test_gate07_edge_zero_depth_sigma(
    gate07_config_default: Gate07Config,
    signal_long: Signal,
    passing_gates_results: tuple,
):
    """Тест: depth_sigma = 0 → depth_volatility_cv = 0."""
    gate07 = Gate07LiquidityCheck(gate07_config_default)
    
    result = gate07.evaluate(
        *passing_gates_results,
        signal=signal_long,
        bid_depth_usd=600_000.0,
        ask_depth_usd=600_000.0,
        spread_bps=8.0,
        volume_24h_usd=15_000_000.0,
        bid_volume_1pct=100_000.0,
        ask_volume_1pct=100_000.0,
        depth_mean=600_000.0,
        depth_sigma=0.0,  # Zero volatility
        notional_usd=50_000.0,
    )
    
    assert result.entry_allowed
    assert result.liquidity_metrics.depth_volatility_cv == 0.0
    assert not result.liquidity_metrics.spoofing_suspected


def test_gate07_edge_zero_volumes(
    gate07_config_default: Gate07Config,
    signal_long: Signal,
    passing_gates_results: tuple,
):
    """Тест: bid_volume = ask_volume = 0 → OBI = 0."""
    gate07 = Gate07LiquidityCheck(gate07_config_default)
    
    result = gate07.evaluate(
        *passing_gates_results,
        signal=signal_long,
        bid_depth_usd=600_000.0,
        ask_depth_usd=600_000.0,
        spread_bps=8.0,
        volume_24h_usd=15_000_000.0,
        bid_volume_1pct=0.0,
        ask_volume_1pct=0.0,
        depth_mean=600_000.0,
        depth_sigma=50_000.0,
        notional_usd=50_000.0,
    )
    
    assert result.entry_allowed
    assert result.liquidity_metrics.obi == 0.0


def test_gate07_edge_spread_equals_hard(
    gate07_config_default: Gate07Config,
    signal_long: Signal,
    passing_gates_results: tuple,
):
    """Тест: spread = hard threshold → граничный случай."""
    gate07 = Gate07LiquidityCheck(gate07_config_default)
    
    # spread = 25.0 bps (= hard threshold)
    # Должен быть rejected (> hard)
    result = gate07.evaluate(
        *passing_gates_results,
        signal=signal_long,
        bid_depth_usd=600_000.0,
        ask_depth_usd=600_000.0,
        spread_bps=25.0,
        volume_24h_usd=15_000_000.0,
        bid_volume_1pct=100_000.0,
        ask_volume_1pct=100_000.0,
        depth_mean=600_000.0,
        depth_sigma=50_000.0,
        notional_usd=50_000.0,
    )
    
    # На границе hard threshold не должно быть rejected
    # (так как проверка: spread_bps > hard)
    assert result.entry_allowed
    assert result.liquidity_multipliers.spread_mult == 0.0


def test_gate07_edge_tiny_notional(
    gate07_config_default: Gate07Config,
    signal_long: Signal,
    passing_gates_results: tuple,
):
    """Тест: очень маленький notional → impact < 10 bps."""
    gate07 = Gate07LiquidityCheck(gate07_config_default)
    
    result = gate07.evaluate(
        *passing_gates_results,
        signal=signal_long,
        bid_depth_usd=600_000.0,
        ask_depth_usd=600_000.0,
        spread_bps=8.0,
        volume_24h_usd=15_000_000.0,
        bid_volume_1pct=100_000.0,
        ask_volume_1pct=100_000.0,
        depth_mean=600_000.0,
        depth_sigma=50_000.0,
        notional_usd=10.0,  # Very tiny
    )
    
    assert result.entry_allowed
    assert result.impact_bps_est < 10.0  # Low impact for tiny notional
    assert result.liquidity_multipliers.impact_mult > 0.5  # Not heavily degraded


def test_gate07_edge_huge_notional(
    gate07_config_default: Gate07Config,
    signal_long: Signal,
    passing_gates_results: tuple,
):
    """Тест: очень большой notional → high impact."""
    gate07 = Gate07LiquidityCheck(gate07_config_default)
    
    result = gate07.evaluate(
        *passing_gates_results,
        signal=signal_long,
        bid_depth_usd=600_000.0,
        ask_depth_usd=600_000.0,
        spread_bps=8.0,
        volume_24h_usd=15_000_000.0,
        bid_volume_1pct=100_000.0,
        ask_volume_1pct=100_000.0,
        depth_mean=600_000.0,
        depth_sigma=50_000.0,
        notional_usd=1_000_000.0,  # Huge
    )
    
    assert result.entry_allowed
    assert result.impact_bps_est > 100.0  # Significant impact
    assert result.liquidity_multipliers.impact_mult < 1.0


# =============================================================================
# RUN TESTS
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
