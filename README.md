# DartBot

코아스템켐온 뉴로나타-알주 식약처 품목허가 및 DART 공시를 실시간 감시하여 텔레그램으로 알림을 보내는 모니터링 서버.

## 감시 대상

| # | 소스 | 감시 주기 | 이벤트 조건 |
|---|------|-----------|-------------|
| 1 | 식약처 보도자료 | 1초 | 제목에 "뉴로나타" 또는 "루게릭" 포함 |
| 2 | nedrug 의약품 상세 | 1초 | 품목기준코드 또는 허가일 변경 |
| 3 | DART 공시 | 5초 | 코아스템켐온 신규 공시 등록 |

---

## 프로젝트 구조

```
DartBot/
├── main.py                    # FastAPI 앱 진입점, 모니터 라이프사이클 관리
├── config.py                  # 환경변수 로드 및 설정값 관리
├── telegram_notifier.py       # 텔레그램 메시지 전송
├── monitors/
│   ├── base.py                # 공통 폴링 루프 (BaseMonitor 추상 클래스)
│   ├── mfds_monitor.py        # 식약처 보도자료 감시
│   ├── nedrug_monitor.py      # nedrug 의약품 상세 감시
│   └── dart_monitor.py        # DART 공시 감시 + 내용 요약
├── utils/
│   └── http_client.py         # 공유 aiohttp 세션 (SSL/certifi 설정)
├── tests/
│   ├── conftest.py            # 테스트 공통 픽스처 (모킹 헬퍼)
│   ├── test_mfds_monitor.py   # MFDS 단위 테스트
│   ├── test_nedrug_monitor.py # nedrug 단위 테스트
│   ├── test_dart_monitor.py   # DART 단위 테스트
│   └── test_live.py           # 실제 API 통합 테스트
├── requirements.txt
├── render.yaml                # Render 배포 설정
├── .env.example               # 환경변수 템플릿
└── .gitignore
```

---

## 모듈별 상세 설명

### main.py - 앱 진입점

FastAPI의 lifespan 컨텍스트 매니저로 서버 시작/종료를 관리한다.

```
서버 시작
  ├─ HttpClient 생성 (aiohttp 세션, SSL 설정)
  ├─ TelegramNotifier 생성
  ├─ 3개 모니터를 asyncio.create_task로 동시 실행
  ├─ 텔레그램으로 "모니터링 시작" 알림 전송
  └─ /health, / 엔드포인트 제공 (Render 헬스체크용)

서버 종료
  ├─ stop_event.set() → 모든 모니터에 종료 신호
  ├─ 10초 내 graceful shutdown
  └─ HTTP 세션 닫기
```

### config.py - 설정 관리

환경변수에서 설정값을 로드하고, 필수값이 없으면 서버 시작 시점에 즉시 에러를 발생시킨다.

| 설정 | 기본값 | 설명 |
|------|--------|------|
| `TELEGRAM_BOT_TOKEN` | (필수) | 텔레그램 봇 토큰 |
| `TELEGRAM_CHAT_ID` | (필수) | 알림 받을 채팅 ID |
| `DART_API_KEY` | (필수) | DART OpenAPI 인증키 |
| `POLL_INTERVAL` | 1.0초 | MFDS/nedrug 폴링 간격 |
| `DART_POLL_INTERVAL` | 5.0초 | DART 폴링 간격 |
| `MFDS_KEYWORDS` | ("뉴로나타", "루게릭") | 식약처 감시 키워드 |
| `DART_STOCK_CODE` | "166480" | 코아스템켐온 종목코드 |
| `HTTP_TIMEOUT` | 10초 | HTTP 요청 타임아웃 |

### telegram_notifier.py - 텔레그램 알림

Telegram Bot API의 `sendMessage`를 aiohttp로 직접 호출한다. 별도 라이브러리 없이 최소 의존성으로 구현.

- HTML 파싱 모드로 **굵은 글씨**, *기울임* 지원
- 웹 페이지 미리보기 비활성화 (메시지를 깔끔하게)
- 전송 성공/실패를 bool로 반환

### utils/http_client.py - HTTP 클라이언트

세 모니터와 텔레그램이 공유하는 단일 aiohttp 세션을 관리한다.

- `certifi` 인증서 번들로 SSL 컨텍스트 구성 (한국 정부 사이트 인증서 체인 지원)
- TCP 커넥션 재사용으로 매 폴링마다 새 연결을 만들지 않음
- 10초 타임아웃으로 정부 사이트 응답 지연 대응

### monitors/base.py - 공통 폴링 루프

