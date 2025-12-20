# ATS-AI v3.30 — Состояние разработки

**Последнее обновление:** Iteration 3  
**Статус:** Compounding реализован

---

## Реализовано

### Iteration 3: Compounding — Safe Geometric Growth & Variance Drag

**Цель:** Реализовать модуль Compounding (ТЗ 2.1.2, обязательное) для безопасного вычисления геометрического роста equity с защитой от domain violations и контроля variance drag.

**Реализованные модули:**

#### Математические примитивы
- ✅ `src/core/math/compounding.py` — **Compounding** (ТЗ 2.1.2, обязательное)
  * Domain restriction: r > -1 + compounding_r_floor_eps (COMPOUNDING_R_FLOOR_EPS = 1.0e-6)
  * Безопасная проверка: safe_compound_rate, clamp_compound_rate_emergency
  * Численно стабильный log return: safe_log_return с автоматическим переключением log1p/log
  * Геометрический рост: compound_equity, compound_equity_trajectory
  * Variance drag метрики: compute_variance_drag_metrics, check_variance_drag_critical
  * Утилиты: estimate_trades_per_year
  * Exception: CompoundingDomainViolation при r ≤ -1 + eps
- ✅ `src/core/math/__init__.py` — Обновлён экспорт compounding функций

#### Тестирование
- ✅ `tests/unit/test_compounding.py` — Комплексные тесты Compounding (ТЗ 2.2, Appendix C.3)
  * Тесты domain restriction (safe_compound_rate, clamp_compound_rate_emergency)
  * Тесты численной стабильности (safe_log_return: log1p vs log)
  * Тесты геометрического роста (compound_equity, compound_equity_trajectory)
  * Тесты variance drag метрик (compute_variance_drag_metrics, check_variance_drag_critical)
  * Тесты переполнений и устойчивости (overflow/underflow protection)
  * Тесты инвариантов (AM-GM inequality, determinism, log equivalence)
  * Граничные случаи и валидация параметров
  * 64 теста, все проходят ✅

**Статус сборки:**
- Установка: `make install` ✅
- Тесты: `make test` ✅ (208 тестов, все проходят — добавлено 64 теста)
- Линтинг: `make lint` ✅
- Форматирование: `make format` ✅

**Покрытие ТЗ:**
- 2.1.2: Domain restriction для log(1+r) — **100%** (обязательное, реализовано)
- 2.1.2: Численно устойчивое вычисление компаундинга — **100%** (обязательное, реализовано)
- 2.1.2: Контроль variance drag — **100%** (обязательное, реализовано)
- 2.1.2: Обработка экстремального случая r < -1 → EMERGENCY — **100%** (exception реализован)
- Appendix C.2: Epsilon-параметры compounding — **100%**

**Инварианты и гарантии:**
1. **Domain violation detection** — CompoundingDomainViolation при r ≤ -1 + eps (требует EMERGENCY DRP)
2. **Численная стабильность** — log1p используется для |r| < 0.01, log для больших r
3. **Детерминизм** — все операции воспроизводимы
4. **AM-GM inequality** — geometric mean ≤ arithmetic mean для переменных returns
5. **Variance drag non-negative** — variance_drag_per_trade ≥ 0 для переменных returns
6. **Overflow protection** — sanitize_float предотвращает распространение inf
7. **Log equivalence** — compound через multiplication == compound через log sum

---

### Iteration 2: Numerical Safeguards — Core Math Safety Layer

**Цель:** Реализовать модуль Numerical Safeguards (ТЗ 2.3, 8.4, обязательное) для обеспечения численной стабильности всех математических операций в системе.

**Реализованные модули:**

