"""GATE 10: Correlation / Exposure Conflict

ТЗ 3.3.2 строка 1027, 1055 (GATE 10 — Modified: Correlation/Exposure Conflict)
ТЗ раздел 3.3.5: Portfolio-level constraints (size-invariant R)

CONFLICT NOTE: В ТЗ указан "Basis-risk", но реализован "Correlation/Exposure Conflict"
по требованию текущей итерации.

Проверяет:
- Correlation между новой позицией и существующими (max correlation threshold)
- Exposure conflicts (max exposure на один asset/sector/total)
- Portfolio-level constraints (max positions, concentration limits)
- All checks size-invariant (в R units)

Portfolio State Requirements:
- Текущие позиции с их exposure_R
- Correlation matrix между assets
- Asset/sector classifications

Порядок проверок:
1. GATE 0-9 блокировки (должны быть PASS)
2. Portfolio state validation
3. Correlation checks (с существующими позициями)
4. Exposure conflict detection (asset/sector/total)
5. Portfolio constraints (max positions, concentration)

Интеграция:
- Использует результаты GATE 0-9 (должны быть PASS)
- Size-invariant (все exposure в R units)
- Deterministic (reproducible results)
"""

from dataclasses import dataclass
from typing import Final

from src.core.domain.market_state import MarketState
from src.core.domain.signal import Direction, Signal
from src.gatekeeper.gates.gate_00_warmup_dqs import Gate00Result
from src.gatekeeper.gates.gate_01_drp_killswitch import Gate01Result
from src.gatekeeper.gates.gate_02_mrc_confidence import Gate02Result
from src.gatekeeper.gates.gate_03_strategy_compat import Gate03Result
from src.gatekeeper.gates.gate_04_signal_validation import Gate04Result
from src.gatekeeper.gates.gate_05_pre_sizing import Gate05Result
from src.gatekeeper.gates.gate_06_mle_decision import Gate06Result
from src.gatekeeper.gates.gate_07_liquidity_check import Gate07Result
from src.gatekeeper.gates.gate_08_gap_glitch import Gate08Result
from src.gatekeeper.gates.gate_09_funding_proximity import Gate09Result


# =============================================================================
# CONSTANTS
# =============================================================================

# Epsilon для защиты от деления на 0
EXPOSURE_EPS: Final[float] = 1e-9
CORRELATION_EPS: Final[float] = 1e-6

# Minimum exposure для correlation checks (absolute floor)
MIN_EXPOSURE_R_FOR_CORRELATION: Final[float] = 0.01  # 1% R


# =============================================================================
# DATA CLASSES
# =============================================================================


@dataclass(frozen=True)
class PositionInfo:
    """Информация о существующей позиции в портфеле."""
    
    instrument: str
    direction: Direction
    exposure_r: float  # Exposure в R units (size-invariant)
    asset_class: str  # e.g., "CRYPTO", "FX", "EQUITY"
    sector: str | None  # e.g., "TECH", "FINANCE", None для crypto
    entry_ts_utc_ms: int  # Timestamp входа в позицию


@dataclass(frozen=True)
class CorrelationMetrics:
    """Метрики correlation checks."""
    
    # Max correlation с существующими позициями
    max_correlation: float  # Максимальная корреляция
    max_correlation_instrument: str | None  # Инструмент с max correlation
    
    # Correlation statistics
    n_correlated_positions: int  # Число позиций с correlation > threshold
    avg_correlation: float  # Средняя корреляция со всеми позициями
    
    # Check results
    correlation_warning: bool  # Soft warning
    correlation_block: bool  # Hard block
    correlation_reason: str  # Описание (если warning/block)


