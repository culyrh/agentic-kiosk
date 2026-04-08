# 🍔 Sadollar Kiosk - AI 음성 주문 키오스크

롯데리아 매장에서 사용자가 음성으로 메뉴를 탐색하고 결제까지 완료할 수 있는 배리어 프리(Barrier-free) 음성 주문 시스템입니다.

---

## 시스템 동작 구조
```
사용자 음성
↓
STT (Whisper)
↓
텍스트
↓
AI 에이전트 (LangChain)
↓                         ↓
ChromaDB 검색              SQLite 조회 (백엔드)
(의미 기반 검색)            (정확한 데이터)
↓                         ↓
menu_id 반환    →→→        가격, 알레르기, 세트 여부
                           장바구니, 주문, 결제 처리
↓
LLM 응답 생성
↓
TTS
↓
음성 출력
```

---

## DB 구조

### SQLite 테이블 (ria_menu.db)

| 테이블 | 역할 | 데이터 수 |
|--------|------|-----------|
| menu | 단품 메뉴 전체 | 82개 |
| options | 세트 구성 선택지 (드링크/사이드/토핑) | 43개 |
| set_menus | 버거별 세트 구성 및 가격 | 23개 |
| set_options | 세트-옵션 연결 | 989개 |
| cart | 주문 중인 장바구니 (주문 시 채워짐) | - |
| orders | 결제 완료된 주문 내역 | - |
| sessions | 현재 대화 상태 저장 | - |

### 메뉴 ID 체계 (카테고리별 100번대)

| 카테고리 | ID 범위 |
|----------|---------|
| 버거 | 101 ~ 199 |
| 디저트 | 201 ~ 299 |
| 치킨 | 301 ~ 399 |
| 음료 | 401 ~ 499 |
| 아이스샷 | 501 ~ 599 |
| 토핑 | 601 ~ 699 |

---


## 환경 세팅

### 1. Python 버전
```
Python 3.10.11 권장
```

### 2. 가상환경 생성 및 활성화
```bash
py -3.10 -m venv venv

# Windows
venv\Scripts\activate

# Mac/Linux
source venv/bin/activate
```

### 3. 패키지 설치
```bash
pip install -r requirements.txt
```

### 4. 환경변수 설정
`.env` 파일 생성 후 OpenAI API 키 입력:
```
OPENAI_API_KEY=sk-...
```

---

## DB 초기화 (최초 1회)
```bash
# 1. 테이블 생성
python db_setup.py

# 2. JSON 데이터 → DB 삽입
python insert_data.py
```

---

## RAG 메뉴 검색 테스트

`ria_menu.json` → ChromaDB 임베딩 저장 → 유사도 검색까지 테스트합니다.
```bash
python test.py
```

처음 실행 시 ChromaDB가 생성됩니다. 이후 실행부터는 기존 DB에 upsert됩니다.

> ⚠️ 현재 test.py는 매번 실행 시 모델을 새로 로드하므로 속도가 느립니다.
> FastAPI 서버에 붙이면 모델이 메모리에 유지되어 속도가 개선됩니다.

---

## AI 에이전트 Tool 함수 목록

LangChain ReAct 에이전트가 사용하는 tool 함수 목록입니다.

| 함수 | 파일 | 기능 |
|------|------|------|
| `search_menu` | menu_tools.py | RAG 기반 메뉴 검색 |
| `get_menu_by_price` | menu_tools.py | 가격 기준 메뉴 조회 (최저/최고/예산 범위) |
| `get_menu_info` | menu_tools.py | 특정 메뉴 가격·설명 조회 |
| `add_to_cart` | cart_tools.py | 장바구니에 메뉴 추가 |
| `remove_from_cart` | cart_tools.py | 장바구니에서 특정 메뉴 제거 |
| `view_cart` | cart_tools.py | 장바구니 목록 및 총 금액 확인 |
| `confirm_order` | cart_tools.py | 주문 완료 및 결제 처리 |
| `clear_cart` | cart_tools.py | 장바구니 전체 비우기 |

<br>

DB 담당이랑 확인 후 추가될 수 있는 것:

| 함수 | 기능 |
|------|------|
|세트 메뉴 주문 | add_to_cart에 is_set, side_option, drink_option 처리 |

---

## STT (음성 인식)

허깅페이스 허브에서 Whisper 모델을 로컬로 다운로드해 추론합니다. OpenAI API를 사용하지 않습니다.

- 모델: `Systran/faster-whisper-{size}`
- 처음 실행 시 자동 다운로드, 이후 캐시에서 로드

### 모델 크기 선택

| 모델 | 다운로드 크기 | 속도 | 한국어 정확도 |
|------|-------------|------|--------------|
| small | ~500MB | 빠름 | 보통 |
| medium | ~1.5GB | 중간 | 좋음 |
| large-v3 | ~3GB | 느림 | 매우 좋음 |
| large-v3-turbo | ~1.6GB | 중간 | 매우 좋음 |

### 녹음파일 인식

```bash
# 기본 (medium 모델)
python voice/stt.py tests/뉴스녹음.m4a

# 모델 크기 지정
python voice/stt.py tests/뉴스녹음.m4a small
python voice/stt.py tests/뉴스녹음.m4a large-v3
python voice/stt.py tests/뉴스녹음.m4a large-v3-turbo
```

