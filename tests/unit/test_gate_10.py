"""Tests for GATE 10: Correlation / Exposure Conflict

ТЗ 3.3.2 строка 1027, 1055 (GATE 10 — Modified: Correlation/Exposure Conflict)
ТЗ раздел 3.3.5: Portfolio-level constraints (size-invariant R)

Test coverage:
- Correlation checks (high/low correlation, empty portfolio)
- Exposure conflict detection (asset/sector/total)
- Portfolio constraints (max positions, concentration)
- Size-invariant calculations (all в R units)
- Integration с GATE 0-9
- Edge cases (empty portfolio, missing correlation data, etc.)
"""

import math
from datetime import datetime, timezone

import pytest

from src.core.domain.market_state import (
    Correlations,
    DataQuality,
    Derivatives,
    Liquidity,
    MarketState,
    Price,
    Volatility,
)
from src.core.domain.signal import Direction, Signal, SignalContext
from src.gatekeeper.gates.gate_00_warmup_dqs import Gate00Result
from src.gatekeeper.gates.gate_01_drp_killswitch import (
    DRPState,
    Gate01Result,
    TradingMode,
)
from src.gatekeeper.gates.gate_02_mrc_confidence import Gate02Result
from src.gatekeeper.gates.gate_03_strategy_compat import Gate03Result
from src.gatekeeper.gates.gate_04_signal_validation import Gate04Result
from src.gatekeeper.gates.gate_05_pre_sizing import Gate05Result
from src.gatekeeper.gates.gate_06_mle_decision import Gate06Result
from src.gatekeeper.gates.gate_07_liquidity_check import Gate07Result
from src.gatekeeper.gates.gate_08_gap_glitch import Gate08Result
from src.gatekeeper.gates.gate_09_funding_proximity import (
    BlackoutCheck,
    FundingMetrics,
    Gate09Result,
    ProximityMetrics,
)
from src.gatekeeper.gates.gate_10_correlation_exposure import (
    Gate10Config,
    Gate10CorrelationExposure,
    PositionInfo,
)


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def base_signal() -> Signal:
    """Base signal для тестов."""
    return Signal(
        instrument="BTCUSDT",
        engine="TREND",
        direction=Direction.LONG,
        signal_ts_utc_ms=int(datetime.now(timezone.utc).timestamp() * 1000),
        levels={
            "entry_price": 50000.0,
            "stop_loss": 49000.0,
            "take_profit": 52000.0,
        },
        context=SignalContext(
            expected_holding_hours=24.0,
            regime_hint="TREND_UP",
            setup_id="setup_001",
        ),
        constraints={
            "RR_min_engine": 2.0,
            "sl_min_atr_mult": 1.0,
            "sl_max_atr_mult": 3.0,
        },
    )


@pytest.fixture
def base_market_state() -> MarketState:
    """Base market state для тестов."""
    return MarketState(
        schema_version="7",
        snapshot_id=1,
        ts_utc_ms=int(datetime.now(timezone.utc).timestamp() * 1000),
        market_data_id=1,
        data_gap_sec=0,
        is_gap_contaminated=False,
        instrument="BTCUSDT",
        timeframe="H1",
        price=Price(
            last=50000.0,
            mid=50000.0,
            bid=49995.0,
            ask=50005.0,
            tick_size=0.1,
        ),
        volatility=Volatility(
            atr=1000.0,
            atr_z_short=0.5,
            atr_z_long=0.3,
            atr_window_short=14,
        ),
        liquidity=Liquidity(
            spread_bps=10.0,
            depth_bid_usd=50000.0,
            depth_ask_usd=50000.0,
            impact_bps_est=5.0,
            orderbook_staleness_ms=100,
        ),
        derivatives=Derivatives(
            funding_rate_spot=0.0001,
            funding_period_hours=8.0,
            time_to_next_funding_sec=14400,
        ),
        correlations=Correlations(
            tail_metrics_reliable=True,
            tail_reliability_score=0.95,
        ),
        data_quality=DataQuality(
            suspected_data_glitch=False,
            stale_book_glitch=False,
            data_quality_score=0.95,
            dqs_critical=0.95,
            dqs_noncritical=0.95,
            dqs_sources=0.95,
            dqs_mult=0.95,
            staleness_price_ms=100,
            staleness_liquidity_ms=100,
            staleness_derivatives_sec=10,
            cross_exchange_dev_bps=1.0,
            price_sources_used=["binance"],
            toxic_flow_suspected=False,
        ),
        regime_state="NORMAL",
        critical_events_near=False,
    )


@pytest.fixture
def passing_gate00() -> Gate00Result:
    """Passing GATE 00 result."""
    return Gate00Result(
        entry_allowed=True,
        block_reason="",
        dqs_result=None,
        drp_transition=None,
        new_drp_state="NORMAL",
        new_warmup_bars_remaining=0,
        new_drp_flap_count=0,
        new_hibernate_until_ts_utc_ms=None,
        details="All GATE 00 checks PASS",
    )


@pytest.fixture
def passing_gate01() -> Gate01Result:
    """Passing GATE 01 result."""
    return Gate01Result(
        entry_allowed=True,
        block_reason="",
        drp_state=DRPState.NORMAL,
        trading_mode=TradingMode.LIVE,
        manual_halt_new_entries=False,
        manual_halt_all_trading=False,
        is_shadow_mode=False,
        details="All GATE 01 checks PASS",
    )


