"""
DART 모니터 테스트: 코아스템켐온 관련 새로운 공시가 등록되면
텔레그램 알림이 발송되는지 검증
"""
import io
import zipfile
import xml.etree.ElementTree as ET
import pytest
from monitors.dart_monitor import DartMonitor
from tests.conftest import make_mock_response

# --- 가짜 corp_code ZIP 데이터 생성 ---


def _make_corp_code_zip() -> bytes:
    """DART corpCode.xml ZIP 파일을 가짜로 생성"""
    root = ET.Element("result")

    # 다른 회사
    item1 = ET.SubElement(root, "list")
    ET.SubElement(item1, "corp_code").text = "00100001"
    ET.SubElement(item1, "corp_name").text = "삼성전자"
    ET.SubElement(item1, "stock_code").text = "005930"

    # 코아스템켐온
    item2 = ET.SubElement(root, "list")
    ET.SubElement(item2, "corp_code").text = "01234567"
    ET.SubElement(item2, "corp_name").text = "코아스템켐온"
    ET.SubElement(item2, "stock_code").text = "166480"

    xml_bytes = ET.tostring(root, encoding="utf-8", xml_declaration=True)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("CORPCODE.xml", xml_bytes)
    return buf.getvalue()


CORP_CODE_ZIP = _make_corp_code_zip()


def _make_document_zip() -> bytes:
    """DART 공시 원문 ZIP 파일을 가짜로 생성"""
    html_content = """
    <html><body>
    <h1>주요사항보고서</h1>
    <table>
    <tr><td>1. 보고서명</td><td>주요사항보고서(영업양수결정)</td></tr>
    <tr><td>2. 결정일</td><td>2026-02-27</td></tr>
    <tr><td>3. 양수 금액</td><td>500억원</td></tr>
    <tr><td>4. 양수 목적</td><td>사업 확장 및 신약 파이프라인 강화</td></tr>
    <tr><td>5. 양수 기간</td><td>2026-03-01 ~ 2026-06-30</td></tr>
    <tr><td>6. 상대방</td><td>바이오제약(주)</td></tr>
    </table>
    </body></html>
    """
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("document.html", html_content.encode("utf-8"))
    return buf.getvalue()


DOCUMENT_ZIP = _make_document_zip()

# --- 가짜 DART API 응답 ---

# 초기 상태: 기존 공시 1건
DART_RESPONSE_BASELINE = {
    "status": "000",
    "message": "정상",
    "total_count": 1,
    "list": [
        {
            "corp_code": "01234567",
            "corp_name": "코아스템켐온",
            "stock_code": "166480",
            "report_nm": "분기보고서 (2025.09)",
            "rcept_no": "20250301000001",
            "flr_nm": "코아스템켐온",
            "rcept_dt": "20250301",
            "rm": "",
        }
    ],
}

# 변경 후: 기존 1건 + 새로운 공시 1건 추가
DART_RESPONSE_NEW_DISCLOSURE = {
    "status": "000",
    "message": "정상",
    "total_count": 2,
    "list": [
        {
            "corp_code": "01234567",
            "corp_name": "코아스템켐온",
            "stock_code": "166480",
            "report_nm": "주요사항보고서(영업양수결정)",
            "rcept_no": "20260227000099",
            "flr_nm": "코아스템켐온",
            "rcept_dt": "20260227",
            "rm": "코",
        },
        {
            "corp_code": "01234567",
            "corp_name": "코아스템켐온",
            "stock_code": "166480",
            "report_nm": "분기보고서 (2025.09)",
            "rcept_no": "20250301000001",
            "flr_nm": "코아스템켐온",
            "rcept_dt": "20250301",
            "rm": "",
        },
    ],
}

# 공시 없음
DART_RESPONSE_EMPTY = {
    "status": "013",
    "message": "조회된 데이터가 없습니다.",
}


