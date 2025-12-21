"""GATE 1: DRP Kill-switch / Manual Halt / Trading Mode

ТЗ 3.3.2 строка 1018:
- Второй gate в цепочке (после GATE 0)
- Блокирует входы при:
  * Manual halt flags (manual_halt_new_entries, manual_halt_all_trading)
  * Trading mode != LIVE/SHADOW (PAPER/BACKTEST блокируются)
  * DRP emergency kill-switch (использует DRP state из GATE 0)

SHADOW mode:
- SHADOW разрешен в GATE 1 (early exit после GATE 6 будет позже)
- ТЗ 3.3.2 строка 1037: "trading_mode == SHADOW завершает после GATE 6"

Интеграция:
- Использует результаты GATE 0 (DRP state, warm-up status)
- Не выполняет DRP transitions (это делает GATE 0)
"""

from dataclasses import dataclass
from typing import Optional

from src.core.domain.portfolio_state import DRPState, TradingMode
from src.gatekeeper.gates.gate_00_warmup_dqs import Gate00Result


@dataclass(frozen=True)
class Gate01Result:
    """Результат GATE 1."""
    
    entry_allowed: bool
    block_reason: str
    
    # Входные параметры для диагностики
    drp_state: DRPState
    trading_mode: TradingMode
    manual_halt_new_entries: bool
    manual_halt_all_trading: bool
    
    # Shadow mode indicator (для будущей логики early exit после GATE 6)
    is_shadow_mode: bool
    
    # Детали
    details: str


class Gate01DRPKillswitch:
    """GATE 1: DRP Kill-switch / Manual Halt / Trading Mode.
    
    Порядок проверок:
    1. Manual halt flags → блокировка
    2. Trading mode проверка → блокировка если PAPER/BACKTEST
    3. DRP state проверка → блокировка если EMERGENCY/RECOVERY/HIBERNATE
    4. SHADOW mode marker → пропуск (early exit будет после GATE 6)
    """
    
    def __init__(self):
        """GATE 1 не требует зависимостей (stateless)."""
        pass
    
    def evaluate(
        self,
        # GATE 0 результаты
        gate00_result: Gate00Result,
        
        # Portfolio state parameters
        trading_mode: TradingMode,
        manual_halt_new_entries: bool = False,
        manual_halt_all_trading: bool = False
    ) -> Gate01Result:
        """Оценка GATE 1: DRP kill-switch, manual halt, trading mode.
        
        Args:
            gate00_result: результат GATE 0 (DRP state и др.)
            trading_mode: текущий режим торговли
            manual_halt_new_entries: флаг ручной блокировки новых входов
            manual_halt_all_trading: флаг ручной блокировки всей торговли
        
        Returns:
            Gate01Result с решением о допуске
        """
        drp_state = gate00_result.new_drp_state
        is_shadow_mode = (trading_mode == TradingMode.SHADOW)
        
        # 1. Manual halt flags проверка (высший приоритет)
        if manual_halt_all_trading:
            return Gate01Result(
                entry_allowed=False,
                block_reason="manual_halt_all_trading",
                drp_state=drp_state,
                trading_mode=trading_mode,
                manual_halt_new_entries=manual_halt_new_entries,
                manual_halt_all_trading=manual_halt_all_trading,
                is_shadow_mode=is_shadow_mode,
                details="Manual emergency stop: all trading halted"
            )
        
        if manual_halt_new_entries:
            return Gate01Result(
                entry_allowed=False,
                block_reason="manual_halt_new_entries",
                drp_state=drp_state,
                trading_mode=trading_mode,
                manual_halt_new_entries=manual_halt_new_entries,
                manual_halt_all_trading=manual_halt_all_trading,
                is_shadow_mode=is_shadow_mode,
                details="Manual kill-switch: new entries halted"
            )
        
        # 2. Trading mode проверка
        # LIVE и SHADOW разрешены, PAPER и BACKTEST блокируются
        if trading_mode == TradingMode.PAPER:
            return Gate01Result(
                entry_allowed=False,
                block_reason="trading_mode_paper",
                drp_state=drp_state,
                trading_mode=trading_mode,
                manual_halt_new_entries=manual_halt_new_entries,
                manual_halt_all_trading=manual_halt_all_trading,
                is_shadow_mode=is_shadow_mode,
                details="PAPER mode: new entries blocked in GATE 1"
            )
        
        if trading_mode == TradingMode.BACKTEST:
            return Gate01Result(
                entry_allowed=False,
                block_reason="trading_mode_backtest",
                drp_state=drp_state,
                trading_mode=trading_mode,
                manual_halt_new_entries=manual_halt_new_entries,
                manual_halt_all_trading=manual_halt_all_trading,
                is_shadow_mode=is_shadow_mode,
                details="BACKTEST mode: new entries blocked in GATE 1"
            )
        
        # 3. DRP state проверка (использует результаты GATE 0)
        # GATE 0 уже проверил EMERGENCY/RECOVERY/HIBERNATE, но мы добавляем
        # дополнительную проверку на уровне GATE 1 для kill-switch логики
        if not gate00_result.entry_allowed:
            # GATE 0 заблокировал вход, пропускаем причину блокировки
            return Gate01Result(
                entry_allowed=False,
                block_reason=f"gate00_blocked: {gate00_result.block_reason}",
                drp_state=drp_state,
                trading_mode=trading_mode,
                manual_halt_new_entries=manual_halt_new_entries,
                manual_halt_all_trading=manual_halt_all_trading,
                is_shadow_mode=is_shadow_mode,
                details=f"GATE 0 blocked: {gate00_result.block_reason}"
            )
        
        # 4. PASS - новые входы разрешены
        # SHADOW mode проходит через GATE 1, early exit будет после GATE 6
        shadow_note = " (SHADOW mode - will exit after GATE 6)" if is_shadow_mode else ""
        
        return Gate01Result(
            entry_allowed=True,
            block_reason="",
            drp_state=drp_state,
            trading_mode=trading_mode,
            manual_halt_new_entries=manual_halt_new_entries,
            manual_halt_all_trading=manual_halt_all_trading,
            is_shadow_mode=is_shadow_mode,
            details=f"PASS: trading_mode={trading_mode.value}, DRP_state={drp_state.value}{shadow_note}"
        )
