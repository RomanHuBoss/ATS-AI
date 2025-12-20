"""
Tests for Pydantic State Models

ТЗ: Appendix B (обязательные state модели)

Комплексное тестирование Pydantic V2 моделей:
- MarketState (Appendix B.1)
- PortfolioState (Appendix B.2)
- MLEOutput (Appendix B.4)

Покрывает:
- Создание и валидация моделей
- JSON сериализация/десериализация
- JSON Schema compliance
- Enum валидация
- Nested models
- Immutability (frozen=True)
- Интеграция с существующими моделями
"""

import pytest
from pydantic import ValidationError

from src.core.contracts import (
    validate_market_state,
    validate_mle_output,
    validate_portfolio_state,
)
from src.core.domain import (
    Correlations,
    DRPState,
    DataQuality,
    Derivatives,
    Equity,
    Liquidity,
    MLEDecision,
    MLEOutput,
    MLOpsState,
    MarketState,
    PortfolioState,
    Position,
    PositionDirection,
    Price,
    Risk,
    States,
    TradingMode,
    Volatility,
)


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def valid_price_data():
    """Валидные ценовые данные."""
    return {
        "last": 42000.50,
        "mid": 42000.25,
        "bid": 42000.00,
        "ask": 42000.50,
        "tick_size": 0.50,
    }


@pytest.fixture
def valid_volatility_data():
    """Валидные данные волатильности."""
    return {
        "atr": 850.0,
        "atr_z_short": 0.5,
        "atr_z_long": 0.3,
        "atr_window_short": 14,
        "hv30": 0.65,
        "hv30_z": 0.2,
    }


@pytest.fixture
def valid_liquidity_data():
    """Валидные данные ликвидности."""
    return {
        "spread_bps": 1.2,
        "depth_bid_usd": 500000.0,
        "depth_ask_usd": 480000.0,
        "impact_bps_est": 2.5,
        "orderbook_staleness_ms": 50,
        "orderbook_last_update_id": 999999,
        "orderbook_update_id_age_ms": 45,
    }


@pytest.fixture
def valid_derivatives_data():
    """Валидные данные деривативов."""
    return {
        "funding_rate_spot": 0.0001,
        "funding_rate_forecast": 0.00012,
        "funding_period_hours": 8.0,
        "time_to_next_funding_sec": 14400,
        "oi": 1500000000.0,
        "basis_value": 5.0,
        "basis_z": 0.8,
        "basis_vol_z": 0.6,
        "adl_rank_quantile": 0.25,
    }


@pytest.fixture
def valid_correlations_data():
    """Валидные данные корреляций."""
    return {
        "tail_metrics_reliable": True,
        "tail_reliability_score": 0.85,
        "tail_corr_to_btc": 0.92,
        "stress_beta_to_btc": 1.15,
        "lambda_tail_dep": 0.45,
        "corr_matrix_snapshot_id": 5000,
        "corr_matrix_age_sec": 300,
        "gamma_s": 0.35,
    }


@pytest.fixture
def valid_data_quality_data():
    """Валидные данные качества."""
    return {
        "suspected_data_glitch": False,
        "stale_book_glitch": False,
        "data_quality_score": 0.95,
        "dqs_critical": 0.98,
        "dqs_noncritical": 0.92,
        "dqs_sources": 0.96,
        "dqs_mult": 0.95,
        "staleness_price_ms": 10,
        "staleness_liquidity_ms": 20,
        "staleness_derivatives_sec": 5,
        "cross_exchange_dev_bps": 0.5,
        "oracle_dev_frac": 0.001,
        "oracle_staleness_ms": 15,
        "price_sources_used": ["exchange_ws", "exchange_rest"],
        "toxic_flow_suspected": False,
        "execution_price_improvement_bps": 0.1,
    }


