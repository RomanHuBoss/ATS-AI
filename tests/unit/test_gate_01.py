"""Unit тесты для GATE 1: DRP Kill-switch / Manual Halt / Trading Mode.

Coverage:
- Manual halt flags блокировка
- Trading mode проверки (LIVE/SHADOW проходят, PAPER/BACKTEST блокируются)
- DRP state integration с GATE 0
- SHADOW mode indicator
- Integration scenarios
"""

import pytest

from src.gatekeeper.gates.gate_00_warmup_dqs import Gate00Result
from src.gatekeeper.gates.gate_01_drp_killswitch import Gate01DRPKillswitch, Gate01Result
from src.core.domain.portfolio_state import DRPState, TradingMode
from src.drp.state_machine import DRPTransitionResult


@pytest.fixture
def gate01():
    """Fixture для GATE 1."""
    return Gate01DRPKillswitch()


@pytest.fixture
def gate00_pass_result():
    """Fixture для успешного результата GATE 0."""
    return Gate00Result(
        entry_allowed=True,
        block_reason="",
        dqs_result=None,
        drp_transition=DRPTransitionResult(
            new_state=DRPState.NORMAL,
            warmup_bars_remaining=0,
            drp_flap_count=0,
            hibernate_until_ts_utc_ms=None,
            details="NORMAL state"
        ),
        new_drp_state=DRPState.NORMAL,
        new_warmup_bars_remaining=0,
        new_drp_flap_count=0,
        new_hibernate_until_ts_utc_ms=None,
        details="PASS"
    )


@pytest.fixture
def gate00_emergency_result():
    """Fixture для EMERGENCY результата GATE 0."""
    return Gate00Result(
        entry_allowed=False,
        block_reason="emergency_mode",
        dqs_result=None,
        drp_transition=DRPTransitionResult(
            new_state=DRPState.EMERGENCY,
            warmup_bars_remaining=0,
            drp_flap_count=0,
            hibernate_until_ts_utc_ms=None,
            details="EMERGENCY triggered"
        ),
        new_drp_state=DRPState.EMERGENCY,
        new_warmup_bars_remaining=0,
        new_drp_flap_count=0,
        new_hibernate_until_ts_utc_ms=None,
        details="EMERGENCY mode"
    )


# =============================================================================
# PASS SCENARIOS
# =============================================================================


def test_gate01_pass_live_mode(gate01, gate00_pass_result):
    """PASS: LIVE mode, нет manual halt, GATE 0 passed."""
    result = gate01.evaluate(
        gate00_result=gate00_pass_result,
        trading_mode=TradingMode.LIVE,
        manual_halt_new_entries=False,
        manual_halt_all_trading=False
    )
    
    assert result.entry_allowed is True
    assert result.block_reason == ""
    assert result.drp_state == DRPState.NORMAL
    assert result.trading_mode == TradingMode.LIVE
    assert result.is_shadow_mode is False
    assert "PASS" in result.details


def test_gate01_pass_shadow_mode(gate01, gate00_pass_result):
    """PASS: SHADOW mode разрешен в GATE 1 (early exit будет после GATE 6)."""
    result = gate01.evaluate(
        gate00_result=gate00_pass_result,
        trading_mode=TradingMode.SHADOW,
        manual_halt_new_entries=False,
        manual_halt_all_trading=False
    )
    
    assert result.entry_allowed is True
    assert result.block_reason == ""
    assert result.drp_state == DRPState.NORMAL
    assert result.trading_mode == TradingMode.SHADOW
    assert result.is_shadow_mode is True
    assert "SHADOW mode - will exit after GATE 6" in result.details


def test_gate01_pass_defensive_state(gate01):
    """PASS: DEFENSIVE state разрешен (GATE 0 passed)."""
    gate00_result = Gate00Result(
        entry_allowed=True,
        block_reason="",
        dqs_result=None,
        drp_transition=DRPTransitionResult(
            new_state=DRPState.DEFENSIVE,
            warmup_bars_remaining=0,
            drp_flap_count=0,
            hibernate_until_ts_utc_ms=None,
            details="DEFENSIVE state"
        ),
        new_drp_state=DRPState.DEFENSIVE,
        new_warmup_bars_remaining=0,
        new_drp_flap_count=0,
        new_hibernate_until_ts_utc_ms=None,
        details="PASS"
    )
    
    result = gate01.evaluate(
        gate00_result=gate00_result,
        trading_mode=TradingMode.LIVE,
        manual_halt_new_entries=False,
        manual_halt_all_trading=False
    )
    
    assert result.entry_allowed is True
    assert result.drp_state == DRPState.DEFENSIVE


# =============================================================================
# MANUAL HALT FLAGS
# =============================================================================


