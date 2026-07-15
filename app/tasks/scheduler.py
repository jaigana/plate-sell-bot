from __future__ import annotations

import logging

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.container import AppContext

logger = logging.getLogger(__name__)


def create_scheduler(context: AppContext, bot: Bot) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="UTC")

    async def minute_jobs() -> None:
        released = await context.reservations.release_expired()
        finished = await context.auctions.finish_due()
        delivered = await context.notifications.deliver_due(bot)
        logger.info("minute_jobs_completed", extra={"released_reservations": released, "finished_auctions": finished, "delivered_notifications": delivered})

    async def inactive_job() -> None:
        result = await context.admin.process_inactive_accounts()
        logger.info("inactive_accounts_checked", extra=result)

    async def backup_job() -> None:
        try:
            await context.backups.create_and_send(bot)
        except Exception:
            logger.exception("scheduled_backup_failed")

    scheduler.add_job(minute_jobs, "interval", minutes=1, id="minute_jobs", coalesce=True, max_instances=1)
    scheduler.add_job(inactive_job, "cron", hour=3, minute=10, id="inactive_accounts", coalesce=True, max_instances=1)
    scheduler.add_job(backup_job, "cron", hour=3, minute=30, id="database_backup", coalesce=True, max_instances=1)
    return scheduler
