"""GATE 7: Liquidity Check — проверка ликвидности рынка

ТЗ 3.3.2 строка 1024, 1052 (GATE 7: Liquidity gates)
ТЗ раздел 2215-2223 (liquidity_mult формула)
ТЗ раздел 2291-2300 (OBI и детектор мнимой ликвидности)

Проверяет:
- Depth (bid/ask) в USD >= min thresholds
- Spread в bps <= max threshold
- Volume 24h в USD >= min threshold
- OBI (Order Book Imbalance) в разумных границах
- Depth volatility для детектирования spoofing

Вычисляет:
- liquidity_mult = min(spread_mult, impact_mult)
- spread_mult = smooth degradation между soft/hard thresholds
- impact_mult = smooth degradation на основе impact estimate

Интеграция:
- Использует результаты GATE 0-6 (должны быть PASS)
- Size-invariant (не зависит от qty)
- liquidity_mult используется в REM для корректировки риска
"""

import math
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


# =============================================================================
# CONSTANTS
# =============================================================================

# Epsilon для защиты от деления на 0
DEPTH_EPS: Final[float] = 1e-6
OBI_EPS: Final[float] = 1e-9
DEPTH_VOL_EPS: Final[float] = 1e-6

# Default impact parameters (ТЗ 2067)
DEFAULT_IMPACT_K: Final[float] = 0.10
DEFAULT_IMPACT_POW: Final[float] = 0.5


# =============================================================================
# DATA CLASSES
# =============================================================================


@dataclass(frozen=True)
class LiquidityMetrics:
    """Метрики ликвидности рынка."""
    
    # Depth metrics (USD)
    bid_depth_usd: float
    ask_depth_usd: float
    total_depth_usd: float
    
    # Spread metrics (bps)
    spread_bps: float
    
    # Volume metrics (USD)
    volume_24h_usd: float
    
    # Order Book Imbalance
    obi: float  # (bid_vol - ask_vol) / (bid_vol + ask_vol)
    
    # Depth volatility (для детектирования spoofing)
    depth_volatility_cv: float  # coefficient of variation
    spoofing_suspected: bool


@dataclass(frozen=True)
class LiquidityMultipliers:
    """Множители ликвидности для корректировки риска."""
    
    spread_mult: float  # [0, 1] — degradation по spread
    impact_mult: float  # [0, 1] — degradation по impact
    liquidity_mult: float  # min(spread_mult, impact_mult)
    
    # Диагностика
    limiting_factor: str  # "spread" или "impact"


# =============================================================================
# RESULT
# =============================================================================


@dataclass(frozen=True)
class Gate07Result:
    """Результат GATE 7."""
    
    entry_allowed: bool
    block_reason: str
    
    # Liquidity metrics
    liquidity_metrics: LiquidityMetrics
    
    # Liquidity multipliers
    liquidity_multipliers: LiquidityMultipliers
    
    # Impact estimate (bps)
    impact_bps_est: float
    
    # Детали
    details: str


# =============================================================================
# CONFIG
# =============================================================================


@dataclass(frozen=True)
class Gate07Config:
    """Конфигурация GATE 7.
    
    Параметры для liquidity checks и multipliers.
    """
    
    # Depth thresholds (USD) — hard limits
    bid_depth_min_usd: float = 500_000.0  # probe_min_depth_usd из ТЗ
    ask_depth_min_usd: float = 500_000.0
    
    # Spread thresholds (bps) — ТЗ 3088-3089
    spread_max_hard_bps: float = 25.0  # hard reject
    spread_max_soft_bps: float = 10.0  # начало degradation
    
    # Volume threshold (USD, 24h)
    volume_24h_min_usd: float = 10_000_000.0  # 10M USD за 24h
    
    # Impact parameters (ТЗ 2067)
    impact_k: float = DEFAULT_IMPACT_K
    impact_pow: float = DEFAULT_IMPACT_POW
    impact_max_hard_bps: float = 20.0  # hard reject
    impact_max_soft_bps: float = 8.0   # начало degradation
    
    # OBI thresholds
    obi_max_abs: float = 0.80  # |OBI| > 0.80 → suspect
    
    # Depth volatility threshold (для spoofing detection)
    depth_volatility_threshold: float = 0.50  # CV > 0.50 → suspect
    
    # Spoofing block
    spoofing_block_enabled: bool = True


