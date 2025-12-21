"""DRP State Machine — управление состояниями Disaster Recovery Protocol.

ТЗ 3.3.2, строки 958-982:
- Переходы состояний на основе DQS (NORMAL/DEFENSIVE/EMERGENCY/RECOVERY/HIBERNATE)
- Warm-up после emergency с зависимостью от emergency_cause
- Anti-flapping с ATR-зависимым скользящим окном
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional, List
import math

from src.core.domain.portfolio_state import DRPState


class EmergencyCause(str, Enum):
    """Причина перехода в EMERGENCY.
    
    ТЗ строки 963-969: warmup_required_bars зависит от cause
    """
    DATA_GLITCH = "DATA_GLITCH"
    LIQUIDITY = "LIQUIDITY"
    DEPEG = "DEPEG"
    OTHER = "OTHER"


@dataclass(frozen=True)
class WarmupConfig:
    """Конфигурация warm-up периода после emergency.
    
    ТЗ строки 963-969:
    - DATA_GLITCH: 3 bars
    - LIQUIDITY: 6 bars  
    - DEPEG: 24 bars
    - OTHER: clip(warmup_bars_base + floor(recovery_hold_minutes / 60), min, max)
    """
    warmup_bars_base: int = 3
    warmup_bars_min: int = 2
    warmup_bars_max: int = 48
    recovery_hold_minutes: float = 60.0  # Для OTHER cause


@dataclass(frozen=True)
class AntiFlappingConfig:
    """Конфигурация anti-flapping механизма.
    
    ТЗ строки 973-981:
    - flap_window_minutes_eff зависит от ATR_z_short
    - flap_to_hibernate_threshold — порог для перехода в HIBERNATE
    - hibernate_min_duration_sec — минимальное время в HIBERNATE
    """
    flap_window_minutes_base: float = 60.0
    flap_window_minutes_min: float = 10.0
    flap_window_minutes_max: float = 240.0
    flap_to_hibernate_threshold: int = 5
    hibernate_min_duration_sec: float = 3600.0  # 1 hour


@dataclass(frozen=True)
class DRPTransitionResult:
    """Результат перехода DRP состояния."""
    
    new_state: DRPState
    warmup_bars_remaining: int
    drp_flap_count: int
    hibernate_until_ts_utc_ms: Optional[int]
    
    # Диагностика
    transition_occurred: bool
    transition_reason: str
    previous_state: DRPState
    
    # Для отладки
    details: str


class DRPStateMachine:
    """DRP State Machine с transitions на основе DQS и anti-flapping.
    
    ТЗ 3.3.2:
    - DQS < emergency_threshold (0.3) → EMERGENCY
    - emergency_threshold ≤ DQS < degraded_threshold (0.7) → DEFENSIVE  
    - DQS ≥ degraded_threshold → NORMAL
    - После EMERGENCY → RECOVERY (с warm-up)
    - flap_count >= threshold → HIBERNATE
    
    States:
    - NORMAL: нормальная работа
    - DEGRADED: незначительная деградация (на данный момент не используется, reserved)
    - DEFENSIVE: умеренная деградация данных, риск снижен
    - EMERGENCY: критическое качество данных или hard-gate, новые входы запрещены
    - RECOVERY: период прогрева после EMERGENCY, новые входы запрещены
    - HIBERNATE: частый flapping, требуется ручное вмешательство
    """
    
    def __init__(
        self,
        dqs_emergency_threshold: float = 0.3,
        dqs_degraded_threshold: float = 0.7,
        warmup_config: Optional[WarmupConfig] = None,
        anti_flapping_config: Optional[AntiFlappingConfig] = None
    ):
        """
        Args:
            dqs_emergency_threshold: порог DQS для EMERGENCY (default 0.3)
            dqs_degraded_threshold: порог DQS для DEFENSIVE/NORMAL (default 0.7)
            warmup_config: конфигурация warm-up
            anti_flapping_config: конфигурация anti-flapping
        """
        self.dqs_emergency_threshold = dqs_emergency_threshold
        self.dqs_degraded_threshold = dqs_degraded_threshold
        self.warmup_config = warmup_config or WarmupConfig()
        self.anti_flapping_config = anti_flapping_config or AntiFlappingConfig()
        
        # История переходов для anti-flapping
        self._transition_history: List[tuple[float, DRPState, DRPState]] = []
    
    def evaluate_transition(
        self,
        current_state: DRPState,
        dqs: float,
        hard_gate_triggered: bool,
        warmup_bars_remaining: int,
        drp_flap_count: int,
        hibernate_until_ts_utc_ms: Optional[int],
        current_time_ms: float,
        atr_z_short: float = 1.0,
        emergency_cause: Optional[EmergencyCause] = None,
        successful_bar_completed: bool = False
    ) -> DRPTransitionResult:
        """Оценка и выполнение перехода DRP состояния.
        
        Args:
            current_state: текущее состояние DRP
            dqs: текущий Data Quality Score [0, 1]
            hard_gate_triggered: True если сработал hard-gate
            warmup_bars_remaining: оставшиеся warm-up бары
            drp_flap_count: текущий счетчик flapping
            hibernate_until_ts_utc_ms: timestamp окончания HIBERNATE
            current_time_ms: текущее время (Unix timestamp ms)
            atr_z_short: z-score краткосрочного ATR для flap window адаптации
            emergency_cause: причина emergency (если переход в EMERGENCY)
            successful_bar_completed: True если успешно завершен бар (для warm-up)
        
        Returns:
            DRPTransitionResult с новым состоянием и параметрами
        """
        # 1. Проверка HIBERNATE unlock
        if current_state == DRPState.HIBERNATE:
            if (
                hibernate_until_ts_utc_ms is not None
                and current_time_ms >= hibernate_until_ts_utc_ms
            ):
                # Выход из HIBERNATE → NORMAL (требуется ручное подтверждение, здесь упрощено)
                return self._create_result(
                    new_state=DRPState.NORMAL,
                    previous_state=current_state,
                    warmup_bars_remaining=0,
                    drp_flap_count=0,
                    hibernate_until_ts_utc_ms=None,
                    transition_occurred=True,
                    transition_reason="hibernate_timeout_unlock",
                    details=f"HIBERNATE unlock after {(current_time_ms - (hibernate_until_ts_utc_ms - self.anti_flapping_config.hibernate_min_duration_sec * 1000)) / 1000:.1f}s"
                )
            else:
                # Остаемся в HIBERNATE
                return self._create_result(
                    new_state=current_state,
                    previous_state=current_state,
                    warmup_bars_remaining=warmup_bars_remaining,
                    drp_flap_count=drp_flap_count,
                    hibernate_until_ts_utc_ms=hibernate_until_ts_utc_ms,
                    transition_occurred=False,
                    transition_reason="in_hibernate",
                    details=f"Remaining: {(hibernate_until_ts_utc_ms - current_time_ms) / 1000:.1f}s"
                )
        
        # 2. Определение целевого состояния на основе DQS и hard-gates
        target_state = self._determine_target_state(dqs, hard_gate_triggered)
        
        # 3. Обработка RECOVERY state (warm-up)
        if current_state == DRPState.RECOVERY:
            new_warmup_bars = warmup_bars_remaining
            
            if successful_bar_completed and warmup_bars_remaining > 0:
                new_warmup_bars = warmup_bars_remaining - 1
            
            if new_warmup_bars == 0 and target_state == DRPState.NORMAL:
                # Warm-up завершен, можно перейти в NORMAL
                new_flap_count = self._update_flap_count(
                    current_state, DRPState.NORMAL, current_time_ms, atr_z_short, drp_flap_count
                )
                
                return self._create_result(
                    new_state=DRPState.NORMAL,
                    previous_state=current_state,
                    warmup_bars_remaining=0,
                    drp_flap_count=new_flap_count,
                    hibernate_until_ts_utc_ms=None,
                    transition_occurred=True,
                    transition_reason="warmup_completed",
                    details=f"Warmup completed, transition RECOVERY → NORMAL"
                )
            elif hard_gate_triggered or target_state == DRPState.EMERGENCY:
                # Новый emergency во время RECOVERY
                new_warmup_bars = self._calculate_warmup_bars(emergency_cause or EmergencyCause.OTHER)
                new_flap_count = self._update_flap_count(
                    current_state, DRPState.EMERGENCY, current_time_ms, atr_z_short, drp_flap_count
                )
                
                # Проверка anti-flapping
                if new_flap_count >= self.anti_flapping_config.flap_to_hibernate_threshold:
                    return self._transition_to_hibernate(
                        current_state, current_time_ms, new_flap_count
                    )
                
                return self._create_result(
                    new_state=DRPState.EMERGENCY,
                    previous_state=current_state,
                    warmup_bars_remaining=new_warmup_bars,
                    drp_flap_count=new_flap_count,
                    hibernate_until_ts_utc_ms=None,
                    transition_occurred=True,
                    transition_reason="new_emergency_during_recovery",
                    details=f"New emergency during RECOVERY, warmup_bars={new_warmup_bars}"
                )
            else:
                # Остаемся в RECOVERY
                return self._create_result(
                    new_state=current_state,
                    previous_state=current_state,
                    warmup_bars_remaining=new_warmup_bars,
                    drp_flap_count=drp_flap_count,
                    hibernate_until_ts_utc_ms=None,
                    transition_occurred=False,
                    transition_reason="in_warmup",
                    details=f"Warmup in progress, remaining={new_warmup_bars} bars"
                )
        
        # 4. Переход из EMERGENCY в RECOVERY
        if current_state == DRPState.EMERGENCY and target_state != DRPState.EMERGENCY:
            # EMERGENCY → RECOVERY (начало warm-up)
            warmup_bars = self._calculate_warmup_bars(emergency_cause or EmergencyCause.OTHER)
            new_flap_count = self._update_flap_count(
                current_state, DRPState.RECOVERY, current_time_ms, atr_z_short, drp_flap_count
            )
            
            return self._create_result(
                new_state=DRPState.RECOVERY,
                previous_state=current_state,
                warmup_bars_remaining=warmup_bars,
                drp_flap_count=new_flap_count,
                hibernate_until_ts_utc_ms=None,
                transition_occurred=True,
                transition_reason="emergency_to_recovery",
                details=f"Emergency cleared, starting warmup: {warmup_bars} bars"
            )
        
        # 5. Переход в EMERGENCY
        if target_state == DRPState.EMERGENCY and current_state != DRPState.EMERGENCY:
            warmup_bars = self._calculate_warmup_bars(emergency_cause or EmergencyCause.OTHER)
            new_flap_count = self._update_flap_count(
                current_state, DRPState.EMERGENCY, current_time_ms, atr_z_short, drp_flap_count
            )
            
            # Проверка anti-flapping
            if new_flap_count >= self.anti_flapping_config.flap_to_hibernate_threshold:
                return self._transition_to_hibernate(
                    current_state, current_time_ms, new_flap_count
                )
            
            return self._create_result(
                new_state=DRPState.EMERGENCY,
                previous_state=current_state,
                warmup_bars_remaining=warmup_bars,
                drp_flap_count=new_flap_count,
                hibernate_until_ts_utc_ms=None,
                transition_occurred=True,
                transition_reason="to_emergency",
                details=f"Transition to EMERGENCY, cause={emergency_cause}, warmup_bars={warmup_bars}"
            )
        
        # 6. Переход NORMAL ↔ DEFENSIVE
        if target_state != current_state and target_state in (DRPState.NORMAL, DRPState.DEFENSIVE):
            new_flap_count = self._update_flap_count(
                current_state, target_state, current_time_ms, atr_z_short, drp_flap_count
            )
            
            # Проверка anti-flapping
            if new_flap_count >= self.anti_flapping_config.flap_to_hibernate_threshold:
                return self._transition_to_hibernate(
                    current_state, current_time_ms, new_flap_count
                )
            
            return self._create_result(
                new_state=target_state,
                previous_state=current_state,
                warmup_bars_remaining=0,
                drp_flap_count=new_flap_count,
                hibernate_until_ts_utc_ms=None,
                transition_occurred=True,
                transition_reason=f"dqs_based_transition_{current_state.value}_to_{target_state.value}",
                details=f"DQS-based transition: {current_state.value} → {target_state.value}, DQS={dqs:.3f}"
            )
        
        # 7. Нет перехода
        return self._create_result(
            new_state=current_state,
            previous_state=current_state,
            warmup_bars_remaining=warmup_bars_remaining,
            drp_flap_count=drp_flap_count,
            hibernate_until_ts_utc_ms=None,
            transition_occurred=False,
            transition_reason="no_transition",
            details=f"State={current_state}, DQS={dqs:.3f}, hard_gate={hard_gate_triggered}"
        )
    
    def _determine_target_state(self, dqs: float, hard_gate_triggered: bool) -> DRPState:
        """Определение целевого состояния на основе DQS и hard-gates.
        
        ТЗ строки 950-956:
        - Hard-gate → EMERGENCY
        - DQS < 0.3 → EMERGENCY
        - 0.3 ≤ DQS < 0.7 → DEFENSIVE
        - DQS ≥ 0.7 → NORMAL
        """
        if hard_gate_triggered:
            return DRPState.EMERGENCY
        
        if dqs < self.dqs_emergency_threshold:
            return DRPState.EMERGENCY
        elif dqs < self.dqs_degraded_threshold:
            return DRPState.DEFENSIVE
        else:
            return DRPState.NORMAL
    
    def _calculate_warmup_bars(self, cause: EmergencyCause) -> int:
        """Вычисление warm-up bars по причине emergency.
        
        ТЗ строки 963-969:
        - DATA_GLITCH: 3
        - LIQUIDITY: 6
        - DEPEG: 24
        - OTHER: clip(base + floor(recovery_hold_minutes / 60), min, max)
        """
        if cause == EmergencyCause.DATA_GLITCH:
            return 3
        elif cause == EmergencyCause.LIQUIDITY:
            return 6
        elif cause == EmergencyCause.DEPEG:
            return 24
        else:
            # OTHER
            bars = self.warmup_config.warmup_bars_base + math.floor(
                self.warmup_config.recovery_hold_minutes / 60.0
            )
            return max(
                self.warmup_config.warmup_bars_min,
                min(bars, self.warmup_config.warmup_bars_max)
            )
    
    def _update_flap_count(
        self,
        from_state: DRPState,
        to_state: DRPState,
        current_time_ms: float,
        atr_z_short: float,
        current_flap_count: int
    ) -> int:
        """Обновление счетчика flapping с учетом скользящего окна.
        
        ТЗ строки 975-979:
        - Считаются только переходы между/в "строгими" состояниями
        - flap_window_minutes_eff = clip(base / max(ATR_z_short, 1), min, max)
        """
        # Строгие состояния: EMERGENCY, RECOVERY, DEFENSIVE
        strict_states = {DRPState.EMERGENCY, DRPState.RECOVERY, DRPState.DEFENSIVE}
        
        # Переход считается если хотя бы одно состояние строгое
        # И states разные (есть переход)
        if from_state == to_state:
            return current_flap_count
        
        if from_state not in strict_states and to_state not in strict_states:
            return current_flap_count
        
        # Вычисление эффективного окна
        flap_window_minutes_eff = max(
            self.anti_flapping_config.flap_window_minutes_min,
            min(
                self.anti_flapping_config.flap_window_minutes_base / max(atr_z_short, 1.0),
                self.anti_flapping_config.flap_window_minutes_max
            )
        )
        
        # Добавление нового перехода в историю
        self._transition_history.append((current_time_ms, from_state, to_state))
        
        # Удаление устаревших переходов
        cutoff_time_ms = current_time_ms - flap_window_minutes_eff * 60_000
        self._transition_history = [
            (ts, f, t) for ts, f, t in self._transition_history if ts >= cutoff_time_ms
        ]
        
        # Подсчет переходов в окне
        return len(self._transition_history)
    
    def _transition_to_hibernate(
        self,
        current_state: DRPState,
        current_time_ms: float,
        flap_count: int
    ) -> DRPTransitionResult:
        """Переход в HIBERNATE при превышении flap threshold."""
        hibernate_until_ts = int(
            current_time_ms + self.anti_flapping_config.hibernate_min_duration_sec * 1000
        )
        
        return self._create_result(
            new_state=DRPState.HIBERNATE,
            previous_state=current_state,
            warmup_bars_remaining=0,
            drp_flap_count=flap_count,
            hibernate_until_ts_utc_ms=hibernate_until_ts,
            transition_occurred=True,
            transition_reason="anti_flapping_hibernate",
            details=f"Excessive flapping detected: {flap_count} transitions, HIBERNATE until {hibernate_until_ts}"
        )
    
    def _create_result(
        self,
        new_state: DRPState,
        previous_state: DRPState,
        warmup_bars_remaining: int,
        drp_flap_count: int,
        hibernate_until_ts_utc_ms: Optional[int],
        transition_occurred: bool,
        transition_reason: str,
        details: str
    ) -> DRPTransitionResult:
        """Создание результата перехода."""
        return DRPTransitionResult(
            new_state=new_state,
            warmup_bars_remaining=warmup_bars_remaining,
            drp_flap_count=drp_flap_count,
            hibernate_until_ts_utc_ms=hibernate_until_ts_utc_ms,
            transition_occurred=transition_occurred,
            transition_reason=transition_reason,
            previous_state=previous_state,
            details=details
        )
