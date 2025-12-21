"""Tests for GATE 9: Funding Filter + Proximity + Blackout

ТЗ 3.3.2 строка 1026, 1054 (GATE 9: Funding фильтр + proximity + blackout)
ТЗ раздел 3.3.4: Funding фильтр (size-invariant R)

Test coverage:
- Funding events count calculation
- Funding cost/bonus в R units
- Net Yield calculation
- Proximity model (smooth transition)
- Blackout conditions (all conditions)
- Integration с GATE 0-8
- Edge cases
"""

import math
from datetime import datetime, timezone

import pytest

from src.core.domain.market_state import Derivatives, MarketState, Price, Volatility
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
    Gate09Config,
    Gate09FundingProximity,
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
    from src.core.domain.market_state import Correlations, DataQuality, Liquidity
    
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
            funding_rate_spot=0.0001,  # 0.01% (LONG платит)
            funding_period_hours=8.0,
            time_to_next_funding_sec=7200,  # 2 часа
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
    )


@pytest.fixture
def pass_gate00() -> Gate00Result:
    """GATE 0 PASS result."""
    return Gate00Result(
        entry_allowed=True,
        block_reason="",
        dqs_result=None,
        drp_transition=None,
        new_drp_state="NORMAL",
        new_warmup_bars_remaining=0,
        new_drp_flap_count=0,
        new_hibernate_until_ts_utc_ms=None,
        details="PASS",
    )


@pytest.fixture
def pass_gate01() -> Gate01Result:
    """GATE 1 PASS result."""
    return Gate01Result(
        entry_allowed=True,
        block_reason="",
        drp_state=DRPState.NORMAL,
        trading_mode=TradingMode.LIVE,
        manual_halt_new_entries=False,
        manual_halt_all_trading=False,
        is_shadow_mode=False,
        details="PASS",
    )


@pytest.fixture
def pass_gate02() -> Gate02Result:
    """GATE 2 PASS result."""
    return Gate02Result(
        entry_allowed=True,
        block_reason="",
        mrc_result=None,
        baseline_result=None,
        final_regime="TREND_UP",
        conflict_info=None,
        is_probe_mode=False,
        regime_risk_mult=1.0,
        details="PASS",
    )


@pytest.fixture
def pass_gate03() -> Gate03Result:
    """GATE 3 PASS result."""
    return Gate03Result(
        entry_allowed=True,
        block_reason="",
        engine_type="TREND",
        final_regime="TREND_UP",
        is_compatible=True,
        details="PASS",
    )


@pytest.fixture
def pass_gate04() -> Gate04Result:
    """GATE 4 PASS result."""
    return Gate04Result(
        entry_allowed=True,
        block_reason="",
        raw_rr=2.0,
        sl_distance_abs=1000.0,
        sl_distance_atr=1.0,
        rr_valid=True,
        sl_distance_valid=True,
        prices_valid=True,
        details="PASS",
    )


@pytest.fixture
def pass_gate05() -> Gate05Result:
    """GATE 5 PASS result."""
    return Gate05Result(
        entry_allowed=True,
        block_reason="",
        unit_risk_bps=200.0,  # 2% (50000 - 49000) / 50000
        unit_risk_allin_net=1020.0,  # После all-in costs
        entry_cost_bps=10.0,
        sl_exit_cost_bps=10.0,
        expected_cost_bps_preMLE=30.0,
        expected_cost_R_preMLE=0.15,
        entry_eff_allin=50010.0,
        tp_eff_allin=51990.0,
        sl_eff_allin=48990.0,
        details="PASS",
    )


@pytest.fixture
def pass_gate06() -> Gate06Result:
    """GATE 6 PASS result."""
    return Gate06Result(
        entry_allowed=True,
        block_reason="",
        mle_decision="NORMAL",
        ev_r_price=0.50,  # 0.5R expected value
        expected_cost_r_postmle=0.12,
        net_edge_r=0.38,  # 0.5 - 0.12
        p_success=0.60,
        p_fail=0.40,
        mu_success_r=2.0,
        mu_fail_r=-1.0,
        expected_cost_bps_postmle=24.0,
        tp_exit_cost_bps=4.5,
        risk_mult=1.0,
        details="PASS",
    )


@pytest.fixture
def pass_gate07() -> Gate07Result:
    """GATE 7 PASS result."""
    return Gate07Result(
        entry_allowed=True,
        block_reason="",
        liquidity_metrics=None,
        liquidity_multipliers=None,
        impact_bps_est=5.0,
        details="PASS",
    )


@pytest.fixture
def pass_gate08() -> Gate08Result:
    """GATE 8 PASS result."""
    return Gate08Result(
        entry_allowed=True,
        block_reason="",
        anomaly_metrics=None,
        drp_trigger=None,
        details="PASS",
    )


