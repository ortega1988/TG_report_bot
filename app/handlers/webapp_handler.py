import logging
from typing import Optional

from aiogram import Router, Bot
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, User
from aiogram.filters import Command

logger = logging.getLogger(__name__)

router = Router()

_bot_info: Optional[User] = None


def set_bot_info(info: User) -> None:
    """Сохранить информацию о боте (вызывается при запуске)"""
    global _bot_info
    _bot_info = info


def get_webapp_keyboard(bot_username: str, chat_id: int) -> InlineKeyboardMarkup:
    """Создать клавиатуру с кнопкой Web App"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Создать отчёт",
                    url=f"https://t.me/{bot_username}/report?startapp={chat_id}"
                )
            ]
        ]
    )


@router.message(Command("bug"))
async def cmd_bug(message: Message, bot: Bot):
    """Обработчик команды /bug"""
    logger.info(f"Получена команда /bug из чата {message.chat.id}")

    username = _bot_info.username if _bot_info else (await bot.get_me()).username

    await message.answer(
        "<b>Создание отчёта об ошибке</b>\n\n"
        "Нажмите кнопку ниже, чтобы заполнить форму:",
        reply_markup=get_webapp_keyboard(username, message.chat.id)
    )