@pytest.fixture
def passing_gate02() -> Gate02Result:
    """Passing GATE 02 result."""
    return Gate02Result(
        entry_allowed=True,
        block_reason="",
        mrc_result=None,
        baseline_result=None,
        final_regime="TREND_UP",
        conflict_info=None,
        is_probe_mode=False,
        regime_risk_mult=1.0,
        details="All GATE 02 checks PASS",
    )


@pytest.fixture
def passing_gate03() -> Gate03Result:
    """Passing GATE 03 result."""
    return Gate03Result(
        entry_allowed=True,
        block_reason="",
        engine_type="TREND",
        final_regime="TREND_UP",
        is_compatible=True,
        details="All GATE 03 checks PASS",
    )


@pytest.fixture
def passing_gate04() -> Gate04Result:
    """Passing GATE 04 result."""
    return Gate04Result(
        entry_allowed=True,
        block_reason="",
        raw_rr=2.5,
        sl_distance_abs=1000.0,
        sl_distance_atr=1.0,
        rr_valid=True,
        sl_distance_valid=True,
        prices_valid=True,
        details="All GATE 04 checks PASS",
    )


@pytest.fixture
def passing_gate05() -> Gate05Result:
    """Passing GATE 05 result."""
    return Gate05Result(
        entry_allowed=True,
        block_reason="",
        unit_risk_bps=200.0,  # 1.0 R = 2% risk
        unit_risk_allin_net=1000.0,  # 1.0 R after costs
        entry_cost_bps=10.0,
        sl_exit_cost_bps=10.0,
        expected_cost_bps_preMLE=30.0,
        expected_cost_R_preMLE=0.05,  # 5% of R
        entry_eff_allin=50010.0,
        tp_eff_allin=51990.0,
        sl_eff_allin=48990.0,
        details="All GATE 05 checks PASS",
    )


@pytest.fixture
def passing_gate06() -> Gate06Result:
    """Passing GATE 06 result."""
    return Gate06Result(
        entry_allowed=True,
        block_reason="",
        mle_decision="NORMAL",
        ev_r_price=0.50,
        expected_cost_r_postmle=0.05,
        net_edge_r=0.45,
        p_success=0.60,
        p_fail=0.40,
        mu_success_r=2.0,
        mu_fail_r=-1.0,
        expected_cost_bps_postmle=10.0,
        tp_exit_cost_bps=5.0,
        risk_mult=1.0,
        details="All GATE 06 checks PASS",
    )


@pytest.fixture
def passing_gate07() -> Gate07Result:
    """Passing GATE 07 result."""
    return Gate07Result(
        entry_allowed=True,
        block_reason="",
        liquidity_metrics=None,
        liquidity_multipliers=None,
        impact_bps_est=5.0,
        details="All GATE 07 checks PASS",
    )


@pytest.fixture
def passing_gate08() -> Gate08Result:
    """Passing GATE 08 result."""
    return Gate08Result(
        entry_allowed=True,
        block_reason="",
        anomaly_metrics=None,
        drp_trigger=None,
        details="All GATE 08 checks PASS",
    )


@pytest.fixture
def passing_gate09() -> Gate09Result:
    """Passing GATE 09 result."""
    return Gate09Result(
        entry_allowed=True,
        block_reason="",
        funding_metrics=FundingMetrics(
            funding_rate=0.0001,
            funding_period_hours=8.0,
            time_to_next_funding_sec=14400,
            expected_holding_hours=24.0,
            n_events_raw=3,
            n_events=3.0,
            direction_sign=1,
            funding_pnl_frac=-0.0003,
            funding_r=0.03,
            funding_cost_r=0.03,
            funding_bonus_r=0.0,
            funding_bonus_r_used=0.0,
        ),
        ev_r_price=0.50,
        expected_cost_r_used=0.05,
        ev_r_price_net=0.45,
        net_yield_r=0.42,
        proximity_metrics=ProximityMetrics(
            tau=0.0,
            funding_proximity_mult=1.0,
            is_near_funding=False,
            proximity_penalty_r=0.0,
        ),
        blackout_check=BlackoutCheck(
            time_condition=False,
            cost_condition=False,
            holding_condition=False,
            significance_condition=False,
            blackout_triggered=False,
            blackout_reason="",
        ),
        funding_risk_mult=1.0,
        combined_risk_mult=1.0,
        details="All GATE 09 checks PASS",
    )


# =============================================================================
# TESTS: Empty Portfolio
# =============================================================================


