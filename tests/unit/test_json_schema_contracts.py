"""
Tests for JSON Schema Contract Validators

ТЗ: Appendix B (обязательные схемы контрактов)

Комплексное тестирование JSON Schema валидаторов:
- Валидность самих схем
- Валидация правильных данных
- Детекция нарушений required полей
- Детекция нарушений типов
- Детекция нарушений constraints (min/max/enum/pattern)
- Интеграция с Pydantic моделями
"""

import json
from pathlib import Path

import pytest
from jsonschema import ValidationError

from src.core.contracts import (
    EngineSignalValidator,
    MarketStateValidator,
    MLEOutputValidator,
    PortfolioStateValidator,
    SchemaLoader,
    validate_engine_signal,
    validate_market_state,
    validate_mle_output,
    validate_portfolio_state,
)
from src.core.domain import EngineType, Position, Signal, SignalDirection


# =============================================================================
# FIXTURES - VALID DATA SAMPLES
# =============================================================================


@pytest.fixture
def valid_market_state():
    """Валидный market_state для тестирования."""
    return {
        "schema_version": "7",
        "snapshot_id": 12345,
        "ts_utc_ms": 1700000000000,
        "market_data_id": 67890,
        "data_gap_sec": 0,
        "is_gap_contaminated": False,
        "instrument": "BTCUSDT",
        "timeframe": "H1",
        "price": {
            "last": 42000.50,
            "mid": 42000.25,
            "bid": 42000.00,
            "ask": 42000.50,
            "tick_size": 0.50,
        },
        "volatility": {
            "atr": 850.0,
            "atr_z_short": 0.5,
            "atr_z_long": 0.3,
            "atr_window_short": 14,
            "hv30": 0.65,
            "hv30_z": 0.2,
        },
        "liquidity": {
            "spread_bps": 1.2,
            "depth_bid_usd": 500000.0,
            "depth_ask_usd": 480000.0,
            "impact_bps_est": 2.5,
            "orderbook_staleness_ms": 50,
            "orderbook_last_update_id": 999999,
            "orderbook_update_id_age_ms": 45,
        },
        "derivatives": {
            "funding_rate_spot": 0.0001,
            "funding_rate_forecast": 0.00012,
            "funding_period_hours": 8.0,
            "time_to_next_funding_sec": 14400,
            "oi": 1500000000.0,
            "basis_value": 5.0,
            "basis_z": 0.8,
            "basis_vol_z": 0.6,
            "adl_rank_quantile": 0.25,
        },
        "correlations": {
            "tail_metrics_reliable": True,
            "tail_reliability_score": 0.85,
            "tail_corr_to_btc": 0.92,
            "stress_beta_to_btc": 1.15,
            "lambda_tail_dep": 0.45,
            "corr_matrix_snapshot_id": 5000,
            "corr_matrix_age_sec": 300,
            "gamma_s": 0.35,
        },
        "data_quality": {
            "suspected_data_glitch": False,
            "stale_book_glitch": False,
            "data_quality_score": 0.95,
            "dqs_critical": 0.98,
            "dqs_noncritical": 0.92,
            "dqs_sources": 0.90,
            "dqs_mult": 0.95,
            "staleness_price_ms": 30,
            "staleness_liquidity_ms": 50,
            "staleness_derivatives_sec": 10,
            "cross_exchange_dev_bps": 0.5,
            "oracle_dev_frac": 0.001,
            "oracle_staleness_ms": 100,
            "price_sources_used": ["binance", "bybit", "okx"],
            "toxic_flow_suspected": False,
            "execution_price_improvement_bps": 0.2,
        },
    }


