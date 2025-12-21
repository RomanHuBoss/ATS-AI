"""Gates — индивидуальные гейты Gatekeeper системы.

ТЗ 3.3.2:
- GATE 0: Warm-up / Data Availability / Cross-Validation / Hard-gates / DQS
- GATE 1: DRP Kill-switch / Manual Halt / Trading Mode
- GATE 2: MRC Confidence + Baseline + Conflict Resolution
- GATE 3: Strategy Compatibility
- GATE 4: Signal Validation
- GATE 5: Pre-sizing + Size-invariant Costs
- GATE 6: MLE Decision (size-invariant price-edge)
- GATE 7: Liquidity Check
- GATE 8: Gap/Data Glitch Detection
- GATE 9-18: дальнейшие гейты (будущие итерации)
"""

from .gate_00_warmup_dqs import Gate00WarmupDQS, Gate00Result
from .gate_01_drp_killswitch import Gate01DRPKillswitch, Gate01Result
from .gate_02_mrc_confidence import Gate02MRCConfidence, Gate02Result, Gate02Config
from .gate_03_strategy_compat import Gate03StrategyCompat, Gate03Result
from .gate_04_signal_validation import Gate04SignalValidation, Gate04Result, Gate04Config
from .gate_05_pre_sizing import Gate05PreSizing, Gate05Result, Gate05Config
from .gate_06_mle_decision import Gate06MLEDecision, Gate06Result, Gate06Config, MLEDecision
from .gate_07_liquidity_check import (
    Gate07LiquidityCheck,
    Gate07Result,
    Gate07Config,
    LiquidityMetrics,
    LiquidityMultipliers,
)
from .gate_08_gap_glitch import (
    Gate08GapGlitch,
    Gate08Result,
    Gate08Config,
    PricePoint,
    AnomalyMetrics,
    DRPTrigger,
)

__all__ = [
    "Gate00WarmupDQS",
    "Gate00Result",
    "Gate01DRPKillswitch",
    "Gate01Result",
    "Gate02MRCConfidence",
    "Gate02Result",
    "Gate02Config",
    "Gate03StrategyCompat",
    "Gate03Result",
    "Gate04SignalValidation",
    "Gate04Result",
    "Gate04Config",
    "Gate05PreSizing",
    "Gate05Result",
    "Gate05Config",
    "Gate06MLEDecision",
    "Gate06Result",
    "Gate06Config",
    "MLEDecision",
    "Gate07LiquidityCheck",
    "Gate07Result",
    "Gate07Config",
    "LiquidityMetrics",
    "LiquidityMultipliers",
    "Gate08GapGlitch",
    "Gate08Result",
    "Gate08Config",
    "PricePoint",
    "AnomalyMetrics",
    "DRPTrigger",
]
