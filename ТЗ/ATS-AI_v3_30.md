# ТЕХНИЧЕСКОЕ ЗАДАНИЕ — ATS-AI v3.30
## Алгоритмическая торговая система для крипторынков с ML, Risk Overlay, MLOps и учётом микроструктуры
---


> **v3.30:** исправлены логические, математические и экономические ошибки, устранены несогласованности.
> Унифицирована терминология (all-in, post-MLE, pre-MLE), улучшены пояснения к формулам.
> Скорректированы target_return_annual_by_tier для согласованности с целевыми диапазонами доходности.
> Добавлены комментарии к критическим формулам (basis_risk_mult, gap_frac, variance_drag).
> Сохранены все исправления v3.28 и v3.29. Документ самодостаточен и готов к реализации.



## 1. ЦЕЛЬ СИСТЕМЫ
Создать промышленную алгоритмическую торговую систему для крипторынков, обладающую:

* формально описанной архитектурой стратегий (**TREND** / **RANGE**);
* ML-модулями:

  * **MRC** — классификатор рыночных режимов,
  * **MLE** — meta-labeling / ML-фильтр для допуска сигналов, оценки price-edge и модификации риска;
* полнофункциональным риск-менеджментом и управлением капиталом;
* учётом корреляций, beta-риска, tail-risk и tail-dependence (включая стресс-сценарии);
* модулем исполнения (**EXM**) с учётом ликвидности и микроструктуры (orderbook/объём/impact);
* MLOps-контуром (monitoring, drift detection, калибровка, A/B-тесты, shadow-mode, rollback);
* disaster recovery протоколами (**DRP**) и режимами деградации;
* использованием данных микроструктуры и деривативов (funding, OI, basis, orderbook, time-to-funding, ADL queue);
* формальной проверяемостью (формулы, инварианты, автотесты), включая численные стандарты устойчивости вычислений (epsilon-защиты, правила сравнения float, PSD-проекция матриц).

Документ определяет архитектуру, интерфейсы модулей и формальные критерии, достаточные для реализации, включая:

* спецификацию режимов работы;
* требования к данным, фичам и обучению моделей;
* формальные критерии допуска к live-режимам;
* принципы настройки и калибровки порогов и лимитов;
* требования к тестируемости (проверяемость формулами, инвариантами и автотестами);
* правила детерминизма и воспроизводимости (live/backtest изоморфны по логике).

---

## 2. ЦЕЛЕВЫЕ ПОКАЗАТЕЛИ И РЫНОК

### 2.1. Целевые показатели
Метрики задаются как инженерные ориентиры проектирования стратегий и риск-контуров. Реалистичность целей подтверждается backtest, walk-forward оптимизацией и Monte Carlo симуляциями equity-curve с учётом компаундинга, variance drag и path-dependency.

Целевые диапазоны для Tier 1 (капитал ~$10k–$50k, **net** — после комиссий, проскальзывания/impact и funding):

* Годовая доходность (net), нормальный режим: **8–15%**.
* Расширенный диапазон (агрессивнее/больше инструментов), нормальный режим: **15–22%**.
* Верхний «stretch»-сценарий: **до 22–25%** при одновременно выполненных условиях:

  * достаточная частота (типично **120–180 сделок/год** по портфелю),
  * положительный геометрический рост по Monte Carlo в OOS,
  * допустимый рост риска и/или улучшение Expectancy по факту,
  * выполнение всех ограничений MaxDD/лимитов REM.
* Максимальная просадка по счёту (MaxDD, net), нормальный режим: **20–30%**.
* Максимальная просадка (стресс-тесты): допускается **до 35%** как тестовый сценарий отказоустойчивости.
* Sharpe Ratio (net): **0.6–1.0**; **1.0+** — успешный сценарий.
* Calmar Ratio:

  * нормальный режим: **0.5–1.0**,
  * стресс-сценарии: **0.3+**.
* Profit Factor (портфельный, money, net): **≥ 1.3**; типичный рабочий диапазон **1.3–1.7**.
* Expectancy (net) в R-единицах (risk-weighted): **0.18–0.30R** (типичный рабочий диапазон **0.20–0.25R**).
* Количество сделок по портфелю: **100–160/год**, допустимо **80–200/год**.

Интерпретация через риск-бюджет:

* Средний реализованный риск на сделку после DD-ladder, MLE, funding/basis/корреляционных и портфельных лимитов: **0.35–0.60% equity**.
* При Expectancy ~0.20–0.25R и риске 0.45–0.55% ожидаемый вклад одной сделки в equity: **~0.09–0.14%**.
* Центральный сценарий калибровки:

  * риск/сделка: ~0.50%,
  * Expectancy: ~0.22–0.24R,
  * 120–150 сделок/год.

#### 2.1.1. Метрики PF / WR / Avg_Win / Avg_Loss / Expectancy: согласованность, единицы измерения и автотестируемые тождества

#### 2.1.1.0. Единицы риска и централизованный модуль RiskUnits (обязательное)
**Единственный допустимый способ преобразований — через централизованный модуль `RiskUnits` (обязательное).** Любая конверсия риска (включая перевод funding/cost/impact в R) обязана проходить через этот модуль. Во всех модулях запрещено смешивать риск в разных единицах без явного конвертера.

Определяются три базовые величины:

* `risk_amount_usd` — денежный риск сделки (USD).
* `risk_pct_equity` — риск в доле equity (безразмерная).
* `R_value` — нормированная величина PnL в единицах R (безразмерная), где 1R соответствует `risk_amount_usd`.

**Обязательные конвертеры (единственный допустимый способ):**

```text
equity_eff      = max(equity_before_usd, pnl_eps_usd)
risk_pct_equity = risk_amount_usd / equity_eff
risk_amount_usd = risk_pct_equity * equity_eff
R_value         = PnL_usd / denom_safe_signed(risk_amount_usd, risk_amount_eps_usd)
```

Все eps и минимумы определены в Приложении C.

**Абсолютный минимум риска сделки (обязательное).**

```text
if risk_amount_usd < risk_amount_min_absolute_usd:
    reject

```

→ сделка отклоняется с причиной `risk_amount_below_minimum_block`.

---

#### 2.1.1.1. Единая “истина” риска в net-метриках: all-in EffectivePrices и unit_risk_allin_net
**Принцип (обязательное).** Для нормализации KPI, расчёта `R_total_net`, `R_price_net`, `unit_risk_*` и проверки инварианта “SL даёт −1R” используется единый модуль EffectivePrices. Вся стоимость исполнения (spread/fees/slippage/impact/stop_slippage) обязана быть отражена в эффективных ценах.

**Определения (обязательное).** Для каждой сделки i:

* `entry_eff_allin_i`, `tp_eff_allin_i`, `sl_eff_allin_i` — эффективные цены (all-in, net) по правилам Приложения A.2.
* `unit_risk_allin_net_i = abs(entry_eff_allin_i - sl_eff_allin_i)`
* `risk_amount_i = qty_i * unit_risk_allin_net_i`

**Минимальный all-in unit risk (обязательное).** Если `unit_risk_allin_net < unit_risk_min_abs` или `unit_risk_allin_net < unit_risk_min_atr_mult * ATR` — вход запрещён (`unit_risk_too_small_block`).

---

#### 2.1.1.2. Компоненты PnL и две net-конструкции
**Компоненты PnL (обязательные соглашения):**

* `price_PnL_i` — signed PnL от движения цены (mark-to-market, включая закрытие).
* `funding_PnL_i` — signed funding PnL (по конвенции 3.3.4.1).
* `commissions_PnL_i ≤ 0`.
* `slippage_PnL_i ≤ 0`.
* `impact_PnL_i ≤ 0` (если impact учитывается отдельно; иначе он включён в slippage).

**Две net-конструкции (обязательные):**

* **Total net** (KPI/отчётность и фактическая доходность):

  * `PnL_total_net_i = price_PnL_i + funding_PnL_i + commissions_PnL_i + slippage_PnL_i + impact_PnL_i`
  * `R_total_net_i = PnL_total_net_i / denom_safe_signed(risk_amount_i, risk_amount_eps_usd)`
* **Price net** (для ML-оценки price-edge в MLE):

  * `PnL_price_net_i = price_PnL_i + commissions_PnL_i + slippage_PnL_i + impact_PnL_i`
  * `R_price_net_i = PnL_price_net_i / denom_safe_signed(risk_amount_i, risk_amount_eps_usd)`

---

#### 2.1.1.3. WR/Avg_* и PF на money/R уровнях (обязательные)
**WR/Avg_* (для total net, обязательные).**

* `WR` — доля прибыльных сделок по `PnL_total_net`.
* `Avg_Win` — средний выигрыш (в R) по прибыльным сделкам по `R_total_net`.
* `Avg_Loss` — средний проигрыш (в R, положительное число) по убыточным сделкам по `R_total_net`.

**Два уровня портфельных PF (обязательные).**

1. Money-уровень (KPI):

```text
PF_money = sum(PnL_total_net_i | PnL_total_net_i > 0) / abs(sum(PnL_total_net_i | PnL_total_net_i < 0))
```

2. R-уровень (диагностический):

```text
PF_R_total = sum(R_total_net_i | R_total_net_i > 0) / abs(sum(R_total_net_i | R_total_net_i < 0))
```

**Risk-weighted метрики (обязательные).** Базовый вес `w_i = risk_amount_i`.

**Фактический вес по исполнению (обязательное).** Если сделка была исполнена частично или в несколько fills, вес и риск обязаны рассчитываться по фактическому объёму и фактической средневзвешенной цене входа:

```text
risk_amount_i_actual = abs(entry_eff_allin_avg_fill_i - sl_eff_allin_i) * qty_filled_i
w_i := risk_amount_i_actual
```

**Floor-правило для статистики (обязательное).** Для расчёта KPI, которые далее используются для Kelly/допуска/автопринятия решений, вводится фильтр “микро-риска”:

* `risk_pct_equity_i_actual = risk_amount_i_actual / max(equity_before_i, pnl_eps_usd)`

Если `risk_pct_equity_i_actual < risk_pct_equity_stats_floor` или `risk_amount_i_actual < risk_amount_stats_floor_usd`, то:

* сделка не включается в вычисление `WR_w`, `Avg_Win_w`, `Avg_Loss_w`, `Expectancy_R_w`, `Kelly` и всех производных допусков;
* сделка включается в PnL и equity-таймсерию;
* факт исключения логируется (`kpi_trade_excluded_low_risk_event`) с полями `risk_pct_equity_i_actual`, `risk_amount_i_actual`, `reason`.

**Risk-weighted WR и Avg_* (обязательные).**

```text
WR_w = sum(w_i * I[R_total_net_i>0]) / sum(w_i)

Avg_Win_w  = sum(w_i * R_total_net_i | R_total_net_i>0) / sum(w_i | R_total_net_i>0)
Avg_Loss_w = abs(sum(w_i * R_total_net_i | R_total_net_i<0) / sum(w_i | R_total_net_i<0))
```

**Идентичность money-PF (обязательная, автотест).**

```text
PF_money_identity = (WR_w × Avg_Win_w) / ((1 − WR_w) × Avg_Loss_w)
```

**Гарды на крайних случаях (обязательное).**

* если `WR_w >= wr_w_invalid_high_threshold` или `WR_w <= wr_w_invalid_low_threshold`, то:

  * `PF_money_identity` помечается статусом `INVALID_EDGE_CASE`,
  * логируется событие `kpi_pf_identity_invalid_edge_case_event`,
  * `PF_money_identity` запрещается использовать для допуска/автопринятия решений.
* если `Avg_Loss_w <= avg_loss_w_floor` или `sum(w_i | R_total_net_i<0) == 0`, то:

  * статус `INVALID_EDGE_CASE` аналогично.

**PF-гомогенность (обязательное, диагностическое).** Вычисляется коэффициент вариации фактического риска:

```text
cv_risk = std(risk_amount_i_actual) / max(mean(risk_amount_i_actual), cv_eps)
```

Если `cv_risk > pf_identity_cv_threshold`, то:

* `PF_money_identity` получает статус `HIGH_VARIANCE_WARNING` (интерпретировать `WR_w/Avg_*` осторожно),
* автотест равенства `PF_money ≈ PF_money_identity` остаётся обязательным (расхождение — баг расчёта/фильтров),
* логируется `kpi_pf_identity_high_variance_warning_event` с `cv_risk` и параметрами порога.

**Требование совпадения PF (обязательное при VALID).** При статусе `VALID` и при `cv_risk <= pf_identity_cv_threshold` метрики `PF_money` и `PF_money_identity` обязаны совпадать в пределах допусков (Приложение C) на одном и том же наборе сделок (после применения фильтра “микро-риска”).

**Risk-weighted Expectancy (обязательное, total net).**

```text
Expectancy_R_w = sum(w_i * R_total_net_i) / sum(w_i)
```

Эквивалентная форма (допускается для диагностики):

```text
Expectancy_R_w = WR_w × Avg_Win_w − (1 − WR_w) × Avg_Loss_w
```

**Перевод в долю equity и правило агрегации (обязательное).**

```text
r_i = PnL_total_net_i / max(equity_before_i, pnl_eps_usd)
E[r] = mean(r_i)
E[r] ≈ Expectancy_R_w × mean(risk_per_trade_pct_actual_i)   (диагностически)
```

**Валидность KPI по выборке (обязательное).** Для использования `PF_money`, `Sharpe`, `Calmar`, `Expectancy_R_w`, `Kelly` в критериях допуска должны выполняться:

* `trades_count ≥ kpi_min_trades`,
* `loss_trades_count ≥ min_loss_trades`,
* `abs(sum(losses_money)) ≥ min_loss_threshold_money` или `≥ min_loss_threshold_pct_equity * equity`,
* `low_risk_excluded_share ≤ kpi_low_risk_excluded_share_cap`.

Если любое условие нарушено, соответствующая метрика помечается `INSUFFICIENT_SAMPLE`, запрещается использовать её для допуска, и формируется критическое событие мониторинга `kpi_insufficient_sample_event`.

**Требование консистентности.** Система обязана поддерживать внутреннюю консистентность метрик на уровне портфеля и на уровне подстратегий (TREND/RANGE) в пределах допустимой погрешности автотестов.

---

**Уточнения (добавлено при консолидации):**

**Фактический вес по исполнению (обязательное).**
**Floor-правило для статистики (обязательное).** Если `risk_pct_equity_i_actual < risk_pct_equity_stats_floor` или `risk_amount_i_actual < risk_amount_stats_floor_usd`, то:
* сделка исключается из вычисления `WR_w`, `Avg_Win_w`, `Avg_Loss_w`, `Expectancy_R_w`, `Kelly` и производных допусков;
* факт исключения логируется (`kpi_trade_excluded_low_risk_event`).
**PF-гомогенность (обязательное, диагностическое).**
**Требование совпадения PF (обязательное при VALID).** При `cv_risk <= pf_identity_cv_threshold` метрики `PF_money` и `PF_money_identity` обязаны совпадать в пределах допусков (Приложение C) на одном и том же наборе сделок.

#### 2.1.2. Учёт компаундинга, variance drag и path dependency
Линейное приближение:

```text
годовой результат ≈ E[r] × число сделок
```

используется только как ориентир. Реальная динамика компаундинга определяется equity-рядом:

```text
Equity(t_k) = Equity(t_0) × Π (1 + r_k)
```

**Требование корректности домена `log(1+r)`.**

* `r_k > -1 + compounding_r_floor_eps`;
* если `r_k ≤ -1 + compounding_r_floor_eps`, фиксируется критический инцидент `compounding_domain_violation_event`, активируется DRP-режим `EMERGENCY`, запрещаются новые входы до ручного подтверждения восстановления.

**Обработка экстремального случая ликвидации/долга (обязательное).** Если фактическое событие исполнения/ликвидации приводит к `r_k < -1`:

* вычисление `log(1+r_k)` запрещено;
* система обязана:

  * записать факт `r_k_raw`, `r_k_clamped = -1 + compounding_r_floor_eps`,
  * построить диагностический “квази-лог” на clamped значении только для предотвращения `MathDomainError`,
  * немедленно перевести DRP в `EMERGENCY` и инициировать протоколы восстановления/аудита.

**Требование устойчивого вычисления компаундинга (обязательное).**

```text
log(Equity(t_K)) = log(Equity(t_0)) + Σ log(1 + r_k)
```

Численная реализация:

* если `abs(r_k) < log1p_switch_threshold` использовать `log1p(r_k)`;
* иначе использовать `log(1 + r_k)`;
* доменная проверка выполняется до вызова `log/log1p`.

**Контроль variance drag (обязательный автотест/мониторинг).**

* точный расчёт на окне: `mean_ln = mean(ln(1+r_k))` (только для `r_k > -1 + compounding_r_floor_eps`);
* `trades_per_year` — эмпирическая оценка числа сделок/год; если оценка недоступна (короткое окно), использовать `trades_per_year_default`.
* метрика годовой потери на drag:

```text
g_trade = exp(mean_ln) - 1
variance_drag_per_trade = E[r] - g_trade
variance_drag_annual = variance_drag_per_trade * trades_per_year
geo_return_annual = exp(mean_ln * trades_per_year) - 1
arith_return_annual_approx = E[r] * trades_per_year
```

* если `variance_drag_annual > variance_drag_critical_frac * target_return_annual`, формируется предупреждение `variance_drag_critical_event`, включается `DEFENSIVE` и применяется снижение `kelly_fraction` и/или `dd_risk_max` по конфигу.

**Перекрывающиеся сделки (обязательное правило расчёта KPI).** Sharpe/MaxDD/CAGR/Calmar считаются по тайм-серии equity, полученной из событий PnL и mark-to-market. Trade-level `r_i` используется только как диагностическая агрегация.

Минимально допустимое число сделок: конфигурации с < **80 сделок/год** считаются неприемлемыми.

---

**Уточнения (добавлено при консолидации):**

* при нарушении фиксируется `compounding_domain_violation_event`, активируется DRP `EMERGENCY`, запрещаются новые входы до ручного подтверждения.
**Обработка экстремального случая ликвидации/долга (обязательное).** При `r_k < -1`:
* записываются `r_k_raw`, `r_k_clamped = -1 + compounding_r_floor_eps`;
* DRP переводится в `EMERGENCY`.
**Численная реализация компаундинга (обязательное).**
mean_ln = mean(ln(1+r_k))  (только для r_k > -1 + compounding_r_floor_eps)
**Перекрывающиеся сделки (обязательное правило KPI).** Sharpe/MaxDD/CAGR/Calmar считаются по тайм-серии equity (mark-to-market). Trade-level `r_i` — диагностически.
Минимально допустимое число сделок: < **80 сделок/год** — неприемлемо.

### 2.2. Минимальный капитал, дискретность лотов и динамический Tier-min-capital
* Рекомендуемый минимальный капитал Tier 1 (базовый): **$10,000**.
* При капитале < **$5,000** повышается вероятность:

  * «квантования» риска из-за лотов/мин. нотационала;
  * доминирования комиссий/проскальзывания в net-PnL.

