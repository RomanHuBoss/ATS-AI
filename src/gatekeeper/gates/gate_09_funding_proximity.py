"""GATE 9: Funding Filter + Proximity + Blackout

ТЗ 3.3.2 строка 1026, 1054 (GATE 9: Funding фильтр + proximity + blackout)
ТЗ раздел 3.3.4: Funding фильтр (size-invariant R)

Проверяет:
- Funding cost в R units (size-invariant)
- Net Yield после funding costs
- Proximity model (близость к событию funding)
- Blackout conditions (запрет торговли перед funding)

Funding sign convention:
- funding_rate > 0: LONG платит, SHORT получает
- direction_sign = +1 для LONG, -1 для SHORT
- funding_pnl_frac = - direction_sign * funding_rate * n_events

Net Yield calculation:
- EV_R_price_net = EV_R_price - expected_cost_R_used
- Net_Yield_R = EV_R_price_net - funding_cost_R + funding_bonus_R_used

Proximity model (непрерывная):
- tau = clip((soft_sec - time_to_funding) / (soft_sec - hard_sec), 0, 1)
- proximity_mult = 1 - (1 - mult_min) * (tau ^ power)

Blackout (hard block):
- Близость к funding event
- Значимость funding cost
- Короткий holding horizon

Интеграция:
- Использует результаты GATE 0-8 (должны быть PASS)
- Size-invariant (не зависит от qty)
- Все расчёты в R units
"""

import math
from dataclasses import dataclass
from typing import Final

from src.core.domain.market_state import MarketState
from src.core.domain.signal import Direction, Signal
from src.gatekeeper.gates.gate_00_warmup_dqs import Gate00Result
from src.gatekeeper.gates.gate_01_drp_killswitch import Gate01Result
from src.gatekeeper.gates.gate_02_mrc_confidence import Gate02Result
from src.gatekeeper.gates.gate_03_strategy_compat import Gate03Result
from src.gatekeeper.gates.gate_04_signal_validation import Gate04Result
from src.gatekeeper.gates.gate_05_pre_sizing import Gate05Result
from src.gatekeeper.gates.gate_06_mle_decision import Gate06Result
from src.gatekeeper.gates.gate_07_liquidity_check import Gate07Result
from src.gatekeeper.gates.gate_08_gap_glitch import Gate08Result


# =============================================================================
# CONSTANTS
# =============================================================================

# Epsilon для защиты от деления на 0
UNIT_RISK_EPS: Final[float] = 1e-9
PRICE_EPS: Final[float] = 1e-8
EV_EPS: Final[float] = 1e-9

# Minimum unit risk для funding calculations (absolute floor)
UNIT_RISK_MIN_ABSOLUTE_FOR_FUNDING: Final[float] = 1e-6


# =============================================================================
# DATA CLASSES
# =============================================================================


@dataclass(frozen=True)
class FundingMetrics:
    """Метрики funding расчётов."""
    
    # Input data
    funding_rate: float  # Текущий funding rate (биржевой знак)
    funding_period_hours: float  # Период funding (обычно 8 часов)
    time_to_next_funding_sec: int  # Время до следующего funding
    expected_holding_hours: float  # Ожидаемое время удержания позиции
    
    # Calculated events
    n_events_raw: int  # Детерминированное число событий funding
    n_events: float  # Сглаженное число событий (может быть дробным)
    
    # Funding PnL
    direction_sign: int  # +1 для LONG, -1 для SHORT
    funding_pnl_frac: float  # Funding PnL в долях notional
    funding_r: float  # Funding в R units (может быть + или -)
    funding_cost_r: float  # max(0, -funding_R) — всегда >= 0
    funding_bonus_r: float  # max(0, funding_R) — всегда >= 0
    
    # Used in Net Yield
    funding_bonus_r_used: float  # 0 или funding_bonus_R в зависимости от политики


@dataclass(frozen=True)
class ProximityMetrics:
    """Метрики proximity model."""
    
    # Proximity calculation
    tau: float  # Normalized proximity (0 = далеко, 1 = близко)
    funding_proximity_mult: float  # Multiplier (1.0 = no penalty, < 1.0 = penalty)
    
    # Details
    is_near_funding: bool  # True если tau > 0
    proximity_penalty_r: float  # Штраф proximity в R units (для диагностики)