@pytest.fixture
def valid_market_state_data(
    valid_price_data,
    valid_volatility_data,
    valid_liquidity_data,
    valid_derivatives_data,
    valid_correlations_data,
    valid_data_quality_data,
):
    """Валидный MarketState для тестирования."""
    return {
        "schema_version": "7",
        "snapshot_id": 12345,
        "ts_utc_ms": 1700000000000,
        "market_data_id": 67890,
        "data_gap_sec": 0,
        "is_gap_contaminated": False,
        "instrument": "BTCUSDT",
        "timeframe": "H1",
        "price": valid_price_data,
        "volatility": valid_volatility_data,
        "liquidity": valid_liquidity_data,
        "derivatives": valid_derivatives_data,
        "correlations": valid_correlations_data,
        "data_quality": valid_data_quality_data,
    }


@pytest.fixture
def valid_position():
    """Валидная Position для использования в PortfolioState."""
    return Position(
        instrument="BTCUSDT",
        cluster_id="btc_cluster",
        direction=PositionDirection.LONG,
        qty=0.1,
        entry_price=42000.0,
        entry_eff_allin=42010.0,
        sl_eff_allin=41000.0,
        risk_amount_usd=100.0,
        risk_pct_equity=0.5,
        notional_usd=4200.0,
        unrealized_pnl_usd=50.0,
        funding_pnl_usd=-2.0,
        opened_ts_utc_ms=1700000000000,
    )


@pytest.fixture
def valid_portfolio_state_data(valid_position):
    """Валидный PortfolioState для тестирования."""
    return {
        "schema_version": "7",
        "snapshot_id": 12345,
        "portfolio_id": 100,
        "ts_utc_ms": 1700000000000,
        "equity": {
            "equity_usd": 10000.0,
            "peak_equity_usd": 10500.0,
            "drawdown_pct": 0.0476,  # 4.76% as fraction
            "drawdown_smoothed_pct": 0.045,  # 4.5% as fraction
        },
        "risk": {
            "current_portfolio_risk_pct": 1.5,
            "current_cluster_risk_pct": 0.8,
            "reserved_portfolio_risk_pct": 0.5,
            "reserved_cluster_risk_pct": 0.3,
            "current_sum_abs_risk_pct": 2.0,
            "reserved_sum_abs_risk_pct": 0.6,
            "reserved_heat_upper_bound_pct": 3.0,
            "adjusted_heat_base_pct": 1.8,
            "adjusted_heat_blend_pct": 1.9,
            "adjusted_heat_worst_pct": 2.1,
            "heat_uni_abs_pct": 1.7,
            "max_portfolio_risk_pct": 5.0,
            "max_sum_abs_risk_pct": 8.0,
            "cluster_risk_limit_pct": 3.0,
            "max_adjusted_heat_pct": 4.0,
            "max_trade_risk_cap_pct": 1.5,
        },
        "states": {
            "DRP_state": "NORMAL",
            "MLOps_state": "OK",
            "trading_mode": "LIVE",
            "warmup_bars_remaining": 0,
            "drp_flap_count": 0,
            "hibernate_until_ts_utc_ms": None,
        },
        "positions": [valid_position.model_dump()],
    }


@pytest.fixture
def valid_mle_output_data():
    """Валидный MLEOutput для тестирования."""
    return {
        "schema_version": "5",
        "model_id": "mle_v1.2.3",
        "artifact_sha256": "a" * 64,
        "feature_schema_version": "1.0",
        "calibration_version": "2.1",
        "decision": "NORMAL",
        "risk_mult": 1.0,
        "EV_R_price": 0.25,
        "p_fail": 0.35,
        "p_neutral": 0.15,
        "p_success": 0.50,
        "p_stopout_noise": 0.10,
        "expected_cost_R_preMLE": 0.08,
        "expected_cost_R_postMLE": 0.06,
    }


# =============================================================================
# TESTS: MarketState
# =============================================================================


