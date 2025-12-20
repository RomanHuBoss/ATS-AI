"""
Тесты для базовых доменных моделей: Position, Trade, Signal

ТЗ: Appendix B.2, B.3 (схемы данных)
ТЗ: 2.1.1.0 (RiskUnits)
ТЗ: 8.1 (RR sanity gates)

Проверяет:
1. Создание и валидацию моделей Pydantic
2. Корректность бизнес-логики (R-value, RR, направление)
3. Immutability (frozen=True)
4. Сериализацию/десериализацию JSON
5. Граничные случаи и невалидные данные
"""

import json

import pytest
from pydantic import ValidationError

from src.core.domain import (
    EngineType,
    ExitReason,
    Position,
    PositionDirection,
    Signal,
    SignalConstraints,
    SignalContext,
    SignalDirection,
    SignalLevels,
    Trade,
    TradeDirection,
)


# =============================================================================
# POSITION TESTS
# =============================================================================


class TestPosition:
    """Тесты для модели Position"""

    @pytest.fixture
    def valid_position_long(self) -> Position:
        """Валидная LONG позиция"""
        return Position(
            instrument="BTCUSDT",
            cluster_id="crypto_major",
            direction=PositionDirection.LONG,
            qty=0.5,
            entry_price=50000.0,
            entry_eff_allin=50050.0,  # entry + costs
            sl_eff_allin=49500.0,  # entry - 500 (SL)
            risk_amount_usd=275.0,  # 0.5 * (50050 - 49500)
            risk_pct_equity=0.0055,  # 0.55% of 50k equity
            notional_usd=25000.0,  # 0.5 * 50000
            unrealized_pnl_usd=100.0,
            funding_pnl_usd=-5.0,
            opened_ts_utc_ms=1700000000000,
        )

    @pytest.fixture
    def valid_position_short(self) -> Position:
        """Валидная SHORT позиция"""
        return Position(
            instrument="ETHUSDT",
            cluster_id="crypto_major",
            direction=PositionDirection.SHORT,
            qty=5.0,
            entry_price=3000.0,
            entry_eff_allin=2985.0,  # entry - costs
            sl_eff_allin=3090.0,  # entry + 90 (SL)
            risk_amount_usd=525.0,  # 5 * (3090 - 2985)
            risk_pct_equity=0.0105,  # 1.05% of 50k equity
            notional_usd=15000.0,  # 5 * 3000
            unrealized_pnl_usd=-50.0,
            funding_pnl_usd=2.0,
            opened_ts_utc_ms=1700000000000,
        )

    def test_position_creation_long(self, valid_position_long: Position) -> None:
        """Создание LONG позиции с валидными данными"""
        pos = valid_position_long
        assert pos.instrument == "BTCUSDT"
        assert pos.direction == PositionDirection.LONG
        assert pos.qty == 0.5
        assert pos.entry_price == 50000.0
        assert pos.risk_amount_usd == 275.0

    def test_position_creation_short(self, valid_position_short: Position) -> None:
        """Создание SHORT позиции с валидными данными"""
        pos = valid_position_short
        assert pos.instrument == "ETHUSDT"
        assert pos.direction == PositionDirection.SHORT
        assert pos.qty == 5.0

    def test_position_immutable(self, valid_position_long: Position) -> None:
        """Позиция должна быть immutable (frozen=True)"""
        with pytest.raises(ValidationError):
            valid_position_long.qty = 1.0  # type: ignore

    def test_position_r_value(self, valid_position_long: Position) -> None:
        """Расчёт R-value для позиции"""
        # total_pnl = unrealized + funding = 100 - 5 = 95 USD
        # R = 95 / 275 ≈ 0.345R
        total_pnl = valid_position_long.total_pnl_usd()
        r_val = valid_position_long.r_value(total_pnl)
        assert abs(r_val - (95.0 / 275.0)) < 1e-9

    def test_position_total_pnl(self, valid_position_long: Position) -> None:
        """Расчёт полного PnL (unrealized + funding)"""
        total = valid_position_long.total_pnl_usd()
        assert total == 100.0 - 5.0
        assert total == 95.0

    def test_position_risk_minimum_validation(self) -> None:
        """Валидация минимального риска (0.10 USD)"""
        with pytest.raises(ValidationError) as exc_info:
            Position(
                instrument="BTCUSDT",
                cluster_id="crypto",
                direction=PositionDirection.LONG,
                qty=0.001,
                entry_price=50000.0,
                entry_eff_allin=50050.0,
                sl_eff_allin=49950.0,
                risk_amount_usd=0.05,  # Below minimum 0.10
                risk_pct_equity=0.0001,
                notional_usd=50.0,
                unrealized_pnl_usd=0.0,
                funding_pnl_usd=0.0,
                opened_ts_utc_ms=1700000000000,
            )
        assert "risk_amount_usd" in str(exc_info.value).lower()

    def test_position_risk_pct_max_validation(self) -> None:
        """Валидация максимального риска (100% equity)"""
        with pytest.raises(ValidationError) as exc_info:
            Position(
                instrument="BTCUSDT",
                cluster_id="crypto",
                direction=PositionDirection.LONG,
                qty=1.0,
                entry_price=50000.0,
                entry_eff_allin=50050.0,
                sl_eff_allin=49500.0,
                risk_amount_usd=550.0,
                risk_pct_equity=1.5,  # 150% - exceeds 100%
                notional_usd=50000.0,
                unrealized_pnl_usd=0.0,
                funding_pnl_usd=0.0,
                opened_ts_utc_ms=1700000000000,
            )
        assert "risk_pct_equity" in str(exc_info.value).lower()

    def test_position_negative_qty_validation(self) -> None:
        """Валидация отрицательного количества"""
        with pytest.raises(ValidationError):
            Position(
                instrument="BTCUSDT",
                cluster_id="crypto",
                direction=PositionDirection.LONG,
                qty=-0.5,  # Negative
                entry_price=50000.0,
                entry_eff_allin=50050.0,
                sl_eff_allin=49500.0,
                risk_amount_usd=275.0,
                risk_pct_equity=0.0055,
                notional_usd=25000.0,
                unrealized_pnl_usd=0.0,
                funding_pnl_usd=0.0,
                opened_ts_utc_ms=1700000000000,
            )

    def test_position_json_serialization(self, valid_position_long: Position) -> None:
        """Сериализация Position в JSON и обратно"""
        # Serialize
        json_str = valid_position_long.model_dump_json()
        data = json.loads(json_str)

        # Validate JSON structure
        assert data["instrument"] == "BTCUSDT"
        assert data["direction"] == "long"
        assert data["qty"] == 0.5

        # Deserialize
        restored = Position.model_validate_json(json_str)
        assert restored == valid_position_long


