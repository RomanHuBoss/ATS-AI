"""GATE 0: Warm-up / Data Availability / Cross-Validation / Hard-gates / DQS

ТЗ 3.3.2 строка 1017:
- Первый gate в цепочке (обязательный)
- Блокирует входы при:
  * Hard-gates (DQS_critical=0, staleness > hard, xdev >= threshold, NaN/inf, oracle block)
  * Warm-up после emergency (RECOVERY state)
  * HIBERNATE state
  * EMERGENCY state

Интеграция:
- DQSChecker для оценки качества данных
- DRPStateMachine для управления состоянием (опционально, может быть внешним)
"""

from dataclasses import dataclass
from typing import Optional

from src.data.quality.dqs import DQSChecker, DQSResult
from src.drp.state_machine import DRPStateMachine, DRPTransitionResult, EmergencyCause
from src.core.domain.portfolio_state import DRPState


@dataclass(frozen=True)
class Gate00Result:
    """Результат GATE 0."""
    
    entry_allowed: bool
    block_reason: str
    
    # DQS диагностика
    dqs_result: Optional[DQSResult]
    
    # DRP диагностика
    drp_transition: Optional[DRPTransitionResult]
    
    # Обновленные параметры для portfolio state
    new_drp_state: DRPState
    new_warmup_bars_remaining: int
    new_drp_flap_count: int
    new_hibernate_until_ts_utc_ms: Optional[int]
    
    # Детали
    details: str


