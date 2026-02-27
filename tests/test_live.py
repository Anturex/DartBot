"""
실제 .env 환경변수를 사용한 통합 테스트
- 실제 텔레그램 봇으로 메시지 전송
- 실제 API 호출로 모니터 동작 검증
- 변경 감지 시나리오를 시뮬레이션하여 알림 수신 확인

실행: python -m pytest tests/test_live.py -v -s
"""
import os
import asyncio
import pytest
from dotenv import load_dotenv
from unittest.mock import AsyncMock, MagicMock

load_dotenv()

from config import load_config, Config
from utils.http_client import HttpClient
from telegram_notifier import TelegramNotifier
from monitors.mfds_monitor import MfdsMonitor
from monitors.nedrug_monitor import NedrugMonitor
from monitors.dart_monitor import DartMonitor
from tests.conftest import make_mock_response


# .env가 없으면 이 테스트 파일 전체 스킵
pytestmark = pytest.mark.skipif(
    not os.environ.get("TELEGRAM_BOT_TOKEN"),
    reason="TELEGRAM_BOT_TOKEN not set - .env 파일을 확인하세요",
)


@pytest.fixture
def live_config():
    return load_config()


@pytest.fixture
async def live_http(live_config):
    client = HttpClient(live_config)
    await client.start()
    yield client
    await client.close()


@pytest.fixture
def live_notifier(live_config, live_http):
    return TelegramNotifier(live_config, live_http)


# ============================================================
# 1. 텔레그램 연결 테스트
# ============================================================

@pytest.mark.asyncio
async def test_telegram_connection(live_notifier):
    """실제 텔레그램 봇으로 테스트 메시지 전송"""
    result = await live_notifier.send(
        "🧪 <b>[DartBot 테스트]</b>\n\n"
        "텔레그램 연결 테스트 성공!\n"
        "이 메시지가 보이면 봇이 정상 작동합니다."
    )
    assert result is True, "텔레그램 메시지 전송 실패 - 봇 토큰/채팅 ID를 확인하세요"
    print("\n✅ 텔레그램 연결 성공 - 메시지를 확인하세요")


# ============================================================
# 2. MFDS 모니터 - 실제 식약처 페이지 파싱 + 변경 시뮬레이션
# ============================================================

@pytest.mark.asyncio
async def test_mfds_live_parsing_and_alert(live_config, live_http, live_notifier):
    """실제 식약처 페이지를 파싱하고, '루게릭' 키워드 글이 추가된 것처럼 시뮬레이션"""

    # Step 1: 실제 식약처 페이지에서 기사 파싱 확인
    monitor = MfdsMonitor(
        config=live_config, http_client=live_http, notifier=live_notifier
    )
    await monitor.initialize()
    count = len(monitor._seen_seqs)
    print(f"\n  식약처 보도자료 {count}건 파싱 완료")
    assert count > 0, "식약처 보도자료 파싱 실패"

    # Step 2: 가짜로 '루게릭' 키워드 글을 주입하여 알림 발송 시뮬레이션
    fake_html = """
    <html><body>
    <li>
      <a href="./view.do?seq=99999">식약처, 루게릭병 치료 희귀의약품 품목허가 승인</a>
      <span>2026-02-27</span>
    </li>
    </body></html>
    """

    # 원래 fetch를 가짜로 교체 (한 번만)
    original_fetch = monitor._fetch_articles

    async def fake_fetch():
        articles = await original_fetch()
        articles.insert(0, {
            "seq": "99999",
            "title": "[테스트] 식약처, 루게릭병 치료 희귀의약품 품목허가 승인",
            "date": "2026-02-27",
        })
        return articles

    monitor._fetch_articles = fake_fetch
    await monitor.check()

    print("  ✅ MFDS 테스트 통과 - 텔레그램에서 식약처 알림을 확인하세요")


# ============================================================
# 3. nedrug 모니터 - 실제 페이지 파싱 + 허가일 변경 시뮬레이션
# ============================================================

@pytest.mark.asyncio
async def test_nedrug_live_parsing_and_alert(live_config, live_http, live_notifier):
    """실제 nedrug 페이지를 파싱하고, 허가일이 변경된 것처럼 시뮬레이션"""

    monitor = NedrugMonitor(
        config=live_config, http_client=live_http, notifier=live_notifier
    )
    await monitor.initialize()
    print(f"\n  nedrug 기준값: 품목코드={monitor._last_item_seq}, 허가일={monitor._last_approval_date}")
    assert monitor._last_item_seq is not None, "nedrug 품목기준코드 파싱 실패"
    assert monitor._last_approval_date is not None, "nedrug 허가일 파싱 실패"

    # 허가일을 강제로 다른 값으로 바꿔서 변경 감지 시뮬레이션
    monitor._last_approval_date = "2020-01-01"  # 일부러 틀린 값

    # fetch는 실제 페이지에서 가져오므로 실제값(2021-08-27)과 다르면 알림 발생
    await monitor.check()

    print("  ✅ nedrug 테스트 통과 - 텔레그램에서 허가일 변경 알림을 확인하세요")


