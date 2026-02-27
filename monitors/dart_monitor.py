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
        self._check_count: int = 0

    async def initialize(self):
        self._corp_code = await self._resolve_corp_code()
        if not self._corp_code:
            logger.error("[DART] corp_code 변환 실패 | check()에서 재시도 예정")
            return

        disclosures = await self._fetch_disclosures()
        if disclosures:
            for d in disclosures:
                self._seen_rcept_nos.add(d["rcept_no"])
            logger.info(
                f"[DART] 초기화 완료 | corp_code={self._corp_code} | "
                f"기존 공시 {len(self._seen_rcept_nos)}건 로드"
            )
            for d in disclosures:
                logger.info(
                    f"[DART]   기존: {d['report_nm']} | "
                    f"접수번호={d['rcept_no']} | 접수일={d['rcept_dt']}"
                )
        else:
            logger.info(
                f"[DART] 초기화 완료 | corp_code={self._corp_code} | "
                f"최근 7일 공시 없음"
            )

    async def check(self):
        self._check_count += 1

        if not self._corp_code:
            self._corp_code = await self._resolve_corp_code()
            if not self._corp_code:
                return

        if self._backoff_seconds > 0:
            logger.info(f"[DART] Rate limit 백오프 {self._backoff_seconds:.1f}초 대기")
            await asyncio.sleep(self._backoff_seconds)
            self._backoff_seconds = 0

        disclosures = await self._fetch_disclosures()
        if disclosures is None:
            return

        new_disclosures = [d for d in disclosures if d["rcept_no"] not in self._seen_rcept_nos]

        if not new_disclosures:
            if self._check_count % 12 == 0:  # 1분마다 (5초 간격 x 12)
                logger.info(
                    f"[DART] 폴링 #{self._check_count} | "
                    f"조회 {len(disclosures)}건 | 신규 0건 | 변동 없음"
                )
        else:
            for d in new_disclosures:
                self._seen_rcept_nos.add(d["rcept_no"])

                logger.info(
                    f"[DART] ★ 신규 공시 감지! | {d['report_nm']} | "
                    f"접수번호={d['rcept_no']} | 접수일={d['rcept_dt']}"
                )

                summary = await self._fetch_document_summary(d["rcept_no"])
                if summary:
                    logger.info(f"[DART] 원문 요약 추출 완료 (접수번호={d['rcept_no']})")
                else:
                    logger.warning(f"[DART] 원문 요약 추출 실패 (접수번호={d['rcept_no']})")

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
                logger.info(f"[DART] 텔레그램 알림 발송 완료 | 접수번호={d['rcept_no']}")

        self._consecutive_errors = 0

    async def _resolve_corp_code(self) -> str | None:
        try:
            logger.info(f"[DART] corp_code 변환 시작 | 종목코드={self.config.DART_STOCK_CODE}")
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
                        f"[DART] corp_code 변환 성공 | "
                        f"종목코드={self.config.DART_STOCK_CODE} → corp_code={code}"
                    )
                    return code

            logger.error(
                f"[DART] 종목코드 {self.config.DART_STOCK_CODE}을 corpCode.xml에서 찾을 수 없음"
            )
            return None

        except Exception as e:
            logger.error(f"[DART] corp_code 변환 실패: {e}")
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
                    f"[DART] API 오류: status={status}, "
                    f"message={data.get('message')}"
                )
                return None

            return data.get("list", [])

        except Exception as e:
            self._consecutive_errors += 1
            logger.error(f"[DART] 공시 조회 실패: {e}")
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
                    logger.warning(f"[DART] 원문 다운로드 실패: HTTP {resp.status}")
                    return None
                data = await resp.read()

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
            logger.warning(f"[DART] 원문 응답이 ZIP이 아님 (접수번호={rcept_no})")
            return None
        except Exception as e:
            logger.warning(f"[DART] 원문 요약 실패: {e}")
            return None

    def _extract_summary(self, text: str) -> str:
        """원문 텍스트에서 핵심 내용을 추출"""
        lines = [line.strip() for line in text.splitlines()]
        lines = [line for line in lines if len(line) > 1]

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
                    cleaned = line[:150]
                    important_lines.append(cleaned)
                    seen.add(line)
                    break

            if len(important_lines) >= 15:
                break

        if important_lines:
            summary = "\n".join(f"  • {line}" for line in important_lines)
        else:
            content_lines = [l for l in lines if len(l) > 10][:10]
            summary = "\n".join(f"  • {line[:150]}" for line in content_lines)

        if len(summary) > 1500:
            summary = summary[:1500] + "\n  ..."

        return summary

    def _handle_rate_limit(self):
        self._consecutive_errors += 1
        self._backoff_seconds = min(2 ** self._consecutive_errors, 300)
        logger.warning(f"[DART] Rate limit 감지! 백오프: {self._backoff_seconds}초")
