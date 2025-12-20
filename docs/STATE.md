# ATS-AI v3.30 — Состояние разработки

**Последнее обновление:** Iteration 0  
**Статус:** Bootstrap завершён

---

## Реализовано

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

1. **EffectivePrices** (ТЗ 2.1.1.1, обязательное)
   - `src/core/math/effective_prices.py`
   - All-in эффективные цены: entry/tp/sl с учётом spread/fees/slippage/impact
   - `unit_risk_allin_net = abs(entry_eff_allin - sl_eff_allin)`
   - Минимальный unit risk валидация
   - Тесты: LONG/SHORT симметрия, инвариант SL = -1R

2. **Numerical Safeguards** (ТЗ 2.3, 8.4)
   - `src/core/math/numerical_safeguards.py`
   - Safe division (denom_safe_signed, denom_safe_unsigned)
   - NaN/Inf санитизация
   - Epsilon-защиты для сравнений float
   - Тесты устойчивости

3. **Compounding** (ТЗ 2.3.2)
   - `src/core/math/compounding.py`
   - Безопасный геометрический рост
   - Domain restriction: r > -1 + eps
   - EMERGENCY переход при r < -1
   - Тесты переполнений и стабильности

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

### Соответствие ТЗ
- **Обязательные требования реализовано**: 1 из ~50 (RiskUnits)
- **Процент готовности**: ~2%

### Следующие вехи
- **Iteration 1-3** (1-2 недели): Математические примитивы → ~8%
- **Iteration 4-5** (1 неделя): Контракты и схемы → ~12%
- **Iteration 6-7** (1-2 недели): DQS → ~18%
- **Iteration 8-12** (2-3 недели): Risk Core → ~30%

---

## Заметки для команды

1. **Детерминизм**: Все случайные величины (Monte Carlo, сиды моделей) должны быть детерминированы через фиксацию сидов.
2. **Воспроизводимость**: Live и backtest изоморфны по логике — одинаковые гейты, одинаковые формулы.
3. **Тестирование**: Каждый модуль обязан иметь юнит-тесты с проверкой инвариантов и граничных случаев.
4. **Направление зависимостей**: Ядро не зависит от внешних контуров (exchanges, databases, MLOps).

---

**Статус:** ✅ Готов к Iteration 1  
**Следующий шаг:** Реализация EffectivePrices (ТЗ 2.1.1.1, обязательное)
