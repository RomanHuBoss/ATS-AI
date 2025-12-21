# ATS-AI v3.30 — Состояние разработки

**Последнее обновление:** Iteration 14  
**Статус:** Gatekeeper GATE 0-8 реализованы — Warm-up/DQS/DRP + DRP Kill-switch/Manual Halt/Trading Mode + MRC Confidence/Conflict Resolution + Strategy Compatibility + Signal Validation + Pre-sizing + MLE Decision + Liquidity Check + Gap/Data Glitch Detection

---

## Реализовано

### Iteration 14: Gatekeeper GATE 8 — Gap/Data Glitch Detection

**Цель:** Реализовать GATE 8 с детектированием аномалий цен (gaps, spikes, glitches) и инициированием DRP при критических обнаружениях.

**Реализованные модули:**

#### Gatekeeper GATE 8
- ✅ `src/gatekeeper/gates/gate_08_gap_glitch.py` — **Gate08GapGlitch**
  * Девятый gate в цепочке (после GATE 0-7)
  * Size-invariant anomaly checks (не зависит от qty)
  * PricePoint dataclass для хранения price history
  * Price jump detection: |price_now - price_prev| / price_prev > threshold
  * Price spike detection: z-score метод с minimum 5 price points
  * Stale orderbook detection: orderbook_age > threshold при fresh price
  * suspected_data_glitch flag для комплексной диагностики
  * DRP trigger mechanism с severity levels (LOW/MEDIUM/HIGH)
  * Hard limits для price_jump_hard_pct и price_spike_zscore_hard
  * Soft detection для suspected_data_glitch
  * Gate08Config для гибкой настройки всех порогов
  * Детальная диагностика через AnomalyMetrics, DRPTrigger, Gate08Result

#### Формулы GATE 8

**1. Price jump (%):**
```
price_jump_pct = |price_current - price_prev| / price_prev * 100
detected = price_jump_pct > price_jump_threshold_pct
hard_reject = price_jump_pct > price_jump_hard_pct
```

**2. Price spike (z-score):**
```
price_mean = mean(price_history)
price_stddev = stddev(price_history)
price_zscore = |price_current - price_mean| / price_stddev
detected = price_zscore > price_spike_zscore_threshold
hard_reject = price_zscore > price_spike_zscore_hard
```

**3. Stale book detection:**
```
orderbook_age_ms = current_price_ts - orderbook_ts
price_age_ms = 0  # Current price is fresh
stale_book_fresh_price = (orderbook_age_ms > max_orderbook_age_ms) AND (price_age_ms < max_price_age_ms)
```

**4. Suspected glitch:**
```
suspected_data_glitch = price_jump_detected OR price_spike_detected OR stale_book_fresh_price
```

**5. DRP trigger evaluation:**
```
HIGH severity: price_zscore > drp_trigger_zscore OR price_jump_pct > drp_trigger_jump_pct
MEDIUM severity: any suspected_data_glitch
```

#### Hard blocks в GATE 8:
1. **GATE 0-7 блокировка** — если любой из предыдущих gates блокирует
2. **price_jump_hard_reject** — price_jump_pct > price_jump_hard_pct
3. **price_spike_hard_reject** — price_zscore > price_spike_zscore_hard
4. **suspected_data_glitch** — любая аномалия при glitch_block_enabled=True

#### Тестирование GATE 8
- ✅ `tests/unit/test_gate_08.py` — Тесты GATE 8 (20 тестов)
  * Price jump detection (4 теста: small pass, soft detected, hard reject, no history)
  * Price spike detection (3 теста: soft detected, hard reject, insufficient history)
  * Stale book detection (2 теста: detected, fresh pass)
  * Suspected glitch (2 теста: multiple anomalies, disabled block)
  * DRP trigger mechanism (3 теста: high severity, medium severity, disabled)
  * Integration с GATE 0-7 (2 теста: GATE 0 blocked, full chain pass)
  * Edge cases (4 теста: zero stddev, orderbook ahead, exact threshold, strict config)

