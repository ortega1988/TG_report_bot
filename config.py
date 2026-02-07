import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
DB_PATH = Path(os.getenv("DB_PATH", "data/bug_reports.db"))

WEBAPP_URL = os.getenv("WEBAPP_URL", "")
WEBAPP_PORT = int(os.getenv("WEBAPP_PORT", "8080"))

TELEGRAM_LOCAL = os.getenv("TELEGRAM_LOCAL", "").lower() in ("true", "1", "yes")
TELEGRAM_API_ID = os.getenv("TELEGRAM_API_ID", "")
TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH", "")
TELEGRAM_API_URL = os.getenv("TELEGRAM_API_URL", "http://localhost:8081")
TELEGRAM_LOCAL_FILES_DIR = Path(os.getenv("TELEGRAM_LOCAL_FILES_DIR", "data/telegram-files"))

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не установлен в переменных окружения")

if TELEGRAM_LOCAL and (not TELEGRAM_API_ID or not TELEGRAM_API_HASH):
    raise ValueError("TELEGRAM_API_ID и TELEGRAM_API_HASH обязательны при TELEGRAM_LOCAL=true")