@dataclass(frozen=True)
class ExposureMetrics:
    """Метрики exposure conflicts."""
    
    # Current portfolio exposure (до новой позиции)
    current_total_exposure_r: float  # Суммарный exposure портфеля
    current_asset_exposure_r: float  # Exposure на asset class новой позиции
    current_sector_exposure_r: float  # Exposure на sector новой позиции (if applicable)
    
    # New position impact
    new_position_exposure_r: float  # Exposure новой позиции
    
    # Projected exposure (после новой позиции)
    projected_total_exposure_r: float  # Суммарный после добавления
    projected_asset_exposure_r: float  # На asset class после добавления
    projected_sector_exposure_r: float  # На sector после добавления
    
    # Utilization ratios (as fractions)
    total_exposure_utilization: float  # projected / max_total
    asset_exposure_utilization: float  # projected / max_asset
    sector_exposure_utilization: float  # projected / max_sector
    
    # Check results
    exposure_warning: bool  # Soft warning
    exposure_block: bool  # Hard block
    exposure_reason: str  # Описание (если warning/block)


@dataclass(frozen=True)
class PortfolioConstraints:
    """Метрики portfolio-level constraints."""
    
    # Current state
    current_n_positions: int  # Текущее число позиций
    current_max_single_exposure_r: float  # Максимальный exposure одной позиции
    
    # New position impact
    projected_n_positions: int  # После добавления новой позиции
    
    # Concentration metrics
    new_position_concentration: float  # new_exposure / total_exposure
    max_position_concentration: float  # max_single / total_exposure (current)
    projected_max_concentration: float  # После добавления новой позиции
    
    # Check results
    positions_warning: bool  # Soft warning по числу позиций
    positions_block: bool  # Hard block по числу позиций
    concentration_warning: bool  # Soft warning по концентрации
    concentration_block: bool  # Hard block по концентрации
    constraints_reason: str  # Описание (если warning/block)


@dataclass(frozen=True)
class Gate10Result:
    """Результат GATE 10."""
    
    entry_allowed: bool
    block_reason: str
    
    # Correlation metrics
    correlation_metrics: CorrelationMetrics
    
    # Exposure metrics
    exposure_metrics: ExposureMetrics
    
    # Portfolio constraints
    portfolio_constraints: PortfolioConstraints
    
    # Risk multiplier (для использования в GATE 13-14)
    correlation_risk_mult: float  # Multiplier от correlation
    exposure_risk_mult: float  # Multiplier от exposure
    combined_risk_mult: float  # Combined multiplier
    
    # Детали
    details: str


# =============================================================================
# CONFIG
# =============================================================================


@dataclass(frozen=True)
class Gate10Config:
    """Конфигурация GATE 10.
    
    Параметры для correlation checks, exposure limits и portfolio constraints.
    """
    
    # Correlation thresholds
    max_correlation_soft: float = 0.70  # Soft warning
    max_correlation_hard: float = 0.85  # Hard block
    min_exposure_r_for_correlation: float = 0.01  # Minimum exposure для correlation checks
    
    # Exposure limits (в R units)
    max_total_exposure_r: float = 10.0  # Max суммарный exposure портфеля
    max_asset_exposure_r: float = 5.0   # Max exposure на один asset class
    max_sector_exposure_r: float = 3.0  # Max exposure на один sector
    
    # Exposure utilization thresholds (as fractions)
    exposure_soft_utilization: float = 0.80  # 80% — soft warning
    exposure_hard_utilization: float = 0.95  # 95% — hard block
    
    # Portfolio constraints
    max_positions_soft: int = 8   # Soft warning
    max_positions_hard: int = 10  # Hard block
    
    # Concentration limits (as fractions of total exposure)
    max_single_position_concentration_soft: float = 0.30  # 30% — soft warning
    max_single_position_concentration_hard: float = 0.40  # 40% — hard block
    
    # Risk multiplier parameters
    correlation_risk_mult_base: float = 1.0  # Базовый multiplier
    correlation_risk_mult_penalty_soft: float = 0.95  # При soft threshold
    correlation_risk_mult_penalty_hard: float = 0.85  # При приближении к hard
    
    exposure_risk_mult_base: float = 1.0  # Базовый multiplier
    exposure_risk_mult_penalty_soft: float = 0.95  # При soft threshold
    exposure_risk_mult_penalty_hard: float = 0.85  # При приближении к hard


