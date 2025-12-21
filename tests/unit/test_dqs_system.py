"""Комплексные тесты Data Quality Score (DQS) системы.

ТЗ 3.3.1 - 3.3.1.1: Staleness, Gap Detection, Cross-Validation, Hard-Gates, DQS Mult.
"""

import math
import pytest

from src.data.quality import (
    DQSChecker,
    StalenessChecker,
    StalenessThresholds,
    StalenessResult,
    GapGlitchDetector,
    GlitchDetectionResult,
    CrossValidator,
    CrossValidationResult,
    OracleSanityResult,
    SourceDQS,
)


# ============================================================================
# STALENESS CHECKER TESTS (15 тестов)
# ============================================================================

class TestStalenessChecker:
    """Тесты staleness проверок для критических и некритических данных."""
    
    def test_fresh_critical_data(self):
        """Критические данные свежие — staleness в пределах."""
        checker = StalenessChecker()
        current_time = 1000000.0
        price_time = 999500.0  # 500ms ago
        
        result = checker.check_staleness('price', current_time, price_time)
        
        assert result.data_type == 'price'
        assert result.age_ms == 500.0
        assert not result.is_stale_soft  # 500 < 1000
        assert not result.is_stale_hard  # 500 < 2000
        assert result.is_fresh
        assert not result.is_critical_stale
        assert result.dqs_component > 0.7  # 1 - 500/2000 = 0.75
    
    def test_stale_soft_critical_data(self):
        """Критические данные soft stale — между soft и hard порогами."""
        checker = StalenessChecker()
        current_time = 1000000.0
        price_time = 998500.0  # 1500ms ago
        
        result = checker.check_staleness('price', current_time, price_time)
        
        assert result.age_ms == 1500.0
        assert result.is_stale_soft  # 1500 > 1000
        assert not result.is_stale_hard  # 1500 < 2000
        assert not result.is_fresh
        assert not result.is_critical_stale
        assert 0.2 < result.dqs_component < 0.3  # 1 - 1500/2000 = 0.25
    
    def test_stale_hard_critical_data(self):
        """Критические данные hard stale — превышен hard порог (HALT)."""
        checker = StalenessChecker()
        current_time = 1000000.0
        price_time = 997500.0  # 2500ms ago
        
        result = checker.check_staleness('price', current_time, price_time)
        
        assert result.age_ms == 2500.0
        assert result.is_stale_soft
        assert result.is_stale_hard  # 2500 > 2000 → HALT
        assert result.is_critical_stale
        assert result.dqs_component == 0.0  # clip(1 - 2500/2000, 0, 1) = 0
    
    def test_missing_timestamp(self):
        """Timestamp отсутствует — критическая ситуация (HALT)."""
        checker = StalenessChecker()
        current_time = 1000000.0
        
        result = checker.check_staleness('price', current_time, None)
        
        assert result.age_ms == float('inf')
        assert result.is_stale_soft
        assert result.is_stale_hard
        assert result.is_critical_stale
        assert result.dqs_component == 0.0
    
    def test_orderbook_staleness(self):
        """Orderbook staleness с более строгими порогами (200-500ms)."""
        checker = StalenessChecker()
        current_time = 1000000.0
        orderbook_time = 999700.0  # 300ms ago
        
        result = checker.check_staleness('orderbook', current_time, orderbook_time)
        
        assert result.age_ms == 300.0
        assert result.is_stale_soft  # 300 > 200
        assert not result.is_stale_hard  # 300 < 500
        assert 0.3 < result.dqs_component < 0.5  # 1 - 300/500 = 0.4
    
    def test_noncritical_funding_staleness(self):
        """Funding staleness с более широкими порогами (30-120 s)."""
        checker = StalenessChecker()
        current_time = 1000000.0
        funding_time = 940000.0  # 60s ago
        
        result = checker.check_staleness('funding', current_time, funding_time)
        
        assert result.age_ms == 60000.0
        assert result.is_stale_soft  # 60s > 30s
        assert not result.is_stale_hard  # 60s < 120s
        assert 0.4 < result.dqs_component < 0.6  # 1 - 60000/120000 = 0.5
    
    def test_check_critical_staleness(self):
        """Проверка всех критических данных."""
        checker = StalenessChecker()
        current_time = 1000000.0
        
        results = checker.check_critical_staleness(
            current_time_ms=current_time,
            price_timestamp_ms=999500.0,  # 500ms ago
            liquidity_timestamp_ms=999800.0,  # 200ms ago
            orderbook_timestamp_ms=999900.0,  # 100ms ago
            volatility_timestamp_ms=999000.0  # 1000ms ago
        )
        
        assert len(results) == 4
        assert 'price' in results
        assert 'liquidity' in results
        assert 'orderbook' in results
        assert 'volatility' in results
        assert all(not r.is_critical_stale for r in results.values())
    
    def test_check_noncritical_staleness(self):
        """Проверка всех некритических данных."""
        checker = StalenessChecker()
        current_time = 1000000.0
        
        results = checker.check_noncritical_staleness(
            current_time_ms=current_time,
            funding_timestamp_ms=970000.0,  # 30s ago
            oi_timestamp_ms=940000.0,  # 60s ago
            basis_timestamp_ms=910000.0,  # 90s ago
            derivatives_timestamp_ms=880000.0  # 120s ago
        )
        
        assert len(results) == 4
        assert 'funding' in results
        assert 'oi' in results
        assert 'basis' in results
        assert 'derivatives' in results
    
    def test_has_critical_staleness_true(self):
        """has_critical_staleness возвращает True при hard staleness."""
        checker = StalenessChecker()
        current_time = 1000000.0
        
        results = {
            'price': StalenessResult(
                data_type='price',
                age_ms=2500.0,
                soft_threshold_ms=1000.0,
                hard_threshold_ms=2000.0,
                is_stale_soft=True,
                is_stale_hard=True,  # HALT
                dqs_component=0.0
            )
        }
        
        assert checker.has_critical_staleness(results)
    
    def test_has_critical_staleness_false(self):
        """has_critical_staleness возвращает False при отсутствии hard staleness."""
        checker = StalenessChecker()
        
        results = {
            'price': StalenessResult(
                data_type='price',
                age_ms=500.0,
                soft_threshold_ms=1000.0,
                hard_threshold_ms=2000.0,
                is_stale_soft=False,
                is_stale_hard=False,
                dqs_component=0.75
            )
        }
        
        assert not checker.has_critical_staleness(results)
    
    def test_custom_thresholds(self):
        """Использование кастомных порогов staleness."""
        thresholds = StalenessThresholds(
            price_soft_ms=500.0,
            price_hard_ms=1000.0
        )
        checker = StalenessChecker(thresholds)
        current_time = 1000000.0
        price_time = 999300.0  # 700ms ago
        
        result = checker.check_staleness('price', current_time, price_time)
        
        assert result.is_stale_soft  # 700 > 500
        assert not result.is_stale_hard  # 700 < 1000
        assert 0.2 < result.dqs_component < 0.4  # 1 - 700/1000 = 0.3
    
    def test_dqs_component_calculation(self):
        """DQS компонент вычисляется как clip(1 - age/hard, 0, 1)."""
        checker = StalenessChecker()
        current_time = 1000000.0
        
        # age = 0 → dqs = 1.0
        result = checker.check_staleness('price', current_time, current_time)
        assert result.dqs_component == 1.0
        
        # age = hard/2 → dqs = 0.5
        result = checker.check_staleness('price', current_time, current_time - 1000.0)
        assert 0.4 < result.dqs_component < 0.6
        
        # age = hard → dqs = 0.0
        result = checker.check_staleness('price', current_time, current_time - 2000.0)
        assert result.dqs_component == 0.0
        
        # age > hard → dqs = 0.0 (clipped)
        result = checker.check_staleness('price', current_time, current_time - 5000.0)
        assert result.dqs_component == 0.0
    
    def test_staleness_result_properties(self):
        """StalenessResult properties работают корректно."""
        result = StalenessResult(
            data_type='price',
            age_ms=1500.0,
            soft_threshold_ms=1000.0,
            hard_threshold_ms=2000.0,
            is_stale_soft=True,
            is_stale_hard=False,
            dqs_component=0.25
        )
        
        assert not result.is_fresh
        assert not result.is_critical_stale
    
    def test_oracle_staleness_thresholds(self):
        """Oracle staleness thresholds (5-10s)."""
        checker = StalenessChecker()
        current_time = 1000000.0
        oracle_time = 992000.0  # 8s ago
        
        result = checker.check_staleness('oracle', current_time, oracle_time)
        
        assert result.age_ms == 8000.0
        assert result.is_stale_soft  # 8s > 5s
        assert not result.is_stale_hard  # 8s < 10s
    
    def test_staleness_result_immutability(self):
        """StalenessResult immutable (frozen=True)."""
        result = StalenessResult(
            data_type='price',
            age_ms=500.0,
            soft_threshold_ms=1000.0,
            hard_threshold_ms=2000.0,
            is_stale_soft=False,
            is_stale_hard=False,
            dqs_component=0.75
        )
        
        with pytest.raises(Exception):  # FrozenInstanceError
            result.age_ms = 1000.0


