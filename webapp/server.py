import csv
import hashlib
import hmac
import io
import json
import logging
import os
import re
import tempfile
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qsl

import aiofiles
from aiohttp import web

from aiogram.types import (
    FSInputFile, InputMediaPhoto, InputMediaVideo, InputMediaDocument,
    InlineKeyboardMarkup, InlineKeyboardButton,
)
from aiogram.exceptions import TelegramBadRequest

from app.database.models import BugReport
from app.utils.report_formatter import format_final_report
from config import WEBAPP_URL, TELEGRAM_LOCAL, TELEGRAM_LOCAL_FILES_DIR

STATIC_DIR = Path(__file__).parent / "static"
logger = logging.getLogger(__name__)

INIT_DATA_MAX_AGE = 86400
MAX_FILE_SIZE = 500 * 1024 * 1024
MAX_FILES = 10
TELEGRAM_SEND_TIMEOUT = 300

STATUS_LABELS = {
    'new': 'Новая',
    'revision': 'Доработка',
    'in_progress': 'В работе',
    'completed': 'Завершена',
    'trash': 'Отказ',
}


def _get_bot(request):
    return request.app["bot"]


def _get_repo(request):
    return request.app["report_repo"]


def _get_token(request):
    return request.app["bot_token"]


def validate_init_data(init_data: str, bot_token: str) -> dict | None:
    """Валидация init_data из Telegram WebApp"""
    try:
        parsed = dict(parse_qsl(init_data, keep_blank_values=True))

        if "hash" not in parsed:
            return None

        received_hash = parsed.pop("hash")

        data_check_arr = sorted([f"{k}={v}" for k, v in parsed.items()])
        data_check_string = "\n".join(data_check_arr)

        secret_key = hmac.new(
            b"WebAppData",
            bot_token.encode(),
            hashlib.sha256
        ).digest()

        calculated_hash = hmac.new(
            secret_key,
            data_check_string.encode(),
            hashlib.sha256
        ).hexdigest()

        if calculated_hash != received_hash:
            logger.warning("Неверный хэш init_data")
            return None

        auth_date = parsed.get("auth_date")
        if auth_date:
            try:
                auth_timestamp = int(auth_date)
                if time.time() - auth_timestamp > INIT_DATA_MAX_AGE:
                    logger.warning("init_data устарел")
                    return None
            except (ValueError, TypeError):
                logger.warning("Некорректный auth_date")
                return None

        if "user" in parsed:
            parsed["user"] = json.loads(parsed["user"])

        return parsed

    except Exception as e:
        logger.error(f"Ошибка валидации init_data: {e}")
        return None


def no_cache_response(file_path: Path) -> web.FileResponse:
    """Ответ без кэширования"""
    response = web.FileResponse(file_path)
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


async def get_chat_member_safe(bot, chat_id: int, user_id: int):
    """Получить участника чата с обработкой миграции"""
    try:
        return await bot.get_chat_member(chat_id, user_id)
    except TelegramBadRequest as e:
        if "migrated" in str(e).lower() or "upgraded" in str(e).lower():
            error_text = str(e)
            match = re.search(r'id[:\s]+(-?\d+)', error_text)
            if match:
                new_chat_id = int(match.group(1))
                logger.info(f"Чат мигрирован: {chat_id} → {new_chat_id}")
                try:
                    return await bot.get_chat_member(new_chat_id, user_id)
                except Exception:
                    pass
        raise


async def _check_admin(bot, chat_id: int, user_id: int) -> bool:
    """Проверить, является ли пользователь админом чата"""
    try:
        member = await get_chat_member_safe(bot, chat_id, user_id)
        return member.status in ("administrator", "creator")
    except Exception:
        return False


async def send_status_notification(bot, report, new_status: str):
    """Отправить уведомление пользователю об изменении статуса"""
    status_text = STATUS_LABELS.get(new_status, new_status)

    text = f"📋 <b>Статус вашей заявки #{report.report_number} изменён</b>\n\n"
    text += f"Новый статус: <b>{status_text}</b>"

    if new_status == 'revision' and report.status_comment:
        text += f"\n\n💬 <b>Комментарий:</b>\n{report.status_comment}"

    keyboard = None
    if new_status == 'revision':
        try:
            webapp_url = f"{WEBAPP_URL}?startapp={report.chat_id}_{report.id}"
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✏️ Редактировать заявку", url=webapp_url)]
            ])
        except Exception as e:
            logger.warning(f"Не удалось создать кнопку: {e}")

    try:
        await bot.send_message(
            chat_id=report.user_id,
            text=text,
            parse_mode="HTML",
            reply_markup=keyboard
        )
        logger.info(f"Уведомление отправлено пользователю {report.user_id}")
    except Exception as e:
        logger.warning(f"Не удалось отправить уведомление: {e}")


