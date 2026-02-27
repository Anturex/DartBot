from __future__ import annotations
import logging
from bs4 import BeautifulSoup
from monitors.base import BaseMonitor

logger = logging.getLogger(__name__)


class NedrugMonitor(BaseMonitor):
    def __init__(self, **kwargs):
        super().__init__(name="nedrug", **kwargs)
        self._last_item_seq: str | None = None
        self._last_approval_date: str | None = None
        self._check_count: int = 0

    async def initialize(self):
        data = await self._fetch_product_data()
        if data:
            self._last_item_seq = data["item_seq"]
            self._last_approval_date = data["approval_date"]
            logger.info(
                f"[nedrug] 초기화 완료 | "
                f"품목기준코드={self._last_item_seq} | "
                f"허가일={self._last_approval_date}"
            )
        else:
            self._last_item_seq = self.config.NEDRUG_KNOWN_ITEM_SEQ
            self._last_approval_date = self.config.NEDRUG_KNOWN_APPROVAL_DATE
            logger.warning(
                f"[nedrug] 초기화 시 파싱 실패 | "
                f"config 기본값 사용: 품목기준코드={self._last_item_seq}, "
                f"허가일={self._last_approval_date}"
            )

    async def check(self):
        self._check_count += 1

        data = await self._fetch_product_data()
        if not data:
            logger.warning(f"[nedrug] 폴링 #{self._check_count} | 페이지 파싱 실패")
            return

        changes = []
        if data["item_seq"] != self._last_item_seq:
            changes.append(
                f"품목기준코드: {self._last_item_seq} → {data['item_seq']}"
            )
        if data["approval_date"] != self._last_approval_date:
            changes.append(
                f"허가일: {self._last_approval_date} → {data['approval_date']}"
            )

        if changes:
            logger.info(
                f"[nedrug] ★ 변경 감지! | 폴링 #{self._check_count} | "
                f"변경사항: {changes}"
            )

            msg = (
                f"🚨 <b>[nedrug 변경 감지 - 긴급]</b>\n\n"
                f"<b>제품:</b> 뉴로나타-알주(자가골수유래중간엽줄기세포)\n"
                f"<b>업체:</b> 코아스템켐온(주)\n\n"
                f"<b>변경사항:</b>\n"
                + "\n".join(f"  • {c}" for c in changes)
                + f"\n\n<b>링크:</b> {self.config.NEDRUG_URL}"
            )
            await self.notifier.send(msg)
            self.alert_count += 1
            logger.info(f"[nedrug] 텔레그램 알림 발송 완료")

            self._last_item_seq = data["item_seq"]
            self._last_approval_date = data["approval_date"]
        else:
            if self._check_count % 10 == 0:  # 10초마다 (1초 간격 x 10)
                logger.info(
                    f"[nedrug] 폴링 #{self._check_count} | "
                    f"품목기준코드={data['item_seq']} | "
                    f"허가일={data['approval_date']} | 변동 없음"
                )

    async def _fetch_product_data(self) -> dict | None:
        try:
            async with self.http.session.get(self.config.NEDRUG_URL) as resp:
                resp.raise_for_status()
                html = await resp.text()
        except Exception as e:
            logger.error(f"[nedrug] Fetch failed: {e}")
            return None

        soup = BeautifulSoup(html, "html.parser")

        item_seq = None
        approval_date = None

        for th in soup.find_all("th"):
            text = th.get_text(strip=True)
            td = th.find_next_sibling("td")
            if not td:
                continue
            value = td.get_text(strip=True)

            if "품목기준코드" in text:
                item_seq = value
            elif "허가일" in text:
                approval_date = value

        if not item_seq and not approval_date:
            all_text = soup.get_text()
            if "202106193" in all_text:
                import re
                seq_match = re.search(r"202106193", all_text)
                if seq_match:
                    item_seq = "202106193"
                date_match = re.search(r"2021-08-27", all_text)
                if date_match:
                    approval_date = "2021-08-27"

        if not item_seq or not approval_date:
            logger.warning("[nedrug] Could not parse required fields from page")
            return None

        return {"item_seq": item_seq, "approval_date": approval_date}