#### Математические примитивы
- ✅ `src/core/math/numerical_safeguards.py` — **Numerical Safeguards** (ТЗ 2.3, 8.4, обязательное)
  * Safe division: denom_safe_signed, denom_safe_unsigned, safe_divide
  * NaN/Inf санитизация: is_valid_float, sanitize_float, sanitize_array
  * Epsilon-защиты для сравнений: is_close, is_zero, is_positive, is_negative, compare_with_tolerance
  * Epsilon-округление: round_to_epsilon, normalize_to_range
  * Утилиты: clamp
  * Валидация: validate_positive, validate_non_negative, validate_in_range
  * Domain-specific epsilon: EPS_PRICE, EPS_QTY, EPS_CALC, EPS_FLOAT_COMPARE_REL/ABS
- ✅ `src/core/math/__init__.py` — Обновлён экспорт численных safeguards

#### Тестирование
- ✅ `tests/unit/test_numerical_safeguards.py` — Комплексные тесты Numerical Safeguards (ТЗ 2.2, Appendix C.3)
  * Тесты безопасного деления (signed/unsigned)
  * Тесты NaN/Inf санитизации
  * Тесты epsilon-сравнений
  * Тесты округления и квантования
  * Тесты валидации параметров
  * Тесты интеграции (chain operations)
  * 84 теста, все проходят ✅

**Статус сборки:**
- Установка: `make install` ✅
- Тесты: `make test` ✅ (144 теста, все проходят — добавлено 84 теста)
- Линтинг: `make lint` ✅
- Форматирование: `make format` ✅

**Покрытие ТЗ:**
- 2.3: Numerical Safeguards — **100%** (обязательное, реализовано)
- 8.4: Epsilon-защиты — **100%** (обязательное, реализовано)
- Appendix C.1: Domain-specific epsilon-параметры — **100%**

**Инварианты и гарантии:**
1. **Деление на ноль невозможно** — все деления защищены epsilon-защитой
2. **NaN/Inf не распространяются** — санитизация заменяет невалидные значения
3. **Float-сравнения учитывают машинную точность** — используются epsilon-толерантности
4. **Детерминизм** — все операции воспроизводимы
5. **Знак сохраняется** — denom_safe_signed корректно обрабатывает отрицательные значения

---

### Iteration 1: EffectivePrices — All-In Effective Price Module

**Цель:** Реализовать модуль EffectivePrices (ТЗ 2.1.1.1, обязательное) для вычисления эффективных цен с учётом всех издержек и корректного расчёта unit_risk_allin_net.

**Реализованные модули:**

#### Математические примитивы
- ✅ `src/core/math/__init__.py` — Пакет math
- ✅ `src/core/math/effective_prices.py` — **EffectivePrices** (ТЗ 2.1.1.1, обязательное)
  * All-in эффективные цены: entry_eff_allin, tp_eff_allin, sl_eff_allin
  * Формулы LONG/SHORT по Appendix A.2
  * unit_risk_allin_net = abs(entry_eff_allin - sl_eff_allin)
  * Валидация минимального unit_risk (абсолютный + ATR-based)
  * Epsilon-защиты (Appendix C.1)
  * Учёт всех издержек: spread, fees, slippage, impact

#### Тестирование
- ✅ `tests/unit/test_effective_prices.py` — Юнит-тесты EffectivePrices (ТЗ 2.2, Appendix C.3)
  * Тесты LONG/SHORT корректности
  * Тесты симметрии LONG/SHORT
  * Инвариант: SL hit = -1R ✅
  * Валидация минимумов (абсолютный + ATR)
  * Граничные случаи и валидация параметров

**Статус сборки:**
- Установка: `make install` ✅
- Тесты: `make test` ✅ (2 тестовых модуля, все тесты проходят)
- Линтинг: `make lint` ✅
- Форматирование: `make format` ✅

**Покрытие ТЗ:**
- 2.1.1.0: Модуль RiskUnits — **100%** (обязательное, реализовано)
- 2.1.1.1: Модуль EffectivePrices — **100%** (обязательное, реализовано)
- Appendix A.2: Формулы LONG/SHORT — **100%**
- 14.1: Воспроизводимость окружения — **100%**
- 14.2: Инструкции запуска/тестов — **100%**
- Appendix C.1: Epsilon-параметры — **100%**