@pytest.fixture
def valid_portfolio_state():
    """Валидный portfolio_state для тестирования."""
    return {
        "schema_version": "7",
        "snapshot_id": 12346,
        "portfolio_id": 5678,
        "ts_utc_ms": 1700000000000,
        "equity": {
            "equity_usd": 10000.0,
            "peak_equity_usd": 11000.0,
            "drawdown_pct": 0.09,
            "drawdown_smoothed_pct": 0.085,
        },
        "risk": {
            "current_portfolio_risk_pct": 0.015,
            "current_cluster_risk_pct": 0.010,
            "reserved_portfolio_risk_pct": 0.005,
            "reserved_cluster_risk_pct": 0.003,
            "current_sum_abs_risk_pct": 0.018,
            "reserved_sum_abs_risk_pct": 0.006,
            "reserved_heat_upper_bound_pct": 0.012,
            "adjusted_heat_base_pct": 0.014,
            "adjusted_heat_blend_pct": 0.016,
            "adjusted_heat_worst_pct": 0.020,
            "heat_uni_abs_pct": 0.018,
            "max_portfolio_risk_pct": 0.04,
            "max_sum_abs_risk_pct": 0.04,
            "cluster_risk_limit_pct": 0.03,
            "max_adjusted_heat_pct": 0.03,
            "max_trade_risk_cap_pct": 0.005,
        },
        "states": {
            "DRP_state": "NORMAL",
            "MLOps_state": "OK",
            "trading_mode": "LIVE",
            "warmup_bars_remaining": 0,
            "drp_flap_count": 0,
            "hibernate_until_ts_utc_ms": None,
        },
        "positions": [
            {
                "instrument": "BTCUSDT",
                "cluster_id": "crypto_large_cap",
                "direction": "long",
                "qty": 0.05,
                "entry_price": 40000.0,
                "entry_eff_allin": 40020.0,
                "sl_eff_allin": 39500.0,
                "risk_amount_usd": 50.0,
                "risk_pct_equity": 0.005,
                "notional_usd": 2000.0,
                "unrealized_pnl_usd": 100.0,
                "funding_pnl_usd": -2.5,
                "opened_ts_utc_ms": 1699900000000,
            }
        ],
    }


@pytest.fixture
def valid_engine_signal():
    """Валидный engine_signal для тестирования."""
    return {
        "schema_version": "3",
        "instrument": "ETHUSDT",
        "engine": "TREND",
        "direction": "long",
        "signal_ts_utc_ms": 1700000000000,
        "levels": {"entry_price": 2200.0, "stop_loss": 2150.0, "take_profit": 2300.0},
        "context": {
            "expected_holding_hours": 12.0,
            "regime_hint": "trending_up",
            "setup_id": "TREND_LONG_001",
        },
        "constraints": {"RR_min_engine": 1.5, "sl_min_atr_mult": 1.0, "sl_max_atr_mult": 3.0},
    }


@pytest.fixture
def valid_mle_output():
    """Валидный mle_output для тестирования."""
    return {
        "schema_version": "5",
        "model_id": "mle_v1.2.3",
        "artifact_sha256": "a" * 64,  # Valid SHA256 hex string
        "feature_schema_version": "fs_v2.1",
        "calibration_version": "cal_v1.5",
        "decision": "NORMAL",
        "risk_mult": 1.0,
        "EV_R_price": 0.25,
        "p_fail": 0.35,
        "p_neutral": 0.15,
        "p_success": 0.50,
        "p_stopout_noise": 0.10,
        "expected_cost_R_preMLE": 0.08,
        "expected_cost_R_postMLE": 0.07,
    }


# =============================================================================
# TESTS - SCHEMA LOADING
# =============================================================================


def test_schema_loader_loads_all_schemas():
    """Проверка загрузки всех схем."""
    loader = SchemaLoader()

    # Все схемы должны загружаться без ошибок
    market_state_schema = loader.load_schema("market_state")
    portfolio_state_schema = loader.load_schema("portfolio_state")
    engine_signal_schema = loader.load_schema("engine_signal")
    mle_output_schema = loader.load_schema("mle_output")

    # Проверка версий схем
    assert market_state_schema["properties"]["schema_version"]["const"] == "7"
    assert portfolio_state_schema["properties"]["schema_version"]["const"] == "7"
    assert engine_signal_schema["properties"]["schema_version"]["const"] == "3"
    assert mle_output_schema["properties"]["schema_version"]["const"] == "5"


def test_schema_loader_caches_schemas():
    """Проверка кэширования схем."""
    loader = SchemaLoader()

    schema1 = loader.load_schema("market_state")
    schema2 = loader.load_schema("market_state")

    # Должен вернуть тот же объект (кэш)
    assert schema1 is schema2


def test_schema_loader_raises_on_missing_schema():
    """Проверка ошибки при отсутствующей схеме."""
    loader = SchemaLoader()

    with pytest.raises(FileNotFoundError):
        loader.load_schema("non_existent_schema")


# =============================================================================
# TESTS - MARKET STATE VALIDATION
# =============================================================================