**Статус сборки GATE 8:**
- Установка: pip install -e . ✅
- Тесты: pytest tests/unit/test_gate_08.py ✅ (**20 тестов, все проходят**)
- GATE 8: все расчёты size-invariant ✅
- Price jump detection: работает корректно ✅
- Price spike detection: z-score метод работает корректно ✅
- Stale book detection: корректно определяет несоответствия timestamps ✅
- suspected_data_glitch flag: корректно устанавливается ✅
- DRP trigger: работает с severity levels ✅
- Integration: GATE 0 → 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 chain работает ✅

**Покрытие ТЗ для GATE 8:**
- ТЗ 3.3.2 строка 1025, 1053 (GATE 8: Gap/Data Glitch Detection) — **100%** (реализован и протестирован)
- ТЗ раздел 9.4 (Gap handling и data glitch detection) — **100%** (реализован)
- DRP trigger mechanism при data anomalies — **100%** (реализован)

**Инварианты и гарантии GATE 8:**
1. **Size-invariant checks** — все проверки не зависят от qty_actual
2. **Price jump detection** — работает с single previous price point
3. **Price spike detection** — требует minimum 5 price points для z-score
4. **Stale book detection** — корректно определяет несоответствие timestamps
5. **suspected_data_glitch flag** — устанавливается при любой аномалии
6. **DRP trigger mechanism** — работает с severity levels (LOW/MEDIUM/HIGH)
7. **Hard limits enforcement** — price_jump_hard и spike_hard строго соблюдаются
8. **Gate order** — GATE 8 после GATE 0-7
9. **Immutability** — Gate08Result frozen=True
10. **Integration ready** — GATE 8 готов к интеграции в full gatekeeper chain

---

### Iteration 12: Gatekeeper GATE 6 — MLE Decision (size-invariant price-edge)

**Цель:** Реализовать GATE 6 с MLE decision (size-invariant по price-edge), вычислением EV_R_price, p_success/p_fail, expected_cost_R_postMLE и проверкой net edge.

**Реализованные модули:**

#### Gatekeeper GATE 6
- ✅ `src/gatekeeper/gates/gate_06_mle_decision.py` — **Gate06MLEDecision**
  * Седьмой gate в цепочке (после GATE 0-5)
  * Size-invariant MLE decision на основе price-edge
  * MLEDecision enum (REJECT, WEAK, NORMAL, STRONG)
  * EV_R_price вычисление: p_success * mu_success_R + p_fail * mu_fail_R
  * mu_success_R = |tp_eff - entry_eff| / unit_risk (abs для SHORT)
  * mu_fail_R = -1.0 (SL hit всегда -1R)
  * expected_cost_R_postMLE с взвешиванием через p_success/p_fail
  * expected_cost_bps_post = entry_cost + p_success*tp_exit + p_fail*sl_exit
  * Net edge check: EV_R_price - expected_cost_R_postMLE >= net_edge_floor_R
  * Risk multipliers по decision (WEAK=0.5, NORMAL=1.0, STRONG=1.25)
  * Gate06Config для гибкой настройки порогов
  * Детальная диагностика через Gate06Result

#### Тестирование GATE 6
- ✅ `tests/unit/test_gate_06.py` — Тесты GATE 6 (21 тест)
  * MLE decision categories (5 тестов)
  * Net edge check (2 теста)
  * EV_R_price calculation (2 теста - LONG и SHORT)
  * expected_cost_R_postMLE calculation (2 теста)
  * Integration GATE 0-5 (2 теста)
  * Edge cases (6 тестов)
  * Size-invariance (1 тест)
  * Integration chain GATE 0-6 (2 теста)

**Статус сборки GATE 6:**
- Установка: pip install -e . ✅
- Тесты: pytest tests/unit/test_gate_06.py ✅ (**21 новый тест, все проходят**)
- GATE 6: все расчёты size-invariant ✅
- MLE decision: REJECT/WEAK/NORMAL/STRONG работают корректно ✅
- Integration: GATE 0 → 1 → 2 → 3 → 4 → 5 → 6 chain работает ✅