def test_gate01_block_manual_halt_all_trading(gate01, gate00_pass_result):
    """BLOCK: manual_halt_all_trading флаг."""
    result = gate01.evaluate(
        gate00_result=gate00_pass_result,
        trading_mode=TradingMode.LIVE,
        manual_halt_new_entries=False,
        manual_halt_all_trading=True
    )
    
    assert result.entry_allowed is False
    assert result.block_reason == "manual_halt_all_trading"
    assert result.manual_halt_all_trading is True
    assert "Manual emergency stop" in result.details


def test_gate01_block_manual_halt_new_entries(gate01, gate00_pass_result):
    """BLOCK: manual_halt_new_entries флаг."""
    result = gate01.evaluate(
        gate00_result=gate00_pass_result,
        trading_mode=TradingMode.LIVE,
        manual_halt_new_entries=True,
        manual_halt_all_trading=False
    )
    
    assert result.entry_allowed is False
    assert result.block_reason == "manual_halt_new_entries"
    assert result.manual_halt_new_entries is True
    assert "Manual kill-switch" in result.details


def test_gate01_block_both_manual_halts(gate01, gate00_pass_result):
    """BLOCK: оба manual halt флага (приоритет у manual_halt_all_trading)."""
    result = gate01.evaluate(
        gate00_result=gate00_pass_result,
        trading_mode=TradingMode.LIVE,
        manual_halt_new_entries=True,
        manual_halt_all_trading=True
    )
    
    assert result.entry_allowed is False
    assert result.block_reason == "manual_halt_all_trading"  # Приоритет
    assert result.manual_halt_all_trading is True
    assert result.manual_halt_new_entries is True


def test_gate01_manual_halt_overrides_shadow(gate01, gate00_pass_result):
    """BLOCK: manual halt блокирует даже SHADOW mode."""
    result = gate01.evaluate(
        gate00_result=gate00_pass_result,
        trading_mode=TradingMode.SHADOW,
        manual_halt_new_entries=True,
        manual_halt_all_trading=False
    )
    
    assert result.entry_allowed is False
    assert result.block_reason == "manual_halt_new_entries"
    assert result.is_shadow_mode is True


# =============================================================================
# TRADING MODE CHECKS
# =============================================================================


def test_gate01_block_paper_mode(gate01, gate00_pass_result):
    """BLOCK: PAPER mode блокируется в GATE 1."""
    result = gate01.evaluate(
        gate00_result=gate00_pass_result,
        trading_mode=TradingMode.PAPER,
        manual_halt_new_entries=False,
        manual_halt_all_trading=False
    )
    
    assert result.entry_allowed is False
    assert result.block_reason == "trading_mode_paper"
    assert result.trading_mode == TradingMode.PAPER
    assert "PAPER mode" in result.details


def test_gate01_block_backtest_mode(gate01, gate00_pass_result):
    """BLOCK: BACKTEST mode блокируется в GATE 1."""
    result = gate01.evaluate(
        gate00_result=gate00_pass_result,
        trading_mode=TradingMode.BACKTEST,
        manual_halt_new_entries=False,
        manual_halt_all_trading=False
    )
    
    assert result.entry_allowed is False
    assert result.block_reason == "trading_mode_backtest"
    assert result.trading_mode == TradingMode.BACKTEST
    assert "BACKTEST mode" in result.details


# =============================================================================
# DRP STATE INTEGRATION (GATE 0 results)
# =============================================================================


def test_gate01_block_gate00_emergency(gate01, gate00_emergency_result):
    """BLOCK: GATE 0 заблокировал из-за EMERGENCY state."""
    result = gate01.evaluate(
        gate00_result=gate00_emergency_result,
        trading_mode=TradingMode.LIVE,
        manual_halt_new_entries=False,
        manual_halt_all_trading=False
    )
    
    assert result.entry_allowed is False
    assert result.block_reason == "gate00_blocked: emergency_mode"
    assert result.drp_state == DRPState.EMERGENCY
    assert "GATE 0 blocked" in result.details


def test_gate01_block_gate00_recovery(gate01):
    """BLOCK: GATE 0 заблокировал из-за RECOVERY (warm-up)."""
    gate00_result = Gate00Result(
        entry_allowed=False,
        block_reason="warmup_in_progress",
        dqs_result=None,
        drp_transition=DRPTransitionResult(
            new_state=DRPState.RECOVERY,
            warmup_bars_remaining=3,
            drp_flap_count=0,
            hibernate_until_ts_utc_ms=None,
            details="Warm-up in progress"
        ),
        new_drp_state=DRPState.RECOVERY,
        new_warmup_bars_remaining=3,
        new_drp_flap_count=0,
        new_hibernate_until_ts_utc_ms=None,
        details="Warm-up in progress"
    )
    
    result = gate01.evaluate(
        gate00_result=gate00_result,
        trading_mode=TradingMode.LIVE,
        manual_halt_new_entries=False,
        manual_halt_all_trading=False
    )
    
    assert result.entry_allowed is False
    assert result.block_reason == "gate00_blocked: warmup_in_progress"
    assert result.drp_state == DRPState.RECOVERY


