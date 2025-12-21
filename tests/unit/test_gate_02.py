"""Тесты для GATE 2: MRC Confidence + Baseline + Conflict Resolution

ТЗ 3.3.2 строка 1019 (GATE 2)
ТЗ 3.3.3 строки 1066-1111 (MRC/Baseline logic, probe-режим)

Покрытие:
- Все варианты MRC/Baseline сочетаний (~20 тестов)
- Probe-режим при конфликте трендов (~5 тестов)
- Conflict sustained diagnostic block (~3 теста)
- GATE 0-1 integration (~5 тестов)
- Edge cases (~5 тестов)
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
from src.gatekeeper.gates import (
    Gate00Result,
    Gate01Result,
    Gate02Config,
    Gate02MRCConfidence,
)


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def gate02():
    """GATE 2 с дефолтной конфигурацией."""
    return Gate02MRCConfidence()


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
def good_market_conditions():
    """Хорошие рыночные условия для probe-режима."""
    return {
        "dqs": 0.85,
        "depth_bid_usd": 100000.0,
        "depth_ask_usd": 100000.0,
        "spread_bps": 3.0,
        "mle_decision_strong_or_normal": True,
        "conflict_count_in_window": 0
    }


# =============================================================================
# ТЕСТЫ: MRC/Baseline Agreement (нет конфликта)
# =============================================================================


def test_gate02_trend_up_agreement(gate02, gate00_pass, gate01_pass, good_market_conditions):
    """PASS: MRC=TREND_UP, Baseline=TREND_UP (согласие)."""
    mrc = MRCResult(mrc_class=MRCClass.TREND_UP, confidence=0.80)
    baseline = BaselineResult(baseline_class=BaselineClass.TREND_UP)
    
    result = gate02.evaluate(
        gate00_result=gate00_pass,
        gate01_result=gate01_pass,
        mrc_result=mrc,
        baseline_result=baseline,
        **good_market_conditions
    )
    
    assert result.entry_allowed is True
    assert result.final_regime == FinalRegime.TREND_UP
    assert result.conflict_info is None
    assert result.is_probe_mode is False
    assert result.regime_risk_mult == 1.0


def test_gate02_trend_down_agreement(gate02, gate00_pass, gate01_pass, good_market_conditions):
    """PASS: MRC=TREND_DOWN, Baseline=TREND_DOWN (согласие)."""
    mrc = MRCResult(mrc_class=MRCClass.TREND_DOWN, confidence=0.75)
    baseline = BaselineResult(baseline_class=BaselineClass.TREND_DOWN)
    
    result = gate02.evaluate(
        gate00_result=gate00_pass,
        gate01_result=gate01_pass,
        mrc_result=mrc,
        baseline_result=baseline,
        **good_market_conditions
    )
    
    assert result.entry_allowed is True
    assert result.final_regime == FinalRegime.TREND_DOWN
    assert result.conflict_info is None
    assert result.is_probe_mode is False
    assert result.regime_risk_mult == 1.0


def test_gate02_range_agreement(gate02, gate00_pass, gate01_pass, good_market_conditions):
    """PASS: MRC=RANGE, Baseline=RANGE (согласие)."""
    mrc = MRCResult(mrc_class=MRCClass.RANGE, confidence=0.70)
    baseline = BaselineResult(baseline_class=BaselineClass.RANGE)
    
    result = gate02.evaluate(
        gate00_result=gate00_pass,
        gate01_result=gate01_pass,
        mrc_result=mrc,
        baseline_result=baseline,
        **good_market_conditions
    )
    
    assert result.entry_allowed is True
    assert result.final_regime == FinalRegime.RANGE
    assert result.conflict_info is None
    assert result.is_probe_mode is False
    assert result.regime_risk_mult == 1.0


# =============================================================================
# ТЕСТЫ: MRC=NOISE
# =============================================================================


def test_gate02_mrc_noise_baseline_trend(gate02, gate00_pass, gate01_pass, good_market_conditions):
    """BLOCK: MRC=NOISE, Baseline=TREND_UP → NO_TRADE."""
    mrc = MRCResult(mrc_class=MRCClass.NOISE, confidence=0.60)
    baseline = BaselineResult(baseline_class=BaselineClass.TREND_UP)
    
    result = gate02.evaluate(
        gate00_result=gate00_pass,
        gate01_result=gate01_pass,
        mrc_result=mrc,
        baseline_result=baseline,
        **good_market_conditions
    )
    
    assert result.entry_allowed is False
    assert result.block_reason == "regime_no_trade"
    assert result.final_regime == FinalRegime.NO_TRADE
    assert result.conflict_info is not None
    assert result.conflict_info.conflict_type == "mrc_noise"


def test_gate02_mrc_noise_baseline_range_exception(gate02, gate00_pass, gate01_pass, good_market_conditions):
    """PASS: MRC=NOISE, Baseline=RANGE → RANGE (exception, reduced risk)."""
    mrc = MRCResult(mrc_class=MRCClass.NOISE, confidence=0.55)
    baseline = BaselineResult(baseline_class=BaselineClass.RANGE)
    
    result = gate02.evaluate(
        gate00_result=gate00_pass,
        gate01_result=gate01_pass,
        mrc_result=mrc,
        baseline_result=baseline,
        **good_market_conditions
    )
    
    assert result.entry_allowed is True
    assert result.final_regime == FinalRegime.RANGE
    assert result.conflict_info is not None
    assert result.conflict_info.conflict_type == "noise_range_exception"
    assert result.regime_risk_mult == 0.50  # noise_override_risk_mult


# =============================================================================
# ТЕСТЫ: Baseline=NOISE
# =============================================================================


def test_gate02_baseline_noise_low_conf_mrc(gate02, gate00_pass, gate01_pass, good_market_conditions):
    """BLOCK: Baseline=NOISE, MRC confidence < very_high → NO_TRADE."""
    mrc = MRCResult(mrc_class=MRCClass.TREND_UP, confidence=0.75)  # < 0.85
    baseline = BaselineResult(baseline_class=BaselineClass.NOISE)
    
    result = gate02.evaluate(
        gate00_result=gate00_pass,
        gate01_result=gate01_pass,
        mrc_result=mrc,
        baseline_result=baseline,
        **good_market_conditions
    )
    
    assert result.entry_allowed is False
    assert result.block_reason == "regime_no_trade"
    assert result.final_regime == FinalRegime.NO_TRADE
    assert result.conflict_info.conflict_type == "baseline_noise"


def test_gate02_baseline_noise_very_high_conf_mrc_trend(gate02, gate00_pass, gate01_pass, good_market_conditions):
    """PASS: Baseline=NOISE, MRC TREND_UP very high conf → TREND_UP (reduced risk)."""
    mrc = MRCResult(mrc_class=MRCClass.TREND_UP, confidence=0.90)  # >= 0.85
    baseline = BaselineResult(baseline_class=BaselineClass.NOISE)
    
    result = gate02.evaluate(
        gate00_result=gate00_pass,
        gate01_result=gate01_pass,
        mrc_result=mrc,
        baseline_result=baseline,
        **good_market_conditions
    )
    
    assert result.entry_allowed is True
    assert result.final_regime == FinalRegime.TREND_UP
    assert result.conflict_info.conflict_type == "baseline_noise_override"
    assert result.regime_risk_mult == 0.50  # noise_override_risk_mult


def test_gate02_baseline_noise_very_high_conf_mrc_breakout(gate02, gate00_pass, gate01_pass, good_market_conditions):
    """PASS: Baseline=NOISE, MRC BREAKOUT_DOWN very high conf → BREAKOUT_DOWN (reduced risk)."""
    mrc = MRCResult(mrc_class=MRCClass.BREAKOUT_DOWN, confidence=0.88)
    baseline = BaselineResult(baseline_class=BaselineClass.NOISE)
    
    result = gate02.evaluate(
        gate00_result=gate00_pass,
        gate01_result=gate01_pass,
        mrc_result=mrc,
        baseline_result=baseline,
        **good_market_conditions
    )
    
    assert result.entry_allowed is True
    assert result.final_regime == FinalRegime.BREAKOUT_DOWN
    assert result.regime_risk_mult == 0.50


# =============================================================================
# ТЕСТЫ: MRC=RANGE, Baseline=TREND
# =============================================================================


def test_gate02_mrc_range_baseline_trend_up(gate02, gate00_pass, gate01_pass, good_market_conditions):
    """PASS: MRC=RANGE, Baseline=TREND_UP → RANGE."""
    mrc = MRCResult(mrc_class=MRCClass.RANGE, confidence=0.72)
    baseline = BaselineResult(baseline_class=BaselineClass.TREND_UP)
    
    result = gate02.evaluate(
        gate00_result=gate00_pass,
        gate01_result=gate01_pass,
        mrc_result=mrc,
        baseline_result=baseline,
        **good_market_conditions
    )
    
    assert result.entry_allowed is True
    assert result.final_regime == FinalRegime.RANGE
    assert result.conflict_info.conflict_type == "range_vs_trend"
    assert result.regime_risk_mult == 1.0


# =============================================================================
# ТЕСТЫ: MRC=TREND, Baseline=RANGE → BREAKOUT
# =============================================================================


def test_gate02_mrc_trend_up_baseline_range(gate02, gate00_pass, gate01_pass, good_market_conditions):
    """PASS: MRC=TREND_UP, Baseline=RANGE → BREAKOUT_UP (reduced risk)."""
    mrc = MRCResult(mrc_class=MRCClass.TREND_UP, confidence=0.78)
    baseline = BaselineResult(baseline_class=BaselineClass.RANGE)
    
    result = gate02.evaluate(
        gate00_result=gate00_pass,
        gate01_result=gate01_pass,
        mrc_result=mrc,
        baseline_result=baseline,
        **good_market_conditions
    )
    
    assert result.entry_allowed is True
    assert result.final_regime == FinalRegime.BREAKOUT_UP
    assert result.conflict_info.conflict_type == "trend_vs_range"
    assert result.regime_risk_mult == 0.75


def test_gate02_mrc_trend_down_baseline_range(gate02, gate00_pass, gate01_pass, good_market_conditions):
    """PASS: MRC=TREND_DOWN, Baseline=RANGE → BREAKOUT_DOWN (reduced risk)."""
    mrc = MRCResult(mrc_class=MRCClass.TREND_DOWN, confidence=0.80)
    baseline = BaselineResult(baseline_class=BaselineClass.RANGE)
    
    result = gate02.evaluate(
        gate00_result=gate00_pass,
        gate01_result=gate01_pass,
        mrc_result=mrc,
        baseline_result=baseline,
        **good_market_conditions
    )
    
    assert result.entry_allowed is True
    assert result.final_regime == FinalRegime.BREAKOUT_DOWN
    assert result.regime_risk_mult == 0.75


# =============================================================================
# ТЕСТЫ: MRC=BREAKOUT, Baseline=RANGE
# =============================================================================


def test_gate02_mrc_breakout_up_baseline_range(gate02, gate00_pass, gate01_pass, good_market_conditions):
    """PASS: MRC=BREAKOUT_UP, Baseline=RANGE → BREAKOUT_UP."""
    mrc = MRCResult(mrc_class=MRCClass.BREAKOUT_UP, confidence=0.82)
    baseline = BaselineResult(baseline_class=BaselineClass.RANGE)
    
    result = gate02.evaluate(
        gate00_result=gate00_pass,
        gate01_result=gate01_pass,
        mrc_result=mrc,
        baseline_result=baseline,
        **good_market_conditions
    )
    
    assert result.entry_allowed is True
    assert result.final_regime == FinalRegime.BREAKOUT_UP
    assert result.conflict_info.conflict_type == "breakout_vs_range"


# =============================================================================
# ТЕСТЫ: MRC=BREAKOUT, Baseline=TREND
# =============================================================================


def test_gate02_mrc_breakout_up_baseline_trend_up_aligned(gate02, gate00_pass, gate01_pass, good_market_conditions):
    """PASS: MRC=BREAKOUT_UP, Baseline=TREND_UP → BREAKOUT_UP (знак совпадает)."""
    mrc = MRCResult(mrc_class=MRCClass.BREAKOUT_UP, confidence=0.85)
    baseline = BaselineResult(baseline_class=BaselineClass.TREND_UP)
    
    result = gate02.evaluate(
        gate00_result=gate00_pass,
        gate01_result=gate01_pass,
        mrc_result=mrc,
        baseline_result=baseline,
        **good_market_conditions
    )
    
    assert result.entry_allowed is True
    assert result.final_regime == FinalRegime.BREAKOUT_UP
    assert result.conflict_info is None or result.conflict_info.conflict_type == "breakout_trend_aligned"


def test_gate02_mrc_breakout_up_baseline_trend_down_conflict(gate02, gate00_pass, gate01_pass, good_market_conditions):
    """BLOCK: MRC=BREAKOUT_UP, Baseline=TREND_DOWN → NO_TRADE (знак не совпадает)."""
    mrc = MRCResult(mrc_class=MRCClass.BREAKOUT_UP, confidence=0.80)
    baseline = BaselineResult(baseline_class=BaselineClass.TREND_DOWN)
    
    result = gate02.evaluate(
        gate00_result=gate00_pass,
        gate01_result=gate01_pass,
        mrc_result=mrc,
        baseline_result=baseline,
        **good_market_conditions
    )
    
    assert result.entry_allowed is False
    assert result.final_regime == FinalRegime.NO_TRADE
    assert result.conflict_info.conflict_type == "breakout_trend_conflict"


def test_gate02_mrc_breakout_down_baseline_trend_down_aligned(gate02, gate00_pass, gate01_pass, good_market_conditions):
    """PASS: MRC=BREAKOUT_DOWN, Baseline=TREND_DOWN → BREAKOUT_DOWN (знак совпадает)."""
    mrc = MRCResult(mrc_class=MRCClass.BREAKOUT_DOWN, confidence=0.83)
    baseline = BaselineResult(baseline_class=BaselineClass.TREND_DOWN)
    
    result = gate02.evaluate(
        gate00_result=gate00_pass,
        gate01_result=gate01_pass,
        mrc_result=mrc,
        baseline_result=baseline,
        **good_market_conditions
    )
    
    assert result.entry_allowed is True
    assert result.final_regime == FinalRegime.BREAKOUT_DOWN


# =============================================================================
# ТЕСТЫ: Probe-режим при конфликте трендов
# =============================================================================


def test_gate02_probe_mode_trend_conflict_all_conditions_met(gate02, gate00_pass, gate01_pass):
    """PASS: MRC=TREND_UP vs Baseline=TREND_DOWN → PROBE_TRADE (все условия выполнены)."""
    mrc = MRCResult(mrc_class=MRCClass.TREND_UP, confidence=0.90)  # >= 0.85
    baseline = BaselineResult(baseline_class=BaselineClass.TREND_DOWN)
    
    result = gate02.evaluate(
        gate00_result=gate00_pass,
        gate01_result=gate01_pass,
        mrc_result=mrc,
        baseline_result=baseline,
        dqs=0.75,  # >= 0.70
        depth_bid_usd=60000.0,  # >= 50000
        depth_ask_usd=70000.0,  # >= 50000
        spread_bps=4.5,  # <= 5.0
        mle_decision_strong_or_normal=True,
        conflict_count_in_window=0
    )
    
    assert result.entry_allowed is True
    assert result.final_regime == FinalRegime.PROBE_TRADE
    assert result.is_probe_mode is True
    assert result.regime_risk_mult == 0.33  # probe_risk_mult
    assert result.conflict_info.conflict_type == "trend_vs_trend"
    assert result.conflict_info.is_probe_eligible is True
    assert result.conflict_info.probe_conditions_met is True


def test_gate02_probe_mode_low_mrc_conf(gate02, gate00_pass, gate01_pass):
    """BLOCK: MRC=TREND_UP vs TREND_DOWN, MRC conf < 0.85 → NO_TRADE."""
    mrc = MRCResult(mrc_class=MRCClass.TREND_UP, confidence=0.80)  # < 0.85
    baseline = BaselineResult(baseline_class=BaselineClass.TREND_DOWN)
    
    result = gate02.evaluate(
        gate00_result=gate00_pass,
        gate01_result=gate01_pass,
        mrc_result=mrc,
        baseline_result=baseline,
        dqs=0.75,
        depth_bid_usd=60000.0,
        depth_ask_usd=70000.0,
        spread_bps=4.5,
        mle_decision_strong_or_normal=True,
        conflict_count_in_window=0
    )
    
    assert result.entry_allowed is False
    assert result.final_regime == FinalRegime.NO_TRADE
    assert result.is_probe_mode is False


def test_gate02_probe_mode_low_dqs(gate02, gate00_pass, gate01_pass):
    """BLOCK: MRC vs Baseline conflict, DQS < degraded → NO_TRADE."""
    mrc = MRCResult(mrc_class=MRCClass.TREND_UP, confidence=0.90)
    baseline = BaselineResult(baseline_class=BaselineClass.TREND_DOWN)
    
    result = gate02.evaluate(
        gate00_result=gate00_pass,
        gate01_result=gate01_pass,
        mrc_result=mrc,
        baseline_result=baseline,
        dqs=0.65,  # < 0.70
        depth_bid_usd=60000.0,
        depth_ask_usd=70000.0,
        spread_bps=4.5,
        mle_decision_strong_or_normal=True,
        conflict_count_in_window=0
    )
    
    assert result.entry_allowed is False
    assert result.final_regime == FinalRegime.NO_TRADE


def test_gate02_probe_mode_low_depth(gate02, gate00_pass, gate01_pass):
    """BLOCK: MRC vs Baseline conflict, depth < min → NO_TRADE."""
    mrc = MRCResult(mrc_class=MRCClass.TREND_DOWN, confidence=0.92)
    baseline = BaselineResult(baseline_class=BaselineClass.TREND_UP)
    
    result = gate02.evaluate(
        gate00_result=gate00_pass,
        gate01_result=gate01_pass,
        mrc_result=mrc,
        baseline_result=baseline,
        dqs=0.80,
        depth_bid_usd=40000.0,  # < 50000
        depth_ask_usd=70000.0,
        spread_bps=4.0,
        mle_decision_strong_or_normal=True,
        conflict_count_in_window=0
    )
    
    assert result.entry_allowed is False
    assert result.final_regime == FinalRegime.NO_TRADE


def test_gate02_probe_mode_high_spread(gate02, gate00_pass, gate01_pass):
    """BLOCK: MRC vs Baseline conflict, spread > max → NO_TRADE."""
    mrc = MRCResult(mrc_class=MRCClass.TREND_UP, confidence=0.88)
    baseline = BaselineResult(baseline_class=BaselineClass.TREND_DOWN)
    
    result = gate02.evaluate(
        gate00_result=gate00_pass,
        gate01_result=gate01_pass,
        mrc_result=mrc,
        baseline_result=baseline,
        dqs=0.80,
        depth_bid_usd=60000.0,
        depth_ask_usd=70000.0,
        spread_bps=6.0,  # > 5.0
        mle_decision_strong_or_normal=True,
        conflict_count_in_window=0
    )
    
    assert result.entry_allowed is False
    assert result.final_regime == FinalRegime.NO_TRADE


# =============================================================================
# ТЕСТЫ: Sustained conflict → diagnostic block
# =============================================================================


def test_gate02_sustained_conflict_block(gate02, gate00_pass, gate01_pass, good_market_conditions):
    """BLOCK: Sustained conflict (count >= threshold) → diagnostic block."""
    mrc = MRCResult(mrc_class=MRCClass.TREND_UP, confidence=0.90)
    baseline = BaselineResult(baseline_class=BaselineClass.TREND_DOWN)
    
    # conflict_window_bars=10, conflict_ratio_threshold=0.60
    # threshold = 10 * 0.60 = 6
    conflict_count = 7  # >= 6
    
    result = gate02.evaluate(
        gate00_result=gate00_pass,
        gate01_result=gate01_pass,
        mrc_result=mrc,
        baseline_result=baseline,
        dqs=0.80,
        depth_bid_usd=60000.0,
        depth_ask_usd=70000.0,
        spread_bps=4.0,
        mle_decision_strong_or_normal=True,
        conflict_count_in_window=conflict_count
    )
    
    assert result.entry_allowed is False
    assert result.block_reason == "regime_conflict_sustained"
    assert result.final_regime == FinalRegime.NO_TRADE


def test_gate02_conflict_below_threshold(gate02, gate00_pass, gate01_pass):
    """PASS: Conflict count < threshold → PROBE_TRADE разрешен."""
    mrc = MRCResult(mrc_class=MRCClass.TREND_UP, confidence=0.90)
    baseline = BaselineResult(baseline_class=BaselineClass.TREND_DOWN)
    
    conflict_count = 5  # < 6 (threshold)
    
    result = gate02.evaluate(
        gate00_result=gate00_pass,
        gate01_result=gate01_pass,
        mrc_result=mrc,
        baseline_result=baseline,
        dqs=0.80,
        depth_bid_usd=60000.0,
        depth_ask_usd=70000.0,
        spread_bps=4.0,
        mle_decision_strong_or_normal=True,
        conflict_count_in_window=conflict_count
    )
    
    assert result.entry_allowed is True
    assert result.final_regime == FinalRegime.PROBE_TRADE


# =============================================================================
# ТЕСТЫ: GATE 0-1 integration
# =============================================================================


def test_gate02_gate00_blocked(gate02, gate01_pass, good_market_conditions):
    """BLOCK: GATE 0 заблокировал → GATE 2 также блокирует."""
    gate00_blocked = Gate00Result(
        entry_allowed=False,
        block_reason="hard_gate: critical_staleness",
        dqs_result=None,
        drp_transition=None,
        new_drp_state=DRPState.EMERGENCY,
        new_warmup_bars_remaining=0,
        new_drp_flap_count=0,
        new_hibernate_until_ts_utc_ms=None,
        details="Hard-gate triggered"
    )
    
    mrc = MRCResult(mrc_class=MRCClass.TREND_UP, confidence=0.80)
    baseline = BaselineResult(baseline_class=BaselineClass.TREND_UP)
    
    result = gate02.evaluate(
        gate00_result=gate00_blocked,
        gate01_result=gate01_pass,
        mrc_result=mrc,
        baseline_result=baseline,
        **good_market_conditions
    )
    
    assert result.entry_allowed is False
    assert "gate00_blocked" in result.block_reason


def test_gate02_gate01_blocked(gate02, gate00_pass, good_market_conditions):
    """BLOCK: GATE 1 заблокировал → GATE 2 также блокирует."""
    gate01_blocked = Gate01Result(
        entry_allowed=False,
        block_reason="manual_halt_all_trading",
        drp_state=DRPState.NORMAL,
        trading_mode=TradingMode.LIVE,
        manual_halt_new_entries=False,
        manual_halt_all_trading=True,
        is_shadow_mode=False,
        details="Manual emergency stop"
    )
    
    mrc = MRCResult(mrc_class=MRCClass.TREND_UP, confidence=0.80)
    baseline = BaselineResult(baseline_class=BaselineClass.TREND_UP)
    
    result = gate02.evaluate(
        gate00_result=gate00_pass,
        gate01_result=gate01_blocked,
        mrc_result=mrc,
        baseline_result=baseline,
        **good_market_conditions
    )
    
    assert result.entry_allowed is False
    assert "gate01_blocked" in result.block_reason


# =============================================================================
# ТЕСТЫ: Edge cases
# =============================================================================


def test_gate02_immutability(gate02, gate00_pass, gate01_pass, good_market_conditions):
    """PASS: Gate02Result immutable (frozen=True)."""
    mrc = MRCResult(mrc_class=MRCClass.TREND_UP, confidence=0.80)
    baseline = BaselineResult(baseline_class=BaselineClass.TREND_UP)
    
    result = gate02.evaluate(
        gate00_result=gate00_pass,
        gate01_result=gate01_pass,
        mrc_result=mrc,
        baseline_result=baseline,
        **good_market_conditions
    )
    
    # Попытка модификации должна вызвать ошибку
    with pytest.raises(Exception):  # FrozenInstanceError или AttributeError
        result.entry_allowed = False


def test_gate02_custom_config():
    """PASS: Custom config применяется корректно."""
    custom_config = Gate02Config(
        mrc_very_high_conf_threshold=0.90,
        probe_risk_mult=0.25,
        noise_override_risk_mult=0.40
    )
    
    gate02_custom = Gate02MRCConfidence(config=custom_config)
    
    assert gate02_custom.config.mrc_very_high_conf_threshold == 0.90
    assert gate02_custom.config.probe_risk_mult == 0.25
    assert gate02_custom.config.noise_override_risk_mult == 0.40
