# Медицинский ИИ-навигатор

Веб-приложение для персонального медицинского сопровождения: анкета здоровья, анализы, документы, чат с ИИ-консультантом и сравнение «двух мнений» (ассистент + очный врач).

**Продакшен:** [https://помощники-консультанты.рф/](https://помощники-консультанты.рф/)

> **Важно.** Сервис не заменяет очного врача, не предназначен для экстренной помощи и даёт только информационную поддержку. Любые гипотезы, рекомендации и планы лечения должны проверяться медицинским специалистом.

---

## Содержание

- [Возможности](#возможности)
- [Архитектура](#архитектура)
- [Стек технологий](#стек-технологий)
- [Структура проекта](#структура-проекта)
- [Аутентификация](#аутентификация)
- [API](#api)
- [База данных](#база-данных)
- [Маршрутизация LLM](#маршрутизация-llm)
- [Сценарий «два мнения»](#сценарий-два-мнения)
- [Безопасность и ФЗ-152](#безопасность-и-фз-152)
- [Переменные окружения](#переменные-окружения)
- [Быстрый старт (локально)](#быстрый-старт-локально)
- [Запуск в Docker](#запуск-в-docker)
- [Продакшен-деплой](#продакшен-деплой)
- [Тестирование и линтер](#тестирование-и-линтер)
- [Типичные проблемы](#типичные-проблемы)
- [Связанные репозитории](#связанные-репозитории)

---

## Возможности

| Раздел | Описание |
|--------|----------|
| **Регистрация / вход** | Email + пароль, JWT-сессии, согласие на обработку ПДн |
| **Анкета здоровья** | Возраст, пол, рост, вес, хронические заболевания, аллергии, препараты, образ жизни |
| **Анализы** | Ввод лабораторных показателей, тренды относительно предыдущих значений |
| **Документы** | Загрузка PDF, изображений и текстовых файлов для последующего разбора |
| **Чат с ИИ** | Многошаговый диалог: сбор анамнеза → первое мнение до визита к врачу |
| **История обращений** | Сохранение жалоб, AI-анализ, сравнение с мнением очного врача |
| **ИИ-нутрициолог** | Генерация недельного меню с учётом профиля и продуктов в холодильнике |
| **Настройки** | Профиль, правовая информация, выход, безвозвратное удаление аккаунта |

---

## Архитектура

```text
Браузер (React SPA)
       │
       │  HTTPS
       ▼
Nginx (хост) ──► frontend:8080  (статика + proxy /api → backend)
       │
       └──► backend:8000  (FastAPI)
                 │
                 ├── PostgreSQL 16  (users, profiles, medical data)
                 ├── Volume uploads  (файлы документов)
                 ├── aitunnel.ru     (основные LLM)
                 └── Yandex Vision OCR (документы)
                 └── proxyapi.ru     (fallback OCR / изображения)
```

**Docker Compose** поднимает три сервиса:

- `postgres` — PostgreSQL 16, порт `127.0.0.1:5432`
- `backend` — FastAPI (uvicorn), внутренний порт `8000`
- `frontend` — Nginx со статикой React, порт `127.0.0.1:8080`

На продакшене перед контейнерами стоит **Nginx на хосте** с Let's Encrypt (HTTP → HTTPS, прокси на `:8080`).

---

## Стек технологий

| Слой | Технологии |
|------|------------|
| Frontend | React 19, TypeScript, Vite |
| Backend | Python 3.11, FastAPI, psycopg3 |
| БД | PostgreSQL 16 |
| Auth | bcrypt + JWT (PyJWT), токен в `localStorage` |
| AI | OpenAI-compatible API (aitunnel.ru, proxyapi.ru) |
| Контейнеры | Docker, Docker Compose |

---

## Структура проекта

```text
medical_consultant_app/
├── backend/
│   ├── app/
│   │   ├── main.py              # Точка входа FastAPI
│   │   ├── config.py            # Настройки из .env
│   │   ├── database.py          # Схема PostgreSQL, миграции через CREATE IF NOT EXISTS
│   │   ├── schemas.py           # Pydantic-модели запросов/ответов
│   │   ├── routers/             # HTTP-маршруты (/api/*)
│   │   └── services/            # Бизнес-логика (auth, LLM, анализ, PII-фильтр)
│   ├── tests/
│   ├── Dockerfile
│   └── pyproject.toml
├── frontend/
│   ├── src/
│   │   ├── App.tsx              # Главный UI и навигация
│   │   ├── api.ts               # HTTP-клиент к backend
│   │   ├── lib/auth.ts          # Хранение JWT в localStorage
│   │   └── components/          # Страницы, auth, чат, настройки
│   ├── Dockerfile
│   ├── nginx.conf               # Прокси /api → backend внутри контейнера
│   └── package.json
├── docker-compose.yml
├── .env.example                 # Шаблон секретов (без реальных значений)
├── .env                         # Локальные секреты (в .gitignore и .cursorignore)
├── .gitignore
├── .cursorignore
├── .cursorrules
└── README.md
```

---

## Аутентификация

Собственная система **Email / Password** без внешних auth-провайдеров.

### Как это работает

1. **Регистрация** — пользователь указывает имя, email, пароль (≥ 8 символов) и даёт согласие на обработку ПДн.
2. Backend создаёт запись в `users` (bcrypt-хеш пароля) и пустой `profiles`.
3. Backend выдаёт **JWT** (`access_token`), frontend сохраняет его в `localStorage`.
4. Все защищённые запросы отправляют заголовок `Authorization: Bearer <token>`.
5. Backend проверяет подпись JWT и актуальность пользователя в БД.

### Срок жизни сессии

По умолчанию JWT действует **7 суток** (`JWT_EXPIRE_MINUTES=10080`). Настраивается в `.env`.

### Восстановление пароля

Endpoints готовы, но для отправки писем нужен **SMTP** в `.env`. Без SMTP запрос «Забыли пароль?» вернёт `503`.

Поток после настройки SMTP:

1. `POST /api/auth/forgot-password` — генерируется одноразовый токен (30 минут), отправляется ссылка `{FRONTEND_URL}/?reset={token}`. Не чаще 1 запроса на email за 5 минут.
2. `POST /api/auth/reset-password` — новый пароль по токену; токен в БД хранится как SHA-256 и удаляется после использования.

### Удаление аккаунта

`DELETE /api/account` с `{ "confirm": true }` — безвозвратно удаляет:

- все медицинские данные (CASCADE от `profiles`);
- загруженные файлы с диска;
- запись пользователя в `users`.

---

## API

Базовый префикс: `/api`. Публичный health-check: `GET /health`.

### Auth

| Метод | Путь | Auth | Описание |
|-------|------|------|----------|
| `POST` | `/api/auth/register` | — | Регистрация `{ name, email, password, consent }` |
| `POST` | `/api/auth/login` | — | Вход `{ email, password }` → JWT |
| `GET` | `/api/auth/me` | JWT | Текущий пользователь |
| `POST` | `/api/auth/forgot-password` | — | Запрос сброса пароля (нужен SMTP) |
| `POST` | `/api/auth/reset-password` | — | Новый пароль `{ token, password }` |

### Account

| Метод | Путь | Auth | Описание |
|-------|------|------|----------|
| `DELETE` | `/api/account` | JWT | Hard delete `{ confirm: true }` |

### Profile

| Метод | Путь | Auth | Описание |
|-------|------|------|----------|
| `GET` | `/api/profile` | JWT | Медицинский профиль |
| `PUT` | `/api/profile` | JWT | Обновление профиля |

### Labs

| Метод | Путь | Auth | Описание |
|-------|------|------|----------|
| `GET` | `/api/labs` | JWT | Список анализов с трендами |
| `POST` | `/api/labs` | JWT | Добавить показатель |

### Documents

| Метод | Путь | Auth | Описание |
|-------|------|------|----------|
| `GET` | `/api/documents` | JWT | Список документов |
| `POST` | `/api/documents` | JWT | Загрузка файла (multipart) |

### Complaints & consultations

| Метод | Путь | Auth | Описание |
|-------|------|------|----------|
| `GET` | `/api/complaints` | JWT | История обращений |
| `POST` | `/api/complaints` | JWT | Новая жалоба |
| `POST` | `/api/complaints/{id}/compare-opinions` | JWT | Сравнение с мнением врача |
| `POST` | `/api/complaints/{id}/review` | JWT | Углублённый разбор |
| `POST` | `/api/consultations/chat` | JWT | Сообщение в чат консультации |

### Nutrition

| Метод | Путь | Auth | Описание |
|-------|------|------|----------|
| `POST` | `/api/nutrition/weekly-menu` | JWT | Генерация меню на неделю |

### Примеры

```bash
# Регистрация
curl -s -X POST http://127.0.0.1:8080/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"name":"Иван","email":"ivan@example.com","password":"Secret123!","consent":true}'

# Вход
curl -s -X POST http://127.0.0.1:8080/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"ivan@example.com","password":"Secret123!"}'

# Текущая сессия
curl -s http://127.0.0.1:8080/api/auth/me \
  -H "Authorization: Bearer <access_token>"
```

---

## База данных

Схема создаётся автоматически при старте backend (`initialize_database()`). Отдельных Alembic-миграций нет.

### Таблицы

| Таблица | Назначение |
|---------|------------|
| `users` | Учётные записи: email, bcrypt-хеш, согласие, токен сброса пароля |
| `profiles` | Медицинский профиль пользователя (1:1 с `users.id`) |
| `lab_results` | Лабораторные показатели |
| `documents` | Метаданные загруженных файлов |
| `complaints` | Жалобы и результаты AI-анализа |
| `consultations` | Сессии чата |
| `consultation_messages` | Сообщения в чате |

Связи: все медицинские таблицы ссылаются на `profiles.user_id` с `ON DELETE CASCADE`.

---

## Маршрутизация LLM

Backend выбирает модель по типу задачи. Ключи и модели задаются в `.env`.

| Задача | Переменная | Модель по умолчанию | Провайдер |
|--------|------------|---------------------|-----------|
| Чат, triage, симптомы | `SYMPTOMS_MODEL` | `qwen3.5-plus-02-15` | aitunnel.ru |
| Препараты, взаимодействия | `MEDICATIONS_MODEL` | `claude-sonnet-4.6` | aitunnel.ru |
| Нутрициолог, меню | `NUTRITION_MODEL` | `claude-sonnet-4.6` | aitunnel.ru |
| Сложные симптомы | `COMPLEX_SYMPTOMS_MODEL` | `deepseek-r1-0528` | aitunnel.ru |
| Углублённый разбор, сравнение мнений | `REVIEW_MODEL` | `claude-opus-4-7` | aitunnel.ru |
| Изображения (fallback OCR) | `IMAGING_MODEL` | `gpt-4o-mini` | proxyapi.ru |
| OCR документов (основной) | Yandex Vision | `page` | yandex.cloud |

**Автовыбор «сложного случая»** — по эвристике (длинный текст, несколько симптомов, хронические заболевания в профиле) или вручную через чекбокс в UI.

Если в профиле указаны препараты, после основного анализа дополнительно вызывается `MEDICATIONS_MODEL`.

---

## Сценарий «два мнения»

1. **Чат «Новое обращение»** — ассистент собирает анамнез и формирует **первое мнение** (гипотезы, план) **до** визита к врачу.
2. **Визит к врачу** — вы получаете **второе мнение** от очного специалиста.
3. **История обращений** — вводите мнение врача → «Сравнить мнения» → блоки: итог, совпадения, расхождения, рекомендации.

---

## Безопасность и ФЗ-152

- Регистрация **только** с явным чекбоксом согласия (`consent_accepted_at` в БД).
- Политика конфиденциальности открывается как страница SPA из настроек и с экрана регистрации. PDF-файл: `frontend/public/privacy-policy.pdf`.
- **Hard delete** — полное удаление аккаунта и всех данных по запросу пользователя.
- **Сброс пароля** — токен живёт 30 минут, одноразовый, в БД хранится SHA-256; rate limit 1 запрос / 5 мин на email.
- **PII-фильтр** в чате маскирует паспорт, СНИЛС, ИНН, телефон, email, ФИО, адрес перед отправкой в LLM.
- Секреты хранятся **только** в `.env` (не в коде, не в git).
- Пароли — **bcrypt**, сессии — **подписанные JWT**.
- PostgreSQL и uploads доступны только внутри Docker-сети / localhost.

---

## Переменные окружения

Скопируйте шаблон и заполните значения:

```bash
cp .env.example .env
```

### Обязательные

| Переменная | Описание |
|------------|----------|
| `POSTGRES_PASSWORD` | Пароль PostgreSQL |
| `DATABASE_URL` | Строка подключения (в Docker: `postgresql://medical:...@postgres:5432/medical_consultant`) |
| `JWT_SECRET` | Секрет для подписи JWT. Сгенерировать: `python -c "import secrets; print(secrets.token_hex(32))"` |
| `AITUNNEL_API_KEY` | API-ключ aitunnel.ru для основных LLM |

### Аутентификация

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `JWT_ALGORITHM` | `HS256` | Алгоритм JWT |
| `JWT_EXPIRE_MINUTES` | `10080` | Срок жизни токена (7 дней) |
| `FRONTEND_URL` | `https://помощники-консультанты.рф` | Базовый URL для ссылок сброса пароля |

### SMTP (опционально, для восстановления пароля)

| Переменная | Описание |
|------------|----------|
| `SMTP_HOST` | SMTP-сервер |
| `SMTP_PORT` | Порт (обычно `587`) |
| `SMTP_USERNAME` | Логин |
| `SMTP_PASSWORD` | Пароль |
| `SMTP_FROM_EMAIL` | Адрес отправителя |
| `SMTP_USE_TLS` | `true` / `false` |

### LLM (опционально, есть значения по умолчанию)

| Переменная | Описание |
|------------|----------|
| `PROXYAPI_API_KEY` | Ключ proxyapi.ru (fallback OCR / изображения) |
| `YANDEX_OCR_API_KEY` | API-ключ сервисного аккаунта Yandex Vision OCR |
| `YANDEX_OCR_FOLDER_ID` | Folder ID в Yandex Cloud (рекомендуется) |
| `YANDEX_OCR_CREDITS_PER_PAGE` | Списание кредитов за страницу OCR (по умолчанию `2`) |
| `SYMPTOMS_MODEL`, `MEDICATIONS_MODEL`, … | Переопределение моделей |
| `AITUNNEL_BASE_URL`, `PROXYAPI_BASE_URL`, `YANDEX_OCR_BASE_URL` | Base URL провайдеров |

### Прочее

| Переменная | Описание |
|------------|----------|
| `APP_ENV` | `production` / `development` / `test` |
| `APP_NAME` | Название в `/health` |
| `UPLOADS_DIR` | Каталог загрузок (в Docker: `/app/data/uploads`) |
| `VITE_API_BASE_URL` | Base URL API для frontend (в Docker пусто — nginx проксирует `/api`) |

> **Не коммитьте `.env`.** Файл в `.gitignore` и `.cursorignore`.

---

## Быстрый старт (локально)

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate          # Linux/macOS
# .venv\Scripts\activate           # Windows

python -m pip install -e ".[dev]"
export DATABASE_URL="postgresql://medical:medical@localhost:5432/medical_consultant"
export JWT_SECRET="dev-local-secret"
uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
export VITE_API_BASE_URL="http://127.0.0.1:8000"
npm run dev
```

Откройте `http://localhost:5173`.

---

## Запуск в Docker

```bash
cp .env.example .env
# Заполните JWT_SECRET, AITUNNEL_API_KEY, POSTGRES_PASSWORD

docker compose up --build -d
docker compose ps
curl -s http://127.0.0.1:8080/health
```

После изменения `.env`:

```bash
docker compose up -d --force-recreate backend
# если менялся frontend:
docker compose build frontend && docker compose up -d --force-recreate frontend
```

Логи:

```bash
docker compose logs -f backend
docker compose logs -f frontend
```

---

## Продакшен-деплой

Текущая конфигурация сервера:

| Параметр | Значение |
|----------|----------|
| Путь приложения | `/opt/medical_consultant_app/` |
| Домен | `https://помощники-консультанты.рф/` |
| Nginx | HTTP → HTTPS, `/` → `127.0.0.1:8080` |
| SSL | Let's Encrypt (certbot) |
| Ops-мониторинг | `/opt/medical-consultant-ops/` → `/ops/status`, `/ops/health` |

Типовой деплой после `git pull`:

```bash
cd /opt/medical_consultant_app
docker compose build
docker compose up -d --force-recreate
curl -sk https://помощники-консультанты.рф/health
```

---

## Тестирование и линтер

```bash
cd backend
python -m pip install -e ".[dev]"
python -m pytest -q
python -m ruff check .
python -m ruff format .
```

В тестах (`APP_ENV=test`) работает упрощённый вход: `Authorization: Bearer test-user`.

---

## Типичные проблемы

| Симптом | Решение |
|---------|---------|
| `401` на всех `/api/*` после входа | Проверьте `JWT_SECRET` — он должен совпадать между перезапусками backend |
| «Восстановление пароля недоступно» | Настройте SMTP в `.env` |
| AI не отвечает / `no_api_key` | Проверьте `AITUNNEL_API_KEY` в `.env`, перезапустите backend |
| Долгий ответ / `504` | Модель перегружена; отключите «Сложный случай» или повторите позже |
| Изменения frontend не видны | `docker compose build frontend --no-cache && docker compose up -d --force-recreate frontend` |

---

## Связанные репозитории

| Репозиторий | Назначение |
|-------------|------------|
| [alex2180369/medical_consultant](https://github.com/alex2180369/medical_consultant) | Основное приложение (этот репозиторий) |
| [alex2180369/medical-consultant-ops](https://github.com/alex2180369/medical-consultant-ops) | Мониторинг, watchdog, ops API |

---

## Лицензия и ответственность

Проект предназначен для личного информационного использования. Разработчики не несут ответственности за медицинские решения, принятые пользователем на основе рекомендаций ИИ.
