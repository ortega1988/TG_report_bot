import aiosqlite
from pathlib import Path


class Database:
    """Менеджер подключения к SQLite"""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._connection: aiosqlite.Connection | None = None

    async def connect(self):
        """Подключение к БД и создание таблиц"""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = await aiosqlite.connect(self.db_path)
        self._connection.row_factory = aiosqlite.Row
        await self._init_schema()

    async def disconnect(self):
        """Закрытие подключения"""
        if self._connection:
            await self._connection.close()
            self._connection = None

    async def _init_schema(self):
        """Создание таблиц"""
        await self._connection.executescript("""
            CREATE TABLE IF NOT EXISTS bug_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_number INTEGER NOT NULL,
                chat_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                username TEXT,
                user_login TEXT NOT NULL,
                platform TEXT NOT NULL,
                platform_version TEXT,
                error_time TEXT NOT NULL,
                server TEXT NOT NULL,
                subscriber_info TEXT,
                description TEXT NOT NULL,
                media_file_id TEXT,
                media_type TEXT,
                message_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(chat_id, report_number)
            );

            CREATE INDEX IF NOT EXISTS idx_reports_chat
            ON bug_reports(chat_id);

            CREATE INDEX IF NOT EXISTS idx_reports_user
            ON bug_reports(user_id);
        """)
        await self._connection.commit()

        await self._migrate()

        await self._connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_reports_status
            ON bug_reports(status)
        """)
        await self._connection.commit()

    async def _migrate(self):
        """Миграция: добавление новых колонок"""
        cursor = await self._connection.execute("PRAGMA table_info(bug_reports)")
        columns = [row[1] for row in await cursor.fetchall()]

        if "tracking_id" not in columns:
            await self._connection.execute("ALTER TABLE bug_reports ADD COLUMN tracking_id TEXT")

        if "status" not in columns:
            await self._connection.execute("ALTER TABLE bug_reports ADD COLUMN status TEXT DEFAULT 'new'")

        if "status_comment" not in columns:
            await self._connection.execute("ALTER TABLE bug_reports ADD COLUMN status_comment TEXT")

        if "status_changed_by" not in columns:
            await self._connection.execute("ALTER TABLE bug_reports ADD COLUMN status_changed_by INTEGER")

        await self._connection.execute("""
            UPDATE bug_reports SET status = 'new'
            WHERE status IS NULL OR status = 'open'
        """)
        await self._connection.execute("""
            UPDATE bug_reports SET status = 'completed'
            WHERE status = 'resolved'
        """)
        await self._connection.execute("""
            UPDATE bug_reports SET status = 'trash'
            WHERE status = 'closed'
        """)

        await self._connection.commit()

    @property
    def connection(self) -> aiosqlite.Connection:
        """Получить подключение к БД"""
        if self._connection is None:
            raise RuntimeError("База данных не подключена")
        return self._connection
