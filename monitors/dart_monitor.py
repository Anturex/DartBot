from __future__ import annotations
import asyncio
import io
import logging
import re
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from monitors.base import BaseMonitor

logger = logging.getLogger(__name__)


class DartMonitor(BaseMonitor):
    def __init__(self, config, **kwargs):
        super().__init__(
            name="DART",
            config=config,
            poll_interval=config.DART_POLL_INTERVAL,
            **kwargs,
        )
        self._corp_code: str | None = None
        self._seen_rcept_nos: set[str] = set()
        self._backoff_seconds: float = 0
        self._consecutive_errors: int = 0

    async def initialize(self):
        self._corp_code = await self._resolve_corp_code()
        if not self._corp_code:
            logger.error("[DART] Could not resolve corp_code; will retry in check()")
            return

        disclosures = await self._fetch_disclosures()
        if disclosures:
            for d in disclosures:
                self._seen_rcept_nos.add(d["rcept_no"])
            logger.info(
                f"[DART] Initialized with {len(self._seen_rcept_nos)} known disclosures"
            )

    async def check(self):
        if not self._corp_code:
            self._corp_code = await self._resolve_corp_code()
            if not self._corp_code:
                return

        if self._backoff_seconds > 0:
            logger.info(f"[DART] Backing off for {self._backoff_seconds:.1f}s")
            await asyncio.sleep(self._backoff_seconds)
            self._backoff_seconds = 0

        disclosures = await self._fetch_disclosures()
        if disclosures is None:
            return

        for d in disclosures:
            if d["rcept_no"] not in self._seen_rcept_nos:
                self._seen_rcept_nos.add(d["rcept_no"])

                summary = await self._fetch_document_summary(d["rcept_no"])

                msg = (
                    f"📢 <b>[DART 공시 알림]</b>\n\n"
                    f"<b>회사:</b> {d.get('corp_name', '코아스템켐온')}\n"
                    f"<b>보고서:</b> {d['report_nm']}\n"
                    f"<b>접수번호:</b> {d['rcept_no']}\n"
                    f"<b>접수일:</b> {d['rcept_dt']}\n"
                    f"<b>제출인:</b> {d.get('flr_nm', '-')}\n"
                    f"<b>비고:</b> {d.get('rm', '-')}\n\n"
                )
                if summary:
                    msg += f"<b>📋 핵심 요약:</b>\n{summary}\n\n"
                msg += (
                    f"<b>링크:</b> https://dart.fss.or.kr/dsaf001/main.do"
                    f"?rcpNo={d['rcept_no']}"
                )

                await self.notifier.send(msg)
                logger.info(f"[DART] Alert sent for rcept_no={d['rcept_no']}")

        self._consecutive_errors = 0

    async def _resolve_corp_code(self) -> str | None:
        try:
            params = {"crtfc_key": self.config.DART_API_KEY}
            async with self.http.session.get(
                self.config.DART_CORP_CODE_URL, params=params
            ) as resp:
                if resp.status == 429:
                    self._handle_rate_limit()
                    return None
                resp.raise_for_status()
                data = await resp.read()

            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                xml_name = zf.namelist()[0]
                with zf.open(xml_name) as f:
                    tree = ET.parse(f)

            root = tree.getroot()
            for corp in root.iter("list"):
                stock_code_el = corp.find("stock_code")
                corp_code_el = corp.find("corp_code")
                if (
                    stock_code_el is not None
                    and stock_code_el.text
                    and stock_code_el.text.strip() == self.config.DART_STOCK_CODE
                    and corp_code_el is not None
                ):
                    code = corp_code_el.text.strip()
                    logger.info(
                        f"[DART] Resolved stock_code {self.config.DART_STOCK_CODE} "
                        f"-> corp_code {code}"
                    )
                    return code

            logger.error(
                f"[DART] stock_code {self.config.DART_STOCK_CODE} not found in corpCode.xml"
            )
            return None

        except Exception as e:
            logger.error(f"[DART] Failed to resolve corp_code: {e}")
            return None

    async def _fetch_disclosures(self) -> list[dict] | None:
        today = datetime.now()
        bgn_de = (today - timedelta(days=7)).strftime("%Y%m%d")
        end_de = today.strftime("%Y%m%d")

        params = {
            "crtfc_key": self.config.DART_API_KEY,
            "corp_code": self._corp_code,
            "bgn_de": bgn_de,
            "end_de": end_de,
            "page_count": "100",
            "sort": "date",
            "sort_mth": "desc",
        }

        try:
            async with self.http.session.get(
                self.config.DART_API_URL, params=params
            ) as resp:
                if resp.status == 429:
                    self._handle_rate_limit()
                    return None
                resp.raise_for_status()
                data = await resp.json(content_type=None)

            status = data.get("status")
            if status == "013":
                return []
            elif status != "000":
                logger.error(
                    f"[DART] API error: status={status}, "
                    f"message={data.get('message')}"
                )
                return None

            return data.get("list", [])

        except Exception as e:
            self._consecutive_errors += 1
            logger.error(f"[DART] Fetch failed: {e}")
            return None

    async def _fetch_document_summary(self, rcept_no: str) -> str | None:
        """공시 원문 ZIP을 받아 핵심 내용을 추출·요약"""
        try:
            params = {
                "crtfc_key": self.config.DART_API_KEY,
                "rcept_no": rcept_no,
            }
            async with self.http.session.get(
                self.config.DART_DOCUMENT_URL, params=params
            ) as resp:
                if resp.status != 200:
                    logger.warning(f"[DART] Document fetch failed: HTTP {resp.status}")
                    return None
                data = await resp.read()

            # ZIP 안에 HTML/XML 파일들이 들어있음
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                text_parts = []
                for name in zf.namelist():
                    if name.endswith((".html", ".htm", ".xml")):
                        with zf.open(name) as f:
                            content = f.read()
                            soup = BeautifulSoup(content, "html.parser")
                            text_parts.append(soup.get_text(separator="\n"))

            if not text_parts:
                return None

            full_text = "\n".join(text_parts)
            return self._extract_summary(full_text)

        except zipfile.BadZipFile:
            logger.warning(f"[DART] Document response is not a ZIP (rcept_no={rcept_no})")
            return None
        except Exception as e:
            logger.warning(f"[DART] Document summary failed: {e}")
            return None

    def _extract_summary(self, text: str) -> str:
        """원문 텍스트에서 핵심 내용을 추출"""
        # 빈 줄, 공백 정리
        lines = [line.strip() for line in text.splitlines()]
        lines = [line for line in lines if len(line) > 1]

        # 핵심 키워드가 포함된 줄을 우선 추출
        key_patterns = [
            r"결정일|이사회결의일|결의일",
            r"신규.*시설|투자|계약|양수|양도|합병",
            r"금액|규모|총액|대금",
            r"목적|사유|내용",
            r"기간|일자|일시|예정일",
            r"상대방|거래처|대상",
            r"허가|승인|인가|취득",
            r"임상|시험|결과",
            r"매출|영업|손익|이익|손실",
        ]

        important_lines = []
        seen = set()
        for line in lines:
            for pattern in key_patterns:
                if re.search(pattern, line) and line not in seen:
                    # 표 형태 (항목: 값) 라인 우선
                    cleaned = line[:150]  # 너무 긴 줄 자르기
                    important_lines.append(cleaned)
                    seen.add(line)
                    break

            if len(important_lines) >= 15:
                break

        if important_lines:
            summary = "\n".join(f"  • {line}" for line in important_lines)
        else:
            # 키워드 매칭이 안 되면 앞부분 텍스트 발췌
            content_lines = [l for l in lines if len(l) > 10][:10]
            summary = "\n".join(f"  • {line[:150]}" for line in content_lines)

        if len(summary) > 1500:
            summary = summary[:1500] + "\n  ..."

        return summary

    def _handle_rate_limit(self):
        self._consecutive_errors += 1
        self._backoff_seconds = min(2 ** self._consecutive_errors, 300)
        logger.warning(f"[DART] Rate limited. Backoff: {self._backoff_seconds}s")
