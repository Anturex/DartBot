import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Config:
    TELEGRAM_BOT_TOKEN: str
    TELEGRAM_CHAT_ID: str
    TELEGRAM_MONITOR_CHAT_ID: str
    DART_API_KEY: str

    MFDS_URL: str = "https://www.mfds.go.kr/brd/m_99/list.do"
    NEDRUG_URL: str = "https://nedrug.mfds.go.kr/pbp/CCBBB01/getItemDetail?itemSeq=202106193"
    DART_API_URL: str = "https://opendart.fss.or.kr/api/list.json"
    DART_DOCUMENT_URL: str = "https://opendart.fss.or.kr/api/document.xml"
    DART_CORP_CODE_URL: str = "https://opendart.fss.or.kr/api/corpCode.xml"

    POLL_INTERVAL: float = 1.0
    DART_POLL_INTERVAL: float = 5.0
    DART_STOCK_CODE: str = "166480"
    MFDS_KEYWORDS: tuple = ("뉴로나타", "루게릭")

    NEDRUG_KNOWN_ITEM_SEQ: str = "202106193"
    NEDRUG_KNOWN_APPROVAL_DATE: str = "2021-08-27"

    HTTP_TIMEOUT: int = 10
    PORT: int = 10000


def load_config() -> Config:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    dart_key = os.environ.get("DART_API_KEY")

    missing = []
    if not token:
        missing.append("TELEGRAM_BOT_TOKEN")
    if not chat_id:
        missing.append("TELEGRAM_CHAT_ID")
    if not dart_key:
        missing.append("DART_API_KEY")

    if missing:
        raise EnvironmentError(
            f"Missing required environment variables: {', '.join(missing)}"
        )

    monitor_chat_id = os.environ.get("TELEGRAM_MONITOR_CHAT_ID") or chat_id

    return Config(
        TELEGRAM_BOT_TOKEN=token,
        TELEGRAM_CHAT_ID=chat_id,
        TELEGRAM_MONITOR_CHAT_ID=monitor_chat_id,
        DART_API_KEY=dart_key,
        PORT=int(os.environ.get("PORT", "10000")),
    )
