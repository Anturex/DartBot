import pytest
from unittest.mock import AsyncMock, MagicMock
from config import Config


@pytest.fixture
def config():
    return Config(
        TELEGRAM_BOT_TOKEN="test-token",
        TELEGRAM_CHAT_ID="test-chat-id",
        DART_API_KEY="test-dart-key",
    )


@pytest.fixture
def mock_notifier():
    notifier = AsyncMock()
    notifier.send = AsyncMock(return_value=True)
    return notifier


def make_mock_response(text="", status=200, json_data=None, read_data=None):
    """aiohttp response를 모킹하는 컨텍스트 매니저 생성"""
    resp = AsyncMock()
    resp.status = status
    resp.raise_for_status = MagicMock()
    resp.text = AsyncMock(return_value=text)
    resp.json = AsyncMock(return_value=json_data)
    resp.read = AsyncMock(return_value=read_data or b"")

    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=resp)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


@pytest.fixture
def mock_http():
    http = MagicMock()
    http.session = MagicMock()
    return http
