"""Gates — индивидуальные гейты Gatekeeper системы.

ТЗ 3.3.2:
- GATE 0: Warm-up / Data Availability / Cross-Validation / Hard-gates / DQS
- GATE 1: DRP Kill-switch / Manual Halt / Trading Mode
- GATE 2: MRC Confidence + Baseline + Conflict Resolution
- GATE 3: Strategy Compatibility
- GATE 4-18: дальнейшие гейты (будущие итерации)
"""

from .gate_00_warmup_dqs import Gate00WarmupDQS, Gate00Result
from .gate_01_drp_killswitch import Gate01DRPKillswitch, Gate01Result
from .gate_02_mrc_confidence import Gate02MRCConfidence, Gate02Result, Gate02Config
from .gate_03_strategy_compat import Gate03StrategyCompat, Gate03Result

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
]