def test_gate01_block_gate00_hibernate(gate01):
    """BLOCK: GATE 0 заблокировал из-за HIBERNATE state."""
    gate00_result = Gate00Result(
        entry_allowed=False,
        block_reason="hibernate_mode",
        dqs_result=None,
        drp_transition=DRPTransitionResult(
            new_state=DRPState.HIBERNATE,
            warmup_bars_remaining=0,
            drp_flap_count=5,
            hibernate_until_ts_utc_ms=1234567890000,
            details="HIBERNATE mode"
        ),
        new_drp_state=DRPState.HIBERNATE,
        new_warmup_bars_remaining=0,
        new_drp_flap_count=5,
        new_hibernate_until_ts_utc_ms=1234567890000,
        details="HIBERNATE mode active"
    )
    
    result = gate01.evaluate(
        gate00_result=gate00_result,
        trading_mode=TradingMode.LIVE,
        manual_halt_new_entries=False,
        manual_halt_all_trading=False
    )
    
    assert result.entry_allowed is False
    assert result.block_reason == "gate00_blocked: hibernate_mode"
    assert result.drp_state == DRPState.HIBERNATE


def test_gate01_block_gate00_hard_gate(gate01):
    """BLOCK: GATE 0 заблокировал из-за hard-gate."""
    gate00_result = Gate00Result(
        entry_allowed=False,
        block_reason="hard_gate: critical_staleness",
        dqs_result=None,
        drp_transition=DRPTransitionResult(
            new_state=DRPState.EMERGENCY,
            warmup_bars_remaining=0,
            drp_flap_count=0,
            hibernate_until_ts_utc_ms=None,
            details="Hard-gate triggered"
        ),
        new_drp_state=DRPState.EMERGENCY,
        new_warmup_bars_remaining=0,
        new_drp_flap_count=0,
        new_hibernate_until_ts_utc_ms=None,
        details="Hard-gate triggered"
    )
    
    result = gate01.evaluate(
        gate00_result=gate00_result,
        trading_mode=TradingMode.LIVE,
        manual_halt_new_entries=False,
        manual_halt_all_trading=False
    )
    
    assert result.entry_allowed is False
    assert result.block_reason == "gate00_blocked: hard_gate: critical_staleness"
    assert "GATE 0 blocked" in result.details


# =============================================================================
# PRIORITY AND EDGE CASES
# =============================================================================


def test_gate01_priority_manual_over_trading_mode(gate01, gate00_pass_result):
    """Priority: manual_halt_new_entries имеет приоритет над trading_mode."""
    result = gate01.evaluate(
        gate00_result=gate00_pass_result,
        trading_mode=TradingMode.LIVE,
        manual_halt_new_entries=True,
        manual_halt_all_trading=False
    )
    
    assert result.entry_allowed is False
    assert result.block_reason == "manual_halt_new_entries"


def test_gate01_priority_manual_over_gate00(gate01, gate00_emergency_result):
    """Priority: manual_halt имеет приоритет над GATE 0 блокировкой."""
    result = gate01.evaluate(
        gate00_result=gate00_emergency_result,
        trading_mode=TradingMode.LIVE,
        manual_halt_new_entries=False,
        manual_halt_all_trading=True
    )
    
    assert result.entry_allowed is False
    assert result.block_reason == "manual_halt_all_trading"  # Не gate00_blocked


def test_gate01_shadow_mode_with_gate00_pass(gate01, gate00_pass_result):
    """SHADOW mode с успешным GATE 0 проходит GATE 1."""
    result = gate01.evaluate(
        gate00_result=gate00_pass_result,
        trading_mode=TradingMode.SHADOW,
        manual_halt_new_entries=False,
        manual_halt_all_trading=False
    )
    
    assert result.entry_allowed is True
    assert result.is_shadow_mode is True
    assert "SHADOW mode" in result.details


def test_gate01_result_immutability(gate01, gate00_pass_result):
    """Проверка immutability Gate01Result (frozen=True)."""
    result = gate01.evaluate(
        gate00_result=gate00_pass_result,
        trading_mode=TradingMode.LIVE,
        manual_halt_new_entries=False,
        manual_halt_all_trading=False
    )
    
    with pytest.raises(Exception):  # dataclass frozen error
        result.entry_allowed = False