**Динамический минимум капитала (обязательное требование оценки).** Для каждого инструмента и набора параметров системы рассчитывается рекомендуемый `min_capital_dynamic_usd`, обеспечивающий ограничение ошибки квантования риска.

Определения:

* `lot_step_qty` — шаг количества.
* `qty_target` — целевое количество до округления.
* `qty_rounded` — количество после округления по правилам ниже.
* `lot_granularity_error = abs(risk_pct_actual - risk_pct_target) / max(risk_pct_target, eps)` на representative-наборе сценариев.

Требование: при Tier 1 целевая ошибка квантования `lot_granularity_error <= lot_granularity_error_target`.

Рекомендуемая инженерная формула для нижней оценки (допускается как быстрый estimator):

```text
min_capital_dynamic_usd =
  max_notional_usd / leverage_effective
  × (min_risk_pct_target / lot_granularity_error_target)
```

Если `min_capital_dynamic_usd > equity_usd`, система обязана автоматически понижать список инструментов/частоту/риск и логировать `min_capital_violation_event`.

**Правила округления (обязательное).**

* расчётный объём переводится в лоты;
* округление по умолчанию вниз;
* при вычислении числа шагов лота запрещено прямое использование `int(float/step)` без epsilon-компенсации;
* безопасная формула (обязательная):

```text
steps = floor((amount + lot_rounding_eps) / step)
amount_rounded = steps * step
```

Если после округления отклонение фактического риска от целевого > `lot_rounding_risk_deviation_threshold`, сделка:

* отклоняется, или
* исполняется как «пониженный риск» (факт фиксируется в логах).

Фактический реализованный риск после округления обязателен к логированию и используется для расчётов `risk_per_trade_pct_actual`.

**Округление цены по `tick_size` (обязательное, консервативное).** Во всех оценках PnL/риска/уровней (включая pre-trade и тесты) округление цены выполняется так, чтобы оценка была в худшую сторону для стратегии:

* для LONG:

  * `entry_price` округляется вверх,
  * `take_profit` округляется вниз,
  * `stop_loss` округляется вниз;
* для SHORT:

  * `entry_price` округляется вниз,
  * `take_profit` округляется вверх,
  * `stop_loss` округляется вверх.

В live-исполнении фактические fill-цены используются как источник истины, но для pre-trade оценок действует правило консервативного округления.

---

**Уточнения (добавлено при консолидации):**

* Рекомендуемый минимальный капитал Tier 1: **$10,000**.
* При капитале < **$5,000** повышается вероятность квантования риска и доминирования издержек.
**Динамический минимум капитала (обязательное).** Для каждого инструмента рассчитывается `min_capital_dynamic_usd`, ограничивающий ошибку квантования риска.
**Консервативное округление цены по `tick_size` (обязательное).**
* LONG: `entry` вверх, `tp` вниз, `sl` вниз;
* SHORT: `entry` вниз, `tp` вверх, `sl` вверх.

### 2.3. Инструменты, корреляции, beta-risk, tail-risk, tail-dependence и basis-risk
Базовый кластер: BTCUSDT, ETHUSDT. Дополнительные инструменты — по согласованному списку ликвидных альтов.

Для каждого инструмента рассчитываются:

* корреляции с BTC/ETH на окнах 7/14/30/90/180/365 дней (H1);
* быстрые корреляции на окнах 1–3 часа и 3–24 часа;
* beta к BTC (или к индексу), включая стресс-оценки;
* tail-зависимость и tail-dependence на стресс-барах;
* метрики ликвидности: объём, глубина стакана, спред;
* basis-метрики и basis-risk;
* индикатор очереди ADL (при доступности у биржи).

#### 2.3.1. Tail subset, stress-метрики и окна расчёта
Окна:

* `corr_lookback_days ∈ {7,14,30,90,180,365}` (H1)
* tail/stress: `tail_lookback_days_default` (365d H1), при недостатке наблюдений расширяется до `tail_lookback_days_max`

Tail subset (нижний хвост ΔBTC):

1. `ΔBTC ≤ tail_fixed_threshold` (по умолчанию −5% за 1 час)
2. fallback: `ΔBTC ≤ q_tail` (по умолчанию 5-й перцентиль)

**Динамический минимум хвостовой выборки (обязательное).**

```text
tail_min_samples_dynamic =
  max(
    tail_min_samples_base,
    ceil(tail_min_samples_base * tail_vol_adj_factor * max(ATR_z_short, 1))
)
```

Метрики:

```text
CrashCondRet = E[ΔInstrument | ΔBTC ∈ tail]
Stress_beta  = Cov(ΔInstrument, ΔBTC | tail) / Var(ΔBTC | tail)
Tail_corr    = Corr(ΔInstrument, ΔBTC | tail)
Stress_beta ≈ Tail_corr × σ(ΔInstrument|tail) / σ(ΔBTC|tail)
Var(ΔBTC|tail) := max(Var(ΔBTC|tail), tail_var_eps)
```

#### 2.3.2. Tail-dependence coefficient (обязательное, со сглаживанием и плавным fallback)
Базовое определение:

```text
lambda_L(α) = P(ΔInstrument ≤ q_I(α) | ΔBTC ≤ q_BTC(α))
```

* основной `α`: `tail_dependence_alpha` (0.05)
* `n_tail = count(ΔBTC ≤ q_BTC(α))`

**Сглаживание (обязательное).**

```text
lambda_prior = clip(
  max(
    tail_dependence_alpha,
    lambda_prior_floor,
    tail_dependence_alpha + lambda_prior_corr_factor * max(Tail_corr, 0)
),
  tail_dependence_alpha,
  1.0
)
```

**Адаптивная инерция сглаживания (обязательное).**

```text
k0_eff = clip(
  k0_base / (1 + k0_vol_sensitivity * max(ATR_z_short - 1, 0)),
  k0_min,
  k0_max
)
if ATR_z_short < 1.0:
    k0_eff = clip(max(k0_eff, k0_low_vol_floor), k0_min, k0_max)
```

**Плавный переход к fallback (обязательное).**

```text
lambda_raw = empirical lambda_L(α)

lambda_smoothed = lambda_prior + (n_tail / (n_tail + k0_eff)) * (lambda_raw - lambda_prior)

lambda_fallback = clip(
  max(
    lambda_prior_floor,
    tail_dependence_alpha + tail_lambda_corr_factor * max(Tail_corr, 0)
),
  tail_dependence_alpha,
  1.0
)

tail_reliability_score = clip(n_tail / max(tail_min_samples_dynamic, 1), 0, 1)

lambda_used = tail_reliability_score * lambda_smoothed + (1 - tail_reliability_score) * lambda_fallback
tail_metrics_reliable = (tail_reliability_score >= tail_reliability_hard_threshold)
```

Требование логирования: `lambda_raw`, `lambda_smoothed`, `lambda_prior`, `k0_eff`, `n_tail`, `tail_min_samples_dynamic`, `tail_reliability_score`, `lambda_used`, `tail_metrics_reliable`.

#### 2.3.3. Stress correlation matrix (обязательное, PSD + нормировка + режимы стресса)
`C_raw` — эмпирическая корреляционная матрица. Конвейер:

1. shrinkage:

```text
C_shrunk = shrinkage(C_raw, shrinkage_alpha)
```

2. PSD + нормировка диагонали:

```text
C_psd = normalize_diag_to_one(PSD_project(C_shrunk))
```

3. стресс-преобразование (i≠j) по `stress_corr_mode`:

* `BREAK_HEDGES`:

  ```text
  rho_stress_raw_ij = clip(rho_ij + stress_corr_delta × (1 − rho_ij), -1, 1)
  ```
* `PRESERVE_SIGN`:

  ```text
  rho_stress_raw_ij = sign(rho_ij) * clip(abs(rho_ij) + stress_corr_delta × (1 − abs(rho_ij)), 0, 1)
  ```
* `ASYMMETRIC` (по умолчанию):

  ```text
  if rho_ij >= 0:
      rho_stress_raw_ij = clip(rho_ij + stress_corr_delta*(1 - rho_ij), 0, 1)
  else:
      rho_stress_raw_ij = clip(rho_ij - stress_corr_delta*(1 + rho_ij), -1, 0)
  ```

Диагональ: `rho_stress_raw_ii = 1`.

Формирование матрицы (обязательное):

```text
C_stress_raw[i,j] = rho_stress_raw_ij   for i≠j
C_stress_raw[i,i] = 1
```

4. PSD + нормировка:

```text
C_stress = normalize_diag_to_one(PSD_project(C_stress_raw))
```

5. регуляризация обусловленности (обязательное):

* если `λ_min(C_psd)` или `λ_min(C_stress)` < `corr_min_eigenvalue_floor`, применяется добавление `corr_regularization_alpha * I` с последующей PSD-проекцией и нормировкой диагонали.

**Сглаживание во времени (обязательное, анти-фликер).**

* `γ ∈ [0,1]` определяется из режима волатильности/DRP/хвостовых предупреждений,
* `γ_s = EMA(γ, stress_gamma_ema_alpha)`.

```text
C_blend_raw = (1 - γ_s) * C_psd + γ_s * C_stress
C_blend = normalize_diag_to_one(PSD_project(C_blend_raw))
```

**Требование к PSD-проекции (обязательное).** `PSD_project` реализуется алгоритмом Higham с ограничением `psd_higham_max_iters`. Если сходимость не достигнута — fallback `eigenvalue_clipping`:

1. симметризация: `A := (A + Aᵀ)/2`
2. разложение: `A = Q Λ Qᵀ`
3. клиппинг: `Λ' = max(Λ, psd_eig_floor)`
4. восстановление: `C_tmp = Q Λ' Qᵀ`

**Нормировка диагонали (обязательная, с защитой от NaN/inf).**

* перед `D^{-1/2}` диагональ клиппируется: `D := max(diag(C_tmp), psd_diag_floor)`
* нормировка:

```text
D = max(diag(C_tmp), psd_diag_floor)
C_norm = D^{-1/2} * C_tmp * D^{-1/2}
```

**Итерации Clip→Normalize (обязательное требование fallback).** Для fallback пути выполняется 2–3 итерации:

* `C_tmp := PSD_clip(C_tmp)` → `C_tmp := NormalizeDiag(C_tmp)`
  Цель: обеспечить `diag==1` в пределах `diag_eps` и отсутствие отрицательных собственных значений ниже `-psd_neg_eig_tol`.

**Производительность и публикация (обязательное).**

* PSD-проекция запрещена в hot path.
* `C_psd`, `C_stress`, `C_blend`, а также `γ_s` публикуются асинхронно по расписанию (закрытие H1 бара и/или таймер), через `corr_matrix_publisher_channel` со снапшотом:

  * `corr_matrix_snapshot_id`,
  * `computed_at_ts_utc_ms`,
  * `valid_from_ts_utc_ms`,
  * `matrix_age_sec`,
  * `gamma_s`,
  * `sha256` матрицы и параметров.
* Gatekeeper использует только снапшоты, где `valid_from_ts_utc_ms <= now` и `matrix_age_sec <= corr_matrix_max_age_sec`; иначе режим `DEFENSIVE` и множитель `corr_matrix_stale_mult`.

#### 2.3.4. Fallback при недостоверных tail-оценках
Если `tail_metrics_reliable=False`:

* риск снижается через `tail_unreliable_mult`,
* запрет новых входов при одновременном ухудшении ликвидности,
* усиление кластерных лимитов,
* перевод DRP минимум в `DEFENSIVE` при совпадении с co-crash сигналами.

#### 2.3.5. Basis-risk (обязательное: уровень, направление неблагоприятности и волатильность базиса)
Определения:

* `basis_value = (perp_price - index_price) / index_price`
* `basis_z` — робастная нормировка уровня basis
* `basis_change_Δt` — изменение basis на окне (1ч/4ч/24ч)
* `basis_vol_1h` — робастная оценка волатильности basis на rolling-окне
* `basis_vol_z` — робастная нормировка `basis_vol_1h`
* `time_to_next_funding_sec` — до ближайшего funding (для перпов)
* `time_to_expiry_sec` — до экспирации (для фьючерсов, если используется)

Требование к робастной оценке `basis_vol_1h`:

* устойчивость к одиночным спайкам;
* допустимые реализации: winsorized std (по умолчанию), trimmed robust std, downside deviation (по направлению сделки).

**Формула `basis_risk_mult` (обязательное).** Базовая часть по уровню:

```text
basis_level_mult =
  1,                              если |basis_z| <= basis_z_soft
  basis_risk_mult_soft,           если basis_z_soft < |basis_z| <= basis_z_hard
  basis_risk_mult_hard,           если |basis_z| > basis_z_hard
```

Часть по волатильности базиса:

```text
basis_vol_mult =
  1,                              если basis_vol_z <= basis_vol_z_soft
  basis_vol_mult_soft,            если basis_vol_z_soft < basis_vol_z <= basis_vol_z_hard
  basis_vol_mult_hard,            если basis_vol_z > basis_vol_z_hard
```

Часть по близости события (обязательная, если `time_to_next_funding_sec` доступен):

```text
event_proximity_mult =
  1, если time_to_next_funding_sec > basis_event_proximity_soft_sec
  basis_event_mult_soft, если within soft..hard
  basis_event_mult_hard, если time_to_next_funding_sec <= basis_event_proximity_hard_sec
```

Итог:

```text
basis_risk_mult = min(basis_level_mult, basis_vol_mult, event_proximity_mult)
# Пояснение: min() выбирает наиболее консервативный (наименьший) множитель,
# т.к. каждый компонент уменьшает риск (значения ≤ 1) при ухудшении условий.
# Наименьший множитель соответствует самому жёсткому ограничению.
```

Пороги и дефолты — в Приложении C. Basis-risk участвует в Gatekeeper и REM, логируется и тестируется в backtest идентично live.

---

**Уточнения (добавлено при консолидации):**

**Формула `basis_risk_mult` (обязательное).**

### 2.4. Стиль торговли и таймфреймы
* Стиль: intra-swing / positional intraday (часы → несколько дней).
* Сигнальный ТФ: H1.
* Контекст: H4/D1 — фильтр направления; M15 — уточнение входа; M5 — микроструктура исполнения (при необходимости).

---

## 3. ОБЩАЯ АРХИТЕКТУРА
Модули системы:

1. **MRC — Market Regime Classifier**
2. **TREND Engine**
3. **RANGE Engine**
4. **MLE — Meta-Labeling Engine**
5. **REM — Risk & Exposure Manager**
6. **EXM — Execution Module**
7. **MLOps Layer**
8. **MVM — Model Versioning, Shadow Mode, A/B testing, Rollback**
9. **DRP — Disaster Recovery Protocol** и контур деградации
10. **Data Layer** — сбор, валидация, хранение данных (рынок, микроструктура, orderbook, funding, OI, basis, ADL queue)
11. **Correlation Matrix Publisher** — асинхронный расчёт и публикация `C_psd/C_stress/C_blend` со снапшотами и `valid_from_ts`

**Архитектура снапшотов (обязательное).** Обновление `market_state`/`portfolio_state` выполняется событийно (Reactor/Event Loop). Gatekeeper читает «горячий» кэш (in-memory/Redis) без блокирующего I/O в критическом пути. Каждый снапшот имеет монотонный `snapshot_id` и timestamp.

**Контроль конкурентности и источника истины (обязательное).**

* применяется принцип Single Writer для портфельного состояния: изменения `portfolio_state` выполняет один компонент — `PortfolioStateWriter`;
* Gatekeeper и REM читают снапшоты как неизменяемые структуры;
* подтверждение ордеров и фиксация факта исполнения обязаны создавать новый `portfolio_state` со следующим `portfolio_id` (и новым `snapshot_id`);
* операции “рассчитать → зарезервировать риск → отправить ордер → зафиксировать в портфеле” выполняются через `RiskCoordinator` с оптимистической проверкой:

  * `portfolio_id_used == current_portfolio_id_at_commit` (где `portfolio_id_used` — `portfolio_state.portfolio_id`, использованный в расчёте/резервировании),
  * при несовпадении — отказ `stale_portfolio_snapshot`.

**Требования к производительности горячего пути (обязательное).**

* В режиме LIVE:

  * `gatekeeper_latency_p99_ms` (от получения снапшота до решения + sizing + reservation-precheck) ≤ `gatekeeper_latency_budget_p99_ms`:

    * Tier 1: ≤ 500 ms
    * Tier 2: ≤ 300 ms
    * Tier 3: ≤ 200 ms
  * `preexec_validation_deadline_ms` ≤ 500 ms (с момента финального решения до отправки ордера).
* Логирование и запись метрик не должны блокировать горячий путь:

  * критические события допускается писать синхронно только при `EMERGENCY`/`CRITICAL`,
  * остальное — асинхронно (очередь/буфер/батчи), с backpressure и деградацией до sampling при перегрузке.

---

**Уточнения (добавлено при консолидации):**

11. **Correlation Matrix Publisher**
**Архитектура снапшотов (обязательное).** Обновление `market_state`/`portfolio_state` — событийно (Reactor/Event Loop). Gatekeeper читает in-memory кэш без блокирующего I/O. Каждый снапшот имеет монотонный `snapshot_id` и timestamp.

### 3.0. Идентификаторы согласованности, логические часы и потоки обновлений (обязательное)
Система использует два независимых потока версий и монотонные логические часы.

1. `market_data_id` — монотонный идентификатор обновления рыночных данных.
2. `portfolio_id` — монотонный идентификатор версии портфеля.
3. `logical_clock_ms` — монотонный логический таймер (Lamport clock):

```text
logical_clock_ms := max(external_ts_ms, logical_clock_ms_prev + 1)
```

**Инвариант трассируемости (обязательное).** В целях диагностики вводится нижняя оценка:

```text
logical_clock_ms >= market_state.ts_utc_ms
```

Нарушение инварианта запрещено и приводит к `logical_clock_invariant_violation_event` и `DRP_state>=DEFENSIVE`.

**Требование.** Optimistic lock при коммитах и резервировании использует только `portfolio_id`. Свежесть рыночных данных проверяется по timestamp/staleness, а не по совпадению идентификаторов.

---

**Уточнения (добавлено при консолидации):**

Система использует два независимых потока версий и монотонные логические часы:
1. `market_data_id`, 2) `portfolio_id`, 3) `logical_clock_ms` (Lamport):
Инвариант трассируемости:
Нарушение → `logical_clock_invariant_violation_event` и `DRP_state>=DEFENSIVE`.

### 3.1. Архитектура снапшотов, Single Writer, шардирование и OCC (обязательное)
Обновление `market_state` выполняется событийно; обновление `portfolio_state` выполняется через контролируемый контур записи.

**Контур записи портфеля (обязательное).**

* Для Tier 1 допускается один `PortfolioStateWriter`.
* Для Tier 2/3 допускается шардирование `PortfolioStateWriter` по `cluster_id` или `instrument`.