모든 모니터가 상속하는 추상 클래스. 핵심 패턴:

```python
while not stop_event.is_set():
    await self.check()                        # 감시 로직 실행
    await asyncio.wait_for(                   # 인터벌 대기 또는 종료 신호
        stop_event.wait(), timeout=interval
    )
```

- `initialize()` - 서버 시작 시 1회 호출. 현재 상태를 기준값으로 저장
- `check()` - 매 폴링마다 호출. 변경 감지 시 텔레그램 알림
- 개별 모니터의 예외가 다른 모니터에 영향을 주지 않음

---

## 감시 모듈 상세

### monitors/mfds_monitor.py - 식약처 보도자료

**조회 대상:** https://www.mfds.go.kr/brd/m_99/list.do

**조회 방식:**
1. 식약처 보도자료 목록 페이지의 HTML을 가져옴
2. BeautifulSoup으로 `<a href="./view.do?seq=NNN">` 태그를 파싱
3. 각 기사에서 **seq(고유번호)**, **제목**, **날짜**를 추출

**변경 감지 로직:**
```
초기화 시:
  페이지의 모든 기사 seq를 _seen_seqs 집합에 저장

매 1초마다:
  페이지를 다시 가져옴
  → 새로운 seq 발견?
    → 제목에 "뉴로나타" 또는 "루게릭" 포함?
      → YES: 텔레그램 긴급 알림 발송
      → NO:  로그만 남김 (새 글이지만 관련 없음)
```

**텔레그램 알림 예시:**
```
🚨 [식약처 보도자료 - 긴급]

제목: 식약처, 루게릭병 치료제 품목허가 승인
날짜: 2026-02-27
링크: https://www.mfds.go.kr/brd/m_99/view.do?seq=10003

⚠️ 뉴로나타-알주 관련 보도자료가 감지되었습니다!
```

---

### monitors/nedrug_monitor.py - nedrug 의약품 상세

**조회 대상:** https://nedrug.mfds.go.kr/pbp/CCBBB01/getItemDetail?itemSeq=202106193

**조회 방식:**
1. 뉴로나타-알주 제품 상세 페이지 HTML을 가져옴
2. `<th>품목기준코드</th><td>값</td>` 구조에서 두 필드를 추출:
   - **품목기준코드** (현재: `202106193`)
   - **허가일** (현재: `2021-08-27`)

**변경 감지 로직:**
```
초기화 시:
  현재 품목기준코드와 허가일을 기준값으로 저장
  (페이지 접속 실패 시 config의 기본값 사용)

매 1초마다:
  페이지를 다시 가져옴
  → 품목기준코드가 달라졌는가?  → 변경사항에 추가
  → 허가일이 달라졌는가?        → 변경사항에 추가
  → 변경사항이 1개 이상이면 텔레그램 알림 발송
  → 기준값을 새 값으로 업데이트 (중복 알림 방지)
```

**텔레그램 알림 예시:**
```
🚨 [nedrug 변경 감지 - 긴급]

제품: 뉴로나타-알주(자가골수유래중간엽줄기세포)
업체: 코아스템켐온(주)

변경사항:
  • 허가일: 2021-08-27 → 2026-02-27

링크: https://nedrug.mfds.go.kr/pbp/CCBBB01/getItemDetail?itemSeq=202106193
```

---

### monitors/dart_monitor.py - DART 공시

**조회 대상:**
| API | URL | 용도 |
|-----|-----|------|
| 기업코드 | `opendart.fss.or.kr/api/corpCode.xml` | 종목코드→기업코드 변환 (초기화 1회) |
| 공시목록 | `opendart.fss.or.kr/api/list.json` | 최근 7일 공시 조회 |
| 공시원문 | `opendart.fss.or.kr/api/document.xml` | 공시 내용 ZIP 다운로드 (요약용) |

**조회 방식:**

**1단계 - 기업코드 변환 (초기화 시 1회)**
```
DART corpCode.xml API 호출
→ ZIP 파일 수신 → CORPCODE.xml 추출
→ XML에서 stock_code="166480"인 항목 검색
→ corp_code 획득 (예: "00989664")
```

**2단계 - 공시 목록 조회 (매 5초)**
```
DART list.json API 호출
  파라미터: corp_code, bgn_de(7일전), end_de(오늘), page_count=100
→ JSON 응답에서 공시 목록 수신
→ 각 공시의 rcept_no(접수번호)로 신규 여부 판단
```

