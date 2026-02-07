# Telegram Bot API Server (Local)

Локальный сервер Telegram Bot API позволяет:
- Загружать файлы до 2GB (вместо 50MB)
- Отправлять файлы по локальному пути (мгновенно, без повторной передачи)
- Работать быстрее за счёт локальной обработки

## Установка

### 1. Получить API credentials

1. Перейти на https://my.telegram.org
2. Войти по номеру телефона
3. Перейти в "API development tools"
4. Создать приложение (название любое)
5. Скопировать `api_id` и `api_hash`

### 2. Скачать telegram-bot-api.exe

Скачать готовый билд для Windows:
- https://github.com/aiogram/telegram-bot-api/releases

Или собрать самому:
- https://github.com/tdlib/telegram-bot-api

Положить `telegram-bot-api.exe` в эту папку.

### 3. Настроить .env

Добавить в `.env` файл проекта:

```
TELEGRAM_API_ID=12345678
TELEGRAM_API_HASH=abcdef1234567890abcdef1234567890
TELEGRAM_LOCAL=true
```

### 4. Запуск

Использовать `start.bat` в корне проекта — он запустит и Bot API Server, и бота.

Или вручную:

```cmd
telegram-bot-api.exe --api-id=YOUR_API_ID --api-hash=YOUR_API_HASH --local --dir=./data
```

## Порты

- `8081` — HTTP API (используется ботом)
- `8082` — Statistics (опционально)

## Файлы

При использовании локального API, файлы можно отправлять по пути:
```python
# Вместо загрузки файла через HTTP:
InputFile("C:/path/to/file.mp4")

# Просто указываем путь (мгновенно):
InputFile("file:///C:/path/to/file.mp4")
```