**Глобальный координатор риска (обязательное).** При шардировании существует `RiskReservationCoordinator`, публикующий глобальные агрегаты рисков.

**Optimistic Concurrency Control для шардов (обязательное).** Запись выполняется без блокировки глобальных агрегатов:

1. шард формирует транзакцию изменения позиции и дельты агрегатов, читая `global_agg_version`;
2. выполняет попытку коммита с условием `global_agg_version` не изменился;
3. при конфликте выполняется retry с ограничением `max_occ_retries` и backoff.

Детерминизм обеспечивается фиксированными правилами упорядочивания коммитов по `(logical_clock_ms, shard_id, sequence)`.

**Источник истины (обязательное).**

* любые изменения `portfolio_state` записывает только Writer/Shard-Writer;
* Gatekeeper и REM читают `portfolio_state` как неизменяемую структуру;
* подтверждение ордеров и фиксация факта исполнения обязаны создавать новый `portfolio_state` со следующим `portfolio_id`.

**Fast reject path (обязательное).** При перегрузке Writer:

* `writer_queue_depth > writer_queue_hard_cap` или `expected_commit_latency_ms > commit_latency_budget_ms` → отклонение новых входов (`portfolio_writer_overload_block`), разрешены только закрытия/уменьшение риска.

**Максимальный возраст снапшотов (обязательное).**

* `market_state` запрещено использовать, если `now_ms - market_state.ts_utc_ms > snapshot_max_age_ms`.
* `snapshot_max_age_ms` задаётся в Приложении C (рекомендуется ≥ max(`staleness_price_hard_ms`, `staleness_liquidity_hard_ms`)).
* Несовпадение `schema_version` → отказ `snapshot_version_mismatch` / `portfolio_version_mismatch`.

---

**Уточнения (добавлено при консолидации):**

* Tier 1: один `PortfolioStateWriter`.
* Tier 2/3: допускается шардирование по `cluster_id` или `instrument`.
**Optimistic Concurrency Control (обязательное).**
* транзакции по `(logical_clock_ms, shard_id, sequence)` детерминированно упорядочены.
**Формальные определения агрегатов портфеля (обязательное, источник истины для дашборда/лимитов).**
* `direction_sign_i = +1` для long, `-1` для short
* `signed_risk_pct_i = direction_sign_i * risk_pct_equity_i`
current_sum_abs_risk_pct   = Σ |signed_risk_pct_i|                      # gross (без учёта хеджирования)
current_portfolio_risk_pct = |Σ signed_risk_pct_i|                      # net (направленный)
current_cluster_risk_pct   = |Σ signed_risk_pct_i| по cluster_id        # net в кластере
`adjusted_heat_*` — отдельная корреляционная норма (раздел 8.3) и не является заменой `current_*_risk_pct`.

### 3.2. Требования к производительности горячего пути (обязательное)
* В LIVE:

  * Tier 1: `gatekeeper_latency_p99_ms` ≤ 500 ms
  * Tier 2: ≤ 300 ms
  * Tier 3: ≤ 200 ms
* Логирование и запись метрик не должны блокировать горячий путь:

  * критические события допускается писать синхронно только при `EMERGENCY/CRITICAL`,
  * остальное — асинхронно с backpressure и деградацией до sampling.

**Требования к рантайм-оптимизации (обязательное).**

* сериализация/десериализация: использовать `orjson` (или эквивалент с гарантией детерминированной сериализации);
* на время обработки сигнала допускается отключение GC в Python, если Gatekeeper реализован на Python:

  * `gc.disable()` перед обработкой,
  * `gc.enable()` после обработки,
  * запрет отключения GC при `EMERGENCY` (для предотвращения утечек в аварийном режиме).
* допускается реализация Gatekeeper как отдельного сервиса/ядра на компилируемом языке при полном сохранении контрактов и детерминизма.

---

**Уточнения (добавлено при консолидации):**

Логирование/метрики не должны блокировать hot path; критические события допускаются синхронно только при `EMERGENCY/CRITICAL`.

### 3.3. Final Decision Rule (Gatekeeper)
Gatekeeper — единая точка допуска сигнала к исполнению и расчёту позиции. Gatekeeper работает на согласованном снапшоте и детерминирован при фиксированном входе.

**Уточнения (добавлено при консолидации):**

Gatekeeper — единая точка допуска сигнала к исполнению и расчёту позиции. Gatekeeper детерминирован при фиксированном входе.

#### 3.3.1. Снапшот данных, staleness, кросс-валидация источников и Data Quality Score
`evaluate_entry_signal` работает на снапшоте с контролем staleness:

* критические данные (Critical):

  * цена/волатильность: `≤ 1000–2000 ms` для решения H1 (точные пороги — конфиг),
  * стакан/ликвидность для исполнения в EXM: `≤ 200–500 ms`;
* некритические данные (Non-critical):

  * funding/OI/basis/ADL: `≤ 30–120 s`.

**Кросс-валидация цены (обязательное).** Для критических ценовых полей `last/mid/bid/ask` рассчитывается расхождение между источниками (биржа-исполнитель и независимый индекс) с учётом staleness каждого источника:

```text
price_src_ref = 0.5 * (price_src_A + price_src_B)
xdev_bps = 10000 * abs(price_src_A - price_src_B) / max(price_src_ref, price_eps_usd)
```

**Независимый sanity-check оракул (обязательное).** Добавляется третий источник `price_oracle_C` (инфраструктурно независимый индекс/оракул). Проверка выполняется только как sanity-check с широким допуском:

```text
oracle_dev_frac = abs(price_src_ref - price_oracle_C) / max(price_oracle_C, price_eps_usd)
```

Если `oracle_dev_frac >= oracle_dev_block_frac` и `oracle_staleness_ms <= oracle_staleness_hard_ms`, то:

* `suspected_data_glitch=True`,
* торговля блокируется hard-gate `oracle_sanity_block`.

**Взвешенное качество источников (обязательное).** Для каждого источника i:

```text
dqs_src_i = clip(1 - staleness_i / staleness_hard_i, 0, 1)
```

Агрегация:

```text
DQS_sources = sum(w_i * dqs_src_i) / sum(w_i)
```

---

**Уточнения (добавлено при консолидации):**

* Critical: цена/волатильность `≤ 1000–2000 ms`, стакан `≤ 200–500 ms`
* Non-critical: funding/OI/basis/ADL `≤ 30–120 s`
Если `oracle_dev_frac >= oracle_dev_block_frac` и `oracle_staleness_ms <= oracle_staleness_hard_ms` → `oracle_sanity_block`.
**Hard-gate “Stale Book but Fresh Price” (обязательное).** Если mid/last цена меняется (по trade-feed), а `orderbook_update_id_age_ms` (возраст последнего изменения `orderbook_last_update_id`) превышает `orderbook_update_id_stale_ms` (и `orderbook_update_id_age_ms` не `null`), то:
* hard-блок `stale_book_glitch_block`,
* DRP минимум `EMERGENCY` при повторе `stale_book_glitch_repeat_threshold` раз за окно `stale_book_glitch_window_minutes` минут.
**Взвешенное качество источников (обязательное).**

#### 3.3.1.1. Hard-gates качества данных и ступенчатый DQS
**Принцип (обязательное).** Для критических параметров качество данных является “жёстким”: если нарушен любой критический порог — торговля блокируется независимо от остальных сигналов.

**Hard-gates (обязательные).**

Если выполняется любое из условий:

* `DQS_critical = 0`,
* `data_quality_score = 0`,
* `DRP_state` минимум `RECOVERY`,
* новые входы запрещены.

Список hard-gates:

* `staleness_price_ms > staleness_price_hard_ms`
* `staleness_liquidity_ms > staleness_liquidity_hard_ms`
* `xdev_bps >= xdev_block_bps` (при валидных staleness обоих источников) либо `DQS_sources < dqs_sources_min`
* `suspected_data_glitch=True`
* `oracle_sanity_block=True`
* обнаружение NaN/inf в критических полях цены/ATR/спреда/глубины

**Усиленная защита от toxic-flow (обязательное).** Вход блокируется как `toxic_flow_suspected_block`, если одновременно:

* `execution_price_improvement_bps >= price_improvement_bps_suspicious`,
* `data_quality_score < dqs_degraded_threshold`,
* `spread_bps >= toxic_flow_spread_bps_min`,
* и/или выполняется частотный триггер: `price_improvement_events_last_N >= toxic_flow_improvement_count_threshold`.

**Ступенчатый расчёт DQS (обязательное).** Если hard-gates не сработали:

* `DQS_critical` вычисляется ступенчато по корзинам staleness и целостности;
* `DQS_noncritical` вычисляется по staleness деривативов/полноте;
* итог:

```text
DQS = dqs_weight_critical * DQS_critical + (1 - dqs_weight_critical) * DQS_noncritical
```

`dqs_weight_critical` по умолчанию 0.75.

**Плавный множитель качества данных (обязательное).** Помимо порогов DRP вводится `dqs_mult` (используется в REM):

```text
if DQS >= dqs_degraded_threshold: dqs_mult = 1
elif DQS <= dqs_emergency_threshold: dqs_mult = 0
else:
  dqs_mult = (DQS - dqs_emergency_threshold) /
             (dqs_degraded_threshold - dqs_emergency_threshold)
```

**Warm-up после аварии данных (обязательное).**

* после выхода из состояния `EMERGENCY`, вызванного качеством данных, система обязана находиться в `RECOVERY`;
* `warmup_required_bars` зависит от причины `emergency_cause`:

```text
warmup_required_bars =
  if cause == "DATA_GLITCH": 3
  if cause == "LIQUIDITY":   6
  if cause == "DEPEG":       24
  else: clip(warmup_bars_base + floor(recovery_hold_minutes / 60), warmup_bars_min, warmup_bars_max)
```

* до завершения warm-up новые входы запрещены; разрешены только закрытия/уменьшение риска.

**Анти-флаппинг DQS/DRP (обязательное).** Вводятся счётчики:

* `drp_flap_count` — число переходов между “строгими” состояниями (EMERGENCY/RECOVERY/DEFENSIVE) в скользящем окне `flap_window_minutes_eff`, где:

```text
flap_window_minutes_eff = clip(flap_window_minutes_base / max(ATR_z_short, 1), flap_window_minutes_min, flap_window_minutes_max)
```

* при `drp_flap_count >= flap_to_hibernate_threshold` система переходит в `HIBERNATE` и запрещает новые входы до ручного подтверждения оператора и выдержки `hibernate_min_duration_sec`.

Контракт:

```python
def evaluate_entry_signal(
    mrc_regime: str,
    mrc_probs: dict,
    baseline_regime: str | None,
    engine_signal: dict,
    mle_output: dict | None,
    market_state: dict,
    portfolio_state: dict
) -> tuple[bool, float, str, dict]:
    """
    Returns:
      entry_allowed: bool
      position_size_notional: float
      rejection_reason: str
      diagnostics: dict
    """
```

**Уточнения (добавлено при консолидации):**

* `xdev_bps >= xdev_block_bps` (при валидном staleness источников) либо `DQS_sources < dqs_sources_min`
* NaN/inf в критических полях цены/ATR/спреда/глубины
* `stale_book_glitch_block=True`
Ступенчатый DQS при отсутствии hard-gates:
Warm-up после аварии данных — обязательный (`RECOVERY`, входы запрещены).
Anti-flapping — обязательный (переход в `HIBERNATE` при достижении порога).
Контракт `evaluate_entry_signal` — обязателен (фиксированная сигнатура; изменения запрещены).

#### 3.3.2. Порядок гейтов
Порядок гейтов фиксирован и обязателен:

1. **GATE 0: Warm-up / Data Availability / Cross-Validation / Hard-gates / DQS**
2. **GATE 1: DRP / Emergency / Kill-switch блокировки**
3. **GATE 2: MRC confidence + baseline + conflict resolution**
4. **GATE 3: Совместимость режима и стратегии**
5. **GATE 4: Валидация сигнала движка**
6. **GATE 5: Pre-sizing + размеро-инвариантная оценка издержек и единиц (unit_risk_bps, expected_cost_R_preMLE)**
7. **GATE 6: Решение MLE (size-invariant по price-edge)**
8. **GATE 7: Liquidity gates (H1 + стакан)**
9. **GATE 8: Gap / data glitch**
10. **GATE 9: Funding фильтр + proximity-модель + blackout-условия**
11. **GATE 10: Basis-risk (уровень + волатильность + близость события)**
12. **GATE 11: Санити уровней входа/SL и net-RR (all-in EffectivePrices)**
13. **GATE 12: Bankruptcy Risk Check (gap, leverage buffer, портфельный stress-gap)**
14. **GATE 13: Sequential Risk (REM)**
15. **GATE 14: Финальный sizing (аналитический или итеративный с демпфированием и guard-условиями)**
16. **GATE 15: Impact / Execution limits**
17. **GATE 16: Risk Reservation + Pre-execution validation (≤500 ms)**
18. **GATE 17: Финальная сверка фактического риска после округления лота**
19. **GATE 18: Partial fill economics (после первого fill-события)**

**Режим SHADOW (обязательное ограничение вычислений).** Если `trading_mode == SHADOW`, Gatekeeper обязан завершить обработку после GATE 6 и вернуть `entry_allowed=False` с причиной `shadow_mode_no_trade`, сохранив диагностику. Гейты 7–18 в этом режиме не выполняются.

**Размеро-инвариантность до финального sizing.** До GATE 14 запрещено использовать величины, зависящие от `qty_actual` и округления, кроме строго диагностических логов. Любые сравнения в гейтах должны быть выполнены в согласованных единицах (bps vs R vs pct_equity); валидатор единиц обязателен.

---

**Уточнения (добавлено при консолидации):**

1. GATE 0: Warm-up / Data Availability / Cross-Validation / Hard-gates / DQS
2. GATE 1: DRP / Emergency / Kill-switch
3. GATE 2: MRC confidence + baseline + conflict resolution
4. GATE 3: Совместимость режима и стратегии
5. GATE 4: Валидация сигнала движка
6. GATE 5: Pre-sizing + size-invariant издержки/единицы (`unit_risk_bps`, `expected_cost_R_preMLE`)
7. GATE 6: Решение MLE (size-invariant по price-edge)
8. GATE 7: Liquidity gates
9. GATE 8: Gap / data glitch
10. GATE 9: Funding фильтр + proximity + blackout
11. GATE 10: Basis-risk (уровень + волатильность + близость события)
12. GATE 11: Санити уровней входа/SL и net-RR (all-in EffectivePrices)
13. GATE 12: Bankruptcy Risk Check (gap, leverage buffer, stress-gap портфеля)
14. GATE 13: Sequential Risk (REM)
15. GATE 14: Финальный sizing
16. GATE 15: Impact / Execution limits
17. GATE 16: Risk Reservation + Pre-execution validation
18. GATE 17: Финальная сверка фактического риска после округления
19. GATE 18: Partial fill economics (после первого fill)
**Режим SHADOW (обязательное).** При `trading_mode == SHADOW` обработка завершается после GATE 6, `entry_allowed=False`, причина `shadow_mode_no_trade`.

#### 3.3.3. GATE 2: MRC Confidence / Baseline / Conflict Resolution (включая probe-режим)
Пороги:

* `mrc_high_conf_threshold` (0.70),
* `mrc_very_high_conf_threshold` (0.85),
* `mrc_low_conf_threshold` (0.55),
* `conflict_window_bars` (10; адаптивно сокращается при `ATR_z_short >= conflict_fast_atr_z`),
* `conflict_ratio_threshold` (0.60),
* `diagnostic_block_minutes` (120).

Классы MRC (H1): `TREND_UP, TREND_DOWN, RANGE, NOISE, BREAKOUT_UP, BREAKOUT_DOWN`. Baseline: `TREND_UP, TREND_DOWN, RANGE, NOISE`.

Правило выбора `final_regime` детерминированно:

* `MRC=NOISE` → по умолчанию `NO_TRADE`, кроме исключения для RANGE.
* `Baseline=NOISE`:

  * если `MRC confidence ≥ mrc_very_high_conf_threshold` и `MRC ∈ {TREND_*, BREAKOUT_*}` → `final_regime = MRC` с `noise_override_risk_mult` и усиленными требованиями ликвидности/издержек;
  * иначе → `NO_TRADE`.
* `MRC=RANGE`, `Baseline=TREND_*` → `RANGE`.
* `MRC=TREND_*`, `Baseline=RANGE` → `BREAKOUT_*` по направлению MRC с пониженным риском и усиленными требованиями ликвидности/издержек.
* `MRC=BREAKOUT_*`, `Baseline=RANGE` → `BREAKOUT_*`.
* `MRC=BREAKOUT_*`, `Baseline=TREND_*`:

  * совпадает знак → `BREAKOUT_*`,
  * иначе → `NO_TRADE`.

**Probe-режим при конфликте тренда (обязательное, ограниченное).**

Если `MRC=TREND_UP` и `Baseline=TREND_DOWN` (или наоборот), допускается `PROBE_TRADE` при одновременном выполнении:

* `MRC confidence ≥ mrc_very_high_conf_threshold`,
* `data_quality_score >= dqs_degraded_threshold`,
* `depth_bid_usd >= probe_min_depth_usd` и `depth_ask_usd >= probe_min_depth_usd`,
* `spread_bps <= probe_max_spread_bps`,
* `MLE.decision ∈ {NORMAL, STRONG}`.

В `PROBE_TRADE`:

* `final_regime = MRC`,
* риск умножается на `probe_risk_mult` (по умолчанию 0.33),
* taker-входы запрещены,
* требования по `net_RR` повышаются через `RR_min_probe_add`.

Устойчивый конфликт на окне `conflict_window_bars` блокирует торговлю инструментом на `diagnostic_block_minutes`.

---

#### 3.3.4. Funding фильтр (size-invariant R): модель, конвенция знака, proximity-модель и blackout-условия

##### 3.3.4.1. Конвенция знака funding (обязательная)
* `funding_rate > 0`: LONG платит, SHORT получает.
* `direction_sign = +1` для LONG, `-1` для SHORT.

```text
funding_pnl_frac_event = - direction_sign * funding_rate_event
```

##### 3.3.4.2. Оценка ожидаемых событий funding на горизонте удержания (обязательное)
Пусть:

* `expected_holding_hours` — из `engine_signal.context`.
* `funding_period_hours` — по бирже (обычно 8), конфиг.
* `time_to_next_funding_sec` — из `market_state`.

Детерминированная оценка числа funding-событий на горизонте удержания (целое число):

```text
t_next_h = time_to_next_funding_sec / 3600
if expected_holding_hours < t_next_h:
    n_events_raw = 0
else:
    n_events_raw = 1 + floor((expected_holding_hours - t_next_h) / funding_period_hours)
```

Для устранения скачков при движении `time_to_next_funding_sec` (особенно около границ периода) `n_events` сглаживается по времени шириной `funding_count_smoothing_width_sec` (EMA). После сглаживания `n_events` может быть дробным; интерпретация — сглаженная оценка ожидаемого числа событий funding на горизонте удержания.