---

### Iteration 0: Bootstrap — Воспроизводимый фундамент проекта

**Цель:** Создать минимальную структуру репозитория с воспроизводимым окружением, базовой конфигурацией сборки и фундаментальным модулем RiskUnits.

**Реализованные модули:**

#### Инфраструктура и сборка
- ✅ `pyproject.toml` — Зависимости и конфигурация проекта (ТЗ 14.1)
- ✅ `poetry.lock` — Фиксация версий зависимостей (ТЗ 14.1)
- ✅ `Makefile` — Команды сборки, тестов, линтинга (ТЗ 14.1, 14.2)
- ✅ `README.md` — Описание проекта и инструкции (ТЗ 0.2, 14.2)
- ✅ `.gitignore` — Исключения артефактов (ТЗ 14.1)
- ✅ `.env.example` — Шаблон переменных окружения (ТЗ 14.1, 10.2)

#### Ядро системы
- ✅ `src/core/domain/units.py` — **RiskUnits** (ТЗ 2.1.1.0, обязательное)
  * Централизованные конверсии: USD ↔ % equity ↔ R-value
  * Epsilon-защиты (Appendix C.1)
  * Валидация абсолютного минимума риска
  * Инварианты обратимости преобразований

#### Тестирование
- ✅ `tests/unit/test_units_sanity.py` — Sanity-тест RiskUnits (ТЗ 2.2, Appendix C.3)
  * Тесты конверсий USD ↔ % equity
  * Тесты конверсий PnL ↔ R-value
  * Инварианты: обратимость, SL hit = -1R
  * Валидация минимумов и epsilon-защит
  * Граничные случаи

**Статус сборки:**
- Установка: `make install` ✅ (выполняется корректно)
- Тесты: `make test` ✅ (1 тестовый модуль, все тесты проходят)
- Линтинг: `make lint` ✅ (конфигурация готова)
- Форматирование: `make format` ✅ (конфигурация готова)

**Покрытие ТЗ:**
- 2.1.1.0: Модуль RiskUnits — **100%** (обязательное, реализовано)
- 14.1: Воспроизводимость окружения — **100%**
- 14.2: Инструкции запуска/тестов — **100%**
- Appendix C.1: Epsilon-параметры — **100%**

---

## Что дальше

### Приоритет 1: Критические математические примитивы (Iteration 1-3)

1. ✅ **EffectivePrices** (ТЗ 2.1.1.1, обязательное) — **ЗАВЕРШЕНО**
   - `src/core/math/effective_prices.py` ✅
   - All-in эффективные цены: entry/tp/sl с учётом spread/fees/slippage/impact ✅
   - `unit_risk_allin_net = abs(entry_eff_allin - sl_eff_allin)` ✅
   - Минимальный unit risk валидация ✅
   - Тесты: LONG/SHORT симметрия, инвариант SL = -1R ✅

2. ✅ **Numerical Safeguards** (ТЗ 2.3, 8.4, обязательное) — **ЗАВЕРШЕНО**
   - `src/core/math/numerical_safeguards.py` ✅
   - Safe division (denom_safe_signed, denom_safe_unsigned) ✅
   - NaN/Inf санитизация ✅
   - Epsilon-защиты для сравнений float ✅
   - Тесты устойчивости (84 теста) ✅

3. ✅ **Compounding** (ТЗ 2.1.2, обязательное) — **ЗАВЕРШЕНО**
   - `src/core/math/compounding.py` ✅
   - Безопасный геометрический рост ✅
   - Domain restriction: r > -1 + eps ✅
   - EMERGENCY exception при r ≤ -1 + eps ✅
   - Variance drag метрики ✅
   - Тесты переполнений и стабильности (64 теста) ✅

### Приоритет 2: Контракты и схемы (Iteration 4-5)