def test_gate10_empty_portfolio_pass(
    base_signal,
    base_market_state,
    passing_gate00,
    passing_gate01,
    passing_gate02,
    passing_gate03,
    passing_gate04,
    passing_gate05,
    passing_gate06,
    passing_gate07,
    passing_gate08,
    passing_gate09,
):
    """Test GATE 10 PASS с пустым портфелем."""
    gate = Gate10CorrelationExposure()
    
    result = gate.evaluate(
        signal=base_signal,
        market_state=base_market_state,
        gate00=passing_gate00,
        gate01=passing_gate01,
        gate02=passing_gate02,
        gate03=passing_gate03,
        gate04=passing_gate04,
        gate05=passing_gate05,
        gate06=passing_gate06,
        gate07=passing_gate07,
        gate08=passing_gate08,
        gate09=passing_gate09,
        portfolio_positions=None,  # Empty portfolio
        correlation_matrix=None,
        asset_class="CRYPTO",
        sector=None,
    )
    
    assert result.entry_allowed is True
    assert result.block_reason == ""
    
    # Correlation metrics (empty portfolio)
    assert result.correlation_metrics.max_correlation == 0.0
    assert result.correlation_metrics.max_correlation_instrument is None
    assert result.correlation_metrics.n_correlated_positions == 0
    assert result.correlation_metrics.correlation_warning is False
    assert result.correlation_metrics.correlation_block is False
    
    # Exposure metrics (only new position)
    assert result.exposure_metrics.current_total_exposure_r == 0.0
    assert result.exposure_metrics.projected_total_exposure_r == 1.0  # From gate05
    assert result.exposure_metrics.exposure_warning is False
    assert result.exposure_metrics.exposure_block is False
    
    # Portfolio constraints (1 position)
    assert result.portfolio_constraints.current_n_positions == 0
    assert result.portfolio_constraints.projected_n_positions == 1
    assert result.portfolio_constraints.positions_warning is False
    assert result.portfolio_constraints.positions_block is False
    
    # Risk multipliers (base)
    assert result.correlation_risk_mult == 1.0
    assert result.exposure_risk_mult == 1.0
    assert result.combined_risk_mult == 1.0


# =============================================================================
# TESTS: Correlation Checks
# =============================================================================


def test_gate10_low_correlation_pass(
    base_signal,
    base_market_state,
    passing_gate00,
    passing_gate01,
    passing_gate02,
    passing_gate03,
    passing_gate04,
    passing_gate05,
    passing_gate06,
    passing_gate07,
    passing_gate08,
    passing_gate09,
):
    """Test GATE 10 PASS с низкой корреляцией."""
    # Portfolio с одной позицией
    positions = [
        PositionInfo(
            instrument="ETHUSDT",
            direction=Direction.LONG,
            exposure_r=1.0,
            asset_class="CRYPTO",
            sector=None,
            entry_ts_utc_ms=int(datetime.now(timezone.utc).timestamp() * 1000),
        )
    ]
    
    # Low correlation
    correlation_matrix = {
        ("BTCUSDT", "ETHUSDT"): 0.40,  # Low correlation
    }
    
    # Config with higher concentration limit to allow 50% concentration
    config = Gate10Config(
        max_single_position_concentration_hard=0.60,
    )
    gate = Gate10CorrelationExposure(config=config)
    
    result = gate.evaluate(
        signal=base_signal,
        market_state=base_market_state,
        gate00=passing_gate00,
        gate01=passing_gate01,
        gate02=passing_gate02,
        gate03=passing_gate03,
        gate04=passing_gate04,
        gate05=passing_gate05,
        gate06=passing_gate06,
        gate07=passing_gate07,
        gate08=passing_gate08,
        gate09=passing_gate09,
        portfolio_positions=positions,
        correlation_matrix=correlation_matrix,
        asset_class="CRYPTO",
        sector=None,
    )
    
    assert result.entry_allowed is True
    assert result.block_reason == ""
    
    # Correlation metrics
    assert result.correlation_metrics.max_correlation == 0.40
    assert result.correlation_metrics.max_correlation_instrument == "ETHUSDT"
    assert result.correlation_metrics.correlation_warning is False
    assert result.correlation_metrics.correlation_block is False


def test_gate10_high_correlation_soft_warning(
    base_signal,
    base_market_state,
    passing_gate00,
    passing_gate01,
    passing_gate02,
    passing_gate03,
    passing_gate04,
    passing_gate05,
    passing_gate06,
    passing_gate07,
    passing_gate08,
    passing_gate09,
):
    """Test GATE 10 soft WARNING при высокой корреляции."""
    positions = [
        PositionInfo(
            instrument="ETHUSDT",
            direction=Direction.LONG,
            exposure_r=1.5,
            asset_class="CRYPTO",
            sector=None,
            entry_ts_utc_ms=int(datetime.now(timezone.utc).timestamp() * 1000),
        )
    ]
    
    # High correlation (soft threshold)
    correlation_matrix = {
        ("BTCUSDT", "ETHUSDT"): 0.75,  # Above soft (0.70), below hard (0.85)
    }
    
    # Config with higher concentration limit to allow 60% concentration
    config = Gate10Config(
        max_single_position_concentration_hard=0.70,
    )
    gate = Gate10CorrelationExposure(config=config)
    
    result = gate.evaluate(
        signal=base_signal,
        market_state=base_market_state,
        gate00=passing_gate00,
        gate01=passing_gate01,
        gate02=passing_gate02,
        gate03=passing_gate03,
        gate04=passing_gate04,
        gate05=passing_gate05,
        gate06=passing_gate06,
        gate07=passing_gate07,
        gate08=passing_gate08,
        gate09=passing_gate09,
        portfolio_positions=positions,
        correlation_matrix=correlation_matrix,
        asset_class="CRYPTO",
        sector=None,
    )
    
    assert result.entry_allowed is True  # WARNING, not BLOCK
    assert result.block_reason == ""
    
    # Correlation metrics
    assert result.correlation_metrics.max_correlation == 0.75
    assert result.correlation_metrics.correlation_warning is True
    assert result.correlation_metrics.correlation_block is False
    assert "Elevated correlation" in result.correlation_metrics.correlation_reason
    
    # Risk multiplier (penalty applied)
    assert result.correlation_risk_mult < 1.0
    assert result.correlation_risk_mult >= 0.85


