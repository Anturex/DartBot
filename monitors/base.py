from __future__ import annotations
import asyncio
import logging
from abc import ABC, abstractmethod
from config import Config
from telegram_notifier import TelegramNotifier
from utils.http_client import HttpClient

logger = logging.getLogger(__name__)


class BaseMonitor(ABC):
    def __init__(
        self,
        name: str,
        config: Config,
        http_client: HttpClient,
        notifier: TelegramNotifier,
        poll_interval: float | None = None,
    ):
        self.name = name
        self.config = config
        self.http = http_client
        self.notifier = notifier
        self.poll_interval = poll_interval or config.POLL_INTERVAL
        self.alert_count: int = 0
        self.error_count: int = 0

    @abstractmethod
    async def initialize(self):
        ...

    @abstractmethod
    async def check(self):
        ...

    async def run(self, stop_event: asyncio.Event):
        logger.info(f"[{self.name}] Starting monitor (interval={self.poll_interval}s)")
        try:
            await self.initialize()
        except Exception as e:
            logger.error(f"[{self.name}] Initialization failed: {e}", exc_info=True)

        while not stop_event.is_set():
            try:
                await self.check()
            except Exception as e:
                logger.error(f"[{self.name}] Check error: {e}", exc_info=True)

            try:
                await asyncio.wait_for(
                    stop_event.wait(),
                    timeout=self.poll_interval,
                )
                break
            except asyncio.TimeoutError:
                pass

        logger.info(f"[{self.name}] Monitor stopped")