async def send_revision_completed_notification(bot, report, admin_user_id: int):
    """Отправить уведомление админу о доработке заявки"""
    text = f"✅ <b>Заявка #{report.report_number} доработана</b>\n\n"
    text += f"Пользователь @{report.username or report.user_id} внёс изменения."

    keyboard = None
    try:
        webapp_url = f"{WEBAPP_URL}?startapp=admin_{report.chat_id}_{report.id}"
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📋 Открыть заявку", url=webapp_url)]
        ])
    except Exception as e:
        logger.warning(f"Не удалось создать кнопку: {e}")

    try:
        await bot.send_message(
            chat_id=admin_user_id,
            text=text,
            parse_mode="HTML",
            reply_markup=keyboard
        )
        logger.info(f"Уведомление о доработке отправлено админу {admin_user_id}")
    except Exception as e:
        logger.warning(f"Не удалось отправить уведомление админу: {e}")


@web.middleware
async def request_logging_middleware(request, handler):
    """Логирование HTTP-запросов"""
    start = time.monotonic()
    try:
        response = await handler(request)
        elapsed = (time.monotonic() - start) * 1000
        logger.info(f"{request.method} {request.path} → {response.status} ({elapsed:.0f}ms)")
        return response
    except web.HTTPException as e:
        elapsed = (time.monotonic() - start) * 1000
        logger.info(f"{request.method} {request.path} → {e.status} ({elapsed:.0f}ms)")
        raise
    except Exception as e:
        elapsed = (time.monotonic() - start) * 1000
        logger.error(f"{request.method} {request.path} → 500 ({elapsed:.0f}ms) {e}")
        raise


async def health(request):
    """Health check"""
    return web.json_response({"status": "ok"})


async def index(request):
    """Главная страница Web App"""
    return no_cache_response(STATIC_DIR / "index.html")