def test_market_state_creation(valid_market_state_data):
    """Тест создания MarketState с валидными данными."""
    market_state = MarketState(**valid_market_state_data)

    assert market_state.schema_version == "7"
    assert market_state.snapshot_id == 12345
    assert market_state.instrument == "BTCUSDT"
    assert market_state.price.last == 42000.50
    assert market_state.volatility.atr == 850.0
    assert market_state.liquidity.spread_bps == 1.2


def test_market_state_json_serialization(valid_market_state_data):
    """Тест JSON сериализации MarketState."""
    market_state = MarketState(**valid_market_state_data)
    json_data = market_state.model_dump()

    # Проверка, что JSON соответствует JSON Schema
    validate_market_state(json_data)  # Должно пройти без исключений


def test_market_state_json_deserialization(valid_market_state_data):
    """Тест JSON десериализации MarketState."""
    market_state = MarketState(**valid_market_state_data)
    json_data = market_state.model_dump()

    # Десериализация из JSON
    restored = MarketState(**json_data)

    assert restored.snapshot_id == market_state.snapshot_id
    assert restored.price.last == market_state.price.last


def test_market_state_immutability(valid_market_state_data):
    """Тест immutability MarketState (frozen=True)."""
    market_state = MarketState(**valid_market_state_data)

    with pytest.raises(ValidationError, match="frozen"):
        market_state.snapshot_id = 99999  # type: ignore


def test_market_state_nested_model_validation(valid_market_state_data):
    """Тест валидации nested моделей MarketState."""
    # Невалидный Price (negative last)
    invalid_data = valid_market_state_data.copy()
    invalid_data["price"] = {"last": -100.0, "mid": 100.0, "bid": 99.0, "ask": 101.0, "tick_size": 0.1}

    with pytest.raises(ValidationError, match="greater than 0"):
        MarketState(**invalid_data)


def test_market_state_schema_version_constraint(valid_market_state_data):
    """Тест constraint schema_version (должна быть '7')."""
    invalid_data = valid_market_state_data.copy()
    invalid_data["schema_version"] = "8"

    with pytest.raises(ValidationError, match="String should match pattern"):
        MarketState(**invalid_data)


def test_market_state_optional_fields(valid_market_state_data):
    """Тест optional полей MarketState."""
    # Убираем optional поля
    data = valid_market_state_data.copy()
    data["volatility"]["hv30"] = None
    data["volatility"]["hv30_z"] = None

    market_state = MarketState(**data)
    assert market_state.volatility.hv30 is None
    assert market_state.volatility.hv30_z is None


# =============================================================================
# TESTS: PortfolioState
# =============================================================================


def test_portfolio_state_creation(valid_portfolio_state_data):
    """Тест создания PortfolioState с валидными данными."""
    portfolio_state = PortfolioState(**valid_portfolio_state_data)

    assert portfolio_state.schema_version == "7"
    assert portfolio_state.snapshot_id == 12345
    assert portfolio_state.portfolio_id == 100
    assert portfolio_state.equity.equity_usd == 10000.0
    assert portfolio_state.risk.current_portfolio_risk_pct == 1.5
    assert portfolio_state.states.DRP_state == DRPState.NORMAL
    assert len(portfolio_state.positions) == 1


def test_portfolio_state_json_serialization(valid_portfolio_state_data):
    """Тест JSON сериализации PortfolioState."""
    portfolio_state = PortfolioState(**valid_portfolio_state_data)
    json_data = portfolio_state.model_dump()

    # Проверка, что JSON соответствует JSON Schema
    validate_portfolio_state(json_data)  # Должно пройти без исключений


def test_portfolio_state_json_deserialization(valid_portfolio_state_data):
    """Тест JSON десериализации PortfolioState."""
    portfolio_state = PortfolioState(**valid_portfolio_state_data)
    json_data = portfolio_state.model_dump()

    # Десериализация из JSON
    restored = PortfolioState(**json_data)

    assert restored.portfolio_id == portfolio_state.portfolio_id
    assert restored.equity.equity_usd == portfolio_state.equity.equity_usd
    assert len(restored.positions) == len(portfolio_state.positions)


