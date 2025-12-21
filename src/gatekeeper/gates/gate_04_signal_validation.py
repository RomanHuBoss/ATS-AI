"""GATE 4: Валидация сигнала движка

ТЗ 3.3.2 строка 1021 (GATE 4: Валидация сигнала движка)
ТЗ 3.3.5 строки 1238-1240 (SL distance в ATR)

Проверяет корректность engine signal:
- RR validation: raw_rr >= RR_min_engine
- SL distance в ATR: sl_min_atr_mult <= distance <= sl_max_atr_mult
- Entry/TP/SL санитарные проверки (NaN, inf, валидность)
- Корректность направлений (LONG/SHORT)

Интеграция:
- Использует результаты GATE 0-3 (должны быть PASS)
- Использует Signal domain model
- Требует ATR для валидации SL distance
"""

import math
from dataclasses import dataclass
from typing import Final

from src.core.domain.signal import Signal
from src.gatekeeper.gates.gate_00_warmup_dqs import Gate00Result
from src.gatekeeper.gates.gate_01_drp_killswitch import Gate01Result
from src.gatekeeper.gates.gate_02_mrc_confidence import Gate02Result
from src.gatekeeper.gates.gate_03_strategy_compat import Gate03Result


# =============================================================================
# CONSTANTS
# =============================================================================

# Epsilon для численных сравнений
EPS_PRICE: Final[float] = 1e-8


# =============================================================================
# RESULT
# =============================================================================


@dataclass(frozen=True)
class Gate04Result:
    """Результат GATE 4."""
    
    entry_allowed: bool
    block_reason: str
    
    # Signal validation metrics
    raw_rr: float
    sl_distance_abs: float
    sl_distance_atr: float  # SL distance in ATR units
    
    # Validation flags
    rr_valid: bool
    sl_distance_valid: bool
    prices_valid: bool
    
    # Детали
    details: str


# =============================================================================
# CONFIG
# =============================================================================


@dataclass(frozen=True)
class Gate04Config:
    """Конфигурация GATE 4.
    
    Параметры для валидации сигнала.
    """
    
    # Минимальный ATR для валидации (защита от деления на 0)
    min_atr_for_validation: float = 1e-8


# =============================================================================
# GATE 4
# =============================================================================


