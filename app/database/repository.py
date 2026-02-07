from typing import Optional, List
from .connection import Database
from .models import BugReport

ALLOWED_UPDATE_FIELDS = frozenset({
    "user_login", "platform", "platform_version", "error_time",
    "server", "subscriber_info", "description", "media_file_id",
    "media_type", "message_id", "tracking_id", "status",
    "status_comment", "status_changed_by",
})


class BugReportRepository:
    """Репозиторий для CRUD операций с баг-репортами"""

    def __init__(self, db: Database):
        self.db = db

    async def get_next_report_number(self, chat_id: int) -> int:
        """Получить следующий номер репорта для чата"""
        cursor = await self.db.connection.execute(
            "SELECT MAX(report_number) FROM bug_reports WHERE chat_id = ?",
            (chat_id,)
        )
        result = await cursor.fetchone()
        await cursor.close()
        max_num = result[0] if result[0] else 0
        return max_num + 1

    async def create(self, report: BugReport) -> int:
        """Создать новый баг-репорт с атомарным присвоением номера"""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                cursor = await self.db.connection.execute(
                    """
                    INSERT INTO bug_reports
                    (report_number, chat_id, user_id, username, user_login, platform,
                     platform_version, error_time, server, subscriber_info,
                     description, media_file_id, media_type, message_id, tracking_id, status)
                    VALUES (
                        (SELECT COALESCE(MAX(report_number), 0) + 1 FROM bug_reports WHERE chat_id = ?),
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                    )
                    """,
                    (
                        report.chat_id,
                        report.chat_id, report.user_id,
                        report.username, report.user_login, report.platform,
                        report.platform_version, report.error_time, report.server,
                        report.subscriber_info, report.description,
                        report.media_file_id, report.media_type, report.message_id,
                        report.tracking_id, report.status
                    )
                )
                await self.db.connection.commit()
                report_id = cursor.lastrowid
                await cursor.close()

                created = await self.get_by_id(report_id)
                if created:
                    report.report_number = created.report_number

                return report_id
            except Exception as e:
                if "UNIQUE constraint failed" in str(e) and attempt < max_retries - 1:
                    continue
                raise

    async def get_by_id(self, report_id: int) -> Optional[BugReport]:
        """Получить репорт по ID"""
        cursor = await self.db.connection.execute(
            "SELECT * FROM bug_reports WHERE id = ?", (report_id,)
        )
        row = await cursor.fetchone()
        await cursor.close()
        if row:
            return self._row_to_report(row)
        return None

    async def get_by_chat_and_number(
        self, chat_id: int, report_number: int
    ) -> Optional[BugReport]:
        """Получить репорт по ID чата и номеру репорта"""
        cursor = await self.db.connection.execute(
            "SELECT * FROM bug_reports WHERE chat_id = ? AND report_number = ?",
            (chat_id, report_number)
        )
        row = await cursor.fetchone()
        await cursor.close()
        if row:
            return self._row_to_report(row)
        return None

    async def get_by_user(
        self, user_id: int, chat_id: Optional[int] = None,
        limit: int = 100, offset: int = 0
    ) -> List[BugReport]:
        """Получить репорты пользователя с пагинацией"""
        if chat_id:
            cursor = await self.db.connection.execute(
                "SELECT * FROM bug_reports WHERE user_id = ? AND chat_id = ? "
                "ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (user_id, chat_id, limit, offset)
            )
        else:
            cursor = await self.db.connection.execute(
                "SELECT * FROM bug_reports WHERE user_id = ? "
                "ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (user_id, limit, offset)
            )
        rows = await cursor.fetchall()
        await cursor.close()
        return [self._row_to_report(row) for row in rows]

    async def get_by_chat(
        self, chat_id: int, status: Optional[str] = None,
        limit: int = 200, offset: int = 0
    ) -> List[BugReport]:
        """Получить репорты чата с фильтрацией по статусу и пагинацией"""
        if status:
            cursor = await self.db.connection.execute(
                "SELECT * FROM bug_reports WHERE chat_id = ? AND status = ? "
                "ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (chat_id, status, limit, offset)
            )
        else:
            cursor = await self.db.connection.execute(
                "SELECT * FROM bug_reports WHERE chat_id = ? "
                "ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (chat_id, limit, offset)
            )
        rows = await cursor.fetchall()
        await cursor.close()
        return [self._row_to_report(row) for row in rows]

    async def get_stats(self, chat_id: int) -> dict:
        """Получить статистику репортов чата"""
        cursor = await self.db.connection.execute(
            """SELECT
                COUNT(*) as total,
                SUM(CASE WHEN status = 'new' OR status IS NULL THEN 1 ELSE 0 END) as new,
                SUM(CASE WHEN status = 'in_progress' THEN 1 ELSE 0 END) as in_progress,
                SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed
            FROM bug_reports WHERE chat_id = ?""",
            (chat_id,)
        )
        row = await cursor.fetchone()
        await cursor.close()
        return {
            "total": row[0] or 0,
            "new": row[1] or 0,
            "in_progress": row[2] or 0,
            "completed": row[3] or 0
        }

    async def search(
        self, chat_id: int, query: str,
        limit: int = 50, offset: int = 0
    ) -> List[BugReport]:
        """Поиск репортов по тексту"""
        search_pattern = f"%{query}%"
        cursor = await self.db.connection.execute(
            """SELECT * FROM bug_reports
            WHERE chat_id = ? AND (
                description LIKE ? OR user_login LIKE ? OR
                subscriber_info LIKE ? OR tracking_id LIKE ?
                OR CAST(report_number AS TEXT) = ?
            )
            ORDER BY created_at DESC LIMIT ? OFFSET ?""",
            (chat_id, search_pattern, search_pattern,
             search_pattern, search_pattern, query, limit, offset)
        )
        rows = await cursor.fetchall()
        await cursor.close()
        return [self._row_to_report(row) for row in rows]

    async def update(self, report_id: int, **fields) -> bool:
        """Обновить поля репорта"""
        if not fields:
            return False

        invalid = set(fields.keys()) - ALLOWED_UPDATE_FIELDS
        if invalid:
            raise ValueError(f"Недопустимые поля: {invalid}")

        set_clause = ", ".join(f"{k} = ?" for k in fields.keys())
        values = list(fields.values()) + [report_id]

        cursor = await self.db.connection.execute(
            f"UPDATE bug_reports SET {set_clause}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            values
        )
        await self.db.connection.commit()
        rows_affected = cursor.rowcount
        await cursor.close()
        return rows_affected > 0

    async def update_message_id(self, report_id: int, message_id: int) -> bool:
        """Обновить ID сообщения"""
        return await self.update(report_id, message_id=message_id)

    async def set_tracking_id(self, report_id: int, tracking_id: str) -> bool:
        """Установить Tracking ID"""
        return await self.update(report_id, tracking_id=tracking_id)

    async def set_status(self, report_id: int, status: str) -> bool:
        """Установить статус"""
        return await self.update(report_id, status=status)

    async def export_chat_reports(self, chat_id: int) -> List[BugReport]:
        """Экспорт всех репортов чата для CSV"""
        cursor = await self.db.connection.execute(
            "SELECT * FROM bug_reports WHERE chat_id = ? ORDER BY report_number ASC",
            (chat_id,)
        )
        rows = await cursor.fetchall()
        await cursor.close()
        return [self._row_to_report(row) for row in rows]

    def _row_to_report(self, row) -> BugReport:
        """Конвертация строки БД в объект BugReport"""
        return BugReport(
            id=row["id"],
            report_number=row["report_number"],
            chat_id=row["chat_id"],
            user_id=row["user_id"],
            username=row["username"],
            user_login=row["user_login"],
            platform=row["platform"],
            platform_version=row["platform_version"],
            error_time=row["error_time"],
            server=row["server"],
            subscriber_info=row["subscriber_info"],
            description=row["description"],
            media_file_id=row["media_file_id"],
            media_type=row["media_type"],
            message_id=row["message_id"],
            tracking_id=row["tracking_id"] if "tracking_id" in row.keys() else None,
            status=row["status"] if "status" in row.keys() else "new",
            status_comment=row["status_comment"] if "status_comment" in row.keys() else None,
            status_changed_by=row["status_changed_by"] if "status_changed_by" in row.keys() else None,
            created_at=row["created_at"],
            updated_at=row["updated_at"]
        )