def test_market_state_validator_accepts_valid_data(valid_market_state):
    """Валидация правильного market_state."""
    validator = MarketStateValidator()
    validator.validate(valid_market_state)  # Не должно выбросить исключение
    assert validator.is_valid(valid_market_state)


def test_market_state_validate_function(valid_market_state):
    """Проверка функции validate_market_state."""
    validate_market_state(valid_market_state)  # Не должно выбросить исключение


def test_market_state_rejects_missing_required_field(valid_market_state):
    """Валидация отклоняет данные без обязательных полей."""
    validator = MarketStateValidator()

    # Удаляем обязательное поле
    data = valid_market_state.copy()
    del data["instrument"]

    with pytest.raises(ValidationError) as exc_info:
        validator.validate(data)
    assert "'instrument' is a required property" in str(exc_info.value)


def test_market_state_rejects_wrong_type(valid_market_state):
    """Валидация отклоняет неправильный тип данных."""
    validator = MarketStateValidator()

    # Неправильный тип для snapshot_id (должен быть int, а не str)
    data = valid_market_state.copy()
    data["snapshot_id"] = "not_an_integer"

    with pytest.raises(ValidationError) as exc_info:
        validator.validate(data)
    assert "is not of type 'integer'" in str(exc_info.value)


def test_market_state_rejects_negative_snapshot_id(valid_market_state):
    """Валидация отклоняет отрицательный snapshot_id."""
    validator = MarketStateValidator()

    data = valid_market_state.copy()
    data["snapshot_id"] = -1

    with pytest.raises(ValidationError):
        validator.validate(data)


def test_market_state_rejects_wrong_timeframe(valid_market_state):
    """Валидация отклоняет неправильный timeframe."""
    validator = MarketStateValidator()

    data = valid_market_state.copy()
    data["timeframe"] = "M5"  # Должно быть "H1"

    with pytest.raises(ValidationError):
        validator.validate(data)


def test_market_state_accepts_null_optional_fields(valid_market_state):
    """Валидация принимает null для опциональных полей."""
    validator = MarketStateValidator()

    data = valid_market_state.copy()
    data["volatility"]["hv30"] = None
    data["volatility"]["hv30_z"] = None
    data["derivatives"]["funding_rate_forecast"] = None
    data["derivatives"]["oi"] = None
    data["derivatives"]["basis_value"] = None
    data["derivatives"]["basis_z"] = None
    data["derivatives"]["basis_vol_z"] = None
    data["derivatives"]["adl_rank_quantile"] = None

    validator.validate(data)  # Не должно выбросить исключение


def test_market_state_rejects_invalid_enum(valid_market_state):
    """Валидация отклоняет невалидное значение enum."""
    validator = MarketStateValidator()

    # Попытка изменить const поле schema_version
    data = valid_market_state.copy()
    data["schema_version"] = "999"  # Должно быть "7"

    with pytest.raises(ValidationError):
        validator.validate(data)


def test_market_state_rejects_negative_prices(valid_market_state):
    """Валидация отклоняет отрицательные цены."""
    validator = MarketStateValidator()

    data = valid_market_state.copy()
    data["price"]["last"] = -100.0  # exclusiveMinimum: 0

    with pytest.raises(ValidationError):
        validator.validate(data)


def test_market_state_rejects_zero_prices(valid_market_state):
    """Валидация отклоняет нулевые цены (exclusiveMinimum)."""
    validator = MarketStateValidator()

    data = valid_market_state.copy()
    data["price"]["bid"] = 0.0  # exclusiveMinimum: 0

    with pytest.raises(ValidationError):
        validator.validate(data)


# =============================================================================
# TESTS - PORTFOLIO STATE VALIDATION
# =============================================================================


def test_portfolio_state_validator_accepts_valid_data(valid_portfolio_state):
    """Валидация правильного portfolio_state."""
    validator = PortfolioStateValidator()
    validator.validate(valid_portfolio_state)
    assert validator.is_valid(valid_portfolio_state)


def test_portfolio_state_validate_function(valid_portfolio_state):
    """Проверка функции validate_portfolio_state."""
    validate_portfolio_state(valid_portfolio_state)


def test_portfolio_state_rejects_invalid_drp_state(valid_portfolio_state):
    """Валидация отклоняет невалидный DRP_state."""
    validator = PortfolioStateValidator()

    data = valid_portfolio_state.copy()
    data["states"]["DRP_state"] = "INVALID_STATE"

    with pytest.raises(ValidationError):
        validator.validate(data)