async def handle_report(request):
    """Обработка отправки баг-репорта"""
    bot = _get_bot(request)
    repo = _get_repo(request)
    bot_token = _get_token(request)
    temp_files = []

    try:
        reader = await request.multipart()

        data = {}
        media_files = []

        while True:
            part = await reader.next()
            if part is None:
                break

            if part.name == "media":
                if len(media_files) >= MAX_FILES:
                    return web.json_response(
                        {"success": False, "error": f"Максимум {MAX_FILES} файлов"},
                        status=400
                    )

                media_filename = part.filename
                media_content_type = part.headers.get("Content-Type", "application/octet-stream")

                suffix = Path(media_filename).suffix if media_filename else ""

                if TELEGRAM_LOCAL:
                    import uuid
                    TELEGRAM_LOCAL_FILES_DIR.mkdir(parents=True, exist_ok=True)
                    unique_name = f"{uuid.uuid4().hex}{suffix}"
                    temp_path = str(TELEGRAM_LOCAL_FILES_DIR / unique_name)
                    temp_fd = os.open(temp_path, os.O_CREAT | os.O_WRONLY, 0o644)
                else:
                    temp_fd, temp_path = tempfile.mkstemp(suffix=suffix)
                    temp_files.append(temp_path)

                file_size = 0
                try:
                    async with aiofiles.open(temp_path, 'wb') as f:
                        while True:
                            chunk = await part.read_chunk(8192)
                            if not chunk:
                                break
                            file_size += len(chunk)
                            if file_size > MAX_FILE_SIZE:
                                max_size_mb = MAX_FILE_SIZE // (1024 * 1024)
                                return web.json_response(
                                    {"success": False, "error": f"Файл слишком большой (макс. {max_size_mb}MB)"},
                                    status=400
                                )
                            await f.write(chunk)
                finally:
                    os.close(temp_fd)

                media_files.append((temp_path, media_filename, media_content_type))
            else:
                value = await part.text()
                data[part.name] = value

        init_data = data.get("init_data", "")
        validated = validate_init_data(init_data, bot_token)

        if not validated:
            logger.warning("Невалидный init_data")

        user_data = validated.get("user", {}) if validated else {}
        user_id = user_data.get("id") or 0
        username = user_data.get("username")

        chat_id = None

        if data.get("chat_id"):
            try:
                chat_id = int(data["chat_id"])
            except ValueError:
                pass

        if not chat_id and validated and "chat" in validated:
            chat_data = json.loads(validated["chat"]) if isinstance(validated["chat"], str) else validated["chat"]
            chat_id = chat_data.get("id")

        if not chat_id:
            chat_id = user_id

        error_time = data.get("error_time", "")
        if error_time:
            try:
                dt = datetime.fromisoformat(error_time)
                error_time = dt.strftime("%Y-%m-%d %H:%M")
            except ValueError:
                pass

        prepared_media = []
        for temp_path, media_filename, media_content_type in media_files:
            input_file = FSInputFile(temp_path, filename=media_filename or "file")

            if media_content_type.startswith("image/"):
                media_type = "photo"
            elif media_content_type.startswith("video/"):
                media_type = "video"
            else:
                media_type = "document"

            prepared_media.append((input_file, media_type))

        first_media_type = prepared_media[0][1] if prepared_media else None

        report = BugReport(
            id=None,
            report_number=0,
            chat_id=chat_id,
            user_id=user_id,
            username=username,
            user_login=data.get("login", ""),
            platform=data.get("platform", ""),
            platform_version=data.get("version"),
            error_time=error_time,
            server=data.get("server", ""),
            subscriber_info=data.get("subscriber"),
            description=data.get("description", ""),
            media_file_id=None,
            media_type=first_media_type,
            message_id=None
        )

        report_id = await repo.create(report)
        report.id = report_id

        final_text = format_final_report(report, username)

        async def send_single_media(input_file, media_type, caption_text):
            """Отправка одного медиафайла"""
            try:
                if media_type == "photo":
                    return await bot.send_photo(
                        chat_id=chat_id, photo=input_file,
                        caption=caption_text, parse_mode="HTML",
                        request_timeout=TELEGRAM_SEND_TIMEOUT
                    )
                elif media_type == "video":
                    return await bot.send_video(
                        chat_id=chat_id, video=input_file,
                        caption=caption_text, parse_mode="HTML",
                        request_timeout=TELEGRAM_SEND_TIMEOUT
                    )
                else:
                    return await bot.send_document(
                        chat_id=chat_id, document=input_file,
                        caption=caption_text, parse_mode="HTML",
                        request_timeout=TELEGRAM_SEND_TIMEOUT
                    )
            except TelegramBadRequest as e:
                error_msg = str(e).lower()
                if "image_process_failed" in error_msg or "wrong file" in error_msg:
                    logger.warning(f"Ошибка обработки медиа, отправляю как документ: {e}")
                    new_input_file = FSInputFile(input_file.path, filename=input_file.filename)
                    return await bot.send_document(
                        chat_id=chat_id, document=new_input_file,
                        caption=caption_text, parse_mode="HTML",
                        request_timeout=TELEGRAM_SEND_TIMEOUT
                    )
                raise

        if len(prepared_media) > 1:
            media_group = []
            for i, (input_file, media_type) in enumerate(prepared_media):
                caption = final_text if i == 0 else None
                parse_mode = "HTML" if i == 0 else None

                if media_type == "photo":
                    media_group.append(InputMediaPhoto(media=input_file, caption=caption, parse_mode=parse_mode))
                elif media_type == "video":
                    media_group.append(InputMediaVideo(media=input_file, caption=caption, parse_mode=parse_mode))
                else:
                    media_group.append(InputMediaDocument(media=input_file, caption=caption, parse_mode=parse_mode))

            try:
                sent_messages = await bot.send_media_group(
                    chat_id=chat_id, media=media_group,
                    request_timeout=TELEGRAM_SEND_TIMEOUT
                )
                report_msg = sent_messages[0]
            except TelegramBadRequest as e:
                error_msg = str(e).lower()
                if "image_process_failed" in error_msg or "wrong file" in error_msg:
                    logger.warning(f"Ошибка группы медиа, отправляю по отдельности: {e}")
                    report_msg = await bot.send_message(
                        chat_id=chat_id, text=final_text, parse_mode="HTML"
                    )
                    for temp_path, media_filename, _ in media_files:
                        try:
                            doc_file = FSInputFile(temp_path, filename=media_filename or "file")
                            await bot.send_document(
                                chat_id=chat_id, document=doc_file,
                                request_timeout=TELEGRAM_SEND_TIMEOUT
                            )
                        except Exception as doc_e:
                            logger.warning(f"Не удалось отправить файл {media_filename}: {doc_e}")
                else:
                    raise

        elif len(prepared_media) == 1:
            input_file, media_type = prepared_media[0]
            report_msg = await send_single_media(input_file, media_type, final_text)
        else:
            report_msg = await bot.send_message(
                chat_id=chat_id, text=final_text, parse_mode="HTML"
            )

        await repo.update_message_id(report_id, report_msg.message_id)

        logger.info(f"Репорт #{report.report_number} создан для чата {chat_id}")

        return web.json_response({"success": True, "report_number": report.report_number})

    except ConnectionResetError:
        logger.warning("Клиент отключился во время загрузки")
        return web.json_response({"success": False, "error": "Соединение прервано"}, status=499)

    except Exception as e:
        logger.exception(f"Ошибка обработки репорта: {e}")
        return web.json_response({"success": False, "error": "Внутренняя ошибка сервера"}, status=500)

    finally:
        for temp_path in temp_files:
            try:
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
            except Exception as e:
                logger.warning(f"Не удалось удалить временный файл {temp_path}: {e}")


