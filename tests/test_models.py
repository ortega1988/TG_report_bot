from datetime import datetime

from app.database.models import BugReport


def _make_report(**overrides) -> BugReport:
    defaults = dict(
        id=1,
        report_number=5,
        chat_id=-1001234567890,
        user_id=123456,
        username="testuser",
        user_login="test_login",
        platform="iOS",
        platform_version="17.2",
        error_time="2025-01-15 10:30",
        server="Corbina",
        subscriber_info="sub_123",
        description="App crashes on launch",
        tracking_id="TRK-001",
        status="new",
        status_comment=None,
        created_at=datetime(2025, 1, 15, 10, 30, 0),
    )
    defaults.update(overrides)
    return BugReport(**defaults)


class TestBugReportToDict:
    def test_basic_fields(self):
        report = _make_report()
        d = report.to_dict()

        assert d["id"] == 1
        assert d["report_number"] == 5
        assert d["chat_id"] == -1001234567890
        assert d["user_login"] == "test_login"
        assert d["platform"] == "iOS"
        assert d["platform_version"] == "17.2"
        assert d["server"] == "Corbina"
        assert d["description"] == "App crashes on launch"
        assert d["tracking_id"] == "TRK-001"
        assert d["status"] == "new"

    def test_excludes_admin_fields_by_default(self):
        report = _make_report()
        d = report.to_dict()

        assert "user_id" not in d
        assert "username" not in d

    def test_includes_admin_fields_when_requested(self):
        report = _make_report()
        d = report.to_dict(include_admin_fields=True)

        assert d["user_id"] == 123456
        assert d["username"] == "testuser"

    def test_created_at_serialized_as_isoformat(self):
        report = _make_report(created_at=datetime(2025, 3, 10, 14, 0, 0))
        d = report.to_dict()

        assert d["created_at"] == "2025-03-10T14:00:00"

    def test_created_at_none(self):
        report = _make_report(created_at=None)
        d = report.to_dict()

        assert d["created_at"] is None