# =============================================================================
# TRADE TESTS
# =============================================================================


class TestTrade:
    """Тесты для модели Trade"""

    @pytest.fixture
    def valid_trade_winner(self) -> Trade:
        """Валидная прибыльная сделка (TP hit)"""
        return Trade(
            trade_id="trade_001",
            instrument="BTCUSDT",
            cluster_id="crypto_major",
            direction=TradeDirection.LONG,
            entry_price=50000.0,
            entry_eff_allin=50050.0,
            entry_qty=0.5,
            entry_ts_utc_ms=1700000000000,
            exit_price=51000.0,
            exit_eff_allin=50950.0,  # 51000 - costs
            exit_qty=0.5,
            exit_ts_utc_ms=1700003600000,  # +1 hour
            exit_reason=ExitReason.TAKE_PROFIT,
            risk_amount_usd=275.0,
            risk_pct_equity=0.0055,
            sl_eff_allin=49500.0,
            tp_eff_allin=50950.0,
            gross_pnl_usd=500.0,  # 0.5 * (51000 - 50000)
            net_pnl_usd=450.0,  # 0.5 * (50950 - 50050)
            funding_pnl_usd=-2.0,
            commission_usd=50.0,
            equity_before_usd=50000.0,
        )

    @pytest.fixture
    def valid_trade_loser(self) -> Trade:
        """Валидная убыточная сделка (SL hit)"""
        return Trade(
            trade_id="trade_002",
            instrument="ETHUSDT",
            cluster_id="crypto_major",
            direction=TradeDirection.SHORT,
            entry_price=3000.0,
            entry_eff_allin=2985.0,
            entry_qty=5.0,
            entry_ts_utc_ms=1700000000000,
            exit_price=3090.0,
            exit_eff_allin=3095.0,  # 3090 + costs
            exit_qty=5.0,
            exit_ts_utc_ms=1700001800000,  # +30 min
            exit_reason=ExitReason.STOP_LOSS,
            risk_amount_usd=525.0,
            risk_pct_equity=0.0105,
            sl_eff_allin=3090.0,
            tp_eff_allin=2880.0,
            gross_pnl_usd=-450.0,  # 5 * (3000 - 3090)
            net_pnl_usd=-550.0,  # 5 * (2985 - 3095)
            funding_pnl_usd=1.0,
            commission_usd=100.0,
            equity_before_usd=50000.0,
        )

    def test_trade_creation_winner(self, valid_trade_winner: Trade) -> None:
        """Создание прибыльной сделки"""
        trade = valid_trade_winner
        assert trade.trade_id == "trade_001"
        assert trade.direction == TradeDirection.LONG
        assert trade.net_pnl_usd == 450.0
        assert trade.exit_reason == ExitReason.TAKE_PROFIT

    def test_trade_creation_loser(self, valid_trade_loser: Trade) -> None:
        """Создание убыточной сделки"""
        trade = valid_trade_loser
        assert trade.trade_id == "trade_002"
        assert trade.direction == TradeDirection.SHORT
        assert trade.net_pnl_usd == -550.0
        assert trade.exit_reason == ExitReason.STOP_LOSS

    def test_trade_immutable(self, valid_trade_winner: Trade) -> None:
        """Trade должен быть immutable (frozen=True)"""
        with pytest.raises(ValidationError):
            valid_trade_winner.net_pnl_usd = 1000.0  # type: ignore

    def test_trade_r_value_winner(self, valid_trade_winner: Trade) -> None:
        """Расчёт R-value для прибыльной сделки"""
        # R = 450 / 275 ≈ 1.636R
        r_val = valid_trade_winner.r_value()
        expected = 450.0 / 275.0
        assert abs(r_val - expected) < 1e-9

    def test_trade_r_value_loser(self, valid_trade_loser: Trade) -> None:
        """Расчёт R-value для убыточной сделки (SL hit ≈ -1R)"""
        # R = -550 / 525 ≈ -1.048R (близко к -1R для SL hit)
        r_val = valid_trade_loser.r_value()
        expected = -550.0 / 525.0
        assert abs(r_val - expected) < 1e-9
        assert -1.1 < r_val < -0.95  # Приблизительно -1R

    def test_trade_holding_time(self, valid_trade_winner: Trade) -> None:
        """Расчёт времени удержания в часах"""
        # Entry: 1700000000000, Exit: 1700003600000 (+3600000 ms = +1 hour)
        holding_hours = valid_trade_winner.holding_time_hours()
        assert abs(holding_hours - 1.0) < 1e-9

    def test_trade_is_winner(self, valid_trade_winner: Trade) -> None:
        """Проверка прибыльной сделки"""
        assert valid_trade_winner.is_winner()
        assert not valid_trade_winner.is_loser()
        assert not valid_trade_winner.is_breakeven()

    def test_trade_is_loser(self, valid_trade_loser: Trade) -> None:
        """Проверка убыточной сделки"""
        assert valid_trade_loser.is_loser()
        assert not valid_trade_loser.is_winner()
        assert not valid_trade_loser.is_breakeven()

    def test_trade_is_breakeven(self) -> None:
        """Проверка сделки в безубытке"""
        trade_be = Trade(
            trade_id="trade_be",
            instrument="BTCUSDT",
            cluster_id="crypto",
            direction=TradeDirection.LONG,
            entry_price=50000.0,
            entry_eff_allin=50050.0,
            entry_qty=0.5,
            entry_ts_utc_ms=1700000000000,
            exit_price=50100.0,
            exit_eff_allin=50050.0,  # Break-even after costs
            exit_qty=0.5,
            exit_ts_utc_ms=1700003600000,
            exit_reason=ExitReason.MANUAL,
            risk_amount_usd=275.0,
            risk_pct_equity=0.0055,
            sl_eff_allin=49500.0,
            tp_eff_allin=51000.0,
            gross_pnl_usd=50.0,
            net_pnl_usd=0.0,  # Break-even
            funding_pnl_usd=0.0,
            commission_usd=50.0,
            equity_before_usd=50000.0,
        )
        assert trade_be.is_breakeven()
        assert not trade_be.is_winner()
        assert not trade_be.is_loser()

    def test_trade_exit_before_entry_validation(self) -> None:
        """Валидация: выход не может быть раньше входа"""
        with pytest.raises(ValidationError) as exc_info:
            Trade(
                trade_id="invalid",
                instrument="BTCUSDT",
                cluster_id="crypto",
                direction=TradeDirection.LONG,
                entry_price=50000.0,
                entry_eff_allin=50050.0,
                entry_qty=0.5,
                entry_ts_utc_ms=1700003600000,  # Later time
                exit_price=51000.0,
                exit_eff_allin=50950.0,
                exit_qty=0.5,
                exit_ts_utc_ms=1700000000000,  # Earlier time - INVALID
                exit_reason=ExitReason.TAKE_PROFIT,
                risk_amount_usd=275.0,
                risk_pct_equity=0.0055,
                sl_eff_allin=49500.0,
                tp_eff_allin=50950.0,
                gross_pnl_usd=450.0,
                net_pnl_usd=450.0,
                funding_pnl_usd=0.0,
                commission_usd=0.0,
                equity_before_usd=50000.0,
            )
        assert "exit_ts_utc_ms" in str(exc_info.value).lower()

    def test_trade_partial_close_validation(self) -> None:
        """Валидация: частичное закрытие пока не поддерживается"""
        with pytest.raises(ValidationError) as exc_info:
            Trade(
                trade_id="partial",
                instrument="BTCUSDT",
                cluster_id="crypto",
                direction=TradeDirection.LONG,
                entry_price=50000.0,
                entry_eff_allin=50050.0,
                entry_qty=1.0,  # Entry: 1.0
                entry_ts_utc_ms=1700000000000,
                exit_price=51000.0,
                exit_eff_allin=50950.0,
                exit_qty=0.5,  # Exit: 0.5 - PARTIAL CLOSE NOT SUPPORTED
                exit_ts_utc_ms=1700003600000,
                exit_reason=ExitReason.MANUAL,
                risk_amount_usd=275.0,
                risk_pct_equity=0.0055,
                sl_eff_allin=49500.0,
                tp_eff_allin=50950.0,
                gross_pnl_usd=450.0,
                net_pnl_usd=450.0,
                funding_pnl_usd=0.0,
                commission_usd=0.0,
                equity_before_usd=50000.0,
            )
        assert "exit_qty" in str(exc_info.value).lower()

    def test_trade_json_serialization(self, valid_trade_winner: Trade) -> None:
        """Сериализация Trade в JSON и обратно"""
        # Serialize
        json_str = valid_trade_winner.model_dump_json()
        data = json.loads(json_str)

        # Validate JSON structure
        assert data["trade_id"] == "trade_001"
        assert data["direction"] == "long"
        assert data["exit_reason"] == "take_profit"

        # Deserialize
        restored = Trade.model_validate_json(json_str)
        assert restored == valid_trade_winner


