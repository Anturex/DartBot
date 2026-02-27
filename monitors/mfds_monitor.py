from __future__ import annotations
import logging
import re
from bs4 import BeautifulSoup
from monitors.base import BaseMonitor

logger = logging.getLogger(__name__)

BASE_URL = "https://www.mfds.go.kr/brd/m_99"


class MfdsMonitor(BaseMonitor):
    def __init__(self, **kwargs):
        super().__init__(name="MFDS", **kwargs)
        self._seen_seqs: set[str] = set()

    async def initialize(self):
        articles = await self._fetch_articles()
        for article in articles:
            self._seen_seqs.add(article["seq"])
        logger.info(f"[MFDS] Initialized with {len(self._seen_seqs)} known articles")

    async def check(self):
        articles = await self._fetch_articles()
        for article in articles:
            if article["seq"] in self._seen_seqs:
                continue

            self._seen_seqs.add(article["seq"])

            if self._matches_keywords(article["title"]):
                msg = (
                    f"🚨 <b>[식약처 보도자료 - 긴급]</b>\n\n"
                    f"<b>제목:</b> {article['title']}\n"
                    f"<b>날짜:</b> {article['date']}\n"
                    f"<b>링크:</b> {BASE_URL}/view.do?seq={article['seq']}\n\n"
                    f"⚠️ 뉴로나타-알주 관련 보도자료가 감지되었습니다!"
                )
                await self.notifier.send(msg)
                logger.info(f"[MFDS] KEYWORD MATCH alert sent for seq={article['seq']}")
            else:
                logger.debug(f"[MFDS] New article (no keyword match): {article['title']}")

    async def _fetch_articles(self) -> list[dict]:
        async with self.http.session.get(self.config.MFDS_URL) as resp:
            resp.raise_for_status()
            html = await resp.text()

        soup = BeautifulSoup(html, "html.parser")
        articles = []

        for a_tag in soup.find_all("a", href=re.compile(r"\./view\.do\?seq=")):
            title = a_tag.get_text(strip=True)
            href = a_tag["href"]

            seq_match = re.search(r"seq=(\d+)", href)
            if not seq_match:
                continue
            seq = seq_match.group(1)

            date = ""
            parent = a_tag.find_parent("li") or a_tag.find_parent("tr") or a_tag.find_parent("div")
            if parent:
                text = parent.get_text()
                date_match = re.search(r"\d{4}-\d{2}-\d{2}", text)
                if date_match:
                    date = date_match.group(0)

            articles.append({"seq": seq, "title": title, "date": date})

        return articles

    def _matches_keywords(self, title: str) -> bool:
        return any(kw in title for kw in self.config.MFDS_KEYWORDS)
