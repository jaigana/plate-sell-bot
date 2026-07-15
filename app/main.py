from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.bot.fsm import PgStorage
from app.bot.handlers import build_user_router
from app.bot.middlewares import RateLimitMiddleware, UserActivityMiddleware
from app.config import Settings
from app.container import AppContext
from app.db import apply_migrations, create_pool
from app.logging_config import configure_logging
from app.tasks import create_scheduler

logger = logging.getLogger(__name__)


async def _health(_: web.Request) -> web.Response:
    return web.json_response({"status": "ok"})


async def _start_health_server(port: int) -> web.AppRunner:
    application = web.Application()
    application.router.add_get("/health", _health)
    runner = web.AppRunner(application, access_log=None)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    return runner


async def run() -> None:
    configure_logging()
    settings = Settings()
    pool = await create_pool(settings.database_url)
    bot: Bot | None = None
    health_runner: web.AppRunner | None = None
    scheduler = None
    try:
        migrations_dir = Path(__file__).resolve().parent.parent / "migrations"
        await apply_migrations(pool, migrations_dir)
        context = AppContext(settings, pool)
        storage = PgStorage(pool)
        bot = Bot(settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
        dispatcher = Dispatcher(storage=storage)
        dispatcher.message.outer_middleware(RateLimitMiddleware())
        dispatcher.callback_query.outer_middleware(RateLimitMiddleware())
        dispatcher.message.outer_middleware(UserActivityMiddleware(context.users))
        dispatcher.callback_query.outer_middleware(UserActivityMiddleware(context.users))
        dispatcher.include_router(build_user_router(context))
        health_runner = await _start_health_server(settings.port)
        scheduler = create_scheduler(context, bot)
        scheduler.start()
        logger.info("application_started", extra={"environment": settings.env, "port": settings.port})
        await dispatcher.start_polling(bot, allowed_updates=dispatcher.resolve_used_update_types())
    finally:
        if scheduler:
            scheduler.shutdown(wait=False)
        if health_runner:
            await health_runner.cleanup()
        if bot:
            await bot.session.close()
        await pool.close()


if __name__ == "__main__":
    asyncio.run(run())