def test_portfolio_state_immutability(valid_portfolio_state_data):
    """Тест immutability PortfolioState (frozen=True)."""
    portfolio_state = PortfolioState(**valid_portfolio_state_data)

    with pytest.raises(ValidationError, match="frozen"):
        portfolio_state.portfolio_id = 99999  # type: ignore


def test_portfolio_state_drp_state_enum():
    """Тест DRPState enum валидации."""
    # Валидные значения
    assert DRPState.NORMAL.value == "NORMAL"
    assert DRPState.DEGRADED.value == "DEGRADED"
    assert DRPState.DEFENSIVE.value == "DEFENSIVE"
    assert DRPState.EMERGENCY.value == "EMERGENCY"
    assert DRPState.RECOVERY.value == "RECOVERY"
    assert DRPState.HIBERNATE.value == "HIBERNATE"


def test_portfolio_state_mlops_state_enum():
    """Тест MLOpsState enum валидации."""
    assert MLOpsState.OK.value == "OK"
    assert MLOpsState.WARNING.value == "WARNING"
    assert MLOpsState.CRITICAL.value == "CRITICAL"


def test_portfolio_state_trading_mode_enum():
    """Тест TradingMode enum валидации."""
    assert TradingMode.LIVE.value == "LIVE"
    assert TradingMode.PAPER.value == "PAPER"
    assert TradingMode.SHADOW.value == "SHADOW"
    assert TradingMode.BACKTEST.value == "BACKTEST"


def test_portfolio_state_invalid_drp_state(valid_portfolio_state_data):
    """Тест невалидного DRP_state."""
    invalid_data = valid_portfolio_state_data.copy()
    invalid_data["states"]["DRP_state"] = "INVALID"

    with pytest.raises(ValidationError, match="Input should be"):
        PortfolioState(**invalid_data)


def test_portfolio_state_empty_positions(valid_portfolio_state_data):
    """Тест PortfolioState без позиций."""
    data = valid_portfolio_state_data.copy()
    data["positions"] = []

    portfolio_state = PortfolioState(**data)
    assert len(portfolio_state.positions) == 0


def test_portfolio_state_position_integration(valid_portfolio_state_data, valid_position):
    """Тест интеграции Position в PortfolioState."""
    portfolio_state = PortfolioState(**valid_portfolio_state_data)

    # Проверка, что Position корректно десериализована
    position = portfolio_state.positions[0]
    assert position.instrument == "BTCUSDT"
    assert position.direction == PositionDirection.LONG
    assert position.risk_amount_usd == 100.0


# =============================================================================
# TESTS: MLEOutput
# =============================================================================


def test_mle_output_creation(valid_mle_output_data):
    """Тест создания MLEOutput с валидными данными."""
    mle_output = MLEOutput(**valid_mle_output_data)

    assert mle_output.schema_version == "5"
    assert mle_output.model_id == "mle_v1.2.3"
    assert mle_output.decision == MLEDecision.NORMAL
    assert mle_output.risk_mult == 1.0
    assert mle_output.EV_R_price == 0.25


def test_mle_output_json_serialization(valid_mle_output_data):
    """Тест JSON сериализации MLEOutput."""
    mle_output = MLEOutput(**valid_mle_output_data)
    json_data = mle_output.model_dump()

    # Проверка, что JSON соответствует JSON Schema
    validate_mle_output(json_data)  # Должно пройти без исключений


def test_mle_output_json_deserialization(valid_mle_output_data):
    """Тест JSON десериализации MLEOutput."""
    mle_output = MLEOutput(**valid_mle_output_data)
    json_data = mle_output.model_dump()

    # Десериализация из JSON
    restored = MLEOutput(**json_data)

    assert restored.model_id == mle_output.model_id
    assert restored.decision == mle_output.decision


