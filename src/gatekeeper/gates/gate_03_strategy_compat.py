"""GATE 3: Совместимость режима и стратегии

ТЗ 3.3.2 строка 1020 (GATE 3: Совместимость режима и стратегии)

Проверяет совместимость final_regime (из GATE 2) и engine strategy (TREND/RANGE).

Правила совместимости:
- TREND engine → совместим с TREND_UP, TREND_DOWN, BREAKOUT_UP, BREAKOUT_DOWN, PROBE_TRADE
- RANGE engine → совместим с RANGE
- NO_TRADE → блокировка для всех
- NOISE → блокировка для всех (должно быть отфильтровано в GATE 2)

Интеграция:
- Использует результаты GATE 0-2 (должны быть PASS)
- Использует engine signal для определения strategy
"""

from dataclasses import dataclass

from src.core.domain.regime import FinalRegime
from src.core.domain.signal import EngineType
from src.gatekeeper.gates.gate_00_warmup_dqs import Gate00Result
from src.gatekeeper.gates.gate_01_drp_killswitch import Gate01Result
from src.gatekeeper.gates.gate_02_mrc_confidence import Gate02Result


# =============================================================================
# RESULT
# =============================================================================


@dataclass(frozen=True)
class Gate03Result:
    """Результат GATE 3."""
    
    entry_allowed: bool
    block_reason: str
    
    # Strategy compatibility
    engine_type: EngineType
    final_regime: FinalRegime
    is_compatible: bool
    
    # Детали
    details: str


# =============================================================================
# GATE 3
# =============================================================================


class Gate03StrategyCompat:
    """GATE 3: Совместимость режима и стратегии.
    
    Проверяет совместимость final_regime (из GATE 2) с engine strategy.
    
    Порядок проверок:
    1. GATE 0-2 блокировки (должны быть PASS)
    2. Проверка совместимости regime и strategy
    3. Блокировка при несовместимости
    """
    
    def __init__(self):
        """GATE 3 не требует зависимостей (stateless)."""
        pass
    
    def evaluate(
        self,
        # GATE 0-2 результаты
        gate00_result: Gate00Result,
        gate01_result: Gate01Result,
        gate02_result: Gate02Result,
        
        # Engine signal
        engine_type: EngineType
    ) -> Gate03Result:
        """Оценка GATE 3: совместимость режима и стратегии.
        
        Args:
            gate00_result: результат GATE 0 (DQS и DRP state)
            gate01_result: результат GATE 1 (trading mode, manual halt)
            gate02_result: результат GATE 2 (final_regime)
            engine_type: тип движка (TREND/RANGE)
        
        Returns:
            Gate03Result с решением о допуске
        """
        final_regime = gate02_result.final_regime
        
        # 1. Проверка GATE 0-2 блокировок
        if not gate00_result.entry_allowed:
            return Gate03Result(
                entry_allowed=False,
                block_reason=f"gate00_blocked: {gate00_result.block_reason}",
                engine_type=engine_type,
                final_regime=final_regime,
                is_compatible=False,
                details=f"GATE 0 blocked: {gate00_result.block_reason}"
            )
        
        if not gate01_result.entry_allowed:
            return Gate03Result(
                entry_allowed=False,
                block_reason=f"gate01_blocked: {gate01_result.block_reason}",
                engine_type=engine_type,
                final_regime=final_regime,
                is_compatible=False,
                details=f"GATE 1 blocked: {gate01_result.block_reason}"
            )
        
        if not gate02_result.entry_allowed:
            return Gate03Result(
                entry_allowed=False,
                block_reason=f"gate02_blocked: {gate02_result.block_reason}",
                engine_type=engine_type,
                final_regime=final_regime,
                is_compatible=False,
                details=f"GATE 2 blocked: {gate02_result.block_reason}"
            )
        
        # 2. Проверка совместимости regime и strategy
        is_compatible = self._check_compatibility(engine_type, final_regime)
        
        if not is_compatible:
            return Gate03Result(
                entry_allowed=False,
                block_reason="strategy_regime_incompatible",
                engine_type=engine_type,
                final_regime=final_regime,
                is_compatible=False,
                details=f"Strategy incompatible: engine={engine_type.value}, regime={final_regime.value}"
            )
        
        # 3. PASS - вход разрешен
        return Gate03Result(
            entry_allowed=True,
            block_reason="",
            engine_type=engine_type,
            final_regime=final_regime,
            is_compatible=True,
            details=f"PASS: engine={engine_type.value} compatible with regime={final_regime.value}"
        )
    
    def _check_compatibility(self, engine_type: EngineType, final_regime: FinalRegime) -> bool:
        """Проверка совместимости engine strategy и final_regime.
        
        Правила:
        - TREND engine → TREND_UP, TREND_DOWN, BREAKOUT_UP, BREAKOUT_DOWN, PROBE_TRADE
        - RANGE engine → RANGE
        - NO_TRADE → несовместим для всех
        - NOISE → несовместим для всех (должно быть отфильтровано в GATE 2)
        
        Args:
            engine_type: тип движка
            final_regime: final regime из GATE 2
        
        Returns:
            True если совместимы, False иначе
        """
        # NO_TRADE и NOISE всегда несовместимы (блокировка)
        if final_regime in (FinalRegime.NO_TRADE, FinalRegime.NOISE):
            return False
        
        # TREND engine
        if engine_type == EngineType.TREND:
            # TREND engine совместим с TREND_*, BREAKOUT_*, PROBE_TRADE
            return final_regime in (
                FinalRegime.TREND_UP,
                FinalRegime.TREND_DOWN,
                FinalRegime.BREAKOUT_UP,
                FinalRegime.BREAKOUT_DOWN,
                FinalRegime.PROBE_TRADE
            )
        
        # RANGE engine
        elif engine_type == EngineType.RANGE:
            # RANGE engine совместим только с RANGE
            return final_regime == FinalRegime.RANGE
        
        # Unexpected engine type (failsafe)
        return False