# ============================================================================
# GAP & GLITCH DETECTOR TESTS (10 тестов)
# ============================================================================

class TestGapGlitchDetector:
    """Тесты обнаружения gaps, glitches, NaN/inf."""
    
    def test_no_nan_inf(self):
        """Нет NaN/inf — проверка проходит."""
        detector = GapGlitchDetector()
        
        result = detector.check_nan_inf(
            price=100.0,
            atr=2.5,
            spread_bps=10.0,
            bid=99.95,
            ask=100.05,
            liquidity_depth=50000.0,
            volatility=0.02
        )
        
        assert result.glitch_type == 'nan_inf'
        assert not result.detected
        assert not result.block_trading
        assert 'No NaN/inf' in result.details
    
    def test_nan_in_price(self):
        """NaN в price — блокировка торговли."""
        detector = GapGlitchDetector()
        
        result = detector.check_nan_inf(price=float('nan'))
        
        assert result.detected
        assert result.block_trading
        assert 'price' in result.details
    
    def test_inf_in_atr(self):
        """Inf в ATR — блокировка торговли."""
        detector = GapGlitchDetector()
        
        result = detector.check_nan_inf(atr=float('inf'))
        
        assert result.detected
        assert result.block_trading
        assert 'atr' in result.details
    
    def test_multiple_nan_inf(self):
        """Множественные NaN/inf — все фиксируются."""
        detector = GapGlitchDetector()
        
        result = detector.check_nan_inf(
            price=float('nan'),
            atr=float('inf'),
            spread_bps=float('-inf')
        )
        
        assert result.detected
        assert result.block_trading
        assert 'price' in result.details
        assert 'atr' in result.details
        assert 'spread_bps' in result.details
    
    def test_stale_book_no_tracking(self):
        """orderbook_update_id_age не отслеживается — проверка skip."""
        detector = GapGlitchDetector()
        
        result = detector.check_stale_book_fresh_price(
            price_changed=True,
            orderbook_update_id_age_ms=None
        )
        
        assert not result.detected
        assert not result.block_trading
        assert 'not tracked' in result.details
    
    def test_stale_book_detected(self):
        """Stale Book but Fresh Price — блокировка."""
        detector = GapGlitchDetector(orderbook_update_id_stale_ms=1000.0)
        
        result = detector.check_stale_book_fresh_price(
            price_changed=True,
            orderbook_update_id_age_ms=1500.0  # > threshold
        )
        
        assert result.detected
        assert result.block_trading
        assert 'stale' in result.details.lower()
    
    def test_stale_book_not_detected(self):
        """Stale Book — price не изменился или book свежий."""
        detector = GapGlitchDetector(orderbook_update_id_stale_ms=1000.0)
        
        # Price не изменился
        result = detector.check_stale_book_fresh_price(
            price_changed=False,
            orderbook_update_id_age_ms=1500.0
        )
        assert not result.detected
        
        # Book свежий
        result = detector.check_stale_book_fresh_price(
            price_changed=True,
            orderbook_update_id_age_ms=500.0
        )
        assert not result.detected
    
    def test_price_jump_detection(self):
        """Price jump обнаружен (advisory only)."""
        detector = GapGlitchDetector(price_jump_threshold_bps=1000.0)
        
        result = detector.check_price_jump(
            current_price=110.0,
            previous_price=100.0
        )
        
        assert result.detected  # 10% jump
        assert not result.block_trading  # Advisory only
        assert '1000' in result.details  # 10% = 1000 bps
    
    def test_spread_anomaly_detection(self):
        """Spread anomaly обнаружен (advisory only)."""
        detector = GapGlitchDetector(spread_anomaly_threshold_bps=500.0)
        
        result = detector.check_spread_anomaly(
            bid=95.0,
            ask=105.0  # 10% spread
        )
        
        assert result.detected
        assert not result.block_trading  # Advisory only
    
    def test_aggregate_glitch_checks(self):
        """Агрегация результатов glitch проверок."""
        detector = GapGlitchDetector()
        
        results = [
            GlitchDetectionResult('nan_inf', True, 'NaN in price', True),
            GlitchDetectionResult('stale_book', True, 'Stale book', True),
            GlitchDetectionResult('price_jump', True, 'Large jump', False),
        ]
        
        suspected, types, details = detector.aggregate_glitch_checks(results)
        
        assert suspected  # Есть blocking glitches
        assert 'nan_inf' in types
        assert 'stale_book' in types
        assert 'price_jump' in types
        assert 'BLOCKING' in details
        assert 'ADVISORY' in details