##### 3.3.4.3. Funding в единицах R (обязательное, size-invariant)
Пусть:

* `f` — прогноз funding rate на один период (доля от notionals), знак биржевой.
* `unit_risk_allin_net` — all-in unit risk.
* `entry_price_ref = max(entry_price, price_eps_usd)`.

Ожидаемый funding PnL в долях notional:

```text
funding_pnl_frac = - direction_sign * f * n_events
```

Перевод в R (обязательное; стабильный по единицам и с абсолютным floor):

```text
funding_R = funding_pnl_frac * entry_price_ref / max(unit_risk_allin_net, unit_risk_min_absolute_for_funding)
```

Определения стоимости/бонуса:

```text
funding_cost_R  = max(0, -funding_R)
funding_bonus_R = max(0,  funding_R)   # используется только диагностически либо по политике risk-policy
```

**Уточнения (добавлено при консолидации):**

funding_bonus_R = max(0,  funding_R)

##### 3.3.4.4. Net_Yield_R и решение funding-гейта (обязательное)
`EV_R_price` берётся из MLE. Ожидаемые издержки исполнения в R берутся как:

* `expected_cost_R_postMLE` (если MLE доступен), иначе `expected_cost_R_preMLE`.

**Price-edge после издержек (обязательное для гейтов доходности).**

```text
expected_cost_R_used = expected_cost_R_postMLE if MLE_available else expected_cost_R_preMLE
EV_R_price_net = EV_R_price - expected_cost_R_used
```

Политика учёта funding-бонуса:

* `funding_credit_allowed: bool` (конфиг; по умолчанию False)

```text
funding_bonus_R_used = funding_bonus_R if funding_credit_allowed else 0
Net_Yield_R = EV_R_price_net - funding_cost_R + funding_bonus_R_used
```

Гейты:

* `unit_risk_allin_net < unit_risk_min_for_funding` → `funding_unit_risk_too_small_block`
* `funding_cost_R >= funding_cost_block_R` → `funding_cost_block`
* `Net_Yield_R < min_net_yield_R` → `funding_net_yield_block`

Множитель `funding_risk_mult` и proximity-модель/blackout — обязательны (формулы сохранены; применяются к риску, а blackout даёт hard-блок при выполнении условий).

---

##### 3.3.4.5. Proximity-модель перед событием funding (обязательное, непрерывное)
Вводится непрерывная функция штрафа близости события, чтобы избегать дискретного “обрыва” по минутам.

Параметры: `funding_proximity_soft_sec`, `funding_proximity_hard_sec`, `funding_proximity_power`, `funding_proximity_mult_min`.

```text
tau = clip((funding_proximity_soft_sec - time_to_next_funding_sec) /
           max(funding_proximity_soft_sec - funding_proximity_hard_sec, 1), 0, 1)

funding_proximity_mult =
  1 - (1 - funding_proximity_mult_min) * (tau ^ funding_proximity_power)
```

`funding_proximity_mult` применяется как дополнительный множитель риска и/или как добавка к `funding_cost_R` по политике.

##### 3.3.4.6. Blackout около события funding (обязательное, horizon-aware)
Blackout применяется только при одновременном выполнении:

* `time_to_next_funding_sec <= funding_blackout_minutes * 60 + funding_event_inclusion_epsilon_sec`
* `funding_cost_R > 0`
* `expected_holding_hours <= funding_blackout_max_holding_hours`
* относительная значимость издержки:

```text
funding_cost_R / max(EV_R_price, funding_blackout_ev_eps) >= funding_blackout_cost_share_threshold
```

При выполнении условий вход блокируется (`funding_blackout_block`). Во всех остальных случаях применяется `funding_risk_mult` и `funding_proximity_mult`.

---

#### 3.3.5. GATE 11: Санити уровней входа, SL и net-RR (обязательное, единая “истина” 1R)
Отказы:

* невалидные цены/NaN/inf;
* `SL_distance < sl_min_atr_mult * ATR`;
* `SL_distance > sl_max_atr_mult * ATR`.

**Эффективные цены all-in (обязательные).** `entry_eff_allin/tp_eff_allin/sl_eff_allin` вычисляются в модуле EffectivePrices по Приложению A.2. Все bps-компоненты (fees/spread/slippage/impact/stop_slippage_mult) определены и выбираются детерминированно по типу исполнения.

**Единая “истина” 1R (обязательное).**

```text
unit_risk_allin_net = abs(entry_eff_allin - sl_eff_allin)
risk_amount         = qty * unit_risk_allin_net
```

**Net-RR (обязательное).**

```text
net_reward = abs(tp_eff_allin - entry_eff_allin)
net_risk   = abs(entry_eff_allin - sl_eff_allin)
net_rr_eps_price = max(tick_size, entry_price * net_rr_eps_bps/10000)
net_RR     = net_reward / max(net_risk, net_rr_eps_price)
```

Требование: `net_RR >= RR_min_{engine}`, иначе отказ.

**Автотест “SL даёт -1R” по фактическим fill-ценам (обязательное).** Система обязана проверять на synthetic-кейсах и на записанных эпизодах, что `R_total_net(stop_fact) ≈ -1` в допусках `integration_kpi`. Для partial fills проверка выполняется по фактической средневзвешенной цене входа и фактическому объёму.

---

**Уточнения (добавлено при консолидации):**

All-in EffectivePrices — по Приложению A.2.
Инвариант “SL даёт −1R” по фактическим fill-ценам — обязателен.

#### 3.3.6. GATE 12: Bankruptcy Risk Check (обязательное: gap, leverage buffer, stress-gap портфеля)
Секции gap-модели, запрет двойного учёта basis по умолчанию, leverage buffer и стресс-гэп портфеля — обязательны.

---

##### 3.3.6.1. Экономический порог банкротства (обязательное)
Определяются два независимых понятия:

* `compounding_r_floor_eps` — технический доменный guard для `log(1+r)` (раздел 2.1.2).
* `bankruptcy_threshold_pct_equity` — экономический риск-порог (доля equity), выше которого потери считаются неприемлемыми.

Также задаётся буфер:

```text
bankruptcy_buffer_pct_equity
max_gap_loss_pct_equity = min(max_gap_loss_pct_equity_config, bankruptcy_threshold_pct_equity - bankruptcy_buffer_pct_equity)
portfolio_max_gap_loss_pct_equity = min(portfolio_max_gap_loss_pct_equity_config, bankruptcy_threshold_pct_equity - bankruptcy_buffer_pct_equity)
```

##### 3.3.6.2. Gap-модель (обязательное; без двойного учёта штрафов)
Определения:

* `gap_frac_base` — базовый гэп,
* `hv30` — 30-дневная историческая волатильность (робастная) на H1 (доля на бар),
* `hv30_ref` — базовый уровень `hv30` (медиана `hv30` на окне `hv30_ref_lookback_days`),
* `hv30_z` — относительный множитель волатильности:

```text
hv30_z = hv30 / max(hv30_ref, price_eps_frac)
gap_frac_dyn = gap_frac_base * (1 + gap_hv_sensitivity * clip(hv30_z - 1, 0, gap_hv_z_cap))
gap_frac = clip(gap_frac_dyn, gap_frac_min, gap_frac_max)
```

Если `hv30` недоступна (`null`), допускается подстановка `hv30_z := max(ATR_z_short, 1)` как грубая аппроксимация.

**Запрет двойного учёта basis в gap (обязательное).** В gap-модели запрещено использовать `basis_vol_z` как дополнительный множитель гэпа по умолчанию. Допускается включение отдельным флагом только при соблюдении условия отсутствия отдельного `basis_risk_mult`:

```text
if basis_gap_adjust_enabled and basis_risk_mult == 1:
  gap_frac = clip(gap_frac * (1 + gap_frac_basis_vol_sensitivity * max(basis_vol_z, 0)),
                  gap_frac_min, gap_frac_max)
```

* `sl_distance_frac = abs(entry_price - stop_loss) / max(entry_price, price_eps_usd)`

**Гэп-исполнение стопа (обязательное).** Формируется гэп-цена стопа:

* LONG: `sl_gap_price = stop_loss * (1 - gap_frac)`
* SHORT: `sl_gap_price = stop_loss * (1 + gap_frac)`

`sl_gap_eff_allin` вычисляется через EffectivePrices из `sl_gap_price` теми же правилами и bps-компонентами, что и `sl_eff_allin`.

```text
unit_loss_gap_allin = abs(entry_eff_allin - sl_gap_eff_allin)
gap_mult = unit_loss_gap_allin / max(unit_risk_allin_net, gap_unit_risk_eps)
```

Требование: в gap-модели запрещено применять дополнительный мультипликатор “overshoot”, если уже используется `sl_gap_price`.

##### 3.3.6.3. Leverage/Margin и буфер до ликвидации (обязательное)
Если торговля ведётся с плечом или через деривативы с механизмом ликвидации, вводится обязательная leverage-модель.

Определения:

* `leverage_effective` — эффективное плечо.
* `initial_margin_frac`, `maintenance_margin_frac` — доли маржи.
* `liq_price` — оценка цены ликвидации позиции.
* `liq_buffer_frac` — минимальный буфер до ликвидации:

```text
liq_buffer_frac >= liq_buffer_min + k_liq_vol*hv30 + k_liq_spread*(spread_bps/10000)
```

Требования:

* для LONG: `stop_loss >= liq_price * (1 + liq_buffer_frac)`
* для SHORT: `stop_loss <= liq_price * (1 - liq_buffer_frac)`
* при нарушении — вход запрещён (`liquidation_buffer_block`).

##### 3.3.6.4. Верхняя граница риска сделки (обязательное)
В GATE 12 используется `risk_pct_upper_bound`, гарантированно не увеличивающаяся далее по пайплайну:

```text
risk_pct_upper_bound = portfolio_state.risk.max_trade_risk_cap_pct
```

##### 3.3.6.5. Проверка одиночной сделки (обязательная, size-invariant)
```text
gap_loss_pct_equity_upper = risk_pct_upper_bound * gap_mult
gap_loss_pct_equity_upper <= max_gap_loss_pct_equity
```

При нарушении вход запрещён (`bankruptcy_gap_block_single`).

##### 3.3.6.6. Портфельный стресс-гэп (обязательное; единственная форма расчёта)
Формируется набор `S`:

* позиции текущего кластера инструмента,
* top-K позиций по `risk_amount_usd`,
* кандидатная позиция.

Для каждой позиции `p ∈ S`:

```text
gap_mult_p = unit_loss_gap_allin_p / max(unit_risk_allin_net_p, gap_unit_risk_eps)
gap_loss_pct_p = risk_pct_p * gap_mult_p
```

Для кандидатной позиции используется `risk_pct_upper_bound`.

**Матрица стресс-корреляций для S (обязательное).** Используется подматрица глобальной стресс-матрицы по инструментам из `S`:

* `C_stress_S` — подматрица `C_stress_global` на индексах инструментов S.
* Если для пары инструментов нет валидной оценки, корреляция задаётся консервативно как `+1`.

**Усиление корреляций при высокой хвостовой зависимости (обязательное).** Если `lambda_used >= stress_gap_lambda_unity_threshold`, то для всех `i≠j` в `C_stress_S`:

```text
C_stress_S[i,j] := +1
```

(после чего матрица нормируется/проектируется в PSD и `diag==1`).

**Сценарная оценка портфельного гэпа (обязательная).** Используется только корреляционная форма:

```text
G = vector(gap_loss_pct_p for p in S)
portfolio_gap_loss_pct_equity = sqrt(max(Gᵀ C_stress_S G, 0))
```

Требование:

```text
portfolio_gap_loss_pct_equity <= portfolio_max_gap_loss_pct_equity
```

---

### 3.4. Risk Reservation (обязательное, для параллелизма и целостности портфельных лимитов)
**Назначение.** Исключить гонки одновременных сигналов и обеспечить соблюдение лимитов при конкурентной обработке.

**Принцип.** Gatekeeper резервирует риск атомарно до отправки ордера; резерв снимается при отмене/таймауте; при первом fill конвертируется в “занятый” риск позиции.

**Буферы резервирования (обязательное).**

* `portfolio_risk_buffer_pct`
* `cluster_risk_buffer_pct`
* `heat_buffer_pct`

**Требование по буферу heat (обязательное).**

```text
heat_buffer_pct >= max_trade_risk_cap_pct
```

(либо ≥ верхней границы прироста риска, допускаемого параллельно одним инстансом; выбирается максимальное из двух).

#### 3.4.1. Данные резервирования
* `reservation_id` (UUID),
* `snapshot_id_used`,
* `instrument/cluster`,
* `reserved_risk_pct`,
* `reserved_cluster_risk_pct`,
* `reserved_sum_abs_risk_pct`,
* `reserved_heat_upper_bound_pct`,
* `expires_at_ts`,
* `lease_id`, `lease_renewal_deadline_ts`,
* `order_type` (maker/taker/stop).

**Скалярная верхняя оценка прироста heat (обязательное).**

```text
reserved_heat_upper_bound_pct := abs(reserved_risk_pct)
```

Эта величина используется как консервативный upper-bound для контроля гонок heat без матриц в Redis.

#### 3.4.2. Атомарность (обязательное)
Redis Lua “check-and-set” работает только для скалярных лимитов (включая `reserved_heat_upper_bound_pct` как upper-bound бюджетирования). Матричный heat проверяется внутри Gatekeeper на согласованном снапшоте и защищается `portfolio_id_used == current_portfolio_id_at_commit` (по `portfolio_state.portfolio_id`).

#### 3.4.3. TTL, Lease Renewal и снятие (обязательное)
* каждый резерв имеет TTL `reservation_ttl_sec`, зависящий от типа исполнения:

  * maker: `reservation_ttl_sec >= passive_fade_hard_timeout_sec` (и не меньше `reservation_ttl_sec_min_maker`)
  * taker: допускается меньше, но не меньше `reservation_ttl_sec_min_taker`
  * stop: не меньше `reservation_ttl_sec_min_stop`
* EXM продлевает “аренду” резерва только при активном ордере и при переходах конечного автомата EXM (heartbeat на переходах), а также по таймеру не чаще чем `reservation_renewal_min_period_sec`.
* если lease renewal не поступил до `lease_renewal_deadline_ts`, резерв считается истёкшим и снимается безопасно, а ордер переводится в режим повышенного контроля;
* по событиям `order_cancelled/timeout/preexec_failed` резерв снимается немедленно;
* по `first_fill` резерв фиксируется как “consumed” и переносится в портфельное состояние.

**Уточнения (добавлено при консолидации):**

* TTL зависит от типа исполнения (maker/taker/stop) и задан дефолтами Приложения C.
* EXM продлевает lease при активном ордере.
* Дополнительно вводится `reservation_heartbeat`:
  * период `reservation_heartbeat_period_ms` (конфиг),
  * если heartbeat отсутствует дольше `reservation_heartbeat_grace_ms`, резерв снимается досрочно (`reservation_heartbeat_lost_release_event`) и новые входы блокируются до стабилизации (DRP минимум `DEFENSIVE`) при частых повторах.
* При `order_cancelled/timeout/preexec_failed` резерв снимается немедленно.
* При `first_fill` резерв фиксируется как consumed и переносится в портфель.

#### 3.4.4. Two-phase commit на событиях fill и auto-reduce (обязательное)
При обработке fill выполняется:

1. `FillPhase-1`: EXM публикует событие fill с `reservation_id`, `snapshot_id_used`, `filled_qty`, `fill_price`.
2. `FillPhase-2` (commit): `PortfolioStateWriter` выполняет optimistic lock с retry:

```text
for attempt in 1..commit_retry_count:
  if snapshot_id_used compatible with current_snapshot_id:
      recalc_limits_on_latest_snapshot()
      if limits_ok: commit(); break
  refresh snapshot and retry
if commit_failed: trigger auto_reduce and DRP escalation
```

Если резерв истёк, но fill произошёл:

* событие `reservation_expired_fill_event` критично,
* немедленный `auto_reduce_to_limits`,
* DRP минимум `EMERGENCY`, запрет новых входов до ручного подтверждения.

---

**Уточнения (добавлено при консолидации):**

Two-phase commit и поведение при `reservation_expired_fill_event` — обязательны (включая auto-reduce и DRP `EMERGENCY`).

## 4. MARKET REGIME CLASSIFIER (MRC)
(структура раздела задана настоящим документом)

### 4.1. Режимы рынка
Классы (H1): `TREND_UP`, `TREND_DOWN`, `RANGE`, `BREAKOUT_UP`, `BREAKOUT_DOWN`, `NOISE`. Служебная метка: `NO_TRADE`.

### 4.2. Набор признаков (MRC Feature Set)
Фичи считаются на H1; все rolling-статистики обязаны использовать `.shift(1)` для исключения look-ahead bias. Источники: price/returns, тренд/диапазон, микроструктура (опционально), деривативы (funding/OI/basis/time-to-funding/ADL) со staleness-контролем.

**Уточнения (добавлено при консолидации):**

Нормализация, робастные окна, модель LightGBM multiclass, baseline dual-speed, гистерезис, retrain, drift, feature_schema_version и политика совместимости — обязательны.

### 4.2.1. Нормализация (robust)
Робастная нормализация через rolling median/IQR с клипом; eps — контекстный.

### 4.2.2. Робастные окна волатильности (обязательное)
Для краткосрочной волатильности и ATR вводится адаптивное окно:

```text
atr_window_short = max(atr_window_min, int(atr_window_base * max(1, ATR_z_long)))
```

Робастная дисперсия/стандартное отклонение вычисляются с winsorization (по умолчанию 1%/99%) либо trimmed-оценкой (конфиг). При обнаружении flash-crash паттерна допускается расширение окна до `atr_window_flash_cap`.

### 4.3. Модель MRC
* Тип: LightGBM multiclass (6 классов).
* Метрики: macro F1 по {TREND/RANGE/BREAKOUT} + контроль ошибок по NOISE.
* Дополнительно: cost-weighted метрика по матрице ошибок `confusion_cost_matrix` (конфиг).

### 4.4. Baseline MRC (rule-based, dual-speed)
Rule-based baseline на EMA/ADX/ATR-z и критериях диапазона/пробоя. Правила baseline версионируются и воспроизводимы.

**Dual-speed baseline (обязательное).**

* `ADX_slow` используется при `ATR_z_short <= baseline_adx_fast_switch_atr_z`,
* `ADX_fast` используется при `ATR_z_short > baseline_adx_fast_switch_atr_z`.

### 4.5. Гистерезис и фильтр уверенности
Смена режима требует устойчивости; параметры версионируются. При высокой волатильности допускается ускоренный режим переключения.

### 4.6. Обучение и защита от переобучения
Retrain: 2–4 недели. Контроль дрейфа: конфликты MRC vs baseline, калибровка вероятностей. Датасеты и фичи воспроизводимы по `dataset_version`.