class Gate00WarmupDQS:
    """GATE 0: Warm-up / Data Availability / Cross-Validation / Hard-gates / DQS.
    
    Порядок проверок:
    1. Проверка HIBERNATE state → блокировка
    2. DQS evaluation → hard-gates проверка
    3. DRP transition на основе DQS
    4. Проверка EMERGENCY/RECOVERY states → блокировка
    5. Проверка warm-up → блокировка если warm-up не завершен
    """
    
    def __init__(
        self,
        dqs_checker: Optional[DQSChecker] = None,
        drp_state_machine: Optional[DRPStateMachine] = None
    ):
        """
        Args:
            dqs_checker: DQS checker (default: создается автоматически)
            drp_state_machine: DRP state machine (default: создается автоматически)
        """
        self.dqs_checker = dqs_checker or DQSChecker()
        self.drp_state_machine = drp_state_machine or DRPStateMachine()
    
    def evaluate(
        self,
        # Current portfolio state
        current_drp_state: DRPState,
        warmup_bars_remaining: int,
        drp_flap_count: int,
        hibernate_until_ts_utc_ms: Optional[int],
        
        # DQS parameters (передаются в DQSChecker.evaluate_dqs)
        current_time_ms: float,
        price_timestamp_ms: Optional[float] = None,
        liquidity_timestamp_ms: Optional[float] = None,
        orderbook_timestamp_ms: Optional[float] = None,
        volatility_timestamp_ms: Optional[float] = None,
        funding_timestamp_ms: Optional[float] = None,
        oi_timestamp_ms: Optional[float] = None,
        basis_timestamp_ms: Optional[float] = None,
        derivatives_timestamp_ms: Optional[float] = None,
        price_src_A: Optional[float] = None,
        price_src_B: Optional[float] = None,
        price_oracle_C: Optional[float] = None,
        oracle_staleness_ms: Optional[float] = None,
        price: Optional[float] = None,
        atr: Optional[float] = None,
        spread_bps: Optional[float] = None,
        bid: Optional[float] = None,
        ask: Optional[float] = None,
        liquidity_depth: Optional[float] = None,
        volatility: Optional[float] = None,
        price_changed: bool = False,
        orderbook_update_id_age_ms: Optional[float] = None,
        source_weights: Optional[dict] = None,
        
        # DRP parameters
        atr_z_short: float = 1.0,
        emergency_cause: Optional[EmergencyCause] = None,
        successful_bar_completed: bool = False
    ) -> Gate00Result:
        """Оценка GATE 0: warm-up, DQS, hard-gates, DRP transitions.
        
        Args:
            current_drp_state: текущее состояние DRP
            warmup_bars_remaining: оставшиеся warm-up бары
            drp_flap_count: текущий счетчик flapping
            hibernate_until_ts_utc_ms: timestamp окончания HIBERNATE
            
            current_time_ms: текущее время (Unix timestamp ms)
            
            DQS timestamps (critical):
                price_timestamp_ms, liquidity_timestamp_ms, orderbook_timestamp_ms, volatility_timestamp_ms
            
            DQS timestamps (non-critical):
                funding_timestamp_ms, oi_timestamp_ms, basis_timestamp_ms, derivatives_timestamp_ms
            
            Cross-validation:
                price_src_A, price_src_B: цены из источников A, B
                price_oracle_C: цена из oracle
                oracle_staleness_ms: staleness oracle
            
            Glitch detection:
                price, atr, spread_bps, bid, ask, liquidity_depth, volatility: для NaN/inf
                price_changed: флаг изменения цены
                orderbook_update_id_age_ms: возраст orderbook update_id
            
            source_weights: веса источников для DQS_sources
            
            DRP parameters:
                atr_z_short: z-score краткосрочного ATR (для flap window)
                emergency_cause: причина emergency (если переход в EMERGENCY)
                successful_bar_completed: True если бар завершен успешно (для warm-up)
        
        Returns:
            Gate00Result с решением о допуске и обновленными DRP параметрами
        """
        # 1. Проверка HIBERNATE state
        if current_drp_state == DRPState.HIBERNATE:
            # HIBERNATE требует ручного unlock, блокировка
            # Но сначала проверим, не истек ли HIBERNATE timeout
            drp_transition = self.drp_state_machine.evaluate_transition(
                current_state=current_drp_state,
                dqs=1.0,  # Dummy value, не используется при HIBERNATE check
                hard_gate_triggered=False,
                warmup_bars_remaining=warmup_bars_remaining,
                drp_flap_count=drp_flap_count,
                hibernate_until_ts_utc_ms=hibernate_until_ts_utc_ms,
                current_time_ms=current_time_ms,
                atr_z_short=atr_z_short,
                emergency_cause=emergency_cause,
                successful_bar_completed=successful_bar_completed
            )
            
            if drp_transition.new_state == DRPState.HIBERNATE:
                return Gate00Result(
                    entry_allowed=False,
                    block_reason="hibernate_mode",
                    dqs_result=None,
                    drp_transition=drp_transition,
                    new_drp_state=drp_transition.new_state,
                    new_warmup_bars_remaining=drp_transition.warmup_bars_remaining,
                    new_drp_flap_count=drp_transition.drp_flap_count,
                    new_hibernate_until_ts_utc_ms=drp_transition.hibernate_until_ts_utc_ms,
                    details=f"HIBERNATE mode active: {drp_transition.details}"
                )
            else:
                # HIBERNATE unlock произошел, продолжаем с новым состоянием
                current_drp_state = drp_transition.new_state
                warmup_bars_remaining = drp_transition.warmup_bars_remaining
                drp_flap_count = drp_transition.drp_flap_count
        
        # 2. DQS evaluation
        dqs_result = self.dqs_checker.evaluate_dqs(
            current_time_ms=current_time_ms,
            price_timestamp_ms=price_timestamp_ms,
            liquidity_timestamp_ms=liquidity_timestamp_ms,
            orderbook_timestamp_ms=orderbook_timestamp_ms,
            volatility_timestamp_ms=volatility_timestamp_ms,
            funding_timestamp_ms=funding_timestamp_ms,
            oi_timestamp_ms=oi_timestamp_ms,
            basis_timestamp_ms=basis_timestamp_ms,
            derivatives_timestamp_ms=derivatives_timestamp_ms,
            price_src_A=price_src_A,
            price_src_B=price_src_B,
            price_oracle_C=price_oracle_C,
            oracle_staleness_ms=oracle_staleness_ms,
            price=price,
            atr=atr,
            spread_bps=spread_bps,
            bid=bid,
            ask=ask,
            liquidity_depth=liquidity_depth,
            volatility=volatility,
            price_changed=price_changed,
            orderbook_update_id_age_ms=orderbook_update_id_age_ms,
            source_weights=source_weights
        )
        
        # 3. DRP transition на основе DQS
        drp_transition = self.drp_state_machine.evaluate_transition(
            current_state=current_drp_state,
            dqs=dqs_result.dqs,
            hard_gate_triggered=dqs_result.hard_gate_triggered,
            warmup_bars_remaining=warmup_bars_remaining,
            drp_flap_count=drp_flap_count,
            hibernate_until_ts_utc_ms=hibernate_until_ts_utc_ms,
            current_time_ms=current_time_ms,
            atr_z_short=atr_z_short,
            emergency_cause=emergency_cause,
            successful_bar_completed=successful_bar_completed
        )
        
        # 4. Проверка блокировок
        new_state = drp_transition.new_state
        
        # Hard-gate блокировка
        if dqs_result.hard_gate_triggered:
            return Gate00Result(
                entry_allowed=False,
                block_reason=f"hard_gate: {dqs_result.block_reason}",
                dqs_result=dqs_result,
                drp_transition=drp_transition,
                new_drp_state=new_state,
                new_warmup_bars_remaining=drp_transition.warmup_bars_remaining,
                new_drp_flap_count=drp_transition.drp_flap_count,
                new_hibernate_until_ts_utc_ms=drp_transition.hibernate_until_ts_utc_ms,
                details=f"Hard-gate triggered: {dqs_result.block_reason}, DQS={dqs_result.dqs:.3f}"
            )
        
        # EMERGENCY блокировка
        if new_state == DRPState.EMERGENCY:
            return Gate00Result(
                entry_allowed=False,
                block_reason="emergency_mode",
                dqs_result=dqs_result,
                drp_transition=drp_transition,
                new_drp_state=new_state,
                new_warmup_bars_remaining=drp_transition.warmup_bars_remaining,
                new_drp_flap_count=drp_transition.drp_flap_count,
                new_hibernate_until_ts_utc_ms=drp_transition.hibernate_until_ts_utc_ms,
                details=f"EMERGENCY mode: DQS={dqs_result.dqs:.3f}, {drp_transition.details}"
            )
        
        # RECOVERY блокировка (warm-up не завершен)
        if new_state == DRPState.RECOVERY and drp_transition.warmup_bars_remaining > 0:
            return Gate00Result(
                entry_allowed=False,
                block_reason="warmup_in_progress",
                dqs_result=dqs_result,
                drp_transition=drp_transition,
                new_drp_state=new_state,
                new_warmup_bars_remaining=drp_transition.warmup_bars_remaining,
                new_drp_flap_count=drp_transition.drp_flap_count,
                new_hibernate_until_ts_utc_ms=drp_transition.hibernate_until_ts_utc_ms,
                details=f"Warm-up in progress: {drp_transition.warmup_bars_remaining} bars remaining"
            )
        
        # 5. PASS - новые входы разрешены
        return Gate00Result(
            entry_allowed=True,
            block_reason="",
            dqs_result=dqs_result,
            drp_transition=drp_transition,
            new_drp_state=new_state,
            new_warmup_bars_remaining=drp_transition.warmup_bars_remaining,
            new_drp_flap_count=drp_transition.drp_flap_count,
            new_hibernate_until_ts_utc_ms=drp_transition.hibernate_until_ts_utc_ms,
            details=f"PASS: DRP_state={new_state}, DQS={dqs_result.dqs:.3f}, dqs_mult={dqs_result.dqs_mult:.3f}"
        )
