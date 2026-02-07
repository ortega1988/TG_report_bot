from typing import Optional
from app.database.models import BugReport


def format_form_message(data: dict, current_step: str, prompt: str) -> str:
    """Сформировать сообщение с текущим состоянием формы"""
    lines = ["<b>Форма отчёта об ошибке</b>\n"]

    fields = [
        ("login", "Логин"),
        ("platform", "Платформа"),
        ("version", "Версия"),
        ("error_time", "Время ошибки"),
        ("server", "Сервер"),
        ("subscriber", "Абонент/Заявка"),
        ("description", "Описание"),
        ("media", "Медиа"),
    ]

    for field_key, field_name in fields:
        value = data.get(field_key)
        if value:
            if field_key == "media":
                lines.append(f"<b>{field_name}:</b> Прикреплено")
            else:
                display_value = _escape_html(str(value))
                lines.append(f"<b>{field_name}:</b> {display_value}")
        elif field_key == current_step:
            lines.append(f"<b>{field_name}:</b> <i>ожидание ввода...</i>")

    lines.append(f"\n{prompt}")
    return "\n".join(lines)


def format_report_preview(data: dict) -> str:
    """Сформировать предпросмотр перед отправкой"""
    lines = [
        "<b>Предпросмотр отчёта</b>",
        "━━━━━━━━━━━━━━━━━━━━",
        f"<b>Логин:</b> {_escape_html(data.get('login', 'N/A'))}",
        f"<b>Платформа:</b> {_escape_html(data.get('platform', 'N/A'))} {_escape_html(data.get('version', ''))}".strip(),
        f"<b>Время:</b> {_escape_html(data.get('error_time', 'N/A'))}",
        f"<b>Сервер:</b> {_escape_html(data.get('server', 'N/A'))}",
    ]

    if data.get('subscriber'):
        lines.append(f"<b>Абонент/Заявка:</b> {_escape_html(data['subscriber'])}")

    lines.append("")
    lines.append("<b>Описание:</b>")
    lines.append(_escape_html(data.get('description', 'N/A')))

    if data.get('media'):
        lines.append("")
        lines.append("<b>Медиа:</b> Прикреплено")

    return "\n".join(lines)


def format_final_report(
    report: BugReport,
    username: Optional[str] = None
) -> str:
    """Сформировать финальный отчёт для отправки в чат"""
    lines = [
        f"<b>Bug Report #{report.report_number}</b>",
        "━━━━━━━━━━━━━━━━━━━━",
        f"<b>Логин:</b> {_escape_html(report.user_login or '')}",
        f"<b>Платформа:</b> {_escape_html(report.platform or '')}",
        f"<b>Версия:</b> {_escape_html(report.platform_version or '')}",
        f"<b>Время:</b> {_escape_html(report.error_time or '')}",
        f"<b>Сервер:</b> {_escape_html(report.server or '')}",
    ]

    if report.subscriber_info:
        lines.append(f"<b>Абонент/Заявка:</b> {_escape_html(report.subscriber_info)}")

    lines.append("")
    lines.append("<b>Описание:</b>")
    lines.append(_escape_html(report.description or ''))

    lines.append("")
    if username:
        lines.append(f"<b>От:</b> @{_escape_html(username)}")
    else:
        lines.append(f"<b>От:</b> ID {report.user_id}")

    return "\n".join(lines)


def _escape_html(text: str) -> str:
    """Экранировать HTML-символы"""
    return (
        text
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
