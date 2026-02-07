import pytest

from app.database.models import BugReport
from app.database.repository import BugReportRepository


def _make_report(chat_id=-100123, user_id=111, **overrides) -> BugReport:
    defaults = dict(
        id=None,
        report_number=0,  # will be assigned atomically
        chat_id=chat_id,
        user_id=user_id,
        username="tester",
        user_login="test_login",
        platform="iOS",
        platform_version="17.0",
        error_time="2025-01-20 10:00",
        server="Corbina",
        subscriber_info=None,
        description="Test bug description",
    )
    defaults.update(overrides)
    return BugReport(**defaults)


class TestCreate:
    @pytest.mark.asyncio
    async def test_create_returns_id(self, repo):
        report = _make_report()
        report_id = await repo.create(report)
        assert report_id is not None
        assert report_id > 0

    @pytest.mark.asyncio
    async def test_auto_increments_report_number(self, repo):
        r1 = _make_report()
        r2 = _make_report()
        await repo.create(r1)
        await repo.create(r2)

        assert r1.report_number == 1
        assert r2.report_number == 2

    @pytest.mark.asyncio
    async def test_separate_chats_independent_numbers(self, repo):
        r1 = _make_report(chat_id=-100)
        r2 = _make_report(chat_id=-200)
        await repo.create(r1)
        await repo.create(r2)

        assert r1.report_number == 1
        assert r2.report_number == 1


class TestGetById:
    @pytest.mark.asyncio
    async def test_get_existing(self, repo):
        report = _make_report(description="unique desc")
        rid = await repo.create(report)

        fetched = await repo.get_by_id(rid)
        assert fetched is not None
        assert fetched.description == "unique desc"

    @pytest.mark.asyncio
    async def test_get_nonexistent(self, repo):
        result = await repo.get_by_id(99999)
        assert result is None


class TestGetByChatAndNumber:
    @pytest.mark.asyncio
    async def test_found(self, repo):
        report = _make_report(chat_id=-300)
        await repo.create(report)

        fetched = await repo.get_by_chat_and_number(-300, 1)
        assert fetched is not None
        assert fetched.chat_id == -300

    @pytest.mark.asyncio
    async def test_not_found(self, repo):
        result = await repo.get_by_chat_and_number(-999, 1)
        assert result is None


class TestGetByUser:
    @pytest.mark.asyncio
    async def test_returns_user_reports(self, repo):
        r1 = _make_report(user_id=555, chat_id=-400)
        r2 = _make_report(user_id=555, chat_id=-400)
        r3 = _make_report(user_id=666, chat_id=-400)
        await repo.create(r1)
        await repo.create(r2)
        await repo.create(r3)

        reports = await repo.get_by_user(555, chat_id=-400)
        assert len(reports) == 2

    @pytest.mark.asyncio
    async def test_pagination(self, repo):
        for _ in range(5):
            await repo.create(_make_report(user_id=777, chat_id=-500))

        page1 = await repo.get_by_user(777, chat_id=-500, limit=2, offset=0)
        page2 = await repo.get_by_user(777, chat_id=-500, limit=2, offset=2)

        assert len(page1) == 2
        assert len(page2) == 2


class TestGetByChat:
    @pytest.mark.asyncio
    async def test_returns_chat_reports(self, repo):
        for _ in range(3):
            await repo.create(_make_report(chat_id=-600))

        reports = await repo.get_by_chat(-600)
        assert len(reports) == 3

    @pytest.mark.asyncio
    async def test_filter_by_status(self, repo):
        r1 = _make_report(chat_id=-700)
        r2 = _make_report(chat_id=-700)
        id1 = await repo.create(r1)
        await repo.create(r2)
        await repo.update(id1, status="completed")

        completed = await repo.get_by_chat(-700, status="completed")
        assert len(completed) == 1
        assert completed[0].status == "completed"


class TestUpdate:
    @pytest.mark.asyncio
    async def test_update_fields(self, repo):
        report = _make_report(chat_id=-800)
        rid = await repo.create(report)

        success = await repo.update(rid, status="in_progress", tracking_id="TRK-99")
        assert success is True

        updated = await repo.get_by_id(rid)
        assert updated.status == "in_progress"
        assert updated.tracking_id == "TRK-99"

    @pytest.mark.asyncio
    async def test_rejects_invalid_fields(self, repo):
        report = _make_report(chat_id=-900)
        rid = await repo.create(report)

        with pytest.raises(ValueError, match="Invalid update fields"):
            await repo.update(rid, evil_column="DROP TABLE")

    @pytest.mark.asyncio
    async def test_update_nonexistent(self, repo):
        result = await repo.update(99999, status="new")
        assert result is False

    @pytest.mark.asyncio
    async def test_empty_update(self, repo):
        result = await repo.update(1)
        assert result is False


class TestSearch:
    @pytest.mark.asyncio
    async def test_search_by_description(self, repo):
        r = _make_report(chat_id=-1000, description="crash on login screen")
        await repo.create(r)

        results = await repo.search(-1000, "login screen")
        assert len(results) >= 1
        assert "login screen" in results[0].description

    @pytest.mark.asyncio
    async def test_search_by_report_number(self, repo):
        r = _make_report(chat_id=-1100)
        await repo.create(r)

        results = await repo.search(-1100, "1")
        assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_search_no_results(self, repo):
        results = await repo.search(-1200, "nonexistent_xyz_query")
        assert len(results) == 0


class TestExportChatReports:
    @pytest.mark.asyncio
    async def test_export_returns_all(self, repo):
        for _ in range(5):
            await repo.create(_make_report(chat_id=-1300))

        reports = await repo.export_chat_reports(-1300)
        assert len(reports) == 5

    @pytest.mark.asyncio
    async def test_export_ordered_by_number(self, repo):
        for _ in range(3):
            await repo.create(_make_report(chat_id=-1400))

        reports = await repo.export_chat_reports(-1400)
        numbers = [r.report_number for r in reports]
        assert numbers == sorted(numbers)