async def api_get_user_reports(request):
    """Получить репорты текущего пользователя"""
    try:
        data = await request.json()
        init_data = data.get("init_data", "")
        chat_id = data.get("chat_id")
        limit = min(int(data.get("limit", 20)), 100)
        offset = int(data.get("offset", 0))

        validated = validate_init_data(init_data, _get_token(request))
        if not validated:
            return web.json_response({"success": False, "error": "Unauthorized"}, status=401)

        user_data = validated.get("user", {})
        user_id = user_data.get("id")

        if not user_id:
            return web.json_response({"success": False, "error": "User not found"}, status=400)

        repo = _get_repo(request)
        reports = await repo.get_by_user(user_id, chat_id, limit=limit + 1, offset=offset)

        has_more = len(reports) > limit
        if has_more:
            reports = reports[:limit]

        reports_data = [r.to_dict() for r in reports]

        return web.json_response({"success": True, "reports": reports_data, "has_more": has_more})

    except Exception as e:
        logger.exception(f"Ошибка получения репортов: {e}")
        return web.json_response({"success": False, "error": "Ошибка загрузки репортов"}, status=500)


async def api_get_chat_reports(request):
    """Получить репорты чата (только для админов)"""
    try:
        data = await request.json()
        init_data = data.get("init_data", "")
        chat_id = data.get("chat_id")
        limit = min(int(data.get("limit", 20)), 100)
        offset = int(data.get("offset", 0))

        validated = validate_init_data(init_data, _get_token(request))
        if not validated:
            return web.json_response({"success": False, "error": "Unauthorized"}, status=401)

        user_data = validated.get("user", {})
        user_id = user_data.get("id")

        if not user_id or not chat_id:
            return web.json_response({"success": False, "error": "Missing parameters"}, status=400)

        bot = _get_bot(request)
        if not await _check_admin(bot, chat_id, user_id):
            return web.json_response({"success": False, "error": "Admin access required"}, status=403)

        repo = _get_repo(request)
        status_filter = data.get("status")
        include_stats = data.get("include_stats", False)

        reports = await repo.get_by_chat(chat_id, status_filter, limit=limit + 1, offset=offset)

        has_more = len(reports) > limit
        if has_more:
            reports = reports[:limit]

        reports_data = [r.to_dict(include_admin_fields=True) for r in reports]

        response = {"success": True, "reports": reports_data, "has_more": has_more}

        if include_stats:
            response["stats"] = await repo.get_stats(chat_id)

        return web.json_response(response)

    except Exception as e:
        logger.exception(f"Ошибка получения репортов чата: {e}")
        return web.json_response({"success": False, "error": "Ошибка загрузки репортов"}, status=500)


