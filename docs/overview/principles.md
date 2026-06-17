# Принципы управления рисками

- **No guessing** — при недостающих требованиях агент задаёт вопросы и не начинает кодинг.
- **Least privilege** — токен бота имеет минимальные права и пишет только в ветки `auto-task-*`.
- **Plan before code** — до генерации кода формируются план изменений, тест-план и риск-профиль.
- **Separation of duties** — код пишет Coder, проверяет независимый Reviewer, security-sensitive
  изменения смотрит Red Team. Reviewer не видит ход рассуждений Coder.
- **Human owns merge** — итоговое решение о слиянии принимает человек-Maintainer.
- **Auditability** — все существенные решения, вызовы инструментов и результаты проверок логируются.
- **Fail closed** — при неопределённости, превышении лимитов или high/critical findings процесс
  блокируется и передаётся человеку.

## Как принципы закреплены в коде

| Принцип | Где |
|---|---|
| No guessing | брифинг с порогом confidence ответов; doc_impact fail-closed |
| Least privilege | ветки только `auto-task-*`; merge не выполняется |
| Plan before code | `planning` → `RiskPlanGate` до `coding` |
| Separation of duties | `reviewer` получает только diff/тесты/docs, без рассуждений Coder |
| Human owns merge | `finalize_mr` снимает Draft, но merge делает человек |
| Auditability | `audit` (структурные логи + редакция), таблица `audit_event` |
| Fail closed | вердикты по умолчанию блокируют; гейты `merge_blocked`; песочница отклоняет неоднозначное |