**3단계 - 공시 내용 요약 (새 공시 발견 시)**
```
DART document.xml API 호출 (rcept_no로)
→ ZIP 파일 수신 → HTML/XML 파일 추출
→ BeautifulSoup으로 텍스트 추출
→ 핵심 키워드 패턴으로 중요 라인 추출:
   결정일, 금액, 목적, 기간, 상대방, 허가, 임상, 매출 등
→ 최대 15줄, 1500자 이내로 요약
```

**변경 감지 로직:**
```
초기화 시:
  최근 7일 공시의 접수번호를 _seen_rcept_nos 집합에 저장

매 5초마다:
  공시 목록을 다시 조회
  → 새로운 접수번호 발견?
    → 공시 원문을 가져와서 핵심 내용 요약
    → 메타데이터 + 요약 포함하여 텔레그램 알림 발송
    → 접수번호를 seen 집합에 추가 (중복 방지)
```

**Rate Limit 처리:**
- DART API 일일 한도: ~20,000건
- 5초 간격 = 하루 17,280건 (한도 이내)
- HTTP 429 응답 시: 지수 백오프 (2초→4초→8초→...→최대 5분)

**텔레그램 알림 예시:**
```
📢 [DART 공시 알림]

회사: 코아스템켐온
보고서: 주요사항보고서(영업양수결정)
접수번호: 20260227000099
접수일: 20260227
제출인: 코아스템켐온
비고: 코

📋 핵심 요약:
  • 결정일: 2026-02-27
  • 양수 금액: 500억원
  • 양수 목적: 사업 확장 및 신약 파이프라인 강화
  • 양수 기간: 2026-03-01 ~ 2026-06-30
  • 상대방: 바이오제약(주)

링크: https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260227000099
```

---

## 실행 방법

### 사전 준비

**1. 텔레그램 봇 생성**
- 텔레그램에서 [@BotFather](https://t.me/BotFather)에게 `/newbot` 명령
- 봇 이름 설정 후 **봇 토큰** 복사
- 생성된 봇에게 아무 메시지 전송 후 아래 URL로 **채팅 ID** 확인:
  ```
  https://api.telegram.org/bot{토큰}/getUpdates
  ```
  응답의 `result[0].message.chat.id` 값이 채팅 ID

**2. DART API 키 발급**
- https://opendart.fss.or.kr 회원가입
- 인증키 신청/관리에서 **API 키** 발급

**3. 환경변수 설정**
```bash
cp .env.example .env
```
`.env` 파일에 실제 값 입력:
```
TELEGRAM_BOT_TOKEN=7588...
TELEGRAM_CHAT_ID=7935...
DART_API_KEY=4b0c...
```

### 로컬 실행

```bash
# 의존성 설치
pip install -r requirements.txt

# 서버 실행
uvicorn main:app --port 8000
```

서버가 시작되면:
- 텔레그램으로 "모니터링 시작" 메시지 수신
- http://localhost:8000/health 에서 상태 확인
- 로그에서 각 모니터의 초기화/폴링 상태 확인

### 테스트 실행

```bash
# 단위 테스트 (모킹, API 호출 없음)
python -m pytest tests/test_mfds_monitor.py tests/test_nedrug_monitor.py tests/test_dart_monitor.py -v -s

# 통합 테스트 (실제 API + 텔레그램 발송, .env 필요)
python -m pytest tests/test_live.py -v -s
```

### Render 배포

1. GitHub에 코드 푸시
2. Render에서 **New > Blueprint** 선택
3. 저장소 연결 → `render.yaml` 자동 감지
4. 환경변수 3개 입력 (TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, DART_API_KEY)
5. 배포 완료 후 텔레그램에서 시작 알림 확인

---

## 아키텍처

```
┌─────────────────────────────────────────────────┐
│                 main.py (FastAPI)                │
│          lifespan → asyncio.create_task          │
├────────────┬────────────┬───────────────────────┤
│  MFDS      │  nedrug    │  DART                 │
│  Monitor   │  Monitor   │  Monitor              │
│  (1초)     │  (1초)     │  (5초)                │
│            │            │                       │
│ 식약처 HTML │ nedrug HTML │ 1. corpCode.xml (ZIP) │
│ 파싱       │ 파싱       │ 2. list.json          │
│            │            │ 3. document.xml (ZIP)  │
│ 키워드     │ 필드값     │    → 내용 요약         │
│ 매칭       │ 비교       │                       │
├────────────┴────────────┴───────────────────────┤
│              TelegramNotifier                    │
│         api.telegram.org/sendMessage             │
├─────────────────────────────────────────────────┤
│              HttpClient (aiohttp)                │
│         공유 세션, SSL/certifi, 10s timeout       │
└─────────────────────────────────────────────────┘
```