async def api_search_reports(request):
    """Поиск репортов в чате (только для админов)"""
    try:
        data = await request.json()
        init_data = data.get("init_data", "")
        chat_id = data.get("chat_id")
        query = data.get("query", "").strip()

        validated = validate_init_data(init_data, _get_token(request))
        if not validated:
            return web.json_response({"success": False, "error": "Unauthorized"}, status=401)

        user_data = validated.get("user", {})
        user_id = user_data.get("id")

        if not user_id or not chat_id or not query:
            return web.json_response({"success": False, "error": "Missing parameters"}, status=400)

        bot = _get_bot(request)
        if not await _check_admin(bot, chat_id, user_id):
            return web.json_response({"success": False, "error": "Admin access required"}, status=403)

        repo = _get_repo(request)
        reports = await repo.search(chat_id, query)

        reports_data = [r.to_dict(include_admin_fields=True) for r in reports]

        return web.json_response({"success": True, "reports": reports_data})

    except Exception as e:
        logger.exception(f"Ошибка поиска: {e}")
        return web.json_response({"success": False, "error": "Ошибка поиска"}, status=500)


async def api_export_csv(request):
    """Экспорт репортов в CSV (только для админов)"""
    try:
        data = await request.json()
        init_data = data.get("init_data", "")
        chat_id = data.get("chat_id")

        validated = validate_init_data(init_data, _get_token(request))
        if not validated:
            return web.json_response({"success": False, "error": "Unauthorized"}, status=401)

        user_data = validated.get("user", {})
        user_id = user_data.get("id")

        if not user_id or not chat_id:
            return web.json_response({"success": False, "error": "Missing parameters"}, status=400)

        bot = _get_bot(request)
        if not await _check_admin(bot, chat_id, user_id):
            return web.json_response({"success": False, "error": "Admin access required"}, status=403)

        repo = _get_repo(request)
        reports = await repo.export_chat_reports(chat_id)

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "ID", "Номер", "Логин", "Платформа", "Версия",
            "Время ошибки", "Сервер", "Абонент/Заявка",
            "Описание", "Tracking ID", "Статус", "Дата создания",
            "Username", "User ID",
        ])
        for r in reports:
            writer.writerow([
                r.id, r.report_number, r.user_login, r.platform,
                r.platform_version, r.error_time, r.server,
                r.subscriber_info, r.description, r.tracking_id,
                STATUS_LABELS.get(r.status, r.status),
                r.created_at.isoformat() if r.created_at else "",
                r.username or "", r.user_id,
            ])

        csv_content = output.getvalue()

        return web.Response(
            text=csv_content,
            content_type="text/csv",
            charset="utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="reports_chat_{chat_id}.csv"'
            }
        )

    except Exception as e:
        logger.exception(f"Ошибка экспорта: {e}")
        return web.json_response({"success": False, "error": "Ошибка экспорта"}, status=500)


async def api_update_report(request):
    """Обновление репорта"""
    try:
        data = await request.json()
        init_data = data.get("init_data", "")
        report_id = data.get("report_id")

        validated = validate_init_data(init_data, _get_token(request))
        if not validated:
            return web.json_response({"success": False, "error": "Unauthorized"}, status=401)

        user_data = validated.get("user", {})
        user_id = user_data.get("id")

        if not user_id or not report_id:
            return web.json_response({"success": False, "error": "Missing parameters"}, status=400)

        bot = _get_bot(request)
        repo = _get_repo(request)

        report = await repo.get_by_id(report_id)
        if not report:
            return web.json_response({"success": False, "error": "Report not found"}, status=404)

        is_owner = report.user_id == user_id
        is_admin = await _check_admin(bot, report.chat_id, user_id)

        if not is_owner and not is_admin:
            return web.json_response({"success": False, "error": "Permission denied"}, status=403)

        if is_owner and not is_admin and report.status not in (None, "new", "revision"):
            return web.json_response({
                "success": False,
                "error": "Редактирование заблокировано: статус заявки изменён"
            }, status=403)

        update_fields = {}

        if is_owner or is_admin:
            for field in ("user_login", "platform", "platform_version", "error_time", "server", "subscriber_info", "description"):
                if field in data:
                    update_fields[field] = data[field]

        old_status = report.status
        old_status_changed_by = report.status_changed_by
        if is_admin:
            for field in ("tracking_id", "status", "status_comment"):
                if field in data:
                    update_fields[field] = data[field]

            if "status" in update_fields and update_fields["status"] == "revision":
                update_fields["status_changed_by"] = user_id

        user_fields_changed = any(
            f in update_fields for f in
            ("user_login", "platform", "platform_version", "error_time", "server", "subscriber_info", "description")
        )
        admin_changing_status = is_admin and "status" in data

        user_editing_revision = (
            is_owner and
            old_status == "revision" and
            old_status_changed_by and
            user_fields_changed and
            not admin_changing_status
        )

        if update_fields:
            if user_editing_revision:
                update_fields["status"] = "new"
                update_fields["status_comment"] = None

            await repo.update(report_id, **update_fields)

            updated_report = await repo.get_by_id(report_id)
            if updated_report and updated_report.message_id:
                try:
                    new_text = format_final_report(updated_report, updated_report.username)

                    if updated_report.media_type:
                        await bot.edit_message_caption(
                            chat_id=updated_report.chat_id,
                            message_id=updated_report.message_id,
                            caption=new_text,
                            parse_mode="HTML"
                        )
                    else:
                        await bot.edit_message_text(
                            chat_id=updated_report.chat_id,
                            message_id=updated_report.message_id,
                            text=new_text,
                            parse_mode="HTML"
                        )
                except Exception as e:
                    logger.warning(f"Не удалось обновить сообщение в Telegram: {e}")

            new_status = update_fields.get("status")
            if is_admin and new_status and new_status != old_status and updated_report.user_id:
                await send_status_notification(bot, updated_report, new_status)

            if user_editing_revision and old_status_changed_by:
                await send_revision_completed_notification(bot, updated_report, old_status_changed_by)

        return web.json_response({"success": True})

    except Exception as e:
        logger.exception(f"Ошибка обновления репорта: {e}")
        return web.json_response({"success": False, "error": "Ошибка обновления репорта"}, status=500)


