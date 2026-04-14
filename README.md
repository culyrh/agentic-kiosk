# 🍔 Sadollar Kiosk - AI 음성 주문 키오스크

롯데리아 매장에서 사용자가 음성으로 메뉴를 탐색하고 결제까지 완료할 수 있는 배리어 프리(Barrier-free) 음성 주문 시스템입니다.

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

### DB 초기화 (최초 1회)

```bash
# 1. 테이블 생성
python db_setup.py

# 2. img_url 매칭
python add_imgurl.py

# 3. JSON 데이터 → DB 삽입
python insert_data.py
```

### 세트 메뉴 크롤링 (최초 1회)

세트 메뉴 데이터가 없거나 업데이트가 필요할 때 실행합니다.

```bash
# 세트 정보 크롤링 (알레르기, 열량, 원산지)
python crawling/crawling_set.py

# 세트 이미지 크롤링 (셀레니움 필요)
python crawling/crawling_setimage.py

# 크롤링 후 DB 재삽입
python insert_data.py

# 일부 데이터는 직접 입력함
```

---

## 시스템 동작 구조

```
사용자 음성
↓
STT (Whisper)
↓
텍스트
↓
AI 에이전트 (LangChain + GPT-4o)
↓
도구 선택
↓
┌────────────────────────────────────────────────────────────────┐
│                                                                │
│  [메뉴 검색]              [메뉴 조회]         [장바구니/주문]     │
│  search_menu              get_menu_info      add_to_cart       │
│                           get_menu_by_price  remove_from_cart  │
│       ↓                        ↓             view_cart         │
│  query(의미) 있음?              ↓             confirm_order     │
│  ┌──YES──┐               SQLite              clear_cart        │
│  ↓       ↓               (이름 LIKE 검색)          ↓            │
│ ChromaDB  SQLite               ↓             SQLite            │
│ (벡터검색) (카테고리           메뉴 정보      (이름 기반 매칭      │ 
│  의미기반)  전체조회,           반환          → cart/orders      │ 
│     ↓      LIMIT+OFFSET)                     테이블 처리)       │ 
│  텍스트     ↓                                      ↓           │
│  반환      텍스트 반환                          결과 반환        │
└────────────────────────────────────────────────────────────────┘
↓
LLM 응답 생성
↓
TTS
↓
음성 출력
```

### 1. 설계 원칙

- **ChromaDB**: `search_menu`에서 의미 기반 쿼리(query 파라미터)가 있을 때만 사용
- **카테고리 전체 조회**: SQLite LIMIT/OFFSET 페이지네이션으로 처리 (ChromaDB k 제한 우회)
- **장바구니 추가/제거**: ChromaDB를 거치지 않고 SQLite 이름 매칭으로 직접 처리
- **장바구니/주문**: SQLite `cart`, `orders` 테이블에서 전담 처리

<br>

### 2. Self-querying 미적용 이유 및 향후 계획

현재 `search_menu`는 LangChain Self-querying Retriever 대신 **수동 파라미터 추출** 방식을 사용한다.

**현재 방식 (수동 파라미터 추출)**
- LLM이 사용자 발화에서 `query`, `category`, `badge`, `exclude`, `exclude_names`, `offset` 파라미터를 직접 추출해 tool에 넘김
- tool docstring의 예시가 LLM의 파라미터 추출을 가이드
- 결과적으로 Self-querying과 동일한 효과

**Self-querying을 도입하지 않은 이유**
- DB 스키마가 아직 확정되지 않아 ChromaDB 메타데이터 구조가 바뀔 수 있음
- 현재 수동 방식으로도 `category`, `badge` 필터가 충분히 동작함

**Self-querying 도입을 고려할 시점**
- DB/ChromaDB 스키마 확정 이후
- "세트 포함 + 8000원 이하 + 매운 버거" 같은 복합 필터 쿼리 실패 케이스가 쌓일 때

<br>

### 3. 현재 한계 및 향후 개선 계획

**대화 히스토리**
- 현재: 메모리(`defaultdict`) 기반 → 서버 재시작 시 히스토리 소멸
- 현재: 대화가 길어질수록 히스토리가 무한정 쌓여 토큰 비용 증가
- 향후: Redis/DB 영속화, 슬라이딩 윈도우(최근 N턴만 유지) 도입 예정

**remove_from_cart 중복 호출**
- 현재: SYSTEM_PROMPT 지시 + 턴당 1회 플래그(`_remove_called`)로 방지
- 한계: LLM이 히스토리에서 정확한 메뉴명을 알고 있을 때 엣지케이스 발생 가능

**주문 외 발화 처리**
- 현재: 별도 필터 없음 → LLM이 주문 외 질문도 응답해 비용 낭비
- 향후: 백엔드 미들웨어(1차) + SYSTEM_PROMPT(2차) 2단계 필터링 예정 (Issue 참고)

---

## DB 구조

### SQLite 테이블 (ria_menu.db)

