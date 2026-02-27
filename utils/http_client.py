from __future__ import annotations
import ssl
import aiohttp
import certifi
from config import Config


class HttpClient:
    def __init__(self, config: Config):
        self._session: aiohttp.ClientSession | None = None
        self._timeout = aiohttp.ClientTimeout(total=config.HTTP_TIMEOUT)
        self._ssl_ctx = ssl.create_default_context(cafile=certifi.where())

    async def start(self):
        conn = aiohttp.TCPConnector(ssl=self._ssl_ctx)
        self._session = aiohttp.ClientSession(
            timeout=self._timeout,
            connector=conn,
            headers={"User-Agent": "DartBot/1.0"},
        )

    async def close(self):
        if self._session:
            await self._session.close()
            self._session = None

    @property
    def session(self) -> aiohttp.ClientSession:
        if self._session is None:
            raise RuntimeError("HttpClient not started")
        return self._session
