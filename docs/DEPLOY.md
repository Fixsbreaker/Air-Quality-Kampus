# Развёртывание на сервере КБТУ

Проект размещается по пути **`esg.kbtu.kz/air-quality`**.

Документ рассчитан на инженера, который разворачивает проект на сервере, и
описывает только то, что нужно для запуска. Устройство системы — в
[TechDoc_AirQualityKampus.md](../TechDoc_AirQualityKampus.md).

---

## 1. Соответствие требованиям к деплою

| Требование | Как выполнено |
|---|---|
| Рабочий backend и frontend | Проверены локально: 152 автотеста, линтеры без замечаний |
| `Dockerfile` и `docker-compose.yml` | `backend/Dockerfile`, `bot/Dockerfile`, `frontend/Dockerfile`; продовый файл — `docker-compose.prod.yml` |
| Все нужные сервисы описаны | PostgreSQL, Redis, API, планировщик задач, Telegram-бот, nginx с фронтендом |
| Настраиваемый базовый путь | `PROJECT_BASE_PATH` → аргумент сборки `VITE_BASE_PATH` → `base` в `vite.config.ts` |
| Настраиваемый URL API | `VITE_API_BASE_URL`; по умолчанию пусто — запросы идут относительно базового пути |
| API работает через `/api/` | Все маршруты FastAPI начинаются с `/api/`, кроме `/health` |
| Секреты в `.env` | Ни одного секрета в репозитории, шаблон — `.env.prod.example` |
| Нет захардкоженных доменов, IP и портов | Всё через переменные окружения; проверяется тестами конфигурации |
| `expose` вместо `ports` | В `docker-compose.prod.yml` ни один сервис не публикует порты на хост |
| Префиксы в именах сервисов | `aqi-db`, `aqi-redis`, `aqi-api`, `aqi-worker`, `aqi-bot`, `aqi-web` |
| Отдельный Compose-проект | `name: kbtu-air-quality` |
| Отдельная база данных | Собственный контейнер `aqi-db`, общими СУБД проект не пользуется |
| Подключение к `esg-network` | Только `aqi-web`; остальные сервисы изолированы в приватной сети `aqi-internal` |
| Внутренний nginx не знает про префикс | `frontend/nginx.conf` обслуживает `/` и `/api/`, без `/air-quality` |

Наружу, в общую сеть, смотрит **единственный контейнер `aqi-web`**. База
данных, кэш, API и фоновые задачи в общую сеть не подключены и другим проектам
на сервере недоступны.

---

## 2. Что нужно от инженера сервера

**Внешняя сеть.** Проект подключается к уже существующей сети:

```bash
docker network ls | grep esg-network
```

Если её нет:

```bash
docker network create esg-network
```

**Публичный nginx.** Добавить блок, снимающий префикс пути. Завершающий слеш
в `proxy_pass` обязателен — именно он убирает `/air-quality` из запроса:

```nginx
location = /air-quality {
    return 301 /air-quality/;
}

location /air-quality/ {
    proxy_pass http://aqi-web/;
    proxy_set_header Host              $host;
    proxy_set_header X-Real-IP         $remote_addr;
    proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;

    # Выгрузка наблюдений в CSV отдаётся потоком и может идти долго.
    proxy_buffering off;
    proxy_read_timeout 300s;
}
```

Дальше внутренний nginx проекта сам разбирает, что отдать статикой, а что
проксировать в API.

---

## 3. Порядок развёртывания

```bash
git clone https://github.com/Fixsbreaker/Air-Quality-Kampus.git
cd Air-Quality-Kampus
cp .env.prod.example .env
```

Заполнить `.env`. Обязательно заменить два значения — сгенерировать, а не
придумывать:

```bash
openssl rand -hex 32    # POSTGRES_PASSWORD (и тот же пароль в DATABASE_URL)
openssl rand -hex 32    # ADMIN_TOKEN
```

`ADMIN_TOKEN` защищает выгрузку наблюдений и список подписчиков — со значением
по умолчанию эти маршруты открыты всем.

Запуск:

```bash
docker compose -f docker-compose.prod.yml --env-file .env up -d --build
```

Миграции базы данных применяются автоматически при старте контейнера `aqi-api`.

Проверка:

```bash
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml exec aqi-api curl -fsS http://localhost:8000/health
```

---

## 4. Наполнение данными после первого запуска

Сразу после старта база пуста: дашборд покажет ошибку «нет данных», это
ожидаемо. Нужно выкачать архив и обучить модель.

```bash
docker compose -f docker-compose.prod.yml exec aqi-api python -m scripts.backfill --days 730
docker compose -f docker-compose.prod.yml exec aqi-api python -m scripts.train
docker compose -f docker-compose.prod.yml exec aqi-api python -m scripts.make_forecast
```

Выкачка двухлетнего архива занимает около минуты, обучение — полторы. Дальше
всё поддерживается автоматически: сбор данных каждый час, пересчёт прогноза
каждый час, переобучение модели в 03:00. Этим занимается контейнер
`aqi-worker`.

Внешний источник ключа не требует, ограничение — около 10 000 запросов в сутки,
проект делает 144.

---

## 5. Telegram-бот (необязательно)

Бот вынесен в отдельный профиль и без явного указания не запускается. Чтобы
поднять, нужно указать `BOT_TOKEN` в `.env` и выполнить:

```bash
docker compose -f docker-compose.prod.yml --profile bot up -d aqi-bot
```

---

## 6. Обновление версии

```bash
git pull
docker compose -f docker-compose.prod.yml up -d --build
```

Модель и база данных лежат в именованных томах `models` и `pgdata` и
пересборку переживают. Команда `down` без флага `-v` их тоже не трогает.

---

## 7. Если что-то не работает

| Симптом | Причина и что смотреть |
|---|---|
| Статика не загружается, в консоли 404 на `/assets/...` | Публичный nginx не снимает префикс — проверить завершающий слеш в `proxy_pass` |
| Страница открылась, данных нет | Не выполнен `backfill` — см. раздел 4 |
| График прогноза пуст | Не выполнены `train` и `make_forecast` |
| `/api/...` отдаёт 502 | Контейнер `aqi-api` не поднялся: `docker compose -f docker-compose.prod.yml logs aqi-api` |
| Публичный nginx не видит `aqi-web` | Контейнер не подключён к `esg-network` или сеть не создана |
| Данные не обновляются | Проверить `aqi-worker`: `docker compose -f docker-compose.prod.yml logs aqi-worker` |

Общее состояние системы, включая доступность базы и активную версию модели,
отдаёт `/health`.

---

## 8. Swagger за префиксом

Интерактивная документация API доступна по адресу
`esg.kbtu.kz/air-quality/docs`, ReDoc — по `/air-quality/redoc`.

Чтобы страница подтягивала схему, приложению нужно знать свой внешний префикс:
Swagger UI иначе запрашивает `/openapi.json` от корня домена. Префикс задаётся
переменной `ROOT_PATH` в `.env` — в шаблоне уже стоит `/air-quality`, без
завершающего слеша.

На работу самого API переменная не влияет: маршруты остаются абсолютными
(`/api/...`), префикс снимает публичный nginx. Если `ROOT_PATH` не задать,
API продолжит работать, перестанет открываться только страница документации.