# =============================================================================
# TESTS: Funding events count
# =============================================================================


def test_funding_events_zero_horizon_too_short(
    base_signal,
    base_market_state,
    pass_gate00,
    pass_gate01,
    pass_gate02,
    pass_gate03,
    pass_gate04,
    pass_gate05,
    pass_gate06,
    pass_gate07,
    pass_gate08,
):
    """Тест: n_events=0 когда expected_holding < time_to_next_funding."""
    gate = Gate09FundingProximity()
    
    # Ожидаемое время удержания меньше времени до следующего funding
    signal = base_signal.model_copy(
        update={
            "context": base_signal.context.model_copy(
                update={"expected_holding_hours": 1.0}  # 1 час < 2 часа (time_to_funding)
            )
        }
    )
    
    result = gate.evaluate(
        signal=signal,
        market_state=base_market_state,
        gate00=pass_gate00,
        gate01=pass_gate01,
        gate02=pass_gate02,
        gate03=pass_gate03,
        gate04=pass_gate04,
        gate05=pass_gate05,
        gate06=pass_gate06,
        gate07=pass_gate07,
        gate08=pass_gate08,
    )
    
    assert result.entry_allowed is True
    assert result.funding_metrics.n_events_raw == 0
    assert result.funding_metrics.n_events == 0.0
    assert result.funding_metrics.funding_cost_r == 0.0


def test_funding_events_single_event(
    base_signal,
    base_market_state,
    pass_gate00,
    pass_gate01,
    pass_gate02,
    pass_gate03,
    pass_gate04,
    pass_gate05,
    pass_gate06,
    pass_gate07,
    pass_gate08,
):
    """Тест: n_events=1 когда holding едва покрывает первый funding."""
    gate = Gate09FundingProximity()
    
    # Ожидаемое время удержания = 3 часа
    # time_to_next = 2 часа
    # n_events = 1 + floor((3 - 2) / 8) = 1 + floor(0.125) = 1
    signal = base_signal.model_copy(
        update={
            "context": base_signal.context.model_copy(
                update={"expected_holding_hours": 3.0}
            )
        }
    )
    
    result = gate.evaluate(
        signal=signal,
        market_state=base_market_state,
        gate00=pass_gate00,
        gate01=pass_gate01,
        gate02=pass_gate02,
        gate03=pass_gate03,
        gate04=pass_gate04,
        gate05=pass_gate05,
        gate06=pass_gate06,
        gate07=pass_gate07,
        gate08=pass_gate08,
    )
    
    assert result.entry_allowed is True
    assert result.funding_metrics.n_events_raw == 1
    assert result.funding_metrics.n_events == 1.0


def test_funding_events_multiple_events(
    base_signal,
    base_market_state,
    pass_gate00,
    pass_gate01,
    pass_gate02,
    pass_gate03,
    pass_gate04,
    pass_gate05,
    pass_gate06,
    pass_gate07,
    pass_gate08,
):
    """Тест: n_events=3 для long holding period."""
    gate = Gate09FundingProximity()
    
    # Ожидаемое время удержания = 24 часа
    # time_to_next = 2 часа
    # n_events = 1 + floor((24 - 2) / 8) = 1 + floor(2.75) = 1 + 2 = 3
    signal = base_signal.model_copy(
        update={
            "context": base_signal.context.model_copy(
                update={"expected_holding_hours": 24.0}
            )
        }
    )
    
    result = gate.evaluate(
        signal=signal,
        market_state=base_market_state,
        gate00=pass_gate00,
        gate01=pass_gate01,
        gate02=pass_gate02,
        gate03=pass_gate03,
        gate04=pass_gate04,
        gate05=pass_gate05,
        gate06=pass_gate06,
        gate07=pass_gate07,
        gate08=pass_gate08,
    )
    
    assert result.entry_allowed is True
    assert result.funding_metrics.n_events_raw == 3
    assert result.funding_metrics.n_events == 3.0


# =============================================================================
# TESTS: Funding cost/bonus в R units
# =============================================================================


