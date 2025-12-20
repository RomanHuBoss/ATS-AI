"""
Core math modules для ATS-AI

Математические примитивы и численные алгоритмы с гарантией стабильности.
"""

# Numerical Safeguards (ТЗ 2.3, 8.4)
from src.core.math.numerical_safeguards import (
    # Epsilon constants
    EPS_CALC,
    EPS_FLOAT_COMPARE_ABS,
    EPS_FLOAT_COMPARE_REL,
    EPS_PRICE,
    EPS_QTY,
    # Safe division
    denom_safe_signed,
    denom_safe_unsigned,
    safe_divide,
    # NaN/Inf sanitization
    is_valid_float,
    sanitize_array,
    sanitize_float,
    # Epsilon comparisons
    compare_with_tolerance,
    is_close,
    is_negative,
    is_positive,
    is_zero,
    # Utilities
    clamp,
    normalize_to_range,
    round_to_epsilon,
    # Validation
    validate_in_range,
    validate_non_negative,
    validate_positive,
)

# Effective Prices (ТЗ 2.1.1.1)
from src.core.math.effective_prices import (
    ABS_MIN_UNIT_RISK_USD,
    DEFAULT_STOP_SLIPPAGE_MULT,
    DEFAULT_UNIT_RISK_MIN_ATR_MULT,
    PositionSide,
    bps_to_fraction,
    calculate_effective_prices,
    calculate_unit_risk_allin_net,
    compute_effective_prices_with_validation,
    validate_unit_risk,
)

# Compounding (ТЗ 2.1.2)
from src.core.math.compounding import (
    COMPOUNDING_R_FLOOR_EPS,
    LOG1P_SWITCH_THRESHOLD,
    TARGET_RETURN_ANNUAL_DEFAULT,
    TRADES_PER_YEAR_DEFAULT,
    VARIANCE_DRAG_CRITICAL_FRAC,
    CompoundingDomainViolation,
    VarianceDragMetrics,
    check_variance_drag_critical,
    clamp_compound_rate_emergency,
    compound_equity,
    compound_equity_trajectory,
    compute_variance_drag_metrics,
    estimate_trades_per_year,
    safe_compound_rate,
    safe_log_return,
)

__all__ = [
    # Numerical Safeguards — Epsilon constants
    "EPS_CALC",
    "EPS_FLOAT_COMPARE_ABS",
    "EPS_FLOAT_COMPARE_REL",
    "EPS_PRICE",
    "EPS_QTY",
    # Numerical Safeguards — Safe division
    "denom_safe_signed",
    "denom_safe_unsigned",
    "safe_divide",
    # Numerical Safeguards — NaN/Inf sanitization
    "is_valid_float",
    "sanitize_array",
    "sanitize_float",
    # Numerical Safeguards — Epsilon comparisons
    "compare_with_tolerance",
    "is_close",
    "is_negative",
    "is_positive",
    "is_zero",
    # Numerical Safeguards — Utilities
    "clamp",
    "normalize_to_range",
    "round_to_epsilon",
    # Numerical Safeguards — Validation
    "validate_in_range",
    "validate_non_negative",
    "validate_positive",
    # Effective Prices — Constants
    "ABS_MIN_UNIT_RISK_USD",
    "DEFAULT_STOP_SLIPPAGE_MULT",
    "DEFAULT_UNIT_RISK_MIN_ATR_MULT",
    # Effective Prices — Types
    "PositionSide",
    # Effective Prices — Functions
    "bps_to_fraction",
    "calculate_effective_prices",
    "calculate_unit_risk_allin_net",
    "compute_effective_prices_with_validation",
    "validate_unit_risk",
    # Compounding — Constants
    "COMPOUNDING_R_FLOOR_EPS",
    "LOG1P_SWITCH_THRESHOLD",
    "TARGET_RETURN_ANNUAL_DEFAULT",
    "TRADES_PER_YEAR_DEFAULT",
    "VARIANCE_DRAG_CRITICAL_FRAC",
    # Compounding — Exceptions
    "CompoundingDomainViolation",
    # Compounding — Types
    "VarianceDragMetrics",
    # Compounding — Functions
    "check_variance_drag_critical",
    "clamp_compound_rate_emergency",
    "compound_equity",
    "compound_equity_trajectory",
    "compute_variance_drag_metrics",
    "estimate_trades_per_year",
    "safe_compound_rate",
    "safe_log_return",
]
