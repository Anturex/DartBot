"""
News 모니터 테스트: 네이버 뉴스 검색 API로 키워드 뉴스를 감지하면
제목·요약과 함께 텔레그램 알림이 발송되는지 검증
"""
import pytest
from monitors.news_monitor import NewsMonitor
from tests.conftest import make_mock_response

# --- 가짜 API 응답 데이터 ---

# 초기 상태: 뉴스 2건
NAVER_NEWS_BASELINE = {
    "lastBuildDate": "Wed, 04 Mar 2026 10:00:00 +0900",
    "total": 2,
    "start": 1,
    "display": 20,
    "items": [
        {
            "title": "코아스템켐온, 2025년 실적 발표",
            "originallink": "https://news.example.com/article/1001",
            "link": "https://n.news.naver.com/article/1001",
            "description": "코아스템켐온이 2025년 연간 실적을 발표했다.",
            "pubDate": "Tue, 03 Mar 2026 09:00:00 +0900",
        },
        {
            "title": "제약 업계 동향 분석",
            "originallink": "https://news.example.com/article/1002",
            "link": "https://n.news.naver.com/article/1002",
            "description": "국내 제약 업계의 최신 동향을 분석한다.",
            "pubDate": "Tue, 03 Mar 2026 10:00:00 +0900",
        },
    ],
}

# 변경 후: 새 뉴스 1건 추가
NAVER_NEWS_WITH_NEW = {
    "lastBuildDate": "Wed, 04 Mar 2026 11:00:00 +0900",
    "total": 3,
    "start": 1,
    "display": 20,
    "items": [
        {
            "title": "<b>코아스템켐온</b>, <b>뉴로나타</b> 임상 3상 결과 발표",
            "originallink": "https://news.example.com/article/1003",
            "link": "https://n.news.naver.com/article/1003",
            "description": "<b>코아스템켐온</b>이 루게릭병 치료제 <b>뉴로나타</b>의 임상 3상 결과를 발표했다.",
            "pubDate": "Wed, 04 Mar 2026 11:00:00 +0900",
        },
        {
            "title": "코아스템켐온, 2025년 실적 발표",
            "originallink": "https://news.example.com/article/1001",
            "link": "https://n.news.naver.com/article/1001",
            "description": "코아스템켐온이 2025년 연간 실적을 발표했다.",
            "pubDate": "Tue, 03 Mar 2026 09:00:00 +0900",
        },
        {
            "title": "제약 업계 동향 분석",
            "originallink": "https://news.example.com/article/1002",
            "link": "https://n.news.naver.com/article/1002",
            "description": "국내 제약 업계의 최신 동향을 분석한다.",
            "pubDate": "Tue, 03 Mar 2026 10:00:00 +0900",
        },
    ],
}

# 빈 응답
NAVER_NEWS_EMPTY = {
    "lastBuildDate": "Wed, 04 Mar 2026 10:00:00 +0900",
    "total": 0,
    "start": 1,
    "display": 20,
    "items": [],
}


@pytest.mark.asyncio
async def test_news_alerts_on_new_article(config, mock_http, mock_notifier):
    """새 뉴스가 감지되면 알림 발송"""
    call_count = 0

    def get_side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        # initialize: 3 키워드 × 1 호출 = 3회
        if call_count <= 3:
            return make_mock_response(json_data=NAVER_NEWS_BASELINE)
        # check: 첫 번째 키워드에서 새 뉴스 발견
        return make_mock_response(json_data=NAVER_NEWS_WITH_NEW)

    mock_http.session.get = get_side_effect

    monitor = NewsMonitor(config=config, http_client=mock_http, notifier=mock_notifier)
    await monitor.initialize()
    mock_notifier.send.assert_not_called()

    await monitor.check()

    mock_notifier.send.assert_called_once()
    msg = mock_notifier.send.call_args[0][0]
    assert "뉴스 알림" in msg
    assert "코아스템켐온" in msg
    assert "뉴로나타" in msg
    assert "임상 3상 결과 발표" in msg
    assert "https://news.example.com/article/1003" in msg
    print(f"\n✅ News 테스트 통과: 신규 뉴스 감지 → 알림 발송")
    print(f"   전송된 메시지:\n{msg}")


@pytest.mark.asyncio
async def test_news_no_duplicate_alert(config, mock_http, mock_notifier):
    """이미 알림 보낸 뉴스는 다시 보내지 않음"""
    call_count = 0

    def get_side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count <= 3:
            return make_mock_response(json_data=NAVER_NEWS_BASELINE)
        return make_mock_response(json_data=NAVER_NEWS_WITH_NEW)

    mock_http.session.get = get_side_effect

    monitor = NewsMonitor(config=config, http_client=mock_http, notifier=mock_notifier)
    await monitor.initialize()

    await monitor.check()  # 첫 번째: 알림 발송
    await monitor.check()  # 두 번째: 같은 뉴스 → 알림 안됨

    assert mock_notifier.send.call_count == 1
    print(f"\n✅ News 테스트 통과: 중복 알림 방지 확인")


@pytest.mark.asyncio
async def test_news_dedup_across_keywords(config, mock_http, mock_notifier):
    """다른 키워드 검색에서 같은 기사가 나와도 1건만 알림"""
    call_count = 0

    # 모든 키워드에서 같은 새 뉴스를 반환하는 시나리오
    def get_side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count <= 3:
            return make_mock_response(json_data=NAVER_NEWS_BASELINE)
        # check 시 모든 키워드에서 동일한 새 기사 반환
        return make_mock_response(json_data=NAVER_NEWS_WITH_NEW)

    mock_http.session.get = get_side_effect

    monitor = NewsMonitor(config=config, http_client=mock_http, notifier=mock_notifier)
    await monitor.initialize()
    await monitor.check()

    # 3개 키워드 모두 같은 article/1003을 반환하지만 1건만 알림
    assert mock_notifier.send.call_count == 1
    print(f"\n✅ News 테스트 통과: 키워드 간 중복 제거 확인")


@pytest.mark.asyncio
async def test_news_strips_html_tags(config, mock_http, mock_notifier):
    """제목과 요약에서 HTML 태그가 제거되는지 확인"""
    call_count = 0

    def get_side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count <= 3:
            return make_mock_response(json_data=NAVER_NEWS_BASELINE)
        return make_mock_response(json_data=NAVER_NEWS_WITH_NEW)

    mock_http.session.get = get_side_effect

    monitor = NewsMonitor(config=config, http_client=mock_http, notifier=mock_notifier)
    await monitor.initialize()
    await monitor.check()

    msg = mock_notifier.send.call_args[0][0]
    # 네이버 API가 돌려주는 <b> 태그가 제거되었는지 확인
    assert "<b>코아스템켐온</b>" not in msg  # 원본 태그는 없어야 함
    assert "코아스템켐온, 뉴로나타 임상 3상 결과 발표" in msg  # 태그 없는 깨끗한 제목
    print(f"\n✅ News 테스트 통과: HTML 태그 제거 확인")