def test_funding_cost_long_pays(
    base_signal,
    base_market_state,
    pass_gate00,
    pass_gate01,
    pass_gate02,
    pass_gate03,
    pass_gate04,
    pass_gate05,
    pass_gate06,
    pass_gate07,
    pass_gate08,
):
    """Тест: LONG платит когда funding_rate > 0."""
    gate = Gate09FundingProximity()
    
    # funding_rate = 0.0001 (0.01%), LONG платит
    # n_events = 3
    # funding_pnl_frac = - (+1) * 0.0001 * 3 = -0.0003
    # funding_R = -0.0003 * 50000 / 1020 = -0.0147
    # funding_cost_R = max(0, -(-0.0147)) = 0.0147
    
    signal = base_signal.model_copy(
        update={
            "context": base_signal.context.model_copy(
                update={"expected_holding_hours": 24.0}
            )
        }
    )
    
    result = gate.evaluate(
        signal=signal,
        market_state=base_market_state,
        gate00=pass_gate00,
        gate01=pass_gate01,
        gate02=pass_gate02,
        gate03=pass_gate03,
        gate04=pass_gate04,
        gate05=pass_gate05,
        gate06=pass_gate06,
        gate07=pass_gate07,
        gate08=pass_gate08,
    )
    
    assert result.entry_allowed is True
    assert result.funding_metrics.direction_sign == 1  # LONG
    assert result.funding_metrics.funding_pnl_frac == pytest.approx(-0.0003, abs=1e-6)
    assert result.funding_metrics.funding_r < 0  # Negative (платим)
    assert result.funding_metrics.funding_cost_r > 0  # Cost
    assert result.funding_metrics.funding_bonus_r == 0.0  # No bonus


def test_funding_bonus_short_receives(
    base_signal,
    base_market_state,
    pass_gate00,
    pass_gate01,
    pass_gate02,
    pass_gate03,
    pass_gate04,
    pass_gate05,
    pass_gate06,
    pass_gate07,
    pass_gate08,
):
    """Тест: SHORT получает когда funding_rate > 0."""
    gate = Gate09FundingProximity()
    
    # funding_rate = 0.0001 (0.01%), SHORT получает
    # direction_sign = -1
    # n_events = 3
    # funding_pnl_frac = - (-1) * 0.0001 * 3 = +0.0003
    # funding_R = +0.0003 * 50000 / 1020 = +0.0147
    # funding_bonus_R = max(0, 0.0147) = 0.0147
    
    signal = base_signal.model_copy(
        update={
            "direction": Direction.SHORT,
            "context": base_signal.context.model_copy(
                update={"expected_holding_hours": 24.0}
            ),
        }
    )
    
    result = gate.evaluate(
        signal=signal,
        market_state=base_market_state,
        gate00=pass_gate00,
        gate01=pass_gate01,
        gate02=pass_gate02,
        gate03=pass_gate03,
        gate04=pass_gate04,
        gate05=pass_gate05,
        gate06=pass_gate06,
        gate07=pass_gate07,
        gate08=pass_gate08,
    )
    
    assert result.entry_allowed is True
    assert result.funding_metrics.direction_sign == -1  # SHORT
    assert result.funding_metrics.funding_pnl_frac == pytest.approx(0.0003, abs=1e-6)
    assert result.funding_metrics.funding_r > 0  # Positive (получаем)
    assert result.funding_metrics.funding_cost_r == 0.0  # No cost
    assert result.funding_metrics.funding_bonus_r > 0  # Bonus


def test_funding_negative_rate_long_receives(
    base_signal,
    base_market_state,
    pass_gate00,
    pass_gate01,
    pass_gate02,
    pass_gate03,
    pass_gate04,
    pass_gate05,
    pass_gate06,
    pass_gate07,
    pass_gate08,
):
    """Тест: LONG получает когда funding_rate < 0."""
    gate = Gate09FundingProximity()
    
    # funding_rate = -0.0001 (SHORT платит, LONG получает)
    # direction_sign = +1
    # n_events = 3
    # funding_pnl_frac = - (+1) * (-0.0001) * 3 = +0.0003
    # funding_R = +0.0003 * 50000 / 1020 = +0.0147
    
    market_state = base_market_state.model_copy(
        update={
            "derivatives": base_market_state.derivatives.model_copy(
                update={"funding_rate_spot": -0.0001}
            )
        }
    )
    
    signal = base_signal.model_copy(
        update={
            "context": base_signal.context.model_copy(
                update={"expected_holding_hours": 24.0}
            )
        }
    )
    
    result = gate.evaluate(
        signal=signal,
        market_state=market_state,
        gate00=pass_gate00,
        gate01=pass_gate01,
        gate02=pass_gate02,
        gate03=pass_gate03,
        gate04=pass_gate04,
        gate05=pass_gate05,
        gate06=pass_gate06,
        gate07=pass_gate07,
        gate08=pass_gate08,
    )
    
    assert result.entry_allowed is True
    assert result.funding_metrics.funding_r > 0  # Positive (получаем)
    assert result.funding_metrics.funding_cost_r == 0.0  # No cost
    assert result.funding_metrics.funding_bonus_r > 0  # Bonus