def test_mle_output_immutability(valid_mle_output_data):
    """Тест immutability MLEOutput (frozen=True)."""
    mle_output = MLEOutput(**valid_mle_output_data)

    with pytest.raises(ValidationError, match="frozen"):
        mle_output.decision = MLEDecision.REJECT  # type: ignore


def test_mle_output_decision_enum():
    """Тест MLEDecision enum валидации."""
    assert MLEDecision.REJECT.value == "REJECT"
    assert MLEDecision.WEAK.value == "WEAK"
    assert MLEDecision.NORMAL.value == "NORMAL"
    assert MLEDecision.STRONG.value == "STRONG"


def test_mle_output_invalid_decision(valid_mle_output_data):
    """Тест невалидного decision."""
    invalid_data = valid_mle_output_data.copy()
    invalid_data["decision"] = "INVALID"

    with pytest.raises(ValidationError, match="Input should be"):
        MLEOutput(**invalid_data)


def test_mle_output_artifact_sha256_pattern(valid_mle_output_data):
    """Тест валидации SHA256 pattern."""
    # Невалидный SHA256 (короткий)
    invalid_data = valid_mle_output_data.copy()
    invalid_data["artifact_sha256"] = "abc123"

    with pytest.raises(ValidationError, match="String should match pattern"):
        MLEOutput(**invalid_data)


def test_mle_output_probability_bounds(valid_mle_output_data):
    """Тест валидации границ вероятностей (0-1)."""
    # Невалидная вероятность (> 1)
    invalid_data = valid_mle_output_data.copy()
    invalid_data["p_fail"] = 1.5

    with pytest.raises(ValidationError, match="less than or equal to 1"):
        MLEOutput(**invalid_data)


def test_mle_output_optional_fields(valid_mle_output_data):
    """Тест optional полей MLEOutput."""
    # Убираем optional поля
    data = valid_mle_output_data.copy()
    data["p_stopout_noise"] = None
    data["expected_cost_R_preMLE"] = None
    data["expected_cost_R_postMLE"] = None

    mle_output = MLEOutput(**data)
    assert mle_output.p_stopout_noise is None
    assert mle_output.expected_cost_R_preMLE is None
    assert mle_output.expected_cost_R_postMLE is None


# =============================================================================
# TESTS: Cross-Model Integration
# =============================================================================


def test_portfolio_state_multiple_positions(valid_portfolio_state_data):
    """Тест PortfolioState с несколькими позициями."""
    position1 = Position(
        instrument="BTCUSDT",
        cluster_id="btc_cluster",
        direction=PositionDirection.LONG,
        qty=0.1,
        entry_price=42000.0,
        entry_eff_allin=42010.0,
        sl_eff_allin=41000.0,
        risk_amount_usd=100.0,
        risk_pct_equity=0.5,
        notional_usd=4200.0,
        unrealized_pnl_usd=50.0,
        funding_pnl_usd=-2.0,
        opened_ts_utc_ms=1700000000000,
    )

    position2 = Position(
        instrument="ETHUSDT",
        cluster_id="eth_cluster",
        direction=PositionDirection.SHORT,
        qty=1.0,
        entry_price=2200.0,
        entry_eff_allin=2198.0,
        sl_eff_allin=2300.0,
        risk_amount_usd=100.0,
        risk_pct_equity=0.5,
        notional_usd=2200.0,
        unrealized_pnl_usd=-30.0,
        funding_pnl_usd=1.0,
        opened_ts_utc_ms=1700000100000,
    )

    data = valid_portfolio_state_data.copy()
    data["positions"] = [position1.model_dump(), position2.model_dump()]

    portfolio_state = PortfolioState(**data)
    assert len(portfolio_state.positions) == 2
    assert portfolio_state.positions[0].instrument == "BTCUSDT"
    assert portfolio_state.positions[1].instrument == "ETHUSDT"


