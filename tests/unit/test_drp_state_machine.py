"""Тесты для DRP State Machine.

Coverage:
- DQS-based transitions (NORMAL/DEFENSIVE/EMERGENCY)
- Warm-up после emergency
- Anti-flapping механизм
- HIBERNATE transitions
- Edge cases
"""

import pytest

from src.drp.state_machine import (
    DRPStateMachine,
    EmergencyCause,
    WarmupConfig,
    AntiFlappingConfig,
)
from src.core.domain.portfolio_state import DRPState


class TestDRPStateMachine:
    """Тесты DRP State Machine."""
    
    def test_normal_to_defensive_on_dqs_drop(self):
        """DQS падение 0.7 → 0.5 → DEFENSIVE."""
        sm = DRPStateMachine()
        
        result = sm.evaluate_transition(
            current_state=DRPState.NORMAL,
            dqs=0.5,
            hard_gate_triggered=False,
            warmup_bars_remaining=0,
            drp_flap_count=0,
            hibernate_until_ts_utc_ms=None,
            current_time_ms=1000.0,
            atr_z_short=1.0
        )
        
        assert result.new_state == DRPState.DEFENSIVE
        assert result.transition_occurred
        assert result.transition_reason == "dqs_based_transition_NORMAL_to_DEFENSIVE"
        assert result.warmup_bars_remaining == 0
        assert result.drp_flap_count > 0  # Transition counted
    
    def test_defensive_to_normal_on_dqs_recovery(self):
        """DQS восстановление 0.5 → 0.8 → NORMAL."""
        sm = DRPStateMachine()
        
        result = sm.evaluate_transition(
            current_state=DRPState.DEFENSIVE,
            dqs=0.8,
            hard_gate_triggered=False,
            warmup_bars_remaining=0,
            drp_flap_count=1,
            hibernate_until_ts_utc_ms=None,
            current_time_ms=2000.0,
            atr_z_short=1.0
        )
        
        assert result.new_state == DRPState.NORMAL
        assert result.transition_occurred
        assert result.transition_reason == "dqs_based_transition_DEFENSIVE_to_NORMAL"
    
    def test_normal_to_emergency_on_low_dqs(self):
        """DQS < 0.3 → EMERGENCY."""
        sm = DRPStateMachine()
        
        result = sm.evaluate_transition(
            current_state=DRPState.NORMAL,
            dqs=0.2,
            hard_gate_triggered=False,
            warmup_bars_remaining=0,
            drp_flap_count=0,
            hibernate_until_ts_utc_ms=None,
            current_time_ms=1000.0,
            atr_z_short=1.0,
            emergency_cause=EmergencyCause.DATA_GLITCH
        )
        
        assert result.new_state == DRPState.EMERGENCY
        assert result.transition_occurred
        assert result.warmup_bars_remaining == 3  # DATA_GLITCH → 3 bars
    
    def test_hard_gate_to_emergency(self):
        """Hard-gate → EMERGENCY независимо от DQS."""
        sm = DRPStateMachine()
        
        result = sm.evaluate_transition(
            current_state=DRPState.NORMAL,
            dqs=0.9,  # DQS высокий, но hard-gate сработал
            hard_gate_triggered=True,
            warmup_bars_remaining=0,
            drp_flap_count=0,
            hibernate_until_ts_utc_ms=None,
            current_time_ms=1000.0,
            atr_z_short=1.0,
            emergency_cause=EmergencyCause.DATA_GLITCH
        )
        
        assert result.new_state == DRPState.EMERGENCY
        assert result.transition_occurred
    
    def test_emergency_to_recovery_transition(self):
        """EMERGENCY → RECOVERY при улучшении DQS."""
        sm = DRPStateMachine()
        
        result = sm.evaluate_transition(
            current_state=DRPState.EMERGENCY,
            dqs=0.8,  # DQS восстановился
            hard_gate_triggered=False,
            warmup_bars_remaining=3,
            drp_flap_count=1,
            hibernate_until_ts_utc_ms=None,
            current_time_ms=2000.0,
            atr_z_short=1.0,
            emergency_cause=EmergencyCause.DATA_GLITCH
        )
        
        assert result.new_state == DRPState.RECOVERY
        assert result.transition_occurred
        assert result.warmup_bars_remaining == 3  # Warm-up начался
    
    def test_warmup_bars_by_cause_data_glitch(self):
        """Warm-up bars: DATA_GLITCH → 3."""
        sm = DRPStateMachine()
        
        result = sm.evaluate_transition(
            current_state=DRPState.NORMAL,
            dqs=0.2,
            hard_gate_triggered=False,
            warmup_bars_remaining=0,
            drp_flap_count=0,
            hibernate_until_ts_utc_ms=None,
            current_time_ms=1000.0,
            atr_z_short=1.0,
            emergency_cause=EmergencyCause.DATA_GLITCH
        )
        
        assert result.warmup_bars_remaining == 3
    
    def test_warmup_bars_by_cause_liquidity(self):
        """Warm-up bars: LIQUIDITY → 6."""
        sm = DRPStateMachine()
        
        result = sm.evaluate_transition(
            current_state=DRPState.NORMAL,
            dqs=0.2,
            hard_gate_triggered=False,
            warmup_bars_remaining=0,
            drp_flap_count=0,
            hibernate_until_ts_utc_ms=None,
            current_time_ms=1000.0,
            atr_z_short=1.0,
            emergency_cause=EmergencyCause.LIQUIDITY
        )
        
        assert result.warmup_bars_remaining == 6
    
    def test_warmup_bars_by_cause_depeg(self):
        """Warm-up bars: DEPEG → 24."""
        sm = DRPStateMachine()
        
        result = sm.evaluate_transition(
            current_state=DRPState.NORMAL,
            dqs=0.2,
            hard_gate_triggered=False,
            warmup_bars_remaining=0,
            drp_flap_count=0,
            hibernate_until_ts_utc_ms=None,
            current_time_ms=1000.0,
            atr_z_short=1.0,
            emergency_cause=EmergencyCause.DEPEG
        )
        
        assert result.warmup_bars_remaining == 24
    
    def test_warmup_bars_by_cause_other(self):
        """Warm-up bars: OTHER → clip(base + floor(recovery_hold/60), min, max)."""
        sm = DRPStateMachine(warmup_config=WarmupConfig(
            warmup_bars_base=3,
            warmup_bars_min=2,
            warmup_bars_max=48,
            recovery_hold_minutes=60.0
        ))
        
        result = sm.evaluate_transition(
            current_state=DRPState.NORMAL,
            dqs=0.2,
            hard_gate_triggered=False,
            warmup_bars_remaining=0,
            drp_flap_count=0,
            hibernate_until_ts_utc_ms=None,
            current_time_ms=1000.0,
            atr_z_short=1.0,
            emergency_cause=EmergencyCause.OTHER
        )
        
        # base=3 + floor(60/60)=1 → 4
        assert result.warmup_bars_remaining == 4
    
    def test_warmup_completion_and_recovery_to_normal(self):
        """RECOVERY: warm-up завершен → NORMAL."""
        sm = DRPStateMachine()
        
        # В RECOVERY с 1 баром
        result = sm.evaluate_transition(
            current_state=DRPState.RECOVERY,
            dqs=0.8,
            hard_gate_triggered=False,
            warmup_bars_remaining=1,
            drp_flap_count=1,
            hibernate_until_ts_utc_ms=None,
            current_time_ms=1000.0,
            atr_z_short=1.0,
            successful_bar_completed=True  # Бар завершен
        )
        
        assert result.new_state == DRPState.NORMAL
        assert result.transition_occurred
        assert result.warmup_bars_remaining == 0
        assert result.transition_reason == "warmup_completed"
    
    def test_warmup_in_progress(self):
        """RECOVERY: warm-up в процессе, бар завершен → счетчик уменьшается."""
        sm = DRPStateMachine()
        
        result = sm.evaluate_transition(
            current_state=DRPState.RECOVERY,
            dqs=0.8,
            hard_gate_triggered=False,
            warmup_bars_remaining=3,
            drp_flap_count=1,
            hibernate_until_ts_utc_ms=None,
            current_time_ms=1000.0,
            atr_z_short=1.0,
            successful_bar_completed=True
        )
        
        assert result.new_state == DRPState.RECOVERY
        assert result.warmup_bars_remaining == 2  # 3 - 1
        assert not result.transition_occurred
    
    def test_warmup_bar_not_completed(self):
        """RECOVERY: бар не завершен → счетчик не уменьшается."""
        sm = DRPStateMachine()
        
        result = sm.evaluate_transition(
            current_state=DRPState.RECOVERY,
            dqs=0.8,
            hard_gate_triggered=False,
            warmup_bars_remaining=3,
            drp_flap_count=1,
            hibernate_until_ts_utc_ms=None,
            current_time_ms=1000.0,
            atr_z_short=1.0,
            successful_bar_completed=False  # Бар не завершен
        )
        
        assert result.new_state == DRPState.RECOVERY
        assert result.warmup_bars_remaining == 3  # Не уменьшается
    
    def test_new_emergency_during_recovery(self):
        """RECOVERY: новый emergency → EMERGENCY с новым warm-up."""
        sm = DRPStateMachine()
        
        result = sm.evaluate_transition(
            current_state=DRPState.RECOVERY,
            dqs=0.1,  # Новый emergency
            hard_gate_triggered=False,
            warmup_bars_remaining=2,
            drp_flap_count=1,
            hibernate_until_ts_utc_ms=None,
            current_time_ms=1000.0,
            atr_z_short=1.0,
            emergency_cause=EmergencyCause.LIQUIDITY
        )
        
        assert result.new_state == DRPState.EMERGENCY
        assert result.transition_occurred
        assert result.warmup_bars_remaining == 6  # LIQUIDITY → 6 bars
    
    def test_anti_flapping_count_increment(self):
        """Anti-flapping: переход NORMAL → DEFENSIVE → счетчик растет."""
        sm = DRPStateMachine()
        
        # Первый переход
        result1 = sm.evaluate_transition(
            current_state=DRPState.NORMAL,
            dqs=0.5,
            hard_gate_triggered=False,
            warmup_bars_remaining=0,
            drp_flap_count=0,
            hibernate_until_ts_utc_ms=None,
            current_time_ms=1000.0,
            atr_z_short=1.0
        )
        
        assert result1.drp_flap_count == 1
        
        # Второй переход
        result2 = sm.evaluate_transition(
            current_state=DRPState.DEFENSIVE,
            dqs=0.8,
            hard_gate_triggered=False,
            warmup_bars_remaining=0,
            drp_flap_count=result1.drp_flap_count,
            hibernate_until_ts_utc_ms=None,
            current_time_ms=2000.0,
            atr_z_short=1.0
        )
        
        assert result2.drp_flap_count == 2
    
    def test_anti_flapping_to_hibernate(self):
        """Anti-flapping: flap_count >= threshold → HIBERNATE."""
        sm = DRPStateMachine(anti_flapping_config=AntiFlappingConfig(
            flap_to_hibernate_threshold=3
        ))
        
        # 3 перехода быстро
        current_state = DRPState.NORMAL
        flap_count = 0
        
        for i in range(3):
            result = sm.evaluate_transition(
                current_state=current_state,
                dqs=0.5 if i % 2 == 0 else 0.8,
                hard_gate_triggered=False,
                warmup_bars_remaining=0,
                drp_flap_count=flap_count,
                hibernate_until_ts_utc_ms=None,
                current_time_ms=1000.0 + i * 1000,
                atr_z_short=1.0
            )
            
            if result.new_state == DRPState.HIBERNATE:
                assert result.transition_occurred
                assert result.transition_reason == "anti_flapping_hibernate"
                assert result.hibernate_until_ts_utc_ms is not None
                return
            
            current_state = result.new_state
            flap_count = result.drp_flap_count
        
        # Не должны дойти сюда
        pytest.fail("Expected HIBERNATE transition")
    
    def test_anti_flapping_window_atr_adaptation(self):
        """Anti-flapping: window адаптируется к ATR_z_short."""
        sm = DRPStateMachine(anti_flapping_config=AntiFlappingConfig(
            flap_window_minutes_base=60.0,
            flap_window_minutes_min=10.0,
            flap_window_minutes_max=240.0
        ))
        
        # Высокий ATR_z_short → узкое окно → старые переходы быстрее выпадают
        # Делаем переход с atr_z_short=2.0
        result1 = sm.evaluate_transition(
            current_state=DRPState.NORMAL,
            dqs=0.5,
            hard_gate_triggered=False,
            warmup_bars_remaining=0,
            drp_flap_count=0,
            hibernate_until_ts_utc_ms=None,
            current_time_ms=1000.0,
            atr_z_short=2.0  # Высокий ATR
        )
        
        # Window = 60 / 2 = 30 минут
        # Следующий переход через 31 минуту → старый переход выпадет
        result2 = sm.evaluate_transition(
            current_state=result1.new_state,
            dqs=0.8,
            hard_gate_triggered=False,
            warmup_bars_remaining=0,
            drp_flap_count=result1.drp_flap_count,
            hibernate_until_ts_utc_ms=None,
            current_time_ms=1000.0 + 31 * 60_000,  # +31 minutes
            atr_z_short=2.0
        )
        
        # Старый переход выпал, только новый
        assert result2.drp_flap_count == 1
    
    def test_hibernate_unlock_after_timeout(self):
        """HIBERNATE: unlock после истечения timeout."""
        sm = DRPStateMachine(anti_flapping_config=AntiFlappingConfig(
            hibernate_min_duration_sec=3600.0  # 1 hour
        ))
        
        hibernate_start = 1000.0
        hibernate_until = int(hibernate_start + 3600_000)  # +1 hour
        
        # До истечения timeout
        result1 = sm.evaluate_transition(
            current_state=DRPState.HIBERNATE,
            dqs=1.0,
            hard_gate_triggered=False,
            warmup_bars_remaining=0,
            drp_flap_count=5,
            hibernate_until_ts_utc_ms=hibernate_until,
            current_time_ms=hibernate_start + 1800_000,  # +30 minutes
            atr_z_short=1.0
        )
        
        assert result1.new_state == DRPState.HIBERNATE
        assert not result1.transition_occurred
        
        # После истечения timeout
        result2 = sm.evaluate_transition(
            current_state=DRPState.HIBERNATE,
            dqs=1.0,
            hard_gate_triggered=False,
            warmup_bars_remaining=0,
            drp_flap_count=5,
            hibernate_until_ts_utc_ms=hibernate_until,
            current_time_ms=hibernate_start + 3600_001,  # +1 hour + 1ms
            atr_z_short=1.0
        )
        
        assert result2.new_state == DRPState.NORMAL
        assert result2.transition_occurred
        assert result2.transition_reason == "hibernate_timeout_unlock"
    
    def test_no_transition_when_state_stable(self):
        """Нет перехода если состояние стабильно."""
        sm = DRPStateMachine()
        
        result = sm.evaluate_transition(
            current_state=DRPState.NORMAL,
            dqs=0.9,
            hard_gate_triggered=False,
            warmup_bars_remaining=0,
            drp_flap_count=0,
            hibernate_until_ts_utc_ms=None,
            current_time_ms=1000.0,
            atr_z_short=1.0
        )
        
        assert result.new_state == DRPState.NORMAL
        assert not result.transition_occurred
        assert result.transition_reason == "no_transition"
