# rubric-v1 — схема агрегации

Оценка — рекомендация работодателю, пока он не утвердит `Assessment` (`APPROVED`). Каждое ненулевое измерение обязано иметь evidence references. Измерение без фактов остаётся `null` («insufficient evidence») и **не** подменяется нулём.

## Измерения (0–100)

| Dimension | Вес | Формула |
|---|---|---|
| `code_quality` | 15 | 100 − штрафы severity findings категории `code_quality` финального AI-анализа |
| `architecture` | 15 | то же для `architecture` |
| `security` | 10 | то же для `security` |
| `tech_knowledge` | 10 | 60% pass rate финального sandbox run + 40% × (100 − штрафы `tech_knowledge`) |
| `debugging` | 10 | 50% pass rate + 50% × (100 − штрафы debugging/performance) + бонус улучшения pass rate между версиями |
| `response_to_review` | 15 | 60% доля `RESOLVED` комментариев + 40% pass rate revised submission |
| `explanation` | 15 | среднее AI-evaluation ответов code defense |
| `adaptability` | 10 | 70% pass rate submission после `RequirementChange` + 30% evaluation ответов на этой версии |

Штрафы severity: info 0, low 5, medium 10, high 20, critical 30. Findings без опоры в коде отбрасываются валидатором evidence.

## Overall

```text
overall = round( sum(weight_d * score_d) / sum(weight_d) )
          по измерениям, у которых score != null
coverage = sum(весов оценённых) / 100
missing  = измерения без score
```

Веса missing-измерений не перераспределяются «тихо»: это видно в `aggregation.coverage` и `aggregation.missing`. Одна и та же версия рубрики и тот же набор фактов всегда дают тот же overall.

Реализация: `packages/domain/src/rubric.ts`, `services/assessment/src/index.ts`.