async def api_check_admin(request):
    """Проверка прав админа"""
    try:
        data = await request.json()
        init_data = data.get("init_data", "")
        chat_id = data.get("chat_id")

        validated = validate_init_data(init_data, _get_token(request))
        if not validated:
            return web.json_response({"is_admin": False})

        user_data = validated.get("user", {})
        user_id = user_data.get("id")

        if not user_id or not chat_id:
            return web.json_response({"is_admin": False})

        bot = _get_bot(request)
        is_admin = await _check_admin(bot, chat_id, user_id)
        return web.json_response({"is_admin": is_admin})

    except Exception as e:
        logger.exception(f"Ошибка проверки админа: {e}")
        return web.json_response({"is_admin": False})


async def api_get_report(request):
    """Получить репорт по ID"""
    try:
        data = await request.json()
        init_data = data.get("init_data", "")
        report_id = data.get("report_id")

        validated = validate_init_data(init_data, _get_token(request))
        if not validated:
            return web.json_response({"success": False, "error": "Unauthorized"}, status=401)

        user_data = validated.get("user", {})
        user_id = user_data.get("id")

        bot = _get_bot(request)
        repo = _get_repo(request)

        report = await repo.get_by_id(report_id)
        if not report:
            return web.json_response({"success": False, "error": "Report not found"}, status=404)

        is_owner = report.user_id == user_id
        is_admin = await _check_admin(bot, report.chat_id, user_id)

        if not is_owner and not is_admin:
            return web.json_response({"success": False, "error": "Access denied"}, status=403)

        report_data = report.to_dict(include_admin_fields=True)

        return web.json_response({"success": True, "report": report_data, "is_admin": is_admin})

    except Exception as e:
        logger.exception(f"Ошибка получения репорта: {e}")
        return web.json_response({"success": False, "error": "Ошибка загрузки репорта"}, status=500)


def create_app() -> web.Application:
    """Создание aiohttp приложения"""
    app = web.Application(
        client_max_size=500 * 1024 * 1024,
        middlewares=[request_logging_middleware],
    )

    app.router.add_get("/health", health)
    app.router.add_get("/", index)

    app.router.add_post("/api/report", handle_report)
    app.router.add_post("/api/user-reports", api_get_user_reports)
    app.router.add_post("/api/chat-reports", api_get_chat_reports)
    app.router.add_post("/api/search-reports", api_search_reports)
    app.router.add_post("/api/export-csv", api_export_csv)
    app.router.add_post("/api/update-report", api_update_report)
    app.router.add_post("/api/get-report", api_get_report)
    app.router.add_post("/api/check-admin", api_check_admin)

    app.router.add_static("/static", STATIC_DIR)

    return app


async def start_webapp(
    bot,
    report_repo,
    bot_token: str,
    host: str = "0.0.0.0",
    port: int = 8080
) -> web.AppRunner:
    """Запуск Web App сервера"""
    app = create_app()

    app["bot"] = bot
    app["report_repo"] = report_repo
    app["bot_token"] = bot_token

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    return runner