결과는 터미널에 출력되고 `tests/results/`에 텍스트 파일로 저장됩니다.
```
tests/results/뉴스녹음_medium_20260326_210639.txt
```

### 실시간 음성 인식

마이크로 말하면 발화가 끝나는 시점을 자동으로 감지해 바로 인식합니다.

```bash
# 기본 (small 모델, 한국어)
python voice/stt_realtime.py

# 옵션 지정
python voice/stt_realtime.py --model small --device cpu --language ko

# 주변 소음이 많을 때 (임계값을 높여 잡음 오인식 방지)
python voice/stt_realtime.py --threshold 0.03
```

| 옵션 | 기본값 | 설명 |
|------|--------|------|
| `--model` | `small` | 모델 크기 (tiny / small / medium / large-v3) |
| `--device` | `cpu` | 추론 장치 (cpu / cuda) |
| `--language` | `ko` | 인식 언어 코드 |
| `--threshold` | `0.01` | 음성 감지 민감도 — 낮을수록 민감, 높을수록 잡음 무시 |

실행하면 마이크 대기 상태가 되고, 말을 마치면 약 0.8초 무음 후 자동으로 인식해 출력합니다.

```
[실시간 STT] 마이크 대기 중... (Ctrl+C로 종료)

[인식] 안녕하세요, 주문하고 싶어요.
      (1.23초)
```

`Ctrl+C` 로 종료합니다.

---

## FastAPI 서버

### 서버 실행

```bash
uvicorn api.main:app --reload
```

실행 후 `http://localhost:8000/docs` 에서 Swagger UI로 전체 API를 확인하고 테스트할 수 있습니다.

### API 엔드포인트

| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/menu` | 메뉴 목록 조회 (`?q=검색어` 로 키워드 검색) |
| GET | `/menu/{id}` | 메뉴 상세 조회 |
| POST | `/stt/transcribe` | 오디오 파일 업로드 → 텍스트 변환 (로컬 테스트용) |
| WS | `/stt/ws` | 실시간 오디오 스트리밍 → 텍스트 반환 |

### STT API

**REST — 파일 업로드 (로컬 테스트용)**

Swagger UI(`/docs`)에서 오디오 파일을 직접 업로드해 테스트할 수 있습니다.

```
POST /stt/transcribe
지원 형식: wav, mp3, m4a, ogg, flac
반환: {"text": "인식된 텍스트", "language": "ko"}
```

**WebSocket — 실시간 스트리밍 (키오스크 브라우저 연동용)**

브라우저에서 마이크 오디오를 float32 PCM 청크(50ms 단위)로 전송하면,
발화가 끝날 때마다 인식 결과를 JSON으로 반환합니다.

```
WS /stt/ws
송신: float32 PCM 바이트 (16kHz, mono, 50ms 청크)
수신: {"text": "인식된 텍스트"}
```

> ⚠️ `/stt/ws` 로 받은 `text` 를 AI 에이전트의 입력으로 사용합니다.
> 에이전트는 이 텍스트를 기반으로 메뉴 검색, 장바구니 추가 등 주문 흐름을 처리합니다.

---

```text
sadollar-ai/
│
├── data/                          # 데이터 파일 모음
│   ├── ria_menu.json              # 단품 메뉴 데이터 (82개, 카테고리별 100번대 id)
│   ├── ria_options.json           # 세트 구성 옵션 (드링크/사이드/토핑 43개)
│   ├── ria_sets_raw.json          # 세트 메뉴 데이터 (23개)
│   └── ria_menu.db                # SQLite DB 파일 (gitignore 제외)
│
├── app/
│   ├── rag/
│   │   ├── loader.py              # ria_menu.json → Document 변환
│   │   ├── vector_store.py        # ChromaDB 임베딩 저장
│   │   └── chroma.py              # ChromaDB 연결 및 검색
│   │
│   └── tools/
│       ├── menu_tools.py          # 메뉴 검색 도구 (RAG)
│       └── cart_tools.py          # 장바구니 도구
│
├── crawling/
│   ├── crawling.py                # 롯데리아 단품 메뉴 크롤링
│   ├── crawling_sets.py           # 롯데리아 세트 메뉴 크롤링
│   ├── db.py                      # 크롤링 결과 DB 저장
│   └── export_js.py               # JS 데이터 추출
│
├── api/
│   ├── main.py                    # FastAPI 앱 진입점, 라우터 등록
│   └── routes/
│       ├── menu.py                # GET /menu, GET /menu/{id}
│       └── stt.py                 # POST /stt/transcribe, WS /stt/ws
│
├── voice/
│   ├── stt.py                     # Whisper STT (파일 인식)
│   ├── stt_realtime.py            # Whisper STT (실시간 마이크 인식, listen_once 포함)
│   └── tts.py                     # TTS
│
├── tests/
│   ├── 뉴스녹음.m4a
│   └── results/                   # STT 결과 저장 디렉토리
│
├── db_setup.py                    # DB 테이블 생성 스크립트 (최초 1회)
├── insert_data.py                 # JSON → DB 데이터 삽입 스크립트 (최초 1회)
├── add_imgurl.py                  # img_url 매칭 스크립트 (최초 1회)
├── test.py                        # RAG 메뉴 검색 테스트
├── requirements.txt
└── .env                           # OpenAI API 키 설정 (gitignore 제외)
```