def test_full_state_roundtrip(valid_market_state_data, valid_portfolio_state_data, valid_mle_output_data):
    """Тест полного roundtrip всех state моделей через JSON."""
    # Создание моделей
    market_state = MarketState(**valid_market_state_data)
    portfolio_state = PortfolioState(**valid_portfolio_state_data)
    mle_output = MLEOutput(**valid_mle_output_data)

    # Сериализация в JSON
    market_json = market_state.model_dump()
    portfolio_json = portfolio_state.model_dump()
    mle_json = mle_output.model_dump()

    # Валидация через JSON Schema validators
    validate_market_state(market_json)
    validate_portfolio_state(portfolio_json)
    validate_mle_output(mle_json)

    # Десериализация из JSON
    restored_market = MarketState(**market_json)
    restored_portfolio = PortfolioState(**portfolio_json)
    restored_mle = MLEOutput(**mle_json)

    # Проверка идентичности
    assert restored_market.snapshot_id == market_state.snapshot_id
    assert restored_portfolio.portfolio_id == portfolio_state.portfolio_id
    assert restored_mle.model_id == mle_output.model_id


# =============================================================================
# TESTS: Additional Coverage (Nested Models, Boundary Cases)
# =============================================================================


def test_price_nested_model_validation():
    """Тест валидации nested Price модели."""
    # Валидный Price
    price = Price(last=100.0, mid=99.5, bid=99.0, ask=100.0, tick_size=0.1)
    assert price.last == 100.0

    # Невалидный Price (negative tick_size)
    with pytest.raises(ValidationError, match="greater than 0"):
        Price(last=100.0, mid=99.5, bid=99.0, ask=100.0, tick_size=-0.1)


def test_volatility_nested_model_nullable_fields():
    """Тест nullable полей в Volatility."""
    volatility = Volatility(
        atr=850.0,
        atr_z_short=0.5,
        atr_z_long=0.3,
        atr_window_short=14,
        hv30=None,
        hv30_z=None,
    )
    assert volatility.hv30 is None
    assert volatility.hv30_z is None


def test_liquidity_orderbook_staleness():
    """Тест валидации orderbook staleness в Liquidity."""
    liquidity = Liquidity(
        spread_bps=1.2,
        depth_bid_usd=500000.0,
        depth_ask_usd=480000.0,
        impact_bps_est=2.5,
        orderbook_staleness_ms=1000,
    )
    assert liquidity.orderbook_staleness_ms == 1000


def test_derivatives_adl_rank_quantile_bounds():
    """Тест границ adl_rank_quantile (0-1) в Derivatives."""
    # Валидный (в границах)
    derivatives = Derivatives(
        funding_rate_spot=0.0001,
        funding_period_hours=8.0,
        time_to_next_funding_sec=14400,
        adl_rank_quantile=0.5,
    )
    assert derivatives.adl_rank_quantile == 0.5

    # Невалидный (> 1)
    with pytest.raises(ValidationError, match="less than or equal to 1"):
        Derivatives(
            funding_rate_spot=0.0001,
            funding_period_hours=8.0,
            time_to_next_funding_sec=14400,
            adl_rank_quantile=1.5,
        )


def test_correlations_tail_reliability_score_bounds():
    """Тест границ tail_reliability_score (0-1) в Correlations."""
    correlations = Correlations(
        tail_metrics_reliable=True,
        tail_reliability_score=0.95,
    )
    assert correlations.tail_reliability_score == 0.95

    # Невалидный (< 0)
    with pytest.raises(ValidationError, match="greater than or equal to 0"):
        Correlations(
            tail_metrics_reliable=True,
            tail_reliability_score=-0.1,
        )