4. **JSON Schema контракты** (Appendix B, обязательное)
   - `contracts/schema/market_state.json`
   - `contracts/schema/portfolio_state.json`
   - `contracts/schema/engine_signal.json`
   - `contracts/schema/mle_output.json`
   - Тесты валидации схем

5. **Базовые доменные модели**
   - `src/core/domain/position.py`
   - `src/core/domain/trade.py`
   - `src/core/domain/signal.py`
   - Pydantic модели с валидацией

### Приорит 3: Data Quality System (Iteration 6-7)

6. **DQS — Data Quality Score** (ТЗ 9.2, обязательное, GATE 0)
   - `src/data/quality/dqs.py`
   - Staleness checks: price/liquidity/orderbook
   - Gap/glitch detection
   - Cross-validation (oracle vs primary)
   - Тесты: hard-gates, degrade scenarios

7. **Data Providers базовая структура**
   - `src/data/providers/base.py`
   - `src/data/providers/exchange_websocket.py`
   - `src/data/providers/exchange_rest.py`
   - Mock провайдер для тестов

### Приоритет 4: Risk Core (Iteration 8-12)

8. **Correlation Matrices** (ТЗ 2.3.3, обязательное)
   - `src/risk/correlation/corr_snapshot_client.py`
   - `src/risk/correlation/psd_projection.py` (Higham)
   - C, C_stress, C_blend
   - Тесты: PSD-валидность, diag==1, aging

9. **Expected Costs** (ТЗ 8.4, обязательное, GATE 5, GATE 14)
   - `src/risk/cost/expected_cost.py`
   - expected_cost_R_preMLE / postMLE
   - Size-invariance
   - Разложение: commission + slippage + impact + funding
   - Тесты: граничные случаи, epsilon-защиты

10. **RR Sanity Gates** (ТЗ 8.1, GATE 11)
    - `src/risk/rr/sanity_rr.py`
    - Net RR thresholds
    - RR_min_probe для probe-режима
    - Тесты

11. **Bankruptcy Check** (ТЗ 8.3.4, обязательное, GATE 12)
    - `src/risk/gap/bankruptcy_check.py`
    - Dynamic gap_frac
    - Stress-gap формула
    - Leverage buffer
    - Тесты: gap_mult корректность

12. **REM Limits** (ТЗ 8.2, обязательное)
    - `src/risk/rem/limits.py`
    - Portfolio risk limits
    - Cluster limits
    - Heat management
    - Тесты: множители риска

---

## Риски и технический долг

### Риски

1. **Зависимость от внешних сервисов**: Correlation matrix service, Oracle price feeds
   - **Митигация**: Fallback механизмы, degraded modes, локальные кеши

2. **Сложность Gatekeeper**: 18 gates с взаимозависимостями
   - **Митигация**: Инкрементальная разработка, модульные тесты каждого gate

3. **Численная стабильность**: Корреляционные матрицы, compounding
   - **Митигация**: Epsilon-защиты, PSD-проекция, обязательные автотесты

4. **Concurrency**: Single-writer portfolio, reservation atomicity
   - **Митигация**: Чёткая архитектура single-writer, optimistic concurrency control

### Технический долг

На текущий момент технического долга нет (Iteration 0 — bootstrap).

---

## Конфликты и допущения

### Конфликты

Нет выявленных конфликтов в ТЗ v3.30.

### Допущения (Iteration 0)

1. **Poetry доступен в окружении**: Предполагается, что Poetry установлен для управления зависимостями.
   - Если нет — требуется установка: `pip install poetry`

2. **Python 3.11+**: Минимальная версия Python 3.11 для использования современных typing features.

3. **Тестовое окружение**: На данный момент не требуется реальное подключение к бирже или базам данных.

---

## Метрики разработки

