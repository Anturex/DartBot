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
from monitors.news_monitor import NewsMonitor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

SELF_PING_INTERVAL = 300  # 5분마다
HOURLY_REPORT_INTERVAL = 3600  # 1시간마다


async def hourly_report(monitors: list, notifier: TelegramNotifier, stop_event: asyncio.Event):
    """1시간마다 모니터링 상태 요약을 무음으로 발송"""
    start_time = asyncio.get_event_loop().time()
    logger.info("[hourly-report] Started (interval=1h)")

    while not stop_event.is_set():
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=HOURLY_REPORT_INTERVAL)
            break
        except asyncio.TimeoutError:
            pass

        uptime_sec = asyncio.get_event_loop().time() - start_time
        hours = int(uptime_sec // 3600)
        minutes = int((uptime_sec % 3600) // 60)

        lines = []
        for m in monitors:
            check_count = getattr(m, "_check_count", 0)
            alerts = m.alert_count
            errors = m.error_count

            if m.name == "MFDS":
                seen = len(getattr(m, "_seen_seqs", set()))
                lines.append(f"  <b>식약처:</b> 폴링 {check_count}회 | 추적 {seen}건 | 알림 {alerts}건 | 에러 {errors}건")
            elif m.name == "nedrug":
                item_seq = getattr(m, "_last_item_seq", "-")
                approval = getattr(m, "_last_approval_date", "-")
                lines.append(f"  <b>nedrug:</b> 폴링 {check_count}회 | 품목={item_seq} | 허가일={approval} | 알림 {alerts}건 | 에러 {errors}건")
            elif m.name == "DART":
                seen = len(getattr(m, "_seen_rcept_nos", set()))
                lines.append(f"  <b>DART:</b> 폴링 {check_count}회 | 추적 {seen}건 | 알림 {alerts}건 | 에러 {errors}건")
            elif m.name == "News":
                seen = len(getattr(m, "_seen_links", set()))
                lines.append(f"  <b>뉴스:</b> 폴링 {check_count}회 | 추적 {seen}건 | 알림 {alerts}건 | 에러 {errors}건")

        msg = (
            f"🕐 <b>[DartBot 정기 리포트]</b>\n\n"
            f"<b>가동시간:</b> {hours}시간 {minutes}분\n\n"
            + "\n".join(lines)
            + "\n\n✅ 정상 감시 중"
        )

        await notifier.send_monitor(msg)
        logger.info("[hourly-report] 정기 리포트 발송 완료 (무음)")

    logger.info("[hourly-report] Stopped")


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
        NewsMonitor(config=config, http_client=http_client, notifier=notifier),
    ]

    tasks = [asyncio.create_task(m.run(stop_event)) for m in monitors]
    tasks.append(asyncio.create_task(self_ping(http_client, stop_event)))
    tasks.append(asyncio.create_task(hourly_report(monitors, notifier, stop_event)))

    await notifier.send_monitor(
        "✅ <b>[DartBot]</b> 모니터링 서버가 시작되었습니다.\n\n"
        "감시 대상:\n"
        "  1. 식약처 보도자료 (1초 간격)\n"
        "  2. nedrug 뉴로나타-알주 상세 (1초 간격)\n"
        "  3. DART 코아스템켐온 공시 (5초 간격)\n"
        "  4. 네이버 뉴스 키워드 (5초 간격, 08~18시)"
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