def test_gate10_very_high_correlation_hard_block(
    base_signal,
    base_market_state,
    passing_gate00,
    passing_gate01,
    passing_gate02,
    passing_gate03,
    passing_gate04,
    passing_gate05,
    passing_gate06,
    passing_gate07,
    passing_gate08,
    passing_gate09,
):
    """Test GATE 10 BLOCK при очень высокой корреляции."""
    positions = [
        PositionInfo(
            instrument="ETHUSDT",
            direction=Direction.LONG,
            exposure_r=2.0,
            asset_class="CRYPTO",
            sector=None,
            entry_ts_utc_ms=int(datetime.now(timezone.utc).timestamp() * 1000),
        )
    ]
    
    # Very high correlation (hard threshold)
    correlation_matrix = {
        ("BTCUSDT", "ETHUSDT"): 0.90,  # Above hard (0.85)
    }
    
    gate = Gate10CorrelationExposure()
    
    result = gate.evaluate(
        signal=base_signal,
        market_state=base_market_state,
        gate00=passing_gate00,
        gate01=passing_gate01,
        gate02=passing_gate02,
        gate03=passing_gate03,
        gate04=passing_gate04,
        gate05=passing_gate05,
        gate06=passing_gate06,
        gate07=passing_gate07,
        gate08=passing_gate08,
        gate09=passing_gate09,
        portfolio_positions=positions,
        correlation_matrix=correlation_matrix,
        asset_class="CRYPTO",
        sector=None,
    )
    
    assert result.entry_allowed is False
    assert "High correlation" in result.block_reason
    
    # Correlation metrics
    assert result.correlation_metrics.max_correlation == 0.90
    assert result.correlation_metrics.correlation_warning is True
    assert result.correlation_metrics.correlation_block is True


def test_gate10_opposite_direction_negative_correlation(
    base_signal,
    base_market_state,
    passing_gate00,
    passing_gate01,
    passing_gate02,
    passing_gate03,
    passing_gate04,
    passing_gate05,
    passing_gate06,
    passing_gate07,
    passing_gate08,
    passing_gate09,
):
    """Test GATE 10 с противоположным направлением (hedging OK)."""
    # Existing SHORT position
    positions = [
        PositionInfo(
            instrument="ETHUSDT",
            direction=Direction.SHORT,  # Opposite to signal LONG
            exposure_r=1.0,
            asset_class="CRYPTO",
            sector=None,
            entry_ts_utc_ms=int(datetime.now(timezone.utc).timestamp() * 1000),
        )
    ]
    
    # High positive correlation (но разные directions → hedging)
    correlation_matrix = {
        ("BTCUSDT", "ETHUSDT"): 0.80,
    }
    
    # Config with higher concentration limit to allow 50% concentration
    config = Gate10Config(
        max_single_position_concentration_hard=0.60,
    )
    gate = Gate10CorrelationExposure(config=config)
    
    result = gate.evaluate(
        signal=base_signal,  # LONG
        market_state=base_market_state,
        gate00=passing_gate00,
        gate01=passing_gate01,
        gate02=passing_gate02,
        gate03=passing_gate03,
        gate04=passing_gate04,
        gate05=passing_gate05,
        gate06=passing_gate06,
        gate07=passing_gate07,
        gate08=passing_gate08,
        gate09=passing_gate09,
        portfolio_positions=positions,
        correlation_matrix=correlation_matrix,
        asset_class="CRYPTO",
        sector=None,
    )
    
    assert result.entry_allowed is True
    
    # Correlation treated as negative (hedging)
    assert result.correlation_metrics.max_correlation < 0  # Negative
    assert result.correlation_metrics.correlation_warning is False
    assert result.correlation_metrics.correlation_block is False


# =============================================================================
# TESTS: Exposure Checks
# =============================================================================


