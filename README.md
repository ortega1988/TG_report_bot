# Bug Report Bot

Telegram-бот для приёма баг-репортов через Web App с админ-панелью для управления заявками.

## Возможности

- **Web App форма** — удобная форма для отправки баг-репортов прямо в Telegram
- **Загрузка файлов** — скриншоты и видео до 500MB (до 2GB с локальным Bot API)
- **Админ-панель** — просмотр, фильтрация, поиск и управление статусами заявок
- **Уведомления** — автоматические уведомления пользователей об изменении статуса
- **Экспорт** — выгрузка отчётов в CSV
- **Пагинация** — загрузка заявок по страницам
- **Трекинг** — привязка Tracking ID к заявкам

## Структура проекта

```
├── bot.py                    # Точка входа
├── config.py                 # Конфигурация
├── requirements.txt          # Python зависимости
├── start.bat                 # Запуск (Windows)
├── stop.bat                  # Остановка (Windows)
├── .env.example              # Пример конфигурации
│
├── app/
│   ├── database/
│   │   ├── connection.py     # Подключение к SQLite
│   │   ├── models.py         # Модели данных
│   │   └── repository.py     # CRUD операции
│   ├── handlers/
│   │   └── webapp_handler.py # Обработчик команд бота
│   └── utils/
│       └── report_formatter.py # Форматирование отчётов
│
├── webapp/
│   ├── server.py             # HTTP сервер (aiohttp)
│   └── static/
│       ├── index.html        # Web App страница
│       ├── css/style.css     # Стили
│       └── js/app.js         # Логика Web App
│
├── telegram-bot-api/         # Локальный Bot API Server (опционально)
│   ├── telegram-bot-api.exe
│   └── README.md
│
├── data/                     # Данные (в .gitignore)
│   ├── bug_reports.db        # SQLite база
│   └── telegram-files/       # Файлы для локального API
│
└── tests/                    # Тесты
    ├── conftest.py
    ├── test_models.py
    ├── test_repository.py
    └── ...
```

## Установка

### 1. Клонировать репозиторий

```bash
git clone <repo-url>
cd OS_bot_telegram
```

### 2. Создать виртуальное окружение

```bash
python -m venv venv
venv\Scripts\activate  # Windows
# или
source venv/bin/activate  # Linux/Mac
```

### 3. Установить зависимости

```bash
pip install -r requirements.txt
```

### 4. Настроить переменные окружения

Скопировать `.env.example` в `.env` и заполнить:

```ini
BOT_TOKEN=your_bot_token_here
DB_PATH=data/bug_reports.db

# HTTPS URL для Web App (обязательно HTTPS!)
WEBAPP_URL=https://your-domain.com
WEBAPP_PORT=8080
```

### 5. Настроить HTTPS

Web App требует HTTPS. Варианты:

- **Продакшн**: настроить nginx/reverse proxy с SSL
- **Разработка**: использовать [ngrok](https://ngrok.com/):
  ```bash
  ngrok http 8080
  ```

### 6. Запустить бота

```bash
python bot.py
```

Или на Windows:
```bash
start.bat
```

## Использование

### Команды бота

- `/start` — приветствие и краткая справка
- `/bug` или `/bugreport` — открыть форму баг-репорта
- Отправить `/bug` в группу — бот пришлёт кнопку для открытия формы

### Статусы заявок

| Статус | Описание |
|--------|----------|
| Новая | Только что создана |
| Доработка | Требует дополнительной информации от пользователя |
| В работе | Взята в работу |
| Завершена | Исправлено |
| Отказ | Отклонена |

### Админ-панель

Админы чата видят кнопку "Админка" в Web App. Функции:

- Просмотр всех заявок чата
- Фильтрация по статусу
- Поиск по номеру, логину, описанию
- Изменение статуса и Tracking ID
- Экспорт в CSV

## Локальный Telegram Bot API (опционально)

Для загрузки файлов до 2GB и ускорения работы можно использовать локальный Bot API сервер.

### Настройка

1. Получить `API_ID` и `API_HASH` на https://my.telegram.org
2. Скачать [telegram-bot-api.exe](https://github.com/aiogram/telegram-bot-api/releases)
3. Положить в папку `telegram-bot-api/`
4. Добавить в `.env`:

```ini
TELEGRAM_LOCAL=true
TELEGRAM_API_ID=12345678
TELEGRAM_API_HASH=abcdef1234567890abcdef1234567890
TELEGRAM_API_URL=http://localhost:8081
TELEGRAM_LOCAL_FILES_DIR=data/telegram-files
```

5. Запустить через `start.bat` — он автоматически запустит Bot API сервер

Подробнее: [telegram-bot-api/README.md](telegram-bot-api/README.md)

## Тесты

```bash
pip install pytest pytest-asyncio
pytest
```

## API Endpoints

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/` | Web App страница |
| GET | `/health` | Health check |
| POST | `/api/report` | Создание репорта |
| POST | `/api/user-reports` | Репорты пользователя |
| POST | `/api/chat-reports` | Репорты чата (админ) |
| POST | `/api/search-reports` | Поиск репортов (админ) |
| POST | `/api/update-report` | Обновление репорта |
| POST | `/api/get-report` | Получение репорта по ID |
| POST | `/api/check-admin` | Проверка прав админа |
| POST | `/api/export-csv` | Экспорт в CSV (админ) |

## Технологии

- **Python 3.10+**
- **aiogram 3.x** — Telegram Bot Framework
- **aiohttp** — HTTP сервер
- **aiosqlite** — асинхронный SQLite
- **Telegram Web App** — клиентское приложение

## Лицензия

MIT