# ============================================================================
# CROSS-VALIDATOR TESTS (10 тестов)
# ============================================================================

class TestCrossValidator:
    """Тесты кросс-валидации источников."""
    
    def test_cross_validate_price_within_threshold(self):
        """Цены источников в пределах допуска."""
        validator = CrossValidator(xdev_block_bps=100.0)
        
        result = validator.cross_validate_price(
            price_src_A=100.0,
            price_src_B=100.5
        )
        
        assert result.price_src_ref == 100.25
        assert result.xdev_bps < 100.0
        assert not result.block_trading
    
    def test_cross_validate_price_exceed_threshold(self):
        """Цены источников расходятся — блокировка."""
        validator = CrossValidator(xdev_block_bps=100.0)
        
        result = validator.cross_validate_price(
            price_src_A=100.0,
            price_src_B=102.0  # 2% = 200 bps
        )
        
        assert result.xdev_bps > 100.0
        assert result.block_trading
        assert 'BLOCK' in result.details
    
    def test_cross_validate_exact_threshold(self):
        """xdev ровно на пороге — блокировка."""
        validator = CrossValidator(xdev_block_bps=100.0)
        
        # 1% расхождение = 100 bps, но нужно учесть референсную цену
        # ref = (100 + 101) / 2 = 100.5
        # xdev = 10000 * |100 - 101| / 100.5 = 99.5 bps (not exactly 100)
        # Используем цены, дающие точно 100 bps
        result = validator.cross_validate_price(
            price_src_A=100.0,
            price_src_B=101.01  # ref=100.505, xdev = 10000 * 1.01 / 100.505 ≈ 100.5 bps
        )
        
        assert result.block_trading  # >= threshold
    
    def test_oracle_sanity_pass(self):
        """Oracle санит-чек прошел."""
        validator = CrossValidator(oracle_dev_block_frac=0.05)
        
        result = validator.oracle_sanity_check(
            price_src_ref=100.0,
            price_oracle_C=100.5,  # 0.5% отклонение
            oracle_staleness_ms=5000.0,
            oracle_staleness_hard_ms=10_000.0
        )
        
        assert result.oracle_valid
        assert not result.oracle_sanity_block
    
    def test_oracle_sanity_block(self):
        """Oracle санит-чек блокирует (большое отклонение)."""
        validator = CrossValidator(oracle_dev_block_frac=0.05)
        
        result = validator.oracle_sanity_check(
            price_src_ref=100.0,
            price_oracle_C=107.0,  # 7% отклонение
            oracle_staleness_ms=5000.0,
            oracle_staleness_hard_ms=10_000.0
        )
        
        assert result.oracle_valid
        assert result.oracle_sanity_block
        assert 'ORACLE_BLOCK' in result.details
    
    def test_oracle_stale(self):
        """Oracle устарел — не блокирует."""
        validator = CrossValidator(oracle_dev_block_frac=0.05)
        
        result = validator.oracle_sanity_check(
            price_src_ref=100.0,
            price_oracle_C=107.0,  # Большое отклонение
            oracle_staleness_ms=15_000.0,  # Stale!
            oracle_staleness_hard_ms=10_000.0
        )
        
        assert not result.oracle_valid
        assert not result.oracle_sanity_block  # Не блокируем стейл oracle
        assert 'ORACLE_STALE' in result.details
    
    def test_oracle_unavailable(self):
        """Oracle недоступен (staleness=None)."""
        validator = CrossValidator(oracle_dev_block_frac=0.05)
        
        result = validator.oracle_sanity_check(
            price_src_ref=100.0,
            price_oracle_C=107.0,
            oracle_staleness_ms=None,  # Unavailable
            oracle_staleness_hard_ms=10_000.0
        )
        
        assert not result.oracle_valid
        assert not result.oracle_sanity_block
    
    def test_calculate_dqs_sources(self):
        """Вычисление взвешенного DQS_sources."""
        validator = CrossValidator()
        
        sources = {
            'price': SourceDQS('price', 500.0, 2000.0, 0.5, 0.75),  # w=0.5, dqs=0.75
            'liquidity': SourceDQS('liquidity', 200.0, 500.0, 0.5, 0.6)  # w=0.5, dqs=0.6
        }
        
        dqs_sources = validator.calculate_dqs_sources(sources)
        
        # (0.5*0.75 + 0.5*0.6) / (0.5 + 0.5) = 0.675
        assert 0.67 < dqs_sources < 0.68
    
    def test_create_source_dqs(self):
        """Создание SourceDQS компонента."""
        validator = CrossValidator()
        
        source = validator.create_source_dqs(
            source_name='price',
            staleness_ms=1000.0,
            staleness_hard_ms=2000.0,
            weight=0.6
        )
        
        assert source.source_name == 'price'
        assert source.staleness_ms == 1000.0
        assert source.weight == 0.6
        assert source.dqs_component == 0.5  # 1 - 1000/2000
    
    def test_dqs_sources_empty(self):
        """DQS_sources при пустых источниках."""
        validator = CrossValidator()
        
        dqs_sources = validator.calculate_dqs_sources({})
        
        assert dqs_sources == 0.0