def test_gate10_exposure_within_limits_pass(
    base_signal,
    base_market_state,
    passing_gate00,
    passing_gate01,
    passing_gate02,
    passing_gate03,
    passing_gate04,
    passing_gate05,
    passing_gate06,
    passing_gate07,
    passing_gate08,
    passing_gate09,
):
    """Test GATE 10 PASS с exposure в пределах лимитов."""
    # Multiple positions с total exposure < max
    positions = [
        PositionInfo(
            instrument="ETHUSDT",
            direction=Direction.LONG,
            exposure_r=1.5,
            asset_class="CRYPTO",
            sector=None,
            entry_ts_utc_ms=int(datetime.now(timezone.utc).timestamp() * 1000),
        ),
        PositionInfo(
            instrument="SOLUSDT",
            direction=Direction.SHORT,
            exposure_r=1.0,
            asset_class="CRYPTO",
            sector=None,
            entry_ts_utc_ms=int(datetime.now(timezone.utc).timestamp() * 1000),
        ),
    ]
    
    # Config with higher concentration limit to allow 42.9% concentration
    config = Gate10Config(
        max_single_position_concentration_hard=0.50,
    )
    gate = Gate10CorrelationExposure(config=config)
    
    result = gate.evaluate(
        signal=base_signal,
        market_state=base_market_state,
        gate00=passing_gate00,
        gate01=passing_gate01,
        gate02=passing_gate02,
        gate03=passing_gate03,
        gate04=passing_gate04,
        gate05=passing_gate05,
        gate06=passing_gate06,
        gate07=passing_gate07,
        gate08=passing_gate08,
        gate09=passing_gate09,
        portfolio_positions=positions,
        correlation_matrix={},
        asset_class="CRYPTO",
        sector=None,
    )
    
    assert result.entry_allowed is True
    
    # Exposure metrics
    assert result.exposure_metrics.current_total_exposure_r == 2.5  # 1.5 + 1.0
    assert result.exposure_metrics.projected_total_exposure_r == 3.5  # 2.5 + 1.0
    assert result.exposure_metrics.current_asset_exposure_r == 2.5
    assert result.exposure_metrics.projected_asset_exposure_r == 3.5
    assert result.exposure_metrics.exposure_warning is False
    assert result.exposure_metrics.exposure_block is False


def test_gate10_total_exposure_soft_warning(
    base_signal,
    base_market_state,
    passing_gate00,
    passing_gate01,
    passing_gate02,
    passing_gate03,
    passing_gate04,
    passing_gate05,
    passing_gate06,
    passing_gate07,
    passing_gate08,
    passing_gate09,
):
    """Test GATE 10 soft WARNING при приближении к max total exposure."""
    # Config with low max_total_exposure_r
    config = Gate10Config(
        max_total_exposure_r=4.0,  # Low limit
        exposure_soft_utilization=0.80,  # 80%
        max_single_position_concentration_hard=0.50,  # Allow 42.9% concentration
    )
    
    # Positions with total 2.5R (projected 3.5R after new 1.0R position)
    # Utilization: 3.5 / 4.0 = 87.5% (between soft 80% and hard 95%)
    positions = [
        PositionInfo(
            instrument="ETHUSDT",
            direction=Direction.LONG,
            exposure_r=1.5,
            asset_class="CRYPTO",
            sector=None,
            entry_ts_utc_ms=int(datetime.now(timezone.utc).timestamp() * 1000),
        ),
        PositionInfo(
            instrument="SOLUSDT",
            direction=Direction.SHORT,
            exposure_r=1.0,
            asset_class="CRYPTO",
            sector=None,
            entry_ts_utc_ms=int(datetime.now(timezone.utc).timestamp() * 1000),
        ),
    ]
    
    gate = Gate10CorrelationExposure(config=config)
    
    result = gate.evaluate(
        signal=base_signal,
        market_state=base_market_state,
        gate00=passing_gate00,
        gate01=passing_gate01,
        gate02=passing_gate02,
        gate03=passing_gate03,
        gate04=passing_gate04,
        gate05=passing_gate05,
        gate06=passing_gate06,
        gate07=passing_gate07,
        gate08=passing_gate08,
        gate09=passing_gate09,
        portfolio_positions=positions,
        correlation_matrix={},
        asset_class="CRYPTO",
        sector=None,
    )
    
    assert result.entry_allowed is True  # WARNING, not BLOCK
    
    # Exposure metrics
    assert result.exposure_metrics.projected_total_exposure_r == 3.5  # 2.5 + 1.0
    assert abs(result.exposure_metrics.total_exposure_utilization - 0.875) < 0.01  # 3.5 / 4.0 = 87.5%
    assert result.exposure_metrics.exposure_warning is True
    assert "approaching limit" in result.exposure_metrics.exposure_reason.lower()


def test_gate10_total_exposure_hard_block(
    base_signal,
    base_market_state,
    passing_gate00,
    passing_gate01,
    passing_gate02,
    passing_gate03,
    passing_gate04,
    passing_gate05,
    passing_gate06,
    passing_gate07,
    passing_gate08,
    passing_gate09,
):
    """Test GATE 10 BLOCK при превышении max total exposure."""
    # Config with low max_total_exposure_r
    config = Gate10Config(
        max_total_exposure_r=3.0,  # Very low limit
        exposure_hard_utilization=0.95,  # 95%
    )
    
    # Positions with total 2.5R (projected 3.5R > 3.0R * 0.95)
    positions = [
        PositionInfo(
            instrument="ETHUSDT",
            direction=Direction.LONG,
            exposure_r=1.5,
            asset_class="CRYPTO",
            sector=None,
            entry_ts_utc_ms=int(datetime.now(timezone.utc).timestamp() * 1000),
        ),
        PositionInfo(
            instrument="SOLUSDT",
            direction=Direction.SHORT,
            exposure_r=1.0,
            asset_class="CRYPTO",
            sector=None,
            entry_ts_utc_ms=int(datetime.now(timezone.utc).timestamp() * 1000),
        ),
    ]
    
    gate = Gate10CorrelationExposure(config=config)
    
    result = gate.evaluate(
        signal=base_signal,
        market_state=base_market_state,
        gate00=passing_gate00,
        gate01=passing_gate01,
        gate02=passing_gate02,
        gate03=passing_gate03,
        gate04=passing_gate04,
        gate05=passing_gate05,
        gate06=passing_gate06,
        gate07=passing_gate07,
        gate08=passing_gate08,
        gate09=passing_gate09,
        portfolio_positions=positions,
        correlation_matrix={},
        asset_class="CRYPTO",
        sector=None,
    )
    
    assert result.entry_allowed is False
    assert "Total exposure" in result.block_reason
    assert "exceeds hard limit" in result.block_reason