| 테이블 | 역할 | 데이터 수 |
|--------|------|-----------|
| menu | 단품 메뉴 전체 | 78개 |
| options | 세트 구성 선택지 (드링크/사이드) | 41개 |
| set_menus | 버거별 세트 구성 및 가격 | 23개 |
| cart | 주문 중인 장바구니 (주문 시 채워짐) | - |
| orders | 결제 완료된 주문 내역 | - |
| sessions | 현재 대화 상태 저장 | - |

> **set_options 테이블을 제거한 이유**
> 초기 설계에서는 세트별로 선택 가능한 옵션을 미리 연결하는 set_options 테이블을 두었으나,
> 롯데리아의 모든 세트는 동일한 음료/사이드 옵션을 제공하므로 불필요한 중복 데이터가 발생했습니다.
> 대신 세트 주문 시 cart 테이블의 drink_option, side_option 컬럼에 선택값을 저장하는 방식으로 단순화했습니다.

<br>

### 테이블 상세 구조

**menu 테이블**
| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | INTEGER | 카테고리별 100번대 고유 ID |
| category | TEXT | 버거/디저트/치킨/음료/아이스샷/토핑 |
| name | TEXT | 메뉴명 |
| badge | TEXT | 뱃지 배열 JSON (예: ["NEW", "BEST"]) |
| price | INTEGER | 단품 가격 (정수) |
| description | TEXT | 메뉴 설명 |
| img_url | TEXT | 이미지 URL |
| allergy | TEXT | 알레르기 배열 JSON (예: ["달걀", "밀"]) |
| origin | TEXT | 원산지 정보 |
| nutrition | TEXT | 영양정보 딕셔너리 JSON |
| spicy_level | INTEGER | 매운맛 단계 (0~3) |

**options 테이블**
| 컬럼 | 타입 | 설명 |
|------|------|------|
| option_id | TEXT | D01~D20 (드링크), S01~S21 (사이드) |
| option_type | TEXT | 드링크 / 사이드 |
| menu_id | INTEGER | menu 테이블 참조 |
| extra_price | INTEGER | 기본 옵션 대비 추가 금액 |

**set_menus 테이블**
| 컬럼 | 타입 | 설명 |
|------|------|------|
| set_id | INTEGER | 세트 고유 ID (자동 증가) |
| burger_menu_id | INTEGER | menu 테이블의 버거 ID 참조 |
| name | TEXT | 세트명 |
| set_price | INTEGER | 세트 가격 (단품 + 2,000원) |
| description | TEXT | 세트 설명 |
| img_url | TEXT | 세트 이미지 URL |
| allergy | TEXT | 알레르기 정보 |
| origin | TEXT | 원산지 정보 |
| calorie | TEXT | 열량 범위 (예: 706kcal ~ 1431kcal) |

**cart 테이블**
| 컬럼 | 타입 | 설명 |
|------|------|------|
| cart_id | INTEGER | 장바구니 항목 ID (자동 증가) |
| session_id | TEXT | 세션 ID |
| menu_id | INTEGER | menu 테이블 참조 |
| is_set | INTEGER | 세트 여부 (0=단품, 1=세트) |
| drink_option | TEXT | 선택한 드링크 option_id |
| side_option | TEXT | 선택한 사이드 option_id |
| quantity | INTEGER | 수량 |
| unit_price | INTEGER | 단가 |

**orders 테이블**
| 컬럼 | 타입 | 설명 |
|------|------|------|
| order_id | INTEGER | 주문 ID (자동 증가) |
| session_id | TEXT | 세션 ID |
| total_price | INTEGER | 총 결제 금액 |
| payment_method | TEXT | 결제 수단 |
| status | TEXT | pending → paid |
| created_at | TEXT | 주문 시각 |

**sessions 테이블**
| 컬럼 | 타입 | 설명 |
|------|------|------|
| session_id | TEXT | 세션 ID |
| current_state | TEXT | browsing → ordering → paying → done |
| last_recommended | TEXT | 마지막 추천 메뉴명 |
| updated_at | TEXT | 마지막 업데이트 시각 |

### 메뉴 ID 체계 (카테고리별 100번대)

| 카테고리 | ID 범위 |
|----------|---------|
| 버거 | 101 ~ 199 |
| 디저트 | 201 ~ 299 |
| 치킨 | 301 ~ 399 |
| 음료 | 401 ~ 499 |
| 아이스샷 | 501 ~ 599 |
| 토핑 | 601 ~ 699 |

### JSON 데이터 구조

**단품 메뉴 (ria_menu.json)**
```json
{
  "id": 101,
  "category": "버거",
  "name": "통다리 크리스피치킨버거(파이어핫)",
  "badge": ["NEW"],
  "price": 6900,
  "description": "...",
  "allergy": ["달걀", "밀", "대두"],
  "origin": "닭고기 - 브라질산",
  "nutrition": {"총중량": "231", "열량": "594"},
  "img_url": "https://...",
  "spicy_level": 0
}
```