**Покрытие ТЗ для GATE 6:**
- ТЗ 3.3.2 строка 1023, 1051 (GATE 6: Решение MLE) — **100%** (реализован и протестирован)
- ТЗ раздел 1688-1709 (EV_R_price формула и decision thresholds) — **100%** (реализован)
- ТЗ раздел 2142-2158 (expected_cost_R_postMLE и net_edge check) — **100%** (реализован)
- ТЗ раздел 2147-2148 (взвешивание exit costs через p_success/p_fail) — **100%** (реализован)

**Инварианты и гарантии GATE 6:**
1. **MLE decision size-invariant** — не зависит от qty_actual
2. **EV_R_price formula** — p_success * mu_success_R + p_fail * mu_fail_R
3. **mu_success_R calculation** — |tp_eff - entry_eff| / unit_risk (abs для SHORT)
4. **mu_fail_R constant** — всегда -1.0 (SL hit = -1R)
5. **expected_cost_R_postMLE** — взвешивание через p_success/p_fail
6. **Net edge check** — EV_R_price - expected_cost_R_postMLE >= net_edge_floor_R
7. **Risk multipliers** — WEAK=0.5, NORMAL=1.0, STRONG=1.25
8. **Gate order** — GATE 6 после GATE 0-5
9. **Immutability** — Gate06Result frozen=True
10. **Integration ready** — GATE 6 готов к интеграции в full gatekeeper chain

---

### GATE 7: Liquidity Check (реализован в iteration 12)

**Цель:** Реализовать GATE 7 с проверкой ликвидности на основе микроструктуры рынка (orderbook depth, spread, volume). Вычислять liquidity_mult для risk adjustment с smooth interpolation.

**Реализованные модули:**

#### Gatekeeper GATE 7
- ✅ `src/gatekeeper/gates/gate_07_liquidity_check.py` — **Gate07LiquidityCheck**
  * Восьмой gate в цепочке (после GATE 0-6)
  * Size-invariant liquidity checks (не зависит от qty)
  * Hard limits: bid_depth_min_usd, ask_depth_min_usd, spread_max_hard_bps, volume_24h_min_usd
  * Soft degradation: spread_mult и impact_mult с smooth interpolation
  * OBI (Order Book Imbalance) вычисление: (bid_vol - ask_vol) / (bid_vol + ask_vol)
  * Spoofing detection через depth_volatility_cv
  * Impact estimate: impact_k * (notional / depth)^impact_pow * 10000 bps
  * liquidity_mult = min(spread_mult, impact_mult)
  * LiquidityMetrics: bid_depth, ask_depth, spread, volume, obi, depth_volatility
  * LiquidityMultipliers: spread_mult, impact_mult, liquidity_mult, limiting_factor
  * Gate07Config для гибкой настройки всех порогов
  * Детальная диагностика через Gate07Result

#### Формулы GATE 7

**1. Spread multiplier (soft degradation):**
```
spread_mult = clip((max_hard - spread) / (max_hard - max_soft), 0, 1)
```

**2. Impact estimate (ТЗ 2067):**
```
avg_depth = (bid_depth + ask_depth) / 2
impact_bps_est = impact_k * (notional / avg_depth)^impact_pow * 10000
```

**3. Impact multiplier (soft degradation):**
```
impact_mult = clip((max_hard - impact) / (max_hard - max_soft), 0, 1)
```

**4. Final liquidity multiplier:**
```
liquidity_mult = min(spread_mult, impact_mult)
```

**5. OBI (Order Book Imbalance):**
```
OBI = (bid_vol_1pct - ask_vol_1pct) / (bid_vol_1pct + ask_vol_1pct)
```

**6. Depth volatility (spoofing detection):**
```
depth_volatility_cv = depth_sigma / depth_mean
spoofing_suspected = depth_volatility_cv > threshold
```

