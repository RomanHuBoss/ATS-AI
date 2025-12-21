"""GATE 6: MLE Decision — размеро-инвариантная оценка price-edge

ТЗ 3.3.2 строка 1023, 1051 (GATE 6: Решение MLE)
ТЗ раздел 1688-1709 (EV_R_price формула и decision thresholds)
ТЗ раздел 2142-2158 (expected_cost_R_postMLE и net_edge check)

Вычисляет:
- EV_R_price = p_success * mu_success_R + p_fail * mu_fail_R
- expected_cost_R_postMLE = expected_cost_bps_post / unit_risk_bps
- net_edge = EV_R_price - expected_cost_R_postMLE
- MLE decision: REJECT/WEAK/NORMAL/STRONG

Интеграция:
- Использует результаты GATE 0-5 (должны быть PASS)
- Size-invariant (не зависит от qty)
- Все расчёты в R units
"""

import math
from dataclasses import dataclass
from enum import Enum
from typing import Final

from src.core.domain.signal import Direction, Signal
from src.gatekeeper.gates.gate_00_warmup_dqs import Gate00Result
from src.gatekeeper.gates.gate_01_drp_killswitch import Gate01Result
from src.gatekeeper.gates.gate_02_mrc_confidence import Gate02Result
from src.gatekeeper.gates.gate_03_strategy_compat import Gate03Result
from src.gatekeeper.gates.gate_04_signal_validation import Gate04Result
from src.gatekeeper.gates.gate_05_pre_sizing import Gate05Result


# =============================================================================
# ENUMS
# =============================================================================


class MLEDecision(str, Enum):
    """MLE Decision categories.
    
    ТЗ 1704-1707:
    - REJECT: EV_R_price <= 0
    - WEAK: 0 < EV_R_price < e1
    - NORMAL: e1 <= EV_R_price < e2
    - STRONG: EV_R_price >= e2
    """
    REJECT = "REJECT"
    WEAK = "WEAK"
    NORMAL = "NORMAL"
    STRONG = "STRONG"


# =============================================================================
# CONSTANTS
# =============================================================================

# Epsilon для unit_risk_bps (защита от деления на 0)
UNIT_RISK_BPS_EPS: Final[float] = 1e-6

# Epsilon для EV_R_price near-zero band
EV_NEAR_ZERO_EPS: Final[float] = 1e-8


# =============================================================================
# RESULT
# =============================================================================


@dataclass(frozen=True)
class Gate06Result:
    """Результат GATE 6."""
    
    entry_allowed: bool
    block_reason: str
    
    # MLE decision
    mle_decision: MLEDecision
    
    # EV and edge metrics
    ev_r_price: float  # Expected value in R units
    expected_cost_r_postmle: float  # Expected cost post-MLE in R units
    net_edge_r: float  # Net edge after costs
    
    # MLE probabilities and outcomes
    p_success: float  # Probability of TP hit
    p_fail: float  # Probability of SL hit
    mu_success_r: float  # TP outcome in R units
    mu_fail_r: float  # SL outcome in R units (-1.0)
    
    # Cost breakdown (bps)
    expected_cost_bps_postmle: float
    tp_exit_cost_bps: float
    
    # Risk multiplier (для использования в GATE 13-14)
    risk_mult: float
    
    # Детали
    details: str


# =============================================================================
# CONFIG
# =============================================================================


@dataclass(frozen=True)
class Gate06Config:
    """Конфигурация GATE 6.
    
    Параметры для MLE decision и risk multipliers.
    """
    
    # MLE decision thresholds (ТЗ 1704-1707)
    ev_r_weak_threshold: float = 0.10  # e1
    ev_r_normal_threshold: float = 0.25  # e2
    
    # Net edge floor (минимальный net edge для PASS)
    net_edge_floor_r: float = 0.05
    
    # Risk multipliers по MLE decision
    risk_mult_reject: float = 0.0  # Не используется (entry blocked)
    risk_mult_weak: float = 0.5
    risk_mult_normal: float = 1.0
    risk_mult_strong: float = 1.25
    
    # Default TP exit cost (если не передан)
    default_tp_exit_cost_bps: float = 4.5  # spread/2 + slippage + impact + fee