# =============================================================================
# GATE 7
# =============================================================================


class Gate07LiquidityCheck:
    """GATE 7: Liquidity Check — проверка ликвидности рынка.
    
    Проверяет:
    1. Depth (bid/ask) >= min thresholds (hard limits)
    2. Spread <= max threshold (hard limit)
    3. Volume 24h >= min threshold (hard limit)
    4. OBI в разумных границах
    5. Depth volatility (spoofing detection)
    
    Вычисляет:
    1. spread_mult = clip((max_hard - spread) / (max_hard - max_soft), 0, 1)
    2. impact_bps_est = impact_k * (notional / depth)^impact_pow
    3. impact_mult = clip((max_hard - impact) / (max_hard - max_soft), 0, 1)
    4. liquidity_mult = min(spread_mult, impact_mult)
    
    Порядок проверок:
    1. GATE 0-6 блокировки (должны быть PASS)
    2. Depth checks (hard limits)
    3. Spread check (hard limit)
    4. Volume check (hard limit)
    5. OBI check (warning)
    6. Depth volatility check (spoofing detection)
    7. Вычисление liquidity_mult
    """
    
    def __init__(self, config: Gate07Config | None = None):
        """Инициализация GATE 7.
        
        Args:
            config: конфигурация gate (опционально, используется default)
        """
        self.config = config or Gate07Config()
    
    def evaluate(
        self,
        # GATE 0-6 результаты
        gate00_result: Gate00Result,
        gate01_result: Gate01Result,
        gate02_result: Gate02Result,
        gate03_result: Gate03Result,
        gate04_result: Gate04Result,
        gate05_result: Gate05Result,
        gate06_result: Gate06Result,
        
        # Signal
        signal: Signal,
        
        # Market data (liquidity)
        bid_depth_usd: float,
        ask_depth_usd: float,
        spread_bps: float,
        volume_24h_usd: float,
        
        # OBI и depth volatility
        bid_volume_1pct: float,
        ask_volume_1pct: float,
        depth_mean: float,
        depth_sigma: float,
        
        # Notional для impact estimate (из GATE 5 или mock)
        notional_usd: float,
    ) -> Gate07Result:
        """Оценка GATE 7: Liquidity check.
        
        Args:
            gate00_result: результат GATE 0
            gate01_result: результат GATE 1
            gate02_result: результат GATE 2
            gate03_result: результат GATE 3
            gate04_result: результат GATE 4
            gate05_result: результат GATE 5
            gate06_result: результат GATE 6
            signal: engine signal
            bid_depth_usd: глубина bid стороны в USD
            ask_depth_usd: глубина ask стороны в USD
            spread_bps: spread в bps
            volume_24h_usd: объём торгов за 24h в USD
            bid_volume_1pct: объём bid в 1% от mid
            ask_volume_1pct: объём ask в 1% от mid
            depth_mean: среднее depth за окно
            depth_sigma: std depth за окно
            notional_usd: планируемый notional для impact estimate
        
        Returns:
            Gate07Result с liquidity metrics и multipliers
        """
        # 1. Проверка GATE 0-6 блокировок
        if not gate00_result.entry_allowed:
            return self._blocked_result(
                reason=f"gate00_blocked: {gate00_result.block_reason}",
                bid_depth_usd=bid_depth_usd,
                ask_depth_usd=ask_depth_usd,
                spread_bps=spread_bps,
                volume_24h_usd=volume_24h_usd,
            )
        
        if not gate01_result.entry_allowed:
            return self._blocked_result(
                reason=f"gate01_blocked: {gate01_result.block_reason}",
                bid_depth_usd=bid_depth_usd,
                ask_depth_usd=ask_depth_usd,
                spread_bps=spread_bps,
                volume_24h_usd=volume_24h_usd,
            )
        
        if not gate02_result.entry_allowed:
            return self._blocked_result(
                reason=f"gate02_blocked: {gate02_result.block_reason}",
                bid_depth_usd=bid_depth_usd,
                ask_depth_usd=ask_depth_usd,
                spread_bps=spread_bps,
                volume_24h_usd=volume_24h_usd,
            )
        
        if not gate03_result.entry_allowed:
            return self._blocked_result(
                reason=f"gate03_blocked: {gate03_result.block_reason}",
                bid_depth_usd=bid_depth_usd,
                ask_depth_usd=ask_depth_usd,
                spread_bps=spread_bps,
                volume_24h_usd=volume_24h_usd,
            )
        
        if not gate04_result.entry_allowed:
            return self._blocked_result(
                reason=f"gate04_blocked: {gate04_result.block_reason}",
                bid_depth_usd=bid_depth_usd,
                ask_depth_usd=ask_depth_usd,
                spread_bps=spread_bps,
                volume_24h_usd=volume_24h_usd,
            )
        
        if not gate05_result.entry_allowed:
            return self._blocked_result(
                reason=f"gate05_blocked: {gate05_result.block_reason}",
                bid_depth_usd=bid_depth_usd,
                ask_depth_usd=ask_depth_usd,
                spread_bps=spread_bps,
                volume_24h_usd=volume_24h_usd,
            )
        
        if not gate06_result.entry_allowed:
            return self._blocked_result(
                reason=f"gate06_blocked: {gate06_result.block_reason}",
                bid_depth_usd=bid_depth_usd,
                ask_depth_usd=ask_depth_usd,
                spread_bps=spread_bps,
                volume_24h_usd=volume_24h_usd,
            )
        
        # 2. Depth checks (hard limits)
        if bid_depth_usd < self.config.bid_depth_min_usd:
            return self._create_result(
                entry_allowed=False,
                block_reason=(
                    f"bid_depth_too_low: {bid_depth_usd:.0f} < "
                    f"{self.config.bid_depth_min_usd:.0f} USD"
                ),
                bid_depth_usd=bid_depth_usd,
                ask_depth_usd=ask_depth_usd,
                spread_bps=spread_bps,
                volume_24h_usd=volume_24h_usd,
                bid_volume_1pct=bid_volume_1pct,
                ask_volume_1pct=ask_volume_1pct,
                depth_mean=depth_mean,
                depth_sigma=depth_sigma,
                notional_usd=notional_usd,
            )
        
        if ask_depth_usd < self.config.ask_depth_min_usd:
            return self._create_result(
                entry_allowed=False,
                block_reason=(
                    f"ask_depth_too_low: {ask_depth_usd:.0f} < "
                    f"{self.config.ask_depth_min_usd:.0f} USD"
                ),
                bid_depth_usd=bid_depth_usd,
                ask_depth_usd=ask_depth_usd,
                spread_bps=spread_bps,
                volume_24h_usd=volume_24h_usd,
                bid_volume_1pct=bid_volume_1pct,
                ask_volume_1pct=ask_volume_1pct,
                depth_mean=depth_mean,
                depth_sigma=depth_sigma,
                notional_usd=notional_usd,
            )
        
        # 3. Spread check (hard limit)
        if spread_bps > self.config.spread_max_hard_bps:
            return self._create_result(
                entry_allowed=False,
                block_reason=(
                    f"spread_too_wide: {spread_bps:.2f} > "
                    f"{self.config.spread_max_hard_bps:.2f} bps"
                ),
                bid_depth_usd=bid_depth_usd,
                ask_depth_usd=ask_depth_usd,
                spread_bps=spread_bps,
                volume_24h_usd=volume_24h_usd,
                bid_volume_1pct=bid_volume_1pct,
                ask_volume_1pct=ask_volume_1pct,
                depth_mean=depth_mean,
                depth_sigma=depth_sigma,
                notional_usd=notional_usd,
            )
        
        # 4. Volume check (hard limit)
        if volume_24h_usd < self.config.volume_24h_min_usd:
            return self._create_result(
                entry_allowed=False,
                block_reason=(
                    f"volume_too_low: {volume_24h_usd:.0f} < "
                    f"{self.config.volume_24h_min_usd:.0f} USD"
                ),
                bid_depth_usd=bid_depth_usd,
                ask_depth_usd=ask_depth_usd,
                spread_bps=spread_bps,
                volume_24h_usd=volume_24h_usd,
                bid_volume_1pct=bid_volume_1pct,
                ask_volume_1pct=ask_volume_1pct,
                depth_mean=depth_mean,
                depth_sigma=depth_sigma,
                notional_usd=notional_usd,
            )
        
        # 5. OBI вычисление (ТЗ 2294)
        # OBI = (bid_vol - ask_vol) / (bid_vol + ask_vol)
        total_vol = bid_volume_1pct + ask_volume_1pct
        if total_vol > OBI_EPS:
            obi = (bid_volume_1pct - ask_volume_1pct) / total_vol
        else:
            obi = 0.0
        
        # OBI check (warning, не блокируем)
        # abs(OBI) > threshold → suspect, но не hard reject
        # Логируем в details
        
        # 6. Depth volatility (spoofing detection, ТЗ 2297-2298)
        if depth_mean > DEPTH_VOL_EPS:
            depth_volatility_cv = depth_sigma / depth_mean
        else:
            depth_volatility_cv = 0.0
        
        spoofing_suspected = depth_volatility_cv > self.config.depth_volatility_threshold
        
        # Spoofing block (если включен)
        if spoofing_suspected and self.config.spoofing_block_enabled:
            return self._create_result(
                entry_allowed=False,
                block_reason=(
                    f"spoofing_suspected: depth_volatility_cv={depth_volatility_cv:.3f} > "
                    f"{self.config.depth_volatility_threshold:.3f}"
                ),
                bid_depth_usd=bid_depth_usd,
                ask_depth_usd=ask_depth_usd,
                spread_bps=spread_bps,
                volume_24h_usd=volume_24h_usd,
                bid_volume_1pct=bid_volume_1pct,
                ask_volume_1pct=ask_volume_1pct,
                depth_mean=depth_mean,
                depth_sigma=depth_sigma,
                notional_usd=notional_usd,
            )
        
        # 7. Вычисление liquidity_mult
        result = self._create_result(
            entry_allowed=True,
            block_reason="",
            bid_depth_usd=bid_depth_usd,
            ask_depth_usd=ask_depth_usd,
            spread_bps=spread_bps,
            volume_24h_usd=volume_24h_usd,
            bid_volume_1pct=bid_volume_1pct,
            ask_volume_1pct=ask_volume_1pct,
            depth_mean=depth_mean,
            depth_sigma=depth_sigma,
            notional_usd=notional_usd,
        )
        
        return result
    
    def _create_result(
        self,
        entry_allowed: bool,
        block_reason: str,
        bid_depth_usd: float,
        ask_depth_usd: float,
        spread_bps: float,
        volume_24h_usd: float,
        bid_volume_1pct: float,
        ask_volume_1pct: float,
        depth_mean: float,
        depth_sigma: float,
        notional_usd: float,
    ) -> Gate07Result:
        """Создание Gate07Result с вычислением всех metrics и multipliers.
        
        Args:
            entry_allowed: разрешён ли вход
            block_reason: причина блокировки (если есть)
            ... (liquidity data)
        
        Returns:
            Gate07Result
        """
        # 1. LiquidityMetrics
        total_depth_usd = bid_depth_usd + ask_depth_usd
        
        # OBI
        total_vol = bid_volume_1pct + ask_volume_1pct
        if total_vol > OBI_EPS:
            obi = (bid_volume_1pct - ask_volume_1pct) / total_vol
        else:
            obi = 0.0
        
        # Depth volatility
        if depth_mean > DEPTH_VOL_EPS:
            depth_volatility_cv = depth_sigma / depth_mean
        else:
            depth_volatility_cv = 0.0
        
        spoofing_suspected = depth_volatility_cv > self.config.depth_volatility_threshold
        
        liquidity_metrics = LiquidityMetrics(
            bid_depth_usd=bid_depth_usd,
            ask_depth_usd=ask_depth_usd,
            total_depth_usd=total_depth_usd,
            spread_bps=spread_bps,
            volume_24h_usd=volume_24h_usd,
            obi=obi,
            depth_volatility_cv=depth_volatility_cv,
            spoofing_suspected=spoofing_suspected,
        )
        
        # 2. Impact estimate (ТЗ 2067)
        # impact_bps_est = impact_k * (notional / depth)^impact_pow
        avg_depth = total_depth_usd / 2.0  # среднее между bid и ask
        impact_bps_est = self.config.impact_k * (
            (notional_usd / max(avg_depth, DEPTH_EPS)) ** self.config.impact_pow
        ) * 10000.0  # конвертируем в bps
        
        # 3. Liquidity multipliers (ТЗ 2218-2220)
        # spread_mult = clip((max_hard - spread) / (max_hard - max_soft), 0, 1)
        spread_range = self.config.spread_max_hard_bps - self.config.spread_max_soft_bps
        if spread_range > 1e-9:
            spread_mult = max(0.0, min(1.0, 
                (self.config.spread_max_hard_bps - spread_bps) / spread_range
            ))
        else:
            # Если hard == soft, то либо 0, либо 1
            spread_mult = 1.0 if spread_bps <= self.config.spread_max_soft_bps else 0.0
        
        # impact_mult = clip((max_hard - impact) / (max_hard - max_soft), 0, 1)
        impact_range = self.config.impact_max_hard_bps - self.config.impact_max_soft_bps
        if impact_range > 1e-9:
            impact_mult = max(0.0, min(1.0,
                (self.config.impact_max_hard_bps - impact_bps_est) / impact_range
            ))
        else:
            impact_mult = 1.0 if impact_bps_est <= self.config.impact_max_soft_bps else 0.0
        
        # liquidity_mult = min(spread_mult, impact_mult)
        liquidity_mult = min(spread_mult, impact_mult)
        
        # Limiting factor
        limiting_factor = "spread" if spread_mult <= impact_mult else "impact"
        
        liquidity_multipliers = LiquidityMultipliers(
            spread_mult=spread_mult,
            impact_mult=impact_mult,
            liquidity_mult=liquidity_mult,
            limiting_factor=limiting_factor,
        )
        
        # 4. Details
        if entry_allowed:
            details = (
                f"PASS: liquidity_mult={liquidity_mult:.3f} "
                f"(spread_mult={spread_mult:.3f}, impact_mult={impact_mult:.3f}), "
                f"spread={spread_bps:.2f}bps, impact_est={impact_bps_est:.2f}bps, "
                f"depth={total_depth_usd:.0f}USD, volume_24h={volume_24h_usd:.0f}USD, "
                f"OBI={obi:.3f}, depth_vol_cv={depth_volatility_cv:.3f}"
            )
            if spoofing_suspected:
                details += f" [SPOOFING_SUSPECTED]"
            if abs(obi) > self.config.obi_max_abs:
                details += f" [OBI_HIGH]"
        else:
            details = block_reason
        
        return Gate07Result(
            entry_allowed=entry_allowed,
            block_reason=block_reason,
            liquidity_metrics=liquidity_metrics,
            liquidity_multipliers=liquidity_multipliers,
            impact_bps_est=impact_bps_est,
            details=details,
        )
    
    def _blocked_result(
        self,
        reason: str,
        bid_depth_usd: float,
        ask_depth_usd: float,
        spread_bps: float,
        volume_24h_usd: float,
    ) -> Gate07Result:
        """Создание blocked result (GATE 0-6 блокировка).
        
        Args:
            reason: причина блокировки
            ... (minimal liquidity data)
        
        Returns:
            Gate07Result с entry_allowed=False
        """
        # Minimal metrics
        liquidity_metrics = LiquidityMetrics(
            bid_depth_usd=bid_depth_usd,
            ask_depth_usd=ask_depth_usd,
            total_depth_usd=bid_depth_usd + ask_depth_usd,
            spread_bps=spread_bps,
            volume_24h_usd=volume_24h_usd,
            obi=0.0,
            depth_volatility_cv=0.0,
            spoofing_suspected=False,
        )
        
        liquidity_multipliers = LiquidityMultipliers(
            spread_mult=0.0,
            impact_mult=0.0,
            liquidity_mult=0.0,
            limiting_factor="N/A",
        )
        
        return Gate07Result(
            entry_allowed=False,
            block_reason=reason,
            liquidity_metrics=liquidity_metrics,
            liquidity_multipliers=liquidity_multipliers,
            impact_bps_est=0.0,
            details=reason,
        )
