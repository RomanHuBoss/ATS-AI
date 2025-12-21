"""GATE 8: Gap/Data Glitch Detection — детектирование аномалий цен

ТЗ 3.3.2 строка 1025, 1053 (GATE 8: Gap handling и data glitch detection)
ТЗ раздел 9.4: Gap handling и data glitch detection

Проверяет:
- Price jumps (% threshold) — внезапные скачки цены
- Price spikes (z-score threshold) — статистические аномалии
- Stale orderbook при свежей цене — несоответствие timestamps
- Suspected data glitch — флаг для инициирования DRP

Детектирование:
1. Price jump: |price_now - price_prev| / price_prev > threshold
2. Price spike: |price_now - price_mean| / price_stddev > z_threshold
3. Stale book: orderbook_age > max_staleness и price_age < max_staleness
4. Suspected glitch: любая из аномалий выше threshold

Интеграция:
- Использует результаты GATE 0-7 (должны быть PASS)
- Size-invariant (не зависит от qty)
- suspected_data_glitch может инициировать DRP transition
"""

import math
import statistics
from dataclasses import dataclass
from typing import Final

from src.core.domain.signal import Direction, Signal
from src.gatekeeper.gates.gate_00_warmup_dqs import Gate00Result
from src.gatekeeper.gates.gate_01_drp_killswitch import Gate01Result
from src.gatekeeper.gates.gate_02_mrc_confidence import Gate02Result
from src.gatekeeper.gates.gate_03_strategy_compat import Gate03Result
from src.gatekeeper.gates.gate_04_signal_validation import Gate04Result
from src.gatekeeper.gates.gate_05_pre_sizing import Gate05Result
from src.gatekeeper.gates.gate_06_mle_decision import Gate06Result
from src.gatekeeper.gates.gate_07_liquidity_check import Gate07Result


# =============================================================================
# CONSTANTS
# =============================================================================

# Minimum price points для z-score calculation
MIN_PRICE_POINTS_FOR_ZSCORE: Final[int] = 5

# Epsilon для защиты от деления на 0
PRICE_EPS: Final[float] = 1e-8
STDDEV_EPS: Final[float] = 1e-9


# =============================================================================
# DATA CLASSES
# =============================================================================


@dataclass(frozen=True)
class PricePoint:
    """Точка цены с timestamp."""
    
    price: float
    timestamp_ms: int  # UTC milliseconds


@dataclass(frozen=True)
class AnomalyMetrics:
    """Метрики детектирования аномалий."""
    
    # Price jump
    price_jump_pct: float  # % изменение от предыдущей цены
    price_jump_detected: bool
    
    # Price spike (z-score)
    price_zscore: float | None  # None если недостаточно данных
    price_spike_detected: bool
    
    # Stale book
    orderbook_age_ms: int
    price_age_ms: int
    stale_book_fresh_price: bool
    
    # Suspected glitch
    suspected_data_glitch: bool
    glitch_reason: str


@dataclass(frozen=True)
class DRPTrigger:
    """DRP trigger information."""
    
    should_trigger: bool
    trigger_reason: str
    severity: str  # "LOW" | "MEDIUM" | "HIGH"


# =============================================================================
# RESULT
# =============================================================================


@dataclass(frozen=True)
class Gate08Result:
    """Результат GATE 8."""
    
    entry_allowed: bool
    block_reason: str
    
    # Anomaly metrics
    anomaly_metrics: AnomalyMetrics
    
    # DRP trigger
    drp_trigger: DRPTrigger
    
    # Детали
    details: str


# =============================================================================
# CONFIG
# =============================================================================


@dataclass(frozen=True)
class Gate08Config:
    """Конфигурация GATE 8.
    
    Параметры для gap/glitch detection.
    """
    
    # Price jump thresholds (%)
    price_jump_threshold_pct: float = 2.0  # 2% jump → suspect
    price_jump_hard_pct: float = 5.0       # 5% jump → hard block
    
    # Price spike thresholds (z-score)
    price_spike_zscore_threshold: float = 3.0  # 3 sigma → suspect
    price_spike_zscore_hard: float = 5.0       # 5 sigma → hard block
    
    # Stale book detection
    max_orderbook_age_ms: int = 5000     # 5 seconds
    max_price_age_ms: int = 1000         # 1 second
    
    # Suspected glitch behavior
    glitch_block_enabled: bool = True  # Block on suspected glitch
    glitch_triggers_drp: bool = True   # Trigger DRP on severe glitch
    
    # DRP trigger thresholds
    drp_trigger_zscore: float = 4.0    # 4 sigma → trigger DRP
    drp_trigger_jump_pct: float = 3.5  # 3.5% jump → trigger DRP


