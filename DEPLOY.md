# Миграция «Медицинский консультант» с локальной машины на удалённый сервер

Документ описывает перенос работающего docker-compose-стека с локального компьютера
(текущее размещение) на удалённый сервер `ii-doktor.ru`. После миграции
приложение должно быть доступно по `https://ii-doktor.ru`.

## Текущее состояние (исходный рубеж)

- Приложение работает локально на этой машине: `F:\Projects\19. Medical consultant`
  (docker-compose стек поднят: postgres + backend + frontend).
- Админ-панель: `http://127.0.0.1:8081/admin`. Фронт поднят на `8081`, потому что
  `8080` на этой машине занят сторонним проектом; **на сервере** `8080` свободен,
  и фронт займёт `127.0.0.1:8080` штатно по `docker-compose.yml`.
- Целевой адрес приложения — домен `https://ii-doktor.ru` (зарегистрирован в Beget).
  Старый домен `помощники-консультанты.рф` утерян: его регистрация истекла, и A-запись
  была переиспользована под чужой сайт — не использовать.
  Значение `FRONTEND_URL` уже прописано в `.env` (используется в ссылках
  восстановления пароля и платёжных редиректах).

## Топология

Локально и на сервере используется один и тот же `docker-compose.yml`:

| Сервис | Внутри compose | Доступ снаружи |
|--------|----------------|----------------|
| `postgres` | `postgres:16-alpine`, порт `5432` | только `127.0.0.1:5432` (наружу не торчит) |
| `backend` | FastAPI (uvicorn), порт `8000` | не публикуется; ходит только через фронт |
| `frontend` | nginx (Vite build → статика), порт `80` | `127.0.0.1:8080:80` в контейнере; публикует домен внешний nginx |

Публичный вход: внешний **nginx на сервере** → HTTP↔HTTPS (Let's Encrypt/certbot) →
проксирует `/` на `127.0.0.1:8080`. Этот nginx + SSL и папка ops-мониторинга
(`/opt/medical-consultant-ops/`) лежат **вне репозитория** и переносятся отдельно.

Имена контейнеров зафиксированы в `docker-compose.yml` (`container_name`), но имена
**томов зависят от имени каталога-проекта** compose: на сервере это
`/opt/medical_consultant_app/` → тома `medical_consultant_app_postgres_data` и
`medical_consultant_app_backend_uploads` (на локалке — `19medicalconsultant_*`).

## Что нужно перенести

| Компонент | Источник | Как переносится |
|-----------|----------|-----------------|
| Код | git (GitHub) | `git pull` на сервере |
| Секреты | `F:\Projects\19. Medical consultant\.env` | вручную на сервер (файл **не в git**) |
| База данных | том `postgres_data` | `pg_dump` → `psql` |
| Загруженные файлы | том `backend_uploads` | `docker compose cp` |
| Nginx домена + SSL | серверная система | не трогать / перенастроить на новом хосте |
| Ops-мониторинг | `/opt/medical-consultant-ops/` | скопировать на сервер отдельно |

## Шаг 1. Подготовка на локалке

```bash
# Дамп базы данных (не останавливая стек)
docker compose exec postgres pg_dump -U medical -d medical_consultant > db.sql

# Копия загруженных документов
docker compose cp backend:/app/data/uploads/. ./uploads_migration/
```

Проверьте `db.sql` на размер и целостность и сохраните оба артефакта вместе с `.env`
в безопасном месте (на время миграции — бэкап не помешает; на сервере после успешного
разворота они не понадобятся).

## Шаг 2. Подготовка сервера

Если мигрируем **на тот же сервер** (новый код вместо старого) — nginx/SSL уже
настроены, переходите к шагу 3.

Если **новый хост**:

1. Установить Docker (compose plugin) — как на README-машине.
2. Создать каталог `/opt/medical_consultant_app`, склонировать репозиторий.
3. Настроить DNS: A-запись `ii-doktor.ru` на IP нового сервера.
4. Установить nginx + certbot, сайт:

```nginx
server {
    listen 80;
    server_name ii-doktor.ru;
    client_max_body_size 30m;   # выровнять с MAX_UPLOAD_BYTES (см. «Нюансы»)
    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_connect_timeout 300s;
        proxy_send_timeout 300s;
        proxy_read_timeout 300s;
    }
}
```

Получить сертификат:
```bash
certbot --nginx -d ii-doktor.ru
```

5. Перенести папку `/opt/medical-consultant-ops/` (если используется).

## Шаг 3. Перенос .env (критично)

Положить на сервер `.../.env`. **Обязательно сохранить те же значения**:

- `JWT_SECRET` — иначе все ранее выпущенные токены (включая вход в админку)
  перестанут работать (`401` на всех `/api/*`).
- `POSTGRES_PASSWORD` — должен совпадать с паролем при `pg_dump`/`psql`.
- `ADMIN_EMAIL` — иначе админских прав не будет.

Остальные ключи (LLM, YooKassa, SMTP, OCR) можно заменить новыми при необходимости.

## Шаг 4. Разворот и импорт данных

```bash
cd /opt/medical_consultant_app
# перенести из дампа и uploads, положив их рядом с репозиторием:
#   db.sql, uploads_migration/

# Импорт БД (на свежем томе postgres)
docker compose exec -T postgres psql -U medical -d medical_consultant < db.sql

# Восстановить документы
docker compose cp ./uploads_migration/. backend:/app/data/uploads/

# Собрать и поднять
docker compose build
docker compose up -d --force-recreate
```

Если том postgres уже не пуст — предварительно `docker compose down -v` и поднять
`postgres` заново, либо добавить `--clean --if-exists` при `pg_dump` на шаге 1.

## Шаг 5. Проверка после миграции

```bash
curl -sk https://ii-doktor.ru/health | jq
curl -sk -o /dev/null -w "%{http_code}" https://ii-doktor.ru/   # 200
```

Ручная проверка в браузере:

- [ ] Открывается главная страница `https://ii-doktor.ru`
- [ ] Вход в админку `/admin` работает (учётная запись `ADMIN_EMAIL`)
- [ ] Виден ранее зарегистрированный пользователь; кошелёк и баланс на месте
- [ ] Старые загруженные документы видны/доступны в списке загрузок
- [ ] Чат отвечает (работают `AITUNNEL_API_KEY` / `PROXYAPI_API_KEY`)
- [ ] `docker compose ps` — все три сервиса `Up (healthy)`

## Нюансы и проверки перед go-live

- **`JWT_SECRET`** — не менять между локалкой и сервером и между перезапусками backend
  (взаимно: смена сбрасывает все сессии).
- **`client_max_body_size` (20m в `frontend/nginx.conf`)** vs `MAX_UPLOAD_BYTES`
  (по умолчанию 30 МБ): файлы 20–30 МБ будут отклонены nginx раньше бэкенда.
  При миграции решить: поднять лимит nginx (`30m`) или снизить `MAX_UPLOAD_BYTES`.
- **Тома названы по каталогу**: команды с именами томов из этого документа корректны
  для `/opt/medical_consultant_app` (для иного пути уточнить `docker compose volume ls`).
- **CI** (GitHub Actions) гоняет `ruff` + `pytest` на `main` — разворот делать из
  зелёной ветки, чтобы не тащить непроверенный код.
- **Откат**: при неудаче — `docker compose down`, восстановить `db.sql` заново
  на чистом томе и `docker compose up -d --build`.

## См. также

- `README.md` — описание переменных окружения, запуск, раздел «Продакшен-деплой».
- `docker-compose.yml` — официальная конфигурация сервисов.