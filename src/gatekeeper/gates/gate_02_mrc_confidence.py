"""GATE 2: MRC Confidence + Baseline + Conflict Resolution (включая probe-режим)

ТЗ 3.3.2 строка 1019 (GATE 2: MRC confidence + baseline + conflict resolution)
ТЗ 3.3.3 строки 1066-1111 (детальная логика MRC/Baseline conflict resolution)

Порядок проверок:
1. GATE 0-1 результаты (должны быть PASS)
2. MRC и Baseline классификация
3. Conflict resolution детерминированный
4. Probe-режим при конфликте трендов (если условия выполнены)
5. Final regime определение

Интеграция:
- Использует результаты GATE 0 (DQS) и GATE 1 (trading mode)
- MRC/Baseline classifiers (опционально, может быть mock для начала)
- Conflict history tracking для diagnostic block
"""

from dataclasses import dataclass
from typing import Optional

from src.core.domain.regime import (
    MRCClass,
    BaselineClass,
    FinalRegime,
    MRCResult,
    BaselineResult,
    RegimeConflictInfo,
)
from src.gatekeeper.gates.gate_00_warmup_dqs import Gate00Result
from src.gatekeeper.gates.gate_01_drp_killswitch import Gate01Result


# =============================================================================
# CONFIG
# =============================================================================


@dataclass(frozen=True)
class Gate02Config:
    """Конфигурация GATE 2.
    
    ТЗ 3.3.3 строки 1067-1075: Пороги MRC confidence
    ТЗ 3.3.3 строки 1072-1074: Conflict resolution parameters
    """
    
    # MRC confidence thresholds
    mrc_high_conf_threshold: float = 0.70
    mrc_very_high_conf_threshold: float = 0.85
    mrc_low_conf_threshold: float = 0.55
    
    # Conflict resolution
    conflict_window_bars: int = 10
    conflict_fast_atr_z: float = 2.0  # При ATR_z_short >= этого → сократить window
    conflict_ratio_threshold: float = 0.60
    diagnostic_block_minutes: int = 120
    
    # Probe-режим requirements (ТЗ 3.3.3 строки 1095-1109)
    probe_min_depth_usd: float = 50000.0
    probe_max_spread_bps: float = 5.0
    probe_risk_mult: float = 0.33  # Риск понижается до 1/3
    
    # Risk multipliers
    noise_override_risk_mult: float = 0.50  # При NOISE override
    
    # DQS threshold для probe (ТЗ 3.3.3 строка 1098)
    dqs_degraded_threshold: float = 0.70


# =============================================================================
# RESULT
# =============================================================================


@dataclass(frozen=True)
class Gate02Result:
    """Результат GATE 2."""
    
    entry_allowed: bool
    block_reason: str
    
    # Regime classification
    mrc_result: MRCResult
    baseline_result: BaselineResult
    final_regime: FinalRegime
    
    # Conflict resolution
    conflict_info: Optional[RegimeConflictInfo]
    is_probe_mode: bool
    
    # Risk multipliers (применяются позже в GATE 14)
    regime_risk_mult: float
    
    # Детали
    details: str


# =============================================================================
# GATE 2
# =============================================================================


