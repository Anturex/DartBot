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
        self._check_count: int = 0

    async def initialize(self):
        articles = await self._fetch_articles()
        for article in articles:
            self._seen_seqs.add(article["seq"])
        logger.info(
            f"[MFDS] 초기화 완료 | 기존 보도자료 {len(self._seen_seqs)}건 로드"
        )

    async def check(self):
        self._check_count += 1
        articles = await self._fetch_articles()

        new_articles = [a for a in articles if a["seq"] not in self._seen_seqs]

        if not new_articles:
            if self._check_count % 10 == 0:
                logger.info(
                    f"[MFDS] 폴링 #{self._check_count} | "
                    f"파싱 {len(articles)}건 | 신규 0건"
                )
            return

        for article in new_articles:
            self._seen_seqs.add(article["seq"])

            logger.info(
                f"[MFDS] ★ 신규 보도자료 감지! | seq={article['seq']} | "
                f"제목: {article['title']} | 날짜: {article['date']}"
            )

            summary = await self._fetch_article_summary(article["seq"])

            msg = (
                f"📢 <b>[식약처 보도자료]</b>\n\n"
                f"<b>제목:</b> {article['title']}\n"
                f"<b>날짜:</b> {article['date']}\n"
            )
            if summary:
                msg += f"\n<b>📋 내용 요약:</b>\n{summary}\n"
            msg += (
                f"\n<b>링크:</b> {BASE_URL}/view.do?seq={article['seq']}"
            )
            await self.notifier.send(msg)
            logger.info(f"[MFDS] 텔레그램 알림 발송 완료 | seq={article['seq']}")

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

    async def _fetch_article_summary(self, seq: str) -> str | None:
        """보도자료 상세 페이지에서 본문을 가져와 요약"""
        url = f"{BASE_URL}/view.do?seq={seq}"
        try:
            async with self.http.session.get(url) as resp:
                if resp.status != 200:
                    logger.warning(f"[MFDS] 상세 페이지 로드 실패: HTTP {resp.status}")
                    return None
                html = await resp.text()

            soup = BeautifulSoup(html, "html.parser")

            content_div = (
                soup.find("div", class_="view_cont")
                or soup.find("div", class_="cont_area")
                or soup.find("div", id="cont_area")
                or soup.find("td", class_="view_con")
            )

            if content_div:
                text = content_div.get_text(separator="\n")
            else:
                text = soup.get_text(separator="\n")

            lines = [line.strip() for line in text.splitlines()]
            lines = [line for line in lines if len(line) > 5]

            summary_lines = []
            for line in lines:
                if len(line) > 300:
                    line = line[:300]
                summary_lines.append(line)
                if len(summary_lines) >= 10:
                    break

            if not summary_lines:
                return None

            summary = "\n".join(f"  • {line}" for line in summary_lines)
            if len(summary) > 1500:
                summary = summary[:1500] + "\n  ..."
            return summary

        except Exception as e:
            logger.warning(f"[MFDS] 본문 요약 실패 (seq={seq}): {e}")
            return None