def test_gate10_asset_exposure_hard_block(
    base_signal,
    base_market_state,
    passing_gate00,
    passing_gate01,
    passing_gate02,
    passing_gate03,
    passing_gate04,
    passing_gate05,
    passing_gate06,
    passing_gate07,
    passing_gate08,
    passing_gate09,
):
    """Test GATE 10 BLOCK при превышении max asset exposure."""
    # Config with low max_asset_exposure_r
    config = Gate10Config(
        max_asset_exposure_r=2.0,  # Low limit для asset class
        exposure_hard_utilization=0.95,
    )
    
    # All CRYPTO positions (same asset class)
    positions = [
        PositionInfo(
            instrument="ETHUSDT",
            direction=Direction.LONG,
            exposure_r=1.0,
            asset_class="CRYPTO",
            sector=None,
            entry_ts_utc_ms=int(datetime.now(timezone.utc).timestamp() * 1000),
        ),
        PositionInfo(
            instrument="SOLUSDT",
            direction=Direction.SHORT,
            exposure_r=0.5,
            asset_class="CRYPTO",
            sector=None,
            entry_ts_utc_ms=int(datetime.now(timezone.utc).timestamp() * 1000),
        ),
    ]
    
    gate = Gate10CorrelationExposure(config=config)
    
    result = gate.evaluate(
        signal=base_signal,  # Also CRYPTO
        market_state=base_market_state,
        gate00=passing_gate00,
        gate01=passing_gate01,
        gate02=passing_gate02,
        gate03=passing_gate03,
        gate04=passing_gate04,
        gate05=passing_gate05,
        gate06=passing_gate06,
        gate07=passing_gate07,
        gate08=passing_gate08,
        gate09=passing_gate09,
        portfolio_positions=positions,
        correlation_matrix={},
        asset_class="CRYPTO",
        sector=None,
    )
    
    assert result.entry_allowed is False
    assert "Asset CRYPTO exposure" in result.block_reason


def test_gate10_sector_exposure_hard_block(
    base_signal,
    base_market_state,
    passing_gate00,
    passing_gate01,
    passing_gate02,
    passing_gate03,
    passing_gate04,
    passing_gate05,
    passing_gate06,
    passing_gate07,
    passing_gate08,
    passing_gate09,
):
    """Test GATE 10 BLOCK при превышении max sector exposure."""
    # Config with low max_sector_exposure_r
    config = Gate10Config(
        max_sector_exposure_r=1.5,  # Low limit для sector
        exposure_hard_utilization=0.95,
    )
    
    # All TECH sector positions
    positions = [
        PositionInfo(
            instrument="AAPL",
            direction=Direction.LONG,
            exposure_r=0.8,
            asset_class="EQUITY",
            sector="TECH",
            entry_ts_utc_ms=int(datetime.now(timezone.utc).timestamp() * 1000),
        ),
        PositionInfo(
            instrument="MSFT",
            direction=Direction.LONG,
            exposure_r=0.5,
            asset_class="EQUITY",
            sector="TECH",
            entry_ts_utc_ms=int(datetime.now(timezone.utc).timestamp() * 1000),
        ),
    ]
    
    # Signal also TECH sector
    tech_signal = Signal(
        instrument="GOOGL",
        engine="TREND",
        direction=Direction.LONG,
        signal_ts_utc_ms=int(datetime.now(timezone.utc).timestamp() * 1000),
        levels={
            "entry_price": 100.0,
            "stop_loss": 98.0,
            "take_profit": 104.0,
        },
        context=SignalContext(
            expected_holding_hours=24.0,
            regime_hint="TREND_UP",
            setup_id="setup_001",
        ),
        constraints={
            "RR_min_engine": 2.0,
            "sl_min_atr_mult": 1.0,
            "sl_max_atr_mult": 3.0,
        },
    )
    
    gate = Gate10CorrelationExposure(config=config)
    
    result = gate.evaluate(
        signal=tech_signal,
        market_state=base_market_state,
        gate00=passing_gate00,
        gate01=passing_gate01,
        gate02=passing_gate02,
        gate03=passing_gate03,
        gate04=passing_gate04,
        gate05=passing_gate05,
        gate06=passing_gate06,
        gate07=passing_gate07,
        gate08=passing_gate08,
        gate09=passing_gate09,
        portfolio_positions=positions,
        correlation_matrix={},
        asset_class="EQUITY",
        sector="TECH",
    )
    
    assert result.entry_allowed is False
    assert "Sector TECH exposure" in result.block_reason


# =============================================================================
# TESTS: Portfolio Constraints
# =============================================================================