def test_portfolio_state_rejects_drawdown_above_1(valid_portfolio_state):
    """Валидация отклоняет drawdown > 100%."""
    validator = PortfolioStateValidator()

    data = valid_portfolio_state.copy()
    data["equity"]["drawdown_pct"] = 1.5  # maximum: 1

    with pytest.raises(ValidationError):
        validator.validate(data)


def test_portfolio_state_accepts_empty_positions(valid_portfolio_state):
    """Валидация принимает пустой массив позиций."""
    validator = PortfolioStateValidator()

    data = valid_portfolio_state.copy()
    data["positions"] = []

    validator.validate(data)


def test_portfolio_state_rejects_position_risk_below_minimum(valid_portfolio_state):
    """Валидация отклоняет риск позиции ниже 0.10 USD."""
    validator = PortfolioStateValidator()

    data = valid_portfolio_state.copy()
    data["positions"][0]["risk_amount_usd"] = 0.05  # minimum: 0.10

    with pytest.raises(ValidationError):
        validator.validate(data)


def test_portfolio_state_rejects_position_risk_pct_above_1(valid_portfolio_state):
    """Валидация отклоняет риск позиции > 100% equity."""
    validator = PortfolioStateValidator()

    data = valid_portfolio_state.copy()
    data["positions"][0]["risk_pct_equity"] = 1.5  # maximum: 1

    with pytest.raises(ValidationError):
        validator.validate(data)


def test_portfolio_state_rejects_invalid_position_direction(valid_portfolio_state):
    """Валидация отклоняет невалидное направление позиции."""
    validator = PortfolioStateValidator()

    data = valid_portfolio_state.copy()
    data["positions"][0]["direction"] = "sideways"  # enum: ["long", "short"]

    with pytest.raises(ValidationError):
        validator.validate(data)


# =============================================================================
# TESTS - ENGINE SIGNAL VALIDATION
# =============================================================================


def test_engine_signal_validator_accepts_valid_data(valid_engine_signal):
    """Валидация правильного engine_signal."""
    validator = EngineSignalValidator()
    validator.validate(valid_engine_signal)
    assert validator.is_valid(valid_engine_signal)


def test_engine_signal_validate_function(valid_engine_signal):
    """Проверка функции validate_engine_signal."""
    validate_engine_signal(valid_engine_signal)


def test_engine_signal_rejects_invalid_engine_type(valid_engine_signal):
    """Валидация отклоняет невалидный тип engine."""
    validator = EngineSignalValidator()

    data = valid_engine_signal.copy()
    data["engine"] = "MOMENTUM"  # enum: ["TREND", "RANGE"]

    with pytest.raises(ValidationError):
        validator.validate(data)


def test_engine_signal_rejects_zero_prices(valid_engine_signal):
    """Валидация отклоняет нулевые цены (exclusiveMinimum)."""
    validator = EngineSignalValidator()

    data = valid_engine_signal.copy()
    data["levels"]["entry_price"] = 0.0  # exclusiveMinimum: 0

    with pytest.raises(ValidationError):
        validator.validate(data)


def test_engine_signal_rejects_zero_holding_hours(valid_engine_signal):
    """Валидация отклоняет нулевое время удержания."""
    validator = EngineSignalValidator()

    data = valid_engine_signal.copy()
    data["context"]["expected_holding_hours"] = 0.0  # exclusiveMinimum: 0

    with pytest.raises(ValidationError):
        validator.validate(data)


def test_engine_signal_accepts_null_regime_hint(valid_engine_signal):
    """Валидация принимает null для regime_hint."""
    validator = EngineSignalValidator()

    data = valid_engine_signal.copy()
    data["context"]["regime_hint"] = None

    validator.validate(data)


def test_engine_signal_rejects_negative_rr(valid_engine_signal):
    """Валидация отклоняет отрицательный RR."""
    validator = EngineSignalValidator()

    data = valid_engine_signal.copy()
    data["constraints"]["RR_min_engine"] = -0.5  # exclusiveMinimum: 0

    with pytest.raises(ValidationError):
        validator.validate(data)


def test_engine_signal_rejects_empty_setup_id(valid_engine_signal):
    """Валидация отклоняет пустой setup_id."""
    validator = EngineSignalValidator()

    data = valid_engine_signal.copy()
    data["context"]["setup_id"] = ""  # minLength: 1

    with pytest.raises(ValidationError):
        validator.validate(data)