@dataclass(frozen=True)
class BlackoutCheck:
    """Результат проверки blackout conditions."""
    
    # Blackout conditions
    time_condition: bool  # Близость к funding event
    cost_condition: bool  # funding_cost_R > 0
    holding_condition: bool  # Короткий holding horizon
    significance_condition: bool  # Значимость funding cost
    
    # Result
    blackout_triggered: bool  # AND всех условий
    blackout_reason: str  # Описание причины (если triggered)


@dataclass(frozen=True)
class Gate09Result:
    """Результат GATE 9."""
    
    entry_allowed: bool
    block_reason: str
    
    # Funding metrics
    funding_metrics: FundingMetrics
    
    # Net Yield
    ev_r_price: float  # From GATE 6
    expected_cost_r_used: float  # From GATE 5/6
    ev_r_price_net: float  # After execution costs
    net_yield_r: float  # After funding costs
    
    # Proximity model
    proximity_metrics: ProximityMetrics
    
    # Blackout check
    blackout_check: BlackoutCheck
    
    # Risk multiplier (для использования в GATE 13-14)
    funding_risk_mult: float  # Базовый multiplier
    combined_risk_mult: float  # С учётом proximity
    
    # Детали
    details: str


# =============================================================================
# CONFIG
# =============================================================================


@dataclass(frozen=True)
class Gate09Config:
    """Конфигурация GATE 9.
    
    Параметры для funding filter, proximity model и blackout conditions.
    ТЗ раздел 3.3.4 + конфиг из appendix.
    """
    
    # Minimum unit risk для funding calculations
    unit_risk_min_for_funding: float = 0.0005  # 5 bps (0.05%)
    
    # Funding cost thresholds (R units)
    funding_cost_soft_r: float = 0.10  # Soft warning
    funding_cost_block_r: float = 0.25  # Hard block
    
    # Net Yield threshold (R units)
    min_net_yield_r: float = 0.05  # Minimum net yield после всех издержек
    
    # Funding credit policy
    funding_credit_allowed: bool = False  # Учитывать ли funding_bonus_R
    
    # Proximity model parameters
    funding_proximity_soft_sec: int = 1800  # 30 минут (soft boundary)
    funding_proximity_hard_sec: int = 300   # 5 минут (hard boundary)
    funding_proximity_power: float = 2.0    # Power для smooth transition
    funding_proximity_mult_min: float = 0.80  # Minimum multiplier
    
    # Blackout conditions
    funding_blackout_minutes: int = 10  # Окно blackout перед funding
    funding_blackout_max_holding_hours: float = 12.0  # Max holding для blackout
    funding_blackout_cost_share_threshold: float = 0.40  # Min cost significance
    funding_blackout_ev_eps: float = 0.05  # Epsilon для EV_R_price
    funding_event_inclusion_epsilon_sec: int = 2  # Epsilon для time condition
    
    # Smoothing parameters
    funding_count_smoothing_width_sec: int = 60  # EMA width для n_events
    
    # Risk multiplier parameters
    funding_risk_mult_base: float = 1.0  # Базовый multiplier (без funding penalty)
    funding_risk_mult_soft_penalty: float = 0.95  # При soft threshold
    funding_risk_mult_hard_penalty: float = 0.85  # При приближении к block


# =============================================================================
# GATE 9
# =============================================================================