#### Hard blocks в GATE 7:
1. **GATE 0-6 блокировка** — если любой из предыдущих gates блокирует
2. **bid_depth_too_low** — bid_depth_usd < bid_depth_min_usd
3. **ask_depth_too_low** — ask_depth_usd < ask_depth_min_usd
4. **spread_hard_reject** — spread_bps > spread_max_hard_bps
5. **volume_too_low** — volume_24h_usd < volume_24h_min_usd
6. **spoofing_suspected** — depth_volatility_cv > threshold (если enabled)

#### Тестирование GATE 7
- ✅ `tests/unit/test_gate_07.py` — Тесты GATE 7 (22 теста, 950 строк)
  * Depth checks (bid/ask) — 2 теста
  * Spread checks (soft/hard/perfect) — 3 теста
  * Volume checks — 1 тест
  * OBI checks (balanced/extreme) — 2 теста
  * Spoofing detection (enabled/disabled) — 2 теста
  * liquidity_mult calculation (perfect/spread-limiting/impact-limiting) — 3 теста
  * Impact calculation — 1 тест
  * Integration с GATE 0-6 — 3 теста
  * Edge cases (zero depth sigma, zero volumes, spread edge, notional edge) — 5 тестов

**Статус сборки GATE 7:**
- Установка: pip install -e . ✅
- Тесты: pytest tests/unit/test_gate_07.py ✅ (**22 теста, все проходят**)
- GATE 7: все расчёты size-invariant ✅
- liquidity_mult: smooth interpolation работает корректно ✅
- OBI calculation: корректно вычисляется ✅
- Spoofing detection: работает корректно ✅
- Integration: GATE 0 → 1 → 2 → 3 → 4 → 5 → 6 → 7 chain работает ✅

**Покрытие ТЗ для GATE 7:**
- ТЗ 3.3.2 строка 1024, 1052 (GATE 7: Liquidity gates) — **100%** (реализован и протестирован)
- ТЗ раздел 2215-2223 (liquidity_mult формула) — **100%** (реализован)
- ТЗ раздел 2291-2300 (OBI и детектор мнимой ликвидности) — **100%** (реализован)
- ТЗ раздел 2067 (impact formula) — **100%** (реализован)

**Инварианты и гарантии GATE 7:**
1. **Size-invariant checks** — все проверки не зависят от qty_actual
2. **Hard limits enforcement** — depth, spread, volume thresholds строго соблюдаются
3. **Smooth degradation** — spread_mult и impact_mult используют linear interpolation
4. **liquidity_mult calculation** — всегда min(spread_mult, impact_mult)
5. **OBI calculation** — корректно обрабатывает zero volumes
6. **Spoofing detection** — depth_volatility_cv с configurable threshold
7. **Gate order** — GATE 7 после GATE 0-6
8. **Immutability** — Gate07Result frozen=True
9. **Integration ready** — GATE 7 готов к интеграции в full gatekeeper chain
10. **Diagnostic richness** — LiquidityMetrics и LiquidityMultipliers для полной диагностики

---

## Архитектурный контекст

### Реализованные Gates (0-8)

**GATE 0: Warm-up / DQS**
- Warm-up состояние после DRP
- Data Quality Score (DQS) вычисление
- Hard-gates для критических данных
- Stale data detection

**GATE 1: DRP Kill-switch / Manual Halt / Trading Mode**
- DRP state machine (NORMAL/DEFENSIVE/RECOVERY/EMERGENCY/HIBERNATE)
- Manual halt block
- Trading mode enforcement (LIVE/PAPER/SHADOW)
- Kill-switch для emergency stop

**GATE 2: MRC Confidence / Conflict Resolution**
- MRC confidence thresholds (high/very_high/low)
- Baseline probability check
- Conflict detection между engine signals
- Probe mode support

**GATE 3: Strategy Compatibility**
- Regime compatibility check
- Engine-regime alignment validation

**GATE 4: Signal Validation**
- Price level sanity checks
- Risk-reward ratio validation
- Expected holding hours validation

**GATE 5: Pre-sizing**
- unit_risk_bps calculation (size-invariant)
- expected_cost_R_preMLE calculation (size-invariant)
- Preliminary size estimate