# =============================================================================
# GATE 10
# =============================================================================


class Gate10CorrelationExposure:
    """GATE 10: Correlation / Exposure Conflict.
    
    Size-invariant проверка корреляций, exposure conflicts и portfolio constraints.
    
    Вычисляет:
    1. Correlation с существующими позициями
    2. Exposure conflicts (asset/sector/total)
    3. Portfolio constraints (positions, concentration)
    4. Risk multipliers для GATE 13-14
    
    Порядок проверок:
    1. GATE 0-9 блокировки (должны быть PASS)
    2. Portfolio state validation
    3. Correlation checks
    4. Exposure conflict detection
    5. Portfolio constraints validation
    """
    
    def __init__(self, config: Gate10Config | None = None):
        """Initialize GATE 10.
        
        Args:
            config: Конфигурация gate (default: Gate10Config())
        """
        self.config = config or Gate10Config()
    
    def evaluate(
        self,
        signal: Signal,
        market_state: MarketState,
        gate00: Gate00Result,
        gate01: Gate01Result,
        gate02: Gate02Result,
        gate03: Gate03Result,
        gate04: Gate04Result,
        gate05: Gate05Result,
        gate06: Gate06Result,
        gate07: Gate07Result,
        gate08: Gate08Result,
        gate09: Gate09Result,
        portfolio_positions: list[PositionInfo] | None = None,
        correlation_matrix: dict[tuple[str, str], float] | None = None,
        asset_class: str = "CRYPTO",
        sector: str | None = None,
    ) -> Gate10Result:
        """Evaluate GATE 10.
        
        Args:
            signal: Trading signal
            market_state: Market state
            gate00-gate09: Результаты предыдущих gates (должны быть PASS)
            portfolio_positions: Текущие позиции в портфеле (None = пустой портфель)
            correlation_matrix: Correlation matrix между instruments
                               Key: (instrument1, instrument2), Value: correlation [-1, 1]
            asset_class: Asset class новой позиции
            sector: Sector новой позиции (optional)
        
        Returns:
            Gate10Result с детальной диагностикой
        """
        # Step 1: Check предыдущие gates
        if not gate00.entry_allowed:
            return self._block(
                reason=f"GATE 00 blocked: {gate00.block_reason}",
                correlation_metrics=self._empty_correlation_metrics(),
                exposure_metrics=self._empty_exposure_metrics(),
                portfolio_constraints=self._empty_portfolio_constraints(),
            )
        
        if not gate01.entry_allowed:
            return self._block(
                reason=f"GATE 01 blocked: {gate01.block_reason}",
                correlation_metrics=self._empty_correlation_metrics(),
                exposure_metrics=self._empty_exposure_metrics(),
                portfolio_constraints=self._empty_portfolio_constraints(),
            )
        
        if not gate02.entry_allowed:
            return self._block(
                reason=f"GATE 02 blocked: {gate02.block_reason}",
                correlation_metrics=self._empty_correlation_metrics(),
                exposure_metrics=self._empty_exposure_metrics(),
                portfolio_constraints=self._empty_portfolio_constraints(),
            )
        
        if not gate03.entry_allowed:
            return self._block(
                reason=f"GATE 03 blocked: {gate03.block_reason}",
                correlation_metrics=self._empty_correlation_metrics(),
                exposure_metrics=self._empty_exposure_metrics(),
                portfolio_constraints=self._empty_portfolio_constraints(),
            )
        
        if not gate04.entry_allowed:
            return self._block(
                reason=f"GATE 04 blocked: {gate04.block_reason}",
                correlation_metrics=self._empty_correlation_metrics(),
                exposure_metrics=self._empty_exposure_metrics(),
                portfolio_constraints=self._empty_portfolio_constraints(),
            )
        
        if not gate05.entry_allowed:
            return self._block(
                reason=f"GATE 05 blocked: {gate05.block_reason}",
                correlation_metrics=self._empty_correlation_metrics(),
                exposure_metrics=self._empty_exposure_metrics(),
                portfolio_constraints=self._empty_portfolio_constraints(),
            )
        
        if not gate06.entry_allowed:
            return self._block(
                reason=f"GATE 06 blocked: {gate06.block_reason}",
                correlation_metrics=self._empty_correlation_metrics(),
                exposure_metrics=self._empty_exposure_metrics(),
                portfolio_constraints=self._empty_portfolio_constraints(),
            )
        
        if not gate07.entry_allowed:
            return self._block(
                reason=f"GATE 07 blocked: {gate07.block_reason}",
                correlation_metrics=self._empty_correlation_metrics(),
                exposure_metrics=self._empty_exposure_metrics(),
                portfolio_constraints=self._empty_portfolio_constraints(),
            )
        
        if not gate08.entry_allowed:
            return self._block(
                reason=f"GATE 08 blocked: {gate08.block_reason}",
                correlation_metrics=self._empty_correlation_metrics(),
                exposure_metrics=self._empty_exposure_metrics(),
                portfolio_constraints=self._empty_portfolio_constraints(),
            )
        
        if not gate09.entry_allowed:
            return self._block(
                reason=f"GATE 09 blocked: {gate09.block_reason}",
                correlation_metrics=self._empty_correlation_metrics(),
                exposure_metrics=self._empty_exposure_metrics(),
                portfolio_constraints=self._empty_portfolio_constraints(),
            )
        
        # Step 2: Extract exposure новой позиции (size-invariant)
        # Используем unit_risk_bps / 200 как exposure в R units
        # This normalizes to 1.0R for standard 200 bps (2%) risk
        # Size-invariant and represents risk as multiples of standard R
        new_position_exposure_r = gate05.unit_risk_bps / 200.0
        
        # Step 3: Portfolio state validation
        positions = portfolio_positions or []
        corr_matrix = correlation_matrix or {}
        
        # Step 4: Correlation checks
        correlation_metrics = self._check_correlation(
            signal=signal,
            positions=positions,
            correlation_matrix=corr_matrix,
            new_exposure_r=new_position_exposure_r,
        )
        
        if correlation_metrics.correlation_block:
            return self._block(
                reason=correlation_metrics.correlation_reason,
                correlation_metrics=correlation_metrics,
                exposure_metrics=self._empty_exposure_metrics(),
                portfolio_constraints=self._empty_portfolio_constraints(),
            )
        
        # Step 5: Exposure conflict detection
        exposure_metrics = self._check_exposure(
            positions=positions,
            new_exposure_r=new_position_exposure_r,
            asset_class=asset_class,
            sector=sector,
        )
        
        if exposure_metrics.exposure_block:
            return self._block(
                reason=exposure_metrics.exposure_reason,
                correlation_metrics=correlation_metrics,
                exposure_metrics=exposure_metrics,
                portfolio_constraints=self._empty_portfolio_constraints(),
            )
        
        # Step 6: Portfolio constraints validation
        portfolio_constraints = self._check_portfolio_constraints(
            positions=positions,
            new_exposure_r=new_position_exposure_r,
        )
        
        if portfolio_constraints.positions_block or portfolio_constraints.concentration_block:
            return self._block(
                reason=portfolio_constraints.constraints_reason,
                correlation_metrics=correlation_metrics,
                exposure_metrics=exposure_metrics,
                portfolio_constraints=portfolio_constraints,
            )
        
        # Step 7: Calculate risk multipliers
        correlation_risk_mult = self._calculate_correlation_risk_mult(correlation_metrics)
        exposure_risk_mult = self._calculate_exposure_risk_mult(exposure_metrics)
        combined_risk_mult = correlation_risk_mult * exposure_risk_mult
        
        # Step 8: Build details
        details_parts = []
        
        if correlation_metrics.correlation_warning:
            details_parts.append(f"Correlation WARNING: {correlation_metrics.correlation_reason}")
        
        if exposure_metrics.exposure_warning:
            details_parts.append(f"Exposure WARNING: {exposure_metrics.exposure_reason}")
        
        if portfolio_constraints.positions_warning:
            details_parts.append(f"Positions WARNING: approaching max positions")
        
        if portfolio_constraints.concentration_warning:
            details_parts.append(f"Concentration WARNING: high portfolio concentration")
        
        if not details_parts:
            details_parts.append("All correlation/exposure/portfolio checks PASS")
        
        details = "; ".join(details_parts)
        
        # PASS
        return Gate10Result(
            entry_allowed=True,
            block_reason="",
            correlation_metrics=correlation_metrics,
            exposure_metrics=exposure_metrics,
            portfolio_constraints=portfolio_constraints,
            correlation_risk_mult=correlation_risk_mult,
            exposure_risk_mult=exposure_risk_mult,
            combined_risk_mult=combined_risk_mult,
            details=details,
        )
    
    def _check_correlation(
        self,
        signal: Signal,
        positions: list[PositionInfo],
        correlation_matrix: dict[tuple[str, str], float],
        new_exposure_r: float,
    ) -> CorrelationMetrics:
        """Check correlation с существующими позициями.
        
        Args:
            signal: Trading signal
            positions: Текущие позиции
            correlation_matrix: Correlation matrix
            new_exposure_r: Exposure новой позиции
        
        Returns:
            CorrelationMetrics
        """
        # Empty portfolio — no correlation checks needed
        if not positions:
            return CorrelationMetrics(
                max_correlation=0.0,
                max_correlation_instrument=None,
                n_correlated_positions=0,
                avg_correlation=0.0,
                correlation_warning=False,
                correlation_block=False,
                correlation_reason="",
            )
        
        # Filter positions with significant exposure
        significant_positions = [
            p for p in positions
            if p.exposure_r >= self.config.min_exposure_r_for_correlation
        ]
        
        if not significant_positions:
            return CorrelationMetrics(
                max_correlation=0.0,
                max_correlation_instrument=None,
                n_correlated_positions=0,
                avg_correlation=0.0,
                correlation_warning=False,
                correlation_block=False,
                correlation_reason="",
            )
        
        # Calculate correlations
        correlations: list[tuple[str, float]] = []
        
        for pos in significant_positions:
            # Try both orderings of instrument pair
            key1 = (signal.instrument, pos.instrument)
            key2 = (pos.instrument, signal.instrument)
            
            correlation = correlation_matrix.get(key1, correlation_matrix.get(key2, 0.0))
            
            # Adjust correlation sign if directions differ
            # Same direction → positive correlation matters
            # Opposite direction → negative correlation (hedging) is OK
            if signal.direction != pos.direction:
                correlation = -abs(correlation)
            else:
                correlation = abs(correlation)
            
            correlations.append((pos.instrument, correlation))
        
        # Statistics
        if correlations:
            max_corr_instrument, max_corr = max(correlations, key=lambda x: x[1])
            avg_corr = sum(c for _, c in correlations) / len(correlations)
            n_correlated = sum(1 for _, c in correlations if c >= self.config.max_correlation_soft)
        else:
            max_corr_instrument, max_corr = None, 0.0
            avg_corr = 0.0
            n_correlated = 0
        
        # Checks
        correlation_warning = max_corr >= self.config.max_correlation_soft
        correlation_block = max_corr >= self.config.max_correlation_hard
        
        if correlation_block:
            reason = (
                f"High correlation with {max_corr_instrument}: "
                f"{max_corr:.3f} >= {self.config.max_correlation_hard:.3f}"
            )
        elif correlation_warning:
            reason = (
                f"Elevated correlation with {max_corr_instrument}: "
                f"{max_corr:.3f} >= {self.config.max_correlation_soft:.3f}"
            )
        else:
            reason = ""
        
        return CorrelationMetrics(
            max_correlation=max_corr,
            max_correlation_instrument=max_corr_instrument,
            n_correlated_positions=n_correlated,
            avg_correlation=avg_corr,
            correlation_warning=correlation_warning,
            correlation_block=correlation_block,
            correlation_reason=reason,
        )
    
    def _check_exposure(
        self,
        positions: list[PositionInfo],
        new_exposure_r: float,
        asset_class: str,
        sector: str | None,
    ) -> ExposureMetrics:
        """Check exposure conflicts.
        
        Args:
            positions: Текущие позиции
            new_exposure_r: Exposure новой позиции
            asset_class: Asset class новой позиции
            sector: Sector новой позиции
        
        Returns:
            ExposureMetrics
        """
        # Calculate current exposures
        current_total = sum(p.exposure_r for p in positions)
        current_asset = sum(p.exposure_r for p in positions if p.asset_class == asset_class)
        current_sector = sum(
            p.exposure_r for p in positions
            if sector is not None and p.sector == sector
        )
        
        # Projected exposures
        projected_total = current_total + new_exposure_r
        projected_asset = current_asset + new_exposure_r
        projected_sector = current_sector + new_exposure_r if sector is not None else 0.0
        
        # Utilization ratios
        total_util = projected_total / (self.config.max_total_exposure_r + EXPOSURE_EPS)
        asset_util = projected_asset / (self.config.max_asset_exposure_r + EXPOSURE_EPS)
        sector_util = (
            projected_sector / (self.config.max_sector_exposure_r + EXPOSURE_EPS)
            if sector is not None
            else 0.0
        )
        
        # Checks
        exposure_warning = (
            total_util >= self.config.exposure_soft_utilization
            or asset_util >= self.config.exposure_soft_utilization
            or sector_util >= self.config.exposure_soft_utilization
        )
        
        exposure_block = (
            total_util >= self.config.exposure_hard_utilization
            or asset_util >= self.config.exposure_hard_utilization
            or sector_util >= self.config.exposure_hard_utilization
        )
        
        # Reason
        reasons = []
        
        if total_util >= self.config.exposure_hard_utilization:
            reasons.append(
                f"Total exposure {projected_total:.2f}R exceeds hard limit "
                f"({self.config.max_total_exposure_r:.2f}R * {self.config.exposure_hard_utilization:.0%})"
            )
        elif total_util >= self.config.exposure_soft_utilization:
            reasons.append(
                f"Total exposure {projected_total:.2f}R approaching limit "
                f"({self.config.max_total_exposure_r:.2f}R * {self.config.exposure_soft_utilization:.0%})"
            )
        
        if asset_util >= self.config.exposure_hard_utilization:
            reasons.append(
                f"Asset {asset_class} exposure {projected_asset:.2f}R exceeds hard limit "
                f"({self.config.max_asset_exposure_r:.2f}R * {self.config.exposure_hard_utilization:.0%})"
            )
        elif asset_util >= self.config.exposure_soft_utilization:
            reasons.append(
                f"Asset {asset_class} exposure {projected_asset:.2f}R approaching limit "
                f"({self.config.max_asset_exposure_r:.2f}R * {self.config.exposure_soft_utilization:.0%})"
            )
        
        if sector is not None and sector_util >= self.config.exposure_hard_utilization:
            reasons.append(
                f"Sector {sector} exposure {projected_sector:.2f}R exceeds hard limit "
                f"({self.config.max_sector_exposure_r:.2f}R * {self.config.exposure_hard_utilization:.0%})"
            )
        elif sector is not None and sector_util >= self.config.exposure_soft_utilization:
            reasons.append(
                f"Sector {sector} exposure {projected_sector:.2f}R approaching limit "
                f"({self.config.max_sector_exposure_r:.2f}R * {self.config.exposure_soft_utilization:.0%})"
            )
        
        reason = "; ".join(reasons) if reasons else ""
        
        return ExposureMetrics(
            current_total_exposure_r=current_total,
            current_asset_exposure_r=current_asset,
            current_sector_exposure_r=current_sector,
            new_position_exposure_r=new_exposure_r,
            projected_total_exposure_r=projected_total,
            projected_asset_exposure_r=projected_asset,
            projected_sector_exposure_r=projected_sector,
            total_exposure_utilization=total_util,
            asset_exposure_utilization=asset_util,
            sector_exposure_utilization=sector_util,
            exposure_warning=exposure_warning,
            exposure_block=exposure_block,
            exposure_reason=reason,
        )
    
    def _check_portfolio_constraints(
        self,
        positions: list[PositionInfo],
        new_exposure_r: float,
    ) -> PortfolioConstraints:
        """Check portfolio-level constraints.
        
        Args:
            positions: Текущие позиции
            new_exposure_r: Exposure новой позиции
        
        Returns:
            PortfolioConstraints
        """
        # Current state
        current_n = len(positions)
        projected_n = current_n + 1
        
        # Concentration metrics
        current_total = sum(p.exposure_r for p in positions)
        current_max_single = max((p.exposure_r for p in positions), default=0.0)
        
        if current_total > EXPOSURE_EPS:
            max_position_concentration = current_max_single / current_total
        else:
            max_position_concentration = 0.0
        
        # Projected concentration
        projected_total = current_total + new_exposure_r
        projected_max_single = max(current_max_single, new_exposure_r)
        
        if projected_total > EXPOSURE_EPS:
            new_position_concentration = new_exposure_r / projected_total
            projected_max_concentration = projected_max_single / projected_total
        else:
            new_position_concentration = 0.0
            projected_max_concentration = 0.0
        
        # Checks
        positions_warning = projected_n >= self.config.max_positions_soft
        positions_block = projected_n > self.config.max_positions_hard
        
        # Concentration checks ONLY if portfolio is NOT empty
        # (first position always 100% concentration - это нормально)
        if current_n > 0:
            concentration_warning = (
                projected_max_concentration >= self.config.max_single_position_concentration_soft
            )
            concentration_block = (
                projected_max_concentration >= self.config.max_single_position_concentration_hard
            )
        else:
            concentration_warning = False
            concentration_block = False
        
        # Reason
        reasons = []
        
        if positions_block:
            reasons.append(
                f"Portfolio positions {projected_n} exceeds hard limit {self.config.max_positions_hard}"
            )
        elif positions_warning:
            reasons.append(
                f"Portfolio positions {projected_n} approaching limit {self.config.max_positions_hard}"
            )
        
        if concentration_block:
            reasons.append(
                f"Position concentration {projected_max_concentration:.1%} exceeds hard limit "
                f"{self.config.max_single_position_concentration_hard:.1%}"
            )
        elif concentration_warning:
            reasons.append(
                f"Position concentration {projected_max_concentration:.1%} approaching limit "
                f"{self.config.max_single_position_concentration_hard:.1%}"
            )
        
        reason = "; ".join(reasons) if reasons else ""
        
        return PortfolioConstraints(
            current_n_positions=current_n,
            current_max_single_exposure_r=current_max_single,
            projected_n_positions=projected_n,
            new_position_concentration=new_position_concentration,
            max_position_concentration=max_position_concentration,
            projected_max_concentration=projected_max_concentration,
            positions_warning=positions_warning,
            positions_block=positions_block,
            concentration_warning=concentration_warning,
            concentration_block=concentration_block,
            constraints_reason=reason,
        )
    
    def _calculate_correlation_risk_mult(
        self,
        correlation_metrics: CorrelationMetrics,
    ) -> float:
        """Calculate correlation risk multiplier.
        
        Args:
            correlation_metrics: Correlation metrics
        
        Returns:
            Risk multiplier [0.85, 1.0]
        """
        if correlation_metrics.correlation_block:
            # Shouldn't reach here (blocked earlier), but defensive
            return self.config.correlation_risk_mult_penalty_hard
        
        if correlation_metrics.correlation_warning:
            # Linear interpolation между soft и hard
            max_corr = correlation_metrics.max_correlation
            soft_thresh = self.config.max_correlation_soft
            hard_thresh = self.config.max_correlation_hard
            
            if hard_thresh > soft_thresh:
                t = (max_corr - soft_thresh) / (hard_thresh - soft_thresh)
                t = max(0.0, min(1.0, t))  # Clamp [0, 1]
                
                return (
                    self.config.correlation_risk_mult_penalty_soft * (1 - t)
                    + self.config.correlation_risk_mult_penalty_hard * t
                )
            else:
                return self.config.correlation_risk_mult_penalty_soft
        
        return self.config.correlation_risk_mult_base
    
    def _calculate_exposure_risk_mult(
        self,
        exposure_metrics: ExposureMetrics,
    ) -> float:
        """Calculate exposure risk multiplier.
        
        Args:
            exposure_metrics: Exposure metrics
        
        Returns:
            Risk multiplier [0.85, 1.0]
        """
        if exposure_metrics.exposure_block:
            # Shouldn't reach here (blocked earlier), but defensive
            return self.config.exposure_risk_mult_penalty_hard
        
        if exposure_metrics.exposure_warning:
            # Worst utilization
            max_util = max(
                exposure_metrics.total_exposure_utilization,
                exposure_metrics.asset_exposure_utilization,
                exposure_metrics.sector_exposure_utilization,
            )
            
            soft_thresh = self.config.exposure_soft_utilization
            hard_thresh = self.config.exposure_hard_utilization
            
            if hard_thresh > soft_thresh:
                t = (max_util - soft_thresh) / (hard_thresh - soft_thresh)
                t = max(0.0, min(1.0, t))  # Clamp [0, 1]
                
                return (
                    self.config.exposure_risk_mult_penalty_soft * (1 - t)
                    + self.config.exposure_risk_mult_penalty_hard * t
                )
            else:
                return self.config.exposure_risk_mult_penalty_soft
        
        return self.config.exposure_risk_mult_base
    
    def _block(
        self,
        reason: str,
        correlation_metrics: CorrelationMetrics,
        exposure_metrics: ExposureMetrics,
        portfolio_constraints: PortfolioConstraints,
    ) -> Gate10Result:
        """Create BLOCK result.
        
        Args:
            reason: Block reason
            correlation_metrics: Correlation metrics
            exposure_metrics: Exposure metrics
            portfolio_constraints: Portfolio constraints
        
        Returns:
            Gate10Result с entry_allowed=False
        """
        return Gate10Result(
            entry_allowed=False,
            block_reason=reason,
            correlation_metrics=correlation_metrics,
            exposure_metrics=exposure_metrics,
            portfolio_constraints=portfolio_constraints,
            correlation_risk_mult=1.0,
            exposure_risk_mult=1.0,
            combined_risk_mult=1.0,
            details=f"BLOCKED: {reason}",
        )
    
    def _empty_correlation_metrics(self) -> CorrelationMetrics:
        """Create empty correlation metrics."""
        return CorrelationMetrics(
            max_correlation=0.0,
            max_correlation_instrument=None,
            n_correlated_positions=0,
            avg_correlation=0.0,
            correlation_warning=False,
            correlation_block=False,
            correlation_reason="",
        )
    
    def _empty_exposure_metrics(self) -> ExposureMetrics:
        """Create empty exposure metrics."""
        return ExposureMetrics(
            current_total_exposure_r=0.0,
            current_asset_exposure_r=0.0,
            current_sector_exposure_r=0.0,
            new_position_exposure_r=0.0,
            projected_total_exposure_r=0.0,
            projected_asset_exposure_r=0.0,
            projected_sector_exposure_r=0.0,
            total_exposure_utilization=0.0,
            asset_exposure_utilization=0.0,
            sector_exposure_utilization=0.0,
            exposure_warning=False,
            exposure_block=False,
            exposure_reason="",
        )
    
    def _empty_portfolio_constraints(self) -> PortfolioConstraints:
        """Create empty portfolio constraints."""
        return PortfolioConstraints(
            current_n_positions=0,
            current_max_single_exposure_r=0.0,
            projected_n_positions=0,
            new_position_concentration=0.0,
            max_position_concentration=0.0,
            projected_max_concentration=0.0,
            positions_warning=False,
            positions_block=False,
            concentration_warning=False,
            concentration_block=False,
            constraints_reason="",
        )