# =============================================================================
# TESTS - MLE OUTPUT VALIDATION
# =============================================================================


def test_mle_output_validator_accepts_valid_data(valid_mle_output):
    """Валидация правильного mle_output."""
    validator = MLEOutputValidator()
    validator.validate(valid_mle_output)
    assert validator.is_valid(valid_mle_output)


def test_mle_output_validate_function(valid_mle_output):
    """Проверка функции validate_mle_output."""
    validate_mle_output(valid_mle_output)


def test_mle_output_rejects_invalid_decision(valid_mle_output):
    """Валидация отклоняет невалидное решение."""
    validator = MLEOutputValidator()

    data = valid_mle_output.copy()
    data["decision"] = "MAYBE"  # enum: ["REJECT", "WEAK", "NORMAL", "STRONG"]

    with pytest.raises(ValidationError):
        validator.validate(data)


def test_mle_output_rejects_risk_mult_above_2(valid_mle_output):
    """Валидация отклоняет risk_mult > 2."""
    validator = MLEOutputValidator()

    data = valid_mle_output.copy()
    data["risk_mult"] = 2.5  # maximum: 2

    with pytest.raises(ValidationError):
        validator.validate(data)


def test_mle_output_rejects_risk_mult_below_0(valid_mle_output):
    """Валидация отклоняет отрицательный risk_mult."""
    validator = MLEOutputValidator()

    data = valid_mle_output.copy()
    data["risk_mult"] = -0.1  # minimum: 0

    with pytest.raises(ValidationError):
        validator.validate(data)


def test_mle_output_rejects_probability_above_1(valid_mle_output):
    """Валидация отклоняет вероятность > 1."""
    validator = MLEOutputValidator()

    data = valid_mle_output.copy()
    data["p_success"] = 1.5  # maximum: 1

    with pytest.raises(ValidationError):
        validator.validate(data)


def test_mle_output_rejects_probability_below_0(valid_mle_output):
    """Валидация отклоняет отрицательную вероятность."""
    validator = MLEOutputValidator()

    data = valid_mle_output.copy()
    data["p_fail"] = -0.1  # minimum: 0

    with pytest.raises(ValidationError):
        validator.validate(data)


def test_mle_output_rejects_invalid_sha256(valid_mle_output):
    """Валидация отклоняет невалидный SHA256."""
    validator = MLEOutputValidator()

    data = valid_mle_output.copy()
    data["artifact_sha256"] = "invalid_sha"  # pattern: ^[a-fA-F0-9]{64}$

    with pytest.raises(ValidationError):
        validator.validate(data)


def test_mle_output_accepts_null_optional_fields(valid_mle_output):
    """Валидация принимает null для опциональных полей."""
    validator = MLEOutputValidator()

    data = valid_mle_output.copy()
    data["p_stopout_noise"] = None
    data["expected_cost_R_preMLE"] = None
    data["expected_cost_R_postMLE"] = None

    validator.validate(data)


def test_mle_output_rejects_negative_expected_cost(valid_mle_output):
    """Валидация отклоняет отрицательный expected_cost."""
    validator = MLEOutputValidator()

    data = valid_mle_output.copy()
    data["expected_cost_R_preMLE"] = -0.01  # minimum: 0

    with pytest.raises(ValidationError):
        validator.validate(data)


# =============================================================================
# TESTS - PYDANTIC MODEL INTEGRATION
# =============================================================================


def test_signal_model_generates_valid_json():
    """Проверка, что Pydantic Signal модель генерирует валидный JSON."""
    signal = Signal(
        instrument="BTCUSDT",
        engine=EngineType.TREND,
        direction=SignalDirection.LONG,
        signal_ts_utc_ms=1700000000000,
        levels={
            "entry_price": 42000.0,
            "stop_loss": 41500.0,
            "take_profit": 43000.0,
        },
        context={
            "expected_holding_hours": 8.0,
            "regime_hint": "trending",
            "setup_id": "TREND_001",
        },
        constraints={
            "RR_min_engine": 1.5,
            "sl_min_atr_mult": 1.0,
            "sl_max_atr_mult": 3.0,
        },
    )

    # Конвертируем в dict
    signal_dict = signal.model_dump()
    # Добавляем schema_version (не часть Pydantic модели, но требуется в JSON Schema)
    signal_dict["schema_version"] = "3"
    # Конвертируем enum в строки
    signal_dict["engine"] = signal_dict["engine"].value
    signal_dict["direction"] = signal_dict["direction"].value

    # Валидация через JSON Schema
    validate_engine_signal(signal_dict)