def test_data_quality_dqs_components_bounds():
    """Тест границ DQS компонентов (0-1) в DataQuality."""
    data_quality = DataQuality(
        suspected_data_glitch=False,
        stale_book_glitch=False,
        data_quality_score=0.95,
        dqs_critical=1.0,
        dqs_noncritical=0.9,
        dqs_sources=0.95,
        dqs_mult=1.0,
        staleness_price_ms=10,
        staleness_liquidity_ms=20,
        staleness_derivatives_sec=5,
        cross_exchange_dev_bps=0.5,
        price_sources_used=["exchange_ws"],
        toxic_flow_suspected=False,
    )
    assert data_quality.dqs_critical == 1.0


def test_equity_drawdown_fraction_validation():
    """Тест валидации drawdown как фракции (0-1) в Equity."""
    # Валидный (фракция)
    equity = Equity(
        equity_usd=10000.0,
        peak_equity_usd=10500.0,
        drawdown_pct=0.0476,
        drawdown_smoothed_pct=0.045,
    )
    assert equity.drawdown_pct == 0.0476

    # Невалидный (> 1, не фракция)
    with pytest.raises(ValidationError, match="less than or equal to 1"):
        Equity(
            equity_usd=10000.0,
            peak_equity_usd=10500.0,
            drawdown_pct=4.76,  # Should be 0.0476
            drawdown_smoothed_pct=0.045,
        )


def test_risk_model_all_fields():
    """Тест Risk модели со всеми полями."""
    risk = Risk(
        current_portfolio_risk_pct=1.5,
        current_cluster_risk_pct=0.8,
        reserved_portfolio_risk_pct=0.5,
        reserved_cluster_risk_pct=0.3,
        current_sum_abs_risk_pct=2.0,
        reserved_sum_abs_risk_pct=0.6,
        reserved_heat_upper_bound_pct=3.0,
        adjusted_heat_base_pct=1.8,
        adjusted_heat_blend_pct=1.9,
        adjusted_heat_worst_pct=2.1,
        heat_uni_abs_pct=1.7,
        max_portfolio_risk_pct=5.0,
        max_sum_abs_risk_pct=8.0,
        cluster_risk_limit_pct=3.0,
        max_adjusted_heat_pct=4.0,
        max_trade_risk_cap_pct=1.5,
    )
    assert risk.current_portfolio_risk_pct == 1.5
    assert risk.max_trade_risk_cap_pct == 1.5


def test_states_hibernate_timestamp_optional():
    """Тест optional hibernate_until_ts_utc_ms в States."""
    # С None
    states = States(
        DRP_state=DRPState.NORMAL,
        MLOps_state=MLOpsState.OK,
        trading_mode=TradingMode.LIVE,
        warmup_bars_remaining=0,
        drp_flap_count=0,
        hibernate_until_ts_utc_ms=None,
    )
    assert states.hibernate_until_ts_utc_ms is None

    # С timestamp
    states_with_hibernate = States(
        DRP_state=DRPState.HIBERNATE,
        MLOps_state=MLOpsState.OK,
        trading_mode=TradingMode.PAPER,
        warmup_bars_remaining=0,
        drp_flap_count=5,
        hibernate_until_ts_utc_ms=1700000000000,
    )
    assert states_with_hibernate.hibernate_until_ts_utc_ms == 1700000000000