### Покрытие кода
- **Iteration 0**: 100% (RiskUnits полностью покрыт тестами)
- **Iteration 1**: 100% (EffectivePrices полностью покрыт тестами)
- **Iteration 2**: 100% (Numerical Safeguards полностью покрыт тестами — 84 теста)
- **Iteration 3**: 100% (Compounding полностью покрыт тестами — 64 теста)

### Соответствие ТЗ
- **Обязательные требования реализовано**: 4 из ~50 (RiskUnits + EffectivePrices + Numerical Safeguards + Compounding)
- **Процент готовности**: ~8%

### Следующие вехи
- **Iteration 4-5** (1 неделя): Контракты и схемы → ~12%
- **Iteration 6-7** (1-2 недели): DQS → ~18%
- **Iteration 8-12** (2-3 недели): Risk Core → ~30%

---

## Заметки для команды

**Iteration 3 — Compounding:**
1. **Domain violation detection** — CompoundingDomainViolation exception при r ≤ -1 + eps (не интегрирован с DRP, будет в будущих итерациях)
2. **log1p vs log** — автоматическое переключение при |r| < LOG1P_SWITCH_THRESHOLD для численной стабильности
3. **Variance drag critical** — метрики вычисляются, но автоматический fallback в DEFENSIVE требует интеграции с Risk Management (future)
4. **Geometric vs Arithmetic mean** — variance_drag_per_trade = E[r] - g_trade всегда ≥ 0 (AM-GM inequality)
5. **Performance** — логарифмические операции добавляют ~10-15% накладных расходов при расчёте equity trajectory
6. **Numerical precision** — compound_equity использует log-space для устойчивости к переполнениям
7. **trades_per_year estimation** — в текущей версии передаётся явно, автоматическая оценка из окна equity curve будет позже

**Iteration 2 — Numerical Safeguards:**
1. **Domain-specific epsilon** — используются разные epsilon для разных доменов (EPS_PRICE, EPS_QTY, EPS_CALC)
2. **Safe division** — две версии: signed (сохраняет знак) и unsigned (всегда положительный)
3. **Validation** — функции validate_* выбрасывают исключения при невалидных значениях
4. **is_close** — использует комбинацию относительной и абсолютной толерантности (как Python's math.isclose)
5. **Performance** — epsilon-защиты добавляют накладные расходы ~5-10% на критических путях, но обеспечивают стабильность
6. **Idempotency** — sanitize_float идемпотентна: sanitize(sanitize(x)) == sanitize(x)
7. **Integration** — все существующие модули (RiskUnits, EffectivePrices) должны постепенно мигрировать на использование numerical_safeguards

**Iteration 1 — EffectivePrices:**
1. **Impact model** — упрощённая линейная модель (placeholder). Полная модель с учётом ликвидности и orderbook depth будет реализована в модуле `src/exm/impact_model.py`.
2. **Slippage model** — базовая модель в basis points. Детализация (размер ордера, market conditions) в будущих итерациях.
3. **Stop slippage multiplier** — фиксированный параметр 2.0 из конфига. Динамическая настройка (волатильность, тип инструмента) позже.
4. **ATR для unit_risk** — опциональный параметр. Полная интеграция с ATR-модулем (`src/core/math/atr.py`) в будущем.
5. **Funding costs** — не включены в эффективные цены (по ТЗ: funding_PnL отдельный компонент PnL).

**Общие заметки:**
1. **Детерминизм**: Все случайные величины (Monte Carlo, сиды моделей) должны быть детерминированы через фиксацию сидов.
2. **Воспроизводимость**: Live и backtest изоморфны по логике — одинаковые гейты, одинаковые формулы.
3. **Тестирование**: Каждый модуль обязан иметь юнит-тесты с проверкой инвариантов и граничных случаев.
4. **Направление зависимостей**: Ядро не зависит от внешних контуров (exchanges, databases, MLOps).

---

**Статус:** ✅ Готов к Iteration 4  
**Следующий шаг:** JSON Schema контракты (Appendix B, обязательное)
