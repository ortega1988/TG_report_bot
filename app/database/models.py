from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class BugReport:
    """Модель баг-репорта"""
    id: Optional[int]
    report_number: int
    chat_id: int
    user_id: int
    username: Optional[str]
    user_login: str
    platform: str
    platform_version: Optional[str]
    error_time: str
    server: str
    subscriber_info: Optional[str]
    description: str
    media_file_id: Optional[str] = None
    media_type: Optional[str] = None
    message_id: Optional[int] = None
    tracking_id: Optional[str] = None
    status: str = "new"
    status_comment: Optional[str] = None
    status_changed_by: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def to_dict(self, include_admin_fields: bool = False) -> dict:
        """Сериализация в словарь для API"""
        data = {
            "id": self.id,
            "report_number": self.report_number,
            "chat_id": self.chat_id,
            "user_login": self.user_login,
            "platform": self.platform,
            "platform_version": self.platform_version,
            "error_time": self.error_time,
            "server": self.server,
            "subscriber_info": self.subscriber_info,
            "description": self.description,
            "tracking_id": self.tracking_id,
            "status": self.status,
            "status_comment": self.status_comment,
            "created_at": self.created_at.isoformat() if isinstance(self.created_at, datetime) else self.created_at,
        }
        if include_admin_fields:
            data["user_id"] = self.user_id
            data["username"] = self.username
        return data