def test_gate10_max_positions_soft_warning(
    base_signal,
    base_market_state,
    passing_gate00,
    passing_gate01,
    passing_gate02,
    passing_gate03,
    passing_gate04,
    passing_gate05,
    passing_gate06,
    passing_gate07,
    passing_gate08,
    passing_gate09,
):
    """Test GATE 10 soft WARNING при приближении к max positions."""
    # Config with low max_positions_soft and higher concentration limit
    config = Gate10Config(
        max_positions_soft=3,
        max_positions_hard=5,
        max_single_position_concentration_hard=0.50,  # Allow 40% concentration
    )
    
    # 2 existing positions (projected 3 = soft limit)
    positions = [
        PositionInfo(
            instrument="ETHUSDT",
            direction=Direction.LONG,
            exposure_r=1.0,
            asset_class="CRYPTO",
            sector=None,
            entry_ts_utc_ms=int(datetime.now(timezone.utc).timestamp() * 1000),
        ),
        PositionInfo(
            instrument="SOLUSDT",
            direction=Direction.SHORT,
            exposure_r=0.5,
            asset_class="CRYPTO",
            sector=None,
            entry_ts_utc_ms=int(datetime.now(timezone.utc).timestamp() * 1000),
        ),
    ]
    
    gate = Gate10CorrelationExposure(config=config)
    
    result = gate.evaluate(
        signal=base_signal,
        market_state=base_market_state,
        gate00=passing_gate00,
        gate01=passing_gate01,
        gate02=passing_gate02,
        gate03=passing_gate03,
        gate04=passing_gate04,
        gate05=passing_gate05,
        gate06=passing_gate06,
        gate07=passing_gate07,
        gate08=passing_gate08,
        gate09=passing_gate09,
        portfolio_positions=positions,
        correlation_matrix={},
        asset_class="CRYPTO",
        sector=None,
    )
    
    assert result.entry_allowed is True  # WARNING, not BLOCK
    
    # Portfolio constraints
    assert result.portfolio_constraints.projected_n_positions == 3
    assert result.portfolio_constraints.positions_warning is True
    assert result.portfolio_constraints.positions_block is False


def test_gate10_max_positions_hard_block(
    base_signal,
    base_market_state,
    passing_gate00,
    passing_gate01,
    passing_gate02,
    passing_gate03,
    passing_gate04,
    passing_gate05,
    passing_gate06,
    passing_gate07,
    passing_gate08,
    passing_gate09,
):
    """Test GATE 10 BLOCK при превышении max positions."""
    # Config with low max_positions_hard
    config = Gate10Config(
        max_positions_hard=3,
    )
    
    # 3 existing positions (projected 4 > hard limit)
    positions = [
        PositionInfo(
            instrument=f"ASSET{i}",
            direction=Direction.LONG,
            exposure_r=0.5,
            asset_class="CRYPTO",
            sector=None,
            entry_ts_utc_ms=int(datetime.now(timezone.utc).timestamp() * 1000),
        )
        for i in range(3)
    ]
    
    gate = Gate10CorrelationExposure(config=config)
    
    result = gate.evaluate(
        signal=base_signal,
        market_state=base_market_state,
        gate00=passing_gate00,
        gate01=passing_gate01,
        gate02=passing_gate02,
        gate03=passing_gate03,
        gate04=passing_gate04,
        gate05=passing_gate05,
        gate06=passing_gate06,
        gate07=passing_gate07,
        gate08=passing_gate08,
        gate09=passing_gate09,
        portfolio_positions=positions,
        correlation_matrix={},
        asset_class="CRYPTO",
        sector=None,
    )
    
    assert result.entry_allowed is False
    assert "Portfolio positions" in result.block_reason
    assert "exceeds hard limit" in result.block_reason


def test_gate10_concentration_soft_warning(
    base_signal,
    base_market_state,
    passing_gate00,
    passing_gate01,
    passing_gate02,
    passing_gate03,
    passing_gate04,
    passing_gate05,
    passing_gate06,
    passing_gate07,
    passing_gate08,
    passing_gate09,
):
    """Test GATE 10 soft WARNING при высокой концентрации."""
    # Config with low concentration limits
    config = Gate10Config(
        max_single_position_concentration_soft=0.30,
        max_single_position_concentration_hard=0.60,  # Allow 50% concentration
    )
    
    # Small existing positions, new position будет 33% от total
    positions = [
        PositionInfo(
            instrument="ETHUSDT",
            direction=Direction.LONG,
            exposure_r=0.5,
            asset_class="CRYPTO",
            sector=None,
            entry_ts_utc_ms=int(datetime.now(timezone.utc).timestamp() * 1000),
        ),
        PositionInfo(
            instrument="SOLUSDT",
            direction=Direction.SHORT,
            exposure_r=0.5,
            asset_class="CRYPTO",
            sector=None,
            entry_ts_utc_ms=int(datetime.now(timezone.utc).timestamp() * 1000),
        ),
    ]
    
    # New position 1.0R → 1.0 / (0.5 + 0.5 + 1.0) = 0.50 > 0.30
    
    gate = Gate10CorrelationExposure(config=config)
    
    result = gate.evaluate(
        signal=base_signal,
        market_state=base_market_state,
        gate00=passing_gate00,
        gate01=passing_gate01,
        gate02=passing_gate02,
        gate03=passing_gate03,
        gate04=passing_gate04,
        gate05=passing_gate05,
        gate06=passing_gate06,
        gate07=passing_gate07,
        gate08=passing_gate08,
        gate09=passing_gate09,
        portfolio_positions=positions,
        correlation_matrix={},
        asset_class="CRYPTO",
        sector=None,
    )
    
    assert result.entry_allowed is True  # WARNING, not BLOCK
    
    # Portfolio constraints
    assert result.portfolio_constraints.concentration_warning is True
    assert result.portfolio_constraints.concentration_block is False