# =============================================================================
# SIGNAL TESTS
# =============================================================================


class TestSignal:
    """Тесты для модели Signal"""

    @pytest.fixture
    def valid_signal_long(self) -> Signal:
        """Валидный LONG сигнал от TREND движка"""
        return Signal(
            instrument="BTCUSDT",
            engine=EngineType.TREND,
            direction=SignalDirection.LONG,
            signal_ts_utc_ms=1700000000000,
            levels=SignalLevels(
                entry_price=50000.0,
                stop_loss=49500.0,  # -500 pts
                take_profit=51500.0,  # +1500 pts, RR=3
            ),
            context=SignalContext(
                expected_holding_hours=24.0,
                regime_hint="strong_trend_up",
                setup_id="trend_breakout_001",
            ),
            constraints=SignalConstraints(
                RR_min_engine=2.0,
                sl_min_atr_mult=1.5,
                sl_max_atr_mult=4.0,
            ),
        )

    @pytest.fixture
    def valid_signal_short(self) -> Signal:
        """Валидный SHORT сигнал от RANGE движка"""
        return Signal(
            instrument="ETHUSDT",
            engine=EngineType.RANGE,
            direction=SignalDirection.SHORT,
            signal_ts_utc_ms=1700000000000,
            levels=SignalLevels(
                entry_price=3000.0,
                stop_loss=3090.0,  # +90 pts
                take_profit=2820.0,  # -180 pts, RR=2
            ),
            context=SignalContext(
                expected_holding_hours=12.0,
                regime_hint="range_resistance",
                setup_id="range_reversal_002",
            ),
            constraints=SignalConstraints(
                RR_min_engine=1.5,
                sl_min_atr_mult=1.0,
                sl_max_atr_mult=3.0,
            ),
        )

    def test_signal_creation_long(self, valid_signal_long: Signal) -> None:
        """Создание LONG сигнала"""
        sig = valid_signal_long
        assert sig.instrument == "BTCUSDT"
        assert sig.engine == EngineType.TREND
        assert sig.direction == SignalDirection.LONG
        assert sig.levels.entry_price == 50000.0

    def test_signal_creation_short(self, valid_signal_short: Signal) -> None:
        """Создание SHORT сигнала"""
        sig = valid_signal_short
        assert sig.instrument == "ETHUSDT"
        assert sig.engine == EngineType.RANGE
        assert sig.direction == SignalDirection.SHORT

    def test_signal_immutable(self, valid_signal_long: Signal) -> None:
        """Signal должен быть immutable (frozen=True)"""
        with pytest.raises(ValidationError):
            valid_signal_long.instrument = "ETHUSDT"  # type: ignore

    def test_signal_nested_immutable(self, valid_signal_long: Signal) -> None:
        """Вложенные модели также должны быть immutable"""
        with pytest.raises(ValidationError):
            valid_signal_long.levels.entry_price = 60000.0  # type: ignore

    def test_signal_potential_profit_long(self, valid_signal_long: Signal) -> None:
        """Расчёт потенциальной прибыли для LONG"""
        # TP - entry = 51500 - 50000 = 1500
        profit = valid_signal_long.potential_profit()
        assert profit == 1500.0

    def test_signal_potential_loss_long(self, valid_signal_long: Signal) -> None:
        """Расчёт потенциального убытка для LONG"""
        # entry - SL = 50000 - 49500 = 500
        loss = valid_signal_long.potential_loss()
        assert loss == 500.0

    def test_signal_raw_rr_long(self, valid_signal_long: Signal) -> None:
        """Расчёт raw RR для LONG"""
        # RR = profit / loss = 1500 / 500 = 3.0
        rr = valid_signal_long.raw_rr()
        assert abs(rr - 3.0) < 1e-9

    def test_signal_raw_rr_short(self, valid_signal_short: Signal) -> None:
        """Расчёт raw RR для SHORT"""
        # profit = |3000 - 2820| = 180
        # loss = |3000 - 3090| = 90
        # RR = 180 / 90 = 2.0
        rr = valid_signal_short.raw_rr()
        assert abs(rr - 2.0) < 1e-9

    def test_signal_validate_rr_constraint_pass(self, valid_signal_long: Signal) -> None:
        """Проверка RR constraint: RR=3.0 >= RR_min_engine=2.0"""
        assert valid_signal_long.validate_rr_constraint()

    def test_signal_validate_rr_constraint_fail(self) -> None:
        """Проверка RR constraint: сигнал с RR < RR_min_engine"""
        signal_low_rr = Signal(
            instrument="BTCUSDT",
            engine=EngineType.TREND,
            direction=SignalDirection.LONG,
            signal_ts_utc_ms=1700000000000,
            levels=SignalLevels(
                entry_price=50000.0,
                stop_loss=49500.0,  # -500
                take_profit=50700.0,  # +700, RR=1.4
            ),
            context=SignalContext(
                expected_holding_hours=24.0,
                regime_hint="weak_trend",
                setup_id="low_rr_setup",
            ),
            constraints=SignalConstraints(
                RR_min_engine=2.0,  # Required RR=2.0
                sl_min_atr_mult=1.5,
                sl_max_atr_mult=4.0,
            ),
        )
        # RR=1.4 < 2.0 - should fail constraint
        assert not signal_low_rr.validate_rr_constraint()

    def test_signal_long_levels_validation_tp_below_entry(self) -> None:
        """Валидация LONG: TP должен быть выше entry"""
        with pytest.raises(ValidationError) as exc_info:
            Signal(
                instrument="BTCUSDT",
                engine=EngineType.TREND,
                direction=SignalDirection.LONG,
                signal_ts_utc_ms=1700000000000,
                levels=SignalLevels(
                    entry_price=50000.0,
                    stop_loss=49500.0,
                    take_profit=49000.0,  # INVALID: TP < entry for LONG
                ),
                context=SignalContext(
                    expected_holding_hours=24.0,
                    regime_hint=None,
                    setup_id="invalid_tp",
                ),
                constraints=SignalConstraints(
                    RR_min_engine=2.0,
                    sl_min_atr_mult=1.5,
                    sl_max_atr_mult=4.0,
                ),
            )
        assert "take_profit" in str(exc_info.value).lower()

    def test_signal_long_levels_validation_sl_above_entry(self) -> None:
        """Валидация LONG: SL должен быть ниже entry"""
        with pytest.raises(ValidationError) as exc_info:
            Signal(
                instrument="BTCUSDT",
                engine=EngineType.TREND,
                direction=SignalDirection.LONG,
                signal_ts_utc_ms=1700000000000,
                levels=SignalLevels(
                    entry_price=50000.0,
                    stop_loss=50500.0,  # INVALID: SL > entry for LONG
                    take_profit=51500.0,
                ),
                context=SignalContext(
                    expected_holding_hours=24.0,
                    regime_hint=None,
                    setup_id="invalid_sl",
                ),
                constraints=SignalConstraints(
                    RR_min_engine=2.0,
                    sl_min_atr_mult=1.5,
                    sl_max_atr_mult=4.0,
                ),
            )
        assert "stop_loss" in str(exc_info.value).lower()

    def test_signal_short_levels_validation_tp_above_entry(self) -> None:
        """Валидация SHORT: TP должен быть ниже entry"""
        with pytest.raises(ValidationError) as exc_info:
            Signal(
                instrument="ETHUSDT",
                engine=EngineType.RANGE,
                direction=SignalDirection.SHORT,
                signal_ts_utc_ms=1700000000000,
                levels=SignalLevels(
                    entry_price=3000.0,
                    stop_loss=3090.0,
                    take_profit=3100.0,  # INVALID: TP > entry for SHORT
                ),
                context=SignalContext(
                    expected_holding_hours=12.0,
                    regime_hint=None,
                    setup_id="invalid_tp_short",
                ),
                constraints=SignalConstraints(
                    RR_min_engine=1.5,
                    sl_min_atr_mult=1.0,
                    sl_max_atr_mult=3.0,
                ),
            )
        assert "take_profit" in str(exc_info.value).lower()

    def test_signal_short_levels_validation_sl_below_entry(self) -> None:
        """Валидация SHORT: SL должен быть выше entry"""
        with pytest.raises(ValidationError) as exc_info:
            Signal(
                instrument="ETHUSDT",
                engine=EngineType.RANGE,
                direction=SignalDirection.SHORT,
                signal_ts_utc_ms=1700000000000,
                levels=SignalLevels(
                    entry_price=3000.0,
                    stop_loss=2900.0,  # INVALID: SL < entry for SHORT
                    take_profit=2820.0,
                ),
                context=SignalContext(
                    expected_holding_hours=12.0,
                    regime_hint=None,
                    setup_id="invalid_sl_short",
                ),
                constraints=SignalConstraints(
                    RR_min_engine=1.5,
                    sl_min_atr_mult=1.0,
                    sl_max_atr_mult=3.0,
                ),
            )
        assert "stop_loss" in str(exc_info.value).lower()

    def test_signal_constraints_sl_max_validation(self) -> None:
        """Валидация: sl_max_atr_mult должен быть больше sl_min_atr_mult"""
        with pytest.raises(ValidationError) as exc_info:
            Signal(
                instrument="BTCUSDT",
                engine=EngineType.TREND,
                direction=SignalDirection.LONG,
                signal_ts_utc_ms=1700000000000,
                levels=SignalLevels(
                    entry_price=50000.0,
                    stop_loss=49500.0,
                    take_profit=51500.0,
                ),
                context=SignalContext(
                    expected_holding_hours=24.0,
                    regime_hint=None,
                    setup_id="invalid_constraints",
                ),
                constraints=SignalConstraints(
                    RR_min_engine=2.0,
                    sl_min_atr_mult=3.0,
                    sl_max_atr_mult=2.0,  # INVALID: max < min
                ),
            )
        assert "sl_max_atr_mult" in str(exc_info.value).lower()

    def test_signal_json_serialization(self, valid_signal_long: Signal) -> None:
        """Сериализация Signal в JSON и обратно"""
        # Serialize
        json_str = valid_signal_long.model_dump_json()
        data = json.loads(json_str)

        # Validate JSON structure
        assert data["instrument"] == "BTCUSDT"
        assert data["engine"] == "TREND"
        assert data["direction"] == "long"
        assert data["levels"]["entry_price"] == 50000.0

        # Deserialize
        restored = Signal.model_validate_json(json_str)
        assert restored == valid_signal_long


