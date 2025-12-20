# ATS-AI v3.30

**Algorithmic Trading System for Crypto Markets**  
_ML-driven, Risk-aware, Production-grade_

---

## Описание

ATS-AI — промышленная алгоритмическая торговая система для крипторынков с:

- **Формальной архитектурой стратегий** (TREND/RANGE)
- **ML-модулями**: MRC (Market Regime Classifier), MLE (Meta-Labeling Engine)
- **Полнофункциональным риск-менеджментом** (REM): портфельные лимиты, корреляции, tail-risk, beta-hedging
- **Модулем исполнения** (EXM) с учётом микроструктуры рынка
- **MLOps-контуром**: monitoring, drift detection, shadow mode, A/B testing
- **Disaster Recovery Protocol** (DRP) и режимами деградации

Система формально проверяема: все формулы, инварианты и критерии описаны в ТЗ и автотестах.

---

## Архитектура (кратко)

```
┌─────────────────────────────────────────────────────────────┐
│                   Стратегии (Engines)                        │
│  TREND Engine  │  RANGE Engine  │  Custom Strategies         │
└────────────┬────────────────────────────────────────────────┘
             │ Signals
             ▼
┌────────────────────────────────────────────────────────────┐
│                   ML Layer                                  │
│  MRC (Regime)  │  MLE (Meta-labeling)  │  ML Features      │
└────────────┬───────────────────────────────────────────────┘
             │ Filtered Signals + Risk Adjustments
             ▼
┌────────────────────────────────────────────────────────────┐
│                   Gatekeeper (18 Gates)                     │
│  DQS │ MRC │ MLE │ RR │ Cost │ Portfolio Limits │ Stress    │
└────────────┬───────────────────────────────────────────────┘
             │ Approved Signals
             ▼
┌────────────────────────────────────────────────────────────┐
│             Execution Module (EXM)                          │
│  Sizing │ Orderbook Analysis │ Impact │ Execution Plan      │
└────────────┬───────────────────────────────────────────────┘
             │ Orders
             ▼
┌────────────────────────────────────────────────────────────┐
│                   Exchange Adapters                         │
│  WebSocket │ REST │ Order Lifecycle │ Reconciliation        │
└────────────────────────────────────────────────────────────┘
```

Направление зависимостей: **ядро не зависит от внешних контуров**.

---

## Быстрый старт

### Требования
- Python 3.11+
- Poetry (dependency management)

### Установка

```bash
# Клонировать репозиторий
git clone <repo-url>
cd ats-ai

# Установить зависимости
make install
```

### Запуск тестов

```bash
# Все тесты
make test

# Только unit-тесты
make test-unit

# Линтинг и форматирование
make lint
make format

# Проверка типов
make type-check
```

### Режимы работы

**Backtest** (исторические данные):
```bash
poetry run python src/main_backtest.py --config configs/backtest.yaml
```

**Shadow Mode** (торговля без исполнения, для валидации):
```bash
poetry run python src/main_live.py --mode shadow --config configs/live.yaml
```

**Live** (реальная торговля):
```bash
poetry run python src/main_live.py --mode live --config configs/live.yaml
```

---

## Структура проекта

```
ats-ai/
├── src/
│   ├── core/           # Доменные модели, математика, инварианты
│   ├── data/           # Провайдеры данных, DQS, фичи
│   ├── mrc/            # Market Regime Classifier
│   ├── mle/            # Meta-Labeling Engine
│   ├── strategies/     # TREND/RANGE движки
│   ├── gatekeeper/     # Централизованный risk gate controller
│   ├── risk/           # REM, корреляции, tail-risk, банкротство
│   ├── exm/            # Execution Module
│   ├── portfolio/      # Управление состоянием портфеля
│   ├── drp/            # Disaster Recovery Protocol
│   ├── mlops/          # MLOps: мониторинг, калибровка, shadow mode
│   └── infra/          # Конфиги, логгирование, метрики
├── tests/
│   ├── unit/           # Юнит-тесты модулей
│   ├── integration/    # Интеграционные тесты пайплайнов
│   └── scenarios/      # Сценарные тесты (flash crash, depeg, etc.)
├── docs/               # Архитектура, формулы, runbooks
├── configs/            # YAML конфигурации
└── contracts/          # JSON Schema контрактов (Appendix B)
```

---

## Целевые показатели (Tier 1, net)

- **Годовая доходность**: 8–15% (нормальный режим), до 22–25% (stretch)
- **MaxDD**: 20–30% (нормальный), до 35% (стресс-тесты)
- **Sharpe Ratio**: 0.6–1.0+ (net)
- **Profit Factor**: ≥1.3 (типично 1.3–1.7)
- **Expectancy**: 0.18–0.30R (типично 0.20–0.25R)
- **Сделки/год**: 100–160 (допустимо 80–200)

Метрики рассчитываются **после** комиссий, проскальзывания, impact и funding.

---

## Статус проекта

См. [docs/STATE.md](docs/STATE.md) для актуального статуса разработки.

---

## Документация

- [Архитектурный обзор](docs/architecture/overview.md)
- [Контракты и интерфейсы](docs/contracts/appendix_b_interfaces.md)
- [Параметры и пороги](docs/params/appendix_c_params.md)
- [Операционные runbooks](docs/runbooks/operations.md)
- [DRP протоколы](docs/runbooks/drp.md)

---

## Лицензия

[Указать лицензию]

---

## Контакты

[Контакты команды]