**Версионирование схемы фич и совместимость (обязательное).**

* вводится `feature_schema_version`;
* каждая модель обязана объявлять `required_feature_schema_version` и `compatibility_policy`;
* слой обратной совместимости: при отсутствии новой фичи в старом снапшоте применяется `zero-fill` только для явно разрешённых optional-фич;
* классификация фич:

  * `required_features`: отсутствие любой → блок торговли `required_feature_missing_block`,
  * `optional_features`: отсутствие → подстановка `fallback_value` и снижение уверенности/риска.
* торговля запрещена при несовместимости схемы фич, приводящей к изменению смыслов (смена единиц/семантики): `feature_schema_incompatible_block`.

---

## 5. TREND ENGINE
Структура раздела включает, включая BREAKOUT-подрежим, подтверждение пробоя, SL/TP обязательны, re-entry ограничения и `reentry_risk_per_hour` — обязательны.

---

### 5.1. Условия активации
TREND активен при `final_regime ∈ {TREND_UP, TREND_DOWN}` и выполнении фильтров направления/волатильности/ликвидности и отсутствия DRP запретов.

**BREAKOUT-подрежим (обязательный).** При `final_regime ∈ {BREAKOUT_UP, BREAKOUT_DOWN}`:

* более строгие требования к DQS и ликвидности,
* ограничение `expected_holding_hours` вниз,
* снижение риска через `breakout_risk_mult`,
* отдельный `RR_min_breakout` (выше `RR_min_trend`),
* допускается повышенная срочность исполнения только при `data_quality_score >= dqs_degraded_threshold` и соблюдении ограничений taker-режима.

**Подтверждение пробоя (обязательное).** Вводится `breakout_confirmation_bars`:

* после первичного сигнала BREAKOUT система ожидает подтверждение в течение `breakout_confirmation_bars` (по умолчанию `ceil(0.5 × expected_holding_hours)` в H1-барах);
* если baseline вернулся в `RANGE` до подтверждения — сигнал отменяется (`breakout_false_break_cancel`).

### 5.2. Логика входа
Сигнал формируется детерминированно на H1 с возможным уточнением M15. Движок обязан сформировать корректные уровни входа/SL/TP и параметры `RR_min_engine`, `sl_min_atr_mult`, `sl_max_atr_mult`.

### 5.3. Price-chasing и тип ордеров
Правила chase и выбор maker/taker задаются параметрами и воспроизводимы в backtest через EXM-автомат.

### 5.4. Логика выхода
SL/TP обязательны. Emergency-выход при DRP `EMERGENCY` или ухудшении ликвидности. Выход по смене режима — по конфигу.

### 5.5. Повторные входы (re-entry)
Ограничения `reentry_max_count`, `reentry_window_hours`, запреты по DRP — обязательны.

**Ограничение ре-энтри по плотности риска (обязательное).**

```text
reentry_risk_per_hour = (sum(risk_pct_equity of reentries in window)) / max(reentry_window_hours, eps)
```

Если `reentry_risk_per_hour > reentry_risk_per_hour_cap` — блок новых re-entry до истечения окна.

---

## 6. RANGE ENGINE
Раздел включает исключение для NOISE при STRONG MLE и ограничении `ATR_z_short` — обязательна.

---

### 6.1. Условия активации
RANGE активен при `final_regime=RANGE` либо при устойчивом baseline-диапазоне, при контроле пробоев и отсутствии признаков разрушения диапазона.

#### 6.1.1. Исключение для NOISE (обязательное, ограниченное)
RANGE может торговать при `final_regime=NOISE` только если одновременно:

* `MLE.decision=STRONG`,
* `ATR_z_short < noise_range_atr_z_cap`,
* ликвидность и DQS не ниже порогов нормального режима,
* включён конфиг `allow_range_in_noise_strong_mle=True`.

Иначе `NO_TRADE`.

### 6.2. Направление сделок в диапазоне (правило зон)
Правило `band_dir` — обязательное; вне зон — `no_trade`.

### 6.3. Вход
Проверки funding/basis/net-RR/издержек выполняются Gatekeeper. Движок предоставляет уровни входа/SL/TP.

### 6.4. Выход
Stop-loss минимум 1R по `unit_risk_allin_net`. Take-profit — по конфигу. Breakout-выход при триггерах разрушения диапазона.

---

## 7. META-LABELING ENGINE (MLE)

### 7.1. Triple Barrier Method (price-net таргет)
Разметка выполняется по ценовому edge (без funding), нормированному на риск:

```text
R_price_net = PnL_price_net / denom_safe_signed(risk_amount, risk_amount_eps_usd)
```

Funding не включается в таргет и учитывается детерминированным фильтром Gatekeeper.

**Барьеры и горизонты (адаптивно, обязательное).**

Для каждого `engine ∈ {TREND,RANGE}` задаются:

* `TP_R`, `SL_R`,
* `T_min`, `T_max`,
* `success_frac`,
* `R_fail`.

```text
R_success = TP_R * success_frac
```

Доля `NEUTRAL` на стабильных режимах контролируется целевым диапазоном `≤ 20%`.

**Уточнения (добавлено при консолидации):**

Funding не включается в таргет.
Барьеры и горизонты — обязательны. Контроль доли `NEUTRAL` — обязателен.

#### 7.1.1. Meta-labeling на “stop-out by noise” и Vol-adjusted Stop (обязательное)
Вводится метка `STOP_OUT_NOISE`, отражающая вероятность выбивания по стопу шумом/виками до достижения TP.

**Vol-adjusted Stop (обязательное поведение).** Если `p_stopout_noise >= stopout_noise_expand_threshold`, система обязана предложить корректировку параметров сделки, не нарушая размеро-инвариантность:

* увеличить `SL_distance` до:

```text
SL_distance_new = SL_distance * stopout_sl_expand_mult
```

* одновременно уменьшить риск так, чтобы денежный риск (USD) не увеличился:

```text
qty_new = qty_old * (SL_distance_old / max(SL_distance_new, price_eps_usd))
```

* после корректировки уровни обязаны пройти GATE 11 и bankruptcy-check.

Если корректировка приводит к нарушению `unit_risk_min_atr_mult` или требований `net_RR`, вход отклоняется.

**Уточнения (добавлено при консолидации):**

Метка `STOP_OUT_NOISE` и поведение `Vol-adjusted Stop` — обязательны:
* уменьшение qty без увеличения денежного риска:
**Требование к обучению (обязательное).** В обучение MLE вводится фича:
* `ratio_sl_to_atr = SL_distance / max(ATR, atr_eps)`
  чтобы модель учитывала вариативность SL (включая post-prediction расширение).

### 7.1.2. EV-скоринг и решение MLE (price-edge, tail-guard)
Пусть `CVaR_fail_R(β)` рассчитан по `R_price_net` на окне калибровки. Используется хвостовой guard:

```text
mu_fail_used = min(mu_fail_R, CVaR_fail_R(β))
EV_R_price = p_success*mu_success_R + p_neutral*mu_neutral_R + p_fail*mu_fail_used
```

**Адаптивный выбор β (обязательное).**

```text
beta = clip(beta_base * tail_dependence_alpha / max(lambda_used, beta_lambda_eps), beta_min, beta_max)
```

Решение:

* `EV_R_price <= 0` → `REJECT`
* `0 < EV_R_price < e1` → `WEAK`
* `e1 ≤ EV_R_price < e2` → `NORMAL`
* `EV_R_price ≥ e2` → `STRONG`

Защитное правило нейтрали: если `p_neutral ≥ p_neutral_cutoff` и `|EV_R_price| < ev_near_zero_band` → `REJECT`.

Выход `mle_output` — обязательная структура (Приложение B).

**Уточнения (добавлено при консолидации):**

Формулы EV и хвостового guard — обязательны, включая адаптивный выбор β:

### 7.2. Фичи для MLE
**Требование к консистентности состояния (обязательное).** MLE строит фичи только на `portfolio_state`, который включает текущие позиции, резервы риска и **in-flight execution exposure** (экспозиции по ордерам в процессе исполнения). Запрещено формировать фичи MLE на состоянии без учёта in-flight экспозиции.

**Lagged корреляционные фичи (обязательное).** Любые фичи на корреляциях/β/хвостах, используемые MLE, обязаны быть лагированы минимум на 1 бар H1.
Фичи не должны дублировать MRC. Допускаются: контекст режима, характеристики сетапа, микроструктура исполнения, деривативы как контекст, портфельный контекст.

**Ожидаемые издержки: разделение pre/post MLE (обязательное).**

Вводятся два значения:

1. `expected_cost_R_preMLE` — считается до MLE консервативно при `p_fail=1`, `p_success=0`.
2. `expected_cost_R_postMLE` — считается после MLE с использованием `p_success/p_fail` текущего снапшота.

Правила использования:

* в GATE 5 вычисляется и логируется `expected_cost_bps` и `expected_cost_R_preMLE`;
* в sizing (GATE 14) используется `expected_cost_R_postMLE`; если MLE недоступен или `decision=REJECT`, используется `expected_cost_R_preMLE`.

**Запрет логического цикла (обязательное).** MLE использует `portfolio_state` строго с `snapshot_id_mle = snapshot_id_used - 1`. REM использует `mle_output` для текущего `snapshot_id_used`.

**Lagged корреляционные фичи (обязательное).** Любые фичи на корреляциях/β/хвостах, используемые MLE, обязаны быть лагированы минимум на 1 бар H1.

**Уточнения (добавлено при консолидации):**

* консистентность `portfolio_state` включая `execution_shadow` (in-flight exposure) — обязательна;
* lagged корреляционные фичи минимум 1 бар H1 — обязательны;
* запрет логического цикла: `snapshot_id_mle = snapshot_id_used - 1` — обязателен;
* разделение `expected_cost_R_preMLE` и `expected_cost_R_postMLE` — обязательное (структуры и формулы приведены в настоящем документе).

### 7.3. Модель и обучение
* Тип: CatBoost или LightGBM (версионируется).
* Метрики: Brier score, ECE, confusion.
* Калибровка вероятностей обязательна.
* Порог включения по стадиям: stage1/stage2/stage3 — обязательны.

**Онлайн-калибровка (обязательное).** На окне последних `mle_calibration_window_trades` выполняется обновление калибровки при соблюдении:

* `min_days_between_calibrations`,
* запрет калибровки при `data_quality_score < dqs_degraded_threshold`.

Цели:

* `ECE ≤ 0.10`,
* `Brier ≤ 0.20`.

**Фиксация методики reference-дистрибуции (обязательное).**

* Reference-распределение для drift/калибровки фиксируется как “первые `reference_days_after_training` дней после обучения”.
* Обновление reference допускается только при управляемом событии `model_recalibration_epoch` и сохраняется как версия.

---

**Уточнения (добавлено при консолидации):**

Калибровка вероятностей, мониторинг ECE/Brier и политика reference-дистрибуции — обязательны.

## 8. RISK & EXPOSURE MANAGER (REM)

### 8.1. DD-ladder, recovery-mode и hibernate-mode
Лестница максимального риска на сделку (до учёта множителей):

```text
dd ≤ 5%:       0.50%
5% < dd ≤10%:  0.50%
10%< dd ≤15%:  0.50%
15%< dd ≤25%:  0.40%
dd > 25%:      0.30% + recovery-mode
```

**Гистерезис dd (обязательный).** Используется сглаженный dd `dd_s = EMA(dd, dd_smooth_alpha)`.

**Recovery-mode (обязательное, управляемое).** Если `dd > dd_recovery_threshold_pct` и наблюдается улучшение на последнем окне, допускается ограниченный буст риска:

```text
recovery_risk_boost = clip(1 + (dd - dd_recovery_threshold_pct)/dd_recovery_span_pct, 1.0, recovery_risk_boost_cap)
dd_risk_max = dd_risk_max * recovery_risk_boost
```

Буст запрещён при `DRP_state != NORMAL` или при `tail_reliability_score < tail_recovery_min_reliability`.

**Kelly cap (обязательное, fractional + clip).**

```text
RR = Avg_Win_w / denom_safe_signed(Avg_Loss_w, R_eps)
Kelly_full = (WR_w × RR - (1 − WR_w)) / max(RR, RR_eps)
# где WR_w - взвешенный win rate, RR = Avg_Win_w / Avg_Loss_w
# Формула даёт оптимальную долю капитала для максимизации логарифма богатства
Kelly_frac = clip(Kelly_full * kelly_fraction, 0, kelly_cap_max)
```

**Условия применения Kelly (обязательное).** Kelly cap применяется только если:

* `trades_count_for_kelly ≥ kelly_min_trades`,
* `loss_trades_count ≥ kelly_min_loss_trades`,
* KPI валидны по правилам 2.1.1.3.

Иначе Kelly не применяется.

**Разделение Kelly и хвостового буфера (обязательное).** Kelly не должен дополнительно умножаться на `lambda_used`. Хвостовой буфер применяется отдельным множителем `tail_lambda_mult` в Sequential Risk.

**Публикация верхней границы риска (обязательное).** REM обязан вычислять и публиковать:

```text
max_trade_risk_cap_pct =
  min(
    dd_risk_max_after_hysteresis,
    max_trade_risk_hard_cap_pct,
    max(kelly_floor_pct, Kelly_frac_if_applicable)
)
```

Эта величина используется как `risk_pct_upper_bound` в bankruptcy-check.

**Hibernate-mode (обязательное).**

* если `allowed_risk < min_risk_floor_pct_by_tier` в течение `hibernate_trigger_n` последовательных оценок → `DRP_state=HIBERNATE` и запрет новых входов;
* выход из `HIBERNATE` возможен только после:

  * выдержки `hibernate_min_duration_sec`,
  * `allowed_risk ≥ min_risk_floor_pct_by_tier` в течение `hibernate_release_n`,
  * `data_quality_score ≥ dqs_degraded_threshold`.

**Уточнения (добавлено при консолидации):**

DD-ladder — обязательна. Гистерезис `dd_s = EMA(dd, dd_smooth_alpha)` — обязателен.
**Recovery-mode (обязательное, управляемое).** Буст риска допускается только при выполнении условий, включая `DRP_state == NORMAL` и достаточную `tail_reliability_score`.
**Жёсткий предохранитель recovery (обязательное).** Если:
dd_s >= dd_recovery_disable_threshold_pct
* `recovery_risk_boost := 1.0`,
* `DRP_state` переводится минимум в `DEFENSIVE`,
* логируется `recovery_disabled_by_drawdown_event`.
Дефолт `dd_recovery_disable_threshold_pct` задан в Приложении C (стартово 30%).
Kelly cap (fractional, clip), условия применения и публикация `max_trade_risk_cap_pct` — обязательны.

### 8.2. Корреляции, beta, tail-risk, tail-dependence, basis-risk и ADL-risk
Используются `Stress_beta`, `Tail_corr`, `lambda_used`, `tail_reliability_score`, `basis_*`, `ADL_rank_quantile`, а также индикатор стресс-смешивания корреляций.

**Определение `corr_stress_indicator` (обязательное).** Используется публикуемое `gamma_s` (из 2.3.3):

```text
corr_stress_indicator =
  clip((gamma_s - gamma_soft) / max(gamma_hard - gamma_soft, eps), 0, 1)
```

`gamma_soft/gamma_hard` — конфиг (Приложение C).

**corr_beta_mult (обязательное, монотонное).** Множитель в диапазоне `[corr_beta_mult_min, 1]`, падает при росте `|Stress_beta|`, `|Tail_corr|` и при снижении `tail_reliability_score`:

```text
beta_abs = abs(stress_beta_to_btc)
corr_abs = abs(tail_corr_to_btc)

t_beta = clip((beta_abs - beta_soft) / max(beta_hard - beta_soft, eps), 0, 1)
t_corr = clip((corr_abs - corr_soft) / max(corr_hard - corr_soft, eps), 0, 1)

beta_mult = 1 - (1 - corr_beta_mult_min) * t_beta^beta_power
corr_mult = 1 - (1 - corr_beta_mult_min) * t_corr^corr_power

reliability_mult = 1 - (1 - corr_beta_mult_min) * (1 - tail_reliability_score)

corr_beta_mult = min(beta_mult, corr_mult, reliability_mult)
```

**ADL-risk (обязательное).** Определяется множитель:

```text
adl_risk_mult =
  1,                  если q < adl_soft
  adl_risk_mult_soft, если adl_soft <= q < adl_hard
  0 (BLOCK),          если q >= adl_hard
```

При `q >= adl_hard`:

* блок новых входов,
* инициируется принудительное снижение экспозиции (`adl_emergency_reduce_event`),
* DRP минимум `EMERGENCY` при устойчивом сигнале.

**Динамическая переоценка существующих позиций при росте хвостов (обязательное).** При `lambda_used >= lambda_dynamic_recalc_threshold` REM пересчитывает риск и инициирует `reduce_existing_positions_to_limits` при нарушении лимитов.

**Crisis index (обязательное).**

```text
crisis_index = max(
  1 - tail_reliability_score,
  I[adl_rank_quantile >= adl_soft],
  corr_stress_indicator,
  I[DRP_state in {DEFENSIVE, EMERGENCY}]
)
```

При `crisis_index >= crisis_emergency_threshold` → запрет новых входов и DRP минимум `EMERGENCY`.

### 8.3. Portfolio Heat и кластерные лимиты
Обозначения:

* `risk_i` — риск позиции i в долях equity,
* `signed_risk_i = direction_sign_i * risk_i`,
* `R` — вектор signed_risk,
* `C_psd`, `C_blend` — PSD-матрицы корреляций (diag==1).

```text
H_C(R) = sqrt(max(Rᵀ C R, 0))
adjusted_heat_base   = H_{C_psd}(R)
adjusted_heat_blend  = H_{C_blend}(R)
adjusted_heat_worst  = max(adjusted_heat_base, adjusted_heat_blend)
```

**Heat-id (обязательное).** Любой расчёт heat обязан логировать:

```text
heat_calculation_id = {
  "matrix_used": "C_blend" if tail_reliability_score >= heat_blend_min_reliability else "C_psd",
  "corr_matrix_snapshot_id": corr_matrix_snapshot_id
}
```

**Runtime-assert (обязательное).**

```text
abs(C[j,j] - 1) < diag_eps  для всех j
```

---

**Уточнения (добавлено при консолидации):**

* `C_psd`, `C_blend` — PSD-матрицы (diag==1).
**Коллапс корреляций (обязательное).**
Heat-ограничения используют worst-case:
heat_worst_for_limits = max(adjusted_heat_worst, H_uni_abs)

#### 8.3.1. Soft/Hard Heat Limits (обязательное)
Вводятся два лимита:

* `H_soft = heat_soft_frac * H_max`
* `H_hard = H_max`

Правило:

* если `H_current > H_hard` → запрет новых входов, допускаются только сделки, уменьшающие heat, и инициируется `heat_hard_violation_event`;
* если `H_soft < H_current ≤ H_hard` → разрешаются только сделки, уменьшающие heat; любые “увеличивающие heat” сделки отклоняются (`heat_soft_block_increase`).

