from __future__ import annotations

import logging
from html import escape
from typing import Callable

from aiogram import Bot, F, Router
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice, Message, PreCheckoutQuery

from app.bot import keyboards as kb
from app.bot.fsm import PgStorage
from app.bot.screens import LEGAL_NOTICE, Screen, auction_text, home_text, market_text, plate_text
from app.bot.states import AdminInput, UserInput
from app.container import AppContext
from app.domain import AccessDenied, DomainError
from app.validators.registry import country_registry

logger = logging.getLogger(__name__)


async def _render(
    event: Message | CallbackQuery,
    bot: Bot,
    state: FSMContext,
    text: str,
    keyboard,
    screen: Screen,
    *,
    photo_file_id: str | None = None,
) -> None:
    """Maintain one UI message, editing it whenever Telegram permits it."""
    data = await state.get_data()
    message_id = data.get("ui_message_id")
    chat_id: int
    rendered = None
    try:
        if isinstance(event, CallbackQuery) and event.message:
            message = event.message
            chat_id = message.chat.id
            if photo_file_id:
                from aiogram.types import InputMediaPhoto
                rendered = await message.edit_media(
                    InputMediaPhoto(media=photo_file_id, caption=text, parse_mode=ParseMode.HTML), reply_markup=keyboard
                )
            elif getattr(message, "photo", None):
                await message.delete()
                rendered = await bot.send_message(chat_id, text, reply_markup=keyboard, parse_mode=ParseMode.HTML)
            else:
                rendered = await message.edit_text(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)
            await event.answer()
        else:
            assert isinstance(event, Message)
            chat_id = event.chat.id
            if message_id:
                try:
                    if photo_file_id:
                        from aiogram.types import InputMediaPhoto
                        rendered = await bot.edit_message_media(
                            chat_id=chat_id, message_id=message_id,
                            media=InputMediaPhoto(media=photo_file_id, caption=text, parse_mode=ParseMode.HTML),
                            reply_markup=keyboard,
                        )
                    else:
                        rendered = await bot.edit_message_text(
                            text, chat_id=chat_id, message_id=message_id, reply_markup=keyboard, parse_mode=ParseMode.HTML
                        )
                except TelegramBadRequest:
                    try:
                        await bot.delete_message(chat_id, message_id)
                    except TelegramBadRequest:
                        pass
            if rendered is None:
                if photo_file_id:
                    rendered = await bot.send_photo(chat_id, photo_file_id, caption=text, reply_markup=keyboard, parse_mode=ParseMode.HTML)
                else:
                    rendered = await bot.send_message(chat_id, text, reply_markup=keyboard, parse_mode=ParseMode.HTML)
            if event.message_id != getattr(rendered, "message_id", None):
                try:
                    await event.delete()
                except TelegramBadRequest:
                    pass
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc).lower():
            logger.warning("screen_render_failed", extra={"screen": screen, "error": str(exc)})
        if isinstance(event, CallbackQuery):
            await event.answer()
        return
    resulting_id = getattr(rendered, "message_id", None) or (event.message.message_id if isinstance(event, CallbackQuery) and event.message else message_id)
    if data.get("current_screen") != screen and isinstance(state.storage, PgStorage):
        await state.storage.push_screen(state.key, screen)
    await state.update_data(ui_message_id=resulting_id, current_screen=screen)


async def _error(event: Message | CallbackQuery, bot: Bot, state: FSMContext, exc: Exception) -> None:
    message = str(exc) if isinstance(exc, DomainError) else "Произошла техническая ошибка. Попробуйте ещё раз."
    logger.info("user_action_rejected", extra={"error": message})
    if isinstance(event, CallbackQuery):
        await event.answer(message, show_alert=True)
    else:
        await _render(
            event, bot, state, f"⚠️ <b>Не удалось выполнить действие</b>\n<blockquote>{escape(message)}</blockquote>",
            kb.home_only(), Screen.HELP,
        )


async def _show_home(event: Message | CallbackQuery, bot: Bot, state: FSMContext, context: AppContext, user_id: int) -> None:
    card = await context.cards.get("home")
    is_admin = await context.admin.is_admin(user_id)
    await state.set_state(None)
    await _render(
        event, bot, state, home_text(card), kb.home_keyboard(is_admin), Screen.HOME,
        photo_file_id=card.get("image_file_id") if card else None,
    )


def _int(value: str, description: str) -> int:
    try:
        result = int(value.strip())
    except ValueError as exc:
        raise DomainError(f"{description} должно быть целым числом.") from exc
    return result


