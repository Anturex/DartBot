"""
nedrug 모니터 테스트: 뉴로나타-알주 상세페이지에서
품목기준코드 또는 허가일이 변경되면 텔레그램 알림이 발송되는지 검증
"""
import pytest
from monitors.nedrug_monitor import NedrugMonitor
from tests.conftest import make_mock_response

# --- 가짜 HTML 데이터 ---

# 초기 상태: 현재 실제 값
NEDRUG_HTML_BASELINE = """
<html><body>
<table>
  <tr><th>품목명</th><td>뉴로나타-알주(자가골수유래중간엽줄기세포)</td></tr>
  <tr><th>품목기준코드</th><td>202106193</td></tr>
  <tr><th>업체명</th><td>코아스템켐온(주)</td></tr>
  <tr><th>허가일</th><td>2021-08-27</td></tr>
  <tr><th>분류</th><td>전문의약품(희귀)</td></tr>
</table>
</body></html>
"""

# 시나리오 1: 허가일이 변경됨 (새로운 허가 승인)
NEDRUG_HTML_DATE_CHANGED = """
<html><body>
<table>
  <tr><th>품목명</th><td>뉴로나타-알주(자가골수유래중간엽줄기세포)</td></tr>
  <tr><th>품목기준코드</th><td>202106193</td></tr>
  <tr><th>업체명</th><td>코아스템켐온(주)</td></tr>
  <tr><th>허가일</th><td>2026-02-27</td></tr>
  <tr><th>분류</th><td>전문의약품(희귀)</td></tr>
</table>
</body></html>
"""

# 시나리오 2: 품목기준코드가 변경됨 (새 품목 등록)
NEDRUG_HTML_CODE_CHANGED = """
<html><body>
<table>
  <tr><th>품목명</th><td>뉴로나타-알주(자가골수유래중간엽줄기세포)</td></tr>
  <tr><th>품목기준코드</th><td>202602001</td></tr>
  <tr><th>업체명</th><td>코아스템켐온(주)</td></tr>
  <tr><th>허가일</th><td>2021-08-27</td></tr>
  <tr><th>분류</th><td>전문의약품(희귀)</td></tr>
</table>
</body></html>
"""

# 시나리오 3: 둘 다 변경됨
NEDRUG_HTML_BOTH_CHANGED = """
<html><body>
<table>
  <tr><th>품목명</th><td>뉴로나타-알주(자가골수유래중간엽줄기세포)</td></tr>
  <tr><th>품목기준코드</th><td>202602001</td></tr>
  <tr><th>업체명</th><td>코아스템켐온(주)</td></tr>
  <tr><th>허가일</th><td>2026-02-27</td></tr>
  <tr><th>분류</th><td>전문의약품(희귀)</td></tr>
</table>
</body></html>
"""


@pytest.mark.asyncio
async def test_nedrug_detects_approval_date_change(config, mock_http, mock_notifier):
    """허가일 변경 감지 → 텔레그램 알림"""
    call_count = 0

    def get_side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return make_mock_response(text=NEDRUG_HTML_BASELINE)
        return make_mock_response(text=NEDRUG_HTML_DATE_CHANGED)

    mock_http.session.get = get_side_effect

    monitor = NedrugMonitor(config=config, http_client=mock_http, notifier=mock_notifier)
    await monitor.initialize()

    assert monitor._last_approval_date == "2021-08-27"
    mock_notifier.send.assert_not_called()

    await monitor.check()

    mock_notifier.send.assert_called_once()
    msg = mock_notifier.send.call_args[0][0]
    assert "2021-08-27" in msg
    assert "2026-02-27" in msg
    assert "허가일" in msg
    print(f"\n✅ nedrug 테스트 통과: 허가일 변경 감지")
    print(f"   전송된 메시지:\n{msg}")


@pytest.mark.asyncio
async def test_nedrug_detects_item_code_change(config, mock_http, mock_notifier):
    """품목기준코드 변경 감지 → 텔레그램 알림"""
    call_count = 0

    def get_side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return make_mock_response(text=NEDRUG_HTML_BASELINE)
        return make_mock_response(text=NEDRUG_HTML_CODE_CHANGED)

    mock_http.session.get = get_side_effect

    monitor = NedrugMonitor(config=config, http_client=mock_http, notifier=mock_notifier)
    await monitor.initialize()
    await monitor.check()

    mock_notifier.send.assert_called_once()
    msg = mock_notifier.send.call_args[0][0]
    assert "202106193" in msg
    assert "202602001" in msg
    assert "품목기준코드" in msg
    print(f"\n✅ nedrug 테스트 통과: 품목기준코드 변경 감지")
    print(f"   전송된 메시지:\n{msg}")


@pytest.mark.asyncio
async def test_nedrug_detects_both_changes(config, mock_http, mock_notifier):
    """품목기준코드 + 허가일 동시 변경 → 텔레그램 알림 (변경사항 2개)"""
    call_count = 0

    def get_side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return make_mock_response(text=NEDRUG_HTML_BASELINE)
        return make_mock_response(text=NEDRUG_HTML_BOTH_CHANGED)

    mock_http.session.get = get_side_effect

    monitor = NedrugMonitor(config=config, http_client=mock_http, notifier=mock_notifier)
    await monitor.initialize()
    await monitor.check()

    mock_notifier.send.assert_called_once()
    msg = mock_notifier.send.call_args[0][0]
    assert "품목기준코드" in msg
    assert "허가일" in msg
    print(f"\n✅ nedrug 테스트 통과: 품목기준코드 + 허가일 동시 변경 감지")
    print(f"   전송된 메시지:\n{msg}")


@pytest.mark.asyncio
async def test_nedrug_no_alert_when_unchanged(config, mock_http, mock_notifier):
    """변경 없으면 알림 없음"""
    mock_http.session.get = lambda *a, **kw: make_mock_response(text=NEDRUG_HTML_BASELINE)

    monitor = NedrugMonitor(config=config, http_client=mock_http, notifier=mock_notifier)
    await monitor.initialize()
    await monitor.check()

    mock_notifier.send.assert_not_called()
    print(f"\n✅ nedrug 테스트 통과: 변경 없으면 알림 없음")


@pytest.mark.asyncio
async def test_nedrug_updates_baseline_after_alert(config, mock_http, mock_notifier):
    """알림 후 기준값이 업데이트되어 같은 변경에 대해 재알림 안됨"""
    call_count = 0

    def get_side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return make_mock_response(text=NEDRUG_HTML_BASELINE)
        return make_mock_response(text=NEDRUG_HTML_DATE_CHANGED)

    mock_http.session.get = get_side_effect

    monitor = NedrugMonitor(config=config, http_client=mock_http, notifier=mock_notifier)
    await monitor.initialize()

    await monitor.check()  # 변경 감지 → 알림
    await monitor.check()  # 같은 값 → 알림 없어야 함

    assert mock_notifier.send.call_count == 1
    assert monitor._last_approval_date == "2026-02-27"
    print(f"\n✅ nedrug 테스트 통과: 기준값 업데이트 후 중복 알림 방지")