@pytest.mark.asyncio
async def test_dart_detects_new_disclosure_with_summary(config, mock_http, mock_notifier):
    """새로운 공시 등록 → 내용 요약 포함 텔레그램 알림 발송"""
    call_count = 0

    def get_side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        url = args[0] if args else kwargs.get("url", "")

        if "corpCode" in str(url):
            return make_mock_response(read_data=CORP_CODE_ZIP)
        if "document" in str(url):
            return make_mock_response(read_data=DOCUMENT_ZIP)

        call_count_api = call_count - 1
        if call_count_api <= 1:
            return make_mock_response(json_data=DART_RESPONSE_BASELINE)
        return make_mock_response(json_data=DART_RESPONSE_NEW_DISCLOSURE)

    mock_http.session.get = get_side_effect

    monitor = DartMonitor(config=config, http_client=mock_http, notifier=mock_notifier)
    await monitor.initialize()

    assert monitor._corp_code == "01234567"
    assert "20250301000001" in monitor._seen_rcept_nos
    mock_notifier.send.assert_not_called()

    await monitor.check()

    mock_notifier.send.assert_called_once()
    msg = mock_notifier.send.call_args[0][0]
    assert "코아스템켐온" in msg
    assert "주요사항보고서" in msg
    assert "20260227000099" in msg
    assert "DART 공시 알림" in msg
    assert "핵심 요약" in msg
    assert "금액" in msg or "결정일" in msg or "목적" in msg
    print(f"\n✅ DART 테스트 통과: 새 공시 감지 + 내용 요약 포함")
    print(f"   전송된 메시지:\n{msg}")


@pytest.mark.asyncio
async def test_dart_no_alert_when_no_new(config, mock_http, mock_notifier):
    """새 공시 없으면 알림 없음"""
    call_count = 0

    def get_side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        url = args[0] if args else kwargs.get("url", "")
        if "corpCode" in str(url):
            return make_mock_response(read_data=CORP_CODE_ZIP)
        return make_mock_response(json_data=DART_RESPONSE_BASELINE)

    mock_http.session.get = get_side_effect

    monitor = DartMonitor(config=config, http_client=mock_http, notifier=mock_notifier)
    await monitor.initialize()
    await monitor.check()

    mock_notifier.send.assert_not_called()
    print(f"\n✅ DART 테스트 통과: 새 공시 없으면 알림 없음")


@pytest.mark.asyncio
async def test_dart_no_alert_on_empty_response(config, mock_http, mock_notifier):
    """DART API가 '데이터 없음(013)' 반환 시 정상 처리"""
    call_count = 0

    def get_side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        url = args[0] if args else kwargs.get("url", "")
        if "corpCode" in str(url):
            return make_mock_response(read_data=CORP_CODE_ZIP)
        return make_mock_response(json_data=DART_RESPONSE_EMPTY)

    mock_http.session.get = get_side_effect

    monitor = DartMonitor(config=config, http_client=mock_http, notifier=mock_notifier)
    await monitor.initialize()
    await monitor.check()

    mock_notifier.send.assert_not_called()
    print(f"\n✅ DART 테스트 통과: 데이터 없음 응답 정상 처리")


@pytest.mark.asyncio
async def test_dart_no_duplicate_alert(config, mock_http, mock_notifier):
    """이미 알림 보낸 공시는 재발송 안됨"""
    call_count = 0

    def get_side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        url = args[0] if args else kwargs.get("url", "")
        if "corpCode" in str(url):
            return make_mock_response(read_data=CORP_CODE_ZIP)
        if "document" in str(url):
            return make_mock_response(read_data=DOCUMENT_ZIP)
        if call_count <= 2:  # corpCode(1) + initialize(2)
            return make_mock_response(json_data=DART_RESPONSE_BASELINE)
        return make_mock_response(json_data=DART_RESPONSE_NEW_DISCLOSURE)

    mock_http.session.get = get_side_effect

    monitor = DartMonitor(config=config, http_client=mock_http, notifier=mock_notifier)
    await monitor.initialize()

    await monitor.check()  # 새 공시 감지
    await monitor.check()  # 같은 공시 → 알림 없어야 함

    assert mock_notifier.send.call_count == 1
    print(f"\n✅ DART 테스트 통과: 중복 알림 방지 확인")


@pytest.mark.asyncio
async def test_dart_corp_code_resolution(config, mock_http, mock_notifier):
    """종목코드 166480 → corp_code 변환 정상 동작"""
    def get_side_effect(*args, **kwargs):
        url = args[0] if args else kwargs.get("url", "")
        if "corpCode" in str(url):
            return make_mock_response(read_data=CORP_CODE_ZIP)
        return make_mock_response(json_data=DART_RESPONSE_EMPTY)

    mock_http.session.get = get_side_effect

    monitor = DartMonitor(config=config, http_client=mock_http, notifier=mock_notifier)
    await monitor.initialize()

    assert monitor._corp_code == "01234567"
    print(f"\n✅ DART 테스트 통과: corp_code 변환 (166480 → 01234567)")
