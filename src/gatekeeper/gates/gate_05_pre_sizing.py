"""GATE 5: Pre-sizing + размеро-инвариантная оценка издержек

ТЗ 3.3.2 строка 1022 (GATE 5: Pre-sizing + size-invariant издержки/единицы)
ТЗ раздел 2128-2150 (unit_risk_bps, expected_cost_R_preMLE)

Вычисляет размеро-инвариантные метрики:
- unit_risk_bps (не зависит от qty)
- expected_cost_R_preMLE (до MLE decision, worst-case с SL exit)
- Все издержки через EffectivePrices

Интеграция:
- Использует результаты GATE 0-4 (должны быть PASS)
- Использует EffectivePrices для вычисления издержек
- Не использует qty_actual (size-invariant)
- expected_cost_R_preMLE вычисляется до MLE (используется SL exit)
"""

import math
from dataclasses import dataclass
from typing import Final

from src.core.domain.signal import Direction, Signal
from src.core.math.effective_prices import PositionSide, calculate_effective_prices
from src.gatekeeper.gates.gate_00_warmup_dqs import Gate00Result
from src.gatekeeper.gates.gate_01_drp_killswitch import Gate01Result
from src.gatekeeper.gates.gate_02_mrc_confidence import Gate02Result
from src.gatekeeper.gates.gate_03_strategy_compat import Gate03Result
from src.gatekeeper.gates.gate_04_signal_validation import Gate04Result


# =============================================================================
# CONSTANTS
# =============================================================================

# Epsilon для цен (ТЗ Appendix C.1)
PRICE_EPS_USD: Final[float] = 1e-8

# Epsilon для unit_risk_bps (защита от деления на 0)
UNIT_RISK_BPS_EPS: Final[float] = 1e-6


# =============================================================================
# RESULT
# =============================================================================


@dataclass(frozen=True)
class Gate05Result:
    """Результат GATE 5."""
    
    entry_allowed: bool
    block_reason: str
    
    # Size-invariant metrics
    unit_risk_allin_net: float  # All-in unit risk (USD)
    unit_risk_bps: float  # Unit risk in basis points
    
    # Expected costs (preMLE)
    entry_cost_bps: float  # Entry costs in bps
    sl_exit_cost_bps: float  # SL exit costs in bps
    expected_cost_bps_preMLE: float  # Total expected cost in bps (entry + SL exit)
    expected_cost_R_preMLE: float  # Expected cost in R units
    
    # Effective prices (all-in)
    entry_eff_allin: float
    tp_eff_allin: float
    sl_eff_allin: float
    
    # Детали
    details: str


# =============================================================================
# CONFIG
# =============================================================================


@dataclass(frozen=True)
class Gate05Config:
    """Конфигурация GATE 5.
    
    Параметры для pre-sizing и вычисления издержек.
    """
    
    # Default costs (можно переопределить через параметры evaluate)
    default_spread_bps: float = 2.0
    default_fee_entry_bps: float = 3.0
    default_fee_exit_bps: float = 3.0
    default_slippage_entry_bps: float = 1.0
    default_slippage_tp_bps: float = 1.0
    default_slippage_stop_bps: float = 2.0
    default_impact_entry_bps: float = 0.5
    default_impact_exit_bps: float = 0.5
    default_impact_stop_bps: float = 1.0
    default_stop_slippage_mult: float = 2.0


# =============================================================================
# GATE 5
# =============================================================================