# =============================================================================
# TESTS: Hard blocks
# =============================================================================


def test_funding_cost_block_high_rate(
    base_signal,
    base_market_state,
    pass_gate00,
    pass_gate01,
    pass_gate02,
    pass_gate03,
    pass_gate04,
    pass_gate05,
    pass_gate06,
    pass_gate07,
    pass_gate08,
):
    """Тест: funding_cost_block при высоком funding rate."""
    config = Gate09Config(
        funding_cost_block_r=0.05  # Низкий порог для теста
    )
    gate = Gate09FundingProximity(config=config)
    
    # Очень высокий funding rate
    market_state = base_market_state.model_copy(
        update={
            "derivatives": base_market_state.derivatives.model_copy(
                update={"funding_rate_spot": 0.02}  # 2% за период (очень высокий)
            )
        }
    )
    
    signal = base_signal.model_copy(
        update={
            "context": base_signal.context.model_copy(
                update={"expected_holding_hours": 24.0}
            )
        }
    )
    
    result = gate.evaluate(
        signal=signal,
        market_state=market_state,
        gate00=pass_gate00,
        gate01=pass_gate01,
        gate02=pass_gate02,
        gate03=pass_gate03,
        gate04=pass_gate04,
        gate05=pass_gate05,
        gate06=pass_gate06,
        gate07=pass_gate07,
        gate08=pass_gate08,
    )
    
    assert result.entry_allowed is False
    assert result.block_reason == "funding_cost_block"
    assert result.funding_metrics.funding_cost_r >= config.funding_cost_block_r


def test_funding_net_yield_block_low_ev(
    base_signal,
    base_market_state,
    pass_gate00,
    pass_gate01,
    pass_gate02,
    pass_gate03,
    pass_gate04,
    pass_gate05,
    pass_gate06,
    pass_gate07,
    pass_gate08,
):
    """Тест: funding_net_yield_block при низком EV и умеренном funding cost."""
    config = Gate09Config(
        min_net_yield_r=0.30  # Высокий порог
    )
    gate = Gate09FundingProximity(config=config)
    
    # Низкий EV
    from dataclasses import replace
    gate06_low_ev = replace(
        pass_gate06,
        ev_r_price=0.20,  # Низкий EV
        net_edge_r=0.08,
    )
    
    # Умеренный funding rate
    market_state = base_market_state.model_copy(
        update={
            "derivatives": base_market_state.derivatives.model_copy(
                update={"funding_rate_spot": 0.001}  # 0.1% за период
            )
        }
    )
    
    signal = base_signal.model_copy(
        update={
            "context": base_signal.context.model_copy(
                update={"expected_holding_hours": 24.0}
            )
        }
    )
    
    result = gate.evaluate(
        signal=signal,
        market_state=market_state,
        gate00=pass_gate00,
        gate01=pass_gate01,
        gate02=pass_gate02,
        gate03=pass_gate03,
        gate04=pass_gate04,
        gate05=pass_gate05,
        gate06=gate06_low_ev,
        gate07=pass_gate07,
        gate08=pass_gate08,
    )
    
    assert result.entry_allowed is False
    assert result.block_reason == "funding_net_yield_block"
    assert result.net_yield_r < config.min_net_yield_r


def test_funding_unit_risk_too_small_block(
    base_signal,
    base_market_state,
    pass_gate00,
    pass_gate01,
    pass_gate02,
    pass_gate03,
    pass_gate04,
    pass_gate05,
    pass_gate06,
    pass_gate07,
    pass_gate08,
):
    """Тест: funding_unit_risk_too_small_block при очень малом unit_risk."""
    config = Gate09Config(
        unit_risk_min_for_funding=10.0  # Высокий порог для теста
    )
    gate = Gate09FundingProximity(config=config)
    
    # Очень малый unit_risk
    from dataclasses import replace
    gate05_small_risk = replace(
        pass_gate05,
        unit_risk_allin_net=5.0,  # < 10.0
    )
    
    result = gate.evaluate(
        signal=base_signal,
        market_state=base_market_state,
        gate00=pass_gate00,
        gate01=pass_gate01,
        gate02=pass_gate02,
        gate03=pass_gate03,
        gate04=pass_gate04,
        gate05=gate05_small_risk,
        gate06=pass_gate06,
        gate07=pass_gate07,
        gate08=pass_gate08,
    )
    
    assert result.entry_allowed is False
    assert result.block_reason == "funding_unit_risk_too_small_block"


# =============================================================================
# TESTS: Proximity model
# =============================================================================