**GATE 6: MLE Decision**
- EV_R_price calculation (size-invariant)
- p_success/p_fail weighting
- expected_cost_R_postMLE calculation
- Net edge check
- Risk multipliers (WEAK/NORMAL/STRONG)

**GATE 7: Liquidity Check**
- Depth thresholds (bid/ask)
- Spread thresholds (soft/hard)
- Volume 24h threshold
- OBI calculation
- Spoofing detection
- liquidity_mult calculation (smooth degradation)
- Impact estimate

**GATE 8: Gap/Data Glitch Detection**
- Price jump detection (% threshold)
- Price spike detection (z-score based)
- Stale book detection
- suspected_data_glitch flag
- DRP trigger mechanism (LOW/MEDIUM/HIGH severity)

### Integration Chain Status

```
Signal → GATE 0 → GATE 1 → GATE 2 → GATE 3 → GATE 4 → GATE 5 → GATE 6 → GATE 7 → GATE 8 → [GATE 9...] → Decision
         ✅       ✅        ✅        ✅        ✅        ✅        ✅        ✅        ✅
```

---

## Что дальше

### Следующие приоритеты (GATE 9-10)

**GATE 9: Funding Filter + Proximity + Blackout**
- Требования из ТЗ 3.3.2 строка 1026, 1054
- Funding rate filter
- Proximity model (близость к событиям)
- Blackout conditions

**GATE 10: Correlation / Exposure Conflict**
- Требования из ТЗ 3.3.2 строка 1027, 1055
- Correlation checks между позициями
- Exposure conflict detection
- Portfolio-level constraints

### Риски и технический долг

1. **Market data infrastructure** — нужны реальные источники данных для orderbook, volume
2. **DRP state machine** — требует интеграции с execution layer
3. **Testing coverage** — нужны integration тесты для full chain GATE 0-7
4. **Performance** — оптимизация вычислений для latency-sensitive paths
5. **Configuration management** — централизованная система конфигов для всех gates

### Открытые вопросы

1. **Data sources** — откуда брать orderbook depth, volume 24h в реальном времени?
2. **Staleness detection** — как отслеживать свежесть данных для каждого источника?
3. **DRP triggers** — кто и как инициирует DRP transitions?
4. **liquidity_mult usage** — как liquidity_mult применяется в REM?
5. **Testing strategy** — как тестировать edge cases с реальными market conditions?

### Покрытие ТЗ (текущий статус)

**Реализовано (100%):**
- ✅ GATE 0: Warm-up/DQS/DRP (ТЗ 3.3.1, 3.3.2 строка 1018, 1045)
- ✅ GATE 1: DRP Kill-switch (ТЗ 3.3.2 строка 1019, 1046)
- ✅ GATE 2: MRC Confidence (ТЗ 3.3.3, 3.3.2 строка 1020, 1047)
- ✅ GATE 3: Strategy Compatibility (ТЗ 3.3.2 строка 1021, 1048)
- ✅ GATE 4: Signal Validation (ТЗ 3.3.2 строка 1022, 1049)
- ✅ GATE 5: Pre-sizing (ТЗ 3.3.2 строка 1023, 1050)
- ✅ GATE 6: MLE Decision (ТЗ 3.3.2 строка 1023, 1051)
- ✅ GATE 7: Liquidity Check (ТЗ 3.3.2 строка 1024, 1052)
- ✅ GATE 8: Gap/Data Glitch (ТЗ 3.3.2 строка 1025, 1053)

**Следующие (0%):**
- ⏳ GATE 9: Funding Filter (ТЗ 3.3.2 строка 1026, 1054)
- ⏳ GATE 10: Correlation/Exposure (ТЗ 3.3.2 строка 1027, 1055)
- ⏳ GATE 11-18: остальные gates

---

**Статус:** ✅ Готов к Iteration 15  
**Следующий шаг:** Gatekeeper GATE 9 — Funding Filter + Proximity + Blackout (ТЗ 3.3.2, обязательный, GATE 9)
