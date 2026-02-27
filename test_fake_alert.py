"""정기 리포트 무음 발송 테스트"""
import asyncio
from dotenv import load_dotenv

load_dotenv()

from config import load_config
from utils.http_client import HttpClient
from telegram_notifier import TelegramNotifier


async def main():
    config = load_config()
    http = HttpClient(config)
    await http.start()
    notifier = TelegramNotifier(config, http)

    msg = (
        "🕐 <b>[DartBot 정기 리포트]</b>\n\n"
        "<b>가동시간:</b> 1시간 0분\n\n"
        "  <b>식약처:</b> 폴링 3600회 | 추적 10건 | 알림 0건 | 에러 0건\n"
        "  <b>nedrug:</b> 폴링 3600회 | 품목=202106193 | 허가일=2021-08-27 | 알림 0건 | 에러 0건\n"
        "  <b>DART:</b> 폴링 720회 | 추적 1건 | 알림 0건 | 에러 0건\n\n"
        "✅ 정상 감시 중"
    )

    await notifier.send(msg, silent=True)
    print("정기 리포트 발송 완료 (무음) - 텔레그램 확인하세요!")

    await http.close()


asyncio.run(main())
