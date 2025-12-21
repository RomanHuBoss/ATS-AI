"""Gatekeeper — система гейтов для допуска сигналов к исполнению.

ТЗ 3.3.2:
- 18 gates с фиксированным порядком
- Size-invariant до GATE 14
- SHADOW mode обработка после GATE 6
"""

from .gates.gate_00_warmup_dqs import Gate00WarmupDQS, Gate00Result

__all__ = [
    "Gate00WarmupDQS",
    "Gate00Result",
]