class Gate09FundingProximity:
    """GATE 9: Funding Filter + Proximity + Blackout.
    
    Size-invariant проверка funding costs, proximity model и blackout conditions.
    
    Вычисляет:
    1. n_events — число funding событий на горизонте удержания
    2. funding_R — ожидаемый funding cost/bonus в R units
    3. Net_Yield_R — net yield после всех издержек
    4. funding_proximity_mult — proximity penalty
    5. blackout_triggered — hard block при выполнении условий
    6. funding_risk_mult — multiplier для GATE 13-14
    
    Порядок проверок:
    1. GATE 0-8 блокировки (должны быть PASS)
    2. Unit risk check (не слишком мал для funding calculations)
    3. Funding events count
    4. Funding cost/bonus в R units
    5. Net Yield check
    6. Proximity model
    7. Blackout conditions
    """
    
    def __init__(self, config: Gate09Config | None = None):
        """Initialize GATE 9.
        
        Args:
            config: Конфигурация gate (default: Gate09Config())
        """
        self.config = config or Gate09Config()
    
    def evaluate(
        self,
        signal: Signal,
        market_state: MarketState,
        gate00: Gate00Result,
        gate01: Gate01Result,
        gate02: Gate02Result,
        gate03: Gate03Result,
        gate04: Gate04Result,
        gate05: Gate05Result,
        gate06: Gate06Result,
        gate07: Gate07Result,
        gate08: Gate08Result,
    ) -> Gate09Result:
        """Evaluate GATE 9.
        
        Args:
            signal: Engine signal
            market_state: Market state
            gate00-gate08: Результаты предыдущих gates
        
        Returns:
            Gate09Result с результатами проверки
        """
        # =====================================================================
        # 1. Check GATE 0-8 blocks
        # =====================================================================
        
        if not gate00.entry_allowed:
            return self._create_blocked_result(
                "gate00_blocked",
                gate00, gate05, gate06,
                signal.direction,
                market_state,
            )
        
        if not gate01.entry_allowed:
            return self._create_blocked_result(
                "gate01_blocked",
                gate00, gate05, gate06,
                signal.direction,
                market_state,
            )
        
        if not gate02.entry_allowed:
            return self._create_blocked_result(
                "gate02_blocked",
                gate00, gate05, gate06,
                signal.direction,
                market_state,
            )
        
        if not gate03.entry_allowed:
            return self._create_blocked_result(
                "gate03_blocked",
                gate00, gate05, gate06,
                signal.direction,
                market_state,
            )
        
        if not gate04.entry_allowed:
            return self._create_blocked_result(
                "gate04_blocked",
                gate00, gate05, gate06,
                signal.direction,
                market_state,
            )
        
        if not gate05.entry_allowed:
            return self._create_blocked_result(
                "gate05_blocked",
                gate00, gate05, gate06,
                signal.direction,
                market_state,
            )
        
        if not gate06.entry_allowed:
            return self._create_blocked_result(
                "gate06_blocked",
                gate00, gate05, gate06,
                signal.direction,
                market_state,
            )
        
        if not gate07.entry_allowed:
            return self._create_blocked_result(
                "gate07_blocked",
                gate00, gate05, gate06,
                signal.direction,
                market_state,
            )
        
        if not gate08.entry_allowed:
            return self._create_blocked_result(
                "gate08_blocked",
                gate00, gate05, gate06,
                signal.direction,
                market_state,
            )
        
        # =====================================================================
        # 2. Extract data from previous gates
        # =====================================================================
        
        # Unit risk from GATE 5 (all-in net unit risk)
        unit_risk_allin_net = gate05.unit_risk_allin_net
        
        # EV and costs from GATE 6
        ev_r_price = gate06.ev_r_price
        expected_cost_r_postmle = gate06.expected_cost_r_postmle
        
        # Expected holding hours from signal
        expected_holding_hours = signal.context.expected_holding_hours
        
        # Entry price (reference) from signal.levels
        entry_price_ref = max(signal.levels.entry_price, PRICE_EPS)
        
        # Direction sign (+1 for LONG, -1 for SHORT)
        direction_sign = 1 if signal.direction == Direction.LONG else -1
        
        # =====================================================================
        # 3. Unit risk check
        # =====================================================================
        
        if unit_risk_allin_net < self.config.unit_risk_min_for_funding:
            return self._create_blocked_result(
                "funding_unit_risk_too_small_block",
                gate00, gate05, gate06,
                signal.direction,
                market_state,
                details=(
                    f"unit_risk_allin_net={unit_risk_allin_net:.6f} < "
                    f"min_for_funding={self.config.unit_risk_min_for_funding:.6f}"
                ),
            )
        
        # =====================================================================
        # 4. Calculate funding events count (ТЗ 3.3.4.2)
        # =====================================================================
        
        funding_metrics = self._calculate_funding_metrics(
            funding_rate=market_state.derivatives.funding_rate_spot,
            funding_period_hours=market_state.derivatives.funding_period_hours,
            time_to_next_funding_sec=market_state.derivatives.time_to_next_funding_sec,
            expected_holding_hours=expected_holding_hours,
            direction_sign=direction_sign,
            entry_price_ref=entry_price_ref,
            unit_risk_allin_net=unit_risk_allin_net,
        )
        
        # =====================================================================
        # 5. Net Yield calculation (ТЗ 3.3.4.4)
        # =====================================================================
        
        # EV_R_price_net = EV_R_price - expected_cost_R_used
        ev_r_price_net = ev_r_price - expected_cost_r_postmle
        
        # funding_bonus_R_used (политика)
        funding_bonus_r_used = (
            funding_metrics.funding_bonus_r if self.config.funding_credit_allowed else 0.0
        )
        
        # Net_Yield_R = EV_R_price_net - funding_cost_R + funding_bonus_R_used
        net_yield_r = (
            ev_r_price_net
            - funding_metrics.funding_cost_r
            + funding_bonus_r_used
        )
        
        # =====================================================================
        # 6. Funding cost hard block (ТЗ 3.3.4.4)
        # =====================================================================
        
        if funding_metrics.funding_cost_r >= self.config.funding_cost_block_r:
            proximity_metrics = self._calculate_proximity_metrics(
                time_to_next_funding_sec=market_state.derivatives.time_to_next_funding_sec,
                funding_cost_r=funding_metrics.funding_cost_r,
            )
            blackout_check = self._check_blackout_conditions(
                time_to_next_funding_sec=market_state.derivatives.time_to_next_funding_sec,
                funding_cost_r=funding_metrics.funding_cost_r,
                expected_holding_hours=expected_holding_hours,
                ev_r_price=ev_r_price,
            )
            
            return Gate09Result(
                entry_allowed=False,
                block_reason="funding_cost_block",
                funding_metrics=funding_metrics,
                ev_r_price=ev_r_price,
                expected_cost_r_used=expected_cost_r_postmle,
                ev_r_price_net=ev_r_price_net,
                net_yield_r=net_yield_r,
                proximity_metrics=proximity_metrics,
                blackout_check=blackout_check,
                funding_risk_mult=self.config.funding_risk_mult_hard_penalty,
                combined_risk_mult=self.config.funding_risk_mult_hard_penalty,
                details=(
                    f"funding_cost_R={funding_metrics.funding_cost_r:.4f} >= "
                    f"block_threshold={self.config.funding_cost_block_r:.4f}"
                ),
            )
        
        # =====================================================================
        # 7. Net Yield hard block (ТЗ 3.3.4.4)
        # =====================================================================
        
        if net_yield_r < self.config.min_net_yield_r:
            proximity_metrics = self._calculate_proximity_metrics(
                time_to_next_funding_sec=market_state.derivatives.time_to_next_funding_sec,
                funding_cost_r=funding_metrics.funding_cost_r,
            )
            blackout_check = self._check_blackout_conditions(
                time_to_next_funding_sec=market_state.derivatives.time_to_next_funding_sec,
                funding_cost_r=funding_metrics.funding_cost_r,
                expected_holding_hours=expected_holding_hours,
                ev_r_price=ev_r_price,
            )
            
            return Gate09Result(
                entry_allowed=False,
                block_reason="funding_net_yield_block",
                funding_metrics=funding_metrics,
                ev_r_price=ev_r_price,
                expected_cost_r_used=expected_cost_r_postmle,
                ev_r_price_net=ev_r_price_net,
                net_yield_r=net_yield_r,
                proximity_metrics=proximity_metrics,
                blackout_check=blackout_check,
                funding_risk_mult=self.config.funding_risk_mult_hard_penalty,
                combined_risk_mult=self.config.funding_risk_mult_hard_penalty,
                details=(
                    f"Net_Yield_R={net_yield_r:.4f} < "
                    f"min_net_yield_R={self.config.min_net_yield_r:.4f}"
                ),
            )
        
        # =====================================================================
        # 8. Proximity model (ТЗ 3.3.4.5)
        # =====================================================================
        
        proximity_metrics = self._calculate_proximity_metrics(
            time_to_next_funding_sec=market_state.derivatives.time_to_next_funding_sec,
            funding_cost_r=funding_metrics.funding_cost_r,
        )
        
        # =====================================================================
        # 9. Blackout conditions (ТЗ 3.3.4.6)
        # =====================================================================
        
        blackout_check = self._check_blackout_conditions(
            time_to_next_funding_sec=market_state.derivatives.time_to_next_funding_sec,
            funding_cost_r=funding_metrics.funding_cost_r,
            expected_holding_hours=expected_holding_hours,
            ev_r_price=ev_r_price,
        )
        
        if blackout_check.blackout_triggered:
            return Gate09Result(
                entry_allowed=False,
                block_reason="funding_blackout_block",
                funding_metrics=funding_metrics,
                ev_r_price=ev_r_price,
                expected_cost_r_used=expected_cost_r_postmle,
                ev_r_price_net=ev_r_price_net,
                net_yield_r=net_yield_r,
                proximity_metrics=proximity_metrics,
                blackout_check=blackout_check,
                funding_risk_mult=0.0,  # Blackout = full risk off
                combined_risk_mult=0.0,
                details=blackout_check.blackout_reason,
            )
        
        # =====================================================================
        # 10. Calculate risk multipliers
        # =====================================================================
        
        # Base funding risk multiplier (без proximity)
        if funding_metrics.funding_cost_r >= self.config.funding_cost_soft_r:
            # Soft penalty для funding cost между soft и block thresholds
            t = min(
                (funding_metrics.funding_cost_r - self.config.funding_cost_soft_r)
                / max(
                    self.config.funding_cost_block_r - self.config.funding_cost_soft_r,
                    EV_EPS,
                ),
                1.0,
            )
            funding_risk_mult = 1.0 - t * (1.0 - self.config.funding_risk_mult_soft_penalty)
        else:
            funding_risk_mult = self.config.funding_risk_mult_base
        
        # Combined multiplier (с учётом proximity)
        combined_risk_mult = funding_risk_mult * proximity_metrics.funding_proximity_mult
        
        # =====================================================================
        # 11. PASS
        # =====================================================================
        
        return Gate09Result(
            entry_allowed=True,
            block_reason="",
            funding_metrics=funding_metrics,
            ev_r_price=ev_r_price,
            expected_cost_r_used=expected_cost_r_postmle,
            ev_r_price_net=ev_r_price_net,
            net_yield_r=net_yield_r,
            proximity_metrics=proximity_metrics,
            blackout_check=blackout_check,
            funding_risk_mult=funding_risk_mult,
            combined_risk_mult=combined_risk_mult,
            details=(
                f"PASS: Net_Yield_R={net_yield_r:.4f}, "
                f"funding_cost_R={funding_metrics.funding_cost_r:.4f}, "
                f"proximity_mult={proximity_metrics.funding_proximity_mult:.4f}"
            ),
        )
    
    def _calculate_funding_metrics(
        self,
        funding_rate: float,
        funding_period_hours: float,
        time_to_next_funding_sec: int,
        expected_holding_hours: float,
        direction_sign: int,
        entry_price_ref: float,
        unit_risk_allin_net: float,
    ) -> FundingMetrics:
        """Calculate funding metrics (ТЗ 3.3.4.2, 3.3.4.3).
        
        Args:
            funding_rate: Текущий funding rate (биржевой знак)
            funding_period_hours: Период funding (обычно 8)
            time_to_next_funding_sec: Время до следующего funding
            expected_holding_hours: Ожидаемое время удержания
            direction_sign: +1 для LONG, -1 для SHORT
            entry_price_ref: Entry price reference
            unit_risk_allin_net: Unit risk all-in net
        
        Returns:
            FundingMetrics
        """
        # =====================================================================
        # 1. Calculate number of funding events (ТЗ 3.3.4.2)
        # =====================================================================
        
        t_next_h = time_to_next_funding_sec / 3600.0
        
        if expected_holding_hours < t_next_h:
            n_events_raw = 0
        else:
            n_events_raw = 1 + math.floor(
                (expected_holding_hours - t_next_h) / funding_period_hours
            )
        
        # NOTE: В ТЗ упоминается сглаживание EMA, но для детерминированности
        # iteration мы пока используем raw value. В production можно добавить EMA.
        n_events = float(n_events_raw)
        
        # =====================================================================
        # 2. Calculate funding PnL fraction (ТЗ 3.3.4.3)
        # =====================================================================
        
        # funding_pnl_frac = - direction_sign * funding_rate * n_events
        funding_pnl_frac = -direction_sign * funding_rate * n_events
        
        # =====================================================================
        # 3. Convert to R units (ТЗ 3.3.4.3)
        # =====================================================================
        
        # funding_R = funding_pnl_frac * entry_price_ref / max(unit_risk_allin_net, min_absolute)
        unit_risk_for_division = max(
            unit_risk_allin_net,
            UNIT_RISK_MIN_ABSOLUTE_FOR_FUNDING,
        )
        
        funding_r = funding_pnl_frac * entry_price_ref / unit_risk_for_division
        
        # =====================================================================
        # 4. Calculate cost/bonus
        # =====================================================================
        
        funding_cost_r = max(0.0, -funding_r)
        funding_bonus_r = max(0.0, funding_r)
        
        # funding_bonus_R_used (политика применяется в evaluate)
        funding_bonus_r_used = 0.0  # Будет обновлено в evaluate
        
        return FundingMetrics(
            funding_rate=funding_rate,
            funding_period_hours=funding_period_hours,
            time_to_next_funding_sec=time_to_next_funding_sec,
            expected_holding_hours=expected_holding_hours,
            n_events_raw=n_events_raw,
            n_events=n_events,
            direction_sign=direction_sign,
            funding_pnl_frac=funding_pnl_frac,
            funding_r=funding_r,
            funding_cost_r=funding_cost_r,
            funding_bonus_r=funding_bonus_r,
            funding_bonus_r_used=funding_bonus_r_used,
        )
    
    def _calculate_proximity_metrics(
        self,
        time_to_next_funding_sec: int,
        funding_cost_r: float,
    ) -> ProximityMetrics:
        """Calculate proximity metrics (ТЗ 3.3.4.5).
        
        Args:
            time_to_next_funding_sec: Время до следующего funding
            funding_cost_r: Funding cost в R units
        
        Returns:
            ProximityMetrics
        """
        # =====================================================================
        # 1. Calculate tau (normalized proximity)
        # =====================================================================
        
        # tau = clip((soft_sec - time_to_funding) / (soft_sec - hard_sec), 0, 1)
        denominator = max(
            self.config.funding_proximity_soft_sec - self.config.funding_proximity_hard_sec,
            1,
        )
        
        tau_raw = (
            self.config.funding_proximity_soft_sec - time_to_next_funding_sec
        ) / denominator
        
        tau = max(0.0, min(1.0, tau_raw))
        
        # =====================================================================
        # 2. Calculate funding_proximity_mult (ТЗ 3.3.4.5)
        # =====================================================================
        
        # funding_proximity_mult = 1 - (1 - mult_min) * (tau ^ power)
        funding_proximity_mult = 1.0 - (
            1.0 - self.config.funding_proximity_mult_min
        ) * (tau ** self.config.funding_proximity_power)
        
        # =====================================================================
        # 3. Calculate diagnostics
        # =====================================================================
        
        is_near_funding = tau > 0.0
        
        # Proximity penalty in R units (для диагностики)
        # Это примерная оценка, как proximity влияет на риск
        proximity_penalty_r = funding_cost_r * (1.0 - funding_proximity_mult)
        
        return ProximityMetrics(
            tau=tau,
            funding_proximity_mult=funding_proximity_mult,
            is_near_funding=is_near_funding,
            proximity_penalty_r=proximity_penalty_r,
        )
    
    def _check_blackout_conditions(
        self,
        time_to_next_funding_sec: int,
        funding_cost_r: float,
        expected_holding_hours: float,
        ev_r_price: float,
    ) -> BlackoutCheck:
        """Check blackout conditions (ТЗ 3.3.4.6).
        
        Blackout применяется только при одновременном выполнении ВСЕХ условий:
        1. time_to_next_funding_sec <= blackout_minutes * 60 + epsilon
        2. funding_cost_R > 0
        3. expected_holding_hours <= blackout_max_holding_hours
        4. funding_cost_R / max(EV_R_price, eps) >= cost_share_threshold
        
        Args:
            time_to_next_funding_sec: Время до следующего funding
            funding_cost_r: Funding cost в R units
            expected_holding_hours: Ожидаемое время удержания
            ev_r_price: EV_R_price from GATE 6
        
        Returns:
            BlackoutCheck
        """
        # =====================================================================
        # 1. Time condition
        # =====================================================================
        
        blackout_window_sec = (
            self.config.funding_blackout_minutes * 60
            + self.config.funding_event_inclusion_epsilon_sec
        )
        
        time_condition = time_to_next_funding_sec <= blackout_window_sec
        
        # =====================================================================
        # 2. Cost condition
        # =====================================================================
        
        cost_condition = funding_cost_r > 0.0
        
        # =====================================================================
        # 3. Holding condition
        # =====================================================================
        
        holding_condition = (
            expected_holding_hours <= self.config.funding_blackout_max_holding_hours
        )
        
        # =====================================================================
        # 4. Significance condition
        # =====================================================================
        
        ev_for_division = max(abs(ev_r_price), self.config.funding_blackout_ev_eps)
        cost_share = funding_cost_r / ev_for_division
        
        significance_condition = (
            cost_share >= self.config.funding_blackout_cost_share_threshold
        )
        
        # =====================================================================
        # 5. Blackout triggered = AND всех условий
        # =====================================================================
        
        blackout_triggered = (
            time_condition
            and cost_condition
            and holding_condition
            and significance_condition
        )
        
        # =====================================================================
        # 6. Reason
        # =====================================================================
        
        if blackout_triggered:
            blackout_reason = (
                f"Blackout triggered: "
                f"time_to_funding={time_to_next_funding_sec}s <= {blackout_window_sec}s, "
                f"funding_cost_R={funding_cost_r:.4f} > 0, "
                f"holding={expected_holding_hours:.1f}h <= {self.config.funding_blackout_max_holding_hours:.1f}h, "
                f"cost_share={cost_share:.2%} >= {self.config.funding_blackout_cost_share_threshold:.2%}"
            )
        else:
            blackout_reason = ""
        
        return BlackoutCheck(
            time_condition=time_condition,
            cost_condition=cost_condition,
            holding_condition=holding_condition,
            significance_condition=significance_condition,
            blackout_triggered=blackout_triggered,
            blackout_reason=blackout_reason,
        )
    
    def _create_blocked_result(
        self,
        block_reason: str,
        gate00: Gate00Result,
        gate05: Gate05Result,
        gate06: Gate06Result,
        direction: Direction,
        market_state: MarketState,
        details: str = "",
    ) -> Gate09Result:
        """Create blocked result with default metrics.
        
        Args:
            block_reason: Причина блокировки
            gate00: GATE 0 result (для time)
            gate05: GATE 5 result (для unit_risk)
            gate06: GATE 6 result (для EV)
            direction: Signal direction
            market_state: Market state
            details: Дополнительные детали
        
        Returns:
            Gate09Result с entry_allowed=False
        """
        # Default funding metrics (все 0)
        direction_sign = 1 if direction == Direction.LONG else -1
        
        funding_metrics = FundingMetrics(
            funding_rate=market_state.derivatives.funding_rate_spot,
            funding_period_hours=market_state.derivatives.funding_period_hours,
            time_to_next_funding_sec=market_state.derivatives.time_to_next_funding_sec,
            expected_holding_hours=0.0,
            n_events_raw=0,
            n_events=0.0,
            direction_sign=direction_sign,
            funding_pnl_frac=0.0,
            funding_r=0.0,
            funding_cost_r=0.0,
            funding_bonus_r=0.0,
            funding_bonus_r_used=0.0,
        )
        
        proximity_metrics = ProximityMetrics(
            tau=0.0,
            funding_proximity_mult=1.0,
            is_near_funding=False,
            proximity_penalty_r=0.0,
        )
        
        blackout_check = BlackoutCheck(
            time_condition=False,
            cost_condition=False,
            holding_condition=False,
            significance_condition=False,
            blackout_triggered=False,
            blackout_reason="",
        )
        
        return Gate09Result(
            entry_allowed=False,
            block_reason=block_reason,
            funding_metrics=funding_metrics,
            ev_r_price=gate06.ev_r_price,
            expected_cost_r_used=gate06.expected_cost_r_postmle,
            ev_r_price_net=gate06.net_edge_r,  # Approximation
            net_yield_r=0.0,
            proximity_metrics=proximity_metrics,
            blackout_check=blackout_check,
            funding_risk_mult=0.0,
            combined_risk_mult=0.0,
            details=details or f"Blocked by previous gate: {block_reason}",
        )