# =============================================================================
# GATE 6
# =============================================================================


class Gate06MLEDecision:
    """GATE 6: MLE Decision — размеро-инвариантная оценка price-edge.
    
    Вычисляет:
    1. mu_success_R = (tp_eff_allin - entry_eff_allin) / unit_risk_allin_net
    2. mu_fail_R = -1.0 (SL hit всегда -1R)
    3. EV_R_price = p_success * mu_success_R + p_fail * mu_fail_R
    4. expected_cost_bps_post = entry_cost + p_success*tp_exit_cost + p_fail*sl_exit_cost
    5. expected_cost_R_postMLE = expected_cost_bps_post / unit_risk_bps
    6. net_edge_R = EV_R_price - expected_cost_R_postMLE
    7. MLE decision: REJECT/WEAK/NORMAL/STRONG
    8. Risk multiplier на основе decision
    
    Порядок проверок:
    1. GATE 0-5 блокировки (должны быть PASS)
    2. Вычисление mu_success_R и mu_fail_R
    3. Вычисление EV_R_price
    4. Вычисление expected_cost_R_postMLE
    5. Вычисление net_edge_R
    6. MLE decision на основе EV_R_price
    7. Net edge check
    8. Risk multiplier assignment
    """
    
    def __init__(self, config: Gate06Config | None = None):
        """Инициализация GATE 6.
        
        Args:
            config: конфигурация gate (опционально, используется default)
        """
        self.config = config or Gate06Config()
    
    def evaluate(
        self,
        # GATE 0-5 результаты
        gate00_result: Gate00Result,
        gate01_result: Gate01Result,
        gate02_result: Gate02Result,
        gate03_result: Gate03Result,
        gate04_result: Gate04Result,
        gate05_result: Gate05Result,
        
        # Signal
        signal: Signal,
        
        # MLE probabilities (mock для этой итерации)
        p_success: float,
        p_fail: float,
        
        # TP exit cost (опционально, default из config)
        tp_exit_cost_bps: float | None = None,
    ) -> Gate06Result:
        """Оценка GATE 6: MLE decision и net edge check.
        
        Args:
            gate00_result: результат GATE 0
            gate01_result: результат GATE 1
            gate02_result: результат GATE 2
            gate03_result: результат GATE 3
            gate04_result: результат GATE 4
            gate05_result: результат GATE 5 (pre-sizing)
            signal: engine signal
            p_success: вероятность TP hit [0, 1]
            p_fail: вероятность SL hit [0, 1]
            tp_exit_cost_bps: TP exit cost в bps (опционально)
        
        Returns:
            Gate06Result с MLE decision и net edge metrics
        """
        # 1. Проверка GATE 0-5 блокировок
        if not gate00_result.entry_allowed:
            return self._blocked_result(
                reason=f"gate00_blocked: {gate00_result.block_reason}",
                p_success=p_success,
                p_fail=p_fail,
            )
        
        if not gate01_result.entry_allowed:
            return self._blocked_result(
                reason=f"gate01_blocked: {gate01_result.block_reason}",
                p_success=p_success,
                p_fail=p_fail,
            )
        
        if not gate02_result.entry_allowed:
            return self._blocked_result(
                reason=f"gate02_blocked: {gate02_result.block_reason}",
                p_success=p_success,
                p_fail=p_fail,
            )
        
        if not gate03_result.entry_allowed:
            return self._blocked_result(
                reason=f"gate03_blocked: {gate03_result.block_reason}",
                p_success=p_success,
                p_fail=p_fail,
            )
        
        if not gate04_result.entry_allowed:
            return self._blocked_result(
                reason=f"gate04_blocked: {gate04_result.block_reason}",
                p_success=p_success,
                p_fail=p_fail,
            )
        
        if not gate05_result.entry_allowed:
            return self._blocked_result(
                reason=f"gate05_blocked: {gate05_result.block_reason}",
                p_success=p_success,
                p_fail=p_fail,
            )
        
        # 2. Валидация вероятностей
        if not (0.0 <= p_success <= 1.0):
            return self._blocked_result(
                reason=f"invalid_p_success: {p_success} (must be [0, 1])",
                p_success=p_success,
                p_fail=p_fail,
            )
        
        if not (0.0 <= p_fail <= 1.0):
            return self._blocked_result(
                reason=f"invalid_p_fail: {p_fail} (must be [0, 1])",
                p_success=p_success,
                p_fail=p_fail,
            )
        
        # Примечание: p_success + p_fail может быть < 1.0 (есть p_neutral)
        # Для упрощённой модели в этой итерации мы используем только p_success и p_fail
        
        # 3. Вычисление mu_success_R
        # mu_success_R = |tp_eff_allin - entry_eff_allin| / unit_risk_allin_net
        # Используем абсолютное значение для корректной работы с SHORT позициями
        entry_eff = gate05_result.entry_eff_allin
        tp_eff = gate05_result.tp_eff_allin
        unit_risk = gate05_result.unit_risk_allin_net
        
        # Защита от деления на 0
        if unit_risk < 1e-12:
            return self._blocked_result(
                reason=f"unit_risk_too_small: {unit_risk} (must be > 1e-12)",
                p_success=p_success,
                p_fail=p_fail,
            )
        
        # Для LONG: tp_eff > entry_eff, для SHORT: tp_eff < entry_eff
        # Используем abs для правильного расчёта mu_success_R в обоих направлениях
        tp_distance = abs(tp_eff - entry_eff)
        mu_success_r = tp_distance / unit_risk
        
        # 4. mu_fail_R всегда -1.0 (SL hit = -1R по определению)
        mu_fail_r = -1.0
        
        # 5. Вычисление EV_R_price
        # EV_R_price = p_success * mu_success_R + p_fail * mu_fail_R
        ev_r_price = p_success * mu_success_r + p_fail * mu_fail_r
        
        # 6. Вычисление expected_cost_bps_postMLE
        # ТЗ 2145-2148: expected_cost_bps_post = entry_cost + p_success*tp_exit + p_fail*sl_exit
        tp_exit_cost_bps = (
            tp_exit_cost_bps 
            if tp_exit_cost_bps is not None 
            else self.config.default_tp_exit_cost_bps
        )
        
        expected_cost_bps_postmle = (
            gate05_result.entry_cost_bps
            + p_success * tp_exit_cost_bps
            + p_fail * gate05_result.sl_exit_cost_bps
        )
        
        # 7. Вычисление expected_cost_R_postMLE
        # ТЗ 2149: expected_cost_R_postMLE = expected_cost_bps_post / unit_risk_bps
        unit_risk_bps = gate05_result.unit_risk_bps
        expected_cost_r_postmle = expected_cost_bps_postmle / max(unit_risk_bps, UNIT_RISK_BPS_EPS)
        
        # 8. Вычисление net_edge_R
        # ТЗ 2155: net_edge_R = EV_R_price - expected_cost_R_postMLE - funding_cost_R
        # funding_cost_R = 0 для этой итерации (GATE 9 будет позже)
        net_edge_r = ev_r_price - expected_cost_r_postmle
        
        # 9. MLE Decision на основе EV_R_price
        # ТЗ 1704-1707
        if ev_r_price <= EV_NEAR_ZERO_EPS:
            mle_decision = MLEDecision.REJECT
            risk_mult = self.config.risk_mult_reject
        elif ev_r_price < self.config.ev_r_weak_threshold:
            mle_decision = MLEDecision.WEAK
            risk_mult = self.config.risk_mult_weak
        elif ev_r_price < self.config.ev_r_normal_threshold:
            mle_decision = MLEDecision.NORMAL
            risk_mult = self.config.risk_mult_normal
        else:
            mle_decision = MLEDecision.STRONG
            risk_mult = self.config.risk_mult_strong
        
        # 10. MLE Decision REJECT check (сначала проверяем EV)
        # ТЗ 1704: EV_R_price <= 0 → REJECT
        if mle_decision == MLEDecision.REJECT:
            return Gate06Result(
                entry_allowed=False,
                block_reason=f"mle_reject: EV_R_price={ev_r_price:.4f}R <= 0",
                mle_decision=mle_decision,
                ev_r_price=ev_r_price,
                expected_cost_r_postmle=expected_cost_r_postmle,
                net_edge_r=net_edge_r,
                p_success=p_success,
                p_fail=p_fail,
                mu_success_r=mu_success_r,
                mu_fail_r=mu_fail_r,
                expected_cost_bps_postmle=expected_cost_bps_postmle,
                tp_exit_cost_bps=tp_exit_cost_bps,
                risk_mult=0.0,  # Blocked, no risk allowed
                details=f"MLE REJECT: EV_R_price={ev_r_price:.4f}R <= 0",
            )
        
        # 11. Net edge check (после MLE decision)
        # ТЗ 2156-2157: если net_edge < net_edge_floor → REJECT
        if net_edge_r < self.config.net_edge_floor_r:
            return Gate06Result(
                entry_allowed=False,
                block_reason=f"net_edge_too_low: {net_edge_r:.4f}R < {self.config.net_edge_floor_r:.4f}R",
                mle_decision=MLEDecision.REJECT,
                ev_r_price=ev_r_price,
                expected_cost_r_postmle=expected_cost_r_postmle,
                net_edge_r=net_edge_r,
                p_success=p_success,
                p_fail=p_fail,
                mu_success_r=mu_success_r,
                mu_fail_r=mu_fail_r,
                expected_cost_bps_postmle=expected_cost_bps_postmle,
                tp_exit_cost_bps=tp_exit_cost_bps,
                risk_mult=0.0,  # Blocked, no risk allowed
                details=(
                    f"MLE REJECT: net_edge={net_edge_r:.4f}R < floor={self.config.net_edge_floor_r:.4f}R"
                ),
            )
        
        # 12. PASS
        return Gate06Result(
            entry_allowed=True,
            block_reason="",
            mle_decision=mle_decision,
            ev_r_price=ev_r_price,
            expected_cost_r_postmle=expected_cost_r_postmle,
            net_edge_r=net_edge_r,
            p_success=p_success,
            p_fail=p_fail,
            mu_success_r=mu_success_r,
            mu_fail_r=mu_fail_r,
            expected_cost_bps_postmle=expected_cost_bps_postmle,
            tp_exit_cost_bps=tp_exit_cost_bps,
            risk_mult=risk_mult,
            details=(
                f"MLE {mle_decision.value}: EV_R={ev_r_price:.4f}R, "
                f"net_edge={net_edge_r:.4f}R, risk_mult={risk_mult:.2f}, "
                f"p_success={p_success:.3f}, p_fail={p_fail:.3f}"
            ),
        )
    
    def _blocked_result(
        self,
        reason: str,
        p_success: float,
        p_fail: float,
    ) -> Gate06Result:
        """Создание blocked result.
        
        Args:
            reason: причина блокировки
            p_success: вероятность TP hit
            p_fail: вероятность SL hit
        
        Returns:
            Gate06Result с entry_allowed=False
        """
        return Gate06Result(
            entry_allowed=False,
            block_reason=reason,
            mle_decision=MLEDecision.REJECT,
            ev_r_price=0.0,
            expected_cost_r_postmle=0.0,
            net_edge_r=0.0,
            p_success=p_success,
            p_fail=p_fail,
            mu_success_r=0.0,
            mu_fail_r=-1.0,
            expected_cost_bps_postmle=0.0,
            tp_exit_cost_bps=0.0,
            risk_mult=0.0,
            details=reason,
        )