def test_position_model_generates_valid_json_for_portfolio():
    """Проверка, что Pydantic Position модель генерирует валидный JSON для portfolio_state."""
    # Note: Position uses PositionDirection, not SignalDirection, but they have same values
    from src.core.domain import PositionDirection
    
    position = Position(
        instrument="ETHUSDT",
        cluster_id="crypto_medium_cap",
        direction=PositionDirection.SHORT,
        qty=1.5,
        entry_price=2200.0,
        entry_eff_allin=2198.0,
        sl_eff_allin=2250.0,
        risk_amount_usd=75.0,
        risk_pct_equity=0.0075,
        notional_usd=3300.0,
        unrealized_pnl_usd=-50.0,
        funding_pnl_usd=1.2,
        opened_ts_utc_ms=1699900000000,
    )

    # Конвертируем в dict
    position_dict = position.model_dump()
    # Конвертируем enum в строки
    position_dict["direction"] = position_dict["direction"].value

    # Создаём минимальный portfolio_state с одной позицией
    portfolio_state = {
        "schema_version": "7",
        "snapshot_id": 1,
        "portfolio_id": 1,
        "ts_utc_ms": 1700000000000,
        "equity": {
            "equity_usd": 10000.0,
            "peak_equity_usd": 10500.0,
            "drawdown_pct": 0.05,
            "drawdown_smoothed_pct": 0.045,
        },
        "risk": {
            "current_portfolio_risk_pct": 0.01,
            "current_cluster_risk_pct": 0.008,
            "reserved_portfolio_risk_pct": 0.002,
            "reserved_cluster_risk_pct": 0.001,
            "current_sum_abs_risk_pct": 0.012,
            "reserved_sum_abs_risk_pct": 0.003,
            "reserved_heat_upper_bound_pct": 0.015,
            "adjusted_heat_base_pct": 0.011,
            "adjusted_heat_blend_pct": 0.013,
            "adjusted_heat_worst_pct": 0.018,
            "heat_uni_abs_pct": 0.012,
            "max_portfolio_risk_pct": 0.04,
            "max_sum_abs_risk_pct": 0.04,
            "cluster_risk_limit_pct": 0.03,
            "max_adjusted_heat_pct": 0.03,
            "max_trade_risk_cap_pct": 0.005,
        },
        "states": {
            "DRP_state": "NORMAL",
            "MLOps_state": "OK",
            "trading_mode": "LIVE",
            "warmup_bars_remaining": 0,
            "drp_flap_count": 0,
            "hibernate_until_ts_utc_ms": None,
        },
        "positions": [position_dict],
    }

    # Валидация через JSON Schema
    validate_portfolio_state(portfolio_state)


def test_iter_errors_returns_all_errors():
    """Проверка, что iter_errors возвращает все ошибки валидации."""
    validator = EngineSignalValidator()

    # Данные с множественными нарушениями
    invalid_data = {
        "schema_version": "3",
        "instrument": "",  # minLength: 1 - НАРУШЕНИЕ
        "engine": "INVALID",  # enum violation - НАРУШЕНИЕ
        "direction": "long",
        "signal_ts_utc_ms": -100,  # exclusiveMinimum: 0 - НАРУШЕНИЕ
        "levels": {
            "entry_price": 0.0,  # exclusiveMinimum: 0 - НАРУШЕНИЕ
            "stop_loss": 100.0,
            "take_profit": 200.0,
        },
        "context": {
            "expected_holding_hours": 0.0,  # exclusiveMinimum: 0 - НАРУШЕНИЕ
            "setup_id": "SETUP_001",
        },
        "constraints": {
            "RR_min_engine": 1.5,
            "sl_min_atr_mult": 1.0,
            "sl_max_atr_mult": 3.0,
        },
    }

    errors = list(validator.iter_errors(invalid_data))
    # Должно быть как минимум 5 ошибок
    assert len(errors) >= 5


# =============================================================================
# SUMMARY
# =============================================================================

# Итого тестов:
# - Schema Loading: 3
# - Market State: 10
# - Portfolio State: 7
# - Engine Signal: 7
# - MLE Output: 9
# - Pydantic Integration: 3
# Всего: 39 тестов
