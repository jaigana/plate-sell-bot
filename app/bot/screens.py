from __future__ import annotations

from enum import StrEnum
from html import escape
from typing import Any


class Screen(StrEnum):
    HOME = "HOME"
    SEARCH = "SEARCH"
    SEARCH_RESULTS = "SEARCH_RESULTS"
    MARKET = "MARKET"
    MARKET_RU = "MARKET_RU"
    MARKET_KZ = "MARKET_KZ"
    NEW_LISTINGS = "NEW_LISTINGS"
    CHEAP_OFFERS = "CHEAP_OFFERS"
    RARE_PLATES = "RARE_PLATES"
    PLATE_VIEW = "PLATE_VIEW"
    MY_PLATES = "MY_PLATES"
    MY_PLATE_VIEW = "MY_PLATE_VIEW"
    CREATE_SALE = "CREATE_SALE"
    CREATE_AUCTION = "CREATE_AUCTION"
    AUCTIONS = "AUCTIONS"
    AUCTION_VIEW = "AUCTION_VIEW"
    BID_HISTORY = "BID_HISTORY"
    PLACE_BID = "PLACE_BID"
    BALANCE = "BALANCE"
    BALANCE_TOPUP = "BALANCE_TOPUP"
    PROFILE = "PROFILE"
    HELP = "HELP"
    LEGAL = "LEGAL"
    ADMIN_HOME = "ADMIN_HOME"
    ADMIN_STATS = "ADMIN_STATS"
    ADMIN_USERS = "ADMIN_USERS"
    ADMIN_USER_VIEW = "ADMIN_USER_VIEW"
    ADMIN_PLATES = "ADMIN_PLATES"
    ADMIN_PLATE_VIEW = "ADMIN_PLATE_VIEW"
    ADMIN_AUCTIONS = "ADMIN_AUCTIONS"
    ADMIN_AUCTION_VIEW = "ADMIN_AUCTION_VIEW"
    ADMIN_FINANCE = "ADMIN_FINANCE"
    ADMIN_BLACKLISTS = "ADMIN_BLACKLISTS"
    ADMIN_SETTINGS = "ADMIN_SETTINGS"
    ADMIN_CARDS = "ADMIN_CARDS"
    ADMIN_BACKUPS = "ADMIN_BACKUPS"


LEGAL_NOTICE = (
    "⚠️ <b>Виртуальные игровые активы</b>\n\n"
    "Все номера в этом боте — цифровые коллекционные активы исключительно для Car Parking Multiplayer 2. "
    "Они не являются, не заменяют и не имитируют реальные государственные регистрационные знаки любой страны."
)


def home_text(card: dict[str, Any] | None) -> str:
    title = (card or {}).get("title", "CPM2 Plates Market")
    description = (card or {}).get("description", "Маркетплейс игровых номеров Car Parking Multiplayer 2.")
    return f"🏁 <b>{escape(title)}</b>\n\n{escape(description)}\n\n{LEGAL_NOTICE}"


def plate_text(plate: dict[str, Any], *, mine: bool = False) -> str:
    state_labels = {
        "STATE_SALE": "у государства",
        "OWNED": "в коллекции",
        "FIXED_SALE": "фиксированная продажа",
        "AUCTION": "аукцион",
    }
    lines = [
        f"🚘 <b>{plate['plate_number']}</b>",
        f"Страна: {plate['country_code']}",
        f"Статус: {state_labels.get(plate['state'], plate['state'])}",
    ]
    if plate.get("sale_price"):
        lines.append(f"Цена: ⭐{plate['sale_price']}")
    if plate.get("current_price"):
        lines.append(f"Текущая ставка: ⭐{plate['current_price']}")
    if mine:
        lines.append("Это ваш виртуальный игровой актив.")
    return "\n".join(lines)


def market_text(title: str, plates: list[dict[str, Any]]) -> str:
    if not plates:
        return f"🛒 <b>{title}</b>\n\nСейчас предложений нет. Найдите номер и получите его у государства."
    rows = []
    for plate in plates:
        suffix = f" · ⭐{plate['sale_price']}" if plate.get("sale_price") else ""
        if plate.get("current_price"):
            suffix = f" · ставка ⭐{plate['current_price']}"
        rows.append(f"• {plate['plate_number']} ({plate['country_code']}){suffix}")
    return f"🛒 <b>{title}</b>\n\n" + "\n".join(rows)


def auction_text(auction: dict[str, Any]) -> str:
    return (
        f"🔨 <b>Аукцион #{auction['id']}</b>\n\n"
        f"Старт: ⭐{auction['starting_price']}\n"
        f"Текущая ставка: ⭐{auction['current_price']}\n"
        f"Окончание: {auction['ends_at']:%Y-%m-%d %H:%M UTC}"
    )