**세트 메뉴 (ria_sets.json)**
```json
{
  "name": "통다리 크리스피치킨버거세트(파이어핫)",
  "burger_menu_id": 101,
  "set_price": 8900,
  "img_url": "https://...",
  "allergy": "달걀, 밀, 대두, ...",
  "origin": "닭고기 - 브라질산",
  "calorie": "706kcal ~ 1431kcal",
  "set_id": 23
}
```

**옵션 (ria_options.json)**
```json
{"option_id": "D01", "option_type": "드링크", "menu_id": 401, "name": "콜라", "extra_price": 0}
```

---

## API 명세

서버 실행:
```bash
uvicorn api.main:app --reload
```

Swagger UI: http://127.0.0.1:8000/docs

### 메뉴
| Method | URL | 설명 |
|--------|-----|------|
| GET | /menu | 전체 메뉴 조회 |
| GET | /menu?category=버거 | 카테고리 필터 |
| GET | /menu?q=불고기 | 키워드 검색 |
| GET | /menu/{id} | 단건 조회 |
| GET | /menu/{id}/set | 세트 조회 |

### 장바구니
| Method | URL | 설명 |
|--------|-----|------|
| GET | /cart/{session_id} | 장바구니 조회 |
| POST | /cart | 장바구니 담기 |
| PUT | /cart/{cart_id} | 수량 수정 |
| DELETE | /cart/{cart_id} | 항목 삭제 |
| DELETE | /cart/session/{session_id} | 전체 비우기 |

### 주문
| Method | URL | 설명 |
|--------|-----|------|
| POST | /order | 주문 생성 |
| POST | /order/{order_id}/payment | 결제 |
| GET | /order/{session_id} | 주문 내역 조회 |

### 세션
| Method | URL | 설명 |
|--------|-----|------|
| POST | /session/{session_id} | 세션 생성 |
| GET | /session/{session_id} | 세션 조회 |
| PUT | /session/{session_id} | 세션 업데이트 |

### RAG 검색
| Method | URL | 설명 |
|--------|-----|------|
| POST | /search | 자연어 메뉴 검색 |

### 음성
| Method | 경로 | 설명 |
|--------|------|------|
| POST | `/stt/transcribe` | 오디오 파일 업로드 → 텍스트 변환 (로컬 테스트용) |
| WS | `/stt/ws` | 실시간 오디오 스트리밍 → 텍스트 반환 |

#### POST /search 요청 예시
```json
{
  "query": "치즈 들어가는 햄버거 추천해줘",
  "k": 5,
  "score_threshold": 0.5
}
```

#### POST /stt/transcribe (로컬 테스트용)

Swagger UI(`/docs`)에서 오디오 파일을 직접 업로드해 테스트할 수 있습니다.

```
POST /stt/transcribe
지원 형식: wav, mp3, m4a, ogg, flac
반환: {"text": "인식된 텍스트", "language": "ko"}
```

#### WS /stt/ws (키오스크 브라우저 연동용)

브라우저에서 마이크 오디오를 float32 PCM 청크(50ms 단위)로 전송하면,
발화가 끝날 때마다 인식 결과를 JSON으로 반환합니다.

```
WS /stt/ws
송신: float32 PCM 바이트 (16kHz, mono, 50ms 청크)
수신: {"text": "인식된 텍스트"}
```

> `/stt/ws` 로 받은 `text` 를 AI 에이전트의 입력으로 사용합니다.
> 에이전트는 이 텍스트를 기반으로 메뉴 검색, 장바구니 추가 등 주문 흐름을 처리합니다.

---


## RAG 메뉴 검색 (ChromaDB 초기화)

FastAPI 서버 실행 전 최초 1회 실행해서 ChromaDB를 생성해야 합니다.
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

---

## STT 테스트 (음성 인식)

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

## 프로젝트 구조

```
sadollar-ai/
│
├── api/
│   ├── main.py                    # FastAPI 서버 진입점
│   └── routes/
│       ├── menu.py                # 메뉴 API
│       ├── cart.py                # 장바구니 API
│       ├── order.py               # 주문/결제 API
│       ├── session.py             # 세션 API
│       ├── search.py              # RAG 검색 API
│       └── stt.py                 # POST /stt/transcribe, WS /stt/ws
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
│   ├── crawling.py                # 단품 메뉴 크롤링 → ria_menu.json
│   ├── crawling_set.py            # 세트 메뉴 크롤링 (이미지 제외) → ria_sets.json
│   └── crawling_setimage.py       # 세트 이미지 크롤링 → ria_sets.json 업데이트
│
├── data/                          # 데이터 파일 모음
│   ├── ria_menu.json              # 단품 메뉴 데이터 (82개, 카테고리별 100번대 id)
│   ├── ria_options.json           # 세트 구성 옵션 (드링크/사이드/토핑 43개)
│   ├── ria_sets_raw.json          # 세트 메뉴 데이터 (23개)
│   └── ria_menu.db                # SQLite DB 파일 (gitignore 제외)
│
├── db/
│   └── sqlite.py                  # DB 연결 및 쿼리 함수
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
├── test.py                        # RAG 메뉴 검색 테스트
├── requirements.txt
└── .env                           # OpenAI API 키 설정 (gitignore 제외)
```

---