---

**Уточнения (добавлено при консолидации):**

Soft/hard правила — обязательны.

#### 8.3.2. Расчёт допустимого добавочного риска по heat (обязательный)
Для кандидата `j` с добавочным риском `x` (доля equity) и знаком `s ∈ {+1,-1}`:

```text
H(x)^2 = (R + s x e_j)ᵀ C (R + s x e_j) = x^2 + 2 b x + c
c = Rᵀ C R
u = (C R)_j
b = s * u
```

Условие `H(x) ≤ H_max` эквивалентно `x^2 + 2 b x + (c - H_max^2) ≤ 0`.

```text
disc = b^2 + H_max^2 - c
sqrt_disc = sqrt(max(disc, 0))
x_root_hi = -b + sqrt_disc
x_max = max(0, x_root_hi)
```

Случай `abs(b) < heat_b_near_zero_eps`:

```text
x_max = sqrt(max(H_max^2 - c, 0))
```

**Iterative halving при численном дрожании (обязательное).** Если `disc <= heat_disc_floor_eps`, но `c < H_max^2` в пределах допусков, применяется:

* `x_try` уменьшается в 2 раза до устойчивости или до `heat_min_step`,
* логируется `heat_limiting_factor = "discriminant_halving"`.

---

**Уточнения (добавлено при консолидации):**

Формулы `H(x)^2 = x^2 + 2bx + c` и решение квадратного неравенства — обязательны.
**Iterative halving (обязательное, с физическим ограничением минимального лота).** При численном дрожании:
* `x_try` уменьшается в 2 раза до устойчивости или до `heat_min_step`.
* Дополнительное условие выхода (обязательное): если `x_try` соответствует количеству ниже `lot_step_qty` (минимально исполнимое):
qty_try = (x_try * equity_usd) / max(unit_risk_allin_net, gap_unit_risk_eps)
if qty_try < lot_step_qty: stop halving; reject with heat_step_below_min_lot_block

#### 8.3.3. Forced Hedge и запрет перехеджа (обязательное)
**Определение “уменьшающей heat” сделки.** Требование: `b < 0` (строго).

**Forced Hedge режим (обязательное).** Если `H_current > H_hard`, разрешается только сделка, которая:

* имеет `b < -heat_forced_b_min`,
* проходит скалярные лимиты по портфелю/кластеру (с учётом буферов),
* гарантирует снижение heat не менее чем на `heat_min_reduction_bps`:

```text
x_opt = max(0, -b)
x_cap = min(hedge_opt_mult * x_opt, hedge_abs_cap_pct, remaining_cluster_risk, remaining_portfolio_risk)
x_force = choose_min_x_in_[0, x_cap] such that H_new <= H_current - heat_min_reduction_bps/10000
```

Если подходящего `x_force` нет — отказ `forced_hedge_not_effective_block`.

**Запрет перехеджа (обязательное).**

* `x_opt = max(0, -b)`
* `x_hedge_cap = min(hedge_opt_mult * x_opt, hedge_abs_cap_pct, remaining_cluster_risk, remaining_portfolio_risk)`
* если `b < 0`: `x_max := min(x_max, x_hedge_cap)`.

---

#### 8.3.4. Сценарий корреляционного коллапса (обязательное)
Дополнительно вычисляется лимит при “единичной корреляции без кредита за хедж”:

```text
H_uni_abs = sum(abs(R))
x_max_uni_abs = max(0, H_max - H_uni_abs)
```

Итоговый допустимый добавочный риск по heat:

```text
remaining_heat_limits = min(
  x_max(C_psd),
  x_max(C_blend),
  x_max_uni_abs
)
```

---

### 8.4. Модель комиссий, проскальзывания и impact и единый расчёт risk_amount
Cost-модель поддерживает: maker/taker комиссии (bps), проскальзывание входа/выхода (bps), impact (bps), усиление стоп-проскальзывания.

**Уточнения (добавлено при консолидации):**

Impact и двухфазная оценка — обязательны.

#### 8.4.1. Impact: определение `impact_bps_est` (обязательное)
Если L2 доступен:

* симуляция VWAP по стакану на момент решения на объём `notional_candidate`,
* `impact_bps_est = 10000 * abs(vwap_price - mid_price) / max(mid_price, price_eps_usd)` с направлением.

Если L2 недоступен:

* `impact_bps_est = impact_k * (notional_candidate / max(depth_usd, depth_eps))^impact_pow`.

**Двухфазная оценка impact (обязательное).**

* Фаза 1 (pre-sizing): оценка `impact_bps_phase1` для верхней границы риска.
* Фаза 2 (sizing): impact может обновляться, но не может быть ниже `impact_bps_phase1` без подтверждения улучшения ликвидности.

#### 8.4.2. Sizing: аналитический (предпочтительный) и итеративный (fallback) (обязательное)
**Требование (обязательное).** Для Tier 1 допускается итеративный sizing; для Tier 2/3 обязателен аналитический или root-finding (1–2 шага) на калиброванной модели `impact_bps = a * qty^b`.

**Уточнения (добавлено при консолидации):**

Tier 1 допускает итеративный sizing; Tier 2/3 — аналитический или root-finding.

##### 8.4.2.1. Sizing solver и разделение risk-пайплайна (fixed-point / Newton-Raphson) (обязательное)
Sizing решает задачу `risk_pct_equity_actual(qty) = risk_target_for_sizing` с учётом impact, ликвидности и дискретности лота.

**Запрет двойного применения liquidity_mult (обязательное).** Разделяются величины:

* `risk_pre_liquidity` — риск после шагов 1–10 REM (без применения `liquidity_mult`),
* `risk_target_for_sizing = risk_pre_liquidity * liquidity_mult`,
* `risk_after_sizing = realized_risk_after_rounding` — источник истины.

Запрещено применять `liquidity_mult` одновременно внутри REM и внутри sizing к одной и той же цели без явного разделения этих переменных; нарушение — `double_liquidity_mult_detected_event` и блок.

**Fixed-point с адаптивной α (обязательное).**

* базовая релаксация:

```text
qty_{k+1} = (1 - alpha_fp) * qty_k + alpha_fp * qty_hat
```

* адаптация при осцилляции (обязательное):

  * если `sign(qty_k - qty_{k-1})` меняется → `alpha_fp := alpha_fp / 2` (halving),
  * `alpha_fp` не может быть ниже `alpha_fp_min`,
  * событие `sizing_alpha_halved_event`.

**Newton-Raphson (обязательное к поддержке, включается по конфигу).** Если функция `risk(qty)` дифференцируема или аппроксимируется, допускается метод Ньютона:

```text
qty_{k+1} = qty_k - F(qty_k)/max(F'(qty_k), newton_deriv_floor)
```

При неустойчивости или выходе за допустимые границы выполняется fallback на fixed-point.

**GATE 13.5: Convergence Feasibility Check (обязательное).** Перед запуском итераций sizing:

* если `liquidity_mult < liquidity_min_convergence_threshold` → применяется `risk_target_for_sizing *= sizing_low_liquidity_cap_mult` и ограничение `qty` по безопасной верхней границе;
* если `impact_bps_est > max_acceptable_impact_bps` → `risk_target_for_sizing *= sizing_high_impact_cap_mult`;
* событие `sizing_feasibility_cap_event`.

**Несходимость (обязательное).** Если после `max_sizing_iters`:

* `|risk_actual - target| > convergence_tol` или осцилляция не устранена,
  то применяется `sizing_not_converged_risk_cap_mult`, логируется `sizing_not_converged_event`.

---


**Размеро-инвариантные единицы (обязательное).**

* `entry_price_ref = max(entry_price, price_eps_usd)`
* `unit_risk_bps = 10000 * unit_risk_allin_net / entry_price_ref`

**expected_cost_R_preMLE (обязательное).**

```text
expected_cost_bps_pre =
  entry_cost_bps +
  1.0 * sl_exit_cost_bps
expected_cost_R_preMLE = expected_cost_bps_pre / max(unit_risk_bps, unit_risk_bps_eps)
```

**expected_cost_R_postMLE (обязательное).**

```text
expected_cost_bps_post =
  entry_cost_bps +
  p_success * tp_exit_cost_bps +
  p_fail    * sl_exit_cost_bps
expected_cost_R_postMLE = expected_cost_bps_post / max(unit_risk_bps, unit_risk_bps_eps)
```

**Ранний выход при отрицательном net-edge (обязательное).**

```text
net_edge_R_after_cost = EV_R_price - expected_cost_R_postMLE - funding_cost_R
if net_edge_R_after_cost < net_edge_floor_R:
    REJECT (или qty=0 по политике)
```

---

**Уточнения (добавлено при консолидации):**

Fixed-point с демпфированием и halving `alpha_fp` — обязательны. Newton — опционален по конфигу.
* `|risk_actual - target| > convergence_tol` или осцилляция не устранена:
  * применяется `sizing_not_converged_risk_cap_mult`,
  * логируется `sizing_not_converged_event`.
**Выбор qty при несходимости (обязательное).** При несходимости выбирается:
qty_final = min(qty_k over all iterations that produced valid, finite risk estimates)
(консервативно; запрещено брать “последнюю” осциллирующую точку по умолчанию).

### 8.5. Sequential Risk Algorithm (полная спецификация множителей)
Функция возвращает `position_risk_pct_target`, `rejection_reason` и диагностику.

**Уточнения (добавлено при консолидации):**

Порядок шагов 1–18 — обязателен.

#### 8.5.1. Порядок (обязательное)
1. DRP/блокировки → риск = 0
2. MLE: `REJECT` → риск=0; иначе `risk_mult_MLE`
3. DD-ladder → `dd_risk_max`
4. Kelly cap (если применим) → ограничение `dd_risk_max` (без множителей хвоста)
5. `base_risk = min(dd_risk_max, Kelly_cap_if_any, max_trade_risk_hard_cap_pct) * risk_mult_MLE`
6. Tail/λ-буфер: `tail_lambda_mult` (отдельно от Kelly)
7. `corr_beta_mult`
8. `funding_risk_mult` и `funding_proximity_mult`
9. `basis_risk_mult`
10. `adl_risk_mult`
11. `liquidity_mult`
12. `dqs_mult`
13. `defensive_mult` (DRP/MLOps)
14. `sizing_mult`
15. Комбинация мультипликаторов (монотонная, анти-каскад)
16. Портфельные лимиты: риск/кластер/heat (включая soft/hard и forced-hedge)
17. Risk floor и hibernate
18. Пост-фактум: фактический риск после sizing/округлений — источник истины

#### 8.5.2. Определения множителей (обязательное)
**tail_lambda_mult (обязательное).** Плавный хвостовой буфер:

```text
t = clip((lambda_used - tail_lambda_soft) / max(tail_lambda_hard - tail_lambda_soft, 1e-9), 0, 1)
tail_lambda_mult = 1 - (1 - tail_lambda_mult_min) * t
```

**defensive_mult (обязательное).**

```text
DRP_mult:    NORMAL=1, DEGRADED=0.85, DEFENSIVE=0.70, RECOVERY=0.60, EMERGENCY=0, HIBERNATE=0
MLOps_mult:  OK=1, WARNING=0.85, CRITICAL=0
defensive_mult = min(DRP_mult, MLOps_mult)
```

**liquidity_mult (обязательное).** Плавная деградация между soft/hard порогами:

```text
spread_mult = clip((max_spread_hard - spread_bps)/(max_spread_hard - max_spread_soft), 0, 1)
impact_mult = clip((max_impact_hard - impact_bps_est)/(max_impact_hard - max_impact_soft), 0, 1)
liquidity_mult = min(spread_mult, impact_mult)
```

Hard-отказы остаются hard-gates в Gatekeeper.

**sizing_mult (обязательное).** Если sizing не сошёлся — применяется `sizing_not_converged_risk_cap_mult`; иначе 1.

**Уточнения (добавлено при консолидации):**

* `tail_lambda_mult`, `defensive_mult`, `liquidity_mult`, `sizing_mult` — обязательны (формулы приведены в настоящем документе).
* `corr_beta_mult` — обязателен (формула задана в 8.2).
* `adl_risk_mult` — обязателен (формула задана в 8.2).
* `dqs_mult`, `funding_risk_mult`, `funding_proximity_mult`, `basis_risk_mult` — обязательны.

#### 8.5.3. Комбинация мультипликаторов (обязательное)
Все множители `m_i ∈ [0,1]` группируются:

* Market cluster: `tail_lambda_mult`, `corr_beta_mult`, `funding_risk_mult`, `funding_proximity_mult`, `basis_risk_mult`, `adl_risk_mult`
* Ops/Infra cluster: `liquidity_mult`, `dqs_mult`, `defensive_mult`, `sizing_mult`

**Активность множителя (обязательное, сглаженное).**

```text
active_strength(m) = clip(((1 - m) / max(1 - mult_active_threshold, 1e-9)) ^ mult_active_power, 0, 1)
effective_count = Σ active_strength(m_i)
min_mult = min(m_i)
```

Кластерная агрегация:

```text
combined_cluster =
  if effective_count <= 1:
      min_mult
  else:
      min_mult * stacking_penalty_base ** (effective_count - 1)
```

Итоговый множитель:

```text
combined_mult_total = 2 * combined_market * combined_ops / max(combined_market + combined_ops, mult_eps)
```

Требование: логировать `min_mult`, `effective_count`, `combined_market`, `combined_ops`, `combined_mult_total`, `limiting_factor`.

---

**Уточнения (добавлено при консолидации):**

Кластерная агрегация с `active_strength`, `effective_count`, `stacking_penalty_base`, итоговое гармоническое объединение — обязательны. Логирование limiting_factor — обязательное.

## 9. EXECUTION MODULE (EXM)
Структура раздела включает: семантика исполнения, latency/staleness, OBI и детектор мнимой ликвидности, gap/glitch, конечный автомат, partial fills, orphan sweep.

**Orphan Order Sweep (обязательное).** При рестарте/разрыве WS:

1. REST snapshot активных ордеров/позиций,
2. синхронизация `execution_shadow` и `portfolio_state`,
3. ордера без `reservation_id` → `orphan_order_detected_event`, отмена или режим “только снижение риска”,
4. запрет новых входов до завершения sweep (`orphan_sweep_in_progress_block`).

---

### 9.1. Execution semantics
Поддерживаются лимитные ордера с timeout и chase, taker-ордера в строгих условиях, partial fills, TWAP/VWAP.

### 9.2. Latency и staleness
* задержка от закрытия H1 до отправки ордера: целевой бюджет соответствует архитектурным требованиям раздела 3;
* staleness для EXM: 200–500 ms норм; 500–1000 ms допустимо с штрафом; >1000 ms — отказ или `DEGRADED`.

### 9.3. Liquidity integrity: OBI и детектор мнимой ликвидности (обязательное)
Метрики:

* `OBI = (bid_vol_1pct - ask_vol_1pct) / max(bid_vol_1pct + ask_vol_1pct, obi_eps)`
* `depth_mean = mean(depth_usd over window)`
* `depth_sigma = std(depth_usd over window)`
* `depth_volatility_cv = depth_sigma / max(depth_mean, depth_vol_eps)`  (**обязательное**)
* `spoofing_suspected = I[depth_volatility_cv > depth_volatility_threshold]`

Правила hard/soft блокировок и влияние на `liquidity_mult` обязательны.

### 9.4. Gap handling и data glitch detection
Контроль аномалий и выставление `suspected_data_glitch`, инициирующее DRP.

### 9.5. EXM как конечный автомат (обязательное, изоморфность live/backtest)
Состояния/события/переходы — обязательны, детерминизм обязателен. Запрет торговли при `trading_mode != LIVE` обязателен на уровне коннектора.

### 9.6. Partial fill economics (обязательное, адаптивные таймауты и пересчёт риска)
После первого fill:

* `fill_frac = filled_qty / target_qty`
* `min_fill_qty = max(min_fill_frac_to_hold * target_qty, min_notional_usd / max(entry_price, price_eps_usd))`

**Пересчёт фактического риска после каждого fill (обязательное).**

```text
risk_amount_usd_actual = abs(entry_eff_allin_avg_fill - sl_eff_allin) * filled_qty
risk_pct_equity_actual = risk_amount_usd_actual / max(equity_before, pnl_eps_usd)
```

**Adaptive fill abandonment (обязательное).**

Определения:

* `unit_risk_bps = 10000 * unit_risk_allin_net / max(entry_price_ref, price_eps_usd)`
* `impact_R_remaining = (impact_bps_est * (1 - fill_frac)) / max(unit_risk_bps, unit_risk_bps_eps)`

Порог отмены остатка:

```text
abandon_threshold_R = max(
  net_RR * fill_abandonment_rr_frac,
  min_abandon_R,
  abandon_threshold_min_bps / max(unit_risk_bps, unit_risk_bps_eps)
)
```

(по умолчанию `abandon_threshold_min_bps = 0.10`, что эквивалентно нижней границе “10% от unit_risk_bps” в R).

Если `impact_R_remaining > abandon_threshold_R`, остаток ордера отменяется (`fill_abandon_event`), позиция фиксируется в текущем объёме либо закрывается по политике риска.

`passive_fade_timeout_sec` адаптивен:

```text
passive_fade_timeout_sec = clip(passive_fade_base_timeout_sec / max(ATR_z_short, 1), passive_fade_timeout_min_sec, passive_fade_timeout_max_sec)
```

Жёсткий таймаут обязателен.

#### In-flight exposure и Orphan Order Sweep (обязательное)
Коммит partial fills обязателен в пределах `fill_commit_deadline_ms`, иначе используется `execution_shadow` и срабатывают ограничения GATE 8a.

**Adaptive fill abandonment (обязательное).**

```text
abandon_threshold_R = max(
  abs(net_RR) * fill_abandonment_rr_frac,
  min_abandon_R,
  abandon_threshold_min_bps / max(unit_risk_bps, unit_risk_bps_eps)
)
```

**Orphan Order Sweep (обязательное).** При рестарте EXM/Writer или при детекте разрыва WebSocket:

1. выполняется REST snapshot активных ордеров/позиций на бирже;
2. синхронизируется `execution_shadow` и `portfolio_state`;
3. ордера без локального `reservation_id` помечаются `orphan_order_detected_event` и:

   * либо отменяются (если политика разрешает),
   * либо переводятся в режим «только уменьшение риска» с ручной эскалацией;
4. до завершения sweep новые входы запрещены (`orphan_sweep_in_progress_block`).

---

### 9.7. Urgency Score (обязательное; фиксированная формула и запреты)
Вводится `urgency_score ∈ [0,1]`:

```text
decision_strength = 0 for REJECT, 1 for WEAK, 2 for NORMAL, 3 for STRONG
is_breakout = I[final_regime in {BREAKOUT_UP, BREAKOUT_DOWN}]

urgency_score = clip(
  w1 * (decision_strength / 3) +
  w2 * is_breakout +
  w3 * (1 - data_quality_score) +
  w4 * min(impact_bps_est / max_acceptable_impact_bps, 1) +
  w5 * min(spread_bps / max_acceptable_spread_bps, 1) +
  w6 * min(ATR_z_short / urgency_atr_z_cap, 1),
  0, 1
)
```

**Запрет taker при плохих данных (обязательное).** Taker-исполнение запрещено, если:

* `data_quality_score < dqs_degraded_threshold`, или
* `DRP_state != NORMAL`, или
* `MLOps_state != OK`.

---

## 10. MLOPS MONITORING
Дрейф фич (PSI/KS), дрейф качества моделей (proxy F1, Brier/ECE), мониторинг конфликтов, логирование решений и критических событий — обязательны.

---

### 10.1. Feature drift
PSI, KS-test. Пороги и действия — обязательны. Reference-дистрибуция фиксируется по правилам раздела 7.3.

### 10.2. Model performance drift
Мониторинг proxy F1 (MRC), Brier/ECE (MLE), конфликтов MRC vs baseline, доли `INSUFFICIENT_SAMPLE`, доли сделок, исключённых по микро-риску в KPI.

### 10.3. Calibration monitoring
Цели: `ECE ≤ 0.10`, `Brier ≤ 0.20`.

### 10.4. Логирование
Логируются решения Gatekeeper, вероятности MRC/MLE, состояния DRP/MLOps, фактический риск, округления лота и цены, tail-метрики, матрицы корреляций и heat-id, события резервирования риска и lease renewal, события качества данных, события toxic-flow, события forced-hedge.

Требование: некритичные логи записываются асинхронно (очередь/батчи), чтобы исключить I/O bottleneck.

---

## 11. MODEL VERSIONING, SHADOW MODE & A/B TESTING
Версионирование, SHA256-проверка целостности, grace period, shadow-mode и rollback — обязательны.

**Ограничение на grace period (обязательное).** В период допуска 2 активных хеша:

* A/B-тесты запрещены,
* `defensive_mult` ограничивается сверху `grace_period_defensive_cap_mult` (конфиг),
* логируется `grace_period_safety_cap_event`.

---

### 11.1. Версионирование
Каждая модель MRC и MLE имеет `model_id`, `training_dataset_version`, `feature_schema_version`, `training_time_utc`, `calibration_version`, `metrics_snapshot`, `artifact_sha256`.

**Проверка целостности артефактов (обязательное).** При загрузке сравнивается SHA256. При несовпадении:

* `MLOps_state := CRITICAL`,
* блокируются все новые ордера (`model_hash_mismatch_circuit_breaker`),
* `DRP_state` минимум `EMERGENCY`.

**Grace period для роллинг-обновлений (обязательное).** Вводится `deployment_epoch_id` и окно `model_hash_grace_period_sec`, допускающее 2 активных хеша при соблюдении политики.

### 11.2. Shadow mode
Shadow mode выполняет inference и запись прогнозов; торговые действия запрещены на уровне коннектора. Gatekeeper ограничивает вычисления по правилу раздела 3.1.2.

### 11.3. A/B testing
Разрешено только при DRP `NORMAL`, стабильных данных и ограниченном риске.

### 11.4. Rollback
Rollback атомарен, совместим по схемам фич, фиксируется в логах и мониторинге.

---

## 12. DISASTER RECOVERY PROTOCOL (DRP) И ДЕГРАДАЦИЯ
Состояния, приоритеты, триггеры EMERGENCY_EXIT, flash crash, depeg auto-exit, LIQUIDATE_OPTIMAL — обязательны.

---

### 12.1. Типы отказов
Exchange API failure, сбои ML, silent data corruption, depeg, flash crash/ликвидность, compounding-domain violation, деградация DQS, reservation-expired fill, ADL critical, forced-hedge режим.

### 12.2. DRP как конечный автомат (обязательное)
Состояния: `NORMAL`, `DEGRADED`, `DEFENSIVE`, `EMERGENCY`, `RECOVERY`, `HIBERNATE`.

Приоритет:

```text
EMERGENCY > HIBERNATE > RECOVERY > DEFENSIVE > DEGRADED > NORMAL
```

### 12.3. Emergency exit check (обязательное)
Триггеры `EMERGENCY_EXIT`: спред, глубина, `data_quality_score = 0`, depeg, API критика, compounding violation, hash mismatch circuit breaker, reservation-expired fill, ADL critical. Действия: отмена pending, `EMERGENCY`, EXM→`EMERGENCY_EXIT`.

### 12.4. Flash crash и динамическая корректировка impact
При схлопывании глубины увеличивается `impact_multiplier`; при превышении `max_acceptable_impact_bps` новые входы запрещаются.

### 12.5. Stablecoin depeg response (автоматизация обязательна)
**Детектор depeg (обязательное).** Вводятся:

* `depeg_dev_frac = abs(stable_price - 1.0)`,
* `depeg_duration_sec` — длительность превышения порога.

Состояния: `DEPEG_WARNING`, `DEPEG_CRITICAL`.

**Автоматический выход (обязательное).** Если `depeg_duration_sec > depeg_auto_exit_threshold_sec` или `depeg_dev_frac > depeg_critical_frac`, система обязана:

* перевести DRP в `EMERGENCY`,
* закрыть все позиции по политике TWAP:

  * `depeg_exit_twap_duration_sec`,
  * лимиты на impact/spread,
* логировать `depeg_auto_exit_event` и публиковать метрику `depeg_exposure_usd`.

**Режим LIQUIDATE_OPTIMAL (обязательное).** При массовой ликвидации порядок закрытий выбирается так, чтобы минимизировать мгновенный Heat: на каждом шаге выбирается позиция, закрытие которой максимизирует снижение `adjusted_heat_worst`.

---

## 13. WFO, BACKTESTING И MONTE CARLO
Backtest имитирует live (Gatekeeper/REM/EXM/EffectivePrices/DQS/DRP/rounding/partial fills), WFO и Monte Carlo ≥1000 прогонов со стрессами хвостов, корреляционного коллапса и качества данных — обязательны.

---

### 13.1. Правила исполнения в backtest
Backtest имитирует live: та же логика Gatekeeper/REM/EXM, те же cost-модели и EffectivePrices, staleness/shift(1), partial fills, chase, TWAP/VWAP, одинаковые правила округления лотов и цены, DQS/DRP hard-gates, корреляционные матрицы по снапшотам, reservation-логика моделируется эквивалентно (скалярные лимиты + optimistic commit + retry).

### 13.2. Walk-Forward Optimization (WFO)
IS/OOS, ограничения `tuning_budget`, запрет оптимизации по невалидным KPI.

### 13.3. Monte Carlo-симуляции
1000+ прогонов, стресс хвостов, стресс корреляционного коллапса, стресс микроструктуры, сценарии качества данных и ML drift, обязательная проверка `mean(ln(1+r))`, портфельный стресс-гэп, сценарии reservation race и auto-reduce, сценарии forced-hedge.

---

## 14. SOFTWARE STACK
Python 3.11; LightGBM/CatBoost; PostgreSQL/Parquet; Redis; primary + hot-standby; внешние конфиги/секреты.

**Детерминизм чисел (обязательное требование реализации).**

* критические расчёты выполняются в `float64` с IEEE-754 совместимостью;
* для цен/лотов допускается фиксированная точность (decimal или фикс-поинт) по конфигу, если это требуется для бит-в-бит воспроизводимости между средами.

---

### 14.1. Основной стек
Python 3.11; LightGBM/CatBoost; PostgreSQL/Parquet; Redis; primary + hot-standby; внешние конфиги/секреты.

**Высокопроизводительный контур (обязательное требование интерфейса).** Gatekeeper допускается реализовать как отдельный сервис/ядро на компилируемом языке (например, Rust/C++), при этом входные/выходные контракты, схемы снапшотов и детерминизм должны оставаться идентичными контрактам данного ТЗ.

### 14.2. Tiered Architecture и микроструктура
Tier 1 допускает монолит; Tier 2/3 — микросервисы и расширенные L2/тик.

### 14.3. Резервное хранение моделей и данных
S3-совместимое хранилище, `metadata.json` (SHA256), зависимости.

---

## 15. ЭТАПЫ ВНЕДРЕНИЯ
Data & Infrastructure → MVP → Shadow/Forward/Nano-live → Full System.

Состав Data & Infra включает: `RiskUnits`, `EffectivePrices`, DQS/hard-gates, publisher матриц корреляций (PSD вне hot path, публикация `gamma_s`), Single Writer, Risk Reservation (скаляры + буферы + heartbeat), in-flight exposure и orphan sweep, property-based тесты монотонности множителей и лимитов.

---

### 15.1. Data & Infra
Data-pipeline, staleness, hard-gates и DQS, кросс-валидация источников и sanity-check оракул, БД/логи/мониторинг, PSD/стресс-матрицы (асинхронная публикация + max age), Single Writer, Risk Reservation (скаляры + буферы + адаптивный TTL), EffectivePrices, leverage/margin модель.


Дополнительно в состав Data & Infra **обязательно** включить:

* `RiskUnits` и `FinancialTransforms` (конверсия риска/издержек в R и USD)
* Feature Store Consistency тесты и детерминированный replay engine
* Publisher матриц корреляций и fast-stress контур (PSD + кэширование, вне hot path)
* Risk Reservation + OCC (optimistic concurrency control) для шардированных лимитов
* In-flight exposure (`execution_shadow`) и Orphan Order Sweep
* Property-based тесты монотонности риск-множителей и лимитов

### 15.2. MVP
TREND, baseline, базовый REM, EXM без MLE, backtest+WFO.

### 15.3. Shadow/Forward-test и Nano-live
Shadow/paper/nano-live; калибровка порогов, проверка DRP/DQS warm-up, сбор датасета MLE.

### 15.4. Full System
Полноценные MRC/MLE, RANGE, расширенный DRP/MLOps, A/B, forced-hedge, постепенное увеличение капитала.

---

## 16. КРИТЕРИИ ДОПУСКА К FULL LIVE
KPI net-of-costs на основе all-in EffectivePrices и equity-таймсерии; требования по WFO/backtest/MC, forward ≥ 6–9 месяцев, минимальные сделки ≥ 80/год, производительность gatekeeper, тесты DRP/DQS, восстановимость backup/restore — обязательны.

---

### 16.1. Определения KPI (обязательные)
Все KPI считаются net-of-costs и используют all-in EffectivePrices/`unit_risk_allin_net` для нормировки R-метрик. Источник истины для Sharpe/MaxDD/CAGR/Calmar — equity-таймсерия.

* Таймзона: UTC.
* Дневные log-доходности: `g_t = ln(Equity_t / Equity_{t-1})` (с доменным контролем).
* Sharpe: `mean(g_t)/std(g_t)*sqrt(365)` (ddof=1).
* CAGR: `(Equity_end/Equity_start)^(365/days) - 1`.
* MaxDD: `max_t (1 - Equity_t / peak(Equity_≤t))`.
* Calmar: `CAGR / max(MaxDD, calmar_eps)`.

### 16.2. Требования к тестам и результатам
* WFO/backtest/Monte Carlo:

  * `PF_money ≥ 1.3` (VALID),
  * Sharpe ≥ 0.6–0.8 (VALID),
  * MaxDD ≤ 30% в базовых тестах,
  * положительный `mean(ln(1+r))` в OOS и по Monte Carlo,
  * контроль `variance_drag_annual` в допустимых пределах,
  * отсутствие систематических нарушений домена `log(1+r)`,
  * прохождение stress-gap (одиночный и портфельный),
  * прохождение leverage buffer условий,
  * прохождение тестов reservation lease renewal, expiration-fill и auto-reduce, commit-retry,
  * прохождение forced-hedge сценариев.
* forward (paper+nano) ≥ 6–9 месяцев: сопоставимые KPI, частота сделок, доли отказов Gatekeeper, отсутствие частых несходимостей sizing в нормальных режимах.
* минимальное число сделок: ≥ 80/год.
* производительность:

  * `gatekeeper_latency_p99_ms` соответствует требованиям раздела 3,
  * `reservation_success_rate` и `reservation_conflict_rate` в пределах политик мониторинга,
  * `sizing_iters_avg` не превышает порога предупреждения.
* DRP/DQS: протестированы сценарии API failure, crash recovery, liquidity emergency, depeg auto-exit, деградация DQS/hard-gates, warm-up, анти-флаппинг.
* Gatekeeper: причины отказов воспроизводимы, проходит набор математических автотестов (Приложение C).
* Backup/restore: проверена восстановимость БД/моделей и воспроизводимая инициализация.



**Обязательный набор автотестов и проверок релизного допуска:**

* не менее 50 тестов на инварианты и гонки (risk reservation, partial fills, DRP-state, snapshot consistency, deterministic replay);
* проверка compounding domain: запрет `r ≤ -1 + eps` и переход в `EMERGENCY` при нарушении;
* in-flight exposure: новые входы не превышают лимиты при задержках коммита, корректная работа `execution_shadow`;
* anti-flapping: достижение порога приводит к `HIBERNATE` и корректному возврату;
* shadow safety: `SHADOW` завершает после гейтов до исполнения, `SHADOW_FULL` проходит все гейты без отправки ордеров;
* Lamport/logical clock: монотонность и трассируемость событий;
* Oracle stale: stale оракул не снижает риск при малом `xdev_bps`, и postfact блокирует следующий сигнал при нарушении;
* Risk Reservation FSM: `RESERVE → (COMMIT|CANCEL|EXPIRE)` идемпотентна по `reservation_id`, инвариант `current + reserved + inflight` не превышает лимиты;
* Orphan Order Sweep: восстановление in-flight состояния после рестарта и запрет новых входов до завершения sweep;
* property-based тест: ухудшение DQS / рост `lambda_used` / рост `abs(beta)` / рост `corr_matrix_age_sec` не увеличивает риск.

---

## Приложение A: СХЕМЫ ПРОЦЕССОВ И EFFECTIVEPRICES

### A.1. Sequential Risk + Gatekeeper (схема)
```text
[Signal]
 → [GATE 0..6 size-invariant]
 → [Liquidity]
 → [In-flight exposure]
 → [Gap/glitch]
 → [Funding/Basis]
 → [EffectivePrices sanity + net-RR]
 → [Bankruptcy + liquidation]
 → [REM multipliers + heat/limits]
 → [Sizing feasibility]
 → [Sizing]
 → [Reservation]
 → [EXM state machine]
 → [Partial fills + in-flight exposure + abandonment]
```

### A.2. EffectivePrices (обязательное: детерминированные формулы LONG/SHORT)
`b(x_bps)=x_bps/10000`. Входные bps-компоненты: `spread_bps` (half-spread `0.5*spread_bps`), `fee_entry_bps`, `fee_exit_bps`, `slippage_*`, `impact_*`, `stop_slippage_mult`.

**LONG**

```text
entry_eff_allin = entry * (1 + b(0.5*spread_bps + slippage_entry_bps + impact_entry_bps + fee_entry_bps))
tp_eff_allin    = tp    * (1 - b(0.5*spread_bps + slippage_tp_bps    + impact_exit_bps  + fee_exit_bps))
sl_eff_allin    = sl    * (1 - b(0.5*spread_bps + stop_slippage_mult*slippage_stop_bps + impact_stop_bps + fee_exit_bps))
```

**SHORT**

```text
entry_eff_allin = entry * (1 - b(0.5*spread_bps + slippage_entry_bps + impact_entry_bps + fee_entry_bps))
tp_eff_allin    = tp    * (1 + b(0.5*spread_bps + slippage_tp_bps    + impact_exit_bps  + fee_exit_bps))
sl_eff_allin    = sl    * (1 + b(0.5*spread_bps + stop_slippage_mult*slippage_stop_bps + impact_stop_bps + fee_exit_bps))
```

---

## Приложение B: СТРУКТУРЫ ДАННЫХ
Все структуры сериализуемы (JSON/MsgPack), версионируемы и воспроизводимы по `snapshot_id`. Времена — UTC. Все численные поля сериализуются в float64.

### B.1. `market_state` (обязательная схема)
```yaml
market_state:
  schema_version: "7"
  snapshot_id: int
  ts_utc_ms: int
  market_data_id: int
  data_gap_sec: int
  is_gap_contaminated: bool

  instrument: str
  timeframe: "H1"
  price:
    last: float
    mid: float
    bid: float
    ask: float
    tick_size: float
  volatility:
    atr: float
    atr_z_short: float
    atr_z_long: float
    atr_window_short: int
    hv30: float | null
    hv30_z: float | null
  liquidity:
    spread_bps: float
    depth_bid_usd: float
    depth_ask_usd: float
    impact_bps_est: float
    orderbook_staleness_ms: int
    orderbook_last_update_id: int | null
    orderbook_update_id_age_ms: int | null
  derivatives:
    funding_rate_spot: float
    funding_rate_forecast: float | null
    funding_period_hours: float
    time_to_next_funding_sec: int
    oi: float | null
    basis_value: float | null
    basis_z: float | null
    basis_vol_z: float | null
    adl_rank_quantile: float | null
  correlations:
    tail_metrics_reliable: bool
    tail_reliability_score: float
    tail_corr_to_btc: float | null
    stress_beta_to_btc: float | null
    lambda_tail_dep: float | null
    corr_matrix_snapshot_id: int | null
    corr_matrix_age_sec: int | null
    gamma_s: float | null
  data_quality:
    suspected_data_glitch: bool
    stale_book_glitch: bool
    data_quality_score: float
    dqs_critical: float
    dqs_noncritical: float
    dqs_sources: float
    dqs_mult: float
    staleness_price_ms: int
    staleness_liquidity_ms: int
    staleness_derivatives_sec: int
    cross_exchange_dev_bps: float
    oracle_dev_frac: float | null
    oracle_staleness_ms: int | null
    price_sources_used: [str]
    toxic_flow_suspected: bool
    execution_price_improvement_bps: float | null
```

### B.2. `portfolio_state` (обязательная схема)
```yaml
portfolio_state:
  schema_version: "7"
  snapshot_id: int
  portfolio_id: int
  ts_utc_ms: int

  equity:
    equity_usd: float
    peak_equity_usd: float
    drawdown_pct: float
    drawdown_smoothed_pct: float
  risk:
    current_portfolio_risk_pct: float
    current_cluster_risk_pct: float
    reserved_portfolio_risk_pct: float
    reserved_cluster_risk_pct: float
    current_sum_abs_risk_pct: float
    reserved_sum_abs_risk_pct: float
    reserved_heat_upper_bound_pct: float
    adjusted_heat_base_pct: float
    adjusted_heat_blend_pct: float
    adjusted_heat_worst_pct: float
    heat_uni_abs_pct: float
    max_portfolio_risk_pct: float
    max_sum_abs_risk_pct: float
    cluster_risk_limit_pct: float
    max_adjusted_heat_pct: float
    max_trade_risk_cap_pct: float
  states:
    DRP_state: enum{NORMAL, DEGRADED, DEFENSIVE, EMERGENCY, RECOVERY, HIBERNATE}
    MLOps_state: enum{OK, WARNING, CRITICAL}
    trading_mode: enum{LIVE, PAPER, SHADOW, BACKTEST}
    warmup_bars_remaining: int
    drp_flap_count: int
    hibernate_until_ts_utc_ms: int | null
  positions:
    - instrument: str
      cluster_id: str
      direction: enum{long, short}
      qty: float
      entry_price: float
      entry_eff_allin: float
      sl_eff_allin: float
      risk_amount_usd: float
      risk_pct_equity: float
      notional_usd: float
      unrealized_pnl_usd: float
      funding_pnl_usd: float
      opened_ts_utc_ms: int
```