def test_market_state_timeframe_constraint():
    """Тест constraint timeframe (должен быть 'H1') в MarketState."""
    valid_data = {
        "schema_version": "7",
        "snapshot_id": 12345,
        "ts_utc_ms": 1700000000000,
        "market_data_id": 67890,
        "data_gap_sec": 0,
        "is_gap_contaminated": False,
        "instrument": "BTCUSDT",
        "timeframe": "H1",
        "price": {"last": 100.0, "mid": 99.5, "bid": 99.0, "ask": 100.0, "tick_size": 0.1},
        "volatility": {"atr": 850.0, "atr_z_short": 0.5, "atr_z_long": 0.3, "atr_window_short": 14},
        "liquidity": {
            "spread_bps": 1.2,
            "depth_bid_usd": 500000.0,
            "depth_ask_usd": 480000.0,
            "impact_bps_est": 2.5,
            "orderbook_staleness_ms": 50,
        },
        "derivatives": {
            "funding_rate_spot": 0.0001,
            "funding_period_hours": 8.0,
            "time_to_next_funding_sec": 14400,
        },
        "correlations": {"tail_metrics_reliable": True, "tail_reliability_score": 0.85},
        "data_quality": {
            "suspected_data_glitch": False,
            "stale_book_glitch": False,
            "data_quality_score": 0.95,
            "dqs_critical": 0.98,
            "dqs_noncritical": 0.92,
            "dqs_sources": 0.96,
            "dqs_mult": 0.95,
            "staleness_price_ms": 10,
            "staleness_liquidity_ms": 20,
            "staleness_derivatives_sec": 5,
            "cross_exchange_dev_bps": 0.5,
            "price_sources_used": ["exchange_ws"],
            "toxic_flow_suspected": False,
        },
    }

    # Валидный timeframe
    market_state = MarketState(**valid_data)
    assert market_state.timeframe == "H1"

    # Невалидный timeframe
    invalid_data = valid_data.copy()
    invalid_data["timeframe"] = "M15"
    with pytest.raises(ValidationError, match="String should match pattern"):
        MarketState(**invalid_data)


def test_mle_output_schema_version_5():
    """Тест constraint schema_version (должна быть '5') в MLEOutput."""
    valid_data = {
        "schema_version": "5",
        "model_id": "mle_v1",
        "artifact_sha256": "a" * 64,
        "feature_schema_version": "1.0",
        "calibration_version": "2.1",
        "decision": "NORMAL",
        "risk_mult": 1.0,
        "EV_R_price": 0.25,
        "p_fail": 0.35,
        "p_neutral": 0.15,
        "p_success": 0.50,
    }

    mle_output = MLEOutput(**valid_data)
    assert mle_output.schema_version == "5"

    # Невалидная версия
    invalid_data = valid_data.copy()
    invalid_data["schema_version"] = "6"
    with pytest.raises(ValidationError, match="String should match pattern"):
        MLEOutput(**invalid_data)


def test_portfolio_state_schema_version_7():
    """Тест constraint schema_version (должна быть '7') в PortfolioState."""
    data = {
        "schema_version": "7",
        "snapshot_id": 12345,
        "portfolio_id": 100,
        "ts_utc_ms": 1700000000000,
        "equity": {
            "equity_usd": 10000.0,
            "peak_equity_usd": 10500.0,
            "drawdown_pct": 0.0476,
            "drawdown_smoothed_pct": 0.045,
        },
        "risk": {
            "current_portfolio_risk_pct": 1.5,
            "current_cluster_risk_pct": 0.8,
            "reserved_portfolio_risk_pct": 0.5,
            "reserved_cluster_risk_pct": 0.3,
            "current_sum_abs_risk_pct": 2.0,
            "reserved_sum_abs_risk_pct": 0.6,
            "reserved_heat_upper_bound_pct": 3.0,
            "adjusted_heat_base_pct": 1.8,
            "adjusted_heat_blend_pct": 1.9,
            "adjusted_heat_worst_pct": 2.1,
            "heat_uni_abs_pct": 1.7,
            "max_portfolio_risk_pct": 5.0,
            "max_sum_abs_risk_pct": 8.0,
            "cluster_risk_limit_pct": 3.0,
            "max_adjusted_heat_pct": 4.0,
            "max_trade_risk_cap_pct": 1.5,
        },
        "states": {
            "DRP_state": "NORMAL",
            "MLOps_state": "OK",
            "trading_mode": "LIVE",
            "warmup_bars_remaining": 0,
            "drp_flap_count": 0,
            "hibernate_until_ts_utc_ms": None,
        },
        "positions": [],
    }

    portfolio_state = PortfolioState(**data)
    assert portfolio_state.schema_version == "7"

