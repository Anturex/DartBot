import logging
from utils.http_client import HttpClient
from config import Config

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


class TelegramNotifier:
    def __init__(self, config: Config, http_client: HttpClient):
        self._url = TELEGRAM_API.format(token=config.TELEGRAM_BOT_TOKEN)
        self._chat_id = config.TELEGRAM_CHAT_ID
        self._http = http_client

    async def send(self, text: str, parse_mode: str = "HTML") -> bool:
        payload = {
            "chat_id": self._chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True,
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