def test_proximity_far_from_funding(
    base_signal,
    base_market_state,
    pass_gate00,
    pass_gate01,
    pass_gate02,
    pass_gate03,
    pass_gate04,
    pass_gate05,
    pass_gate06,
    pass_gate07,
    pass_gate08,
):
    """Тест: proximity_mult = 1.0 когда далеко от funding."""
    gate = Gate09FundingProximity()
    
    # time_to_next = 7200 секунд (2 часа) > soft_sec (1800 секунд)
    # tau = 0 → proximity_mult = 1.0
    
    signal = base_signal.model_copy(
        update={
            "context": base_signal.context.model_copy(
                update={"expected_holding_hours": 24.0}
            )
        }
    )
    
    result = gate.evaluate(
        signal=signal,
        market_state=base_market_state,
        gate00=pass_gate00,
        gate01=pass_gate01,
        gate02=pass_gate02,
        gate03=pass_gate03,
        gate04=pass_gate04,
        gate05=pass_gate05,
        gate06=pass_gate06,
        gate07=pass_gate07,
        gate08=pass_gate08,
    )
    
    assert result.entry_allowed is True
    assert result.proximity_metrics.tau == 0.0
    assert result.proximity_metrics.funding_proximity_mult == pytest.approx(1.0, abs=1e-6)
    assert result.proximity_metrics.is_near_funding is False


def test_proximity_near_funding_soft(
    base_signal,
    base_market_state,
    pass_gate00,
    pass_gate01,
    pass_gate02,
    pass_gate03,
    pass_gate04,
    pass_gate05,
    pass_gate06,
    pass_gate07,
    pass_gate08,
):
    """Тест: proximity penalty при приближении к funding (soft boundary)."""
    gate = Gate09FundingProximity()
    
    # time_to_next = 1000 секунд (между soft=1800 и hard=300)
    # tau = (1800 - 1000) / (1800 - 300) = 800 / 1500 = 0.533
    # proximity_mult = 1 - (1 - 0.80) * (0.533^2) = 1 - 0.20 * 0.284 = 0.943
    
    market_state = base_market_state.model_copy(
        update={
            "derivatives": base_market_state.derivatives.model_copy(
                update={"time_to_next_funding_sec": 1000}
            )
        }
    )
    
    signal = base_signal.model_copy(
        update={
            "context": base_signal.context.model_copy(
                update={"expected_holding_hours": 24.0}
            )
        }
    )
    
    result = gate.evaluate(
        signal=signal,
        market_state=market_state,
        gate00=pass_gate00,
        gate01=pass_gate01,
        gate02=pass_gate02,
        gate03=pass_gate03,
        gate04=pass_gate04,
        gate05=pass_gate05,
        gate06=pass_gate06,
        gate07=pass_gate07,
        gate08=pass_gate08,
    )
    
    assert result.entry_allowed is True
    assert result.proximity_metrics.tau == pytest.approx(0.533, abs=0.01)
    assert 0.90 < result.proximity_metrics.funding_proximity_mult < 1.0
    assert result.proximity_metrics.is_near_funding is True


def test_proximity_very_near_funding_hard(
    base_signal,
    base_market_state,
    pass_gate00,
    pass_gate01,
    pass_gate02,
    pass_gate03,
    pass_gate04,
    pass_gate05,
    pass_gate06,
    pass_gate07,
    pass_gate08,
):
    """Тест: maximum proximity penalty при очень близком funding (hard boundary)."""
    gate = Gate09FundingProximity()
    
    # time_to_next = 100 секунд < hard=300
    # tau = (1800 - 100) / (1800 - 300) = 1700 / 1500 = 1.133 → clip to 1.0
    # proximity_mult = 1 - (1 - 0.80) * (1.0^2) = 1 - 0.20 = 0.80
    
    market_state = base_market_state.model_copy(
        update={
            "derivatives": base_market_state.derivatives.model_copy(
                update={"time_to_next_funding_sec": 100}
            )
        }
    )
    
    signal = base_signal.model_copy(
        update={
            "context": base_signal.context.model_copy(
                update={"expected_holding_hours": 24.0}
            )
        }
    )
    
    result = gate.evaluate(
        signal=signal,
        market_state=market_state,
        gate00=pass_gate00,
        gate01=pass_gate01,
        gate02=pass_gate02,
        gate03=pass_gate03,
        gate04=pass_gate04,
        gate05=pass_gate05,
        gate06=pass_gate06,
        gate07=pass_gate07,
        gate08=pass_gate08,
    )
    
    assert result.entry_allowed is True
    assert result.proximity_metrics.tau == pytest.approx(1.0, abs=0.01)
    assert result.proximity_metrics.funding_proximity_mult == pytest.approx(0.80, abs=0.01)
    assert result.proximity_metrics.is_near_funding is True