def build_user_router(context: AppContext) -> Router:
    router = Router(name="market")

    @router.message(Command("start"))
    async def start(message: Message, bot: Bot, state: FSMContext) -> None:
        await _show_home(message, bot, state, context, message.from_user.id)

    @router.callback_query(F.data == "nav:home")
    async def nav_home(query: CallbackQuery, bot: Bot, state: FSMContext) -> None:
        await _show_home(query, bot, state, context, query.from_user.id)

    @router.callback_query(F.data == "home:search")
    async def open_search(query: CallbackQuery, bot: Bot, state: FSMContext) -> None:
        await state.set_state(None)
        await _render(
            query, bot, state,
            "🔎 <b>Выберите страну</b>\n<blockquote>Сначала выберите страну, затем введите номер. Поиск перед выпуском не требуется.</blockquote>",
            kb.search_keyboard(), Screen.SEARCH,
        )

    @router.message(UserInput.search, F.text)
    async def execute_search(message: Message, bot: Bot, state: FSMContext) -> None:
        try:
            results = await context.plates.search(message.text)
            await state.update_data(search_query=message.text.strip())
            await state.set_state(None)
            if results:
                text = "🔎 <b>Результаты поиска</b>\n\n" + "\n".join(
                    f"• {escape(row['plate_number'])} ({row['country_code']})" for row in results
                )
                await _render(message, bot, state, text, kb.market_keyboard(results), Screen.SEARCH_RESULTS)
            else:
                await _render(
                    message, bot, state,
                    "🔎 Номер не найден. Выберите страну — проверим формат и предложим получить виртуальный игровой актив у государства.",
                    kb.search_keyboard(), Screen.SEARCH_RESULTS,
                )
        except Exception as exc:
            await _error(message, bot, state, exc)

    @router.callback_query(F.data.startswith("market:"))
    async def market(query: CallbackQuery, bot: Bot, state: FSMContext) -> None:
        try:
            parts = query.data.split(":")
            country = parts[2].upper() if len(parts) == 3 and parts[1] == "country" else None
            plates = await context.plates.market(country)
            title = "Рынок" if not country else f"Рынок {country}"
            screen = Screen.MARKET_RU if country == "RU" else Screen.MARKET_KZ if country == "KZ" else Screen.MARKET
            await _render(query, bot, state, market_text(title, plates), kb.market_keyboard(plates), screen)
        except Exception as exc:
            await _error(query, bot, state, exc)

    @router.callback_query(F.data == "plate:mine")
    async def my_plates(query: CallbackQuery, bot: Bot, state: FSMContext) -> None:
        try:
            plates = await context.plates.my_plates(query.from_user.id)
            text = "🚘 <b>Мои игровые номера</b>\n\n"
            text += "У вас пока нет номеров." if not plates else "Выберите номер для управления."
            await _render(query, bot, state, text, kb.my_plates_keyboard(plates), Screen.MY_PLATES)
        except Exception as exc:
            await _error(query, bot, state, exc)

    @router.callback_query(F.data.startswith("plate:view:"))
    async def plate_view(query: CallbackQuery, bot: Bot, state: FSMContext) -> None:
        try:
            plate = await context.plates.get(_int(query.data.rsplit(":", 1)[1], "Идентификатор номера"))
            mine = plate.get("owner_id") == query.from_user.id
            await _render(query, bot, state, plate_text(plate, mine=mine), kb.plate_keyboard(plate, query.from_user.id), Screen.MY_PLATE_VIEW if mine else Screen.PLATE_VIEW)
        except Exception as exc:
            await _error(query, bot, state, exc)

    @router.callback_query(F.data.startswith("mint:country:"))
    async def mint_country(query: CallbackQuery, bot: Bot, state: FSMContext) -> None:
        country = query.data.rsplit(":", 1)[1].upper()
        country_info = country_registry.get(country)
        await state.update_data(mint_country=country)
        await state.set_state(UserInput.mint_plate)
        await _render(
            query, bot, state,
            f"🚘 <b>Выпуск номера · {escape(country_info.name)}</b>\n"
            f"<blockquote>{escape(country_info.format_hint)}</blockquote>\n"
            f"Введите номер. После проверки откроется счёт на Telegram Stars.",
            kb.home_only(), Screen.SEARCH,
        )

    @router.message(UserInput.mint_plate, F.text)
    async def mint_input(message: Message, bot: Bot, state: FSMContext) -> None:
        try:
            data = await state.get_data()
            prepared = await context.emission.prepare_invoice(message.from_user.id, data["mint_country"], message.text)
            await bot.send_invoice(
                chat_id=message.chat.id,
                title="Виртуальный игровой номер CPM2",
                description=f"Эмиссия {prepared['plate_number']} — цифрового игрового актива.",
                payload=prepared["invoice_ref"], provider_token="", currency="XTR",
                prices=[LabeledPrice(label="Эмиссия игрового номера", amount=prepared["price"])],
            )
            await state.set_state(None)
            await _render(message, bot, state, f"⭐ Номер <b>{prepared['plate_number']}</b> зарезервирован на 5 минут. Оплатите счёт ⭐{prepared['price']}.", kb.home_only(), Screen.SEARCH_RESULTS)
        except Exception as exc:
            await _error(message, bot, state, exc)

    @router.callback_query(F.data.startswith("mint:existing:"))
    async def mint_existing(query: CallbackQuery, bot: Bot, state: FSMContext) -> None:
        try:
            plate = await context.plates.get(_int(query.data.rsplit(":", 1)[1], "Идентификатор номера"))
            prepared = await context.emission.prepare_invoice(query.from_user.id, plate["country_code"], plate["plate_number"])
            await bot.send_invoice(
                chat_id=query.message.chat.id, title="Виртуальный игровой номер CPM2",
                description=f"Эмиссия {prepared['plate_number']} — цифрового игрового актива.",
                payload=prepared["invoice_ref"], provider_token="", currency="XTR",
                prices=[LabeledPrice(label="Эмиссия игрового номера", amount=prepared["price"])],
            )
            await _render(query, bot, state, "⭐ Счёт создан. Номер зарезервирован на 5 минут.", kb.home_only(), Screen.PLATE_VIEW)
        except Exception as exc:
            await _error(query, bot, state, exc)

    @router.callback_query(F.data == "balance:view")
    async def balance_view(query: CallbackQuery, bot: Bot, state: FSMContext) -> None:
        profile = await context.users.profile(query.from_user.id)
        await _render(query, bot, state, f"⭐ <b>Баланс</b>\n\nДоступно: ⭐{profile['balance_available']}\nЗаморожено в ставках: ⭐{profile['balance_frozen']}", kb.balance_keyboard(), Screen.BALANCE)

    @router.callback_query(F.data == "balance:topup")
    async def balance_topup_open(query: CallbackQuery, bot: Bot, state: FSMContext) -> None:
        await state.set_state(UserInput.topup_amount)
        await _render(query, bot, state, "Введите количество ⭐ для пополнения (от 1 до 99 999).", kb.home_only(), Screen.BALANCE_TOPUP)

    @router.message(UserInput.topup_amount, F.text)
    async def balance_topup_invoice(message: Message, bot: Bot, state: FSMContext) -> None:
        try:
            amount = _int(message.text, "Количество Stars")
            if not 1 <= amount <= 99_999:
                raise DomainError("Можно пополнить от ⭐1 до ⭐99 999.")
            await bot.send_invoice(
                chat_id=message.chat.id, title="Баланс CPM2 Plates Market", description="Пополнение баланса виртуального игрового маркетплейса.",
                payload=f"topup:{amount}", provider_token="", currency="XTR", prices=[LabeledPrice(label="Баланс", amount=amount)],
            )
            await state.set_state(None)
            await _render(message, bot, state, f"⭐ Счёт на ⭐{amount} создан.", kb.balance_keyboard(), Screen.BALANCE)
        except Exception as exc:
            await _error(message, bot, state, exc)

    @router.callback_query(F.data.startswith("sale:create:"))
    async def create_sale_open(query: CallbackQuery, bot: Bot, state: FSMContext) -> None:
        await state.update_data(sale_plate_id=_int(query.data.rsplit(":", 1)[1], "Идентификатор номера"))
        await state.set_state(UserInput.sale_price)
        await _render(query, bot, state, "💵 Введите цену в ⭐ (от 1 до 99 999).", kb.home_only(), Screen.CREATE_SALE)

    @router.message(UserInput.sale_price, F.text)
    async def create_sale(message: Message, bot: Bot, state: FSMContext) -> None:
        try:
            sale = await context.sales.create(message.from_user.id, (await state.get_data())["sale_plate_id"], _int(message.text, "Цена"))
            await state.set_state(None)
            await _render(message, bot, state, f"✅ Продажа создана: ⭐{sale['price']}.", kb.home_only(), Screen.MY_PLATE_VIEW)
        except Exception as exc:
            await _error(message, bot, state, exc)

    @router.callback_query(F.data.startswith("sale:buy:"))
    async def buy_sale(query: CallbackQuery, bot: Bot, state: FSMContext) -> None:
        try:
            result = await context.sales.buy(query.from_user.id, _int(query.data.rsplit(":", 1)[1], "Идентификатор номера"))
            await _render(query, bot, state, f"✅ Вы купили <b>{result['plate_number']}</b> за ⭐{result['price']}.", kb.home_only(), Screen.MY_PLATE_VIEW)
        except Exception as exc:
            await _error(query, bot, state, exc)

    @router.callback_query(F.data.startswith("auction:create:"))
    async def auction_create_open(query: CallbackQuery, bot: Bot, state: FSMContext) -> None:
        await state.update_data(auction_plate_id=_int(query.data.rsplit(":", 1)[1], "Идентификатор номера"))
        await state.set_state(UserInput.auction_price)
        await _render(query, bot, state, "🔨 Введите стартовую цену в ⭐.", kb.home_only(), Screen.CREATE_AUCTION)

    @router.message(UserInput.auction_price, F.text)
    async def auction_create_price(message: Message, bot: Bot, state: FSMContext) -> None:
        try:
            await state.update_data(auction_starting_price=_int(message.text, "Стартовая цена"))
            await state.set_state(UserInput.auction_duration)
            await _render(message, bot, state, "Введите длительность аукциона в минутах (1–1440).", kb.home_only(), Screen.CREATE_AUCTION)
        except Exception as exc:
            await _error(message, bot, state, exc)

    @router.message(UserInput.auction_duration, F.text)
    async def auction_create_duration(message: Message, bot: Bot, state: FSMContext) -> None:
        try:
            data = await state.get_data()
            auction = await context.auctions.create(message.from_user.id, data["auction_plate_id"], data["auction_starting_price"], _int(message.text, "Длительность"))
            await state.set_state(None)
            await _render(message, bot, state, f"✅ Аукцион #{auction['id']} создан до {auction['ends_at']:%H:%M UTC}.", kb.home_only(), Screen.AUCTION_VIEW)
        except Exception as exc:
            await _error(message, bot, state, exc)

    @router.callback_query(F.data == "auction:list")
    async def auction_list(query: CallbackQuery, bot: Bot, state: FSMContext) -> None:
        auctions = await context.auctions.list_active()
        text = "🔨 <b>Аукционы</b>\n\n" + ("Выберите лот." if auctions else "Активных аукционов пока нет.")
        await _render(query, bot, state, text, kb.auctions_keyboard(auctions), Screen.AUCTIONS)

    @router.callback_query(F.data.startswith("auction:view:"))
    async def auction_view(query: CallbackQuery, bot: Bot, state: FSMContext) -> None:
        try:
            auction = await context.auctions.get(_int(query.data.rsplit(":", 1)[1], "Идентификатор аукциона"))
            await _render(query, bot, state, auction_text(auction), kb.auction_keyboard(auction["id"]), Screen.AUCTION_VIEW)
        except Exception as exc:
            await _error(query, bot, state, exc)

    @router.callback_query(F.data.startswith("auction:plate:"))
    async def auction_from_plate(query: CallbackQuery, bot: Bot, state: FSMContext) -> None:
        plate_id = _int(query.data.rsplit(":", 1)[1], "Идентификатор номера")
        auctions = await context.auctions.list_active()
        matching = next((row for row in auctions if row["plate_id"] == plate_id), None)
        if not matching:
            await _error(query, bot, state, DomainError("Активный аукцион не найден."))
            return
        await _render(query, bot, state, auction_text(matching), kb.auction_keyboard(matching["id"]), Screen.AUCTION_VIEW)

    @router.callback_query(F.data.startswith("auction:bid:"))
    async def bid_open(query: CallbackQuery, bot: Bot, state: FSMContext) -> None:
        await state.update_data(bid_auction_id=_int(query.data.rsplit(":", 1)[1], "Идентификатор аукциона"))
        await state.set_state(UserInput.bid_amount)
        await _render(query, bot, state, "Введите сумму вашей ставки в ⭐. Она будет заморожена до конца аукциона или перебития.", kb.home_only(), Screen.PLACE_BID)

    @router.message(UserInput.bid_amount, F.text)
    async def bid_place(message: Message, bot: Bot, state: FSMContext) -> None:
        try:
            result = await context.auctions.place_bid(message.from_user.id, (await state.get_data())["bid_auction_id"], _int(message.text, "Ставка"))
            await state.set_state(None)
            await _render(message, bot, state, f"✅ Ставка ⭐{result['amount']} принята. Окончание: {result['ends_at']:%H:%M UTC}.", kb.home_only(), Screen.AUCTION_VIEW)
        except Exception as exc:
            await _error(message, bot, state, exc)

    @router.callback_query(F.data.startswith("auction:history:"))
    async def bid_history(query: CallbackQuery, bot: Bot, state: FSMContext) -> None:
        history = await context.auctions.bid_history(_int(query.data.rsplit(":", 1)[1], "Идентификатор аукциона"))
        text = "📜 <b>История ставок</b>\n\n" + ("\n".join(f"• ⭐{bid['amount']} · {bid['created_at']:%H:%M UTC}" for bid in history) if history else "Ставок ещё нет.")
        await _render(query, bot, state, text, kb.home_only(), Screen.BID_HISTORY)

    @router.callback_query(F.data == "profile:view")
    async def profile(query: CallbackQuery, bot: Bot, state: FSMContext) -> None:
        user = await context.users.profile(query.from_user.id)
        await _render(query, bot, state, f"👤 <b>Профиль</b>\n\nID: <code>{user['telegram_id']}</code>\nБаланс: ⭐{user['balance_available']}", kb.home_only(), Screen.PROFILE)

    @router.callback_query(F.data == "help:view")
    async def help_screen(query: CallbackQuery, bot: Bot, state: FSMContext) -> None:
        await _render(query, bot, state, "❓ <b>Помощь</b>\n\nИщите номер, получайте его у государства за Telegram Stars, продавайте за баланс или выставляйте на аукцион.\n\n" + LEGAL_NOTICE, kb.home_only(), Screen.HELP)

    @router.callback_query(F.data == "legal:view")
    async def legal_screen(query: CallbackQuery, bot: Bot, state: FSMContext) -> None:
        await _render(query, bot, state, LEGAL_NOTICE, kb.home_only(), Screen.LEGAL)

    @router.message(Command("admin"))
    @router.callback_query(F.data == "admin:home")
    async def admin_home(event: Message | CallbackQuery, bot: Bot, state: FSMContext) -> None:
        user_id = event.from_user.id
        try:
            await context.admin.require_admin(user_id)
            await _render(event, bot, state, "🛠 <b>Администрирование</b>\n\nУправление платформой выполняется только внутри этого бота.", kb.admin_keyboard(), Screen.ADMIN_HOME)
        except Exception as exc:
            await _error(event, bot, state, exc)

    @router.callback_query(F.data == "admin:stats")
    async def admin_stats(query: CallbackQuery, bot: Bot, state: FSMContext) -> None:
        try:
            values = await context.admin.stats(query.from_user.id)
            await _render(query, bot, state, f"📊 <b>Статистика</b>\n\nПользователи: {values['users']}\nНомера: {values['plates']}\nПродажи: {values['sales']}\nАукционы: {values['auctions']}\nБаланс игроков: ⭐{values['stars']}", kb.admin_keyboard(), Screen.ADMIN_STATS)
        except Exception as exc:
            await _error(query, bot, state, exc)

    @router.callback_query(F.data == "admin:settings")
    async def admin_settings(query: CallbackQuery, bot: Bot, state: FSMContext) -> None:
        try:
            values = await context.admin.settings(query.from_user.id)
            text = "⚙️ <b>Настройки платформы</b>\n\n" + "\n".join(f"• <code>{escape(key)}</code>: {escape(str(value))}" for key, value in values.items())
            rows = [[InlineKeyboardButton(text=f"✏️ {key}", callback_data=f"admin:setting:{key}")] for key in values]
            rows.append([InlineKeyboardButton(text="🔙 Админка", callback_data="admin:home")])
            await _render(query, bot, state, text, InlineKeyboardMarkup(inline_keyboard=rows), Screen.ADMIN_SETTINGS)
        except Exception as exc:
            await _error(query, bot, state, exc)

    @router.callback_query(F.data == "admin:backup")
    async def admin_backup(query: CallbackQuery, bot: Bot, state: FSMContext) -> None:
        try:
            await context.admin.require_admin(query.from_user.id)
            await _render(query, bot, state, "💾 Запускаю резервное копирование. Файл будет отправлен владельцу бота.", kb.admin_keyboard(), Screen.ADMIN_BACKUPS)
            await context.backups.create_and_send(bot, query.from_user.id)
        except Exception as exc:
            await _error(query, bot, state, exc)

    @router.callback_query(F.data == "admin:users")
    async def admin_users_open(query: CallbackQuery, bot: Bot, state: FSMContext) -> None:
        try:
            await context.admin.require_admin(query.from_user.id)
            await state.set_state(AdminInput.user_lookup)
            await _render(query, bot, state, "👤 Введите Telegram ID пользователя.", kb.admin_keyboard(), Screen.ADMIN_USERS)
        except Exception as exc:
            await _error(query, bot, state, exc)

    @router.message(AdminInput.user_lookup, F.text)
    async def admin_user_view(message: Message, bot: Bot, state: FSMContext) -> None:
        try:
            await context.admin.require_admin(message.from_user.id)
            user_id = _int(message.text, "Telegram ID")
            user = await context.users.profile(user_id)
            if not user:
                raise DomainError("Пользователь ещё не открывал бота.")
            moderation = InlineKeyboardButton(text="✅ Разблокировать", callback_data=f"admin:unblock:{user_id}") if user["is_blocked"] else InlineKeyboardButton(text="🚫 Заблокировать", callback_data=f"admin:block:{user_id}")
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [moderation, InlineKeyboardButton(text="⭐ Изменить баланс", callback_data=f"admin:balance:{user_id}")],
                [InlineKeyboardButton(text="↩️ Вернуть Telegram Stars", callback_data=f"admin:refund:{user_id}")],
                [InlineKeyboardButton(text="🔙 Админка", callback_data="admin:home")],
            ])
            await state.set_state(None)
            await _render(message, bot, state, f"👤 <b>Пользователь {user_id}</b>\n\nUsername: @{escape(user['username'] or '—')}\nДоступно: ⭐{user['balance_available']}\nЗаморожено: ⭐{user['balance_frozen']}\nЗаблокирован: {'да' if user['is_blocked'] else 'нет'}", keyboard, Screen.ADMIN_USER_VIEW)
        except Exception as exc:
            await _error(message, bot, state, exc)

    @router.callback_query(F.data.startswith("admin:block:"))
    async def admin_block_open(query: CallbackQuery, bot: Bot, state: FSMContext) -> None:
        try:
            await context.admin.require_admin(query.from_user.id)
            await state.update_data(admin_target_user_id=_int(query.data.rsplit(":", 1)[1], "Telegram ID"))
            await state.set_state(AdminInput.block_reason)
            await _render(query, bot, state, "Введите причину блокировки.", kb.admin_keyboard(), Screen.ADMIN_USER_VIEW)
        except Exception as exc:
            await _error(query, bot, state, exc)

    @router.message(AdminInput.block_reason, F.text)
    async def admin_block_apply(message: Message, bot: Bot, state: FSMContext) -> None:
        try:
            await context.admin.block(message.from_user.id, (await state.get_data())["admin_target_user_id"], message.text)
            await state.set_state(None)
            await _render(message, bot, state, "✅ Пользователь заблокирован.", kb.admin_keyboard(), Screen.ADMIN_USERS)
        except Exception as exc:
            await _error(message, bot, state, exc)

    @router.callback_query(F.data.startswith("admin:unblock:"))
    async def admin_unblock(query: CallbackQuery, bot: Bot, state: FSMContext) -> None:
        try:
            user_id = _int(query.data.rsplit(":", 1)[1], "Telegram ID")
            await context.admin.unblock(query.from_user.id, user_id)
            await _render(query, bot, state, "✅ Пользователь разблокирован.", kb.admin_keyboard(), Screen.ADMIN_USERS)
        except Exception as exc:
            await _error(query, bot, state, exc)

    @router.callback_query(F.data.startswith("admin:balance:"))
    async def admin_balance_open(query: CallbackQuery, bot: Bot, state: FSMContext) -> None:
        try:
            await context.admin.require_admin(query.from_user.id)
            await state.update_data(admin_target_user_id=_int(query.data.rsplit(":", 1)[1], "Telegram ID"))
            await state.set_state(AdminInput.balance_adjustment)
            await _render(query, bot, state, "Введите изменение и причину через <code>|</code>. Пример: <code>-50|корректировка</code>", kb.admin_keyboard(), Screen.ADMIN_FINANCE)
        except Exception as exc:
            await _error(query, bot, state, exc)

    @router.message(AdminInput.balance_adjustment, F.text)
    async def admin_balance_apply(message: Message, bot: Bot, state: FSMContext) -> None:
        try:
            amount_text, reason = message.text.split("|", 1)
            result = await context.balance.adjust((await state.get_data())["admin_target_user_id"], _int(amount_text, "Изменение"), reason.strip(), message.from_user.id)
            await state.set_state(None)
            await _render(message, bot, state, f"✅ Баланс изменён. Доступно: ⭐{result['available']}, заморожено: ⭐{result['frozen']}.", kb.admin_keyboard(), Screen.ADMIN_FINANCE)
        except ValueError:
            await _error(message, bot, state, DomainError("Используйте формат: изменение|причина."))
        except Exception as exc:
            await _error(message, bot, state, exc)

    @router.callback_query(F.data.startswith("admin:refund:"))
    async def admin_refund_open(query: CallbackQuery, bot: Bot, state: FSMContext) -> None:
        try:
            await context.admin.require_admin(query.from_user.id)
            await state.update_data(admin_target_user_id=_int(query.data.rsplit(":", 1)[1], "Telegram ID"))
            await state.set_state(AdminInput.refund_charge_id)
            await _render(
                query, bot, state,
                "↩️ <b>Возврат Telegram Stars</b>\n"
                "<blockquote>Отправьте <code>telegram_payment_charge_id</code> из платежа пользователя. "
                "Для пополнения баланс должен оставаться доступным; для эмиссии номер должен всё ещё принадлежать пользователю.</blockquote>",
                kb.admin_keyboard(), Screen.ADMIN_FINANCE,
            )
        except Exception as exc:
            await _error(query, bot, state, exc)

    @router.message(AdminInput.refund_charge_id, F.text)
    async def admin_refund_apply(message: Message, bot: Bot, state: FSMContext) -> None:
        try:
            result = await context.admin.refund_stars(
                message.from_user.id, (await state.get_data())["admin_target_user_id"], message.text, bot
            )
            await state.set_state(None)
            await _render(
                message, bot, state,
                f"✅ <b>Возврат выполнен</b>\n<blockquote>Telegram вернул ⭐{result['amount']}. Тип платежа: {result['payment_type']}.</blockquote>",
                kb.admin_keyboard(), Screen.ADMIN_FINANCE,
            )
        except Exception as exc:
            await _error(message, bot, state, exc)

    @router.callback_query(F.data == "admin:plates")
    async def admin_plates_open(query: CallbackQuery, bot: Bot, state: FSMContext) -> None:
        try:
            await context.admin.require_admin(query.from_user.id)
            await state.set_state(AdminInput.plate_lookup)
            await _render(query, bot, state, "🚘 Введите ID игрового номера.", kb.admin_keyboard(), Screen.ADMIN_PLATES)
        except Exception as exc:
            await _error(query, bot, state, exc)

    @router.message(AdminInput.plate_lookup, F.text)
    async def admin_plate_view(message: Message, bot: Bot, state: FSMContext) -> None:
        try:
            await context.admin.require_admin(message.from_user.id)
            plate = await context.plates.get(_int(message.text, "ID номера"))
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="↔️ Принудительная передача", callback_data=f"admin:transfer:{plate['id']}")],
                [InlineKeyboardButton(text="🔙 Админка", callback_data="admin:home")],
            ])
            await state.set_state(None)
            await _render(message, bot, state, plate_text(plate), keyboard, Screen.ADMIN_PLATE_VIEW)
        except Exception as exc:
            await _error(message, bot, state, exc)

    @router.callback_query(F.data.startswith("admin:transfer:"))
    async def admin_transfer_open(query: CallbackQuery, bot: Bot, state: FSMContext) -> None:
        try:
            await context.admin.require_admin(query.from_user.id)
            await state.update_data(admin_plate_id=_int(query.data.rsplit(":", 1)[1], "ID номера"))
            await state.set_state(AdminInput.transfer_target)
            await _render(query, bot, state, "Введите Telegram ID нового владельца или <code>0</code>, чтобы вернуть номер государству.", kb.admin_keyboard(), Screen.ADMIN_PLATE_VIEW)
        except Exception as exc:
            await _error(query, bot, state, exc)

    @router.message(AdminInput.transfer_target, F.text)
    async def admin_transfer_apply(message: Message, bot: Bot, state: FSMContext) -> None:
        try:
            target = _int(message.text, "Telegram ID")
            await context.admin.force_transfer(message.from_user.id, (await state.get_data())["admin_plate_id"], target or None)
            await state.set_state(None)
            await _render(message, bot, state, "✅ Передача номера выполнена.", kb.admin_keyboard(), Screen.ADMIN_PLATES)
        except Exception as exc:
            await _error(message, bot, state, exc)

    @router.callback_query(F.data == "admin:auctions")
    async def admin_auctions_open(query: CallbackQuery, bot: Bot, state: FSMContext) -> None:
        try:
            await context.admin.require_admin(query.from_user.id)
            await state.set_state(AdminInput.auction_lookup)
            await _render(query, bot, state, "🔨 Введите ID аукциона.", kb.admin_keyboard(), Screen.ADMIN_AUCTIONS)
        except Exception as exc:
            await _error(query, bot, state, exc)

    @router.message(AdminInput.auction_lookup, F.text)
    async def admin_auction_view(message: Message, bot: Bot, state: FSMContext) -> None:
        try:
            await context.admin.require_admin(message.from_user.id)
            auction = await context.auctions.get(_int(message.text, "ID аукциона"))
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ Завершить принудительно", callback_data=f"admin:finish:{auction['id']}"), InlineKeyboardButton(text="⛔ Отменить", callback_data=f"admin:cancel:{auction['id']}")],
                [InlineKeyboardButton(text="🔙 Админка", callback_data="admin:home")],
            ])
            await state.set_state(None)
            await _render(message, bot, state, auction_text(auction), keyboard, Screen.ADMIN_AUCTION_VIEW)
        except Exception as exc:
            await _error(message, bot, state, exc)

    @router.callback_query(F.data.startswith("admin:finish:"))
    async def admin_force_finish(query: CallbackQuery, bot: Bot, state: FSMContext) -> None:
        try:
            await context.admin.require_admin(query.from_user.id)
            result = await context.auctions.finish(_int(query.data.rsplit(":", 1)[1], "ID аукциона"), force=True)
            if not result:
                raise DomainError("Аукцион уже не активен.")
            await _render(query, bot, state, "✅ Аукцион завершён принудительно.", kb.admin_keyboard(), Screen.ADMIN_AUCTIONS)
        except Exception as exc:
            await _error(query, bot, state, exc)

    @router.callback_query(F.data.startswith("admin:cancel:"))
    async def admin_force_cancel(query: CallbackQuery, bot: Bot, state: FSMContext) -> None:
        try:
            await context.admin.require_admin(query.from_user.id)
            await context.auctions.force_cancel(_int(query.data.rsplit(":", 1)[1], "ID аукциона"))
            await _render(query, bot, state, "✅ Аукцион отменён, текущая ставка разморожена.", kb.admin_keyboard(), Screen.ADMIN_AUCTIONS)
        except Exception as exc:
            await _error(query, bot, state, exc)

    @router.callback_query(F.data == "admin:finance")
    async def admin_finance(query: CallbackQuery, bot: Bot, state: FSMContext) -> None:
        try:
            values = await context.admin.stats(query.from_user.id)
            await _render(query, bot, state, f"💰 <b>Финансы</b>\n\nВсего ⭐ на счетах и в ставках: {values['stars']}\nАктивные продажи: {values['sales']}\nАктивные аукционы: {values['auctions']}", kb.admin_keyboard(), Screen.ADMIN_FINANCE)
        except Exception as exc:
            await _error(query, bot, state, exc)

    @router.callback_query(F.data.startswith("admin:setting:"))
    async def admin_setting_open(query: CallbackQuery, bot: Bot, state: FSMContext) -> None:
        try:
            await context.admin.require_admin(query.from_user.id)
            await state.update_data(admin_setting_key=query.data.rsplit(":", 1)[1])
            await state.set_state(AdminInput.setting_value)
            await _render(query, bot, state, "Введите новое целое значение настройки.", kb.admin_keyboard(), Screen.ADMIN_SETTINGS)
        except Exception as exc:
            await _error(query, bot, state, exc)

    @router.message(AdminInput.setting_value, F.text)
    async def admin_setting_apply(message: Message, bot: Bot, state: FSMContext) -> None:
        try:
            await context.admin.set_setting(message.from_user.id, (await state.get_data())["admin_setting_key"], _int(message.text, "Значение"))
            await state.set_state(None)
            await _render(message, bot, state, "✅ Настройка обновлена.", kb.admin_keyboard(), Screen.ADMIN_SETTINGS)
        except Exception as exc:
            await _error(message, bot, state, exc)

    @router.callback_query(F.data == "admin:cards")
    async def admin_cards_edit_button(query: CallbackQuery, bot: Bot, state: FSMContext) -> None:
        # This replaces the earlier list view with the same card list plus a direct editor action.
        try:
            await context.admin.require_admin(query.from_user.id)
            cards = await context.cards.list_all()
            text = "🗃 <b>Карточки интерфейса</b>\n\n" + "\n".join(f"• <code>{escape(card['card_id'])}</code>: {escape(card['title'])}" for card in cards)
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✏️ Изменить карточку", callback_data="admin:cardedit")],
                [InlineKeyboardButton(text="🔙 Админка", callback_data="admin:home")],
            ])
            await _render(query, bot, state, text, keyboard, Screen.ADMIN_CARDS)
        except Exception as exc:
            await _error(query, bot, state, exc)

    @router.callback_query(F.data == "admin:cardedit")
    async def admin_card_open(query: CallbackQuery, bot: Bot, state: FSMContext) -> None:
        try:
            await context.admin.require_admin(query.from_user.id)
            await state.set_state(AdminInput.card_edit)
            await _render(query, bot, state, "Отправьте <code>card_id|заголовок|описание</code>. Можно прикрепить фото к этому сообщению — его Telegram file_id будет сохранён.", kb.admin_keyboard(), Screen.ADMIN_CARDS)
        except Exception as exc:
            await _error(query, bot, state, exc)

    async def save_card(message: Message, bot: Bot, state: FSMContext, image_file_id: str | None = None) -> None:
        try:
            await context.admin.require_admin(message.from_user.id)
            raw = message.caption if image_file_id else message.text
            card_id, title, description = [part.strip() for part in raw.split("|", 2)]
            existing = await context.cards.get(card_id)
            await context.cards.update(message.from_user.id, card_id, title, description, image_file_id if image_file_id else (existing or {}).get("image_file_id"))
            await state.set_state(None)
            await _render(message, bot, state, "✅ Карточка обновлена.", kb.admin_keyboard(), Screen.ADMIN_CARDS)
        except ValueError:
            await _error(message, bot, state, DomainError("Используйте формат: card_id|заголовок|описание."))
        except Exception as exc:
            await _error(message, bot, state, exc)

    @router.message(AdminInput.card_edit, F.text)
    async def admin_card_text(message: Message, bot: Bot, state: FSMContext) -> None:
        await save_card(message, bot, state)

    @router.message(AdminInput.card_edit, F.photo)
    async def admin_card_photo(message: Message, bot: Bot, state: FSMContext) -> None:
        if not message.caption:
            await _error(message, bot, state, DomainError("Добавьте подпись в формате: card_id|заголовок|описание."))
            return
        await save_card(message, bot, state, message.photo[-1].file_id)

    @router.pre_checkout_query()
    async def pre_checkout(query: PreCheckoutQuery, bot: Bot) -> None:
        payload = query.invoice_payload
        if payload.startswith("mint-") or payload.startswith("topup:"):
            await bot.answer_pre_checkout_query(query.id, ok=True)
        else:
            await bot.answer_pre_checkout_query(query.id, ok=False, error_message="Неизвестный платёж.")

    @router.message(F.successful_payment)
    async def successful_payment(message: Message, bot: Bot, state: FSMContext) -> None:
        try:
            payment = message.successful_payment
            payload = payment.invoice_payload
            if payload.startswith("mint-"):
                plate = await context.emission.complete_invoice(message.from_user.id, payload, payment.telegram_payment_charge_id, payment.total_amount)
                await _render(message, bot, state, f"✅ Оплата принята. <b>{plate['plate_number']}</b> добавлен в вашу коллекцию.", kb.home_only(), Screen.MY_PLATE_VIEW)
            elif payload.startswith("topup:"):
                amount = _int(payload.split(":", 1)[1], "Сумма")
                if payment.total_amount != amount:
                    raise DomainError("Сумма платежа не совпадает со счётом.")
                await context.balance.top_up(message.from_user.id, amount, payment.telegram_payment_charge_id)
                await _render(message, bot, state, f"✅ Баланс пополнен на ⭐{amount}.", kb.balance_keyboard(), Screen.BALANCE)
            else:
                raise DomainError("Неизвестный платёж.")
        except Exception as exc:
            await _error(message, bot, state, exc)

    @router.message(StateFilter(None), F.text)
    async def fallback(message: Message, bot: Bot, state: FSMContext) -> None:
        await _render(message, bot, state, "Используйте кнопки меню, чтобы открыть нужный раздел.", kb.home_only(), Screen.HELP)

    return router