# ============================================================
# 4. DART 모니터 - 실제 API 연결 + 새 공시 시뮬레이션
# ============================================================

@pytest.mark.asyncio
async def test_dart_live_connection_and_alert(live_config, live_http, live_notifier):
    """실제 DART API로 corp_code 변환 및 공시 조회, 새 공시 시뮬레이션"""

    monitor = DartMonitor(
        config=live_config, http_client=live_http, notifier=live_notifier
    )
    await monitor.initialize()
    print(f"\n  DART corp_code 변환: 166480 → {monitor._corp_code}")
    print(f"  기존 공시 {len(monitor._seen_rcept_nos)}건 로드")
    assert monitor._corp_code is not None, "DART corp_code 변환 실패 - API 키를 확인하세요"

    # 가짜 새 공시를 주입하여 알림 시뮬레이션
    original_fetch = monitor._fetch_disclosures

    async def fake_fetch():
        real_disclosures = await original_fetch() or []
        fake_disclosure = {
            "corp_code": monitor._corp_code,
            "corp_name": "코아스템켐온",
            "stock_code": "166480",
            "report_nm": "[테스트] 주요사항보고서(뉴로나타-알주 품목허가 취득)",
            "rcept_no": "99999999999999",
            "flr_nm": "코아스템켐온",
            "rcept_dt": "20260227",
            "rm": "코",
        }
        return [fake_disclosure] + real_disclosures

    # 문서 요약도 가짜로 넣어서 전체 파이프라인 테스트
    original_summary = monitor._fetch_document_summary

    async def fake_summary(rcept_no):
        if rcept_no == "99999999999999":
            return (
                "  • 1. 보고서명: 주요사항보고서(뉴로나타-알주 품목허가 취득)\n"
                "  • 2. 결정일: 2026-02-27\n"
                "  • 3. 내용: 식약처로부터 뉴로나타-알주 품목허가 승인\n"
                "  • 4. 적응증: 루게릭병(근위축성측삭경화증, ALS)\n"
                "  • 5. 향후 계획: 상업 생산 및 출시 준비"
            )
        return await original_summary(rcept_no)

    monitor._fetch_disclosures = fake_fetch
    monitor._fetch_document_summary = fake_summary
    await monitor.check()

    print("  ✅ DART 테스트 통과 - 텔레그램에서 공시 알림(요약 포함)을 확인하세요")


# ============================================================
# 5. 전체 통합: 3개 모니터 동시 실행 테스트
# ============================================================

@pytest.mark.asyncio
async def test_all_monitors_concurrent(live_config, live_http, live_notifier):
    """세 모니터를 동시에 시작하고 정상 초기화 확인"""

    mfds = MfdsMonitor(config=live_config, http_client=live_http, notifier=live_notifier)
    nedrug = NedrugMonitor(config=live_config, http_client=live_http, notifier=live_notifier)
    dart = DartMonitor(config=live_config, http_client=live_http, notifier=live_notifier)

    # 세 모니터 동시 초기화
    await asyncio.gather(
        mfds.initialize(),
        nedrug.initialize(),
        dart.initialize(),
    )

    assert len(mfds._seen_seqs) > 0
    assert nedrug._last_item_seq is not None
    assert dart._corp_code is not None

    await live_notifier.send(
        "🧪 <b>[DartBot 통합 테스트 완료]</b>\n\n"
        f"✅ MFDS: 보도자료 {len(mfds._seen_seqs)}건 감시 중\n"
        f"✅ nedrug: 품목코드={nedrug._last_item_seq}, 허가일={nedrug._last_approval_date}\n"
        f"✅ DART: corp_code={dart._corp_code}, 공시 {len(dart._seen_rcept_nos)}건 감시 중\n\n"
        "모든 모니터 정상 작동 확인!"
    )

    print(f"\n  ✅ 전체 통합 테스트 통과")
    print(f"     MFDS: {len(mfds._seen_seqs)}건")
    print(f"     nedrug: 품목코드={nedrug._last_item_seq}")
    print(f"     DART: corp_code={dart._corp_code}, {len(dart._seen_rcept_nos)}건")
