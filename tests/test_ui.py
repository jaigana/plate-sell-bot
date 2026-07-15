from app.bot.keyboards import search_keyboard
from app.bot.screens import LEGAL_NOTICE, home_text


def test_release_flow_shows_available_countries_before_text_input() -> None:
    keyboard = search_keyboard()
    buttons = [button for row in keyboard.inline_keyboard for button in row]

    assert [(button.text, button.callback_data) for button in buttons[:2]] == [
        ("🇷🇺 Россия · А001АА77", "mint:country:ru"),
        ("🇰🇿 Казахстан · 777AAA01", "mint:country:kz"),
    ]


def test_main_screen_uses_telegram_html_quote_formatting() -> None:
    assert "<blockquote>" in LEGAL_NOTICE
    assert "<blockquote>" in home_text({"title": "Title", "description": "Description"})
