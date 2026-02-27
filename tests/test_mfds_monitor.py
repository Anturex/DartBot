"""
MFDS 모니터 테스트: 식약처 보도자료에 새 글이 올라오면
본문 요약과 함께 텔레그램 알림이 발송되는지 검증
"""
import pytest
from monitors.mfds_monitor import MfdsMonitor
from tests.conftest import make_mock_response

# --- 가짜 HTML 데이터 ---

# 초기 상태: 보도자료 2건
MFDS_HTML_BASELINE = """
<html><body>
<ul class="bbs_list">
  <li>
    <a href="./view.do?seq=10001">식약처, 화장품 안전기준 강화</a>
    <span>2026-02-25</span>
  </li>
  <li>
    <a href="./view.do?seq=10002">식약처, 의약품 유통 관리 개선</a>
    <span>2026-02-26</span>
  </li>
</ul>
</body></html>
"""

# 변경 후: 새 글 1건 추가
MFDS_HTML_WITH_NEW = """
<html><body>
<ul class="bbs_list">
  <li>
    <a href="./view.do?seq=10003">식약처, 루게릭병 치료제 품목허가 승인</a>
    <span>2026-02-27</span>
  </li>
  <li>
    <a href="./view.do?seq=10001">식약처, 화장품 안전기준 강화</a>
    <span>2026-02-25</span>
  </li>
  <li>
    <a href="./view.do?seq=10002">식약처, 의약품 유통 관리 개선</a>
    <span>2026-02-26</span>
  </li>
</ul>
</body></html>
"""

# 상세 페이지 본문 HTML
MFDS_DETAIL_HTML = """
<html><body>
<div class="view_cont">
  <p>식약처는 루게릭병 치료제인 뉴로나타-알주에 대해 품목허가를 승인하였다.</p>
  <p>코아스템켐온이 개발한 자가골수유래중간엽줄기세포 치료제로, 근위축성측삭경화증(ALS) 환자를 대상으로 한다.</p>
  <p>허가 조건 및 세부사항은 식약처 홈페이지를 참고하시기 바랍니다.</p>
</div>
</body></html>
"""

# 새 글 2건 동시 추가
MFDS_HTML_WITH_TWO_NEW = """
<html><body>
<ul class="bbs_list">
  <li>
    <a href="./view.do?seq=10004">식약처, 건강기능식품 관리 강화</a>
    <span>2026-02-27</span>
  </li>
  <li>
    <a href="./view.do?seq=10003">식약처, 루게릭병 치료제 품목허가 승인</a>
    <span>2026-02-27</span>
  </li>
  <li>
    <a href="./view.do?seq=10001">식약처, 화장품 안전기준 강화</a>
    <span>2026-02-25</span>
  </li>
  <li>
    <a href="./view.do?seq=10002">식약처, 의약품 유통 관리 개선</a>
    <span>2026-02-26</span>
  </li>
</ul>
</body></html>
"""


@pytest.mark.asyncio
async def test_mfds_alerts_on_any_new_article(config, mock_http, mock_notifier):
    """새 글이 올라오면 키워드 상관없이 알림 발송"""
    call_count = 0

    def get_side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return make_mock_response(text=MFDS_HTML_BASELINE)
        # check() → 목록 조회
        if call_count == 2:
            return make_mock_response(text=MFDS_HTML_WITH_NEW)
        # check() → 상세 페이지 조회
        return make_mock_response(text=MFDS_DETAIL_HTML)

    mock_http.session.get = get_side_effect

    monitor = MfdsMonitor(config=config, http_client=mock_http, notifier=mock_notifier)
    await monitor.initialize()
    mock_notifier.send.assert_not_called()

    await monitor.check()

    mock_notifier.send.assert_called_once()
    msg = mock_notifier.send.call_args[0][0]
    assert "루게릭병 치료제 품목허가 승인" in msg
    assert "식약처 보도자료" in msg
    assert "10003" in msg
    print(f"\n✅ MFDS 테스트 통과: 신규 글 감지 → 알림 발송")
    print(f"   전송된 메시지:\n{msg}")


@pytest.mark.asyncio
async def test_mfds_includes_summary(config, mock_http, mock_notifier):
    """알림에 본문 요약이 포함되는지 확인"""
    call_count = 0

    def get_side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return make_mock_response(text=MFDS_HTML_BASELINE)
        if call_count == 2:
            return make_mock_response(text=MFDS_HTML_WITH_NEW)
        return make_mock_response(text=MFDS_DETAIL_HTML)

    mock_http.session.get = get_side_effect

    monitor = MfdsMonitor(config=config, http_client=mock_http, notifier=mock_notifier)
    await monitor.initialize()
    await monitor.check()

    msg = mock_notifier.send.call_args[0][0]
    assert "내용 요약" in msg
    assert "뉴로나타-알주" in msg
    print(f"\n✅ MFDS 테스트 통과: 본문 요약 포함 확인")


@pytest.mark.asyncio
async def test_mfds_alerts_multiple_new_articles(config, mock_http, mock_notifier):
    """새 글이 2건 동시에 올라오면 2건 모두 알림"""
    call_count = 0

    def get_side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return make_mock_response(text=MFDS_HTML_BASELINE)
        if call_count == 2:
            return make_mock_response(text=MFDS_HTML_WITH_TWO_NEW)
        return make_mock_response(text=MFDS_DETAIL_HTML)

    mock_http.session.get = get_side_effect

    monitor = MfdsMonitor(config=config, http_client=mock_http, notifier=mock_notifier)
    await monitor.initialize()
    await monitor.check()

    assert mock_notifier.send.call_count == 2
    print(f"\n✅ MFDS 테스트 통과: 신규 2건 → 알림 2건 발송")


@pytest.mark.asyncio
async def test_mfds_no_duplicate_alert(config, mock_http, mock_notifier):
    """이미 알림 보낸 글은 다시 보내지 않음"""
    call_count = 0

    def get_side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return make_mock_response(text=MFDS_HTML_BASELINE)
        if call_count <= 3:
            return make_mock_response(text=MFDS_HTML_WITH_NEW)
        return make_mock_response(text=MFDS_DETAIL_HTML)

    mock_http.session.get = get_side_effect

    monitor = MfdsMonitor(config=config, http_client=mock_http, notifier=mock_notifier)
    await monitor.initialize()

    await monitor.check()  # 첫 번째: 알림 발송
    await monitor.check()  # 두 번째: 같은 글 → 알림 안됨

    assert mock_notifier.send.call_count == 1
    print(f"\n✅ MFDS 테스트 통과: 중복 알림 방지 확인")
