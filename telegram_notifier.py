import logging
from utils.http_client import HttpClient
from config import Config

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


class TelegramNotifier:
    def __init__(self, config: Config, http_client: HttpClient):
        self._url = TELEGRAM_API.format(token=config.TELEGRAM_BOT_TOKEN)
        self._alert_chat_id = config.TELEGRAM_CHAT_ID
        self._monitor_chat_id = config.TELEGRAM_MONITOR_CHAT_ID
        self._http = http_client

    async def send(self, text: str, parse_mode: str = "HTML", silent: bool = False) -> bool:
        """알림 채팅방으로 발송"""
        return await self._send_to(self._alert_chat_id, text, parse_mode, silent)

    async def send_monitor(self, text: str, parse_mode: str = "HTML") -> bool:
        """모니터링 채팅방으로 무음 발송"""
        return await self._send_to(self._monitor_chat_id, text, parse_mode, silent=True)

    async def _send_to(self, chat_id: str, text: str, parse_mode: str, silent: bool) -> bool:
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True,
            "disable_notification": silent,
        }
        try:
            async with self._http.session.post(self._url, json=payload) as resp:
                if resp.status == 200:
                    logger.info("Telegram message sent successfully")
                    return True
                else:
                    body = await resp.text()
                    logger.error(f"Telegram API error {resp.status}: {body}")
                    return False
        except Exception as e:
            logger.error(f"Failed to send Telegram message: {e}")
            return False