# =============================================================================
# GATE 8
# =============================================================================


class Gate08GapGlitch:
    """GATE 8: Gap/Data Glitch Detection — детектирование аномалий цен.
    
    Проверяет:
    1. Price jumps (резкие скачки цены)
    2. Price spikes (статистические аномалии через z-score)
    3. Stale orderbook при свежей цене
    4. Устанавливает suspected_data_glitch flag
    
    Порядок проверок:
    1. GATE 0-7 блокировки (должны быть PASS)
    2. Price jump detection
    3. Price spike detection (z-score)
    4. Stale book detection
    5. Suspected glitch determination
    6. DRP trigger evaluation
    """
    
    def __init__(self, config: Gate08Config | None = None):
        """Инициализация GATE 8.
        
        Args:
            config: конфигурация gate (опционально, используется default)
        """
        self.config = config or Gate08Config()
    
    def evaluate(
        self,
        # GATE 0-7 результаты
        gate00_result: Gate00Result,
        gate01_result: Gate01Result,
        gate02_result: Gate02Result,
        gate03_result: Gate03Result,
        gate04_result: Gate04Result,
        gate05_result: Gate05Result,
        gate06_result: Gate06Result,
        gate07_result: Gate07Result,
        
        # Signal
        signal: Signal,
        
        # Market data для gap/glitch detection
        current_price: float,
        current_price_ts_ms: int,
        price_history: list[PricePoint],  # Recent prices (последние N точек)
        orderbook_ts_ms: int,  # Timestamp последнего orderbook update
    ) -> Gate08Result:
        """Оценка GATE 8: Gap/Glitch detection.
        
        Args:
            gate00_result: результат GATE 0
            gate01_result: результат GATE 1
            gate02_result: результат GATE 2
            gate03_result: результат GATE 3
            gate04_result: результат GATE 4
            gate05_result: результат GATE 5
            gate06_result: результат GATE 6
            gate07_result: результат GATE 7
            signal: engine signal
            current_price: текущая цена
            current_price_ts_ms: timestamp текущей цены (UTC ms)
            price_history: история недавних цен для z-score calculation
            orderbook_ts_ms: timestamp последнего orderbook update (UTC ms)
        
        Returns:
            Gate08Result
        """
        # 1. GATE 0-7 блокировки
        if not gate00_result.entry_allowed:
            return self._blocked_result("gate00_blocked: " + gate00_result.block_reason)
        if not gate01_result.entry_allowed:
            return self._blocked_result("gate01_blocked: " + gate01_result.block_reason)
        if not gate02_result.entry_allowed:
            return self._blocked_result("gate02_blocked: " + gate02_result.block_reason)
        if not gate03_result.entry_allowed:
            return self._blocked_result("gate03_blocked: " + gate03_result.block_reason)
        if not gate04_result.entry_allowed:
            return self._blocked_result("gate04_blocked: " + gate04_result.block_reason)
        if not gate05_result.entry_allowed:
            return self._blocked_result("gate05_blocked: " + gate05_result.block_reason)
        if not gate06_result.entry_allowed:
            return self._blocked_result("gate06_blocked: " + gate06_result.block_reason)
        if not gate07_result.entry_allowed:
            return self._blocked_result("gate07_blocked: " + gate07_result.block_reason)
        
        # 2. Price jump detection
        price_jump_pct = 0.0
        price_jump_detected = False
        
        if price_history:
            # Берем последнюю цену для сравнения
            prev_price = price_history[-1].price
            if prev_price > PRICE_EPS:
                price_jump_pct = abs(current_price - prev_price) / prev_price * 100.0
                price_jump_detected = price_jump_pct > self.config.price_jump_threshold_pct
        
        # Hard block на большой jump
        if price_jump_pct > self.config.price_jump_hard_pct:
            return self._create_result(
                entry_allowed=False,
                block_reason=(
                    f"price_jump_hard_reject: {price_jump_pct:.2f}% > "
                    f"{self.config.price_jump_hard_pct:.2f}%"
                ),
                current_price=current_price,
                current_price_ts_ms=current_price_ts_ms,
                price_history=price_history,
                orderbook_ts_ms=orderbook_ts_ms,
                price_jump_pct=price_jump_pct,
                price_jump_detected=True,
                price_zscore=None,
                price_spike_detected=False,
            )
        
        # 3. Price spike detection (z-score)
        price_zscore = None
        price_spike_detected = False
        
        if len(price_history) >= MIN_PRICE_POINTS_FOR_ZSCORE:
            prices = [p.price for p in price_history]
            price_mean = statistics.mean(prices)
            price_stddev = statistics.stdev(prices) if len(prices) > 1 else 0.0
            
            if price_stddev > STDDEV_EPS:
                price_zscore = abs(current_price - price_mean) / price_stddev
                price_spike_detected = price_zscore > self.config.price_spike_zscore_threshold
        
        # Hard block на большой spike
        if price_zscore is not None and price_zscore > self.config.price_spike_zscore_hard:
            return self._create_result(
                entry_allowed=False,
                block_reason=(
                    f"price_spike_hard_reject: z-score={price_zscore:.2f} > "
                    f"{self.config.price_spike_zscore_hard:.2f}"
                ),
                current_price=current_price,
                current_price_ts_ms=current_price_ts_ms,
                price_history=price_history,
                orderbook_ts_ms=orderbook_ts_ms,
                price_jump_pct=price_jump_pct,
                price_jump_detected=price_jump_detected,
                price_zscore=price_zscore,
                price_spike_detected=True,
            )
        
        # 4. Stale book detection
        orderbook_age_ms = current_price_ts_ms - orderbook_ts_ms
        price_age_ms = 0  # Current price считается fresh
        
        stale_book_fresh_price = (
            orderbook_age_ms > self.config.max_orderbook_age_ms
            and price_age_ms < self.config.max_price_age_ms
        )
        
        # 5. Suspected glitch determination
        suspected_data_glitch = False
        glitch_reason = ""
        
        if price_jump_detected:
            suspected_data_glitch = True
            glitch_reason = f"price_jump={price_jump_pct:.2f}%"
        
        if price_spike_detected:
            suspected_data_glitch = True
            if glitch_reason:
                glitch_reason += f", price_spike=z{price_zscore:.2f}"
            else:
                glitch_reason = f"price_spike=z{price_zscore:.2f}"
        
        if stale_book_fresh_price:
            suspected_data_glitch = True
            if glitch_reason:
                glitch_reason += f", stale_book={orderbook_age_ms}ms"
            else:
                glitch_reason = f"stale_book={orderbook_age_ms}ms"
        
        # Block on suspected glitch если включен
        if suspected_data_glitch and self.config.glitch_block_enabled:
            return self._create_result(
                entry_allowed=False,
                block_reason=f"suspected_data_glitch: {glitch_reason}",
                current_price=current_price,
                current_price_ts_ms=current_price_ts_ms,
                price_history=price_history,
                orderbook_ts_ms=orderbook_ts_ms,
                price_jump_pct=price_jump_pct,
                price_jump_detected=price_jump_detected,
                price_zscore=price_zscore,
                price_spike_detected=price_spike_detected,
            )
        
        # 6. DRP trigger evaluation
        should_trigger_drp = False
        drp_severity = "LOW"
        drp_reason = ""
        
        if self.config.glitch_triggers_drp:
            # High severity triggers
            if price_zscore is not None and price_zscore > self.config.drp_trigger_zscore:
                should_trigger_drp = True
                drp_severity = "HIGH"
                drp_reason = f"high_spike_zscore={price_zscore:.2f}"
            elif price_jump_pct > self.config.drp_trigger_jump_pct:
                should_trigger_drp = True
                drp_severity = "HIGH"
                drp_reason = f"high_jump={price_jump_pct:.2f}%"
            # Medium severity triggers
            elif suspected_data_glitch:
                should_trigger_drp = True
                drp_severity = "MEDIUM"
                drp_reason = glitch_reason
        
        # 7. PASS result
        return self._create_result(
            entry_allowed=True,
            block_reason="",
            current_price=current_price,
            current_price_ts_ms=current_price_ts_ms,
            price_history=price_history,
            orderbook_ts_ms=orderbook_ts_ms,
            price_jump_pct=price_jump_pct,
            price_jump_detected=price_jump_detected,
            price_zscore=price_zscore,
            price_spike_detected=price_spike_detected,
            should_trigger_drp=should_trigger_drp,
            drp_severity=drp_severity,
            drp_reason=drp_reason,
        )
    
    def _create_result(
        self,
        entry_allowed: bool,
        block_reason: str,
        current_price: float,
        current_price_ts_ms: int,
        price_history: list[PricePoint],
        orderbook_ts_ms: int,
        price_jump_pct: float,
        price_jump_detected: bool,
        price_zscore: float | None,
        price_spike_detected: bool,
        should_trigger_drp: bool = False,
        drp_severity: str = "LOW",
        drp_reason: str = "",
    ) -> Gate08Result:
        """Создание Gate08Result с вычислением всех metrics.
        
        Args:
            entry_allowed: разрешён ли вход
            block_reason: причина блокировки (если есть)
            ... (anomaly detection data)
        
        Returns:
            Gate08Result
        """
        # 1. Calculate ages
        orderbook_age_ms = current_price_ts_ms - orderbook_ts_ms
        price_age_ms = 0  # Current price is fresh by definition
        
        # 2. Stale book detection
        stale_book_fresh_price = (
            orderbook_age_ms > self.config.max_orderbook_age_ms
            and price_age_ms < self.config.max_price_age_ms
        )
        
        # 3. Suspected glitch
        suspected_data_glitch = False
        glitch_reason = ""
        
        if price_jump_detected:
            suspected_data_glitch = True
            glitch_reason = f"price_jump={price_jump_pct:.2f}%"
        
        if price_spike_detected:
            suspected_data_glitch = True
            if glitch_reason:
                glitch_reason += f", price_spike=z{price_zscore:.2f}"
            else:
                glitch_reason = f"price_spike=z{price_zscore:.2f}"
        
        if stale_book_fresh_price:
            suspected_data_glitch = True
            if glitch_reason:
                glitch_reason += f", stale_book={orderbook_age_ms}ms"
            else:
                glitch_reason = f"stale_book={orderbook_age_ms}ms"
        
        if not suspected_data_glitch:
            glitch_reason = "none"
        
        # 4. AnomalyMetrics
        anomaly_metrics = AnomalyMetrics(
            price_jump_pct=price_jump_pct,
            price_jump_detected=price_jump_detected,
            price_zscore=price_zscore,
            price_spike_detected=price_spike_detected,
            orderbook_age_ms=orderbook_age_ms,
            price_age_ms=price_age_ms,
            stale_book_fresh_price=stale_book_fresh_price,
            suspected_data_glitch=suspected_data_glitch,
            glitch_reason=glitch_reason,
        )
        
        # 5. DRPTrigger
        drp_trigger = DRPTrigger(
            should_trigger=should_trigger_drp,
            trigger_reason=drp_reason if should_trigger_drp else "none",
            severity=drp_severity,
        )
        
        # 6. Details
        if entry_allowed:
            details = (
                f"PASS: no anomalies detected. "
                f"jump={price_jump_pct:.2f}%, "
            )
            if price_zscore is not None:
                details += f"zscore={price_zscore:.2f}, "
            details += f"orderbook_age={orderbook_age_ms}ms"
            
            if should_trigger_drp:
                details += f" [DRP_TRIGGER: {drp_severity} - {drp_reason}]"
        else:
            details = block_reason
        
        return Gate08Result(
            entry_allowed=entry_allowed,
            block_reason=block_reason,
            anomaly_metrics=anomaly_metrics,
            drp_trigger=drp_trigger,
            details=details,
        )
    
    def _blocked_result(self, reason: str) -> Gate08Result:
        """Создание blocked result (GATE 0-7 блокировка).
        
        Args:
            reason: причина блокировки
        
        Returns:
            Gate08Result с entry_allowed=False
        """
        # Minimal metrics
        anomaly_metrics = AnomalyMetrics(
            price_jump_pct=0.0,
            price_jump_detected=False,
            price_zscore=None,
            price_spike_detected=False,
            orderbook_age_ms=0,
            price_age_ms=0,
            stale_book_fresh_price=False,
            suspected_data_glitch=False,
            glitch_reason="N/A",
        )
        
        drp_trigger = DRPTrigger(
            should_trigger=False,
            trigger_reason="N/A",
            severity="LOW",
        )
        
        return Gate08Result(
            entry_allowed=False,
            block_reason=reason,
            anomaly_metrics=anomaly_metrics,
            drp_trigger=drp_trigger,
            details=reason,
        )