class Gate04SignalValidation:
    """GATE 4: Валидация сигнала движка.
    
    Проверяет корректность engine signal:
    1. Санитарные проверки (NaN, inf, валидность цен)
    2. RR validation (raw_rr >= RR_min_engine)
    3. SL distance в ATR (sl_min_atr_mult <= distance <= sl_max_atr_mult)
    
    Порядок проверок:
    1. GATE 0-3 блокировки (должны быть PASS)
    2. Санитарные проверки цен и ATR
    3. RR validation
    4. SL distance validation
    """
    
    def __init__(self, config: Gate04Config | None = None):
        """Инициализация GATE 4.
        
        Args:
            config: конфигурация gate (опционально, используется default)
        """
        self.config = config or Gate04Config()
    
    def evaluate(
        self,
        # GATE 0-3 результаты
        gate00_result: Gate00Result,
        gate01_result: Gate01Result,
        gate02_result: Gate02Result,
        gate03_result: Gate03Result,
        
        # Signal и market data
        signal: Signal,
        atr: float,
    ) -> Gate04Result:
        """Оценка GATE 4: валидация сигнала движка.
        
        Args:
            gate00_result: результат GATE 0 (DQS и DRP state)
            gate01_result: результат GATE 1 (trading mode, manual halt)
            gate02_result: результат GATE 2 (final_regime)
            gate03_result: результат GATE 3 (strategy compatibility)
            signal: engine signal для валидации
            atr: Average True Range для валидации SL distance
        
        Returns:
            Gate04Result с решением о допуске
        """
        # 1. Проверка GATE 0-3 блокировок
        if not gate00_result.entry_allowed:
            return self._blocked_result(
                reason=f"gate00_blocked: {gate00_result.block_reason}",
                signal=signal,
                atr=atr,
            )
        
        if not gate01_result.entry_allowed:
            return self._blocked_result(
                reason=f"gate01_blocked: {gate01_result.block_reason}",
                signal=signal,
                atr=atr,
            )
        
        if not gate02_result.entry_allowed:
            return self._blocked_result(
                reason=f"gate02_blocked: {gate02_result.block_reason}",
                signal=signal,
                atr=atr,
            )
        
        if not gate03_result.entry_allowed:
            return self._blocked_result(
                reason=f"gate03_blocked: {gate03_result.block_reason}",
                signal=signal,
                atr=atr,
            )
        
        # 2. Санитарные проверки
        prices_valid, price_error = self._validate_prices(signal)
        if not prices_valid:
            return self._blocked_result(
                reason=f"invalid_prices: {price_error}",
                signal=signal,
                atr=atr,
            )
        
        atr_valid, atr_error = self._validate_atr(atr)
        if not atr_valid:
            return self._blocked_result(
                reason=f"invalid_atr: {atr_error}",
                signal=signal,
                atr=atr,
            )
        
        # 3. Вычисление метрик
        raw_rr = signal.raw_rr()
        sl_distance_abs = signal.potential_loss()
        sl_distance_atr = sl_distance_abs / atr
        
        # 4. RR validation
        rr_valid = raw_rr >= signal.constraints.RR_min_engine
        if not rr_valid:
            return Gate04Result(
                entry_allowed=False,
                block_reason=f"rr_too_low: {raw_rr:.3f} < {signal.constraints.RR_min_engine:.3f}",
                raw_rr=raw_rr,
                sl_distance_abs=sl_distance_abs,
                sl_distance_atr=sl_distance_atr,
                rr_valid=False,
                sl_distance_valid=False,
                prices_valid=True,
                details=f"RR {raw_rr:.3f} < min {signal.constraints.RR_min_engine:.3f}",
            )
        
        # 5. SL distance validation
        sl_too_tight = sl_distance_atr < signal.constraints.sl_min_atr_mult
        sl_too_wide = sl_distance_atr > signal.constraints.sl_max_atr_mult
        sl_distance_valid = not (sl_too_tight or sl_too_wide)
        
        if sl_too_tight:
            return Gate04Result(
                entry_allowed=False,
                block_reason=(
                    f"sl_too_tight: {sl_distance_atr:.3f} ATR < "
                    f"{signal.constraints.sl_min_atr_mult:.3f} ATR"
                ),
                raw_rr=raw_rr,
                sl_distance_abs=sl_distance_abs,
                sl_distance_atr=sl_distance_atr,
                rr_valid=True,
                sl_distance_valid=False,
                prices_valid=True,
                details=(
                    f"SL too tight: {sl_distance_atr:.3f} ATR < "
                    f"{signal.constraints.sl_min_atr_mult:.3f} ATR min"
                ),
            )
        
        if sl_too_wide:
            return Gate04Result(
                entry_allowed=False,
                block_reason=(
                    f"sl_too_wide: {sl_distance_atr:.3f} ATR > "
                    f"{signal.constraints.sl_max_atr_mult:.3f} ATR"
                ),
                raw_rr=raw_rr,
                sl_distance_abs=sl_distance_abs,
                sl_distance_atr=sl_distance_atr,
                rr_valid=True,
                sl_distance_valid=False,
                prices_valid=True,
                details=(
                    f"SL too wide: {sl_distance_atr:.3f} ATR > "
                    f"{signal.constraints.sl_max_atr_mult:.3f} ATR max"
                ),
            )
        
        # 6. PASS
        return Gate04Result(
            entry_allowed=True,
            block_reason="",
            raw_rr=raw_rr,
            sl_distance_abs=sl_distance_abs,
            sl_distance_atr=sl_distance_atr,
            rr_valid=True,
            sl_distance_valid=True,
            prices_valid=True,
            details=(
                f"Signal validated: RR={raw_rr:.3f} (>= {signal.constraints.RR_min_engine:.3f}), "
                f"SL={sl_distance_atr:.3f} ATR "
                f"[{signal.constraints.sl_min_atr_mult:.3f}, {signal.constraints.sl_max_atr_mult:.3f}]"
            ),
        )
    
    def _validate_prices(self, signal: Signal) -> tuple[bool, str]:
        """Санитарные проверки цен.
        
        Args:
            signal: engine signal
        
        Returns:
            (is_valid, error_message)
        """
        entry = signal.levels.entry_price
        tp = signal.levels.take_profit
        sl = signal.levels.stop_loss
        
        # NaN/inf проверки
        if math.isnan(entry) or math.isinf(entry):
            return False, f"entry_price is NaN/inf: {entry}"
        if math.isnan(tp) or math.isinf(tp):
            return False, f"take_profit is NaN/inf: {tp}"
        if math.isnan(sl) or math.isinf(sl):
            return False, f"stop_loss is NaN/inf: {sl}"
        
        # Положительность
        if entry <= EPS_PRICE:
            return False, f"entry_price <= 0: {entry}"
        if tp <= EPS_PRICE:
            return False, f"take_profit <= 0: {tp}"
        if sl <= EPS_PRICE:
            return False, f"stop_loss <= 0: {sl}"
        
        return True, ""
    
    def _validate_atr(self, atr: float) -> tuple[bool, str]:
        """Санитарные проверки ATR.
        
        Args:
            atr: Average True Range
        
        Returns:
            (is_valid, error_message)
        """
        # NaN/inf проверки
        if math.isnan(atr) or math.isinf(atr):
            return False, f"atr is NaN/inf: {atr}"
        
        # Минимальный порог
        if atr < self.config.min_atr_for_validation:
            return False, f"atr too small: {atr} < {self.config.min_atr_for_validation}"
        
        return True, ""
    
    def _blocked_result(
        self,
        reason: str,
        signal: Signal,
        atr: float,
    ) -> Gate04Result:
        """Создание blocked result с вычислением метрик.
        
        Args:
            reason: причина блокировки
            signal: engine signal
            atr: ATR (может быть невалидным)
        
        Returns:
            Gate04Result с entry_allowed=False
        """
        # Вычисляем метрики, если возможно (для диагностики)
        try:
            raw_rr = signal.raw_rr()
            sl_distance_abs = signal.potential_loss()
            # ATR может быть невалидным, защищаемся
            if atr > 0 and not math.isnan(atr) and not math.isinf(atr):
                sl_distance_atr = sl_distance_abs / atr
            else:
                sl_distance_atr = 0.0
        except Exception:
            raw_rr = 0.0
            sl_distance_abs = 0.0
            sl_distance_atr = 0.0
        
        return Gate04Result(
            entry_allowed=False,
            block_reason=reason,
            raw_rr=raw_rr,
            sl_distance_abs=sl_distance_abs,
            sl_distance_atr=sl_distance_atr,
            rr_valid=False,
            sl_distance_valid=False,
            prices_valid=False,
            details=reason,
        )
