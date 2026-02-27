import asyncio
import logging
import os
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

SELF_PING_INTERVAL = 300  # 5분마다


async def self_ping(http_client: HttpClient, stop_event: asyncio.Event):
    """Render 무료 티어 슬립 방지를 위한 self-ping"""
    render_url = os.environ.get("RENDER_EXTERNAL_URL")
    if not render_url:
        logger.info("[self-ping] RENDER_EXTERNAL_URL not set, skipping self-ping")
        return

    health_url = f"{render_url}/health"
    logger.info(f"[self-ping] Started (interval={SELF_PING_INTERVAL}s, url={health_url})")

    while not stop_event.is_set():
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=SELF_PING_INTERVAL)
            break
        except asyncio.TimeoutError:
            pass

        try:
            async with http_client.session.get(health_url) as resp:
                logger.debug(f"[self-ping] OK (status={resp.status})")
        except Exception as e:
            logger.warning(f"[self-ping] Failed: {e}")

    logger.info("[self-ping] Stopped")


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
    tasks.append(asyncio.create_task(self_ping(http_client, stop_event)))

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