class Gate02MRCConfidence:
    """GATE 2: MRC Confidence + Baseline + Conflict Resolution.
    
    ТЗ 3.3.3 строки 1079-1111: Детерминированное правило выбора final_regime
    
    Порядок проверок:
    1. GATE 0-1 блокировки (должны быть PASS)
    2. MRC и Baseline классификация
    3. Conflict resolution:
       - MRC=NOISE → NO_TRADE (кроме RANGE exception)
       - Baseline=NOISE → очень строгие требования или NO_TRADE
       - MRC=RANGE, Baseline=TREND → RANGE
       - MRC=TREND, Baseline=RANGE → BREAKOUT (пониженный риск)
       - MRC=BREAKOUT, Baseline=RANGE → BREAKOUT
       - MRC=BREAKOUT, Baseline=TREND → BREAKOUT если знак совпадает
       - TREND_vs_TREND conflict → PROBE_TRADE или NO_TRADE
    4. Final regime определение
    """
    
    def __init__(
        self,
        config: Optional[Gate02Config] = None
    ):
        """
        Args:
            config: Конфигурация GATE 2 (default: Gate02Config())
        """
        self.config = config or Gate02Config()
    
    def evaluate(
        self,
        # GATE 0-1 результаты
        gate00_result: Gate00Result,
        gate01_result: Gate01Result,
        
        # MRC и Baseline (mock или реальные)
        mrc_result: MRCResult,
        baseline_result: BaselineResult,
        
        # Market state для probe-режима (ТЗ 3.3.3 строки 1097-1100)
        dqs: float,
        depth_bid_usd: float,
        depth_ask_usd: float,
        spread_bps: float,
        
        # MLE decision для probe (ТЗ 3.3.3 строка 1101)
        # В итерации 10 MLE еще не реализован, поэтому используем placeholder
        mle_decision_strong_or_normal: bool = True,
        
        # Conflict history (для diagnostic block)
        # В итерации 10 упрощено — передается текущий conflict count
        conflict_count_in_window: int = 0
    ) -> Gate02Result:
        """Оценка GATE 2: MRC confidence, conflict resolution, probe-режим.
        
        Args:
            gate00_result: результат GATE 0 (DQS и DRP state)
            gate01_result: результат GATE 1 (trading mode, manual halt)
            mrc_result: результат MRC classifier
            baseline_result: результат Baseline classifier
            dqs: текущий DQS (для probe requirements)
            depth_bid_usd: глубина bid стороны (USD)
            depth_ask_usd: глубина ask стороны (USD)
            spread_bps: спред bid-ask (bps)
            mle_decision_strong_or_normal: MLE decision NORMAL/STRONG (для probe)
            conflict_count_in_window: количество конфликтов в скользящем окне
        
        Returns:
            Gate02Result с решением о допуске и final_regime
        """
        # 1. Проверка GATE 0-1 блокировок
        if not gate00_result.entry_allowed:
            return Gate02Result(
                entry_allowed=False,
                block_reason=f"gate00_blocked: {gate00_result.block_reason}",
                mrc_result=mrc_result,
                baseline_result=baseline_result,
                final_regime=FinalRegime.NO_TRADE,
                conflict_info=None,
                is_probe_mode=False,
                regime_risk_mult=1.0,
                details=f"GATE 0 blocked: {gate00_result.block_reason}"
            )
        
        if not gate01_result.entry_allowed:
            return Gate02Result(
                entry_allowed=False,
                block_reason=f"gate01_blocked: {gate01_result.block_reason}",
                mrc_result=mrc_result,
                baseline_result=baseline_result,
                final_regime=FinalRegime.NO_TRADE,
                conflict_info=None,
                is_probe_mode=False,
                regime_risk_mult=1.0,
                details=f"GATE 1 blocked: {gate01_result.block_reason}"
            )
        
        # 2. Conflict resolution (детерминированный)
        final_regime, conflict_info, is_probe, risk_mult = self._resolve_conflict(
            mrc_result=mrc_result,
            baseline_result=baseline_result,
            dqs=dqs,
            depth_bid_usd=depth_bid_usd,
            depth_ask_usd=depth_ask_usd,
            spread_bps=spread_bps,
            mle_decision_strong_or_normal=mle_decision_strong_or_normal
        )
        
        # 3. Diagnostic block при устойчивом конфликте
        if conflict_count_in_window >= self.config.conflict_window_bars * self.config.conflict_ratio_threshold:
            return Gate02Result(
                entry_allowed=False,
                block_reason="regime_conflict_sustained",
                mrc_result=mrc_result,
                baseline_result=baseline_result,
                final_regime=FinalRegime.NO_TRADE,
                conflict_info=conflict_info,
                is_probe_mode=False,
                regime_risk_mult=1.0,
                details=f"Sustained conflict: {conflict_count_in_window} conflicts in window, blocked for {self.config.diagnostic_block_minutes} minutes"
            )
        
        # 4. Блокировка при NO_TRADE
        if final_regime == FinalRegime.NO_TRADE:
            return Gate02Result(
                entry_allowed=False,
                block_reason="regime_no_trade",
                mrc_result=mrc_result,
                baseline_result=baseline_result,
                final_regime=final_regime,
                conflict_info=conflict_info,
                is_probe_mode=is_probe,
                regime_risk_mult=risk_mult,
                details=f"Regime conflict resolved to NO_TRADE: MRC={mrc_result.mrc_class.value}, Baseline={baseline_result.baseline_class.value}"
            )
        
        # 5. PASS - вход разрешен
        probe_note = " (PROBE mode - reduced risk)" if is_probe else ""
        
        return Gate02Result(
            entry_allowed=True,
            block_reason="",
            mrc_result=mrc_result,
            baseline_result=baseline_result,
            final_regime=final_regime,
            conflict_info=conflict_info,
            is_probe_mode=is_probe,
            regime_risk_mult=risk_mult,
            details=f"PASS: final_regime={final_regime.value}, risk_mult={risk_mult:.2f}, MRC_conf={mrc_result.confidence:.2f}{probe_note}"
        )
    
    def _resolve_conflict(
        self,
        mrc_result: MRCResult,
        baseline_result: BaselineResult,
        dqs: float,
        depth_bid_usd: float,
        depth_ask_usd: float,
        spread_bps: float,
        mle_decision_strong_or_normal: bool
    ) -> tuple[FinalRegime, Optional[RegimeConflictInfo], bool, float]:
        """Детерминированное разрешение конфликта между MRC и Baseline.
        
        ТЗ 3.3.3 строки 1079-1111
        
        Returns:
            (final_regime, conflict_info, is_probe_mode, regime_risk_mult)
        """
        mrc_class = mrc_result.mrc_class
        baseline_class = baseline_result.baseline_class
        mrc_conf = mrc_result.confidence
        
        # Default values
        is_probe = False
        risk_mult = 1.0
        conflict_detected = False
        conflict_type = "none"
        
        # ТЗ 3.3.3 строка 1080: MRC=NOISE → NO_TRADE (кроме исключения для RANGE)
        if mrc_class == MRCClass.NOISE:
            if baseline_class == BaselineClass.RANGE:
                # Exception: NOISE + RANGE → RANGE (сниженный риск)
                final_regime = FinalRegime.RANGE
                conflict_detected = True
                conflict_type = "noise_range_exception"
                risk_mult = self.config.noise_override_risk_mult
            else:
                final_regime = FinalRegime.NO_TRADE
                conflict_detected = True
                conflict_type = "mrc_noise"
        
        # ТЗ 3.3.3 строки 1081-1084: Baseline=NOISE
        elif baseline_class == BaselineClass.NOISE:
            if (mrc_conf >= self.config.mrc_very_high_conf_threshold and
                mrc_class in (MRCClass.TREND_UP, MRCClass.TREND_DOWN, 
                             MRCClass.BREAKOUT_UP, MRCClass.BREAKOUT_DOWN)):
                # Very high confidence MRC override Baseline NOISE
                if mrc_class == MRCClass.TREND_UP:
                    final_regime = FinalRegime.TREND_UP
                elif mrc_class == MRCClass.TREND_DOWN:
                    final_regime = FinalRegime.TREND_DOWN
                elif mrc_class == MRCClass.BREAKOUT_UP:
                    final_regime = FinalRegime.BREAKOUT_UP
                else:  # BREAKOUT_DOWN
                    final_regime = FinalRegime.BREAKOUT_DOWN
                
                conflict_detected = True
                conflict_type = "baseline_noise_override"
                risk_mult = self.config.noise_override_risk_mult
            else:
                final_regime = FinalRegime.NO_TRADE
                conflict_detected = True
                conflict_type = "baseline_noise"
        
        # ТЗ 3.3.3 строка 1085: MRC=RANGE, Baseline=TREND_* → RANGE
        elif mrc_class == MRCClass.RANGE and baseline_class in (BaselineClass.TREND_UP, BaselineClass.TREND_DOWN):
            final_regime = FinalRegime.RANGE
            conflict_detected = True
            conflict_type = "range_vs_trend"
        
        # ТЗ 3.3.3 строка 1086: MRC=TREND_*, Baseline=RANGE → BREAKOUT_* (пониженный риск)
        elif mrc_class in (MRCClass.TREND_UP, MRCClass.TREND_DOWN) and baseline_class == BaselineClass.RANGE:
            if mrc_class == MRCClass.TREND_UP:
                final_regime = FinalRegime.BREAKOUT_UP
            else:  # TREND_DOWN
                final_regime = FinalRegime.BREAKOUT_DOWN
            
            conflict_detected = True
            conflict_type = "trend_vs_range"
            risk_mult = 0.75  # Пониженный риск при переходе из RANGE
        
        # ТЗ 3.3.3 строка 1087: MRC=BREAKOUT_*, Baseline=RANGE → BREAKOUT_*
        elif mrc_class in (MRCClass.BREAKOUT_UP, MRCClass.BREAKOUT_DOWN) and baseline_class == BaselineClass.RANGE:
            if mrc_class == MRCClass.BREAKOUT_UP:
                final_regime = FinalRegime.BREAKOUT_UP
            else:  # BREAKOUT_DOWN
                final_regime = FinalRegime.BREAKOUT_DOWN
            
            conflict_detected = True
            conflict_type = "breakout_vs_range"
        
        # ТЗ 3.3.3 строки 1088-1091: MRC=BREAKOUT_*, Baseline=TREND_*
        elif mrc_class in (MRCClass.BREAKOUT_UP, MRCClass.BREAKOUT_DOWN) and baseline_class in (BaselineClass.TREND_UP, BaselineClass.TREND_DOWN):
            # Проверка совпадения знака
            mrc_is_up = (mrc_class == MRCClass.BREAKOUT_UP)
            baseline_is_up = (baseline_class == BaselineClass.TREND_UP)
            
            if mrc_is_up == baseline_is_up:
                # Знак совпадает → BREAKOUT
                if mrc_class == MRCClass.BREAKOUT_UP:
                    final_regime = FinalRegime.BREAKOUT_UP
                else:  # BREAKOUT_DOWN
                    final_regime = FinalRegime.BREAKOUT_DOWN
                
                conflict_detected = False  # Согласие
                conflict_type = "breakout_trend_aligned"
            else:
                # Знак не совпадает → NO_TRADE
                final_regime = FinalRegime.NO_TRADE
                conflict_detected = True
                conflict_type = "breakout_trend_conflict"
        
        # ТЗ 3.3.3 строки 1093-1109: Probe-режим при конфликте трендов
        # MRC=TREND_UP/DOWN vs Baseline=TREND_DOWN/UP (противоположные)
        elif (
            (mrc_class == MRCClass.TREND_UP and baseline_class == BaselineClass.TREND_DOWN) or
            (mrc_class == MRCClass.TREND_DOWN and baseline_class == BaselineClass.TREND_UP)
        ):
            conflict_detected = True
            conflict_type = "trend_vs_trend"
            
            # Проверка условий probe-режима (ТЗ 3.3.3 строки 1095-1101)
            probe_eligible = (
                mrc_conf >= self.config.mrc_very_high_conf_threshold and
                dqs >= self.config.dqs_degraded_threshold and
                depth_bid_usd >= self.config.probe_min_depth_usd and
                depth_ask_usd >= self.config.probe_min_depth_usd and
                spread_bps <= self.config.probe_max_spread_bps and
                mle_decision_strong_or_normal
            )
            
            if probe_eligible:
                # PROBE_TRADE: follow MRC with reduced risk
                final_regime = FinalRegime.PROBE_TRADE
                is_probe = True
                risk_mult = self.config.probe_risk_mult
            else:
                # Не все условия выполнены → NO_TRADE
                final_regime = FinalRegime.NO_TRADE
        
        # Нет конфликта — согласие между MRC и Baseline
        else:
            # MRC и Baseline согласны
            if mrc_class == MRCClass.TREND_UP and baseline_class == BaselineClass.TREND_UP:
                final_regime = FinalRegime.TREND_UP
            elif mrc_class == MRCClass.TREND_DOWN and baseline_class == BaselineClass.TREND_DOWN:
                final_regime = FinalRegime.TREND_DOWN
            elif mrc_class == MRCClass.RANGE and baseline_class == BaselineClass.RANGE:
                final_regime = FinalRegime.RANGE
            else:
                # Неожиданное сочетание → NO_TRADE (failsafe)
                final_regime = FinalRegime.NO_TRADE
                conflict_detected = True
                conflict_type = "unexpected_combination"
        
        # Создание conflict_info
        if conflict_detected:
            is_probe_eligible = (conflict_type == "trend_vs_trend")
            probe_conditions_met = is_probe  # True если probe-режим активирован
            
            conflict_info = RegimeConflictInfo(
                conflict_detected=True,
                conflict_type=conflict_type,
                is_probe_eligible=is_probe_eligible,
                probe_conditions_met=probe_conditions_met,
                mrc_class=mrc_class,
                baseline_class=baseline_class,
                mrc_confidence=mrc_conf
            )
        else:
            conflict_info = None
        
        return final_regime, conflict_info, is_probe, risk_mult