# =============================================================================
# TESTS: Blackout conditions
# =============================================================================


def test_blackout_all_conditions_met(
    base_signal,
    base_market_state,
    pass_gate00,
    pass_gate01,
    pass_gate02,
    pass_gate03,
    pass_gate04,
    pass_gate05,
    pass_gate06,
    pass_gate07,
    pass_gate08,
):
    """Тест: blackout triggered когда все условия выполнены."""
    config = Gate09Config(
        funding_blackout_minutes=10,  # 600 секунд
        funding_blackout_max_holding_hours=12.0,
        funding_blackout_cost_share_threshold=0.10,  # Низкий порог для теста
    )
    gate = Gate09FundingProximity(config=config)
    
    # 1. Time condition: time_to_next = 300 секунд < 10*60+2 = 602
    # 2. Cost condition: funding_cost_R > 0
    # 3. Holding condition: expected_holding = 8 часов < 12 часов
    # 4. Significance: cost_share >= 0.10
    
    market_state = base_market_state.model_copy(
        update={
            "derivatives": base_market_state.derivatives.model_copy(
                update={
                    "time_to_next_funding_sec": 300,
                    "funding_rate_spot": 0.005,  # Высокий rate для cost > 0
                }
            )
        }
    )
    
    signal = base_signal.model_copy(
        update={
            "context": base_signal.context.model_copy(
                update={"expected_holding_hours": 8.0}
            )
        }
    )
    
    result = gate.evaluate(
        signal=signal,
        market_state=market_state,
        gate00=pass_gate00,
        gate01=pass_gate01,
        gate02=pass_gate02,
        gate03=pass_gate03,
        gate04=pass_gate04,
        gate05=pass_gate05,
        gate06=pass_gate06,
        gate07=pass_gate07,
        gate08=pass_gate08,
    )
    
    assert result.entry_allowed is False
    assert result.block_reason == "funding_blackout_block"
    assert result.blackout_check.blackout_triggered is True
    assert result.blackout_check.time_condition is True
    assert result.blackout_check.cost_condition is True
    assert result.blackout_check.holding_condition is True
    assert result.blackout_check.significance_condition is True


def test_blackout_time_condition_not_met(
    base_signal,
    base_market_state,
    pass_gate00,
    pass_gate01,
    pass_gate02,
    pass_gate03,
    pass_gate04,
    pass_gate05,
    pass_gate06,
    pass_gate07,
    pass_gate08,
):
    """Тест: blackout НЕ triggered когда time condition не выполнено."""
    config = Gate09Config(
        funding_blackout_minutes=10,
    )
    gate = Gate09FundingProximity(config=config)
    
    # time_to_next = 1000 секунд > blackout_window (602 секунды)
    market_state = base_market_state.model_copy(
        update={
            "derivatives": base_market_state.derivatives.model_copy(
                update={"time_to_next_funding_sec": 1000}
            )
        }
    )
    
    signal = base_signal.model_copy(
        update={
            "context": base_signal.context.model_copy(
                update={"expected_holding_hours": 8.0}
            )
        }
    )
    
    result = gate.evaluate(
        signal=signal,
        market_state=market_state,
        gate00=pass_gate00,
        gate01=pass_gate01,
        gate02=pass_gate02,
        gate03=pass_gate03,
        gate04=pass_gate04,
        gate05=pass_gate05,
        gate06=pass_gate06,
        gate07=pass_gate07,
        gate08=pass_gate08,
    )
    
    assert result.entry_allowed is True  # PASS
    assert result.blackout_check.blackout_triggered is False
    assert result.blackout_check.time_condition is False


def test_blackout_holding_condition_not_met(
    base_signal,
    base_market_state,
    pass_gate00,
    pass_gate01,
    pass_gate02,
    pass_gate03,
    pass_gate04,
    pass_gate05,
    pass_gate06,
    pass_gate07,
    pass_gate08,
):
    """Тест: blackout НЕ triggered когда holding слишком длинный."""
    config = Gate09Config(
        funding_blackout_minutes=10,
        funding_blackout_max_holding_hours=12.0,
    )
    gate = Gate09FundingProximity(config=config)
    
    # expected_holding = 48 часов > max_holding (12 часов)
    market_state = base_market_state.model_copy(
        update={
            "derivatives": base_market_state.derivatives.model_copy(
                update={"time_to_next_funding_sec": 300}
            )
        }
    )
    
    signal = base_signal.model_copy(
        update={
            "context": base_signal.context.model_copy(
                update={"expected_holding_hours": 48.0}
            )
        }
    )
    
    result = gate.evaluate(
        signal=signal,
        market_state=market_state,
        gate00=pass_gate00,
        gate01=pass_gate01,
        gate02=pass_gate02,
        gate03=pass_gate03,
        gate04=pass_gate04,
        gate05=pass_gate05,
        gate06=pass_gate06,
        gate07=pass_gate07,
        gate08=pass_gate08,
    )
    
    assert result.entry_allowed is True  # PASS
    assert result.blackout_check.blackout_triggered is False
    assert result.blackout_check.holding_condition is False


