"""
MFDS 모니터 테스트: 식약처 보도자료에 '뉴로나타' 또는 '루게릭' 키워드가
포함된 새 글이 올라오면 텔레그램 알림이 발송되는지 검증
"""
import pytest
from monitors.mfds_monitor import MfdsMonitor
from tests.conftest import make_mock_response

# --- 가짜 HTML 데이터 ---

# 초기 상태: 일반 보도자료 2건 (키워드 없음)
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

# 변경 후: 기존 2건 + '루게릭' 키워드가 포함된 새 글 1건 추가
MFDS_HTML_WITH_MATCH = """
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

# 변경 후: '뉴로나타' 키워드가 포함된 새 글
MFDS_HTML_WITH_NEURONATA = """
<html><body>
<ul class="bbs_list">
  <li>
    <a href="./view.do?seq=10004">뉴로나타-알주 품목허가 관련 보도자료</a>
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

# 키워드 없는 새 글만 추가된 경우
MFDS_HTML_NO_KEYWORD_NEW = """
<html><body>
<ul class="bbs_list">
  <li>
    <a href="./view.do?seq=10005">식약처, 건강기능식품 관리 강화</a>
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
async def test_mfds_detects_루게릭_keyword(config, mock_http, mock_notifier):
    """'루게릭' 키워드가 포함된 새 글 → 텔레그램 알림 발송"""
    call_count = 0

    def get_side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return make_mock_response(text=MFDS_HTML_BASELINE)
        return make_mock_response(text=MFDS_HTML_WITH_MATCH)

    mock_http.session.get = get_side_effect

    monitor = MfdsMonitor(config=config, http_client=mock_http, notifier=mock_notifier)
    await monitor.initialize()

    # 알림이 아직 없어야 함
    mock_notifier.send.assert_not_called()

    # check 실행 → 새 글 감지
    await monitor.check()

    # 텔레그램 알림이 발송되어야 함
    mock_notifier.send.assert_called_once()
    msg = mock_notifier.send.call_args[0][0]
    assert "루게릭" in msg
    assert "식약처 보도자료" in msg
    assert "10003" in msg
    print(f"\n✅ MFDS 테스트 통과: '루게릭' 키워드 감지")
    print(f"   전송된 메시지:\n{msg}")


@pytest.mark.asyncio
async def test_mfds_detects_뉴로나타_keyword(config, mock_http, mock_notifier):
    """'뉴로나타' 키워드가 포함된 새 글 → 텔레그램 알림 발송"""
    call_count = 0

    def get_side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return make_mock_response(text=MFDS_HTML_BASELINE)
        return make_mock_response(text=MFDS_HTML_WITH_NEURONATA)

    mock_http.session.get = get_side_effect

    monitor = MfdsMonitor(config=config, http_client=mock_http, notifier=mock_notifier)
    await monitor.initialize()
    await monitor.check()

    mock_notifier.send.assert_called_once()
    msg = mock_notifier.send.call_args[0][0]
    assert "뉴로나타" in msg
    print(f"\n✅ MFDS 테스트 통과: '뉴로나타' 키워드 감지")
    print(f"   전송된 메시지:\n{msg}")


@pytest.mark.asyncio
async def test_mfds_no_alert_without_keyword(config, mock_http, mock_notifier):
    """키워드 없는 새 글 → 알림 발송 안됨"""
    call_count = 0

    def get_side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return make_mock_response(text=MFDS_HTML_BASELINE)
        return make_mock_response(text=MFDS_HTML_NO_KEYWORD_NEW)

    mock_http.session.get = get_side_effect

    monitor = MfdsMonitor(config=config, http_client=mock_http, notifier=mock_notifier)
    await monitor.initialize()
    await monitor.check()

    mock_notifier.send.assert_not_called()
    print(f"\n✅ MFDS 테스트 통과: 키워드 미포함 글은 알림 없음")


@pytest.mark.asyncio
async def test_mfds_no_duplicate_alert(config, mock_http, mock_notifier):
    """이미 알림 보낸 글은 다시 보내지 않음"""
    call_count = 0

    def get_side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return make_mock_response(text=MFDS_HTML_BASELINE)
        return make_mock_response(text=MFDS_HTML_WITH_MATCH)

    mock_http.session.get = get_side_effect

    monitor = MfdsMonitor(config=config, http_client=mock_http, notifier=mock_notifier)
    await monitor.initialize()

    await monitor.check()
    await monitor.check()  # 같은 글로 두 번째 check

    # 한 번만 발송
    assert mock_notifier.send.call_count == 1
    print(f"\n✅ MFDS 테스트 통과: 중복 알림 방지 확인")
