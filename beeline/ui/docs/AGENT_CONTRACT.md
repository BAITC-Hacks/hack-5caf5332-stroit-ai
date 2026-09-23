# Контракт агента для UI

`server.py` запускает `run_case.py` рядом с `agent.py`, тот вызывает `Agent().act(env)` через `local_eval.evaluate_agent`, а потом читает **`agent.audit`** и пишет `run.json` + `submission.csv`. UI (`src/workspace.js`) читает только `run.json`. Всё, что нужно от агента: заполнить `self.audit` до возврата из `act`. Числа JSON-сериализуемые (без numpy-типов, без NaN), `run_case.clean()` numpy-скаляры приводит сам.

## Обязательное

| Ключ | Тип | Кто читает |
|---|---|---|
| `audit.plan[]` | список финальных кампаний, непустой | run_case (падает, если пусто), UI «План» |
| `plan[].candidate` | id кандидата, совпадает с `candidates[].id` | UI |
| `plan[].campaign` | dict с полями submission.csv: `campaign_name, filter_arpu_segment, filter_data_segment, filter_call_segment, filter_current_tariff, target_tariff, channel` | run_case → submission.csv |
| `plan[].contacts`, `plan[].cost`, `plan[].net` | числа; `net` может быть null | UI |
| `plan[].reason` | строка, почему выбрана | UI |
| `audit.pilots[]` | по одному на `env.run_pilot` | UI «Пилоты» |
| `pilots[].candidate` | id кандидата | UI |
| `pilots[].filters` | dict аргументов run_pilot без n | UI |
| `pilots[].result` | dict, который вернул `env.run_pilot` как есть | UI (`n_customers`, `observed_lift_ratio`, `cost`, `pilot`) |
| `pilots[].reason` | строка, зачем пилот | UI |
| `audit.candidates[]` | все гипотезы, включая непротестированные | UI «Аудитория» |
| `candidates[].id, cell, current, arpu, target, channel` | строки; `cell` = `f"{current}_{arpu}"` | UI |
| `candidates[].n, mean, se, pilot_count` | числа; `mean`/`se` null, если не тестировали | UI |
| `candidates[].selected` | bool | UI |
| `candidates[].decision` | строка: `selected` / `unmeasured` / `not_selected: ...` | UI |
| `audit.remaining_after_pilots` | `{budget, contacts, pilots}` | UI |

## Необязательное, но UI покажет

`audit.low_confidence_fallback` (bool), `audit.stop_reason`, `audit.quality {rows, invalid_rows, duplicate_ids, missing_values}`, `audit.limits {budget, contacts, pilots}`, `audit.elapsed_seconds`, `candidates[].prior_rank`, `candidates[].history_n`, `plan[].gross`, `plan[].conservative_net`.

## Маппинг на agent.py из PR #4

- `self.records` → `audit.pilots` (`result` собрать из `res`, `filters` из аргументов run_pilot, `candidate` = `f"{tariff}_{seg}_{target}_{channel}"`).
- `self.hyps` (DataFrame) → `audit.candidates` (`n` = `n_obs`, `mean` = `mu`, `se` = `sd`, `channel` = канал финальной кампании или `sms`).
- `self.plan_detail` → `audit.plan` (`campaign` = словарь кампании без `n/cost/value`, `contacts` = `n`, `net` = `value`).
- `self.calibration` → можно положить в `audit.calibration`, UI пока не читает.
