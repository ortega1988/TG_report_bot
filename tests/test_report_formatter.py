from datetime import datetime

from app.database.models import BugReport
from app.utils.report_formatter import (
    format_final_report,
    format_form_message,
    format_report_preview,
)


def _make_report(**overrides) -> BugReport:
    defaults = dict(
        id=1,
        report_number=42,
        chat_id=-100123,
        user_id=999,
        username="johndoe",
        user_login="john_login",
        platform="Android",
        platform_version="14.0",
        error_time="2025-01-20 09:00",
        server="Beeline",
        subscriber_info="sub_555",
        description="Button doesn't work",
    )
    defaults.update(overrides)
    return BugReport(**defaults)


class TestFormatFinalReport:
    def test_contains_report_number(self):
        report = _make_report()
        text = format_final_report(report, username="johndoe")
        assert "Bug Report #42" in text

    def test_contains_all_fields(self):
        report = _make_report()
        text = format_final_report(report)
        assert "john_login" in text
        assert "Android" in text
        assert "14.0" in text
        assert "Beeline" in text
        assert "Button doesn't work" in text

    def test_username_shown_when_provided(self):
        report = _make_report()
        text = format_final_report(report, username="johndoe")
        assert "@johndoe" in text

    def test_user_id_shown_when_no_username(self):
        report = _make_report()
        text = format_final_report(report, username=None)
        assert "ID 999" in text

    def test_subscriber_info_shown(self):
        report = _make_report(subscriber_info="SUB-007")
        text = format_final_report(report)
        assert "SUB-007" in text

    def test_subscriber_info_omitted_when_empty(self):
        report = _make_report(subscriber_info=None)
        text = format_final_report(report)
        assert "Абонент" not in text

    def test_html_escaped(self):
        report = _make_report(description="<script>alert('xss')</script>")
        text = format_final_report(report)
        assert "<script>" not in text
        assert "&lt;script&gt;" in text


class TestFormatFormMessage:
    def test_shows_filled_fields(self):
        data = {"login": "user1", "platform": "iOS"}
        text = format_form_message(data, current_step="version", prompt="Введите версию:")
        assert "user1" in text
        assert "iOS" in text
        assert "ожидание ввода" in text

    def test_prompt_appended(self):
        text = format_form_message({}, current_step="login", prompt="Введите логин:")
        assert "Введите логин:" in text


class TestFormatReportPreview:
    def test_contains_key_info(self):
        data = {
            "login": "test_user",
            "platform": "Android",
            "version": "12.0",
            "error_time": "2025-01-01 00:00",
            "server": "Corbina",
            "description": "Something broke",
        }
        text = format_report_preview(data)
        assert "test_user" in text
        assert "Android" in text
        assert "Corbina" in text
        assert "Something broke" in text

    def test_subscriber_shown_when_present(self):
        data = {
            "login": "u",
            "platform": "iOS",
            "version": "1",
            "error_time": "t",
            "server": "s",
            "description": "d",
            "subscriber": "SUB-123",
        }
        text = format_report_preview(data)
        assert "SUB-123" in text