### B.3. `engine_signal` (обязательная схема)
```yaml
engine_signal:
  schema_version: "3"
  instrument: str
  engine: enum{TREND, RANGE}
  direction: enum{long, short}
  signal_ts_utc_ms: int

  levels:
    entry_price: float
    stop_loss: float
    take_profit: float
  context:
    expected_holding_hours: float
    regime_hint: str | null
    setup_id: str
  constraints:
    RR_min_engine: float
    sl_min_atr_mult: float
    sl_max_atr_mult: float
```

### B.4. `mle_output` (обязательная схема)
```yaml
mle_output:
  schema_version: "5"
  model_id: str
  artifact_sha256: str
  feature_schema_version: str
  calibration_version: str
  decision: enum{REJECT, WEAK, NORMAL, STRONG}
  risk_mult: float
  EV_R_price: float
  p_fail: float
  p_neutral: float
  p_success: float
  p_stopout_noise: float | null
  expected_cost_R_preMLE: float | null
  expected_cost_R_postMLE: float | null
```



Дополнения (обязательные поля):

* `shadow_execution_log` для `SHADOW_FULL`;
* `tail_metrics_state_changed_ts_utc_ms` и `tail_metrics_state_hold_sec`;
* поля risk-пайплайна: `risk_pre_liquidity`, `risk_target_for_sizing`, `risk_after_sizing`;
* `reservation_id` и состояния резерва риска в `execution_shadow`.

---

**Уточнения (добавлено при консолидации):**

* `tail_metrics_state_changed_ts_utc_ms`, `tail_metrics_state_hold_sec`;

## Приложение C: ЧИСЛЕННЫЕ СТАНДАРТЫ И ПАРАМЕТРЫ ПО УМОЛЧАНИЮ

### C.1. Численные стандарты
Контекстные допуски:

```text
is_close(a,b; rtol, atol) := abs(a-b) <= (atol + rtol*max(abs(a),abs(b)))
```

Контексты:

* `strict_unit`: `rtol=1e-9`, `atol=1e-12`
* `integration_kpi`: `rtol=1e-6`, `atol=1e-8`
* `prices`: `rtol=1e-8`, `atol=1e-10`
* `ml_outputs`: `rtol=1e-5`, `atol=1e-8`

eps:

* `price_eps_usd = max(tick_size, price_eps_frac * entry_price)`
* `pnl_eps_usd = max(0.01, equity_usd * pnl_eps_frac_equity)`
* `risk_amount_eps_usd = max(0.01, equity_usd * risk_amount_eps_frac_equity)`
* `R_eps = 1e-9`

Безопасное деление:

```text
denom_safe_signed(x, eps) =
  +eps, если x >= 0 и abs(x) < eps
  -eps, если x <  0 и abs(x) < eps
  x, иначе
```

### C.2. Параметры по умолчанию
```yaml
numerical_safeguards:
  price_eps_frac: 1.0e-6
  pnl_eps_frac_equity: 1.0e-6
  risk_amount_eps_frac_equity: 1.0e-6
  compounding_r_floor_eps: 1.0e-6
  log1p_switch_threshold: 0.01
  net_rr_eps_bps: 0.01
  heat_b_near_zero_eps: 1.0e-6
  heat_disc_floor_eps: 1.0e-12
  lot_rounding_eps: 1.0e-12
  avg_loss_w_floor: 1.0e-6
  diag_eps: 1.0e-4
  gap_unit_risk_eps: 1.0e-12
  unit_risk_bps_eps: 1.0e-6
  calmar_eps: 1.0e-6
  atr_eps: 1.0e-12
  RR_eps: 1.0e-9

risk_floors:
  risk_amount_min_absolute_usd: 2.00
  risk_amount_stats_floor_usd: 5.00
  risk_pct_equity_stats_floor: 0.0005
  unit_risk_min_absolute_for_funding: 0.01
  unit_risk_min_for_funding: 0.01

kpi_validity_defaults:
  kpi_min_trades: 80
  min_loss_trades: 20
  min_loss_threshold_money: 200.0
  min_loss_threshold_pct_equity: 0.01
  wr_w_invalid_high_threshold: 0.99
  wr_w_invalid_low_threshold: 0.01
  kpi_low_risk_excluded_share_cap: 0.30
  pf_identity_cv_threshold: 1.0
  cv_eps: 1.0e-9

variance_drag_defaults:
  trades_per_year_default: 140
  variance_drag_critical_frac: 0.35
  target_return_annual: 0.12
  target_return_annual_by_tier:
    tier1: 0.115  # среднее из целевого диапазона 8-15% (нормальный режим)
    tier2: 0.185  # среднее из целевого диапазона 15-22% (расширенный режим)
    tier3: 0.235  # среднее из целевого диапазона 22-25% (stretch-сценарий)

atr_defaults:
  atr_window_base: 14
  atr_window_min: 14
  atr_winsor_p_low: 0.01
  atr_winsor_p_high: 0.99
  atr_window_flash_cap: 200

tail_risk_defaults:
  tail_lookback_days_default: 365
  tail_lookback_days_max: 1095
  tail_fixed_threshold: -0.05
  q_tail: 0.05
  tail_min_samples_base: 500
  tail_vol_adj_factor: 1.0
  tail_reliability_hard_threshold: 0.95
  k0_base: 120
  k0_min: 50
  k0_max: 200
  k0_vol_sensitivity: 0.75
  k0_low_vol_floor: 120
  tail_var_eps: 1.0e-6
  tail_dependence_alpha: 0.05
  lambda_prior_floor: 0.25
  lambda_prior_corr_factor: 0.50
  tail_lambda_corr_factor: 0.50
  tail_dep_warning_threshold: 0.65
  tail_unreliable_mult: 0.70

tail_lambda_buffer_defaults:
  tail_lambda_soft: 0.65
  tail_lambda_hard: 0.85
  tail_lambda_mult_min: 0.30
  lambda_dynamic_recalc_threshold: 0.75
  stress_gap_lambda_unity_threshold: 0.70

mle_tail_guard_defaults:
  beta_base: 0.05
  beta_min: 0.01
  beta_max: 0.10
  beta_lambda_eps: 1.0e-6

correlation_matrix_defaults:
  shrinkage_alpha: 0.10
  stress_corr_delta: 0.50
  stress_corr_mode: "ASYMMETRIC"
  corr_min_eigenvalue_floor: 1.0e-6
  corr_regularization_alpha: 1.0e-4
  stress_gamma_ema_alpha: 0.20
  corr_matrix_max_age_sec: 86400
  psd_higham_max_iters: 15
  psd_eig_floor: 1.0e-6
  psd_diag_floor: 1.0e-6
  corr_matrix_stale_mult: 0.80

rounding_defaults:
  lot_rounding_risk_deviation_threshold: 0.10
  lot_granularity_error_target: 0.05

funding_defaults:
  funding_period_hours_default: 8
  funding_blackout_minutes: 15
  funding_blackout_max_holding_hours: 12
  funding_blackout_cost_share_threshold: 0.40
  funding_blackout_ev_eps: 0.05
  funding_event_inclusion_epsilon_sec: 2
  funding_count_smoothing_width_sec: 60
  funding_cost_soft_R: 0.10
  funding_cost_block_R: 0.25
  min_net_yield_R: 0.05
  funding_cost_R_eps_price: 1.0e-12
  funding_blackout_risk_cap_min: 0.25
  funding_proximity_soft_sec: 1800
  funding_proximity_hard_sec: 300
  funding_proximity_power: 2.0
  funding_proximity_mult_min: 0.80
  funding_credit_allowed: false

basis_defaults:
  basis_z_soft: 2.0
  basis_z_hard: 3.0
  basis_vol_z_soft: 2.0
  basis_vol_z_hard: 3.0
  basis_risk_mult_soft: 0.85
  basis_risk_mult_hard: 0.70
  basis_vol_mult_soft: 0.85
  basis_vol_mult_hard: 0.70
  basis_event_proximity_soft_sec: 1800
  basis_event_proximity_hard_sec: 600
  basis_event_mult_soft: 0.90
  basis_event_mult_hard: 0.80

gap_defaults:
  gap_frac_min: 0.10
  gap_frac_max: 0.70
  gap_hv_sensitivity: 0.20
  gap_hv_z_cap: 3.0
  hv30_ref_lookback_days: 180
  gap_frac_basis_vol_sensitivity: 0.20
  basis_gap_adjust_enabled: false

bankruptcy_defaults:
  bankruptcy_threshold_pct_equity: 0.50
  bankruptcy_buffer_pct_equity: 0.05
  max_gap_loss_pct_equity_config: 0.25
  portfolio_max_gap_loss_pct_equity_config: 0.45
  liq_buffer_min: 0.01
  k_liq_vol: 4.0
  k_liq_spread: 10.0

risk_defaults:
  max_portfolio_risk_pct: 0.04
  max_sum_abs_risk_pct: 0.04
  cluster_risk_limit_pct: 0.03
  max_adjusted_heat_pct: 0.03
  heat_soft_frac: 0.95
  min_risk_floor_pct_by_tier:
    tier1: 0.0020
    tier2: 0.0020
    tier3: 0.0020
  hedge_opt_mult: 1.25
  hedge_abs_cap_pct: 0.02
  heat_min_reduction_bps: 10
  max_trade_risk_hard_cap_pct: 0.0050
  kelly_fraction: 0.50
  kelly_cap_max: 0.0040
  kelly_floor_pct: 0.0010
  kelly_min_trades: 150
  kelly_min_loss_trades: 30

drawdown_defaults:
  dd_recovery_disable_threshold_pct: 0.30

stacking_defaults:
  mult_active_threshold: 0.98
  mult_active_power: 2.0
  stacking_penalty_base: 0.95
  mult_eps: 1.0e-9

execution_defaults:
  stop_slippage_mult: 2.0
  min_fill_frac_to_hold: 0.25
  max_sizing_iters: 5
  convergence_tol: 0.05
  sizing_damp_alpha: 0.60
  impact_update_alpha: 0.50
  impact_convergence_tol_bps: 1.0
  liquidity_min_convergence_threshold: 0.60
  sizing_low_liquidity_cap_mult: 0.50
  sizing_high_impact_cap_mult: 0.50
  sizing_not_converged_risk_cap_mult: 0.50
  passive_fade_base_timeout_sec: 120
  passive_fade_timeout_min_sec: 30
  passive_fade_timeout_max_sec: 180
  passive_fade_hard_timeout_sec: 300
  urgency_taker_threshold: 0.85
  max_acceptable_impact_bps: 25
  max_impact_soft: 15
  max_impact_hard: 35
  max_acceptable_spread_bps: 15
  max_spread_soft: 10
  max_spread_hard: 25
  urgency_atr_z_cap: 3.0
  taker_urgency_risk_cap_pct: 0.0030
  alpha_decay_cancel_R: 0.50
  fill_abandonment_rr_frac: 0.20
  min_abandon_R: 0.05
  abandon_threshold_min_bps: 0.10
  net_edge_floor_R: 0.03

data_quality_defaults:
  dqs_degraded_threshold: 0.70
  dqs_emergency_threshold: 0.40
  dqs_weight_critical: 0.75
  dqs_sources_min: 0.60
  staleness_price_hard_ms: 2000
  staleness_liquidity_hard_ms: 1000
  snapshot_max_age_ms: 2500
  orderbook_update_id_stale_ms: 1500
  stale_book_glitch_window_minutes: 60
  stale_book_glitch_repeat_threshold: 3
  warmup_bars_base: 1
  warmup_bars_min: 1
  warmup_bars_max: 24
  flap_window_minutes_base: 180
  flap_window_minutes_min: 180
  flap_window_minutes_max: 360
  flap_to_hibernate_threshold: 4
  xdev_block_bps: 25
  oracle_dev_block_frac: 0.01
  oracle_staleness_hard_ms: 5000
  price_improvement_bps_suspicious: 30
  toxic_flow_spread_bps_min: 10
  toxic_flow_improvement_count_threshold: 3

mrc_defaults:
  mrc_high_conf_threshold: 0.70
  mrc_very_high_conf_threshold: 0.85
  mrc_low_conf_threshold: 0.55
  conflict_window_bars: 10
  conflict_fast_atr_z: 2.0
  conflict_ratio_threshold: 0.60
  diagnostic_block_minutes: 120

probe_defaults:
  probe_risk_mult: 0.33
  probe_min_depth_usd: 500000
  probe_max_spread_bps: 12
  RR_min_probe_add: 0.10

mle_calibration_defaults:
  mle_calibration_window_trades: 200
  min_days_between_calibrations: 7
  reference_days_after_training: 30
  ece_binning: "adaptive_equal_frequency"
  ece_bins: 15

risk_reservation_defaults:
  reservation_ttl_sec_min_maker: 30
  reservation_ttl_sec_min_taker: 10
  reservation_ttl_sec_min_stop: 20
  reservation_renewal_min_period_sec: 2
  reservation_heartbeat_period_ms: 500
  reservation_heartbeat_grace_ms: 1500
  commit_retry_count: 3
  portfolio_risk_buffer_pct: 0.002
  cluster_risk_buffer_pct: 0.002
  heat_buffer_pct: 0.002

concurrency_defaults:
  writer_queue_hard_cap: 2000
  commit_latency_budget_ms: 300
  max_occ_retries: 3
  preexec_validation_deadline_ms: 500
  gatekeeper_latency_budget_p99_ms_by_tier:
    tier1: 500
    tier2: 300
    tier3: 200

drp_depeg_defaults:
  depeg_critical_frac: 0.02
  depeg_auto_exit_threshold_sec: 120
  depeg_exit_twap_duration_sec: 60
```


### C.3. Обязательные автотесты (минимальный набор)
1. `PF_money == PF_money_identity` в пределах `integration_kpi` при `cv_risk <= pf_identity_cv_threshold`; при превышении порога — статус `HIGH_VARIANCE_WARNING`.
2. Корректность EffectivePrices LONG/SHORT и `unit_risk_allin_net == abs(entry_eff_allin - sl_eff_allin)`.
3. Инвариант “-1R по фактическим fill-ценам” на synthetic и записанных эпизодах, включая partial fills.
4. PSD-валидность `C_psd/C_stress/C_blend` и `diag()==1` в пределах `diag_eps`; проверка fallback `eigenvalue_clipping` с нормировкой `D^{-1/2} C D^{-1/2}`.
5. Funding boundary тесты: `funding_R`, `funding_cost_R`, proximity-модель, blackout, size-invariance.
6. Проверка минимального unit risk и абсолютного минимума риска сделки.
7. Корректность `remaining_heat_limits` включая soft/hard правила, `b≈0`, iterative halving, и хедж-кап.
8. Forced-hedge: при `H_current > H_hard` разрешаются только сделки с `b<0`, и они обязаны снижать `H_current` минимум на `heat_min_reduction_bps`.
9. Сценарий корреляционного коллапса: `x_max_uni_abs` учитывается и может только уменьшать лимит; соответствие `max_sum_abs_risk_pct`.
10. Несходимость sizing: `sizing_not_converged=True` и применение `sizing_not_converged_risk_cap_mult`; проверка раннего выхода при `net_edge_R_after_cost < net_edge_floor_R`.
11. Compounding domain: запрет `r ≤ -1 + eps`, безопасная обработка `r < -1` и переход в `EMERGENCY`.
12. Bankruptcy check: динамический `gap_frac`, корректность `gap_mult` без двойного учёта basis по умолчанию; leverage buffer блокирует сделки, где SL ближе к ликвидации, чем допускает буфер.
13. Stress-gap: корректность формы `sqrt(Gᵀ C_stress_S G)` и усиление `rho=+1` при `lambda_used >= stress_gap_lambda_unity_threshold`.
14. Risk Reservation: атомарное ограничение скалярных лимитов; буферы; адаптивный TTL/renewal; поведение при истечении резерва и fill; commit retry.
15. Shadow safety: при `trading_mode == SHADOW` Gatekeeper завершает обработку после GATE 6 и не выполняет гейты 7–18.
16. Concurrency: тест 100 параллельных сигналов с проверкой целостности лимитов и отсутствия некорректных коммитов.
17. Flash-crash: сценарий гэпа 20% за 1 бар и проверка переходов DRP, impact, liquidity hard-gates и emergency-exit.
18. Anti-flapping: при достижении `flap_to_hibernate_threshold` система переходит в `HIBERNATE`.
19. Depeg auto-exit: при `depeg_duration_sec > depeg_auto_exit_threshold_sec` инициируется TWAP-выход и режим `LIQUIDATE_OPTIMAL`.
20. Unit-consistency tests: любые сравнения в гейтах проходят валидатор единиц (bps vs R vs pct_equity); нарушение — тестовый fail.

**Уточнения (добавлено при консолидации):**

Минимальный набор включает, помимо ранее перечисленных, следующие обязательные тесты/проверки:
1. Полное покрытие конфигов: все упомянутые параметры присутствуют в дефолтах и доступны через единый реестр параметров.
2. Property-based тест монотонности: ухудшение входов (`DQS↓`, `lambda_used↑`, `|Stress_beta|↑`, `|Tail_corr|↑`, `gamma_s↑`, `adl_rank_quantile↑`, `corr_matrix_age_sec↑`) не может увеличивать риск (включая `corr_beta_mult` и `adl_risk_mult`).
3. Проверка `heat_buffer_pct >= max_trade_risk_cap_pct` и корректность `reserved_heat_upper_bound_pct` в резервах.
4. Iterative halving: завершение при `qty_try < lot_step_qty` с корректным отказом.
5. PSD fallback: цикл Clip→Normalize обеспечивает `diag==1` и отсутствие значимых отрицательных собственных значений ниже `-psd_neg_eig_tol`.
6. Stale Book but Fresh Price: детект и hard-блокировка воспроизводимы в тестовом стенде.
7. Sizing несходимость: выбирается минимум из валидных `qty_k`, применяется `sizing_not_converged_risk_cap_mult`.
8. Recovery guard: при `dd_s >= dd_recovery_disable_threshold_pct` буст отключён и DRP минимум `DEFENSIVE`.
9. Funding credit policy: при `funding_credit_allowed=false` положительный ожидаемый funding не может улучшать `Net_Yield_R` и не может служить причиной прохождения доходностных гейтов.