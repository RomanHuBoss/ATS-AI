# ATS-AI v3.30 — Состояние разработки

**Последнее обновление:** Iteration 12  
**Статус:** Gatekeeper GATE 0-6 — Warm-up/DQS/DRP + DRP Kill-switch/Manual Halt/Trading Mode + MRC Confidence/Conflict Resolution + Strategy Compatibility + Signal Validation + Pre-sizing + MLE Decision реализованы

---

## Реализовано

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

#### Тестирование
- ✅ `tests/unit/test_gate_06.py` — Тесты GATE 6 (21 тест)
  * MLE decision categories (5 тестов)
  * Net edge check (2 теста)
  * EV_R_price calculation (2 теста - LONG и SHORT)
  * expected_cost_R_postMLE calculation (2 теста)
  * Integration GATE 0-5 (2 теста)
  * Edge cases (6 тестов)
  * Size-invariance (1 тест)
  * Integration chain GATE 0-6 (2 теста)

**Статус сборки:**
- Установка: pip install -e . ✅
- Тесты: pytest tests/unit/test_gate_06.py ✅ (**21 новый тест, все проходят**)
- GATE 6: все расчёты size-invariant ✅
- MLE decision: REJECT/WEAK/NORMAL/STRONG работают корректно ✅
- Integration: GATE 0 → 1 → 2 → 3 → 4 → 5 → 6 chain работает ✅

**Покрытие ТЗ:**
- ТЗ 3.3.2 строка 1023, 1051 (GATE 6: Решение MLE) — **100%** (реализован и протестирован)
- ТЗ раздел 1688-1709 (EV_R_price формула и decision thresholds) — **100%** (реализован)
- ТЗ раздел 2142-2158 (expected_cost_R_postMLE и net_edge check) — **100%** (реализован)
- ТЗ раздел 2147-2148 (взвешивание exit costs через p_success/p_fail) — **100%** (реализован)

**Инварианты и гарантии:**
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

**Статус:** ✅ Готов к Iteration 13  
**Следующий шаг:** Gatekeeper GATE 7-9 — Liquidity gates (H1 + стакан) + Gap/data glitch + Funding фильтр (ТЗ 3.3.2, обязательные, GATE 7-9)
