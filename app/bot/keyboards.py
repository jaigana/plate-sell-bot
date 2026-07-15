from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def _button(text: str, callback_data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=callback_data)


def home_keyboard(is_admin: bool = False) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(_button("🔎 Поиск / выпуск", "home:search"), _button("🛒 Рынок", "market:all"))
    builder.row(_button("🔨 Аукционы", "auction:list"), _button("🚘 Мои номера", "plate:mine"))
    builder.row(_button("⭐ Баланс", "balance:view"), _button("👤 Профиль", "profile:view"))
    builder.row(_button("❓ Помощь", "help:view"), _button("⚖️ Правила", "legal:view"))
    if is_admin:
        builder.row(_button("🛠 Администрирование", "admin:home"))
    return builder.as_markup()


def home_only() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[_button("🏠 Главная", "nav:home")]])


def market_keyboard(plates: list[dict]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for plate in plates:
        builder.button(text=f"{plate['plate_number']} · {plate['country_code']}", callback_data=f"plate:view:{plate['id']}")
    builder.adjust(1)
    builder.row(_button("🇷🇺 Россия", "market:country:ru"), _button("🇰🇿 Казахстан", "market:country:kz"))
    builder.row(_button("🏠 Главная", "nav:home"))
    return builder.as_markup()


def search_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [_button("🇷🇺 Россия · А001АА77", "mint:country:ru")],
        [_button("🇰🇿 Казахстан · 777AAA01", "mint:country:kz")],
        [_button("🏠 Главная", "nav:home")],
    ])


def plate_keyboard(plate: dict, user_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if plate["state"] == "STATE_SALE":
        builder.row(_button("⭐ Получить у государства", f"mint:existing:{plate['id']}"))
    elif plate["state"] == "FIXED_SALE":
        builder.row(_button("🛒 Купить за баланс", f"sale:buy:{plate['id']}"))
    elif plate["state"] == "AUCTION":
        builder.row(_button("🔨 Открыть аукцион", f"auction:plate:{plate['id']}"))
    if plate.get("owner_id") == user_id and plate["state"] == "OWNED":
        builder.row(_button("💵 Продать", f"sale:create:{plate['id']}"), _button("🔨 На аукцион", f"auction:create:{plate['id']}"))
    builder.row(_button("🏠 Главная", "nav:home"))
    return builder.as_markup()


def my_plates_keyboard(plates: list[dict]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for plate in plates:
        builder.button(text=plate["plate_number"], callback_data=f"plate:view:{plate['id']}")
    builder.adjust(1)
    builder.row(_button("🏠 Главная", "nav:home"))
    return builder.as_markup()


def auctions_keyboard(auctions: list[dict]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for auction in auctions:
        builder.button(text=f"{auction['plate_number']} · ⭐{auction['current_price']}", callback_data=f"auction:view:{auction['id']}")
    builder.adjust(1)
    builder.row(_button("🏠 Главная", "nav:home"))
    return builder.as_markup()


def auction_keyboard(auction_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [_button("⭐ Сделать ставку", f"auction:bid:{auction_id}"), _button("📜 Ставки", f"auction:history:{auction_id}")],
        [_button("🔙 К аукционам", "auction:list"), _button("🏠 Главная", "nav:home")],
    ])


def balance_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [_button("➕ Пополнить Telegram Stars", "balance:topup")],
        [_button("🏠 Главная", "nav:home")],
    ])


def admin_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [_button("📊 Статистика", "admin:stats"), _button("👤 Пользователи", "admin:users")],
        [_button("🚘 Номера", "admin:plates"), _button("🔨 Аукционы", "admin:auctions")],
        [_button("💰 Финансы", "admin:finance"), _button("⚙️ Настройки", "admin:settings")],
        [_button("🗃 Карточки", "admin:cards")],
        [_button("💾 Резервная копия", "admin:backup")],
        [_button("🏠 Главная", "nav:home")],
    ])