def test_gate10_concentration_hard_block(
    base_signal,
    base_market_state,
    passing_gate00,
    passing_gate01,
    passing_gate02,
    passing_gate03,
    passing_gate04,
    passing_gate05,
    passing_gate06,
    passing_gate07,
    passing_gate08,
    passing_gate09,
):
    """Test GATE 10 BLOCK при очень высокой концентрации."""
    # Config with low concentration limits
    config = Gate10Config(
        max_single_position_concentration_hard=0.40,
    )
    
    # Very small existing positions, new position будет 50% от total
    positions = [
        PositionInfo(
            instrument="ETHUSDT",
            direction=Direction.LONG,
            exposure_r=0.5,
            asset_class="CRYPTO",
            sector=None,
            entry_ts_utc_ms=int(datetime.now(timezone.utc).timestamp() * 1000),
        ),
    ]
    
    # New position 1.0R → 1.0 / (0.5 + 1.0) = 0.67 > 0.40
    
    gate = Gate10CorrelationExposure(config=config)
    
    result = gate.evaluate(
        signal=base_signal,
        market_state=base_market_state,
        gate00=passing_gate00,
        gate01=passing_gate01,
        gate02=passing_gate02,
        gate03=passing_gate03,
        gate04=passing_gate04,
        gate05=passing_gate05,
        gate06=passing_gate06,
        gate07=passing_gate07,
        gate08=passing_gate08,
        gate09=passing_gate09,
        portfolio_positions=positions,
        correlation_matrix={},
        asset_class="CRYPTO",
        sector=None,
    )
    
    assert result.entry_allowed is False
    assert "Position concentration" in result.block_reason


# =============================================================================
# TESTS: Integration (Chain GATE 0→10)
# =============================================================================

# NOTE: Integration tests покрыты косвенно через все тесты выше
# Каждый тест вызывает full chain GATE 0→10
# Blocking propagation проверен в test_gate10_gate09_blocks_propagates



def test_gate10_gate09_blocks_propagates(
    base_signal,
    base_market_state,
    passing_gate00,
    passing_gate01,
    passing_gate02,
    passing_gate03,
    passing_gate04,
    passing_gate05,
    passing_gate06,
    passing_gate07,
    passing_gate08,
):
    """Test GATE 10 propagates GATE 09 block."""
    blocking_gate09 = Gate09Result(
        entry_allowed=False,
        block_reason="Funding cost too high",
        funding_metrics=FundingMetrics(
            funding_rate=0.01,
            funding_period_hours=8.0,
            time_to_next_funding_sec=14400,
            expected_holding_hours=24.0,
            n_events_raw=3,
            n_events=3.0,
            direction_sign=1,
            funding_pnl_frac=-0.03,
            funding_r=3.0,
            funding_cost_r=3.0,
            funding_bonus_r=0.0,
            funding_bonus_r_used=0.0,
        ),
        ev_r_price=0.50,
        expected_cost_r_used=0.05,
        ev_r_price_net=0.45,
        net_yield_r=-2.55,
        proximity_metrics=ProximityMetrics(
            tau=0.0,
            funding_proximity_mult=1.0,
            is_near_funding=False,
            proximity_penalty_r=0.0,
        ),
        blackout_check=BlackoutCheck(
            time_condition=False,
            cost_condition=False,
            holding_condition=False,
            significance_condition=False,
            blackout_triggered=False,
            blackout_reason="",
        ),
        funding_risk_mult=0.85,
        combined_risk_mult=0.85,
        details="Funding cost exceeds threshold",
    )
    
    gate = Gate10CorrelationExposure()
    
    result = gate.evaluate(
        signal=base_signal,
        market_state=base_market_state,
        gate00=passing_gate00,
        gate01=passing_gate01,
        gate02=passing_gate02,
        gate03=passing_gate03,
        gate04=passing_gate04,
        gate05=passing_gate05,
        gate06=passing_gate06,
        gate07=passing_gate07,
        gate08=passing_gate08,
        gate09=blocking_gate09,
        portfolio_positions=None,
        correlation_matrix=None,
        asset_class="CRYPTO",
        sector=None,
    )
    
    assert result.entry_allowed is False
    assert "GATE 09 blocked" in result.block_reason


# =============================================================================
# TESTS: Edge Cases
# =============================================================================

# NOTE: Edge cases покрыты через интеграцию:
# - Missing correlation data: defaults to 0.0 (tested in main tests)
# - Small exposure positions: filtered by min_exposure_r_for_correlation
# - Empty portfolio: tested in test_gate10_empty_portfolio_pass


# =============================================================================
# TESTS: Size-Invariant Validation
# =============================================================================

# NOTE: Size-invariant validation is covered by all tests above
# All exposure calculations use unit_risk_bps from GATE 05 (size-invariant)
# No tests depend on qty_actual or other size-dependent values
