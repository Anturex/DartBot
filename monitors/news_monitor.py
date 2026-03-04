from __future__ import annotations
import logging
import re
from datetime import datetime, timezone, timedelta
from monitors.base import BaseMonitor

logger = logging.getLogger(__name__)


class NewsMonitor(BaseMonitor):
    """네이버 뉴스 검색 API를 이용한 키워드 뉴스 모니터링"""

    def __init__(self, **kwargs):
        super().__init__(name="News", poll_interval=kwargs.pop("poll_interval", None), **kwargs)
        if self.poll_interval is None:
            self.poll_interval = self.config.NEWS_POLL_INTERVAL
        self._seen_links: set[str] = set()
        self._check_count: int = 0

    async def initialize(self):
        for keyword in self.config.NEWS_KEYWORDS:
            items = await self._search_news(keyword)
            for item in items:
                self._seen_links.add(item["link"])
        logger.info(
            f"[News] 초기화 완료 | 기존 뉴스 {len(self._seen_links)}건 로드 | "
            f"키워드: {', '.join(self.config.NEWS_KEYWORDS)}"
        )

    KST = timezone(timedelta(hours=9))

    def _is_active_hours(self) -> bool:
        """현재 한국 시각이 활성 시간대(08~18시)인지 확인"""
        now = datetime.now(self.KST)
        return self.config.NEWS_ACTIVE_START_HOUR <= now.hour < self.config.NEWS_ACTIVE_END_HOUR

    async def check(self):
        self._check_count += 1

        if not self._is_active_hours():
            if self._check_count % 360 == 0:  # 30분마다 로그
                logger.info(f"[News] 비활성 시간대 | 현재 KST {datetime.now(self.KST).strftime('%H:%M')}")
            return

        all_new_items: list[tuple[str, dict]] = []

        for keyword in self.config.NEWS_KEYWORDS:
            items = await self._search_news(keyword)
            for item in items:
                if item["link"] not in self._seen_links:
                    self._seen_links.add(item["link"])
                    all_new_items.append((keyword, item))

        if not all_new_items:
            if self._check_count % 10 == 0:
                logger.info(
                    f"[News] 폴링 #{self._check_count} | "
                    f"추적 {len(self._seen_links)}건 | 신규 0건"
                )
            return

        for keyword, item in all_new_items:
            title = self._strip_html(item.get("title", ""))
            description = self._strip_html(item.get("description", ""))
            originallink = item.get("originallink", item.get("link", ""))
            pub_date = item.get("pubDate", "")

            logger.info(
                f"[News] ★ 신규 뉴스 감지! | 키워드={keyword} | "
                f"제목: {title}"
            )

            msg = (
                f"📰 <b>[뉴스 알림]</b>\n\n"
                f"<b>키워드:</b> {keyword}\n"
                f"<b>제목:</b> {title}\n"
                f"<b>날짜:</b> {pub_date}\n"
            )
            if description:
                msg += f"\n<b>📋 요약:</b>\n  • {description}\n"
            msg += f"\n<b>링크:</b> {originallink}"

            await self.notifier.send(msg)
            self.alert_count += 1
            logger.info(f"[News] 텔레그램 알림 발송 완료 | {title}")

    async def _search_news(self, keyword: str) -> list[dict]:
        """네이버 뉴스 검색 API 호출"""
        headers = {
            "X-Naver-Client-Id": self.config.NAVER_CLIENT_ID,
            "X-Naver-Client-Secret": self.config.NAVER_CLIENT_SECRET,
        }
        params = {
            "query": keyword,
            "display": 20,
            "sort": "date",
        }
        try:
            async with self.http.session.get(
                self.config.NAVER_NEWS_API_URL,
                headers=headers,
                params=params,
            ) as resp:
                if resp.status != 200:
                    logger.warning(f"[News] API 응답 오류: HTTP {resp.status} (keyword={keyword})")
                    return []
                data = await resp.json()
                return data.get("items", [])
        except Exception as e:
            logger.warning(f"[News] API 호출 실패 (keyword={keyword}): {e}")
            return []

    @staticmethod
    def _strip_html(text: str) -> str:
        """HTML 태그 제거"""
        return re.sub(r"<[^>]+>", "", text).strip()