# =============================================================================
# CROSS-MODEL INTEGRATION TESTS
# =============================================================================


class TestCrossModelIntegration:
    """Интеграционные тесты между моделями"""

    def test_signal_to_position_workflow(self) -> None:
        """Тестирование workflow: Signal → Position"""
        # 1. Создаём сигнал
        signal = Signal(
            instrument="BTCUSDT",
            engine=EngineType.TREND,
            direction=SignalDirection.LONG,
            signal_ts_utc_ms=1700000000000,
            levels=SignalLevels(entry_price=50000.0, stop_loss=49500.0, take_profit=51500.0),
            context=SignalContext(
                expected_holding_hours=24.0, regime_hint="trend", setup_id="setup_001"
            ),
            constraints=SignalConstraints(RR_min_engine=2.0, sl_min_atr_mult=1.5, sl_max_atr_mult=4.0),
        )

        # 2. "Открываем" позицию на основе сигнала
        position = Position(
            instrument=signal.instrument,
            cluster_id="crypto_major",
            direction=PositionDirection(signal.direction.value),
            qty=0.5,
            entry_price=signal.levels.entry_price,
            entry_eff_allin=50050.0,  # +costs
            sl_eff_allin=49500.0,  # signal.levels.stop_loss with costs
            risk_amount_usd=275.0,
            risk_pct_equity=0.0055,
            notional_usd=25000.0,
            unrealized_pnl_usd=0.0,
            funding_pnl_usd=0.0,
            opened_ts_utc_ms=signal.signal_ts_utc_ms + 1000,  # Opened shortly after signal
        )

        # Verify consistency
        assert position.instrument == signal.instrument
        assert position.direction.value == signal.direction.value
        assert position.entry_price == signal.levels.entry_price

    def test_position_to_trade_workflow(self) -> None:
        """Тестирование workflow: Position → Trade (закрытие позиции)"""
        # 1. Открытая позиция
        position = Position(
            instrument="BTCUSDT",
            cluster_id="crypto_major",
            direction=PositionDirection.LONG,
            qty=0.5,
            entry_price=50000.0,
            entry_eff_allin=50050.0,
            sl_eff_allin=49500.0,
            risk_amount_usd=275.0,
            risk_pct_equity=0.0055,
            notional_usd=25000.0,
            unrealized_pnl_usd=450.0,
            funding_pnl_usd=-2.0,
            opened_ts_utc_ms=1700000000000,
        )

        # 2. "Закрываем" позицию, создаём Trade
        trade = Trade(
            trade_id="trade_from_position",
            instrument=position.instrument,
            cluster_id=position.cluster_id,
            direction=TradeDirection(position.direction.value),
            entry_price=position.entry_price,
            entry_eff_allin=position.entry_eff_allin,
            entry_qty=position.qty,
            entry_ts_utc_ms=position.opened_ts_utc_ms,
            exit_price=51000.0,
            exit_eff_allin=50950.0,
            exit_qty=position.qty,
            exit_ts_utc_ms=position.opened_ts_utc_ms + 3600000,  # +1 hour
            exit_reason=ExitReason.TAKE_PROFIT,
            risk_amount_usd=position.risk_amount_usd,
            risk_pct_equity=position.risk_pct_equity,
            sl_eff_allin=position.sl_eff_allin,
            tp_eff_allin=50950.0,
            gross_pnl_usd=500.0,
            net_pnl_usd=position.unrealized_pnl_usd + position.funding_pnl_usd,
            funding_pnl_usd=position.funding_pnl_usd,
            commission_usd=50.0,
            equity_before_usd=50000.0,
        )

        # Verify consistency
        assert trade.instrument == position.instrument
        assert trade.entry_price == position.entry_price
        assert trade.risk_amount_usd == position.risk_amount_usd
        assert trade.net_pnl_usd == position.total_pnl_usd()
