# Требования к окружению

Базовый вариант использует внешний LLM API — **GPU не требуется**. Ресурсы нужны для
оркестрации, временных checkout, PostgreSQL/Redis, логов и сетевых операций.

## Профили

| Профиль | Нагрузка | CPU | RAM | Диск |
|---|---|---|---|---|
| Dev / локальная проверка | 1 задача за раз | 2 vCPU | 4–8 GB | 30–50 GB SSD |
| Pilot / малая команда | 1–3 параллельные | 4 vCPU | 8–16 GB | 100 GB SSD |
| Production minimum | 3–6 параллельных | 8 vCPU | 16–32 GB | 200–300 GB NVMe |
| Production recommended | 6–12 параллельных | 12–16 vCPU | 32–64 GB | 500 GB+ NVMe |
| Scale-out | много команд | api 2–4 / worker 4–8 каждый | api 4–8 / worker 8–16 | shared DB + per-worker tmp |

## Прочее

| Параметр | Минимум | Рекомендуется |
|---|---|---|
| Сеть | стабильный HTTPS egress к GitLab/Bitrix/LLM | низкая задержка до GitLab |
| Диск `/tmp` | 2–5 GB на активную задачу | 5–10 GB + cleanup |
| IOPS | обычный SSD | NVMe для production |
| Backup | ручной | автоматический daily backup PostgreSQL + retention |
| Мониторинг | docker logs + healthcheck | Prometheus/Grafana + централизованные логи + алерты |

## Размещение

Для production — выделенный сервер/VM. Рядом с GitLab допустимо только для пилота и при
вынесенных CI runners. **Запрещено** размещать рядом с GitLab, если: GitLab уже испытывает
нехватку ресурсов; на нём боевые секреты; планируется >3 параллельных задач; нельзя задать
resource limits и отдельные volumes; нет мониторинга.