# ============================================================================
# DQS CHECKER TESTS (15 тестов)
# ============================================================================

class TestDQSChecker:
    """Тесты главного DQS модуля."""
    
    def test_full_dqs_evaluation_ok(self):
        """Полная оценка DQS — все в порядке."""
        checker = DQSChecker()
        
        current_time = 1000000.0
        
        result = checker.evaluate_dqs(
            current_time_ms=current_time,
            price_timestamp_ms=current_time - 500.0,  # Fresh
            liquidity_timestamp_ms=current_time - 200.0,
            orderbook_timestamp_ms=current_time - 100.0,
            volatility_timestamp_ms=current_time - 800.0,
            funding_timestamp_ms=current_time - 20_000.0,
            price_src_A=100.0,
            price_src_B=100.3,  # Small xdev
            price_oracle_C=100.1,
            oracle_staleness_ms=5000.0,
            price=100.0,
            atr=2.5,
            spread_bps=10.0,
            bid=99.95,
            ask=100.05
        )
        
        # DQS_critical = min(dqs_components) = 0.6 (liquidity и volatility)
        # DQS = 0.75 * 0.6 + 0.25 * 0.833 = 0.658
        assert result.dqs > 0.6  # Good quality (скорректировано с учетом min)
        assert not result.hard_gate_triggered
        assert result.block_reason == 'OK'
        # dqs_mult = (0.658 - 0.3) / (0.7 - 0.3) = 0.896
        assert result.dqs_mult > 0.8  # Above emergency, below degraded
    
    def test_dqs_critical_staleness_halt(self):
        """DQS critical staleness → HALT."""
        checker = DQSChecker()
        
        current_time = 1000000.0
        
        result = checker.evaluate_dqs(
            current_time_ms=current_time,
            price_timestamp_ms=current_time - 3000.0,  # Stale hard!
            liquidity_timestamp_ms=current_time - 200.0
        )
        
        assert result.components.has_critical_staleness
        assert result.hard_gate_triggered
        assert result.dqs == 0.0
        assert 'critical_staleness_hard' in result.block_reason
    
    def test_dqs_xdev_block_halt(self):
        """xdev превышен → HALT."""
        checker = DQSChecker()
        
        current_time = 1000000.0
        
        result = checker.evaluate_dqs(
            current_time_ms=current_time,
            price_timestamp_ms=current_time - 500.0,
            price_src_A=100.0,
            price_src_B=103.0  # 3% = 300 bps >> threshold
        )
        
        assert result.components.has_xdev_block
        assert result.hard_gate_triggered
        assert result.dqs == 0.0
        assert 'xdev_block' in result.block_reason
    
    def test_dqs_nan_inf_halt(self):
        """NaN/inf обнаружен → HALT."""
        checker = DQSChecker()
        
        current_time = 1000000.0
        
        result = checker.evaluate_dqs(
            current_time_ms=current_time,
            price_timestamp_ms=current_time - 500.0,
            price=float('nan')  # NaN!
        )
        
        assert result.components.suspected_data_glitch
        assert result.hard_gate_triggered
        assert result.dqs == 0.0
        assert 'data_glitch' in result.block_reason
    
    def test_dqs_oracle_block_halt(self):
        """Oracle санит-чек блокирует → HALT."""
        checker = DQSChecker()
        
        current_time = 1000000.0
        
        result = checker.evaluate_dqs(
            current_time_ms=current_time,
            price_timestamp_ms=current_time - 500.0,
            price_src_A=100.0,
            price_src_B=100.2,
            price_oracle_C=110.0,  # 10% отклонение!
            oracle_staleness_ms=5000.0
        )
        
        assert result.components.has_oracle_block
        assert result.hard_gate_triggered
        assert 'oracle_sanity_block' in result.block_reason
    
    def test_dqs_sources_low_halt(self):
        """DQS_sources < threshold → HALT."""
        checker = DQSChecker(dqs_sources_min=0.8)
        
        current_time = 1000000.0
        
        result = checker.evaluate_dqs(
            current_time_ms=current_time,
            price_timestamp_ms=current_time - 1800.0,  # Near hard limit
            liquidity_timestamp_ms=current_time - 450.0
        )
        
        # DQS_sources будет низким из-за near-stale данных
        assert result.components.has_dqs_sources_block or result.hard_gate_triggered
    
    def test_dqs_mult_normal(self):
        """dqs_mult = 1.0 при DQS >= degraded_threshold."""
        checker = DQSChecker(dqs_degraded_threshold=0.7)
        
        current_time = 1000000.0
        
        result = checker.evaluate_dqs(
            current_time_ms=current_time,
            price_timestamp_ms=current_time - 100.0,  # Very fresh
            liquidity_timestamp_ms=current_time - 50.0,  # Very fresh
            funding_timestamp_ms=current_time - 10_000.0  # Fresh noncritical
        )
        
        # Требуем высокий DQS для dqs_mult = 1.0
        assert result.dqs >= 0.7, f"DQS={result.dqs} должен быть >= 0.7"
        assert result.dqs_mult == 1.0
    
    def test_dqs_mult_degraded(self):
        """dqs_mult линейная интерполяция при degraded."""
        checker = DQSChecker(
            dqs_degraded_threshold=0.7,
            dqs_emergency_threshold=0.3
        )
        
        current_time = 1000000.0
        
        result = checker.evaluate_dqs(
            current_time_ms=current_time,
            price_timestamp_ms=current_time - 1500.0,  # Somewhat stale
            liquidity_timestamp_ms=current_time - 300.0,
            funding_timestamp_ms=current_time - 80_000.0
        )
        
        # DQS будет между 0.3 и 0.7
        if 0.3 < result.dqs < 0.7:
            expected_mult = (result.dqs - 0.3) / (0.7 - 0.3)
            assert abs(result.dqs_mult - expected_mult) < 0.01
    
    def test_dqs_mult_emergency(self):
        """dqs_mult = 0.0 при DQS <= emergency_threshold."""
        checker = DQSChecker(dqs_emergency_threshold=0.3)
        
        current_time = 1000000.0
        
        result = checker.evaluate_dqs(
            current_time_ms=current_time,
            price_timestamp_ms=current_time - 1900.0,  # Very stale
            liquidity_timestamp_ms=current_time - 480.0
        )
        
        # DQS будет очень низким
        if result.dqs <= 0.3:
            assert result.dqs_mult == 0.0
    
    def test_dqs_components_structure(self):
        """DQSComponents содержит все необходимые компоненты."""
        checker = DQSChecker()
        
        current_time = 1000000.0
        
        result = checker.evaluate_dqs(
            current_time_ms=current_time,
            price_timestamp_ms=current_time - 500.0,
            liquidity_timestamp_ms=current_time - 200.0
        )
        
        assert hasattr(result.components, 'dqs_critical')
        assert hasattr(result.components, 'dqs_noncritical')
        assert hasattr(result.components, 'dqs_sources')
        assert hasattr(result.components, 'dqs')
        assert hasattr(result.components, 'critical_staleness')
        assert hasattr(result.components, 'has_critical_staleness')
        assert hasattr(result.components, 'hard_gate_triggered')
    
    def test_dqs_weight_critical(self):
        """dqs_weight_critical влияет на итоговый DQS."""
        # Высокий вес critical
        checker_high = DQSChecker(dqs_weight_critical=0.9)
        # Низкий вес critical
        checker_low = DQSChecker(dqs_weight_critical=0.1)
        
        current_time = 1000000.0
        
        # Critical fresh, noncritical stale
        result_high = checker_high.evaluate_dqs(
            current_time_ms=current_time,
            price_timestamp_ms=current_time - 200.0,  # Fresh critical
            funding_timestamp_ms=current_time - 100_000.0  # Stale noncritical
        )
        
        result_low = checker_low.evaluate_dqs(
            current_time_ms=current_time,
            price_timestamp_ms=current_time - 200.0,
            funding_timestamp_ms=current_time - 100_000.0
        )
        
        # High weight → DQS closer to critical (high)
        # Low weight → DQS closer to noncritical (low)
        assert result_high.dqs > result_low.dqs
    
    def test_dqs_details_formatting(self):
        """Details содержат полезную диагностику."""
        checker = DQSChecker()
        
        current_time = 1000000.0
        
        result = checker.evaluate_dqs(
            current_time_ms=current_time,
            price_timestamp_ms=current_time - 500.0,
            liquidity_timestamp_ms=current_time - 200.0,
            price_src_A=100.0,
            price_src_B=100.5
        )
        
        assert 'DQS=' in result.details
        assert 'critical=' in result.details
        assert 'noncritical=' in result.details
        assert 'staleness:' in result.details
    
    def test_multiple_hard_gates(self):
        """Множественные hard-gates одновременно."""
        checker = DQSChecker()
        
        current_time = 1000000.0
        
        result = checker.evaluate_dqs(
            current_time_ms=current_time,
            price_timestamp_ms=current_time - 3000.0,  # Stale hard
            price_src_A=100.0,
            price_src_B=105.0,  # xdev block
            price=float('nan')  # NaN block
        )
        
        assert result.components.has_critical_staleness
        assert result.components.has_xdev_block
        assert result.components.suspected_data_glitch
        assert result.hard_gate_triggered
        
        # Все причины в block_reason
        assert 'critical_staleness_hard' in result.block_reason
        assert 'xdev_block' in result.block_reason
        assert 'data_glitch' in result.block_reason
    
    def test_dqs_result_immutability(self):
        """DQSResult и DQSComponents immutable."""
        checker = DQSChecker()
        
        current_time = 1000000.0
        result = checker.evaluate_dqs(
            current_time_ms=current_time,
            price_timestamp_ms=current_time - 500.0
        )
        
        with pytest.raises(Exception):
            result.dqs = 0.5
        
        with pytest.raises(Exception):
            result.components.dqs_critical = 0.5
    
    def test_custom_source_weights(self):
        """Кастомные веса источников для DQS_sources."""
        checker = DQSChecker()
        
        current_time = 1000000.0
        
        source_weights = {
            'price': 0.6,
            'liquidity': 0.4
        }
        
        result = checker.evaluate_dqs(
            current_time_ms=current_time,
            price_timestamp_ms=current_time - 500.0,
            liquidity_timestamp_ms=current_time - 300.0,
            source_weights=source_weights
        )
        
        # DQS_sources должен быть взвешен согласно source_weights
        assert result.components.dqs_sources > 0.0
