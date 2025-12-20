"""
Domain models and value objects.

Contains fundamental domain entities like RiskUnits, Position, Trade, Signal.
"""

from src.core.domain.position import Direction as PositionDirection
from src.core.domain.position import Position
from src.core.domain.signal import Direction as SignalDirection
from src.core.domain.signal import (
    EngineType,
    Signal,
    SignalConstraints,
    SignalContext,
    SignalLevels,
)
from src.core.domain.trade import Direction as TradeDirection
from src.core.domain.trade import ExitReason, Trade
from src.core.domain.units import (
    EQUITY_MIN_FOR_PCT_CALC_USD,
    PNL_EPS_USD,
    RISK_AMOUNT_EPS_USD,
    RISK_AMOUNT_MIN_ABSOLUTE_USD,
    equity_effective,
    pnl_to_r_value,
    r_value_to_pnl,
    risk_pct_to_usd,
    risk_usd_to_pct,
    validate_equity,
    validate_risk_amount,
)

__all__ = [
    # Units module
    "PNL_EPS_USD",
    "RISK_AMOUNT_EPS_USD",
    "RISK_AMOUNT_MIN_ABSOLUTE_USD",
    "EQUITY_MIN_FOR_PCT_CALC_USD",
    "equity_effective",
    "risk_pct_to_usd",
    "risk_usd_to_pct",
    "pnl_to_r_value",
    "r_value_to_pnl",
    "validate_risk_amount",
    "validate_equity",
    # Position model
    "Position",
    "PositionDirection",
    # Trade model
    "Trade",
    "TradeDirection",
    "ExitReason",
    # Signal model
    "Signal",
    "SignalDirection",
    "EngineType",
    "SignalLevels",
    "SignalContext",
    "SignalConstraints",
]

