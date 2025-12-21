"""DRP (Disaster Recovery Protocol) — модули управления состоянием системы при аномалиях.

ТЗ 3.3.2, строки 958-982:
- DRP state machine с переходами на основе DQS
- Warm-up после emergency
- Anti-flapping механизмы
"""

from .state_machine import (
    DRPStateMachine,
    DRPTransitionResult,
    WarmupConfig,
    AntiFlappingConfig,
    EmergencyCause,
)

__all__ = [
    "DRPStateMachine",
    "DRPTransitionResult",
    "WarmupConfig",
    "AntiFlappingConfig",
    "EmergencyCause",
]
