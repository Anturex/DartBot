import asyncio
import logging
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from fastapi import FastAPI

load_dotenv()

from config import load_config
from utils.http_client import HttpClient
from telegram_notifier import TelegramNotifier
from monitors.mfds_monitor import MfdsMonitor
from monitors.nedrug_monitor import NedrugMonitor
from monitors.dart_monitor import DartMonitor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    config = load_config()
    http_client = HttpClient(config)
    await http_client.start()

    notifier = TelegramNotifier(config, http_client)
    stop_event = asyncio.Event()

    monitors = [
        MfdsMonitor(config=config, http_client=http_client, notifier=notifier),
        NedrugMonitor(config=config, http_client=http_client, notifier=notifier),
        DartMonitor(config=config, http_client=http_client, notifier=notifier),
    ]

    tasks = [asyncio.create_task(m.run(stop_event)) for m in monitors]

    await notifier.send(
        "✅ <b>[DartBot]</b> 모니터링 서버가 시작되었습니다.\n\n"
        "감시 대상:\n"
        "  1. 식약처 보도자료 (1초 간격)\n"
        "  2. nedrug 뉴로나타-알주 상세 (1초 간격)\n"
        "  3. DART 코아스템켐온 공시 (5초 간격)"
    )
    logger.info("All monitors started")

    yield

    logger.info("Shutting down monitors...")
    stop_event.set()
    done, pending = await asyncio.wait(tasks, timeout=10)
    for task in pending:
        task.cancel()
    await http_client.close()
    logger.info("Shutdown complete")


app = FastAPI(lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/")
async def root():
    return {"service": "DartBot", "status": "running"}
