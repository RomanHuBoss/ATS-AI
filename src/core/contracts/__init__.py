"""
Contract Validation Module

ТЗ: Appendix B (обязательные схемы контрактов)

Модуль для валидации JSON контрактов системы ATS-AI.
"""

from .validators import (
    ContractValidator,
    EngineSignalValidator,
    MarketStateValidator,
    MLEOutputValidator,
    PortfolioStateValidator,
    SchemaLoader,
    validate_engine_signal,
    validate_market_state,
    validate_mle_output,
    validate_portfolio_state,
)

__all__ = [
    # Classes
    "SchemaLoader",
    "ContractValidator",
    "MarketStateValidator",
    "PortfolioStateValidator",
    "EngineSignalValidator",
    "MLEOutputValidator",
    # Functions
    "validate_market_state",
    "validate_portfolio_state",
    "validate_engine_signal",
    "validate_mle_output",
]