def test_blackout_significance_condition_not_met(
    base_signal,
    base_market_state,
    pass_gate00,
    pass_gate01,
    pass_gate02,
    pass_gate03,
    pass_gate04,
    pass_gate05,
    pass_gate06,
    pass_gate07,
    pass_gate08,
):
    """Тест: blackout НЕ triggered когда funding cost незначителен."""
    config = Gate09Config(
        funding_blackout_minutes=10,
        funding_blackout_cost_share_threshold=0.40,  # Высокий порог
    )
    gate = Gate09FundingProximity(config=config)
    
    # funding_cost_R очень мал относительно EV_R_price
    # cost_share < threshold
    market_state = base_market_state.model_copy(
        update={
            "derivatives": base_market_state.derivatives.model_copy(
                update={
                    "time_to_next_funding_sec": 300,
                    "funding_rate_spot": 0.00001,  # Очень низкий rate
                }
            )
        }
    )
    
    signal = base_signal.model_copy(
        update={
            "context": base_signal.context.model_copy(
                update={"expected_holding_hours": 8.0}
            )
        }
    )
    
    result = gate.evaluate(
        signal=signal,
        market_state=market_state,
        gate00=pass_gate00,
        gate01=pass_gate01,
        gate02=pass_gate02,
        gate03=pass_gate03,
        gate04=pass_gate04,
        gate05=pass_gate05,
        gate06=pass_gate06,
        gate07=pass_gate07,
        gate08=pass_gate08,
    )
    
    assert result.entry_allowed is True  # PASS
    assert result.blackout_check.blackout_triggered is False
    assert result.blackout_check.significance_condition is False


# =============================================================================
# TESTS: Integration с GATE 0-8
# =============================================================================


def test_integration_gate00_blocked(
    base_signal,
    base_market_state,
    pass_gate01,
    pass_gate02,
    pass_gate03,
    pass_gate04,
    pass_gate05,
    pass_gate06,
    pass_gate07,
    pass_gate08,
):
    """Тест: GATE 0 блокировка propagates через GATE 9."""
    gate = Gate09FundingProximity()
    
    gate00_blocked = Gate00Result(
        entry_allowed=False,
        block_reason="dqs_too_low",
        dqs_result=None,
        drp_transition=None,
        new_drp_state="NORMAL",
        new_warmup_bars_remaining=0,
        new_drp_flap_count=0,
        new_hibernate_until_ts_utc_ms=None,
        details="BLOCKED",
    )
    
    result = gate.evaluate(
        signal=base_signal,
        market_state=base_market_state,
        gate00=gate00_blocked,
        gate01=pass_gate01,
        gate02=pass_gate02,
        gate03=pass_gate03,
        gate04=pass_gate04,
        gate05=pass_gate05,
        gate06=pass_gate06,
        gate07=pass_gate07,
        gate08=pass_gate08,
    )
    
    assert result.entry_allowed is False
    assert result.block_reason == "gate00_blocked"


def test_integration_full_chain_pass(
    base_signal,
    base_market_state,
    pass_gate00,
    pass_gate01,
    pass_gate02,
    pass_gate03,
    pass_gate04,
    pass_gate05,
    pass_gate06,
    pass_gate07,
    pass_gate08,
):
    """Тест: Full chain GATE 0→9 PASS."""
    gate = Gate09FundingProximity()
    
    # Low funding rate, moderate holding
    market_state = base_market_state.model_copy(
        update={
            "derivatives": base_market_state.derivatives.model_copy(
                update={
                    "funding_rate_spot": 0.00005,  # Очень низкий
                    "time_to_next_funding_sec": 3600,  # 1 час
                }
            )
        }
    )
    
    signal = base_signal.model_copy(
        update={
            "context": base_signal.context.model_copy(
                update={"expected_holding_hours": 12.0}
            )
        }
    )
    
    result = gate.evaluate(
        signal=signal,
        market_state=market_state,
        gate00=pass_gate00,
        gate01=pass_gate01,
        gate02=pass_gate02,
        gate03=pass_gate03,
        gate04=pass_gate04,
        gate05=pass_gate05,
        gate06=pass_gate06,
        gate07=pass_gate07,
        gate08=pass_gate08,
    )
    
    assert result.entry_allowed is True
    assert result.block_reason == ""
    assert result.net_yield_r > 0


