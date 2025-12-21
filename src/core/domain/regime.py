"""Regime — Модели рыночных режимов (MRC, Baseline)

ТЗ 3.3.3 строки 1066-1111:
- MRC classifier (H1): TREND_UP, TREND_DOWN, RANGE, NOISE, BREAKOUT_UP, BREAKOUT_DOWN
- Baseline classifier: TREND_UP, TREND_DOWN, RANGE, NOISE
- Final regime: результат conflict resolution (+ NO_TRADE, PROBE_TRADE)

Immutable Pydantic модели для результатов классификации режима.
"""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# =============================================================================
# ENUMS
# =============================================================================


class MRCClass(str, Enum):
    """MRC классификация режима (H1 timeframe).
    
    ТЗ 3.3.3 строка 1076: MRC classes
    """
    
    TREND_UP = "TREND_UP"
    TREND_DOWN = "TREND_DOWN"
    RANGE = "RANGE"
    NOISE = "NOISE"
    BREAKOUT_UP = "BREAKOUT_UP"
    BREAKOUT_DOWN = "BREAKOUT_DOWN"


class BaselineClass(str, Enum):
    """Baseline классификация режима.
    
    ТЗ 3.3.3 строка 1076: Baseline classes
    """
    
    TREND_UP = "TREND_UP"
    TREND_DOWN = "TREND_DOWN"
    RANGE = "RANGE"
    NOISE = "NOISE"


class FinalRegime(str, Enum):
    """Final regime после conflict resolution.
    
    ТЗ 3.3.3 строки 1079-1111: Результат conflict resolution
    
    Includes:
    - Базовые классы MRC/Baseline
    - NO_TRADE — блокировка входов
    - PROBE_TRADE — probe режим при конфликте трендов
    """
    
    TREND_UP = "TREND_UP"
    TREND_DOWN = "TREND_DOWN"
    RANGE = "RANGE"
    NOISE = "NOISE"
    BREAKOUT_UP = "BREAKOUT_UP"
    BREAKOUT_DOWN = "BREAKOUT_DOWN"
    NO_TRADE = "NO_TRADE"
    PROBE_TRADE = "PROBE_TRADE"


# =============================================================================
# MODELS
# =============================================================================


class MRCResult(BaseModel):
    """Результат MRC classifier.
    
    ТЗ 3.3.3 строки 1069-1075: MRC confidence thresholds
    
    Содержит:
    - mrc_class: классификация режима
    - confidence: уверенность модели [0, 1]
    """
    
    mrc_class: MRCClass = Field(..., description="MRC classification")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence [0, 1]")
    
    model_config = {"frozen": True}


class BaselineResult(BaseModel):
    """Результат Baseline classifier.
    
    ТЗ 3.3.3 строка 1076: Baseline classes
    
    Baseline classifier:
    - Более простой алгоритм (fallback)
    - Используется для conflict resolution с MRC
    """
    
    baseline_class: BaselineClass = Field(..., description="Baseline classification")
    
    model_config = {"frozen": True}


class RegimeConflictInfo(BaseModel):
    """Информация о конфликте между MRC и Baseline.
    
    ТЗ 3.3.3 строки 1093-1111: Probe-режим и conflict resolution
    
    Используется для:
    - Детектирования устойчивых конфликтов (conflict_window_bars)
    - Probe-режима при конфликте трендов
    - Diagnostic block при превышении порога
    """
    
    conflict_detected: bool = Field(..., description="Флаг конфликта MRC vs Baseline")
    conflict_type: str = Field(..., description="Тип конфликта (trend_vs_trend, trend_vs_range, и т.д.)")
    is_probe_eligible: bool = Field(..., description="Возможен ли probe-режим")
    probe_conditions_met: bool = Field(..., description="Все условия probe выполнены")
    
    # Диагностика
    mrc_class: MRCClass = Field(..., description="MRC класс")
    baseline_class: BaselineClass = Field(..., description="Baseline класс")
    mrc_confidence: float = Field(..., ge=0.0, le=1.0, description="MRC confidence")
    
    model_config = {"frozen": True}