class Gate05PreSizing:
    """GATE 5: Pre-sizing + размеро-инвариантная оценка издержек.
    
    Вычисляет размеро-инвариантные метрики для оценки издержек и риска:
    1. Эффективные цены (all-in) через EffectivePrices
    2. unit_risk_allin_net = |entry_eff_allin - sl_eff_allin|
    3. unit_risk_bps = 10000 * unit_risk_allin_net / max(entry_price, price_eps)
    4. expected_cost_bps_preMLE = entry_cost + sl_exit_cost
    5. expected_cost_R_preMLE = expected_cost_bps / unit_risk_bps
    
    Порядок проверок:
    1. GATE 0-4 блокировки (должны быть PASS)
    2. Вычисление эффективных цен
    3. Вычисление unit_risk_bps
    4. Вычисление expected_cost_R_preMLE
    """
    
    def __init__(self, config: Gate05Config | None = None):
        """Инициализация GATE 5.
        
        Args:
            config: конфигурация gate (опционально, используется default)
        """
        self.config = config or Gate05Config()
    
    def evaluate(
        self,
        # GATE 0-4 результаты
        gate00_result: Gate00Result,
        gate01_result: Gate01Result,
        gate02_result: Gate02Result,
        gate03_result: Gate03Result,
        gate04_result: Gate04Result,
        
        # Signal и costs
        signal: Signal,
        
        # Costs (опционально, используются defaults из config)
        spread_bps: float | None = None,
        fee_entry_bps: float | None = None,
        fee_exit_bps: float | None = None,
        slippage_entry_bps: float | None = None,
        slippage_tp_bps: float | None = None,
        slippage_stop_bps: float | None = None,
        impact_entry_bps: float | None = None,
        impact_exit_bps: float | None = None,
        impact_stop_bps: float | None = None,
        stop_slippage_mult: float | None = None,
    ) -> Gate05Result:
        """Оценка GATE 5: pre-sizing и размеро-инвариантные издержки.
        
        Args:
            gate00_result: результат GATE 0 (DQS и DRP state)
            gate01_result: результат GATE 1 (trading mode, manual halt)
            gate02_result: результат GATE 2 (final_regime)
            gate03_result: результат GATE 3 (strategy compatibility)
            gate04_result: результат GATE 4 (signal validation)
            signal: engine signal
            spread_bps: spread в bps (опционально)
            fee_entry_bps: entry fee в bps (опционально)
            fee_exit_bps: exit fee в bps (опционально)
            slippage_entry_bps: entry slippage в bps (опционально)
            slippage_tp_bps: TP slippage в bps (опционально)
            slippage_stop_bps: stop slippage в bps (опционально)
            impact_entry_bps: entry impact в bps (опционально)
            impact_exit_bps: exit impact в bps (опционально)
            impact_stop_bps: stop impact в bps (опционально)
            stop_slippage_mult: stop slippage multiplier (опционально)
        
        Returns:
            Gate05Result с размеро-инвариантными метриками
        """
        # 1. Проверка GATE 0-4 блокировок
        if not gate00_result.entry_allowed:
            return self._blocked_result(
                reason=f"gate00_blocked: {gate00_result.block_reason}"
            )
        
        if not gate01_result.entry_allowed:
            return self._blocked_result(
                reason=f"gate01_blocked: {gate01_result.block_reason}"
            )
        
        if not gate02_result.entry_allowed:
            return self._blocked_result(
                reason=f"gate02_blocked: {gate02_result.block_reason}"
            )
        
        if not gate03_result.entry_allowed:
            return self._blocked_result(
                reason=f"gate03_blocked: {gate03_result.block_reason}"
            )
        
        if not gate04_result.entry_allowed:
            return self._blocked_result(
                reason=f"gate04_blocked: {gate04_result.block_reason}"
            )
        
        # 2. Использование defaults для costs если не переданы
        spread_bps = spread_bps if spread_bps is not None else self.config.default_spread_bps
        fee_entry_bps = fee_entry_bps if fee_entry_bps is not None else self.config.default_fee_entry_bps
        fee_exit_bps = fee_exit_bps if fee_exit_bps is not None else self.config.default_fee_exit_bps
        slippage_entry_bps = slippage_entry_bps if slippage_entry_bps is not None else self.config.default_slippage_entry_bps
        slippage_tp_bps = slippage_tp_bps if slippage_tp_bps is not None else self.config.default_slippage_tp_bps
        slippage_stop_bps = slippage_stop_bps if slippage_stop_bps is not None else self.config.default_slippage_stop_bps
        impact_entry_bps = impact_entry_bps if impact_entry_bps is not None else self.config.default_impact_entry_bps
        impact_exit_bps = impact_exit_bps if impact_exit_bps is not None else self.config.default_impact_exit_bps
        impact_stop_bps = impact_stop_bps if impact_stop_bps is not None else self.config.default_impact_stop_bps
        stop_slippage_mult = stop_slippage_mult if stop_slippage_mult is not None else self.config.default_stop_slippage_mult
        
        # 3. Вычисление эффективных цен
        side = PositionSide.LONG if signal.direction == Direction.LONG else PositionSide.SHORT
        
        entry_eff_allin, tp_eff_allin, sl_eff_allin = calculate_effective_prices(
            side=side,
            entry_price=signal.levels.entry_price,
            tp_price=signal.levels.take_profit,
            sl_price=signal.levels.stop_loss,
            spread_bps=spread_bps,
            fee_entry_bps=fee_entry_bps,
            fee_exit_bps=fee_exit_bps,
            slippage_entry_bps=slippage_entry_bps,
            slippage_tp_bps=slippage_tp_bps,
            slippage_stop_bps=slippage_stop_bps,
            impact_entry_bps=impact_entry_bps,
            impact_exit_bps=impact_exit_bps,
            impact_stop_bps=impact_stop_bps,
            stop_slippage_mult=stop_slippage_mult,
        )
        
        # 4. Вычисление unit_risk (all-in, net)
        unit_risk_allin_net = abs(entry_eff_allin - sl_eff_allin)
        
        # 5. Вычисление unit_risk_bps (size-invariant)
        # ТЗ 2128-2131: unit_risk_bps = 10000 * unit_risk_allin_net / max(entry_price, price_eps)
        entry_price_ref = max(signal.levels.entry_price, PRICE_EPS_USD)
        unit_risk_bps = 10000.0 * unit_risk_allin_net / entry_price_ref
        
        # 6. Вычисление entry cost (bps)
        # entry_cost = spread/2 + slippage + impact + fee
        entry_cost_bps = (
            0.5 * spread_bps
            + slippage_entry_bps
            + impact_entry_bps
            + fee_entry_bps
        )
        
        # 7. Вычисление SL exit cost (bps)
        # sl_exit_cost = spread/2 + stop_slippage_mult * slippage + impact + fee
        sl_exit_cost_bps = (
            0.5 * spread_bps
            + stop_slippage_mult * slippage_stop_bps
            + impact_stop_bps
            + fee_exit_bps
        )
        
        # 8. Вычисление expected_cost_bps_preMLE
        # ТЗ 2136-2139: expected_cost_bps_pre = entry_cost + 1.0 * sl_exit_cost
        # До MLE decision используем worst-case (SL exit)
        expected_cost_bps_preMLE = entry_cost_bps + 1.0 * sl_exit_cost_bps
        
        # 9. Вычисление expected_cost_R_preMLE
        # ТЗ 2139: expected_cost_R_preMLE = expected_cost_bps_pre / max(unit_risk_bps, eps)
        expected_cost_R_preMLE = expected_cost_bps_preMLE / max(unit_risk_bps, UNIT_RISK_BPS_EPS)
        
        # 10. PASS
        return Gate05Result(
            entry_allowed=True,
            block_reason="",
            unit_risk_allin_net=unit_risk_allin_net,
            unit_risk_bps=unit_risk_bps,
            entry_cost_bps=entry_cost_bps,
            sl_exit_cost_bps=sl_exit_cost_bps,
            expected_cost_bps_preMLE=expected_cost_bps_preMLE,
            expected_cost_R_preMLE=expected_cost_R_preMLE,
            entry_eff_allin=entry_eff_allin,
            tp_eff_allin=tp_eff_allin,
            sl_eff_allin=sl_eff_allin,
            details=(
                f"Pre-sizing: unit_risk={unit_risk_bps:.2f} bps, "
                f"expected_cost_R_preMLE={expected_cost_R_preMLE:.4f}R, "
                f"entry_cost={entry_cost_bps:.2f} bps, "
                f"sl_exit_cost={sl_exit_cost_bps:.2f} bps"
            ),
        )
    
    def _blocked_result(self, reason: str) -> Gate05Result:
        """Создание blocked result.
        
        Args:
            reason: причина блокировки
        
        Returns:
            Gate05Result с entry_allowed=False
        """
        return Gate05Result(
            entry_allowed=False,
            block_reason=reason,
            unit_risk_allin_net=0.0,
            unit_risk_bps=0.0,
            entry_cost_bps=0.0,
            sl_exit_cost_bps=0.0,
            expected_cost_bps_preMLE=0.0,
            expected_cost_R_preMLE=0.0,
            entry_eff_allin=0.0,
            tp_eff_allin=0.0,
            sl_eff_allin=0.0,
            details=reason,
        )