# =============================================================================
# TESTS: Edge cases
# =============================================================================


def test_edge_zero_funding_rate(
    base_signal,
    base_market_state,
    pass_gate00,
    pass_gate01,
    pass_gate02,
    pass_gate03,
    pass_gate04,
    pass_gate05,
    pass_gate06,
    pass_gate07,
    pass_gate08,
):
    """Тест: funding_rate = 0 → no cost, no bonus."""
    gate = Gate09FundingProximity()
    
    market_state = base_market_state.model_copy(
        update={
            "derivatives": base_market_state.derivatives.model_copy(
                update={"funding_rate_spot": 0.0}
            )
        }
    )
    
    signal = base_signal.model_copy(
        update={
            "context": base_signal.context.model_copy(
                update={"expected_holding_hours": 24.0}
            )
        }
    )
    
    result = gate.evaluate(
        signal=signal,
        market_state=market_state,
        gate00=pass_gate00,
        gate01=pass_gate01,
        gate02=pass_gate02,
        gate03=pass_gate03,
        gate04=pass_gate04,
        gate05=pass_gate05,
        gate06=pass_gate06,
        gate07=pass_gate07,
        gate08=pass_gate08,
    )
    
    assert result.entry_allowed is True
    assert result.funding_metrics.funding_r == 0.0
    assert result.funding_metrics.funding_cost_r == 0.0
    assert result.funding_metrics.funding_bonus_r == 0.0


def test_edge_exact_blackout_window_boundary(
    base_signal,
    base_market_state,
    pass_gate00,
    pass_gate01,
    pass_gate02,
    pass_gate03,
    pass_gate04,
    pass_gate05,
    pass_gate06,
    pass_gate07,
    pass_gate08,
):
    """Тест: time_to_next ровно на границе blackout window."""
    config = Gate09Config(
        funding_blackout_minutes=10,
        funding_event_inclusion_epsilon_sec=2,
        funding_blackout_cost_share_threshold=0.10,
    )
    gate = Gate09FundingProximity(config=config)
    
    # time_to_next = 602 секунды (ровно blackout_window)
    # Условие: <= 602, так что должно быть True
    market_state = base_market_state.model_copy(
        update={
            "derivatives": base_market_state.derivatives.model_copy(
                update={
                    "time_to_next_funding_sec": 602,
                    "funding_rate_spot": 0.005,
                }
            )
        }
    )
    
    signal = base_signal.model_copy(
        update={
            "context": base_signal.context.model_copy(
                update={"expected_holding_hours": 8.0}
            )
        }
    )
    
    result = gate.evaluate(
        signal=signal,
        market_state=market_state,
        gate00=pass_gate00,
        gate01=pass_gate01,
        gate02=pass_gate02,
        gate03=pass_gate03,
        gate04=pass_gate04,
        gate05=pass_gate05,
        gate06=pass_gate06,
        gate07=pass_gate07,
        gate08=pass_gate08,
    )
    
    # time_condition должно быть True
    assert result.blackout_check.time_condition is True


def test_funding_bonus_credit_allowed_policy(
    base_signal,
    base_market_state,
    pass_gate00,
    pass_gate01,
    pass_gate02,
    pass_gate03,
    pass_gate04,
    pass_gate05,
    pass_gate06,
    pass_gate07,
    pass_gate08,
):
    """Тест: funding_credit_allowed=True учитывает funding_bonus_R."""
    config = Gate09Config(
        funding_credit_allowed=True  # Учитываем bonus
    )
    gate = Gate09FundingProximity(config=config)
    
    # SHORT получает bonus
    market_state = base_market_state.model_copy(
        update={
            "derivatives": base_market_state.derivatives.model_copy(
                update={"funding_rate_spot": 0.0001}  # LONG платит, SHORT получает
            )
        }
    )
    
    signal = base_signal.model_copy(
        update={
            "direction": Direction.SHORT,
            "context": base_signal.context.model_copy(
                update={"expected_holding_hours": 24.0}
            ),
        }
    )
    
    result = gate.evaluate(
        signal=signal,
        market_state=market_state,
        gate00=pass_gate00,
        gate01=pass_gate01,
        gate02=pass_gate02,
        gate03=pass_gate03,
        gate04=pass_gate04,
        gate05=pass_gate05,
        gate06=pass_gate06,
        gate07=pass_gate07,
        gate08=pass_gate08,
    )
    
    assert result.entry_allowed is True
    assert result.funding_metrics.funding_bonus_r > 0
    # Net_Yield должен быть выше за счёт bonus
    assert result.net_yield_r > result.ev_r_price_net
